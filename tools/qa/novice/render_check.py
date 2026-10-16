"""Does an opened PDF draw its content, and how long until it does?

The tile renderer uses spawn-started processes, so every script here keeps
its work under ``if __name__ == "__main__"``.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import harness as H
    from PySide6.QtTest import QTest
    w = H.new_window()
    pdf = H.make_pdf(H.WORK + "/set.pdf")
    t0 = time.perf_counter()
    w.open_from_command_line(pdf)
    H.pump(5)
    print("open ms", (time.perf_counter() - t0) * 1000)
    for ms in (0, 500, 2000):
        QTest.qWait(ms)
        H.shot(w, f"01_render_after_{ms}")


if __name__ == "__main__":
    main()
