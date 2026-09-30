# How SMath Cloud behaves: research notes

These are the notes the replica is built from. Everything here was observed
on **smath.com/en-US/cloud** (SMath Studio Cloud) on 29 Sep 2026 by typing into
worksheets and reading back what the server rendered. Where the SMath Studio
install in `smath/SMath Studio/` gave data (unit table, file format, example
worksheets), that is noted as well.

## How the research was done

The web editor sends every keystroke to the server and waits for the reply,
which took 4–15 s through this environment's proxy. The page drops keys typed
while it is waiting: until the server answers, a new region has no id yet, and
the client throws away keys aimed at it (`resetPendingFocusedElement`). A
"please wait" layer (`.dialog-box-layer`) also swallows input. Driving the page
with a simulated keyboard therefore gave scrambled results (`x=5` came out as
`x5 := ■`).

The fix was to talk to the same endpoint the page uses, strictly one request
at a time:

```
POST /en-US/cloud/srv
{"Id": sheet, "Revision": n, "Data": null,
 "Changes": [{"Data": {"Action": "="}, "$id": 9}], "$id": 5}
```

* A new region is `{"Data": {"Left": x, "Top": y, "Focused": true, "Action": key}, "$id": 8}`.
* A key typed into the focused region is `{"Data": {"Action": key}, "$id": 9}`.
  Key names are `LEFT RIGHT UP DOWN BACK DELETE TAB ENTER SENTER EMPTY`.
* Leaving a region is `{"Data": {"Focused": false}}`.
* Undo is `Data: {"Actions": "Undo"}`.
* `Revision` must equal the sheet's current revision, or the server returns 500.
  The `$id` values are type tags (5 = update, 8 = add region, 9 = update region)
  and must match.
* The reply lists every changed region with its rendered SVG, `ErrorText`, and a
  `Suggestions` flag. When the flag is set, `GET /cloud/srv/{sheet}/suggestions`
  returns the autocomplete list. `GET .../functions` and `GET .../units` return
  the Insert Function and Insert Unit catalogues.

Every experiment was saved as SVG and error text, rendered to PNG, and read
back. The catalogues are stored in `websmath/engine/catalog.py`.

## Worksheet and regions

* The page is a **9 px grid**. Clicking empty space moves a small **red cross**
  (9×9) there, snapped to the grid. Typing starts a new math region at the cross.
* A region being edited is drawn on white with a **1 px grey frame**. Text starts
  4 px in, and a single-line region is 24 px tall.
* **Enter** leaves the region and puts the cross just below it.
* **Tab** moves focus to the next region, wrapping from the last back to the first.
* An empty region disappears when you leave it.
* Regions are evaluated in **reading order**: top to bottom, then left to right.
  A region only sees definitions above it. Moving a line above the definition it
  uses turns it into an error: `x - not defined.`

## Timing of evaluation (and how the replica stays fast)

* The region being edited is **re-evaluated on every keystroke**. `2+3=` shows
  `= 5` the moment `=` is typed, while the region is still being edited.
  Nothing about the result looks different from a result computed later.
* Other regions are **not** recalculated while you type. Changing `q:=5` to
  `q7:=5` left `q = 5` below it unchanged until the definition lost focus. Then
  the whole sheet was recalculated, and `q =` became `q - not defined.`

The replica keeps every definition in an index ordered by position, so
"what is x here" is a binary search. When a region is left, only the regions
below it that use a changed name (directly or through a function or another
definition) are re-evaluated, and only regions whose result changed are
redrawn. With 3000 regions, a keystroke takes about 7 ms and leaving a region
that 1500 others depend on about 0.1 s. A region that runs for more than 10 s
(a runaway `while`) is interrupted with an error instead of freezing the
window.

## `=` means define or evaluate

| Typed | Result |
|---|---|
| `x=` with `x` not defined above | becomes `x := ■` with the cursor on the ■. **`=` acts like `:`** |
| `x=` with `x` defined above | `x = 5`, evaluated immediately |
| `x:9` | `:` always defines (redefinition allowed) |
| `a=b` (both undefined) | `a := b`, no error: definitions may be symbolic |
| `abc=` then leave | `abc := ■`, error **"Fill in all empty elements."** |
| `log(100)=` | log has no 1-argument form, so it becomes the *definition* `log(100) := ■`, error **"Syntax is incorrect."** with `100` outlined |
| `max(1,5,3)=` | max takes one matrix, so this is a definition too. Same error |
| `f(3)=` with `f(t)` defined | evaluates |

