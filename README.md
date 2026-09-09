# MarkForge

A PDF markup editor for drawing review, on Windows, macOS and Linux. Open a
drawing, mark it up, save it back — as a PDF that anybody can open, with every
markup a real PDF annotation the next person can pick up and move.

It is Bluebeam's job, done in the open:

| You would normally use… | MarkForge gives you |
|---|---|
| Bluebeam Revu | The full markup tool set, scaled measurement, takeoff, tool sets |
| A PDF reader | Pages read as one scroll, at any zoom, sharp because they are re-rendered rather than magnified |
| Anything that has to open it afterwards | An ordinary PDF — the drawing untouched, the markups standard annotations |

There is no proprietary file format. **The document is a PDF.** Open a drawing,
mark it up and save, and what is written is an *incremental update*: the file
that came in is preserved byte for byte and the markups are appended after it,
so a signature over the original still covers the original. What MarkForge
knows about a markup that PDF has no word for rides along inside the same file
as an embedded record — so a round trip through MarkForge loses nothing, and a
round trip through anything else loses only what that program never understood.

Assemble a document out of several files, or paint something into a page, and
it is written afresh instead: that is not an addition to one file, and it says
so rather than pretending.

---

## Install and run

```bash
git clone <this repository>
cd <this repository>
python -m pip install -r requirements.txt
python main.py                    # or: python main.py drawing.pdf
```

Python 3.10 or newer. Everything else comes from `requirements.txt`
(PySide6, Pint, PyMuPDF) — no system libraries beyond a normal desktop.

Install it as a command instead, if you prefer:

```bash
python -m pip install .
markforge                         # or: markforge drawing.pdf
```

On a headless machine (CI, a container) run with `QT_QPA_PLATFORM=offscreen`.

---

## Markup

The complete annotation set, with a properties panel for colour, fill,
thickness, dash pattern, hatch, opacity, arrowheads, font, author and
comment:

- **Draw** — pen, highlighter, eraser, line, arrow, arc, polyline, rectangle,
  ellipse, polygon, revision cloud (box or free-form), area highlight, redaction
- **Annotate** — text box, callout with a draggable leader, cloud callout,
  sticky note, flag, status stamps (*APPROVED*, *FOR CONSTRUCTION*,
  *AS BUILT*…), images, a printed contents block
- **Measure** — length, polyline length, area, perimeter, volume, angle, radius,
  diameter, dimension, and a count tool with numbered markers

Every tool draws either way: press and drag, or click for the first point and
again for the second, with the drawing following the pointer in between.
Polylines and polygons take a click per vertex and finish on a double-click.

Selected markups get eight resize handles and a rotation handle; polylines,
polygons and callout leaders get one handle per vertex — the leader's are
orange diamonds, because they move the arrow rather than the box — and a
double-click inserts another. Shift holds a line to 0°, 45° or 90° and squares
off a box; Ctrl-dragging leaves a copy behind, and Ctrl taken hold of mid-drag
lets go of the snapping while it is held. Arrow keys nudge, and everything is
undoable.

**Snapping** picks up the grid and what is already drawn — corners, centres and
edge midpoints of anything boxed, every vertex of anything drawn as a line, and
**where two lines cross**, which is the point a drawing is most often aimed at
and the one nothing has a vertex for: two grid lines meeting, a beam arriving
at a column. What it has caught is marked with a small orange square and named
in the status bar. Snapping to the
imported drawing's own line work is a separate switch from snapping to the
markups over it, because they want different things: a corner of a beam is
worth catching exactly, and the alignment guides that help when laying markups
out only get in the way over a drawing that is already full of lines.
`View ▸ Snap`.

**Group** several markups with `Ctrl+G` and they select, move and copy as one
thing; `Ctrl+Shift+G` takes them apart. A group is a shared name rather than a
container, so the markups stay where they are on the page and grouping is one
undo step.

**Snapshot** (`G`) drags a region and copies everything in it. What comes back
is not a picture: the line work in it is copied as line work, so pasting puts
something down that stays sharp at any zoom.

The **Markups** panel is a live list of every annotation in the document —
page, type, subject, measured value, author, date and comment —
sortable, filterable, and exportable to CSV as a takeoff. Measurements and
counts sharing a subject are totalled at the bottom. The list and the drawing
are two views of one thing: pick a row and the markup is picked on the page,
pick a markup and its row is picked in the list.

