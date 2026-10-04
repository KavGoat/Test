# Text Maths

Select text anywhere (Notepad, Word, Outlook, Excel, OneNote), press a hotkey,
and every line that asks for an answer gets one. The new text replaces the
selection. Lines that aren't sums are left exactly as they were.

| Launcher | Units | Variables | Shows working |
|---|:-:|:-:|:-:|
| `Text Maths - Pure Maths.pyw` | angles only | | |
| `Text Maths - Pure Maths and Units.pyw` | ✓ | | |
| `Text Maths - Variables.pyw` | ✓ | ✓ | |
| `Text Maths - Variables with Substitution.pyw` | ✓ | ✓ | ✓ |

All four are three-line launchers. The engine, clipboard and paste code is in
`text_maths_core.py`, so **keep all five files in the same folder.**

## Setup

1. Python 3.8+ on Windows. Nothing to `pip install`: the clipboard and Ctrl+V
   go through the Windows API directly. On macOS/Linux it uses `pyperclip`
   and `pyautogui` instead.
2. Load `Text Maths.ahk` (AutoHotkey v2), or copy its `TextMaths()` function
   into your own script. Hotkeys are Ctrl+Alt+1 … 4.

If your own AHK script just does `Send "^c"` and then runs Python, add the
`A_Clipboard := ""` / `ClipWait` lines. Without them Python can read the
*previous* clipboard and paste that.

If something goes wrong, the error is written to `text_maths_error.log` next
to the scripts (pythonw has no window to show it in).

## Writing sums

```
5+5=                      ->  5+5= 10
sin(30)=                  ->  sin(30)= 0.5        angles are degrees
5mm+5mm=                  ->  5mm+5mm= 10mm       answers follow your units
5MPa*100mm^2 = kN         ->  5MPa*100mm^2 = 0.5kN    ask for a unit
6m = (mm)                 ->  6m = 6000mm         brackets are fine too
5kN+2m=                   ->  5kN+2m= [Error: can't add a force and a length]
```

**Variables** (the two Variables launchers):

```
L = 6m                    remembered, nothing printed
w = 10kN/m
M = w*L^2/8 =             ->  M = w*L^2/8 = 45kNm
M = w*L^2/8 =             ->  M = w*L^2/8 = 10kN/m*(6m)^2/8 = 45kNm   (with Substitution)
M =                       ->  M = 45kNm
L2 = L*2 = mm             ->  L2 = L*2 = 12000mm   (L2 is kept in mm from then on)
```

**Run it again any time.** Old answers, old working and old `[Error: …]`
notes are recalculated. A unit you asked for (`= mm`) is kept. So you can
change `L = 6m` to `L = 7m`, select the block, and press the hotkey again.

### Rules worth knowing

- **A number with letters stuck to it is a unit**: `5m`, `2t` (tonnes),
  `300mm`. With a space, a variable of that name wins: `2 t` is 2 × t.
  Use `2*t` or `2 t` for "twice the variable t".
- **`300mm^3` is 300 mm³**, not (300 mm)³. Write `(300mm)^3`, or use a variable.
- Implicit multiplication works: `2pi`, `2L`, `2(a+b)`, `(a+b)(c+d)`.
- `^`, `**` and superscripts are all powers: `x^2`, `x**2`, `x²`, `mm⁴`.
- `×`, `÷`, `−`, `·` and non-breaking spaces from Word or the web are fine.
- Variable names: letters (Greek too), digits, `_`, `'` and subscripts:
  `f'c`, `M_Ed`, `σ`, `M₁`. They are case sensitive (`E` ≠ `e`). A variable
  hides a constant of the same name (`e = 50mm`).
- `# comment` lines are skipped; `x = 5  # note` works on assignments.
- Numbers: 3 decimals, 3 significant figures below 0.1, and engineering
  notation outside 0.001 – 1e6 (`450e6mm⁴`, `1.067e9mm⁴`). Change `DECIMALS`
  at the top of `text_maths_core.py`.

**Units:** N kN MN lbf kip · g kg t · mm cm m km in ft · s min hr ·
Pa kPa MPa GPa psi ksi · rad deg ° · and force×length together, such as kNm, Nmm.
**Misspelt units are corrected in your text** on any line that gets calculated:
`5kn` → `5kN`, `10Mpa` → `10MPa`, `100MM^2` → `100mm^2`, `KNm` → `kNm`,
`6M` → `6m`, `KG` → `kg`, `secs`/`mins`/`hours`/`degrees` → `s`/`min`/`hr`/`deg`.
Other single letters (N, s, g, t) must be typed exactly, and `mn` is left alone
(mN or MN?). Prose lines are never changed. Combine units with
`/` `*` `·` and powers: `kN/m`, `kN/m^2`, `m/s²`, `kg/m3`.

When the inputs don't give a tidy unit, the answer uses kN or N for force,
kPa or MPa for stress, kNm for moment, mm²/m² for area and mm⁴ for second
moment of area.

**Functions:** sin cos tan asin acos atan atan2 · sqrt cbrt abs · round floor ceil
(rounded in the unit shown) · min max · lin_int((x1,y1),(x2,y2),x) ·
log(x[, base]) ln log10 log2 exp · radians degrees. **Constants:** pi (π), e, ge (9.81 m/s²).

## Tests

```
python -m pytest text_maths/tests
```
