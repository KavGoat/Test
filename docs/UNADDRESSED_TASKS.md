# Tasks requiring follow-up

Previous entries were deleted at the user's request on 2026-09-27. New
follow-up items for the 2026-09-27 report are recorded below as they arise.

| Report | Status | What is needed |
| --- | --- | --- |
| Red cross over elements of a Revit-exported PDF | Not reproduced. No code path draws a red cross over page content. MuPDF renders the page tiles, and imported annotations never draw a cross. | One of the affected PDFs, or a screenshot showing which tool/view displays the cross (page view, thumbnail, snapshot or export). |
| Speed on the user's own drawings | Caches and worker counts now scale with the machine, and zoomed-out tiles are sharper. | The user's slow PDFs and the actions that lag, so they can be profiled with `tools/benchmark_editing.py` and `docs/PDF_PERFORMANCE.md`'s benchmarks. |
| Windows check of the new size bar, search field and spin-box arrows | Verified offscreen on Linux with screenshots. | A look on the user's Windows machine. |
| Exported markups opened in Bluebeam | Checked in MuPDF, pdfium and with appearances rebuilt from the dictionary; Bluebeam's own keys written as its files write them. | A look in Bluebeam at an exported sheet with a Section, a cloud, a callout, a hatched area and an arc. |
| Bluebeam line styles and hatch patterns on export | Written by name and scale; the pattern's own tile is not embedded, so Bluebeam draws the hatch only if it has a pattern of that name. | Confirm whether Bluebeam shows it; if not, embed the tile as a PDF pattern. |
| Dashes in documents saved before 2026-09-30 | Dashes read from a PDF or tool set were kept in line widths for a day (2026-09-29); they are points now. A line brought in on that day with its own dashes and a width other than 1 pt shows dashes that many times shorter. | Re-import those tool sets or PDFs if any were used. |
