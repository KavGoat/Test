## Revu 21 audit of CalcForge's dialogs, panels and menus

I compared CalcForge's menus, dialogs, panels, toolbars and context menus with the Revu 21 manual and the user's 31 screenshots. The main finding is that most of the Revu commands CalcForge already has work, but sit in the wrong place, have the wrong name, or open a quick prompt where Revu opens a real dialog. Revu's shared "Pages" range control is missing everywhere. No app code was changed and nothing was committed.

**How it was done**
- The audit ran on branch `claude/admiring-archimedes-i371m1` at commit bffe07d. My worktree was on `main`, which has no `calcforge/` folder, so I exported that branch to `/tmp/revu_audit/src` with `git archive`.
- Every menu item ending in "…" was triggered in the real window, headless. Modal dialogs were grabbed to an image, their fields were listed, and they were cancelled.
- Scripts are in `/tmp/revu_audit/`; the menu tree is in `/tmp/revu_audit/menus.txt` and the field lists in `/tmp/revu_audit/dialogs_all.txt` and `/tmp/revu_audit/dialogs2.txt`.
- Screenshots are in `(audit screenshots) `. One mislabel: `(audit screenshots) 011_Spelling.png` is actually the Link dialog.
- Withdrawn and declined features (layers, status/replies, sequences, Sets, Replace Pages, security, OCR, email, Visual Search, bookmark tools, batch commands, PDF summary report and so on) are not reported as missing.
- **Already with another agent, noted only:**
  - Flatten: recovery is a Preferences tick ("Recoverable flattening") instead of Revu's "Allow Markup Recovery" in the Flatten dialog. Document ▸ "Flatten Selection" should be "Flatten…" (Ctrl+Shift+M); Batch ▸ "Flatten…" should be "Flatten Markups".
  - Set Scale: the dialog, the "Page Scale…" wording (Revu says "Set Scale…"), and where Calibrate sits.

Sizes: S = wording or placement, M = dialog rework, L = large. File:function references are to the exported source.

---

### P1 — Highest impact

#### Group A. Thumbnails panel and page right-click menu
Code: `calcforge/ui/mainwindow.py:page_menu` (around line 3965), `_rebuild_current_page_menu`, and `calcforge/ui/panels.py:PagesPanel`.

**A1. The page right-click menu is a different menu from Revu's (M)**
- **Revu** (user screenshots 141836/141842; `menus__window__thumbnails-panel.txt`), in this order:
  - Page Set-up…, Set Scale…
  - Cut Pages, Copy Pages, Copy Page to Snapshot (Ctrl+Alt+C), Paste Pages
  - Apply Stamp…
  - Insert Blank Page… (Ctrl+Shift+N), Insert Pages… (Ctrl+Shift+I), Extract Pages… (Ctrl+Shift+X), Delete Pages… (Ctrl+Shift+D), Rotate Pages… (Ctrl+Shift+R), Number Pages…, Rename Page Label, Reset All Page Labels
  - Export Pages ▸, Print Pages…
  - Flatten… (Ctrl+Shift+M)
  - Markup Summary ▸
- **CalcForge**:
  - Go to Page, Add Bookmark, Rename…, Reset Label, a "Print" tick
  - Copy Page / Paste Page / Paste Before
  - Blank Before, Blank After, Spreadsheet After, Duplicate Page
  - PDF Before/After…, Image Before/After…
  - Move Up/Down
  - Rotate Clockwise/Counterclockwise, Header/Footer ▸, Page Grid, Paper Size ▸
  - Page Setup…, Page Scale…, Calc section break, Color Processing…, Make This Page's Markups Editable, Delete Page
  - There are two separators in a row after Move Down: `page_menu` calls `addSeparator()` twice and the menu does not collapse separators.
- Screenshot: `(audit screenshots) ctx_thumb_page.png`
- **Change:**
  - Rebuild the menu in Revu's order and with Revu's names, on the selected pages.
  - "Rename…" becomes "Rename Page Label"; add "Reset All Page Labels".
  - "Delete Page" becomes "Delete Pages…"; "Copy Page" becomes "Copy Pages"; "Paste Page" becomes "Paste Pages".
  - Add Cut Pages, and Copy Page to Snapshot (wanted).
  - "Blank Before/After" becomes "Insert Blank Page…"; "PDF Before/After…" becomes "Insert Pages…". Where the pages go is chosen in the dialog (A3).
  - Rotate becomes "Rotate Pages…" (a wanted dialog). The two rotate commands stay on the Rotation toolbar.
  - Add "Print Pages…" (Print with the Selected range) and "Flatten…".
  - Move the CalcForge-only entries (Spreadsheet After, Duplicate, Calc section break, Page Grid, Header/Footer ticks, Paper Size, per-page Print tick, Make Markups Editable) into one CalcForge section at the bottom.
  - Collapse the double separator.

**A2. The panel's header has no "Thumbnails ▾" menu, Labels toggle or Size slider (M)**
- **Revu:** "Thumbnails menu:" holds the same items as the right-click menu. "Labels: Toggles page labels … Page Label … Page Scale". "Use the Size slider at the bottom of the Thumbnail panel."
- **CalcForge:** the header has +, spreadsheet, duplicate and − buttons. Size is only Ctrl+wheel.
  - Each thumbnail is captioned "1 three.pdf page 1" (index plus `source_note`, set in `io/pdfio.py:616`) instead of the page label.
  - The page scale is never shown under thumbnails, though "page scale under thumbnails" is a wanted feature.
- Screenshot: `(audit screenshots) panel_dock_pages.png`
- **Change:** make the panel title a menu button, as Revu does. Add the Labels toggle (Page Label / Page Scale) and a bottom Size slider. Caption thumbnails with the page label only. Keep the + / sheet / − buttons as an icon strip.

**A3. Document ▸ "Current Page" submenu (S)**
- **Revu:** there is no such submenu; page commands open dialogs that have a Pages range.
- **CalcForge:** `_build_menus` adds "Current Page" with a copy of `page_menu`.
- **Change:** remove it once A1 and B1 give the Document menu its real items.

#### Group B. Document menu and page dialogs
Code: `calcforge/ui/mainwindow.py:_build_menus` (Document block around lines 1890–1905), `add_page`, `insert_pdf`, `extract_pages`, `split_into_files`, `delete_page`, `crop_page_region`, `apply_to_pages`; `calcforge/ui/dialogs.py:NewPagesDialog`, `PdfImportDialog`, `PageSetupDialog`.

