"""Opening and saving documents.

A saved document is a PDF (see :mod:`calcforge.io.pdfbase`). ``.cfx`` names one
that carries calculations; ``.pdf`` names one that does not. Both are the same
kind of file, and documents written before that was true — a zip of JSON and
assets — still open.
"""
from __future__ import annotations

import json
import os
import zipfile

from . import pdfbase

DOCUMENT_ENTRY = pdfbase.DOCUMENT_ENTRY
ASSET_PREFIX = pdfbase.ASSET_PREFIX
EXTENSION = ".cfx"
PLAIN_EXTENSION = ".pdf"
FILTER = ("Documents (*.cfx *.pdf);;Documents with calculations (*.cfx);;"
          "PDF documents (*.pdf);;All files (*)")


def intended_extension(document) -> str:
    """``.cfx`` once there is a calculation in it, ``.pdf`` while there is not."""
    return EXTENSION if pdfbase.has_calculations(document) else PLAIN_EXTENSION


def named_for_what_it_holds(document, path: str) -> str:
    """*path* with the extension the document has earned.

    A document with no calculations keeps whatever it is called — renaming
    somebody's ``.cfx`` because they deleted the last calculation out of it
    would be a surprise nobody asked for. A document that has gained one is
    written as ``.cfx``, because there is now a layer in it that only ``.cfx``
    promises is there.
    """
    stem, suffix = os.path.splitext(path)
    known = suffix.lower() in (EXTENSION, PLAIN_EXTENSION)
    wanted = intended_extension(document)
    if not known:
        return path + wanted
    if wanted == EXTENSION and suffix.lower() != EXTENSION:
        return stem + EXTENSION
    return path


def suggested_name(document) -> str:
    """What Save-as should offer: the document's name, named for what it holds."""
    stem = document.title or "document"
    if document.path:
        stem = os.path.splitext(document.path)[0]
    return stem + intended_extension(document)


def assets_in_use(document) -> set[str]:
    """Every asset something still refers to.

    The logo belongs to no page, so it has to be spoken for here or the tidy-up
    on save would throw it away the first time.
    """
    used: set[str] = set()
    if document.settings.logo_key:
        used.add(document.settings.logo_key)
    for page in document.pages:
        if page.frame is not None:
            used |= page.frame.assets_used()
        else:
            if page.background_key:
                used.add(page.background_key)
            if page.pdf_key:
                used.add(page.pdf_key)
    return used


def save_document(document, path: str, enforce_extension: bool = True,
                  appearance: bool = True) -> None:
    """Write *document* to *path* atomically, as a PDF.

    The name follows what is in the document: a marked-up drawing set is a PDF
    and keeps that name, and the moment there is a calculation in it the same
    file is written as ``.cfx`` instead. Nothing about the bytes changes — the
    name is only saying whether there is a calculation layer to come back to.

    Recovery copies are written beside the document as ``….cfx.autosave``, so
    they pass *enforce_extension* False to keep the name they were given, and
    *appearance* False because nothing but CalcForge ever reads them.
    """
    if enforce_extension:
        path = named_for_what_it_holds(document, path)
    document.prune_assets(assets_in_use(document))
    pdfbase.write(document, path, appearance=appearance)
    document.path = path
    document.modified = False


def load_document(document, path: str) -> None:
    """Populate *document* from the file at *path*."""
    if pdfbase.read(document, path):
        return
    if pdfbase.is_pdf(path):
        raise OSError("That PDF holds no CalcForge document — open it instead")
    _load_the_old_zip(document, path)
    document.path = path
    document.modified = False


def carries_a_document(path: str) -> bool:
    """Whether opening this file restores a document rather than importing one."""
    if pdfbase.is_pdf(path):
        return pdfbase.layer_in(path) is not None
    return zipfile.is_zipfile(path)


def _load_the_old_zip(document, path: str) -> None:
    """Documents written before the format was a PDF."""
    with zipfile.ZipFile(path, "r") as archive:
        payload = json.loads(archive.read(DOCUMENT_ENTRY).decode("utf-8"))
        assets = {}
        for entry in archive.namelist():
            if entry.startswith(ASSET_PREFIX) and not entry.endswith("/"):
                assets[entry[len(ASSET_PREFIX):]] = archive.read(entry)
    document.assets = assets
    document.load_dict(payload)


def describe(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]
