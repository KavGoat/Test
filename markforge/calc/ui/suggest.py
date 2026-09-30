"""SMath's autocomplete list and the entries it offers.

Moved out of WebSMath's window (ui/worksheet_view.py) unchanged, so the
CalcForge canvas offers exactly the list SMath Cloud does: units, functions,
constants and the names defined above, in SMath's order, with SMath's icons
and descriptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem

from ..engine.catalog import FUNCTIONS, UNIT_CATALOG
from ..engine.evaluator import BUILTIN_CONSTANTS

PACKAGE_ICONS = Path(__file__).with_name("icons")
KEYWORDS = ["break", "continue"]


class SuggestionList(QListWidget):
    """SMath Cloud's autocomplete list (#region-suggestions): white, 1px black
    border, 12px text, at least 90px wide and 90px high at most; each entry
    has a 12x12 icon for function / unit / operand coloured by origin (core,
    plugin, worksheet) and shows its name without the unit apostrophe; the
    selected entry is white on #9faab5.  The selected entry's description
    appears in a tooltip box to the right of the list."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip)
        self.setFocusPolicy(Qt.NoFocus)
        self.setIconSize(QSize(11, 11))
        self.setSpacing(0)
        self.setUniformItemSizes(True)
        self.setStyleSheet(
            "QListWidget{background:#fff;border:1px solid #000;font-size:11px;outline:0;}"
            "QListWidget::item{padding:0px 2px 0px 2px;margin:0;color:#000;border:0;height:14px;}"
            "QListWidget::item:selected{color:#fff;background:#9faab5;}"
            "QListWidget::item:hover{color:#fff;background:#9faab5;}")
        self.setMinimumWidth(90)
        self.setMaximumHeight(92)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.start = 0
        self.word = ""
        self.activated = False  # the user moved through the list (Enter applies)
        self.tooltip = QLabel(parent)
        self.tooltip.setWindowFlags(Qt.ToolTip)
        self.tooltip.setTextFormat(Qt.RichText)
        self.tooltip.setWordWrap(True)
        self.tooltip.setMaximumWidth(206)
        self.tooltip.setStyleSheet("QLabel{background:#ffffe1;border:1px solid #000;font-size:12px;"
                                   "padding:0 3px;margin:0;color:#000;}")
        self.tooltip.hide()
        self.currentRowChanged.connect(lambda _r: self.show_tooltip())

    def entries(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def fill(self, entries, selected) -> None:
        self.clear()
        for e in entries:
            it = QListWidgetItem(_origin_icon(e.kind, e.origin), e.text)
            it.setData(Qt.UserRole, e)
            self.addItem(it)
        self.activated = False
        self.setCurrentRow(-1 if selected is None else selected)
        if selected is not None:
            self.scrollToItem(self.item(selected), QListWidget.PositionAtTop)

    def show_tooltip(self) -> None:
        it = self.currentItem()
        desc = it.data(Qt.UserRole).description if it is not None and self.isVisible() else ""
        if not desc:
            self.tooltip.hide()
            return
        self.tooltip.setText(desc)
        self.tooltip.adjustSize()
        self.tooltip.move(self.x() + self.width() + 2, self.y())
        self.tooltip.show()

    def hideEvent(self, e) -> None:
        self.tooltip.hide()
        super().hideEvent(e)


_ICONS: dict = {}


def _origin_icon(kind: str, origin: int) -> QIcon:
    """The site's img-origin-<kind>-<origin> icons (copied from its CSS)."""
    key = (kind, origin)
    if key not in _ICONS:
        from pathlib import Path

        path = PACKAGE_ICONS / f"origin-{kind}-{origin}.png"
        _ICONS[key] = QIcon(str(path)) if path.exists() else QIcon()
    return _ICONS[key]


SITE_HIDDEN_UNITS = {"A", "C", "g", "H", "K", "S", "T", "mg", "mJ", "mN", "mW", "mohm", "mΩ",
                     "Pa", "kN", "mS", "pc", "pS", "μS"}


# arc minute/second are listed under SMath's escaped names
SMATH_LABEL = {"'": "\\0027\\", '"': "\\0022\\"}


_SYMBOL_ORDER = "\\%‰°¤∞"


def smath_sort_key(label: str):
    """Order SMath Cloud lists suggestions in (.NET culture sorting): symbols
    first (\\ % ‰ ° ¤), then digits, then letters ignoring case and accents
    (Å with a), Greek after Latin; ties: lower case, then unaccented first."""
    import unicodedata

    primary, ties = [], []
    for ch in label.lstrip("'"):
        base = unicodedata.normalize("NFD", ch)[0]
        if ch.isalpha():
            primary.append((3, base.lower()))
        elif ch.isdigit():
            primary.append((2, ch))
        elif ch in _SYMBOL_ORDER:
            primary.append((1, str(_SYMBOL_ORDER.index(ch))))
        else:
            primary.append((0, ch))
        ties.append((base != ch, not ch.islower()))
    return primary, ties


@dataclass
class Suggestion:
    """One autocomplete entry, as SMath Cloud sends it."""

    name: str  # what is inserted: 'm, sum (4), x
    text: str  # what the list shows: m, sum (4), x
    kind: str  # function / unit / operand (picks the icon)
    origin: int  # 1 SMath core, 2 plugin, 3 this worksheet
    args: int
    description: str  # HTML shown in the tooltip ("" = no tooltip)


def suggestion_entries(word: str, defined_names, user_functions=None) -> list:
    """suggestion_list with each entry's icon kind, origin and description."""
    from markforge.calc.engine.suggest_meta import SUGGESTION_META

    user_functions = user_functions or {}
    out = []
    for label, _kind in suggestion_list(word, defined_names):
        meta = SUGGESTION_META.get(label)
        if meta is not None and label not in user_functions:
            origin, args, desc = meta
        elif label.startswith("'"):
            # a unit the site hides (kN, Pa...): its title from the catalogue
            origin, args, desc = 1, 0, UNIT_CATALOG.get(label[1:], ("", ""))[1]
        else:
            origin, args, desc = 3, user_functions.get(label, 0), ""
        kind = "function" if args > 0 else ("unit" if label.startswith("'") else "operand")
        text = label[1:] if label.startswith("'") else label
        out.append(Suggestion(label, text, kind, origin, args, desc))
    return out


def unit_value_text(name: str) -> str:
    """'k -> "k = 1.380650424·10^-23 kg m^2/K s^2" (SI base units)."""
    from markforge.calc.engine.display import DUnit, display_text, display_value, unit_text
    from markforge.calc.engine.numformat import NumberFormat
    from markforge.calc.engine.units import base_unit_parts, unit_quantity

    q = unit_quantity(name)
    num = display_text(display_value(q, NumberFormat(decimals=10, engineering=False), show_unit=False))
    u = unit_text(DUnit(*base_unit_parts(q.dims))) if any(q.dims) else ""
    return f"{name} = {num} {u}".rstrip()


def unit_box_entries(word: str) -> list:
    """Entries for the desired-unit box: every unit whose name starts with the
    typed text (any case), in SMath's order, each described by its name,
    category and value in SI units."""
    import html

    w = word[1:] if word.startswith("'") else word
    names = [u for u in UNIT_CATALOG if u.lower().startswith(w.lower())]
    names.sort(key=lambda u: smath_sort_key("'" + u))
    out = []
    for u in names:
        category, title = UNIT_CATALOG.get(u, ("", u))
        desc = (f"{html.escape(title)} ({html.escape(category)})<br>"
                f"<span style='font-family:Courier New'>{html.escape(unit_value_text(u))}</span>")
        label = "'" + SMATH_LABEL.get(u, u)
        out.append(Suggestion(label, label[1:], "unit", 1, 0, desc))
    return out


def _selection_key_name(key, mods) -> Optional[str]:
    """Editor key for Shift/Ctrl (Option/Cmd on a Mac) + arrow, Home, End:
    SHIFT+LEFT, WORD+RIGHT, SHIFT+WORD+LEFT, ...  None for plain keys."""
    import sys

    mac = sys.platform == "darwin"
    shift = bool(mods & Qt.ShiftModifier)
    word = bool(mods & (Qt.AltModifier if mac else Qt.ControlModifier))
    base = {Qt.Key_Left: "LEFT", Qt.Key_Right: "RIGHT", Qt.Key_Home: "HOME", Qt.Key_End: "END"}[key]
    if mac and mods & Qt.ControlModifier and base in ("LEFT", "RIGHT"):
        base = "HOME" if base == "LEFT" else "END"  # Cmd+arrow: start/end of the line
        word = False
    if word and base in ("HOME", "END"):
        word = False  # Ctrl+Home/End: start/end
    if not shift and not word:
        return None if base in ("LEFT", "RIGHT") and not (mac and mods & Qt.ControlModifier) else base
    return ("SHIFT+" if shift else "") + ("WORD+" if word else "") + base


def selected_index(entries: list, word: str) -> Optional[int]:
    """The entry SMath Cloud highlights when the list opens: the first whose
    name starts with the typed text (case-sensitive first, observed: M ->
    MB, m -> m, q -> qq), else ignoring case (Si -> sign), else none."""
    key = (lambda e: e.name) if word.startswith("'") else (lambda e: e.text)
    for fold in (False, True):
        w = word.lower() if fold else word
        for k, e in enumerate(entries):
            t = key(e).lower() if fold else key(e)
            if t.startswith(w):
                return k
    return None


# False: variables, units, constants, functions (asked for); True: SMath Cloud's order
SMATH_ORDER = False


def _is_constant_unit(label: str) -> bool:
    from markforge.calc.engine.unitdata import INFO

    name = label[1:] if label.startswith("'") else label
    return INFO.get(name, ("",))[0] == "constant"


_UNITS_SORTED = None


def _sorted_units() -> list:
    """[(label, lower-case name)] of every unit in SMath's order (sorted once)."""
    global _UNITS_SORTED
    if _UNITS_SORTED is None or len(_UNITS_SORTED) != len(UNIT_CATALOG):
        _UNITS_SORTED = sorted((("'" + SMATH_LABEL.get(u, u), u.lower()) for u in UNIT_CATALOG),
                               key=lambda x: smath_sort_key(x[0]))
    return _UNITS_SORTED


_CATALOG_SORTED = None


def _sorted_catalog() -> list:
    """[(label, kind, lower-case name)] of functions, constants and keywords
    in SMath's order, built once (overloads listed as "sum (1)", "sum (4)")."""
    global _CATALOG_SORTED
    if _CATALOG_SORTED is None:
        counts, entries = {}, {}
        for name, nargs, _, _ in FUNCTIONS:
            counts[name] = counts.get(name, 0) + 1
        for name, nargs, _, _ in FUNCTIONS:
            entries.setdefault(name if counts[name] == 1 else f"{name} ({nargs})", ("function", name.lower()))
        for c in list(BUILTIN_CONSTANTS) + KEYWORDS + ["lastError"]:
            entries.setdefault(c, ("constant", c.lower()))
        _CATALOG_SORTED = sorted(((k, kind, low) for k, (kind, low) in entries.items()),
                                 key=lambda x: smath_sort_key(x[0]))
    return _CATALOG_SORTED


def suggestion_list(word: str, defined_names) -> list:
    """The autocomplete list for a partial word: case-insensitive substring
    matches over units, functions, constants, keywords, lastError and the
    worksheet's names defined above.  Order: the worksheet's names, units,
    constants, unit constants, functions and keywords (SMATH_ORDER: SMath
    Cloud's own order - units first, the rest mixed).  Catalogues are sorted
    once, so a keystroke only filters them."""
    w = word.lower()
    needle = w[1:] if w.startswith("'") else w
    # every unit is listed, also those SMath Cloud hides behind a case
    # variant (kN behind kn, Pa behind pa; see SITE_HIDDEN_UNITS)
    units = [(label, "unit") for label, low in _sorted_units() if needle in low]
    catalog = [(k, kind) for k, kind, low in _sorted_catalog() if needle in low]
    known = {k for k, _ in catalog}
    variables = sorted(((n, "variable") for n in defined_names if needle in n.lower() and n not in known),
                       key=lambda x: smath_sort_key(x[0]))
    if SMATH_ORDER:
        rest = sorted(catalog + variables, key=lambda x: smath_sort_key(x[0]))
        return units + rest
    consts = [(k, v) for k, v in catalog if v == "constant" and k not in KEYWORDS]
    funcs = [(k, v) for k, v in catalog if v == "function" or k in KEYWORDS]
    unit_consts = [u for u in units if _is_constant_unit(u[0])]
    plain_units = [u for u in units if not _is_constant_unit(u[0])]
    return variables + plain_units + consts + unit_consts + funcs


def _linear_unit(u: str) -> str:
    """kg·m/s^2 -> kg*'m/'s^2 (typed form for the unit placeholder)."""
    out = u.replace("·", "*'").replace("/", "/'")
    return out
