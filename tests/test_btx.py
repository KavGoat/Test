"""Reading Bluebeam tool sets.

Every test here runs against real ``.btx`` files: two of the user's, kept in
``tests/data/btx/`` (a timber set of grouped shapes and a steel-section set
of stamps; the other thirteen left the repository on 2026-10-29 at the
user's request, and the tests that read them with it). A synthetic file
would prove the parser reads what the parser writes; these prove it reads
what Bluebeam writes.
"""
import glob
import os
import zlib

import pytest
from PySide6.QtCore import QRectF

from calcforge.io import btx
from calcforge.io.pdfobj import Name, operations, parse_dict
from calcforge.items.base import build_item

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "btx")
FILES = sorted(glob.glob(os.path.join(HERE, "*.btx")))


def test_the_sample_tool_sets_are_where_the_tests_expect_them():
    assert len(FILES) == 2


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
    timber = btx.read(os.path.join(HERE, "Structures - Timber.btx"))
    names = [tool.name for tool in timber.tools]
    assert "Timber Post 200x200" in names
    assert "Joist Hanger" in names
    # The parent markup of a group is only ever called "Rectangle"; the name
    # somebody would look for is the group's.
    assert "Rectangle" not in names


def test_a_tool_made_of_several_markups_stays_one_tool():
    timber = btx.read(os.path.join(HERE, "Structures - Timber.btx"))
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
    assert {"rect", "poly", "sketch"} <= types
    assert ("poly", "line") in kinds
    assert ("poly", "polygon") in kinds


# ---------------------------------------------------------------------------
# groups, and groups inside groups
# ---------------------------------------------------------------------------

def _a_tool_set_with_a_group_inside_a_group(path) -> str:
    """A tool set written the way Bluebeam writes a nested group.

    None of the sample files has one — every group in them is a single flat
    group — so the shape of a nested one is written out here: a leader
    annotation naming its members, each member pointing back at it through
    ``/IRT``, and an inner leader that is itself a member of the outer group.
    """
    import binascii
    import zlib

    def packed(text: str) -> str:
        return binascii.hexlify(zlib.compress(text.encode("utf-8"))).decode()

    parts = [
        ("<< /Subtype /Line /Rect [0 0 60 11] /L [5.5 5.5 54.5 5.5] "
         "/C [0 0 0] /NM (OUTER) /GroupNesting "
         "[(Section mark) (OUTER) (INNER) (CUTLINE)] >>"),
        ("<< /Subtype /Circle /Rect [0 0 40 40] /RD [.5 .5 .5 .5] /C [0 0 0] "
         "/NM (INNER) /IRT (OUTER) /RT /Group /GroupNesting "
         "[(Bubble) (INNER) (LABEL)] >>"),
        ("<< /Subtype /FreeText /Rect [0 0 30 14] /Contents (S1) "
         "/DA (0 0 0 rg /Helv 8 Tf) /NM (LABEL) /IRT (INNER) /RT /Group >>"),
        ("<< /Subtype /Line /Rect [0 0 50 11] /L [5.5 5.5 44.5 5.5] "
         "/C [0 0 0] /NM (CUTLINE) /IRT (OUTER) /RT /Group >>"),
    ]
    rows = []
    for order, raw in enumerate(parts):
        tag = "ToolChestItem" if order == 0 else "Child"
        body = (f"<Name>N{order}</Name><Type>Bluebeam.PDF.Annotations."
                f"Annotation</Type><Raw>{packed(raw)}</Raw>"
                f"<X>0</X><Y>0</Y><Index>{order}</Index>")
        rows.append(f"<{tag}>{body}" + ("" if order == 0 else f"</{tag}>"))
    xml = ("<?xml version='1.0'?><BluebeamRevuToolSet>"
           f"<Title>{packed('Nested')}</Title>" + rows[0] + "".join(rows[1:])
           + "</ToolChestItem></BluebeamRevuToolSet>")
    path.write_text(xml, encoding="utf-8")
    return str(path)


def test_a_group_inside_a_group_comes_across_as_one(qapp, tmp_path):
    """Every part in the outer group, and the inner ones in theirs as well."""
    made = btx.read(_a_tool_set_with_a_group_inside_a_group(
        tmp_path / "nested.btx"))
    assert len(made.tools) == 1
    tool = made.tools[0]
    assert tool.name == "Section mark", "the outermost group names the tool"
    assert len(tool.payloads) == 4

    outer = {tuple(p["group_path"])[0] for p in tool.payloads}
    assert len(outer) == 1, "every part is in the one outer group"
    inside = [p for p in tool.payloads if len(p["group_path"]) > 1]
    assert len(inside) == 2, "the bubble and its label are a group of their own"
    assert len({tuple(p["group_path"]) for p in inside}) == 1