**B0. Build one shared "Pages" range control first (M)**
- **Revu**, the same lines in delete-pages, extract-pages, page-setup, crop-pages, print and Apply to Pages: "All Pages … Current (2) … Selected: This option only appears if pages were selected … Custom: 1-3, 5, 9".
- **CalcForge:** nothing like it exists. B1–B6, D4 and the Print dialog (F1) all need it.

**B1. Document menu order and items (S)**
- **Revu** (`menus__document__document-menu.txt`, screenshot 142016):
  - Document Properties (Ctrl+D), Page Set-up…, Rotate Pages… (Ctrl+Shift+R), Insert ▸, Extract Pages…, Split Document…, Delete Pages…, Crop Pages… (Shift+Alt+O), Number Pages…, Create Page Labels…
  - Headers & Footers ▸ (Add, Edit)
  - Colour Processing…
  - Flatten…, Unflatten
- **CalcForge:**
  - Document Properties…, Page Setup…
  - Current Page ▸, Insert ▸, Duplicate Page, Extract Pages…, Split Document…
  - "Delete Pages" and "Crop Pages", both with no ellipsis and no dialog
  - Sheet Layout…, "Headers & Footers…" (a single item), Page Scale… (Ctrl+Shift+K), Viewports…, Add Bookmark (Ctrl+B), Table of Contents
  - Color Processing…, Flatten Selection, Unflatten
- Menu dump: `/tmp/revu_audit/menus.txt`
- **Change:**
  - Use Revu's order and ellipses. Add Rotate Pages… and Number Pages….
  - Make Headers & Footers a submenu (Add / Edit).
  - Shortcuts: Document Properties Ctrl+D, Delete Pages Ctrl+Shift+D, Extract Ctrl+Shift+X, Crop Shift+Alt+O.
  - Move Page Scale… and Viewports… to the Measurements panel and Tools ▸ Measure (Group H).
  - Move Add Bookmark to the Bookmarks panel and the page right-click.
  - Move Duplicate Page to the Thumbnails menu.
  - Sheet Layout… and Table of Contents are CalcForge features: give them a CalcForge section at the end (or put Sheet Layout in the Calculation menu).

**B2. Insert ▸ Blank Page opens "Add pages" (S/M)**
- **Revu** (`menus__document__insert-pages.txt`): "Insert Blank Page dialog … Template … Width and Height … Portrait or Landscape … Style … Page Count … Before or After … First Page, Last Page, or specify a Page … Set as Default".
- **CalcForge** (`dialogs.py:NewPagesDialog`): title "Add pages"; fields Number / Paper ("Same as current") / Orientation with lower-case items. Pages always go after the current page.
- Screenshot: `(audit screenshots) 001_Add_blank_page.png`
- **Change:** title it "Insert Blank Page". Use Revu's fields: size, Width/Height, Portrait/Landscape, Page Count, Before/After plus First/Last/Page, Set as Default.

**B3. Insert Pages ("Insert PDF pages") (M)**
- **Revu:** a file list with Add / Add Open / sort / up / down / remove / Modify (Pages: Custom). Options: "Include Bookmarks … Merge Document Properties … Use Filename as Page Label". Placement: "Before or After … First Page, Last Page, or specify a Page … Interleave Pages".
- **CalcForge** (`dialogs.py:PdfImportDialog`): one file plus Browse, Pages "all", a "Page size" combo. Placement comes from separate "PDF Before…" / "PDF After…" commands.
- Screenshot: `(audit screenshots) 004_File_Import_Pages_from_Document.png`
- **Change:** title "Insert Pages". Add the Before/After plus First/Last/Page placement. Keep "Page size" as a CalcForge option. A single file is fine.

**B4. Extract Pages and Split Document are plain prompts (M)**
- **Extract, Revu:** a Pages menu (All / Current / Selected / Custom) and Options "Delete Pages After Extracting … Extract Pages as Separate Files … Use Page Label to Name Files … Open Files After Extraction".
- **Extract, CalcForge** (`extract_pages`): `QInputDialog.getText("Pages (e.g. 1-3, 7)")`, then a save dialog.
- **Split, Revu:** "Split By … Page Count … File Size … Top Level Bookmarks … Folder … File Name Prefix or Suffix".
- **Split, CalcForge** (`split_into_files`): `QInputDialog.getInt("Pages in each file")`.
- **Change:** build both dialogs on B0. Bookmarks and File Size can be left out if unwanted.

**B5. Delete Pages is a Yes/No question (S/M)**
- **Revu:** "Each of these methods opens the Delete Pages dialog. Choose which pages to delete from the Pages menu."
- **CalcForge** (`delete_page`): `QMessageBox.question("Delete page 1?")`.
- **Change:** a Delete Pages dialog using the B0 Pages combo.

**B6. Crop Pages is a drag tool for the current page only (M)**
- **Revu:** "Crop and Page Setup dialog … Top, Bottom, Left, and Right margins … Set Proportional … Get Window … Pages dropdown".
- **CalcForge:** the Crop tool appears in Tools ▸ Navigation and Document ▸ Crop Pages. `view.py` calls `crop_page_region(frame, region)` with no pages choice and no margin entry.
- **Change:** Document ▸ Crop Pages… opens a dialog with margins, Get Window (the current drag tool) and a Pages range.

**B7. Page Setup dialog is a different concept (M)**
- **Revu** (`menus__document__page-setup.txt`): "Media Size … Auto Scale … Scale … Offset X or Y … Rotation … Get Line … Clear … Center … Fit to Media … Pages dropdown … Preview".
- **CalcForge** (`dialogs.py:PageSetupDialog`): title "Page setup"; Paper, Size, Orientation (lower-case), Margins group, an "All pages" tick.
- Screenshot: `(audit screenshots) 006_Document_Page_Setup.png`
- **Change:**
  - Title "Page Setup"; rename "Paper" to "Media Size".
  - Add Auto Scale, Scale, Offset, Center and Fit to Media if wanted.
  - Replace the "All pages" tick with the B0 Pages combo.
  - Margins are CalcForge's own calculation-layout margins; keep them in their own "Margins (CalcForge)" group.
- **Unsure:** whether the user wants Revu's content-resizing behaviour, or just its layout. Ask before building the resize maths.

**B8. Apply to Pages… is a three-choice prompt (S/M)**
- **Revu** (`menus__edit__*`): "The Apply to Pages dialog … All Pages … Custom Range … Even Pages … Odd Pages … Landscape … Portrait … Custom page ranges can be selected from the Thumbnails panel".
- **CalcForge** (`apply_to_pages`): `QInputDialog.getItem` with "Every other page / after / before".
- **Change:** an Apply to Pages dialog using B0, pre-filled from the thumbnail selection.

