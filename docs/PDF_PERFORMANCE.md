# PDF rendering performance

For editing, snapping and undo latency, see [APP_PERFORMANCE.md](APP_PERFORMANCE.md).

Measured 2026-09-12 on this 8-core Apple Silicon Mac, macOS 26.4.1. The
repeatable fixture is an A1 PDF with 60,000 vector segments. Each round draws
20 tiles of 1024 × 1024 pixels (edge tiles are smaller), at two pixels per
point. Five rounds include one cold start and four warm rounds. Warm rounds
reuse parsed pages but rerender every tile; this is not a pixmap-cache test.

| Renderer | Cold batch | Median warm batch | Largest UI heartbeat gap |
| --- | ---: | ---: | ---: |
| Previous single thread (`aa9cd1c`) | 486.4 ms | 185.1 ms | 121.43 ms |
| 1 render process | 323.6 ms | 177.6 ms | 7.05 ms |
| 2 render processes | 239.7 ms | 94.6 ms | 6.93 ms |
| **4 render processes (default here)** | **255.1 ms** | **61.7 ms** | **11.18 ms** |
| 6 render processes | 294.4 ms | 58.2 ms | 14.58 ms |

Four processes are **3.0× faster for the warm batch** than the previous
renderer, with a substantially smaller UI scheduling gap. Pixel hashes match
exactly across the five renderer configurations. Six processes improve warm
throughput only slightly, with more startup overhead, memory and scheduling
cost. These measurements describe this synthetic rendering workload, not all
PDFs or end-to-end opening/import time.

The heartbeat is a Qt timer scheduled every 5 ms while the main event loop is
pumped. Its largest gap measures UI scheduling stalls during the batch; it is
not a display frame-rate measurement.

## Implementation

- Independent spawned processes run MuPDF. The coordinator thread does no PDF
  parsing or rasterisation. This follows [PyMuPDF's multiprocessing
  guidance](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html).
- Default concurrency is up to four workers, retaining CPU capacity for the
  application/OS. `CALCFORGE_PDF_WORKERS=1` through `8` overrides it, capped at
  available CPU count. Invalid values fall back safely.
- Each source is written once to a private temporary directory and opened by
  the workers. Tile requests do not resend PDF bytes. Retained source files
  target eight files / 256 MiB, excluding busy sources and an individually
  larger PDF needed for the current job.
- Each process retains at most three document variants and six display lists.
  This bounds retained entry counts; complex PDFs can still need substantial
  native decoder memory.
- One fixed shared pixel buffer per worker avoids serialising raster bytes
  through pipes. Four default workers use about 18.5 MiB for these buffers.
  Qt copies the result before the buffer can be reused, so cached/queued images
  remain valid after a new render or worker shutdown.
- Jobs stay in the coordinator until a worker is available. The current view's
  centre is served first. Panning and zooming abandon obsolete tiles, while
  preserving requests from another view of the same page.
- Late results cannot repopulate a forgotten source. Worker exits are detected
  and jobs retried once; transient image failures retry with backoff rather
  than caching a blank tile as a successful render.
- Shutdown stops and joins the processes and removes temporary files/shared
  buffers. GUI entry points and the stress harness are spawn-safe.

The existing 192 MiB tile cache and 32 MiB thumbnail cache remain in effect.
Repainting cached tiles starts no new PDF work. No resolution reduction or
additional image compression was introduced.

## Tile-size comparison

Four processes, the same page area, four warm rounds:

| Tile edge | Tiles | Median warm batch |
| --- | ---: | ---: |
| 512 px | 70 | 79.1 ms |
| **1024 px** | **20** | **61.7 ms** |
| 2048 px | 6 | 66.7 ms |

1024 remains the default. The 2048-pixel option also needs larger shared buffers
and takes longer to deliver the first warm tile.

## Reproduce and validate

```bash
python tools/benchmark_pdf.py --workers 1 2 4 6 --rounds 5
python tools/benchmark_pdf.py --workers 4 --rounds 5 --tile 512
python tools/benchmark_pdf.py --workers 4 --rounds 5 --tile 2048
python tools/benchmark_pdf.py --pdf drawing.pdf --workers 1 4 --rounds 5
```

To include the previous thread implementation:

```bash
git show aa9cd1c:markforge/io/pdftiles.py > /tmp/markforge-pdftiles-baseline.py
python tools/benchmark_pdf.py --workers 1 2 4 6 --rounds 5 --legacy-worker /tmp/markforge-pdftiles-baseline.py
```

Raw timings and hashes are in
[`benchmarks/pdf_render_2026-09-12.json`](benchmarks/pdf_render_2026-09-12.json).

Validation: **911 passed, one skipped** in the full suite (152.98 s).
`tests/test_pdf_parallel.py` adds eight regressions covering actual child
processes, rotated/annotation-filtered pixel equivalence, retained image
ownership, parsed-page reuse, cache limits, pan cancellation across two views,
centre priority, failure recovery and worker cleanup. The latest native
`python tools/session_fuzz.py 97 300` run completed **300 rounds, zero failures**.
The skipped test needs the external PDF corpus, which is not present.

## Follow-up validation — 2026-09-13

Both pages of `tests/data/btx/Document1.pdf` and a generated mixed scan/text/vector sheet
were benchmarked with one and four processes. All corresponding pixel hashes
match. These small reference pages have roughly 8–9 ms warm batches with either
configuration; their timing differences are not a meaningful speedup claim.
The mixed sheet measured median warm batches of 48.3 ms (one worker) and
39.7 ms (four workers). Raw results are in
[`benchmarks/pdf_review_2026-09-13.json`](benchmarks/pdf_review_2026-09-13.json).

