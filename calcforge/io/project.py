"""Reading and writing ``.cfx`` project files (a zip of JSON plus assets)."""
from __future__ import annotations

import json
import os
import zipfile

DOCUMENT_ENTRY = "document.json"
ASSET_PREFIX = "assets/"
EXTENSION = ".cfx"
FILTER = "CalcForge documents (*.cfx);;All files (*)"


def save_document(document, path: str, enforce_extension: bool = True) -> None:
    """Write *document* to *path* atomically.

    Recovery copies are written beside the document as ``…​.cfx.autosave``, so
    they pass *enforce_extension* False to keep the name they were given.
    """
    if enforce_extension and not path.lower().endswith(EXTENSION):
        path += EXTENSION
    used: set[str] = set()
    for page in document.pages:
        if page.scene is not None:
            used |= page.scene.assets_used()
        elif page.background_key:
            used.add(page.background_key)
    document.prune_assets(used)

    payload = json.dumps(document.to_dict(), indent=1, ensure_ascii=False)
    temporary = path + ".tmp"
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DOCUMENT_ENTRY, payload)
        for key, data in document.assets.items():
            archive.writestr(ASSET_PREFIX + key, data)
    os.replace(temporary, path)
    document.path = path
    document.modified = False


def load_document(document, path: str) -> None:
    """Populate *document* from the project file at *path*."""
    with zipfile.ZipFile(path, "r") as archive:
        payload = json.loads(archive.read(DOCUMENT_ENTRY).decode("utf-8"))
        assets = {}
        for entry in archive.namelist():
            if entry.startswith(ASSET_PREFIX) and not entry.endswith("/"):
                assets[entry[len(ASSET_PREFIX):]] = archive.read(entry)
    document.assets = assets
    document.load_dict(payload)
    document.path = path
    document.modified = False


def describe(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]
