# Tasks requiring follow-up

Previous entries were deleted at the user's request on 2026-09-27. New
follow-up items for the 2026-09-27 report are recorded below as they arise.

| Report | Status | What is needed |
| --- | --- | --- |
| Red cross over elements of a Revit-exported PDF | Not reproduced. No code path draws a red cross over page content. MuPDF renders the page tiles, and imported annotations never draw a cross. | One of the affected PDFs, or a screenshot showing which tool/view displays the cross (page view, thumbnail, snapshot or export). |
| Speed on the user's own drawings | Caches and worker counts now scale with the machine, and zoomed-out tiles are sharper. | The user's slow PDFs and the actions that lag, so they can be profiled with `tools/benchmark_editing.py` and `docs/PDF_PERFORMANCE.md`'s benchmarks. |
| Windows check of the new size bar, search field and spin-box arrows | Verified offscreen on Linux with screenshots. | A look on the user's Windows machine. |
