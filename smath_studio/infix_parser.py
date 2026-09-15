"""Infix expression parser and AST-to-XML conversion for user-entered expressions.

Converts typed text like 'x := 5 + 3' or 'sin(pi/4) =' into AST nodes,
and converts AST nodes back to editable text and to XML <e> elements
for round-trip saving.
"""

from __future__ import annotations

import re
from typing import Optional
from xml.etree.ElementTree import Element

from .expression import (
    ASTNode, Number, Variable, UnitRef, StringLiteral,
    BinaryOp, UnaryOp, FunctionCall, Evaluation,
)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class _Token:
    __slots__ = ("type", "value")

    def __init__(self, type: str, value: str):
        self.type = type
        self.value = value


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 1
            tokens.append(_Token("STRING", text[i + 1 : j]))
            i = j + 1 if j < n else j
            continue
        if c == "'":
            j = i + 1
            while j < n and text[j] != "'":
                j += 1
            tokens.append(_Token("UNIT", text[i + 1 : j]))
            i = j + 1 if j < n else j
            continue
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = re.match(r"(\d+\.?\d*(?:[eE][+-]?\d+)?)", text[i:])
            if m:
                tokens.append(_Token("NUMBER", m.group(1)))
                i += len(m.group(1))
                continue
        if c == ":" and i + 1 < n and text[i + 1] == "=":
            tokens.append(_Token("ASSIGN", ":="))
            i += 2
            continue
        if c in "<>!" and i + 1 < n and text[i + 1] == "=":
            op_map = {"<=": "≤", ">=": "≥", "!=": "≠"}
            tokens.append(_Token("OP", op_map.get(c + "=", c + "=")))
            i += 2
            continue
        if c in "+-*/^=<>":
            tokens.append(_Token("OP", c))
            i += 1
            continue
        if c == "(":
            tokens.append(_Token("LPAREN", "("))
            i += 1
            continue
        if c == ")":
            tokens.append(_Token("RPAREN", ")"))
            i += 1
            continue
        if c == ",":
            tokens.append(_Token("COMMA", ","))
            i += 1
            continue
        if c.isalpha() or c == "_" or ord(c) > 127:
            m = re.match(r"([a-zA-Z_-￿][\w.-￿]*)", text[i:])
            if m:
                tokens.append(_Token("IDENT", m.group(1)))
                i += len(m.group(1))
            else:
                tokens.append(_Token("IDENT", c))
                i += 1
            continue
        i += 1
    return tokens


