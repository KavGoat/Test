# The best Qt PDF editor to learn from, and what to take from it

Stirling-PDF was ruled out: it is a Java and React web application, and the
parts that matter are under a paid licence (see `docs/STIRLING_BASIS.md` on
the `claude/stirling-based-markup-editor` branch). This is the Qt desktop
research that replaced it.

## The candidates

| | **PDF4QT** | **Okular** | qpdfview |
|---|---|---|---|
| Repository | `JakubMelka/PDF4QT` | `KDE/okular` | `adamreichold/qpdfview` |
| Licence | **MIT** | GPL-2.0-or-later | GPL-2.0 |
| What it is | PDF **editor**, with its own PDF engine | Document **viewer** with annotation | Tabbed viewer |
| Toolkit | Qt 6, C++ | Qt 6, C++ (KDE Frameworks) | Qt, C++ |
| PDF engine | Its own, written to PDF 2.0 | Poppler | Poppler |
| Annotation model | Every PDF 2.0 annotation type, 5,343 lines | The common types, via Poppler | Basic |

**PDF4QT is the one.** MIT means its ideas — and its code, with attribution —
are safe to use. It is an editor rather than a viewer. And its annotation
model is written straight from the specification, which is exactly the part
this application has been guessing at.

Okular is worth knowing for its annotation *tool* UX — the annotating
toolbar, the per-tool remembered properties — but its licence is copyleft and
its annotation model is thinner: no callout line, no measurement dictionary,
no dimension intents.

## What PDF4QT knows that this application did not

`Pdf4QtLibCore/sources/pdfannotation.h`. Everything below is a PDF structure
this application currently throws away, exporting the markup as a `/Stamp`
with a picture of itself instead. A stamp can be moved in Bluebeam. It cannot
be *edited* as what it is — a cloud does not stay a cloud, a dimension does
not keep its measurement, a call-out loses its leader.

| Markup | What it exports as now | What the PDF actually has |
|---|---|---|
| **Revision cloud** | `/Stamp` | `/Square` or `/Polygon` with `/BE << /S /C /I n >>` — a *cloudy border effect*, with an intensity. `PDFAnnotationBorderEffect` |
| **Call-out** | `/Stamp` | `/FreeText` with `/IT /FreeTextCallout` and `/CL` — a callout line of **two or three points**, the three-point form being exactly the hinged leader. `PDFAnnotationCalloutLine::StartKneeEnd` |
| **Typewriter** | `/Stamp` | `/FreeText` with `/IT /FreeTextTypeWriter` |
| **Dimension** | `/Stamp` | `/Line` with `/IT /LineDimension`, `/LL` leader length, `/LLE` extension, `/LLO` offset, `/Cap` and `/CP` for the value on the line, `/CO` for a moved value, and `/Measure` for the scale. `PDFLineAnnotation` |
| **Arrow** | `/Stamp` | `/Line` with `/L` and `/LE` — ten line endings, not one |
| **Polyline / area take-off** | `/PolyLine`, `/Polygon` with no intent | the same, with `/IT /PolyLineDimension` or `/PolygonDimension` and a `/Measure` |
| **Page scale** | nothing — it lives only in our own record | `/Measure` — PDF's own scale dictionary, which is how a measurement reads correctly in somebody else's reader |

`PDFLineAnnotation`'s leader lines are, line for line, the dimension built by
hand in `items/measure.py`: `/LL` is the witness reach, `/LLE` the overshoot,
`/LLO` the gap that keeps the witness line off the point it measures, and
`/CO` is where the value went when it was dragged off with Shift. The
specification had a name for every one of them.

## What this changes

Exporting a markup as its real annotation type instead of a stamp is the
difference between a marked-up PDF and a picture of one. The work is in
`io/annotate.py` (writing) and `io/pdfmarkups.py` (reading), and it is
symmetrical: what can be written natively can be read back natively, so a
round trip through Bluebeam keeps a cloud a cloud.

Two things stay as they are. The appearance stream is still written for every
annotation, because that is what guarantees it *looks* right everywhere. And
anything with no PDF equivalent — a count marker, a snapshot — still travels
as a stamp, which is honest: a PDF has no idea what those are.

## What came of it

Written 2026-09-06 as research; this is what was built from it, as of
2026-09-07.

- **The annotation model was taken and used.** Every row of the table above is
  now what `io/annotate.py` writes and `io/pdfmarkups.py` reads — the cloudy
  border, the three-point callout line, the dimension's leader lines and its
  `/Measure`, the ten line endings. Evidence is listed under "What a saved file
  is" in `docs/COMPLETED_TASKS.md`.
- **The engine was taken as a model, not as code.** PDF4QT's shape — an object
  storage that resolves references, a lexer under it, filters under that — is
  the shape of `markforge/pdf/`, which is written in Python from the
  specification. Nothing was copied; the attribution owed is for the idea of
  how to lay it out, and this document is it.
- **The incremental update is the part that mattered most**, and it did not
  come from the table above. A markup editor's save has to leave the drawing
  that came in exactly as it was, which is an operation no library this project
  had would do. `markforge/pdf/writer.incremental_update` and
  `io/pdfsave.py` are the answer.
- **Two rows of the table are moot now.** Typewriter was withdrawn as a tool,
  and the page scale reaches other readers through `/Measure` as the table said
  it should.
