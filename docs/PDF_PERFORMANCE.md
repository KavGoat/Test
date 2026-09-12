# PDF rendering performance

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
  application/OS. `MARKFORGE_PDF_WORKERS=1` through `8` overrides it, capped at
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
