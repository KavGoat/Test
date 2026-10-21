# CalcForge User Manual

CalcForge puts three tools an engineer uses every day into one document:

- **Part 1 — Markup**, modelled on Bluebeam Revu: mark up and measure PDF drawings.
- **Part 2 — Calculation**, modelled on SMath Studio: equations with units, typed
  on the page and calculated live.
- **Part 3 — Spreadsheets and tables**, modelled on Microsoft Excel: cells with
  formulas, formats and units, as small tables on any page or as whole
  spreadsheet pages.

The document **is a PDF**. It opens in any PDF reader exactly as it looks here;
markups are ordinary PDF annotations, and equations, tables and charts are drawn
into the page. Everything CalcForge needs to edit them again travels inside the
same file, so a round trip through CalcForge loses nothing.

**How to read this manual.** Menu paths are written **Menu ▸ Item**. Keys are
written `Ctrl+Shift+K`. Every key in this manual is the default; all of them can
be changed (see *Customisation ▸ Keyboard shortcuts*). The reference tables of
functions, preferences and keys are generated from the program itself, so they
always match the version you are using. Open this manual at any time with
**Help ▸ User Manual** (`Ctrl+F1`); type in its search box to find a word, and
pick a heading on its left to jump there.

## Getting started

### Markup mode and Calc mode

CalcForge has two modes, shown by the **Markup | Calc** pair of buttons at the
right-hand end of the menu bar. `F12` switches between them.

- **Markup mode** is Revu: the markup tools have their single-letter keys
  (`R` for a rectangle, `M` for a length measurement…), a click selects, and a
  table is opened for its cells with a double-click.
- **Calc mode** is SMath: a click on empty paper puts SMath's red cross there and
  typing starts an equation. The markup tool letters are switched off (a letter
  is the start of an equation), `"` starts Calculation text and `@` a plot. A
  click on a table goes straight into its cells.

Equations, tables and markups all live on the same pages in both modes; the mode
only decides what a click and a key press mean. In Markup mode you can still
start an equation where the pointer is by typing `'`.

### Opening, saving and starting a document

- **File ▸ New PDF** (`Ctrl+N`) starts a blank A4 portrait page in Markup mode.
  **File ▸ New Tab** (`Ctrl+T`) opens another document in a tab of its own, and
  **File ▸ New Window** (`Ctrl+Alt+Shift+N`) a second window.
- **File ▸ Open** (`Ctrl+O`) opens a PDF, or an Excel workbook (`.xlsx`, `.xlsm`),
  in a new tab. A PDF opens exactly as it was written: its pages stay its own line
  work (sharp at any zoom), its bookmarks come into the Bookmarks panel, and the
  markups someone else made come in as markups you can select, move and change.
  **File ▸ Open Recent** lists the files opened lately.
- **File ▸ Save** (`Ctrl+S`), **Save As** (`Ctrl+Shift+S`) and **Save All** write
  a PDF. Every save is a fresh compact file; a digitally signed PDF is appended to
  instead, so its signature still verifies.
- **File ▸ Close** (`Ctrl+W`) and **Close All** close documents, asking about
  unsaved changes. A document tab's right-click menu also has Close Others,
  New Window, Open in Split View and Duplicate Tab.
- **Tabs and windows.** A file open in two tabs — in one window, or each in a
  window of its own — is **two views of one document**: an edit in either shows
  in both at once, one undo history serves both (Undo in either undoes the
  document's last step), one save saves it, and every tab of it shows the
  unsaved-changes mark and, after **Save As**, the new name. Each tab keeps its
  own zoom, scroll position, page and tool. Closing one of the tabs (or one of
  the windows) asks nothing while another still shows the document; closing the
  last one asks about unsaved changes. A tab's **New Window** and **Duplicate
  Tab** give a document another view; so does **File ▸ Open** (or **Open
  Recent**) of a file another window already has open — this window gets a tab
  on that same document, its unsaved changes included, rather than a second copy
  read from the disk. Opening a file already open in this window brings its tab
  forward.
- **Dragging tabs.** Drag a document tab out of the window to give it a window
  of its own, or drop it on another CalcForge window (its tab bar, its page or
  its empty workspace) to move it there with its pages, place, zoom, undo
  history and selection. A tab is never merged into another: dropped on a window
  (or the other pane of a Split View) that already shows the document, it stays
  a tab of its own there, a second view of the same document. A window left with
  no tab by the drag closes.
- **Two copies of one file.** Two separate copies of the same file (one read
  from the disk apart from the other, such as a recovered version) are never
  merged: dropped on a window that holds the other copy, both tabs stay, the one
  brought in marked **(2)** (for example `a.pdf (2)`), and the status bar says so
  — save one with **Save As** so that neither is saved over the other.
- **File ▸ Import** brings pages in: **Pages** (from another PDF), **Image Page**,
  **Excel Workbook** and **Tool Set** (a Bluebeam `.btx`). Each page import offers
  **Before** or **After** the current page.
- **File ▸ Export** writes a plain **PDF** (`Ctrl+E`), **Images** of the pages,
  or a **Markups Summary**.

### The window

**Menu bar.** Revu's menus — CalcForge (Preferences, Keyboard Shortcuts, Exit),
File, Edit, View, Document, Batch, Tools, then **Calculation** (equations and
spreadsheets), Window and Help. At its right end are the **Markup | Calc**
switch and a **Search** box that finds tools, commands, markups and pages as you
type.

**Toolbars.** Main (new, open, save, insert pages, export, print, undo, redo),
**Tools** (the markup tools), **Measure**, **Calculation**, **Markup Styles** and
**Properties**. Turn each on or off in **Tools ▸ Toolbars**; drag a toolbar by its
grip to the top or bottom of the window; **Lock Toolbars** stops them moving.
When the window is too narrow for them, the toolbars wrap onto another row
(and a bar too long for the window shows the rest on its » button).

**Panels.** The panels sit behind two strips of icons down the window's edges,
as in Revu. Left: **Thumbnails** (`Alt+T`), **Bookmarks** (`Alt+B`), **Tool
Chest** (`Alt+X`) and **Search** (`Alt+1`). Right: **Properties**, **Page**
(`Alt+U`), **Maths** and **Variables**. The **Markups List** (`Alt+L`) lies along
the bottom. Click an icon to open or close its panel; drag an icon to the other
edge to move the panel there. Each panel's title bar can roll it up, pin it where
it is, float it and hide it. The edge of a panel column turns blue under the
pointer and hides the column with one click. **Window ▸ Hide/Show Panels**
(`Shift+F4`) clears them all away for room and brings them back. Changing
anything in a panel — ticking an option, picking from a list, typing a value,
picking a page, a tool or a search result — leaves the panel scrolled where it
was and the keyboard with what you were using; only picking something else on
the page starts the Properties panel at its top again.

**Properties toolbar and Properties panel.** Whatever is selected — or the tool
you are holding — is shown and changed on the **Properties toolbar** (Revu's bar
above the page) and in more detail in the **Properties panel**. Both are
described in *Part 1 ▸ Properties toolbar and panel*. With a table open, the
toolbar shows Excel's cell controls instead.

**Tool Chest.** Your own collections of ready-made markups and styles, kept
between documents (see *Part 1 ▸ Tool Chest and tool sets*).

**Status bar.** From the left: Show Grid, Snap to Grid, Snap to Content, Snap to
Markup and Reuse toggles; what is happening and where the pointer is; Dim
Content; the page's scale (**Scale Not Set** until one is set — click it to set
one); the page navigation (first, previous, page number, next, last); Fit Width;
the page layout (Continuous ▾); Snap ▾; Sync (link this view with other windows
on the same document); the paper size (click it for Page Setup); and the zoom
box. When the window narrows, the least-needed controls move onto the » menu.

**Undo.** Every change is one step: **Edit ▸ Undo** (`Ctrl+Z`), **Redo**
(`Ctrl+Y` or `Ctrl+Shift+Z`) and **Edit ▸ Undo History**, which lists the steps.
Inside an equation, `Ctrl+Z` takes back keystrokes first.

**Finding a command.** **Help ▸ Find Tools + Commands** (`Shift+F1`) — type what
you want to do and it names the tool or command and its key. **CalcForge ▸
Keyboard Shortcuts** (`F1`) lists every command.

**Typing never fires a shortcut.** While you are typing in a text box, callout,
note, equation, cell, formula bar or search box, a key types; tool keys and
single-letter commands only act on the bare page.

## Part 1 — Markup (Bluebeam Revu-style)

### Drawing a markup

1. Pick a tool: its toolbar button, its key, **Tools ▸ Markup**, **Tools ▸
   Measure** or **Tools ▸ Sketch to Scale**.
2. Draw it. Most tools draw either way: **press and drag**, or **click** for the
   first point and **click** again for the second, the markup following the
   pointer in between. Tools made of points (Polyline, Polygon, Area…) take a
   click per point and finish on a **double-click** or `Enter`; a right-click
   closes a half-drawn polygon or cloud.
3. Hold `Shift` to keep a line to 0°, 45° or 90°, to square a rectangle off, to
   make an ellipse a circle, or to draw a straight stroke with the Pen.
4. `Esc` cancels what is half drawn and puts the tool down (back to Select);
   `V` also goes back to Select, as in Revu.

After one markup the tool goes back to Select. Turn on **Reuse** (Tools menu or
status bar) to keep drawing with the same tool.

**Snapping.** While you draw, the pointer catches corners, midpoints, centres
and line ends of markups (**Snap to Markup**), of the PDF's own drawing (**Snap
to Content**) and the page grid (**Snap to Grid**); **Align to Markups** and
**Align to Content** line a new point up level with or under one already there.
What has been caught is marked with a small orange square and named in the
status bar. Hold `Ctrl` while dragging to let go of snapping for that drag. All
of these are on **View** and on the status bar's **Snap ▾**.

**Typing straight onto the page.** On bare paper in Markup mode, `"` starts a
text box where the pointer is, `|` a note and `@` a callout. Any other letter
does nothing unless it is bound to something — it never starts writing by
accident.

**The number keys.** With nothing in hand, `1` to `9` pick up the first nine
tools in **My Tools** (Tool Chest). With a markup tool in hand, `1` to `9` draw
the next markup in that tool's numbered **markup style**, and `0` goes back to
its default (see *Markup styles and defaults*).

### The markup tools

#### Navigate

- **Select** (`Esc`, or `V`) — select, move and edit. Drag on bare paper for a
  selection box: dragged rightwards it takes what is wholly inside, leftwards what
  it crosses. `Shift`+click on bare paper starts a lasso: click its corners and
  press `Enter` or right-click to close it.
- **Pan** (`Shift+V`) — drag to move round the page. The space bar held down and
  the middle mouse button pan with any tool.
- **Snapshot** (`G`) — drag a region to copy everything in it. What is pasted is
  the drawing itself, line for line, so it stays sharp at any size.
- **Hyperlink** — drag a region that goes to a page, a view of a page, a file or a
  web address when clicked. It is a real link in the saved PDF; on screen it is a
  faint dashed outline and it never prints. Right-click it for **Follow Link** and
  **Edit Link**; double-click follows it.
- **Crop** — drag the part of the page to keep; Undo brings the rest back.

#### Draw

- **Pen** (`Alt+P`) — freehand ink. `Shift` draws a straight stroke.
- **Highlight** (`H`) — a translucent freehand highlighter.
- **Eraser** (`Shift+E`) — drag over Pen and Highlight strokes to rub them out.
  It never touches markups drawn as shapes.
- **Line** (`L`) and **Arrow** (`A`) — two points. Their ends (arrowheads) are set
  on the Properties toolbar.
- **Arc** (`Shift+C`) — a curve between two points: drag it, then move the middle
  handle to bend it.
- **Polyline** (`N`) — click each point, double-click to finish.
- **Rectangle** (`R`) and **Ellipse** (`E`) — drag, or click two corners. Their
  width and height are paper sizes (millimetres, inches or points, as the rulers
  say); right-click ▸ **Exact Size…** sets them exactly and **Show Size** writes
  the size on the page.
- **Polygon** (`P`) — click each corner, double-click to close.
- **Cloud** (`C`) — a revision cloud: drag a rectangle, or click corner by corner
  for a free-form cloud; a double-click, a click on the first corner again,
  `Enter` or a right-click closes it. As in Revu, the cloud is a ring of
  overlapping scallops centred on the outline, one on every corner and the rest
  spaced evenly along each side, each tucked behind the one before;
  **Cloud intensity** sets how big they are.
- **Highlight Area** (`J`) — drag over anything to highlight it. It darkens what is
  underneath rather than covering it.
- **Mark for Redaction** — an opaque box over what is to be removed. Nothing is
  removed until **Edit ▸ PDF Content ▸ Apply Redactions…**, which permanently
  destroys what the boxes cover and cannot be undone.
- **Whiteout** — Revu's Erase Content: drag a region to clear the PDF's own drawing
  in it (Edit ▸ PDF Content). Undo restores it.

#### Annotate

- **Text Box** (`T`) — drag the box, then type. With Autosize text on
  (Preferences) the box grows as you type; **Auto-Size** (`Alt+Z`) brings it back
  round the words, at their line spacing and margins (the font size stays as it
  is). It works on text boxes, typewriter text, callouts and Cloud+ notes; the
  callout's Properties toolbar also has it as **Fit to text**. Double-click to
  edit the words again.
- **Callout** (`Q`) — click what it points at, then click where the words go. The
  first click snaps to what is drawn; the box for the words follows the pointer
  exactly and lands where it was shown (on the grid when you snap to it), and its
  leader keeps to the side it leaves by until another side clearly faces what it
  points at, so it does not jump from side to side. The same goes for Cloud+. Drag
  the orange diamonds to move the leader. Right-click for **Add Arrow Leader**,
  **Add Cloud Leader** and **Remove Leader**. **Add Cloud Leader** draws the
  cloud by hand, as the Cloud tool does: press and drag a rectangle round the
  area, or click its corners for a free-form one; the leader then joins it, in
  one undo step. `Esc` puts it down with nothing changed. A cloud leader ends on
  the cloud's scalloped edge.
- **Cloud+** (`Shift+Q`) — a cloud and its note as one markup, drawn as in Revu:
  press and drag for a rectangular cloud of that size, or click its corners for a
  free-form one (a double-click, a click on the first corner again, `Enter` or a
  right-click closes it); then click where the words go — the leader joins them —
  and type. The cloud, its leader and the words are one undo step. A Cloud+ kept
  in a tool set to draw with its properties is drawn with the Cloud+ tool.
- **Checkbox** — options with a box to tick beside each, as on a review stamp, all
  in one markup typed like a text box. Click to put one down with one option
  (Option 1) picked ready to type over; it is not dragged to a size. Each line
  you type is one option: `Enter` adds the next, `Backspace` at the start of a line
  joins it to the one above, and a tick stays with its option as lines are added,
  joined or taken away. With Select, a click **on a box** ticks or unticks it (one
  undo step) — also inside a group, unless it is locked; a click anywhere else
  picks the markup up as usual, and a double-click on the words edits them. It is
  only the options: no heading or caption of its own (group it with a text box or
  other markups to build a stamp). Making it narrower wraps an option's words onto
  the next line, hanging under the words rather than the box; only the font size
  makes the boxes, and the whole Checkbox, bigger; `Alt+Z` fits it round its
  options. Its settings are in the Properties panel's **Checkbox** section:
  **Options** (tick, or double-click to rename, each option; **Add Option**,
  **Remove Option**, **Move Up**, **Move Down**), **Box** (Square, Rounded square,
  Circle, Diamond), **Mark** (Tick — a heavy tick, as made by hand, running out past
  the box on both sides — Cross, Filled, Dot), **Multiple Selection** (on:
  several may be ticked; off: ticking one unticks the others), **Box Colour** and
  **Mark Colour** (the words' colour to begin with), **Option Spacing** (the space
  between options, as a share of the font size) and **Line Spacing**; Box ▾, Mark ▾
  and Multiple are on the Properties toolbar too. Everything a text box has also
  applies: border colour, width and line style (none to begin with), fill,
  opacity, font, size, colour, bold, italic and underline, alignment and margin.
  The ticked options are its **Checked** property, shown in the Markups List's
  Checked column ("Satisfactory", or "A; C" for several); the Subject is Checkbox.
  A Checkbox style (Markup Styles, Tool Chest) keeps its box, mark and Multiple
  Selection. Saved to PDF it is a stamp annotation drawn exactly as here: in other
  PDF readers it shows as drawn and can be moved or resized, but its options and
  ticks are changed only in CalcForge (its contents read "☑ Satisfactory",
  "☐ Rejected" … for searching); moved or resized there, it opens here where it
  was put.
- **Note** — click to drop a sticky note; double-click it (or use the Properties
  panel) to read and write what it says. Its **Icon** (Comment, Help, Insert, Key,
  New Paragraph, Note, Paragraph) is on the Properties toolbar.
- **Stamp** (`S`) — drag a status stamp (see *Stamps*).
- **Flag** (`Shift+F`) — click to pin a flag to come back to.
- **Image** — drag a box and choose a picture from disk (or paste one). Dragging a
  picture's corner keeps its proportions; hold `Shift` to stretch it freely. An
  edge handle stretches it one way. The opposite corner or edge stays where it is.
  **Crop Image**: select an image, then drag the part of it to keep.
- **Table** — drag out a spreadsheet table; its rows and columns follow the size
  you drag (see Part 3).
- **Contents** — a table of contents built from the document's bookmarks; click a
  line to go there. It is a real link in the saved PDF.

#### Measure

**Length** (`M`), **Dimension** (`Alt+M`), **Polylength** (`Shift+Alt+Q`),
**Area** (`Shift+Alt+A`), **Perimeter** (`Shift+Alt+P`), **Volume**
(`Shift+Alt+V`), **Angle** (`Shift+Alt+G`), **Centre Radius**, **Diameter**
(`Shift+Alt+D`), **Polygon Cut-Out**, **Ellipse Cut-Out**, **Count**
(`Shift+Alt+C`), **Viewport** and **Calibrate**. They are described in
*Measurement* below.

#### Sketch to Scale

**Sketch to Scale Rectangle** and **Sketch to Scale Ellipse** (Tools ▸ Sketch to
Scale, and the Measure toolbar) draw shapes to a real size on a scaled page.
While you drag, a size bar rides the corner: type the real **Width**, `Tab` to
**Height** and **Rotation**, `Enter` to place it (3 m × 1.5 m). They offer the
measurement extras too: cut-outs, Units, Caption and Totals.

#### Every tool at a glance

