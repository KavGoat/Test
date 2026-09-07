# MarkForge tasks still requiring work

Audited: 2026-09-07 against `claude/markforge-python`.

The entries below are what the audit could not show working. Each says what is
missing or blocking it. Several are tasks whose base behaviour is finished and
whose recent amendment is not; those name the part that is done so the
remaining work is clear.

This is not the user-owned completion record. It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`.

## 1. What the app is

- **(amended)** Support multiple open documents at once: each appears in its own tab, can be viewed side-by-side in a split view, and can be moved into an independent application window.
  - **Missing:** Two of the three parts done; split view is not. DONE — tabs: each open document has a tab with its own document, canvas, undo history, page and tool, and one view is handed a different canvas on a switch, so nothing is re-wired and nothing of one document reaches into another. The bar hides itself when only one document is open. File ▸ New tab, Ctrl+T. DONE — independent windows: File ▸ New window, Ctrl+Shift+N, each with its own document, view and undo stack. NOT DONE — side-by-side split view: that needs a second live PageView in the same window, which the shared-view design deliberately avoids, so it is a separate piece of work rather than a bolt-on. Evidence: `test_two_documents_open_in_tabs_without_reaching_into_each_other`, `test_a_second_window_keeps_its_own_document`.

## 15. Panels & layout

- **(new)** Only one panel should be open at a time in each side location, Bluebeam-style.
  - **Missing:** Not started. Panels dock, pin, float and are remembered, but nothing enforces one-at-a-time per side.

## 27. Reliability / process

- Never let hitting the token/usage limit silently end the session's work — pause, and resume automatically once the limit resets, without needing a fresh prompt.
  - **Missing:** Platform limitation, restated accurately rather than closed. Nothing in this environment resumes a session when a usage limit lifts, and no code in this repository can change that. What does exist is a scheduled wake-up (`send_later`), which brings a session back at a chosen time but does not detect the limit — arranging to come back, not carrying on. `docs/HANDOVER.md` says this, and says the register and branch should always be left in a state somebody else can pick up from. Stays a requirement per HANDOVER rule 6.

- **(new, amended)** Validate interactive changes through the real MarkForge UI, not only unit-level code inspection.
  - **Missing:** Ongoing acceptance requirement, and it should stay open: it governs how every future interactive change is validated, so there is no state in which it is finished. Leaving it open is the point of it.

## 29. New requests awaiting review

- **(amended, reported again)** After the first click of a rectangle or ellipse, show the numeric size entry as a small tooltip anchored near the bottom-right corner of the in-progress shape.
  - **Missing:** Better, but the reported rotation could not be reproduced. The entry is screen-aligned — `ItemIgnoresTransformations` and rotation pinned to zero — so it stays upright and the same size at any zoom and at every reading turn, and it anchors to the shape's corner that is bottom-right ON SCREEN rather than the one the item calls bottom-right, which was genuinely wrong on a turned page. What could not be reproduced is a rotated panel on an unturned view. Worth a re-check against this build. Evidence: `test_the_size_entry_stays_upright_whichever_way_the_page_is_turned`.

- **(amended)** Add recoverable document flattening, with the class chooser, recovery data and the Preferences switch.
  - **Missing:** Half done. Flattened content is part of the page as far as the pointer is concerned: it no longer answers `markup_at`, takes no mouse buttons and no hover, so a click reaches whatever is in front of or behind it, and recovery gives all of that back. Evidence: `test_flattened_markup_lets_the_pointer_through_to_what_is_behind`. NOT done: the crosshair cursor the report mentions. There is no flatten tool in the tool table — flattening is a menu action — so nothing here sets a crosshair for it. Needs the reporter to say what was selected when they saw it. The class chooser now offers Markups, Text and Measurements, the classes that exist since the strip-down.

- **(new)** Walk the whole application as somebody meeting it for the first time and write down what is wrong with it.
  - **Missing:** Not started. A first-run walk of the whole application has not been done, and what it finds is meant to become its own list of tasks rather than staying one entry. It is more worth doing now than it was: three features have been removed since the walk was asked for, and a removal leaves loose ends a walk is exactly the way to find.

- **(new)** Recolour a snapshot the way a page and an image can be recoloured.
  - **Missing:** Logged rather than half-built. A snapshot is stored as a `QPicture` — a recording of drawing commands — not as the line work it was taken from, and a command stream cannot be replayed through a colour substitution. Giving a snapshot the same swap, colourise and transparency means keeping its source items alongside the recording so the picture can be rebuilt recoloured; repainting a raster of it would throw away the vectors, which is the whole point of a snapshot.

## Left behind by the removals

Found by this audit rather than reported.

- `docs/COMPLETED_TASKS.md` is a dated evidence record from the calculation era. Its entries are true of the build they were written against and false of this one. It is kept as history; it should not be read as a description of the app.
- `docs/backlog.md` still refers to "the layer switches" as a comparison for the page bar, in a task that is otherwise live.
- `markforge/ui/icons.py` still draws `panel_variables`, `panel_functions`, `panel_problems` and `variables`. Nothing asks for them.
