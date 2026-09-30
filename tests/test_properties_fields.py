"""Phase 6: header/footer with SMath's fields, and one File > Properties
(decisions 27 and 28)."""
from __future__ import annotations

import datetime

import pymupdf
import pytest

from markforge.core.document import Document
from markforge.ui import dialogs


@pytest.fixture
def win(window):
    window.show()
    return window


# -- SMath's fields, in MarkForge's header and footer ----------------------------------------

def test_fields():
    """Ported from tests/calc/test_page_model.py (SMath's header fields)."""
    now = datetime.datetime(2024, 12, 10, 9, 5)
    document = Document()
    document.pages = document.pages * 8
    document.keywords, document.title, document.author = "JOB-7", "Issue 1", "ME"
    assert document.expand_fields("{keywords}", 2, now) == "JOB-7"
    assert document.expand_fields("{page}", 2, now) == "3"
    assert document.expand_fields("{pages}", 2, now) == "8"
    assert document.expand_fields("{date:DD.MM.YYYY}", 0, now) == "10.12.2024"
    assert document.expand_fields("{title} by {author}", 0, now) == "Issue 1 by ME"


def test_field_formats_as_smaths_insert_field_dialog():
    """Ported: observed in SMath's Insert Field dialog (Number of pages, one
    page): Format -> Example."""
    document = Document()
    assert [document.expand_fields("{pages:" + f + "}", 0) for f in ("-1", "22", "-5", "0001")] \
        == ["0", "23", "-4", "0002"]
    now = datetime.datetime(2024, 12, 10, 21, 5, 7)
    assert document.expand_fields("{time:HH:mm:ss}", 0, now) == "21:05:07"
    assert document.expand_fields("{time:hh:mm tt}", 0, now) == "09:05 PM"
    assert document.expand_fields("{date:DD MMMM YYYY}", 0, now) == "10 December 2024"
    assert document.expand_fields("{nothing} {page", 0, now) == "{nothing} {page", \
        "anything that is not a field is left as written"


def test_the_merged_properties_are_fields_too():
    document = Document()
    document.company, document.description = "ACME Engineering", "Car park beams"
    document.revision, document.doc_id, document.path = 3, "abc-123", "/jobs/S-101 calcs.pdf"
    assert document.expand_fields("{company} · {description} · rev {revision} · {id}", 0) \
        == "ACME Engineering · Car park beams · rev 3 · abc-123"
    assert document.expand_fields("{filename}", 0) == "S-101 calcs.pdf"


def test_the_header_prints_its_fields(win, tmp_path):
    from tests.test_calc_saving import save_to
    document = win.document
    document.title, document.company = "Beam checks", "ACME"
    settings = document.settings
    settings.show_header = True
    settings.header_left = "{company}"
    settings.header_center = "{title} rev {revision}"
    settings.header_right = "Page {page:0000} of {pages}"
    win.rebuild_scenes()
    path = str(tmp_path / "header.pdf")
    save_to(win, path)
    with pymupdf.open(path) as saved:
        words = saved[0].get_text()
    assert "ACME" in words and "Beam checks rev 1" in words and "Page 0001 of 1" in words


# -- each save is a revision, as in SMath ---------------------------------------------------

def test_identity_is_kept_and_each_save_is_a_revision(win, tmp_path):
    """Ported from tests/calc/test_page_model.py: a document gets an id once,
    and each save is a new revision."""
    from tests.test_calc_saving import reopen, save_to
    assert not win.document.doc_id and win.document.revision == 0
    path = str(tmp_path / "a.pdf")
    save_to(win, path)
    first = win.document.doc_id
    assert first and win.document.revision == 1
    reopen(win, path)
    assert win.document.doc_id == first and win.document.revision == 1
    save_to(win, path)
    reopen(win, path)
    assert win.document.doc_id == first and win.document.revision == 2
    win.write_autosave()
    assert win.document.revision == 2, "a recovery copy is not a revision"


# -- the PDF's own properties -----------------------------------------------------------------

def test_title_author_subject_and_keywords_go_into_the_pdf(win, tmp_path):
    from pypdf import PdfReader
    from tests.test_calc_saving import save_to
    document = win.document
    document.title, document.author = "Beam checks", "K. D."
    document.subject, document.keywords = "Level 2 transfer beams", "JOB-7, S-101"
    document.company = "ACME"
    path = str(tmp_path / "props.pdf")
    save_to(win, path)
    info = PdfReader(path).metadata
    assert info.title == "Beam checks" and info.author == "K. D."
    assert info.subject == "Level 2 transfer beams" and info["/Keywords"] == "JOB-7, S-101"
    assert "ACME" not in str(dict(info)), "the rest stay in CalcForge's record"


def test_an_exported_pdf_has_them_too(win, tmp_path):
    from markforge.io import export as export_io
    win.document.title, win.document.keywords = "Export", "K1"
    path = str(tmp_path / "exported.pdf")
    export_io.export_pdf(win.document, path, resolution=150)
    with pymupdf.open(path) as saved:
        meta = saved.metadata
    assert meta["title"] == "Export" and meta["keywords"] == "K1"


# -- one File > Properties --------------------------------------------------------------------

def test_one_properties_dialog_with_markforges_and_smaths_fields(win):
    dialog = dialogs.DocumentPropertiesDialog(win.document, win)
    dialog.title.setText("T")
    dialog.company.setText("ACME")
    dialog.keywords.setText("K")
    dialog.description.setPlainText("Two lines\nof description")
    dialog.apply()
    document = win.document
    assert (document.title, document.company, document.keywords) == ("T", "ACME", "K")
    assert document.description == "Two lines\nof description"


def test_insert_field_goes_into_the_slot_typed_in_last(win):
    dialog = dialogs.DocumentPropertiesDialog(win.document, win)
    menu = dialog.findChild(dialogs.QPushButton, "insertField").menu()
    labels = [action.text() for action in menu.actions()]
    assert "Date, DD.MM.YYYY" in labels and "Company" in labels and "Revision" in labels
    footer = dialog.footer_fields[2]
    footer.setText("Rev ")
    footer.setFocus()
    dialog._slot = footer                 # (offscreen: focus events are not delivered)
    next(a for a in menu.actions() if a.text() == "Revision").trigger()
    assert footer.text() == "Rev {revision}"
