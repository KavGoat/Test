"""Run with:  python -m pytest text_maths/tests"""

import ctypes
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import text_maths_core as core  # noqa: E402
from text_maths_core import process_text  # noqa: E402


def calc(text, mode):
    return process_text(text, mode)


def last(text, mode):
    return calc(text, mode).splitlines()[-1]


# ------------------------------------------------------------ pure maths

@pytest.mark.parametrize("line, expected", [
    ("5+5=", "5+5= 10"),
    ("2^3=", "2^3= 8"),
    ("2**3=", "2**3= 8"),
    ("1/3=", "1/3= 0.333"),
    ("0.05=", "0.05= 0.05"),
    ("0.1+0.2=", "0.1+0.2= 0.3"),
    ("1e7/3=", "1e7/3= 3.333e6"),
    ("2^20=", "2^20= 1048576"),
    ("1/7*1e-5=", "1/7*1e-5= 1.429e-6"),
    ("-2^2=", "-2^2= -4"),
    ("2^3^2=", "2^3^2= 512"),
    ("2pi=", "2pi= 6.283"),
    ("2(3+4)=", "2(3+4)= 14"),
    ("(1+2)(3+4)=", "(1+2)(3+4)= 21"),
    ("3×4÷2−1=", "3×4÷2−1= 5"),
    ("5%*200=", "5%*200= 10"),
    ("√16=", "√16= 4"),
    ("3² =", "3² = 9"),
    ("sin(30)=", "sin(30)= 0.5"),
    ("cos(60)=", "cos(60)= 0.5"),
    ("asin(0.5)=", "asin(0.5)= 30°"),
    ("sin(radians(30))=", "sin(radians(30))= 0.5"),
    ("degrees(pi)=", "degrees(pi)= 180°"),
    ("sin(30°)=", "sin(30°)= 0.5"),
    ("max(1,2,3)=", "max(1,2,3)= 3"),
    ("min([4,2,8])=", "min([4,2,8])= 2"),
    ("lin_int((0,0),(10,100),5)=", "lin_int((0,0),(10,100),5)= 50"),
    ("round(2.567, 1)=", "round(2.567, 1)= 2.6"),
    ("cbrt(-8)=", "cbrt(-8)= -2"),
    ("log(100, 10)=", "log(100, 10)= 2"),
    ("ln(e)=", "ln(e)= 1"),
    ("ge=", "ge= 9.81"),
    ("area = 5*3 =", "area = 5*3 = 15"),
])
def test_pure(line, expected):
    assert calc(line, "pure") == expected


@pytest.mark.parametrize("line, message", [
    ("10/0=", "division by zero"),
    ("(1+2=", "bracket"),
    ("2x=", "unknown name 'x'"),
    ("(-8)^(1/3)=", "fractional power"),
    ("10^400=", "too big"),
    ("asin(2)=", "between -1 and 1"),
    ("sqrt(-1)=", "negative"),
    ("sin=", "needs brackets"),
    ("max(1, 2m)=", "unknown name"),
])
def test_pure_errors(line, message):
    out = calc(line, "pure")
    assert out.startswith(line) and "[Error:" in out and message in out


@pytest.mark.parametrize("text", [
    "hello = world",
    "no equals sign here",
    "if x >= 5 then y = 2",
    "a == b",
    "# 5+5=",
    "Total = 5 bolts",
    "",
])
def test_prose_is_left_alone(text):
    for mode in core.MODES:
        assert calc(text, mode) == text


def test_rerun_recalculates_old_answers_and_errors():
    assert calc("5+5= 11", "pure") == "5+5= 10"
    assert calc("5+5= [Error: old]", "pure") == "5+5= 10"
    assert calc("5+5= 10", "pure") == "5+5= 10"


# ------------------------------------------------------------ units

