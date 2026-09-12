# MarkForge — start here

## Latest review: 2026-09-11–12

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
- Branch: **`claude/markforge-mupdf-pdf-handling-vpyj1t`** — all work goes here. Never push to
  another branch without being asked.
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

**It used to be more than this.** Until 2026-09-07 it also did unit-aware
calculations, spreadsheets and plots, and the file format was `.cfx`. All of
that has been withdrawn by the user, along with markup review states, replies
and layers. If you find a reference to any of it, it is a leftover — take it
out. `docs/tasklist.md` has a **Withdrawn** section recording what went and
which instruction withdrew it; do not build any of it back.

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
  core/        no Qt beyond QPointF-style value types
    document.py      Document, Page, PageSetup, PageScale, assets
    units.py         pint registry, unit ladders, formatting, UNIT_MENU
    typography.py    page fonts sized in pixels, not points (see below)
    spelling.py      New Zealand English, checked against a packed word list
  items/       every markup, all deriving from MarkupItem (items/base.py)
    base.py          Style, handles, hatches, dash arrays, cloud_path()
    text.py          _TextBase, TextItem, CalloutItem, NoteItem, StampItem,
                     and _Leader — the leader model (see §5)
    shapes.py        RectItem, PolyItem — corners, arcs, break symbols
    measure.py       MeasureItem and CountItem: length, area, dimension, count
    media.py, snapshot.py, contents.py
  ui/
    mainwindow.py    MainWindow: menus, commands, panels, page commands
    view.py          PageView: the canvas — every mouse and key gesture
    scene.py         DocumentScene, PageFrame: pages stacked down one canvas
    panels.py        the docked panels; toolsets.py, rail.py, docks.py
    dialogs.py       every dialog
    tools.py         the tool table: key, label, icon, shortcut, factory
    shortcuts.py     DEFAULT_BINDINGS and the shortcut manager
    theme.py (markforge/theme.py) light and dark stylesheets
  io/          pdfbase (what a saved document is), pdfsave (the incremental
               update), project (open and save), annotate (markups as real PDF
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
- **A saved document is a PDF, and saving adds to it.** `io/pdfsave.py` writes
  an incremental update when the document is one source PDF and its markups:
  same source, pages in order, at their own size and full strength, printable,
  nothing flattened in, no grid and no running text. Anything else has to be
  painted, so `io/pdfbase.py` assembles it page by page as it always did. Both
  put the record — everything a PDF cannot hold — inside the file as an
  embedded attachment. What decides how a file opens is what it holds, never
  what it is called: `project.carries_a_document(path)`.
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
- `git push -u origin claude/markforge-mupdf-pdf-handling-vpyj1t`
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

**The incremental save (`io/pdfsave.py`).** `source_bytes(document)` decides
whether this document is an addition to one file or a new file. Every condition
in it is there because something has to be painted otherwise — a grid, a
running header, a flattened markup, a dimmed page, a page fitted to different
paper. If you add anything that paints onto the sheet, add its condition there
too, or a save will silently lose it. Object numbers belong to the file they
are in, so anything brought across from the scratch appearance PDF goes through
`copy_into`, which renumbers as it copies.

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
