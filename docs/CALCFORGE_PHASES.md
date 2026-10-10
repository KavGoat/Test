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
  keys), copy, duplicate and delete with the block. Since 2026-10-01 it behaves
  like a text box: one click anywhere on it picks it up, and a double-click
  opens it to edit what is inside (see "After phase 8"). Like an
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
  editing above; drag and arrow keys move members; typing inside an opened
  block starts an equation in it; delete and undo; duplicate; saved as page drawing (not an
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
- **Unit box: no white box round it** (2026-10-01): typing into an empty
  unit box, WebSMath's caret line ran 1–2 px into the black square, which
  showed as a sliver of white between two black edges. On an empty slot the
  caret now stands just clear of its square. That is the one place it is
  drawn differently from WebSMath (the reference test records it).
- **WebSMath's mouse pointer** (2026-10-01): over an equation, the arrow
  (typing or not, over a plot too) and, along the 4-pixel band of its frame
  that drags it, SMath's own move cursor (WebSMath's `move.cur`, at any
  zoom); the same move cursor while an equation is being dragged.
- **A calculation block works like a text box** (2026-10-01): closed, it is
  one thing — a click anywhere on it, its equations included, selects it,
  a drag moves it with everything in it (by whole grid steps, so the
  equations keep their places), right-click gives the block's menu. A
  double-click opens it: a dashed blue frame shows it is open (on the
  screen only, never printed or saved), the double-click lands where it was
  pointed (the caret in that equation, or the red cross on the page inside
  it), and clicks inside edit, type and select its equations as anywhere
  else. A click outside it or Esc closes it. A block just made is closed
  and selected. *Different from Bluebeam*: a Bluebeam text box opens on a
  double-click the same way; Bluebeam has no block of equations.
- **A PDF opens exactly as written** (2026-10-01): its markups are drawn by
  the file itself, untouched, and opening it is not a change (no "save
  changes?" on closing an untouched file — it used to count as modified).
  Picking a markup out — a click, a box selection, the properties and
  style bar showing it — no longer takes it over (it did, the moment it was
  selected). It becomes CalcForge's only when it is actually changed:
  moved, resized, nudged, restyled, or typed into. A click that trembles a
  pixel is not a move. Undoing the change gives it back to the file — drawn
  as written again, and saved as the very annotation it was. A text box
  double-clicked into is drawn here while it is open, and given back to the
  file if it is closed without a change. Checked on Bluebeam's own drawing
  (btx/Document1.pdf): every markup clicked and shown in Properties, all
  still the file's, nothing to undo or save; the screen is identical pixel
  for pixel after picking one out and letting go.
- **Bluebeam PDFs fast and true to their look** (2026-10-01, Calcs.pdf).
  The page is rendered without its markups; each markup nobody has
  changed draws its file's own appearance (its annotation alone, from tiles
  the render processes make, at its place in the stacking order). So
  taking one over, or undoing that, never re-renders or blanks the page —
  before, every take-over threw away every tile of the page. Dragging:
  clouds' and call-outs' geometry is cached (Qt asks for a markup's box
  thousands of times a frame), snapping is gathered once per drag and
  vectorised, and Properties is rebuilt when the button comes up rather
  than before the drag can start (a drag step on a busy sheet: 72 → ~34 ms
  with a full repaint each step; press 217 → ~78 ms). Edited, a Bluebeam
  markup keeps its look: pictures (/IT /SquareImage) keep their image at
  its own resolution, highlighters multiply (/BM), call-outs with no
  border keep a 1 pt leader, lines indented with spaces keep the indent,
  words wrap where Bluebeam wraps them (Qt keeps a point for the caret),
  multi-stroke ink is drawn once and saved once. A page 0.00000001 off its
  own size no longer had all its markups converted on opening.
- **Crash after pages are rebuilt** (PowerShell log): the red cross and the
  equation being typed in forget a deleted page instead of failing on every
  repaint.
