"""Saving and reopening equations (phase 4; decisions 3 and 4).

Every save writes a fresh, compact file: the page's own content, CalcForge's
tagged layers over it (the sheet, and the equations as vector drawing and
text), the markups as annotations and the record. A signed file is appended
to instead. Opening it here takes the layers off and rebuilds live equations
from the record. Everything goes through the real window.
"""
from __future__ import annotations

import os

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt

from markforge.calc.engine.display import display_text
from markforge.io import calclayer, pdfbase
from markforge.io import project as project_io
from markforge.items.calc import CalcItem
from tests.test_calc_modes import at, into_calc_mode, typed
from tests.test_usability import click, press_key


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    return window


def equations(window, page=None):
    pages = window.document.pages if page is None else [window.document.pages[page]]
    return [item for p in pages for item in p.frame.markups() if isinstance(item, CalcItem)]


def write_lines(window, lines, x=100, y=120, page=0):
    window.go_to_page(page)
    window.toggle_calc_mode(True)
    p = window.document.pages[page].frame.mapToScene(QPointF(x, y))
    click(window.view, p.x(), p.y())
    for line in lines:
        typed(window, line)
        press_key(window.view, Qt.Key_Return)
    press_key(window.view, Qt.Key_Escape)


def src(item):
    """An equation's text as typed (SMath shows := as ≔)."""
    return item.text().replace("≔", ":")


def answer(window, text):
    """The shown result of the equation whose source is *text*."""
    (item,) = [i for i in equations(window) if src(i) == text]
    return display_text(item.region.display)


def reopen(window, path):
    window.open_path(path)
    window.undo_stack.clear()
    window.current_index = 0
    window.rebuild_scenes()


def a_drawing(path, pages=1, words="DRAWING"):
    document = pymupdf.open()
    for number in range(pages):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 72), f"{words} {number + 1}")
        for step in range(40):
            page.draw_line((72, 100 + step * 10), (500, 100 + step * 10))
    document.save(path)
    document.close()


def save_to(window, path):
    window.document.path = path
    assert window.save_document()


def the_page_text(path, index=0):
    with pymupdf.open(path) as document:
        return document[index].get_text()


# -- the file as another reader sees it ------------------------------------------------

def test_equations_are_saved_as_real_text_in_a_tagged_layer(win, tmp_path):
    write_lines(win, ["x:2", "y:x*3", "y="])
    assert answer(win, "y=") == "6"
    path = str(tmp_path / "calc.pdf")
    save_to(win, path)
    text = the_page_text(path)
    assert "6" in text and "y" in text, "the result reads back as text"
    with pymupdf.open(path) as document:
        page = document[0]
        assert list(page.annots()) == [], "equations are page content, not annotations"
        assert calclayer.layer_print(document, 0, calclayer.CALC) is not None
        assert calclayer.page_uid(document, 0) == win.document.pages[0].uid


def test_another_reader_can_move_the_markups_but_not_the_equations(win, tmp_path):
    from pypdf import PdfReader
    from markforge.items.shapes import RectItem

    write_lines(win, ["a:1.5"])
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 80, 40))
    win.document.pages[0].frame.add_markup(box, QPointF(300, 500))
    path = str(tmp_path / "both.pdf")
    save_to(win, path)
    reader = PdfReader(path)
    annotations = [a.get_object() for a in reader.pages[0].get("/Annots") or []]
    assert [str(a["/Subtype"]) for a in annotations] == ["/Square"], \
        "the markup is an annotation, the equation is not, so no markups list shows it"
    assert "1.5" in reader.pages[0].extract_text()


