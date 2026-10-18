"""Every command, by mouse and keyboard, checked by eye (docs/qa/QA_PLAN.md §5).

Drives every line of the feature inventory the way a person does, in the real
window, headless (QT_QPA_PLATFORM=offscreen):

* a toolbar button is clicked where it is drawn (``toolbar.widgetForAction``);
* a menu-bar command is reached by clicking the menu title on the menu bar and
  then the item in the open menu (``actionGeometry``) — submenus by clicking
  their item — and again with the keyboard (Alt, then the arrow keys);
* a right-click entry gets a real right press and ``QContextMenuEvent`` on the
  widget under the pointer, and the item is clicked in the live popup;
* a shortcut is pressed with ``QTest.keyClick``;
* panel buttons are clicked and their fields typed into.

Each command runs from a fresh known state (one window reused, the document
reset) in the state it applies to (a fixture library: a rectangle selected, a
table open, a sheet page, Calc mode …). Modal dialogs and blocking popups are
caught by timers, photographed, described and cancelled (a few safe ones are
also run once with OK). For each run it records the exception, Qt warnings,
time taken, what changed on screen, the dialog opened, and whether one undo
puts the document back — with before/after pictures gathered onto contact
sheets.

    python tools/qa/exercise.py build [inventory.md]   # -> tools/qa/commands.json
    python tools/qa/exercise.py run --out DIR [--theme dark] [--only PREFIX] [--workers 2]
    python tools/qa/exercise.py sheets --out DIR        # contact sheets from a run

``tests/test_every_command.py`` keeps the mechanical part permanent.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from collections import OrderedDict, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMANDS_JSON = os.path.join(ROOT, "tools", "qa", "commands.json")
INVENTORY_MD = os.path.join(ROOT, "docs", "qa", "feature_inventory.md")
sys.path.insert(0, ROOT)


def _sandbox() -> None:
    """Settings, recovery files and the rest go somewhere disposable."""
    if os.environ.get("CALCFORGE_SETTINGS_FILE"):
        return                                 # the test suite's conftest did it
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    box = tempfile.mkdtemp(prefix="calcforge-exercise-")
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        os.environ[var] = os.path.join(box, var.lower())
        os.makedirs(os.environ[var], exist_ok=True)
    os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(box, "calcforge-exercise.ini")
    os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(box, "markforge-absent.ini")


# ===========================================================================
# 1. the inventory -> commands.json
# ===========================================================================
SECTION_AREAS = ("Menu bar", "Toolbars", "Right-click menus", "Panels", "Dialogs", "Keys",
                 "Mouse")
MENU_TOPS = ("CalcForge", "File", "Edit", "View", "Document", "Batch", "Tools",
             "Calculation", "Window", "Help")


def parse_inventory(path: str) -> list[dict]:
    rows, area = [], None
    for line in open(path, encoding="utf-8"):
        if line.startswith("## "):
            title = line[3:].split(" (")[0].strip()
            area = title if title in SECTION_AREAS else None
            continue
        if area is None or not line.startswith("| ") or line.startswith(("| Where", "|---")):
            continue
        cells = [c.strip() for c in line.rstrip("\n").strip().strip("|").split(" | ")]
        if len(cells) < 3:
            continue
        where, raw, shortcut = cells[0], cells[1], cells[2]
        notes = re.findall(r"\*\((.*?)\)\*", raw)
        name = re.sub(r"\s*\*\(.*?\)\*", "", raw).strip()
        name = name.replace("\\|", "|")
        rows.append(dict(area=area, where=where.replace("\\|", "|"), name=name,
                         note="; ".join(notes), shortcut=shortcut.replace("\\|", "|"),
                         covered=cells[3] if len(cells) > 3 else ""))
    return rows


def norm(text: str, mnemonics: bool = False) -> str:
    """Compare labels the way a reader would: case, ellipsis, spelling apart.
    *mnemonics*: the text is Qt's own (``&File``, ``Merge && Centre``)."""
    text = text or ""
    if mnemonics:
        text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    text = text.split("\t")[0].replace("…", "").replace("...", "").strip().casefold()
    for gb, us in (("colour", "color"), ("centre", "center"), ("customise", "customize"),
                   ("anticlockwise", "counterclockwise"), ("grey", "gray")):
        text = text.replace(gb, us)
    return re.sub(r"\s+", " ", text)


# what a command needs to be in reach: by its name (menu-bar and key rows)
STATE_BY_NAME = {
    # one markup picked
    "cut": "rect", "copy": "rect", "duplicate": "rect", "delete": "rect",
    "multiply": "rect", "offset": "rect", "hide": "rect", "lock": "rect",
    "format painter": "rect", "bring to front": "rect", "bring forward": "rect",
    "send backward": "rect", "send to back": "rect", "zoom to selection": "rect",
    "flatten selection": "rect", "flatten": "rect", "set as default": "rect",
    "selected markups": "rect", "lock (revu's key)": "rect",
    "bold": "textbox", "italic": "textbox", "underline": "textbox", "align left": "textbox",
    "strikethrough": "textbox", "superscript": "textbox", "subscript": "textbox",
    "align center": "textbox", "align right": "textbox", "increase font size": "textbox",
    "decrease font size": "textbox", "auto-size": "textbox", "text": "textbox",
    # several
    "group": "two_rects", "align": "two_rects", "change colors": "two_rects",
    "ungroup": "group", "arrange": "rect",
    "paste": "copied", "paste in place": "copied", "paste here": "copied",
    "undo": "undoable", "redo": "redoable", "redo (revu's key)": "redoable",
    "undo history": "undoable",
    "show hidden": "hidden", "unflatten": "flattened", "apply redactions": "redact",
    "check spelling in markups": "misspelt", "check spelling": "misspelt",
    "renumber counts": "counts", 
    "previous page": "two_pages_second", "previous page (revu's key)": "two_pages_second",
    "next page": "two_pages", "next page (revu's key)": "two_pages",
    "duplicate page": "two_pages", "delete pages": "two_pages", "extract pages": "two_pages",
    "split document": "two_pages", "crop pages": "fresh",
    "sheet layout": "sheet_open", "color processing": "pdf_page",
    "remove page break": "sheet_break", "reset all page breaks": "sheet_break",
    "insert page break": "sheet_open", "set print area": "sheet_open",
    "clear print area": "sheet_open", "page layout": "sheet_open",
    "reset page label": "two_pages_labelled", "reset all page labels": "two_pages_labelled",
    "table of contents": "bookmarked",
    # Calc
    "calculate": "equations", "solve": "equation", "calculate selection": "equation",
    "invert": "matrix_eq", "determinant": "matrix_eq", "selection": "equation",
    "block": "two_equations", "double-check": "equations",
    "conditional formatting": "equations",
    "function": "equation_editing", "operator": "equation_editing",
    "constants": "equation_editing", "matrix": "calc_mode", "plot": "calc_mode",
    "calc text": "calc_mode", "program": "calc_mode", "if": "calc_mode", "for": "calc_mode",
    "while": "calc_mode", "line": "calc_mode", "chart": "table_range", "table": "fresh",
}

# a right-click menu's 'where' -> (state, target)
CONTEXT_TARGETS = [
    ("Canvas, two shapes selected", "two_rects", "item"),
    ("Canvas, empty page (Markup mode)", "fresh", "paper"),
    ("Canvas, empty page (Calc mode", "calc_mode", "paper"),
    ("Canvas, any item", "rect", "item"),
    ("Canvas, any markup", "rect", "item"),
    ("Canvas, 9 kinds (Line", "line", "item"),
    ("Canvas, 9 kinds (Length", "length", "item"),
    ("Canvas, Polyline / Rectangle", "rect", "item"),
    ("Canvas, Rectangle / Ellipse", "rect", "item"),
    ("Canvas, Link", "link", "item"),
    ("Canvas, Hyperlink", "link", "item"),
    ("Canvas, 26 kinds (Pen", "rect", "item"),
    ("Canvas, Text box / Callout / Cloud+ / calculation text", "textbox", "item"),
    ("Canvas, Text box / Callout / Cloud+", "textbox", "item"),
    ("Canvas, Callout / Cloud+", "callout", "item"),
    ("Canvas, table", "table_closed", "item"),
    ("Canvas, equation", "equation", "item"),
    ("Canvas, calculation block", "calc_block", "item"),
    ("Canvas, calculation text", "calc_text", "item"),
    ("Markups List row", "markups_list", "markups_row"),
    ("Markups List column heading", "markups_list", "markups_header"),
    ("Thumbnails (two pages", "two_pages_picked", "thumbnail"),
    ("Thumbnail (one page)", "two_pages", "thumbnail"),
    ("Document tab", "fresh", "doc_tab"),
    ("Ruler", "rulers", "ruler"),
    ("Tool Chest ▸ Tool Sets button", "toolchest", "chest_button"),
    ("Tool Chest ▸ a set's gear button", "toolchest", "chest_gear"),
    ("Tool Chest ▸ a tool (right-click)", "toolchest", "chest_tool"),
    ("Table cell (open table)", "table_open", "cell"),
    ("Spreadsheet cell", "sheet_open", "cell"),
    ("Sheet tab", "sheet_open", "sheet_tab"),
    ("Variables panel row", "variables", "variables_row"),
]

# any item's menu is also tried on these (the inventory lists it once)
ALSO_ON = {"Canvas, any item": [("equation", "item"), ("calc_block", "item"),
                                ("table_closed", "item")]}

# the Properties bar's kind combos ("Pen — Subject, and more") -> the fixture
# that picks a markup of that kind, so its row of controls is on screen
KIND_STATE = {
    "Nothing selected": "fresh", "Pen": "pen", "Highlighter": "highlighter", "Line": "line",
    "Arrow": "arrow", "Arc": "arc", "Polyline": "polyline", "Rectangle": "rect",
    "Ellipse": "ellipse", "Polygon": "polygon", "Cloud": "cloud", "Highlight": "highlight",
    "Redaction": "redact", "Link": "link", "Hyperlink": "link", "Text box": "textbox",
    "Text Box": "textbox", "Callout": "callout", "Cloud+": "cloudplus", "Note": "note",
    "Stamp": "stamp", "Flag": "flag", "Contents": "contents", "Length": "length",
    "Dimension": "dimension", "Polyline length": "polylength", "Polylength": "polylength",
    "Area": "area", "Perimeter": "perimeter", "Volume": "volume", "Angle": "angle",
    "Radius": "radius", "Centre Radius": "radius", "Diameter": "diameter", "Count": "counts",
    "Image": "image", "Equation": "equation", "Calculation block": "calc_block",
    "Calculation text": "calc_text", "Table": "table_closed",
}

# toolbar rows that need something picked first
STYLE_STATE = [
    (("line ending", "end size"), "line"),
    (("corner radius", "hatch"), "rect"),
    (("size: how big the cloud",), "cloud"),
    (("count symbol",), "counts"),
    (("(unlabelled)", "text colour", "text alignment", "b", "i", "u"), "textbox"),
]

# dialogs reached only through code: the command a person uses to open them
DIALOG_OPENERS = {
    "dialogs.scale_dialog()": ("fresh", ["menu", ["Tools", "Measure", "Set Scale…"]]),
    "datatools.top10_dialog()": ("table_filtered", ["context", "filter_button", ["Top 10…"]]),
    "mainwindow.bookmark_page()": ("two_pages", ["context", "thumbnail", ["Add Bookmark"]]),
    "cfmanager.edit()": ("table_open", ["context", "cell", ["Conditional Formatting", "New Rule…"]]),
    "cfmanager.rules_manager()": ("table_open", ["context", "cell",
                                                 ["Conditional Formatting", "Manage Rules…"]]),
    "changecolors.change_multiple_colors()": ("two_rects", ["context", "item", ["Change Colours…"]]),
    "chartdialog.edit_chart()": ("chart", ["mouse", "chart | Double-click"]),
    "colorprocess.change_colors()": ("pdf_page", ["menu", ["Document", "Color Processing…"]]),
    "condformat.open_document_rules()": ("equations", ["menu", ["Calculation",
                                                                "Conditional Formatting…"]]),
    "condformat.open_equation_rules()": ("equation", ["context", "item",
                                                      ["Equation", "Conditional Formatting…"]]),
    "datatools.cell_rule_dialog()": ("table_open", ["context", "cell", [
        "Conditional Formatting", "Highlight Cells Rules", "Greater Than…"]]),
    "datatools.comment_dialog()": ("table_open", ["context", "cell", ["Comment", "New Comment…"]]),
    "datatools.custom_filter_dialog()": ("table_filtered", ["context", "filter_button",
                                                            ["Number/Text Filter…"]]),
    "datatools.date_rule_dialog()": ("table_open", ["context", "cell", [
        "Conditional Formatting", "Highlight Cells Rules", "A Date Occurring…"]]),
    "datatools.duplicates_dialog()": ("table_open", ["context", "cell", ["Data",
                                                                         "Remove Duplicates…"]]),
    "datatools.find_dialog()": ("table_open", ["context", "cell", ["Find & Replace…"]]),
    "datatools.goal_seek_dialog()": ("table_open", ["context", "cell", ["Data", "Goal Seek…"]]),
    "datatools.sort_dialog()": ("table_open", ["context", "cell", ["Data", "Custom Sort…"]]),
    "datatools.text_columns_dialog()": ("table_open", ["context", "cell", [
        "Data", "Text to Columns…"]]),
    "datatools.text_rule_dialog()": ("table_open", ["context", "cell", [
        "Conditional Formatting", "Highlight Cells Rules", "Text that Contains…"]]),
    "datatools.validation_dialog()": ("table_open", ["context", "cell", ["Data",
                                                                         "Data Validation…"]]),
    "datatools.values_dialog()": ("table_filtered", ["context", "filter_button",
                                                     ["Choose Values…"]]),
    "dialogs.choose_count_subject()": ("count_tool", ["toolbar", "Properties", "Count subject…"]),
    "dialogs.add_viewport()": ("fresh", ["menu", ["Tools", "Measure", "Viewports…"]]),
    "hatchpatterns.manage_hatches()": ("rect", ["toolbar", "Properties", "Hatch pattern, drawn over the fill in its own colour",
                                                {"choose": "Manage…"}]),
    # Line Styles: the line-style list's Manage…, as Hatch Patterns is the hatch list's
    "linestyledialog.manage_line_styles()": ("rect", ["toolbar", "Properties", "Solid",
                                                      {"choose": "Manage…"}]),
    "linestyledialog.new_style()": ("rect", ["toolbar", "Properties", "Solid",
                                             {"choose": "Manage…",
                                              "inside": {"title": "Line Styles",
                                                         "click": "New…"}}]),
    "hatchpatterns.new_pattern()": ("rect", ["toolbar", "Properties", "Hatch pattern, drawn over the fill in its own colour",
                                             {"choose": "Manage…",
                                              "inside": {"title": "Hatch Patterns",
                                                         "click": "New…"}}]),
    "mainwindow.apply_to_pages()": ("rect", ["context", "item", ["Apply to Pages…"]]),
    "pagedialogs.apply_to_pages_dialog()": ("rect", ["context", "item", ["Apply to Pages…"]]),
    "markupstyles.rename()": ("styles", ["context", "style_button", ["Rename…"]]),
    "names.open_editor()": ("table_open", ["context", "cell", ["Names", "Name Manager…"],
                                           {"inside": {"title": "Name Manager",
                                                       "click": "New…"}}]),
    "panels.rename()": ("bookmarked", ["panel", "Bookmarks", "Rename"]),
    "panels.rename_set()": ("toolchest", ["call", "rename_set"]),
    "sheetlayout.sheet_page_setup()": ("sheet_open", ["menu", ["Calculation", "Page Layout",
                                                                "Sheet Layout…"]]),
    "tableedit._ask_name()": ("table_open", ["context", "cell", ["Names", "Define Name…"]]),
    "tableedit.rename()": ("table_open", ["context", "cell", ["Rename Table…"]]),
    "view.edit_note()": ("note", ["mouse", "note | Double-click"]),
    "xlsximport.__init__()": ("fresh", ["menu", ["File", "Import", "Excel Workbook…"],
                                        {"policy": "ok"}]),
    "calcdialogs.operator_to_insert()": ("equation_editing", ["menu", ["Calculation",
                                                                      "Operator…"]]),
    "calcdialogs.pick()": ("equation_editing", ["menu", ["Calculation", "Function…"]]),
    "calcmenu.plot_settings()": ("plot_item", ["context", "item", ["Plot settings…"]]),
    "calcsections.rename()": ("section_break", ["context", "thumbnail",
                                                ["Rename Calc Section…"]]),
    "condformat.save_preset()": ("equation", ["context", "item", [
        "Equation", "Conditional Formatting…"], {"inside": {
            "title": "Conditional Formatting", "click": "Save these rules as a preset…"}}]),
    "condformat.new_preset()": ("equations", ["menu", ["Calculation", "Conditional Formatting…"],
                                              {"inside": {"title": "Conditional Formatting Rules",
                                                          "click": "New"}}]),
    "condformat.rename_preset()": ("equations", ["menu", ["Calculation",
                                                          "Conditional Formatting…"],
                                                 {"inside": {"title": "Conditional Formatting "
                                                             "Rules", "click": "Rename"}}]),
    "managetoolsets._ask_name()": ("toolchest", ["menu", ["Tools", "Tool Chest",
                                                          "Manage Tool Sets…"],
                                                 {"inside": {"title": "Manage Tool Sets",
                                                             "click": "Add…"}}]),
    "dialogs.save_preset()": ("fresh", ["menu", ["Tools", "Measure", "Set Scale…"],
                                        {"inside": {"title": "Set Scale",
                                                    "click": "+ Add Preset"}}]),
    # Advanced Printing: the Print dialog's Advanced button, as Revu opens it
    "printdialog.open_advanced()": ("fresh", ["menu", ["File", "Print…"],
                                              {"inside": {"title": "Print",
                                                          "click": "Advanced"}}]),
    "(no opener found)": ("two_pages", ["context", "thumbnail", ["Insert Pages", "After…"]]),
}

# dialogs that are also run once with OK (their defaults), to see them work
SAFE_OK = ("Insert Blank Page", "Page Setup", "Rectangle Size", "Multiply", "Add Bookmark",
           "Document Properties", "Rename", "Insert matrix", "Insert Matrix", "Sort",
           "Goal Seek", "Format Cells", "Flatten Markups", "Set Scale", "Headers",
           "Crop Pages", "Delete Pages", "Customise Toolbars", "Row Height", "Column Width",
           "Greater Than", "Text that Contains", "Data Validation", "Comment",
           "Remove Duplicates", "Define Name", "Page layout", "Apply to Pages",
           "Conditional Formatting", "Chart", "Color Processing", "Change Multiple",
           "Add Pages", "Duplicate Values")

# can't be driven headless at all: why (printing is driven: its dialog is opened
# and cancelled; Exit is driven: the window closes and a fresh one is built)
HEADLESS = {
    # (the drawn Minimise / Maximise / Close are gone: the window has its
    # native frame since 11324c9, which the offscreen platform does not draw)
}


def context_target(where: str):
    for prefix, state, target in CONTEXT_TARGETS:
        if where.casefold().startswith(prefix.casefold()):   # "Text box" became "Text Box"
            return state, target, where[:len(prefix)]
    # "Canvas, 28 kinds (Pen, Highlight, …)": a menu several kinds share, tried
    # on the first kind it names (the count changes as kinds are added)
    shared = re.match(r"Canvas, \d+ kinds \(([^,)]+)[^)]*\)", where)
    if shared:
        listed = [k.strip() for k in shared.group(0).split("(", 1)[1].rstrip(")").split(",")]
        first = "Rectangle" if "Rectangle" in listed else listed[0]   # the shape most offer
        return KIND_STATE.get(first, "rect"), "item", shared.group(0)
    single = re.match(r"Canvas, ([A-Za-z+ ]+?)(?= ▸|$)", where)
    if single and single.group(1) in KIND_STATE:
        return KIND_STATE[single.group(1)], "item", single.group(0)
    return None


def job_keys(commands) -> dict:
    """(command id, entry index) -> a key that survives renumbering: where the
    command is, its name and the way in. Ids (M0123) shift whenever a line is
    added above; known_failures.json is keyed by these instead."""
    keys, seen = {}, defaultdict(int)
    for command in commands:
        for index, entry in enumerate(command["entries"]):
            way = entry.get("path") or entry.get("keys") or entry.get("label") or \
                entry.get("gesture") or entry.get("tip") or entry.get("button") or ""
            if isinstance(way, list):
                way = " ▸ ".join(way)
            extra = entry.get("target") or entry.get("state") or ""
            key = f"{command['where']} | {command['name']} | {entry['via']} {way}"
            key += f" @{extra}" if extra else ""
            seen[key] += 1
            keys[(command["id"], index)] = key if seen[key] == 1 else f"{key} #{seen[key]}"
    return keys


def state_for_name(name: str, default="fresh") -> str:
    key = norm(name)
    return STATE_BY_NAME.get(key, STATE_BY_NAME.get(key.rstrip(" ▸"), default))


def menu_path_of(where: str, name: str) -> list[str]:
    return [p.strip() for p in where.split(" ▸ ")] + [name]


def tool_label_set():
    from calcforge.ui.tools import TOOLS
    return {norm(t.label): t.key for t in TOOLS}


