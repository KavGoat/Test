"""The window's frame is the system's own (the user, 2026-10-16: "put the top
bar in the normal window bar with Windows' window controls"). On Windows the menus are drawn inside its title bar; elsewhere
they are a row under it. No window draws its own minimise, maximise or close.

The Win32 side cannot run here; what can is the hit-test decision (a pure
function) and the Qt side of the title row.
"""
import sys

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QApplication, QWidget

from calcforge.ui import nativeframe
from calcforge.ui.nativeframe import (HTCAPTION, HTCLIENT, HTCLOSE, HTMAXBUTTON, HTMINBUTTON,
                                      HTTOP, HTTOPLEFT, HTTOPRIGHT, hit_test)

TITLE = QRectF(0, 0, 1000, 32)
MENUS = [QRectF(30, 0, 40, 32), QRectF(70, 0, 40, 32)]     # File, Edit
SEARCH = QRectF(600, 4, 200, 24)
CAPTION = QRectF(862, 0, 138, 30)
EDGE = 8


def _hit(x, y, maximised=False):
    return hit_test(QPointF(x, y), TITLE, MENUS + [SEARCH], EDGE, CAPTION, maximised)


def _settle(times=6):
    for _ in range(times):
        QApplication.processEvents()


# -- the hit-test decision ------------------------------------------------

def test_an_empty_part_of_the_title_row_is_the_caption():
    assert _hit(300, 16) == HTCAPTION          # between the menus and the search
    assert _hit(10, 20) == HTCAPTION           # the icon
    assert _hit(830, 16) == HTCAPTION          # beside the caption buttons


def test_the_menus_and_the_search_box_are_the_client():
    assert _hit(50, 16) == HTCLIENT
    assert _hit(90, 20) == HTCLIENT
    assert _hit(700, 16) == HTCLIENT


def test_the_top_edge_resizes():
    assert _hit(300, 2) == HTTOP
    assert _hit(50, 2) == HTTOP                # over a menu too
    assert _hit(3, 2) == HTTOPLEFT
    assert _hit(998, 2) == HTTOPRIGHT


def test_maximised_there_is_no_top_edge():
    assert _hit(300, 2, maximised=True) == HTCAPTION
    assert _hit(50, 2, maximised=True) == HTCLIENT
    assert _hit(3, 2, maximised=True) == HTCAPTION


def test_over_the_caption_buttons_they_are_the_buttons():
    # the client area covers them, so the hit test has to say which they are
    assert _hit(870, 16) == HTMINBUTTON         # 862–908
    assert _hit(930, 16) == HTMAXBUTTON         # 908–954 (Snap Layouts)
    assert _hit(990, 20) == HTCLOSE             # 954–1000
    assert _hit(999, 29, maximised=True) == HTCLOSE
    assert _hit(931, 2, maximised=True) == HTMAXBUTTON   # maximised: to the very top
    assert _hit(931, 2) == HTTOP                # otherwise the top edge resizes


def test_below_the_title_row_is_the_client_and_outside_it_is_windows_border():
    assert _hit(300, 200) == HTCLIENT
    assert _hit(-3, 16) is None                # the left resize border
    assert _hit(1004, 200) is None             # the right one


# -- no frame of our own ----------------------------------------------------

def test_the_window_keeps_the_ordinary_frame(window):
    window.show()
    _settle()
    if window._native_frame is not None:
        # Windows: its own frame too, with the menus inside its title bar
        assert not window.windowFlags() & Qt.FramelessWindowHint
        assert not hasattr(window, "window_buttons")
        return
    assert not window.windowFlags() & Qt.FramelessWindowHint
    assert not hasattr(window, "window_buttons")
    assert window._native_frame is None
    assert window.contentsMargins().top() == 0
    names = {child.objectName() for child in window.findChildren(QWidget)}
    assert not {name for name in names
                if name.startswith("titleButton") or name == "windowButtons"}
    # the menus are an ordinary row under the title bar
    assert window.menuBar().isVisible() or window.menuBar().isNativeMenuBar()


def test_full_screen_comes_and_goes_with_the_ordinary_frame(window):
    window.show()
    _settle()
    window.act_full_screen.trigger()
    _settle()
    assert window.isFullScreen()
    window.act_full_screen.trigger()
    _settle()
    assert not window.isFullScreen()
    assert not window.windowFlags() & Qt.FramelessWindowHint


