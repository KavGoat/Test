"""Spreadsheets in CalcForge: tables on pages and whole spreadsheet pages.

Written from scratch (docs/SPREADSHEET_DESIGN.md). This package is the
engine, with no Qt in it:

    refs.py       A1 addresses and ranges
    values.py     what a cell holds; numbers with units (Qty); Excel's errors
    inputs.py     what a typed entry becomes (5 kN, 12%, 2026-10-09, =A1*2)
    dates.py      Excel's date serial numbers
    formula.py    Excel formulas: tokens, the tree, rewriting references
    evaluate.py   working out a formula's value
    functions.py  Excel's worksheet functions, keeping units
    numfmt.py     Excel number formats
    style.py      how a cell looks, stored once per distinct look
    workbook.py   every sheet and table of a document, kept calculated, with undo
"""
