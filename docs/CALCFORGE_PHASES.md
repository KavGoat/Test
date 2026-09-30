# CalcForge — phase reports

What each phase changed, how it was tested, and what behaves differently from
SMath or Bluebeam. The plan is `CALCFORGE_PLAN.md`; requirements are in
`tasklist.md`. Completion status belongs to the user.

## Phase 1 — engine and units merged (2026-09-30)

- WebSMath's engine, editor, worksheet and plot code are in `markforge/calc/`,
  unchanged except for one import line: `ast_to_items` moved out of the `.sm`
  module into `calc/astitems.py`. The unit table regenerates byte for byte from
  SMath's `Units.xml`.
- The 766 WebSMath tests are in `tests/calc/`. SMath's example `.sm` files are
  read through a test-only reader, `tests/calc/smfile.py`.
- Pint is removed. `core/units.py` is built on the engine's quantities, SMath's
  unit names and its number formatter.
- Fixed:
  - `/Measure` `/C` was in mm per point while `/U` named the display unit, so
    other editors measured 1000× too long.
  - The PDF writer kept only six decimal places, which lost precision in small
    factors.
- Different from before:
  - Status-bar scale, totals and calibration labels use 4 decimal places
    instead of 4 significant figures.
  - `-0.00` is shown as `0.00`.

## Phase 2 — equations on pages (2026-09-30)

**What changed**

- **One worksheet for the document** (`calc/docsheet.py`): pages are folded
  into the reading order, so reordering or deleting pages re-keys the
  equations. Moves are calculated when the gesture ends, not on every mouse
  move. A restored page is calculated once.
- **The record** (`calc/record.py`): an equation's source is stored as plain
  JSON (tree, unit box and options). Every region of SMath's 18 example
  worksheets and 400 random equations survive the round trip.
- **The equation item** (`items/calc.py`) draws with WebSMath's typesetting at
  SMath's printed size (1 px = 0.75 pt).
- **Typing** (`ui/calcedit.py`, Calc mode):
  - The red cross sits on the grid. Enter leaves the equation, with the cross
    underneath; Tab and Up/Down step through equations; Esc leaves.
  - Autocomplete and the variable/unit clash work as in SMath.
  - Clicking an equation puts the cursor there. Dragging moves it, and so does
    dragging the frame of the equation being edited.
  - One undo history covers keystrokes and the document.
  - Inside an equation, SMath's keys win (Ctrl+0 types ≥). Other Ctrl keys run
    the window's own command.
- **Grid**: SMath's dotted 9 px (6.75 pt) grid, never printed. MarkForge's
  5 mm grid and its spacing setting are removed. Equations always land on the
  grid when dropped.
- **Pages** (decision 11):
  - An equation past the bottom of its page's area moves to the next page;
    past the last page, a blank page is added.
  - Undoing it is one step.
  - On pages CalcForge creates, the area is inside the page margins (10 mm).
    On imported drawings, it is the whole sheet.
- **Too wide**: an equation that doesn't fit is broken onto more lines.
  - It breaks before the loosest operator that fits, never at `:=`, with later
    lines indented under the right-hand side.
  - This applies only while the equation isn't being typed into.
  - If it still doesn't fit, it gets an orange outline that never prints.
- **Rotated pages**:
  - Equations turn with the page and are read in the page's own direction, so
    results never change.
  - They show upright while typed into.
  - The page remembers its turn (`Page.turn`), so new equations are born
    turned.
- **Working with markups**:
  - Box select, group, align and arrow nudges (one grid step) work on
    equations and markups together.
  - Lock stops an equation being moved or opened.
  - Hide and the Print flag don't apply to equations.
  - Equations are not in the Markups list and are never PDF annotations.
  - Until phase 4 they are painted into the page on print and export.
- **Page tools**:
  - A snapshot copies equations as line work (vector outlines through MuPDF).
  - Recolour and Whiteout leave equations alone, and Flatten skips them.
  - Redaction deletes equations it fully covers and flags ones it partly
    covers.
  - Crop removes equations wholly outside the kept area and flags ones partly
    outside.
  - Redaction, crop and page deletion name the variables that became
    undefined.

**Tests**

- New:
  - `tests/test_calc_pages.py`
  - `tests/test_calc_editing.py`
  - `tests/calc/test_record.py`
  - `tests/calc/test_calcforge_window.py`, which holds 26 of WebSMath's window
    tests, ported to drive the CalcForge window with the same keystrokes and
    checks.
- Five MarkForge grid tests now use the 6.75 pt step instead of the removed
  5/10 mm spacing.
- Removed with the features they covered:
  - `test_page_coordinates_round_trip` — SMath's endless-sheet page coordinates;
    CalcForge has fixed pages.
  - `test_view_modes_keep_worksheet_positions` — SMath's None/Bounds/Pages view
    modes.
  - `test_desktop_main_window` — WebSMath's own main window and menus.
  - `test_region_options_saved_in_sm` — options saved in `.sm`. The same
    options are round-tripped in `test_record.py`.
- Moved, unchanged:
  - `test_line_block_sizes_round_trip` → `test_smfiles.py`
  - `test_placeholder_is_centred_on_the_equals_sign` → `test_calcforge_window.py`
- Still on WebSMath's old window until their phase:
  - Clipboard and right-click menu, Calculation menu, Maths panel symbols
    (phase 5).
  - Text-region selection (Calculation text, phases 3/5).
  - SMath page model and dialogs (phase 6).
  - The operator list (phase 5).

**Different from SMath**

- Pages are fixed: equations don't straddle pages and wide ones are broken
  onto more lines. SMath lets content run off onto the desk and never breaks
  equations.
- Line breaks inside a function's brackets are not done yet.
- Margins are the page's own (10 mm by default); SMath's are 37 px (9.8 mm).
- A single click on an equation puts the cursor in it, as in SMath. Dragging
  one moves it, as in Bluebeam.