def same_ink_as_the_screen(win, path, scale=2.0):
    """The page as MuPDF draws *path*, against the page as CalcForge draws it:
    the same ink in the same places."""
    import numpy as np
    from PySide6.QtGui import QImage, QPainter

    frame = win.document.pages[0].frame
    size = (int(frame.page.width_pt * scale), int(frame.page.height_pt * scale))
    image = QImage(size[0], size[1], QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    frame.render_page(painter, QRectF(0, 0, size[0], size[1]), for_print=True)
    painter.end()
    screen = np.frombuffer(image.constBits(), np.uint8).reshape(
        size[1], image.bytesPerLine() // 4, 4)
    screen = screen[:, :size[0], :3].mean(axis=2)
    with pymupdf.open(path) as document:
        pix = document[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), annots=True)
    saved = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    saved = saved[:size[1], :size[0], :3].mean(axis=2)
    ink_screen, ink_saved = screen < 160, saved < 160
    assert ink_screen.sum() > 200, "the equations drew something"
    ys, xs = np.nonzero(ink_screen)
    ys2, xs2 = np.nonzero(ink_saved)
    for a, b in ((xs.min(), xs2.min()), (xs.max(), xs2.max()),
                 (ys.min(), ys2.min()), (ys.max(), ys2.max())):
        assert abs(int(a) - int(b)) <= 4, "the ink lands in the same place"
    both = (ink_screen & ink_saved).sum()
    assert both / max(ink_screen.sum(), 1) > 0.6, "and is the same ink"


def test_the_saved_page_looks_like_the_screen(win, tmp_path):
    write_lines(win, ["P1:4.5*2", "P1=", "Q1:P1^2+sqrt(P1)", "Q1="])
    path = str(tmp_path / "look.pdf")
    save_to(win, path)
    same_ink_as_the_screen(win, path)


def test_an_exported_page_looks_like_the_screen_at_any_resolution(win, tmp_path):
    """Export and print draw at the device's resolution; SMath's fonts are in
    points, so without care they come out bigger than the layout (a third too
    big at 200 dpi, running into each other at 300)."""
    from markforge.io import export as export_io

    write_lines(win, ["P1:4.5*2", "P1=", "Q1:P1^2+sqrt(P1)", "Q1="])
    for resolution in (150, 300, 600):
        path = str(tmp_path / f"export{resolution}.pdf")
        export_io.export_pdf(win.document, path, resolution=resolution)
        same_ink_as_the_screen(win, path)
        assert "Q1" in the_page_text(path)


# -- reopening -------------------------------------------------------------------------

def test_reopening_rebuilds_live_equations_and_takes_the_layer_off(win, tmp_path):
    write_lines(win, ["x:2", "y:x*3", "y="])
    path = str(tmp_path / "calc.pdf")
    save_to(win, path)
    reopen(win, path)
    assert len(equations(win)) == 3
    assert answer(win, "y=") == "6"
    assert win.document.open_warnings == []
    # the page underneath is the page without CalcForge's drawing on it
    page = win.document.pages[0]
    from markforge.items.calc import created_here
    assert created_here(page), "a page written here stays a page written here (SMath's margins)"
    for data in win.document.assets.values():
        if data[:4] == b"%PDF":
            with pymupdf.open(stream=data) as source:
                assert "6" not in source[0].get_text()
                assert not calclayer.has_layers(source) or \
                    calclayer.layer_print(source, 0, calclayer.CALC) is None
    # and editing them still works
    (x,) = [i for i in equations(win) if src(i) == "x:2"]
    win.view.calc.focus(x, x.sceneBoundingRect().center())
    press_key(win.view, Qt.Key_End)
    typed(win, "0")
    press_key(win.view, Qt.Key_Escape)
    assert answer(win, "y=") == "60"


def test_a_drawing_with_equations_reopens_on_its_own_page(win, tmp_path):
    source = str(tmp_path / "drawing.pdf")
    a_drawing(source)
    reopen(win, source)
    write_lines(win, ["L1:3.5'm", "Ar:L1^2", "Ar="])
    assert answer(win, "Ar=") == "12.25 m^2"
    path = str(tmp_path / "checked.pdf")
    save_to(win, path)
    text = the_page_text(path)
    assert "DRAWING 1" in text and "12.25" in text
    reopen(win, path)
    assert answer(win, "Ar=") == "12.25 m^2"
    page = win.document.pages[0]
    with pymupdf.open(stream=win.document.asset(page.pdf_key)) as underneath:
        assert "DRAWING 1" in underneath[0].get_text()
        assert "12.25" not in underneath[0].get_text()
    record, assets = pdfbase.read_record(pdfbase.record_in(path))
    assert not [key for key in assets if key.endswith(".pdf")], \
        "the drawing is not stored a second time inside its own record"


def test_repeated_saves_do_not_grow_the_file(win, tmp_path):
    from markforge.items.shapes import RectItem

    source = str(tmp_path / "drawing.pdf")
    a_drawing(source, pages=2)
    reopen(win, source)
    write_lines(win, ["p:2", "q:p*p", "q="])
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 80, 40))
    win.document.pages[1].frame.add_markup(box, QPointF(300, 500))
    path = str(tmp_path / "grow.pdf")
    save_to(win, path)
    sizes = [os.path.getsize(path)]
    for _ in range(3):
        save_to(win, path)                    # saved again as it is
        sizes.append(os.path.getsize(path))
        reopen(win, path)                     # and after opening it again
        save_to(win, path)
        sizes.append(os.path.getsize(path))
    assert max(sizes) - min(sizes) <= 64, sizes
    assert sizes[0] < os.path.getsize(source) + 60_000, "and it is compact"
    assert answer(win, "q=") == "4"
    assert len([i for i in win.document.pages[1].frame.markups()
                if isinstance(i, RectItem)]) == 1


