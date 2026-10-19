# MarkForge — evidence record

Previous entries were deleted at the user's request on 2026-09-27. Evidence for
the 2026-09-27 report is recorded below. Completion status stays user-owned.

## 2026-10-18/19 — Revu's Properties per markup, line styles and hatches; Windows fixes; the crash and leaks under the test runs (pushed at f1843e7)

- Full test runs passed at 24d9d61, e01d705 and f1843e7 (`-n 3`, every-command tests included); 14/14 planted bugs caught each time.
- Windows (2026-10-18): the title bar's minimise, maximise and close answer and act; panel edges go blue on hover and hide in one click; buttons with a menu leave room for their arrow; zooming leaves nothing at the page edges. No zoom keys by default — the wheel zooms (the user's answer); Zoom In/Out stay bindable.
- Properties toolbar and panel per markup kind, as the user's Revu shots (docs/qa/revu_shots/propbar/): line-end colour; ends only where a markup has ends; end sizes as Auto/%; Sketch to Scale Units, Caption, Totals and cut-out; Note icon; picture lists with ticks; Highlight multiplies only the inside; Show Segment Values, Show Caption + Edit, Show Centroid.
- Revu's line styles (Dashed 1–6 and nine complex styles, drawn, printed and written to the PDF) and hatches first, every older style kept.
- Undo: a step that changed only a markup's Modified time is no step (a box opened and closed untouched used the next Ctrl+Z up when a second ticked over).
- Crash: a throwaway line-end list on each theme change and Set Scale's unplaced boxes were Python-owned windows freed at random — a segmentation fault while the window list was read. Answered dialogs (Set Scale, Page Setup, Document Properties, Flatten, Colour Processing, About) are let go with their document; the every-command harness delivers deferred deletes between jobs.
- Waiting on the user: a retest on Windows of the caption buttons, panel edges, arrow overlap and zoom edges.

## 2026-10-17 (later) — Print as the user's Revu photo; the Markups List filter dims the page (pushed at e2f4212)

- Full test runs passed at 7ae6cd0 and e2f4212; 14/14 planted bugs caught.
- Print dialog laid out as the user's Revu 21 photo; greyscale, visible hyperlinks and dim filtered markups print; Defaults ▾ and Advanced Printing.
- Markups List: filtered-out markups dimmed on the canvas (and on paper with Dim Filtered Markups), imported and ink annotations included; Filter List toggle; typing in the search stays at 1–5 ms a key with 1000 markups.
- The user checked on Windows: the menus in the native title bar work; opening Excel is fine.

## 2026-10-17 — Revu's Print and Page Setup, the Properties toolbar finished, names in reading order (pushed at 8f1c391)

- Full test runs passed at 4f86c8b, 4672a2d, ac8f077 and 8f1c391 (`-n 3`, every-command tests included, no silent re-runs); 14/14 planted bugs caught each time.
- Print: Revu's dialog — preview, printer, Pages range with Get Window, Document & Markups / Document Only / Markups Only, copies, rotation, page scaling, centre or offset, dim; imported pages no longer print blank at 1200 dpi.
- Page Setup: Revu's dialog, and the page really resizes — drawing, markups, equations and tables move and scale together, measurements keep their values (page scale follows), one undo step, 50 pages in 0.8 s.
- Properties toolbar: framed swatches, area hatch, Auto font size ("A"), cloud scallop styles and intensity, units and captions per measurement, strikethrough/superscript/subscript, line-style manager, line-end sizes, hatch colour on every hatch markup, boxes wide enough; Sketch to Scale buttons of their own; no size box on plain shapes.
- Names: read in document order whatever defines them (equation, named cell, table, measurement); a name defined only below is not defined, as in SMath; the Variables panel marks the one in force.
- Spreadsheets: rows counted, Insert Row and Enter add one row, pages follow the rows, a print area's pages only; a deleted sheet takes its formula tip and editors with it.
- Thumbnails: going to a page picks it alone; a picked run stays through scrolling and zooming; the page in view has its own outline.
- Crashes: dialogs given back to their parents after exec(); answered dialogs and closed menus deleted (96 windows stay 96, not 516).
- Every-command tests: no silent re-runs; first failures logged; harness order bugs fixed; 2219 commands, 2747 ways in.

