# MarkForge — tasks still requiring work

## Current review — 2026-09-11–12

This is the active remainder. The older audit below is retained as history,
not as a second open-work list. Completion cells remain user-owned and blank.

| Requirement | Current finding / next evidence needed |
| --- | --- |
| Intermittent tool lockup that survives Escape | Still not reproduced. The current native 300-round stress session had zero failures, and the event suite covers callout, leader, selection, resize, snapshot and painter cancellation. A concrete sequence reaching the reported lockup is still needed; passing unrelated tests does not close it. |
| Automatically resume after a usage-limit reset | Platform limitation; this repository cannot control session limits or guarantee automatic restart. The handover and task records preserve the work for continuation. |
| Continue validating interactive changes through actual Qt events | Ongoing requirement. Current coverage includes pointer gestures, keyboard cancellation, tab transfer, printing/export and a native stress session. It must be repeated for future changes, so it is not a one-time completion. |

### Addressed in this review

- PDF snapshot capture/paste, vector persistence/recolouring, and background
  exclusion now have actual-PDF regressions. The previously contradictory
  background test has been corrected. The old “needs a gesture sequence”
  snapshot entry is superseded by this implementation evidence.
- Hatch scale, Whiteout, arbitrary markup-edge snapping, persistent tab bars,
  floating drag previews and moving tabs back into existing windows are
  implemented and tested. Whiteout is vector clipping, not secure redaction.
- Performance work fixes competing zoom requests, bounds preview memory and
  reduces snap candidate generation. Measurements and their limits are in
  `COMPLETED_TASKS.md`; responsiveness on the user's own dense PDFs still
  requires acceptance, rather than a universal “fast” claim.
- Split view and BTX section/elevation reference-geometry fixes were already
  present. Their current tests replace the stale “not done” entries below.
- The remaining dialog and print-preview walkthrough was performed. It found
  long scale labels and a narrow section editor, now corrected. Existing
  toolset/window/output tests cover the corresponding editing workflows.
- Format Painter's claimed tool-change cancellation was false. A new event
  test reproduced it; tool changes and outside controls now cancel the mode.

For exact evidence see `COMPLETED_TASKS.md` and `tests/test_review_regressions.py`.

---

## Historical audit — superseded by the current review above

Audited: 2026-09-07 against `claude/markforge-mupdf-pdf-handling-vpyj1t`. Re-audited the same day
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

## 29. New requests awaiting review

- **Walk the whole application as somebody meeting it for the first time.**
  - **Not started, and more worth doing than when it was asked for.** Three
    features have been removed since — calculations and everything with them,
    review states, layers — and a removal is exactly the kind of change that
    leaves loose ends a first-run walk finds. What it finds is meant to become
    its own list of tasks rather than staying one entry.

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

---

## 30. New rows still requiring work after the 2026-09-10 pass
- **Snapshot broken-state sequence.** Existing snapshot creation, cancellation,
  repeat use, vector capture and Escape paths pass, but the newly reported
  reproducible corrupting sequence is not described in the task row and was
  not reproduced in this pass or in the 300-round seed-41 UI fuzz run. It needs
  the exact gesture sequence; no speculative change was made.
