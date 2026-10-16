# Exercise round 1: every command, by mouse and keyboard, checked by eye

Exhaustive-interaction tester, 2026-10-16, on b31a4dd (branch
`qa-exercise-round1`). This follows QA_PLAN.md §5. Nothing in the app was
changed: the only workarounds are in the harness, and each one is listed
under "Harness notes".

## What was run

- **`tools/qa/exercise.py`** drives every line of
  `docs/qa/feature_inventory.md` through the UI path a person uses:
  - a mouse click at the widget's geometry on toolbar buttons, the status bar,
    the corner and the formula bar;
  - a click on the menu-bar title and then on each item, and the same again with
    Alt+mnemonic and arrow keys;
  - a real right-press, `QContextMenuEvent` and a live popup click, for every
    right-click menu;
  - `QTest.keyClick` for every shortcut;
  - clicks and typing in panel controls, and real drags for mouse gestures.

  Each run starts from a fresh document in a named state taken from a library
  of about 60 fixtures. Modal dialogs are caught by a timer, photographed, have
  their title and labels recorded, and are cancelled; safe ones are also OK'd.
  Each run records:
  - exceptions (excepthook) and Qt critical messages;
  - wall time (slow means over 100 ms);
  - the visible change (image diff and box);
  - whether the document changed, and whether one undo restores it;
  - before and after screenshots.
- **The inventory was regenerated at HEAD.** `tools/qa/inventory.py` gives
  1214 lines, against the brief's 1181: 118 lines were renamed or moved and 151
  are new. The live walk also found **241 extra right-click and button-menu
  entries** that the inventory never opened (ids X0001…X0241), such as row and
  column heading menus, filter buttons, style buttons and plot menus.
  `tools/qa/commands.json` has 1455 commands and **1931 entry points**.
- **Two full runs** were made, in light and in dark (2153 runs each, with two
  worker processes). Each produced contact sheets with before, after and dialog
  panes. All of them were reviewed by eye: 573 light and 574 dark (the dark ones
  as 2×2 tiles).
  - Contact sheets:
    `/tmp/claude-0/-home-user-Test/612018b6-a7e0-52c2-960e-e0bdb34e3bba/scratchpad/qa/exercise/{light,dark}/<area>/sheet_NNN.png`.
    Below, a path such as `light/menu/sheet_017` is relative to that folder.
  - Raw results: `.../scratchpad/qa/run6/results.json` (light) and
    `.../scratchpad/qa/run7/results.json` (dark).
- **`tests/test_every_command.py`** is parametrized over commands.json and
  gives 1931 tests. Each checks the mechanical part: no exception, no Qt
  critical message, no hang (two-minute faulthandler), and that one undo
  restores the document. The 60 jobs that fail now are xfail with their finding
  in `tools/qa/known_failures.json`, so a fix shows up as XPASS. The window
  manager's caption buttons are skipped. A smoke subset passed (`-n 2`).

Reproduce:
```
python tools/qa/exercise.py build                  # inventory → commands.json
python tools/qa/exercise.py run --out DIR --workers 2 [--theme dark]
python tools/qa/exercise.py sheets --out DIR --to SHEETS [--theme dark]
python tools/qa/exercise.py report DIR SHEETS
python tools/qa/exercise.py try M0007#0 …          # one entry, with shots
python -m pytest tests/test_every_command.py -n 2 -p no:cacheprovider
```

## Counts (light run; dark is identical except for one flaky menu, D0062)

| Area | Commands (inventory lines) exercised |
|---|---:|
| Menu bar | 197 |
| Toolbars | 177 |
| Right-click menus | 368 |
| Panels | 109 |
| Dialogs | 77 |
| Keys | 242 |
| Mouse | 44 |
| Extra (not in the inventory) | 241 | 

 | Area | Entry point | Runs | Passed | Failed | Disabled as expected | Not drivable |
|---|---|---:|---:|---:|---:|---:|
| Menu bar | menu (mouse) | 243 | 238 | 3 | 2 | 0 |
| Menu bar | menu (Alt+keys) | 193 | 188 | 3 | 2 | 0 |
| Menu bar | shortcut | 69 | 69 | 0 | 0 | 0 |
| Toolbars | toolbar | 114 | 101 | 12 | 1 | 0 |
| Toolbars | toolbar menu | 23 | 23 | 0 | 0 | 0 |
| Toolbars | status/corner/formula bar | 29 | 26 | 3 | 0 | 0 |
| Toolbars | bar button menu | 11 | 6 | 5 | 0 | 0 |
| Toolbars | shortcut | 25 | 25 | 0 | 0 | 0 |
| Right-click menus | menu (mouse) | 63 | 61 | 2 | 0 | 0 |
| Right-click menus | right-click | 513 | 499 | 2 | 12 | 0 |
| Panels | menu (mouse) | 8 | 8 | 0 | 0 | 0 |
| Panels | panel control | 67 | 62 | 5 | 0 | 0 |
| Panels | panel buttons | 71 | 64 | 0 | 0 | 7 |
| Panels | panel menu | 1 | 1 | 0 | 0 | 0 |
| Panels | rail button | 8 | 8 | 0 | 0 | 0 |
| Panels | panel title bar | 32 | 32 | 0 | 0 | 0 |
| Dialogs | menu (mouse) | 47 | 47 | 0 | 0 | 0 |
| Dialogs | toolbar | 3 | 2 | 1 | 0 | 0 |
| Dialogs | right-click | 58 | 58 | 0 | 0 | 0 |
| Dialogs | panel control | 2 | 2 | 0 | 0 | 0 |
| Dialogs | mouse gesture | 3 | 3 | 0 | 0 | 0 |
| Dialogs | by code | 2 | 2 | 0 | 0 | 0 |
| Keys | shortcut | 227 | 222 | 5 | 0 | 0 |
| Keys | canvas key | 13 | 13 | 0 | 0 | 0 |
| Keys | no key bound | 43 | 0 | 0 | 0 | 43 |
| Mouse | mouse gesture | 44 | 38 | 0 | 0 | 6 |
| Extra (not in the inventory) | right-click | 241 | 215 | 20 | 6 | 0 |
| **All** | | **2153** | **2013** | **61** | **23** | **56** | 