## 2026-10-16 (later) — every command exercised and bindable; the QA round's bugs fixed (pushed at 3ec54f1)

- Full test run on 3ec54f1: all tests pass with `-n 3`, including tests/test_every_command.py (2204 commands, 2729 ways in, no known failures); 14/14 planted bugs caught.
- Keyboard Shortcuts lists 778 commands — menu bar, right-click menus, toolbars, panel buttons — any usual key, saved at once (tests/test_every_command_is_bindable.py).
- Crashes: Offset then New PDF then drawing; closed windows' leftover Markup Styles buttons freed under the window list. A closed window is hidden and quiet at once.
- Undo: one step per text box, callout, Cloud+, typed value, insert and link; Cancel changes nothing; undo puts back the view and the selection; Ctrl+Z works after New.
- Documents keep their own search marks and view rotation; New Window and Split View no longer slow down over a session (closed windows were never deleted).
- Shapes: no group resize; Sketch to Scale Rectangle and Ellipse beside plain ones in paper units; text box by drag; ellipse to polygon; group menus; leaders; scale prompt only for measures; locked selection shows.
- Spreadsheet: empty-clipboard paste, Excel's Insert/Delete Cells dialogs, header guess, format box, Comment column, thumbnails catch up, edge drags size on release with a guide line; recalc 2.0→0.3 s, insert row 6→1.5 s, xlsx open 5.6→1.3 s.
- User items: style text applies on placement; Variable and Global atop a cell's menu; Decimal Places, Significant Figures and Global atop an equation's; the stuck "=" unit box; SMath-style Variable boxes; panels left or right only; no stale red cross; Dim Content ticked in a window opened while dimmed.
- Not yet tried on Windows: the menus inside the native title bar.

## 2026-10-16 — rounds 2–4 merged and gated (pushed at dbc632f)

- Split View: a tab dragged to the other pane opens no copy and leaves no blank tab, and the emptied pane ends the split (tests/test_split_tabs.py).
- Right-click on a cell moves the selection there first (Excel), so Insert Page Break lands where the pointer is.
- Markups List: double-click its handle bar to hide or show it.
- Equations: ")" closes the bracket ((1+2)*3=9); name(1,2)= always evaluates; max/min/sum take any number of arguments; atan2 and lg.
- Cells: equation variables keep their unit (35 kN·m); units in blue with real superscripts, on screen and in print; incompatible units refused with a reason.
- Excel: General shortens to fit the column; var(X) reads the equations' X before Excel's VAR; errors say why; hidden columns; dates.
- Markup Styles toolbar: tool key then 1–9; back to the default after each markup; styles edited like Revu's Properties Mode; app-wide; Preferences tick for the keys.
- Window: resizes to 800×600; the status bar drops controls into »; toolbar rows wrap; a Measure toolbar; clouds without the hook.
- Revu Flatten Markups (types, scope, Allow Markup Recovery, Pages) and Set Scale (presets, Custom with Calibrate, Separate Y, Precision).
- Every right-click menu regrouped (docs/qa/findings.md round 4).
- The page no longer jumps when a markup is picked (the Markup Styles hint matches its buttons' height).
- QA: docs/qa/feature_inventory.md (1181 features, 435 untested, 86 placement smells), docs/qa/revu_audit.md, docs/qa/QA_PLAN.md.

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

## 2026-09-29 (later) — every markup, every look, every kind of page

A sweep exported every drawing tool in six looks (plain, faded, heavy dashed
with arrowheads, filled, hatched, turned) on six kinds of page (blank, PDF,
PDF cropped, PDF turned 90°, 180°, and 270° cropped), and compared each with
MuPDF, pdfium and the markup rebuilt from its dictionary. Fixed:

- **Markups on turned PDF pages were squashed** in every viewer: the
  appearance was fitted into the turned Rect without being turned. Each
  appearance now carries the page's turn in its /Matrix.
- **Markups on cropped PDF pages were placed off by the crop**, on export and
  when a PDF was opened: MuPDF's `transformation_matrix` was used the wrong
  way round, and on turned pages it drops the crop's offset altogether. The
  mapping is now built from the page's crop box (verified against rendered
  positions in all four turns, with and without a crop, and with a media box
  not at 0,0).
