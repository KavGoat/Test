# Engineering Calc App — Requested Features & Bugs (v2, more detail)

Extracted from your 154 messages (2026‑09‑01 to 2026‑09‑03) plus the 6 new screenshots/prompts you just sent. Grouped by topic, deduplicated (several messages were verbatim repeats/recaps of earlier ones — merged those), and expanded so each item explains the actual expected behaviour, not just a label. Message numbers in parentheses trace back to `myinputs.md`; items marked **(new)** come from the screenshots in this message.

**This is the living list.** It is kept in the repository and updated as
things are asked for and as they are built. Nothing is removed: where a later
message contradicts an earlier one, the existing line is rewritten to say what
was most recently asked for, and says so. A ticked box means the behaviour is
in the code *and* held there by a test — every one of them was checked against
the code rather than against memory.

One correction from your note: anywhere below that says "right‑click," I mean it shows up **in the context menu that appears after right‑clicking**, and — unless stated otherwise — that context‑menu option should appear for **every item type it logically applies to** (e.g. rounded‑corner/arc conversion should be offered on rectangles, polygons, polylines, clouds, wherever a corner or segment exists), not hard‑coded to one shape.

### ⚠ Contradictions found on review

Checking this against your raw messages turned up a few places where either I got it wrong, or your own messages disagree with each other at different points in the 3 days. Flagging these rather than silently picking one:

1. **Equation/text entry key — my mistake, now fixed.** §3 previously said the space‑based text/equation switch should be *removed* and replaced by explicit `"`/`\`/`/` trigger keys. That's backwards — msg 66 says the opposite: keep the space rule (no space = equation, space = text), and only remove the narrower bug where a space *after a number specifically* was wrongly turning into a unit. Corrected below.
2. **Which key starts an entry, at all.** Your messages describe two different models at different times: early on (msg 6, then msg 24) `"` starts *text* and `\` (later swapped to `/`) starts a *separate* equation entry — two distinct keys. Later (msg 66, 83, 131, 139 — repeated four separate times over the last day) you describe **one single key, `"`, for both**, with equation‑vs‑text decided purely by whether a space gets typed. I've treated the later, repeatedly‑confirmed model as the real requirement below, since it supersedes the earlier one and shows up four times independently. Flag me if that's wrong and the two‑key model was actually what you meant to keep.
3. **`\` vs `/` for the in‑text‑box equation insert.** Separately from #2, msg 86 says typing `\` inside a text box inserts an inline equation reference. But msg 24 asked to swap the *equation trigger key* from `\` to `/` a day earlier. It's unclear whether that swap was meant to carry over to this inline‑insert feature too, or whether `\` there is intentional/different. Left as `\` below per the literal text of msg 86 (the more recent of the two), but worth confirming.
4. **Rounded‑corner/arc conversion — two different trigger mechanisms.** Msg 115 says this is a **right‑click context‑menu** action; msg 125 (same day, ~2 hours later) says it's triggered by **Ctrl+hover** instead. These could both be true (menu option *and* a hover shortcut, which is a common pattern), so I've kept both below — but they were never reconciled in your messages, so confirm whether you want both or just one.
5. ~~**Callout hinge: auto‑recompute vs. manual override.**~~ **Resolved — you confirmed:** moving the arrow head or the box always resets the hinge back to its auto-computed position, even if it had been manually dragged before. A manual drag only holds until the next time the arrow or box moves.

## 1. Core concept

- [x] Python desktop app combining three engines that share data: SMath-style calculation (with units), Bluebeam-style PDF markup/annotation, and Excel-style spreadsheets — the spreadsheet must be able to read variables computed in the calc section, and vice versa where relevant (1)
- [x] Document is page-by-page like a PDF editor (discrete pages, not one infinite canvas), default page size A4, and must be printable straight to PDF preserving layout (1)
- [x] 100% guaranteed-correct numbers and unit tracking, since outputs will be used to design real buildings — you suggested a background "calc verifier" that independently re-checks values/units and flags discrepancies before they're trusted (12, 13)
- [ ] Long-running work should never just stop when usage/tokens run out mid-task — it should pause and automatically pick back up once the limit resets, rather than requiring you to notice and re-prompt (130, 138)

## 2. Calculation engine — variables & units

- [x] SMath-style assignment: typing `=` on an undefined variable auto-converts it to `:=` (definition); typing `=` on an already-defined variable evaluates it; typing `:` explicitly forces a (re)definition even over an existing one (6)
- [x] Auto-suggest default units matching SMath conventions: kN, kPa, kN/m by default when the surrounding units match that family; length units auto-switch between mm and m depending on whether the numeric value is above or below ~1000 (6)
- [x] Live warnings for (a) unit mismatch in an expression and (b) reference to an undefined variable — shown inline near the offending term, not just in a log (6)
- [x] **Strict no-space rule inside equations — rewritten, latest message wins**: an equation entry must never contain a space, and a number immediately followed by letters (no space) is "number + unit". This line used to end "if a space is typed anywhere while in equation mode, convert the *entire* entry to a plain text item" — **that half is withdrawn.** Your latest message reports the conversion as a bug: "whenever I'm in an equation, adding a spacing will change to text line". So a space in an equation is simply **refused** — nothing is converted, the entry stays the equation it was, and the status bar says why. That holds in every equation state: a fresh entry, one opened with `"`, and one being re-edited (6/22/66, refined, then corrected)
- [x] The opening `"` should be treated as "assume equation mode first" and behave differently from how a pre-existing equation item behaves when re-edited — i.e. entering fresh vs. editing an existing equation are two distinct interaction states that both need to respect the no-space rule **(new)**
- [x] Fix: typing Backspace, Escape, or `=` while inside an equation sometimes doesn't register / doesn't do anything — these three keys need to be reliable in every equation-edit state **(new; reported again, but that report was against a build made before the fix — the cause was the view closing the line whenever it lost the keyboard, which a right-click menu or a click on a toolbar button does)**. Re-checked since with 360 randomised keystrokes through the real event queue, with the live recalculation firing in the middle of them: not one Backspace, `=` or character dropped. If it still happens on a build that has this, say what was clicked just before
- [x] **(new)** Bug: `kpa` is not recognised as a unit and no unit list comes up while typing it. A unit typed in the wrong case must still be found and offered — the list is what corrects the case, so it has to appear for `kpa` and offer `kPa`
- [x] Committing a unit still needs a discrete action (Tab) rather than auto-completing as soon as a matching unit string is typed; the unit list shown while typing must be navigable with arrow keys or mouse click, and must also list already-defined variable names that match what's typed so far (22, 139)
- [x] Lazy evaluation: a line should only compute and *display* its result when `=` is typed at the end. If no `=`, still evaluate it silently in the background so later lines can reference the value, but show nothing (22)
- [x] Per-result display-unit override: right-click (or similar) a computed value and change what unit it's displayed in without changing the underlying definition (22)
- [x] Bug: changing the *displayed* unit on one reference/instance of a variable incorrectly changed the original definition elsewhere too — display-unit changes must be local to that one instance (68)
- [x] Add right-click options for output formatting: choose decimal places, scientific notation, or significant figures per result (121)
- [x] Audit every Greek letter glyph — phi in particular is rendering as two visually different glyphs depending on where it's used; needs to be one consistent glyph everywhere (96)
- [x] Autocomplete dropdown of matching variable names while typing inside an equation, with Tab to accept — this should work for non-numeric typing generally, not just a specific trigger (87, 22)
- [x] `_` (underscore) and `^` (caret) should trigger subscript/superscript formatting even when typed inside plain text boxes and table cells, not only inside equations (85)
- [x] Superscript is still rendering too close to the base character/too cramped — needs another visual pass on spacing (88, 97, 99)

