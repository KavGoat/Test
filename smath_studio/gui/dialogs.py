"""Dialog windows for SMath Studio GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..functions import BUILTIN_FUNCTIONS

_BG = "#ece9d8"
_FNT = ("DejaVu Sans", 9)
_FNT_BOLD = ("DejaVu Sans", 9, "bold")
_FNT_SM = ("DejaVu Sans", 8)


def _xp_btn(parent, text, command, width=10):
    """Create a Windows-XP-classic styled button."""
    btn = tk.Button(
        parent, text=text, command=command, width=width,
        font=_FNT, bg=_BG, activebackground="#c1d2ee",
        relief=tk.RAISED, bd=1, padx=6, pady=2,
    )
    return btn


def _xp_label(parent, text, **kw):
    return tk.Label(parent, text=text, font=kw.pop("font", _FNT), bg=_BG, fg="#000000", **kw)


def _xp_entry(parent, textvariable, width=20):
    return tk.Entry(parent, textvariable=textvariable, width=width,
                    font=_FNT, relief=tk.SUNKEN, bd=2)


def _xp_check(parent, text, variable):
    return tk.Checkbutton(parent, text=text, variable=variable,
                          font=_FNT, bg=_BG, activebackground=_BG,
                          selectcolor="white", anchor="w")


def _xp_radio(parent, text, variable, value):
    return tk.Radiobutton(parent, text=text, variable=variable, value=value,
                          font=_FNT, bg=_BG, activebackground=_BG,
                          selectcolor="white", anchor="w")


def _xp_spin(parent, textvariable, from_=1, to=99, width=5):
    return tk.Spinbox(parent, textvariable=textvariable, from_=from_, to=to,
                      width=width, font=_FNT, relief=tk.SUNKEN, bd=2)


class AboutDialog(tk.Toplevel):
    """About dialog showing application information."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("About SMath Studio")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#ece9d8")

        self.geometry("420x300")
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

        # Blue header banner
        banner = tk.Frame(self, bg="#003399", height=60)
        banner.pack(fill=tk.X)
        banner.pack_propagate(False)
        tk.Label(
            banner, text="SMath Studio", font=("DejaVu Sans", 20, "bold"),
            fg="white", bg="#003399",
        ).pack(pady=(12, 0))
        tk.Label(
            banner, text="Python Edition", font=("DejaVu Sans", 10),
            fg="#aaccff", bg="#003399",
        ).pack()

        frame = tk.Frame(self, bg="#ece9d8", padx=20, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        from .. import __version__
        tk.Label(
            frame, text=f"Version {__version__}", font=("DejaVu Sans", 10),
            bg="#ece9d8", fg="#333333",
        ).pack(pady=(0, 10))

        tk.Label(
            frame,
            text=(
                "A Python implementation of SMath Studio,\n"
                "the mathematical worksheet application.\n\n"
                "Supports parsing, evaluating, and rendering\n"
                "SMath Studio .sm worksheet files."
            ),
            justify=tk.CENTER, font=("DejaVu Sans", 9),
            bg="#ece9d8", fg="#444444",
        ).pack(pady=(0, 16))

        btn_frame = tk.Frame(frame, bg="#ece9d8")
        btn_frame.pack()
        ok_btn = tk.Button(
            btn_frame, text="OK", command=self.destroy, width=12,
            font=("DejaVu Sans", 9), bg="#ece9d8", activebackground="#c1d2ee",
            relief=tk.RAISED, bd=1, padx=8, pady=2,
        )
        ok_btn.pack()
        ok_btn.focus_set()

        self.bind("<Return>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())


class _TabBar(tk.Frame):
    """Simple tab bar widget styled to match Windows classic look."""

    def __init__(self, parent, tabs, on_select):
        super().__init__(parent, bg=_BG)
        self._tabs = tabs
        self._on_select = on_select
        self._buttons: list[tk.Label] = []
        self._selected = 0
        for i, name in enumerate(tabs):
            lbl = tk.Label(
                self, text=f"  {name}  ", font=_FNT,
                bg=_BG, fg="#000000", bd=1, relief=tk.RAISED, padx=6, pady=2,
            )
            lbl.pack(side=tk.LEFT, padx=(0, 1))
            lbl.bind("<Button-1>", lambda e, idx=i: self._select(idx))
            self._buttons.append(lbl)
        self._select(0)

    def _select(self, idx):
        self._selected = idx
        for i, btn in enumerate(self._buttons):
            if i == idx:
                btn.configure(relief=tk.FLAT, bg="white", fg="#000000")
            else:
                btn.configure(relief=tk.RAISED, bg=_BG, fg="#000000")
        self._on_select(idx)


class OptionsDialog(tk.Toplevel):
    """Options dialog for calculation settings."""

    def __init__(self, parent: tk.Widget, settings: dict):
        super().__init__(parent)
        self.title("Options")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=_BG)
        self.result: Optional[dict] = None

        self.geometry("400x380")
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

        frame = tk.Frame(self, bg=_BG, padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Tab pages
        self._pages: list[tk.Frame] = []

        # --- Build tab content frames ---
        # Calculation
        calc_frame = tk.Frame(frame, bg="white", bd=1, relief=tk.SUNKEN, padx=12, pady=12)
        self._pages.append(calc_frame)

        _xp_label(calc_frame, "Decimal precision:").configure(bg="white")
        _xp_label(calc_frame, "Decimal precision:").destroy()
        r = 0
        lbl = tk.Label(calc_frame, text="Decimal precision:", font=_FNT, bg="white")
        lbl.grid(row=r, column=0, sticky=tk.W, pady=4)
        self._precision_var = tk.IntVar(value=settings.get("precision", 4))
        _xp_spin(calc_frame, self._precision_var, 1, 15, 6).grid(
            row=r, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        r += 1
        tk.Label(calc_frame, text="Result format:", font=_FNT, bg="white").grid(
            row=r, column=0, sticky=tk.W, pady=4)
        self._fractions_var = tk.StringVar(value=settings.get("fractions", "decimal"))
        frac_menu = tk.OptionMenu(calc_frame, self._fractions_var, "decimal", "fraction")
        frac_menu.configure(font=_FNT, bg="white", relief=tk.SUNKEN, bd=1,
                            highlightthickness=0, width=10)
        frac_menu.grid(row=r, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        r += 1
        tk.Label(calc_frame, text="Angle units:", font=_FNT, bg="white").grid(
            row=r, column=0, sticky=tk.W, pady=4)
        self._angle_var = tk.StringVar(value=settings.get("angle_units", "radians"))
        angle_menu = tk.OptionMenu(calc_frame, self._angle_var, "radians", "degrees")
        angle_menu.configure(font=_FNT, bg="white", relief=tk.SUNKEN, bd=1,
                             highlightthickness=0, width=10)
        angle_menu.grid(row=r, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        r += 1
        self._trailing_var = tk.BooleanVar(value=settings.get("trailing_zeros", True))
        tk.Checkbutton(calc_frame, text="Show trailing zeros", variable=self._trailing_var,
                       font=_FNT, bg="white", activebackground="white",
                       selectcolor="white", anchor="w").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=4)

        r += 1
        self._sigdig_var = tk.BooleanVar(value=settings.get("significant_digits_mode", False))
        tk.Checkbutton(calc_frame, text="Significant digits mode", variable=self._sigdig_var,
                       font=_FNT, bg="white", activebackground="white",
                       selectcolor="white", anchor="w").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=4)

        # Display
        disp_frame = tk.Frame(frame, bg="white", bd=1, relief=tk.SUNKEN, padx=12, pady=12)
        self._pages.append(disp_frame)

        r = 0
        tk.Label(disp_frame, text="Exponential threshold:", font=_FNT, bg="white").grid(
            row=r, column=0, sticky=tk.W, pady=4)
        self._exp_threshold_var = tk.IntVar(value=settings.get("exponential_threshold", 3))
        _xp_spin(disp_frame, self._exp_threshold_var, 1, 15, 6).grid(
            row=r, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        r += 1
        self._show_border_var = tk.BooleanVar(value=settings.get("show_region_borders", False))
        tk.Checkbutton(disp_frame, text="Show region borders", variable=self._show_border_var,
                       font=_FNT, bg="white", activebackground="white",
                       selectcolor="white", anchor="w").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=4)

        r += 1
        self._syntax_color_var = tk.BooleanVar(value=settings.get("syntax_coloring", True))
        tk.Checkbutton(disp_frame, text="Syntax coloring", variable=self._syntax_color_var,
                       font=_FNT, bg="white", activebackground="white",
                       selectcolor="white", anchor="w").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=4)

        # Interface
        iface_frame = tk.Frame(frame, bg="white", bd=1, relief=tk.SUNKEN, padx=12, pady=12)
        self._pages.append(iface_frame)

        r = 0
        self._auto_scroll_var = tk.BooleanVar(value=settings.get("auto_scroll", True))
        tk.Checkbutton(iface_frame, text="Auto-scroll to cursor", variable=self._auto_scroll_var,
                       font=_FNT, bg="white", activebackground="white",
                       selectcolor="white", anchor="w").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=4)

        r += 1
        self._snap_grid_var = tk.BooleanVar(value=settings.get("snap_to_grid", True))
        tk.Checkbutton(iface_frame, text="Snap to grid", variable=self._snap_grid_var,
                       font=_FNT, bg="white", activebackground="white",
                       selectcolor="white", anchor="w").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=4)

        r += 1
        tk.Label(iface_frame, text="Grid size:", font=_FNT, bg="white").grid(
            row=r, column=0, sticky=tk.W, pady=4)
        self._grid_size_var = tk.IntVar(value=settings.get("grid_size", 8))
        _xp_spin(iface_frame, self._grid_size_var, 4, 32, 6).grid(
            row=r, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        # Tab bar
        tab_bar = _TabBar(frame, ["Calculation", "Display", "Interface"], self._show_tab)
        tab_bar.pack(fill=tk.X)
        self._tab_container = tk.Frame(frame, bg=_BG)
        self._tab_container.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        self._show_tab(0)

        # Buttons
        btn_frame = tk.Frame(frame, bg=_BG)
        btn_frame.pack(fill=tk.X)
        _xp_btn(btn_frame, "Cancel", self.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        _xp_btn(btn_frame, "OK", self._on_ok).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda e: self.destroy())

    def _show_tab(self, idx):
        for p in self._pages:
            p.pack_forget()
        self._pages[idx].pack(in_=self._tab_container, fill=tk.BOTH, expand=True)

    def _on_ok(self):
        self.result = {
            "precision": self._precision_var.get(),
            "fractions": self._fractions_var.get(),
            "angle_units": self._angle_var.get(),
            "trailing_zeros": self._trailing_var.get(),
            "significant_digits_mode": self._sigdig_var.get(),
            "exponential_threshold": self._exp_threshold_var.get(),
            "show_region_borders": self._show_border_var.get(),
            "syntax_coloring": self._syntax_color_var.get(),
            "auto_scroll": self._auto_scroll_var.get(),
            "snap_to_grid": self._snap_grid_var.get(),
            "grid_size": self._grid_size_var.get(),
        }
        self.destroy()


class InsertFunctionDialog(tk.Toplevel):
    """Searchable dialog for inserting built-in functions."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("Insert Function")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=_BG)
        self.result: Optional[str] = None

        self.geometry("420x480")
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

        frame = tk.Frame(self, bg=_BG, padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        search_frame = tk.Frame(frame, bg=_BG)
        search_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(search_frame, text="Search:", font=_FNT, bg=_BG).pack(side=tk.LEFT, padx=(0, 6))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)
        search_entry = _xp_entry(search_frame, self._search_var, 30)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.focus_set()

        list_frame = tk.Frame(frame, bg=_BG)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self._listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set,
            font=("Consolas", 10), selectmode=tk.SINGLE,
            bg="white", selectbackground="#316ac5", selectforeground="white",
            relief=tk.SUNKEN, bd=2,
        )
        scrollbar.config(command=self._listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._listbox.bind("<Double-1>", lambda e: self._on_ok())

        self._desc_label = tk.Label(
            frame, text="", wraplength=380, justify=tk.LEFT,
            font=_FNT, bg=_BG, fg="#444444", anchor="w",
        )
        self._desc_label.pack(fill=tk.X, pady=(0, 8))

        btn_frame = tk.Frame(frame, bg=_BG)
        btn_frame.pack(fill=tk.X)
        _xp_btn(btn_frame, "Cancel", self.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        _xp_btn(btn_frame, "Insert", self._on_ok).pack(side=tk.RIGHT)

        self._functions = _build_function_list()
        self._populate_list("")

        self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def _populate_list(self, query: str):
        self._listbox.delete(0, tk.END)
        query_lower = query.lower()
        for name, desc in self._functions:
            if query_lower in name.lower() or query_lower in desc.lower():
                self._listbox.insert(tk.END, name)

    def _on_search_changed(self, *_args):
        self._populate_list(self._search_var.get())

    def _on_select(self, _event):
        sel = self._listbox.curselection()
        if sel:
            name = self._listbox.get(sel[0])
            for fn, desc in self._functions:
                if fn == name:
                    self._desc_label.config(text=desc)
                    break

    def _on_ok(self):
        sel = self._listbox.curselection()
        if sel:
            self.result = self._listbox.get(sel[0])
        self.destroy()


# ---------------------------------------------------------------------------
# Function descriptions
# ---------------------------------------------------------------------------

_FUNCTION_DESCRIPTIONS: dict[str, str] = {
    # Trigonometric
    "sin": "sin(x) -- Sine of x (radians)",
    "cos": "cos(x) -- Cosine of x (radians)",
    "tan": "tan(x) -- Tangent of x (radians)",
    "cot": "cot(x) -- Cotangent of x (radians)",
    "sec": "sec(x) -- Secant of x (radians)",
    "csc": "csc(x) -- Cosecant of x (radians)",
    "asin": "asin(x) -- Arcsine, returns radians",
    "acos": "acos(x) -- Arccosine, returns radians",
    "atan": "atan(x) -- Arctangent, returns radians",
    "acot": "acot(x) -- Arc-cotangent, returns radians",
    "asec": "asec(x) -- Arc-secant, returns radians",
    "acsc": "acsc(x) -- Arc-cosecant, returns radians",
    "atan2": "atan2(y, x) -- Two-argument arctangent",
    # Hyperbolic
    "sinh": "sinh(x) -- Hyperbolic sine",
    "cosh": "cosh(x) -- Hyperbolic cosine",
    "tanh": "tanh(x) -- Hyperbolic tangent",
    "coth": "coth(x) -- Hyperbolic cotangent",
    "sech": "sech(x) -- Hyperbolic secant",
    "csch": "csch(x) -- Hyperbolic cosecant",
    "asinh": "asinh(x) -- Inverse hyperbolic sine",
    "acosh": "acosh(x) -- Inverse hyperbolic cosine",
    "atanh": "atanh(x) -- Inverse hyperbolic tangent",
    # Exponential / log / roots
    "exp": "exp(x) -- Exponential function e^x",
    "ln": "ln(x) -- Natural logarithm",
    "log": "log(x) or log(x, base) -- Logarithm",
    "log2": "log2(x) -- Base-2 logarithm",
    "sqrt": "sqrt(x) -- Square root",
    "cbrt": "cbrt(x) -- Cube root",
    "nthroot": "nthroot(x, n) -- N-th root of x",
    # Basic math
    "abs": "abs(x) -- Absolute value",
    "sign": "sign(x) -- Sign function (-1, 0, or 1)",
    "ceil": "ceil(x) -- Ceiling (round up to integer)",
    "floor": "floor(x) -- Floor (round down to integer)",
    "round": "round(x) or round(x, places) -- Round to nearest",
    "max": "max(x) -- Maximum value in vector/matrix",
    "min": "min(x) -- Minimum value in vector/matrix",
    "mod": "mod(a, b) -- Remainder of a divided by b",
    "factorial": "factorial(n) -- n! factorial",
    "numericValue": "numericValue(x) -- Extract numeric value from quantity",
    # Complex numbers
    "Re": "Re(z) -- Real part of complex number",
    "Im": "Im(z) -- Imaginary part of complex number",
    "arg": "arg(z) -- Argument (phase) of complex number",
    "conj": "conj(z) -- Complex conjugate",
    # Number theory
    "gcd": "gcd(a, b) -- Greatest common divisor",
    "lcm": "lcm(a, b) -- Least common multiple",
    "isPrime": "isPrime(n) -- Returns 1 if n is prime, 0 otherwise",
    "Cn": "Cn(n, k) -- Combinations (n choose k)",
    "Pn": "Pn(n, k) -- Permutations P(n, k)",
    # Special functions
    "Gamma": "Gamma(x) -- Gamma function",
    "erf": "erf(x) -- Error function",
    # Matrix
    "mat": "mat(e1, ..., rows, cols) -- Create a matrix",
    "el": "el(M, row, col) -- Element access (1-based)",
    "rows": "rows(M) -- Number of rows in matrix M",
    "cols": "cols(M) -- Number of columns in matrix M",
    "col": "col(M, j) -- Extract column j from matrix M",
    "det": "det(M) -- Determinant of matrix M",
    "invert": "invert(M) -- Inverse of matrix M",
    "transpose": "transpose(M) -- Transpose of matrix M",
    "identity": "identity(n) -- n x n identity matrix",
    "stack": "stack(A, B) -- Stack matrices vertically",
    "augment": "augment(A, B) -- Augment matrices horizontally",
    "tr": "tr(M) -- Trace of matrix M (sum of diagonal)",
    "polyroots": "polyroots(p) -- Polynomial roots from coefficients",
    "csort": "csort(M, col) -- Sort matrix rows by column",
    "submatrix": "submatrix(M, r1, c1, r2, c2) -- Extract submatrix",
    "eigenvals": "eigenvals(M) -- Eigenvalues of matrix M",
    "eigenvecs": "eigenvecs(M) -- Eigenvectors of matrix M",
    "rank": "rank(M) -- Rank of matrix M",
    "norm": "norm(M) -- Frobenius norm of matrix/vector",
    "cross": "cross(a, b) -- Cross product of 3D vectors",
    "dot": "dot(a, b) -- Dot product of vectors",
    "zeros": "zeros(rows, cols) -- Zero matrix",
    "ones": "ones(rows, cols) -- Matrix of ones",
    "diag": "diag(v) -- Diagonal matrix from vector",
    "solve": "solve(A, b) -- Solve linear system Ax = b",
    "lsolve": "lsolve(A, b) -- Solve linear system Ax = b",
    "length": "length(x) -- Length of vector/string",
    "sort": "sort(x) -- Sort vector/matrix",
    "reverse": "reverse(x) -- Reverse vector/matrix",
    "unique": "unique(x) -- Unique elements of vector",
    # Statistics
    "mean": "mean(x) -- Arithmetic mean of vector/matrix",
    "median": "median(x) -- Median of vector/matrix",
    "stdev": "stdev(x) -- Standard deviation (sample)",
    "variance": "variance(x) -- Variance (sample)",
    # Control flow
    "if": "if(cond, true_val, false_val) -- Conditional",
    "for": "for(init, cond, incr, body) -- For loop",
    "while": "while(cond, body) -- While loop",
    "line": "line(e1, e2, ..., n, 1) -- Block of statements",
    # Numeric
    "range": "range(start, end) -- Integer range vector",
    "eval": "eval(expr) -- Force numeric evaluation",
    "diff": "diff(f, x) -- Numerical derivative df/dx",
    "int": "int(f, x, a, b) -- Numerical integration",
    "nintegrate": "nintegrate(f, x, a, b) -- Numerical integration",
    "sum": "sum(expr, var, start, end) -- Summation",
    "product": "product(expr, var, start, end) -- Product",
    # String
    "num2str": "num2str(x) -- Convert number to string",
    "str2num": "str2num(s) -- Convert string to number",
    "concat": "concat(a, b, ...) -- Concatenate strings",
    "strlen": "strlen(s) -- Length of string",
    "substr": "substr(s, start, len) -- Substring extraction",
    "strpos": "strpos(s, sub) -- Position of substring",
    "strsplit": "strsplit(s, delim) -- Split string by delimiter",
    "upper": "upper(s) -- Convert string to uppercase",
    "lower": "lower(s) -- Convert string to lowercase",
}


class FindReplaceDialog(tk.Toplevel):
    """Find and Replace dialog for worksheet expressions."""

    def __init__(self, parent: tk.Widget, on_find=None, on_replace=None, on_replace_all=None):
        super().__init__(parent)
        self.title("Find and Replace")
        self.resizable(True, False)
        self.transient(parent)
        self.configure(bg=_BG)
        self.geometry("420x180")

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - 210}+{ph - 90}")

        self._on_find = on_find
        self._on_replace = on_replace
        self._on_replace_all = on_replace_all

        frame = tk.Frame(self, bg=_BG, padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Find:", font=_FNT, bg=_BG).grid(row=0, column=0, sticky="w", pady=4)
        self.find_var = tk.StringVar()
        self.find_entry = _xp_entry(frame, self.find_var, 30)
        self.find_entry.grid(row=0, column=1, padx=(8, 0), pady=4, sticky="ew")

        tk.Label(frame, text="Replace:", font=_FNT, bg=_BG).grid(row=1, column=0, sticky="w", pady=4)
        self.replace_var = tk.StringVar()
        self.replace_entry = _xp_entry(frame, self.replace_var, 30)
        self.replace_entry.grid(row=1, column=1, padx=(8, 0), pady=4, sticky="ew")

        self.case_var = tk.BooleanVar(value=False)
        _xp_check(frame, "Match case", self.case_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=4)

        btn_frame = tk.Frame(frame, bg=_BG)
        btn_frame.grid(row=0, column=2, rowspan=3, padx=(12, 0), sticky="n")

        _xp_btn(btn_frame, "Find Next", self._do_find, 12).pack(pady=2)
        _xp_btn(btn_frame, "Replace", self._do_replace, 12).pack(pady=2)
        _xp_btn(btn_frame, "Replace All", self._do_replace_all, 12).pack(pady=2)
        _xp_btn(btn_frame, "Close", self.destroy, 12).pack(pady=2)

        frame.columnconfigure(1, weight=1)
        self.find_entry.focus_set()
        self.bind("<Return>", lambda e: self._do_find())
        self.bind("<Escape>", lambda e: self.destroy())

    def _do_find(self):
        if self._on_find:
            self._on_find(self.find_var.get(), self.case_var.get())

    def _do_replace(self):
        if self._on_replace:
            self._on_replace(self.find_var.get(), self.replace_var.get(), self.case_var.get())

    def _do_replace_all(self):
        if self._on_replace_all:
            self._on_replace_all(self.find_var.get(), self.replace_var.get(), self.case_var.get())


class MatrixSizeDialog(tk.Toplevel):
    """Dialog for choosing matrix dimensions."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("Insert Matrix")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=_BG)
        self.result: Optional[tuple[int, int]] = None

        frame = tk.Frame(self, bg=_BG, padx=15, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Rows:", font=_FNT, bg=_BG).grid(
            row=0, column=0, padx=5, pady=5, sticky="e")
        self._rows_var = tk.StringVar(value="2")
        rows_spin = _xp_spin(frame, self._rows_var, 1, 20, 5)
        rows_spin.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame, text="Columns:", font=_FNT, bg=_BG).grid(
            row=1, column=0, padx=5, pady=5, sticky="e")
        self._cols_var = tk.StringVar(value="2")
        _xp_spin(frame, self._cols_var, 1, 20, 5).grid(row=1, column=1, padx=5, pady=5)

        btn_frame = tk.Frame(frame, bg=_BG)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        _xp_btn(btn_frame, "OK", self._on_ok, 8).pack(side=tk.LEFT, padx=5)
        _xp_btn(btn_frame, "Cancel", self.destroy, 8).pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        rows_spin.focus_set()
        self.wait_window()

    def _on_ok(self):
        try:
            rows = max(1, min(20, int(self._rows_var.get())))
            cols = max(1, min(20, int(self._cols_var.get())))
            self.result = (rows, cols)
        except ValueError:
            self.result = (2, 2)
        self.destroy()


