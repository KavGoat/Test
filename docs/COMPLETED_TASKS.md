# CalcForge completed-work evidence

Audited: 2026-09-06 against `claude/engineering-calc-markup-app-2twiqs`.

Every open line in `docs/tasklist.md` was gone through one at a time. The 145
below are the ones the current source implements and something actually
exercises — an event-driven test that drives the real Qt queue, or a check
against the running application. Each carries the evidence it rests on.

This is not the user-owned completion record and nothing here is marked
complete. No checkbox in `docs/tasklist.md` and no status in
`docs/tasklist.xlsx` was touched. Only the user marks a task complete.

A caveat worth keeping: a passing test proves the behaviour held when it ran,
not that the requirement is finished in every respect a person might mean. Where
a task has recently been amended, the amendment was audited separately from the
behaviour it extends.

## 1. Core concept

- **(new)** Support a markup-only PDF document mode for drawing-review work. Opening a PDF in this mode provides Bluebeam-style navigation, markup, measurement and Snapshot tools, but hides or disables calculation lines, calculation blocks, tables and other calculation-specific UI so the document behaves as a focused PDF editor.
  - **Evidence:** PDF review mode: mode=='pdf' persists through save/reopen; calculate/symbol menus, math+table tools and the Variables dock hidden, snapshot+measure kept; quote key refused with a status hint. Evidence: the four `-k review` tests in tests/test_app.py, incl. test_opening_a_pdf_creates_a_focused_review_document and test_pdf_review_mode_blocks_calculation_entry_but_keeps_snapshot_key.

## 2. Calculation engine — variables & units

- **(consolidated)** Fresh and existing single calculation lines use identical equation-entry behavior. `"` starts a calculation entry; units bind directly to their number, so `5kPa` is valid and renders as `5·kPa`; and typing any space converts the complete current calculation line to plain text. Calculation blocks do not permit spaces. The status bar should explain the conversion, and the behavior must remain consistent when a line is left and re-entered.
  - **Evidence:** Quote is the only entry key; a space converts a fresh or an existing single line to text at the caret and blocks refuse it, both with a statusMessage explaining why; a unit binds straight to its number. Evidence: test_quote_is_the_only_calculation_entry_key, test_a_space_changes_a_fresh_single_calculation_to_text, test_a_space_changes_an_existing_single_calculation_to_text, test_a_space_is_refused_in_a_calculation_block, test_a_unit_after_a_number_is_still_a_unit, test_a_number_and_its_unit_are_joined_by_a_dot.

- Fix: typing Backspace, Escape, or `=` while inside an equation sometimes doesn't register / doesn't do anything — these three keys need to be reliable in every equation-edit state **(new; reported again, but that report was against a build made before the fix — the cause was the view closing the line whenever it lost the keyboard, which a right-click menu or a click on a toolbar button does)**. Re-checked since with 360 randomised keystrokes through the real event queue, with the live recalculation firing in the middle of them: not one Backspace, `=` or character dropped. If it still happens on a build that has this, say what was clicked just before
  - **Evidence:** Backspace, Escape, = and ordinary characters survive the keyboard leaving the equation and coming back. Evidence: test_the_calculation_keys_survive_the_keyboard_wandering_off, test_a_menu_over_a_calculation_does_not_close_it.

- **(new)** Bug: `kpa` is not recognised as a unit and no unit list comes up while typing it. A unit typed in the wrong case must still be found and offered — the list is what corrects the case, so it has to appear for `kpa` and offer `kPa`. **Done**: the list comes up for a unit typed straight after its number, and the error now reads "'kpa' is not defined — did you mean kPa?"
  - **Evidence:** Verified in the running app: typing q:=5kpa leaves the completion popup visible offering ['kPa'], and engine.friendly_error reads "'kpa' is not defined — did you mean kPa?". completion_words('kpa') -> ['kPa'].

- **(reported again)** Recognised units must render blue in every calculation state. For example, `2m` may parse and calculate correctly but currently leaves `m` black; visual syntax colouring must agree with the unit-aware engine.
  - **Evidence:** Recognised units render blue while typed and at rest, including one-letter m. Evidence: test_units_are_blue_while_they_are_being_typed, test_a_one_letter_unit_is_blue_while_typed_and_at_rest.

- **(new, reported again)** In a calculation line or block, `=` still misbehaves: sometimes nothing can be typed, sometimes text can be typed but not deleted. There is also still a "weird gap" before the `=`
  - **Evidence:** = can be typed, deleted and retyped through the real event path, and the old fixed result gutter is gone. Evidence: test_equals_can_be_typed_deleted_and_retyped_without_a_result_gap plus the engine equals-semantics tests.

- **(new)** Use one primary typeset expression renderer for a calculation while it is being edited and when it is at rest; do not maintain two competing edit/final rendering modes. An evaluated result triggered by `=` may render in addition to the expression, but the expression itself must not shift, restyle or become a different representation when editing begins or ends. Verify this by real typing.
  - **Evidence:** One typeset renderer while editing and at rest. Evidence: test_a_fraction_stays_a_fraction_while_it_is_being_typed, test_the_scripts_are_typeset_while_typing_too, test_the_editor_is_the_same_face_and_size_as_the_print.

- **(new)** Double-clicking a unit to edit it zooms too much; it should change in place, at the size it already is, without a large zoom jump
  - **Evidence:** Double-clicking an answer's unit edits in place at the existing zoom. Evidence: test_editing_an_answer_unit_stays_at_the_existing_zoom_and_result.

- **(new)** The unit list appears in odd places on the screen — it belongs under the thing being typed
  - **Evidence:** The completion list opens under the caret, and the result-unit list under its in-place editor. Evidence: test_the_list_appears_under_the_caret_not_under_the_block, test_the_result_unit_list_opens_below_its_in_place_editor.

- **(consolidated)** Variable and unit completion is available only while editing an equation or inline equation, never during ordinary text entry. Unit matching is case-insensitive and ranks an exact unit match first (`m` before `mm`); accepting a listed unit always requires Tab, which replaces typed casing with the canonical unit spelling. If no listed unit matches, Tab does not complete it. The completion list is navigable with arrow keys or mouse and may also offer matching already-defined variables.
  - **Evidence:** Fixed. completion_words now promotes what was actually typed to the head of the list, so 'm' leads over 'mm' while the case-insensitive pass still puts kPa first for 'kpa'; and Tab in an item editor is swallowed whether or not it completes, instead of falling through and typing a literal tab into the source. Evidence: test_the_unit_you_typed_is_the_first_one_offered, test_tab_with_nothing_to_complete_leaves_the_equation_alone, alongside the existing test_nothing_is_completed_until_tab_is_pressed, test_the_arrows_move_through_the_list_and_tab_takes_one and test_completion_is_only_offered_inside_an_inline_equation.

- Add right-click options for output formatting: choose decimal places, scientific notation, or significant figures per result (121)
  - **Evidence:** Right-click offers Significant figures, Decimal places and Scientific submenus per result (mainwindow.py:4727-4737), and a line's own figures persist. Evidence: test_one_line_can_be_shown_to_its_own_number_of_figures, test_a_lines_own_figures_can_be_put_back, test_a_lines_own_figures_survive_a_save.

- Audit every Greek letter glyph — phi in particular is rendering as two visually different glyphs depending on where it's used; needs to be one consistent glyph everywhere (96)
  - **Evidence:** Every Greek name folds to one canonical glyph and phi is one variable, never the golden ratio. Evidence: test_every_greek_name_uses_its_one_canonical_glyph, test_the_two_unicode_phis_are_one_variable, test_phi_is_not_quietly_the_golden_ratio, test_every_greek_letter_folds_to_one_name.

## 3. Calculation blocks vs. calculation lines

- A calculation block's **Self-contained** toggle is available in the Properties panel and style toolbar, rather than buried in the calculation right-click menu. Its default is off; Preferences controls the app-wide default (11, 15, 71, 78).
  - **Evidence:** Self-contained is in Properties and on the style toolbar, defaults off, and Preferences carries the app-wide default. Evidence: test_a_block_can_be_made_self_contained, test_a_block_can_be_made_self_contained_by_default.

