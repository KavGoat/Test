
"""
To-do list - Microsoft To Do style (PySide6).
Everything (windows, tabs, groups, tasks, order, completed state, size,
window position) is stored in TodoList.txt.
F2 (AHK) starts it; F2 again (or closing the last open window) saves and
closes the whole app completely (nothing keeps running in the background).
Click selects a task, double-click edits it, Ctrl+Z undoes.
Uses a real (hidden) Windows frame so Aero Snap / Win+arrows work.

Tabs and windows:
  - Each window shows a row of tabs along the top (each with a colour and
    a name), plus a '+' to add one; every tab is always visible somewhere -
    double-click a tab to rename it, right-click for Rename / Colour /
    Delete. Tabs shrink to fit; past their minimum width the row scrolls
    (mouse wheel, or drag a tab against either end).
  - Drag any tab (open or not) along the row to reorder it, onto another
    window's tabs to move it there, or anywhere else to tear it off into
    its own new window. Dragging a window's only tab drags the window
    itself - drop it on another window's tabs to merge the two.
  - Closing a window (the X) moves its tabs into whichever other open
    window was used most recently; closing the very last window saves
    everything and exits the app completely, same as a second F2.
  - Drag a GROUP heading onto a tab (in this window or another) to move
    that whole group - its tasks, colour, folded state - into that tab.

Drag vs paste, in short:
  - Dragging a file or folder from Explorer onto a task (or a group) links
    its existing location - nothing is copied, double-click opens the
    original file/folder.
  - Dragging an Outlook email copies it into TodoAttachments as a .msg;
    dragging one or several Outlook attachments copies each of them in.
  - Pasting (Ctrl+V) a file or folder copies it into TodoAttachments (a
    linked copy); pasting Outlook emails/attachments copies them in too.
    Plain text still pastes normally into whatever you're editing.
  - Outlook items that need COM/PowerShell are fetched on a background
    thread so the list never freezes while they're retrieved.

Undo:
  - Ctrl+Z right after adding or editing a task's text reopens it for
    editing (with everything you typed, or its pre-edit text, still
    there) instead of deleting it or silently reverting it - so fixing a
    typo never means retyping the whole task from scratch. Every other
    action (delete, move, star, due date, drag, archive, etc.) undoes as
    a normal single step.
"""
import os
import sys
import ctypes
WM_SHOW_TASKS = 0x8011          # F2 while this copy is starting: come to the front
HERE = os.path.dirname(os.path.abspath(__file__))
_PH_TITLE = "My Tasks"
_mutex = None
# ------------------------------------------------------------------
# ONE COPY AT A TIME
# ------------------------------------------------------------------
def _visible_list_window():
    """The list window of another python process, only if it's showing."""
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    buf = ctypes.create_unicode_buffer(64)
    me = os.getpid()
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if (u.IsWindowVisible(hwnd) and u.GetWindowTextW(hwnd, buf, 64)
                and buf.value == _PH_TITLE):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != me:
                found.append((hwnd, pid.value))
                return False
        return True
    u.EnumWindows(each, 0)
    return found[0] if found else (None, None)
def claim_instance():
    """If another copy is open, bring it forward and exit. If one is still
    closing down (saving), wait for it to finish, then start normally."""
    global _mutex
    if os.name != "nt":
        return
    import time
    from ctypes import wintypes
    k, u = ctypes.windll.kernel32, ctypes.windll.user32
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    end = time.monotonic() + 4
    while True:
        _mutex = k.CreateMutexW(None, False, "Local\\WSP.MyTasks")
        if k.GetLastError() != 183:              # nobody else running
            return
        hwnd, pid = _visible_list_window()
        if hwnd:                                 # open (or just opening): show it
            u.AllowSetForegroundWindow(pid)
            u.PostMessageW(hwnd, WM_SHOW_TASKS, 0, 0)
            sys.exit(0)
        k.CloseHandle(_mutex)                    # still starting or closing: wait
        _mutex = None
        if time.monotonic() > end:
            _mutex = k.CreateMutexW(None, False, "Local\\WSP.MyTasks")
            return
        time.sleep(0.04)
if __name__ == "__main__":
    claim_instance()
_launch_mutex = _mutex
import shutil
import subprocess
import threading
import time
import re
import html
import uuid
import traceback
from datetime import datetime, date, timedelta
from PySide6.QtCore import (Qt, QTimer, QThread, QPoint, QRectF, QPointF, QEvent,
                            QPropertyAnimation, QAbstractAnimation,
                            QEasingCurve, Signal, QUrl, QDate, QRect, QSize)
from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QPainterPath,
                           QLinearGradient, QGuiApplication, QCursor,
                           QPalette, QFontMetrics, QTextOption, QTextCursor,
                           QKeySequence, QTextDocument, QDesktopServices,
                           QTextCharFormat, QIcon, QPixmap, QRadialGradient,
                           QBrush, QTransform)
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QTextEdit,
                               QScrollArea, QVBoxLayout, QHBoxLayout, QMenu,
                               QFrame, QSlider, QGraphicsDropShadowEffect,
                               QMessageBox, QDialog, QCalendarWidget, QPushButton,
                               QStyledItemDelegate, QStyle)
WM_TODO_CLOSE = 0x8012          # F2 while the list is in front: close
WM_AHK_TOGGLE = 0x8001          # sent by TodoLauncher.ahk on F2: show / close
START_HIDDEN = "--background" in sys.argv and "--show" not in sys.argv
_instance_mutex = None
# ------------------------------------------------------------------
# WINDOWS API (native frame so snapping works)
# ------------------------------------------------------------------
if os.name == "nt":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
    class MINMAXINFO(ctypes.Structure):
        _fields_ = [("ptReserved", wintypes.POINT), ("ptMaxSize", wintypes.POINT),
                    ("ptMaxPosition", wintypes.POINT), ("ptMinTrackSize", wintypes.POINT),
                    ("ptMaxTrackSize", wintypes.POINT)]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
    user32.MonitorFromRect.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    gdi32 = ctypes.windll.gdi32
    gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
WM_NCCALCSIZE, WM_NCHITTEST, WM_EXITSIZEMOVE = 0x0083, 0x0084, 0x0232
WM_GETMINMAXINFO = 0x0024
HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
# ------------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------------
# Portable by default (next to the script); the original fixed OneDrive path
# is kept working for this machine as long as that file already exists there.
_LEGACY_DATA_FILE = r"C:\Users\NZKP32013\OneDrive - WSP O365\Desktop\Everything\My Files\Shortcuts\TodoList.txt"
DATA_FILE = _LEGACY_DATA_FILE if os.path.exists(_LEGACY_DATA_FILE) \
    else os.path.join(HERE, "TodoList.txt")
WINDOW_TITLE = "My Tasks"          # the AHK script looks for this title
GENERAL = "General"
DEFAULT_SIZE = (400, 560)
ATTACH_DIR = os.path.join(os.path.dirname(DATA_FILE), "TodoAttachments")
ARCHIVE_FILE = os.path.join(os.path.dirname(DATA_FILE), "TodoArchive.txt")
ARCHIVE_ATT_DIR = os.path.join(ATTACH_DIR, "Archive")
ERROR_LOG_FILE = os.path.join(os.path.dirname(DATA_FILE), "TodoError.log")
MANIFEST_FILE = os.path.join(ATTACH_DIR, ".manifest.txt")
ICON_FILE = os.path.join(HERE, "TodoIcon.ico")
MAX_DESCRIPTORS = 500                       # sanity limit on a dropped/pasted batch
MAX_ATTACHMENT_BYTES = 200 * 1024 * 1024    # 200 MB per item, avoids runaway memory use
def log_error(context, exc=None):
    """.pyw has no console, so exceptions vanish - write them to TodoError.log
    instead of silently swallowing them."""
    try:
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n{context}\n")
            if exc is not None:
                f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except OSError:
        pass
SCALE_MIN, SCALE_MAX = 60, 150      # slider range in %
CORNER = 8                          # rounded corner radius of the window
FONT = "Segoe UI"
CARD = "#2e3235"
CARD_HOVER = "#383d41"
CARD_DONE = "#292c2e"
CARD_DONE_HOVER = "#323538"
CARD_SELECTED = "#34495b"
CARD_DRAG = "#3b4247"
CARD_EDIT = "#33383c"
ENTRY_BG = "#2a2e31"
ENTRY_FOCUS = "#30353a"
TEXT = "#ffffff"
TEXT_SUB = "#d6dfe1"
TEXT_DONE = "#8f979a"
PLACEHOLDER = "#a3acaf"
CIRCLE = "#d0d5d7"
CIRCLE_DONE = "#8fa4b9"
ACCENT = "#8ab4f8"
OVERDUE = "#ff6b6b"        # overdue: red
DUE_SOON = "#ffa94d"       # today / tomorrow: orange
DUE_LATER = "#aab4b8"      # later: grey
THEMES = [                 # name, top, bottom of the background gradient
    ("Teal", "#1b4f52", "#58797d"),
    ("Ocean", "#1c3a5c", "#50708f"),
    ("Purple", "#382a56", "#6d5f8c"),
    ("Forest", "#1e4629", "#5b7b62"),
    ("Rose", "#522a3a", "#8a6474"),
    ("Sunset", "#5a3122", "#8c6c58"),
    ("Slate", "#2a3138", "#5c656d"),
    ("Graphite", "#1c1d20", "#3b3d42"),
]
GROUP_COLOURS = [
    ("Red", "#ff8a80"), ("Orange", "#ffb74d"), ("Yellow", "#ffe082"),
    ("Green", "#a5d6a7"), ("Teal", "#80cbc4"), ("Blue", "#8ab4f8"),
    ("Purple", "#ce93d8"), ("Pink", "#f48fb1"),
]
# Tab colour presets: the same background colours that used to live in the
# three-dot settings menu (now removed from there - background is purely
# per-tab). Each tab's colour becomes its whole window's background via
# derive_theme() (same as these always did), so reusing THEMES' own top
# colours keeps exactly the same look, just chosen per-tab instead of
# app-wide.
TAB_COLOURS = [(name, top) for name, top, _bottom in THEMES]
ARCHIVE_CHOICES = [0, 7, 14, 30, 90]      # days; 0 = off
TINT_BASE = "#26292c"      # group colours are mixed into this for task backgrounds
TINT = [0.42]              # how strong group colours are (changed in ... settings)
# The top strip of the window (behind the tabs, where the window controls
# sit) is a flat, shared dark grey - separate from any tab's own colour -
# so it reads as neutral chrome instead of competing with whichever tab is
# open. Customisable from ... -> Bar colour, with its own quick picker.
TOPBAR_BG_DEFAULT = "#202225"
TOPBAR_BG = [TOPBAR_BG_DEFAULT]
TOPBAR_QUICK = ["#202225", "#2b2f32", "#17181a", "#1c1d20",
                "#2a2e31", "#33383c", "#121314"]
# Theme/autoarchive/scale apply to the whole app (every window, every tab),
# not to any one window - kept here so a new window (or a tab dragged into
# one) always starts in sync with whatever every other open window shows.
APP_SETTINGS = {"autoarchive": 30}
def mix(a, b, t):
    """Blend colour a towards b by t (0..1). Returns '#rrggbb'."""
    ca, cb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))
STAR_ON = "#8ab4f8"
PILL = "#2b2f32"
PILL_HOVER = "#353a3e"
ANIM_MS = 200
UNDO_LIMIT = 50
# ------------------------------------------------------------------
# SCALING - every size is worked out from these base values
# ------------------------------------------------------------------
S = 1.0
EDGE = 6        # invisible resize border around the frameless window
BASE = dict(MARGIN=12, TOP_PAD=4, MIN_H=40, GAP=3, GROUP_GAP=16, TEXT_X=40,
            RADIUS=5, HEAD_H=28, EDIT_H=26, PILL_H=26, CARD_PAD=20, SUB_H=13,
            ATT_H=22, ARROW_W=20, STAR_W=32)
MARGIN = TOP_PAD = MIN_H = GAP = GROUP_GAP = TEXT_X = RADIUS = 0
HEAD_H = EDIT_H = PILL_H = CARD_PAD = SUB_H = ATT_H = ARROW_W = STAR_W = 0
CX = CR = 0.0
def set_scale(s):
    global S, CX, CR
    S = min(max(s, SCALE_MIN / 100), SCALE_MAX / 100)
    g = globals()
    for k, v in BASE.items():
        g[k] = max(1, int(round(v * S)))
    CX = 20.0 * S
    CR = 7.5 * S
_fonts = {}
_line_h = {}
def F(pt, bold=False, strike=False):
    """Fonts are cached - rebuilding them for every task slowed loading."""
    key = (pt, bold, strike, S)
    f = _fonts.get(key)
    if f is None:
        f = QFont(FONT)
        f.setPointSizeF(pt * S)
        if bold:
            f.setWeight(QFont.Weight.DemiBold)
        f.setStrikeOut(strike)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        _fonts[key] = f
    return f
def task_line_h():
    h = _line_h.get(S)
    if h is None:
        h = _line_h[S] = QFontMetrics(F(10)).height()
    return h
DIALOG_STYLE = """
QMessageBox { background: #2b2f32; }
QLabel { color: #ffffff; font-family: 'Segoe UI'; font-size: 9pt; }
QPushButton { background: #3b4146; color: #ffffff; border: none; border-radius: 4px;
    padding: 5px 16px; min-width: 60px; font-family: 'Segoe UI'; font-size: 9pt; }
QPushButton:hover { background: #474e54; }
QPushButton:default { background: #8ab4f8; color: #1b1f22; }
"""
def _rgb(c):
    """'#rrggbb' or '#aarrggbb' -> [r, g, b]."""
    c = c.lstrip("#")
    if len(c) == 8:
        c = c[2:]
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]
def alpha_of(c):
    """Alpha 0..255 of '#aarrggbb' (255 for '#rrggbb' / None)."""
    return int(c[1:3], 16) if c and len(c) == 9 else 255
def with_alpha(hexc, a):
    """Colour as '#rrggbb' when solid, '#aarrggbb' when see-through."""
    q = QColor(hexc)
    q.setAlpha(max(0, min(255, int(round(a)))))
    return q.name() if q.alpha() == 255 else q.name(QColor.NameFormat.HexArgb)
def qcolour(hexc, alpha=None):
    """QColor from a stored colour, optionally with another alpha."""
    q = QColor(hexc)
    if alpha is not None:
        q.setAlpha(alpha)
    return q
def derive_theme(hexc):
    """One colour -> background gradient (top, bottom): the colour you picked
    at the top, a bit lighter at the bottom. Transparency is kept."""
    a = alpha_of(hexc)
    top = QColor(hexc).name()
    return with_alpha(top, a), with_alpha(mix(top, "#c8d0d2", 0.35), a)
def legacy_theme_top_colour(name):
    """Migrating an old single-theme file (format<3, one shared background
    for the whole app): picks a single representative colour from that old
    theme string, used to seed the first ('Work') tab's own colour so a
    background you'd customised carries over, rather than reverting to a
    default palette colour. Pure - never mutates anything."""
    parts = (name or "").split()
    if (len(parts) == 3 and parts[0] == "Custom" and
            all(QColor.isValidColorName(c) for c in parts[1:])):
        return parts[1]
    for n, top, _ in THEMES:
        if n == name:
            return top
    return THEMES[0][1]
def paint_checker(p, path, cell=4.0):
    """Grey checkerboard inside path - shows through see-through colours."""
    p.save()
    p.setClipPath(path)
    r = path.boundingRect()
    p.fillRect(r, QColor("#d9dcde"))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#9aa1a5"))
    y, row = r.top(), 0
    while y < r.bottom():
        x = r.left() + (cell if row % 2 else 0)
        while x < r.right():
            p.drawRect(QRectF(x, y, cell, cell))
            x += cell * 2
        y += cell
        row += 1
    p.restore()
class ColourWheel(QWidget):
    """Hue round the edge, white in the middle. Brightness darkens the lot."""
    _cache = {}
    def __init__(self, picker, size=176):
        super().__init__()
        self.picker = picker
        self.setFixedSize(size, size)
        self.setCursor(Qt.CrossCursor)
    def radius(self):
        return self.width() / 2 - 7          # room for the marker at the edge
    def base(self):
        """Full-brightness wheel, drawn once with gradients (no pixel loops)."""
        dpr = self.devicePixelRatioF()
        key = (self.width(), dpr)
        cache = ColourWheel._cache
        if key not in cache:
            pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            c, r = QPointF(self.width() / 2, self.height() / 2), self.radius()
            # hue: thin overlapping slices, counter-clockwise from 3 o'clock
            # (drawPie angles are 1/16 degree, counter-clockwise on screen)
            box = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            for i in range(720):
                p.setBrush(QColor.fromHsvF(i / 720, 1, 1))
                p.drawPie(box, i * 8 - 6, 20)
            white = QRadialGradient(c, r)
            white.setColorAt(0, QColor(255, 255, 255, 255))
            white.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(white)
            p.drawEllipse(c, r, r)
            p.end()
            cache[key] = pm                      # shared, so reopening is instant
        return cache[key]
    def paintEvent(self, _):
        import math
        pk = self.picker
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, r = QPointF(self.width() / 2, self.height() / 2), self.radius()
        p.drawPixmap(0, 0, self.base())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, int(round((1 - pk.v) * 255))))
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r + 0.5, r + 0.5)
        a = math.radians(pk.h * 360)
        m = QPointF(c.x() + math.cos(a) * pk.s * r, c.y() - math.sin(a) * pk.s * r)
        p.setPen(QPen(QColor(0, 0, 0, 120), 3.5))
        p.setBrush(QColor.fromHsvF(pk.h, pk.s, pk.v))
        p.drawEllipse(m, 6.5, 6.5)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(m, 6.5, 6.5)
    def _pick(self, pos):
        import math
        dx = pos.x() - self.width() / 2
        dy = self.height() / 2 - pos.y()
        h = (math.degrees(math.atan2(dy, dx)) % 360) / 360
        s = min(math.hypot(dx, dy) / self.radius(), 1.0)
        self.picker.set_hsv(h=h, s=s)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pick(e.position())
    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position())
    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.picker.accept()
class ColourSlider(QWidget):
    """Rounded gradient bar with a round handle. kind = 'bright' or 'clear'."""
    def __init__(self, picker, kind):
        super().__init__()
        self.picker, self.kind = picker, kind
        self.setFixedHeight(20)
        self.setCursor(Qt.PointingHandCursor)
    def value(self):
        pk = self.picker
        return pk.v if self.kind == "bright" else 1 - pk.a      # 'clear' = transparency
    def _x(self, v):
        pad = 9
        return pad + v * (self.width() - 2 * pad)
    def paintEvent(self, _):
        pk = self.picker
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(2, 4, self.width() - 4, self.height() - 8)
        path = QPainterPath()
        path.addRoundedRect(track, track.height() / 2, track.height() / 2)
        g = QLinearGradient(track.left(), 0, track.right(), 0)
        if self.kind == "bright":
            g.setColorAt(0, QColor(0, 0, 0))
            g.setColorAt(1, QColor.fromHsvF(pk.h, pk.s, 1))
        else:
            paint_checker(p, path)
            solid = QColor.fromHsvF(pk.h, pk.s, pk.v)
            clear = QColor(solid)
            clear.setAlpha(0)
            g.setColorAt(0, solid)
            g.setColorAt(1, clear)
        p.fillPath(path, g)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        x, cy = self._x(self.value()), self.height() / 2
        p.setPen(QPen(QColor(0, 0, 0, 120), 3.5))
        p.setBrush(QColor.fromHsvF(pk.h, pk.s, pk.v) if self.kind == "bright"
                   else QColor(TEXT))
        p.drawEllipse(QPointF(x, cy), 7, 7)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(QPointF(x, cy), 7, 7)
    def _set(self, v):
        v = min(max(v, 0.0), 1.0)
        if self.kind == "bright":
            self.picker.set_hsv(v=v)
        else:
            self.picker.set_alpha(1 - v)
    def _pick(self, pos):
        pad = 9
        self._set((pos.x() - pad) / max(self.width() - 2 * pad, 1))
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pick(e.position())
    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position())
    def wheelEvent(self, e):
        step = 0.02 if e.angleDelta().y() > 0 else -0.02
        self._set(self.value() + step)
class _Preset(QWidget):
    """Small round quick-pick colour under the wheel."""
    def __init__(self, picker, hexc):
        super().__init__()
        self.picker, self.hexc = picker, hexc
        self.hover = False
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(hexc)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.hover:
            p.setPen(QPen(QColor(255, 255, 255, 130), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(1.5, 1.5, 19, 19))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(self.hexc))
        p.drawEllipse(QRectF(5, 5, 12, 12))
    def enterEvent(self, _):
        self.hover = True
        self.update()
    def leaveEvent(self, _):
        self.hover = False
        self.update()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.picker.set_rgb(self.hexc)
    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.picker.accept()
class ColourPicker(QDialog):
    """Colour wheel + brightness + transparency. Changes show live.
    Enter / Use / double-click = keep, click outside = keep (if you changed
    something), Esc = cancel and put the old colour back."""
    def __init__(self, parent, initial, title, background=False, live=None, quick_colours=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        no_system_shadow(self)
        self.background = background
        self.live = live
        self.quick_colours = quick_colours
        self.cancelled = False
        self.touched = False
        start = QColor(initial) if initial and QColor.isValidColorName(initial) \
            else QColor("#8ab4f8")
        h, s, v, a = start.getHsvF()
        self.h = h if h >= 0 else 0.0            # greys have no hue
        self.s, self.v, self.a = s, v, a
        self.max_clear = 0.9 if background else 1.0   # background never fully invisible
        self.setStyleSheet(f"""
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel#dim {{ color: {TEXT_DONE}; }}
QLineEdit {{ background: #3b4146; color: {TEXT}; border: 1px solid #4a5055; border-radius: 5px;
    padding: 3px 6px; font-family: '{FONT}'; font-size: 9pt; selection-background-color: #3d6fb4; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{ background: {ACCENT}; color: #1b1f22; border: none; border-radius: 5px;
    padding: 5px 14px; font-family: '{FONT}'; font-size: 9pt; }}
QPushButton:hover {{ background: #a3c4fa; }}
""")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14 + SHADOW, 10 + SHADOW - 2, 14 + SHADOW, 12 + SHADOW + 2)
        lay.setSpacing(6)
        head = QLabel(title)
        head.setFont(QFont(FONT, 9, QFont.Weight.DemiBold))
        lay.addWidget(head)
        self.wheel = ColourWheel(self)
        lay.addWidget(self.wheel, 0, Qt.AlignHCenter)
        lay.addSpacing(2)
        self.bright = ColourSlider(self, "bright")
        self.bright_val = QLabel()
        self.clear = ColourSlider(self, "clear")
        self.clear_val = QLabel()
        for name, slider, val in (("Brightness", self.bright, self.bright_val),
                                  ("Transparency", self.clear, self.clear_val)):
            row = QHBoxLayout()
            lab = QLabel(name)
            lab.setFont(QFont(FONT, 8))
            val.setObjectName("dim")
            val.setFont(QFont(FONT, 8))
            row.addWidget(lab)
            row.addStretch()
            row.addWidget(val)
            lay.addLayout(row)
            lay.addWidget(slider)
        presets = QHBoxLayout()
        presets.setSpacing(0)
        quick = self.quick_colours if self.quick_colours is not None else (
            [top for _, top, _ in THEMES] if background else [h for _, h in GROUP_COLOURS])
        for hexc in quick:
            presets.addWidget(_Preset(self, hexc))
        presets.addStretch()
        lay.addLayout(presets)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.preview = QWidget()
        self.preview.setFixedSize(26, 26)
        self.preview.paintEvent = self._paint_preview
        bottom.addWidget(self.preview)
        self.hex = QLineEdit()
        self.hex.setFixedWidth(84)
        self.hex.setMaxLength(7)
        self.hex.setPlaceholderText("#rrggbb")
        self.hex.textEdited.connect(self._typed)
        self.hex.returnPressed.connect(self.accept)
        bottom.addWidget(self.hex)
        bottom.addStretch()
        ok = QPushButton("Use")
        ok.setCursor(Qt.PointingHandCursor)
        ok.setAutoDefault(False)
        ok.clicked.connect(self.accept)
        bottom.addWidget(ok)
        lay.addLayout(bottom)
        self.a = max(self.a, 1 - self.max_clear)
        self._refresh(typed=False, notify=False)
    # ---------- the colour ----------
    @property
    def colour(self):
        q = QColor.fromHsvF(self.h, self.s, self.v)
        return with_alpha(q.name(), self.a * 255)
    def set_hsv(self, h=None, s=None, v=None):
        if h is not None:
            self.h = h
        if s is not None:
            self.s = s
        if v is not None:
            self.v = v
        self._refresh()
    def set_alpha(self, a):
        self.a = min(max(a, 1 - self.max_clear), 1.0)
        self._refresh()
    def set_rgb(self, hexc, typed=False):
        h, s, v, _ = QColor(hexc).getHsvF()
        if h >= 0:
            self.h = h                               # greys keep the last hue
        self.s, self.v = s, v
        self._refresh(typed=typed)
    def _typed(self, text):
        t = text.strip()
        if not t.startswith("#"):
            t = "#" + t
        if len(t) == 7 and QColor.isValidColorName(t):
            self.set_rgb(t, typed=True)
    def _refresh(self, typed=False, notify=True):
        if not typed:
            self.hex.setText(QColor.fromHsvF(self.h, self.s, self.v).name())
        self.bright_val.setText(f"{round(self.v * 100)}%")
        self.clear_val.setText(f"{round((1 - self.a) * 100)}%")
        for w in (self.wheel, self.bright, self.clear, self.preview):
            w.update()
        if notify:
            self.touched = True
            if self.live:
                self.live(self.colour)
    def _paint_preview(self, _):
        p = QPainter(self.preview)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, 24, 24)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        paint_checker(p, path)
        if self.background:
            top, bottom = derive_theme(self.colour)
            g = QLinearGradient(1, 1, 25, 25)
            g.setColorAt(0, QColor(top))
            g.setColorAt(1, QColor(bottom))
            p.fillPath(path, g)
        else:
            p.fillPath(path, QColor(self.colour))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled = True
            self.reject()
            return
        super().keyPressEvent(e)
    def paintEvent(self, _):
        p = QPainter(self)
        paint_panel(p, QRectF(self.rect()).adjusted(SHADOW, SHADOW - 2, -SHADOW, -SHADOW - 2))
def place_popup(w, anchor, align="left"):
    """Put a popup right under the thing that opened it (or above it if there's
    no room), kept on screen. anchor = QRect in screen coordinates. The soft
    shadow margin is allowed for, so the visible panel lines up."""
    w.adjustSize()
    side, top_in, bot_in = SHADOW, SHADOW - 2, SHADOW + 2
    pw = w.width() - 2 * side
    ph = w.height() - top_in - bot_in
    x = anchor.right() - pw + 1 if align == "right" else anchor.left()
    y = anchor.bottom() + 5
    scr = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
    a = scr.availableGeometry()
    if y + ph > a.bottom() and anchor.top() - 5 - ph >= a.top():
        y = anchor.top() - 5 - ph                  # no room below: open above
    x = min(max(x, a.left() + 4), a.right() - pw - 4)
    y = min(max(y, a.top() + 4), a.bottom() - ph - 4)
    w.move(x - side, y - top_in)
def point_rect(pos):
    return QRect(pos, QSize(1, 1))
def pick_colour(parent, initial, title="Pick a colour", anchor=None, background=False,
                live=None, quick_colours=None):
    """Returns '#rrggbb' / '#aarrggbb' or None. Opens under `anchor` (QRect,
    screen coords). `live(colour)` is called while you drag, for a preview.
    `quick_colours` overrides the row of quick-pick swatches (e.g. the
    darker TAB_COLOURS for a tab, instead of the default GROUP_COLOURS)."""
    dlg = ColourPicker(parent, initial, title, background, live, quick_colours)
    place_popup(dlg, anchor if anchor is not None else point_rect(QCursor.pos()))
    ok = dlg.exec() == QDialog.Accepted
    if ok or (dlg.touched and not dlg.cancelled):
        return dlg.colour
    return None
