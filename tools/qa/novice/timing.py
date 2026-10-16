"""Stalls the novice run saw, timed properly: first time and median of 5.

    QT_QPA_PLATFORM=offscreen python tools/qa/novice/timing.py
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import harness as H
    import tasks as T
    from PySide6.QtCore import Qt
    H.CURRENT = None                       # no Log: measure here instead
    w, _ = T.opened(H, 4)
    results = {}

    def measure(name, setup, action, n=5):
        times = []
        for i in range(n):
            setup(i)
            H.pump(3)
            t0 = time.perf_counter()
            action(i)
            H.pump(2)
            times.append((time.perf_counter() - t0) * 1000)
        results[name] = (times[0], statistics.median(times), max(times))

    def tool(name):
        return H.toolbar_action(w, name, exact=True)[0][1]

    def esc(_i=0):
        H.key(w.view.viewport(), Qt.Key_Escape)
        e = T.page_point(w, 1150, 60)
        H.click(w.view, e.x(), e.y())

    def pick(name):
        act = tool(name)
        for bar in w.findChildren(H.QToolBar):
            btn = bar.widgetForAction(act)
            if btn is not None and btn.isVisible():
                from PySide6.QtTest import QTest
                QTest.mouseClick(btn, Qt.LeftButton)
                return

    measure("pick Cloud+ tool (toolbar)", esc, lambda i: pick("Cloud+"))

    def cloud_drag(i):
        a, b = T.page_point(w, 200 + 40 * i, 600), T.page_point(w, 260 + 40 * i, 650)
        H.drag(w.view, a.x(), a.y(), b.x(), b.y())

    def cloud_place(i):
        c = T.page_point(w, 220 + 40 * i, 720)
        H.click(w.view, c.x(), c.y())
    times_drag, times_place = [], []
    for i in range(5):
        esc()
        pick("Cloud+")
        H.pump(3)
        t0 = time.perf_counter(); cloud_drag(i); H.pump(2)
        times_drag.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter(); cloud_place(i); H.pump(2)
        times_place.append((time.perf_counter() - t0) * 1000)
        T.typing(H, w, "x")
    results["Cloud+ drag"] = (times_drag[0], statistics.median(times_drag), max(times_drag))
    results["Cloud+ click where the words go"] = (
        times_place[0], statistics.median(times_place), max(times_place))

    def table_setup(i):
        esc()
        pick("Table")

    def table_drag(i):
        a, b = T.page_point(w, 700, 100 + 110 * i), T.page_point(w, 900, 190 + 110 * i)
        H.drag(w.view, a.x(), a.y(), b.x(), b.y())
    measure("Table drag", table_setup, table_drag)

    def tb_setup(i):
        esc()
        pick("Text box")

    def tb_drag(i):
        a, b = T.page_point(w, 950, 100 + 60 * i), T.page_point(w, 1100, 130 + 60 * i)
        H.drag(w.view, a.x(), a.y(), b.x(), b.y())
    measure("Text box drag", tb_setup, tb_drag)

    from calcforge.items.text import CalloutItem
    callout = T.items_of(w, CalloutItem)[0]
    c = callout.mapToScene(callout.boundingRect().center())

    def rc(i):
        H.right_click_menu(w.view, c.x(), c.y())
    measure("right-click a Cloud+ (menu opens)", esc, rc)

    def split(i):
        act = H.menu_action(w, "View > Split View")
        act.trigger()
        H.pump(3)

    def unsplit(i):
        host = w._split_host
        if host is not None:
            act = H.menu_action(w, "View > Split View")
            act.trigger()
            H.pump(3)
    times_s, times_u = [], []
    for i in range(3):
        t0 = time.perf_counter(); split(i)
        times_s.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter(); unsplit(i)
        times_u.append((time.perf_counter() - t0) * 1000)
    results["View > Split View (on)"] = (times_s[0], statistics.median(times_s), max(times_s))
    results["View > Split View (off)"] = (times_u[0], statistics.median(times_u), max(times_u))

    for name, (first, med, worst) in results.items():
        flag = "  <-- over 100 ms" if med > 100 or first > 100 else ""
        print(f"{name:40} first {first:7.0f} ms  median {med:7.0f}  max {worst:7.0f}{flag}")


if __name__ == "__main__":
    main()