- **/RD** is computed in the file's own space, so it is right on turned pages.
- **Turned rectangles, ellipses, clouds and highlights, and rounded
  rectangles** go out as a polygon of their exact outline (a PDF square
  cannot turn or round its corners); turned text carries Bluebeam's
  /Rotation.
- **Hatches** go out with the hatch itself as a PDF tiling pattern in
  /Pattern (Bluebeam's own tile for imported hatches, the library linework
  otherwise); checked by painting the pattern and comparing with MarkForge.
- **Cloud scallop joints** are round everywhere; the screen drew miter
  spikes that no export showed.
- **Freehand lines with arrowheads** go out as a polyline (ink cannot carry
  line endings); arrowheads are written filled (/IC) as they are drawn.
- **Notes on turned pages** vanished in MuPDF: PDF keeps a note's icon
  upright and pins it by its top-left corner. Notes there are now written
  upright, pinned at their corner, with the no-rotate flag.

Tests: `test_markups_on_a_turned_or_cropped_sheet_export_where_they_are`,
`test_an_annotation_on_a_cropped_sheet_opens_where_it_is_drawn`,
`test_a_turned_rectangle_goes_out_as_its_outline`,
`test_a_hatch_goes_out_as_a_pattern_the_editor_can_draw`,
`test_a_note_on_a_turned_sheet_shows_where_it_was_put`,
`test_arrowheads_go_out_filled_and_a_freehand_arrow_keeps_them`.
After the fixes every tool shows in MuPDF and pdfium where and as MarkForge
draws it (97–100 % of its ink in place) on every page kind. Full suite: 1003
passed.

Differences that remain, and why:
- A dashed curve's dashes can sit a fraction differently in another viewer:
  each viewer measures dashes along a curve its own way. Straight dashed
  lines match exactly.
- When an editor redraws a markup from its dictionary (not when it shows
  it): arrowhead size, cloud scallop size and note icons follow that
  editor's own style — PDF has no key for them; MuPDF ignores Bluebeam's
  /Rotation, /Curves, /FillOpacity and /Pattern, which Bluebeam reads.
- Thick borders: MuPDF centres a rebuilt square's border on Rect less /RD,
  Bluebeam keeps it inside; the export follows Bluebeam's own files.

## 2026-09-30

- **Measurements across a viewport's edge:** when a move or resize finishes,
  each measurement and sized shape is read again at the scale where it
  landed — the viewport's inside it, the page's outside.
  `test_a_measurement_dragged_into_a_viewport_takes_its_scale`.
- **Move and copy modifiers as Bluebeam's:** a drag is a copy only when Ctrl
  is held as it starts; Ctrl pressed during a move turns snapping off; Shift
  locks the move to straight lines. (Replaces the old rule that Ctrl
  mid-move made a copy.) `test_ctrl_taken_hold_of_mid_move_lets_go_of_the_grid_and_copies_nothing`,
  `test_shift_then_ctrl_mid_move_stays_a_constrained_move`.
- **Pages panel Ctrl+C / Ctrl+V:** the window's own Copy/Paste shortcuts took
  the keys first; the page list now claims them. With a page on the
  clipboard, hovering the thumbnails shows the blue insertion bar where Ctrl+V
  will put it; the bar goes when the clipboard changes.
  `test_ctrl_c_and_ctrl_v_in_the_pages_panel_copy_and_paste_pages`,
  `test_a_page_on_the_clipboard_shows_an_insertion_bar_where_it_will_go`.
- **Line spacing and cloud size:** dashes are now kept in points, so a line's
  thickness no longer changes them; a Spacing setting (Properties and the
  style toolbar) scales dashes and dots. Cloud size is offered for every
  cloud, cloud callout and cloud leader.
  `test_a_thicker_line_keeps_its_dash_spacing_and_spacing_scales_it`,
  `test_every_cloud_has_a_cloud_size`.