### Defaults and tool sets

Change a markup's properties and press **Set as default** in the properties
panel: every rectangle after that is drawn the way you set that one up.
Defaults are per kind — a rectangle and an ellipse keep their own — and are
remembered between sessions. *Markup ▸ Forget markup defaults* puts them all
back.

The **Tool sets** panel is a tool chest. Keep anything in it, in as many named
sets as you like, and use each entry two ways:

- **as a copy**, which puts back exactly what was added, contents and all: a
  text box comes back with its words in it;
- **as properties**, which makes it a tool — draw a new one where and how big
  you like, wearing the stored colours, thickness and font.

**My Tools** is always there for quick adds, and its first nine entries are on
the number keys: press `3` on the page and you are holding the third one.
Sets are remembered between documents, because they belong to you rather than
to the job.

**Bluebeam tool sets import.** *File ▸ Import tools…* reads a `.btx` file —
the real thing, not an export of one: each tool's `Raw` field is a
zlib-compressed, hex-encoded PDF annotation dictionary, and it is parsed as
one. The sets in `btx/` are what the reader is tested against, so the tools an
office already has come across with their colours, weights, line types, hatches
and stamps intact.

### Scale and measurement

A scale is **optional**. A page starts without one, and everything still works
— measurements simply read paper distances, and the first one you draw says so.

Give a page a scale whenever you want real dimensions: click the scale button
in the status bar or right-click the page in the pages panel, then either pick
a standard ratio or press **Calibrate** — click each end of something you know
the length of and type that length. Scale is per page, so an imported 1:50
detail and a 1:200 layout can live in the same document, and each page carries
its scale beside its number in the pages panel.

Only the tools that measure something obey the scale:

| Tool | Key | Reads |
|---|---|---|
| Length | `M` | The true distance between the two ends |
| Polylength | `Shift+Alt+Q` | The true length of a run of segments |
| Area | `Shift+Alt+A` | The true area of the polygon you click out |
| Perimeter | `Shift+Alt+P` | The true distance round it |
| Volume | `Shift+Alt+V` | An area against a depth you give it |
| Angle | `Shift+Alt+G` | The angle between two legs |
| Radius · diameter | `Shift+Alt+D` | The true size of a circle |
| Rectangle | `R` | Its true width × height — and it will take an exact size |

An area measurement takes **cut-outs**: draw a polygon or an ellipse inside one
and its area comes off the total, which is how an opening is taken out of a
wall.

**A rectangle and an ellipse both know how big they are** — real dimensions on
a scaled page, paper millimetres without one. The size is in the properties
panel, where it can also be set exactly, and in the Value column of the markups
list for a takeoff. It is not written across the drawing unless you ask for it:
a page of shapes each carrying their dimensions is unreadable.

Everything else — polygon, pen, cloud, arrow, text — is a drawing, not a
measurement, and is never scaled.

The **Dimension** tool (`Alt+M`) is the exception that measures but lets you
overrule the number: it asks for the text to display, so a run of studs can
read `3600 c/c` while the takeoff total still uses what was actually measured.

### Moving and duplicating by an exact offset

`Ctrl+Shift+D` (also on the right-click menu) moves or copies whatever is
selected by a distance you type, any number of times — "across 3 m, 4 times"
lays out a row of footings. On a scaled page the offset is a real distance
(`3 m`); without a scale it is a paper one (`25 mm`).

---

## Pages

**File ▸ Open** takes a PDF and that PDF *is* the document. Its pages come in
at their own size, as their own line work rather than a picture of it, so they
stay sharp however far you zoom in — the page is re-rendered at the zoom you
are actually looking at, not magnified. Somebody else's markups come in as
markups: a Bluebeam cloud opens as a cloud you can select, recolour and move.
Its bookmarks come in too, so the sheet index a drawing set was issued with is
in the panel rather than only in the file.

**File ▸ Insert PDF pages** brings more in beside them — all pages or a range
like `1-3,7`, keeping each page's own size or fitting to A4, with a preview of
what is coming. A photo goes in the same way through **Insert image as a page**.

