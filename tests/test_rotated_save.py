"""A turned page keeps its markups where they were through a save and a
reopen (50 PDFs made and reopened, 2026-10-14): Rotate Page turned each
markup about its corner, a reopened one turns about its centre, and every
markup on a turned page came back off to one side."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from calcforge.items.shapes import PolyItem, RectItem
from tests.test_calc_saving import reopen, save_to
from tests.test_tables import pump


def printed(frame) -> QImage:
    rect = frame.page_rect()
    image = QImage(int(rect.width()), int(rect.height()), QImage.Format_RGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    frame.render_page(painter, QRectF(image.rect()), for_print=True)
    painter.end()
    return image


def red_box(image: QImage):
    """Where the red ink is on the page."""
    xs, ys = [], []
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            colour = image.pixelColor(x, y)
            if colour.red() > 200 and colour.green() < 80 and colour.blue() < 80:
                xs.append(x)
                ys.append(y)
    assert xs, "no red on the page"
    return min(xs), min(ys), max(xs), max(ys)


def a_red_box(frame, at=QPointF(100, 200)) -> RectItem:
    box = RectItem("rect", QRectF(0, 0, 100, 50))
    box.style.fill = "#ff0000"
    box.style.stroke = "#ff0000"
    frame.add_markup(box, at)
    return box


@pytest.mark.parametrize("turns", [1, -1, 2])
def test_a_turned_pages_markups_reopen_where_they_were(window, tmp_path, turns):
    window.show()
    window.add_page()
    page = window.document.pages[1]
    a_red_box(page.frame)
    for _ in range(abs(turns)):
        window.rotate_page(1, clockwise=turns > 0)
    pump()
    before = red_box(printed(page.frame))
    path = str(tmp_path / "turned.pdf")
    save_to(window, path)
    reopen(window, path)
    pump()
    assert red_box(printed(window.document.pages[1].frame)) == pytest.approx(before, abs=3)


def test_a_markup_already_turned_turns_with_its_page(window, tmp_path):
    """Turned by its handle first (about its centre), then the page turned:
    it lands where the page's turn takes it, and stays there."""
    window.show()
    frame = window.document.pages[0].frame
    box = a_red_box(frame)
    box.set_item_rotation(30)
    centre = box.mapToParent(box.local_rect().center())
    height = window.document.pages[0].height_pt
    window.rotate_page(0, clockwise=True)
    pump()
    box = next(i for i in window.document.pages[0].frame.markups() if isinstance(i, RectItem))
    moved = box.mapToParent(box.local_rect().center())
    assert (moved.x(), moved.y()) == pytest.approx((height - centre.y(), centre.x()), abs=0.5)
    assert box.rotation() == pytest.approx(120)
    before = red_box(printed(window.document.pages[0].frame))
    path = str(tmp_path / "turned.pdf")
    save_to(window, path)
    reopen(window, path)
    pump()
    assert red_box(printed(window.document.pages[0].frame)) == pytest.approx(before, abs=3)


def test_a_turned_rectangle_converts_to_a_polygon_in_place(window):
    frame = window.document.pages[0].frame
    box = a_red_box(frame)
    box.set_item_rotation(30)
    corners = [box.mapToParent(p) for p in (box.local_rect().topLeft(), box.local_rect().bottomRight())]
    shape = PolyItem.from_rectangle(box)
    frame.add_markup(shape)
    pairs = zip(corners, [shape.mapToParent(p) for p in (shape.points[0], shape.points[2])])
    for was, now in pairs:
        assert (now.x(), now.y()) == pytest.approx((was.x(), was.y()), abs=0.5)


def ink(image: QImage):
    """Where anything at all is drawn on the page."""
    xs, ys = [], []
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            colour = image.pixelColor(x, y)
            if min(colour.red(), colour.green(), colour.blue()) < 160:
                xs.append(x)
                ys.append(y)
    assert xs, "nothing on the page"
    return min(xs), min(ys), max(xs), max(ys)


def test_a_table_on_a_turned_page_reopens_where_it_was(window, tmp_path):
    from tests.test_tables import make_table
    window.show()
    table = make_table(window, x=200, y=300)
    window.view.tables.close()
    window.document.show_name_tags = False
    window.rotate_page(0, clockwise=True)
    pump()
    before = ink(printed(window.document.pages[0].frame))
    path = str(tmp_path / "table.pdf")
    save_to(window, path)
    reopen(window, path)
    pump()
    window.document.show_name_tags = False
    after = ink(printed(window.document.pages[0].frame))
    assert after == pytest.approx(before, abs=3)
    del table


def test_equations_on_a_turned_page_reopen_where_they_were(window, tmp_path):
    from tests.test_calc_saving import write_lines
    window.show()
    write_lines(window, ["a:5'm", "b:a*4", "b="], x=100, y=150)
    window.toggle_calc_mode(False)
    window.rotate_page(0, clockwise=True)
    pump()
    before = ink(printed(window.document.pages[0].frame))
    path = str(tmp_path / "sums.pdf")
    save_to(window, path)
    reopen(window, path)
    pump()
    after = ink(printed(window.document.pages[0].frame))
    assert after == pytest.approx(before, abs=3)
