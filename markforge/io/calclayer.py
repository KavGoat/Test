"""CalcForge's own drawing in a saved file, and taking it off again.

A saved document is a PDF that any reader opens (decision 3). Two things are
drawn into each page as page content rather than as annotations:

- the **sheet** — the paper of a page written on here, its running header and
  footer, anything flattened into it: what MarkForge always painted;
- the **calc layer** — the equations, plots and matrices, as vector drawing
  and real text, so another reader shows them, searches them and prints them,
  but cannot move, edit or delete them, and never lists them as markups.

Each goes in as its own content stream appended after the page's own, which
is never changed, invoking one form XObject. Both the stream and the form
carry ``/CalcForge /Sheet`` or ``/CalcForge /Calc`` — a private key, which
readers ignore — and the page itself carries ``/CalcForgePage`` with the
page's uid, so pages can be followed through a reorder or a deletion done
elsewhere.

Opening the file here again takes both layers off, which gives back exactly
the page as it was before CalcForge drew on it: that stripped page is the
page's source from then on, so the file never needs a second copy of itself
inside its record, and saving it again cannot make it grow.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from ..pdf import engine

KEY = "CalcForge"
PAGE_KEY = "CalcForgePage"
SHEET = "Sheet"
CALC = "Calc"


# -- writing ------------------------------------------------------------------
def mark_page(document, index: int, uid: str) -> None:
    """Say on the page which of the record's pages it is."""
    page = document[index]
    document.xref_set_key(page.xref, PAGE_KEY, _pdf_string(uid))


def place_layer(document, index: int, overlay, overlay_index: int,
                kind: str) -> Optional[str]:
    """Draw page *overlay_index* of *overlay* over page *index*, tagged *kind*.

    Returns a fingerprint of what was drawn (see :func:`layer_print`), or
    None when nothing could be placed.
    """
    page = document[index]
    before = set(page.get_contents())
    names_before = {entry[1] for entry in page.get_xobjects() if entry[2] == 0}
    try:
        page.show_pdf_page(page.rect, overlay, overlay_index, overlay=True)
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return None
    for xref in page.get_contents():
        if xref not in before:
            document.xref_set_key(xref, KEY, "/" + kind)
    for xref, name, invoker, _box in page.get_xobjects():
        if invoker == 0 and name not in names_before:
            document.xref_set_key(xref, KEY, "/" + kind)
    return layer_print(document, index, kind)


def layer_print(document, index: int, kind: str) -> Optional[str]:
    """A fingerprint of the page's *kind* layer, or None if it has none.

    Over the drawing streams themselves — the tagged form and the forms it
    draws — decompressed, so writing the file out again does not change it but
    any edit to the drawing does.
    """
    page = document[index]
    entries = page.get_xobjects()
    tagged = [xref for xref, _name, invoker, _box in entries
              if invoker == 0 and _tag(document, xref) == kind]
    if not tagged:
        return None
    digest = hashlib.sha256()
    for top in tagged:
        for xref in [top] + [x for x, _n, invoker, _b in entries if invoker == top]:
            try:
                digest.update(document.xref_stream(xref) or b"")
            except Exception:                          # noqa: BLE001
                engine.drain_messages()
    return digest.hexdigest()


# -- reading ------------------------------------------------------------------
def page_uid(document, index: int) -> str:
    page = document[index]
    kind, value = document.xref_get_key(page.xref, PAGE_KEY)
    if kind != "string":
        return ""
    return value


def has_layers(document) -> bool:
    """Whether any page carries CalcForge's drawing or its page mark."""
    for index in range(document.page_count):
        if page_uid(document, index):
            return True
        for xref, _name, invoker, _box in document[index].get_xobjects():
            if invoker == 0 and _tag(document, xref):
                return True
    return False


def strip(document, index: int) -> bool:
    """Take CalcForge's layers off page *index*. Says whether any were found.

    The appended streams go from the page's contents and the forms go from its
    resources, so nothing is left to be carried into the next save. A reader
    that rewrote the page into one stream is handled too: the invocations of
    the tagged forms are cut out of it.
    """
    page = document[index]
    tagged = {name: xref for xref, name, invoker, _box in page.get_xobjects()
              if invoker == 0 and _tag(document, xref)}
    contents = page.get_contents()
    kept = []
    found = False
    for xref in contents:
        if _tag(document, xref):
            found = True
            continue
        if tagged:
            data = document.xref_stream(xref) or b""
            cut = data
            for name in tagged:
                named = re.escape(name.encode())
                cut = re.sub(rb"q\s+(?:[-+\d.eE\s]+cm\s+)?/" + named + rb"\s+Do\s+Q",
                             b"", cut)
                cut = re.sub(rb"/" + named + rb"\s+Do\b", b"", cut)
            if cut != data:
                found = True
                if not cut.strip():
                    continue
                document.update_stream(xref, cut)
        kept.append(xref)
    if kept != contents:
        document.xref_set_key(page.xref, "Contents",
                              "[" + " ".join(f"{x} 0 R" for x in kept) + "]")
    if tagged:
        found = True
        holder, prefix = _xobjects_of(document, page)
        for name in tagged:
            document.xref_set_key(holder, prefix + name, "null")
    return found


def _xobjects_of(document, page) -> tuple[int, str]:
    """Where the page's /XObject dictionary is: an object, and a key path."""
    holder, prefix = page.xref, "Resources/"
    kind, value = document.xref_get_key(holder, "Resources")
    if kind == "xref":
        holder, prefix = int(value.split()[0]), ""
    kind, value = document.xref_get_key(holder, prefix + "XObject")
    if kind == "xref":
        return int(value.split()[0]), ""
    return holder, prefix + "XObject/"


def _tag(document, xref: int) -> str:
    try:
        kind, value = document.xref_get_key(xref, KEY)
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return ""
    if kind != "name":
        return ""
    return value.lstrip("/")


def _pdf_string(text: str) -> str:
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


# -- signatures ---------------------------------------------------------------
def is_signed(document) -> bool:
    """Whether the file carries a digital signature over its bytes: a /Sig
    field whose value has a /ByteRange."""
    for xref in range(1, document.xref_length()):
        try:
            kind, value = document.xref_get_key(xref, "FT")
            if kind != "name" or value != "/Sig":
                continue
            vkind, vvalue = document.xref_get_key(xref, "V")
            if vkind == "xref":
                number = int(vvalue.split()[0])
                if document.xref_get_key(number, "ByteRange")[0] == "array":
                    return True
            elif vkind == "dict" and "/ByteRange" in vvalue:
                return True
        except Exception:                              # noqa: BLE001
            engine.drain_messages()
    return False


# -- annotations ---------------------------------------------------------------
def annotation_print(document, xref: int) -> str:
    """What an annotation is, independent of its object number: how a markup
    that is still somebody else's annotation is found again in the saved file,
    whose objects are numbered afresh."""
    parts = []
    for key in ("Subtype", "Rect", "NM", "M", "Contents"):
        try:
            kind, value = document.xref_get_key(xref, key)
        except Exception:                              # noqa: BLE001
            engine.drain_messages()
            kind, value = "null", ""
        if key == "Rect" and kind == "array":
            try:
                value = " ".join(f"{float(v):.2f}"
                                 for v in value.strip("[] ").split())
            except ValueError:
                pass
        parts.append(f"{key}={value}")
    return hashlib.sha1("\n".join(parts).encode("utf-8", "replace")).hexdigest()
