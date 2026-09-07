"""The PDF engine: reading a file apart, and putting things back into it.

Modelled on PDF4QT's, and tested against real files from two other projects'
corpora rather than only against what this application writes — a reader that
only reads its own output is not a reader.
"""
import glob
import os

import pytest

from markforge.pdf import annotations, filters, lexer, reader, writer
from markforge.pdf.objects import Name, Ref, Stream
from markforge.pdf.storage import ObjectStorage

CORPUS = sorted(
    glob.glob("/home/user/stirling-tools/stirling-pdf/testing/**/*.pdf",
              recursive=True))


# ---------------------------------------------------------------------------
# Reading the syntax
# ---------------------------------------------------------------------------

def test_the_eight_kinds_of_object_read_back_as_themselves():
    read = lambda src: lexer.read_object(src)[0]
    assert read(b"null") is None
    assert read(b"true") is True
    assert read(b"-4") == -4
    assert read(b"3.25") == 3.25
    assert read(b"/Square") == Name("Square")
    assert read(b"(words)") == b"words"
    assert read(b"[1 /A]") == [1, Name("A")]
    assert read(b"<< /K 2 >>") == {"K": 2}


def test_a_name_may_be_written_with_escapes():
    """``/A#20name`` is one name with a space in it."""
    assert lexer.read_object(b"/A#20name")[0] == Name("A name")


def test_a_string_may_nest_its_own_brackets():
    assert lexer.read_object(rb"(a \(nested\) string)")[0] == b"a (nested) string"


def test_an_octal_escape_is_one_character():
    assert lexer.read_object(rb"(\101\102)")[0] == b"AB"


def test_a_hex_string_pads_an_odd_tail():
    assert lexer.read_object(b"<48656C6C6F>")[0] == b"Hello"
    assert lexer.read_object(b"<414>")[0] == b"A@"


def test_a_reference_is_not_two_numbers():
    """``12 0 R`` is one object; ``12 0`` in an array is two."""
    assert lexer.read_object(b"12 0 R")[0] == Ref(12, 0)
    assert lexer.read_object(b"[12 0]")[0] == [12, 0]


def test_a_stream_takes_its_length_from_the_dictionary():
    src = b"<< /Length 5 >>\nstream\nHELLO\nendstream"
    found = lexer.read_object(src)[0]
    assert isinstance(found, Stream)
    assert found.raw == b"HELLO"


def test_a_stream_with_a_wrong_length_is_still_read():
    """Files in the wild lie about it, and the data is still there."""
    src = b"<< /Length 900 >>\nstream\nHELLO\nendstream"
    assert lexer.read_object(src)[0].raw == b"HELLO"


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def test_the_filters_undo_what_they_are_named_for():
    import zlib

    assert filters.decode(Stream({"Filter": Name("FlateDecode")},
                                 zlib.compress(b"hello"))) == b"hello"
    assert filters.decode(Stream({"Filter": Name("ASCIIHexDecode")},
                                 b"48656C6C6F>")) == b"Hello"
    assert filters.decode(Stream({"Filter": Name("RunLengthDecode")},
                                 bytes([2]) + b"abc" + bytes([254]) + b"z"
                                 + bytes([128]))) == b"abczzz"


def test_a_truncated_flate_stream_gives_back_what_it_can():
    """A drawing that is nearly all there beats an exception."""
    import zlib

    whole = zlib.compress(b"x" * 500)
    assert filters.decode(Stream({"Filter": Name("FlateDecode")},
                                 whole[:-4])) != b""


# ---------------------------------------------------------------------------
# Following references
# ---------------------------------------------------------------------------

def test_a_reference_chain_resolves_to_the_thing_at_the_end():
    store = ObjectStorage({1: Ref(2), 2: Ref(3), 3: {"W": 595}})
    assert store.number(Ref(1), "W") == 595


def test_a_reference_loop_is_not_followed_for_ever():
    store = ObjectStorage({1: Ref(2), 2: Ref(1)})
    assert store.resolve(Ref(1)) is None


# ---------------------------------------------------------------------------
# Real files
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not CORPUS, reason="no corpus of real PDFs here")
@pytest.mark.parametrize("path", CORPUS[:10], ids=os.path.basename)
def test_a_real_pdf_comes_apart_into_its_pages(path):
    store = reader.read_file(path)
    pages = store.get(store.trailer.get("Root"), "Pages")
    kids = store.get(pages, "Kids") or []
    assert kids, "a file with no pages is not one this read properly"
    first = store.resolve(kids[0])
    assert "MediaBox" in first or "Parent" in first


def test_a_file_that_is_not_a_pdf_is_refused():
    with pytest.raises(reader.ReadError):
        reader.read(b"<!DOCTYPE html>\n<html>not a drawing</html>")


def test_a_file_with_a_broken_cross_reference_is_read_by_scanning():
    """A damaged drawing that opens is worth more than a correct refusal."""
    body = (b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>\nendobj\n"
            b"startxref\n999999\n%%EOF\n")          # an offset that goes nowhere
    store = reader.read(body)
    kids = store.get(store.get(store.trailer.get("Root"), "Pages"), "Kids")
    assert store.numbers(kids[0], "MediaBox") == [0, 0, 595, 842]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def test_an_object_is_written_the_way_a_pdf_writes_one():
    written = writer.serialize({"Type": Name("Annot"), "Rect": [1, 2.5],
                                "P": Ref(7), "T": b"a (name)"})
    assert b"/Type /Annot" in written
    assert b"/Rect [1 2.5]" in written
    assert b"/P 7 0 R" in written
    assert rb"(a \(name\))" in written


