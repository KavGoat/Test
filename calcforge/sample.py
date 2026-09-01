"""A worked example document, used by Help ▸ Load the worked example."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF

from .core.document import Document, Page, PageScale, PageSetup
from .core.engine import Workspace
from .items.mathitem import MathItem
from .items.plotitem import PlotItem, Series
from .items.measure import MeasureItem
from .items.shapes import RectItem
from .items.tableitem import TableItem
from .items.text import CalloutItem, StampItem, TextItem

BEAM_CALC = """# Span and loading
L = 7.2 m
w_dead = 8.5 kN/m
w_live = 6.0 kN/m
w = 1.2*w_dead + 1.5*w_live   # ULS combination

# Design actions
M_max = w*L^2/8
V_max = w*L/2
M(x) = w*x*(L - x)/2

# Section 356 x 171 x 51 UB
Z_x = 896 cm^3
I_x = 14100 cm^4
E = 205 GPa
f_y = 355 MPa

# Bending check
sigma_b = M_max/Z_x
M_cap = f_y*Z_x
util_b = M_max/M_cap
util_b <= 1.0

# Deflection under live load
delta = 5*w_live*L^4/(384*E*I_x)
delta_lim = L/360
delta <= delta_lim
"""

REACTION_CALC = """# Beam reaction using the table total
q_total = q_floor + 1.0 kPa      # plus an allowance for partitions
b_trib = 3.0 m
L_beam = 7.2 m
w_beam = q_total*b_trib
R = w_beam*L_beam/2
"""

FOUNDATION_CALC = """# Pad footing bearing pressure
N = 780 kN            # column axial load
B = 2.4 m
D = 2.4 m
t = 0.6 m
gamma_c = 24 kN/m^3

