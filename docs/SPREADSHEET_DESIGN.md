# Spreadsheets in CalcForge — design

The user's request (2026-10-08): "Yes import everything, make it work just
like excel … dragging copying styling conditional formatting highlighting
etc. there should be an insert table where I can drag a table to columns and
row as required. And in the page panel there's should be a inset spreadsheet
option which is similar but the whole page is a spreadsheet and if the page
before,after is a spreadsheet it does it like how else's does page outline
view so it's continues but shows a blue line for page break, there should be
canvas spreadsheet tot he right atleast the same width as the original page
for me to do side calcs(not in print region). It should allow be to resize
row column insets etc. also rotate page or landscape spreadsheet etc. …
Don't copy code from the original calcforge. Use that for the end feature
only. Write code from scratch. … Do not make ur own decision for complex
things. Ask me."

The 2twiqs branch (`claude/engineering-calc-markup-app-2twiqs`) is a reference
for what the finished feature should do. None of its code is used; everything
here is new.

## Decisions (asked as pop-up questions, answered by the user)

| Topic | Decision |
| --- | --- |
| Formulas | Excel's syntax in cells. A cell reference wins over a document variable of the same spelling; such a variable is written `var(M20)`. |
| Units | Cells hold units (`5 kN`) and calculate with CalcForge's unit system. Units that don't match are an error (`#UNITS!`). |
| Calculation order | Reading order between normal pages and sheets/tables: a table or sheet section uses variables defined before it; its values are usable after it. Inside a sheet section (one page, or consecutive sheet pages shown as one block) and inside a table, references are Excel's: A5 can be read above it. |
| Order clashes | Follow dependencies: evaluate in the order things depend on each other, reading order otherwise. A true loop is a circular reference, as in Excel. |
| Consecutive sheet pages | One sheet that grows. Its page count follows its content; typing past the last page adds one; no normal page can be put in the middle. |
| A table's place in reading order | Its top-left corner. |
| Cross references | A formula may read any other sheet or table: `='Sheet 2'!B4`. One name per table or sheet section, easy to set. |
| Values into equations | All four: name a cell (`W_total`); refer directly (`Loads.D12`); whole named columns as vectors; lookup by table name (`V := bolts(d, A, B)`, interpolating). |
| Scratch area | To the right of a sheet page, at least a page wide, never printed; formulas may read it. |
| Rotating a sheet page | Switches portrait/landscape and re-flows the page breaks. |
| What may sit on a sheet page | Markups only (no equations, no tables). |
| Insert table | Drag a rectangle; rows and columns appear live as it grows. Distribute rows/columns evenly (also for selected ones) in tables and sheets. |
| Tables in the PDF | Like equations: page drawing on the calc layer, editable only in CalcForge. |
| Clicks on sheet pages | Mode-aware. Markup mode: markup tools draw over the grid; Select picks a markup if one is hit, else a cell. Calc mode: clicks and typing go to cells. |
| xlsx | Open `.xlsx` as sheet pages and export to `.xlsx` (adds openpyxl). Copy/paste with Excel keeps formulas and formatting. |
| In scope | Charts, dynamic arrays (spill, FILTER/SORT/UNIQUE/SEQUENCE), named ranges and structured references, and everything else Excel does: fill handle, copy/cut/paste, Paste Special, formatting, borders, merge, number formats, Format Painter, conditional formatting (highlight rules, top/bottom, data bars, colour scales, icon sets, formula rules, rules manager), sort/filter, data validation, comments, find/replace, insert/delete/hide/resize/autofit, point mode, F4, Ctrl+arrows, drag-moving cells. **Out:** pivot tables. |
| Printing | Excel's defaults: gridlines on screen only, row/column headings never printed (both switchable per sheet); cell borders always print. |
| Page layout | Fit to N pages wide, repeat header rows (Print Titles), print area, margins and centring. |
| Page breaks | Excel's Page Break Preview: dashed blue automatic breaks, solid blue manual ones; dragging an automatic break makes it manual. |
| Sheet names | Automatic (Sheet1, Table1); renamed from a title tab on the sheet/table, its right-click menu, or Properties. References follow a rename. |
| A new table's look | Thin black borders on every cell, printed; changed afterwards as in Excel. |
| Default font and size | Excel's: Calibri 11, columns 64 px and rows 20 px wide/high (96 px to the inch), so Excel content keeps its size. |
| A table on a normal page | As on sheet pages: in Markup mode it is a markup (click selects, drag moves, double-click goes into its cells); in Calc mode clicks and typing go to the cells. |
| Dragging a table's edge or corner | Adds or removes rows and columns, as when inserting it; row and column sizes change by dragging their header borders. |
| Lookups by table name (confirmed 2026-10-09) | As built: `bolts(d)`, `bolts(d, "A", "B")`, `bolts(d, t)`; straight-line interpolation between rows, never extrapolated. |
| Column lists in equations (confirmed) | `Loads.Load` — the column under the heading's first word ("Load (kN)"), e.g. `sum(Loads.Load)`. |
| A number too wide for its cell | `####` as Excel, with Excel's feel: typing a number into a General cell of a column whose width was never set widens the column to fit it. |
| Find and Replace | Both: Ctrl+F in an open table is Excel's Find & Replace for that table; the document Search also finds text in every table's cells. |
| Cell conditional formatting with units | Units allowed: "greater than 200 kN" compares quantities (250 kN > 0.2 MN); a plain number compares the number as shown; units that don't match never match. |
| Print width of a sheet page (phase 4) | The columns that fit inside the page's margins print; every column after them is the scratch area (never printed), a blue line marking the edge. A Print Area, or Fit to N pages wide (which scales down), prints more. |
| Markups over a sheet page | Move with cells (Excel's "move but don't size with cells"): a markup stays on the cell it was drawn over when rows/columns are inserted, deleted or resized. |
| Empty pages at the end of a run | Kept: pages added stay until deleted in the Pages panel (the run still grows when typing past its last page). |
| Row numbers and column letters on sheet pages | Always on screen, in both modes, like Excel; printing follows each sheet's own switch. |
| Where charts go (phase 5) | Anywhere: a chart is its own item, on a sheet page over the cells (moving with them, like Excel) or on any normal page beside the equations; it reads a range of any sheet or table; it moves like a markup in Markup mode. |
| Chart types (phase 5) | The engineering subset, done well: XY scatter (markers, lines, both), line and column; log axes, error bars and trendlines. |
| Structured references (phase 5) | Excel's full syntax on tables, the first row being the headings: `Loads[Load]`, `Loads[@Load]`, `Loads[[#Headers],[Load]]`, `Loads[#All]`, `Loads[#Data]`, `Loads[[Load]:[Span]]`; they follow renames and grow with the table. |
| Chart look (phase 5) | Excel's default (2016 and later): Office colours, light grey gridlines, title on top, legend at the bottom; units from the cells shown in the axis titles. |
| Build order | 1 engine and formulas · 2 table markup with editing, fill, copy, formatting · 3 conditional formatting and data tools · 4 sheet pages, page breaks, scratch area · 5 charts, spill, named ranges · 6 xlsx. Each phase tested, pushed and reported. |

## Settled while building (small; recorded so they can be changed)

* **`var` and Excel's `VAR`.** Excel has a `VAR` function (variance). `var(M20)`
  or `var(L.beam)` — one bare cell-like name or one bare name — is the
  document variable; `VAR(A1:A9)`, `VAR(1,2,3)` and `VAR($M$20)` are Excel's
  variance. Excel's VAR of a single value is always `#DIV/0!`, so nothing
  Excel can do is lost.
* **Writing units in formulas.** A unit follows a number: `=5 kN`,
  `=10 kN/m*B2`, `=3 m^2`. On its own a unit is written SMath's way with an
  apostrophe: `=A1/'kN`. A bare name is looked up as a defined name, then a
  document variable, then a unit.
* **Showing units.** A quantity is shown in the unit it was typed in;
  `5 kN + 200 N` shows `5.2 kN` (the first operand's unit); `5 kN * 2 m`
  shows `10 kN·m`, like units cancelling (`10 kN/m * 3 m` shows `30 kN`).
  Otherwise the unit is the one CalcForge's equations would choose. A cell's
  format may name a display unit.
* **A quantity compared with plain 0** is a test of its sign (`=A1>0` with A1
  = 5 kN is TRUE); any other comparison of a quantity with a number of
  another dimension is `#UNITS!`. An empty cell added to a quantity counts as
  zero of that unit.
* **CalcForge's own functions:** `VALUEIN(x,"kN")` (x as a plain number in
  kN), `CONVERT(x,"kN")` (x shown in kN; the three-argument form is Excel's),
  `INTERP(x, xs, ys)` (straight-line interpolation), `UNITOF(x)`,
  `STRIPUNIT(x)`.
* **Circular references** show 0 in the loop's cells and are listed in
  `Workbook.circular` (Excel's status-bar warning); cells reading them carry on
  with the 0.
* **Dates** use Excel's 1900 system, including its 29 February 1900, so files
  agree with Excel. A typed `9/10/2026` is read day first (the workbook's
  `day_first` setting).

* **Lookups by table name (phase 2).** A table used as a function in an
  equation searches its first column (numbers, with units) and interpolates
  in a straight line between rows; outside the table is an error, never an
  extrapolation:
    - `bolts(d)` — the rest of that row (one value, or a vector);
    - `bolts(d, "A")` or `bolts(d, "A", "B")` — the values under those
      headings (first row), a value or a vector;
    - `bolts(d, t)` — with numbers along the first row: interpolated both ways;
    - `bolts(d, 2)` — with text headings: the second column after the keys.
* **Columns as vectors.** `Loads.Load` is the column under the heading
  "Load" in the table's first row (the heading's first word, so
  "Load (kN)" is `Loads.Load`), down to its last filled cell. A cell
  reference wins over a heading spelled like one.
* **Defined names** (`W_total`) are kept, saved and undone with the table
  their cells are on.
* **Copying across tables** behaves as in Excel: a copied formula reads the
  table it lands in; a *cut* keeps reading the cells it read.
* **New rows and columns** take the look of the one beside them, so a
  bordered table stays bordered as it grows.
* **Moving a table** in Calc mode: by its name tab (clicks on cells go to the
  cells); in Markup mode it is a markup like any other.

* **Sheet pages (phase 4), small things settled while building:** Fit to
  page width is "fit to 1 page wide" (Excel's N pages wide with N = 1); a page
  added beside a run joins it at its end; a copied sheet page is an ordinary
  page (one sheet is one run); deleting a run's page deletes its rows; the
  column letters sit above the run's first row (not frozen at the window top);
  the selection reaches one row past the last page, where typing adds a page;
  a sheet page's markups are drawn with its cells into the calc layer and kept
  in the record instead of being written as annotations.

* **Phase 5, small things settled while building:** a spilled block may not
  run out of a table (its size is fixed by dragging its edge), so it is
  `#SPILL!` there; standard-deviation error bars are drawn round the series'
  mean with the sample standard deviation, as Excel draws them; R² of an
  exponential or power trendline is that of the logarithms (as Excel); a
  chart's title is the series' name when it has one series and none
  otherwise; when the series have different units the axis title shows none;
  a trendline's equation goes in the corner of the plot the points leave
  clearest; deleting a defined name a cell still reads leaves it reading the
  same word as a unit if it is one (`g` is then grams), as names come before
  units.

## Tables on pages (phase 2)

* `items/table.py` — the table markup. Calc layer, printed, saved as page
  drawing with its cells in the record. Screen only: the name tab, and while
  open the row/column headings, selection, fill handle, reference colours.
* `ui/tableedit.py` — working in the cells: selection and Excel's keys, the
  cell editor and formula bar, point mode, F4, fill handle, drag-move,
  heading resize and AutoFit, insert/delete/hide/distribute, merge, clipboard
  (CalcForge's own, Excel's XML Spreadsheet with R1C1 formulas, HTML, text),
  Format Painter, the right-click menu. Every change is one undo step of the
  window (a page snapshot).
* `ui/tablebar.py` — the table's controls on the properties toolbar.
* `ui/celldialog.py` — Format Cells (Number with a display unit, Alignment,
  Font, Border, Fill).
* `sheet/docbook.py` — the document's workbook and the bridge to the
  equations; `sheet/clip.py`, `sheet/fill.py`, `sheet/store.py` — clipboard,
  fill series, the record.

## Engine (phase 1)

`calcforge/sheet/` holds the engine; it has no Qt in it.

* A workbook holds every sheet section and table of a document. Cells are
  sparse (`dict` keyed by row and column, plus per-column sorted row lists so
  `SUM(A:A)` walks only the filled cells).
* A formula is kept as typed. References are rewritten token by token (copy,
  insert/delete rows and columns, move, rename), so spacing and case stay as
  typed. For calculating, it is parsed once per *shape*: references without
  `$` are kept relative to the cell (as Excel's R1C1), so a column of filled
  formulas shares one tree.
* Recalculation: a changed cell marks its readers (and theirs) dirty; the
  dirty formulas are then ordered so each comes after what it reads, found
  by a depth-first walk that also finds loops. Block references are indexed
  by column buckets and looked at once per wave of changes, however many
  cells changed. Volatile functions (NOW, RAND, OFFSET, INDIRECT…)
  recalculate on every edit, as in Excel.
* Undo: every change is recorded inside a transaction (one user action, one
  undo step); structural changes record each cell and formula they touched,
  so undo restores exactly what was there (including references that a delete
  made `#REF!`).
* The bridge to equations: `Workbook.outside(sheet, name)` is asked for a
  document variable (the document answers with the value defined before the
  sheet's place in reading order); `outside_changed(names)` recalculates the
  cells that read them. `evaluate.to_engine` / `from_engine` convert values
  both ways. The document's worksheet asks the book for names and functions
  it does not define itself (`evaluator.EXTERNAL`, set per worksheet); after
  each calculation, tables and equations take up each other's changes on the
  next turn of the event loop, round after round until nothing changes, so
  dependencies win over reading order.