def build_commands(path: str) -> list[dict]:
    rows = parse_inventory(path)
    tools = tool_label_set()
    commands = []
    counter = defaultdict(int)
    menu_state = {}
    properties_kind = None
    panel_buttons = set()
    for row in rows:
        area, where, name, note, shortcut = (row["area"], row["where"], row["name"],
                                             row["note"], row["shortcut"])
        prefix = {"Menu bar": "M", "Toolbars": "T", "Right-click menus": "R", "Panels": "P",
                  "Dialogs": "D", "Keys": "K", "Mouse": "U"}[area]
        counter[prefix] += 1
        cid = f"{prefix}{counter[prefix]:04d}"
        entries = []
        sub = name.endswith(" ▸")
        label = name[:-2] if sub else name
        values = re.match(r"(\d+) (choices|buttons): (.*)", label)
        state = None
        if area == "Menu bar":
            path_parts = menu_path_of(where, label)
            state = state_for_name(label, None) or state_for_name(where.split(" ▸ ")[-1])
            if where.startswith("Tools ▸ Markup") or where.startswith("Tools ▸ Measure") or (
                    where.startswith("Tools ▸ Navigation")):
                state = "fresh"
            if "disabled" in note and state == "fresh":
                state = "auto"
            kind = "submenu" if sub else ("each" if values else "item")
            if values:
                path_parts = menu_path_of(where, "*")
            entries.append(dict(via="menu", path=path_parts, kind=kind))
            if not values:
                entries.append(dict(via="menu_keys", path=path_parts, kind=kind))
            if label.startswith(("No ", "Nothing ")):     # a greyed placeholder line
                state = "fresh"
                for entry in entries:
                    entry["expect_disabled"] = True
            if shortcut and not sub:
                for part in shortcut.split(" / "):
                    entries.append(dict(via="key", keys=part))
            menu_state[norm(label)] = state
        elif area == "Toolbars":
            if where.startswith("Toolbar "):
                bar, _, button = where[len("Toolbar "):].partition(" ▸ ")
                if button:
                    entries.append(dict(via="toolbar_menu", bar=bar, button=button,
                                        path=[label] if not values else ["*"]))
                else:
                    entries.append(dict(via="toolbar", bar=bar, label=label,
                                        widget=note.split(";")[0] if note else ""))
                    if label.startswith("Markup Styles: pick"):
                        entries[-1]["expect_disabled"] = True     # a greyed hint
                if shortcut and not button:
                    entries.append(dict(via="key", keys=shortcut.split(" / ")[0]))
                state = "fresh"
                lowered = label.casefold()
                kind = re.match(r"(.+?) — Subject, and more$", label)
                if bar == "Properties" and kind:
                    # Revu's Properties bar: one row of controls per markup kind,
                    # headed by that kind's combo; the rows below it are its own
                    properties_kind = KIND_STATE.get(kind.group(1)) or (
                        f"tool:{tools[norm(kind.group(1))]}" if norm(kind.group(1)) in tools
                        else "rect")
                if bar == "Properties" and (kind or "shown with a markup selected" in note) \
                        and properties_kind:
                    state = properties_kind
                elif bar == "Properties" and "spreadsheet page" in note:
                    state = "sheet_open"
                elif "shown with a table open" in note:
                    state = "table_open"
                elif "shown with a markup selected" in note:
                    state = "rect"
                    for needles, st in STYLE_STATE:
                        if any(n == lowered or (len(n) > 1 and n in lowered)
                               for n in needles):
                            state = st
                elif bar in ("Style", "Properties") and button:
                    state = "table_open"
                elif bar in ("Style", "Properties"):
                    # restyles the picked markup; Set default shows with none picked
                    state = "fresh" if label == "Set default" else "rect"
                elif bar == "Calculation":
                    state = state_for_name(label, "calc_mode")
                elif bar == "Main":
                    state = state_for_name(label, "fresh")
            else:
                container, _, button = where.partition(" ▸ ")
                state = {"Formula bar": "table_open", "Sheet tabs bar": "sheet_open"}.get(
                    container, "fresh")
                if button:
                    entries.append(dict(via="widget_menu", container=container, button=button,
                                        path=[label]))
                else:
                    entries.append(dict(via="widget", container=container, label=label,
                                        kind=note.split(",")[0].split(";")[0]))
                if container == "Status bar" and label in ("Previous Page", "Next Page",
                                                           "First Page", "Last Page"):
                    state = "three_pages"
                if "disabled" in note or label.startswith(("(no ", "No ", "Nothing ")):
                    entries[-1]["expect_disabled"] = True     # a greyed placeholder
        elif area == "Right-click menus":
            target = context_target(where)
            if target is None:
                state = "fresh"
                entries.append(dict(via="unknown", where=where))
            else:
                state, tgt, pre = target
                rest = where[len(pre):].replace(" — also Document ▸ Current Page", "")
                rest = rest[rest.index(" ▸ ") + 3:] if " ▸ " in rest else ""
                path_parts = ([p for p in rest.split(" ▸ ")] if rest else []) + [
                    "*" if values else label]
                kind = "submenu" if sub else ("each" if values else "item")
                if label.startswith("[field]"):
                    kind = "field"
                if label.startswith("Filter ") and tgt == "markups_header":
                    entries.append(dict(via="context", target=tgt, column=label[7:].split(":")[0],
                                        path=["(All)"], kind="item"))
                else:
                    entries.append(dict(via="context", target=tgt, path=path_parts, kind=kind))
                    for also_prefix, others in ALSO_ON.items():
                        if where.startswith(also_prefix):
                            if state == "two_rects":
                                others = [("two_equations", "item")]
                            for st, t in others:
                                entries.append(dict(via="context", target=t, state=st,
                                                    path=path_parts, kind=kind))
                if "Paste Pages" in path_parts[:-1] or label == "Paste Pages":
                    state = "pages_copied"
                if "Alignment" in path_parts[:-1] or label == "Alignment":
                    state = "two_rects"
                if label in ("Clear Filter",):
                    state = "table_filtered"
                if label in ("Delete Comment",):
                    state = "table_commented"
                if label in ("Reset Page Label", "Reset All Page Labels"):
                    state = "two_pages_labelled"
                if label == "Calc Section Break Above This Page" and tgt == "paper":
                    state = "calc_page2"
                if tgt == "cell" and (label == "Paste" or "Paste Special" in path_parts):
                    state = "table_copied" if state == "table_open" else "sheet_copied"
                if "also Document ▸ Current Page" in where:
                    entries.append(dict(via="menu", path=["Document", "Current Page"] + path_parts,
                                        kind=kind))
                if "(two pages" in where:
                    entries[0]["kind"] = kind
                if "disabled here" in note or (label.startswith("No ") and
                                               label.casefold().endswith("yet")):
                    entries[0]["expect_disabled"] = True
        elif area == "Panels":
            panel, _, rest = where.partition(" ▸ ")
            state = "fresh"
            if panel.endswith(" (title bar)"):
                entries.append(dict(via="dock_button", panel=panel[:-len(" (title bar)")],
                                    tip=label))
            elif label == "(panel shown/hidden)":
                entries.append(dict(via="panel_toggle", panel=panel))
                entries.append(dict(via="menu", path=["Window", "Panels", panel], kind="item"))
                if shortcut:
                    entries.append(dict(via="key", keys=shortcut))
            elif values:
                entries.append(dict(via="panel_each", panel=panel, group=rest))
            elif rest.endswith("Add to Tool Chest"):
                entries.append(dict(via="panel_menu", panel=panel, button="Add to Tool Chest",
                                    path=[label]))
            elif (panel, rest) in panel_buttons:
                # a row under a panel's button: an item of that button's menu
                # (Thumbnails ▸ + ▸ Before…)
                entries.append(dict(via="panel_menu", panel=panel, button=rest, path=[label]))
            else:
                entries.append(dict(via="panel", panel=panel, group=rest, label=label,
                                    kind=note.split(",")[0]))
                if note.startswith("button") and not rest:
                    panel_buttons.add((panel, label))
            if panel in ("Page Setup", "Page") and rest == "Viewports":
                state = "viewport"
            if panel == "Page" and rest == "Scale" and label == "Y scale":
                entries[-1]["expect_disabled"] = True   # greyed until "Separate Y scale"
            if panel == "Properties":
                state = "rect" if "Calc mode" not in note else "rect"
                if label == "Bookmark":
                    state = "textbox"
                if rest == "Appearance" and label in ("Font", "Font Size", "Font Colour", "B",
                                                      "I", "U", "S", "x²", "x₂", "Auto",
                                                      "Alignment", "Margin"):
                    state = "textbox"
            elif panel == "Maths":
                state = "equation_editing" if values else "calc_mode"
            elif panel == "Variables":
                state = "variables"
            elif panel == "Markups List":
                state = "markups_list"
            elif panel == "Bookmarks":
                state = "bookmarked"
            elif panel == "Search":
                state = "pdf_page"
            elif panel == "Thumbnails":
                state = "two_pages"
            elif panel == "Tool Chest":
                state = "toolchest"
        elif area == "Dialogs":
            openers = [o.strip() for o in where.split(";")]
            spec = None
            via = where[4:] if where.startswith("via ") else None
            if via:
                for key in [k for k in DIALOG_OPENERS if k in via]:
                    spec = DIALOG_OPENERS[key]
                    break
            elif where in DIALOG_OPENERS:
                spec = DIALOG_OPENERS[where]
            if spec is None and not via:
                first = openers[0]
                parts = [p.strip() for p in first.split(" ▸ ")]
                if parts[0] in MENU_TOPS:
                    st = state_for_name(parts[-1])
                    spec = (st if st != "fresh" else "auto", ["menu", parts])
                elif first.startswith("Toolbar "):
                    spec = ("calc_mode", ["toolbar", first[8:].split(" ▸ ")[0], parts[-1]])
                else:
                    tgt = context_target(first)
                    if tgt is not None:
                        rest = first[len(tgt[2]):].replace(" — also Document ▸ Current Page", "")
                        sub_parts = rest[rest.index(" ▸ ") + 3:].split(" ▸ ") if " ▸ " in rest \
                            else []
                        spec = (tgt[0], ["context", tgt[1], sub_parts])
            if spec is None:
                entries.append(dict(via="unknown", where=where))
                state = "fresh"
            else:
                state = spec[0]
                how = list(spec[1])
                more = how.pop() if how and isinstance(how[-1], dict) else {}
                if how[0] == "menu":
                    entries.append(dict(via="menu", path=how[1], kind="item", dialog=True))
                elif how[0] == "context":
                    entries.append(dict(via="context", target=how[1], path=how[2], kind="item",
                                        dialog=True))
                elif how[0] == "toolbar":
                    entries.append(dict(via="toolbar", bar=how[1], label=how[2], dialog=True))
                elif how[0] == "panel":
                    entries.append(dict(via="panel", panel=how[1], label=how[2], kind="button",
                                        dialog=True))
                elif how[0] == "mouse":
                    entries.append(dict(via="mouse", gesture=how[1], dialog=True))
                elif how[0] == "call":
                    entries.append(dict(via="call", fn=how[1], dialog=True))
                if entries:
                    entries[-1].update(more)
            title = name.split(" — ")[0]
            if any(title.startswith(s) or s in title for s in SAFE_OK) and entries and \
                    entries[0]["via"] != "unknown":
                ok = dict(entries[0])
                ok["policy"] = "ok"
                entries.append(ok)
        elif area == "Keys":
            kind = note.split(";")[0].strip()
            scope = where.split(" · ")[-1]
            keys = shortcut
            if where.startswith("Canvas, fixed in view.py"):
                entries.append(dict(via="viewkey", what=name, keys=shortcut))
                state = "rect"
            elif where.startswith("Shown only on a menu"):
                entries.append(dict(via="key", keys=keys))
                state = "rect"
            elif not keys:
                state = "fresh"
                entries.append(dict(via="nokey", what=name))
            else:
                for part in keys.split(" / "):
                    entries.append(dict(via="key", keys=part, kind=kind))
                if kind == "tool":
                    state = "fresh"
                    entries[-1]["use_tool"] = True
                elif kind == "sheet":
                    state = "sheet_copied" if norm(name).startswith("paste") else "sheet_open"
                    entries.append(dict(via="key", keys=keys.split(" / ")[0], kind=kind,
                                        state="table_open"))
                elif kind == "smath":
                    state = "equation_editing"
                elif kind == "symbol":
                    state = "textbox_editing"
                elif kind == "insert":
                    state = "calc_mode" if scope == "Calc mode" else "fresh"
                else:
                    base = re.sub(r" \(revu's key\)$", "", norm(name))
                    state = STATE_BY_NAME.get(norm(name)) or STATE_BY_NAME.get(base) or \
                        menu_state.get(base) or "fresh"
                    if state == "auto":
                        state = "fresh"
                    if base in ("calc/markup mode",):
                        state = "fresh"
        elif area == "Mouse":
            state = "fresh"
            entries.append(dict(via="mouse", gesture=f"{where} | {name.split(':')[0]}"))
        if state in (None, "auto"):
            state = "auto"
        command = OrderedDict(id=cid, area=area, where=where, name=name, note=note,
                              shortcut=shortcut, state=state, entries=entries)
        if (where, name) in HEADLESS:
            command["headless"] = HEADLESS[(where, name)]
        commands.append(command)
    return commands


# right-click menus the inventory never opened (it draws what the tools draw
# and stops): each is walked live and every entry it holds is run
EXTRA_MENUS = [
    ("Row heading (open table)", "table_open", "row_heading", False),
    ("Column heading (open table)", "table_open", "col_heading", False),
    ("Row heading (spreadsheet page)", "sheet_open", "row_heading", False),
    ("Column heading (spreadsheet page)", "sheet_open", "col_heading", False),
    ("Markup Styles button", "styles", "style_button1", False),
    ("Markup Styles button (a markup picked)", "styles_selected", "style_button1", False),
    ("Canvas, plot", "plot_item", "item", True),
    ("Canvas, chart", "chart", "item", True),
    ("Canvas, image", "image", "item", True),
    ("Canvas, note", "note", "item", True),
    ("Canvas, stamp", "stamp", "item", True),
    ("Canvas, flag", "flag", "item", True),
    ("Canvas, count", "counts", "item", True),
    ("Canvas, ellipse", "ellipse", "item", True),
    ("Canvas, arrow", "arrow", "item", True),
    ("Canvas, arc", "arc", "item", True),
    ("Canvas, polyline", "polyline", "item", True),
    ("Canvas, polygon", "polygon", "item", True),
    ("Canvas, cloud", "cloud", "item", True),
    ("Canvas, highlight area", "highlight", "item", True),
    ("Canvas, redact", "redact", "item", True),
    ("Canvas, callout", "callout", "item", True, None, ("insert field",)),
    ("Canvas, Cloud+", "cloudplus", "item", True, None, ("insert field",)),
    ("Canvas, pen ink", "pen", "item", True),
    ("Canvas, area", "area", "item", True),
    ("Canvas, perimeter", "perimeter", "item", True),
    ("Canvas, polylength", "polylength", "item", True),
    ("Canvas, volume", "volume", "item", True),
    ("Canvas, angle", "angle", "item", True),
    ("Canvas, radius", "radius", "item", True),
    ("Canvas, diameter", "diameter", "item", True),
    ("Canvas, dimension", "dimension", "item", True),
    ("Canvas, group", "group", "item", True),
    ("Thumbnail of a page after a calc section break", "section_break", "thumbnail", False,
     ("rename calc section", "calc section break above this page")),
    ("Spreadsheet cell, cells copied", "sheet_copied", "cell", False,
     ("paste", "paste special")),
    ("Filter drop-down of a filtered column (open table)", "table_filtered", "filter_button",
     False),
]
# entries every item offers: run once on a rectangle (the inventory's lines)
GENERIC_TOP = {"cut", "copy", "paste", "duplicate", "delete", "order", "alignment",
               "add to tool chest", "multiply", "lock", "unlock", "properties",
               "set as default", "format painter", "hide", "flatten", "apply to pages",
               "group", "ungroup"}


def live_menu(win, state, target):
    """[(path, enabled, checkable)] of the right-click menu on *target*."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    reset(win)
    ctx = build_state(win, state)
    found = []

    def collect(menu, path):
        try:
            menu.aboutToShow.emit()
        except Exception:  # noqa: BLE001
            pass
        for action in menu.actions():
            if action.isSeparator() or not action.isVisible():
                continue
            text = clean(action.text())
            if not text and isinstance(action, QtWidgets.QWidgetAction):
                text = "[field]"
            sub = action.menu()
            found.append((path + [text], action.isEnabled(), action.isCheckable(),
                          sub is not None))
            if sub is not None:
                collect(sub, path + [text])

    def lister(tries=[0]):
        menu = QtWidgets.QApplication.activePopupWidget()
        if not isinstance(menu, QtWidgets.QMenu):
            tries[0] += 1
            if tries[0] < 60:
                QtCore.QTimer.singleShot(30, lister)
            return
        collect(menu, [])
        close_popups()

    widget, local = context_spot(win, target, ctx, {})
    Watch.navigating = True
    QtCore.QTimer.singleShot(80, lister)
    button = QtCore.Qt.LeftButton if target == "filter_button" else QtCore.Qt.RightButton
    QTest.mousePress(widget, button, QtCore.Qt.NoModifier, local)
    QTest.mouseRelease(widget, button, QtCore.Qt.NoModifier, local)
    if QtWidgets.QApplication.activePopupWidget() is None and not found and \
            target != "filter_button":
        QtWidgets.QApplication.sendEvent(widget, QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, local, widget.mapToGlobal(local)))
    settle(200)
    Watch.navigating = False
    close_popups()
    return found


def extra_commands(start: int = 1) -> list[dict]:
    app()
    win = window()
    commands = []
    n = start
    for spec in EXTRA_MENUS:
        where, state, target, markup = spec[:4]
        keep = spec[4] if len(spec) > 4 else None
        drop = spec[5] if len(spec) > 5 else ()
        try:
            entries = live_menu(win, state, target)
        except Exception as error:  # noqa: BLE001
            print(f"extra {where}: {error!r}", file=sys.stderr)
            continue
        for path, enabled, checkable, sub in entries:
            if markup and norm(path[0]) in GENERIC_TOP:
                continue
            if keep and norm(path[0]) not in keep:
                continue
            if norm(path[0]) in drop:
                continue
            if sub:
                continue                     # its entries are listed themselves
            name = path[-1]
            note = ", ".join(x for x, on in (("toggle", checkable),
                                             ("disabled here", not enabled)) if on)
            entry = dict(via="context", target=target, path=path,
                         kind="field" if name == "[field]" else "item")
            if not enabled:
                entry["expect_disabled"] = True
            commands.append(OrderedDict(
                id=f"X{n:04d}", area="Extra (not in the inventory)",
                where=" ▸ ".join([where] + path[:-1]), name=name, note=note, shortcut="",
                state=state, entries=[entry]))
            n += 1
    return commands


def write_commands(path: str = INVENTORY_MD, out: str = COMMANDS_JSON) -> list[dict]:
    commands = build_commands(path) + extra_commands()
    head = os.popen(f"git -C '{ROOT}' rev-parse --short HEAD").read().strip()
    data = OrderedDict(
        about="Every inventory line with the state it needs and the real UI paths that "
              "reach it. Generated by `python tools/qa/exercise.py build` from "
              "docs/qa/feature_inventory.md; edit the tables in exercise.py, not this file.",
        inventory=os.path.relpath(path, ROOT), commit=head, count=len(commands),
        entries=sum(len(c["entries"]) for c in commands), commands=commands)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    return commands


def load_commands(path: str = COMMANDS_JSON) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["commands"]


def jobs_of(commands) -> list[tuple[dict, int, dict]]:
    return [(c, i, e) for c in commands for i, e in enumerate(c["entries"])]


# ===========================================================================
# 2. the live window
# ===========================================================================
APP = None
WIN = None
QtMods = None


def qt():
    """Import Qt late, after the sandbox is in place."""
    global QtMods
    if QtMods is None:
        from PySide6 import QtCore, QtGui, QtWidgets
        from PySide6.QtTest import QTest
        QtMods = (QtCore, QtGui, QtWidgets, QTest)
    return QtMods


def pump(times: int = 2) -> None:
    for _ in range(times):
        APP.processEvents()


def settle(ms: int = 30) -> None:
    """Let deferred work (single-shot timers) run, as it would for a person."""
    QtCore = qt()[0]
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        APP.processEvents(QtCore.QEventLoop.AllEvents, 10)
    pump()


# What app() changed in the process, so shutdown() can put it back: inside the
# test suite the same QApplication goes on to run every other test file.
_RESTORE: dict = {}


def app():
    """The application, with the harness's recorders and dialog watchers on.
    Started is its own flag, not "APP is set": another test file borrows this
    module's helpers and sets APP itself (test_exercise_round1_undo.py), and a
    worker that ran it first then had no watchers — the next dialog was never
    closed and the worker hung or crashed (D0003, gate on eebcff1)."""
    global APP
    if not _RESTORE.get("started"):
        _sandbox()
        from PySide6.QtWidgets import QApplication
        APP = QApplication.instance()
        if APP is None:
            from calcforge.app import build_application
            APP = build_application([])
        _RESTORE["quit_on_last"] = APP.quitOnLastWindowClosed()
        _RESTORE["excepthook"] = sys.excepthook
        _RESTORE["palette"] = APP.palette()
        _RESTORE["style_sheet"] = APP.styleSheet()
        APP.setQuitOnLastWindowClosed(False)
        import faulthandler
        _RESTORE["faulthandler"] = faulthandler.is_enabled()
        faulthandler.enable()
        install_recorders()
        Watch.start()
        from calcforge.ui import scene as scene_module
        _RESTORE["dimmer"] = dict(scene_module.DIMMER)     # app-wide, not per window
        _RESTORE["started"] = True
    return APP


def restore_globals() -> None:
    """State the app keeps for the whole process rather than per window:
    View ▸ Dim Content's on/off and level (scene.DIMMER). A command that left
    it on dimmed the next test file's pages (test_view_workspace.py's dimmer
    test, gate on eebcff1)."""
    if "dimmer" in _RESTORE:
        from calcforge.ui import scene as scene_module
        scene_module.DIMMER.clear()
        scene_module.DIMMER.update(_RESTORE["dimmer"])


def shutdown() -> None:
    """Leave the process as app() found it: no dialog-closing timers, no
    recorders, no window, no clipboard, no tool sets or settings written by
    the commands, the application's own palette. Safe to call twice."""
    global APP, WIN, BASELINE
    if not _RESTORE.get("started"):
        return
    QtCore, QtGui, QtWidgets = qt()[0], qt()[1], qt()[2]
    import shiboken6
    for timer in (Watch.modal_timer, Watch.popup_timer):
        if timer is not None and shiboken6.isValid(timer):
            timer.stop()
            timer.deleteLater()
    Watch.modal_timer = Watch.popup_timer = None
    Watch.reset()
    close_popups()
    if WIN is not None and shiboken6.isValid(WIN):
        try:
            set_theme(WIN, "light")
            close_strays(WIN)
        except Exception:  # noqa: BLE001 - teardown only
            pass
        dispose(WIN)
    WIN = BASELINE = None
    from calcforge.ui.mainwindow import MainWindow
    handled = set()
    for _ in range(60):                        # a fresh list each time (close_strays)
        left = [w for w in QtWidgets.QApplication.topLevelWidgets()
                if shiboken6.isValid(w) and id(w) not in handled and (
                    isinstance(w, MainWindow) or (w.isVisible() and w.isWindow()))]
        if not left:
            break
        widget = left[0]
        handled.add(id(widget))
        if isinstance(widget, MainWindow):
            dispose(widget)                    # New Window's, Exit's, any left
        else:
            widget.close()
            pump()
    pump(3)
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    pump()
    APP.clipboard().clear()
    QtCore.qInstallMessageHandler(_RESTORE.get("message_handler"))
    sys.excepthook = _RESTORE.get("excepthook", sys.__excepthook__)
    APP.setQuitOnLastWindowClosed(_RESTORE.get("quit_on_last", True))
    import faulthandler
    if not _RESTORE.get("faulthandler", True):
        faulthandler.disable()        # the suite runs without it (pytest.ini)
    if "palette" in _RESTORE:
        APP.setPalette(_RESTORE["palette"])
        APP.setStyleSheet(_RESTORE["style_sheet"])
    try:
        from calcforge.settings import app_settings
        settings = app_settings()
        settings.clear()
        settings.sync()
    except Exception:  # noqa: BLE001
        pass
    restore_globals()
    CURRENT.clear()
    _RESTORE.clear()                           # started: no
    APP = None


def new_window():
    from calcforge.ui.mainwindow import MainWindow
    app()
    window = MainWindow()
    window.confirm_discard = lambda: True
    window.interactive_prompts = True
    window.resize(1280, 860)
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump(3)
    return window


def dispose(window) -> None:
    """Close and delete a window, whatever state it is in. Each step stands
    alone: a window that File ▸ Exit closed has already let go of its undo
    stack, and a failed first step must not leave the window alive — a live
    MainWindow filters every event in the application, other tests' included."""
    QtCore = qt()[0]
    import shiboken6
    if window is None or not shiboken6.isValid(window):
        return
    steps = (
        lambda: setattr(window, "confirm_discard", lambda: True),
        lambda: setattr(window.document, "modified", False),
        lambda: window.undo_stack.clear(),
        lambda: window.view.setScene(None),
        lambda: [setattr(page, "frame", None) for page in window.document.pages],
        lambda: window.close(),
        lambda: window.setParent(None),
        lambda: window.deleteLater(),
    )
    for step in steps:
        try:
            step()
        except Exception:  # noqa: BLE001 - teardown only
            pass
    pump(3)
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    pump()


def window_gone(win) -> bool:
    """Closed (File ▸ Exit, Close Window) or already deleted with its history."""
    import shiboken6
    if win is None or not shiboken6.isValid(win):
        return True
    try:
        stack = getattr(win, "undo_stack", None)
        return win.isHidden() or (stack is not None and not shiboken6.isValid(stack))
    except RuntimeError:
        return True


def window():
    global WIN, BASELINE
    import shiboken6
    if WIN is None or window_gone(WIN):
        if WIN is not None and shiboken6.isValid(WIN):
            dispose(WIN)
        WIN = new_window()
        BASELINE = chrome_state(WIN)
    return WIN


# ---------------------------------------------------------------------------
# what gets recorded while a command runs
# ---------------------------------------------------------------------------
CURRENT: dict = {}
NOISE = ("does not support", "propagateSizeHints", "QFont::setPointSize",
         "Populating font family aliases", "QPainter::begin: Paint device returned engine == 0",
         "Fontconfig", "qt.qpa", "QBasicTimer::start", "libpng warning")


