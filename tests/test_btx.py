"""Reading Bluebeam tool sets.

Every test here runs against the real ``.btx`` files in ``btx/`` — the ones
they were brought across for. A synthetic file would prove the parser reads
what the parser writes; these prove it reads what Bluebeam writes.
"""
import math
import glob
import os
import zlib

import pytest
from PySide6.QtCore import QRectF

from markforge.io import btx
from markforge.io.pdfobj import Name, operations, parse, parse_dict
from markforge.items.base import build_item

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
# a section mark, put together
#
# The one thing every one of these files is really for. A section mark is a
# bubble with a cut line through it, an arrowhead on the bubble saying which
# way the section looks, and two labels inside. Every part of it is a separate
# annotation, so it only reads as a section mark if all of them land in the
# right place relative to each other — which makes it the sharpest test there
# is of how the parts of a tool are positioned. The numbers below are read off
# ``btx/Document1.pdf``, a sheet with these same tools placed on it.
# ---------------------------------------------------------------------------

def _sketch_tools():
    return btx.read(os.path.join(HERE, "btx", "Structures - Sketch Tools.btx"))


def _part(tool, kind: str, which: int = 0) -> dict:
    found = [p for p in tool.payloads
             if p.get("kind") == kind or p.get("type") == kind]
    return found[which]


def _place(payload) -> QRectF:
    """Where a payload sits on the page, as a box."""
    item = build_item(payload)
    return item.local_rect().translated(item.pos())


def test_a_section_marks_cut_line_crosses_its_own_bubble(qapp):
    """The line is a chord of the circle, not a tail hanging off one side.

    X and Y on a tool's parts say how far the tool's anchor is *from* each
    one, so they are applied the other way round. Read the sign the other way
    and the cut line lands ten points clear of the bubble it belongs to.
    """
    tool = [t for t in _sketch_tools().tools if t.name == "Elevation"][1]
    bubble = _place(_part(tool, "ellipse"))
    line = _place(_part(tool, "line"))
    # Flush with it: the chord is drawn right across the bubble, its ends
    # landing on the circle within a fraction of a point either side.
    assert abs(line.left() - bubble.left()) < 0.2, \
        f"the cut line {line} does not start at the bubble {bubble}"
    assert abs(line.right() - bubble.right()) < 0.2, \
        f"the cut line {line} does not finish at the bubble {bubble}"
    # And through the middle of it, which is what divides the two labels.
    assert abs(line.center().y() - bubble.center().y()) < 1.0


def test_a_section_marks_arrowhead_points_away_from_its_bubble(qapp):
    """Apex clear of the circle, base behind it — which way the section looks.

    The arrowhead is drawn upright and turned with ``/Rotation``. Ignoring
    that left it beside the bubble; turning it the wrong way round left it
    pointing into the bubble instead of out of it.
    """
    tool = [t for t in _sketch_tools().tools if t.name == "Elevation"][1]
    bubble = _place(_part(tool, "ellipse"))
    head = build_item(_part(tool, "polygon"))
    points = [p + head.pos() for p in head.points]
    apex = min(points, key=lambda p: p.y())          # the one furthest up
    assert apex.y() < bubble.top(), "the arrowhead does not clear the bubble"
    assert abs(apex.x() - bubble.center().x()) < 1.0, "and it is off to one side"
    base = [p for p in points if p is not apex]
    assert all(bubble.contains(p) for p in base), \
        "the wide end of the arrowhead should sit behind the bubble"


