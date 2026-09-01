# CalcForge

A desktop engineering workbench for Windows, macOS and Linux. One document holds
your **calculations**, your **drawing markup** and your **spreadsheets** — laid out
page by page like a PDF, A4 by default, and printable exactly as you see it.

It is the three tools an engineer normally juggles, in one place:

| You would normally use… | CalcForge gives you |
|---|---|
| SMath Studio / Mathcad | Unit-aware, typeset calculations with named variables and functions |
| Bluebeam Revu | The full markup tool set, scaled measurement, takeoff and PDF page import |
| Excel | Spreadsheets that read the very same variables your calculations define |

Everything shares one workspace: a variable defined in a calculation can be used in a
cell, and a cell can be published back as a variable. Change one number, press **F9**,
and the whole document — text, tables and measurements — updates.

---

## Install and run

```bash
git clone <this repository>
cd <this repository>
python -m pip install -r requirements.txt
python main.py
```

Python 3.10 or newer. Everything else comes from `requirements.txt`
(PySide6, Pint, NumPy, SymPy) — no system libraries beyond a normal desktop.

Install it as a command instead, if you prefer:

```bash
python -m pip install .
calcforge                 # or: calcforge my-calculation.cfx
```

Start with **Help ▸ Load the worked example** (or `python main.py --sample`) for a
three-page steel-beam, load take-down and pad-footing calculation to poke at.

On a headless machine (CI, a container) run with `QT_QPA_PLATFORM=offscreen`.

---

## Calculations

Draw a calculation block with the **Calculation** tool (`M`) and type ordinary
engineering maths. It is typeset as you would write it by hand — real fractions,
radicals, subscripts and superscripts — and evaluated live.

```
# Simply supported beam
L := 7.2 m
w_dead := 8.5 kN/m
w_live := 6.0 kN/m
w := 1.2*w_dead + 1.5*w_live      # ULS combination

M_max := w*L^2/8 -> kN*m
Z_x := 896 cm^3
sigma_b := M_max/Z_x -> MPa
f_y := 355 MPa
sigma_b <= f_y                    # capacity check
```

### How to write it

| You type | What happens |
|---|---|
| `b := 300 mm` | Defines `b`. `b = 300 mm` works too. |
| `b*d^2/6` | Implicit multiplication and `^` powers; shown as a real fraction. |
| `5 kN`, `24 kN/m^3` | A number and a unit — no `*` needed. |
| `M_max` | `_` makes a subscript; `sigma`, `delta`, `gamma`… become Greek letters. |
| `expr -> MPa` | Show this result in a particular unit. |
| `f(x) := w*x*(L-x)/2` | Defines a function; call it with `f(2 m)`. |
| `sigma <= f_y` | A check — the result reads `true` or `false`. |
| `# note` | A comment, at the start of a line or after an expression. |

Units that cancel collapse to a plain number, the way an engineer reads them:
`6 m / 200 mm` is **30**, and a utilisation ratio built from `kN·m/(mm³·MPa)` is
**0.1018** — while `30 deg` stays an angle.

Units are enforced, not decorative: `1 m + 1 kg` is refused with
*"Units do not match: cannot combine meter with kilogram"*, and every result carries
the unit it earned. SI, imperial and the usual structural units (`kN`, `MPa`, `kip`,
`ksi`, `psf`, `pcf`, `klf`…) are all built in.

### What is available

Arithmetic, `sqrt`, `root`, `exp`, `ln`, `log`; trigonometry that accepts degrees or
radians; `sum`, `mean`, `median`, `stdev`, `max`, `min`; `if`, `and`, `or`, `not`;
matrices (`matrix`, `det`, `inv`, `lsolve`, `norm`, `el`); `interp` and `lookup` for
design tables; numerical `diff`, `integral`, `root_of`, `maximise`, `minimise`; unit
helpers `to`, `mag`, `unit_of`; and a SymPy bridge (`sym`, `symsolve`, `symdiff`,
`symint`, `simplify`, `factor`) when you want the algebra rather than the number.
The **Functions** panel lists them all with one-line help — double-click to insert.

The **Variables** panel shows every value the document has defined, what it evaluated
to, and which block it came from.

---

## Markup

The complete annotation set, with a properties panel for colour, fill, thickness,
dash pattern, opacity, arrowheads, font, layer, author and comment:

- **Draw** — pen, highlighter, line, arrow, polyline, rectangle, ellipse, polygon,
  revision cloud (box or free-form), area highlight, redaction
- **Annotate** — text box, callout with a draggable leader, sticky note, status stamps
  (*APPROVED*, *FOR CONSTRUCTION*, *AS BUILT*…), images
- **Measure** — length, polyline length, area, perimeter, volume, angle, radius,
  diameter, and a count tool with numbered markers

Selected markups get eight resize handles and a rotation handle; polylines, polygons
and callout leaders get one handle per vertex, and a double-click inserts another.
Shift constrains to 15° or to a square, arrow keys nudge, and everything is
undoable.

The **Markups** panel is a live list of every annotation in the document — page, type,
subject, measured value, author, date and comment — filterable, and exportable to CSV
as a takeoff. Measurements and counts sharing a subject are totalled at the bottom.

