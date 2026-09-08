# PDF4Py

A small desktop PDF editor, inspired by
[PDF4QT](https://github.com/JakubMelka/PDF4QT) — its viewer, its Page Master
page-assembly tool and its annotation editing, reduced to the four things this
app is for:

- **Open a PDF**
- **Add and delete pages**
- **Move the markups a PDF already has** — drag any existing annotation
- **Draw a rectangle**

Nothing else. There is no form filling, no signing, no text editing.

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
| **Move markups** (tool) | `V` — drag any existing annotation to a new place |
| **Rectangle** (tool) | `R` — drag on the page to draw one |
| **Insert blank page after** | `Ctrl+Shift+A` — matches the current page's size |
| **Delete page** | `Ctrl+Shift+D` |
| **Zoom** | `Ctrl++`, `Ctrl+-`, `Ctrl+0` to fit, or `Ctrl`+wheel |

The strip on the left is one thumbnail per page; click one to go to it. Markups
outline as you pass over them, and a rectangle you draw is red, 1.5 pt.

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

**The file is read into memory** and the handle closed, so a document can always
be saved back over the file it was opened from.

**Pages are rendered without their annotations**, and every markup is then
rendered on its own and placed over the page as a separate item. That is what
makes a markup something you can pick up and drag rather than part of a picture.
A drag is clamped to the page, so a markup cannot be lost off the edge.

**Coordinates are display points** everywhere outside `document.py`: PDF user
space with the page's own `/Rotate` already applied, so a rotated page behaves
like any other. A move is written straight into the annotation's `/Rect`,
because PyMuPDF's `Annot.set_rect` re-applies the border padding on every call
and would walk the markup a point further with every drag.

---

## Tests

```bash
python -m pytest
```

Runs headless (the suite forces `QT_QPA_PLATFORM=offscreen`). It covers the
document model — exact, drift-free moves, rotated pages, page insertion and
deletion, the save round trip — and drives the real window with synthetic mouse
events: the rectangle tool, dragging a markup, clamping at the page edge, and
the page strip staying in step with the canvas.
