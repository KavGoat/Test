"""Data files: importData (SMath core, 1 to 9 arguments) and exportData.CSV
(SMath's data exchange plugin).  Relative file names are relative to the
worksheet's folder, as in SMath; the worksheet sets ``base_dir``."""
from __future__ import annotations

import csv
import io
import os
import re

from .builtins import fn
from .catalog import FUNCTIONS
from .errors import SMathError
from .values import Matrix, Q, String, need_scalar

base_dir = ""  # folder of the worksheet being calculated ("" = current folder)

FUNCTIONS.extend([
    ("exportData.CSV", 2, "Strings, Files",
     'exportData.CSV("1:matrix", "2:fileName") — Writes the matrix to a CSV file (comma separated, "." as '
     "decimal symbol). Returns 1 if successful."),
    ("exportData.CSV", 4, "Strings, Files",
     'exportData.CSV("1:matrix", "2:fileName", "3:delimiter", "4:delimiter") — Writes the matrix to a CSV file '
     'with the given decimal symbol ("3:delimiter") and column separator ("4:delimiter"). Returns 1 if successful.'),
])


def _path(name) -> str:
    if not isinstance(name, String):
        raise SMathError("Argument must be a string.", None)
    p = os.path.expanduser(name.text)
    return p if os.path.isabs(p) else os.path.join(base_dir or os.getcwd(), p)


def _text_arg(v, default: str) -> str:
    """A delimiter argument: a string, or 0 for SMath's built-in default."""
    if isinstance(v, String):
        return v.text or default
    q = need_scalar(v)
    if q.value == 0:
        return default
    raise SMathError("Argument must be a string.", None)


def _int_arg(v, default):
    q = need_scalar(v)
    n = int(round(q.real))
    return default if n == 0 else n


def _sniff(text: str, decimal: str) -> str:
    """The column separator of a data file: tab, ';', ',' (unless it is the
    decimal symbol) or runs of spaces."""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    for sep in ("\t", ";", ","):
        if sep in first and sep != decimal:
            return sep
    return " "


def _cell(s: str, decimal: str):
    t = s.strip().strip('"')
    if t == "":
        return String("")
    num = t.replace(decimal, ".") if decimal != "." else t
    try:
        return Q(float(num))
    except ValueError:
        return String(t)


def import_data(path: str, decimal: str = ".", argsep: str = ",", coldelim: str = "", r1=None, r2=None,
                c1=None, c2=None) -> Matrix:
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError:
        raise SMathError(f"File not found: {os.path.basename(path)}", None) from None
    sep = coldelim or _sniff(text, decimal)
    rows = []
    if sep == " ":
        for ln in text.splitlines():
            if ln.strip():
                rows.append(re.split(r"\s+", ln.strip()))
    else:
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=sep) if any(c.strip() for c in r)]
    if not rows:
        raise SMathError("File is empty.", None)
    r1 = max(1, r1 or 1)
    r2 = min(len(rows), r2 or len(rows))
    rows = rows[r1 - 1:r2]
    width = max(len(r) for r in rows)
    c1 = max(1, c1 or 1)
    c2 = min(width, c2 or width)
    if r2 < r1 or c2 < c1:
        raise SMathError("Matrix dimensions do not match.", None)
    items = []
    for r in rows:
        r = r + [""] * (width - len(r))  # ragged rows are padded
        items.extend(_cell(c, decimal) for c in r[c1 - 1:c2])
    return Matrix(len(rows), c2 - c1 + 1, items)


@fn("importData", -1)
def _import(*args):
    if not 1 <= len(args) <= 9:
        raise SMathError("Incorrect number of arguments.", None)
    a = list(args) + [Q(0.0)] * (9 - len(args))
    decimal = _text_arg(a[1], ".")
    argsep = _text_arg(a[2], ",")
    coldelim = _text_arg(a[3], "")
    return import_data(_path(a[0]), decimal, argsep, coldelim, _int_arg(a[4], None), _int_arg(a[5], None),
                       _int_arg(a[6], None), _int_arg(a[7], None))


def _fmt(v, decimal: str) -> str:
    if isinstance(v, String):
        return v.text
    q = need_scalar(v)
    x = q.value
    if isinstance(x, complex):
        if x.imag == 0:
            x = x.real
        else:
            return str(x).replace(".", decimal) if decimal != "." else str(x)
    s = repr(float(x))
    if s.endswith(".0"):
        s = s[:-2]
    return s.replace(".", decimal) if decimal != "." else s


def export_csv(m, path: str, decimal: str = ".", sep: str = ",") -> None:
    mm = m if isinstance(m, Matrix) else Matrix(1, 1, [m])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=sep)
        for i in range(mm.nrows):
            w.writerow([_fmt(mm.get(i, j), decimal) for j in range(mm.ncols)])


@fn("exportData.CSV", 2)
def _export2(m, name):
    try:
        export_csv(m, _path(name))
    except OSError:
        return Q(0.0)
    return Q(1.0)


@fn("exportData.CSV", 4)
def _export4(m, name, dec, sep):
    try:
        export_csv(m, _path(name), _text_arg(dec, "."), _text_arg(sep, ","))
    except OSError:
        return Q(0.0)
    return Q(1.0)