- **Add-leader icons (the pointer, as the user confirmed):** the pointer
  while adding a leader was a bare arrow or a bare cloud. It is now the
  Callout drawing with its arrowhead as the exact click point (arrow leader)
  or the Cloud+ drawing centred on its cloud (cloud leader, and the Cloud+
  tool), each with a thin white edge so it reads over dark linework.
  `test_adding_a_leader_carries_the_callouts_own_picture`.
- **Shift/Ctrl on a shape's outline:** a click still adds or removes a point,
  curves a side or rounds a corner; pressed and dragged it is a Shift-drag
  (straight move) or Ctrl-drag (copy) instead.
  `test_shift_or_ctrl_dragging_a_shape_moves_or_copies_it_instead_of_reshaping`.
- **Format painter as Bluebeam's:** picks up every appearance property the
  source has (colour, fill, both opacities, width, line type and spacing,
  hatch, line endings, the whole font, cloud size, corner radius) and paints
  onto each markup only what it can show — never size, words or values. It
  stays in hand across clicks; dragging a box paints everything inside in one
  undo step; Esc or the button puts it down.
  `test_the_format_painter_carries_the_whole_look_like_bluebeams`,
  `test_dragging_round_markups_paints_them_all_in_one_step`.

Full suite: 1012 passed.

## 2026-10-14 — Bluebeam Revu's interface, and 138 PDFs in and out

**Opened elsewhere, opened here.** 88 marked-up PDFs from pdf.js's test
corpus (every annotation kind: ink, free text, stamps, file attachments,
form fields, quad-point text markups, rotated annotations) were drawn by
CalcForge and by MuPDF, PDFium and Poppler at 144 dpi and compared pixel
by pixel (ink within one pixel and 60 levels). 102 of 113 pages agreed with
a reference within 2 % of their ink; the rest were inspected by eye:
- **An ink note in several strokes printed as straight segments** instead of
  the file's own curves (rotated_ink.pdf). On screen the page drew the file's
  own; in print the strokes drew themselves. Print now does as the screen
  does while every stroke is untouched; a save still writes the strokes.
  `test_a_three_stroke_ink_note_prints_as_its_file_draws_it`.
- The rest are anti-aliasing of large text and hairlines, a strike-out with no
  appearance drawn thinner by MuPDF and CalcForge than by PDFium, and a page
  Poppler sizes differently — the references disagree with each other there
  by as much.

**Made here, opened elsewhere.** 50 documents (every drawing tool with
random colours, widths, dashes, fills, hatches, line ends and cloud sizes;
1–3 pages; equations; tables; sheet pages; viewports; turned pages) were
saved, drawn by the three readers and reopened here:
- **A turned page's markups and tables moved on reopening** (36 of 86 pages).
  Rotate Page turned each markup about its corner; a reopened one turns
  about its centre. Markups now turn about their centre and their centre is
  carried by the page's turn; equations and tables keep WebSMath's corner
  and are reopened about it. A turned rectangle converted to a polygon
  jumped the same way. After: 0 of 86 pages change across a save and reopen.
  `test_rotated_save.py` (7 tests).
- Every page agrees with MuPDF, PDFium and Poppler; the 10 over 2 % are a
  dash pattern's starting phase and hairline anti-aliasing (MuPDF snaps
  0.5 pt verticals to whole pixels).

**A renderer outliving the application.** Three PDF renderers whose window
had been killed mid-page kept a core and a half busy for 37 minutes. A
renderer now ends with its parent (the kernel's parent-death signal on
Linux, and a watcher everywhere). `test_a_renderer_dies_with_the_application_even_mid_page`
fails without it.

**Revu's interface.** Menu bar (Revu … Help with a Calculation menu), Revu 21
palettes with Dark first, the Properties panel's sections and Title Case
names, cloud Size and Invert as the PDF's /BE intensity, Revu's ten line
ends, the scale box with proportional corners, gold control points and
the curled rotation cursor, Symbol/Detail views, **Manage Tool
Sets** (show, hide, order, rename, remove), **Hatch Patterns** (import an
AutoCAD/Revu .pat, write one, remove one's own), the status bar's snaps and
page navigation, and Title Case on the Thumbnails page menu.
`test_revu_ui.py`, `test_cloud_size.py`.

**Follow-ups the same day (the user, 2026-10-14):**
- **Pieces of the selection box and rotation handle left behind on moving a
  markup.** Handles are drawn a fixed number of pixels across, so zoomed out
  they reached past the markup's own rectangle, which is all Qt repaints.
  A selected markup now counts its handles' room at the current zoom (and
  align and redaction still measure the markup alone). Checked for every
  markup kind at five zooms: `test_selection_chrome.py`.
