"""Keep the user manual's reference tables true to the program.

docs/USER_MANUAL.md is written by hand, except for the sections between

    <!-- generated:NAME -->
    …
    <!-- /generated -->

which this script writes from the program itself: the markup tools
(``ui/tools.py``), every SMath function the engine evaluates
(``calc/engine/builtins.py``), every spreadsheet function
(``sheet/functions.py``), every Preferences option (``ui/preferences.py``) and
every keyboard shortcut a command has by default (the shortcut list a real
window builds). The one-line descriptions come from ``tools/manual_data.py``
(and the tools' own hints), so regenerating never loses them. README.md's
keyboard tables (``<!-- generated:readme-keys -->``) are written the same way.

The manual ships with the application as ``calcforge/data/USER_MANUAL.md``
(Help ▸ User Manual reads it); this script keeps that copy identical.

    python tools/manual.py            # rewrite the generated sections and the copy
    python tools/manual.py --check    # say what is out of date; exit 1 if anything is

``tests/test_user_manual.py`` runs the check, so the manual cannot drift.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "USER_MANUAL.md"
SHIPPED = ROOT / "calcforge" / "data" / "USER_MANUAL.md"
README = ROOT / "README.md"

SECTIONS = ("markup-tools", "smath-functions", "sheet-functions", "preferences", "shortcuts")
_BLOCK = re.compile(r"(<!-- generated:(?P<name>[a-z-]+) -->\n)(?P<body>.*?)(<!-- /generated -->)",
                    re.S)


def _data():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import manual_data
    finally:
        sys.path.pop(0)
    return manual_data


def _cell(text: str) -> str:
    """Text safe inside a Markdown table cell."""
    return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _code(text: str) -> str:
    """Text as inline code in a table cell (a key, a function's arguments)."""
    text = str(text).replace("|", "\\|")
    return f"`` {text} ``" if "`" in text else f"`{text}`"


# ---------------------------------------------------------------------------
# what the program has
# ---------------------------------------------------------------------------
def smath_function_names() -> list[str]:
    """Every function the SMath engine evaluates (its catalogue, less the
    entries SMath lists that the engine has no implementation of)."""
    import calcforge.calc.engine  # noqa: F401  (registers the extra functions)
    from calcforge.calc.engine import builtins
    return [name for name in builtins.catalogue_names() if builtins.known(name)]


def sheet_function_names() -> list[str]:
    from calcforge.sheet import functions
    return sorted(functions.FUNCTIONS)


def preference_fields() -> list:
    from dataclasses import fields

    from calcforge.ui.preferences import Preferences
    return list(fields(Preferences))


def markup_tools() -> list:
    from calcforge.ui.tools import TOOLS
    return list(TOOLS)


def default_shortcuts(window=None) -> list:
    """(group, command, key, where it acts) for every command that has a key
    out of the box, as the Keyboard Shortcuts list of a real window holds it."""
    from calcforge.ui.shortcuts import SCOPE_NAMES
    made = window is None
    if made:
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is None:
            from calcforge.app import build_application
            build_application([])
        from calcforge.ui.mainwindow import MainWindow
        window = MainWindow()
    try:
        rows = []
        seen = set()
        for binding in window.shortcuts.bindings():
            if not binding.default or binding.action_id in seen:
                continue
            seen.add(binding.action_id)
            rows.append((binding.category or "Other", binding.label.rstrip("…").strip(),
                         binding.default, SCOPE_NAMES.get(binding.scope, binding.scope)))
        return rows
    finally:
        if made:
            window.close()
            window.deleteLater()


# ---------------------------------------------------------------------------
# the sections
# ---------------------------------------------------------------------------
def markup_tools_section(problems: list) -> str:
    lines = ["| Tool | Group | Key | What it does |", "|---|---|---|---|"]
    for tool in markup_tools():
        key = _code(tool.shortcut) if tool.shortcut else "—"
        hint = tool.hint or ""
        if not hint:
            problems.append(f"markup tool {tool.label!r} has no hint in calcforge/ui/tools.py")
        lines.append(f"| **{_cell(tool.label)}** | {_cell(tool.category)} | {key} | "
                     f"{_cell(hint)} |")
    return "\n".join(lines) + "\n"


def smath_functions_section(problems: list) -> str:
    data = _data()
    names = smath_function_names()
    missing = [n for n in names if n not in data.SMATH]
    stale = sorted(set(data.SMATH) - set(names))
    if missing:
        problems.append("SMath functions with no description in tools/manual_data.py SMATH: "
                        + ", ".join(missing))
    if stale:
        problems.append("tools/manual_data.py SMATH describes functions the engine does not "
                        "have: " + ", ".join(stale))
    groups = {group: [] for group in data.SMATH_GROUPS}
    for name in names:
        group, signature, words = data.SMATH.get(name, ("Other", name, "(not described yet)"))
        groups.setdefault(group, []).append((name.lower(), signature, words))
    out = [f"The engine has **{len(names)}** built-in functions.\n"]
    for group, rows in groups.items():
        if not rows:
            continue
        out.append(f"#### {group}\n")
        out.append("| Function | What it does |")
        out.append("|---|---|")
        for _key, signature, words in sorted(rows):
            out.append(f"| {_code(signature)} | {_cell(words)} |")
        out.append("")
    return "\n".join(out)


def sheet_functions_section(problems: list) -> str:
    from calcforge.ui.formulahelp import arguments

    data = _data()
    names = sheet_function_names()
    missing = [n for n in names if n not in data.SHEET]
    stale = sorted(set(data.SHEET) - set(names))
    if missing:
        problems.append("spreadsheet functions with no description in tools/manual_data.py "
                        "SHEET: " + ", ".join(missing))
    if stale:
        problems.append("tools/manual_data.py SHEET describes functions the engine does not "
                        "have: " + ", ".join(stale))
    groups = {group: [] for group in data.SHEET_GROUPS}
    for name in names:
        entry = data.SHEET.get(name, ("Other", "(not described yet)"))
        group, words = entry[0], entry[1]
        if len(entry) > 2:
            signature = entry[2]
        else:
            signature = f"{name}({', '.join(arguments(name))})"
        groups.setdefault(group, []).append((signature, words))
    out = [f"The engine has **{len(names)}** spreadsheet functions.\n"]
    for group, rows in groups.items():
        if not rows:
            continue
        out.append(f"#### {group}\n")
        out.append("| Function | What it does |")
        out.append("|---|---|")
        for signature, words in rows:
            out.append(f"| {_code(signature)} | {_cell(words)} |")
        out.append("")
    return "\n".join(out)


#: How a default reads in the table, where the stored value would not.
_DEFAULT_WORDS = {
    "wheel": {"zoom": "Zooms in and out", "scroll": "Scrolls up and down"},
    "dictionary": {"en_NZ": "New Zealand English"},
    "result_fractions": {"decimal": "Decimal", "fraction": "Fraction", "auto": "Auto"},
}


def _default(field) -> str:
    from dataclasses import MISSING
    if field.default is MISSING:
        return "Your login name" if field.name == "author" else "—"
    value = field.default
    words = _DEFAULT_WORDS.get(field.name, {})
    if value in words:
        return words[value]
    if isinstance(value, bool):
        return "On" if value else "Off"
    if field.name == "filtered_dim_percent":
        return f"{value} %"
    if field.name == "equation_font_size":
        return f"{value:g} pt"
    if field.name == "page_thumbnails":
        return f"{value:g}× (ordinary size)"
    if field.name == "equation_colour":
        return f"{value} (black)" if str(value).lower() == "#000000" else str(value)
    return str(value)


def preferences_section(problems: list) -> str:
    data = _data()
    fields = preference_fields()
    names = [f.name for f in fields]
    missing = [n for n in names if n not in data.PREFERENCES]
    stale = sorted(set(data.PREFERENCES) - set(names))
    if missing:
        problems.append("Preferences with no description in tools/manual_data.py PREFERENCES: "
                        + ", ".join(missing))
    if stale:
        problems.append("tools/manual_data.py PREFERENCES describes options that do not "
                        "exist: " + ", ".join(stale))
    lines = ["| Option | Where | Default | What it does |", "|---|---|---|---|"]
    for field in fields:
        where, option, words = data.PREFERENCES.get(
            field.name, ("—", field.name, "(not described yet)"))
        lines.append(f"| **{_cell(option)}** | {_cell(where)} | {_cell(_default(field))} | "
                     f"{_cell(words)} |")
    return "\n".join(lines) + "\n"


def shortcuts_section(problems: list, window=None, rows=None) -> str:
    data = _data()
    rows = default_shortcuts(window) if rows is None else rows
    order = {group: k for k, group in enumerate(data.SHORTCUT_GROUP_ORDER)}
    by_group: dict[str, list] = {}
    for group, label, key, where in rows:
        by_group.setdefault(group, []).append((label, key, where))
    out = [f"**{len(rows)}** commands have a key out of the box. Every other command can be "
           "given one in Keyboard Shortcuts.\n"]
    for group in sorted(by_group, key=lambda g: (order.get(g, len(order)), g)):
        out.append(f"#### {group}\n")
        out.append("| Command | Key | Works |")
        out.append("|---|---|---|")
        for label, key, where in sorted(by_group[group], key=lambda r: (r[0].lower(), r[1])):
            out.append(f"| {_cell(label)} | {_code(key)} | {_cell(where)} |")
        out.append("")
    return "\n".join(out)


def readme_keys_section(problems: list, rows: list) -> str:
    """README's keyboard tables: every markup tool's key, and the keys of the
    commands README_COMMANDS names, as the program has them now."""
    data = _data()
    lines = ["| Tool | Key |", "|---|---|"]
    for tool in markup_tools():
        if tool.shortcut:
            lines.append(f"| {_cell(tool.label)} | {_code(tool.shortcut)} |")
    lines += ["", "| Command | Key | Works |", "|---|---|---|"]
    keys = {}
    for _group, label, key, where in rows:
        keys.setdefault(label, (key, where))
    for label in data.README_COMMANDS:
        if label not in keys:
            problems.append(f"README_COMMANDS in tools/manual_data.py names {label!r}, which "
                            "has no key out of the box")
            continue
        key, where = keys[label]
        lines.append(f"| {_cell(label)} | {_code(key)} | {_cell(where)} |")
    return "\n".join(lines) + "\n"


def sections(problems: list, window=None, rows=None) -> dict:
    rows = default_shortcuts(window) if rows is None else rows
    return {
        "markup-tools": markup_tools_section(problems),
        "smath-functions": smath_functions_section(problems),
        "sheet-functions": sheet_functions_section(problems),
        "preferences": preferences_section(problems),
        "shortcuts": shortcuts_section(problems, window, rows),
    }


def render(text: str, made: dict, problems: list, where: str = "docs/USER_MANUAL.md") -> str:
    """*text* with each generated section replaced by what *made* holds."""
    found = set()

    def put(match):
        name = match.group("name")
        found.add(name)
        if name not in made:
            problems.append(f"{where} has a generated section nobody makes: {name}")
            return match.group(0)
        return match.group(1) + made[name] + match.group(4)

    out = _BLOCK.sub(put, text)
    for name in made:
        if name not in found:
            problems.append(f"{where} has no <!-- generated:{name} --> section")
    return out


def _both(problems: list, window=None) -> tuple:
    """(manual, README) as they should read."""
    rows = default_shortcuts(window)
    manual = render(MANUAL.read_text(encoding="utf-8"), sections(problems, window, rows),
                    problems)
    readme = render(README.read_text(encoding="utf-8"),
                    {"readme-keys": readme_keys_section(problems, rows)}, problems, "README.md")
    return manual, readme


def check(window=None) -> list[str]:
    """Everything that is out of date, in words; empty when the manual is true."""
    problems: list[str] = []
    text = MANUAL.read_text(encoding="utf-8")
    wanted, readme = _both(problems, window)
    if wanted != text:
        problems.append("docs/USER_MANUAL.md's generated sections are out of date: run "
                        "python tools/manual.py")
    if not SHIPPED.exists() or SHIPPED.read_text(encoding="utf-8") != text:
        problems.append("calcforge/data/USER_MANUAL.md is not the same as docs/USER_MANUAL.md: "
                        "run python tools/manual.py")
    if readme != README.read_text(encoding="utf-8"):
        problems.append("README.md's keyboard tables are out of date: run python tools/manual.py")
    return problems


def write(window=None) -> list[str]:
    problems: list[str] = []
    text, readme = _both(problems, window)
    MANUAL.write_text(text, encoding="utf-8")
    SHIPPED.write_text(text, encoding="utf-8")
    README.write_text(readme, encoding="utf-8")
    return problems


def _sandbox() -> None:
    """Run the window against settings of its own, never the person's."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    folder = tempfile.mkdtemp(prefix="calcforge-manual-")
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        os.environ[variable] = os.path.join(folder, variable.lower())
        os.makedirs(os.environ[variable], exist_ok=True)
    os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(folder, "calcforge-manual.ini")
    os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(folder, "markforge-absent.ini")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _sandbox()
    sys.path.insert(0, str(ROOT))
    if "--check" in argv:
        problems = check()
        for line in problems:
            print(line)
        if not problems:
            print("docs/USER_MANUAL.md is up to date.")
        return 1 if problems else 0
    problems = write()
    for line in problems:
        print(line)
    print(f"Wrote {MANUAL.relative_to(ROOT)}, {SHIPPED.relative_to(ROOT)} and "
          f"{README.relative_to(ROOT)}.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
