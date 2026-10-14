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
    # Bluebeam Revu 21's light look: grey chrome, white fields, Revu's blue
    "chrome": "#f0f0f0",          # toolbars, menu bar, dock titles
    "chrome_edge": "#d4d5d6",     # the hairline between bands
    "surface": "#f0f0f0",         # window behind the panels
    "field": "#ffffff",           # anything you can type into
    "field_edge": "#a9abad",
    "row_alt": "#f7f7f7",
    "ink": "#1e2022",
    "ink_soft": "#45484b",
    "ink_faint": "#8a8c8e",
    "accent": "#1e77bf",          # Revu's blue
    "accent_soft": "#dbe9f6",
    "accent_edge": "#9cc3e6",
    "accent_deep": "#c2dbf1",
    "danger": "#b3261e",
    "scroll": "#c6c8ca",
    "scroll_hover": "#a9abad",
    "menu": "#ffffff",
    "menubar": "#f0f0f0",
}

_DARK_TOKENS = {
    # Bluebeam Revu 21's dark look, from its manual's screenshots: one
    # charcoal (#1e2022) for bars, panels and fields, fields outlined in
    # grey, menus a shade lighter with a blue-grey hover, Revu's blue
    "chrome": "#1e2022",
    "chrome_edge": "#3c3e40",
    "surface": "#1e2022",
    "field": "#1e2022",
    "field_edge": "#5a5c5e",
    "row_alt": "#232527",
    "ink": "#ffffff",
    "ink_soft": "#c9cacb",
    "ink_faint": "#8a8c8e",
    "accent": "#1e77bf",
    "accent_soft": "#244053",
    "accent_edge": "#1e77bf",
    "accent_deep": "#0f527e",
    "danger": "#e5726a",
    "scroll": "#3c3e40",
    "scroll_hover": "#5a5c5e",
    "menu": "#2d2f31",
    "menubar": "#000000",
}

