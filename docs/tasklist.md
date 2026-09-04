# CalcForge - Requirements and Bug Register

This register is synchronized from `docs/tasklist.xlsx`. Column A is
user-owned: `1` marks a completed requirement; blank means it remains open.
Agents may add, combine and clarify tasks, but must never mark a task complete
or change task status. Only the user updates completion state in the workbook
and explicitly requests a synchronization.

## Completed (user-confirmed)

- 1. Core concept: 4 confirmed requirement(s).
- 2. Calculation engine — variables & units: 8 confirmed requirement(s).
- 3. Calculation blocks vs. calculation lines: 3 confirmed requirement(s).
- 5. Lookup tables & functions: 5 confirmed requirement(s).
- 6. Spreadsheet (Excel-like) behavior: 6 confirmed requirement(s).
- 7. Markup tools — placement & interaction model (Bluebeam parity): 4 confirmed requirement(s).
- 8. Markup tools — specific shapes: 8 confirmed requirement(s).
- 9. Callouts, text boxes, dimensions: 11 confirmed requirement(s).
- 10. Snapshot tool: 4 confirmed requirement(s).
- 11. Snapping, grid, alignment: 4 confirmed requirement(s).
- 12. Move, duplicate, group: 3 confirmed requirement(s).
- 13. Copy / paste: 2 confirmed requirement(s).
- 14. Toolsets / "My Tools": 7 confirmed requirement(s).
- 15. Panels & layout: 1 confirmed requirement(s).
- 16. Toolbars: 3 confirmed requirement(s).
- 17. Dark mode, icons & canvas/viewport: 8 confirmed requirement(s).
- 18. Keyboard shortcuts: 2 confirmed requirement(s).
- 19. Pages & document structure: 4 confirmed requirement(s).
- 20. Page setup (headers/footers/scale/grid): 6 confirmed requirement(s).
- 21. Measuring tools: 3 confirmed requirement(s).
- 22. Bookmarks & table of contents: 2 confirmed requirement(s).
- 24. Undo/redo: 2 confirmed requirement(s).
- 25. Settings, persistence & spellcheck: 3 confirmed requirement(s).
- 28. Miscellaneous fixes reported (screenshots referenced): 2 confirmed requirement(s).

## Open Requirements

### 1. Core concept

- [ ] **(new)** Support a markup-only PDF document mode for drawing-review work. Opening a PDF in this mode provides Bluebeam-style navigation, markup, measurement and Snapshot tools, but hides or disables calculation lines, calculation blocks, tables and other calculation-specific UI so the document behaves as a focused PDF editor.
- [ ] **(new)** Support multiple open documents at once: PDF review documents and `.cfx` CalcForge documents appear in separate tabs, can be viewed side-by-side in a split view, and can be moved into independent application windows. Each document keeps its own pages, state and active tool without leaking into another tab/window.

### 2. Calculation engine — variables & units

- [ ] **(consolidated)** Fresh and existing single calculation lines use identical equation-entry behavior. `"` starts a calculation entry; units bind directly to their number, so `5kPa` is valid and renders as `5·kPa`; and typing any space converts the complete current calculation line to plain text. Calculation blocks do not permit spaces. The status bar should explain the conversion, and the behavior must remain consistent when a line is left and re-entered.
- [ ] Fix: typing Backspace, Escape, or `=` while inside an equation sometimes doesn't register / doesn't do anything — these three keys need to be reliable in every equation-edit state **(new; reported again, but that report was against a build made before the fix — the cause was the view closing the line whenever it lost the keyboard, which a right-click menu or a click on a toolbar button does)**. Re-checked since with 360 randomised keystrokes through the real event queue, with the live recalculation firing in the middle of them: not one Backspace, `=` or character dropped. If it still happens on a build that has this, say what was clicked just before
- [ ] **(new)** Bug: `kpa` is not recognised as a unit and no unit list comes up while typing it. A unit typed in the wrong case must still be found and offered — the list is what corrects the case, so it has to appear for `kpa` and offer `kPa`. **Done**: the list comes up for a unit typed straight after its number, and the error now reads "'kpa' is not defined — did you mean kPa?"
- [ ] **(reported again)** Recognised units must render blue in every calculation state. For example, `2m` may parse and calculate correctly but currently leaves `m` black; visual syntax colouring must agree with the unit-aware engine.
- [ ] **(new, reported again)** In a calculation line or block, `=` still misbehaves: sometimes nothing can be typed, sometimes text can be typed but not deleted. There is also still a "weird gap" before the `=`
- [ ] **(new)** Use one primary typeset expression renderer for a calculation while it is being edited and when it is at rest; do not maintain two competing edit/final rendering modes. An evaluated result triggered by `=` may render in addition to the expression, but the expression itself must not shift, restyle or become a different representation when editing begins or ends. Verify this by real typing.
- [ ] **(new)** Double-clicking a unit to edit it zooms too much; it should change in place, at the size it already is, without a large zoom jump
- [ ] **(new)** The unit list appears in odd places on the screen — it belongs under the thing being typed
- [ ] **(consolidated)** Variable and unit completion is available only while editing an equation or inline equation, never during ordinary text entry. Unit matching is case-insensitive and ranks an exact unit match first (`m` before `mm`); accepting a listed unit always requires Tab, which replaces typed casing with the canonical unit spelling. If no listed unit matches, Tab does not complete it. The completion list is navigable with arrow keys or mouse and may also offer matching already-defined variables.
- [ ] Add right-click options for output formatting: choose decimal places, scientific notation, or significant figures per result (121)
- [ ] Audit every Greek letter glyph — phi in particular is rendering as two visually different glyphs depending on where it's used; needs to be one consistent glyph everywhere (96)

