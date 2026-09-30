"""SMath Studio 0.99 files with a page model: custom margins, a background
frame, a header layer (title-block picture and fields), pictures, rich text
(<content><p style><span style><br/>), fixed-width text, and definitions
that also show their value.  Built like a real company calculation sheet."""
from __future__ import annotations

import base64
import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from markforge.calc.engine.display import display_text  # noqa: E402
from tests.calc.smfile import dumps, loads  # noqa: E402
from markforge.calc.page import field_text  # noqa: E402


def _png(w=8, h=6, color="#0000ff") -> str:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor(color))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode()


def _sheet() -> str:
    pic = _png()
    return f'''<?xml version="1.0" encoding="utf-8"?>
<worksheet xmlns="http://smath.info/schemas/worksheet/1.0">
  <settings ppi="96">
    <metadata lang="eng"><title>Issue 1</title><author>ME</author><keywords>JOB-7</keywords></metadata>
    <calculation><precision>4</precision><exponentialThreshold>5</exponentialThreshold></calculation>
    <pageModel active="false" viewMode="2" printGrid="false" printAreas="true" printBackgroundImages="true">
      <paper id="9" orientation="Portrait" width="827" height="1169" />
      <margins left="39" right="39" top="117" bottom="49" />
      <header alignment="Center" color="#a9a9a9">&amp;[DATE]</header>
      <footer alignment="Center" color="#a9a9a9">&amp;[PAGENUM]</footer>
      <backgrounds><image fullPage="false" size="stretch">{_png(20, 30, "#00000000")}</image></backgrounds>
    </pageModel>
  </settings>
  <regions type="content">
    <region left="18" top="18" width="29" height="20" color="#000000" fontSize="8">
      <text lang="eng" fontFamily="Arial" fontSize="8"><content>
          <p>
            <span style="font-weight: bold;">Design</span>
            <br />
            <br />
            <span style="text-decoration: underline;">Brace Check</span>
            <br />Plain line.</p>
      </content></text>
    </region>
    <region left="72" top="45" width="749" height="90" color="#000000">
      <picture><raw format="png" encoding="base64">{pic}</raw></picture>
    </region>
    <region left="369" top="200" width="120" height="32" color="#000000" fontSize="8">
      <text lang="eng" width="120" fontFamily="Arial" fontSize="8"><content>
        <p>The capacity is 6.67 kN. This is larger than the demand.</p></content></text>
    </region>
    <region left="18" top="300" width="199" height="36" color="#000000" fontSize="8">
      <math>
        <input>
          <e type="operand">L</e><e type="operand">50</e><e type="operand" style="unit">kg</e>
          <e type="operand" style="unit">m</e><e type="operator" args="2">/</e>
          <e type="operator" args="2">*</e><e type="operand">1.2</e><e type="operator" args="2">*</e>
          <e type="operator" args="2">:</e>
        </input>
        <result action="numeric"><e type="operand">60</e></result>
      </math>
    </region>
    <region left="18" top="1100" width="80" height="20" color="#000000" fontSize="8">
      <text lang="eng" fontFamily="Arial" fontSize="8"><content><p>Second page</p></content></text>
    </region>
  </regions>
  <regions type="header">
    <region left="0" top="18" width="749" height="90" color="#000000">
      <picture><raw format="png" encoding="base64">{pic}</raw></picture>
    </region>
    <region left="123" top="45" width="131" height="20" color="#000000" fontSize="8">
      <math><input><e type="operand">\\[KEYWORDS]\\</e></input></math>
    </region>
    <region left="573" top="45" width="16" height="20" color="#000000" fontSize="8">
      <math><input><e type="operand">\\[PAGENUM[0]]\\</e></input></math>
    </region>
    <region left="666" top="45" width="16" height="20" color="#000000" fontSize="8">
      <math><input><e type="operand">\\[COUNT[0]]\\</e></input></math>
    </region>
  </regions>
</worksheet>'''


