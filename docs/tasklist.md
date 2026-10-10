# Task list

Previous entries were deleted at the user's request on 2026-09-27; the register
restarts with the report below. Completion status is user-owned.

## Standing instruction: calculations are back (2026-09-30)

Calculations were withdrawn on 2026-09-07, and the handover used to say never
to build them back. **The user overrode that on 2026-09-30, on purpose:**
calculations return as WebSMath (the SMath Studio replica), and the app becomes
**CalcForge**. Calculations, equations, plots, matrices, program blocks,
calculation blocks and Calculation text are wanted features. No future session
may remove them or treat them as leftovers. Work is on branch
`claude/admiring-archimedes-i371m1`; the MarkForge branch
(`claude/markforge-mupdf-pdf-handling-vpyj1t`) and the WebSMath branch
(`claude/zealous-clarke-8yiu03`) are read-only sources.

## Withdrawn

| Withdrawn | Instruction that withdrew it |
| --- | --- |
| ~~`.sm` files: opening, importing and saving SMath worksheets in CalcForge~~ | 2026-09-30: "No `.sm` files at all. Old `.sm` files are opened in the standalone WebSMath app." |
| ~~SMath's Ctrl+G (Greek) and the units-list key (Ctrl+W)~~ | 2026-09-30: "aren't needed". |
| ~~Pint as MarkForge's unit system~~ | 2026-09-30: "One unit system: SMath's … Pint is removed." |
| ~~Calculations withdrawn (2026-09-07)~~ | 2026-09-30: overridden; see the standing instruction above. |

## Requests reported 2026-09-27

| Complete | Task |
| --- | --- |
|  | Snapshot selection preview must look like the normal selection marquee but dashed. It currently replicates the last rectangle drawn. |
|  | Correctly drawn PDFs exported from Revit show a red cross over certain elements. Source content must render as in other viewers, never as a red cross. |
|  | Changing a page scale's display unit must update existing dimensions and measurements on that page to the new unit. |
|  | Area measurements must look like dimensions: plain text with no title box or little leader line, and the text can be dragged to reposition it. |
|  | Circle radius and diameter measurements get the same plain, movable text treatment as dimensions. |
|  | Measuring a diameter currently reports the radius. Diameter must report the diameter. |
|  | Alignment snap needs two separate options: align to markups and align to PDF content. |
|  | Closing a tab in split view must remove the split view. Split view must also be turnable off directly. |
|  | When zoomed out, linework looks faded or too thin until zooming in. Match Bluebeam's zoomed-out legibility. |
|  | The app must be faster still: use more RAM and CPU where that helps; it still feels laggy. |
|  | Callout and cloud callout tools have no drawing cursor. Adding a cloud leader draws a cloud but a normal cloud callout has no cloud. Fix all callout variants. |
|  | Hatch colour must be separate from fill colour: fill is a solid fill, hatch is hatch linework, each with its own colour. Hatch scale must be unbounded. Numeric up/down step buttons are missing their arrows. |
|  | Spell check is not working. |
|  | Find must not be a popup. It is a dropdown under the search field that live-searches as you type, lists every match, and lets you pick one. |
|  | Format Painter must show a paint-brush cursor while a format is armed. |
|  | A snapshot of a real PDF looks right in the app but, opened in another viewer, appears black or with massive line widths. Exported snapshots must match the app. |
|  | Rectangle and ellipse drawing tooltip must match Bluebeam (reference video): a compact bar beside the dragged corner with editable Width, Height and Rotation fields; typing sets the value and Tab moves to the next field. |
|  | PDF linework on the page looks blurrier than a snapshot of the same lines pasted beside it until zoomed in. Page lines must look as sharp as the pasted snapshot at every zoom. |
|  | A pasted snapshot shows stray repeated dots in the app that do not appear in other PDF editors. The app must draw it as the export does. |
|  | After placing a rectangle or ellipse no size dialog may pop up; the size bar while drawing is the only size entry. |
|  | Hatch must stay sharp at any hatch scale and zoom: linework, not a tiled picture. **(amended)** Hatch scale is effectively infinite in both directions, in both the style toolbar and Properties. |
|  | Bluebeam tool set import must line up one to one with Bluebeam: verify Sketch Tools against btx/Document1.pdf, where Bluebeam placed the same tools. |

## Requests reported 2026-09-28

