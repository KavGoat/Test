# What matters to an engineer, and what this app is for

This is the brief the app is built and tested against. It exists so that
"is it finished?" has an answer that is not a matter of opinion.

## What the app is for

An engineer designing a building produces a **calculation sheet**: a document
that another engineer — a checker, an approver, a building control officer, or
the same engineer in ten years when something cracks — has to be able to read,
follow, and disagree with. It is a legal record as much as a working tool.

CalcForge is that document. Calculations, the drawings they refer to, and the
tables they read from all live on the same page, and the page prints exactly as
it appears.

## What has to be true

In rough order of how badly it hurts when it is not.

### 1. The numbers are right

Nothing else matters if this is not true. A wrong number that *looks* right is
the worst possible failure of a tool like this, because it is the one nobody
catches. So:

- Arithmetic is arithmetic. No silent rearrangement, no lost precision.
- **A quantity is one value.** `6 m / 200 mm` is thirty. It is not
  `(6 m / 200) mm`. Getting this wrong is how a tool produces a number that is
  wrong by a factor of a thousand and still looks plausible.
- Every result is reproducible: the same sheet gives the same answer today and
  next year, on any machine.

### 2. The units are tracked, and mismatches are refused

Unit errors are the classic way a structure gets designed wrong. So:

- Adding a force to a length is an **error**, never a number.
- Converting to the wrong dimension is an **error**, never a number.
- Choosing a unit to display in never changes the value underneath.
- Mixing metric and imperial in one sheet is fine, and gives the same answer as
  either alone.
- A name the engineer chose is theirs. `sigma` is a stress, not the
  Stefan-Boltzmann constant, whatever the unit registry thinks.

### 3. It is auditable

A checker has to be able to follow it without the author standing over them.

- Every line shows its expression *and* its result, laid out as it would be
  written by hand.
- Every variable can be traced to where it was defined — including a value
  published from a spreadsheet cell, which says which cell.
- Nothing is hidden. There are no invisible defaults doing work off-screen.
- What is on the screen is what prints.

### 4. It prints properly

A calculation that cannot be issued is not finished. A4 by default, page by
page, at the right size, with the numbers legible.

### 5. It says when it is unsure

The tool must be loud about what it cannot confirm: undefined names, unit
mismatches, values that were used before they were defined, circular
references. Silence has to mean "checked", not "not looked at".

### 6. It fits how engineers actually work

- Loads come out of a spreadsheet; that spreadsheet has to come along.
- Drawings get marked up, measured and taken off, at a page scale.
- Assumptions get written on the page next to the number they justify.
- Somebody else opens the file and has to make sense of it.

## What this does not claim

No test suite proves software correct, and no tool removes the engineer's
responsibility for the design. What the suites in `tests/` do is make specific,
checkable promises: that the worked examples in `test_validation.py` come out at
their published values, that the properties in `test_units_property.py` hold
across every unit family and across randomised inputs, and that what leaves the
printer in `test_output.py` is what was on the page.

**Check the printed sheet before you issue it.** That is true of every
calculation tool ever written, and it is true of this one.