def install_recorders() -> None:
    QtCore = qt()[0]
    previous = sys.excepthook

    def hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        if CURRENT is not None and "errors" in CURRENT:
            CURRENT["errors"].append(text)
        else:
            previous(kind, value, tb)
    sys.excepthook = hook

    def handler(mode, context, message):
        if any(n in message for n in NOISE):
            return
        level = {QtCore.QtMsgType.QtWarningMsg: "warning",
                 QtCore.QtMsgType.QtCriticalMsg: "critical",
                 QtCore.QtMsgType.QtFatalMsg: "fatal"}.get(mode)
        if level and "qt_messages" in CURRENT:
            CURRENT["qt_messages"].append(f"{level}: {message}")
    _RESTORE["message_handler"] = QtCore.qInstallMessageHandler(handler)


class Watch:
    """Two timers: one for blocking popups, one for modal dialogs. Each acts
    through a single-shot so neither is ever stuck inside a nested loop."""
    modal_timer = None
    popup_timer = None
    navigating = False
    overflow_token = None
    seen: set = set()
    policy = "cancel"
    shots_dir = None
    handled_first = False

    @classmethod
    def start(cls):
        QtCore = qt()[0]
        cls.modal_timer = QtCore.QTimer()
        cls.modal_timer.timeout.connect(cls.modal_tick)
        cls.modal_timer.start(25)
        cls.popup_timer = QtCore.QTimer()
        cls.popup_timer.timeout.connect(cls.popup_tick)
        cls.popup_timer.start(25)

    @classmethod
    def reset(cls, policy="cancel", inside=None):
        cls.seen = set()
        cls.run += 1
        cls.policy = policy
        cls.handled_first = False
        cls.navigating = False
        cls.inside = dict(inside) if inside else None
        cls.navigating_since = 0.0

    @classmethod
    def note_ui(cls):
        if CURRENT.get("t0") and not CURRENT.get("t_ui"):
            CURRENT["t_ui"] = time.perf_counter()

    # Which dialogs and popups were already handled is marked on the object
    # itself, with the run it was seen in: an id() is reused as soon as the
    # object is freed, and Check Spelling's next word's dialog, built where the
    # last one was, was taken for handled and left the run hanging.
    run = 0

    @classmethod
    def mark_seen(cls, widget, on=True):
        import shiboken6
        if shiboken6.isValid(widget):
            widget.setProperty("qaSeenInRun", cls.run if on else -1)

    @classmethod
    def was_seen(cls, widget):
        return widget.property("qaSeenInRun") == cls.run

    last_tick = 0.0
    last_modal = ""

    @classmethod
    def state(cls) -> str:
        """For a hang report: are the watchers alive, and what did they last see."""
        import shiboken6
        timers = [t for t in (cls.modal_timer, cls.popup_timer)]
        alive = [t is not None and shiboken6.isValid(t) and t.isActive() for t in timers]
        return (f"watch timers active {alive}; last modal tick "
                f"{time.perf_counter() - cls.last_tick:.1f} s ago; last modal seen "
                f"{cls.last_modal!r}; navigating {cls.navigating}; run {cls.run}; "
                f"policy {cls.policy}")

    @classmethod
    def modal_tick(cls):
        QtCore, QtGui, QtWidgets, QTest = qt()
        cls.last_tick = time.perf_counter()
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is not None:
            cls.last_modal = f"{type(modal).__name__} {modal.windowTitle()} seen=" \
                f"{modal.property('qaSeenInRun')} visible={modal.isVisible()}"
        if modal is None or cls.was_seen(modal) or not modal.isVisible():
            return
        cls.mark_seen(modal)
        cls.note_ui()
        QtCore.QTimer.singleShot(60, lambda m=modal: cls.handle_modal(m))

    inside = None                     # {"title": parent, "click": button text}

    @classmethod
    def handle_modal(cls, modal):
        try:
            cls._handle_modal(modal)
        except Exception:  # noqa: BLE001 - the dialog must still go
            CURRENT.setdefault("harness_notes", []).append(traceback.format_exc()[-600:])
            QtWidgets = qt()[2]
            if isinstance(modal, QtWidgets.QDialog):
                modal.reject()
            else:
                modal.close()

    @classmethod
    def _handle_modal(cls, modal):
        import shiboken6
        QtCore, QtGui, QtWidgets, QTest = qt()
        # The dialog is asked for again rather than trusted from the tick: a
        # dialog built in C++ (QInputDialog.getItem) where the last one was
        # freed can come back as the old, dead Python wrapper, which isValid()
        # calls gone — and the dialog was left open (R0277 hung, gate on
        # eebcff1, on its fourth Add to Tool Set dialog in a row).
        current = QtWidgets.QApplication.activeModalWidget()
        if current is not None and current.isVisible():
            modal = current
        if not shiboken6.isValid(modal) or not modal.isVisible():
            return
        record = describe_dialog(modal)
        CURRENT.setdefault("dialogs", []).append(record)
        record["shot"] = save_shot(modal.grab().toImage(), "dialog")
        plan = cls.inside
        if plan and not plan.get("done") and norm(qt()[2].QWidget.windowTitle(modal)).startswith(
                norm(plan["title"])):
            plan["done"] = True
            button = next((b for b in modal.findChildren(QtWidgets.QAbstractButton)
                           if b.isVisible() and norm(clean(b.text())) == norm(
                               plan["click"])), None)
            record["policy"] = "inside"
            if button is None:
                record["inside_missing"] = plan["click"]
            else:
                record["pressed"] = clean(button.text())

                def press(b=button, m=modal):
                    QTest.mouseClick(b, QtCore.Qt.LeftButton)
                    # the parent is handled again (cancelled) once its child closed
                    QtCore.QTimer.singleShot(150, lambda: cls.mark_seen(m, False))
                QtCore.QTimer.singleShot(0, press)
                return
        if plan and plan.get("done") and not plan.get("child_seen") and \
                not norm(qt()[2].QWidget.windowTitle(modal)).startswith(norm(plan["title"])):
            plan["child_seen"] = True
            cls.handled_first = False          # the child gets the entry's policy
        policy = cls.policy if not cls.handled_first else "cancel"
        cls.handled_first = True
        record["policy"] = policy
        if policy == "ok" and isinstance(modal, QtWidgets.QFileDialog):
            path = file_for(modal)
            record["typed_path"] = path
            names = [e for e in modal.findChildren(QtWidgets.QLineEdit) if e.isVisible()]
            if names:
                field = names[0]
                QTest.keyClick(field, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
                QTest.keyClicks(field, path)
                QTest.keyClick(field, QtCore.Qt.Key_Return)
                record["pressed"] = "typed path, Enter"
            QtCore.QTimer.singleShot(400, lambda m=modal, r=record: cls.ensure_closed(m, r))
            return
        if policy == "ok":
            button = default_button(modal)
            if button is not None:
                record["pressed"] = clean(button.text())
                QTest.mouseClick(button, QtCore.Qt.LeftButton)
            else:
                QTest.keyClick(modal, QtCore.Qt.Key_Return)
                record["pressed"] = "Enter"
        else:
            focus = QtWidgets.QApplication.focusWidget()
            target = focus if focus is not None and modal.isAncestorOf(focus) else modal
            QTest.keyClick(target, QtCore.Qt.Key_Escape)
            record["pressed"] = "Esc"
        QtCore.QTimer.singleShot(400, lambda m=modal, r=record: cls.ensure_closed(m, r))

    @classmethod
    def ensure_closed(cls, modal, record, tries=0):
        import shiboken6
        QtCore, QtGui, QtWidgets, QTest = qt()
        current = QtWidgets.QApplication.activeModalWidget()   # (see _handle_modal)
        if current is not None and current.isVisible() and \
                QtWidgets.QWidget.windowTitle(current) == record.get("title"):
            modal = current
        if not shiboken6.isValid(modal) or not modal.isVisible():
            return
        if record.get("pressed") != "Esc" and tries == 0:
            record["ok_kept_open"] = True       # OK refused (validation?) -> cancel
            QTest.keyClick(modal, QtCore.Qt.Key_Escape)
        else:
            record["escape_ignored"] = True
            if isinstance(modal, QtWidgets.QDialog):
                modal.reject()
            else:
                modal.close()
        if tries < 3:
            QtCore.QTimer.singleShot(300, lambda: cls.ensure_closed(modal, record, tries + 1))
        else:
            record["would_not_close"] = True
            modal.hide()

    navigating_since = 0.0

    @classmethod
    def popup_tick(cls):
        QtCore, QtGui, QtWidgets, QTest = qt()
        popup = QtWidgets.QApplication.activePopupWidget()
        if cls.navigating:
            if not cls.navigating_since:
                cls.navigating_since = time.perf_counter()
            elif time.perf_counter() - cls.navigating_since > 8 and popup is not None:
                CURRENT.setdefault("harness_notes", []).append(
                    f"a menu walk stalled; closed {type(popup).__name__}")
                cls.navigating = False
                popup.close()
            return
        cls.navigating_since = 0.0
        if popup is None or cls.was_seen(popup) or not popup.isVisible():
            return
        cls.mark_seen(popup)
        cls.note_ui()
        QtCore.QTimer.singleShot(60, lambda p=popup: cls.handle_popup(p))

    @classmethod
    def handle_popup(cls, popup):
        try:
            cls._handle_popup(popup)
        except Exception:  # noqa: BLE001
            CURRENT.setdefault("harness_notes", []).append(traceback.format_exc()[-600:])
            popup.close()

    @classmethod
    def _handle_popup(cls, popup):
        import shiboken6
        QtCore, QtGui, QtWidgets, QTest = qt()
        if not shiboken6.isValid(popup) or not popup.isVisible() or cls.navigating:
            if shiboken6.isValid(popup) and cls.navigating:
                cls.mark_seen(popup, False)
            return
        kind = type(popup).__name__
        record = dict(kind=kind, title=getattr(popup, "title", lambda: "")() if isinstance(
            popup, QtWidgets.QMenu) else "")
        if isinstance(popup, QtWidgets.QMenu):
            record["items"] = [clean(a.text()) for a in popup.actions() if not a.isSeparator()][:30]
        record["shot"] = save_shot(popup.grab().toImage(), "popup")
        CURRENT.setdefault("popups", []).append(record)
        if kind in ("ColourPopup", "FoundPopup"):
            # pick a colour, as a person would: the second swatch of the palette
            swatches = [b for b in popup.findChildren(QtWidgets.QToolButton)
                        if b.isVisible() and b.objectName() not in ("plain",)]
            if len(swatches) > 3:
                record["picked"] = swatches[3].toolTip() or "swatch 4"
                QTest.mouseClick(swatches[3], QtCore.Qt.LeftButton)
                return
        QTest.keyClick(popup, QtCore.Qt.Key_Escape)
        QtCore.QTimer.singleShot(300, lambda: shiboken6.isValid(popup) and popup.isVisible()
                                 and popup.close())


def clean(text: str) -> str:
    text = (text or "").replace("&&", "\0").replace("&", "").replace("\0", "&")
    return text.split("\t")[0].strip()


def file_for(dialog) -> str:
    """The file a person would pick in this file dialog: one of the run's
    samples to open, or a new name in a scratch folder to save to."""
    QtWidgets = qt()[2]
    files = sample_files()
    filters = " ".join(dialog.nameFilters()).casefold()
    if dialog.acceptMode() == QtWidgets.QFileDialog.AcceptSave:
        ext = ".png" if "png" in filters and "pdf" not in filters else (
            ".csv" if "csv" in filters else ".pdf")
        if dialog.fileMode() == QtWidgets.QFileDialog.Directory:
            return files["dir"]
        return os.path.join(files["dir"], f"saved_{int(time.time() * 1000) % 10 ** 8}{ext}")
    if dialog.fileMode() == QtWidgets.QFileDialog.Directory:
        return files["dir"]
    for kind in ("xlsx", "png", "pdf"):
        if kind in filters or (kind == "png" and "image" in filters):
            return files[kind]
    return files["pdf"]


def default_button(dialog):
    QtWidgets = qt()[2]
    boxes = dialog.findChildren(QtWidgets.QDialogButtonBox)
    for box in boxes:
        for which in (QtWidgets.QDialogButtonBox.Ok, QtWidgets.QDialogButtonBox.Save,
                      QtWidgets.QDialogButtonBox.Yes, QtWidgets.QDialogButtonBox.Apply):
            button = box.button(which)
            if button is not None and button.isVisible() and button.isEnabled():
                return button
        for button in box.buttons():
            if box.buttonRole(button) == QtWidgets.QDialogButtonBox.AcceptRole and \
                    button.isVisible():
                return button
    for button in dialog.findChildren(QtWidgets.QPushButton):
        if button.isDefault() and button.isVisible() and button.isEnabled():
            return button
    if isinstance(dialog, QtWidgets.QMessageBox):
        return dialog.defaultButton()
    return None


def describe_dialog(dialog) -> dict:
    QtWidgets = qt()[2]
    labels, fields = [], []
    for label in dialog.findChildren(QtWidgets.QLabel):
        if label.isVisibleTo(dialog) and clean(label.text()) and not label.text().startswith("<"):
            labels.append(clean(label.text())[:80])
        elif label.isVisibleTo(dialog) and label.text().startswith("<"):
            plain = re.sub(r"<[^>]+>", " ", label.text())
            if plain.strip():
                labels.append(re.sub(r"\s+", " ", plain).strip()[:80])
    for box in dialog.findChildren(QtWidgets.QGroupBox):
        if box.isVisibleTo(dialog) and box.title():
            labels.append(f"[{clean(box.title())}]")
    for widget in dialog.findChildren(QtWidgets.QAbstractButton):
        if widget.isVisibleTo(dialog) and clean(widget.text()):
            fields.append(f"{type(widget).__name__.replace('Q', '', 1)}:{clean(widget.text())}")
    size = QtWidgets.QWidget.size(dialog)          # a dialog may have its own `size`
    return dict(title=QtWidgets.QWidget.windowTitle(dialog), cls=type(dialog).__name__,
                labels=labels[:40], buttons=fields[:40], size=[size.width(), size.height()])


# ---------------------------------------------------------------------------
# pictures
# ---------------------------------------------------------------------------
SHOTS = {"dir": None, "n": 0, "prefix": ""}
# Before/after pictures and their diff: the contact sheets need them, the
# test suite (which judges only exceptions, hangs and undo) does not, and they
# are a third of a run's time.
PICTURES = True


def save_shot(image, tag: str) -> str:
    if not SHOTS["dir"]:
        return ""
    SHOTS["n"] += 1
    name = f"{SHOTS['prefix']}_{tag}{SHOTS['n']}.png"
    path = os.path.join(SHOTS["dir"], name)
    image.save(path)
    return name


def as_array(image):
    import numpy as np
    QtGui = qt()[1]
    image = image.convertToFormat(QtGui.QImage.Format_RGB32)
    width, height = image.width(), image.height()
    data = np.frombuffer(image.constBits(), np.uint8).reshape(height, image.bytesPerLine())
    return data[:, :width * 4].reshape(height, width, 4)[:, :, :3].astype(np.int16)


def diff_box(before, after, ignore=None):
    """The box of what changed (x, y, w, h) in 16-pixel cells, or None."""
    import numpy as np
    if before.shape != after.shape:
        return (0, 0, after.shape[1], after.shape[0]), 1.0
    changed = np.abs(before - after).max(axis=2) > 24
    if ignore is not None:
        x, y, w, h = ignore
        changed[y:y + h, x:x + w] = False
    if not changed.any():
        return None, 0.0
    ys, xs = np.nonzero(changed)
    share = float(changed.mean())
    return (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1),
            int(ys.max() - ys.min() + 1)), share


# ---------------------------------------------------------------------------
# the document, as a comparable record
# ---------------------------------------------------------------------------
VOLATILE = {"uid", "modified", "created", "date", "doc_id", "revision", "their_box",
            "still_theirs", "time", "timestamp", "stamp_time"}


