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

## Phase 3 — modes and shortcuts (2026-09-30)

**What changed**

- **Calc and Markup modes** (decision 5).
  - The mode shows in the status bar, and a click there switches it. F12 or
    Calculation ▸ Calc mode switches it too.
  - F12 is my choice of default key; it is an ordinary binding.
  - File ▸ New opens one blank A4 portrait page in Markup mode.
- **Calc mode.**
  - Typing on the page starts an equation at the red cross, or at the pointer.
  - Every tool key is off, including Shift and Alt ones: Shift+E types `E`,
    Alt+P does nothing, and 1–9 are digits rather than My Tools.
  - `"` starts Calculation text and `@` starts a plot.
  - A lone word followed by a space becomes Calculation text; one Ctrl+Z
    (after the typing) turns it back into the equation.
- **Markup mode.** MarkForge as before. `'` starts an equation at the pointer,
  and `"` makes a text box.
- **Calculation text** (`CalcTextItem`).
  - A text box type of its own, plain by default: Arial 10 pt black, no frame,
    no fill.
  - It never takes a leader and is saved as a `/FreeText` annotation.
  - Its style defaults, tool sets and spell checking come in phase 5.
- **Shortcut scopes.** Every binding says where it acts: Always, Calc mode,
  Markup mode, in an equation, or while typing.
  - A key may do two things only where both can never act at once: Calc vs
    Markup mode, or inside vs outside an equation ("editing decides").
  - The manager and the shortcuts dialog check clashes that way. The dialog
    has a new "Where" column.
