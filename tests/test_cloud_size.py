"""A cloud's Size, as Bluebeam's (2026-10-14): no unit — it is the PDF's
cloudy-border intensity, so the scallops are as big as any reader draws them
(4.75 × intensity + half the line width, Apache PDFBox's CloudyBorder) —
and Invert turns them inward."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF

from calcforge.items.base import cloud_radius_for
from calcforge.items.shapes import PolyItem, RectItem
from tests.test_format import _a_drawing_marked_up_elsewhere, _annotations


def test_size_goes_out_as_the_clouds_intensity(window, tmp_path):
    from calcforge.io import export as export_io
    frame = window.document.pages[0].frame
    boxed = RectItem("cloud", QRectF(0, 0, 150, 90))
    boxed.cloud_size = 3.25
    frame.add_markup(boxed, QPointF(60, 60))
    poly = PolyItem("cloud", [QPointF(0, 0), QPointF(120, 0), QPointF(60, 80)])
    poly.cloud_size = 1.0
    frame.add_markup(poly, QPointF(300, 300))
    path = str(tmp_path / "clouds.pdf")
    export_io.export_pdf(window.document, path)
    sizes = sorted(float(mark["/BE"]["/I"]) for mark in _annotations(path) if "/BE" in mark)
    assert sizes == [1.0, 3.25]


def test_a_clouds_intensity_comes_in_as_its_size(window, tmp_path):
    source = str(tmp_path / "marked.pdf")
    _a_drawing_marked_up_elsewhere(source)          # a cloud with /BE /I 2
    window.open_path(source)
    window.rebuild_scenes()
    (cloud,) = [i for i in window.document.pages[0].frame.ordered_markups()
                if getattr(i, "kind", "") == "cloud"]
    assert cloud.cloud_size == pytest.approx(2.0)
    assert cloud.cloud_radius == pytest.approx(cloud_radius_for(2.0, cloud.style.width))


def test_a_cloud_saved_before_size_looks_the_same(window):
    """Its radius in points becomes the Size that draws it the same."""
    old = {"type": "rect", "kind": "cloud", "rect": [0, 0, 100, 60], "cloud_radius": 9.0,
           "style": {"stroke": "#ff0000", "width": 1.5}}
    cloud = RectItem()
    cloud.deserialize(old)
    assert cloud.cloud_radius == pytest.approx(9.0)
    again = RectItem()
    again.deserialize(cloud.serialize())
    assert again.cloud_size == pytest.approx(cloud.cloud_size)
    assert "cloud_radius" not in cloud.serialize()


def test_invert_turns_the_scallops_inward_and_is_kept():
    cloud = RectItem("cloud", QRectF(0, 0, 120, 80))
    out = cloud.hatch_region().boundingRect()
    cloud.cloud_invert = True
    inward = cloud.hatch_region().boundingRect()
    assert inward.width() < out.width() and inward.height() < out.height()
    again = RectItem()
    again.deserialize(cloud.serialize())
    assert again.cloud_invert
