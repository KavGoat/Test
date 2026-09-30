"""The snapshot tool (2026-09-30): whatever can be seen in the box is taken,
as line work wherever it can be (photos stay pixels), and it is not live.

Each test snapshots a region, pastes the snapshot onto a blank page at the
same place, and compares the two pages as CalcForge draws them — and, once
saved, as MuPDF and pdfium draw them.
"""
from __future__ import annotations

import shutil

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt

from calcforge.core.document import PageSetup
from calcforge.items.calc import CalcItem
from calcforge.items.shapes import RectItem
from calcforge.items.snapshot import SnapshotItem
from calcforge.items.text import TextItem
from tests import fidelity
from tests.test_calc_saving import answer, reopen, save_to, write_lines
from tests.test_roundtrip import (assert_alike, compare_everywhere, every_kind,
                                  the_second_page)


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    return window


def snapshot_onto_a_new_page(window, page: int, region: QRectF) -> tuple:
    """Snapshot *region* of *page* and paste it at the same place on a new
    blank page of the same size. Returns (new page index, the snapshot)."""
    source = window.document.pages[page]
    window.take_snapshot(source.frame, region)
    assert window._clipboard, window.status_hint.text()
    setup = PageSetup.from_dict(source.setup.to_dict())
    window.document.pages.append(type(source)(setup))
    window.rebuild_scenes()
    index = len(window.document.pages) - 1
    target = window.document.pages[index].frame
    before = {id(i) for page in window.document.pages for i in page.frame.markups()}
    window.go_to_page(index)
    window.paste_in_place()
    (shot,) = [i for page in window.document.pages for i in page.frame.markups()
               if isinstance(i, SnapshotItem) and id(i) not in before]
    if shot.parentItem() is not target:
        target.add_markup(shot)
    shot.setPos(region.topLeft())
    return index, shot


def looks_like(window, page_a: int, page_b: int, region: QRectF, **limits) -> None:
    a = fidelity.calcforge(window.document.pages[page_a].frame)
    b = fidelity.calcforge(window.document.pages[page_b].frame)
    got = fidelity.compare(a, b, region)
    assert got["ink"][0] > 50, "there was something to take"
    assert got["overlap"] > limits.get("overlap", 0.9) and \
        got["shift"] <= limits.get("shift", 1.5) and \
        got["colour"] < limits.get("colour", 45), f"the snapshot differs: {got}"


def test_a_snapshot_of_everything_looks_like_what_was_there(win, tmp_path):
    regions = every_kind(win)
    whole = QRectF(30, 50, 530, 750)
    index, shot = snapshot_onto_a_new_page(win, 0, whole)
    looks_like(win, 0, index, whole)
    for name, box in regions.items():
        looks_like(win, 0, index, box)
    # and it is drawing, not live: nothing in it calculates or can be typed in
    assert not any(isinstance(i, CalcItem) for i in win.document.pages[index].frame.markups())
    assert [s["type"] for s in shot.source_items] == ["pdf_svg"]
    # saved, the other readers show the snapshot the same way
    path = str(tmp_path / "snap.pdf")
    save_to(win, path)
    assert_alike(compare_everywhere(win, path, {"snapshot": whole}, page=index))


def test_a_snapshot_of_a_plot_and_a_snapshot(win, tmp_path):
    every_kind(win)
    more = the_second_page(win)
    region = more["plot"].united(more["snapshot"]).adjusted(-5, -5, 5, 5)
    index, _shot = snapshot_onto_a_new_page(win, 1, region)
    looks_like(win, 1, index, more["plot"])
    looks_like(win, 1, index, more["snapshot"])


def test_equations_in_a_snapshot_stay_as_they_were(win, tmp_path):
    write_lines(win, ["a1:2", "b1:a1*5", "b1="], x=80, y=100)
    region = QRectF(70, 90, 200, 70)
    index, shot = snapshot_onto_a_new_page(win, 0, region)
    looks_like(win, 0, index, region)
    # change the equation: the snapshot does not follow (it is not live)
    before = fidelity.calcforge(win.document.pages[index].frame)
    (first,) = [i for i in win.document.pages[0].frame.markups()
                if isinstance(i, CalcItem) and i.text().startswith("a1")]
    win.view.calc.focus(first, first.sceneBoundingRect().center())
    from tests.test_usability import press_key
    from tests.test_calc_modes import typed
    press_key(win.view, Qt.Key_End)
    typed(win, "0")
    press_key(win.view, Qt.Key_Escape)
    assert answer(win, "b1=") == "100"
    after = fidelity.calcforge(win.document.pages[index].frame)
    assert (before == after).all(), "the snapshot is what was seen, not live"


