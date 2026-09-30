"""Do the proof tests really catch wrong numbers and units?

Each mutation below plants one realistic bug in a throw-away copy of the
package (a wrong unit factor, a lost dimension, a rounding mode, a missed
recalculation...) and runs the proof tests against it.  Every mutation must
make the tests FAIL; one that passes would mean a kind of wrong answer the
tests cannot see.

    python -m markforge.calc.tools.mutation_check        (from the repository root)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]          # markforge/calc
ROOT = PKG.parents[1]                               # the repository

# (what the bug is, file, original text, planted text)
MUTATIONS = [
    ("lbf factor off in the 14th digit", "engine/unitdata.py", "'lbf': (4.4482216152605,", "'lbf': (4.4482216152606,"),
    ("Mega prefix 10^5 instead of 10^6", "engine/extra_units.py", '("M", "Mega", 1e6)', '("M", "Mega", 1e5)'),
    ("multiplying adds dims wrongly", "engine/units.py", "return tuple(_clean(x + y) for x, y in zip(a, b))",
     "return tuple(_clean(x + y + (x < 0)) for x, y in zip(a, b))"),
    ("dividing adds dims instead of subtracting", "engine/units.py",
     "return tuple(_clean(x - y) for x, y in zip(a, b))", "return tuple(_clean(x + y) for x, y in zip(a, b))"),
    ("square root keeps the dims", "engine/units.py", "return tuple(_clean(x * p) for x in a)",
     "return tuple(_clean(x * (p if p != 0.5 else 1)) for x in a)"),
    ("division off by one part in 10^9", "engine/values.py", "return Q(x.value / y.value,",
     "return Q(x.value / y.value * (1 + 1e-9),"),
    ("sqrt slightly wrong", "engine/builtins.py", "return _out(sqrt_value(q.value), dims_scale(q.dims, 0.5))",
     "return _out(sqrt_value(q.value * 1.000001), dims_scale(q.dims, 0.5))"),
    ("shown unit's factor ignored ('P = 0.1 P bug)", "engine/display.py", "scale = unit_factor(unit)",
     "scale = unit_factor(unit) if unit_text(unit) != 'kN' else 1.0"),
    ("rounds half up instead of half-to-even", "engine/numformat.py",
     "mode = ROUND_HALF_EVEN if fmt.half_even else ROUND_HALF_UP", "mode = ROUND_HALF_UP"),
    ("rounds down (truncates)", "engine/numformat.py",
     "mode = ROUND_HALF_EVEN if fmt.half_even else ROUND_HALF_UP", "mode = 'ROUND_DOWN'"),
    ("exponent not carried when 9.99995 rounds to 10", "engine/numformat.py", "            exp += 1\n",
     "            pass\n"),
    ("recalculation ignores a unit change", "worksheet.py", "return a.dims == b.dims and (a.value == b.value",
     "return (a.value == b.value"),
    ("recalculation misses names read through functions", "engine/evaluator.py",
     "        if self.reads is not None:\n            self.reads.add(n.name)\n", ""),
    ("unit box conversion uses the wrong factor", "engine/unitdata.py", "'mm': (0.001,", "'mm': (0.0010001,"),
]

TESTS = ["tests/calc/test_proof_end_to_end.py", "tests/calc/test_proof_units.py", "tests/calc/test_number_fuzz.py",
         "tests/calc/test_recalc_fuzz.py", "tests/calc/test_verify.py"]


def run(tmp: Path) -> bool:
    env = dict(os.environ, PYTHONPATH=str(tmp), PROOF_EXAMPLES="150", QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:faulthandler", "-p", "no:cacheprovider",
                        *TESTS], cwd=tmp, env=env, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    missed = 0
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # a copy of the application package and the tests, run from the copy
        # (the tests import markforge.calc, so the copy has to be first on the path)
        ignore = shutil.ignore_patterns("__pycache__")
        shutil.copytree(ROOT / "markforge", tmp / "markforge", ignore=ignore)
        shutil.copytree(ROOT / "tests", tmp / "tests", ignore=ignore)
        shutil.copytree(ROOT / "SMath Studio" / "examples", tmp / "SMath Studio" / "examples")
        shutil.copy2(ROOT / "pytest.ini", tmp / "pytest.ini")
        if not run(tmp):
            print("the unmutated copy fails its tests - fix that first")
            return 2
        for what, rel, old, new in MUTATIONS:
            f = tmp / "markforge" / "calc" / rel
            src = f.read_text()
            assert src.count(old) >= 1, f"mutation text not found: {what}"
            f.write_text(src.replace(old, new, 1))
            try:
                caught = not run(tmp)
            finally:
                f.write_text(src)
            missed += not caught
            print(f"{'caught' if caught else 'MISSED'}  {what}", flush=True)
    print(f"\n{len(MUTATIONS) - missed}/{len(MUTATIONS)} planted bugs caught")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