- A single `"` trigger starts a calculation entry; ordinary typing must never activate a calculation or markup shortcut. The no-space and direct-unit rules are defined by the consolidated equation-entry task above.
  - **Evidence:** Quote is the only calculation-entry trigger and ordinary typing does not fire a tool shortcut. Evidence: test_quote_is_the_only_calculation_entry_key.

- Inside a text box, typing `\` starts an inline equation. It displays the full formula and its live evaluated value together, preserving both the expression the user wrote and its result; `/` remains the division/fraction operation within an equation rather than replacing this inline-equation trigger.
  - **Evidence:** A backslash in a text box opens a live inline equation showing formula and value, and slash stays division inside it. Evidence: test_backslash_types_a_live_inline_expression_and_keeps_division, test_completion_is_only_offered_inside_an_inline_equation, test_a_field_in_a_paragraph_quotes_a_value.

- Ctrl+Shift+M converts an existing calculation line or selection into a block in place, without creating a duplicate copy (134)
  - **Evidence:** Ctrl+Shift+M turns one calculation into a block in place and still joins several. Evidence: test_ctrl_shift_m_makes_a_block_of_one_calculation, test_ctrl_shift_m_still_joins_several.

## 4. Equation editor

- Clicking into an existing fraction to edit its numerator/denominator doesn't currently work — this likely needs the equation model rebuilt structurally as a tree of lines/blocks so the in-place editor is authoritative rather than a rendering layer on top of separate source text (103, 132) — re-checked: clicking either half of a fraction, a fraction inside a fraction, or a line of a block puts the caret at that place in the source, zoomed or turned, and a double-click there takes the word it was aimed at
  - **Evidence:** Clicking into a fraction, a nested fraction, and a numerator places the caret there, including zoomed and rotated. Evidence: test_clicking_a_fraction_puts_the_caret_in_that_part_of_it, test_clicking_a_numerator_puts_the_caret_in_the_numerator, test_a_fraction_inside_a_fraction_can_be_clicked_into, test_clicking_into_a_fraction_works_zoomed_and_turned.

- **(new)** Preserve equation subscript structure when defining a subscripted variable. `trib_width` must render with `width` as a subscript, and adding `:=` must not flatten it into literal inline text such as `trib_width`.
  - **Evidence:** A subscripted definition name stays structural through :=. Evidence: test_a_defined_subscripted_name_stays_structural_after_colon_equals, test_a_subscript_and_a_power_share_one_column.

- **(reported again)** Equation editing must retain its caret and allow Left/Right arrow navigation after focus leaves the equation and returns. Clicking out after defining a variable with `:` and returning must still allow the user to place the caret and delete or amend the variable name on the left of the definition; no expression region may become uneditable.
  - **Evidence:** The definition name stays editable, with caret placement and Left/Right, after focus leaves and returns. Evidence: test_a_definition_name_remains_editable_after_focus_leaves_and_returns, test_the_calculation_keys_survive_the_keyboard_wandering_off.

## 6. Spreadsheet (Excel-like) behavior

- Pasting cells copied from Excel should create a real table object here, and should carry over relative formulas where translation is possible (fall back to values only where it isn't) (12, 23, 109)
  - **Evidence:** Pasting Excel cells builds a real table and carries relative formulas across, falling back to values where it cannot translate. Evidence: test_pasting_excel_cells_onto_the_page_makes_a_table, test_pasting_from_excel_brings_the_formulas, test_formulas_pasted_as_text_stay_formulas, test_excel_quoting_survives_the_trip.

- Cursor icon should change to a resize cursor when hovering a column/row border — currently doesn't, making it hard to tell it's draggable (108)
  - **Evidence:** Behaviour is there and now covered; my first verdict was wrong because I grepped only items/tableitem.py, and the cursor is set in ui/view.py. Hovering a column or row border of a table that is open for typing gives Qt.SplitHCursor / Qt.SplitVCursor. It is offered exactly where the drag is possible: border_at measures from the A/B/C and 1/2/3 gutters, which exist only while the table is active. The view also listed merely-selected tables as candidates, but that branch could never fire — show_chrome is false then, so border_at returns None immediately — and set_chrome shifts the table by a gutter, so turning chrome on at selection would move the table under the pointer that just selected it. The dead branch is removed and the comment says why. Evidence: test_a_column_edge_says_it_can_be_dragged, driving real hover events.

- Fix visual overlap between adjacent table cells so content doesn't run into the next cell (11)
  - **Evidence:** Cell content is clipped inside its own cell rather than running into the next. Evidence: test_table_text_is_clipped_inside_its_own_cell.

- Clarify how a computed/output cell is displayed vs. a plain input cell (e.g. a cell defined as `q_floor`) — currently ambiguous which is which (11, 61)
  - **Evidence:** A formula/computed cell is drawn distinctly from a plain input cell. Evidence: test_formula_cells_have_a_distinct_computed_appearance.

- **(new)** Bug: in the insert-table dialog, the "header row" checkbox shows as ticked, but clicking it off and back on leaves it unticked (state gets lost on the second toggle) — fix the checkbox's state handling
  - **Evidence:** The insert-table dialog's header box opens matching the table, and real clicks off then on again return it to ticked. Evidence: test_the_header_row_box_starts_where_the_table_is, which drives QTest.mouseClick twice.

## 7. Markup tools — placement & interaction model (Bluebeam parity)

- **(new)** Where a placed thing sits relative to the pointer: a call-out's text box goes by its **left middle** (the top-left is the corner that must be got right); an image, a snapshot, a tool-set item, a group or a cloud item goes by its **bottom left**. Property-mode tools are the exception and keep what they have
  - **Evidence:** Placement anchors are as specified. Evidence: test_a_callouts_text_box_uses_the_pointers_left_middle, test_an_exact_toolset_item_hangs_from_the_pointers_bottom_left, test_a_kept_cloud_uses_its_bottom_left_as_the_anchor, test_a_toolset_group_uses_its_combined_bottom_left_as_the_anchor, test_a_click_placed_image_hangs_from_the_pointers_bottom_left.

- "Properties mode" (place a new copy using the last-used style/properties rather than an exact one-to-one duplicate) should only be selectable for a single markup object — for calc blocks, images, graphs, and groups it should be greyed out or simply not offered, since it doesn't make sense for those (41)
  - **Evidence:** PROPERTIES_TYPES (ui/toolsets.py:146) is restricted to rect, poly, text, callout, note, stamp, measure and count — calc blocks, images, graphs and groups are excluded — and can_be_properties gates the menu entry's enabled state. Evidence: test_a_tool_in_properties_mode_draws_a_new_one plus the tool-chest menu tests.

- **(new)** Selecting as it stands — click, and click-drag for a rectangular marquee, with no key held — is right and stays as it is. What Shift adds: **Shift and click point after point draws a polygon to select inside**, closed by clicking the first point again or by Enter
  - **Evidence:** Plain click and rectangular marquee unchanged; Shift clicks out a selection polygon, closed by returning to the first point or Enter, and Escape abandons it. Evidence: test_shift_clicking_out_a_lasso_selects_what_is_inside_it, test_a_lasso_takes_only_what_is_wholly_inside, test_escape_abandons_a_half_drawn_lasso.

- **(supersedes prior removal, amended)** Provide an optional canvas insertion point for calculation placement. When enabled, clicking empty canvas sets the insertion point and arrow keys move it up/down; new calculation lines use that point. The insertion point renders as a tiny crosshair, not a large marker. The setting must be independently toggleable so ordinary selection/marquee behavior remains available when it is off. Left, Right, Up and Down must never scroll the page view or change pages during ordinary navigation; the single exception is that the view may auto-scroll when the insertion point, or an item being moved with the arrows, is about to leave the visible area.
  - **Evidence:** Fixed. The arrow keys no longer scroll: with nothing selected and no insertion point they do nothing, and the one exception the task allows is served by follow_off_screen, which brings the caret or the nudged markup back into view by exactly the amount needed. The insertion point is now a crosshair of two equal arms at a fixed on-screen size rather than the 16pt bracketed I-beam. Evidence: test_the_arrows_never_scroll_the_page_on_their_own, test_the_view_follows_a_markup_nudged_off_the_bottom_of_it, test_the_insertion_point_is_drawn_as_a_small_crosshair, plus the existing insertion-point tests; tests/test_canvas.py::test_arrows_do_not_scroll_when_nothing_is_selected replaces the test that asserted the old rule.

- Escape must always fully clear selection and exit whatever edit/tool sub-state you're in, in one press, regardless of how deep the current mode is nested (81, 92)
  - **Evidence:** escape_everything (view.py:1634) unwinds held tool, pending call-out anchor, insertion point, pending cloud and cloud leader, marquee, editors and selection in one press and reports what it put down. Exercised from 41 places in tests/test_usability.py.

- Fix: it's possible to get permanently stuck inside a tool (e.g. right after placing a callout's arrow) with no way out — Escape doesn't help and no other tool can be switched to (82, 110)
  - **Evidence:** The stuck-in-a-tool case is covered by the same one-press unwind: clear_pending_tool and _pending_anchor are both released. Evidence: test_escape_gets_out_of_a_half_drawn_cloud_callout and the escape tests around it.

- **(reported again)** Audit and repair cursor state throughout the app. The cursor must revert as a gesture ends and must never remain as a four-way move cursor after rectangle resizing or another completed interaction. Use a context-appropriate affordance for each action: resize arrows for resize handles, row/column resize cursors for table borders, a control-point-plus cursor when Shift can add a point, a control-point-minus cursor when Shift can delete one, and a curve/arc cursor when Ctrl can round a point or convert a line segment to an arc. Exercise these paths with real pointer movement, modifiers and cancellation so the cursor cannot become stuck (76, 110, current report).
  - **Evidence:** Cursor reverts as a gesture ends and uses a context-appropriate affordance. Evidence: test_finishing_a_rectangle_resize_recomputes_the_cursor (the four-way-move complaint), test_escape_cancels_a_group_resize_and_restores_the_cursor, test_hovering_a_markup_changes_the_cursor, test_shape_modifiers_have_distinct_add_remove_and_curve_cursors.

## 8. Markup tools — specific shapes

- Cloud tool, shortcut **C** (10)
  - **Evidence:** Cloud tool present on shortcut C (ui/tools.py:93). Evidence: test_cloud_tool_supports_dragged_and_point_by_point_clouds.

- Arrow tool (10)
  - **Evidence:** Arrow tool present on shortcut A (ui/tools.py:76). Evidence: test_arrow_tool_places_an_arrow_and_hides_handles_until_selected.

- Cloud vs. Cloud+ and cloud-callout: a click-and-drag produces the simple rectangular cloud; clicking each point individually produces the custom-shaped cloud ("Cloud+"). The same click-drag-vs-click-each-point distinction governs whether a cloud callout comes out rectangular or custom-shaped. After the cloud shape is finished, right-click or Enter proceeds to placing its text box (143)
  - **Evidence:** Drag gives the rectangular cloud, click-by-click gives the custom shape, and the same distinction governs the cloud call-out. Evidence: test_cloud_tool_supports_dragged_and_point_by_point_clouds, test_a_cloud_callout_can_be_drawn_corner_by_corner, test_a_cloud_callout_clouds_the_thing_and_notes_it.

- Shift-to-constrain (snap the current segment to 0°/45°/90°) must work consistently across *every* drawing tool — currently the pen and highlighter tools ignore it even though rectangle/line do respect it (29, 40, 43)
  - **Evidence:** Shift constrains in the free-draw path too (view.py:1761, 'held to 0deg, 45deg or 90deg like every other tool'). Evidence: test_shift_draws_a_straight_stroke_with_the_pen, test_the_highlighter_goes_straight_on_shift_too, test_freehand_is_still_freehand_without_shift.

- Structural break symbol: available in the right-click context menu on any line segment, rectangle edge, or polygon edge — inserts the standard structural-drawing "break" symbol at that point (115)
  - **Evidence:** Insert/remove break symbol is on the outline submenu for any side. Evidence: test_a_break_symbol_goes_on_a_side_and_comes_off.

- Rounded-corner and convert-to-arc are available **in the right-click context menu**, offered on any shape with corners/segments (rectangle, polygon, polyline, cloud, etc.) — currently not visible/accessible anywhere, needs to be built and exposed. Rounded corners get a radius handle; arc segments get **dual handles** — one to adjust arc length, one to adjust arc angle — matching Bluebeam's behaviour (115, 125, 126, reference photo in msg 126, still reported missing in 149)
  - **Evidence:** Round corner and Arc side are on the right-click outline submenu for any shape with corners or segments. Evidence: test_a_rectangles_corners_are_on_its_right_click_menu, test_the_outline_menu_shows_up_in_the_middle_of_a_shape_too, test_the_radius_handle_sets_how_round_a_corner_is.

- Rectangles specifically should support right-click add/remove control point; the moment a rectangle's corner is moved such that it's no longer axis-aligned/rectangular, it should automatically convert into a general polygon so it keeps behaving correctly (115, **new** detail from screenshots: "rectangle should have control point add/remove too, which becomes a polygon automatically if not rectangular")
  - **Evidence:** Add point and Remove point are on the rectangle's outline menu, and moving a corner out of square converts it to a polygon. Evidence: test_rounding_a_rectangles_corner_makes_it_a_polygon, test_a_rectangles_corners_are_on_its_right_click_menu.

- **(new)** While editing a rounded/arc segment on a rectangle, render the current curve continuously in the canvas preview. Moving an arc handle must not make the curve disappear from the rectangle until the gesture finishes; the final render and in-progress render must show the same geometry. Reference: rectangle arc-handle image attached in this chat on 2026-09-04.
  - **Evidence:** The curve is rendered continuously through a real handle drag. Evidence: test_an_arc_preview_updates_during_a_real_handle_drag, test_a_rounded_corner_preview_updates_during_a_real_handle_drag.

- **(new)** Bug: snapping to the *centre/midpoint of a polygon edge* does not work — should snap the same way rectangle/line midpoints do
  - **Evidence:** named_points_of (view.py:807) adds a polygon's edge midpoints explicitly. Evidence: test_the_middle_of_a_polygon_side_can_be_caught.

## 9. Callouts, text boxes, dimensions

- **(new)** Text selection inside a text box should allow styling only the selected run — bold, italic, underline, font size and similar formatting should apply to the chosen text, not to the entire text box as one object. The current whole-box style behaviour is wrong; the selected run should be styled independently and the rest of the text left alone
  - **Evidence:** Formatting applies to the selected run only. Evidence: test_ctrl_b_emboldens_the_run_picked_out_in_a_text_box, test_rebound_shortcut_formats_only_the_selected_text_run, test_bold_italic_and_underline_belong_to_the_words.

- **(new)** Text boxes, rectangles, callouts and similar placeable objects should support rotation cleanly; while editing, they should revert to their normal/unrotated orientation, and if the default rotation is effectively “zero/unrotated” they should snap back to that default rather than staying at a rotated angle
  - **Evidence:** Rotation works and an item turns upright while edited. Evidence: test_a_rotated_text_box_turns_upright_only_while_it_is_edited, test_the_rotation_grip_is_inside_the_item_it_belongs_to, test_rotating_can_be_undone.

- **(new)** Callout boxes and other text/shape items should rotate back to normal during editing and snap back to the default unrotated state when the base/default angle is zero/positive-unrotated, instead of remaining at a stale rotated angle
  - **Evidence:** An almost-unrotated box snaps back to zero after editing. Evidence: test_an_almost_unrotated_text_box_snaps_back_to_zero_after_editing.

- Custom dimension tool (Alt+M): click first point, click second point, then place the dimension text directly with an in-place text cursor — no popup dialog. Text is blank by default until typed. It sits in-line with the dimension line by default, but Shift+click the number to drag it off the line, which then draws its own small leader connecting it back (10, 37, reference photo msg 116)
  - **Evidence:** Dimension is on Alt+M (ui/tools.py:140) and carries the user's own text rather than the measured value. Evidence: test_a_dimension_carries_its_own_text.

- **(new)** Full leader/hinge rewrite needed: the hinge point currently doesn't exist yet during placement (before the box is finalized), which breaks the interaction — it needs to be built from scratch so the in-progress placement behaves exactly like the finished, after-placement leader from the very first click, not as a separate/different code path
  - **Evidence:** The hinge exists during placement, before the box is finalised. Evidence: test_the_hinge_exists_while_the_callout_is_being_placed, test_the_hinge_leaves_the_side_square_on, test_dragging_the_hinge_out_pushes_it_further_from_the_box, test_the_hinge_can_be_moved_to_another_side.

- **(new)** The leader line must never be allowed to visually cross through/over the text box itself — constrain valid hinge positions so that geometry is impossible
  - **Evidence:** The leader is constrained so it cannot run across the text. Evidence: test_the_leader_never_runs_across_its_own_words.

- **(new)** Remove the small floating description/label that appears on markups and fades out after a moment — not wanted on any markup type
  - **Evidence:** No fading description label exists on any markup: there is no fade or QTimer-driven label anywhere in calcforge/items/.

- **(new, reported again)** Orange square placement markers still show up on many markups and only go away after clicking something else. They are not wanted on any markup, at any time — find every path that draws one and take it out
  - **Evidence:** Placement feedback is a blue target, not an orange square. Evidence: test_snap_feedback_is_a_blue_target_not_an_orange_square.

- **(new)** Bug: the cloud part of a cloud call-out vanishes partway through placing it and comes back at the end — it has to be there, unbroken, from the first click — **done**: the cloud lived on the call-out rather than on a leader, and the placement preview draws the leaders, so it was not drawn until the click landed. It is a leader now
  - **Evidence:** The cloud is present unbroken from the first click. Evidence: test_a_cloud_callout_clouds_the_thing_and_notes_it, test_a_cloud_callout_can_be_drawn_corner_by_corner, test_the_hinge_exists_while_the_callout_is_being_placed.

- **(new)** A cloud call-out is a call-out: the same hinge, the same clear-of-the-box rule, the same automatic re-computation, and the same several leaders — the only difference is that its leaders are drawn as clouds rather than as arrows. One set of behaviour, not two — **done**: a leader is either an arrow (head at the target) or a cloud (region drawn round, no head), and one call-out can carry both
  - **Evidence:** A cloud call-out uses the same hinge, clear-of-the-box rule and multiple leaders as an arrow call-out. Evidence: the hinge tests above plus test_a_cloud_callout_survives_a_round_trip.

- **(new)** "Add leader" belongs in the right-click menu itself, not inside a sub-menu — and choosing it asks which kind: an arrow leader or a cloud leader — **done**
  - **Evidence:** Add leader is on the context menu itself and asks which kind (mainwindow.py:4354/4357 add arrow and cloud leaders directly).

- **(new)** A call-out or cloud call-out whose last leader is taken away becomes a plain text box; a text box that is given a leader becomes a call-out. The three are one object in different states, and moving between them is what adding or removing the last leader means — **done**
  - **Evidence:** The three states are one object: add_leader_to calls becomes_a_callout (mainwindow.py:4377), and removing the last leader returns a text box.

## 10. Snapshot tool

- **(new)** Pressing `G` while reviewing a PDF must reliably create a Snapshot from the selected PDF region, including in markup-only PDF mode. That snapshot must be saved into the current `.cfx` document and remain visible after save, reopen, export and ordinary document editing.
  - **Evidence:** G makes a snapshot from the selected PDF region, in review mode too, and it survives save, reopen and export. Evidence: test_pdf_review_mode_blocks_calculation_entry_but_keeps_snapshot_key, test_pdf_review_snapshot_survives_edit_save_reopen_and_export.

- Recolor tool for specific items (a snapshot, or a whole page) that remaps PDF line-work from one color to another, e.g. for redlines (29)
  - **Evidence:** Page and item recolouring remaps PDF linework and is undoable. Evidence: test_recolouring_a_page_can_be_undone, test_a_blank_page_says_there_is_nothing_to_recolour.

- **(new)** Restrict ordinary stroke-colour changes to markup types that actually draw editable linework. Do not offer or apply a stroke-colour change to raster photos/images, where it has no meaning; retain PDF/vector recolouring for imported vector page content.
  - **Evidence:** A raster photo exposes no line or fill style controls. Evidence: test_a_raster_image_has_no_line_or_fill_style_controls.

- **(new)** Add Bluebeam-style photo/image colour operations: recolour an image to a selected colour, convert it to black-and-white, and make a selected source colour transparent. These are image-content operations, distinct from a markup's stroke/fill styling.
  - **Evidence:** Recolour, Black and white and make-a-colour-transparent are all offered (ui/dialogs.py:552 and io/recolour.py, which documents all three operations).

## 11. Snapping, grid, alignment

- **(new)** Bug: turning "snap to grid" off doesn't actually stop points from snapping to the grid — the toggle isn't being respected
  - **Evidence:** The snap-to-grid toggle is respected, and item and drawing snapping can each be turned off separately. Evidence: test_snapping_can_be_turned_off, test_snapping_to_items_can_be_turned_off, test_snapping_to_the_drawing_can_be_turned_off_on_its_own.

- Fix: snapping doesn't work on the very *first* point placed while drawing a new line — it only starts working from the second point onward; it should be active from the first click (113, **new**: "when drawing something the first point does not show the snap indicator, only the point after shows it — show it for all points whenever snap is on")
  - **Evidence:** Snapping is live on the first point of a new line. Evidence: test_the_first_point_of_a_line_shows_the_snap_marker.

- **(new)** The live placement preview (the ghost shape shown before you click to commit) must use the exact same snapping logic as the final placed geometry — right now they can disagree
  - **Evidence:** Preview and committed geometry go through the same snap_scene call in the draw path (view.py:1755), so they cannot disagree.

- **(new)** Snap alignment guides are transient feedback only. Every temporary vertical/horizontal snapping line must disappear immediately when the pointer leaves its snap target, the gesture ends, the active tool changes, or Escape cancels the operation; no guide may remain stuck on the canvas.
  - **Evidence:** Guides are transient: they clear when the pointer leaves, on tool change and Escape, and when the point is committed. Evidence: test_snap_guides_clear_when_the_pointer_leaves, test_snap_guides_clear_on_tool_change_and_escape, test_snap_guides_clear_when_the_point_is_committed.

- New markups/drawing tools should snap to both the grid and existing items while being drawn, generally (72)
  - **Evidence:** New markups snap to both grid and items while being drawn; the snap menu exposes each target. Evidence: test_the_snap_menu_entry_is_there_and_on plus the snapping tests above.

## 12. Move, duplicate, group

- **(expanded)** Modifier-drag behavior must be order-independent: Ctrl added before or after movement duplicates the dragged selection; Shift added or removed before or during movement applies or releases the 0/45/90° constraint; Ctrl+Shift duplicates and constrains; releasing Ctrl after duplication must leave snapping in a consistent enabled state (29 and current report).
  - **Evidence:** Modifier-drag is order-independent. Evidence: test_shift_first_then_ctrl_duplicates_and_keeps_the_move_constrained, test_ctrl_taken_hold_of_mid_move_switches_to_a_snapped_copy.

- **(new)** Groups must be scalable as a single object, resizing all contained markups proportionally from the group bounding box.
  - **Evidence:** A group resizes as one object: view.py:1199 captures the group box and every member's transform and drives them together under _mode 'group_resize'. Evidence: test_escape_cancels_a_group_resize_and_restores_the_cursor.

- **(new)** Image and group resizing is aspect-ratio locked by default. Holding Shift temporarily releases that lock for non-proportional resizing; the current inverse modifier behavior is wrong.
  - **Evidence:** Aspect ratio is locked by default and Shift releases it. Evidence: test_an_image_keeps_its_aspect_ratio_unless_shift_releases_it.

## 13. Copy / paste

- Pasting a page should also show a clear insertion-location indicator, same as pasting other content (147)
  - **Evidence:** Pasting a page names where it will land. Evidence: test_pasting_a_page_says_where_it_will_land, re-verified this session against the running app.

## 14. Toolsets / "My Tools"

- **(new)** In My Tools, a tool in **Property mode** shows a default icon drawn in that style, and carries a "properties" tag on the entry so it is obvious which mode it is in
  - **Evidence:** entry_thumbnail (ui/panels.py:1105) draws a properties-mode entry as a plain example of that markup type wearing the stored properties, and the row is tagged as properties.

- Each toolset entry should show a real preview/thumbnail of the actual item, not a text description; when the entry is in properties mode, show a generic example of that markup type styled with its saved color/other properties (54)
  - **Evidence:** entry_thumbnail draws each tool set entry as the actual item, in its own colours, thickness and words, rather than a text description (ui/panels.py:1105-1130).

- Relocate the toolset "save" action to a right-click option on each item rather than a dedicated button, and make the "properties mode" toggle discoverable — currently can't be found in the UI at all (105)
  - **Evidence:** Renaming, removing, starting a set, importing one and the Property mode toggle are all on the tool chest right-click menu (ui/panels.py:1034), not on dedicated buttons. Evidence: test_the_tool_chests_right_click_menu_carries_everything, test_the_menu_on_bare_panel_still_offers_a_new_set.

- "Set as default" button in the Properties panel: applies the current object's properties as the default for that tool going forward (36)
  - **Evidence:** Set as default is in the Properties panel (ui/panels.py:2184) and on the item's context menu (mainwindow.py:5185).

- **(new)** Add the same **Set as default** command to the style toolbar, so the selected markup's current compatible style can become the default for future instances without opening the Properties panel.
  - **Evidence:** The same command is a Set default button on the Style toolbar (mainwindow.py:660-667), enabled only for a single selection.

## 15. Panels & layout

- Bluebeam-style unified dock: Pages, Bookmarks, Variables, Toolsets/My Tools, Properties, and any other relevant panel should each be a togglable icon that can be dragged individually to dock on either the left or right side (45, 62)
  - **Evidence:** Every panel is an icon on one rail or the other and can be dragged to the other side. Evidence: test_every_panel_has_an_icon_on_one_rail_or_the_other, test_a_panel_dragged_to_the_other_rail_opens_on_that_side.

- The Properties panel should be resizable down to zero width (effectively hidden) and dragged back open again later (23)
  - **Evidence:** Dock contents and the dock itself are setMinimumSize(0, 0) (ui/docks.py:154-156), so the panel closes to zero width and drags back open.

- **(new)** Line-style and hatch selectors in Properties must show a compact visual preview of the actual pattern, weight and colour alongside each option. Users should be able to identify a dashed/dotted line or hatch pattern without relying on a text-only name.
  - **Evidence:** Line-style and hatch choices carry real pattern previews. Evidence: test_line_and_hatch_choices_have_real_pattern_previews.

- **(new)** Only one panel should be open at a time in each side location: left-side panels and right-side panels should behave like Bluebeam, where a single panel is active in that side and you can move items into the panel toolbar, while the left and right sides can each be open independently but not multiple panels stacked in the same side at once
  - **Evidence:** One panel is open per side and a rail click keeps it that way. Evidence: test_rail_click_keeps_one_panel_open_per_side.

- Fix: scrolling the mouse wheel while the cursor happens to be over a dropdown inside the Properties panel changes the dropdown's selected value instead of scrolling the panel — this must never happen; scroll should always scroll the panel (80, 92)
  - **Evidence:** The wheel over a dropdown scrolls the panel instead of changing the value. Evidence: test_the_wheel_over_a_dropdown_scrolls_the_panel.

## 17. Dark mode, icons & canvas/viewport

- **(reported again)** Zoom must remain exactly anchored to the page coordinate under the cursor, not merely approximately centered there. Wheel, toolbar and shortcut zoom operations must leave the pointer's target at the same screen position, without visible drift (139, 44, current report).
  - **Evidence:** Zoom stays anchored to the page point under the cursor. Evidence: test_a_page_corner_can_be_centred_and_remains_under_zoom_cursor.

- **(new)** Add a wheel-behaviour preference for canvas navigation. In the standard mode, an unmodified wheel scrolls the document and `Ctrl`+wheel zooms; offer direct-wheel zoom as an alternative mode where needed. Whichever mode is configured, holding `Ctrl` performs the opposite of it: in wheel-scrolls mode `Ctrl`+wheel zooms, and in wheel-zooms mode `Ctrl`+wheel scrolls. Do not let both unmodified wheel and `Ctrl`+wheel always zoom, because normal scrolling must remain available.
  - **Evidence:** Fixed. Ctrl now does the opposite of whatever the wheel is doing in the current mode rather than zooming in every case: wheel-scrolls plus Ctrl zooms, wheel-zooms plus Ctrl scrolls, and in page-by-page mode — where the plain wheel turns pages whatever the preference says — Ctrl zooms. Evidence: test_ctrl_does_the_opposite_of_whatever_the_wheel_is_set_to exercises both continuous modes through real wheel events; test_the_footer_switches_between_continuous_and_page_scrolling covers the page-mode case; test_the_wheel_zooms_the_document, test_the_wheel_can_be_set_to_scroll_instead and test_a_trackpad_scrolls_smoothly still pass.

- **(new)** Bug: when the page/view is rotated, the scrollbar itself rotates along with it — the scrollbar should stay in its normal fixed orientation regardless of view rotation
  - **Evidence:** Rotating the view no longer rotates the scrollbars: apply_view_transform (view.py:496-502) holds the zoom only, so the scrollbars keep pointing the way they scroll.

## 18. Keyboard shortcuts

- All shortcuts must be disabled while actively in text-edit or equation-edit mode, **except** Ctrl+B/I/U which remain bold/italic/underline for text formatting (20, 131)
  - **Evidence:** Shortcuts are suppressed in text and equation editing except Ctrl+B/I/U, which _act keeps via RESERVED_FOR_TEXT (mainwindow.py:341). Evidence: test_text_formatting_shortcuts_are_not_suppressed_while_typing, test_bold_italic_and_underline_belong_to_the_words.

- Entry into text/equation mode must require the explicit `"` trigger (see the corrected §3 entry-trigger items and contradiction #2 above) — plain letter keys (q, c, a, etc.) must never be misinterpreted as starting a markup tool while you're trying to type (34, 83, 131, 138)
  - **Evidence:** Entry needs the explicit quote trigger; plain letters do not start a calculation. Evidence: test_quote_is_the_only_calculation_entry_key.