| Complete | Task |
| --- | --- |
|  | A1: Keep fractional font sizes exact (10.87 pt stays 10.87 pt, not rounded to a whole pixel). |
|  | A2: Draw stamp artwork (e.g. the Titleblock) as linework, not a picture. |
|  | B3: Viewports: different scales in different regions of one sheet. |
|  | B6: Link tool: a region that jumps to a page, a view, a file or a web address. |
|  | B8: A library of named hatches and line styles like Bluebeam's. |
|  | C2: Search the PDF's own text and the markups' text across all pages, list every hit, and replace text in markups. |
|  | C4: Crop pages. |
|  | C5: Extract or split pages into a new PDF. |
|  | Markups list panel like Bluebeam's: columns for colour, line style, font and similar; filter and sort; select rows to change colour, style or delete several markups at once. |
|  | Panel rail buttons can move between the left and right side but cannot be reordered top to bottom by dragging. They must be. |
|  | The Markups list panel lives only at the bottom of the window, and is shown or hidden by dragging its edge up or down, exactly like Bluebeam. |
|  | Hatch must be drawn behind the markup's outline, not over it. |
|  | Line style and hatch pickers must be big dropdowns where each pattern is easy to tell apart, with its name. |
|  | The scroll wheel over a dropdown must not cycle through its values, anywhere: toolbar, Properties and every dialog. |
|  | The Cloud+ (cloud callout) icon shows only a cloud; it must show a cloud with a callout. Add leader icons for adding an arrow leader and a cloud leader, not just an arrow or just a cloud. |

## Requests reported 2026-09-29

| Complete | Task |
| --- | --- |
|  | Add-leader menu icons must be the callout icons themselves (text box + leader + arrow for an arrow callout, text box + leader + cloud for a cloud callout), not just an arrow or just a cloud. |
|  | A viewport's frame shows only while it has been clicked into; otherwise it is hidden. |
|  | Page setup and scale panel that follows the current page: units, decimal places, scale, the viewports on the page (add, change, delete), page size and orientation (e.g. landscape), and separate X and Y scales. |
|  | A Sketch Tools markup (e.g. section cut) placed in MarkForge and opened in another PDF editor does not look right. |
|  | A cloud markup opened in another editor shows a drag box of the wrong size. |
|  | Every markup type must export correctly to PDF and look and behave right in other editors. |
|  | Sketch Tools contain groups within groups. Import them as nested groups linked together the way Bluebeam does. |
|  | Import of any Bluebeam tool set must be exactly one to one with Bluebeam; it currently is not. |
|  | Right-click an image: Replace image from clipboard or from file. The new picture keeps its own aspect ratio and is sized from the existing image, exactly like Word. |
|  | Fix the margin bugs and every other export issue found, for every markup type throughout the app: anything added in MarkForge must appear exactly the same in another editor. |

## Requests reported 2026-09-30

| Complete | Task |
| --- | --- |
|  | Dragging a measurement into or out of a viewport changes its scale automatically: finished inside the viewport it uses the viewport's scale, otherwise the page's. |
|  | Move and copy modifiers like Bluebeam: only copy if Ctrl is held before the drag starts; during a move, Ctrl turns snapping off and Shift locks the move to straight lines. |
|  | Pages panel: Ctrl+C and Ctrl+V copy and paste pages; with a page on the clipboard, hovering shows an insertion bar where it will go, exactly like Bluebeam. |
|  | Cloud size property for clouds, and a spacing (scale) property for line types that scales dot and dash spacing; line thickness must not change the spacing (it currently does). |
|  | The add-leader icons are still wrong; fix them. |
|  | Adding a curve or control point with Shift+click or Ctrl+click must not happen when the item is dragged afterwards; that is a Shift-drag or Ctrl-drag instead. |
|  | Format painter must behave exactly like Bluebeam's. |

## Requests reported 2026-09-30 — CalcForge (MarkForge + WebSMath)

