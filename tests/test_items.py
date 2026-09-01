"""Item geometry, measurement maths and serialisation round-trips."""
import pytest
from PySide6.QtCore import QPointF, QRectF

from calcforge.core.document import Document, PageScale
from calcforge.core.engine import Workspace
from calcforge.items.base import ITEM_REGISTRY, build_item
from calcforge.items.mathitem import MathItem
from calcforge.items.measure import CountItem, MeasureItem
from calcforge.items.media import ImageItem
from calcforge.items.shapes import PolyItem, RectItem
from calcforge.items.tableitem import TableItem
from calcforge.items.text import CalloutItem, NoteItem, StampItem, TextItem


def make_all(qapp):
    return [
        RectItem("rect", QRectF(0, 0, 100, 50)),
        RectItem("ellipse", QRectF(0, 0, 80, 40)),
        RectItem("cloud", QRectF(0, 0, 120, 60)),
        PolyItem("line", [QPointF(0, 0), QPointF(50, 20)]),
        PolyItem("arrow", [QPointF(0, 0), QPointF(60, 0)]),
        PolyItem("polygon", [QPointF(0, 0), QPointF(40, 0), QPointF(20, 30)]),
        PolyItem("ink", [QPointF(0, 0), QPointF(5, 6), QPointF(9, 2)]),
        TextItem("hello"),
        CalloutItem("note"),
        NoteItem("a comment"),
        StampItem("APPROVED"),
        ImageItem(),
        MeasureItem("length", [QPointF(0, 0), QPointF(100, 0)]),
        MeasureItem("area", [QPointF(0, 0), QPointF(100, 0), QPointF(100, 50)]),
        CountItem("Doors", 2, "star"),
        MathItem("a := 2 m\nb := a*3"),
        TableItem(3, 3),
    ]


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


def test_math_item_evaluates_and_lays_out(qapp):
    workspace = Workspace()
    item = MathItem("L := 6 m\nw := 12 kN/m\nM := w*L^2/8 -> kN*m")
    item.local_scope = False
    item.refresh(workspace)
    assert workspace.get("M").to("kN*m").magnitude == pytest.approx(54)
    assert item.local_rect().width() > 40
    assert item.defined_names() == ["L", "w", "M"]


def test_a_block_defines_for_the_document_by_default(qapp):
    workspace = Workspace()
    workspace.begin_pass()
    block = MathItem("w = 12 kN/m\nM = w*6 m^2/8")
    assert not block.local_scope and not block.scoped
    block.refresh(workspace)
    assert workspace.get("w").to("kN/m").magnitude == pytest.approx(12)


def test_a_block_can_be_made_self_contained(qapp):
    workspace = Workspace()
    workspace.begin_pass()
    MathItem("L = 6 m").refresh(workspace)          # a one-line region defines globally

    block = MathItem("w = 12 kN/m\nM = w*L^2/8")
    block.local_scope = True
    block.refresh(workspace)
    assert block.scoped
    assert workspace.get("L").to("m").magnitude == pytest.approx(6)   # read from above
    assert workspace.get("M") is None and workspace.get("w") is None
    assert block.local_values["M"].value.to("kN*m").magnitude == pytest.approx(54)


def test_block_scope_survives_a_round_trip(qapp):
    item = MathItem("a = 1 m\nb = 2 m")
    item.local_scope = True
    clone = build_item(item.serialize())
    assert clone.local_scope is True
    assert build_item(MathItem("a = 1 m").serialize()).local_scope is False


def test_math_item_marks_unit_literals(qapp):
    item = MathItem("")
    from calcforge.core.engine import compile_expression
    _code, tree = compile_expression("24 kN/m^3")
    assert item._is_unit_literal(tree)
    _code, tree = compile_expression("w*L^2/8")
    assert not item._is_unit_literal(tree)


def test_table_publishes_named_cells(qapp):
    workspace = Workspace()
    table = TableItem(3, 2)
    table.set_cell(0, 0, "10 kN")
    table.set_cell(1, 0, "15 kN")
    table.set_cell(2, 0, "=SUM(A1:A2)")
    table.named_cells = {"N_total": "A3"}
    table.refresh(workspace)
    assert workspace.get("N_total").to("kN").magnitude == pytest.approx(25)


def test_table_cell_hit_testing(qapp):
    table = TableItem(4, 3)
    table.show_chrome = True
    rect = table.cell_rect(2, 1)
    assert table.cell_at(rect.center()) == (2, 1)
    assert table.cell_at(QPointF(-40, -40)) is None


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
