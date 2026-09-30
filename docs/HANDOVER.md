# CalcForge (formerly MarkForge) — start here

## 2026-09-30: CalcForge

MarkForge and WebSMath are being combined into **CalcForge**. Calculations
are a wanted feature again: see "Calculations are back" in §1. The plan is
`docs/CALCFORGE_PLAN.md`.

## Latest review: 2026-09-29

Evidence in `COMPLETED_TASKS.md`. Things that will bite:
- `/RD` is left, bottom, right, top (y up) — Bluebeam's own callouts prove
  it. Read and write it that way (`btx.drawn_box`, `annotate`, `pdfmarkups`).
- For FreeText, `/C` is the background, `/DA`'s colour is the frame and
  leader, `/DS` color is the words (`btx.free_text_colours`).
- Export writes annotations in stacking order (`annotate.exportable`).
- Groups: `btx.group_paths` follows `/IRT` chains and the nested
  `[ (Group) … ]` lists in `/GroupNesting`; `annotate._group_nesting`
  writes them back.
- Page setup panel: `ui/pagepanel.py`; separate Y scale is
  `PageScale.y_factor`.
- `QTextCharFormat.fontFamilies()` segfaults PySide 6.11 when empty.
- Page coordinates: never use PyMuPDF's `transformation_matrix` directly —
  `engine.to_pdf`/`to_display` build it from the crop box (MuPDF's drops
  the crop offset on turned pages). Appearances on turned pages carry the
  turn in their /Matrix (`Placement.turn_the_appearance`), except notes,
  which stay upright and pinned (`_pin_the_note`).
- Audit scripts used this round (not in the repo): export every tool and
  compare MarkForge / MuPDF / pdfium / rebuilt renders; render every `.btx`
  tool from Bluebeam's own appearance and compare with the import.

## Previous review: 2026-09-28

The user's add list from `BLUEBEAM_COMPARISON.md` is built (A1, A2, B3, B6,
B8, C2, C4, C5, the Markups list) with the follow-ups; evidence in
`COMPLETED_TASKS.md`. Things worth knowing:
- The Markups list is not a dock: it is the second widget of
  `MainWindow.bottom_split`, a vertical `QSplitter` under the canvas.
- Viewports are page data (`Page.viewports`, `Page.scale_at`), not
  markups. Measurements and sized shapes read their scale through
  `scale_on(page)` (`base.scale_where`), never `page.scale` directly.
- Combo boxes never take the wheel: `widgets.WheelBelongsToTheScroller`
  is installed application-wide.
- Hatch patterns live in `items/hatches.py`; `paint_visible` draws fill,
  then hatch, then the outline.

## Previous review: 2026-09-27