def test_split_and_unsplit_keep_the_ordinary_frame(window):
    window.show()
    window.open_in_new_tab()
    window.split_document(0)
    _settle()
    assert window.is_split and window.isWindow()
    assert not window.windowFlags() & Qt.FramelessWindowHint
    window.act_split_view.trigger()
    _settle()
    assert not window.is_split and window.isWindow()
    assert not window.windowFlags() & Qt.FramelessWindowHint
    assert len(window._open_documents) == 2


# -- the title row's Qt side (what Windows' messages are answered from) ------

@pytest.fixture
def title_row(window):
    """The title row as Windows has it, built here without the Win32 calls."""
    window.show()
    _settle()
    frame = window._native_frame
    if frame is None:
        frame = nativeframe.NativeTitleBar(window)
        window._native_frame = frame
    _settle()
    frame.refresh()
    _settle()
    return frame


def test_the_title_row_keeps_room_for_windows_buttons(window, title_row):
    bar = window.menuBar()
    caption = title_row.caption_rect()
    assert title_row.gap.width() >= caption.width()
    assert bar.height() >= caption.height()
    assert bar.cornerWidget(Qt.TopLeftCorner) is title_row.badge
    # nothing that takes a click is under the buttons
    assert not any(rect.intersects(caption) for rect in title_row.widget_rects())
    # Windows' buttons show through: their place on the row is transparent
    image = bar.grab().toImage()
    at = caption.center().toPoint() - bar.pos()
    assert image.pixelColor(at).alpha() == 0
    assert image.pixelColor(5, 5).alpha() == 255


def test_the_title_row_answers_as_a_title_bar(window, title_row):
    bar = window.menuBar()
    title = title_row.title_rect()
    rects = title_row.widget_rects()
    caption = title_row.caption_rect()

    def hit(point):
        return hit_test(point, title, rects, 8, caption, False)

    file_menu = bar.actions()[0]
    assert hit(QPointF(bar.actionGeometry(file_menu).center())) == HTCLIENT
    field = window.search_field
    assert hit(QPointF(field.mapTo(window, field.rect().center()))) == HTCLIENT
    switch = window.mode_switch
    assert hit(QPointF(switch.mapTo(window, switch.rect().center()))) == HTCLIENT
    # between the last menu and the switch: the window moves from there
    last = max(bar.actionGeometry(a).right() for a in bar.actions() if a.isVisible())
    left_of_switch = switch.mapTo(window, switch.rect().topLeft()).x()
    if left_of_switch - last > 4:
        assert hit(QPointF((last + left_of_switch) / 2, title.height() / 2)) == HTCAPTION
    assert hit(QPointF(window.width() / 2, title.bottom() + 40)) == HTCLIENT


def test_the_title_row_steps_aside_in_full_screen_and_stays_in_the_split(window, title_row):
    window.act_full_screen.trigger()
    _settle()
    title_row.refresh()
    assert title_row.gap.width() == 0
    window.act_full_screen.trigger()
    _settle()
    title_row.refresh()
    assert title_row.gap.width() > 0
    window.open_in_new_tab()
    window.split_document(0)
    _settle()
    title_row.refresh()
    assert title_row.gap.width() > 0            # still one window, one title bar
    window.act_split_view.trigger()
    _settle()
    title_row.refresh()
    assert title_row.gap.width() > 0


def test_the_native_frame_imports_without_windows():
    assert nativeframe.IN_TITLE_BAR == (sys.platform == "win32")
    if sys.platform != "win32":
        assert nativeframe._api() is None


# -- the message handling, against a stand-in for Win32 ----------------------