@pytest.mark.parametrize("line, expected", [
    ("5m+5m=m", "5m+5m= 10m"),
    ("5mm+5mm=", "5mm+5mm= 10mm"),
    ("5 kN + 3 kN =", "5 kN + 3 kN = 8kN"),
    ("1kN+500N=", "1kN+500N= 1.5kN"),
    ("5kN*2m=", "5kN*2m= 10kNm"),
    ("10kN/(2m^2)=", "10kN/(2m²)= 5kPa"),
    ("20kN/m*(6m)^2/8=", "20kN/m*(6m)^2/8= 90kNm"),
    ("10kN/m*2=", "10kN/m*2= 20kN/m"),
    ("5MPa*100mm^2=", "5MPa*100mm²= 500N"),
    ("5MPa*100mm^2 = kN", "5MPa*100mm² = 0.5kN"),
    ("5kN = (N)", "5kN = 5000N"),
    ("6m = mm", "6m = 6000mm"),
    ("1m^2= mm^2", "1m²= 1e6mm²"),
    ("100kN/(300mm*500mm)=", "100kN/(300mm*500mm)= 666.667kPa"),
    ("32MPa*0.85=", "32MPa*0.85= 27.2MPa"),
    ("200GPa*2=", "200GPa*2= 400GPa"),
    ("45kNm/(1.2e6mm^3)=", "45kNm/(1.2e6mm³)= 37.5MPa"),
    ("9.81kg*ge=", "9.81kg*ge= 96.236N"),
    ("2t*ge=", "2t*ge= 19.62kN"),
    ("200mm*(300mm)^3/12=", "200mm*(300mm)^3/12= 450e6mm⁴"),
    ("200mm*300mm^3/12=", "200mm*300mm³/12= 5000mm⁴"),     # 300 mm³, not (300mm)³
    ("2sin(30deg)=", "2sin(30deg)= 1"),
    ("sin(30°)=", "sin(30°)= 0.5"),
    ("asin(0.5)=", "asin(0.5)= 30°"),
    ("atan2(1m, 1m)=", "atan2(1m, 1m)= 45°"),
    ("sqrt(16m^2)=", "sqrt(16m²)= 4m"),
    ("5kn+5KN=", "5kN+5kN= 10kN"),
    ("10mpa*2=", "10MPa*2= 20MPa"),
    ("1 kN = 1000 N", "1 kN = 1000N"),
    ("3m/1.5m=", "3m/1.5m= 2"),
    ("5000mm/1m=", "5000mm/1m= 5"),
    ("max(1m, 500mm)=", "max(1m, 500mm)= 1m"),
    ("round(1.2345m, 2)=", "round(1.2345m, 2)= 1.23m"),
    ("6kNm/(2kN)=", "6kNm/(2kN)= 3m"),
    ("10 kNm + 5 kN*m =", "10 kNm + 5 kN*m = 15kNm"),
])
def test_units(line, expected):
    assert calc(line, "units") == expected


@pytest.mark.parametrize("line, message", [
    ("5kN+2m=", "can't add a force and a length"),
    ("5kN = mm", "the answer is a force, not mm"),
    ("sin(5m)=", "needs an angle"),
    ("2^(3m)=", "plain number"),
])
def test_unit_errors(line, message):
    out = calc(line, "units")
    assert "[Error:" in out and message in out


def test_unit_request_survives_a_rerun_and_an_error():
    once = calc("6m = mm", "units")
    assert calc(once, "units") == once
    bad = calc("5kN = mm", "units")
    assert bad.startswith("5kN = mm [Error:")
    assert calc(bad, "units") == bad


def test_stale_answer_with_wrong_kind_of_unit_is_recalculated():
    assert calc("5+5= 10m", "units") == "5+5= 10"


def test_old_original_format_answers_are_recognised():
    assert calc("b*h = 1066.667e+06mm⁴", "units") == "b*h = 1066.667e+06mm⁴"  # b unknown: left
    assert calc("2m*3m= 6000000mm²", "units") == "2m*3m= 6e6mm²"


def test_units_are_off_in_pure_mode():
    assert "unknown name 'm'" in calc("5m+5m=", "pure")


def test_function_names_are_not_read_as_units():
    # "sin" could be s·in, "min" is minutes: a bracket means a function.
    assert calc("2sin(30)=", "units") == "2sin(30)= 1"
    assert calc("min(3m, 2m)=", "units") == "min(3m, 2m)= 2m"
    assert calc("5min=", "units") == "5min= 5min"


# ------------------------------------------------------------ variables

BEAM = "L = 6m\nw = 10kN/m\nM = w*L^2/8 =\n"