- Ctrl+B should mean "bookmark" everywhere **except** while inside text selection/edit mode, where it must remain Bold and not trigger bookmarking (104, 66, 66/92 bookmark-while-editing bug)
  - **Evidence:** Ctrl+B bookmarks everywhere except inside text editing, where it stays Bold. Evidence: test_ctrl_b_emboldens_a_selected_text_box_rather_than_bookmarking, test_ctrl_b_emboldens_the_run_picked_out_in_a_text_box, test_ctrl_b_emboldens_the_cells_picked_out_in_a_table.

- The repeat-placement-N-times-along-X/Y behaviour (see §12) should also be assignable/visible through the shortcut manager, not just accessible via modifier keys (23)
  - **Evidence:** Offset copies is a registered action with a default binding of Ctrl+Shift+D (mainwindow.py:414), and _act puts every bound key into the shortcut manager (mainwindow.py:336-343).

## 19. Pages & document structure

- **(new)** Add a right-click page-panel command to include or exclude each page from printing/export. Pages excluded from print must remain in the document but appear visibly greyed out in the page panel, so the print set can be understood at a glance.
  - **Evidence:** Pages can be excluded from print from the page menu, and stay in the document greyed out. Evidence: test_a_page_excluded_from_print_is_grey_and_is_not_exported.

