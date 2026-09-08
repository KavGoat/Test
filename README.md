# PDF4Py

A small desktop PDF editor, inspired by
[PDF4QT](https://github.com/JakubMelka/PDF4QT) — its viewer, its Page Master
page-assembly tool and its annotation editing, reduced to the four things this
app is for:

- **Open a PDF**
- **Add and delete pages**
- **Edit the markups a PDF already has** — move them, resize them, bend a
  callout's leader line, rewrite what a text box says, group them and ungroup
  them again
- **Draw a rectangle**

Nothing else. There is no form filling, no signing, no page text editing.

---

## Install and run

```bash
git clone <this repository>
cd <this repository>
python -m pip install -r requirements.txt
python main.py                    # or: python main.py document.pdf
```

Python 3.10 or newer, PySide6 for the interface and
[PyMuPDF](https://pymupdf.readthedocs.io) for the PDF itself. Nothing else, and
no system libraries beyond a normal desktop.

Install it as a command instead, if you prefer:

```bash
python -m pip install .
pdf4py document.pdf               # or: python -m pdf4py
```

---

## Using it

| | |
|---|---|
| **Open** | `Ctrl+O`, or pass a file on the command line |
| **Save / Save As** | `Ctrl+S` / `Ctrl+Shift+S` |
| **Edit markups** (tool) | `V` — drag a markup to move it, its handles to resize or reshape it |
| **Rectangle** (tool) | `R` — drag on the page to draw one |
| **Edit text** | `F2`, or double-click a text box or a sticky note |
| **Group / Ungroup** | `Ctrl+G` / `Ctrl+Shift+G` |
| **Insert blank page after** | `Ctrl+Shift+A` — matches the current page's size |
| **Delete page** | `Ctrl+Shift+D` |
| **Zoom** | `Ctrl`+wheel zooms on the pointer; `Ctrl++`, `Ctrl+-`, `Ctrl+0` to fit |

The strip on the left is one thumbnail per page; click one to go to it. Markups
outline as you pass over them, and a rectangle you draw is red, 1.5 pt.

**Selecting.** Click a markup to select it; drag on empty paper to rubber-band
several, or `Ctrl`-click to add one at a time. A selected markup grows eight
blue handles for its size, and a callout grows an orange one at each bend of its
leader line — drag the tip to move the arrow, the middle one to move the hinge.
A sticky note has no handles: it is an icon, and stretching it would only
stretch the icon.

**Groups.** Select two or more markups and `Ctrl+G` ties them together; from
then on clicking any one of them selects the whole group and dragging moves all
of it, outlined in purple. Groups move but do not reshape — `Ctrl+Shift+G`
breaks the group and the handles come back. This is PDF's own grouping
(`/RT /Group` with `/IRT` naming the leader, PDF 32000 §12.5.6.2), so groups
made here survive a save and are understood by other PDF software.

The title bar carries a `*` while there are unsaved changes, and closing or
opening another file asks before throwing them away.

---

## Layout of the code

```
main.py            launcher
pdf4py/
  app.py           the QApplication
  document.py      the PDF and the four edits — no Qt anywhere in here
  ui/
    pageview.py    the canvas: the page, the markup items, the two tools
    pagelist.py    the page thumbnails
    mainwindow.py  menus, toolbar and the wiring between the two
    icons.py       toolbar icons, painted rather than shipped as files
    images.py      rasters from the document into Qt images
```

`document.py` keeps the same split PDF4QT does between its rendering library
and its applications: it owns the PDF and hands the interface finished images,
and the interface hands back geometry. Three details are worth knowing:

**Saving appends.** Saving back over the file it came from writes only the
change, so it takes no measurable time whatever the document's size. A full
rewrite happens only under Save As, or when the file was damaged enough that
MuPDF had to repair it — and even then without recompressing every stream in
the document, which on a ten megabyte drawing set costs seventeen seconds for a
change that took a moment to make.

**Pages are rendered without their annotations**, and every markup is then
rendered on its own and placed over the page as a separate item. That is what
makes a markup something you can pick up and drag rather than part of a picture.
A drag is clamped to the page, so a markup cannot be lost off the edge.

**Coordinates are display points** everywhere outside `document.py`: PDF user
space with the page's own `/Rotate` already applied, so a rotated page behaves
like any other. A move is written straight into the annotation's `/Rect`,
because PyMuPDF's `Annot.set_rect` re-applies the border padding on every call
and would walk the markup a point further with every drag. A resize does go
through `set_rect` — it needs the appearance redrawn, not shifted — and then
asks what it actually got and corrects the difference once, so dragging the same
handle twenty times leaves the markup exactly where it was put.

**The scene is 1:1 with the screen.** Zooming re-renders the page rather than
scaling the view, which is what keeps text crisp and lets the edit handles stay
the same size at every zoom. It also means `Ctrl`+wheel has to do its own work:
the page point under the pointer is followed through the new zoom and the
scrollbars moved to put it back under the pointer. When the whole page fits in
the window there is nothing to scroll, so it stays centred, as every other PDF
viewer does.

---

## Large documents

A two hundred page drawing set is the case the app is built for, and three
things had to be true for it to work:

**Thumbnails are drawn lazily.** A sheet of a drawing set can cost a second to
render, so drawing all two hundred up front would leave the window dead for
minutes. Every page starts as a blank sheet of the right shape, and the ones
actually on screen fill in a few hundredths of a second at a time. Adding or
deleting a page changes that one row rather than rebuilding the strip.

**The markup overlay is built in one walk of the page.** Asking for each
markup by name re-walks the annotation list every time, which is quadratic: a
sheet carrying six hundred markups took four seconds to open, and now takes a
sixth of a second.

**MuPDF's diagnostics are captured, not printed.** A damaged file makes it
write a `cannot find object in xref` line for every object it cannot find —
thousands of them, straight to the console, slow enough on Windows to be felt.
They are collected instead, and the status bar says the one thing you can act
on: the file is damaged, it was repaired to open it, and Save As will write a
clean copy. Nothing MuPDF refuses to draw can take the window down with it —
a page that will not render shows as a blank sheet and the rest still works.

Measured on a 200-page, 10 MB A1 drawing set:

| | before | after |
|---|---|---|
| Open | 2.3 s | 0.3 s |
| Insert or delete a page | 1.8 s | ~0.01 s |
| Show a page carrying 600 markups | 4.0 s | 0.17 s |
| Save | 17.4 s | ~0.00 s |

---

## Tests

```bash
python -m pytest
```

Runs headless (the suite forces `QT_QPA_PLATFORM=offscreen`). It covers the
document model — exact, drift-free moves and resizes, rotated pages, callouts,
text, grouping, page insertion and deletion, the save round trip, a deliberately
damaged file opening quietly and saving sound — and drives the real window: the
rectangle tool, dragging a markup, dragging a handle, bending a callout, moving
a group as one, zoom holding the point under the pointer, clamping at the page
edge, and the page strip staying in step without drawing pages nobody is looking
at.