<!-- generated:markup-tools -->
| Tool | Group | Key | What it does |
|---|---|---|---|
| **Select** | Navigate | `Esc` | Select, move and edit markups |
| **Snapshot** | Navigate | `G` | Drag a region to copy everything in it — what comes back is the drawing itself, lines and all, so it stays sharp at any size |
| **Pan** | Navigate | `Shift+V` | Drag to move around the page |
| **Pen** | Draw | `Alt+P` | Freehand ink |
| **Highlight** | Draw | `H` | Translucent freehand highlight |
| **Eraser** | Draw | `Shift+E` | Drag over freehand ink and highlighting to rub it out — it does not touch anything that was drawn as a shape |
| **Line** | Draw | `L` | Straight line |
| **Arrow** | Draw | `A` | Arrow |
| **Arc** | Draw | `Shift+C` | A curve between two points — drag it, then move the middle handle to bend it where you want |
| **Polyline** | Draw | `N` | Click each vertex, double-click to finish |
| **Rectangle** | Draw | `R` | Rectangle — drag it or click twice; Shift squares it off. Its width and height are on the paper; right-click ▸ Exact Size… sets them |
| **Ellipse** | Draw | `E` | Ellipse — hold Shift for a circle; its width and height are on the paper |
| **Polygon** | Draw | `P` | Click each vertex, double-click to close — not scaled |
| **Cloud** | Draw | `C` | Mark a revision: drag a rectangular Cloud, or click each corner for a custom Cloud+ — a double-click, the first corner again, Enter or a right-click closes it |
| **Highlight Area** | Draw | `J` | Drag over anything to highlight it — it darkens what is underneath rather than covering it |
| **Mark for Redaction** | Draw | — | Opaque black-out box |
| **Hyperlink** | Navigate | — | Drag a region that goes to a page, a view, a file or a web address when clicked — a real link in the saved PDF |
| **Crop** | Navigate | — | Drag the part of the page to keep; the rest is cropped away, and Undo brings it back |
| **Whiteout** | Draw | — | Revu's Cut Content (Erase Content): drag a region to clear the flattened PDF artwork in it; Undo restores it |
| **Text Box** | Annotate | `T` | A box of words on the page — drag the box, then type in it |
| **Callout** | Annotate | `Q` | Click what it points at, then click where the words go |
| **Cloud+** | Annotate | `Shift+Q` | Drag a rectangular Cloud or click the corners of a custom Cloud+ (a double-click or the first corner again closes it), then click where the words go — the cloud and note are one thing |
| **Checkbox** | Annotate | — | Options with boxes to tick — click to place one; type one option a line, and click a box to tick it |
| **Note** | Annotate | — | Sticky note with a comment |
| **Stamp** | Annotate | `S` | Approval or status stamp |
| **Flag** | Annotate | `Shift+F` | Pin a flag somewhere to come back to |
| **Image** | Annotate | — | Place an image from disk |
| **Crop Image** | Annotate | — | Select an image, then drag the part of it to keep |
| **Table** | Annotate | — | Drag out a table: the rows and columns follow the size you drag — a spreadsheet on the page, with Excel's formulas, formats and units |
| **Contents** | Annotate | — | A table of contents built from the document's bookmarks — click a line to go there |
| **Length** | Measure | `M` | Measure a distance to the page scale |
| **Dimension** | Measure | `Alt+M` | A dimension line carrying your own text instead of the measured value |
| **Polylength** | Measure | `Shift+Alt+Q` | Measure along a path |
| **Area** | Measure | `Shift+Alt+A` | Measure an enclosed area to the page scale |
| **Perimeter** | Measure | `Shift+Alt+P` | Measure around a shape |
| **Volume** | Measure | `Shift+Alt+V` | Area × depth |
| **Angle** | Measure | `Shift+Alt+G` | Measure an angle from three points |
| **Centre Radius** | Measure | — | Measure a radius |
| **Diameter** | Measure | `Shift+Alt+D` | Measure a diameter |
| **Polygon Cut-Out** | Measure | — | Draw a hole in the area measurement under it — the hole comes off the area |
| **Ellipse Cut-Out** | Measure | — | Drag a round hole in the area measurement under it |
| **Count** | Measure | `Shift+Alt+C` | Click to drop numbered markers; they count as the subject on the Properties toolbar's Count subject… (Count to begin with) |
| **Viewport** | Measure | — | Drag a region of the sheet drawn at its own scale — a detail at 1:20 beside a plan at 1:100; measurements inside use it |
| **Calibrate** | Measure | — | Click each end of something you know the length of, then type that length — the page scale follows |
| **Sketch to Scale Rectangle** | Sketch to Scale | — | A rectangle drawn to a real size: it uses the page scale, and its real width and height can be typed while drawing — 3 m × 1.5 m |
| **Sketch to Scale Ellipse** | Sketch to Scale | — | An ellipse drawn to a real size: it uses the page scale, and its real diameters can be typed while drawing — Shift for a circle |
<!-- /generated -->

### Selecting and editing markups

- **Select**: click a markup. `Shift`+click adds or takes away, `Ctrl`+click adds.
  **Edit ▸ Select All** (`Ctrl+A`) selects every markup on the page.
- **Move**: drag it (`Shift` keeps the move straight: across, down or at 45°).
  Over a markup the pointer is Revu's arrow with a small move sign. `Ctrl`+drag
  leaves a copy behind, from anywhere on the markup, its points included; the
  arrow carries a copy sign while `Ctrl` is held, and `Ctrl`+click adds the
  markup to the selection. A drag with `Shift`, `Ctrl` or `Alt` held never
  changes the markup's shape. Drag it onto another page and it belongs to that
  page. The arrow keys nudge by 1 mm, `Shift`+arrow by 1 pt.
- **Resize**: drag a handle; the arrows on the pointer lie the way the handle
  pulls, turned with a turned markup. `Shift` on a corner keeps the proportions.
  The blue dot on a dashed stalk turns the markup;
  **Properties panel ▸ Layout** has its exact position, size and rotation.
- **Control points** (lines, polylines, polygons, clouds, rectangles…): drag a
  point to move it — over a single point, a leader's arrow head or its hinge the
  pointer is a thin crosshair. A *click* (not a drag) with a key held reshapes
  the selected outline, and the arrow's sign says what it will do:
  `Shift`+click on a side puts a point in where you click (a small "+"), on a
  point takes it out (a "−"); `Alt`+click on a corner rounds it off (or sharpens
  it again), on a side bends it into an arc (or straightens it) (a small arc).
  Pressed and dragged instead, the same keys move the markup. A double-click on
  a polyline or polygon adds a point too. Right-click ▸
  **Control Point** has **Add Control Point**, **Insert Break**, **Subtract Control
  Point** and **Round Corner**; there are also **Arc Segment**, **Round All
  Corners** and, for a rectangle or ellipse, **Convert to Polygon**.
- **Cut, Copy, Paste** (`Ctrl+X`, `Ctrl+C`, `Ctrl+V`); **Paste in Place**
  (`Ctrl+Shift+V`) puts it back where it was on this page; **Paste Here…**
  (`Ctrl+Alt+V`) carries it on the pointer until you click; **Duplicate**
  (`Ctrl+J`) makes a copy a little down and to the right; **Delete** removes it.
- **Offset** (`O`) — Revu's Offset: a copy of the selected markup a set distance
  away, on the side the pointer is (inside or outside a closed shape). Its toolbar
  has **Distance** (in the page's units), **Replace Markup** (the original goes)
  and **Angle Miter Limit**. Click to put the copy down; `Esc` stops.
- **Multiply…** (`Ctrl+M` in Markup mode) — repeat the selection at a fixed
  spacing: **Across (x)**, **Down (y)** (real distances on a scaled page, paper
  distances otherwise, typed with a unit such as `3 m` or `25 mm`), **Times**, and
  **Duplicate** or **Move**.
- **Group** (`Ctrl+G`) makes several markups select and move as one;
  **Ungroup** (`Ctrl+Shift+G`).
- **Order** — **Bring to Front** (`Ctrl+Shift+]`), **Bring Forward** (`Ctrl+]`),
  **Send Backward** (`Ctrl+[`), **Send to Back** (`Ctrl+Shift+[`). The PDF's own
  drawing always stays underneath.
- **Alignment** — Revu's Align Markups, on **Edit ▸ Alignment**, a selection's
  right-click ▸ **Alignment** and the **Alignment** toolbar (**Tools ▸ Toolbars ▸
  Alignment**). With several selected, the first one picked is the **primary
  markup**: its control points are yellow, the others' green; click a
  green-pointed markup to make it the primary.
  - **Align Left**, **Align Centre**, **Align Right**, **Align Top**, **Align
    Middle**, **Align Bottom** (two or more): each lines up with the primary's
    edge or centre line.
  - **Align Width**, **Align Height**, **Align Size** (two or more): each takes the
    primary's width, height or both, its top left corner staying put (equations,
    tables, notes and counts keep the size of what they hold).
  - **Distribute Horizontally**, **Distribute Vertically** (three or more): the
    centres equally spaced between the two outermost, which stay.
  - **Centre in Document** (one or more): each markup's centre on its page's
    centre.
  - **Flip Horizontal**, **Flip Vertical** (one or more that flip): each mirrored
    about its own centre — images, snapshots, stamps, polylines, polygons,
    clouds, pen and highlighter ink, and groups (a group turns over as one). A
    callout flips as in Revu: its box goes to the other side of its leader and
    the leader is mirrored, but the words stay readable. A text box does not
    flip; picked with others, it is left as it is.

  A group counts as one markup and a calculation block takes its equations with
  it; equations, tables and markups align together. Each is one undo step. A
  command is greyed — on the toolbar, in both menus and for its key — until
  enough is picked (two for the aligns and sizes, three to distribute, one for
  Centre in Document, one that flips for a flip), and its tip says what it
  needs. None has a key out of the box — Revu's (`Ctrl+Alt+L`, `E`, `R`, `T`, `M`,
  `B`, `H`, `V`) are CalcForge's symbol and Paste Here keys — but any key can be
  given to each in Keyboard Shortcuts (group **Alignment**).
- **Lock** (`Ctrl+Shift+L` or `Ctrl+L`) stops a markup being moved or changed;
  again to unlock.
- **Hide** takes a markup off the screen and out of print without deleting it;
  **Show Hidden** brings every hidden one back.
- **Flatten** makes the markup part of the page drawing; it can then no longer be
  moved. **Unflatten** (`Ctrl+Shift+U`) brings flattened markups back when they
  were flattened with recovery allowed (see *Files* below). Equations,
  Calculation text, calculation blocks, tables and charts are never hidden or
  flattened, so neither is offered for them.
- **Edit ▸ Edit Selected** (`F2`) opens the one selected text box, callout,
  Calculation text, equation or table for typing, as a double-click does (a
  table at A1). In an open table `F2` edits the cell, as in Excel.
- **Format Painter** (`Ctrl+Shift+C`) — takes the selected markup's look; click
  another markup (or drag over several) to paint it on. It stays armed until
  `Esc`.
- **Change Colours…** — with several markups selected (or a group), change one
  colour they use — line, fill, text or hatch — to another in all of them.
- **Apply to Pages…** — a copy of the markup on All Pages or chosen pages.
- **Set as Default**, **Save as Markup Style** and **Add to Tool Chest** keep the
  look for later (see below).
- **Properties** opens the Properties panel.

The same commands are on **Edit**, on **Tools ▸ Selected Markups** and on a
markup's right-click menu.

### Properties toolbar and panel

The **Properties toolbar** reads left to right as Revu's, showing only what
applies to what is selected (or to the tool in hand). For selected equations (or
the one being typed in) it shows their font size, colour and **Style ▾** (bold,
italic, underline): one undo step for all of them; an equation's font family is
SMath's own and is not offered.

- **Type ▾** — the markup's kind; its menu holds the Subject, how many markups are
  selected, the dash spacing, the hatch's colour, scale and opacity, and **Set as
  Default**.
- **Line**: colour, opacity (the whole markup), line style, width.
- **Start** and **End** — the line ends: None, Open, Closed, Open (Reversed),
  Closed (Reversed), Butt, Diamond, Round, Square, Slash and Half Arrow — each with
  its **size** (Auto sizes it from the line width, or 25–400 %) and a **line-end
  colour** for the filled ends.
- **Fill**: colour and fill opacity; the **Highlight** button makes the fill (and
  hatch) multiply onto the drawing like a highlighter, leaving the border as it
  is.
