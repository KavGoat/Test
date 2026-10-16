"""Revu's Flatten Markups and Set Scale dialogs (the user, 2026-10-15:
"Things like flatten recovery is in settings not in flatten, page scale pop
up doesn't look like [Bluebeam]")."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF

from calcforge.core.document import PageScale
from calcforge.items.measure import LENGTH, MeasureItem
from calcforge.items.shapes import RectItem
from calcforge.ui import dialogs, preferences


@pytest.fixture
def prefs_kept():
    """Flatten remembers Allow Markup Recovery; put it back afterwards."""
    prefs = preferences.current()
    before = prefs.recover_flattened
    yield prefs
    prefs.recover_flattened = before
    preferences.save(prefs)


@pytest.fixture
def no_saved_presets():
    dialogs.store_scale_presets([])
    yield
    dialogs.store_scale_presets([])


def _put(window, kind="rect", page=0, at=(100, 100)):
    frame = window.document.pages[page].frame
    item = RectItem(kind, QRectF(0, 0, 80, 40))
    frame.add_markup(item, QPointF(*at))
    return item


def _length(window, page=0, length_pt=100.0, down=False):
    frame = window.document.pages[page].frame
    end = QPointF(0, length_pt) if down else QPointF(length_pt, 0)
    item = MeasureItem(LENGTH, [QPointF(0, 0), end])
    frame.add_markup(item, QPointF(100, 300))
    item.refresh(page=window.document.pages[page])
    return item


def _three_pages(window):
    window.add_page()
    window.add_page()
    window.go_to_page(0)


# ---------------------------------------------------------------------------
# Flatten Markups
# ---------------------------------------------------------------------------

def test_flatten_markups_is_laid_out_as_revus(window):
    _put(window, "rect")
    _put(window, "cloud")
    dialog = window.flatten_dialog()
    try:
        assert dialog.windowTitle() == "Flatten Markups"
        assert dialog.types.headerItem().text(0) == "Type"
        assert dialog.chosen_types() == {"Rectangle", "Cloud"}
        assert [b.text() for b in (dialog.all_markups, dialog.exclude_filtered,
                                   dialog.selected_markups)] == [
            "All Markups", "Exclude Filtered Markups", "Currently Selected Markups"]
        assert dialog.allow_recovery.text() == "Allow Markup Recovery (Unflatten)"
        assert dialog.flatten_button.text() == "Flatten"
        # nothing selected: Currently Selected is not available
        assert not dialog.selected_markups.isEnabled()
        assert dialog.all_markups.isChecked()
        assert [dialog.pages.combo.itemText(i) for i in range(dialog.pages.combo.count())] \
            == ["All Pages", "Current (1)", "Custom"]
    finally:
        dialog.deleteLater()


def test_allow_markup_recovery_off_cannot_be_unflattened(window, prefs_kept):
    rect = _put(window)
    dialog = window.flatten_dialog()
    assert dialog.allow_recovery.isChecked() == prefs_kept.recover_flattened
    dialog.allow_recovery.setChecked(False)
    assert window.finish_flatten(dialog) == 1
    dialog.deleteLater()
    assert rect.scene() is None                  # baked into a recording
    window.recover_flattened()
    assert "No recoverable" in window.status_hint.text()
    # and the choice is remembered for next time
    assert preferences.current().recover_flattened is False
    again = window.flatten_dialog()
    assert not again.allow_recovery.isChecked()
    again.deleteLater()


def test_allow_markup_recovery_on_can_be_unflattened(window, prefs_kept):
    prefs_kept.recover_flattened = False
    rect = _put(window)
    dialog = window.flatten_dialog()
    dialog.allow_recovery.setChecked(True)
    window.finish_flatten(dialog)
    dialog.deleteLater()
    assert rect.flattened and rect.flatten_recoverable
    window.act_recover_flattened.trigger()
    assert not rect.flattened
    assert preferences.current().recover_flattened is True


def test_currently_selected_markups_flattens_only_the_selection(window, prefs_kept):
    picked = _put(window, "rect", at=(100, 100))
    other = _put(window, "rect", at=(300, 100))
    picked.setSelected(True)
    dialog = window.flatten_dialog()
    try:
        # something was selected: Revu makes it the default
        assert dialog.selected_markups.isEnabled() and dialog.selected_markups.isChecked()
        window.finish_flatten(dialog)
    finally:
        dialog.deleteLater()
    assert picked.flattened
    assert not other.flattened


def test_the_type_list_leaves_unticked_types_alone(window, prefs_kept):
    rect = _put(window, "rect")
    cloud = _put(window, "cloud", at=(300, 100))
    dialog = window.flatten_dialog()
    dialog.set_type_checked("Cloud", False)
    window.finish_flatten(dialog)
    dialog.deleteLater()
    assert rect.flattened
    assert not cloud.flattened


def test_exclude_filtered_markups_leaves_what_the_list_hides(window, prefs_kept):
    rect = _put(window, "rect")
    cloud = _put(window, "cloud", at=(300, 100))
    cloud.subject = "keep me"
    window.markups_panel.filter.setText("keep me")      # only the cloud shows
    dialog = window.flatten_dialog()
    dialog.exclude_filtered.setChecked(True)
    window.finish_flatten(dialog)
    dialog.deleteLater()
    window.markups_panel.filter.clear()
    assert cloud.flattened
    assert not rect.flattened


def test_the_pages_range_is_honoured(window, prefs_kept):
    _three_pages(window)
    on = [_put(window, page=i) for i in range(3)]
    dialog = window.flatten_dialog()
    assert dialog.pages.which() == dialog.pages.ALL           # Revu's default here
    dialog.pages.range.setText("1, 3")
    dialog.pages.range.textEdited.emit("1, 3")                # as typed: Custom
    assert dialog.pages.which() == dialog.pages.CUSTOM
    assert dialog.page_indexes() == [0, 2]
    window.finish_flatten(dialog)
    dialog.deleteLater()
    assert [item.flattened for item in on] == [True, False, True]


def test_right_click_flatten_is_at_once_and_recoverable(window, prefs_kept):
    prefs_kept.recover_flattened = False         # what the dialog last had
    window.interactive_prompts = True            # and still no question
    rect = _put(window)
    rect.setSelected(True)
    window.act_flatten.trigger()
    assert rect.flattened and rect.flatten_recoverable


# ---------------------------------------------------------------------------
# Set Scale
# ---------------------------------------------------------------------------

def test_set_scale_is_laid_out_as_revus(window, no_saved_presets):
    _three_pages(window)
    window.go_to_page(1)
    dialog = window.scale_dialog()
    try:
        assert dialog.windowTitle() == "Set Scale"
        combo = dialog.pages.combo
        assert [combo.itemText(i) for i in range(combo.count())] == [
            "All Pages", "Current (2)", "Custom"]
        assert combo.currentText() == "Current (2)"            # the default
        assert dialog.x_row.preset_choice.text() == "Preset"
        assert dialog.x_row.custom_choice.text() == "Custom"
        assert dialog.separate_y.text() == "Separate Y Scale"
        assert dialog.add_preset.text() == "+ Add Preset"
        assert dialog.apply_button.text() == "Apply Scale"
        names = [dialog.x_row.preset.itemText(i) for i in range(dialog.x_row.preset.count())]
        for wanted in ("1:100", "1/4\" = 1'-0\"", "1\" = 20'"):
            assert wanted in names
        assert not dialog.y_row.stack.isVisibleTo(dialog)
        dialog.separate_y.setChecked(True)
        assert dialog.y_row.stack.isVisibleTo(dialog)
    finally:
        dialog.deleteLater()


def test_selected_appears_only_with_pages_picked_in_thumbnails(window):
    _three_pages(window)
    listed = window.pages_panel.list
    listed.item(0).setSelected(True)
    listed.item(2).setSelected(True)
    dialog = window.scale_dialog()
    try:
        assert dialog.pages.combo.findText("Selected") >= 0
        dialog.pages.choose(dialog.pages.SELECTED)
        assert dialog.page_indexes() == [0, 2]
        assert dialog.pages.range.text() == "1, 3"
    finally:
        dialog.deleteLater()


def test_preset_1_100_on_the_current_page_only(window, no_saved_presets):
    _three_pages(window)
    window.go_to_page(1)
    dialog = window.scale_dialog()
    dialog.x_row.preset.setCurrentText("1:100")
    assert window.finish_scale(dialog)
    dialog.deleteLater()
    scales = [page.scale for page in window.document.pages]
    assert scales[1].label == "1:100" and scales[1].ratio() == pytest.approx(100)
    assert not scales[0].is_calibrated() and not scales[2].is_calibrated()
    assert window.status_scale.text() == "Scale 1:100"


def test_all_pages_sets_every_page(window, no_saved_presets):
    _three_pages(window)
    dialog = window.scale_dialog()
    dialog.x_row.preset.setCurrentText("1:50")
    dialog.pages.choose(dialog.pages.ALL)
    window.finish_scale(dialog)
    dialog.deleteLater()
    assert [page.scale.label for page in window.document.pages] == ["1:50"] * 3
    # and they are separate copies, not one shared scale
    assert window.document.pages[0].scale is not window.document.pages[1].scale


def test_custom_1_mm_50_mm_and_measurements_follow(window, no_saved_presets):
    length = _length(window, length_pt=100.0)
    dialog = window.scale_dialog()
    dialog.x_row.set_custom(True)
    dialog.x_row.page_length.setText("1")
    dialog.x_row.page_unit.setCurrentText("mm")
    dialog.x_row.real_length.setText("50")
    dialog.x_row.real_unit.setCurrentText("mm")
    dialog.set_precision("0.1")
    assert window.finish_scale(dialog)
    dialog.deleteLater()
    scale = window.current_page().scale
    assert scale.label == "1 mm = 50 mm"
    assert scale.ratio() == pytest.approx(50)
    # 100 pt is 35.28 mm of paper: 1763.9 mm at 1:50
    assert length.value.to("mm").magnitude == pytest.approx(100 * 25.4 / 72 * 50, rel=1e-6)
    assert length.measured_text == "1763.9 mm"


def test_separate_y_scale_measures_down_the_page_at_its_own_scale(window, no_saved_presets):
    across = _length(window, length_pt=72.0)
    down = _length(window, length_pt=72.0, down=True)
    dialog = window.scale_dialog()
    dialog.x_row.preset.setCurrentText("1:100")
    dialog.separate_y.setChecked(True)
    dialog.y_row.preset.setCurrentText("1:50")
    window.finish_scale(dialog)
    dialog.deleteLater()
    scale = window.current_page().scale
    assert scale.separate_y() and scale.label == "X 1:100, Y 1:50"
    assert across.value.to("mm").magnitude == pytest.approx(2540)
    assert down.value.to("mm").magnitude == pytest.approx(1270)


def test_calibrate_comes_back_with_the_measured_length(window, monkeypatch, no_saved_presets):
    _three_pages(window)
    first = window.scale_dialog()
    first.pages.choose(first.pages.ALL)
    first.x_row.set_custom(True)
    first.x_row.calibrate.click()                 # closes it with PICK
    assert first.result() == dialogs.ScaleDialog.PICK
    window._scale_dialog_state = first.state()
    first.deleteLater()
    again = window.scale_dialog(measured_pt=144.0)  # two inches of paper
    try:
        assert again.pages.which() == again.pages.ALL   # as it was left
        assert again.x_row.is_custom()
        assert float(again.x_row.page_length.text()) == pytest.approx(50.8)
        assert again.x_row.real_length.text() == ""
        again.x_row.real_length.setText("10")
        again.x_row.real_unit.setCurrentText("m")
        window.finish_scale(again)
    finally:
        again.deleteLater()
    for page in window.document.pages:
        assert page.scale.length(144.0).to("m").magnitude == pytest.approx(10)


def test_add_preset_saves_one_that_is_at_the_top_next_time(window, no_saved_presets):
    dialog = window.scale_dialog()
    dialog.x_row.set_custom(True)
    dialog.x_row.page_length.setText("1")
    dialog.x_row.page_unit.setCurrentText("mm")
    dialog.x_row.real_length.setText("75")
    dialog.x_row.real_unit.setCurrentText("mm")
    assert dialog.add_preset.isEnabled()
    entry = dialog.save_preset()
    dialog.deleteLater()
    assert entry["name"] == "1 mm = 75 mm"
    again = window.scale_dialog()
    try:
        combo = again.x_row.preset
        assert combo.itemText(0) == "1 mm = 75 mm"
        assert combo.itemData(0, dialogs._DELETE_ROLE)        # it has a delete button
        assert not combo.itemData(combo.findText("1:100"), dialogs._DELETE_ROLE)
        combo.setCurrentIndex(0)
        again.x_row.set_custom(False)
        window.finish_scale(again)
        assert window.current_page().scale.ratio() == pytest.approx(75)
        # ✕ deletes it; Revu's own presets stay
        again.delete_preset("1 mm = 75 mm")
        assert combo.findText("1 mm = 75 mm") < 0
        assert dialogs.saved_scale_presets() == []
    finally:
        again.deleteLater()


def test_precision_changes_the_measurement_text(window, no_saved_presets):
    length = _length(window, length_pt=100.0)
    texts = {}
    for precision in ("1", "0.01", "0.001"):
        dialog = window.scale_dialog()
        dialog.x_row.preset.setCurrentText("1:100")
        assert dialog.set_precision(precision)
        window.finish_scale(dialog)
        dialog.deleteLater()
        texts[precision] = length.measured_text
    assert texts == {"1": "4 m", "0.01": "3.53 m", "0.001": "3.528 m"}


def test_architectural_scales_write_feet_and_inches_to_a_fraction(window, no_saved_presets):
    length = _length(window, length_pt=100.0)          # 1.389 in of paper
    dialog = window.scale_dialog()
    dialog.x_row.preset.setCurrentText("1/4\" = 1'-0\"")
    dialog.scale_changed()
    precisions = [dialog.precision.itemText(i) for i in range(dialog.precision.count())]
    assert precisions == ["1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]
    assert dialog.precision.currentText() == "1/16"
    window.finish_scale(dialog)
    dialog.deleteLater()
    # 100/18 ft = 5'-6 2/3", to the nearest 1/16 is 5'-6 11/16"
    assert length.measured_text == "5'-6 11/16\""
    dialog = window.scale_dialog()
    dialog.set_precision("1/2")
    window.finish_scale(dialog)
    dialog.deleteLater()
    assert length.measured_text == "5'-6 1/2\""


def test_old_files_without_fractions_still_open():
    old = {"label": "1:100", "magnitude": 35.27777, "units": "mm", "precision": 2,
           "display_unit": "m", "area_unit": "m^2", "calibrated": True}
    scale = PageScale.from_dict(old)
    assert scale.fraction == 0 and scale.ratio() == pytest.approx(100, rel=1e-4)
    assert PageScale.from_dict(scale.to_dict()).to_dict() == scale.to_dict()


def test_every_way_in_opens_set_scale(window, monkeypatch):
    opened = []
    monkeypatch.setattr(dialogs.ScaleDialog, "exec",
                        lambda self: opened.append(self.windowTitle()) or 0)
    window.act_scale.trigger()                    # Tools ▸ Measure ▸ Set Scale…
    window.status_scale.click()                   # the status bar's Scale button
    window.calibrate_scale(120.0)                 # the Calibrate tool's two points
    assert opened == ["Set Scale"] * 3
