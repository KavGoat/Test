"""Item geometry, measurement maths and serialisation round-trips."""
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from markforge.core.document import Document, PageScale
from markforge.items.base import ITEM_REGISTRY, build_item
from markforge.items.measure import CountItem, MeasureItem
from markforge.items.media import ImageItem
from markforge.items.shapes import PolyItem, RectItem
from markforge.items.text import CalloutItem, NoteItem, StampItem, TextItem


def test_every_item_type_is_registered(qapp):
    for item in make_all(qapp):
        assert item.TYPE in ITEM_REGISTRY


def test_serialisation_round_trip(qapp):
    for item in make_all(qapp):
        item.setPos(QPointF(12, 34))
        item.comment = "round trip"
        item.style.stroke = "#123456"
        data = item.serialize()
        clone = build_item(data)
        assert clone is not None
        assert clone.TYPE == item.TYPE
        assert clone.pos() == item.pos()
        assert clone.comment == "round trip"
        assert clone.style.stroke == "#123456"


def test_handles_present_for_resizable_items(qapp):
    rect = RectItem("rect", QRectF(0, 0, 100, 50))
    handles = rect.handle_points()
    assert {"nw", "se", "rot"} <= set(handles)
    rect.move_handle("se", QPointF(200, 120))
    assert rect.local_rect().width() == pytest.approx(200)


def test_polyline_vertex_editing(qapp):
    poly = PolyItem("polyline", [QPointF(0, 0), QPointF(50, 0), QPointF(100, 0)])
    assert set(poly.handle_points()) >= {"v0", "v1", "v2"}
    poly.move_handle("v1", QPointF(50, 40))
    assert poly.points[1].y() == pytest.approx(40)
    index = poly.insert_point(QPointF(75, 10))
    assert len(poly.points) == 4 and index in (2, 3)
    poly.delete_point(0)
    assert len(poly.points) == 3


def test_measurement_uses_the_page_scale(qapp):
    page = Document().pages[0]
    page.scale = PageScale.from_ratio(100)
    length = MeasureItem("length", [QPointF(0, 0), QPointF(200, 0)])
    length.refresh(page=page)
    assert length.value.to("m").magnitude == pytest.approx(7.0555, rel=1e-3)

    area = MeasureItem("area", [QPointF(0, 0), QPointF(200, 0), QPointF(200, 100),
                                QPointF(0, 100)])
    area.refresh(page=page)
    assert area.value.to("m**2").magnitude == pytest.approx(24.89, rel=1e-3)


def test_angle_measurement(qapp):
    angle = MeasureItem("angle", [QPointF(100, 0), QPointF(0, 0), QPointF(0, 100)])
    angle.refresh()
    assert angle.value.magnitude == pytest.approx(90)


def test_calibration_from_a_drawn_distance(qapp):
    scale = PageScale.from_calibration(200.0, "5 m")
    assert scale.length(200).to("m").magnitude == pytest.approx(5)
    assert scale.area(40000).to("m**2").magnitude == pytest.approx(25)


def test_locked_items_do_not_offer_handles(qapp):
    rect = RectItem("rect", QRectF(0, 0, 50, 50))
    rect.set_locked(True)
    assert rect.handle_at(QPointF(0, 0)) is None


def test_measurement_bounding_rect_covers_its_label(qapp):
    page = Document().pages[0]
    page.scale = PageScale.from_ratio(100)
    item = MeasureItem("length", [QPointF(0, 0), QPointF(120, 0)])
    item.label_offset = QPointF(0, -40)
    item.refresh(page=page)
    label_centre = item._label_anchor() + item.label_offset
    assert item.boundingRect().contains(label_centre)


def test_measurement_without_a_label_has_a_tight_rect(qapp):
    item = MeasureItem("length", [QPointF(0, 0), QPointF(120, 0)])
    item.show_label = False
    tight = item.boundingRect()
    item.show_label = True
    item.value_text = "12.345 m"
    assert item.boundingRect().height() > tight.height()


