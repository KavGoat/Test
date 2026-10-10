"""User-editable keyboard bindings.

Some bindings do more than pick a tool. On an empty canvas a bare keypress does
nothing unless it is bound: typing ``"`` starts a text markup where the pointer
is, ``|`` a note and ``@`` a callout, so that writing on the page never needs a
trip to the toolbar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QKeySequence

from ..settings import app_settings
from .tools import TOOLS

TOOL = "tool"
INSERT = "insert"
COMMAND = "command"
SYMBOL = "symbol"
SMATH = "smath"          # a key inside an equation (calcedit.py handles it)

# Where a binding acts (decisions 5 and 6). A key may mean two things only
# when its two meanings can never both be live: Calc and Markup mode are
# never on together, and inside an equation SMath's keys win ("editing
# decides"), so Ctrl+0 is ≥ there and Fit page everywhere else.
ALWAYS = "always"        # document commands, whatever is going on
CALC = "calc"            # on the canvas in Calc mode
MARKUP = "markup"        # on the canvas in Markup mode (tool keys, typing keys)
EQUATION = "equation"    # while an equation has the cursor
TYPING = "typing"        # symbols: wherever words or an equation are being typed

SCOPE_NAMES = {ALWAYS: "Always", CALC: "Calc mode", MARKUP: "Markup mode",
               EQUATION: "In an equation", TYPING: "While typing"}


def scopes_overlap(a: str, b: str) -> bool:
    """Whether a key bound in scope *a* and in scope *b* could both be live."""
    if a == b or TYPING in (a, b):
        return True
    pair = {a, b}
    if pair == {CALC, MARKUP}:
        return False
    if EQUATION in pair:
        return False              # inside an equation SMath's key wins
    return True                   # ALWAYS with CALC or MARKUP


@dataclass(frozen=True)
class Binding:
    """One bindable action."""

    action_id: str
    label: str
    default: str
    kind: str
    category: str
    payload: str = ""          # tool key, or command method name
    scope: str = ALWAYS


def _tool_bindings() -> list[Binding]:
    bindings = []
    for tool in TOOLS:
        # Every tool key is off in Calc mode, with or without Shift or Alt
        # (decision 5): there a letter starts an equation.
        bindings.append(Binding(f"tool.{tool.key}", tool.label, tool.shortcut,
                                TOOL, tool.category, tool.key,
                                ALWAYS if tool.key == "select" else MARKUP))
    return bindings


# Symbols, for typing into a text markup, a note or a callout. A markup on a
# structural drawing is full of them — ⌀20 bars, a 45° splay, φMn — and they are
# here so the ones somebody writes every day are on a key they can reach without
# hunting through a character map.
SYMBOLS: list[tuple[str, str, str, str]] = [
    # action name,      symbol, label,               default keys
    ("multiply",        "×",    "Multiply ×",        "Ctrl+Alt+8"),
    ("divide",          "÷",    "Divide ÷",          "Ctrl+Alt+/"),
    ("power",           "^",    "Power ^",           "Ctrl+Alt+6"),
    ("root",            "√(",   "Square root √",     "Ctrl+Alt+R"),
    ("squared",         "²",    "Squared ²",         "Ctrl+Alt+2"),
    ("cubed",           "³",    "Cubed ³",           "Ctrl+Alt+3"),
    ("plusminus",       "±",    "Plus/minus ±",      "Ctrl+Alt+="),
    ("le",              "≤",    "At most ≤",         "Ctrl+Alt+,"),
    ("ge",              "≥",    "At least ≥",        "Ctrl+Alt+."),
    ("ne",              "≠",    "Not equal ≠",       "Ctrl+Alt+N"),
    ("pi",              "π",    "Pi π",              "Ctrl+Alt+P"),
    ("degree",          "°",    "Degree °",          "Ctrl+Alt+D"),
    ("delta",           "Δ",    "Delta Δ",           "Ctrl+Alt+T"),
    ("sum",             "Σ",    "Sum Σ",             "Ctrl+Alt+S"),
    ("diameter",        "⌀",    "Diameter ⌀",        "Ctrl+Alt+O"),
    ("micro",           "µ",    "Micro µ",           "Ctrl+Alt+M"),
    # The Greek letters an engineer here writes every week. φ is the capacity
    # reduction factor, and it is the same variable however it is typed —
    # "phi", this key, or a letter pasted out of a standard.
    ("phi",             "φ",    "Phi φ",             "Ctrl+Alt+F"),
    ("sigma",           "σ",    "Sigma σ",           "Ctrl+Alt+G"),
    ("alpha",           "α",    "Alpha α",           "Ctrl+Alt+A"),
    ("beta",            "β",    "Beta β",            "Ctrl+Alt+B"),
    ("gamma",           "γ",    "Gamma γ",           "Ctrl+Alt+Y"),
    ("theta",           "θ",    "Theta θ",           "Ctrl+Alt+H"),
    ("lamda",           "λ",    "Lambda λ",          "Ctrl+Alt+L"),
    ("rho",             "ρ",    "Rho ρ",             "Ctrl+Alt+K"),
    ("epsilon",         "ε",    "Epsilon ε",         "Ctrl+Alt+E"),
    ("omega",           "ω",    "Omega ω",           "Ctrl+Alt+W"),
]


def _symbol_bindings() -> list[Binding]:
    return [Binding(f"symbol.{name}", label, keys, SYMBOL, "Symbols", symbol, TYPING)
            for name, symbol, label, keys in SYMBOLS]


# SMath's keys inside an equation (decision 6: the SMath section of the
# shortcut manager). The payload says what calcedit.py does with it: "type:"
# types those characters into the equation, "box:" inserts a structure,
# "command:" runs a command. Bold, italic and underline are not here: they
# are MarkForge's own Ctrl+B/I/U, which reach equations too.
SMATH_KEYS: list[tuple[str, str, str, str]] = [
    # action name,       label,                    default,     payload
    ("boolean_equal",    "Boolean equals ≡",       "Ctrl+=",    "type:≡"),
    ("not_equal",        "Not equal ≠",            "Ctrl+3",    "type:≠"),
    ("at_most",          "At most ≤",              "Ctrl+9",    "type:≤"),
    ("at_least",         "At least ≥",             "Ctrl+0",    "type:≥"),
    ("nth_root",         "N-th root",              "Ctrl+\\",   "box:nthroot"),
    ("transpose",        "Transpose",              "Ctrl+1",    "type:transpose("),
    ("cross_product",    "Cross product ×",        "Ctrl+8",    "type:†"),
    ("element",          "Element (index)",        "Ctrl+[",    "type:["),
    ("insert_function",  "Insert function",        "Ctrl+E",    "command:insert_function"),
    ("constants",        "Constants",              "Ctrl+K",    "command:show_constants"),
    ("double_check",     "Double-check results",   "Ctrl+Shift+D", "command:double_check"),
    ("select_all",       "Select all equations",   "Ctrl+A",    "command:select_all_equations"),
]


def _smath_bindings() -> list[Binding]:
    return [Binding(f"smath.{name}", label, keys, SMATH, "SMath", payload, EQUATION)
            for name, label, keys, payload in SMATH_KEYS]


# Typing on bare paper comes first because it is reached without choosing a
# tool. One explicit trigger avoids consuming ordinary typing.
DEFAULT_BINDINGS: list[Binding] = [
    Binding("insert.text", "Start text", '"', INSERT, "Typing", "text", MARKUP),
    Binding("insert.note", "Start note", "|", INSERT, "Typing", "note", MARKUP),
    Binding("insert.callout", "Start callout", "@", INSERT, "Typing", "callout", MARKUP),
    # Decision 5: the mode switch, the equation start key in Markup mode, and
    # " giving Calculation text in Calc mode are ordinary bindings.
    Binding("command.calc_mode", "Calc/Markup mode", "F12", COMMAND, "SMath", "toggle_calc_mode"),
    Binding("insert.equation", "Start equation", "'", INSERT, "SMath", "equation", MARKUP),
    Binding("insert.calc_text", "Start Calculation text", '"', INSERT, "SMath", "calc_text", CALC),
    Binding("insert.plot", "Insert plot", "@", INSERT, "SMath", "plot", CALC),
] + _smath_bindings() + _tool_bindings() + [
    Binding("command.fit_page", "Fit page", "Ctrl+0", COMMAND, "View", "fit_page"),
    Binding("command.fit_width", "Fit width", "Ctrl+1", COMMAND, "View", "fit_width"),
    Binding("command.renumber_counts", "Renumber counts", "", COMMAND, "Markup",
            "renumber_counts"),
] + _symbol_bindings()

BY_ID = {binding.action_id: binding for binding in DEFAULT_BINDINGS}


def clashes_in(assignments: dict) -> dict[str, list[str]]:
    """Keys given to two actions that could both be live (scopes_overlap)."""
    by_key: dict[str, list[str]] = {}
    for action_id, text in assignments.items():
        if text:
            by_key.setdefault(QKeySequence(text).toString(QKeySequence.PortableText).lower()
                              or text.lower(), []).append(action_id)
    found = {}
    for key, ids in by_key.items():
        bad = set()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                sa = BY_ID[a].scope if a in BY_ID else ALWAYS
                sb = BY_ID[b].scope if b in BY_ID else ALWAYS
                if scopes_overlap(sa, sb):
                    bad.update((a, b))
        if bad:
            found[key] = [i for i in ids if i in bad]
    return found


class ShortcutManager(QObject):
    """Holds the current bindings and remembers changes between sessions."""

    changed = Signal()

    SETTINGS_GROUP = "shortcuts"

    def __init__(self, parent=None):
        super().__init__(parent)
        # Registered as the window builds its actions, so that every key the
        # application answers to is in one list and can be changed. Only the
        # ones that belong to the words being typed — Ctrl+B, Ctrl+I, Ctrl+U —
        # stay out of it: those mean bold, italic and underline in a text box
        # in every program there has ever been, and nothing else may take them.
        self._extra: list[Binding] = []
        self._sequences: dict[str, str] = {b.action_id: b.default for b in DEFAULT_BINDINGS}
        self.load()

    def register(self, action_id: str, label: str, default: str,
                 category: str = "Document", payload: str = "", scope: str = ALWAYS) -> str:
        """Add a binding the window owns, and give back the key to use.

        Called once per action as the window is built. A binding that has been
        changed keeps the change: what is registered is the *default*.
        """
        known = BY_ID.get(action_id)
        if known is None:
            binding = Binding(action_id, label, default, COMMAND, category, payload, scope)
            BY_ID[action_id] = binding
            self._extra.append(binding)
        elif not any(b.action_id == action_id for b in self._extra) \
                and known not in DEFAULT_BINDINGS:
            # A second window in the same process: the binding is already in
            # the shared list, but this manager's own copy of the sequences
            # was read before it existed.
            self._extra.append(known)
        if action_id not in self._sequences:
            # Registered after load(), so its own stored value is read here.
            settings = self._settings()
            settings.beginGroup(self.SETTINGS_GROUP)
            stored = settings.value(action_id, None)
            settings.endGroup()
            self._sequences[action_id] = default if stored is None else str(stored)
        return self._sequences[action_id]

    # -- access ------------------------------------------------------------
    def bindings(self) -> list[Binding]:
        return list(DEFAULT_BINDINGS) + list(self._extra)

    def sequence(self, action_id: str) -> str:
        return self._sequences.get(action_id, "")

    def default(self, action_id: str) -> str:
        binding = BY_ID.get(action_id)
        return binding.default if binding else ""

    def set_sequence(self, action_id: str, text: str) -> None:
        """Change a binding, and remember it straight away.

        A rebound key that only survives a clean quit is a rebound key that
        does not survive a crash, and the user has to do it twice.
        """
        self._sequences[action_id] = text.strip()
        self.save()

    def reset(self, action_id: Optional[str] = None) -> None:
        if action_id is None:
            self._sequences = {b.action_id: b.default for b in self.bindings()}
        elif action_id in BY_ID:
            self._sequences[action_id] = BY_ID[action_id].default
        self.changed.emit()

    def conflicts(self) -> dict[str, list[str]]:
        """Key sequences bound to more than one action that could both be live."""
        return clashes_in(self._sequences)

    def scope_of(self, action_id: str) -> str:
        binding = BY_ID.get(action_id)
        return binding.scope if binding is not None else ALWAYS

    # -- canvas typing -----------------------------------------------------
    def is_canvas_binding(self, sequence: "QKeySequence") -> bool:
        """True when *sequence* picks a tool or starts something on the canvas.

        These are the bindings that must fall silent while somebody is typing:
        M is a letter in the middle of a sentence, and Alt+M is not a request
        to change tool when the cursor is in a text box.
        """
        if sequence.isEmpty():
            return False
        wanted = sequence.toString(QKeySequence.PortableText).lower()
        for binding in DEFAULT_BINDINGS:
            if binding.kind not in (TOOL, INSERT):
                continue
            current = self._sequences.get(binding.action_id, "")
            if not current:
                continue
            if QKeySequence(current).toString(
                    QKeySequence.PortableText).lower() == wanted:
                return True
        return False

    def binding_for(self, sequence: "QKeySequence", scopes=None) -> Optional[Binding]:
        """Return the configured binding that owns *sequence*, if any — in one
        of *scopes*, when given."""
        if sequence.isEmpty():
            return None
        wanted = sequence.toString(QKeySequence.PortableText).lower()
        # Without a scope asked for, the meaning outside an equation comes
        # first: that is where a key is asked about when nothing is being
        # typed (inside an equation calcedit asks for EQUATION explicitly).
        ordered = sorted(self.bindings(), key=lambda b: b.scope == EQUATION)
        for binding in ordered:
            if scopes is not None and binding.scope not in scopes:
                continue
            current = self._sequences.get(binding.action_id, "")
            if (current and QKeySequence(current).toString(
                    QKeySequence.PortableText).lower() == wanted):
                return binding
        return None

    def match_typed(self, text: str, modifiers, mode: str = MARKUP) -> Optional[Binding]:
        """The binding a bare keypress on the canvas should run, if any, in
        the canvas mode *mode* (Calc or Markup)."""
        if not text or modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return None
        for binding in DEFAULT_BINDINGS:
            if binding.scope not in (mode, ALWAYS, TYPING) or binding.kind == SMATH:
                continue
            sequence = self._sequences.get(binding.action_id, "")
            if not sequence:
                continue
            # Single-character bindings are what a bare keystroke can match.
            if len(sequence) == 1 and sequence == text:
                return binding
            if len(sequence) == 1 and sequence.isalpha() and sequence.lower() == text.lower():
                return binding
        return None

    # -- persistence -------------------------------------------------------
    def _settings(self) -> QSettings:
        return app_settings()

    def load(self) -> None:
        settings = self._settings()
        settings.beginGroup(self.SETTINGS_GROUP)
        for action_id in list(self._sequences):
            stored = settings.value(action_id, None)
            if stored is not None:
                self._sequences[action_id] = str(stored)
        settings.endGroup()

    def save(self) -> None:
        settings = self._settings()
        settings.beginGroup(self.SETTINGS_GROUP)
        for action_id, text in self._sequences.items():
            if text == self.default(action_id):
                settings.remove(action_id)
            else:
                settings.setValue(action_id, text)
        settings.endGroup()
        settings.sync()