def colour_icon(hexc, current=False):
    from PySide6.QtGui import QPixmap, QIcon
    pm = QPixmap(32, 32)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if current:
        p.setPen(QPen(QColor("#ffffff"), 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(0.8, 0.8, 14.4, 14.4))
    if hexc:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(hexc))
        p.drawEllipse(QRectF(3, 3, 10, 10))
    else:
        p.setPen(QPen(QColor("#8f979a"), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(3.5, 3.5, 9, 9))
        p.drawLine(QPointF(5, 11), QPointF(11, 5))
    p.end()
    return QIcon(pm)
SHADOW = 12          # soft shadow drawn around menus and popups
POP_BG = "#2b2f32"
POP_RADIUS = 8
def alert(parent, title, text):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton("OK", QMessageBox.AcceptRole)
    box.setStyleSheet(DIALOG_STYLE)
    box.exec()
def menu_style():
    return f"""
QMenu {{
    background: transparent; border: none; color: {TEXT};
    padding: {int(5 * S)}px; font-family: '{FONT}'; font-size: {9 * S:.1f}pt;
}}
QMenu::item {{
    padding: {int(6 * S)}px {int(26 * S)}px {int(6 * S)}px {int(8 * S)}px;
    margin: 1px 0; border-radius: 5px; background: transparent;
}}
QMenu::item:selected {{ background: rgba(138, 180, 248, 46); }}
QMenu::item:checked {{ background: rgba(138, 180, 248, 70); color: #ffffff; font-weight: 600; }}
QMenu::item:checked:selected {{ background: rgba(138, 180, 248, 95); }}
QMenu::indicator {{ width: 0px; height: 0px; }}
QMenu::item:disabled {{ color: #8f979a; }}
QMenu::icon {{ padding-left: {int(8 * S)}px; }}
QMenu::separator {{ height: 1px; background: rgba(255, 255, 255, 22); margin: 5px 8px; }}
QMenu::right-arrow {{ width: 8px; height: 8px; margin-right: 8px; }}
"""
def paint_shadow(p, rect, radius, size=SHADOW):
    """Soft rounded shadow around rect (drawn before the panel)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    for i in range(size, 0, -1):
        k = 1 - i / (size + 1)
        p.setBrush(QColor(0, 0, 0, int(3 + 10 * k * k)))
        r = rect.adjusted(-i, -i + 3, i, i + 3)
        p.drawRoundedRect(r, radius + i, radius + i)
    p.restore()
def paint_panel(p, rect, radius=POP_RADIUS):
    """Shadow + dark rounded panel + faint edge (menus, ... popup, date picker)."""
    paint_shadow(p, rect, radius)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 26), 1))
    p.setBrush(QColor(POP_BG))
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.restore()
def no_system_shadow(w):
    """Drop Windows' square popup shadow; we draw our own rounded one."""
    w.setWindowFlags(w.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    w.setAttribute(Qt.WA_TranslucentBackground)
class RoundMenu(QMenu):
    """Right-click menu with rounded corners and a soft rounded shadow."""
    def __init__(self, parent=None, title=""):
        super().__init__(title, parent)
        no_system_shadow(self)
        self.setContentsMargins(SHADOW, SHADOW - 2, SHADOW, SHADOW + 2)
        self.setStyleSheet(menu_style())
    def sub(self, title, icon=None):
        m = RoundMenu(self, title)
        if icon is not None:
            m.setIcon(icon)
        self.addMenu(m)
        return m
    def paintEvent(self, e):
        p = QPainter(self)
        m = self.contentsMargins()
        panel = QRectF(self.rect()).adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        paint_panel(p, panel)
        p.end()
        super().paintEvent(e)
    def open_at(self, pos):
        """Show at the mouse, lining the visible panel (not the shadow) up
        with it. (Overriding QMenu.exec itself crashes PySide6.)"""
        m = self.contentsMargins()
        return self.exec(pos - QPoint(m.left() - 2, m.top() - 2))
def menu_icon(kind, colour="#d6dfe1"):
    """Small line icons for the menus."""
    from PySide6.QtGui import QPixmap, QIcon
    pm = QPixmap(32, 32)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(colour)
    pen = QPen(c, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == "cal":
        p.drawRoundedRect(QRectF(2.5, 3.5, 11, 10), 2, 2)
        p.drawLine(QPointF(2.5, 6.5), QPointF(13.5, 6.5))
        p.drawLine(QPointF(5.5, 2), QPointF(5.5, 4.5))
        p.drawLine(QPointF(10.5, 2), QPointF(10.5, 4.5))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(QRectF(6.3, 8.3, 3.4, 3.4))
    elif kind == "cal-empty":
        p.drawRoundedRect(QRectF(2.5, 3.5, 11, 10), 2, 2)
        p.drawLine(QPointF(2.5, 6.5), QPointF(13.5, 6.5))
        p.drawLine(QPointF(5.5, 2), QPointF(5.5, 4.5))
        p.drawLine(QPointF(10.5, 2), QPointF(10.5, 4.5))
    elif kind == "x":
        p.drawLine(QPointF(4.5, 4.5), QPointF(11.5, 11.5))
        p.drawLine(QPointF(11.5, 4.5), QPointF(4.5, 11.5))
    elif kind == "plus":
        p.drawLine(QPointF(8, 3), QPointF(8, 13))
        p.drawLine(QPointF(3, 8), QPointF(13, 8))
    elif kind == "pen":
        p.drawLine(QPointF(4, 12), QPointF(11.5, 4.5))
        p.drawLine(QPointF(3.5, 12.5), QPointF(6, 12.5))
    elif kind == "bin":
        p.drawLine(QPointF(3, 4.5), QPointF(13, 4.5))
        p.drawRoundedRect(QRectF(4.5, 4.5, 7, 9), 1.5, 1.5)
        p.drawLine(QPointF(6.5, 2.5), QPointF(9.5, 2.5))
    elif kind == "box":
        p.drawRoundedRect(QRectF(2.5, 3, 11, 3.5), 1, 1)
        p.drawRoundedRect(QRectF(3.5, 6.5, 9, 7), 1.5, 1.5)
        p.drawLine(QPointF(6.5, 9), QPointF(9.5, 9))
    elif kind == "open":
        p.drawRoundedRect(QRectF(2.5, 2.5, 11, 11), 2, 2)
        p.drawLine(QPointF(7, 9), QPointF(13, 3))
        p.drawLine(QPointF(9.5, 3), QPointF(13, 3))
        p.drawLine(QPointF(13, 3), QPointF(13, 6.5))
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(2.5, 4.5)
        path.lineTo(6.5, 4.5)
        path.lineTo(8, 6)
        path.lineTo(13.5, 6)
        path.lineTo(13.5, 12.5)
        path.lineTo(2.5, 12.5)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "copy":
        p.drawRoundedRect(QRectF(5.5, 5.5, 8, 8.5), 1.5, 1.5)
        path = QPainterPath()
        path.moveTo(3.5, 10.5)
        path.lineTo(3.5, 3.5)
        path.quadTo(3.5, 2.5, 4.5, 2.5)
        path.lineTo(10, 2.5)
        p.drawPath(path)
    elif kind == "palette":
        p.drawEllipse(QRectF(2.5, 2.5, 11, 11))
        p.setPen(Qt.NoPen)
        for (x, y), col in zip(((5.5, 6), (8, 4.8), (10.5, 6), (10.5, 9)),
                               ("#ff8a80", "#ffe082", "#a5d6a7", "#8ab4f8")):
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(x, y), 1.2, 1.2)
    p.end()
    return QIcon(pm)
set_scale(1.0)
# ------------------------------------------------------------------
# STORAGE
# ------------------------------------------------------------------
def clean(text):
    """Single line (group names)."""
    return " ".join(text.replace("\t", " ").splitlines()).strip()
def clean_task(text):
    """Keeps line breaks inside a task, tidies everything else."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2029", "\n")
    lines = [ln.replace("\t", " ").rstrip() for ln in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)
def escape(text):
    return text.replace("\\", "\\\\").replace("\n", "\\n")
def unescape(text):
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append("\n" if nxt == "n" else nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)
def parse_geometry(value):
    try:
        if "," in value:
            x, y, w, h = [int(v) for v in value.split(",")]
            return x, y, w, h
        size, x, y = value.split("+")
        w, h = size.split("x")
        return int(x), int(y), int(w), int(h)
    except Exception:
        return None
def default_tab_colour(index):
    return TAB_COLOURS[index % len(TAB_COLOURS)][1]
def _empty_tab(name, colour):
    return {"name": name, "colour": colour, "collapsed": False,
            "folded": set(), "colours": {}, "groups": [[GENERAL, []]], "done": []}
WORK_TAB_NAME = "Work"
def _default_app_state():
    """One window, one 'Work' tab, empty General group - a brand-new install,
    or what we fall back to if the file can't be read/parsed at all."""
    tid = 0
    return {"scale": 1.0, "theme": "Teal", "autoarchive": 30, "tint": 0.42,
            "topbar_colour": TOPBAR_BG_DEFAULT,
            "next_tab_id": 1, "ok": False, "partial": False,
            "windows": [{"geometry": None, "zoomed": False, "pinned": False,
                        "tabs": [tid], "active": tid}],
            "tabs": {tid: _empty_tab(WORK_TAB_NAME, default_tab_colour(0))}}
def load_app_state():
    """Reads the whole app's state: every window, and every tab (with its
    groups/tasks) in each window. Understands the current format (#format=3,
    tabs namespaced as '[tabid/GroupName]') and transparently upgrades an
    older single-board file (#format=2 or below, plain '[GroupName]') into
    one window containing a single tab named 'Work' - so existing data is
    never lost, it just starts out as one tab."""
    if not os.path.exists(DATA_FILE):
        return _default_app_state()
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            lines = [ln.rstrip("\r") for ln in f.read().split("\n")]
    except OSError as exc:
        log_error("Couldn't read TodoList.txt - starting with an empty list", exc)
        return _default_app_state()
    # Format is decided up-front from the (always-first) #format= line, so
    # every other line is parsed unambiguously - no guessing based on what
    # other lines happen to be present.
    fmt = 2
    for line in lines:
        if line.startswith("#format="):
            try:
                fmt = int(line[len("#format="):].strip())
            except ValueError:
                pass
            break
    is_v3 = fmt >= 3
    escaped = fmt >= 2
    state = {"scale": 1.0, "theme": "Teal", "autoarchive": 30, "tint": 0.42,
             "topbar_colour": TOPBAR_BG_DEFAULT,
             "next_tab_id": 1, "ok": True, "partial": False}
    windows = {}            # winid -> {"geometry","zoomed","pinned","tabs":[],"active"}
    window_order = []
    tabs = {}               # tabid -> tab dict (see _empty_tab)
    tab_order = []
    def _get_tab(tabid):
        if tabid not in tabs:
            tabs[tabid] = _empty_tab(f"Tab {tabid}", default_tab_colour(len(tabs)))
            tab_order.append(tabid)
        return tabs[tabid]
    def _get_window(winid):
        if winid not in windows:
            windows[winid] = {"geometry": None, "zoomed": False, "pinned": False,
                              "tabs": [], "active": None}
            window_order.append(winid)
        return windows[winid]
    # Legacy (format<3) single-board accumulators
    legacy_groups = {GENERAL: [GENERAL, []]}
    legacy_group_order = [legacy_groups[GENERAL]]
    legacy_done = []
    legacy_folded = set()
    legacy_colours = {}
    legacy_geometry = None
    legacy_zoomed = False
    legacy_pinned = False
    legacy_collapsed = False
    current_legacy_group = GENERAL
    current_tab_group = None     # (tabid, group_task_list) for v3 task-line routing
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("#"):
            key, _, value = line[1:].partition("=")
            try:
                if key == "format":
                    pass                      # already resolved above
                elif key == "scale":
                    state["scale"] = float(value)
                elif key == "autoarchive":
                    state["autoarchive"] = max(0, int(value))
                elif key == "tint":
                    state["tint"] = min(0.8, max(0.1, float(value)))
                elif key == "topbarcolour":
                    hexc = value.strip()
                    if QColor.isValidColorName(hexc):
                        state["topbar_colour"] = hexc
                elif key == "theme":
                    state["theme"] = value.strip()
                elif key == "nexttabid":
                    state["next_tab_id"] = max(1, int(value))
                elif key == "win" and is_v3:
                    p = value.split(",")
                    winid = int(p[0])
                    w = _get_window(winid)
                    w["geometry"] = (int(p[1]), int(p[2]), int(p[3]), int(p[4]))
                    w["zoomed"] = p[5] == "1"
                    w["pinned"] = p[6] == "1"
                    w["active"] = int(p[7])
                elif key == "wintab" and is_v3:
                    winid_s, _, tabid_s = value.partition(",")
                    w = _get_window(int(winid_s))
                    w["tabs"].append(int(tabid_s))
                elif key == "tab" and is_v3:
                    tabid_s, _, name = value.partition(",")
                    t = _get_tab(int(tabid_s))
                    t["name"] = clean(name) or t["name"]
                elif key == "tabcolour" and is_v3:
                    tabid_s, _, hexc = value.partition(",")
                    _get_tab(int(tabid_s))["colour"] = hexc.strip()
                elif key == "tabcollapsed" and is_v3:
                    tabid_s, _, v = value.partition(",")
                    _get_tab(int(tabid_s))["collapsed"] = v == "1"
                elif key == "fold":
                    if is_v3:
                        tabid_s, _, groupname = value.partition(",")
                        _get_tab(int(tabid_s))["folded"].add(groupname)
                    else:
                        legacy_folded.add(value)
                elif key == "gcolour":
                    if is_v3:
                        tabid_s, rest = value.split(",", 1)
                        hexc, _, name = rest.partition(" ")
                        if name:
                            _get_tab(int(tabid_s))["colours"][name] = hexc
                    else:
                        hexc, _, name = value.partition(" ")
                        if name:
                            legacy_colours[name] = hexc
                elif key == "window" and not is_v3:
                    legacy_geometry = parse_geometry(value)
                elif key == "zoomed" and not is_v3:
                    legacy_zoomed = value == "1"
                elif key == "pinned" and not is_v3:
                    legacy_pinned = value == "1"
                elif key == "collapsed" and not is_v3:
                    legacy_collapsed = value == "1"
            except (ValueError, IndexError) as exc:
                state["partial"] = True
                log_error(f"Ignoring malformed setting line: {line!r}", exc)
            continue
        if line.startswith("[") and line.rstrip().endswith("]"):
            inner = line.strip()[1:-1]
            if is_v3:
                try:
                    tabid_s, groupname = inner.split("/", 1)
                    tabid = int(tabid_s)
                except ValueError:
                    state["partial"] = True
                    continue
                t = _get_tab(tabid)
                name = clean(groupname) or GENERAL
                existing = next((gl for gn, gl in t["groups"] if gn == name), None)
                if existing is None:
                    existing = []
                    t["groups"].append([name, existing])
                current_tab_group = (tabid, existing)
            else:
                name = clean(inner) or GENERAL
                if name not in legacy_groups:
                    legacy_groups[name] = [name, []]
                    legacy_group_order.append(legacy_groups[name])
                current_legacy_group = name
            continue
        try:
            parts = line.split("\t")
            line_state = parts[0]
            text = parts[1] if len(parts) > 1 else ""
            files = [f for f in parts[2].split("|") if f] if len(parts) > 2 else []
            if escaped:
                text = unescape(text)
            text = clean_task(text)
            if not text:
                continue
            # "group" is set to the real group NAME below once we know it;
            # for v3 it's resolved from current_tab_group, so a placeholder
            # here is fine either way.
            task = {"text": text, "done": line_state == "1",
                    "group": current_legacy_group}
            if files:
                task["files"] = files
            if len(parts) > 3:
                for item in parts[3].split(";"):
                    k, _, v = item.partition("=")
                    if k == "star" and v == "1":
                        task["star"] = True
                    elif k == "due" and parse_due(v):
                        task["due"] = v
                    elif k == "doneat" and parse_due(v):
                        task["doneat"] = v
            if task["done"] and not task.get("doneat"):
                task["doneat"] = date.today().isoformat()
            if is_v3:
                if current_tab_group is None:
                    continue
                tabid, group_list = current_tab_group
                t = _get_tab(tabid)
                # task["group"] must be the GROUP NAME, not the tab id -
                # find it from which list we're appending into.
                gname = next(gn for gn, gl in t["groups"] if gl is group_list)
                task["group"] = gname
                (t["done"] if task["done"] else group_list).append(task)
            else:
                (legacy_done if task["done"] else legacy_groups[current_legacy_group][1]
                 ).append(task)
        except Exception as exc:
            state["partial"] = True
            log_error(f"Ignoring malformed task line: {line!r}", exc)
    if is_v3 and tabs:
        state["windows"] = [
            {"geometry": windows[w]["geometry"], "zoomed": windows[w]["zoomed"],
             "pinned": windows[w]["pinned"],
             "tabs": windows[w]["tabs"] or [t for t in tab_order if t not in
                     {tid for ow in window_order if ow != w for tid in windows[ow]["tabs"]}],
             "active": windows[w]["active"] if windows[w]["active"] in windows[w]["tabs"]
                       else (windows[w]["tabs"][0] if windows[w]["tabs"] else None)}
            for w in window_order] or [
            {"geometry": None, "zoomed": False, "pinned": False,
             "tabs": tab_order, "active": tab_order[0] if tab_order else None}]
        # Any tab that somehow isn't claimed by a window (corrupt file) still
        # needs to be shown somewhere rather than silently vanishing.
        claimed = {tid for w in state["windows"] for tid in w["tabs"]}
        orphans = [tid for tid in tab_order if tid not in claimed]
        if orphans:
            if state["windows"]:
                state["windows"][0]["tabs"] += orphans
                if state["windows"][0]["active"] is None:
                    state["windows"][0]["active"] = orphans[0]
            else:
                state["windows"] = [{"geometry": None, "zoomed": False, "pinned": False,
                                     "tabs": orphans, "active": orphans[0]}]
        state["tabs"] = tabs
        if state["next_tab_id"] <= max(tabs):
            state["next_tab_id"] = max(tabs) + 1
    else:
        # Legacy file (or a v3-format file with no tabs somehow) - wrap the
        # single board we parsed into one "Work" tab in one window.
        tid = 0
        state["tabs"] = {tid: {
            "name": WORK_TAB_NAME, "colour": legacy_theme_top_colour(state["theme"]),
            "collapsed": legacy_collapsed, "folded": legacy_folded,
            "colours": legacy_colours, "groups": legacy_group_order, "done": legacy_done}}
        state["windows"] = [{"geometry": legacy_geometry, "zoomed": legacy_zoomed,
                             "pinned": legacy_pinned, "tabs": [tid], "active": tid}]
        state["next_tab_id"] = 1
    return state
def task_line(state, t):
    line = f"{state}\t{escape(clean_task(t['text']))}"
    files = "|".join(t.get("files") or [])
    meta = []
    if t.get("star"):
        meta.append("star=1")
    if t.get("due"):
        meta.append(f"due={t['due']}")
    if t.get("done") and t.get("doneat"):
        meta.append(f"doneat={t['doneat']}")
    if meta:
        line += "\t" + files + "\t" + ";".join(meta)
    elif files:
        line += "\t" + files
    return line
def save_app_state(windows, tabs, scale, autoarchive, tint, next_tab_id, topbar_colour):
    """Writes the WHOLE app (every window, every tab in it, every tab's
    groups/tasks) to TodoList.txt atomically. `windows` is an ordered list of
    {"geometry":(x,y,w,h),"zoomed":bool,"pinned":bool,"tabs":[tabid,...],
    "active":tabid}; `tabs` maps tabid -> {"name","colour","collapsed",
    "folded","colours","groups","done"} (the same per-tab shape used
    throughout the app). Each tab carries its own background colour, so
    there's no shared app-wide theme to write any more - `topbar_colour` is
    the one exception: a flat shared colour for the bar itself (behind the
    tabs), set from the ... settings popup. Returns True on success, False
    on failure - the caller must never treat a False return as a save."""
    lines = ["#format=3", f"#scale={scale:.2f}",
             f"#autoarchive={autoarchive}", f"#tint={tint:.2f}",
             f"#topbarcolour={topbar_colour}",
             f"#nexttabid={next_tab_id}"]
    for winid, w in enumerate(windows):
        x, y, wd, h = w["geometry"]
        lines.append(f"#win={winid},{x},{y},{wd},{h},"
                      f"{1 if w['zoomed'] else 0},{1 if w['pinned'] else 0},{w['active']}")
        for tabid in w["tabs"]:
            lines.append(f"#wintab={winid},{tabid}")
    for tabid, t in tabs.items():
        lines.append(f"#tab={tabid},{t['name']}")
        lines.append(f"#tabcolour={tabid},{t['colour']}")
        lines.append(f"#tabcollapsed={tabid},{1 if t['collapsed'] else 0}")
        for name in t["folded"]:
            lines.append(f"#fold={tabid},{name}")
        for name, hexc in t["colours"].items():
            lines.append(f"#gcolour={tabid},{hexc} {name}")
    for tabid, t in tabs.items():
        names = [g for g, _ in t["groups"]]
        for name, open_tasks in t["groups"]:
            lines.append(f"[{tabid}/{name}]")
            for task in open_tasks:
                lines.append(task_line(0, task))
            for task in t["done"]:
                if task["group"] == name or (name == GENERAL and task["group"] not in names):
                    lines.append(task_line(1, task))
    text = "\n".join(lines) + "\n"
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            if f.read().replace("\r\n", "\n") == text:
                return True          # nothing changed - don't touch the file (no OneDrive sync)
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    except OSError as exc:
        log_error("Couldn't create the folder for TodoList.txt", exc)
        return False
    # Unique temp name (pid + random) so two copies can never collide, then an
    # atomic replace - the real file is never left half-written.
    tmp = f"{DATA_FILE}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(DATA_FILE):
            try:
                shutil.copy2(DATA_FILE, DATA_FILE + ".bak")   # last-known-good backup
            except OSError as exc:
                log_error("Couldn't refresh TodoList.txt.bak (save continues)", exc)
        os.replace(tmp, DATA_FILE)
        return True
    except OSError as exc:
        log_error("Couldn't save TodoList.txt", exc)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
# ------------------------------------------------------------------
# ATTACHMENTS (Outlook emails / files dropped onto tasks)
# ------------------------------------------------------------------
def is_location(name):
    """Folders dropped on a task are stored as their full path (never copied).
    Copied attachments are stored as a plain file name."""
    return os.path.isabs(name)
def attach_path(name):
    return name if is_location(name) else os.path.join(ATTACH_DIR, name)
def display_name(name):
    """What the chip shows: folder name for locations, file name otherwise."""
    if is_location(name):
        return os.path.basename(name.rstrip("\\/")) or name
    return name
_isdir_cache = {}                    # linked path -> True/False, from a background check
attachment_kinds_changed = [False]    # set once a background check updates the cache
def cached_isdir(path):
    """Whether a linked location is a folder. Never touches the filesystem
    directly from paintEvent (network paths can be very slow) - starts out
    assuming 'file', checks in the background, and flips the icon once the
    real answer is known."""
    hit = _isdir_cache.get(path)
    if hit is not None:
        return hit
    _isdir_cache[path] = False
    def check():
        try:
            real = os.path.isdir(path)
        except OSError:
            real = False
        if _isdir_cache.get(path) != real:
            _isdir_cache[path] = real
            attachment_kinds_changed[0] = True
    threading.Thread(target=check, daemon=True).start()
    return False
def safe_name(name):
    name = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name)
    name = name.strip(" .")
    stem, ext = os.path.splitext(name)
    return (stem[:120].strip() or "attachment") + ext[:10]
def unique_path(name, taken=()):
    os.makedirs(ATTACH_DIR, exist_ok=True)
    stem, ext = os.path.splitext(safe_name(name))
    path, n = attach_path(stem + ext), 2
    while os.path.exists(path) or path in taken:
        path = attach_path(f"{stem} ({n}){ext}")
        n += 1
    return path
# ---------- ownership manifest: only files we know we copied in may ever be
# ---------- silently cleaned up; anything else (linked paths, attachments
# ---------- from before this existed) is left alone.
_manifest_cache = None
def _load_manifest():
    global _manifest_cache
    if _manifest_cache is None:
        names = set()
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                names = {ln.strip() for ln in f if ln.strip()}
        except OSError:
            pass
        _manifest_cache = names
    return _manifest_cache
def _save_manifest():
    if _manifest_cache is None:
        return
    try:
        os.makedirs(ATTACH_DIR, exist_ok=True)
        text = "\n".join(sorted(_manifest_cache))
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            f.write(text + ("\n" if text else ""))
    except OSError as exc:
        log_error("Couldn't update the attachment manifest", exc)
def mark_owned(names):
    """Remember that this app copied/created these files in ATTACH_DIR, so
    cleanup_attachments() is allowed to remove them later if unreferenced."""
    m = _load_manifest()
    changed = False
    for n in names:
        if n and not is_location(n) and n not in m:
            m.add(n)
            changed = True
    if changed:
        _save_manifest()
def unmark_owned(names):
    m = _load_manifest()
    changed = False
    for n in names:
        if n in m:
            m.discard(n)
            changed = True
    if changed:
        _save_manifest()
def _mime_format(mime, key):
    for f in mime.formats():
        if f == key or f.endswith(f'"{key}"'):
            return f
    return None
def _descriptor_names(raw, wide):
    """File names from an Outlook/Explorer FileGroupDescriptor blob. Bounds
    are validated defensively - a malformed/truncated blob must never cause
    an out-of-range read or a huge loop."""
    if len(raw) < 4:
        return []
    count = int.from_bytes(raw[:4], "little")
    count = min(count, MAX_DESCRIPTORS)
    size, name_len = (592, 520) if wide else (332, 260)
    names = []
    for i in range(count):
        off = 4 + i * size + 72
        if off + name_len > len(raw):
            break            # truncated/malformed descriptor - stop, don't guess
        chunk = raw[off:off + name_len]
        text = chunk.decode("utf-16-le" if wide else "cp1252", "replace")
        text = text.split("\0")[0].strip()
        if text:
            names.append(os.path.basename(text))
    return names
def can_accept_drop(mime):
    if mime is None:
        return False
    if mime.hasUrls() and any(u.isLocalFile() for u in mime.urls()):
        return True
    return bool(_mime_format(mime, "FileGroupDescriptorW") or
                _mime_format(mime, "FileGroupDescriptor"))
OUTLOOK_PS = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ol = [Runtime.InteropServices.Marshal]::GetActiveObject('Outlook.Application')
$sel = $ol.ActiveExplorer().Selection
$dir = '%s'
for ($i = 1; $i -le $sel.Count; $i++) {
    $it = $sel.Item($i)
    try {
        $p = Join-Path $dir ("$i.msg")
        $it.SaveAs($p, 3)
        $s = [string]$it.Subject
        if (-not $s) { $s = 'Email' }
        Write-Output ("$i`t" + ($s -replace "[`r`n`t]", ' '))
    } catch {}
}
"""
def save_outlook_items(names):
    """Several items dragged/pasted at once: Qt only gives us their names
    (from FileGroupDescriptor), so ask Outlook for the actual content.
    Covers, and correctly tells apart:
      - one or more attachments pulled out of the open Inspector window, or
        out of the single previewed/selected email - matched by file name
        against that email's Attachments collection (each match consumes
        one entry, so two attachments that happen to share a name both
        still get through);
      - one or more whole emails selected in the explorer list - saved as
        .msg.
    Tries pywin32 first (it can match by name, so a mixed drop/paste of
    attachments and whole emails works); falls back to PowerShell for whole
    emails only if pywin32 isn't installed.
    This is meant to run off the Qt UI thread - it never touches widgets.
    Returns (saved_paths, failed_names): saved_paths are the final files
    inside ATTACH_DIR; failed_names lists exactly which requested items
    could not be retrieved, so the caller can tell the user what's missing
    instead of silently dropping them."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="todo_mail_")
    remaining = list(names)
    saved = []                           # (temp file, display name to save as)
    failed_display = []                  # matched but couldn't be saved/moved
    pywin32_ok = False
    try:
        try:
            import win32com.client       # fast if pywin32 is installed
            ol = win32com.client.GetActiveObject("Outlook.Application")
            pywin32_ok = True
        except Exception as exc:
            ol = None
            log_error("pywin32 / Outlook COM unavailable for this fetch", exc)
        if ol is not None:
            # 1) attachments of the open Inspector, then of the single
            #    previewed/selected email, matched by file name
            sources = []
            try:
                insp = ol.ActiveInspector()
                if insp is not None:
                    sources.append(insp.CurrentItem)
            except Exception:
                pass
            try:
                exp = ol.ActiveExplorer()
                sel = exp.Selection if exp is not None else None
                if sel is not None and sel.Count == 1:
                    sources.append(sel.Item(1))
            except Exception:
                pass
            for item in sources:
                try:
                    atts = item.Attachments
                except Exception:
                    continue
                for i in range(1, atts.Count + 1):
                    if not remaining:
                        break
                    try:
                        att = atts.Item(i)
                        fn = os.path.basename(str(att.FileName))
                    except Exception:
                        continue
                    if fn in remaining:
                        # unique temp name - two attachments can share fn
                        tmp_name = f"{uuid.uuid4().hex}_{safe_name(fn)}"
                        p = os.path.join(tmp, tmp_name)
                        try:
                            att.SaveAsFile(p)
                            saved.append((p, fn))
                            remaining.remove(fn)
                        except Exception as exc:
                            log_error(f"Couldn't save Outlook attachment '{fn}'", exc)
            # 2) anything left over: whole emails selected in the list.
            # Subject-derived names and the Explorer-supplied descriptor
            # names go through different sanitising rules (illegal
            # characters, truncation, etc.), so they often won't match
            # exactly even when the email is the right one - an exact-string
            # requirement here is what caused successfully-saved emails to
            # still be reported as "couldn't be attached". Try a normalised
            # match first, then fall back to consuming by position/count so
            # a save that actually succeeded is never misreported as failed.
            if remaining and all(n.lower().endswith(".msg") for n in remaining):
                def _norm(s):
                    return re.sub(r"[^a-z0-9]+", "", s.lower())
                try:
                    exp = ol.ActiveExplorer()
                    sel = exp.Selection
                    still = list(remaining)
                    still_norm = [_norm(n) for n in still]
                    for i in range(1, sel.Count + 1):
                        it = sel.Item(i)
                        try:
                            subj = str(it.Subject or "Email")
                            name = subj if subj.lower().endswith(".msg") else subj + ".msg"
                            p = os.path.join(tmp, f"{uuid.uuid4().hex}.msg")
                            it.SaveAs(p, 3)          # 3 = olMSG
                            saved.append((p, name))
                            nm = _norm(name)
                            if nm in still_norm:
                                k = still_norm.index(nm)
                            elif still:
                                k = 0     # count-based fallback: a genuine
                                          # save still counts as one handled,
                                          # even if the names don't line up
                            else:
                                k = None
                            if k is not None:
                                del still[k]
                                del still_norm[k]
                        except Exception as exc:
                            log_error("Couldn't save an Outlook email", exc)
                    if len(still) < len(remaining):
                        remaining = still
                except Exception as exc:
                    log_error("Couldn't read the Outlook selection", exc)
        # 3) pywin32 missing (or nothing left to try above): PowerShell
        #    fallback - whole emails only, can't match attachments by name
        if remaining and not pywin32_ok and all(n.lower().endswith(".msg") for n in remaining):
            script = OUTLOOK_PS % tmp.replace("'", "''")
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                    creationflags=0x08000000, timeout=20, capture_output=True)
                got = 0
                for line in res.stdout.decode("utf-8", "replace").splitlines():
                    num, _, subj = line.partition("\t")
                    p = os.path.join(tmp, f"{num.strip()}.msg")
                    if os.path.exists(p):
                        subj = subj.strip() or "Email"
                        saved.append((p, subj if subj.lower().endswith(".msg") else subj + ".msg"))
                        got += 1
                if got:
                    remaining = remaining[got:]
            except Exception as exc:
                log_error("PowerShell fallback for Outlook emails failed", exc)
        out, taken = [], []
        for p, name in saved:
            if not os.path.exists(p):
                failed_display.append(name)
                continue
            dst = unique_path(name, taken)
            try:
                shutil.move(p, dst)
                taken.append(dst)
                out.append(dst)
            except OSError as exc:
                log_error(f"Couldn't move Outlook item into attachments: '{name}'", exc)
                failed_display.append(name)
        all_failed = list(remaining) + failed_display
        if all_failed and not pywin32_ok and any(not n.lower().endswith(".msg") for n in all_failed):
            # Without pywin32, attachments can't be matched/extracted at all
            # (only whole emails, via PowerShell) - say so rather than just
            # listing names with no explanation.
            all_failed = all_failed + [
                "(pywin32 isn't installed, so individual attachments can't be "
                "fetched from Outlook - only whole emails can, via PowerShell)"]
        return out, all_failed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
def open_attachment(name, parent=None):
    path = attach_path(name)
    if os.path.exists(path):          # folder locations open in Explorer
        try:
            os.startfile(path)
            return
        except OSError as exc:
            log_error(f"Couldn't open attachment '{path}'", exc)
            alert(parent, "Location" if is_location(name) else "Attachment",
                  f"Couldn't open:\n{path}\n\n{exc}")
            return
    alert(parent, "Location" if is_location(name) else "Attachment", f"Can't find:\n{path}")
def archive_tasks(tasks):
    """Append tasks to TodoArchive.txt; their attachments are copied into
    TodoAttachments\\Archive so the archive still points at them.
    Returns (block written, attachment copies) or None if it failed."""
    if not tasks:
        return "", []
    copies = []
    lines = []
    for t in tasks:
        kept, places = [], []
        for n in t.get("files") or []:
            if is_location(n):
                places.append(n)
                continue
            src_path = attach_path(n)
            if not os.path.isfile(src_path):
                continue
            try:
                os.makedirs(ARCHIVE_ATT_DIR, exist_ok=True)
                stem, ext = os.path.splitext(n)
                dst, k = os.path.join(ARCHIVE_ATT_DIR, n), 2
                while os.path.exists(dst):
                    dst = os.path.join(ARCHIVE_ATT_DIR, f"{stem} ({k}){ext}")
                    k += 1
                shutil.copy2(src_path, dst)
                kept.append(dst)
                copies.append(dst)
            except OSError as exc:
                log_error(f"Couldn't copy '{n}' into the archive", exc)
        line = (f"{t.get('doneat') or '':10}  [{t['group']}]  "
                f"{clean_task(t['text']).replace(chr(10), ' / ')}")
        if t.get("due"):
            line += f"  (due {t['due']})"
        for f in kept:
            line += f"\n{'':12}attachment: {f}"
        for f in places:
            line += f"\n{'':12}location: {f}"
        lines.append(line)
    block = "\n".join(lines) + "\n"
    try:
        new = not os.path.exists(ARCHIVE_FILE)
        with open(ARCHIVE_FILE, "a", encoding="utf-8") as f:
            if new:
                f.write(ARCHIVE_HEADER)
            f.write(block)
        return block, copies
    except OSError as exc:
        log_error("Couldn't write to TodoArchive.txt", exc)
        return None
ARCHIVE_HEADER = "Archived tasks  (completed date, group, task)\n\n"
def unarchive(block, copies):
    """Undo of an archive: take those lines back out of TodoArchive.txt."""
    for p in copies:
        try:
            os.remove(p)
        except OSError as exc:
            log_error(f"Couldn't remove archived copy '{p}' while undoing", exc)
    if not block:
        return
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            text = f.read()
        k = text.rfind(block)
        if k < 0:
            return
        text = text[:k] + text[k + len(block):]
        if text.strip() == ARCHIVE_HEADER.strip():
            os.remove(ARCHIVE_FILE)
        else:
            with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
                f.write(text)
    except OSError as exc:
        log_error("Couldn't undo an archive in TodoArchive.txt", exc)
def open_archive(parent=None):
    if not os.path.exists(ARCHIVE_FILE):
        alert(parent, "Archive", "Nothing archived yet.")
        return
    try:
        os.startfile(ARCHIVE_FILE)
    except OSError as exc:
        log_error(f"Couldn't open '{ARCHIVE_FILE}'", exc)
        alert(parent, "Archive", f"Couldn't open:\n{ARCHIVE_FILE}\n\n{exc}")
TRASH_DIR = os.path.join(ATTACH_DIR, ".deleted")
def trash_files(names):
    """Take files out of the attachments folder straight away. They sit in a
    hidden .deleted folder until the list closes, so Ctrl+Z can bring them
    back. Only ever acts on copied attachments - a linked location (a real
    file or folder somewhere else) is never touched."""
    for n in names:
        if is_location(n):
            continue            # a linked file/folder somewhere - never touch it
        src_path = attach_path(n)
        if not os.path.isfile(src_path):
            continue
        try:
            os.makedirs(TRASH_DIR, exist_ok=True)
            if os.name == "nt":
                ctypes.windll.kernel32.SetFileAttributesW(TRASH_DIR, 0x2)   # hidden
            os.replace(src_path, os.path.join(TRASH_DIR, n))
        except OSError as exc:
            # e.g. the file is open elsewhere - leave it where it is rather
            # than lose it; it'll just stay a normal (unreferenced) attachment
            log_error(f"Couldn't move '{n}' to the trash (left in place)", exc)
def restore_files(names):
    for n in names:
        if is_location(n):
            continue
        dst = attach_path(n)
        trashed = os.path.join(TRASH_DIR, n)
        if not os.path.exists(dst) and os.path.exists(trashed):
            try:
                os.replace(trashed, dst)
            except OSError as exc:
                log_error(f"Couldn't restore '{n}' from the trash", exc)
