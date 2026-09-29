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

## Timing of evaluation

* The region being edited is **re-evaluated on every keystroke**. `2+3=` shows
  `= 5` the moment `=` is typed, while the region is still being edited.
  Nothing about the result looks different from a result computed later.
* Other regions are **not** recalculated while you type. Changing `q:=5` to
  `q7:=5` left `q = 5` below it unchanged until the definition lost focus. Then
  the whole sheet was recalculated, and `q =` became `q - not defined.`

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

* In a math region holding **only a name** (`abc`, `x`, `x1`), pressing
  **space** converts the region to a **text region**. `abc` + space + `def`
  gives the text "abc def".
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

## Autocomplete

A list appears as soon as a name is typed. It is **substring, case-insensitive**:
`k` offers `'stokes`, `'week`, `rank`, `stack`. It contains **units** (with their
apostrophe), built-in **functions** (overloads listed as `sum (1)`/`sum (4)`),
**constants** `π e i ∞`, keywords `break continue`, and the worksheet's own
**variables**. Units come first, then everything else, each group sorted
alphabetically ignoring case.

Styling: white background, black border, 12 px text, 90 px high with a
scrollbar. The selected item is white on #9faab5. Up/Down moves, Tab or Enter
picks, Esc closes. The full function and unit lists are in `engine/catalog.py`
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