After `=`, the **cursor stays on the left-hand side**. Typing `7` after `x=`
gives `x7 = ■`, error `x7 - not defined.`

## Typing and the cursor

* The cursor is an **L shape**: a line under the operand being edited, plus a
  vertical bar at the insertion point.
* `*` is shown as `·`. `:` is shown as `:=`.
* **`/` takes only the operand to the left** of the cursor as the numerator and
  moves into the denominator. `2*3/4` is 2·(3/4) = 1.5, and `1+2/4=` is 1 + 2/4 = 1.5.
  **Typing then continues in the denominator**: `1/7*1000=` is 1/(7·1000) = 0.0001.
* **`^` opens an exponent, and typing continues inside it.** `a^2+1` is a^(2+1).
  Right-arrow leaves the exponent: `a^2` → `+1` gives a²+1.
* **`)` does not close a bracket.** `(1+2)*3=` typed straight through gives
  (1+2·3) = 7. Right-arrow leaves the bracket: `(1+2` → `*3=` gives 9.
  The same applies to `sin(0.5)*2=`, which is sin(1).
* `name.x` is a literal subscript: `x.1` shows as x₁.
* `M[1` is an index, shown as M₁.
* `:` inserts `:=` at the cursor, wherever it is.
* Some words followed by `(` become structures:
  * `if(` → an if/else block
  * `line(` → a vertical-bar block
  * `mat(` → an empty **2×2** matrix (commas are ignored inside cells)
  * `sqrt(` → a radical
  * `nthroot(x,n` → a radical with index n (`nthroot(3,27)` is 3^(1/27) = 1.0415)
  * `abs(` → |x|
* Some calls are drawn in maths notation: `log(8,2)` as log₂(8) and `det(M)` as |M|.
* `for(`, `while(` and other names stay as function calls; the
  for/while blocks come from the Programming toolbox.
* Inside an if-block a comma moves from the condition to its value. A comma
  after a value adds an **else if** branch.

## The cursor and the arrow keys

Read back from the site's SVG, which draws the cursor as a vertical bar plus
an underline:

* **The underline covers the whole name or number** the cursor is in, not
  just the part to its left. At the start of a name it underlines the name to
  the right.
* **Left/Right move one character at a time inside a name and jump over
  operators.** From the start of `ef` in `ab+cd·ef`, Left goes straight to the
  end of `cd`.
* **The "whole sub-expression" state.** At the start of the first name of a
  sub-expression, Left does not move. It extends the underline over the
  whole sub-expression (`cd·ef`). The next Left leaves it (to the end of
  `ab`). At the very start of the expression the whole expression is
  underlined, and Left stays there. Right across an operator
  (`ab` → `+` → `cd`) lands in the same state. Right from the state
  returns to the plain cursor at the start of `cd`.
  * Typing `/` in this state gives ■/(cd·ef), with the cursor in the empty
    numerator. `^` gives ■^(cd·ef).
  * An operator such as `+` is inserted in front of it.
  * Letters are ignored.
  * Backspace removes the operator before it.
* **Boxes:**
  * Left from the start of an exponent goes to the end of the base. Left from
    the start of a function argument goes to the end of the function name.
  * Left from the start of a denominator goes to the end of the numerator.
  * Right at the end of a box leaves it, underlining the whole box (with the
    function name).
  * In a matrix, Right walks the cells row by row. An empty ■ has a stop
    before it and one after it.
* **Up/Down move to the previous/next region** in reading order, even from
  inside a fraction. The cursor comes back where it was left in that region.

## Calls drawn as structures

A call is drawn by its name and number of arguments. Typing `while(` shows
`while(■)`, but once the second argument exists it is the while-block. The
toolbox inserts the complete forms (its buttons type `for(,,`, `while(,`,
`sum(,,,`…):

