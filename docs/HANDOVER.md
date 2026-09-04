# CalcForge — start here

**If you are an agent picking this project up, read this file first.** It gives
the product context, code map, validation approach and task-tracking rules
needed to work safely without re-reading earlier chat.

- Repository: `KavGoat/Test`
- Branch: **`claude/engineering-calc-markup-app-2twiqs`** — all work goes here.
  Never push to another branch without being asked.
- The living task list: **`docs/tasklist.md`** — read it, work from it, keep it
  updated. `docs/tasklist.xlsx` is the user's companion status sheet: column A
  is blank for open work and `1` for user-confirmed completion. Rules for both
  are below and repeated in the task-list header.

---

## 1. What the app is

CalcForge is a PySide6 (Qt 6) desktop application for a **New Zealand
structural engineer**. It puts three things that are normally three programs
onto one page-by-page A4 document:

| Part | Behaves like | What it must do |
|---|---|---|
| Calculations | **SMath** | Unit-aware maths, typeset as it is typed, evaluated in reading order down the page |
| Markup | **Bluebeam Revu** | Every annotation tool, tool sets, `.btx` import, PDF pages underneath |
| Spreadsheet | **Excel** | Real formulas, fill handle, paste from Excel with formulas intact |

The three share data: a spreadsheet cell can read a calculated variable and
vice versa. The document is discrete pages (not an infinite canvas), A4 by
default, and prints to PDF preserving layout.

**The numbers must be right.** The outputs are used to design real buildings.
There is a background verifier that independently re-checks values and units
and flags disagreements. Never weaken it, and never make a calculation change
without running the validation suite.

### Who the user is, and how they work

- A practising structural engineer, not a programmer. They describe what they
  want in the language of Bluebeam and SMath — if a request seems vague, the
  answer is usually "whatever Bluebeam does".
- They send **photographs of their screen** as bug reports. Read them
  carefully; they often show the exact defect in the corner of the frame.
- They type quickly and with typos. Read intent, not spelling: "calcition
  line block, = spazzes out" is a real, specific bug report.
- They test the app themselves between sessions and come back with lists.
  Take every item seriously and log every one (see §4).

### Standing constraints

- **No copying Bluebeam's icon artwork.** Match its conventions, names,
  shortcuts and behaviour — draw the icons.
- Labels are **one or two words**, like Bluebeam's. The explanation goes in
  the tooltip, never in the button.
- The user cannot be shown a video; do not suggest one.

---

## 2. How the code is laid out

```
calcforge/
  core/        the engine, no Qt beyond QPointF-style value types
    engine.py        parse, compile and evaluate a statement; friendly_error()
    units.py         pint registry, unit ladders, formatting, UNIT_MENU
    mathrender.py    the box tree: typesets maths, and maps a click back to a
                     character (offset_in / caret_in) — this is what makes
                     clicking into a fraction work
    document.py      Document, Page, PageSetup, layers, assets
    spreadsheet.py   Sheet: cells, formulas, sizes (DEFAULT_COL_WIDTH etc.)
    excelxml.py      Excel's XML clipboard flavour, R1C1 -> A1
  items/       every markup, all deriving from MarkupItem (items/base.py)
    base.py          Style, handles, hatches, dash arrays, cloud_path()
    text.py          _TextBase, TextItem, CalloutItem, NoteItem, StampItem,
                     and _Leader — the leader model (see §5)
    shapes.py        RectItem, PolyItem — corners, arcs, break symbols
    mathitem.py      MathItem: the calculation region and its editor
    tableitem.py     TableItem: the spreadsheet on the page
    measure.py, snapshot.py, image.py, plot.py, count.py, contents.py
  ui/
    mainwindow.py    MainWindow: menus, commands, panels, page commands
    view.py          PageView: the canvas — every mouse and key gesture
    scene.py         DocumentScene, PageFrame: pages stacked down one canvas
    panels.py        the docked panels; toolsets.py, rail.py, docks.py
    dialogs.py       every dialog
    tools.py         the tool table: key, label, icon, shortcut, factory
    shortcuts.py     DEFAULT_BINDINGS and the shortcut manager
    theme.py (calcforge/theme.py) light and dark stylesheets
  io/          project (.cfx), pdfio, pdfvector, btx (Bluebeam tool sets),
               export
tests/         pytest; see §3
tools/         session_fuzz.py — a long randomised session against the app
docs/          this file, tasklist.md, interface.md, backlog.md,
               what-matters.md
```

### Things worth knowing before you change anything

- **The canvas is one scene holding every page.** Scrolling is continuous.
  A gesture is always aimed at a page frame — use `view.frame_at(point)`,
  never assume the current page.
- **Rotating the view rotates the pages on the canvas, not the view
  transform.** `apply_view_transform()` holds the zoom only, so the
  scrollbars keep pointing the way they scroll.
- **A calculation is typeset by a box tree and edited by an invisible
  `QGraphicsTextItem`.** The editor holds the characters as one flat line;
  what you see is painted from the box tree. `place_caret()` maps a click
  back through the box tree, which is why clicking into a fraction works.
  Qt's own hit-testing on that invisible editor is meaningless — never use it.
- **Undo is a snapshot stack.** `view.begin_snapshot(frames)` … change …
  `view.commit_snapshot("Label")`. One gesture is one step.
- **Settings** are `QSettings("CalcForge", "CalcForge")`. The suite sandboxes
  them; do not call `sync()` to "fix" ordering — that broke the layout tests
  once already.

---

## 3. How to verify work

```bash
# the whole suite (about 1100 tests, several minutes — run it in background)
xvfb-run -a python -m pytest -q --tb=line

# one area while working
xvfb-run -a python -m pytest -q --tb=short tests/test_usability.py -k callout

# a long randomised session; seeds are reproducible
xvfb-run -a python tools/session_fuzz.py 41 300
```

