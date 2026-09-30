"""Keystroke-level equation editor replicating SMath's math region editing.

Observed SMath behaviour this reproduces (see docs/SMATH_BEHAVIOUR.md):

* Typing ``/`` takes the operand left of the cursor into the numerator and
  moves into the denominator; everything typed next stays there
  (``1/7*1000`` is 1 over 7·1000).  ``2*3/4`` is 2·(3/4).
* ``^`` opens an exponent, ``(`` a bracket, ``[`` an index, ``|`` an
  absolute value (``|`` alone is logical OR).  Typing continues inside until the right arrow leaves;
  ``)`` does not close anything.  ``:`` inserts ``:=`` at the cursor.
* ``=`` evaluates.  If what is left of it is a single name (or a call
  pattern ``f(x)``) that is not defined above, SMath turns it into ``:=``
  instead.  The cursor stays where it was.
* Space on a region holding just a name converts the region to a *text*
  region (``abc`` + space -> text "abc ").  Backspace does not convert it
  back; undo does.  Elsewhere space widens the selection.
* After ``=`` the result carries a unit placeholder; typing a unit there
  converts the result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .engine.model import (DIGITS, LETTERS, Abs, Box, Frac, Index, Matrix, Paren,
                           Pow, Program, Root, Row, Sqrt)

IDENT_CHARS = LETTERS | DIGITS | {"."}
OPERATOR_KEYS = {
    "+": "+", "-": "-", "*": "*", "<": "<", ">": ">", "!": "!",
    "≤": "≤", "≥": "≥", "≠": "≠", "≡": "≡", "∧": "∧", "∨": "∨", "¬": "¬",
    "±": "±", "×": "*", "&": "∧", "|": "∨",
}
# calls that become structures once they have this many arguments
STRUCTURE_ARITY = {"for": 3, "while": 2, "try": 2, "sum": 4, "product": 4, "int": 4,
                   "diff": 2, "range": 2, "el": 2}
TOOLBOX_ROWS = {"for": 3, "while": 2, "try": 2, "sum": 4, "product": 4, "int": 4, "diff": 2,
                "range": 2, "range3": 3, "sys": 2, "line": 2, "if": 3}
NAMED_KEYS = {"LEFT", "RIGHT", "UP", "DOWN", "HOME", "END", "TAB", "ENTER", "BACK", "DELETE"}
# precedence of operators typed after a selection
BINARY_PREC = {"∨": 1, "⊕": 1, "∧": 2, "<": 3, ">": 3, "≤": 3, "≥": 3, "≠": 3, "≡": 3,
               "≈": 3, "≉": 3, "+": 4, "-": 4, "±": 4, "*": 5, "†": 5}


def _prec(node) -> int:
    from .engine import ast as A

    if isinstance(node, A.BinOp):
        return BINARY_PREC.get(node.op, 6 if node.op in "/^" else 5)
    if isinstance(node, A.Unary) and node.op in "-+":
        return 4
    return 9


@dataclass
class Cursor:
    row: Row
    pos: int


def _is_word_char(it) -> bool:
    return isinstance(it, str) and (it in IDENT_CHARS or it == "'")


def _row_path(r: Row) -> list:
    """Path of (item index, child row index) pairs from the root to r."""
    path = []
    while r.parent is not None:
        box = r.parent
        prow = box.parent_row
        path.append((prow.items.index(box), box.rows.index(r)))
        r = prow
    return list(reversed(path))


def _follow(root: Row, path: list) -> Row:
    r = root
    for i, j in path:
        r = r.items[i].rows[j]
    return r


@dataclass
class Snapshot:
    kind: str
    root: Row
    unit: Optional[Row]
    text: str
    in_unit: bool
    path: list
    pos: int
    text_pos: int = 0


class MathEditor:
    """Edits one math region.

    ``is_defined(name, nargs)`` tells the editor whether a name is defined
    above this region (nargs None = variable); it decides whether ``=`` means
    "evaluate" or "define".
    """

    def __init__(self, root: Optional[Row] = None, is_defined: Optional[Callable] = None):
        self.kind = "math"  # or "text"
        self.root = root or Row()
        self.evaluate = False  # region ends with "=" (result shown)
        self.unit = Row()  # unit placeholder after the result
        self.text = ""  # when kind == "text"
        self.text_pos = 0
        self.cursor = Cursor(self.root, len(self.root))
        self.in_unit = False
        self.selection: Optional[tuple] = None  # (row, start, end)
        # SMath's "whole sub-expression" cursor state: the cursor sits at the
        # start of a sub-expression and the underline covers all of it
        # (reached with Left at the start of its first name, or Right across
        # an operator).  Typing an operator there makes it the right operand.
        self.node: Optional[tuple] = None
        self.is_defined = is_defined or (lambda name, nargs=None: False)
        self.plot_input = False  # a plot's input: no "=", no text conversion
        # names the user picked as the worksheet variable although a unit has
        # the same name (m:10 above; see WorksheetView._clash)
        self.confirmed_words: set = set()
        self._undo: list[Snapshot] = []
        self._redo: list[Snapshot] = []
        self._fix_parents(self.root)

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _fix_parents(r: Row, parent=None):
        r.parent = parent
        for it in r.items:
            if isinstance(it, Box):
                it.parent_row = r
                for c in it.rows:
                    MathEditor._fix_parents(c, it)

    def _snapshot(self) -> Snapshot:
        root = self.root.copy()
        unit = self.unit.copy()
        self._fix_parents(root)
        self._fix_parents(unit)
        return Snapshot(self.kind, root, unit, self.text, self.in_unit,
                        _row_path(self.cursor.row), self.cursor.pos, self.text_pos)

    def _restore(self, s: Snapshot) -> None:
        self.kind = s.kind
        self.root = s.root
        self.unit = s.unit
        self.text = s.text
        self.in_unit = s.in_unit
        base = self.unit if s.in_unit else self.root
        self.evaluate = any(it == "=" for it in self.root.items)
        try:
            r = _follow(base, s.path)
        except (IndexError, AttributeError):
            r = self.root
        self.cursor = Cursor(r, min(s.pos, len(r)))
        self.text_pos = min(s.text_pos, len(self.text))
        self.selection = None
        self.node = None

    def _push_undo(self) -> None:
        self._undo.append(self._snapshot())
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    @property
    def row(self) -> Row:
        return self.cursor.row

    @property
    def pos(self) -> int:
        return self.cursor.pos

    def set_cursor(self, r: Row, pos: int) -> None:
        self.cursor = Cursor(r, max(0, min(pos, len(r))))
        self.in_unit = self._root_of(r) is self.unit
        self.selection = None
        self.node = None

    def _root_of(self, r: Row) -> Row:
        while r.parent is not None:
            r = r.parent.parent_row
        return r

    def expression_items(self) -> list:
        """Items of the root row before the evaluation sign."""
        items = self.root.items
        if self.evaluate and "=" in items:
            return items[: items.index("=")]
        return items

    # -- public keystroke API -------------------------------------------------
    def key(self, k: str) -> None:
        """Apply one keystroke. Named keys: LEFT RIGHT UP DOWN HOME END BACK
        DELETE TAB ENTER; everything else is a typed character."""
        if self.kind == "text":
            self._push_undo()
            self._text_key(k)
            return
        handler = {
            "LEFT": self._left, "RIGHT": self._right, "UP": self._up, "DOWN": self._down,
            "HOME": self._home, "END": self._end, "TAB": self._tab,
        }.get(k)
        if handler:
            handler()
            return
        self._push_undo()
        if self.node is not None and k not in ("BACK", "DELETE"):
            if self._type_at_node(k):
                return
        if self.node is not None and k == "BACK":
            self._back_at_node()
            return
        self.node = None
        if k == "BACK":
            self._backspace()
        elif k == "DELETE":
            self._delete()
        else:
            self._type(k)

    def type(self, text: str) -> None:
        for ch in text:
            self.key(ch)

    # -- text regions -----------------------------------------------------------
    def _text_key(self, k: str) -> None:
        p = self.text_pos
        if k == "BACK":
            if p > 0:
                self.text = self.text[: p - 1] + self.text[p:]
                self.text_pos = p - 1
        elif k == "DELETE":
            self.text = self.text[:p] + self.text[p + 1:]
        elif k == "LEFT":
            self.text_pos = max(0, p - 1)
        elif k == "RIGHT":
            self.text_pos = min(len(self.text), p + 1)
        elif k == "HOME":
            self.text_pos = self.text.rfind("\n", 0, p) + 1
        elif k == "END":
            e = self.text.find("\n", p)
            self.text_pos = len(self.text) if e < 0 else e
        elif k == "ENTER":
            self.text = self.text[:p] + "\n" + self.text[p:]
            self.text_pos = p + 1
        elif len(k) == 1:
            self.text = self.text[:p] + k + self.text[p:]
            self.text_pos = p + 1

    def _to_text(self, text: str) -> None:
        self.kind = "text"
        self.text = text
        self.text_pos = len(text)

    # -- typing -----------------------------------------------------------------
    def _type(self, ch: str) -> None:
        if self.selection and ch not in (" ",):
            self._apply_to_selection(ch)
            return
        if ch == " ":
            self._space()
            return
        if ch == "." and self._number_has_dot():
            return  # a second decimal point is ignored (2.5.3 -> 2.53)
        if not _is_word_char(ch):
            self._drop_empty_subscript()
        if (ch in LETTERS and ch != "'" or ch == "(") and not self.in_unit and self._after_number():
            self._insert_char("*")  # observed: 2x -> 2·x, 2( -> 2·(, 2e3 -> 2·e3
        if ch == '"' and self.root.is_empty() and not self.in_unit:
            self._to_text("")
            return
        if ch == "=":
            self._equals()
            return
        if ch == ":":
            self._define_sign()
            return
        if ch == "/":
            self._fraction()
            return
        if ch == "^":
            self._insert_box(Pow(Row()), into=0)
            return
        if ch == "(":
            if self._structure_from_word():
                return
            self._insert_box(Paren(Row()), into=0)
            return
        if ch in ",;" and self._separator_in_structure():
            return
        if ch == ")":
            self._close(Paren)
            return
        if ch == "[":
            self._insert_box(Index(Row()), into=0)
            return
        if ch == "]":
            self._close(Index)
            return
        if ch == "\\":
            self._insert_box(Sqrt(Row()), into=0)
            return
        ch = OPERATOR_KEYS.get(ch, ch)
        self._insert_char(ch)

    def _word_bounds(self) -> tuple:
        r, p = self.row, self.pos
        a = p
        while a > 0 and _is_word_char(r.items[a - 1]):
            a -= 1
        return a, p

    def _number_has_dot(self) -> bool:
        a, p = self._word_bounds()
        items = self.row.items[a:p]
        return bool(items) and (items[0] in DIGITS or items[0] == ".") and "." in items

    def _after_number(self) -> bool:
        a, p = self._word_bounds()
        items = self.row.items[a:p]
        return bool(items) and (items[0] in DIGITS or items[0] == ".") and \
            all(it in DIGITS or it == "." for it in items)

    def _drop_empty_subscript(self) -> None:
        """x. followed by an operator: the empty subscript is dropped (x+)."""
        a, p = self._word_bounds()
        items = self.row.items
        if p - a >= 2 and items[p - 1] == "." and items[a] not in DIGITS \
                and "." not in items[a:p - 1]:
            del items[p - 1]
            self.cursor = Cursor(self.row, p - 1)

    def _insert_char(self, ch: str) -> None:
        r, p = self.row, self.pos
        r.insert(p, ch)
        self.cursor = Cursor(r, p + 1)

    def _insert_box(self, box: Box, into: int = 0) -> None:
        r, p = self.row, self.pos
        r.insert(p, box)
        box.parent_row = r
        for c in box.rows:
            c.parent = box
        self.cursor = Cursor(box.rows[into], len(box.rows[into]))

    # Words that turn into structures when "(" is typed after them (observed:
    # if( -> if/else block, line( -> line block, mat( -> 2x2 matrix,
    # sqrt( -> radical, nthroot( -> radical with index, abs( -> |x|).
    STRUCTURE_WORDS = ("if", "line", "mat", "sqrt", "nthroot", "abs")

    def _structure_from_word(self) -> bool:
        start, word = self.current_word()
        if word not in self.STRUCTURE_WORDS:
            return False
        r = self.row
        del r.items[start:self.pos]
        self.cursor = Cursor(r, start)
        if word == "if":
            self._insert_box(Program("if", Row(), Row(), Row()), into=0)
        elif word == "line":
            self._insert_box(Program("line", Row(), Row()), into=0)
        elif word == "mat":
            self._insert_box(Matrix(2, 2), into=0)
        elif word == "sqrt":
            self._insert_box(Sqrt(Row()), into=0)
        elif word == "nthroot":
            self._insert_box(Root(Row(), Row()), into=1)
        elif word == "abs":
            self._insert_box(Abs(Row()), into=0)
        return True

    def _separator_in_structure(self) -> bool:
        """',' moves between the slots of structures instead of being typed."""
        r = self.row
        box = r.parent
        if box is None:
            return False
        if isinstance(box, Paren) and self._call_to_structure(box):
            return True
        k = box.rows.index(r)
        if isinstance(box, Program) and box.name == "if":
            # if(c1, v1, c2, v2, ..., else): a comma after a value adds an
            # "else if" branch (observed), after a condition moves on.
            if k % 2 == 0 and k < len(box.rows) - 1:
                self.cursor = Cursor(box.rows[k + 1], len(box.rows[k + 1]))
            else:
                new_c, new_v = Row(), Row()
                insert_at = k + 1 if k % 2 == 1 else k
                for j, nr in enumerate((new_c, new_v)):
                    box.rows.insert(insert_at + j, nr)
                    nr.parent = box
                self.cursor = Cursor(new_c, 0)
            return True
        if isinstance(box, Program):
            nr = Row()
            box.rows.insert(k + 1, nr)
            nr.parent = box
            self.cursor = Cursor(nr, 0)
            return True
        if isinstance(box, Root):
            if r is box.rows[1]:
                self.cursor = Cursor(box.rows[0], len(box.rows[0]))
            return True
        if isinstance(box, Matrix):
            return True  # commas are ignored inside matrix cells (observed)
        return False

    def _call_to_structure(self, paren: Paren) -> bool:
        """SMath draws some calls by their argument count: once the comma that
        completes while(c, body), for(i, range, body), sum(e, i, a, b)...
        is typed, the call becomes the block (the toolbox inserts the same)."""
        prow = paren.parent_row
        i = prow.items.index(paren)
        j = i
        while j > 0 and _is_word_char(prow.items[j - 1]):
            j -= 1
        name = "".join(prow.items[j:i])
        arity = STRUCTURE_ARITY.get(name)
        inner = paren.rows[0]
        # the comma being typed completes the argument list?
        if arity is None or self.row is not inner:
            return False
        commas = [k for k, it in enumerate(inner.items) if it in (",", ";")]
        if len(commas) + 2 != arity or self.pos != len(inner):
            return False
        pieces, start = [], 0
        for k in commas + [len(inner.items)]:
            pieces.append(Row(inner.items[start:k]))
            start = k + 1
        pieces.append(Row())
        del prow.items[j:i + 1]
        if name == "el":
            # el(v, i): the index is drawn as a subscript on v
            base = pieces[0].items
            prow.items[j:j] = base
            box = Index(pieces[1])
            prow.insert(j + len(base), box)
            self._fix_parents(prow, prow.parent)
            self.cursor = Cursor(box.rows[0], 0)
            return True
        box = Program(name, *pieces)
        prow.insert(j, box)
        self._fix_parents(prow, prow.parent)
        self.cursor = Cursor(pieces[-1], 0)
        return True

    def insert_structure(self, name: str) -> None:
        """Insert a toolbox structure: for(,,  while(,  sum(,,, ..."""
        self._push_undo()
        rows = TOOLBOX_ROWS.get(name, 2)
        if name == "el":
            self._insert_box(Index(Row()), into=0)
            return
        if name == "nthroot":
            self._insert_box(Root(Row(), Row()), into=1)
            return
        self._insert_box(Program("range" if name == "range3" else name, *[Row() for _ in range(rows)]), into=0)

    def _close(self, kind) -> None:
        """")" and "]" are ignored: SMath Cloud keeps the cursor inside the
        bracket ((1+2)*3= typed straight through gives (1+2·3)=7); the right
        arrow is what leaves a bracket."""
        return

    def operand_start(self, r: Row, p: int) -> int:
        """Index where the operand ending at position p starts."""
        i = p
        while i > 0:
            it = r.items[i - 1]
            if isinstance(it, (Pow, Index)) or it == "!":
                i -= 1
                continue
            if isinstance(it, Paren):
                i -= 1
                while i > 0 and _is_word_char(r.items[i - 1]):
                    i -= 1
                return i
            if isinstance(it, Box):
                return i - 1
            if _is_word_char(it):
                # a 'unit is its own operand: 2'kN/ puts only kN over the bar
                while i > 0 and _is_word_char(r.items[i - 1]) and r.items[i - 1] != "'":
                    i -= 1
                if i > 0 and r.items[i - 1] == "'":
                    i -= 1
                return i
            return i
        return i

    def _fraction(self) -> None:
        r, p = self.row, self.pos
        if self.selection:
            sr, a, b = self.selection
            r, p, start = sr, b, a
            self.selection = None
        else:
            start = self.operand_start(r, p)
        num = Row(r.items[start:p])
        del r.items[start:p]
        frac = Frac(num, Row())
        r.insert(start, frac)
        self._fix_parents(r, r.parent)
        if num.is_empty():
            self.cursor = Cursor(frac.rows[0], 0)
        else:
            self.cursor = Cursor(frac.rows[1], 0)

    def _define_sign(self) -> None:
        """":" inserts ":=" at the cursor, wherever it is (as SMath does)."""
        if self.in_unit or "≔" in self.root.items:
            return
        self._insert_char("≔")

    def _equals(self) -> None:
        if self.in_unit or self.plot_input:
            return
        if self.evaluate or "≔" in self.root.items:
            return
        name, nargs = self._definable_head()
        if name is not None and not self.is_defined(name, nargs):
            self.root.append("≔")
            self.cursor = Cursor(self.root, len(self.root))
            return
        self.root.append("=")
        self.evaluate = True
        self.unit = Row()
        # the cursor stays where it was (observed)

    def _definable_head(self):
        """(name, nargs) if the root is a lone name or name(args...)."""
        items = self.root.items
        if not items:
            return None, None
        if all(_is_word_char(it) for it in items):
            word = "".join(items)
            if word[0] in DIGITS or word[0] == "'" or word[0] == ".":
                return None, None
            return word, None
        if isinstance(items[-1], Paren) and all(_is_word_char(it) for it in items[:-1]) and len(items) > 1:
            word = "".join(items[:-1])
            if word[0] in DIGITS or word[0] == "'":
                return None, None
            inner = items[-1].rows[0].items
            nargs = 1 + sum(1 for it in inner if it in (",", ";")) if inner else 1
            return word, nargs
        return None, None

    def _space(self) -> None:
        items = self.root.items
        if (not self.in_unit and not self.plot_input and items and self.selection is None
                and all(isinstance(it, str) and it in IDENT_CHARS for it in items)):
            # a lone name, number or subscripted name becomes text (observed:
            # "q ", "2 ", "sin ", "x.1 "); anything with an operator does not
            self._to_text("".join(items) + " ")
            return
        self._grow_selection()

    # -- selection ------------------------------------------------------------
    def selection_levels(self) -> list:
        """Spans (row, start, end) space cycles through, innermost first.

        Observed on SMath Cloud with the cursor after the 3 of 1+2·3: the first
        space selects 2·3, the second the whole expression, the third 2·3
        again.  A single name or number is never a level of its own; when
        the cursor is inside a box the box itself (and what contains it)
        follow.
        """
        from .engine import ast as A
        from .engine.parser import ParseError, Parser

        levels = []
        r, p = self.row, self.pos
        while True:
            if r is self.root:
                items = self.expression_items()
            else:
                items = r.items
            sub = Row()
            sub.items = list(items)
            spans = set()
            try:
                parser = Parser(sub)
                node = parser.boolean() if parser.toks else None
            except (ParseError, IndexError):
                node = None
            if node is not None:
                for n in A.walk(node):
                    if n.src is None or isinstance(n, (A.Num, A.Var, A.UnitRef, A.Placeholder, A.Str)):
                        continue
                    _, s0, s1 = n.src
                    if s0 < p <= s1 or (s0 <= p < s1):
                        spans.add((s0, s1))
            if items:
                spans.add((0, len(items)))
            for s0, s1 in sorted(spans, key=lambda t: t[1] - t[0]):
                if (r, s0, s1) not in levels:
                    levels.append((r, s0, s1))
            if r.parent is None:
                break
            box = r.parent
            prow = box.parent_row
            i = prow.items.index(box)
            levels.append((prow, i, i + 1))
            r, p = prow, i + 1
        return levels

    def _grow_selection(self) -> None:
        levels = self.selection_levels()
        if not levels:
            return
        if self.selection in levels:
            k = (levels.index(self.selection) + 1) % len(levels)
        else:
            k = 0
        self.selection = levels[k]

    def _apply_to_selection(self, ch: str) -> None:
        """What typing does with a selection (observed on SMath Cloud)."""
        from .engine.parser import ParseError, parse_row

        r, a, b = self.selection
        self.selection = None
        ch = OPERATOR_KEYS.get(ch, ch)
        if ch == ")" or ch == "]":
            return
        if ch == "/":
            self.cursor = Cursor(r, b)
            self.selection = (r, a, b)
            self._fraction()
            return
        if ch in ("(", "\\", "^"):
            inner = Row(r.items[a:b])
            del r.items[a:b]
            single = len(inner.items) == 1 and isinstance(inner.items[0], Box)
            box = Sqrt(inner) if ch == "\\" else (inner.items[0] if (ch == "^" and single) else Paren(inner))
            r.insert(a, box)
            self._fix_parents(r, r.parent)
            self.cursor = Cursor(r, a + 1)
            if ch == "^":
                self._insert_box(Pow(Row()))
            return
        if ch in ("BACK", "DELETE"):
            del r.items[a:b]
            self.cursor = Cursor(r, a)
            return
        if ch in BINARY_PREC:
            # the selection becomes the left operand; bracket it when the new
            # operator binds tighter: (1+2·3)·■ but 1+2·3+■
            sel = Row(r.items[a:b])
            try:
                node = parse_row(sel)
            except ParseError:
                node = None
            if node is not None and _prec(node) < BINARY_PREC[ch] and b - a > 1:
                del r.items[a:b]
                r.insert(a, Paren(sel))
                self._fix_parents(r, r.parent)
                b = a + 1
            self.cursor = Cursor(r, b)
            self._insert_char(ch)
            return
        if ch in ("=", ":"):
            self.cursor = Cursor(r, b)
            self._type(ch)
            return
        # letters and digits leave the expression unchanged (observed)

    # -- deletion ---------------------------------------------------------------
    def _backspace(self) -> None:
        if self.selection:
            self._apply_to_selection("BACK")
            return
        r, p = self.row, self.pos
        if p > 0:
            it = r.items[p - 1]
            if isinstance(it, Box):
                if all(c.is_empty() for c in it.rows):
                    r.pop(p - 1)
                    self.cursor = Cursor(r, p - 1)
                else:
                    last = it.rows[-1] if not isinstance(it, Frac) else it.rows[1]
                    self.cursor = Cursor(last, len(last))
                return
            if it == "=" and r is self.root:
                r.pop(p - 1)
                self.evaluate = False
                self.unit = Row()
                self.cursor = Cursor(r, p - 1)
                return
            r.pop(p - 1)
            self.cursor = Cursor(r, p - 1)
            return
        # at the start of a row inside a box
        if r.parent is None:
            if r is self.unit and self.root is not None:
                self.set_cursor(self.root, len(self.expression_items()))
            return
        box = r.parent
        prow = box.parent_row
        i = prow.items.index(box)
        if isinstance(box, Frac) and r is box.rows[1]:
            # remove the fraction bar: numerator and denominator join
            merged = box.rows[0].items + box.rows[1].items
            prow.items[i:i + 1] = merged
            self._fix_parents(prow, prow.parent)
            self.cursor = Cursor(prow, i + len(box.rows[0].items))
            return
        if all(c.is_empty() for c in box.rows) or isinstance(box, (Paren, Pow, Index, Sqrt, Abs)):
            inner = [x for c in box.rows for x in c.items]
            prow.items[i:i + 1] = inner
            self._fix_parents(prow, prow.parent)
            self.cursor = Cursor(prow, i)
            return
        self.cursor = Cursor(prow, i)

    def _delete(self) -> None:
        if self.selection:
            self._apply_to_selection("DELETE")
            return
        r, p = self.row, self.pos
        if p < len(r):
            it = r.items[p]
            if isinstance(it, Box):
                if all(c.is_empty() for c in it.rows):
                    r.pop(p)
                else:
                    self.cursor = Cursor(it.rows[0], 0)
                return
            if it == "=" and r is self.root:
                del r.items[p:]
                self.evaluate = False
                return
            r.pop(p)

    # -- the SMath cursor: tokens, underline, sub-expression state -----------------
    def _limit(self, r: Row) -> int:
        return len(self.expression_items()) if r is self.root else len(r)

    def token_span(self, r: Row, p: int) -> tuple:
        """The name/number the cursor is in (or just before), as SMath
        underlines it: the whole token, not just the part left of the cursor."""
        items = r.items
        n = self._limit(r)
        if p > 0 and _is_word_char(items[p - 1]):
            a = p
            while a > 0 and _is_word_char(items[a - 1]) and items[a - 1] != "'":
                a -= 1
            if a > 0 and items[a - 1] == "'":
                a -= 1
            b = p
            while b < n and _is_word_char(items[b]) and items[b] != "'":
                b += 1
            return self._subscript_part(items, a, b, p)
        if p > 0 and (isinstance(items[p - 1], Box) or items[p - 1] == "!"):
            return self.operand_start(r, p), p
        if p < n and _is_word_char(items[p]):
            b = p + 1
            while b < n and _is_word_char(items[b]) and items[b] != "'":
                b += 1
            return self._subscript_part(items, p, b, p)
        if p < n and isinstance(items[p], Box):
            b = p + 1
            while b < n and isinstance(items[b], (Pow, Index)):
                b += 1
            return p, b
        return p, p

    @staticmethod
    def _subscript_part(items, a: int, b: int, p: int) -> tuple:
        """A name with a subscript (x.1) is underlined part by part, as on
        SMath Cloud: the subscript when the cursor is after the dot, else
        the base.  Numbers keep their decimal point."""
        head = a + 1 if items[a] == "'" else a
        if head >= b or items[head] in DIGITS or items[head] == ".":
            return a, b
        try:
            d = items.index(".", head, b)
        except ValueError:
            return a, b
        return (d + 1, b) if p > d else (a, d)

    def in_subscript(self) -> bool:
        """True when the cursor sits in a name's subscript."""
        r, a, _ = self.underline()
        return a > 0 and r is self.row and r.items[a - 1] == "." and self.node is None \
            and self._subscript_part(r.items, *self._whole_word(r, a - 1), self.pos)[0] == a

    def _whole_word(self, r: Row, i: int) -> tuple:
        a = i
        while a > 0 and _is_word_char(r.items[a - 1]) and r.items[a - 1] != "'":
            a -= 1
        if a > 0 and r.items[a - 1] == "'":
            a -= 1
        b = i
        while b < len(r.items) and _is_word_char(r.items[b]) and (r.items[b] != "'" or b == a):
            b += 1
        return a, b

    def underline(self) -> tuple:
        """(row, start, end) of what the cursor's underline covers."""
        if self.node is not None:
            return self.node
        a, b = self.token_span(self.row, self.pos)
        return self.row, a, b

    def _node_spans(self, r: Row) -> list:
        from .engine import ast as A
        from .engine.parser import ParseError, Parser

        sub = Row()
        sub.items = list(r.items[: self._limit(r)])
        try:
            parser = Parser(sub)
            node = parser.boolean() if parser.toks else None
        except (ParseError, IndexError):
            return []
        spans = []
        for n in A.walk(node) if node is not None else ():
            if n.src is not None and not isinstance(n, (A.Num, A.Var, A.UnitRef, A.Placeholder, A.Str)):
                spans.append((n.src[1], n.src[2]))
        return spans

    def _bigger_node_at(self, r: Row, a: int, than: int):
        """Smallest sub-expression starting at a that is longer than `than`."""
        cands = [(s1 - s0, s1) for s0, s1 in self._node_spans(r) if s0 == a and s1 - s0 > than]
        return min(cands)[1] if cands else None

    # -- movement ---------------------------------------------------------------
    def _left(self) -> None:
        self.selection = None
        if self.node is not None:
            r, a, b = self.node
            end = self._bigger_node_at(r, a, b - a)
            if end is not None:
                self.node = (r, a, end)
                return
            if a == 0 and r.parent is None:
                return  # at the very start it stays (observed)
            self.node = None
            self.cursor = Cursor(r, a)
        else:
            r, p = self.row, self.pos
            ta, tb = self.token_span(r, p)
            if ta == p and tb > p and (p == 0 or not _is_word_char(r.items[p - 1])):
                end = self._bigger_node_at(r, p, tb - ta)
                if end is not None:
                    self.node = (r, p, end)
                    return
        r, p = self.row, self.pos
        if p > 0:
            it = r.items[p - 1]
            if isinstance(it, Box):
                last = it.rows[-1]
                self.cursor = Cursor(last, len(last))
            else:
                self.cursor = Cursor(r, p - 1)
            return
        if r.parent is not None:
            box = r.parent
            k = box.rows.index(r)
            if k > 0:
                prev = box.rows[k - 1]
                self.cursor = Cursor(prev, len(prev))
            else:
                prow = box.parent_row
                self.cursor = Cursor(prow, prow.items.index(box))
        elif r is self.unit:
            self.set_cursor(self.root, len(self.expression_items()))

    def _right(self) -> None:
        self.selection = None
        if self.node is not None:
            # leaving the sub-expression state: back to the name at the cursor
            self.node = None
            return
        r, p = self.row, self.pos
        limit = len(self.expression_items()) if r is self.root else len(r)
        if p < limit:
            it = r.items[p]
            if isinstance(it, Box):
                self.cursor = Cursor(it.rows[0], 0)
            else:
                self.cursor = Cursor(r, p + 1)
                # across an operator onto a sub-expression: select it as a whole
                if isinstance(it, str) and not _is_word_char(it) and it not in ",;":
                    ta, tb = self.token_span(r, p + 1)
                    if ta == p + 1 and tb > ta:
                        end = self._bigger_node_at(r, p + 1, tb - ta)
                        if end is not None:
                            self.node = (r, p + 1, end)
            return
        if r.parent is not None:
            box = r.parent
            k = box.rows.index(r)
            if k + 1 < len(box.rows):
                self.cursor = Cursor(box.rows[k + 1], 0)
            else:
                prow = box.parent_row
                self.cursor = Cursor(prow, prow.items.index(box) + 1)
        elif r is self.root and self.evaluate:
            self.set_cursor(self.unit, 0)

    def _type_at_node(self, k: str) -> bool:
        """Typing in the sub-expression state (observed with ab+cd·ef):
        '/' gives ■/(cd·ef), an operator goes in front of it, letters are
        ignored.  Returns False to fall through to normal typing."""
        r, a, b = self.node
        ch = OPERATOR_KEYS.get(k, k)
        if k in NAMED_KEYS:
            return False
        if k == "/":
            inner = Row(r.items[a:b])
            del r.items[a:b]
            frac = Frac(Row(), inner)
            r.insert(a, frac)
            self._fix_parents(r, r.parent)
            self.node = None
            self.cursor = Cursor(frac.rows[0], 0)
            return True
        if k == "(":
            self.selection = (r, a, b)
            self.node = None
            self._apply_to_selection("(")
            return True
        if ch in BINARY_PREC:
            r.insert(a, ch)
            self.node = (r, a, b + 1)
            self.cursor = Cursor(r, a)
            return True
        if len(k) == 1 and (k in IDENT_CHARS or k == "'"):
            return True  # ignored, as on the site
        self.node = None
        return False

    def _back_at_node(self) -> None:
        """Backspace at the start of a sub-expression removes the operator
        before it; the two operands stay separate (a product)."""
        r, a, b = self.node
        self.node = None
        if a > 0 and isinstance(r.items[a - 1], str) and r.items[a - 1] in BINARY_PREC:
            r.items[a - 1] = "*"
            self.cursor = Cursor(r, a)
        else:
            self.cursor = Cursor(r, a)
            self._backspace()

    def _up(self) -> None:
        r = self.row
        if r.parent is not None and isinstance(r.parent, Frac) and r is r.parent.rows[1]:
            num = r.parent.rows[0]
            self.cursor = Cursor(num, len(num))

    def _down(self) -> None:
        r = self.row
        if r.parent is not None and isinstance(r.parent, Frac) and r is r.parent.rows[0]:
            den = r.parent.rows[1]
            self.cursor = Cursor(den, len(den))

    def _home(self) -> None:
        self.set_cursor(self.root, 0)

    def _end(self) -> None:
        self.set_cursor(self.root, len(self.expression_items()))

    def _tab(self) -> None:
        """Jump to the next empty placeholder (the unit slot after a result)."""
        from .engine.model import walk_rows

        rows = list(walk_rows(self.root))
        empties = [r for r in rows if r.is_empty() and r is not self.root]
        cur = self.row
        if empties:
            idx = empties.index(cur) + 1 if cur in empties else 0
            if idx < len(empties):
                self.cursor = Cursor(empties[idx], 0)
                return
        if self.evaluate:
            self.set_cursor(self.unit, len(self.unit))

    # -- queries -------------------------------------------------------------------
    def current_word(self) -> tuple[int, str]:
        """The identifier fragment immediately left of the cursor (autocomplete)."""
        r, p = self.row, self.pos
        i = p
        while i > 0 and _is_word_char(r.items[i - 1]):
            i -= 1
        return i, "".join(r.items[i:p])

    def replace_word(self, start: int, text: str, call: bool = False) -> None:
        """Replace the word being typed with an autocomplete choice."""
        self._push_undo()
        r, p = self.row, self.pos
        del r.items[start:p]
        self.cursor = Cursor(r, start)
        for ch in text:
            self._insert_char(ch)
        if call:
            self._insert_box(Paren(Row()))
