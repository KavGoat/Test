# Full QA plan — every feature, so the user never has to bug-test

Asked 2026-10-15: test every feature of the app for function, speed and
intuitiveness, and for correct placement (where each button and command
belongs). The lead runs this plan and keeps docs/qa/findings.md as the one
list. Fixes go to doers in worktrees; a verifier and one gate come before
every push.

## 1. Inventory (the denominator)
`docs/qa/feature_inventory.md` lists every user-reachable feature once:
- every menu-bar command (menu path, name, shortcut)
- every toolbar button
- every right-click menu entry (canvas: empty page in both modes, each
  markup type, a multi-selection, an equation, a calc block, table and
  spreadsheet cells, row and column headings, sheet tabs, document tabs,
  thumbnails, bookmarks, the Markups List, the Tool Chest, the Variables
  panel, rulers)
- every panel and its header buttons
- every dialog and its fields
- every keyboard and mouse gesture
For each it records the test that covers it, or "UNTESTED".

## 2. Four passes over the inventory
Each tester owns one area: markup tools and editing; pages, files and
panels; Calc mode; spreadsheets and tables. Each runs all four passes and
logs one line per finding in the findings format.

| Pass | Asks | How |
|---|---|---|
| Function | Does it do what its name says, undo in one step, survive save and reopen, and work in both modes and on rotated or scaled pages? | Drive the real window headless, with real mouse and key events |
| Speed | Does it meet the budgets in AGENT_PROMPT.md? Any visible stall over 100 ms is a finding | time.perf_counter around the real event, median of 5 |
| Placement | Is it where a Revu, Excel or SMath user looks first? Is it grouped with its relatives (e.g. Insert ▸ Page Break beside Insert ▸ Rows)? Do the menu bar, right-click menus, toolbars and panels agree on its name and order? | Compare against Revu 21, Excel 365 and SMath. Any related items split across groups is a finding |
| Intuitiveness | Could a first-time user find it and finish the task? | Novice tester: plain tasks with no docs, counting clicks and wrong turns |

## 3. Novice task list (the tester gets only these words)
1. Open a PDF, put a red cloud with a callout saying "check", save, reopen.
2. Measure a room's area on a scaled drawing; set the scale first if needed.
3. Add a blank page after page 2, then delete it.
4. Make a table of three beam lengths and sum them.
5. Write `L:=5 m`, then `w:=2 kN/m`, then `M:=w*L^2/8=` and show M in kN·m.
6. Use a measured length as a variable in an equation.
7. Insert a page break in a spreadsheet page after row 20.
8. Split the view, drag a document between panes, then unsplit.
9. Find every "TBC" in the document and replace it.
10. Print pages 2–3 only, without markups.
11. Save a callout style and reuse it with a number key.
12. Hide and show the Markups List; filter it to clouds only.

## 4. Done means
Every inventory line has a passing test or a dated "not a bug" note.
Every speed budget is met. No placement finding is open. Every novice task
is completed in at most the clicks a Revu, Excel or SMath user would need.
