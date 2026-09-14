"""Toolbar panels for SMath Studio GUI -- math symbol palettes and standard toolbar."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class StandardToolbar(ttk.Frame):
    """Standard toolbar row with New, Open, Save, Print, Undo, Redo, Cut, Copy, Paste."""

    def __init__(self, parent: tk.Widget, commands: dict[str, Callable]):
        super().__init__(parent)
        self._commands = commands
        self._build()

    def _build(self):
        buttons = [
            ("New", "new"),
            ("Open", "open"),
            ("Save", "save"),
            None,  # separator
            ("Print", "print"),
            None,
            ("Undo", "undo"),
            ("Redo", "redo"),
            None,
            ("Cut", "cut"),
            ("Copy", "copy"),
            ("Paste", "paste"),
        ]
        for item in buttons:
            if item is None:
                sep = ttk.Separator(self, orient=tk.VERTICAL)
                sep.pack(side=tk.LEFT, fill=tk.Y, padx=3, pady=2)
            else:
                label, cmd_key = item
                cmd = self._commands.get(cmd_key, lambda: None)
                btn = ttk.Button(
                    self, text=label, command=cmd, width=6, style="Toolbutton.TButton"
                )
                btn.pack(side=tk.LEFT, padx=1, pady=2)


class CollapsiblePanel(ttk.LabelFrame):
    """A collapsible panel with a header and content area.

    Clicking the header toggles the body visibility.
    """

    def __init__(self, parent: tk.Widget, title: str):
        super().__init__(parent, text=title)
        self._expanded = True
        self._content = ttk.Frame(self)
        self._content.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Bind the label click to toggle
        self.bind("<Button-1>", self._toggle)

    @property
    def content(self) -> ttk.Frame:
        return self._content

    def _toggle(self, _event=None):
        if self._expanded:
            self._content.pack_forget()
        else:
            self._content.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._expanded = not self._expanded


class ArithmeticPanel(CollapsiblePanel):
    """Arithmetic operators panel: +, -, x, /, ^, sqrt, etc."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent, title="Arithmetic")
        self._on_insert = on_insert
        self._build()

    def _build(self):
        symbols = [
            ("+", "+"), ("−", "-"), ("×", "*"), ("÷", "/"),
            ("^", "^"), ("√", "sqrt"), ("∑", "sum"), ("∏", "product"),
            ("∫", "int"), ("d/dx", "diff"), ("|x|", "abs"), ("()", "()"),
            ("!", "factorial"), ("%", "mod"), ("∞", "inf"), ("=", "="),
            (":=", ":="), ("≠", "!="), ("<", "<"), (">", ">"),
            ("≤", "<="), ("≥", ">="),
        ]
        frame = self.content
        cols = 4
        for i, (label, value) in enumerate(symbols):
            row = i // cols
            col = i % cols
            btn = tk.Button(
                frame,
                text=label,
                width=4,
                height=1,
                font=("Segoe UI", 10),
                relief=tk.FLAT,
                bg="#f0f0f0",
                activebackground="#d8d8d8",
                command=lambda v=value: self._insert(v),
            )
            btn.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
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
            row = i // cols
            col = i % cols
            btn = tk.Button(
                frame,
                text=label,
                width=4,
                height=1,
                font=("Segoe UI", 11),
                relief=tk.FLAT,
                bg="#f0f0f0",
                activebackground="#d8d8d8",
                command=lambda v=value: self._insert(v),
            )
            btn.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
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
            row = i // cols
            col = i % cols
            btn = tk.Button(
                frame,
                text=label,
                width=6,
                height=1,
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                bg="#f0f0f0",
                activebackground="#d8d8d8",
                command=lambda v=value: self._insert(v),
            )
            btn.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
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
            row = i // cols
            col = i % cols
            btn = tk.Button(
                frame,
                text=label,
                width=6,
                height=1,
                font=("Consolas", 9),
                relief=tk.FLAT,
                bg="#f0f0f0",
                activebackground="#d8d8d8",
                command=lambda v=value: self._insert(v),
            )
            btn.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
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
            row = i // cols
            col = i % cols
            btn = tk.Button(
                frame,
                text=label,
                width=6,
                height=1,
                font=("Consolas", 9),
                relief=tk.FLAT,
                bg="#f0f0f0",
                activebackground="#d8d8d8",
                command=lambda v=value: self._insert(v),
            )
            btn.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
        for c in range(cols):
            frame.columnconfigure(c, weight=1)

    def _insert(self, value: str):
        if self._on_insert:
            self._on_insert(value)


class MathPanelContainer(ttk.Frame):
    """Container holding all math toolbar panels in a scrollable sidebar."""

    def __init__(self, parent: tk.Widget, on_insert: Optional[Callable] = None):
        super().__init__(parent)
        self._on_insert = on_insert

        # Inner canvas with scrollbar for the panels
        self._canvas = tk.Canvas(self, width=180, highlightthickness=0)
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

        # Build panels
        self.arithmetic = ArithmeticPanel(self._inner, on_insert=on_insert)
        self.arithmetic.pack(fill=tk.X, padx=2, pady=2)

        self.symbols = SymbolsPanel(self._inner, on_insert=on_insert)
        self.symbols.pack(fill=tk.X, padx=2, pady=2)

        self.matrices = MatricesPanel(self._inner, on_insert=on_insert)
        self.matrices.pack(fill=tk.X, padx=2, pady=2)

        self.functions = FunctionsPanel(self._inner, on_insert=on_insert)
        self.functions.pack(fill=tk.X, padx=2, pady=2)

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