| Complete | Task |
| --- | --- |
|  | Build CalcForge: MarkForge (PDF markup) combined with WebSMath (SMath Studio replica, branch `claude/zealous-clarke-8yiu03`, folder `websmath/`, commit 8b340fa). New branch from the MarkForge branch; never push to the MarkForge or WebSMath branches. |
|  | Numbers and units must never be wrong: WebSMath's 766 tests, proof tests and mutation check (14 of 14 planted bugs caught) and all MarkForge tests pass in CalcForge. WebSMath's `engine` moves over unchanged except where a decision says otherwise. |
|  | Look: MarkForge's window (toolbars, panels, dark theme, icons, one- or two-word labels with tooltips). Equations look exactly like SMath (fonts, blue units, red errors); the page stays white in dark mode. |
|  | One undo history for everything: Ctrl+Z undoes the last action, equation edit or markup move. |
|  | Keep WebSMath's fast recalculation: editing one equation recalculates only what depends on it. |
|  | Validate every interactive change through the real CalcForge window. |
|  | 1. One unit system, SMath's. Scales, calibration and measurements move from Pint to WebSMath's units engine; Pint removed. All measurement and scale tests still pass; unit names and formatting match everywhere. |
|  | 2. No `.sm` files at all: CalcForge doesn't open, import or save them. |
|  | 3. The document is a PDF. On every save, recalculate, then flatten calc content (equations, plots, matrices, program blocks, calculation blocks) into the page as vector PDF content: embedded-font selectable text, vector fraction bars, roots, brackets and plots, SMath's colours. The flattened layer is its own content stream tagged as CalcForge's, drawn over the untouched page content. The editable source is saved in the embedded record beside MarkForge's. On reopen, remove the tagged layer and rebuild live equations from the record. Tagged layer changed elsewhere: warn, the record wins. Pages deleted or reordered elsewhere: equations follow their pages; equations on deleted pages are removed with a warning naming the variables that became undefined. Record missing: open as a plain PDF and warn the calc can't be edited. Other editors can't move, edit or delete calc content and it never shows in their Markups list; markups stay normal annotations. |
|  | 4. Saving is clean unless signed: every save writes a fresh, compact file so the file never grows. A digitally signed PDF is appended to instead (incremental save) so the signature stays valid, with the reason in the status bar, and the calc layer is still swapped correctly. Test that repeated saves don't grow the file. |
|  | 5. Two modes, Calc and Markup, shown in the status bar. Calc mode behaves like SMath: typing on empty page space starts an equation, `"` starts Calculation text, and every MarkForge single-key or letter shortcut is off (tool keys, 1–9 My Tools keys); new markups are placed only from toolbar, menu or panel buttons. Markup mode is MarkForge as today: `"` makes a normal text box, a new equation starts only with the start key (`'` by default) at the pointer, plots and matrices are placed by clicking. Everything on the page stays editable in both modes. Inside an equation `'` still means "unit follows". Mode toggle, equation start key and both `"` actions are ordinary bindings in the shortcut manager, with clash checking. |
|  | 6. Keyboard clashes: inside an equation or text SMath's key wins; elsewhere MarkForge's (Ctrl+0, Ctrl+1, Ctrl+E, Ctrl+Shift+D, Ctrl+A). Ctrl+B, I and U are MarkForge's text formatting keys and extend to equations. Add an SMath section to the shortcut manager listing every calculation shortcut. Report any other clash. |
|  | 7. File > New gives one blank A4 portrait page in Markup mode. |
|  | 8. Equations can go on any page, including drawing pages (e.g. a check calc on an A1 sheet). |
|  | 9. Variables reach the whole document. Evaluation runs like SMath: page 1 top-left to bottom-right, then page 2, and so on; reordering pages changes the order. |
|  | 10. Calculation blocks replace SMath areas. Not collapsible. Right-click › "Self-contained" (off by default): reads values from above, its own definitions stay inside it. |
|  | 11. MarkForge's fixed pages. Placing or pushing an equation past the last page adds a blank page automatically; equations never straddle two pages. |
|  | 12. One grid, matching SMath's dotted grid and spacing. Equations, Calculation text and markups snap to it. |
|  | 13. Clicking empty space: Calc mode places SMath's red + cursor; Markup mode behaves as MarkForge. Clicking an existing item selects or edits it in both modes. |
|  | 14. Equations and markups select together, group (Ctrl+G), align and snap to each other; grouping never changes calculation order. Box select uses MarkForge's rule (drag right: wholly inside; drag left: touching). Arrow keys nudge a selected equation when not typing in it, and move the text cursor when typing. |
|  | 15. Rotating a page turns equations with it, like callouts: horizontal while edited, turned back afterwards. |
|  | 16. A snapshot copies equations as line work. Raise recolour, redaction or flatten if equations need special handling. |
|  | 17. Lock (Ctrl+L) works on equations. Hide and leave-out-of-print don't apply to equations. |
|  | 18. Keep MarkForge's toolbars and add a condensed "Calculation" section: calculate (F9), auto-calc, insert plot, insert matrix, Calculation text, calculation block, program blocks (if, for, while, line). Result format, font, size and colours are not on the toolbar: defaults in Preferences, per item by right-click. |
|  | 19. SMath's Arithmetic, Matrices, Functions, Programming, Graph and Units panels become one "Maths" panel on the side rail, pinnable and floatable. |
|  | 20. Equation settings (decimals, format, font, colour, disable evaluation, units) are in SMath's right-click menu and in MarkForge's Properties panel. |
|  | 21. Variables panel on the rail: every variable with value, unit, page and any error; click a row to jump to it. The Markups list stays markups-only. |
|  | 22. Calculation text replaces SMath text regions: a MarkForge text box underneath but its own type with its own default style (plain by default), saved as an annotation (not flattened), keeps border and fill, snaps to the calc grid, can go in tool sets as a copy or as a tool (properties mode), no callout leader, no effect on calculations. |
|  | 23. Tool sets and My Tools can hold equations and calculation blocks. Placing one shows a preview, then behaves exactly as if typed there (uses variables above; each line shows its own error). Properties mode stays for single markups and Calculation text only. |
|  | 24. A measure markup can be given a variable name in its properties; its value and unit feed the calcs live, evaluated at its position on the page. |
|  | 25. The Search panel finds variable names and text in equations; Calculation text gets spell checking. |
|  | 26. Copied equations paste into other programs as a picture plus plain text (e.g. "M = 45.2 kN·m"); inside CalcForge they paste as live equations. |
|  | 27. Header and footer: MarkForge's six slots, logo and page ranges, extended with SMath's extra fields. |
|  | 28. One merged File properties dialog: title, author, subject, project (MarkForge) and company, description, keywords, revision (SMath). Title, author, subject and keywords also go to the PDF's standard properties; the rest stay in CalcForge and can be header/footer fields. |
|  | 29. Rename everything to CalcForge: window title, README, code folder (`markforge/` → `calcforge/`), launch command, settings name. |
|  | 30. On first start, copy the MarkForge settings (shortcuts, tool sets, My Tools, toolbar layout, dark mode, markup defaults) into CalcForge once. |
|  | Later phase (plan only, don't build yet): live values in Calculation text, e.g. "The design moment is M = 45.2 kN·m", updating when the calc changes. |
|  | How to work: research both codebases; find every further clash and ask about each (multiple choice, up to four at a time, recommendation first, no guessing); write a phased plan to `docs/`; build one phase at a time, running all tests and the mutation check before every push and checking each change in the real window; test saved PDFs by reading text back, rendering and comparing with the screen, and by opening them as another reader would; log every request here; remove withdrawn things completely; commit with clear messages, push only to the CalcForge branch, no PR unless asked; after each phase report what changed, what was tested, and what behaves differently from SMath or Bluebeam. |

## Clarifications to the CalcForge brief (2026-09-30, answers to the clash questions)

| Complete | Task |
| --- | --- |
|  | WebSMath's tests that check answers against SMath's own example `.sm` files keep running through a test-only `.sm` reader in the tests folder. The app itself has no `.sm` code, menu or file filter. |
|  | MarkForge's tests of the old incremental save are rewritten to the new rule: page content unaltered, a fresh file that doesn't grow, and a signed file appended to with its signature bytes intact. |
|  | Units in plain text (measurement labels, Variables panel, status bar, copied text) are written with a middle dot and superscripts: kN·m, m². |
|  | Units SMath lacks or spells differently use SMath's names: °C, °F, K, yr, hr; pcf, klf and plf are given as lbf/ft³, kip/ft and lbf/ft. SMath's unit table is unchanged. |
|  | One grid, SMath's: dotted, 9 px spacing, never printed. MarkForge's grid spacing and grid printing are removed; one Show grid switch (Ctrl+') plus per-page on/off. |
|  | Margins: on pages CalcForge creates, SMath's margins apply (grid inside only; pushing past the bottom margin moves to the next page). On imported PDF pages equations go anywhere and push at the sheet's bottom edge. |
|  | A too-wide equation breaks automatically onto more lines, before an operator (+, −, ·, =) or between a function's arguments, with later lines indented under the first operand. Display only; the maths is unchanged. Where no break fits, it runs past the edge with an orange outline and a warning that it won't print in full. |
|  | Reading order on a rotated page follows the page's own, unrotated direction; rotating a page never changes a result. |
|  | Recolour and Whiteout never touch equations. Redaction deletes an equation it fully covers (warning names variables that became undefined); partly covered ones are left and flagged. Flatten skips equations. |
|  | Extract and Split pages carry their pages' equations live in the new file's record, warning of variables defined on pages left behind. Insert PDF brings a CalcForge file's equations in live, in reading order. |
|  | Crop removes equations wholly outside the kept area, with the undefined-variables warning; partly outside ones are kept and flagged; Undo restores. |
|  | Plots: the wheel scrolls and dragging moves the plot, until it's double-clicked into; then the wheel zooms (Ctrl: x only, Shift: y only) and dragging pans, until a click outside or Esc. |
|  | Calc mode turns off every tool key, with or without Shift or Alt; Ctrl commands stay. |
|  | MarkForge's symbol keys (Ctrl+Alt+P π, Ctrl+Alt+, ≤, Ctrl+Alt+R √, Ctrl+Alt+F φ…) work inside equations with their maths meaning. |
|  | SMath's Separator, Picture regions, Page background and margin double-click for header/footer are removed in favour of MarkForge's line, image and Header/Footer dialog. |
|  | A lone word followed by a space turns into Calculation text, as in SMath; undo turns it back. |
|  | Measurement labels keep the page's decimal places (trailing zeros included), written by SMath's number formatter. |
|  | WebSMath's 766 tests are ported and run green in phase 1. As a withdrawn feature goes, its tests go with it, listed by name in the phase report. Tests of WebSMath's window are rewritten to drive the CalcForge window. No maths, units, recalculation or editor test is removed. |
|  | 2026-09-30: The equations' visuals must be WebSMath's code, copied one to one — no redrawn look. (Drawing code `calc/ui/layout.py` and `calc/ui/region_item.py` is byte-identical to WebSMath; the red cross and the selected look are WebSMath's own drawing; `tests/calc/test_same_drawing.py` checks CalcForge draws every equation pixel for pixel as WebSMath's window does.) |
|  | 2026-09-30: The Calc/Markup mode switch defaults to F12 (the brief named no key; chosen by the agent, pending the user's say). |
|  | 2026-09-30: CalcForge's own markups (not equations) moved or edited in another editor open as that editor wrote them: the file wins for markups. Equations can't be touched elsewhere (they are page content). Autosave keeps the record without the drawn layers — agreed. |
|  | 2026-09-30: Asked for the pros and cons of a separate CalcForge file type (e.g. `.cfx`) instead of PDF before moving on; decided: keep PDF as the one format. |
|  | 2026-09-30: Big round-trip test: save as PDF, open in another editor, delete pages or move/edit markups, reopen in CalcForge — fix everything found. However a document looks in CalcForge it must look exactly the same in another PDF editor: the save/export engine must be right for every markup, snapshot, photo, calc and plot. |
|  | 2026-09-30: Make the snapshot tool bulletproof. A snapshot is not live: whatever can be seen in the selected box is captured and placed, like a screenshot, but as line work wherever possible (always, unless there is an image in it). Equations, plots and Calculation text come through as line work. Reported: snapshotting a sheet's title block brought the block's lines but not its text. |
|  | 2026-09-30: A calculation block is another type of markup, not a typical equation: an equation block, which acts the same (calculates like the equations, in reading order) but is a separate thing of its own. |
|  | 2026-09-30: Continue with phase 8 — the rename to CalcForge and the one-time migration of MarkForge's settings. |
|  | 2026-09-30: A named measurement's variable must update when its end points are moved, when the page scale changes, and when it is dragged into a viewport (verified: it does, live; tests added). Explain the shortcut clash. Fix the leftover MarkForge names in the docs (`MARKFORGE_PDF_WORKERS`, `MARKFORGE_PDF_CORPUS`). How to run the app. |
|  | 2026-09-30: Bugs: the autocomplete dropdown shows with a big offset from where it should be; a red cross and a blue cross both show. Is turning Calc mode off Markup mode, or is there another mode? The Maths panel, made wide, keeps its buttons left with a big gap on the right: make every panel responsive to its width. The properties toolbar should always be visible (it drops down and up now). Fill and hatch opacity aren't clear, and changing the hatch's opacity changes the fill's too (wrong). The page number at the bottom should be centred on the viewport (it sits a little left). |
|  | 2026-10-01: Right-click a measurement or area measurement to find its variable. Variable names as SMath writes them, `L.beam` (not `L_beam`), shown with the subscript on the measurement. Test the calculation UI against SMath's behaviour. The cursor looked wrong while editing a unit: no cursor issues at all. Move the Calc mode toggle somewhere better and easy to see. A toolbar could be dragged into a panel bar: must not be possible. Flesh out and fix the UI in general. Maths panel: don't keep the same columns and widen them — make the whole thing flex. Bugs: `t:=test+1=` (the second `=` doesn't work); sometimes `=` couldn't be typed at all (neither `:=` nor `=`). Calculation block: no dragging things in or out — it is like its own little page. Continue, fix all the features, and test by actually using the app. |
|  | 2026-10-01: The properties toolbar is missing things — e.g. a cloud's size. Make it like Bluebeam's Properties toolbar, which shows the controls for each type of markup, aligned with CalcForge's own customisation. |
|  | 2026-10-01: "SMath" meant the user's WebSMath (the other branch): run it and compare with CalcForge — using the equations should be the same, errors, cursor, colours. |
|  | 2026-10-01: The result's unit placeholder (second black box) has a weird white box round it — the alignment is wrong; fix it. Use WebSMath's mouse cursors while editing and hovering. Calculation blocks behave like a text box: one click selects the block and it can be moved; double-click goes into edit mode to edit the equations inside. |
|  | 2026-10-01: All equations should look good — margins and things in line: the input unit box in line with the automatic unit output, in line with the symbols and variables. Check this everywhere in the maths. |
|  | 2026-10-01: Opening a PDF must open exactly as intended — don't try to convert markups. Only convert one to a CalcForge markup when it is edited (moved, double-clicked into, etc.), and undo should undo that and revert to however it was written. |
|  | 2026-10-01: The autocomplete dropdown is truncated. In edit mode the second (unit) box should always be visible — copy WebSMath's behaviour, and test edit mode. The measurement variable should be a text box in the context menu, not a separate popup. A subscripted measurement opened in Bluebeam with the subscript massive. Scaling a group with a measurement didn't update its value. Why is there a Calc mode button in Calculation — one toggle, on the bar after Help, not in the draggable toolbars. Dark mode: the toolbar's line and hatch samples can't be seen. The toolbar's number inputs take up too much width. In a calc block an equation can be dragged outside and snaps back: stop dragging outside completely. Use the app and look for issues like these. |
|  | 2026-10-01: Calcs.pdf (made in Bluebeam: pictures, text boxes, highlighters, markups) loads fine but navigating is slow and moving markups is laggy and buggy; editing a text box, highlight or markup should keep its look. Make it ultra fast, use multiple cores. Also an error (PowerShell log: Internal C++ object (PageFrame) already deleted). |
|  | 2026-10-01: Not fast enough: even a big PDF with no annotations scrolls and pans jittery and laggy — it needs to be ultra smooth. The hatch and line-type pickers on the toolbar have padding to the right of the word — look at how Bluebeam does it. |
|  | 2026-10-01 (videos, photo, Calcs.pdf on a Mac): moving a group with markups leaves the leaders in one position; the red dimension doesn't show its length (1m); scrolling is laggy; on the Mac the Calc toggle and search bar on the right didn't show. The one critical rule: opening a PDF must always look the same — a PDF editor first, PDF is a standard, so whatever app wrote it, it must look the same as in any app; a markup's appearance may change after it is edited, but only then. |
|  | 2026-10-02 (Windows): zooming and scrolling still lag; things repaint while zooming. Test it, take screenshots while zooming; it has to be extra fast — keep going until it is as smooth as it can be. |
|  | 2026-10-02: Why is there page sharpening after a zoom? Bluebeam handles it much better. |
|  | 2026-10-05: Better but still laggy: put ~1000 markups on one sheet and scroll, zoom, pan or add pages — it lags. Needs to be better: multiple cores, the graphics card; figure it out, don't stop until it works. |
|  | 2026-10-05: Dragging a page in the Pages panel to rearrange showed a red cross for the cursor and a picture of the whole page, hiding where it was going. Show a small white shaded box for the pages picked out instead. |
|  | 2026-10-08: Don't like the separate menu bar — put it back so it (the window's own bar with the Calc switch and search) is Windows only. Scrolling is faster; make it, zooming and panning even faster — look at the code and optimise without losing any functionality. On zoom the page is blurry and takes a split second to render; Bluebeam is always sharp — figure it out. |
|  | 2026-10-08: Spreadsheets, written from scratch (the 2twiqs branch only shows the end feature): "make it work just like excel" — dragging, copying, styling, conditional formatting, highlighting; Insert Table by dragging a rectangle to the rows and columns wanted; an Insert Spreadsheet page in the Pages panel where the whole page is a sheet, consecutive sheet pages shown continuous like Excel's page view with a blue line at each page break; a scratch area to the right at least a page wide for side calculations, not printed; resize rows/columns, insert, rotate or landscape a sheet. Ask about complex things rather than deciding. Decisions taken by pop-up questions are in `docs/SPREADSHEET_DESIGN.md` (Excel formulas with `var()` for clashing names; units in cells; reading order between pages, Excel order within a sheet; follow dependencies, circular reference error; one growing sheet per run of sheet pages; cross-sheet references with easy names; four ways into equations; markups only on sheet pages; opening xlsx; charts, dynamic arrays, named ranges in, pivot tables out; Excel's printing and page-break preview; built in six phases). |
|  | 2026-10-09: Conditional formatting for equations, "based on the final number, like for dcr … more than 1 is red, less than 1 is green" (font colour, size, bold, underline, background asked for). Answers by pop-up: WebSMath's drawing (kept byte for byte) shows only size and background on maths, so rules set **size and background only**; a rule restyles the **whole equation**; rules **per equation, as presets, and document-wide by variable name**; only **results without units** are compared. Found while checking: the equation menu's Colour, Bold and Underline have never shown on maths (WebSMath draws maths black and regular) — left as they are, to be decided. |
|  | 2026-10-09: Phase 3 (conditional formatting and data tools) to go ahead; open points from phase 2 asked by pop-up. Answers: table lookups kept as built; column lists are `Loads.Load` (the heading's first word); a too-wide number shows #### but typing one widens a never-sized column (Excel's feel); **equations' Colour, Bold and Underline must work on maths — the user allows WebSMath's drawing (`layout.py`, `region_item.py`) to change for this, overriding the byte-identical rule for these three only**; equation conditional formatting sets all five (colour, size, bold, underline, background); Find & Replace both in an open table (Ctrl+F) and in the document Search; cell rules compare units. |
|  | 2026-10-10: Phase 6 (xlsx). Answers by pop-up: no export to Excel at all; opening an `.xlsx` brings in its cells only (no charts). |
|  | 2026-10-10: Phase 5 (charts, spill, named ranges). Answers by pop-up: charts go anywhere (sheet pages over the cells, or any normal page), reading any sheet or table; chart types are the engineering subset — XY scatter, line, column — with log axes, error bars and trendlines; Excel's full structured-reference syntax on tables; Excel's default chart look with units in the axis titles. |
|  | 2026-10-09: Phase 4 (sheet pages). Answers by pop-up: the columns that fit inside the page's margins print and everything to their right is scratch (blue line at the edge; Print Area or Fit to N pages wide prints more); markups over a sheet move with their cells; empty pages left at the end of a run are kept; row numbers and column letters always show on screen. |
|  | 2026-09-30 (phase 7, chosen by the agent, pending the user's say): a calculation block is a thin grey frame, printed as page drawing like an equation; the equations and Calculation text whose top-left is inside it are its members; it is picked by its frame only, so a click inside still starts an equation (superseded 2026-10-01 by the user: it behaves like a text box — click selects, double-click opens); blocks inside blocks: an equation belongs to the innermost self-contained one only (it does not also read the outer block's names). A named measurement's label reads "name = value", and the variable is typed in the measurement's own unit (100 pt at 1:1 is L≔0.03528'm). A block kept in a tool set comes back with its equations, not as a markup group. |
|  | 2026-09-30 (phase 4, chosen by the agent, pending the user's say): the calc and sheet layers are tagged with a private key rather than an optional-content group, so other readers can't list or switch off a "CalcForge" layer. (Superseded the same day: for markups the file wins — see the row below.) Recovery copies (autosave) keep the record and pages but skip the drawn layers, to stay quick. |