| Call | Drawn as |
|---|---|
| `for(i, r, body)` | `for i ∈ r` with the body indented |
| `while(c, body)` | `while c` with the body indented |
| `if(c, a, b)` | if / else block (appears as soon as `if(` is typed) |
| `try(a, b)` | `try` / a / `on error` / b |
| `line(…)` | vertical bar with one line per argument (`]` adds a line) |
| `sum(e, i, a, b)`, `product(…)` | Σ / Π with `i = a` below and `b` above |
| `int(e, x, a, b)` | ∫ with limits, then `e dx` |
| `diff(e, x)` | d/dx e |
| `log(x, b)` | log_b(x) |
| `range(a, b)`, `range(a, b, s)` | [a..b], [a, s..b] |
| `el(v, i)` | v with subscript i |
| `sys(…)` | brace list |
| `nthroot(x, n)` | ⁿ√x |
| `a † b` | a × b (cross product, Ctrl+8) |
| `≈`, `≉` | approximately (not) equal |

## Toolbox and menus

The toolbox sections are Arithmetic, Matrices, Boolean, Functions, Plot,
Programming and the Greek letters, with the site's tooltips; the table above
lists what their buttons type.

The menus are:

* **File:** New Worksheet, Upload (Ctrl+O), Save, Share, Download as, Print
  (Ctrl+P), Properties.
* **Edit:** Undo (Ctrl+Z), Redo (Ctrl+Y), Cut/Copy/Paste, Delete, Select all.
* **View:** Grid, Dynamic assistance (autocomplete on/off).
* **Insert:** Matrix (Ctrl+M), Function, Unit, Picture, Plot 2D/3D, Area,
  Formula, Separator, CheckBox, ComboBox, Modeller, Text region.
* **Calculation:** Solve, Calculate, Simplify, Invert, Differentiate,
  Determinant, Auto calculation, Recalculate page (F9).
* **Format toolbar:** font size, text colour, background colour, border.

## Typing over a selection

Selections are made with **space** (the web client has no Shift+arrow
selection) or by dragging with the mouse inside the region being edited.
Observed with the cursor after the 3 of `1+2·3`:

* **Space cycles** between the sub-expressions that contain the cursor.
  The first press selects `2·3`, the second the whole `1+2·3`, the third
  `2·3` again. A lone name or number is not a level of its own.