### 3. Calculation blocks vs. calculation lines

- [ ] A calculation block's **Self-contained** toggle is available in the Properties panel and style toolbar, rather than buried in the calculation right-click menu. Its default is off; Preferences controls the app-wide default (11, 15, 71, 78).
- [ ] A single `"` trigger starts a calculation entry; ordinary typing must never activate a calculation or markup shortcut. The no-space and direct-unit rules are defined by the consolidated equation-entry task above.
- [ ] Inside a text box, typing `\` starts an inline equation. It displays the full formula and its live evaluated value together, preserving both the expression the user wrote and its result; `/` remains the division/fraction operation within an equation rather than replacing this inline-equation trigger.
- [ ] Ctrl+Shift+M converts an existing calculation line or selection into a block in place, without creating a duplicate copy (134)

### 4. Equation editor

- [ ] **(new)** Use the locally supplied `SMath Studio/` installation, especially its desktop UI, examples and snippets, as the behavior reference when resolving equation-editor interactions. Reproduce its navigation and structured-expression behavior by observing the application; do not copy proprietary implementation code.
- [ ] Clicking into an existing fraction to edit its numerator/denominator doesn't currently work — this likely needs the equation model rebuilt structurally as a tree of lines/blocks so the in-place editor is authoritative rather than a rendering layer on top of separate source text (103, 132) — re-checked: clicking either half of a fraction, a fraction inside a fraction, or a line of a block puts the caret at that place in the source, zoomed or turned, and a double-click there takes the word it was aimed at
- [ ] **(new)** Preserve equation subscript structure when defining a subscripted variable. `trib_width` must render with `width` as a subscript, and adding `:=` must not flatten it into literal inline text such as `trib_width`.
- [ ] **(reported again)** Equation editing must retain its caret and allow Left/Right arrow navigation after focus leaves the equation and returns. Clicking out after defining a variable with `:` and returning must still allow the user to place the caret and delete or amend the variable name on the left of the definition; no expression region may become uneditable.
- [ ] **(new)** Make equation editing structural rather than flat-text-like: arrow keys and pointer placement navigate the visible expression tree; selecting an expression and typing an opening bracket wraps the entire selected expression; selecting an expression and typing `/` turns that selection into the numerator of a fraction/division structure. Preserve the selected expression and its formatting when applying either transformation.

### 6. Spreadsheet (Excel-like) behavior

- [ ] Pasting cells copied from Excel should create a real table object here, and should carry over relative formulas where translation is possible (fall back to values only where it isn't) (12, 23, 109)
- [ ] Cursor icon should change to a resize cursor when hovering a column/row border — currently doesn't, making it hard to tell it's draggable (108)
- [ ] Fix visual overlap between adjacent table cells so content doesn't run into the next cell (11)
- [ ] Clarify how a computed/output cell is displayed vs. a plain input cell (e.g. a cell defined as `q_floor`) — currently ambiguous which is which (11, 61)
- [ ] **(new)** Bug: in the insert-table dialog, the "header row" checkbox shows as ticked, but clicking it off and back on leaves it unticked (state gets lost on the second toggle) — fix the checkbox's state handling

### 7. Markup tools — placement & interaction model (Bluebeam parity)

- [ ] **(new)** Where a placed thing sits relative to the pointer: a call-out's text box goes by its **left middle** (the top-left is the corner that must be got right); an image, a snapshot, a tool-set item, a group or a cloud item goes by its **bottom left**. Property-mode tools are the exception and keep what they have
- [ ] "Properties mode" (place a new copy using the last-used style/properties rather than an exact one-to-one duplicate) should only be selectable for a single markup object — for calc blocks, images, graphs, and groups it should be greyed out or simply not offered, since it doesn't make sense for those (41)
- [ ] **(new)** Selecting as it stands — click, and click-drag for a rectangular marquee, with no key held — is right and stays as it is. What Shift adds: **Shift and click point after point draws a polygon to select inside**, closed by clicking the first point again or by Enter
- [ ] **(supersedes prior removal)** Provide an optional canvas insertion point for calculation placement. When enabled, clicking empty canvas sets the insertion point and arrow keys move it up/down; new calculation lines use that point. The setting must be independently toggleable so ordinary selection/marquee behavior remains available when it is off.
- [ ] Escape must always fully clear selection and exit whatever edit/tool sub-state you're in, in one press, regardless of how deep the current mode is nested (81, 92)
- [ ] Fix: it's possible to get permanently stuck inside a tool (e.g. right after placing a callout's arrow) with no way out — Escape doesn't help and no other tool can be switched to (82, 110)
- [ ] **(reported again)** Audit and repair cursor state throughout the app. The cursor must revert as a gesture ends and must never remain as a four-way move cursor after rectangle resizing or another completed interaction. Use a context-appropriate affordance for each action: resize arrows for resize handles, row/column resize cursors for table borders, a control-point-plus cursor when Shift can add a point, a control-point-minus cursor when Shift can delete one, and a curve/arc cursor when Ctrl can round a point or convert a line segment to an arc. Exercise these paths with real pointer movement, modifiers and cancellation so the cursor cannot become stuck (76, 110, current report).

### 8. Markup tools — specific shapes

- [ ] Cloud tool, shortcut **C** (10)
- [ ] Arrow tool (10)
- [ ] Cloud vs. Cloud+ and cloud-callout: a click-and-drag produces the simple rectangular cloud; clicking each point individually produces the custom-shaped cloud ("Cloud+"). The same click-drag-vs-click-each-point distinction governs whether a cloud callout comes out rectangular or custom-shaped. After the cloud shape is finished, right-click or Enter proceeds to placing its text box (143)
- [ ] Shift-to-constrain (snap the current segment to 0°/45°/90°) must work consistently across *every* drawing tool — currently the pen and highlighter tools ignore it even though rectangle/line do respect it (29, 40, 43)
- [ ] Structural break symbol: available in the right-click context menu on any line segment, rectangle edge, or polygon edge — inserts the standard structural-drawing "break" symbol at that point (115)
- [ ] Rounded-corner and convert-to-arc are available **in the right-click context menu**, offered on any shape with corners/segments (rectangle, polygon, polyline, cloud, etc.) — currently not visible/accessible anywhere, needs to be built and exposed. Rounded corners get a radius handle; arc segments get **dual handles** — one to adjust arc length, one to adjust arc angle — matching Bluebeam's behaviour (115, 125, 126, reference photo in msg 126, still reported missing in 149)
- [ ] Rectangles specifically should support right-click add/remove control point; the moment a rectangle's corner is moved such that it's no longer axis-aligned/rectangular, it should automatically convert into a general polygon so it keeps behaving correctly (115, **new** detail from screenshots: "rectangle should have control point add/remove too, which becomes a polygon automatically if not rectangular")
- [ ] **(new)** While editing a rounded/arc segment on a rectangle, render the current curve continuously in the canvas preview. Moving an arc handle must not make the curve disappear from the rectangle until the gesture finishes; the final render and in-progress render must show the same geometry. Reference: rectangle arc-handle image attached in this chat on 2026-09-04.
- [ ] **(new)** Bug: snapping to the *centre/midpoint of a polygon edge* does not work — should snap the same way rectangle/line midpoints do

### 9. Callouts, text boxes, dimensions

- [ ] **(new)** Text selection inside a text box should allow styling only the selected run — bold, italic, underline, font size and similar formatting should apply to the chosen text, not to the entire text box as one object. The current whole-box style behaviour is wrong; the selected run should be styled independently and the rest of the text left alone
- [ ] **(new)** Text boxes, rectangles, callouts and similar placeable objects should support rotation cleanly; while editing, they should revert to their normal/unrotated orientation, and if the default rotation is effectively “zero/unrotated” they should snap back to that default rather than staying at a rotated angle
- [ ] **(new)** Callout boxes and other text/shape items should rotate back to normal during editing and snap back to the default unrotated state when the base/default angle is zero/positive-unrotated, instead of remaining at a stale rotated angle
- [ ] Custom dimension tool (Alt+M): click first point, click second point, then place the dimension text directly with an in-place text cursor — no popup dialog. Text is blank by default until typed. It sits in-line with the dimension line by default, but Shift+click the number to drag it off the line, which then draws its own small leader connecting it back (10, 37, reference photo msg 116)
- [ ] **(new)** Full leader/hinge rewrite needed: the hinge point currently doesn't exist yet during placement (before the box is finalized), which breaks the interaction — it needs to be built from scratch so the in-progress placement behaves exactly like the finished, after-placement leader from the very first click, not as a separate/different code path
- [ ] **(new)** The leader line must never be allowed to visually cross through/over the text box itself — constrain valid hinge positions so that geometry is impossible
- [ ] **(new)** Remove the small floating description/label that appears on markups and fades out after a moment — not wanted on any markup type
- [ ] **(new, reported again)** Orange square placement markers still show up on many markups and only go away after clicking something else. They are not wanted on any markup, at any time — find every path that draws one and take it out
- [ ] **(new)** Bug: the cloud part of a cloud call-out vanishes partway through placing it and comes back at the end — it has to be there, unbroken, from the first click — **done**: the cloud lived on the call-out rather than on a leader, and the placement preview draws the leaders, so it was not drawn until the click landed. It is a leader now
- [ ] **(new)** A cloud call-out is a call-out: the same hinge, the same clear-of-the-box rule, the same automatic re-computation, and the same several leaders — the only difference is that its leaders are drawn as clouds rather than as arrows. One set of behaviour, not two — **done**: a leader is either an arrow (head at the target) or a cloud (region drawn round, no head), and one call-out can carry both
- [ ] **(new)** "Add leader" belongs in the right-click menu itself, not inside a sub-menu — and choosing it asks which kind: an arrow leader or a cloud leader — **done**
- [ ] **(new)** A call-out or cloud call-out whose last leader is taken away becomes a plain text box; a text box that is given a leader becomes a call-out. The three are one object in different states, and moving between them is what adding or removing the last leader means — **done**

### 10. Snapshot tool

- [ ] **(new)** Pressing `G` while reviewing a PDF must reliably create a Snapshot from the selected PDF region, including in markup-only PDF mode. That snapshot must be saved into the current `.cfx` document and remain visible after save, reopen, export and ordinary document editing.
- [ ] Recolor tool for specific items (a snapshot, or a whole page) that remaps PDF line-work from one color to another, e.g. for redlines (29)
- [ ] **(new)** Restrict ordinary stroke-colour changes to markup types that actually draw editable linework. Do not offer or apply a stroke-colour change to raster photos/images, where it has no meaning; retain PDF/vector recolouring for imported vector page content.
- [ ] **(new)** Add Bluebeam-style photo/image colour operations: recolour an image to a selected colour, convert it to black-and-white, and make a selected source colour transparent. These are image-content operations, distinct from a markup's stroke/fill styling.
- [ ] **(new)** Pasted images must not acquire a red outline when their stroke is explicitly set to no colour or when the image tool default has no stroke. The visible frame must match the persisted/default image style.

### 11. Snapping, grid, alignment

- [ ] **(new)** Bug: turning "snap to grid" off doesn't actually stop points from snapping to the grid — the toggle isn't being respected
- [ ] Fix: snapping doesn't work on the very *first* point placed while drawing a new line — it only starts working from the second point onward; it should be active from the first click (113, **new**: "when drawing something the first point does not show the snap indicator, only the point after shows it — show it for all points whenever snap is on")
- [ ] **(new)** The live placement preview (the ghost shape shown before you click to commit) must use the exact same snapping logic as the final placed geometry — right now they can disagree
- [ ] **(new)** Snap alignment guides are transient feedback only. Every temporary vertical/horizontal snapping line must disappear immediately when the pointer leaves its snap target, the gesture ends, the active tool changes, or Escape cancels the operation; no guide may remain stuck on the canvas.
- [ ] New markups/drawing tools should snap to both the grid and existing items while being drawn, generally (72)

### 12. Move, duplicate, group

- [ ] Ctrl+drag duplicates the item being dragged; Shift+drag constrains movement to 0/45/90°; Ctrl+Shift+drag duplicates *and* constrains to 0/45/90°; releasing Ctrl mid-drag re-enables snapping (29)
- [ ] **(new)** Groups must be scalable as a single object, resizing all contained markups proportionally from the group bounding box.
- [ ] **(new)** Image and group resizing is aspect-ratio locked by default. Holding Shift temporarily releases that lock for non-proportional resizing; the current inverse modifier behavior is wrong.

### 13. Copy / paste

- [ ] Pasting a page should also show a clear insertion-location indicator, same as pasting other content (147)

### 14. Toolsets / "My Tools"

- [ ] **(new)** In My Tools, a tool in **Property mode** shows a default icon drawn in that style, and carries a "properties" tag on the entry so it is obvious which mode it is in
- [ ] Each toolset entry should show a real preview/thumbnail of the actual item, not a text description; when the entry is in properties mode, show a generic example of that markup type styled with its saved color/other properties (54)
- [ ] Relocate the toolset "save" action to a right-click option on each item rather than a dedicated button, and make the "properties mode" toggle discoverable — currently can't be found in the UI at all (105)
- [ ] "Set as default" button in the Properties panel: applies the current object's properties as the default for that tool going forward (36)
- [ ] **(new)** Add the same **Set as default** command to the style toolbar, so the selected markup's current compatible style can become the default for future instances without opening the Properties panel.

### 15. Panels & layout

- [ ] Bluebeam-style unified dock: Pages, Bookmarks, Variables, Toolsets/My Tools, Properties, and any other relevant panel should each be a togglable icon that can be dragged individually to dock on either the left or right side (45, 62)
- [ ] The Properties panel should be resizable down to zero width (effectively hidden) and dragged back open again later (23)
- [ ] **(expanded)** Make the style toolbar and Properties panel selection-aware. Show only controls compatible with the selected markup type and hide or disable every irrelevant control: rectangles/ellipses expose shape geometry, stroke, fill and hatch but no text controls; lines, arrows, polylines and measurements expose their relevant stroke/endpoint controls but no hatch; text and callouts expose text formatting and only their applicable fill/stroke/leader controls; photos, snapshots and groups expose only their supported image/group operations. Surface important type-specific controls there too, including **Self-contained** for calculation blocks and table-specific editing controls for tables. Apply the same filtering when no item is selected, using the active tool's capabilities instead.
- [ ] **(new)** Line-style and hatch selectors in Properties must show a compact visual preview of the actual pattern, weight and colour alongside each option. Users should be able to identify a dashed/dotted line or hatch pattern without relying on a text-only name.
- [ ] **(new)** Only one panel should be open at a time in each side location: left-side panels and right-side panels should behave like Bluebeam, where a single panel is active in that side and you can move items into the panel toolbar, while the left and right sides can each be open independently but not multiple panels stacked in the same side at once
- [ ] Fix: scrolling the mouse wheel while the cursor happens to be over a dropdown inside the Properties panel changes the dropdown's selected value instead of scrolling the panel — this must never happen; scroll should always scroll the panel (80, 92)

### 17. Dark mode, icons & canvas/viewport

- [ ] **(reported again)** Zoom must remain exactly anchored to the page coordinate under the cursor, not merely approximately centered there. Wheel, toolbar and shortcut zoom operations must leave the pointer's target at the same screen position, without visible drift (139, 44, current report).
- [ ] **(new)** Add a wheel-behaviour preference for canvas navigation. In the standard mode, an unmodified wheel scrolls the document and `Ctrl`+wheel zooms; offer direct-wheel zoom as an alternative mode where needed. Do not let both unmodified wheel and `Ctrl`+wheel always zoom, because normal scrolling must remain available.
- [ ] **(new)** Bug: when the page/view is rotated, the scrollbar itself rotates along with it — the scrollbar should stay in its normal fixed orientation regardless of view rotation

### 18. Keyboard shortcuts

- [ ] All shortcuts must be disabled while actively in text-edit or equation-edit mode, **except** Ctrl+B/I/U which remain bold/italic/underline for text formatting (20, 131)
- [ ] Entry into text/equation mode must require the explicit `"` trigger (see the corrected §3 entry-trigger items and contradiction #2 above) — plain letter keys (q, c, a, etc.) must never be misinterpreted as starting a markup tool while you're trying to type (34, 83, 131, 138)
- [ ] Ctrl+B should mean "bookmark" everywhere **except** while inside text selection/edit mode, where it must remain Bold and not trigger bookmarking (104, 66, 66/92 bookmark-while-editing bug)
- [ ] The repeat-placement-N-times-along-X/Y behaviour (see §12) should also be assignable/visible through the shortcut manager, not just accessible via modifier keys (23)

