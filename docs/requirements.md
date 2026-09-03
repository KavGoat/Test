# Everything asked for, and where it stands

Built from all 154 messages, in order. Each line says which message asked for
it. **Done** means the behaviour is in the code and a test holds it there;
**Outstanding** means it is not built yet. Checked against the code, not
against memory.

## The foundations (messages 1–20)

- [x] Unit-aware calculation engine, SMath-style — m1
- [x] Bluebeam-style markup on the same page — m1
- [x] Insert PDF pages — m1
- [x] Spreadsheet tables that can use the variables — m1
- [x] Page-by-page A4 document, printable — m1
- [x] Double-click edits a block, line or cell — m9
- [x] Arrow keys move the caret in edit, not the whole item — m9
- [x] A block keeps its own names, and can still read the globals — m9, m11
- [x] Blocks default to *not* self-contained, with a right-click toggle — m11, m71
- [x] Shortcuts: C cloud, R rectangle, Q call-out, Alt+M dimension — m10
- [x] Optional page scale, and measuring to it — m10
- [x] Measure: M length, Shift+Alt+A area, P polygon, A arrow — m10
- [x] Only length, area and rectangle are scaled — m10
- [x] Rectangle asks for width and height — m10
- [x] Move or duplicate an item by x, y times — m10
- [x] Background calculation verifier — m12
- [x] Paste cells from Excel as a table — m12
- [x] Numerical validation against published worked examples — m13, m14
- [x] Bluebeam-like interface, its icons and names — m14, m48, m57, m63
- [x] Rectangle carries its dimension — m16 (later: in properties only, m34)
- [x] Desk background behind the page, continuous scroll and zoom — m19
- [x] Toolbars customisable and dockable left/right — m20
- [x] Panels pin, hide and are remembered — m20
- [x] Dark mode — m20
- [x] Shortcut manager, and no tool chords while typing — m20

## The first real pass (messages 22–35)

- [x] Q: click the arrow head, then the box — m22, m34, m38
- [x] Spreadsheet formulas by clicking cells after `=` — m22
- [x] A unit is taken on Tab, not automatically — m22
- [x] Unit list completes with the arrows, and lists the variables — m22, m87
- [x] Only lines ending in `=` show a result — m22
- [x] Change the unit a result is shown in — m22
- [x] Units in blue — m22
- [x] One equation view, edited in its printed form — m22, m49, m67, m103, m132
- [x] Insert PDF pages, with the 3-dot toolbar grips — m23
- [x] Multiply on the shortcut list — m23
- [x] Narrower, even page border — m23, m65
- [x] Header and footer: page number, date, title, custom, logo — m23
- [x] Reference panels grouped in one dock, hideable and resizable — m23
- [x] Page right-click: delete, duplicate, insert before/after, PDF, photo — m23
- [x] Excel paste spills across cells — m23
- [x] The maths key is `/` — m24
- [x] Every setting remembered — m24
- [x] Inserting a table asks for rows and columns — m25
- [x] Inserted PDF pages are not blank — m25
- [x] "Calculation line" and "Calculation block" as separate tools — m25
- [x] Page right-click sets the scale — m25
- [x] Per-page setup: rotate, page size — m25
- [x] Calibrate: pick two points, type the distance — m25
- [x] The scale shows beside the page number — m25, m31
- [x] Bookmarks — m25, m32, m60
- [x] Click-by-click measuring, no measurement from nowhere — m25
- [x] Plots: obvious how to add and edit a formula — m26
- [x] One shortcuts window, not two — m27
- [x] Dark-mode icons for undo and redo — m28
- [x] Cloud call-out — m29
- [x] Highlight anywhere — m29
- [x] Shift constrains every drawing tool — m29, m40
- [x] Ellipse, circle on Shift, carrying its size — m29
- [x] Snapshot on G — m29
- [x] Change the colours in a snapshot or a page — m29
- [x] Ctrl-drag copies; Shift moves on an axis; Ctrl suspends snapping — m29, m136
- [x] Snap to grid and snap to what is drawn — m29, m72
- [x] Linear interpolation — m30
- [x] Named tables, and a look-up by column — m30
- [x] Table of contents from the bookmarks, clickable in the PDF — m32
- [x] Rectangle shows nothing; its size is in properties — m34

## Tool sets, call-outs and the interface (messages 36–65)

