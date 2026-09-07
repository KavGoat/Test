# Building the markup editor on Stirling-PDF

> **Kept for the record.** This was written on a branch that has since been
> deleted, and it argues a route the project did not take. Route 2 below is
> the one that was chosen: the PySide6 desktop application stayed, and the
> PDF engine was written in Python instead (`markforge/pdf/`). The list in
> §4 is still worth reading — it is the clearest inventory of what a
> document-operations layer would have to cover.

Read before starting: what Stirling-PDF is, what it already does, what it does
not do, and what its licence permits. Written from the repository at
`Stirling-Tools/stirling-pdf` (shallow clone of `main`).

## 1. What Stirling-PDF actually is

Not a desktop annotation tool. It is a **server plus a browser front end**:

| Part | Technology | Size |
|---|---|---|
| Backend | Java 21 / Spring Boot, PDFBox | 2,279 `.java` files |
| Front end | React + TypeScript, Mantine/MUI, built on **EmbedPDF** | 3,252 `.ts`/`.tsx` files |
| Engine | Python service, separate container | 150 files |

It runs as a Docker image serving `http://localhost:8080`, or as a licensed
desktop wrapper around the same web front end.

This matters because the existing markup work in this repository is a
**PySide6 desktop application** in Python. The two share no code, no widget
toolkit and no rendering path. Building on Stirling means the markup engine is
written again in TypeScript against EmbedPDF's annotation plugin — the Python
is a specification, not a source.

## 2. Licence — read this before writing any code

The root `LICENSE` is MIT, with named directories carved out under the
**Stirling PDF User License**, which says plainly: *"Production use of the
Stirling PDF Software is only permitted with a valid Stirling PDF User
License."*

| Directory | Files | Licence |
|---|---|---|
| `frontend/editor/src/core/` | 2,314 | **MIT** — the viewer, annotation tools, page editor |
| `app/core/` (most of the Java) | — | **MIT** |
| `app/proprietary/` | 985 | Stirling PDF User License |
| `app/saas/` | 309 | Stirling PDF User License |
| `engine/` | 150 | Stirling PDF User License |
| `frontend/editor/src/proprietary/` | 378 | Stirling PDF User License |
| `frontend/editor/src/desktop/` | 147 | Stirling PDF User License |
| `frontend/editor/src/saas/` | 98 | Stirling PDF User License |
| `frontend/editor/src/cloud/` | 40 | Stirling PDF User License |

Two things follow:

- **The desktop client is proprietary.** Shipping this as a desktop
  application the way the current app is shipped needs a licence from
  Stirling PDF Inc.
- **`core` is MIT but not self-contained.** 25 files under
  `frontend/editor/src/core/` import from the proprietary trees. Those imports
  have to be stubbed or replaced before an MIT-only build will compile.

`frontend/package.json` also declares the whole front-end package proprietary,
which contradicts the root `LICENSE`'s carve-out list. That contradiction is
worth resolving with Stirling before depending on it.

## 3. What Stirling-PDF already has

Use these rather than rebuilding them.

**Annotation tools** (EmbedPDF, `frontend/editor/src/core/tools/Annotate.tsx`):
highlight, underline, strikeout, squiggly, ink, ink highlighter, free text,
note, text comment, insert/replace text, square, circle, line, arrow,
polyline, polygon, stamp, signature stamp, signature ink. Each with colour,
opacity, border width, and a comment that shows in a comments sidebar.

**Measurement**: `RulerOverlay.tsx`, `RulerMeasurementLayer.tsx`,
`ScaleCalibrationDialog.tsx`, `ScaleSettingsPanel.tsx` — a calibrated page
scale and distance measurement, about 2,100 lines.

**Redaction**: a real redaction plugin, not a black rectangle.

**Document operations** — 50+, server side: merge, split, rotate, crop, OCR,
compress, convert, watermark, page numbers, metadata, permissions, passwords,
flatten, repair, sanitise, compare, overlay, booklet imposition, extract
images/pages, remove blanks, scanner split, sign and validate signatures.
The current desktop app has almost none of these.

**Viewer**: tiling render at zoom, thumbnails, search, bookmarks, spreads,
pan/zoom, history, export, print, attachments.

## 4. What is missing, and where to take it from

Everything below exists in `claude/engineering-calc-markup-app-2twiqs` and has
no equivalent in Stirling-PDF. Ordered by how much of a Bluebeam replacement
depends on it.

| Missing | Where it is in the Python app |
|---|---|
| **Revision clouds** — rectangle, polygon, and a cloud call-out | `items/shapes.py` `cloud_path()`, `RectItem(kind="cloud")`, `PolyItem(kind="cloud")` |
| **Call-outs with hinged leaders**, several per box | `items/text.py` `_Leader`, `CalloutItem` |
| **Dimensions** — arrow-to-arrow, value along the line, control dot, witness lines, hinged leader for a moved value | `items/measure.py` |
| **Area, perimeter, volume, angle, radius, diameter** measurement, with cut-outs taken out of an area | `items/measure.py`, `items/base.py` cut-outs |
| **Count markers** with subjects and renumbering | `items/measure.py` `CountItem` |
| **Snapshots** — copy a region as vectors, stays sharp, recolourable | `items/snapshot.py` |
| **Bluebeam tool set import (`.btx`)** | `io/btx.py` — asked for explicitly |
| **Layers** — visibility, lock, print | `core/document.py` `Layer`, `ui/panels.py` |
| **Markups list** — author, subject, status, date, layer, comment; CSV out | `ui/panels.py` `MarkupsPanel`, `io/export.py` |
| **Snapping** to the PDF's own vector geometry | `io/pdfvector.py`, `ui/view.py` `snap_scene` |
| **Reading a PDF's annotations back as editable markups** | `io/pdfmarkups.py` |
| **Writing markups out as live PDF annotations** with appearance streams | `io/annotate.py` |
| **Hatch patterns** on fills | `items/base.py` `HATCH_PATTERNS` |
| **Per-type remembered defaults**, "set as default" | `ui/toolsets.py` |
| **Recolour** — swap a colour, colourise, make a colour transparent with a tolerance | `io/recolour.py` |
| **Flatten with recovery** | `ui/mainwindow.py` `_flatten_items` |
| **Typewriter, flags, stamp presets** | `items/text.py` |

## 5. The decision this needs

Three routes, and they do not converge:

1. **Fork Stirling-PDF** and add the markup layer to its React front end.
   Gets 50+ document operations and a mature viewer for free; needs the
   licence question answered, needs the proprietary imports stubbed, and means
   writing the whole markup engine again in TypeScript.
2. **Take the ideas, not the code.** Keep the PySide6 application, and use
   this list to add what Stirling has and the desktop app lacks — the document
   operations, redaction, OCR, search. No licence question, no rewrite.
3. **Both**: the desktop app stays, and a Stirling deployment sits behind it
   for the server-side operations it calls out to.

Nothing here picks one. That is the user's call.
