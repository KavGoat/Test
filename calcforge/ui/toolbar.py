"""Toolbars matching SMath Studio's layout."""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QToolBar, QComboBox, QLabel


class MathToolbar(QToolBar):
    """Math input toolbar — insert operators and regions, like SMath Studio."""

    insert_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Math", parent)
        self.setMovable(False)

        items = [
            ("Math Region", "calculation", "Insert math region"),
            ("Text Region", "text", "Insert text region"),
            ("Plot", "plot", "Insert 2D plot"),
            None,
            (":=", "op_assign", "Assignment operator"),
            ("=", "op_eval", "Evaluation operator"),
            ("→", "op_convert", "Unit conversion"),
            None,
            ("+", "op_plus", "Addition"),
            ("−", "op_minus", "Subtraction"),
            ("×", "op_mul", "Multiplication"),
            ("/", "op_div", "Division"),
            ("xⁿ", "op_pow", "Power"),
            ("√", "op_sqrt", "Square root"),
            None,
            ("α", "greek_alpha", "Greek letter alpha"),
            ("β", "greek_beta", "Greek letter beta"),
            ("γ", "greek_gamma", "Greek letter gamma"),
            ("δ", "greek_delta", "Greek letter delta"),
            ("π", "greek_pi", "Pi"),
            ("σ", "greek_sigma", "Greek letter sigma"),
        ]

        for item in items:
            if item is None:
                self.addSeparator()
                continue
            label, item_id, tooltip = item
            action = QAction(label, self)
            action.setToolTip(tooltip)
            action.setData(item_id)
            action.triggered.connect(
                lambda checked, t=item_id: self.insert_requested.emit(t))
            self.addAction(action)


class ViewToolbar(QToolBar):
    """Zoom controls toolbar."""

    zoom_fit_page = Signal()
    zoom_fit_width = Signal()
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("View", parent)
        self.setMovable(False)

        fit_page = QAction("Fit Page", self)
        fit_page.setShortcut(QKeySequence("Ctrl+0"))
        fit_page.setToolTip("Fit page in view [Ctrl+0]")
        fit_page.triggered.connect(self.zoom_fit_page.emit)
        self.addAction(fit_page)

        fit_width = QAction("Fit Width", self)
        fit_width.setShortcut(QKeySequence("Ctrl+1"))
        fit_width.setToolTip("Fit page width [Ctrl+1]")
        fit_width.triggered.connect(self.zoom_fit_width.emit)
        self.addAction(fit_width)

        self.addSeparator()
        self._zoom_combo = QComboBox()
        self._zoom_combo.setEditable(True)
        self._zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%"])
        self._zoom_combo.setCurrentText("100%")
        self._zoom_combo.currentTextChanged.connect(self._on_zoom_text)
        self.addWidget(QLabel(" Zoom: "))
        self.addWidget(self._zoom_combo)

    def _on_zoom_text(self, text: str):
        try:
            val = float(text.replace("%", "")) / 100.0
            if 0.1 <= val <= 10.0:
                self.zoom_changed.emit(val)
        except ValueError:
            pass
