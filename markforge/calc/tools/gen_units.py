"""Generate markforge/calc/engine/unitdata.py from SMath Studio's Units.xml / Constants.xml.

SMath ships its unit system as data: every unit belongs to a *dimension*
(a product of base units), has a factor (and optional offset for the
non-linear temperature scales) and may take a list of SI prefixes.  Using
the very same data keeps names, factors and the output-unit choice
identical to SMath.

    python -m markforge.calc.tools.gen_units "SMath Studio/entries"
"""
from __future__ import annotations

import math
import pprint
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"e": "http://smath.info/schemas/entries/1.0"}
BASE = ["m", "kg", "s", "A", "K", "mol", "cd", "bit", "sr", "dB", "¤"]


def _num(expr: str) -> float:
    expr = expr.replace("π", str(math.pi)).replace("{", "(").replace("}", ")")
    expr = expr.replace("^", "**")
    if not re.fullmatch(r"[0-9.eE+\-*/() ]+", expr):
        raise ValueError(expr)
    return float(eval(expr))  # noqa: S307 - digits and operators only


def _dims(connection: str, known: dict[str, tuple]) -> tuple:
    """Parse "{kg*m^2}/{A*s^3}" into an exponent vector over BASE."""
    toks = re.findall(r"[A-Za-zΩμ°¤.]+|-?[0-9.]+|[*/^(){}]", connection)
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1]

    def atom():
        t = take()
        if t in "({":
            v = product()
            take()
        elif re.fullmatch(r"-?[0-9.]+", t):
            v = [0.0] * len(BASE)  # the "1" of 1/x
        else:
            v = list(known[t])
        if peek() == "^":
            take()
            p = float(take())
            v = [x * p for x in v]
        return v

    def product():
        v = atom()
        while peek() in ("*", "/"):
            op = take()
            w = atom()
            v = [a + b if op == "*" else a - b for a, b in zip(v, w)]
        return v

    vec = product()
    return tuple(int(v) if v == int(v) else v for v in vec)


def generate(entries: Path) -> str:
    units_xml = ET.parse(entries / "Units.xml").getroot()
    const_xml = ET.parse(entries / "Constants.xml").getroot()

    known: dict[str, tuple] = {}
    for i, b in enumerate(BASE):
        v = [0] * len(BASE)
        v[i] = 1
        known[b] = tuple(v)

    prefixes = {}
    for p in units_xml.find("e:prefixes", NS):
        sym = p.get("name").split()[0]
        factor = _num(p.get("factor", "1")) * 10 ** int(p.get("exp", "0"))
        prefixes[sym] = factor

    dimensions: dict[str, tuple] = {}
    derived = []  # (baseunit, dims) in file order: SMath's output-unit table
    for d in units_xml.find("e:dimensions", NS):
        did = d.get("id")
        base = d.get("baseunit")
        conn = d.get("connection")
        if conn:
            dims = _dims(conn, known)
        elif base in known:
            dims = known[base]
        else:
            dims = tuple([0] * len(BASE))
        dimensions[did] = dims
        if base and conn:
            derived.append((base, dims))
            known[base] = dims

    units: dict[str, tuple] = {}
    info: dict[str, tuple] = {}

    def add(el, dims, category):
        factor = _num(el.get("factor", "1")) * 10 ** _num(el.get("exp", "0"))
        offset = _num(el.get("offset")) if el.get("offset") else 0.0
        system = el.get("system", "All")
        names = []
        for syn in el.findall("e:synonym", NS):
            names += syn.get("name").split()
        names = [n.replace("\\0027\\", "'").replace("\\0022\\", '"') for n in names]
        for n in names:
            units[n] = (factor, dims, offset)
            info[n] = (category, system, names[0])
        for ext in el.findall("e:extension", NS):
            for root in ext.get("for").split():
                for pre in ext.findall("e:prefix", NS):
                    pname = pre.get("name") + root
                    units[pname] = (factor * prefixes[pre.get("name")], dims, 0.0)
                    info[pname] = (category, system, pname)

    for prop in units_xml.find("e:units", NS):
        conn = prop.get("connection")
        dims = _dims(conn, known) if conn else dimensions[prop.get("dimension")]
        for el in prop.findall("e:add", NS):
            d = _dims(el.get("connection"), known) if el.get("connection") else dims
            add(el, d, prop.get("dimension"))
        if prop.tag.endswith("add"):
            add(prop, dims, "")

    for prop in const_xml.find("e:constants", NS):
        if prop.tag.endswith("property"):
            for el in prop.findall("e:add", NS):
                add(el, dimensions[prop.get("dimension")], "constant")
        else:
            add(prop, _dims(prop.get("connection"), known), "constant")

    # Units the current SMath Cloud has that this Units.xml predates.
    ev = 1.602176634e-19
    for pre, f in (("", 1), ("k", 1e3), ("M", 1e6), ("G", 1e9), ("T", 1e12)):
        units[pre + "eV"] = (ev * f, known["J"], 0.0)
        info[pre + "eV"] = ("260", "All", pre + "eV")
    units["nt"] = (1.0, _dims("cd/m^2", known), 0.0)
    info["nt"] = ("266", "Metric", "nt")
    units["¤"] = (1.0, known["¤"], 0.0)
    info["¤"] = ("money", "All", "¤")

    out = [
        '"""Unit table generated from SMath Studio Units.xml/Constants.xml. Do not edit."""',
        f"BASE = {BASE!r}",
        "",
        "# name -> (factor to SI base, dimension exponents over BASE, offset)",
        "UNITS = " + pprint.pformat(units, width=100, sort_dicts=True),
        "",
        "# name -> (dimension id / 'constant', system, primary synonym)",
        "INFO = " + pprint.pformat(info, width=100, sort_dicts=True),
        "",
        "# Derived units SMath uses to display results, in its preference order.",
        "DERIVED = " + pprint.pformat(derived, width=100),
        "",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "SMath Studio/entries")
    dst = Path(__file__).resolve().parent.parent / "engine" / "unitdata.py"
    dst.write_text(generate(src), encoding="utf-8")
    print("wrote", dst)