Right-clicking a page in the pages panel does everything else to it: insert a
blank page, PDF pages or an image either side, duplicate, move, turn it a
quarter turn either way — taking the drawing and the markups with it — put it
on a different sheet of paper, set its scale, or change its colours.
**Change colours** pushes everything dark enough to be a line onto one colour,
which is what turns a black drawing grey so red markups can be read on top of
it, or swaps one colour for another.

- **One continuous canvas.** Every page is stacked down it with a gap of desk
  between them, and you scroll through the whole document the way you would
  scroll a PDF. The wheel scrolls, `Shift`+wheel scrolls sideways,
  `Ctrl`+wheel zooms at the pointer, `Space`+drag and the middle button pan.
  `PgUp`/`PgDn` move a screenful, `Ctrl`+them move a page, and `Ctrl+Home` /
  `Ctrl+End` reach the ends. Scrolling onto another page makes it the current
  one; the view is never moved under you to tidy up.
- Drawing lands on the page under the pointer, and a markup dragged onto the
  next page belongs to that page afterwards — undo covers both.
- New pages are real pages: **A4 portrait by default**, plus A0–A5, Letter,
  Legal, Tabloid, ANSI and ARCH sizes, portrait or landscape, with adjustable
  margins — per page or applied to all.
- Thumbnail panel for adding, duplicating, deleting and reordering pages.
- Optional grid with snapping, margin guides, and header/footer templates with
  fields: `{title} {project} {author} {page} {pages} {date} {time} {file}`.
- **Order**: bring a markup to the front, send it to the back, or move it one
  step either way (`Ctrl+Shift+]`, `Ctrl+Shift+[`, `Ctrl+]`, `Ctrl+[`). The
  page's own imported line work always sits under everything drawn on it, so
  sending a markup to the back puts it behind the other markups rather than
  under the drawing, where nothing would be seen of it again.
- **Hide** a markup you want out of the way without deleting it, and *Markup ▸
  Show hidden* brings them all back. Anything can be left out of the print on
  its own, and locked so it cannot be moved.
- **Redaction that redacts**: draw the boxes, then *Markup ▸ Apply redactions*
  to overwrite the page underneath and delete the markups they cover. It says
  plainly that this cannot be undone, and that partly-overlapping markups are
  left for you to check.
- **Bookmarks** (`Ctrl+B`) name places in the document. An opened PDF's own
  outline arrives as bookmarks, and anything you add joins the same list. The
  bookmarks panel jumps to them, a **contents block** prints the same list on
  the page with page numbers and leader dots, and each line of it is a link.
  Both reach the saved PDF: the bookmarks become its outline and every contents
  line becomes a working link. A drawing set exported from here keeps the links
  it came in with as well.
- **A light and a dark theme** (View ▸ Dark). The chrome, the icons and every
  panel follow it; the page itself stays paper-white in both, and what is drawn
  on it keeps its own colour — the sheet is the sheet, whatever the frame does.
- **The window is yours.** Every panel has a pin, a float button and a close
  button in its title bar. Toolbars dock on any edge and can be locked, and
  *View ▸ Toolbars ▸ Choose tools* picks which markup tools appear on them —
  anything taken off is still on its menu and still on its key. Where
  everything sits comes back next time; *Reset the layout* puts the original
  arrangement back.
- **Print** and **print preview** through the normal system dialog, export
  pages as images, and export the markups list to CSV.
- Autosave every two minutes beside the document, offered back on the next
  start.

---

## What a saved file is

A PDF. Not a PDF-shaped container, and not a PDF with a copy of the drawing
inside it — the file you opened, plus an appended update.

- **The source page is untouched.** When the document is that PDF and the
  markups on it, its bytes are the same bytes: the update is appended after
  them. Nothing is re-encoded, re-compressed or re-rendered, so a signature
  still verifies, an embedded font stays embedded and a CAD export keeps
  whatever it was doing. (Assemble pages from several files, dim a drawing,
  flatten a markup into the sheet or turn on a running footer, and the page
  has to be painted — then the file is built rather than added to.)
- **Every markup is a real annotation.** A cloud is a `/Square` or `/Polygon`
  with a `/BE` cloudy border; a callout is a `/FreeText` with a `/CL` callout
  line and the right `/IT` intent; a measurement is a `/Line`, `/Polygon` or
  `/PolyLine` carrying a `/Measure` dictionary and the leader lines and endings
  it was drawn with. Open the file in Bluebeam, Acrobat or a browser and the
  markups are markups: selectable, movable, editable.
