# MarkForge — tasks still requiring work

Audited: 2026-09-07 against `claude/markforge-python`. Re-audited the same day
after a run-through of the running application, which corrected four entries
below and found five bugs — those are in `docs/COMPLETED_TASKS.md` under
"Found by walking the application", with what was done about each.

These are the open requirements the audit could **not** show working. Each says
what is missing or blocking it; several have a base behaviour that is finished
and an amendment that is not, and those name the part that is done so the
remaining work is clear.

Everything the audit *could* show working, with the test that holds it, is in
`docs/COMPLETED_TASKS.md`. That file also ends with a short list of behaviour
that is built but has no focused test — real, but unguarded.

This is not the user-owned completion record. It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`.

---

## 1. What the app is

- **Support multiple open documents at once, side by side in a split view.**
  - **Two of three parts done.** Tabs: each open document has its own document,
    canvas, undo history, page and tool, and a switch hands the one view a
    different canvas rather than re-wiring anything. File ▸ New tab, `Ctrl+T`.
    Independent windows: File ▸ New window, `Ctrl+Shift+N`. **Not done:**
    side-by-side split view, which needs a second live `PageView` in the same
    window — the shared-view design deliberately avoids that, so it is its own
    piece of work rather than a bolt-on. Evidence for what is done:
    `test_two_documents_open_in_tabs_without_reaching_into_each_other`,
    `test_a_second_window_keeps_its_own_document`.

## 7. Markup tools — placement and interaction

- **It is possible to get permanently stuck inside a tool, with Escape not
  helping and no other tool selectable.**
  - **Cannot reproduce, and not closed.** Escape is held by six tests through
    the real event queue — a click-started drawing, a half-drawn callout, an
    unplaced cloud leader, a lasso, a group resize, the format painter — and
    `escape_everything()` puts the tool down, clears the selection and ends any
    edit in one press. Two hundred rounds of the fuzzer, which picks tools and
    abandons gestures at random, end with the tool selectable. That does not
    prove the reported state cannot happen; it means nothing here reaches it.
    Needs the sequence that produced it.

## 8. Markup tools — specific shapes

- **Cloud vs Cloud+: click-and-drag gives the rectangular cloud, clicking each
  point gives the custom-shaped one, and the same distinction governs a cloud
  callout. After the shape is finished, right-click or Enter proceeds to the
  text box.**
  - **The two ways of drawing are built and tested**
    (`test_cloud_tool_supports_dragged_and_point_by_point_clouds`,
    `test_a_cloud_callout_can_be_drawn_corner_by_corner`). **Not done:** they
    are not named Cloud and Cloud+ anywhere, and nothing holds the
    right-click-or-Enter step from a finished cloud shape into placing its text
    box.

## 9. Callouts, text boxes, dimensions

- **Remove the small floating description/label that appears on markups and
  fades out.**
  - **Cannot find it.** Nothing in `items/` or `ui/` draws a fading label on a
    markup, and no test asserts one. It may already be gone, or it may be
    something else — the orange placement marker (removed and held by
    `test_snap_feedback_is_a_blue_target_not_an_orange_square`) is the nearest
    thing. Needs a screenshot to identify.

## 19. Pages & document structure

- **Insert-PDF must bring in the actual PDF content, not a raster snapshot.**
  - **Done for the line work and the source page, and worth keeping open for
    the text.** An imported page keeps the source PDF's own page in the saved
    file, and its vectors come in as real geometry to snap to — evidence in
    `docs/COMPLETED_TASKS.md`. What is still a picture is the *screen*
    rendering behind that geometry: `pdfio.BEST_DPI` renders the page at 110
    dpi for display, re-rendered sharper as you zoom. Nothing is lost from the
    file, but the thing being looked at between zoom steps is a raster.

## 23. Import / interoperability

- **Repair BTX sketch-tool import fidelity — `btx/Structures - Sketch Tools.btx`
  imports incorrectly, including structural section-cut and circle symbols.**
  - **Not done.** Every tool set in `btx/` reads and every tool in them arrives
    with its colours, weights, line types and hatches
    (`test_every_tool_set_reads_without_losing_a_tool` and 27 others). What is
    not held is *fidelity of the drawn symbol*: nothing compares an imported
    structural section-cut against what Bluebeam draws, so "imports
    incorrectly" is neither confirmed nor fixed. This needs the specific
    symbols named and a reference to compare against.

- **Format Painter's icon should match Bluebeam's paint-roller.**
  - **The tool is done and tested**; the icon is drawn as a brush
    (`icons.py`, `test_the_format_painter_carries_a_brush`) rather than a
    roller. A deliberate difference or an oversight — worth one word from the
    user either way. It is the only open item waiting on an answer rather than
    on work.

## 27. Reliability / process

- **Never let hitting the token/usage limit silently end the session's work.**
  - **Platform limitation, restated rather than closed.** Nothing in this
    environment resumes a session when a usage limit lifts, and no code in this
    repository can change that. What exists is a scheduled wake-up
    (`send_later`), which brings a session back at a chosen time but does not
    detect the limit — arranging to come back, not carrying on.
    `docs/HANDOVER.md` says this, and says the register and the branch must
    always be left in a state somebody else can pick up from. Stays open per
    HANDOVER rule 6.

- **Validate interactive changes through the real MarkForge UI.**
  - **An ongoing acceptance requirement, and it should stay open**: it governs
    how every future interactive change is validated, so there is no state in
    which it is finished. Leaving it open is the point of it.

## 28. Miscellaneous fixes reported

- **An object can get stuck showing a "move" cursor even when nothing is
  selected, and Escape does not clear it.**
  - **Partly answered.** The cursor is recomputed when a resize finishes and
    when Escape cancels a group resize
    (`test_finishing_a_rectangle_resize_recomputes_the_cursor`,
    `test_escape_cancels_a_group_resize_and_restores_the_cursor`). The reported
    case — nothing selected at all — has no test and could not be reproduced.

- **The "blue tool" in the UI that does nothing and cannot be selected.**
  - **Not found.** Every entry in the tool table has a factory or a mode, and
    every tool is reachable from the toolbar and the menu bar
    (`test_every_markup_tool_is_reachable_from_the_toolbar`). Whatever was seen
    is not identifiable from the description. Needs a screenshot.

- **Highlighter leaves gaps where strokes overlap.**
  - **Measured, real, and needs a change to how the page is painted.** One
    stroke is already merged into a single band and filled once, so it has no
    seams (`test_a_highlighter_stroke_is_one_even_band`). Two strokes crossing
    do double up: measured on the real painter, one band is `#ffe99d` and the
    crossing is `#ffde6c`, so the overlap reads as a darker patch through what
    should be one even wash. It cannot be fixed on the stroke. A blend mode
    does not do it either — Darken with a half-transparent colour still
    composites the second stroke over the first, which was tried and measured
    and put back. What it needs is every highlighter on a page painted into
    one layer and that layer composited once, which is a change to
    `PageFrame`'s painting rather than to `PolyItem`'s.

