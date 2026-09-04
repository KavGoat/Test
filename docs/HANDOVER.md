# CalcForge — start here

**If you are an agent picking this project up, read this file first and read
nothing else until you have.** It is the whole context you need: what the app
is, how it is built, what is done, what is not, and how the work is tracked.
It exists so that no session has to re-read three days of chat to be useful.

- Repository: `KavGoat/Test`
- Branch: **`claude/engineering-calc-markup-app-2twiqs`** — all work goes here.
  Never push to another branch without being asked.
- The living task list: **`docs/tasklist.md`** — read it, work from it, keep it
  updated. Rules for it are below and repeated in its own header.

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

**A box in the task list is only ticked when the behaviour is in the code
*and* held there by a test.** Not "I wrote it", not "it looks right".

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

### `docs/tasklist.md` is the single source of truth

It holds every feature and bug the user has ever asked for, grouped by topic,
with `- [ ]` / `- [x]` boxes. The user asked for it to live in the repository
and be kept current. The rules, which they set:

1. **Nothing is ever deleted.** Not a completed item, not a superseded one.
2. **When a later message contradicts an earlier one, rewrite the existing
   line** to say what was most recently asked for — and say in the line that
   it was rewritten and why. Do not add a second, contradicting line.
   (Example already in the file: the space-in-an-equation rule, which was
   reversed. The line records both the old rule and the reversal.)
3. **Every new request from the user goes in as soon as it arrives**, before
   you start work on it, so nothing is lost if the session ends.
4. **Tick a box only when code + test exist.** If a thing turns out to have
   been built already, tick it and append what you checked.
5. Items that are about *how the agent works* rather than about the app stay
   unticked, with the honest answer written into the line.

### The per-session task tool

Use `TaskCreate` / `TaskUpdate` for the handful of things you are working on
right now. That list is scratch — it does not survive, and it is not the
record. `docs/tasklist.md` is the record.

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

**The equation space rule.** A space cannot be typed into a calculation at
all — it is refused and the status bar says why. Shift+Space turns a line
still being entered into a text box. This was reversed once (it used to
convert on any space); the task list line records the reversal.

**`.btx` import.** Bluebeam tool sets are XML with zlib-compressed,
hex-encoded PDF annotation dictionaries. Sample files are in the repo and the
importer is tested against them, not against synthetic files. X/Y in a `.btx`
annotation is the **bottom-left** corner.

**Focus.** The view no longer ends an edit when it loses keyboard focus — a
right-click menu or a toolbar click used to close the line being typed, which
is what made Backspace, `=` and Enter look like broken keys. If you touch
`focusOutEvent`, do not put that back.

---

## 6. Where things stand

As of this writing: **191 of 203 boxes in `docs/tasklist.md` are ticked.**
The suite is green and three seeded fuzz runs are clean.

The open items are listed in `docs/tasklist.md` — search it for `- [ ]`.
At the time of writing they are, in rough priority order:

1. Orange square placement markers still appearing on markups.
2. Calculation editing: `=` misbehaving, text that cannot be deleted, the gap
   before `=`, and — the big one — **making the editing view and the final
   view genuinely identical**, verified by typing.
3. Unit editing zooming in instead of changing in place; the unit list
   appearing in odd places.
4. Menu cleanup: labels down to one or two words everywhere, "Property mode"
   as the name, and the calculation right-click group ("Figures on this
   line", "Edit…", "Show this result in…", "Keep as one block",
   "Self-contained block", split/merge) taken out and what is worth keeping
   moved to the main menu bar.
5. Placement anchors: call-out text box by its left middle; images,
   snapshots, tool-set items, groups and cloud items by their bottom left.
6. My Tools: a property-mode entry shows a default icon in that style and
   carries a "properties" tag.
7. Two process items about token limits and background tasks, which are about
   how the agent works and carry their honest answer in the line.

None of these have been started. They were logged, deliberately, without
being built — the user asked for the batch to be written down rather than
worked on, so the next session starts from a full list and a green suite.

Two of these are worth a word of warning. **"One style for editing and
final"** is not a small change — it is the thing the user has raised most
often and it means the box tree must be the only view of a calculation, with
the editor purely a keystroke sink. Verify it by driving real key events and
comparing what is painted, not by reading the code. And **the orange squares**
have been reported more than once, so search for every path that paints a
placement marker rather than fixing the first one you find.
