# CalcForge — build plan

CalcForge is MarkForge (Bluebeam-style PDF markup) with WebSMath (the SMath
Studio replica) built in. The requirements are the 2026-09-30 entries in
`docs/tasklist.md`: 30 numbered decisions plus the clarifications that
followed. This file says how they will be built and in what order. It doesn't
restate every decision.

- Branch: `claude/admiring-archimedes-i371m1`. It was started from the
  MarkForge branch at `d0ddb22`.
- Sources (read-only): MarkForge `claude/markforge-mupdf-pdf-handling-vpyj1t`,
  and WebSMath `claude/zealous-clarke-8yiu03` at `8b340fa`, folder `websmath/`.
- Baselines measured on 2026-09-30 in this container:
  - MarkForge: 1012 passed.
  - WebSMath: 766 passed. The process then segfaults on exit during PySide
    teardown, after every test has passed; this is fixed in phase 1.
  - Mutation check: 14 of 14 planted bugs caught.

## The gate every push goes through

1. The whole suite: MarkForge's tests plus the ported WebSMath tests, run with
   `QT_QPA_PLATFORM=offscreen`.
2. `python -m <package>.calc.tools.mutation_check`, which must catch 14 of 14.
3. Every interactive change is driven through the real window, using real Qt
   events as `tests/test_usability.py` does, and checked by eye in an
   offscreen screenshot where it affects what is drawn.
4. From phase 4 on, saved files are read back three ways:
   - the text, with MuPDF and with pypdf;
   - the pages, rendered and compared pixel-for-pixel with the screen;
   - the file as another reader sees it: the calc layer is page content
     rather than an annotation, and the markups are ordinary annotations that
     can be moved.

A phase ends with a report to the user covering what changed, what was
tested, the tests removed (by name) with the feature they covered, and
anything that behaves differently from SMath or Bluebeam.

## Architecture in one page

**Engine.** WebSMath's `engine/` (Qt-free) moves over byte-for-byte. So do
`editor.py`, `worksheet.py` and `plot.py`, which are also Qt-free and are what
make typing, reading-order evaluation and dependency-only recalculation work.
Two changes to `worksheet.py` are required by decisions, and each gets its own
tests:

- A region's reading-order key gains the page. A region's key becomes
  `(page order, y, x, id)`, where `y` and `x` are in the page's own,
  unrotated coordinates. Reordering pages reorders evaluation, and rotating a
  page never does.
- Calculation blocks with **Self-contained** on (decision 10). Names defined
  inside the block are visible only inside it; the block still reads
  everything defined above it.

**One worksheet per document.** The document owns one `Worksheet`, so
variables reach every page (decision 9).

- Each equation, plot, matrix or program is a `CalcItem(MarkupItem)`. It sits
  on its page like any markup, so selection, grouping, alignment, snapping,
  lock and undo all work unchanged.
- Each `CalcItem` wraps one worksheet `Region` and paints it with WebSMath's
  `layout.py` and `RegionItem` drawing code. That keeps SMath's fonts
  (including SMath's own equation font), blue units, red errors and yellow
  tips. The page is never themed, so equations stay black on white in dark
  mode.
- Moving an item re-keys its region, and the worksheet's own incremental
  recalculation does the rest (the speed requirement).
- **Calculation blocks** are a `CalcBlockItem`: a rectangle whose regions
  evaluate as a unit. They are never collapsible.

**Keyboard.** WebSMath's `WorksheetView` key logic (`_key_to_region`,
`_named_key`, `_enter`, autocomplete and the error tip) moves into a
Qt-light `CalcController` that `PageView` hands keys to.

- While an equation has the cursor, the controller gets every key first
  (decision 6: editing decides). The exceptions are document commands (save,
  print, zoom) and Ctrl+B/I/U, which format the equation.
- Outside editing, MarkForge's shortcut manager decides, filtered by the mode.

**Modes.** Calc mode and Markup mode are a document-view state, shown in the
status bar. The mode toggle, the equation start key (`'`), and "`"` = Calculation
text" versus "`"` = text box" are ordinary `Binding`s with clash checking.

- In Calc mode, `ShortcutManager.match_typed` and every tool binding (with or
  without Shift or Alt) return nothing. A printable key on empty page space
  starts an equation at the red cross instead.

**Undo.** There is one stack: MarkForge's snapshot stack.