- **SMath section of the shortcut manager.** Each key works inside an equation
  and can be rebound:
  - Ctrl+= ≡, Ctrl+3 ≠, Ctrl+9 ≤, Ctrl+0 ≥
  - Ctrl+\ n-th root, Ctrl+1 transpose, Ctrl+8 cross product, Ctrl+[ element
  - Ctrl+E insert function, Ctrl+K constants, Ctrl+Shift+D double-check,
    Ctrl+A select all equations
  - Also in the section: the mode switch F12, the equation start key `'`,
    Calculation text `"`, and plot `@`.
- **Calculation menu.** Calc mode, Calculate (F9), Auto-calc, Matrix (Ctrl+M),
  Function…, Constants…, Double-check. The dialogs are WebSMath's own.
- **Ctrl+B/I/U** are MarkForge's formatting keys and now bold, italicise or
  underline the equation being typed into, or the selected equations. Ctrl+B
  no longer adds a bookmark while an equation is open.
- **MarkForge's symbol keys inside an equation** type their maths meaning: π,
  ≤ ≥ ≠, √ as a real root, ² and ³ as powers, Greek letters, and ° as the unit.
- **Tests.** `tests/test_calc_modes.py` has 22 tests, all through key events
  delivered the way Qt's shortcut map delivers them.

**Keyboard clashes found beyond the brief** (all settled by "editing decides"):

- Ctrl+[ — element (SMath) vs send backward (MarkForge)
- Ctrl+= — boolean equals vs zoom in, where the keyboard maps them together
- Ctrl+K — constants; no clash
- Ctrl+M — insert matrix; no clash
- `|` — absolute value inside an equation vs start note in Markup mode
- `@` — plot in Calc mode vs callout in Markup mode
- Ctrl+E, Ctrl+Shift+D, Ctrl+A, Ctrl+0 and Ctrl+1, as listed in the brief

**Different from SMath**

- SMath's Ctrl+G (Greek) and Ctrl+W (units list) are left out, as asked.
- WebSMath only showed Ctrl+\, Ctrl+1, Ctrl+8 and Ctrl+[ in its panel tooltips;
  CalcForge binds them, as SMath desktop does.

## Phase 4 — saving and flattening

**What changed**

- **Every save writes a fresh, compact file** (decision 4). It is built in
  memory and written once, with unused objects dropped, so saving again —
  or opening and saving again — gives the same size. A page that is a page
  of the opened PDF is that PDF's page (the file is copied and its pages
  picked out, so every annotation on it survives as its author wrote it).
- **Equations are page content in a tagged layer** (decision 3). On every
  save CalcForge recalculates, then draws the equations as vector lines and
  real, embedded-font text into a content stream of their own, appended after
  the page's own content, which is never touched. MarkForge's own sheet
  drawing (header, footer, flattened markups, the paper of written pages)
  goes in the same way as a second layer. Both are tagged with a private key
  (`/CalcForge /Calc`, `/CalcForge /Sheet`) and each page carries its uid.
- **Reopening takes the layers off and rebuilds live equations** from the
  record. The page left behind is the page's source from then on, so the
  record no longer stores a second copy of the PDF (that copy was what made
  MarkForge's files grow on every save).
- **Warnings on open** — in the status bar, and in a message box:
  - the calc layer was changed in another program: CalcForge rebuilds it from
    its record, and says so;
  - pages were deleted elsewhere: their equations go, and the variables that
    became undefined are named; reordered pages carry their equations;
  - the record is missing: the file opens as a plain PDF, and says the
    calculations show but can't be edited.
- **Markups** stay ordinary annotations. Somebody else's untouched markups are
  found again after each save and stay theirs. A markup added in another
  program comes in as a markup.
- **Signed PDFs** (a `/Sig` field with a `/ByteRange`) are appended to, so the
  signature stays valid; the old calc layer is taken off and the new one put
  on in the appended part, and the status bar says why. If the pages have
  changed (added, moved, resized) the file is written afresh and the status
  bar says the signature no longer applies.
- **Extract and Split** carry their pages' equations live, and warn of
  variables the extracted equations use that are defined only on pages left
  behind. **Insert PDF** (and dropping a file on the pages panel) brings a
  CalcForge file's pages in with their equations live, in reading order.
- **Autosave** writes the same format (a PDF with the record; the layers are
  left out of recovery copies, as before, to keep autosave quick).
- **Found and fixed on the way:** the equations' layer was drawn at 200 dpi,
  which made SMath's point-sized fonts come out about a third too big and run
  into each other. It is drawn at 96 dpi now. The equation snapshot (phase 2)
  had the same fault the other way (72 dpi, letters too small) and is fixed
  too.

**Tests**

- `tests/test_calc_saving.py` (new, all through the real window): text reads
  back; the saved page renders like the screen (same ink, same places); a
  pypdf reader sees the markups as annotations and not the equations;
  reopening rebuilds live, editable equations; the drawing is not stored
  twice; repeated saves (and reopen-then-save) don't grow the file; the three
  warnings; reordered pages; a markup added elsewhere; a signed file signed
  with pyHanko stays valid after two saves, with one calc layer; a signed file
  whose pages changed is written afresh and says why; Extract, Split, Insert
  and autosave.
- MarkForge's incremental-save tests in `tests/test_format.py` are rewritten
  to the new rule: the page's own content is unchanged, the file is fresh
  (one `%%EOF`) and doesn't grow; a turned page keeps its content and its
  `/Rotate`; only a signed file takes the appending path.
- pyHanko is a new test-only dependency (signing and validating).

**Different from SMath or Bluebeam**

- Markups: the file wins (see the addendum below).
- Another reader can switch nothing off: the calc layer is page content with
  a private tag, not an optional-content layer, so it can't be hidden or
  deleted as a unit elsewhere.
- Recovery copies (autosave) hold the record and the pages but not the drawn
  layers, so opened in another reader they show no equations.

### Phase 4 addendum — the round trip (2026-09-30)

Asked for: save, open in another editor, delete pages or move markups, open
again; and a page must look the same in CalcForge and in any other reader.

**What changed**

- **For markups the file wins.** A CalcForge markup moved, restyled, retyped
  or reshaped in another editor opens as that editor left it (drawn by the
  file, exactly as they drew it), keeping its identity, lock and group. One
  deleted elsewhere is gone. Somebody else's markup changed elsewhere is read
  in afresh. Untouched markups keep everything CalcForge knows about them.
  Each annotation CalcForge writes is fingerprinted (place, shape, colours,
  words, date and its appearance drawing) so an edit is noticed.
- **A written page now has its own saved page underneath** once reopened, so
  anything another editor leaves on it shows. It still counts as written in
  CalcForge (SMath's margins) through a new `written_here` flag.
- **Deleting pages elsewhere doesn't corrupt anything:** the rest opens,
  recalculates, saves and opens again cleanly.

**Found by the testing and fixed**

- On a page that says it is turned (`/Rotate`), the equations layer (and the
  header/footer layer, a MarkForge fault too) landed at half size and off the
  sheet in other readers. The placement is now worked out from the page's own
  boxes; checked at 0/90/180/270° with and without an offset crop box.
- A markup changed elsewhere on a written page wasn't drawn in CalcForge at
  all (there was no page underneath to draw it). Fixed as above.
- A markup that was still somebody else's could be mistaken for deleted on
  the second reopen. Fixed.

**Tests** — `tests/test_roundtrip.py` (15) and `tests/fidelity.py`:

- Every page is drawn three ways — by CalcForge, by MuPDF and by pdfium
  (Chrome's and Foxit's engine) — and compared region by region: where the
  ink is, how far its edges are apart, and its colour.
- Covered: rectangle, filled ellipse, cloud, arrow, polygon, pen, text box,
  callout, stamp, length, area, dimension, count, typewriter, photo, note,
  flag, sketch, equations, Calculation text, a plot, a snapshot; dashes,
  hatch, cut-out, transparency, arrowheads, bold/italic/coloured words,
  highlight; header and footer; a flattened markup; a turned drawing; a real
  Bluebeam-marked sheet; after save, after reopen-and-save, and Export PDF.
- Edited elsewhere: moved, restyled and retyped, deleted, a callout and an
  area measurement moved, a page deleted, pages reordered, the whole file
  rewritten by another program (pypdf).
- A test plants a wrong colour and a wrong position and checks the comparison
  catches both, so the check can't pass by being blind.

### Snapshot tool made bulletproof (2026-09-30)

Asked for: whatever can be seen in the box is taken, like a screenshot, but
as line work wherever possible (always, unless there's an image); equations,
plots and Calculation text included; not live. Reported: a title block's
lines came through but not its words.

**What changed**

- **Cause of the missing words:** the snapshot skipped every text-type
  markup (text boxes, callouts, typewriter text — and so Calculation text)
  unless it was selected, an old MarkForge rule. Gone: whatever is visible
  in the box is taken.
- **How a snapshot is made now:** the page's own PDF drawing is read from the
  file as before (curves, clips, words as outlines, photos as their pixels),
  and everything drawn over it — markups whole or in part, words, equations,
  plots, Calculation text, header and footer, a picture page's picture — is
  drawn once exactly as the page draws it and kept as one piece of vector
  line work, letters as outlines. It used to rebuild copies of the markups,
  which could draw differently away from their page (a measurement without
  the page's scale, a Bluebeam markup without the file that draws it).
  Colours can still be changed.
- **Found and fixed:** PDF line ends and corners weren't carried into
  snapshots, so a PDF miter that becomes a bevel came out as a spike (a line
  drawn there and back came out longer); a selected snapshot could print or
  export with its dashed selection box, drawn from its cached picture.

**Tests** — `tests/test_snapshot_fidelity.py` (7): each snapshots a region,
pastes it at the same place on a blank page and compares the two pages as
CalcForge draws them (and, saved, as MuPDF and pdfium draw them): every kind
of markup, equations, Calculation text, a plot, a snapshot of a snapshot, a
title block (the PDF's own words and typed-on ones), a real Bluebeam sheet,
a turned drawing, a box running off the page; and a snapshot doesn't change
when the equation it was taken of does.

**Different from Bluebeam:** a snapshot's contents come through as one
drawing, not as separate markups; its colours can be changed as a whole, as
before, but not markup by markup.

## Phase 5 — toolbar, panels and properties

**What changed**

- **Calculation toolbar** beside the tools (decision 18): Calculate (F9),
  Auto-calc, Plot, Matrix, Calc text, If, For, While, Line. Each has a
  drawn icon in MarkForge's style and a tooltip. The Calculation menu has
  the same, plus a Program submenu. (The calculation block button waits for
  phase 7, where blocks are built.)
- **Maths panel on the rail** (decision 19): WebSMath's side panel one to
  one — Arithmetic, Matrices, Boolean, Functions, Plot, Programming,
  Constants — plus Units (common units and "All units…"). Sections fold
  away. Every button types into the equation, or starts one at the red
  cross, as its key would. Pinnable and floatable like every panel.
- **Equation settings** (decision 20):
  - Right-click › Equation: SMath's menu item for item (Display input
    data, Go to definition, Disable evaluation, Ignore units, Optimization,
    Decimal places, Exponential threshold, Fractions, Rounding) plus Font,
    Colour, Background and Border. For a plot: Plot settings, Grid, Axes,
    Graph by points.
  - The Properties panel has the same as Result and Equation sections.
  - A setting changes every selected equation, as one undo step, and is
    saved with the file.
- **Defaults in Preferences** › Calculations: decimals, threshold,
  trailing zeros, fractions, and the size and colour new equations are
  written in. The number format is also saved in the document, so a file
  shows its results the same on every machine; a new document takes
  Preferences'.
- **Plot mouse** (SMath's, once double-clicked into): until then a plot is
  a markup — one click picks it up, dragging moves it, the wheel scrolls
  the page. Double-clicked into (or just made): dragging inside pans the
  graph (or zooms it with the Maths panel's Scale tool), the corner resizes
  it, the wheel zooms it (Ctrl: x only, Shift: y only), until a click
  outside or Esc.
- **Calculation text** snaps to the equations' grid when moved or nudged,
  and is spell-checked like any text (live, and in the F7 check); equations
  are not.
- **Search** finds equations by what was typed (`Mu:` finds the
  definition) and by the result they show. Replace never changes an
  equation.
- **Copying out** (decision 26): a copy now puts three things on the
  clipboard — plain text ("Mu = 40.5 kN·m", "sp := 6 m"), a picture at
  print resolution, and CalcForge's own copy under its own clipboard type,
  which pastes as live equations here and in another CalcForge window.
  Other markups copy as their words, or what they are. (Before, pasting
  into another program gave CalcForge's internal data as text.)
- **Found and fixed:** Go to definition didn't work with the cursor after a
  number (WebSMath's gap too). Preferences didn't keep the page-thumbnail
  size through a save of the dialog.

**Tests** — `tests/test_calc_panels.py` (35), all through the real window:
toolbar buttons clicked, Maths panel buttons clicked, right-click menu
actions and undo, the Properties panel, Preferences (and that a document's
format travels with it), plot pan/zoom/axis-zoom/resize/click vs
double-click, Calculation text grid and spelling, Search, copy out and
paste back live.

**Different from SMath**

- The Maths panel has a Units section; SMath desktop's unit list is a
  dialog (Ctrl+W, left out as asked).
- Font and colour are on the Equation menu; SMath has them on its Format
  toolbar.
- Replace in Search never changes an equation.

## Phase 6 — header/footer and file properties

**What changed**

- **SMath's fields in MarkForge's header and footer** (decision 27): the six
  slots, logo and page ranges as before, and every field of SMath's Insert
  › Field — `{company}`, `{description}`, `{keywords}`, `{revision}`,
  `{id}`, `{filename}` beside MarkForge's `{title}`, `{project}`,
  `{author}`, `{subject}`, `{page}`, `{pages}`, `{date}`, `{time}`,
  `{file}` — with SMath's formats after a colon: `{date:DD.MM.YYYY}`,
  `{time:hh:mm tt}`, `{page:0000}` (SMath's own offset-and-pad rule),
  `{page:-1}`. An "Insert field…" button puts one into the slot you were
  typing in.
- **One File › Properties** (decision 28): title, project, author, subject
  (MarkForge) and company, keywords, description, revision (SMath) in one
  tab. Title, author, subject and keywords also go into the PDF's own
  properties — on save, on a signed file's appended save, and on Export
  PDF. The rest stay in CalcForge's record. As in SMath, a document gets
  an id on its first save and every save is a new revision (recovery copies
  aren't).
- **SMath's page extras removed** (the Separator/Picture/Background
  clarification): SMath's page model — paper, margins, background picture,
  header and footer layers of regions — is gone from the app; MarkForge's
  page setup, images and Header/Footer dialog are what CalcForge has.
  `calc/page.py` keeps only SMath's field functions. The test-only `.sm`
  reader keeps its own copy of the page model, since SMath's example files
  carry one. (Areas stay until phase 7, where calculation blocks replace
  them.)
- **WebSMath's old window removed** (`tests/calc/legacy_ui/`). Things only
  it could do came across first: WebSMath's Calculation menu on the
  selected part of an equation (Solve, Calculate selection, Invert,
  Determinant — CalcForge's Calculation › Selection), Insert › Operator
  (Calculation › Operator…), and copying and pasting part of an equation.

**Tests**

- `tests/test_properties_fields.py` (9): fields and SMath's formats, the
  header printing its fields in the saved PDF, id and revision through
  saves, the PDF's own properties (read back with pypdf and MuPDF), the
  merged dialog and Insert field.
- `tests/calc/test_same_drawing.py` no longer needs WebSMath's window: it
  checks the drawing code's SHA-256 against WebSMath's commit, the
  equations and results the same keystrokes made in WebSMath's window
  (recorded before it went), and that a CalcForge page draws WebSMath's
  drawing pixel for pixel.

**Tests removed with withdrawn features, by name**

- `tests/calc/test_ui.py` (WebSMath's window). Ported to the CalcForge
  window in `tests/calc/test_calcforge_window.py`, same keystrokes and
  checks: `test_copy_paste_regions`, `test_copy_paste_inside_equation`,
  `test_calculation_menu_commands`, `test_context_menu_items_match_site`,
  `test_context_menu_options_match_site` (all 11 cases),
  `test_context_menu_fractions_and_mixed`,
  `test_default_rounding_is_half_to_even_on_the_binary_value`,
  `test_display_input_and_disable_evaluation`, `test_calculation_solve`,
  and `test_side_panel_symbols_are_visible_and_insert` (as
  `test_side_panel_symbols_insert`). Removed: `test_format_and_areas`
  (separators, SMath text regions and `.sm` saving are withdrawn; areas
  come back as calculation blocks in phase 7) and
  `test_text_region_selection` (SMath text regions are replaced by
  Calculation text, which is MarkForge's text box).
- `tests/calc/test_files_and_operators.py::test_insert_operator_list_and_formula`
  — ported to the CalcForge window.
- `tests/calc/test_page_model.py` (SMath's page model).
  `test_definition_with_equals_shows_its_value` (maths) moved to
  `tests/calc/test_smfiles.py`; `test_fields`,
  `test_field_formats_as_smaths_insert_field_dialog` and
  `test_identity_is_kept_and_each_save_is_a_revision` ported to
  `tests/test_properties_fields.py`. Removed with the page model:
  `test_page_model_header_pictures_and_rich_text_load`,
  `test_save_round_trip_keeps_everything`,
  `test_pages_follow_the_file_and_print_like_smath`,
  `test_pictures_are_selected_not_typed_into`,
  `test_edit_header_layer_insert_field_and_leave`,
  `test_page_text_only_without_layers`, `test_background_sizes`,
  `test_page_dialogs_apply`.
- No maths, units, recalculation or editor test was removed.

**Different from SMath**

- Header and footer are MarkForge's six text slots with a logo, not layers
  of regions: a title-block picture goes in as a logo, or as an image
  markup.
- (Not a difference, but worth knowing: a page-number format is SMath's —
  an offset plus zero-padding — so `{page:0000}` shows page 1 as 0001 and
  `{page:0001}` shows it as 0002, exactly as SMath's Insert › Field does.)

## Phase 7 — blocks, tool sets, Variables panel, measurement variables

**What changed**

- **Calculation block** — a markup type of its own (Calculation toolbar and
  menu › Block). It wraps the selected equations, or starts empty at the red
  cross. The equations and Calculation text whose top-left is inside it are
  its members: they calculate exactly as they did, and move (drag or arrow
  keys), copy, duplicate and delete with the block. It is picked by its thin
  frame only, so a click inside still starts an equation there. Like an
  equation it is page drawing when saved, never an annotation, and always
  prints.
- **Self-contained** (decision 10), on the block's right-click menu and in
  Properties: what the block's equations define stays inside it. The block
  still reads everything defined above it; after it, the names mean what
  they meant before it. Editing above the block updates inside it; moving an
  equation in or out recalculates. The screen shows "Self-contained" over
  the block (never printed). Done at the worksheet with a scoped index per
  block (`Worksheet.scope_of`, `ScopedContext`); a sheet with no
  self-contained block calculates exactly as before.
- **Tool sets and My Tools** (decision 23): an equation kept in a set shows
  its own drawing on its row and while held, then calculates where it is put
  down, on SMath's grid, as if typed there. A block is kept with its
  equations as one tool and comes back with them (not as a markup group).
- **Variables panel** on the rail (decision 21): every name defined, in
  reading order, with value, unit, page ("· block" when inside a
  self-contained one) and its error in red; functions listed as `f(·)`. A
  filter box finds a name; clicking a row goes to the equation (or
  measurement) and selects it. It follows each calculation.
- **Measurement variables** (decision 24): Properties › Variable, or
  right-click › Variable name…. The measurement defines the name as SMath
  would if you typed it (`L_b:0.03528'm`, in the measurement's own unit, to
  full precision) at the top-left of its box, so equations below it see it
  and equations above don't. It follows the measurement live — stretch it
  and the results change; move it below an equation and that equation loses
  it. Its label reads "L_b = 0.04 m". Deleting it says which names are no
  longer defined (and asks first). The name is saved with it.
- **SMath areas are gone from the app** (promised in phase 6):
  `Worksheet.add_special` moved into the test-only `.sm` reader, which
  still reads SMath's example files. The region fields remain only because
  WebSMath's drawing code, kept byte for byte, reads them.

**Tests**

- `tests/calc/test_block_scope.py` (5): Self-contained at the worksheet —
  shared without it; reads above, keeps its own; editing above updates
  inside; two blocks don't see each other; moving out recalculates.
- `tests/test_calc_blocks.py` (11), through the window: Block wraps the
  selection; right-click and Properties toggle Self-contained with undo;
  editing above; drag and arrow keys move members; a click inside starts an
  equation; delete and undo; duplicate; saved as page drawing (not an
  annotation) and reopened with its setting; snapshot as line work.
- `tests/test_calc_toolsets.py` (3): an equation's row picture and held
  size; placed below/above its definition; a block tool.
- `tests/test_variables_panel.py` (6): on the rail; value, unit, page,
  function, red error; follows edits; block marker; click goes to it;
  filter.
- `tests/test_measure_variables.py` (7): exact values below it, undefined
  above; live when stretched; moved below an equation; Properties field and
  a rejected name; in the Variables panel; delete message and undo; saved.
- No test removed.

**Different from SMath**

- No SMath areas: calculation blocks instead. They can't be collapsed, and
  Self-contained is new (SMath has nothing like it).
- Blocks inside blocks: an equation belongs to the innermost
  self-contained block only, and doesn't also read the outer block's names.
- A variable whose name is also a unit (`a` is the are) asks which one is
  meant when typed, exactly as SMath does — the Variables panel lists it
  either way.

## Phase 8 — rename and settings migration

**What changed**

- **`markforge/` is now `calcforge/`**, with every import, the `calcforge`
  launch command, the `pyproject` name and description, the window title,
  About box, PDF Creator, printer document name and messages, the
  clipboard and drag types (`application/x-calcforge-…`), temporary-file
  names and the environment overrides (`CALCFORGE_SETTINGS_FILE`,
  `CALCFORGE_PDF_WORKERS`, …). Comments that say where something came from
  ("MarkForge's grid") still say MarkForge.
- **Settings** are CalcForge's own (`QSettings("CalcForge", "CalcForge")`).
  On first start, before anything reads them, MarkForge's are copied across
  once: shortcuts, tool sets (My Tools is one), toolbar, panel and window
  layout, dark mode, markup defaults. Anything CalcForge already has wins,
  and nothing else comes across (not the spelling dictionary, preferences
  or recent files). `migration/from_markforge` records that it happened.
- **Files are unchanged.** The record is still `markups.json.zip`, so a PDF
  saved by MarkForge opens in CalcForge exactly as before.
- **README and HANDOVER** describe CalcForge: the calculations, what a
  saved file is now (fresh compact saves, calculations as a tagged page
  layer, signed files appended to), the `calc/` package and the new
  modules.

**Tests**

- `tests/test_settings_migration.py` (6): exactly the six kinds of setting
  come across; once only; CalcForge's own kept; no MarkForge settings is
  fine; a new window starts with the migrated shortcut, dark theme and My
  Tools; the names are CalcForge's.
- The suite points both settings stores at its sandbox, so no run reads
  anybody's real MarkForge settings.
- No test removed. The WebSMath drawing code's SHA-256 still matches: the
  rename didn't touch it.

**Different from SMath and Bluebeam** — nothing new in this phase.

## After phase 8 — the user's bug list (2026-09-30 and 2026-10-01)

**Fixed**

- **`=` couldn't be typed.** A name that is also a unit (t, m, s, g, A,
  h, L…) blocked every key after it — `=`, `:`, operators — until the
  variable or the unit was picked from the list (WebSMath, after SMath
  Cloud). The variable defined on the sheet now wins and typing carries
  on; the unit is `'m` as SMath writes units.
- **`t:=test+1=`** — a definition can show its value, as SMath Studio
  desktop does (the worksheet already could; the editor refused the `=`).
- **Autocomplete list in the wrong place**: it was offset by the
  equation's whole position on the page. It now opens under the caret and
  follows the page when it scrolls.
- **Red and blue crosses together**: in Calc mode the red cross is the only
  insertion marker.
- **Caret while typing a unit**: briefly changed (a pixel to the right,
  blue in units), then put back to WebSMath's own caret when the user asked
  for CalcForge to match WebSMath exactly (2026-10-01).
- **Calculation blocks are pages of their own**: an equation can't be
  dragged out of its block (it stops at the edge) or into one (it goes
  back); a block can't be moved or resized over equations that aren't its
  own, or shrunk off its own. Typed or pasted inside, an equation belongs.
  Right-click: Select its equations, Remove block (keep equations); in
  Properties, a Calculation block section (what it holds, Self-contained,
  Remove). Making one over more than was selected says what else it took.
- **Measurement variables** use SMath's names: `L.beam` (typing `L_beam`
  gives `L.beam`), drawn with the subscript on the measurement. Right-click
  any measurement (area included): Variable… first, and Show in Variables.
- **Markup | Calc** is a switch at the end of the top toolbar, the mode on
  lit in the accent colour (it was a word in the status bar).
- **Toolbars** go top or bottom only — dropped at a side they ended up in
  the panel rails; an old saved layout with one there is put right.
- **Panels flex with their width**: the Maths panel reflows (more buttons
  to a row when wide, every row filled); Bookmarks' buttons and Search's
  options wrap; Search's and Variables' columns share the width; Page setup's
  two size boxes share the row.
- **Style bar** stays put (it came and went, moving the page); with nothing
  to style its controls are greyed. **Fill %** sits by the fill colour,
  **Hatch %** (new: the hatch on its own) by the hatch, **Overall %** (line,
  fill and hatch together) last; changing the hatch's no longer fades the
  fill. Properties says the same.
- **Page number** is centred under the page view, following panels as they
  open and close (as close as the status bar's controls allow).
- **Equations** have no markup pen in Properties or on the style bar; their
  menu leaves out Set default, Format painter, Hide, Flatten, Apply pages.
- **Page thumbnails** show the markups and calculations (a reopened page's
  was blank) and are no longer washed blue when current.
- **`calcforge drawing.pdf`** opens the file again (`main()` called a
  method that no longer existed).
- **Dark theme checkboxes** were invisible when unticked; both themes now
  draw the box, filled with the accent and a tick when on.

**Tests**: `tests/test_ui_fixes.py`, `tests/test_real_session.py` (the
whole session above, checked at every stage), `tests/test_smath_examples_in_window.py`
(SMath's example files on a CalcForge page give the results SMath saved:
all 36 numeric results it stores, 15 of them quantities), additions to
`test_calc_blocks.py`, `test_measure_variables.py`, `test_layout.py`,
`test_settings_migration.py`. Rewritten to the new rules (the old ones
recorded the behaviour asked to change):
`test_variable_unit_clash_needs_a_choice` →
`test_a_variable_named_like_a_unit_is_the_variable`,
`test_the_style_toolbar_goes_when_it_has_nothing_to_offer` →
`test_the_style_toolbar_stays_put`, `test_the_toolbars_can_be_moved_to_any_edge`
→ `test_toolbars_move_between_top_and_bottom_never_onto_the_rails`.

**Different from SMath**: a variable named like a unit is the variable
without asking (SMath Cloud asks); SMath can't run here, so its behaviour is
checked against its saved files and WebSMath's recordings of SMath Cloud.
- **The properties toolbar works per markup type, as Bluebeam's does**
  (2026-10-01): it starts with the type it is setting (Cloud, Text box,
  Area… or "New cloud" with a tool in hand) and shows that type's own
  controls, in Bluebeam's order — the font first for anything with words in
  it, the line and fill first for shapes. New on it: **Arc** (a cloud's arc
  size — there was no control for it anywhere), **Radius** (a rectangle's
  corners) and **Symbol** (a count's); each also sets what the next one is
  drawn with. A highlight shows only its colour and opacities, a
  highlighter pen its colour, width and opacity, an area no arrowheads, a
  count no dashes or hatch. The toolbar and Properties still offer exactly
  the same settings for every tool (the existing check), and Properties
  gained Arc size too.
- **Compared with WebSMath itself** (2026-10-01): WebSMath's window (its
  branch at 8b340fa, run read-only from a scratch checkout) and CalcForge's
  were given the same keystrokes — sums, definitions with units, the
  result's unit box, undefined names, fractions, roots, powers, functions,
  unit arithmetic, mismatched units, autocomplete, editing in the middle —
  and every step compared: the equation's text, unit box, result, error,
  the caret's place and the suggestion list, and the drawing pixel for
  pixel at 4×, caret and colours included. All the same, but for one
  deliberate difference: a name that is also a unit no longer blocks the
  next key (`a*a=` after `a:5`). On screen at 1 SMath pixel = 1 screen
  pixel they match too; the page around them differs (WebSMath's sheet has
  SMath's line grid, CalcForge's page its margins and grid switch).
  `tests/calc/test_websmath_reference.py` keeps WebSMath's reference
  (tests/calc/data/websmath_reference) and checks CalcForge against it on
  every run.
