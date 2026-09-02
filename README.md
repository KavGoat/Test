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

Type `\` anywhere on the page — or pick the **Calculation** tool from the toolbar — and write
ordinary engineering maths. It is typeset as you would write it by hand — real
fractions, radicals, subscripts and superscripts — with the result immediately
after it. Each line is its own region, so you can drag any of them where you want.
Press **Enter** to open the next line below, **Shift+Enter** to keep several lines
in one region.

**Double-click** any region, cell or line to edit it. While you are editing, the
keyboard and the pointer belong to the text: arrows move the caret, dragging
selects, `Ctrl+C`/`V` work on the text, and clicking outside finishes the edit.

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
| `b = 300 mm` | Defines `b` the first time that name appears… |
| `b = 400 mm` | …and *checks* it afterwards, reading `false`, so nothing is silently overwritten. |
| `b := 400 mm` or `b : 400 mm` | Always defines, even over a name that already exists. |
| `b*d^2/6` | Implicit multiplication and `^` powers; shown as a real fraction. |
| `5 kN`, `24 kN/m^3` | A number and a unit — no `*` needed. |
| `M_max` | `_` makes a subscript; `sigma`, `delta`, `gamma`… become Greek letters. |
| `expr -> MPa` | Show this result in a particular unit. |
| `f(x) := w*x*(L-x)/2` | Defines a function; call it with `f(2 m)`. |
| `sigma <= f_y` | A check — the result reads `true` or `false`. |
| `# note` | A comment, at the start of a line or after an expression. |

Results come out in the unit you would have written yourself. `w·L²/8` reads
**124.4 kN·m**, a bearing pressure reads **149.8 kPa**, a deflection **7.26 mm** —
lengths swap from mm to m past a metre, forces from N to kN past a kilonewton.
A value you typed out in full keeps the unit you chose (`896 cm³` stays cm³), and
imperial input is never quietly turned into SI. An angle that fell out of `atan`
reads in degrees; one you wrote in radians stays in radians.

Units that cancel collapse to a plain number: `6 m / 200 mm` is **30**, and a
utilisation ratio built from `kN·m/(mm³·MPa)` is **0.1018**.

Units are enforced, not decorative: `1 m + 1 kg` is refused with
*"Units do not match: cannot combine meter with kilogram"*, and every result carries
the unit it earned. SI, imperial and the usual structural units (`kN`, `MPa`, `kip`,
`ksi`, `psf`, `pcf`, `klf`…) are all built in.

### Blocks can be self-contained

By default every calculation **defines for the whole document**, which is how a
calculation sheet reads: something worked out at the top is available further down.

Right-click a block of several lines and tick **Self-contained block** to keep its
own names inside it — a dozen intermediate values in one check then cannot collide
with the rest of the document. A self-contained block can still read anything
defined **above** it, so it is the natural place for a side calculation that
consumes a couple of document-wide inputs. It is marked with a rule down its left
edge, and its values are listed in the Variables panel as local to it.

A single-line region always defines for the whole document.

### Order is position

The whole document evaluates in one pass, top-left to bottom-right, exactly as
SMath does. A value has to be defined above — or to the left of — whatever uses
it, so dragging a line somewhere else really does change what resolves. When
something stops resolving the **Problems** panel says so, with the page, the line
or cell, and what went wrong: an undefined name, a unit mismatch, a bad formula.
The status bar carries the count.

**Split into separate lines** and **Merge into one block** (under *Calculate*)
convert between one region per line and a single block.

### Checking every number

*Calculate ▸ Check every number* (`F10`) re-derives the whole document from its
source text in a workspace of its own and compares every answer with what is on
the page. It shares nothing with the live calculation, so a stale value, a cached
result or a definition that has quietly gone missing shows up as a disagreement
rather than as a number nobody questions. It also reports a name defined twice, a
name that spells out a unit, a result that cannot be shown in its own target unit,
and a magnitude far outside anything a building is made of.

It runs by itself a moment after you stop typing, so a sheet is never left
unchecked without you being told. What it finds appears in the **Problems** panel
alongside anything that failed to evaluate.

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

