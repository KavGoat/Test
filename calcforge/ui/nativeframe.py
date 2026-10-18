"""The window's frame: Windows' own, with the menus drawn inside its title bar.

The user, 2026-10-16: "put the top bar in the normal window bar with
Windows' window controls" — no frame of our own. So on Windows the window keeps its native
frame — Windows' own minimise, maximise and close buttons, its dragging,
double-click to maximise, Aero Snap, Windows 11's Snap Layouts on the
maximise button, its resize borders and shadow — and the menus are drawn in
the title bar's row, as Revu 21 draws them.

This is Microsoft's documented pattern, "Custom Window Frame Using DWM":

* WM_NCCALCSIZE takes away the top of the non-client area only, so the client
  area reaches the top of the window; the side and bottom borders stay
  Windows' (resizing, shadow). Maximised, the top is pushed down by the frame
  thickness, the part of a maximised window that hangs off the screen.
* DwmExtendFrameIntoClientArea extends the frame down behind the title row,
  so the desktop window manager keeps drawing its caption buttons there. Qt
  paints the title row; the place where the buttons are is left transparent
  (the window has an alpha channel) so they show through.
* WM_NCHITTEST asks DwmDefWindowProc first. Over the caption buttons the
  window answers HTMINBUTTON, HTMAXBUTTON or HTCLOSE itself from
  DWMWA_CAPTION_BUTTON_BOUNDS (in thirds) when DWM does not: the client area
  covers them, so nothing else would, and HTMAXBUTTON is what gives Windows
  11's Snap Layouts. The top edge resizes; empty parts of the title row
  answer HTCAPTION, so Windows itself moves, snaps and maximises the window
  (double-click too); menus, the Markup | Calc switch and the search box stay
  ordinary widgets.
* Every non-client mouse message goes to DwmDefWindowProc first, which lights
  and presses the buttons. A press on a button is kept from DefWindowProc —
  its old button-tracking loop looks for a caption the window no longer has,
  and the click came to nothing (the user, 2026-10-18: minimise, maximise
  and close did nothing) — and the release on the same button posts its
  WM_SYSCOMMAND, as Windows Terminal and Chrome do.
* A right-click on the caption opens the system menu here: Qt would take the
  WM_CONTEXTMENU, since the title row is client area to it. Alt+Space is
  Qt's own (it opens the same system menu).

Everything that touches Win32 is inside win32-only branches, so the module
imports anywhere; the hit-test decision is the pure function hit_test(), which
is tested on every platform.

On macOS and Linux the window has the ordinary native title bar, with the
menus in a menu row under it (on a Mac, in the Mac's menu bar).
"""
from __future__ import annotations

import math
import sys

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette, QResizeEvent
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication, QComboBox,
                               QLabel, QLineEdit, QMenuBar, QStyle, QStyleOption, QWidget)

#: Whether the menus are drawn inside the system's own title bar.
IN_TITLE_BAR = sys.platform == "win32"

# Win32 hit-test codes (WinUser.h)
HTNOWHERE = 0
HTCLIENT = 1
HTCAPTION = 2
HTMINBUTTON = 8
HTMAXBUTTON = 9
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTCLOSE = 20
HTHELP = 21
CAPTION_BUTTON_CODES = frozenset({HTMINBUTTON, HTMAXBUTTON, HTCLOSE, HTHELP})
TOP_EDGE_CODES = frozenset({HTTOP, HTTOPLEFT, HTTOPRIGHT})

#: Where Windows' caption buttons are while it has not said: three buttons
#: 46 px wide and about a title bar high, in device-independent pixels.
FALLBACK_CAPTION_SIZE = (138, 30)


def caption_button_at(point, caption_buttons_rect):
    """Which of Windows' caption buttons is at *point*: HTMINBUTTON,
    HTMAXBUTTON or HTCLOSE, left to right, each a third of the buttons' place
    (they are all one width); None when the point is not on them."""
    if caption_buttons_rect is None:
        return None
    rect = QRectF(caption_buttons_rect)
    p = QPointF(point)
    if rect.isEmpty() or not rect.contains(p):
        return None
    third = (p.x() - rect.left()) / rect.width() * 3
    return (HTMINBUTTON, HTMAXBUTTON, HTCLOSE)[min(2, max(0, int(third)))]


