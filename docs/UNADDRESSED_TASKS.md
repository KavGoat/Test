# Tasks requiring follow-up

Reviewed 2026-09-17. This file contains current follow-up only. Implementation
and test evidence is in `COMPLETED_TASKS.md`. User-owned completion cells in
`tasklist.md` and `tasklist.xlsx` remain unchanged.

## Application verification pending

The September 17 findings and verified repairs are in
[REVIEW_2026-09-17.md](REVIEW_2026-09-17.md). Still open: the cut-off Whiteout
request; the meaning of “choose size and fits”; Windows 1920-pixel geometry;
third-party viewer click acceptance for title/contents links; cold snapping
latency on a dense user PDF; the full item-property/dialog audit; and native
Bluebeam comparison on Windows. The 1280-pixel text style toolbar still puts
some controls in overflow. These remain requirements in `tasklist.md` with
all completion status left to the user.
The offscreen-only randomized session reported zero application failures but
segfaulted during Qt shutdown; the same 300-round seed on the native Cocoa
backend exited cleanly. The cause of that backend-specific teardown remains
unidentified.

| Report | Implemented and verified | Remaining verification |
| --- | --- | --- |
| Escape-resistant tool lockup | Reproduced and fixed Escape being swallowed by an inline panel editor, plus a stale scene mouse grab surviving cancellation. The earlier abandoned-callout-anchor fix is also retained. Real Qt regressions cover these cases and preserve normal dialog cancellation. | The user's exact original sequence is still unknown. These concrete failure paths are fixed; confirmation against that original sequence remains pending. |
| Dense-PDF speed and low-zoom clarity | Multicore rendering, cancellation and bounded caches are implemented. The dense synthetic benchmark improved 3.0×. Both pages of the repository reference PDF now have serial/parallel pixel checks at overview, normal and detail zooms; mixed scan/text/vector benchmarking also checks matching output. | The user's specific problematic PDFs have not been supplied. Their workload still needs acceptance testing. |

No additional reproduced application defect from this review is currently
awaiting implementation. The verification items above are not claims that
all possible lockups or PDFs have been covered.

Overall editing performance was profiled and improved in the follow-up review:
the 500-markup native fixture measured 35× faster undo/redo and 1.83× faster
pointer snapping. See [APP_PERFORMANCE.md](APP_PERFORMANCE.md) for timings and
scope. This is verified implementation evidence; acceptance on the user's
specific workload remains pending as above.

## External requirement — blocked

**Automatically resume after a usage-limit reset.** This remains unfulfilled.
The application repository cannot change the assistant host's account limits
or restart a stopped assistant session. Commits, the handover and task records
preserve progress for continuation; they do not implement automatic restart.

## Standing requirement — performed for this revision

**Validate interactive changes through actual Qt events.** This is a continuing
engineering requirement, not an unfinished feature. The current revision has
focused cancellation/rendering regressions and a native 1,000-round stress
session (seed 131) with zero failures. Repeat relevant checks after future
changes. Final suite counts are recorded in `COMPLETED_TASKS.md`.

## Archived material

Old “not done” statements about features subsequently implemented have moved
to [TASK_AUDIT_HISTORY.md](TASK_AUDIT_HISTORY.md). They are not active tasks.