def test_a_section_marks_arrowhead_touches_its_bubble(qapp):
    """The two corners of the base sit exactly on the circle, not inside it.

    A shape annotation is drawn inside its ``Rect`` less its ``/RD``, and the
    border is kept inside *that* rather than straddling it — so the path is in
    by another half a border width. Drawing the bubble in the whole of
    ``Rect`` makes it a border width wider than its own file draws it, and an
    arrowhead built to meet the bubble ends up a point inside it. On a
    forty-point bubble that is plain to see.
    """
    tool = [t for t in _sketch_tools().tools if t.name == "Elevation"][1]
    bubble = _place(_part(tool, "ellipse"))
    head = build_item(_part(tool, "polygon"))
    points = [p + head.pos() for p in head.points]
    middle = bubble.center()
    radius = bubble.width() / 2.0
    def how_far(point):
        return math.hypot(point.x() - middle.x(), point.y() - middle.y())

    base = sorted(points, key=how_far)[:2]
    for corner in base:
        gap = math.hypot(corner.x() - middle.x(), corner.y() - middle.y())
        assert abs(gap - radius) < 0.01, (
            f"the arrowhead's base is {gap - radius:+.3f}pt off the bubble; "
            f"it should touch it")


def test_a_shape_is_drawn_the_size_its_own_file_draws_it(qapp):
    """Rect less /RD less half the border — measured off the reference sheet.

    ``btx/Document1.pdf`` has these very tools placed on it, and the circle's
    own appearance stream draws a path 37.803 across inside a 39.803 Rect
    whose /RD is 0.5 and whose border is 1.
    """
    tool = [t for t in _sketch_tools().tools if t.name == "Elevation"][1]
    bubble = _part(tool, "ellipse")
    assert bubble["rect"][2] == pytest.approx(37.803, abs=0.01)
    assert bubble["rect"][3] == pytest.approx(37.803, abs=0.01)
    # And it is still in the middle of where Rect put it.
    assert bubble["rect"][0] == pytest.approx(1.0, abs=0.01)
    assert bubble["rect"][1] == pytest.approx(1.0, abs=0.01)


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
    from markforge.items.base import rename_groups

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


def test_a_legend_keeps_its_heading_and_the_space_between_its_entries(qapp):
    """Bold, underlined, and the blank lines that hold the entries apart.

    Bluebeam sets a text markup in XHTML, and dropping it left three lines of
    a legend in a heap in the top corner of a box built for five.
    """
    tool = next(t for t in _sketch_tools().tools if t.name == "Legend")
    words = _part(tool, "text")
    assert "LEGEND" in words["text"]
    assert words["text"].count("\n") >= 4, "the blank lines have gone"
    set_out = words["html"]
    assert "underline" in set_out and "bold" in set_out
    # The size is kept to every decimal, in points, and drawn at exactly that
    # many page units — not at the screen's dpi, which set every line a third
    # too big and broke a drawing title across two lines.
    assert "font-size:10.8654pt" in set_out
    item = build_item(words)
    run = item.doc.firstBlock().begin().fragment().charFormat()
    assert run.fontPointSize() == pytest.approx(10.8654)
    assert run.font().pixelSize() == 11
    assert run.fontLetterSpacing() == pytest.approx(100 * 10.8654 / 11, rel=1e-3)
    title = build_item(_part(next(t for t in _sketch_tools().tools
                                  if t.name == "Drawing Title"), "text"))
    title.doc.setTextWidth(title.text_rect().width())
    assert title.doc.firstBlock().layout().lineCount() == 1


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
    from markforge.items.shapes import SketchItem

    item = SketchItem([{"path": [["m", 0, 0], ["l", 10, 0], ["l", 10, 10], ["z"]],
                        "stroke": "#000000", "fill": "", "width": 1.0}])
    assert item.local_rect() == QRectF(0, 0, 10, 10)
    item.set_local_rect(QRectF(0, 0, 40, 20))
    assert item._transform()[:2] == (4.0, 2.0)


def test_a_drawing_survives_a_save(qapp):
    from markforge.items.shapes import SketchItem

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
    from markforge.items.shapes import PolyItem, RectItem

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