def test_variables_basic():
    assert calc(BEAM, "variables") == "L = 6m\nw = 10kN/m\nM = w*L^2/8 = 45kNm\n"


def test_variables_chain_and_display():
    out = calc("a=5\nb=a*2=\na+b=\nb =", "variables")
    assert out == "a=5\nb=a*2= 10\na+b= 15\nb = 10"


@pytest.mark.parametrize("text, expected", [
    ("x = 5 kN\nx*2 =", "x*2 = 10kN"),
    ("m = 5kg\nF = m*ge =", "F = m*ge = 49.05N"),
    ("L=6m\nL*2 = (mm)", "L*2 = 12000mm"),
    ("b = 200mm\nh = 400mm\nI = b*h^3/12 =", "I = b*h^3/12 = 1.067e9mm⁴"),
    ("a = 2\n2a =", "2a = 4"),
    ("t = 10mm\n2 t =", "2 t = 20mm"),          # spaced: the variable wins
    ("t = 10mm\n2t =", "2t = 2t"),              # attached: always the unit
    ("σ = 5MPa\nσ*2 =", "σ*2 = 10MPa"),
    ("f'c = 40MPa\nf'c/2 =", "f'c/2 = 20MPa"),
    ("f_c = 32MPa\n0.85*f_c =", "0.85*f_c = 27.2MPa"),
    ("M₁ = 3kNm\nM₁*2 =", "M₁*2 = 6kNm"),
    ("N = 500kN\nA = 300mm*300mm\nN/A =", "N/A = 5.556MPa"),
    ("e = 50mm\npi*e =", "pi*e = 157.08mm"),     # a variable hides the constant
    ("E = 200GPa\ne =", "e = 2.718"),            # names are case sensitive
    ("L = 6m\nL2 = L*2 = mm\nL2 =", "L2 = 12000mm"),
    ("x = 5 # comment\nx*2 =", "x*2 = 10"),
    ("m = 5kg\nL = 6m\nL*m =", "L*m = 30kg·m"),
    ("rho = 2400kg/m3\nrho*ge =", "rho*ge = 23.544kN/m³"),
    ("v = 3m/s\nv*2 =", "v*2 = 6m/s"),
])
def test_variables(text, expected):
    assert last(text, "variables") == expected


def test_variable_errors():
    assert "unknown name 'q'" in calc("y = q*2 =", "variables")
    out = calc("x = 5kN + 2m", "variables")
    assert out == "x = 5kN + 2m [Error: can't add a force and a length]"
    assert calc(out, "variables") == out
    # A broken line doesn't stop the rest.
    assert calc("y = q*2 =\nz = 3\nz*2 =", "variables").endswith("z*2 = 6")


def test_assignment_that_is_prose_is_left_alone():
    text = "Note = see drawing\nx = 2\nx ="
    assert calc(text, "variables") == "Note = see drawing\nx = 2\nx = 2"


def test_variables_rerun_is_stable_and_updates():
    once = calc(BEAM, "variables")
    assert calc(once, "variables") == once
    changed = once.replace("L = 6m", "L = 4m")
    assert "M = w*L^2/8 = 20kNm" in calc(changed, "variables")


# ------------------------------------------------------------ substitution

@pytest.mark.parametrize("text, expected", [
    (BEAM, "M = w*L^2/8 = 10kN/m*(6m)^2/8 = 45kNm"),
    ("a=5\nb=a*2=", "b=a*2= 5*2 = 10"),
    ("b = 200mm\nh = 400mm\nI = b*h^3/12 =", "I = b*h^3/12 = 200mm*(400mm)^3/12 = 1.067e9mm⁴"),
    ("a = -2\nb = 3 - a =", "b = 3 - a = 3 - (-2) = 5"),
    ("a = -2\nc = a^2 =", "c = a^2 = (-2)^2 = 4"),
    ("L = 6m\nx = 2L =", "x = 2L = 2*6m = 12m"),
    ("L = 6m\nx = L(1+1) =", "x = L(1+1) = 6m*(1+1) = 12m"),
    ("L = 6m\nx = L² =", "x = L² = (6m)² = 36m²"),
    ("m = 5kg\nF = m*ge =", "F = m*ge = 5kg*9.81m/s² = 49.05N"),
    ("w = 10kN/m\nx = 5kN\nx/w =", "x/w = 5kN/(10kN/m) = 0.5m"),
    ("L=6m\nL*2 = (mm)", "L*2 = 6m*2 = 12000mm"),
    ("L = 6m\nL =", "L = 6m"),
    ("x = 3\ny = 2x + 1 =", "y = 2x + 1 = 2*3 + 1 = 7"),
    ("5+5=", "5+5= 10"),
])
def test_substitution(text, expected):
    assert last(text, "substitution") == expected


