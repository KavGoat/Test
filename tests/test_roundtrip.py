"""The round trip (2026-09-30): save as PDF, open it in another editor, change
it there, open it here again.

Two promises, both checked through the real window:

- **The page looks the same everywhere.** However a document looks in
  CalcForge is how it looks in any other PDF reader: every kind of markup,
  photos, snapshots, equations, plots and Calculation text, drawn by
  CalcForge, by MuPDF and by pdfium (Chrome's and Foxit's engine) and
  compared a region at a time.
- **For markups, the file wins.** A markup moved, restyled, retyped or
  deleted in another editor opens here as that editor left it. Equations
  can't be touched elsewhere — they are page content — and pages deleted or
  reordered elsewhere take their equations with them.
"""
from __future__ import annotations

import os

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

from calcforge.core.document import PageScale
from calcforge.items.calc import CalcItem, CalcTextItem
from calcforge.items.measure import CountItem, MeasureItem
from calcforge.items.media import ImageItem
from calcforge.items.shapes import PolyItem, RectItem, SketchItem
from calcforge.items.snapshot import SnapshotItem
from calcforge.items.text import (CalloutItem, FlagItem, NoteItem, StampItem, TextItem,
                                  TypewriterItem)
from tests import fidelity
from tests.test_calc_modes import typed
from tests.test_calc_saving import answer, reopen, save_to, src, write_lines
from tests.test_usability import press_key

CELL_W, CELL_H = 170.0, 105.0
LEFT, TOP = 40.0, 60.0


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    return window


def cell(index: int) -> QRectF:
    column, row = index % 3, index // 3
    return QRectF(LEFT + column * CELL_W, TOP + row * CELL_H, CELL_W - 10, CELL_H - 10)


