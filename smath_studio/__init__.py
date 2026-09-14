"""smath_studio -- Pure Python reverse-engineering of SMath Studio worksheets."""

from .parser import parse_file, Worksheet, Region, MathRegion, TextContent
from .expression import (
    ASTNode,
    Number,
    Variable,
    UnitRef,
    StringLiteral,
    BinaryOp,
    UnaryOp,
    FunctionCall,
    Evaluation,
    parse_postfix,
)
from .units import Unit, Dimension, Quantity, UnitRegistry, get_default_registry
from .constants import ConstantsRegistry, get_default_constants
from .context import EvalContext, create_default_context
from .writer import write_file

__version__ = "0.1.0"

__all__ = [
    # Parser
    "parse_file",
    "Worksheet",
    "Region",
    "MathRegion",
    "TextContent",
    # Expression AST
    "ASTNode",
    "Number",
    "Variable",
    "UnitRef",
    "StringLiteral",
    "BinaryOp",
    "UnaryOp",
    "FunctionCall",
    "Evaluation",
    "parse_postfix",
    # Units
    "Unit",
    "Dimension",
    "Quantity",
    "UnitRegistry",
    "get_default_registry",
    # Constants
    "ConstantsRegistry",
    "get_default_constants",
    # Context
    "EvalContext",
    "create_default_context",
    # Writer
    "write_file",
]