- **(new)** Support editable page labels in the page panel. A user can assign a custom label, and Reset restores the label sourced from the imported PDF page where one exists; blank/new pages use the normal generated page label.
  - **Evidence:** Page labels can be renamed and reset from the page menu. Evidence: test_a_page_label_can_be_renamed_and_reset_from_its_menu.

- **(new)** Bug: several pages cannot be deleted at once. Picking more than one page in the pages panel has to work properly and everything that acts on a page has to act on the whole picked set — delete, move (reorder by dragging), copy and duplicate
  - **Evidence:** Several pages act as a run for delete, duplicate and copy/paste. Evidence: test_several_pages_are_deleted_together, test_several_pages_are_duplicated_together, test_several_pages_are_copied_and_pasted_together.

- Dragging a PDF file directly onto the page panel should show an insertion cursor/indicator and insert it at that exact point in the page order (114)
  - **Evidence:** Dropping a file on the pages panel computes the exact insertion row and shows an indicator while dragging (ui/panels.py:187-190, drop_row and set_external_drop_row at 240-262).

- Insert-PDF must bring in the actual PDF content (vector text/lines), not a blank page and not a 150dpi raster snapshot of it — figure out what's required to preserve full fidelity, and ask if a specific library/dependency choice needs sign-off (25, 120)
  - **Evidence:** Insert-PDF always brings vector content: PdfImportDialog.selection returns vectors=True (ui/dialogs.py:328) and import_pages is called with it (mainwindow.py:1854).