### 19. Pages & document structure

- [ ] **(new)** Add a right-click page-panel command to include or exclude each page from printing/export. Pages excluded from print must remain in the document but appear visibly greyed out in the page panel, so the print set can be understood at a glance.
- [ ] **(new)** Support editable page labels in the page panel. A user can assign a custom label, and Reset restores the label sourced from the imported PDF page where one exists; blank/new pages use the normal generated page label.
- [ ] **(new)** Bug: several pages cannot be deleted at once. Picking more than one page in the pages panel has to work properly and everything that acts on a page has to act on the whole picked set — delete, move (reorder by dragging), copy and duplicate
- [ ] Dragging a PDF file directly onto the page panel should show an insertion cursor/indicator and insert it at that exact point in the page order (114)
- [ ] Insert-PDF must bring in the actual PDF content (vector text/lines), not a blank page and not a 150dpi raster snapshot of it — figure out what's required to preserve full fidelity, and ask if a specific library/dependency choice needs sign-off (25, 120)
- [ ] **(new)** Insert-PDF must not ask for a DPI at all. There is no resolution to choose: everything in the file comes through as the PDF has it, vector work included. Drop the question from the dialog

### 20. Page setup (headers/footers/scale/grid)

- [ ] Current page scale should be displayed next to the page number in the page viewer/page panel (25, 31)

