# MarkForge compared with Bluebeam Revu — 2026-09-27

Made from a pass through MarkForge's tools, menus and panels, set against
Bluebeam Revu's standard feature set. Features the user has already withdrawn are left
out: layers, markup status and replies, and calculations. Every item waits for the user
to say **add** or **ignore**. Nothing here has been built.

## A. Tool set import accuracy (done this round)

Sketch Tools now match Bluebeam's own drawing in `btx/Document1.pdf` to
within about half a point per part; see `COMPLETED_TASKS.md`. Still
different:

| # | Difference | Effect |
| --- | --- | --- |
| A1 | Fractional font sizes are rounded to whole points (10.87 → 11) | Text in scaled tool sets is ~1 % wider than Bluebeam's |
| A2 | Title block stamp artwork is a high-resolution picture, not linework | Soft at very high zoom; cannot be recoloured |

## B. Markup and measurement tools Bluebeam has that MarkForge lacks

| # | Bluebeam feature | What it does |
| --- | --- | --- |
| B1 | Dynamic Fill | Click inside a closed region of PDF linework to fill or measure it without tracing |
| B2 | Arc measurement | Measures the length along an arc |
| B3 | Viewports | Different scales in different regions of one sheet (details at 1:20 beside a plan at 1:100) |
| B4 | Legends | An automatic key of the markups used on a page, with counts and totals |
| B5 | Spaces | Named regions; markups inside report which space they are in |
| B6 | Hyperlink / Link tool | A region that jumps to a page, a view, a file or a web address |
| B7 | Custom stamp editor | Build stamps with dynamic fields such as date, user and time |
| B8 | Hatch and line-style libraries | Bluebeam ships many named patterns (brick, earth, insulation, …); MarkForge has 9 hatches |

## C. Document and page features

| # | Bluebeam feature | What it does |
| --- | --- | --- |
| C1 | Compare Documents / Overlay Pages | Highlights what changed between two revisions of a sheet |
| C2 | Search panel for PDF text | Finds words in the drawing itself, across pages, and lists every hit |
| C3 | OCR | Makes scanned drawings searchable |
| C4 | Crop pages | Trims a page's visible area |
| C5 | Extract / split pages | Save selected pages as a new PDF |
| C6 | Batch slip sheet | Replace sheets in a set with new revisions, carrying markups across |
| C7 | Markup summary report | PDF or CSV report of all markups and measurements, grouped |
| C8 | Print tiling | Print a large sheet across several A4/A3 pages |

## D. Usability and workspace

| # | Bluebeam feature | What it does |
| --- | --- | --- |
| D1 | Recent Tools | Tool chest section with the last tools and styles used |
| D2 | Zoom (marquee) tool and Magnifier | Drag a box to zoom to it; a loupe panel |
| D3 | Profiles | Save and switch whole workspace layouts (panels, toolbars) |
| D4 | Tool chest Properties / Drawing mode | A tool either keeps its stored look or takes the current toolbar look |
| D5 | Typewriter tool on the toolbar | Borderless text tool (W) as its own button; MarkForge only creates one by typing on the canvas |

## User decisions — 2026-09-28

Add: A1, A2, B3, B6, B8, C2 (with markup search and replace), C4, C5, and a
Bluebeam-style Markups list (in place of C7).
Ignore: B1, B2, B4, B5, B7, C1, C3, C6, C7 (report), C8, D1–D5.
