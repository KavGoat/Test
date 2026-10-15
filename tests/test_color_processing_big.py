"""Color Processing on a big drawing (the user, 2026-10-15: "colour change on
a really big PDF only one page it's froze the whole thing crashed the whole
app"; the page's list should hold only that page's colours, be very fast,
and a colour already chosen as a Source Color leaves the other rows' list)."""
from __future__ import annotations

import random
import time

import pymupdf

from calcforge.io import colorjobs, colorproc
from calcforge.io.colorproc import Process


def _big_page(lines: int = 120_000) -> bytes:
    random.seed(4)
    parts = []
    colours = [b"1 0 0 RG", b"0 0 1 RG", b"0 G", b"0 0 0 1 K", b"(paren (nested) ) Tj"]
    for n in range(lines):
        if n % 40 == 0:
            parts.append(random.choice(colours[:4]))
        x, y = random.uniform(0, 800), random.uniform(0, 600)
        parts.append(b"%.2f %.2f m %.2f %.2f l S" % (x, y, x + 9, y + 7))
    pdf = pymupdf.open()
    page = pdf.new_page(width=842, height=595)
    xref = pdf.get_new_xref()
    pdf.update_object(xref, "<<>>")
    pdf.update_stream(xref, b"0.4 w\n" + b"\n".join(parts))
    page.set_contents(xref)
    data = pdf.tobytes(deflate=True)
    pdf.close()
    return data


def test_a_big_drawing_lists_and_changes_its_colours_in_moments():
    data = _big_page()
    started = time.monotonic()
    found = colorproc.colours_in_pdf(data, 0)
    listed = time.monotonic() - started
    assert found == ["#000000", "#0000ff", "#ff0000"]
    started = time.monotonic()
    out = colorproc.process_pdf(data, [0], Process(pairs=[("#ff0000", "#00aa00")]))
    changed = time.monotonic() - started
    assert colorproc.colours_in_pdf(out, 0) == ["#000000", "#0000ff", "#00aa00"]
    # about 4 MB of line work: it took 8 s byte by byte; now well under one
    assert listed < 3.0 and changed < 4.0, (listed, changed)


def test_strings_inline_images_and_comments_are_not_read_as_colours():
    stream = (b"q 1 0 0 rg (1 0 0 rg (nested) 0 1 0 rg) Tj % 0 0 1 rg\n"
              b"BI /W 1 /H 1 /CS /RGB /BPC 8 ID \x00\xff\x00 EI\n"
              b"0 0 1 RG 5 5 m 9 9 l S Q")
    seen: set = set()
    colorproc.rewrite_stream(stream, {}, lambda c: c, seen)
    assert seen == {"#ff0000", "#0000ff"}
    out = colorproc.rewrite_stream(stream, {}, lambda c: (0.0, 1.0, 0.0) if c == (1.0, 0, 0) else c)
    assert out.startswith(b"q 0 1 0 rg (1 0 0 rg (nested) 0 1 0 rg) Tj % 0 0 1 rg")
    assert b"\x00\xff\x00 EI" in out


def test_only_the_colours_this_page_draws_are_listed():
    """A set's pages often share one resources dictionary: the forms named
    there that another page draws are not this page's colours."""
    doc = pymupdf.open()
    for colour in ((1, 0, 0), (0, 0, 1)):
        source = pymupdf.open()
        source.new_page().draw_rect(pymupdf.Rect(10, 10, 50, 50), color=colour)
        page = doc.new_page()
        page.show_pdf_page(page.rect, source, 0)
    first, second = doc[0], doc[1]
    other = second.get_xobjects()[0][0]
    kind, value = doc.xref_get_key(first.xref, "Resources")
    holder, path = (int(value.split()[0]), "XObject") if kind == "xref" \
        else (first.xref, "Resources/XObject")
    kind, value = doc.xref_get_key(holder, path)
    if kind == "xref":
        holder, path = int(value.split()[0]), ""
    doc.xref_set_key(holder, (path + "/" if path else "") + "Other", f"{other} 0 R")
    data = doc.tobytes()
    assert colorproc.colours_in_pdf(data, 0) == ["#ff0000"]
    assert colorproc.colours_in_pdf(data, 1) == ["#0000ff"]


def test_the_work_is_done_off_the_window_and_comes_back(qapp):
    data = _big_page(2000)
    future = colorjobs.submit(colorjobs.colours, data, 0)
    assert colorjobs.wait(future) == ["#000000", "#0000ff", "#ff0000"]
    raw = colorjobs.wait(colorjobs.submit(colorjobs.preview, data, Process(pairs=[("#ff0000", None)])))
    width, height, stride, samples = raw
    assert width == 200 and len(samples) == stride * height


def test_a_chosen_source_colour_leaves_the_other_rows_list(window, monkeypatch):
    from calcforge.ui import colorpicker, colorprocess
    dialog = colorprocess.ColorProcessingDialog(window, colorprocess.PAGES,
                                                document=window.document,
                                                colours=["#000000", "#ff0000", "#0000ff"])
    dialog.pairs[0][1].set("#ff0000")
    dialog.add_pair()
    offered = []
    monkeypatch.setattr(colorpicker, "choose_found",
                        lambda _anchor, colours, _current=None: offered.append(colours) or None)
    dialog.pairs[1][1]._pick()
    assert offered[-1] == ["#000000", "#0000ff"]
    dialog.pairs[0][1]._pick()
    assert "#ff0000" in offered[-1], "its own colour stays in its own list"