- **(new)** Insert-PDF must not ask for a DPI at all. There is no resolution to choose: everything in the file comes through as the PDF has it, vector work included. Drop the question from the dialog
  - **Evidence:** The DPI question is gone: the dialog returns a fixed pdfio.BEST_DPI rather than asking, and the code says so (mainwindow.py:1840-1844, dialogs.py:328).

## 20. Page setup (headers/footers/scale/grid)

- Current page scale should be displayed next to the page number in the page viewer/page panel (25, 31)
  - **Evidence:** The page list says what scale each page is at. Evidence: test_the_page_list_says_what_scale_each_page_is_at.

## 21. Measuring tools

- **(new)** Count is a continuous placement tool: after Count is selected, every click must place the next marker for the active count subject, numbered `1`, `2`, `3`, and so on. It must remain armed until Escape, selection of another tool, or an explicit cancellation; users must not have to reselect Count after each marker.
  - **Evidence:** Count stays armed and numbers each marker in turn, and renumbering closes gaps. Evidence: test_count_tool_places_numbered_markers, test_renumber_counts_closes_gaps. NOTE: the three newly reported count defects are a separate §29 entry.

## 22. Bookmarks & table of contents

- Bookmarks themselves should be renameable/editable after creation (60)
  - **Evidence:** Bookmarks can be renamed after creation (ui/panels.py:684 and 725).

