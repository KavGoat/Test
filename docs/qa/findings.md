# QA findings — the one deduplicated list

Kept by the lead agent (docs/AGENT_PROMPT.md §5). One line per finding, newest
round at the top. Status: open · fixing (who) · merged · pushed · decision
(waiting on the user) · not a bug.

## Round 5 — spreadsheet speed (performance agent, 2026-10-16)

Merged in cbacfa6. Medians in ms, before → after:

| Action | Before → after |
|---|---|
| Keystroke in a cell | 21 → 3 (the editor's style sheet was causing endless repaints) |
| Undo on the 300-formula sheet | 117 → 16 |
| Undo on a 3000-row workbook | 6.9 s → 1.5 s |
| Table markup keystroke | 108 → 4 |
| Table markup click | 14 → 5 |
| Zoom on the 3000-row sheet | 112 → 33 |

Still open, each over the 50 ms aim:
- 5.1 Insert or delete a row on a heavy sheet: 115 ms (300 formulas), 3.3 s (3000 rows). Every moved formula is parsed and calculated again; this needs an engine refactor.
- 5.2 A 3000-row running-total column recalculates in about 1.1–1.5 s, spent in Python cell reads.
- 5.3 Dragging a column edge redraws the cached rows on every move: about 25–60 ms per move.
- 5.4 Panning or zooming a table markup takes about 15 ms per frame, against 2–6 ms for markups, because tables are drawn live rather than from tiles.
- 5.5 Opening the 3000-row xlsx takes 4.3 s, against the 1.5 s budget.

## Round 4 — right-click menus, placement and grouping (lead as bug tester, 2026-10-15)

Every right-click menu was dumped from the real window (empty page in both modes,
rectangle, line, several markups, thumbnail, document tab, table cell open and
closed, sheet cell, row and column headings, sheet tab, equation in both modes).

- 4.1 **Insert Page Break.** The command itself works: a break at A10 gives pages
  of rows 1–9 and 10+, and one undo removes it. Two real faults:
  - A right-click outside the selection didn't move the active cell (Excel does),
    so the break landed at the old cell. Fixed in eab8413.
  - The command is buried under Page Layout ▸ while Insert ▸ holds Rows and
    Columns. Move it to Insert ▸ Page Break and Delete ▸ Page Break.
  Status: fixing.
- 4.2 **Charts sit outside Insert.** "Insert Chart ▸" is a top-level item. Move it
  into Insert ▸ Chart ▸.
- 4.3 **Lower-case submenu items.** Insert ▸ "Rows above", "Rows below", "Columns to
  the left", "Columns to the right". Use Title Case: Rows Above, Rows Below,
  Columns Left, Columns Right.
- 4.4 **Headings show the whole cell menu.** The row and column heading menus are
  copies of the cell menu (45+ items). Excel's heading menu is short: Cut, Copy,
  Paste, Paste Special, Insert, Delete, Clear Contents, Format Cells,
  Row Height…/Column Width…, Hide, Unhide, and Insert Page Break before this
  row/column.
- 4.5 **Closed table offers outline commands.** A closed table, as a markup,
  offers "This outline ▸ Round corner / Arc side / Insert break", Convert to
  Polygon and Exact Size. These make no sense for a table, and there is no
  "Edit Table". A line also offers Round corner and Arc side.
- 4.6 **Doubled separators.** The equation menu has two in a row, and so does the
  thumbnail menu after Move Down.
- 4.7 **Thumbnail menu out of order.** Delete Page sits last, after "Make This
  Page's Markups Editable", with no separator (the user: "weirdly categorised").
  Use Revu's order, with Delete Pages… in the insert/extract group (audit A1).
- 4.8 **Thin document-tab menu.** It holds only "Open tab / Open window / Split
  view", in lower case. Revu's tab menu has Close, Close All, Close Others, Save,
  Save As…, Split Vertical/Horizontal and New Window.
- 4.9 **Thin sheet-tab menu.** It holds only "Go to / Rename… / New sheet". Excel
  also has Insert, Delete, Move or Copy… (duplicate), Tab Colour, Hide/Unhide.
  Use Title Case.
- 4.10 **Calc mode's empty-page menu is Markup mode's.** Nothing for equations:
  no Insert ▸ Equation here, Text region, Calculation block, Section break or
  Plot.
- 4.11 **Inconsistent "Insert Here ▸" names.** Its entries mix case ("Text box",
  Callout, Note). Use "Text Box".
- 4.12 **Markup menu order differs from Revu (audit C1/C2).** Cut, Copy, Paste
  and Delete should come first, and "This outline" → "Control Point". Arrange →
  Order, Align → Alignment, Flatten Selection → Flatten, Multiply Ctrl+M (in
  Markup mode).

## Round 3 — Revu parity audit, 2026-10-15

The full report is docs/qa/revu_audit.md (groups A–N). It finds mostly misplaced,
misnamed, or prompt-instead-of-dialog commands, and no shared "Pages" range
control anywhere. Status: open, queued after round 2 merges.

User's decisions (pop-up):
- Ctrl+M is Multiply in Markup mode and Matrix in Calc mode. The other Revu keys
  are adopted (Ctrl+D Document Properties, Ctrl+9/0/8 zoom, Alt+panel keys,
  Shift+F4 Hide Panels).
- Page Setup follows Revu's layout and really resizes the content (Auto Scale,
  Scale, Offset, Rotation, Center, Fit to Media), with a preview and a Pages range.
