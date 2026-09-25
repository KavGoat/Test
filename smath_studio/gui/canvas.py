"""Worksheet canvas for SMath Studio GUI -- renders regions on a scrollable surface."""

from __future__ import annotations

import base64
import copy
import io
import math
import tkinter as tk
from tkinter import ttk, font as tkfont
from typing import Any, Optional

from PIL import Image, ImageTk

from ..parser import Worksheet, Region, TextContent, TextParagraph, MathRegion
from ..context import EvalContext, create_default_context
from ..expression import (
    ASTNode, Number, Variable, UnitRef, StringLiteral,
    BinaryOp, UnaryOp, FunctionCall, Evaluation,
)
from ..units import Quantity
from ..infix_parser import parse_infix, ast_to_text, ast_to_elements
from .math_edit import MathEditor

# Try importing the MathRenderer from the sibling module (another agent's work).
# If unavailable, fall back to plain text rendering.
try:
    from .math_renderer import MathRenderer
    _HAS_MATH_RENDERER = True
except Exception:
    _HAS_MATH_RENDERER = False

# Try importing the plot renderer for matplotlib-based plot rendering.
try:
    from .plot_renderer import render_plot
    from PIL import ImageTk
    _HAS_PLOT_RENDERER = True
except Exception:
    _HAS_PLOT_RENDERER = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CANVAS_BG = "#d4d0c8"
_PAGE_BOUNDARY_COLOR = "#c0c0c0"
_SELECTION_COLOR = "#3366cc"
_SELECTION_DASH = (4, 4)
_GRID_SIZE = 8  # snap grid in pixels
_DEFAULT_REGION_WIDTH = 120
_DEFAULT_REGION_HEIGHT = 24
_REGION_PADDING = 4
_AREA_TRIANGLE_SIZE = 8

# Colors matching SMath Studio conventions
_COMMENT_BG = "#ffff80"
_TITLE_FG = "#0000ff"
_BORDER_BG = "#dddddd"
_UNIT_FG = "#0000ff"
_ERROR_FG = "#ff0000"
_PAGE_SHADOW = "#a0a0a0"
_CURSOR_COLOR = "#ff0000"

_SMATH_BUILTIN_STRINGS = {
    "0": "Contents",
    "1": "1. Introduction",
    "2": "1.1. Entering simple expression",
    "3": "1.2. Using variables",
    "4": "1.3. Using functions",
    "6": "1.5. Using units of measurement",
    "8": "1.7. Working with text regions",
    "17": "4. Mathematical expressions",
    "18": "4.1. Degrees and radians",
    "22": "4.2. Trigonometric functions",
    "23": "4.3. Inverse trig functions",
    "24": "4.4. Hyperbolic functions",
    "25": "4.5. Powers and logarithms",
    "26": "4.6. Derivatives",
    "27": "4.7. Integrals",
    "28": "4.8. Summation and product",
    "29": "4.9. Piecewise functions",
    "30": "4.10. Range variables",
    "31": "4.11. Systems of equations",
    "32": "4.12. Boolean algebra",
    "33": "4.13. Complex numbers",
    "34": "4.14. Strings",
    "35": "5. Matrices and vectors",
    "36": "5.1. Creating matrices",
    "37": "5.2. Matrix operations",
    "38": "5.3. Matrix functions",
    "62": "9. Graphs and charts",
    "63": "9.1. 2D graphs",
    "64": "9.2. Parametric plots",
    "69": "10. Units of measurement",
    "70": "10.1. Defining units",
    "71": "10.2. Unit conversions",
    "78": "13. Calculus",
    "79": "13.1. Integration table",
    "80": "13.2. Differentiation table",
    "89": "16. Programming",
    "93": "16.4. Line function",
    "118": "Converting degrees to radians",
    "119": "Converting radians to degrees",
    "120": "Imaginary unit",
    "121": "Conjugate",
    "122": "Polar form",
    "123": "Example",
    "124": "Determinant",
    "125": "Inverse matrix",
    "126": "Transpose",
    "127": "Eigenvalues",
    "128": "Derivative rules",
    "129": "Chain rule",
    "130": "Product rule",
    "131": "Quotient rule",
    "132": "Higher derivatives",
}


def _snap(value: int, grid: int = _GRID_SIZE) -> int:
    """Snap a coordinate to the nearest grid point."""
    return round(value / grid) * grid


def _z(value: float, zoom: float) -> int:
    """Scale a coordinate by zoom factor."""
    return int(value * zoom)


# ---------------------------------------------------------------------------
# Utility: AST to display text
# ---------------------------------------------------------------------------

def _expr_to_text(node: Optional[ASTNode]) -> str:
    """Convert an AST node to a human-readable string."""
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


def _format_value(val: Any, precision: int = 4, trailing_zeros: bool = True,
                   exp_threshold: int = 5) -> str:
    """Format an evaluated value for display."""
    if isinstance(val, Quantity):
        unit_str = val.display_unit if hasattr(val, 'display_unit') else val.unit.name
        num = _format_number(val.value, precision, trailing_zeros, exp_threshold)
        return f"{num} {unit_str}"
    if isinstance(val, float):
        return _format_number(val, precision, trailing_zeros, exp_threshold)
    if isinstance(val, int):
        if trailing_zeros and precision > 0:
            return f"{val}.{'0' * precision}"
        return str(val)
    try:
        import numpy as np
        if isinstance(val, np.ndarray):
            if val.size <= 20:
                return str(val)
            return f"[{val.shape[0]}x{val.shape[1] if val.ndim > 1 else 1} matrix]"
    except ImportError:
        pass
    return str(val)


def _format_number(val: float, precision: int, trailing_zeros: bool,
                   exp_threshold: int = 5) -> str:
    """Format a float with SMath-style precision."""
    if math.isnan(val):
        return "NaN"
    if math.isinf(val):
        return "Inf" if val > 0 else "-Inf"
    if val != 0 and (abs(val) >= 10 ** exp_threshold or abs(val) < 10 ** -exp_threshold):
        return f"{val:.{precision}e}"
    if trailing_zeros:
        return f"{val:.{precision}f}"
    formatted = f"{val:.{precision}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


# ---------------------------------------------------------------------------
# Rendered-region info (internal bookkeeping for hit testing)
# ---------------------------------------------------------------------------

class _RenderedRegion:
    """Tracks a rendered region's canvas items and source data."""

    __slots__ = ("region", "items", "bbox")

    def __init__(self, region: Region, items: list[int], bbox: tuple[int, int, int, int]):
        self.region = region
        self.items = items  # canvas item ids
        self.bbox = bbox    # (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# WorksheetCanvas
# ---------------------------------------------------------------------------

