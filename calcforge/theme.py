"""Application palette and stylesheets.

The chrome is flat and quiet on purpose: a markup tool is looked at all day,
and the only colours that should catch the eye are the ones on the drawing.
The page itself is always paper-white — a sheet does not change colour because
the frame around it did — so the dark theme restyles the frame only, and the
desk behind the paper stays a neutral grey in both.
"""
from __future__ import annotations

LIGHT = "light"
DARK = "dark"

# ---------------------------------------------------------------------------
# light
# ---------------------------------------------------------------------------

_LIGHT_TOKENS = {
    "chrome": "#f4f6f8",          # toolbars, menu bar, dock titles
    "chrome_edge": "#dce1e7",     # the hairline between bands
    "surface": "#eef1f4",         # window behind the panels
    "field": "#ffffff",           # anything you can type into
    "field_edge": "#c8cfd8",
    "row_alt": "#f7f9fb",
    "ink": "#1f2530",
    "ink_soft": "#5a6472",
    "ink_faint": "#8a93a2",
    "accent": "#0b6bcb",          # the one colour the chrome is allowed
    "accent_soft": "#e4eefb",
    "accent_edge": "#a9c9ee",
    "accent_deep": "#cbe0f8",
    "danger": "#b3261e",
    "scroll": "#c6cdd7",
    "scroll_hover": "#a7b1be",
    "menu": "#ffffff",
}

_DARK_TOKENS = {
    "chrome": "#2a2e36",
    "chrome_edge": "#191c21",
    "surface": "#22252b",
    "field": "#1b1e24",
    "field_edge": "#3a404b",
    "row_alt": "#242830",
    "ink": "#e2e7ee",
    "ink_soft": "#aab3c0",
    "ink_faint": "#7e8797",
    "accent": "#4d9be6",
    "accent_soft": "#2b394d",
    "accent_edge": "#3f5f8a",
    "accent_deep": "#334a68",
    "danger": "#e5726a",
    "scroll": "#434a56",
    "scroll_hover": "#59616f",
    "menu": "#2a2e36",
}

TEMPLATE = """
* {{ font-size: 12px; }}
QWidget {{ color: {ink}; }}
QMainWindow, QDialog {{ background: {surface}; }}

/* --- toolbars: flat bands, an underline on the active tool --------------- */
QToolBar {{
    background: {chrome}; border: 0; border-bottom: 1px solid {chrome_edge};
    spacing: 1px; padding: 3px 6px;
}}
QToolBar QToolButton {{
    border: 0; border-bottom: 2px solid transparent;
    border-radius: 3px; padding: 4px 5px; margin: 0 1px;
}}
QToolBar QToolButton:hover {{ background: {accent_soft}; }}
QToolBar QToolButton:pressed {{ background: {accent_deep}; }}
QToolBar QToolButton:checked {{
    background: {accent_soft}; border-bottom: 2px solid {accent};
}}
QToolBar QToolButton::menu-indicator {{ width: 0; }}
QToolBar QLabel {{ color: {ink_soft}; padding: 0 3px 0 6px; }}
QToolBar::separator {{ background: {chrome_edge}; width: 1px; margin: 5px 6px; }}
QToolBar::handle {{ width: 0; height: 0; }}

/* --- menus --------------------------------------------------------------- */
QMenuBar {{ background: {chrome}; border-bottom: 1px solid {chrome_edge}; }}
QMenuBar::item {{ padding: 5px 11px; background: transparent; }}
QMenuBar::item:selected {{ background: {accent_soft}; }}
QMenu {{ background: {menu}; border: 1px solid {field_edge}; padding: 5px; }}
QMenu::item {{ padding: 6px 26px 6px 24px; border-radius: 3px; }}
QMenu::item:selected {{ background: {accent_soft}; }}
QMenu::item:disabled {{ color: {ink_faint}; }}
QMenu::separator {{ height: 1px; background: {chrome_edge}; margin: 5px 8px; }}

/* --- docks: a quiet uppercase title, like every drawing tool ------------- */
QDockWidget {{ color: {ink_soft}; }}
QDockWidget::title {{
    background: {chrome}; padding: 6px 9px; border-bottom: 1px solid {chrome_edge};
    font-weight: 600;
}}
QDockWidget > QWidget {{ background: {surface}; }}

QGroupBox {{
    border: 1px solid {chrome_edge}; border-radius: 4px; margin-top: 10px;
    background: {field}; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 9px; padding: 0 4px; color: {ink_soft};
}}

/* --- fields -------------------------------------------------------------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
QAbstractItemView {{
    background: {field}; border: 1px solid {field_edge}; border-radius: 3px;
    padding: 3px 5px; selection-background-color: {accent};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {ink_faint}; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}

QPushButton {{
    background: {chrome}; border: 1px solid {field_edge}; border-radius: 3px;
    padding: 5px 14px;
}}
QPushButton:hover {{ background: {accent_soft}; border-color: {accent_edge}; }}
QPushButton:pressed {{ background: {accent_deep}; }}
QPushButton:default {{ border-color: {accent}; }}

/* --- lists and tables ---------------------------------------------------- */
QTreeWidget, QTableWidget, QListWidget, QTreeView, QTableView {{
    background: {field}; border: 1px solid {chrome_edge}; border-radius: 3px;
    alternate-background-color: {row_alt}; gridline-color: {chrome_edge};
    outline: 0;
}}
QTreeWidget::item, QTableWidget::item, QListWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:selected, QTableWidget::item:selected,
QListWidget::item:selected {{ background: {accent_soft}; color: {ink}; }}
QHeaderView::section {{
    background: {chrome}; border: 0; border-right: 1px solid {chrome_edge};
    border-bottom: 1px solid {chrome_edge}; padding: 5px 7px;
    font-weight: 600; color: {ink_soft};
}}

/* --- tabs: an underline, not a folder tab -------------------------------- */
QTabWidget::pane {{ border: 0; border-top: 1px solid {chrome_edge}; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; border: 0; border-bottom: 2px solid transparent;
    padding: 6px 14px; color: {ink_soft};
}}
QTabBar::tab:hover {{ color: {ink}; }}
QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}

/* --- status bar ---------------------------------------------------------- */
QStatusBar {{ background: {chrome}; border-top: 1px solid {chrome_edge}; }}
QStatusBar::item {{ border: 0; }}
QStatusBar QLabel {{ color: {ink_soft}; padding: 0 4px; }}

/* --- scrollbars ---------------------------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {scroll}; border-radius: 5px; min-height: 28px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {scroll_hover}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {scroll}; border-radius: 5px; min-width: 28px; margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {scroll_hover}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: {chrome_edge}; }}
QCheckBox, QRadioButton {{ spacing: 7px; }}
QToolTip {{
    background: {ink}; color: {field}; border: 0; padding: 6px 8px;
    border-radius: 3px;
}}
QGraphicsView {{ border: 0; }}
"""

STYLESHEET = TEMPLATE.format(**_LIGHT_TOKENS)
DARK_STYLESHEET = TEMPLATE.format(**_DARK_TOKENS)

# The desk the paper lies on, per theme.  Dark enough that a white sheet has an
# unmistakable edge, neutral enough that it never competes with a markup.
CANVAS = {LIGHT: "#6e747d", DARK: "#141619"}


def stylesheet(theme: str) -> str:
    return DARK_STYLESHEET if theme == DARK else STYLESHEET


def tokens(theme: str) -> dict:
    """The colour tokens the chrome is built from, for code that needs one."""
    return dict(_DARK_TOKENS if theme == DARK else _LIGHT_TOKENS)
