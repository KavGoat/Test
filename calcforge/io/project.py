"""Project file I/O — save/load .cfx files (zip of JSON + assets)."""
from __future__ import annotations

import json
import os
import zipfile
from typing import Optional

from ..core.document import Document


def save_project(doc: Document, path: str):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        data = doc.to_dict()
        zf.writestr("document.json", json.dumps(data, indent=2, ensure_ascii=False))


def load_project(path: str) -> Document:
    with zipfile.ZipFile(path, 'r') as zf:
        with zf.open("document.json") as f:
            data = json.loads(f.read())
    return Document.from_dict(data)