- **Edit mode as WebSMath** (2026-10-01): the result's unit box shows after
  the automatic unit while editing (the earlier "unit box in its place"
  change is withdrawn); Esc only closes the suggestion list — a click
  elsewhere or Enter leaves the equation (a double-clicked plot still
  closes on Esc). Twelve edit-mode sequences — reopening a result, editing
  a definition's number and unit, Home/End, fraction navigation, Delete,
  Tab into the unit box, errors — are recorded from WebSMath and checked
  on every test run; identical but for the empty-slot caret.
- **Smaller fixes** (2026-10-01): the autocomplete list is sized to what it
  shows; a measurement's variable is typed in a box at the top of its
  right-click menu; its subscript is the label's font at 72% (a fixed 7 pt
  fallback blew up in the saved PDF — "beam" towering over its L in
  Bluebeam); scaling a group stretches a measurement by its points, so its
  value (and variable) update; Markup | Calc is one switch on the menu bar
  after Help, not in a toolbar or the Calculation menu (F12 as before);
  the style bar's line and hatch samples are drawn in the theme's ink and
  its number boxes are as wide as their longest value; an equation in a
  block stops at the block's edge while it is dragged.
- **Smooth scrolling and panning** (2026-10-01). A wheel notch glides over
  a few frames instead of jumping 30 px; a quick spin is one continuous
  movement, and the scroll bar or a key takes over at once. A pan step is
  one scroll, not two (across and down separately made Qt repaint a third
  of the window on every step instead of shifting it). Tiles are put into
  the screen's pixel format on the render thread — converting them on the
  window's thread was a 10 ms freeze per tile, the stutter felt while
  scrolling — and pages render most of a screen ahead up and down on the
  spare cores. The pointer's position in the status bar is updated at most
  every 30 ms. Measured on a 30-sheet A1 drawing at 60 frames a second:
  0–1 frames over 16 ms in 2,800 at 100% scaling; a pan step repaints 0.6%
  of the window.
- **Line and hatch pickers as Bluebeam's** (2026-10-01): closed, they show
  only the sample, filling the box (104 px, was ~170 with the name and room
  beside it); the name is the tooltip; the open list keeps every pattern
  big with its name, on the list's own background so the theme's ink shows
  in dark mode too.
- **A PDF looks as its file says, everywhere** (2026-10-01, the user's
  photo and video of Calcs.pdf on a Mac). The file's drawing of each
  untouched markup is laid in the box the file gives it (/Rect), not the
  box CalcForge measures: a Bluebeam dimension's "1m", out at the end of
  its leader, had been cut away. Annotations are hidden from the page's
  render by writing the flag into their dictionary: PyMuPDF's set_flags
  had MuPDF build a new appearance its own way — the likely source of the
  solid blue call-outs in the video. An ink annotation in several strokes
  is drawn, while all of them are untouched, by the page as its file says
  (it had been drawn by CalcForge from the moment it opened); changing one
  stroke hands all of them over. On the graphics card, an untouched
  highlighter (which multiplies, which OpenGL cannot) is drawn by the
  page's own render. On Calcs.pdf nothing at all is drawn by CalcForge on
  opening. Checked against MuPDF's
  render of every page of Calcs.pdf: with a pixel of slack, only
  anti-aliasing specks differ.
- **Groups carry their call-outs' leaders** (the user's video): moved with
  others, a call-out's arrow moves too; on its own it still keeps pointing
  where it pointed.
- **Mac: the Markup | Calc switch and search show.** The window keeps its
  own menu bar on macOS too; on the Mac's system bar Qt cannot show them.
- **Drawing with the graphics card** (Preferences, on by default): the
  canvas is drawn with OpenGL, so a scroll on a Retina screen is no longer
  millions of pixels moved by the processor each step. Falls back where
  there is no OpenGL. On the graphics card a highlighter CalcForge draws is
  translucent (OpenGL cannot multiply). Scrolling also no longer strokes
  every dash of the margin and the page edge on each step, only the part
  scrolled into view, and a trackpad scroll is one scroll, not two.