## Plots

Draw a plot with the **Plot** tool (`G`) and give it a curve per line — a function
you defined (`M`), or any expression in the plot variable. The range can be
written in units (`0 m` to `L`), the axes label themselves from the units that
come back, and a curve whose units do not match the y axis says so rather than
being silently dropped.

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

A scale is **optional**. A page starts without one, and everything still works —
measurements simply read paper distances, and the first one you draw says so.

Give a page a scale whenever you want real dimensions: click the scale button in the
status bar, or draw a known distance with the **Calibrate** tool and type what it
represents ("5 m"). Scale is per page, so an imported 1:50 detail and a 1:200 layout
can live in the same document.

Only the three tools that measure something obey the scale:

| Tool | Key | Reads |
|---|---|---|
| Length | `M` | The true distance between the two ends |
| Area | `Shift+Alt+A` | The true area of the polygon you click out |
| Rectangle | `R` | Its true width × height — and it will take an exact size |

**A rectangle always says how big it is** — real dimensions on a scaled page, paper
millimetres without one — and that size is in the Value column of the markups list.
Draw one on a scaled page and it offers an exact size, so you can type `3 m` × `1.5 m`
and have it set out precisely; leave the boxes as they are to keep what you dragged.
On an unscaled page it does not interrupt you, because a rectangle there is usually
markup: ask for an exact size from the right-click menu instead. That menu also
switches the size label off for a rectangle that does not need one.

Everything else — polygon, pen, cloud, arrow, text — is a drawing, not a measurement,
and is never scaled.

The **Dimension** tool (`Alt+M`) is the exception that measures but lets you overrule
the number: it asks for the text to display, so a run of studs can read `3600 c/c`
while the takeoff total still uses what was actually measured.

### Moving and duplicating by an exact offset

`Ctrl+Shift+D` (also on the right-click menu) moves or copies whatever is selected by a
distance you type, any number of times — "across 3 m, 4 times" lays out a row of
footings. On a scaled page the offset is a real distance (`3 m`); without a scale it is
a paper one (`25 mm`).

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
- Copy, cut and paste ranges with `Ctrl+C` / `Ctrl+X` / `Ctrl+V`. Relative references
  follow the paste, absolute ones do not, and the clipboard is tab-separated so it
  round-trips with Excel.
- Excel-style functions: `SUM`, `AVERAGE`, `COUNT`, `COUNTA`, `IF`, `IFERROR`,
  `AND`, `OR`, `MIN`, `MAX`, `ROUND`, `SUMIF`, `COUNTIF`, `SUMPRODUCT`, `VLOOKUP`,
  `INDEX`, `MATCH`, `CONCAT`, `TEXT`… case-insensitive, with `=` for equality,
  `<>` for not-equal and `&` for joining text. `IF` and `IFERROR` are lazy, so
  `=IF(B2=0,0,A2/B2)` is safe.
- **Any variable from a calculation works in a formula** — `=D2*gamma_c` just works.
- Give a column a display unit and every value in it is converted for display.

### Getting a sheet out of Excel

Copy cells in Excel and paste them straight onto the page: they arrive as a table
sized to what you copied, with a header row picked up from words sitting over
numbers. Quantities stay quantities (`150 mm` is a length), Excel's quoting is
honoured so a cell holding a line break survives, and a thousands-separated number
like `1,234.5` stays a number instead of becoming text. Pasting into a table that
is already open drops the cells in at the cursor instead.

### Publishing a cell as a variable

Click a cell and type a name into the **name box** in the formula bar — the box
between the cell reference and `ƒx`. From then on every calculation in the document
can use that name, and the cell is **tagged with it on the sheet** and marked with a
folded corner, so a table never hides what it defines. The Variables panel says
which cell each published value came from (`Table · B2`). Clear the box to stop
publishing it.

Names are checked the same way everywhere, so a cell cannot be called after a unit,
a built-in function or a reserved word. *Publish columns as variables* does the same
thing for whole columns, using the header as the name.

