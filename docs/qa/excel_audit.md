# Excel audit of the workbook view (2026-10-22)

This audit compares CalcForge's spreadsheet workbook view with Excel for Microsoft 365 on Windows. It was asked for after the user said: "the horizontal scroll at the bottom is very small and not adjustable, issues with cursors".

**How it was done**
- Branch `claude/admiring-archimedes-i371m1` at d8b485a. No app code was changed.
- CalcForge was run headless (offscreen, window 1280×860, zoom 100 %) with real `QMouseEvent`, `QTest` key and wheel events. Cursors were read from `view.viewport().cursor()`; zones from `TableEditor._zone`.
- Scripts: `/tmp/claude-0/-home-user-Test/612018b6-a7e0-52c2-960e-e0bdb34e3bba/scratchpad/excel_audit/p1_chrome.py` to `p7_scrolled.py`, with `harness.py` in the same folder.
- Screenshots are in `/tmp/claude-0/-home-user-Test/612018b6-a7e0-52c2-960e-e0bdb34e3bba/scratchpad/excel_audit/shots/`. The tables below give file names only. The scratchpad does not outlast the session; the scripts rebuild the screenshots.
- Excel's behaviour comes from Microsoft's pages where one exists, otherwise from a named third-party guide. Rows marked **unverified** could not be confirmed from a source, or headless.
- Already being fixed by another agent, so not repeated here: the select-all corner, and a one-page print area for a new sheet.

**Severity:** blocker = the user named it and it stops the task; major = clearly not Excel and gets in the way; minor = polish.

**Totals: 40 findings — 2 blocker, 10 major, 28 minor.**

---

