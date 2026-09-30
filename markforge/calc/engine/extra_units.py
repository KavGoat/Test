"""SI-prefixed units SMath's own library does not define.

SMath's Units.xml has kN and MPa but not, for example, hPa, mPa, daN, mbar,
kWh, MA or kC.  Engineers type these, so every SI prefix from pico to tera
is added to the common SI units (and bar, eV, Wh), unless the name already
exists in SMath's library - SMath's definition always wins, so 'min, 'ha,
'ms and the like keep their meaning.  They are listed in the autocomplete
with their full name (Hectopascal).  SMath Studio itself will not read them
back from a saved file.
"""
from __future__ import annotations

PREFIXES = [
    ("p", "Pico", 1e-12), ("n", "Nano", 1e-9), ("μ", "Micro", 1e-6), ("m", "Milli", 1e-3),
    ("c", "Centi", 1e-2), ("d", "Deci", 1e-1), ("da", "Deca", 1e1), ("h", "Hecto", 1e2),
    ("k", "Kilo", 1e3), ("M", "Mega", 1e6), ("G", "Giga", 1e9), ("T", "Tera", 1e12),
]

# units that take every prefix
BASES = ["N", "Pa", "J", "W", "m", "g", "s", "A", "V", "Hz", "C", "Ω", "L", "bar", "mol",
         "F", "H", "T", "S", "Wb", "lm", "lx", "Bq", "Gy", "Sv", "kat", "eV", "Wh"]
# centi, deci, deca and hecto only where they are actually used
# (hPa, daN, cm, dL, hL, mbar...), so the list is not flooded with cA, dV...
CDH_BASES = {"N", "Pa", "m", "g", "L", "bar"}

# watt hour, which SMath lacks too (kWh is the usual energy unit on bills)
WH = (3600.0, (2, 1, -2, 0, 0, 0, 0, 0, 0, 0, 0), 0.0)

ADDED: list[str] = []


def install(units: dict, info: dict, catalog: dict) -> None:
    if ADDED:
        return
    if "Wh" not in units:
        units["Wh"] = WH
        info["Wh"] = ("260", "All", "Wh")
        catalog["Wh"] = ("Energy", "Watt hour")
        ADDED.append("Wh")
    for base in BASES:
        if base not in units:
            continue
        factor, dims, offset = units[base]
        category, title = catalog.get(base, ("", base))
        for sym, word, mult in PREFIXES:
            name = sym + base
            if sym in ("c", "d", "da", "h") and base not in CDH_BASES:
                continue
            if name in units:
                continue
            units[name] = (factor * mult, dims, offset)
            info[name] = (info[base][0], info[base][1], name)
            catalog[name] = (category, word + title.lower())
            ADDED.append(name)