The counts:

- **Inventory lines.** 1214 inventory lines plus 241 extras, with every line
  driven at least once. 2153 runs cover the 1931 entry points, the extra runs
  being the value lists of commands with several choices.
- **What "passed" means.** The command was reached where a person looks, with
  no exception, no Qt critical message, no hang, and with one undo restoring
  any document change.
- **Not drivable.** 43 key lines have no key bound, which is correct: the
  command has no key. Seven panel buttons and six gestures are not on screen in
  the fixture state.
- **Exceptions and timings.** 22 runs had exceptions (all F-03). There were
  0 Qt critical messages and 0 crashes or hangs in the final runs. 588 runs
  took over 100 ms, 37 over 500 ms and 14 over 1 s (load average 6–16 on 4
  cores, so read single times with care; the repeated slow ones are in F-14).
- **Documents changed with no undo step.** There were 76 commands. Most are
  equation symbol keys typed while editing (expected: the edit commits as one
  step) and view toggles stored in the document (Grid, Snap, Margins, Name
  Tags). The real ones are listed in F-08.

### Mechanical failures (light run, same in dark)


 | Command | Entry | State | What happened | Sheet |
|---|---|---|---|---|
| M0125 24 choices: Text box, Callout, Cloud+, Note, Stamp | menu: Tools ▸ Markup ▸ * | fresh | one undo does not restore | menu/sheet_082.png |
| M0125 24 choices: Text box, Callout, Cloud+, Note, Stamp | menu: Tools ▸ Markup ▸ * | fresh | one undo does not restore | menu/sheet_082.png |
| M0125 24 choices: Text box, Callout, Cloud+, Note, Stamp | menu: Tools ▸ Markup ▸ * | fresh | one undo does not restore | menu/sheet_082.png |
| M0172 Function… | Alt+keys: Calculation ▸ Function… | equation_editing | not reached: Alt+letter opened no menu | menu/sheet_112.png |
| M0174 Constants… | Alt+keys: Calculation ▸ Constants… | equation_editing | not reached: Alt+letter opened no menu | menu/sheet_113.png |
| M0175 Operator… | Alt+keys: Calculation ▸ Operator… | equation_editing | not reached: Alt+letter opened no menu | menu/sheet_114.png |
| T0061 Text box | toolbar Tools: Text box | fresh | one undo does not restore | toolbars/sheet_022.png |
| T0062 Callout | toolbar Tools: Callout | fresh | one undo does not restore | toolbars/sheet_022.png |
| T0063 Cloud+ | toolbar Tools: Cloud+ | fresh | one undo does not restore | toolbars/sheet_022.png |
| T0075 Opacity: the whole markup — line, fill and hatch t | toolbar Style: Opacity: the whole markup — line, fill and hatch togeth | rect | one undo does not restore | toolbars/sheet_026.png |
| T0077 Dash spacing: how long the dashes and gaps are, wh | toolbar Style: Dash spacing: how long the dashes and gaps are, whateve | rect | one undo does not restore | toolbars/sheet_026.png |
| T0078 Line width | toolbar Style: Line width | rect | one undo does not restore | toolbars/sheet_026.png |
| T0080 Fill opacity: how solid the fill is (not the line  | toolbar Style: Fill opacity: how solid the fill is (not the line or th | rect | one undo does not restore | toolbars/sheet_027.png |
| T0084 End size: how big the line ends are, whatever the  | toolbar Style: End size: how big the line ends are, whatever the line  | line | one undo does not restore | toolbars/sheet_028.png |
| T0085 Corner radius: 0 is square | toolbar Style: Corner radius: 0 is square | rect | not reached: the control is not on screen (overflow or hidden) | toolbars/sheet_028.png |
| T0089 Hatch opacity: how solid the hatch lines are (not  | toolbar Style: Hatch opacity: how solid the hatch lines are (not the f | rect | not reached: the control is not on screen (overflow or hidden) | toolbars/sheet_029.png |
| T0092 (unlabelled) | toolbar Style: (unlabelled) | textbox | one undo does not restore | toolbars/sheet_030.png |
| T0114 Continuous | widget_menu: Status bar | fresh | not reached: no 'Continuous' in the Status bar | toolbars/sheet_036.png |
| T0115 Side-by-Side | widget_menu: Status bar | fresh | not reached: no 'Continuous' in the Status bar | toolbars/sheet_036.png |
| T0116 Continuous Side-by-Side | widget_menu: Status bar | fresh | not reached: no 'Continuous' in the Status bar | toolbars/sheet_036.png |
| T0117 Show Cover Page in Side-by-Side | widget_menu: Status bar | fresh | not reached: no 'Continuous' in the Status bar | toolbars/sheet_036.png |
| T0130 Minimise | widget: Minimise | fresh | not reached: the control is not on screen (overflow or hidden) | toolbars/sheet_040.png |
| T0131 Maximise | widget: Maximise | fresh | not reached: the control is not on screen (overflow or hidden) | toolbars/sheet_040.png |
| T0132 Close | widget: Close | fresh | not reached: the control is not on screen (overflow or hidden) | toolbars/sheet_040.png |
| T0170 Format Painter | toolbar Style: Format Painter | table_open | not reached: the control is not on screen (overflow or hidden) | toolbars/sheet_050.png |
| T0174 (no names yet) | widget_menu: Formula bar | table_open | not reached: (no names yet) | toolbars/sheet_051.png |
| R0104 Reset Page Label | menu: Document ▸ Current Page ▸ Reset Page Label | two_pages | not reached: Reset Page Label | rightclick/sheet_048.png |
| R0105 Reset All Page Labels | menu: Document ▸ Current Page ▸ Reset All Page Labels | two_pages | not reached: Reset All Page Labels | rightclick/sheet_049.png |
| R0136 New Tool Set… | right-click chest_gear: New Tool Set… | toolchest | not reached: no chest gear | rightclick/sheet_060.png |
| R0137 Import Tool Set… | right-click chest_gear: Import Tool Set… | toolchest | not reached: no chest gear | rightclick/sheet_060.png |
| P0060 Y scale | panel: Y scale | fresh | not reached: the control is disabled | panels/sheet_017.png |
| P0074 All functions… | panel: All functions… | calc_mode | not reached: the control is not on screen (overflow or hidden) | panels/sheet_038.png |
| P0081 Subject | panel: Subject | rect | one undo does not restore | panels/sheet_040.png |
| P0082 Author | panel: Author | rect | one undo does not restore | panels/sheet_040.png |
| P0083 Label | panel: Label | rect | one undo does not restore | panels/sheet_041.png |
| D0023 Count Tool — dialogs.py:CountSubjectDialog, 2 fiel | toolbar Style: Count subject… | count_tool | not reached: the control is not on screen (overflow or hidden) | dialogs/sheet_010.png |
| K0039 Text box | key T | fresh | one undo does not restore | keys/sheet_010.png |
| K0040 Callout | key Q | fresh | one undo does not restore | keys/sheet_011.png |
| K0041 Cloud+ | key Shift+Q | fresh | one undo does not restore | keys/sheet_011.png |
| K0073 Paste cells | key Ctrl+V | table_open | exception: AttributeError: Error calling Python override of QObject::eventFilter(): Error calling Python override of QObject::eventFilter(): Error calling Pytho | keys/sheet_020.png |
| K0074 Paste values | key Ctrl+Shift+V | table_open | exception: AttributeError: Error calling Python override of QObject::eventFilter(): Error calling Python override of QObject::eventFilter(): Error calling Pytho | keys/sheet_021.png |
| X0003 Paste | right-click row_heading: Paste | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_001.png |
| X0004 Values | right-click row_heading: Paste Special ▸ Values | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_001.png |
| X0005 Formulas | right-click row_heading: Paste Special ▸ Formulas | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_002.png |
| X0006 Formats | right-click row_heading: Paste Special ▸ Formats | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_002.png |
| X0007 Transpose | right-click row_heading: Paste Special ▸ Transpose | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_002.png |
| X0019 Paste | right-click col_heading: Paste | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_005.png |
| X0020 Values | right-click col_heading: Paste Special ▸ Values | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_005.png |
| X0021 Formulas | right-click col_heading: Paste Special ▸ Formulas | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_006.png |
| X0022 Formats | right-click col_heading: Paste Special ▸ Formats | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_006.png |
| X0023 Transpose | right-click col_heading: Paste Special ▸ Transpose | table_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_006.png |
| X0035 Paste | right-click row_heading: Paste | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_009.png |
| X0036 Values | right-click row_heading: Paste Special ▸ Values | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_009.png |
| X0037 Formulas | right-click row_heading: Paste Special ▸ Formulas | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_010.png |
| X0038 Formats | right-click row_heading: Paste Special ▸ Formats | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_010.png |
| X0039 Transpose | right-click row_heading: Paste Special ▸ Transpose | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_010.png |
| X0052 Paste | right-click col_heading: Paste | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_013.png |
| X0053 Values | right-click col_heading: Paste Special ▸ Values | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_014.png |
| X0054 Formulas | right-click col_heading: Paste Special ▸ Formulas | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_014.png |
| X0055 Formats | right-click col_heading: Paste Special ▸ Formats | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_014.png |
| X0056 Transpose | right-click col_heading: Paste Special ▸ Transpose | sheet_open | exception: AttributeError: 'NoneType' object has no attribute 'formats' | extra/sheet_014.png |

The dark run has the same rows, plus one: D0062, Help ▸ Find Tools + Commands,
did not open once (flaky).

## Findings, critical → minor

Each finding uses the AGENT_PROMPT format, plus where it shows, the entry point
and the contact sheet (relative to `.../scratchpad/qa/exercise/`). Scratch
repro scripts are in `.../scratchpad/qa/probe_*.py`.

```
[CRITICAL] F-01 Offset, then New PDF, then drawing crashes the app
Where/entry: Edit ▸ Offset (menu or toolbar), then File ▸ New PDF, then any drag tool
Repro: build_state("rect"); act_offset.trigger(); Esc; new_document(); select_tool("rect"); drag on page (scratchpad/qa/repro_offset.py)
Expected: the offset session ends with its document; drawing on the new page works
Actual: segmentation fault in the next job. The offset session outlives its scene and still filters the view's events. The harness now ends the session in reset() to keep running.
Owner area: ui/offset.py (OffsetSession), mainwindow.py new_document / tab switch
Confidence: verified twice
```
```
[MAJOR] F-02 Ctrl+Z dead after Undo then New PDF
Where/entry: Edit ▸ Undo or Ctrl+Z, after File ▸ New PDF
Repro: draw a rect; Ctrl+Z; File ▸ New PDF; draw a rect; Ctrl+Z
Expected: the new document's undo is enabled once it has a step
Actual: Undo stays greyed and Ctrl+Z does nothing until another tab switch. The harness re-runs the undo-refresh hook after New to keep going.
Owner area: mainwindow.py undo-stack hookup on new document
Confidence: verified twice
```
```
[MAJOR] F-03 Paste with an empty clipboard raises AttributeError in tables
Where/entry: table or sheet cell, row or column heading right-click ▸ Paste and Paste Special ▸ Values/Formulas/Formats/Transpose; Ctrl+V and Ctrl+Shift+V (22 runs)
Repro: build_state("table_open") with an empty clipboard; right-click the row 2 heading ▸ Paste
Expected: nothing to paste, so it is greyed out or a status message is shown
Actual: AttributeError: 'NoneType' object has no attribute 'formats'. QClipboard.mimeData() returns None, and tableedit.py paste() (~l.2342) calls mime.formats().
Owner area: ui/tableedit.py paste()
Confidence: verified twice (offscreen clipboard is empty; a desktop clipboard is rarely None, but the guard is missing)
Sheet: light/extra/sheet_001, 005, 009, 013; light/keys/sheet_020-021
```
```
[MAJOR] F-04 Search highlights stay drawn on every later document
Where/entry: Search panel (find "TBC" on drawing.pdf), then any New PDF or other page
Repro: P0041 search, then File ▸ New PDF: yellow hit boxes on the blank page
Expected: highlights belong to their document and are cleared when it closes or a new search starts
Actual: the yellow boxes stay until the window is rebuilt, in both light and dark runs (scratchpad/qa/ghosts.py finds them).
Owner area: ui/searchpanel.py, view overlay
Confidence: verified twice
Sheet: light/dialogs/sheet_009-012, light/panels/sheet_015, light/panels/sheet_041-047
```
```
[MAJOR] F-05 Text box, Callout and Cloud+ need two undos
Where/entry: Tools ▸ Markup ▸ Text box/Callout/Cloud+, toolbar T0061-63, keys T, Q and Shift+Q
Repro: tool, click on the page, type, Esc; Ctrl+Z once
Expected: one placement is one undo step (Revu)
Actual: the box stays and a second Ctrl+Z is needed: one step for the item and one for its text.
Owner area: items/text.py, tools.py commit of text items
Confidence: verified twice
Sheet: light/menu/sheet_082, light/toolbars/sheet_022, light/keys/sheet_010-011
```
```
[MAJOR] F-06 Style fields and Properties fields make one undo step per keystroke
Where/entry: Style toolbar Opacity, Dash spacing, Line width, Fill opacity, End size, font size (T0075-T0092); Properties Subject, Author, Label (P0081-83); Page Setup panel width spin box
Repro: select a rect, click Line width, Ctrl+A, type 2.5, Enter; Ctrl+Z
Expected: one edit is one undo step, applied on Enter or focus out
Actual: each keystroke is applied and stored ("Test 1" gives 6 steps). Intermediate values are drawn: typing a page width squashes the page to a strip mid-typing.
Owner area: ui/markupstyles.py, panels.py property editors, pagepanel.py
Confidence: verified twice
Sheet: light/toolbars/sheet_026-030, light/panels/sheet_016, 040-041
```
```
[MAJOR] F-07 Alt+menu mnemonics dead while an equation is being edited
Where/entry: Alt+C (Calculation) ▸ Function…/Constants…/Operator… in the equation_editing state
Repro: start an equation, type "x := 3"; Alt+C
Expected: the Calculation menu opens, as it does by mouse
Actual: no menu opens; the editor eats Alt+letter.
Owner area: ui/calcedit.py key handling
Confidence: verified twice
Sheet: light/menu/sheet_112-114
```
```
[MAJOR] F-08 These inserts and edits leave no undo step
Where/entry: Calculation ▸ Plot / Program ▸ If, For, While, Line (menu, toolbar, right-click, key); Calculation ▸ Matrix… OK; Tools ▸ Link (even when its Action dialog is cancelled); Add Bookmark (menu and right-click); Conditional Formatting dialogs (Cancel still writes document calc_rules); preset Save/New/Rename
Repro: calc_mode; Calculation ▸ Plot; Ctrl+Z
Expected: every document change is undoable; Cancel changes nothing
Actual: the document changed and undo_steps is 0 ("CHANGED, NO UNDO STEP" on the sheets).
Owner area: ui/calcmenu.py, calcdialogs.py, condformat.py, mainwindow.py add_bookmark_here/bookmark_page, tools.py link
Confidence: verified twice
Sheet: light/menu/sheet_109, 117; light/toolbars/sheet_008; light/rightclick/sheet_094; dark/rightclick (R0357); light/dialogs/sheet_003, 027
```
```
[MAJOR] F-09 View turn leaks across documents
Where/entry: View ▸ Rotate Clockwise/Counterclockwise, then File ▸ New PDF or Close
Repro: rotate_view(); New PDF: view._view_turn stays 90 while the new scene's reading_turn is 0 (scratchpad/qa/probe_rot.py)
Expected: the turn belongs to the document (or is reapplied to the new scene)
Actual: the new page is shown upright. The next Rotate Clockwise goes to 180° (upside down), and Reset Rotation turns the page instead of doing nothing.
Owner area: ui/view.py rotate_view/turn_the_pages, mainwindow tab switch
Confidence: verified twice
Sheet: light/menu/sheet_053-054
```
```
[MAJOR] F-10 Ellipse ▸ Convert to Polygon gives a rectangle
Where/entry: right-click an ellipse ▸ Convert to Polygon
Repro: build_state("ellipse"); right-click ▸ Convert to Polygon
Expected: a polygon close to the ellipse (Revu uses many vertices)
Actual: a 4-corner box, the ellipse's bounding rectangle. Exact Size… on an ellipse is also titled "Rectangle Size".
Owner area: items/shapes.py convert
Confidence: verified twice
Sheet: light/extra/sheet_022
```
```
[MAJOR] F-11 Group menu edits reach inside the group to one member
Where/entry: right-click a group ▸ Control Point ▸ Add/Subtract/Round/Insert Break, Arc Segment, Round All Corners, Convert to Polygon, Exact Size…, Show Size
Repro: build_state("group"); right-click ▸ Round All Corners
Expected: either greyed for groups or applied to the whole group
Actual: only the first rectangle changes, and the selection frame jumps to it. Exact Size and Show Size report the first member's 35.3 × 24.7 mm.
Owner area: mainwindow.py item menu, items/shapes.py
Confidence: verified twice
Sheet: light/extra/sheet_055-057; light/menus/sheet_016
```
```
[MAJOR] F-12 Add Arrow Leader points into its own box; Remove Leader deletes the cloud
Where/entry: right-click a text box, callout or Cloud+ ▸ Add Arrow Leader / Add Cloud Leader / Remove Leader
Repro: build_state("textbox"); right-click ▸ Add Arrow Leader
Expected: the leader starts at the box edge and points outward to a free spot; Remove Leader keeps the body
Actual: the arrow is drawn inside the box through the text. Add Cloud Leader shows nothing. Remove Leader on Cloud+ deletes the cloud too.
Owner area: items/text.py leaders
Confidence: verified twice
Sheet: light/rightclick/sheet_132; light/extra/sheet_038-040; dark/rightclick (R0320-R0323)
```
```
[MAJOR] F-13 Ctrl+- deletes a whole column with no prompt; Ctrl++ has no dialog
Where/entry: table open, keys Ctrl+- ("Delete cells…") and Ctrl++ ("Insert cells…")
Repro: table_open at B2; Ctrl+-
Expected: the Excel dialog: shift cells left or up, entire row, entire column (the label has "…")
Actual: column B (Beam, Joist, Post) is deleted at once; Ctrl++ shifts cells right at once.
Owner area: ui/tableedit.py SHEET_COMMANDS
Confidence: verified twice
Sheet: light/keys/sheet_033-034
```
```
[MAJOR] F-14 New Window and Split View are slow, and slower as the session ages
Where/entry: Window ▸ New Window / Split View, tab ▸ New Window / Open in Split View, Ctrl+Shift+N
Repro: run any long session and time act_new_window
Expected: under 500 ms
Actual: light run 0.8–4.3 s, dark run (later in a longer session) 8.6–15.9 s for New Window and 8.1–31.3 s for Split View. The growth points to leaked windows or scenes. There are also deleted-C++-object RuntimeErrors from timers after split or new windows close. Other slow commands, first open: Dark Mode toggle 1.0–2.6 s, Keyboard Shortcuts 0.5–1.0 s, Open… 1.6–2.2 s, Colour Processing 0.66–0.82 s, Apply Redactions 0.73–0.95 s.
Owner area: mainwindow.py new_window/split, scene ownership (a leak agent is already looking)
Confidence: verified twice (on a loaded machine)
```
```
[MAJOR] F-15 Insert Field with blank document properties inserts an invisible field
Where/entry: right-click a text box ▸ Insert Field ▸ Project/Author/Company/Subject/Keywords/Description/Revision/Document id/File name
Repro: build_state("textbox"); right-click ▸ Insert Field ▸ Author
Expected: a placeholder such as «Author», or the item greyed
Actual: the field is inserted (document changed, one undo step) but draws nothing, so it cannot be seen or selected.
Owner area: items/fields.py
Confidence: verified twice
Sheet: light/rightclick/sheet_126-128; dark/rightclick (R0298-R0306)
```
```
[MAJOR] F-16 Sort and Remove Duplicates take the first data row as a header
Where/entry: Data ▸ Sort Z to A (one click), Custom Sort…, Remove Duplicates… on headerless data
Repro: table_open with rows 3 Beam / 5 Joist / 4 Post; Data ▸ Sort Z to A
Expected: Excel's guess: numbers in row 1 mean no header, so all rows are sorted
Actual: row 1 stays fixed ("3 Beam"), giving Beam, Post, Joist. The dialogs default "My data has headers" on and name the columns "3" and "Beam".
Owner area: ui/datatools.py header guess
Confidence: verified twice
Sheet: light/rightclick/sheet_080; light/dialogs/sheet_006
```
```
[MAJOR] F-17 One Insert Page Break turns 2 pages into 5
Where/entry: sheet page right-click ▸ Insert ▸ Insert Page Break at B2
Repro: sheet_open, B2 active; right-click ▸ Insert Page Break
Expected: one extra page boundary
Actual: the status bar goes from "2 of 2" to "2 of 5", with three or more new thumbnails.
Owner area: ui/sheetpages.py
Confidence: verified twice
Sheet: light/rightclick/sheet_091; dark/rightclick (R0242)
```
```
[MAJOR] F-18 Ctrl+Alt symbol keys type plain letters in a text box
Where/entry: editing a text box: Ctrl+Alt+8 / ÷ / 6 / R / 2 / 3 / = / , / . / N / P / D / T / S / O / M / F / G / A
Repro: textbox_editing; Ctrl+Alt+P
Expected: π, as in the equation editor (shortcuts.py symbol table)
Actual: "p" is typed (likewise 8, /, 6, r…). Ctrl+Alt+B (β) makes the text bold instead, and one undo does not restore it.
Owner area: items/text.py keyPressEvent, shortcuts.py symbol bindings
Confidence: harness doubt (QTest gives the event its character text; check on a real keyboard)
Sheet: light/keys/sheet_045-050
```
```
[MAJOR] F-19 The Set Scale prompt pops up for the wrong tools
Where/entry: first drag on an unscaled page with Rectangle (R), Ellipse (E), Length (M), Polylength, Area, Volume
Repro: fresh; key R; drag
Expected: only measurements ask for a scale; a rectangle never does
Actual: Rectangle and Ellipse ask, while Dimension, Perimeter, Angle, Diameter, Polygon and Cloud do not.
Owner area: tools.py scale prompt
Confidence: verified twice
Sheet: light/keys/sheet_009-015
```
```
[MINOR] F-20 Controls cut off at 1280 px
Where/entry: Style toolbar Corner radius, Hatch opacity, Count subject…, Format Painter (table style bar); Maths panel "All functions…"
Repro: window at 1280×860; look for the control, then use the » overflow
Expected: reachable through » or by wrapping
Actual: hidden even with » open (Count subject is never shown). The table style bar clips "Rows & Columns".
Owner area: ui/markupstyles.py, tablebar.py, mathspanel.py
Confidence: verified twice
Sheet: light/toolbars/sheet_028-029, 046-050; light/dialogs/sheet_010; light/panels/sheet_038
```
```
[MINOR] F-21 Undo of a page operation leaves the view lost
Where/entry: undo after Insert Blank Page, Insert Spreadsheet Page, page Crop, Paper Size A0…ARCH E, Rotate Pages, Insert Chart, row or column operations
Repro: two_pages; Paper Size ▸ A0; Ctrl+Z
Expected: the view returns to where it was
Actual: the page is back to A4, but the zoom stays at 17–48 % or the view jumps to page 2, an empty desk, or the bottom-right corner.
Owner area: ui/view.py fit after undo, pagedialogs.py
Confidence: verified twice
Sheet: light/dialogs/sheet_019; light/menu/sheet_070, 098-099; light/rightclick/sheet_025-033; light/extra/sheet_001-012
```
```
[MINOR] F-22 Page Setup panel cuts off its own labels
Where/entry: right panel Page Setup, after any field gets focus
Repro: click the Width field
Expected: labels stay whole
Actual: the panel scrolls sideways and every label loses its start ("per", "entation", "ale", "ngth unit", "cimal places").
Owner area: ui/pagepanel.py
Confidence: verified twice
Sheet: light/panels/sheet_016-019
```
```
[MINOR] F-23 Status-bar hint text paints over the grid and snap buttons
Where/entry: status bar, after any long hint ("…on their grid (* in Calc mode)")
Expected: the hint is elided before the buttons
Actual: overlapping, garbled text.
Owner area: mainwindow.py status bar layout
Confidence: verified twice
Sheet: light/menu/sheet_119-121; light/panels/sheet_003
```
```
[MINOR] F-24 Search results drop the first letter
Where/entry: Search panel results list
Actual: hits on "Sheet 1: beam TBC" are listed as "heet 1:…", and the Found column is too narrow. Replace and Replace all on drawing (PDF) text do nothing, with no message.
Owner area: ui/searchpanel.py
Confidence: verified twice
Sheet: light/panels/sheet_012-015
```
```
[MINOR] F-25 Markups List Filter ▸ Comment shows the Value column
Where/entry: Markups List column filter on Comment
Actual: it lists sizes ("35.3 mm × 28.2 mm") instead of comments.
Owner area: ui/panels.py markups list filter
Confidence: verified twice
Sheet: light/menus/sheet_007
```
```
[MINOR] F-26 Thumbnails lag or keep stale marks
Where/entry: Thumbnails panel after Undo or Redo, while a table is open, after Paste Pages
Actual: the thumbnail shows the old page after Ctrl+Z, and stays blank while a table is edited. A blue drop line stays above thumbnail 2 after Paste Pages and after its undo. After a thumbnail drag all three thumbnails look selected.
Owner area: ui/panels.py thumbnails refresh
Confidence: verified twice
Sheet: light/menu/sheet_017; light/dialogs/sheet_001; light/rightclick/sheet_023; light/mouse/sheet_007
```
```
[MINOR] F-27 Colour Processing preview is empty at first
Where/entry: Document ▸ Colour Processing… on a PDF page, image ▸ Colour Processing…
Actual: the Before and After boxes are empty when the dialog shows (D0006, X0085). Later they fill after about 600 ms (R0108). A "Reading the page's colours…" box shows first.
Owner area: ui/colorprocess.py
Confidence: verified twice
Sheet: light/dialogs/sheet_003; light/extra/sheet_022
```
```
[MINOR] F-28 Page Setup OK with no change refits the view and adds an undo step
Where/entry: Document ▸ Page Setup… OK
Actual: the zoom goes from 100 % to 67 %, the page jumps, and a no-op undo step is pushed.
Owner area: ui/dialogs.py PageSetupDialog, mainwindow page_setup
Confidence: verified twice
Sheet: light/dialogs/sheet_012
```
```
[MINOR] F-29 Spell check misses "The" and leaves a red box behind
Where/entry: Edit ▸ Check Spelling ▸ … (F7) on "Teh"
Actual: it suggests tech, th, te, eh, tenth. After closing, a red box stays around the text.
Owner area: spelling suggestions, markuplayer overlay
Confidence: verified twice
Sheet: light/dialogs/sheet_014
```
```
[MINOR] F-30 Table format combo shows the wrong category
Where/entry: Ctrl+Shift+~ (General), Ctrl+Shift+@ (Time)
Repro: table_open; Ctrl+Shift+~; the cell's number_format is "General" (probe_fmt.py)
Actual: the table style bar's format combo says "Number" for General and "Date" for Time.
Owner area: ui/tablebar.py category of code
Confidence: verified twice
Sheet: light/keys/sheet_028, 031
```
```
[MINOR] F-31 Duplicate and Paste land almost on top of the original
Where/entry: Ctrl+D Duplicate, item Paste, Multiply… (default Across 1 mm, Times 1)
Expected: a visible offset, or paste at the cursor (Revu)
Actual: copies of equations, calc blocks and tables overprint the original and become unreadable.
Owner area: mainwindow.py duplicate/paste placement
Confidence: verified twice
Sheet: light/rightclick/sheet_110, 117; light/menu/sheet_025
```
```
[MINOR] F-32 Locked markups show no sign of being selected or locked
Where/entry: Edit ▸ Lock / right-click ▸ Lock (Ctrl+Shift+L, also Ctrl+L)
Actual: the frame and handles vanish while Properties still shows the item, and only its Lock tick says so. Lock has two shortcuts.
Owner area: items/base.py selection painting
Confidence: verified twice
Sheet: light/menu/sheet_029; light/rightclick/sheet_116
```
```
[MINOR] F-33 Measurement Edit Text… opens an empty editor
Where/entry: right-click a Length/Area ▸ Edit Text…
Actual: the "0.05 m" label vanishes and an empty inline box appears; Inline Text shows no change. The menu also shows a raw item "[field] L.beam".
Owner area: items/measure.py
Confidence: verified twice
Sheet: light/rightclick/sheet_133; light/extra/sheet_041-052
```
```
[MINOR] F-34 Undo restores the item but not its selection
Where/entry: Ctrl+Z after Cut, Duplicate, Hide, Delete
Actual: the markup comes back unselected (Revu re-selects it).
Owner area: undo commands in mainwindow.py
Confidence: verified twice
Sheet: light/menu/sheet_020-026
```
```
[MINOR] F-35 Commands that do nothing or give no feedback
- File ▸ Save All with only an untitled document: no Save As and no message (light/menu/sheet_010).
- Apply to Pages… on a one-page document: nothing happens (light/dialogs/sheet_016; light/rightclick/sheet_121).
- Goal Seek OK with blank fields: silent.
- Add to Tool Chest ▸ My Tools, Set as Default, Forget Defaults, Format Painter (no cursor change), Cut Pages and Copy Pages, Bookmark on a text box, Help ▸ Record Slow-Downs: no feedback.
- Go to Page on the current page: no prompt.
- Insert Equation Here: only the red cross cursor moves.
- Document ▸ Viewports… with none: a dead-end message box.
- Polygon cut-out and Ellipse cut-out with no Area: nothing is drawn and no hint is given (light/toolbars/sheet_014).
Confidence: verified twice
```
```
[MINOR] F-36 Smaller faults
- Fractions submenu ticks both Decimal and Default (light/menus/sheet_014).
- AutoSum leaves a floating QLabel.
- Polygon ▸ Subtract Control Point goes down to a 2-point "polygon" (light/extra/sheet_032).
- Hidden rows and columns leave no marker between the headings (light/rightclick/sheet_068).
- Top 10… applies at once despite its "…".
- The filter arrow covers the header cell's text (light/extra/sheet_059-061).
- The Choose Values filter dialog has no labels and no Select All.
- Data Validation keeps every field enabled for "Any value" (light/rightclick/sheet_082).
- An empty "Text that Contains" rule is accepted and paints every cell (dark/dialogs/sheet_008).
- CF Rules Rename and Delete are enabled with no presets.
- Bookmarks Rename and Delete are enabled with an empty list.
- Variables ▸ Go to scrolls past the page edge (light/rightclick/sheet_095).
- Calibrate opens "60.6942 mm = [empty] mm" (light/menu/sheet_095).
- The status-bar Scale 1:1 button opens Set Scale preselected on 1:100 (light/toolbars/sheet_033).
- The Style toolbar with nothing selected shows the last tool's values.
- Whiteout's style bar looks like Crop's (dashed, 11 % fill).
- The Print dialog's output file is "/root/"; Save, Save As and Export start in the working directory.
- Unticking the only tool set leaves an empty Tool Chest with no hint.
- The Customise Toolbars text names an "Insert" menu and a "Markup" menu that do not exist.
- About shows no version.
- The Fill-handle drag moved B2 to B4 instead of filling (light/mouse/sheet_011; harness doubt: the grab point may be the cell border).
- Full Screen and Presentation on a small screen: the docks keep their width and the page shrinks to a strip (harness doubt: offscreen screen size).
```
```
[MINOR] F-37 Dark mode contrast
- The CF "Font #9c0006" swatch is dark red text on a dark button (dark/dialogs/sheet_001).
- Disabled checkboxes and the "Line:" and "Fill:" labels are near-invisible.
- Hatch pattern previews are dark grey on dark grey (dark/dialogs/sheet_024).
- The Preferences equation colour swatch is black on the dark dialog.
Otherwise every menu, popup and dialog in the 574 dark sheets is readable, and pages stay white.
Confidence: verified (visual)
```

### Naming, placement and consistency (one list, for a decision pass)

- **Same command, different names.**
  - Edit ▸ Arrange/Align against right-click Order/Alignment.
  - Set Scale… against Page Scale….
  - Color Processing against Colour Processing.
  - Rotate Counterclockwise against Anticlockwise.
  - Align Center against Align Centre.
  - Calc empty-page Text Region and Calculation Block against Calculation ▸ Calc Text and Block.
  - Go To against Go to.
  - Import ▸ Excel Workbook… opening "Insert Excel workbook", and Import ▸ Image Page… opening "Insert image as a page".
  - Manage Tool Sets Add… against New Tool Set….
  - Rename Table against Rename table (two dialogs; Rename Sheet… also opens "Rename table").
  - Sheet Layout… opening "Page layout — Sheet1".
  - Headers & Footers… opening the whole Document Properties dialog.
  - Markups Summary… with a save dialog titled "Summary".
  - Exact Size of an ellipse titled "Rectangle Size".
- **Case.**
  - Sentence-case dialog titles: Row height, Column width, Insert function, Apply redactions, Save document as, Open document, New tool set.
  - Lower-case menu items: Text box, Highlight area, Center radius, Polygon cut-out, Page sync, solid, dashdot, left/center/right, circle/square, portrait, Line style, Font size, Lock / unlock.
- **Menu shape.**
  - The View and Document ▸ Current Page menus, and the thumbnail menu (about 35 items), spill into a second column at 860 px.
  - Edit ▸ Check Spelling is a submenu with one item.
  - The Control Point submenu has a separator between its two entries.
  - Duplicate (Ctrl+D) sits with the shape extras, not with Cut, Copy and Paste.
  - Delete shows "Del" in item menus but no key in Edit.
  - The Snap order differs between the status bar and the View menu.
  - Only some Import and Snap items have icons.
- **Ellipses.** These have "…" but open nothing: Paste Here…, Edit Text…, Colour…/Fill… (a popup), Insert/Delete cells…, Top 10…. Add Bookmark has no "…" but opens a dialog.
- **Labels and glyphs.**
  - The Style font family combo and font size box have no accessible name.
  - The table align buttons are bare glyphs (◀ ≡ ▶).
  - Maths panel glyphs show no tooltip.
  - Stay Active's icon looks like Refresh.
  - The equation menu's "Global (Read by Later Calc Sections)" is jargon.
  - The Markups List footer says "No measurements yet." on an empty list.
  - Function list shows "atan" twice.
  - Constants show exponents as "10^8".
  - Page Setup precision is "10.00 mm" against "210.0 mm" in Insert Blank Page.

### What worked

- Every menu-bar item opens by mouse and by Alt+keys, apart from F-07.
- All 69 menu shortcuts work.
- Every right-click menu opens where expected, with its items enabled or greyed sensibly.
- All 77 dialogs open, show their labels, cancel cleanly and OK safely, with no hangs.
- Table and sheet editing works: rows, columns, merge, conditional formatting, data tools, names and comments.
- Charts insert, and alignment, order and page operations work.
- Equation menus (decimals, threshold, fractions, rounding, font, colour) all apply and undo in one step.
- There were no Qt critical messages, and no crashes beyond F-01.
- The dark theme is complete.

## Harness notes (what is the harness, not the app)

- **Workarounds added to keep running.** reset() ends any Offset session
  (F-01) and re-runs the undo-refresh hook after New (F-02). The window is
  re-activated after each dialog so that shortcuts reach it.
- **State that leaks between runs.** Settings persist across commands and
  window rebuilds: Name Tags, tool sets, the status-bar page layout (which
  breaks T0114-T0117), and the clipboard (Paste in the "rect" state pastes an
  earlier table).
- **Weak fixtures.**
  - The "bookmarked" fixture has no bookmark.
  - "matrix_eq" is "M := 2", so Invert, Determinant and Solve show nothing.
  - Decimal places and Optimization on "a := 2" have nothing visible to change.
- **Unreliable timing and crops.** The hatch Manage dialog timing (D0035) is
  unreliable. Change crops often land on the thumbnail rather than the cell,
  because the thumbnail repaints one event late.
- **Offscreen platform.**
  - Caption buttons are not drawn.
  - Floating panels are placed off screen.
  - The clipboard starts empty (F-03).
  - QTest key text may differ from a real keyboard (F-18).
- **Machine load.** Load average was 6–16 on 4 cores. Single timings near
  100 ms are noise; F-14's growth is not.