- **Zooming without repainting** (2026-10-02, the user on Windows). A wheel
  notch of zoom glides over a few frames about the point under the pointer
  instead of jumping a fifth. While a zoom moves nothing new is drawn: what
  is already drawn stands in, scaled, and the zoom it stops at is asked for
  140 ms after the last notch (every notch used to start a screenful of
  renders nobody would see, and each frame drew what arrived of them).
  What stands in is the nearest zoom that covers the screen, not every
  zoom passed through stacked — on Calcs.pdf a zoom had drawn 31,000
  pictures; frames went from 100–900 ms to 6–15 ms. The cache keeps an
  index by page and zoom, so finding stand-ins no longer searches every
  tile for every markup. When the zoom has stopped, the screen goes sharp
  in one go when its last square is in, not square by square over a
  blurred page. The page's small picture, and a preview of each of its
  Bluebeam markups, are made ahead for the pages either side, so a page or
  picture zoomed or scrolled into view is never blank first. Measured with
  screenshots taken mid-zoom against the same view settled: at most 0.4%
  of the pixels short (was 3.5%, whole pictures missing).
  No sharpening after a zoom in (the user: "Bluebeam handles it much
  better"): once the screen is sharp and the render processes are idle,
  what is on screen — page and markups — is also drawn at twice the zoom.
  A zoom in of up to 2× then shrinks that sharper drawing instead of
  stretching a softer one (measured: 1.17× the resolution needed, where it
  was 0.58×), so when the exact zoom arrives nothing visibly changes.
- **A thousand markups on a sheet** (2026-10-05). Each page's markups
  nobody is touching are drawn once into squares (256 px) and shown from
  them, as the PDF is: a frame of a scroll, pan or zoom is pictures moved,
  however many markups there are, and on the graphics card those pictures
  are textures. The markups stay real items — clicked, hovered, snapped to,
  selected (the page draws the handles over the squares) — they are only
  not painted one by one. Anything being drawn, typed into, dragged or
  changed is drawn live and goes back into the squares 0.4 s after it
  stops; a markup leaving or joining them patches just its own part of the
  squares (its neighbours drawn again into that patch), so picking one up
  off a crowded sheet costs a millisecond or two. Squares are drawn while
  the hand is still — never between the frames of a movement — nearest the
  middle of the screen first, then most of a screen above and below. While a
  zoom moves, the squares of the zoom before stand in. Highlighters (which
  multiply into the page) and equations are always drawn live. Print,
  export and snapshots draw every markup itself. Also: the markups list is
  rebuilt once a burst of changes is over, not once per markup (adding a
  thousand: 43 s → 1 s); its columns size from a sample of rows; page
  thumbnails are cached until a markup on the page changes and drawn again
  after edits stop; add-page's undo record reuses the pages that did not
  change; pens and clouds are worked out once. Measured on a 30-sheet A1 set
  with 1,000 markups on sheet 1, processor drawing: frames scrolling 1.5 ms
  (was 13), panning 2 ms (was 21), zooming 3–5 ms (was 70–110), dragging a
  markup 2 ms; adding a page 0.2–0.3 s (was 0.9 s). The squares match the
  markups drawn live pixel for pixel at 100% and 200% scaling; at 125% and
  150% they can sit up to half a pixel off, which moves anti-aliasing only.
  Markups still drawn by their own file stay drawn that way (their own
  squares from the render processes). A page carrying more than 120 of them
  (a crowded Bluebeam sheet) has the file draw them with the page, in the
  page's own squares, on every core: a PDF with 1,000 annotations on a sheet
  went from 45–60 ms a frame to 1.5–5 ms. Taking one of those over leaves
  the page's squares as they were, standing in, while the page is drawn
  again without it, and the patch where it was is drawn straight away — no
  ghost, no blank page. Hiding an annotation from the page's drawing now
  goes by its number (it walked every annotation on the page: over a second
  on such a sheet). Pages exported or printed one at a time leave the pages
  either side out of the drawing. A contents block knows its rows before it
  is first painted.
- **Dragging pages in the Pages panel** (2026-10-05): a small white,
  slightly see-through sheet beside the pointer (a little stack with the
  count when several are picked out), an ordinary move cursor along the
  strip instead of Qt's no-entry cross, the blue line where they will land,
  and the strip scrolls when the pointer nears its top or bottom. Fixed on
  the way: a drag passed the count where the target belonged, so pages could
  land in the wrong place. Pages picked out here and there gather into a run
  where they are dropped.
- **The Mac's own menu bar again** (2026-10-08): on a Mac the menus are in
  the Mac's bar at the top of the screen; the window's own bar, with the
  Markup | Calc switch and the search box after Help, is Windows (and
  Linux) only. On a Mac, F12 switches modes.
- **Sharp while zooming** (2026-10-08). A notch of the wheel knows where the
  zoom is going: the page there is drawn straight away on every core, while
  the zoom is still gliding, rather than after it stops — what arrives
  stands in, shrunk and so sharp, and is the page itself when the zoom
  lands (sharp 0.1–0.17 s after the last notch on a 30-sheet A1 set, was
  0.45 s, and mostly sharp throughout). What is on screen at twice the zoom
  is asked for as soon as what is on screen is sharp, ahead of the squares
  off screen. Markups whose squares at a new zoom are not drawn yet are
  drawn as they are — sharp — when there are up to 150 of them on screen.
- **Faster frames** (2026-10-08): a markup still its file's keeps its size
  instead of working it out each time Qt asks (several times a frame for
  every markup on the canvas); the previews of the pages round the one on
  screen are asked for once, not on every repaint; a page drawn for export
  or a thumbnail leaves the others out by making them see-through rather
  than hiding them, which had every markup on them told it was hidden and
  drawn again. Calcs.pdf scrolling 6.9 → 2.2 ms a frame; adding a page next
  to a sheet of a thousand markups 0.5 → 0.2 s.


## Spreadsheets, phase 1 — engine and formulas (2026-10-09)

Written from scratch in `calcforge/sheet/` (no Qt; design and every decision
in `docs/SPREADSHEET_DESIGN.md`):

* Excel formulas: references (`A1`, `$B$7`, `A:A`, `3:5`, `'Loads 2'!B4`),
  operators with Excel's precedence (`-2^2` = 4), `%`, `&`, arrays
  `{1,2;3,4}`, omitted arguments, defined names, `_xlfn.` prefixes; units
  after numbers (`=10 kN/m*B2`) and `'kN`; document variables by name or
  `var(M20)`.
* About 260 Excel functions (maths, statistics, logic, lookup incl.
  XLOOKUP/INDEX/OFFSET/INDIRECT, text, dates, dynamic arrays
  FILTER/SORT/UNIQUE/SEQUENCE, money, matrices, LET/LAMBDA — called at once, by LET or as a defined name — with MAP, BYROW,
  BYCOL, REDUCE, SCAN and MAKEARRAY), all keeping units;
  CalcForge's own VALUEIN, CONVERT(x,"kN"), INTERP, UNITOF, STRIPUNIT.
* Typed entries as Excel reads them (numbers, 12%, $1,200, dates, times,
  fractions, TRUE, errors, `'text`) plus quantities (`5 kN`, `2.5 kN/m^2`).
* Excel number formats (sections, colours, conditions, dates and times,
  elapsed time, fractions, scientific, thousands scaling, text sections).
* A workbook of sheets and tables: dependency-ordered recalculation of only
  what changed, circular references, volatile functions, insert/delete
  rows and columns with Excel's reference rules, copy (relative references
  follow), Paste Special values/formats/formulas, cut-and-move (readers
  follow), rename (formulas follow), defined names, undo/redo of whole steps.