### 21. Measuring tools

- [ ] **(new)** Count is a continuous placement tool: after Count is selected, every click must place the next marker for the active count subject, numbered `1`, `2`, `3`, and so on. It must remain armed until Escape, selection of another tool, or an explicit cancellation; users must not have to reselect Count after each marker.
- [ ] **(new)** Make polygon and ellipse cut-outs discoverable in the measurement workflow. A cut-out is a hole owned by an existing area/volume measurement, not a standalone markup: the UI must clearly indicate that it is drawn inside that measurement, finished with Enter, and subtracts from its reported area.

### 22. Bookmarks & table of contents

- [ ] Bookmarks themselves should be renameable/editable after creation (60)
- [ ] Bookmarks and any links must remain fully clickable/working as hyperlinks in the exported PDF (32)
- [ ] Fix: the bookmark shortcut fires accidentally while you're actively typing/holding text selected — it must not trigger during text edit (66, 92)

### 23. Import / interoperability

- [ ] Import Bluebeam `.btx` toolset files — including tool sets, hatch patterns, line-type definitions, groups, and whatever other markup types are embedded in them. You've uploaded sample `.btx` files to the GitHub repo specifically for this to be tested against — verify import against those real files, not just synthetic ones (80, 92)
- [ ] **(reported again)** Repair BTX sketch-tool import fidelity. The real `btx/Structures - Sketch Tools.btx` sample currently imports incorrectly, including structural section-cut/circle symbols. Preserve the Bluebeam toolset's geometry, styles, groups, hatches and line types so imported symbols match the supplied structural-drafting reference; hold this with regression tests against the real BTX files (137, 139, 149, current report).
- [ ] Format Painter tool, with an icon matching Bluebeam's paint-roller icon (146)
- [ ] **(new)** Format Painter transfers only compatible visual style: fill colour, line/stroke colour and line thickness. It must never copy geometry, markup type or tool-specific behaviour. In particular, painting from a cloud onto another markup must not turn that markup into a cloud, and painting onto a cloud must leave it cloud-shaped; the same rule applies in either direction.
- [ ] **(new)** Format Painter must not copy callout leader count, leader positions, cloud geometry or any other callout structure. Between callouts it transfers only compatible appearance: line colour, arrowhead styling, fill and text properties.
- [ ] **(new)** Make Format Painter's armed state unambiguous: while active it uses a paint-brush cursor consistent with Bluebeam, exposes a clear active state, and Escape cancels it immediately without applying style.