def test_a_layer_changed_elsewhere_warns_and_the_record_wins(win, tmp_path):
    write_lines(win, ["r:7", "r="])
    path = str(tmp_path / "edited.pdf")
    save_to(win, path)
    with pymupdf.open(path) as document:
        page = document[0]
        tagged = [x for x, _n, invoker, _b in page.get_xobjects()
                  if invoker == 0 and calclayer._tag(document, x) == calclayer.CALC]
        inner = [x for x, _n, invoker, _b in page.get_xobjects() if invoker in tagged]
        target = (inner or tagged)[0]
        document.update_stream(target, document.xref_stream(target) + b"\n0 0 m 10 10 l S\n")
        document.save(path + ".x", garbage=0)
    os.replace(path + ".x", path)
    reopen(win, path)
    assert any("changed in another program" in w for w in win.document.open_warnings)
    assert "changed in another program" in win.status_hint.text()
    assert answer(win, "r=") == "7"


def test_pages_reordered_elsewhere_carry_their_equations(win, tmp_path):
    win.add_page() if hasattr(win, "add_page") else win.document.add_page()
    win.rebuild_scenes()
    write_lines(win, ["b:2"], page=0)
    write_lines(win, ["cv:b*10", "cv="], page=1)
    assert answer(win, "cv=") == "20"
    first, second = (p.uid for p in win.document.pages)
    path = str(tmp_path / "pages.pdf")
    save_to(win, path)
    with pymupdf.open(path) as document:
        document.move_page(1, 0)          # (select() would drop the attachments)
        document.save(path + ".x")
    os.replace(path + ".x", path)
    reopen(win, path)
    assert [p.uid for p in win.document.pages] == [second, first]
    assert [src(i) for i in equations(win, 1)] == ["b:2"]
    assert answer(win, "cv=") != "20", "reading order follows the pages: b comes after c now"


def test_pages_deleted_elsewhere_warn_which_variables_went(win, tmp_path):
    win.document.add_page()
    win.rebuild_scenes()
    write_lines(win, ["width:3", "depth:4"], page=0)
    write_lines(win, ["area:width*depth", "area="], page=1)
    path = str(tmp_path / "deleted.pdf")
    save_to(win, path)
    with pymupdf.open(path) as document:
        document.delete_page(0)
        document.save(path + ".x")
    os.replace(path + ".x", path)
    reopen(win, path)
    assert len(win.document.pages) == 1
    (said,) = [w for w in win.document.open_warnings if "deleted" in w]
    assert "depth" in said and "width" in said
    assert [src(i) for i in equations(win)] == ["area:width*depth", "area="]


def test_a_missing_record_opens_as_a_plain_pdf_and_says_so(win, tmp_path):
    write_lines(win, ["sv:5", "sv="])
    path = str(tmp_path / "norecord.pdf")
    save_to(win, path)
    with pymupdf.open(path) as document:
        document.embfile_del(pdfbase.RECORD_ENTRY)
        document.save(path + ".x", garbage=3)
    os.replace(path + ".x", path)
    reopen(win, path)
    assert equations(win) == []
    assert "can't be edited" in win.status_hint.text()


def test_a_markup_added_in_another_program_comes_in(win, tmp_path):
    write_lines(win, ["t:1"])
    path = str(tmp_path / "theirs.pdf")
    save_to(win, path)
    with pymupdf.open(path) as document:
        cloud = document[0].add_rect_annot(pymupdf.Rect(300, 300, 400, 360))
        cloud.set_info(content="from Bluebeam")
        cloud.update()
        document.save(path + ".x")
    os.replace(path + ".x", path)
    reopen(win, path)
    others = [i for i in win.document.pages[0].frame.markups() if not isinstance(i, CalcItem)]
    assert len(others) == 1 and others[0].still_theirs
    save_to(win, path)
    with pymupdf.open(path) as document:
        assert len(list(document[0].annots())) == 1, "still one annotation, theirs"


# -- signed files ------------------------------------------------------------------------