### Scale and measurement

Set the page scale from the status bar, or draw a known distance with the
**Calibrate** tool and type what it represents ("5 m"). Every measurement on that page
then reads true site dimensions in the units you choose, at the precision you choose.
Scale is per page, so an imported 1:50 detail and a 1:200 layout can live in the same
document.

### PDF pages

**File ▸ Insert PDF pages** brings drawings in as page backgrounds — all pages or a
range like `1-3,7`, at the resolution you pick, keeping each page's own size or
fitting to A4. Mark them up, measure them, and calculate against them.

---

## Tables

Draw a table with the **Table** tool (`B`). It behaves like a spreadsheet: click a
cell and type, `Tab` and the arrow keys navigate, `Ctrl+D` / `Ctrl+R` fill down and
right (with relative and `$absolute$` references translated properly), and the formula
bar shows the raw entry and the evaluated result.

```
A            B          C             D
Item         Thickness  Density       Load
Slab         150 mm     24 kN/m^3     =B2*C2
Screed       60 mm      22 kN/m^3     =B3*C3
Total                                 =SUM(D2:D4)
```

- Cells accept numbers, text, booleans **and quantities** — `150 mm` is a length, not
  a string, so `=B2*C2` comes out as a pressure.
- Excel-style functions: `SUM`, `AVERAGE`, `COUNT`, `COUNTA`, `IF`, `IFERROR`,
  `AND`, `OR`, `MIN`, `MAX`, `ROUND`, `SUMIF`, `COUNTIF`, `SUMPRODUCT`, `VLOOKUP`,
  `INDEX`, `MATCH`, `CONCAT`, `TEXT`… case-insensitive, with `=` for equality,
  `<>` for not-equal and `&` for joining text. `IF` and `IFERROR` are lazy, so
  `=IF(B2=0,0,A2/B2)` is safe.
- **Any variable from a calculation works in a formula** — `=D2*gamma_c` just works.
- Give a column a display unit and every value in it is converted for display.
- Publish results back: name a cell (right-click ▸ **Named cells…**) or switch on
  *Publish columns as variables*, and the rest of the document can use it.

Recalculation is dependency-ordered with circular-reference detection, and runs in two
passes so a block can reference something defined further down the document.

---

## The document

- Pages are real pages: **A4 portrait by default**, plus A0–A5, Letter, Legal,
  Tabloid, ANSI and ARCH sizes, portrait or landscape, with adjustable margins —
  per page or applied to all.
- Thumbnail panel for adding, duplicating, deleting and reordering pages.
- Optional grid with snapping, margin guides, and header/footer templates with
  fields: `{title} {project} {author} {page} {pages} {date} {time} {file}`.
- **Print** and **print preview** through the normal system dialog, **Export to PDF**
  (vector, any page size), export pages as images, and export the markups list or the
  variable list to CSV.
- Save to `.cfx` — a zip holding the document as JSON plus its images and imported
  PDF pages, so a file is self-contained and diff-friendly.

---

## Keyboard

| Key | Action |
|---|---|
| `Esc` | Back to Select · finish or cancel what you are doing |
| `P` `K` | Pen · highlighter |
| `L` `A` | Line · arrow |
| `R` `E` `C` | Rectangle · ellipse · revision cloud |
| `T` `N` `S` | Text box · note · stamp |
| `M` `B` | Calculation · table |
| `H`, `Space`+drag | Pan |
| `Ctrl`+wheel | Zoom · `Ctrl+0` fit page · `Ctrl+1` fit width |
| `Shift`+drag | Constrain to 15° or square |
| Double-click | Edit text, calculation or table · add a polyline vertex |
| `F9` | Recalculate everything |
| `Ctrl+Z` / `Ctrl+Y` | Undo · redo |
| In a table | `Enter`/`F2` edit · `Tab`/arrows move · `Ctrl+D`/`Ctrl+R` fill |

Full list under **Help ▸ Keyboard shortcuts** (`F1`).

---

## Layout of the code

```
calcforge/
  core/        units, evaluation engine, function library, 2D maths typesetting,
               spreadsheet engine, document and page model
  items/       everything that can sit on a page: shapes, text, stamps, images,
               measurements, calculation blocks, tables
  ui/          the scene and canvas, tools, dock panels, dialogs, main window
  io/          project files, PDF import, printing and export
  sample.py    the worked example
tests/         100 tests: engine, spreadsheet, items and end-to-end GUI
```

Two pieces are worth knowing about if you go digging:

**`core/mathrender.py`** lays maths out as a tree of boxes — fractions, radicals,
scripts, scaled brackets, matrices — and paints them with `QPainter`. That is what
makes a calculation look handwritten rather than like source code.

**`core/typography.py`** sizes every page font in pixels rather than points. Page
coordinates are PostScript points, so a font sized in points would come out four
times too large on a 300 dpi printer; pixel sizing pins text to scene units and lets
the painter's transform scale it like any other geometry.

### Tests

```bash
python -m pytest
```

Runs headless (the suite forces `QT_QPA_PLATFORM=offscreen`) and drives the real
window: every drawing tool, selection, resize, undo, table editing, recalculation
order, save/reload, and PDF export.