def hit_test(point, title_rect, widgets_rects, edge, caption_buttons_rect, maximised):
    """What a point in the window is, for WM_NCHITTEST.

    All in the window's client coordinates (device-independent pixels):
    *title_rect* is the title row, as wide as the window; *widgets_rects* are
    the things on it that take clicks (menus, the switch, the search box);
    *edge* is how far down from the top a press resizes the window;
    *caption_buttons_rect* is where Windows draws its caption buttons (or
    None).

    Over the caption buttons it answers HTMINBUTTON, HTMAXBUTTON or HTCLOSE
    itself: the client area covers them, so nothing else will — Windows
    gives Snap Layouts to HTMAXBUTTON, and the window carries out the click
    (NativeTitleBar). Returns None only off the client area (Windows' side
    and bottom borders), which is Windows' own to decide.
    """
    p = QPointF(point)
    title = QRectF(title_rect)
    if p.x() < title.left() or p.x() > title.right() or p.y() < title.top():
        return None                           # Windows' own borders
    if p.y() >= title.bottom():
        button = caption_button_at(p, caption_buttons_rect)
        return button if button is not None else HTCLIENT   # below the title row
    if not maximised and p.y() < title.top() + edge:
        corner = 2 * edge
        if p.x() < title.left() + corner:
            return HTTOPLEFT
        if p.x() >= title.right() - corner:
            return HTTOPRIGHT
        return HTTOP
    button = caption_button_at(p, caption_buttons_rect)
    if button is not None:
        return button
    if any(QRectF(rect).contains(p) for rect in widgets_rects):
        return HTCLIENT
    return HTCAPTION


# ---------------------------------------------------------------------------
# Win32, through ctypes: only ever built on Windows
# ---------------------------------------------------------------------------

WM_ACTIVATE = 0x0006
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCMOUSEFIRST = 0x00A0          # WM_NCMOUSEMOVE
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_NCRBUTTONDOWN = 0x00A4
WM_NCRBUTTONUP = 0x00A5
WM_NCMOUSELAST = 0x00AD           # WM_NCXBUTTONDBLCLK
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE = 0xF020
SC_MAXIMIZE = 0xF030
SC_CLOSE = 0xF060
SC_RESTORE = 0xF120
SC_MOVE = 0xF010
SC_SIZE = 0xF000
MF_BYCOMMAND = 0x0000
MF_ENABLED = 0x0000
MF_GRAYED = 0x0001
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
TME_LEAVE = 0x0002
TME_NONCLIENT = 0x0010
WM_NCPOINTERUPDATE = 0x0241
WM_NCPOINTERUP = 0x0243
WM_NCMOUSEHOVER = 0x02A0
WM_NCMOUSELEAVE = 0x02A2

WS_CAPTION = 0x00C00000
GWL_STYLE = -16
SWP_FLAGS_FRAMECHANGED = 0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0010  # FRAMECHANGED NOSIZE NOMOVE NOZORDER NOACTIVATE
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
DWMWA_CAPTION_BUTTON_BOUNDS = 5
DWMWA_CAPTION_COLOR = 35


def _is_dwm_message(message: int) -> bool:
    """The messages DwmDefWindowProc acts on: hit testing and the mouse over
    the non-client area (WM_NCMOUSELEAVE included, or a button stays lit)."""
    return (message == WM_NCHITTEST
            or WM_NCMOUSEFIRST <= message <= WM_NCMOUSELAST
            or WM_NCPOINTERUPDATE <= message <= WM_NCPOINTERUP
            or message in (WM_NCMOUSEHOVER, WM_NCMOUSELEAVE))


def _structures():
    """MARGINS and NCCALCSIZE_PARAMS. Plain ctypes structures: they can be
    made anywhere, which lets the message handling be exercised off Windows."""
    import ctypes
    from ctypes import wintypes

    class MARGINS(ctypes.Structure):
        _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    return MARGINS, NCCALCSIZE_PARAMS