class _FakeWin32:
    """Stands in for nativeframe._Win32: the same calls, answered as Windows
    would for a 1000 x 700 window at (100, 100) with 8 px borders."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.MARGINS, self.NCCALCSIZE_PARAMS = nativeframe._structures()
        self.zoomed = False
        self.caption_style = True
        self.dwm_answer = (False, 0)
        self.calls = []
        self.origin = (0, 0)
        self.bounds = None
        self.commands = []
        self.menus = []

    def DefWindowProcW(self, hwnd, message, wparam, lparam):
        params = self.NCCALCSIZE_PARAMS.from_address(lparam)
        rect = params.rgrc[0]
        rect.left += 8
        rect.right -= 8
        rect.bottom -= 8
        rect.top += 31 + 8                        # caption and frame
        return 0

    def IsZoomed(self, hwnd):
        return self.zoomed

    def has_caption(self, hwnd):
        return self.caption_style

    def dwm_def_window_proc(self, hwnd, message, wparam, lparam):
        self.calls.append(message)
        return self.dwm_answer

    def screen_to_client(self, hwnd, x, y):
        return x - self.origin[0], y - self.origin[1]

    def frame_thickness(self, hwnd):
        return 8

    def frame_changed(self, hwnd):
        self.calls.append("frame_changed")

    def caption_button_bounds(self, hwnd):
        return self.bounds                        # client device pixels, or None

    def system_command(self, hwnd, command):
        self.commands.append(command)

    def system_menu(self, hwnd, x, y):
        self.menus.append((x, y))

    def track_leaving(self, hwnd):
        self.calls.append("track")

    def extend_frame(self, hwnd, top):
        self.calls.append(("extend", top))

    def set_dark(self, hwnd, dark, colour):
        self.calls.append(("dark", dark))


def _message(kind, wparam=0, lparam=0):
    from ctypes import addressof, wintypes
    msg = wintypes.MSG()
    msg.hWnd = 1234
    msg.message = kind
    msg.wParam = wparam
    msg.lParam = lparam
    return msg, addressof(msg)


def _lparam(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


@pytest.fixture
def fake_win32(monkeypatch, window):
    if window._native_frame is not None and sys.platform == "win32":
        pytest.skip("a real window procedure would be answered by the stand-in")
    fake = _FakeWin32()
    monkeypatch.setattr(nativeframe, "_api", lambda: fake)
    return fake


def test_the_top_of_the_frame_goes_and_the_sides_stay(title_row, fake_win32):
    from ctypes import addressof
    params = fake_win32.NCCALCSIZE_PARAMS()
    params.rgrc[0].left, params.rgrc[0].top = 100, 100
    params.rgrc[0].right, params.rgrc[0].bottom = 1100, 800
    _msg, address = _message(nativeframe.WM_NCCALCSIZE, 1, addressof(params))
    assert title_row.native_event(address) == (True, 0)
    rect = params.rgrc[0]
    assert (rect.left, rect.top, rect.right, rect.bottom) == (108, 100, 1092, 792)
    # maximised, the top comes down by the frame that hangs off the screen
    fake_win32.zoomed = True
    params.rgrc[0].left, params.rgrc[0].top = -8, -8
    params.rgrc[0].right, params.rgrc[0].bottom = 1928, 1048
    assert title_row.native_event(address) == (True, 0)
    assert (params.rgrc[0].left, params.rgrc[0].top) == (0, 0)
    # full screen (a bare popup) and wParam FALSE are Windows' own
    fake_win32.caption_style = False
    assert title_row.native_event(address) is None
    fake_win32.caption_style = True
    _msg, address = _message(nativeframe.WM_NCCALCSIZE, 0, addressof(params))
    assert title_row.native_event(address) is None


def test_hit_testing_through_the_window_procedure(window, title_row, fake_win32):
    bar = window.menuBar()
    hit = nativeframe.WM_NCHITTEST

    def ask(x, y):
        _msg, address = _message(hit, 0, _lparam(int(x), int(y)))
        return title_row.native_event(address)

    file_menu = bar.actionGeometry(bar.actions()[0]).center()
    assert ask(file_menu.x(), file_menu.y()) == (True, HTCLIENT)
    assert ask(window.width() / 2, 300) == (True, HTCLIENT)
    badge = title_row.badge                      # the icon moves the window
    icon = badge.mapTo(window, badge.rect().center())
    assert ask(icon.x(), icon.y()) == (True, HTCAPTION)
    assert ask(window.width() / 2, 2) == (True, HTTOP)
    assert ask(-4, 300) is None                    # Windows' left border
    # Windows' buttons: DwmDefWindowProc answers, and is asked first
    fake_win32.dwm_answer = (True, nativeframe.HTMAXBUTTON)
    caption = title_row.caption_rect().center()
    assert ask(caption.x(), caption.y()) == (True, nativeframe.HTMAXBUTTON)
    assert fake_win32.calls[-1] == hit
    # the top edge still resizes above them; maximised, the buttons reach the top
    assert ask(caption.x(), 2) == (True, HTTOP)
    fake_win32.zoomed = True
    assert ask(caption.x(), 2) == (True, nativeframe.HTMAXBUTTON)
    # the pointer leaving is DWM's to see (it unlights the buttons) and then
    # Windows'
    fake_win32.dwm_answer = (True, 0)
    _msg, address = _message(nativeframe.WM_NCMOUSELEAVE)
    assert title_row.native_event(address) is None
    assert fake_win32.calls[-1] == nativeframe.WM_NCMOUSELEAVE
    # in full screen there is no title bar to answer for
    fake_win32.caption_style = False
    assert ask(window.width() / 2, 15) is None


def test_the_frame_is_extended_behind_the_title_row(window, title_row, fake_win32):
    fake_win32.calls.clear()
    title_row.refresh(new_window=True)
    assert "frame_changed" in fake_win32.calls
    (top,) = [call[1] for call in fake_win32.calls if call[0] == "extend"]
    assert top >= window.menuBar().height()
    assert ("dark", window.palette().window().color().lightness() < 128) in fake_win32.calls


# -- the caption buttons, through the window procedure, at several scales ----

N = nativeframe


def _send(frame, kind, wparam=0, lparam=0):
    _msg, address = _message(kind, wparam, lparam)
    return frame.native_event(address)


@pytest.fixture(params=[1.0, 1.25, 1.5, 2.0], ids=["100%", "125%", "150%", "200%"])
def scaled(request, window, title_row, fake_win32, monkeypatch):
    """The title row at a display scale, the window at (200, 100) on the
    screen, and Windows' buttons where DWMWA_CAPTION_BUTTON_BOUNDS puts them:
    46 x 30 each at 100 %, at the window's top right."""
    ratio = request.param
    monkeypatch.setattr(title_row, "_ratio", lambda: ratio)
    fake_win32.origin = (200, 100)
    width = window.width() * ratio
    fake_win32.bounds = (round(width - 138 * ratio), 0, round(width), round(30 * ratio))
    title_row.refresh()
    _settle()
    title_row.refresh()

    def at(x, y):
        """lParam of a logical point in the window."""
        return _lparam(round(200 + x * ratio), round(100 + y * ratio))

    return title_row, fake_win32, at, ratio