TEMPLATE = """
* {{ font-size: 12px; }}
QWidget {{ color: {ink}; }}
QMainWindow, QDialog {{ background: {surface}; }}

/* --- toolbars: flat bands, an underline on the active tool --------------- */
QToolBar {{
    background: {chrome}; border: 0; border-bottom: 1px solid {chrome_edge};
    spacing: 1px; padding: 3px 4px 3px 2px;
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
/* Markup | Calc: one pill, the mode on filled with the accent */
QWidget#modeSwitch QToolButton {{
    border: 1px solid {chrome_edge}; border-radius: 0; margin: 0;
    padding: 4px 12px; font-weight: 600; background: {surface};
}}
QWidget#modeSwitch QToolButton#modeMarkup {{
    border-top-left-radius: 11px; border-bottom-left-radius: 11px; border-right: 0;
}}
QWidget#modeSwitch QToolButton#modeCalc {{
    border-top-right-radius: 11px; border-bottom-right-radius: 11px;
}}
QWidget#modeSwitch QToolButton:checked {{
    background: {accent}; color: white; border-color: {accent};
}}
QWidget#modeSwitch QToolButton:hover:!checked {{ background: {accent_soft}; }}
QToolBar QLabel {{ color: {ink_soft}; padding: 0 3px 0 6px; }}
QToolBar QLabel#styleKind {{
    color: {ink}; font-weight: 600; padding: 0 10px 0 6px;
    border-right: 1px solid {chrome_edge}; margin-right: 4px;
}}
QToolBar::separator {{ background: {chrome_edge}; width: 1px; margin: 5px 6px; }}
/* The grip is left to the style to draw — a rule here would replace the dots
   with nothing, which is how the toolbars ended up with no way to pick them up.
   The padding above leaves it room. */

/* --- menus --------------------------------------------------------------- */
QMenuBar {{ background: {menubar}; border-bottom: 1px solid {chrome_edge}; }}
QMenuBar::item {{ padding: 5px 11px; background: transparent; }}
QMenuBar::item:selected {{ background: {accent_soft}; }}
QMenu {{ background: {menu}; border: 1px solid {field_edge}; padding: 5px; }}
QListWidget#completionList {{
    background: {menu}; border: 1px solid {accent}; border-radius: 3px;
    padding: 2px; outline: none;
}}
QListWidget#completionList::item {{ padding: 2px 8px; border-radius: 2px; }}
QListWidget#completionList::item:selected {{ background: {accent}; color: white; }}
QMenu::item {{ padding: 6px 26px 6px 24px; border-radius: 3px; }}
QMenu::item:selected {{ background: {accent_soft}; }}
QMenu::item:disabled {{ color: {ink_faint}; }}
QMenu::separator {{ height: 1px; background: {chrome_edge}; margin: 5px 8px; }}

/* --- docks: our own title bar, so it can carry a pin --------------------- */
QDockWidget {{ color: {ink_soft}; }}
QDockWidget > QWidget {{ background: {surface}; }}
#dockTitleBar {{
    background: {chrome}; border-bottom: 1px solid {chrome_edge};
}}
#dockTitle {{
    color: {ink_soft}; font-weight: 600; letter-spacing: 0.3px;
}}
#dockButton {{
    border: 0; border-radius: 3px; padding: 2px; margin: 0;
}}
#dockButton:hover {{ background: {accent_soft}; }}
#dockButton:checked {{ background: {accent_deep}; }}

/* The rails of panel icons down either edge of the canvas. */
#panelRail {{
    background: {chrome}; border-right: 1px solid {chrome_edge};
    border-left: 1px solid {chrome_edge};
}}
#railButton {{
    border: 0; border-radius: 4px; padding: 3px; margin: 0;
}}
#railButton:hover {{ background: {accent_soft}; }}
#railButton:checked {{ background: {accent_deep}; }}

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
QComboBox::down-arrow {{ image: url("{arrow_down}"); width: 9px; height: 9px; }}

/* A styled spin box loses the platform's arrows, so they are drawn here. */
QSpinBox, QDoubleSpinBox {{ padding-right: 18px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 16px; border: 0; border-left: 1px solid {field_edge};
    border-top-right-radius: 3px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 16px; border: 0; border-left: 1px solid {field_edge};
    border-bottom-right-radius: 3px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {accent_soft};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{arrow_up}"); width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{arrow_down}"); width: 9px; height: 9px;
}}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
    image: none;
}}

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
QTabBar::tab:selected {{ color: {ink}; border-bottom: 2px solid {accent}; }}
QTabBar::close-button {{
    image: url({arrow_close}); subcontrol-position: right; border-radius: 2px;
    margin: 2px;
}}
QTabBar::close-button:hover {{ background: {accent_soft}; }}

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
/* a box you can see in either theme, filled with the accent when ticked */
/* (and the same box in lists and trees: Manage Tool Sets, Layers) */
QCheckBox::indicator, QAbstractItemView::indicator {{
    width: 13px; height: 13px; border-radius: 3px;
    border: 1px solid {ink_soft}; background: {field};
}}
QCheckBox::indicator:hover, QAbstractItemView::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{
    background: {accent}; border-color: {accent}; image: url("{arrow_tick}");
}}
QCheckBox::indicator:disabled {{ border-color: {chrome_edge}; background: {surface}; }}
QToolTip {{
    background: {ink}; color: {field}; border: 0; padding: 6px 8px;
    border-radius: 3px;
}}
QGraphicsView {{ border: 0; }}

/* --- the odds and ends ---------------------------------------------------- */
QComboBox QAbstractItemView {{
    border: 1px solid {field_edge}; selection-background-color: {accent};
}}
QProgressBar {{
    border: 1px solid {chrome_edge}; border-radius: 3px; text-align: center;
    background: {field};
}}
QProgressBar::chunk {{ background: {accent}; }}
QSlider::groove:horizontal {{
    height: 4px; background: {field_edge}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {accent_edge}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {accent}; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QMenu::icon {{ padding-left: 6px; }}

/* --- Bluebeam's Properties panel: sections with a chevron, no box ------- */
QGroupBox#propSection {{
    border: 0; background: transparent; margin-top: 24px; font-weight: 600;
}}
QGroupBox#propSection::title {{
    subcontrol-origin: margin; subcontrol-position: top left; left: 2px;
    padding: 3px 4px; color: {ink}; font-size: 13px;
}}
QGroupBox#propSection::indicator {{ width: 12px; height: 12px; }}
QGroupBox#propSection::indicator:checked {{ image: url({arrow_chev_down}); }}
QGroupBox#propSection::indicator:unchecked {{ image: url({arrow_chev_right}); }}
QLabel#propHeading {{ font-size: 14px; padding: 2px 2px 4px 2px; }}

/* --- Bluebeam's Tool Chest: set bars, tools on a light ground ----------- */
QListWidget#toolGrid {{ background: #e4e5e6; border: 0; border-radius: 0; }}
QListWidget#toolGrid::item {{ border-radius: 2px; }}
QListWidget#toolGrid::item:hover {{ background: #cfd6de; }}
QListWidget#toolGrid::item:selected {{ background: #b9cde3; }}
QLabel#toolSetName {{ color: {ink}; font-weight: 600; }}
QTreeWidget#toolChestTree::item {{ padding: 0; }}
QLabel:disabled {{ color: {ink_faint}; }}
"""