def test_substitution_rerun_replaces_old_working():
    once = calc(BEAM, "substitution")
    assert calc(once, "substitution") == once
    changed = once.replace("w = 10kN/m", "w = 20kN/m")
    assert last(changed, "substitution") == "M = w*L^2/8 = 20kN/m*(6m)^2/8 = 90kNm"
    # Switching to the plain Variables script drops the working.
    assert last(once, "variables") == "M = w*L^2/8 = 45kNm"


# ------------------------------------------------------------ text handling

def test_line_endings_and_trailing_newline_are_kept():
    assert calc("x=1\r\ny=x+1=\r\n", "variables") == "x=1\r\ny=x+1= 2\r\n"
    assert calc("1+1=\n\n2+2=\n", "pure") == "1+1= 2\n\n2+2= 4\n"
    assert calc("1+1=\x0b2+2=", "pure") == "1+1= 2\x0b2+2= 4"       # Word soft break
    assert calc("  1+1=  \n", "pure") == "  1+1= 2\n"


def test_non_breaking_spaces_from_word_or_web():
    assert calc("5\xa0kN\xa0+\xa03\xa0kN =", "units") == "5\xa0kN\xa0+\xa03\xa0kN = 8kN"


def test_unexpected_characters_do_not_crash():
    for text in ["5 & 3 =", "x = 'hello'", "=", "==", "= =", "a = = 5", "(" * 2000 + "1=",
                 "1" * 5000 + "=", "€5 =", "5@3=", ")=", "1,2=", "()="]:
        for mode in core.MODES:
            calc(text, mode)        # must not raise


def test_big_input_is_fast():
    lines = [f"x{i} = {i}mm" for i in range(500)] + [f"x{i}*2 =" for i in range(500)]
    text = "\n".join(lines)
    start = time.perf_counter()
    out = calc(text, "substitution")
    assert time.perf_counter() - start < 1.0
    assert out.splitlines()[-1] == "x499*2 = 499mm*2 = 998mm"


@pytest.mark.parametrize("value, text", [
    (0, "0"), (-0.0, "0"), (12.5, "12.5"), (1 / 3, "0.333"), (0.0123456, "0.0123"),
    (1066666666.67, "1.067e9"), (999999.9, "999999.9"), (999999999.9996, "1e9"), (0.0001234, "123.4e-6"),
    (-2.5e7, "-25e6"), (float("inf"), "inf"),
])
def test_number_format(value, text):
    assert core.format_number(value) == text


# ------------------------------------------------------------ clipboard + paste

class FakeSystem:
    def __init__(self, text):
        self.text = text
        self.pasted = False

    def get(self):
        return self.text

    def set(self, text):
        self.text = text

    def paste(self):
        self.pasted = True


@pytest.fixture
def fake(monkeypatch):
    holder = {}

    def make(text):
        holder["system"] = FakeSystem(text)
        monkeypatch.setattr(core, "_Fallback", lambda: holder["system"])
        monkeypatch.setattr(core.sys, "platform", "linux")
        return holder["system"]
    return make


def test_run_pastes_the_result(fake):
    system = fake("L = 6m\nL*2 =\n")
    core.run("variables")
    assert system.text == "L = 6m\nL*2 = 12m\n" and system.pasted


def test_run_does_not_paste_when_nothing_changed(fake):
    system = fake("just some text = here")
    core.run("variables")
    assert not system.pasted


def test_run_does_not_paste_an_empty_clipboard(fake):
    system = fake("")
    core.run("pure")
    assert not system.pasted


