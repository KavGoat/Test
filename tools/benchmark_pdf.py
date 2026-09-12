"""Measure PDF tile throughput and UI heartbeat gaps on a repeatable drawing.

    python tools/benchmark_pdf.py --workers 1 2 4 --rounds 3
    python tools/benchmark_pdf.py --pdf drawing.pdf --workers 1 4

Numbers include process startup on the cold round. Warm rounds reuse parsed
pages but deliberately rerender the tiles, so they measure CPU throughput
rather than pixmap-cache hits. No timing assertions depend on machine speed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def synthetic_pdf():
    import pymupdf
    pdf = pymupdf.open()
    page = pdf.new_page(width=2384, height=1684)
    # 60,000 short engineering-style segments.
    content = ['0.35 w\n']
    for row in range(200):
        for col in range(300):
            x, y = 5 + col * 7.9, 5 + row * 8.3
            content.append(f'{x:.2f} {y:.2f} m {x+6:.2f} {y+4:.2f} l S\n')
    xref = pdf.get_new_xref()
    pdf.update_object(xref, '<<>>')
    pdf.update_stream(xref, ''.join(content).encode())
    page.set_contents(xref)
    data = pdf.tobytes(deflate=True)
    pdf.close()
    return data


def measure(application, data, width, height, processes, rounds, legacy=None, tile=1024):
    from PySide6.QtCore import QTimer, Qt
    from markforge.io import pdftiles
    module = pdftiles
    if legacy:
        name = 'markforge.io._benchmark_legacy'
        spec = importlib.util.spec_from_file_location(name, legacy)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    module.TILE = tile
    waiting = set()
    worker = module._Worker(waiting) if legacy else module._Worker(waiting, processes=processes)
    finished, digests, results, ticks = set(), {}, [], []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))

    def arrived(key, image):
        if image.isNull():
            raise RuntimeError(f'Failed to render {key}')
        finished.add(key)
        digests[(key.col, key.row)] = hashlib.sha256(image.constBits()).hexdigest()

    worker.tileDone.connect(arrived, Qt.QueuedConnection)
    worker.start()
    try:
        for iteration in range(rounds):
            keys = [module.TileKey('benchmark', 0, 2., col, row, False)
                    for row in range(int((min(height * 2, 3368) + tile - 1) // tile))
                    for col in range(int((min(width * 2, 4768) + tile - 1) // tile))]
            finished.clear()
            ticks.clear()
            started = time.perf_counter()
            ticks.append(started)
            timer.start()
            waiting.update(keys)
            for key in keys:
                worker.submit(key, data, width, height)
            first = None
            while len(finished) < len(keys):
                application.processEvents()
                if finished and first is None:
                    first = time.perf_counter() - started
                if time.perf_counter() - started > 120:
                    raise RuntimeError('Renderer did not finish within 120 seconds')
                time.sleep(.001)
            elapsed = time.perf_counter() - started
            timer.stop()
            ticks.append(time.perf_counter())
            results.append({'round': iteration, 'tiles': len(keys), 'seconds': round(elapsed, 4),
                            'first_tile_seconds': round(first or elapsed, 4),
                            'max_ui_gap_ms': round(max(b-a for a, b in zip(ticks, ticks[1:])) * 1000, 2)})
    finally:
        timer.stop()
        worker.stop()
        worker.wait()
        application.processEvents()
    return {'workers': 'legacy-thread' if legacy else processes, 'tile_pixels': tile, 'rounds': results,
            'worker_pids': list(getattr(worker, 'stats', {})),
            'pixel_digest': hashlib.sha256(''.join(v for _, v in sorted(digests.items())).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', nargs='+', type=int, default=[1, 2, 4])
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--tile', type=int, choices=[512, 1024, 2048], default=1024)
    parser.add_argument('--pdf')
    parser.add_argument('--legacy-worker')
    args = parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from markforge.pdf import engine
    application = QApplication([])
    data = Path(args.pdf).read_bytes() if args.pdf else synthetic_pdf()
    document = engine.open_bytes(data)
    width, height = engine.page_size(document, 0)
    engine.close(document)
    if args.legacy_worker:
        print(json.dumps(measure(application, data, width, height, 1, args.rounds, args.legacy_worker, args.tile)), flush=True)
    for count in args.workers:
        print(json.dumps(measure(application, data, width, height, count, args.rounds, tile=args.tile)), flush=True)


if __name__ == '__main__':
    main()
