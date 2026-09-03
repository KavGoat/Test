"""Spelling, checked against New Zealand English.

A calculation sheet is read by people who did not write it, and a misspelling
in a note is the kind of thing nobody notices until it is printed and bound.
So words typed into a text box, a callout or a note are checked, and the ones
the dictionary does not know are underlined — quietly, the way every other
editor does it, with no dialog and nothing to dismiss.

New Zealand English follows British spelling, so "colour" and "analyse" are
right and "color" and "analyze" are wrong. The list is British and Australian
English together, plus the structural-engineering words and the Māori and New
Zealand place names an engineer here writes every week. Anything else can be
added to the personal list, which is remembered between sessions.
"""
from __future__ import annotations

import gzip
import os
import re
from pathlib import Path
from typing import Iterable, Optional

# A word for spelling purposes: letters, with apostrophes and hyphens allowed
# inside. Numbers, units and variable names are not words in this sense and
# are never checked — "5kN" and "f_c" are not misspellings.
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")

# Where a system dictionary might be, for anyone who has one installed.
SYSTEM_LISTS = (
    "/usr/share/dict/en_NZ",
    "/usr/share/dict/british-english",
    "/usr/share/dict/words",
)

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "en_nz.txt.gz"


def _read(path: Path) -> set[str]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="ignore") as handle:
        return {line.strip() for line in handle if line.strip()}


class SpellChecker:
    """Knows which words are words. Nothing more.

    Loading is put off until the first question is asked: a document with no
    prose in it never pays for the dictionary at all.
    """

    def __init__(self, extra: Optional[Iterable[str]] = None,
                 path: Optional[str] = None):
        self._words: Optional[set[str]] = None
        self._path = path
        self.personal: set[str] = {word.lower() for word in (extra or ())}

    # -- the dictionary ----------------------------------------------------
    def words(self) -> set[str]:
        if self._words is None:
            self._words = self._load()
        return self._words

    def _load(self) -> set[str]:
        for candidate in ([self._path] if self._path else []) + list(SYSTEM_LISTS):
            if candidate and os.path.exists(candidate):
                try:
                    return {word.lower() for word in _read(Path(candidate))}
                except OSError:
                    continue
        if BUNDLED.exists():
            try:
                return {word.lower() for word in _read(BUNDLED)}
            except OSError:
                pass
        return set()                      # no dictionary: nothing is misspelt

    def ready(self) -> bool:
        return bool(self.words())

    # -- checking ----------------------------------------------------------
    def knows(self, word: str) -> bool:
        """Whether *word* is spelt correctly.

        Anything with a digit in it, anything one letter long, and anything in
        capitals (an abbreviation, a stamp, a bolt grade) is left alone: those
        are not the kind of thing a dictionary has an opinion about.
        """
        if not word or any(character.isdigit() for character in word):
            return True
        if "_" in word:
            return True                   # a variable name, not a word
        stripped = word.strip("'’-")
        if len(stripped) < 2:
            return True
        if stripped.isupper():
            return True
        lowered = stripped.lower().replace("’", "'")
        if lowered in self.personal:
            return True
        vocabulary = self.words()
        if not vocabulary:
            return True
        if lowered in vocabulary:
            return True
        # "Beam's" and "beams'" are the possessive of a word that is spelt
        # correctly, and hyphenated compounds are right when both halves are.
        base = lowered.rstrip("'").removesuffix("'s")
        if base != lowered and base in vocabulary:
            return True
        if "-" in lowered:
            parts = [part for part in lowered.split("-") if part]
            return bool(parts) and all(part in vocabulary for part in parts)
        return False

    def mistakes(self, text: str) -> list[tuple[int, int, str]]:
        """Every misspelt word in *text*, as (start, length, word)."""
        found = []
        for match in WORD.finditer(text or ""):
            word = match.group(0)
            if not self.knows(word):
                found.append((match.start(), len(word), word))
        return found

    def learn(self, word: str) -> None:
        """Add a word to the personal list, so it stops being flagged."""
        cleaned = (word or "").strip().strip("'’-").lower()
        if cleaned:
            self.personal.add(cleaned)


_shared: Optional[SpellChecker] = None


def shared() -> SpellChecker:
    """The one checker the whole application uses."""
    global _shared
    if _shared is None:
        _shared = SpellChecker()
    return _shared


def forget() -> None:
    """Drop the shared checker — used by the tests."""
    global _shared
    _shared = None