def a_drawing_with_a_title_block(path: str) -> None:
    """A sheet whose title block is the PDF's own lines and words."""
    document = pymupdf.open()
    page = document.new_page(width=842, height=595)
    block = pymupdf.Rect(560, 440, 820, 575)
    page.draw_rect(block, color=(0, 0, 0), width=1.2)
    for y in (470, 500, 530):
        page.draw_line((560, y), (820, y), color=(0, 0, 0), width=0.6)
    page.draw_line((690, 500), (690, 575), color=(0, 0, 0), width=0.6)
    page.insert_text((570, 460), "ACME ENGINEERING", fontsize=12)
    page.insert_text((570, 490), "PROJECT: CAR PARK EXTENSION", fontsize=9)
    page.insert_text((570, 520), "DRAWN: KD", fontsize=8)
    page.insert_text((700, 520), "CHECKED: JS", fontsize=8)
    page.insert_text((570, 555), "DWG S-101  REV C", fontsize=10)
    for x in range(40, 540, 40):
        page.draw_line((x, 40), (x, 400), color=(0.3, 0.3, 0.3), width=0.4)
    document.save(path)


def test_a_title_block_comes_with_its_words(win, tmp_path):
    """Reported: snapshotting a title block brought its lines, not its text —
    whether the words are the PDF's own or typed on as markups."""
    source = str(tmp_path / "sheet.pdf")
    a_drawing_with_a_title_block(source)
    reopen(win, source)
    frame = win.document.pages[0].frame
    # a title block of our own too: a box with words typed into it, grouped
    box = RectItem("rect", QRectF(0, 0, 200, 60))
    box.style.stroke = "#000000"
    frame.add_markup(box, QPointF(40, 440))
    words = TextItem("CALC PACKAGE — SHEET 3 OF 12")
    words.set_local_rect(QRectF(0, 0, 190, 24))
    words.style.stroke = ""
    frame.add_markup(words, QPointF(45, 450))
    for region in (QRectF(550, 430, 280, 155), QRectF(30, 430, 220, 80)):
        index, shot = snapshot_onto_a_new_page(win, 0, region)
        looks_like(win, 0, index, region)
    path = str(tmp_path / "blocks.pdf")
    save_to(win, path)
    with pymupdf.open(path) as document:
        # the words are there as drawing (outlines), where they were seen
        drawn = fidelity.mupdf(path, 1)
        assert drawn[int(440 * 2):int(575 * 2), int(560 * 2):int(820 * 2)].mean() < 250
    assert_alike(compare_everywhere(win, path, {"block": QRectF(550, 430, 280, 155)},
                                    page=1))
    assert_alike(compare_everywhere(win, path, {"ours": QRectF(30, 430, 220, 80)},
                                    page=2))


def test_a_snapshot_of_somebody_elses_marked_up_drawing(win, tmp_path):
    """A real Bluebeam sheet: its drawing and its markups — which the file
    itself draws — come across as they are seen."""
    from tests.test_format import REFERENCE

    source = str(tmp_path / "theirs.pdf")
    shutil.copy(REFERENCE, source)
    reopen(win, source)
    page = win.document.pages[0]
    region = QRectF(0, 0, page.width_pt, page.height_pt * 0.5)
    index, shot = snapshot_onto_a_new_page(win, 0, region)
    looks_like(win, 0, index, region)


def test_a_snapshot_on_a_turned_drawing(win, tmp_path):
    from tests.test_format import _a_turned_pdf

    source = str(tmp_path / "turned.pdf")
    _a_turned_pdf(source, 90)
    reopen(win, source)
    frame = win.document.pages[0].frame
    frame.add_markup(RectItem("cloud", QRectF(0, 0, 120, 60)), QPointF(150, 100))
    write_lines(win, ["t2:7*6", "t2="], x=300, y=220)
    page = win.document.pages[0]
    region = QRectF(0, 0, page.width_pt, page.height_pt)
    index, _shot = snapshot_onto_a_new_page(win, 0, region)
    looks_like(win, 0, index, region)


def test_a_box_running_off_the_page_takes_what_is_on_it(win, tmp_path):
    """(With the turned-drawing test above, this also guards printing a
    selected snapshot: drawn from its cached picture it came out with its
    dashed selection box round it — scene.render_page turns caching off.)"""
    frame = win.document.pages[0].frame
    frame.add_markup(RectItem("rect", QRectF(0, 0, 80, 40)), QPointF(10, 10))
    write_lines(win, ["e2:1"], x=20, y=70)
    region = QRectF(-40, -40, 200, 160)
    win.take_snapshot(frame, region)
    assert win._clipboard, "a box partly off the sheet still takes what is on it"
    index, shot = snapshot_onto_a_new_page(win, 0, region)
    looks_like(win, 0, index, QRectF(0, 0, 160, 120))

