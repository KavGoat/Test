# What is still to do

Everything asked for that has not been built yet, in the order it is being
worked. Each entry is one job: it is struck off only when it is written,
tested and pushed. Kept in the repository on purpose — a list that lives only
in a conversation is a list that gets lost.

## Regressions — things that used to work

- [ ] **"Image missing"** on a snapshot, and on a picture pasted from
  elsewhere. Both come back empty.
- [ ] **Ctrl+B** bookmarks while words are being typed or selected, where it
  should embolden them. It should only reach for a bookmark on the page.
- [ ] **The table resize pointer** does not change over a column or row edge.

## The page, and what is on it

- [ ] The **page bar**: page width and margins on it, the grid switches as
  buttons along the bottom the way the layer switches are, and the page
  controls in the middle with next and previous, as Bluebeam has them.
- [ ] A **grid that belongs to the page**: on for a blank page, never on an
  inserted PDF page, printed with the sheet, and switched off page by page
  from the pages panel and from page setup.
- [ ] **Rotating a page** must turn the page and everything drawn on it.
  Separately, View gets a rotate that only changes how it is looked at.
- [ ] **Insert PDF** must bring the whole page through, not a 150 dpi
  photograph of it.
- [ ] The **footer** lands outside the page on an imported PDF; and one or
  more pages can be given or refused a header and footer from the right-click
  menu.
- [ ] Dragging a **PDF onto the pages panel** shows where it will land and
  puts it there.

## Markups

- [ ] The **cloud call-out** must cloud the region and attach a text box on a
  leader, the way the ordinary call-out does.
- [ ] The call-out's **box shows a preview** while it is being dragged.
- [ ] An **arrow shows a control point** when nothing is selected; and the
  **rotation handle** is cut off, and jumps when the markup moves.
- [ ] **Control points on any shape**: Shift over a point takes it away, Shift
  over a segment adds one, Ctrl over a point rounds it, Ctrl over a segment
  bends it into an arc. An arc gets two handles — how long the curve is and
  how far it turns. A rounded corner gets a radius handle.
- [ ] **Break symbols** on a segment or an edge from the right-click menu; a
  curve tool; and Insert gets a markup section with every drawing tool in it.
- [ ] **Dimensions** that look like the photograph, whose number can be
  shift-clicked out to one side, and whose value does not change while the
  dimension is being turned.
- [ ] **Hatch patterns and line types** that match Bluebeam's, read from its
  own files where possible.

## Tool sets

- [ ] **Import Bluebeam .btx tool sets** — zlib-compressed, hex-encoded PDF
  annotation dictionaries, groups and every markup type included. The fifteen
  files in `btx/` are the test.
- [ ] The tool chest: **no dashed blue box** when placing, clicking an entry
  arms it, and every tool set is shown at once.
- [ ] Tool sets move onto the **right-click menu**, and properties mode
  becomes findable.

## Calculations

- [ ] **One written-out equation view.** The edit view must be the final view:
  fractions, powers, subscripts, no inline fallback, and a superscript that
  sits where it belongs. Rebuilt in terms of lines and blocks.
- [ ] **One phi.** Two different characters are being used for it; every Greek
  letter wants checking, and the spacing around them fixing.
- [ ] **Variable completion**: typing a name in an equation offers every
  variable, and Tab fills it in.
- [ ] The **unit list** appears in the wrong place.
- [ ] **Only the bound key starts a calculation** — a bare keystroke must not,
  or the tool shortcuts stop working.
- [ ] **How many figures** a result is shown to: decimal places, significant
  figures or scientific notation, from its right-click menu.
- [ ] An **equation inside a paragraph**: a backslash in a text box opens a
  field where a variable name prints as name = value with its unit, or a
  calculation is worked out in place.

## Tables and text

- [ ] A table can be **read by its column headings** as well as by A, B, C.
- [ ] **Alignment for cells**, left, centre and right, the way Excel offers it.
- [ ] **Subscript and superscript** from `_` and `^` in a text box and in a
  table cell.
- [ ] **Pasting from Excel** carries relative formulas across where it can.

## The frame

- [ ] The wheel **scrolls the panel**, not the dropdown the pointer is over.
- [ ] **Ctrl+Shift+V pastes in place**, where it was copied from.
- [ ] **Everything in the menus**: every page, line and markup function
  reachable from the menu bar, preferences under Settings, and a tool search
  in Help.