class _Win32:
    """The handful of Win32 and DWM calls the frame needs."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        LRESULT = ctypes.c_ssize_t
        self.LRESULT = LRESULT
        MARGINS, NCCALCSIZE_PARAMS = _structures()
        self.MARGINS = MARGINS
        self.NCCALCSIZE_PARAMS = NCCALCSIZE_PARAMS

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi")
        HWND, UINT, WPARAM, LPARAM = wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM

        self.DefWindowProcW = user32.DefWindowProcW
        self.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
        self.DefWindowProcW.restype = LRESULT
        self.IsZoomed = user32.IsZoomed
        self.IsZoomed.argtypes = [HWND]
        self.IsZoomed.restype = wintypes.BOOL
        self.GetWindowRect = user32.GetWindowRect
        self.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
        self.GetWindowRect.restype = wintypes.BOOL
        self.ClientToScreen = user32.ClientToScreen
        self.ClientToScreen.argtypes = [HWND, ctypes.POINTER(wintypes.POINT)]
        self.ClientToScreen.restype = wintypes.BOOL
        self.ScreenToClient = user32.ScreenToClient
        self.ScreenToClient.argtypes = [HWND, ctypes.POINTER(wintypes.POINT)]
        self.ScreenToClient.restype = wintypes.BOOL
        self.SetWindowPos = user32.SetWindowPos
        self.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, UINT]
        self.SetWindowPos.restype = wintypes.BOOL
        getter = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        getter.argtypes = [HWND, ctypes.c_int]
        getter.restype = ctypes.c_ssize_t
        self.GetWindowLongPtrW = getter
        self.GetSystemMetrics = user32.GetSystemMetrics
        self.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.GetSystemMetrics.restype = ctypes.c_int
        # Windows 10 1607 and later
        self.GetDpiForWindow = getattr(user32, "GetDpiForWindow", None)
        if self.GetDpiForWindow is not None:
            self.GetDpiForWindow.argtypes = [HWND]
            self.GetDpiForWindow.restype = UINT
        self.GetSystemMetricsForDpi = getattr(user32, "GetSystemMetricsForDpi", None)
        if self.GetSystemMetricsForDpi is not None:
            self.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, UINT]
            self.GetSystemMetricsForDpi.restype = ctypes.c_int

        class TRACKMOUSEEVENT(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("hwndTrack", HWND), ("dwHoverTime", wintypes.DWORD)]

        self.TRACKMOUSEEVENT = TRACKMOUSEEVENT
        self.TrackMouseEvent = user32.TrackMouseEvent
        self.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
        self.TrackMouseEvent.restype = wintypes.BOOL
        self.PostMessageW = user32.PostMessageW
        self.PostMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
        self.PostMessageW.restype = wintypes.BOOL
        self.GetSystemMenu = user32.GetSystemMenu
        self.GetSystemMenu.argtypes = [HWND, wintypes.BOOL]
        self.GetSystemMenu.restype = wintypes.HMENU
        self.EnableMenuItem = user32.EnableMenuItem
        self.EnableMenuItem.argtypes = [wintypes.HMENU, UINT, UINT]
        self.EnableMenuItem.restype = wintypes.BOOL
        self.SetMenuDefaultItem = user32.SetMenuDefaultItem
        self.SetMenuDefaultItem.argtypes = [wintypes.HMENU, UINT, UINT]
        self.SetMenuDefaultItem.restype = wintypes.BOOL
        self.TrackPopupMenuEx = user32.TrackPopupMenuEx
        self.TrackPopupMenuEx.argtypes = [wintypes.HMENU, UINT, ctypes.c_int, ctypes.c_int,
                                          HWND, ctypes.c_void_p]
        self.TrackPopupMenuEx.restype = wintypes.BOOL

        self.DwmDefWindowProc = dwmapi.DwmDefWindowProc
        self.DwmDefWindowProc.argtypes = [HWND, UINT, WPARAM, LPARAM, ctypes.POINTER(LRESULT)]
        self.DwmDefWindowProc.restype = wintypes.BOOL
        self.DwmExtendFrameIntoClientArea = dwmapi.DwmExtendFrameIntoClientArea
        self.DwmExtendFrameIntoClientArea.argtypes = [HWND, ctypes.POINTER(MARGINS)]
        self.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        self.DwmGetWindowAttribute = dwmapi.DwmGetWindowAttribute
        self.DwmGetWindowAttribute.argtypes = [HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.DwmGetWindowAttribute.restype = ctypes.c_long
        self.DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
        self.DwmSetWindowAttribute.argtypes = [HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.DwmSetWindowAttribute.restype = ctypes.c_long

    # -- helpers ----------------------------------------------------------
    def dwm_def_window_proc(self, hwnd, message, wparam, lparam):
        result = self.LRESULT(0)
        handled = bool(self.DwmDefWindowProc(hwnd, message, wparam, lparam,
                                             self.ctypes.byref(result)))
        return handled, int(result.value)

    def has_caption(self, hwnd) -> bool:
        """A framed window, not one Qt has made a bare popup for full screen."""
        return (self.GetWindowLongPtrW(hwnd, GWL_STYLE) & WS_CAPTION) == WS_CAPTION

    def frame_thickness(self, hwnd) -> int:
        """The resize border's thickness, in device pixels."""
        if self.GetDpiForWindow is not None and self.GetSystemMetricsForDpi is not None:
            dpi = self.GetDpiForWindow(hwnd) or 96
            return (self.GetSystemMetricsForDpi(SM_CYSIZEFRAME, dpi)
                    + self.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi))
        return self.GetSystemMetrics(SM_CYSIZEFRAME) + self.GetSystemMetrics(SM_CXPADDEDBORDER)

    def screen_to_client(self, hwnd, x, y):
        point = self.wintypes.POINT(x, y)
        self.ScreenToClient(hwnd, self.ctypes.byref(point))
        return point.x, point.y

    def caption_button_bounds(self, hwnd):
        """Where Windows draws its caption buttons, in client device pixels,
        as (left, top, right, bottom); None when it does not say."""
        bounds = self.wintypes.RECT()
        ok = self.DwmGetWindowAttribute(hwnd, DWMWA_CAPTION_BUTTON_BOUNDS,
                                        self.ctypes.byref(bounds),
                                        self.ctypes.sizeof(bounds)) == 0
        if not ok or bounds.right <= bounds.left or bounds.bottom <= bounds.top:
            return None
        # window-relative → client-relative
        window = self.wintypes.RECT()
        origin = self.wintypes.POINT(0, 0)
        if not self.GetWindowRect(hwnd, self.ctypes.byref(window)):
            return None
        self.ClientToScreen(hwnd, self.ctypes.byref(origin))
        dx, dy = origin.x - window.left, origin.y - window.top
        return (bounds.left - dx, bounds.top - dy, bounds.right - dx, bounds.bottom - dy)

    def extend_frame(self, hwnd, top: int) -> None:
        margins = self.MARGINS(0, 0, max(0, int(top)), 0)
        self.DwmExtendFrameIntoClientArea(hwnd, self.ctypes.byref(margins))

    def set_dark(self, hwnd, dark: bool, caption_colour: QColor | None) -> None:
        value = self.wintypes.BOOL(1 if dark else 0)
        size = self.ctypes.sizeof(value)
        if self.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                      self.ctypes.byref(value), size) != 0:
            self.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1,
                                       self.ctypes.byref(value), size)
        if caption_colour is not None:
            # Windows 11: the caption the same colour as the menu row, so the
            # buttons sit on it. Earlier Windows refuses it, harmlessly.
            colour = self.wintypes.DWORD(caption_colour.red() | caption_colour.green() << 8
                                         | caption_colour.blue() << 16)
            self.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, self.ctypes.byref(colour),
                                       self.ctypes.sizeof(colour))

    def track_leaving(self, hwnd) -> None:
        """Ask for WM_NCMOUSELEAVE when the pointer leaves the non-client
        area (DefWindowProc would ask, but it does not see these moves)."""
        track = self.TRACKMOUSEEVENT(self.ctypes.sizeof(self.TRACKMOUSEEVENT),
                                     TME_LEAVE | TME_NONCLIENT, hwnd, 0)
        self.TrackMouseEvent(self.ctypes.byref(track))

    def system_command(self, hwnd, command: int) -> None:
        """What Windows' own button does: SC_MINIMIZE, SC_MAXIMIZE,
        SC_RESTORE or SC_CLOSE, posted so it runs after this message."""
        self.PostMessageW(hwnd, WM_SYSCOMMAND, command, 0)

    def system_menu(self, hwnd, x: int, y: int) -> None:
        """The window's system menu at (x, y) on the screen, as a right-click
        on a title bar opens it; the command picked is carried out."""
        menu = self.GetSystemMenu(hwnd, False)
        if not menu:
            return
        maximised = bool(self.IsZoomed(hwnd))

        def able(command, on):
            self.EnableMenuItem(menu, command, MF_BYCOMMAND | (MF_ENABLED if on else MF_GRAYED))

        able(SC_RESTORE, maximised)
        able(SC_MOVE, not maximised)
        able(SC_SIZE, not maximised)
        able(SC_MINIMIZE, True)
        able(SC_MAXIMIZE, not maximised)
        able(SC_CLOSE, True)
        self.SetMenuDefaultItem(menu, SC_CLOSE, False)
        command = self.TrackPopupMenuEx(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                                        int(x), int(y), hwnd, None)
        if command:
            self.system_command(hwnd, int(command))

    def frame_changed(self, hwnd) -> None:
        """Have Windows send WM_NCCALCSIZE again, so the client area grows."""
        self.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FLAGS_FRAMECHANGED)