- [x] Set the current properties as the default — m36
- [x] Tool sets, with groups, a copy mode and a properties mode — m36, m41
- [x] My Tools, numbered, on the number keys — m36
- [x] Group and ungroup — m36
- [x] The leader joins the middle of a side, and the elbow slides — m38
- [x] Ctrl-copying a call-out takes its arrow with it — m38
- [x] A preview before anything is placed — m38, m41
- [x] Type a dimension's text in place, not in a dialog — m38
- [x] A group shows one box, and goes into a tool set as one thing — m38
- [x] Excel fill handle, with `$` — m38
- [x] A table's name shows on it and in properties — m38
- [x] Marquee: drag a rectangle, Shift for a lasso; direction matters — m39, m53
- [x] Scroll wheel zooms — m44
- [x] Panels as an icon rail, on either side — m45
- [x] The insert point is gone, and everything that hung off it — m46
- [x] One arrow while a call-out is drawn, not two — m47
- [x] Spreadsheet: arrows move the cell, like Excel — m52
- [x] Tool sets: drag to reorder, and show the thing itself — m54
- [x] Call-out: no rubber box; the box grows with the text; Alt+Z fits it — m55
- [x] A picture copied elsewhere beats the last snapshot — m56
- [x] The highlighter draws one clean stroke — m58, m59
- [x] Bookmarks enable and disable; add one from the page panel — m60
- [x] Every label read, and what was not needed dropped — m61
- [x] One undo step for a slider, not one per pixel — m62

## Typing, Greek and the equation (messages 66–99)

- [x] Ctrl+B is bold while typing, bookmarks otherwise — m66, m104
- [x] `"` opens a region that is maths until a space makes it words — m66, m83, m131, m139
- [x] Units come straight after the number — m66
- [x] Changing one line's unit leaves the others alone — m68
- [x] A stamp's wording stays on stamps — m69
- [x] Preferences, and an NZ spell check — m71
- [x] Copy and paste whole pages — m73
- [x] No ghost table name — m74
- [x] Resize table rows and columns — m75
- [x] The pointer says what will happen — m76, m108
- [x] Scrolling a panel does not spin a dropdown under the pointer — m80
- [x] Import Bluebeam tool sets (.btx), groups and all — m80
- [x] Escape goes all the way back — m81
- [x] Ctrl+Shift+V pastes in place — m82, m111
- [x] Cell alignment, left, centre, right — m84
- [x] `_` and `^` for subscript and superscript — m85
- [x] `\` opens an equation inside a text box — m86
- [x] The variable list, with Tab to take it — m87
- [x] Superscripts sit clear of the base — m88, m97
- [x] Add and delete a leader — m90, m140
- [x] Header names work as column references — m91
- [x] One phi, and every other Greek letter checked — m96
- [x] The unit list opens in the right place — m98
- [x] Decimal places, scientific notation and significant figures — m121

## The last round (messages 100–149)

- [x] Cloud call-out: no arrow, a line to the cloud — m100, m141
- [x] The call-out box previews before it is placed — m100
- [x] No control point on an arrow that is not selected — m101
- [x] The rotation grip is not cut off — m102
- [x] Remove the tool set button; right-click instead — m105
- [x] A snapshot is not "image missing" — m106
- [x] A pasted photo is not "image missing" — m107
- [x] Ctrl suspends snapping everywhere, calibrate included — m136
- [x] The .btx section cuts look like section cuts — m137, m139
- [x] Zoom goes to the pointer — m139
- [x] SMath's dot between a number and its unit — m139
- [x] The leader does not jump between preview and placement — m140
- [x] The elbow moves anywhere, and the side follows it — m140
- [x] As many leaders as wanted on an arrow call-out — m140
- [x] Cloud and Cloud+ are one tool; drag for a box, click for a shape — m143
- [x] A snapshot is its own markup, holding lines, not a picture — m144
- [x] Rotating a page turns the paper as well as the markups — m118, m145
- [x] View ▸ turn the view, for reading sideways, changing nothing — m119
- [x] The format painter has a brush icon — m146
- [x] Pasting a page says where it will land — m147
- [x] The selection box draws without needing a right-click — m148

## Outstanding

Nothing. Every request above is built and held by a test.

- [x] Snapping says what it has caught — m112
- [x] Snap while a point is dragged, not only while it is drawn — m113
- [x] Drop a PDF on the pages panel, with an insertion line — m114
- [x] Insert a break symbol in a line, an edge or a polygon side — m115
- [x] A control point converts to a rounded corner — m115, m125
- [x] A segment converts to an arc — m115, m125, m149
- [x] Insert ▸ Markup, with every drawing tool on it — m115
- [x] Shift-click takes hold of a dimension's number and moves it out — m116
- [x] A dimension's value does not flicker while it is rotated — m117
- [x] Insert PDF brings the drawing's own lines through — m120
- [x] The footer stays on the paper on an imported page — m122
- [x] Add or remove a header and footer on one page or many — m123, m124
- [x] Shift adds a control point, and takes one away — m125
- [x] Ctrl rounds a corner, and curves a segment — m125
- [x] An arc has two handles; a rounded corner has a radius — m126
- [x] A grid per page: on for blank pages, never on inserted PDFs — m127
- [x] Every drawing tool on the menu bar; Help searches the tools — m128
- [x] Hatch and line types that read Bluebeam's files — m80
- [x] Excel paste brings relative formulas with it — m109
- [x] The page bar: paper, margins, grid buttons, and page arrows — m93
- [x] The numbers in the properties panel: where it is, how big — m38