def _normal(value):
    if isinstance(value, dict):
        return {k: _normal(v) for k, v in sorted(value.items()) if k not in VOLATILE}
    if isinstance(value, (list, tuple)):
        return [_normal(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (float, int)):
        return round(float(value), 1)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def doc_signature(win, skip_scale=False) -> str:
    try:
        data = win.document.to_dict()
    except Exception as error:  # noqa: BLE001
        return f"<to_dict raised {error!r}>"
    if skip_scale:
        for page in data.get("pages", []):
            page.pop("scale", None)
    return json.dumps(_normal(data), sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# keeping the window the way it started
# ---------------------------------------------------------------------------
BASELINE = None


def chrome_state(win) -> dict:
    QtGui = qt()[1]
    checks = {}
    tool_ids = {id(a) for a in getattr(win, "tool_actions", {}).values()}
    for action in win.findChildren(QtGui.QAction):
        if action.isCheckable() and id(action) not in tool_ids and action.objectName() != "":
            checks[action.objectName()] = action.isChecked()
    for name, value in vars(win).items():
        if name.startswith("act_") and isinstance(value, QtGui.QAction) and value.isCheckable():
            checks[name] = value.isChecked()
    docks = {d.objectName(): (d.isVisible(), d.isFloating(), getattr(d, "pinned", False),
                              getattr(d, "collapsed", False)) for d in win.panels}
    bars = {b.objectName() or b.windowTitle(): b.isVisible() for b in win.toolbars}
    # every other switch too (View ▸ Single Page and its group have no name)
    loose = [(action, action.isChecked()) for action in win.findChildren(QtGui.QAction)
             if action.isCheckable() and id(action) not in tool_ids
             and not action.objectName() and action.actionGroup() is not None]
    # Maths panel sections opened or rolled up (their headers are buttons too)
    sections = {id(b): b.isChecked() for b in win.findChildren(
        qt()[2].QToolButton, "mathsSectionHeader")}
    return dict(checks=checks, docks=docks, bars=bars, loose=loose, sections=sections)


def restore_chrome(win) -> list[str]:
    """Put the window's switches, panels and toolbars back; say what moved."""
    QtGui = qt()[1]
    moved = []
    now = chrome_state(win)
    for name, was in BASELINE["checks"].items():
        if now["checks"].get(name, was) != was:
            action = getattr(win, name, None) if name.startswith("act_") else \
                win.findChild(QtGui.QAction, name)
            if action is not None:
                moved.append(name)
                try:
                    # as a person flips it, so what listens to triggered hears it too
                    group = action.actionGroup()
                    if group is None or not group.isExclusive() or was:
                        action.trigger()
                    if action.isChecked() != was:
                        action.setChecked(was)
                except Exception:  # noqa: BLE001
                    pass
    import shiboken6
    for action, was in BASELINE.get("loose", []):
        if shiboken6.isValid(action) and was and not action.isChecked():
            moved.append(clean(action.text()))
            action.trigger()                   # the one that was on comes back on
    for header in win.findChildren(qt()[2].QToolButton, "mathsSectionHeader"):
        was = BASELINE.get("sections", {}).get(id(header))
        if was is not None and header.isChecked() != was:
            moved.append(f"maths section {header.text()}")
            header.setChecked(was)             # toggled: the section opens or rolls up
    if now["docks"] != BASELINE["docks"] or now["bars"] != BASELINE["bars"]:
        moved.append("layout")
        try:
            win.reset_layout()
            for name, (visible, floating, _pinned, _rolled) in BASELINE["docks"].items():
                dock = win.findChild(qt()[2].QDockWidget, name)
                if dock is not None:
                    dock.setFloating(floating)
                    dock.setVisible(visible)
        except Exception:  # noqa: BLE001
            pass
    return moved


def close_strays(win) -> list[str]:
    import shiboken6
    QtWidgets = qt()[2]
    from calcforge.ui.mainwindow import MainWindow
    closed = []
    for _ in range(4):
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is None:
            break
        closed.append(f"popup {type(popup).__name__}")
        popup.close()
        pump()
    for _ in range(4):
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is None:
            break
        closed.append(f"dialog {qt()[2].QWidget.windowTitle(modal)}")
        if isinstance(modal, QtWidgets.QDialog):
            modal.reject()
        modal.close()
        pump()
    if getattr(win, "_split_host", None) is not None:
        closed.append("split view")
        try:
            win.act_split_view.setChecked(False)
            if win._split_host is not None:
                win._split_host.unsplit(win)
        except Exception:  # noqa: BLE001
            pass
        pump()
    # One window at a time, from a fresh list each time: closing one can free
    # others there and then, and a list taken before still holds them. The
    # workers that crashed in this loop (R0275, D0003, gate on eebcff1) were
    # the app's: the Markup Styles bar left freed buttons in the
    # application's window list (fixed in 3ec54f1).
    handled = set()
    for _ in range(40):
        stray = None
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if not shiboken6.isValid(widget) or id(widget) in handled:
                continue
            if widget is win or widget is toplevel(win) or not widget.isVisible():
                continue
            if isinstance(widget, (QtWidgets.QDockWidget, QtWidgets.QMenu)) or \
                    type(widget).__name__ in ("QToolTip", "QTipLabel"):
                continue
            if isinstance(widget, MainWindow) or widget.isWindow():
                stray = widget
                break
        if stray is None:
            break
        handled.add(id(stray))
        if isinstance(stray, MainWindow):
            closed.append("second window")
            dispose(stray)
        else:
            closed.append(f"window {type(stray).__name__} {stray.windowTitle()}")
            stray.close()
            if stray.isVisible():
                stray.hide()              # one that will not close is not asked twice
            pump()
    pump()
    return closed


def forget_settings(win) -> list[str]:
    """Every command starts from the shipped settings, as each test does under
    the suite's conftest: what an earlier command saved (a tool set made or
    hidden, a default style, Name Tags) is wiped, and the Tool Chest, which
    reads its sets from the settings, is redrawn from them."""
    from calcforge.settings import app_settings
    from calcforge.ui import toolsets
    settings = app_settings()
    notes = []
    if settings.allKeys():
        settings.clear()
        settings.sync()
        notes.append("settings")
    # the chest holds its sets in memory too: under the test suite the settings
    # are wiped before each test, so compare what it shows with what is stored
    panel = getattr(win, "toolsets_panel", None)
    if panel is not None:
        try:
            shown = [group.to_dict() for group in getattr(panel, "groups", [])]
            stored = [group.to_dict() for group in toolsets.load_toolsets()]
            if shown != stored:
                panel.rebuild()
                notes.append("tool sets")
        except Exception:  # noqa: BLE001
            pass
    return notes


def reset(win) -> list[str]:
    """A fresh document in a window the way it started."""
    notes = close_strays(win)
    try:
        while len(getattr(win, "_open_documents", [])) > 1:
            win.close_document_tab(len(win._open_documents) - 1)
    except Exception as error:  # noqa: BLE001
        notes.append(f"closing tabs: {error!r}")
    notes += restore_chrome(win)
    notes += forget_settings(win)
    if "dimmer" in _RESTORE:
        from calcforge.ui import scene as scene_module
        if scene_module.DIMMER != _RESTORE["dimmer"]:
            notes.append("dimmer")
            restore_globals()
            win.view.viewport().update()
    if win.isFullScreen() or win.isMaximized() or win.isMinimized():
        win.showNormal()
        notes.append("window state")
    if win.size().width() != 1280 or win.size().height() != 860:
        win.resize(1280, 860)
    try:
        win.view.escape_everything()
    except Exception:  # noqa: BLE001
        pass
    if getattr(win, "_offset", None) is not None:
        # an Offset left waiting outlives a new document and crashes the next
        # drawing (finding in exercise_round1.md): end it the way a person does
        notes.append("offset session left open")
        QtCore, QTest = qt()[0], qt()[3]
        QTest.keyClick(win.view.viewport(), QtCore.Qt.Key_Escape)
        pump()
        if getattr(win, "_offset", None) is not None:
            try:
                win._offset.finish()
            except Exception:  # noqa: BLE001
                pass
            win._offset = None
    # what the Properties toolbar set with nothing selected is the window's
    # own (the next markup's look): one job's hatch or line style must not
    # be the next job's fixture's (D0036 found a rectangle drawn hatched)
    from calcforge.items.base import Style
    if getattr(win, "default_style", None) is not None and \
            win.default_style.to_dict() != Style().to_dict():
        win.default_style = Style()
        notes.append("default style")
    if getattr(win, "default_cloud_size", 2.0) != 2.0:
        win.default_cloud_size = 2.0
        notes.append("cloud size")
    win._measure_units_next = None
    win.interactive_prompts = False
    win.new_document(confirm=False)
    win.view.set_zoom(1.0)
    win.select_tool("select")
    APP.clipboard().clear()
    activate(win)
    # Edit > Undo stays greyed after Undo then New (finding in exercise_round1.md):
    # refresh it here so every later command is judged on its own
    refresh = getattr(win, "_refresh_undo_actions", None)
    if refresh is not None:
        stack = win.undo_stack
        if not getattr(stack, "_exercise_hooked", False):
            stack.indexChanged.connect(lambda *_a, w=win, st=stack: _refresh_quietly(w, st))
            stack._exercise_hooked = True
        refresh()
    return notes


def _refresh_quietly(win, stack):
    import shiboken6
    if shiboken6.isValid(win) and shiboken6.isValid(stack) and win.undo_stack is stack:
        win._refresh_undo_actions()


def toplevel(widget):
    """The top-level window of *widget* (MainWindow has its own `window`)."""
    return qt()[2].QWidget.window(widget)


def activate(win):
    """The window has to be the active one, or no shortcut reaches it (after
    a dialog closes the offscreen platform does not give it back)."""
    QtWidgets = qt()[2]
    win.raise_()
    win.activateWindow()
    pump()
    if QtWidgets.QApplication.activeWindow() is not toplevel(win):
        handle = toplevel(win).windowHandle()
        if handle is not None:
            handle.requestActivate()
        pump()
    if QtWidgets.QApplication.activeWindow() is not toplevel(win):
        QtWidgets.QApplication.setActiveWindow(toplevel(win))
        pump()


# ===========================================================================
# 3. fixtures: the states commands run in
# ===========================================================================
def page_point(win, x, y, page=0):
    QtCore = qt()[0]
    frame = win.document.pages[page].frame
    return frame.mapToScene(QtCore.QPointF(x, y))


def view_point(win, scene_point):
    return win.view.mapFromScene(scene_point)


def look_at(win, x=300, y=260, page=0):
    """Put the fixtures' corner of the page in the middle of the view."""
    win.view.set_zoom(1.0)
    win.view.centerOn(page_point(win, x, y, page))
    pump()


def markups(win):
    return win.view.scene().ordered_markups()


def gesture(win, tool, mode, a, b, extra=()):
    """Draw with *tool* the way its mode is drawn, between page points a and b."""
    from tests.test_usability import click, double_click, drag, press_key
    from calcforge.ui.tools import ANCHOR, CLICK, CLOUD, CLOUDY, DRAG, FREE, POLY
    QtCore = qt()[0]
    view = win.view
    p, q = page_point(win, *a), page_point(win, *b)
    if tool is not None:
        win.select_tool(tool)
    if mode in (DRAG, CLOUDY, FREE, "snapshot", "table"):
        drag(view, p.x(), p.y(), q.x(), q.y())
    elif mode == POLY:
        click(view, p.x(), p.y())
        click(view, q.x(), p.y())
        double_click(view, q.x(), q.y())
    elif mode == CLICK:
        click(view, p.x(), p.y())
        for point in extra:
            r = page_point(win, *point)
            click(view, r.x(), r.y())
    elif mode == ANCHOR:
        click(view, p.x(), p.y())
        click(view, q.x(), q.y())
    elif mode == CLOUD:
        drag(view, p.x(), p.y(), q.x(), q.y())
        r = page_point(win, b[0] + 40, b[1] + 40)
        click(view, r.x(), r.y())
    pump()
    return p, q


def draw(win, tool_key, a=(100, 100), b=(230, 180), text=None, extra=()):
    from tests.test_usability import press_key, type_text
    from calcforge.ui.tools import TOOLS
    QtCore = qt()[0]
    tool = next(t for t in TOOLS if t.key == tool_key)
    before = {id(i) for i in markups(win)}
    gesture(win, tool_key, tool.mode, a, b, extra)
    if win.view._editing_item is not None:
        type_text(win.view, text or "Words")
    press_key(win.view, QtCore.Qt.Key_Escape)
    press_key(win.view, QtCore.Qt.Key_Escape)
    win.select_tool("select")
    pump()
    new = [i for i in markups(win) if id(i) not in before]
    return new


def pick(win, items):
    scene = win.view.scene()
    scene.clearSelection()
    for item in items:
        item.setSelected(True)
    pump()


def centre_of(item):
    if hasattr(item, "local_rect"):
        return item.mapToScene(item.local_rect().center())
    return item.sceneBoundingRect().center()


def make_table(win, values=True, x=72, y=320):
    from tests.test_tables import make_table as _make, type_text, enter
    table = _make(win, x=x, y=y)
    if values:
        win.view.tables.open(table)
        for row, words in enumerate((("3", "Beam"), ("5", "Joist"), ("4", "Post"))):
            for col, word in enumerate(words):
                win.view.tables.select((row, col))
                type_text(win, word)
                enter(win)
        win.view.tables.close()
    pump()
    return table


def an_equation(win, text, x=100, y=120):
    from tests.test_calc_panels import an_equation as _eq
    return _eq(win, text, x, y)


def equations(win):
    from calcforge.items.calc import CalcItem
    return [i for i in win.view.scene().items() if isinstance(i, CalcItem)]


def sample_files() -> dict:
    """A PDF, a picture and a workbook to open, made once per run."""
    folder = os.path.join(tempfile.gettempdir(), f"calcforge-exercise-files-{os.getpid()}")
    files = {"pdf": os.path.join(folder, "drawing.pdf"), "png": os.path.join(folder, "pic.png"),
             "xlsx": os.path.join(folder, "book.xlsx"), "dir": folder}
    if os.path.exists(files["xlsx"]):
        return files
    os.makedirs(folder, exist_ok=True)
    import fitz
    doc = fitz.open()
    for n in range(2):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Sheet {n + 1}: beam TBC, column TBC", fontsize=14)
        page.draw_rect(fitz.Rect(72, 150, 400, 400), color=(0.1, 0.1, 0.6), width=1.5)
        page.draw_line(fitz.Point(72, 450), fitz.Point(500, 450), color=(0.8, 0, 0), width=2)
        if n == 0:
            annot = page.add_rect_annot(fitz.Rect(420, 150, 520, 220))
            annot.set_colors(stroke=(1, 0, 0))
            annot.update()
    doc.save(files["pdf"])
    QtGui = qt()[1]
    image = QtGui.QImage(160, 100, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor("#4a90d9"))
    image.save(files["png"])
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Beams"
    for r, row in enumerate([("Beam", "Length"), ("B1", 3), ("B2", 5), ("B3", 4)], 1):
        for c, v in enumerate(row, 1):
            sheet.cell(r, c, v)
    sheet.cell(5, 2, "=SUM(B2:B4)")
    book.create_sheet("Notes").cell(1, 1, "TBC")
    book.save(files["xlsx"])
    return files


def fx_fresh(win):
    look_at(win)
    return dict(point=page_point(win, 420, 560))


def _one(tool_key, a=(100, 100), b=(230, 180), text=None, extra=()):
    def fixture(win):
        look_at(win)
        items = draw(win, tool_key, a, b, text, extra)
        if not items:
            raise RuntimeError(f"drawing with {tool_key} made nothing")
        pick(win, items[:1])
        return dict(item=items[0], items=items, point=centre_of(items[0]))
    return fixture


def fx_two_rects(win):
    look_at(win)
    first = draw(win, "rect", (100, 100), (200, 170))
    second = draw(win, "rect", (260, 130), (380, 210))
    pick(win, first + second)
    return dict(item=first[0], items=first + second, point=centre_of(first[0]))


def fx_group(win):
    ctx = fx_two_rects(win)
    win.act_group.trigger()
    pump()
    group = [i for i in markups(win) if i.isSelected()]
    ctx["items"] = group
    ctx["item"] = group[0] if group else ctx["item"]
    ctx["point"] = centre_of(ctx["item"])
    return ctx


def fx_hidden(win):
    ctx = _one("rect")(win)
    win.act_hide.trigger()
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_flattened(win):
    ctx = _one("rect")(win)
    win.act_flatten.trigger()
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_copied(win):
    ctx = _one("rect")(win)
    win.act_copy.trigger()
    win.view.scene().clearSelection()
    pump()
    return dict(point=page_point(win, 420, 420))


def fx_undoable(win):
    _one("rect")(win)
    win.view.scene().clearSelection()
    return dict(point=page_point(win, 420, 560))


def fx_redoable(win):
    _one("rect")(win)
    win.view.scene().clearSelection()
    win.undo_something()
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_counts(win):
    look_at(win)
    items = draw(win, "count", (100, 100), (100, 100), extra=[(160, 100), (220, 100), (280, 100)])
    if len(items) >= 3:
        pick(win, [items[1]])
        win.act_delete.trigger()
        pump()
    left = [i for i in markups(win)]
    if left:
        pick(win, left[:1])
    return dict(item=left[0] if left else None, items=left,
                point=centre_of(left[0]) if left else page_point(win, 100, 100))


def fx_misspelt(win):
    return _one("text", (100, 100), (300, 150), text="Teh beam is TBC")(win)


def fx_two_pages(win, current=0, picked=False, count=2):
    for _ in range(count - 1):
        win.add_page()
        pump()
    win.go_to_page(current)
    look_at(win, page=current)
    if picked:
        strip = win.pages_panel.list
        strip.clearSelection()
        for r in range(min(2, strip.count())):
            strip.item(r).setSelected(True)
    show_dock(win, "Thumbnails")
    return dict(point=page_point(win, 420, 560, current), page=current)


def fx_two_pages_labelled(win):
    """Two pages, both renamed (S-101, S-102): what the label resets undo."""
    ctx = fx_two_pages(win)
    win.set_page_label(0, "S-101")
    win.set_page_label(1, "S-102")
    pump()
    win.go_to_page(0)
    return ctx


def fx_pages_copied(win):
    ctx = fx_two_pages(win)
    menu = win.page_menu(0)
    action = find_action(menu.actions(), "Copy Pages")
    if action is not None:
        action.trigger()
    pump()
    return ctx


def fx_table_open(win, a1="B2"):
    from tests.test_tables import cell_scene
    look_at(win, 300, 400)
    table = make_table(win)
    win.view.tables.open(table)
    point = cell_scene(table, a1)
    win.view.centerOn(point)
    from tests.test_tables import click as tclick
    tclick(win, point)
    pump()
    return dict(item=table, table=table, point=cell_scene(table, a1))


def fx_table_range(win):
    from tests.test_tables import cell_scene
    ctx = fx_table_open(win, "A1")
    win.view.tables.select((0, 0), (2, 0)) if _takes_two(win.view.tables.select) else None
    pump()
    return ctx


def _takes_two(fn):
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 2
    except (TypeError, ValueError):
        return False


def fx_table_closed(win):
    look_at(win, 300, 400)
    table = make_table(win)
    pick(win, [table])
    return dict(item=table, table=table, point=centre_of(table))


def fx_table_filtered(win):
    ctx = fx_table_open(win, "A1")
    from calcforge.ui import datatools
    datatools.toggle_filter(win.view.tables)
    pump()
    return ctx


def fx_table_commented(win):
    ctx = fx_table_open(win, "B2")
    from calcforge.ui import datatools
    datatools.set_comment(win.view.tables, "Check this")
    pump()
    return ctx


def fx_calc_page2(win):
    ctx = fx_two_pages(win, current=1)
    win.toggle_calc_mode(True)
    pump()
    return ctx


def fx_viewport(win):
    from calcforge.core.document import Viewport
    look_at(win)
    page = win.document.pages[0]
    page.viewports.append(Viewport(name="Detail", x=80, y=80, width=240, height=160))
    try:
        win.page_panel.refresh()
    except Exception:  # noqa: BLE001
        pass
    show_dock(win, "Page Setup")
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_chart(win):
    ctx = fx_table_range(win)
    win.insert_chart()
    pump()
    from calcforge.items.chart import ChartItem
    charts = [i for i in win.view.scene().items() if isinstance(i, ChartItem)]
    win.view.tables.close()
    if charts:
        pick(win, charts[:1])
        ctx.update(item=charts[0], point=centre_of(charts[0]))
    return ctx


def fx_sheet_open(win, a1="C5"):
    from tests.test_sheet_pages import sheet_page, open_at
    from tests.test_tables import cell_scene, type_text, enter
    run = sheet_page(win)
    open_at(win, run, "A1")
    for row, words in enumerate((("Beam", "3"), ("Joist", "5"), ("Post", "4"))):
        for col, word in enumerate(words):
            win.view.tables.select((row, col))
            type_text(win, word)
            enter(win)
    open_at(win, run, a1)
    return dict(item=run, table=run, point=cell_scene(run, a1))


def fx_sheet_break(win):
    """A spreadsheet page with a manual page break above row 3, the active
    cell on it: what Remove Page Break takes away."""
    ctx = fx_sheet_open(win, "A3")
    win.insert_page_break()
    pump()
    return ctx


def fx_calc_mode(win):
    from tests.test_usability import click
    look_at(win)
    win.toggle_calc_mode(True)
    p = page_point(win, 120, 140)
    click(win.view, p.x(), p.y())
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_equation(win):
    look_at(win)
    item = an_equation(win, "a:2")
    pump()
    pick(win, [item])
    return dict(item=item, point=centre_of(item))


def fx_equations(win):
    look_at(win)
    first = an_equation(win, "a:2")
    second = an_equation(win, "b:a+1", 100, 170)
    third = an_equation(win, "b*3=", 100, 220)
    pump()
    return dict(item=third, items=[first, second, third], point=page_point(win, 420, 560))


def fx_matrix_eq(win):
    """An equation being typed, the caret after its operand: what Invert,
    Determinant and Solve work on (they act on the selection or the operand
    under the caret, so a picked but closed equation gives them nothing)."""
    from tests.test_calc_modes import into_calc_mode, typed
    look_at(win)
    into_calc_mode(win, 100, 140)
    typed(win, "M:4")
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_two_equations(win):
    look_at(win)
    first = an_equation(win, "a:2")
    second = an_equation(win, "a+1=", 100, 200)
    win.toggle_calc_mode(False)
    pick(win, [first, second])
    return dict(item=first, items=[first, second], point=centre_of(first))


def fx_equation_editing(win):
    from tests.test_calc_modes import into_calc_mode, typed
    look_at(win)
    into_calc_mode(win, 100, 140)
    typed(win, "x:3")
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_calc_block(win):
    ctx = fx_two_equations(win)
    win.insert_block()
    pump()
    from calcforge.items.calc import CalcBlockItem
    blocks = [i for i in win.view.scene().items() if isinstance(i, CalcBlockItem)]
    if blocks:
        pick(win, blocks[:1])
        return dict(item=blocks[0], point=centre_of(blocks[0]))
    return ctx


def fx_calc_text(win):
    from tests.test_usability import click, press_key, type_text
    QtCore = qt()[0]
    look_at(win)
    an_equation(win, "a:2")                     # a variable for Insert Field ▸ Variable
    win.toggle_calc_mode(True)
    p = page_point(win, 100, 300)
    click(win.view, p.x(), p.y())
    win.insert_calc_text()
    type_text(win.view, "Words here")
    press_key(win.view, QtCore.Qt.Key_Escape)
    press_key(win.view, QtCore.Qt.Key_Escape)
    pump()
    from calcforge.items.calc import CalcTextItem
    texts = [i for i in win.view.scene().items() if isinstance(i, CalcTextItem)]
    if texts:
        pick(win, texts[:1])
        return dict(item=texts[0], point=centre_of(texts[0]))
    return dict(point=p)


def fx_textbox_editing(win):
    from tests.test_usability import double_click
    ctx = _one("text", (100, 100), (300, 150), text="Note")(win)
    p = ctx["point"]
    double_click(win.view, p.x(), p.y())
    pump()
    return ctx


def fx_pdf_page(win):
    files = sample_files()
    win.open_from_command_line(files["pdf"])
    pump(3)
    look_at(win)
    return dict(point=page_point(win, 300, 600))


def fx_rulers(win):
    win.act_rulers.setChecked(True)
    pump()
    look_at(win)
    return dict(point=page_point(win, 420, 560))


def fx_bookmarked(win):
    win.add_page()
    pump()
    win.go_to_page(0)
    # the way Add Bookmark files one, without its name prompt
    win.document.add_bookmark("Beams", 0, 0.0)
    win.document.add_bookmark("Joists", 1, 0.0)
    win.bookmarks_changed()
    show_dock(win, "Bookmarks")
    pump()
    panel = getattr(win, "bookmarks_panel", None)
    tree = getattr(panel, "tree", None) if panel is not None else None
    if tree is not None and tree.topLevelItemCount():
        tree.setCurrentItem(tree.topLevelItem(0))   # Rename / Delete act on a picked one
    look_at(win)
    return dict(point=page_point(win, 420, 560))


def fx_markups_list(win):
    ctx = _one("rect")(win)
    draw(win, "ellipse", (260, 120), (360, 200))
    if not win.markups_panel.isVisible():
        win.act_markups_list.trigger()
    pump()
    pick(win, [ctx["item"]])
    return ctx


def fx_variables(win):
    ctx = fx_equations(win)
    show_dock(win, "Variables")
    pump()
    return ctx


def fx_toolchest(win):
    show_dock(win, "Tool Chest")
    look_at(win)
    return dict(point=page_point(win, 420, 560))


def fx_note(win):
    return _one("note", (150, 150), (150, 150))(win)


def fx_plot(win):
    ctx = fx_calc_mode(win)
    win.insert_plot()
    pump()
    return ctx


def fx_section(win):
    fx_two_pages(win)
    return dict(point=page_point(win, 420, 560))


def fx_image(win):
    look_at(win)
    files = sample_files()
    from calcforge.items.media import ImageItem
    QtCore = qt()[0]
    item = ImageItem(rect=QtCore.QRectF(0, 0, 160, 100))
    item.asset_key = win.document.add_asset(open(files["png"], "rb").read(), "png")
    item.load_from_document(win.document)
    win.document.pages[0].frame.add_markup(item, QtCore.QPointF(100, 100))
    pump()
    pick(win, [item])
    return dict(item=item, point=centre_of(item))


def fx_styles(win):
    """Two saved Markup Styles for the rectangle, the tool held."""
    from calcforge.ui import markupstyles
    markupstyles.set_styles_for("rect", [])
    look_at(win)
    win.select_tool("rect")
    pump()
    win.markup_styles.add_style("First")
    win.markup_styles.add_style("Second")
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_styles_selected(win):
    ctx = _one("rect")(win)
    from calcforge.ui import markupstyles
    markupstyles.set_styles_for("rect", [])
    win.select_tool("rect")
    win.markup_styles.add_style("First")
    win.select_tool("select")
    pick(win, [ctx["item"]])
    win.select_tool("rect")
    pump()
    return ctx


def fx_count_tool(win):
    look_at(win)
    win.select_tool("count")
    pump()
    return dict(point=page_point(win, 420, 560))


def fx_section_break(win):
    fx_two_pages(win)
    win.document.pages[1].section_break = True
    win.document.pages[1].section_title = "Part 2"
    pump()
    return dict(point=page_point(win, 420, 560, 1), page=1)


def fx_plot_item(win):
    fx_calc_mode(win)
    win.insert_plot()
    pump()
    from tests.test_usability import press_key
    press_key(win.view, qt()[0].Qt.Key_Escape)
    pump()
    from calcforge.items.calc import CalcItem
    plots = [i for i in win.view.scene().items() if isinstance(i, CalcItem)
             and getattr(i.region, "plot", None) is not None]
    if plots:
        pick(win, plots[:1])
        return dict(item=plots[0], point=centre_of(plots[0]))
    return dict(point=page_point(win, 420, 560))


def fx_table_copied(win):
    ctx = fx_table_open(win, "A1")
    from tests.test_tables import cell_scene
    win.view.tables.select((0, 0))
    win.view.tables.copy()
    win.view.tables.select((1, 3))
    pump()
    ctx["point"] = cell_scene(ctx["table"], "D2")
    return ctx


def fx_sheet_copied(win):
    ctx = fx_sheet_open(win, "A1")
    win.view.tables.select((0, 0))
    win.view.tables.copy()
    win.view.tables.select((4, 2))
    pump()
    return ctx


FIXTURES = {
    "fresh": fx_fresh,
    "rect": _one("rect"),
    "ellipse": _one("ellipse"),
    "line": _one("line", (100, 100), (260, 170)),
    "cloud": _one("cloud"),
    "textbox": _one("text", (100, 100), (300, 150), text="Hello world"),
    "callout": _one("callout", (100, 220), (220, 120), text="Callout"),
    "link": _one("link"),
    "length": _one("measure_length", (100, 300), (320, 300)),
    "note": fx_note,
    "two_rects": fx_two_rects,
    "group": fx_group,
    "hidden": fx_hidden,
    "flattened": fx_flattened,
    "copied": fx_copied,
    "undoable": fx_undoable,
    "redoable": fx_redoable,
    "redact": _one("redact"),
    "counts": fx_counts,
    "misspelt": fx_misspelt,
    "two_pages": fx_two_pages,
    "two_pages_labelled": fx_two_pages_labelled,
    "sheet_break": fx_sheet_break,
    "two_pages_second": lambda w: fx_two_pages(w, current=1),
    "two_pages_picked": lambda w: fx_two_pages(w, picked=True),
    "three_pages": lambda w: fx_two_pages(w, current=1, count=3),
    "table_open": fx_table_open,
    "pages_copied": fx_pages_copied,
    "table_commented": fx_table_commented,
    "calc_page2": fx_calc_page2,
    "viewport": fx_viewport,
    "table_range": fx_table_range,
    "table_closed": fx_table_closed,
    "table_filtered": fx_table_filtered,
    "chart": fx_chart,
    "sheet_open": fx_sheet_open,
    "calc_mode": fx_calc_mode,
    "equation": fx_equation,
    "equations": fx_equations,
    "matrix_eq": fx_matrix_eq,
    "two_equations": fx_two_equations,
    "equation_editing": fx_equation_editing,
    "calc_block": fx_calc_block,
    "calc_text": fx_calc_text,
    "textbox_editing": fx_textbox_editing,
    "pdf_page": fx_pdf_page,
    "rulers": fx_rulers,
    "bookmarked": fx_bookmarked,
    "markups_list": fx_markups_list,
    "variables": fx_variables,
    "toolchest": fx_toolchest,
    "plot": fx_plot,
    "section": fx_section,
    "image": fx_image,
    "styles": fx_styles,
    "styles_selected": fx_styles_selected,
    "count_tool": fx_count_tool,
    "section_break": fx_section_break,
    "plot_item": fx_plot_item,
    "table_copied": fx_table_copied,
    "sheet_copied": fx_sheet_copied,
    "stamp": _one("stamp"),
    "flag": _one("flag", (150, 150), (150, 150)),
    "polyline": _one("polyline", (100, 300), (260, 420)),
    "arc": _one("arc"),
    "arrow": _one("arrow", (100, 100), (260, 170)),
    "highlight": _one("highlight"),
    "area": _one("measure_area", (100, 300), (260, 420)),
    "perimeter": _one("measure_perimeter", (100, 300), (260, 420)),
    "polylength": _one("measure_polylength", (100, 300), (260, 420)),
    "volume": _one("measure_volume", (100, 300), (260, 420)),
    "angle": _one("measure_angle", (100, 300), (260, 420)),
    "radius": _one("measure_radius", (100, 300), (220, 380)),
    "diameter": _one("measure_diameter", (100, 300), (220, 380)),
    "cloudplus": _one("cloud_callout", text="Cloud words"),
    "contents": _one("contents"),
    "pen": _one("pen"),
    "highlighter": _one("highlighter"),
}
FIXTURES["auto"] = fx_fresh
FALLBACK_STATES = ["fresh", "rect", "two_rects", "textbox", "two_pages", "equation",
                   "table_open", "sheet_open", "calc_mode", "pdf_page"]


def show_dock(win, title):
    for dock in win.panels:
        if dock.windowTitle() == title:
            if not dock.isVisible():
                dock.show()
            dock.raise_()
            try:
                dock.set_collapsed(False)
            except Exception:  # noqa: BLE001
                pass
            pump()
            return dock
    return None


# ===========================================================================
# 4. reaching a command the way a person does
# ===========================================================================
class NotReached(Exception):
    """The command could not be found or was disabled where a person looks."""


def find_action(actions, label):
    want = norm(label)
    visible = [a for a in actions if not a.isSeparator() and a.isVisible()]
    for action in visible:
        if norm(action.text(), True) == want:
            return action
    for action in visible:                       # "[field] …" and "6 choices" rows
        if want and norm(action.text(), True).startswith(want):
            return action
    return None


_LAST_CLICK = {"widget": None, "at": 0.0}


def click_at(widget, point, button=None, modifiers=None):
    QtCore, QtGui, QtWidgets, QTest = qt()
    QTest.mouseMove(widget, point)
    # A second click on the same button inside the double-click time is a
    # double-click to Qt, and a button's menu then does not open (T0184
    # Borders, then T0185 its All Borders, under -n 3). A hand clicking two
    # different things on one button is never that quick: wait it out.
    delay = -1
    if _LAST_CLICK["widget"] is widget:
        gap = (time.perf_counter() - _LAST_CLICK["at"]) * 1000
        wait = QtWidgets.QApplication.doubleClickInterval() + 20 - gap
        if wait > 0:
            delay = int(wait)
    QTest.mouseClick(widget, button or QtCore.Qt.LeftButton,
                     modifiers or QtCore.Qt.NoModifier, point, delay)
    _LAST_CLICK["widget"] = widget
    _LAST_CLICK["at"] = time.perf_counter()


def walk_popup(path, outcome, each_index=None):
    """In the open popup menu, click through *path*; the last is triggered."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    Watch.navigating = True
    try:
        for depth, label in enumerate(path):
            menu = QtWidgets.QApplication.activePopupWidget()
            if not isinstance(menu, QtWidgets.QMenu):
                outcome["error"] = f"no menu open at '{label}'"
                return False
            remember_menu(menu, outcome)
            last = depth == len(path) - 1
            if label == "*":
                choices = [a for a in menu.actions() if not a.isSeparator() and a.isVisible()]
                if each_index is None or each_index >= len(choices):
                    outcome["choices"] = [clean(a.text()) for a in choices]
                    outcome["error"] = "choice index"
                    close_popups()
                    return False
                action = choices[each_index]
                outcome["choice"] = clean(action.text())
            else:
                action = find_action(menu.actions(), label)
            if action is None:
                outcome["missing"] = label
                outcome["menu_items"] = [clean(a.text()) for a in menu.actions()
                                         if not a.isSeparator() and a.isVisible()]
                close_popups()
                return False
            if not action.isEnabled():
                outcome["disabled"] = label
                close_popups()
                return False
            rect = menu.actionGeometry(action)
            if not point_at(menu, action):
                outcome["error"] = f"the pointer never rested on '{label}'"
                close_popups()
                return False
            if last and outcome.get("open_only"):
                sub = action.menu()
                if sub is not None:
                    wait_for(sub.isVisible, 1.0)
                    if sub.isVisible():
                        remember_menu(sub, outcome)
                        outcome["popup_shot"] = save_shot(sub.grab().toImage(), "submenu")
                close_popups()
                return True
            if last:
                Watch.navigating = False
                outcome["t0"] = CURRENT["t0"] = time.perf_counter()
                QTest.mouseClick(menu, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                                 rect.center())
                return True
            sub = action.menu()
            if sub is not None and not sub.isVisible():
                QTest.mouseClick(menu, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                                 rect.center())
            if sub is not None and not wait_for(sub.isVisible, 1.5):
                outcome["error"] = f"{label} ▸ did not open"
                close_popups()
                return False
        return True
    finally:
        Watch.navigating = False


def wait_for(condition, limit=2.0) -> bool:
    """Process events until *condition()* holds or *limit* seconds pass."""
    deadline = time.perf_counter() + limit
    while not condition():
        if time.perf_counter() > deadline:
            return False
        APP.processEvents()
        time.sleep(0.005)
    return True


def point_at(menu, action) -> bool:
    """Glide the pointer onto *action* in small steps, as a hand does, and wait
    until the menu has it under the pointer. QMenu takes a click only once the
    pointer has moved since it opened (several moves, or more than the drag
    distance): one jump could land too close to where an earlier command left
    the pointer, and the click was ignored (tests/test_sheet_qa_round1.py has
    the same finding, a7656be)."""
    QtCore, QTest = qt()[0], qt()[3]
    rect = menu.actionGeometry(action)
    centre = rect.center()
    for k in range(8, -1, -1):
        QTest.mouseMove(menu, QtCore.QPoint(centre.x() - k * max(1, rect.width() // 20),
                                            centre.y()))
    return wait_for(lambda: menu.activeAction() is action, 1.0)


def back_to_the_window(win, limit=3.0) -> bool:
    """Wait until the keyboard is the window's again after a popup: none left
    showing and the window active. The offscreen platform keeps a closed menu
    as the active window for some events, so a key sent straight after goes
    nowhere (tests/test_markup_interaction_round6.py has the same helper)."""
    QtWidgets = qt()[2]
    deadline = time.perf_counter() + limit
    asked = False
    while True:
        APP.processEvents()
        popup = QtWidgets.QApplication.activePopupWidget() or \
            QtWidgets.QApplication.activeModalWidget()
        if popup is None and QtWidgets.QApplication.activeWindow() is toplevel(win):
            return True
        if time.perf_counter() > deadline:
            if asked:
                return False
            asked = True
            activate(win)
            deadline = time.perf_counter() + limit
        time.sleep(0.005)


def remember_menu(menu, outcome):
    """Each distinct menu is photographed once per run, for the menu sheets."""
    key = (CURRENT.get("menu_key", ""), menu.title() or "",
           tuple(clean(a.text()) for a in menu.actions()[:4]))
    if key in MENUS_SEEN or not SHOTS["dir"]:
        return
    MENUS_SEEN.add(key)
    shot = save_shot(menu.grab().toImage(), "menu")
    CURRENT.setdefault("menus", []).append(dict(title=menu.title(), shot=shot,
                                                items=[clean(a.text()) for a in menu.actions()
                                                       if not a.isSeparator()][:40]))


MENUS_SEEN: set = set()


def close_popups():
    QtWidgets = qt()[2]
    for _ in range(6):
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is None:
            return
        popup.close()
        pump()


def via_menu(win, entry, outcome, each_index=None):
    QtCore, QtGui, QtWidgets, QTest = qt()
    path = entry["path"]
    bar = win.menuBar()
    top = find_action(bar.actions(), path[0])
    if top is None:
        raise NotReached(f"no '{path[0]}' on the menu bar")
    outcome["open_only"] = entry.get("kind") == "submenu"
    Watch.navigating = True
    click_at(bar, bar.actionGeometry(top).center())
    settle(30)
    if len(path) == 1:
        Watch.navigating = False
        return True
    # a menu that is slow to build (Help ▸ Find Tools, on a loaded machine)
    # is waited for, and clicked once more if the first click was lost
    for attempt in range(12):
        if isinstance(QtWidgets.QApplication.activePopupWidget(), QtWidgets.QMenu):
            break
        if attempt == 6:
            activate(win)
            click_at(bar, bar.actionGeometry(top).center())
        settle(40)
    return walk_popup(path[1:], outcome, each_index)


def via_menu_keys(win, entry, outcome, each_index=None):
    """Alt+the menu's letter, then the arrow keys down to the item and Enter
    (Right into a submenu) — the keyboard way through the menu bar."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    path = entry["path"]
    bar = win.menuBar()
    top = find_action(bar.actions(), path[0])
    if top is None:
        raise NotReached(f"no '{path[0]}' on the menu bar")
    letter = re.search(r"&(\w)", top.text())
    Watch.navigating = True
    try:
        if letter:
            QTest.keyClick(win, getattr(QtCore.Qt, f"Key_{letter.group(1).upper()}"),
                           QtCore.Qt.AltModifier)
            outcome["keys"] = f"Alt+{letter.group(1).upper()}"
        else:
            outcome["keys"] = "(no mnemonic) click"
            click_at(bar, bar.actionGeometry(top).center())
        settle(30)
        menu = QtWidgets.QApplication.activePopupWidget()
        if not isinstance(menu, QtWidgets.QMenu):
            outcome["error"] = "Alt+letter opened no menu"
            close_popups()
            return False
        for depth, label in enumerate(path[1:]):
            menu = QtWidgets.QApplication.activePopupWidget()
            items = [a for a in menu.actions() if not a.isSeparator() and a.isVisible()]
            action = find_action(menu.actions(), label) if label != "*" else (
                items[each_index] if each_index is not None and each_index < len(items) else None)
            if action is None:
                outcome["missing"] = label
                close_popups()
                return False
            if not action.isEnabled():
                outcome["disabled"] = label
                close_popups()
                return False
            # arrow down from the top until this item is the active one
            for _ in range(len(menu.actions()) + 2):
                if menu.activeAction() is action:
                    break
                QTest.keyClick(menu, QtCore.Qt.Key_Down)
            if menu.activeAction() is not action:
                outcome["error"] = f"arrow keys never reached '{label}' (disabled items skipped?)"
                close_popups()
                return False
            last = depth == len(path) - 2
            if last and entry.get("kind") == "submenu":
                QTest.keyClick(menu, QtCore.Qt.Key_Right)
                settle(30)
                close_popups()
                return True
            if last:
                Watch.navigating = False
                outcome["t0"] = CURRENT["t0"] = time.perf_counter()
                QTest.keyClick(menu, QtCore.Qt.Key_Return)
                return True
            QTest.keyClick(menu, QtCore.Qt.Key_Right)
            settle(30)
        return True
    finally:
        Watch.navigating = False


def toolbar_named(win, title):
    QtWidgets = qt()[2]
    # the Style bar is Revu's Properties toolbar now (propbar.py, a9cdcd2);
    # a commands.json built when it was still called Style still finds it
    names = {title, {"Style": "Properties"}.get(title, title)}
    for bar in win.findChildren(QtWidgets.QToolBar):
        if bar.windowTitle() in names:
            return bar
    raise NotReached(f"no toolbar '{title}'")


def describe(widget):
    return inventory().describe_widget(widget)


_INVENTORY = None


def inventory():
    """tools/qa/inventory.py, for its widget walkers. It stubs out every file
    dialog, input box and message box when imported (it must never block);
    here those are wanted for real, so they are put back."""
    global _INVENTORY
    if _INVENTORY is None:
        from PySide6.QtWidgets import QColorDialog, QFileDialog, QInputDialog, QMessageBox
        saved = {(cls, name): cls.__dict__.get(name) for cls in (
            QFileDialog, QInputDialog, QMessageBox, QColorDialog) for name in (
            "getOpenFileName", "getOpenFileNames", "getSaveFileName", "getExistingDirectory",
            "getText", "getItem", "getInt", "getDouble", "getColor", "information",
            "warning", "question", "critical")}
        environ = dict(os.environ)
        from tools.qa import inventory as module
        for (cls, name), value in saved.items():
            if value is not None:
                setattr(cls, name, value)
            elif name in cls.__dict__:
                delattr(cls, name)
        os.environ.clear()
        os.environ.update(environ)
        _INVENTORY = module
    return _INVENTORY


def labelled(container, label, kinds=None):
    """The control in *container* a person would call *label*."""
    inv = inventory()
    QtWidgets = qt()[2]
    labels = inv.form_labels(container)
    want = norm(label)
    best = None
    for widget in inv.controls(container, only_visible=False):
        kind, text = inv.describe_widget(widget)
        if kind not in ("QToolButton", "QPushButton"):
            text = labels.get(id(widget), text)
        if kinds and not any(k.casefold() in kind.casefold() for k in kinds):
            continue
        if norm(text) == want or norm(widget.objectName()) == want:
            if widget.isVisible():
                return widget
            best = best or widget
    return best


def press_widget(win, widget, outcome, kind=""):
    """Use a control as a person would: click, type, choose."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QtWidgets.QScrollArea):
            parent.ensureWidgetVisible(widget)
            pump()
            break
        parent = parent.parentWidget()
    show_from_overflow(widget, outcome)
    if not widget.isVisible():
        outcome["hidden"] = True
        raise NotReached("the control is not on screen (overflow or hidden)")
    if not widget.isEnabled():
        outcome["disabled"] = describe(widget)[1]
        raise NotReached("the control is disabled")
    centre = widget.rect().center()
    outcome["t0"] = CURRENT["t0"] = time.perf_counter()
    if isinstance(widget, QtWidgets.QComboBox):
        Watch.navigating = True
        try:
            click_at(widget, centre)
            settle(60)
            view = widget.view()
            popup = view.window()
            if popup.isVisible():
                outcome["popup_shot"] = save_shot(popup.grab().toImage(), "combo")
            count = widget.count()
            target = (widget.currentIndex() + 1) % max(1, count)
            if CURRENT.get("choose"):
                found = next((i for i in range(count) if norm(widget.itemText(i)) == norm(
                    CURRENT["choose"])), None)
                if found is None:
                    outcome["missing"] = CURRENT["choose"]
                    outcome["menu_items"] = [widget.itemText(i) for i in range(count)]
                    Watch.navigating = False
                    close_popups()
                    return False
                target = found
            if count:
                index = widget.model().index(target, widget.modelColumn())
                rect = view.visualRect(index)
                outcome["chose"] = widget.itemText(target)
                Watch.navigating = False
                if popup.isVisible() and rect.isValid() and not rect.isEmpty():
                    click_at(view.viewport(), rect.center())
                else:
                    widget.setCurrentIndex(target)
                    outcome["fallback"] = "setCurrentIndex (popup not shown)"
        finally:
            Watch.navigating = False
            close_popups()
    elif isinstance(widget, QtWidgets.QAbstractSpinBox):
        click_at(widget, centre)
        line = widget.findChild(QtWidgets.QLineEdit)
        QTest.keyClick(line or widget, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        value = "3"
        if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            span = widget.maximum() - widget.minimum()
            value = str(int(widget.minimum() + min(span, max(1, span / 3))) if isinstance(
                widget, QtWidgets.QSpinBox) else round(widget.minimum() + min(span, 2.5), 1))
        QTest.keyClicks(line or widget, value)
        QTest.keyClick(line or widget, QtCore.Qt.Key_Return)
        outcome["typed"] = value
    elif isinstance(widget, QtWidgets.QLineEdit):
        click_at(widget, centre)
        QTest.keyClick(widget, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        text = "TBC" if "find" in norm(widget.placeholderText() + widget.toolTip()) or \
            "filter" in norm(widget.placeholderText()) else "Test 1"
        QTest.keyClicks(widget, text)
        QTest.keyClick(widget, QtCore.Qt.Key_Return)
        outcome["typed"] = text
    elif isinstance(widget, (QtWidgets.QToolButton, QtWidgets.QPushButton)) and \
            widget.menu() is not None and getattr(widget, "popupMode", lambda: None)() == \
            QtWidgets.QToolButton.MenuButtonPopup:
        click_at(widget, QtCore.QPoint(max(2, centre.x() - 4), centre.y()))
    else:
        click_at(widget, centre)
    return True


def via_toolbar(win, entry, outcome):
    QtGui, QtWidgets = qt()[1], qt()[2]
    bar = toolbar_named(win, entry["bar"])
    label = entry["label"]
    for action in bar.actions():
        if action.isSeparator() or not action.isVisible():
            continue
        widget = bar.widgetForAction(action)
        if isinstance(action, QtWidgets.QWidgetAction) or (
                widget is not None and not isinstance(widget, QtWidgets.QToolButton)):
            container = (action.defaultWidget() if isinstance(action, QtWidgets.QWidgetAction)
                         else None) or widget
            if container is None:
                continue
            found = None
            inv = inventory()
            members = [container] if isinstance(container, inv.CONTROL_TYPES) else \
                inv.controls(container, only_visible=False)
            want_kind = entry.get("widget", "")
            for member in members:
                kind, text = inv.describe_widget(member)
                if norm(text) == norm(label) and (not want_kind or want_kind.replace(
                        "Q", "") in kind.replace("Q", "")):
                    found = member
                    break
            if found is not None:
                return press_widget(win, found, outcome)
            continue
        text = clean(action.text()) or clean(action.toolTip().split("\n")[0])
        if norm(text) == norm(label):
            if widget is None or not widget.isVisible():
                outcome["overflow"] = True
                return via_overflow(win, bar, action, outcome)
            return press_widget(win, widget, outcome)
    # a family button shows the member last used (Sketch to Scale Rectangle
    # becomes "… Ellipse" once that was picked): a person takes the one they
    # want from its arrow menu
    family = button_offering(bar, label)
    if family is not None:
        outcome["family_menu"] = clean(family.text()) or family.toolTip()
        return menu_button(family, outcome, [label])
    raise NotReached(f"no '{label}' on toolbar {entry['bar']}")


def via_overflow(win, bar, action, outcome):
    """A button pushed into the toolbar's » menu: open it and click there."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    extension = bar.findChild(QtWidgets.QToolButton, "qt_toolbar_ext_button")
    if extension is None or not extension.isVisible():
        raise NotReached("button hidden and no » button")
    Watch.navigating = True
    try:
        click_at(extension, extension.rect().center())
        settle(60)
        widget = bar.widgetForAction(action)
        if widget is not None and widget.isVisible():
            Watch.navigating = False
            outcome["t0"] = CURRENT["t0"] = time.perf_counter()
            click_at(widget, widget.rect().center())
            return True
    finally:
        Watch.navigating = False
    raise NotReached("not visible even in the » popup")


def show_from_overflow(widget, outcome) -> None:
    """A toolbar control that did not fit is behind the bar's » button: open
    that, as a person would, so the control is on screen."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    if widget.isVisible():
        return
    bar = widget.parentWidget()
    while bar is not None and not isinstance(bar, QtWidgets.QToolBar):
        bar = bar.parentWidget()
    extension = bar.findChild(QtWidgets.QToolButton, "qt_toolbar_ext_button") \
        if bar is not None else None
    if extension is None:
        return
    pump()                                     # a bar still being laid out
    for _ in range(3):                         # » toggles: open, or close and open
        if widget.isVisible() or not extension.isVisible():
            break
        outcome["overflow"] = True             # behind the toolbar's » button
        Watch.navigating = True                # its popup is ours, not a stray
        click_at(extension, extension.rect().center())
        for _wait in range(10):
            settle(50)
            if widget.isVisible():
                break
    if not outcome.get("overflow"):
        return
    # the » popup was ours: let the watcher close strays again a little later,
    # but only if nothing has started navigating since. A bare timer here
    # fired inside the next job's own menu walk on a loaded machine and let
    # the watcher shut that menu as a stray ("no menu opened", T0180 and
    # T0198 under -n 3).
    Watch.overflow_token = token = object()

    def done():
        if Watch.overflow_token is token:
            Watch.overflow_token = None
            Watch.navigating = False
    QtCore.QTimer.singleShot(1500, done)


def menu_button(widget, outcome, path, each_index=None):
    """Open a button's own menu by clicking (its arrow), then walk *path*.
    A button's menu runs modally (QToolButton::showMenu is exec), so the walk
    is queued first and runs inside it."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    # a menu still closing from the job before (T0179 Merge, then T0180 its
    # Merge & Centre, gate on 4694f8c): a click on its own button while it
    # is up only closes it, as Qt does, so the next click opens nothing
    close_popups()
    wait_for(lambda: QtWidgets.QApplication.activePopupWidget() is None, 2.0)
    show_from_overflow(widget, outcome)
    if not widget.isVisible():
        outcome["hidden"] = True
        raise NotReached("its button is not on screen")
    rect = widget.rect()
    # A plain click on the same button just before (T0179 Merge, T0184
    # Borders, T0197 Rows & Columns) opened its menu on the press; the
    # watcher shut that menu before the release came, so the button was left
    # held down and the next press opened nothing. A hand always lets go:
    # let go first.
    if isinstance(widget, QtWidgets.QAbstractButton) and widget.isDown():
        QTest.mouseRelease(widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                           rect.center())
        pump()
        if widget.isDown():
            widget.setDown(False)
    if isinstance(widget, QtWidgets.QToolButton) and \
            widget.popupMode() == QtWidgets.QToolButton.MenuButtonPopup:
        point = QtCore.QPoint(rect.right() - 4, rect.center().y())
    else:
        point = rect.center()
    ok = open_then_walk(lambda: click_at(widget, point), path, outcome, each_index)
    if not ok and outcome.get("error") == "no menu opened" and under_its_own_pointer(widget):
        # The button is settled, enabled, not held and under the pointer, and
        # still the click opened nothing: under -n 3 Qt sometimes drops a
        # synthetic press on a button whose menu the job before closed by
        # code (T0185 after T0184, gate runs on 4694f8c). A hand clicks again.
        # Written down, never silent: a second miss fails the job.
        note = ("swallowed click on '%s' (%s), clicked again\n"
                % (clean(widget.text()) if hasattr(widget, "text") else widget,
                   " > ".join(path)))
        try:
            import tempfile
            with open(os.path.join(tempfile.gettempdir(),
                                   "test_every_command-failures.txt"), "a") as log:
                log.write("SWALLOWED\t" + note)
        except OSError:
            pass
        for key in ("error", "missing", "disabled"):
            outcome.pop(key, None)
        outcome["clicked_again"] = True
        settle(QtWidgets.QApplication.doubleClickInterval() + 50)
        ok = open_then_walk(lambda: click_at(widget, point), path, outcome, each_index)
    return ok


def open_then_walk(opener, path, outcome, each_index=None, kind=None):
    """Queue the walk through the menu, then open it (which may block)."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    done = {"ran": False, "ok": False}
    # A button's menu can take more than half a second to show on a loaded
    # machine (T0183 Borders ▸ All Borders gave up after 0.6 s, gate on
    # eebcff1): wait up to 3 s for it, by looking, not by a fixed sleep.
    tries = [0]

    def navigate():
        menu = QtWidgets.QApplication.activePopupWidget()
        if not isinstance(menu, QtWidgets.QMenu):
            tries[0] += 1
            if tries[0] < 100:
                QtCore.QTimer.singleShot(30, navigate)
                return
            done["ran"] = True
            outcome["error"] = "no menu opened"
            Watch.navigating = False
            return
        done["ran"] = True
        done["ok"] = walk_popup(path, outcome, each_index)

    Watch.navigating = True
    Watch.overflow_token = None                # a menu walk of its own now
    QtCore.QTimer.singleShot(60, navigate)
    opener()
    wait_for(lambda: done["ran"], 4.0)
    Watch.navigating = False
    if not done["ran"]:
        outcome["error"] = "no menu opened"
        close_popups()
        return False
    return done["ok"] and not any(k in outcome for k in ("missing", "disabled", "error"))


def under_its_own_pointer(widget) -> bool:
    """The button found is the one on screen where it says it is: a bar
    still being rebuilt (the Properties bar after the table fixture opens)
    hands back a button that is about to go, and a click at its place lands
    on nothing (T0180, T0185, T0198 under -n 3)."""
    QtWidgets = qt()[2]
    try:
        if not widget.isVisible():
            return False
        hit = QtWidgets.QApplication.widgetAt(widget.mapToGlobal(widget.rect().center()))
    except RuntimeError:
        return False
    return hit is not None and (hit is widget or widget.isAncestorOf(hit))


def via_toolbar_menu(win, entry, outcome, each_index=None):
    QtWidgets = qt()[2]
    # wait for the bar to settle: the button found must be the one on screen
    for _ in range(20):
        pump()
        found = find_toolbar_menu_button(win, entry)
        if found is None or under_its_own_pointer(found) or \
                not found.isVisible():          # behind the », shown from there
            break
        settle(100)
    return _via_toolbar_menu(win, entry, outcome, each_index)


def find_toolbar_menu_button(win, entry):
    QtWidgets = qt()[2]
    try:
        bar = toolbar_named(win, entry["bar"])
    except NotReached:
        return None
    inv = inventory()
    for action in bar.actions():
        widget = bar.widgetForAction(action)
        candidates = [widget] if widget is not None else []
        holder = (action.defaultWidget() if isinstance(action, QtWidgets.QWidgetAction)
                  else None) or widget
        if holder is not None and not isinstance(holder, QtWidgets.QToolButton):
            candidates = inv.controls(holder, only_visible=False)
        for candidate in candidates:
            if candidate is None:
                continue
            text = inv.describe_widget(candidate)[1]
            if isinstance(candidate, QtWidgets.QToolButton) and candidate.defaultAction():
                text = clean(candidate.defaultAction().text()) or text
            if norm(text) == norm(entry["button"]):
                return candidate
    return None


def _via_toolbar_menu(win, entry, outcome, each_index=None):
    QtWidgets = qt()[2]
    bar = toolbar_named(win, entry["bar"])
    inv = inventory()
    for action in bar.actions():
        widget = bar.widgetForAction(action)
        candidates = [widget] if widget is not None else []
        holder = (action.defaultWidget() if isinstance(action, QtWidgets.QWidgetAction)
                  else None) or widget
        if holder is not None and not isinstance(holder, QtWidgets.QToolButton):
            candidates = inv.controls(holder, only_visible=False)
        for candidate in candidates:
            if candidate is None:
                continue
            text = inv.describe_widget(candidate)[1]
            if isinstance(candidate, QtWidgets.QToolButton) and candidate.defaultAction():
                text = clean(candidate.defaultAction().text()) or text
            if norm(text) == norm(entry["button"]):
                return menu_button(candidate, outcome, entry["path"], each_index)
    offering = button_offering(bar, entry["path"][0]) if entry.get("path") else None
    if offering is not None:
        return menu_button(offering, outcome, entry["path"], each_index)
    raise NotReached(f"no '{entry['button']}' button on toolbar {entry['bar']}")


def container_of(win, name):
    if name == "Status bar":
        return win.statusBar()
    if name == "Menu-bar corner":
        return win.menuBar().cornerWidget()
    if name == "Formula bar":
        return win.formula_bar
    if name == "Sheet tabs bar":
        return win.sheet_tabs
    raise NotReached(f"no container {name}")


def via_widget(win, entry, outcome):
    container = container_of(win, entry["container"])
    widget = labelled(container, entry["label"])
    if widget is None:
        raise NotReached(f"no '{entry['label']}' in the {entry['container']}")
    return press_widget(win, widget, outcome)


def button_offering(container, item):
    """The menu button in *container* whose menu holds *item*. Some buttons
    are named after what they are set to (the page layout reads "Continuous"
    or "Single Page"), so a person finds them by what they offer."""
    QtWidgets = qt()[2]
    want = norm(item)
    for button in container.findChildren(QtWidgets.QToolButton) + \
            container.findChildren(QtWidgets.QPushButton):
        menu = button.menu()
        if menu is None or not button.isVisible():
            continue
        if any(norm(clean(a.text())) == want for a in menu.actions()):
            return button
    return None


def via_widget_menu(win, entry, outcome, each_index=None):
    container = container_of(win, entry["container"])
    widget = labelled(container, entry["button"])
    if widget is None and entry.get("path"):
        widget = button_offering(container, entry["path"][0])
    if widget is None:
        raise NotReached(f"no '{entry['button']}' in the {entry['container']}")
    return menu_button(widget, outcome, entry["path"], each_index)


def keys_of(text):
    QtGui = qt()[1]
    sequence = QtGui.QKeySequence(text)
    if sequence.isEmpty():
        return None
    combo = sequence[0]
    return combo.key(), combo.keyboardModifiers()


def focus_target(win):
    QtWidgets = qt()[2]
    focus = QtWidgets.QApplication.focusWidget()
    if focus is not None and toplevel(focus) is toplevel(win):
        return focus
    return win.view.viewport()


def via_key(win, entry, outcome):
    QtCore, QtGui, QtWidgets, QTest = qt()
    spec = entry["keys"]
    if spec in ("", "1 … 9"):
        raise NotReached("no single key")
    parsed = keys_of(spec)
    if parsed is None:
        raise NotReached(f"cannot read the key '{spec}'")
    key, mods = parsed
    target = focus_target(win)
    outcome["focus"] = type(target).__name__
    outcome["t0"] = CURRENT["t0"] = time.perf_counter()
    QTest.keyClick(target, key, mods)
    return True


def context_spot(win, target, ctx, entry):
    """(widget, local point) for a right-click on *target*."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    view = win.view
    if target in ("item", "paper", "cell"):
        point = ctx.get("point")
        if target == "item" and ctx.get("item") is not None:
            point = centre_of(ctx["item"])
        if point is None:
            raise NotReached("the fixture has no point to right-click")
        if target == "cell" and ctx.get("table") is not None:
            from tests.test_tables import cell_scene
            point = cell_scene(ctx["table"], "B2" if entry.get("table") != "sheet" else "C5")
        view.ensureVisible(QtCore.QRectF(point.x() - 40, point.y() - 40, 80, 80))
        pump()
        return view.viewport(), view.mapFromScene(point)
    if target == "thumbnail":
        strip = win.pages_panel.list
        show_dock(win, "Thumbnails")
        item = strip.item(ctx.get("page", 0))
        if item is None:
            raise NotReached("no thumbnail")
        strip.scrollToItem(item)
        return strip.viewport(), strip.visualItemRect(item).center()
    if target == "markups_row":
        tree = win.markups_panel.tree
        if tree.topLevelItemCount() == 0:
            raise NotReached("the Markups List is empty")
        item = tree.topLevelItem(0)
        while item.childCount():
            item = item.child(0)
        tree.scrollToItem(item)
        tree.setCurrentItem(item)
        return tree.viewport(), tree.visualItemRect(item).center()
    if target == "markups_header":
        tree = win.markups_panel.tree
        header = tree.header()
        titles = list(win.markups_panel.COLUMNS)
        column = next((i for i, t in enumerate(titles) if norm(t) == norm(entry["column"])),
                      None)
        if column is None:
            raise NotReached(f"no column {entry['column']}")
        if header.isSectionHidden(column):
            raise NotReached(f"column {entry['column']} is hidden")
        tree.scrollTo(tree.model().index(0, column)) if tree.topLevelItemCount() else None
        x = header.sectionViewportPosition(column) + header.sectionSize(column) // 2
        return header.viewport(), QtCore.QPoint(x, header.height() // 2)
    if target == "doc_tab":
        bar = win.document_tabs
        if bar.count() == 0 or not bar.isVisible():
            raise NotReached("no document tab shown")
        return bar, bar.tabRect(0).center()
    if target == "sheet_tab":
        bar = win.sheet_tabs.bar
        if bar.count() == 0:
            raise NotReached("no sheet tab")
        return bar, bar.tabRect(0).center()
    if target == "ruler":
        from calcforge.ui.rulers import Ruler
        rulers = [r for r in win.findChildren(Ruler) if r.isVisible()]
        if not rulers:
            raise NotReached("no ruler shown")
        return rulers[0], QtCore.QPoint(40, rulers[0].height() // 2)
    if target == "variables_row":
        panel = win.variables_panel
        tree = panel.tree
        for r in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(r)
            for candidate in [top] + [top.child(c) for c in range(top.childCount())]:
                if panel.row_of(candidate) is not None:
                    tree.scrollToItem(candidate)
                    return tree.viewport(), tree.visualItemRect(candidate).center()
        raise NotReached("the Variables panel has no row")
    if target in ("row_heading", "col_heading"):
        return heading_spot(win, ctx, target.split("_")[0])
    if target == "filter_button":
        table = view.tables.item
        if table is None or table.sheet is None or table.sheet.filter is None:
            raise NotReached("no filtered table open")
        local = table.filter_button(0).center()
        return view.viewport(), view.mapFromScene(table.mapToScene(local))
    if target.startswith("style_button"):
        number = target[len("style_button"):] or "1"
        bar = win.markup_styles.bar
        button = bar.findChild(QtWidgets.QToolButton, f"markupStyle{number}")
        if button is None or not button.isVisible():
            raise NotReached(f"no Markup Styles button {number}")
        return button, button.rect().center()
    if target == "chest_tool":
        chest = win.toolsets_panel
        lists = [w for w in chest.findChildren(QtWidgets.QAbstractItemView) if w.isVisible()]
        for view_ in lists:
            model = view_.model()
            if model is not None and model.rowCount():
                return view_.viewport(), view_.visualRect(model.index(0, 0)).center()
        buttons = [b for b in chest.findChildren(QtWidgets.QToolButton) if b.isVisible()
                   and b.objectName() not in ("toolSetChevron",)]
        if buttons:
            return buttons[-1], buttons[-1].rect().center()
        raise NotReached("no tool in the Tool Chest")
    raise NotReached(f"unknown right-click target {target}")


def heading_spot(win, ctx, axis):
    """A point on row 2's or column B's heading of the open table or sheet."""
    QtCore = qt()[0]
    view = win.view
    want = 1
    headings = getattr(view, "sheet_headings", None)
    vp = view.viewport()
    if headings is not None and headings.isVisible():
        for y in range(0, vp.height(), 3):
            for x in range(0, vp.width(), 3) if axis == "col" else range(0, 80, 2):
                if axis == "col" and y > 60:
                    break
                hit = headings.hit(QtCore.QPointF(x, y))
                if hit is not None and hit[1] == (axis, want):
                    return vp, QtCore.QPoint(x, y)
    table = view.tables.item
    if table is None:
        raise NotReached("no table open for its headings")
    xs, ys = table.edges()
    for step in range(1, 60):
        if axis == "row":
            local = QtCore.QPointF(-step, (ys[want] + ys[want + 1]) / 2)
        else:
            local = QtCore.QPointF((xs[want] + xs[want + 1]) / 2, -step)
        zone = view.tables._zone(table, local)
        if zone and zone[0] == axis and zone[1] == want:
            point = view.mapFromScene(table.mapToScene(local))
            return vp, point
    raise NotReached(f"no {axis} heading found")


def via_context(win, entry, outcome, ctx, each_index=None):
    QtCore, QtGui, QtWidgets, QTest = qt()
    target = entry["target"]
    if target in ("chest_button", "chest_gear"):
        chest = win.toolsets_panel
        name = "Tool Sets ▾" if target == "chest_button" else None
        buttons = [b for b in chest.findChildren(QtWidgets.QToolButton) if b.isVisible()]
        button = None
        for b in buttons:
            text = describe(b)[1]
            if target == "chest_button" and norm(text).startswith("tool sets"):
                button = b
            if target == "chest_gear" and b.objectName() == "toolSetGear":
                button = b
        if button is None:
            raise NotReached(f"no {target.replace('_', ' ')}")
        return menu_button(button, outcome, entry["path"], each_index)
    widget, local = context_spot(win, target, ctx, entry)
    deepest = widget.childAt(local)
    if deepest is not None and target not in ("item", "paper", "cell", "row_heading",
                                               "col_heading", "filter_button"):
        local = deepest.mapFrom(widget, local)
        widget = deepest
    outcome["spot"] = f"{type(widget).__name__}@{local.x()},{local.y()}"
    plan = list(entry["path"])
    done = {"ran": False}

    def navigate(tries=[0]):
        menu = QtWidgets.QApplication.activePopupWidget()
        if not isinstance(menu, QtWidgets.QMenu):
            tries[0] += 1
            if tries[0] < 60:
                QtCore.QTimer.singleShot(30, navigate)
                return
            done["ran"] = True
            outcome["error"] = "the right-click opened no menu"
            Watch.navigating = False
            return
        done["ran"] = True
        if entry.get("kind") == "field":
            remember_menu(menu, outcome)
            action = find_action(menu.actions(), plan[-1].replace("[field] ", ""))
            fields = menu.findChildren(QtWidgets.QLineEdit)
            Watch.navigating = False
            if fields:
                click_at(fields[0], fields[0].rect().center())
                QTest.keyClick(fields[0], QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
                outcome["t0"] = CURRENT["t0"] = time.perf_counter()
                QTest.keyClicks(fields[0], "L.test")
                QTest.keyClick(fields[0], QtCore.Qt.Key_Return)
                outcome["typed"] = "L.test"
                QtCore.QTimer.singleShot(50, close_popups)
            else:
                outcome["missing"] = "field"
                close_popups()
            return
        walk_popup(plan, outcome, each_index)

    Watch.navigating = True
    QtCore.QTimer.singleShot(80, navigate)
    QTest.mouseMove(widget, local)
    if target == "filter_button":
        outcome["spot"] += " (left click)"
        QTest.mouseClick(widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, local)
    else:
        QTest.mousePress(widget, QtCore.Qt.RightButton, QtCore.Qt.NoModifier, local)
        QTest.mouseRelease(widget, QtCore.Qt.RightButton, QtCore.Qt.NoModifier, local)
    if QtWidgets.QApplication.activePopupWidget() is None and target != "filter_button" \
            and not done["ran"]:
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, local,
                                        widget.mapToGlobal(local))
        QtWidgets.QApplication.sendEvent(widget, event)
    for _ in range(200):
        if done["ran"]:
            break
        settle(10)
    Watch.navigating = False
    if not done["ran"]:
        outcome["error"] = "the right-click opened no menu"
        done["ran"] = True                     # a late retry must not walk anything now
        return False
    return not any(k in outcome for k in ("missing", "disabled", "error"))


def via_dock_button(win, entry, outcome):
    dock = show_dock(win, entry["panel"])
    if dock is None:
        raise NotReached(f"no panel {entry['panel']}")
    QtWidgets = qt()[2]
    bar = dock.titleBarWidget()
    if bar is None:
        raise NotReached("the panel has no title bar")
    for button in bar.findChildren(QtWidgets.QToolButton):
        if norm(clean(button.toolTip())) == norm(entry["tip"]):
            return press_widget(win, button, outcome)
    raise NotReached(f"no '{entry['tip']}' on the {entry['panel']} title bar")


def via_panel_toggle(win, entry, outcome):
    """The panel's rail button (the icon at the window edge)."""
    QtWidgets = qt()[2]
    want = norm(entry["panel"])
    for button in win.findChildren(QtWidgets.QToolButton, "railButton"):
        # the tip names the panel and its key: "Thumbnails  (Alt+T)"
        names = (re.sub(r"\s*\(.*\)$", "", button.toolTip()), button.text())
        if any(norm(n) == want for n in names if n) and button.isVisible():
            return press_widget(win, button, outcome)
    for bar in win.findChildren(QtWidgets.QToolBar):
        if bar.windowTitle() not in ("Left panels", "Right panels"):
            continue
        inv = inventory()
        for widget in inv.controls(bar, only_visible=False):
            if norm(inv.describe_widget(widget)[1]) == want:
                return press_widget(win, widget, outcome)
    dock = next((d for d in win.panels if d.windowTitle() == entry["panel"]), None)
    if dock is None:
        raise NotReached(f"no panel {entry['panel']}")
    raise NotReached("no rail button for it")


def panel_root(win, title):
    """The widget a panel's controls live in (the Markups List is not a dock)."""
    if title == "Markups List":
        if not win.markups_panel.isVisible():
            win.act_markups_list.trigger()
            pump()
        return win.markups_panel
    dock = show_dock(win, title)
    if dock is None:
        raise NotReached(f"no panel {title}")
    return win.properties_panel if title == "Properties" else dock.widget()


def via_panel(win, entry, outcome):
    root = panel_root(win, entry["panel"])
    widget = labelled(root, entry["label"])
    if widget is None:
        raise NotReached(f"no '{entry['label']}' in {entry['panel']}")
    return press_widget(win, widget, outcome)


def via_panel_menu(win, entry, outcome, each_index=None):
    root = panel_root(win, entry["panel"])
    widget = labelled(root, entry["button"])
    if widget is None:
        raise NotReached(f"no '{entry['button']}' in {entry['panel']}")
    return menu_button(widget, outcome, entry["path"], each_index)


def panel_group_buttons(win, entry):
    QtWidgets = qt()[2]
    root = panel_root(win, entry["panel"])
    inv = inventory()
    return [w for w in inv.controls(root, only_visible=False)
            if isinstance(w, QtWidgets.QToolButton) and w.menu() is None
            and w.isVisibleTo(root)]


def via_call(win, entry, outcome, ctx):
    """Dialogs only reachable from inside another dialog or by code: their
    function, called the way their parent calls it."""
    QtCore = qt()[0]
    fn = entry["fn"]
    outcome["t0"] = CURRENT["t0"] = time.perf_counter()
    if fn == "count_subject":
        from calcforge.ui import dialogs
        dialogs.choose_count_subject(win) if _arity(dialogs.choose_count_subject) else \
            dialogs.choose_count_subject()
    elif fn == "manage_hatches":
        from calcforge.ui import hatchpatterns
        hatchpatterns.manage_hatches(win)
    elif fn == "new_hatch":
        from calcforge.ui import hatchpatterns
        hatchpatterns.new_pattern(win)
    elif fn == "rename_style":
        from calcforge.ui import markupstyles
        bar = getattr(win, "markup_styles", None) or getattr(win, "styles_bar", None)
        if bar is None or not hasattr(bar, "rename"):
            raise NotReached("no Markup Styles bar with rename()")
        bar.rename(0) if _arity(bar.rename) else bar.rename()
    elif fn == "import_xlsx":
        files = sample_files()
        from calcforge.ui import xlsximport
        dialog_cls = next((getattr(xlsximport, n) for n in dir(xlsximport)
                           if n.endswith("Dialog")), None)
        if dialog_cls is None:
            raise NotReached("no dialog class in xlsximport")
        try:
            dialog = dialog_cls(files["xlsx"], win)
        except TypeError:
            dialog = dialog_cls(win, files["xlsx"])
        dialog.exec()
    elif fn == "plot_settings":
        from calcforge.ui import calcmenu
        from calcforge.items.calc import CalcItem
        plots = [i for i in win.view.scene().items() if isinstance(i, CalcItem)]
        if not plots:
            raise NotReached("no plot")
        calcmenu.plot_settings(win, plots[0])
    elif fn == "rename_section":
        from calcforge.ui import calcsections
        calcsections.rename(win, 1)
    elif fn in ("save_preset", "new_preset", "rename_preset"):
        from calcforge.ui import condformat
        getattr(condformat, fn)(win)
    elif fn == "toolset_new_name":
        from calcforge.ui import managetoolsets
        managetoolsets._ask_name(win, "New Tool Set", "")
    elif fn == "rename_set":
        chest = win.toolsets_panel
        chest.rename_set() if not _arity(chest.rename_set) else chest.rename_set(0)
    elif fn in ("custom_filter", "values_filter"):
        from calcforge.ui import datatools
        if fn == "custom_filter":
            datatools.custom_filter_dialog(win.view.tables, 0)
        else:
            datatools.values_dialog(win.view.tables, 0)
    else:
        raise NotReached(f"no caller for {fn}")
    return True


def _arity(fn):
    import inspect
    try:
        return len([p for p in inspect.signature(fn).parameters.values()
                    if p.default is inspect.Parameter.empty])
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# the fixed canvas keys and the mouse gestures
# ---------------------------------------------------------------------------
def via_viewkey(win, entry, outcome, ctx):
    QtCore, QtGui, QtWidgets, QTest = qt()
    from tests.test_usability import click, double_click, drag, press_key
    view = win.view
    vp = view.viewport()
    what = entry["what"]
    keys = entry["keys"]
    outcome["t0"] = CURRENT["t0"] = time.perf_counter()
    if keys.startswith("Space"):
        p = page_point(win, 400, 500)
        QTest.keyPress(vp, QtCore.Qt.Key_Space)
        drag(view, p.x(), p.y(), p.x() - 120, p.y() - 80)
        QTest.keyRelease(vp, QtCore.Qt.Key_Space)
    elif keys == "Esc":
        QTest.keyClick(vp, QtCore.Qt.Key_Escape)
    elif keys.startswith("Enter"):
        win.select_tool("polygon")
        for x, y in ((300, 400), (420, 400), (420, 500)):
            p = page_point(win, x, y)
            click(view, p.x(), p.y())
        QTest.keyClick(vp, QtCore.Qt.Key_Return)
    elif keys.startswith("Delete"):
        QTest.keyClick(vp, QtCore.Qt.Key_Delete)
    elif keys == "Arrows":
        QTest.keyClick(vp, QtCore.Qt.Key_Right)
    elif keys.startswith("Shift+Arrows"):
        QTest.keyClick(vp, QtCore.Qt.Key_Right, QtCore.Qt.ShiftModifier)
    elif keys.startswith("PgUp"):
        QTest.keyClick(vp, QtCore.Qt.Key_PageDown)
    elif keys.startswith("Home"):
        QTest.keyClick(vp, QtCore.Qt.Key_End)
    elif keys.startswith("Ctrl+Home"):
        QTest.keyClick(vp, QtCore.Qt.Key_End, QtCore.Qt.ControlModifier)
    elif keys.startswith("1"):
        QTest.keyClick(vp, QtCore.Qt.Key_1)
        p, q = page_point(win, 300, 400), page_point(win, 420, 480)
        drag(view, p.x(), p.y(), q.x(), q.y())
    elif keys.startswith("Ctrl"):
        item = ctx.get("item")
        if item is None:
            raise NotReached("nothing to drag")
        a = centre_of(item)
        QTest.keyPress(vp, QtCore.Qt.Key_Control)
        drag(view, a.x(), a.y(), a.x() + 37, a.y() + 23, QtCore.Qt.ControlModifier)
        QTest.keyRelease(vp, QtCore.Qt.Key_Control)
    elif keys.startswith("Shift"):
        win.select_tool("line")
        p, q = page_point(win, 300, 420), page_point(win, 420, 440)
        drag(view, p.x(), p.y(), q.x(), q.y(), QtCore.Qt.ShiftModifier)
        press_key(view, QtCore.Qt.Key_Escape)
    elif keys.startswith("Ctrl+B"):
        raise NotReached("covered by the text-box typing state")
    else:
        raise NotReached(f"no handler for {keys}")
    return True


def via_mouse(win, entry, outcome, ctx):
    """One handler per gesture of the inventory's Mouse section."""
    QtCore, QtGui, QtWidgets, QTest = qt()
    from tests.test_usability import click, double_click, drag, hover
    view = win.view
    vp = view.viewport()
    g = entry["gesture"]
    where, _, what = g.partition(" | ")
    outcome["t0"] = CURRENT["t0"] = time.perf_counter()
    item = ctx.get("item")
    c = centre_of(item) if item is not None else page_point(win, 300, 300)
    local = view.mapFromScene(c)

    def wheel(dy, mods=QtCore.Qt.NoModifier, dx=0, pixels=False):
        event = QtGui.QWheelEvent(QtCore.QPointF(local), QtCore.QPointF(vp.mapToGlobal(local)),
                                  QtCore.QPoint(dx, dy) if pixels else QtCore.QPoint(0, 0),
                                  QtCore.QPoint(dx, dy) if not pixels else QtCore.QPoint(0, 0),
                                  QtCore.Qt.NoButton, mods, QtCore.Qt.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(vp, event)
        pump()
        try:
            view.finish_scrolling()
        except Exception:  # noqa: BLE001
            pass

    if g == "canvas | Wheel":
        wheel(120)
    elif g == "canvas | Ctrl+Wheel":
        wheel(-120, QtCore.Qt.ControlModifier)
    elif g == "canvas | Shift+Wheel":
        wheel(-120, QtCore.Qt.ShiftModifier)
    elif g == "canvas | Two-finger scroll":
        wheel(-60, dx=-40, pixels=True)
    elif g == "canvas | Middle-button drag":
        QTest.mousePress(vp, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier, local)
        for step in range(1, 4):
            event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove,
                                      QtCore.QPointF(local + QtCore.QPoint(-30 * step, -20 * step)),
                                      QtCore.QPointF(vp.mapToGlobal(local + QtCore.QPoint(
                                          -30 * step, -20 * step))),
                                      QtCore.Qt.NoButton, QtCore.Qt.MiddleButton,
                                      QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(vp, event)
        QTest.mouseRelease(vp, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier,
                           local + QtCore.QPoint(-90, -60))
    elif g == "canvas | Space + drag / Pan tool":
        win.select_tool("pan")
        drag(view, c.x(), c.y(), c.x() - 120, c.y() - 90)
    elif g == "canvas (Select) | Drag on bare paper":
        win.view.scene().clearSelection()
        p, q = page_point(win, 80, 80), page_point(win, 260, 210)
        drag(view, p.x(), p.y(), q.x(), q.y())
    elif g == "canvas (Select) | Shift+click on bare paper":
        win.view.scene().clearSelection()
        for x, y in ((80, 80), (300, 80), (300, 230)):
            p = page_point(win, x, y)
            click(view, p.x(), p.y(), modifiers=QtCore.Qt.ShiftModifier)
        QTest.keyClick(vp, QtCore.Qt.Key_Return)
    elif where == "markup" and what == "Click":
        win.view.scene().clearSelection()
        click(view, c.x(), c.y())
    elif where == "markup" and what in ("Shift+click", "Ctrl+click"):
        others = [i for i in markups(win) if i is not item]
        target = centre_of(others[0]) if others else c
        mods = QtCore.Qt.ShiftModifier if what.startswith("Shift") else QtCore.Qt.ControlModifier
        click(view, target.x(), target.y(), modifiers=mods)
    elif where == "markup" and what == "Drag":
        drag(view, c.x(), c.y(), c.x() + 60, c.y() + 40)
    elif where == "markup" and what == "Ctrl+drag":
        drag(view, c.x(), c.y(), c.x() + 60, c.y() + 40, QtCore.Qt.ControlModifier)
    elif where == "markup" and what == "Drag onto another page":
        q = page_point(win, 200, 150, 1)
        drag(view, c.x(), c.y(), q.x(), q.y())
    elif where == "selected markup":
        corner = item.mapToScene(item.local_rect().bottomRight())
        drag(view, corner.x(), corner.y(), corner.x() + 40, corner.y() + 30)
    elif where == "several selected":
        box = QtCore.QRectF()
        for i in ctx.get("items", []):
            box = box.united(i.sceneBoundingRect())
        drag(view, box.right(), box.bottom(), box.right() + 50, box.bottom() + 40)
    elif where == "outline":
        corner = item.mapToScene(item.local_rect().topLeft()) if hasattr(item, "local_rect") \
            else c
        mid = QtCore.QPointF((corner.x() + c.x()) / 2, corner.y())
        click(view, mid.x(), mid.y(), modifiers=QtCore.Qt.ShiftModifier)
    elif where == "dimension":
        drag(view, c.x(), c.y() - 6, c.x() + 30, c.y() - 50, QtCore.Qt.ShiftModifier)
    elif where in ("text box / callout", "note", "polyline / polygon / area",
                   "dimension / length", "table", "chart", "closed calculation block",
                   "equation", "link"):
        double_click(view, c.x(), c.y())
    elif where == "contents line":
        click(view, c.x(), c.y())
    elif where == "markup / paper":
        win.act_format_painter.trigger()
        others = [i for i in markups(win) if i is not item]
        target = centre_of(others[0]) if others else page_point(win, 300, 300)
        click(view, target.x(), target.y())
        QTest.keyClick(vp, QtCore.Qt.Key_Escape)
    elif where == "half-drawn polygon or cloud":
        win.select_tool("cloud")
        for x, y in ((300, 400), (420, 400), (420, 500)):
            p = page_point(win, x, y)
            click(view, p.x(), p.y())
        lp = view.mapFromScene(page_point(win, 300, 500))
        QtWidgets.QApplication.sendEvent(vp, QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, lp, vp.mapToGlobal(lp)))
    elif where == "thumbnail":
        strip = win.pages_panel.list
        a = strip.visualItemRect(strip.item(0)).center()
        b = strip.visualItemRect(strip.item(strip.count() - 1)).bottomLeft() + QtCore.QPoint(
            10, 10)
        QTest.mousePress(strip.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, a)
        for step in range(1, 6):
            QTest.mouseMove(strip.viewport(), a + (b - a) * step / 5)
        QTest.mouseRelease(strip.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, b)
    elif where == "Markups List handle":
        split = getattr(win, "bottom_split", None)
        handle = split.handle(1) if split is not None else None
        if handle is None:
            raise NotReached("no Markups List handle found")
        QTest.mouseDClick(handle, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                          handle.rect().center())
    elif where == "panel title bar":
        dock = show_dock(win, "Properties")
        bar = dock.titleBarWidget()
        QTest.mouseDClick(bar, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(30, 8))
    elif where == "cells":
        from tests.test_tables import cell_scene
        a, b = cell_scene(ctx["table"], "A1"), cell_scene(ctx["table"], "B3")
        drag(view, a.x(), a.y(), b.x(), b.y())
    elif where == "fill handle":
        table = ctx["table"]
        rect = table.cell_rect(0, 0)
        corner = table.mapToScene(rect.bottomRight()) - QtCore.QPointF(1, 1)
        drag(view, corner.x(), corner.y(), corner.x(), corner.y() + 3 * rect.height())
    elif where == "selection border":
        table = ctx["table"]
        rect = table.cell_rect(0, 0)
        edge = table.mapToScene(QtCore.QPointF(rect.center().x(), rect.top() + 1))
        drag(view, edge.x(), edge.y(), edge.x() + rect.width() * 2, edge.y() + rect.height() * 4)
    elif where == "row/column heading border":
        table = ctx["table"]
        rect = table.cell_rect(0, 0)
        top = table.mapToScene(QtCore.QPointF(rect.right(), rect.top() - 6))
        drag(view, top.x(), top.y(), top.x() + 30, top.y())
    elif where == "table corner":
        table = ctx["table"]
        corner = table.mapToScene(table.local_rect().bottomRight()) if hasattr(
            table, "local_rect") else table.sceneBoundingRect().bottomRight()
        drag(view, corner.x() - 1, corner.y() - 1, corner.x() + 60, corner.y() + 40)
    else:
        raise NotReached("not drivable headless: " + {
            "thumbnail strip": "a file dropped from the desktop",
            "document tab onto the other split pane": "drag between two windows",
            "panel title bar / rail icon": "a dock drag needs a window manager",
            "toolbar grip": "a toolbar drag needs a window manager",
            "window edge (frameless)": "needs a window manager",
            "empty menu-bar space": "needs a window manager",
        }.get(where, f"no handler for '{g}'"))
    return True


MOUSE_STATE = {
    "markup": "two_rects_one", "selected markup": "rect", "several selected": "two_rects",
    "outline": "rect", "dimension": "dimension", "text box / callout": "textbox",
    "note": "note", "polyline / polygon / area": "polygon", "dimension / length": "length",
    "table": "table_closed", "chart": "chart", "closed calculation block": "calc_block_closed",
    "equation": "equation", "link": "link", "contents line": "fresh", "markup / paper":
    "two_rects_one", "thumbnail": "three_pages", "cells": "table_open",
    "fill handle": "table_open", "selection border": "table_open",
    "row/column heading border": "table_open", "table corner": "table_closed",
    "Markups List handle": "markups_list",
}


def fixture_for_mouse(gesture_text):
    where, _, what = gesture_text.partition(" | ")
    if where == "markup" and what == "Drag onto another page":
        return "rect_two_pages"
    return MOUSE_STATE.get(where, "rect" if where.startswith("canvas") else "fresh")


def fx_two_rects_one(win):
    ctx = fx_two_rects(win)
    pick(win, ctx["items"][:1])
    return ctx


def fx_rect_two_pages(win):
    win.add_page()
    pump()
    win.go_to_page(0)
    return _one("rect")(win)


def fx_calc_block_closed(win):
    ctx = fx_calc_block(win)
    win.toggle_calc_mode(False)
    win.view.scene().clearSelection()
    return ctx


FIXTURES.update({
    "two_rects_one": fx_two_rects_one,
    "rect_two_pages": fx_rect_two_pages,
    "calc_block_closed": fx_calc_block_closed,
    "dimension": _one("measure_dimension", (100, 300), (320, 300)),
    "polygon": _one("polygon", (100, 300), (260, 420)),
})


# ===========================================================================
# 5. one run: state, command, what happened
# ===========================================================================
def use_tool_if_picked(win, outcome):
    """A tool picked by its button, key or menu is then used on the page."""
    from calcforge.ui.tools import TOOLS
    from tests.test_usability import press_key, type_text
    QtCore = qt()[0]
    key = getattr(win.view, "tool_key", "select")
    if key in (None, "select"):
        return
    tool = next((t for t in TOOLS if t.key == key), None)
    if tool is None:
        return
    outcome["tool_used"] = key
    # a first rectangle or measurement on an unscaled page asks for the scale:
    # answer it (OK), so the tool goes on to draw
    Watch.policy, Watch.handled_first = "ok", False
    gesture(win, None, tool.mode, (330, 420), (470, 520))
    settle(30)
    if win.view._editing_item is not None:
        type_text(win.view, "Typed")
    press_key(win.view, QtCore.Qt.Key_Escape)
    press_key(win.view, QtCore.Qt.Key_Escape)
    pump()


def state_name(command, entry):
    if entry.get("state"):
        return entry["state"]
    if entry.get("via") == "mouse" and command["area"] == "Mouse":
        return fixture_for_mouse(entry["gesture"])
    return command["state"]


def build_state(win, name):
    fixture = FIXTURES.get(name)
    if fixture is None and name.startswith("tool:"):
        fixture = _one(name[5:])               # one markup drawn with that tool, picked
    if fixture is None:
        raise NotReached(f"no fixture '{name}'")
    win.interactive_prompts = False
    Watch.reset("cancel")
    ctx = fixture(win) or {}
    settle(20)
    activate(win)
    back_to_the_window(win, 1.0)               # a fixture's own menus have let go
    if name not in ("equation_editing", "matrix_eq", "textbox_editing", "table_open", "sheet_open",
                    "table_range", "table_filtered") and not win.view.calc.editing():
        win.view.setFocus(qt()[0].Qt.MouseFocusReason)
    win.interactive_prompts = True
    return ctx


def drive(win, command, entry, outcome, ctx, each_index=None):
    via = entry["via"]
    if via == "menu":
        return via_menu(win, entry, outcome, each_index)
    if via == "menu_keys":
        return via_menu_keys(win, entry, outcome, each_index)
    if via == "toolbar":
        return via_toolbar(win, entry, outcome)
    if via == "toolbar_menu":
        return via_toolbar_menu(win, entry, outcome, each_index)
    if via == "widget":
        return via_widget(win, entry, outcome)
    if via == "widget_menu":
        return via_widget_menu(win, entry, outcome, each_index)
    if via == "key":
        return via_key(win, entry, outcome)
    if via == "context":
        return via_context(win, entry, outcome, ctx, each_index)
    if via == "dock_button":
        return via_dock_button(win, entry, outcome)
    if via == "panel_toggle":
        return via_panel_toggle(win, entry, outcome)
    if via == "panel":
        return via_panel(win, entry, outcome)
    if via == "panel_menu":
        return via_panel_menu(win, entry, outcome, each_index)
    if via == "panel_each":
        buttons = panel_group_buttons(win, entry)
        if each_index is None or each_index >= len(buttons):
            outcome["choices"] = len(buttons)
            raise NotReached("not drivable headless: the button set changed under it "
                             "(a category button switches the set)" if each_index is not None
                             else "choice index")
        outcome["choice"] = describe(buttons[each_index])[1]
        return press_widget(win, buttons[each_index], outcome)
    if via == "call":
        return via_call(win, entry, outcome, ctx)
    if via == "viewkey":
        return via_viewkey(win, entry, outcome, ctx)
    if via == "mouse":
        return via_mouse(win, entry, outcome, ctx)
    if via == "nokey":
        raise NotReached("has no key bound (the command itself is exercised by its menu)")
    raise NotReached(f"no route for '{via}' ({entry.get('where', '')})")


def count_choices(win, command, entry, ctx):
    """How many entries a value list ('6 choices: …') has, live."""
    if entry["via"] == "panel_each":
        return len(panel_group_buttons(win, entry))
    outcome = {}
    try:
        drive(win, command, entry, outcome, ctx, each_index=10 ** 6)
    except NotReached:
        pass
    close_popups()
    choices = outcome.get("choices")
    return len(choices) if isinstance(choices, list) else (choices or 0)


def run_one(win, command, entry, each_index=None, shots_dir=None, prefix="x"):
    """Reset, build the state, drive the entry, and record what happened."""
    QtCore = qt()[0]
    SHOTS["dir"], SHOTS["prefix"], SHOTS["n"] = shots_dir, prefix, 0
    result = OrderedDict(id=command["id"], area=command["area"], where=command["where"],
                         name=command["name"], via=entry["via"], entry=entry,
                         choice_index=each_index, state=state_name(command, entry))
    CURRENT.clear()
    CURRENT.update(errors=[], qt_messages=[])
    result["reset_notes"] = reset(win)
    if CURRENT["errors"]:
        result["reset_errors"] = CURRENT["errors"][:]
    CURRENT.clear()
    CURRENT.update(errors=[], qt_messages=[], menu_key=command["where"],
                   choose=entry.get("choose"))
    try:
        ctx = build_state(win, result["state"])
    except Exception as error:  # noqa: BLE001
        result["fixture_error"] = "".join(traceback.format_exception(error))[-1500:]
        ctx = {}
    fixture_errors = list(CURRENT["errors"])
    CURRENT["errors"].clear()
    CURRENT["qt_messages"].clear()
    pump()
    if PICTURES:
        before_img, before = stable_picture(win)
    else:
        settle(40)
        before_img = before = None
    before_sig = doc_signature(win)
    before_sig_unscaled = doc_signature(win, skip_scale=True)
    before_doc = win.document
    before_index = win.undo_stack.index()
    before_count = win.undo_stack.count()
    Watch.reset(entry.get("policy", "cancel"), entry.get("inside"))
    if entry.get("inside"):
        Watch.handled_first = True             # the parent itself is not OK'd
    outcome = {}
    CURRENT["t0"] = None
    start = time.perf_counter()
    reached = False
    try:
        reached = bool(drive(win, command, entry, outcome, ctx, each_index))
        if reached and entry.get("use_tool") or (reached and command["area"] == "Toolbars"
                                                  and entry["via"] == "toolbar") or (
                reached and command["where"].startswith(("Tools ▸ Markup", "Tools ▸ Measure",
                                                         "Tools ▸ Navigation"))):
            end_click = time.perf_counter()
            use_tool_if_picked(win, outcome)
            outcome["t_end_click"] = end_click
    except NotReached as why:
        outcome["not_reached"] = str(why)
    except Exception as error:  # noqa: BLE001
        CURRENT["errors"].append("".join(traceback.format_exception(error)))
    t_trigger = CURRENT.get("t0") or start
    pump(2)                                    # queued work the command posted
    t_done = time.perf_counter()
    settle(60)
    # wait for any dialog the watcher is still closing
    for _ in range(80):
        if qt()[2].QApplication.activeModalWidget() is None and \
                qt()[2].QApplication.activePopupWidget() is None:
            break
        settle(25)
    if not window_gone(win) and qt()[2].QApplication.activeModalWidget() is None:
        back_to_the_window(win, 1.0)           # so the undo key that follows lands
    t_ui = CURRENT.get("t_ui")
    stop = outcome.get("t_end_click") or t_done
    elapsed = ((t_ui if t_ui and t_ui < stop else stop) - t_trigger) * 1000
    # opening a submenu is Qt's hover delay, not the command: not timed
    result["ms"] = None if entry.get("kind") == "submenu" else round(elapsed, 1)
    result["reached"] = reached and "not_reached" not in outcome and not any(
        k in outcome for k in ("missing", "disabled", "error"))
    for key in ("not_reached", "missing", "disabled", "error", "menu_items", "choice",
                "choices", "typed", "chose", "keys", "focus", "spot", "overflow", "hidden",
                "fallback", "tool_used", "popup_shot", "picked"):
        if key in outcome:
            result[key] = outcome[key]
    if window_gone(win) or not PICTURES:
        after_img, after = before_img, before
    else:
        after_img, after = stable_picture(win, tries=4)
    box, share = None, 0.0
    if PICTURES:
        status = win.statusBar()
        ignore = None
        if status.isVisible():
            top_left = status.mapTo(win, qt()[0].QPoint(0, 0))
            ignore = (top_left.x(), top_left.y(), status.width(), status.height())
        box, share = diff_box(before, after, ignore)
    result["changed"] = box is not None
    result["change_box"] = box
    result["change_share"] = round(share, 4)
    result["dialogs"] = CURRENT.get("dialogs", [])
    result["popups"] = CURRENT.get("popups", [])
    result["menus"] = CURRENT.get("menus", [])
    result["errors"] = CURRENT["errors"][:]
    if CURRENT.get("harness_notes"):
        result["harness_notes"] = CURRENT["harness_notes"]
    result["qt_messages"] = CURRENT["qt_messages"][:]
    if fixture_errors:
        result["fixture_errors"] = fixture_errors
    gone = window_gone(win)
    result["window_gone"] = gone
    # did the document change, and does one undo put it back? (a window that
    # was closed has let go of its document and history: nothing to undo)
    same_doc = not gone and win.document is before_doc
    after_sig = doc_signature(win) if same_doc else None
    steps = (win.undo_stack.index() - before_index) if same_doc else None
    result["doc_changed"] = same_doc and after_sig != before_sig
    result["undo_steps"] = steps
    result["doc_replaced"] = not same_doc
    if same_doc and (steps or result["doc_changed"]):
        if steps and steps > 0:
            try:
                win.act_undo.trigger() if win.act_undo.isEnabled() else win.undo_something()
            except Exception as error:  # noqa: BLE001
                result["errors"].append("undo: " + "".join(traceback.format_exception(error)))
            settle(40)
            if outcome.get("tool_used"):
                # the page scale asked for by a first rectangle or measurement is
                # set by its own dialog, not by the drawing: left out here
                undone_sig, before_cmp = doc_signature(win, True), before_sig_unscaled
            else:
                undone_sig, before_cmp = doc_signature(win), before_sig
            result["undo_restores"] = undone_sig == before_cmp
            if not result["undo_restores"]:
                result["undo_diff"] = first_difference(before_cmp, undone_sig)
            if PICTURES:
                undone = as_array(win.grab().toImage())
                vp = win.view.viewport()
                corner = vp.mapTo(win, qt()[0].QPoint(0, 0))
                y0, x0 = max(0, corner.y()), max(0, corner.x())
                ubox, ushare = diff_box(before[y0:y0 + vp.height(), x0:x0 + vp.width()],
                                        undone[y0:y0 + vp.height(), x0:x0 + vp.width()])
                if ubox is not None:
                    ubox = (ubox[0] + x0, ubox[1] + y0, ubox[2], ubox[3])
                result["undo_pixels_left"] = round(ushare, 4)
                result["undo_box"] = ubox
                if SHOTS["dir"] and ubox is not None and ushare > 0.0005:
                    result["undo_shot"] = save_shot(win.grab().toImage(), "undone")
        elif result["doc_changed"] and steps == 0:
            result["undo_restores"] = None
            result["no_undo_step"] = first_difference(before_sig, after_sig)
    if SHOTS["dir"]:
        result["before"] = save_shot(before_img, "before")
        result["after"] = save_shot(after_img, "after")
    result["ok"] = not result["errors"] and not any(
        m.startswith(("critical", "fatal")) for m in result["qt_messages"])
    CURRENT.clear()
    return result


def run_with_fallback(win, command, entry, each_index=None, shots_dir=None, prefix="x"):
    """Run; if the command was disabled in its state, find a state where a
    person could use it (and say so)."""
    result = run_one(win, command, entry, each_index, shots_dir, prefix)
    if result.get("reached") or not result.get("disabled") or entry.get("expect_disabled") \
            or result.get("window_gone"):
        return result
    tried = [result["state"]]
    for state in FALLBACK_STATES:
        if state in tried:
            continue
        tried.append(state)
        again = run_one(win, command, dict(entry, state=state), each_index, shots_dir,
                        prefix + "f")
        if again.get("reached"):
            again["disabled_in"] = result["state"]
            return again
    result["disabled_everywhere_tried"] = tried
    return result


def stable_picture(win, tries=6):
    """The window once it has stopped changing (thumbnails and panels catch up
    on a timer), so 'before' shows the state and not its last repaint."""
    import numpy as np
    image = win.grab().toImage()
    array = as_array(image)
    for _ in range(tries):
        settle(90)
        again = win.grab().toImage()
        again_array = as_array(again)
        if again_array.shape == array.shape and not (np.abs(again_array - array) > 24).any():
            return again, again_array
        image, array = again, again_array
    return image, array


def first_difference(a: str, b: str) -> str:
    if a is None or b is None:
        return ""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"…{a[max(0, i - 80):i + 60]}…  ≠  …{b[max(0, i - 80):i + 60]}…"
    return f"length {len(a)} vs {len(b)}"


def expand(win, command, entry):
    """A value list or a button group is one inventory line but each of its
    entries is run."""
    each = entry.get("kind") == "each" or entry["via"] == "panel_each" or (
        entry.get("path") and entry["path"][-1] == "*")
    if not each:
        return [None]
    reset(win)
    ctx = build_state(win, state_name(command, entry))
    n = count_choices(win, command, entry, ctx)
    if not n and not entry.get("expect_disabled"):
        for state in FALLBACK_STATES:
            reset(win)
            try:
                ctx = build_state(win, state)
            except Exception:  # noqa: BLE001
                continue
            n = count_choices(win, command, entry, ctx)
            if n:
                entry["state"] = state          # run where it can be used (and say so)
                entry["counted_in"] = state
                break
    return list(range(n)) if n else [None]


# ===========================================================================
# 6. a worker runs a slice of the jobs; the parent restarts it after a crash
# ===========================================================================
def worker(out_dir, start, stop, theme, ids_file=None):
    global WIN
    app()
    commands = load_commands()
    if ids_file:
        wanted = set(open(ids_file).read().split())
        commands = [c for c in commands if c["id"] in wanted]
    jobs = jobs_of(commands)[start:stop]
    win = window()
    set_theme(win, theme)
    shots = os.path.join(out_dir, "shots")
    os.makedirs(shots, exist_ok=True)
    vp = win.view.viewport()
    corner = vp.mapTo(win, qt()[0].QPoint(0, 0))
    with open(os.path.join(out_dir, "viewport.json"), "w") as handle:
        json.dump([corner.x(), corner.y(), vp.width(), vp.height()], handle)
    results = open(os.path.join(out_dir, f"results_{start}.jsonl"), "a", encoding="utf-8")
    progress = os.path.join(out_dir, f"progress_{start}.txt")
    for offset, (command, index, entry) in enumerate(jobs):
        n = start + offset
        with open(progress, "w") as handle:
            handle.write(str(n))
        win = window()
        set_theme(win, theme)
        import faulthandler
        faulthandler.dump_traceback_later(150, exit=True)   # a hang: say where, and end
        entry = dict(entry)
        try:
            choices = expand(win, command, entry)
        except Exception as error:  # noqa: BLE001
            choices = [None]
        for choice in choices:
            prefix = f"{command['id']}_{index}" + (f"_{choice}" if choice is not None else "")
            try:
                result = run_with_fallback(win, command, entry, choice, shots, prefix)
            except Exception as error:  # noqa: BLE001
                result = dict(id=command["id"], via=entry["via"], entry=entry, ok=False,
                              harness_error="".join(traceback.format_exception(error))[-2000:])
            result["job"] = n
            result["entry_index"] = index
            results.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            results.flush()
            if WIN is not None and (window_gone(WIN) or result.get("window_gone")):
                dispose(WIN)
                WIN = None
                win = window()
                set_theme(win, theme)
        faulthandler.cancel_dump_traceback_later()
        print(f"{n} {command['id']} {entry['via']}", flush=True)
    with open(progress, "w") as handle:
        handle.write("done")
    results.close()
    os._exit(0)


def set_theme(win, theme):
    """Light or dark, and that is the state every command starts from."""
    want = theme == "dark"
    if win.act_dark.isChecked() != want:
        win.act_dark.setChecked(want)
        pump(3)
        globals()["BASELINE"] = chrome_state(win)


def orchestrate(out_dir, theme="light", workers=2, only=None, timeout=240):
    commands = load_commands()
    ids_file = None
    if only:
        chosen = [c["id"] for c in commands if any(c["id"].startswith(p) for p in only.split(","))]
        ids_file = os.path.join(out_dir, "ids.txt")
        os.makedirs(out_dir, exist_ok=True)
        open(ids_file, "w").write("\n".join(chosen))
        commands = [c for c in commands if c["id"] in set(chosen)]
    total = len(jobs_of(commands))
    os.makedirs(out_dir, exist_ok=True)
    bounds = [(total * k // workers, total * (k + 1) // workers) for k in range(workers)]
    running = {}

    def launch(start, stop, slot):
        args = [sys.executable, os.path.abspath(__file__), "worker", out_dir, str(start),
                str(stop), theme] + ([ids_file] if ids_file else [])
        log = open(os.path.join(out_dir, f"worker_{slot}.log"), "a")
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                                   env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        running[slot] = dict(process=process, start=start, stop=stop, origin=bounds[slot][0],
                             last=time.time(), seen=None)

    for slot, (start, stop) in enumerate(bounds):
        if stop > start:
            launch(start, stop, slot)
    crashes = open(os.path.join(out_dir, "crashes.jsonl"), "a")
    while running:
        time.sleep(2)
        for slot, info in list(running.items()):
            progress = os.path.join(out_dir, f"progress_{info['start']}.txt")
            try:
                mark = open(progress).read().strip()
            except OSError:
                mark = None
            if mark != info["seen"]:
                info["seen"], info["last"] = mark, time.time()
            code = info["process"].poll()
            if code is not None or time.time() - info["last"] > timeout:
                if code is None:
                    info["process"].kill()        # by PID, never by pattern
                    info["process"].wait()
                    code = "timeout"
                del running[slot]
                if mark == "done":
                    continue
                stuck = int(mark) if mark and mark.isdigit() else info["start"]
                crashes.write(json.dumps(dict(job=stuck, code=code)) + "\n")
                crashes.flush()
                if stuck + 1 < info["stop"]:
                    # the worker's results file is keyed by its start: continue in a new file
                    launch(stuck + 1, info["stop"], slot)
    crashes.close()
    merge_results(out_dir)


def merge_results(out_dir):
    results = []
    for name in sorted(os.listdir(out_dir)):
        if name.startswith("results_") and name.endswith(".jsonl"):
            for line in open(os.path.join(out_dir, name), encoding="utf-8"):
                if line.strip():
                    results.append(json.loads(line))
    crashes = []
    path = os.path.join(out_dir, "crashes.jsonl")
    if os.path.exists(path):
        crashes = [json.loads(l) for l in open(path) if l.strip()]
    commands = load_commands()
    jobs = jobs_of(commands)
    for crash in crashes:
        if crash["job"] < len(jobs):
            command, index, entry = jobs[crash["job"]]
            results.append(dict(id=command["id"], area=command["area"], where=command["where"],
                                name=command["name"], via=entry["via"], entry=entry,
                                entry_index=index, job=crash["job"], ok=False,
                                crash=str(crash["code"])))
    unique = OrderedDict()                   # a resumed worker may repeat its first job
    for result in results:
        unique[(result.get("job"), result.get("choice_index"), result.get("id"),
                result.get("via"), result.get("state"))] = result
    results = list(unique.values())
    results.sort(key=lambda r: (r.get("job", 0), r.get("choice_index") or 0))
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=0, default=str)
    return results


# ===========================================================================
# 7. contact sheets
# ===========================================================================
PANE_W, PANE_H, HEAD_H, GAP = 520, 380, 46, 6
ROW_W = 3 * PANE_W + 4 * GAP
ROW_H = HEAD_H + PANE_H + GAP
ROWS_PER_SHEET = 4


def crop_region(box, size, viewport=None):
    """What to show: the change with some room round it, at about the pane's
    shape; a change bigger than a pane shows the canvas instead."""
    width, height = size
    if box is None:
        if viewport:
            x, y, w, h = viewport
            return (x + max(0, (w - PANE_W) // 2), y + 20, min(PANE_W, w), min(PANE_H, h))
        return (width // 2 - PANE_W // 2, 200, PANE_W, PANE_H)
    x, y, w, h = box
    if w > 2 * PANE_W or h > 2 * PANE_H:
        return viewport or (0, 0, width, height)
    aspect = PANE_W / PANE_H
    w2, h2 = max(w + 60, PANE_W), max(h + 60, PANE_H)
    if w2 / h2 > aspect:
        h2 = w2 / aspect
    else:
        w2 = h2 * aspect
    cx, cy = x + w / 2, y + h / 2
    w2, h2 = min(w2, width), min(h2, height)
    x0 = int(max(0, min(width - w2, cx - w2 / 2)))
    y0 = int(max(0, min(height - h2, cy - h2 / 2)))
    return (x0, y0, int(w2), int(h2))


def _paint_pane(painter, image, region, slot, box=None, caption=""):
    QtCore, QtGui = qt()[0], qt()[1]
    left = GAP + slot * (PANE_W + GAP)
    if image is not None and not image.isNull():
        part = image.copy(region) if region is not None else image
        scale = min(PANE_W / max(1, part.width()), PANE_H / max(1, part.height()), 1.0)
        shown = part.scaled(int(part.width() * scale), int(part.height() * scale),
                            QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        painter.drawImage(left, HEAD_H, shown)
        if box is not None and region is not None:
            pen = QtGui.QPen(QtGui.QColor("#ff2a6d"))
            pen.setWidth(1)
            painter.setPen(pen)
            bx = left + (box[0] - region.x()) * scale
            by = HEAD_H + (box[1] - region.y()) * scale
            painter.drawRect(QtCore.QRectF(bx - 2, by - 2, box[2] * scale + 4,
                                           box[3] * scale + 4))
    if caption:
        painter.setPen(QtGui.QColor("#ffd43b"))
        font = painter.font()
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(left, HEAD_H - 17, PANE_W, 16), QtCore.Qt.AlignLeft,
                         caption[:80])


def compose_rows(result, shots_dir, viewport=None):
    """One row per run: before | after | the dialog, popup or undo picture
    (a row more for each further picture)."""
    QtCore, QtGui = qt()[0], qt()[1]
    label = cell_label(result)
    flags = cell_flags(result)
    extras = []
    for kind in ("dialogs", "popups"):
        for record in result.get(kind, []):
            if record.get("shot"):
                extras.append((os.path.join(shots_dir, record["shot"]),
                               f"{kind[:-1]}: {record.get('title') or record.get('kind')} → "
                               f"{record.get('pressed', record.get('picked', ''))}"))
    if result.get("popup_shot"):
        extras.append((os.path.join(shots_dir, result["popup_shot"]), "its popup / submenu"))
    if result.get("undo_shot"):
        extras.append((os.path.join(shots_dir, result["undo_shot"]),
                       "after one undo (canvas differs from before)"))
    before = QtGui.QImage(os.path.join(shots_dir, result["before"])) if result.get(
        "before") else None
    after = QtGui.QImage(os.path.join(shots_dir, result["after"])) if result.get(
        "after") else None
    rows = []
    first = True
    while first or extras:
        row = QtGui.QImage(ROW_W, ROW_H, QtGui.QImage.Format_RGB32)
        row.fill(QtGui.QColor("#202020"))
        painter = QtGui.QPainter(row)
        font = painter.font()
        font.setPixelSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#ffffff"))
        painter.drawText(QtCore.QRect(GAP, 2, ROW_W - 2 * GAP, 20), QtCore.Qt.AlignLeft,
                         label + ("" if first else "  (continued)"))
        font.setBold(False)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#ff6b6b" if flags_bad(result) else "#8ce99a"))
        painter.drawText(QtCore.QRect(PANE_W + 2 * GAP, HEAD_H - 17, 2 * PANE_W, 16),
                         QtCore.Qt.AlignRight, flags[:150])
        slots = range(3)
        if first and before is not None and after is not None and not after.isNull():
            region = QtCore.QRect(*crop_region(result.get("change_box"),
                                               (after.width(), after.height()), viewport))
            _paint_pane(painter, before, region, 0, None, "before")
            _paint_pane(painter, after, region, 1, result.get("change_box"), "after")
            slots = [2]
        for slot in slots:
            if not extras:
                break
            path, caption = extras.pop(0)
            _paint_pane(painter, QtGui.QImage(path), None, slot, None, caption)
        painter.end()
        rows.append(row)
        first = False
    return rows


def menu_rows(menus, shots_dir):
    """Every distinct menu, three to a row, for reading the menus themselves."""
    QtCore, QtGui = qt()[0], qt()[1]
    rows = []
    for n in range(0, len(menus), 3):
        row = QtGui.QImage(ROW_W, ROW_H + 300, QtGui.QImage.Format_RGB32)
        row.fill(QtGui.QColor("#202020"))
        painter = QtGui.QPainter(row)
        for slot, (result, record) in enumerate(menus[n:n + 3]):
            image = QtGui.QImage(os.path.join(shots_dir, record["shot"]))
            left = GAP + slot * (PANE_W + GAP)
            if not image.isNull():
                scale = min(PANE_W / max(1, image.width()),
                            (PANE_H + 300) / max(1, image.height()), 1.0)
                painter.drawImage(left, HEAD_H, image.scaled(
                    int(image.width() * scale), int(image.height() * scale),
                    QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            painter.setPen(QtGui.QColor("#ffffff"))
            font = painter.font()
            font.setPixelSize(13)
            painter.setFont(font)
            painter.drawText(QtCore.QRect(left, 2, PANE_W, 40), QtCore.Qt.TextWordWrap,
                             f"{result['where']}" + (f" ▸ {clean(record['title'])}" if record.get(
                                 "title") else "") + f"  [{result.get('state', '')}]")
        painter.end()
        rows.append((menus[n][0], row))
    return rows


def entry_text(result):
    entry = result.get("entry", {})
    via = entry.get("via", result.get("via"))
    if via in ("menu", "menu_keys"):
        path = " ▸ ".join(entry.get("path", []))
        return ("menu: " if via == "menu" else "Alt+keys: ") + path
    if via == "key":
        return f"key {entry.get('keys')}"
    if via == "context":
        verb = "click" if entry.get("target") == "filter_button" else "right-click"
        return f"{verb} {entry.get('target')}: " + " ▸ ".join(entry.get("path", []))
    if via in ("toolbar", "toolbar_menu"):
        return f"toolbar {entry.get('bar')}: {entry.get('label') or entry.get('button')}"
    if via == "mouse":
        return f"mouse: {entry.get('gesture')}"
    return via + ": " + str(entry.get("label") or entry.get("panel") or entry.get("fn") or
                            entry.get("what") or entry.get("container") or "")


def cell_label(result):
    choice = f" [{result.get('choice')}]" if result.get("choice") else ""
    policy = " (OK)" if result.get("entry", {}).get("policy") == "ok" else ""
    return (f"{result['id']} {result.get('name', '')}{choice}{policy} — "
            f"{entry_text(result)}  · {result.get('state', '')}")[:170]


def flags_bad(result):
    return bool(result.get("errors") or result.get("crash") or result.get("harness_error")
                or result.get("undo_restores") is False or (
                    not result.get("reached", True) and not result.get("entry", {}).get(
                        "expect_disabled")))


def cell_flags(result):
    bits = []
    if result.get("crash"):
        bits.append(f"CRASH {result['crash']}")
    if result.get("errors"):
        bits.append("EXCEPTION")
    if result.get("harness_error"):
        bits.append("HARNESS")
    if not result.get("reached", True):
        why = str(result.get("not_reached") or result.get("missing") or
                  result.get("disabled") or result.get("error"))[:60]
        bits.append(("disabled (expected): " if result.get("entry", {}).get(
            "expect_disabled") else "NOT REACHED: ") + why)
    if result.get("disabled_in"):
        bits.append(f"disabled in {result['disabled_in']}, run in {result.get('state')}")
    if result.get("entry", {}).get("kind") == "submenu":
        result = dict(result, ms=None)          # Qt's hover delay, not the command
    if (result.get("ms") or 0) > 100:
        bits.append(f"SLOW {result['ms']:.0f} ms")
    if not result.get("changed") and not result.get("dialogs") and not result.get("popups"):
        bits.append("NO VISIBLE CHANGE")
    if result.get("undo_restores") is False:
        bits.append("UNDO DOES NOT RESTORE")
    if result.get("no_undo_step"):
        bits.append("CHANGED, NO UNDO STEP")
    if result.get("undo_steps") and result["undo_steps"] > 1:
        bits.append(f"{result['undo_steps']} UNDO STEPS")
    if any(m.startswith(("warning", "critical")) for m in result.get("qt_messages", [])):
        bits.append("QT WARNING")
    if not bits or (len(bits) == 1 and bits[0].startswith("disabled in")):
        bits.append(f"ok {result.get('ms') or 0:.0f} ms" if result.get("ms") is not None else "ok (submenu)")
    return " · ".join(bits)


def area_of(result):
    return {"Menu bar": "menu", "Toolbars": "toolbars", "Right-click menus": "rightclick",
            "Panels": "panels", "Dialogs": "dialogs", "Keys": "keys",
            "Mouse": "mouse", "Extra (not in the inventory)": "extra"}.get(
        result.get("area"), "other")


def make_sheets(out_dir, sheet_root, theme="light"):
    app()
    results = json.load(open(os.path.join(out_dir, "results.json"), encoding="utf-8"))
    shots = os.path.join(out_dir, "shots")
    viewport = None
    meta = os.path.join(out_dir, "viewport.json")
    if os.path.exists(meta):
        viewport = tuple(json.load(open(meta)))
    by_area = defaultdict(list)
    index = []
    for result in results:
        by_area[area_of(result)].append(result)
    written = []
    for area, items in by_area.items():
        rows = []
        for result in items:
            for row in compose_rows(result, shots, viewport):
                rows.append((result, row))
        written += write_sheets(rows, os.path.join(sheet_root, theme, area), index)
    menus, seen = [], set()
    for r in results:
        for m in r.get("menus", []):
            key = (clean(m.get("title") or ""), tuple(m.get("items", [])))
            if m.get("shot") and key not in seen:
                seen.add(key)
                menus.append((r, m))
    written += write_sheets(menu_rows(menus, shots), os.path.join(sheet_root, theme, "menus"),
                            index, per=3)
    with open(os.path.join(sheet_root, theme, "index.json"), "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=0)
    return written


def write_sheets(rows, folder, index, per=ROWS_PER_SHEET):
    QtCore, QtGui = qt()[0], qt()[1]
    os.makedirs(folder, exist_ok=True)
    written = []
    for n in range(0, len(rows), per):
        chunk = rows[n:n + per]
        height = sum(row.height() for _r, row in chunk) + GAP * (len(chunk) + 1)
        sheet = QtGui.QImage(ROW_W, height, QtGui.QImage.Format_RGB32)
        sheet.fill(QtGui.QColor("#555555"))
        painter = QtGui.QPainter(sheet)
        y = GAP
        for _result, row in chunk:
            painter.drawImage(0, y, row)
            y += row.height() + GAP
        painter.end()
        path = os.path.join(folder, f"sheet_{n // per + 1:03d}.png")
        sheet.save(path)
        written.append(path)
        index.append(dict(sheet=os.path.relpath(path, os.path.dirname(folder)),
                          ids=list(OrderedDict.fromkeys(
                              f"{r['id']} {entry_text(r)}" for r, _ in chunk))))
    return written


EDITING_STATES = ("equation_editing", "textbox_editing", "matrix_eq")


def outcome_of(result):
    """passed / failed / expected-disabled / not drivable, for the counts."""
    entry = result.get("entry", {})
    if result.get("state") in EDITING_STATES and result.get("undo_restores") is False and \
            not result.get("errors"):
        result = dict(result, undo_restores=None)  # typing under way: undo takes it too
    if result.get("crash") or result.get("harness_error"):
        return "failed"
    if not result.get("reached", True) or result.get("reached") is False:
        if entry.get("expect_disabled"):
            return "disabled as expected"
        why = str(result.get("not_reached", ""))
        if why.startswith("not drivable headless") or why.startswith("has no key bound"):
            return "not drivable"
        return "failed"
    if result.get("errors") or any(m.startswith(("critical", "fatal"))
                                   for m in result.get("qt_messages", [])):
        return "failed"
    if result.get("undo_steps") and result.get("undo_restores") is False:
        return "failed"
    return "passed"


def report_tables(out_dir, sheet_root=None):
    """Markdown: runs per area and entry point, and every mechanical failure."""
    results = json.load(open(os.path.join(out_dir, "results.json"), encoding="utf-8"))
    sheets = {}
    if sheet_root:
        for theme in ("light", "dark"):
            path = os.path.join(sheet_root, theme, "index.json")
            if os.path.exists(path):
                for record in json.load(open(path, encoding="utf-8")):
                    for key in record["ids"]:
                        sheets.setdefault((theme, key), record["sheet"])
    vias = ["menu", "menu_keys", "toolbar", "toolbar_menu", "widget", "widget_menu", "key",
            "viewkey", "context", "panel", "panel_each", "panel_menu", "panel_toggle",
            "dock_button", "mouse", "call", "nokey", "unknown"]
    names = {"menu": "menu (mouse)", "menu_keys": "menu (Alt+keys)", "toolbar": "toolbar",
             "toolbar_menu": "toolbar menu", "widget": "status/corner/formula bar",
             "widget_menu": "bar button menu", "key": "shortcut", "viewkey": "canvas key",
             "context": "right-click", "panel": "panel control", "panel_each": "panel buttons",
             "panel_menu": "panel menu", "panel_toggle": "rail button",
             "dock_button": "panel title bar", "mouse": "mouse gesture", "call": "by code",
             "nokey": "no key bound", "unknown": "no route"}
    table = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    commands = defaultdict(set)
    for result in results:
        area = result.get("area", "?")
        table[area][result.get("via")][outcome_of(result)] += 1
        commands[area].add(result["id"])
    lines = ["| Area | Entry point | Runs | Passed | Failed | Disabled as expected | "
             "Not drivable |", "|---|---|---:|---:|---:|---:|---:|"]
    totals = defaultdict(int)
    for area in list(SECTION_AREAS) + ["Extra (not in the inventory)"]:
        if area not in table:
            continue
        for via in vias:
            if via not in table[area]:
                continue
            row = table[area][via]
            runs = sum(row.values())
            lines.append(f"| {area} | {names.get(via, via)} | {runs} | {row['passed']} | "
                         f"{row['failed']} | {row['disabled as expected']} | "
                         f"{row['not drivable']} |")
            for k in ("passed", "failed", "disabled as expected", "not drivable"):
                totals[k] += row[k]
            totals["runs"] += runs
    lines.append(f"| **All** | | **{totals['runs']}** | **{totals['passed']}** | "
                 f"**{totals['failed']}** | **{totals['disabled as expected']}** | "
                 f"**{totals['not drivable']}** |")
    per_area = ["| Area | Commands (inventory lines) exercised |", "|---|---:|"]
    for area, ids in commands.items():
        per_area.append(f"| {area} | {len(ids)} |")
    failures = ["| Command | Entry | State | What happened | Sheet |", "|---|---|---|---|---|"]
    for result in results:
        if outcome_of(result) != "failed":
            continue
        what = (result.get("crash") and f"crash ({result['crash']})") or (
            result.get("harness_error") and "harness error") or (
            result.get("errors") and ("exception: " + result["errors"][0].strip().splitlines()[-1])
        ) or (not result.get("reached", True) and "not reached: " + str(
            result.get("not_reached") or result.get("missing") or result.get("disabled")
            or result.get("error"))) or (
            result.get("undo_restores") is False and "one undo does not restore") or \
            "Qt critical"
        key = f"{result['id']} {entry_text(result)}"
        sheet = sheets.get(("light", key), "")
        failures.append(f"| {result['id']} {result.get('name', '')[:50]} | "
                        f"{entry_text(result)[:70]} | {result.get('state')} | "
                        f"{str(what)[:160].replace('|', '/')} | {sheet} |")
    return "\n".join(per_area), "\n".join(lines), "\n".join(failures), totals


# ===========================================================================
# CLI
# ===========================================================================
def main(argv):
    if not argv or argv[0] == "build":
        path = argv[1] if len(argv) > 1 else INVENTORY_MD
        commands = write_commands(path)
        print(f"wrote {COMMANDS_JSON}: {len(commands)} commands, "
              f"{sum(len(c['entries']) for c in commands)} entry points")
        return
    if argv[0] == "worker":
        out_dir, start, stop, theme = argv[1], int(argv[2]), int(argv[3]), argv[4]
        worker(out_dir, start, stop, theme, argv[5] if len(argv) > 5 else None)
        return
    if argv[0] == "run":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--out", required=True)
        parser.add_argument("--theme", default="light")
        parser.add_argument("--only")
        parser.add_argument("--workers", type=int, default=2)
        args = parser.parse_args(argv[1:])
        orchestrate(args.out, args.theme, args.workers, args.only)
        return
    if argv[0] == "try":
        app()
        win = window()
        set_theme(win, os.environ.get("EXERCISE_THEME", "light"))
        commands = {c["id"]: c for c in load_commands()}
        out = os.environ.get("EXERCISE_SHOTS")
        if out:
            os.makedirs(out, exist_ok=True)
        for cid in argv[1:]:
            command = commands[cid.split("#")[0]]
            entries = list(enumerate(command["entries"]))
            if "#" in cid:
                entries = [entries[int(cid.split("#")[1])]]
            for index, entry in entries:
                entry = dict(entry)
                import faulthandler
                faulthandler.dump_traceback_later(60, exit=True)
                for choice in expand(win, command, entry)[:3]:
                    result = run_with_fallback(win, command, entry, choice, out,
                                               f"{command['id']}_{index}")
                    keep = {k: v for k, v in result.items() if k not in (
                        "entry", "menus", "where", "area") and v not in (None, [], {}, False)}
                    print(json.dumps(keep, ensure_ascii=False, default=str)[:1500], flush=True)
        os._exit(0)
    if argv[0] == "report":
        per_area, table, failures, totals = report_tables(argv[1], argv[2] if len(argv) > 2
                                                          else None)
        print(per_area, "\n\n", table, "\n\n", failures)
        return
    if argv[0] == "merge":
        merge_results(argv[1])
        return
    if argv[0] == "sheets":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--out", required=True)
        parser.add_argument("--to", required=True)
        parser.add_argument("--theme", default="light")
        args = parser.parse_args(argv[1:])
        written = make_sheets(args.out, args.to, args.theme)
        print(f"{len(written)} contact sheets under {args.to}")
        os._exit(0)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