### 25. Settings, persistence & spellcheck

- [ ] **(reported again)** Repair spellcheck dictionary coverage and correction workflow. Valid ordinary words such as `requests` must not be falsely underlined red; a misspelled word should be marked inline and its right-click context menu must offer appropriate replacement suggestions and a command to change the spelling.

### 26. Menus & discoverability

- [ ] Every capability (page operations, line operations, etc.) must be reachable from the main menu bar somewhere, not only via right-click or a shortcut (128)
- [ ] Preferences/settings should live under a "Settings" top-level menu (128)
- [ ] Help menu should include a searchable command/tool search (128)
- [ ] **(new)** Right-click menu on a calculation is too long and says too much. Take out the whole calculation group — the exact entries, in `MainWindow.build_context_menu`, are **"Figures on this line"** (the submenu), **"Edit…"**, **"Show this result in…"**, **"Keep as one block"**, **"Self-contained block"**, and the split/merge entries. Whatever of that is worth keeping goes on the **main menu bar**, not in the right-click menu
- [ ] **(new)** Every button and menu label in the app should be one or two words, the way Bluebeam's are — not a sentence explaining what the thing does. The explanation goes in the tooltip. In particular "draw again" and friends are called **Property mode**, everywhere

### 27. Reliability / process

- [ ] Investigate and explain why background tasks were observed stopped unexpectedly, and prevent recurrence (129, 138) — **what happened**: a long test run or fuzz run is started as a background command with a timeout on it, and when the session's turn ends before that timeout the command is killed with it. Nothing crashed; the run was cut off. **What is done about it now**: long runs are given a timeout that matches how long they actually take, their output goes to a file that survives the run, and the file is read back and reported rather than assumed
- [ ] Never let hitting the token/usage limit silently end the session's work — pause, and resume automatically once the limit resets, without needing a fresh prompt from you (130, 138) — **not something this end can promise.** A session that runs out of context is summarised and continued, and that is automatic; a session that runs out of *usage* stops until the limit resets and needs a prompt to pick up again. What is under control here is that nothing is left half-finished and unrecorded: work is committed and pushed as it is done, and this list says what is built and what is not, so whatever picks the work up next — a fresh session, or this one after a reset — starts from the list rather than from memory
- [ ] **(new)** Validate interactive changes through the real CalcForge UI, not only unit-level code inspection. Agents must drive the canvas with pointer moves, clicks, drags, keyboard arrows and configured shortcuts, including Escape/cancel paths, and look for stuck tools, lost focus, incorrect cursor states, blocked input, broken selections and other interaction regressions. Keep repeatable Qt event-driven tests for each defect found.
- [ ] **(new)** Write a context document so a session does not have to re-read every past chat: what the app is, who it is for, how the code is laid out, how to test it, what is done and what is not, and how this list is kept. **Done** — `docs/HANDOVER.md`, which is the first thing any agent picking this up should read. This list stays the record of what is asked for and built; the handover is the map to everything else
- [ ] **(new)** Maintain a separate Markdown review register of every task that has not yet been implemented and validated. Keep it synchronized as work is addressed, without changing task completion checkboxes in this file or completion status in `docs/tasklist.xlsx`; only the user marks tasks complete.

