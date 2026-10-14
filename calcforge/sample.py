"""Built-in worked example — a steel beam calculation."""
from __future__ import annotations

from .core.document import Document, Page, Region


def create_sample_document() -> Document:
    doc = Document(
        title="Steel Beam Check",
        author="CalcForge",
        project="Sample",
    )
    page = doc.pages[0]

    page.add_region(Region(
        type="text", x=60, y=40, width=300, height=30,
        data={"text": "Simply Supported Beam — ULS Check", "font_size": 16, "bold": True},
    ))

    page.add_region(Region(
        type="calculation", x=60, y=90, width=400, height=220,
        data={"lines": [
            "L := 7.2 m",
            "w_dead := 8.5 kN/m",
            "w_live := 6.0 kN/m",
            "w := 1.2*w_dead + 1.5*w_live",
            "",
            "M_max := w*L^2/8 -> kN*m",
            "Z_x := 896 cm^3",
            "sigma_b := M_max/Z_x -> MPa",
            "f_y := 355 MPa",
            "sigma_b <= f_y",
        ]},
    ))

    page.add_region(Region(
        type="text", x=60, y=330, width=250, height=24,
        data={"text": "Load take-down table:", "font_size": 11, "bold": True},
    ))

    page.add_region(Region(
        type="table", x=60, y=360, width=400, height=150,
        data={"table": {
            "rows": 4, "cols": 4,
            "col_widths": [100, 80, 100, 100],
            "row_heights": [24, 24, 24, 24],
            "cells": {
                "0,0": {"raw": "Item"},
                "0,1": {"raw": "Thickness"},
                "0,2": {"raw": "Density"},
                "0,3": {"raw": "Load"},
                "1,0": {"raw": "Slab"},
                "1,1": {"raw": "150"},
                "1,2": {"raw": "24"},
                "1,3": {"raw": "=B2*C2"},
                "2,0": {"raw": "Screed"},
                "2,1": {"raw": "60"},
                "2,2": {"raw": "22"},
                "2,3": {"raw": "=B3*C3"},
                "3,0": {"raw": "Total"},
                "3,3": {"raw": "=SUM(D2:D3)"},
            },
        }},
    ))

    page.add_region(Region(
        type="plot", x=60, y=530, width=350, height=230,
        data={
            "expressions": ["w*x*(L-x)/2"],
            "x_var": "x",
            "x_min": 0,
            "x_max": 7.2,
            "title": "Bending Moment Diagram",
            "grid": True,
        },
    ))

    return doc