At the user's request every earlier entry in `tasklist.md`, `tasklist.xlsx`,
`COMPLETED_TASKS.md` and `UNADDRESSED_TASKS.md` was deleted; the registers
restart with the 2026-09-27 report. The "nothing is ever deleted" rule in §4
still applies from here on. (Branch: see the top of this file.)
Evidence for this round is in `COMPLETED_TASKS.md`; open follow-up (the Revit
red cross needs the user's file) is in `UNADDRESSED_TASKS.md`.

Things learnt this round that will bite again:
- Qt 6.11's `QSvgRenderer` strokes a `stroke="none"` path with a default pen
  when painting to `QPdfWriter`, and Qt's PDF writer loses precision on MuPDF's
  unit-sized glyph outlines. `pdfsnapshot.inline_glyphs` writes glyphs out in
  page coordinates with `stroke-opacity="0"`; snapshots paint their kept
  vector source (not the QPicture) whenever the painter is a PDF or printer.
- `hatch_named()` returns a Qt enum; never `int()` it. An exception in
  `paint` is a segfault a few events later.
- Hatch is its own linework (`Style.hatch_color`) over a solid fill. Styles
  saved before that are converted on load in `Style.from_dict`.
- PySide 6.11 on Linux: run the suite with `QT_QPA_PLATFORM=offscreen`; it
  is several times faster than `xvfb-run` and does not hang. `numpy` and
  `cffi` must be installed (units formatting and pypdf respectively).

## Previous review: 2026-09-18

The clarified Whiteout behavior is flattened PDF artwork only; live markups
remain editable and untouched. The requested fit option was withdrawn. PDF
content snapping now includes vectors beyond the old import cap and creates
interactive geometry only near the pointer. Second-point alignment guides
repaint their full extent and clear after placement. Break symbols expose
independent width, height and position with three handles; older saved settings
still load. Both task registers were updated without changing completion
status. See `COMPLETED_TASKS.md` for the 947-test suite and native stress run.

## Previous review: 2026-09-17

The September 17 user reports are recorded in both task registers. See
`REVIEW_2026-09-17.md` for the visual/Qt-event walkthrough, repaired findings,
Bluebeam documentation comparison, and the validation still needed on Windows
and in third-party viewers. PDF content snapping is now lazily extracted from
the source PDF; these targets stay outside document markups. Export no longer
paints viewing paper into the PDF. Contents links are written on both Save and
Export. Appearance controls are shared between Properties and the dynamic
style toolbar, including numeric step buttons and visual line-end previews.
Do not mark task-list completion cells: only the user can do that. The latest
suite evidence is in `COMPLETED_TASKS.md`.

## Previous review: 2026-09-13

Editing performance follow-up: see `APP_PERFORMANCE.md` and
`tools/benchmark_editing.py`. Page restoration emits one final change signal,
undo commits reuse serialized state, and snapping reuses nearby geometry only
within the current event. Do not restore per-item panel refresh during undo or
persist the snapping candidate list across edits. The 500-markup native
benchmark measured 35× faster undo/redo and 1.8× faster pointer snapping.

PDF rendering now uses `io/pdfrender.py` worker processes coordinated by
`io/pdftiles.py`. Do not move MuPDF rendering back into Python threads.
Sources are shared through private files; pixels use fixed shared buffers.
The default is up to four processes (override `MARKFORGE_PDF_WORKERS=1..8`).
See `PDF_PERFORMANCE.md` for timings, cache bounds and reproducible benchmarks.
Latest full suite: 920 passed, no skips; native stress: seed 131, 1,000 rounds,
4 pages, 71 markups, no failures.
Escape recovery now handles inline panel editors and stale scene mouse grabs
(`tests/test_escape_recovery.py`). Use `QWidget.window(widget)` in the event
filter: `PageView.window` is an owner attribute, not QWidget's window method.
The real-PDF tests include `btx/Document1.pdf`; optional additional files use
`MARKFORGE_PDF_CORPUS`. Old audit statements moved to `TASK_AUDIT_HISTORY.md`.
The current outstanding file separates verification from external blockers.

Read the **Current review** sections of `COMPLETED_TASKS.md` and
`UNADDRESSED_TASKS.md` before using the older architecture/status notes below.
The PDF engine is now MuPDF-backed (`pdf/engine.py`); the old standalone parser
map is historical. Split view and transferable document tabs are implemented.
The bar stays visible with one tab.

Snapshots use `io/pdfsnapshot.py`: vector-only pages retain exact paths; text
and image pages retain a full SVG appearance with outlined fonts and source
image pixels. Both persist in `SnapshotItem.source_items` beside the QPicture.
Do not restore the raster page fallback: it carries the background through and
breaks recolouring. Source PDF paths are separate from capped optional snapping
geometry. Raster page backgrounds and full-page vector fills are excluded.
Whiteout uses `io/pdfwhiteout.py` to subtract actual geometry and erase image
pixels, preserving outside segments and live annotations. Source text keeps its exact outlined appearance and gains a searchable layer
containing only surviving characters, including rotated labels. Undo retains
the original; this is not secure redaction. Callout tool switching now clears abandoned arrow anchors.
`Style.hatch_scale` controls hatch spacing and is shared by both style surfaces.

Current acceptance tests: `tests/test_review_regressions.py`. Rendering requests
carry a viewport consumer so a detail view cannot cancel an overview's tiles.
The fuzzer isolates application settings. On this macOS environment, pytest
uses Qt's offscreen backend; a native fuzzer requires access to GUI services.
No completion checkbox was changed in this review. New requests appear in
both task registers; old completion evidence was checked and corrected.
Follow-up final suite and native stress results are recorded in
`COMPLETED_TASKS.md`. The focused review suite currently contains 32 tests.

---

**If you are an agent picking this project up, read this file first.** It gives
the product context, code map, validation approach and task-tracking rules
needed to work safely without re-reading earlier chat.

- Repository: `KavGoat/Test`
- Branch: **`claude/admiring-archimedes-i371m1`** (CalcForge) — all work goes
  here. The MarkForge branch `claude/markforge-mupdf-pdf-handling-vpyj1t` and
  the WebSMath branch `claude/zealous-clarke-8yiu03` are read-only sources:
  never push to them. Never push to another branch without being asked.
- The living task list: **`docs/tasklist.md`** — read it, work from it, keep it
  updated. `docs/tasklist.xlsx` is the user's companion status sheet: column A
  is blank for open work and `1` for user-confirmed completion. Rules for both
  are below and repeated in the task-list header.

---

## 1. What the app is

MarkForge is a PySide6 (Qt 6) desktop **PDF markup editor** for a New Zealand
structural engineer. Open somebody's drawing, mark it up, save it back. It does
Bluebeam Revu's job: the full annotation tool set, scaled measurement and
take-off, tool sets with `.btx` import, and pages read as one continuous scroll.

**The document is a PDF.** There is no format of its own and no second
extension. Saving a drawing that was opened here writes an *incremental update*
— the bytes that came in are the first bytes of the file that goes out, and the
markups are appended after them as real PDF annotations. What a PDF has no word
for rides along inside the same file as an embedded record. Everything about
that is in §2 under `pdf/` and `io/`.

**Calculations are back — standing instruction, 2026-09-30.** Until
2026-09-07 this app did unit-aware calculations, and they were then withdrawn
(with spreadsheets, the `.cfx` format, review states, replies and layers).
**On 2026-09-30 the user overrode that withdrawal on purpose:** calculations
return as WebSMath, the SMath Studio replica from branch
`claude/zealous-clarke-8yiu03`, and the app becomes **CalcForge**. Equations,
plots, matrices, program blocks, calculation blocks and Calculation text are
wanted features. Never remove them and never treat them as leftovers.
Spreadsheets, `.cfx`, review states, replies and layers stay withdrawn.
`docs/tasklist.md` records this at the top and in its **Withdrawn** section,
and `docs/CALCFORGE_PLAN.md` is the build plan.

### Who the user is, and how they work

- A practising structural engineer, not a programmer. They describe what they
  want in the language of Bluebeam — if a request seems vague, the answer is
  usually "whatever Bluebeam does".
- They send **photographs of their screen** as bug reports. Read them
  carefully; they often show the exact defect in the corner of the frame.
- They type quickly and with typos. Read intent, not spelling.
- They test the app themselves between sessions and come back with lists. Take
  every item seriously and log every one (see §4).
- When they say a thing is not needed, it goes — the whole thing, including the
  tests and the documentation for it. Three features have been removed that
  way. Take the instruction at face value and remove it properly rather than
  hiding it behind a switch.

### Standing constraints

- **No copying Bluebeam's icon artwork.** Match its conventions, names,
  shortcuts and behaviour — draw the icons.
- Labels are **one or two words**, like Bluebeam's. The explanation goes in the
  tooltip, never in the button.
- The user cannot be shown a video; do not suggest one.

---

## 2. How the code is laid out

```
markforge/
  pdf/         a PDF reader and writer of its own, written from the
               specification rather than wrapped round somebody else's
    objects.py       the eight object kinds: Name, Ref, Stream, and the rest
    lexer.py         the syntax: dictionaries, arrays, strings, streams
    filters.py       Flate, LZW, ASCIIHex, ASCII85, RunLength; PNG and TIFF
                     predictors
    storage.py       ObjectStorage: every object by number, and resolve()
    reader.py        cross-reference tables and streams, object streams, and
                     recovery by scanning when the table is wrong
    writer.py        serialize(), and incremental_update() — the important one
    annotations.py   the annotation model: border effects, callout lines,
                     measure dictionaries, line endings
  calc/        the calculation engine — WebSMath, the SMath Studio replica
    engine/          Qt-free maths, moved over unchanged (only symbolic.py's
                     import of ast_to_items now points at ../astitems.py)
    editor.py, worksheet.py, plot.py, page.py, astitems.py
    ui/layout.py, ui/region_item.py   SMath's typesetting and drawing
    tools/mutation_check.py           plants 14 bugs; all must be caught
    docsheet.py      one worksheet per document; pages folded into the
                     reading order; moves settled at the end of a gesture
    record.py        an equation's source as JSON (what the PDF record keeps)
    ui/wrap.py       too-wide equations broken onto more lines (display only)
    ui/suggest.py    SMath's autocomplete list (moved from WebSMath's window)
  core/        no Qt beyond QPointF-style value types
    document.py      Document, Page, PageSetup, PageScale, assets
    units.py         scales and measurements on SMath's unit table and the
                     engine's number formatter (Pint is gone), UNIT_MENU
    typography.py    page fonts sized in pixels, not points (see below)
    spelling.py      New Zealand English, checked against a packed word list
  items/       every markup, all deriving from MarkupItem (items/base.py)
    base.py          Style, handles, hatches, dash arrays, cloud_path()
    text.py          _TextBase, TextItem, CalloutItem, NoteItem, StampItem,
                     and _Leader — the leader model (see §5)
    shapes.py        RectItem, PolyItem — corners, arcs, break symbols
    measure.py       MeasureItem and CountItem: length, area, dimension, count
    calc.py          CalcItem: an equation on a page (IS_CALC); its area,
                     grid snap, turned pages; CalcDrawingItem (line work)
    media.py, snapshot.py, contents.py
  ui/
    mainwindow.py    MainWindow: menus, commands, panels, page commands
    view.py          PageView: the canvas — every mouse and key gesture
    calcedit.py      CalcEditing (view.calc): Calc/Markup mode, red cross,
                     SMath's keys, typing equations, pushing to next page
    scene.py         DocumentScene, PageFrame: pages stacked down one canvas
    panels.py        the docked panels; toolsets.py, rail.py, docks.py
    dialogs.py       every dialog
    tools.py         the tool table: key, label, icon, shortcut, factory
    shortcuts.py     DEFAULT_BINDINGS and the shortcut manager. Every
                     binding has a scope (ALWAYS, CALC, MARKUP, EQUATION,
                     TYPING); a key clashes only where scopes overlap
                     (scopes_overlap). SMATH_KEYS is the SMath section.
    mathspanel.py    the Maths rail panel (WebSMath's side panel sections)
    calcedit.py (end) WebSMath's selection commands (Solve, Calculate
                     selection, Invert, Determinant), Insert > Operator and
                     copy/paste of part of an equation
    calcmenu.py      an equation's settings: right-click › Equation, plot
                     settings; calcmenu.change() is the one undoable way
                     to change regions' settings
    calcdialogs.py   WebSMath's matrix/function/constants/double-check
                     dialogs (ANSWERS lets tests answer them)
    theme.py (markforge/theme.py) light and dark stylesheets
  io/          pdfbase (what a saved document is: a fresh file every save,
               and reopening it), calclayer (CalcForge's tagged sheet and calc
               layers, taking them off, signatures), pdfsave (appending to a
               signed file), project (open and save), annotate (markups as real PDF
               annotations), pdfio, pdfvector, pdfmarkups, pdflinks,
               btx (Bluebeam tool sets), recolour, export
btx/           the real Bluebeam tool sets the importer is tested against
tests/         pytest; see §3
tools/         session_fuzz.py — a long randomised session against the app
docs/          this file, tasklist.md, interface.md, backlog.md,
               what-matters.md
```

### Things worth knowing before you change anything

- **The canvas is one scene holding every page.** Scrolling is continuous. A
  gesture is always aimed at a page frame — use `view.frame_at(point)`, never
  assume the current page.
- **Rotating the view rotates the pages on the canvas, not the view
  transform.** `apply_view_transform()` holds the zoom only, so the scrollbars
  keep pointing the way they scroll.
- **Undo is a snapshot stack.** `view.begin_snapshot(frames)` … change …
  `view.commit_snapshot("Label")`. One gesture is one step.
- **Settings** are `QSettings("MarkForge", "MarkForge")`. The suite sandboxes
  them by pointing `XDG_CONFIG_HOME` and its neighbours at a temporary folder,
  at the top of `tests/conftest.py` and **not in a fixture**, because Qt works
  out those locations once and keeps the answer. Do not call `sync()` to "fix"
  ordering — that broke the layout tests once already.
- **A saved document is a PDF, written afresh every save** (decisions 3
  and 4). `io/pdfbase.py` builds it in memory and writes it once, compact:
  each page's own content (when every page is a page of one PDF at its size,
  that PDF is copied and its pages selected — grafting page by page drops
  annotations), then two tagged layers (`io/calclayer.py`: the sheet —
  header, footer, flattened markups, paper — and the equations as vector
  drawing and text), then the markups as annotations, then the record. Every
  page carries `/CalcForgePage` (its uid). Opening strips both layers and our
  own annotations; what is left is the page's source from then on, so the
  record no longer carries the PDF again (`FILE_FACTS["itself"]`). Markups
  that are still somebody else's annotation are found again by
  `calclayer.annotation_print` (object numbers change on every save).
  For markups the file wins: each annotation CalcForge writes carries a
  fingerprint in the record (`written_print`); on reopen an unchanged one is
  replaced by the record's markup, a changed one is read in as the other
  editor wrote it (keeping uid, lock, group), a missing one means deleted.
  On reopen every non-image page gets its saved page as source
  (`Page.written_here` keeps SMath's margins on written pages). Layers are
  placed with a matrix from the page's own boxes (`calclayer._put_it_where_it_is_shown`)
  because MuPDF's placement is wrong on turned pages with offset crop boxes.
  `tests/test_roundtrip.py` compares CalcForge, MuPDF and pdfium page by page. Only a digitally signed file is appended to
  (`io/pdfsave.py`, `Document.signed_source`). What decides how a file opens
  is what it holds, never what it is called: `project.carries_a_document(path)`.
- **A markup is a real annotation.** `io/annotate.py` builds each one in the
  PDF's own vocabulary — the plain dictionaries and names of `markforge/pdf`,
  not any library's object types — so the same description can be appended by
  the incremental writer or handed to pypdf when a document is assembled. A
  cloud is a `/Square` or `/Polygon` with a `/BE` cloudy border; a callout is a
  `/FreeText` with `/CL` and the right `/IT`; a dimension is a `/Line` with a
  `/Measure` dictionary. Each carries its own appearance stream, which is why
  the print tests read markup text out of the appearance streams
  (`Printed.text()` in `tests/test_output.py`) rather than from the page.
- **The page's own line work is not a markup.** An imported PDF's vectors come
  in as items so that a measurement can snap to the end of a beam, flagged
  `from_drawing`. They are locked, they sit below every markup, they are
  written as part of the page rather than as annotations, they are not what a
  snapshot copies, and they are caught hold of but never offered as an
  alignment guide. Four places ask about that flag; keep them in step.
- **`core/typography.py` sizes every page font in pixels rather than points.**
  Page coordinates are PostScript points, so a font sized in points would come
  out four times too large on a 300 dpi printer.

---

## 3. How to verify work

**The CalcForge gate, before every push:** the whole suite (MarkForge's
tests and WebSMath's, which live in `tests/calc/`) and
`python -m markforge.calc.tools.mutation_check` (14 of 14 caught). The
`.sm` reader in `tests/calc/smfile.py` is test-only: it lets the tests
check answers against SMath's own example files; the app has no `.sm`
support; it also keeps SMath's page model (paper, header/footer layers),
which the app no longer has. WebSMath's old window is gone (phase 6): its
tests drive the CalcForge window (`tests/calc/test_calcforge_window.py`),
and `tests/calc/test_same_drawing.py` holds the SHA-256 of WebSMath's
drawing code — `calc/ui/layout.py` and `calc/ui/region_item.py` must stay
byte for byte WebSMath's. (That is also why `Region` keeps the inert
picture/field attributes that code reads.)

```bash
# the whole suite (about 800 tests, four minutes — run it in background)
xvfb-run -a python -m pytest -q --tb=line

# one area while working
xvfb-run -a python -m pytest -q --tb=short tests/test_usability.py -k callout

# a long randomised session; seeds are reproducible
xvfb-run -a python tools/session_fuzz.py 41 300
```

| File | What it promises |
|---|---|
| `test_pdf_engine.py` | The PDF engine, against real files from other software |
| `test_format.py` | What a saved document is: a PDF, the source page untouched, markups as annotations |
| `test_btx.py` | Bluebeam tool sets, read from the real `.btx` files in `btx/` |
| `test_items.py` | Serialisation, geometry and layout of every markup type |
| `test_app.py` | The window: tools, panels, undo, files, printing |
| `test_canvas.py` | One continuous scroll through every page |
| `test_layout.py` | Panels and toolbars: pinning, hiding, moving, remembering |
| `test_usability.py` | Real pointer and keyboard sequences through the viewport |
| `test_walkthrough.py` | A whole review, start to finish |
| `test_output.py` | Exported PDFs, read back and measured |

`tests/test_usability.py` is the important one: **every test in it drives the
real Qt event queue** — press/release pairs, the four-event double-click
sequence, context-menu events, key events with their text. Calling a handler
directly hides exactly the bugs that file exists to catch. Write new tests that
way.

`pytest.ini` already passes `-q`, so a second `-q` on the command line makes it
`-qq` and suppresses the "N passed" summary line. The exit code still tells you.

The suite prints `TypeError: Unknown return type ... (that may be a signal)`
lines on teardown. That is PySide noise, not a failure. Grep them out:
`| grep -vE "Unknown return type|propagateSize"`.

**Task-list status belongs to the user.** Agents may validate behaviour, report
evidence, and add or clarify requirement text, but must never mark a Markdown
task complete or change any status.

### A note on segfaults

A Python exception raised inside a Qt event override does not raise — shiboken
stores it, and after enough of them the process dies with a segmentation fault
somewhere unrelated. If the suite segfaults, the cause is almost always a
missing attribute or a `KeyError` inside a `keyPressEvent`, `paint` or
`eventFilter`. Run the failing file with `-x` and read the first error rather
than the crash.

---

## 4. How the work is tracked — follow this exactly

### The requirements register and user status sheet

`docs/tasklist.md` holds every feature and bug the user has asked for, grouped
by topic. `docs/tasklist.xlsx` is a spreadsheet copy where column A is the
user's completion field and column B is the task text. The Markdown is the
agent-facing requirements register; the workbook is the user-owned status
record. The rules are:

1. **Nothing is ever deleted.** Not a completed item, not a superseded one, not
   a withdrawn one.
2. **When a later message changes an earlier request, rewrite the existing
   line** to state the current intended behaviour. Do not retain competing
   alternatives in the active task.
3. **Every new request from the user goes in as soon as it arrives**, before
   you start work on it, so nothing is lost if the session ends.
4. **Never mark work complete or change status.** Only the user changes
   completion status in `docs/tasklist.xlsx`; agents instead report their
   verification result and leave task state unchanged.
5. **When the user withdraws a requirement, move it to the Withdrawn section**
   with the instruction that withdrew it, struck through and kept. A withdrawn
   item is not a completed one and must never be counted as one.
6. Items about how the agent works remain requirements, with an honest note
   where a platform limitation prevents the requested behaviour.

`docs/COMPLETED_TASKS.md` and `docs/UNADDRESSED_TASKS.md` are the evidence and
review registers asked for in §27 of the task list. Both are snapshots with a
date on them; neither changes any status.

### The per-session task tool

Use `TaskCreate` / `TaskUpdate` for the handful of things you are working on
right now. That list is scratch — it does not survive, and it is not the
record. `docs/tasklist.md` is the record.

### Agent operating protocol

1. Read this handover and the current open requirements in `docs/tasklist.md`.
2. When the user gives a new requirement or defect, add or consolidate it in
   the task list immediately, using the existing section structure.
3. Do not mark any task complete, edit user-owned completion status, or claim a
   feature is finished without current evidence.
4. For implementation work, find the controlling code path, make the smallest
   safe change, and validate it through the real Qt event queue. Exercise mouse
   movement, clicks, drags, modifier keys, keyboard navigation, shortcuts,
   focus changes and Escape where relevant.
5. Preserve existing user changes, keep commits scoped, and report the exact
   validation performed along with any remaining limitation.

### If the session is going to end

The container is ephemeral and a usage limit ends a turn without warning, so
the rule is that unpushed work is lost work — commit and push each finished
piece rather than batching. Nothing in the environment resumes a session
automatically when a limit lifts. What is available is a scheduled wake-up
(`send_later` on the claude-code-remote server), which can bring a session back
at a chosen time; it does not detect the limit, so it is a way of arranging to
come back rather than a way of not stopping. Leave the register and the branch
in a state somebody else could pick up from, because they may have to.

### Commits

- Commit and push **continuously** — every completed piece of work, not at the
  end. The container is ephemeral; unpushed work is lost work.
- `git push -u origin claude/admiring-archimedes-i371m1`
- Commit messages: a short title, then prose explaining **what was wrong and
  why the new behaviour is right**. The user reads them. Look at the recent log
  for the register.
- Never put a model identifier in a commit message, a PR, a code comment or
  anything else pushed to the repository.
- Do not open a pull request unless asked.

### Talking to the user

- Report what was actually done, with the failure that caused it. If a report
  turns out to be against an older build, say so plainly rather than claiming a
  new fix.
- Do not re-litigate. If they contradict an earlier instruction, the new one
  wins — update the task list line and move on.

---

## 5. The parts most likely to bite you

**Saving (`io/pdfbase.py`, `io/calclayer.py`, `io/pdfsave.py`).** Anything
new that paints onto the sheet must be painted by `render_page(layer="sheet")`
so it lands in the tagged sheet layer — anything drawn into the page any other
way is not taken off on reopen and doubles up on the next save.
`tests/test_calc_saving.py::test_repeated_saves_do_not_grow_the_file` guards
it. The equations' layer is drawn at 96 dpi (`CALC_DPI`): SMath's fonts are
in points and Qt resolves points by the device's resolution, so any other
resolution draws letters a different size from the layout. A signed file is
only appended to while it is still that file's pages in order
(`pdfsave.source_bytes`); anything else is written afresh with a note that the
signature no longer applies. Object numbers belong to the file they are in,
so anything brought across from the scratch appearance PDF goes through
`copy_into`, which renumbers as it copies.

**Snapshots (`ui/scene.py` `picture_items`, `io/pdfsnapshot.py`).** A
snapshot is the page's PDF drawing read from the file (`source_paths`) plus
one `PdfSvgItem` of everything drawn over it (`drawn_over`: the frame
rendered into a 96-dpi PDF and read back as SVG with text as outlines). Don't
go back to rebuilding copies of the markups: they draw differently away from
their page. `tests/test_snapshot_fidelity.py` compares every case.

**Leaders (`markforge/items/text.py`).** A `_Leader` stores `tip`, `side`,
`reach`, `kind` and `cloud`. The hinge is *never stored* — it is computed every
time from the side and the reach, which is what keeps it perpendicular and
automatic. A leader is either an `arrow` (ends in a head) or a `cloud` (ends at
a region drawn round with a cloud, no head). A text box, a call-out and a cloud
call-out are **one object in three states**: the last leader coming off makes a
text box, the first going on makes a call-out (`MainWindow.becomes_a_callout` /
`becomes_a_text_box`).

**`.btx` import.** Bluebeam tool sets are XML with zlib-compressed, hex-encoded
PDF annotation dictionaries. Sample files are in `btx/` and the importer is
tested against them, not against synthetic files. X/Y in a `.btx` annotation is
the **bottom-left** corner.

**Snapping (`ui/view.py`).** Three sources with their own switches — the
markups drawn here, the page's own line work, and the alignment guides — and
crossings, which are computed only from the segments passing near the pointer
because a sheet holds thousands of them. `MOST_CROSSING_SIDES` is what keeps
one mouse move from becoming a million comparisons.

**Focus.** Text editing is sensitive to focus changes from right-click menus
and toolbar actions. The keys belonging to what is being written go down to the
scene: the `_editing_item` branch of `PageView.keyPressEvent` must end in
`super().keyPressEvent(event)`, or Backspace and Enter arrive nowhere. Exercise
focus-loss and return paths whenever this area changes.

---

## 6. Current status

`docs/tasklist.md` is the active requirements register and `docs/tasklist.xlsx`
is the user-owned completion record. Agents add and consolidate requirements
but never change their status. Begin with the user's newest report, find or add
its task, then validate behaviour through real canvas, keyboard and menu
interaction before changing code.

The suite is green and the fuzzer runs clean. Prioritise anything that leaves
the UI stuck or prevents ordinary editing, and anything that would make a saved
file wrong — those are the two failures that cost the user real work.
