"""Reading Bluebeam tool sets.

Every test here runs against the real ``.btx`` files in ``btx/`` — the ones
they were brought across for. A synthetic file would prove the parser reads
what the parser writes; these prove it reads what Bluebeam writes.
"""
import glob
import os
import zlib

import pytest
from PySide6.QtCore import QRectF

from calcforge.io import btx
from calcforge.io.pdfobj import Name, operations, parse, parse_dict
from calcforge.items.base import build_item

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(glob.glob(os.path.join(HERE, "btx", "*.btx")))


def test_the_sample_tool_sets_are_where_the_tests_expect_them():
    assert len(FILES) >= 15


# ---------------------------------------------------------------------------
# the PDF object syntax
# ---------------------------------------------------------------------------

def test_a_dictionary_reads_as_a_dictionary():
    found = parse_dict(b"<</Subtype/Square/Rect[0 0 57.2 57.2]/F 4"
                       b"/BS<</W 0.5/S/S/Type/Border>>>>")
    assert found["Subtype"] == "Square"
    assert found["Rect"] == [0, 0, 57.2, 57.2]
    assert found["F"] == 4
    assert found["BS"] == {"W": 0.5, "S": "S", "Type": "Border"}


def test_names_strings_and_numbers_keep_themselves_apart():
    found = parse_dict(rb"<</A/S/B(S)/C -3.5/D true/E<</F[1 [2]]>>/G()>>")
    assert isinstance(found["A"], Name) and found["A"] == "S"
    assert found["B"] == "S" and not isinstance(found["B"], Name)
    assert found["C"] == -3.5
    assert found["D"] is True
    assert found["E"]["F"] == [1, [2]]
    assert found["G"] == ""


def test_an_escaped_string_comes_back_with_its_characters():
    found = parse_dict(rb"<</A(one\(two\) \\ \n \101)>>")
    assert found["A"] == "one(two) \\ \n A"


def test_a_comment_is_not_read_as_a_value():
    assert parse_dict(b"<</A 1 % this is ignored\n/B 2>>") == {"A": 1, "B": 2}


def test_a_truncated_object_does_not_hang():
    assert parse_dict(b"<</A[1 2 /B<</C") is not None


def test_a_content_stream_reads_as_operands_and_operators():
    ops = operations(b"q 1 0 0 1 5 5 cm 0 0 m 10 0 l S Q")
    assert ops == [([], "q"), ([1, 0, 0, 1, 5, 5], "cm"), ([0, 0], "m"),
                   ([10, 0], "l"), ([], "S"), ([], "Q")]


# ---------------------------------------------------------------------------
# colours and geometry
# ---------------------------------------------------------------------------

def test_colours_come_across_from_every_space():
    assert btx.colour([1, 0, 0]) == "#ff0000"
    assert btx.colour([0.5]) == "#808080"                 # grey
    assert btx.colour([0, 0, 0, 0]) == "#ffffff"          # CMYK white
    assert btx.colour([]) == ""                           # not coloured at all
    assert btx.colour(None) == ""


# ---------------------------------------------------------------------------
# every file, every tool
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", FILES, ids=lambda p: os.path.basename(p)[:28])
def test_every_tool_set_reads_without_losing_a_tool(path):
    imported = btx.read(path)
    assert imported.name and not imported.name.startswith("789c")
    assert imported.tools, "no tools came out of the file"
    assert imported.skipped == 0, "a tool could not be read at all"


@pytest.mark.parametrize("path", FILES, ids=lambda p: os.path.basename(p)[:28])
def test_every_tool_becomes_markups_that_can_be_built(path, qapp):
    imported = btx.read(path)
    for tool in imported.tools:
        assert tool.payloads
        for payload in tool.payloads:
            item = build_item(payload)
            assert item is not None, f"{tool.name}: no item for {payload['type']}"
            box = item.local_rect()
            assert box.width() > 0 and box.height() > 0, f"{tool.name} has no size"
            assert box.width() < 5000 and box.height() < 5000, \
                f"{tool.name} came out {box.width():.0f}x{box.height():.0f}"


def test_the_tools_have_the_names_bluebeam_gave_them():
    timber = btx.read(os.path.join(HERE, "btx", "Structures - Timber.btx"))
    names = [tool.name for tool in timber.tools]
    assert "Timber Post 200x200" in names
    assert "Joist Hanger" in names
    # The parent markup of a group is only ever called "Rectangle"; the name
    # somebody would look for is the group's.
    assert "Rectangle" not in names