* The keys typed next:

  | Key | Selection `2·3` | Selection `1+2·3` |
  |---|---|---|
  | `(` | 1+(2·3) | (1+2·3) |
  | `)` | nothing | nothing |
  | `/` | 1 + 2·3/■ | 1+2·3 / ■ (selection becomes the numerator) |
  | `^` | 1+(2·3)^■ | (1+2·3)^■ |
  | `\` | 1+√(2·3) | √(1+2·3) |
  | `-`, `+` | 1+2·3−■ | 1+2·3−■ |
  | `*` | 1+2·3·■ | (1+2·3)·■ (bracketed because · binds tighter) |
  | a letter | nothing | nothing |

* `|` is **logical OR** (∨) in SMath, not absolute value (use `abs(`).

## Text regions

* In a math region holding **only a name or a number** (`abc`, `x`, `x1`,
  `2`, `2.5`, `sin`, `x.1`, even a name that is defined above), pressing
  **space** converts the region to a **text region**. `abc` + space + `def`
  gives the text "abc def", and `x.1` becomes the literal text "x.1".
* Anywhere else space is never inserted: after an operator, `:` or `=`
  (`q+1 `, `w: `, `q= `) it widens the selection instead.
* `"` as the first key also starts a text region.
* **Backspace never turns text back into maths**; it just deletes characters.
  **Undo** steps back one keystroke at a time, including the conversion itself.
* Space inside a real expression (`1+2 `) does not convert.
* Text regions use a sans font, with a black frame while being edited.

## Numbers, decimal places, significant figures

The defaults are **4 decimal places**, **exponential threshold 5**, trailing
zeros off, and decimal (not fractional) results. The same defaults are in
every `.sm` file's `<calculation>` settings.

| Typed | Shown |
|---|---|
| `1/3` | 0.3333 |
| `2/3` | 0.6667 |
| `10/4` | 2.5 |
| `1.50` | 1.5 |
| `22/7` | 3.1429 |
| `99999` | 99999 |
| `12345.6789` | 12345.6789 |
| `123456` | 1.2346·10⁵ |
| `100000.5` | 1·10⁵ |
| `1234567.8` | 1.2346·10⁶ |
| `0.001234` | 0.0012 |
| `0.00001234` | 1.234·10⁻⁵ |
| `-2.25` | −2.25 |

The rule: a number whose decimal exponent is at least the threshold, or at most
minus the threshold, is written as mantissa·10ⁿ. Otherwise it is rounded to the
decimal places, and trailing zeros are dropped. SMath also has **significant
figures mode**, **trailing zeros** and **rounding** (half to even or away from
zero) options (strings from `Text_ENG.lang`). The replica has all of these under
the Calculation menu.

## Units

* A unit is typed with an apostrophe: `3'mm` shows `3 mm`, with the unit in
  **blue**, a small space and no multiplication dot. A bare `m` is an ordinary
  **variable**: `L:2*m` then `L=` gives `m - not defined.`
* Unit fractions: `2'kN/'m` is 2·(kN/m), with only the unit going over the bar.
* A product of two units is drawn with a space (`kg m`), not a dot.
* Results use SMath's derived-unit table (`Units.xml` `<dimensions>`):

  | Typed | Result |
  |---|---|
  | `3'kN` | 3000 N |
  | `2'kN*3'm` | 6000 J |
  | `5'MPa` | 5·10⁶ Pa |
  | `9.81'kg*'m/'s^2` | 9.81 N |
  | `3/'s` | 3 Hz |
  | `100'kPa*2'm^2` | 2·10⁵ N |
  | `5'm/'s` | 5 m/s (stacked fraction) |
  | `2'kg/'m` | 2 kg/m |
  | `2'm^3` | 2 m³ (litres are never chosen) |
  | `1'in*1'in` | 0.0006 m² |
  | `1'ft` | 0.3048 m |
  | `sqrt(2'm)` | 1.4142 m^(1/2), with the power drawn as a fraction |
  | `20'°C` | 293.15 K |
  | `60'deg` | 1.0472 (angles are dimensionless) |
  | `2'kN/'m` | SMath shows **2000 m Pa** (one base unit next to a derived unit, when base units would need s² or worse in the denominator). **The replica deliberately shows 2000 N/m instead**, and similarly N/m³, W/m², J/K and W/m |

* **Unit mismatch**: `L+3's=` gives **"Units don't match."**, with the whole
  `L + 3 s` outlined in red.
* **Units in an exponent** (`'m^2/'s^2` typed straight through gives m^(2/s²)):
  **"Operation cannot be performed with units."**
* **Converting a result**: a result carries a unit placeholder ■. It is shown
  after the result, even after an automatic unit, while the region is being
  edited. Right-arrow at the end of the expression moves into it, and what you
  type there is parsed as maths, so units need the apostrophe (`cm` alone gives
  `cm - not defined.`). Double-clicking the unit of an answer opens it for editing.

## 2-D plots

Read from SMath's example worksheets (`.sm` plot regions) and from SMath
Cloud's rendering of the MaclaurinSeries example:

* The plot area is white with a black 1 px frame, **#d3d3d3 grid lines**
  every unit, and **black axes** through the origin labelled `x` (right
  end) and `y` (top).
* Tick numbers are **#808080, 8 pt**: x values along the bottom edge (every
  2 units at 20.5 px/unit) and y values along the left edge (every unit).
* Curves are drawn in list order in **blue #0000ff, red #ff0000**, then
  further colours.
* The input sits **under** the plot: one expression, or several shown as a
  list with a left brace (stored as `sys(e1, e2, …, n, 1)`). Each expression
  is a function of `x`; a two-column matrix is drawn as connected points.
