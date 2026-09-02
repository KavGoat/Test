# What matters in the interface

`docs/what-matters.md` is the brief for the numbers. This is the brief for
everything around them — the standard the chrome is held to, and why it looks
the way it does.

## Who is at the keyboard

An engineer with a drawing on one screen and this on the other, three hours
into a check, with a deadline. They are not admiring the software. Every second
the interface spends drawing attention to itself is a second not spent on the
design.

That gives one governing rule:

> **The only colours that should catch the eye are the ones on the drawing.**

The chrome is a flat, quiet grey with a single accent. Markup colours are
saturated and deliberate. If a toolbar ever competes with a revision cloud for
attention, the toolbar is wrong.

## What has to be true

### 1. The document looks like the document

The sheet on screen is the sheet that comes out of the printer. It is white
paper of a known size, lying on a desk, with an edge you can see and a shadow
under it. Nothing is drawn on screen that will not print, except guides that
are obviously guides — grid, margins, selection handles.

This is why the desk is a distinct grey rather than another shade of white: the
edge of an A4 page is information, and a page whose boundary you cannot see is a
page you cannot lay out.

### 2. It moves the way documents move

A calculation sheet is *read*, not operated. So:

- The wheel scrolls. Shift and the wheel scroll sideways. Ctrl and the wheel
  zoom at the pointer, where the pointer is.
- Every page is on one canvas, scrolled through continuously. Reaching the next
  page is a flick of the wheel, not a command.
- Page Up and Page Down move a screenful. Ctrl with them moves a page.
  Ctrl+Home and Ctrl+End reach the ends.
- Space and drag pans; so does the middle button.
- Nothing scrolls under the reader on its own. Scrolling onto another page
  updates the page number — it never moves the view to "tidy up".

A person who has used a PDF reader already knows all of this. That is the point.

### 3. Every state is visible somewhere

- The current tool is underlined in the toolbar.
- The page, the scale, the zoom and the problem count are always in the status
  bar.
- A published cell is tagged with its variable name **on the sheet**, not only
  in a dialog.
- A self-contained block carries a rule down its edge.
- A measurement shows what it measured; a rectangle shows how big it is.

If the only way to know something is to open a dialog and look, that is a bug.

### 4. Nothing surprising, nothing modal without cause

A dialog stops the work, so it has to earn it. Setting a rectangle out at an
exact size on a scaled drawing earns one. Dropping a sticky note does not — you
place it and type into it, and a dialog appears only when you ask for it.

Where a gesture has an obvious meaning, it has that meaning: double-click to
edit, drag to move, drag an edge to resize, double-click a run of points to add
one, right-click for what applies to what is under the pointer.

### 5. It survives being used badly

Clicking in the wrong place, typing with nothing selected, scrolling mid-drag,
turning the page while editing — none of it may lose work or leave the document
inconsistent. `tools/session_fuzz.py` exists to try exactly this, and the
crashes and data losses it found are in the commit history.

### 6. Keyboard first, for the things done all day

Drawing tools are single keys. Every binding is rebindable by pressing the keys
you want, and the manager refuses to save a key that would mean two things.
Typing on the page does nothing unless the key is bound — which is what allows
a bare keystroke to mean "start writing here" rather than being a hazard.

**A tool key is a letter when you are writing.** While a calculation, a text
box or a table cell has the cursor in it, no tool binding fires: `M` types an
m, and so does `Alt+M`. Document commands — save, print, zoom — stay live,
because they do in every other application. Getting this wrong is not a small
annoyance; it is a tool changing under somebody mid-sentence.

### 7. The window belongs to whoever is using it

Panels pin, float, hide and come back. Toolbars go on any edge, lock when they
are where you want them, and carry the tools you choose. All of it is
remembered, and all of it can be put back with one command.

The one thing that is *not* customisable is the document: the page always looks
like the page. The dark theme restyles the frame, never the sheet — the words
on the paper keep their own colour, because what you see has to be what
prints.

## What this is not

It is not a copy of any one product. It borrows the arrangement engineers
already know — thumbnails on the left, properties on the right, a markups list
at the bottom, tools across the top — because familiarity is worth more than
novelty in a tool somebody has to be productive in on the first afternoon.

It is also not finished. The test in `tests/test_canvas.py` and the fuzzer are
how the claims above stay true as it changes.