class InsertPlotDialog(tk.Toplevel):
    """Dialog for inserting a 2D plot region."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("Insert Plot")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=_BG)
        self.result: Optional[dict] = None

        frame = tk.Frame(self, bg=_BG, padx=15, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Expression (e.g. sin(x)):", font=_FNT, bg=_BG).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self._expr_var = tk.StringVar(value="sin(x)")
        expr_entry = _xp_entry(frame, self._expr_var, 30)
        expr_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)

        for r, lbl_text, default in [
            (2, "X min:", "-10"), (3, "X max:", "10"),
            (4, "Width:", "400"), (5, "Height:", "300"),
        ]:
            tk.Label(frame, text=lbl_text, font=_FNT, bg=_BG).grid(
                row=r, column=0, sticky="e", padx=5, pady=3)
            var = tk.StringVar(value=default)
            _xp_entry(frame, var, 8).grid(row=r, column=1, sticky="w", pady=3)
            setattr(self, f"_{'xmin' if r==2 else 'xmax' if r==3 else 'width' if r==4 else 'height'}_var", var)

        btn_frame = tk.Frame(frame, bg=_BG)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        _xp_btn(btn_frame, "Insert", self._on_ok, 8).pack(side=tk.LEFT, padx=5)
        _xp_btn(btn_frame, "Cancel", self.destroy, 8).pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        expr_entry.focus_set()
        expr_entry.select_range(0, tk.END)
        self.wait_window()

    def _on_ok(self):
        expr = self._expr_var.get().strip()
        if not expr:
            self.destroy()
            return
        try:
            xmin = float(self._xmin_var.get())
            xmax = float(self._xmax_var.get())
            w = int(self._width_var.get())
            h = int(self._height_var.get())
        except ValueError:
            xmin, xmax, w, h = -10, 10, 400, 300
        self.result = {
            "expression": expr,
            "x_min": xmin,
            "x_max": xmax,
            "width": w,
            "height": h,
        }
        self.destroy()


class PageSetupDialog(tk.Toplevel):
    """Dialog for configuring page size, margins, and orientation."""

    PAPER_SIZES = {
        "Letter": (850, 1100),
        "A4": (793, 1122),
        "A3": (1122, 1587),
        "A5": (559, 793),
        "Legal": (850, 1400),
        "B5": (665, 944),
    }

    def __init__(self, parent: tk.Widget, page_model=None):
        super().__init__(parent)
        self.title("Page Setup")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=_BG)
        self.result: Optional[dict] = None

        frame = tk.Frame(self, bg=_BG, padx=15, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)

        pw = page_model.paper_width if page_model else 850
        ph = page_model.paper_height if page_model else 1100
        orient = page_model.paper_orientation if page_model else "Portrait"
        ml = page_model.margin_left if page_model else 39
        mr = page_model.margin_right if page_model else 39
        mt = page_model.margin_top if page_model else 39
        mb = page_model.margin_bottom if page_model else 39

        tk.Label(frame, text="Paper Size:", font=_FNT, bg=_BG).grid(
            row=0, column=0, sticky="e", padx=5, pady=4)
        self._paper_var = tk.StringVar(value="Letter")
        for name, (w, h) in self.PAPER_SIZES.items():
            if (w == pw and h == ph) or (h == pw and w == ph):
                self._paper_var.set(name)
                break
        paper_menu = tk.OptionMenu(frame, self._paper_var, *list(self.PAPER_SIZES.keys()))
        paper_menu.configure(font=_FNT, bg=_BG, relief=tk.SUNKEN, bd=1,
                             highlightthickness=0, width=12)
        paper_menu.grid(row=0, column=1, sticky="w", pady=4)

        tk.Label(frame, text="Orientation:", font=_FNT, bg=_BG).grid(
            row=1, column=0, sticky="e", padx=5, pady=4)
        self._orient_var = tk.StringVar(value=orient)
        orient_frame = tk.Frame(frame, bg=_BG)
        orient_frame.grid(row=1, column=1, sticky="w", pady=4)
        _xp_radio(orient_frame, "Portrait", self._orient_var, "Portrait").pack(side=tk.LEFT)
        _xp_radio(orient_frame, "Landscape", self._orient_var, "Landscape").pack(side=tk.LEFT, padx=8)

        margin_frame = tk.LabelFrame(frame, text="Margins", font=_FNT, bg=_BG,
                                     padx=8, pady=8)
        margin_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)

        for i, (lbl, val, attr) in enumerate([
            ("Left:", ml, "ml"), ("Right:", mr, "mr"),
            ("Top:", mt, "mt"), ("Bottom:", mb, "mb"),
        ]):
            tk.Label(margin_frame, text=lbl, font=_FNT, bg=_BG).grid(
                row=i // 2, column=(i % 2) * 2, sticky="e", padx=3, pady=2)
            var = tk.StringVar(value=str(val))
            setattr(self, f"_{attr}_var", var)
            _xp_entry(margin_frame, var, 6).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=3, pady=2)

        hf_frame = tk.LabelFrame(frame, text="Header / Footer", font=_FNT, bg=_BG,
                                 padx=8, pady=8)
        hf_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)

        hdr_text = ""
        ftr_text = ""
        if page_model and page_model.header:
            hdr_text = page_model.header.text
        if page_model and page_model.footer:
            ftr_text = page_model.footer.text

        tk.Label(hf_frame, text="Header:", font=_FNT, bg=_BG).grid(
            row=0, column=0, sticky="e", padx=3, pady=2)
        self._header_var = tk.StringVar(value=hdr_text)
        _xp_entry(hf_frame, self._header_var, 30).grid(
            row=0, column=1, sticky="ew", padx=3, pady=2)

        tk.Label(hf_frame, text="Footer:", font=_FNT, bg=_BG).grid(
            row=1, column=0, sticky="e", padx=3, pady=2)
        self._footer_var = tk.StringVar(value=ftr_text)
        _xp_entry(hf_frame, self._footer_var, 30).grid(
            row=1, column=1, sticky="ew", padx=3, pady=2)

        tk.Label(hf_frame, text="Codes: &[DATE] &[TIME] &[FILENAME] &[PAGENUM] &[COUNT]",
                 font=_FNT_SM, bg=_BG, fg="#666666").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=3)

        btn_frame = tk.Frame(frame, bg=_BG)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        _xp_btn(btn_frame, "OK", self._on_ok, 8).pack(side=tk.LEFT, padx=5)
        _xp_btn(btn_frame, "Cancel", self.destroy, 8).pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window()

    def _on_ok(self):
        paper_name = self._paper_var.get()
        pw, ph = self.PAPER_SIZES.get(paper_name, (850, 1100))
        if self._orient_var.get() == "Landscape":
            pw, ph = ph, pw
        try:
            ml = int(self._ml_var.get())
            mr = int(self._mr_var.get())
            mt = int(self._mt_var.get())
            mb = int(self._mb_var.get())
        except ValueError:
            ml = mr = mt = mb = 39
        self.result = {
            "paper_width": pw, "paper_height": ph,
            "orientation": self._orient_var.get(),
            "margin_left": ml, "margin_right": mr,
            "margin_top": mt, "margin_bottom": mb,
            "header": self._header_var.get(),
            "footer": self._footer_var.get(),
        }
        self.destroy()


class UnitsBrowserDialog(tk.Toplevel):
    """Dialog for browsing and inserting measurement units."""

    UNIT_CATEGORIES = {
        "Length": [
            ("m", "meter"), ("km", "kilometer"), ("cm", "centimeter"),
            ("mm", "millimeter"), ("um", "micrometer"), ("nm", "nanometer"),
            ("mi", "mile"), ("yd", "yard"), ("ft", "foot"), ("in", "inch"),
        ],
        "Mass": [
            ("kg", "kilogram"), ("g", "gram"), ("mg", "milligram"),
            ("t", "metric ton"), ("lb", "pound"), ("oz", "ounce"),
        ],
        "Time": [
            ("s", "second"), ("ms", "millisecond"), ("us", "microsecond"),
            ("min", "minute"), ("hr", "hour"), ("day", "day"),
        ],
        "Force": [
            ("N", "newton"), ("kN", "kilonewton"), ("lbf", "pound-force"),
            ("dyn", "dyne"), ("kgf", "kilogram-force"),
        ],
        "Energy": [
            ("J", "joule"), ("kJ", "kilojoule"), ("MJ", "megajoule"),
            ("cal", "calorie"), ("kcal", "kilocalorie"),
            ("eV", "electronvolt"), ("kWh", "kilowatt-hour"),
            ("BTU", "British thermal unit"),
        ],
        "Power": [
            ("W", "watt"), ("kW", "kilowatt"), ("MW", "megawatt"),
            ("hp", "horsepower"),
        ],
        "Pressure": [
            ("Pa", "pascal"), ("kPa", "kilopascal"), ("MPa", "megapascal"),
            ("bar", "bar"), ("atm", "atmosphere"), ("psi", "psi"),
            ("mmHg", "millimeters of mercury"),
        ],
        "Temperature": [
            ("K", "kelvin"), ("degC", "degree Celsius"), ("degF", "degree Fahrenheit"),
        ],
        "Angle": [
            ("rad", "radian"), ("deg", "degree"), ("grad", "gradian"),
            ("rev", "revolution"),
        ],
        "Electric": [
            ("A", "ampere"), ("V", "volt"), ("ohm", "ohm"),
            ("F", "farad"), ("H", "henry"), ("C", "coulomb"),
            ("S", "siemens"), ("Wb", "weber"), ("T", "tesla"),
        ],
        "Frequency": [
            ("Hz", "hertz"), ("kHz", "kilohertz"), ("MHz", "megahertz"),
            ("GHz", "gigahertz"),
        ],
        "Volume": [
            ("L", "liter"), ("mL", "milliliter"), ("gal", "gallon"),
            ("qt", "quart"), ("pt", "pint"), ("fl_oz", "fluid ounce"),
        ],
        "Area": [
            ("m2", "square meter"), ("cm2", "square centimeter"),
            ("km2", "square kilometer"), ("ha", "hectare"),
            ("acre", "acre"), ("ft2", "square foot"), ("in2", "square inch"),
        ],
        "Velocity": [
            ("m/s", "meters per second"), ("km/h", "kilometers per hour"),
            ("mph", "miles per hour"), ("kn", "knot"),
        ],
    }

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("Units Browser")
        self.geometry("450x400")
        self.transient(parent)
        self.grab_set()
        self.configure(bg=_BG)
        self.result: Optional[str] = None

        frame = tk.Frame(self, bg=_BG, padx=8, pady=8)
        frame.pack(fill=tk.BOTH, expand=True)

        paned = tk.PanedWindow(frame, orient=tk.HORIZONTAL, bg=_BG,
                               sashwidth=4, sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True)

        cat_frame = tk.Frame(paned, bg=_BG)
        paned.add(cat_frame)

        tk.Label(cat_frame, text="Category", font=_FNT_BOLD, bg=_BG).pack(anchor="w")
        self._cat_list = tk.Listbox(cat_frame, font=_FNT, exportselection=False,
                                    bg="white", selectbackground="#316ac5",
                                    selectforeground="white", relief=tk.SUNKEN, bd=2)
        self._cat_list.pack(fill=tk.BOTH, expand=True)
        for cat in self.UNIT_CATEGORIES:
            self._cat_list.insert(tk.END, cat)
        self._cat_list.bind("<<ListboxSelect>>", self._on_cat_select)

        unit_frame = tk.Frame(paned, bg=_BG)
        paned.add(unit_frame)

        tk.Label(unit_frame, text="Unit", font=_FNT_BOLD, bg=_BG).pack(anchor="w")
        self._unit_list = tk.Listbox(unit_frame, font=_FNT, exportselection=False,
                                     bg="white", selectbackground="#316ac5",
                                     selectforeground="white", relief=tk.SUNKEN, bd=2)
        self._unit_list.pack(fill=tk.BOTH, expand=True)
        self._unit_list.bind("<Double-1>", lambda e: self._on_ok())

        btn_frame = tk.Frame(frame, bg=_BG)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        _xp_btn(btn_frame, "Insert", self._on_ok, 8).pack(side=tk.LEFT, padx=5)
        _xp_btn(btn_frame, "Cancel", self.destroy, 8).pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self._cat_list.select_set(0)
        self._on_cat_select(None)
        self.wait_window()

    def _on_cat_select(self, event):
        sel = self._cat_list.curselection()
        if not sel:
            return
        cat = self._cat_list.get(sel[0])
        units = self.UNIT_CATEGORIES.get(cat, [])
        self._unit_list.delete(0, tk.END)
        for symbol, name in units:
            self._unit_list.insert(tk.END, f"{symbol}  —  {name}")

    def _on_ok(self):
        sel = self._unit_list.curselection()
        if not sel:
            return
        text = self._unit_list.get(sel[0])
        self.result = text.split("  —")[0].strip()
        self.destroy()


class PrintPreviewDialog(tk.Toplevel):
    """Print preview showing a scaled rendering of worksheet pages."""

    def __init__(self, parent: tk.Widget, canvas: tk.Canvas, page_w: int, page_h: int, num_pages: int = 1):
        super().__init__(parent)
        self.title("Print Preview")
        self.transient(parent)
        self.grab_set()
        self.configure(bg=_BG)
        self.geometry("700x550")
        self.minsize(500, 400)

        self._src_canvas = canvas
        self._page_w = page_w
        self._page_h = page_h
        self._num_pages = max(num_pages, 1)
        self._current_page = 0
        self._scale = 0.5

        toolbar = tk.Frame(self, bg=_BG)
        toolbar.pack(fill=tk.X, padx=4, pady=4)

        _xp_btn(toolbar, "Print", self._on_print, 6).pack(side=tk.LEFT, padx=2)
        tk.Frame(toolbar, width=2, height=20, bg="#a0a0a0", bd=0).pack(
            side=tk.LEFT, fill=tk.Y, padx=4, pady=2)

        _xp_btn(toolbar, "<", self._prev_page, 3).pack(side=tk.LEFT)
        self._page_label = tk.Label(toolbar, text=f"Page 1 of {self._num_pages}",
                                    font=_FNT, bg=_BG)
        self._page_label.pack(side=tk.LEFT, padx=6)
        _xp_btn(toolbar, ">", self._next_page, 3).pack(side=tk.LEFT)

        tk.Frame(toolbar, width=2, height=20, bg="#a0a0a0", bd=0).pack(
            side=tk.LEFT, fill=tk.Y, padx=4, pady=2)
        _xp_btn(toolbar, "Zoom In", lambda: self._zoom(1.25), 8).pack(side=tk.LEFT, padx=2)
        _xp_btn(toolbar, "Zoom Out", lambda: self._zoom(0.8), 8).pack(side=tk.LEFT, padx=2)
        _xp_btn(toolbar, "Close", self.destroy, 6).pack(side=tk.RIGHT, padx=2)

        container = tk.Frame(self, bg=_BG)
        container.pack(fill=tk.BOTH, expand=True)
        self._preview = tk.Canvas(container, bg="#808080", highlightthickness=0)
        self._preview.pack(fill=tk.BOTH, expand=True)
        self._draw_page()
        self.bind("<Configure>", lambda e: self._draw_page())

    def _draw_page(self):
        self._preview.delete("all")
        pw = self._preview.winfo_width() or 680
        ph = self._preview.winfo_height() or 480
        scaled_w = int(self._page_w * self._scale)
        scaled_h = int(self._page_h * self._scale)
        ox = max((pw - scaled_w) // 2, 10)
        oy = max((ph - scaled_h) // 2, 10)

        self._preview.create_rectangle(ox + 3, oy + 3, ox + scaled_w + 3, oy + scaled_h + 3,
                                        fill="#666666", outline="")
        self._preview.create_rectangle(ox, oy, ox + scaled_w, oy + scaled_h,
                                        fill="white", outline="#333333")

        margin = int(40 * self._scale)
        self._preview.create_rectangle(ox + margin, oy + margin,
                                        ox + scaled_w - margin, oy + scaled_h - margin,
                                        outline="#e0e0e0", dash=(2, 4))
        self._page_label.config(text=f"Page {self._current_page + 1} of {self._num_pages}")

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._draw_page()

    def _next_page(self):
        if self._current_page < self._num_pages - 1:
            self._current_page += 1
            self._draw_page()

    def _zoom(self, factor):
        self._scale = max(0.2, min(2.0, self._scale * factor))
        self._draw_page()

    def _on_print(self):
        self.destroy()


def _build_function_list() -> list[tuple[str, str]]:
    """Build sorted list of (name, description) for all known functions."""
    result = []
    seen = set()
    # Include described functions first
    for name in sorted(_FUNCTION_DESCRIPTIONS):
        result.append((name, _FUNCTION_DESCRIPTIONS[name]))
        seen.add(name)
    # Add any remaining built-in functions without descriptions
    for name in sorted(BUILTIN_FUNCTIONS):
        if name not in seen:
            result.append((name, f"{name}(...) -- Built-in function"))
    return result