def _arrow_files(ink: str, name: str) -> dict:
    """Small up and down arrow images for the stylesheet, in *ink*.

    A stylesheet can only take an arrow as an image file, so the two are
    written once to a private folder and referred to by path.
    """
    import os
    import tempfile

    folder = os.path.join(tempfile.gettempdir(), "calcforge-theme")
    shapes = {"up": "1,7 5,2 9,7", "down": "1,3 5,8 9,3"}
    paths = {}
    drawings = {way: ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                      f'viewBox="0 0 10 10"><polygon points="{points}" '
                      f'fill="{ink}"/></svg>') for way, points in shapes.items()}
    # Bluebeam's section chevrons (the Properties panel): open, folded
    for way, points in (("chev_down", "2,4.5 6,8.5 10,4.5"), ("chev_right", "4.5,2 8.5,6 4.5,10")):
        drawings[way] = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
                         f'viewBox="0 0 12 12"><polyline points="{points}" fill="none" '
                         f'stroke="{ink}" stroke-width="1.4" stroke-linecap="round" '
                         'stroke-linejoin="round"/></svg>')
    # a tab's close cross, Bluebeam's plain ×
    drawings["close"] = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
                         f'viewBox="0 0 12 12"><path d="M3 3 L9 9 M9 3 L3 9" fill="none" '
                         f'stroke="{ink}" stroke-width="1.3" stroke-linecap="round"/></svg>')
    # a ticked box's tick, white on the accent
    drawings["tick"] = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
                        'viewBox="0 0 12 12"><polyline points="2.5,6.5 5,9 9.5,3" '
                        'fill="none" stroke="#ffffff" stroke-width="1.9" '
                        'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    for way, svg in drawings.items():
        path = os.path.join(folder, f"{name}-{way}.svg")
        try:
            os.makedirs(folder, exist_ok=True)
            current = ""
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    current = handle.read()
            if current != svg:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(svg)
        except OSError:
            pass
        paths[f"arrow_{way}"] = path.replace("\\", "/")
    return paths


STYLESHEET = TEMPLATE.format(**_LIGHT_TOKENS,
                             **_arrow_files(_LIGHT_TOKENS["ink_soft"], "light"))
DARK_STYLESHEET = TEMPLATE.format(**_DARK_TOKENS,
                                  **_arrow_files(_DARK_TOKENS["ink_soft"], "dark"))

# The desk the paper lies on, per theme.  Dark enough that a white sheet has an
# unmistakable edge, neutral enough that it never competes with a markup.
CANVAS = {LIGHT: "#6e747d", DARK: "#141619"}


def stylesheet(theme: str) -> str:
    return DARK_STYLESHEET if theme == DARK else STYLESHEET


def palette(theme: str):
    """The Qt palette to go with the stylesheet.

    A stylesheet only reaches the widgets it has rules for. Everything else —
    a scroll area's viewport, a tooltip Qt draws itself, the text cursor —
    falls back to the palette, and a light palette under a dark stylesheet is
    how a dark theme ends up with white rectangles in it.
    """
    from PySide6.QtGui import QColor, QPalette

    values = tokens(theme)
    ink = QColor(values["ink"])
    field = QColor(values["field"])
    surface = QColor(values["surface"])
    accent = QColor(values["accent"])
    faint = QColor(values["ink_faint"])

    result = QPalette()
    result.setColor(QPalette.Window, surface)
    result.setColor(QPalette.WindowText, ink)
    result.setColor(QPalette.Base, field)
    result.setColor(QPalette.AlternateBase, QColor(values["row_alt"]))
    result.setColor(QPalette.Text, ink)
    result.setColor(QPalette.Button, QColor(values["chrome"]))
    result.setColor(QPalette.ButtonText, ink)
    result.setColor(QPalette.BrightText, QColor(values["danger"]))
    result.setColor(QPalette.Highlight, accent)
    result.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    result.setColor(QPalette.ToolTipBase, ink)
    result.setColor(QPalette.ToolTipText, field)
    result.setColor(QPalette.PlaceholderText, faint)
    result.setColor(QPalette.Link, accent)
    for group in (QPalette.Disabled,):
        result.setColor(group, QPalette.Text, faint)
        result.setColor(group, QPalette.WindowText, faint)
        result.setColor(group, QPalette.ButtonText, faint)
    return result


def tokens(theme: str) -> dict:
    """The colour tokens the chrome is built from, for code that needs one."""
    return dict(_DARK_TOKENS if theme == DARK else _LIGHT_TOKENS)
