# PDF4Py

A Python PDF markup editor inspired by PDF4QT and MarkForge. Open a drawing,
mark it up, save it back — as a PDF that anybody can open, with every markup a
real PDF annotation.

## Install and run

```bash
pip install -e ".[dev]"
python -m pdf4py.app        # or: pdf4py drawing.pdf
```

Python 3.10+. Dependencies: PySide6, pymupdf.

## Features

### Markup tools

| Tool         | Key | Description                                    |
|-------------|-----|------------------------------------------------|
| Select       | V   | Move, resize, edit markups                     |
| Rectangle    | R   | Draw a rectangle                               |
| Line         | L   | Draw a line                                    |
| Arrow        | A   | Draw an arrow                                  |
| Ellipse      | E   | Draw an ellipse                                |
| Polygon      | P   | Click points, double-click to finish           |
| Cloud        | C   | Draw a revision cloud (cloudy border)          |
| Ink / Pen    | I   | Freehand drawing                               |
| Highlight    | H   | Highlight an area                              |
| Text Box     | T   | Place a text box                               |
| Note         | N   | Place a sticky note                            |

### Editing

- **Select and move** any markup by dragging
- **Resize** via eight corner/edge handles
- **Callout leader** reshape via orange diamond handles
- **In-place text editing** — double-click a text box or note to edit
- **Groups** — Ctrl+G to group, Ctrl+Shift+G to ungroup
- **Order** — bring to front (Ctrl+Shift+]) and send to back (Ctrl+Shift+[)
- **Undo/Redo** — Ctrl+Z / Ctrl+Shift+Z, unlimited depth (200 steps)
- **Delete** selected markups with the Delete key

### Properties panel

Select a markup to see and edit:
- Stroke colour (click to pick)
- Fill colour (click to pick)
- Border width (0.1–20 pt)
- Opacity (0–100% slider)
- Type and author info

### Pages

- **Continuous scroll** — all pages stacked vertically, scroll through the whole document
- **Insert** blank pages (Ctrl+Shift+A)
- **Delete** pages (Ctrl+Shift+D)
- **Rotate** pages clockwise (Ctrl+Shift+R) or counter-clockwise (Ctrl+Shift+L)
- **Thumbnail panel** with lazy rendering

### Bookmarks

- PDF outline navigation in the Bookmarks panel
- Add and remove bookmarks
- Double-click to jump to the bookmarked page

### Markups list

- Sortable, filterable table of every annotation
- Filter by type or search text
- Click a row to jump to that markup on the page

### Zooming

- Ctrl+scroll to zoom at the pointer
- Two-phase smooth zoom: instant scale preview, then proper redraw
- Fit page (Ctrl+0), zoom in (+), zoom out (-)

### View panels

View > Panels lets you show/hide:
- Pages (thumbnails)
- Properties (markup editing)
- Bookmarks (PDF outline)
- Markups (annotation list)

### File handling

- Opens any PDF, including damaged files (auto-repair)
- Incremental save — changes are appended, not rewritten
- Save As for a clean copy
- Handles 200+ page documents efficiently

## Architecture

```
pdf4py/
  document.py    — PDF model (PyMuPDF), no Qt dependency
  geometry.py    — Transforms all annotation geometry keys together
  history.py     — Undo/redo stack
  app.py         — QApplication builder
  ui/
    mainwindow.py  — Menus, toolbars, dock panels
    pageview.py    — Continuous-scroll canvas with markup overlays
    pagelist.py    — Lazy thumbnail strip
    textedit.py    — In-place text editor
    properties.py  — Property panel (colour, border, opacity)
    bookmarks.py   — Bookmarks panel
    markuplist.py  — Sortable annotation list
    icons.py       — Painted toolbar icons
    images.py      — Raster-to-QImage conversion
```

## Keyboard shortcuts

| Shortcut        | Action                              |
|----------------|-------------------------------------|
| Ctrl+O          | Open                                |
| Ctrl+S          | Save                                |
| Ctrl+Z          | Undo                                |
| Ctrl+Shift+Z    | Redo                                |
| Delete          | Delete selected markups             |
| Ctrl+G          | Group                               |
| Ctrl+Shift+G    | Ungroup                             |
| Ctrl+Shift+]    | Bring to front                      |
| Ctrl+Shift+[    | Send to back                        |
| Ctrl+Shift+A    | Insert page                         |
| Ctrl+Shift+D    | Delete page                         |
| Ctrl+Shift+R    | Rotate page clockwise               |
| Ctrl+Shift+L    | Rotate page counter-clockwise       |
| Ctrl+0          | Fit page                            |
| Ctrl++          | Zoom in                             |
| Ctrl+-          | Zoom out                            |
| F2              | Edit text of selected markup        |
| V               | Select tool                         |
| R               | Rectangle tool                      |
| L               | Line tool                           |
| A               | Arrow tool                          |
| E               | Ellipse tool                        |
| P               | Polygon tool                        |
| C               | Cloud tool                          |
| I               | Ink/Pen tool                        |
| H               | Highlight tool                      |
| T               | Text box tool                       |
| N               | Note tool                           |
| Escape          | Cancel polygon/ink drawing          |

## Testing

```bash
pytest tests/ -v
```