```bash
python tools/benchmark_pdf.py --pdf tests/data/btx/Document1.pdf --page 0 --workers 1 4 --rounds 5
python tools/benchmark_pdf.py --pdf tests/data/btx/Document1.pdf --page 1 --workers 1 4 --rounds 5
python tools/benchmark_pdf.py --fixture mixed --workers 1 4 --rounds 5
```

The current checksum uses RGBA8888 pixel bytes so unused RGB row padding cannot
produce false differences. Its hashes should not be compared directly to the
older RGB-format hashes. Annotations are included in the current benchmark.

Latest full suite: **916 passed, no skips**. Both reference pages have exact
serial/parallel comparisons at overview, normal and detail zooms. A native
1,000-round Qt session also passed. The user's own problematic PDFs have not
been supplied, so that specific acceptance check remains pending.

## A big marked-up drawing set — 2026-10-19

The user's 162-sheet, 24 MB steel set (80 A1 and 82 A3 sheets, 1,144 markups,
the same review stamp on every sheet) was "very slow to zoom and scroll".
Measured headless (offscreen raster; the graphics-card path under Xvfb with
software OpenGL, so its wall-clock times are not a real card's) on a shared
4-core machine under heavy load from other jobs. The robust figure is the
window thread's own CPU time per painted frame; wall-clock figures are
inflated by the load and only comparable within one run.

| | Before (`29d95b1`) | After |
| --- | ---: | ---: |
| Open (the call), raster / GL | 17.8 s / 15.2 s | 6.4 s / 6.5 s |
| Scroll at a person's pace: CPU per frame, median / p95 | 19.4 / 35.5 ms | 13.1 / 18.6 ms |
| Fast flick at fit width | 20.0 / 29.3 ms | 9.5 / 11.9 ms |
| Flick at fit page | 20.1 / 31.1 ms, 4 of 52 page paints blank | 8.5 / 16.5 ms, none blank |
| Wheel zoom in, 10 % → 800 % | 21.5 / 28.4 ms | 4.4 / 12.7 ms |
| Wheel zoom out | 23.1 / 36.4 ms | 8.6 / 15.7 ms |
| Fast wheel spin in and out | 19.6 / 26.0 ms | 6.5 / 12.5 ms |
| Frames painted while zooming in (same gesture) | 21 | 95 |
| GL: scroll at pace / flick at fit page (CPU median) | 24.4 / 21.7 ms | 13.4 / 11.3 ms |
| GL: zoom in / zoom out (CPU median) | 27.6 / 20.6 ms | 6.6 / 13.5 ms |

What it was, and what changed:

- **Every markup asked its size every frame.** With no item index, Qt went
  down every page's markups on each frame of a scroll or zoom, page on screen
  or not — a call into Python per markup (about 20 ms a frame here). A page
  whose markups all lie inside it now says so (`ItemContainsChildrenInShape`,
  set only when it changes and dropped the moment a markup moves), and Qt
  passes it by. Inside the page's *shape*, so clicks and snaps find exactly
  what they found before. (Toggling the flag around each paint was tried
  first: Qt then revisits every child after each paint, a repaint loop.)
- **The bottom rung of the ladder.** A 256-pixel preview of every page is
  drawn in the background once the document is laid out, behind anything on
  screen, nearest page first (a second, first-in-first-out queue in the render
  coordinator); asked for on screen it jumps the queue. A page scrolled,
  dragged or zoomed into view before anything sharper exists shows its
  preview, scaled, never a blank sheet. Above it the existing rungs are
  unchanged: the 1,100-pixel sheet, other zooms' squares standing in, and the
  squares at exactly the zoom on screen — so a settled page is pixel for pixel
  what it was.
- **Ahead of the scroll.** Squares are asked for from the whole window (a
  scroll's repaint is the uncovered strip, and the margin measured from it was
  a few pixels, which also gave up what the last full repaint had asked for),
  further ahead in the direction of travel; squares of pages left more than a
  screen behind are given up.
- **Stalls.** Each wheel notch of a zoom worked out stand-ins for every markup
  it would land on (40 ms a notch; now it only asks for the squares). Every
  page scrolled onto set the canvas's scroll-bar policy, which lays the view
  out again (80 ms). The spreadsheet headings looked through every markup of
  every page on each scroll step, and each whole-page picture arriving asked
  all 162 pages whether they had one.
- **Opening.** The same stamp on every sheet is a copy each, with its own
  object numbers: its picture was drawn, PNG-encoded and decoded 162 times.
  Annotations whose appearances fingerprint the same (`engine.
  appearance_fingerprint`: the appearance stream and everything it reaches, by
  content) now share one picture: 162 → 45 renders here, 17.8 s → 6.4 s.

`tests/test_big_pdf_smooth.py` builds a synthetic set with the same traits
(36 A1 sheets, 4,000 strokes and a picture each, 32 markups a sheet, the same
stamp on every one) and drives the real wheel and scroll bar: the window's work
per frame must stay under 16 ms median and 40 ms p95, no page on screen may
show unpainted paper in any frame, and the settled window must match a fresh
start pixel for pixel. Before these changes it fails the budget (25–27 ms
median) and shows blank pages while the scroll bar is dragged.