@pytest.mark.skipif(not CORPUS, reason="no corpus of real PDFs here")
def test_adding_a_markup_leaves_every_original_byte_alone():
    """An incremental update is the only honest way to add to somebody's file."""
    path = CORPUS[0]
    raw = open(path, "rb").read()
    store = reader.read(raw)
    kids = store.get(store.get(store.trailer.get("Root"), "Pages"), "Kids")
    page_ref = kids[0]

    number = store.next_number()
    cloud = annotations.Annotation(
        subtype="Square", rect=(72.0, 500.0, 300.0, 620.0),
        author="MarkForge", contents="a cloud",
        border_effect=annotations.BorderEffect(True, 2.0))
    page = dict(store.resolve(page_ref))
    page["Annots"] = list(store.get(page_ref, "Annots") or []) + [Ref(number)]
    updated = writer.incremental_update(raw, {
        number: annotations.write(cloud, page_ref),
        page_ref.number: page})

    assert updated[:len(raw)] == raw, "the drawing that came in is untouched"
    assert len(updated) - len(raw) < 2000, "and what was added is small"

    back = reader.read(updated)
    kids = back.get(back.get(back.trailer.get("Root"), "Pages"), "Kids")
    found = annotations.on_page(back, kids[0])
    assert [a.subtype for a in found] == ["Square"]
    assert found[0].is_cloud
    assert found[0].author == "MarkForge"


@pytest.mark.skipif(not CORPUS, reason="no corpus of real PDFs here")
def test_what_we_write_is_readable_by_other_readers():
    from pypdf import PdfReader

    path = CORPUS[0]
    raw = open(path, "rb").read()
    store = reader.read(raw)
    kids = store.get(store.get(store.trailer.get("Root"), "Pages"), "Kids")
    page_ref = kids[0]
    number = store.next_number()
    cloud = annotations.Annotation(subtype="Square", rect=(72.0, 500.0, 300.0, 620.0),
                                   border_effect=annotations.BorderEffect(True, 2.0))
    page = dict(store.resolve(page_ref))
    page["Annots"] = list(store.get(page_ref, "Annots") or []) + [Ref(number)]
    out = writer.incremental_update(raw, {number: annotations.write(cloud, page_ref),
                                          page_ref.number: page})
    written = os.path.join(os.path.dirname(path), "..", "written.pdf")
    import tempfile
    written = os.path.join(tempfile.mkdtemp(), "written.pdf")
    open(written, "wb").write(out)

    theirs = PdfReader(written)
    mark = theirs.pages[0]["/Annots"][-1].get_object()
    assert str(mark["/Subtype"]) == "/Square"
    assert str(mark["/BE"]["/S"]) == "/C"


# ---------------------------------------------------------------------------
# The annotation model
# ---------------------------------------------------------------------------

def test_a_cloud_is_a_border_effect_and_comes_back_as_one():
    store = ObjectStorage({1: {"Subtype": Name("Square"),
                               "Rect": [0, 0, 10, 10],
                               "BE": {"S": Name("C"), "I": 2}}})
    found = annotations.read(store, Ref(1))
    assert found.is_cloud and found.border_effect.intensity == 2


def test_a_call_out_keeps_its_knee():
    store = ObjectStorage({1: {"Subtype": Name("FreeText"),
                               "Rect": [0, 0, 10, 10],
                               "IT": Name("FreeTextCallout"),
                               "CL": [1, 2, 3, 4, 5, 6]}})
    found = annotations.read(store, Ref(1))
    assert found.callout.hinged
    assert found.callout.points == [(1, 2), (3, 4), (5, 6)]


def test_a_dimension_keeps_every_part_the_specification_names():
    store = ObjectStorage({1: {"Subtype": Name("Line"), "Rect": [0, 0, 10, 10],
                               "IT": Name("LineDimension"),
                               "L": [0, 0, 100, 0], "LL": 30, "LLE": 4, "LLO": 2,
                               "Cap": True, "CP": Name("Inline"), "CO": [5, -6]}})
    found = annotations.read(store, Ref(1))
    assert found.is_dimension
    assert (found.leader_length, found.leader_extension, found.leader_offset) \
        == (30, 4, 2)
    assert found.caption and found.caption_inline
    assert found.caption_offset == (5, -6)


def test_a_measurement_carries_the_scale_it_was_taken_against():
    written = annotations.write(annotations.Annotation(
        subtype="Polygon", intent="PolygonDimension",
        measure=annotations.Measure("1:100", "m", 35.2778)), Ref(1))
    store = ObjectStorage({1: written})
    found = annotations.read(store, Ref(1))
    assert found.measure.ratio == "1:100"
    assert found.measure.unit == "m"
    assert round(found.measure.per_point, 3) == 35.278


def test_a_colour_reads_the_same_whichever_space_it_was_written_in():
    grey = ObjectStorage({1: {"Subtype": Name("Square"), "C": [0.5]}})
    assert annotations.read(grey, Ref(1)).stroke == (0.5, 0.5, 0.5)
    rgb = ObjectStorage({1: {"Subtype": Name("Square"), "C": [1, 0, 0]}})
    assert annotations.read(rgb, Ref(1)).stroke == (1, 0, 0)
    cmyk = ObjectStorage({1: {"Subtype": Name("Square"), "C": [0, 1, 1, 0]}})
    assert annotations.read(cmyk, Ref(1)).stroke == (1, 0, 0)


def test_a_link_is_not_somebody_s_markup():
    store = ObjectStorage({1: {"Subtype": Name("Link"), "Rect": [0, 0, 5, 5]}})
    assert not annotations.read(store, Ref(1)).is_markup
