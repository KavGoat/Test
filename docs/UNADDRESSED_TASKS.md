# CalcForge tasks still requiring work

Audited: 2026-09-06 against `claude/engineering-calc-markup-app-2twiqs`.

The 3 entries below are what the audit could not show working. Each says
what is missing or blocking it. Several are tasks whose base behaviour is
finished and whose recent amendment is not; those name the part that is done so
the remaining work is clear.

This is not the user-owned completion record. It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`.

## 1. Core concept

- **(new)** Support multiple open documents at once: PDF review documents and `.cfx` CalcForge documents appear in separate tabs, can be viewed side-by-side in a split view, and can be moved into independent application windows. Each document keeps its own pages, state and active tool without leaking into another tab/window.
  - **Missing:** Two of the three parts done; split view is not. DONE — tabs: each open document has a tab with its own document, canvas, undo history, page and tool, and one view is handed a different canvas on a switch, so nothing is re-wired and nothing of one document reaches into another. The bar hides itself when only one document is open. File > New tab, Ctrl+T. DONE — independent windows: File > New window, Ctrl+Shift+N, each with its own document, view and undo stack; a window built this way is kept alive rather than collected as the call returns, and every tab's undo stack is released when the window closes so none of them calls back into a window that has gone. NOT DONE — side-by-side split view: that needs a second live PageView in the same window, which the shared-view design deliberately avoids, so it is a separate piece of work rather than a bolt-on. Also not done: PDF review documents opening into a tab of their own, which follows the split-view question. Evidence: test_two_documents_open_in_tabs_without_reaching_into_each_other, test_a_second_window_keeps_its_own_document.

## 27. Reliability / process

- Never let hitting the token/usage limit silently end the session's work — pause, and resume automatically once the limit resets, without needing a fresh prompt from you (130, 138) — **not something this end can promise.** A session that runs out of context is summarised and continued, and that is automatic; a session that runs out of *usage* stops until the limit resets and needs a prompt to pick up again. What is under control here is that nothing is left half-finished and unrecorded: work is committed and pushed as it is done, and this list says what is built and what is not, so whatever picks the work up next — a fresh session, or this one after a reset — starts from the list rather than from memory
  - **Missing:** Platform limitation, restated accurately rather than closed. Nothing in this environment resumes a session when a usage limit lifts, and no code in this repository can change that. What does exist is a scheduled wake-up (send_later), which brings a session back at a chosen time but does not detect the limit — arranging to come back, not carrying on. docs/HANDOVER.md now says this, and says that the register and branch should always be left in a state somebody else can pick up from. Stays a requirement per HANDOVER rule 5.

- **(new)** Validate interactive changes through the real CalcForge UI, not only unit-level code inspection. Agents must drive the canvas with pointer moves, clicks, drags, keyboard arrows and configured shortcuts, including Escape/cancel paths, and look for stuck tools, lost focus, incorrect cursor states, blocked input, broken selections and other interaction regressions. Keep repeatable Qt event-driven tests for each defect found.
  - **Missing:** Ongoing acceptance requirement, and it should stay open: it governs how every future interactive change is validated, so there is no state in which it is finished. It was held to throughout this session — the size entry, the count marker, the completion list, the wheel, the cloud cursor, undo, tabs and a second window were each driven through the real Qt event queue or the running application, and three of the fixes were only found that way. Leaving it open is the point of it.