- **Each carries its own appearance stream**, so it looks the same wherever it
  is opened, including in readers that would not otherwise know how to draw it.
- **What PDF has no word for is not thrown away.** A markup's tool-set origin,
  its cut-outs, its group, the page's scale: these ride along as an embedded
  record in the same file, so MarkForge reads back exactly what it wrote while
  everything else reads back a perfectly ordinary annotation.

---

## Keyboard

Typing straight onto the page does **nothing unless the key is bound** — which
is what lets a bare keystroke mean "start writing here":

| Key | Starts |
|---|---|
| `"` | A text markup where the cursor is |
| `\|` | A note |
| `@` | A callout |

Everything is editable under **Help ▸ Keyboard shortcuts…** (`F1`): click a
shortcut and **press the keys you want**. A single character is stored as that
character; anything with Ctrl or Alt is stored as a key sequence and works from
the menus too. Backspace clears one, Escape puts it back, and a key bound to
two things outlines both rows in red and will not save until you resolve it.

**Tool keys are silent while you are typing.** `M` in the middle of a sentence
is a letter, and so is `Alt+M` — they only pick a tool when nothing is being
written. Save, print and zoom stay live throughout, as they do everywhere else.

| Key | Action |
|---|---|
| `Esc` | Back to Select · finish or cancel what you are doing |
| `L` `A` `Shift+C` | Line · arrow · arc |
| `R` `E` `C` | Rectangle · ellipse · revision cloud |
| `P` `Alt+P` `H` `Shift+E` | Polygon · pen · highlighter · eraser |
| `N` | Polyline |
| `T` `Q` `Shift+Q` `S` `Shift+F` | Text box · callout · cloud callout · stamp · flag |
| `J` | Highlight — dragged over anything, it darkens rather than covers |
| `G` | Snapshot — copy a region and paste it back as itself |
| `M` `Shift+Alt+A` | Measure length · measure area |
| `Alt+M` | Dimension — asks for the text to show |
| `Shift+Alt+Q` `Shift+Alt+P` `Shift+Alt+V` | Polylength · perimeter · volume |
| `Shift+Alt+G` `Shift+Alt+D` `Shift+Alt+C` | Angle · diameter · count |
| `Space`+drag, middle-drag | Pan |
| Wheel · `Shift`+wheel | Scroll · scroll sideways |
| `PgUp` / `PgDn` | A screenful · `Ctrl`+them for a whole page |
| `Ctrl+Home` / `Ctrl+End` | The start and the end of the document |
| `Ctrl`+wheel | Zoom at the pointer |
| `Ctrl+0` `Ctrl+1` `Ctrl+2` `Ctrl+Alt+0` | Fit page · fit width · fit selection · 100% |
| `Shift`+drag | Hold a line to 0°, 45° or 90° · square off a box · draw straight freehand |
| Drag right / left | Select what is wholly inside · what the marquee crosses |
| Click, click… | Lasso a shape and select what is inside it · `Enter` closes it |
| `Ctrl`+drag | Leave a copy behind · `Ctrl` mid-drag lets go of the snapping |
| Double-click | Edit the words · add a polyline vertex |
| `Ctrl+Shift+D` | Move or duplicate the selection by an exact offset |
| `Ctrl+Shift+V` | Carry what was copied on the pointer and click to drop it |
| `Ctrl+B` | Bookmark this place |
| `Ctrl+G` / `Ctrl+Shift+G` | Group · ungroup the selection |
| `Ctrl+Shift+]` / `Ctrl+Shift+[` | Bring to the front · send to the back |
| `Ctrl+]` / `Ctrl+[` | Bring forward · send backward one step |
| `1` … `9` | Pick up that tool from **My Tools** |
| `Ctrl+Alt+8` `Ctrl+Alt+R` … | Symbols — the full list under Insert ▸ Symbol |
| `Ctrl+Z` / `Ctrl+Y` | Undo · redo |

The mouse and canvas gestures are on the second tab of the same window.

---

## Layout of the code