Recalculation is dependency-ordered with circular-reference detection, and runs in two
passes so a block can reference something defined further down the document.

---

## The document

- **One continuous canvas.** Every page is stacked down it with a gap of desk
  between them, and you scroll through the whole document the way you would
  scroll a PDF. The wheel scrolls, `Shift`+wheel scrolls sideways,
  `Ctrl`+wheel zooms at the pointer, `Space`+drag and the middle button pan.
  `PgUp`/`PgDn` move a screenful, `Ctrl`+them move a page, and `Ctrl+Home` /
  `Ctrl+End` reach the ends. Scrolling onto another page makes it the current
  one; the view is never moved under you to tidy up.
- Drawing lands on the page under the pointer, and a markup dragged onto the
  next page belongs to that page afterwards — undo covers both.
- Pages are real pages: **A4 portrait by default**, plus A0–A5, Letter, Legal,
  Tabloid, ANSI and ARCH sizes, portrait or landscape, with adjustable margins —
  per page or applied to all.
- Thumbnail panel for adding, duplicating, deleting and reordering pages.
- Optional grid with snapping, margin guides, and header/footer templates with
  fields: `{title} {project} {author} {page} {pages} {date} {time} {file}`.
- **Print** and **print preview** through the normal system dialog, **Export to PDF**
  (vector, any page size), export pages as images, and export the markups list or the
  variable list to CSV.
- **Layers** with per-layer show, lock and print — hidden layers cannot be clicked,
  locked ones cannot be moved, non-printing ones stay out of the output.
- **Redaction that redacts**: draw the boxes, then *Markup ▸ Apply redactions* to
  overwrite the page pixels underneath and delete the markups they cover. It says
  plainly that this cannot be undone, and that partly-overlapping markups are left
  for you to check.
- **A light and a dark theme** (View ▸ Dark). The chrome, the icons and every
  panel follow it; the page itself stays paper-white in both, and the words on
  it keep their own colour — the sheet is the sheet, whatever the frame does.
- **The window is yours.** Every panel has a pin, a float button and a close
  button in its title bar: pin one and it stays put however clumsy the next
  drag is. Toolbars dock on any edge and can be locked, and
  *View ▸ Toolbars ▸ Choose tools* picks which markup tools appear on them —
  anything taken off is still on its menu and still on its key. Where
  everything sits, what is pinned, what is hidden and the window's own size
  come back next time; *Reset the layout* puts the original arrangement back.
- Autosave every two minutes beside the document, offered back on the next start.
- Save to `.cfx` — a zip holding the document as JSON plus its images and imported
  PDF pages, so a file is self-contained and diff-friendly.

---

## Keyboard

Typing straight onto the page does **nothing unless the key is bound** — which is
what lets a bare keystroke mean "start writing here":