- **The eyedropper hung or crashed the application.** Over a modal dialog
  (Color Processing) its held-still screen took no clicks; it is now
  application-modal. Where the system refuses a screen grab, the
  application's own windows are shown instead. A colour button deleted while
  its picker was open is left alone. `test_colour_picker.py`.
- **Modify Colors has no tolerance**: a colour of the line work is changed
  exactly (each one its own row); Mask Images keeps its tolerance.
- **Recent Tools removed** (not wanted).
- **Tool Chest:** Symbol, List and Detail views per set; every set as wide as
  the panel and every tool shown (a set of seven showed three, with a gap
  down the right); Revu's tool menu — Drawing Mode / Properties Mode,
  **Scale** (a tool keeps its real size on a page of another drawing
  scale), Move Up / Move Down, Copy and Paste.

## 2026-10-15 — a sharp picker, the eyedropper everywhere, and Revu's workspace

**The colour picker looked blurry next to Revu's.** Its swatches, and every
icon, were pictures made at 100 % and stretched by Windows at 125 % or 150 %,
so each edge spread over two pixels. Icons are now drawn once for each
screen's own pixel ratio and Qt shows the one that matches; the More Colors
spectrum and hue strip are gradients drawn at the screen's pixels.
`test_the_picker_swatches_are_drawn_at_the_screens_own_pixels`.