def test_a_highlighter_stroke_is_one_even_band(qapp):
    """Drawn back over itself, a highlighter must not darken or leave holes."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter
    from markforge.items.shapes import PolyItem

    item = PolyItem(kind="highlighter")
    item.points = [QPointF(40, 100), QPointF(160, 100), QPointF(100, 100),
                   QPointF(100, 40)]
    image = QImage(200, 200, QImage.Format_ARGB32_Premultiplied)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    item.paint(painter, None, None)
    painter.end()

    # Along the middle of the band: one shade, and no white showing through.
    shades = {image.pixelColor(x, 100).rgb() for x in range(50, 150)}
    assert len(shades) == 1
    assert shades != {0xFFFFFFFF}


def test_a_dimensions_value_carries_a_control_dot(qapp):
    """Not a corner of a box — a control point sitting on the number."""
    from PySide6.QtCore import QPointF
    from markforge.items.measure import DIMENSION, LENGTH, AREA, MeasureItem

    for kind in (DIMENSION, LENGTH):
        item = MeasureItem(kind, [QPointF(0, 0), QPointF(200, 0)])
        assert item.control_dots() == {"lbl"}
        assert "lbl" in item.handle_points()

    area = MeasureItem(AREA, [QPointF(0, 0), QPointF(100, 0), QPointF(100, 80)])
    assert area.control_dots() == set(), "an area has no dimension line to adjust"


def test_a_snapshots_colours_can_be_changed(window):
    """A recording cannot be asked anything, so it keeps what it was made of."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor

    from markforge.io import recolour
    from markforge.items.shapes import PolyItem
    from markforge.items.snapshot import SnapshotItem

    frame = window.document.pages[0].frame
    for index, colour in enumerate(("#000000", "#0a0a0a", "#c92a2a")):
        line = PolyItem("polyline", [QPointF(0, 0), QPointF(80, 0)])
        line.style.stroke = colour
        line.style.width = 2.0
        frame.add_markup(line, QPointF(100, 120 + index * 20))
    window.take_snapshot(frame, QRectF(90, 100, 200, 100))
    window.paste_items()
    snapshot = [i for i in frame.markups() if isinstance(i, SnapshotItem)][0]

    source = snapshot.source_markups()
    assert [item.style.stroke for item in source] \
        == ["#000000", "#0a0a0a", "#c92a2a"]
    assert recolour.swap_line_colour(source, QColor("#000000"),
                                     QColor("#1971c2"), 40) == 2
    picture = snapshot.redraw_from(source)
    assert not picture.isNull(), "still a recording, so still sharp at any size"
    assert [payload["style"]["stroke"] for payload in snapshot.source_items] \
        == ["#1971c2", "#1971c2", "#c92a2a"]


def test_a_snapshot_and_a_photo_have_a_line_type_of_their_own(window):
    """Neither is drawn with the toolbar's pen, so each remembers its own."""
    from markforge.ui import toolsets
    from markforge.items.media import ImageItem
    from markforge.items.snapshot import SnapshotItem

    for key, kind in (("snapshot", SnapshotItem), ("image", ImageItem)):
        window.select_tool(key)
        window.refresh_selection()
        shown = {field for field, actions in window._style_widgets.items()
                 if any(action.isVisible() for action in actions)}
        assert "dash" in shown, f"{key} should offer a line type"
        assert "stroke" in shown and "width" in shown

    window.select_tool("snapshot")
    window.refresh_selection()
    window._style_stroke("#c92a2a")
    window._style_width(2.5)
    window._style_dash("dash")
    made = SnapshotItem()
    toolsets.apply_default(made)
    assert made.style.stroke == "#c92a2a"
    assert made.style.width == 2.5
    assert made.style.line_style == "dash"
    assert window.default_style.line_style == "solid", \
        "and the pen every other markup is drawn with is left alone"
