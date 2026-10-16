# Bug hunt, round 1 (2026-10-16)

Base 4f6e28b (command-family sweep read at 7763468, the branch head with the
regrouped page menu). Everything driven in the real window, offscreen, with
QTest/QMouseEvent events on `view.viewport()`. Regression tests for the fixed
ones: `tests/test_bughunt_round1.py`. Status: **fixed** (in this branch) ·
**open** · **decision** (needs the user) · **not a bug**.

## A. Calc-mode row selection, every way

```
[HIGH] A sheet page's row numbers and column letters did nothing until a cell was clicked — fixed
Repro: insert_sheet_page(0); either mode; click (or drag, Shift+click, right-click) a row number or column letter before clicking any cell
Expected: the whole row/column is picked (Excel); right-click gives the row menu
Actual: nothing — tables.item None, no selection; worked only after a first click in a cell. Same in Markup and Calc mode; the likeliest cause of "in calc mode can't select rows"
Owner area: ui/tableedit.py mouse_press (new _press_run_heading)
Confidence: verified twice
```
```
[MED] Clicking a kept (sticky) row heading scrolled the sheet away from the pointer — fixed
Repro: sheet page, zoom 2, centerOn H40 so view.sheet_headings shows the row strip; click a row number in it
Expected: the row is picked and the canvas stays put (Excel never scrolls for a heading)
Actual: the active cell (r, A) was scrolled into view — back across to column A; with the sheet not open yet, up to A1 and down again — so the next drag/Shift+click hit other rows (picked 31–33 instead of 39–41). Both modes
Owner area: ui/tableedit.py _scroll_to/_press_heading
Confidence: verified twice
```
```
[LOW] Click an equation, then Shift/Ctrl+click another: only the second is picked — open
Repro: three equations in a row; click the first, Shift+click (or Ctrl+click) the second; both modes
Expected: both picked (Revu's Shift/Ctrl-click adds)
Actual: the first click opens the first equation for typing (not picked), so the selection is just the second. A marquee or Ctrl+A works
Owner area: ui/calcedit.py mouse_release (focus on a plain click)
Confidence: verified twice
```
Worked, identical in Markup and Calc mode, on a sheet page and an open table
markup: click/drag/Shift+click/Ctrl+click on row numbers of an open sheet or
table, Shift+Space, Shift+↓, drag across cells, right-click row number (row
picked + Excel's short heading menu), the sticky strip (click, drag,
Shift+click); marquee left→right and right→left over a row of equations, inside
an open calc block too; Ctrl+A (all equations; in an open block, the block and
its equations). A closed table markup shows no headings in either mode (by
design: one click opens it in Calc mode, a double-click in Markup mode).

## B. Finding 1.7 — dragging a 400-markup selection by one markup's edge

```
[MED] A press on a picked markup's stroke resizes that one markup instead of moving the selection — decision
Repro: 400 RectItem 20×14 pt in a grid; Ctrl+A; press at the middle of one's top stroke (local 10,0) and drag 30,25
Expected: all 400 move (Revu: "drag to reposition"; multi-selection allows movement)
Actual: 0 moved. view._press_select step 5 checks every selected markup's handles first: HANDLE_SIZE = 4 pt round each of the 8 control points and 4 scale-box corners (3 pt outside the shape) covers nearly the whole stroke of a small markup, so the press becomes "resize" of that markup — or of a neighbour whose scale-box corner is within 4 pt (the corner case resized a neighbour). An unfilled rectangle can only be grabbed by its stroke, so a selection of small ones cannot be dragged at all. Pressing the interior of a filled one moves all 400. Same with 1, 2 or 5 picked — not a speed problem, unchanged by the 1.1 fix
Options: (a) with more than one markup picked, control points don't take the press and the drag moves the selection (resize through a group box, as groups already have); (b) only the pressed markup's own points count, within the drawn square
Owner area: ui/view.py _press_select (step 5), items/base.py handle_at
Confidence: verified twice
```

## C. Typing never fires shortcuts

Swept 13 contexts × 96 keys (a–z, Shift+A–Z, 0–9, F2–F12, Delete,
Backspace, Ctrl+C/V/X/Z/A); checked the character typed, tool/page/mode/zoom/
theme/markup style/full screen unchanged, markup count and selection unchanged,
no action fired, no popup or dialog.