### 28. Miscellaneous fixes reported (screenshots referenced)

- [ ] **(found here, not reported by you)** Two layout tests — `test_everything_that_can_be_arranged_comes_back` and `test_a_rolled_up_panel_comes_back_rolled_up` — fail intermittently, but only in a **full** suite run. Both pass on their own, and both pass when every file that runs before them is run with them, so nothing earlier is leaving a mess behind: it is a race that shows up only when the machine is busy. Both save an arrangement and then build a second window to check it came back, so the suspect is a 1.5-second layout-save timer on a window still alive, firing between the save and the second window reading it. Worth chasing rather than re-running until it passes — the same race could lose a real arrangement on a slow machine
- [ ] General inconsistent/odd spacing in rendered equations, per screenshot (97)
- [ ] The unit-selection dropdown list appears in the wrong screen position relative to what's being edited (98)
- [ ] Arrow markups show a small control-point handle even when the arrow isn't selected — handles should only be visible while selected (101)
- [ ] Rotation control point gets clipped at the shape's edge and visually glitches/smears while the item is being moved (102)
- [ ] There's an unidentified "blue tool" in the UI that does nothing and can't even be selected/clicked — find and remove it (63)
- [ ] Audit every Properties-panel option for redundancy or unclear labeling — e.g. what does "multiply highlighter" in the callout properties actually do? Several options may not be needed at all (61)
- [ ] Highlighter tool leaves odd gaps/holes depending on the stroke path used to draw it (58, 59)
- [ ] Table column/row resize doesn't show a resize cursor (108, duplicate of §6 item)
- [ ] An object can get stuck showing a "move" cursor even when nothing is selected, and Escape doesn't clear it (110)