`tests/test_usability.py` is the important one: **every test in it drives the
real Qt event queue** — press/release pairs, the four-event double-click
sequence, context-menu events, key events with their text. Calling a handler
directly hides exactly the bugs that file exists to catch. Write new tests
that way.

The suite prints `TypeError: Unknown return type ... (that may be a signal)`
lines on teardown. That is PySide noise, not a failure. Grep them out:
`| grep -vE "Unknown return type|propagateSize"`.

**Task-list status belongs to the user.** Agents may validate behavior, report
evidence, and add or clarify requirement text, but must never mark a Markdown
task complete or change any status. The user maintains completion in
`docs/tasklist.xlsx` column A and can explicitly request a synchronization.

### One known flake

`tests/test_layout.py::test_everything_that_can_be_arranged_comes_back`
and `::test_a_rolled_up_panel_comes_back_rolled_up` fail intermittently in
a **full** run and pass every time on their own — including when run after
every file that precedes them. It is a race, not pollution: both save an
arrangement and immediately build a second window to check it came back,
and there is a 1.5-second layout-save timer that can fire in between. It is
logged in `docs/tasklist.md`. Do not read a green full run as proof it is
fixed, and do not read these two as your own breakage without checking them
in isolation first.

---

## 4. How the work is tracked — follow this exactly

### The requirements register and user status sheet

`docs/tasklist.md` holds every feature and bug the user has asked for, grouped
by topic. `docs/tasklist.xlsx` is a spreadsheet copy where column A is the
user's completion field and column B is the task text. The Markdown is the
agent-facing requirements register; the workbook is the user-owned status
record. The rules are:

1. **Nothing is ever deleted.** Not a completed item, not a superseded one.
2. **When a later message changes an earlier request, rewrite the existing
  line** to state the current intended behavior. Do not retain competing
  alternatives in the active task.
3. **Every new request from the user goes in as soon as it arrives**, before
   you start work on it, so nothing is lost if the session ends.
4. **Never mark work complete or change status.** Only the user changes
  completion status in `docs/tasklist.xlsx`; agents instead report their
  verification result and leave task state unchanged.
5. Items about how the agent works remain requirements, with an honest note
  where a platform limitation prevents the requested behavior.

### The per-session task tool

Use `TaskCreate` / `TaskUpdate` for the handful of things you are working on
right now. That list is scratch — it does not survive, and it is not the
record. `docs/tasklist.md` is the record.

### Agent operating protocol

1. Read this handover and the current open requirements in `docs/tasklist.md`.
2. When the user gives a new requirement or defect, add or consolidate it in
  the task list immediately, using the existing section structure.
3. Do not mark any task complete, edit user-owned completion status, or claim
  a feature is finished without current evidence.
4. For implementation work, find the controlling code path, make the smallest
  safe change, and validate it through the real Qt event queue. Exercise
  mouse movement, clicks, drags, modifier keys, keyboard navigation,
  shortcuts, focus changes and Escape where relevant.
5. Preserve existing user changes, keep commits scoped, and report the exact
  validation performed along with any remaining limitation.

### Commits

- Commit and push **continuously** — every completed piece of work, not at
  the end. The container is ephemeral; unpushed work is lost work.
- `git push -u origin claude/engineering-calc-markup-app-2twiqs`
- Commit messages: a short title, then prose explaining **what was wrong and
  why the new behaviour is right**. The user reads them. Look at the recent
  log for the register.
- Do not open a pull request unless asked.

### Talking to the user

- Report what was actually done, with the failure that caused it. If a report
  turns out to be against an older build, say so plainly rather than claiming
  a new fix.
- Do not re-litigate. If they contradict an earlier instruction, the new one
  wins — update the task list line and move on.

---

## 5. The parts most likely to bite you

**Leaders (`calcforge/items/text.py`).** A `_Leader` stores `tip`, `side`,
`reach`, `kind` and `cloud`. The hinge is *never stored* — it is computed
every time from the side and the reach, which is what keeps it perpendicular
and automatic. A leader is either an `arrow` (ends in a head) or a `cloud`
(ends at a region drawn round with a cloud, no head). A text box, a call-out
and a cloud call-out are **one object in three states**: the last leader
coming off makes a text box, the first going on makes a call-out
(`MainWindow.becomes_a_callout` / `becomes_a_text_box`).

**The equation space rule.** In a single calculation line, units attach
directly to their number (for example `5kPa`, rendered as `5·kPa`). Typing a
space converts the current fresh calculation entry into plain text. Keep this
rule aligned with the active task-list requirement and validate it through
real key events.

**`.btx` import.** Bluebeam tool sets are XML with zlib-compressed,
hex-encoded PDF annotation dictionaries. Sample files are in the repo and the
importer is tested against them, not against synthetic files. X/Y in a `.btx`
annotation is the **bottom-left** corner.

**Focus.** Equation and text editing are sensitive to focus changes from
right-click menus and toolbar actions. Exercise focus-loss and return paths,
including Backspace, `=`, arrow navigation and Escape, whenever these areas
change.

---

## 6. Current status

`docs/tasklist.md` is the active requirements register and
`docs/tasklist.xlsx` is the user-owned completion record. Agents add and
consolidate requirements but never change their status. Begin with the user's
newest report, find or add its task, then validate behavior through real
canvas, keyboard and menu interaction before changing code.

Prioritize safety-critical calculation/unit behavior and workflows that leave
the UI stuck or prevent ordinary editing. For interactive work, use the real
Qt event queue and test pointer movement, modifier keys, focus changes,
keyboard arrows, shortcuts and Escape cancellation rather than relying only on
direct method calls.