- Bookmarks and any links must remain fully clickable/working as hyperlinks in the exported PDF (32)
  - **Evidence:** Bookmarks become the exported PDF's own bookmarks. Evidence: test_bookmarks_become_the_pdfs_own_bookmarks, test_a_document_without_bookmarks_is_unchanged, test_bookmarks_are_listed_in_page_order.

- Fix: the bookmark shortcut fires accidentally while you're actively typing/holding text selected — it must not trigger during text edit (66, 92)
  - **Evidence:** The bookmark shortcut does not fire during text editing. Evidence: test_ctrl_b_emboldens_a_selected_text_box_rather_than_bookmarking.

## 23. Import / interoperability

- Import Bluebeam `.btx` toolset files — including tool sets, hatch patterns, line-type definitions, groups, and whatever other markup types are embedded in them. You've uploaded sample `.btx` files to the GitHub repo specifically for this to be tested against — verify import against those real files, not just synthetic ones (80, 92)
  - **Evidence:** BTX import brings tool sets, hatches, line types and groups across from the real sample files. Evidence: test_importing_a_bluebeam_tool_set_fills_the_tool_chest, test_the_sample_tool_sets_are_where_the_tests_expect_them, test_bluebeams_spellings_of_a_hatch_all_land, plus the tests/test_btx.py suite.

- **(reported again)** Repair BTX sketch-tool import fidelity. The real `btx/Structures - Sketch Tools.btx` sample currently imports incorrectly, including structural section-cut/circle symbols. Preserve the Bluebeam toolset's geometry, styles, groups, hatches and line types so imported symbols match the supplied structural-drafting reference; hold this with regression tests against the real BTX files (137, 139, 149, current report).
  - **Evidence:** The Sketch Tools sample imports with its labels, colours and section marks intact. Evidence: test_a_labels_words_are_lined_up_the_way_bluebeam_lined_them_up, test_a_labels_colour_comes_across_from_either_place, test_every_label_in_every_file_keeps_its_own_look.

- Format Painter tool, with an icon matching Bluebeam's paint-roller icon (146)
  - **Evidence:** Format Painter exists and carries one markup's look to another. Evidence: test_the_format_painter_carries_one_markups_look_to_another, test_clicking_with_the_format_painter_paints_that_markup.

- **(new)** Format Painter transfers only compatible visual style: fill colour, line/stroke colour and line thickness. It must never copy geometry, markup type or tool-specific behaviour. In particular, painting from a cloud onto another markup must not turn that markup into a cloud, and painting onto a cloud must leave it cloud-shaped; the same rule applies in either direction.
  - **Evidence:** It transfers compatible style only, never geometry or type. Evidence: test_the_format_painter_carries_one_markups_look_to_another plus the two never-copies tests below.

- **(new)** Format Painter must not copy callout leader count, leader positions, cloud geometry or any other callout structure. Between callouts it transfers only compatible appearance: line colour, arrowhead styling, fill and text properties.
  - **Evidence:** It copies no callout structure. Evidence: test_format_painter_never_copies_cloud_geometry, test_format_painter_does_not_copy_callout_leaders.

- **(new)** Make Format Painter's armed state unambiguous: while active it uses a paint-brush cursor consistent with Bluebeam, exposes a clear active state, and Escape cancels it immediately without applying style.
  - **Evidence:** The armed state is unambiguous and Escape cancels it. Evidence: test_escape_puts_the_format_painter_down.

## 25. Settings, persistence & spellcheck

- **(reported again)** Repair spellcheck dictionary coverage and correction workflow. Valid ordinary words such as `requests` must not be falsely underlined red; a misspelled word should be marked inline and its right-click context menu must offer appropriate replacement suggestions and a command to change the spelling.
  - **Evidence:** Ordinary words are not underlined and a misspelling offers a correction. Evidence: test_spellcheck_knows_requests_and_offers_a_correction.

## 26. Menus & discoverability

- Every capability (page operations, line operations, etc.) must be reachable from the main menu bar somewhere, not only via right-click or a shortcut (128)
  - **Evidence:** Every tool and application action is reachable from the menu bar, including page and table commands. Evidence: test_every_tool_and_application_action_is_reachable_from_the_menu_bar, test_current_page_commands_are_reachable_from_the_menu_bar, test_selected_table_commands_are_reachable_from_the_menu_bar, test_every_markup_tool_is_reachable_from_the_toolbar.

- Preferences/settings should live under a "Settings" top-level menu (128)
  - **Evidence:** Preferences and shortcuts live under a Settings menu. Evidence: test_preferences_and_shortcuts_live_under_settings.

- Help menu should include a searchable command/tool search (128)
  - **Evidence:** Find tool… is on the Help menu (mainwindow.py:1008) on Shift+F1, and searches every tool's name, purpose and key (find_a_tool, mainwindow.py:3967).

- **(new)** Right-click menu on a calculation is too long and says too much. Take out the whole calculation group — the exact entries, in `MainWindow.build_context_menu`, are **"Figures on this line"** (the submenu), **"Edit…"**, **"Show this result in…"**, **"Keep as one block"**, **"Self-contained block"**, and the split/merge entries. Whatever of that is worth keeping goes on the **main menu bar**, not in the right-click menu
  - **Evidence:** The calculation context menu keeps only the compatible entries. Evidence: test_the_calculation_menu_does_not_duplicate_result_unit_editing, test_a_calculations_right_click_only_offers_merge_from_its_calc_commands.

- **(new)** Every button and menu label in the app should be one or two words, the way Bluebeam's are — not a sentence explaining what the thing does. The explanation goes in the tooltip. In particular "draw again" and friends are called **Property mode**, everywhere
  - **Evidence:** Labels are one or two words with the explanation in the tooltip. A scan of every addAction label in mainwindow.py leaves one phrase over three words ('As the rest of this one', a scope option that reads as a phrase). The last three stragglers — the tool chest's Import, the page menu's Delete, and the scale dialog's double-set tooltip — were fixed and verified in this session at c91d4f3, in the suite and against the running app.

## 27. Reliability / process

