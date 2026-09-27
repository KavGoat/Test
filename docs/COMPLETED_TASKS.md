# MarkForge — evidence record

Previous entries were deleted at the user's request on 2026-09-27. Evidence for
the 2026-09-27 report is recorded below. Completion status stays user-owned.

## 2026-09-27 report — implementation evidence

Full offscreen Qt suite (`QT_QPA_PLATFORM=offscreen python -m pytest`) was run
after the changes; the final result is at the end of this section.

| Report | What was wrong | What changed | Evidence |
| --- | --- | --- | --- |
| Snapshot marquee copies the last rectangle | The Snapshot/Whiteout region is a `RectItem` and went through `apply_default_style`, so it wore the toolbar pen and any saved rectangle default. | The region skips markup styling and paints as the selection marquee, dashed, one pixel wide at any zoom. | `test_the_snapshot_marquee_is_not_the_last_rectangle_drawn` |
| Revit PDF red cross | Not reproduced: nothing in the application draws a red cross over page content. | None yet — see `UNADDRESSED_TASKS.md`. | — |
| Scale unit does not update dimensions | `apply_scale_change` refreshed the label and lists but never re-read the measurements. | Every measurement and sized shape on the page is refreshed when the scale, unit or area unit changes. | `test_changing_the_scale_unit_updates_existing_dimensions` |
| Area / radius / diameter look like a title box | Non-dimension values were drawn in a rounded box with a tail line to the anchor. | All measurement values are plain text like a dimension's and are moved by dragging the text. | Visual check; existing label-drag tests |
| Diameter reports the radius | The tool is drawn edge to edge but was treated as centre-to-edge. | A diameter reports the drawn length; its circle is centred on the midpoint. | `test_a_diameter_reports_what_was_drawn_across_the_circle` |
| Align snap needs markup and PDF options | Alignment only used markups. | **Align markups** and **Align PDF** in the Snap dropdown and View menu; PDF guides bisect sorted vertex coordinates. | `test_align_to_pdf_lines_up_with_the_drawing`, `test_the_snaps_are_on_the_view_menu` |
| Closing a split tab keeps the split; cannot turn split off | Closing the last tab made a blank document; Split view did nothing when already split. | Split view is a toggle; closing a pane's last tab turns the split off; the other pane's documents move over as tabs. | `test_closing_a_split_panes_tab_turns_the_split_off`, `test_split_view_action_turns_the_split_off` |
| Faded linework when zoomed out | Tiles were rendered at up to 2× the screen resolution and shrunk, and sub-pixel hairlines were anti-aliased to grey. | Hairlines rasterise at least one pixel wide (`engine.MIN_LINE_PIXELS`); tile rungs are a quarter-doubling apart. | `test_zoomed_out_hairlines_are_not_faded` |
| Speed: use more RAM and CPU | Fixed 192 MB tile cache, 4 render workers, 6 parsed pages. | Tile cache is 1/8 of RAM (192 MB–2 GB), sheet cache scales with it, workers = cores − 1 (max 8), 24 parsed pages held. | Suite; `test_pdf_parallel.py` |
| Callout / Cloud / Cloud+ cursors | Only DRAG/POLY/FREE tools had drawing cursors. | Cloud and Cloud+ carry the cloud cursor; callouts, notes, stamps and the snapshot carry a crosshair with their icon; Cloud+ switches to the callout cursor once the cloud is drawn. | `test_every_drawing_tool_has_a_drawing_cursor` |
| Hatch colour separate from fill; unbounded scale; spin arrows | Hatch was drawn in the fill colour with no fill beneath; scale capped at 100; styled spin boxes lost their arrows. | `Style.hatch_color`; the fill is solid, the hatch is antialiased linework over it; scale has no upper limit; spin boxes draw arrow images. Old styles are converted on load. | `test_a_hatched_fill_is_not_a_flat_one`, `test_old_hatches_keep_their_look_when_loaded`, `test_hatch_scale_controls_and_undo`; screenshot of the spin box |
| Spell check not working | The underline was Qt's font-sized dotted line, invisible at normal zoom, and there was no spell-check command. | A red wave drawn in screen pixels; **Add word** in the correction menu (remembered); **Markup ▸ Check spelling… (F7)** steps through every text markup. | `test_the_spellcheck_squiggle...`, `test_check_spelling_walks_every_text_markup` |
| Find should be a live dropdown | Find tool was a modal input dialog. | A search field in the menu bar lists matching tools, commands, pages and markups as you type; Enter or a click runs the pick. Shift+F1 focuses it. | `test_finding_a_tool_picks_it_up`, `test_search_lists_commands_and_markups_too` |
| Format Painter brush cursor | The brush was set once and replaced by hover cursors. | The brush stays while a format is held, over markups too. | `test_format_painter_keeps_the_brush_over_markups` |
| Snapshot black / thick in other viewers | Three faults: the screen recording was replayed into Qt's PDF writer, which rescaled its transforms; MuPDF's unit-sized glyph outlines lost precision; Qt's SVG renderer stroked fill-only glyphs. | PDF/print output paints the kept vector source; glyphs are written in page coordinates with an invisible stroke. Existing snapshots are normalised on load. | `test_exported_text_snapshot_matches_its_source_in_another_viewer` (rendered by MuPDF) |
| Bluebeam rectangle/ellipse tooltip | A white two-field entry appeared only after a click, only on calibrated pages. | A dark bar with Width, Height and Rotation beside the dragged corner, for drags and clicks. The live width is selected, typing holds a value, Tab moves on, Enter places it. | `test_size_bar_matches_bluebeam_width_tab_height_enter`; screenshot compared with the reference video |

**Final suite: 952 passed, 0 failed** (offscreen Qt, Linux, PySide6 6.11,
387 s). Screenshots of the size bar, search dropdown, spin-box arrows, plain
measurement labels and a MuPDF render of an exported text snapshot were
inspected. Not yet checked on Windows or in Bluebeam itself.

## 2026-09-27 follow-up — page lines softer than a pasted snapshot

Tiles were rendered on a ladder of resolutions above the screen's and drawn
at fractional pixel positions, so Qt shrank and smoothed every tile; a
snapshot is drawn as vectors at exactly screen resolution. Tiles are now
rendered at the zoom on screen (`pdftiles.zoom_step`, four significant
figures) and drawn snapped to whole device pixels without smoothing when the
size matches (`scene._draw_on_the_pixel_grid`). Before/after screenshots at
62 % zoom were compared. Evidence:
`test_page_tiles_land_on_whole_pixels_without_resampling`. Full suite:
953 passed.
