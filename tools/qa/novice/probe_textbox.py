"""Text box: does a single click make one, and does Esc keep what was typed?"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import harness as H
    import tasks as T
    from PySide6.QtCore import Qt
    from calcforge.items.text import TextItem
    for finish in ("esc", "click"):
        for how in ("click", "drag"):
            w, _ = T.opened(H, 1)
            H.click_toolbar(w, H.toolbar_action(w, "text box", exact=True)[0][1])
            p = T.page_point(w, 700, 650)
            if how == "click":
                H.click(w.view, p.x(), p.y())
            else:
                q = T.page_point(w, 860, 680)
                H.drag(w.view, p.x(), p.y(), q.x(), q.y())
            H.pump(2)
            made = [t.text() for t in T.items_of(w, TextItem)]
            print("   placed; editing:", w.view.editing_item() is not None,
                  "focus:", type(H.QApplication.focusWidget()).__name__, "tool:", w.view.tool_key, "hint:", w.status_hint.text())
            tools = []
            for ch in "Cover TBC":
                T.typing(H, w, ch)
                tools.append(w.view.tool_key)
            print("   tool after each letter:", tools)
            if finish == "esc":
                H.key(H.QApplication.focusWidget() or w.view.viewport(), Qt.Key_Escape)
            else:
                e = T.page_point(w, 1100, 100)
                H.click(w.view, e.x(), e.y())
            H.pump(2)
            print(f"{how:5} then {finish:5}: after placing {made}; after typing+finish "
                  f"{[t.text() for t in T.items_of(w, TextItem)]}; hint {w.status_hint.text()!r}")


if __name__ == "__main__":
    main()
