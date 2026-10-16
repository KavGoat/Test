"""What a first-time user sees: menu bar, toolbars, panels, first screenshot.

    QT_QPA_PLATFORM=offscreen python tools/qa/novice/explore.py > out.txt
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

w = H.new_window()
pdf = H.make_pdf(H.WORK + "/set.pdf")
w.open_from_command_line(pdf)
H.pump(5)
print("TOP:", H.top_menu_names(w))
for label, act in H.menu_tree(w):
    sc = act.shortcut().toString()
    print(label, ("  [" + sc + "]") if sc else "", "" if act.isEnabled() else "(off)")
print("=== TOOLBARS")
for t in H.toolbar_buttons(w):
    print(t)
print("=== DOCKS", H.docks(w))
print("=== STATUS", [c.text() for c in w.statusBar().findChildren(H.QLabel) if c.isVisible()])
H.shot(w, "00_first_open")
