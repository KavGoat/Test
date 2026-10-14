"""Expression parser and evaluator with unit awareness.

Parses infix expressions with variables, functions, and units.
Evaluates top-left to bottom-right like SMath Studio.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from .units import (
    Quantity, make_quantity, parse_unit,
    add_quantities, subtract_quantities,
    multiply_quantities, divide_quantities,
    power_quantity, quantities_compatible, Unit,
)
from .functions import get_function, FUNCTIONS


class TokenType(Enum):
    NUMBER = auto()
    IDENT = auto()
    UNIT = auto()
    OP = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    ASSIGN = auto()
    DEFINE = auto()
    ARROW = auto()
    COMPARE = auto()
    HASH = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    pos: int = 0


_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ",
    "delta": "δ", "epsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "iota": "ι",
    "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ",
    "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Sigma": "Σ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
}

_KNOWN_UNITS = {
    "m", "mm", "cm", "km", "in", "inch", "ft", "foot", "yd", "yard", "mi", "mile",
    "kg", "g", "mg", "t", "lb", "lbm", "oz",
    "s", "ms", "min", "hr", "h",
    "N", "kN", "MN", "lbf", "kip",
    "Pa", "kPa", "MPa", "GPa", "psi", "ksi", "psf", "pcf", "klf",
    "J", "kJ", "MJ", "cal", "kcal", "BTU",
    "W", "kW", "MW", "hp",
    "A", "mA", "V", "kV", "ohm",
    "K", "degC", "degF",
    "deg", "degree", "rad", "radian",
    "L", "mL", "gal",
    "Hz", "kHz", "MHz", "GHz",
    "m2", "m3", "cm2", "cm3", "mm2", "mm3",
}


def _is_unit_name(name: str) -> bool:
    if name in _KNOWN_UNITS:
        return True
    if parse_unit(name) is not None:
        return True
    return False


def tokenize(expr: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(expr):
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c == '#':
            break
        if c == '-' and i + 1 < len(expr) and expr[i + 1] == '>':
            tokens.append(Token(TokenType.ARROW, "->", i))
            i += 2
            continue
        if c == ':' and i + 1 < len(expr) and expr[i + 1] == '=':
            tokens.append(Token(TokenType.DEFINE, ":=", i))
            i += 2
            continue
        if c == ':' and (i + 1 >= len(expr) or expr[i + 1] == ' '):
            tokens.append(Token(TokenType.DEFINE, ":", i))
            i += 1
            continue
        if c == '<' and i + 1 < len(expr) and expr[i + 1] == '=':
            tokens.append(Token(TokenType.COMPARE, "<=", i))
            i += 2
            continue
        if c == '>' and i + 1 < len(expr) and expr[i + 1] == '=':
            tokens.append(Token(TokenType.COMPARE, ">=", i))
            i += 2
            continue
        if c in ('<', '>'):
            tokens.append(Token(TokenType.COMPARE, c, i))
            i += 1
            continue
        if c == '=' and (i + 1 >= len(expr) or expr[i + 1] != '='):
            if tokens and tokens[-1].type == TokenType.IDENT:
                tokens.append(Token(TokenType.ASSIGN, "=", i))
            else:
                tokens.append(Token(TokenType.COMPARE, "==", i))
            i += 1
            continue
        if c == '=' and i + 1 < len(expr) and expr[i + 1] == '=':
            tokens.append(Token(TokenType.COMPARE, "==", i))
            i += 2
            continue
        if c.isdigit() or (c == '.' and i + 1 < len(expr) and expr[i + 1].isdigit()):
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == '.'):
                j += 1
            if j < len(expr) and expr[j] in ('e', 'E'):
                j += 1
                if j < len(expr) and expr[j] in ('+', '-'):
                    j += 1
                while j < len(expr) and expr[j].isdigit():
                    j += 1
            tokens.append(Token(TokenType.NUMBER, expr[i:j], i))
            i = j
            continue
        if c.isalpha() or c == '_' or c in _GREEK.values():
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] in ('_', '.')):
                j += 1
            name = expr[i:j]
            tokens.append(Token(TokenType.IDENT, name, i))
            i = j
            continue
        if c in ('+', '-', '*', '/', '^'):
            tokens.append(Token(TokenType.OP, c, i))
            i += 1
            continue
        if c == '(':
            tokens.append(Token(TokenType.LPAREN, "(", i))
            i += 1
            continue
        if c == ')':
            tokens.append(Token(TokenType.RPAREN, ")", i))
            i += 1
            continue
        if c == ',':
            tokens.append(Token(TokenType.COMMA, ",", i))
            i += 1
            continue
        i += 1
    tokens.append(Token(TokenType.EOF, "", len(expr)))
    return tokens


@dataclass
class ASTNode:
    pass


@dataclass
class NumberNode(ASTNode):
    value: float


@dataclass
class IdentNode(ASTNode):
    name: str


@dataclass
class UnitAttachNode(ASTNode):
    expr: ASTNode
    unit_name: str


@dataclass
class BinOpNode(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode


@dataclass
class UnaryNode(ASTNode):
    op: str
    operand: ASTNode


@dataclass
class CallNode(ASTNode):
    name: str
    args: list[ASTNode]


@dataclass
class AssignNode(ASTNode):
    name: str
    value: ASTNode
    is_define: bool = False


@dataclass
class CompareNode(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode


@dataclass
class ConvertNode(ASTNode):
    expr: ASTNode
    target_unit: str


@dataclass
class FuncDefNode(ASTNode):
    name: str
    params: list[str]
    body: ASTNode


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, ttype: TokenType) -> Token:
        t = self.advance()
        if t.type != ttype:
            raise SyntaxError(f"Expected {ttype}, got {t.type} '{t.value}'")
        return t

    def parse(self) -> ASTNode:
        node = self.parse_assignment()
        if self.peek().type == TokenType.ARROW:
            self.advance()
            unit_tok = self.expect(TokenType.IDENT)
            unit_parts = [unit_tok.value]
            while self.peek().type == TokenType.OP and self.peek().value in ('*', '/'):
                op = self.advance().value
                next_u = self.expect(TokenType.IDENT)
                unit_parts.append(op)
                unit_parts.append(next_u.value)
                if self.peek().type == TokenType.OP and self.peek().value == '^':
                    self.advance()
                    exp_tok = self.advance()
                    unit_parts.append('^')
                    unit_parts.append(exp_tok.value)
            if self.peek().type == TokenType.OP and self.peek().value == '^':
                self.advance()
                exp_tok = self.advance()
                unit_parts.append('^')
                unit_parts.append(exp_tok.value)
            node = ConvertNode(node, "".join(unit_parts))
        return node

    def parse_assignment(self) -> ASTNode:
        if self.peek().type == TokenType.IDENT:
            name_tok = self.peek()
            saved_pos = self.pos
            self.advance()
            if self.peek().type == TokenType.LPAREN:
                paren_pos = self.pos
                self.advance()
                params = []
                if self.peek().type == TokenType.IDENT:
                    params.append(self.advance().value)
                    while self.peek().type == TokenType.COMMA:
                        self.advance()
                        params.append(self.expect(TokenType.IDENT).value)
                if self.peek().type == TokenType.RPAREN:
                    self.advance()
                    if self.peek().type == TokenType.DEFINE:
                        self.advance()
                        body = self.parse_comparison()
                        return FuncDefNode(name_tok.value, params, body)
                self.pos = paren_pos
            if self.peek().type == TokenType.DEFINE:
                self.advance()
                value = self.parse_comparison()
                return AssignNode(name_tok.value, value, is_define=True)
            if self.peek().type == TokenType.ASSIGN:
                self.advance()
                value = self.parse_comparison()
                return AssignNode(name_tok.value, value, is_define=False)
            self.pos = saved_pos
        return self.parse_comparison()

    def parse_comparison(self) -> ASTNode:
        left = self.parse_expr()
        while self.peek().type == TokenType.COMPARE:
            op = self.advance().value
            right = self.parse_expr()
            left = CompareNode(op, left, right)
        return left

    def parse_expr(self) -> ASTNode:
        left = self.parse_term()
        while self.peek().type == TokenType.OP and self.peek().value in ('+', '-'):
            op = self.advance().value
            right = self.parse_term()
            left = BinOpNode(op, left, right)
        return left

    def parse_term(self) -> ASTNode:
        left = self.parse_unary()
        while self.peek().type == TokenType.OP and self.peek().value in ('*', '/'):
            op = self.advance().value
            right = self.parse_unary()
            left = BinOpNode(op, left, right)
        return left

    def parse_unary(self) -> ASTNode:
        if self.peek().type == TokenType.OP and self.peek().value == '-':
            self.advance()
            operand = self.parse_power()
            return UnaryNode('-', operand)
        return self.parse_power()

    def parse_power(self) -> ASTNode:
        base = self.parse_postfix()
        if self.peek().type == TokenType.OP and self.peek().value == '^':
            self.advance()
            exp = self.parse_unary()
            base = BinOpNode('^', base, exp)
        return base

    def parse_postfix(self) -> ASTNode:
        node = self.parse_primary()
        while self.peek().type == TokenType.IDENT and _is_unit_name(self.peek().value):
            unit_name = self.advance().value
            unit_parts = [unit_name]
            if self.peek().type == TokenType.OP and self.peek().value == '^':
                self.advance()
                exp_tok = self.advance()
                unit_parts.append('^')
                unit_parts.append(exp_tok.value)
            while self.peek().type == TokenType.OP and self.peek().value in ('*', '/'):
                op_tok = self.peek()
                next_pos = self.pos + 1
                if next_pos < len(self.tokens) and self.tokens[next_pos].type == TokenType.IDENT and _is_unit_name(self.tokens[next_pos].value):
                    self.advance()
                    unit_parts.append(op_tok.value)
                    next_unit = self.advance().value
                    unit_parts.append(next_unit)
                    if self.peek().type == TokenType.OP and self.peek().value == '^':
                        self.advance()
                        exp_tok = self.advance()
                        unit_parts.append('^')
                        unit_parts.append(exp_tok.value)
                else:
                    break
            node = UnitAttachNode(node, "".join(unit_parts))
            break
        return node

    def parse_primary(self) -> ASTNode:
        tok = self.peek()
        if tok.type == TokenType.NUMBER:
            self.advance()
            return NumberNode(float(tok.value))
        if tok.type == TokenType.IDENT:
            name = tok.value
            self.advance()
            if self.peek().type == TokenType.LPAREN:
                self.advance()
                args: list[ASTNode] = []
                if self.peek().type != TokenType.RPAREN:
                    args.append(self.parse_comparison())
                    while self.peek().type == TokenType.COMMA:
                        self.advance()
                        args.append(self.parse_comparison())
                self.expect(TokenType.RPAREN)
                return CallNode(name, args)
            return IdentNode(name)
        if tok.type == TokenType.LPAREN:
            self.advance()
            node = self.parse_comparison()
            self.expect(TokenType.RPAREN)
            return node
        if tok.type == TokenType.OP and tok.value == '-':
            self.advance()
            operand = self.parse_primary()
            return UnaryNode('-', operand)
        raise SyntaxError(f"Unexpected token: {tok.type} '{tok.value}'")


def parse(expr: str) -> ASTNode:
    tokens = tokenize(expr)
    parser = Parser(tokens)
    return parser.parse()


@dataclass
class EvalResult:
    value: Quantity
    is_bool: bool = False
    error: Optional[str] = None
    defined_name: Optional[str] = None
    display_text: str = ""


@dataclass
class UserFunction:
    name: str
    params: list[str]
    body: ASTNode


class EvalContext:
    def __init__(self):
        self.variables: dict[str, Quantity] = {}
        self.user_functions: dict[str, UserFunction] = {}
        self.problems: list[str] = []

    def clone(self) -> "EvalContext":
        ctx = EvalContext()
        ctx.variables = dict(self.variables)
        ctx.user_functions = dict(self.user_functions)
        return ctx

    def define(self, name: str, value: Quantity):
        self.variables[name] = value

    def lookup(self, name: str) -> Optional[Quantity]:
        return self.variables.get(name)

    def define_function(self, name: str, params: list[str], body: ASTNode):
        self.user_functions[name] = UserFunction(name, params, body)


def evaluate(node: ASTNode, ctx: EvalContext) -> Quantity:
    if isinstance(node, NumberNode):
        return Quantity(node.value)

    if isinstance(node, IdentNode):
        greek = _GREEK.get(node.name)
        display_name = greek if greek else node.name
        val = ctx.lookup(node.name) or ctx.lookup(display_name)
        if val is None:
            fn_info = get_function(node.name)
            if fn_info and fn_info[1] == 0:
                return fn_info[0]()
            raise NameError(f"Undefined: {node.name}")
        return val

    if isinstance(node, UnitAttachNode):
        val = evaluate(node.expr, ctx)
        unit = parse_unit(node.unit_name)
        if unit is None:
            raise ValueError(f"Unknown unit: {node.unit_name}")
        return Quantity(val.value, unit, unit, user_specified_unit=True)

    if isinstance(node, BinOpNode):
        left = evaluate(node.left, ctx)
        right = evaluate(node.right, ctx)
        if node.op == '+':
            return add_quantities(left, right)
        if node.op == '-':
            return subtract_quantities(left, right)
        if node.op == '*':
            return multiply_quantities(left, right)
        if node.op == '/':
            return divide_quantities(left, right)
        if node.op == '^':
            return power_quantity(left, right.value)
        raise ValueError(f"Unknown operator: {node.op}")

    if isinstance(node, UnaryNode):
        operand = evaluate(node.operand, ctx)
        if node.op == '-':
            return Quantity(-operand.value, operand.unit, operand.display_unit,
                            operand.user_specified_unit)
        raise ValueError(f"Unknown unary: {node.op}")

    if isinstance(node, CallNode):
        ufn = ctx.user_functions.get(node.name)
        if ufn:
            args = [evaluate(a, ctx) for a in node.args]
            local_ctx = ctx.clone()
            for pname, aval in zip(ufn.params, args):
                local_ctx.define(pname, aval)
            return evaluate(ufn.body, local_ctx)
        fn_info = get_function(node.name)
        if fn_info is None:
            raise NameError(f"Unknown function: {node.name}")
        fn, nargs, _ = fn_info
        args = [evaluate(a, ctx) for a in node.args]
        if nargs == -1:
            return fn(*args)
        if len(args) != nargs:
            raise TypeError(f"{node.name} expects {nargs} args, got {len(args)}")
        return fn(*args)

    if isinstance(node, AssignNode):
        value = evaluate(node.value, ctx)
        if not node.is_define:
            existing = ctx.lookup(node.name)
            if existing is not None:
                try:
                    is_eq = abs(existing.value - value.value) < 1e-12
                except Exception:
                    is_eq = False
                return Quantity(1.0 if is_eq else 0.0)
        ctx.define(node.name, value)
        return value

    if isinstance(node, FuncDefNode):
        ctx.define_function(node.name, node.params, node.body)
        return Quantity(0.0)

    if isinstance(node, CompareNode):
        left = evaluate(node.left, ctx)
        right = evaluate(node.right, ctx)
        lv = left.pint_qty.to_base_units().magnitude if not left.dimensionless else left.value
        rv = right.pint_qty.to_base_units().magnitude if not right.dimensionless else right.value
        ops = {
            "<=": lv <= rv, ">=": lv >= rv,
            "<": lv < rv, ">": lv > rv,
            "==": abs(lv - rv) < 1e-12,
        }
        result = ops.get(node.op, False)
        return Quantity(1.0 if result else 0.0)

    if isinstance(node, ConvertNode):
        val = evaluate(node.expr, ctx)
        return val.to(node.target_unit)

    raise TypeError(f"Cannot evaluate: {type(node).__name__}")


def eval_line(line: str, ctx: EvalContext) -> EvalResult:
    line = line.strip()
    if not line or line.startswith('#'):
        return EvalResult(Quantity(0.0), display_text=line)
    comment = ""
    if '#' in line:
        idx = line.index('#')
        comment = line[idx:]
        line = line[:idx].strip()
    try:
        ast = parse(line)
        value = evaluate(ast, ctx)
        displayed = value.auto_display()
        defined = None
        is_bool = False
        if isinstance(ast, AssignNode):
            defined = ast.name
            if not ast.is_define:
                is_bool = True
                displayed = Quantity(1.0 if value.value else 0.0)
        elif isinstance(ast, CompareNode):
            is_bool = True
        elif isinstance(ast, FuncDefNode):
            defined = f"{ast.name}({', '.join(ast.params)})"
        text = f"{'true' if displayed.value else 'false'}" if is_bool else repr(displayed)
        if comment:
            text += f"  {comment}"
        return EvalResult(displayed, is_bool=is_bool, defined_name=defined, display_text=text)
    except Exception as e:
        return EvalResult(Quantity(0.0), error=str(e), display_text=f"Error: {e}")
