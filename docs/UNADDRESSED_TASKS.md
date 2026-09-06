# CalcForge tasks still requiring work

Audited: 2026-09-06 against `claude/engineering-calc-markup-app-2twiqs`.

The 21 entries below are what the audit could not show working. Each says
what is missing or blocking it. Several are tasks whose base behaviour is
finished and whose recent amendment is not; those name the part that is done so
the remaining work is clear.

This is not the user-owned completion record. It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`.

## 1. Core concept

- **(new)** Support multiple open documents at once: PDF review documents and `.cfx` CalcForge documents appear in separate tabs, can be viewed side-by-side in a split view, and can be moved into independent application windows. Each document keeps its own pages, state and active tool without leaking into another tab/window.
  - **Missing:** Not started: the app builds one MainWindow (calcforge/app.py:57) and has no document tabs, split view or second-window path.

## 2. Calculation engine — variables & units

- **(consolidated)** Variable and unit completion is available only while editing an equation or inline equation, never during ordinary text entry. Unit matching is case-insensitive and ranks an exact unit match first (`m` before `mm`); accepting a listed unit always requires Tab, which replaces typed casing with the canonical unit spelling. If no listed unit matches, Tab does not complete it. The completion list is navigable with arrow keys or mouse and may also offer matching already-defined variables.
  - **Missing:** Two clauses fail, verified in the running app. Exact match is not ranked first: completion_words('m') returns ['mm','m','mile',...]. And Tab with no matching unit inserts a literal tab into the equation: 'L:=300zzq' becomes 'L:=300zzq\t'. Suppression in ordinary prose and Tab-to-accept do work.

## 4. Equation editor

- **(new)** Use the locally supplied `SMath Studio/` installation, especially its desktop UI, examples and snippets, as the behavior reference when resolving equation-editor interactions. Reproduce its navigation and structured-expression behavior by observing the application; do not copy proprietary implementation code.
  - **Missing:** Standing reference instruction, not a code change: the SMath Studio/ installation is in the repo but no audit of its behaviour has been recorded. Stays a requirement per HANDOVER rule 5.

- **(new, extended)** Make equation editing structural rather than flat-text-like: arrow keys and pointer placement navigate the visible expression tree; selecting an expression and typing an opening bracket wraps the entire selected expression; selecting an expression and typing `/` turns that selection into the numerator of a fraction/division structure. Preserve the selected expression and its formatting when applying either transformation. The structure must also survive a syntax error: a calculation that does not parse keeps its structured typeset layout instead of collapsing back to inline text, operator precedence (BEDMAS) stays visible, `5/` renders as 5 over an empty denominator placeholder, and incomplete value, unit and power slots render as small SMath-style outline input boxes.
  - **Missing:** Not implemented, verified in the running app. With '1+2' selected in 'a:=1+2', typing '(' replaces the selection instead of wrapping it — the text becomes 'a:=('; typing '/' likewise gives 'a:=/' rather than making the selection a numerator. No expression-tree/wrap code exists. The extended error-tolerant-rendering clause is also unimplemented.

## 6. Spreadsheet (Excel-like) behavior

- Cursor icon should change to a resize cursor when hovering a column/row border — currently doesn't, making it hard to tell it's draggable (108)
  - **Missing:** Not implemented: neither calcforge/items/tableitem.py nor the view sets any cursor over a column or row border — tableitem.py contains no setCursor call at all. The SizeHor/SizeVerCursor in items/base.py belong to markup resize handles, not table borders.

## 7. Markup tools — placement & interaction model (Bluebeam parity)

- **(supersedes prior removal, amended)** Provide an optional canvas insertion point for calculation placement. When enabled, clicking empty canvas sets the insertion point and arrow keys move it up/down; new calculation lines use that point. The insertion point renders as a tiny crosshair, not a large marker. The setting must be independently toggleable so ordinary selection/marquee behavior remains available when it is off. Left, Right, Up and Down must never scroll the page view or change pages during ordinary navigation; the single exception is that the view may auto-scroll when the insertion point, or an item being moved with the arrows, is about to leave the visible area.
  - **Missing:** Base feature is there and tested (off by default, places and moves the next calculation, Escape clears it, Preferences exposes it) but the amendment is not: view.py:4699 still ends the arrow-key path with 'Nothing selected: the arrows scroll the document' and calls scroll_by, which the amended task forbids outside the follow-the-caret-off-screen case. The marker drawn by _draw_insertion_point (view.py:4388) is a 16px I-beam caret with end ticks, not the crosshair the task asks for.

## 10. Snapshot tool

- **(new, amended)** Pasted or placed images and snapshots must not acquire a red outline. The image tool's own default stroke must be settable and must default to none, and a snapshot's default stroke must be none; in both cases the visible frame must match the persisted or default style rather than a hard-coded red. A snapshot's stroke colour and width must then be settable by the user and honoured when set, and the style toolbar and the Properties panel must agree with each other on image and snapshot border state.
  - **Missing:** Half done. A snapshot's default really is no stroke (items/snapshot.py:38, Style(stroke='', width=0.0)) and a set stroke is honoured (snapshot.py:91); a pasted image keeps its borderless default rather than picking up the drawn-markup red (items/media.py:84-91). Still missing: the image tool has no settable default stroke of its own anywhere in the code, and nothing verifies that the style toolbar and the Properties panel agree on image and snapshot border state.

## 15. Panels & layout

- **(expanded)** Make the style toolbar and Properties panel selection-aware. Show only controls compatible with the selected markup type and hide or disable every irrelevant control: rectangles/ellipses expose shape geometry, stroke, fill and hatch but no text controls; lines, arrows, polylines and measurements expose their relevant stroke/endpoint controls but no hatch; text and callouts expose text formatting and only their applicable fill/stroke/leader controls; photos, snapshots and groups expose only their supported image/group operations. Surface important type-specific controls there too, including **Self-contained** for calculation blocks and table-specific editing controls for tables. Apply the same filtering when no item is selected, using the active tool's capabilities instead. A selected equation or calculation exposes decimal-places, significant-figures and scientific-notation controls in both the style toolbar and the Properties panel, not only through the right-click menu; markups expose their full colour, hatch and line controls; text exposes text controls; and callouts expose both.
  - **Missing:** Base filtering is done and tested (test_a_raster_image_has_no_line_or_fill_style_controls, test_drawing_again_is_greyed_out_for_a_calculation, the Self-contained panel tests). The amended clause is half done: the Properties panel does expose Significant digits and a Number format combo of auto/fixed/scientific/engineering for a calculation (ui/panels.py:1910-1926), but the Style toolbar carries only Line, Fill, Width, Dash, Text, Set default, Self-contained and Stamp (mainwindow.py:628-690) — no result-formatting control at all.

## 17. Dark mode, icons & canvas/viewport

- **(new)** Add a wheel-behaviour preference for canvas navigation. In the standard mode, an unmodified wheel scrolls the document and `Ctrl`+wheel zooms; offer direct-wheel zoom as an alternative mode where needed. Whichever mode is configured, holding `Ctrl` performs the opposite of it: in wheel-scrolls mode `Ctrl`+wheel zooms, and in wheel-zooms mode `Ctrl`+wheel scrolls. Do not let both unmodified wheel and `Ctrl`+wheel always zoom, because normal scrolling must remain available.
  - **Missing:** The preference exists and both modes work (test_the_wheel_zooms_the_document, test_the_wheel_can_be_set_to_scroll_instead, test_ctrl_and_the_wheel_zoom), but the amended clause is unverified: nothing establishes that Ctrl inverts the configured mode in BOTH directions. test_ctrl_and_the_wheel_zoom only covers Ctrl+wheel zooming; there is no test of Ctrl+wheel scrolling while the wheel-zooms mode is set.

## 21. Measuring tools

- **(new)** Make polygon and ellipse cut-outs discoverable in the measurement workflow. A cut-out is a hole owned by an existing area/volume measurement, not a standalone markup: the UI must clearly indicate that it is drawn inside that measurement, finished with Enter, and subtracts from its reported area. Polygon and ellipse cut-outs apply to any closed shape — polygons, area measurements, rectangles, circles and ellipses — not only to polygonal areas.
  - **Missing:** Base behaviour is done and tested (test_a_cut_out_takes_its_area_off_the_measurement, test_a_polygon_cut_out_belongs_to_the_area_it_is_drawn_in). The amended any-closed-shape clause is not: area_under (view.py:2810-2824) accepts only a MeasureItem whose kind is AREA or VOLUME, so a rectangle, polygon or ellipse cannot host a cut-out. Also note unreachable code at view.py:2825-2826, after that function's return None.

## 27. Reliability / process

- Never let hitting the token/usage limit silently end the session's work — pause, and resume automatically once the limit resets, without needing a fresh prompt from you (130, 138) — **not something this end can promise.** A session that runs out of context is summarised and continued, and that is automatic; a session that runs out of *usage* stops until the limit resets and needs a prompt to pick up again. What is under control here is that nothing is left half-finished and unrecorded: work is committed and pushed as it is done, and this list says what is built and what is not, so whatever picks the work up next — a fresh session, or this one after a reset — starts from the list rather than from memory
  - **Missing:** Platform limitation, unchanged: the session environment cannot guarantee resuming itself after a usage limit. Stays a requirement with that note, per HANDOVER rule 5.

- **(new)** Validate interactive changes through the real CalcForge UI, not only unit-level code inspection. Agents must drive the canvas with pointer moves, clicks, drags, keyboard arrows and configured shortcuts, including Escape/cancel paths, and look for stuck tools, lost focus, incorrect cursor states, blocked input, broken selections and other interaction regressions. Keep repeatable Qt event-driven tests for each defect found.
  - **Missing:** Ongoing acceptance requirement rather than a finished feature: it governs how every future interactive change is validated, so it never closes.

## 28. Miscellaneous fixes reported (screenshots referenced)

- **(found here, not reported by you)** Two layout tests — `test_everything_that_can_be_arranged_comes_back` and `test_a_rolled_up_panel_comes_back_rolled_up` — fail intermittently, but only in a **full** suite run. Both pass on their own, and both pass when every file that runs before them is run with them, so nothing earlier is leaving a mess behind: it is a race that shows up only when the machine is busy. Both save an arrangement and then build a second window to check it came back, so the suspect is a 1.5-second layout-save timer on a window still alive, firing between the save and the second window reading it. Worth chasing rather than re-running until it passes — the same race could lose a real arrangement on a slow machine
  - **Missing:** The race is still structurally present: mainwindow.py:218-220 still runs a 1500 ms _layout_timer, and both tests still save an arrangement and immediately build a second window. They passed in all three full runs this session, which is not proof the race is gone — HANDOVER §3 says as much. Logged, not fixed.

- Audit every Properties-panel option for redundancy or unclear labeling — e.g. what does "multiply highlighter" in the callout properties actually do? Several options may not be needed at all (61)
  - **Missing:** No record of the audit having been carried out. The specific example does do something — blend 'multiply' is the highlighter's composition mode (items/base.py:133 and 496) — but nothing shows every Properties option was reviewed for redundancy or unclear labelling.

- Table column/row resize doesn't show a resize cursor (108, duplicate of §6 item)
  - **Missing:** Duplicate of the §6 entry and open for the same reason: no cursor is set over a table column or row border anywhere; calcforge/items/tableitem.py contains no setCursor call.

## 29. New requests awaiting review

- **(amended)** After the first click of a rectangle or ellipse, show the numeric size entry as a small tooltip anchored near the bottom-right corner of the in-progress shape, tracking that corner as the drag proceeds. It live-updates width and height (or diameter) throughout the drag and accepts typed values at any point before the second click commits. Typed values update the preview at page scale; the second click places the markup and dismisses the entry.
  - **Missing:** The base size entry exists and is tested (test_a_rectangle_reports_its_real_size_and_accepts_an_exact_one, test_an_ellipse_can_be_set_out_to_an_exact_size), but the amendment is not implemented. open_size_editor (view.py:2840-2878) anchors the panel once at draft.mapToScene(0,0)+(8,8) — the shape's TOP-LEFT — and never moves it again, so it does not track the bottom-right corner as the drag proceeds. The two fields are placeholders only: nothing writes the live width and height into them while dragging.

- **(amended)** Recompute each callout leader hinge completely when its arrow tip, text box or cloud moves. Do not retain a prior manually adjusted hinge length after any of those changes. In a multi-leader callout each leader's hinge is computed independently: moving the cloud or the text box must not force every leader to share a single hinge length.
  - **Missing:** The recompute-on-move behaviour is there and tested (the hinge tests), but the amended per-leader clause is unverified: no test covers a multi-leader call-out keeping independent hinge lengths when the cloud or the box moves.

- **(new)** Count tool defects: the marker number is visually cut off; Escape must cancel the entire count session immediately rather than lagging behind the keypress; and the ghost `1` marker left behind after cancellation must disappear on its own, without needing a further click.
  - **Missing:** One of the three fixed; two could not be reproduced on this build. FIXED — the clipped number: CountItem now sizes the number's box from the font (index_rect) instead of a box fixed at 16x10 points, and owns that space in boundingRect, so the number is whole at 7, 9, 11, 14 and 18pt and up to three digits. Evidence: test_a_count_marker_shows_its_whole_number_at_any_size. NOT REPRODUCED — Escape already puts the count tool down on the press, with no lag and no draft left behind, and no ghost 1 marker appears on either the hover-then-Escape or place-then-Escape path; test_escape_puts_the_count_tool_down_at_once covers it. Those two reports look to have been made against an older build. Leaving the task open until the user confirms against this one.

- **(new)** A snapshot offers no colour-change control at all. Either add the option wherever it is meaningful for a snapshot, or deliberately exclude snapshots from stroke-colour controls — and if excluded, make that exclusion consistent between the style toolbar and the Properties panel rather than present in one and absent in the other.
  - **Missing:** Confirmed: calcforge/ui/panels.py has no SnapshotItem branch at all, so a selected snapshot gets no colour control anywhere. The decision the task asks for — add it where meaningful, or exclude snapshots consistently in both the style toolbar and Properties — has not been made.

- **(new)** Undo must cover equation state transitions. Undo reverts a space-triggered equation-to-text conversion back to the live equation, and restores text removed by Backspace, down to an empty entry.
  - **Missing:** Half works, verified in the running app. Undo of the space-triggered conversion does return the live equation: after typing a calculation, pressing space and undoing, a MathItem is back on the page. Backspace is not covered: typing 'b:=300mm', deleting all eight characters and undoing restores the MathItem with source '' rather than the removed text.

- **(new)** Cloud-leader placement feedback: when a cloud leader is being added, no provisional straight leader is drawn before the cloud itself is drawn, and the cursor changes to a cloud-drawing cursor for the duration of the placement.
  - **Missing:** No cloud-drawing cursor exists: the view sets no cursor for the pending-cloud-leader state (no cloud cursor anywhere in ui/view.py), and nothing suppresses a provisional straight leader between arming the cloud leader at view.py:397 and the cloud being drawn.