def a_photo(window) -> str:
    image = QImage(240, 160, QImage.Format_RGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 240, 160)
    gradient.setColorAt(0, QColor("#1c7ed6"))
    gradient.setColorAt(1, QColor("#f59f00"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(image.rect(), Qt.AlignCenter, "SITE PHOTO")
    painter.end()
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return window.document.add_asset(bytes(data), "png")


def every_kind(window) -> dict:
    """One of everything a page can hold, each in a cell of its own.
    Returns {name: cell rectangle}."""
    frame = window.document.pages[0].frame
    window.document.pages[0].scale = PageScale.from_ratio(50)
    made: dict = {}

    def put(name, item, index, at=(10, 12)):
        box = cell(index)
        frame.add_markup(item, QPointF(box.left() + at[0], box.top() + at[1]))
        made[name] = box

    put("rectangle", RectItem("rect", QRectF(0, 0, 120, 60)), 0)
    shape = RectItem("ellipse", QRectF(0, 0, 120, 60))
    shape.style.fill = "#ffe066"
    put("ellipse, filled", shape, 1)
    cloud = RectItem("cloud", QRectF(0, 0, 120, 60))
    cloud.style.stroke = "#c92a2a"
    put("cloud", cloud, 2)
    put("arrow", PolyItem("arrow", [QPointF(0, 60), QPointF(120, 0)]), 3)
    put("polygon", PolyItem("polygon", [QPointF(0, 60), QPointF(60, 0), QPointF(120, 60)]), 4)
    put("pen", PolyItem("ink", [QPointF(0, 30), QPointF(30, 0), QPointF(60, 50),
                                QPointF(90, 10), QPointF(120, 40)]), 5)
    text = TextItem("Check the beam depth")
    text.set_local_rect(QRectF(0, 0, 130, 40))
    put("text box", text, 6)
    callout = CalloutItem("See detail 4")
    put("callout", callout, 7, at=(60, 12))
    put("stamp", StampItem("APPROVED"), 8)
    put("measurement, length", MeasureItem("length", [QPointF(0, 30), QPointF(130, 30)]), 9)
    put("measurement, area", MeasureItem("area", [QPointF(0, 0), QPointF(120, 0),
                                                 QPointF(120, 60), QPointF(0, 60)]), 10)
    put("dimension", MeasureItem("dimension", [QPointF(0, 40), QPointF(130, 40)]), 11)
    count = CountItem("Doors", 1, "circle")
    put("count", count, 12, at=(40, 40))
    put("typewriter", TypewriterItem("typed words"), 13)
    photo = ImageItem(a_photo(window), QRectF(0, 0, 120, 80))
    photo.load_from_document(window.document)
    put("photo", photo, 14)
    put("note", NoteItem("a comment"), 15, at=(60, 30))
    put("flag", FlagItem(), 16, at=(60, 30))
    for item in frame.markups():
        if hasattr(item, "refresh"):
            try:
                item.refresh(page=window.document.pages[0])
            except TypeError:
                pass
    sketch = SketchItem([{"path": [["m", 0, 0], ["l", 60, 50], ["c", 80, 0, 100, 0, 120, 40]],
                          "stroke": "#2b8a3e", "width": 2.0}])
    put("sketch", sketch, 18)
    # the equations, a plot and Calculation text, made as a user makes them
    box = cell(17)
    write_lines(window, ["b1:300'mm", "d1:2*b1", "d1="], x=box.left() + 4, y=box.top() + 8)
    made["equations"] = box
    box = cell(19)
    window.view.calc.start_calc_text(frame, QPointF(box.left() + 4, box.top() + 8))
    typed(window, "Design to AS 3600")
    press_key(window.view, Qt.Key_Escape)
    made["calculation text"] = box
    return made


def the_second_page(window) -> dict:
    """A second page: a plot, and a snapshot of the first page's top row."""
    window.document.add_page()
    window.rebuild_scenes()
    first, second = (page.frame for page in window.document.pages[:2])
    made: dict = {}
    window.toggle_calc_mode(True)
    plot = window.view.calc.start_plot(second, QPointF(LEFT + 4, TOP + 4))
    typed(window, "sin(x)")
    press_key(window.view, Qt.Key_Escape)
    made["plot"] = plot.sceneBoundingRect().translated(-second.scenePos())
    window.take_snapshot(first, cell(0).united(cell(2)))
    window.go_to_page(1)
    window.paste_in_place()
    shots = [i for i in second.markups() if isinstance(i, SnapshotItem)] or \
        [i for i in first.markups() if isinstance(i, SnapshotItem)]
    (shot,) = shots
    if shot.parentItem() is not second:
        second.add_markup(shot)
    shot.setPos(QPointF(LEFT, 400))
    made["snapshot"] = shot.sceneBoundingRect().translated(-second.scenePos())
    return made


def compare_everywhere(window, path, regions: dict, page=0) -> dict:
    """{region: (vs MuPDF, vs pdfium)} for one page."""
    frame = window.document.pages[page].frame
    here = fidelity.calcforge(frame)
    theirs = fidelity.mupdf(path, page), fidelity.pdfium(path, page)
    return {name: tuple(fidelity.compare(here, other, box) for other in theirs)
            for name, box in regions.items()}


def assert_alike(results: dict, overlap=0.9, shift=1.5, colour=45.0) -> None:
    """Every region drawn alike by CalcForge and both readers.

    Anti-aliasing alone differs by up to about 30 on thin lines (measured over
    every kind of markup); a wrong colour — units black instead of blue, a
    fill gone grey — differs by 100 to 200.
    """
    wrong = []
    for name, pair in results.items():
        if pair[0]["ink"][0] < 50:
            wrong.append(f"{name}: CalcForge drew nothing there to compare")
        for reader, got in zip(("MuPDF", "pdfium"), pair):
            if got["overlap"] < overlap or got["shift"] > shift or got["colour"] > colour:
                wrong.append(f"{name} in {reader}: {got}")
    assert not wrong, "drawn differently elsewhere:\n" + "\n".join(wrong)


# -- the page looks the same everywhere -----------------------------------------------

def test_every_kind_of_markup_looks_the_same_in_other_readers(win, tmp_path):
    regions = every_kind(win)
    more = the_second_page(win)
    path = str(tmp_path / "everything.pdf")
    save_to(win, path)
    assert_alike(compare_everywhere(win, path, regions))
    assert_alike(compare_everywhere(win, path, more, page=1))


def test_and_still_the_same_after_opening_and_saving_again(win, tmp_path):
    regions = every_kind(win)
    more = the_second_page(win)
    path = str(tmp_path / "everything.pdf")
    save_to(win, path)
    reopen(win, path)
    save_to(win, path)
    assert_alike(compare_everywhere(win, path, regions))
    assert_alike(compare_everywhere(win, path, more, page=1))


# -- changed in another editor, opened here again ---------------------------------------

def elsewhere(path, change) -> None:
    """Open *path* in another editor (MuPDF's), let *change* edit it, save."""
    with pymupdf.open(path) as document:
        change(document)
        document.save(path + ".x", garbage=1, deflate=True)
        _HELD.clear()
    os.replace(path + ".x", path)


_HELD: list = []


def annotation_of(document, item, page=0):
    """The annotation a markup was saved as. (Its page is kept alive: MuPDF
    crashes on an annotation whose page has been let go.)"""
    sheet = document[page]
    _HELD.append(sheet)
    (found,) = [a for a in sheet.annots()
                if document.xref_get_key(a.xref, "NM")[1] == item.uid]
    return found


def markups_on(window, page=0):
    return [i for i in window.document.pages[page].frame.markups()
            if not isinstance(i, (CalcItem, CalcTextItem))]


def a_marked_up_calc(window):
    """Two pages: markups and equations on both, variables across them."""
    frame = window.document.pages[0].frame
    window.document.pages[0].scale = PageScale.from_ratio(50)
    box = RectItem("rect", QRectF(0, 0, 120, 60))
    frame.add_markup(box, QPointF(60, 300))
    words = TextItem("Check the beam depth")
    words.set_local_rect(QRectF(0, 0, 150, 40))
    frame.add_markup(words, QPointF(260, 300))
    area = MeasureItem("area", [QPointF(0, 0), QPointF(120, 0), QPointF(120, 60), QPointF(0, 60)])
    frame.add_markup(area, QPointF(60, 420))
    area.refresh(page=window.document.pages[0])
    write_lines(window, ["span:6'm", "load:12'kN/'m"], x=60, y=120)
    window.document.add_page()
    window.rebuild_scenes()
    cloud = RectItem("cloud", QRectF(0, 0, 120, 60))
    window.document.pages[1].frame.add_markup(cloud, QPointF(60, 300))
    write_lines(window, ["Mu:load*span*span/8", "Mu="], x=60, y=120, page=1)
    assert answer(window, "Mu=") == "54 kN m"
    return box, words, area, cloud


def test_a_markup_moved_elsewhere_opens_where_it_was_moved(win, tmp_path):
    box, words, area, cloud = a_marked_up_calc(win)
    path = str(tmp_path / "moved.pdf")
    save_to(win, path)

    def move(document):
        annotation = annotation_of(document, box)
        rect = annotation.rect
        annotation.set_rect(rect + (200, 150, 200, 150))
        annotation.update()
    elsewhere(path, move)
    reopen(win, path)
    boxes = [i for i in markups_on(win) if i.uid == box.uid]
    assert len(boxes) == 1, "still one markup, the same one"
    assert boxes[0].sceneBoundingRect().translated(
        -win.document.pages[0].frame.scenePos()).left() > 230, "where the other editor put it"
    assert len(markups_on(win)) == 3, "and nothing else came or went"
    # the untouched ones are still CalcForge's own, with everything they know
    (kept,) = [i for i in markups_on(win) if i.uid == area.uid]
    assert isinstance(kept, MeasureItem) and not kept.still_theirs
    # the page looks the same here as in the other readers
    regions = {"page": QRectF(0, 0, 595, 842)}
    assert_alike(compare_everywhere(win, path, regions))
    # and saved again, it stays where it was moved
    save_to(win, path)
    reopen(win, path)
    (again,) = [i for i in markups_on(win) if i.uid == box.uid]
    assert again.sceneBoundingRect().translated(
        -win.document.pages[0].frame.scenePos()).left() > 230


def test_a_markup_restyled_or_retyped_elsewhere_opens_as_they_left_it(win, tmp_path):
    box, words, area, cloud = a_marked_up_calc(win)
    path = str(tmp_path / "restyled.pdf")
    save_to(win, path)

    def change(document):
        annotation = annotation_of(document, box)
        annotation.set_colors(stroke=(0, 0.6, 0))
        annotation.update()
        text = annotation_of(document, words)
        text.set_info(content="Beam depth is fine")
        text.update()
    elsewhere(path, change)
    reopen(win, path)
    here = fidelity.calcforge(win.document.pages[0].frame)
    theirs = fidelity.mupdf(path, 0)
    (green,) = [i for i in markups_on(win) if i.uid == box.uid]
    where = green.sceneBoundingRect().translated(-win.document.pages[0].frame.scenePos())
    shown = fidelity.compare(here, theirs, where)
    assert shown["overlap"] > 0.9 and shown["colour"] < 45
    s = fidelity.SCALE
    ink = here[int(where.top() * s):int(where.bottom() * s),
               int(where.left() * s):int(where.right() * s)]
    dark = ink[ink.mean(axis=2) < 200]
    assert dark[:, 1].mean() > dark[:, 0].mean() + 40, "the rectangle is green now, as they made it"
    (said,) = [i for i in markups_on(win) if i.uid == words.uid]
    assert "Beam depth is fine" in (said.comment or "") + said.text()


def test_a_markup_deleted_elsewhere_is_gone(win, tmp_path):
    box, words, area, cloud = a_marked_up_calc(win)
    path = str(tmp_path / "deleted.pdf")
    save_to(win, path)
    def delete(document):
        annotation = annotation_of(document, words)
        _HELD[-1].delete_annot(annotation)
    elsewhere(path, delete)
    reopen(win, path)
    assert words.uid not in [i.uid for i in markups_on(win)]
    assert {i.uid for i in markups_on(win)} == {box.uid, area.uid}


def test_a_page_deleted_elsewhere_takes_its_markups_and_equations(win, tmp_path):
    box, words, area, cloud = a_marked_up_calc(win)
    path = str(tmp_path / "pages.pdf")
    save_to(win, path)
    elsewhere(path, lambda document: document.delete_page(0))
    reopen(win, path)
    assert len(win.document.pages) == 1
    assert [i.uid for i in markups_on(win)] == [cloud.uid]
    (said,) = [w for w in win.document.open_warnings if "deleted" in w]
    assert "load" in said and "span" in said
    assert "no longer defined" in win.status_hint.text()
    # nothing is corrupt: the file saves and opens again cleanly
    save_to(win, path)
    reopen(win, path)
    assert win.document.open_warnings == []
    assert [src(i) for i in win.document.pages[0].frame.markups()
            if isinstance(i, CalcItem)] == ["Mu:load*span*(span)/(8)", "Mu="]


def test_pages_reordered_elsewhere_keep_their_markups(win, tmp_path):
    box, words, area, cloud = a_marked_up_calc(win)
    path = str(tmp_path / "order.pdf")
    save_to(win, path)
    elsewhere(path, lambda document: document.move_page(1, 0))
    reopen(win, path)
    assert [i.uid for i in markups_on(win, 0)] == [cloud.uid]
    assert {i.uid for i in markups_on(win, 1)} == {box.uid, words.uid, area.uid}
    assert answer(win, "Mu=") != "54 kN m", "Mu now comes before span and load"


def test_a_file_rewritten_whole_by_another_program_still_opens_live(win, tmp_path):
    """pypdf writes every object out afresh, as some editors do on save."""
    from pypdf import PdfReader, PdfWriter

    box, words, area, cloud = a_marked_up_calc(win)
    path = str(tmp_path / "rewritten.pdf")
    save_to(win, path)
    writer = PdfWriter(clone_from=PdfReader(path))
    with open(path + ".x", "wb") as out:
        writer.write(out)
    os.replace(path + ".x", path)
    reopen(win, path)
    assert win.document.open_warnings == []
    assert answer(win, "Mu=") == "54 kN m"
    assert {i.uid for i in markups_on(win, 0)} == {box.uid, words.uid, area.uid}
    assert all(not i.still_theirs for i in markups_on(win, 0))


# -- styles, sheets and other people's drawings -----------------------------------------

def test_styles_look_the_same_in_other_readers(win, tmp_path):
    """Dashes, hatches, cut-outs, transparency, arrowheads and formatted words."""
    frame = win.document.pages[0].frame
    made = {}

    def put(name, item, index):
        box = cell(index)
        frame.add_markup(item, QPointF(box.left() + 10, box.top() + 12))
        made[name] = box

    dashed = RectItem("rect", QRectF(0, 0, 120, 60))
    dashed.style.line_style = "dash"
    dashed.style.width = 2.0
    put("dashed", dashed, 0)
    hatched = RectItem("rect", QRectF(0, 0, 120, 60))
    hatched.style.fill = "#d0ebff"
    hatched.style.hatch = "diagonal cross"
    hatched.style.hatch_color = "#1864ab"
    put("hatched", hatched, 1)
    holed = RectItem("rect", QRectF(0, 0, 120, 60))
    holed.style.fill = "#ffc9c9"
    holed.style.fill_opacity = 1.0
    holed.cutouts = [[QPointF(40, 15), QPointF(80, 15), QPointF(80, 45), QPointF(40, 45)]]
    put("cut-out", holed, 2)
    faint = RectItem("ellipse", QRectF(0, 0, 120, 60))
    faint.style.fill = "#2f9e44"
    faint.style.opacity = 0.5
    put("half transparent", faint, 3)
    arrows = PolyItem("line", [QPointF(0, 30), QPointF(120, 30)])
    arrows.style.arrow_start, arrows.style.arrow_end = "open", "closed"
    arrows.style.width = 2.0
    put("arrowheads", arrows, 4)
    rich = TextItem("")
    rich.set_local_rect(QRectF(0, 0, 140, 50))
    rich.set_html("<p><b>Bold</b> <i>italic</i> <span style='color:#c92a2a'>red</span></p>")
    put("formatted words", rich, 5)
    highlight = RectItem("rect", QRectF(0, 0, 120, 30))
    highlight.style.stroke, highlight.style.fill = "", "#ffd43b"
    highlight.style.fill_opacity = 1.0
    highlight.style.blend = "multiply"
    put("highlight", highlight, 6)
    path = str(tmp_path / "styles.pdf")
    save_to(win, path)
    assert_alike(compare_everywhere(win, path, made))


def test_header_footer_and_a_flattened_markup_look_the_same(win, tmp_path):
    settings = win.document.settings
    settings.show_header = settings.show_footer = True
    settings.header_center = "PROJECT 2417 — BEAM CHECKS"
    win.document.title = "Calcs"
    box = RectItem("rect", QRectF(0, 0, 120, 60))
    win.document.pages[0].frame.add_markup(box, QPointF(60, 300))
    box.setSelected(True)
    win.flatten_selection()
    write_lines(win, ["h1:450'mm", "h1="], x=60, y=420)
    win.rebuild_scenes()
    path = str(tmp_path / "sheet.pdf")
    save_to(win, path)
    regions = {"header": QRectF(0, 0, 595, 50), "footer": QRectF(0, 790, 595, 52),
               "flattened": QRectF(50, 290, 140, 80), "equations": QRectF(50, 410, 200, 60)}
    assert_alike(compare_everywhere(win, path, regions))
    reopen(win, path)
    save_to(win, path)
    assert_alike(compare_everywhere(win, path, regions)), "and after a round trip, not twice"


def test_a_turned_drawing_with_equations_looks_the_same(win, tmp_path):
    from tests.test_format import _a_turned_pdf

    source = str(tmp_path / "turned.pdf")
    _a_turned_pdf(source, 90)
    reopen(win, source)
    box = RectItem("cloud", QRectF(0, 0, 120, 60))
    win.document.pages[0].frame.add_markup(box, QPointF(150, 100))
    write_lines(win, ["t1:3*4", "t1="], x=300, y=220)
    path = str(tmp_path / "turned-out.pdf")
    save_to(win, path)
    page = win.document.pages[0]
    whole = {"sheet": QRectF(0, 0, page.width_pt, page.height_pt)}
    assert_alike(compare_everywhere(win, path, whole))
    reopen(win, path)
    assert answer(win, "t1=") == "12"
    assert_alike(compare_everywhere(win, path, whole))


def test_somebody_elses_marked_up_drawing_with_our_equations(win, tmp_path):
    """A real Bluebeam sheet: their markups, ours, and equations, everywhere
    alike; then one of theirs moved in another editor."""
    import shutil
    from tests.test_format import REFERENCE

    source = str(tmp_path / "theirs.pdf")
    shutil.copy(REFERENCE, source)
    reopen(win, source)
    page = win.document.pages[0]
    ours = RectItem("rect", QRectF(0, 0, 90, 40))
    page.frame.add_markup(ours, QPointF(300, 600))
    write_lines(win, ["q2:2.5'kPa", "q2="], x=300, y=680)
    path = str(tmp_path / "checked.pdf")
    save_to(win, path)
    whole = {"sheet": QRectF(0, 0, page.width_pt, page.height_pt)}
    assert_alike(compare_everywhere(win, path, whole))
    theirs_before = len([i for i in markups_on(win) if i.still_theirs])
    reopen(win, path)
    assert len([i for i in markups_on(win) if i.still_theirs]) == theirs_before
    assert_alike(compare_everywhere(win, path, whole))

    def move_one_of_theirs(document):
        sheet = document[0]
        _HELD.append(sheet)
        annotation = next(a for a in sheet.annots() if a.type[1] in ("Square", "Circle"))
        annotation.set_rect(annotation.rect + (0, 40, 0, 40))
        annotation.update()
    elsewhere(path, move_one_of_theirs)
    reopen(win, path)
    assert len([i for i in markups_on(win) if i.still_theirs]) == theirs_before
    assert_alike(compare_everywhere(win, path, whole))


def test_the_comparison_catches_a_wrong_colour_or_place(win, tmp_path):
    """The check above is only worth something if it fails when it should:
    a markup drawn the wrong colour, or in the wrong place, elsewhere."""
    box, words, area, cloud = a_marked_up_calc(win)
    path = str(tmp_path / "planted.pdf")
    save_to(win, path)
    frame = win.document.pages[0].frame
    here_box = box.sceneBoundingRect().translated(-frame.scenePos())
    here_area = area.sceneBoundingRect().translated(-frame.scenePos())

    def plant(document):
        wrong = annotation_of(document, box)
        wrong.set_colors(stroke=(0, 0, 0))
        wrong.update()
        moved = annotation_of(document, words)
        moved.set_rect(moved.rect + (0, 30, 0, 30))
        moved.update()
    elsewhere(path, plant)
    results = compare_everywhere(win, path, {"recoloured": here_box,
                                             "moved": words.sceneBoundingRect().translated(
                                                 -frame.scenePos()),
                                             "untouched": here_area})
    with pytest.raises(AssertionError):
        assert_alike({"recoloured": results["recoloured"]})
    with pytest.raises(AssertionError):
        assert_alike({"moved": results["moved"]})
    assert_alike({"untouched": results["untouched"]})


def test_an_exported_pdf_looks_the_same_as_calcforge(win, tmp_path):
    """Export PDF (not Save) goes through its own path: the same promise."""
    from calcforge.io import export as export_io

    regions = every_kind(win)
    more = the_second_page(win)
    path = str(tmp_path / "export.pdf")
    export_io.export_pdf(win.document, path, resolution=300)
    assert_alike(compare_everywhere(win, path, regions))
    assert_alike(compare_everywhere(win, path, more, page=1))


def test_a_callout_and_a_measurement_moved_elsewhere(win, tmp_path):
    box, words, area, cloud = a_marked_up_calc(win)
    frame = win.document.pages[0].frame
    callout = CalloutItem("See detail 4")
    frame.add_markup(callout, QPointF(420, 520))
    path = str(tmp_path / "complex.pdf")
    save_to(win, path)

    def move(document):
        for item in (callout, area):
            annotation = annotation_of(document, item)
            # a move as another editor writes it: every point shifted (25
            # right, 60 down — PDF's y runs up), the appearance with it
            # (MuPDF regenerates it)
            for key in ("Vertices", "CL"):
                kind, value = document.xref_get_key(annotation.xref, key)
                if kind == "array":
                    numbers = [float(v) for v in value.strip("[] ").split()]
                    shifted = [v - 60 if n % 2 else v + 25 for n, v in enumerate(numbers)]
                    document.xref_set_key(annotation.xref, key,
                                          "[" + " ".join("%g" % v for v in shifted) + "]")
            annotation.set_rect(annotation.rect + (25, 60, 25, 60))
            annotation.update()
    elsewhere(path, move)
    reopen(win, path)
    uids = [i.uid for i in markups_on(win)]
    assert uids.count(callout.uid) == 1 and uids.count(area.uid) == 1, "each still one markup"
    assert len(markups_on(win)) == 4
    page = win.document.pages[0]
    assert_alike(compare_everywhere(win, path, {"sheet": QRectF(0, 0, page.width_pt,
                                                                page.height_pt)}))
