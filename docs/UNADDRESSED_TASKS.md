# CalcForge tasks still requiring work

Audited: 2026-09-06 against `claude/engineering-calc-markup-app-2twiqs`.

The 4 entries below are what the audit could not show working. Each says
what is missing or blocking it. Several are tasks whose base behaviour is
finished and whose recent amendment is not; those name the part that is done so
the remaining work is clear.

This is not the user-owned completion record. It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`.

## 1. Core concept

- **(new)** Support multiple open documents at once: PDF review documents and `.cfx` CalcForge documents appear in separate tabs, can be viewed side-by-side in a split view, and can be moved into independent application windows. Each document keeps its own pages, state and active tool without leaking into another tab/window.
  - **Missing:** Two of the three parts done; split view is not. DONE — tabs: each open document has a tab with its own document, canvas, undo history, page and tool, and one view is handed a different canvas on a switch, so nothing is re-wired and nothing of one document reaches into another. The bar hides itself when only one document is open. File > New tab, Ctrl+T. DONE — independent windows: File > New window, Ctrl+Shift+N, each with its own document, view and undo stack; a window built this way is kept alive rather than collected as the call returns, and every tab's undo stack is released when the window closes so none of them calls back into a window that has gone. NOT DONE — side-by-side split view: that needs a second live PageView in the same window, which the shared-view design deliberately avoids, so it is a separate piece of work rather than a bolt-on. Also not done: PDF review documents opening into a tab of their own, which follows the split-view question. Evidence: test_two_documents_open_in_tabs_without_reaching_into_each_other, test_a_second_window_keeps_its_own_document.

## 4. Equation editor

- **(new)** Use the locally supplied `SMath Studio/` installation, especially its desktop UI, examples and snippets, as the behavior reference when resolving equation-editor interactions. Reproduce its navigation and structured-expression behavior by observing the application; do not copy proprietary implementation code.
  - **Missing:** Standing reference instruction, not a code change: the SMath Studio/ installation is in the repo but no audit of its behaviour has been recorded. Stays a requirement per HANDOVER rule 5.

## 27. Reliability / process

- Never let hitting the token/usage limit silently end the session's work — pause, and resume automatically once the limit resets, without needing a fresh prompt from you (130, 138) — **not something this end can promise.** A session that runs out of context is summarised and continued, and that is automatic; a session that runs out of *usage* stops until the limit resets and needs a prompt to pick up again. What is under control here is that nothing is left half-finished and unrecorded: work is committed and pushed as it is done, and this list says what is built and what is not, so whatever picks the work up next — a fresh session, or this one after a reset — starts from the list rather than from memory
  - **Missing:** Platform limitation, unchanged: the session environment cannot guarantee resuming itself after a usage limit. Stays a requirement with that note, per HANDOVER rule 5.

- **(new)** Validate interactive changes through the real CalcForge UI, not only unit-level code inspection. Agents must drive the canvas with pointer moves, clicks, drags, keyboard arrows and configured shortcuts, including Escape/cancel paths, and look for stuck tools, lost focus, incorrect cursor states, blocked input, broken selections and other interaction regressions. Keep repeatable Qt event-driven tests for each defect found.
  - **Missing:** Ongoing acceptance requirement rather than a finished feature: it governs how every future interactive change is validated, so it never closes.