def test_ungrouping_takes_off_one_layer_at_a_time(qapp, tmp_path):
    """The bubble and its label stay together when the mark is taken apart."""
    made = btx.read(_a_tool_set_with_a_group_inside_a_group(
        tmp_path / "nested.btx"))
    items = [build_item(dict(p)) for p in made.tools[0].payloads]
    assert len({item.group for item in items}) == 1, "one thing to click on"

    for item in items:
        item.out_of_its_outer_group()
    left = {item.group for item in items if item.group}
    assert len(left) == 1, "what was inside is still one group"
    assert sum(1 for item in items if item.group) == 2
    assert sum(1 for item in items if not item.group) == 2


def test_two_of_the_same_tool_are_two_things_and_not_one(qapp, tmp_path):
    """Putting a tool down twice gives two groups, not one group of eight."""
    from calcforge.items.base import rename_groups

    made = btx.read(_a_tool_set_with_a_group_inside_a_group(
        tmp_path / "nested.btx"))
    placed = []
    for _ in range(2):
        renamed: dict = {}
        for payload in made.tools[0].payloads:
            copy = dict(payload)
            rename_groups(copy, renamed)
            placed.append(copy)
    outer = {p["group"] for p in placed}
    assert len(outer) == 2, "each one is its own group"
    paths = {tuple(p["group_path"]) for p in placed}
    assert len(paths) == 4, "and each keeps its own inner group"


def test_a_markup_bluebeam_turned_comes_back_turned(qapp):
    """``/Rotation`` is degrees clockwise about the middle of the markup's box."""
    upright = {"Subtype": "Polygon", "Rect": [0, 0, 40, 20],
               "Vertices": [10, -10, 10, 30, 30, 10]}    # apex pointing right
    straight = btx.markup_from(upright, {})
    turned = btx.markup_from(dict(upright, Rotation=90), {})
    # Upright: the apex is the point furthest to the right, halfway down.
    assert straight["points"][2] == pytest.approx([30.0, 10.0])
    # Turned a quarter turn clockwise: the apex is at the bottom, halfway
    # across. Display measures down the page, so "the bottom" is the big y.
    assert turned["points"][2] == pytest.approx([20.0, 20.0])


# ---------------------------------------------------------------------------
# a stamp's drawing
# ---------------------------------------------------------------------------

def test_a_steel_section_comes_across_as_a_drawing(qapp):
    sections = btx.read(os.path.join(HERE, "Structural Steel UC Sections - 1-10 @ A1.btx"))
    tool = next(t for t in sections.tools if t.name.startswith("150UC"))
    payload = tool.payloads[0]
    assert payload["type"] == "sketch"

    item = build_item(payload)
    assert len(item.strokes) > 10, "a UC in section is more than a few lines"
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
    sections = btx.read(os.path.join(HERE, "Structural Steel UC Sections - 1-10 @ A1.btx"))
    item = build_item(next(t for t in sections.tools
                           if t.name.startswith("150UC")).payloads[0])
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
# labels, and the size of every tool
# ---------------------------------------------------------------------------

def test_a_labels_colour_comes_across_from_either_place():
    """/DS says one colour and /DA another; the stylesheet wins, as it should."""
    assert btx._text_look({"Subtype": "FreeText",
                           "DS": "font: Helvetica 8pt; color:#c92a2a"}) \
        ["text_color"] == "#c92a2a"
    assert btx._text_look({"Subtype": "FreeText",
                           "DA": "1 0 0 rg /Helv 8 Tf"})["text_color"] == "#ff0000"
    assert btx._text_look({"Subtype": "FreeText", "Q": 2})["align"] == "right"
    assert btx._text_look({"Subtype": "Square", "Q": 2}) == {}


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


def test_every_tool_still_fits_in_a_sensible_box(qapp):
    """A part placed by the wrong rule shows up as a tool the size of a page."""
    for path in FILES:
        for tool in btx.read(path).tools:
            box = None
            for payload in tool.payloads:
                item = build_item(payload)
                here = item.local_rect().translated(item.pos())
                box = here if box is None else box.united(here)
            assert box.width() < 700 and box.height() < 700, \
                f"{tool.name} came out {box.width():.0f}x{box.height():.0f}"


# ---------------------------------------------------------------------------
# 2026-09-29: groups in groups, in Bluebeam's own sheet
# ---------------------------------------------------------------------------

def test_bluebeams_own_pdf_opens_with_its_groups_in_groups(qapp):
    from collections import Counter
    from calcforge.io import pdfmarkups, pdfvector

    source = pdfvector.PdfFile.open(os.path.join(HERE, "Document1.pdf"))
    made = pdfmarkups.markups_of_page(source, 0)
    sections = Counter(tuple(p["group_path"]) for p in made
                       if p.get("group_title") == "Section")
    assert sorted(sections.values()) == [2, 2, 6, 6]        # two section marks
    assert {path[0] for path in sections} and all(len(p) == 2 for p in sections)


