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
| Formulas | Excel's syntax in cells. ~~A cell reference wins over a document variable of the same spelling; such a variable is written `var(M20)`.~~ Replaced 2026-10-24 (the user: "to use a calc forge variable, you always have to do var(variable), maybe change from var to something excel does not have as a function, so there can never be a clash"; by pop-up: a function, everywhere): a bare name in a cell is only ever an Excel name (the sheet's, then its workbook's); a CalcForge variable — an equation's, a measurement's, a cell named in its Variable box — is `CALC(x)`. `VAR(...)` is always Excel's variance. |
| Units | Cells hold units (`5 kN`) and calculate with CalcForge's unit system. Units that don't match are an error (`#UNITS!`). |
| Calculation order | Reading order between normal pages and sheets/tables: a table or sheet section uses variables defined before it; its values are usable after it. Inside a sheet section (one page, or consecutive sheet pages shown as one block) and inside a table, references are Excel's: A5 can be read above it. |
| Order clashes | ~~Follow dependencies: evaluate in the order things depend on each other, reading order otherwise.~~ Replaced 2026-10-17 (the user's answer by pop-up): **reading order, as in SMath.** An equation reads the latest definition before it, an equation's, a measurement's or a table's alike (a table's names are defined at its top-left corner); a name defined only below an equation is "not defined" there (SMath's red "test - not defined."), even when a table further down has it. A cell reads only the equation variables defined above its sheet. Tables and equations still take up each other's changed values until nothing changes; a true loop is a circular reference, as in Excel. |
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
| xlsx (confirmed 2026-10-10) | Open `.xlsx` as sheet pages (adds openpyxl): cells only — values, formulas, formatting, sizes, merges, names, comments, validation, conditional formatting and the page layout; charts and pictures are left out (said so on opening). No export to `.xlsx`. Copy/paste with Excel keeps formulas and formatting. |
| An imported workbook's names (2026-10-19, by pop-up) | A workbook comes in as one: its sheets share its names. **Self-contained** (the default, a tick in the import chooser) its names are its own: equations below read any of its cells by sheet and cell (`Seismic_Actions.H44`) and its names only qualified (`Seismic_Actions_NZS1170_5.Cd_T_min_ULS` or `Seismic_Actions.Cd_T_min_ULS`), never bare. Inside its cells a bare name is the workbook's own name first (a sheet-local name wins on its sheet, Excel's rule), and never an equation's variable, which is read as `CALC(X)` (2026-10-24). **Unticked** (replaced 2026-10-24: "un self contained workbook variable names (like spreadsheet names) should not be accessible from outside unless I dial in like sheet1.variable ... selfcontained shows nothing and cant dial in"), its names are read from outside only dialled in, as a spreadsheet's own names are (`Seismic_Actions.Cd`, `Seismic_Actions_NZS1170_5.Cd`, a cell's `='Seismic Actions'!Cd`), never bare; so they never clash and the import asks nothing about clashes (the prefix renaming and "go ahead" are gone). Self-contained, not even dialled in. Changeable later from the sheet tab's right-click menu (Self-contained) and the Properties panel's Workbook section; one undo step; saved with the document. Two self-contained workbooks with the same names stay apart. |
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
| A table on a rotated page (2026-10-10) | Like equations: it turns with the page and prints turned, but is upright while open for its cells. |
| Box-selecting markups on a sheet page (2026-10-10) | Ctrl+drag draws the selection box over the sheet; a plain drag selects cells; Shift+click adds markups one by one. |
| Variables panel (2026-10-10) | A Tables section: each defined name and each table column the equations can read, with its value; clicking one goes to its cells. |
| Pages across (2026-10-11) | A sheet wider than its paper prints on pages side by side on the canvas, numbered down then over (Excel's default); more pages across come from a print area wider than the paper, a vertical page break (Insert Page Break at a cell right of column A, or dragged) or Fit to N pages wide. Columns to repeat print at the left of each page across. |
| Calc section breaks (2026-10-11) | A break above a page starts the calculation afresh from there: equations, tables and sheets of earlier sections are not read (an equation reading one says so; a cell formula gives #REF!). Made global — an equation by right-click ▸ Global or the Variables panel, cells by right-click ▸ Make Global — it is read by every later section. The break shows as a purple band above its page (never printed); the Variables panel lists variables section by section. Sheet and table names stay unique across the whole document. |
| Sheet tabs (2026-10-11) | A tab strip under the canvas that navigates: every sheet in reading order (tables have no tab, the user's word); click goes there, double-click renames, dragging a sheet's tab moves its pages, + adds a sheet. Each sheet keeps its own printed pages. |
| Cells and equations alike (2026-10-11) | Cells adopt SMath's units, fonts unchanged: a unit is typed SMath's way too (`5'kN`); a custom unit the equations define (`kip_s := 5'kN`) works in cells written with the apostrophe (`2'kip_s`, `=3*'kip_s`) — a bare word stays text or a name; SMath's unit box sits after the value in the formula bar (a small black box when empty) and shows the selected cells' quantities in the unit typed into it, custom units included. Cells keep Excel's font (Calibri 11, whose cap height matches SMath's 10 pt equations); WebSMath's drawing is untouched. |
| Units typed as in SMath (2026-10-11) | Typing a unit into a cell is exactly SMath's: SMath's black unit box after a number alone, the unit in SMath's blue, and SMath's own unit list (entries, order, icons, descriptions) under the unit being typed — in the cell and the formula bar, in entries and in formulas. The output unit is changed with SMath's black unit box after the selected cell's quantity (on screen only, never printed): click it — or the unit once one is set — and type the unit, with SMath's list; blank goes back to as typed. The formula bar's unit box stays in step. |
| Build order | 1 engine and formulas · 2 table markup with editing, fill, copy, formatting · 3 conditional formatting and data tools · 4 sheet pages, page breaks, scratch area · 5 charts, spill, named ranges · 6 opening xlsx. Each phase tested, pushed and reported. |

## Settled while building (small; recorded so they can be changed)

* **`CALC(x)` and Excel's `VAR`** (2026-10-24, replacing `var(x)`). `CALC(x)`
  reads the CalcForge variable x where the sheet is: the latest defined
  before it, as an equation would read it; a cell named x in its Variable box
  of the same workbook wherever it is (`DocumentBook.calc_variable`).
  `VAR(...)` is always Excel's variance. A document recorded before
  (`store.CALC_NAMES` missing from a sheet's record) is rewritten once as it
  opens (`DocumentBook.settle_old_formulas`): a bare name that read an
  equation's variable, and `var(x)` of one, become `CALC(x)`; an Excel name
  of the same spelling, a LET or LAMBDA name, a sheet's name are left alone.
* **Errors explained** (QA, 2026-10-15). An error carries a reason
  (`ErrorValue.reason`, not part of comparing it); selecting or hovering a
  cell with an error says it in one line, following it back to the cell it
  started in (`sheet/explain.py`): `#UNITS! — kN and m can't be added (A1 + A2)`.
* **General fits its column** (QA, 2026-10-15). As Excel's General format: a
  number is rounded to the column's width, or written 1.2E+09 when that is
  shorter, measured with the cell's real font; `####` only when even that
  won't fit, or for an explicit number format. The value and formula bar
  keep every digit.
* **A column dragged to nothing is hidden** (QA, 2026-10-15), keeping its
  width for Unhide; dragged from just right of the double line it opens
  again. Rows alike.
* **Date results** (QA, 2026-10-15): a formula whose result is a date or a
  time (`=DATE(…)`, `=TODAY()+7`, `=NOW()`, `=TIME(…)`) gives a General cell
  a date or time format, as a typed date does.
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

* **Phase 6, small things settled while building:** every worksheet comes in,
  hidden ones too (other sheets' formulas read them), each as its own run of
  pages; File ▸ Open of an `.xlsx` makes a new document, File ▸ Insert
  Excel… adds to this one; a worksheet's Excel tables become plain cells and
  their structured references the cells they name; a print scale other than
  100 % is left out (said), Fit to page width is kept; cells Excel shows but a
  formula here gives otherwise are listed by address after opening.

* **Excel's implicit intersection** (2026-10-19, the user's two engineering
  workbooks). A formula an `.xlsx` stores plainly (not as an array formula)
  is worked out as Excel did before dynamic arrays: a name of a block
  (`s_x = $J$17:$J$39`), a block reference, or what INDIRECT or OFFSET give,
  standing where one value is wanted, is the cell of the block in the
  formula's own row (a column) or column (a row). The reader writes Excel
  365's `@` there, as Excel 365 shows such a formula (`=@s_x*@w`), so the
  cell keeps Excel's answer and says why (`sheet/legacy.py`). Where a value
  is wanted follows each function's arguments: SUM's, COUNTIF's range,
  VLOOKUP's table, OFFSET's reference take a block as it is; SUMPRODUCT,
  INDEX's array, LOOKUP's vectors, LARGE, MMULT work over whole arrays;
  IF's and CHOOSE's results pass on what they are given; every other
  argument and the operands of `+ - * / ^ & = < >` take one value. An array
  formula (Ctrl+Shift+Enter, or a dynamic one) is left as it is.
* **A name whose cells were deleted** in Excel (`Wp = 'Seismic Actions'!#REF!`)
  comes in as a name giving `#REF!`, as Excel keeps it, instead of being
  left out. A sheet-local name is kept with its own sheet whichever cells it
  names.
* **How an imported workbook is named** (2026-10-19). Its name for the
  equations is its file name without the extension, each run of characters
  an identifier can't hold made one `_` (a leading digit gets a `_` before
  it), unique among the document's sheet names (as equations write them)
  and other workbooks' names by `_2`, `_3`…:
  `Seismic_Actions_NZS1170.5.xlsm` is `Seismic_Actions_NZS1170_5`; the same
  file inserted again is `Seismic_Actions_NZS1170_5_2`. A sheet is written
  in equations as its name, or, when its name holds spaces or other such
  characters, with each run of them one `_` (`Seismic Actions` is
  `Seismic_Actions`, `Tables (2)` is `Tables_2`); its exact name still
  works. A self-contained workbook is closed, as a self-contained
  calculation block is (the user, 2026-10-24): equations read it only by
  `Sheet.H44` and by its CalcForge variables (a cell named in its Variable
  box is always a document name, `DefinedName.variable`, read bare); its
  Excel names, `Sheet.Name`, `Book.Name` and its headings are not read from
  outside. In an equation:
    - `Sheet.H44` — that cell of the sheet (a table's too: `Loads.D12`);
    - `Sheet.Name` — the defined name as that sheet's cells read it: the
      sheet's own name first, then its workbook's (so any sheet of the
      workbook qualifies a workbook name; a sheet-local name needs its own
      sheet: `Tables.ReturnPeriodFactor`) — not on a self-contained
      workbook's sheet;
    - `Book.Name` — the workbook's own (workbook-wide) name, of a workbook
      that isn't self-contained;
    - `Table.Heading` — a table's column, as before (a defined name of the
      same spelling on that sheet wins);
    - a bare `Name` — a CalcForge variable (a cell named in its Variable
      box), and nothing else: every Excel name, an imported workbook's
      included, is dialled in.
  Qualified names follow reading order like any other: the sheet must be
  above the equation.
* **Which name a cell reads** (Excel's order, then the document's): the
  cell's sheet's own name; its workbook's name; on a table on a page, a
  name the tables share; a unit. Never an equation's variable: that is
  `CALC(X)`. `Sheet!Name` reads the name as that sheet's cells do
  (`'Seismic Actions'!Cd` too), refused (`#NAME?`) from outside a
  self-contained workbook (`Workbook.closed_to`).
* **Where the setting lives.** Each sheet of an imported workbook carries
  the workbook (`"book": {"id", "name", "file", "self_contained"}`) in its
  record, so it is saved with the document and undone with the pages
  (`Workbook.books`, `Sheet.book`, `DefinedName.book`; a workbook name's key
  is `(name, book id)`). The Variables panel leaves a self-contained
  workbook's Excel names out, and lists those of one that isn't as dialled
  in, under "Workbook <name>"; the Name Manager's Scope says "<name>
  (self-contained)" or "<name>".

## Workbooks side by side (2026-10-24)

A document can hold several workbooks: Excel workbooks brought in and
workbooks made here, each a run of spreadsheet pages (a Section). The user,
2026-10-24: "think of some other issue along these lines for merging
multiple workbooks in one file like this app allows ... think through all
possibilities and how they might clash". What could clash, and what
happens:

| Clash | What happens |
| --- | --- |
| A bare name in a cell vs a CalcForge variable | Never: a bare name in a cell is only ever an Excel name (the sheet's, then its workbook's); a CalcForge variable is read as `CALC(x)`, a function Excel doesn't have. `VAR(...)` is always Excel's variance. Old documents are rewritten once when opened (`store.CALC_NAMES`, `DocumentBook.settle_old_formulas`). |
| Two workbooks with a name of the same spelling | Each its own: a workbook's names are keyed by its Book (`(name, book id)`), a sheet's own by the sheet. A formula reads its own workbook's; another workbook's only as `Sheet!Name`, refused from outside a self-contained one. |
| Workbooks made here | Each is a workbook as an imported one is (a Book: Self-contained, its own names, the Properties panel's Workbook section, the Name Manager's list). A new one is self-contained; one recorded before every workbook had a Book is given one as it comes in, not self-contained, its names its own, and a table that read one of them bare reads it as `Sheet!Name` (`sheetpages.give_books`). |
| Two workbooks with a sheet of the same name | Sheet names stay unique in the document (the user's choice, 2026-10-24): the later one is renamed as Excel names a copy, "Loads (2)", and its formulas, names, rules and validations follow. The workbook remembers the name it had (`Book.renamed`), so text its formulas build — `INDIRECT("Loads!A1")` — still reads its own sheet (`Workbook.sheet_as_written`). |
| A formula reading another workbook (`[1]Snow.xlsx` … `Sheet1!B2`) | When that workbook is in the document already, it reads it live, by its sheets as named here (`xlsx.linked_formula`; a name of it as the cells the name gives). When it isn't, the cell keeps the value Excel last showed, and the import says how many (bring the other workbook in first). |
| Copying cells from one workbook to another | The names their formulas use come with them, as Excel's copy brings them; when the destination has its own name of that spelling, the destination's is used, as Excel's "use this version" (`clip.bring_names`). |
| The 1904 date system | A workbook kept in it (Excel for Mac) comes in with the same dates: its dates are read as dates and kept in the document's one system (1900). |
| Excel tables (ListObjects) | Their structured references are written as the cells they name on the way in, so two workbooks' `Table1` can't clash. |
| Conditional formatting, data validation | Per sheet; their formulas read names as the sheet's cells do, so per workbook. The Rules Manager shows the sheet's or the selection's rules. |
| The Name Manager, the Name Box, Find | One workbook at a time: the Name Manager's drop-down picks the workbook (the open sheet's to start), the tables on pages, or the CalcForge variables, and its Scope is Workbook or the sheet; the Name Box lists the open sheet's workbook's names; Find's Within is Sheet, Workbook or Document. |
| Iterative calculation | Not carried: a workbook that relies on Excel's iterative calculation shows its circular references as errors, and the import says so. |

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
* **Recalculating fast** (2026-10-19: an input of the user's seismic
  workbook, read by 4,000 formulas, must feel instant). Three things, none
  changing an answer (`tests/test_workbook_speed.py` checks every value
  against a full recalculation, and each short cut against walking the
  tree):
    - *Only what can have changed is worked out.* Of the dirty formulas,
      the roots — typed, volatile, reading a name or a document variable
      that changed — are always worked out; any other only when something
      it reads (its cells, blocks, the cells of its names) changed value in
      this pass. A dependent whose inputs came out the same is left as it
      is, so a volatile INDIRECT that gives what it gave stops there
      (Excel itself works out everything below a volatile cell).
    - *Each formula is compiled once* into Python closures
      (`sheet/compiled.py`), kept on its shared parsed form: a cell read for
      its value is fetched straight away, `+ - * / ^` and the comparisons of
      two plain numbers are done on the spot, IF and IFERROR choose their
      branch directly; everything else is `evaluate.ev`'s own code for that
      node. A defined name's formula is parsed once while it stays the
      same; a sheet named in formulas, and the calculation sections, are
      looked up once a pass.
    - *The order is kept.* Every formula's place in an order where each
      comes after what it reads is kept until a formula, a sheet or a name
      changes; an edit sorts its dirty formulas by it, and the same cells
      typed into again reuse what they reached and its order. With spills
      or circular references the dirty formulas are walked as before.
  The screen follows: a sheet page's band of cells is drawn again only when
  what conditional formatting makes of its own cells changed, the headings
  draw only the columns in view (one mark for a run of hidden ones), and the
  Variables panel is brought up to date when it is shown.
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
  next turn of the event loop, round after round until nothing changes.
  Which definition an equation reads is reading order alone (2026-10-17):
  the latest one before it, an equation's or a table's
  (`IndexedContext.entry`, `DocumentBook.defined_at`); a table below it is
  not read ("name - not defined.").
