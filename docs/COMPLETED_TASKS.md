# MarkForge — evidence record

Audited: 2026-09-07 against `claude/markforge-mupdf-pdf-handling-vpyj1t`, with the suite green
and `tools/session_fuzz.py` clean over two hundred rounds. Re-checked the same
day by driving the running application and looking at it, which is where the
last section came from.

**This is not the completion record.** It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`; only the user marks a
requirement complete. What it says is narrower and checkable: *here is the code
that implements this, and here is the test that holds it*. Where something is
built but nothing holds it, this says so — an untested feature is a feature
that will break quietly.

Everything below was re-checked against the branch as it stands, not carried
over from an earlier audit. The previous version of this file described the
calculation-era application and has been replaced; if you want that history it
is in the git log.

---

## What a saved file is

- **A saved document is a PDF, and saving adds to it rather than rewriting it.**
  `io/pdfsave.py` writes an incremental update when the document is one source
  PDF and its markups: the bytes that came in are the first bytes of the file
  that goes out. Evidence:
  `test_saving_a_marked_up_drawing_leaves_the_drawing_byte_for_byte`,
  `test_an_updated_drawing_still_reads_as_a_pdf_everywhere`,
  `test_saving_twice_leaves_one_record_to_read_back`,
  `test_a_page_the_update_cannot_describe_is_assembled_instead`.
- **Anything that has to be painted is assembled instead**, by `io/pdfbase.py`
  — several sources, a dimmed page, a flattened markup, a running header or
  footer. The conditions are in `pdfsave.source_bytes`.
- **Every markup goes out as a real annotation**, with its own appearance
  stream, in the PDF's own vocabulary: a cloud as a `/Square` or `/Polygon`
  with a `/BE` cloudy border, a callout as a `/FreeText` with `/CL` and `/IT`,
  a dimension as a `/Line` with `/Measure`, `/LL`, `/LLE`, `/Cap` and its line
  endings. Evidence: `test_every_markup_goes_out_as_a_markup`,
  `test_an_exported_markup_is_not_also_painted_into_the_sheet`,
  `test_a_cloud_goes_out_as_a_cloud_not_a_drawing_of_one`,
  `test_a_dimension_keeps_every_part_the_specification_names`,
  `test_a_call_out_goes_out_with_its_leader`.
- **What a PDF cannot hold rides along** as an embedded record, and what
  decides how a file opens is what it holds rather than what it is called.
  Evidence: `test_a_saved_document_comes_back_exactly`,
  `test_a_saved_document_is_recognised_whatever_it_is_called`,
  `test_a_pdf_that_is_not_a_document_is_not_opened_as_one`,
  `test_documents_written_before_the_format_was_a_pdf_still_open`.
- **Bookmarks reach the exported PDF as its own outline**, and go in after the
  annotations without displacing them. Evidence:
  `test_bookmarks_still_work_when_the_markups_are_live`.

## The PDF engine

`markforge/pdf/` is a reader and writer written from the specification rather
than wrapped round somebody else's. Evidence: `tests/test_pdf_engine.py`, 24
tests, run against real files from other people's software rather than files of
its own making.

- Syntax, filters and predictors: Flate, LZW, ASCIIHex, ASCII85, RunLength,
  PNG and TIFF.
- Classic cross-reference tables, cross-reference streams and object streams.
- Recovery by scanning when the cross-reference table is wrong; refusal of a
  file that is not a PDF at all.
- Incremental update, verified byte-for-byte and cross-read with pypdf.
- The annotation model: border effects, callout lines, measure dictionaries,
  the ten line endings.

## Opening somebody else's drawing

- **A page comes in as its own line work**, not a picture of it, so it stays
  sharp at any zoom. Evidence: `test_an_imported_page_keeps_the_source_pdfs_own_page`,
  `test_the_lines_come_in_knowing_they_are_the_pages_own`.
- **Their markups come in as markups.** Evidence:
  `test_an_imported_pdf_brings_in_the_markups_somebody_else_made`,
  `test_a_marked_up_drawing_opens_as_markups_that_can_be_worked_with`,
  `test_a_cloud_is_a_border_effect_and_comes_back_as_one`,
  `test_a_link_is_not_somebody_s_markup`.
- **Opening a PDF is opening a document, not converting one**: Save writes it
  back. Evidence: `test_opening_a_pdf_is_opening_a_document_not_converting_one`.
- **The page's own line work is the page**, not a markup on it: locked, below
  everything drawn on it, written as part of the page, not copied by a
  snapshot, caught hold of but never offered as an alignment guide. Evidence:
  `test_the_pages_own_line_work_is_not_dragged_about`,
  `test_sending_to_the_back_stays_in_front_of_the_drawing`,
  `test_snapshot_skips_unselected_typing`.
- **Insert PDF asks no resolution question.** There is no answer to give:
  everything comes across as the file has it. `dialogs.PdfImportDialog` asks
  only which pages and what size of page.
- **A drawing can be dropped straight onto the pages panel**, at the row
  indicated. Evidence: `test_the_pages_panel_takes_a_dropped_drawing`,
  `test_a_dropped_pdf_is_imported_at_the_indicated_row`.

## Bluebeam tool sets

`.btx` import is held against the real files in `btx/`, not synthetic ones.
Evidence: `tests/test_btx.py`, 28 tests — `test_every_tool_set_reads_without_losing_a_tool`,
`test_the_sample_tool_sets_are_where_the_tests_expect_them`,
`test_importing_a_bluebeam_tool_set_fills_the_tool_chest`,
`test_a_dashed_line_from_a_toolset_comes_in_dashed`,
`test_bluebeams_spellings_of_a_hatch_all_land`,
`test_every_label_in_every_file_keeps_its_own_look`,
`test_a_file_that_is_not_a_tool_set_is_refused_politely`.

## Drawing and editing

- **Every tool draws both ways** — press and drag, or click and click — with
  the shape following the pointer between. Evidence:
  `test_a_click_placed_tool_shows_itself_before_it_lands`,
  `test_cloud_tool_supports_dragged_and_point_by_point_clouds`,
  `test_a_cloud_callout_can_be_drawn_corner_by_corner`.
- **Where a placed thing sits relative to the pointer**: a callout's box by its
  left middle, an image, snapshot, tool-set item or group by its bottom left.
  Evidence: `test_a_callouts_text_box_uses_the_pointers_left_middle`,
  `test_a_click_placed_image_hangs_from_the_pointers_bottom_left`,
  `test_an_exact_toolset_item_hangs_from_the_pointers_bottom_left`,
  `test_a_toolset_group_uses_its_combined_bottom_left_as_the_anchor`.
- **Shift holds a line to 0°, 45° or 90° in every tool**, freehand included.
  Evidence: `test_shift_holds_a_line_to_forty_five_degrees`,
  `test_the_highlighter_goes_straight_on_shift_too`.
- **Shift and click point after point lassoes a selection.** Evidence:
  `test_shift_clicking_out_a_lasso_selects_what_is_inside_it`,
  `test_a_lasso_takes_only_what_is_wholly_inside`,
  `test_escape_abandons_a_half_drawn_lasso`.
- **Escape goes all the way back in one press.** Evidence:
  `test_escape_abandons_a_click_started_drawing`,
  `test_escape_abandons_a_half_drawn_callout`,
  `test_escape_cancels_an_unplaced_cloud_leader`,
  `test_escape_puts_the_format_painter_down`,
  `test_escape_cancels_a_group_resize_and_restores_the_cursor`.
- **Cursors say what the gesture will do, and revert when it ends.** Evidence:
  `test_hovering_a_markup_changes_the_cursor`,
  `test_finishing_a_rectangle_resize_recomputes_the_cursor`,
  `test_shape_modifiers_have_distinct_add_remove_and_curve_cursors`.
- **Rounded corners and arcs**, on the right-click menu, with live preview
  during the drag. Evidence: `test_ctrl_over_a_side_bends_it_into_an_arc`,
  `test_the_arc_handles_bend_and_lean_the_curve`,
  `test_an_arc_has_an_editable_bend_control_point`,
  `test_a_rounded_corner_preview_updates_during_a_real_handle_drag`,
  `test_an_arc_preview_updates_during_a_real_handle_drag`.
- **The structural break symbol**, on any side. Evidence:
  `test_a_break_symbol_goes_on_a_side_and_comes_off`.
- **A rectangle becomes a polygon** when it stops being a rectangle.
  `MainWindow.rectangle_to_polygon`, exercised in `tests/test_usability.py`.
- **Modifier drags are order-independent.** Evidence:
  `test_shift_first_then_ctrl_duplicates_and_keeps_the_move_constrained`,
  `test_a_ctrl_click_does_not_copy_anything`.
- **Images and groups keep their aspect ratio unless Shift releases it.**
  Evidence: `test_an_image_keeps_its_aspect_ratio_unless_shift_releases_it`.
- **Ordering**: bring front, send back, forward, backward, with the page's own
  line work as the floor. Evidence:
  `test_order_moves_a_markup_in_front_of_and_behind_the_others`,
  `test_sending_to_the_back_stays_in_front_of_the_drawing`,
  `test_a_new_markup_lands_on_top_of_the_ones_already_there`.

## Callouts and text

- **A text box, a callout and a cloud callout are one object in three states**,
  and the leader is what moves between them. Evidence:
  `test_a_callout_can_have_as_many_leaders_as_you_like`,
  `test_a_cloud_callout_is_offered_more_leaders_of_either_kind`,
  `test_a_leader_survives_a_round_trip_with_its_side_and_reach`,
  `test_a_call_out_keeps_its_knee`.
- **The hinge is computed, never stored**, so it stays perpendicular and
  automatic. Evidence: `test_the_leader_leaves_the_middle_of_a_side`,
  `test_resizing_a_callout_leaves_the_arrow_where_it_points`,
  `test_a_callout_leader_keeps_pointing_at_the_same_place_during_upright_edit`.
- **The cloud is there from the first click**, and cloud and box move
  independently. Evidence:
  `test_placing_a_cloud_leader_shows_a_cloud_on_the_pointer`,
  `test_a_cloud_and_its_callout_box_move_independently`,
  `test_add_cloud_leader_uses_the_region_dragged_on_the_canvas`.
- **A rotated text markup turns upright to be edited and snaps back.**
  Evidence: `test_a_rotated_text_box_turns_upright_only_while_it_is_edited`,
  `test_an_almost_unrotated_text_box_snaps_back_to_zero_after_editing`.
- **The rotation grip stays inside the item.** Evidence:
  `test_the_rotation_grip_is_inside_the_item_it_belongs_to`.
- **Typing lands where it was aimed.** Evidence:
  `test_typing_after_a_click_lands_where_the_caret_is`,
  `test_a_click_does_not_snap_back_to_the_start`,
  `test_a_double_click_lands_where_it_was_aimed`,
  `test_a_double_click_in_the_words_takes_the_word_it_was_aimed_at`,
  `test_backspace_edits_text_rather_than_deleting_the_markup`,
  `test_undo_takes_back_the_typing_before_the_markup_itself`,
  `test_saving_settles_the_markup_being_typed`.
- **The Typewriter tool is gone**, and an old document holding one still opens.
  Evidence: `test_the_markup_menu_omits_typewriter_but_keeps_the_other_tools`,
  `test_an_old_typewriter_item_still_loads_without_exposing_its_tool`.

## Measuring and take-off

- **Scale is per page, optional, and calibratable.** Evidence:
  `test_a_page_starts_without_a_scale_and_can_be_given_one`,
  `test_a_scale_turns_the_paper_size_into_a_real_one`,
  `test_a_calibration_line_is_not_left_on_the_page`,
  `test_a_page_set_to_a_real_one_to_one_is_not_an_unscaled_page`,
  `test_the_first_scaled_tool_click_prompts_before_drawing`,
  `test_cancelling_the_first_scale_prompt_does_not_create_a_markup`.
- **A measurement carries the scale it was taken against**, into the file.
  Evidence: `test_a_measurement_carries_the_scale_it_was_taken_against`,
  `test_a_take_off_carries_the_scale_it_was_measured_against`,
  `test_a_measurement_prints_the_dimension_it_reads`.
- **The dimension tool draws plainly, with its value on the line and a control
  dot.** Evidence: `test_a_dimension_is_drawn_plainly_with_its_value_on_the_line`,
  `test_a_dimensions_value_carries_a_control_dot`,
  `test_a_dimensions_text_lies_along_its_line`,
  `test_a_dimension_carries_its_own_text`,
  `test_a_dimensions_value_holds_still_while_its_text_is_turned`.
- **Cut-outs belong to any closed shape**, and come off the area. Evidence:
  `test_a_cut_out_belongs_to_any_closed_shape`,
  `test_a_cut_out_drawn_nowhere_says_so`,
  `test_an_open_polyline_is_not_offered_as_somewhere_to_put_a_hole`.
- **The takeoff list follows the scale.** Evidence:
  `test_changing_the_page_scale_updates_the_takeoff_list`.
- **Count markers show their whole number.** Evidence:
  `test_a_count_marker_shows_its_whole_number_at_any_size`.

## Snapping

- **Three sources with their own switches**, plus alignment guides and
  crossings. Evidence: `test_the_first_point_of_a_line_shows_the_snap_marker`,
  `test_the_middle_of_a_polygon_side_can_be_caught`,
  `test_a_corner_can_land_on_a_markup_while_drawing_the_polygon`,
  `test_holding_ctrl_lets_go_of_the_grid_while_drawing`,
  `test_ctrl_lets_go_of_the_grid_for_a_calibration_too`,
  `test_freehand_snaps_only_its_start_and_end`.
- **Where two lines cross.** Evidence:
  `test_the_pointer_catches_where_two_lines_cross`,
  `test_lines_that_stop_short_of_each_other_do_not_cross`,
  `test_a_corner_still_beats_a_crossing_that_is_further_away`,
  `test_crossings_are_left_alone_when_snapping_is_switched_off`.
- **Guides are transient**, and the marker is a blue target rather than an
  orange square. Evidence: `test_snap_guides_clear_when_the_pointer_leaves`,
  `test_snap_guides_clear_on_tool_change_and_escape`,
  `test_snap_guides_clear_when_the_point_is_committed`,
  `test_snap_feedback_is_a_blue_target_not_an_orange_square`.

## Pages, panels and the window

- **One continuous canvas**, and a gesture aimed at the page under it.
  Evidence: `tests/test_canvas.py`, 38 tests.
- **Pages panel**: multi-selection, reorder, exclude from print, rename and
  reset a label, centred thumbnails. Evidence:
  `test_a_page_excluded_from_print_is_grey_and_is_not_exported`,
  `test_a_page_label_can_be_renamed_and_reset_from_its_menu`,
  `test_page_thumbnail_uses_a_centred_responsive_grid_cell`,
  `test_a_wrapping_page_grid_uses_left_and_right_for_the_drop_slot`,
  `test_page_navigation_and_label_are_centred_in_the_footer`.
- **One panel open per side**, from the rail and from the View menu. Evidence:
  `test_rail_click_keeps_one_panel_open_per_side`,
  `test_view_menu_panel_toggle_obeys_the_same_side_limit`.
- **The arrangement comes back**: pinning, floating, hiding, rolling up.
  Evidence: `tests/test_layout.py`, 35 tests.
- **Two documents in tabs, and a second window**, neither reaching into the
  other. Evidence: `test_two_documents_open_in_tabs_without_reaching_into_each_other`,
  `test_a_second_window_keeps_its_own_document`.
- **Every action is reachable from the menu bar**, and every tool from the
  toolbar. Evidence: `test_every_tool_and_application_action_is_reachable_from_the_menu_bar`,
  `test_every_markup_tool_is_reachable_from_the_toolbar`,
  `test_current_page_commands_are_reachable_from_the_menu_bar`.
- **Every key the application answers to is in the shortcut list**, rebindable,
  and silent while typing. Evidence:
  `test_every_key_the_application_answers_to_is_in_the_shortcut_list`,
  `test_a_changed_shortcut_reaches_the_action_and_the_canvas`,
  `test_a_bare_letter_types_rather_than_picking_a_tool`,
  `test_letter_keys_pick_their_tool`,
  `test_ctrl_b_emboldens_a_selected_text_box_rather_than_bookmarking`,
  `test_ctrl_b_still_bookmarks_when_there_are_no_words`.
- **The markups list and the drawing show the same selection.** Evidence:
  `test_picking_a_row_picks_the_markup_and_the_other_way_round`.

## Tool sets and defaults

- **My Tools, the number keys, and tool sets remembered between documents.**
  Evidence: `test_my_tools_is_always_there`, `test_my_tools_are_numbered_in_the_panel`,
  `test_the_number_keys_reach_for_my_tools`,
  `test_tool_sets_are_remembered_between_sessions`,
  `test_tool_sets_can_be_made_renamed_and_deleted`,
  `test_a_markup_can_be_saved_to_a_tool_set_from_its_context_menu`,
  `test_a_group_goes_into_a_tool_set_as_one_thing`,
  `test_a_tool_set_entry_is_drawn_as_what_it_is`.
- **Properties mode places a new one wearing the stored style.** Evidence:
  `test_a_tool_in_properties_mode_draws_a_new_one`.
- **Defaults are per kind, remembered, forgettable, and settable from the style
  toolbar as well as the panel.** Evidence:
  `test_a_default_belongs_to_that_kind_of_markup_only`,
  `test_a_default_is_remembered_between_sessions`,
  `test_a_default_can_be_forgotten`,
  `test_a_default_never_carries_the_contents_across`,
  `test_the_style_toolbar_sets_the_selected_markup_as_default`.

## Format painter

Evidence: `test_the_format_painter_carries_one_markups_look_to_another`,
`test_clicking_with_the_format_painter_paints_that_markup`,
`test_format_painter_never_copies_cloud_geometry`,
`test_format_painter_does_not_copy_callout_leaders`,
`test_the_format_painter_carries_a_brush`,
`test_escape_puts_the_format_painter_down`.

## Properties and the style toolbar

- **Both are selection-aware and agree with each other**, for every tool.
  Evidence: `test_the_style_toolbar_and_the_properties_panel_agree`,
  `test_style_toolbar_tracks_real_selection_and_the_active_tool`,
  `test_an_image_does_not_get_shape_style_controls`,
  `test_a_raster_image_has_no_line_or_fill_style_controls`,
  `test_a_photos_own_border_is_not_offered_but_its_default_is`,
  `test_a_snapshot_and_a_photo_have_a_line_type_of_their_own`.
- **Line styles and hatches show a real preview.** Evidence:
  `test_line_and_hatch_choices_have_real_pattern_previews`.
- **One name per idea, and short labels.** Evidence:
  `test_one_idea_has_one_name_in_the_properties_panel`.

## Snapshots and images

Evidence: `test_a_snapshot_is_a_picture_of_the_region`,
`test_a_snapshot_pastes_back_as_one_thing`,
`test_a_snapshot_scaled_up_is_still_drawn_from_its_lines`,
`test_a_snapshot_has_a_border_that_starts_at_none_and_can_be_set`,
`test_a_snapshot_is_borderless_when_it_comes_back`,
`test_snapshot_skips_unselected_typing`,
`test_the_snapshot_marquee_looks_like_the_selection_marquee`,
`test_an_image_can_be_swapped_for_another`,
`test_a_cancelled_image_insert_changes_nothing`,
`test_a_colour_can_be_made_transparent_within_a_tolerance`,
`test_recolouring_a_page_can_be_undone`,
`test_a_blank_page_says_there_is_nothing_to_recolour`.

## Flattening and redaction

Evidence: `test_flattened_content_stays_part_of_the_sheet`,
`test_flattened_markup_lets_the_pointer_through_to_what_is_behind`,
`test_irreversible_flattening_keeps_only_a_vector_recording`,
`test_document_flattening_uses_the_classes_chosen`,
`test_flatten_dialog_class_choices_follow_real_clicks`, and the redaction tests
in `tests/test_app.py`.

## Spelling

Evidence: `test_spellcheck_knows_requests_and_offers_a_correction`.

---

## Found by walking the application

The audit above reads the code and the tests. This section is what came of
opening the window, drawing one of everything, opening a drawing, marking it
up and looking at the result, and from a fuzz run. Six bugs, all now fixed
and held.

- **The footer drew three things on top of one another.** The page navigation
  was parented to the status bar, moved to the middle and raised, so on a
  marked-up drawing the bottom of the window read
  "of 140.9, 246.8 mm drawing.pdf page 1" — the page count, the cursor
  position and the page label in one place. It is in the layout now, between
  two stretches, and nothing in a layout can overlap anything else. Evidence:
  `test_nothing_in_the_footer_is_drawn_on_top_of_anything_else`,
  `test_page_navigation_and_label_are_centred_in_the_footer`.
- **`Ctrl+I` inserted a PDF.** The requirement says Ctrl+B/I/U must never
  insert a page. Ctrl+I was Insert PDF's shortcut, and the cause was the rule
  meant to protect those keys: they were kept *out* of the shortcut list so
  nothing could take them, and let through while typing so that whatever had
  taken them anyway fired anyway. A key the application answers to that cannot
  be seen or changed is a key nobody knows about.
  Both halves are fixed. They are ordinary bindings in the list now — visible,
  rebindable, and holding italic, underline and bookmark; and while words are
  being typed *no* binding fires, whatever is on it, because the view takes
  the key and formats the words instead. The editor has no handling of its own
  for these three, so suppressing the shortcut alone would have left Ctrl+B
  doing nothing at all. Insert PDF is on `Ctrl+Shift+I`. Evidence:
  `test_ctrl_i_italicises_rather_than_inserting_a_pdf`,
  `test_bold_italic_and_underline_are_in_the_shortcut_list`,
  `test_no_command_fires_from_ctrl_b_i_or_u_while_typing`,
  `test_ctrl_b_i_and_u_format_the_words_being_typed`,
  `test_a_key_bound_over_ctrl_b_still_does_not_fire_while_typing`,
  `test_italic_and_underline_reach_the_markup_that_is_picked`,
  `test_italic_and_underline_reach_only_the_run_picked_out`.
- **A right click did not close a shape being clicked out**, though the cloud
  tool's own tooltip promises "Enter or a right-click closes it". It opened a
  context menu over the half-drawn shape. Evidence:
  `test_a_right_click_closes_a_shape_being_clicked_out`,
  `test_a_right_click_closes_a_lasso_being_clicked_out`.
- **The style toolbar was an empty band with one stranded button.** With
  nothing selected and the Select tool held, every control on it is hidden and
  what was left was a full row of chrome carrying a disabled "Set default". It
  goes until there is something to put on it. Evidence:
  `test_the_style_toolbar_goes_when_it_has_nothing_to_offer`.
- **An unrecognised unit raised out of a Qt slot.** Found by the fuzzer typing
  "lc" into the exact-size box: `parse_unit` let pint's own `UndefinedUnitError`
  escape, and an exception raised inside a Qt override is not an error message,
  it is a crash a few events later. It returns None now, which is what every
  caller already reads as "that is not a length". Evidence:
  `test_a_size_typed_in_a_unit_nobody_knows_is_refused_not_raised`.
- **Four labels were sentences, and one of them made the Properties panel
  wider than the dock it lives in** — "Write the measurement on the page" as a
  checkbox pushed the panel's minimum width to 335 against a 320-wide dock, so
  a measurement's properties opened with a horizontal scrollbar. They are
  "Show value", "Show size", "Inline text" and "Print" now, with the sentence
  in the tooltip, and the minimum is 276. Evidence:
  `test_every_label_the_user_reads_is_one_or_two_words`.

## Corrected by this audit

Four things an earlier pass called missing, which the code and now a test show
are built. They are here so the record does not go on being wrong about them.

- **Property mode is greyed out for what cannot use it**, with a tooltip
  saying why. Evidence: `test_property_mode_is_greyed_out_for_what_cannot_use_it`.
- **A rectangle takes a point in or out** from its own right-click menu, and
  becomes a polygon by doing it rather than by a separate command. Evidence:
  `test_a_rectangle_takes_a_point_in_or_out_and_becomes_a_polygon`.
- **Turning the grid switch off stops grid snapping.** Reported as not
  respected; measured as respected. Evidence:
  `test_the_grid_switch_actually_stops_grid_snapping`.
- **Groups scale as one object**, Shift releasing the ratio. Evidence:
  `test_a_group_scales_as_one_and_shift_releases_its_ratio`.

## Built, and now held

Four things the first audit listed as real but untested. Each has a test now.

- **The page scale beside the page number in the pages panel**, and nothing
  said for an unscaled page. Evidence:
  `test_the_page_scale_is_shown_beside_the_page_in_the_panel`.
- **Contents-block lines as working links in the exported PDF**, one `/Link`
  per line, each with a destination. Evidence:
  `test_a_contents_line_is_a_working_link_in_the_exported_pdf`.
- **The scrollbars while the view is turned**: no rotation in the view's
  transform, and the vertical bar still runs down the document. Evidence:
  `test_turning_the_view_leaves_the_scrollbars_the_way_they_scroll`.
- **Where pasted pages landed**, said the way a drop says it — the slot line
  at the landing place and the pages picked out. Evidence:
  `test_pasting_a_page_says_where_it_landed`.

## Built, but nothing holds it

- **The `.btx` sketch-tool fidelity repair.** The tool sets load and every tool
  in them reads, but nothing compares an imported structural symbol against
  what Bluebeam draws — see `docs/UNADDRESSED_TASKS.md`.

---

## Evidence added 2026-09-10

This is implementation and validation evidence only. The completion cells in
`tasklist.md` and `tasklist.xlsx` remain user-owned and were not changed.

- **Persistent Format Painter:** remains armed for repeated targets and exits
  on Escape or another tool. Existing interaction evidence:
  `test_format_painter_stays_armed_until_escape` and
  `test_format_painter_stops_when_another_tool_is_chosen`.
- **Independent arrowhead and dimension-text sizes:** `Style.arrow_size` is
  persisted and used by line, callout and dimension arrow rendering. Both the
  style toolbar and Properties expose it; measurement text size is separately
  editable. Evidence:
  `test_arrowhead_size_is_independent_in_properties_and_toolbar` and
  `test_dimension_text_size_is_editable_in_properties`.
- **No phantom toolbar menu rows:** both panel rails now have real Qt object
  titles, so the toolbar visibility menu contains named entries rather than
  blank checked slots. Evidence: `test_toolbar_popup_has_no_blank_phantom_entries`.
- **Drawing and leader cursors:** active line, rectangle, ellipse and other
  drawing gestures now carry the selected tool beside a precise crosshair;
  arrow- and cloud-leader placement have their own drawn affordances and both
  return to the ordinary cursor on Escape. The existing `_TextBase` context
  path makes both leader kinds available consistently to every text markup
  capable of carrying a leader. Evidence:
  `test_active_drawing_gestures_carry_their_tool_on_the_cursor`,
  `test_placing_a_cloud_leader_shows_a_cloud_on_the_pointer`, and the leader
  context-menu tests in `tests/test_usability.py`.
- **Finer canvas scrolling:** wheel scrolling uses smaller 30-pixel steps while
  native pixel/trackpad deltas remain continuous. Evidence:
  `test_wheel_scrolls_the_canvas_in_small_steps` and the canvas wheel tests.
- **Multiple:** the offset-copy command and dialog are now consistently named
  `Multiple`, retain the rebindable `Ctrl+Shift+D` command, and keep explanatory
  text in tooltips. Evidence: `test_multiple_has_a_working_shortcut` and
  `test_every_label_the_user_reads_is_one_or_two_words`.
- **Same-document views and windows:** a tab context menu opens the same live
  document in a second tab or window, with independent viewport state and a
  shared document/undo history. Tabs dragged outside the bar tear into a window.
  The bottom-right control offers Page sync (zoom and relative viewport only)
  and Document sync (page, zoom and viewport). Evidence:
  `test_a_tab_can_open_a_second_view_of_the_same_document`,
  `test_a_document_tab_can_be_torn_into_a_window`, and
  `test_same_document_windows_can_sync_by_page_or_document`.
- **Section-specific headers and footers:** Document Properties now accepts
  page-range rows with their own header/footer visibility and six text slots.
  Sections persist in the document and are used by both rendering and PDF
  export. Evidence: `test_the_header_footer_manager_accepts_page_sections` and
  `test_header_and_footer_wording_can_vary_by_page_section`.
- **Cutouts after host resize:** saved holes are intersected with the host's
  current outline for painting, fill subtraction and measured area, including
  curved polygon and exact ellipse outlines. Evidence:
  `test_cutouts_are_reclipped_when_the_host_is_resized`.
- **Cross-platform test isolation:** application settings now honour the
  explicit `MARKFORGE_SETTINGS_FILE` test path on macOS as well as Linux, so a
  run cannot read or overwrite the user's real preferences. The NZ spelling
  dictionary is also preferred before a generic system dictionary, retaining
  `colour` while covering ordinary words such as `requests`.
- **Session fuzz validation:** `python3 tools/session_fuzz.py 41 300` completed
  300 randomised UI rounds across two pages and 20 markups with zero failures.

- **Cloud drawing and callout completion:** one Cloud tool supports both the
  dragged rectangular form and the point-by-point Cloud+ form. Enter and
  right-click both close a point-by-point cloud; for a cloud callout either
  gesture proceeds to placement of its text box. Evidence:
  `test_cloud_tool_supports_dragged_and_point_by_point_clouds`,
  `test_a_cloud_callout_can_be_drawn_corner_by_corner`, and
  `test_a_right_click_finishes_the_cloud_before_placing_its_callout`.
- **Format Painter roller:** the persistent Format Painter now uses an
  independently drawn paint-roller icon rather than the earlier brush drawing,
  without copying another application's artwork. Evidence:
  `test_the_format_painter_carries_a_paint_roller`.
- **Previously stale unaddressed entries:** Insert PDF retains the source PDF
  and vector linework; Escape restores the ordinary cursor even with no
  selection; every visible tool entry is backed by a selectable tool; the
  rectangle/ellipse size editor is screen-aligned; and flattening is a menu
  command rather than a cursor tool. The removed fading markup label is absent.
  Evidence: `test_an_imported_page_keeps_the_source_pdfs_own_page`,
  `test_escape_cancels_a_group_resize_and_restores_the_cursor`,
  `test_every_markup_tool_is_reachable_from_the_toolbar`,
  `test_the_size_entry_stays_upright_whichever_way_the_page_is_turned`, and the
  flattening tests in `tests/test_usability.py`.
- **Snapshot recolouring:** snapshots retain serialised source linework beside
  their `QPicture`, recolour that source, and rebuild a vector recording rather
  than rasterising it. Evidence: `test_a_snapshots_colours_can_be_changed`.
- **Even crossing highlights:** highlighter bands use an opaque marker colour
  in Darken composition, retaining darker drawing content while preventing a
  separately drawn crossing from darkening the first stroke again. Evidence:
  `test_crossing_highlighters_are_one_even_wash`.
