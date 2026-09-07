# CalcForge tasks still requiring work

Audited: 2026-09-06 against `claude/engineering-calc-markup-app-2twiqs`.

The 13 entries below are what the audit could not show working. Each says
what is missing or blocking it. Several are tasks whose base behaviour is
finished and whose recent amendment is not; those name the part that is done so
the remaining work is clear.

This is not the user-owned completion record. It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`.

## 1. Core concept

- **(new)** Support multiple open documents at once: PDF review documents and `.cfx` CalcForge documents appear in separate tabs, can be viewed side-by-side in a split view, and can be moved into independent application windows. Each document keeps its own pages, state and active tool without leaking into another tab/window.
  - **Missing:** Not started: the app builds one MainWindow (calcforge/app.py:57) and has no document tabs, split view or second-window path.

## 4. Equation editor

- **(new)** Use the locally supplied `SMath Studio/` installation, especially its desktop UI, examples and snippets, as the behavior reference when resolving equation-editor interactions. Reproduce its navigation and structured-expression behavior by observing the application; do not copy proprietary implementation code.
  - **Missing:** Standing reference instruction, not a code change: the SMath Studio/ installation is in the repo but no audit of its behaviour has been recorded. Stays a requirement per HANDOVER rule 5.

- **(new, extended)** Make equation editing structural rather than flat-text-like: arrow keys and pointer placement navigate the visible expression tree; selecting an expression and typing an opening bracket wraps the entire selected expression; selecting an expression and typing `/` turns that selection into the numerator of a fraction/division structure. Preserve the selected expression and its formatting when applying either transformation. The structure must also survive a syntax error: a calculation that does not parse keeps its structured typeset layout instead of collapsing back to inline text, operator precedence (BEDMAS) stays visible, `5/` renders as 5 over an empty denominator placeholder, and incomplete value, unit and power slots render as small SMath-style outline input boxes.
  - **Missing:** Not implemented, verified in the running app. With '1+2' selected in 'a:=1+2', typing '(' replaces the selection instead of wrapping it — the text becomes 'a:=('; typing '/' likewise gives 'a:=/' rather than making the selection a numerator. No expression-tree/wrap code exists. The extended error-tolerant-rendering clause is also unimplemented.

## 10. Snapshot tool

- **(new, amended)** Pasted or placed images and snapshots must not acquire a red outline. The image tool's own default stroke must be settable and must default to none, and a snapshot's default stroke must be none; in both cases the visible frame must match the persisted or default style rather than a hard-coded red. A snapshot's stroke colour and width must then be settable by the user and honoured when set, and the style toolbar and the Properties panel must agree with each other on image and snapshot border state.
  - **Missing:** Half done. A snapshot's default really is no stroke (items/snapshot.py:38, Style(stroke='', width=0.0)) and a set stroke is honoured (snapshot.py:91); a pasted image keeps its borderless default rather than picking up the drawn-markup red (items/media.py:84-91). Still missing: the image tool has no settable default stroke of its own anywhere in the code, and nothing verifies that the style toolbar and the Properties panel agree on image and snapshot border state.

## 27. Reliability / process

- Never let hitting the token/usage limit silently end the session's work — pause, and resume automatically once the limit resets, without needing a fresh prompt from you (130, 138) — **not something this end can promise.** A session that runs out of context is summarised and continued, and that is automatic; a session that runs out of *usage* stops until the limit resets and needs a prompt to pick up again. What is under control here is that nothing is left half-finished and unrecorded: work is committed and pushed as it is done, and this list says what is built and what is not, so whatever picks the work up next — a fresh session, or this one after a reset — starts from the list rather than from memory
  - **Missing:** Platform limitation, unchanged: the session environment cannot guarantee resuming itself after a usage limit. Stays a requirement with that note, per HANDOVER rule 5.

- **(new)** Validate interactive changes through the real CalcForge UI, not only unit-level code inspection. Agents must drive the canvas with pointer moves, clicks, drags, keyboard arrows and configured shortcuts, including Escape/cancel paths, and look for stuck tools, lost focus, incorrect cursor states, blocked input, broken selections and other interaction regressions. Keep repeatable Qt event-driven tests for each defect found.
  - **Missing:** Ongoing acceptance requirement rather than a finished feature: it governs how every future interactive change is validated, so it never closes.

## 28. Miscellaneous fixes reported (screenshots referenced)

- **(found here, not reported by you)** Two layout tests — `test_everything_that_can_be_arranged_comes_back` and `test_a_rolled_up_panel_comes_back_rolled_up` — fail intermittently, but only in a **full** suite run. Both pass on their own, and both pass when every file that runs before them is run with them, so nothing earlier is leaving a mess behind: it is a race that shows up only when the machine is busy. Both save an arrangement and then build a second window to check it came back, so the suspect is a 1.5-second layout-save timer on a window still alive, firing between the save and the second window reading it. Worth chasing rather than re-running until it passes — the same race could lose a real arrangement on a slow machine
  - **Missing:** The race is still structurally present: mainwindow.py:218-220 still runs a 1500 ms _layout_timer, and both tests still save an arrangement and immediately build a second window. They passed in all three full runs this session, which is not proof the race is gone — HANDOVER §3 says as much. Logged, not fixed.

- Audit every Properties-panel option for redundancy or unclear labeling — e.g. what does "multiply highlighter" in the callout properties actually do? Several options may not be needed at all (61)
  - **Missing:** No record of the audit having been carried out. The specific example does do something — blend 'multiply' is the highlighter's composition mode (items/base.py:133 and 496) — but nothing shows every Properties option was reviewed for redundancy or unclear labelling.

## 29. New requests awaiting review

- **(amended)** Recompute each callout leader hinge completely when its arrow tip, text box or cloud moves. Do not retain a prior manually adjusted hinge length after any of those changes. In a multi-leader callout each leader's hinge is computed independently: moving the cloud or the text box must not force every leader to share a single hinge length.
  - **Missing:** The recompute-on-move behaviour is there and tested (the hinge tests), but the amended per-leader clause is unverified: no test covers a multi-leader call-out keeping independent hinge lengths when the cloud or the box moves.

- **(new)** Count tool defects: the marker number is visually cut off; Escape must cancel the entire count session immediately rather than lagging behind the keypress; and the ghost `1` marker left behind after cancellation must disappear on its own, without needing a further click.
  - **Missing:** One of the three fixed; two could not be reproduced on this build. FIXED — the clipped number: CountItem now sizes the number's box from the font (index_rect) instead of a box fixed at 16x10 points, and owns that space in boundingRect, so the number is whole at 7, 9, 11, 14 and 18pt and up to three digits. Evidence: test_a_count_marker_shows_its_whole_number_at_any_size. NOT REPRODUCED — Escape already puts the count tool down on the press, with no lag and no draft left behind, and no ghost 1 marker appears on either the hover-then-Escape or place-then-Escape path; test_escape_puts_the_count_tool_down_at_once covers it. Those two reports look to have been made against an older build. Leaving the task open until the user confirms against this one.

- **(new)** A snapshot offers no colour-change control at all. Either add the option wherever it is meaningful for a snapshot, or deliberately exclude snapshots from stroke-colour controls — and if excluded, make that exclusion consistent between the style toolbar and the Properties panel rather than present in one and absent in the other.
  - **Missing:** Confirmed: calcforge/ui/panels.py has no SnapshotItem branch at all, so a selected snapshot gets no colour control anywhere. The decision the task asks for — add it where meaningful, or exclude snapshots consistently in both the style toolbar and Properties — has not been made.

- **(new)** Undo must cover equation state transitions. Undo reverts a space-triggered equation-to-text conversion back to the live equation, and restores text removed by Backspace, down to an empty entry.
  - **Missing:** Half works, verified in the running app. Undo of the space-triggered conversion does return the live equation: after typing a calculation, pressing space and undoing, a MathItem is back on the page. Backspace is not covered: typing 'b:=300mm', deleting all eight characters and undoing restores the MathItem with source '' rather than the removed text.

- **(new)** Cloud-leader placement feedback: when a cloud leader is being added, no provisional straight leader is drawn before the cloud itself is drawn, and the cursor changes to a cloud-drawing cursor for the duration of the placement.
  - **Missing:** No cloud-drawing cursor exists: the view sets no cursor for the pending-cloud-leader state (no cloud cursor anywhere in ui/view.py), and nothing suppresses a provisional straight leader between arming the cloud leader at view.py:397 and the cloud being drawn.