* Found and settled while building: Excel's own `VAR` (variance) clashes with
  `var(M20)`; one bare cell-like name or bare name is the document variable,
  anything else is Excel's VAR (see the design doc).

Tests: `tests/sheet/` (311: 230 formulas against Excel's answers, the
workbook's rules, parsing, formats, speed — one edit in a 15,000-formula
sheet under 0.1 s).

## Spreadsheets, phase 2 — tables on pages (2026-10-09)

The user's answers for this phase (pop-up questions): new tables have thin
borders on every cell, printed; Excel's Calibri 11 and 64 × 20 px cells; a
table behaves as sheet pages will (Markup mode: a markup, double-click for
its cells; Calc mode: clicks and typing go to the cells); dragging its edge
adds or removes rows and columns.

* **Insert Table** (Calculation bar, Calculation menu, Annotate tools): drag
  a rectangle — the grid and "rows × columns" follow the drag; a click gives
  4 × 3.
* **Cells as in Excel:** typing, F2, Enter/Tab/arrows/Ctrl+arrows/Home/End,
  Shift to extend, headings and corner to select rows, columns, all; the
  name box and formula bar over the canvas; references coloured on their
  cells while a formula is typed; point mode (click or arrow to a cell, also
  in another table, which is then named); F4; Ctrl+Enter; Alt+= AutoSum;
  Ctrl+D/R; Ctrl+; date; Delete/Backspace; Ctrl+B/I/U/5; Ctrl+1.