#### Group C. Markup and page right-click menus
Code: `calcforge/ui/mainwindow.py:build_context_menu` (around line 8446) and `_fill_outline_menu` (around line 8339).

**C1. The markup menu's order and names differ (S/M)**
- **Revu** (screenshot 141818), in this order:
  - Cut, Copy, Paste, Multiply… (Ctrl+M), Format Painter, Delete (Del)
  - Open Pop-Up Note
  - Control Point ▸, Arc Segment, Round All Corners
  - Order ▸, Alignment ▸, Flatten, Lock, Hide, Legend ▸
  - Add to Tool Chest ▸
  - Set as Default, Apply to Pages…, Properties
  - Icons on most items.
- **CalcForge:**
  - "This outline ▸", Convert to Polygon, Exact Size…, Show Size
  - Set as Default, Add to Tool Chest ▸ (both at the top)
  - Cut, Copy, Paste, Duplicate, Format Painter, Delete
  - "Arrange ▸", "Align ▸", Multiply… (Ctrl+Shift+D), Lock, Hide
  - "Flatten Selection", Apply to Pages…, Properties
  - Delete shows no "Del" key.
- Screenshots: `(audit screenshots) ctx_rectangle.png` and `(audit screenshots) ctx_length.png`
- **Change:**
  - Use Revu's order. Put Multiply right after Paste. "Arrange" becomes "Order", "Align" becomes "Alignment", "Flatten Selection" becomes "Flatten".
  - Move Add to Tool Chest, Set as Default, Apply to Pages and Properties to the bottom.
  - Show "Del" on Delete. Add Revu's icons.
  - Keep Duplicate and the shape-specific extras (Convert to Polygon, Exact Size, Show Size) in a group after the control-point group.

**C2. The control-point submenu (S)**
- **Revu** (`menus__tools__control-points.txt`, `curved-markups.txt`): "Control Point > Add Control Point … Subtract Control Point … Convert Control Point to Curve", plus top-level "Convert to Arc" / "Arc Segment" and "Round All Corners".
- **CalcForge** (`_fill_outline_menu`): "This outline ▸ Round corner / Remove point / Add point / Arc side / Insert break".
- **Change:**
  - "This outline" becomes "Control Point"; "Add point" becomes "Add Control Point"; "Remove point" becomes "Subtract Control Point".
  - "Arc side" becomes "Arc Segment" (or "Convert to Arc") at the top level.
  - Add "Round All Corners" at the top level.
  - "Insert break" (a CalcForge feature) stays in the submenu.

**C3. The measurement right-click menu (S)**
- **Revu** (`menus__tools__length-measurement.txt`): "right-click it and select Reset Caption Position … right-click the markup and select Flip Text".
- **CalcForge:** a Variable field, Edit Text…, Inline Text (tick), Page Scale….
- **Change:** add Reset Caption Position and Flip Text; rename "Page Scale…" to "Set Scale…". Keep the Variable field, a CalcForge feature, as the first item.

**C4. The empty-page right-click menu (S)**
- **Revu** (screenshot 141823): Paste, Add Note, Add Bookmark, Add Flag | Next Page, Previous Page | Select All, Select All Text, Deselect All Text | Print…, Look Up, Search.
- **CalcForge:** matches Revu's order, with extras: Paste in Place, Paste Here…, Insert Here ▸, Page Setup…, Page Scale…, and a viewport's scale. Select All Text is missing (text selection is a wanted feature).
- Screenshot: `(audit screenshots) ctx_page_empty.png`
- **Change:** add Select All Text and Deselect All Text when text selection lands. "Page Scale…" becomes "Set Scale…". Otherwise acceptable.

#### Group D. Document Properties, Headers & Footers and the "nothing selected" Properties panel
Code: `calcforge/ui/dialogs.py:DocumentPropertiesDialog`, `mainwindow.py:edit_header_footer` and `document_properties`, `panels.py:PropertiesPanel.show_items` (around line 2473).

**D1. Headers & Footers opens Document Properties (M)**
- **Revu** (`menus__document__create-headers-footers.txt`): "There are six boxes in the Header and Footer section representing the right, left and center … Page Number … Date … Bates Number … File Data … Font controls … Margins … Fit content inside margins … Preview".
- **CalcForge:** Document ▸ "Headers & Footers…", the thumbnail Header/Footer ▸ "Edit Wording…", and the Header & footer tab all open the "Document properties" dialog.
- Screenshot: `(audit screenshots) 013_Document_Headers_Footers.png`
- **Change:**
  - Move the tab into its own "Headers & Footers" dialog: 6 boxes, insert Page Number / Date / File Data, Font, Margins, Preview, Pages range.
  - Document ▸ Headers & Footers ▸ Add / Edit opens it.
  - Keep the Logo and Sections features inside it.

**D2. Document Properties carries settings Revu keeps elsewhere (S)**
- **Revu:** the user's name is "Preferences > General > User: Determines the user name used to track history" (`menus__revu__general.txt`). Grid is in "Grid & Snap Preferences … Grid Spacing".
- **CalcForge:** the dialog has a "Markups" tab whose only field is Author (`settings.default_author`). This is a third author setting, beside the PDF Author field and Preferences ▸ Author, and it overrides Preferences.
  - The "Grid" tab has Show grid, Grid snap (fixed "9 px, 6.75 pt") and Margin guides. Grid spacing cannot be set.
- Screenshot: `(audit screenshots) 005_Document_Document_Properties.png`
- **Change:**
  - Drop the Markups tab; Preferences "User" is the one source.
  - Move Grid to Preferences ▸ Grid & Snap and add Grid Spacing and Snap Color. Show Grid and Snap stay in View and the status bar. Margin guides stays in View ("Show Margins").
  - Title "Document Properties".

