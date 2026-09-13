# Editing performance — 2026-09-13

The application uses the multicore PDF renderer described in
[PDF_PERFORMANCE.md](PDF_PERFORMANCE.md). This follow-up profiles the UI work
that still runs on the main thread when editing an annotated drawing.

## Measured editing latency

Native macOS/Cocoa, one page with 500 rectangular markups, normal panels and
selection. Baseline: `a4dc33f`. Three rounds with 20 pointer moves per round,
followed by a nudge, undo and redo. Each sample processes pending Qt events.
Setup, profiling and state comparison are excluded from the timings.

| Operation | Before median | After median | Speedup |
| --- | ---: | ---: | ---: |
| Pointer move with snapping | 8.18 ms | 4.46 ms | 1.83× |
| Nudge selected markup | 85.80 ms | 62.25 ms | 1.38× |
| Undo | 6,989.77 ms | 197.76 ms | 35.34× |
| Redo | 6,855.04 ms | 195.71 ms | 35.03× |

These are operation timings on a repeatable fixture, not whole-application
speedups or a guarantee for every document. Raw samples and environment details
are in [editing_2026-09-13.json](benchmarks/editing_2026-09-13.json).

```bash
python3 tools/benchmark_editing.py --items 500 --rounds 3
# Optional profiling; do not compare profiled times with normal times:
python3 tools/benchmark_editing.py --items 500 --rounds 3 --profile /tmp/editing.prof
```

The benchmark isolates settings and verifies full serialized document equality
after every undo and redo. It dispatches real Qt pointer and keyboard events.

## Changes and correctness constraints

- Restoring a page publishes one `itemsChanged` notification after all markups
  are ready. Previously each removed markup rebuilt the lists, making undo
  quadratic in the markup count. The final panel refresh remains synchronous.
- Committing an edit serializes each affected page once for comparison and
  stores that same result in undo history. Full page history remains intact.
- Style serialization copies scalar values directly and still deep-copies
  mutable data such as imported dash lists. Saved values remain unchanged.
- The main-window event filter bypasses widget ownership checks for events it
  does not handle. Keyboard shortcuts, Escape and format-painter input still
  follow their existing routes, including dialog and multi-window boundaries.
- Snapping shares one nearby-item scan between endpoints, crossings and edges
  within an event. Order and tie-breaking are preserved. Nothing survives into
  the next event, so moves, rotation, visibility and undo cannot leave stale
  geometry. The scene's `NoIndex` safety choice is retained.
- Rectangle size refresh reuses the shared registry's millimetre unit object,
  avoiding repeated parsing while retaining quantities and displayed dimensions.

No rendering resolution, PDF content, tool, snapping target, history depth or
cache memory limit was reduced. The rendering process pool remains bounded;
additional CPU workers are not used for UI work that must stay on Qt's thread.

Final validation counts are recorded in [COMPLETED_TASKS.md](COMPLETED_TASKS.md).
