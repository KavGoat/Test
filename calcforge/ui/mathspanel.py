"""The Maths panel on the side rail (decision 19).

SMath's side panel — Arithmetic, Matrices, Boolean, Functions, Plot,
Programming, Units and Constants — as one CalcForge panel, pinnable and
floatable like every other panel on the rail. The sections and their buttons
are WebSMath's own (its ui/mainwindow.py ``_side_panel``), one to one; the
look is MarkForge's: the theme's colours, sections that fold away.

Every button types into the equation being written, or starts one at the red
cross (or under the pointer), exactly as the key it stands for would.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QGridLayout, QPushButton, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

# The units SMath's Units panel offers first; "All units…" lists the rest.
COMMON_UNITS = ("m", "mm", "cm", "km", "m²", "m³", "kg", "t", "s", "min", "h",
                "N", "kN", "MN", "Pa", "kPa", "MPa", "GPa", "J", "kJ", "W", "kW",
                "°", "rad", "°C", "K", "L", "Hz")


class MathsSection(QWidget):
    """A title that folds its buttons away, and the buttons.

    The buttons flex with the panel: as many columns as fit (each button at
    least CELL wide), every column stretched equally to fill the width, so a
    wide panel has more buttons to a row and a narrow one fewer — never a gap
    down the right.
    """

    CELL = 46            # the narrowest a button gets before a column is dropped

    def __init__(self, title: str, buttons: list, cols: int = 6,
                 collapsed: bool = False, extra: QWidget = None, keypad: bool = False):
        super().__init__()
        self.title = title
        self.base_cols = cols
        self.keypad = keypad
        self.cols = cols
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(2)
        self.header = QToolButton()
        self.header.setObjectName("mathsSectionHeader")
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setAutoRaise(True)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header.toggled.connect(lambda on: self.set_collapsed(not on))
        lay.addWidget(self.header)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(2, 0, 2, 0)
        self.grid.setSpacing(1)
        self.buttons: list[QToolButton] = []
        for label, action, tip in buttons:
            button = QToolButton()
            button.setObjectName("mathsButton")
            button.setText(label)
            button.setToolTip(tip)
            button.setFocusPolicy(Qt.NoFocus)     # the equation keeps the keyboard
            button.setAutoRaise(True)
            button.setMinimumSize(QSize(28, 24))
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if action is None:
                button.setEnabled(False)
            else:
                button.clicked.connect(action)
            self.buttons.append(button)
        self.extra = extra
        if extra is not None:
            extra.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._lay_out(cols)
        lay.addWidget(self.body)
        self.header.setChecked(not collapsed)
        self.set_collapsed(collapsed)

    def _lay_out(self, cols: int) -> None:
        grid = self.grid
        for widget in self.buttons + ([self.extra] if self.extra is not None else []):
            grid.removeWidget(widget)
        for column in range(grid.columnCount()):
            grid.setColumnStretch(column, 0)
        for index, button in enumerate(self.buttons):
            grid.addWidget(button, index // cols, index % cols)
        for column in range(cols):
            grid.setColumnStretch(column, 1)
        if self.extra is not None:
            grid.addWidget(self.extra, (len(self.buttons) + cols - 1) // cols, 0, 1, cols)
        self.cols = cols

    def columns_for(self, width: int) -> int:
        fits = max(1, width // self.CELL)
        return max(1, min(fits, len(self.buttons)))

    def fit(self, width: int) -> None:
        """Lay the buttons out for *width* (the panel's, not this section's:
        a section can't shrink below the columns it already has)."""
        wanted = self.columns_for(width)
        if wanted != self.cols:
            self._lay_out(wanted)

    def set_collapsed(self, on: bool) -> None:
        self.collapsed = bool(on)
        self.body.setVisible(not on)
        self.header.setArrowType(Qt.RightArrow if on else Qt.DownArrow)
        if self.header.isChecked() == on:
            self.header.blockSignals(True)
            self.header.setChecked(not on)
            self.header.blockSignals(False)

    def button(self, label: str) -> QToolButton:
        return next(b for b in self.buttons if b.text() == label)


class MathsPanel(QScrollArea):
    """Every section, one above the other."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("mathsPanel")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.sections = self._sections()
        for section in self.sections:
            lay.addWidget(section)
        lay.addStretch(1)
        self.setWidget(inner)

    def resizeEvent(self, event) -> None:
        # The columns first, for the width there will be; then the scroll area
        # sizes what is inside it (the other way round, it has already sized
        # it to the old columns and doesn't look again).
        bar = self.verticalScrollBar()
        width = event.size().width() - 2 * self.frameWidth() \
            - (bar.sizeHint().width() if bar.isVisible() else 0) - 8
        for section in self.sections:
            section.fit(width)
        super().resizeEvent(event)
        # and once the new columns have settled, the content to the panel's
        # width (a scroll area only resizes what is in it on its own resize)
        QTimer.singleShot(0, self._fill_the_width)

    def _fill_the_width(self) -> None:
        inner = self.widget()
        if inner is None:
            return
        width = max(self.viewport().width(), inner.minimumSizeHint().width())
        if inner.width() != width:
            inner.resize(width, inner.height())

    def section(self, title: str) -> MathsSection:
        return next(s for s in self.sections if s.title == title)

    # -- what the buttons do ----------------------------------------------------
    def type(self, text: str) -> None:
        self.window.maths_type(text)

    def _sections(self) -> list:
        w = self.window
        typed = lambda s: (lambda: self.type(s))
        struct = lambda n: (lambda: w.insert_structure(n))
        return [
            MathsSection("Arithmetic", [
                ("∞", typed("∞"), "Positive infinity"), ("π", typed("π"), "Number 'Pi'"),
                ("i", typed("i"), "Imaginary unit"), ("±", typed("±"), "Plus/minus"),
                ("xₙ", typed("["), "Vector element ([)"),
                ("←", lambda: w.maths_key("BACK"), "Backspace"),
                ("7", typed("7"), "7"), ("8", typed("8"), "8"), ("9", typed("9"), "9"),
                ("+", typed("+"), "Addition (+)"), ("( )", typed("("), "Brackets"),
                ("xʸ", typed("^"), "Power (^)"),
                ("4", typed("4"), "4"), ("5", typed("5"), "5"), ("6", typed("6"), "6"),
                ("−", typed("-"), "Subtraction (-)"), ("√", typed("\\"), "Square root (\\)"),
                ("ⁿ√", struct("nthroot"), "N-th root (Ctrl+\\)"),
                ("1", typed("1"), "1"), ("2", typed("2"), "2"), ("3", typed("3"), "3"),
                ("×", typed("*"), "Multiplication (*)"), (",", typed(","), "Arguments separator"),
                ("→", typed("symbolic("), "Symbolic evaluation: symbolic(…)"),
                (".", typed("."), "Decimal symbol"), ("0", typed("0"), "0"),
                ("!", typed("!"), "Factorial (!)"),
                ("/", typed("/"), "Division (/)"), ("≔", typed(":"), "Definition (:)"),
                ("=", typed("="), "Numeric evaluation (=)"),
            ]),
            MathsSection("Matrices", [
                ("[⋮]", w.insert_matrix, "Insert matrix (Ctrl+M)"),
                ("|M|", typed("det("), "Determinant"),
                ("Mᵀ", typed("transpose("), "Matrix transpose (Ctrl+1)"),
                ("Aᵢⱼ", typed("alg("), "Algebraic addition to matrix"),
                ("Mᵢⱼ", typed("minor("), "Minor"),
                ("×", typed("†"), "Cross product (Ctrl+8)"),
                ("v⃗", typed("vectorize("), "Vectorize"), ("a..b", struct("range"), "Range"),
                ("a,b..", struct("range3"), "Range with step"),
                ("vᵢ", typed("["), "Element (Ctrl+[)"),
                ("M⁻¹", typed("invert("), "Inverse"), ("tr", typed("tr("), "Trace"),
            ]),
            MathsSection("Boolean", [
                ("=", typed("≡"), "Boolean equality (Ctrl+=)"), ("<", typed("<"), "Less than"),
                (">", typed(">"), "Greater than"),
                ("≤", typed("≤"), "Less than or equal (Ctrl+9)"),
                ("≥", typed("≥"), "Greater than or equal (Ctrl+0)"),
                ("≠", typed("≠"), "Not equal (Ctrl+3)"),
                ("¬", typed("¬"), "Not"), ("∧", typed("&"), "And (&)"), ("∨", typed("|"), "Or (|)"),
                ("⊕", typed("⊕"), "Exclusive or"),
            ], collapsed=True),
            MathsSection("Functions", [
                ("log", typed("log("), "Logarithm"), ("sign", typed("sign("), "Sign"),
                ("sin", typed("sin("), "Sine"), ("cos", typed("cos("), "Cosine"),
                ("Σ", struct("sum"), "Summation"), ("Π", struct("product"), "Product"),
                ("ln", typed("ln("), "Natural logarithm"), ("arg", typed("arg("), "Argument"),
                ("tan", typed("tan("), "Tangent"), ("cot", typed("cot("), "Cotangent"),
                ("∫", struct("int"), "Definite integral"), ("d/dx", struct("diff"), "Derivative"),
                ("exp", typed("exp("), "Exponent"), ("{", struct("sys"), "System"),
            ], extra=self._wide("All functions…", w.insert_function)),
            MathsSection("Plot", [
                ("2D", w.insert_plot, "Plot - 2D (@)"),
                ("✥", lambda: w.plot_tool("move"), "Move (drag pans the plot)"),
                ("⤢", lambda: w.plot_tool("scale"), "Scale (drag zooms the plot)"),
                ("⁘", lambda: w.plot_render(True), "Points"),
                ("∿", lambda: w.plot_render(False), "Lines"),
                ("⟳", w.calculate, "Refresh"),
            ], collapsed=True),
            MathsSection("Programming", [
                ("if", struct("if"), "If"), ("for", struct("for"), "For loop"),
                ("try", struct("try"), "Try/on error"), ("line", struct("line"), "Add line (])"),
                ("while", struct("while"), "While loop"),
                ("cont.", typed("continue"), "continue"),
                ("break", typed("break"), "break"),
            ], cols=4),
            MathsSection("Units", [
                (unit, typed("'" + unit), f"'{unit}") for unit in COMMON_UNITS
            ], collapsed=True, extra=self._wide("All units…", w.insert_unit)),
            MathsSection("Constants", [
                ("g", typed("'g.e"), "'g.e - gravitational acceleration"),
                ("c", typed("'c"), "'c - speed of light"),
                ("h", typed("'h"), "'h - Planck constant"),
                ("k", typed("'k"), "'k - Boltzmann constant"),
                ("Nᴀ", typed("'N.A"), "'N.A - Avogadro's number"),
                ("R", typed("'R.m"), "'R.m - gas constant"),
                ("ε₀", typed("'ε.0"), "'ε.0 - vacuum permittivity"),
                ("μ₀", typed("'μ.0"), "'μ.0 - magnetic constant"),
                ("e⁻", typed("'e"), "'e - elementary charge"),
                ("mₑ", typed("'m.e"), "'m.e - electron mass"),
                ("mₚ", typed("'m.p"), "'m.p - proton mass"),
                ("u", typed("'u"), "'u - atomic mass unit"),
            ], collapsed=True, extra=self._wide("Table of all constants…", w.show_constants)),
        ]

    @staticmethod
    def _wide(text: str, action) -> QPushButton:
        button = QPushButton(text)
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(action)
        return button