## 29. New requests awaiting review

- **The numeric size entry after the first click of a rectangle or ellipse.**
  - **Better, but the reported rotation could not be reproduced.** The entry is
    screen-aligned — `ItemIgnoresTransformations`, rotation pinned to zero — so
    it stays upright and the same size at any zoom and at every reading turn,
    and it anchors to the corner that is bottom-right *on screen* rather than
    the one the item calls bottom-right, which was genuinely wrong on a turned
    page. What could not be reproduced is a rotated panel on an unturned view.
    Worth a re-check against this build. Evidence:
    `test_the_size_entry_stays_upright_whichever_way_the_page_is_turned`.

- **Recoverable document flattening.**
  - **Mostly done; one part unreproducible.** Flattened content is part of the
    page as far as the pointer is concerned, recovery gives it back, the class
    chooser offers the classes that exist since the strip-down (Markups, Text,
    Measurements), and the Preferences switch turns recoverability off.
    Evidence: `test_flattened_markup_lets_the_pointer_through_to_what_is_behind`,
    `test_document_flattening_uses_the_classes_chosen`,
    `test_flatten_dialog_class_choices_follow_real_clicks`,
    `test_irreversible_flattening_keeps_only_a_vector_recording`.
    **Not done:** the crosshair cursor the report mentions. There is no flatten
    tool in the tool table — flattening is a menu action — so nothing here sets
    a crosshair for it. Needs the reporter to say what was selected when they
    saw it.

- **Walk the whole application as somebody meeting it for the first time.**
  - **Not started, and more worth doing than when it was asked for.** Three
    features have been removed since — calculations and everything with them,
    review states, layers — and a removal is exactly the kind of change that
    leaves loose ends a first-run walk finds. What it finds is meant to become
    its own list of tasks rather than staying one entry.

- **Recolour a snapshot the way a page and an image can be recoloured.**
  - **Logged rather than half-built, and the reason is structural.** A snapshot
    is stored as a `QPicture` — a recording of drawing commands — not as the
    line work it was taken from, and a command stream cannot be replayed
    through a colour substitution. Giving a snapshot the same swap, colourise
    and transparency means keeping its source items alongside the recording so
    the picture can be rebuilt recoloured; repainting a raster of it would
    throw away the vectors, which is the whole point of a snapshot.

---

## Not covered by the walk

The run-through covered the toolbars, the menus, the status bar, the Properties
panel for every markup there is, and opening a drawing and marking it up. It
did not cover:

- the dialogs — page setup, header and footer, document properties,
  preferences, shortcuts, insert PDF, and the scale and calibrate prompts;
- the tool sets panel in use, as against read;
- printing and print preview;
- a second window and a second tab, beyond the two tests that hold them.

Each is somewhere a first-run walk would be worth the time, and none of it has
had one.

## Left behind by the removals

Found by this audit rather than reported. None of these is a user requirement;
they are debris from taking three features out.

All four found by this audit were cleared in the same commit:

- `docs/backlog.md` compared the page bar to "the layer switches" — reworded,
  with a note saying when layers went.
- `markforge/ui/icons.py` drew `panel_variables`, `panel_functions`,
  `panel_problems` and `variables` for panels and a tool that no longer exist —
  all four removed.
- A test was still named `test_the_calculation_insertion_point_is_off_by_default`.
  What it checks is right; it is `test_the_insertion_point_is_off_by_default` now.
- `markforge/io/pdfmarkups.py` imported `Optional` and never used it — removed.
