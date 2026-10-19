# Consistency audit, 2026-10-19

The user (2026-10-19): "the Properties panel doesn't show for a table in Calc
mode or for equations; cells don't have the decimal thing like equations in
the right-click menu. Look for other inconsistencies like that."

Compared, for each thing that can be picked: its right-click menu (names,
places, keys, missing commands), whether the Properties panel and the
Properties toolbar show it in each mode, the keys (Delete, Ctrl+C/V/X,
Ctrl+J Duplicate, the arrows, Esc, F2) and the pointer. Measured in the real
window by clicking, right-clicking (the menus' builders), keys through the
shortcut map and hovering; the tests are `tests/test_consistency.py`.

## Why the panel showed nothing

There was no mode check. A click on an equation opens it for typing (SMath),
and a click on a table in Calc mode (or a double-click in Markup mode) opens
its cells (Excel); neither *picks* it, and the panel showed only what was
picked. Now `MainWindow.panel_subjects()` gives the panel, and the
Properties toolbar's label, the picked markups or, with nothing picked, what
is being worked in: the equation or text being typed in, or the table or
spreadsheet open for its cells. The same rule applies in both modes.

## Findings

| Thing | Aspect | What was wrong | Done |
|---|---|---|---|
| Equation | Properties panel | Nothing shown once clicked, in either mode (a click opens it for typing) | **Fixed**: shown while typed in; a panel change first finishes the typing as its own step, then makes its own (one undo step each); the equation stays picked |
| Equation | Properties toolbar | Read "Nothing selected" while typed in | **Fixed**: reads "Equation", as when picked |
| Equation | Panel rows vs right-click | Rows worded differently from the menu ("Decimals", "Threshold", "Significant figures"); no Global, Result unit or Conditional Formatting in the panel | **Fixed**: Result section in the menu's order and words: Variable (what it defines), Decimal Places, Significant Figures, Global, Trailing Zeros, Exponential Threshold, Fractions, Rounding, Result Unit, Document default; Conditional Formatting… in Equation. Each goes through `calcmenu.change`, as the menu does |
| Table (open for its cells) | Properties panel | Nothing shown: always in Calc mode (a click opens the cells, the user's choice), and in Markup mode after a double-click | **Fixed**: Table and a new Cells section (Selection, Number Format, Decimal Places, Significant Figures, Unit, Font, Size, Bold/Italic/Underline, Colour, Fill, Horizontal, Vertical, Wrap Text, Borders, Format Cells…), then Layout and Options. Follows the active cell as it moves |
| Table picked, then opened | Properties panel | Stayed on the picked table's sections (same object, so no rebuild) | **Fixed**: the Cells section comes and goes with the cells being open |
| Spreadsheet page | Properties panel | Nothing shown; when it did show, Layout (X, Y) and Options (Add to Tool Chest) appeared for a sheet that cannot be moved or picked | **Fixed**: General, Sheet (name, size) and Cells; no Layout or Options |
| Cells (sheet and table) | Right-click | No Decimal Places or Significant Figures, which an equation's menu has at the top | **Fixed**: Variable [box], Decimal Places ▸ (General, 0–15), Significant Figures, Global, in the equation's words and order. Decimal Places sets the places of the active cell's format, its kind kept (#,##0.00, 0.0%, 0.00E+00), as Excel's Increase/Decrease Decimal; Significant Figures makes those places count significant figures (SMath's: 0.000 → 12300, 0.00123), a quantity keeping its unit. A new cell style field (`Style.significant`), saved with the document. One undo step each. The formula bar keeps what was typed; the unit box keeps the unit |
| Cells | Right-click | No Properties entry; every markup's menu ends with it | **Fixed**: Properties last, opening the panel on the cells |
| Calculation block | Panel vs right-click | Panel said "Self-contained" and "Remove block, keep equations"; Select Its Equations missing | **Fixed**: Self-Contained, Select Its Equations, Remove Block, Keep Equations (Title Case, as the menus since 2026-10-17) |
| Table (picked) | Panel vs right-click | Panel button "Edit cells", menu "Edit Table" | **Fixed**: Edit Table (same command id) |
| Chart | Panel vs right-click | Panel "Edit chart…", menu "Edit Chart…" | **Fixed**: Edit Chart… |
| Calculation text | Panel | Shown in both modes (it is picked while typed in) | Correct; no change |
| Every markup kind, chart, picture | Panel and toolbar, both modes | Shown, with the same sections in both modes | Correct; no change |
| All kinds | Right-click shared commands | Cut, Copy, Paste, Paste in Place, Paste Here…, Duplicate, Multiply…, Delete (Del), Order, Alignment, Lock (Ctrl+Shift+L), Add to Tool Chest, Properties: same names, places and keys on every kind | Correct; no change |
| Equation, block, table, chart | Right-click | No Format Painter, Flatten, Hide, Set as Default, Apply to Pages | By decision 17 (calc things are not drawn with a markup's pen, never hidden or flattened); consistent within the calc family |
| All kinds | Keys | Delete, Ctrl+C then Ctrl+V, Ctrl+J, Right arrow (nudge), Esc: the same on equation, Calculation text, block, table, rectangle, text box, length and picture | Correct; no change |
| All kinds | F2 | Does nothing on any picked thing; F2 edits only a cell (Excel) | Question 1 |
| Equation | Pointer | The arrow over it, SMath's move cursor on its frame; other markups show the move cursor anywhere on them | WebSMath's own; no change |
| Table | Click by mode | Markup mode: a click picks the table; Calc mode: it opens the cells | The user's choice (in the code); no change |
| Equation | Right-click | No "Edit Equation" where text has Edit Text, a table Edit Table and a chart Edit Chart… | Question 2 |
| Calculation text | Right-click | Offers Flatten, Unflatten, Hide and Show Hidden, and they act; its class says it is "never flattened" | Question 3 |
| Equation (picked) | Properties toolbar | Shows "Equation" with the pen controls greyed; its font, size, colour and B/I/U are only in the panel and the menu, while a table's cells get their own controls in the toolbar | Question 4 |
| Cells | Decimal Places ▸ | No Trailing Zeros entry (an equation's has one): Excel's fixed formats always show trailing zeros. General is offered instead, to go back | Question 5 |
| Cells | Format Cells… and .xlsx | Significant Figures is not in Format Cells, and an exported .xlsx keeps the places but not the significant figures (Excel has none) | Noted; Question 5 |
| Picture / snapshot | Right-click | A picture has "Colour Processing…", a snapshot "Change Colours…" (each opens the same dialog) | Question 6 |
| Equation | Panel width | "Global (Read by Later Calc Sections)" and "Exponential Threshold:" made the panel wider than its dock | The panel says "Global" (the full words in its tooltip) and puts "Exponential Threshold:" on two lines |

## Questions for the lead

1. **F2 on a picked thing.** Should F2 open a picked text box, callout,
   equation or table for editing (Windows' and Excel's convention), or stay
   for cells only? Recommended: open it for editing, as a double-click does.
2. **Edit Equation.** Should an equation's right-click have an "Edit
   Equation" entry (opens it for typing), like Edit Text, Edit Table and Edit
   Chart…? The user fixed the top of the menu as Decimal Places, Significant
   Figures, Global (2026-10-16), so it would go under Equation ▸ or just
   after Global. Recommended: under Equation ▸, first.
3. **Flattening Calculation text.** The right-click offers Flatten and Hide on
   Calculation text, and they work, but `CalcTextItem` says it is "never
   flattened". Should Calculation text follow equations (decision 17: no
   Flatten or Hide), or stay a text box in this? Recommended: follow
   equations.
4. **The Properties toolbar for an equation.** Should a picked equation get
   its own controls on the toolbar (font size, colour, background, B/I/U), as
   a table's cells do? Recommended: yes, as the table's.
5. **Cells' Trailing Zeros and Significant Figures in files.** Should the
   cells' Decimal Places ▸ also have Trailing Zeros (switching 0.00 to 0.##),
   and should Format Cells' Number tab show Significant Figures? An .xlsx
   export cannot carry significant figures: is showing the rounded places
   enough? Recommended: Significant Figures in Format Cells; no Trailing
   Zeros (Excel's 0.## shows "12." for a whole number).
6. **Colour Processing vs Change Colours.** Pick one name for a picture's and
   a snapshot's colour command. Recommended: Revu's own for each, if they
   differ in Revu; otherwise "Colour Processing…" for both.

## Answers (the user, 2026-10-19) and what was done

1. F2 — **Done**: Edit ▸ Edit Selected (`F2`) opens the one picked text box,
   callout, Calculation text, equation or table (at A1), as a double-click
   does; nothing while something is being typed into; in an open table F2 is
   still Edit the cell.
2. Edit Equation — **Done**: first under Equation ▸ (shows F2).
3. Calculation text — **Done**: no Flatten, Unflatten, Hide or Show Hidden on
   its menu; Flatten, Hide and Flatten Markups leave it alone.
4. The toolbar for equations — **Done**: font size, colour and Style ▾ (B, I,
   U) for the picked equations, or the one being typed in; one undo step for
   all of them. No font family (equations use SMath's maths fonts) and no
   strikethrough.
5. (Recommendation taken) — **Done**: Significant Figures in Format Cells ▸
   Number; no Trailing Zeros for cells; the manual says an .xlsx keeps the
   places only.
6. **Done**: a picture's and a snapshot's menu and panel say Colour
   Processing….
