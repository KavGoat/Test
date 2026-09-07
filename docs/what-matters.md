# What matters when a drawing is marked up, and what this app is for

This is the brief the app is built and tested against. It exists so that
"is it finished?" has an answer that is not a matter of opinion.

## What the app is for

An engineer checking a drawing produces a **marked-up set**: the consultant's
drawing with somebody's clouds, dimensions, take-off and comments on it, issued
back so that the person who drew it can act on it. It is a record of what was
asked for and when, as much as a working tool. It goes to people who are not
using this program.

MarkForge is that document, and the document is a PDF. The drawing that came
in, the markups put on it, and the measurements taken off it are one file that
anybody can open.

## What has to be true

In rough order of how badly it hurts when it is not.

### 1. The file that comes out opens everywhere, and is still the file that went in

Nothing else matters if this is not true. A markup nobody else can read is a
markup that was not made. So:

- **A saved file is a PDF**, not a container with a PDF inside it. Acrobat,
  Bluebeam, a browser and a phone all open it.
- **The source page is preserved byte for byte** whenever the document is that
  page and the markups on it. Saving appends; it never re-encodes,
  re-compresses or re-renders what came in. A signature still verifies, an
  embedded font stays embedded, and a drawing office's export is handed back
  exactly as it was received. Where something has to be painted onto the page
  — a markup flattened into it, a drawing dimmed, a running footer — the file
  is built afresh, and the tool says which of the two it did rather than
  claiming the stronger one.
- **Every markup is a real annotation** with its own appearance stream — a
  cloud is a cloudy-bordered square, a callout is a free text with a callout
  line, a dimension is a measured line — so the next person can select it,
  move it and reply to it in their own software.
- Nothing MarkForge knows about a markup is lost on a round trip through
  MarkForge, and nothing another editor understands is lost on a round trip
  through it.

### 2. The measurements are right

A take-off that is wrong by a factor is worse than no take-off, because it
looks like work that has been done.

- A page's scale is the page's own. An imported 1:50 detail and a 1:200 layout
  in one document each measure against their own scale, never the document's.
- Setting a scale, or calibrating one against something of known length, never
  changes what was measured before it — it changes what the number reads as.
- Adding an area to a length is an error, never a number.
- Choosing a unit to display in never changes the value underneath.
- A cut-out comes off the area it is drawn inside, and the takeoff total says
  so.

### 3. Somebody else's drawing opens quickly, correctly and sharply

The drawings are large, and they arrive from everywhere.

- A page is drawn from its own line work, not from a picture of it, so it is
  sharp at any zoom rather than magnified — and that line work can be caught
  hold of: its ends, its corners, and where its lines cross, which is where a
  dimension is actually taken from.
- Somebody else's markups come in as markups — a Bluebeam cloud opens as a
  cloud that can be selected, recoloured and moved, not as part of the page.
- A drawing opens in a moment, not in a minute. Opening a file is not a
  conversion.
- A file with a damaged cross-reference table is read anyway, by looking for
  the objects, rather than refused.

### 4. It is auditable

The person receiving the markups has to be able to act on them without the
author standing over them.

- Every markup carries its author, its date, its subject and its comment.
- The markups list is the take-off: every annotation in the document, its page,
  its measured value, filterable and exportable to CSV.
- Measurements and counts sharing a subject are totalled, and the total is the
  sum of what is actually on the pages.
- What is on the screen is what prints, and what prints is what was saved.

### 5. It says when it is unsure

The tool must be loud about what it cannot confirm: a measurement on a page
with no scale, a redaction that only partly covers something, a flatten that
cannot be undone. Silence has to mean "checked", not "not looked at".

### 6. It fits how the work is actually done

- The tools an office already has are Bluebeam tool sets. They import.
- The same twenty markups get drawn a hundred times, so defaults, tool sets and
  the number keys matter more than any single feature.
- Drawings get turned, recoloured and reissued, and the markups go with them.
- Somebody else opens the file and has to make sense of it.

## What this does not claim

No test suite proves software correct, and no tool removes the reviewer's
responsibility for the review. What the suites in `tests/` do is make specific,
checkable promises: that `test_format.py` opens what was saved and finds an
ordinary PDF with the source page untouched, that `test_pdf_engine.py` reads
real files from other people's software rather than files of its own making,
that `test_btx.py` reads the actual `.btx` tool sets in `btx/`, and that
`test_output.py` measures what leaves the printer.

**Check the marked-up set before you issue it.** That is true of every review
tool ever written, and it is true of this one.