# ---------------------------------------------------------------------------
# Recursive descent parser
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: list[_Token]):
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Optional[_Token]:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _match(self, ttype: str, value: str | None = None) -> Optional[_Token]:
        tok = self._peek()
        if tok and tok.type == ttype and (value is None or tok.value == value):
            return self._advance()
        return None

    def parse(self) -> Optional[ASTNode]:
        if not self._tokens:
            return None
        return self._parse_statement()

    def _parse_statement(self) -> ASTNode:
        node = self._parse_comparison()
        if self._match("ASSIGN"):
            value = self._parse_comparison()
            return BinaryOp(":", node, value)
        tok = self._peek()
        if tok and tok.type == "OP" and tok.value == "=":
            if self._pos == len(self._tokens) - 1:
                self._advance()
                return Evaluation(node)
            self._advance()
            right = self._parse_comparison()
            return BinaryOp("=", node, right)
        return node

    def _parse_comparison(self) -> ASTNode:
        node = self._parse_additive()
        while True:
            tok = self._peek()
            if tok and tok.type == "OP" and tok.value in ("<", ">", "≤", "≥", "≠"):
                self._advance()
                right = self._parse_additive()
                node = BinaryOp(tok.value, node, right)
            else:
                break
        return node

    def _parse_additive(self) -> ASTNode:
        node = self._parse_multiplicative()
        while True:
            tok = self._peek()
            if tok and tok.type == "OP" and tok.value in ("+", "-"):
                self._advance()
                right = self._parse_multiplicative()
                node = BinaryOp(tok.value, node, right)
            else:
                break
        return node

    def _parse_multiplicative(self) -> ASTNode:
        node = self._parse_power()
        while True:
            tok = self._peek()
            if tok and tok.type == "OP" and tok.value in ("*", "/"):
                self._advance()
                right = self._parse_power()
                node = BinaryOp(tok.value, node, right)
            elif tok and tok.type == "UNIT":
                right = self._parse_power()
                node = BinaryOp("*", node, right)
            else:
                break
        return node

    def _parse_power(self) -> ASTNode:
        node = self._parse_unary()
        tok = self._peek()
        if tok and tok.type == "OP" and tok.value == "^":
            self._advance()
            right = self._parse_power()
            return BinaryOp("^", node, right)
        return node

    def _parse_unary(self) -> ASTNode:
        tok = self._peek()
        if tok and tok.type == "OP" and tok.value == "-":
            self._advance()
            operand = self._parse_unary()
            return UnaryOp("-", operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> ASTNode:
        node = self._parse_primary()
        while (
            self._peek()
            and self._peek().type == "LPAREN"
            and isinstance(node, Variable)
        ):
            self._advance()
            args = self._parse_arglist()
            self._match("RPAREN")
            node = FunctionCall(node.name, args)
        return node

    def _parse_arglist(self) -> list[ASTNode]:
        if self._peek() and self._peek().type == "RPAREN":
            return []
        args = [self._parse_statement()]
        while self._match("COMMA"):
            args.append(self._parse_statement())
        return args

    def _parse_primary(self) -> ASTNode:
        tok = self._peek()
        if tok is None:
            return Number(0)
        if tok.type == "NUMBER":
            self._advance()
            try:
                v = float(tok.value)
                if v == int(v) and "." not in tok.value and "e" not in tok.value.lower():
                    return Number(int(v))
                return Number(v)
            except ValueError:
                return Number(0)
        if tok.type == "STRING":
            self._advance()
            return StringLiteral(tok.value)
        if tok.type == "UNIT":
            self._advance()
            return UnitRef(tok.value)
        if tok.type == "IDENT":
            self._advance()
            return Variable(tok.value)
        if tok.type == "LPAREN":
            self._advance()
            node = self._parse_statement()
            self._match("RPAREN")
            return node
        self._advance()
        return Number(0)


def parse_infix(text: str) -> Optional[ASTNode]:
    """Parse infix expression text into an AST node."""
    text = text.strip()
    if not text:
        return None
    tokens = _tokenize(text)
    if not tokens:
        return None
    return _Parser(tokens).parse()


# ---------------------------------------------------------------------------
# AST to editable text (for round-trip editing)
# ---------------------------------------------------------------------------

_PRECEDENCE = {
    ":": 0, "=": 0, "≡": 0,
    "<": 1, ">": 1, "≤": 1, "≥": 1, "≠": 1,
    "+": 2, "-": 2,
    "*": 3, "/": 3,
    "^": 4,
}


def ast_to_text(node: Optional[ASTNode], parent_prec: int = -1) -> str:
    """Convert an AST node to editable infix text."""
    if node is None:
        return ""
    if isinstance(node, Number):
        v = node.value
        if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return str(v)
    if isinstance(node, Variable):
        return node.name
    if isinstance(node, UnitRef):
        return f"'{node.name}'"
    if isinstance(node, StringLiteral):
        return f'"{node.value}"'
    if isinstance(node, UnaryOp):
        inner = ast_to_text(node.operand, 5)
        if node.operator == "-":
            return f"-{inner}"
        return inner
    if isinstance(node, BinaryOp):
        prec = _PRECEDENCE.get(node.operator, 2)
        left_text = ast_to_text(node.left, prec)
        right_prec = prec + (1 if node.operator != "^" else 0)
        right_text = ast_to_text(node.right, right_prec)
        if node.operator == ":":
            text = f"{left_text} := {right_text}"
        else:
            op = node.operator
            if op == "≤":
                op = "<="
            elif op == "≥":
                op = ">="
            elif op == "≠":
                op = "!="
            text = f"{left_text} {op} {right_text}"
        if prec < parent_prec:
            text = f"({text})"
        return text
    if isinstance(node, FunctionCall):
        args = ", ".join(ast_to_text(a) for a in node.args)
        return f"{node.name}({args})"
    if isinstance(node, Evaluation):
        return f"{ast_to_text(node.expression)} ="
    return str(node)


# ---------------------------------------------------------------------------
# AST to XML <e> elements (postfix, for round-trip saving)
# ---------------------------------------------------------------------------

def ast_to_elements(node: ASTNode) -> list[Element]:
    """Convert an AST node to a list of <e> elements in postfix order."""
    elements: list[Element] = []
    _to_postfix(node, elements)
    return elements


def _to_postfix(node: ASTNode, elements: list[Element]):
    if isinstance(node, Number):
        e = Element("e")
        e.set("type", "operand")
        v = node.value
        if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
            e.text = str(int(v))
        else:
            e.text = str(v)
        elements.append(e)
    elif isinstance(node, Variable):
        e = Element("e")
        e.set("type", "operand")
        e.text = node.name
        elements.append(e)
    elif isinstance(node, UnitRef):
        e = Element("e")
        e.set("type", "operand")
        e.set("style", "unit")
        e.text = node.name
        elements.append(e)
    elif isinstance(node, StringLiteral):
        e = Element("e")
        e.set("type", "operand")
        e.set("style", "string")
        e.text = node.value
        elements.append(e)
    elif isinstance(node, UnaryOp):
        _to_postfix(node.operand, elements)
        e = Element("e")
        e.set("type", "operator")
        e.set("args", "1")
        e.text = node.operator
        elements.append(e)
    elif isinstance(node, BinaryOp):
        _to_postfix(node.left, elements)
        _to_postfix(node.right, elements)
        e = Element("e")
        e.set("type", "operator")
        e.set("args", "2")
        e.text = node.operator
        elements.append(e)
    elif isinstance(node, FunctionCall):
        for arg in node.args:
            _to_postfix(arg, elements)
        e = Element("e")
        e.set("type", "function")
        e.set("args", str(len(node.args)))
        e.text = node.name
        elements.append(e)
    elif isinstance(node, Evaluation):
        _to_postfix(node.expression, elements)