_win32: _Win32 | None = None


def _api() -> _Win32 | None:
    global _win32
    if _win32 is None and sys.platform == "win32":
        _win32 = _Win32()
    return _win32


# ---------------------------------------------------------------------------
# The title row
# ---------------------------------------------------------------------------

def app_badge(window) -> QLabel:
    """The application's icon at the left of the title row."""
    from .icons import app_icon
    badge = QLabel(window)
    badge.setObjectName("titleIcon")
    badge.setPixmap(app_icon().pixmap(18, 18))
    badge.setContentsMargins(8, 0, 6, 0)
    badge.setToolTip("CalcForge")
    return badge


#: Kinds of widget on the title row that take a click; anything else there
#: (the icon, empty space) is the title bar and moves the window.
_CLICKABLE = (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox)


class NativeTitleBar(QObject):
    """A MainWindow's menu row, drawn inside Windows' own title bar."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        bar = window.menuBar()
        self.bar = bar
        self.badge = app_badge(window)
        bar.setCornerWidget(self.badge, Qt.TopLeftCorner)
        # room at the right of the menu row for Windows' caption buttons
        self.gap = QWidget()
        self.gap.setObjectName("captionButtonsGap")
        self.gap.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.gap.setFixedSize(0, 0)
        corner = bar.cornerWidget(Qt.TopRightCorner)
        if corner is not None and corner.layout() is not None:
            margins = corner.layout().contentsMargins()
            corner.layout().setContentsMargins(margins.left(), margins.top(), 0, margins.bottom())
            corner.layout().addWidget(self.gap)
        else:
            bar.setCornerWidget(self.gap, Qt.TopRightCorner)
        # now, not when the event loop gets round to it
        self.badge.setVisible(True)
        self.gap.setVisible(True)
        self._padding = None
        #: the caption button a press went down on, for its release
        self._pressed = None
        #: Windows' caption buttons, as Windows last gave them: (distance
        #: from the window's right edge, top, width, height), in
        #: device-independent pixels; None until it has
        self.caption = None
        self._hwnd = None
        bar.installEventFilter(self)
        window.installEventFilter(self)
        self.refresh()

    # -- geometry, in the window's client coordinates ---------------------
    def showing(self) -> bool:
        """Whether the menus are in the title bar just now: the window is a
        window of its own (not a pane of the split view) and not full screen."""
        window = self.window
        return (window.isWindow() and not window.isFullScreen()
                and self.bar.isVisible() and not self.bar.isNativeMenuBar())

    def title_rect(self) -> QRectF:
        geometry = self.bar.geometry()
        return QRectF(0, 0, self.window.width(), geometry.y() + geometry.height())

    def widget_rects(self) -> list:
        """The menus and everything else on the title row that takes clicks."""
        bar = self.bar
        origin = bar.pos()
        rects = []
        for action in bar.actions():
            if action.isVisible() and not action.isSeparator():
                rect = bar.actionGeometry(action)
                if rect.isValid() and rect.width() > 0:
                    rects.append(QRectF(rect.translated(origin)))
        for widget in bar.findChildren(QWidget):
            if (widget is self.gap or widget is self.badge or not widget.isVisible()
                    or widget.isWindow() or widget.window() is not self.window
                    or widget.testAttribute(Qt.WA_TransparentForMouseEvents)):
                continue
            if isinstance(widget, _CLICKABLE) or widget.objectName() == "modeSwitch" \
                    or type(widget).__name__ == "ModeSwitch":
                top_left = widget.mapTo(self.window, widget.rect().topLeft())
                rects.append(QRectF(top_left.x(), top_left.y(), widget.width(), widget.height()))
        return rects

    def _ratio(self) -> float:
        """Device pixels to the window's own (125 % scaling: 1.25)."""
        return self.window.devicePixelRatioF() or 1.0

    def caption_rect(self) -> QRectF:
        """Where Windows' caption buttons are, or would be. They keep to the
        window's right-hand edge, so the place follows a resize at once."""
        if self.caption is not None:
            from_right, top, width, height = self.caption
        else:
            from_right, top = 0, 0
            width, height = FALLBACK_CAPTION_SIZE
        return QRectF(self.window.width() - from_right - width, top, width, height)

    # -- keeping up -------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if watched is self.bar:
            if kind == QEvent.Paint and self.showing() and self.gap.width() > 0:
                QMenuBar.paintEvent(self.bar, event)
                self._clear_caption_area()
                return True
            return False
        if watched is self.window:
            if kind == QEvent.Paint and self.window.testAttribute(Qt.WA_TranslucentBackground):
                self._paint_window_background(event)
            elif kind == QEvent.Show:
                self.refresh(new_window=True)
                QTimer.singleShot(0, self, self.refresh)
            elif kind in (QEvent.Resize, QEvent.WindowStateChange, QEvent.ParentChange,
                          QEvent.ActivationChange, QEvent.ScreenChangeInternal):
                QTimer.singleShot(0, self, self.refresh)
        return False

    def _paint_window_background(self, event) -> None:
        """The window's own background, as its style sheet has it. The alpha
        channel turns Qt's painting of it off (WA_TranslucentBackground
        implies WA_NoSystemBackground), and anything left unpainted would be
        a hole in the window."""
        painter = QPainter(self.window)
        painter.setClipRegion(event.region())
        option = QStyleOption()
        option.initFrom(self.window)
        painter.fillRect(self.window.rect(), self.window.palette().color(QPalette.Window))
        self.window.style().drawPrimitive(QStyle.PE_Widget, option, painter, self.window)
        painter.end()

    def _clear_caption_area(self) -> None:
        """Leave the caption buttons' place transparent: Windows draws them
        there, underneath."""
        rect = self.caption_rect().translated(-QPointF(self.bar.pos()))
        rect = rect.intersected(QRectF(self.bar.rect()))
        if rect.isEmpty():
            return
        painter = QPainter(self.bar)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(rect, Qt.transparent)
        painter.end()

    def refresh(self, new_window: bool = False) -> None:
        """Bring the title row, the frame and Windows up to date."""
        api = _api()
        hwnd = None
        if api is not None and self.window.isWindow() and self.window.testAttribute(Qt.WA_WState_Created):
            hwnd = int(self.window.winId())
            if new_window or hwnd != self._hwnd:
                self._hwnd = hwnd
                api.frame_changed(hwnd)       # the client area takes the caption's place
            bounds = api.caption_button_bounds(hwnd)
            ratio = self._ratio()
            if bounds is not None:
                left, top, right, bottom = (value / ratio for value in bounds)
                self.caption = (max(0.0, self.window.width() - right), top,
                                right - left, bottom - top)
        showing = self.showing()
        caption = self.caption_rect()
        self._fit_title_row(caption if showing else None)
        if hwnd is not None:
            ratio = self._ratio()
            top = max(caption.bottom(), self.title_rect().bottom()) if showing else 0
            api.extend_frame(hwnd, math.ceil(top * ratio))
            self.follow_theme(hwnd)
        self.bar.update()

    def _fit_title_row(self, caption) -> None:
        """Make room on the row for the caption buttons, and make the row at
        least as tall as they are."""
        before = (self.gap.width(), self._padding)
        if caption is None:
            self.gap.setFixedSize(0, 0)
            self._set_padding(None)
        else:
            self.gap.setFixedSize(max(0, math.ceil(self.window.width() - caption.left())), 1)
            self._set_padding(math.ceil(caption.bottom()))
        if (self.gap.width(), self._padding) != before:
            # the menu bar lays its corners out only when it is resized
            QApplication.sendEvent(self.bar, QResizeEvent(self.bar.size(), self.bar.size()))

    def _set_padding(self, height) -> None:
        """Pad the menus so the row is *height* tall, the menus centred in it."""
        bar = self.bar
        if height is None:
            wanted = None
        else:
            text = bar.fontMetrics().height()
            wanted = max(5, (height - text) // 2)
            if (height - text) % 2:
                wanted = (wanted, wanted + 1)
            else:
                wanted = (wanted, wanted)
        if wanted == self._padding:
            return
        self._padding = wanted
        if wanted is None:
            bar.setStyleSheet("")
            bar.setMinimumHeight(0)
        else:
            bar.setStyleSheet(f"QMenuBar::item {{ padding: {wanted[0]}px 11px {wanted[1]}px 11px; }}")
            bar.setMinimumHeight(height)

    def follow_theme(self, hwnd=None) -> None:
        """Windows' buttons dark on the dark theme, light on the light."""
        api = _api()
        if api is None:
            return
        if hwnd is None:
            if not (self.window.isWindow() and self.window.testAttribute(Qt.WA_WState_Created)):
                return
            hwnd = int(self.window.winId())
        dark = self.window.palette().color(QPalette.Window).lightness() < 128
        colour = None
        try:
            from ..theme import DARK, LIGHT, tokens
            colour = QColor(tokens(DARK if dark else LIGHT)["menubar"])
        except Exception:
            pass
        api.set_dark(hwnd, dark, colour)

    # -- the window procedure ----------------------------------------------
    def native_event(self, message) -> tuple | None:
        """Handle one Windows message for the window: (True, result) when it
        is answered here, None to let Qt and Windows carry on."""
        try:
            return self._native_event(message)
        except Exception:                     # never take the window procedure down
            if not getattr(self, "_reported", False):
                self._reported = True
                import traceback
                traceback.print_exc()
            return None

    def _native_event(self, message) -> tuple | None:
        api = _api()
        if api is None or not self.window.isWindow():
            return None
        msg = api.wintypes.MSG.from_address(int(message))
        kind = msg.message
        if kind == WM_NCCALCSIZE:
            return self._calc_size(api, msg)
        if kind == WM_ACTIVATE:
            # as Microsoft's sample does: the frame is extended on activation
            # (Qt resets it whenever it changes the window's flags)
            QTimer.singleShot(0, self, self.refresh)
            return None
        if not _is_dwm_message(kind):
            return None
        hwnd = msg.hWnd
        if not api.has_caption(hwnd):
            return None                       # full screen: no title bar
        # DWM first, on every non-client mouse message: it draws the caption
        # buttons, and lights and presses them from these
        handled, result = api.dwm_def_window_proc(hwnd, kind, msg.wParam, msg.lParam)
        if kind == WM_NCHITTEST:
            return self._answer_hit_test(api, hwnd, msg.lParam, handled, result)
        if not (WM_NCMOUSEFIRST <= kind <= WM_NCMOUSELAST or kind == WM_NCMOUSELEAVE):
            # pen and touch (WM_NCPOINTER*): DefWindowProc turns what is left
            # of them into the mouse messages handled below
            return (True, result) if handled else None
        where = int(msg.wParam)               # the hit-test code the message is for
        if where in CAPTION_BUTTON_CODES and kind != WM_NCMOUSELEAVE:
            return self._caption_button_message(api, hwnd, kind, where, handled, result)
        if kind == WM_NCMOUSELEAVE:
            self._pressed = None
        if kind == WM_NCRBUTTONUP and where == HTCAPTION:
            # Qt takes the WM_CONTEXTMENU that would follow for a context
            # menu of its own (the title row is client area to it), so the
            # system menu is opened here, as Windows' title bar opens it
            x, y = _point_of(api, msg.lParam)
            api.system_menu(hwnd, x, y)
            return True, 0
        # anything else — a press, drag or double-click on the caption — is
        # Windows' own to carry out: moving, snapping, maximising
        return None

    def _answer_hit_test(self, api, hwnd, lparam, handled, result):
        code = self._hit(api, hwnd, lparam)
        if code in TOP_EDGE_CODES:
            return True, code
        if code in CAPTION_BUTTON_CODES:
            # DWM knows its buttons best, when it says
            return True, (result if handled and result in CAPTION_BUTTON_CODES else code)
        if handled and result in CAPTION_BUTTON_CODES:
            return True, result
        if code is None:
            return None
        return True, code

    def _caption_button_message(self, api, hwnd, kind, button, handled, result):
        """The mouse on Windows' minimise, maximise or close button.

        Left to DefWindowProc, a press there starts the old button-tracking
        loop, which looks for the buttons in a caption this window no longer
        has, and the click comes to nothing. So, as apps that draw into the
        caption do, the press is noted here and the release on the same
        button carries out the button's command.
        """
        if kind in (WM_NCLBUTTONDOWN, WM_NCLBUTTONDBLCLK):
            # what maximise does is settled at the press: restore if the
            # window was maximised then (so a second command, should DWM
            # also send one, changes nothing)
            self._pressed = (button, bool(api.IsZoomed(hwnd)))
            return True, 0
        if kind == WM_NCLBUTTONUP:
            pressed, self._pressed = self._pressed, None
            if pressed is not None and pressed[0] == button:
                if button == HTMINBUTTON:
                    api.system_command(hwnd, SC_MINIMIZE)
                elif button == HTMAXBUTTON:
                    api.system_command(hwnd, SC_RESTORE if pressed[1] else SC_MAXIMIZE)
                elif button == HTCLOSE:
                    api.system_command(hwnd, SC_CLOSE)
            return True, 0
        if kind in (WM_NCRBUTTONDOWN, WM_NCRBUTTONUP):
            return True, 0                    # a right-click on a button does nothing
        if kind == WM_NCMOUSEMOVE:
            api.track_leaving(hwnd)
        # the hover is DWM's to show (and Windows 11's Snap Layouts come from
        # the HTMAXBUTTON hit test); DefWindowProc is kept out of it, as it
        # would draw the old style of button over the window
        return True, (result if handled else 0)

    def _calc_size(self, api, msg):
        if not msg.wParam or not api.has_caption(msg.hWnd):
            return None
        params = api.NCCALCSIZE_PARAMS.from_address(msg.lParam)
        top, left = params.rgrc[0].top, params.rgrc[0].left
        result = api.DefWindowProcW(msg.hWnd, WM_NCCALCSIZE, msg.wParam, msg.lParam)
        if result != 0:
            return True, result
        # Only the top of the frame goes; the sides and bottom stay Windows'.
        # A maximised window hangs off the screen by the frame's thickness —
        # the side border's — so its top is pushed back onto the screen.
        border = params.rgrc[0].left - left
        params.rgrc[0].top = top + (border if api.IsZoomed(msg.hWnd) else 0)
        return True, 0

    def _hit(self, api, hwnd, lparam):
        x, y = _point_of(api, lparam)
        x, y = api.screen_to_client(hwnd, x, y)
        ratio = self._ratio()
        point = QPointF(x / ratio, y / ratio)
        if not self.showing():
            return None
        title = self.title_rect()
        widgets = self.widget_rects() if title.top() <= point.y() < title.bottom() else []
        return hit_test(point, title, widgets, api.frame_thickness(hwnd) / ratio,
                        self.caption_rect(), bool(api.IsZoomed(hwnd)))


def _point_of(api, lparam):
    """The screen point packed in a mouse message's lParam (GET_X_LPARAM,
    GET_Y_LPARAM: signed, for monitors left of or above the main one)."""
    return (api.ctypes.c_short(lparam & 0xFFFF).value,
            api.ctypes.c_short((lparam >> 16) & 0xFFFF).value)


def install(window) -> None:
    """Give *window* (a MainWindow) its frame: on Windows, the native frame
    with the menus inside its title bar; elsewhere, the plain native frame."""
    window._native_frame = None
    if not IN_TITLE_BAR or QApplication.platformName() != "windows":
        return                                # (an offscreen test run on Windows)
    # An alpha channel, so the caption buttons' place can be left
    # transparent for Windows to draw them; it has to be there before the
    # native window is made. (A framed window is not made a layered window
    # by this: Qt only does that for frameless ones.)
    window.setAttribute(Qt.WA_TranslucentBackground, True)
    window._native_frame = NativeTitleBar(window)


def follow_theme() -> None:
    """The theme changed: every window's caption buttons follow it."""
    if not IN_TITLE_BAR:
        return
    for widget in QApplication.topLevelWidgets():
        frame = getattr(widget, "_native_frame", None)
        if frame is not None:
            frame.follow_theme()
            frame.bar.update()
