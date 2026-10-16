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
  test that still hangs ends its worker after four minutes, its stacks left in
  the temp folder as test_every_command-hang-<job>-<pid>.txt;
* when it changes the document, one undo puts the document back.

Pictures, timings and the visual check are tools/qa/exercise.py's job
(docs/qa/exercise_round1.md). The failures that run found are marked xfail
with their finding (tools/qa/known_failures.json), so a fix shows as XPASS.
Lines that cannot run headless (printing to a printer, the window manager's
buttons) are skipped with the reason; their dialogs are still opened and
cancelled by the menu entries that reach them.

About 2,150 runs, 8 minutes at ``-n 3 -p no:cacheprovider`` (the rows of
Keyboard Shortcuts with no key bound are skipped).
"""
import faulthandler
import tempfile
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

COMMANDS = os.path.join(ROOT, "tools", "qa", "commands.json")
KNOWN = os.path.join(ROOT, "tools", "qa", "known_failures.json")
STALE = ("  If the command was renamed or moved on purpose, rebuild the list: "
         "python tools/qa/inventory.py && python tools/qa/exercise.py build. If it is "
         "gone, that is a regression.")


def _jobs():
    with open(COMMANDS, encoding="utf-8") as handle:
        commands = json.load(handle)["commands"]
    known = {}
    if os.path.exists(KNOWN):
        with open(KNOWN, encoding="utf-8") as handle:
            known = json.load(handle)
    from tools.qa.exercise import job_keys          # no Qt is touched by the import
    keys = job_keys(commands)
    only = None
    if os.environ.get("QA_EXERCISE_ONLY"):        # a file of "M0123#0" lines, to re-run a few
        with open(os.environ["QA_EXERCISE_ONLY"], encoding="utf-8") as handle:
            only = {line.split()[0] for line in handle if line.strip()}
    params = []
    for command in commands:
        for index, entry in enumerate(command["entries"]):
            job = f"{command['id']}#{index}"
            if only is not None and job not in only:
                continue
            marks = []
            reason = known.get(keys[(command["id"], index)])
            if command.get("headless"):
                marks.append(pytest.mark.skip(reason="headless: " + command["headless"]))
            elif entry["via"] == "nokey":
                # Keyboard Shortcuts lists every command so any can be bound;
                # one with no key yet has nothing to press (its menu, toolbar
                # and right-click entries are tested on their own lines)
                marks.append(pytest.mark.skip(reason="no key bound"))
            elif reason:
                marks.append(pytest.mark.xfail(reason=reason, strict=False))
            label = f"{job}-{entry['via']}-{command['name'][:40]}"
            params.append(pytest.param(command, index, id=label, marks=marks))
    return params


@pytest.fixture(scope="module")
def exercise(qapp):
    """The harness, with one window it reuses. On the way out it hands the
    process back as it found it (tools/qa/exercise.py shutdown()): its
    dialog-closing timers stopped, its exception and Qt-message recorders
    taken off, its window closed, the clipboard and the settings empty, the
    application's own palette — so it cannot change any other test file's
    run, whatever order xdist gives them."""
    from tools.qa import exercise as ex
    ex.PICTURES = False                 # pictures are for the contact sheets
    ex.app()
    win = ex.window()
    ex.set_theme(win, "light")
    try:
        yield ex
    finally:
        ex.shutdown()


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
        if result.get("missing") or str(result.get("not_reached", "")).startswith("no "):
            problems.append(STALE)
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


def run_entry(ex, command, entry):
    win = ex.window()                   # a new one if the last command closed it
    ex.set_theme(win, "light")
    problems = []
    for choice in ex.expand(win, command, entry):
        result = ex.run_with_fallback(win, command, entry, choice)
        win = ex.window()
        problems += problems_of(ex, command, entry, result)
    return problems


@pytest.mark.parametrize("command, index", _jobs())
def test_every_command(exercise, command, index):
    ex = exercise
    entry = dict(command["entries"][index])
    # A hang ends the worker loudly; xdist drops a dead worker's stderr, so the
    # stacks go to a file named after the job as well (in the temp folder).
    hang_log = open(os.path.join(tempfile.gettempdir(), "test_every_command-hang-"
                                 f"{command['id']}-{index}-{os.getpid()}.txt"), "w")
    faulthandler.dump_traceback_later(240, exit=True, file=hang_log)
    try:
        problems = run_entry(ex, command, entry)
        if problems:
            # The window is reused from command to command, and reset() puts
            # back everything known to matter; anything it misses would make a
            # result depend on which test xdist ran before this one. So a
            # failure is judged again on a window built for it alone.
            ex.dispose(ex.WIN)
            ex.WIN = None
            problems = run_entry(ex, command, entry)
        assert not problems, "\n".join(problems)
    finally:
        faulthandler.cancel_dump_traceback_later()
        hang_log.close()
        os.remove(hang_log.name)