**D3. Properties panel with nothing selected (M — a wanted feature)**
- **Revu** (`menus__window__file-properties.txt`): "When no markup … is selected, the properties of the active PDF are shown in the Properties panel": File Properties (editable metadata) and Custom Properties.
- **CalcForge:** "Nothing selected. Pick a markup on the page…".
- Screenshot: `(audit screenshots) props_nothing_selected.png`
- **Change:** show the Information fields (Title, Author, Subject, Keywords, plus CalcForge's Project/Company/Description) as editable "File Properties" and "Custom Properties" sections.

#### Group E. Preferences dialog
Code: `calcforge/ui/dialogs.py:PreferencesDialog`, `calcforge/ui/preferences.py`. Coordinate with the Flatten agent (they remove `recover_flattened`) and with D2.

**E1. Layout (M)**
- **Revu** (`menus__revu__revu-preferences.txt` and `general.txt`): pages listed on the left (General, Tools, …), each with tabs: General has Options / Document / Navigation / Grid & Snap / Spelling; Tools has Markup / Measure / Sketch.
- **CalcForge:** one page with Canvas, Writing and Calculations groups; title "Preferences".
- Screenshot: `(audit screenshots) 002_CalcForge_Preferences.png`
- **Change:** a left list and tabbed pages: General (Options, Navigation, Grid & Snap, Spelling), Tools (Markup), Rendering, and a CalcForge "Calculations" page (SMath's options).

**E2. Option by option (S each)**
- **"Author"**
  - Revu: General ▸ Options ▸ "User".
  - Change: rename to "User".
- **"Mouse wheel: Zooms in and out / Scrolls up and down"**
  - Revu (Navigation): "Single Page Mode: … Zoom or Scroll … Continuous Mode: … Zoom or Scroll".
  - Change: two combos with Revu's wording.
- **"Drawing snap"**
  - CalcForge: a hidden master switch that overrides View ▸ Snap to Content/Markup/Grid (`view.py` around line 1389: `if not preferences.current().snap_while_drawing … return`).
  - Revu has no such switch; snapping lives in View, the status bar, and Grid & Snap ("Snap to options", "Sensitivity 5–25", "Snap Color").
  - Change: remove it, or replace it with Grid & Snap's Snap-to options and Sensitivity.
- **"Autosize text"**
  - Revu: Tools ▸ Markup ▸ "Autosize Text Box and Callout Markups".
  - Change: rename and move to Tools ▸ Markup.
- **"Check spelling" and "Dictionary"**
  - Revu (Spelling tab): "Enable Spell Check … Include Upper Case Words … Spell Check Color … Active Dictionary … Custom Words".
  - Change: rename, and add a Custom Words list for the words added through "Add word".
- **Stay Active**
  - Revu: Tools ▸ Markup ▸ "Reuse Tools", which is also on the status bar and in the Tools menu.
  - Change: add it here, named Reuse (see G3).
- **"Recoverable flattening"**
  - With the Flatten agent.
- **"Insertion point" and "Draw with the graphics card"**
  - These are CalcForge features. Put them on General ▸ Options and Rendering.

#### Group F. Print and Export
Code: `mainwindow.py:print_document`, `print_preview`, `export_pdf`, `export_images`, `export_markups`.

**F1. Print uses the plain Qt dialog (L)**
- **Revu** (`menus__file__print.txt`): "Preview section … Printer section … Page Range: All / Current (2) / Selected / Custom … Get Window … Size … Auto … Print: Document & Markups, Document Only, or Markups Only … Copies … Collate … Reverse … Rotation … Page Scaling: None / Fit to Paper / Reduce to Paper / Custom Scale / Fit to Margins … Center … Dim Page Content … Defaults".
- **CalcForge:** `QPrintDialog` (title "Print": Printer, Options >>), plus a separate File ▸ "Print Preview…" that Revu does not have.
  - Which pages print comes from a per-page "Print" tick in the thumbnail menu; which markups print comes from a per-markup "Print" tick in Properties ▸ General.
- Screenshot: `(audit screenshots) 008_Print.png`
- **Change:**
  - A Revu-style Print dialog with a preview pane, B0 Pages, the Print stream choice, Page Scaling, Copies/Collate and Dim Page Content.
  - Print Pages… from the thumbnails opens it with Selected.
  - Fold Print Preview into it. Keep the per-page and per-markup print flags as CalcForge extras.

**F2. File ▸ Export and Import (S)**
- **Revu** (`menus__file__file-menu.txt`): "Export: … PDF/A … TIFF, JPEG, PNG, GIF, and BMP … Text, RTF …". The Markups Summary is reached from the Markups list (⇪), Batch ▸ Summary and the Thumbnails menu ▸ Markup Summary.
- **CalcForge:**
  - "Export PDF…": Revu has no such item. The nearest is Save As or Publish As ▸ Flattened.
  - "Export Images…": a folder dialog then `QInputDialog` "Resolution (dpi)", with no format choice.
  - "Markups Summary…": a CSV save dialog.
  - File ▸ Import ▸ Pages from Document… and Import Tool Set… duplicate Document ▸ Insert and the Tool Chest. Import Tool Set… appears in three places.
- **Change:**
  - Export ▸ "Image ▸ PNG / JPEG / TIFF…", with a small options dialog (resolution, pages).
  - Rename "Export PDF…" to "Publish As ▸ Flattened…" if that is what it does. **Unsure** — check `export_io.export_pdf`.
  - Name the summary "Summary…" and also put it in the Markups List header (J1) and the Thumbnails menu.
  - Keep File ▸ Import ▸ Excel Workbook (the user asked for it).

#### Group G. Properties panel and Properties toolbar
Code: `calcforge/ui/panels.py:PropertiesPanel` and `PropertySection`; the style toolbar in `mainwindow.py:_build_toolbars`.

**G1. General section (S)**
- **Revu** (`customize-markups__properties_tab.png`; `file-properties.txt`): "Author, Subject, Label, Comments, Lock". Author comes first; Label is "Generally found only in measurements"; there is no Print tick.
- **CalcForge:** Subject, Author, Label, Comments, Modified, Lock, Print.
- Screenshot: `(audit screenshots) props_RectItem_rect.png`
- **Change:** put Author before Subject; show Label only on measurements. Keep the Print tick only if F1 keeps the per-markup flag.

**G2. Appearance and Size sections (S/M)**
- **Revu**, rectangle (`menus__tools__rectangle-tool.txt` and the cloud image): Color, Fill Color + Highlight, "Hatch" (showing "None" when there is none), Scale, Opacity, Fill Opacity, Line Width, Style. The cloud adds "Size [ ] Invert".
- **CalcForge** adds four things:
  - "Hatch Opacity" (the user's own hatch request, so keep it);
  - "Spacing ×1.00", which Revu does not have;
  - "Corner Radius", which Revu does not have — it uses Round All Corners;
  - a separate "Size" section (Measures, Exact size…, Show size) that duplicates Layout's Width and Height.
  - With no hatch set, the hatch box shows an empty swatch instead of "None".
- **Change:**
  - Show "None" text when there is no hatch.
  - Move Exact size / Show size under Layout, or drop the Size section.
  - Relabel Layout Width/Height as "Document Width" / "Document Height".
  - Check that Spacing and Corner Radius are wanted; if so, keep them at the end of Appearance.

**G3. Measurement properties (M, overlaps Group H)**
- **Revu** (`menus__tools__length-measurement.txt`): Appearance has "Fill Color … Highlight … Start and End … Each endpoint has an associated Scale … Auto … Show Caption … Edit … Show Caption Leader Line … Font Style: Bold, Italic, Underline, Strikethrough, Superscript and Subscript".
- **CalcForge:**
  - Length has no Fill Color/Highlight and a single "End Size" spin instead of a per-end Scale with Auto.
  - The caption controls are "Says", "Inline text" and "Show value" in a "Measurement" section, beside "Counts as", "Variable" and "Calibrate scale…".
  - Font Style has only B, I, U.
- Screenshot: `(audit screenshots) props_MeasureItem_length.png`
- **Change:**
  - Per-end Scale with Auto; Show Caption + Edit; Show Caption Leader Line; the full Font Style row.
  - "Counts as" looks like Revu's Subject. **Unsure** what it is — check the code; if it is a subject, merge it.
  - Keep Variable (CalcForge) in a "Calculation" section.

**G4. The Properties toolbar (M)**
- **Revu** (`properties-toolbar__*.png`; screenshot 142239):
  - Nothing selected: "[doc ▾] Name: A 201 Pages: 1 [insert page]".
  - Markup selected, in order: [markup ▾] Line: colour, %, style, width; Fill: colour, %; Hatch ▾; …; Units ▾, Caption ▾; Font, size ▾ (a combo), text colour; "Style ▾" (a menu for B/I/U/S/sup/sub); Totals ▾ for measurements.
- **CalcForge:**
  - Nothing selected: "Nothing selected ▾", disabled Line/Fill controls and "Set default".
  - Text tool: Font first, then Line and Fill; size is a "10.00 pt" spin; B/I/U are buttons; there is a "left" alignment combo and a "× 1.00" spacing spin.
  - Area tool: no Units ▾, Caption ▾ or Totals.
  - "Set default" sits on the toolbar; Revu keeps it in Properties ▸ Options.
- Screenshots:
  - `(audit screenshots) toolbar_style_nothing.png`
  - `(audit screenshots) toolbar_style_text_tool.png`
  - `(audit screenshots) toolbar_style_area_tool.png`
- **Change:**
  - Nothing selected: show Name and Pages.
  - Always order Line, Fill, Hatch, then Font.
  - Font size becomes an editable combo; B/I/U go into a "Style ▾" menu.
  - Add Units ▾, Caption ▾ and Totals for measurements (wanted).
  - Remove "Set default" from the toolbar.
  - The toolbar is named "Style" in Tools ▸ Toolbars; Revu calls it "Properties Toolbar".

**G5. Tool defaults never appear in the Properties panel (S, unsure)**
- **CalcForge:** with a drawing tool chosen, the panel still says "Nothing selected", even though its own text says "or choose a tool".
- Screenshot: `(audit screenshots) props_area_tool.png`
- **Unsure:** what Revu 21's panel shows for an active tool. The manual only says tool properties are on the Properties toolbar and in the Measurements panel. At minimum, fix the misleading text.

---

### P2

#### Group H. Measurement (overlaps the Set Scale agent — hand over together or after)
Code: `calcforge/ui/pagepanel.py:PagePanel`, `mainwindow.py:calibrate_dialog`, `viewports_dialog`, `choose_count_subject`; `view.py:_press_draw`; `widgets.py:UnitCombo`.

**H1. The "Page Setup" dock is Revu's Measurements panel under another name (M/L — a wanted feature)**
- **Revu** (`menus__window__measurements-panel.txt`):
  - "Measurements panel … measurement modes … document scale and measurement precision … Viewports".
  - Page Scale section: "Page … Add Scale to More Pages … Calibrate … Preset vs Custom … + Add Preset … Separate Y Scale … Precision".
  - Measurement Properties: "Subject, Label, Depth, Slope, Length/Area/Volume units, Show Segment Values, Show Caption, Show Centroid".
  - Opened with Alt+U.
- **CalcForge:** Window ▸ Panels ▸ "Page Setup" holds Paper, Orientation, Size, Apply to all pages; Scale, Separate Y scale, Calibrate…, Length unit, Area unit, Decimal places; and Viewports (Add / Edit… / Delete). The right-hand controls are cut off at the panel's 320 px width.
- Screenshot: `(audit screenshots) panel_dock_page.png`
- **Change:**
  - Rename it to "Measurements" (Alt+U), with a tool strip of the measure tools.
  - Sections: Page Scale (with Add Scale to More Pages and Precision), Viewports, Measurement Properties.
  - Move Paper/Orientation to Page Setup (B7).
  - This also replaces the Document ▸ "Viewports…" dialog (`dialogs.py:ViewportsDialog`) and the Document ▸ "Page Scale…" entry.
  - Fix the clipping.

**H2. Unit names (S)**
- **Revu** (screenshot 142242): "Length mm, Area sq m, Volume cu m".
- **CalcForge:** "m^2" and "m^3"; the unit combo also has blank separator rows (`dialogs_all.txt`).
- **Change:** display "sq m" and "cu m" (and so on) in measurement unit pickers.

**H3. A plain Rectangle or Ellipse asks for a page scale (S — a behaviour bug)**
- **Revu** (`menus__tools__length-measurement.txt`): "If you try to place a measurement on a page without a scale, you'll be prompted to set one."
- **CalcForge** (`view.py:_press_draw`): `scale_tools = {"rect", "ellipse", "measure_length", …}`, so drawing an ordinary rectangle on an unscaled page opens "Page scale". Seen in `(audit screenshots) 001_x.png`, which opened during a plain rectangle draw.
  - Perimeter, Diameter, Angle, Radius and Count do **not** prompt.
- **Change:** prompt for every measure tool and for no markup tool.

**H4. Tools ▸ Measure menu (S)**
- **Revu:** Set Scale first, then Length, Polylength, Area, Perimeter, Diameter, Center Radius, Angle, Volume, Polygon Cutout, Ellipse Cutout, Count, Dynamic Fill. Dimension is in Tools ▸ Markup.
- **CalcForge:** Dimension, Viewport and Calibrate (last) are in Measure.
- **Change:**
  - Put "Set Scale…" first and move Dimension to Markup. Viewport belongs in the Measurements panel.
  - Rename the tools (also used on toolbars and in Customize Toolbars): "Center radius" becomes "Center Radius", "Polygon cut-out" becomes "Polygon Cutout", "Ellipse cut-out" becomes "Ellipse Cutout", "Text box" becomes "Text Box". Labels come from `calcforge/ui/tools.py:TOOLS`.

**H5. The Count tool's own dialog (S)**
- **Revu:** Count subject and symbol are set in Properties and Measurements; there is no dialog.
- **CalcForge:** a toolbar button opens "Count tool" (Counting, Symbol: circle/square/…).
- Screenshot: `(audit screenshots) 004_Count_subject.png`
- **Change:** move these fields into Properties / Measurement Properties.

#### Group I. Tool Chest
Code: `panels.py:ToolSetsPanel.build_set_menu` and `build_chest_menu` (around lines 2105–2215), `managetoolsets.py`, the `_build_menus` Tools block.

**I1. A tool set's gear menu (S/M)**
- **Revu** (`menus__window__tool-chest-panel.txt`; screenshot 142326): Symbol, Detail | Set Scale…, Legend ▸, Disable Number Shortcuts | Edit, Export, Save, Pin ▸ | Hide.
- **CalcForge:** Symbol / List / Detail, then Paste, Add Selection, Rename Tool Set…, Delete Tool Set, New Tool Set…, Import Tool Set….
  - The set's Scale exists only as a per-tool "Scale" in the tool's right-click menu.
  - There is no Export and no Hide.
- Screenshot: `(audit screenshots) panel_dock_toolsets.png`
- **Change:** add Set Scale… / Remove Scale at set level, Export, Hide and Legend ▸ (wanted). Keep List.

**I2. A tool's right-click menu (S)**
- **Revu** (screenshot 142333 and `use-tool-chest.txt`): Duplicate, Paint Format | Create Count | Delete | Drawing Mode / Properties Mode (one toggle). "Change Colors", "Offset as".
- **CalcForge:** Use Tool, Drawing Mode, Properties Mode (two items), Scale, Move Up/Down, Copy, Rename…, Remove.
- **Change:**
  - Make Drawing Mode / Properties Mode one toggle.
  - "Remove" becomes "Delete"; "Copy" becomes "Duplicate".
  - Add "Change Colors…" (it exists for markups) and "Paint Format".

**I3. Manage Tool Sets (S)**
- **Revu** (`manage-tool-sets.txt`): "To hide a tool set, uncheck the box beside its name … up and down arrows … Add … Import … Modify … OK".
- **CalcForge:** a list with no ticks; buttons Add…, Import…, Rename…, Remove, Move Up, Move Down, Close.
- Screenshot: `(audit screenshots) 017_Tools_Tool_Chest_Manage_Tool_Sets.png`
- **Change:** add show/hide ticks and arrow buttons; "Rename…" becomes "Modify…"; buttons OK / Cancel.

**I4. Where the Tool Chest is reached (S)**
- **Revu:** the Tools menu has no Tool Chest submenu; the panel's own menu has the Tool Chest Settings (Comment Persistence, Update Tool Set Item on Reuse).
- **CalcForge:** Tools ▸ Tool Chest ▸ Manage Tool Sets… / Import Tool Set….
- **Change:** move these to the panel's Tool Chest ▾ menu; there is no Tools submenu in Revu. Minor; this could be kept as a convenience.

#### Group J. Markups List
Code: `panels.py:MarkupsPanel` (around line 837; COLUMNS at line 854).

**J1. The header (M)**
- **Revu** (`markups-list__markups-list-toolbar.png`; `menus__window__markups-list.txt`): "Markups List ▾" (Columns ▸ ticks + Manage Columns…, Markups ▸ Import/Export, Summary), a Hide Markups eye, Search, "Filter List", and Summary ⇪.
- **CalcForge:** "Filter markups…", a "By page" grouping combo, "All" and "CSV" buttons. There is no title or menu, no Hide Markups, no Columns menu and no per-column Filter List.
- Screenshot: `(audit screenshots) win_full2.png` (bottom)
- **Change:** use Revu's header row. Columns ▸ and Manage Columns…, Filter List and saved filters are wanted. "CSV" becomes Summary ⇪. The search field reads "Search". Grouping comes from sorting, as Revu groups by the sorted column.

**J2. Columns (S)**
- **Revu:** "Subject … Page Label … Page Index … Lock … Checkmark … Author … Date … Creation Date … Color … X and Y … Document Width and Document Height … Comments … Length, Area, Volume, Count and Measurement … Label … Depth … Slope … Height and Width … Unit". The Subject column shows the icon.
- **CalcForge:** Page, Type, Subject, Colour, Fill, Line, Width, Opacity, Font, Size, Value, Author, Date, Comment.
- **Change:**
  - Use Revu names: "Page" becomes "Page Label", "Value" becomes "Measurement", "Comment" becomes "Comments".
  - Merge "Type" into Subject with the icon.
  - Add Lock, Checkmark, Creation Date, Label and Unit as optional columns. Keep Fill/Line/Font/Size as optional extras, hidden by default.
  - Spelling: the user's Revu is UK-English ("Colour Processing"). Decide one spelling app-wide; today menus say "Color Processing…" while this column says "Colour".

**J3. Row right-click (S)**
- **Revu:** "Copy (the cell) … Lock … Legend … Check … Delete … Properties".
- **CalcForge:** "N selected", Colour…, Fill…, No fill, Width ▸, Line style ▸, Font size ▸, Opacity ▸, Lock / unlock, Hide, Delete.
- **Change:** add Copy (cell), Check, Properties and Legend ▸; "Lock / unlock" becomes "Lock" (a tick). Keep the batch-style items in a group.

#### Group K. Search and Bookmarks panels
Code: `calcforge/ui/searchpanel.py:SearchPanel`, `panels.py:BookmarksPanel` (around line 1330).

**K1. Search panel wording and layout (S/M)**
- **Revu** (`menus__window__search-panel.txt` and the Search tab image): Criteria (term + "Search" button; scope Current Document / Current Page / All Open Documents), Options "Search Pages … Search File Properties … Search Markups … Case Sensitive … Whole Words Only", results with checkboxes and "Replace Checked" opening a "Search and Replace" dialog. Shortcuts: "Alt+1 or Ctrl+F".
- **CalcForge:** "Find" button; ticks "Drawing", "Markups", "Case", "Whole word"; a Replace field and "Replace all" in the panel.
- Screenshot: `(audit screenshots) win_full2.png` (left)
- **Change:**
  - Use Revu's tick labels and a "Search" button; add a Current Document / Current Page scope.
  - Make results checkable (wanted) with "Replace Checked…".
  - Alt+1 opens the panel.

**K2. Bookmarks panel (S)**
- **Revu:** a "Bookmarks ▾" menu plus icon toolbar at the top (Add Bookmark …).
- **CalcForge:** Add / Rename / Delete / Contents push-buttons at the bottom and a "Page" column.
- Screenshot: `(audit screenshots) panel_dock_bookmarks.png`
- **Change:** move the buttons into a top icon strip with a header menu. Keep Contents as a CalcForge item. Bookmark tools such as AutoMark were declined, so don't add them.

#### Group L. Menu bar wording, placement and shortcuts
Code: `mainwindow.py:_build_menus` and `_build_actions`. Conflicts with B1, which edits the same function — give both to one agent or run them in sequence.

**L1. Edit menu (S)**
- **Revu** (`menus__edit__edit-menu.txt`; screenshot 141909):
  - Undo, Redo, Undo History
  - Cut, Copy, Paste, Paste in Place, Offset, Multiply… (Ctrl+M), Hide, Delete
  - Pan, Select, Select All, Lasso
  - Snapshot, Format Painter
  - PDF Content ▸ (Select Text, Edit Text, Erase/Cut Content, Mark for Redaction, Apply Redactions)
  - Check Spelling ▸
- **CalcForge:**
  - Adds Paste Here…, Duplicate (Ctrl+D), Show Hidden, Lock, Group, Ungroup, "Arrange ▸", "Align ▸", "Text ▸" and "Search" (Ctrl+F).
  - Pan, Select and Snapshot are under Tools ▸ "Navigation".
  - Redact and Whiteout are under Tools ▸ Markup. The user accepts "Whiteout" as Cut Content.
  - Apply Redactions… sits at Edit's top level.
- **Change:**
  - Add Pan, Select and Snapshot to Edit, and drop the "Navigation" submenu.
  - Add PDF Content ▸ holding Redact (as "Mark for Redaction"), Whiteout (mentioning Cut/Erase Content), and Apply Redactions….
  - "Arrange" becomes "Order"; "Align" becomes "Alignment".
- **Align item wording** (`_build_actions` around line 919: "Align left", "Align centres", "Align right", "Align top", "Align middles", "Align bottom"):
  - Revu (`toolbars__alignment-toolbar.txt`): "Align Left … Align Center … Align Middle …", plus Center in Document, Align Width/Height/Size, Distribute Horizontally/Vertically, Flip Horizontal/Vertical.
  - Change: use Revu's names. Adding Distribute and Flip is a feature decision — ask.

**L2. Shortcuts that clash with the user's Revu**
- From the screenshots and `navigate.txt`:
  - Revu Ctrl+D is Document Properties; ours is Duplicate.
  - Revu Ctrl+Shift+N is Insert Blank Page; ours is New Window.
  - Revu Ctrl+Shift+D is Delete Pages; ours is Multiply.
  - Revu Ctrl+M is Multiply; ours is Matrix (an SMath key).
  - "Fit Page — CTRL+9, Fit Width — CTRL+0, Actual Size — CTRL+8"; ours are Ctrl+0, Ctrl+1 and Ctrl+Alt+0.
  - Revu Ctrl+2 is Split Vertical; ours is Zoom to Selection.
  - Panels Alt+T, B, X, U, 1 are missing; only Alt+L exists.
  - Revu Shift+F4 is Hide Panels.
- **Change:** adopt Revu's keys.
- **Unsure:** the Ctrl+M clash with SMath's Matrix needs the user's call. One option is Ctrl+M as Matrix only in Calc mode.

**L3. Window menu (S)**
- **Revu** (screenshot 142022/142028): "Panels ▸" is alphabetical and includes "Markups Alt+L" and "Measurements Alt+U"; "Hide Panels Shift+F4"; Auto-Hide items.
- **CalcForge:** "Markups List" sits outside Panels. Panels includes "Page Setup", which becomes Measurements under H1. There is "Show Panels", "Pin Panels" and "Reset Layout", and no Alt shortcuts.
- **Change:** move Markups into Panels with shortcuts; "Show Panels" becomes "Hide/Show Panels" (Shift+F4).

**L4. Tools menu (S)**
- **Revu:** Markup ▸ (with Typewriter), Image ▸ (From File, Crop Image), Flag, PDF Content ▸, Stamp ▸, Measure ▸, Hyperlink, Toolbars ▸, "Reuse".
- **CalcForge:**
  - Markup ▸ holds Stamp, Flag, Image, Crop Image, Table, Contents.
  - Link is under "Navigation".
  - There are Selected Markups ▸, Auto-Size (Alt+Z), "Stay Active", Renumber Counts, Forget Defaults.
  - Toolbars are named Main / Tools / Calculation / Style.
- **Change:**
  - "Stay Active" becomes "Reuse", here and on the status bar.
  - "Link" becomes "Hyperlink", at the Tools top level.
  - Add an Image ▸ submenu (From File, Crop Image) and a Stamp ▸ submenu.
  - "Style" toolbar becomes "Properties Toolbar"; add Status Bar (F8) and Navigation Bar (F4) entries.
  - Move Table and Contents to the Calculation menu, or keep them as CalcForge items.

**L5. View menu (S)**
- **Revu:** "Single Page Mode", "Continuous Mode"; Split Vertical / Split Horizontal / Toggle Split / Unsplit / Synchronize Document / Synchronize Page; "Disable Line Weights".
- **CalcForge:** "Single Page" / "Continuous"; a single "Split View" tick and "Separate Views"; Zoom In/Out, Zoom to Selection and Previous/Next Page added to View.
- **Change:** rename to "Single Page Mode" / "Continuous Mode"; offer Split Vertical/Horizontal and Unsplit. The extras are harmless.

**L6. CalcForge (Revu) menu and Help (S)**
- **CalcForge:** Keyboard Shortcuts is on F1.
- **Change:** move F1 to Help. **Unsure** of Revu's exact key; the manual does not give one.

#### Group M. Status bar and navigation bar
Code: `mainwindow.py:_build_status` (around line 2003).

**M1. One row instead of Revu's two (M)**
- **Revu** (`toolbars__status-bar.txt`, `toolbars__navigation-bar.txt`, screenshot 141924):
  - Status bar: Show Grid, Snap to Grid, Snap to Content, Snap to Markup, "Reuse Markup Tools", Sync; scale "3.75 in = 30'-0"" or "Scale Not Set"; page size "42.00 x 30.00 in"; cursor coordinates.
  - Navigation bar: Unsplit / Split Vertical / Split Horizontal, One Full Page / Scrolling Pages, Pan / Select / Select Text / Zoom tool, First / Prev / page / Next / Last, Previous View / Next View, Dark Mode, Dimmer, page size, page scale.
- **CalcForge:** one row:
  - the grid/snap/Stay Active toggles; "211.7, 158.9 mm · 100 pt = 1763.8889 mm";
  - nav buttons, Dimmer, "Scale 1:50", "Fit width", "Continuous▾", "Snap▾", "Sync off ▾", "Custom 297×210", "109%".
- Screenshot: `(audit screenshots) statusbar.png`
- **Change:**
  - The scale label shows "1:50" or "Scale Not Set" instead of "Scale 1:50".
  - Page size shows "29.70 x 21.00 cm" in ruler units, instead of the paper name.
  - The page-mode combo becomes two icons; add Pan/Select tool buttons, split buttons and Previous/Next View.
  - Splitting this into two bars is a larger, optional step.

---

### P3 — Smaller dialogs and wording

#### Group N. Small dialogs, one per file
- **N1. Dialog titles in sentence case (S).** Revu uses Title Case and its own names. Rename:
  - "Page setup" to "Page Setup"; "Document properties" to "Document Properties"; "Page scale" to "Set Scale" (Set Scale agent)
  - "Keyboard shortcuts" to "Keyboard Shortcuts"; "Check spelling" to "Check Spelling"
  - "Add bookmark" to "Add Bookmark"; "Rename page" to "Rename Page Label"
  - "Insert PDF pages" to "Insert Pages"; "Add pages" to "Insert Blank Page"
  - "Multiple" to "Multiply" (the menu says Multiply…); "Calibrate scale" to "Calibrate"
  - "Tools on the toolbar" to "Customize Toolbars"; "Export markups" to "Summary"; "Apply to pages" to "Apply to Pages"
  - Files: `dialogs.py` throughout, `mainwindow.py` `QInputDialog` titles.
- **N2. Check Spelling (S)**
  - Revu (`menus__edit__spell-check.txt`): "Ignore Once … Ignore All … Add to Dictionary … Change … Change All".
  - CalcForge (`dialogs.py:SpellingDialog`): Change / Ignore / Add word / Stop.
  - Screenshot: `(audit screenshots) 010_Spelling.png`
  - Change: use Revu's five buttons plus Close.
- **N3. Link / Hyperlink (S)**
  - Revu (`menus__tools__hyperlink-tool.txt`): the tool is "Hyperlink"; "Release the mouse button and the Action dialog appears".
  - CalcForge (`dialogs.py:LinkDialog`): a "Link" dialog with "Go to: Page/View/File/Web".
  - Screenshot: `(audit screenshots) 012_Link.png`
  - Change: title "Action". Use Revu's action names: "Jump to Page", "Open File", "Open URL", "Snapshot View" for View.
  - **Unsure** of Revu 21's exact action list; the manual page only says "Action dialog".
- **N4. Customize Toolbars (M)**
  - Revu (`toolbars__customize-toolbars_dialog-box.png`): Categories, Commands, Toolbar list (+ / gear / ×), Items with arrows and separator; Apply / OK / Cancel.
  - CalcForge (`dialogs.py:ToolbarDialog`): a tick list of tools for the Tools toolbar only.
  - Screenshot: `(audit screenshots) 018_Tools_Toolbars_Customize_Toolbars.png`
- **N5. Hatch Patterns (M)**
  - Revu (`toolbars__hatch-patterns.txt`): "Hatch > Manage … Manage Hatch Pattern Sets dialog … Add … Modify … Hatch Pattern Editor … Line, Small Dot, Large Dot, Delete".
  - CalcForge (`hatchpatterns.py:HatchPatternsDialog`): "Hatch Patterns" — one flat list with Import… / New… / Remove / Close.
  - Screenshot: `(audit screenshots) 006_Hatch_Manage.png`
  - Change: use sets with Add / Modify / Remove / Export.
  - The line-style list has **no "Manage…" entry at all**, though Revu's style menu has one and the custom line-style editor is wanted (`toolbars__custom-line-styles`).
- **N6. Keyboard Shortcuts (S, low)**
  - CalcForge (`ShortcutManagerDialog`): tabs "Shortcuts" / "Mouse and canvas", columns Group / Command / Shortcut / Default / Where, buttons Clear / Reset one / Reset all.
  - Revu has Import/Export and Reset All.
  - Screenshot: `(audit screenshots) 003_CalcForge_Keyboard_Shortcuts.png`
- **N7. Rename page label is a modal prompt (S)**
  - Revu: "Re-Label: Makes the label of the current page editable" — edited in place on the thumbnail.
  - CalcForge (`mainwindow.py:rename_page`): `QInputDialog` "Rename page".
  - Change: edit the label in place on the thumbnail.
- **Already matching Revu, no change:** Change Multiple Colors (`(audit screenshots) 007_Change_colors.png` against `00_change-multiple-colors_dialog-box.png`), Color Processing, the ruler right-click units, the Dimmer menu, Undo History.

---

### Things I'm not sure about
- **Multiply (`ArrayDialog`):** I could not find Revu 21's Multiply UI in the manual. It may be an on-canvas mode rather than a dialog. Only the title mismatch ("Multiple") is certain.
- **"Counts as" in measurement Properties:** I did not trace what it maps to.
- **Whether Revu 21 has a Tools ▸ Tool Chest submenu:** the Revu 21 Tools-menu page does not list one; older Revu versions did.
- **Page Setup:** whether the user wants Revu's content-resize behaviour (Scale, Offset, Rotation, Fit to Media) or only its fields.
- **Default Fill Opacity:** CalcForge's rectangle starts at 35 % with no fill. I did not confirm Revu's default.

### Suggested split for fix agents
Each item below touches different code, so they can run in parallel. Where two share a file, they edit different functions or classes.

1. **B + A1/A3:** page dialogs plus the shared Pages control (`dialogs.py` page dialogs; `mainwindow.py` page methods and `page_menu`).
2. **L + B1:** menu bar (`mainwindow.py:_build_menus` and `_build_actions`). Run after or alongside agent 1, since both touch the Document menu block.
3. **C:** right-click menus (`mainwindow.py:build_context_menu` and `_fill_outline_menu`).
4. **D + E:** Document Properties, Headers & Footers and Preferences (`dialogs.py:DocumentPropertiesDialog` and `PreferencesDialog`, `preferences.py`). Coordinate with the Flatten agent.
5. **G + D3:** Properties panel and Properties toolbar (`panels.py:PropertiesPanel`; the style toolbar in `_build_toolbars`).
6. **H:** Measurements panel (`pagepanel.py`, `view.py:_press_draw`, `widgets.py:UnitCombo`). Coordinate with the Set Scale agent.
7. **A2 + I + J + K:** Thumbnails header, Tool Chest, Markups List, Search and Bookmarks. These are separate classes in `panels.py` and `searchpanel.py`; split further if wanted.
8. **F:** Print and Export.
9. **M:** status bar.
10. **N:** small dialogs and wording.

