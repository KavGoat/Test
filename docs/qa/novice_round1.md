# Novice usability round 1 (QA_PLAN.md §3)

2026-10-16, at commit 4f6e28b. I played a first-time user who knows Revu, Excel
and SMath a little and had never seen CalcForge. I drove the real `MainWindow`
headless (offscreen) with real mouse and key events. Menus were reached by
walking the menu bar, right-click menus and dialogs were captured with a QTimer,
and a test drawing set of 4 A3 pages was made with PyMuPDF (a room outline,
"TBC" notes and the label "1:100" on every page).

Repeat the run: `QT_QPA_PLATFORM=offscreen python tools/qa/novice/tasks.py [n ...]`
(each task runs in its own process). Stall timings: `python tools/qa/novice/timing.py`.
The screenshots are in the session scratchpad (`qa/novice/`) and do not survive
the session; the scripts rebuild them.

## Results

The clicks column counts mouse clicks plus keys pressed, not counting text
typed. "Par" is about how many a Revu, Excel or SMath user would need.

| # | Task | Success | Clicks (+keys) | Path found | Wrong turns | Confusion |
|---|---|---|---|---|---|---|
| 1 | Red cloud + "check" callout, save, reopen | yes | 12 (+1) — par | Cloud+ toolbar button → drag → click for the words → type → Ctrl+S → File ▸ Close → File ▸ Open | none | Cloud+ is red by default (good), but the Properties panel calls it "Callout Properties" with an empty Subject. The Cloud tool's tooltip also says "custom Cloud+". Saving and reopening worked. Closing the last tab leaves an "Untitled" document. |
| 2 | Area of a room on a scaled drawing | yes (149.34 m², correct) | 12 — 2 over par | status bar "Scale 1:1" → Set Scale dialog → preset 1:100 → Apply → Area tool → 4 corners | looked for Revu's Measurements panel or Tools ▸ Measure ▸ scale; found only Calibrate there | The status bar says "Scale 1:1" before any scale is set. The area's value label is covered by its own handle dots right after drawing (screenshot). The value is shown in Properties only far down, under "Value:". Area Unit reads "m^2" while the value reads "m²". |
| 3 | Blank page after p2, then delete it | yes | 9 — par | right-click thumbnail 2 ▸ Insert Blank Page ▸ After… ▸ OK; right-click thumbnail 3 ▸ Delete Pages… ▸ OK | none | The Insert Blank Page dialog shows 420 × 297 mm with Orientation "Portrait" ticked; the page comes out landscape. |
| 4 | Table of 3 beam lengths and their sum | yes (13.7) | 2 (+49 typed) — par | Table toolbar button → drag → type with Tab/Enter → `=SUM(B2:B4)` | none | There are two "Table" buttons (Calculation and Tools toolbars) with slightly different tooltips. There is no Σ AutoSum button, though Alt+= works. |
| 5 | `L:=5 m`, `w:=2 kN/m`, `M:=w*L^2/8=` in kN·m | yes, on the 3rd attempt | 3 (+83 typed over 3 attempts) | File ▸ New PDF → F12 → click → type, with SMath's `'` before units and → to leave the power | Attempt 1, typed as written: `L:=5 m` silently became just `m`, and so on. Attempt 2, `5*m`: "m - not defined." | The result shows "6.25 kN m" on screen (no middle dot). Error notes overlap the equation below. Copy-as-text of unfinished equations has unbalanced brackets. |
| 6 | Measured length as a variable | yes (Lw·2 = 28.2222 m) | 9 (+3) — no Revu equivalent | Length tool → 2 clicks → right-click ▸ Variable box at the top of the menu → "Lw" Enter → F12 → `Lw*2=` | none | The Variable box is easy to find in the right-click menu. In Properties it is below the fold. |
| 7 | Page break after row 20 on a spreadsheet page | yes | 10 — 1 over par | Document ▸ Insert ▸ Spreadsheet page → click A21 → right-click ▸ Insert ▸ Insert Page Break | opened right-click ▸ Page Layout first (Excel keeps Breaks there); it holds only "Reset All Page Breaks" | There is no page-break command in the menu bar at all. |
| 8 | Split, drag a doc between panes, unsplit | **no** | 16 — par is about 5 | File ▸ Open (replaced the first doc) → File ▸ New Tab → File ▸ Open → View ▸ Split View → drag tab → View ▸ Split View | File ▸ Open replaced the open PDF instead of adding a tab. Looked in Window ▸ for Split (Revu). | A straight sideways drag of the "other.pdf" tab onto the right pane moved **set4.pdf** instead, leaving it in that pane twice. Dragging down and round first works. Split View takes 3.8 s and unsplit takes 0.5 s. Each pane repeats the whole menu bar and every toolbar. |
| 9 | Find every "TBC" and replace it | yes (markups; PDF text cannot be replaced, as in Revu) | 2 (+4) — par | Ctrl+F → Search panel → "TBC" Enter → Replace with → Replace all | Ctrl+H (Excel/Word Replace) does nothing | After Replace all, the 6 drawing hits stay listed. The summary that explains why is cut off ("Replaced 2 — 6 fou"). |
| 10 | Print pages 2–3 without markups | yes, by a workaround | 10 (+3) — par about 5 | Ctrl+P (Qt's print dialog, no markups option) → printed with clouds → Ctrl+A → Edit ▸ Hide → Ctrl+P → pages 2–3 → Edit ▸ Show Hidden | Print has no Markups on/off. Revu's Print dialog has it. | The print dialog opens with Output file "/root/" (a folder, no name). The page range is hidden behind "Options >>". |
| 11 | Save a callout style, reuse with a number key | yes | 11 (+3) — no Revu equivalent | draw callout → Properties Line Width 3 → Markup Styles bar "+" → Q → 1 → draw | right-click ▸ has no "save style" (only Add to Tool Chest / Set as Default) | The Properties title then reads "Callout Style 1 — Style 1". |
| 12 | Hide/show Markups List; filter to clouds | yes | 5 (+3) — par | Alt+L ×3; type "cloud" in "Filter markups…" (also: right-click the Type heading ▸ untick) | left-clicked the Type heading looking for Revu's filter funnel; it sorts | The column filter is only on a right-click of the heading. The groups are listed Page 4, 3, 2, 1, and the empty Page 4 group shows. Subject is blank for clouds and callouts. Drawing a plain **Rectangle** on an unscaled page opened Set Scale, on every try. |

11 of 12 tasks were done. 7 of those took no more clicks than a Revu, Excel
or SMath user would need.

## Findings (deduplicated, critical → minor)

Each line gives the severity, where it happens, what happened and what a user expects. Confidence: verified twice unless marked.

1. [MAJOR] View ▸ Split View, document tab drag — dragging tab "other.pdf" straight across onto the other pane's tab bar moved the *other* document (set4.pdf), which then appears twice in that pane; dragging down out of the bar first works — Revu moves the tab that was dragged. (harness doubt: synthetic QTest tab drag; deterministic over 3 runs; `tasks.py 8`, `NOVICE_T8_ROUTE=down` for the working route; mainwindow.py DetachableTabBar/_track_dragged_tab/tear_off_document)
2. [MAJOR] File ▸ Open — opening a second PDF replaces the document in view, asking only to save. Revu opens each file in its own tab, and the user has to know about File ▸ New Tab first. (mainwindow.open_document → _open_chosen)
3. [MAJOR] Calc mode, typing `L:=5 m` — the space selects the expression and `m` replaces it: `L:=5` is silently lost and only `m` is left, with no message. SMath users at least see what was replaced, and a novice expects `5 m` to read as 5 metres. The same happens to `w:=2 kN/m`. (calc editor, space handling)
4. [MAJOR] Calc mode, units — `5*m` and `2*kN/m` give "m - not defined." / "kN - not defined."; only SMath's `'m` works. SMath shows a known unit name as a unit when nothing of that name is defined. (calc engine/editor unit recognition; confidence on SMath's exact behaviour: medium)
5. [MAJOR] Rectangle / Ellipse tool on an unscaled page — every drag opens the Set Scale dialog, and Cancel drops the shape; the 2nd drag asks again. A Revu rectangle is just a markup and never asks for a scale. (view._press_draw scale_tools)
6. [MAJOR] Text box tool, single click — one click places an empty box waiting for a second corner ("click again to finish"), and the words typed next are lost. Revu: one click gives a default-size box ready to type. (probe_textbox.py; view text tool)
7. [MAJOR] View ▸ Split View — takes 3.8 s every time (median of 3; unsplit 0.5 s), well over the 100 ms stall budget; the frozen window gives no feedback. (timing.py; mainwindow.split_document builds a whole second MainWindow)
8. [MINOR] File ▸ Print… (Ctrl+P) — Qt's generic print dialog has no Markups on/off, no page range visible until "Options >>", and Output file "/root/". Revu's Print has Pages and a Markups checkbox. The only way is Ctrl+A ▸ Edit ▸ Hide ▸ print ▸ Show Hidden. (mainwindow.print_document)
9. [MINOR] Insert Blank Page dialog — shows Width 420, Height 297 with Orientation "Portrait" ticked for a landscape A3 page; the page made is landscape. The radio should follow the size. (pagedialogs InsertBlankPageDialog)
10. [MINOR] Area measurement just drawn — its value label sits under the two yellow handle dots, so the answer cannot be read (screenshot t2_area_label_zoom). Revu keeps the label readable, and the value is in the Measurements panel. (items/measure.py label vs handles)
11. [MINOR] Spreadsheet right-click ▸ Page Layout — holds Reset All Page Breaks, Print Area and Page Layout…, but not Insert/Remove Page Break, which sit under Insert ▸ and Delete ▸. Excel groups all three under Page Layout ▸ Breaks, and the menu bar has no page-break command at all. (tableedit._page_layout_menu)
12. [MINOR] Status bar "Scale 1:1" — shown for a page with no scale, so a measurement looks calibrated when it is not. Revu shows the page as uncalibrated. (Clicking it opening Set Scale is good.)
13. [MINOR] Scale naming — the same command is "Page Scale…" (Document menu, Ctrl+Shift+K) and "Set Scale…" (Current Page, thumbnails, right-click), and Tools ▸ Measure has only Calibrate. Revu users look for one name in one place (the Measurements panel). (mainwindow act_scale)
14. [MINOR] Markups List — groups are listed Page 4, 3, 2, 1, and the empty "Page 4" group is shown. The column filter is only on a right-click of the heading, and a left-click sorts. Revu lists pages ascending, hides empty groups and shows a filter funnel on each heading. (panels.MarkupsPanel)
15. [MINOR] Cloud and Cloud+ (also callout) — Subject is blank in Properties and in the Markups List, and the Cloud+ Properties title says "Callout Properties". Revu fills Subject with the tool name ("Cloud", "Cloud+"), as CalcForge already does for "Area". (items/text.py, shapes)
16. [MINOR] Equation answer units — the screen shows "6.25 kN m" (a space) while copying gives "kN·m". The brief says units show as "kN·m". (calc display)
17. [MINOR] Error notes under equations — "m - not defined." overlaps the next equation's first line when equations sit one grid row apart (screenshot t5_attempt2). (calc layout of notes)
18. [MINOR] Copy as text (calc.record.plain_text) of unfinished equations — `M := w·L²/8)=` for w·L^(2/8) and `M := w·(L²/8=`, with unbalanced brackets; a finished one gives `w·(L^2)/8`, so L^2 and L² are mixed. (calc/record.py; harness doubt: read through plain_text)
19. [MINOR] Ctrl+H — does nothing. Excel and Word open Replace with it; here Find & Replace is Ctrl+F's Search panel. (shortcuts)
20. [MINOR] Search panel after Replace all — the 6 drawing hits stay listed, and the summary that says only markups were replaced is cut off at the default panel width ("Replaced 2 — 6 fou"). (searchpanel.py)
21. [MINOR] Table — there are two "Table" buttons (Calculation toolbar and Tools toolbar) and two menu entries (Tools ▸ Markup ▸ Table, Calculation ▸ Table) with different tooltips, so it is unclear whether they differ. There is also no AutoSum Σ button, though Alt+= works. (mainwindow toolbars)
22. [MINOR] Split View chrome — each pane repeats the full menu bar (cut to "File Edit View »") and all four toolbar rows, and the panels collapse. Revu's split keeps one ribbon. (SplitDocumentWindow)
23. [MINOR] Menu bar at 1280 px — Help (and more) is hidden behind "»". (menu bar width)
24. [MINOR] Close the last tab — File ▸ Close leaves an "Untitled" document instead of an empty workspace (Revu). (close_document_tab)
25. [MINOR] Stalls over 100 ms (fresh process; first time / median of 5): right-click on a Cloud+ 329/220 ms, Cloud+ "click where the words go" 287/160 ms, Text box drag 130/130 ms, first pick of the Cloud+ tool 258 ms. (timing.py; times include a 30 ms popup-poll tick)
26. [MINOR] Area Unit combo reads "m^2" beside the value "m²", and the X/Y/Width/Height fields of a scaled measurement are in paper mm (141.1 mm), not the 14.11 m it measures. (panels.PropertiesPanel measure section)
27. [MINOR] Markup Styles — after "+", the Properties title reads "Callout Style 1 — Style 1" (named twice). Nothing in the callout's right-click menu says it can be saved as a style; it is found only through the Markup Styles bar. (markupstyles.py)

**Worked well:** Cloud+ in one button, red by default; save and reopen keep the
markup; the status-bar Scale button opens Set Scale; the Area value is correct
(149.34 m²); the Revu thumbnail menu and Insert Blank Page/Delete Pages dialogs;
table cells type like Excel, with a formula bar and Alt+= AutoSum; SMath `'`
units give 6.25 kN·m; the measurement's Variable box sits at the top of its
right-click menu and equations read it; the page break shows as a blue line
with "Page 1/Page 2"; Ctrl+F's Search panel has Replace/Replace all; number-key
callout styles work; Alt+L toggles the Markups List and "Filter markups…"
filters by type.

**Harness notes:** the tile renderer uses spawn processes, so every script keeps
its work under `if __name__ == "__main__"`. Offscreen Qt does not give the
keyboard back to the main window after a dialog closes, so `harness._refocus`
does. Without it F12 seemed dead after Set Scale, which is a harness artefact,
not a finding. Leftover windows from earlier tasks slow later ones down (Split
View measured 47 s that way), so each task runs in its own process.
`QMenu.popup()` menus (the Markups List heading filter) are picked up after the
event rather than by the modal watcher.