- **Corner radius** (rectangles), **Cloud intensity** (scallop size), **Shape**
  (a callout's box).
- **Hatch** and **hatch colour**.
- **Font**: family, size (or **Auto**: the largest that fits the box), colour,
  and **Style ▾** (bold, italic, underline, strikethrough, alignment); **Fit to
  text** for a callout.
- **Line spacing ▾** (text boxes, typewriter text, callouts and Cloud+): 1.0
  (Single), 1.15, 1.5 or 2.0 (Double), or type any other multiple.
- For measurements: **Units ▾** (this measurement's own units, or the page's),
  **Caption ▾** (whether it is written on the drawing and which values: Label,
  Dimensions, Length, Area, Perimeter, Volume, Wall Area; Inline Text), **Add a
  cut-out**, and **Totals** (the selected measurements added up).
- For a note: colour, opacity and **Icon**; for a count: **Count symbol**.

The **Properties panel** has the same and more, in sections:

- **General** — Subject, Author, Label, the comment, Modified, and **Lock**,
  **Print** (leave it out of print and export when off) and **Bookmark**.
- **Appearance** — colours, fill and **Highlight**, hatch and its colour, scale and
  opacity, opacity, fill opacity, line width, line style and dash spacing, line-end
  sizes, corner radius, and for markups that suit them **Show Segment Values**
  (each side's length along it, or level), **Show Caption** with **Edit…**, and
  **Show Centroid**; the font, size, colour, styles (bold, italic, underline,
  strikethrough, superscript, subscript), alignment, **Line Spacing** and the
  margins — **Margin** (the space between the border and the words, the same all
  round) or **Margins** (L, T, R, B: each side of its own).
- **Leader** (callouts) — the hinge and how many leaders.
- **Layout** — X, Y, Document Width, Document Height and Rotation.
- **Measurement**, **Count**, **Stamp**, **Note**, **Image**, **Snapshot**,
  **Contents**, **Table** (or **Sheet**) and **Cells**, **Chart**, **Calculation
  block**, and for equations **Result**, **Equation** and **Plot**, each described
  in its own section.
- **Options** — **Add to Tool Chest** and **Set as Default** (and **Forget
  Default** when the kind has one).

The panel shows what is selected or, with nothing selected, what you are working
in: the equation or text being typed in, or the table or spreadsheet page open
for its cells — in Markup and Calc mode alike. A change made in the panel to an
equation being typed in finishes the typing first (its own undo step), then makes
the change (another).

With several markups selected, a change applies to all of them in one undo step.
Text inside a text box can be styled a word at a time: select the words while
typing and use **Edit ▸ Text** (Bold, `Ctrl+I` Italic, `Ctrl+U` Underline,
Strikethrough, Superscript, Subscript, Align Left `Ctrl+Alt+Left`, Align Centre
`Ctrl+Alt+Home`, Align Right `Ctrl+Alt+Right`, Increase and Decrease Font Size
`Ctrl+Alt+Up` and `Ctrl+Alt+Down`).

### Line styles, hatches and fills

**Line styles.** Solid; Dashed 1 to 6; Revu's complex styles — **Fenceline
Circle**, **Fenceline Square**, **Gas**, **Hot Water**, **Zig Zag**,
**Insulation**, **Double**, **Tracks** and **Road**, drawn along any path and
growing with the line width; and the older dash styles (dash, dot, dash-dot,
long dash, centre, phantom, hidden, border, divide…). **Manage…** at the top of
the line-style list opens **Line Styles**: every style drawn, **Import…** an
AutoCAD `.lin` file, **New…** a style of your own (dashes and gaps in points),
and **Remove** your own ones. A markup carries its dashes with it, so it looks
the same on a computer that has never seen the style.

**Hatches.** Revu's Brick, Diagonal Brick, Horizontal, Vertical, Diagonal Down,
Diagonal Up, Grid, Weave and 10/20/30 % Dots come first, then Diagonal Cross,
Dots, Dense and the materials: steel, masonry, aluminium, bronze, lead, plastic,
rubber, glass, block, stone, tiles, earth, hardcore, honeycomb, grating, chequer
plate, concrete, gravel, sand, batt and rigid insulation, timber and timber end.
A hatch is drawn as real lines over the fill, in its own colour, at its own scale
and opacity. **Manage…** at the top of the hatch list opens **Hatch Patterns**:
import an AutoCAD or Revu `.pat` file, make a pattern of your own, or remove one
of yours.

**Colours.** Every colour button opens Revu's picker: the basic colours, **No
Color** where a colour can be none, the **eyedropper** (pick any colour on the
screen; `Esc` or right-click leaves it) and **More Colors**; the last eight
colours you made are kept.

### Text in markups

- **Steady words.** The words in markups are spaced by the font's own widths and
  never fitted to the screen's pixels, as a PDF viewer sets them, so they look the
  same at every zoom and do not shift or change width when a markup is picked out,
  hovered or clicked near. On screen the words are always drawn the same way —
  the same pixels whether the markup is still, picked out, being typed in, or has
  another markup dragged past it, and with the graphics card on or off — so they
  never flicker, swell or lighten for a moment.
- **Line spacing and margins.** A text box, typewriter text, callout or Cloud+
  has Revu's **Line Spacing** — Single (1.0), 1.15, 1.5, Double (2.0) or any
  multiple — on the Properties toolbar and panel, and **Margins**, the space
  between its border and its words: one value, or left, top, right and bottom
  each of its own (Properties panel). Both show as you type, print and export
  as drawn, and are kept in the PDF as Bluebeam keeps them (the `line-height`
  and `margin` of the text's style), so a file from Revu with them opens with
  them; a file without them opens exactly as before. Words set by Bluebeam keep
  their own line heights, scaled when you change the spacing.

- **Insert Field** (right-click a text box, callout, Cloud+ or Calculation text)
  puts in a field that shows its value on screen and in print: Title, Project,
  Author, Company, Subject, Keywords, Description, Revision, Document id, File
  name, Page number (also `0001` style), Number of pages, Page n of m, four date
  formats, two time formats — and **Variable**, which shows an equation's value
  (`{=name}`) and follows it as it is recalculated.
- **Edit Text** puts the cursor in the words; **Bookmark** makes the words a
  bookmark.
- **Edit ▸ Check Spelling ▸ Check Spelling in Markups…** (`F7`) goes through every
  text markup word by word: Ignore Once, Ignore All, Add to Dictionary, Change,
  Change All. Spelling is also checked as you type (Preferences).
- **Symbols**: `Ctrl+Alt` keys type ×, ÷, √, ², ³, ±, ≤, ≥, ≠, π, °, Δ, Σ, ⌀, µ
  and the Greek letters φ σ α β γ θ λ ρ ε ω (see the shortcut reference, Symbols).

### Measurement

**Setting the scale.** A page has no scale until you give it one; measurements
then read paper distances and say so. **Tools ▸ Measure ▸ Set Scale…**
(`Ctrl+Shift+K`), the status bar's scale button, or right-click a page opens
Revu's **Set Scale**:

- **Pages** — this page, all, selected or a range such as `1-3, 5`.
- **Preset** — the standard scales (your saved ones at the top), or **Custom**:
  a drawing length = a real-world length, each with its unit.
- **Calibrate** — click each end of something you know the length of, then type
  that length; the scale follows. The **Calibrate** tool does the same.
- **Separate Y Scale** — a different scale down the page than across it.
- **Precision** — decimals, or fractions for feet-and-inches and inches.
- **+ Add Preset** saves a custom or calibrated scale to the top of the list.

The **Page panel** (`Alt+U`) shows the page's paper, orientation and scale, the
length and area units, decimal places and its **Viewports**, and changes them as
soon as you change them. Changing the unit there updates every measurement on the
page that has no unit of its own.

**Viewports.** A viewport is a region of the sheet drawn at its own scale — a
1:20 detail beside a 1:100 plan. Drag it with the **Viewport** tool (it asks for
its name and scale), or use **Tools ▸ Measure ▸ Viewports…** and the Page
panel's Add, Edit and Delete. Measurements inside a viewport use its scale.

**The measuring tools.**

- **Length** (`M`) — the true distance between two points.
- **Dimension** (`Alt+M`) — a dimension line that can carry your own text instead
  of the measured value (the takeoff still uses what was measured). `Shift`+drag
  its number to pull the words onto a leader.
- **Polylength** — the length along a run of segments.
- **Area** — the area of the shape you click out; **Perimeter** — the distance
  round it; **Volume** — area × a **Depth** you type (e.g. `150 mm`).
- **Angle** — three points: the angle between two legs.
- **Centre Radius** and **Diameter** — the size of a circle.
- **Polygon Cut-Out** and **Ellipse Cut-Out** — draw a hole inside an area
  measurement and its area comes off (an opening out of a wall). **Add a cut-out**
  on the Properties toolbar does the same for the selected area.
- **Count** — click to drop numbered markers. As in Revu the tool does not ask
  what it counts: markers count as *Count* until, with the tool in hand, **Count
  subject…** on the Properties toolbar says what you are counting (doors,
  sprinkler heads…) and its symbol (circle, square, triangle, diamond, cross,
  star); markers of one subject number on in order. **Tools ▸ Renumber Counts**
  closes gaps in page order. The Properties panel changes a marker's subject,
  symbol, number and whether the number shows.

**A measurement's properties.** In the Properties panel: **Value**, **Counts as**
(measurements sharing a subject are totalled in the Markups List), its own
**Length/Area/Volume** units or the page's, the page's area unit, **Depth**,
**Variable** (give it a name and the equations can use its value — see Part 2),
**Says** (your own words instead of the measured value), **Inline text** and
**Calibrate…**. On the toolbar: **Units ▾**, **Caption ▾** and **Totals**.
Right-click a measurement for its variable name box, **Edit Text…**, **Inline
Text** and **Set Scale…**.

**Rectangles and ellipses know their size**: a Sketch to Scale shape in real
units, a plain one on the paper; it is in the Properties panel and in the Markups
List's Value column.

### The Markups List

The **Markups List** (`Alt+L`, or drag its bar up from the bottom of the window)
is every markup in the document as a table — the drawing and the list are two
views of one thing: pick a row and the markup is picked on the page, and the
other way round.

- **Columns**: Page, Type, Subject, Label, Colour, Fill, Line, Width, Opacity,
  Font, Size, Value, Checked (a Checkbox's ticked options), Author, Date and
  Comment. Drag a heading to reorder the
  columns or its edge to resize.
- **Sorting**: click a heading; click again to reverse. Page 2 sorts before
  page 10.
- **Filtering**: type in **Filter markups…** to show only rows containing the
  words; with **Filter List** on, each heading has a filter button (▾) listing its
  values to tick. A filtered column's button turns into a blue funnel. **All**
  clears every column filter. Markups the filter leaves out are dimmed on the page
  (by the *Filtered Annotation Dim Percent* preference). Turning **Filter List**
  off keeps the filters but stops using them.
- **Grouping**: by page, type, subject, colour or author, or no groups.
- **Editing in place**: Subject, Label, Author and Comment (a text box's or
  callout's words) can be typed into — click a picked row's cell, double-click, or
  press `F2`; `Enter` keeps it, `Esc` leaves it as it was.
- **Changing many at once**: right-click picked rows for Colour…, Fill…, No fill,
  Width, Line style, Font size, Opacity, Lock / unlock, Hide and Delete.
- **Totals**: measurements and counts sharing a subject are added up under the
  list.
- **CSV** exports the list for a takeoff.

Double-click a row to go to its markup.

### Tool Chest and tool sets

The **Tool Chest** (`Alt+X`) keeps markups you use again and again, in named
**tool sets**, and they belong to you, not to the document. Every set is shown at
once, stacked down the panel; roll one up with its chevron.

- **Add**: right-click a markup ▸ **Add to Tool Chest ▸ My Tools** or **Choose a
  Tool Set…**; or right-click in a set ▸ **Add Selection**.
- **Use**: click a tool to pick it up, then click (or drag) on the page.
- **Drawing Mode** puts the markup down exactly as it was kept (a text box with
  its words). **Properties Mode** makes it a tool: draw a new one where and how big
  you like, wearing the kept look. **Scale** keeps a Drawing Mode tool's real size
  on a page of another scale.
- A tool's right-click menu also has Use Tool, Move Up, Move Down, Copy, Rename…
  and Remove; a set's has Paste, Add Selection, Rename Tool Set… and Delete Tool
  Set. Drag tools to reorder them or move them between sets.
- A set's gear button changes its view (Symbol, List or Detail) and holds its own
  commands; the slider under the sets sets how big the tools are drawn. **Tool Sets ▾** at the top: tick which sets show, **Manage Tool
  Sets…** (show, hide, order, rename and remove), **New Tool Set…** and **Import
  Tool Set…**.
- **My Tools** is always there; its first nine tools are on the number keys.
- **Bluebeam tool sets**: **File ▸ Import ▸ Tool Set…** reads a Revu `.btx` file
  as it is — colours, line weights, line styles, hatches and stamps come across.

### Markup styles and defaults

**Defaults.** Right-click a markup ▸ **Set as Default** (or the button in the
Properties panel or on the Type ▾ menu) and every new markup of that kind is drawn
the same way. Defaults are per kind and are remembered. **Tools ▸ Forget
Defaults** puts every kind back as it started.

**Markup styles.** Numbered looks for each tool, on the **Markup Styles**
toolbar, which shows the styles of the tool in hand drawn in their own colours.
Press `1` to `9` with a tool in hand (or click a style) to draw the next markup in
that style; after that one markup the tool is back on its default. **+** saves the
tool's current look as a new style; right-click a style to rename it, update it
from the selected markup, remove it or move it. While a style is picked and
nothing is selected, the Properties toolbar and panel edit the style itself.
Right-click a markup ▸ **Save as Markup Style** keeps its look as a new style.

### Stamps

The **Stamp** tool draws a status stamp; with the tool in hand, the Properties
toolbar's **Stamp** list says what the next one reads. Its **Text** is one of APPROVED,
REVIEWED, FOR CONSTRUCTION, FOR REVIEW, AS BUILT, PRELIMINARY, NOT FOR
CONSTRUCTION, SUPERSEDED, REJECTED, DRAFT, CONFIDENTIAL and ISSUED FOR TENDER —
each with its own colour — or any words you type. **Sub-text** adds a name, date
or revision under it, and **Corners** rounds its frame. Stamps from a Bluebeam
tool set keep their own drawing.

### Pages

**Thumbnails panel** (`Alt+T`). A picture of every page, as many to a row as
the panel has room for, with the page number (and label) centred under it and
its scale under that when it has one; the page picked out is framed in blue.
Click to go there; drag pages to reorder them (a run of picked pages moves
together); drop a PDF file onto it to insert its pages there. `Ctrl`+wheel over
the panel changes the picture size, as do **Larger Thumbnails** and **Smaller
Thumbnails** (on the Window menu too). The panel's title, **Thumbnails ▾**, is
its menu: every insert (Before or After), Duplicate Page, Extract Pages…, Split
Document…, Delete Pages…, Crop Pages…, Rotate Pages, Page Setup…, Set Scale… and
the two sizes. The buttons after it are **Insert Pages**, **Insert Blank Page**
and **Insert Spreadsheet Page** (each with Before or After on its arrow; a click
puts it after this page), **Duplicate Page** and **Delete Pages**; on a narrow
panel they go on a line of their own under the title.

**A workbook is one entry.** The pages of a workbook — an Excel workbook brought
in, or spreadsheet pages made here side by side — show in Thumbnails as one
entry: its first page on a stack of sheets, with **▸ Loads** over **pages 2–10**
(the document's own page numbers, which stay as they are everywhere else).
Click the picture to go to its first page; click its name (the ▸) to show its
pages one by one (**▾ Loads**, on a tinted band) and again to fold them back;
**Expand Section** / **Collapse Section** on a page's right-click menu do the
same. It starts folded. Picked, the entry is the whole workbook: Delete Pages,
Cut, Copy, Move Up / Down, Extract Pages, Print Pages and dragging it act on all
its pages; with its pages shown, a page picked is that page. Nothing goes between
an Excel workbook's sheets: a page dragged there is refused (and said so in the
status bar), and a page inserted after one of its sheets goes after the workbook.

**A page's right-click menu** (also **Document ▸ Current Page**): Page Setup…,
Set Scale…, Cut, Copy and Paste Pages (Before or After), Move Up, Move Down,
Insert Blank Page, Insert Spreadsheet Page, Insert Pages, Insert Image Page and
Insert Excel Workbook (each Before or After), Duplicate Page, Extract Pages…,
Split Document…, Delete Pages…, Crop Pages…, Rotate Pages (Clockwise or
Anticlockwise), Rename Page Label, Reset Page Label, Reset All Page Labels, Print
Pages…, **Include in Print & Export**, Flatten…, Unflatten, Colour Processing…,
Go to Page, Add Bookmark, **Calc Section Break Above This Page** (Part 2), Page
Grid, Header/Footer (Show Header, Show Footer, Headers & Footers…), Paper Size and
**Make This Page's Markups Editable** (for a page whose own annotations were not
read out as markups).

**The Document menu** has the same page commands for the whole document:
Document Properties… (`Ctrl+D`), Page Setup…, Rotate Pages, **Insert** (Blank
Page `Ctrl+Shift+N`, Spreadsheet Page, Pages `Ctrl+Shift+I`, Image Page, Excel
Workbook — each Before or After), Extract Pages… (`Ctrl+Shift+X`), Split
Document…, Delete Pages… (`Ctrl+Shift+D`), Crop Pages… (`Alt+Shift+O`),
Headers & Footers…, Colour Processing…, Flatten… (`Ctrl+Shift+M`), Unflatten,
Duplicate Page, Add Bookmark (`Ctrl+B`) and Table of Contents.

- **Insert Blank Page** asks the size, how many and where. New pages are A4
  portrait unless you choose otherwise (A0–A5, Letter, Legal, Tabloid, ANSI and
  ARCH sizes, portrait or landscape).
- **Insert Pages** brings in pages from a PDF: all, or a range such as `1-3,7`.
- **Extract Pages** saves chosen pages, with their markups, as a new PDF;
  **Split Document** saves the document as several PDFs of so many pages each.
- **Crop Pages** cuts margins off chosen pages, or drag the part to keep (**Get
  Window**); Undo restores it.
- **Rotate Pages** turns pages and everything on them a quarter turn; equations
  turn with the page but never change their results. To turn only the view, use
  **View ▸ Rotate View**.
- **Page Setup** (Revu's): new paper (Media Size, Portrait or Landscape, Width and
  Height), the content placed on it (Offset X and Y, Scale with Auto Scale,
  Rotation, Clear, Centre, Fit to Media) with a preview and a Pages range, and
  CalcForge's own calculation margins.
- **Page labels**: rename a page's label (the name shown under its thumbnail and
  in the page box).
- **Include in Print & Export** off greys a page out, with a crossed-out printer
  in its corner: it is left out of printing and export. A workbook's entry has
  the printer when some of its pages don't print, and is greyed when none do.

**Bookmarks panel** (`Alt+B`) — Add, Rename and Delete bookmarks, and
**Contents** for a table of contents. An opened PDF's own outline arrives as
bookmarks; saved, the bookmarks become the PDF's outline.

### Headers, footers and document properties

**Document ▸ Document Properties…** (`Ctrl+D`) has four tabs:

- **Information** — Title, Project, Author, Company, Subject, Keywords,
  Description, Revision and Document id. Title, author, subject and keywords also
  go into the PDF's own properties.
- **Header & footer** (also **Document ▸ Headers & Footers…**) — Show header,
  Show footer, and left, centre and right wording for each, with fields:
  `{title} {project} {author} {company} {subject} {keywords} {description}
  {revision} {id} {page} {pages} {date} {time} {file} {filename}`. SMath's formats
  go after a colon: `{date:DD.MM.YYYY}`, `{time:HH:mm}`, `{page:0001}`.
  **Sections** give a page range wording of its own; **Logo** places an image in
  any of the six slots at a chosen height.
- **Markups** — the **Author** new markups in this document are signed with
  (left empty, Preferences ▸ Author is used).
- **Grid** — Show grid, Grid snap (SMath's 9 px grid) and Margin guides.

### Colour Processing

**Document ▸ Colour Processing…** (also a page's right-click menu, and
**Colour Processing…** on a snapshot's or an image's) changes the colours of the
page's own drawing —
never the markups. **Process Type**: **Modify Colours** (one exact colour on the
current page to another; it lists only the colours used there), **Colourise**,
**Greyscale**, **Black and White**, **Luminosity, Saturation, and Hue** and **Mask
Images**. **Process Images** takes pictures along; **Pages**: all, current,
selected or a custom range. The preview shows the page before and after. A photo
offers Colourise and Mask only, as in Revu.

### Printing and exporting

**File ▸ Print…** (`Ctrl+P`; **Print Preview…** opens the same dialog) is Revu's
Print dialog with the preview built in:

- the page as it will print, with page navigation;
- **Printer** — name, Properties, To File;
- **Pages** — All Pages, Current, Selected, or Custom (a range), and **Get
  Window** to print part of a page;
- **Options** — Size and Auto, Portrait or Landscape, **Print** (Document &
  Markups, Document Only, Markups Only), Copies, Collate, Reverse, Rotation
  (Auto-Rotate 90), Page Scaling, Scale, Centre or X and Y, **Dim Page Content**,
  **Dim Filtered Markups**, **Print Visible Hyperlinks** and **Print in
  Greyscale**;
- **Defaults ▾** and **Advanced** (the print engine, resolution, bands and grid).

What prints is exactly what is drawn: equations, tables and charts are part of the
page and print with Document Only. A page with *Include in Print & Export* off, a
sheet marked **Don't Print** (see *Sheet tabs*), or a markup with its **Print**
tick off, does not print.

**File ▸ Export ▸ PDF…** (`Ctrl+E`) writes a plain PDF with the markups drawn in;
**Images…** writes every printable page as a picture; **Markups Summary…** (also
**Batch ▸ Markups Summary…**) exports the markup list.

### Searching

**Edit ▸ Search** (`Ctrl+F`) opens the **Search** panel: find words in the
**Drawing** (the PDF's own text) and in the **Markups**, with **Case** and **Whole
word**, on every page; click a hit to go there. **Replace with**, **Replace** and
**Replace all** change the words in markups (one undo step); the drawing's own
text is never changed. **Edit ▸ Replace** (`Ctrl+H`) opens it ready to replace.
Tables' cells are searched too. (In an open table, `Ctrl+F` and `Ctrl+H` are the
cells' own Find and Replace — see Part 3.)

### Viewing the drawing

- **Zoom**: the plain **wheel zooms** at the pointer, as in Revu; `Ctrl`+wheel
  scrolls; `Shift`+wheel scrolls sideways; a trackpad's two-finger scroll scrolls
  (and zooms with `Ctrl`). Preferences ▸ Mouse wheel swaps zoom and scroll: with
  the wheel scrolling, `Ctrl`+wheel zooms. As in Revu, each notch lands at once —
  no animation — and the point under the pointer stays under it; the drawing
  already made stands in (sharp where it was drawn finer) for the moment the new
  zoom's drawing takes, which starts as soon as the notches stop. Preferences ▸
  **Smooth zoom and scroll** makes each notch glide there instead. **View ▸ Fit Page**
  (`Ctrl+9`), **Fit Width** (`Ctrl+0`), **Actual Size** (`Ctrl+8`), **Zoom to
  Selection** (`Ctrl+2`), **Zoom In** and **Zoom Out** (no key by default), and the
  zoom box in the status bar.
- **Big drawing sets.** As in Revu, a page you have not looked at yet appears at
  once at low resolution and sharpens a moment later: when a document opens, a
  small picture of every page is drawn in the background, so however fast you
  scroll, flick, drag the scroll bar or zoom out, each page shows itself (soft)
  rather than a blank sheet until its sharp drawing arrives. While a zoom is
  moving, the drawing already made stands in, scaled; once you stop, the page
  is drawn sharp at exactly the zoom on screen, the same as before. Scrolling
  draws ahead in the direction you are going. Nothing needs setting.
- **Clear when zoomed out.** Below 100 % no line of the drawing is drawn
  thinner than a pixel and a bit, with smooth edges, as in Revu: every hairline
  comes out dark wherever it falls, lines of one weight look the same weight
  and coloured lines keep their colour, instead of thin lines coming out as
  pale grey pairs of pixels. Markups are drawn sharp: a thin markup line is a
  whole number of pixels wide, and one running straight across or down the
  screen (a rectangle's sides, a level line, a text box's border) is one solid
  row of pixels with no soft edge; slanting lines and curves such as clouds
  keep smooth edges, as dark as the drawing's. Words stay as they are, and
  from 100 % up lines are drawn at their own width as before. Only the screen
  changes; prints, exports and the PDF are not affected.
- **Moving about**: `Page Up` / `Page Down` move a screenful; `Home` and `End` go
  to the first and last page; `Ctrl+Left` / `Ctrl+Right` (and `Ctrl+Page Up` /
  `Ctrl+Page Down`) turn pages; `Ctrl+Home` / `Ctrl+End` reach the very ends. The
  space bar or the middle button pans.
- **Page layouts** (View, or the status bar): **Single Page Mode** (one page,
  fitted), **Continuous Mode**, **Side-by-Side Mode**, **Continuous Side-by-Side
  Mode** and **Show Cover Page in Side-by-Side**. The wheel works as in Revu:
  - **Continuous** (and Continuous Side-by-Side) scroll through all the pages, at
    Fit Page too.
  - **Single Page** (and Side-by-Side, a spread at a time) shows one page only,
    however far you zoom out. The wheel zooms or scrolls as it does in Continuous;
    scrolling moves within the page and, at its end, turns to the next (or
    previous) page.
  - Preferences ▸ **Wheel in Single Page** can have the plain wheel always scroll
    there (`Ctrl`+wheel zooming), and Preferences ▸ **Scrolling past a page's
    end** can have it stay on the page (`Ctrl+Left` / `Ctrl+Right` still turn
    it).
- **Rotate View** — turn the screen view clockwise (`Ctrl+Shift+.`) or
  anticlockwise (`Ctrl+Shift+,`) to read a sideways drawing; **Reset Rotation**.
  The page itself is not changed.
- **Split View** — this document beside another pane (drag a document tab onto the
  other pane); **Separate Views** turns the panes back into windows. The status
  bar's **Sync** links the two views (or two windows):
  - **Off** — each view moves on its own; zooming, scrolling or turning pages in
    one never moves the other.
  - **Page sync** — the same zoom and the same spot, each on its own page: zoom
    or scroll in one view and the other shows the same place (in points from
    the page's top-left corner) on whichever page it is on; going to a page in
    one view leaves the other on its page. Scrolling past a page's end carries
    the other view onto its next page too.
  - **Document sync** — scrolling, zooming and page changes in one view are
    repeated in the other, keeping the difference between them that there was
    when it was turned on.
- **Rulers** along the top and left, from the page's corner; right-click one for
  inches, centimetres, millimetres, points or picas. **Full-Screen Crosshair**:
  two lines across the drawing that meet at the pointer.
- **Show Grid** (`Ctrl+'`), **Snap to Grid**, **Show Margins**, **Name Tags** (the
  names of tables, sheets and named cells, on screen and in print).
- **Dimmer**: **View ▸ Dimmer** or **Dim Content** (`Ctrl+F5`) tones down the
  page's own drawing (0–100 %) so the markups stand out — on screen only.
- **Dark Mode** (`Ctrl+3`) — see *Customisation ▸ Themes*. The page stays white
  paper in both themes.
- **Window ▸ Full Screen** (`F11`) and **Presentation** (`Ctrl+Return`: the page
  alone over the whole screen; arrows, Space and Page Up/Down turn pages, `Esc`
  ends it).

### Files: flattening, layers and recovery

- **The saved file.** Markups are written as standard PDF annotations, each with
  its own appearance, so Revu, Acrobat or a browser show and edit them. Equations,
  tables, charts and spreadsheet pages are written into the page as drawing
  (their own layer), so every reader shows them and none can change them; CalcForge
  takes that layer off and rebuilds it from the record when it opens the file.
- **Pages deleted in another program.** When the file is opened again, a message
  lists each page deleted elsewhere by its number as saved here and its label, and
  what was on it — equations (and the variables that are now undefined), tables,
  markups, a page of a spreadsheet. A spreadsheet keeps all its cells, however many
  of its pages went, and is laid out again over the pages left. **Restore…** in that
  message, or **Document ▸ Restore Pages…** at any time until the document
  is saved, lists the pages again and puts back **what CalcForge itself had on them**
  — equations, calculation blocks and text, tables, spreadsheet cells and charts — on
  pages where they were, as one undo step. Their **markups** come back only when you
  tick **Also restore the markups that were on them** (a page that had only markups
  is restored only then), and its **drawing** — a picture, or a PDF page CalcForge
  kept as a file of its own — only when you tick **Also restore the page's
  drawing**, which can be ticked only where CalcForge still holds it. A drawing that
  was the file's own page went with it and can't come back: that page is restored as
  paper.
- **Flatten…** (`Ctrl+Shift+M`; Document and Batch menus, and a page's menu) is
  Revu's **Flatten Markups**: tick the markup types; **All Markups**, **Exclude
  Filtered Markups** or **Currently Selected Markups**; the **Pages**; and **Allow
  Markup Recovery (Unflatten)** — keep it ticked to be able to bring them back with
  **Unflatten** (`Ctrl+Shift+U`), even after saving. Right-click ▸ **Flatten**
  flattens one markup at once.
- **Autosave.** Every two minutes an unsaved change is written to a recovery copy:
  beside the document as `name.pdf.autosave`, or for an untitled document in
  CalcForge's recovery folder. If CalcForge stops before an untitled document is
  saved, it offers the copy back the next time it starts. Opening a saved
  document whose recovery copy is newer than it asks first: "A recovered version
  of *name* exists from *date and time*" — **Open Recovered** (the copy opens in
  the document's place, and Save writes it over the document), **Open Saved**
  (the document as last saved; the copy is kept for another time) or **Discard
  Recovered** (the copy is deleted). Saving deletes the copy.

## Part 2 — Calculation (SMath-style)

Equations work as in SMath Studio: typed on the page, with units, worked out in
reading order through the whole document, and shown in SMath's own look (blue
units, red errors). They are not markups: they never appear in the Markups List,
and they print as part of the page.

### Typing an equation

Switch to Calc mode (`F12`), click empty paper and type. In Markup mode, `'`
starts an equation at the pointer. In Calc mode, right-click the page ▸ **Insert
Here** has Equation, Calc Text, Calculation Block and Plot.

- **Define** with `:` — it types `≔`: `L:6'm` gives `L ≔ 6 m`.
- **Evaluate** with `=`: `L=` shows `L = 6 m`. If what is left of `=` is a single
  name (or `f(x)`) that is not defined above, SMath makes it a definition instead,
  so `x=5` defines x.
- **Units** follow a number with an apostrophe: `6'm`, `25'kN`, `2.5'kN/'m^2`. The
  unit is drawn in blue.
- **The unit box.** After `=`, the result has a small black box after it. Press →
  (or click the box) and type the unit you want the answer in — `kN·m`, `MPa`,
  `mm`, or a custom unit (below). Leave it empty for SMath's own choice.
- **Custom units.** A quantity you define, such as `kips:1000'lbf`, is a unit
  wherever it is written with the apostrophe, as in SMath: `2'kips` in an equation
  below the definition (drawn blue like any unit), `kips` in a unit box, and
  `2'kips` in cells. It can still be used as a name too (`3*kips`). A built-in
  unit of the same name (CalcForge already has `kip`) wins over the definition.
- `Enter` leaves the equation and puts the red cross below it; `Tab` and
  `Shift+Tab` go to the next or previous equation in reading order; the arrow keys
  move the red cross. `Esc` lets go of the equation.

**Keys inside an equation:**

| Type | You get |
|---|---|
| `:` | `≔` (definition): once in an equation, and once in each line of a program block (local definitions: `f(x):`, `]`, `a:x+1`, `]`, `2*a`) |
| `=` | evaluation (or a definition, as above) |
| `/` | a fraction: what is left of the cursor goes on top, and you type the bottom |
| `^` | a power: type the exponent, then → to come out |
| `(` and `)` | brackets; `)` closes the bracket you are in and carries on after it |
| `[` | an index (element): `v[2` is `v₂`; → comes out |
| `\` | a square root |
| `.` in a name | a subscript: `L.beam` is L with *beam* below |
| `'` | a unit follows (a built-in one, or a custom unit defined above) |
| `]` | SMath's Add line: a program block of two lines; inside one, a new line after the one you are in. With part of the equation selected, that part becomes its first line |
| `*` | multiply (`×` too); a number then a letter multiplies by itself: `2x` is 2·x |
| `&` and `\|` | logical and (∧) and or (∨) |
| a word and a space | turns a lone word into Calculation text |
| `"` (first) | Calculation text instead of an equation |

`Ctrl` keys: `Ctrl+=` ≡, `Ctrl+3` ≠, `Ctrl+9` ≤, `Ctrl+0` ≥, `Ctrl+\` n-th root,
`Ctrl+1` transpose, `Ctrl+8` cross product, `Ctrl+[` element, `Ctrl+E` insert a
function, `Ctrl+K` constants, `Ctrl+M` a matrix (Calc mode), `Ctrl+Shift+D`
double-check, `Ctrl+A` select all equations. `Ctrl+B`, `Ctrl+I` and `Ctrl+U`
format the equation. Inside an equation SMath's keys win: `Ctrl+0` is ≥ there and
Fit Width everywhere else.

**Autocomplete.** As you type a name, SMath's list shows the functions, units and
variables that fit; `Tab` or `Enter` puts the chosen one in, `Esc` closes it. Only
variables defined above are offered. When a name is both a unit and a variable
(`m`), you are asked which you mean.

**Inserting things.** **Calculation ▸ Function…** (`Ctrl+E`), **Operator…**,
**Constants…** (`Ctrl+K`; double-click one to insert it), **Matrix** (rows and
columns), **Plot**, **Calc Text**, **Calculation Block**, **Table** and
**Chart**; **Calculation ▸ Program** (If, For, While, Line) and the **Calculation
toolbar**. The **Maths panel** has SMath's side panel: Arithmetic, Matrices,
Boolean, Functions, Plot, Programming, Units and Constants, plus **All
functions…**, **All units…** and **Table of all constants…**; each button types
into the equation, or starts one at the red cross.

**Data files.** `wfile(value, "name")` keeps a value — a number, quantity,
matrix or text — in a file for another equation or document to read back with
`rfile("name")`; `dfile("name")` deletes it. As in SMath, these files live in one
folder of the application's own (`user` in CalcForge's data folder), whatever
document calls them, and an equation can name only a file in it, never a folder or
path, so a document from someone else cannot read, change or delete anything else
on your computer. The file is written or deleted when you leave the equation, not
while you type. (`importData` reads any text or CSV file, relative to the
document.) Files SMath Studio wrote are in SMath's own format and are not read.

**Calculation ▸ Selection** works on the part of the equation selected: **Solve**
(solve for the variable under the cursor; the roots go below), **Calculate
selection** (replace it by its value), **Invert** and **Determinant**.

### Reading order and "not defined"

An equation sees only what is defined **above** it in reading order: page 1 from
top to bottom (and left to right along a line), then page 2, and so on. Move an
equation above the definition it uses and it shows `x - not defined.` in red.
Defining a name again further down is allowed; each equation uses the latest
definition above it — whether that comes from an equation, a measurement or a
table. Turning a page never changes a result; moving a page changes the order as
moving its equations would.

**Calculate** (`F9`) recalculates everything. **Auto-Calc** (on by default)
recalculates what depends on an equation as soon as you leave it; turn it off to
calculate only with F9. **Double-Check** recalculates every result independently
and lists any difference.

### Calculation text

Words among the equations, on their grid: `"` in Calc mode (or **Calculation ▸
Calc Text**, or a lone word and a space). `Enter` starts a new line;
`Shift+Enter` leaves it. Calculation text takes fields too (right-click ▸ Insert
Field), including **Variable**, which shows an equation's current value. Like an
equation it is never flattened or hidden.

### Calculation blocks

**Calculation ▸ Calculation Block** puts a thin grey frame round the selected
equations (or starts an empty block at the red cross). The equations and text
whose top-left corner is inside are its members: they move, copy and delete with
it. Click the frame to select it; double-click to go inside.

Right-click a block: **Self-Contained** keeps what its equations define to itself
— nothing after the block sees those names, and a small *Self-contained* label
above it says so on screen;
**Select Its Equations**; **Remove Block, Keep Equations** — the Properties
panel's Calculation block section offers the same three. Blocks can sit inside
blocks; an equation belongs to the innermost self-contained one.

### Calc section breaks and Global

A **calc section break** starts the calculation afresh from a page: right-click
its thumbnail ▸ **Calc Section Break Above This Page** (also on the page's
right-click menu in Calc mode). Equations, tables and sheets before the break
are not seen after it — an equation reading one says so, and a cell gives
`#REF!`. The break shows as a purple band above its page and never prints.

To carry something past the breaks, make it **Global**: right-click an equation
▸ **Global (Read by Later Calc Sections)** or right-click its row in the Variables
panel ▸ **Make Global**; for a table's cells, right-click ▸ **Global (Read by Later
Calc Sections)**. Every later section then reads it; the same commands make it
local again.

### The Variables panel

Every name the equations define, in the order SMath reads them: its value and
unit, its page (and whether it is inside a self-contained block), and its error
in red. The definition in force at the selected equation is bold. Click a row to
go to the equation; **Find a variable** narrows the list; right-click ▸ **Go to**
or **Make Global**. Under **Tables** are what the tables give the equations: each
defined name and each column a table's headings name (`Loads.Load`), with its
value. With calc section breaks the rows come section by section.

### Plots

`@` in Calc mode (or **Calculation ▸ Plot**) puts a 2-D plot at the red cross.
Type under it a function of `x`, several joined by commas, or an n×2 matrix of
points. Double-click into a plot to work in it: the wheel zooms (`Ctrl` for x
only, `Shift` for y only) and dragging moves it. Right-click ▸ **Plot settings…**
(x and y ranges, Grid, Axes, lines or points), **Grid**, **Axes** and **Graph by
points**; the Maths panel's Plot buttons (Move, Scale, Points, Lines, Refresh) do
the same.

### How results are shown

Right-click an equation:

- **Decimal Places** — 0 to 15 (the document's default is starred), and
  **Trailing Zeros**.
- **Significant Figures** — Decimal Places counts significant figures instead.
- **Global** (above).
- **Equation ▸** **Edit Equation** (`F2`, puts the cursor in it), Display Input
  Data, Go to Definition, Show Description, Disable
  Evaluation, Ignore Units, Optimization (Symbolic, Numeric, None), Exponential
  Threshold (0–15), Fractions (Decimal, Fraction, Auto, Default, Use Mixed
  Numbers), Rounding (Half to Even, Away from Zero), Font size, **Colour…**,
  **Background…**, **Border** and **Conditional Formatting…**.

The Properties panel shows the same, in the menu's words and order, as
**Result** (Variable — what the equation defines — Decimal Places, Significant
Figures, Global, Trailing Zeros, Exponential Threshold, Fractions, Rounding,
**Result Unit** — the unit typed into the placeholder after the result — and
**Document default**) and **Equation** (Size, Colour, Background, Bold, Italic,
Underline, Border, Display Input Data, Ignore Units, Disable Evaluation and
**Conditional Formatting…**). It shows while the equation is being typed in, too.
A setting changes every selected equation in one undo step. The document's defaults — and the size and colour of new equations
— are in Preferences ▸ Calculations.

### Conditional formatting of equations

An equation's look can follow its result — a utilisation ratio over 1 in red,
under 1 in green. Right-click ▸ **Equation ▸ Conditional Formatting…**: no rules,
a preset, or rules of its own (which can be saved as a preset). A rule tests the
result (`>`, `>=`, `<`, `<=`, `=`, `<>`, between, outside) and sets the font
colour, size, bold, underline and background. **Calculation ▸ Conditional
Formatting…** holds the document's presets and which variable names use them (a
pattern such as `DCR*`). Only results without units are compared.

### Measurements as variables

Give a measurement a **Variable** name (Properties panel, or the name box at the
top of its right-click menu) — for example `L.beam` — and the equations can use
its value. It is defined at the measurement's top-left corner, in the
measurement's own unit, and follows the measurement as it is changed. Its label
then reads `name = value`.

### Tables and sheets in equations

An equation reads a table's (or spreadsheet's) values four ways — only tables
**above** it in reading order (a table's place is its top-left corner):

- **a named cell**: `W_total` (name it with Define Name or the Name Box — Part 3);
- **a cell**: `Table1.D12`, or a spreadsheet's `Seismic_Actions.H44` — a sheet whose
  name has spaces or other such characters is written with each run of them as one
  `_` (`Seismic Actions` is `Seismic_Actions`, `Tables (2)` is `Tables_2`);
- **an imported Excel workbook's name**, qualified: `Seismic_Actions_NZS1170_5.Z`
  (the workbook's name) or `Seismic_Actions.Z` (the name as that sheet's cells read
  it: the sheet's own name first, then its workbook's; a sheet's own name needs its
  sheet, `Tables.ReturnPeriodFactor`). A self-contained workbook's names are never
  read bare; see Part 3, *Excel workbooks*;
- **a column as a vector**: `Loads.Load` is the column under the heading "Load" in
  the table's first row (the heading's first word, so "Load (kN)" is `Load`), down
  to its last filled cell — e.g. `sum(Loads.Load)`;
- **the table as an interpolating lookup function**, searching its first column
  and interpolating in a straight line between rows (never beyond the table):
  `bolts(d)` gives the rest of that row; `bolts(d, "A")` (or `"A", "B"`) the values
  under those headings; `bolts(d, t)` interpolates both ways when the first row
  holds numbers; `bolts(d, 2)` the second column after the keys.

The other way round, a cell reads an equation's variable by its name (see Part 3,
*Equation variables in cells*). Tables and equations take up each other's changes
until nothing changes; a true loop is reported as circular.

**Equations follow the cells, as Excel's formulas do.** What you do to a table or
sheet is made in the equations that read it, in the same undo step:

- **rename a table or sheet** — renamed `Beam loads`, `Loads.D12` becomes
  `Beam_loads.D12`; renamed `Beams`, the lookup `Loads(d)` becomes `Beams(d)` too (a
  lookup needs a name with no spaces);
- **insert or delete rows, columns or cells, or move cells** (drag the selection's
  border, or cut and paste) — `T.A3` becomes `T.A4` when a row goes in above it,
  and follows a cell moved to another sheet;
- **delete the cell an equation reads** — the reference becomes `T.#REF` and the
  equation shows a red error, *T.#REF: the cell it read was deleted (#REF!)*, until
  you change it (undo puts the cell and the reference back);
- **rename a name** in the Name Manager — `W_total` becomes `W_sum` (an equation
  defining a variable of the same spelling keeps its own);
- **retype a column's heading** — `Loads.Load` becomes `Loads.Load_kN`. Text in
  quotes, such as a lookup's `"Load"`, is left alone, as Excel leaves text.

### Errors

An error is shown in red under the equation, and prints and exports with it.
Common ones:

- `x - not defined.` — nothing above defines x;
- `Fill in all empty elements.` — a placeholder is still empty;
- `Syntax is incorrect.` — the expression cannot be read as typed;
- `Incorrect number of arguments.` — a function was given too many or too few;
- units that cannot be added or compared;
- a table an equation reads names its own problem, such as `bolts has no heading
  C.` or `The value is outside the table bolts.`

### SMath functions

Type a function's name and an opening bracket, or use **Calculation ▸
Function…** (`Ctrl+E`). Every built-in function:

<!-- generated:smath-functions -->
The engine has **122** built-in functions.

#### Arithmetic and rounding

| Function | What it does |
|---|---|
| `abs(x)` | Absolute value (the modulus of a complex number); keeps the units. |
| `ceil(x)` | The smallest whole number greater than or equal to x. |
| `floor(x)` | The largest whole number less than or equal to x. |
| `Gamma(x)` | The gamma function (Gamma(n + 1) = n!). |
| `mixed(w, a, b)` | The mixed number w a/b as a value: mixed(2, 1, 3) is 7/3. |
| `mod(a, b)` | The remainder of a divided by b (real numbers). |
| `nthroot(x, n)` | The n-th root of x. |
| `perc(x, p)` | p per cent of x: perc(100, 5) is 5. |
| `random(n)` | A random number from 0 up to n, evenly spread. |
| `round(x, n) · round(x, n, mode)` | x rounded to n decimal places (0 to 15), halves away from zero; the mode, as in SMath, is "te" (halves to the even neighbour: round(2.5, 0, "te") is 2) or "afz" (halves away from zero). |
| `sign(x)` | 1 if x is positive, −1 if negative, 0 if zero. |
| `sqrt(x)` | Square root (also typed with \\); units are rooted too. |
| `trunc(x)` | The whole-number part of x, with the fraction cut off. |

#### Exponentials and logarithms

| Function | What it does |
|---|---|
| `exp(x)` | e raised to the power x. |
| `lg(x)` | Base-10 logarithm. |
| `ln(x)` | Natural logarithm (base e). |
| `log(x, b)` | Logarithm of x to base b. |
| `log10(x)` | Base-10 logarithm. |

#### Trigonometry

| Function | What it does |
|---|---|
| `acos(x)` | Inverse cosine, in radians. |
| `acot(x)` | Inverse cotangent. |
| `acsc(x)` | Inverse cosecant. |
| `asec(x)` | Inverse secant. |
| `asin(x)` | Inverse sine, in radians. |
| `atan(x) · atan(x, y)` | Inverse tangent; with two arguments, the angle of the point (x, y). |
| `atan2(x, y)` | The angle of the point (x, y) from the x axis, in the right quadrant. |
| `cos(x)` | Cosine. |
| `cot(x)` | Cotangent. |
| `csc(x)` | Cosecant. |
| `sec(x)` | Secant. |
| `sin(x)` | Sine; x in radians, or an angle with a unit (30'°). |
| `tan(x)` | Tangent. |

#### Hyperbolic functions

| Function | What it does |
|---|---|
| `acosh(x)` | Inverse hyperbolic cosine. |
| `acoth(x)` | Inverse hyperbolic cotangent. |
| `asinh(x)` | Inverse hyperbolic sine. |
| `atanh(x)` | Inverse hyperbolic tangent. |
| `cosh(x)` | Hyperbolic cosine. |
| `coth(x)` | Hyperbolic cotangent. |
| `csch(x)` | Hyperbolic cosecant. |
| `sech(x)` | Hyperbolic secant. |
| `sinh(x)` | Hyperbolic sine. |
| `tanh(x)` | Hyperbolic tangent. |

#### Complex numbers

| Function | What it does |
|---|---|
| `arg(z)` | The angle of z from the real axis. |
| `Im(z)` | The imaginary part of z. |
| `pol2xy(r, φ)` | Polar coordinates to rectangular (x, y). |
| `Re(z)` | The real part of z. |
| `xy2pol(x, y)` | Rectangular coordinates to polar (r, φ). |

#### Matrices and vectors

| Function | What it does |
|---|---|
| `alg(M, i, j)` | The cofactor (signed minor) of element (i, j). |
| `augment(A, B, …)` | Matrices (or columns) placed side by side. |
| `col(M, j)` | Column j of M. |
| `cols(M)` | The number of columns. |
| `csort(M, j)` | The rows of M reordered so column j is ascending. |
| `det(M)` | The determinant. |
| `diag(v)` | A square matrix with the vector v down its diagonal. |
| `el(v, i) · el(M, i, j)` | One element of a vector or matrix (the same as typing v[i). |
| `findrows(M, value, j)` | The rows of M whose column j holds value (0 if none). |
| `identity(n)` | The n × n identity matrix. |
| `invert(M)` | The inverse matrix (M⁻¹). |
| `length(M)` | The number of elements. |
| `mat(…)` | A matrix; typed as mat( it becomes a matrix box (or use Ctrl+M in Calc mode). |
| `matrix(rows, cols)` | A matrix of zeros of the given size. |
| `max(M) · max(a, b, …)` | The largest element of a matrix, or of the values given. |
| `min(M) · min(a, b, …)` | The smallest element of a matrix, or of the values given. |
| `minor(M, i, j)` | The minor of element (i, j). |
| `norm1(M)` | The L1 norm. |
| `norme(M)` | The Euclidean norm. |
| `normi(M)` | The infinity norm. |
| `range(a, b) · range(a, b, second)` | A column of values from a to b, in steps of 1, or of (second − a). |
| `rank(M)` | The rank of the matrix. |
| `reverse(M)` | The rows (or a vector's elements) in reverse order. |
| `row(M, i)` | Row i of M. |
| `rows(M)` | The number of rows. |
| `rsort(M, i)` | The columns of M reordered so row i is ascending. |
| `sort(v)` | The vector sorted ascending. |
| `stack(A, B, …)` | Matrices (or values) placed one above the other; stack(1, 2, 3) is a column vector. |
| `submatrix(M, r1, r2, c1, c2)` | The part of M from rows r1–r2 and columns c1–c2. |
| `tr(M)` | The trace: the sum of the main diagonal. |
| `transpose(M)` | The transpose (Mᵀ). |
| `vectorize(expression)` | The expression worked element by element on the vectors and matrices in it: vectorize(v*v) is the column of squares (v*v alone is the dot product), vectorize(f(v)) calls f on each element. |
| `vminor(M, i, j)` | M with row i and column j taken out. |

#### Interpolation

| Function | What it does |
|---|---|
| `ainterp(xs, ys, x)` | Akima-spline interpolation of xs, ys at x. |
| `cinterp(xs, ys, x)` | Cubic-spline interpolation of xs, ys at x. |
| `linterp(xs, ys, x)` | Straight-line interpolation of the data vectors xs, ys at x. |

#### Sums, calculus and solving

| Function | What it does |
|---|---|
| `diff(expr, x) · diff(expr, x, n)` | The value of the derivative (or n-th derivative) of expr at x's current value; x needs a value (use symbolic for the formula). |
| `eval(expr)` | Evaluates expr numerically. |
| `int(expr, x, a, b)` | The definite integral of expr from a to b (units are carried). |
| `Jacob(f, x)` | The Jacobian matrix of the vector function f at the current values of x. |
| `numden(expr)` | The numerator and denominator of expr as a two-element vector. |
| `polyroots(v)` | The roots of the polynomial whose coefficients (constant first) are in v. |
| `product(expr, i, a, b)` | Π: the product of expr for i from a to b. |
| `roots(f, x) · roots(f, x, guess)` | Solves f = 0 (or a system of equations, with vectors of f and x) by Newton's method, starting from x's current value, 1, or the guess. |
| `solve(expr, x) · solve(expr, x, a, b)` | The real roots of expr = 0 in x, searched between −1000 and 1000 or between a and b. |
| `sum(M) · sum(expr, i, a, b)` | The sum of a matrix's elements, or Σ of expr for i from a to b. |
| `symbolic(expr) · symbolic(expr, "expand" \| "factor")` | CalcForge's own: works expr out as a formula — letters without a value stay letters, and diff, int, sum, product, solve and lim give formulas. |
| `sys(…)` | A system of equations or values, for roots and for writing several at once. |

#### Text (strings)

| Function | What it does |
|---|---|
| `concat(s1, s2, …)` | The strings joined together. |
| `description(name)` | SMath's description text of a definition. CalcForge's equations have none, so it gives empty text; it is kept so SMath worksheets that use it calculate, and is not offered in Insert Function. |
| `error(s)` | Stops with the red error message s. |
| `findstr(s, find)` | The positions where find starts in s (−1 if it does not). |
| `IsString(x)` | 1 if x is a string, otherwise 0. |
| `num2str(x) · num2str(x, format)` | A number as text; formats such as "0.00", "#.##", "F2", "N2", "P1" and "0.0E+00". |
| `str2num(s)` | The expression written in a string, worked out. |
| `strlen(s)` | The number of characters. |
| `strrep(s, find, replace)` | Every occurrence of find replaced. |
| `substr(s, start) · substr(s, start, n)` | Part of a string, from position start (n characters long). |

#### Programming

| Function | What it does |
|---|---|
| `break` | Leaves the loop it is in. |
| `Clear(a, b, …)` | Forgets the named variables from here on. |
| `continue` | Goes straight to the loop's next pass. |
| `for(i, range, body) · for(start, condition, step, body)` | A loop over a range of values, or with a start, a condition and a step. |
| `if(condition, then, else)` | then when the condition is true (1), else otherwise; also the If button and Calculation ▸ Program ▸ If. |
| `line(…)` | Groups several lines into one program block: `]` in an equation (or Calculation ▸ Program ▸ Line) starts one, and adds a line in one. |
| `Sleep(ms)` | Waits the given milliseconds (at most 10 s). |
| `time(x)` | Milliseconds since midnight, 1 January 1601 (for timing). |
| `trace("text {0} {1}", a, b) · trace(a, …)` | The values as a string, placed into the text's {0}, {1}… when given. |
| `try(expr, otherwise)` | expr, or otherwise if expr gives an error. |
| `while(condition, body)` | Repeats the body while the condition holds. |

#### Information and units

| Function | What it does |
|---|---|
| `appVersion(n)` | The SMath Studio version CalcForge follows (1.3.0.9126). |
| `IsDefined(expr)` | 1 if everything in expr is defined, otherwise 0. |
| `UnitsOf(x)` | The units of x (1 when it has none): UnitsOf(5'kN) is 1 N. |

#### Files

| Function | What it does |
|---|---|
| `dfile(name)` | Deletes the file name from CalcForge's data folder when the equation is left; 1 if it was there, otherwise 0. |
| `importData(file) · importData(file, …)` | A matrix read from a text or CSV file (relative to the document); further arguments set the decimal symbol, separators and the rows and columns to read. |
| `rfile(name)` | The value wfile wrote to name (in CalcForge's data folder), as a number, quantity, matrix or text. |
| `wfile(expression, name)` | Writes the value to the file name in CalcForge's data folder (a file name only, no folder) when the equation is left; 1 if it was written, 0 if not. A file of the same name is replaced. |
<!-- /generated -->

## Part 3 — Spreadsheets and tables (Excel-style)

### Tables and spreadsheet pages

- A **table** is a small spreadsheet anywhere on a page, beside drawings and
  equations. Draw one with the **Table** tool (Tools or Calculation toolbar): drag
  a rectangle and the rows and columns appear as it grows. It has a name
  (Table1…) on a tab above it, always prints, and is part of the page in the saved
  PDF. Dragging its edge or corner adds or removes rows and columns.
- A **spreadsheet page** is a whole page of cells: **Document ▸ Insert ▸
  Spreadsheet Page ▸ Before / After**, the Thumbnails panel's Insert Spreadsheet
  Page button, or a page's right-click menu. Consecutive spreadsheet pages are **one sheet** that
  grows a page at a time; the columns that fit inside the page margins print, and
  everything to the right of the blue line is a **scratch area** for side
  calculations that never prints. Only markups can go on a spreadsheet page.

**Opening the cells.** In Calc mode click a table to work in it; in Markup mode a
table is a markup (click selects, drag moves) and a double-click opens its cells
(or right-click ▸ **Edit Table**). Click outside it or press `Esc` to close it.
On a spreadsheet page, in Markup mode, `Ctrl`+drag box-selects markups over the
cells and a plain drag selects cells. While a table is open it shows Excel's row
and column headings, the selection and the fill handle; on a long sheet the column
letters and row numbers stay in view as you scroll.

**The formula bar** (above the page while cells are open): the **Name Box** (the
selected cell or block — type an address such as `B4` or `A1:C3` to go there; its
▾ lists the names), the cell's formula or value, and the **unit box**.

### Typing and moving

As in Excel: typing replaces the cell; `F2` or a double-click edits it; `Enter`
keeps it and moves down, `Tab` right; `Esc` throws the typing away; the arrow
keys, `Home`, `Ctrl`+arrows, `Ctrl+Home` and `Ctrl+End`, `Page Up` and `Page Down`
move, with `Shift` to extend the selection. Click, drag and `Shift`+click select
cells; the headings select rows and columns; the corner selects everything.
`Ctrl+Space` and `Shift+Space` select the column and the row. `Ctrl+Enter` fills
the selection with what you typed. `Enter` on the last row adds a row.

What a typed entry becomes: `5` a number; `1,250.5` with a thousands format;
`12%` a percentage; `$1,200` currency; `(40)` −40; `5 kN` or `5'kN` a quantity;
`2026-10-09` or `9/10/2026` a date (day first); `14:30` a time; `TRUE`; `#N/A`;
`'anything` text; `=A1+1` a formula.

A number too wide for its column is rounded to fit (General format) or written
`1.2E+09`; `####` appears only when even that will not fit. Typing a number into a
column whose width was never set widens it.

### Formulas and references

Excel's syntax: `=SUM(B2:B9)*1.2`. While you type a formula, a click on a cell (or
the arrow keys) puts its address in, the references are coloured, and `F4` cycles
the `$` signs on the reference at the cursor. **Formula AutoComplete** lists
functions, names and tables as you type (`Tab` puts one in), and a tip shows the
function's arguments with the current one in bold.

- **Other sheets and tables**: `='Sheet 2'!B4`, `=Table1!C3`.
- **Structured references** to a table (its first row being the headings):
  `Loads[Load]`, `Loads[@Load]`, `Loads[[#Headers],[Load]]`, `Loads[#All]`,
  `Loads[#Data]`, `Loads[[Load]:[Span]]`. They follow renames and grow with the
  table, and follow a retyped heading (`Loads[Load]` becomes `Loads[Load kN]`) —
  unless the old heading heads another column too.
- **References follow the cells, Excel's way**: inserted and deleted rows, columns
  and cells, and cells moved by dragging the selection's border or by cut and
  paste, are followed by every formula, name and chart that reads them; a
  reference to a deleted cell becomes `#REF!`, and so does one to a cell that
  moved cells were dropped onto. The equations follow the same way (Part 2,
  *Tables and sheets in equations*).
- **Dynamic arrays** spill: `=SORT(A2:A9)`, `=FILTER(…)`, `=UNIQUE(…)`,
  `=SEQUENCE(5)`. A spill that would run out of a table is `#SPILL!`.
- **Errors explained**: select or hover over a cell with an error and the status
  line says why, following it back to where it started — `#UNITS! — kN and m can't
  be added (A1 + A2)`.
- **Links**: `=HYPERLINK("https://…", "Code clause")` shows the friendly text;
  over the cell the pointer becomes a pointing hand, and `Ctrl`+click (or
  right-click ▸ **Open Hyperlink**) follows it. A web or mail address opens in your
  browser or mail program; `#Sheet2!A1` (or `#Name`) goes to that place in the
  document; a file on the computer is opened only after you say yes, since a
  document from someone else can name any file. A plain click selects the cell,
  as on the rest of the page.
- **Circular references** show 0 in the loop's cells and are reported.
- **AutoSum** (`Alt+=`), today's date (`Ctrl+;`), the time (`Ctrl+Shift+:`).
- Volatile functions (NOW, TODAY, RAND, OFFSET, INDIRECT…) recalculate at every
  change, as in Excel.

### Names

A **name** stands for a cell, a block or a constant (`W_total`,
`Loads!$B$2:$B$9`, `g = 9.81`), and cell formulas and the equations use it alike.

- **Define Name…** (right-click ▸ Names), the **Name Box** (select the cells, type
  the name, `Enter`), **Name Manager…** (`Ctrl+F3`: every name, to add, edit or
  delete) and **Create from Selection…** (`Ctrl+Shift+F3`: names from the labels in
  the top row or left column).
- Excel's rules: a name starts with a letter; names that look like a cell (`A1`,
  `R1C1`) are refused; `NAME(` is a function and a bare `NAME` is a name or
  variable.
- A name is kept with the sheet whose cells it names, so it is saved, undone and
  copied with it.
- **Renaming a name** in the Name Manager renames it in every formula, name and
  equation that uses it, as Excel does; a sheet's own name of the same spelling is
  another name and is left alone.
- The cell's right-click menu starts with its **Variable** name box (typed as
  SMath writes a name: `.` makes a subscript) and the **Global** tick.

### Units in cells

Cells hold units and calculate with them, as the equations do:

- type `5 kN` or SMath's `5'kN`; units are drawn in blue with superscripts;
  SMath's black unit box shows where the unit goes after a number, and SMath's unit
  list opens as you type one;
- in a formula a unit follows a number (`=5 kN*B2`, `=10 kN/m*B2`); on its own it
  is written with the apostrophe (`=A1/'kN`);
- a custom unit the equations define (`kip:4.448'kN`) works with the apostrophe:
  `2'kip`, `=3*'kip`; a bare word stays text or a name;
- results show sensible units: `5 kN + 200 N` is `5.2 kN`, `5 kN * 2 m` is
  `10 kN·m`, `10 kN/m * 3 m` is `30 kN`;
- units that do not match are `#UNITS!`; a quantity compared with plain 0 tests
  its sign (`=A1>0`); an empty cell added to a quantity counts as zero of that unit;
- **the unit box** after the value in the formula bar shows the selected cells'
  quantities in the unit typed into it (`kN`, `kN/m`, `MPa`, or a custom unit);
  blank shows them as typed. A finished unit that does not fit is drawn red, with
  why. **Format Cells ▸ Number** can give a display unit too;
- CalcForge's unit functions: `VALUEIN(x, "kN")` (a plain number in kN),
  `CONVERT(x, "kN")` (shown in kN), `UNITOF(x)`, `STRIPUNIT(x)` and `INTERP`.

### Equation variables in cells

A bare name in a formula is looked up as a defined name, then as an equation
variable defined **above** the sheet in reading order, then as a unit: `=fc*2`
reads the equation's `fc`. A cell reference wins over a variable spelt like one:
`var(M20)` (or `var(L.beam)`) reads the equation variable — `var(X)` with one
bare name is the variable when there is one, otherwise Excel's VAR. A name that is
neither is `#NAME?`.

### Formatting

- **Format Cells…** (`Ctrl+1`) — Excel's **Number** (General, Number, Currency,
  Accounting, Date, Time, Percentage, Fraction, Scientific, Text, Custom, with a
  display unit), **Alignment** (General, Left, Centre, Right, Fill, Justify, Centre
  Across Selection; vertical; wrap), **Font**, **Border** and **Fill** tabs.
- **The cell controls on the Properties toolbar**: font, size, **B**, **I**,
  **U**, font colour, fill, align left/centre/right, vertical alignment, Wrap,
  **Merge** (Merge & Centre, Merge Across, Merge Cells, Unmerge Cells), **Borders**
  (All, Outside, Inside, Thick Box, Top, Bottom, Left, Right, No Border), the
  number format (General, Number, Currency, Percent, Scientific, Fraction, Date,
  Time, Text, More…), fewer and more decimals, **Rows & Columns**, **Format
  Painter** and **Format…**.
- **Right-click the cells**: at the top, as an equation's menu, **Variable**
  (a name for the cells), **Decimal Places ▸** (General, 0–15: the selected cells
  show that many places, the format's kind kept — `#,##0.00`, `0.0%`,
  `0.00E+00` — as Excel's Increase and Decrease Decimal would leave it),
  **Significant Figures** (the places count significant figures instead, as
  SMath's: with three, 12345.678 shows 12300 and 0.0012345 shows 0.00123; a
  quantity keeps its unit; a General cell takes the equations' default places)
  and **Global**. Each is one undo step and is saved with the document; the
  formula bar still shows what was typed. **Properties**, at the end of the menu,
  opens the Properties panel. **Format Cells ▸ Number** has **Significant
  Figures** too. Excel has no significant figures, so a workbook exported to
  .xlsx keeps the decimal places only. Cells have no Trailing Zeros entry:
  Excel's fixed places always show them.
- **The Properties panel's Cells section**, while a table or sheet is open:
  Selection, Number Format, Decimal Places, Significant Figures, Unit, Font, Size,
  Colour, Fill, Horizontal and Vertical alignment, Bold, Italic, Underline, Wrap
  Text, Borders and Format Cells…, following the active cell. A table also shows
  its name, Layout and Options; a spreadsheet page its name and size.
- Keys: `Ctrl+B`, `Ctrl+I`, `Ctrl+U`, `Ctrl+5` (strikethrough), and Excel's number
  formats `Ctrl+Shift+~` General, `Ctrl+Shift+!` Number, `Ctrl+Shift+$` Currency,
  `Ctrl+Shift+%` Percent, `Ctrl+Shift+^` Scientific, `Ctrl+Shift+#` Date,
  `Ctrl+Shift+@` Time; borders `Ctrl+Shift+&` outline and `Ctrl+Shift+_` none.
- A new table has thin black borders on every cell; new rows and columns take the
  look of the one beside them. Cells use Excel's Calibri 11 and SMath's number
  style.

### Rows, columns and cells

Right-click a cell (or a heading) for **Insert** (Rows Above, Rows Below, Columns
Left, Columns Right, Cells… `Ctrl++`, Chart), **Delete** (Rows, Columns, Cells…
`Ctrl+-`), **Clear** (Contents, Formats, All), **Merge** and **Rows & Columns**
(Distribute Rows Evenly, Distribute Columns Evenly, AutoFit Column Width, AutoFit
Row Height, Row Height…, Column Width…, Hide Rows `Ctrl+9`, Unhide Rows
`Ctrl+Shift+9`, Hide Columns `Ctrl+0`, Unhide Columns `Ctrl+Shift+0`). Drag a
heading's border to resize (double-click to fit); drag a column to nothing to hide
it. Drag the selection's border to move the cells (`Ctrl` copies them).

### Fill, copy and paste

- The **fill handle** (the selection's corner) fills a series or copies formulas;
  **Fill Down** (`Ctrl+D`) and **Fill Right** (`Ctrl+R`).
- **Copy, Cut, Paste** (`Ctrl+C`, `Ctrl+X`, `Ctrl+V`) work with Excel both ways,
  keeping formulas and formats. **Paste Special**: Values (`Ctrl+Shift+V`),
  Formulas, Formats, Transpose. A block bigger than the table grows it.
- A copied formula reads the table it lands in; a cut keeps reading the cells it
  read.

### Conditional formatting

Right-click ▸ **Conditional Formatting**: **Highlight Cells Rules** (Greater Than,
Less Than, Between, Equal To, Not Equal To, Text that Contains, A Date Occurring,
Duplicate Values), **Top/Bottom Rules** (Top 10 Items, Top 10 %, Bottom 10 Items,
Above Average, Below Average), **Data Bars**, **Colour Scales**, **Icon Sets**,
**New Rule…**, **Clear Rules** and **Manage Rules…**. Rules compare quantities
with units (`greater than 200 kN` matches 250 kN and 0.3 MN); units that do not
match never match.

The **Conditional Formatting Rules Manager** lists the rules in the order they
apply, each with a preview of its look, the cells it applies to and **Stop If
True**; show the rules for the selection or the whole sheet; add, edit, duplicate,
delete and move them; the picked rule's cells are outlined, and **Applies to** can
be picked by dragging over the cells. Nothing changes until **OK** or **Apply**.

### Data tools

Right-click ▸ **Data**: **Sort A to Z**, **Sort Z to A**, **Custom Sort…**,
**Filter** (`Ctrl+Shift+L`: a drop-down on each heading to sort, choose values,
filter numbers or text, or Top 10), **Clear Filter**, **Remove Duplicates…**,
**Text to Columns…**, **Goal Seek…**, **Data Validation…** (any value, whole
number, decimal, list, date, time, text length or a custom formula, with an input
message, an error style and message, and an in-cell drop-down — `Alt+Down` opens
it), **Circle Invalid Data** and
**Clear Validation Circles**. **Comment** adds a note to a cell (`Shift+F2`);
**Find & Replace…** (`Ctrl+F`, `Ctrl+H`) searches the open table.

### Charts

Pick cells and choose **Calculation ▸ Chart**, right-click ▸ **Insert ▸ Chart**
(XY Scatter, Scatter with Lines, Line, Column), or press `Alt+F1`. The first
column is x (or the categories), each other column a series, and headings in the
first row name the series. A chart goes anywhere — over a sheet's cells (moving
with them) or on any page — and follows its cells as they change.

Double-click a chart (or Properties ▸ **Edit Chart…**) for the **Chart** dialog:
**Type** (XY scatter, Scatter with lines, Scatter with lines only, Line, Line with
markers, Column), the title, **Legend** (Bottom, Right, Top, None), each axis's
title, minimum, maximum, major unit, **Logarithmic scale (base 10)** and **Major
gridlines**, and each series' name, x and y cells, **error bars** (Fixed value,
Percentage, Standard deviation, Standard error or Custom; Both, Plus or Minus;
x error bars too) and **trendline** (Linear, Polynomial with its order,
Exponential, Logarithmic, Power, Moving average with its period; a set intercept;
the equation and R² on the chart). The axis titles carry the cells' units.

### Spreadsheet pages: printing and layout

- **Print area**: right-click ▸ **Page Layout ▸ Print Area ▸ Set Print Area** /
  **Clear Print Area** (also **Calculation ▸ Page Layout**). A sheet prints only its
  print area, and its pages and thumbnails follow it.
- **Page breaks**: Excel's Page Break Preview — dashed blue where they fall by
  themselves, solid blue where you put them. **Insert Page Break**, **Remove Page
  Break** and **Reset All Page Breaks**; dragging an automatic break makes it
  yours.
- **Sideways sheets**: a sheet wider than its paper prints on pages side by side,
  numbered down then over; more pages across come from a wide print area, a
  vertical page break or Fit to N pages wide.
- **Sheet Layout…** (Page Layout menu): Print area, **Rows to repeat at top**,
  **Columns to repeat at left**, Adjust to %, **Fit to** N pages wide, Centre on
  page horizontally and vertically, Print gridlines, Print row and column headings,
  and Show gridlines on screen.
- Turning a spreadsheet page turns the whole sheet between portrait and landscape
  and the page breaks flow again. Paper and orientation belong to the whole sheet.
- Cell borders always print; gridlines and headings print only when asked.

### Sheet tabs

Under the canvas, beside the scroll bar, a tab for each sheet of the workbook in
view, in reading order (tables have none). The tabs, like the formula bar, show
only in the **spreadsheet view**: while the page in view — the one the page box
shows — is a page of a workbook, or while one of its sheets is open for its cells
(a click on a cell). Scroll off the workbook and they go, once the middle of the
window is a little way past its edge (so they don't flicker at the boundary); a
sheet open for its cells is closed once none of its pages is on screen, unless a
cell is being typed in.

Click a tab to go to it; double-click to rename; drag it to move the sheet's
pages among the workbook's; **+** adds a sheet at the end of the workbook (to an
Excel workbook, one of its sheets, sharing its names). Right-click a tab — or
press and hold it, on a touch screen — for **Insert Sheet**, **Delete**,
**Rename…**, **Print** and **Go To** — and, on a sheet of an imported Excel
workbook, the **Self-contained** tick (see *Excel workbooks*). Rename a table from its right-click menu
(**Rename Table…**) or the Properties panel; references follow a rename. Sheet and
table names are unique in the whole document.

**Print / Don't Print.** **Print** on a tab's menu is ticked while the sheet
prints; untick it for **Don't Print** (one undo step). A sheet that doesn't print
has a grey tab with a crossed-out printer (its tooltip says so), and its pages
are greyed in Thumbnails. Its pages are left out of Print, Export ▸ PDF and
Images, and are not written as pages of the saved PDF, so Acrobat, Revu or a
browser neither shows nor prints them; CalcForge keeps them in the file's own
record and puts them back where they were when it opens the file. The sheet is
still part of the document: equations and other sheets read its cells as before.

### Excel workbooks

**File ▸ Open** an `.xlsx` makes a new document of it; **File ▸ Import ▸ Excel
Workbook** (or Document ▸ Insert, or a page's menu) adds one Before or After the
current page. A workbook with several worksheets asks which to bring in, and
for each whether it prints: the window lists the worksheets with a tick to bring
each in and a **Print** column, ticked (**Print**) to start; untick it for
**Don't Print** (see *Sheet tabs*). Each
worksheet becomes a run of spreadsheet pages with its cells, formulas, formatting,
sizes, merges, names, comments, validation, conditional formatting and page
layout; hidden worksheets come in too. Charts, pictures and a print scale other
than 100 % are left out, and CalcForge says so, listing any cell whose formula
gives another answer here than Excel last showed. A worksheet whose name is
already used in the document is renamed `Name (2)` (then `(3)`…), and the formulas
reading it follow. Nothing is ever written back to Excel.

Formulas come out as Excel showed them, named ranges included. Where an older
workbook's formula uses a block of cells where one value is wanted — a name of a
column such as `s_x = $J$17:$J$39` in `=s_x*w`, or `INDIRECT` of such a name —
Excel takes the cell in the formula's own row (implicit intersection); CalcForge
does the same and shows it the way Excel 365 does, with `@`: `=@s_x*@w`. A name
whose cells were deleted in Excel stays and gives `#REF!`, as in Excel.

**A workbook is one, and self-contained by default.** Its sheets share its names.
The import window has a **Self-contained** tick (ticked to start):

- **Self-contained**: its names are its own. Its cells read its names first (a
  sheet's own name wins on its sheet, as in Excel), otherwise the equation variable
  defined above the sheet; `var(X)` still reads the equation variable X. Equations
  below read any of its cells by sheet and cell (`Seismic_Actions.H44`) and its
  names only qualified — `Seismic_Actions_NZS1170_5.Cd_T_min_ULS` or
  `Seismic_Actions.Cd_T_min_ULS` — never bare. The workbook's name is its file name
  without the extension, each run of other characters one `_`
  (`Seismic_Actions_NZS1170.5.xlsm` is `Seismic_Actions_NZS1170_5`), made unique in
  the document with `_2`, `_3`…; the import's message and the Properties panel say
  it. Two workbooks with the same names stay apart.
- **Not self-contained** (untick it): its names are document variables, read bare
  by equations and other sheets, each defined where its sheet is in reading order.
  Names already used in the document (equation variables, other names, SMath's
  constants) are listed, with **Keep self-contained**, **Rename them with the
  prefix** (suggested from the workbook's name, e.g. `Seismic_`; the workbook's
  formulas follow) or **Go ahead** (reading order then decides which is read).

Change it later with the **Self-contained** tick on the sheet tab's right-click
menu, or in the Properties panel's **Workbook** section (shown while one of its
sheets is open); it is one undo step and is saved with the document. Unticking it
then lists any names already used and asks before going ahead. The Variables panel
lists a self-contained workbook's names under a heading of its own
(**Workbook Seismic_Actions_NZS1170_5**), written as the equations read them; the
Name Manager's Scope shows the workbook.

### Spreadsheet functions

Type `=` and the function's name; the tip shows its arguments (optional ones in
[brackets]). Every function the engine supports:

<!-- generated:sheet-functions -->
The engine has **471** spreadsheet functions.

#### Maths and trigonometry

| Function | What it does |
|---|---|
| `ABS(number)` | Absolute value; keeps the unit. |
| `ACOS(number)` | Inverse cosine, in radians. |
| `ACOSH(number)` | Inverse hyperbolic cosine. |
| `ACOT(value)` | Inverse cotangent, in radians. |
| `ACOTH(value)` | Inverse hyperbolic cotangent. |
| `AGGREGATE(function_num, options, ref1, …)` | One of 19 summaries (SUM, AVERAGE, LARGE…) that can skip errors and hidden rows. |
| `ARABIC(value)` | A Roman numeral as a number. |
| `ASIN(number)` | Inverse sine, in radians. |
| `ASINH(value)` | Inverse hyperbolic sine. |
| `ATAN(number)` | Inverse tangent, in radians. |
| `ATAN2(x_num, y_num)` | The angle of the point (x, y) from the x axis, in radians. |
| `ATANH(value)` | Inverse hyperbolic tangent. |
| `BASE(number, radix, [min_length])` | A number written in another base (2 to 36) as text. |
| `CEILING(number, significance)` | Rounded up to the nearest multiple of significance. |
| `CEILING.MATH(number, [significance], [mode])` | Rounded up to a multiple, with a choice for negative numbers. |
| `CEILING.PRECISE(value, [significance])` | Rounded up to a multiple, whatever the sign. |
| `COMBIN(number, number_chosen)` | The number of combinations of k items from n. |
| `COMBINA(number, k)` | Combinations with repetition. |
| `COS(number)` | Cosine of an angle in radians. |
| `COSH(number)` | Hyperbolic cosine. |
| `COT(value)` | Cotangent. |
| `COTH(value)` | Hyperbolic cotangent. |
| `CSC(value)` | Cosecant. |
| `CSCH(value)` | Hyperbolic cosecant. |
| `DECIMAL(value, radix)` | Text in a given base as a decimal number. |
| `DEGREES(angle)` | Radians to degrees. |
| `EVEN(number)` | Rounded away from zero to the next even whole number. |
| `EXP(number)` | e raised to a power. |
| `FACT(number)` | Factorial, n!. |
| `FACTDOUBLE(value)` | Double factorial, n!!. |
| `FLOOR(number, significance)` | Rounded down to the nearest multiple of significance. |
| `FLOOR.MATH(number, [significance], [mode])` | Rounded down to a multiple, with a choice for negative numbers. |
| `FLOOR.PRECISE(value, [significance])` | Rounded down to a multiple, whatever the sign. |
| `GCD(value1, [value2], …)` | Greatest common divisor. |
| `INT(number)` | Rounded down to a whole number. |
| `ISO.CEILING(value, [significance])` | Rounded up to a multiple, whatever the sign (ISO). |
| `LCM(value1, [value2], …)` | Least common multiple. |
| `LN(number)` | Natural logarithm. |
| `LOG(number, [base])` | Logarithm to a base (10 when left out). |
| `LOG10(number)` | Base-10 logarithm. |
| `MDETERM(value1)` | Determinant of a square array. |
| `MINVERSE(value1)` | Inverse of a square array. |
| `MMULT(array1, array2)` | Matrix product of two arrays. |
| `MOD(number, divisor)` | Remainder after division, with the divisor's sign. |
| `MROUND(number, multiple)` | Rounded to the nearest multiple. |
| `MULTINOMIAL(value1, [value2], …)` | The multinomial of a set of numbers. |
| `MUNIT(number)` | The identity matrix of a size. |
| `ODD(number)` | Rounded away from zero to the next odd whole number. |
| `PERCENTOF(subset, everything)` | What share of the total a subset is: SUM(subset) / SUM(all). |
| `PI()` | π to 15 digits. |
| `POWER(number, power)` | A number raised to a power. |
| `PRODUCT(number1, [number2], …)` | All the arguments multiplied together; units multiply too. |
| `QUOTIENT(value, y)` | The whole-number part of a division. |
| `RADIANS(angle)` | Degrees to radians. |
| `RAND()` | A random number from 0 to 1; new at every change. |
| `RANDARRAY([rows], [cols], [lo], [hi], [whole])` | An array of random numbers (whole or not, between limits). |
| `RANDBETWEEN(bottom, top)` | A random whole number between two limits. |
| `ROMAN(number, [form])` | A number as Roman numerals, classic (0) to simplified (4). |
| `ROUND(number, num_digits)` | Rounded to a number of digits. |
| `ROUNDDOWN(number, num_digits)` | Rounded towards zero. |
| `ROUNDUP(number, num_digits)` | Rounded away from zero. |
| `SEC(value)` | Secant. |
| `SECH(value)` | Hyperbolic secant. |
| `SEQUENCE(rows, [columns], [start], [step])` | A spilled array of a sequence of numbers. |
| `SERIESSUM(value, number, m, coefficients)` | The sum of a power series. |
| `SIGN(number)` | 1, 0 or −1 by the sign. |
| `SIN(number)` | Sine of an angle in radians. |
| `SINH(number)` | Hyperbolic sine. |
| `SQRT(number)` | Square root; units are rooted too (SQRT(9 m^2) is 3 m). |
| `SQRTPI(value)` | Square root of (n × π). |
| `SUBTOTAL(function_num, ref1, [ref2], …)` | SUM, AVERAGE, COUNT… of a range, leaving out rows a filter hides (codes 101–111 also leave out rows hidden by hand). |
| `SUM(number1, [number2], …)` | Adds the arguments; quantities with units add as quantities. |
| `SUMIF(range, criteria, [sum_range])` | Adds the cells that meet one condition. |
| `SUMIFS(sum_range, criteria_range1, criteria1, [criteria_range2, criteria2], …)` | Adds the cells that meet several conditions. |
| `SUMPRODUCT(array1, [array2], …)` | The sum of the products of matching items in arrays. |
| `SUMSQ(number1, [number2], …)` | The sum of the squares. |
| `SUMX2MY2(value1, value2)` | The sum of x² − y² over two arrays. |
| `SUMX2PY2(value1, value2)` | The sum of x² + y² over two arrays. |
| `SUMXMY2(value1, value2)` | The sum of (x − y)² over two arrays. |
| `TAN(number)` | Tangent of an angle in radians. |
| `TANH(number)` | Hyperbolic tangent. |
| `TRUNC(number, [num_digits])` | Truncated to a number of digits (the fraction cut off). |

#### Statistics

| Function | What it does |
|---|---|
| `AVEDEV(value1, [value2], …)` | Average absolute deviation from the mean. |
| `AVERAGE(number1, [number2], …)` | The arithmetic mean. |
| `AVERAGEA(value1, [value2], …)` | The mean, counting text as 0 and TRUE as 1. |
| `AVERAGEIF(range, criteria, [average_range])` | The mean of the cells that meet a condition. |
| `AVERAGEIFS(average_range, criteria_range1, criteria1, [criteria_range2, criteria2], …)` | The mean of the cells that meet several conditions. |
| `BETA.DIST(value, alpha, beta, cumulative, [value1], [value2])` | The beta distribution. |
| `BETA.INV(probability, alpha, beta, [value1], [value2])` | Inverse of the beta distribution. |
| `BETADIST(value, alpha, beta, [value1], [value2])` | The cumulative beta distribution (older name). |
| `BETAINV(probability, alpha, beta, [value1], [value2])` | Inverse of the beta distribution (older name). |
| `BINOM.DIST(k, number, probability, cumulative)` | The binomial distribution. |
| `BINOM.DIST.RANGE(number, probability, text, [s2])` | The probability of a number of successes falling in a range. |
| `BINOM.INV(number, probability, alpha)` | The smallest value whose cumulative binomial is at least a criterion. |
| `BINOMDIST(k, number, probability, cumulative)` | The binomial distribution (older name). |
| `CHIDIST(value, deg_freedom)` | Right-tailed chi-squared distribution (older name). |
| `CHIINV(probability, deg_freedom)` | Inverse of the right-tailed chi-squared distribution (older name). |
| `CHISQ.DIST(value, deg_freedom, cumulative)` | The chi-squared distribution. |
| `CHISQ.DIST.RT(value, deg_freedom)` | Right-tailed chi-squared distribution. |
| `CHISQ.INV(probability, deg_freedom)` | Inverse of the left-tailed chi-squared distribution. |
| `CHISQ.INV.RT(probability, deg_freedom)` | Inverse of the right-tailed chi-squared distribution. |
| `CHISQ.TEST(actual, expected)` | The chi-squared test of independence. |
| `CHITEST(actual, expected)` | The chi-squared test (older name). |
| `CONFIDENCE(alpha, standard_dev, size)` | Confidence interval half-width, normal distribution (older name). |
| `CONFIDENCE.NORM(alpha, standard_dev, size)` | Confidence interval half-width, normal distribution. |
| `CONFIDENCE.T(alpha, standard_dev, size)` | Confidence interval half-width, Student's t. |
| `CORREL(array1, array2)` | Correlation coefficient of two arrays. |
| `COUNT(value1, [value2], …)` | How many cells hold numbers. |
| `COUNTA(value1, [value2], …)` | How many cells are not empty. |
| `COUNTBLANK(range)` | How many cells are empty. |
| `COUNTIF(range, criteria)` | How many cells meet a condition. |
| `COUNTIFS(criteria_range1, criteria1, [criteria_range2, criteria2], …)` | How many cells meet several conditions. |
| `COVAR(value1, value2)` | Population covariance (older name). |
| `COVARIANCE.P(value1, value2)` | Population covariance. |
| `COVARIANCE.S(value1, value2)` | Sample covariance. |
| `CRITBINOM(number, probability, alpha)` | Smallest value whose cumulative binomial reaches a criterion (older name). |
| `DEVSQ(value1, [value2], …)` | The sum of squared deviations from the mean. |
| `EXPON.DIST(value, lambda, cumulative)` | The exponential distribution. |
| `EXPONDIST(value, lambda, cumulative)` | The exponential distribution (older name). |
| `F.DIST(value, deg_freedom1, deg_freedom2, cumulative)` | The F distribution. |
| `F.DIST.RT(value, deg_freedom1, deg_freedom2)` | Right-tailed F distribution. |
| `F.INV(probability, deg_freedom1, deg_freedom2)` | Inverse of the F distribution. |
| `F.INV.RT(probability, deg_freedom1, deg_freedom2)` | Inverse of the right-tailed F distribution. |
| `F.TEST(a1, a2)` | The F-test on two arrays. |
| `FDIST(value, deg_freedom1, deg_freedom2)` | Right-tailed F distribution (older name). |
| `FINV(probability, deg_freedom1, deg_freedom2)` | Inverse of the right-tailed F distribution (older name). |
| `FISHER(value)` | The Fisher transformation. |
| `FISHERINV(y)` | Inverse of the Fisher transformation. |
| `FORECAST(x, known_y's, known_x's)` | A value on the straight-line fit at a given x (older name). |
| `FORECAST.LINEAR(x, known_y's, known_x's)` | A value on the straight-line fit at a given x. |
| `FREQUENCY(data, bins)` | How many values fall in each bin, as a spilled column. |
| `FTEST(a1, a2)` | The F-test (older name). |
| `GAMMA(value)` | The gamma function. |
| `GAMMA.DIST(value, alpha, beta, cumulative)` | The gamma distribution. |
| `GAMMA.INV(probability, alpha, beta)` | Inverse of the gamma distribution. |
| `GAMMADIST(value, alpha, beta, cumulative)` | The gamma distribution (older name). |
| `GAMMAINV(probability, alpha, beta)` | Inverse of the gamma distribution (older name). |
| `GAMMALN(value)` | Natural logarithm of the gamma function. |
| `GAMMALN.PRECISE(value)` | Natural logarithm of the gamma function. |
| `GAUSS(z)` | 0.5 less than the standard normal cumulative distribution. |
| `GEOMEAN(value1, [value2], …)` | The geometric mean. |
| `GROWTH(known_y's, [known_x's], [new_x's], [const])` | Values along an exponential fit. |
| `HARMEAN(value1, [value2], …)` | The harmonic mean. |
| `HYPGEOM.DIST(sample_s, number_sample, population_s, number_pop, cumulative)` | The hypergeometric distribution. |
| `HYPGEOMDIST(sample_s, number_sample, population_s, number_pop)` | The hypergeometric distribution (older name). |
| `INTERCEPT(known_y's, known_x's)` | Where the straight-line fit crosses the y axis. |
| `KURT(value1, [value2], …)` | Kurtosis. |
| `LARGE(array, k)` | The k-th largest value. |
| `LINEST(known_y's, [known_x's], [const], [stats])` | Statistics of a straight-line (least squares) fit, as an array. |
| `LOGEST(known_y, [known_x], [const], [stats])` | Statistics of an exponential fit, as an array. |
| `LOGINV(probability, mean, standard_dev)` | Inverse of the lognormal distribution (older name). |
| `LOGNORM.DIST(value, mean, standard_dev, cumulative)` | The lognormal distribution. |
| `LOGNORM.INV(probability, mean, standard_dev)` | Inverse of the lognormal distribution. |
| `LOGNORMDIST(value, mean, standard_dev)` | The cumulative lognormal distribution (older name). |
| `MAX(number1, [number2], …)` | The largest value; quantities compare as quantities. |
| `MAXA(value1, [value2], …)` | The largest value, counting text as 0 and TRUE as 1. |
| `MAXIFS(max_range, criteria_range1, criteria1, …)` | The largest value among cells that meet conditions. |
| `MEDIAN(number1, [number2], …)` | The middle value. |
| `MIN(number1, [number2], …)` | The smallest value. |
| `MINA(value1, [value2], …)` | The smallest value, counting text as 0 and TRUE as 1. |
| `MINIFS(min_range, criteria_range1, criteria1, …)` | The smallest value among cells that meet conditions. |
| `MODE(value1, [value2], …)` | The most common value (older name). |
| `MODE.MULT(value1, [value2], …)` | Every most-common value, as a spilled column. |
| `MODE.SNGL(value1, [value2], …)` | The most common value. |
| `NEGBINOM.DIST(f, text, probability, cumulative)` | The negative binomial distribution. |
| `NEGBINOMDIST(f, text, probability)` | The negative binomial distribution (older name). |
| `NORM.DIST(x, mean, standard_dev, cumulative)` | The normal distribution. |
| `NORM.INV(probability, mean, standard_dev)` | Inverse of the normal distribution. |
| `NORM.S.DIST(z, cumulative)` | The standard normal distribution. |
| `NORM.S.INV(probability)` | Inverse of the standard normal distribution. |
| `NORMDIST(value, mean, standard_dev, cumulative)` | The normal distribution (older name). |
| `NORMINV(probability, mean, standard_dev)` | Inverse of the normal distribution (older name). |
| `NORMSINV(probability)` | Inverse of the standard normal distribution (older name). |
| `PEARSON(value1, value2)` | Pearson correlation coefficient. |
| `PERCENTILE(array, k)` | The k-th percentile, inclusive (older name). |
| `PERCENTILE.EXC(value, probability)` | The k-th percentile, exclusive. |
| `PERCENTILE.INC(value, probability)` | The k-th percentile, inclusive. |
| `PERCENTRANK(array, value, [significance])` | The rank of a value as a percentage, inclusive (older name). |
| `PERCENTRANK.EXC(array, value, [significance])` | The rank of a value as a percentage, exclusive. |
| `PERCENTRANK.INC(array, value, [significance])` | The rank of a value as a percentage, inclusive. |
| `PERMUT(number, k)` | The number of permutations of k items from n. |
| `PERMUTATIONA(number, k)` | Permutations with repetition. |
| `PHI(value)` | The standard normal density at x. |
| `POISSON(value, mean, cumulative)` | The Poisson distribution (older name). |
| `POISSON.DIST(value, mean, cumulative)` | The Poisson distribution. |
| `PROB(known_x's, probs, lower, [upper])` | The probability that values fall between two limits. |
| `QUARTILE(array, quart)` | A quartile, inclusive (older name). |
| `QUARTILE.EXC(value, q)` | A quartile, exclusive. |
| `QUARTILE.INC(value, q)` | A quartile, inclusive. |
| `RANK(number, ref, [order])` | The rank of a number in a list (older name). |
| `RANK.AVG(number, ref, [order])` | The rank of a number; ties get their average rank. |
| `RANK.EQ(number, ref, [order])` | The rank of a number; ties get the top rank. |
| `RSQ(known_y's, known_x's)` | R², the square of the Pearson correlation. |
| `SKEW(value1, [value2], …)` | Skewness of a sample. |
| `SKEW.P(value1, [value2], …)` | Skewness of a population. |
| `SLOPE(known_y's, known_x's)` | Slope of the straight-line fit. |
| `SMALL(array, k)` | The k-th smallest value. |
| `STANDARDIZE(value, mean, standard_dev)` | A normalised value, (x − mean) / standard deviation. |
| `STDEV(number1, [number2], …)` | Sample standard deviation (older name). |
| `STDEV.P(number1, [number2], …)` | Population standard deviation. |
| `STDEV.S(number1, [number2], …)` | Sample standard deviation. |
| `STDEVA(value1, [value2], …)` | Sample standard deviation, counting text and logicals. |
| `STDEVP(value1, [value2], …)` | Population standard deviation (older name). |
| `STDEVPA(value1, [value2], …)` | Population standard deviation, counting text and logicals. |
| `STEYX(known_y's, known_x's)` | Standard error of the predicted y in a straight-line fit. |
| `T.DIST(value, deg_freedom, cumulative)` | Student's t distribution (left-tailed). |
| `T.DIST.2T(value, deg_freedom)` | Two-tailed Student's t distribution. |
| `T.DIST.RT(value, deg_freedom)` | Right-tailed Student's t distribution. |
| `T.INV(probability, deg_freedom)` | Inverse of the left-tailed t distribution. |
| `T.INV.2T(probability, deg_freedom)` | Inverse of the two-tailed t distribution. |
| `T.TEST(a1, a2, tails, type)` | Student's t-test on two arrays. |
| `TDIST(value, deg_freedom, tails)` | Student's t distribution (older name). |
| `TINV(probability, deg_freedom)` | Inverse of the two-tailed t distribution (older name). |
| `TREND(known_y's, [known_x's], [new_x's], [const])` | Values along a straight-line fit. |
| `TRIMMEAN(array, percent)` | The mean with a fraction of the extremes left out. |
| `TTEST(a1, a2, tails, type)` | Student's t-test (older name). |
| `VAR(number1, [number2], …)` | Sample variance — but var(X) with one bare name reads the equation variable X (see Part 3). |
| `VAR.P(number1, [number2], …)` | Population variance. |
| `VAR.S(number1, [number2], …)` | Sample variance. |
| `VARA(value1, [value2], …)` | Sample variance, counting text and logicals. |
| `VARP(value1, [value2], …)` | Population variance (older name). |
| `VARPA(value1, [value2], …)` | Population variance, counting text and logicals. |
| `WEIBULL(value, alpha, beta, cumulative)` | The Weibull distribution (older name). |
| `WEIBULL.DIST(value, alpha, beta, cumulative)` | The Weibull distribution. |
| `Z.TEST(array, value, [sigma])` | One-tailed probability of a z-test. |
| `ZTEST(array, value, [sigma])` | One-tailed probability of a z-test (older name). |

#### Logical

| Function | What it does |
|---|---|
| `AND(logical1, [logical2], …)` | TRUE if every argument is true. |
| `FALSE()` | The logical value FALSE. |
| `IF(logical_test, [value_if_true], [value_if_false])` | One value if a test is true, another if it is false. |
| `IFERROR(value, value_if_error)` | The value, or another one if it is an error. |
| `IFNA(value, value_if_na)` | The value, or another one if it is #N/A. |
| `IFS(logical_test1, value_if_true1, [logical_test2, value_if_true2], …)` | The value for the first test that is true. |
| `NOT(logical)` | The opposite logical value. |
| `OR(logical1, [logical2], …)` | TRUE if any argument is true. |
| `SWITCH(expression, value1, result1, [default_or_value2, result2], …)` | The result matching a value from a list of cases, or a default. |
| `TRUE()` | The logical value TRUE. |
| `XOR(logical1, [logical2], …)` | TRUE if an odd number of arguments are true. |

#### Lookup and reference

| Function | What it does |
|---|---|
| `ADDRESS(row, col, [type], [a1], [sheet])` | A cell's address as text, from row and column numbers. |
| `AREAS(reference)` | How many areas a reference has. |
| `CHOOSE(index_num, value1, [value2], …)` | The value at a position in a list of arguments. |
| `CHOOSECOLS(array, col_num1, [col_num2], …)` | Chosen columns of an array. |
| `CHOOSEROWS(array, row_num1, [row_num2], …)` | Chosen rows of an array. |
| `COLUMN([reference])` | The column number of a reference. |
| `COLUMNS(array)` | How many columns a reference or array has. |
| `DROP(array, rows, [columns])` | An array without its first or last rows or columns. |
| `EXPAND(array, rows, [cols], [pad_with])` | An array grown to a size, padded with a value. |
| `FILTER(array, include, [if_empty])` | The rows of an array that meet a condition, spilled. |
| `FORMULATEXT(value)` | A cell's formula as text. |
| `HLOOKUP(lookup_value, table_array, row_index_num, [range_lookup])` | Looks along the top row and returns from a row below. |
| `HSTACK(array1, [array2], …)` | Arrays placed side by side. |
| `HYPERLINK(link, [friendly])` | Shows the friendly name (or the address); Ctrl+click the cell (or right-click ▸ Open Hyperlink) follows the link: a web or mail address, a file (asked first), or #Sheet2!A1 for a place in the document. |
| `INDEX(array, row_num, [column_num])` | The value at a row and column of a range. |
| `INDIRECT(ref_text, [a1])` | The reference named by a text, such as "B4" or "Loads!A1". |
| `INTERP(x, known_x's, known_y's)` | CalcForge's own: straight-line interpolation, INTERP(x, A2:A10, B2:B10); outside the table is #N/A. |
| `LOOKUP(lookup_value, lookup_vector, [result_vector])` | Looks up a value in a row or column (the older form). |
| `MATCH(lookup_value, lookup_array, [match_type])` | The position of a value in a range. |
| `OFFSET(reference, rows, cols, [height], [width])` | A reference shifted by rows and columns from another. |
| `ROW([reference])` | The row number of a reference. |
| `ROWS(array)` | How many rows a reference or array has. |
| `SORT(array, [sort_index], [sort_order], [by_col])` | An array sorted, spilled. |
| `SORTBY(array, by_array1, [sort_order1], …)` | An array sorted by another array, spilled. |
| `TAKE(array, rows, [columns])` | The first or last rows or columns of an array. |
| `TOCOL(array, [ignore], [scan_by_column])` | An array as one column. |
| `TOROW(array, [ignore], [scan_by_column])` | An array as one row. |
| `TRANSPOSE(array)` | Rows turned into columns. |
| `TRIMRANGE(range, [trim_rows], [trim_cols])` | A reference without its empty outer rows and columns. |
| `UNIQUE(array, [by_col], [exactly_once])` | The distinct values of an array, spilled. |
| `VLOOKUP(lookup_value, table_array, col_index_num, [range_lookup])` | Looks down the first column and returns from a column to the right. |
| `VSTACK(array1, [array2], …)` | Arrays placed one above the other. |
| `WRAPCOLS(vector, count, [pad_with])` | A row or column wrapped into columns of a length. |
| `WRAPROWS(vector, count, [pad_with])` | A row or column wrapped into rows of a length. |
| `XLOOKUP(lookup_value, lookup_array, return_array, [if_not_found], [match_mode], [search_mode])` | Looks up a value and returns the matching item, with a default when not found. |
| `XMATCH(lookup_value, lookup_array, [match_mode], [search_mode])` | The position of a value, with more match and search modes than MATCH. |

#### Text

| Function | What it does |
|---|---|
| `ARRAYTOTEXT(array, [format])` | An array written as text. |
| `ASC(value)` | Full-width characters changed to half-width. |
| `CHAR(number)` | The character with a code number. |
| `CLEAN(text)` | Text without its non-printing characters. |
| `CODE(text)` | The code number of the first character. |
| `CONCAT(text1, [text2], …)` | Texts and ranges joined together. |
| `CONCATENATE(text1, [text2], …)` | Texts joined together. |
| `DBCS(value)` | Half-width characters changed to full-width. |
| `DOLLAR(value, [digits])` | A number as currency text. |
| `EXACT(text1, text2)` | TRUE if two texts are exactly the same, case included. |
| `FIND(find_text, within_text, [start_num])` | Where one text starts in another (case matters). |
| `FINDB(what, within, [start])` | FIND counting bytes. |
| `FIXED(number, [decimals], [no_commas])` | A number as text with fixed decimals. |
| `JIS(value)` | Half-width characters changed to full-width. |
| `LEFT(text, [num_chars])` | The first characters of a text. |
| `LEFTB(value, [number])` | LEFT counting bytes. |
| `LEN(text)` | How many characters a text has. |
| `LENB(value)` | LEN counting bytes. |
| `LOWER(text)` | Text in lower case. |
| `MID(text, start_num, num_chars)` | Characters from the middle of a text. |
| `MIDB(value, start, number)` | MID counting bytes. |
| `NUMBERVALUE(value, [decimal], [group])` | Text as a number, with chosen decimal and group separators. |
| `PROPER(text)` | Each word with a capital first letter. |
| `REGEXEXTRACT(value, pattern, [mode], [case_sensitivity])` | The part of a text that matches a regular expression. |
| `REGEXREPLACE(value, pattern, replacement, [occurrence], [case_sensitivity])` | Text with the matches of a regular expression replaced. |
| `REGEXTEST(value, pattern, [case_sensitivity])` | TRUE if a text matches a regular expression. |
| `REPLACE(old_text, start_num, num_chars, new_text)` | Text with characters at a position replaced. |
| `REPLACEB(value, start, count, new)` | REPLACE counting bytes. |
| `REPT(text, number_times)` | A text repeated a number of times. |
| `RIGHT(text, [num_chars])` | The last characters of a text. |
| `RIGHTB(value, [number])` | RIGHT counting bytes. |
| `SEARCH(find_text, within_text, [start_num])` | Where one text starts in another (case ignored, wildcards allowed). |
| `SEARCHB(what, within, [start])` | SEARCH counting bytes. |
| `SUBSTITUTE(text, old_text, new_text, [instance_num])` | Text with one piece of text replaced by another. |
| `T(value)` | The value if it is text, otherwise empty text. |
| `TEXT(value, format_text)` | A value as text in a number format, such as "0.00" or "d/mm/yyyy". |
| `TEXTAFTER(text, delimiter, [instance_num], …)` | The text after a delimiter. |
| `TEXTBEFORE(text, delimiter, [instance_num], …)` | The text before a delimiter. |
| `TEXTJOIN(delimiter, ignore_empty, text1, [text2], …)` | Texts joined with a delimiter, optionally skipping empty ones. |
| `TEXTSPLIT(text, col_delimiter, [row_delimiter], [ignore_empty], …)` | Text split into columns and rows at delimiters, spilled. |
| `TRIM(text)` | Text without extra spaces. |
| `UNICHAR(value)` | The Unicode character with a number. |
| `UNICODE(value)` | The Unicode number of the first character. |
| `UPPER(text)` | Text in capitals. |
| `VALUE(text)` | Text that looks like a number, as a number. |
| `VALUETOTEXT(value, [format])` | A value written as text. |

#### Date and time

| Function | What it does |
|---|---|
| `DATE(year, month, day)` | The date of a year, month and day. |
| `DATEDIF(start_date, end_date, unit)` | Whole days, months or years between two dates. |
| `DATEVALUE(date_text)` | A date written as text, as a date. |
| `DAY(serial_number)` | The day of the month. |
| `DAYS(end_date, start_date)` | The days between two dates. |
| `DAYS360(start, end, [european])` | The days between two dates on a 360-day year. |
| `EDATE(start_date, months)` | The date a number of months before or after. |
| `EOMONTH(start_date, months)` | The last day of the month a number of months away. |
| `HOUR(serial_number)` | The hour of a time. |
| `ISOWEEKNUM(value)` | The ISO week number. |
| `MINUTE(serial_number)` | The minute of a time. |
| `MONTH(serial_number)` | The month of a date. |
| `NETWORKDAYS(start_date, end_date, [holidays])` | Working days between two dates. |
| `NETWORKDAYS.INTL(start, end, [rest1], [rest2], …)` | Working days between two dates, with chosen weekend days. |
| `NOW()` | The date and time now; new at every change. |
| `SECOND(serial_number)` | The second of a time. |
| `TIME(hour, minute, second)` | The time of an hour, minute and second. |
| `TIMEVALUE(value)` | A time written as text, as a time. |
| `TODAY()` | Today's date; new at every change. |
| `WEEKDAY(serial_number, [return_type])` | The day of the week as a number. |
| `WEEKNUM(serial_number, [return_type])` | The week number in the year. |
| `WORKDAY(start_date, days, [holidays])` | The date a number of working days away. |
| `WORKDAY.INTL(start, days, [rest1], [rest2], …)` | The date a number of working days away, with chosen weekend days. |
| `YEAR(serial_number)` | The year of a date. |
| `YEARFRAC(start_date, end_date, [basis])` | The fraction of a year between two dates. |

#### Financial

| Function | What it does |
|---|---|
| `ACCRINT(issue, first_interest, settlement, rate, par, frequency, [basis], [calc_method])` | Accrued interest of a security that pays periodic interest. |
| `CUMIPMT(rate, nper, pv, start, end, type)` | Cumulative interest paid between two periods. |
| `CUMPRINC(rate, nper, pv, start, end, type)` | Cumulative principal paid between two periods. |
| `DB(cost, salvage, life, period, [month])` | Depreciation by the fixed-declining balance method. |
| `DDB(cost, salvage, life, period, [factor])` | Depreciation by the double-declining balance method. |
| `DOLLARDE(fractional, fraction)` | A fractional dollar price as a decimal. |
| `DOLLARFR(decimal, fraction)` | A decimal dollar price as a fraction. |
| `EFFECT(nominal, npery)` | The effective annual interest rate. |
| `FV(rate, nper, pmt, [pv], [type])` | Future value of an investment. |
| `FVSCHEDULE(principal, schedule)` | Future value after a schedule of interest rates. |
| `IPMT(rate, per, nper, pv, [fv], [type])` | The interest part of a payment. |
| `IRR(values, [guess])` | Internal rate of return of cash flows. |
| `ISPMT(rate, per, nper, pv)` | Interest paid in a period of a straight-line loan. |
| `MIRR(value, finance_rate, reinvest_rate)` | Modified internal rate of return. |
| `NOMINAL(effect, npery)` | The nominal annual interest rate. |
| `NPER(rate, pmt, pv, [fv], [type])` | The number of periods of an investment. |
| `NPV(rate, value1, [value2], …)` | Net present value of cash flows. |
| `PDURATION(rate, pv, fv)` | Periods needed to reach a value. |
| `PMT(rate, nper, pv, [fv], [type])` | The payment of a loan. |
| `PPMT(rate, per, nper, pv, [fv], [type])` | The principal part of a payment. |
| `PV(rate, nper, pmt, [fv], [type])` | Present value of an investment. |
| `RATE(nper, pmt, pv, [fv], [type], [guess])` | The interest rate per period. |
| `RRI(nper, pv, fv)` | The equivalent interest rate for growth. |
| `SLN(cost, salvage, life)` | Straight-line depreciation. |
| `SYD(cost, salvage, life, per)` | Sum-of-years'-digits depreciation. |
| `VDB(cost, salvage, life, start, end, [factor], [no_switch])` | Variable declining-balance depreciation between two periods. |
| `XIRR(value, dates, [guess])` | Internal rate of return of cash flows on dates. |
| `XNPV(rate, value, dates)` | Net present value of cash flows on dates. |

#### Engineering

| Function | What it does |
|---|---|
| `BESSELI(value, number)` | Modified Bessel function In(x). |
| `BESSELJ(value, number)` | Bessel function Jn(x). |
| `BESSELK(value, number)` | Modified Bessel function Kn(x). |
| `BESSELY(value, number)` | Bessel function Yn(x). |
| `BIN2DEC(value, [places])` | Binary to decimal. |
| `BIN2HEX(value, [places])` | Binary to hexadecimal. |
| `BIN2OCT(value, [places])` | Binary to octal. |
| `BITAND(value1, value2)` | Bitwise AND. |
| `BITLSHIFT(number, k)` | Bits shifted left. |
| `BITOR(value1, value2)` | Bitwise OR. |
| `BITRSHIFT(number, k)` | Bits shifted right. |
| `BITXOR(value1, value2)` | Bitwise exclusive OR. |
| `COMPLEX(re_part, im_part, [suffix])` | A complex number as text from real and imaginary parts. |
| `CONVERT(number, from_unit, to_unit)` | CONVERT(x, "kN") shows a quantity in kN; Excel's CONVERT(5, "kN", "lbf") converts a plain number between units. |
| `DEC2BIN(value, [places])` | Decimal to binary. |
| `DEC2HEX(value, [places])` | Decimal to hexadecimal. |
| `DEC2OCT(value, [places])` | Decimal to octal. |
| `DELTA(value1, [value2])` | 1 if two numbers are equal, otherwise 0. |
| `ERF(lower, [upper])` | The error function. |
| `ERF.PRECISE(value)` | The error function from 0 to x. |
| `ERFC(value)` | The complementary error function. |
| `ERFC.PRECISE(value)` | The complementary error function. |
| `GESTEP(number, [step])` | 1 if a number is at least a step, otherwise 0. |
| `HEX2BIN(value, [places])` | Hexadecimal to binary. |
| `HEX2DEC(value, [places])` | Hexadecimal to decimal. |
| `HEX2OCT(value, [places])` | Hexadecimal to octal. |
| `IMABS(value1, [value2], …)` | Modulus of a complex number. |
| `IMAGINARY(value1, [value2], …)` | Imaginary part of a complex number. |
| `IMARGUMENT(value1, [value2], …)` | Argument (angle) of a complex number. |
| `IMCONJUGATE(value1, [value2], …)` | Complex conjugate. |
| `IMCOS(value1, [value2], …)` | Cosine of a complex number. |
| `IMCOSH(value1, [value2], …)` | Hyperbolic cosine of a complex number. |
| `IMCOT(value1, [value2], …)` | Cotangent of a complex number. |
| `IMCSC(value1, [value2], …)` | Cosecant of a complex number. |
| `IMCSCH(value1, [value2], …)` | Hyperbolic cosecant of a complex number. |
| `IMDIV(value1, [value2], …)` | Quotient of two complex numbers. |
| `IMEXP(value1, [value2], …)` | Exponential of a complex number. |
| `IMLN(value1, [value2], …)` | Natural logarithm of a complex number. |
| `IMLOG10(value1, [value2], …)` | Base-10 logarithm of a complex number. |
| `IMLOG2(value1, [value2], …)` | Base-2 logarithm of a complex number. |
| `IMPOWER(z, number)` | A complex number raised to a power. |
| `IMPRODUCT(value1, [value2], …)` | Product of complex numbers. |
| `IMREAL(value1, [value2], …)` | Real part of a complex number. |
| `IMSEC(value1, [value2], …)` | Secant of a complex number. |
| `IMSECH(value1, [value2], …)` | Hyperbolic secant of a complex number. |
| `IMSIN(value1, [value2], …)` | Sine of a complex number. |
| `IMSINH(value1, [value2], …)` | Hyperbolic sine of a complex number. |
| `IMSQRT(value1, [value2], …)` | Square root of a complex number. |
| `IMSUB(value1, [value2], …)` | Difference of two complex numbers. |
| `IMSUM(value1, [value2], …)` | Sum of complex numbers. |
| `IMTAN(value1, [value2], …)` | Tangent of a complex number. |
| `OCT2BIN(value, [places])` | Octal to binary. |
| `OCT2DEC(value, [places])` | Octal to decimal. |
| `OCT2HEX(value, [places])` | Octal to hexadecimal. |

#### Information

| Function | What it does |
|---|---|
| `CELL(info_type, [reference])` | Information about a cell: its address, row, column, contents, type… |
| `ENCODEURL(value)` | Text encoded for use in a web address. |
| `ERROR.TYPE(value)` | The number of an error value (1 for #NULL! … 7 for #N/A). |
| `INFO(type_text)` | Information about the working environment. |
| `ISBLANK(value)` | TRUE if the cell is empty. |
| `ISERR(value)` | TRUE for any error except #N/A. |
| `ISERROR(value)` | TRUE for any error. |
| `ISEVEN(value)` | TRUE if the number is even. |
| `ISFORMULA(value)` | TRUE if the cell holds a formula. |
| `ISLOGICAL(value)` | TRUE if the value is TRUE or FALSE. |
| `ISNA(value)` | TRUE if the value is #N/A. |
| `ISNONTEXT(value)` | TRUE if the value is not text. |
| `ISNUMBER(value)` | TRUE if the value is a number (a quantity with a unit counts). |
| `ISODD(value)` | TRUE if the number is odd. |
| `ISOMITTED(argument)` | Inside a LAMBDA, TRUE if an argument was left out. |
| `ISREF(value)` | TRUE if the value is a reference. |
| `ISTEXT(value)` | TRUE if the value is text. |
| `N(value)` | A value as a number (text gives 0). |
| `NA()` | The error #N/A. |
| `SHEET([value])` | The sheet number of a reference. |
| `SHEETS([reference])` | How many sheets a reference covers. |
| `TYPE(value)` | The type of a value: 1 number, 2 text, 4 logical, 16 error, 64 array. |

#### Database

| Function | What it does |
|---|---|
| `DAVERAGE(database, field, criteria)` | Mean of a database column, for the records meeting criteria. |
| `DCOUNT(database, field, criteria)` | How many numbers in a database column meet criteria. |
| `DCOUNTA(database, field, criteria)` | How many non-empty cells in a database column meet criteria. |
| `DGET(database, field, criteria)` | The one value in a database column that meets criteria. |
| `DMAX(database, field, criteria)` | Largest value in a database column meeting criteria. |
| `DMIN(database, field, criteria)` | Smallest value in a database column meeting criteria. |
| `DPRODUCT(database, field, criteria)` | Product of the values in a database column meeting criteria. |
| `DSTDEV(database, field, criteria)` | Sample standard deviation of a database column meeting criteria. |
| `DSTDEVP(database, field, criteria)` | Population standard deviation of a database column meeting criteria. |
| `DSUM(database, field, criteria)` | Sum of a database column, for the records meeting criteria. |
| `DVAR(database, field, criteria)` | Sample variance of a database column meeting criteria. |
| `DVARP(database, field, criteria)` | Population variance of a database column meeting criteria. |

#### Dynamic arrays and LAMBDA

| Function | What it does |
|---|---|
| `BYCOL(array, lambda)` | A LAMBDA applied to each column, one result per column. |
| `BYROW(array, lambda)` | A LAMBDA applied to each row, one result per row. |
| `LAMBDA([parameter1, …], calculation)` | A function of your own: =LAMBDA(x, y, x*y)(2, 3) is 6; define it as a name in the Name Manager to call it by that name. |
| `LET(name1, name_value1, calculation_or_name2, …)` | Names for values inside one formula: =LET(a, 2, b, a*3, a+b). |
| `MAKEARRAY(rows, cols, lambda)` | An array of a size, each element worked out by a LAMBDA. |
| `MAP(array1, [array2], …, lambda)` | Each element of one or more arrays through a LAMBDA. |
| `REDUCE([initial_value], array, lambda)` | An array reduced to one value by a LAMBDA, from a starting value. |
| `SCAN([initial_value], array, lambda)` | Like REDUCE, but every step's value, as an array. |

#### Units (CalcForge)

| Function | What it does |
|---|---|
| `STRIPUNIT(quantity)` | The number a quantity shows, without its unit. |
| `UNITOF(quantity)` | The unit of a quantity as text (empty for a plain number). |
| `VALUEIN(quantity, unit)` | A quantity as a plain number in a unit: VALUEIN(5000 N, "kN") is 5. |
<!-- /generated -->

## Customisation

### Preferences

**CalcForge ▸ Preferences…** (`Ctrl+,`) holds the choices that belong to you
rather than to the document; they are the same in every document you open.

<!-- generated:preferences -->
| Option | Where | Default | What it does |
|---|---|---|---|
| **Mouse wheel** | Preferences ▸ Canvas | Zooms in and out | Whether a plain turn of the wheel zooms at the pointer (as in Revu) or scrolls. Ctrl with the wheel does the other one. |
| **Wheel in Single Page** | Preferences ▸ Canvas | As the mouse wheel (as Revu) | What a plain turn of the wheel does in Single Page and Side-by-Side: the same as in Continuous (the Mouse wheel choice), as in Revu, or always scroll there, with Ctrl and the wheel zooming. |
| **Scrolling past a page's end** | Preferences ▸ Canvas | Turns to the next page | In Single Page and Side-by-Side, scrolling on past the end of the page turns to the next (or previous) page, as in Revu, or stays on the page. |
| **Smooth zoom and scroll** | Preferences ▸ Canvas | Off | Each notch of the wheel glides there over a few frames. Off, each notch lands at once, as in Revu. |
| **Author** | Preferences ▸ Writing | Your login name | The name new markups are signed with (your login name to begin with); saved PDFs carry it as each markup's author. |
| **Check spelling** | Preferences ▸ Writing | On | Words typed on the page are checked as you type. |
| **Dictionary** | Preferences ▸ Writing | New Zealand English | Which spelling words are checked against (New Zealand English). |
| **Drawing snap** | Preferences ▸ Canvas | On | Corners, midpoints and line ends pull the pointer to them while you draw. |
| **Autosize text** | Preferences ▸ Writing | On | A text box grows to fit what is typed into it. |
| **Insertion point** | Preferences ▸ Canvas | Off | A click on empty paper leaves a caret to type at; the arrow keys move it. |
| **Draw with the graphics card** | Preferences ▸ Canvas | On | Draws the pages with OpenGL for smooth scrolling on high-density screens. Turn it off if pages draw wrongly with your graphics driver. |
| **Allow Markup Recovery (Unflatten)** | Document ▸ Flatten… dialog | On | Remembered from the Flatten Markups dialog: whether flattened markups can be brought back with Unflatten. Set it there, as in Revu. |
| **Number keys pick markup styles** | Preferences ▸ Markup | On | With a markup tool in hand, 1 to 9 draw the next markup in that tool's style 1 to 9; 0 goes back to the default. |
| **Filtered Annotation Dim Percent** | Preferences ▸ Markup | 60 % | How far the markups the Markups List's filter leaves out are toned down on the page (and in print with Dim Filtered Markups). |
| **Thumbnail size** | Thumbnails panel | 1× (ordinary size) | How big the page pictures are; Ctrl and the wheel over the Thumbnails panel change it. |
| **Decimals** | Preferences ▸ Calculations | 4 | Decimal places a result is shown with, unless an equation says otherwise (0 to 15). |
| **Threshold** | Preferences ▸ Calculations | 5 | Exponential threshold: numbers with more digits than this are shown with a power of ten. |
| **Trailing Zeros** | Preferences ▸ Calculations | Off | Shows 2.5 as 2.5000 at four decimals. |
| **Fractions** | Preferences ▸ Calculations | Decimal | Results as decimals, as fractions, or whichever suits (Auto). |
| **Equation size** | Preferences ▸ Calculations | 10 pt | The size a new equation is written at, in points. |
| **Equation colour** | Preferences ▸ Calculations | #000000 (black) | The colour a new equation is written in. |
<!-- /generated -->

### Keyboard shortcuts

**CalcForge ▸ Keyboard Shortcuts…** (`F1`) lists **every command** — the menu
bar's, every right-click menu's, the toolbar and panel buttons, the tools, the
SMath keys, the spreadsheet keys and the symbols — grouped as the menus are, with
its key, its default, where it acts (always, Markup mode, Calc mode, in an
equation, while typing, in a table) and where it is offered.

- **To give a command a key**: click its **Shortcut** box and press the keys — Ctrl,
  Alt, Shift or Meta with a key, F1–F24, Insert, Delete, Home, End, Page Up/Down,
  an arrow, or a single letter or digit. It works at once and is remembered.
- `Backspace` clears the box; `Esc` puts it back. **Clear**, **Reset one** and
  **Reset all** do the same with buttons.
- A key that already does something where this one would act is shown in the bar
  under the list: **Reassign** gives it to this command, **Cancel** keeps it where
  it was. A key may mean two things only where they can never both be live (Calc
  and Markup mode, inside an equation or a table).
- Search by name or place, press a key in **Key:** to list the commands on it, or
  pick a group.
- The **Mouse and canvas** tab lists the mouse gestures.

A single character acts only when typed straight onto the page; no key acts while
you are typing.

### Themes

**View ▸ Dark Mode** (`Ctrl+3`) switches between Revu 21's dark and light themes;
CalcForge starts in dark, as Revu does, and remembers your choice. The frame,
icons and panels follow the theme; the page stays white paper in both, and what is
drawn on it keeps its own colours.

### Toolbars and panels

- **Tools ▸ Toolbars**: show or hide Main, Calculation, Measure, Tools, Markup
  Styles, Properties and Alignment (hidden at first, as Revu's); **Lock Toolbars**; **Customise Toolbars…** picks which
  markup tools are on the toolbar (a tool taken off stays on its menu and key).
- Drag a toolbar by its handle to any edge of the window. On the left or right
  it stands on end in a column of its own at the window's edge, outside the
  panel strip, so the panels still open between the strip and the page. While
  you drag it near a side edge, that column is outlined at the window's edge,
  where it will go when you let go. The Properties and Markup Styles toolbars go
  top or bottom only.
- Panels: open and close them from the edge strips or **Window ▸ Panels**; drag an
  icon to the other side; pin, float or roll up a panel from its title bar.
  **Window ▸ Pin Panels** pins them all; **Reset Layout** puts every panel and
  toolbar back where it started.
- The layout, the panels' sizes, the window's size and the Markups List's height
  are remembered between sessions.

### Tool Chest, markup styles and defaults

Your tool sets, My Tools, markup styles and per-kind defaults are kept in your
settings and are the same in every document (see Part 1). Bluebeam tool sets
import from `.btx` files.

### Line styles, hatch patterns and colours

**Manage…** at the top of the line-style and hatch lists adds your own: import an
AutoCAD `.lin` or `.pat` file, or make one. The colour picker keeps your last
eight made colours.

### Scale presets

**+ Add Preset** in Set Scale saves a custom or calibrated scale to the top of the
Preset list, for every document.

### Stamps

The Stamp's **Text** takes any words as well as the presets; keep a stamp you use
often in the Tool Chest (Drawing Mode puts it back exactly).

### Author name

New markups are signed with **Preferences ▸ Author** (your login name to begin
with), unless the document's **Document Properties ▸ Markups ▸ Author** says
otherwise. Each markup's author is in the Markups List and in the saved PDF.

### Equation defaults

**Preferences ▸ Calculations** sets how results are shown (decimals, threshold,
trailing zeros, fractions) unless an equation says otherwise, and the size and
colour of new equations. The document keeps its own number format; an equation's
**Document default** button puts it back to it.

## Keyboard shortcut reference

The keys every command has out of the box. *Works* says where a key acts. Every
command — with a key or not — is in **CalcForge ▸ Keyboard Shortcuts**, where any
key can be changed.

<!-- generated:shortcuts -->
**197** commands have a key out of the box. Every other command can be given one in Keyboard Shortcuts.

#### File

| Command | Key | Works |
|---|---|---|
| Close | `Ctrl+W` | Always |
| Exit | `Ctrl+Q` | Always |
| Export PDF | `Ctrl+E` | Always |
| Insert Pages | `Ctrl+Shift+I` | Always |
| New PDF | `Ctrl+N` | Always |
| New Tab | `Ctrl+T` | Always |
| New Window | `Ctrl+Alt+Shift+N` | Always |
| Open | `Ctrl+O` | Always |
| Print | `Ctrl+P` | Always |
| Save | `Ctrl+S` | Always |
| Save As | `Ctrl+Shift+S` | Always |

#### Edit

| Command | Key | Works |
|---|---|---|
| Copy | `Ctrl+C` | Always |
| Cut | `Ctrl+X` | Always |
| Duplicate | `Ctrl+J` | Always |
| Edit Selected | `F2` | Always |
| Lock | `Ctrl+L` | Always |
| Lock (Revu's key) | `Ctrl+Shift+L` | Always |
| Multiply | `Ctrl+M` | Markup mode |
| Offset | `O` | Always |
| Paste | `Ctrl+V` | Always |
| Paste Here | `Ctrl+Alt+V` | Always |
| Paste in Place | `Ctrl+Shift+V` | Always |
| Preferences | `Ctrl+,` | Always |
| Redo | `Ctrl+Shift+Z` | Always |
| Redo (Revu's key) | `Ctrl+Y` | Always |
| Replace | `Ctrl+H` | Always |
| Search | `Ctrl+F` | Always |
| Select All | `Ctrl+A` | Always |
| Undo | `Ctrl+Z` | Always |
| Unflatten | `Ctrl+Shift+U` | Always |

#### View

| Command | Key | Works |
|---|---|---|
| Actual Size | `Ctrl+8` | Always |
| Dark Mode | `Ctrl+3` | Always |
| Dim Content | `Ctrl+F5` | Always |
| Fit Page | `Ctrl+9` | Always |
| Fit Width | `Ctrl+0` | Always |
| Markups List | `Alt+L` | Always |
| Next Page | `Ctrl+PgDown` | Always |
| Next Page (Revu's key) | `Ctrl+Right` | Always |
| Previous Page | `Ctrl+PgUp` | Always |
| Previous Page (Revu's key) | `Ctrl+Left` | Always |
| Rotate Anticlockwise | `Ctrl+Shift+,` | Always |
| Rotate Clockwise | `Ctrl+Shift+.` | Always |
| Show Grid | `Ctrl+'` | Always |
| Zoom to Selection | `Ctrl+2` | Always |

#### Document

| Command | Key | Works |
|---|---|---|
| Flatten | `Ctrl+Shift+M` | Always |

#### Pages

| Command | Key | Works |
|---|---|---|
| Add Bookmark | `Ctrl+B` | Always |
| Crop Pages | `Alt+Shift+O` | Always |
| Delete Pages | `Ctrl+Shift+D` | Always |
| Document Properties | `Ctrl+D` | Always |
| Extract Pages | `Ctrl+Shift+X` | Always |
| Insert Blank Page | `Ctrl+Shift+N` | Always |
| Set Scale | `Ctrl+Shift+K` | Always |

#### Markup

| Command | Key | Works |
|---|---|---|
| Auto-Size | `Alt+Z` | Always |
| Check Spelling in Markups | `F7` | Always |
| Format Painter | `Ctrl+Shift+C` | Always |
| Group | `Ctrl+G` | Always |
| Ungroup | `Ctrl+Shift+G` | Always |

#### Text

| Command | Key | Works |
|---|---|---|
| Align Centre | `Ctrl+Alt+Home` | Always |
| Align Left | `Ctrl+Alt+Left` | Always |
| Align Right | `Ctrl+Alt+Right` | Always |
| Decrease Font Size | `Ctrl+Alt+Down` | Always |
| Increase Font Size | `Ctrl+Alt+Up` | Always |
| Italic | `Ctrl+I` | Always |
| Underline | `Ctrl+U` | Always |

#### Order

| Command | Key | Works |
|---|---|---|
| Bring Forward | `Ctrl+]` | Always |
| Bring to Front | `Ctrl+Shift+]` | Always |
| Send Backward | `Ctrl+[` | Always |
| Send to Back | `Ctrl+Shift+[` | Always |

#### Navigate

| Command | Key | Works |
|---|---|---|
| Pan | `Shift+V` | Markup mode |
| Select | `Esc` | Always |
| Select (Revu's key) | `V` | Markup mode |
| Snapshot | `G` | Markup mode |

#### Draw

| Command | Key | Works |
|---|---|---|
| Arc | `Shift+C` | Markup mode |
| Arrow | `A` | Markup mode |
| Cloud | `C` | Markup mode |
| Ellipse | `E` | Markup mode |
| Eraser | `Shift+E` | Markup mode |
| Highlight | `H` | Markup mode |
| Highlight Area | `J` | Markup mode |
| Line | `L` | Markup mode |
| Pen | `Alt+P` | Markup mode |
| Polygon | `P` | Markup mode |
| Polyline | `N` | Markup mode |
| Rectangle | `R` | Markup mode |

#### Annotate

| Command | Key | Works |
|---|---|---|
| Callout | `Q` | Markup mode |
| Cloud+ | `Shift+Q` | Markup mode |
| Flag | `Shift+F` | Markup mode |
| Stamp | `S` | Markup mode |
| Text Box | `T` | Markup mode |

#### Measure

| Command | Key | Works |
|---|---|---|
| Angle | `Shift+Alt+G` | Markup mode |
| Area | `Shift+Alt+A` | Markup mode |
| Count | `Shift+Alt+C` | Markup mode |
| Diameter | `Shift+Alt+D` | Markup mode |
| Dimension | `Alt+M` | Markup mode |
| Length | `M` | Markup mode |
| Perimeter | `Shift+Alt+P` | Markup mode |
| Polylength | `Shift+Alt+Q` | Markup mode |
| Volume | `Shift+Alt+V` | Markup mode |

#### Typing

| Command | Key | Works |
|---|---|---|
| Start callout | `@` | Markup mode |
| Start note | `\|` | Markup mode |
| Start text | `"` | Markup mode |

#### Symbols

| Command | Key | Works |
|---|---|---|
| Alpha α | `Ctrl+Alt+A` | While typing |
| At least ≥ | `Ctrl+Alt+.` | While typing |
| At most ≤ | `Ctrl+Alt+,` | While typing |
| Beta β | `Ctrl+Alt+B` | While typing |
| Cubed ³ | `Ctrl+Alt+3` | While typing |
| Degree ° | `Ctrl+Alt+D` | While typing |
| Delta Δ | `Ctrl+Alt+T` | While typing |
| Diameter ⌀ | `Ctrl+Alt+O` | While typing |
| Divide ÷ | `Ctrl+Alt+/` | While typing |
| Epsilon ε | `Ctrl+Alt+E` | While typing |
| Gamma γ | `Ctrl+Alt+Y` | While typing |
| Lambda λ | `Ctrl+Alt+L` | While typing |
| Micro µ | `Ctrl+Alt+M` | While typing |
| Multiply × | `Ctrl+Alt+8` | While typing |
| Not equal ≠ | `Ctrl+Alt+N` | While typing |
| Omega ω | `Ctrl+Alt+W` | While typing |
| Phi φ | `Ctrl+Alt+F` | While typing |
| Pi π | `Ctrl+Alt+P` | While typing |
| Plus/minus ± | `Ctrl+Alt+=` | While typing |
| Power ^ | `Ctrl+Alt+6` | While typing |
| Rho ρ | `Ctrl+Alt+K` | While typing |
| Sigma σ | `Ctrl+Alt+G` | While typing |
| Square root √ | `Ctrl+Alt+R` | While typing |
| Squared ² | `Ctrl+Alt+2` | While typing |
| Sum Σ | `Ctrl+Alt+S` | While typing |
| Theta θ | `Ctrl+Alt+H` | While typing |

#### SMath

| Command | Key | Works |
|---|---|---|
| At least ≥ | `Ctrl+0` | In an equation |
| At most ≤ | `Ctrl+9` | In an equation |
| Boolean equals ≡ | `Ctrl+=` | In an equation |
| Calc/Markup mode | `F12` | Always |
| Calculate | `F9` | Always |
| Constants | `Ctrl+K` | In an equation |
| Cross product × | `Ctrl+8` | In an equation |
| Double-check results | `Ctrl+Shift+D` | In an equation |
| Element (index) | `Ctrl+[` | In an equation |
| Insert function | `Ctrl+E` | In an equation |
| Insert plot | `@` | Calc mode |
| Matrix | `Ctrl+M` | Calc mode |
| N-th root | `Ctrl+\` | In an equation |
| Not equal ≠ | `Ctrl+3` | In an equation |
| Select all equations | `Ctrl+A` | In an equation |
| Start Calculation text | `"` | Calc mode |
| Start equation | `'` | Markup mode |
| Transpose | `Ctrl+1` | In an equation |

#### Spreadsheet

| Command | Key | Works |
|---|---|---|
| AutoSum | `Alt+=` | In a table / sheet |
| Bold | `Ctrl+B` | In a table / sheet |
| Copy cells | `Ctrl+C` | In a table / sheet |
| Create names from selection | `Ctrl+Shift+F3` | In a table / sheet |
| Currency format | `Ctrl+Shift+$` | In a table / sheet |
| Cut cells | `Ctrl+X` | In a table / sheet |
| Date format | `Ctrl+Shift+#` | In a table / sheet |
| Delete cells | `Ctrl+-` | In a table / sheet |
| Edit the cell | `F2` | In a table / sheet |
| Fill down | `Ctrl+D` | In a table / sheet |
| Fill right | `Ctrl+R` | In a table / sheet |
| Filter on or off | `Ctrl+Shift+L` | In a table / sheet |
| Find in the cells | `Ctrl+F` | In a table / sheet |
| Format cells | `Ctrl+1` | In a table / sheet |
| General number format | `Ctrl+Shift+~` | In a table / sheet |
| Hide columns | `Ctrl+0` | In a table / sheet |
| Hide rows | `Ctrl+9` | In a table / sheet |
| Insert cells | `Ctrl++` | In a table / sheet |
| Insert chart | `Alt+F1` | In a table / sheet |
| Insert or edit a note | `Shift+F2` | In a table / sheet |
| Insert the time | `Ctrl+Shift+:` | In a table / sheet |
| Insert today's date | `Ctrl+;` | In a table / sheet |
| Italic | `Ctrl+I` | In a table / sheet |
| Name Manager | `Ctrl+F3` | In a table / sheet |
| No borders | `Ctrl+Shift+_` | In a table / sheet |
| Number format (0.00) | `Ctrl+Shift+!` | In a table / sheet |
| Open the cell's list | `Alt+Down` | In a table / sheet |
| Outline border | `Ctrl+Shift+&` | In a table / sheet |
| Paste cells | `Ctrl+V` | In a table / sheet |
| Paste values | `Ctrl+Shift+V` | In a table / sheet |
| Percent format | `Ctrl+Shift+%` | In a table / sheet |
| Replace in the cells | `Ctrl+H` | In a table / sheet |
| Scientific format | `Ctrl+Shift+^` | In a table / sheet |
| Select all cells | `Ctrl+A` | In a table / sheet |
| Select whole column | `Ctrl+Space` | In a table / sheet |
| Select whole row | `Shift+Space` | In a table / sheet |
| Strikethrough | `Ctrl+5` | In a table / sheet |
| Time format | `Ctrl+Shift+@` | In a table / sheet |
| Underline | `Ctrl+U` | In a table / sheet |
| Unhide columns | `Ctrl+Shift+0` | In a table / sheet |
| Unhide rows | `Ctrl+Shift+9` | In a table / sheet |

#### Window

| Command | Key | Works |
|---|---|---|
| Bookmarks Panel | `Alt+B` | Always |
| Full Screen | `F11` | Always |
| Hide/Show Panels | `Shift+F4` | Always |
| Page Panel | `Alt+U` | Always |
| Presentation | `Ctrl+Return` | Always |
| Search Panel | `Alt+1` | Always |
| Thumbnails Panel | `Alt+T` | Always |
| Tool Chest Panel | `Alt+X` | Always |

#### Help

| Command | Key | Works |
|---|---|---|
| Find Tools + Commands | `Shift+F1` | Always |
| Keyboard Shortcuts | `F1` | Always |
| User Manual | `Ctrl+F1` | Always |
<!-- /generated -->