class WorksheetCanvas(ttk.Frame):
    """Scrollable canvas that renders all regions from a Worksheet."""

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)
        self._worksheet: Optional[Worksheet] = None
        self._ctx: Optional[EvalContext] = create_default_context()
        self._rendered: list[_RenderedRegion] = []
        self._selected_index: Optional[int] = None
        self._selection_items: list[int] = []
        self._photo_cache: list = []

        # Undo/redo stacks
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._max_undo = 50

        # Inline editing state
        self._editing = False
        self._math_editor: Optional[MathEditor] = None
        self._edit_region_idx: Optional[int] = None
        self._edit_mode = "math"
        self._cursor_x = 40
        self._cursor_y = 40
        self._on_modified: Optional[Any] = None
        self._on_navigate: Optional[Any] = None
        self._trailing_zeros = True
        self._fractions_mode = "decimal"
        self._editable = True
        self._filename: str = ""

        # Build rulers and canvas with scrollbars
        _RULER_SIZE = 18
        self._ruler = tk.Canvas(self, height=_RULER_SIZE, bg="#f8f4ec", highlightthickness=0)
        self._v_ruler = tk.Canvas(self, width=_RULER_SIZE, bg="#f8f4ec", highlightthickness=0)
        self._ruler_corner = tk.Frame(self, width=_RULER_SIZE, height=_RULER_SIZE, bg="#f8f4ec")

        self._canvas = tk.Canvas(
            self,
            bg=_CANVAS_BG,
            highlightthickness=0,
            cursor="arrow",
        )
        self._h_scroll = ttk.Scrollbar(
            self, orient=tk.HORIZONTAL, command=self._on_hscroll
        )
        self._v_scroll = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self._on_vscroll
        )
        self._canvas.configure(
            xscrollcommand=self._h_scroll.set,
            yscrollcommand=self._v_scroll.set,
        )

        # Grid layout: corner+rulers on top/left, canvas fills center
        self._ruler_corner.grid(row=0, column=0, sticky="nsew")
        self._ruler.grid(row=0, column=1, sticky="ew")
        self._v_ruler.grid(row=1, column=0, sticky="ns")
        self._canvas.grid(row=1, column=1, sticky="nsew")
        self._v_scroll.grid(row=0, column=2, rowspan=2, sticky="ns")
        self._h_scroll.grid(row=2, column=1, sticky="ew")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Drag state
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Multi-selection
        self._multi_selected: set[int] = set()
        self._multi_selection_items: list[int] = []

        # Hover state
        self._hover_index: Optional[int] = None
        self._hover_items: list[int] = []

        # Selection rubberband state
        self._rubberband = False
        self._rb_start_x = 0
        self._rb_start_y = 0
        self._rb_item: Optional[int] = None

        # Resize state
        self._resizing = False
        self._resize_handle: Optional[str] = None  # e.g. "se", "e", "s"

        # Events
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<Double-Button-1>", self._on_double_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._canvas.bind("<Button-3>", self._on_right_click)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Key>", self._on_key)
        self._canvas.bind("<FocusIn>", lambda e: None)

        # Zoom level
        self._zoom = 1.0
        self._show_grid = True
        self._show_margin = True
        self._show_borders = False

        # Mouse-wheel scrolling
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>", self._on_mousewheel_linux_up)
        self._canvas.bind("<Button-5>", self._on_mousewheel_linux_down)
        self._canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        self._canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        self._canvas.bind("<Control-Button-4>", self._on_ctrl_mousewheel_up)
        self._canvas.bind("<Control-Button-5>", self._on_ctrl_mousewheel_down)

        # Context menu
        self._context_menu = tk.Menu(
            self._canvas, tearoff=0, bg="#ffffff",
            activebackground="#316ac5", activeforeground="white",
            font=("DejaVu Sans", 9),
        )
        self._context_menu.add_command(
            label="Cut", accelerator="Ctrl+X", command=self.cut_selected
        )
        self._context_menu.add_command(
            label="Copy", accelerator="Ctrl+C", command=self.copy_selected
        )
        self._context_menu.add_command(
            label="Paste", accelerator="Ctrl+V", command=self.paste_at_cursor
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Duplicate", command=self.duplicate_selected
        )
        self._context_menu.add_command(
            label="Delete", accelerator="Del", command=self.delete_selected
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Insert Math Region", command=self._ctx_insert_math
        )
        self._context_menu.add_command(
            label="Insert Text Region", command=self._ctx_insert_text
        )
        self._context_menu.add_command(
            label="Insert Comment", command=self._ctx_insert_comment
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Evaluate (F5)", command=self.evaluate_selected
        )
        self._context_menu.add_command(
            label="Recalculate All (F9)", command=self.recalculate
        )
        self._context_menu.add_command(
            label="Lock/Unlock Region", command=self._toggle_lock_selected
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Select All", accelerator="Ctrl+A", command=self.select_all
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Properties...", command=self._show_region_properties
        )

        # Fonts (cached)
        self._font_cache: dict[tuple, tkfont.Font] = {}

        # Math renderer if available
        self._math_renderer = None
        if _HAS_MATH_RENDERER:
            try:
                self._math_renderer = MathRenderer(self._canvas)
            except Exception:
                pass

        # Page layout defaults
        self._page_height = 1100
        self._page_width = 800
        self._page_gap = 8
        self._num_pages = 5

        self._initial_page_drawn = False
        self._canvas.bind("<Map>", self._on_map)
        self._initial_page_after = self._canvas.after(100, self._draw_initial_page)

    def _on_map(self, event=None):
        if not self._initial_page_drawn:
            self._draw_initial_page()

    def _draw_initial_page(self):
        """Draw an initial empty page so the user sees a white workspace."""
        try:
            if not self._canvas.winfo_exists():
                return
        except Exception:
            return
        if self._worksheet is None and not self._rendered and not self._initial_page_drawn:
            self._initial_page_drawn = True
            dummy_ws = Worksheet()
            self._draw_page_background(dummy_ws)
            if self._show_grid:
                self._draw_grid_dots()
            if self._show_margin:
                self._draw_left_margin()
            self._draw_page_boundaries(dummy_ws)
            self._draw_cursor_marker()
            z = self._zoom
            self._canvas.configure(scrollregion=(0, 0, _z(850, z), _z(5540, z)))
            self._canvas.xview_moveto(0)
            self._canvas.yview_moveto(0)
            self._draw_ruler()
            self._draw_v_ruler()

    def destroy(self):
        for attr in ("_blink_after", "_initial_page_after"):
            after_id = getattr(self, attr, None)
            if after_id is not None:
                try:
                    self._canvas.after_cancel(after_id)
                except Exception:
                    pass
                setattr(self, attr, None)
        super().destroy()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_worksheet(self, worksheet: Optional[Worksheet]):
        """Load a worksheet and render all its regions."""
        if worksheet is None:
            worksheet = Worksheet()
        self._worksheet = worksheet
        self._initial_page_drawn = True
        self._ctx = create_default_context()
        self._ctx._precision = worksheet.settings.calculation.precision
        self._ctx._exponential_threshold = worksheet.settings.calculation.exponential_threshold
        self._trailing_zeros = getattr(worksheet.settings.calculation, 'trailing_zeros', True)
        self._fractions_mode = getattr(worksheet.settings.calculation, 'fractions', 'decimal')
        self._editable = getattr(worksheet.settings, 'editable', True)
        self._selected_index = None
        self._evaluate_and_render()
        self._canvas.xview_moveto(0)
        self._canvas.yview_moveto(0)

    def clear(self):
        """Clear the canvas and reset state."""
        self._canvas.delete("all")
        self._rendered.clear()
        self._selection_items.clear()
        self._photo_cache.clear()
        self._selected_index = None
        self._worksheet = None
        self._ctx = None

    def recalculate(self):
        """Re-evaluate all math regions and redraw."""
        if self._worksheet is not None:
            self._ctx = create_default_context()
            self._ctx._precision = self._worksheet.settings.calculation.precision
            self._ctx._exponential_threshold = self._worksheet.settings.calculation.exponential_threshold
            self._trailing_zeros = getattr(self._worksheet.settings.calculation, 'trailing_zeros', False)
            self._fractions_mode = getattr(self._worksheet.settings.calculation, 'fractions', 'decimal')
            self._evaluate_and_render()

    def get_selected_region(self) -> Optional[Region]:
        """Return the currently selected region, or None."""
        if self._selected_index is not None and self._selected_index < len(self._rendered):
            return self._rendered[self._selected_index].region
        return None

    def get_cursor_position(self) -> tuple[int, int]:
        """Return the logical canvas position under the mouse (for status bar)."""
        try:
            x = self._canvas.winfo_pointerx() - self._canvas.winfo_rootx()
            y = self._canvas.winfo_pointery() - self._canvas.winfo_rooty()
            cx = self._unzoom(int(self._canvas.canvasx(x)))
            cy = self._unzoom(int(self._canvas.canvasy(y)))
            return (cx, cy)
        except Exception:
            return (0, 0)

    def get_region_count(self) -> int:
        if self._worksheet:
            return len(self._worksheet.regions)
        return 0

    def get_selected_info(self) -> str:
        """Return a description of the selected region for the status bar."""
        if self._editing:
            return "Editing"
        if self._selected_index is None:
            return "Ready"
        if self._selected_index >= len(self._rendered):
            return "Ready"
        region = self._rendered[self._selected_index].region
        if region.math and region.math.input_expr:
            expr = _expr_to_text(region.math.input_expr)
            if len(expr) > 40:
                expr = expr[:37] + "..."
            return f"Math: {expr}"
        if region.text_contents:
            tc = self._get_text_content(region.text_contents)
            if tc and tc.paragraphs:
                text = tc.paragraphs[0].text
                if len(text) > 40:
                    text = text[:37] + "..."
                return f"Text: {text}"
        return "Selected"

    # ------------------------------------------------------------------
    # Evaluation and rendering
    # ------------------------------------------------------------------

    def _evaluate_and_render(self):
        """Evaluate all math, then render everything."""
        self._canvas.delete("all")
        self._rendered.clear()
        self._selection_items.clear()
        self._hover_items.clear()
        self._hover_index = None
        self._photo_cache.clear()

        # Fresh context each time so evaluation order matters
        if self._worksheet is not None:
            self._ctx = create_default_context()
            self._ctx._precision = self._worksheet.settings.calculation.precision
            self._ctx._exponential_threshold = self._worksheet.settings.calculation.exponential_threshold

        ws = self._worksheet
        if ws is None:
            dummy_ws = Worksheet()
            self._draw_page_background(dummy_ws)
            if self._show_grid:
                self._draw_grid_dots()
            if self._show_margin:
                self._draw_left_margin()
            self._draw_cursor_marker()
            self._update_scroll_region()
            return

        self._draw_page_background(ws)
        if self._show_grid:
            self._draw_grid_dots()
        if self._show_margin:
            self._draw_left_margin()

        # Draw page boundaries
        self._draw_page_boundaries(ws)

        # Flatten regions and sort by reading order (top, then left)
        # Group regions at similar Y positions into the same row
        all_regions = self._flatten_regions(ws.regions)
        row_threshold = 15
        all_regions.sort(key=lambda r: (r.top, r.left))
        if all_regions:
            rows: list[list[Region]] = []
            current_row: list[Region] = [all_regions[0]]
            current_y = all_regions[0].top
            for r in all_regions[1:]:
                if abs(r.top - current_y) <= row_threshold:
                    current_row.append(r)
                else:
                    current_row.sort(key=lambda r: r.left)
                    rows.append(current_row)
                    current_row = [r]
                    current_y = r.top
            current_row.sort(key=lambda r: r.left)
            rows.append(current_row)
            all_regions = []
            for row in rows:
                all_regions.extend(row)

        # Phase 1: evaluate all math regions in order
        eval_results: dict[str, Any] = {}
        for region in all_regions:
            if region.math is not None and region.math.input_expr is not None:
                try:
                    val = region.math.input_expr.evaluate(self._ctx)
                    eval_results[region.id] = val
                except Exception as ex:
                    eval_results[region.id] = ex

        # Phase 2: render each region at its position
        for region in all_regions:
            result = eval_results.get(region.id)
            self._render_region(region, result)

        # Draw the cursor crosshair
        self._draw_cursor_marker()

        # Update scroll region
        self._update_scroll_region()

    def _flatten_regions(self, regions: list[Region]) -> list[Region]:
        """Flatten nested regions from area blocks, hiding collapsed sections."""
        result: list[Region] = []
        skip_until_terminator = False
        for r in regions:
            if r.area is not None:
                if r.area.is_terminator:
                    skip_until_terminator = False
                    result.append(r)
                    continue
                result.append(r)
                if r.area.single:
                    if r.children:
                        result.extend(self._flatten_regions(r.children))
                    continue
                if r.area.collapsed:
                    skip_until_terminator = True
                    continue
                if r.children:
                    result.extend(self._flatten_regions(r.children))
                continue
            if skip_until_terminator:
                continue
            result.append(r)
            if r.children:
                result.extend(self._flatten_regions(r.children))
        return result

    def _draw_page_background(self, ws: Worksheet):
        """Draw white page rectangles with drop shadow on the gray canvas."""
        if ws and ws.settings.page_model.active:
            pw = ws.settings.page_model.paper_width
            ph = ws.settings.page_model.paper_height
        else:
            pw = 800
            ph = 1100

        num_pages = max(5, self._estimate_page_count(ws, ph))
        shadow_w = 3
        page_gap = 8

        z = self._zoom
        for page in range(num_pages):
            page_y = page * (ph + page_gap)
            sw = max(2, _z(shadow_w, z))
            zpw = _z(pw, z)
            zpy = _z(page_y, z)
            zph = _z(page_y + ph, z)
            # Right shadow (gradient: darker near edge, lighter away)
            for si in range(sw):
                alpha = 1.0 - si / sw
                shade = int(160 + (1.0 - alpha) * 60)
                c = f"#{shade:02x}{shade:02x}{shade:02x}"
                self._canvas.create_line(
                    zpw + 1 + si, zpy + si + 2,
                    zpw + 1 + si, zph + 1,
                    fill=c, tags="page_shadow"
                )
            # Bottom shadow (gradient)
            for si in range(sw):
                alpha = 1.0 - si / sw
                shade = int(160 + (1.0 - alpha) * 60)
                c = f"#{shade:02x}{shade:02x}{shade:02x}"
                self._canvas.create_line(
                    si + 2, zph + 1 + si,
                    zpw + 1, zph + 1 + si,
                    fill=c, tags="page_shadow"
                )
            # White page
            self._canvas.create_rectangle(
                0, zpy, zpw, zph,
                fill="#ffffff", outline="#c0c0c0", width=1, tags="page_bg"
            )
            # Page break dashed line at the bottom of each page
            if page < num_pages - 1:
                self._canvas.create_line(
                    0, zph, zpw, zph,
                    fill="#a0a0a0", dash=(4, 3), width=1, tags="page_bounds"
                )
        self._page_height = ph
        self._page_width = pw
        self._page_gap = page_gap
        self._num_pages = num_pages

    def _estimate_page_count(self, ws: Worksheet, ph: int) -> int:
        if ws is None:
            return 5
        max_y = 0
        for r in ws.regions:
            bottom = r.top + r.height
            if bottom > max_y:
                max_y = bottom
        return max(5, (max_y // ph) + 3)

    def _draw_page_boundaries(self, ws: Worksheet):
        """Draw light gray page boundary lines and margin guides."""
        pm = ws.settings.page_model
        pw = pm.paper_width
        ph = pm.paper_height
        ml = pm.margin_left
        mr = pm.margin_right
        mt = pm.margin_top
        mb = pm.margin_bottom

        num_pages = getattr(self, '_num_pages', 5)
        page_gap = getattr(self, '_page_gap', 10)
        z = self._zoom
        for page in range(num_pages):
            page_y = page * (ph + page_gap)
            margin_color = "#e8e8e8"
            if mt > 0:
                self._canvas.create_line(
                    _z(ml, z), _z(page_y + mt, z),
                    _z(pw - mr, z), _z(page_y + mt, z),
                    fill=margin_color, dash=(1, 4), tags="page_bounds"
                )
            if mb > 0:
                self._canvas.create_line(
                    _z(ml, z), _z(page_y + ph - mb, z),
                    _z(pw - mr, z), _z(page_y + ph - mb, z),
                    fill=margin_color, dash=(1, 4), tags="page_bounds"
                )
            if ml > 0:
                self._canvas.create_line(
                    _z(ml, z), _z(page_y, z),
                    _z(ml, z), _z(page_y + ph, z),
                    fill=margin_color, dash=(1, 4), tags="page_bounds"
                )
            if mr > 0:
                self._canvas.create_line(
                    _z(pw - mr, z), _z(page_y, z),
                    _z(pw - mr, z), _z(page_y + ph, z),
                    fill=margin_color, dash=(1, 4), tags="page_bounds"
                )

        self._draw_headers_footers(ws)

    def _draw_headers_footers(self, ws: Worksheet):
        """Draw header and footer text on each page."""
        pm = ws.settings.page_model
        if pm.header is None and pm.footer is None:
            return
        pw = pm.paper_width
        ph = pm.paper_height
        ml = pm.margin_left
        mr = pm.margin_right
        mt = pm.margin_top
        mb = pm.margin_bottom
        num_pages = getattr(self, '_num_pages', 5)
        page_gap = getattr(self, '_page_gap', 10)
        z = self._zoom
        fs = max(7, _z(8, z))
        fnt = ("DejaVu Sans", fs)

        import datetime
        now = datetime.datetime.now()
        filename = ""
        if self._worksheet is not None:
            filename = getattr(self, '_filename', '') or 'Untitled'

        for page in range(num_pages):
            page_y = page * (ph + page_gap)
            page_num = page + 1

            for hf, y_offset in [
                (pm.header, page_y + mt // 2),
                (pm.footer, page_y + ph - mb // 2),
            ]:
                if hf is None:
                    continue
                text = hf.text
                text = text.replace("&[DATE]", now.strftime("%Y-%m-%d"))
                text = text.replace("&[TIME]", now.strftime("%H:%M"))
                text = text.replace("&[FILENAME]", filename)
                text = text.replace("&[PAGENUM]", str(page_num))
                text = text.replace("&[COUNT]", str(num_pages))

                anchor_map = {"Left": "w", "Center": "center", "Right": "e"}
                anc = anchor_map.get(hf.alignment, "center")
                if anc == "w":
                    tx = _z(ml, z)
                elif anc == "e":
                    tx = _z(pw - mr, z)
                else:
                    tx = _z(pw // 2, z)
                    anc = tk.CENTER

                self._canvas.create_text(
                    tx, _z(y_offset, z),
                    text=text, anchor=anc, font=fnt,
                    fill=hf.color or "#a9a9a9",
                    tags="page_hf",
                )

    def _draw_grid_dots(self):
        """Draw subtle grid dots on visible pages for alignment like SMath Studio."""
        pw = getattr(self, '_page_width', 800)
        ph = getattr(self, '_page_height', 1100)
        pg = getattr(self, '_page_gap', 10)
        num_pages = getattr(self, '_num_pages', 5)
        grid = _GRID_SIZE * 3
        z = self._zoom
        vis = self._get_visible_area()
        for page in range(min(num_pages, 4)):
            page_y = page * (ph + pg)
            if vis:
                page_top_z = _z(page_y, z)
                page_bot_z = _z(page_y + ph, z)
                if page_bot_z < vis[1] or page_top_z > vis[3]:
                    continue
            for gx in range(grid, pw, grid):
                for gy in range(grid, ph, grid):
                    py = page_y + gy
                    zx = _z(gx, z)
                    zy = _z(py, z)
                    self._canvas.create_oval(
                        zx, zy, zx + 1, zy + 1,
                        fill="#c8c8c8", outline="", tags="grid_dots",
                    )

    def _get_visible_area(self) -> tuple[float, float, float, float] | None:
        try:
            w = self._canvas.winfo_width()
            h = self._canvas.winfo_height()
            if w < 2 or h < 2:
                return None
            x1 = float(self._canvas.canvasx(0))
            y1 = float(self._canvas.canvasy(0))
            x2 = float(self._canvas.canvasx(w))
            y2 = float(self._canvas.canvasy(h))
            return (x1, y1, x2, y2)
        except Exception:
            return None

    def _draw_left_margin(self):
        """Draw left margin lines on each page like SMath Studio."""
        pw = getattr(self, '_page_width', 800)
        ph = getattr(self, '_page_height', 1100)
        pg = getattr(self, '_page_gap', 10)
        num = getattr(self, '_num_pages', 5)
        margin_x = 30
        z = self._zoom
        for page in range(num):
            page_y = page * (ph + pg)
            self._canvas.create_line(
                _z(margin_x, z), _z(page_y, z),
                _z(margin_x, z), _z(page_y + ph, z),
                fill="#e0dcd6", width=1, tags="margin_line"
            )

    def _draw_cursor_marker(self):
        """Draw a blue crosshair cursor at the insertion position (SMath style)."""
        if self._editing:
            return
        x = _z(self._cursor_x, self._zoom)
        y = _z(self._cursor_y, self._zoom)
        sz = max(6, _z(8, self._zoom))
        color = "#0000ff"
        self._canvas.create_line(
            x - sz, y, x + sz, y, fill=color, width=1, tags="cursor_marker"
        )
        self._canvas.create_line(
            x, y - sz, x, y + sz, fill=color, width=1, tags="cursor_marker"
        )
        self._start_cursor_blink()

    def _start_cursor_blink(self):
        """Start blinking the cursor marker."""
        blink_id = getattr(self, "_blink_after", None)
        if blink_id is not None:
            self._canvas.after_cancel(blink_id)
        self._cursor_visible = True
        self._blink_cursor()

    def _blink_cursor(self):
        """Toggle cursor visibility for blink effect."""
        if self._editing:
            return
        try:
            if not self._canvas.winfo_exists():
                return
        except Exception:
            return
        self._cursor_visible = not self._cursor_visible
        state = tk.NORMAL if self._cursor_visible else tk.HIDDEN
        for item_id in self._canvas.find_withtag("cursor_marker"):
            self._canvas.itemconfigure(item_id, state=state)
        self._blink_after = self._canvas.after(530, self._blink_cursor)

    def _ensure_visible(self, x: int, y: int):
        """Scroll the canvas to ensure the given position is visible."""
        try:
            sr = self._canvas.cget("scrollregion")
            if not sr:
                return
            parts = sr.split()
            if len(parts) != 4:
                return
            sx1, sy1, sx2, sy2 = [float(p) for p in parts]
            sw = sx2 - sx1
            sh = sy2 - sy1
            if sw <= 0 or sh <= 0:
                return
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            vx = float(self._canvas.canvasx(0))
            vy = float(self._canvas.canvasy(0))
            margin = 50
            if x < vx + margin or x > vx + cw - margin:
                new_x = max(0, (x - cw / 2 - sx1) / sw)
                self._canvas.xview_moveto(min(new_x, 1.0))
            if y < vy + margin or y > vy + ch - margin:
                new_y = max(0, (y - ch / 2 - sy1) / sh)
                self._canvas.yview_moveto(min(new_y, 1.0))
        except Exception:
            pass

    def _on_hscroll(self, *args):
        self._canvas.xview(*args)
        self._draw_ruler()

    def _on_vscroll(self, *args):
        self._canvas.yview(*args)
        self._draw_v_ruler()

    def _draw_ruler(self):
        """Draw a horizontal ruler showing centimetre ticks."""
        self._ruler.delete("all")
        try:
            x_offset = float(self._canvas.canvasx(0))
        except Exception:
            x_offset = 0
        rw = self._ruler.winfo_width()
        if rw < 10:
            rw = 800
        z = self._zoom
        cm = 37.8 * z
        h = 18
        self._ruler.create_line(0, h - 1, rw, h - 1, fill="#c0b8a8", width=1)
        start_cm = int(x_offset / cm)
        end_cm = int((x_offset + rw) / cm) + 2
        for i in range(max(0, start_cm), end_cm):
            px = i * cm - x_offset
            self._ruler.create_line(px, 4, px, h - 1, fill="#8a8070", width=1)
            if i > 0:
                self._ruler.create_text(
                    px + 3, 2, text=str(i), anchor="nw",
                    font=("DejaVu Sans", 7), fill="#5a5040",
                )
            for sub in range(1, 10):
                spx = px + sub * cm / 10
                tick_h = 6 if sub == 5 else 3
                self._ruler.create_line(spx, h - 1 - tick_h, spx, h - 1, fill="#a09888")

    def _draw_v_ruler(self):
        """Draw a vertical ruler showing centimetre ticks."""
        self._v_ruler.delete("all")
        try:
            y_offset = float(self._canvas.canvasy(0))
        except Exception:
            y_offset = 0
        rh = self._v_ruler.winfo_height()
        if rh < 10:
            rh = 600
        z = self._zoom
        cm = 37.8 * z
        w = 18
        self._v_ruler.create_line(w - 1, 0, w - 1, rh, fill="#c0b8a8", width=1)
        start_cm = int(y_offset / cm)
        end_cm = int((y_offset + rh) / cm) + 2
        for i in range(max(0, start_cm), end_cm):
            py = i * cm - y_offset
            self._v_ruler.create_line(4, py, w - 1, py, fill="#8a8070", width=1)
            if i > 0:
                self._v_ruler.create_text(
                    3, py + 3, text=str(i), anchor="nw",
                    font=("DejaVu Sans", 7), fill="#5a5040", angle=0,
                )
            for sub in range(1, 10):
                spy = py + sub * cm / 10
                tick_w = 6 if sub == 5 else 3
                self._v_ruler.create_line(w - 1 - tick_w, spy, w - 1, spy, fill="#a09888")

    def _update_scroll_region(self):
        """Set the scrollable region to encompass all pages."""
        pw = getattr(self, '_page_width', 850)
        ph = getattr(self, '_page_height', 1100)
        pg = getattr(self, '_page_gap', 10)
        num = getattr(self, '_num_pages', 5)
        z = self._zoom
        total_h = _z(num * (ph + pg), z)
        total_w = _z(pw, z) + 20
        bbox = self._canvas.bbox("all")
        if bbox:
            total_w = max(total_w, bbox[2] + 20)
            total_h = max(total_h, bbox[3] + 50)
        self._canvas.configure(scrollregion=(0, 0, total_w, total_h))
        self._draw_ruler()
        self._draw_v_ruler()

    # ------------------------------------------------------------------
    # Region rendering
    # ------------------------------------------------------------------

    def _render_region(self, region: Region, eval_result: Any = None):
        """Render a single region on the canvas."""
        items: list[int] = []
        x = _z(region.left, self._zoom)
        y = _z(region.top, self._zoom)

        if region.area is not None:
            items = self._render_area(region, x, y)
        elif region.math is not None:
            items = self._render_math(region, x, y, eval_result)
        elif region.text_contents:
            items = self._render_text(region, x, y)
        elif region.plot is not None:
            items = self._render_plot_placeholder(region, x, y)
        elif region.picture is not None:
            items = self._render_picture_placeholder(region, x, y)

        if not items and region.border and region.width > 0:
            line_id = self._canvas.create_line(
                x, y + 2, x + region.width, y + 2,
                fill=region.color or "#aaaaaa", width=1, dash=(4, 2),
            )
            items.append(line_id)

        if items:
            all_bbox = self._canvas.bbox(*items) if items else (x, y, x + 10, y + 10)
            if all_bbox is None:
                all_bbox = (x, y, x + 10, y + 10)
            if self._show_borders:
                pad = 2
                border_id = self._canvas.create_rectangle(
                    all_bbox[0] - pad, all_bbox[1] - pad,
                    all_bbox[2] + pad, all_bbox[3] + pad,
                    outline="#cccccc", width=1, dash=(2, 2),
                )
                items.append(border_id)
                all_bbox = (all_bbox[0] - pad, all_bbox[1] - pad,
                            all_bbox[2] + pad, all_bbox[3] + pad)
            rr = _RenderedRegion(region, items, all_bbox)
            self._rendered.append(rr)

    def _render_text(self, region: Region, x: int, y: int) -> list[int]:
        """Render a text region with wrapping support."""
        items: list[int] = []
        tc = self._get_text_content(region.text_contents)
        if tc is None:
            return items

        fg = region.color if region.color else "#000000"
        bg = region.bg_color if region.bg_color != "#ffffff" else None

        is_title = fg.lower() in ("#0000ff", "#0000cc")
        is_comment = bg and bg.lower() in ("#ffff80", "#ffffcc")
        has_border = region.border

        if is_title:
            fg = _TITLE_FG
        if is_comment and bg is None:
            bg = _COMMENT_BG

        rw = _z(max(region.width, _DEFAULT_REGION_WIDTH), self._zoom)
        rh = _z(max(region.height, _DEFAULT_REGION_HEIGHT), self._zoom)

        zpad = _z(_REGION_PADDING, self._zoom)

        if has_border or bg:
            draw_bg = bg if bg else _BORDER_BG
            outline_color = "#b0b0b0" if is_comment else "#aaaaaa"
            rect_id = self._canvas.create_rectangle(
                x, y, x + rw, y + rh,
                fill=draw_bg,
                outline=outline_color if has_border else "",
                width=1 if has_border else 0,
            )
            items.append(rect_id)

        cy = y + zpad
        wrap_width = max(1, rw - 2 * zpad)
        for para in tc.paragraphs:
            if para.built_in:
                display = _SMATH_BUILTIN_STRINGS.get(para.text)
                if para.href and para.href.endswith(".sm"):
                    if display is None:
                        display = para.href.replace(".sm", "").replace("_", ".")
                        if display == "contents":
                            display = "Contents"
                    fnt = self._get_font(region.font_size, para.bold, False, underline=True)
                    text_id = self._canvas.create_text(
                        x + zpad, cy, text=display, anchor=tk.NW,
                        font=fnt, fill="#0066cc", width=wrap_width,
                    )
                    href = para.href
                    self._canvas.tag_bind(text_id, "<Button-1>", lambda e, url=href: self._open_link(url))
                    self._canvas.tag_bind(text_id, "<Enter>", lambda e: self._canvas.configure(cursor="hand2"))
                    self._canvas.tag_bind(text_id, "<Leave>", lambda e: self._canvas.configure(cursor=""))
                    items.append(text_id)
                    bbox = self._canvas.bbox(text_id)
                    if bbox:
                        cy = bbox[3] + 2
                    else:
                        cy += region.font_size + 4
                elif display is not None:
                    fnt = self._get_font(region.font_size, para.bold, para.italic)
                    text_id = self._canvas.create_text(
                        x + zpad, cy, text=display, anchor=tk.NW,
                        font=fnt, fill=fg, width=wrap_width,
                    )
                    items.append(text_id)
                    bbox = self._canvas.bbox(text_id)
                    if bbox:
                        cy = bbox[3] + 2
                    else:
                        cy += region.font_size + 4
                continue
            fnt = self._get_font(region.font_size, para.bold, para.italic)
            text_color = fg
            if para.href:
                text_color = "#0066cc"
                fnt = self._get_font(region.font_size, para.bold, para.italic, underline=True)
            if is_title:
                anchor = tk.N
                tx = x + rw // 2
                justify = tk.CENTER
            else:
                anchor = tk.NW
                tx = x + zpad
                justify = tk.LEFT
            text_id = self._canvas.create_text(
                tx, cy,
                text=para.text,
                anchor=anchor,
                font=fnt,
                fill=text_color,
                width=wrap_width,
                justify=justify,
            )
            if para.href:
                href = para.href
                self._canvas.tag_bind(text_id, "<Button-1>", lambda e, url=href: self._open_link(url))
                self._canvas.tag_bind(text_id, "<Enter>", lambda e: self._canvas.configure(cursor="hand2"))
                self._canvas.tag_bind(text_id, "<Leave>", lambda e: self._canvas.configure(cursor=""))
            items.append(text_id)
            bbox = self._canvas.bbox(text_id)
            if bbox:
                cy = bbox[3] + 2
            else:
                cy += region.font_size + 4

        return items

    def _render_math(self, region: Region, x: int, y: int, eval_result: Any) -> list[int]:
        """Render a math region with input expression and optional result."""
        items: list[int] = []
        math_data = region.math
        if math_data is None:
            return items

        # Determine if this region expects a visible result
        expects_result = bool(
            math_data.result_elements
            or math_data.result_expr is not None
            or (math_data.input_expr is not None
                and isinstance(math_data.input_expr, Evaluation))
        )

        # Only show results for regions that explicitly expect them (have = sign)
        display_result = eval_result
        if not expects_result:
            display_result = None

        # Handle showInputData=False: only show the result value
        zpad = _z(_REGION_PADDING, self._zoom)
        if region.show_input_data is not None and not region.show_input_data:
            if display_result is not None and not isinstance(display_result, Exception):
                precision = self._ctx.precision if self._ctx else 4
                et = getattr(self._ctx, '_exponential_threshold', 5) if self._ctx else 5
                result_text = _format_value(display_result, precision, self._trailing_zeros, et)
                fnt = self._get_font(region.font_size, bold=False, italic=False)
                text_id = self._canvas.create_text(
                    x + zpad, y + zpad,
                    text=result_text, anchor=tk.NW, font=fnt,
                    fill=region.color or "#000000",
                )
                return [text_id]

        # Try the dedicated math renderer first
        zoomed_font_size = max(6, int(region.font_size * self._zoom))
        if self._math_renderer is not None:
            try:
                tz = self._trailing_zeros
                if hasattr(math_data, 'trailing_zeros') and math_data.trailing_zeros is not None:
                    tz = math_data.trailing_zeros
                et = getattr(self._ctx, '_exponential_threshold', 5) if self._ctx else 5
                fm = self._fractions_mode if hasattr(self, '_fractions_mode') else "decimal"
                rendered_items = self._math_renderer.render(
                    self._canvas, math_data, x, y, display_result,
                    font_size=zoomed_font_size,
                    color=region.color,
                    trailing_zeros=tz,
                    exp_threshold=et,
                    fractions_mode=fm,
                )
                if rendered_items:
                    return rendered_items
            except Exception:
                pass  # Fall through to plain text rendering

        # Plain text fallback rendering
        fnt = self._get_font(region.font_size, bold=False, italic=True)
        fnt_bold = self._get_font(region.font_size, bold=True, italic=False)
        fnt_unit = self._get_font(region.font_size, bold=False, italic=False)

        fg = region.color if region.color else "#000000"
        cx = x + zpad
        cy = y + zpad

        # Render input expression
        input_text = _expr_to_text(math_data.input_expr)
        if input_text:
            text_id = self._canvas.create_text(
                cx, cy,
                text=input_text,
                anchor=tk.NW,
                font=fnt,
                fill=fg,
            )
            items.append(text_id)
            bbox = self._canvas.bbox(text_id)
            if bbox:
                cx = bbox[2] + 4

        # Render result if this is an evaluation
        has_result = (
            math_data.result_elements
            or math_data.result_expr is not None
            or (math_data.input_expr is not None
                and isinstance(math_data.input_expr, BinaryOp)
                and math_data.input_expr.operator == "=")
        )

        if has_result and display_result is not None:
            # Draw equals sign
            eq_id = self._canvas.create_text(
                cx, cy,
                text=" = ",
                anchor=tk.NW,
                font=fnt,
                fill=fg,
            )
            items.append(eq_id)
            bbox = self._canvas.bbox(eq_id)
            if bbox:
                cx = bbox[2] + 2

            # Draw result value
            if isinstance(display_result, Exception):
                result_text = f"Error: {display_result}"
                result_fg = _ERROR_FG
            else:
                precision = self._ctx.precision if self._ctx else 4
                et = getattr(self._ctx, '_exponential_threshold', 5) if self._ctx else 5
                result_text = _format_value(display_result, precision, self._trailing_zeros, et)
                result_fg = fg

            result_id = self._canvas.create_text(
                cx, cy,
                text=result_text,
                anchor=tk.NW,
                font=fnt_bold,
                fill=result_fg,
            )
            items.append(result_id)

        # Render description if present
        if math_data.descriptions:
            for desc in math_data.descriptions:
                if desc.active and desc.text:
                    desc_fnt = self._get_font(
                        max(region.font_size - 1, 8), bold=False, italic=False
                    )
                    # Calculate position for description
                    all_bbox = self._canvas.bbox(*items) if items else None
                    if all_bbox and desc.position == "Right":
                        dx = all_bbox[2] + 8
                        dy = y + _REGION_PADDING
                    else:
                        dx = x + _REGION_PADDING
                        dy = (all_bbox[3] + 4) if all_bbox else (y + _REGION_PADDING)
                    desc_id = self._canvas.create_text(
                        dx, dy,
                        text=desc.text,
                        anchor=tk.NW,
                        font=desc_fnt,
                        fill="#666666",
                    )
                    items.append(desc_id)

        return items

    def _render_area(self, region: Region, x: int, y: int) -> list[int]:
        """Render an area (collapsible section) marker."""
        items: list[int] = []
        area = region.area
        if area is None:
            return items

        z = self._zoom
        ts = _z(_AREA_TRIANGLE_SIZE, z)

        if area.is_terminator or area.single:
            w = _z(max(region.width, 200), z)
            line_id = self._canvas.create_line(
                x, y, x + w, y,
                fill="#b0b0b0", dash=(3, 3), width=1
            )
            items.append(line_id)
        else:
            collapsed = area.collapsed

            if collapsed:
                tri_id = self._canvas.create_polygon(
                    x, y,
                    x + ts, y + ts // 2,
                    x, y + ts,
                    fill="#6a6a6a", outline="#5a5a5a", width=1,
                )
            else:
                tri_id = self._canvas.create_polygon(
                    x, y,
                    x + ts, y,
                    x + ts // 2, y + ts,
                    fill="#6a6a6a", outline="#5a5a5a", width=1,
                )
            items.append(tri_id)
            self._canvas.tag_bind(tri_id, "<Button-1>",
                                  lambda e, r=region: self._toggle_area_collapse(r))

            label = ""
            if area.show_name and area.name:
                label = area.name
            if not label:
                tc = self._get_text_content(region.text_contents)
                if tc and tc.paragraphs:
                    label = tc.paragraphs[0].text
            if label:
                fnt = self._get_font(region.font_size, bold=True, italic=False)
                label_id = self._canvas.create_text(
                    x + ts + _z(6, z), y + 1,
                    text=label,
                    anchor=tk.NW,
                    font=fnt,
                    fill="#333333",
                )
                items.append(label_id)

            w = _z(max(region.width, 200), z)
            line_y = y + ts + _z(3, z)
            line_id = self._canvas.create_line(
                x, line_y, x + w, line_y,
                fill="#b0b0b0", dash=(3, 3), width=1
            )
            items.append(line_id)

        return items

    def _toggle_area_collapse(self, region: Region):
        """Toggle the collapsed state of an area region."""
        if region.area is None:
            return
        self._save_undo_state()
        region.area.collapsed = not region.area.collapsed
        self._mark_modified()
        self._evaluate_and_render()

    def _render_plot_placeholder(self, region: Region, x: int, y: int) -> list[int]:
        """Render a plot region using matplotlib, falling back to a placeholder."""
        items: list[int] = []
        w = _z(max(region.width, 200), self._zoom)
        h = _z(max(region.height, 150), self._zoom)

        # Try to render using matplotlib
        if _HAS_PLOT_RENDERER and region.plot is not None:
            try:
                ctx = self._ctx if self._ctx is not None else create_default_context()
                pil_img = render_plot(region.plot, ctx, width=w, height=h)
                tk_img = ImageTk.PhotoImage(pil_img, master=self._canvas)
                self._photo_cache.append(tk_img)
                img_id = self._canvas.create_image(
                    x, y, image=tk_img, anchor=tk.NW,
                )
                items.append(img_id)
                return items
            except Exception:
                pass  # Fall through to placeholder

        # Fallback: simple placeholder
        rect_id = self._canvas.create_rectangle(
            x, y, x + w, y + h,
            fill="#f8f8f8", outline="#cccccc",
        )
        items.append(rect_id)

        fs = max(7, _z(10, self._zoom))
        label_id = self._canvas.create_text(
            x + w // 2, y + h // 2,
            text="[Plot Region]",
            anchor=tk.CENTER,
            font=("DejaVu Sans", fs, "italic"),
            fill="#999999",
        )
        items.append(label_id)
        return items

    def _render_picture_placeholder(self, region: Region, x: int, y: int) -> list[int]:
        """Render an embedded picture, or a placeholder if decoding fails."""
        items: list[int] = []
        w = _z(max(region.width, 80), self._zoom)
        h = _z(max(region.height, 60), self._zoom)

        pic = region.picture
        if pic is not None and pic.data:
            try:
                raw_bytes = base64.b64decode(pic.data)
                pil_image = Image.open(io.BytesIO(raw_bytes))
                pil_image.thumbnail((w, h), Image.LANCZOS)
                photo = ImageTk.PhotoImage(pil_image, master=self._canvas)
                self._photo_cache.append(photo)
                img_id = self._canvas.create_image(
                    x, y, image=photo, anchor=tk.NW,
                )
                items.append(img_id)
                return items
            except Exception:
                pass

        rect_id = self._canvas.create_rectangle(
            x, y, x + w, y + h,
            fill="#f0f0f0", outline="#cccccc",
        )
        items.append(rect_id)

        fs = max(7, _z(9, self._zoom))
        label_id = self._canvas.create_text(
            x + w // 2, y + h // 2,
            text="[Image]",
            anchor=tk.CENTER,
            font=("DejaVu Sans", fs, "italic"),
            fill="#999999",
        )
        items.append(label_id)
        return items

    # ------------------------------------------------------------------
    # Text content helpers
    # ------------------------------------------------------------------

    def _get_text_content(
        self, contents: list[TextContent], lang: str = "eng"
    ) -> Optional[TextContent]:
        """Pick the best text content, preferring the given language."""
        for tc in contents:
            if tc.lang == lang:
                return tc
        return contents[0] if contents else None

    # ------------------------------------------------------------------
    # Font cache
    # ------------------------------------------------------------------

    def _get_font(
        self, size: int, bold: bool = False, italic: bool = False, underline: bool = False
    ) -> tkfont.Font:
        """Return a cached tkinter Font object, scaled by current zoom."""
        zoomed_size = max(6, int(size * self._zoom))
        key = (zoomed_size, bold, italic, underline)
        if key not in self._font_cache:
            weight = "bold" if bold else "normal"
            slant = "italic" if italic else "roman"
            self._font_cache[key] = tkfont.Font(
                family="DejaVu Sans",
                size=zoomed_size,
                weight=weight,
                slant=slant,
                underline=underline,
            )
        return self._font_cache[key]

    def _is_on_page(self, cx: int, cy: int) -> bool:
        """Check whether canvas coordinates (cx, cy) fall on a white page."""
        pw = _z(getattr(self, '_page_width', 800), self._zoom)
        if cx < 0 or cx > pw:
            return False
        ph = getattr(self, '_page_height', 1100)
        pg = getattr(self, '_page_gap', 10)
        num = getattr(self, '_num_pages', 5)
        z = self._zoom
        for page in range(num):
            page_y = page * (ph + pg)
            top_z = _z(page_y, z)
            bot_z = _z(page_y + ph, z)
            if top_z <= cy <= bot_z:
                return True
        return False

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _select_region(self, index: Optional[int]):
        """Select a region by its rendered index, or deselect if None."""
        # Clear previous selection
        for item_id in self._selection_items:
            self._canvas.delete(item_id)
        self._selection_items.clear()
        self._selected_index = index

        if index is None or index >= len(self._rendered):
            return

        rr = self._rendered[index]
        x1, y1, x2, y2 = rr.bbox
        pad = 3
        sel_rect = self._canvas.create_rectangle(
            x1 - pad, y1 - pad, x2 + pad, y2 + pad,
            outline="#4a6ea9", width=1, dash=(3, 3),
        )
        self._selection_items.append(sel_rect)
        hs = 3
        for hx, hy in [
            (x1 - pad, y1 - pad), (x2 + pad, y1 - pad),
            (x1 - pad, y2 + pad), (x2 + pad, y2 + pad),
            ((x1 + x2) // 2, y1 - pad), ((x1 + x2) // 2, y2 + pad),
            (x1 - pad, (y1 + y2) // 2), (x2 + pad, (y1 + y2) // 2),
        ]:
            h = self._canvas.create_rectangle(
                hx - hs, hy - hs, hx + hs, hy + hs,
                fill="#4a6ea9", outline="#4a6ea9", width=1,
            )
            self._selection_items.append(h)

        if rr.region.locked:
            lock_item = self._canvas.create_text(
                x2 + pad + 10, y1 - pad,
                text="\U0001F512", font=("DejaVu Sans", 8),
                fill="#666666", anchor="nw",
            )
            self._selection_items.append(lock_item)

    def _hit_resize_handle(self, cx: int, cy: int) -> Optional[str]:
        """Check if (cx, cy) is on a resize handle of the selected region.

        Returns a handle id like 'nw', 'n', 'ne', 'w', 'e', 'sw', 's', 'se',
        or None.
        """
        if self._selected_index is None or self._selected_index >= len(self._rendered):
            return None
        rr = self._rendered[self._selected_index]
        x1, y1, x2, y2 = rr.bbox
        pad = 3
        hs = 5
        handles = [
            ("nw", x1 - pad, y1 - pad),
            ("ne", x2 + pad, y1 - pad),
            ("sw", x1 - pad, y2 + pad),
            ("se", x2 + pad, y2 + pad),
            ("n", (x1 + x2) // 2, y1 - pad),
            ("s", (x1 + x2) // 2, y2 + pad),
            ("w", x1 - pad, (y1 + y2) // 2),
            ("e", x2 + pad, (y1 + y2) // 2),
        ]
        for name, hx, hy in handles:
            if abs(cx - hx) <= hs and abs(cy - hy) <= hs:
                return name
        return None

    def _draw_multi_selection(self):
        """Draw selection outlines for all multi-selected regions."""
        self._clear_multi_selection()
        for idx in self._multi_selected:
            if idx >= len(self._rendered):
                continue
            rr = self._rendered[idx]
            x1, y1, x2, y2 = rr.bbox
            pad = 3
            rect = self._canvas.create_rectangle(
                x1 - pad, y1 - pad, x2 + pad, y2 + pad,
                outline="#4a6ea9", dash=(3, 3), width=1,
            )
            self._multi_selection_items.append(rect)

    def _clear_multi_selection(self):
        """Remove multi-selection outlines."""
        for item_id in self._multi_selection_items:
            try:
                self._canvas.delete(item_id)
            except Exception:
                pass
        self._multi_selection_items.clear()

    def _hit_test(self, cx: int, cy: int) -> Optional[int]:
        """Return the index of the rendered region at canvas coords (cx, cy)."""
        # Search in reverse order (top-most rendered last)
        for i in range(len(self._rendered) - 1, -1, -1):
            rr = self._rendered[i]
            x1, y1, x2, y2 = rr.bbox
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return i
        return None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _unzoom(self, val: int) -> int:
        """Convert a zoomed canvas coordinate back to logical coordinate."""
        if self._zoom == 1.0:
            return val
        return int(val / self._zoom)

    def _open_link(self, url: str):
        """Open a hyperlink -- .sm files navigate internally, others use browser."""
        if url.endswith(".sm"):
            if self._on_navigate:
                self._on_navigate(url)
            return
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _on_click(self, event: tk.Event):
        """Handle left-click: commit edit, select region, or set cursor."""
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))
        ctrl = event.state & 0x4

        if self._editing:
            hit = self._hit_test(cx, cy)
            if hit is not None and self._edit_region_idx == hit:
                self._canvas.focus_set()
                return
            self._commit_edit()
            self._canvas.focus_set()

        handle = self._hit_resize_handle(cx, cy)
        if handle is not None:
            if self._selected_index is not None and self._selected_index < len(self._rendered):
                if self._rendered[self._selected_index].region.locked:
                    self._canvas.focus_set()
                    return
            self._resizing = True
            self._resize_handle = handle
            self._drag_start_x = cx
            self._drag_start_y = cy
            self._canvas.focus_set()
            return

        hit = self._hit_test(cx, cy)
        if hit is not None:
            if ctrl:
                if hit in self._multi_selected:
                    self._multi_selected.discard(hit)
                else:
                    self._multi_selected.add(hit)
                    if self._selected_index is not None:
                        self._multi_selected.add(self._selected_index)
                self._select_region(hit)
                self._draw_multi_selection()
            else:
                self._multi_selected.clear()
                self._clear_multi_selection()
                self._select_region(hit)
            self._dragging = False
            self._drag_start_x = cx
            self._drag_start_y = cy
        else:
            self._multi_selected.clear()
            self._clear_multi_selection()
            self._select_region(None)
            self._cursor_x = _snap(self._unzoom(cx))
            self._cursor_y = _snap(self._unzoom(cy))
            self._dragging = False
            self._canvas.delete("cursor_marker")
            self._draw_cursor_marker()
        self._canvas.focus_set()

    def _on_right_click(self, event: tk.Event):
        """Show context menu on right-click."""
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))
        self._right_click_x = _snap(self._unzoom(cx))
        self._right_click_y = _snap(self._unzoom(cy))
        hit = self._hit_test(cx, cy)
        if hit is not None:
            self._select_region(hit)
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    def _ctx_insert_math(self):
        x = getattr(self, "_right_click_x", self._cursor_x)
        y = getattr(self, "_right_click_y", self._cursor_y)
        self._start_editing(x, y, mode="math")

    def _ctx_insert_text(self):
        x = getattr(self, "_right_click_x", self._cursor_x)
        y = getattr(self, "_right_click_y", self._cursor_y)
        self._start_editing(x, y, mode="text")

    def _ctx_insert_comment(self):
        x = getattr(self, "_right_click_x", self._cursor_x)
        y = getattr(self, "_right_click_y", self._cursor_y)
        self._start_editing(x, y, mode="comment")

    def _toggle_lock_selected(self):
        """Toggle the lock state of the selected region."""
        region = self.get_selected_region()
        if region is None:
            return
        region.locked = not region.locked
        self._select_region(self._selected_index)

    def _show_region_properties(self):
        """Show a properties dialog for the selected region."""
        region = self.get_selected_region()
        if region is None:
            return
        dlg = tk.Toplevel(self._canvas)
        dlg.title("Region Properties")
        dlg.resizable(False, False)
        dlg.transient(self._canvas.winfo_toplevel())
        dlg.grab_set()

        frame = tk.Frame(dlg, padx=15, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0
        if region.math is not None:
            rtype = "Math"
        elif region.text_contents:
            rtype = "Text"
        elif region.area:
            rtype = "Area"
        elif region.plot:
            rtype = "Plot"
        elif region.picture:
            rtype = "Picture"
        else:
            rtype = "Region"
        tk.Label(frame, text=f"Type: {rtype}    ID: {region.id}", font=("DejaVu Sans", 9)).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=2
        )

        row += 1
        tk.Label(frame, text="Position:", font=("DejaVu Sans", 9)).grid(
            row=row, column=0, sticky="e", padx=5
        )
        pos_var = tk.StringVar(value=f"{region.left}, {region.top}")
        tk.Entry(frame, textvariable=pos_var, width=15).grid(row=row, column=1, pady=2)

        row += 1
        tk.Label(frame, text="Font Size:", font=("DejaVu Sans", 9)).grid(
            row=row, column=0, sticky="e", padx=5
        )
        size_var = tk.StringVar(value=str(region.font_size))
        tk.Spinbox(frame, from_=6, to=72, textvariable=size_var, width=5).grid(
            row=row, column=1, sticky="w", pady=2
        )

        row += 1
        tk.Label(frame, text="Color:", font=("DejaVu Sans", 9)).grid(
            row=row, column=0, sticky="e", padx=5
        )
        color_var = tk.StringVar(value=region.color or "#000000")
        color_frame = tk.Frame(frame)
        color_frame.grid(row=row, column=1, sticky="w", pady=2)
        color_entry = tk.Entry(color_frame, textvariable=color_var, width=10)
        color_entry.pack(side=tk.LEFT)
        color_swatch = tk.Label(color_frame, text="  ", bg=color_var.get(), relief=tk.SUNKEN, width=3)
        color_swatch.pack(side=tk.LEFT, padx=4)
        def _pick_color():
            from tkinter import colorchooser
            c = colorchooser.askcolor(color=color_var.get(), parent=dlg)
            if c[1]:
                color_var.set(c[1])
                color_swatch.configure(bg=c[1])
        tk.Button(color_frame, text="...", command=_pick_color, width=2).pack(side=tk.LEFT)

        row += 1
        tk.Label(frame, text="Background:", font=("DejaVu Sans", 9)).grid(
            row=row, column=0, sticky="e", padx=5
        )
        bg_var = tk.StringVar(value=region.bg_color or "#ffffff")
        bg_frame = tk.Frame(frame)
        bg_frame.grid(row=row, column=1, sticky="w", pady=2)
        bg_entry = tk.Entry(bg_frame, textvariable=bg_var, width=10)
        bg_entry.pack(side=tk.LEFT)
        bg_swatch = tk.Label(bg_frame, text="  ", bg=bg_var.get(), relief=tk.SUNKEN, width=3)
        bg_swatch.pack(side=tk.LEFT, padx=4)
        def _pick_bg():
            from tkinter import colorchooser
            c = colorchooser.askcolor(color=bg_var.get(), parent=dlg)
            if c[1]:
                bg_var.set(c[1])
                bg_swatch.configure(bg=c[1])
        tk.Button(bg_frame, text="...", command=_pick_bg, width=2).pack(side=tk.LEFT)

        row += 1
        border_var = tk.BooleanVar(value=region.border)
        tk.Checkbutton(frame, text="Show Border", variable=border_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=2
        )

        row += 1
        locked_var = tk.BooleanVar(value=region.locked)
        tk.Checkbutton(frame, text="Locked (prevent moving/editing)", variable=locked_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=2
        )

        dec_var = None
        trailing_var = None
        if region.math is not None:
            row += 1
            tk.Label(frame, text="Decimal Places:", font=("DejaVu Sans", 9)).grid(
                row=row, column=0, sticky="e", padx=5
            )
            dec_val = region.math.decimal_places if region.math.decimal_places else 4
            dec_var = tk.StringVar(value=str(dec_val))
            tk.Spinbox(frame, from_=0, to=15, textvariable=dec_var, width=5).grid(
                row=row, column=1, sticky="w", pady=2
            )

            row += 1
            trailing_var = tk.BooleanVar(value=getattr(region.math, 'trailing_zeros', False))
            tk.Checkbutton(frame, text="Show Trailing Zeros", variable=trailing_var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=2
            )

        row += 1
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0))

        def on_ok():
            try:
                parts = pos_var.get().split(",")
                if len(parts) == 2:
                    region.left = int(parts[0].strip())
                    region.top = int(parts[1].strip())
            except ValueError:
                pass
            try:
                region.font_size = int(size_var.get())
            except ValueError:
                pass
            region.color = color_var.get().strip() or None
            region.bg_color = bg_var.get().strip() or "#ffffff"
            region.border = border_var.get()
            region.locked = locked_var.get()
            if dec_var is not None and region.math is not None:
                try:
                    region.math.decimal_places = int(dec_var.get())
                except ValueError:
                    pass
            if trailing_var is not None and region.math is not None:
                region.math.trailing_zeros = trailing_var.get()
            dlg.destroy()
            self._mark_modified()
            self._evaluate_and_render()

        tk.Button(btn_frame, text="OK", command=on_ok, width=8).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(btn_frame, text="Cancel", command=dlg.destroy, width=8).pack(
            side=tk.LEFT, padx=5
        )
        dlg.bind("<Return>", lambda e: on_ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.wait_window()

    def _on_mousewheel(self, event: tk.Event):
        """Vertical scroll with mouse wheel (Windows/macOS)."""
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._draw_v_ruler()

    def _on_mousewheel_linux_up(self, _event):
        self._canvas.yview_scroll(-4, "units")
        self._draw_v_ruler()

    def _on_mousewheel_linux_down(self, _event):
        self._canvas.yview_scroll(4, "units")
        self._draw_v_ruler()

    def _on_shift_mousewheel(self, event: tk.Event):
        """Horizontal scroll with Shift+mousewheel."""
        self._canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        self._draw_ruler()

    def _on_ctrl_mousewheel(self, event: tk.Event):
        if event.delta > 0:
            self._zoom_at(1.1, event.x, event.y)
        else:
            self._zoom_at(1 / 1.1, event.x, event.y)

    def _on_ctrl_mousewheel_up(self, event):
        self._zoom_at(1.1, getattr(event, 'x', None), getattr(event, 'y', None))

    def _on_ctrl_mousewheel_down(self, event):
        self._zoom_at(1 / 1.1, getattr(event, 'x', None), getattr(event, 'y', None))

    def _zoom_in(self):
        if self._zoom < 3.0:
            self._zoom = min(3.0, self._zoom * 1.1)
            self._apply_zoom()

    def _zoom_out(self):
        if self._zoom > 0.3:
            self._zoom = max(0.3, self._zoom / 1.1)
            self._apply_zoom()

    def _zoom_at(self, factor: float, px=None, py=None):
        old_zoom = self._zoom
        new_zoom = self._zoom * factor
        new_zoom = max(0.3, min(3.0, new_zoom))
        if new_zoom == old_zoom:
            return
        if px is not None and py is not None:
            cx = self._canvas.canvasx(px)
            cy = self._canvas.canvasy(py)
            lx = cx / old_zoom
            ly = cy / old_zoom
        self._zoom = new_zoom
        self._apply_zoom()
        if px is not None and py is not None:
            new_cx = lx * new_zoom
            new_cy = ly * new_zoom
            self._canvas.xview_moveto((new_cx - px) / max(1, self._canvas.winfo_width() * 4))
            self._canvas.yview_moveto((new_cy - py) / max(1, int(self._canvas.cget('scrollregion').split()[3]) if self._canvas.cget('scrollregion') else 5000))

    def _apply_zoom(self):
        self._font_cache.clear()
        self._evaluate_and_render()

    def get_zoom_percent(self) -> int:
        return int(self._zoom * 100)

    def get_current_page(self) -> int:
        """Return the 1-based page number currently visible."""
        try:
            vy = float(self._canvas.canvasy(0))
        except Exception:
            return 1
        ph = getattr(self, '_page_height', 1100)
        pg = getattr(self, '_page_gap', 10)
        z = self._zoom
        y_unzoomed = vy / z if z > 0 else vy
        page = int(y_unzoomed / (ph + pg)) + 1
        return max(1, page)

    _HANDLE_CURSORS = {
        "nw": "top_left_corner", "n": "top_side", "ne": "top_right_corner",
        "w": "left_side", "e": "right_side",
        "sw": "bottom_left_corner", "s": "bottom_side", "se": "bottom_right_corner",
    }

    def _on_motion(self, event: tk.Event):
        """Highlight region under mouse on hover, change cursor for resize handles."""
        if self._editing:
            return
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))

        handle = self._hit_resize_handle(cx, cy)
        if handle:
            self._canvas.config(cursor=self._HANDLE_CURSORS[handle])
        else:
            if self._is_on_page(cx, cy):
                self._canvas.config(cursor="crosshair")
            else:
                self._canvas.config(cursor="arrow")

        hit = self._hit_test(cx, cy)
        if hit != self._hover_index:
            for item_id in self._hover_items:
                try:
                    self._canvas.delete(item_id)
                except Exception:
                    pass
            self._hover_items.clear()
            self._hide_tooltip()
            self._hover_index = hit
            if hit is not None and hit != self._selected_index:
                rr = self._rendered[hit]
                x1, y1, x2, y2 = rr.bbox
                pad = 3
                hover_rect = self._canvas.create_rectangle(
                    x1 - pad, y1 - pad, x2 + pad, y2 + pad,
                    outline="#a0b8d8", width=1, dash=(2, 2),
                )
                self._hover_items.append(hover_rect)
                self._schedule_tooltip(rr.region, event.x_root, event.y_root)

    def _schedule_tooltip(self, region: Region, x: int, y: int):
        self._tooltip_after = self._canvas.after(
            600, lambda: self._show_tooltip(region, x, y)
        )

    def _show_tooltip(self, region: Region, x: int, y: int):
        tip = ""
        if region.math and region.math.descriptions:
            for d in region.math.descriptions:
                if d.text:
                    tip = d.text
                    break
        if not tip:
            return
        self._tooltip_win = tw = tk.Toplevel(self._canvas)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x + 12}+{y + 12}")
        lbl = tk.Label(
            tw, text=tip, justify=tk.LEFT, background="#ffffcc",
            relief=tk.SOLID, borderwidth=1, font=("DejaVu Sans", 8),
            padx=4, pady=2,
        )
        lbl.pack()

    def _hide_tooltip(self):
        after_id = getattr(self, "_tooltip_after", None)
        if after_id:
            self._canvas.after_cancel(after_id)
            self._tooltip_after = None
        tw = getattr(self, "_tooltip_win", None)
        if tw:
            tw.destroy()
            self._tooltip_win = None

    def _draw_snap_guides(self, moving_indices: set[int]):
        """Draw alignment guide lines when a dragged region aligns with others."""
        self._canvas.delete("snap_guide")
        if not self._rendered:
            return
        snap_tolerance = _z(6, self._zoom)
        edges_x: list[int] = []
        edges_y: list[int] = []
        for idx in moving_indices:
            if idx >= len(self._rendered):
                continue
            b = self._rendered[idx].bbox
            edges_x.extend([b[0], (b[0] + b[2]) // 2, b[2]])
            edges_y.extend([b[1], (b[1] + b[3]) // 2, b[3]])
        if not edges_x:
            return
        target_x: set[int] = set()
        target_y: set[int] = set()
        for i, rr in enumerate(self._rendered):
            if i in moving_indices:
                continue
            b = rr.bbox
            target_x.update([b[0], (b[0] + b[2]) // 2, b[2]])
            target_y.update([b[1], (b[1] + b[3]) // 2, b[3]])
        sr = self._canvas.cget("scrollregion")
        if sr:
            parts = sr.split()
            sy2 = int(float(parts[3])) if len(parts) > 3 else 5000
        else:
            sy2 = 5000
        sx2 = _z(getattr(self, '_page_width', 850), self._zoom)
        for ex in edges_x:
            for tx in target_x:
                if abs(ex - tx) <= snap_tolerance:
                    self._canvas.create_line(
                        tx, 0, tx, sy2,
                        fill="#3399ff", dash=(3, 3), width=1, tags="snap_guide",
                    )
                    break
        for ey in edges_y:
            for ty in target_y:
                if abs(ey - ty) <= snap_tolerance:
                    self._canvas.create_line(
                        0, ty, sx2, ty,
                        fill="#3399ff", dash=(3, 3), width=1, tags="snap_guide",
                    )
                    break

    def _clear_snap_guides(self):
        self._canvas.delete("snap_guide")

    def _auto_scroll_on_drag(self, event: tk.Event):
        """Scroll canvas when dragging near edges."""
        margin = 30
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        dx = dy = 0
        if event.x < margin:
            dx = -20
        elif event.x > w - margin:
            dx = 20
        if event.y < margin:
            dy = -20
        elif event.y > h - margin:
            dy = 20
        if dx:
            self._canvas.xview_scroll(dx, "units")
        if dy:
            self._canvas.yview_scroll(dy, "units")

    def _on_drag(self, event: tk.Event):
        """Handle mouse drag to move selected region, resize, or draw rubberband."""
        if self._editing:
            return
        self._auto_scroll_on_drag(event)
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))

        if self._resizing and self._selected_index is not None:
            if self._selected_index >= len(self._rendered):
                self._resizing = False
                return
            rr = self._rendered[self._selected_index]
            region = rr.region
            dx = self._unzoom(cx - self._drag_start_x)
            dy = self._unzoom(cy - self._drag_start_y)
            h = self._resize_handle
            new_w = region.width
            new_h = region.height
            new_left = region.left
            new_top = region.top
            if h in ("e", "ne", "se"):
                new_w = max(20, region.width + dx)
            if h in ("w", "nw", "sw"):
                new_left = region.left + dx
                new_w = max(20, region.width - dx)
            if h in ("s", "se", "sw"):
                new_h = max(10, region.height + dy)
            if h in ("n", "ne", "nw"):
                new_top = region.top + dy
                new_h = max(10, region.height - dy)
            region.left = new_left
            region.top = new_top
            region.width = new_w
            region.height = new_h
            self._drag_start_x = cx
            self._drag_start_y = cy
            self._evaluate_and_render()
            for i, r in enumerate(self._rendered):
                if r.region is region:
                    self._select_region(i)
                    break
            return

        if self._selected_index is not None and not self._rubberband:
            # Moving selected region(s)
            if self._selected_index >= len(self._rendered):
                return
            if self._rendered[self._selected_index].region.locked:
                return
            dx = cx - self._drag_start_x
            dy = cy - self._drag_start_y
            if abs(dx) < 4 and abs(dy) < 4 and not self._dragging:
                return
            self._dragging = True
            indices_to_move = set(self._multi_selected) if self._multi_selected else {self._selected_index}
            indices_to_move.add(self._selected_index)
            for idx in indices_to_move:
                if idx >= len(self._rendered):
                    continue
                rr = self._rendered[idx]
                for item_id in rr.items:
                    self._canvas.move(item_id, dx, dy)
                rr.bbox = (
                    rr.bbox[0] + dx, rr.bbox[1] + dy,
                    rr.bbox[2] + dx, rr.bbox[3] + dy,
                )
            for item_id in self._selection_items:
                self._canvas.move(item_id, dx, dy)
            for item_id in self._multi_selection_items:
                self._canvas.move(item_id, dx, dy)
            self._drag_start_x = cx
            self._drag_start_y = cy
            self._draw_snap_guides(indices_to_move)
        else:
            # Rubberband selection
            if not self._rubberband:
                self._rubberband = True
                self._rb_start_x = cx
                self._rb_start_y = cy
            if self._rb_item is not None:
                self._canvas.delete(self._rb_item)
            self._rb_item = self._canvas.create_rectangle(
                self._rb_start_x, self._rb_start_y, cx, cy,
                outline="#3366cc", fill="#3366cc", stipple="gray12",
                dash=(3, 3), width=1,
            )

    def _on_drag_end(self, event: tk.Event):
        """Snap region to grid after dragging, resize, or complete rubberband selection."""
        self._clear_snap_guides()
        if self._resizing:
            if self._selected_index is not None and self._selected_index < len(self._rendered):
                self._save_undo_state()
                region = self._rendered[self._selected_index].region
                region.left = _snap(region.left)
                region.top = _snap(region.top)
                region.width = _snap(region.width)
                region.height = _snap(region.height)
                self._mark_modified()
                self._evaluate_and_render()
                for i, r in enumerate(self._rendered):
                    if r.region is region:
                        self._select_region(i)
                        break
            self._resizing = False
            self._resize_handle = None
            return
        if self._rubberband:
            cx = int(self._canvas.canvasx(event.x))
            cy = int(self._canvas.canvasy(event.y))
            if self._rb_item is not None:
                self._canvas.delete(self._rb_item)
                self._rb_item = None
            # Select all regions within the rubberband rectangle
            x1 = min(self._rb_start_x, cx)
            y1 = min(self._rb_start_y, cy)
            x2 = max(self._rb_start_x, cx)
            y2 = max(self._rb_start_y, cy)
            self._multi_selected.clear()
            for i, rr in enumerate(self._rendered):
                rx1, ry1, rx2, ry2 = rr.bbox
                if rx1 >= x1 and ry1 >= y1 and rx2 <= x2 and ry2 <= y2:
                    self._multi_selected.add(i)
            if self._multi_selected:
                first = min(self._multi_selected)
                self._select_region(first)
                self._draw_multi_selection()
            self._rubberband = False
            return
        if not self._dragging or self._selected_index is None:
            self._dragging = False
            return
        if self._selected_index >= len(self._rendered):
            self._dragging = False
            return
        self._save_undo_state()
        indices_to_snap = set(self._multi_selected) if self._multi_selected else {self._selected_index}
        indices_to_snap.add(self._selected_index)
        moved_regions = []
        for idx in indices_to_snap:
            if idx >= len(self._rendered):
                continue
            rr = self._rendered[idx]
            rr.region.left = _snap(self._unzoom(rr.bbox[0]))
            rr.region.top = _snap(self._unzoom(rr.bbox[1]))
            moved_regions.append(rr.region)
        self._dragging = False
        self._mark_modified()
        self._evaluate_and_render()
        primary = moved_regions[0] if moved_regions else None
        idx = None
        for i, r in enumerate(self._rendered):
            if r.region is primary:
                idx = i
                break
        self._select_region(idx)
        if self._multi_selected:
            new_multi = set()
            for mr in moved_regions:
                for i, r in enumerate(self._rendered):
                    if r.region is mr:
                        new_multi.add(i)
                        break
            self._multi_selected = new_multi
            self._draw_multi_selection()

    def _on_key(self, event: tk.Event):
        """Handle key events: forward to editor or start new editing."""
        ctrl = event.state & 0x4

        if ctrl and not self._editing:
            keysym = event.keysym.lower()
            shift = event.state & 0x1
            if keysym == "a":
                self.select_all()
                return "break"
            _struct_shortcuts = {
                "m": "_do_matrix",
                "d": "_do_derivative",
                "i": "_do_integral",
            }
            if shift:
                _struct_shortcuts_shift = {
                    "s": "_do_summation",
                    "p": "_do_product",
                }
                method = _struct_shortcuts_shift.get(keysym)
            else:
                method = _struct_shortcuts.get(keysym)
            if method:
                self._start_editing(self._cursor_x, self._cursor_y)
                if self._math_editor:
                    getattr(self._math_editor, method)()
                    self._math_editor._update_eval()
                    self._math_editor.render()
                return "break"
            return None

        if self._editing and self._math_editor is not None:
            result = self._math_editor.handle_key(event)
            if result == "commit":
                self._commit_edit()
            elif result == "cancel":
                self._cancel_edit()
            elif result == "switch_to_text":
                self._switch_math_to_text()
            return "break"

        keysym = event.keysym
        char = event.char

        if keysym == "Escape":
            self._select_region(None)
            return "break"

        if keysym == "Tab":
            self._tab_next_region(shift=bool(event.state & 0x1))
            return "break"

        if keysym == "Delete":
            self.delete_selected()
            return "break"

        if keysym == "Return" or keysym == "KP_Enter":
            if self._selected_index is not None:
                rr = self._rendered[self._selected_index]
                region = rr.region
                if region.math is not None:
                    self._start_editing(
                        region.left, region.top, editing_idx=self._selected_index,
                        ast_node=region.math.input_expr,
                        has_result=bool(region.math.result_elements),
                    )
                elif region.text_contents:
                    tc = self._get_text_content(region.text_contents)
                    text = ""
                    if tc and tc.paragraphs:
                        text = "\n".join(p.text for p in tc.paragraphs)
                    self._start_editing(
                        region.left, region.top, initial_text=text,
                        editing_idx=self._selected_index, mode="text",
                    )
            return "break"

        if keysym in ("Up", "Down", "Left", "Right"):
            step = _GRID_SIZE * 3
            if keysym == "Up":
                self._cursor_y = max(0, self._cursor_y - step)
            elif keysym == "Down":
                self._cursor_y += step
            elif keysym == "Left":
                self._cursor_x = max(0, self._cursor_x - step)
            elif keysym == "Right":
                self._cursor_x += step
            self._canvas.delete("cursor_marker")
            self._draw_cursor_marker()
            self._ensure_visible(_z(self._cursor_x, self._zoom), _z(self._cursor_y, self._zoom))
            hit = self._hit_test(_z(self._cursor_x, self._zoom), _z(self._cursor_y, self._zoom))
            self._select_region(hit)
            return "break"

        if keysym in ("Prior", "Next", "Home", "End"):
            canvas_h = self._canvas.winfo_height()
            page_step = max(100, int(canvas_h / self._zoom))
            if keysym == "Prior":
                self._cursor_y = max(0, self._cursor_y - page_step)
            elif keysym == "Next":
                self._cursor_y += page_step
            elif keysym == "Home":
                self._cursor_x = 20
                self._cursor_y = 20
            elif keysym == "End":
                max_y = 20
                for rr in self._rendered:
                    max_y = max(max_y, self._unzoom(rr.bbox[3]) + 30)
                self._cursor_y = max_y
            self._canvas.delete("cursor_marker")
            self._draw_cursor_marker()
            self._ensure_visible(_z(self._cursor_x, self._zoom), _z(self._cursor_y, self._zoom))
            hit = self._hit_test(_z(self._cursor_x, self._zoom), _z(self._cursor_y, self._zoom))
            self._select_region(hit)
            return "break"

        if keysym == "F2":
            self._start_editing(self._cursor_x, self._cursor_y, mode="text")
            return "break"

        if keysym == "F5":
            self.evaluate_selected()
            return "break"

        if keysym == "F9":
            self.recalculate()
            return "break"

        if char == "'":
            self._start_editing(self._cursor_x, self._cursor_y)
            return "break"

        if char == '"':
            self._start_editing(self._cursor_x, self._cursor_y, mode="text")
            return "break"

        return None

    def _tab_next_region(self, shift: bool = False):
        """Move selection to the next (or previous) region in reading order."""
        if not self._rendered:
            return
        if self._selected_index is None:
            self._select_region(0)
            return
        if shift:
            new_idx = self._selected_index - 1
            if new_idx < 0:
                new_idx = len(self._rendered) - 1
        else:
            new_idx = self._selected_index + 1
            if new_idx >= len(self._rendered):
                new_idx = 0
        self._select_region(new_idx)
        rr = self._rendered[new_idx]
        self._cursor_x = rr.region.left
        self._cursor_y = rr.region.top
        self._canvas.delete("cursor_marker")
        self._draw_cursor_marker()
        self._ensure_visible(_z(self._cursor_x, self._zoom), _z(self._cursor_y, self._zoom))

    def evaluate_selected(self):
        """Evaluate just the selected region (F5)."""
        if self._selected_index is None or self._worksheet is None:
            return
        if self._selected_index >= len(self._rendered):
            return
        region = self._rendered[self._selected_index].region
        if region.math is not None and region.math.input_expr is not None:
            if self._ctx is None:
                self._ctx = create_default_context()
            try:
                region.math.input_expr.evaluate(self._ctx)
            except Exception:
                pass
            self._evaluate_and_render()
            for i, rr in enumerate(self._rendered):
                if rr.region is region:
                    self._select_region(i)
                    break

    def _build_context_up_to(self, edit_y: int, edit_x: int, edit_idx: Optional[int] = None) -> EvalContext:
        """Build an eval context containing only definitions above the editing position."""
        ctx = create_default_context()
        if self._worksheet is None:
            return ctx
        ctx._precision = self._worksheet.settings.calculation.precision
        ctx._exponential_threshold = self._worksheet.settings.calculation.exponential_threshold

        all_regions = self._flatten_regions(self._worksheet.regions)
        row_threshold = 15
        all_regions.sort(key=lambda r: (r.top, r.left))
        if all_regions:
            rows: list[list[Region]] = []
            current_row: list[Region] = [all_regions[0]]
            current_y = all_regions[0].top
            for r in all_regions[1:]:
                if abs(r.top - current_y) <= row_threshold:
                    current_row.append(r)
                else:
                    current_row.sort(key=lambda r2: r2.left)
                    rows.append(current_row)
                    current_row = [r]
                    current_y = r.top
            current_row.sort(key=lambda r2: r2.left)
            rows.append(current_row)
            all_regions = []
            for row in rows:
                all_regions.extend(row)

        for i, region in enumerate(all_regions):
            if edit_idx is not None:
                rr = next((r for r in self._rendered if r.region is region), None)
                if rr is not None:
                    idx = self._rendered.index(rr)
                    if idx >= edit_idx:
                        break
            else:
                if region.top > edit_y or (region.top >= edit_y - row_threshold and region.left >= edit_x):
                    break
            if region.math is not None and region.math.input_expr is not None:
                try:
                    region.math.input_expr.evaluate(ctx)
                except Exception:
                    pass
        return ctx

    def _eval_for_editor(self, expr_text: str) -> Any:
        """Evaluate an expression for the live editor preview."""
        ctx = getattr(self, '_editor_ctx', None) or self._ctx
        if ctx is None:
            return None
        try:
            ast = parse_infix(expr_text)
        except Exception:
            return None
        if ast is None:
            return None
        return ast.evaluate(ctx)

    def _on_double_click(self, event: tk.Event):
        """Handle double-click: edit existing region or create new one."""
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))

        if self._editing:
            if self._edit_region_idx is not None:
                hit = self._hit_test(cx, cy)
                if hit == self._edit_region_idx:
                    self._canvas.focus_set()
                    return
            self._commit_edit()

        hit = self._hit_test(cx, cy)

        if hit is not None and hit < len(self._rendered):
            rr = self._rendered[hit]
            region = rr.region
            if region.locked:
                self._select_region(hit)
                self._canvas.focus_set()
                return
            if region.math is not None:
                if self._try_unit_change(region, rr, cx, cy):
                    return
                self._start_editing(
                    region.left, region.top, editing_idx=hit,
                    ast_node=region.math.input_expr,
                    has_result=bool(region.math.result_elements),
                )
            elif region.text_contents:
                tc = self._get_text_content(region.text_contents)
                text = ""
                if tc and tc.paragraphs:
                    text = "\n".join(p.text for p in tc.paragraphs)
                self._start_editing(
                    region.left, region.top, initial_text=text,
                    editing_idx=hit, mode="text",
                )
        else:
            x = _snap(self._unzoom(cx))
            y = _snap(self._unzoom(cy))
            self._start_editing(x, y)

        self._canvas.focus_set()

    def _try_unit_change(self, region: Region, rr: _RenderedRegion, cx: int, cy: int) -> bool:
        """Check if click is on a result unit; if so, enter edit mode. Returns True if handled."""
        if region.math is None or not region.math.result_elements:
            return False
        x1, y1, x2, y2 = rr.bbox
        mid_x = (x1 + x2) / 2
        if cx < mid_x:
            return False
        return False

    # ------------------------------------------------------------------
    # Public editing API (called by app.py)
    # ------------------------------------------------------------------

    def set_on_modified(self, callback):
        """Set a callback that fires when the worksheet is modified."""
        self._on_modified = callback

    def _mark_modified(self):
        if self._on_modified:
            self._on_modified()

    def _save_undo_state(self):
        """Save a snapshot of the current worksheet for undo."""
        if self._worksheet is None:
            return
        try:
            snapshot = []
            for r in self._worksheet.regions:
                snapshot.append(self._snapshot_region(r))
            self._undo_stack.append(snapshot)
            if len(self._undo_stack) > self._max_undo:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
        except Exception:
            pass

    def _snapshot_region(self, r) -> dict:
        """Create a minimal snapshot of a region's position and expression."""
        snap = {
            "id": r.id, "left": r.left, "top": r.top,
            "width": r.width, "height": r.height,
            "font_size": r.font_size, "color": r.color,
            "bg_color": r.bg_color, "border": r.border,
        }
        if r.math is not None and r.math.input_expr is not None:
            from ..infix_parser import ast_to_text
            snap["math_text"] = ast_to_text(r.math.input_expr)
            snap["has_result"] = bool(r.math.result_elements)
        elif r.text_contents:
            tc = self._get_text_content(r.text_contents)
            if tc and tc.paragraphs:
                snap["text"] = "\n".join(p.text for p in tc.paragraphs)
        children = []
        for c in r.children:
            children.append(self._snapshot_region(c))
        if children:
            snap["children"] = children
        return snap

    def _restore_snapshot(self, snapshot: list):
        """Restore worksheet regions from a snapshot."""
        if self._worksheet is None:
            return
        from ..infix_parser import parse_infix, ast_to_elements
        self._worksheet.regions.clear()
        for snap in snapshot:
            region = Region()
            region.id = snap["id"]
            region.left = snap["left"]
            region.top = snap["top"]
            region.width = snap["width"]
            region.height = snap["height"]
            region.font_size = snap.get("font_size", 10)
            region.color = snap.get("color", "#000000")
            region.bg_color = snap.get("bg_color", "#ffffff")
            region.border = snap.get("border", False)
            if "math_text" in snap:
                ast = parse_infix(snap["math_text"])
                if ast is not None:
                    math_r = MathRegion()
                    math_r.input_expr = ast
                    math_r.input_elements = ast_to_elements(ast)
                    if snap.get("has_result"):
                        math_r.result_elements = list(math_r.input_elements)
                        math_r.result_action = "numeric"
                    region.math = math_r
            elif "text" in snap:
                tc = TextContent(lang="eng")
                for line in snap["text"].split("\n"):
                    tc.paragraphs.append(TextParagraph(text=line))
                region.text_contents.append(tc)
            self._worksheet.regions.append(region)

    def undo(self):
        """Undo the last modification."""
        if not self._undo_stack or self._worksheet is None:
            return
        current = []
        for r in self._worksheet.regions:
            current.append(self._snapshot_region(r))
        self._redo_stack.append(current)
        snapshot = self._undo_stack.pop()
        self._restore_snapshot(snapshot)
        self._evaluate_and_render()

    def redo(self):
        """Redo the last undone modification."""
        if not self._redo_stack or self._worksheet is None:
            return
        current = []
        for r in self._worksheet.regions:
            current.append(self._snapshot_region(r))
        self._undo_stack.append(current)
        snapshot = self._redo_stack.pop()
        self._restore_snapshot(snapshot)
        self._evaluate_and_render()

    def ensure_worksheet(self):
        """Create a worksheet if none exists (for new documents)."""
        if self._worksheet is None:
            self._worksheet = Worksheet()
            self._ctx = create_default_context()

    def select_all(self):
        """Select all regions on the worksheet."""
        if not self._rendered:
            return
        self._multi_selected = set(range(len(self._rendered)))
        if self._rendered:
            self._select_region(0)
            self._draw_multi_selection()

    def _get_selected_regions(self) -> list[Region]:
        """Get the list of currently selected Region objects."""
        indices = set(self._multi_selected)
        if self._selected_index is not None:
            indices.add(self._selected_index)
        return [self._rendered[i].region for i in sorted(indices) if i < len(self._rendered)]

    def align_left(self):
        """Align selected regions to the leftmost region's left edge."""
        regions = self._get_selected_regions()
        if len(regions) < 2:
            return
        self._save_undo_state()
        left = min(r.left for r in regions)
        for r in regions:
            r.left = left
        self._mark_modified()
        self._evaluate_and_render()

    def align_right(self):
        """Align selected regions to the rightmost region's right edge."""
        regions = self._get_selected_regions()
        if len(regions) < 2:
            return
        self._save_undo_state()
        right = max(r.left + r.width for r in regions)
        for r in regions:
            r.left = right - r.width
        self._mark_modified()
        self._evaluate_and_render()

    def align_top(self):
        """Align selected regions to the topmost region's top edge."""
        regions = self._get_selected_regions()
        if len(regions) < 2:
            return
        self._save_undo_state()
        top = min(r.top for r in regions)
        for r in regions:
            r.top = top
        self._mark_modified()
        self._evaluate_and_render()

    def align_bottom(self):
        """Align selected regions to the bottommost region's bottom edge."""
        regions = self._get_selected_regions()
        if len(regions) < 2:
            return
        self._save_undo_state()
        bottom = max(r.top + r.height for r in regions)
        for r in regions:
            r.top = bottom - r.height
        self._mark_modified()
        self._evaluate_and_render()

    def distribute_horizontal(self):
        """Evenly distribute selected regions horizontally."""
        regions = self._get_selected_regions()
        if len(regions) < 3:
            return
        self._save_undo_state()
        regions.sort(key=lambda r: r.left)
        left = regions[0].left
        right = regions[-1].left
        step = (right - left) / (len(regions) - 1)
        for i, r in enumerate(regions):
            r.left = int(left + i * step)
        self._mark_modified()
        self._evaluate_and_render()

    def distribute_vertical(self):
        """Evenly distribute selected regions vertically."""
        regions = self._get_selected_regions()
        if len(regions) < 3:
            return
        self._save_undo_state()
        regions.sort(key=lambda r: r.top)
        top = regions[0].top
        bottom = regions[-1].top
        step = (bottom - top) / (len(regions) - 1)
        for i, r in enumerate(regions):
            r.top = int(top + i * step)
        self._mark_modified()
        self._evaluate_and_render()

    def delete_selected(self):
        """Delete the currently selected region(s)."""
        if self._worksheet is None or not self._editable:
            return
        indices = set(self._multi_selected)
        if self._selected_index is not None:
            indices.add(self._selected_index)
        if not indices:
            return
        self._save_undo_state()
        regions_to_remove = []
        for idx in sorted(indices, reverse=True):
            if idx < len(self._rendered):
                if self._rendered[idx].region.locked:
                    continue
                regions_to_remove.append(self._rendered[idx].region)
        for region in regions_to_remove:
            if region in self._worksheet.regions:
                self._worksheet.regions.remove(region)
            else:
                self._remove_from_children(self._worksheet.regions, region)
        self._selected_index = None
        self._multi_selected.clear()
        self._mark_modified()
        self._evaluate_and_render()

    def duplicate_selected(self):
        """Duplicate the currently selected region(s), offset below."""
        if self._worksheet is None:
            return
        indices = set(self._multi_selected)
        if self._selected_index is not None:
            indices.add(self._selected_index)
        if not indices:
            return
        self._save_undo_state()
        for idx in sorted(indices):
            if idx >= len(self._rendered):
                continue
            src = self._rendered[idx].region
            dup = copy.deepcopy(src)
            dup.id = self._generate_id()
            dup.top = (src.top or 0) + 40
            self._worksheet.regions.append(dup)
        self._mark_modified()
        self._evaluate_and_render()

    def copy_selected(self) -> str:
        """Copy selected region(s) expression to clipboard. Returns the text."""
        indices = set(self._multi_selected)
        if self._selected_index is not None:
            indices.add(self._selected_index)
        if not indices:
            return ""
        texts = []
        for idx in sorted(indices):
            if idx >= len(self._rendered):
                continue
            region = self._rendered[idx].region
            if region.math is not None:
                t = self._region_to_edit_text(region)
                if t:
                    texts.append(t)
            elif region.text_contents:
                tc = self._get_text_content(region.text_contents)
                if tc and tc.paragraphs:
                    texts.append("\n".join(p.text for p in tc.paragraphs))
        text = "\n".join(texts)
        if text:
            try:
                self._canvas.clipboard_clear()
                self._canvas.clipboard_append(text)
            except Exception:
                pass
        return text

    def cut_selected(self):
        """Cut selected region (copy + delete)."""
        self.copy_selected()
        self.delete_selected()

    def paste_at_cursor(self):
        """Paste clipboard text as a math or text region at the cursor position."""
        try:
            text = self._canvas.clipboard_get()
        except Exception:
            return
        if not text or not text.strip():
            return
        self.ensure_worksheet()
        self._save_undo_state()
        ast = parse_infix(text.strip())
        if ast is not None:
            self._create_new_math_region(ast, self._cursor_x, self._cursor_y)
        else:
            region = Region()
            region.id = self._generate_id()
            region.left = self._cursor_x
            region.top = self._cursor_y
            tc = TextContent(lang="eng")
            for line in text.strip().split("\n"):
                tc.paragraphs.append(TextParagraph(text=line))
            region.text_contents.append(tc)
            self._worksheet.regions.append(region)
        self._cursor_y += 30
        self._mark_modified()
        self._evaluate_and_render()

    def insert_math_at(self, x: Optional[int] = None, y: Optional[int] = None):
        """Start editing a new math region at the given or cursor position."""
        if x is None:
            x = self._cursor_x
        if y is None:
            y = self._cursor_y
        self._start_editing(x, y, mode="math")

    def insert_text_at(self, x: Optional[int] = None, y: Optional[int] = None):
        """Start editing a new text region at the given or cursor position."""
        if x is None:
            x = self._cursor_x
        if y is None:
            y = self._cursor_y
        self._start_editing(x, y, mode="text")

    def insert_comment_at(self, x: Optional[int] = None, y: Optional[int] = None):
        """Insert a comment (yellow background text) at the cursor position."""
        if x is None:
            x = self._cursor_x
        if y is None:
            y = self._cursor_y
        self._start_editing(x, y, mode="comment")

    def insert_plot_region(
        self,
        expression: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        x_min: float = -10,
        x_max: float = 10,
        width: int = 400,
        height: int = 300,
    ):
        """Insert a plot region at the cursor position."""
        if x is None:
            x = self._cursor_x
        if y is None:
            y = self._cursor_y
        self.ensure_worksheet()
        self._save_undo_state()
        from ..parser import PlotRegion as PlotRegionData
        ast = parse_infix(expression)
        region = Region()
        region.id = self._generate_id()
        region.left = x
        region.top = y
        region.width = width
        region.height = height
        region.font_size = 10
        plot = PlotRegionData()
        plot.plot_type = "2d"
        plot.input_expr = ast
        if ast is not None:
            plot.input_elements = ast_to_elements(ast)
        plot.attributes = {
            "x_min": str(x_min),
            "x_max": str(x_max),
        }
        region.plot = plot
        self._worksheet.regions.append(region)
        self._cursor_y = y + height + 16
        self._mark_modified()
        self._evaluate_and_render()

    def insert_area_region(self, x: Optional[int] = None, y: Optional[int] = None):
        """Insert an area (collapsible section) start and end marker pair."""
        if x is None:
            x = self._cursor_x
        if y is None:
            y = self._cursor_y
        self.ensure_worksheet()
        self._save_undo_state()

        from ..parser import AreaRegion, TextContent, TextParagraph
        start = Region()
        start.id = self._generate_id()
        start.left = x
        start.top = y
        start.width = 400
        start.height = 16
        start.area = AreaRegion(collapsed=False, is_terminator=False)
        start.text_contents = [TextContent(paragraphs=[TextParagraph(text="Section")])]

        end = Region()
        end.id = self._generate_id()
        end.left = x
        end.top = y + 200
        end.width = 400
        end.height = 4
        end.area = AreaRegion(collapsed=False, is_terminator=True)

        self._worksheet.regions.append(start)
        self._worksheet.regions.append(end)
        self._cursor_y = y + 24
        self._mark_modified()
        self._evaluate_and_render()

    def insert_line_separator(self, x: Optional[int] = None, y: Optional[int] = None):
        """Insert a horizontal line separator at the given or cursor position."""
        if x is None:
            x = self._cursor_x
        if y is None:
            y = self._cursor_y
        self.ensure_worksheet()
        self._save_undo_state()
        region = Region()
        region.id = self._generate_id()
        region.left = x
        region.top = y
        region.width = 400
        region.height = 4
        region.border = True
        region.color = "#aaaaaa"
        self._worksheet.regions.append(region)
        self._cursor_y = y + 16
        self._mark_modified()
        self._evaluate_and_render()

    def insert_picture_region(self, filepath: str, x: Optional[int] = None, y: Optional[int] = None):
        """Insert a picture region from a file path."""
        if x is None:
            x = self._cursor_x
        if y is None:
            y = self._cursor_y
        self.ensure_worksheet()
        self._save_undo_state()
        try:
            img = Image.open(filepath)
            w, h = img.size
            if w > 600:
                ratio = 600 / w
                w = 600
                h = int(h * ratio)
                img = img.resize((w, h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = base64.b64encode(buf.getvalue()).decode("ascii")
            from ..parser import PictureRegion as PicRegion
            region = Region()
            region.id = self._generate_id()
            region.left = x
            region.top = y
            region.width = w
            region.height = h
            region.picture = PicRegion(format="png", encoding="base64", data=data)
            self._worksheet.regions.append(region)
            self._cursor_y = y + h + 16
            self._mark_modified()
            self._evaluate_and_render()
        except Exception as exc:
            import traceback
            traceback.print_exc()

    def insert_symbol(self, symbol: str):
        """Insert a symbol/function into the current editor or create a new region."""
        if self._editing and self._math_editor is not None:
            for ch in symbol:
                fake_event = tk.Event()
                fake_event.keysym = ""
                fake_event.char = ch
                fake_event.state = 0
                self._math_editor.handle_key(fake_event)
            self._math_editor.render()
            self._canvas.focus_set()
        else:
            self._start_editing(self._cursor_x, self._cursor_y, initial_text=symbol)

    # ------------------------------------------------------------------
    # Inline editor
    # ------------------------------------------------------------------

    def _start_editing(
        self,
        x: int,
        y: int,
        initial_text: str = "",
        editing_idx: Optional[int] = None,
        mode: str = "math",
        ast_node: Optional[ASTNode] = None,
        has_result: bool = False,
    ):
        if not self._editable:
            return
        if self._editing:
            self._cancel_edit()

        self._editing = True
        self._edit_region_idx = editing_idx
        self._edit_mode = mode
        self._cursor_x = x
        self._cursor_y = y

        zx = _z(x, self._zoom)
        zy = _z(y, self._zoom)

        if mode in ("text", "comment"):
            self._math_editor = None
            bg_color = "#ffff80" if mode == "comment" else "#fffff0"
            zoomed_text_size = max(8, int(11 * self._zoom))
            self._edit_text_entry = tk.Text(
                self._canvas,
                font=("DejaVu Sans", zoomed_text_size),
                bd=1,
                relief=tk.SOLID,
                highlightthickness=1,
                highlightcolor="#3366cc",
                bg=bg_color,
                width=40,
                height=3,
                wrap=tk.WORD,
                undo=True,
            )
            if initial_text:
                self._edit_text_entry.insert("1.0", initial_text)
            self._edit_text_entry.bind("<Escape>", lambda e: self._cancel_edit())
            self._edit_text_entry.bind(
                "<Control-Return>", lambda e: self._commit_edit()
            )
            self._edit_text_window = self._canvas.create_window(
                zx, zy, window=self._edit_text_entry, anchor=tk.NW
            )
            self._edit_text_entry.focus_set()
            if initial_text:
                self._edit_text_entry.mark_set("insert", "end")
            return

        if editing_idx is not None:
            for item_id in self._rendered[editing_idx].items:
                try:
                    self._canvas.delete(item_id)
                except Exception:
                    pass

        self._editor_ctx = self._build_context_up_to(y, x, editing_idx)
        precision = 4
        if self._editor_ctx:
            precision = getattr(self._editor_ctx, '_precision', 4)
        zoomed_editor_size = max(8, int(12 * self._zoom))
        editor = MathEditor(
            self._canvas, zx, zy,
            font_size=zoomed_editor_size,
            eval_callback=self._eval_for_editor,
            precision=precision,
            eval_context=self._editor_ctx,
        )

        if ast_node is not None:
            editor.from_ast(ast_node, has_result=has_result)
        elif initial_text:
            ast = parse_infix(initial_text)
            if ast is not None:
                editor.from_ast(ast, has_result=initial_text.strip().endswith("="))
            else:
                for ch in initial_text:
                    fake_event = tk.Event()
                    fake_event.keysym = ""
                    fake_event.char = ch
                    fake_event.state = 0
                    editor.handle_key(fake_event)
                editor.render()

        self._math_editor = editor
        self._select_region(None)
        self._canvas.focus_set()

    def _commit_edit(self):
        if not self._editing:
            return

        self._save_undo_state()

        if self._edit_mode in ("text", "comment"):
            entry = getattr(self, "_edit_text_entry", None)
            if entry is None:
                self._cancel_edit()
                return
            text = entry.get("1.0", "end-1c").strip()
            if not text:
                self._cancel_edit()
                return
            self.ensure_worksheet()
            self._commit_text_edit(text)
        else:
            if self._math_editor is None:
                self._cancel_edit()
                return
            text = self._math_editor.to_text().strip()
            if not text:
                self._cancel_edit()
                return
            self.ensure_worksheet()
            self._commit_math_edit(text)

        cx = self._cursor_x
        cy = self._cursor_y
        self._cancel_edit()
        self._mark_modified()
        self._evaluate_and_render()
        self._cursor_x = cx
        self._cursor_y = cy + 32
        self._canvas.delete("cursor_marker")
        self._draw_cursor_marker()
        self._ensure_visible(self._cursor_x, self._cursor_y)
        self._canvas.focus_set()

    def _commit_math_edit(self, text: str):
        ast = parse_infix(text)
        if ast is None:
            return

        if self._edit_region_idx is not None and self._edit_region_idx < len(self._rendered):
            self._update_existing_math_region(ast, self._edit_region_idx)
        else:
            self._create_new_math_region(ast, self._cursor_x, self._cursor_y)

    def _commit_text_edit(self, text: str):
        is_comment = self._edit_mode == "comment"
        if self._edit_region_idx is not None and self._edit_region_idx < len(self._rendered):
            region = self._rendered[self._edit_region_idx].region
            tc = self._get_text_content(region.text_contents)
            if tc is None:
                tc = TextContent(lang="eng")
                region.text_contents.append(tc)
            tc.paragraphs.clear()
            for line in text.split("\n"):
                tc.paragraphs.append(TextParagraph(text=line))
            if is_comment:
                region.bg_color = "#ffff80"
                region.border = True
        else:
            region = Region()
            region.id = self._generate_id()
            region.left = self._cursor_x
            region.top = self._cursor_y
            lines = text.split("\n")
            region.width = max(max(len(l) for l in lines) * 8, _DEFAULT_REGION_WIDTH)
            region.height = max(len(lines) * 18, _DEFAULT_REGION_HEIGHT)
            region.font_size = 10
            if is_comment:
                region.bg_color = "#ffff80"
                region.border = True
            tc = TextContent(lang="eng")
            for line in lines:
                tc.paragraphs.append(TextParagraph(text=line))
            region.text_contents.append(tc)
            self._worksheet.regions.append(region)

    def _switch_math_to_text(self):
        if self._math_editor is None:
            return
        text = self._math_editor.to_text().strip()
        x = self._cursor_x
        y = self._cursor_y
        editing_idx = self._edit_region_idx
        self._math_editor.destroy()
        self._math_editor = None
        self._editing = False
        self._edit_region_idx = None
        self._start_editing(x, y, initial_text=text, editing_idx=editing_idx, mode="text")

    def _cancel_edit(self):
        if self._math_editor is not None:
            self._math_editor.destroy()
            self._math_editor = None
        entry = getattr(self, "_edit_text_entry", None)
        if entry is not None:
            entry.destroy()
            self._edit_text_entry = None
        win = getattr(self, "_edit_text_window", None)
        if win is not None:
            try:
                self._canvas.delete(win)
            except Exception:
                pass
            self._edit_text_window = None
        self._editing = False
        self._edit_region_idx = None
        self._editor_ctx = None

    # ------------------------------------------------------------------
    # Region creation / update helpers
    # ------------------------------------------------------------------

    def _create_new_math_region(self, ast: ASTNode, x: int, y: int):
        region = Region()
        region.id = self._generate_id()
        region.left = x
        region.top = y
        region.width = _DEFAULT_REGION_WIDTH
        region.height = _DEFAULT_REGION_HEIGHT
        region.font_size = 10

        math_region = MathRegion()

        if isinstance(ast, BinaryOp) and ast.operator == ":":
            math_region.input_expr = ast
            math_region.input_elements = ast_to_elements(ast)
        elif isinstance(ast, Evaluation):
            math_region.input_expr = ast.expression
            math_region.input_elements = ast_to_elements(ast.expression)
            math_region.result_elements = list(math_region.input_elements)
            math_region.result_action = "numeric"
        elif isinstance(ast, BinaryOp) and ast.operator == "=":
            math_region.input_expr = ast
            math_region.input_elements = ast_to_elements(ast)
        else:
            math_region.input_expr = ast
            math_region.input_elements = ast_to_elements(ast)

        region.math = math_region
        self._worksheet.regions.append(region)

    def _update_existing_math_region(self, ast: ASTNode, rendered_idx: int):
        region = self._rendered[rendered_idx].region
        if region.math is None:
            region.math = MathRegion()

        math_region = region.math

        if isinstance(ast, BinaryOp) and ast.operator == ":":
            math_region.input_expr = ast
            math_region.input_elements = ast_to_elements(ast)
            math_region.result_elements = []
            math_region.result_expr = None
        elif isinstance(ast, Evaluation):
            math_region.input_expr = ast.expression
            math_region.input_elements = ast_to_elements(ast.expression)
            math_region.result_elements = list(math_region.input_elements)
            math_region.result_action = "numeric"
            math_region.result_expr = None
        elif isinstance(ast, BinaryOp) and ast.operator == "=":
            math_region.input_expr = ast
            math_region.input_elements = ast_to_elements(ast)
            math_region.result_elements = []
            math_region.result_expr = None
        else:
            math_region.input_expr = ast
            math_region.input_elements = ast_to_elements(ast)
            math_region.result_elements = []
            math_region.result_expr = None

    def _region_to_edit_text(self, region: Region) -> str:
        if region.math is None or region.math.input_expr is None:
            return ""
        expr = region.math.input_expr
        text = ast_to_text(expr)
        if region.math.result_elements:
            if not text.endswith("="):
                text += " ="
        return text

    def _generate_id(self) -> str:
        max_id = 0
        if self._worksheet:
            for r in self._worksheet.regions:
                try:
                    num = int(r.id)
                    if num > max_id:
                        max_id = num
                except (ValueError, TypeError):
                    pass
                for c in r.children:
                    try:
                        num = int(c.id)
                        if num > max_id:
                            max_id = num
                    except (ValueError, TypeError):
                        pass
        return str(max_id + 1)

    def _remove_from_children(self, regions: list[Region], target: Region) -> bool:
        for r in regions:
            if target in r.children:
                r.children.remove(target)
                return True
            if self._remove_from_children(r.children, target):
                return True
        return False