| Key | Starts |
|---|---|
| `"` | A text region where the cursor is |
| `\` | A calculation |
| `\|` | A table |
| `@` | A callout |

Everything is editable under **Help ▸ Keyboard shortcuts**: click a shortcut and
**press the keys you want**. A single character is stored as that character;
anything with Ctrl or Alt is stored as a key sequence and works from the menus
too. Backspace clears one, Escape puts it back, and a key bound to two things
outlines both rows in red and will not save until you resolve it.

**Tool keys are silent while you are typing.** `M` in the middle of a sentence
is a letter, and so is `Alt+M` — they only pick a tool when nothing is being
edited. Save, print and zoom stay live throughout, as they do everywhere else.

| Key | Action |
|---|---|
| `Esc` | Back to Select · finish or cancel what you are doing |
| `L` `A` | Line · arrow |
| `R` `E` `C` | Rectangle · ellipse · revision cloud |
| `P` `Alt+P` `K` | Polygon · pen · highlighter |
| `T` `Q` `N` `S` | Text box · callout · note · stamp |
| `B` `G` | Table · plot |
| `M` `Shift+Alt+A` | Measure length · measure area |
| `Alt+M` | Dimension — asks for the text to show |
| `H`, `Space`+drag, middle-drag | Pan |
| Wheel · `Shift`+wheel | Scroll · scroll sideways |
| `PgUp` / `PgDn` | A screenful · `Ctrl`+them for a whole page |
| `Ctrl+Home` / `Ctrl+End` | The start and the end of the document |
| `Ctrl`+wheel | Zoom at the pointer |
| `Ctrl+0` `Ctrl+1` `Ctrl+2` `Ctrl+Alt+0` | Fit page · fit width · fit selection · 100% |
| `Shift`+drag | Constrain to 15° or square |
| Double-click | Edit text, calculation or table · add a polyline vertex |
| `Enter` | In a one-line calculation: open the next line below |
| `Shift+Enter` | Keep typing on a new line of the same region |
| `F9` | Recalculate everything |
| `F10` | Check every number — re-derive the document and compare |
| `Ctrl+Shift+D` | Move or duplicate the selection by an exact offset |
| `Ctrl+Z` / `Ctrl+Y` | Undo · redo |
| In a table | `Enter`/`F2` edit · `Tab`/arrows move · `Ctrl+D`/`Ctrl+R` fill |

Full list under **Help ▸ Keyboard shortcuts** (`F1`).

---

## Layout of the code

```
calcforge/
  core/        units, evaluation engine, function library, 2D maths typesetting,
               spreadsheet engine, document and page model, problem collection
  items/       everything that can sit on a page: shapes, text, stamps, images,
               measurements, calculations, tables, plots
  ui/          the scene and canvas, tools, key bindings, dock panels, dialogs,
               main window
  io/          project files, PDF import, printing and export
  sample.py    the worked example
tests/         168 tests: engine, spreadsheet, items and end-to-end GUI
```

Two pieces are worth knowing about if you go digging:

**`core/mathrender.py`** lays maths out as a tree of boxes — fractions, radicals,
scripts, scaled brackets, matrices — and paints them with `QPainter`. That is what
makes a calculation look handwritten rather than like source code.

**`core/typography.py`** sizes every page font in pixels rather than points. Page
coordinates are PostScript points, so a font sized in points would come out four
times too large on a 300 dpi printer; pixel sizing pins text to scene units and lets
the painter's transform scale it like any other geometry.

**`core/units.py`** holds the ladders that decide a result reads best in kN rather
than 780 000 N, and the rules that keep an angle, an imperial input or a value you
typed out in full exactly as it was written.

### Tests

```bash
python -m pytest
```

Runs headless (the suite forces `QT_QPA_PLATFORM=offscreen`) and drives the real
window: every drawing tool, selection, resize, undo, table editing, recalculation
order, save/reload, and PDF export.

| File | What it promises |
|---|---|
| `test_engine.py` | Parsing, units, `=` / `:=`, functions, matrices, symbolics |
| `test_spreadsheet.py` | Cells, formulas, ranges, dependency order, clipboard |
| `test_items.py` | Serialisation, geometry, layout of every markup type |
| `test_app.py` | The window: tools, panels, undo, files, printing |
| `test_usability.py` | Real pointer and keyboard sequences through the viewport |
| `test_validation.py` | Worked examples against published answers |
| `test_units_property.py` | What must hold for every value, plus randomised runs |
| `test_verify.py` | The independent check, mostly by breaking things on purpose |
| `test_output.py` | Exported PDFs, read back and measured |

Beyond the suite there is a fuzzer:

```bash
python tools/session_fuzz.py 42 400        # seed, rounds
```

It drives the real window at random — tools, drags, double-clicks, typing,
undo, page changes, pasting, rescaling — then asks the verifier whether the
document still re-derives, and finally whether it still prints. Fifty sessions
of four hundred gestures each currently run clean. Earlier ones did not: they
found a crash while rendering a page thumbnail, a page insertion that emptied
the document, a move that did not recalculate, and a reading order that was not
a total order.

`docs/what-matters.md` is the brief all of this is written against — what an
engineer needs from a calculation sheet, and what this tool does not claim.
`docs/interface.md` is the same for the interface: who is at the keyboard, and
why the chrome looks the way it does.
