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
    "raised": "#e6e6e6",
    "tab_on": "#ffffff",
    "picked": "#cce4f7",
    "picked_ink": "#1e2022",
}

_DARK_TOKENS = {
    # Bluebeam Revu's dark look as the user's own Revu shows it (their
    # screenshots, 2026-10-15): charcoal bars and panels (#2e2e2e), menus,
    # list headers and rulers a step lighter (#3e3e3e), the open document's
    # tab lighter again (#4e4e4e), dark rules between bands, fields outlined
    # in grey, a picked tool or row filled with Revu's deep blue (#175884)
    # and its bright blue (#0083db) for focus and lines
    "chrome": "#2e2e2e",
    "chrome_edge": "#1c1c1c",
    "surface": "#2e2e2e",
    "field": "#2e2e2e",
    "field_edge": "#565656",
    "row_alt": "#333333",
    "raised": "#3e3e3e",
    "tab_on": "#4e4e4e",
    "ink": "#ffffff",
    "ink_soft": "#d9d9d9",
    "ink_faint": "#8a8a8a",
    "accent": "#0083db",
    "accent_soft": "#454545",
    "accent_edge": "#0083db",
    "accent_deep": "#175884",
    "picked": "#175884",
    "picked_ink": "#ffffff",
    "danger": "#e5726a",
    "scroll": "#858585",
    "scroll_hover": "#a6a6a6",
    "menu": "#3e3e3e",
    "menubar": "#2e2e2e",
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
QToolBar QToolButton:checked {{ background: {picked}; color: {picked_ink}; }}
QToolBar QToolButton::menu-indicator {{ width: 0; }}
/* Markup | Calc: two plain buttons as Revu's own toggles (the status bar's
   page modes): flat, square, the one on filled with Revu's deep blue */
QWidget#modeSwitch QToolButton {{
    border: 1px solid {field_edge}; border-radius: 0; margin: 0;
    padding: 3px 12px; background: transparent; color: {ink_soft};
}}
QWidget#modeSwitch QToolButton#modeMarkup {{ border-right: 0; }}
QWidget#modeSwitch QToolButton:checked {{
    background: {picked}; color: {picked_ink}; border-color: {field_edge};
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
QMenu::item:selected {{ background: {picked}; color: {picked_ink}; }}
QMenu::item:disabled {{ color: {ink_faint}; }}
QMenu::separator {{ height: 1px; background: {chrome_edge}; margin: 5px 8px; }}

/* --- docks: our own title bar, so it can carry a pin --------------------- */
QDockWidget {{ color: {ink_soft}; }}
QDockWidget > QWidget {{ background: {surface}; }}
#dockTitleBar {{
    background: {chrome}; border-bottom: 1px solid {chrome_edge};
}}
#dockTitle {{
    color: {ink}; font-weight: 600; font-size: 14px;
}}
#dockButton {{
    border: 0; border-radius: 3px; padding: 2px; margin: 0;
}}
#dockButton:hover {{ background: {accent_soft}; }}
#dockButton:checked {{ background: {picked}; }}

/* The rails of panel icons down either edge of the canvas. */
#panelRail {{
    background: {chrome}; border-right: 1px solid {chrome_edge};
    border-left: 1px solid {chrome_edge};
}}
#railButton {{
    border: 0; border-radius: 4px; padding: 3px; margin: 0;
}}
#railButton:hover {{ background: {accent_soft}; }}
#railButton:checked {{ background: {picked}; }}

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
QComboBox::down-arrow {{ image: url("{arrow_vee}"); width: 10px; height: 10px; }}

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
/* on Revu's Properties toolbar and Properties panel the arrows sit before
   the number */
QToolBar QSpinBox, QToolBar QDoubleSpinBox,
#propertiesPanel QSpinBox, #propertiesPanel QDoubleSpinBox {{
    padding-right: 5px; padding-left: 3px;
}}
QToolBar QSpinBox::up-button, QToolBar QDoubleSpinBox::up-button,
#propertiesPanel QSpinBox::up-button, #propertiesPanel QDoubleSpinBox::up-button {{
    subcontrol-position: top left; border-left: 0; border-right: 1px solid {field_edge};
    border-top-right-radius: 0; border-top-left-radius: 3px;
}}
QToolBar QSpinBox::down-button, QToolBar QDoubleSpinBox::down-button,
#propertiesPanel QSpinBox::down-button, #propertiesPanel QDoubleSpinBox::down-button {{
    subcontrol-position: bottom left; border-left: 0; border-right: 1px solid {field_edge};
    border-bottom-right-radius: 0; border-bottom-left-radius: 3px;
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
QListWidget::item:selected {{ background: {picked}; color: {picked_ink}; }}
QHeaderView::section {{
    background: {raised}; border: 0; border-right: 1px solid {field_edge};
    border-bottom: 1px solid {chrome_edge}; padding: 5px 7px;
    font-weight: 600; color: {ink};
}}

/* --- tabs: Revu's — flat, the open one a lighter block ------------------- */
QTabWidget::pane {{ border: 0; border-top: 1px solid {chrome_edge}; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: {chrome}; border: 0; border-right: 1px solid {chrome_edge};
    padding: 7px 14px; color: {ink_soft};
}}
QTabBar::tab:hover {{ color: {ink}; background: {accent_soft}; }}
QTabBar::tab:selected {{ color: {ink}; background: {tab_on}; }}
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
/* the canvas's scroll bar sharing its row with the sheet tabs (Excel's) */
QScrollBar#sheetRowScroll:horizontal {{ height: 24px; }}
QScrollBar#sheetRowScroll::handle:horizontal {{ margin: 6px 2px; }}
#sheetTabs QTabBar::tab {{ padding: 3px 10px; }}
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
/* and a round one for a choice of one: unticked radios were near invisible
   in dark mode (Set Scale's Preset | Custom; QA, 2026-10-15) */
QRadioButton::indicator {{
    width: 13px; height: 13px; border-radius: 7px;
    border: 1px solid {ink_soft}; background: {field};
}}
QRadioButton::indicator:hover {{ border-color: {accent}; }}
QRadioButton::indicator:checked {{
    border-color: {accent};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {accent}, stop:0.5 {accent}, stop:0.56 {field}, stop:1 {field});
}}
QRadioButton::indicator:disabled {{ border-color: {chrome_edge}; background: {surface}; }}
QToolTip {{
    background: {ink}; color: {field}; border: 0; padding: 6px 8px;
    border-radius: 3px;
}}
QGraphicsView {{ border: 0; }}

/* --- the odds and ends ---------------------------------------------------- */
QComboBox QAbstractItemView {{
    border: 1px solid {field_edge}; selection-background-color: {picked};
    selection-color: {picked_ink};
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
    # a drop-down's arrow: Revu's thin chevron, not a filled triangle
    drawings["vee"] = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                       f'viewBox="0 0 10 10"><polyline points="1.5,3.5 5,7 8.5,3.5" '
                       f'fill="none" stroke="{ink}" stroke-width="1.2" '
                       'stroke-linecap="round" stroke-linejoin="round"/></svg>')
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
# Dark: Revu's grey desk, a step lighter than its bars (the user's Revu,
# 2026-10-15), not the near-black it was.
CANVAS = {LIGHT: "#6e747d", DARK: "#424242"}


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