* **Fill handle** with Excel's series; **drag the selection's border** to move
  cells (Ctrl copies; readers follow a move); **cut/copy/paste** inside
  CalcForge and with Excel (its XML Spreadsheet: formulas, number formats,
  fonts, fills, borders, merges, column widths), HTML and text; Paste Special
  values/formulas/formats; a block pasted into a multiple of its size repeats.
* **Rows and columns:** drag heading borders (all selected ones together),
  double-click to AutoFit, insert/delete/hide/unhide, Distribute Rows/Columns
  Evenly (selected ones, or all), row height/column width by number; the
  table's corner or edge adds and removes rows and columns.
* **Formatting:** the properties toolbar shows the table's controls while it is
  open (font, size, B/I/U, colours, alignment, wrap, merge, borders, number
  format, fewer/more decimals, display unit, rows & columns, Format Painter,
  Format…); Format Cells dialog; merge & center/across/unmerge.
* **Names:** auto Table1, Table2…; renamed from the name tab (double-click),
  the right-click menu, or the Properties panel; every formula that reads it
  follows. Define Name for a cell or block.
* **Equations ↔ tables** (see the design doc): `Loads.D12`, `W_total`,
  `Loads.Load` (column vector), `bolts(d, "A")` (interpolating lookup); a
  table reads variables defined before it; dependencies win over reading
  order; a table that appears, goes or is renamed recalculates the equations.
* **Saving:** a table is page drawing on the calc layer (real text, never an
  annotation), with its cells, formats, sizes, merges and names in the record;
  it prints without the on-screen headings and tab.

Found and fixed while building: Qt crashed when a table recalculated in the
middle of an equation being put on its page — tables and equations now take
up each other's changes on the next turn of the event loop.

Not yet (phase 3): conditional formatting, sort/filter, data validation,
cell comments, find/replace.