def test_the_buttons_answer_the_hit_test_at_every_scale(window, scaled):
    frame, fake, at, ratio = scaled
    right = window.width()
    for x, code in ((right - 115, HTMINBUTTON), (right - 69, HTMAXBUTTON),
                    (right - 23, HTCLOSE), (right - 2, HTCLOSE)):
        assert _send(frame, N.WM_NCHITTEST, 0, at(x, 18)) == (True, code), (ratio, x)
    # DWM is asked first, every time
    assert fake.calls.count(N.WM_NCHITTEST) == 4
    # and its own answer, when it gives one, is the one used
    fake.dwm_answer = (True, HTCLOSE)
    assert _send(frame, N.WM_NCHITTEST, 0, at(right - 69, 18)) == (True, HTCLOSE)
    fake.dwm_answer = (False, 0)
    # the menus stop before the buttons
    caption = frame.caption_rect()
    assert caption.left() == pytest.approx(right - 138, abs=1)
    assert not any(rect.intersects(caption) for rect in frame.widget_rects())
    bar = window.menuBar()
    menu = bar.actionGeometry(bar.actions()[1]).center()
    assert _send(frame, N.WM_NCHITTEST, 0, at(menu.x(), menu.y())) == (True, HTCLIENT)
    icon = frame.badge.mapTo(window, frame.badge.rect().center())
    assert _send(frame, N.WM_NCHITTEST, 0, at(icon.x(), icon.y())) == (True, HTCAPTION)
    # the top edge, a frame's thickness (8 device pixels) deep
    assert _send(frame, N.WM_NCHITTEST, 0, at(icon.x(), 7 / ratio))[1] in N.TOP_EDGE_CODES
    assert _send(frame, N.WM_NCHITTEST, 0, at(icon.x(), 9 / ratio)) == (True, HTCAPTION)


def test_a_click_on_each_button_does_what_the_button_does(window, scaled):
    frame, fake, at, _ratio = scaled
    right = window.width()
    for x, command in ((right - 115, N.SC_MINIMIZE), (right - 69, N.SC_MAXIMIZE),
                       (right - 23, N.SC_CLOSE)):
        code = _send(frame, N.WM_NCHITTEST, 0, at(x, 18))[1]
        fake.commands.clear()
        # the press is kept from DefWindowProc (its button tracking looks for
        # a caption the window no longer has) and the release acts
        assert _send(frame, N.WM_NCLBUTTONDOWN, code, at(x, 18)) == (True, 0)
        assert fake.commands == []
        assert _send(frame, N.WM_NCLBUTTONUP, code, at(x, 18)) == (True, 0)
        assert fake.commands == [command]
        # DWM saw both, to show the press
        assert fake.calls[-2:] == [N.WM_NCLBUTTONDOWN, N.WM_NCLBUTTONUP]
    # maximised, the middle button restores
    fake.zoomed = True
    fake.commands.clear()
    _send(frame, N.WM_NCLBUTTONDOWN, HTMAXBUTTON, at(right - 69, 18))
    _send(frame, N.WM_NCLBUTTONUP, HTMAXBUTTON, at(right - 69, 18))
    assert fake.commands == [N.SC_RESTORE]


