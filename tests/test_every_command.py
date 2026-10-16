"""Every command in the feature inventory, by its real UI path (QA_PLAN.md §5).

Parametrized over tools/qa/commands.json (generated from
docs/qa/feature_inventory.md, plus the right-click menus the inventory never
opened, by ``python tools/qa/exercise.py build``): one test per way of
reaching a command — its menu-bar item by mouse, the same by Alt and the arrow
keys, its toolbar button, its right-click entry, its key, its panel control,
its mouse gesture. Each starts from a fresh document in the state the command
applies to (tools/qa/exercise.py's fixtures) and checks the mechanical part:

* it can be reached where a person looks, and is enabled there (or it is a
  line that is meant to be greyed, such as "No recent files");
* no exception and no Qt critical warning;
* no hang — every dialog it opens is caught, photographed and cancelled, and a
  test that still hangs ends its worker after two minutes with a traceback;
* when it changes the document, one undo puts the document back.

Pictures, timings and the visual check are tools/qa/exercise.py's job
(docs/qa/exercise_round1.md). The failures that run found are marked xfail
with their finding (tools/qa/known_failures.json), so a fix shows as XPASS.
Lines that cannot run headless (printing to a printer, the window manager's
buttons) are skipped with the reason; their dialogs are still opened and
cancelled by the menu entries that reach them.

Slow: about 1,900 runs. Use ``-n 2 -p no:cacheprovider`` on a shared machine.
"""
import faulthandler
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

COMMANDS = os.path.join(ROOT, "tools", "qa", "commands.json")
KNOWN = os.path.join(ROOT, "tools", "qa", "known_failures.json")


def _jobs():
    with open(COMMANDS, encoding="utf-8") as handle:
        commands = json.load(handle)["commands"]
    known = {}
    if os.path.exists(KNOWN):
        with open(KNOWN, encoding="utf-8") as handle:
            known = json.load(handle)
    params = []
    for command in commands:
        for index, entry in enumerate(command["entries"]):
            job = f"{command['id']}#{index}"
            marks = []
            if command.get("headless"):
                marks.append(pytest.mark.skip(reason="headless: " + command["headless"]))
            elif job in known:
                marks.append(pytest.mark.xfail(reason=known[job], strict=False))
            label = f"{job}-{entry['via']}-{command['name'][:40]}"
            params.append(pytest.param(command, index, id=label, marks=marks))
    return params


@pytest.fixture(scope="module")
def exercise(qapp):
    from tools.qa import exercise as ex
    ex.app()
    win = ex.window()
    ex.set_theme(win, "light")
    yield ex
    if ex.WIN is not None:
        ex.dispose(ex.WIN)
        ex.WIN = None


def problems_of(ex, command, entry, result):
    """What a person would call broken in one run, in words."""
    what = command["name"] + (f" [{result.get('choice')}]" if result.get("choice") else "")
    if ex.outcome_of(result) != "failed":
        return []                       # passed, greyed as expected, or not drivable
    problems = []
    if result.get("harness_error"):
        problems.append(f"{what}: harness: {result['harness_error'][-400:]}")
    elif not result.get("reached"):
        problems.append(f"{what}: not reached by {entry['via']}: " + str(
            result.get("not_reached") or result.get("missing") or result.get("disabled")
            or result.get("error")))
    for error in result.get("errors", []):
        problems.append(f"{what}: exception: {error[-600:]}")
    for message in result.get("qt_messages", []):
        if message.startswith(("critical", "fatal")):
            problems.append(f"{what}: Qt {message}")
    for dialog in result.get("dialogs", []):
        if dialog.get("would_not_close"):
            problems.append(f"{what}: dialog '{dialog['title']}' would not close")
    if result.get("undo_steps") and result.get("undo_restores") is False:
        problems.append(f"{what}: one undo does not restore the document: "
                        f"{result.get('undo_diff', '')[:300]}")
    return problems or [f"{what}: failed"]


@pytest.mark.parametrize("command, index", _jobs())
def test_every_command(exercise, command, index):
    ex = exercise
    entry = dict(command["entries"][index])
    faulthandler.dump_traceback_later(120, exit=True)     # a hang ends the worker loudly
    try:
        win = ex.window()
        ex.set_theme(win, "light")
        problems = []
        for choice in ex.expand(win, command, entry):
            result = ex.run_with_fallback(win, command, entry, choice)
            if ex.WIN is not None and (ex.WIN.isHidden() or result.get("window_gone")):
                ex.dispose(ex.WIN)
                ex.WIN = None
                win = ex.window()
            problems += problems_of(ex, command, entry, result)
        assert not problems, "\n".join(problems)
    finally:
        faulthandler.cancel_dump_traceback_later()