def test_run_logs_instead_of_crashing(monkeypatch, tmp_path):
    log = tmp_path / "log.txt"
    monkeypatch.setattr(core, "ERROR_LOG", str(log))
    monkeypatch.setattr(core.sys, "platform", "linux")

    def broken():
        raise RuntimeError("no clipboard")
    monkeypatch.setattr(core, "_Fallback", broken)
    core.run("pure")
    assert "no clipboard" in log.read_text()


class _FakeDLL:
    """Stands in for user32/kernel32 so the Win32 code runs on any OS."""

    def __init__(self, calls):
        self._calls = calls

    def __getattr__(self, name):
        calls = self._calls

        class Function:
            argtypes = restype = None

            def __call__(self, *args):
                calls.append((name, args))
                return {"GetAsyncKeyState": 0, "OpenClipboard": 1, "MapVirtualKeyW": 47,
                        "SendInput": 4}.get(name, 1)
        function = Function()
        setattr(self, name, function)
        return function


def test_windows_paste_sends_ctrl_v(monkeypatch):
    calls = []
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _FakeDLL(calls), raising=False)
    monkeypatch.setattr(core, "PASTE_DELAY_S", 0)
    win = core._Windows()
    assert ctypes.sizeof(win.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
    win.paste()
    count, inputs, size = next(args for name, args in calls if name == "SendInput")
    keys = [(inputs[i].ki.wVk, inputs[i].ki.dwFlags) for i in range(count)]
    assert keys == [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)]
    assert size == ctypes.sizeof(win.INPUT)


def test_windows_paste_waits_for_hotkey_modifiers(monkeypatch):
    calls = []
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _FakeDLL(calls), raising=False)
    monkeypatch.setattr(core, "PASTE_DELAY_S", 0)
    monkeypatch.setattr(core, "MODIFIER_WAIT_S", 0.05)
    win = core._Windows()
    win.user32.GetAsyncKeyState = lambda vk: -32768 if vk == 0x12 else 0   # Alt stuck down
    win.paste()
    count, inputs, _ = next(args for name, args in calls if name == "SendInput")
    keys = [(inputs[i].ki.wVk, inputs[i].ki.dwFlags) for i in range(count)]
    assert keys[0] == (0x12, 2)            # Alt lifted before Ctrl+V
    assert keys[1:] == [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)]


# ------------------------------------------------------------ launchers

LAUNCHERS = {
    "Text Maths - Pure Maths.pyw": "pure",
    "Text Maths - Pure Maths and Units.pyw": "units",
    "Text Maths - Variables.pyw": "variables",
    "Text Maths - Variables with Substitution.pyw": "substitution",
}


@pytest.mark.parametrize("name, mode", LAUNCHERS.items())
def test_launcher_runs_its_mode(name, mode, tmp_path):
    # Run each launcher for real with a stub pyperclip/pyautogui on the path.
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "pyperclip.py").write_text(
        "import os\nF=os.environ['CLIP']\n"
        "def paste(): return open(F, encoding='utf-8').read()\n"
        "def copy(t): open(F, 'w', encoding='utf-8').write(t)\n")
    (stub / "pyautogui.py").write_text(
        "import os\ndef hotkey(*k): open(os.environ['CLIP']+'.keys','w').write('+'.join(k))\n")
    clip = tmp_path / "clip.txt"
    clip.write_text("L = 6m\nL*2 =", encoding="utf-8")
    env = dict(os.environ, CLIP=str(clip), PYTHONPATH=str(stub))
    subprocess.run([sys.executable, os.path.join(ROOT, name)], env=env, check=True)
    expected = {"pure": "L = 6m\nL*2 = [Error: unknown name 'L']",
                "units": "L = 6m\nL*2 = [Error: unknown name 'L']",
                "variables": "L = 6m\nL*2 = 12m",
                "substitution": "L = 6m\nL*2 = 6m*2 = 12m"}[mode]
    assert clip.read_text(encoding="utf-8") == expected
    assert (tmp_path / "clip.txt.keys").read_text() == "ctrl+v"


# ------------------------------------------------------------ unit spelling