- Keystrokes inside an equation use WebSMath's per-keystroke undo while the
  equation is open, the same way MarkForge already treats text being typed.
- Leaving the equation commits one snapshot, which records the equation's
  source and position.
- A snapshot restore rebuilds the affected regions and recalculates only
  what depends on them.

**Units.** `core/units.py` stops importing Pint.

- It becomes a thin adapter over the engine's `Quantity`, keeping the names
  its callers use (`parse_unit`, `convert`, `format_quantity`, `Q_`,
  `UNIT_MENU`). Measurements, scales and calibration therefore use SMath's
  unit table and number formatter.
- Menus use SMath's unit names; pcf, klf and plf become compound units.
- Plain-text units read `kN·m`, `m²`. Measurement labels keep the page's
  decimal places.

**File.** The document is still one PDF with an embedded record.

- On every save, CalcForge recalculates, then writes the calc content as
  vector drawing and embedded-font text. It goes into a separate content
  stream on each page, wrapped as an optional-content group tagged
  `CalcForge` and appended after the page's own content, which is never
  changed.
- The record gains `calc`: every region's source, format, unit box, position
  and page uid.
- On open, the tagged stream is found and removed, then its bytes are
  compared with what the record would draw. A difference warns, and the
  record wins. Pages are matched by uid, so deleted or reordered pages are
  handled as decision 3 says. With no record, the file opens as a plain PDF
  and a warning says the calc can't be edited.
- Save writes a fresh, garbage-collected file every time. A file with a
  `/Sig` field that has a `/ByteRange` is appended to instead, and the status
  bar says why.

Found while researching, to be checked in phase 4: the record currently
embeds a copy of the source PDF as an asset. With incremental saves that
copy is appended again on every save, which would explain file growth. The
fix is for the saved file's own pages to be the source, with every CalcForge
drawing in tagged layers that are removed on open. The test "repeated saves
don't grow the file" guards it.

## Phases

### Phase 1 — engine and units merged, all tests passing

- Bring `engine/`, `editor.py`, `worksheet.py`, `plot.py` and `tools/` under
  `markforge/calc/`. They are renamed with the rest of the package in
  phase 8.
- Bring WebSMath's `ui/` and `page.py` in temporarily, only so the 766 tests
  run unchanged; they are replaced piece by piece in phases 2–6.
- Move the `.sm` reader and writer into `tests/calc/`, as a test-only
  fixture. No app code imports it.
- Tests go to `tests/calc/` with imports updated. Make `mutation_check` plant
  its bugs in the new location, and fix the segfault on exit.
- Replace Pint in `core/units.py` with the adapter over the engine; remove
  Pint from `requirements.txt` and `pyproject.toml`.
  - Unit names follow SMath's. The formatter writes `kN·m` and `m²`.
  - Measurement labels use the engine's formatter at the page's decimal
    places.
- Gate: MarkForge's 1012, WebSMath's 766 and 14 of 14 mutations. No
  measurement or scale test is changed, apart from unit spellings SMath
  writes differently, and each such change is listed in the report.

### Phase 2 — equations on pages

- Add `CalcItem`, `CalcBlockItem` and a plot item, all on MarkForge pages,
  with one worksheet per document and reading order across pages.
- Equations snap to the SMath grid and markups snap to it too. MarkForge's
  5 mm grid, grid spacing and grid printing are removed.
- The red cross appears in Calc mode (the mode switch itself is phase 3; this
  phase uses Calc behaviour for testing).
- Pushing an equation past the last page adds a page, and nothing straddles
  two pages. SMath margins apply on pages CalcForge creates.
- Automatic line breaks for too-wide equations; where no break fits, an
  orange outline and a warning.
- Rotated pages: equations turn with the page and show upright while edited.
- Mixed selection with markups, grouping, align, box select (right: wholly
  inside; left: touching), arrow keys nudge, and Lock.
- One undo stack.
- Snapshots copy equations as line work. Recolour and Whiteout skip
  equations; Redaction deletes the ones it fully covers; Flatten skips them;
  Crop removes the ones wholly outside. Each of these warns about variables
  that became undefined.
- Port `test_ui.py` and the other window tests onto the CalcForge window.

### Phase 3 — modes and shortcuts