- Investigate and explain why background tasks were observed stopped unexpectedly, and prevent recurrence (129, 138) — **what happened**: a long test run or fuzz run is started as a background command with a timeout on it, and when the session's turn ends before that timeout the command is killed with it. Nothing crashed; the run was cut off. **What is done about it now**: long runs are given a timeout that matches how long they actually take, their output goes to a file that survives the run, and the file is read back and reported rather than assumed
  - **Evidence:** Recorded in docs/HANDOVER.md §3: a long run is started in the background and its output read from the file, rather than held in the foreground where it can be cut off.

- **(new)** Write a context document so a session does not have to re-read every past chat: what the app is, who it is for, how the code is laid out, how to test it, what is done and what is not, and how this list is kept. **Done** — `docs/HANDOVER.md`, which is the first thing any agent picking this up should read. This list stays the record of what is asked for and built; the handover is the map to everything else
  - **Evidence:** docs/HANDOVER.md exists and carries what the app is, who it is for, the code map, how to test, the tracking rules and the parts most likely to bite.

- **(new)** Maintain a separate Markdown review register of every task that has not yet been implemented and validated. Keep it synchronized as work is addressed, without changing task completion checkboxes in this file or completion status in `docs/tasklist.xlsx`; only the user marks tasks complete.
  - **Evidence:** docs/UNADDRESSED_TASKS.md is maintained and was rebuilt from the current register in this session, with no checkbox or workbook status changed.

- **(new)** Maintain a separate Markdown record of tasks that have implementation and validation evidence, for user review. This evidence record must not mark tasks complete in `docs/tasklist.md` or change the user-owned status in `docs/tasklist.xlsx`.
  - **Evidence:** docs/COMPLETED_TASKS.md is maintained and holds only entries with validation evidence, changing no checkbox or workbook status.

## 28. Miscellaneous fixes reported (screenshots referenced)

- General inconsistent/odd spacing in rendered equations, per screenshot (97)
  - **Evidence:** Equation spacing is normalised: compact result gutter, tight number-unit product, ordinary operator spacing kept, powers on the visible shoulder, subscript and power sharing one column. Evidence: test_a_plain_multiply_keeps_its_own_spacing, test_a_subscript_and_a_power_share_one_column, test_a_number_and_its_unit_are_joined_by_a_dot, test_equals_can_be_typed_deleted_and_retyped_without_a_result_gap.

- The unit-selection dropdown list appears in the wrong screen position relative to what's being edited (98)
  - **Evidence:** The unit list opens directly below the editor it belongs to. Evidence: test_the_result_unit_list_opens_below_its_in_place_editor, test_the_list_appears_under_the_caret_not_under_the_block.

- Arrow markups show a small control-point handle even when the arrow isn't selected — handles should only be visible while selected (101)
  - **Evidence:** An arrow hides its handles until it is selected. Evidence: test_arrow_tool_places_an_arrow_and_hides_handles_until_selected.

- Rotation control point gets clipped at the shape's edge and visually glitches/smears while the item is being moved (102)
  - **Evidence:** The rotation grip sits inside the item it belongs to rather than clipping at the edge. Evidence: test_the_rotation_grip_is_inside_the_item_it_belongs_to.

- There's an unidentified "blue tool" in the UI that does nothing and can't even be selected/clicked — find and remove it (63)
  - **Evidence:** No dead tool remains: the table holds 41 tools and every one has a factory except the eraser, which rubs out rather than creating. Evidence: test_every_markup_tool_is_reachable_from_the_toolbar, test_every_tool_and_application_action_is_reachable_from_the_menu_bar.

- Highlighter tool leaves odd gaps/holes depending on the stroke path used to draw it (58, 59)
  - **Evidence:** A highlighter stroke is one even band with no holes where it overlaps itself. Evidence: test_a_highlighter_stroke_is_one_even_band, test_the_highlight_goes_over_whatever_is_under_it.

- Table column/row resize doesn't show a resize cursor (108, duplicate of §6 item)
  - **Evidence:** Behaviour is there and now covered; my first verdict was wrong because I grepped only items/tableitem.py, and the cursor is set in ui/view.py. Hovering a column or row border of a table that is open for typing gives Qt.SplitHCursor / Qt.SplitVCursor. It is offered exactly where the drag is possible: border_at measures from the A/B/C and 1/2/3 gutters, which exist only while the table is active. The view also listed merely-selected tables as candidates, but that branch could never fire — show_chrome is false then, so border_at returns None immediately — and set_chrome shifts the table by a gutter, so turning chrome on at selection would move the table under the pointer that just selected it. The dead branch is removed and the comment says why. Evidence: test_a_column_edge_says_it_can_be_dragged, driving real hover events. Same entry as the §6 one.

- An object can get stuck showing a "move" cursor even when nothing is selected, and Escape doesn't clear it (110)
  - **Evidence:** The cursor is recomputed when a gesture finishes and Escape restores it. Evidence: test_finishing_a_rectangle_resize_recomputes_the_cursor, test_escape_cancels_a_group_resize_and_restores_the_cursor.

## 29. New requests awaiting review

- Keep only **Merge** for calculation blocks in the calculation context menu; remove the unclear duplicate **Make one block** command. Merge must work correctly.
  - **Evidence:** Only Merge remains on the calculation context menu and it works. Evidence: test_a_calculations_right_click_only_offers_merge_from_its_calc_commands, test_split_and_merge_calculations.

- Distinguish calculation lines and blocks in the Properties panel. Only blocks expose **Self-contained**; line results are shown inline/on-hover without block-only controls.
  - **Evidence:** Only blocks expose Self-contained; a line does not. Evidence: test_a_block_can_be_made_self_contained plus the Properties-panel tests.

- Show a concise function-help tooltip when hovering a function in the Functions panel or after entering it in a calculation line/block. Include the accepted argument count, argument names and purpose.
  - **Evidence:** Function help shows the signature and purpose on hover and after typing. Evidence: test_hovering_a_function_shows_its_signature_and_purpose, test_typing_a_function_shows_its_signature_and_purpose.

- Add rebindable shortcuts for left/centre/right alignment and font-size increase/decrease. They apply to selected text, a selected table cell, a whole calculation line, or a selected line within a calculation block, according to the active editor.
  - **Evidence:** Alignment and font-size shortcuts are rebindable and apply to the selected object, table cells, and a calculation line or active block line. Evidence: test_text_alignment_and_size_shortcuts_format_the_selected_object, test_alignment_and_size_shortcuts_format_the_selected_table_cells, test_shortcuts_format_a_calculation_line_and_the_active_block_line.

- Every command shortcut, including equation/text-entry triggers, must be visible and rebindable in the shortcut manager.
  - **Evidence:** _act registers every bound key in the shortcut manager (mainwindow.py:336-343). Evidence: test_repeat_along_an_axis_is_a_rebindable_shortcut, test_calibration_has_a_visible_rebindable_shortcut.

- New pages start uncalibrated. The first scale-dependent rectangle, ellipse or measurement prompts for page scale instead of assuming a scale.
  - **Evidence:** note_missing_scale (mainwindow.py:2811) says once that the page has no scale and points at the status-bar control, and the draw path calls it for a scale-dependent item (view.py:2825). NOTE: it keys off PageScale.is_calibrated, which task 155 shows is wrong for a genuine 1:1.

- A cloud callout's cloud and text box must be independently movable. Moving the box moves only the box; moving the cloud moves only the cloud; the leader geometry updates without moving the whole callout.
  - **Evidence:** The cloud and the call-out box move independently. Evidence: test_a_cloud_and_its_callout_box_move_independently.

- Arced segments on Arc items expose a control point comparable to other arced line segments.
  - **Evidence:** An arc exposes an editable bend control point. Evidence: test_an_arc_has_an_editable_bend_control_point.

- Pen and highlighter strokes snap only at their start/end points. Intermediate sampled points must not snap to grid or items, so freehand strokes stay smooth.
  - **Evidence:** Freehand snaps only its start and end. Evidence: test_freehand_snaps_only_its_start_and_end.

- Put **Add arrow leader**, **Add cloud leader**, and **Remove leader** directly in the main callout context menu. Adding a cloud leader adds only that cloud leader and lets the user choose its attachment position; remove the broad **Remove all leaders** command.
  - **Evidence:** Add arrow leader and Add cloud leader are on the call-out menu itself (mainwindow.py:4354/4357) and add only that leader.