def test_a_tool_made_of_several_markups_stays_one_tool():
    timber = btx.read(os.path.join(HERE, "btx", "Structures - Timber.btx"))
    post = next(t for t in timber.tools if t.name == "Timber Post 200x200")
    assert post.is_group and len(post.payloads) > 1
    assert len({p["group"] for p in post.payloads}) == 1


def test_each_kind_of_bluebeam_markup_lands_on_the_right_one_here(qapp):
    kinds = set()
    for path in FILES:
        for tool in btx.read(path).tools:
            for payload in tool.payloads:
                kinds.add((payload["type"], payload.get("kind", "")))
    types = {kind[0] for kind in kinds}
    # Squares and circles, lines and polygons, text, and the drawings that
    # come off a stamp: every one of those is in the fifteen sample files.
    assert {"rect", "poly", "text", "sketch"} <= types
    assert ("rect", "ellipse") in kinds
    assert ("poly", "polygon") in kinds


# ---------------------------------------------------------------------------
# a stamp's drawing
# ---------------------------------------------------------------------------

def test_a_steel_section_comes_across_as_a_drawing(qapp):
    sections = btx.read(os.path.join(HERE, "btx",
                                     "Structural Steel UB Sections - 1-10 @ A1.btx"))
    tool = next(t for t in sections.tools if t.name.startswith("150UB"))
    payload = tool.payloads[0]
    assert payload["type"] == "sketch"

    item = build_item(payload)
    assert len(item.strokes) > 20, "a UB in section is more than a few lines"
    # The drawing sits inside the box the tool says it is, not somewhere off
    # in the page coordinates it was captured from.
    box = item.local_rect()
    for stroke in item.strokes:
        for command in stroke["path"]:
            for index in range(1, len(command), 2):
                x, y = command[index], command[index + 1]
                assert -1 <= x <= box.width() + 1
                assert -1 <= y <= box.height() + 1


def test_a_drawing_keeps_its_colours_and_its_fills(qapp):
    sections = btx.read(os.path.join(HERE, "btx",
                                     "Structural Steel UB Sections - 1-10 @ A1.btx"))
    item = build_item(next(t for t in sections.tools
                           if t.name.startswith("150UB")).payloads[0])
    assert any(stroke["fill"] for stroke in item.strokes), "nothing is filled"
    assert any(stroke["stroke"] for stroke in item.strokes), "nothing is drawn"


def test_a_drawing_scales_with_its_box(qapp):
    from calcforge.items.shapes import SketchItem

    item = SketchItem([{"path": [["m", 0, 0], ["l", 10, 0], ["l", 10, 10], ["z"]],
                        "stroke": "#000000", "fill": "", "width": 1.0}])
    assert item.local_rect() == QRectF(0, 0, 10, 10)
    item.set_local_rect(QRectF(0, 0, 40, 20))
    assert item._transform()[:2] == (4.0, 2.0)


def test_a_drawing_survives_a_save(qapp):
    from calcforge.items.shapes import SketchItem

    item = SketchItem([{"path": [["m", 0, 0], ["c", 1, 1, 2, 2, 3, 3]],
                        "stroke": "#123456", "fill": "#abcdef", "width": 0.5}])
    item.set_local_rect(QRectF(5, 5, 30, 30))
    clone = build_item(item.serialize())
    assert clone.strokes == item.strokes
    assert clone.local_rect() == item.local_rect()
    assert clone.source_box == item.source_box


# ---------------------------------------------------------------------------
# damaged files
# ---------------------------------------------------------------------------

def test_something_that_is_not_a_tool_set_says_so(tmp_path):
    path = tmp_path / "not.btx"
    path.write_bytes(b"<?xml version='1.0'?><Something/>")
    with pytest.raises(btx.BtxError):
        btx.read(str(path))


def test_a_file_that_is_not_xml_at_all_says_so(tmp_path):
    path = tmp_path / "broken.btx"
    path.write_bytes(b"\x00\x01 not xml")
    with pytest.raises(btx.BtxError):
        btx.read(str(path))


def test_a_missing_file_says_so():
    with pytest.raises(btx.BtxError):
        btx.read("/nowhere/at/all.btx")