```
[MED] F12/F11/F9/F7 fired while typing in a box — fixed
Repro: focus the Search field (or formula bar, Name Box, a Properties field such as Subject, the typed size while drawing a rectangle, a dimension's words); QTest.keyClick(focus, Qt.Key_F12)
Expected: the key stays with the box, as it already did in a cell, an equation and a text box
Actual: F12 switched to Calc mode, F11 went full screen, F9 calculated, F7 opened Check Spelling, mid-word. The canvas boxes (typed size, dimension words) live in proxy widgets, which the window's key filter never saw
Owner area: ui/mainwindow.py eventFilter (+ _a_field_being_typed_in), ui/view.py PageView.event and _SizeEdit.keyPressEvent
Confidence: verified twice
```
Clean (0 leaks, every character typed): text box, callout, dimension words,
Search, typed size, equation, cell editor, formula bar, Name Box, Properties
field, a dialog's line edit in both modes. Not bugs: F1 opens Keyboard Shortcuts
from any box (Help, as everywhere); in an equation Ctrl+A picks every equation
(SMath's select-all, `select_all_equations`) and the window's Copy/Cut/Paste
run but hand the equation's own selection to `calcedit.clipboard` — nothing
outside the equation is touched. Harness note: `QTest.keyClick(w, Qt.Key_A,
Shift)` sends "a"; send the character to get "A".

## D. Crash under parallel tests

```
[HIGH] After the app's main() has run once, the crash dump goes to a reused file descriptor and every Python error to a closed file — fixed
Repro: tests/test_settings_migration.py calls calcforge.app.main() (exec patched); afterwards in the same xdist worker raise anything in a Qt callback
Expected: main() hands faulthandler and sys.excepthook back when it closes crash.log
Actual: keep_a_crash_log() enabled faulthandler on crash.log and replaced sys.excepthook; main() then closed the file and left both on it. faulthandler holds the descriptor number, so a later hard crash wrote its dump into whatever file or pipe had reused it — which is why the worker that died ("node down: Not properly terminated") left no dump. Every later exception printed "Error in sys.excepthook … ValueError: I/O operation on closed file" (in every full run's log)
Owner area: calcforge/app.py (close_the_crash_log)
Confidence: verified twice
```
```
[HIGH] The xdist worker's native crash itself — open (not reproduced)
Repro: PYTHONFAULTHANDLER=1 QT_QPA_PLATFORM=offscreen python -m pytest -p no:cacheprovider -q -n 3 tests/test_revu_ui.py tests/test_usability.py -x, twice
Actual: both runs passed, no dump. The one logged death (qa/round2/full_run2.txt) came with "resource_tracker: 3 leaked shared_memory objects" — the worker died while io/pdftiles.py's render processes (one SharedMemory each) were up, so it was a hard death of the worker, not a Python error. With the fix above the next one will leave its dump on stderr
Owner area: io/pdftiles.py _Worker (QThread + spawn processes), unknown
Confidence: harness doubt (not reproduced)
```
Noise, not a bug: one "TypeError: Unknown return type used in call of meta
function (that may be a signal)" per window, printed as the worker exits.

## E. Command-family consistency (menus at 7763468)

Places walked: menu bar (every submenu filled), Document ▸ Current Page (=
the Thumbnails menu, `page_menu`), the page menu on a spreadsheet page, the
canvas menu on bare paper in both modes, a rectangle's menu, the document tab,
the sheet tab, a cell and a row heading, every toolbar, every panel's buttons.

| # | Family | Type | Finding | Status |
|---|---|---|---|---|
| E1 | Insert | 2 | One command, three names: "Insert Pages ▸" (page menu, Revu's name) vs "Pages from Document…" (Document ▸ Insert, File ▸ Import, Main toolbar) | fixed (round 6) |
| E2 | Insert | 2,3 | "Add Sheet Page" on a spreadsheet page's menu is exactly Insert Spreadsheet Page ▸ After (`insert_sheet_page(index)`), under another name, two groups away in "CalcForge's own" | fixed (round 6) |
| E3 | Insert | 4 | From the menu bar, Blank Page… and Pages from Document… ask where (their dialogs have a placement); Spreadsheet Page, Image Page… and Excel Workbook… always go after the current page, no choice. Before/After exists only in the page menu | fixed (round 6) |
| E4 | Insert | 2 | Thumbnails panel "+" is "Add a page" (opens Insert Blank Page); "▦" is "Insert a spreadsheet page" — two wordings for the menu's Insert Blank Page / Insert Spreadsheet Page | fixed (round 6) |
| E5 | Insert/Calc | 3 | Calc mode's canvas menu: "Insert Equation Here" and "Calculation Block" sit outside the "Insert Here ▸" submenu that holds Text Box, Callout, Note… ; the Calculation toolbar and menu call it "Block" | fixed (round 6) |
| E6 | Import/Export | 2 | Inside the submenus: File ▸ Import ▸ "Import Tool Set…" and File ▸ Export ▸ "Export PDF…", "Export Images…" repeat the menu's word; the siblings ("Excel Workbook…", "Markups Summary…") don't | fixed (round 6) |
| E7 | Rotate | 1,2 | Document menu has Duplicate, Extract, Split, Delete, Crop Pages but no Rotate Pages (only in Current Page ▸). Page menu says "Anticlockwise", View ▸ Rotate View says "Rotate Counterclockwise" (UK decision: Anticlockwise) | fixed (round 6) |
| E8 | Extract/Crop/Split | 1 | Split Document… and Crop Pages… are in the Document menu but not the page menu, which has Extract Pages… beside where they'd go | fixed (round 6) |
| E9 | Move | 1,3 | Move Up / Move Down are only in the page menu, and there in "CalcForge's own" group, away from Cut/Copy/Paste Pages and the inserts | fixed (round 6) |
| E10 | Print | 2,3 | The page menu has "Print Pages…" (prints) and, at the bottom, a tick called just "Print" (include in print/export) — same word, different thing, two groups apart. Properties' markup tick is also "Print" | fixed (round 6) |
| E11 | Scale | 2 | `calibrate_dialog` is "Set Scale…" (page menu, canvas menu, a measurement's menu) but "Page Scale…" in the Document menu | fixed (round 6) |
| E12 | Page setup | 2 | Window ▸ Panels ▸ "Page Setup" is a panel; "Page Setup…" everywhere else is the dialog | fixed (round 6) |
| E13 | Sheet layout | 2 | `sheet_page_setup` is "Sheet Layout…" (Document, page menu) but "Page Layout ▸ Page Layout…" in the cell menu | fixed (round 6) |
| E14 | Flatten | 1,2 | "Flatten…" (page menu, Batch) is the dialog; Document has "Flatten Selection" + "Unflatten" but not "Flatten…"; a markup's menu says "Flatten"; Unflatten is in no right-click menu | fixed (round 6) |
| E15 | Colour | 2,4 | Spelling mixed for one family (UK decided): Document "Color Processing…" vs page menu "Colour Processing…"; markup menu "Change Colours…" vs Properties buttons "Change Colors…"; an image's right-click "Colour Processing…" and Properties "Color Processing…" open Change Colours (`change_colors(item)`), not the page's Colour Processing of the same name | fixed (round 6) |
| E16 | Copy/paste | 1,3 | Edit has Paste in Place and Paste Here…; a markup's menu has neither. Its "Duplicate" is in the shape-extras group after Show Size, not with Cut/Copy/Paste as in Edit | fixed (round 6) |
| E17 | Hide/Lock/Delete | 3 | Edit menu: Hide, Show Hidden and Delete in one group, Lock in another; a markup's menu groups Flatten, Lock, Hide and puts Delete with Cut/Copy/Paste. Show Hidden is in no right-click menu | fixed (round 6) |
| E18 | Align | 2 | Edit ▸ "Align ▸" / "Arrange ▸" vs a markup's "Alignment ▸" / "Order ▸" (round 4 asked for Revu's); Edit ▸ Text ▸ "Align Center" vs Align ▸ "Align Centre" in the same menu | fixed (round 6) |
| E19 | Names | 2 | Lower-case tool names in Tools ▸ Markup/Measure: "Text box", "Highlight area", "Center radius", "Polygon cut-out", "Ellipse cut-out" (the canvas menu says "Text Box") | fixed (round 6) |

Round 6 (2026-10-16) fixed E1–E19 in the menus, right-click menus, toolbars and
panel buttons; `tests/test_command_families.py` checks each family in every
place. Left for their owners: the Properties panel and Properties toolbar keep
Revu's "Color:" / "Fill Color:" field labels and the markup's "Print" tick
(propbar.py, Revu-parity tests).

Worked: every insert type has Before/After in the page menu and Document ▸
Current Page (7763468); Cut/Copy/Paste Pages, Duplicate, Extract, Delete Pages…,
Print Pages… act on the run picked out and say how many; the thumbnails "−"
and the menus open the same Delete Pages dialog.
