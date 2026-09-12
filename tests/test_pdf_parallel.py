"""Real process rendering, cancellation, cache reuse and shutdown regressions."""
import multiprocessing
import os
import time

import pymupdf
import pytest
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QImage

from markforge.io import pdftiles, pdfrender
from markforge.io.pdfio import to_image
from markforge.pdf import engine


def source_pdf(rotation=0):
    document = pymupdf.open()
    page = document.new_page(width=1200, height=800)
    page.draw_rect(page.rect, fill=(.8, .9, 1), color=None)
    page.draw_line((50, 80), (1150, 700), width=3)
    annot = page.add_rect_annot(pymupdf.Rect(20, 20, 70, 60))
    annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
    annot.update()
    xref = annot.xref
    page.set_rotation(rotation)
    width, height = page.rect.width, page.rect.height
    data = document.tobytes()
    document.close()
    return data, width, height, xref


def until(qapp, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.002)
    assert predicate(), 'PDF worker did not respond'


@pytest.mark.parametrize('rotation', [0, 90])
def test_parallel_tiles_match_serial_pixels_and_own_their_buffers(qapp, rotation):
    data, width, height, xref = source_pdf(rotation)
    keys = [pdftiles.TileKey('drawing', 0, 2, col, row, True, (xref,))
            for col in range(2) for row in range(2)]
    wanted, images = set(keys), {}
    worker = pdftiles._Worker(wanted, processes=2)
    worker.tileDone.connect(lambda key, image: images.__setitem__(key, image), Qt.QueuedConnection)
    heartbeats = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: heartbeats.append(time.monotonic()))
    timer.start()
    worker.start()
    try:
        for key in keys:
            worker.submit(key, data, width, height)
        until(qapp, lambda: len(images) == len(keys))
        assert len(worker.stats) == 2
        assert os.getpid() not in worker.stats
        assert len(heartbeats) >= 2
        with pymupdf.open(stream=data, filetype='pdf') as document:
            drawing = engine.display_list(document, 0, True, (xref,))
            for key, actual in images.items():
                box = key.page_rect().intersected(QRectF(0, 0, width, height))
                expected = to_image(engine.raster_from(drawing, (box.left(), box.top(), box.right(), box.bottom()), key.scale))
                assert not actual.isNull()
                assert actual == expected
        before = {key: image.copy() for key, image in images.items()}
        images.clear()
        for key in keys:
            worker.submit(key, data, width, height)
        until(qapp, lambda: len(images) == len(keys))
        assert all(image == before[key] for key, image in images.items())
        assert all(stats['parses'] == 1 and stats['opens'] == 1 for stats in worker.stats.values())
    finally:
        timer.stop()
        worker.stop()
        assert worker.wait(5000)
    # The shared memory has been unlinked; queued QImages still own their bytes.
    assert all(image == before[key] for key, image in images.items())


def test_renderer_annotation_variants_and_lru_do_not_leak_flags(tmp_path):
    data, width, height, xref = source_pdf()
    path = tmp_path / 'annotations.pdf'
    path.write_bytes(data)
    renderer = pdfrender.Renderer()
    try:
        def render(omitted):
            return to_image(renderer.render(str(path), 0, True, omitted, (0, 0, 100, 100), 1))
        visible = render(())
        hidden = render((xref,))
        assert visible.pixelColor(40, 40).red() == 255
        assert hidden.pixelColor(40, 40) != visible.pixelColor(40, 40)
        assert render(()) == visible
        assert renderer.opens == 2 and renderer.parses == 2
        for index in range(12):
            other = tmp_path / f'other-{index}.pdf'
            other.write_bytes(data)
            renderer.render(str(other), 0, False, (), (0, 0, 100, 100), 1)
        assert len(renderer.documents) <= pdfrender.MAX_DOCUMENTS
        assert len(renderer.drawings) <= pdfrender.MAX_DISPLAY_LISTS
        assert render(()) == visible
    finally:
        renderer.close()


def test_pan_cancels_old_tiles_but_keeps_the_other_view(qapp):
    from PySide6.QtWidgets import QWidget
    cache = pdftiles.TileCache()
    cache._ask = lambda key, *args, **kw: cache._waiting.add(key)
    first, second = QWidget(), QWidget()
    page = QRectF(0, 0, 6000, 6000)
    cache.tiles('pdf', b'pdf', 0, page, 2, QRectF(0, 0, 200, 200), consumer=first)
    cache.tiles('pdf', b'pdf', 0, page, 2, QRectF(1000, 0, 200, 200), consumer=second)
    cache.tiles('pdf', b'pdf', 0, page, 2, QRectF(3000, 0, 200, 200), consumer=first)
    assert not any(key.col == 0 for key in cache._waiting)
    assert any(key.col == 1 for key in cache._waiting)
    assert any(key.col == 5 for key in cache._waiting)


def test_centre_tiles_are_first_out_of_the_worker_stack(qapp):
    cache = pdftiles.TileCache()
    asked = []
    cache._ask = lambda key, *args, **kw: asked.append(key)
    page = QRectF(0, 0, 3000, 3000)
    cache.tiles('pdf', b'pdf', 0, page, 1, page)
    assert (asked[-1].col, asked[-1].row) == (1, 1)


def test_forget_drops_queued_results_instead_of_resurrecting_a_pdf(qapp):
    cache = pdftiles.TileCache()
    key = pdftiles.TileKey('pdf', 0, 1, 0, 0, False)
    cache._waiting.add(key)
    cache.forget('pdf')
    image = QImage(10, 10, QImage.Format_RGB32)
    image.fill(Qt.red)
    cache._tile_arrived(key, image)
    assert key not in cache._tiles
    assert not cache._waiting


def test_render_failure_keeps_fallback_and_retries_without_busy_loop(qapp):
    cache = pdftiles.TileCache()
    key = pdftiles.TileKey('pdf', 0, 1, 0, 0, False)
    cache._waiting.add(key)
    cache._tile_arrived(key, QImage())
    assert key not in cache._tiles
    requests = []
    cache._started = lambda: type('Worker', (), {'submit': lambda _, *args: requests.append(args)})()
    page = QRectF(0, 0, 100, 100)
    _, missing = cache.tiles('pdf', b'pdf', 0, page, 1, page, False)
    assert missing and not requests
    until(qapp, lambda: time.monotonic() >= cache._failures[key][1])
    cache.tiles('pdf', b'pdf', 0, page, 1, page, False)
    assert len(requests) == 1


def test_child_exit_recovers_and_shutdown_leaves_no_renderer(qapp):
    data, width, height, _ = source_pdf()
    key = pdftiles.TileKey('drawing', 0, 1, 0, 0, False)
    wanted, images = {key}, []
    worker = pdftiles._Worker(wanted, processes=1)
    worker.tileDone.connect(lambda key, image: images.append(image), Qt.QueuedConnection)
    worker.start()
    pids = set()
    try:
        worker.submit(key, data, width, height)
        until(qapp, lambda: bool(images))
        pids.update(worker.stats)
        child = next(child for child in multiprocessing.active_children() if child.pid in pids)
        child.terminate()
        child.join(3)
        images.clear()
        worker.submit(key, data, width, height)
        until(qapp, lambda: bool(images))
        assert not images[0].isNull()
        assert len(worker.stats) == 2
        pids.update(worker.stats)
    finally:
        worker.stop()
        assert worker.wait(5000)
    assert not any(child.pid in pids for child in multiprocessing.active_children())