def test_a_section_marks_parts_are_assembled_not_scattered(qapp):
    """X and Y are the annotation's bottom-left, as PDF puts a Rect's origin.

    Read as the top instead, every part slid up by its own height: the two
    labels swapped halves of the bubble, the arrow came off it, and the heavy
    bar at the end of the cut line ended up a hundred points from the line.
    """
    from markforge.items.shapes import PolyItem, RectItem
    from markforge.items.text import TextItem

    marks = btx.read(os.path.join(HERE, "btx", "Structures - Sketch Tools.btx"))
    section = next(t for t in marks.tools if t.name == "Section")
    items = [build_item(p) for p in section.payloads]

    bubble = [i for i in items if isinstance(i, RectItem) and i.kind == "ellipse"]
    assert bubble, "a section mark has a bubble"
    circle = bubble[0].mapRectToParent(bubble[0].local_rect())

    labels = [i for i in items if isinstance(i, TextItem)]
    assert len(labels) == 2
    boxes = sorted((i.mapRectToParent(i.local_rect()) for i in labels),
                   key=lambda r: r.top())
    # Both labels sit inside the bubble, one above the middle and one below.
    for box in boxes:
        assert circle.adjusted(-2, -2, 2, 2).contains(box.center())
    assert boxes[0].center().y() < circle.center().y() < boxes[1].center().y()

    # The number is the upper one, the sheet reference the lower — as drawn.
    assert labels[boxes.index(boxes[0])] is not None
    upper = min(labels, key=lambda i: i.mapRectToParent(i.local_rect()).top())
    assert upper.text().strip() == "1"

    # The arrow overlaps the bubble rather than floating off on its own.
    arrows = [i for i in items if isinstance(i, PolyItem) and i.kind == "polygon"]
    assert arrows
    head = arrows[0].mapRectToParent(arrows[0].local_rect())
    assert head.intersects(circle)

    # And the heavy bar at the end of the cut is on the line, not adrift.
    bars = [i for i in items if isinstance(i, RectItem) and i.kind == "rect"]
    lines = [i for i in items if isinstance(i, PolyItem) and i.kind == "line"]
    assert bars and lines
    bar = bars[0].mapRectToParent(bars[0].local_rect())
    reach = None
    for line in lines:
        for point in (line.mapToParent(p) for p in line.points):
            gap = (point - bar.center()).manhattanLength()
            reach = gap if reach is None else min(reach, gap)
    assert reach < 30, f"the bar is {reach:.0f} points from any cut line"


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
# one to one with the reference sheet
#
# btx/Document1.pdf has Sketch Tools placed on it by Bluebeam. Each tool is
# rendered here and laid over Bluebeam's own appearance of the same
# annotations; the share of ink the two have in common is what is checked.
# ---------------------------------------------------------------------------

REFERENCE_PAIRS = [      # tool index, xrefs on page 1, least overlap
    (1, [19, 21, 23, 25, 28], 0.9),                          # Elevation
    (8, [117, 119, 121, 123, 125, 127, 129, 132], 0.9),      # Section
    (13, [43, 45, 49, 51], 0.6),                             # Legend
    (14, [53, 90, 93, 96, 99, 102, 105, 108, 111], 0.85),    # Titleblock
]


def _reference_ink(xrefs, zoom=6.0):
    import numpy as np
    import pymupdf

    doc = pymupdf.open(os.path.join(HERE, "btx", "Document1.pdf"))
    page = doc[0]
    doc.xref_set_key(page.xref, "Annots",
                     "[" + " ".join(f"{x} 0 R" for x in xrefs) + "]")
    page = doc.reload_page(page)
    box = None
    for annotation in page.annots():
        if not annotation.rect.is_empty:
            box = annotation.rect if box is None else box | annotation.rect
    for number in page.get_contents():
        doc.update_stream(number, b"")
    box = pymupdf.Rect(box) + (-6, -6, 6, 6)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=box, alpha=False)
    image = np.frombuffer(pixmap.samples, np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n)[:, :, :3]
    return image.min(axis=2) < 200


