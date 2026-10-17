"""Revu's dimming of filtered-out markups on the page.

Revu's manual (Markups list, Filtering): "Markups on the PDF that do not
match the selected filters are dimmed ... The exact amount that filtered
markups are dimmed is determined by the Filtered Annotation Dim percentage
setting in the Markups List Preferences", and of the search box: "any
markups that are filtered out will be dimmed on the PDF".

The dimming is the canvas's alone. A markup keeps its own look in the file,
in an export and on paper: ``PageFrame.render_page`` and the snapshot's
drawing put every markup back to full strength while they draw, and Print's
Dim Filtered Markups tones down the filtered ones there itself.

How each kind of markup is dimmed:

* one CalcForge draws — live, or from the page's squares
  (ui/markuplayer.py, which draws a markup at its opacity) — through its
  opacity;
* an imported annotation nobody has changed on a page of a hundred or so,
  drawn by its own file in a picture of its own (``_TheirLook``), the same;
* one on a crowded page, which the page's render draws with the page
  (``PageFrame.file_draws``): while it is dimmed the page leaves it out, as
  it leaves out one taken over, and it is drawn alone, by its own file, from
  the annotation squares the render processes make — so it can be dimmed;
* an annotation that came in as several strokes (an ink line nobody has
  changed) is drawn whole by the page's render, which alone has its curves;
  the strokes are a straight-line reading of it, so it is left at full
  strength rather than shown as something it is not.
"""
from __future__ import annotations


def opacity() -> float:
    """How strong a filtered-out markup is drawn: the Markups List
    preference Filtered Annotation Dim Percent, as an opacity."""
    from . import preferences
    percent = getattr(preferences.current(), "filtered_dim_percent", 60)
    try:
        percent = float(percent)
    except (TypeError, ValueError):
        percent = 60.0
    return max(0.05, min(1.0, 1.0 - percent / 100.0))


def is_dimmed(item) -> bool:
    return bool(getattr(item, "filter_dimmed", False))


def apply(document, filtered) -> int:
    """Dim the markups in *filtered* on the canvas and show every other one
    at full strength; how many changed."""
    filtered = set(filtered)
    level = opacity()
    changed = 0
    for page in document.pages:
        frame = page.frame
        if frame is None:
            continue
        moved = []
        crowd = False
        for item in frame.markups():
            want = item in filtered
            if getattr(item, "split_theirs", False):
                want = False                 # drawn whole by the page: see above
            target = level if want else 1.0
            if is_dimmed(item) == want and abs(item.opacity() - target) < 1e-6:
                continue
            item.filter_dimmed = want
            item.setOpacity(target)
            moved.append(item)
            if getattr(item, "still_theirs", False) and getattr(frame, "file_draws", False):
                crowd = True
                if hasattr(item, "sync_their_look"):
                    item.sync_their_look()
        if not moved:
            continue
        changed += len(moved)
        layer = getattr(frame, "layer", None)
        if layer is not None:
            for item in moved:
                if item in layer.members:
                    # drawn from the squares: those parts are drawn again,
                    # together, once (MarkupLayer.dirty)
                    box = layer._box(item)
                    known = layer.boxes.get(item)
                    layer.dirty(box if known is None else box.united(known))
        if crowd:
            # the page leaves out (or takes back) the ones it was drawing
            frame.update()
    return changed


class undimmed:
    """While a page is drawn for paper, a file or a picture, every markup at
    full strength — but those in *dimmed* (Print's Dim Filtered Markups),
    at the Filtered Annotation Dim level."""

    def __init__(self, frame, dimmed=()):
        self.changes = []
        dimmed = set(dimmed or ())
        level = opacity() if dimmed else 1.0
        for item in frame.markups():
            target = level if item in dimmed else (1.0 if is_dimmed(item) else None)
            if target is not None and abs(item.opacity() - target) > 1e-6:
                self.changes.append((item, item.opacity(), target))

    def __enter__(self):
        for item, _was, target in self.changes:
            item.setOpacity(target)
        return self

    def __exit__(self, *_):
        for item, was, _target in self.changes:
            item.setOpacity(was)
        return False


__all__ = ["opacity", "apply", "undimmed", "is_dimmed"]