W_pad = B*D*t*gamma_c
N_total = N + W_pad
A_base = B*D
q = N_total/A_base
q_allow = 200 kPa
util_q = q/q_allow
q <= q_allow
"""


# At 1:50 one page point represents 17.639 mm, so a 2.4 m pad is 136 pt across.
PAD_PT = 2400.0 / (50.0 * 25.4 / 72.0)
COLUMN_PT = 400.0 / (50.0 * 25.4 / 72.0)


def build_sample() -> Document:
    """Assemble a three-page demonstration document."""
    document = Document()
    document.title = "Worked example"
    document.project = "CalcForge demonstration"
    document.author = "CalcForge"
    document.settings.show_footer = True
    document.settings.footer_left = "{project} — {title}"
    document.settings.footer_right = "Page {page} of {pages}"
    document.settings.default_author = "CalcForge"
    document.settings.math_size = 9.0

    # ---------------------------------------------------------------- page 1
    first = document.pages[0]
    first.setup = PageSetup.from_name("A4")
    first.label = "Beam design"

    beam_heading = _heading("Steel beam design", QPointF(56, 46), 420)
    # One region per line, the way the calculation tool now builds them, so each
    # line can be dragged on its own.
    beam_lines = _as_lines(BEAM_CALC, QPointF(56, 84), label="Beam design")

    moment_plot = PlotItem()
    moment_plot.series = [Series("M", "Bending moment")]
    moment_plot.variable = "x"
    moment_plot.x_from = "0 m"
    moment_plot.x_to = "L"
    moment_plot.title = "Bending moment along the span"
    moment_plot.x_label = "Distance from support"
    moment_plot.setPos(QPointF(300, 470))
    moment_plot.set_local_rect(QRectF(0, 0, 250, 170))

    stamp = StampItem("FOR REVIEW")
    stamp.setPos(QPointF(360, 716))
    stamp.subtext = "CalcForge worked example"

    # ---------------------------------------------------------------- page 2
    second = Page(PageSetup.from_name("A4"))
    second.label = "Load take-down"
    document.pages.append(second)

    table_heading = _heading("Load take-down", QPointF(56, 46), 420)
    loads = TableItem(6, 4)
    loads.title = "Floor build-up"
    loads.setPos(QPointF(56, 96))
    loads.sheet.banded = True
    rows = [
        ["Item", "Thickness", "Density", "Load"],
        ["Slab", "150 mm", "24 kN/m^3", "=B2*C2"],
        ["Screed", "60 mm", "22 kN/m^3", "=B3*C3"],
        ["Finishes", "25 mm", "18 kN/m^3", "=B4*C4"],
        ["Services", "", "", "0.5 kPa"],
        ["Total", "", "", "=SUM(D2:D5)"],
    ]
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            loads.set_cell(row_index, column_index, value)
    loads.sheet.column_units[3] = "kPa"
    loads.sheet.col_widths = {0: 92.0, 1: 78.0, 2: 88.0, 3: 78.0}
    loads.sheet.cells[(5, 0)].fmt.bold = True
    loads.sheet.cells[(5, 3)].fmt.bold = True
    loads.sheet.cells[(5, 3)].fmt.border_top = True
    loads.named_cells = {"q_floor": "D6"}
    loads.label = "Floor build-up"

    note = CalloutItem("Cell D6 is published as the variable q_floor, "
                       "so the calculation below reads it directly.")
    note.setPos(QPointF(392, 150))
    note.set_local_rect(QRectF(0, 0, 160, 62))
    note.leader = [QPointF(-70, 70), QPointF(-24, 34)]
    note.style.stroke = "#e8590c"
    note.style.text_color = "#8a3a06"
    note.style.font_size = 8.0

    reaction = MathItem(REACTION_CALC)
    reaction.setPos(QPointF(56, 258))
    reaction.label = "Beam reaction from the table"
    reaction.style.font_size = 9.0

    hint = _heading("Try it: change a thickness in the table and press F9 — "
                    "the reaction below follows.", QPointF(56, 440), 430, size=10.0,
                    bold=False)
    hint.style.text_color = "#5a6270"

    # ---------------------------------------------------------------- page 3
    third = Page(PageSetup.from_name("A4"))
    third.label = "Foundation"
    third.scale = PageScale.from_ratio(50)
    document.pages.append(third)

    footing_heading = _heading("Pad footing check and site sketch", QPointF(56, 46), 430)
    footing = MathItem(FOUNDATION_CALC)
    footing.setPos(QPointF(56, 84))
    footing.label = "Pad footing"
    footing.style.font_size = 9.0

    column = RectItem("rect", QRectF(0, 0, COLUMN_PT, COLUMN_PT))
    column.setPos(QPointF(96 + (PAD_PT - COLUMN_PT) / 2, 486 + (PAD_PT - COLUMN_PT) / 2))
    column.style.stroke = "#495057"
    column.style.fill = "#adb5bd"
    column.style.fill_opacity = 0.6

    width_dim = MeasureItem("length", [QPointF(0, 0), QPointF(PAD_PT, 0)])
    width_dim.setPos(QPointF(96, 462))
    width_dim.subject = "Pad width"

    area = MeasureItem("area", [QPointF(0, 0), QPointF(PAD_PT, 0), QPointF(PAD_PT, PAD_PT),
                                QPointF(0, PAD_PT)])
    area.setPos(QPointF(96, 486))
    area.subject = "Pad area"
    area.label_offset = QPointF(0, -PAD_PT / 2 + 16)
    area.style.stroke = "#2f9e44"
    area.style.fill = "#8ce99a"

    scale_note = _heading("Drawn at 1:50 — the measurement tools read true "
                          "site dimensions.", QPointF(96, 486 + PAD_PT + 16), 320,
                          size=9.0, bold=False)
    scale_note.style.text_color = "#5a6270"

    cloud = RectItem("cloud", QRectF(0, 0, 190, 74))
    cloud.setPos(QPointF(300, 470))
    cloud.style.stroke = "#e03131"
    cloud.cloud_radius = 8.0
    cloud_text = _heading("Confirm the allowable bearing pressure with the "
                          "geotechnical report.", QPointF(310, 484), 172,
                          size=8.0, bold=False)
    cloud_text.style.text_color = "#a02020"

    first._pending_items = _serialise([beam_heading] + beam_lines
                                      + [moment_plot, stamp])
    second._pending_items = _serialise([table_heading, loads, note, reaction, hint])
    third._pending_items = _serialise([footing_heading, footing, column,
                                       width_dim, area, scale_note, cloud, cloud_text])
    return document


def _as_lines(source: str, origin: QPointF, label: str = "",
              font_size: float = 9.0) -> list[MathItem]:
    """Lay a block of source out as one movable region per line."""
    block = MathItem(source)
    block.style.font_size = font_size
    block.label = label
    block.setPos(origin)
    workspace = Workspace()
    workspace.begin_pass()
    block.refresh(workspace)
    pieces = block.split_lines()
    return pieces or [block]


def _heading(text: str, position: QPointF, width: float, size: float = 16.0,
             bold: bool = True) -> TextItem:
    item = TextItem(text)
    item.style.font_size = size
    item.style.bold = bold
    item.style.stroke = ""
    item.style.fill = ""
    item.style.width = 0.0
    item.setPos(position)
    item.set_local_rect(QRectF(0, 0, width, size * 1.8))
    item.apply_style()
    return item


def _serialise(items) -> list[dict]:
    for index, item in enumerate(items, start=1):
        item.setZValue(index)
    return [item.serialize() for item in items]
