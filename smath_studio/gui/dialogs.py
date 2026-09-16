"""Dialog windows for SMath Studio GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..functions import BUILTIN_FUNCTIONS


class AboutDialog(tk.Toplevel):
    """About dialog showing application information."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("About SMath Studio")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.geometry("400x280")
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(
            frame,
            text="SMath Studio",
            font=("DejaVu Sans", 18, "bold"),
        )
        title_label.pack(pady=(0, 4))

        subtitle_label = ttk.Label(
            frame,
            text="Python Edition",
            font=("DejaVu Sans", 12),
        )
        subtitle_label.pack(pady=(0, 12))

        from .. import __version__
        version_label = ttk.Label(
            frame,
            text=f"Version {__version__}",
            font=("DejaVu Sans", 10),
        )
        version_label.pack(pady=(0, 8))

        desc_label = ttk.Label(
            frame,
            text=(
                "A Python reverse-engineering of SMath Studio,\n"
                "the mathematical worksheet application.\n\n"
                "Supports parsing, evaluating, and rendering\n"
                "SMath Studio .sm worksheet files."
            ),
            justify=tk.CENTER,
            font=("DejaVu Sans", 9),
        )
        desc_label.pack(pady=(0, 16))

        ok_btn = ttk.Button(frame, text="OK", command=self.destroy, width=12)
        ok_btn.pack()
        ok_btn.focus_set()

        self.bind("<Return>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())


class OptionsDialog(tk.Toplevel):
    """Options dialog for calculation settings."""

    def __init__(self, parent: tk.Widget, settings: dict):
        super().__init__(parent)
        self.title("Options")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[dict] = None

        self.geometry("380x300")
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # Notebook for tabs
        notebook = ttk.Notebook(frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # --- Calculation tab ---
        calc_frame = ttk.Frame(notebook, padding=12)
        notebook.add(calc_frame, text="Calculation")

        # Precision
        ttk.Label(calc_frame, text="Decimal precision:").grid(
            row=0, column=0, sticky=tk.W, pady=4
        )
        self._precision_var = tk.IntVar(value=settings.get("precision", 4))
        precision_spin = ttk.Spinbox(
            calc_frame, from_=1, to=15, textvariable=self._precision_var, width=6
        )
        precision_spin.grid(row=0, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        # Fractions mode
        ttk.Label(calc_frame, text="Result format:").grid(
            row=1, column=0, sticky=tk.W, pady=4
        )
        self._fractions_var = tk.StringVar(
            value=settings.get("fractions", "decimal")
        )
        fractions_combo = ttk.Combobox(
            calc_frame,
            textvariable=self._fractions_var,
            values=["decimal", "fraction"],
            state="readonly",
            width=10,
        )
        fractions_combo.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        # Angle units
        ttk.Label(calc_frame, text="Angle units:").grid(
            row=2, column=0, sticky=tk.W, pady=4
        )
        self._angle_var = tk.StringVar(
            value=settings.get("angle_units", "radians")
        )
        angle_combo = ttk.Combobox(
            calc_frame,
            textvariable=self._angle_var,
            values=["radians", "degrees"],
            state="readonly",
            width=10,
        )
        angle_combo.grid(row=2, column=1, sticky=tk.W, padx=(8, 0), pady=4)

        # Trailing zeros
        self._trailing_var = tk.BooleanVar(
            value=settings.get("trailing_zeros", True)
        )
        trailing_check = ttk.Checkbutton(
            calc_frame, text="Show trailing zeros", variable=self._trailing_var
        )
        trailing_check.grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=4
        )

        # Significant digits mode
        self._sigdig_var = tk.BooleanVar(
            value=settings.get("significant_digits_mode", False)
        )
        sigdig_check = ttk.Checkbutton(
            calc_frame,
            text="Significant digits mode",
            variable=self._sigdig_var,
        )
        sigdig_check.grid(
            row=4, column=0, columnspan=2, sticky=tk.W, pady=4
        )

        # --- Buttons ---
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Cancel", command=self.destroy, width=10).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side=tk.RIGHT
        )

        self.bind("<Escape>", lambda e: self.destroy())

    def _on_ok(self):
        self.result = {
            "precision": self._precision_var.get(),
            "fractions": self._fractions_var.get(),
            "angle_units": self._angle_var.get(),
            "trailing_zeros": self._trailing_var.get(),
            "significant_digits_mode": self._sigdig_var.get(),
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
        self.result: Optional[str] = None

        self.geometry("420x480")
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Search bar
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 6))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)
        search_entry = ttk.Entry(search_frame, textvariable=self._search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.focus_set()

        # Function list
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self._listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 10),
            selectmode=tk.SINGLE,
        )
        scrollbar.config(command=self._listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._listbox.bind("<Double-1>", lambda e: self._on_ok())

        # Description area
        self._desc_label = ttk.Label(
            frame, text="", wraplength=380, justify=tk.LEFT
        )
        self._desc_label.pack(fill=tk.X, pady=(0, 8))

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy, width=10).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(btn_frame, text="Insert", command=self._on_ok, width=10).pack(
            side=tk.RIGHT
        )

        # Build function list with descriptions
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
        self.geometry("420x180")

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - 210}+{ph - 90}")

        self._on_find = on_find
        self._on_replace = on_replace
        self._on_replace_all = on_replace_all

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Find:").grid(row=0, column=0, sticky="w", pady=4)
        self.find_var = tk.StringVar()
        self.find_entry = ttk.Entry(frame, textvariable=self.find_var, width=30)
        self.find_entry.grid(row=0, column=1, padx=(8, 0), pady=4, sticky="ew")

        ttk.Label(frame, text="Replace:").grid(row=1, column=0, sticky="w", pady=4)
        self.replace_var = tk.StringVar()
        self.replace_entry = ttk.Entry(frame, textvariable=self.replace_var, width=30)
        self.replace_entry.grid(row=1, column=1, padx=(8, 0), pady=4, sticky="ew")

        self.case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Match case", variable=self.case_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=4
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=0, column=2, rowspan=3, padx=(12, 0), sticky="n")

        ttk.Button(btn_frame, text="Find Next", command=self._do_find, width=12).pack(pady=2)
        ttk.Button(btn_frame, text="Replace", command=self._do_replace, width=12).pack(pady=2)
        ttk.Button(btn_frame, text="Replace All", command=self._do_replace_all, width=12).pack(pady=2)
        ttk.Button(btn_frame, text="Close", command=self.destroy, width=12).pack(pady=2)

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