* Files store `scale_x`/`scale_y` (1.6347 means 20.5 px per unit),
  `transpose_x`/`transpose_y` (the origin's offset from the centre in pixels)
  and `grid`/`axes` flags.
* `@` inserts a plot. In the replica the wheel zooms (Ctrl for x only,
  Shift for y only), dragging inside the plot pans, and the corner square
  resizes.

## Errors

The offending part is outlined with a **rounded red box** and drawn in red. The
result becomes ■. While the region is being edited, a tip appears under it
(#ffffe1 background, black 1 px border, 11 px text). Messages seen:

* `y - not defined.`
* `f(#) - function is not defined.`
* `Units don't match.`
* `Operation cannot be performed with units.`
* `Fill in all empty elements.`
* `Syntax is incorrect.`
* `Logarithm of zero is not defined.` (`ln(0)`)
* `Division by zero.` (`1/0`, and also `0/0`)
* `Result is above max. allowed positive number.` (`exp(1000)`, `10^400`,
  `171!`, `cot(0)`)
* `Uncertainty.` (`0^0`)
* `Factorial is defined for real numbers and zero.` (`3.5!`; the site's
  wording)
* `Coefficient of rounding should be in the range from 0 to 15 inclusive.`
  (`round(12345.6789,-2)`)
* `Operation cannot be performed with units.` also for `sin(1'm)`

## Subscripts (`.`)

* `x.1` draws x with subscript 1. The cursor and its underline move into the
  subscript: the underline covers **only the subscript** while the cursor is
  after the dot, and **only the base** before it. The cursor bar drops to the
  subscript's line.
* Backspace in `x.1` removes `1` and leaves an **empty subscript** (the
  underline is then empty); a second Backspace removes the dot.
* `x.` followed by an operator drops the empty subscript: `x.+1` is `x+1`.
* Left through `ab.cd`: inside `cd`, to the start of the subscript, then to
  the end of `ab` (underline switches to `ab`), then inside `ab`.
* Inside a subscript a further dot is literal (`x.1.2`: subscript `1.2`).
  In a number a second dot is ignored (`2.5.3` is `2.53`); `.5` is 0.5.
* Units, constants and function names take subscripts too (`5'm.x`,
  `'g.e`, `f.a(x)`); a power goes after the subscript (`x.1^2`).

## Number then letter

A letter or `(` typed straight after a number inserts a multiplication:
`2x` is `2·x`, `2i` is `2·i`, `2(` is `2·(■)`, `3.5a` is `3.5·a`. There is no
`e` notation: `2e3` is `2·e3`. `2'm` stays a number with a unit, and `x2` is a
name.

## Functions (results checked on the site)

`sqrt(-1)` = i; `asin(2)` = 1.5708−1.317i and `acos(2)` = 1.317i (.NET branch
cuts); `ln(-1)` = 3.1416i; `mod(-7,3)` = −1 and `mod(7,-3)` = 1 (the
remainder takes the sign of the dividend); `round(2.5)`-style rounding is half
away from zero; `floor/ceil/trunc(-2.5)` = −3/−2/−2; `sin(π)` and `cos(π/2)`
are exactly 0 but `tan(π/2)` = 1.6331·10^16; `170!` = 7.2574·10^306;
`perc(5,200)` = 10; `sin(1+2i)` = 3.1658+1.9596i. Typing `name(args)=` for a
function that has no overload with that many arguments (`round(2.5)`,
`log(0)`, `gcd(12,18)`, `max(1,5,3)`) turns `=` into `:=` (a definition).

## Constants

SMath's physical constants live in its unit library and are typed like units:
`'c 'e 'g.e 'G.N 'h 'hildebrand 'k 'm.e 'm.n 'm.p 'N.A 'R.m 'u 'ε.0 'μ.0`,
plus the operands `π e i ∞`. The site shows them as:
`'g.e` = 9.8066 m/s² (9.80665 is stored as 9.806649999…), `'c` = 2.9979·10^8 m/s, `'h` = 6.6261·10^-34 s J,
`'k` = 1.3807·10^-23 J/K, `'N.A` = 6.0221·10^23 1/mol, `'R.m` = 8.3145
J/(K mol), `'ε.0` = 8.8542·10^-12 F/m, `'μ.0` = 1.2566·10^-6 m T/A, `'m.e`,
`'m.p`, `'m.n`, `'u` in kg, `'e` = 1.6022·10^-19 C and `'hildebrand` =
2045.48 kg^(1/2)/(s m^(1/2)). **`'G.N` is not evaluated on the site** (it shows
`1 G.N`, like any unknown unit such as `'σ`); the replica gives it its
library value, 6.6743·10^-11 m³/(kg s²). Insert > Constants... lists them all.

## Errors while typing, and the unit box

* A region without `=` or `:=` shows **no error**: `test`, `x+1` and the
  partial `100kg*g.e` stay clean until `=` is typed (observed). The
  replica still runs such regions (a `for` loop in one assigns variables).
* After `=` the result is followed by a small box for the desired unit
  (SMath's placeholder is the glyph "H" of its SMath Equations font: 5×7 px,
  on the baseline, 1 px after the unit). A matching unit converts the
  result (980.665 N → 0.9807 kN); a unit that does not match stays at the
  end and SMath fills in what is missing (980.665 m/s² kg).

## Right-click menu

Read from the site (`GET /srv/{sheet}/contextmenu`). Everywhere: Cut
(Ctrl+X), Copy (Ctrl+C), Paste (Ctrl+V) | Delete (Del) | Select all (Ctrl+A).
On a math region, then: **Display input data** (checked) | Go to definition,
Show description, Disable evaluation | Ignore units | **Optimization**
(Symbolic, Numeric, None; Numeric is checked for `x=`, Symbolic for `x:`),
**Decimal places** (Trailing zeros | Significant figures mode | 0-15),
**Exponential threshold** (0-15), **Fractions** (Decimal, Fraction, Auto,
Default | Use mixed numbers, greyed while Decimal), **Rounding** (Half to
even, Away from zero). The worksheet's value is marked `*` (`4 *`, `5 *`).
The settings belong to the one region. Effects seen on the site:

| Region | Option | Shows |
|---|---|---|
| `1/3=` | Decimal places 2 | 0.33 |
| `1234.5678=` | Significant figures mode | 1235 |
| `0.012345=` | Significant figures mode | 0.01235 |
| `1.5=` | Trailing zeros | 1.5000 |
| `12345=` | Exponential threshold 2 | 1.2345·10^4 |
| `1.23*10^9=` | Exponential threshold 15 | 1230000000 |
| `1/(3+1/4)=` | Fraction | 4/13 |
| `0.75=` | Auto | 3/4 |
| `7/3=` | Fraction + mixed numbers | 2 1/3 |
| `2+3=` | Display input data off | 5 (only the result) |
| `5'm+2=` / `5'm*2'kg=` | Ignore units | 7 / 10 |
| `2+3=` | Optimization None | 2+3 |
| `2.00025=` | (default rounding) | 2.0002 |

**Rounding** is half to even by default and works on the binary value: 2.00025
is stored as 2.000249999… and shows 2.0002, and 9.80665 ('g.e) shows 9.8066.
Only exact binary ties (0.125 to 2 places) depend on the option: 0.12 to even,
0.13 away from zero. The replica saves the options on `<math>` as SMath does
(`decimalPlaces`, `significantDigitsMode`, `trailingZeros`, `optimize`: 0
none, 1 symbolic, 2 numeric). "Show description" is shown but greyed out;
"Symbolic" is numeric here (there is no symbolic engine). A text region's
menu (language, line spacing, alignment, automatic replacement) is not
copied.

## A variable with a unit's name

After `m:10`, `m=` shows 10 and `m*2'm=` shows 20 m: **the variable wins over
the unit**, and `'m` is still the metre. The autocomplete list for `m` shows
both (unit m with the unit icon, highlighted; variable m with the worksheet
icon). The replica keeps this but makes the choice explicit: while the name
under the cursor is both a defined variable and a unit, keys that would finish
the name (operators, `=`, `:`, Enter, arrows, Tab out) are refused and the list
opens; pick the variable or the unit with Up/Down and Tab (or Enter, or a
click). The unit becomes `'m`; the variable stays `m`. Names that are not both
are typed as usual.

## Autocomplete

A list appears as soon as a name is typed. The replica's list has been
checked item for item against 18 lists read back from the site. The rules:

* **Worksheet variables and functions appear only if they are defined above**
  the region being edited.
* **Order:** units first, then everything else (functions, keywords,
  `lastError`, variables) mixed. Each group uses .NET culture order: symbols
  first (`\\ % ‰ ° ¤`), then digits, then letters ignoring case and accents
  (`'Å` sorts with `a`), with Greek after Latin. On a tie, lower case comes
  first.
* **Units differing only in case appear once on the site:** a over A, pA
  over Pa, s over S, t over T, kn over kN, G over g, Mg over mg, MJ over mJ,
  pC over pc. The hidden spellings still work when typed. **The replica
  lists both** (kn, then kN), because hiding kN and Pa from engineers is
  unhelpful.
* Arc minute and arc second are listed as `'\\0027\\` and `'\\0022\\`.
* **What each entry shows** (from the site's own client code): the name
  **without the unit apostrophe**, after a 12×12 icon chosen by kind
  (function if it takes arguments, unit if it starts with `'`, operand
  otherwise) and origin (1 SMath core, 2 plugin, 3 this worksheet). The
  icons are copied from the site's stylesheet into `ui/icons/`. **Values of
  variables are not shown.** The entry's description (the unit's name, or
  the function's signature with the name in bold and arguments in blue) is
  shown in a tooltip box to the right of the list: 12 px, InfoBackground,
  black border, at most 200 px wide. Variables have no description, so no
  tooltip. All descriptions are in `engine/suggest_meta.py`.
* **Highlighted when the list opens:** the first entry whose name starts with
  the typed text, case-sensitive first (`m` → unit m, `M` → MB, `q` → qq),
  else ignoring case (`Si` → sign), else none. A name typed in full is still
  listed (`qq` lists qq).
* **Keys:** Esc closes; **Tab** applies the highlighted entry; **Enter**
  applies it only once the list has been moved through with Up/Down; Up/Down
  from nothing highlighted go to the last/first entry; one click applies an
  entry. A function is inserted with its brackets (`sqrt` becomes the
  radical).

Matching is **substring, case-insensitive**:
`k` offers `'stokes`, `'week`, `rank`, `stack`. It contains **units** (with their
apostrophe), built-in **functions** (overloads listed as `sum (1)`/`sum (4)`),
**constants** `π e i ∞`, keywords `break continue`, and the worksheet's own
**variables**. Units come first, then everything else, each group sorted
alphabetically ignoring case.

Styling: white background, black border, 12 px text, at least 90 px wide,
90 px high at most, with a scrollbar. The selected item is white on #9faab5. The full function and unit lists are in `engine/catalog.py`
(129 functions, 284 units).

## Styling of equations (`representation/settings.prop` and the SVG)

* Equations use a 10 pt monospace font (Courier New) on the web.
* User-defined variables and functions are *italic*. Built-in constants (π, e)
  are **bold**. Built-in functions are upright. Units are blue (#0000ff).
  Strings are #a31515.
* Operators have about 2.5 px of padding on each side. Placeholders are small
  black squares.

## Functions (catalogue from the site)

* **Elementary:** abs, sqrt, nthroot, exp, ln, log(x,b), log10, sign, mod,
  floor, ceil, trunc, round(x,n), Gamma, perc, random, `!`
* **Trigonometric and hyperbolic:** sin, cos, tan, cot, sec, csc; asin, acos,
  atan, atan(x,y), acot, asec, acsc; the hyperbolic versions and their inverses
* **Matrices:** mat, matrix, identity, det, invert, transpose, rows, cols,
  length, el, row, col, tr, diag, max, min, sum, sort, csort, rsort, reverse,
  augment, stack, submatrix, minor, vminor, alg, rank, norm1, norme, normi,
  range, linterp, cinterp, ainterp, polyroots
* **Programming:** if, for (3 and 4 arguments), while, line, try, break,
  continue, error
* **Strings:** concat, strlen, substr, strrep, findstr, num2str, str2num, IsString
* **Other:** sum/product over a range, int (numeric), diff (numeric), solve,
  IsDefined, UnitsOf, eval, Re, Im, arg, pol2xy, xy2pol

SMath also has a symbolic engine: symbolic differentiation, polynomials in an
undefined variable, Jacobians and Hessians. The replica evaluates numerically;
those example worksheets are listed as symbolic in the tests.