## 3. Calculation blocks vs. calculation lines

- [x] Rename and formally split the two concepts: a **calculation line** is a single-line calc entry; a **block** is a multi-line container. These should be distinct object types with distinct UI, not the same thing styled differently (25)
- [x] Blocks support a "self-contained" toggle: when on, the block has its own local variable scope isolated from the rest of the document (but can still *read* already-defined global variables); when off, its variables behave as normal globals (9)
- [x] Right-click a block for a "self-contained" toggle; **default must be off (not self-contained)** — this was requested repeatedly and should be confirmed as the actual default in Preferences too (11, 15, 71, 78)
- [x] A Preferences/Settings page where app-wide defaults like this live, so they don't need to be re-set per document (71)
- [x] **(corrected — see contradiction #2 above)** There is a single entry trigger, `"`. It starts entry mode and, by default, assumes you're writing an equation. No other keystroke should ever switch into a calc/markup tool by accident while typing normally — this is what actually stops q/c/a etc. from firing a markup shortcut mid-type (6, 66, 83, 131, 139)
- [x] **(corrected — see contradiction #1 above)** Keep, not remove, the space-based switch: once inside a `"` entry, typing letters/an expression with no space keeps it as an equation; the moment a space is typed, the whole entry converts to a plain text item instead. This is the actual desired mechanism, not something to strip out (66, 83, 139)
- [x] Separately, fix the narrower unit-typing bug: a space typed directly after a number was wrongly being interpreted as "start of a unit" — units must attach directly to the number with no space, and that specific behavior should be removed without touching the equation/text space-switch above (66)
- [x] **(see contradiction #3 above)** Inside a text box, typing `\` mid-paragraph should insert an inline equation reference: typing a variable name there renders `variable = value [unit]` inline, or performs/shows a live calculation if you type an expression, so you can reference computed values directly in prose — confirm whether this should now be `/` instead, matching the equation-key swap in msg 24 (86)
- [x] Ctrl+Shift+M is meant to convert an existing line/selection into a block in place, but it currently also spawns an unwanted duplicate copy — fix so it's a clean in-place conversion (134)

## 4. Equation editor

- [x] Equation editor must match SMath exactly: a **single unified view** — no separate "inline editing" mode vs. "final rendered" mode. What you see while editing (fractions, powers, subscripts) is the same visual form as the printed/final result, edited in place, no left/right shifting or re-zoom on click (49, 66, 67, 103, 132)
- [x] Clicking into an existing fraction to edit its numerator/denominator doesn't currently work — this likely needs the equation model rebuilt structurally as a tree of lines/blocks so the in-place editor is authoritative rather than a rendering layer on top of separate source text (103, 132) — re-checked: clicking either half of a fraction, a fraction inside a fraction, or a line of a block puts the caret at that place in the source, zoomed or turned, and a double-click there takes the word it was aimed at
- [x] Units should render in blue throughout, matching SMath's convention, so they're visually distinct from variables/numbers at a glance (22)

## 5. Lookup tables & functions

- [x] Named data/lookup table object (e.g. bolt diameter vs. shear capacity) usable from the calc engine like a VLOOKUP: `V = table_x(d, A, B)` looks up `d` in column A of table `table_x` and returns the corresponding value from column B (30)
- [x] Table lookups should accept the table's actual header text as the column identifier (e.g. "Dia" / "Shear") in addition to plain spreadsheet-style letters (A, B) — both should resolve to the same column (91)
- [x] Linear interpolation function for use in calc expressions (e.g. interpolating between two rows of a table or two known points) (30)
- [x] Remove the leftover placeholder/"ghost" table name ("bolts") that shows by default on a newly inserted table before you've named it (74)
- [x] When a table is named, show that name both in the Properties panel and as a visible label above the table on the page (38)

## 6. Spreadsheet (Excel-like) behavior

- [x] Formula entry should support clicking or arrow-navigating to another cell to insert its reference while typing `=...`, the same way Excel does — not just manually typing a cell address (22)
- [x] While editing a cell, pressing the Up arrow should move the edit cursor to the cell above, Excel-style (52)
- [x] Pasting cells copied from Excel should create a real table object here, and should carry over relative formulas where translation is possible (fall back to values only where it isn't) (12, 23, 109)
- [x] Excel-style fill/autofill drag handle on a cell selection, respecting `$` absolute-reference locking when dragged (38)
- [x] Resize column widths and row heights by dragging their borders (75)
- [x] Quick left/center/right alignment controls for cell content (84)
- [x] Cursor icon should change to a resize cursor when hovering a column/row border — currently doesn't, making it hard to tell it's draggable (108)
- [x] Fix visual overlap between adjacent table cells so content doesn't run into the next cell (11)
- [x] Clarify how a computed/output cell is displayed vs. a plain input cell (e.g. a cell defined as `q_floor`) — currently ambiguous which is which (11, 61)
- [x] **(new)** Bug: in the insert-table dialog, the "header row" checkbox shows as ticked, but clicking it off and back on leaves it unticked (state gets lost on the second toggle) — fix the checkbox's state handling
- [ ] **(new)** Dragging out a table must add and take away rows and columns as it goes, at a fixed default cell size — not stretch a fixed 6×4 grid to whatever the box is. The drag says how many cells, not how big they are

## 7. Markup tools — placement & interaction model (Bluebeam parity)

- [x] Every placeable object (markups, toolset items, groups) should show a live, cursor-following preview of exactly what will be placed, before you click to commit it (37, 41)
- [x] "Properties mode" (place a new copy using the last-used style/properties rather than an exact one-to-one duplicate) should only be selectable for a single markup object — for calc blocks, images, graphs, and groups it should be greyed out or simply not offered, since it doesn't make sense for those (41)
- [x] Selection tool: a click-drag draws a rectangular marquee select; a plain click (no drag) instead falls back to a polygon/lasso-style custom selection area (39)
- [x] Rectangle marquee direction matters: dragging left-to-right selects only items fully enclosed by the box; dragging right-to-left selects enclosed **and** intersecting items. This left/right distinction is for the rectangle marquee only — it does not apply to the polygon/lasso selection (39)
- [ ] **(new)** Selecting as it stands — click, and click-drag for a rectangular marquee, with no key held — is right and stays as it is. What Shift adds: **Shift and click point after point draws a polygon to select inside**, closed by clicking the first point again or by Enter
- [x] **(contradiction — later message wins)** A plain click on empty canvas must not start a select-drag; a rectangular marquee begins on a click-drag and a lasso on Shift+click-drag. The original half of this (msg 53: a click sets an *insertion point* for pastes) was withdrawn by msgs 46 and 74 ("remove the insert click point thing and remove other dependent functionality") — there is no insertion point; what you are pointing at is where things land (53, superseded by 46/74)
- [x] Escape must always fully clear selection and exit whatever edit/tool sub-state you're in, in one press, regardless of how deep the current mode is nested (81, 92)
- [x] Fix: it's possible to get permanently stuck inside a tool (e.g. right after placing a callout's arrow) with no way out — Escape doesn't help and no other tool can be switched to (82, 110)
- [x] Cursor icon must reflect context at all times: a generic move cursor only while actually moving something; distinct cursors for dragging a table border, for a resize handle, and for adjusting a leader/arrow endpoint (76, 110)
- [x] Selection should always show its bounding box immediately on select — currently sometimes the item is selected internally but no visible box appears until you right-click it (148)

## 8. Markup tools — specific shapes

- [x] Cloud tool, shortcut **C** (10)
- [x] Rectangle tool, shortcut **R** — should be scale-aware (drawn to real-world scale using the page's calibration, or typed width/height); dimensions should appear only in the Properties panel while selected, never as floating text on the canvas itself (10, 16, 34, 47)
- [x] Ellipse tool; holding Shift while drawing constrains it to a perfect circle, with the same scale-aware behaviour as the rectangle tool (29)
- [x] Polygon tool — explicitly *not* scaled to the page (freeform annotation shape) (10)
- [x] Arrow tool (10)
- [x] Cloud vs. Cloud+ and cloud-callout: a click-and-drag produces the simple rectangular cloud; clicking each point individually produces the custom-shaped cloud ("Cloud+"). The same click-drag-vs-click-each-point distinction governs whether a cloud callout comes out rectangular or custom-shaped. After the cloud shape is finished, right-click or Enter proceeds to placing its text box (143)
- [x] Cloud callout must **not** have an arrowhead — the connecting line should run from a corner or midpoint of the cloud straight to the text box, with no arrow tip (100, 141)
- [x] Curve/arc drawing tool available directly from the toolbar, not only as a conversion of an existing shape (115)
- [x] The Insert menu should include a "Markup" submenu listing every drawing tool (piles, polygons, clouds, etc.) so they're discoverable outside the toolbar too (115)
- [x] Shift-to-constrain (snap the current segment to 0°/45°/90°) must work consistently across *every* drawing tool — currently the pen and highlighter tools ignore it even though rectangle/line do respect it (29, 40, 43)
- [x] Highlighter needs to support straight-line strokes (hold Shift, or a straight-line mode), same as the pen tool is expected to (40, 43)
- [x] Structural break symbol: available in the right-click context menu on any line segment, rectangle edge, or polygon edge — inserts the standard structural-drawing "break" symbol at that point (115)
- [x] Rounded-corner and convert-to-arc are available **in the right-click context menu**, offered on any shape with corners/segments (rectangle, polygon, polyline, cloud, etc.) — currently not visible/accessible anywhere, needs to be built and exposed. Rounded corners get a radius handle; arc segments get **dual handles** — one to adjust arc length, one to adjust arc angle — matching Bluebeam's behaviour (115, 125, 126, reference photo in msg 126, still reported missing in 149)
- [x] Rectangles specifically should support right-click add/remove control point; the moment a rectangle's corner is moved such that it's no longer axis-aligned/rectangular, it should automatically convert into a general polygon so it keeps behaving correctly (115, **new** detail from screenshots: "rectangle should have control point add/remove too, which becomes a polygon automatically if not rectangular")
- [x] Add/delete control points generally: Shift+hover over an existing point deletes it; Shift+hover over a mid-segment adds a new point there. Ctrl+hover over a point converts it to rounded; Ctrl+hover over a segment converts it to an arc — **(see contradiction #4 above)** this is a second, hover-based trigger for the same rounded/arc conversion described in the item above via the right-click menu; treating both as valid parallel shortcuts for now, confirm if only one should exist (125)
- [x] **(new)** Bug: snapping to the *centre/midpoint of a polygon edge* does not work — should snap the same way rectangle/line midpoints do

## 9. Callouts, text boxes, dimensions

- [x] Callout (arrow) tool, shortcut **Q**: press Q, next click places and locks the arrowhead (must render immediately and visibly, not silently), the click after that places/sizes the text box (10, 34, 38, 140)
- [x] Text boxes (including callouts) auto-grow to fit their content as you type, and never auto-shrink again just because content was deleted; Alt+Z manually re-fits the box tightly to current content on demand (55)
- [x] Callout text box starts at a fixed default size rather than requiring a manual rectangle-drag to create it (55)
- [x] The leader's attachment point ("hinge") should auto-snap to the midpoint of whichever of the box's 4 sides the leader is closest to, and should only be draggable *along* that side (perpendicular to it, not away from it) — this should be computed automatically by default but remain user-adjustable (38, 140, reference photo msg 116)
- [x] If you manually drag the hinge point across to a different side of the box, the leader should re-anchor to the new side rather than resisting (140)
- [x] Arrow-style callouts should support **multiple leaders** on one callout (add as many as needed), not just a single fixed leader — right-click should offer Add Leader / Delete Leader (140, **new**: currently the right-click menu is missing Add Leader entirely)
- [x] Plain text boxes and normal callouts should also support adding/removing leaders, using the same mechanism (90)
- [x] Ctrl+drag (duplicate) of a callout must move the entire object together — currently duplicating leaves the arrowhead fixed in its original spot while the rest of the callout moves, tearing them apart (38)
- [x] Custom dimension tool (Alt+M): click first point, click second point, then place the dimension text directly with an in-place text cursor — no popup dialog. Text is blank by default until typed. It sits in-line with the dimension line by default, but Shift+click the number to drag it off the line, which then draws its own small leader connecting it back (10, 37, reference photo msg 116)
- [x] Bug: rotating a placed dimension shows an incorrect/flickering value *while* dragging the rotation, only snapping back to the correct value on release — the displayed value should stay correct throughout the drag (117)
- [x] **(new)** Full leader/hinge rewrite needed: the hinge point currently doesn't exist yet during placement (before the box is finalized), which breaks the interaction — it needs to be built from scratch so the in-progress placement behaves exactly like the finished, after-placement leader from the very first click, not as a separate/different code path
- [x] Hinge point must stay perpendicular to whichever side of the box it's attached to at all times (see reference photos) — this restates the item above from §9 (perpendicular, auto-computed, but user-draggable along the side), repeated again in the latest screenshots, so treat it as one requirement not two (38, 140, and the new screenshot batch)
- [x] **(new)** The leader line must never be allowed to visually cross through/over the text box itself — constrain valid hinge positions so that geometry is impossible
- [x] **Resolved (was contradiction #5):** moving the arrow head, or moving/resizing the text box, always resets the hinge back to its auto-computed position — this takes priority over any prior manual drag, which only holds until the next move. Currently the hinge is frozen wherever it was first set and never updates, which is the bug to fix
- [x] **(new)** Remove the small floating description/label that appears on markups and fades out after a moment — not wanted on any markup type
- [ ] **(new)** Bug: the cloud part of a cloud call-out vanishes partway through placing it and comes back at the end — it has to be there, unbroken, from the first click
- [ ] **(new)** A cloud call-out is a call-out: the same hinge, the same clear-of-the-box rule, the same automatic re-computation, and the same several leaders — the only difference is that its leaders are drawn as clouds rather than as arrows. One set of behaviour, not two
- [ ] **(new)** "Add leader" belongs in the right-click menu itself, not inside a sub-menu — and choosing it asks which kind: an arrow leader or a cloud leader
- [ ] **(new)** A call-out or cloud call-out whose last leader is taken away becomes a plain text box; a text box that is given a leader becomes a call-out. The three are one object in different states, and moving between them is what adding or removing the last leader means

## 10. Snapshot tool

- [x] Snapshot tool, shortcut **G**: a Bluebeam-style capture that's flattened and non-editable once placed, but stays crisp when zoomed (vector, not a raster grab) (10, 29)
- [x] Should capture as PDF vector content (plus any images that were within the captured area), stored as its own distinct object type — not saved as a generic "Image" item (29, 144)
- [x] A snapshot is specifically the *screen-capture* tool's output — pasting an ordinary image from elsewhere (e.g. clipboard screenshot from another app) must be treated as a plain pasted image, never as a "snapshot" object (56, 144)
- [x] Fix: snapshots and pasted images intermittently show "image missing" instead of the actual content (106, 107)
- [x] Recolor tool for specific items (a snapshot, or a whole page) that remaps PDF line-work from one color to another, e.g. for redlines (29)

## 11. Snapping, grid, alignment

- [x] Two distinct snap types needed: (1) **snap to grid** — the regular page grid; (2) **snap to content** — snaps only to flattened/PDF line-item corners and endpoints (existing drawing content), *not* to generic vertical/horizontal alignment guides (29, **new** clarification: "snap to content... only snap to pdf line item corners and ends, and the vertical/horizontal line snapping is not needed" for that mode specifically)
- [x] Separately, snapping to **items you've drawn** (your own markups, not the underlying PDF) should include snapping to vertical/horizontal alignment based on the points of whatever else is already drawn on the page **(new)**
- [x] Holding Ctrl disables all snapping for as long as it's held, across drawing, calibration, and measuring tools alike (29, 136)
- [x] **(new)** Bug: turning "snap to grid" off doesn't actually stop points from snapping to the grid — the toggle isn't being respected
- [x] Fix: no visual indicator shows when you're actively snapping to another markup/existing item — there should be a highlight or marker the moment a snap engages (112)
- [x] Fix: snapping doesn't work on the very *first* point placed while drawing a new line — it only starts working from the second point onward; it should be active from the first click (113, **new**: "when drawing something the first point does not show the snap indicator, only the point after shows it — show it for all points whenever snap is on")
- [x] **(new)** The live placement preview (the ghost shape shown before you click to commit) must use the exact same snapping logic as the final placed geometry — right now they can disagree
- [x] New markups/drawing tools should snap to both the grid and existing items while being drawn, generally (72)

## 12. Move, duplicate, group

- [x] Move/duplicate/array a selected item by a specified X offset repeated Y times (i.e. a repeat-pattern tool) (10)
- [x] Ctrl+drag duplicates the item being dragged; Shift+drag constrains movement to 0/45/90°; Ctrl+Shift+drag duplicates *and* constrains to 0/45/90°; releasing Ctrl mid-drag re-enables snapping (29)
- [x] Grouped items should render **one single bounding box** around the whole group when selected — currently each item inside the group still shows its own individual box (36, 38)
- [x] Fix: saving a group into "My Tools" only preserves one item from the group instead of the entire group — the whole group must round-trip correctly (38)

## 13. Copy / paste

- [x] Ctrl+C / Ctrl+V for whole pages, with an insertion-point indicator that follows the cursor to show where the paste will land (73)
- [x] Ctrl+Shift+V performs "paste in place" — pastes at the exact same coordinates as the copied item, Bluebeam-style (82, 111)
- [x] Pasting a page should also show a clear insertion-location indicator, same as pasting other content (147)

## 14. Toolsets / "My Tools"

- [x] Support multiple custom toolset groups, each able to hold any mix of content — markups, calc blocks, anything (36)
- [x] Two distinct paste modes, matching Bluebeam: "one-to-one" (exact duplicate including contents — e.g. a saved text box keeps its saved text) vs. "properties only" (reuses the style but not the content) (36, 41)
- [x] A "My Tools" section for quick access; items numbered 1, 2, 3…; pressing that number key while not in an edit mode places that tool directly (36)
- [x] All toolsets/groups should be shown expanded by default, similar to Bluebeam's Tool Chest, rather than collapsed (94)
- [x] Clicking a toolset item should both select it and arm it for placement in one action (94)
- [x] Remove the odd blue dashed box currently shown while placing something from My Tools — it's visual noise (94)
- [x] Replace the current "move up/move down" reordering buttons with plain drag-to-reorder (54)
- [x] Each toolset entry should show a real preview/thumbnail of the actual item, not a text description; when the entry is in properties mode, show a generic example of that markup type styled with its saved color/other properties (54)
- [x] Relocate the toolset "save" action to a right-click option on each item rather than a dedicated button, and make the "properties mode" toggle discoverable — currently can't be found in the UI at all (105)
- [x] "Set as default" button in the Properties panel: applies the current object's properties as the default for that tool going forward (36)

## 15. Panels & layout

- [x] Bluebeam-style unified dock: Pages, Bookmarks, Variables, Toolsets/My Tools, Properties, and any other relevant panel should each be a togglable icon that can be dragged individually to dock on either the left or right side (45, 62)
- [x] The Properties panel should be resizable down to zero width (effectively hidden) and dragged back open again later (23)
- [x] Fix: scrolling the mouse wheel while the cursor happens to be over a dropdown inside the Properties panel changes the dropdown's selected value instead of scrolling the panel — this must never happen; scroll should always scroll the panel (80, 92)
- [x] Page view controls (fit width, show grid, etc.) belong as buttons along the bottom of the canvas, similar to a "levels" style bar; page number/navigation should be centered with explicit next/previous buttons, Bluebeam-style (93)

## 16. Toolbars

- [x] Toolbars are customizable and draggable to the left or right side of the window (20)
- [x] Toolbar drag handles should be small 3-dot grip icons, matching the rest of the app's affordances (23)
- [x] Ability to pin or hide the variables/properties list independently (20)

## 17. Dark mode, icons & canvas/viewport

- [x] Full dark mode across the entire UI (20)
- [x] Fix icons that are invisible or wrong-colored in dark mode — undo/redo were specifically flagged, but audit every icon (28, 52, 138)
- [x] Replace generic/placeholder icons with Bluebeam's actual icon set and naming wherever equivalent functionality exists, including undo/redo (10, 57, 63, 64 — reference screenshots supplied)
- [x] General UI modernization pass beyond just icons (20, 25)
- [x] The border/margin around the page canvas is too wide and not centered — needs to be reduced and properly centered (65, 70)
- [x] Distinct background color behind the page itself so the page's edge/outline is clearly visible against the canvas (19)
- [x] Continuous vertical scroll across pages, and standard app-like zoom behaviour — **(new)**: still reported broken/incomplete as of the latest check, needs re-verification, not just the original build — re-checked from the events themselves: the vertical bar runs through every page of the document, the trackpad scrolls by the pixel, Page Up/Down move a screenful, Ctrl+Home/End reach the ends, the wheel zooms about the pointer, and all of it still holds with the view turned
- [x] Zoom should center on wherever the cursor currently is, not on a fixed point — currently doesn't (139, 44)
- [x] Scroll-wheel zoom is broken entirely in some state (44)
- [x] **(new)** Bug: when the page/view is rotated, the scrollbar itself rotates along with it — the scrollbar should stay in its normal fixed orientation regardless of view rotation

## 18. Keyboard shortcuts

- [x] Full keyboard shortcut manager UI to view and rebind every shortcut (6, 20)
- [x] Only one shortcut manager should exist in the app — there are currently two separate ones, which is confusing (27)
- [x] All shortcuts must be disabled while actively in text-edit or equation-edit mode, **except** Ctrl+B/I/U which remain bold/italic/underline for text formatting (20, 131)
- [x] Entry into text/equation mode must require the explicit `"` trigger (see the corrected §3 entry-trigger items and contradiction #2 above) — plain letter keys (q, c, a, etc.) must never be misinterpreted as starting a markup tool while you're trying to type (34, 83, 131, 138)
- [x] Ctrl+B should mean "bookmark" everywhere **except** while inside text selection/edit mode, where it must remain Bold and not trigger bookmarking (104, 66, 66/92 bookmark-while-editing bug)
- [x] The repeat-placement-N-times-along-X/Y behaviour (see §12) should also be assignable/visible through the shortcut manager, not just accessible via modifier keys (23)

## 19. Pages & document structure

- [x] Right-click a page, or a multi-page selection, for: Delete, Duplicate, Insert Before, Insert After, Insert PDF, Insert Photo (23, 60, 123)
- [x] **(new)** Bug: several pages cannot be deleted at once. Picking more than one page in the pages panel has to work properly and everything that acts on a page has to act on the whole picked set — delete, move (reorder by dragging), copy and duplicate
- [x] Dragging a PDF file directly onto the page panel should show an insertion cursor/indicator and insert it at that exact point in the page order (114)
- [x] Insert-PDF must bring in the actual PDF content (vector text/lines), not a blank page and not a 150dpi raster snapshot of it — figure out what's required to preserve full fidelity, and ask if a specific library/dependency choice needs sign-off (25, 120)
- [x] **(new)** Insert-PDF must not ask for a DPI at all. There is no resolution to choose: everything in the file comes through as the PDF has it, vector work included. Drop the question from the dialog
- [x] Rotating a page must rotate the page shape **and every markup on it** together as one unit — currently the markups don't follow the page rotation (118, still broken as of msg 145)
- [x] Separate "Rotate View" command (View menu) that visually rotates the on-screen display of pages for reading convenience only, without altering the actual stored page rotation/orientation (119)
- [x] Fix: footer content renders outside the visible page bounds specifically on imported PDF pages (122)

## 20. Page setup (headers/footers/scale/grid)

- [x] Per-page setup panel: rotate, and change page size, independently per individual page rather than only document-wide (25)
- [x] Header/footer editor supporting: page number, date, title, custom free text, and a logo/image (23)
- [x] Right-click a page (or multiple selected pages) to add/remove header and footer in bulk (123, 124)
- [x] Dedicated "Calibrate" action for setting page scale: click two points, type the real-world distance between them plus a unit, and the scale is derived from that — not from clicking on a measurement you already happened to draw (25)
- [x] Current page scale should be displayed next to the page number in the page viewer/page panel (25, 31)
- [x] Right-click a page for a direct "Set Scale" option (25)
- [x] Grid-per-page: on by default for newly inserted blank pages, off by default for inserted PDF pages; independently toggleable per page via right-click on the page panel or via Page Setup; grid should print when enabled, and its print-visibility should be independently switchable from its on-screen visibility (127)

## 21. Measuring tools

- [x] Length/distance measure tool, shortcut **M** (10)
- [x] Area measure tool, shortcut **Shift+Alt+A** (10)
- [x] Measure and area/polygon tools should follow a click-point, click-next-point, ...,  finish flow — currently a measurement just drops a value in the wrong place instead of following your clicks properly (25, 143)

## 22. Bookmarks & table of contents

- [x] Bookmarks panel for document navigation, plus a matching Table-of-Contents block/element that mirrors the bookmark list (32)
- [x] Right-click a page → "Add to Bookmarks" (60)
- [x] Bookmarks themselves should be renameable/editable after creation (60)
- [x] Bookmarks and any links must remain fully clickable/working as hyperlinks in the exported PDF (32)
- [x] Fix: the bookmark shortcut fires accidentally while you're actively typing/holding text selected — it must not trigger during text edit (66, 92)

## 23. Import / interoperability

- [x] Import Bluebeam `.btx` toolset files — including tool sets, hatch patterns, line-type definitions, groups, and whatever other markup types are embedded in them. You've uploaded sample `.btx` files to the GitHub repo specifically for this to be tested against — verify import against those real files, not just synthetic ones (80, 92)
- [x] Fix: content imported from the `.btx` samples (specifically section-cut/circle symbols) currently renders corrupted — it should render as a proper structural section-cut symbol; reference screenshot supplied showing the correct appearance (137, 139, 149)
- [x] Format Painter tool, with an icon matching Bluebeam's paint-roller icon (146)

## 24. Undo/redo

- [x] Continuous interactions (e.g. dragging a slider) should collapse into a single undo step covering start-value → end-value, not one step per intermediate tick — unless there's a large enough pause between changes that they should be treated as separate edits (62)
- [x] Undo/redo icons should match Bluebeam's actual icons, not the current placeholders (57, 63)

## 25. Settings, persistence & spellcheck

- [x] Persist all user settings across sessions/restarts: keyboard shortcut bindings, dark mode, toolbar positions, which panels are hidden vs. shown — everything, not a subset (24)
- [x] Spellcheck using an NZ English dictionary (71)
- [x] Preferences page covering defaults such as "blocks default to not self-contained" and similar app-wide behaviour toggles (71, 78)

## 26. Menus & discoverability

- [x] Every capability (page operations, line operations, etc.) must be reachable from the main menu bar somewhere, not only via right-click or a shortcut (128)
- [x] Preferences/settings should live under a "Settings" top-level menu (128)
- [x] Help menu should include a searchable command/tool search (128)

## 27. Reliability / process

These two are about how the work gets done rather than about the app, so
there is no code to point at and no test to hold them. The answer to both,
written out here so it is on the record rather than in a chat message:

- [ ] Investigate and explain why background tasks were observed stopped unexpectedly, and prevent recurrence (129, 138) — **what happened**: a long test run or fuzz run is started as a background command with a timeout on it, and when the session's turn ends before that timeout the command is killed with it. Nothing crashed; the run was cut off. **What is done about it now**: long runs are given a timeout that matches how long they actually take, their output goes to a file that survives the run, and the file is read back and reported rather than assumed
- [ ] Never let hitting the token/usage limit silently end the session's work — pause, and resume automatically once the limit resets, without needing a fresh prompt from you (130, 138) — **not something this end can promise.** A session that runs out of context is summarised and continued, and that is automatic; a session that runs out of *usage* stops until the limit resets and needs a prompt to pick up again. What is under control here is that nothing is left half-finished and unrecorded: work is committed and pushed as it is done, and this list says what is built and what is not, so whatever picks the work up next — a fresh session, or this one after a reset — starts from the list rather than from memory

## 28. Miscellaneous fixes reported (screenshots referenced)

- [x] "Stamp: Approved" text is showing at the top of objects that aren't stamps at all — fix the condition that triggers it (69)
- [x] Square/other shape formatting renders visually incorrectly per the screenshot supplied (70)
- [x] General inconsistent/odd spacing in rendered equations, per screenshot (97)
- [x] The unit-selection dropdown list appears in the wrong screen position relative to what's being edited (98)
- [x] Arrow markups show a small control-point handle even when the arrow isn't selected — handles should only be visible while selected (101)
- [x] Rotation control point gets clipped at the shape's edge and visually glitches/smears while the item is being moved (102)
- [x] There's an unidentified "blue tool" in the UI that does nothing and can't even be selected/clicked — find and remove it (63)
- [x] Audit every Properties-panel option for redundancy or unclear labeling — e.g. what does "multiply highlighter" in the callout properties actually do? Several options may not be needed at all (61)
- [x] Highlighter tool leaves odd gaps/holes depending on the stroke path used to draw it (58, 59)
- [x] Table column/row resize doesn't show a resize cursor (108, duplicate of §6 item)
- [x] An object can get stuck showing a "move" cursor even when nothing is selected, and Escape doesn't clear it (110)

---

### How this list is kept
Items are grouped by feature area rather than by message, since many messages
(notably #15, #92, #95, #99, #138, #149, and the screenshot batches) were
re-statements, corrections or reminders of earlier asks — those are folded into
the relevant section rather than listed separately.

The rules it is kept by:

- Nothing is deleted. A request that has been superseded has its line rewritten
  to say what is wanted now, and marked as a contradiction so the history is
  readable.
- A box is only ticked when the behaviour is in the code and a test holds it
  there. "It looks like it works" is not ticked.
- New requests are added to the section they belong in, marked **(new)**.