def cleanup_attachments(keep):
    """Called only after a fully successful close (good load, good save):
    empties .deleted for good, and removes copied attachments that this app
    made (tracked in the ownership manifest) and that no task references
    any more. Anything not in the manifest - a linked location, or a copy
    made before this tracking existed - is left alone, even if unreferenced,
    so nothing is ever deleted just because it looks orphaned."""
    shutil.rmtree(TRASH_DIR, ignore_errors=True)
    owned = _load_manifest()
    try:
        names = os.listdir(ATTACH_DIR)
    except OSError as exc:
        log_error(f"Couldn't list '{ATTACH_DIR}' for cleanup", exc)
        return
    removed = []
    for n in names:
        if n.startswith(".") or n == "Archive":
            continue                       # manifest file, trash dir, archive copies
        path = attach_path(n)
        if n in keep or n not in owned or not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed.append(n)
        except OSError as exc:
            log_error(f"Couldn't remove unused attachment '{n}'", exc)
    if removed:
        unmark_owned(removed)
# ------------------------------------------------------------------
# DUE DATES
# ------------------------------------------------------------------
def parse_due(value):
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None
def due_text(value):
    """('Due tomorrow', days_from_today) - days < 0 means overdue."""
    d = parse_due(value)
    if d is None:
        return None, 0
    today = date.today()
    days = (d - today).days
    nice = d.strftime("%a ") + str(d.day) + d.strftime(" %b")
    if d.year != today.year:
        nice += f" {d.year}"
    if days == 0:
        return "Due today", 0
    if days == 1:
        return "Due tomorrow", 1
    if days == -1:
        return "Overdue, yesterday", -1
    if days < 0:
        return f"Overdue, {nice}", days
    return f"Due {nice}", days
def done_text(value):
    d = parse_due(value)
    if d is None:
        return None
    days = (date.today() - d).days
    if days == 0:
        return "Completed today"
    if days == 1:
        return "Completed yesterday"
    nice = d.strftime("%a ") + str(d.day) + d.strftime(" %b")
    if d.year != date.today().year:
        nice += f" {d.year}"
    return f"Completed {nice}"
def due_colour(days):
    return OVERDUE if days < 0 else DUE_SOON if days <= 1 else DUE_LATER
_DAYS = {"mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1,
         "wed": 2, "weds": 2, "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3,
         "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5,
         "sun": 6, "sunday": 6}
_MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
           "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
           "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
           "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12}
_WEEKDAY_ALT = "|".join(sorted(_DAYS, key=len, reverse=True))
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
# Optional "due"/"by" lead-in, then the date word/phrase, then trailing
# punctuation from normal sentence typing (a full stop, comma, etc.) that
# shouldn't stop any of these from matching.
_LEAD = r"(?:\s+(?:due|by))?\s+"
_TAIL = r"[.,;:!?\s]*$"
_RE_RELATIVE = re.compile(
    _LEAD + r"(?P<word>today|tdy|eod|tomorrow|tmr|tmrw|tmw|eow|eom|next\s+week)" + _TAIL, re.I)
_RE_IN_N = re.compile(_LEAD + r"in\s+(?P<n>\d{1,3})\s+(?P<unit>days?|weeks?)" + _TAIL, re.I)
_RE_WEEKDAY = re.compile(
    _LEAD + r"(?:(?P<prefix>this|next)\s+)?(?P<day>" + _WEEKDAY_ALT + r")" + _TAIL, re.I)
_RE_ISO = re.compile(_LEAD + r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})" + _TAIL)
# Deliberately "/" only (not "-" or "."): this app is used for structural
# engineering tasks that constantly reference clause/section numbers like
# "cl 4.2" or "NZS 3404" - accepting "." or "-" as date separators here
# would silently misread those as due dates. ISO (yyyy-mm-dd) and
# month-name dates below cover the rest without that ambiguity.
_RE_NUMERIC = re.compile(_LEAD + r"(?P<d>\d{1,2})/(?P<m>\d{1,2})(?:/(?P<y>\d{2,4}))?" + _TAIL)
_RE_MONTH_DMY = re.compile(
    _LEAD + r"(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon>" + _MONTH_ALT + r")"
    r"(?:\s+(?P<y>\d{4}))?" + _TAIL, re.I)
_RE_MONTH_MDY = re.compile(
    _LEAD + r"(?P<mon>" + _MONTH_ALT + r")\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s+(?P<y>\d{4}))?" + _TAIL, re.I)
def _eom(today):
    if today.month == 12:
        return date(today.year, 12, 31)
    return date(today.year, today.month + 1, 1) - timedelta(days=1)
def _weekday_date(today, day_word, prefix):
    wd = _DAYS[day_word.lower()]
    ahead = (wd - today.weekday()) % 7          # bare/'this': upcoming occurrence (today counts)
    if prefix and prefix.lower() == "next":
        ahead += 7                              # always the occurrence after that
    return today + timedelta(days=ahead)
def _yearless_date(today, month, day):
    """A day and month typed without a year: whichever occurrence is
    nearest today. A date a few weeks back stays this year (it's simply
    overdue - '2/9' typed in October means the 2nd of September just gone);
    only one more than half a year back means next year ('3/1' typed in
    December is January). May raise ValueError - the caller handles it."""
    d = date(today.year, month, day)
    if (today - d).days > 182:
        d = date(today.year + 1, month, day)
    elif (d - today).days > 182:
        d = date(today.year - 1, month, day)
    return d
def _month_date(today, day, mon_word, year):
    month = _MONTHS[mon_word.lower()]
    if not year:
        return _yearless_date(today, month, int(day))
    return date(int(year), month, int(day))       # may raise ValueError - caller handles it
def due_from_text(text):
    """'Check shop drawings fri' -> ('Check shop drawings', '2026-10-02').
    Only looks at the very end of the task. Recognises (in order tried):
    ISO dates, '15 oct'/'oct 15' style dates (with optional year), 'd/m[/y]'
    (NZ day/month), 'in N days/weeks', today/tdy/eod/tomorrow/tmr/eow/eom/
    next week, and weekday names ('fri' = the upcoming Friday, even if
    today is one; 'next fri' = the Friday after that; 'this fri' = same as
    bare 'fri')."""
    today = date.today()
    for rx in (_RE_ISO, _RE_MONTH_DMY, _RE_MONTH_MDY, _RE_NUMERIC,
               _RE_IN_N, _RE_RELATIVE, _RE_WEEKDAY):
        m = rx.search(text)
        if not m or not text[:m.start()].strip():
            continue
        try:
            if rx is _RE_ISO:
                d = date(int(m["y"]), int(m["m"]), int(m["d"]))
            elif rx in (_RE_MONTH_DMY, _RE_MONTH_MDY):
                d = _month_date(today, m["d"], m["mon"], m["y"])
            elif rx is _RE_NUMERIC:
                day, month = int(m["d"]), int(m["m"])
                year = m["y"]
                if year:
                    y = int(year) + (2000 if len(year) <= 2 else 0)
                    d = date(y, month, day)
                else:
                    d = _yearless_date(today, month, day)
            elif rx is _RE_IN_N:
                n = int(m["n"])
                d = today + (timedelta(weeks=n) if m["unit"].lower().startswith("week")
                             else timedelta(days=n))
            elif rx is _RE_RELATIVE:
                word = re.sub(r"\s+", " ", m["word"].lower())
                if word in ("today", "tdy", "eod"):
                    d = today
                elif word in ("tomorrow", "tmr", "tmrw", "tmw"):
                    d = today + timedelta(days=1)
                elif word == "eow":
                    d = _weekday_date(today, "fri", None)
                elif word == "eom":
                    d = _eom(today)
                else:                                       # "next week"
                    d = next_monday()
            else:                                            # _RE_WEEKDAY
                d = _weekday_date(today, m["day"], m["prefix"])
        except ValueError:
            continue             # looked like a match but not a real date - try the next pattern
        return text[:m.start()].rstrip(), d.isoformat()
    return text, None
_RE_URGENT = re.compile(r"(?:\s*!!+|\s+urgent)[.,;:!?\s]*$", re.I)
def detect_urgent(text):
    """A trailing '!!' or the word 'urgent' auto-stars the task and is
    stripped out, independent of (and in either order relative to) a due
    date word - see parse_task_shortcuts()."""
    m = _RE_URGENT.search(text)
    if not m or not text[:m.start()].strip():
        return text, False
    return text[:m.start()].rstrip(), True
_RE_GROUP_TAG = re.compile(r"[#@](\w[\w-]{0,40})")
def extract_group_tag(text, group_names):
    """'#Lincoln' or '@Lincoln' anywhere in the text routes the task to
    that group instead of whichever group it was typed in, and is stripped
    out. Matches case-insensitively, by exact name first, then by an
    unambiguous prefix (spaces in the group name ignored, so '#TiwaiPoint'
    can match a group literally named 'Tiwai Point'). If nothing matches,
    or more than one group could, the tag is left as plain text untouched
    - never guesses when it's unsure."""
    if not group_names:
        return text, None
    m = _RE_GROUP_TAG.search(text)
    if not m:
        return text, None
    token = m.group(1).lower()
    exact = [g for g in group_names if g.lower() == token]
    if len(exact) == 1:
        matched = exact[0]
    else:
        prefix = [g for g in group_names if g.lower().replace(" ", "").startswith(token)]
        if len(prefix) != 1:
            return text, None        # no match, or ambiguous - leave it as literal text
        matched = prefix[0]
    new_text = text[:m.start()] + text[m.end():]
    new_text = re.sub(r"[ \t]{2,}", " ", new_text).strip()
    return new_text, matched
def parse_task_shortcuts(text, group_names):
    """The full set of typed shortcuts, combined: a '#Group'/'@Group' tag
    (anywhere in the text), a due-date word, and a trailing '!!'/'urgent'
    marker - all independent of each other and order-independent at the
    tail (so 'RFI tmr !!' and 'RFI !! tmr' both work). Returns
    (clean_text, due_or_None, is_urgent, group_name_or_None)."""
    text, group = extract_group_tag(text, group_names)
    star = False
    due = None
    for _ in range(4):               # at most two real markers to find - this is a safe bound
        changed = False
        if not star:
            new_text, found = detect_urgent(text)
            if found:
                text, star, changed = new_text, True, True
        if due is None:
            new_text, found_due = due_from_text(text)
            if found_due:
                text, due, changed = new_text, found_due, True
        if not changed:
            break
    return text, due, star, group
def group_as_list(group):
    """Open tasks as dash bullets, ready to paste into an email / Aconex.
    Extra lines of a task are indented under it."""
    out = []
    for c in group.cards:
        lines = c.task["text"].split("\n")
        out.append("- " + lines[0])
        out += ["  " + ln for ln in lines[1:]]
    return "\n".join(out)
def next_monday():
    """Monday of next week. On Sunday that's 8 days away, not tomorrow."""
    today = date.today()
    days = 7 - today.weekday()
    if days == 1:
        days = 8
    return today + timedelta(days=days)
class _DayDelegate(QStyledItemDelegate):
    """Draws the calendar days: rounded highlight for the chosen day and a
    rounded hover, instead of Qt's square cells."""
    def paint(self, p, opt, index):
        text = index.data(Qt.DisplayRole)
        if text is None or text == "":
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(opt.rect)
        header = index.row() == 0                       # the M T W T F S S row
        enabled = bool(index.flags() & Qt.ItemIsEnabled)
        sel = bool(opt.state & QStyle.State_Selected) and not header
        hov = bool(opt.state & QStyle.State_MouseOver) and enabled and not header
        side = min(r.width(), r.height()) - 4
        cell = QRectF(r.center().x() - side / 2, r.center().y() - side / 2, side, side)
        fg = index.data(Qt.ForegroundRole)
        if hasattr(fg, "color"):
            colour = fg.color()
        elif isinstance(fg, QColor):
            colour = fg
        else:
            colour = QColor(TEXT)
        if not enabled and not header:
            colour = QColor("#5f676b")
        font = index.data(Qt.FontRole)
        font = QFont(font) if isinstance(font, QFont) else QFont(opt.font)
        if sel:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(cell, 6, 6)
            colour = QColor("#1b1f22")
        elif hov:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 28))
            p.drawRoundedRect(cell, 6, 6)
        p.setFont(font)
        p.setPen(colour)
        p.drawText(r, Qt.AlignCenter, str(text))
        p.restore()
def pick_date(parent, current=None, anchor=None):
    """Small dark calendar that opens under `anchor` (the task). One click picks."""
    from PySide6.QtWidgets import QToolButton, QTableView
    dlg = QDialog(parent, Qt.Popup | Qt.FramelessWindowHint)
    no_system_shadow(dlg)
    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(SHADOW, SHADOW - 2, SHADOW, SHADOW + 2)
    def _paint(_e):
        p = QPainter(dlg)
        paint_shadow(p, QRectF(dlg.rect()).adjusted(SHADOW, SHADOW - 2, -SHADOW, -SHADOW - 2),
                     POP_RADIUS)
        p.end()
    dlg.paintEvent = _paint
    card = QFrame()
    card.setObjectName("card")
    outer.addWidget(card)
    card.setStyleSheet(f"""
QFrame#card {{ background: #2b2f32; border: 1px solid #454b50; border-radius: 8px; }}
QLabel {{ color: {TEXT}; background: transparent; border: none; }}
QCalendarWidget {{ background: transparent; border: none; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: transparent; }}
QCalendarWidget QToolButton {{ color: {TEXT}; background: transparent; border: none;
    border-radius: 4px; padding: 3px 8px; font-family: '{FONT}'; font-size: 10pt; font-weight: 600; }}
QCalendarWidget QToolButton:hover {{ background: #3b4146; }}
QCalendarWidget QToolButton:pressed {{ background: #474e54; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; width: 0; }}
QCalendarWidget QMenu {{ background: #2b2f32; color: {TEXT}; border: 1px solid #454b50;
    border-radius: 8px; padding: 4px; font-family: '{FONT}'; font-size: 9pt; }}
QCalendarWidget QMenu::item {{ padding: 4px 18px 4px 10px; border-radius: 5px; }}
QCalendarWidget QMenu::item:selected {{ background: rgba(138, 180, 248, 46); }}
QCalendarWidget QSpinBox {{ background: #3b4146; color: {TEXT}; border: none; border-radius: 4px;
    padding: 2px 4px; selection-background-color: #3d6fb4; }}
QCalendarWidget QAbstractItemView {{ background: transparent; color: {TEXT}; border: none;
    font-family: '{FONT}'; font-size: 9pt; outline: 0;
    selection-background-color: transparent; selection-color: {TEXT}; }}
QCalendarWidget QAbstractItemView:disabled {{ color: #5f676b; }}
QCalendarWidget QTableView {{ background: #2b2f32; alternate-background-color: #2b2f32; }}
""")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(10, 8, 10, 10)
    lay.setSpacing(4)
    title = QLabel("Pick a due date")
    title.setFont(QFont(FONT, 9, QFont.Weight.DemiBold))
    title.setStyleSheet(f"color: {TEXT_SUB};")
    lay.addWidget(title)
    cal = QCalendarWidget()
    cal.setGridVisible(False)
    cal.setFirstDayOfWeek(Qt.Monday)
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames)
    cal.setMinimumSize(250, 210)
    # plain arrow text instead of the default blue icons
    for name, txt in (("qt_calendar_prevmonth", "\u2039"), ("qt_calendar_nextmonth", "\u203a")):
        b = cal.findChild(QToolButton, name)
        if b is not None:
            b.setIcon(QIcon())
            b.setText(txt)
            b.setFont(QFont(FONT, 13))
    # month drop-down: rounded, no square Windows shadow
    mbtn = cal.findChild(QToolButton, "qt_calendar_monthbutton")
    if mbtn is not None and mbtn.menu() is not None:
        no_system_shadow(mbtn.menu())
    view = cal.findChild(QTableView)
    if view is not None:
        view.setItemDelegate(_DayDelegate(view))
        view.setMouseTracking(True)
        view.viewport().setAttribute(Qt.WA_Hover)
        pal = view.palette()
        for role in (QPalette.Base, QPalette.AlternateBase, QPalette.Window):
            pal.setColor(role, QColor("#2b2f32"))
        # no square selection fill behind the cell - the delegate draws a rounded one
        pal.setColor(QPalette.Highlight, QColor(0, 0, 0, 0))
        pal.setColor(QPalette.HighlightedText, QColor(TEXT))
        view.setPalette(pal)
        view.viewport().setPalette(pal)
    wk = QTextCharFormat()
    wk.setForeground(QColor(TEXT))
    for day in (Qt.Saturday, Qt.Sunday):
        cal.setWeekdayTextFormat(day, wk)
    head = QTextCharFormat()
    head.setForeground(QColor(TEXT_DONE))
    head.setBackground(QColor(0, 0, 0, 0))
    cal.setHeaderTextFormat(head)
    today = QDate.currentDate()
    tf = QTextCharFormat()
    tf.setForeground(QColor(ACCENT))
    tf.setFontWeight(QFont.Weight.Bold)
    cal.setDateTextFormat(today, tf)
    d = parse_due(current) if current else None
    cal.setSelectedDate(QDate(d.year, d.month, d.day) if d else today)
    cal.clicked.connect(lambda _: dlg.accept())
    cal.activated.connect(lambda _: dlg.accept())
    lay.addWidget(cal)
    place_popup(dlg, anchor if anchor is not None else point_rect(QCursor.pos()))
    if dlg.exec() == QDialog.Accepted:
        q = cal.selectedDate()
        return f"{q.year():04d}-{q.month():02d}-{q.day():02d}"
    return None
# ------------------------------------------------------------------
# LINKS (URLs and file paths in task text)
# ------------------------------------------------------------------
URL_RE = re.compile(r'(?:https?://|www\.)[^\s<>"]+', re.I)
QPATH_RE = re.compile(r'"((?:[A-Za-z]:\\|\\\\)[^"\n]+)"')
PATH_RE = re.compile(r'(?:[A-Za-z]:\\|\\\\)[^\n"<>|*?]*')
TRAIL = ".,;:!?)]}'"
_exists_cache = {}
def _exists(path):
    """Cached (network drives can be slow), refreshed every 60 s."""
    now = time.monotonic()
    hit = _exists_cache.get(path)
    if hit is None or now - hit[1] > 60:
        try:
            ok = os.path.exists(path)
        except (OSError, ValueError):
            ok = False
        hit = _exists_cache[path] = (ok, now)
    return hit[0]
_drive_cache = {}
def _is_remote(path):
    """Network drive / UNC path - never touched while loading (slow or offline)."""
    if path.startswith("\\\\"):
        return True
    letter = path[:1].upper()
    if letter not in _drive_cache:
        try:
            _drive_cache[letter] = ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") == 4
        except Exception:
            _drive_cache[letter] = True
    return _drive_cache[letter]
_remote_lens = {}           # raw text -> length of the real path
_remote_pending = set()
_remote_lock = threading.Lock()
links_changed = [False]     # set by the background check, picked up by a timer
def _remote_check(raw):
    """Runs in a background thread: network drives can take seconds."""
    n = None
    cuts = [len(raw)] + [i for i in range(len(raw) - 1, 2, -1) if raw[i] == " "]
    try:
        for cut in cuts[:40]:
            base = raw[:cut].rstrip(" ")
            for cand in (base, base.rstrip(TRAIL + " ")):
                if cand and len(cand) > 3 and os.path.exists(cand):
                    n = len(cand)
                    break
            if n:
                break
    except Exception:
        pass
    if not n:
        first = raw.split()
        n = len(first[0].rstrip(TRAIL)) if first else 0
    with _remote_lock:
        _remote_lens[raw] = n
        _remote_pending.discard(raw)
    links_changed[0] = True
def _path_end(raw, whole_line):
    """Paths can contain spaces and brackets, e.g.
    U:\\...\\1. Standards and Building Code (NZ)
    Whole line (or after a colon): take the whole line, no disk check.
    Mid-sentence: longest part that exists. Network drives are checked in the
    background so loading never waits on them; the link grows once found."""
    if whole_line:
        return len(raw.rstrip(" .,;:"))
    if _is_remote(raw):
        with _remote_lock:
            if raw in _remote_lens:
                return _remote_lens[raw]
            start = raw not in _remote_pending
            _remote_pending.add(raw)
        if start:
            threading.Thread(target=_remote_check, args=(raw,), daemon=True).start()
        first = raw.split()                    # for now; updated once checked
        return len(first[0].rstrip(TRAIL)) if first else 0
    cuts = [len(raw)] + [i for i in range(len(raw) - 1, 2, -1) if raw[i] == " "]
    for n in cuts[:40]:
        base = raw[:n].rstrip(" ")
        for cand in (base, base.rstrip(TRAIL + " ")):
            if cand and len(cand) > 3 and _exists(cand):
                return len(cand)
    if whole_line:
        return len(raw.rstrip(" .,;:"))
    first = raw.split()
    return len(first[0].rstrip(TRAIL)) if first else 0
def find_links(text):
    spans = []
    def free(s, e):
        return all(e <= a or s >= b for a, b, _ in spans)
    for m in QPATH_RE.finditer(text):
        spans.append((m.start(1), m.end(1), m.group(1)))
    for m in URL_RE.finditer(text):
        s = m.group(0).rstrip(TRAIL)
        if s and free(m.start(), m.start() + len(s)):
            target = "http://" + s if s.lower().startswith("www.") else s
            spans.append((m.start(), m.start() + len(s), target))
    for m in PATH_RE.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        before = text[line_start:m.start()].strip()
        whole = before == "" or before.endswith(":")
        n = _path_end(m.group(0), whole)
        if n > 3 and free(m.start(), m.start() + n):
            spans.append((m.start(), m.start() + n, text[m.start():m.start() + n]))
    return sorted(spans)
_RE_LONG_RUN = re.compile(r"\S{16,}")
def breakable(text):
    """Text as displayed on a task: runs of 16+ characters with no space
    (long words, paths, URLs) get invisible break points between their
    characters, so they wrap at the card's edge instead of running off it.
    Display only - the stored text is never changed."""
    return _RE_LONG_RUN.sub(lambda m: "\u200b".join(m.group()), text)
def links_html(text, links):
    def esc(t):
        return html.escape(breakable(t), quote=False).replace("\n", "<br>")
    out, i = [], 0
    for k, (s, e, _) in enumerate(links):
        out.append(esc(text[i:s]))
        out.append(f'<a href="{k}" style="color:{ACCENT}; text-decoration:underline;">'
                   f'{esc(text[s:e])}</a>')
        i = e
    out.append(esc(text[i:]))
    return '<span style="white-space:pre-wrap;">' + "".join(out) + "</span>"
def open_link(target, parent=None):
    if re.match(r"https?://", target, re.I):
        QDesktopServices.openUrl(QUrl(target))
        return
    if os.path.exists(target):
        try:
            os.startfile(target)
            return
        except OSError as exc:
            log_error(f"Couldn't open link '{target}'", exc)
            alert(parent, "Link", f"Couldn't open:\n{target}\n\n{exc}")
            return
    alert(parent, "Link", f"Can't find:\n{target}")
def star_path(cx, cy, r):
    import math
    path = QPainterPath()
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = math.radians(-90 + i * 36)
        pt = QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path
# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def make_anim(widget):
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(ANIM_MS)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    return anim
def check_path(cx, cy, s=1.0):
    s *= S * 0.8
    path = QPainterPath()
    path.moveTo(cx - 4.2 * s, cy + 0.2 * s)
    path.lineTo(cx - 1.3 * s, cy + 3.0 * s)
    path.lineTo(cx + 4.3 * s, cy - 3.2 * s)
    return path
def round_corners(widget):
    """Windows 11 rounded corners for the frameless window."""
    if os.name != "nt":
        return
    try:
        hwnd = int(widget.winId())
        value = ctypes.c_int(2)     # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass
def shadow_for(widget):
    sh = QGraphicsDropShadowEffect(widget)
    sh.setBlurRadius(26 * S)
    sh.setOffset(0, 5 * S)
    sh.setColor(QColor(0, 0, 0, 145))
    return sh
def set_colour(widget, colour):
    """Text colour via palette - much faster than a style sheet per widget."""
    pal = widget.palette()
    pal.setColor(QPalette.WindowText, QColor(colour))
    widget.setPalette(pal)
def style_editor(widget):
    pal = widget.palette()
    clear = QColor(0, 0, 0, 0)
    pal.setColor(QPalette.Base, clear)
    pal.setColor(QPalette.Window, clear)
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor("#3d6fb4"))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(PLACEHOLDER))
    widget.setPalette(pal)
    widget.setAutoFillBackground(False)
class LineEdit(QLineEdit):
    escaped = Signal()
    focus_lost = Signal()
    focus_gained = Signal()
    undo_requested = Signal()
    def __init__(self, parent, size=10, bold=False):
        super().__init__(parent)
        self.pt, self.bold = size, bold
        self.setFrame(False)
        self.setTextMargins(0, 0, 0, 0)
        self.setAcceptDrops(False)
        style_editor(self)
        self.apply_scale()
    def apply_scale(self):
        self.setFont(F(self.pt, self.bold))
    def event(self, e):
        # Left/Right with text selected (e.g. the whole name, right after
        # starting a rename) and no modifier: put the cursor at the START /
        # END of the selection and drop it, like every native text box. Qt's
        # QLineEdit instead steps one character from the cursor, which after
        # select-all sits at the end - so Left landed one before the end.
        # Done in event(), ahead of QLineEdit's own key handling, so nothing
        # in between can act on the key first. Shift/Ctrl/Alt are untouched
        # (extend selection, word jumps).
        if (e.type() in (QEvent.KeyPress, QEvent.ShortcutOverride)
                and e.key() in (Qt.Key_Left, Qt.Key_Right) and self.hasSelectedText()
                and not (e.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier
                                          | Qt.AltModifier))):
            e.accept()
            if e.type() == QEvent.KeyPress:
                start = self.selectionStart()
                end = start + len(self.selectedText())
                self.setCursorPosition(start if e.key() == Qt.Key_Left else end)
            return True
        return super().event(e)
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.escaped.emit()
            return
        # Ctrl+Z: undo typing first, then undo task changes
        if e.matches(QKeySequence.StandardKey.Undo) and not self.isUndoAvailable():
            self.undo_requested.emit()
            return
        super().keyPressEvent(e)
    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.focus_gained.emit()
    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.focus_lost.emit()
def line_edit_height(edit):
    return QFontMetrics(edit.font()).height() + 4
