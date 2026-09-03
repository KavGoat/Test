"""User-editable keyboard bindings.

Two of these do more than pick a tool.  On an empty canvas a bare keypress does
nothing at all unless it is bound — typing ``"`` opens a text region where the
cursor is and typing ``/`` opens a calculation, which is how SMath decides what
you meant before you have typed anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QKeySequence

from .tools import TOOLS

TOOL = "tool"
INSERT = "insert"
COMMAND = "command"
SYMBOL = "symbol"


@dataclass(frozen=True)
class Binding:
    """One bindable action."""

    action_id: str
    label: str
    default: str
    kind: str
    category: str
    payload: str = ""          # tool key, or command method name


def _tool_bindings() -> list[Binding]:
    bindings = []
    for tool in TOOLS:
        bindings.append(Binding(f"tool.{tool.key}", tool.label, tool.shortcut,
                                TOOL, tool.category, tool.key))
    return bindings


# Maths symbols, for typing into a calculation, a text box or a cell. The
# engine reads the operators among them — × really multiplies, √ really takes a
# root, ² really squares — and Δ and Σ are ordinary letters as far as a variable
# name is concerned. They are here so the ones somebody uses every day can go on
# a key they can reach without hunting through a character map.
SYMBOLS: list[tuple[str, str, str, str]] = [
    # action name,      symbol, label,               default keys
    ("multiply",        "×",    "Multiply ×",        "Ctrl+Alt+8"),
    ("divide",          "÷",    "Divide ÷",          "Ctrl+Alt+/"),
    ("power",           "^",    "To the power ^",    "Ctrl+Alt+6"),
    ("root",            "√(",   "Square root √",     "Ctrl+Alt+R"),
    ("squared",         "²",    "Squared ²",         "Ctrl+Alt+2"),
    ("cubed",           "³",    "Cubed ³",           "Ctrl+Alt+3"),
    ("plusminus",       "±",    "Plus or minus ±",   "Ctrl+Alt+="),
    ("le",              "≤",    "Less or equal ≤",   "Ctrl+Alt+,"),
    ("ge",              "≥",    "More or equal ≥",   "Ctrl+Alt+."),
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
    return [Binding(f"symbol.{name}", label, keys, SYMBOL, "Symbols", symbol)
            for name, symbol, label, keys in SYMBOLS]


# The two canvas typing modes come first because they are the ones people reach
# for without thinking about tools at all.
DEFAULT_BINDINGS: list[Binding] = [
    Binding("insert.text", "Start typing text", '"', INSERT, "Typing", "text"),
    # Typing anything unbound already starts a calculation; this is for people
    # who would rather say so first.
    Binding("insert.math", "Start typing maths", "/", INSERT, "Typing", "math"),
    Binding("insert.table", "Start a table here", "|", INSERT, "Typing", "table"),
    Binding("insert.callout", "Start a callout here", "@", INSERT, "Typing", "callout"),
] + _tool_bindings() + [
    Binding("command.recalculate", "Recalculate", "F9", COMMAND, "Document", "recalculate"),
    Binding("command.fit_page", "Fit page", "Ctrl+0", COMMAND, "View", "fit_page"),
    Binding("command.fit_width", "Fit width", "Ctrl+1", COMMAND, "View", "fit_width"),
    Binding("command.split_lines", "Split calculation into lines", "Ctrl+Shift+L",
            COMMAND, "Document", "split_calculation"),
    Binding("command.merge_lines", "Merge calculations", "Ctrl+Shift+M",
            COMMAND, "Document", "merge_calculations"),
    Binding("command.problems", "Show problems", "Ctrl+Shift+P", COMMAND, "Document",
            "show_problems"),
    Binding("command.renumber_counts", "Renumber count markers", "", COMMAND, "Document",
            "renumber_counts"),
] + _symbol_bindings()

BY_ID = {binding.action_id: binding for binding in DEFAULT_BINDINGS}


class ShortcutManager(QObject):
    """Holds the current bindings and remembers changes between sessions."""

    changed = Signal()

    SETTINGS_GROUP = "shortcuts"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sequences: dict[str, str] = {b.action_id: b.default for b in DEFAULT_BINDINGS}
        self.load()

    # -- access ------------------------------------------------------------
    def bindings(self) -> list[Binding]:
        return list(DEFAULT_BINDINGS)

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
            self._sequences = {b.action_id: b.default for b in DEFAULT_BINDINGS}
        elif action_id in BY_ID:
            self._sequences[action_id] = BY_ID[action_id].default
        self.changed.emit()

    def conflicts(self) -> dict[str, list[str]]:
        """Key sequences bound to more than one action."""
        seen: dict[str, list[str]] = {}
        for action_id, text in self._sequences.items():
            if text:
                seen.setdefault(text.lower(), []).append(action_id)
        return {text: ids for text, ids in seen.items() if len(ids) > 1}

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

    def match_typed(self, text: str, modifiers) -> Optional[Binding]:
        """The binding a bare keypress on the canvas should run, if any."""
        if not text or modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return None
        for binding in DEFAULT_BINDINGS:
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
        return QSettings("CalcForge", "CalcForge")

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

    def as_key_sequence(self, action_id: str) -> QKeySequence:
        return QKeySequence(self.sequence(action_id))