- Calc and Markup modes, shown in the status bar, with a toggle binding.
- Calc mode turns off every tool key (plain, Shift and Alt). `"` gives
  Calculation text, a lone word then space gives Calculation text, and `@`
  inserts a plot.
- Markup mode: `'` starts an equation at the pointer, and `"` gives a text
  box.
- Editing decides clashes: Ctrl+0, Ctrl+1, Ctrl+E, Ctrl+Shift+D, Ctrl+A, and
  also Ctrl+[ (element vs send backward), Ctrl+= (boolean equals vs zoom),
  `|` (absolute value vs start note), Tab, Space and Esc.
- Ctrl+B/I/U format equations. MarkForge's symbol keys work in equations
  with their maths meaning. SMath's Ctrl+G and Ctrl+W go.
- The shortcut manager gets an "SMath" section listing every calculation key.
- File > New gives one blank A4 portrait page in Markup mode.

### Phase 4 — saving and flattening

- Recalculate on save, then write the tagged vector calc layer: selectable,
  searchable text with embedded fonts; lines for fraction bars, radicals,
  brackets and plots; SMath's colours.
- The calc record, and rebuilding from it on open, with the three warnings
  (layer edited elsewhere, pages deleted elsewhere, record missing).
- Save always writes a fresh, compact file; signed files are appended to and
  the calc layer is still swapped.
- Tests:
  - repeated saves don't grow the file;
  - saved text reads back correctly;
  - the rendered page matches the screen;
  - opened as another reader would, the calc can't be moved and the markups
    can;
  - a signature stays valid.
- Extract and Split carry their pages' equations live, and Insert PDF brings
  a CalcForge file's equations live.
- Autosave writes the same file format.

### Phase 5 — toolbar, panels and properties

- A "Calculation" toolbar section: F9, auto-calc, plot, matrix, Calculation
  text, calculation block, if/for/while/line.
- A "Maths" rail panel made from SMath's Arithmetic, Matrices, Functions,
  Programming, Graph and Units panels.
- Equation settings in the right-click menu and in Properties.
- Result format, font, size and colour defaults in Preferences.
- Plot mouse behaviour: SMath's behaviour once the plot has been
  double-clicked into.
- Calculation text as its own type, with its own default style, snapping to
  the grid, with no leader; it gets spell checking.
- Search finds variable names and equation text.
- Copying equations out gives a picture plus plain text.

### Phase 6 — header/footer and file properties

- MarkForge's six slots, logo and page ranges, plus SMath's fields.
- One merged Properties dialog. Title, author, subject and keywords also go to
  the PDF's standard properties.
- SMath's Separator, Picture, Background and header layers are removed, with
  their tests (listed in the report).

### Phase 7 — blocks, tool sets, Variables panel, measurement variables

- The **Self-contained** option on calculation blocks.
- Equations and blocks in tool sets and My Tools: a preview, then behaviour as
  if typed there.
- A Variables rail panel: value, unit, page and error for each variable;
  clicking a row jumps to it.
- A measure markup can be given a variable name, which feeds the calcs live.
  It is evaluated at the top-left of its bounding box, the same rule as an
  equation. Deleting it warns about variables that became undefined.

### Phase 8 — rename and settings migration

- `markforge/` → `calcforge/`, along with the window title, README, launch
  command, `pyproject` name and settings name.
- On first start, the MarkForge settings are copied across once: shortcuts,
  tool sets, My Tools, toolbar layout, dark mode and markup defaults.
- The handover is updated to match.

### Later (planned, not built)

**Live values in Calculation text.**

- A field such as `{M}` inside Calculation text shows `M = 45.2 kN·m`, formatted
  as the equation that defines `M`, and updates whenever `M` changes.
- It is evaluated at the text's own position, so it only sees what is defined
  above it, and an undefined name shows SMath's error text in red.
- It is saved as plain text in the annotation, so other readers see the value
  at the time of saving.

## Differences from SMath and Bluebeam known up front

- Pages are fixed, not SMath's endless worksheet: equations never straddle
  pages, and too-wide ones break onto more lines (SMath doesn't break
  equations).
- There are no SMath areas; calculation blocks aren't collapsible, and
  "Self-contained" is new.
- No `.sm` files, and no → symbolic arrow (already the case in WebSMath).
- Calc content in the saved PDF is page content, not annotations, so in
  Bluebeam it can't be moved or listed; this is on purpose.
