# QA findings — the one deduplicated list

Kept by the lead agent (docs/AGENT_PROMPT.md §5). One line per finding, newest
round at the top. Status: open · fixing (who) · merged · pushed · decision
(waiting on the user) · not a bug.

## Round 3 — Revu parity audit, 2026-10-15

The full report is docs/qa/revu_audit.md (groups A–N). It finds mostly misplaced,
misnamed, or prompt-instead-of-dialog commands, and no shared "Pages" range
control anywhere. Status: open, queued after round 2 merges.

User's decisions (pop-up):
- Ctrl+M is Multiply in Markup mode and Matrix in Calc mode. The other Revu keys
  are adopted (Ctrl+D Document Properties, Ctrl+9/0/8 zoom, Alt+panel keys,
  Shift+F4 Hide Panels).
- Page Setup follows Revu's layout and really resizes the content (Auto Scale,
  Scale, Offset, Rotation, Center, Fit to Media), with a preview and a Pages range.
- Build Revu's Print dialog, with the preview folded in. Print Pages… opens it
  with Selected chosen. The per-page and per-markup print ticks stay.
- UK spelling app-wide (Colour, Centre).

Lead's calls, under "behave like Revu, keep everything":
- Add Distribute and Flip to Alignment.
- Keep Spacing, Corner Radius and Hatch Opacity at the end of Appearance.
- Move the CalcForge-only items into a CalcForge section rather than delete them.

## Round 2 — 2026-10-15

| # | Sev | Finding | Area | Status |
|---|---|---|---|---|
| 2.1 | High | An equation variable read into a cell shows base SI (M=35 kN·m comes out as 35000 J) | sheet/units | fixing (cell-units doer) |
| 2.2 | High | General-format numbers show #### instead of rounding to fit (Excel) | sheet/numfmt, items/table | fixing (Excel doer) |
| 2.3 | High | The window can't be narrower than ~1180 px; the status bar never gives way | ui/mainwindow status bar | fixing (window doer) |
| 2.4 | High | `var(F)` gives Excel's VAR (#DIV/0!) when a cell is also named F | sheet/formula | fixing (Excel doer) — decided: variable if one exists |
| 2.5 | Med | `max(1,2)=` (and min, sum, atan2, lg) becomes a broken definition | calc/engine/builtins | fixing (equations doer) |
| 2.6 | Med | `)` doesn't close the bracket: `(1+2)*3=` gives 7 | calc/editor | fixing (equations doer) — decided: close it |
| 2.7 | Med | Cell units drawn black with a caret (m^2), unlike equations | items/table | fixing (cell-units doer) — decided: blue + superscripts |
| 2.8 | Med | Cell errors (#UNITS!, #DIV/0!, #NAME?…) never explained | sheet, ui/tableedit | fixing (Excel doer) |
| 2.9 | Med | A column dragged to zero width is a broken "ghost", not hidden | ui/tableedit | fixing (Excel doer) |
| 2.10 | Med | Calculation toolbar mostly in the overflow chevron at 1280 px | ui/mainwindow toolbars | fixing (window doer) |
| 2.11 | Med | An incompatible output unit is accepted silently | ui/cellunits, tablebar | fixing (cell-units doer) |
| 2.12 | Low | DATE()/TODAY() show a serial number, not a date | sheet | fixing (Excel doer) |
| 2.13 | Low | Cloud path has a hook at the SE corner where it closes | items (cloud) | fixing (window doer) |
| 2.14 | Med | Allow Markup Recovery lives in Preferences, not the Flatten dialog (Revu) | ui/dialogs FlattenDialog | fixing (dialogs doer) |
| 2.15 | Med | Set Scale dialog doesn't look or work like Revu's (pages, preset/custom, calibrate, precision, presets) | ui/dialogs ScaleDialog | fixing (dialogs doer) |
| 2.16 | — | Every dialog, panel and menu vs the Revu manual | all | auditing (Revu-parity auditor) |
| 2.17 | — | No shortcut may fire while typing (text box, callout, label, Search, typed size, equation, cell, formula bar) | ui | text box, callout, cell: 0 of 152 keys leak; rest running |

## Round 1 — 2026-10-15 (pushed, gated at f67fd82)

| # | Sev | Finding | Status |
|---|---|---|---|
| 1.1 | High | Nudge/drag/Ctrl+A with 400 markups picked took seconds | pushed |
| 1.2 | Med | Home/End went to the top/bottom of the current page (Home even went forward); Revu: first/last page | pushed |
| 1.3 | Med | Ctrl+Left/Right didn't turn pages (Revu) | pushed |
| 1.4 | Low | Redo only Ctrl+Shift+Z on Linux; Revu's Ctrl+Y added | pushed |
| 1.5 | Low | Revu keys missing: V, Shift+V, Ctrl+Shift+M/U, Ctrl+3, Ctrl+Shift+L | pushed |
| 1.6 | Med | Page right-click menu lacked Revu's Add Note/Bookmark/Flag, Next/Prev Page, Print, Search | pushed |
| 1.7 | — | Dragging a 400-markup selection by one markup's edge moved nothing (seen before and after 1.1) | open — re-check in the bug hunter's round |

## Not bugs (harness or by design)
- The plain wheel zooms and Ctrl+wheel scrolls — Revu's default, by design.
- SMath-style `name(…)=` with `;` separators works; `,` is the case in 2.5.
