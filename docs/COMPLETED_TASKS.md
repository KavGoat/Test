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

## 2026-09-27 second follow-up

- **Snapshot dots in the app only:** the app replayed the recording made at
  capture time, while the export (which the user says is right) painted the
  kept vector source. The app now paints the kept source too, cached at
  screen resolution per zoom (`DeviceCoordinateCache`). The dots were not
  reproduced with `btx/Document1.pdf`; confirmation needs the user's file.
- **Size dialog after placing:** `prompt_rectangle_size` no longer runs when
  a rectangle or ellipse is placed; **Exact size…** stays on the right-click
  menu. `test_no_size_dialog_pops_up_once_a_rectangle_is_placed`.
- **Blurry hatch at large scale:** the hatch was a picture tile, magnified.
  It is now drawn as lines clipped to the shape (`base.paint_hatch`) for
  rectangles, ellipses, clouds, polygons, stamps and count markers. It is
  vector in exports too. `test_a_hatched_fill_is_not_a_flat_one` checks a
  crisp line at a hatch scale of 1000 and of 12.

Full suite: 953 passed.

## 2026-09-27 — Sketch Tools against Bluebeam's own drawing

Each Sketch Tools tool was rendered and overlaid on Bluebeam's appearance of
the same annotations in `btx/Document1.pdf` (ink overlap after alignment):

| Tool | Before | After | What was wrong |
| --- | --- | --- | --- |
| Elevation / Section / Detail Label | 0.92–0.94 | 0.92–0.94 | Already one to one; part positions match to 0.01 pt |
| Titleblock | 0.28 | 0.83 | The stamp form's `/Matrix` was applied twice, so logo, labels and dividers were drawn about 2× too big |
| Legend | 0.46 | 0.67 | `line-height` was dropped (Qt treats it as a minimum), so every line drifted 0.5 pt lower |
| Drawing / Detail Title | 0.49–0.57 | 0.54–0.56 | Second line used the paragraph's 18.4 pt instead of its span's 13.8 pt; first baseline 1.8 pt low; text 1 pt left; Qt kerning made titles 1 pt narrow |

Per text box, the remaining difference is under ~0.5 pt, which is the glyph
difference between Helvetica and the fallback font here. Fractional font sizes are still rounded to
whole pixels (10.87 pt → 11), about 1 % wider. Evidence:
`test_sketch_tools_match_bluebeams_own_drawing`,
`test_bluebeam_line_spacing_is_exact`. Full suite: 958 passed.

## 2026-09-27 — infinite hatch scale

Both hatch-scale boxes are `UnboundedSpin` (1e-12 to 1e15, shown compactly,
arrows step by 10 %). Drawing no longer spreads lines out past 4 000 lines:
beyond that density the hatch is an even tint of its colour at the coverage
the lines would give, so every scale typed is honoured.
`test_hatch_scale_has_no_practical_limit`. Full suite: 959 passed.

## 2026-09-28 — the add list from the Bluebeam comparison, and follow-ups

- **A1 exact fractional font sizes:** text keeps its point size in the
  document and is laid out with `FontPixelSize` plus a percentage letter
  spacing that makes up the fraction, so 10.87 pt stays 10.87 pt
  (`text.exact_sizes`). `test_btx.py` reference-overlap tests.
- **A2 stamp artwork as linework:** tool-set stamps come across as SVG
  linework (`btx._stamp_svg`, `base.paint_stamp_drawing`), sharp at any zoom.
- **Markups list (in place of C7):** columns Page, Type, Subject, Colour,
  Fill, Line, Width, Opacity, Font, Size, Value, Author, Date, Comment;
  group by page/type/subject/colour/author; filter by right-clicking a
  column header; multi-select to recolour, restyle, lock, hide or delete as
  one undo step. It lives only under the drawing on a drag bar: drag up to
  open, down to close, or View > Markups list (Alt+L); its height is
  remembered. `test_markups_list_filters_sorts_and_changes_several_at_once`,
  `test_the_markups_list_lives_under_the_drawing`.
- **C2 search and replace:** Search panel (Ctrl+F, rail icon) finds words in
  the PDF's own text and in markup text on every page, lists each hit, and
  replaces in markups (one undo step).
  `test_search_finds_drawing_and_markup_text_and_replaces_in_markups`,
  `test_ctrl_f_opens_the_search_panel`.
- **C4 crop / C5 extract and split:** Crop tool and Page > Crop page set the
  PDF's CropBox (Undo restores); Page > Extract pages and Split pages save
  pages with their markups. `test_crop_keeps_the_dragged_part_and_undo_restores_it`,
  `test_extract_and_split_save_pages_with_their_markups`.
- **B6 link tool:** a region that goes to a page, a view, a file or a web
  address; a real PDF link on export.
  `test_a_link_goes_to_a_page_and_is_a_real_link_in_the_pdf`.
- **B8 hatch and line-style library:** 33 named hatches (brick, earth,
  concrete, insulation, …) drawn as linework, and more line styles. Hatch is
  drawn behind the outline. Line-style and hatch pickers are big dropdowns,
  each pattern shown large with its name.
  `test_the_hatch_library_draws_every_pattern_behind_the_outline`.