def test_a_press_let_go_elsewhere_does_nothing(window, scaled):
    frame, fake, at, _ratio = scaled
    right = window.width()
    _send(frame, N.WM_NCLBUTTONDOWN, HTCLOSE, at(right - 23, 18))
    _send(frame, N.WM_NCLBUTTONUP, HTMAXBUTTON, at(right - 69, 18))
    assert fake.commands == []
    _send(frame, N.WM_NCLBUTTONDOWN, HTCLOSE, at(right - 23, 18))
    _send(frame, N.WM_NCMOUSELEAVE)
    _send(frame, N.WM_NCLBUTTONUP, HTCLOSE, at(right - 23, 18))
    assert fake.commands == []
    # a release with no press before it (pressed in the client, say)
    _send(frame, N.WM_NCLBUTTONUP, HTMINBUTTON, at(right - 115, 18))
    assert fake.commands == []


def test_hovering_the_buttons_is_dwms_and_never_defwindowprocs(window, scaled):
    frame, fake, at, _ratio = scaled
    right = window.width()
    assert _send(frame, N.WM_NCMOUSEMOVE, HTMAXBUTTON, at(right - 69, 18)) == (True, 0)
    assert fake.calls[-2:] == [N.WM_NCMOUSEMOVE, "track"]    # and asks for the leave
    fake.dwm_answer = (True, 0)
    assert _send(frame, N.WM_NCMOUSEMOVE, HTCLOSE, at(right - 23, 18)) == (True, 0)


def test_the_caption_still_drags_snaps_and_double_click_maximises(window, scaled):
    frame, fake, at, _ratio = scaled
    icon = frame.badge.mapTo(window, frame.badge.rect().center())
    point = at(icon.x(), icon.y())
    # Windows' own: the drag, Aero Snap, and the double-click — even should
    # DWM claim the message
    for kind in (N.WM_NCLBUTTONDOWN, N.WM_NCLBUTTONDBLCLK, N.WM_NCLBUTTONUP):
        assert _send(frame, kind, HTCAPTION, point) is None
        fake.dwm_answer = (True, 0)
        assert _send(frame, kind, HTCAPTION, point) is None
        fake.dwm_answer = (False, 0)
    assert fake.commands == []


def test_a_right_click_on_the_caption_opens_the_system_menu(window, scaled):
    frame, fake, at, ratio = scaled
    icon = frame.badge.mapTo(window, frame.badge.rect().center())
    point = at(icon.x(), icon.y())
    assert _send(frame, N.WM_NCRBUTTONDOWN, HTCAPTION, point) is None
    assert _send(frame, N.WM_NCRBUTTONUP, HTCAPTION, point) == (True, 0)
    assert fake.menus == [(round(200 + icon.x() * ratio), round(100 + icon.y() * ratio))]
    # not on the buttons
    right = window.width()
    assert _send(frame, N.WM_NCRBUTTONUP, HTCLOSE, at(right - 23, 18)) == (True, 0)
    assert len(fake.menus) == 1


def test_a_screen_left_of_the_main_one_gives_negative_points(window, title_row, fake_win32):
    fake_win32.origin = (-1500, -40)
    fake_win32.bounds = None
    title_row.refresh()
    caption = title_row.caption_rect()
    x, y = int(-1500 + caption.right() - 10), int(-40 + 15)
    assert _send(title_row, N.WM_NCHITTEST, 0, _lparam(x, y)) == (True, HTCLOSE)


def test_full_screen_leaves_every_message_to_windows(window, scaled):
    frame, fake, at, _ratio = scaled
    fake.caption_style = False
    right = window.width()
    assert _send(frame, N.WM_NCHITTEST, 0, at(right - 23, 18)) is None
    assert _send(frame, N.WM_NCLBUTTONUP, HTCLOSE, at(right - 23, 18)) is None
    assert fake.commands == []