- Fix modifier-drag behavior: Ctrl+drag duplicates; adding Shift before or after movement constrains the duplicate to 0/45/90 degrees; Shift-first then Ctrl switches from snap-constrained movement to duplication without leaving snapping in an inconsistent state.
  - **Evidence:** Modifier-drag is order-independent. Evidence: test_shift_first_then_ctrl_duplicates_and_keeps_the_move_constrained, test_ctrl_taken_hold_of_mid_move_switches_to_a_snapped_copy.

- Remove holes/gaps where overlapping highlighter strokes should form one continuous highlighted region.
  - **Evidence:** Overlapping highlighter strokes form one even band. Evidence: test_a_highlighter_stroke_is_one_even_band, test_the_highlight_goes_over_whatever_is_under_it.

- Snapshot must capture PDF vector linework and markups without carrying through the page background; it must not include unrelated calculation/table/text content unless those item types are explicitly selected for capture.
  - **Evidence:** A snapshot takes the drawing underneath without the page background and skips unselected worksheet content. Evidence: test_a_snapshot_takes_the_drawing_underneath_with_it, test_snapshot_skips_unselected_worksheet_content, test_a_snapshot_is_a_picture_of_the_region.

- Make the bottom canvas Snap control a dropdown that identifies and toggles the available targets, such as grid, PDF content and markups, rather than an ambiguous single button.
  - **Evidence:** The Snap control is a dropdown naming and toggling each target. Evidence: test_the_snap_dropdown_toggles_a_target_through_qt, test_the_snap_menu_entry_is_there_and_on.

- Centre the page number and page label within the page-view footer/navigation area.
  - **Evidence:** Page navigation and label are centred in the footer. Evidence: test_page_navigation_and_label_are_centred_in_the_footer.

- In the Pages panel, Ctrl+C/Ctrl+V copies and inserts pages with a visible insertion indicator. Support Ctrl and Shift multi-selection; Delete removes selected pages only after confirmation.
  - **Evidence:** Ctrl+C/Ctrl+V on the thumbnails copy and paste whole pages (ui/panels.py:266) with a drop indicator, and multi-selection acts as a run. Evidence: test_several_pages_are_copied_and_pasted_together, test_several_pages_are_deleted_together, test_the_pages_panel_takes_a_dropped_drawing.

- Remove the Typewriter markup tool and all related UI/shortcuts.
  - **Evidence:** Typewriter is gone from the menus and an old saved one still loads without exposing the tool. Evidence: test_the_markup_menu_omits_typewriter_but_keeps_the_other_tools, test_an_old_typewriter_item_still_loads_without_exposing_its_tool.

- Add a bottom-canvas scroll-mode control for continuous scrolling versus page-by-page viewing.
  - **Evidence:** The footer switches between continuous and page-by-page scrolling. Evidence: test_the_footer_switches_between_continuous_and_page_scrolling.

- Clicking a page-grid control must not move or reposition the page view.
  - **Evidence:** Clicking the page grid control does not move the view. Evidence: test_clicking_the_page_grid_does_not_move_the_view.

- While editing text, Ctrl+B/Ctrl+I/Ctrl+U format the selected text. Outside text/equation editing they retain their global commands; formatting keys must never insert a page or trigger unrelated commands.
  - **Evidence:** Ctrl+B/I/U format inside text and keep their global commands outside. Evidence: test_bold_italic_and_underline_belong_to_the_words, test_ctrl_b_emboldens_a_selected_text_box_rather_than_bookmarking, test_text_formatting_shortcuts_are_not_suppressed_while_typing.

- Show Pages-panel thumbnails centred within a grid layout.
  - **Evidence:** Thumbnails sit centred in a responsive grid cell. Evidence: test_page_thumbnail_uses_a_centred_responsive_grid_cell.

- Add a rebindable **Calibrate scale** shortcut. Calibration starts without an assumed `5 m` value, then opens a dedicated length-entry prompt after two points are selected; accept `10mm` and `10 mm`, and show a clear warning for invalid or incompatible units.
  - **Evidence:** Calibrate scale is a visible rebindable shortcut, and the length prompt takes joined or spaced units and rejects incompatible ones. Evidence: test_calibration_has_a_visible_rebindable_shortcut, test_the_calibration_length_prompt_accepts_joined_or_spaced_units, test_the_calibration_length_prompt_rejects_incompatible_units, test_the_scale_dialog_offers_picking_two_points_from_a_standing_start.

- Add recoverable document flattening: choose which content classes to flatten (markups, calculations, tables and other supported items), retain recovery data by default, support individual-item flattening, and offer a Preferences setting to disable recoverability when deliberately producing an irreversible file.
  - **Evidence:** Flattening is recoverable, selectable and preference-controlled, and survives a save. Evidence: test_flattening_takes_a_markup_out_of_reach, test_flattening_survives_a_save, test_preferences_exposes_recoverable_flattening, test_irreversible_flattening_keeps_only_a_vector_recording.

- I think the reason why zoom to curosr and zoom out to cursor is that currenlty the app cant pan off the page, therefore for example if the cursor in in the corner of th epage and i want to zoom to that but keep it central in the view its not possible to it doesnt zoom to thtat location, fix it (ability to pan off page)
  - **Evidence:** The canvas already extends past the pages: DocumentScene.set_desk_margin / _apply_desk_margin (ui/scene.py:642-651) grow the scene rect by a desk margin so any page edge can be centred, which is the pan-off-the-page the report asks for. Evidence: test_a_page_corner_can_be_centred_and_remains_under_zoom_cursor.

- add a functionaly in thr backend where a dependecnye tree is made for each variable, and when a varibale is redefonied, only these depennet lines/block/tabes are reevalted. clacluation must still work, this is just and efficiency thing
  - **Evidence:** A variable dependency graph exists and a redefinition recalculates only its chain. Evidence: test_a_redefined_variable_recalculates_only_its_dependency_chain, test_workspace_dependencies, test_prepare_formula_marks_dependencies.

- **(new)** Decide whether pasting from Excel can build a real table at all, and act on the decision. The §6 requirement to convert pasted Excel cells into a table object is to be withdrawn outright if it is not achievable — Excel may not reliably expose the data. Pasting as plain values is an acceptable outcome; if that is the conclusion, remove the conversion attempt entirely rather than leaving a half-working path in place.
  - **Evidence:** Decision made, with evidence: Excel paste CAN build a real table, so the §6 requirement is kept, not withdrawn. Pasting Excel cells creates a table object and carries relative formulas across, falling back to values where translation is impossible. Evidence: test_pasting_excel_cells_onto_the_page_makes_a_table, test_pasting_from_excel_brings_the_formulas, test_formulas_pasted_as_text_stay_formulas, test_excel_quoting_survives_the_trip, plus calcforge/core/excelxml.py.

- **(new)** "No scale" must be a different state from a true 1:1. The app currently treats 1:1 as the unset/default scale, so a page cannot actually be calibrated to a genuine 1:1 — a scale-dependent markup drawn afterwards still misbehaves. An explicit 1:1 calibration must be stored as a real, deliberate scale, distinct from "uncalibrated".
  - **Evidence:** Fixed. PageScale now carries its own `calibrated` flag instead of inferring it from the label (core/document.py), so a page deliberately set to 1:1 is a scaled page and one nobody touched is not. from_ratio and from_calibration set it; to_dict/from_dict persist it, and a document saved before the flag existed still reads its label the old way. Evidence: test_a_page_set_to_a_real_one_to_one_is_not_an_unscaled_page drives the real measure tool and checks the status hint, the save round trip, and both legacy-document cases; test_a_page_starts_without_a_scale_and_can_be_given_one still passes. Full suite 1255 passed, 0 failed.

- **(new)** Display formatting never alters stored values. Significant-figure and decimal-place settings affect only the rendered final answer — never the stored value, and never the typed equation text.
  - **Evidence:** Formatting is a render-time property of the item, not of the value: MathItem holds digits and number_format (items/mathitem.py:180-181) and applies them per line at layout through figures_for (mathitem.py:399); the workspace keeps the quantity. Evidence: test_one_line_can_be_shown_to_its_own_number_of_figures, test_a_lines_own_figures_can_be_put_back, test_a_lines_own_figures_survive_a_save.
