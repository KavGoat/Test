"""Device-independent fonts.

Every page coordinate in CalcForge is a PostScript point, so a "10 pt" font has
to occupy exactly 10 scene units — on screen, in an exported image, and on a
600 dpi printer alike.  ``QFont.setPointSizeF`` cannot do that: Qt turns points
into device pixels using the paint device's own DPI, so the same font comes out
four times too large on a 300 dpi page.  Sizing fonts in *pixels* pins them to
scene units instead, and the painter's world transform then scales them exactly
like every other piece of geometry.
"""
from __future__ import annotations

from PySide6.QtGui import QFont

# Fallback chains, tried in order, so the app looks right on a bare system.
SANS = ["Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Helvetica Neue", "sans-serif"]
SERIF = ["Cambria Math", "STIX Two Math", "Georgia", "Noto Serif", "DejaVu Serif", "serif"]
MONO = ["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "monospace"]

MIN_PIXELS = 1


def page_font(family: str, size: float, bold: bool = False, italic: bool = False,
              underline: bool = False, fallbacks: list[str] | None = None) -> QFont:
    """A font whose height is *size* scene units (points) on any paint device."""
    font = QFont()
    families = [family] if family else []
    families += [name for name in (fallbacks or SANS) if name != family]
    # setFamilies() must be the last family call: in Qt 6 setFamily() replaces
    # the whole list, which would throw the fallback chain away.
    font.setFamilies(families)
    font.setPixelSize(max(int(round(size)), MIN_PIXELS))
    font.setBold(bold)
    font.setItalic(italic)
    font.setUnderline(underline)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


def scale_font(font: QFont, factor: float) -> QFont:
    """A copy of *font* resized by *factor*, keeping pixel sizing."""
    copy = QFont(font)
    copy.setPixelSize(max(int(round(font.pixelSize() * factor)), MIN_PIXELS))
    return copy


def set_size(font: QFont, size: float) -> QFont:
    copy = QFont(font)
    copy.setPixelSize(max(int(round(size)), MIN_PIXELS))
    return copy


# ---------------------------------------------------------------------------
# Sub- and superscripts in plain text
# ---------------------------------------------------------------------------
#
# A text box holds rich text and can set a real subscript. A table cell holds
# plain text, because that is what a formula reads and what a name is written
# in. So the same "A_g" and "m^2" an engineer types are *drawn* with the run
# after the marker lowered or lifted, while what is stored stays "A_g".

# What ends a run: the moment the word moves on, so does the level.
_ENDS_A_RUN = set(" \t,;:()[]{}+-*/=<>_^'\"")


def script_runs(text: str) -> list:
    """Split ``A_g = m^2`` into ``[("A",""), ("g","sub"), (" = m",""), ("2","super")]``.

    A marker with nothing after it stays as itself: somebody half-way through
    typing ``f_`` should see the underscore they just pressed.
    """
    if not text:
        return []
    runs: list = []
    plain: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character in "_^":
            run = index + 1
            while run < len(text) and text[run] not in _ENDS_A_RUN:
                run += 1
            if run > index + 1:
                if plain:
                    runs.append(("".join(plain), ""))
                    plain = []
                runs.append((text[index + 1:run],
                             "sub" if character == "_" else "super"))
                index = run
                continue
        plain.append(character)
        index += 1
    if plain:
        runs.append(("".join(plain), ""))
    return runs


def has_scripts(text: str) -> bool:
    return any(level for _run, level in script_runs(text))