**The eyedropper couldn't take the taskbar.** It held only the screen under
the pointer still, and read the grab at the screen's stated ratio even when
the grab did not say. It now holds every screen still, the loupe follows the
pointer from one to the next, the mouse is held by one of them so a click
anywhere comes to it, and a grab is read at its true pixels (its size over
the screen's). `test_the_eyedropper_reaches_every_screen_and_a_scaled_one`.

**Transparent line work: not applied.** Revu 21's manual gives the Line,
Polyline, Rectangle and Pen tools an Opacity for the line itself ("Sets
opacity level of the line and endpoints, from 0 (invisible) to 100
(opaque)") beside Fill Opacity, so line opacity stays as Revu has it.

**Already here under another name** (the user: don't add what exists):
Revu's Erase Content and Cut Content are the Whiteout tool; Multiply is what
was called Multiple Copies… (now named Multiply…, keeping Ctrl+Shift+D as
Ctrl+M is SMath's matrix); the page relabelling, rotation, Page Scale,
Calibrate, Link tool and a snapshot's Change Colors are built on, not beside.

**Revu's workspace (gap list, group 1):**
- **Page layouts** — View ▸ Single Page, Continuous, Side-by-Side and
  Continuous Side-by-Side, with Show Cover Page in Side-by-Side; the status
  bar's layout button lists them. The old Page/Continuous scroll switch is
  Single Page/Continuous. In the one-spread layouts the wheel scrolls the page
  and turns to the next at its end. Each document keeps its own layout.
- **Rulers** along the top and left, from the page's corner, in inches,
  centimetres, millimetres, points or picas (right-click), showing the page,
  the selection and the pointer; **Full-Screen Crosshair** in the snap colour.
- **Dimmer** — View ▸ Dimmer ▸ Dim Content (Ctrl+F5) and 0–100 %, and a
  status-bar toggle: the page's content toned down under the markups, on
  screen only.
- **Full Screen** (F11) and **Presentation** (Ctrl+Enter): the page alone, a
  page at a time; arrows, Space and Page Up/Down turn, Esc puts everything
  back as it was.
- **Edit ▸ Undo History** — newest first; choosing one undoes back to before it.
- **File ▸ Open Recent, Close (Ctrl+W), Close All, Save All.**
Tests: `tests/test_page_layouts.py`, `tests/test_view_workspace.py`.

## 2026-10-15 (later) — big drawings, the title row, fields, errors, the sheet's rough edges

**Colour change on a big drawing froze the app.** Color Processing read and
rewrote a 21 MB page in about 8 s on the window's own thread, and again for
every preview. The content scanner now skips everything that is not a colour
or paint operator in one pass (operands read backwards, not re-matched), the
rewritten streams are deflated at zlib level 1, and only forms the page
actually draws are followed: about 0.9 s to list the colours and 1.15 s to
process, with identical renders. The work runs in one helper process; the
window keeps drawing (a progress note after half a second) and an overtaken
preview is dropped. Right-clicking a page lists only that page's colours, and
a colour picked in one row leaves the Source list of the others.
`tests/test_color_processing_big.py`.

**An equation dropped on a spreadsheet page couldn't be picked.** A drop on a
sheet page sends equations and tables back where they came from; one already
stranded there is moved to the nearest page that takes it when the document
is opened or rebuilt. `test_sheet_pages.py`.

**One row at the top.** The first menu is CalcForge, and the window draws no
system title bar: the app's icon, the menus, the Markup | Calc switch, Search
and the minimise / maximise / close buttons share one row. Dragging empty
space on it moves the window (Windows still snaps it), a double-click
maximises, the edges resize. macOS keeps its own menu bar and frame.

**SMath errors.** `t:fc` with `fc` undefined now says "fc - not defined." as
soon as it is committed (not while typing), and every equation's error is
written in red under it whether or not it is selected (never printed).
`tests/test_equation_errors.py`.

**The wheel never changes a value** in the Properties panel or the Properties
toolbar; it scrolls the panel. **Dark mode:** the line-style and hatch
samples are drawn in the theme's ink when theirs would vanish.

**Text boxes: bookmarks and fields.** Right-click ▸ Bookmark (or Properties ▸
General ▸ Bookmark) gives the box a bookmark titled with its first line that
follows it to whatever page it is moved to and goes when it is deleted.
Right-click ▸ Insert Field puts in a variable from the equations (`{=L.beam}`,
showing its value and unit and recalculating), the page number, page count,
date, time or a document property — shown as codes while typing, values on
screen, in print and in the saved PDF. `tests/test_text_fields.py`.

**Spreadsheet usability.**
- *Two horizontal scroll bars:* the sheet tabs sat on a row of their own
  under the canvas's scroll bar; they now share the scroll bar's row, as
  Excel's do.
- *Surprise rows:* a page break added a page and removing it never took it
  back, so every break left an extra page of rows behind; and on an empty
  sheet a break cut off the rows after it. Now the page a break starts is
  always there, removing the break takes back the page it made (pages added
  by hand stay, markups go with their cells), each in one undo step.
  `test_a_break_takes_back_the_page_it_made`.
- *A #### cell's unit:* SMath's unit box now shows after the hashes, so the
  unit that would make the value fit can be typed there (the formula bar's
  unit box works as before). `test_a_hashes_cell_still_has_its_unit_box`.
- *A name beside a function of the same name* (the user's question): as in
  Excel, `SUM(` followed by a bracket is always the function and a bare `SUM`
  is the defined name — or the equations' variable (`max` vs `MAX(1,2)`).
  Names that read as cells are refused, now including Excel's R1C1 forms
  (R1C1, RC, R2C, C3). `test_a_name_beside_a_function_of_the_same_name`.

## 2026-10-15 (evening) — nothing lost, Import where it's looked for, colour change rules

**Nothing was deleted.** Every command of every version of the window was
checked against today's: the 136 commands ever defined, the menus and
toolbars before the Revu menu bar (25d0f71) and now, and the right-click
menus of a shape, a text box and a page. Everything the user had before is
still there — renamed to Revu's words (Insert Excel… is Excel Workbook…,
Insert PDF… is Pages from Document…, Export markups… is Markups Summary…,
Order is Arrange, Multiple… is Multiply…, Recover is Unflatten) or moved to
Revu's menu (Page → Document, Insert → Tools, Settings → CalcForge). The ten
commands no longer defined went with the user's own instructions (the
calculations taken out on 2026-09-07, review replies withdrawn, Recalculate
replaced by the Calculation toolbar). The only module deleted is the old
recolour.py, replaced by Color Processing as asked.
`test_the_menu_bar_is_revus_with_a_calculation_menu` now fails if any
command of the window is in no menu or toolbar.

**File ▸ Import** — Excel Workbook…, Pages from Document…, Image Page… and
Import Tool Set…, beside Export: the Excel import was only under Document ▸
Insert, where nobody looks for it.

**Colour change: the drawing's, and a group's.** A page's Color Processing
changes the PDF's own line work (flattened content) and never a markup;
markups change colour together only through Change Colors on a group or on
several picked together. A grouped markup now offers Change Colors for its
whole group however it was picked.
`test_page_colour_change_is_the_drawings_and_a_group_is_how_markups_change`.

**Dark mode:** the line-style and hatch lists, open and closed, on the
Properties toolbar and in the Properties panel, checked on screen.

**Revu's look, from the user's own Revu** (their 2026-10-15 screenshots; the
user: the colours, the Markup | Calc switch, the toolbars and the panels
didn't look like Bluebeam). The dark theme had copied the Revu 21 manual's
near-black (#1e2022, a black menu bar); the user's Revu is a softer
charcoal, measured from their screenshots and now ours: bars and panels
#2e2e2e, menus, list headers and rulers #3e3e3e, the open document's tab
#4e4e4e, input outlines #565656, a picked tool, row, menu entry or rail
button filled with Revu's deep blue #175884, its bright blue #0083db for
focus, light-grey scroll handles, and a grey desk behind the page (#424242,
not near-black). Toolbar tools show as picked by that blue fill, not an
underline; tabs are flat blocks with the open one lighter; panel titles are
Revu's bold white; icons are white line work with an amber accent (the PDF
icons are no longer red). Markup | Calc is two flat square buttons like
Revu's own toggles instead of a bright pill. On the Properties toolbar the
spin arrows sit before the number and drop-downs carry Revu's thin chevron.
The rulers' corner follows a theme change (it stayed dark in light mode).

**Right-click a row ▸ Insert Page Break "deleted all the rows after"** (the
user's answer): on a sheet with one page the break cut the run off at the
break, so the rows after it were nowhere. The page a break starts is now
always there, and removing the break takes it back (above).

**Dark-mode line and hatch lists, again (the user repeated it):** checked
with the worst case — black line work and a black Cross hatch — on the
Properties toolbar and in the Properties panel, closed and open: every
sample is drawn in light ink. The toolbar's line list now names its styles
as the panel does (Solid, Dash … rather than solid, dash), and a list's
highlighted entry is Revu's deep blue. `test_the_toolbars_line_styles_are_named_as_in_properties_and_still_apply`.

**Line style and hatch drop-downs as Revu's** (the user, 2026-10-15 night):
closed, the Properties panel's Style and Hatch boxes now show only the
sample drawn across the box, with Revu's thin chevron and no name (the name
is the tooltip), as the toolbar's already did and as Revu's panel does. The
hatch list opens as Revu's hatch menu does: Manage… at the top, then (None)
and every pattern. Number boxes in the Properties panel carry their arrows
before the number, as in Revu's panel.

**Equation errors print** (the user's answer): the red note under an
equation with an error now prints and goes into the saved PDF as well as
showing on screen; a definition with an undefined name keeps saying so as
soon as it is committed. `test_an_evaluation_error_shows_without_being_selected_and_prints`.

## 2026-10-17 — Revu's Page Setup, with the content really resized

**Page Setup follows Revu's layout and really resizes the content** (the
user's decision, round 3; audit B7 and B0). Document ▸ Page Setup… (and a
page's own menu, the canvas menu and the status bar's paper size) opens
Revu 21's Page Setup tab: Change Media Size (mm) — Media Size
(<Default Page Size>, the standard sizes, Custom Page Size), Portrait or
Landscape, Width and Height; Offset X and Y; Scale (%) with Auto Scale;
Rotation with Get Line; Clear, Centre and Fit to Media (its arrow picks
where on the paper: Top Left … Bottom Right). Then Revu's Pages range
(All Pages, Current, Selected, Custom), CalcForge's calculation margins in
their own "Margins (CalcForge)" group, and a Preview (Media Size, Page Size,
Scale, the page drawn where it will land, a page navigator). Get Line hands
over to a line dragged on the drawing and comes back with the Rotation that
makes it level; Esc comes back unchanged.

What OK does to each page (calcforge/ui/pagesetup.py, calcforge/io/pdfresize.py):
the page's paper becomes the new size and everything on it is turned,
scaled and moved onto it in one transform — the PDF page itself (its
content wrapped in one `cm`, its boxes the new paper, its /Rotate folded in,
its annotations carried), markups, equations, tables, pictures, viewports
and bookmarks. Measurements keep their real values: their points scale and
the page's (and viewports') scale changes by the same factor (1:100 at 50 %
is 1:200). The saved PDF shows the result in any reader. One undo step,
which puts everything back exactly; OK with nothing changed adds none. Fifty
A4 sheets with twenty markups each go to A3 in about 0.8 s (undo 0.45 s).
The Page panel's paper boxes and the Paper Size menu go through the same
path with the content left where it is, so the file's page gets the paper
too and the panel and dialog always agree. Disabled radio buttons and tick
boxes now still show which is chosen (theme). `tests/test_revu_page_setup.py`.

## 2026-10-19 — a tab dragged into another window, with the same file in both

**The user:** "Had an issue where having two windows with the same PDF then
dragging it over to one window, but only [the] tab stayed." A window made
by a tab's New Window kept the blank document it was born with as its one
tab's record, so a tab of the same document dragged onto it was not
recognised and was opened a second time beside itself; the window dragged
from was left as an empty shell; a tab dropped on the other window's canvas
made a third window over it; and the undo history went over with steps that
still called back into the window that recorded them — once that window had
closed, Ctrl+Z crashed, and a page step put pages back into whatever that
window showed next.

What happens now, as in Revu (one file is not open twice in a window, and a
window emptied by a drag closes):
- the same document in both windows (New Window): the tab there comes
  forward, and the window dragged from closes if that was its last tab;
- two copies of one file opened apart: the one with unsaved changes is kept
  (the clean one gives way); both clean, one tab; both with changes, both
  are kept, the one brought in marked "a.pdf (2)", and the status bar says to
  Save As one of them;
- another file: it moves with its canvas, page, zoom, undo history and
  selection; a window keeping other tabs stays;
- dropped anywhere on another window (its tab bar, canvas or empty
  workspace) it goes into that window; dropped on no window it still makes a
  window of its own;
- File ▸ Open of a file another window has open brings that window's tab
  forward ("already open in another window") instead of a second copy; a
  document shown in two windows is one document, one canvas and one history,
  so an edit in either shows in both, and closing one of the windows asks
  nothing (the other still has it).
Undo steps now find their pages through the canvas and their window as the
one holding the document when they are applied (ui/commands.py
`on_the_canvas`, MainWindow._on_its_window). `tests/test_tab_drag_windows.py`.

## 2026-10-19 — the Thumbnails panel as Revu's

The user's photo showed page 3 on a second row with room for it on the
first. The grid gave each cell width / columns, so the cells came to the
whole width, and Qt starts a new row as soon as the next cell reaches the
right edge; it also kept a scroll bar's width spare whenever the strip might
scroll. The strip now works out its columns from its own width (less the
scroll bar only while one is shown), leaves Qt its spare pixel, and lays
itself out again on resize, zoom, pages put in or taken out, and at 125 %
and 150 %. Pages fewer than the row has room for share it, centred.

The header is Revu's: "Thumbnails ▾" (the title) is the panel's menu —
every insert Before / After, Duplicate, Extract, Split, Delete, Crop and
Rotate Pages, Page Setup, Set Scale, Larger / Smaller Thumbnails (also on
the Window menu) — and the
buttons follow it as small flat icons, evenly spaced: Insert Pages ▾ (new
here, as Revu's), Insert Blank Page ▾, Insert Spreadsheet Page ▾ (a page
icon, not "▦"), Duplicate Page and Delete Pages. On a narrow panel they go
on a line of their own under the title. Pin, float, roll up and close are
small and flat on every panel. The thumbnails have a thin neutral edge, the
picked page Revu's blue frame (#0972b8 in dark), the page in view an
outline just outside it, the number centred under the page and its scale
under that, on the panel's own ground. `tests/test_thumbnails_look.py`.