def test_page_model_header_pictures_and_rich_text_load():
    ws = loads(_sheet())
    p = ws.page
    assert (round(p.paper_w), round(p.paper_h)) == (794, 1122)
    assert round(p.margin_t) == 112 and round(p.margin_b) == 47 and round(p.margin_l) == 37
    assert p.background and not p.background_full_page
    # the header layer is not content
    assert [r.kind for r in p.header] == ["picture", "math", "math", "math"]
    assert [r.field_code for r in p.header][1:] == ["\\[KEYWORDS]\\", "\\[PAGENUM[0]]\\", "\\[COUNT[0]]\\"]
    kinds = sorted(r.kind for r in ws.regions)
    assert kinds == ["math", "picture", "text", "text", "text"]
    pic = next(r for r in ws.regions if r.kind == "picture")
    assert (pic.pic_w, pic.pic_h) == (749, 90) and pic.image
    rich = next(r for r in ws.ordered() if r.kind == "text")
    assert rich.editor.text == "Design\n\nBrace Check\nPlain line."
    assert rich.line_runs[0][0][1]["bold"] and rich.line_runs[2][0][1]["underline"]
    wrapped = next(r for r in ws.regions if r.text_width)
    assert wrapped.text_width == 120


def test_definition_with_equals_shows_its_value():
    ws = loads(_sheet())
    m = next(r for r in ws.regions if r.kind == "math")
    assert display_text(m.display) == "60 kg/m"


def test_fields():
    now = datetime.datetime(2024, 12, 10, 9, 5)
    meta = {"keywords": "JOB-7", "title": "Issue 1", "author": "ME"}
    assert field_text("\\[KEYWORDS]\\", meta, 3, 8) == "JOB-7"
    assert field_text("\\[PAGENUM[0]]\\", meta, 3, 8) == "3"
    assert field_text("\\[COUNT[0]]\\", meta, 3, 8) == "8"
    assert field_text("\\[DATE[DD\\002E\\MM\\002E\\YYYY]]\\", meta, 1, 1, now=now) == "10.12.2024"


def test_save_round_trip_keeps_everything():
    ws = loads(_sheet())
    text = dumps(ws)
    assert text.count('<regions type="header">') == 1 and "<pageModel" in text and "<picture>" in text
    again = loads(text)

    def sig(w):
        regs = [(r.kind, r.x, r.y, r.editor.text if r.kind == "text" else r.editor.root.text(),
                 [[(t, sorted(st.items())) for t, st in runs] for runs in r.line_runs], r.text_width,
                 r.image, r.pic_w, r.pic_h) for r in w.ordered()]
        p = w.page
        return regs, (p.paper_w, p.paper_h, p.margin_l, p.margin_t, p.margin_b, p.background,
                      [(r.kind, r.x, r.y, r.field_code, r.image) for r in p.header])

    assert sig(again) == sig(ws)
    assert dumps(again) == text  # stable


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_pages_follow_the_file_and_print_like_smath(app):
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageSize, QPdfWriter

    from tests.calc.legacy_ui.worksheet_view import WorksheetView

    ws = loads(_sheet())
    v = WorksheetView(ws)
    v._grow_scene()
    g = v.scene_.geo
    # the 749 px picture is wider than the 720 px printable width: SMath
    # prints at 720/749, so a page holds that much more of the worksheet
    assert abs(g.scale - ws.page.printable_w / (72 + 749)) < 1e-9
    assert abs(g.CH - ws.page.printable_h / g.scale) < 1e-9
    assert v.scene_.page_count() == 2  # "Second page" at y=1100 is past the first page
    second = next(r for r in ws.regions if r.kind == "text" and r.editor.text == "Second page")
    item = v.items[second.id]
    assert item.pos().y() > g.STEP  # drawn on page 2, below its top margin
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.pdf")
        w = QPdfWriter(path)
        w.setPageSize(QPageSize(QPageSize.A4))
        w.setPageMargins(QMarginsF(0, 0, 0, 0))
        v.render_pages(w)
        del w
        import re

        assert len(re.findall(rb"/Type\s*/Page[^s]", open(path, "rb").read())) == 2


def test_pictures_are_selected_not_typed_into(app):
    from tests.calc.legacy_ui.worksheet_view import WorksheetView

    ws = loads(_sheet())
    v = WorksheetView(ws)
    pic = next(it for it in v.items.values() if it.region.special == "picture")
    v.focus_item(pic)
    assert v.focused_item is None and pic in v.selected


# -- SMath's page dialogs and header/footer editing ---------------------------------------------
def test_field_formats_as_smaths_insert_field_dialog():
    from markforge.calc.page import make_field, number_field

    # observed in SMath's Insert Field dialog (Number of pages, 1 page): Format -> Example
    assert [number_field(1, f) for f in ("-1", "22", "-5", "0001")] == ["0", "23", "-4", "0002"]
    assert make_field("DATE", "DD.MM.YYYY") == "\\[DATE[DD\\002E\\MM\\002E\\YYYY]]\\"
    assert make_field("PAGENUM", "0") == "\\[PAGENUM[0]]\\" and make_field("TITLE") == "\\[TITLE]\\"


