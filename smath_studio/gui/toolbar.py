"""Toolbar panels for SMath Studio GUI -- math symbol palettes and standard toolbar."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

try:
    from PIL import Image, ImageDraw, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _make_icon(name: str) -> "Image.Image":
    """Create a 16x16 toolbar icon."""
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if name == "new":
        d.rectangle([3, 0, 12, 15], outline="#444", fill="#fff")
        d.polygon([(9, 0), (12, 3), (9, 3)], fill="#ddd", outline="#444")
        for y in (5, 7, 9, 11): d.line([(5, y), (10, y)], fill="#999")
    elif name == "open":
        d.rectangle([1, 4, 14, 14], outline="#886600", fill="#ffdd44")
        d.rectangle([1, 4, 14, 7], outline="#886600", fill="#ccaa00")
        d.polygon([(0, 7), (3, 14), (14, 14), (11, 7)], fill="#ffee88", outline="#886600")
    elif name == "save":
        d.rectangle([1, 1, 14, 14], outline="#336", fill="#448")
        d.rectangle([3, 1, 12, 6], outline="#336", fill="#aab")
        d.rectangle([4, 8, 11, 14], outline="#336", fill="#ddd")
        d.rectangle([8, 2, 10, 5], fill="#336")
    elif name == "print":
        d.rectangle([3, 0, 12, 5], outline="#555", fill="#fff")
        d.rectangle([0, 5, 15, 12], outline="#555", fill="#ddd")
        d.rectangle([3, 10, 12, 15], outline="#555", fill="#fff")
        d.rectangle([5, 12, 10, 14], fill="#ccc")
        d.ellipse([10, 7, 13, 10], fill="#0a0")
    elif name == "undo":
        d.arc([2, 2, 14, 14], 120, 340, fill="#226")
        d.polygon([(2, 4), (6, 1), (6, 7)], fill="#226")
    elif name == "redo":
        d.arc([2, 2, 14, 14], 200, 60, fill="#226")
        d.polygon([(14, 4), (10, 1), (10, 7)], fill="#226")
    elif name == "cut":
        d.line([(7, 0), (5, 8)], fill="#555", width=2)
        d.line([(9, 0), (11, 8)], fill="#555", width=2)
        d.ellipse([2, 9, 8, 15], outline="#555", fill=None)
        d.ellipse([8, 9, 14, 15], outline="#555", fill=None)
    elif name == "copy":
        d.rectangle([0, 3, 9, 15], outline="#448", fill="#dde8ff")
        d.rectangle([4, 0, 13, 12], outline="#448", fill="#dde8ff")
        for y in (3, 5, 7, 9): d.line([(6, y), (11, y)], fill="#99a")
    elif name == "paste":
        d.rectangle([3, 3, 14, 15], outline="#448", fill="#ffe")
        d.rectangle([5, 0, 11, 5], outline="#886600", fill="#ccaa00")
        d.rectangle([6, 1, 10, 4], fill="#ffe")
        for y in (7, 9, 11, 13): d.line([(5, y), (12, y)], fill="#999")
    elif name == "find":
        d.ellipse([0, 0, 10, 10], outline="#448", fill="#dde8ff", width=2)
        d.line([(9, 9), (15, 15)], fill="#448", width=2)
    return img


class StandardToolbar(ttk.Frame):
    """Standard toolbar row with New, Open, Save, Print, Undo, Redo, Cut, Copy, Paste."""

    _BG = "#ece9d8"
    _HOVER_BG = "#c1d2ee"
    _PRESS_BG = "#98b5e2"

    def __init__(self, parent: tk.Widget, commands: dict[str, Callable]):
        super().__init__(parent)
        self._commands = commands
        self._icon_refs: list = []
        self._build()

    def _build(self):
        buttons = [
            ("new", "New (Ctrl+N)", "new"),
            ("open", "Open (Ctrl+O)", "open"),
            ("save", "Save (Ctrl+S)", "save"),
            None,
            ("print", "Print (Ctrl+P)", "print"),
            None,
            ("undo", "Undo (Ctrl+Z)", "undo"),
            ("redo", "Redo (Ctrl+Y)", "redo"),
            None,
            ("cut", "Cut (Ctrl+X)", "cut"),
            ("copy", "Copy (Ctrl+C)", "copy"),
            ("paste", "Paste (Ctrl+V)", "paste"),
            None,
            ("find", "Find (Ctrl+H)", "find"),
        ]
        for item in buttons:
            if item is None:
                sep = ttk.Separator(self, orient=tk.VERTICAL)
                sep.pack(side=tk.LEFT, fill=tk.Y, padx=2, pady=3)
            else:
                icon_name, tooltip, cmd_key = item
                cmd = self._commands.get(cmd_key, lambda: None)
                if _HAS_PIL:
                    pil_img = _make_icon(icon_name)
                    photo = ImageTk.PhotoImage(pil_img, master=self)
                    self._icon_refs.append(photo)
                    btn = tk.Button(
                        self, image=photo, command=cmd,
                        relief=tk.FLAT, bg=self._BG,
                        activebackground=self._PRESS_BG,
                        bd=0, highlightthickness=0,
                        padx=3, pady=3,
                    )
                else:
                    fallback = {"new": "⬜", "open": "\U0001f4c2",
                                "save": "\U0001f4be", "print": "\U0001f5a8",
                                "undo": "↶", "redo": "↷",
                                "cut": "✂", "copy": "⎘",
                                "paste": "\U0001f4cb", "find": "\U0001f50d"}
                    btn = tk.Button(
                        self, text=fallback.get(icon_name, "?"), command=cmd,
                        width=2, height=1, font=("DejaVu Sans", 10),
                        relief=tk.FLAT, bg=self._BG,
                        activebackground=self._PRESS_BG,
                        bd=0, highlightthickness=0,
                        padx=2, pady=1,
                    )
                btn.pack(side=tk.LEFT, padx=0, pady=1)
                self._bind_hover_tooltip(btn, tooltip)

    def _bind_hover_tooltip(self, widget: tk.Widget, text: str):
        tip = None
        def enter(e):
            nonlocal tip
            widget.configure(bg=self._HOVER_BG, relief=tk.RAISED)
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(tip, text=text, bg="#ffffdd", relief=tk.SOLID,
                           borderwidth=1, font=("DejaVu Sans", 8),
                           padx=3, pady=1)
            lbl.pack()
        def leave(e):
            nonlocal tip
            widget.configure(bg=self._BG, relief=tk.FLAT)
            if tip:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    @staticmethod
    def _add_tooltip(widget: tk.Widget, text: str):
        tip = None
        def enter(e):
            nonlocal tip
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(tip, text=text, bg="#ffffdd", relief=tk.SOLID,
                           borderwidth=1, font=("DejaVu Sans", 8),
                           padx=3, pady=1)
            lbl.pack()
        def leave(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)


class FormatToolbar(ttk.Frame):
    """Formatting toolbar with Bold, Italic, Underline, font size."""

    _BG = "#ece9d8"
    _HOVER_BG = "#c1d2ee"

    def __init__(self, parent: tk.Widget, commands: dict[str, Callable]):
        super().__init__(parent)
        self._commands = commands
        self._build()

    def _bind_hover_tooltip(self, widget: tk.Widget, text: str):
        tip = None
        def enter(e):
            nonlocal tip
            widget.configure(bg=self._HOVER_BG, relief=tk.RAISED)
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(tip, text=text, bg="#ffffdd", relief=tk.SOLID,
                           borderwidth=1, font=("DejaVu Sans", 8),
                           padx=3, pady=1)
            lbl.pack()
        def leave(e):
            nonlocal tip
            widget.configure(bg=self._BG, relief=tk.FLAT)
            if tip:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _build(self):
        fmt_buttons = [
            ("B", "Bold (Ctrl+B)", "bold", ("DejaVu Sans", 10, "bold")),
            ("I", "Italic", "italic", ("DejaVu Sans", 10, "italic")),
            ("U", "Underline (Ctrl+U)", "underline", ("DejaVu Sans", 10, "underline")),
        ]
        for text, tooltip, cmd_key, font in fmt_buttons:
            cmd = self._commands.get(cmd_key, lambda: None)
            btn = tk.Button(
                self, text=text, command=cmd,
                width=2, height=1,
                font=font,
                relief=tk.FLAT,
                bg=self._BG,
                activebackground="#98b5e2",
                bd=0,
                highlightthickness=0,
                padx=2, pady=1,
            )
            btn.pack(side=tk.LEFT, padx=0, pady=1)
            self._bind_hover_tooltip(btn, tooltip)

        sep = ttk.Separator(self, orient=tk.VERTICAL)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=3, pady=2)

        lbl = tk.Label(self, text="Size:", font=("DejaVu Sans", 9), bg=self._BG)
        lbl.pack(side=tk.LEFT, padx=(2, 0))
        self._font_size_var = tk.StringVar(value="10")
        size_combo = ttk.Combobox(
            self, textvariable=self._font_size_var,
            values=["8", "9", "10", "11", "12", "14", "16", "18", "20", "24"],
            width=4, state="readonly",
        )
        size_combo.pack(side=tk.LEFT, padx=2)
        size_combo.bind("<<ComboboxSelected>>", self._on_size_change)

        sep2 = ttk.Separator(self, orient=tk.VERTICAL)
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=3, pady=2)

        zoom_label = tk.Label(self, text="Zoom:", font=("DejaVu Sans", 9), bg=self._BG)
        zoom_label.pack(side=tk.LEFT, padx=(2, 0))
        self._zoom_var = tk.StringVar(value="100%")
        zoom_combo = ttk.Combobox(
            self, textvariable=self._zoom_var,
            values=["50%", "75%", "100%", "125%", "150%", "200%", "300%"],
            width=5, state="readonly",
        )
        zoom_combo.pack(side=tk.LEFT, padx=2)
        zoom_combo.bind("<<ComboboxSelected>>", self._on_zoom_change)

    def _on_size_change(self, event=None):
        cmd = self._commands.get("font_size")
        if cmd:
            try:
                size = int(self._font_size_var.get())
                cmd(size)
            except ValueError:
                pass

    def _on_zoom_change(self, event=None):
        cmd = self._commands.get("zoom")
        if cmd:
            try:
                zoom_text = self._zoom_var.get().replace("%", "")
                zoom = int(zoom_text) / 100
                cmd(zoom)
            except ValueError:
                pass

    def set_zoom(self, pct: int):
        self._zoom_var.set(f"{pct}%")


class CollapsiblePanel(tk.Frame):
    """A collapsible panel with a header and content area.

    Clicking the header toggles the body visibility.
    """

    def __init__(self, parent: tk.Widget, title: str):
        super().__init__(parent, bd=0, relief=tk.FLAT, bg="#ece9d8")
        self._expanded = True
        self._title = title
        self._header = tk.Frame(self, bg="#ece9d8", cursor="hand2")
        self._header.pack(fill=tk.X)
        self._arrow_label = tk.Label(
            self._header, text="▼", font=("DejaVu Sans", 6),
            bg="#ece9d8", fg="#666666", padx=1,
        )
        self._arrow_label.pack(side=tk.LEFT, padx=(2, 0))
        self._title_label = tk.Label(
            self._header, text=title, font=("DejaVu Sans", 8, "bold"),
            bg="#ece9d8", fg="#000000", anchor=tk.W, padx=2, pady=1,
        )
        self._title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Separator line below header
        tk.Frame(self, height=1, bg="#c0c0c0").pack(fill=tk.X)
        self._content = tk.Frame(self, bg="#ffffff", bd=1, relief=tk.SUNKEN)
        self._content.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        for w in (self._header, self._arrow_label, self._title_label):
            w.bind("<Button-1>", self._toggle)

    @property
    def content(self) -> tk.Frame:
        return self._content

    def _toggle(self, _event=None):
        if self._expanded:
            self._content.pack_forget()
            self._arrow_label.configure(text="▶")
        else:
            self._content.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
            self._arrow_label.configure(text="▼")
        self._expanded = not self._expanded


def _make_panel_btn(frame: tk.Widget, label: str, value: str,
                    on_insert, row: int, col: int, cols: int = 4):
    """Create a styled panel button with hover effect."""
    btn = tk.Button(
        frame, text=label, width=4, height=1,
        font=("DejaVu Sans", 9), relief=tk.FLAT,
        bg="#ffffff", activebackground="#c1d2ee",
        bd=0, highlightthickness=0, padx=1, pady=0,
        command=lambda: on_insert(value) if on_insert else None,
    )
    btn.grid(row=row, column=col, padx=0, pady=0, sticky="nsew")
    def enter(e): btn.configure(bg="#dce6f4", relief=tk.RAISED)
    def leave(e): btn.configure(bg="#ffffff", relief=tk.FLAT)
    btn.bind("<Enter>", enter)
    btn.bind("<Leave>", leave)
    return btn


class ArithmeticPanel(CollapsiblePanel):
    """Arithmetic operators panel: +, -, x, /, ^, sqrt, etc."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Arithmetic")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        symbols = [
            ("+", "+"), ("−", "-"), ("×", "*"), ("÷", "/"),
            ("^", "^"), ("√", "sqrt"), ("ⁿ√", "nthroot"), ("∑", "sum"),
            ("∏", "product"), ("∫", "int"), ("d/dx", "diff"), ("lim", "lim"),
            ("|x|", "abs"), ("()", "()"), ("!", "factorial"), ("%", "mod"),
            ("∞", "inf"), ("=", "="),
            (":=", ":="), ("≠", "!="), ("<", "<"), (">", ">"),
            ("≤", "<="), ("≥", ">="),
        ]
        frame = self.content
        cols = 4
        for i, (label, value) in enumerate(symbols):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class SymbolsPanel(CollapsiblePanel):
    """Greek letters and special symbols panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Symbols")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        greek = [
            ("α", "alpha"), ("β", "beta"), ("γ", "gamma"),
            ("δ", "delta"), ("ε", "epsilon"), ("ζ", "zeta"),
            ("η", "eta"), ("θ", "theta"), ("ι", "iota"),
            ("κ", "kappa"), ("λ", "lambda"), ("μ", "mu"),
            ("ν", "nu"), ("ξ", "xi"), ("ο", "omicron"),
            ("π", "pi"), ("ρ", "rho"), ("σ", "sigma"),
            ("τ", "tau"), ("υ", "upsilon"), ("φ", "phi"),
            ("χ", "chi"), ("ψ", "psi"), ("ω", "omega"),
            ("Γ", "Gamma"), ("Δ", "Delta"), ("Θ", "Theta"),
            ("Λ", "Lambda"), ("Σ", "Sigma"), ("Φ", "Phi"),
            ("Ψ", "Psi"), ("Ω", "Omega"),
        ]
        frame = self.content
        cols = 4
        for i, (label, value) in enumerate(greek):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class MatricesPanel(CollapsiblePanel):
    """Matrix operations panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Matrices")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        items = [
            ("Matrix", "mat"), ("det", "det"), ("T", "transpose"),
            ("inv", "invert"), ("I", "identity"), ("el", "el"),
            ("rows", "rows"), ("cols", "cols"), ("col", "col"),
            ("stack", "stack"), ("augment", "augment"), ("tr", "tr"),
        ]
        frame = self.content
        cols = 3
        for i, (label, value) in enumerate(items):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols, cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class FunctionsPanel(CollapsiblePanel):
    """Common math functions panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Functions")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        funcs = [
            ("sin", "sin"), ("cos", "cos"), ("tan", "tan"),
            ("asin", "asin"), ("acos", "acos"), ("atan", "atan"),
            ("ln", "ln"), ("log", "log"), ("exp", "exp"),
            ("sqrt", "sqrt"), ("abs", "abs"), ("sign", "sign"),
            ("ceil", "ceil"), ("floor", "floor"), ("round", "round"),
            ("max", "max"), ("min", "min"), ("mod", "mod"),
            ("mean", "mean"), ("median", "median"), ("stdev", "stdev"),
        ]
        frame = self.content
        cols = 3
        for i, (label, value) in enumerate(funcs):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols, cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class SystemPanel(CollapsiblePanel):
    """System / control flow panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="System")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        items = [
            ("if", "if"), ("for", "for"), ("while", "while"),
            ("line", "line"), ("range", "range"), ("eval", "eval"),
        ]
        frame = self.content
        cols = 3
        for i, (label, value) in enumerate(items):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols, cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class BooleanPanel(CollapsiblePanel):
    """Boolean and comparison operators panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Boolean")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        items = [
            ("AND", "and"), ("OR", "or"), ("NOT", "not"), ("XOR", "xor"),
            ("=", "=="), ("≠", "!="), ("<", "<"), (">", ">"),
            ("≤", "<="), ("≥", ">="), ("true", "true"), ("false", "false"),
        ]
        frame = self.content
        cols = 4
        for i, (label, value) in enumerate(items):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class ProgrammingPanel(CollapsiblePanel):
    """Programming constructs panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Programming")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        items = [
            ("if", "if"), ("for", "for"), ("while", "while"),
            ("line", "line"), ("{}", "system"),
            ("break", "break"), ("continue", "continue"), ("return", "return"),
        ]
        frame = self.content
        cols = 3
        for i, (label, value) in enumerate(items):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols, cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class PlotPanel(CollapsiblePanel):
    """Plot/graph panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Plots")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        items = [
            ("2D Plot", "plot2d"), ("Parametric", "plotparam"),
            ("Polar", "plotpolar"), ("3D Plot", "plot3d"),
        ]
        frame = self.content
        cols = 2
        for i, (label, value) in enumerate(items):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols, cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class UnitsPanel(CollapsiblePanel):
    """Common physical units panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Units")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        items = [
            ("m", "'m'"), ("kg", "'kg'"), ("s", "'s'"), ("A", "'A'"),
            ("K", "'K'"), ("N", "'N'"), ("Pa", "'Pa'"), ("J", "'J'"),
            ("W", "'W'"), ("V", "'V'"), ("Hz", "'Hz'"), ("rad", "'rad'"),
            ("mm", "'mm'"), ("cm", "'cm'"), ("km", "'km'"), ("in", "'in'"),
            ("ft", "'ft'"), ("kN", "'kN'"), ("MPa", "'MPa'"), ("kPa", "'kPa'"),
            ("kJ", "'kJ'"), ("kW", "'kW'"), ("deg", "'deg'"), ("L", "'L'"),
        ]
        frame = self.content
        cols = 4
        for i, (label, value) in enumerate(items):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class ConstantsPanel(CollapsiblePanel):
    """Physical and mathematical constants panel."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Constants")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        items = [
            ("π", "pi"), ("e", "e"), ("i", "i"), ("∞", "inf"),
            ("c₀", "c_0"), ("h", "h_planck"), ("k_B", "k_B"),
            ("N_A", "N_A"), ("R", "R_gas"), ("g", "g"),
            ("ε₀", "epsilon_0"), ("μ₀", "mu_0"),
        ]
        frame = self.content
        cols = 4
        for i, (label, value) in enumerate(items):
            _make_panel_btn(frame, label, value, self._on_insert, i // cols, i % cols)
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class DocumentMapPanel(CollapsiblePanel):
    """Document Map panel showing title regions as navigable links."""

    def __init__(self, parent: tk.Widget, on_navigate: Optional[Callable] = None):
        super().__init__(parent, title="Document Map")
        self._on_navigate = on_navigate
        self._listbox = tk.Listbox(
            self.content, font=("DejaVu Sans", 9), fg="#0000ff",
            selectbackground="#c8d8e8", selectforeground="#000000",
            activestyle="none", relief=tk.FLAT, highlightthickness=0,
            height=6,
        )
        self._listbox.pack(fill=tk.BOTH, expand=True)
        self._listbox.bind("<Double-Button-1>", self._on_click)
        self._entries: list[tuple[str, float]] = []

    def update_entries(self, entries: list[tuple[str, float]]):
        self._entries = entries
        self._listbox.delete(0, tk.END)
        for title, _top in entries:
            self._listbox.insert(tk.END, title)

    def _on_click(self, _event=None):
        sel = self._listbox.curselection()
        if sel and self._on_navigate and sel[0] < len(self._entries):
            _, top = self._entries[sel[0]]
            self._on_navigate(top)


class MathPanelContainer(ttk.Frame):
    """Container holding all math toolbar panels in a scrollable sidebar."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None,
                 on_navigate: Optional[Callable] = None):
        super().__init__(parent)
        self._on_insert = on_insert

        self._canvas = tk.Canvas(self, width=180, highlightthickness=0, bg="#ece9d8")
        self._scrollbar = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self._canvas.yview
        )
        self._inner = ttk.Frame(self._canvas)

        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._window_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor=tk.NW
        )
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        self.doc_map = DocumentMapPanel(self._inner, on_navigate=on_navigate)
        self.doc_map.pack(fill=tk.X, padx=2, pady=2)

        self.arithmetic = ArithmeticPanel(self._inner, on_insert=on_insert)
        self.arithmetic.pack(fill=tk.X, padx=2, pady=2)

        self.symbols = SymbolsPanel(self._inner, on_insert=on_insert)
        self.symbols.pack(fill=tk.X, padx=2, pady=2)

        self.matrices = MatricesPanel(self._inner, on_insert=on_insert)
        self.matrices.pack(fill=tk.X, padx=2, pady=2)

        self.functions = FunctionsPanel(self._inner, on_insert=on_insert)
        self.functions.pack(fill=tk.X, padx=2, pady=2)

        self.boolean = BooleanPanel(self._inner, on_insert=on_insert)
        self.boolean.pack(fill=tk.X, padx=2, pady=2)

        self.units = UnitsPanel(self._inner, on_insert=on_insert)
        self.units.pack(fill=tk.X, padx=2, pady=2)

        self.constants = ConstantsPanel(self._inner, on_insert=on_insert)
        self.constants.pack(fill=tk.X, padx=2, pady=2)

        self.programming = ProgrammingPanel(self._inner, on_insert=on_insert)
        self.programming.pack(fill=tk.X, padx=2, pady=2)

        self.plots = PlotPanel(self._inner, on_insert=on_insert)
        self.plots.pack(fill=tk.X, padx=2, pady=2)

        self.system = SystemPanel(self._inner, on_insert=on_insert)
        self.system.pack(fill=tk.X, padx=2, pady=2)

        # Mouse wheel scrolling
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_inner_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._window_id, width=event.width)

    def _bind_mousewheel(self, _event):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        # Linux
        self._canvas.bind_all("<Button-4>", self._on_mousewheel_up)
        self._canvas.bind_all("<Button-5>", self._on_mousewheel_down)

    def _unbind_mousewheel(self, _event):
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_up(self, _event):
        self._canvas.yview_scroll(-1, "units")

    def _on_mousewheel_down(self, _event):
        self._canvas.yview_scroll(1, "units")