Tests: `tests/test_tables.py` (32, the real window), `tests/test_table_equations.py`
(4), `tests/sheet/test_clip.py` (4, Excel's clipboard).

## Conditional formatting of equations (2026-10-09)

The user: "add a conditional formatting to smath equation … based on the
final number, like for dcr I can do more than 1 is red etc, less than 1 is
green". Their answers (pop-up questions): size and background only (what
WebSMath's drawing shows on maths — the drawing stays byte for byte); the
whole equation; rules per equation, as presets, and document-wide by
variable name; only results without units are compared.

* Right-click an equation ▸ Equation ▸ **Conditional Formatting…**: no rules
  of its own, a preset, or its own rules (greater/less than, equal, between,
  not between; a font size and/or background each; a "DCR: > 1 red, ≤ 1
  green" button); Save these rules as a preset.
* Calculation ▸ **Conditional Formatting…**: the document's presets, and
  name patterns that use them (`DCR*` → DCR) for every equation without
  rules of its own.
* The number is what the equation shows (`DCR=`), or what it defines
  (`DCR:=M/Mc`). Every rule that matches applies; the higher one wins where
  two set the same thing.
* The equation's own size and background are never changed: the rule's look
  is put on only while it is laid out and drawn, so it prints and exports as
  seen, the record keeps the equation's own look, and the menus still set it.
  Rules travel with an equation (copy, paste, tool sets, undo); presets and
  name rules are saved with the document.

Found while checking: the equation menu's Colour, Bold and Underline have
never shown on maths — WebSMath draws maths black and regular. Left as they
are for the user to decide.

Tests: `tests/test_equation_rules.py` (6).

## Spreadsheets, phase 3 — conditional formatting and data tools (2026-10-09)

Open points from phase 2, answered by the user: lookups kept as built;
column lists are `Loads.Load`; a typed number widens a never-sized column
(else ####); **equations' Colour, Bold and Underline now show on maths** —
the user let WebSMath's drawing change for this (`calc/ui/layout.py` and
`region_item.py` differ from WebSMath's only by the diff kept in
`tests/calc/websmath_drawing_colour.diff`, which the identity test checks);
equation conditional formatting sets colour, size, bold, underline and
background; Find & Replace both in tables and in the document Search; cell
rules compare units.

* **Conditional formatting** (right-click ▸ Conditional Formatting): Highlight
  Cells Rules (greater/less/between/equal/not equal, text that contains, a date
  occurring, duplicates), Top/Bottom rules (top/bottom n or n%, above/below
  average), Data Bars, Colour Scales, Icon Sets, New Rule with a formula, Clear
  Rules, Manage Rules (order, applies to, Stop If True). "200 kN" compares
  quantities; a plain number compares the number as shown; units that don't
  match never match. Rules move with inserted/deleted rows and columns.
* **Sort** A→Z / Z→A on the active column, Custom Sort with levels and
  headings; blanks last; formulas keep reading their own row.
* **AutoFilter**: drop-downs in the first row (screen only): sort, choose
  values, number/text filter with two conditions, top 10, clear; filtered rows
  take no room and don't print; SUBTOTAL leaves them out.
* **Data validation**: whole number, decimal, list (in-cell drop-down, Alt+↓),
  date, time, text length, custom formula, with units in limits; input message;
  Stop/Warning/Information alerts; Circle Invalid Data.
* **Comments**: new/edit/delete (Shift+F2), a red triangle on screen, the comment
  as a tooltip.
* **Find & Replace** (Ctrl+F / Ctrl+H in an open table): this table or all,
  formulas/values/comments, match case, entire cell, Excel's wildcards; the
  document Search also finds and replaces in table cells.

Tests: `tests/sheet/test_data_tools.py` (11), `tests/test_table_data.py` (8),
`tests/test_equation_rules.py` (8).

## Spreadsheets, phase 4 — sheet pages, page breaks and the scratch area (2026-10-09)

Answers by pop-up: the columns that fit inside the page's margins print and
everything to their right is scratch (a blue line at the edge; Print Area or
Fit to page width prints more); markups over a sheet move with their cells;
empty pages at the end of a run are kept; row numbers and column letters
always show on screen.

* **Insert spreadsheet page**: the ▦ button in the Pages panel, Page ▸ Spreadsheet
  page, or a page's right-click menu ("Spreadsheet after"; on a sheet page
  "Add sheet page"). Consecutive sheet pages are one sheet (`Sheet1`…),
  shown as one continuous grid: no gap between its pages, Excel's Page Break
  Preview lines where one ends (dashed blue where the break fell by itself,
  solid blue where the user put it), "Page N" faintly on each, the printed
  part white and the scratch area grey to its right (at least a page wide, and
  always two columns past the last one used).
* **Clicks**: in Markup mode a markup over the cells is picked first and
  anywhere else is a cell; in Calc mode clicks go to the cells. Row numbers and
  column letters always show.
* **Growth**: the selection can go one row past the last page; typing there
  adds a page, in the same undo step as the typing. Empty pages are kept.
* **Pages of a run**: nothing goes in between them (a page added inside goes
  after the run); a reorder that would split a run is refused, a whole run
  moves; turning one page turns the run (portrait ⇄ landscape) and the breaks
  flow again; Page Setup on a sheet page sets the whole run's paper; deleting
  a page of a run deletes its rows (its markups go with it, later ones keep
  their cells); a duplicated or pasted sheet page is an ordinary page.
* **Markups move with their cells**: rows or columns inserted, deleted,
  resized or hidden move each markup with the cell under its corner, onto the
  next page when that is where its cell went.
* **Page layout** (right-click ▸ Page Layout, or Page ▸ Sheet
  layout…): Insert/Remove Page Break, Reset All Page Breaks, Set/Clear Print
  Area, and the dialog: print area, rows to repeat at top, fit all columns to
  the page width, centre horizontally/vertically, print gridlines, print
  headings, gridlines on screen. Dragging a break line makes a manual break
  there. Breaks, print area and titles move with inserted and deleted rows.
* **On paper**: each page prints its slice of rows inside the margins (scaled
  for Fit to page width), title rows repeated at the top of later pages, the
  markups over their cells; gridlines and headings only when switched on;
  borders always.
* **Saving**: the cells and the markups of a sheet page are CalcForge's own
  drawing (the calc layer, taken off and rebuilt on reopen) and are kept in the
  record — not written as annotations, because another reader could move them
  off their cells.
* **Not on sheet pages**: equations (no red cross, typing goes to the cells,
  an equation dropped there stays where it was) and tables.

Tests: `tests/sheet/test_pagination.py` (8), `tests/test_sheet_pages.py` (16).

## Spreadsheets, phase 5 — charts, dynamic arrays and named ranges (2026-10-10)

Answers by pop-up: a chart goes anywhere (a sheet page over its cells, or any
page beside the equations) and reads any sheet or table; the engineering
chart types — XY scatter, line, column — with log axes, error bars and
trendlines; Excel's full structured-reference syntax on tables; Excel's
default chart look with the cells' units in the axis titles.

* **Dynamic arrays**: a formula whose result is a block (SEQUENCE, FILTER,
  SORT, UNIQUE, a range…) spills into the cells below and to the right; the
  spilled cells are read like any other; a thin blue frame shows the block
  while one of its cells is active, and the formula bar shows its formula
  greyed. Anything in the way — a value, another spill, a merged cell, the
  edge of a table — makes it `#SPILL!` until it is cleared. `A1#` is the
  whole block (`=SUM(A1#)`, `=SORT(A1#)`). Spilled values are not saved:
  their formula makes them again.
* **Structured references** on tables, the first row being the headings:
  `Loads[Load]`, `Loads[@Load]` (this row), `[@Span]` inside the table,
  `Loads[[#Headers],[Load]]`, `Loads[#All]`, `Loads[#Data]`, `Loads[]`,
  `Loads[[Load]:[Span]]`; they grow with the table and follow its renames
  (a table has no totals row, so `#Totals` is `#REF!`).
* **Named ranges**: the Name Box names the selection (type a new name and
  Enter) and goes to a name (type it, or its ▾ list); right-click ▸ Names ▸
  Define Name…, Name Manager… (Ctrl+F3: New, Edit, Delete; name, value,
  refers to, scope, comment) and Create from Selection… (Ctrl+Shift+F3: top
  row, left column, bottom row, right column — "Load (kN)" becomes
  `Load_kN`). Names follow Excel's rules (no spaces, not like a cell), keep
  their scope and comment, and are saved and undone with the sheet whose
  cells they name (a constant with the sheet it was made on). The equations
  read a named block as a vector.
* **Charts** (Calculation ▸ Chart, or right-click a table ▸ Insert Chart ▸ XY
  Scatter / Scatter with Lines / Line / Column): the cells picked out are read
  as Excel reads them — headings as series names, the first column as x (or
  the categories) — and the chart goes beside the table, or over the cells to
  the right on a sheet page. Excel's look: Office colours, light grey
  gridlines, title on top, legend at the bottom, axis titles with the cells'
  units. Double-click (or right-click ▸ Edit Chart…) for type, titles,
  legend, each axis's bounds, major unit, log scale and gridlines, and each
  series' name and cells, y error bars (fixed, percentage, standard
  deviation, standard error, custom ranges; both/plus/minus), x error bars on
  scatter charts, and a trendline (linear with an optional intercept,
  polynomial of order 2–6, exponential, logarithmic, power, moving average)
  with its equation and R². A chart follows its cells as they change, and its
  ranges follow renames and inserted or deleted rows; it prints and exports
  with the page (CalcForge's drawn layer, not an annotation) and moves like a
  markup.

Tests: `tests/sheet/test_dynamic_arrays.py` (9), `tests/sheet/test_chartdata.py`
(9), `tests/test_table_names.py` (6), `tests/test_charts.py` (7).

## Spreadsheets, phase 6 — opening Excel workbooks (2026-10-10)

Answers by pop-up: no export to Excel at all; opening an `.xlsx` brings in its
cells only (no charts).

* **File ▸ Open** takes an `.xlsx` (or `.xlsm`) as a new document, and **File ▸
  Insert Excel…** puts a workbook's worksheets after the current page (one
  undo step). Each worksheet becomes a run of spreadsheet pages of its own
  name, on its own paper (size, orientation, margins), as many pages as its
  cells need. A worksheet named like a sheet or table already in the document
  is renamed ("Beams (2)") and the formulas that read it follow.