### 29. New requests awaiting review

- [ ] Keep only **Merge** for calculation blocks in the calculation context menu; remove the unclear duplicate **Make one block** command. Merge must work correctly.
- [ ] Distinguish calculation lines and blocks in the Properties panel. Only blocks expose **Self-contained**; line results are shown inline/on-hover without block-only controls.
- [ ] Show a concise function-help tooltip when hovering a function in the Functions panel or after entering it in a calculation line/block. Include the accepted argument count, argument names and purpose.
- [ ] Add rebindable shortcuts for left/centre/right alignment and font-size increase/decrease. They apply to selected text, a selected table cell, a whole calculation line, or a selected line within a calculation block, according to the active editor.
- [ ] Every command shortcut, including equation/text-entry triggers, must be visible and rebindable in the shortcut manager.
- [ ] New pages start uncalibrated. The first scale-dependent rectangle, ellipse or measurement prompts for page scale instead of assuming a scale.
- [ ] After the first click of a rectangle or ellipse, show an in-canvas numeric size entry for width/height or diameter. Typed values update the preview at page scale; the second click places the markup and dismisses the entry.
- [ ] A cloud callout's cloud and text box must be independently movable. Moving the box moves only the box; moving the cloud moves only the cloud; the leader geometry updates without moving the whole callout.
- [ ] Arced segments on Arc items expose a control point comparable to other arced line segments.
- [ ] Pen and highlighter strokes snap only at their start/end points. Intermediate sampled points must not snap to grid or items, so freehand strokes stay smooth.
- [ ] Put **Add arrow leader**, **Add cloud leader**, and **Remove leader** directly in the main callout context menu. Adding a cloud leader adds only that cloud leader and lets the user choose its attachment position; remove the broad **Remove all leaders** command.
- [ ] Fix modifier-drag behavior: Ctrl+drag duplicates; adding Shift before or after movement constrains the duplicate to 0/45/90 degrees; Shift-first then Ctrl switches from snap-constrained movement to duplication without leaving snapping in an inconsistent state.
- [ ] Recompute each callout leader hinge completely when its arrow tip, text box or cloud moves. Do not retain a prior manually adjusted hinge length after any of those changes.
- [ ] Remove holes/gaps where overlapping highlighter strokes should form one continuous highlighted region.
- [ ] Snapshot must capture PDF vector linework and markups without carrying through the page background; it must not include unrelated calculation/table/text content unless those item types are explicitly selected for capture.
- [ ] Make the bottom canvas Snap control a dropdown that identifies and toggles the available targets, such as grid, PDF content and markups, rather than an ambiguous single button.
- [ ] Centre the page number and page label within the page-view footer/navigation area.
- [ ] In the Pages panel, Ctrl+C/Ctrl+V copies and inserts pages with a visible insertion indicator. Support Ctrl and Shift multi-selection; Delete removes selected pages only after confirmation.
- [ ] Remove the Typewriter markup tool and all related UI/shortcuts.
- [ ] Add a bottom-canvas scroll-mode control for continuous scrolling versus page-by-page viewing.
- [ ] Clicking a page-grid control must not move or reposition the page view.
- [ ] While editing text, Ctrl+B/Ctrl+I/Ctrl+U format the selected text. Outside text/equation editing they retain their global commands; formatting keys must never insert a page or trigger unrelated commands.
- [ ] Show Pages-panel thumbnails centred within a grid layout.
- [ ] Add a rebindable **Calibrate scale** shortcut. Calibration starts without an assumed `5 m` value, then opens a dedicated length-entry prompt after two points are selected; accept `10mm` and `10 mm`, and show a clear warning for invalid or incompatible units.
- [ ] Add recoverable document flattening: choose which content classes to flatten (markups, calculations, tables and other supported items), retain recovery data by default, support individual-item flattening, and offer a Preferences setting to disable recoverability when deliberately producing an irreversible file.

## Task List Rules

- The user owns completion status in `docs/tasklist.xlsx`. Agents never change
	completion state; the user controls the workbook and may explicitly request
	a Markdown synchronization.
- Agents add and clarify new requests in this Markdown register without
	changing completed/open status.
- Combine overlapping tasks into one observable requirement with the current intended behavior.
- Validate interactive behavior through real Qt mouse, keyboard, focus, shortcut and Escape/cancel paths.
