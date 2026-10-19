"""Data files: importData (SMath core, 1 to 9 arguments), whose relative file
names are relative to the worksheet's folder, as in SMath (the worksheet sets
``base_dir``); and SMath's wfile, rfile and dfile, which keep values in a data
folder of the application's own (below)."""
from __future__ import annotations

import csv
import io
import math
import os
import re

from .builtins import fn
from .errors import SMathError
from .values import Matrix, Q, String, need_scalar

base_dir = ""  # folder of the worksheet being calculated ("" = current folder)



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


# ---------------------------------------------------------------------------
# wfile / rfile / dfile: SMath's own data files
# ---------------------------------------------------------------------------
# SMath Studio keeps these in one folder of its own, "user" in its settings
# folder, whatever worksheet calls them, so one worksheet can leave a result
# for another (read from SMath's SpecialFunctions plugin).  CalcForge does the
# same in its application data folder.  An equation can only name a file in
# that folder - never a path - so a worksheet from someone else cannot read,
# write or delete anything else on the computer.

data_folder = ""     # tests and tools may point it elsewhere; "" = the usual place
writing_allowed = True  # False while an equation is being typed (see Worksheet._evaluate)


def user_data_folder() -> str:
    """The folder wfile, rfile and dfile work in (made when first needed)."""
    folder = data_folder
    if not folder:
        from PySide6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
            os.path.join(os.path.expanduser("~"), ".calcforge")
        folder = os.path.join(base, "user")
    os.makedirs(folder, exist_ok=True)
    return folder


def _data_file(name) -> str:
    if not isinstance(name, String):
        raise SMathError("Argument must be a string.", None)
    text = name.text.strip()
    if not text or text in (".", "..") or os.path.isabs(text) or any(c in text for c in "/\\:"):
        raise SMathError("A file name only: rfile, wfile and dfile use CalcForge's data folder.", None)
    return os.path.join(user_data_folder(), text)


def _number_text(x: float) -> str:
    if math.isinf(x):
        return "∞" if x > 0 else "-∞"
    if x != x:
        raise SMathError("Cannot evaluate.", None)
    s = repr(float(x))
    if "e" in s:
        mant, exp = s.split("e")
        return f"{mant}*10^({int(exp)})"
    return s[:-2] if s.endswith(".0") else s


def _exp_text(p) -> str:
    p = int(p) if float(p).is_integer() else p
    return f"^{p}" if isinstance(p, int) and p > 0 else f"^({p})"


def value_text(v) -> str:
    """A value as linear maths text that rfile reads back exactly: numbers in
    full precision, units in SI base units, matrices as mat(…), strings."""
    from .unitdata import BASE
    from .units import Quantity

    if isinstance(v, String):
        return '"' + v.text + '"'
    if isinstance(v, Matrix):
        return "mat(" + ",".join([value_text(x) for x in v.items] + [str(v.nrows), str(v.ncols)]) + ")"
    if isinstance(v, Quantity):
        z = v.value
        if isinstance(z, complex):
            re_, im = z.real, z.imag
            num = f"({_number_text(re_)}{'-' if im < 0 else '+'}{_number_text(abs(im))}*i)"
        else:
            num = _number_text(z)
        units = "".join(f"*'{name}" + ("" if p == 1 else _exp_text(p))
                        for name, p in zip(BASE, v.dims) if p)
        return num + units
    raise SMathError("Cannot evaluate.", None)


def read_value_text(text: str):
    """What value_text wrote, as a value (rfile)."""
    from .evaluator import Context, Evaluator
    from .linear import parse_text
    from .model import Row
    from .parser import parse_row

    # parse_text reads ":", brackets and spaces as maths: each string's text
    # goes through as one stand-in character and is put back afterwards
    parts = text.strip().split('"')
    strings = parts[1::2]
    for k in range(1, len(parts), 2):
        parts[k] = chr(0xE000 + k // 2)
    row = parse_text('"'.join(parts))

    def restore(r):
        for k in range(len(r.items) - 1, -1, -1):
            it = r.items[k]
            if isinstance(it, str) and 0xE000 <= ord(it[0]) < 0xE000 + len(strings):
                r.items[k:k + 1] = list(strings[ord(it[0]) - 0xE000])
            elif not isinstance(it, str):
                for inner in it.rows:
                    restore(inner)
    restore(row)
    if not isinstance(row, Row) or not row.items:
        raise SMathError("File is empty.", None)
    return Evaluator().eval(parse_row(row), Context())


@fn("wfile", 2)
def _wfile(value, name):
    path = _data_file(name)
    text = value_text(value)
    if not writing_allowed:
        return Q(1.0)       # written when the equation is left, not at every keystroke
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        return Q(0.0)
    return Q(1.0)


@fn("rfile", 1)
def _rfile(name):
    path = _data_file(name)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError:
        raise SMathError(f"File not found: {os.path.basename(path)}", None) from None
    return read_value_text(text)


@fn("dfile", 1)
def _dfile(name):
    path = _data_file(name)
    if not os.path.isfile(path):
        return Q(0.0)
    if not writing_allowed:
        return Q(1.0)
    try:
        os.remove(path)
    except OSError:
        return Q(0.0)
    return Q(1.0)