@pytest.mark.parametrize("line, mode, expected", [
    ("5kn+3KN=", "units", "5kN+3kN= 8kN"),
    ("10 Mpa*100MM^2 = kn", "units", "10 MPa*100mm² = 1kN"),
    ("5KNm*2 =", "units", "5kNm*2 = 10kNm"),
    ("5 Nmm + 3 NMM =", "units", "5 Nmm + 3 Nmm = 8Nmm"),
    ("6M = mm", "units", "6m = 6000mm"),
    ("5 KG*ge=", "units", "5 kg*ge= 49.05N"),
    ("2 secs + 1 mins =", "units", "2 s + 1 min = 62s"),
    ("sin(30 degrees)=", "pure", "sin(30 deg)= 0.5"),
    ("5kn+2m=", "units", "5kN+2m= [Error: can't add a force and a length]"),
    ("5kn = MM", "units", "5kN = mm [Error: the answer is a force, not mm]"),
    ("w = 10 kn/m\nw*2 =", "variables", "w = 10 kN/m\nw*2 = 20kN/m"),
    ("x = 5kn + 2m", "variables", "x = 5kN + 2m [Error: can't add a force and a length]"),
    ("w = 10kn/m\nL = 6M\nM = w*L^2/8 =", "substitution",
     "w = 10kN/m\nL = 6m\nM = w*L^2/8 = 10kN/m*(6m)^2/8 = 45kNm"),
    ("t = 2 hours\nt =", "variables", "t = 2 hr\nt = 2hr"),
])
def test_misspelt_units_are_corrected_in_the_text(line, mode, expected):
    assert calc(line, mode) == expected


@pytest.mark.parametrize("line, mode", [
    ("Total = 5 KN", "units"),          # not a sum: prose is never touched
    ("5mn=", "units"),                  # mN or MN? too risky to guess
    ("5kn=", "pure"),                   # no units in Pure Maths
])
def test_spelling_is_not_guessed(line, mode):
    out = calc(line, mode)
    assert "kN" not in out and "MN" not in out


def test_corrected_spelling_is_stable_on_rerun():
    once = calc("w = 10kn/m\nL = 6M\nM = w*L^2/8 =", "substitution")
    assert calc(once, "substitution") == once


# ------------------------------------------------------------ unit powers

@pytest.mark.parametrize("line, mode, expected", [
    ("5m2+3m^2=", "units", "5m²+3m²= 8m²"),
    ("I = 450e6mm4\nI*2 =", "variables", "I = 450e6mm⁴\nI*2 = 900e6mm⁴"),
    ("5m^-1*2m=", "units", "5m⁻¹*2m= 10"),
    ("5mm^1=", "units", "5mm= 5mm"),
    ("10 Mpa*100MM2 = kn", "units", "10 MPa*100mm² = 1kN"),
    ("rho = 2400kg/m3\nrho*ge =", "substitution",
     "rho = 2400kg/m³\nrho*ge = 2400kg/m³*9.81m/s² = 23.544kN/m³"),
    ("5m² + 2m^2 = mm^2", "units", "5m² + 2m² = 7e6mm²"),
])
def test_unit_powers_become_superscripts(line, mode, expected):
    assert calc(line, mode) == expected


@pytest.mark.parametrize("line, mode, expected", [
    ("(6m)^2=", "units", "(6m)^2= 36m²"),         # a bracket's power is maths, not a unit
    ("x = 3\nx^2 =", "variables", "x^2 = 9"),
    ("2^3=", "pure", "2^3= 8"),
])
def test_other_powers_are_left_as_typed(line, mode, expected):
    assert calc(line, mode).splitlines()[-1] == expected


# ------------------------------------------------------------ design actions and full sheets

@pytest.mark.parametrize("text, expected", [
    ("M* = 120kNm\nφMs = 180kNm\nM*/φMs =", "M*/φMs = 120kNm/180kNm = 0.667"),
    ("V* = 250kN\ne = 150mm\nMz = V* * e =", "Mz = V* * e = 250kN * 150mm = 37.5kNm"),
    ("M* = 120kNm\n2*M* =", "2*M* = 2*120kNm = 240kNm"),
    ("M* = 120kNm\nM*2 =", "M*2 = 120kNm*2 = 240kNm"),
    ("M = 5kNm\nM* = 120kNm\nM*2 =", "M*2 = 5kNm*2 = 10kNm"),     # M defined: M times 2
    ("N* = 500kN\nφNc = 900kN\nN*/φNc =", "N*/φNc = 500kN/900kN = 0.556"),
    ("x = 3\nx*2 =", "x*2 = 3*2 = 6"),
])
def test_starred_design_actions(text, expected):
    assert last(text, "substitution") == expected