def test_a_tool_whose_raw_field_is_rubbish_is_skipped(tmp_path):
    path = tmp_path / "half.btx"
    good = zlib.compress(b"<</Subtype/Square/Rect[0 0 20 10]/C[1 0 0]"
                         b"/BS<</W 1>>>>").hex()
    path.write_bytes(f"""<?xml version="1.0" encoding="utf-8"?>
<BluebeamRevuToolSet Version="1">
  <Title>{zlib.compress(b"Half a set").hex()}</Title>
  <ToolChestItem Version="1"><Name>A</Name>
    <Type>Bluebeam.PDF.Annotations.AnnotationSquare</Type>
    <Raw>{good}</Raw><X>0</X><Y>0</Y><Index>1</Index><Mode>drawing</Mode>
  </ToolChestItem>
  <ToolChestItem Version="1"><Name>B</Name>
    <Type>Bluebeam.PDF.Annotations.AnnotationSquare</Type>
    <Raw>not hex at all</Raw><X>0</X><Y>0</Y><Index>2</Index><Mode>drawing</Mode>
  </ToolChestItem>
</BluebeamRevuToolSet>""".encode("utf-8"))
    imported = btx.read(str(path))
    assert imported.name == "Half a set"
    assert len(imported.tools) == 1        # the good one still comes through
    assert imported.skipped == 1           # and the bad one is counted, not hidden


# ---------------------------------------------------------------------------
# A section mark has to look like a section mark
# ---------------------------------------------------------------------------

def test_a_labels_words_are_lined_up_the_way_bluebeam_lined_them_up(qapp):
    """"S1" belongs in the middle of its bubble, not in the corner of its box.

    Bluebeam writes the alignment in the CSS-ish /DS string rather than in
    PDF's own /Q, so reading only /Q leaves every label hard against the
    top-left of the box it sits in — which is what made a section mark look
    broken rather than merely plain.
    """
    marks = btx.read(os.path.join(HERE, "btx", "Structures - Sketch Tools.btx"))
    tool = marks.tools[0]
    labels = [p for p in tool.payloads if p["type"] == "text"]
    assert labels, "the section mark has no words in it"
    for label in labels:
        assert label["style"]["align"] == "center"
        assert label["style"]["valign"] == "middle"


def test_the_alignment_reaches_the_markup(qapp):
    marks = btx.read(os.path.join(HERE, "btx", "Structures - Sketch Tools.btx"))
    label = [p for p in marks.tools[0].payloads if p["type"] == "text"][0]
    item = build_item(label)
    assert item.style.align == "center"
    assert item.style.valign == "middle"


def test_a_labels_colour_comes_across_from_either_place():
    """/DS says one colour and /DA another; the stylesheet wins, as it should."""
    assert btx._text_look({"Subtype": "FreeText",
                           "DS": "font: Helvetica 8pt; color:#c92a2a"}) \
        ["text_color"] == "#c92a2a"
    assert btx._text_look({"Subtype": "FreeText",
                           "DA": "1 0 0 rg /Helv 8 Tf"})["text_color"] == "#ff0000"
    assert btx._text_look({"Subtype": "FreeText", "Q": 2})["align"] == "right"
    assert btx._text_look({"Subtype": "Square", "Q": 2}) == {}


def test_the_parts_of_a_section_mark_line_up_with_each_other(qapp):
    """The cut line runs through the middle of the bubble, not past it."""
    from calcforge.items.shapes import PolyItem, RectItem

    marks = btx.read(os.path.join(HERE, "btx", "Structures - Sketch Tools.btx"))
    tool = marks.tools[0]
    items = [build_item(p) for p in tool.payloads]
    circles = [i for i in items if isinstance(i, RectItem) and i.kind == "ellipse"]
    lines = [i for i in items if isinstance(i, PolyItem) and i.kind == "line"]
    assert circles and lines

    bubble = circles[0].mapRectToParent(circles[0].local_rect())
    for line in lines:
        ends = [line.mapToParent(point) for point in line.points]
        heights = [point.y() for point in ends]
        # Level, and level with the middle of the bubble.
        assert abs(heights[0] - heights[-1]) < 1.0
        assert abs(heights[0] - bubble.center().y()) < 1.5


def test_every_label_in_every_file_keeps_its_own_look(qapp):
    """Whatever the file says about a label, the markup wears it."""
    for path in FILES:
        for tool in btx.read(path).tools:
            for payload in tool.payloads:
                if payload["type"] not in ("text", "callout"):
                    continue
                style = payload["style"]
                assert style["align"] in ("left", "center", "right")
                assert style.get("valign", "top") in ("top", "middle", "bottom")
