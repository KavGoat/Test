"""Command-line interface for smath_studio."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .parser import parse_file, Worksheet, Region
from .context import create_default_context, EvalContext
from .expression import ASTNode
from .units import Quantity


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="smath-studio",
        description="SMath Studio worksheet evaluator (Python)",
    )
    sub = parser.add_subparsers(dest="command")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate a worksheet and print results")
    p_eval.add_argument("file", help="Path to .sm file")
    p_eval.add_argument("--lang", default="eng", help="Language for text output (default: eng)")

    # info
    p_info = sub.add_parser("info", help="Show worksheet metadata")
    p_info.add_argument("file", help="Path to .sm file")
    p_info.add_argument("--lang", default="eng", help="Preferred language (default: eng)")

    # convert
    p_conv = sub.add_parser("convert", help="Convert worksheet to text")
    p_conv.add_argument("file", help="Path to .sm file")
    p_conv.add_argument("--format", choices=["text", "summary"], default="text")
    p_conv.add_argument("--lang", default="eng", help="Preferred language (default: eng)")

    # parse (debug)
    p_parse = sub.add_parser("parse", help="Parse and dump the AST (debug)")
    p_parse.add_argument("file", help="Path to .sm file")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "convert":
        cmd_convert(args)
    elif args.command == "parse":
        cmd_parse(args)


def cmd_evaluate(args):
    ws = parse_file(args.file)
    ctx = create_default_context()
    ctx._precision = ws.settings.calculation.precision
    ctx._exponential_threshold = ws.settings.calculation.exponential_threshold

    # Sort regions by top then left (natural reading order)
    all_regions = _flatten_regions(ws.regions)
    all_regions.sort(key=lambda r: (r.top, r.left))

    results = []
    for region in all_regions:
        if region.math is not None and region.math.input_expr is not None:
            try:
                val = region.math.input_expr.evaluate(ctx)

                # If this is an evaluation (has result section), display it
                if region.math.result_elements:
                    results.append(("result", _format_value(val, ctx.precision)))
                elif region.math.contract_expr is not None:
                    # Has a contract (unit display) but is an evaluation
                    results.append(("result", _format_value(val, ctx.precision)))
            except Exception as e:
                results.append(("error", str(e)))

    if results:
        for kind, text in results:
            if kind == "error":
                print(f"  ERROR: {text}")
            else:
                print(f"  = {text}")
    else:
        print("No evaluable results found.")


def cmd_info(args):
    ws = parse_file(args.file)
    lang = args.lang

    md = _get_metadata(ws, lang)
    print(f"File: {args.file}")
    print(f"Application: {ws.app_progid} v{ws.app_version}")
    print(f"ID: {ws.settings.identity.id}")
    print(f"Revision: {ws.settings.identity.revision}")
    if md:
        print(f"Title: {md.title}")
        print(f"Author: {md.author}")
        if md.description:
            print(f"Description: {md.description}")
        if md.company:
            print(f"Company: {md.company}")
        if md.keywords:
            print(f"Keywords: {md.keywords}")
    print(f"Precision: {ws.settings.calculation.precision}")
    print(f"Regions: {len(ws.regions)}")

    # Count region types
    all_regions = _flatten_regions(ws.regions)
    n_math = sum(1 for r in all_regions if r.math is not None)
    n_text = sum(1 for r in all_regions if r.text_contents)
    n_plot = sum(1 for r in all_regions if r.plot is not None)
    n_area = sum(1 for r in all_regions if r.area is not None)
    print(f"  Math: {n_math}, Text: {n_text}, Plot: {n_plot}, Area: {n_area}")


def cmd_convert(args):
    ws = parse_file(args.file)
    lang = args.lang

    md = _get_metadata(ws, lang)
    if md and md.title:
        print(f"# {md.title}")
        print()

    all_regions = _flatten_regions(ws.regions)
    all_regions.sort(key=lambda r: (r.top, r.left))

    for region in all_regions:
        if region.text_contents:
            tc = _get_text(region.text_contents, lang)
            if tc:
                for p in tc.paragraphs:
                    prefix = "**" if p.bold else ""
                    suffix = "**" if p.bold else ""
                    print(f"{prefix}{p.text}{suffix}")
                print()

        if region.math is not None and region.math.input_expr is not None:
            expr_str = _expr_to_text(region.math.input_expr)
            if region.math.result_expr is not None:
                result_str = _expr_to_text(region.math.result_expr)
                print(f"  {expr_str} = {result_str}")
            else:
                print(f"  {expr_str}")
            print()


def cmd_parse(args):
    ws = parse_file(args.file)

    all_regions = _flatten_regions(ws.regions)
    all_regions.sort(key=lambda r: (r.top, r.left))

    for region in all_regions:
        if region.math is not None and region.math.input_expr is not None:
            print(f"Region {region.id} (top={region.top}, left={region.left}):")
            print(f"  AST: {region.math.input_expr}")
            print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_regions(regions: list[Region]) -> list[Region]:
    """Flatten nested regions (from area blocks)."""
    result = []
    for r in regions:
        result.append(r)
        if r.children:
            result.extend(_flatten_regions(r.children))
    return result


def _get_metadata(ws: Worksheet, lang: str):
    for md in ws.settings.metadata:
        if md.lang == lang:
            return md
    if ws.settings.metadata:
        return ws.settings.metadata[0]
    return None


def _get_text(contents: list, lang: str):
    for tc in contents:
        if tc.lang == lang:
            return tc
    if contents:
        return contents[0]
    return None


def _format_value(val: Any, precision: int = 4) -> str:
    if isinstance(val, Quantity):
        return f"{val.value:.{precision}g} {val.unit.name}"
    if isinstance(val, float):
        return f"{val:.{precision}g}"
    if isinstance(val, int):
        return str(val)
    try:
        import numpy as np
        if isinstance(val, np.ndarray):
            return str(val)
    except ImportError:
        pass
    return str(val)


def _expr_to_text(node: ASTNode) -> str:
    """Convert an AST node to a human-readable text representation."""
    from .expression import (
        Number, Variable, UnitRef, StringLiteral,
        BinaryOp, UnaryOp, FunctionCall, Evaluation,
    )

    if isinstance(node, Number):
        v = node.value
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v)
    if isinstance(node, Variable):
        return node.name
    if isinstance(node, UnitRef):
        return node.name
    if isinstance(node, StringLiteral):
        return f'"{node.value}"'
    if isinstance(node, UnaryOp):
        return f"-{_expr_to_text(node.operand)}"
    if isinstance(node, BinaryOp):
        left = _expr_to_text(node.left)
        right = _expr_to_text(node.right)
        if node.operator == ":":
            return f"{left} := {right}"
        if node.operator == "^":
            return f"{left}^{right}"
        return f"({left} {node.operator} {right})"
    if isinstance(node, FunctionCall):
        args = ", ".join(_expr_to_text(a) for a in node.args)
        return f"{node.name}({args})"
    if isinstance(node, Evaluation):
        return _expr_to_text(node.expression)
    return repr(node)


if __name__ == "__main__":
    main()