* **What comes across**: values (dates as Excel's serial numbers in their
  format, text that looks like a number or formula kept as text), formulas
  (Excel's `_xlfn.` prefixes taken off, `ANCHORARRAY(A1)` as `A1#`, dynamic
  arrays spilling again, old Ctrl+Shift+Enter arrays the same way), formatting
  (font, size, bold, italic, underline, strike, colours with the workbook's
  theme and tints, fills, borders, alignment, wrap, indent, rotation, number
  formats, locked/hidden), column widths and row heights, hidden rows and
  columns, merged cells, comments, defined names (workbook and sheet scope),
  data validation, conditional formatting (cell value, formula, text, blanks,
  errors, duplicates, top/bottom, above/below average, dates, colour scales,
  data bars, icon sets), gridlines, and the page layout (print area, rows to
  repeat, manual page breaks, fit to page width, centring, printed gridlines
  and headings). An Excel table's references (`BeamTbl[Moment]`,
  `BeamTbl[@Load]`) become the cells they name — a worksheet's Excel tables
  are not CalcForge tables.
* **Said on opening**: how many worksheets came in, which were hidden in
  Excel, what was left out (charts, pictures, chart sheets, What-If data
  tables — their values kept —, a print scale other than 100 %, names that
  refer to deleted cells), and every formula that gives another answer here
  than Excel last showed for it, by address, with those using functions or
  names CalcForge does not know.
* Nothing is written to `.xlsx`. openpyxl is now a dependency.

Tests: `tests/test_xlsx_open.py` (6).