def test_a_signed_file_is_appended_to_and_its_signature_stays_valid(win, tmp_path):
    from tests.signing import signature_is_intact, signed_pdf

    unsigned = str(tmp_path / "unsigned.pdf")
    a_drawing(unsigned)
    with open(unsigned, "rb") as handle:
        original = signed_pdf(str(tmp_path / "signed.pdf"), handle.read())
    path = str(tmp_path / "signed.pdf")
    reopen(win, path)
    write_lines(win, ["f:9.81", "f="])
    save_to(win, path)
    assert "digitally signed" in win.status_hint.text()
    with open(path, "rb") as handle:
        written = handle.read()
    assert written[:len(original)] == original, "the signed bytes are all still there"
    assert signature_is_intact(path)
    assert "9.81" in the_page_text(path)
    # opened again and changed, the calc layer is swapped, not stacked
    reopen(win, path)
    (f,) = [i for i in equations(win) if src(i) == "f:9.81"]
    win.view.calc.focus(f, f.sceneBoundingRect().center())
    press_key(win.view, Qt.Key_End)
    typed(win, "5")
    press_key(win.view, Qt.Key_Escape)
    save_to(win, path)
    assert signature_is_intact(path)
    with pymupdf.open(path) as document:
        page = document[0]
        calc = [x for x, _n, invoker, _b in page.get_xobjects()
                if invoker == 0 and calclayer._tag(document, x) == calclayer.CALC]
        assert len(calc) == 1
        assert "9.815" in page.get_text() and "9.81\n" not in page.get_text()


def test_a_signed_file_whose_pages_changed_is_saved_afresh_and_says_why(win, tmp_path):
    from tests.signing import signed_pdf

    unsigned = str(tmp_path / "unsigned.pdf")
    a_drawing(unsigned)
    with open(unsigned, "rb") as handle:
        signed_pdf(str(tmp_path / "signed.pdf"), handle.read())
    path = str(tmp_path / "signed.pdf")
    reopen(win, path)
    win.document.add_page()
    win.rebuild_scenes()
    save_to(win, path)
    assert "signature no longer applies" in win.status_hint.text()
    assert win.document.signed_source is None


# -- extract, split, insert, autosave ---------------------------------------------------

def test_extracted_pages_carry_their_equations_live(win, tmp_path):
    win.document.add_page()
    win.rebuild_scenes()
    write_lines(win, ["q1:3", "unused:1"], page=0)
    write_lines(win, ["v:6", "v=", "vw:v*q1"], page=1)
    path = str(tmp_path / "extract.pdf")
    win.extract_pages([1], path)
    said = win.status_hint.text()
    assert "q1 is no longer defined" in said and "unused" not in said, \
        "only what the extracted equations use is named"
    reopen(win, path)
    assert [src(i) for i in equations(win)] == ["v:6", "v=", "vw:v*q1"]
    assert answer(win, "v=") == "6"


def test_split_files_carry_their_equations_live(win, tmp_path):
    win.document.add_page()
    win.rebuild_scenes()
    write_lines(win, ["g:1"], page=0)
    write_lines(win, ["h:2"], page=1)
    made = win.split_into_files(1, str(tmp_path))
    assert len(made) == 2
    reopen(win, made[1])
    assert [src(i) for i in equations(win)] == ["h:2"]


def test_inserting_a_calcforge_pdf_brings_its_equations_live(win, tmp_path):
    write_lines(win, ["w:4", "w="])
    path = str(tmp_path / "other.pdf")
    save_to(win, path)
    win.new_document(confirm=False)
    win.rebuild_scenes()
    write_lines(win, ["z:w+1", "z="])
    win.insert_calcforge_pages(path, at=0)
    assert len(win.document.pages) == 2
    assert answer(win, "z=") == "5", "the inserted page comes first, so w is defined above z"
    with pymupdf.open(stream=win.document.asset(win.document.pages[0].pdf_key)) \
            if win.document.pages[0].pdf_key else pymupdf.open() as underneath:
        assert all("4" not in p.get_text() for p in underneath)


def test_autosave_writes_the_same_format(win, tmp_path):
    write_lines(win, ["n:8"])
    win.document.path = str(tmp_path / "doc.pdf")
    win.document.modified = True
    made = win.write_autosave()
    assert made and project_io.carries_a_document(made)
    with pymupdf.open(made) as document:
        assert document.page_count == 1
    record, _assets = pdfbase.read_record(pdfbase.record_in(made))
    assert any(item.get("type") == "calc" for item in record["pages"][0]["items"])