- **B3 viewports:** the Viewport tool (Measure) drags a region of the sheet
  and gives it a name and scale; measurements and rectangle sizes inside it
  use that scale, the rest of the page its own. Shown on screen as a dashed
  purple frame with its name and scale (not printed). Page > Viewports…
  lists them to rename, rescale or delete; right-click inside one does the
  same. Saved with the document; every change is undoable.
  `test_a_measurement_inside_a_viewport_uses_its_scale`,
  `test_viewports_are_saved_changed_and_deleted`,
  `test_the_viewport_tool_asks_for_a_scale`.
- **Rail reordering:** panel icons can be dragged up and down their rail as
  well as across; the order is remembered.
  `test_rail_icons_can_be_reordered_top_to_bottom`.
- **No wheel on dropdowns:** a combo box never takes the scroll wheel
  anywhere in the application; the wheel scrolls whatever it sits in.
  `test_the_wheel_over_a_dropdown_scrolls_the_panel`.
- **Icons:** the cloud callout icon shows a text box, leader and cloud; the
  leader menu has separate arrow-leader and cloud-leader icons.

Full suite: 971 passed, then the one failing viewport test fixed (it now turns on the
prompts it checks) and re-run with the other viewport tests: 3 passed.

## 2026-09-29 — Page setup panel, viewports, export fidelity, Bluebeam import

- **Leader icons:** Add arrow leader / Add cloud leader use the Callout and
  Cloud+ tool icons.
- **Viewports hidden until clicked into:** a viewport's frame shows only
  while it has been clicked into, while it is picked in the Page setup panel,
  or while the Viewport tool is out.
  `test_a_viewport_frame_shows_only_once_clicked_into`.
- **Page setup panel** (right rail): follows the current page — paper size,
  orientation (e.g. landscape), custom size, apply to all pages; scale with
  an optional separate Y scale, calibrate, length and area units, decimal
  places; the page's viewports to add, edit or delete. Separate X/Y scales
  are honoured by lengths, areas, angles and rectangle sizes, saved, and
  written to the PDF measure dictionary (/Y). Page scale dialog has the same
  option. `test_separate_x_and_y_scales_measure_true`,
  `test_the_page_panel_follows_and_changes_the_page`.
- **Cloud drag box in other editors:** `/RD` was lopsided (room for the
  rotation handle) and written top-first; editors (MuPDF, Bluebeam — whose
  own callouts confirm the order) read left, bottom, right, top. Square,
  circle and cloud Rects are now even about the shape and `/RD` is written
  and read in that order. `test_a_clouds_drag_box_in_another_editor_is_the_cloud`.
- **Every markup exported and checked** in MarkForge, MuPDF, pdfium (Chrome
  and Edge) and with its appearance rebuilt from its dictionary (what an
  editor does on edit). All markup types and all Sketch Tools render
  identically in MuPDF and pdfium. Fixed on the way: annotations written in
  reading order instead of stacking order (a section arrowhead over its
  bubble); borderless text boxes now say `/BS /W 0`; text boxes carry `/DS`
  and `/RC` in Bluebeam's format; colours written as Bluebeam writes them
  (/C fill, /DA frame, /LEIC arrowhead, /FillOpacity, /PatternName, /BM);
  dashes in `/BS /D`; arcs as a curved PolyLine (`/Curves`). Rebuilt
  rectangles, ellipses, text, callouts, highlights and Sketch Tools now match
  at 0.92–1.00. `test_markups_go_out_in_the_order_they_are_stacked`,
  `test_a_borderless_text_box_says_so_and_carries_its_rich_text`,
  `test_an_arc_goes_out_curved_for_an_editor_that_redraws_it`.
- **Groups within groups:** Bluebeam's `/GroupNesting` sub-group lists are
  read from `.btx` files and from Bluebeam PDFs (a Section is one group
  holding a bubble group and a cut-line group, titled "Section"), and written
  back out the same way: leader with `/GroupNesting`, members `/RT /Group
  /IRT`. `test_a_section_mark_is_a_group_holding_a_bubble_group_and_a_cut_line_group`,
  `test_bluebeams_own_pdf_opens_with_its_groups_in_groups`,
  `test_a_sketch_tool_goes_out_as_bluebeams_nested_group_and_comes_back`.
- **One-to-one tool set import:** every tool in all 14 `.btx` files that
  carries Bluebeam's own appearance (290) was rendered from that appearance
  and compared with the import: all match (one RHS stamp turned a quarter
  was fixed by fitting the appearance to its box as PDF does). For tools
  Bluebeam draws from their settings, the import now reads `/Curves`
  (curved sides), `/LineStyle` (Medium Dash, Grid Line), the hatch tile
  itself (`/Pattern`, `/PatternScale`, `/PatternColor`), text-box colours
  (/C fill, /DA frame), `/Shape /Circle` circled text, and the callout knee
  from `/CL`. Tests in `tests/test_btx.py` (2026-09-29 section).
- **Replace image like Word:** right-click an image → Replace image → From
  file… / From clipboard (also in Properties). The new picture keeps its own
  proportions, fitted into the old one's box from the same corner; one undo
  step. `test_replacing_an_image_keeps_its_box_like_word`,
  `test_an_image_offers_replace_on_its_right_click_menu`.

Still different when another editor rebuilds a markup from its dictionary:
cloud scallop size, note icons and measurement labels are drawn in that
editor's own style; MuPDF ignores Bluebeam's `/Curves`, `/FillOpacity` and
hatch keys (Bluebeam reads them). Not verified in Bluebeam itself — no copy
here.