class TextBox(QTextEdit):
    """Auto-growing multi-line box. Enter = submit, Alt/Shift+Enter = new line."""
    submitted = Signal()
    escaped = Signal()
    focus_lost = Signal()
    focus_gained = Signal()
    undo_requested = Signal()
    paste_requested = Signal(object)    # clipboard has files/Outlook items to attach
    def __init__(self, parent, size=10):
        super().__init__(parent)
        self.pt = size
        self.setAcceptRichText(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setContentsMargins(0, 0, 0, 0)
        style_editor(self)
        style_editor(self.viewport())
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        # Set by an owner (e.g. AddRow) that wants its own right-click menu
        # instead of Qt's built-in text-edit one (Undo/Cut/Copy/Paste/...).
        # Left as None everywhere else, so nothing else changes behaviour.
        self.menu_owner = None
        self.apply_scale()
    def apply_scale(self):
        f = F(self.pt)
        self.setFont(f)
        self.document().setDefaultFont(f)
    def text(self):
        return self.toPlainText()
    def insert(self, text):
        self.insertPlainText(text)
    def go_end(self):
        self.moveCursor(QTextCursor.MoveOperation.End)
    def content_height(self, width):
        doc = self.document()
        doc.setTextWidth(max(int(width), 10))
        h = int(doc.size().height() + 0.999)
        return max(h, QFontMetrics(self.font()).height()) + 2
    def keyPressEvent(self, e):
        # Ctrl+V: only take over the paste when the clipboard actually has
        # files/Outlook items - plain text keeps pasting normally below.
        if e.matches(QKeySequence.StandardKey.Paste):
            mime = QGuiApplication.clipboard().mimeData()
            if can_accept_drop(mime):
                self.paste_requested.emit(mime)
                return
        # Ctrl+Z: undo typing first, then fall through to undoing task changes
        if e.matches(QKeySequence.StandardKey.Undo) and not self.document().isUndoAvailable():
            self.undo_requested.emit()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            if e.modifiers() & (Qt.AltModifier | Qt.ShiftModifier):
                self.insertPlainText("\n")
            else:
                self.submitted.emit()
            return
        if e.key() == Qt.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(e)
    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.focus_gained.emit()
    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.focus_lost.emit()
    def contextMenuEvent(self, e):
        if self.menu_owner is not None:
            self.menu_owner(e.globalPos())
            return
        super().contextMenuEvent(e)      # unchanged everywhere menu_owner isn't set
def first_line_cy(height, text_top):
    """Circle centre: middle for single-line rows, first line for tall rows."""
    if height <= MIN_H + 2:
        return height / 2
    return text_top + task_line_h() / 2
# ------------------------------------------------------------------
# TASK CARD
# ------------------------------------------------------------------
class TaskCard(QWidget):
    def __init__(self, board, task):
        super().__init__(board)
        self.board = board
        self.task = task
        # Persistent tie-breaker for the star-sort in relayout() - see the
        # comment on Board._order_seq. Assigned once, here, and left alone
        # by star toggling; only an explicit drag reorder (Board._renumber)
        # changes it afterwards.
        self._order = board.next_order_seq()
        self.hover = False
        self.circle_hover = False
        self.selected = False
        self.dragging = False
        self.editing = False
        self.drop_hover = False
        self.chip_hover = -1
        self.star_hover = False
        self.link_hover = False
        self.att_rects = []
        self.links = []
        self._html = None
        self._doc = None
        self._doc_key = None
        self._sub_colour = None
        self.setMouseTracking(True)
        self.label = QLabel(self)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.sub = QLabel(self)
        self.sub.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._colour = None
        self.cy = MIN_H / 2
        self.editor = None      # only built when you edit (keeps loading fast)
        self._suspend_focus_commit = False  # True only while edit_menu()'s menu is open
        self.anim = make_anim(self)
        self.apply_scale()
    def make_editor(self):
        if self.editor is None:
            ed = TextBox(self)
            ed.hide()
            ed.submitted.connect(lambda: self.finish_edit(then="add"))
            ed.escaped.connect(lambda: self.finish_edit(then="board"))
            # Opening the right-click menu below takes focus away from the
            # editor; while it's open we don't want that focus change to
            # auto-commit the edit out from under the menu (see edit_menu),
            # so this is suppressed for exactly as long as the menu is open.
            ed.focus_lost.connect(
                lambda: None if getattr(self, "_suspend_focus_commit", False)
                else self.finish_edit())
            ed.textChanged.connect(self._editor_changed)
            ed.paste_requested.connect(lambda m: self.board.paste_attachment_for(self, m))
            # Right-click while editing: our own "Update task" + due-date
            # menu (same design as the Add-row's), instead of Qt's built-in
            # text-edit menu (Undo/Cut/Copy/Paste/...).
            ed.menu_owner = lambda pos: self.board.edit_menu(self, pos)
            self.editor = ed
        return self.editor
    def apply_scale(self):
        self.sub.setFont(F(7.5))
        if self.editor is not None:
            self.editor.apply_scale()
        self.refresh()
    def has_sub(self):
        return self.task["done"] or bool(self.task.get("due"))
    def urgency(self):
        """Colour for the strip on the left: overdue / today / tomorrow only."""
        if self.task["done"] or not self.task.get("due"):
            return None
        _, days = due_text(self.task["due"])
        return OVERDUE if days < 0 else DUE_SOON if days <= 1 else None
    def refresh(self):
        done = self.task["done"]
        text = self.task["text"]
        self.label.setFont(F(10, strike=done))
        self.links = find_links(text) if ("\\" in text or "www" in text.lower()
                                          or "http" in text.lower()) else []
        if self.links:
            self._html = links_html(text, self.links)
            self.label.setTextFormat(Qt.RichText)
            self.label.setText(self._html)
        else:
            self._html = None
            self.label.setTextFormat(Qt.PlainText)
            self.label.setText(breakable(text))
        self._doc_key = None
        colour = TEXT_DONE if done else TEXT
        if colour != self._colour:
            self._colour = colour
            set_colour(self.label, colour)
        parts, sub_colour = [], TEXT_DONE
        if done:
            parts.append(self.task["group"])
            finished = done_text(self.task.get("doneat"))
            if finished:
                parts.append(finished)
        else:
            label, days = due_text(self.task.get("due"))
            if label:
                parts.append(label)
                sub_colour = due_colour(days)
        self.sub.setText("  \u00b7  ".join(parts))
        if sub_colour != self._sub_colour:
            self._sub_colour = sub_colour
            set_colour(self.sub, sub_colour)
        self.sub.setVisible(bool(parts))
        self.update()
    def link_at(self, pos):
        if self.editing or not self.links or not self.label.isVisible():
            return None
        key = (self._html, self.label.width(), S, self.task["done"])
        if key != self._doc_key:
            doc = QTextDocument()
            doc.setDocumentMargin(0)
            doc.setDefaultFont(self.label.font())
            doc.setHtml(self._html)
            doc.setTextWidth(self.label.width())
            self._doc, self._doc_key = doc, key
        p = QPointF(pos) - QPointF(self.label.pos())
        if p.x() < 0 or p.y() < 0:
            return None
        a = self._doc.documentLayout().anchorAt(p)
        try:
            return self.links[int(a)][2] if a else None
        except (ValueError, IndexError):
            return None
    def in_star(self, pos):
        return pos.x() >= self.width() - STAR_W
    def _text_height(self, width):
        tw = max(width - TEXT_X - STAR_W, 40)
        lh = self.label.heightForWidth(tw)
        return tw, (lh if lh > 0 else self.label.sizeHint().height())
    def files(self):
        return self.task.get("files") or []
    def _parts(self, width):
        tw, lh = self._text_height(width)
        main = self.editor.content_height(tw) if self.editing else lh
        att = len(self.files()) * ATT_H
        sub = SUB_H if self.has_sub() else 0
        return tw, lh, main, att, sub
    def height_for(self, width):
        _, _, main, att, sub = self._parts(width)
        return max(MIN_H, main + att + sub + CARD_PAD)
    def apply_size(self, width, height):
        self.resize(width, height)
        tw, lh, main, att, sub = self._parts(width)
        top = (height - main - att - sub) // 2
        if self.editing:
            self.editor.setGeometry(TEXT_X, top, tw, main)
        else:
            self.label.setGeometry(TEXT_X, top, tw, lh)
        fm = QFontMetrics(F(8))
        self.att_rects = []
        y = top + main
        for name in self.files():
            w = min(tw, fm.horizontalAdvance(display_name(name)) + int(30 * S))
            self.att_rects.append((QRectF(TEXT_X, y + 2 * S, w, ATT_H - 4 * S), name))
            y += ATT_H
        if sub:
            self.sub.setGeometry(TEXT_X, y, tw, SUB_H)
        self.cy = first_line_cy(height, top)
    def chip_at(self, pos):
        for i, (r, _) in enumerate(self.att_rects):
            if r.contains(QPointF(pos)):
                return i
        return -1
    def _editor_changed(self):
        if self.editing:
            self.board.relayout(animate=False)
    def in_circle(self, pos):
        return pos.x() < CX + CR + 6 * S
    # ---------- editing ----------
    def home_group(self):
        return self.board.group_of(self) or self.board.group_named(self.task["group"])
    def start_edit(self):
        if self.editing:
            return
        self.board.active_group = self.home_group()
        self.make_editor()
        self.editing = True
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.task["text"])
        self.editor.blockSignals(False)
        self.label.hide()
        # The due date / completed-date line stays visible while editing
        # (refresh()'s own visibility check already covers it; nothing
        # forces it hidden here any more).
        self.editor.show()
        self.board.relayout(animate=False)
        self.editor.setFocus()
        self.editor.go_end()
        self.update()
    def finish_edit(self, then=None):
        if not self.editing:
            return
        self.editing = False
        text = clean_task(self.editor.text())
        if text and text != self.task["text"]:
            # for the "undo puts this back in the editor" case below (a
            # real copy, so later in-place changes to self.task can't
            # reach back into it)
            old_task = self.board._task_copy(self.task)
            raw_text = text     # exactly as typed, before shortcuts strip it
            history_len = len(self.board.history)
            self.board.checkpoint()
            # Same shortcuts as adding a new task: a trailing due-date word
            # ("fri", "tomorrow", "eod", "15 oct"...) sets/updates the due
            # date, a trailing "!!"/"urgent" stars it, and a "#Group"/
            # "@Group" tag anywhere moves it to that group - all stripped
            # out of the text. Typing over the task without any of these
            # leaves its existing due date/star/group untouched.
            body, due, urgent, tag_group = parse_task_shortcuts(
                text, [g.name for g in self.board.groups])
            text = body
            if due:
                self.task["due"] = due
            if urgent:
                self.task["star"] = True
            self.task["text"] = text
            self.board.changed.emit()
            if tag_group and tag_group != self.task["group"]:
                current_group = self.board.group_of(self)
                target_group = self.board.group_named(tag_group)
                if current_group is not None and current_group is not target_group:
                    current_group.cards.remove(self)
                    target_group.cards.append(self)
                    self.task["group"] = target_group.name
            # Ctrl+Z right after committing this undoes only "pressing
            # Enter" - it reopens THIS task's editor with exactly what you
            # had typed (including the typo/shortcut word), and puts its
            # due/star/group back to how they were before the commit - the
            # same as if you'd never pressed Enter at all. So fixing a typo
            # never means retyping the whole task. Only recorded if
            # checkpoint() actually pushed something (it's a no-op on a
            # dead board).
            if len(self.board.history) > history_len:
                self.board.history[-1]["_reedit"] = {
                    "mode": "edit", "card": self, "old_task": old_task, "raw_text": raw_text}
        self.editor.hide()
        self.label.show()
        self.refresh()
        self.board.relayout(animate=True)
        group = self.home_group()
        self.board.active_group = group
        if then == "add":
            # Enter while editing -> straight to this group's "Add a task"
            self.board.clear_selection()
            self.board.focus_add(group)
        elif then == "board":
            self.board.setFocus()
    # ---------- painting ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        done = self.task["done"]
        gcol = self.board.colour_of(self.task["group"])
        if gcol:
            # Whole task tinted in its group colour
            t = TINT[0] * (0.5 if done else 1.0)
            if self.hover or self.dragging or self.editing:
                t += 0.08
            bg = mix(TINT_BASE, gcol, t)
            if self.selected and not self.dragging:
                bg = mix(bg, ACCENT, 0.18)
        elif self.dragging:
            bg = CARD_DRAG
        elif self.editing:
            bg = CARD_EDIT
        elif self.selected:
            bg = CARD_SELECTED
        elif self.hover:
            bg = CARD_DONE_HOVER if done else CARD_HOVER
        else:
            bg = CARD_DONE if done else CARD
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(qcolour(bg, alpha_of(gcol)))     # group colour may be see-through
        p.drawRoundedRect(rect, RADIUS, RADIUS)
        strip = self.urgency()
        if strip:
            clip = QPainterPath()
            clip.addRoundedRect(rect, RADIUS, RADIUS)
            p.save()
            p.setClipPath(clip)
            p.setBrush(QColor(strip))
            p.drawRect(QRectF(0, 0, 6 * S, self.height()))
            p.restore()
        if self.editing:
            p.setPen(QPen(QColor(ACCENT), 2))
            p.drawLine(QPointF(RADIUS, self.height() - 1),
                       QPointF(self.width() - RADIUS, self.height() - 1))
        elif self.selected and not self.dragging:
            p.setPen(QPen(QColor(ACCENT), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, RADIUS, RADIUS)
        if self.drop_hover:
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), RADIUS, RADIUS)
        # attachments
        col = QColor(TEXT_DONE if done else TEXT_SUB)
        fm = QFontMetrics(F(8))
        for i, (r, name) in enumerate(self.att_rects):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 40 if i == self.chip_hover else 20))
            p.drawRoundedRect(r, 4 * S, 4 * S)
            ix, iy = r.left() + 9 * S, r.center().y()
            p.setPen(QPen(col, 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            if is_location(name) and cached_isdir(name):
                # folder icon
                x0, y0 = ix - 5 * S, iy - 3.8 * S
                fold = QPainterPath()
                fold.moveTo(x0, y0)
                fold.lineTo(x0 + 3.6 * S, y0)
                fold.lineTo(x0 + 4.8 * S, y0 + 1.3 * S)
                fold.lineTo(x0 + 10 * S, y0 + 1.3 * S)
                fold.lineTo(x0 + 10 * S, y0 + 7.6 * S)
                fold.lineTo(x0, y0 + 7.6 * S)
                fold.closeSubpath()
                p.drawPath(fold)
            elif name.lower().endswith((".msg", ".eml")):
                box = QRectF(ix - 4.5 * S, iy - 3.2 * S, 9 * S, 6.4 * S)
                p.drawRect(box)
                env = QPainterPath()
                env.moveTo(box.topLeft())
                env.lineTo(ix, iy + 0.6 * S)
                env.lineTo(box.topRight())
                p.drawPath(env)
            else:
                p.drawRect(QRectF(ix - 3.5 * S, iy - 4.5 * S, 7 * S, 9 * S))
            p.setFont(F(8))
            p.setPen(col)
            text = fm.elidedText(display_name(name), Qt.ElideMiddle, int(r.width() - 24 * S))
            p.drawText(r.adjusted(18 * S, 0, -4 * S, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        extra = len(getattr(self.board, "drag_extra", [])) if self.dragging else 0
        if extra:
            txt = f"+{extra}"
            f = F(8, bold=True)
            bw = QFontMetrics(f).horizontalAdvance(txt) + 12 * S
            badge = QRectF(self.width() - STAR_W - bw - 2 * S, 5 * S, bw, 16 * S)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(badge, 8 * S, 8 * S)
            p.setFont(f)
            p.setPen(QColor("#1b1f22"))
            p.drawText(badge, Qt.AlignCenter, txt)
        # star (always shown when starred, outline on hover)
        starred = bool(self.task.get("star"))
        if starred or self.hover or self.selected:
            sx, sy = self.width() - STAR_W / 2 - 2 * S, self.cy
            path = star_path(sx, sy, 7 * S)
            if starred:
                c = QColor(TEXT_DONE if done else STAR_ON)
                p.setPen(QPen(c, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(c)
            else:
                c = QColor(TEXT if self.star_hover else TEXT_SUB)
                if not self.star_hover:
                    c.setAlpha(150)
                p.setPen(QPen(c, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        cx, cy, r = CX, self.cy, CR
        if done:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(CIRCLE_DONE))
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(QPen(QColor(bg), 1.7 * max(S, 0.8), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(check_path(cx, cy))
        else:
            ring = CIRCLE
            p.setPen(QPen(QColor(ring), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)
            if self.circle_hover:
                c = QColor(ring)
                c.setAlpha(170)
                p.setPen(QPen(c, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPath(check_path(cx, cy, 0.9))
    # ---------- mouse ----------
    def enterEvent(self, _):
        self.hover = True
        self.update()
    def leaveEvent(self, _):
        self.hover = False
        self.circle_hover = False
        self.chip_hover = -1
        self.star_hover = False
        self.link_hover = False
        self.update()
    def mouseMoveEvent(self, e):
        pos = e.position()
        over = self.in_circle(pos)
        chip = self.chip_at(pos)
        star = self.in_star(pos)
        link = bool(self.links) and not self.dragging and self.link_at(pos) is not None
        if (over, chip, star, link) != (self.circle_hover, self.chip_hover,
                                        self.star_hover, self.link_hover):
            self.circle_hover, self.chip_hover = over, chip
            self.star_hover, self.link_hover = star, link
            if not self.dragging:
                self.setCursor(Qt.PointingHandCursor if (over or chip >= 0 or star or link)
                               else Qt.ArrowCursor)
                tip = ""
                if chip >= 0 and is_location(self.att_rects[chip][1]):
                    tip = self.att_rects[chip][1] + "\nDouble-click to open"
                elif link or chip >= 0:
                    tip = "Double-click to open"
                self.setToolTip(tip)
            self.update()
        self.board.card_move(self, e)
    def mousePressEvent(self, e):
        self.board.card_press(self, e)
    def mouseReleaseEvent(self, e):
        self.board.card_release(self, e)
    def mouseDoubleClickEvent(self, e):
        # Double-click edits (double-clicking the circle does nothing extra)
        if e.button() != Qt.LeftButton or self.in_circle(e.position()):
            return
        if self.in_star(e.position()):
            self.board.toggle_star([self])          # second click of a fast double-click
            return
        link = self.link_at(e.position())
        if link:
            open_link(link, self.window())
            return
        chip = self.chip_at(e.position())
        if chip >= 0:
            open_attachment(self.att_rects[chip][1], self.window())
            return
        self.board.select_only(self)
        self.start_edit()
    def contextMenuEvent(self, e):
        chip = self.chip_at(e.pos())
        if chip >= 0:
            self.board.chip_menu(self, self.att_rects[chip][1], e.globalPos())
        else:
            self.board.card_menu(self, e.globalPos())
# ------------------------------------------------------------------
# ADD TASK LINE (one per group)
# ------------------------------------------------------------------
class AddRow(QWidget):
    def __init__(self, board, group):
        super().__init__(board)
        self.group = group
        self.board = board
        self.cy = MIN_H / 2
        self.edit = TextBox(self)
        self.edit.setPlaceholderText("Add a task")
        self.edit.focus_gained.connect(self.update)
        self.edit.focus_lost.connect(self.update)
        self.edit.textChanged.connect(self._changed)
        self.edit.paste_requested.connect(lambda m: self.board.paste_attachment_for(self.group, m))
        # Right-click: our own "Add task" + due-date menu instead of Qt's
        # built-in text-edit menu (Undo/Cut/Copy/Paste/...) - only shown if
        # something's actually been typed (see Board.add_row_menu).
        self.edit.menu_owner = lambda pos: self.board.add_row_menu(self, pos)
        self.setCursor(Qt.IBeamCursor)
        self.anim = make_anim(self)
        self._last_h = MIN_H
        self.drop_hover = False
    def apply_scale(self):
        self.edit.apply_scale()
        self.position_edit()
    def height_for(self, width):
        tw = max(width - TEXT_X - MARGIN, 40)
        return max(MIN_H, self.edit.content_height(tw) + CARD_PAD)
    def _changed(self):
        h = self.height_for(self.width())
        if h != self._last_h:
            self._last_h = h
            self.board.relayout(animate=False)
    def position_edit(self):
        tw = max(self.width() - TEXT_X - MARGIN, 40)
        eh = self.edit.content_height(tw)
        top = (self.height() - eh) // 2
        self.edit.setGeometry(TEXT_X, top, tw, eh)
        self.cy = first_line_cy(self.height(), top)
    def resizeEvent(self, _):
        self.position_edit()
    def mousePressEvent(self, _):
        self.edit.setFocus()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        focused = self.edit.hasFocus()
        p.setPen(Qt.NoPen)
        gcol = self.group.colour
        if gcol:
            p.setBrush(qcolour(mix(TINT_BASE, gcol, TINT[0] * (0.66 if focused else 0.5)),
                               alpha_of(gcol)))
        else:
            p.setBrush(QColor(ENTRY_FOCUS if focused else ENTRY_BG))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                          RADIUS, RADIUS)
        cx, cy = CX, self.cy
        if focused:
            p.setPen(QPen(QColor(CIRCLE), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), CR, CR)
            p.setPen(QPen(QColor(ACCENT), 2))
            p.drawLine(QPointF(RADIUS, self.height() - 1),
                       QPointF(self.width() - RADIUS, self.height() - 1))
        else:
            a = 6 * S
            p.setPen(QPen(QColor(ACCENT), 1.5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - a, cy), QPointF(cx + a, cy))
            p.drawLine(QPointF(cx, cy - a), QPointF(cx, cy + a))
        if self.drop_hover:
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), RADIUS, RADIUS)
# ------------------------------------------------------------------
# GROUP HEADING
# ------------------------------------------------------------------
class GroupHeader(QWidget):
    def __init__(self, board, group):
        super().__init__(board)
        self.board = board
        self.group = group
        self.hover = False
        self.renaming = False
        self.dragging = False
        self.drop_hover = False
        self.press = None
        self.last_press = (0.0, QPoint())
        self.setCursor(Qt.PointingHandCursor)
        self.editor = LineEdit(self, 11, bold=True)
        self.editor.hide()
        self.editor.returnPressed.connect(self.finish_rename)
        self.editor.escaped.connect(lambda: self.finish_rename(cancel=True))
        self.editor.undo_requested.connect(
            lambda: (self.finish_rename(cancel=True, refocus=False),
                     self.board.undo_requested.emit()))
        self.editor.focus_lost.connect(lambda: self.finish_rename(refocus=False))
        self.anim = make_anim(self)
        self.apply_scale()
    def apply_scale(self):
        self.font_ = F(11, bold=True)
        self.count_font = F(9)
        self.editor.apply_scale()
        self.position_edit()
    def position_edit(self):
        eh = line_edit_height(self.editor)
        x = int(4 * S) + ARROW_W - 2
        self.editor.setGeometry(x, (self.height() - eh) // 2,
                                self.width() - x - int(4 * S), eh)
    def in_arrow(self, pos):
        return pos.x() < int(4 * S) + ARROW_W
    def resizeEvent(self, _):
        self.position_edit()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        if self.renaming:
            p.setBrush(QColor(ENTRY_FOCUS))
            p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
            p.setPen(QPen(QColor(ACCENT), 2))
            p.drawLine(QPointF(RADIUS, self.height() - 1),
                       QPointF(self.width() - RADIUS, self.height() - 1))
            return
        colour = self.group.colour
        if colour:
            t = min(1.0, TINT[0] * (1.3 if (self.hover or self.dragging) else 1.15))
            p.setBrush(qcolour(mix(TINT_BASE, colour, t), alpha_of(colour)))
            p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        elif self.dragging:
            p.setBrush(QColor(CARD_DRAG))
            p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        elif self.hover:
            p.setBrush(QColor(255, 255, 255, 18))
            p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        if self.group.name != GENERAL and (self.hover or self.dragging):
            p.setBrush(QColor(TEXT_SUB))
            gx, gy = self.width() - 14 * S, self.height() / 2
            for dx in (-3, 3):
                for dy in (-5, 0, 5):
                    p.drawEllipse(QPointF(gx + dx * S, gy + dy * S), 1.2 * S, 1.2 * S)
        if self.drop_hover:
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), RADIUS, RADIUS)
        # collapse arrow
        ax, ay, a = int(4 * S) + 9 * S, self.height() / 2, 3.5 * S
        p.setPen(QPen(QColor(TEXT if colour else TEXT_SUB), 1.5,
                      Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        arrow = QPainterPath()
        if self.group.folded:
            arrow.moveTo(ax - a / 2, ay - a)
            arrow.lineTo(ax + a / 2, ay)
            arrow.lineTo(ax - a / 2, ay + a)
        else:
            arrow.moveTo(ax - a, ay - a / 2)
            arrow.lineTo(ax, ay + a / 2)
            arrow.lineTo(ax + a, ay - a / 2)
        p.drawPath(arrow)
        pad = int(4 * S) + ARROW_W
        name, nw, _ = self._name_layout()
        p.setFont(self.font_)
        p.setPen(QColor(TEXT))
        p.drawText(self.rect().adjusted(pad, 0, 0, 0),
                   Qt.AlignVCenter | Qt.AlignLeft, name)
        n = len(self.group.cards)
        if n:
            p.setFont(self.count_font)
            p.setPen(QColor(TEXT if colour else TEXT_SUB))
            x = pad + nw + int(8 * S)
            p.drawText(self.rect().adjusted(x, 0, 0, 0),
                       Qt.AlignVCenter | Qt.AlignLeft, str(n))
            late = self.group.overdue()
            if late:
                # small red pill: how many are overdue
                x += QFontMetrics(self.count_font).horizontalAdvance(str(n)) + int(7 * S)
                txt = f"{late} overdue"
                f = F(7.5, bold=True)
                bw = QFontMetrics(f).horizontalAdvance(txt) + 12 * S
                bh = 15 * S
                badge = QRectF(x, (self.height() - bh) / 2, bw, bh)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(OVERDUE))
                p.drawRoundedRect(badge, bh / 2, bh / 2)
                p.setFont(f)
                p.setPen(QColor("#1b1f22"))
                p.drawText(badge, Qt.AlignCenter, txt)
    def enterEvent(self, _):
        self.hover = True
        self.update()
    def leaveEvent(self, _):
        self.hover = False
        self.update()
    def mousePressEvent(self, e):
        self.board.setFocus()
        self.board.clear_selection()
        if e.button() == Qt.LeftButton:
            self.press = (e.globalPosition().toPoint(), int(e.position().y()))
            self.last_press = (time.monotonic(), e.globalPosition().toPoint())
    def _name_layout(self):
        """(name as shown, its width, width of what follows it). A long
        name is cut short with '…' so the task count and overdue badge
        after it, and the drag grip, always stay visible."""
        n = len(self.group.cards)
        extras = 0
        if n:
            extras = int(8 * S) + QFontMetrics(self.count_font).horizontalAdvance(str(n))
            late = self.group.overdue()
            if late:
                extras += int(7 * S) + int(QFontMetrics(F(7.5, bold=True)).horizontalAdvance(
                    f"{late} overdue") + 12 * S)
        room = self.width() - (int(4 * S) + ARROW_W) - extras - int(28 * S)
        fm = QFontMetrics(self.font_)
        name = fm.elidedText(self.group.name, Qt.ElideRight, max(0, room))
        return name, fm.horizontalAdvance(name), extras
    def on_name(self, pos):
        pad = int(4 * S) + ARROW_W
        nw = self._name_layout()[1]
        return pad - 4 * S <= pos.x() <= pad + nw + 6 * S
    def mouseMoveEvent(self, e):
        if not self.press or not (e.buttons() & Qt.LeftButton):
            return
        if self.group.name == GENERAL:
            return
        gpos = e.globalPosition().toPoint()
        if not self.dragging:
            if (gpos - self.press[0]).manhattanLength() < 6:
                return
            self.board.start_group_drag(self.group, self.press[1])
        self.board.update_group_drag(gpos)
    def mouseReleaseEvent(self, e):
        press, self.press = self.press, None
        if self.dragging:
            self.board.end_group_drag()
        elif press and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            # Plain click anywhere on the heading opens / closes the group
            self.board.toggle_fold(self.group)
    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        t0, p0 = self.last_press
        quick = (time.monotonic() - t0 < 0.3 and
                 (e.globalPosition().toPoint() - p0).manhattanLength() <= 4)
        if (self.group.name == GENERAL or not quick or
                not self.on_name(e.position())):
            # Treat it as an ordinary click (open / close on release)
            self.press = (e.globalPosition().toPoint(), int(e.position().y()))
            self.last_press = (time.monotonic(), e.globalPosition().toPoint())
            return
        # Double-click the name = rename: undo the first click's open/close
        self.board.toggle_fold(self.group)
        self.start_rename()
    def contextMenuEvent(self, e):
        self.board.group_menu(self.group, e.globalPos())
    def start_rename(self):
        if self.group.name == GENERAL:
            return
        if self.group.folded:
            self.board.toggle_fold(self.group)
        self.renaming = True
        self.editor.setText(self.group.name)
        self.editor.show()
        self.editor.setFocus()
        self.editor.selectAll()
        self.update()
    def finish_rename(self, cancel=False, refocus=True):
        if not self.renaming:
            return
        self.renaming = False
        self.editor.hide()
        if not cancel:
            self.board.rename_group(self.group, self.editor.text())
        self.update()
        if refocus:
            if self.group.folded:
                self.board.setFocus()
            else:
                self.group.add_row.edit.setFocus()
# ------------------------------------------------------------------
# PILL BUTTONS ("New group", "Completed")
# ------------------------------------------------------------------
class PillButton(QWidget):
    clicked = Signal()
    def __init__(self, board, text, chevron=False, transparent=False, big=False):
        super().__init__(board)
        self.big = big
        self.text = text
        self.chevron = chevron
        self.collapsed = False
        self.transparent = transparent
        self.hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.anim = make_anim(self)
        self.apply_scale()
    def apply_scale(self):
        if self.big:
            # Matches the group headings: same font, icon under the arrows
            self.font_ = F(11, bold=True)
            self.icon_x = int(4 * S) + 9 * S
            self.text_x = int(4 * S) + ARROW_W
            self.h = HEAD_H
        else:
            self.font_ = F(9, bold=True)
            self.icon_x = 15.0 * S
            self.text_x = int(30 * S)
            self.h = PILL_H
        self.set_text(self.text)
    def set_text(self, text):
        self.text = text
        fm = QFontMetrics(self.font_)
        self.resize(self.text_x + fm.horizontalAdvance(text) + int(12 * S), self.h)
        self.update()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        if self.transparent:
            if self.hover:
                p.setBrush(QColor(255, 255, 255, 22))
                p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        else:
            p.setBrush(QColor(PILL_HOVER if self.hover else PILL))
            p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        cx, cy = self.icon_x, self.height() / 2
        a = 3.5 * S if self.big else 4.5 * S
        p.setPen(QPen(QColor(TEXT), 1.5 if self.big else 1.4,
                      Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath()
        if self.chevron and self.collapsed:
            path.moveTo(cx - a / 2, cy - a)
            path.lineTo(cx + a / 2, cy)
            path.lineTo(cx - a / 2, cy + a)
            p.drawPath(path)
        elif self.chevron:
            path.moveTo(cx - a, cy - a / 2)
            path.lineTo(cx, cy + a / 2)
            path.lineTo(cx + a, cy - a / 2)
            p.drawPath(path)
        else:
            p.drawLine(QPointF(cx - a * 1.2, cy), QPointF(cx + a * 1.2, cy))
            p.drawLine(QPointF(cx, cy - a * 1.2), QPointF(cx, cy + a * 1.2))
        p.setFont(self.font_)
        p.setPen(QColor(TEXT))
        p.drawText(self.rect().adjusted(self.text_x, 0, 0, 0),
                   Qt.AlignVCenter | Qt.AlignLeft, self.text)
    def enterEvent(self, _):
        self.hover = True
        self.update()
    def leaveEvent(self, _):
        self.hover = False
        self.update()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
    def contextMenuEvent(self, e):
        if self.chevron:
            self.parent().done_menu(e.globalPos())
# ------------------------------------------------------------------
# GROUP
# ------------------------------------------------------------------
class Group:
    def __init__(self, board, name):
        self.name = name
        self.cards = []
        self.folded = False
        self.colour = None
        self.header = GroupHeader(board, self)
        self.add_row = AddRow(board, self)
        self.add_row.edit.submitted.connect(lambda: board.add_task(self))
        self.add_row.edit.escaped.connect(board.setFocus)
        self.add_row.edit.focus_gained.connect(lambda: board.add_focused(self))
        self.add_row.edit.undo_requested.connect(lambda: board.undo_requested.emit())
    def overdue(self):
        today = date.today()
        return sum(1 for c in self.cards
                   if c.task.get("due") and parse_due(c.task["due"])
                   and parse_due(c.task["due"]) < today)
# ------------------------------------------------------------------
# BOARD
# ------------------------------------------------------------------
class OutlookFetchThread(QThread):
    """Runs save_outlook_items() off the Qt UI thread, so dragging/pasting
    several Outlook emails or attachments never freezes the list. Never
    touches a Qt widget itself - only emits the result back to the main
    thread through a signal."""
    done = Signal(int, list, list)      # request_id, saved_paths, failed_names
    def __init__(self, names, request_id, parent=None):
        super().__init__(parent)
        self.names = list(names)
        self.request_id = request_id
    def run(self):
        try:
            saved, failed = save_outlook_items(self.names)
        except Exception as exc:
            saved, failed = [], list(self.names)
            log_error("Outlook extraction thread failed", exc)
        self.done.emit(self.request_id, saved, failed)
class Board(QWidget):
    changed = Signal()
    undo_requested = Signal()
    def __init__(self, data, scroll, history):
        super().__init__()
        self.history = history
        self.dead = False
        self._drag_snap = None
        self.setObjectName("board")
        self.scroll = scroll
        self.setFocusPolicy(Qt.ClickFocus)
        self.collapsed = data["collapsed"]
        self.groups = []
        self.done_cards = []
        self.selected = set()
        self.anchor = None
        self.kb_cursor = None      # where Up/Down moves on from
        self.press = None
        self.drag = None
        self.slots = {}
        self.regions = []
        self._press_offset = 0
        self.gdrag = None
        self.gdrag_parts = []
        self.gdrag_offset = 0
        self.drop_target = None
        self.setAcceptDrops(True)
        # A persistent, ever-increasing tie-breaker for the star-sort below
        # (relayout()) - kept on each card as card._order. Unlike physical
        # list position, this never gets rewritten by the star sort itself,
        # so starring and then unstarring a task restores its original place
        # among the other non-starred tasks instead of leaving it wherever
        # the star sort last moved it to.
        self._order_seq = 0
        folded = data.get("folded") or set()
        colours = data.get("colours") or {}
        for name, tasks in data["groups"]:
            g = self.create_group(name)
            g.folded = name in folded
            g.colour = colours.get(name)
            g.cards = [TaskCard(self, dict(t)) for t in tasks]
        self.done_cards = [TaskCard(self, dict(t)) for t in data["done"]]
        self.active_group = self.groups[0]
        self.new_group_btn = PillButton(self, "New group", transparent=True, big=True)
        self.new_group_btn.clicked.connect(self.new_group)
        self.done_header = PillButton(self, "Completed", chevron=True)
        self.done_header.clicked.connect(self.toggle_collapsed)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setInterval(16)
        self.scroll_timer.timeout.connect(self.auto_scroll)
        self._outlook_requests = {}      # request id -> {"target": ..., "thread": ...}
        self._outlook_req_seq = 0
    # ---------- data ----------
    def next_order_seq(self):
        self._order_seq += 1
        return self._order_seq
    def _renumber(self, group):
        """Rebases a group's star-sort tie-breaker onto its current physical
        order - used only after an explicit drag reorder, so the new
        arrangement the user dragged into becomes the baseline order (star
        toggling never calls this, so it can never disturb that baseline)."""
        for i, c in enumerate(group.cards):
            c._order = i
    def create_group(self, name):
        g = Group(self, name)
        self.groups.append(g)
        return g
    def group_named(self, name):
        return next((g for g in self.groups if g.name == name), self.groups[0])
    def group_of(self, card):
        return next((g for g in self.groups if card in g.cards), None)
    def open_cards(self):
        return [c for g in self.groups for c in g.cards]
    def all_cards(self):
        return self.open_cards() + self.done_cards
    def visible_cards(self):
        shown = [c for g in self.groups if not g.folded for c in g.cards]
        return shown + ([] if self.collapsed else self.done_cards)
    def folded_names(self):
        return [g.name for g in self.groups if g.folded]
    def colours(self):
        return {g.name: g.colour for g in self.groups if g.colour}
    def colour_of(self, name):
        for g in self.groups:
            if g.name == name:
                return g.colour
        return None
    def export(self):
        groups = [(g.name, [c.task for c in g.cards]) for g in self.groups]
        return groups, [c.task for c in self.done_cards]
    # ---------- undo ----------
    @staticmethod
    def _task_copy(task):
        """A copy that later in-place changes (e.g. to a task's files list)
        can never reach back into - keeps every undo snapshot independent."""
        t = dict(task)
        if "files" in t:
            t["files"] = list(t["files"])
        return t
    def snapshot(self):
        return {"groups": [(g.name, [self._task_copy(c.task) for c in g.cards])
                           for g in self.groups],
                "done": [self._task_copy(c.task) for c in self.done_cards],
                "collapsed": self.collapsed,
                "folded": set(self.folded_names()),
                "colours": self.colours()}
    def checkpoint(self, snap=None):
        """Call before any change so Ctrl+Z can go back to it."""
        if self.dead:
            return
        self.history.append(snap if snap is not None else self.snapshot())
        del self.history[:-UNDO_LIMIT]
    # ---------- scaling ----------
    def rescale(self):
        for g in self.groups:
            g.header.apply_scale()
            g.add_row.apply_scale()
        for c in self.all_cards():
            c.apply_scale()
        self.new_group_btn.apply_scale()
        self.done_header.apply_scale()
        self.relayout(animate=False)
    # ---------- layout ----------
    def place(self, widget, x, y, animate):
        target = QPoint(int(x), int(y))
        running = widget.anim.state() == QAbstractAnimation.State.Running
        if animate and widget.isVisible() and widget.pos() != target:
            widget.anim.stop()
            widget.anim.setStartValue(widget.pos())
            widget.anim.setEndValue(target)
            widget.anim.start()
        elif widget.pos() != target or running:
            widget.anim.stop()
            widget.move(target)
    def relayout(self, animate=True):
        width = self.scroll.viewport().width()
        if width < 100:
            width = self.width() if self.width() > 100 else DEFAULT_SIZE[0]
        cw = max(width - 2 * MARGIN, 120)
        x, y = MARGIN, TOP_PAD
        self.slots, self.regions = {}, []
        for g in self.groups:
            # Starred first; ties break on the persistent _order (not
            # physical position), so unstarring a task puts it back where
            # it was rather than leaving it at the front where the star
            # sort last moved it to.
            g.cards.sort(key=lambda c: (not c.task.get("star"), c._order))
            top = y
            moving = g is self.gdrag
            if moving:
                self.gdrag_parts = []
            def put(w, yy, g_top=top, moving=moving):
                if moving:
                    self.gdrag_parts.append((w, yy - g_top))
                else:
                    self.place(w, x, yy, animate)
            g.header.resize(cw, HEAD_H)
            put(g.header, y)
            g.header.show()
            g.header.update()
            y += HEAD_H + GAP
            if g.folded:
                for c in g.cards:
                    if c is not self.drag:
                        c.hide()
                g.add_row.hide()
                y -= GAP
                self.regions.append((g, top, y))
                y += GAP * 2
                continue
            for c in g.cards:
                h = c.height_for(cw)
                c.apply_size(cw, h)
                self.slots[c] = y
                if c is not self.drag:
                    put(c, y)
                c.show()
                y += h + GAP
            ah = g.add_row.height_for(cw)
            g.add_row._last_h = ah
            g.add_row.resize(cw, ah)
            put(g.add_row, y)
            g.add_row.show()
            y += ah
            self.regions.append((g, top, y))
            y += GROUP_GAP
        last_folded = self.groups[-1].folded
        y -= (GAP * 2 if last_folded else GROUP_GAP) - (GAP * 2 if last_folded else GAP * 3)
        self.place(self.new_group_btn, x, y, animate)
        self.new_group_btn.show()
        y += self.new_group_btn.height() + GROUP_GAP
        if self.done_cards:
            self.done_header.collapsed = self.collapsed
            self.done_header.set_text(f"Completed   {len(self.done_cards)}")
            self.place(self.done_header, x, y, animate and self.done_header.isVisible())
            self.done_header.show()
            y += self.done_header.height() + GAP * 2
            for c in self.done_cards:
                h = c.height_for(cw)
                c.apply_size(cw, h)
                if self.collapsed:
                    c.hide()
                    continue
                self.place(c, x, y, animate and not c.isHidden())
                c.show()
                y += h + GAP
        else:
            self.done_header.hide()
        if self.drag:
            self.drag.raise_()
        for w, _ in self.gdrag_parts if self.gdrag else []:
            w.raise_()
        self.setMinimumHeight(y + MARGIN * 2)
    def resizeEvent(self, e):
        if e.oldSize().width() != e.size().width():
            self.relayout(animate=False)
    # ---------- selection ----------
    def refresh_selection(self):
        for c in self.all_cards():
            sel = id(c) in self.selected
            if c.selected != sel:
                c.selected = sel
                c.update()
    def select_only(self, card):
        self.selected = {id(card)}
        self.anchor = card
        self.refresh_selection()
    def clear_selection(self):
        if self.selected:
            self.selected.clear()
            self.refresh_selection()
    def selected_cards(self):
        return [c for c in self.all_cards() if id(c) in self.selected]
    def move_selection(self, step, extend=False):
        """Up/Down: select the task above/below (in the order shown, across
        groups, skipping folded ones). Shift+Up/Down grows or shrinks the
        selection from where it started. Nothing selected yet: Down picks
        the first task, Up the last."""
        order = self.visible_cards()
        if not order:
            return
        cursor = self.kb_cursor if self.kb_cursor in order and id(self.kb_cursor) in \
            self.selected else None
        if cursor is None:
            picked = [c for c in order if id(c) in self.selected]
            if picked:
                cursor = picked[0] if step < 0 else picked[-1]
        if cursor is None:
            target = order[0] if step > 0 else order[-1]
        else:
            target = order[max(0, min(len(order) - 1, order.index(cursor) + step))]
        if extend and self.anchor in order:
            a, b = sorted((order.index(self.anchor), order.index(target)))
            self.selected = {id(c) for c in order[a:b + 1]}
            self.refresh_selection()
        else:
            self.select_only(target)
        self.kb_cursor = target
        self.active_group = target.home_group() or self.active_group
        self.scroll.ensureWidgetVisible(target, 0, int(20 * S))
    # ---------- mouse on cards ----------
    def card_press(self, card, e):
        if e.button() != Qt.LeftButton:
            return
        self.setFocus()
        self.active_group = card.home_group()
        self._press_offset = int(e.position().y())
        ctrl = bool(e.modifiers() & Qt.ControlModifier)
        shift = bool(e.modifiers() & Qt.ShiftModifier)
        if not ctrl and not shift and card.in_circle(e.position()):
            self.press = None
            self.set_done([card], not card.task["done"])
            return
        if not ctrl and not shift and card.in_star(e.position()):
            self.press = None
            self.toggle_star([card])
            return
        pending = False
        order = self.visible_cards()
        if shift and self.anchor in order:
            a, b = order.index(self.anchor), order.index(card)
            if a > b:
                a, b = b, a
            if not ctrl:
                self.selected.clear()
            self.selected.update(id(c) for c in order[a:b + 1])
        elif ctrl:
            self.selected ^= {id(card)}
            self.anchor = card
        else:
            if id(card) in self.selected and len(self.selected) > 1:
                pending = True
            else:
                self.selected = {id(card)}
            self.anchor = card
        self.kb_cursor = card
        self.refresh_selection()
        self.press = {
            "card": card,
            "start": e.globalPosition().toPoint(),
            "plain": not (ctrl or shift),
            "can_drag": not (ctrl or shift) and not card.task["done"],
            "pending": pending,
        }
    def card_move(self, card, e):
        if not self.press or not (e.buttons() & Qt.LeftButton):
            return
        if self.drag is None:
            if not self.press["can_drag"]:
                return
            if (e.globalPosition().toPoint() - self.press["start"]).manhattanLength() < 6:
                return
            self.start_drag(self.press["card"])
        self.update_drag(e.globalPosition().toPoint())
    def card_release(self, card, e):
        press, self.press = self.press, None
        if self.drag is not None:
            self.end_drag()
            return
        if not press:
            return
        if press["pending"]:
            self.select_only(press["card"])
    # ---------- dragging tasks ----------
    def start_drag(self, card):
        self._drag_snap = self.snapshot()
        self.drag = card
        # Other selected (open) tasks come along: tucked away while dragging,
        # dropped in right under the one you're holding
        self.drag_extra = [c for c in self.selected_cards()
                           if c is not card and not c.task["done"]]
        for c in self.drag_extra:
            g = self.group_of(c)
            if g:
                g.cards.remove(c)
            c.hide()
        if not self.drag_extra:
            self.select_only(card)
        card.dragging = True
        card.anim.stop()
        card.raise_()
        card.setGraphicsEffect(shadow_for(card))
        card.setCursor(Qt.ClosedHandCursor)
        card.update()
        self.scroll_timer.start()
    def update_drag(self, global_pos):
        card = self.drag
        if card is None or not self.regions:
            return
        first_top = self.regions[0][1]
        last_bottom = self.regions[-1][2]
        mouse_y = self.mapFromGlobal(global_pos).y()
        y = mouse_y - self._press_offset
        y = max(first_top, min(y, last_bottom - card.height()))
        card.move(MARGIN, y)
        # Drop position follows the mouse pointer, so tall tasks can reach
        # the first and last spots too
        centre = max(first_top, min(mouse_y, last_bottom))
        target_group, best = None, None
        for g, top, bottom in self.regions:
            d = 0 if top <= centre <= bottom else min(abs(centre - top), abs(centre - bottom))
            if best is None or d < best:
                best, target_group = d, g
        others = [c for c in target_group.cards if c is not card]
        if target_group.folded:
            index = len(others)
        else:
            index = sum(1 for c in others
                        if c in self.slots and self.slots[c] + c.height() / 2 < centre)
        # starred tasks stay above the rest
        n_star = sum(1 for c in others if c.task.get("star"))
        index = min(index, n_star) if card.task.get("star") else max(index, n_star)
        current = self.group_of(card)
        if current is not target_group or current.cards.index(card) != index:
            current.cards.remove(card)
            target_group.cards.insert(index, card)
            card.task["group"] = target_group.name
            # This is an explicit manual reorder - rebase the tie-breaker
            # order onto it now, so it sticks (and so a later star toggle
            # restores THIS arrangement, not whatever came before it).
            self._renumber(target_group)
            if current is not target_group:
                self._renumber(current)
            card.update()
            self.relayout(animate=True)
    def end_drag(self):
        card = self.drag
        self.drag = None
        self._drag_snap_saved = None
        if getattr(self, "drag_extra", []):
            self._drag_snap_saved = self._drag_snap      # always a change when several move
        elif self._drag_snap is not None and self.snapshot() != self._drag_snap:
            self.checkpoint(self._drag_snap)
        self._drag_snap = None
        self.scroll_timer.stop()
        card.dragging = False
        card.setCursor(Qt.ArrowCursor)
        extra, self.drag_extra = getattr(self, "drag_extra", []), []
        if extra:
            g = self.group_of(card)
            i = g.cards.index(card) + 1
            for c in extra:
                c.task["group"] = g.name
                g.cards.insert(i, c)
                i += 1
                c.move(card.pos())
                c.refresh()
            self._renumber(g)     # manual reorder - rebase the tie-breaker order
            if self._drag_snap_saved is not None and not self.history[-1:] == [self._drag_snap_saved]:
                self.checkpoint(self._drag_snap_saved)
        self.relayout(animate=True)
        for c in extra:
            c.show()
            c.stackUnder(card)
        def drop_shadow():
            if not card.dragging:
                card.setGraphicsEffect(None)
                card.update()
        QTimer.singleShot(ANIM_MS + 20, card, drop_shadow)
        card.update()
        self.changed.emit()
    # ---------- dragging whole groups ----------
    def start_group_drag(self, group, offset):
        self._drag_snap = self.snapshot()
        self.gdrag = group
        self.gdrag_offset = offset
        group.header.dragging = True
        focus = QApplication.focusWidget()
        if focus is not None and focus is not self:
            focus.clearFocus()
        self.relayout(animate=False)
        for w, _ in self.gdrag_parts:
            w.anim.stop()
            w.raise_()
        group.header.setGraphicsEffect(shadow_for(group.header))
        group.header.setCursor(Qt.ClosedHandCursor)
        group.header.update()
        self.scroll_timer.start()
    def _set_group_drop_tab(self, win, tabid):
        prev = getattr(self, "_group_drop_target", None)
        if prev == (win, tabid):
            return
        if prev and prev[0] is not None:
            chip = prev[0].tabbar.chips.get(prev[1])
            if chip:
                chip.drop_hover = False
                chip.update()
        self._group_drop_target = (win, tabid)
        if win is not None:
            chip = win.tabbar.chips.get(tabid)
            if chip:
                chip.drop_hover = True
                chip.update()
    def update_group_drag(self, global_pos):
        g = self.gdrag
        if g is None:
            return
        win = self.window()
        target_win, target_tabid = tab_chip_at_global_pos(
            global_pos, exclude=(win, getattr(win, "active_tab", None)))
        self._set_group_drop_tab(target_win, target_tabid)
        if target_win is not None:
            return          # hovering a tab to drop onto - no in-board repositioning
        mouse_y = self.mapFromGlobal(global_pos).y()
        general_bottom = self.regions[0][2] + GROUP_GAP
        top = max(general_bottom, mouse_y - self.gdrag_offset)
        for w, dy in self.gdrag_parts:
            w.move(MARGIN, top + dy)
        # General always stays first
        others = [(og, t, b) for og, t, b in self.regions[1:] if og is not g]
        index = 1 + sum(1 for _, t, b in others if (t + b) / 2 < mouse_y)
        if self.groups.index(g) != index:
            self.groups.remove(g)
            self.groups.insert(index, g)
            self.relayout(animate=True)
            for w, dy in self.gdrag_parts:
                w.move(MARGIN, top + dy)
    def end_group_drag(self):
        g = self.gdrag
        if g is None:
            return
        self.gdrag = None
        self.gdrag_parts = []
        target = getattr(self, "_group_drop_target", None)
        self._set_group_drop_tab(None, None)
        self.scroll_timer.stop()
        g.header.dragging = False
        g.header.setCursor(Qt.ArrowCursor)
        if target and target[0] is not None:
            self._drag_snap = None       # moving away - no in-board undo snapshot needed
            self._move_group_to_tab(g, *target)
            return
        if self._drag_snap is not None and self.snapshot() != self._drag_snap:
            self.checkpoint(self._drag_snap)
        self._drag_snap = None
        self.relayout(animate=True)
        def drop_shadow():
            if not g.header.dragging:
                g.header.setGraphicsEffect(None)
                g.header.update()
        QTimer.singleShot(ANIM_MS + 20, g.header, drop_shadow)
        g.header.update()
        self.changed.emit()
    def _move_group_to_tab(self, group, target_win, target_tabid):
        """Moves a WHOLE group - its tasks, colour, folded state - out of
        this board into a different tab, in this window or another one.
        (General can never be dragged at all, enforced in GroupHeader, so
        this only ever applies to a named, deletable group.)"""
        self.checkpoint()
        self.groups.remove(group)
        for w in (group.header, group.add_row):
            w.hide()
            w.deleteLater()
        if self.active_group is group:
            self.active_group = self.groups[0]
        tasks = [dict(c.task) for c in group.cards]
        colour, folded, name = group.colour, group.folded, group.name
        self.relayout(animate=True)
        self.changed.emit()
        if target_win.active_tab == target_tabid:
            target_win.board.receive_group(name, tasks, colour, folded)
        else:
            data = target_win.tab_data.get(target_tabid)
            if data is None:
                meta = target_win.tab_meta[target_tabid]
                data = _empty_tab(meta["name"], meta["colour"])
                target_win.tab_data[target_tabid] = data
            new_name = _unique_group_name(name, [gn for gn, _ in data["groups"]])
            for t in tasks:
                t["group"] = new_name
            data["groups"].append([new_name, tasks])
            if folded:
                data["folded"].add(new_name)
            if colour:
                data["colours"][new_name] = colour
            target_win.tabbar.update()
        global_save()
    def receive_group(self, name, tasks, colour, folded):
        """The other side of _move_group_to_tab(): adds a whole group
        (dragged in from another tab, possibly another window) to this
        currently-active board."""
        self.checkpoint()
        new_name = _unique_group_name(name, [g.name for g in self.groups])
        g = self.create_group(new_name)
        g.colour = colour
        g.folded = folded
        for t in tasks:
            t = dict(t)
            t["group"] = new_name
            card = TaskCard(self, t)
            g.cards.append(card)
        self.relayout(animate=True)
        for c in g.cards:
            c.show()
        self.changed.emit()
    # ---------- auto scroll while dragging ----------
    def auto_scroll(self):
        if self.gdrag is not None:
            self._edge_scroll(self.update_group_drag)
        elif self.drag is not None:
            self._edge_scroll(self.update_drag)
        else:
            self.scroll_timer.stop()
    def _edge_scroll(self, update):
        vp = self.scroll.viewport()
        pos = vp.mapFromGlobal(QCursor.pos())
        bar = self.scroll.verticalScrollBar()
        edge, step = 40, 0
        if pos.y() < edge:
            step = -max(2, (edge - pos.y()) // 3)
        elif pos.y() > vp.height() - edge:
            step = max(2, (pos.y() - vp.height() + edge) // 3)
        if step:
            bar.setValue(bar.value() + step)
            update(QCursor.pos())
    # ---------- empty area ----------
    def mousePressEvent(self, e):
        self.setFocus()
        if not (e.modifiers() & Qt.ControlModifier):
            self.clear_selection()
    # ---------- collapsing groups ----------
    def toggle_fold(self, group):
        group.folded = not group.folded
        if group.folded:
            ids = {id(c) for c in group.cards}
            if self.selected & ids:
                self.selected -= ids
                self.refresh_selection()
            if group.add_row.edit.hasFocus():
                self.setFocus()
        self.relayout(animate=True)
        group.header.update()
        self.changed.emit()
    def focus_add(self, group):
        if group.folded:
            self.toggle_fold(group)
        group.add_row.edit.setFocus()
    # ---------- dropping emails / files ----------
    def _drop_hit(self, pos):
        for c in self.visible_cards():
            if c.isVisible() and c.geometry().contains(pos):
                return c
        best, dist = None, None
        for g, top, bottom in self.regions:
            d = 0 if top <= pos.y() <= bottom else min(abs(pos.y() - top), abs(pos.y() - bottom))
            if dist is None or d < dist:
                dist, best = d, g
        return best
    def _set_drop(self, target):
        if target is self.drop_target:
            return
        for t, on in ((self.drop_target, False), (target, True)):
            if isinstance(t, TaskCard):
                t.drop_hover = on
                t.update()
            elif isinstance(t, Group):
                w = t.header if t.folded else t.add_row
                t.header.drop_hover = on and t.folded
                t.add_row.drop_hover = on and not t.folded
                w.update()
        self.drop_target = target
    def dragEnterEvent(self, e):
        if can_accept_drop(e.mimeData()):
            e.setDropAction(Qt.CopyAction)      # never let Outlook move the email
            e.accept()
            self._set_drop(self._drop_hit(e.position().toPoint()))
        else:
            e.ignore()
    def dragMoveEvent(self, e):
        if can_accept_drop(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self._set_drop(self._drop_hit(e.position().toPoint()))
        else:
            e.ignore()
    def dragLeaveEvent(self, e):
        self._set_drop(None)
    def dropEvent(self, e):
        mime = e.mimeData()
        target = self._drop_hit(e.position().toPoint())
        self._set_drop(None)
        e.setDropAction(Qt.CopyAction)      # never let Outlook move the original
        e.accept()
        if target is None:
            return
        if mime.hasUrls() and any(u.isLocalFile() for u in mime.urls()):
            # Explorer files/folders: dragging always links the existing
            # location - nothing is copied, whether it's a file or a folder.
            paths = []
            for u in mime.urls():
                p = u.toLocalFile()
                if p and (os.path.isdir(p) or os.path.isfile(p)):
                    paths.append(os.path.normpath(p))
            if paths:
                self.attach_files(target, paths)
            return
        self._handle_outlook_mime(target, mime, "dropped")
    # ---------- pasting emails / files (Ctrl+V) ----------
    def paste_attachment(self, mime):
        """Ctrl+V while the board (not a text editor) has focus: paste onto
        the one selected task, or into the active group."""
        sel = self.selected_cards()
        target = sel[0] if len(sel) == 1 else self.active_group
        self.paste_attachment_for(target, mime)
    def paste_attachment_for(self, target, mime):
        if target is None or mime is None:
            return
        if mime.hasUrls() and any(u.isLocalFile() for u in mime.urls()):
            self._paste_explorer_urls(target, mime)
            return
        self._handle_outlook_mime(target, mime, "pasted")
    def _paste_explorer_urls(self, target, mime):
        """Ctrl+V of Explorer files/folders copies them in (unlike a drag,
        which only links the location)."""
        files, folders = [], []
        for u in mime.urls():
            p = u.toLocalFile()
            if not p:
                continue
            if os.path.isdir(p):
                folders.append(p)
            elif os.path.isfile(p):
                files.append(p)
        if folders:
            alert(self.window(), "Paste",
                  f"{len(folders)} folder{'s' if len(folders) != 1 else ''} "
                  "can't be pasted (only files are copied in).\n"
                  "Drag a folder onto a task instead - that links its "
                  "location without copying it.")
        copied = []
        for p in files:
            try:
                dst = unique_path(os.path.basename(p))
                shutil.copy2(p, dst)
                name = os.path.basename(dst)
                mark_owned([name])
                copied.append(name)
            except OSError as exc:
                log_error(f"Couldn't copy pasted file '{p}'", exc)
                alert(self.window(), "Paste", f"Couldn't copy:\n{p}\n\n{exc}")
        if copied:
            self.attach_files(target, copied)
    # ---------- shared Outlook handling (drag and paste) ----------
    def _handle_outlook_mime(self, target, mime, verb):
        """FileGroupDescriptor formats - one or more Outlook emails and/or
        attachments, whether dropped or pasted. A single small item Qt can
        hand us directly is saved right away; anything else is fetched from
        Outlook on a background thread so the list never freezes."""
        fmt, wide = _mime_format(mime, "FileGroupDescriptorW"), True
        if not fmt:
            fmt, wide = _mime_format(mime, "FileGroupDescriptor"), False
        if not fmt:
            return
        names = _descriptor_names(bytes(mime.data(fmt)), wide)
        if not names:
            alert(self.window(), "Outlook items",
                  f"Couldn't read what was {verb} from Outlook.\n"
                  "Try again with one item at a time.")
            return
        if len(names) == 1:
            cf = _mime_format(mime, "FileContents")
            if cf:
                data = bytes(mime.data(cf))
                if data:
                    if len(data) > MAX_ATTACHMENT_BYTES:
                        alert(self.window(), "Attachment",
                              f"'{names[0]}' is too large to attach.")
                        return
                    dst = unique_path(names[0])
                    try:
                        with open(dst, "wb") as f:
                            f.write(data)
                        name = os.path.basename(dst)
                        mark_owned([name])
                        self.attach_files(target, [name])
                    except OSError as exc:
                        log_error(f"Couldn't save {verb} attachment '{names[0]}'", exc)
                        alert(self.window(), "Attachment",
                              f"Couldn't save '{names[0]}':\n{exc}")
                    return
        # Several items, or Qt couldn't hand us the bytes directly: ask
        # Outlook, off the UI thread.
        self.start_outlook_fetch(target, names)
    # ---------- fetching Outlook items on a background thread ----------
    def start_outlook_fetch(self, target, names):
        self._outlook_req_seq += 1
        req_id = self._outlook_req_seq
        thread = OutlookFetchThread(names, req_id, self)
        thread.done.connect(self._outlook_fetch_done)
        thread.finished.connect(thread.deleteLater)
        self._outlook_requests[req_id] = target
        win = self.window()
        if hasattr(win, "set_busy"):
            win.set_busy(True, "Getting Outlook items\u2026")
        thread.start()
    def _outlook_fetch_done(self, req_id, saved, failed):
        target = self._outlook_requests.pop(req_id, None)
        win = self.window()
        if hasattr(win, "set_busy"):
            win.set_busy(False)
        names = [os.path.basename(p) for p in saved]
        if names:
            mark_owned(names)
        # The task/group the drop started on may have been deleted or
        # archived while the fetch was running - check before attaching.
        valid = (isinstance(target, TaskCard) and target in self.all_cards()) or \
                (isinstance(target, Group) and target in self.groups)
        if valid and names:
            self.attach_files(target, names)
        elif names:
            self.release_files(names)     # target's gone - don't leave orphans lying around
        if failed:
            alert(self.window(), "Outlook items",
                  "Some items couldn't be attached:\n- " + "\n- ".join(failed))
    def attach_files(self, target, names):
        """Onto a task: attach. Onto a group: new task named from "Add a task"
        (if you've typed something) or from the email subject / file name."""
        self.checkpoint()
        if isinstance(target, TaskCard):
            have = target.files()
            target.task["files"] = have + [n for n in names if n not in have]
            self.relayout(animate=True)
        else:
            g = target
            g.folded = False
            edit = g.add_row.edit
            text = clean_task(edit.text())
            if text:
                tasks = [{"text": text, "files": names}]
                edit.clear()
            else:
                tasks = [{"text": clean(display_name(n) if is_location(n)
                                        else os.path.splitext(n)[0]) or n, "files": [n]}
                         for n in names]
            new = []
            for t in tasks:
                t.update(done=False, group=g.name)
                card = TaskCard(self, t)
                card.move(g.add_row.pos())
                g.cards.append(card)
                new.append(card)
            self.relayout(animate=True)
            for card in new:
                card.show()
                card.stackUnder(g.add_row)
            g.header.update()
            self.reveal_later(g.add_row)
        self.changed.emit()
    def chip_menu(self, card, name, global_pos):
        place = is_location(name)
        folder = place and cached_isdir(name)
        menu = RoundMenu(self)
        act_open = menu.addAction(menu_icon("open"), "Open folder" if folder else "Open")
        act_folder = menu.addAction(menu_icon("folder"), "Show in folder")
        act_copy = menu.addAction(menu_icon("copy"), "Copy path")
        menu.addSeparator()
        act_remove = menu.addAction(menu_icon("x", OVERDUE),
                                    "Remove location" if place else "Remove attachment")
        chosen = menu.open_at(global_pos)
        if chosen == act_copy:
            QGuiApplication.clipboard().setText(attach_path(name))
        elif chosen == act_open:
            open_attachment(name, self.window())
        elif chosen == act_folder:
            path = attach_path(name)
            try:
                if folder:
                    os.startfile(path)                      # linked folder: open it directly
                else:
                    # linked file or copied attachment: open its parent and select it
                    subprocess.Popen(f'explorer /select,"{path}"')
            except OSError as exc:
                log_error(f"'Show in folder' failed for '{path}'", exc)
                alert(self.window(), "Show in folder", f"Couldn't open:\n{path}\n\n{exc}")
        elif chosen == act_remove:
            self.checkpoint()
            card.task["files"] = [f for f in card.files() if f != name]
            self.release_files([name])
            self.relayout(animate=True)
            self.changed.emit()
    def used_files(self):
        return {f for c in self.all_cards() for f in c.files()}
    def release_files(self, names):
        used = self.used_files()
        trash_files([n for n in names if n not in used])
    def add_focused(self, group):
        self.active_group = group
        self.clear_selection()
    def _create_task(self, group, text, due=None):
        """Shared by add_task() (Enter / focus-lost) and add_row_menu() (the
        Add-row's right-click menu): builds and inserts a new TaskCard.
        Always runs the full set of typed shortcuts (due date, '#Group'/
        '@Group' routing, trailing '!!'/'urgent') on the text - a
        '#Lincoln' tag routes the new task to that group even if typed in
        a different group's Add-row. If the caller already chose an
        explicit due date (e.g. a menu preset), that wins over anything
        auto-detected in the text, but the text is still stripped either way."""
        text = clean_task(text)
        if not text:
            return None
        origin_group = group        # where to put the text back if this is undone
        raw_text = text              # exactly as typed, before shortcuts strip it
        history_len = len(self.history)
        self.checkpoint()
        body, auto_due, urgent, tag_group = parse_task_shortcuts(
            text, [g.name for g in self.groups])
        text = body
        if due is None:
            due = auto_due
        if tag_group:
            group = self.group_named(tag_group)
        task = {"text": text, "done": False, "group": group.name}
        if due:
            task["due"] = due
        if urgent:
            task["star"] = True
        card = TaskCard(self, task)
        card.move(group.add_row.pos())
        group.cards.append(card)
        self.relayout(animate=True)
        card.show()
        card.stackUnder(group.add_row)
        self.reveal_later(group.add_row)
        self.changed.emit()
        # Ctrl+Z right after adding this undoes only "pressing Enter" - the
        # task disappears again and exactly what you typed goes back into
        # the Add-task box you typed it in (not into an editor on the now
        # vanished task), ready to fix and resubmit. So fixing a typo never
        # means retyping the whole thing from scratch.
        if len(self.history) > history_len:
            self.history[-1]["_reedit"] = {
                "mode": "add", "card": card, "origin_group_name": origin_group.name,
                "raw_text": raw_text}
        return card
    def add_task(self, group):
        edit = group.add_row.edit
        if self._create_task(group, edit.text()) is not None:
            edit.clear()
    def add_row_menu(self, add_row, global_pos):
        """Right-click on the 'Add a task' row: only shown once something's
        actually been typed (there's nothing to act on otherwise). Lets you
        add the task as-is, or add it with a due date - using the same
        Today/Tomorrow/Next week/Pick a date design as an existing task's
        menu, just applied before the task exists yet. The preset shown
        checked here previews whatever _create_task() will actually detect
        (a '#Group'/'!!' elsewhere in the text doesn't stop a trailing due
        word from being found)."""
        text = clean_task(add_row.edit.text())
        if not text:
            return
        group = add_row.group
        _, auto_due, _, _ = parse_task_shortcuts(text, [g.name for g in self.groups])
        today = date.today()
        nxt = next_monday()
        def short(d):
            return d.strftime("%a ") + str(d.day) + d.strftime(" %b")
        menu = RoundMenu(self)
        act_add = menu.addAction(menu_icon("plus", ACCENT), "Add task")
        menu.addSeparator()
        options = [("Today", today, DUE_SOON),
                   ("Tomorrow", today + timedelta(days=1), DUE_SOON),
                   ("Next week", nxt, DUE_LATER)]
        due_actions = {}
        preset = False
        for label, d, col in options:
            value = d.isoformat()
            on = auto_due == value
            preset = preset or on
            act = menu.addAction(menu_icon("cal", col), f"{label}   \u00b7  {short(d)}")
            act.setCheckable(True)
            act.setChecked(on)
            due_actions[act] = value
        custom = auto_due if auto_due and not preset else None
        pick_text = f"Due {short(parse_due(custom))}" if custom and parse_due(custom) \
            else "Pick a date\u2026"
        act_pick = menu.addAction(menu_icon("cal-empty", ACCENT), pick_text)
        act_pick.setCheckable(True)
        act_pick.setChecked(bool(custom))
        chosen = menu.open_at(global_pos)
        if chosen is None:
            return
        if chosen == act_add:
            if self._create_task(group, text) is not None:
                add_row.edit.clear()
        elif chosen in due_actions:
            if self._create_task(group, text, due=due_actions[chosen]) is not None:
                add_row.edit.clear()
        elif chosen == act_pick:
            # opens under the row, with any auto-detected date pre-selected
            top = add_row.mapToGlobal(QPoint(0, 0))
            anchor = QRect(global_pos.x(), top.y(), 1, add_row.height())
            value = pick_date(self.window(), custom, anchor)
            if value and self._create_task(group, text, due=value) is not None:
                add_row.edit.clear()
    def edit_menu(self, card, global_pos):
        """Right-click on a task while it's being edited inline: the same
        due-date menu as a normal (not-editing) task - Today/Tomorrow/Next
        week/Pick a date highlighted to match the current due date, Remove
        due date, and Delete - plus "Update task" on top, which commits
        whatever's currently typed instead of leaving the editor open.
        The due date shown/highlighted is whichever would actually apply if
        you pressed Enter right now: a date word just typed at the end of
        the text takes precedence; otherwise it's the task's existing due
        date, exactly as if you'd right-clicked it normally."""
        text = clean_task(card.editor.text())
        if not text:
            return
        self.select_only(card)
        body, auto_due, urgent, tag_group = parse_task_shortcuts(
            text, [g.name for g in self.groups])
        current = auto_due if auto_due else card.task.get("due")
        today = date.today()
        nxt = next_monday()
        def short(d):
            return d.strftime("%a ") + str(d.day) + d.strftime(" %b")
        menu = RoundMenu(self)
        act_update = menu.addAction(menu_icon("plus", ACCENT), "Update task")
        menu.addSeparator()
        options = [("Today", today, DUE_SOON),
                   ("Tomorrow", today + timedelta(days=1), DUE_SOON),
                   ("Next week", nxt, DUE_LATER)]
        due_actions = {}
        preset = False
        for label, d, col in options:
            value = d.isoformat()
            on = current == value
            preset = preset or on
            act = menu.addAction(menu_icon("cal", col), f"{label}   \u00b7  {short(d)}")
            act.setCheckable(True)
            act.setChecked(on)
            due_actions[act] = value
        custom = current if current and not preset else None
        pick_text = f"Due {short(parse_due(custom))}" if custom and parse_due(custom) \
            else "Pick a date\u2026"
        act_pick = menu.addAction(menu_icon("cal-empty", ACCENT), pick_text)
        act_pick.setCheckable(True)
        act_pick.setChecked(bool(custom))
        act_nodue = None
        if current:
            menu.addSeparator()
            act_nodue = menu.addAction(menu_icon("x", OVERDUE), "Remove due date")
        menu.addSeparator()
        act_delete = menu.addAction(menu_icon("bin", OVERDUE), "Delete")
        # Opening the menu takes focus away from the editor - suppress the
        # usual focus-lost auto-commit for as long as it's open, so this
        # menu's own commit (below) is always the one that applies, however
        # Qt happens to sequence the focus change underneath it.
        card._suspend_focus_commit = True
        try:
            chosen = menu.open_at(global_pos)
        finally:
            card._suspend_focus_commit = False
        if chosen is None:
            card.editor.setFocus()      # menu dismissed - carry on editing
            return
        if chosen == act_delete:
            self.delete_cards([card])           # Ctrl+Z restores it, as usual
        elif chosen == act_update:
            self._apply_edit(card, body, due=current, star=urgent, tag_group=tag_group,
                             raw_text=text)
        elif chosen in due_actions:
            value = due_actions[chosen]
            # clicking the one that's already set clears it, same as the
            # normal (not-editing) due-date menu
            self._apply_edit(card, body, due=None if current == value else value,
                             clear_due=current == value, star=urgent, tag_group=tag_group,
                             raw_text=text)
        elif chosen == act_pick:
            top = card.mapToGlobal(QPoint(0, 0))
            anchor = QRect(global_pos.x(), top.y(), 1, card.height())
            value = pick_date(self.window(), custom, anchor)
            if value:
                self._apply_edit(card, body, due=value, star=urgent, tag_group=tag_group,
                                 raw_text=text)
            else:
                card.editor.setFocus()   # date picker cancelled - keep editing
        elif act_nodue is not None and chosen == act_nodue:
            self._apply_edit(card, body, due=None, clear_due=True, star=urgent,
                             tag_group=tag_group, raw_text=text)
    def _apply_edit(self, card, text, due=None, clear_due=False, star=False, tag_group=None,
                    raw_text=None):
        """Commits text/due into the task being edited and closes the inline
        editor - used by edit_menu()'s actions. Reads from (and only acts
        on) what's currently in the editor box, so it's correct whether or
        not editing was already ended by some other path in the meantime.
        clear_due=True explicitly removes the due date (distinct from
        due=None, which just means 'leave the existing due date alone').
        star=True (from a trailing '!!'/'urgent' in the typed text) stars
        the task; tag_group (from a '#Group'/'@Group' tag) moves it to
        that group instead of wherever it currently lives. raw_text is
        exactly what was in the editor before shortcuts were stripped out
        of it - restored into the editor verbatim if this gets undone."""
        had_due = card.task.get("due")
        due_changed = (clear_due and had_due is not None) or \
                      (not clear_due and bool(due) and due != had_due)
        text_changed = bool(text) and text != card.task["text"]
        group_changed = bool(tag_group) and tag_group != card.task.get("group")
        if text_changed or due_changed or star or group_changed:
            # for the "undo puts this back in the editor" case below (a
            # real copy, so later in-place changes to card.task can't
            # reach back into it)
            old_task = self._task_copy(card.task)
            history_len = len(self.history)
            self.checkpoint()
            if text:
                card.task["text"] = text
            if clear_due:
                card.task.pop("due", None)
            elif due:
                card.task["due"] = due
            if star:
                card.task["star"] = True
            self.changed.emit()
            # Ctrl+Z right after this undoes only "committing the menu
            # choice" - it reopens this task's editor with exactly what you
            # had typed, and its due/star/group go back to how they were
            # before, same as the plain inline-edit path.
            if len(self.history) > history_len:
                self.history[-1]["_reedit"] = {
                    "mode": "edit", "card": card, "old_task": old_task,
                    "raw_text": raw_text if raw_text is not None else text}
        if group_changed:
            current_group = self.group_of(card)
            target_group = self.group_named(tag_group)
            if current_group is not None and current_group is not target_group:
                current_group.cards.remove(card)
                target_group.cards.append(card)
                card.task["group"] = target_group.name
        card.editing = False
        card.editor.hide()
        card.label.show()
        card.refresh()
        self.relayout(animate=True)
        group = card.home_group()
        self.active_group = group
    def set_done(self, cards, done):
        if not any(c.task["done"] != done for c in cards):
            return
        self.checkpoint()
        for card in cards:
            if card.task["done"] == done:
                continue
            card.task["done"] = done
            if done:
                card.task["doneat"] = date.today().isoformat()
            else:
                card.task.pop("doneat", None)
            if done:
                g = self.group_of(card)
                if g:
                    g.cards.remove(card)
                    card.task["group"] = g.name
                self.done_cards.insert(0, card)
            else:
                self.done_cards.remove(card)
                g = self.group_named(card.task["group"])
                card.task["group"] = g.name
                g.cards.append(card)
                card._order = self.next_order_seq()   # lands at the end, as before
            card.refresh()
            card.raise_()
        self.relayout(animate=True)
        self.changed.emit()
    def move_cards(self, cards, group):
        self.checkpoint()
        for card in cards:
            card.task["group"] = group.name
            if not card.task["done"]:
                current = self.group_of(card)
                if current is not group:
                    current.cards.remove(card)
                    group.cards.append(card)
                    card._order = self.next_order_seq()   # lands at the end, as before
            card.refresh()
        self.relayout(animate=True)
        self.changed.emit()
    def delete_cards(self, cards):
        if not cards:
            return
        self.checkpoint()
        self._remove(cards)
        self.relayout(animate=True)
        self.changed.emit()
    def archive_cards(self, cards, undoable=True):
        if not cards:
            return
        snap = self.snapshot() if undoable else None
        result = archive_tasks([dict(c.task) for c in cards])
        if result is None:
            alert(self.window(), "Archive", f"Couldn't write to:\n{ARCHIVE_FILE}")
            return
        if snap is not None:
            snap["archive"] = result          # so Ctrl+Z takes it back out of the file
            self.checkpoint(snap)
        self._remove(cards)
        self.relayout(animate=True)
        self.changed.emit()
    def auto_archive(self, days):
        if days <= 0 or self.dead:
            return
        today = date.today()
        old = [c for c in self.done_cards
               if parse_due(c.task.get("doneat") or "") and
               (today - parse_due(c.task["doneat"])).days >= days]
        self.archive_cards(old, undoable=False)
    def confirm(self, title, text, ok, info=None):
        box = QMessageBox(self.window())
        box.setWindowTitle(title)
        box.setText(text)
        if info:
            box.setInformativeText(info)
        yes = box.addButton(ok, QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.setStyleSheet(DIALOG_STYLE)
        box.exec()
        return box.clickedButton() is yes
    def done_menu(self, global_pos):
        n = len(self.done_cards)
        menu = RoundMenu(self)
        act_arch = menu.addAction(menu_icon("box"), f"Archive all completed ({n})")
        act_del = menu.addAction(menu_icon("bin", OVERDUE), f"Delete all completed ({n})")
        menu.addSeparator()
        act_open = menu.addAction(menu_icon("open"), "Open archive file")
        chosen = menu.open_at(global_pos)
        if chosen == act_arch:
            if self.confirm("Archive completed",
                            f"Move {n} completed task{'s' if n != 1 else ''} to TodoArchive.txt?",
                            "Archive"):
                self.archive_cards(list(self.done_cards))
        elif chosen == act_del:
            if self.confirm("Delete completed",
                            f"Delete {n} completed task{'s' if n != 1 else ''}?\n"
                            "Ctrl+Z brings them back until you close the list.",
                            "Delete"):
                self.delete_cards(list(self.done_cards))
        elif chosen == act_open:
            open_archive(self.window())
    def set_group_colour(self, group, colour):
        if group.colour == colour:
            return
        self.checkpoint()
        group.colour = colour
        self.repaint_group(group)
        self.changed.emit()
    def repaint_group(self, group):
        group.header.update()
        group.add_row.update()
        for c in self.all_cards():
            if c.task["group"] == group.name:
                c.update()
    def _remove(self, cards):
        files = [f for c in cards for f in c.files()]
        for c in cards:
            g = self.group_of(c)
            if g:
                g.cards.remove(c)
            if c in self.done_cards:
                self.done_cards.remove(c)
            self.selected.discard(id(c))
            if self.anchor is c:
                self.anchor = None
            c.hide()
            c.deleteLater()
        self.release_files(files)
    def toggle_star(self, cards):
        if not cards:
            return
        self.checkpoint()
        on = not all(c.task.get("star") for c in cards)
        for c in cards:
            if on:
                c.task["star"] = True
            else:
                c.task.pop("star", None)
            c.update()
        self.relayout(animate=True)
        self.changed.emit()
    def set_due(self, cards, value):
        if not cards:
            return
        self.checkpoint()
        for c in cards:
            if value:
                c.task["due"] = value
            else:
                c.task.pop("due", None)
            c.refresh()
        self.relayout(animate=True)
        self.changed.emit()
    def refresh_dates(self):
        """Overdue / today / 'Completed yesterday' move on when the day changes."""
        for c in self.all_cards():
            if c.task.get("due") or c.task["done"]:
                c.refresh()
        self.relayout(animate=False)
    def refresh_links(self):
        for c in self.all_cards():
            if c.links or "\\" in c.task["text"]:
                c.refresh()
        self.relayout(animate=False)
    def refresh_attachments(self):
        """A background cached_isdir() check came back - repaint the chips
        it affects (no filesystem access happens in paintEvent itself)."""
        for c in self.all_cards():
            if c.files():
                c.update()
    def toggle_collapsed(self):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.selected -= {id(c) for c in self.done_cards}
            self.refresh_selection()
        self.relayout(animate=True)
        self.changed.emit()
    # ---------- group actions ----------
    def unique_name(self, name, ignore=None):
        names = {g.name.lower() for g in self.groups if g is not ignore}
        base, n = name, 2
        while name.lower() in names:
            name = f"{base} {n}"
            n += 1
        return name
    def reveal_later(self, widget, then=None):
        """Scrolls `widget` into view once the layout animation has moved it
        there. Tied to the widget, so it's simply dropped if the widget is
        gone by then (tab switched, group deleted, undo)."""
        def go():
            if self.dead:
                return
            self.scroll.ensureWidgetVisible(widget, 0, 30)
            if then is not None:
                then()
        QTimer.singleShot(ANIM_MS, widget, go)
    def new_group(self):
        self.checkpoint()
        g = self.create_group(self.unique_name("New group"))
        g.header.move(self.new_group_btn.pos())
        g.add_row.move(self.new_group_btn.pos())
        self.relayout(animate=True)
        self.reveal_later(g.add_row, then=g.header.start_rename)
        self.changed.emit()
    def rename_group(self, group, text):
        name = clean(text).replace("[", "(").replace("]", ")")
        if not name or name == group.name or name.lower() == GENERAL.lower():
            return
        name = self.unique_name(name, ignore=group)
        self.checkpoint()
        old = group.name
        group.name = name
        for c in group.cards:
            c.task["group"] = name
        for c in self.done_cards:
            if c.task["group"] == old:
                c.task["group"] = name
                c.refresh()
        group.header.update()
        self.changed.emit()
    def confirm_delete_group(self, group):
        n = len(group.cards) + sum(1 for c in self.done_cards
                                   if c.task["group"] == group.name)
        info = f"Its {n} task{'' if n == 1 else 's'} will move to {GENERAL}." if n else None
        return self.confirm("Delete group", f'Delete "{group.name}"?', "Delete", info)
    def delete_group(self, group):
        if group.name == GENERAL:
            return
        self.checkpoint()
        general = self.groups[0]
        for c in group.cards:
            c.task["group"] = GENERAL
            general.cards.append(c)
        for c in self.done_cards:
            if c.task["group"] == group.name:
                c.task["group"] = GENERAL
                c.refresh()
        self.groups.remove(group)
        for w in (group.header, group.add_row):
            w.hide()
            w.deleteLater()
        if self.active_group is group:
            self.active_group = general
        self.relayout(animate=True)
        self.changed.emit()
    # ---------- menus ----------
    def card_menu(self, card, global_pos):
        self.setFocus()
        # Right-clicking a task that isn't part of the current selection
        # selects just that one first; right-clicking one of several
        # already-selected tasks keeps the whole selection (so Delete, and
        # only Delete, applies to all of them).
        if id(card) not in self.selected:
            self.select_only(card)
        all_selected = self.selected_cards()
        n_all = len(all_selected)
        cards = [c for c in all_selected if not c.task["done"]]   # due dates: open tasks only
        n = len(cards)
        menu = RoundMenu(self)
        due_actions, act_pick, act_nodue, current = {}, None, None, None
        if cards:
            today = date.today()
            nxt = next_monday()
            dues = {c.task.get("due") for c in cards}
            current = dues.pop() if len(dues) == 1 else None      # same date on all
            mixed = len({c.task.get("due") for c in cards}) > 1
            def short(d):
                return d.strftime("%a ") + str(d.day) + d.strftime(" %b")
            options = [("Today", today, DUE_SOON),
                       ("Tomorrow", today + timedelta(days=1), DUE_SOON),
                       ("Next week", nxt, DUE_LATER)]
            preset = False
            for label, d, col in options:
                value = d.isoformat()
                on = current == value
                preset = preset or on
                act = menu.addAction(menu_icon("cal", col), f"{label}   \u00b7  {short(d)}")
                act.setCheckable(True)
                act.setChecked(on)
                due_actions[act] = value
            custom = current if current and not preset else None
            pick_text = f"Due {short(parse_due(custom))}" if custom and parse_due(custom) \
                else "Pick a date\u2026"
            act_pick = menu.addAction(menu_icon("cal-empty", ACCENT), pick_text)
            act_pick.setCheckable(True)
            act_pick.setChecked(bool(custom))
            if mixed or current:
                menu.addSeparator()
                act_nodue = menu.addAction(menu_icon("x", OVERDUE),
                                           "Remove due dates" if n > 1 else "Remove due date")
        # Delete is always available - for a single task, a multi-selection,
        # or a completed task (which has no due-date actions above).
        menu.addSeparator()
        act_delete = menu.addAction(menu_icon("bin", OVERDUE),
                                    f"Delete {n_all} tasks" if n_all > 1 else "Delete")
        chosen = menu.open_at(global_pos)
        if chosen is None:
            return
        if chosen == act_delete:
            self.delete_cards(all_selected)         # Ctrl+Z restores them, as usual
        elif chosen in due_actions:
            value = due_actions[chosen]
            # clicking the one that's already set clears it
            self.set_due(cards, None if current == value else value)
        elif act_pick is not None and chosen == act_pick:
            # opens under the task, with its current date selected
            top = card.mapToGlobal(QPoint(0, 0))
            anchor = QRect(global_pos.x(), top.y(), 1, card.height())
            value = pick_date(self.window(), card.task.get("due"), anchor)
            if value:
                self.set_due(cards, value)
        elif act_nodue is not None and chosen == act_nodue:
            self.set_due(cards, None)
    def group_menu(self, group, global_pos):
        menu = RoundMenu(self)
        act_rename = act_delete = None
        if group.name != GENERAL:
            act_rename = menu.addAction(menu_icon("pen"), "Rename group")
        colour_menu = menu.sub("Colour", menu_icon("palette"))
        colour_actions = {}
        presets = [h for _, h in GROUP_COLOURS]
        for name, hexc in [("None", None)] + GROUP_COLOURS:
            act = colour_menu.addAction(colour_icon(hexc, group.colour == hexc), name)
            colour_actions[act] = hexc
        colour_menu.addSeparator()
        custom_now = group.colour if group.colour and group.colour not in presets else None
        act_custom = colour_menu.addAction(
            colour_icon(custom_now, True) if custom_now else menu_icon("palette"),
            "Custom colour\u2026")
        act_copy = menu.addAction(menu_icon("copy"), "Copy as list")
        act_copy.setEnabled(bool(group.cards))
        if group.name != GENERAL:
            menu.addSeparator()
            act_delete = menu.addAction(menu_icon("bin", OVERDUE), "Delete group")
        chosen = menu.open_at(global_pos)
        if chosen is None:
            return
        if chosen in colour_actions:
            self.set_group_colour(group, colour_actions[chosen])
        elif chosen == act_custom:
            head = group.header
            top = head.mapToGlobal(QPoint(0, 0))
            anchor = QRect(global_pos.x(), top.y(), 1, head.height())
            old = group.colour
            def live(colour):
                group.colour = colour
                self.repaint_group(group)
            c = pick_colour(self.window(), group.colour, f"Colour for {group.name}",
                            anchor, live=live)
            group.colour = old              # put back, so undo gets the old colour
            self.repaint_group(group)
            if c:
                self.set_group_colour(group, c)
        elif chosen == act_copy:
            QGuiApplication.clipboard().setText(group_as_list(group))
        elif chosen == act_rename:
            group.header.start_rename()
        elif chosen == act_delete:
            if self.confirm_delete_group(group):
                self.delete_group(group)
    # ---------- keyboard ----------
    def keyPressEvent(self, e):
        key = e.key()
        ctrl = bool(e.modifiers() & Qt.ControlModifier)
        if key == Qt.Key_Delete:
            self.delete_cards(self.selected_cards())
        elif key == Qt.Key_Escape:
            self.clear_selection()
        elif ctrl and key == Qt.Key_Z:
            self.undo_requested.emit()
        elif ctrl and key == Qt.Key_A:
            self.selected = {id(c) for c in self.visible_cards()}
            self.refresh_selection()
        elif e.matches(QKeySequence.StandardKey.Paste):
            mime = QGuiApplication.clipboard().mimeData()
            if can_accept_drop(mime):
                self.paste_attachment(mime)
            # otherwise: nothing sensible to paste plain text into here
        elif key in (Qt.Key_Up, Qt.Key_Down) and not ctrl:
            self.move_selection(-1 if key == Qt.Key_Up else 1,
                                bool(e.modifiers() & Qt.ShiftModifier))
        elif key == Qt.Key_Space and self.selected:
            cards = self.selected_cards()
            self.set_done(cards, not cards[0].task["done"])
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            cards = self.selected_cards()
            if len(cards) == 1:
                cards[0].start_edit()
            else:
                self.focus_add(self.active_group)
        elif e.text() and e.text().isprintable() and not ctrl:
            self.clear_selection()
            self.focus_add(self.active_group)
            self.active_group.add_row.edit.insert(e.text())
        else:
            super().keyPressEvent(e)
SCROLL_STYLE = """
QScrollBar:vertical { background: transparent; width: 9px; margin: 4px 2px 4px 0; }
QScrollBar::handle:vertical { background: rgba(255,255,255,55); border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,95); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""
HSCROLL_STYLE = """
QScrollBar:horizontal { background: transparent; height: 6px; margin: 0 2px 1px 2px; }
QScrollBar::handle:horizontal { background: rgba(255,255,255,55); border-radius: 3px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: rgba(255,255,255,95); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
"""
# ------------------------------------------------------------------
# SETTINGS BUTTON + SIZE SLIDER POPUP
# ------------------------------------------------------------------
class IconButton(QWidget):
    """Small top-bar button: 'pin', 'more', 'min', 'max', 'close', 'plus' or
    'tabs' (the all-tabs menu)."""
    clicked = Signal()
    def __init__(self, parent, kind, tip):
        super().__init__(parent)
        self.kind = kind
        self.hover = False
        self.active = False         # pin state
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tip)
        self.apply_scale()
    def apply_scale(self):
        self.setFixedSize(int(28 * S), int(26 * S))
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        if self.hover:
            p.setBrush(QColor("#c42b1c") if self.kind == "close"
                       else QColor(255, 255, 255, 40))
            p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        cx, cy = self.width() / 2, self.height() / 2
        pen = QPen(QColor(TEXT), 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if self.kind == "more":
            p.setBrush(QColor(TEXT))
            for dx in (-6, 0, 6):
                p.drawEllipse(QPointF(cx + dx * S, cy), 1.4 * S, 1.4 * S)
        elif self.kind == "min":
            p.setPen(pen)
            p.drawLine(QPointF(cx - 5 * S, cy), QPointF(cx + 5 * S, cy))
        elif self.kind == "max":
            a = 4.5 * S
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            if self.window().isMaximized():
                d = 2 * S
                p.drawRect(QRectF(cx - a, cy - a + d, 2 * a - d, 2 * a - d))
                back = QPainterPath()
                back.moveTo(cx - a + d, cy - a + d)
                back.lineTo(cx - a + d, cy - a)
                back.lineTo(cx + a, cy - a)
                back.lineTo(cx + a, cy + a - d)
                back.lineTo(cx + a - d, cy + a - d)
                p.drawPath(back)
            else:
                p.drawRect(QRectF(cx - a, cy - a, 2 * a, 2 * a))
        elif self.kind == "pin":
            col = QColor(ACCENT if self.active else TEXT)
            p.translate(cx, cy)
            p.rotate(45)
            p.setPen(QPen(col, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(col if self.active else Qt.NoBrush)
            p.drawRoundedRect(QRectF(-2.8 * S, -6.5 * S, 5.6 * S, 5 * S), 1 * S, 1 * S)
            p.drawLine(QPointF(-5 * S, -1.5 * S), QPointF(5 * S, -1.5 * S))
            p.drawLine(QPointF(0, -1.5 * S), QPointF(0, 6.5 * S))
        elif self.kind == "tabs":
            a = 3.5 * S
            p.setPen(QPen(QColor(TEXT), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            chevron = QPainterPath()
            chevron.moveTo(cx - a, cy - a / 2)
            chevron.lineTo(cx, cy + a / 2)
            chevron.lineTo(cx + a, cy - a / 2)
            p.drawPath(chevron)
        elif self.kind == "plus":
            a = 5 * S
            p.setPen(QPen(QColor(TEXT), 1.4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - a, cy), QPointF(cx + a, cy))
            p.drawLine(QPointF(cx, cy - a), QPointF(cx, cy + a))
        else:
            a = 4.5 * S
            p.setPen(QPen(QColor(TEXT), 1.3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - a, cy - a), QPointF(cx + a, cy + a))
            p.drawLine(QPointF(cx - a, cy + a), QPointF(cx + a, cy - a))
    def enterEvent(self, _):
        self.hover = True
        self.update()
    def leaveEvent(self, _):
        self.hover = False
        self.update()
    def mousePressEvent(self, e):
        # Act on release, like normal Windows buttons. Acting on press closed
        # the window first, so the release landed on the app behind it and
        # clicked its X / minimise.
        if e.button() == Qt.LeftButton:
            self.pressed = True
            e.accept()
    def mouseReleaseEvent(self, e):
        was = getattr(self, "pressed", False)
        self.pressed = False
        e.accept()
        if (was and e.button() == Qt.LeftButton
                and self.rect().contains(e.position().toPoint())):
            self.clicked.emit()
class TabFade(QWidget):
    """Soft fade at whichever end of the tab row has more tabs scrolled out
    of view - the only hint needed that the row scrolls (mouse wheel, or
    automatically to keep the open / dragged tab in view)."""
    def __init__(self, area):
        super().__init__(area)
        self.area = area
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
    def paintEvent(self, _):
        bar = self.area.horizontalScrollBar()
        if bar.maximum() <= 0:
            return
        p = QPainter(self)
        w = 18 * S
        solid = QColor(TOPBAR_BG[0])
        clear = QColor(solid)
        clear.setAlpha(0)
        for show, x0, x1 in ((bar.value() > bar.minimum(), 0, w),
                             (bar.value() < bar.maximum(), self.width(), self.width() - w)):
            if show:
                g = QLinearGradient(x0, 0, x1, 0)
                g.setColorAt(0, solid)
                g.setColorAt(1, clear)
                p.fillRect(QRectF(min(x0, x1), 0, w, self.height()), g)
class TabScrollArea(QScrollArea):
    """Horizontal-only, frameless, background-free viewport around the tab
    row. Tabs shrink to fit first (TabBar.relayout); only once they're at
    their minimum width does the row scroll - by mouse wheel, by dragging a
    tab against either end, and automatically so the open tab is always in
    view - and the all-tabs menu button appears. No scrollbar or arrows."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.viewport().setAutoFillBackground(False)
        self.viewport().setStyleSheet("background: transparent;")
        self.fade = TabFade(self)
        bar = self.horizontalScrollBar()
        bar.valueChanged.connect(self._scrolled)
        bar.rangeChanged.connect(self._scrolled)
    def _scrolled(self, *_):
        self.fade.update()
        self.window().update()      # the open tab's background is painted by the window
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fade.setGeometry(self.rect())
        self.fade.raise_()
    def wheelEvent(self, e):
        delta = e.angleDelta().y() or e.angleDelta().x()
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - delta)
        e.accept()
class TopBar(QWidget):
    """The window's only top row: tabs (with a '+' right after the last one)
    on the left, the window controls (pin / settings / minimise / maximise /
    close) on the right. Tabs sit flush with the bottom of the bar so the
    open tab runs straight into the list below it.
    Children are placed by hand (layout_children) rather than by a layout,
    because how wide the tab row may be depends on how much room the
    controls leave, and the '+' then follows the tab row's actual width.
    Empty space in this bar is a native caption (Window.hit_test): drag to
    move the window, double-click to maximise / restore."""
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.tab_scroll = TabScrollArea(self)
        self.tabbar = TabBar(self)
        self.tab_scroll.setWidget(self.tabbar)
        self.tabbar.setAutoFillBackground(False)     # setWidget turns this on
        self.plus_btn = IconButton(self, "plus", "New tab")
        self.plus_btn.clicked.connect(win.add_tab)
        # Only shown while some tabs don't fit: lists every tab to jump to.
        self.tabs_btn = IconButton(self, "tabs", "All tabs")
        self.tabs_btn.clicked.connect(self.tabbar.all_tabs_menu)
        self.tabs_btn.hide()
        # Kept only so set_busy() has somewhere to park a short status
        # string while a background fetch runs - never shown on screen.
        self.title = QLabel("", self)
        self.title.hide()
        self.pin_btn = IconButton(self, "pin", "Keep on top")
        self.settings_btn = IconButton(self, "more", "Settings")
        self.min_btn = IconButton(self, "min", "Minimise")
        self.max_btn = IconButton(self, "max", "Maximise")
        self.close_btn = IconButton(self, "close", "Close (F2)")
        self.controls = (self.pin_btn, self.settings_btn, self.min_btn,
                         self.max_btn, self.close_btn)
        self.apply_scale()
    def apply_scale(self):
        self.setFixedHeight(int(34 * S))
        self.plus_btn.apply_scale()
        self.tabs_btn.apply_scale()
        for b in self.controls:
            b.apply_scale()
        self.tabbar.apply_scale()      # re-measures every tab, then lays the bar out
        # Never so narrow that the open tab, '+' and the all-tabs menu can't
        # all fit beside the window controls.
        self.win.setMinimumWidth(self.min_width() + 2 * EDGE)
    def min_width(self):
        sp = int(2 * S)
        controls = sum(b.width() + sp for b in self.controls)
        return (self.tab_left() + int(84 * S) + sp + self.plus_btn.width() + sp
                + self.tabs_btn.width() + int(6 * S) + controls + int(4 * S))
    def tab_top(self):
        return int(4 * S)
    def tab_left(self):
        return MARGIN                  # tabs line up with the list's own left edge
    def caption_widgets(self):
        """What counts as empty bar space (window drag / double-click to
        maximise) rather than something clickable."""
        return (self, self.tab_scroll, self.tab_scroll.viewport(), self.tabbar)
    def layout_children(self, animate=False):
        h, sp = self.height(), int(2 * S)
        x = self.width() - int(4 * S)
        for b in reversed(self.controls):
            x -= b.width()
            b.move(x, (h - b.height()) // 2)
            x -= sp
        left, top = self.tab_left(), self.tab_top()
        avail = max(0, x - int(6 * S) - left - sp - self.plus_btn.width())
        overflow = self.tabbar.content_width(avail) > avail
        if overflow:
            avail = max(0, avail - sp - self.tabs_btn.width())
        content = self.tabbar.relayout(avail, h - top, animate)
        shown = min(content, avail)
        self.tab_scroll.setGeometry(left, top, shown, h - top)
        y = top + (h - top - self.plus_btn.height()) // 2
        self.plus_btn.move(left + shown + sp, y)
        self.tabs_btn.move(self.plus_btn.x() + self.plus_btn.width() + sp, y)
        self.tabs_btn.setVisible(overflow)
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.layout_children()
    def mousePressEvent(self, e):
        # Only reached where the native caption isn't (non-Windows)
        if e.button() == Qt.LeftButton:
            self.win.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.toggle_max()
class Chip(QLabel):
    def __init__(self, text, on_click):
        super().__init__(text)
        self.on_click = on_click
        self.setFont(QFont(FONT, 8))
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(22)
        self.setMinimumWidth(32)
        self.set_selected(False)
    def set_selected(self, on):
        self.setAttribute(Qt.WA_Hover)
        if on:
            self.setStyleSheet(f"QLabel {{ background: {ACCENT}; color: #1b1f22; "
                               "border-radius: 5px; padding: 0 6px; }")
        else:
            self.setStyleSheet("QLabel { background: #3b4146; color: #ffffff; "
                               "border-radius: 5px; padding: 0 6px; } "
                               "QLabel:hover { background: #474e54; }")
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_click()
class SettingsPopup(QFrame):
    """Small dropdown with a live size slider. Fixed size so it doesn't jump
    around while you drag the slider."""
    def __init__(self, win):
        super().__init__(win, Qt.Popup)
        no_system_shadow(self)
        self.win = win
        self.setFixedWidth(230 + 2 * SHADOW)
        self.setStyleSheet(f"""
SettingsPopup {{ background: transparent; border: none; }}
QLabel {{ color: {TEXT}; border: none; background: transparent; }}
QLabel#dim {{ color: {TEXT_DONE}; }}
QSlider {{ border: none; background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: #4a5055; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #ffffff; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px; }}
QLabel#link {{ color: {ACCENT}; }}
QLabel#link:hover {{ text-decoration: underline; }}
""")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14 + SHADOW, 10 + SHADOW - 2, 14 + SHADOW, 12 + SHADOW + 2)
        lay.setSpacing(6)
        row = QHBoxLayout()
        title = QLabel("Size")
        title.setFont(QFont(FONT, 9, QFont.Weight.DemiBold))
        self.value = QLabel()
        self.value.setObjectName("dim")
        self.value.setFont(QFont(FONT, 9))
        row.addWidget(title)
        row.addStretch()
        row.addWidget(self.value)
        lay.addLayout(row)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(SCALE_MIN, SCALE_MAX)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(int(round(S * 100)))
        self.slider.valueChanged.connect(self.changed)
        lay.addWidget(self.slider)
        reset_row = QHBoxLayout()
        reset = QLabel("Reset to 100%")
        reset.setObjectName("link")
        reset.setFont(QFont(FONT, 8))
        reset.setCursor(Qt.PointingHandCursor)
        reset.mousePressEvent = lambda e: self.slider.setValue(100)
        reset_row.addWidget(reset)
        reset_row.addStretch()
        lay.addLayout(reset_row)
        lay.addSpacing(4)
        # Each tab has its own colour (right-click a tab -> Colour) - that's
        # the window/list background. The top bar itself (behind the tabs)
        # is separate: one flat, shared colour, set here.
        brow = QHBoxLayout()
        brow.addWidget(self.heading("Bar colour"))
        brow.addStretch()
        self.bar_swatch = _Preset(self, TOPBAR_BG[0])
        self.bar_swatch.mousePressEvent = lambda e: self.pick_bar_colour()
        brow.addWidget(self.bar_swatch)
        lay.addLayout(brow)
        lay.addSpacing(4)
        trow = QHBoxLayout()
        trow.addWidget(self.heading("Group colour strength"))
        trow.addStretch()
        self.tint_val = QLabel()
        self.tint_val.setObjectName("dim")
        self.tint_val.setFont(QFont(FONT, 9))
        trow.addWidget(self.tint_val)
        lay.addLayout(trow)
        self.tint = QSlider(Qt.Horizontal)
        self.tint.setRange(10, 80)
        self.tint.setValue(int(round(TINT[0] * 100)))
        self.tint.valueChanged.connect(self.tint_changed)
        lay.addWidget(self.tint)
        self.tint_val.setText(f"{self.tint.value()}%")
        lay.addSpacing(4)
        lay.addWidget(self.heading("Auto-archive completed after"))
        chips = QHBoxLayout()
        chips.setSpacing(4)
        self.chips = []
        for days in ARCHIVE_CHOICES:
            chip = Chip("Off" if days == 0 else f"{days}d", lambda d=days: self.pick_archive(d))
            chip.days = days
            self.chips.append(chip)
            chips.addWidget(chip)
        chips.addStretch()
        lay.addLayout(chips)
        self.refresh_choices()
        lay.addSpacing(4)
        links = QHBoxLayout()
        reset = QLabel("Open archive")
        reset.setObjectName("link")
        reset.setFont(QFont(FONT, 8))
        reset.setCursor(Qt.PointingHandCursor)
        reset.mousePressEvent = lambda e: (self.close(), open_archive(win))
        links.addWidget(reset)
        links.addStretch()
        lay.addLayout(links)
        self.changed(self.slider.value())
    def paintEvent(self, _):
        p = QPainter(self)
        paint_panel(p, QRectF(self.rect()).adjusted(SHADOW, SHADOW - 2, -SHADOW, -SHADOW - 2))
    def hideEvent(self, e):
        self.win.popup_closed_at = time.monotonic()
        super().hideEvent(e)
    def heading(self, text):
        lab = QLabel(text)
        lab.setFont(QFont(FONT, 9, QFont.Weight.DemiBold))
        return lab
    def pick_archive(self, days):
        self.win.set_autoarchive(days)
        self.refresh_choices()
    def pick_bar_colour(self):
        anchor = QRect(self.bar_swatch.mapToGlobal(QPoint(0, 0)), self.bar_swatch.size())
        old = TOPBAR_BG[0]
        def live(colour):
            set_topbar_colour(colour)
        c = pick_colour(self.win, old, "Bar colour", anchor, background=True,
                        live=live, quick_colours=TOPBAR_QUICK)
        set_topbar_colour(c if c else old)
        self.bar_swatch.hexc = TOPBAR_BG[0]
        self.bar_swatch.update()
        if c:
            global_save()
    def tint_changed(self, v):
        self.tint_val.setText(f"{v}%")
        self.win.set_tint(v / 100)
    def refresh_choices(self):
        for c in self.chips:
            c.set_selected(c.days == self.win.autoarchive)
    def changed(self, v):
        v = int(round(v / 5.0) * 5)
        self.value.setText(f"{v}%")
        self.win.set_ui_scale(v / 100)
# ------------------------------------------------------------------
# TABS / MULTIPLE WINDOWS
# ------------------------------------------------------------------
WINDOWS = []                  # every live Window, in creation order
DELETED_TABS = []             # tabs deleted this session, newest last - for Ctrl+Z
TAB_ID_COUNTER = [1]          # next id to hand out to a brand-new tab
def alloc_tab_id():
    tid = TAB_ID_COUNTER[0]
    TAB_ID_COUNTER[0] += 1
    return tid
def window_by_pyid(pyid_str):
    return next((w for w in WINDOWS if str(id(w)) == pyid_str), None)
def tab_chip_at_global_pos(global_pos, exclude=None):
    """(window, tabid) the cursor is currently over, checking every open
    window's tab bar - used while dragging a GROUP so it can be dropped
    onto a tab (same window, a different tab; or a different window
    entirely) to move the whole group there. `exclude` is the (window,
    tabid) the group already lives in - hovering back over that one isn't
    a move, it's just normal in-board reordering."""
    for w in WINDOWS:
        bar = w.tabbar
        # The row can be wider than what's shown (it scrolls): a chip
        # scrolled out of view must never count as a drop target.
        viewport = bar.scroll.viewport()
        if not viewport.rect().contains(viewport.mapFromGlobal(global_pos)):
            continue
        local = bar.mapFromGlobal(global_pos)
        if not bar.rect().contains(local):
            continue
        for tabid, chip in bar.chips.items():
            if chip.geometry().contains(local):
                if exclude is not None and (w, tabid) == exclude:
                    return None, None
                return w, tabid
    return None, None
def _unique_group_name(name, existing):
    if name not in existing:
        return name
    n = 2
    while f"{name} ({n})" in existing:
        n += 1
    return f"{name} ({n})"
def most_recently_focused_other(exclude):
    """Which window a closing window's tabs should move into: whichever
    other open window was focused most recently, falling back to the first
    one still open."""
    others = [w for w in WINDOWS if w is not exclude]
    if not others:
        return None
    others.sort(key=lambda w: getattr(w, "_last_focus_at", 0), reverse=True)
    return others[0]
def global_save():
    """Writes the ENTIRE app - every window, every tab in it - to
    TodoList.txt in one go (the data file is shared by the whole app, not
    per-window). Returns True/False; callers must never treat False as a
    successful save."""
    if not WINDOWS:
        return True
    windows_out, tabs_out = [], {}
    for w in WINDOWS:
        if w.board is None:
            continue              # still loading - nothing to contribute yet
        for tid in w.tab_order:
            if tid == w.active_tab:
                tabs_out[tid] = w.export_active_tab_data()
            else:
                tabs_out[tid] = w.tab_data.get(tid) or _empty_tab(
                    w.tab_meta[tid]["name"], w.tab_meta[tid]["colour"])
            tabs_out[tid]["name"] = w.tab_meta[tid]["name"]
            tabs_out[tid]["colour"] = w.tab_meta[tid]["colour"]
        windows_out.append({"geometry": w.current_geometry(), "zoomed": w.isMaximized(),
                            "pinned": w.pinned, "tabs": list(w.tab_order),
                            "active": w.active_tab})
    if not windows_out:
        return True
    primary = WINDOWS[0]
    ok = save_app_state(windows_out, tabs_out, S, primary.autoarchive,
                        TINT[0], TAB_ID_COUNTER[0], TOPBAR_BG[0])
    if not ok:
        primary._report_save_failure()
        QTimer.singleShot(3000, primary.save_timer.start)
    return ok
def set_topbar_colour(colour):
    """Changes the shared top-bar background (behind the tabs) and repaints
    it in every open window - this one colour isn't per-tab/per-window."""
    TOPBAR_BG[0] = colour or TOPBAR_BG_DEFAULT
    for w in WINDOWS:
        w.update()
def used_files_everywhere():
    """Union of attachment file names referenced by any tab in any open
    window - what cleanup_attachments() is allowed to keep."""
    used = set()
    for w in WINDOWS:
        if w.board is None:
            continue
        for tid in w.tab_order:
            if tid == w.active_tab:
                used |= w.board.used_files()
            else:
                data = w.tab_data.get(tid)
                if data:
                    for _, tasks in data["groups"]:
                        for t in tasks:
                            used.update(t.get("files") or [])
                    for t in data["done"]:
                        used.update(t.get("files") or [])
    return used
def any_window_data_unsafe():
    """True if any open window loaded its data incompletely/partially, or
    failed to load at all - in that case cleanup must be skipped entirely,
    everywhere, since we can't be sure what's really still referenced."""
    return any((not w.load_ok or w.load_partial) for w in WINDOWS)
def shutdown_everything():
    """F2's second press, or closing the very last window: one consolidated
    save across every window/tab, attachment cleanup, then quits the whole
    application. Unlike a single window's closeEvent, this never refuses to
    proceed - matching 'F2 saves and closes it completely'."""
    for w in WINDOWS:
        w.commit_edits()
        w.save_timer.stop()
    ok = global_save()
    if ok and not any_window_data_unsafe():
        cleanup_attachments(used_files_everywhere())
    for w in WINDOWS:
        w.history.clear()
        w.quitting = True
    release_instance()
    QTimer.singleShot(0, QApplication.quit)
# ------------------------------------------------------------------
# TAB BAR (tabs across the top of each window)
# ------------------------------------------------------------------
TAB_GAP_BASE = 4         # space between neighbouring tabs
TAB_PAD_BASE = 12        # space either side of a tab's name
TAB_MIN_W_BASE = 56      # tabs shrink to this before the row starts scrolling
TAB_MAX_W_BASE = 180
TAB_TEAR_BASE = 30       # how far above / below the bar a dragged tab tears out
TAB_INSET_BASE = 3       # other tabs stop this far above the list
def tab_flare():
    return 8 * S
def tab_shape(r, rad):
    """The open tab: rounded top corners, square bottom (it sits on the list
    below)."""
    path = QPainterPath()
    path.moveTo(r.left(), r.bottom())
    path.lineTo(r.left(), r.top() + rad)
    path.quadTo(r.left(), r.top(), r.left() + rad, r.top())
    path.lineTo(r.right() - rad, r.top())
    path.quadTo(r.right(), r.top(), r.right(), r.top() + rad)
    path.lineTo(r.right(), r.bottom())
    path.closeSubpath()
    return path
def tab_flares(r):
    """The two small concave curves either side of the open tab's foot,
    sweeping out into the list - so the tab grows out of the list instead
    of meeting it at a hard right angle. Painted by the window as part of
    the list's own background."""
    f = tab_flare()
    path = QPainterPath()
    for edge, out in ((r.left(), -f), (r.right(), f)):
        path.moveTo(edge + out, r.bottom())
        path.quadTo(edge, r.bottom(), edge, r.bottom() - f)
        path.lineTo(edge, r.bottom())
        path.closeSubpath()
    return path
def tab_bar_at_global_pos(global_pos, exclude=None):
    """The TabBar whose top-bar row is under the cursor (dragging a tab onto
    another window). If windows overlap, the most recently used one wins."""
    hits = []
    for w in WINDOWS:
        if w is exclude or not w.isVisible() or w.isMinimized():
            continue
        local = w.bar.mapFromGlobal(global_pos)
        if w.bar.rect().contains(local):
            hits.append(w)
    if not hits:
        return None
    hits.sort(key=lambda w: getattr(w, "_last_focus_at", 0), reverse=True)
    return hits[0].tabbar
class TabChip(QWidget):
    """One tab. Press selects it (any tab, open or not); dragging it slides
    it along the row (the others make room as it passes them), or out of
    the row to move it to another window or tear it off into a new one.
    Double-click renames it; right-click for the menu."""
    def __init__(self, bar, tabid):
        super().__init__(bar)
        self.bar = bar
        self.tabid = tabid
        self.hover = False
        self.drop_hover = False    # a dragged GROUP is hovering over this tab
        self.renaming = False      # a rename LineEdit is open on top of this chip
        self.lifted = False        # dragged out of the row: drawn by the ghost instead
        self._press = None         # (global, local) position of a left-button press
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(150)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setCursor(Qt.PointingHandCursor)
        self.apply_scale()
    def meta(self):
        return self.bar.win.tab_meta.get(self.tabid, {"name": "Tab", "colour": ACCENT})
    def is_active(self):
        return self.tabid == self.bar.win.active_tab
    def apply_scale(self):
        self.font_ = F(10, bold=True)
    def ideal_width(self):
        w = QFontMetrics(self.font_).horizontalAdvance(self.meta()["name"]) \
            + 2 * int(TAB_PAD_BASE * S)
        return int(min(max(w, TAB_MIN_W_BASE * S), TAB_MAX_W_BASE * S))
    def _shape(self, open_tab):
        r = QRectF(self.rect())
        if open_tab:
            return r, tab_shape(r, RADIUS)
        # Other tabs float just above the list, rounded all round, so only
        # the open one visibly joins it.
        r = r.adjusted(0, 0, 0, -int(TAB_INSET_BASE * S))
        path = QPainterPath()
        path.addRoundedRect(r, RADIUS, RADIUS)
        return r, path
    def _paint(self, p, fill, text_colour, open_tab):
        p.setRenderHint(QPainter.Antialiasing)
        r, path = self._shape(open_tab)
        p.fillPath(path, fill)
        r = QRectF(self.rect())          # same text line on every tab
        if not self.renaming:
            # The rename box is transparent - drawing the name under it too
            # would double up the text being typed.
            pad = int(TAB_PAD_BASE * S)
            p.setFont(self.font_)
            p.setPen(QColor(text_colour))
            name = QFontMetrics(self.font_).elidedText(
                self.meta()["name"], Qt.ElideRight, max(0, self.width() - 2 * pad))
            p.drawText(r.adjusted(pad, 0, -pad, 0), Qt.AlignVCenter | Qt.AlignLeft, name)
        if self.drop_hover:
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), RADIUS, RADIUS)
    def paintEvent(self, _):
        if self.lifted:
            return
        p = QPainter(self)
        colour = self.meta()["colour"] or ACCENT
        if self.is_active():
            # Exactly the list's own background (same gradient, same
            # origin), so the open tab and the list are one surface.
            win = self.bar.win
            fill = QBrush(win.list_gradient())
            off = self.mapTo(win, QPoint(0, 0))
            fill.setTransform(QTransform.fromTranslate(-off.x(), -off.y()))
            self._paint(p, fill, TEXT, True)
        else:
            fill = QColor(mix(TINT_BASE, colour, 0.75 if self.hover else 0.55))
            self._paint(p, fill, TEXT if self.hover else TEXT_SUB, False)
    def ghost_pixmap(self):
        """The tab as it looks while being carried outside the row."""
        dpr = self.devicePixelRatioF()
        pm = QPixmap(self.size() * dpr)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        lifted, self.lifted = self.lifted, False
        self._paint(p, QColor(self.meta()["colour"] or ACCENT), TEXT, False)
        self.lifted = lifted
        p.end()
        return pm
    def moveEvent(self, e):
        super().moveEvent(e)
        if self.is_active():
            self.bar.win.update()      # the window leaves a hole in the top strip for it
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.is_active():
            self.bar.win.update()
    def enterEvent(self, _):
        self.hover = True
        self.update()
    def leaveEvent(self, _):
        self.hover = False
        self.update()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = (e.globalPosition().toPoint(), e.position().toPoint())
            self.bar.win.switch_tab(self.tabid)
            self.bar.scroll_into_view(self.tabid)
    def mouseMoveEvent(self, e):
        if self.bar._drag is not None:
            self.bar.mouseMoveEvent(e)     # in case the bar's grab didn't take
            return
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.globalPosition().toPoint() - self._press[0]).manhattanLength() < 6:
            return
        press, self._press = self._press, None
        self.bar.begin_drag(self, press[1], e.globalPosition().toPoint())
    def mouseReleaseEvent(self, e):
        self._press = None
        if self.bar._drag is not None:
            self.bar.mouseReleaseEvent(e)
    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = None
            self.bar.start_rename(self.tabid)
    def contextMenuEvent(self, e):
        self.bar.tab_context_menu(self.tabid, e.globalPos())
class TabGhost(QWidget):
    """Picture of a tab following the cursor once it's dragged out of its
    row - the only image shown (no OS drag cursor on top of it)."""
    def __init__(self, pixmap):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.pm = pixmap
        self.pad = int(10 * S)
        size = pixmap.size() / pixmap.devicePixelRatio()
        self.resize(size.width() + 2 * self.pad, size.height() + 2 * self.pad)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        inner = QRectF(self.rect()).adjusted(self.pad, self.pad, -self.pad, -self.pad)
        paint_shadow(p, inner, RADIUS, self.pad)
        p.setOpacity(0.95)
        p.drawPixmap(inner.topLeft(), self.pm)
class TabBar(QWidget):
    """The row of tabs, inside TopBar's TabScrollArea. Tabs sit side by side
    (no overlap) and shrink, Chrome-style, to share the room there is;
    only past their minimum width does the row scroll.
    Chips live as long as their tab does - refresh() adds / removes /
    re-measures them rather than rebuilding the row - so a tab pressed a
    moment ago is still the same widget when the drag starts.
    Dragging is handled here directly with a mouse grab (no QDrag): along
    the row it reorders live; pulled out of the row it becomes a floating
    ghost that can be dropped on another window's tab row, or anywhere else
    to tear it off into its own window. A window's only tab drags the whole
    window instead (dropping it on another window's tabs merges them)."""
    def __init__(self, top):
        super().__init__(top)
        self.top = top
        self.win = top.win
        self.scroll = top.tab_scroll
        self.chips = {}
        self.rename_edit = None
        self._rename_tabid = None
        self._avail = 0
        self._height = int(30 * S)
        self._incoming = None      # (index, width): room made for a tab from another window
        self._drag = None
        self._drag_timer = QTimer(self)
        self._drag_timer.setInterval(16)
        self._drag_timer.timeout.connect(self._drag_tick)
    def apply_scale(self):
        for c in self.chips.values():
            c.apply_scale()
        self.refresh(animate=False)
    # ---------- layout ----------
    def refresh(self, animate=True):
        """Brings the chips in line with win.tab_order / tab_meta, then lays
        the whole bar out again (the '+' follows the row's new width)."""
        order = self.win.tab_order
        for tabid in [t for t in self.chips if t not in order]:
            c = self.chips.pop(tabid)
            if self._drag and self._drag["chip"] is c:
                self._finish_drag()
            c.hide()
            c.deleteLater()
        for tabid in order:
            c = self.chips.get(tabid)
            if c is None:
                c = self.chips[tabid] = TabChip(self, tabid)
                c.show()
            c.setToolTip(c.meta()["name"])
            c.update()
        self.top.layout_children(animate)
        self.scroll_into_view(self.win.active_tab)
        self.win.update()
    def _widths(self, tabids, avail):
        """Each tab's width. The open tab always gets its whole name (as far
        as the row allows); the others share what's left - narrow ones keep
        their size, wide ones shrink equally, down to a minimum."""
        gap = int(TAB_GAP_BASE * S)
        low = int(TAB_MIN_W_BASE * S)
        ideal = [self.chips[t].ideal_width() for t in tabids]
        if self._incoming:
            ideal.append(self._incoming[1])
        n = len(ideal)
        budget = avail - gap * max(0, n - 1)
        if not n or sum(ideal) <= budget:
            return ideal
        active = self.win.active_tab
        fixed = [i for i, t in enumerate(tabids) if t == active]
        for i in fixed:
            ideal[i] = max(low, min(ideal[i], avail))     # others scroll if need be
        shared = [i for i in range(n) if i not in fixed]
        left = budget - sum(ideal[i] for i in fixed)
        cap, rest = None, len(shared)
        for w in sorted(ideal[i] for i in shared):
            share = left / rest
            if w > share:
                cap = share
                break
            left -= w
            rest -= 1
        widths = list(ideal)
        if cap is not None:
            for i in shared:
                widths[i] = int(max(low, min(ideal[i], cap)))
        return widths
    def _slots(self, avail=None):
        """{tabid: (x, width)} and the total width, for the row as it
        currently stands (a tab lifted out of it leaves no gap; room made
        for an incoming tab does)."""
        tabids = [t for t in self.win.tab_order if t in self.chips
                  and not self.chips[t].lifted]
        widths = self._widths(tabids, self._avail if avail is None else avail)
        incoming_w = widths.pop() if self._incoming else 0
        gap = int(TAB_GAP_BASE * S)
        slots, x = {}, 0
        for i, (t, w) in enumerate(zip(tabids, widths)):
            if self._incoming and i == self._incoming[0]:
                x += incoming_w + gap
            slots[t] = (x, w)
            x += w + gap
        if self._incoming and self._incoming[0] >= len(tabids):
            x += incoming_w + gap
        return slots, max(0, x - gap)
    def content_width(self, avail):
        """How wide the row would be if given `avail` (nothing moves)."""
        return self._slots(avail)[1]
    def relayout(self, avail, height, animate=True):
        """Called by TopBar.layout_children() with the room it can give the
        row; returns the width the row actually needs."""
        self._avail, self._height = avail, height
        slots, content = self._slots()
        dragged = self._drag["chip"] if self._drag else None
        for t, (x, w) in slots.items():
            c = self.chips[t]
            c.resize(w, height)
            if c is dragged:
                continue           # follows the cursor, not its slot
            target = QPoint(x, 0)
            if animate and c.isVisible() and c.pos() != target:
                c.anim.stop()
                c.anim.setStartValue(c.pos())
                c.anim.setEndValue(target)
                c.anim.start()
            else:
                c.anim.stop()
                c.move(target)
        if self.rename_edit is not None and self._rename_tabid in slots:
            x, w = slots[self._rename_tabid]
            self.rename_edit.setGeometry(x, 0, w, height)
        self.resize(content, height)
        return content
    def scroll_into_view(self, tabid):
        slots, _ = self._slots()
        if tabid not in slots:
            return
        x, w = slots[tabid]
        bar = self.scroll.horizontalScrollBar()
        view = self.scroll.viewport().width()
        if x < bar.value():
            bar.setValue(x)
        elif x + w > bar.value() + view:
            bar.setValue(x + w - view)
    def index_at(self, x):
        """Where in this row a tab dropped at bar x would go."""
        slots, _ = self._slots()
        order = [t for t in self.win.tab_order if t in slots]
        return sum(1 for t in order if slots[t][0] + slots[t][1] / 2 < x)
    def set_incoming(self, index, width):
        value = None if index is None else (index, width)
        if value != self._incoming:
            self._incoming = value
            self.top.layout_children(animate=True)
    # ---------- dragging ----------
    def begin_drag(self, chip, local, global_pos):
        self.commit_rename_if_open()
        self._drag = {"chip": chip, "tabid": chip.tabid, "dx": local.x(), "dy": local.y(),
                      "mode": "row", "ghost": None, "target": None,
                      "win_offset": None}
        chip.anim.stop()
        chip.raise_()
        chip.setCursor(Qt.ClosedHandCursor)
        self.grabMouse(Qt.ClosedHandCursor)
        self._drag_timer.start()
        self._drag_move(global_pos)
    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        if not (e.buttons() & Qt.LeftButton):
            self._end_drag(e.globalPosition().toPoint())   # missed the release
            return
        self._drag_move(e.globalPosition().toPoint())
    def mouseReleaseEvent(self, e):
        if self._drag is not None and e.button() == Qt.LeftButton:
            self._end_drag(e.globalPosition().toPoint())
    def _single(self):
        return len(self.win.tab_order) == 1
    def _torn(self, global_pos):
        """Far enough above / below this window's top bar (or right out of
        the window sideways) to count as pulling the tab out of the row."""
        local = self.top.mapFromGlobal(global_pos)
        tear = int(TAB_TEAR_BASE * S)
        return (local.y() < -tear or local.y() > self.top.height() + tear
                or not self.win.rect().contains(self.win.mapFromGlobal(global_pos)))
    def _drag_move(self, global_pos):
        d = self._drag
        if d["mode"] == "row":
            if self._torn(global_pos):
                self._lift(global_pos)
            else:
                self._slide(global_pos)
                return
        # Out of the row: over another window's tabs, back over our own, or loose
        target = tab_bar_at_global_pos(global_pos, exclude=self.win if self._single() else None)
        if target is self and not self._torn(global_pos):
            self._land(global_pos)
            return
        if target is self:
            target = None
        if d["target"] is not target:
            if d["target"] is not None:
                d["target"].set_incoming(None, 0)
            d["target"] = target
        if target is not None:
            target.set_incoming(target.index_at(target.mapFromGlobal(global_pos).x()),
                                d["chip"].width())
            if d["mode"] == "window":
                target.win.raise_()
        if d["mode"] == "ghost":
            d["ghost"].move(global_pos - QPoint(d["dx"], d["dy"]) - QPoint(d["ghost"].pad,
                                                                             d["ghost"].pad))
        elif d["mode"] == "window":
            self.win.move(global_pos - d["win_offset"])
    def _slide(self, global_pos):
        """Along the row: the tab follows the cursor, the others make room."""
        d, chip = self._drag, self._drag["chip"]
        slots, content = self._slots()
        x = self.mapFromGlobal(global_pos).x() - d["dx"]
        x = max(0, min(x, content - chip.width()))
        chip.move(x, 0)
        # A neighbour steps aside once the dragged tab's leading edge passes
        # its middle (right edge going right, left edge going left).
        order = self.win.tab_order
        mine = order.index(d["tabid"])
        index = 0
        for i, t in enumerate(order):
            if t == d["tabid"]:
                continue
            centre = slots[t][0] + slots[t][1] / 2
            if (centre <= x) if i < mine else (centre < x + chip.width()):
                index += 1
        if self.win.tab_order.index(d["tabid"]) != index:
            self.win.tab_order.remove(d["tabid"])
            self.win.tab_order.insert(index, d["tabid"])
            self.top.layout_children(animate=True)
    def _drag_tick(self):
        """Keeps the row scrolling while a tab is held against either end."""
        d = self._drag
        if d is None or d["mode"] != "row":
            return
        vp = self.scroll.viewport()
        x = vp.mapFromGlobal(QCursor.pos()).x()
        edge, step = int(24 * S), int(8 * S)
        bar = self.scroll.horizontalScrollBar()
        if x < edge and bar.value() > bar.minimum():
            bar.setValue(bar.value() - step)
        elif x > vp.width() - edge and bar.value() < bar.maximum():
            bar.setValue(bar.value() + step)
        else:
            return
        self._slide(QCursor.pos())
    def _lift(self, global_pos):
        d, chip = self._drag, self._drag["chip"]
        if self._single():
            # The only tab: carry the whole window, like a browser does.
            if self.win.isMaximized():
                self.win.showNormal()
            d["mode"] = "window"
            d["win_offset"] = chip.mapTo(self.win, QPoint(d["dx"], d["dy"]))
            return
        d["mode"] = "ghost"
        d["ghost"] = TabGhost(chip.ghost_pixmap())
        chip.lifted = True
        chip.update()
        self.top.layout_children(animate=True)     # the others close the gap
        self.win.update()
        d["ghost"].move(global_pos - QPoint(d["dx"] + d["ghost"].pad, d["dy"] + d["ghost"].pad))
        d["ghost"].show()
    def _land(self, global_pos):
        """A lifted tab brought back over its own row."""
        d, chip = self._drag, self._drag["chip"]
        if d["ghost"] is not None:
            d["ghost"].hide()
            d["ghost"].deleteLater()
            d["ghost"] = None
        d["mode"] = "row"
        chip.lifted = False
        chip.raise_()
        self.win.update()
        self._slide(global_pos)
        self.top.layout_children(animate=True)
    def _finish_drag(self):
        """Ends the drag's bookkeeping (grab, timer, ghost, markers) without
        deciding where the tab goes. Returns the drag's state."""
        d, self._drag = self._drag, None
        self._drag_timer.stop()
        self.releaseMouse()
        if d["ghost"] is not None:
            d["ghost"].hide()
            d["ghost"].deleteLater()
        if d["target"] is not None:
            d["target"].set_incoming(None, 0)
        d["chip"].lifted = False
        d["chip"].setCursor(Qt.PointingHandCursor)
        return d
    def _end_drag(self, global_pos):
        d = self._finish_drag()
        tabid, target = d["tabid"], d["target"]
        if d["mode"] == "row":
            self.top.layout_children(animate=True)    # settle into its slot
            self.win.update()
            global_save()
            return
        if target is not None and target.win in WINDOWS:
            index = target.index_at(target.mapFromGlobal(global_pos).x())
            move_tab_to_window(self.win, tabid, target.win, index)
            return
        if d["mode"] == "window":
            global_save()                  # just moved the window
            return
        self.win.detach_tab_to_new_window(tabid, global_pos - QPoint(d["dx"], d["dy"]))
    def all_tabs_menu(self):
        """Every tab in this window, to jump to - for when they don't all
        fit in the row. The open one is marked."""
        self.commit_rename_if_open()
        btn = self.top.tabs_btn
        menu = RoundMenu(self)
        actions = {}
        for tabid in self.win.tab_order:
            meta = self.win.tab_meta[tabid]
            act = menu.addAction(colour_icon(meta["colour"] or ACCENT,
                                             tabid == self.win.active_tab), meta["name"])
            actions[act] = tabid
        chosen = menu.open_at(btn.mapToGlobal(QPoint(0, btn.height())))
        if chosen in actions:
            self.win.switch_tab(actions[chosen])
            self.scroll_into_view(actions[chosen])
    # ---------- per-tab menu / rename ----------
    def tab_context_menu(self, tabid, global_pos):
        self.commit_rename_if_open()
        win = self.win
        meta = win.tab_meta[tabid]
        menu = RoundMenu(self)
        act_rename = menu.addAction(menu_icon("pen"), "Rename tab")
        colour_menu = menu.sub("Colour", menu_icon("palette"))
        colour_actions = {}
        presets = [h for _, h in TAB_COLOURS]
        for name, hexc in TAB_COLOURS:
            act = colour_menu.addAction(colour_icon(hexc, meta["colour"] == hexc), name)
            colour_actions[act] = hexc
        colour_menu.addSeparator()
        custom_now = meta["colour"] if meta["colour"] not in presets else None
        act_custom = colour_menu.addAction(
            colour_icon(custom_now, True) if custom_now else menu_icon("palette"),
            "Custom colour…")
        act_delete = None
        total_tabs = sum(len(w.tab_order) for w in WINDOWS)
        if total_tabs > 1:
            menu.addSeparator()
            act_delete = menu.addAction(menu_icon("bin", OVERDUE), "Delete tab")
        chosen = menu.open_at(global_pos)
        if chosen is None:
            return
        if chosen in colour_actions:
            win.set_tab_colour(tabid, colour_actions[chosen])
            global_save()
        elif chosen == act_custom:
            chip = self.chips.get(tabid)
            anchor = QRect(chip.mapToGlobal(QPoint(0, 0)), chip.size()) if chip else \
                point_rect(global_pos)
            old = meta["colour"]
            def live(colour):
                win.set_tab_colour(tabid, colour)
            c = pick_colour(win, old, f"Colour for {meta['name']}", anchor, live=live,
                            background=True, quick_colours=[h for _, h in TAB_COLOURS])
            win.set_tab_colour(tabid, old)     # put back unless actually confirmed
            if c:
                win.set_tab_colour(tabid, c)
                global_save()
        elif chosen == act_rename:
            self.start_rename(tabid)
        elif chosen == act_delete:
            if win.board is not None and win.board.confirm(
                    "Delete tab", f"Delete the '{meta['name']}' tab and everything in it?",
                    "Delete"):
                win.delete_tab(tabid)
                global_save()
    def start_rename(self, tabid):
        # Clicking the '+' (or anything else that never takes focus) doesn't
        # fire the old box's focus-lost, so close any open one explicitly.
        self.commit_rename_if_open()
        chip = self.chips.get(tabid)
        if chip is None:
            return
        self.scroll_into_view(tabid)
        edit = LineEdit(self, 10, bold=True)
        pad = int(TAB_PAD_BASE * S)
        edit.setTextMargins(pad, 0, pad, 0)       # text stays exactly where the name was
        edit.setGeometry(chip.geometry())
        edit.setText(self.win.tab_meta[tabid]["name"])
        edit.show()
        edit.raise_()
        self.rename_edit = edit
        self._rename_tabid = tabid
        chip.renaming = True
        chip.update()
        edit.returnPressed.connect(lambda: self.finish_rename(False))
        edit.escaped.connect(lambda: self.finish_rename(True))
        edit.focus_lost.connect(lambda: self.finish_rename(False))
        edit.setFocus(Qt.OtherFocusReason)
        edit.selectAll()
    def finish_rename(self, cancel=False):
        if self.rename_edit is None:
            return
        edit, tabid = self.rename_edit, self._rename_tabid
        self.rename_edit = None
        self._rename_tabid = None
        edit.hide()
        edit.deleteLater()
        chip = self.chips.get(tabid)
        if chip is not None:
            chip.renaming = False
            chip.update()
        if not cancel:
            meta = self.win.tab_meta.get(tabid)
            if meta is not None:
                new_name = clean(edit.text()) or meta["name"]
                if new_name != meta["name"]:
                    self.win.rename_tab(tabid, new_name)
                    global_save()
    def commit_rename_if_open(self):
        """Finishes (keeping whatever was typed) any rename box that's
        still open - called before anything else that changes the tab bar,
        so a stale rename box is never left floating over the wrong tab."""
        if self.rename_edit is not None:
            self.finish_rename(False)
def move_tab_to_window(src, tabid, dst, index):
    """A tab dropped on another window's tab row: it moves there (opened),
    and the window it came from closes if that was its last tab."""
    data, meta = src.pop_tab_for_transfer(tabid)
    dst.insert_tab(tabid, data, meta, index=index, activate=True)
    if not src.tab_order:
        src.close_emptied_by_transfer()
    else:
        src.tabbar.refresh()
    dst.raise_()
    dst.activateWindow()
    global_save()
# ------------------------------------------------------------------
# MAIN WINDOW
# ------------------------------------------------------------------
class Window(QWidget):
    def __init__(self, win_state=None, tabs_state=None, detached=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        # See-through window so the corners can be drawn smooth (anti-aliased).
        # The corners are painted almost-transparent (not fully), so clicks
        # there still land on the list, never on the window behind.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setWindowTitle(WINDOW_TITLE)
        if os.path.exists(ICON_FILE):
            self.setWindowIcon(QIcon(ICON_FILE))
        self.setMinimumSize(220, 160)
        self.setMouseTracking(True)
        # Maximise is always the real Windows state (button, double-click
        # on the bar, Win+Up, dragging to the top edge alike), so Windows
        # itself handles restoring, dragging a maximised window off the top,
        # and snapping. _normal_geom is the last un-maximised geometry, the
        # one saved to file.
        self._normal_geom = None
        # ---- figure out which tab(s) this window starts with ----
        if detached is not None:
            # Torn off a tab from another window: starts with just that one.
            tabid, tdata, tmeta = detached
            self.tab_order = [tabid]
            self.tab_meta = {tabid: tmeta}
            self.tab_data = {}
            self.active_tab = tabid
            active_tab_data = tdata
            geometry, zoomed, pinned = None, False, False
        else:
            win_state = win_state or {"geometry": None, "zoomed": False,
                                      "pinned": False, "tabs": [0], "active": 0}
            tabs_state = tabs_state or {0: _empty_tab(WORK_TAB_NAME, default_tab_colour(0))}
            self.tab_order = list(win_state["tabs"]) or [0]
            self.active_tab = win_state["active"] if win_state["active"] in self.tab_order \
                else self.tab_order[0]
            self.tab_meta = {tid: {"name": tabs_state[tid]["name"],
                                   "colour": tabs_state[tid]["colour"]}
                             for tid in self.tab_order if tid in tabs_state}
            self.tab_data = {tid: tabs_state[tid] for tid in self.tab_order
                             if tid != self.active_tab and tid in tabs_state}
            active_tab_data = tabs_state.get(self.active_tab) or \
                _empty_tab(WORK_TAB_NAME, default_tab_colour(0))
            geometry, zoomed, pinned = (win_state["geometry"], win_state["zoomed"],
                                        win_state["pinned"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(EDGE, EDGE, EDGE, EDGE)   # resize border
        layout.setSpacing(0)
        self.bar = TopBar(self)
        self.tabbar = self.bar.tabbar     # tabs live inside the merged top bar now
        self.settings_btn = self.bar.settings_btn
        self.settings_btn.clicked.connect(self.open_settings)
        self.bar.close_btn.clicked.connect(self.close)
        self.bar.min_btn.clicked.connect(self.showMinimized)
        self.bar.max_btn.clicked.connect(self.toggle_max)
        self.bar.pin_btn.clicked.connect(self.toggle_pin)
        self.pinned = pinned
        self.load_ok = True
        self.load_partial = False
        self._busy_count = 0
        self.autoarchive = APP_SETTINGS["autoarchive"]
        # Background is per-TAB now (not a shared app-wide theme) - starts
        # out matching whichever tab is active; switching tabs, or
        # recolouring the active one, updates it and repaints the window.
        self.bg_top, self.bg_bottom = derive_theme(
            self.tab_meta.get(self.active_tab, {}).get("colour") or default_tab_colour(0))
        self.bar.pin_btn.active = self.pinned
        layout.addWidget(self.bar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        self.scroll.viewport().setObjectName("viewport")
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.verticalScrollBar().setStyleSheet(SCROLL_STYLE)
        layout.addWidget(self.scroll)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(300)
        self.save_timer.timeout.connect(self.save_now)
        # Midnight (due colours) + background path checks
        self.today = date.today()
        self.tick = QTimer(self)
        self.tick.setInterval(500)
        self.tick.timeout.connect(self.on_tick)
        self.tick.start()
        # The board (tasks) is built right after the window appears.
        # Undo history is per-TAB (not shared across tab switches), kept in
        # memory only - self.history is always an alias for whichever tab's
        # list is currently showing, swapped by switch_tab()/add_tab()/etc.
        self.tab_history = {tid: [] for tid in self.tab_order}
        self.history = self.tab_history[self.active_tab]
        self.board = None
        self.data = active_tab_data
        self._last_focus_at = time.monotonic()
        self.apply_header_scale()
        self.start_zoomed = zoomed
        self.restore_window(geometry)
        self._normal_geom = self.geometry()
        self.ready = True
        WINDOWS.append(self)
    # ---------- board ----------
    def build_board(self, data):
        old = self.board
        if old is not None:
            old.dead = True
            self.scroll.takeWidget()
            old.hide()
            old.deleteLater()
        self.board = Board(data, self.scroll, self.history)
        self.board.changed.connect(self.save_timer.start)
        self.board.undo_requested.connect(lambda: QTimer.singleShot(0, self.undo))
        self.scroll.setWidget(self.board)
        self.board.setAutoFillBackground(False)     # setWidget turns this on
        self.board.relayout(animate=False)
        self.board.show()
    def export_active_tab_data(self):
        """Snapshot of the currently-mounted board, in the same dict shape
        every tab's stored data uses - for stashing a tab away when
        switching off it, or for saving/moving it."""
        groups, done = self.board.export()
        meta = self.tab_meta.get(self.active_tab, {"name": "Tab", "colour": ACCENT})
        return {"name": meta["name"], "colour": meta["colour"],
                "groups": groups, "done": done, "folded": set(self.board.folded_names()),
                "colours": self.board.colours(), "collapsed": self.board.collapsed}
    # ---------- tabs ----------
    def switch_tab(self, tabid):
        if tabid == self.active_tab or self.board is None or tabid not in self.tab_order:
            return
        self.tabbar.commit_rename_if_open()
        self.commit_edits()
        self.tab_data[self.active_tab] = self.export_active_tab_data()
        data = self.tab_data.pop(tabid, None) or _empty_tab(
            self.tab_meta[tabid]["name"], self.tab_meta[tabid]["colour"])
        self.history = self.tab_history.setdefault(tabid, [])
        self.build_board(data)
        self.active_tab = tabid
        self.apply_tab_background(self.tab_meta[tabid]["colour"])
        self.board.auto_archive(self.autoarchive)
        self.scroll_to_top()
        general = self.board.groups[0]
        if general.folded:
            self.board.setFocus()
        else:
            general.add_row.edit.setFocus()
        self.tabbar.refresh()
        self.save_timer.start()
    def add_tab(self):
        self.tabbar.commit_rename_if_open()
        tid = alloc_tab_id()
        colour = default_tab_colour(tid)
        meta = {"name": "New tab", "colour": colour}
        if self.active_tab is not None and self.board is not None:
            self.tab_data[self.active_tab] = self.export_active_tab_data()
        self.tab_order.append(tid)
        self.tab_meta[tid] = meta
        self.tab_history[tid] = []
        self.history = self.tab_history[tid]
        self.build_board(_empty_tab(meta["name"], meta["colour"]))
        self.active_tab = tid
        self.apply_tab_background(colour)
        self.board.auto_archive(self.autoarchive)
        self.scroll_to_top()
        self.tabbar.refresh()
        self.tabbar.start_rename(tid)      # ready to type a name right away
        self.save_timer.start()
    def rename_tab(self, tabid, name):
        if tabid in self.tab_meta:
            self.tab_meta[tabid]["name"] = name
            self.tabbar.refresh()
            self.save_timer.start()
    def set_tab_colour(self, tabid, hexc):
        if tabid in self.tab_meta:
            self.tab_meta[tabid]["colour"] = hexc
            self.tabbar.update()
            if tabid == self.active_tab:
                self.apply_tab_background(hexc)    # this tab IS the visible background
            self.save_timer.start()
    def delete_tab(self, tabid):
        """Removes a tab entirely (after the user confirmed). If it was the
        last tab in THIS window, the window closes - but only ever called
        when at least one other tab exists somewhere in the app.
        Ctrl+Z brings it back (see DELETED_TABS), in this window - or, if
        this window closed with it, in the window that's used next."""
        index = self.tab_order.index(tabid)
        data = None
        if tabid == self.active_tab:
            others = [t for t in self.tab_order if t != tabid]
            if others:
                self.switch_tab(others[0])     # snapshots tabid's data first
            else:
                data = self.export_active_tab_data()
                self.board.dead = True
                self.scroll.takeWidget()
                self.board.hide()
                self.board.deleteLater()
                self.board = None
                self.active_tab = None
        data = self.tab_data.pop(tabid, None) or data or _empty_tab(
            self.tab_meta[tabid]["name"], self.tab_meta[tabid]["colour"])
        meta = self.tab_meta.pop(tabid)
        history = self.tab_history.pop(tabid, None) or []
        if tabid in self.tab_order:
            self.tab_order.remove(tabid)
        home = self if self.tab_order else most_recently_focused_other(self)
        if home is not None:
            DELETED_TABS.append({"tabid": tabid, "data": data, "meta": meta,
                                 "history": history, "index": index, "win": home,
                                 "mark": home.undo_mark()})
            del DELETED_TABS[:-UNDO_LIMIT]
        if not self.tab_order:
            self.close_emptied_by_transfer()
        else:
            self.tabbar.refresh()
            self.save_timer.start()
    def undo_mark(self):
        """Identifies 'nothing has been done here since': the open tab and
        the newest step in its undo history."""
        return self.active_tab, (self.history[-1] if self.history else None)
    def _restore_deleted_tab(self):
        """Ctrl+Z straight after deleting a tab (nothing else done since in
        the tab you're on): the tab comes back where it was, opened, with
        its own undo history. Returns True if it did."""
        if not DELETED_TABS:
            return False
        rec = DELETED_TABS[-1]
        if rec["win"] is not self or rec["mark"][0] != self.active_tab \
                or rec["mark"][1] is not (self.history[-1] if self.history else None):
            return False
        DELETED_TABS.pop()
        self.tab_history[rec["tabid"]] = rec["history"]
        self.insert_tab(rec["tabid"], rec["data"], rec["meta"],
                        index=rec["index"], activate=True)
        restore_files(self.board.used_files())
        self.save_timer.start()
        return True
    def pop_tab_for_transfer(self, tabid):
        """Pulls one tab's data out for moving to another window (drag to
        another bar, or tear-off) - this window keeps running with its
        remaining tabs (switching to a neighbour if the removed tab was the
        active one). If that leaves zero tabs, active_tab becomes None and
        the caller must close this window (close_emptied_by_transfer)."""
        was_active = tabid == self.active_tab
        if was_active:
            data = self.export_active_tab_data()
        else:
            data = self.tab_data.pop(tabid, None) or _empty_tab(
                self.tab_meta[tabid]["name"], self.tab_meta[tabid]["colour"])
        meta = self.tab_meta.pop(tabid)
        self.tab_history.pop(tabid, None)
        self.tab_order.remove(tabid)
        if was_active:
            if self.tab_order:
                new_active = self.tab_order[0]
                next_data = self.tab_data.pop(new_active, None) or _empty_tab(
                    self.tab_meta[new_active]["name"], self.tab_meta[new_active]["colour"])
                self.history = self.tab_history.setdefault(new_active, [])
                self.build_board(next_data)
                self.board.auto_archive(self.autoarchive)
                self.active_tab = new_active
                self.apply_tab_background(self.tab_meta[new_active]["colour"])
            else:
                self.active_tab = None
        return data, meta
    def insert_tab(self, tabid, data, meta, index=None, activate=True):
        """Receives a tab dragged in from another window (or being restored
        after a merge)."""
        if index is None or index > len(self.tab_order):
            index = len(self.tab_order)
        self.tab_order.insert(index, tabid)
        self.tab_meta[tabid] = meta
        if activate:
            if self.active_tab is not None and self.board is not None:
                self.tab_data[self.active_tab] = self.export_active_tab_data()
            self.history = self.tab_history.setdefault(tabid, [])
            self.build_board(data)
            self.active_tab = tabid
            self.apply_tab_background(meta["colour"])
            self.board.auto_archive(self.autoarchive)
            self.scroll_to_top()
        else:
            self.tab_data[tabid] = data
        self.tabbar.refresh()
    def detach_tab_to_new_window(self, tabid, global_pos):
        """A tab was dragged out of the row and let go anywhere that isn't a
        tab row - it becomes its own window, appearing where it was dropped."""
        data, meta = self.pop_tab_for_transfer(tabid)
        new_win = Window(detached=(tabid, data, meta))
        new_win.resize(self._normal_geom.size() if self._normal_geom else self.size())
        # global_pos is where the tab's top-left was let go: the new window's
        # (only) tab lands right there.
        new_win.move(global_pos - QPoint(EDGE + new_win.bar.tab_left(),
                                         EDGE + new_win.bar.tab_top()))
        new_win.winId()      # must exist before enable_snap() can touch its HWND
        enable_snap(new_win)
        new_win.show_panel()
        QApplication.processEvents()
        new_win.load_board()
        if not self.tab_order:
            self.close_emptied_by_transfer()
        else:
            self.tabbar.refresh()
        global_save()
    def _harvest_all_tabs(self):
        """Pulls every tab's data out of this window without bothering to
        rebuild its board in between (used only when the WHOLE window is
        closing and all its tabs move elsewhere)."""
        out = []
        for tabid in self.tab_order:
            if tabid == self.active_tab:
                data = self.export_active_tab_data()
            else:
                data = self.tab_data.get(tabid) or _empty_tab(
                    self.tab_meta[tabid]["name"], self.tab_meta[tabid]["colour"])
            out.append((tabid, data, self.tab_meta[tabid]))
        self.tab_order, self.tab_data, self.tab_meta, self.active_tab = [], {}, {}, None
        return out
    def close_emptied_by_transfer(self):
        """This window's last tab just moved to another window (dragged
        there, or torn off successfully) - nothing left to show, so it just
        disappears; the tab itself already lives on elsewhere."""
        self.quitting = True
        if self in WINDOWS:
            WINDOWS.remove(self)
        self.hide()
        self.deleteLater()
    def scroll_to_top(self):
        """The list always opens scrolled to the top - called a couple of
        times shortly after load since the board's layout (and so the
        scroll range) settles asynchronously as cards are added."""
        bar = self.scroll.verticalScrollBar()
        def go():
            bar.setValue(0)
        go()
        QTimer.singleShot(0, go)
        QTimer.singleShot(60, go)
    def set_tint(self, t):
        TINT[0] = t
        for w in WINDOWS:
            if w.board is not None:
                for g in w.board.groups:
                    if g.colour:
                        g.header.update()
                        g.add_row.update()
                for c in w.board.all_cards():
                    c.update()
        self.save_timer.start()
    def apply_tab_background(self, colour):
        """Recomputes this window's background gradient from a tab's single
        colour (the same colour shown as that tab's accent stripe/swatch)
        and repaints - called whenever the ACTIVE tab changes, or whenever
        the active tab's own colour is changed."""
        self.bg_top, self.bg_bottom = derive_theme(colour or default_tab_colour(0))
        self.update()
    def set_autoarchive(self, days):
        APP_SETTINGS["autoarchive"] = days
        for w in WINDOWS:
            w.autoarchive = days
            if w.board is not None:
                w.board.auto_archive(days)
        self.save_timer.start()
    def on_tick(self):
        if self.board is None:
            return
        if links_changed[0]:
            links_changed[0] = False
            self.board.refresh_links()
        if attachment_kinds_changed[0]:
            attachment_kinds_changed[0] = False
            self.board.refresh_attachments()
        if date.today() != self.today:
            self.today = date.today()
            self.board.refresh_dates()
            self.board.auto_archive(self.autoarchive)
    def load_board(self):
        self.build_board(self.data)
        self.data = None
        self.board.auto_archive(self.autoarchive)
        self.scroll_to_top()
        self.save_now()
        general = self.board.groups[0]
        if general.folded:
            self.board.setFocus()
        else:
            general.add_row.edit.setFocus()
    # ---------- top bar buttons ----------
    def toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
    def _apply_window_state(self):
        """No resize border while maximised (nothing to drag-resize from),
        and the maximise button's icon kept in step."""
        m = 0 if self.isMaximized() else EDGE
        self.layout().setContentsMargins(m, m, m, m)
        self.bar.max_btn.update()
        QTimer.singleShot(0, self.update_corners)
    def toggle_pin(self):
        self.pinned = not self.pinned
        self.bar.pin_btn.active = self.pinned
        self.bar.pin_btn.update()
        self.apply_pin()
        self.save_timer.start()
    def apply_pin(self):
        if os.name != "nt":
            return
        try:
            after = ctypes.c_void_p(-1 if self.pinned else -2)   # TOPMOST / NOTOPMOST
            user32.SetWindowPos(int(self.winId()), after, 0, 0, 0, 0, 0x13)
        except Exception:
            pass
    def undo(self):
        if self.board is None or self._restore_deleted_tab() or not self.history:
            return
        top = self.history[-1]
        reedit = top.get("_reedit")
        if reedit is not None and reedit["card"] in self.board.open_cards():
            # The very next thing to undo is "you just pressed Enter to
            # commit a task" - Ctrl+Z undoes only that commit, not the
            # typing that led up to it, so fixing a typo never means
            # retyping from scratch:
            #   - a brand NEW task: it disappears again and exactly what
            #     you typed goes back into the Add-task box you typed it
            #     in, ready to fix and resubmit.
            #   - an EDITED task: its due/star/group go back to how they
            #     were before, and its editor reopens with exactly what you
            #     had typed (not the old pre-edit text), ready to fix.
            # No board rebuild needed either way - far more precise than a
            # full snapshot revert.
            self.history.pop()
            card = reedit["card"]
            if reedit["mode"] == "add":
                group = self.board.group_of(card)
                if group is not None:
                    group.cards.remove(card)
                self.board.selected.discard(id(card))
                if self.board.anchor is card:
                    self.board.anchor = None
                card.hide()
                card.deleteLater()
                self.board.relayout(animate=True)
                target_group = self.board.group_named(reedit["origin_group_name"])
                self.board.focus_add(target_group)
                self.board.active_group = target_group
                edit = target_group.add_row.edit
                edit.blockSignals(True)
                edit.setPlainText(reedit["raw_text"])
                edit.blockSignals(False)
                edit.go_end()
            else:       # "edit"
                old_task = reedit["old_task"]
                old_group_name = old_task.get("group")
                current_group = self.board.group_of(card)
                card.task.clear()
                card.task.update(old_task)
                if current_group is not None and current_group.name != old_group_name:
                    target_group = self.board.group_named(old_group_name)
                    current_group.cards.remove(card)
                    target_group.cards.append(card)
                card.refresh()
                self.board.relayout(animate=True)
                self.board.select_only(card)
                card.start_edit()
                edit = card.editor
                edit.blockSignals(True)
                edit.setPlainText(reedit["raw_text"])
                edit.blockSignals(False)
                edit.go_end()
            self.save_timer.start()
            return
        snap = self.history.pop()
        if snap.get("archive"):
            unarchive(*snap["archive"])
        bar = self.scroll.verticalScrollBar()
        pos = bar.value()
        active = self.board.active_group.name
        self.build_board(snap)
        restore_files(self.board.used_files())
        self.board.active_group = next(
            (g for g in self.board.groups if g.name == active), self.board.groups[0])
        bar.setValue(pos)
        QTimer.singleShot(0, lambda: bar.setValue(pos))
        self.board.setFocus()
        self.save_timer.start()
    # ---------- scaling ----------
    def apply_header_scale(self):
        self.bar.apply_scale()      # also rescales the embedded tab bar
    # ---------- resizing the frameless window from its edges ----------
    def _edges(self, pos):
        if self.isMaximized():
            return []
        m = EDGE + 2
        e = []
        if pos.x() < m:
            e.append(Qt.Edge.LeftEdge)
        if pos.x() > self.width() - m:
            e.append(Qt.Edge.RightEdge)
        if pos.y() < m:
            e.append(Qt.Edge.TopEdge)
        if pos.y() > self.height() - m:
            e.append(Qt.Edge.BottomEdge)
        return e
    def mouseMoveEvent(self, e):
        edges = self._edges(e.position().toPoint())
        if not edges:
            self.unsetCursor()
            return
        lr = any(x in edges for x in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge))
        tb = any(x in edges for x in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge))
        if lr and tb:
            main_diag = ((Qt.Edge.LeftEdge in edges and Qt.Edge.TopEdge in edges) or
                         (Qt.Edge.RightEdge in edges and Qt.Edge.BottomEdge in edges))
            self.setCursor(Qt.SizeFDiagCursor if main_diag else Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.SizeHorCursor if lr else Qt.SizeVerCursor)
    def mousePressEvent(self, e):
        edges = self._edges(e.position().toPoint())
        if e.button() == Qt.LeftButton and edges:
            flags = edges[0]
            for x in edges[1:]:
                flags = flags | x
            self.windowHandle().startSystemResize(flags)
    def leaveEvent(self, _):
        self.unsetCursor()
    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange:
            self._apply_window_state()
        elif e.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._last_focus_at = time.monotonic()
        super().changeEvent(e)
    def set_ui_scale(self, s):
        if abs(s - S) < 0.001:
            return
        set_scale(s)
        self.setUpdatesEnabled(False)
        self.apply_header_scale()
        if self.board is not None:
            self.board.rescale()
        self.setUpdatesEnabled(True)
        self.save_timer.start()
    def open_settings(self):
        # Clicking ... while the popup is open: the click closes it - don't reopen
        if time.monotonic() - getattr(self, "popup_closed_at", 0) < 0.3:
            return
        popup = SettingsPopup(self)
        popup.setAttribute(Qt.WA_DeleteOnClose)
        btn = self.settings_btn
        place_popup(popup, QRect(btn.mapToGlobal(QPoint(0, 0)), btn.size()), align="right")
        popup.show()
    # ---------- window position ----------
    def restore_window(self, geo):
        if geo:
            x, y, w, h = geo
            screen = QGuiApplication.screenAt(QPoint(x + w // 2, y + h // 2))
            if screen is not None:
                y = max(y, screen.availableGeometry().top())   # never above the top
                self.setGeometry(x, y, max(w, 240), max(h, 200))
                return
            self.resize(w, h)
            return
        self.resize(*DEFAULT_SIZE)
    def current_geometry(self):
        g = self._normal_geom or self.geometry()
        return g.x(), g.y(), g.width(), g.height()
    def _note_normal_geometry(self):
        """Remembers the geometry while the window is neither maximised nor
        minimised. Asks Windows directly: Qt's own window state can lag a
        step behind the move/resize that maximising causes."""
        if os.name == "nt":
            hwnd = int(self.winId())
            off = user32.IsZoomed(hwnd) or user32.IsIconic(hwnd)
        else:
            off = self.isMaximized() or self.isMinimized()
        if not off:
            self._normal_geom = self.geometry()
    def save_now(self):
        """Returns True/False - callers must never treat a False return as
        a successful save (no cleanup, no 'saved' assumptions). The data
        file covers the WHOLE app (every window, every tab), so this just
        triggers that one consolidated save regardless of which window's
        timer fired."""
        return global_save()
    def _report_save_failure(self):
        now = time.monotonic()
        if now - getattr(self, "_save_error_shown_at", 0) < 5:
            return               # the 300 ms save timer must never spam this dialog
        self._save_error_shown_at = now
        alert(self, "Save failed",
              "Couldn't save your tasks to TodoList.txt.\n"
              "Nothing has been lost - the list stays open so you can try "
              "again (e.g. close whatever else has the file open).\n"
              "Details were written to TodoError.log.")
    def set_busy(self, busy, text="Working\u2026"):
        """Wait cursor + a temporary status in the title, reference-counted
        so several overlapping background fetches never leave the cursor
        stuck or clobber each other's status."""
        self._busy_count = max(0, self._busy_count + (1 if busy else -1))
        if busy and self._busy_count == 1:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._busy_title = self.bar.title.text()
            self.bar.title.setText(text)
        elif not busy and self._busy_count == 0:
            QApplication.restoreOverrideCursor()
            self.bar.title.setText(getattr(self, "_busy_title", ""))
    def commit_edits(self):
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()
    def moveEvent(self, e):
        if getattr(self, "ready", False) and self.isVisible():
            self._note_normal_geometry()
            self.save_timer.start()
            QTimer.singleShot(0, self.update_corners)
    def resizeEvent(self, e):
        if getattr(self, "ready", False) and self.isVisible():
            self._note_normal_geometry()
            self.save_timer.start()
            QTimer.singleShot(0, self.update_corners)
    # ---------- show / close ----------
    def show_panel(self):
        if self.start_zoomed:
            # Placed at its saved normal geometry already (restore_window),
            # so that's what un-maximising goes back to.
            self.start_zoomed = False
            self.showMaximized()
        else:
            self.show()
        self.apply_pin()
        self.raise_()
        self.activateWindow()
    def closeEvent(self, e):
        # X: if this is the LAST open window, save everything and quit
        # completely, same as before - but never on top of a failed save,
        # so nothing gets lost. If OTHER windows are still open, this
        # window's tabs move into the most recently used one instead of
        # the app quitting (every tab must always be showing SOMEWHERE).
        if getattr(self, "quitting", False):
            e.accept()
            return
        self.commit_edits()
        self.save_timer.stop()
        others = [w for w in WINDOWS if w is not self]
        if not others:
            ok = self.save_now()
            if not ok:
                e.ignore()                 # keep the list open - try again
                self.save_timer.start()
                return
            if not any_window_data_unsafe():
                cleanup_attachments(used_files_everywhere())
            self.history.clear()
            self.quitting = True
            if self in WINDOWS:
                WINDOWS.remove(self)
            release_instance()
            e.accept()
            QTimer.singleShot(0, QApplication.quit)
            return
        target = most_recently_focused_other(self)
        for tabid, data, meta in self._harvest_all_tabs():
            target.insert_tab(tabid, data, meta, activate=False)
        target.tabbar.refresh()
        self.history.clear()
        self.quitting = True
        if self in WINDOWS:
            WINDOWS.remove(self)
        e.accept()
        global_save()
        self.deleteLater()
    def close_from_f2(self):
        """F2 from AHK while this window is in front: close any open menu /
        dialog first, then shut the WHOLE app down (every window)."""
        popup = QApplication.activePopupWidget()
        for _ in range(5):
            if popup is None:
                break
            popup.close()
            popup = QApplication.activePopupWidget()
        modal = QApplication.activeModalWidget()
        for _ in range(5):
            if modal is None or modal in WINDOWS:
                break
            modal.close()           # message box / calendar -> cancelled
            modal = QApplication.activeModalWidget()
        QTimer.singleShot(0, shutdown_everything)
    def ahk_toggle(self):
        """F2 from TodoLauncher.ahk, received by this window: in front ->
        close everything, otherwise bring this window to the front."""
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            self.close_from_f2()
        else:
            self.bring_back()
    def bring_back(self):
        """Second F2 while this copy was still starting: just come to the front."""
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show_panel()
        self.apply_pin()
        self.raise_()
        self.activateWindow()
        if os.name == "nt":
            try:
                user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass
    def showEvent(self, e):
        super().showEvent(e)
        round_corners(self)
        QTimer.singleShot(0, self.update_corners)
        if self.board is not None:
            self.board.relayout(animate=False)
    # ---------- native Windows frame: snapping, Win+arrows, edge resize ----------
    def nativeEvent(self, event_type, message):
        if os.name == "nt":
            try:
                msg = wintypes.MSG.from_address(int(message))
                m = msg.message
                if m == WM_GETMINMAXINFO:
                    # Tells Windows the correct maximised size/position
                    # BEFORE it picks a (wrong) default - see
                    # fill_minmaxinfo()'s docstring for why this matters.
                    dpr = self.devicePixelRatioF()
                    fill_minmaxinfo(msg.hWnd, msg.lParam,
                                    int(self.minimumWidth() * dpr),
                                    int(self.minimumHeight() * dpr))
                    return True, 0
                if m == WM_NCCALCSIZE and msg.wParam:
                    # No visible frame; when maximised, fit the work area exactly
                    if user32.IsZoomed(msg.hWnd):
                        fit_to_work_area(msg.lParam)
                    return True, 0
                if m == WM_NCHITTEST:
                    return True, self.hit_test(msg.lParam)
                if m == WM_EXITSIZEMOVE:
                    QTimer.singleShot(0, self.update_corners)
                if m == WM_SHOW_TASKS:
                    QTimer.singleShot(0, self.bring_back)
                    return True, 0
                if m == WM_TODO_CLOSE:
                    QTimer.singleShot(0, self.close_from_f2)
                    return True, 0
                if m == WM_AHK_TOGGLE:
                    QTimer.singleShot(0, self.ahk_toggle)
                    return True, 0
                if m == 0x0005:                         # WM_SIZE (snap, Win+arrows, maximise)
                    QTimer.singleShot(0, self.update_corners)
            except Exception:
                pass
        return False, 0
    def hit_test(self, lparam):
        hwnd = int(self.winId())
        pt = wintypes.POINT(ctypes.c_short(lparam & 0xFFFF).value,
                            ctypes.c_short((lparam >> 16) & 0xFFFF).value)
        user32.ScreenToClient(hwnd, ctypes.byref(pt))
        rc = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rc))
        dpr = self.devicePixelRatioF()
        if not user32.IsZoomed(hwnd):
            b = int(EDGE * dpr) + 1
            left, right = pt.x < b, pt.x >= rc.right - b
            top, bottom = pt.y < b, pt.y >= rc.bottom - b
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        lp = QPoint(int(pt.x / dpr), int(pt.y / dpr))
        if self.bar.geometry().contains(lp):
            # Only genuinely empty bar space is caption (drag the window,
            # double-click to maximise); tabs, the rename box and buttons
            # are ordinary clicks for Qt.
            child = self.bar.childAt(lp - self.bar.pos())
            if child is None or child in self.bar.caption_widgets():
                return HTCAPTION
        return HTCLIENT
    def corners_cut(self):
        """True when Windows 11 would square the corners (snapped / maximised),
        so we round them ourselves."""
        if os.name != "nt" or not self.isVisible() or self.isMinimized():
            return False
        hwnd = int(self.winId())
        if user32.IsZoomed(hwnd):
            return True
        rc = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        mon = user32.MonitorFromWindow(hwnd, 2)
        if not (mon and user32.GetMonitorInfoW(mon, ctypes.byref(info))):
            return False
        w, t = info.rcWork, 2
        touching = sum((abs(rc.left - w.left) <= t, abs(rc.right - w.right) <= t,
                        abs(rc.top - w.top) <= t, abs(rc.bottom - w.bottom) <= t))
        return touching >= 2
    def update_corners(self):
        """Corners are always drawn round by paintEvent (smooth, any state).
        Just repaint when snapped / maximised / restored."""
        cut = self.corners_cut() if os.name == "nt" else False
        if cut != getattr(self, "_rounded", False):
            self._rounded = cut
        self.update()
    def list_gradient(self):
        """The list's background, in window coordinates - the open tab
        paints itself with this too, so the two are one surface."""
        bar_h = self.bar.y() + self.bar.height()
        g = QLinearGradient(0, bar_h, self.width() * 0.3, self.height())
        g.setColorAt(0, QColor(self.bg_top))
        g.setColorAt(1, QColor(self.bg_bottom))
        return g
    def _open_tab_shape(self):
        """(the open tab's body, its two flares) in window coordinates, cut
        to the visible part of the tab row - or None if it isn't in the row
        right now."""
        chip = self.tabbar.chips.get(self.active_tab)
        if chip is None or chip.lifted or not chip.isVisible():
            return None
        vp = self.bar.tab_scroll.viewport()
        f = tab_flare()
        shown = QPainterPath()
        shown.addRect(QRectF(QRect(vp.mapTo(self, QPoint(0, 0)), vp.size())).adjusted(-f, 0, f, 0))
        r = QRectF(QRect(chip.mapTo(self, QPoint(0, 0)), chip.size()))
        return (tab_shape(r, RADIUS).intersected(shown),
                tab_flares(r).intersected(shown))
    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect())
        # 1. Whole window: alpha 1/255 - looks invisible, but still catches
        #    the mouse, so the corner areas never click through.
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.Antialiasing)
        rad = 0 if self.isMaximized() else CORNER * max(S, 0.8)
        shape = QPainterPath()
        shape.addRoundedRect(r, rad, rad)
        p.save()
        p.setClipPath(shape)
        # 2. Top strip (behind the tab bar), reaching every edge - except
        #    where the open tab is: that tab paints the list's own gradient
        #    (TabChip.paintEvent), so tab and list are one seamless surface
        #    even with a see-through colour.
        bar_h = self.bar.y() + self.bar.height()
        strip = QPainterPath()
        strip.addRect(QRectF(r.left(), r.top(), r.width(), bar_h))
        tab = self._open_tab_shape()
        if tab is not None:
            strip = strip.subtracted(tab[0]).subtracted(tab[1])
        p.fillPath(strip, QColor(TOPBAR_BG[0]))
        # 3. The list itself: gradient, filling the rest - and the open
        #    tab's flares, which are part of the list's surface.
        listed = QPainterPath()
        listed.addRect(QRectF(r.left(), r.top() + bar_h, r.width(), r.height() - bar_h))
        if tab is not None:
            listed = listed.united(tab[1])
        p.fillPath(listed, self.list_gradient())
        p.restore()
        # 4. Thin light edge so it stands out from what's behind
        if rad:
            p.setPen(QPen(QColor(255, 255, 255, 38), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad)
def fit_to_work_area(lparam):
    rect = wintypes.RECT.from_address(lparam)
    mon = user32.MonitorFromRect(ctypes.byref(rect), 2)    # nearest monitor
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        w = info.rcWork
        rect.left, rect.top, rect.right, rect.bottom = w.left, w.top, w.right, w.bottom
def fill_minmaxinfo(hwnd, lparam, min_w, min_h):
    """WM_GETMINMAXINFO: without this, a frameless window that gained
    WS_THICKFRAME dynamically (enable_snap, applied AFTER the window was
    already created with no border) has nothing telling Windows what its
    maximised size/position should actually be. Windows then falls back to
    a default based on standard caption/border metrics that don't apply
    here, which is exactly why double-clicking maximise - or Windows snap
    (dragging to the top of the screen) - was landing the window in the
    top-left corner at a narrow, wrong size instead of filling the work
    area: fit_to_work_area() (WM_NCCALCSIZE) only ever got a chance to
    correct the size AFTER Windows had already decided on that wrong one.
    This fills in the real answer up front, from the correct monitor (the
    one the window is actually on, not always the primary one)."""
    info = MINMAXINFO.from_address(lparam)
    mon = user32.MonitorFromWindow(hwnd, 2)      # MONITOR_DEFAULTTONEAREST
    if mon:
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            work, full = mi.rcWork, mi.rcMonitor
            # Position is relative to the monitor's own top-left, which
            # matters as soon as there's more than one monitor.
            info.ptMaxPosition.x = work.left - full.left
            info.ptMaxPosition.y = work.top - full.top
            info.ptMaxSize.x = work.right - work.left
            info.ptMaxSize.y = work.bottom - work.top
    info.ptMinTrackSize.x = max(info.ptMinTrackSize.x, min_w)
    info.ptMinTrackSize.y = max(info.ptMinTrackSize.y, min_h)
def enable_snap(widget):
    """Give the frameless window a real (invisible) resizable frame so Windows
    treats it like a normal window: Aero Snap, Win+arrows, snap layouts."""
    if os.name != "nt":
        return
    try:
        hwnd = int(widget.winId())
        style = user32.GetWindowLongW(hwnd, -16)                  # GWL_STYLE
        style |= 0x00040000 | 0x00C00000 | 0x00010000 | 0x00020000  # THICKFRAME, CAPTION, MAX, MIN
        user32.SetWindowLongW(hwnd, -16, style)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)         # FRAMECHANGED etc.
    except Exception:
        pass
def release_instance():
    global _instance_mutex
    if _instance_mutex and os.name == "nt":
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_instance_mutex))
        _instance_mutex = None
def _log_errors():
    """.pyw has no console, so uncaught errors vanish - write them to
    TodoError.log instead (log_error() covers explicitly-handled ones)."""
    def hook(kind, value, tb):
        try:
            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} --- (uncaught)\n")
                f.write("".join(traceback.format_exception(kind, value, tb)))
        except OSError:
            pass
    sys.excepthook = hook
def main(mutex=None):
    global _instance_mutex
    _instance_mutex = mutex
    _log_errors()
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WSP.MyTasks")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    if os.path.exists(ICON_FILE):
        app.setWindowIcon(QIcon(ICON_FILE))
    state = load_app_state()
    set_scale(state["scale"])
    APP_SETTINGS["autoarchive"] = state["autoarchive"]
    TINT[0] = state["tint"]
    TOPBAR_BG[0] = state.get("topbar_colour") or TOPBAR_BG_DEFAULT
    TAB_ID_COUNTER[0] = state["next_tab_id"]
    windows = []
    for win_state in state["windows"]:
        w = Window(win_state=win_state, tabs_state=state["tabs"])
        w.load_ok = state["ok"]
        w.load_partial = state["partial"]
        w.winId()
        enable_snap(w)
        windows.append(w)
    # Windows shutting down / logging off: save everything, once
    app.aboutToQuit.connect(
        lambda: None if any(getattr(w, "quitting", False) for w in windows)
        else shutdown_everything())
    if START_HIDDEN:
        for w in windows:
            w.load_board()       # AHK preload at startup: ready, but hidden until F2
    else:
        for w in windows:
            w.show_panel()
        app.processEvents()      # paint the windows straight away...
        for w in windows:
            w.load_board()       # ...then fill in each one's tasks
    sys.exit(app.exec())
if __name__ == "__main__":
    main(_launch_mutex)