```
markforge/
  pdf/         the PDF layer: what a PDF is made of, and MuPDF — opening,
               drawing, reading objects, writing annotations, saving
  core/        document and page model, units and formatting, typography,
               spelling
  items/       everything that can sit on a page: shapes, text, stamps,
               images, snapshots, measurements, counts
  ui/          the scene and canvas, tools, key bindings, dock panels,
               dialogs, main window
  io/          opening and saving PDFs, the incremental update, annotation
               writing, Bluebeam tool sets, vector import, links, recolouring,
               export
btx/           the real Bluebeam tool sets the importer is tested against
tests/         the suite: the engine, the items, the window, and real use
```

Three pieces are worth knowing about if you go digging:

**`pdf/`** is where every PDF file operation happens, and it is MuPDF.
`pdf/engine.py` opens files, measures and draws pages, reads their objects and
their line work, writes annotations, attachments, bookmarks and links, and
saves — either whole or as an incremental update that leaves every original
byte where it was. Nothing in it imports Qt, which is the same split PDF4QT
keeps between its rendering library and its applications: above that line a
page is a rectangle of points with markups on it, below it a page is objects
and streams. `pdf/objects.py` is the small part that is MarkForge's own — the
vocabulary a markup's annotation is described in, so that description is
written once and does not belong to whichever library writes it out.

MarkForge used to carry its own reader and writer — a lexer, the stream
filters, a cross-reference reader that could fall back to scanning. It was
correct on the files it had been shown and it was never going to be correct on
the ones it had not: a drawing set is full of files written by CAD packages
that treat the specification as a suggestion. MuPDF has had thirty years of
those fixes, and getting them for free is worth more than owning the code.

`io/pdfsave.py` is what saving goes through. It decides whether this document
is an addition to one file, and when it is, appends the annotations, the pages
that now point at them and the record — leaving the drawing that came in byte
for byte as its author wrote it, so a signature over it still verifies. That is
what makes "save" a promise rather than a re-export.

**Coordinates.** Everything above `pdf/` works in *display points*: points with
the page's own `/Rotate` already applied, origin top-left, y down — the page as
it is drawn. A PDF annotation is written in the file's own space, measured up
from the bottom-left of the *unrotated* sheet. On a page that is not turned
those differ by a flip; on one that is, by a rotation as well. `engine.to_pdf`
and `engine.to_display` are the only two places that conversion happens.

**`io/annotate.py`** is the other half of that promise: the mapping from a
markup on the canvas to the annotation dictionary that means the same thing —
`/BE` for a cloud, `/CL` and `/IT` for a callout, `/Measure` with its `/LL`,
`/LLE`, `/Cap` and line endings for a dimension — each with an appearance
stream drawn from the item itself.

**`core/typography.py`** sizes every page font in pixels rather than points.
Page coordinates are PostScript points, so a font sized in points would come
out four times too large on a 300 dpi printer; pixel sizing pins text to scene
units and lets the painter's transform scale it like any other geometry.

### Tests

```bash
python -m pytest
```

Runs headless (the suite forces `QT_QPA_PLATFORM=offscreen`) and drives the
real window: every drawing tool, selection, resize, undo, save and reload, and
the PDF that comes out at the end.

| File | What it promises |
|---|---|
| `test_pdf_engine.py` | The PDF layer: opening, page geometry under rotation, drawing, object round trips, incremental update, attachments, line work |
| `test_format.py` | What a saved document is — a PDF, the source page untouched, markups as annotations |
| `test_btx.py` | Bluebeam tool sets, read from the real `.btx` files in `btx/` |
| `test_items.py` | Serialisation, geometry and layout of every markup type |
| `test_app.py` | The window: tools, panels, undo, files, printing |
| `test_canvas.py` | One continuous scroll through every page |
| `test_layout.py` | Panels and toolbars: pinning, hiding, moving, remembering |
| `test_usability.py` | Real pointer and keyboard sequences through the viewport |
| `test_walkthrough.py` | A whole review, start to finish, the way somebody would do it |
| `test_output.py` | Exported PDFs, read back and measured |

`docs/what-matters.md` is the brief all of this is written against — what
somebody reviewing a drawing needs, and what this tool does not claim.
`docs/interface.md` is the same for the interface: who is at the keyboard, and
why the chrome looks the way it does.
