"""The quick gate: the tests for what changed, plus a quick check across every
area (the user, 2026-10-20: "Why is every little change taking 30-45 minute
testing ... is it now testing things that haven't changed"; answer by pop-up:
tiered — the quick gate before each push, the full suite every few pushes and
always before saying a piece of work is finished; docs/AGENT_PROMPT.md §3).

    python tools/qa/quick.py build GATE_OUTPUT    pick the quick check from a full
                                                  run made with --durations=0
    python tools/qa/quick.py run [--base REV] [--workers N]
                                                  run the quick gate on the work
                                                  tree; REV defaults to the pushed
                                                  branch, N to 3 (fewer while
                                                  agents are testing too)

The quick check is the fastest tests of every test file, up to a few seconds
of each file, every test function's quickest case first; it is written to
tools/qa/quick_tests.txt. The run adds every test file that changed, every
test file that imports a module that changed, and the planted-bug check
(mutation_check) when the maths engine changed.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIST = os.path.join(ROOT, "tools", "qa", "quick_tests.txt")
BRANCH = "claude/admiring-archimedes-i371m1"
FILE_BUDGET = 4.0         # seconds of each test file in the quick check
HEAVY_BUDGET = 40.0       # ... of the two files that drive the whole window
HEAVY = {"tests/test_every_command.py", "tests/test_usability.py"}
# what the two heavy files read: a change to any of these runs them whole
EXERCISED = {"tools/qa/exercise.py", "tools/qa/commands.json", "tools/qa/known_failures.json",
             "calcforge/ui/bindable_list.py"}
UNTIMED = 0.25            # a test the full run didn't list took under 0.5 s
# the planted bugs live in these (calcforge/calc/tools/mutation_check.py)
ENGINE = ("calcforge/calc/engine/", "calcforge/calc/worksheet.py", "calcforge/calc/tools/mutation_check.py")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def collect():
    # (pytest.ini already passes -q: one more would list files, not tests)
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    # only the committed test files: a probe left in the work tree is not the suite
    tracked = set(git("ls-files", "tests").split())
    return [line.strip() for line in out.splitlines() if "::" in line and line.split("::")[0] in tracked]


def build(gate_output):
    times = defaultdict(float)
    with open(gate_output, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"^([0-9.]+)s (?:call|setup|teardown)\s+(\S.*?)\s*$", line)
            if m:
                times[m[2]] += float(m[1])
    by_file = defaultdict(list)
    for test in collect():
        by_file[test.split("::")[0]].append((times.get(test, UNTIMED), test))
    chosen, total = [], 0.0
    for path in sorted(by_file):
        budget = HEAVY_BUDGET if path in HEAVY else FILE_BUDGET
        tests = sorted(by_file[path])
        # every test function's quickest case first, then the quickest of the rest
        first, seen = [], set()
        for t in tests:
            name = t[1].split("[")[0]
            if name not in seen:
                seen.add(name)
                first.append(t)
        spent = 0.0
        for t in first + [t for t in tests if t not in first]:
            if spent and spent + t[0] > budget:
                continue
            chosen.append(t[1])
            spent += t[0]
        total += spent
    with open(LIST, "w", encoding="utf-8") as f:
        f.write("# The quick check (tools/qa/quick.py build): the fastest tests of every\n"
                "# test file. Rebuild it after each full run made with --durations=0.\n")
        f.write("\n".join(chosen) + "\n")
    print(f"{len(chosen)} tests from {len(by_file)} files, about {total / 60:.0f} min of one worker")


def changed(base):
    files = set(git("diff", "--name-only", f"{base}...HEAD").split())
    files |= set(git("diff", "--name-only", "HEAD").split())
    files |= set(git("ls-files", "--others", "--exclude-standard").split())
    return {f for f in files if os.path.exists(os.path.join(ROOT, f))}


def tests_for(files):
    """The test files that changed, and those that import a module that did."""
    tests = {f for f in files if re.match(r"tests/(.*/)?test_[^/]*\.py$", f)}
    modules = []
    for f in files:
        if f.endswith(".py") and (f.startswith("calcforge/") or f.startswith("tests/")):
            dotted = f[:-3].replace("/", ".").removesuffix(".__init__")
            package, _, name = dotted.rpartition(".")
            modules.append(re.compile(rf"\b{re.escape(dotted)}\b|from {re.escape(package)} import [^\n]*\b{name}\b"))
    if modules:
        for folder, _, names in os.walk(os.path.join(ROOT, "tests")):
            for n in names:
                if n.startswith("test_") and n.endswith(".py"):
                    path = os.path.join(folder, n)
                    text = open(path, encoding="utf-8").read()
                    if any(m.search(text) for m in modules):
                        tests.add(os.path.relpath(path, ROOT))
    if files & EXERCISED:
        tests |= HEAVY
    if "tests/conftest.py" in files:
        print("tests/conftest.py changed: run the full suite instead")
    return tests


def run(base, workers="3"):
    started = time.time()
    files = changed(base)
    whole = sorted(tests_for(files))
    # (a test renamed or gone since the list was built is left out: pytest
    # would otherwise stop at it before running anything)
    known = set(collect())
    quick = [t for t in open(LIST, encoding="utf-8").read().splitlines()
             if t and not t.startswith("#") and t.split("::")[0] not in whole and t in known]
    print(f"{len(files)} files changed since {base}; {len(whole)} test files run whole, "
          f"plus {len(quick)} quick-check tests")
    for t in whole:
        print("  whole:", t)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as args:
        args.write("\n".join(whole + quick) + "\n")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    try:
        code = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-n", workers, "-rf",
                               f"@{args.name}"], cwd=ROOT, env=env).returncode
    finally:
        os.unlink(args.name)
    if any(f.startswith(ENGINE) for f in files):
        print("the maths engine changed: the planted-bug check")
        code = code or subprocess.run([sys.executable, "-m", "calcforge.calc.tools.mutation_check"],
                                      cwd=ROOT, env=env).returncode
    print(f"QUICK_GATE_EXIT={code} after {(time.time() - started) / 60:.1f} min")
    return code


def main(argv):
    if argv[:1] == ["build"] and len(argv) == 2:
        build(argv[1])
        return 0
    if argv[:1] == ["run"]:
        base = argv[argv.index("--base") + 1] if "--base" in argv else f"origin/{BRANCH}"
        workers = argv[argv.index("--workers") + 1] if "--workers" in argv else "3"
        return run(base, workers)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
