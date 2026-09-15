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

_CANVAS_BG = "#e8e8e8"
_PAGE_BOUNDARY_COLOR = "#d0d0d0"
_SELECTION_COLOR = "#3366cc"
_SELECTION_DASH = (4, 4)
_GRID_SIZE = 8  # snap grid in pixels
_DEFAULT_REGION_WIDTH = 120
_DEFAULT_REGION_HEIGHT = 24
_REGION_PADDING = 4
_AREA_TRIANGLE_SIZE = 10

# Colors matching SMath Studio conventions
_COMMENT_BG = "#ffff80"
_TITLE_FG = "#0000ff"
_BORDER_BG = "#dddddd"
_UNIT_FG = "#0000ff"
_ERROR_FG = "#ff0000"


def _snap(value: int, grid: int = _GRID_SIZE) -> int:
    """Snap a coordinate to the nearest grid point."""
    return round(value / grid) * grid


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


def _format_value(val: Any, precision: int = 4) -> str:
    """Format an evaluated value for display."""
    if isinstance(val, Quantity):
        unit_str = val.display_unit if hasattr(val, 'display_unit') else val.unit.name
        return f"{val.value:.{precision}g} {unit_str}"
    if isinstance(val, float):
        if math.isnan(val):
            return "NaN"
        if math.isinf(val):
            return "Inf" if val > 0 else "-Inf"
        return f"{val:.{precision}g}"
    if isinstance(val, int):
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
        self._ctx: Optional[EvalContext] = None
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

        # Build canvas with scrollbars
        self._canvas = tk.Canvas(
            self,
            bg=_CANVAS_BG,
            highlightthickness=0,
            cursor="arrow",
        )
        self._h_scroll = ttk.Scrollbar(
            self, orient=tk.HORIZONTAL, command=self._canvas.xview
        )
        self._v_scroll = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self._canvas.yview
        )
        self._canvas.configure(
            xscrollcommand=self._h_scroll.set,
            yscrollcommand=self._v_scroll.set,
        )

        # Grid layout: canvas fills center, scrollbars on edges
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._v_scroll.grid(row=0, column=1, sticky="ns")
        self._h_scroll.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Drag state
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Hover state
        self._hover_index: Optional[int] = None
        self._hover_items: list[int] = []

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

        # Mouse-wheel scrolling
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>", self._on_mousewheel_linux_up)
        self._canvas.bind("<Button-5>", self._on_mousewheel_linux_down)
        self._canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        self._canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        self._canvas.bind("<Control-Button-4>", self._on_ctrl_mousewheel_up)
        self._canvas.bind("<Control-Button-5>", self._on_ctrl_mousewheel_down)

        # Context menu
        self._context_menu = tk.Menu(self._canvas, tearoff=0)
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

        # Fonts (cached)
        self._font_cache: dict[tuple, tkfont.Font] = {}

        # Math renderer if available
        self._math_renderer = None
        if _HAS_MATH_RENDERER:
            try:
                self._math_renderer = MathRenderer(self._canvas)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_worksheet(self, worksheet: Worksheet):
        """Load a worksheet and render all its regions."""
        self._worksheet = worksheet
        self._ctx = create_default_context()
        self._ctx._precision = worksheet.settings.calculation.precision
        self._selected_index = None
        self._evaluate_and_render()

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
            self._evaluate_and_render()

    def get_selected_region(self) -> Optional[Region]:
        """Return the currently selected region, or None."""
        if self._selected_index is not None and self._selected_index < len(self._rendered):
            return self._rendered[self._selected_index].region
        return None

    def get_cursor_position(self) -> tuple[int, int]:
        """Return the canvas position under the mouse (for status bar)."""
        try:
            x = self._canvas.winfo_pointerx() - self._canvas.winfo_rootx()
            y = self._canvas.winfo_pointery() - self._canvas.winfo_rooty()
            cx = int(self._canvas.canvasx(x))
            cy = int(self._canvas.canvasy(y))
            return (cx, cy)
        except Exception:
            return (0, 0)

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

        ws = self._worksheet
        if ws is None:
            self._draw_page_background(None)
            if self._show_grid:
                self._draw_grid_dots()
            if self._show_margin:
                self._draw_left_margin()
            self._draw_cursor_marker()
            return

        self._draw_page_background(ws)
        if self._show_grid:
            self._draw_grid_dots()
        if self._show_margin:
            self._draw_left_margin()

        # Draw page boundaries if page model is active
        if ws.settings.page_model.active:
            self._draw_page_boundaries(ws)

        # Flatten regions and sort by reading order (top, then left)
        all_regions = self._flatten_regions(ws.regions)
        all_regions.sort(key=lambda r: (r.top, r.left))

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
        """Flatten nested regions from area blocks."""
        result: list[Region] = []
        for r in regions:
            result.append(r)
            if r.children:
                result.extend(self._flatten_regions(r.children))
        return result

    def _draw_page_background(self, ws: Worksheet):
        """Draw a white page rectangle on the gray canvas background."""
        if ws and ws.settings.page_model.active:
            pw = ws.settings.page_model.paper_width
            ph = ws.settings.page_model.paper_height
        else:
            pw = 800
            ph = 5000
        self._canvas.create_rectangle(
            0, 0, pw, ph,
            fill="#ffffff", outline="#cccccc", width=1, tags="page_bg"
        )
        shadow_w = 3
        self._canvas.create_rectangle(
            pw, shadow_w, pw + shadow_w, ph + shadow_w,
            fill="#cccccc", outline="", tags="page_shadow"
        )
        self._canvas.create_rectangle(
            shadow_w, ph, pw + shadow_w, ph + shadow_w,
            fill="#cccccc", outline="", tags="page_shadow"
        )

    def _draw_page_boundaries(self, ws: Worksheet):
        """Draw light gray page boundary lines."""
        pm = ws.settings.page_model
        pw = pm.paper_width
        ph = pm.paper_height

        # Draw several pages worth of boundaries
        for page_y in range(0, ph * 5, ph):
            self._canvas.create_line(
                0, page_y, pw * 2, page_y,
                fill=_PAGE_BOUNDARY_COLOR, dash=(2, 4)
            )
        for page_x in range(0, pw * 3, pw):
            self._canvas.create_line(
                page_x, 0, page_x, ph * 5,
                fill=_PAGE_BOUNDARY_COLOR, dash=(2, 4)
            )

    def _draw_grid_dots(self):
        """Draw subtle grid dots for alignment like SMath Studio."""
        visible = self._get_visible_area()
        if visible is None:
            return
        x1, y1, x2, y2 = visible
        grid = _GRID_SIZE * 3
        sx = (int(x1) // grid) * grid
        sy = (int(y1) // grid) * grid
        for gx in range(sx, int(x2) + grid, grid):
            for gy in range(sy, int(y2) + grid, grid):
                self._canvas.create_oval(
                    gx - 1, gy - 1, gx + 1, gy + 1,
                    fill="#e0e0e0", outline="", tags="grid_dots",
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
        """Draw a subtle left margin line like SMath Studio."""
        margin_x = 30
        h = 5000
        self._canvas.create_line(
            margin_x, 0, margin_x, h,
            fill="#e8e8e8", width=1, tags="margin_line"
        )

    def _draw_cursor_marker(self):
        """Draw a red crosshair at the current cursor position."""
        if self._editing:
            return
        x = self._cursor_x
        y = self._cursor_y
        sz = 6
        self._canvas.create_line(
            x - sz, y, x + sz, y, fill="#ff0000", width=1, tags="cursor_marker"
        )
        self._canvas.create_line(
            x, y - sz, x, y + sz, fill="#ff0000", width=1, tags="cursor_marker"
        )

    def _update_scroll_region(self):
        """Set the scrollable region to encompass all content."""
        bbox = self._canvas.bbox("all")
        if bbox:
            # Add margin around the content
            margin = 100
            x1, y1, x2, y2 = bbox
            self._canvas.configure(
                scrollregion=(
                    min(x1, 0) - margin,
                    min(y1, 0) - margin,
                    x2 + margin,
                    y2 + margin,
                )
            )

    # ------------------------------------------------------------------
    # Region rendering
    # ------------------------------------------------------------------

    def _render_region(self, region: Region, eval_result: Any = None):
        """Render a single region on the canvas."""
        items: list[int] = []
        x = region.left
        y = region.top

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
            rr = _RenderedRegion(region, items, all_bbox)
            self._rendered.append(rr)

    def _render_text(self, region: Region, x: int, y: int) -> list[int]:
        """Render a text region."""
        items: list[int] = []
        tc = self._get_text_content(region.text_contents)
        if tc is None:
            return items

        # Determine style
        fg = region.color if region.color else "#000000"
        bg = region.bg_color if region.bg_color != "#ffffff" else None

        # Detect special styles from colors
        is_title = fg.lower() in ("#0000ff", "#0000cc")
        is_comment = bg and bg.lower() in ("#ffff80", "#ffffcc")
        has_border = region.border

        if is_title:
            fg = _TITLE_FG
        if is_comment and bg is None:
            bg = _COMMENT_BG

        # Background rectangle for bordered/colored regions
        if has_border or bg:
            draw_bg = bg if bg else _BORDER_BG
            rw = max(region.width, _DEFAULT_REGION_WIDTH)
            rh = max(region.height, _DEFAULT_REGION_HEIGHT)
            rect_id = self._canvas.create_rectangle(
                x, y, x + rw, y + rh,
                fill=draw_bg,
                outline="#aaaaaa" if has_border else "",
                width=1 if has_border else 0,
            )
            items.append(rect_id)

        # Render each paragraph
        cy = y + _REGION_PADDING
        for para in tc.paragraphs:
            fnt = self._get_font(region.font_size, para.bold, para.italic)
            text_id = self._canvas.create_text(
                x + _REGION_PADDING, cy,
                text=para.text,
                anchor=tk.NW,
                font=fnt,
                fill=fg,
            )
            items.append(text_id)
            # Advance y by the text height
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

        # Try the dedicated math renderer first
        if self._math_renderer is not None:
            try:
                rendered_items = self._math_renderer.render(
                    self._canvas, math_data, x, y, eval_result,
                    font_size=region.font_size,
                    color=region.color,
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
        cx = x + _REGION_PADDING
        cy = y + _REGION_PADDING

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

        if has_result and eval_result is not None:
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
            if isinstance(eval_result, Exception):
                result_text = f"Error: {eval_result}"
                result_fg = _ERROR_FG
            else:
                precision = self._ctx.precision if self._ctx else 4
                result_text = _format_value(eval_result, precision)
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

        if area.is_terminator:
            # Area end marker: horizontal line
            w = max(region.width, 200)
            line_id = self._canvas.create_line(
                x, y, x + w, y,
                fill="#aaaaaa", dash=(4, 2)
            )
            items.append(line_id)
        else:
            # Area start marker: triangle + label
            collapsed = area.collapsed

            # Draw expand/collapse triangle
            if collapsed:
                # Right-pointing triangle
                tri_id = self._canvas.create_polygon(
                    x, y,
                    x + _AREA_TRIANGLE_SIZE, y + _AREA_TRIANGLE_SIZE // 2,
                    x, y + _AREA_TRIANGLE_SIZE,
                    fill="#555555", outline="#333333",
                )
            else:
                # Down-pointing triangle
                tri_id = self._canvas.create_polygon(
                    x, y,
                    x + _AREA_TRIANGLE_SIZE, y,
                    x + _AREA_TRIANGLE_SIZE // 2, y + _AREA_TRIANGLE_SIZE,
                    fill="#555555", outline="#333333",
                )
            items.append(tri_id)

            # Area label from text contents
            label = ""
            tc = self._get_text_content(region.text_contents)
            if tc and tc.paragraphs:
                label = tc.paragraphs[0].text
            if label:
                fnt = self._get_font(region.font_size, bold=True, italic=False)
                label_id = self._canvas.create_text(
                    x + _AREA_TRIANGLE_SIZE + 6, y,
                    text=label,
                    anchor=tk.NW,
                    font=fnt,
                    fill="#333333",
                )
                items.append(label_id)

            # Horizontal line after label
            w = max(region.width, 200)
            line_id = self._canvas.create_line(
                x, y + _AREA_TRIANGLE_SIZE + 2,
                x + w, y + _AREA_TRIANGLE_SIZE + 2,
                fill="#aaaaaa", dash=(4, 2)
            )
            items.append(line_id)

        return items

    def _render_plot_placeholder(self, region: Region, x: int, y: int) -> list[int]:
        """Render a plot region using matplotlib, falling back to a placeholder."""
        items: list[int] = []
        w = max(region.width, 200)
        h = max(region.height, 150)

        # Try to render using matplotlib
        if _HAS_PLOT_RENDERER and region.plot is not None:
            try:
                ctx = self._ctx if self._ctx is not None else create_default_context()
                pil_img = render_plot(region.plot, ctx, width=w, height=h)
                tk_img = ImageTk.PhotoImage(pil_img)
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

        label_id = self._canvas.create_text(
            x + w // 2, y + h // 2,
            text="[Plot Region]",
            anchor=tk.CENTER,
            font=("Segoe UI", 10, "italic"),
            fill="#999999",
        )
        items.append(label_id)
        return items

    def _render_picture_placeholder(self, region: Region, x: int, y: int) -> list[int]:
        """Render an embedded picture, or a placeholder if decoding fails."""
        items: list[int] = []
        w = max(region.width, 80)
        h = max(region.height, 60)

        # Attempt to decode and display the actual image data.
        pic = region.picture
        if pic is not None and pic.data:
            try:
                raw_bytes = base64.b64decode(pic.data)
                pil_image = Image.open(io.BytesIO(raw_bytes))
                # Resize to fit the region dimensions while preserving aspect ratio.
                pil_image.thumbnail((w, h), Image.LANCZOS)
                photo = ImageTk.PhotoImage(pil_image)
                # Keep a reference so the image is not garbage-collected.
                self._photo_cache.append(photo)
                img_id = self._canvas.create_image(
                    x, y, image=photo, anchor=tk.NW,
                )
                items.append(img_id)
                return items
            except Exception:
                pass  # Fall through to placeholder below.

        # Fallback placeholder when image data is missing or cannot be decoded.
        rect_id = self._canvas.create_rectangle(
            x, y, x + w, y + h,
            fill="#f0f0f0", outline="#cccccc",
        )
        items.append(rect_id)

        label_id = self._canvas.create_text(
            x + w // 2, y + h // 2,
            text="[Image]",
            anchor=tk.CENTER,
            font=("Segoe UI", 9, "italic"),
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
        self, size: int, bold: bool = False, italic: bool = False
    ) -> tkfont.Font:
        """Return a cached tkinter Font object."""
        key = (size, bold, italic)
        if key not in self._font_cache:
            weight = "bold" if bold else "normal"
            slant = "italic" if italic else "roman"
            self._font_cache[key] = tkfont.Font(
                family="Segoe UI",
                size=size,
                weight=weight,
                slant=slant,
            )
        return self._font_cache[key]

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
            outline=_SELECTION_COLOR,
            dash=_SELECTION_DASH,
            width=2,
        )
        self._selection_items.append(sel_rect)
        hs = 3
        for hx, hy in [(x1 - pad, y1 - pad), (x2 + pad, y1 - pad),
                        (x1 - pad, y2 + pad), (x2 + pad, y2 + pad)]:
            h = self._canvas.create_rectangle(
                hx - hs, hy - hs, hx + hs, hy + hs,
                fill=_SELECTION_COLOR, outline=_SELECTION_COLOR,
            )
            self._selection_items.append(h)

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

    def _on_click(self, event: tk.Event):
        """Handle left-click: commit edit, select region, or set cursor."""
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))

        if self._editing:
            self._commit_edit()
            self._canvas.focus_set()

        hit = self._hit_test(cx, cy)
        if hit is not None:
            self._select_region(hit)
            self._dragging = False
            self._drag_start_x = cx
            self._drag_start_y = cy
        else:
            self._select_region(None)
            self._cursor_x = _snap(cx)
            self._cursor_y = _snap(cy)
            self._dragging = False
        self._canvas.focus_set()

    def _on_right_click(self, event: tk.Event):
        """Show context menu on right-click."""
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))
        self._right_click_x = _snap(cx)
        self._right_click_y = _snap(cy)
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

    def _on_mousewheel(self, event: tk.Event):
        """Vertical scroll with mouse wheel (Windows/macOS)."""
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux_up(self, _event):
        self._canvas.yview_scroll(-3, "units")

    def _on_mousewheel_linux_down(self, _event):
        self._canvas.yview_scroll(3, "units")

    def _on_shift_mousewheel(self, event: tk.Event):
        """Horizontal scroll with Shift+mousewheel."""
        self._canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_ctrl_mousewheel(self, event: tk.Event):
        """Zoom with Ctrl+mousewheel."""
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _on_ctrl_mousewheel_up(self, _event):
        self._zoom_in()

    def _on_ctrl_mousewheel_down(self, _event):
        self._zoom_out()

    def _zoom_in(self):
        if self._zoom < 3.0:
            self._zoom = min(3.0, self._zoom * 1.1)
            self._apply_zoom()

    def _zoom_out(self):
        if self._zoom > 0.3:
            self._zoom = max(0.3, self._zoom / 1.1)
            self._apply_zoom()

    def _apply_zoom(self):
        self._canvas.delete("all")
        self._canvas.scale("all", 0, 0, self._zoom, self._zoom)
        self._evaluate_and_render()

    def get_zoom_percent(self) -> int:
        return int(self._zoom * 100)

    def _on_motion(self, event: tk.Event):
        """Highlight region under mouse on hover."""
        if self._editing:
            return
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))
        hit = self._hit_test(cx, cy)
        if hit != self._hover_index:
            for item_id in self._hover_items:
                try:
                    self._canvas.delete(item_id)
                except Exception:
                    pass
            self._hover_items.clear()
            self._hover_index = hit
            if hit is not None and hit != self._selected_index:
                rr = self._rendered[hit]
                x1, y1, x2, y2 = rr.bbox
                pad = 2
                rect = self._canvas.create_rectangle(
                    x1 - pad, y1 - pad, x2 + pad, y2 + pad,
                    outline="#aaccee", width=1, dash=(3, 3),
                )
                self._hover_items.append(rect)

    def _on_drag(self, event: tk.Event):
        """Handle mouse drag to move selected region."""
        if self._editing or self._selected_index is None:
            return
        if self._selected_index >= len(self._rendered):
            return
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))
        dx = cx - self._drag_start_x
        dy = cy - self._drag_start_y
        if abs(dx) < 4 and abs(dy) < 4 and not self._dragging:
            return
        self._dragging = True
        rr = self._rendered[self._selected_index]
        for item_id in rr.items:
            self._canvas.move(item_id, dx, dy)
        for item_id in self._selection_items:
            self._canvas.move(item_id, dx, dy)
        rr.bbox = (
            rr.bbox[0] + dx, rr.bbox[1] + dy,
            rr.bbox[2] + dx, rr.bbox[3] + dy,
        )
        self._drag_start_x = cx
        self._drag_start_y = cy

    def _on_drag_end(self, event: tk.Event):
        """Snap region to grid after dragging."""
        if not self._dragging or self._selected_index is None:
            self._dragging = False
            return
        if self._selected_index >= len(self._rendered):
            self._dragging = False
            return
        self._save_undo_state()
        rr = self._rendered[self._selected_index]
        region = rr.region
        region.left = _snap(rr.bbox[0])
        region.top = _snap(rr.bbox[1])
        self._dragging = False
        self._mark_modified()
        self._evaluate_and_render()
        idx = None
        for i, r in enumerate(self._rendered):
            if r.region is region:
                idx = i
                break
        self._select_region(idx)

    def _on_key(self, event: tk.Event):
        """Handle key events: forward to editor or start new editing."""
        ctrl = event.state & 0x4

        if ctrl and not self._editing:
            keysym = event.keysym.lower()
            if keysym == "m":
                self._start_editing(self._cursor_x, self._cursor_y)
                if self._math_editor:
                    self._math_editor._do_matrix()
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
            hit = self._hit_test(self._cursor_x, self._cursor_y)
            self._select_region(hit)
            return "break"

        if keysym == "F5":
            self.evaluate_selected()
            return "break"

        if keysym == "F9":
            self.recalculate()
            return "break"

        if char and ord(char) >= 32 and keysym not in (
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
            "F10", "F11", "F12",
        ):
            self._start_editing(self._cursor_x, self._cursor_y, initial_text=char)
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

    def _eval_for_editor(self, expr_text: str) -> Any:
        """Evaluate an expression for the live editor preview."""
        if self._ctx is None:
            return None
        ast = parse_infix(expr_text)
        if ast is None:
            return None
        return ast.evaluate(self._ctx)

    def _on_double_click(self, event: tk.Event):
        """Handle double-click: edit existing region or create new one."""
        cx = int(self._canvas.canvasx(event.x))
        cy = int(self._canvas.canvasy(event.y))
        hit = self._hit_test(cx, cy)

        if self._editing:
            self._commit_edit()

        if hit is not None:
            rr = self._rendered[hit]
            region = rr.region
            if region.math is not None:
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
            x = _snap(cx)
            y = _snap(cy)
            self._start_editing(x, y)

        self._canvas.focus_set()

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

    def delete_selected(self):
        """Delete the currently selected region."""
        if self._selected_index is None or self._worksheet is None:
            return
        self._save_undo_state()
        if self._selected_index >= len(self._rendered):
            return
        rr = self._rendered[self._selected_index]
        region = rr.region
        if region in self._worksheet.regions:
            self._worksheet.regions.remove(region)
        else:
            self._remove_from_children(self._worksheet.regions, region)
        self._selected_index = None
        self._mark_modified()
        self._evaluate_and_render()

    def copy_selected(self) -> str:
        """Copy selected region's expression to clipboard. Returns the text."""
        if self._selected_index is None:
            return ""
        if self._selected_index >= len(self._rendered):
            return ""
        region = self._rendered[self._selected_index].region
        text = self._region_to_edit_text(region)
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
        """Paste clipboard text as a new math region at the cursor position."""
        try:
            text = self._canvas.clipboard_get()
        except Exception:
            return
        if not text or not text.strip():
            return
        ast = parse_infix(text.strip())
        if ast is None:
            return
        self.ensure_worksheet()
        self._save_undo_state()
        self._create_new_math_region(ast, self._cursor_x, self._cursor_y)
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
        if self._editing:
            self._cancel_edit()

        self._editing = True
        self._edit_region_idx = editing_idx
        self._edit_mode = mode
        self._cursor_x = x
        self._cursor_y = y

        if mode in ("text", "comment"):
            self._math_editor = None
            bg_color = "#ffff80" if mode == "comment" else "#fffff0"
            self._edit_text_entry = tk.Text(
                self._canvas,
                font=("DejaVu Sans", 11),
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
                x, y, window=self._edit_text_entry, anchor=tk.NW
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

        editor = MathEditor(
            self._canvas, x, y,
            font_size=12,
            eval_callback=self._eval_for_editor,
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
        if region.math.result_elements and not (
            isinstance(expr, BinaryOp) and expr.operator == ":"
        ):
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