def test_identity_is_kept_and_each_save_is_a_revision(tmp_path):
    from tests.calc.smfile import load_sm, save_sm

    ws = loads(_sheet())
    assert "_id" not in ws.metadata
    save_sm(ws, tmp_path / "a.sm")
    first = load_sm(tmp_path / "a.sm").metadata
    assert first["_id"] and first["_revision"] == "1"
    ws2 = load_sm(tmp_path / "a.sm")
    save_sm(ws2, tmp_path / "a.sm")
    again = load_sm(tmp_path / "a.sm").metadata
    assert again["_id"] == first["_id"] and again["_revision"] == "2"


def test_edit_header_layer_insert_field_and_leave(app):
    from tests.calc.legacy_ui.worksheet_view import WorksheetView

    ws = loads(_sheet())
    v = WorksheetView(ws)
    content_items = dict(v.items)
    v.edit_layer("header")
    assert v.scene_.layer == "header" and v.worksheet is not ws
    assert {it.region.id for it in v.items.values()} == {r.id for r in ws.page.header}
    assert all(it.opacity() < 1 for it in content_items.values())
    v.scene_.cross.setX(300)
    v.insert_field("\\[TITLE]\\")
    assert ws.page.header[-1].field_code == "\\[TITLE]\\"  # added to the header layer, not the content
    assert v.items[ws.page.header[-1].id].field_value() == "Issue 1"
    v.leave_layer()
    assert v.worksheet is ws and v.items == content_items and v.scene_.layer is None
    assert all(it.opacity() == 1 for it in content_items.values())
    assert "\\[TITLE]\\" in dumps(ws)


def test_page_text_only_without_layers(app):
    from tests.calc.legacy_ui.worksheet_view import WorksheetView

    ws = loads(_sheet())
    ws.page.footer_text = "&[PAGENUM] / &[COUNT]"
    v = WorksheetView(ws)
    calls = []
    v.scene_._paint_page_text = lambda *a: calls.append(a)
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    img = QImage(200, 200, QImage.Format_RGB32)
    p = QPainter(img)
    v.scene_.drawBackground(p, QRectF(0, 0, 800, 800))
    assert not calls  # the file has a header layer: SMath prints the layers, not these lines
    ws.page.header.clear()
    v.scene_.drawBackground(p, QRectF(0, 0, 800, 800))
    p.end()
    assert calls


def test_background_sizes(app):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage

    from tests.calc.legacy_ui.worksheet_view import background_rect

    img = QImage(100, 50, QImage.Format_RGB32)
    t = QRectF(0, 0, 200, 200)
    assert background_rect(t, img, "stretch") == t
    assert background_rect(t, img, "fit") == QRectF(0, 50, 200, 100)
    assert background_rect(t, img, "fill") == QRectF(-100, 0, 400, 200)
    assert background_rect(t, img, "original") == QRectF(50, 75, 100, 50)


def test_page_dialogs_apply(app, tmp_path):
    from tests.calc.legacy_ui.page_dialogs import (BackgroundDialog, FilePropertiesDialog, InsertFieldDialog,
                                          PageSetupDialog)

    ws = loads(_sheet())
    d = PageSetupDialog(ws.page)
    assert d.top.text() == "29,72" and d.size.currentText() == "A4"
    d.landscape.setChecked(True)
    d.left.setText("20")
    d.footer.setText("&[PAGENUM]")
    d.apply()
    assert ws.page.orientation == "Landscape" and ws.page.paper_w > ws.page.paper_h
    assert abs(ws.page.margin_l - 20 * 96 / 25.4) < 1e-6 and ws.page.footer_text == "&[PAGENUM]"
    p = FilePropertiesDialog(ws.metadata, None)
    p.fields["company"].setText("WSP")
    p.apply()
    assert ws.metadata["company"] == "WSP"
    f = InsertFieldDialog(ws.metadata, 8)
    f.list.setCurrentRow(6)  # Current page index
    f.format.setEditText("0001")
    assert f.command.text() == "PAGENUM" and f.example.text() == "0002" and f.code() == "\\[PAGENUM[0001]]\\"
    b = BackgroundDialog(ws.page)
    b.none.setChecked(True)
    b.apply()
    assert ws.page.background == b""