STEEL_BEAM = """# Simply supported steel beam - 310UB40.4
L = 7.2 m
s = 3.0m
G = 1.2 kPa
Q_floor = 3.0kPa
SW = 0.396kN/m
w_G = G*s + SW =
w_Q = Q_floor*s =
w_ULS = 1.2*w_G + 1.5*w_Q =
w_SLS = w_G + 0.7*w_Q =
M* = w_ULS*L^2/8 =
V* = w_ULS*L/2 =
fy = 320MPa
Zex = 633e3 mm3
φ = 0.9
φMs = φ*fy*Zex = kNm
util = M*/φMs =
E = 200GPa
Ix = 86.4e6mm4
δ = 5*w_SLS*L^4/(384*E*Ix) = mm
δ_lim = L/250 = mm
"""


def test_full_steel_beam_sheet_matches_hand_calcs():
    out = calc(STEEL_BEAM, "variables").splitlines()
    answers = {line.split(" =")[0]: line.rsplit("= ", 1)[1] for line in out if line.count("=") >= 2}
    assert answers == {
        "w_G": "3.996kN/m", "w_Q": "9kN/m", "w_ULS": "18.295kN/m", "w_SLS": "10.296kN/m",
        "M*": "118.553kNm", "V*": "65.863kN", "φMs": "182.304kNm", "util": "0.65",
        "δ": "20.849mm", "δ_lim": "28.8mm",
    }
    assert "Zex = 633e3 mm³" in out and "Ix = 86.4e6mm⁴" in out
    once = calc(STEEL_BEAM, "substitution")
    assert calc(once, "substitution") == once


def test_footing_and_concrete_sheets():
    footing = calc("N_G = 850 kN\nN_Q = 400 kN\nB = 2.4m\nqa = 250 kPa\n"
                   "q = (N_G + N_Q)/B^2 =\ncheck = q/qa =\nq_u = (1.2*N_G + 1.5*N_Q)/B^2 =\n"
                   "M_f = q_u*B*((B - 0.4m)/2)^2/2 =", "variables").splitlines()
    assert footing[-4:] == ["q = (N_G + N_Q)/B^2 = 217.014kPa", "check = q/qa = 0.868",
                            "q_u = (1.2*N_G + 1.5*N_Q)/B^2 = 281.25kPa",
                            "M_f = q_u*B*((B - 0.4m)/2)^2/2 = 337.5kNm"]
    slab = calc("f'c = 32 MPa\nb = 1000 mm\nd = 169mm\nAst = 565.487mm2\nfsy = 500 MPa\n"
                "γ = 0.85 - 0.007*(32 - 28) =\nku = Ast*fsy/(0.85*f'c*γ*b*d) =\n"
                "φMu = 0.85*Ast*fsy*d*(1 - 0.5*γ*ku) = kNm", "variables").splitlines()
    assert slab[-3:] == ["γ = 0.85 - 0.007*(32 - 28) = 0.822", "ku = Ast*fsy/(0.85*f'c*γ*b*d) = 0.0748",
                         "φMu = 0.85*Ast*fsy*d*(1 - 0.5*γ*ku) = 39.367kNm"]


def test_hundred_member_sheet():
    rows = []
    for i in range(1, 101):
        rows += [f"L{i} = {3 + i * 0.05:.2f}m", f"w{i} = {5 + i * 0.1:.1f}kN/m",
                 f"M{i}* = w{i}*L{i}^2/8 ="]
    out = calc("\n".join(rows), "substitution").splitlines()
    for i in range(1, 101):
        length, load = round(3 + i * 0.05, 2), round(5 + i * 0.1, 1)
        got = float(out[3 * i - 1].rsplit("= ", 1)[1].removesuffix("kNm"))
        assert abs(got - load * length ** 2 / 8) < 0.001