- Build Revu's Print dialog, with the preview folded in. Print Pages… opens it
  with Selected chosen. The per-page and per-markup print ticks stay.
- UK spelling app-wide (Colour, Centre).

Lead's calls, under "behave like Revu, keep everything":
- Add Distribute and Flip to Alignment.
- Keep Spacing, Corner Radius and Hatch Opacity at the end of Appearance.
- Move the CalcForge-only items into a CalcForge section rather than delete them.

## Round 2 — 2026-10-15

| # | Sev | Finding | Area | Status |
|---|---|---|---|---|
| 2.1 | High | An equation variable read into a cell shows base SI (M=35 kN·m comes out as 35000 J) | sheet/units | fixing (cell-units doer) |
| 2.2 | High | General-format numbers show #### instead of rounding to fit (Excel) | sheet/numfmt, items/table | fixing (Excel doer) |
| 2.3 | High | The window can't be narrower than ~1180 px; the status bar never gives way | ui/mainwindow status bar | fixing (window doer) |
| 2.4 | High | `var(F)` gives Excel's VAR (#DIV/0!) when a cell is also named F | sheet/formula | fixing (Excel doer) — decided: variable if one exists |
| 2.5 | Med | `max(1,2)=` (and min, sum, atan2, lg) becomes a broken definition | calc/engine/builtins | fixing (equations doer) |
| 2.6 | Med | `)` doesn't close the bracket: `(1+2)*3=` gives 7 | calc/editor | fixing (equations doer) — decided: close it |
| 2.7 | Med | Cell units drawn black with a caret (m^2), unlike equations | items/table | fixing (cell-units doer) — decided: blue + superscripts |
| 2.8 | Med | Cell errors (#UNITS!, #DIV/0!, #NAME?…) never explained | sheet, ui/tableedit | fixing (Excel doer) |
| 2.9 | Med | A column dragged to zero width is a broken "ghost", not hidden | ui/tableedit | fixing (Excel doer) |
| 2.10 | Med | Calculation toolbar mostly in the overflow chevron at 1280 px | ui/mainwindow toolbars | fixing (window doer) |
| 2.11 | Med | An incompatible output unit is accepted silently | ui/cellunits, tablebar | fixing (cell-units doer) |
| 2.12 | Low | DATE()/TODAY() show a serial number, not a date | sheet | fixing (Excel doer) |
| 2.13 | Low | Cloud path has a hook at the SE corner where it closes | items (cloud) | fixing (window doer) |
| 2.14 | Med | Allow Markup Recovery lives in Preferences, not the Flatten dialog (Revu) | ui/dialogs FlattenDialog | fixing (dialogs doer) |
| 2.15 | Med | Set Scale dialog doesn't look or work like Revu's (pages, preset/custom, calibrate, precision, presets) | ui/dialogs ScaleDialog | fixing (dialogs doer) |
| 2.16 | — | Every dialog, panel and menu vs the Revu manual | all | auditing (Revu-parity auditor) |
| 2.17 | — | No shortcut may fire while typing (text box, callout, label, Search, typed size, equation, cell, formula bar) | ui | text box, callout, cell: 0 of 152 keys leak; rest running |

## Round 1 — 2026-10-15 (pushed, gated at f67fd82)

| # | Sev | Finding | Status |
|---|---|---|---|
| 1.1 | High | Nudge/drag/Ctrl+A with 400 markups picked took seconds | pushed |
| 1.2 | Med | Home/End went to the top/bottom of the current page (Home even went forward); Revu: first/last page | pushed |
| 1.3 | Med | Ctrl+Left/Right didn't turn pages (Revu) | pushed |
| 1.4 | Low | Redo only Ctrl+Shift+Z on Linux; Revu's Ctrl+Y added | pushed |
| 1.5 | Low | Revu keys missing: V, Shift+V, Ctrl+Shift+M/U, Ctrl+3, Ctrl+Shift+L | pushed |
| 1.6 | Med | Page right-click menu lacked Revu's Add Note/Bookmark/Flag, Next/Prev Page, Print, Search | pushed |
| 1.7 | — | Dragging a 400-markup selection by one markup's edge moved nothing (seen before and after 1.1) | open — re-check in the bug hunter's round |

## Not bugs (harness or by design)
- The plain wheel zooms and Ctrl+wheel scrolls — Revu's default, by design.
- SMath-style `name(…)=` with `;` separators works; `,` is the case in 2.5.
