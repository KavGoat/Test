from PySide6.QtWidgets import QApplication
from calcforge.core.document import Document


def _drop_on_first_tab(source, target):
    bar = target.document_tabs
    source.tear_off_document(max(0, source.document_tabs.currentIndex()),
                             bar.mapToGlobal(bar.tabRect(0).center()))
    QApplication.processEvents()


def test_dragging_a_split_panes_tab_onto_the_other_pane_makes_no_extra_tabs(window):
    first = window.document
    window.open_in_new_tab()
    host = window.split_document(0)
    other = host.panes[1]
    other.confirm_discard = lambda: True
    QApplication.processEvents()
    assert other.document is first
    _drop_on_first_tab(other, window)
    # The document was already a tab here: no copy, no blank tab left behind,
    # and the emptied pane takes the split with it.
    assert window.document_tabs.count() == 2
    assert window.document is first
    assert window._split_host is None and window.isWindow()
    assert not window.act_split_view.isChecked()


def test_dragging_a_split_panes_other_document_across_moves_it(window):
    host = window.split_document()
    other = host.panes[1]
    other.confirm_discard = lambda: True
    QApplication.processEvents()
    other.new_document(confirm=False)
    moved = other.document
    _drop_on_first_tab(other, window)
    assert window._split_host is None
    held = [state["document"] for state in window._open_documents]
    assert moved in held and len(held) == 2