## 1. Horizontal scroll bar and the tab/scroll-bar splitter (the user's first point)

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| A1 | The tab area and the horizontal scroll bar share the row. `Window.TabRatio` sets the split, default **0.6**: tabs about 60 %, scroll bar about 40 %. [learn.microsoft.com TabRatio](https://learn.microsoft.com/en-us/office/vba/api/excel.window.tabratio) | The scroll bar is squeezed to **80 px of a 636 px row (13 %)**. The tab strip takes **556 px even with one tab**, mostly empty space before the ×. This is the same with 1, 8 or 20 sheets. Thumb 32×12 px. `p1_scrollrow.png`, `p1_window.png`, `p1_bottom_zoom.png` | blocker | `mainwindow.py` (`addScrollBarWidget(sheet_tabs, Qt.AlignLeft)`, around l.1175 and l.3781) and `SheetTabs.__init__`. The strip is `Preferred` with the tab bar at stretch 1, so it takes all spare room. Give `SheetTabs` a width of `ratio × row width`, set on each resize of the `qt_scrollarea_hcontainer` (event filter), with `ratio` 0.6 by default. The tab bar scrolls inside that width. |
| A2 | A splitter at the scroll bar's left edge: "hover … until you see the double-headed arrow … drag the arrow to the right until you see the complete tab name". Dragging left gives the bar more room. [support: Where are my worksheet tabs?](https://support.microsoft.com/en-us/excel/where-are-my-worksheet-tabs). The ratio is saved with the workbook (`TabRatio`, above). | **No splitter.** The tabs/bar boundary (x 555/556) has the plain arrow cursor, and nothing there can be dragged. The split is fixed. | blocker | Add a 6 px handle widget (three dots painted, `Qt.SplitHCursor`) between `SheetTabs` and the scroll bar, in `sheettabs.py` and placed with `addScrollBarWidget`. Dragging it sets the ratio (clamped to 0–1, 0 hides the tabs). Keep the ratio per workbook (beside `scene.sheet_zooms`). Read and write the xlsx `workbookView/@tabRatio` in `calcforge/sheet/xlsx.py`. |
| A3 | The scroll bars' size "is normally determined by the dimensions of the used range". The thumb is large on a small sheet and grows back once you return. [exceloffthegrid](https://exceloffthegrid.com/resetting-the-scroll-bar-in-excel/) | The grid only ever grows (`scene.sheet_extent = max(now, …)`). After ten drags to the end, the vertical thumb is **164 → 40 px**, and it **stays 40 px back at A1** (rows 122 → 492). The horizontal thumb sits at the 32 px minimum. `p6_after_scrolling.png` | major | `sheetview.fill()`: when scrolled back, shrink the extent to max(used range, visible window + `AHEAD`) instead of keeping the maximum. Apply `_keep_whole` after a shrink too. |
| A4 | Standard Windows scroll bars with arrow buttons at both ends (exact Excel width **unverified**, about 17 px at 100 %). | Vertical bar 12 px with an 8 px handle. Horizontal handle 12 px tall inside a 24 px row. **No arrow buttons** (`theme.py`: `add-line`/`sub-line` width 0). | minor | `theme.py`, the `QScrollBar#sheetRowScroll` rules and the view's vertical bar while `sheetview.is_on`: give them arrow buttons and about 16 px, as on Windows. |
| A5 | While the vertical thumb is dragged, a tip shows "Row: N" (**unverified**: no source found). | No tip. | minor | `sheetview._Watch`: on `sliderMoved`, `QToolTip` with the top row (or column). |

## 2. Cursors (the user's second point): every place one differs

Matching Excel already:
- the white thick cross over cells, and the black ↓ / → over the headings when they are not scrolled away;
- split ↔ / ↕ on heading edges, with a ±3 px band (`p3_cursors.py`);
- the thin cross on the fill handle;
- the I-beam in the cell editor, formula bar and Name Box;
- the format-painter brush.

The differences:

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| B1 | In Normal view the page-break lines are inert. They are dragged only in Page Break Preview, where "you can drag the blue lines to change the print area or page breaks". [support: Insert, move, or delete page breaks](https://support.microsoft.com/en-us/Excel/insert-move-or-delete-page-breaks-in-a-worksheet) | In the workbook (Normal) view, the dashed page line (J\|K) and the print area's right edge are drag handles in a **±3 px band down every row**. Over cells that band shows **↔ (SplitH)**, at x = 502 and 504 at row 10. A drag that starts 1 px inside K10, meant to select K10:L10, **set print area A1:L48** (the undo stack read "Set print area"). `p5_drag_on_dashed_line.png`, `p5_dashed_zoom.png` | major | `TableEditor._zone` (tableedit.py l.904–918) returns `area`, `break` and `vbreak` even when `sheetview.is_on(window)` is true. Return them only in a Page Break Preview mode (I1). Make the same change in `TableEditor.edge_cursor`, used by `view._update_hover_cursor`. |
| B2 | Headings always show resize cursors on their edges, and a drag resizes. [support: Change the column width and row height](https://support.microsoft.com/en-US/excel/change-the-column-width-and-row-height) | Once scrolled, the headings kept in view (the `SheetHeadings` overlay) **never show ↔/↕**: on an edge they show the ↓ / → arrow. A drag from a column edge **selected column G instead of resizing** (width stayed 48). `p7_scrolled.png` | major | `SheetHeadings.hit()` should return `col_edge`/`row_edge` with `tableedit._edge_near`. `view._update_hover_cursor` (l.3813) should use `tableedit._cursor_for` instead of `excel_cursor(hit[1][0])`. `TableEditor.mouse_press` then passes the edge to `_press_zone` as it already does on the sheet. |
| B3 | On the selection's border Excel shows "the White Arrow with a smaller 4-headed black arrow". When copying (Ctrl) "a small cross appears". [Dickinson College, Excel pointer shapes (PDF)](https://www.dickinson.edu/download/downloads/id/2558/excel_pointer_shapes_pdf); [support: Move or copy cells](https://support.microsoft.com/en-us/office/move-or-copy-cells-and-cell-contents-803d65eb-6a3e-4534-8c6f-ff12d1c4139e) | `Qt.SizeAllCursor`: the bare four-headed arrow, no pointer arrow. **With Ctrl held it does not change.** | minor | `tableedit._CURSORS["border"]` → `cursors.move_cursor()` (the arrow with the MOVE sign already exists). With Ctrl, use the arrow with the COPY sign. Refresh it on Ctrl key press and release (view `keyPressEvent`/`keyReleaseEvent`, which call `_hover`). |
| B4 | The move pointer appears on the selection's border line (exact width **unverified**). | The band is ±3 px on **both** sides of the border. On a single 15 px cell, the top and bottom 3 px inside it (6 of 15 px) show the move cursor, so a click-drag there moves the cell instead of selecting. | minor | `TableEditor._zone`: about 1 px inside the border and 3 px outside. |
| B5 | Page Break Preview: hovering a break gives a double-headed arrow, plain ↔ / ↕ (third-party: [thebricks](https://www.thebricks.com/resources/how-to-move-a-page-break-in-excel)). | Page breaks and print-area edges use `SplitVCursor`/`SplitHCursor`, the same as the heading-resize cursor, so the two cannot be told apart. | minor | `_CURSORS["break"]`, `["vbreak"]` and `_cursor_for` for `area` → `Qt.SizeVerCursor`/`Qt.SizeHorCursor`. |
| B6 | Windows cursors are drawn for the display's scale. | `view.excel_cursor` draws the cell, column and row cursors as **32×32 bitmaps at pixel ratio 1**, unlike `cursors.py`, which draws at `screen_ratio()`. On a 125–200 % Windows display they are probably scaled up blurry, or small. **Unverified headless.** | minor | `view.excel_cursor`: draw at `cursors.screen_ratio()` (`setDevicePixelRatio`), as `cursors.py` does. |
| B7 | HYPERLINK cell: a single click follows the link. To select the cell, "click and hold … until the pointer changes" to the cross. [support: HYPERLINK function](https://support.microsoft.com/en-us/excel/hyperlink-function) | Hand cursor, and **Ctrl**+click follows (Word's rule). | minor | `TableEditor.mouse_press` and `hover_cursor`: a plain click follows; a press held about 0.5 s selects instead. |
| B8 | The double-headed arrow at the tab/scroll-bar boundary (A2). | Plain arrow (A2). | — | (counted in A2) |
| B9 | Over the select-all corner: **unverified** which cursor Excel shows (believed to be the white cross). | Arrow. | minor | Check against Excel when the corner fix (another agent) lands. |
| M1 | Below the tab row is the status bar, with no other control between them. | An 8 px `QSplitterHandle` (the collapsed Markups List, `qt_splithandle_markupsList`, ↕ cursor) sits between the sheet-tab row and the status bar (y 820–828). A pointer coming down to the scroll bar meets a ↕. `p1_bottom_zoom.png` | minor | `mainwindow.py`, `markupsSplit`: hide or disable that handle while `sheetview.is_on`. |

## 3. Sheet tab bar

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| C1 | Order from the left: ◀ ▶ tab-scroll arrows (with … when tabs are hidden), the tabs, ⊕ New sheet after the last tab, then the splitter and the scroll bar. Ctrl+click an arrow goes to the first or last tab. [support: Insert or delete a worksheet](https://support.microsoft.com/en-us/Excel/get-started/insert-or-delete-a-worksheet); [GCFGlobal](https://edu.gcfglobal.org/en/excel-tips/jump-to-any-sheet-with-a-shortcut/1/) | **+ at the far left**. Qt's 16 px ◀▶ at the **right end** of the tab area appear only when the tabs overflow. The first tab is then cut ("heet6"). A × (Close Workbook) sits after the tabs. `p2_tabrow_11.png`, `p6_tabs6.png` | major | `SheetTabs.__init__`: add its own always-shown ◀ ▶ buttons on the left (`bar.setUsesScrollButtons(False)`, then scroll by moving the first shown tab), Ctrl+click to the ends, + after the last tab, × last. |
| C2 | Right-click a tab-scroll arrow: a list of all sheets (Activate). [GCFGlobal](https://edu.gcfglobal.org/en/excel-tips/jump-to-any-sheet-with-a-shortcut/1/) | Nothing. | minor | A `QMenu` of `SheetTabs.entries` on the new arrows; picking one calls `go(i)`. |
| C3 | Double-click a tab: its name is edited **in place** on the tab. [support: Insert or delete a worksheet](https://support.microsoft.com/en-us/Excel/get-started/insert-or-delete-a-worksheet) | A `QInputDialog` "Rename sheet" opens (seen in `p6_scroll.py`). | minor | `SheetTabs._rename`: a `QLineEdit` over `bar.tabRect(i)`; Enter commits, Esc cancels. |
| C4 | The tab shows the bare name; the active tab is white with green bold text and a green underline. | Each tab is labelled "▦ Sheet1". The active tab is only slightly lighter. | minor | `SheetTabs._fill`: no "▦ " prefix. Style the current tab in `theme.py` `#sheetTabs QTabBar::tab:selected`. |
| C5 | Shift+F11 inserts a new worksheet. [support: Keyboard shortcuts](https://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f) | Nothing (tabs 6 → 6). | minor | `shortcuts.SHEET_KEYS` + `SHEET_COMMANDS`: add `new_sheet` → `window.sheet_tabs.new_sheet` (Excel puts it before the active sheet). |
| C6 | The tab menu has Insert, Delete, Rename, Move or Copy, View Code, Protect Sheet, Tab Color, Hide, Unhide and Select All Sheets. | It has Insert Sheet, Delete, Rename…, Print, Go To and Close Workbook (`build_menu` says Move or Copy and Tab Colour are left out on purpose). | minor | Note only; Hide/Unhide sheet would be the next one to add. |

## 4. Status bar, view buttons, zoom

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| D1 | On the left, the Cell Mode: **Ready / Enter / Edit / Point**. **Average, Count and Sum** of the selection, on by default. [support: Excel status bar options](https://support.microsoft.com/en-gb/office/excel-status-bar-options-6055ecd9-e20f-4a7a-a611-4481bd488c55) | No mode and **no Average/Count/Sum** (F1:F3 = 1, 2, 3 selected). It shows the canvas position "**-3527735.4, 24.0 mm**" (meaningless in the workbook view), the page box "2 of 2", Scale Not Set, Fit Width, Continuous, Snap, Sync, A4 and the zoom box. `p4_status_with_F1F3.png` | major | `mainwindow` status bar: while `sheetview.is_on`, hide the position, scale, snap and layout controls. Show a mode label (from `TableEditor`: editor open and `_pointing()`) and Average/Count/Sum, refreshed from `TableEditor.select` (cache it; the selection can be a whole column). |
| D2 | View buttons Normal / Page Layout / Page Break Preview. A zoom slider with − / + buttons, and the zoom %, which opens the Zoom dialog. [same page](https://support.microsoft.com/en-gb/office/excel-status-bar-options-6055ecd9-e20f-4a7a-a611-4481bd488c55); [support: Zoom in or out](https://support.microsoft.com/en-us/excel/zoom-in-or-out-of-a-document-presentation-or-worksheet) | No view buttons; a "100%" combo box, with no slider. | minor | Three status-bar buttons: Normal = workbook view, Page Layout = page view, Page Break Preview = I1. Add a slider beside the zoom box. |
| K1 | Ctrl+wheel zooms (third-party: [exceldemy](https://www.exceldemy.com/learn-excel/worksheets/zoom/)). The step per notch is **unverified**. | ×1.2 per notch: 100 → 120 → 143 → 172 → 205, and down 84, 70, 58, 49. | minor | Check against Excel. If Excel steps by fixed amounts, round to them in the view's Ctrl+wheel zoom. |

## 5. Name Box and formula bar

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| E1 | The Name Box shows "4R x 3C" only while the mouse drags. After release it shows the active cell (**unverified** source; Excel's long-standing behaviour). | It still reads "**4R × 3C**" after the Shift-click or drag has finished. | minor | Where tableedit writes the "R × C" text: only while `self.drag` is a select drag; otherwise the active cell. |
| E2 | ✗ Cancel and ✓ Enter buttons beside **fx** (which opens Insert Function). An expand arrow and Ctrl+Shift+U make the bar taller, and its bottom edge drags. The Name Box widens by dragging the dots. [exceljet](https://exceljet.net/shortcuts/expand-or-collapse-the-formula-bar), [MrExcel](https://mrexcel.com/excel-tips/long-formulas-in-the-formula-bar); Ctrl+Shift+U is on the [shortcuts page](https://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f) | fx is a `QLabel`, so clicking it does nothing. No ✗/✓. The field is one line and cannot be expanded or resized. The Name Box is fixed at 110 px. `p1_formulabar.png` | minor | `FormulaBar.__init__` (tableedit.py about l.175): fx as a button opening the formula help, ✗/✓ while editing, a multi-line field with an expand toggle (Ctrl+Shift+U), and a splitter after the Name Box. |
| E3 | F2 while typing a formula toggles Point mode, so the arrow keys move the caret. [shortcuts page](https://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f) | Point mode itself works (= then ↓ gives =E6, the references are coloured in the bar and outlined on the grid; `p4_pointmode_zoom.png`). But **after F2, ← still replaced the reference** (D5 → C5) instead of moving the caret. | minor | The cell editor's key handling: F2 flips a flag that `_pointing()` honours. |

## 6. Selection and keyboard

What worked: click, Shift+click, drag, Ctrl+arrows within data (F1 → F3), Ctrl+Home, Enter moves down, Tab Tab Enter goes back to the starting column (A2), typing replaces, Esc cancels an entry (H1 kept 5), F2 puts the caret at the end, and Shift+wheel scrolls across.

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| F1 | Esc only "cancel[s] an entry in the cell or formula bar". There is always an active cell, and typing goes into it. [shortcuts page](https://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f) | Esc in Ready mode **closes the sheet's editing**: no active cell, a blank Name Box, and the formula bar reads "click a cell". **Typing "7" afterwards does nothing.** The hint itself says "Esc to close it". `p7_sel_and_esc.png` | major | `TableEditor.key_press`, the Escape branch: when `sheetview.is_on(window)`, never `close()`; only clear `copied` (the marching ants). Change the status hint too. |
| F2 | Ctrl+click or Ctrl+drag adds another range; Shift+F8 adds with the keys. [shortcuts page](https://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f) | Ctrl+click A9 **replaced** the selection, leaving A9 alone. Only one range is supported. | major | A selection model with a list of ranges in `TableEditor` (`select`, `selection`, drawing in `items/table.py`). Commands that need one range say so, as Excel's "This command cannot be used on multiple selections". |
| F3 | Ctrl+Space selects the whole column (C:C, 1,048,576 rows). Ctrl+↓ in an empty column goes to row 1,048,576, and Ctrl+→ to XFD. [shortcuts page](https://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f) | The selection is limited to the grid grown so far: Ctrl+Space gives "122R × 1C", Ctrl+↓ stops at B122, Ctrl+→ at AY6. Ctrl+A and the headings likewise. | minor | `SHEET_COMMANDS` `select_*` and `TableEditor._jump`: in the workbook view, use the sheet's limits (1,048,576 × 16,384), held as "whole column/row" rather than as cells. Let `sheetview.fill` grow the grid to the target. |
| F4 | Ctrl+A inside data selects the current region first; pressed again, the whole sheet. [shortcuts page](https://support.microsoft.com/en-us/office/keyboard-shortcuts-in-excel-1798d9d5-842a-42b8-9c99-9b7213f0040f) | It selects the whole grid at once, from inside F1:F3 too. | minor | `SHEET_COMMANDS["select_all"]`: the current region (data_area around the active cell) first. |
| F5 | Page Down / Page Up move one screen and scroll the window with the cell. | They move 10 rows (D4 → D14) and do not page the window. | minor | `TableEditor.key_press`: step = rows visible in the viewport, and scroll by the same amount. |
| F6 | One wheel notch scrolls 3 rows (Windows' default "3 lines"; **unverified** for Excel). | One notch scrolls 30 px = 2 rows. | minor | The view's wheel handler in the workbook view: lines × the default row height. |

## 7. Mouse editing and headings

What worked:
- the fill handle (1, 2 → 3…6);
- dragging the border moves the cells;
- double-clicking an edge autofits (E 48 → 171);
- hidden column B shows as a double line in the headings (`p5_hidden_zoom.png`);
- the cell and heading right-click menus are close to Excel's (Insert Columns Left/Right, Column Width…, Hide/Unhide).

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| G1 | Shift + drag of the border cuts and inserts. [support: Move or copy cells](https://support.microsoft.com/en-us/office/move-or-copy-cells-and-cell-contents-803d65eb-6a3e-4534-8c6f-ff12d1c4139e) | Not supported (only Ctrl to copy). | minor | `TableEditor` release, the `move` branch: with Shift, `insert_cells` at the target, then `move_block`, with an insert-line preview. |
| G2 | While a column edge is dragged, a tip at the pointer reads "Width: 10.71 (80 pixels)", in characters of the default font. [support: Change the column width and row height](https://support.microsoft.com/en-US/excel/change-the-column-width-and-row-height) | The status bar reads "Width: 78.00 pt (104 pixels)". No tip at the pointer. `p5_col_resize_zoom.png` | minor | The `col_size`/`row_size` drag in tableedit: `QToolTip.showText` at the pointer, with the width in characters (pixels) and the row height in points (pixels). |
| H1 | At 100 % the default column is 8.43 characters = **64 px** and the default row 15 pt = **20 px** at 96 DPI. [support: Change the column width and row height](https://support.microsoft.com/en-US/excel/change-the-column-width-and-row-height); [excel-easy](https://www.excel-easy.com/examples/autofit.html) | At "100 %" one point is one pixel: columns **48 px**, rows **15 px**, headings 12 px tall and 22 px wide. That is Excel's **75 %**, so text and headings look small next to Excel. `p1_corner_zoom.png` | major | A decision for the user. Option: in the workbook view, show 100 % as a scale of 96/72 (`sheetview.enter` default zoom 4/3, and the zoom box shows the value × 0.75). The page view stays as it is. |
| H2 | The headings stay one size whether frozen or not; the corner box stays at the top left. | Scrolled, the kept-in-view strips are **14 px / 24 px** (`max(14, …)`, `max(24, …)` in `SheetHeadings.refresh`), while the sheet's own are 12 / 22. The headings jump in size as they detach, and the overlay has **no corner box**: row "20" is drawn in the corner. `p7_scrolled.png` | minor | `SheetHeadings.refresh`/`paintEvent`: use the sheet's own heading sizes, and paint the corner (tie it to the corner fix). |
| H3 | Normal view shows page breaks only once printed or previewed, or with File ▸ Options ▸ Advanced ▸ **Show page breaks**. [support: Insert, move, or delete page breaks](https://support.microsoft.com/en-us/Excel/insert-move-or-delete-page-breaks-in-a-worksheet) | A brand-new empty sheet shows a dashed page line at J\|K at once. `p1_window.png` | minor | `items/sheetpage.py` (the break pens): draw them only when a per-sheet "Show page breaks" option is on (default off until Print or Sheet Layout has been used). |
| H4 | In Normal view the print area is drawn with a thin line; blue is Page Break Preview's (**partly unverified**). | After Set Print Area, the workbook view draws a thick solid blue edge. `p5_dashed_zoom.png` | minor | `items/sheetpage.py` `_edges` drawing: a thin grey line in the workbook view; blue only in I1. |

## 8. Page Break Preview, print area, freeze panes

| # | Excel | CalcForge (observed) | Sev | Fix |
|---|---|---|---|---|
| I1 | Page Break Preview: "dashed lines are page breaks Excel automatically added. Solid lines are page breaks that were added manually" ([support: View page breaks](https://support.microsoft.com/en-us/excel/view-page-breaks)). The print area is white with a bold blue outline, everything outside it grey, a grey "Page N" watermark on each page, and the blue lines drag ([Access Analytic](https://accessanalytic.com.au/?p=1074), third-party, from a search summary). | **No Page Break Preview mode.** The workbook view looks like Normal view, yet lets the breaks and print-area edges be dragged (B1). The page view is the Page Layout view. "Page N" shows only on pages in the page view. | major | `sheetview.py`: a third mode (`scene.sheet_mode = "break_preview"`), chosen from the D2 view buttons. `items/sheetpage.py` paints grey outside the print area, blue solid and dashed lines and a "Page N" watermark there. The `area`, `break` and `vbreak` zones in `TableEditor._zone` are enabled only in this mode. |
| J1 | View ▸ Freeze Panes (rows above and columns left of the selected cell), Freeze Top Row, Freeze First Column, Unfreeze; and Split. [support: Freeze panes](https://support.microsoft.com/en-us/Excel/get-started/freeze-panes-to-lock-rows-and-columns) | **None.** Only the headings are kept in view (`grep -i freeze` finds nothing in the UI). | major | A per-sheet `freeze = (rows, cols)` in `calcforge/sheet` (saved, and read and written as the xlsx `pane`). Draw the frozen cells in a `SheetHeadings`-like overlay that does not scroll. The Name Box, Ctrl+Home and scrolling respect it. |

## Not verifiable here

These could not be checked headless or from a source:
- how big the cursors look on the user's Windows scaling (B6);
- Excel's own Ctrl+wheel step (K1);
- Excel's cursor over the select-all corner (B9);
- the exact width of Excel's scroll bars and move band (A4, B4);
- the Name Box after a drag (E1);
- the "Row: N" scroll tip (A5).
