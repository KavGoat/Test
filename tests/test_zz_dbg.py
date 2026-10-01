from PySide6.QtWidgets import QApplication
from tests.test_format import _a_drawing_marked_up_elsewhere
def test_dbg(window, tmp_path):
    path = str(tmp_path / "marked.pdf"); _a_drawing_marked_up_elsewhere(path)
    window.show(); print("A", window.document.modified)
    window.open_path(path); print("B", window.document.modified, window.undo_stack.count())
    window.rebuild_scenes(); print("C", window.document.modified)
    window.select_tool("select"); print("D", window.document.modified)
    window.toggle_calc_mode(False); print("E", window.document.modified)
    QApplication.instance().processEvents(); print("F", window.document.modified)
    page = window.document.pages[0]
    print([ (i.TYPE, i.still_theirs) for i in page.frame.ordered_markups()])
