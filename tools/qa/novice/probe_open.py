"""Does opening a second PDF add a tab or replace the first one?"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import harness as H
    import tasks as T
    w = H.new_window()
    a = H.make_pdf(os.path.join(H.WORK, "a.pdf"), 2)
    b = H.make_pdf(os.path.join(H.WORK, "b.pdf"), 2)
    c = H.make_pdf(os.path.join(H.WORK, "c.pdf"), 2)
    print("start tabs", T.tab_names(w), len(w._open_documents))
    w.open_from_command_line(a)
    H.pump(3)
    print("after cmdline a:", T.tab_names(w), len(w._open_documents))
    log = H.Log("probe")
    T.open_via_dialog(H, w, b, log)
    print("after File>Open b:", T.tab_names(w), len(w._open_documents))
    T.open_via_dialog(H, w, c, log)
    print("after File>Open c:", T.tab_names(w), len(w._open_documents))
    print("recent:", H.menu_search(w, "a.pdf", "b.pdf", "c.pdf"))
    print(log.notes)


if __name__ == "__main__":
    main()
