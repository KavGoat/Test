"""File ▸ Export markups (CSV): one row per markup, every kind, in page
order, readable by Excel as written (2026-10-10)."""
from __future__ import annotations

import csv

import pytest

from PySide6.QtCore import QPointF, QRectF

from calcforge.io.export import export_markups_csv
from calcforge.items.shapes import RectItem
from tests.test_tables import make_table, pump, w  # noqa: F401


def test_every_markup_one_row_and_excel_reads_the_symbols(w, tmp_path):
    frame = w.document.pages[0].frame
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 30, 12))
    box.subject = "Opening 600×600"
    frame.add_markup(box, QPointF(100, 300))
    make_table(w)
    w.view.tables.close()
    w.insert_sheet_page(0)
    pump()
    path = tmp_path / "markups.csv"
    assert export_markups_csv(w.document, str(path)) == 3
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "a byte-order mark: Excel then reads UTF-8"
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    assert rows[0] == ["Page", "Type", "Subject", "Value", "Author", "Created", "Modified", "Comment"]
    kinds = {(r[0], r[1]) for r in rows[1:]}
    assert ("1", "Rectangle") in kinds and ("1", "Table1") in kinds and ("2", "Sheet1") in kinds
    assert any(r[2] == "Opening 600×600" for r in rows[1:])


def test_link_markups_work_in_the_exported_pdf(w, tmp_path):
    """A link to a page, to a view part-way down one, to a web address and
    to a file: each a working link in the exported PDF; one to a page not
    exported is left out rather than pointing nowhere."""
    import pymupdf

    from calcforge.io import export as export_io
    from calcforge.items.link import FILE, PAGE, VIEW, WEB, LinkItem
    w.add_page()
    w.add_page()
    frame = w.document.pages[0].frame
    for i, (kind, page, y, address) in enumerate(((PAGE, 1, 0.0, ""), (VIEW, 2, 300.0, ""),
                                                  (WEB, 0, 0.0, "https://example.com/spec"),
                                                  (FILE, 0, 0.0, "calcs/beam.pdf"))):
        link = LinkItem(QRectF(0, 0, 80, 20))
        link.kind, link.target_page, link.target_y, link.address = kind, page, y, address
        frame.add_markup(link, QPointF(60, 100 + 40 * i))
    path = str(tmp_path / "links.pdf")
    export_io.export_pdf(w.document, path)
    with pymupdf.open(path) as pdf:
        links = sorted(pdf[0].get_links(), key=lambda link: link["from"].y0)
    assert [link["kind"] for link in links] == [pymupdf.LINK_GOTO, pymupdf.LINK_GOTO,
                                                pymupdf.LINK_URI, pymupdf.LINK_GOTOR]  # another PDF
    assert [links[0]["page"], links[1]["page"]] == [1, 2]
    assert links[1]["to"].y == pytest.approx(300, abs=2) or links[1]["to"].y == pytest.approx(
        w.document.pages[2].height_pt - 300, abs=2), "part-way down the page"
    assert links[2]["uri"] == "https://example.com/spec"
    assert links[3]["file"].endswith("beam.pdf")
    # only the first page exported: the page links go nowhere, so they are left out
    export_io.export_pdf(w.document, path, pages=[w.document.pages[0]])
    with pymupdf.open(path) as pdf:
        assert [link["kind"] for link in pdf[0].get_links()].count(pymupdf.LINK_GOTO) == 0


def test_link_markups_show_on_screen_and_come_back_after_saving(w, tmp_path):
    """A link is a dashed blue box on screen (never on paper), and every kind
    comes back from the saved file as it was (2026-10-10)."""
    from calcforge.items.link import FILE, PAGE, VIEW, WEB, LinkItem
    w.add_page()
    w.go_to_page(0)
    frame = w.document.pages[0].frame
    made = [(PAGE, 1, 0.0, ""), (VIEW, 1, 250.0, ""), (WEB, 0, 0.0, "https://example.com/spec"),
            (FILE, 0, 0.0, "calcs/beam.pdf")]
    for i, (kind, page, y, address) in enumerate(made):
        link = LinkItem(QRectF(0, 0, 80, 20))
        link.kind, link.target_page, link.target_y, link.address = kind, page, y, address
        frame.add_markup(link, QPointF(60, 100 + 40 * i))
    w.view.set_zoom(1.0)
    first = next(i for i in frame.markups() if isinstance(i, LinkItem))
    w.view.centerOn(first.mapToScene(first.local_rect().center()))
    pump()
    image = w.view.viewport().grab().toImage()
    edge = w.view.mapFromScene(first.mapToScene(first.local_rect().topLeft() + QPointF(20, 0)))
    colour = image.pixelColor(edge.x(), edge.y())
    assert colour.blue() > colour.red() + 40, "the dashed blue edge"
    path = str(tmp_path / "links.pdf")
    w.document.path = path
    assert w.save_document()
    w.open_from_command_line(path)
    pump()
    back = sorted(((i.kind, i.target_page, i.target_y, i.address) for i in
                   w.document.pages[0].frame.markups() if isinstance(i, LinkItem)), key=str)
    assert back == sorted(made, key=str)
