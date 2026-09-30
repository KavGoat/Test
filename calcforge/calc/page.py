"""SMath's fields — ``\\[TITLE]\\``, ``\\[PAGENUM[0]]\\``, ``\\[DATE[…]]\\`` — and
their formats (SMath Studio's Insert > Field dialog).

CalcForge writes them into MarkForge's running header and footer as
``{title}``, ``{page:0001}``, ``{date:DD.MM.YYYY}`` (core/document.py uses
:func:`number_field` and :func:`date_text`). SMath's page model — paper,
margins, background picture, header and footer layers of regions — is not
here: MarkForge's page setup, header/footer and images replace it (phase 6).
The field functions stay, too, because WebSMath's drawing code
(ui/region_item.py, byte for byte) imports :func:`field_text`.
"""
from __future__ import annotations

import datetime
import re
from typing import Optional

# -- fields: \[NAME[args]]\ --------------------------------------------------------------
FIELD_RE = re.compile(r"^\\\[(?P<name>[A-Z]+)(?:\[(?P<arg>.*)\])?\]\\$", re.S)


def is_field(text: str) -> bool:
    return bool(FIELD_RE.match(text or ""))


def _unescape(s: str) -> str:
    # SMath writes special characters in field arguments as \XXXX\ (hex)
    return re.sub(r"\\([0-9A-Fa-f]{4})\\", lambda m: chr(int(m.group(1), 16)), s)


def date_text(fmt: str, now: datetime.datetime) -> str:
    """A date or time in SMath's format (DD.MM.YYYY, HH:mm …)."""
    return _date(fmt, now)


def _date(fmt: str, now: datetime.datetime) -> str:
    fmt = _unescape(fmt) if fmt else "DD.MM.YYYY"
    out, i = [], 0
    tokens = [("YYYY", "%Y"), ("YY", "%y"), ("MMMM", "%B"), ("MMM", "%b"), ("MM", "%m"), ("DD", "%d"),
              ("HH", "%H"), ("hh", "%I"), ("mm", "%M"), ("ss", "%S"), ("tt", "%p")]
    while i < len(fmt):
        for tok, code in tokens:
            if fmt.startswith(tok, i):
                out.append(now.strftime(code))
                i += len(tok)
                break
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


def field_text(raw: str, metadata: dict, page: int, count: int, filename: str = "",
               now: Optional[datetime.datetime] = None) -> str:
    """What a field shows on page `page` (1-based) of `count`."""
    m = FIELD_RE.match(raw or "")
    if not m:
        return raw
    name, arg = m.group("name"), m.group("arg")
    now = now or datetime.datetime.now()

    if name in ("PAGENUM", "COUNT"):
        return number_field(page if name == "PAGENUM" else count, _unescape(arg or ""))
    if name == "DATE":
        return _date(arg or "", now)
    if name == "TIME":
        return _date(arg or "HH:mm:ss", now)
    if name in ("FILENAME", "FILE"):
        return filename
    if name == "ID":
        return metadata.get("_id", "")
    if name == "REVISION":
        return metadata.get("_revision", "")
    return metadata.get(name.lower(), "")


def number_field(n: int, fmt: str) -> str:
    """Page number / page count with SMath's Format: an offset added to the
    number ("-1" -> page 1 shows 0, "22" -> 23), and leading zeros give the
    width ("0001" -> 0002)."""
    fmt = (fmt or "").strip()
    try:
        off = int(fmt) if fmt else 0
    except ValueError:
        return str(n)
    v = n + off
    digits = fmt.lstrip("+-")
    if len(digits) > 1 and digits.startswith("0"):
        return ("-" if v < 0 else "") + str(abs(v)).zfill(len(digits))
    return str(v)


def escape_arg(s: str) -> str:
    """Field argument as SMath stores it: characters other than letters and
    digits written as \\XXXX\\ (hex code), e.g. "." -> \\002E\\."""
    return "".join(c if c.isalnum() else f"\\{ord(c):04X}\\" for c in s)


def make_field(name: str, fmt: str = "") -> str:
    """The operand SMath stores for a field: \\[NAME]\\ or \\[NAME[format]]\\."""
    if fmt == "" and name not in ("PAGENUM", "COUNT"):
        return f"\\[{name}]\\"
    return f"\\[{name}[{escape_arg(fmt) if name in ('DATE', 'TIME') else fmt}]]\\"


# The fields of SMath Studio's Insert > Field dialog: (label, command, default format, format choices)
AVAILABLE_FIELDS = [
    ("Worksheet Id", "ID", "", []),
    ("Worksheet revision", "REVISION", "", []),
    ("File name", "FILENAME", "", []),
    ("Current date", "DATE", "DD.MM.YYYY", ["DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD",
                                            "DD MMMM YYYY", "MMMM DD, YYYY", "DD.MM.YY"]),
    ("Current time", "TIME", "HH:mm:ss", ["HH:mm:ss", "HH:mm", "hh:mm tt"]),
    ("Number of pages", "COUNT", "0", ["0", "-1", "1"]),
    ("Current page index", "PAGENUM", "0", ["0", "-1", "1", "0000"]),
    ("Author", "AUTHOR", "", []),
    ("Company", "COMPANY", "", []),
    ("Keywords", "KEYWORDS", "", []),
    ("Title", "TITLE", "", []),
    ("Description", "DESCRIPTION", "", []),
]