def _tool_ink(tool, zoom=6.0):
    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    items = [build_item(dict(p)) for p in tool.payloads]
    bound = None
    for item in items:
        placed = item.boundingRect().translated(item.pos())
        bound = placed if bound is None else bound.united(placed)
    bound = bound.adjusted(-6, -6, 6, 6)
    wide, high = int(bound.width() * zoom), int(bound.height() * zoom)
    image = QImage(wide, high, QImage.Format_RGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(zoom, zoom)
    painter.translate(-bound.left(), -bound.top())
    for item in sorted(items, key=lambda each: each.zValue()):
        painter.save()
        painter.translate(item.pos())
        item.paint_visible(painter)
        painter.restore()
    painter.end()
    pixels = np.frombuffer(image.constBits(), np.uint8).reshape(
        high, image.bytesPerLine() // 4, 4)[:, :wide, :3]
    return pixels.min(axis=2) < 200


def _overlap(first, second) -> float:
    """Share of ink in common, once the two are slid onto each other."""
    import numpy as np

    height = max(first.shape[0], second.shape[0]) * 2
    width = max(first.shape[1], second.shape[1]) * 2
    product = np.fft.irfft2(np.fft.rfft2(first.astype(float), (height, width))
                            * np.conj(np.fft.rfft2(second.astype(float), (height, width))),
                            (height, width))
    dy, dx = np.unravel_index(np.argmax(product), product.shape)
    dy = dy - height if dy > height // 2 else dy
    dx = dx - width if dx > width // 2 else dx
    canvas_h = height
    canvas_w = width
    a = np.zeros((canvas_h, canvas_w), bool)
    b = np.zeros((canvas_h, canvas_w), bool)
    oy, ox = canvas_h // 4, canvas_w // 4
    a[oy:oy + first.shape[0], ox:ox + first.shape[1]] = first
    b[oy + dy:oy + dy + second.shape[0], ox + dx:ox + dx + second.shape[1]] = second
    return (a & b).sum() / max((a | b).sum(), 1)


@pytest.mark.parametrize("index, xrefs, least", REFERENCE_PAIRS)
def test_sketch_tools_match_bluebeams_own_drawing(qapp, index, xrefs, least):
    tool = _sketch_tools().tools[index]
    assert _overlap(_reference_ink(xrefs), _tool_ink(tool)) >= least, tool.name


def test_bluebeam_line_spacing_is_exact(qapp):
    """line-height is Bluebeam's exact spacing, not Qt's minimum."""
    tool = _sketch_tools().tools[13]
    legend = build_item(dict(next(p for p in tool.payloads if p.get("type") == "text")))
    legend.doc.setTextWidth(200)
    first = legend.doc.firstBlock()
    assert first.blockFormat().lineHeight() == pytest.approx(12.495, abs=0.01)
    blocks = []
    block = first
    while block.isValid():
        blocks.append(block.layout().position().y())
        block = block.next()
    gaps = [b - a for a, b in zip(blocks, blocks[1:])]
    assert all(gap == pytest.approx(12.495, abs=0.05) for gap in gaps)


def test_a_title_block_stamp_comes_across_as_linework(qapp):
    """Its logo, labels and rules are vectors, not a picture of them."""
    tool = _sketch_tools().tools[14]
    stamp = tool.payloads[0]
    assert stamp.get("stamp_svg") and "<image" not in stamp["stamp_svg"]
    assert not stamp.get("stamp_picture")
    item = build_item(dict(stamp))
    again = build_item(item.serialize())
    assert again.stamp_svg == item.stamp_svg


# ---------------------------------------------------------------------------
# 2026-09-29: groups in groups, and Bluebeam's own keys
# ---------------------------------------------------------------------------

def _tool(file_name, pick):
    made = btx.read(os.path.join(HERE, "btx", file_name))
    return next(tool for tool in made.tools if pick(tool))


def test_a_section_mark_is_a_group_holding_a_bubble_group_and_a_cut_line_group():
    section = _sketch_tools().tools[6]
    paths = [tuple(p["group_path"]) for p in section.payloads]
    assert len({path[0] for path in paths}) == 1           # one outer group
    inner = {path[1] for path in paths if len(path) > 1}
    assert len(inner) == 2                                  # bubble and cut line
    kinds = {path[1]: [] for path in paths}
    for path, payload in zip(paths, section.payloads):
        kinds[path[1]].append(payload.get("kind") or payload["type"])
    assert sorted(len(v) for v in kinds.values()) == [2, 6]
    assert {p["group_title"] for p in section.payloads} == {"Section"}


def test_bluebeams_own_pdf_opens_with_its_groups_in_groups(qapp):
    from collections import Counter
    from markforge.io import pdfmarkups, pdfvector

    source = pdfvector.PdfFile.open(os.path.join(HERE, "btx", "Document1.pdf"))
    made = pdfmarkups.markups_of_page(source, 0)
    sections = Counter(tuple(p["group_path"]) for p in made
                       if p.get("group_title") == "Section")
    assert sorted(sections.values()) == [2, 2, 6, 6]        # two section marks
    assert {path[0] for path in sections} and all(len(p) == 2 for p in sections)


def test_curved_sides_come_in_as_bluebeam_draws_them():
    dhs = _tool("DHS Sections.btx", lambda t: t.name.startswith("DHS 200"))
    shape = build_item(dict(dhs.payloads[0]))
    assert len(shape.bezier) == 2
    path = shape.build_path()
    assert any(path.elementAt(i).type == path.elementAt(i).type.CurveToElement
               for i in range(path.elementCount()))


def test_a_bluebeam_line_style_keeps_its_dashes():
    grid = _tool("Strucutures - General.btx", lambda t: t.name == "Centre Line")
    style = grid.payloads[0]["style"]
    width = style["width"]
    assert [round(step * width, 3) for step in style["dash_array"]] == [32, 8, 8, 8]


def test_a_bluebeam_hatch_is_drawn_from_its_own_tile():
    slab = _tool("Structures - Steel.btx",
                 lambda t: any(p.get("style", {}).get("hatch_tile") for p in t.payloads))
    style = next(p["style"] for p in slab.payloads if p.get("style", {}).get("hatch_tile"))
    assert style["hatch_scale"] == pytest.approx(0.6)
    assert style["hatch_tile"]["step_x"] == pytest.approx(36)
    assert style["hatch_color"] == "#969696"
    item = build_item(dict(next(p for p in slab.payloads
                                if p.get("style", {}).get("hatch_tile"))))
    assert item.style.hatched()


def test_a_comment_box_is_filled_with_c_and_framed_in_the_da_colour():
    comment = _tool("Structures - Drawing Review.btx", lambda t: t.name == "Engineer Comment")
    box = next(p for p in comment.payloads if p["type"] == "callout")
    assert box["style"]["fill"] == "#00ffff"
    assert box["style"]["fill_opacity"] == pytest.approx(0.2)
    assert box["style"]["stroke"] == "#0080c0"
    leader = box["leaders"][0]
    assert leader["side"] == "left" and leader["reach"] == pytest.approx(15.8, abs=0.1)


def test_circled_text_is_a_circle_with_its_words_inside():
    grid = _tool("Strucutures - General.btx",
                 lambda t: any(p.get("style", {}).get("text_shape") == "circle"
                               for p in t.payloads))
    bubble = next(p for p in grid.payloads
                  if p.get("style", {}).get("text_shape") == "circle")
    left, top, right, bottom = bubble["style"]["text_margins"]
    assert left == pytest.approx(9.7066 + 4, abs=0.01)
    assert top == pytest.approx(7.4409 + 4, abs=0.01)


def test_a_rotated_stamp_whose_drawing_is_not_is_fitted_like_bluebeam():
    rhs = btx.read(os.path.join(HERE, "btx", "Structural Steel RHS Sections - 110 @ A1.btx"))
    payload = rhs.tools[47].payloads[0]
    xs = [v for s in payload["strokes"] for c in s["path"] for v in c[1::2]]
    ys = [v for s in payload["strokes"] for c in s["path"] for v in c[2::2]]
    assert max(xs) - min(xs) < max(ys) - min(ys)        # standing up, like its neighbours


def test_a_callouts_box_is_read_from_rd_in_bluebeams_order():
    comment = _tool("Structures - Drawing Review.btx", lambda t: t.name == "Engineer Comment")
    box = next(p for p in comment.payloads if p["type"] == "callout")
    left, top, width, height = box["rect"]
    knee_y = 39.82599 - 26.32611                          # /CL's knee, turned y-down
    assert top + height / 2 == pytest.approx(knee_y, abs=0.05)
