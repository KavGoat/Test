"""Turn hunspell dictionaries into the word list CalcForge ships.

Hunspell keeps a stem and a set of flags, and works the endings out at look-up
time. Carrying a hunspell engine around just to spell-check a text box is more
than the job needs, so the endings are worked out once, here, and the result
is a plain sorted list of words, gzipped.

New Zealand English is not one of the dictionaries published in the LibreOffice
pack, and it does not need to be: it follows British spelling, with a handful of
Australian and Māori words alongside. So the list is British plus Australian
plus the words in ``extra_words.txt``.

Run it as::

    python tools/build_dictionary.py path/to/dictpack calcforge/data/en_nz.txt.gz

It is a build tool, not part of the application: the application only ever
reads the list it produces.
"""
from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

MAX_STEM_FLAGS = 64


def read_affixes(path: Path) -> dict:
    """Every SFX/PFX rule in an .aff file, keyed by its flag."""
    rules: dict[str, list[tuple[str, str, str, str]]] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] not in ("SFX", "PFX"):
            continue
        kind, flag = parts[0], parts[1]
        if parts[2] in ("Y", "N") and len(parts) == 4:
            continue                       # the header line, not a rule
        strip, add = parts[2], parts[3]
        condition = parts[4] if len(parts) > 4 else "."
        rules.setdefault(flag, []).append((kind, strip, add, condition))
    return rules


def apply(stem: str, rule: tuple[str, str, str, str]) -> str | None:
    kind, strip, add, condition = rule
    add = "" if add == "0" else add.split("/")[0]
    strip = "" if strip == "0" else strip
    try:
        pattern = re.compile(condition + "$" if kind == "SFX" else "^" + condition)
    except re.error:
        return None
    if kind == "SFX":
        if not pattern.search(stem) or (strip and not stem.endswith(strip)):
            return None
        return stem[:len(stem) - len(strip)] + add if strip else stem + add
    if not pattern.match(stem) or (strip and not stem.startswith(strip)):
        return None
    return add + stem[len(strip):] if strip else add + stem


def expand(dic: Path, aff: Path) -> set[str]:
    rules = read_affixes(aff)
    words: set[str] = set()
    lines = dic.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in lines[1:]:                 # the first line is a count
        line = line.strip()
        if not line:
            continue
        stem, _, flags = line.partition("/")
        stem = stem.strip()
        if not stem:
            continue
        words.add(stem)
        for flag in flags.strip()[:MAX_STEM_FLAGS]:
            for rule in rules.get(flag, ()):
                grown = apply(stem, rule)
                if grown:
                    words.add(grown)
    return words


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    pack, out = Path(argv[1]), Path(argv[2])
    words: set[str] = set()
    for name in ("en_GB", "en_AU"):
        dic, aff = pack / f"{name}.dic", pack / f"{name}.aff"
        if dic.exists() and aff.exists():
            words |= expand(dic, aff)
    extra = Path(__file__).with_name("extra_words.txt")
    if extra.exists():
        words |= {w.strip() for w in extra.read_text().splitlines() if w.strip()}
    keep = sorted({w for w in words if w and not w.startswith("'")})
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as handle:
        handle.write("\n".join(keep))
    print(f"{len(keep)} words → {out} ({out.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
