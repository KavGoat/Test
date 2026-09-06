# CalcForge completed-work evidence

Last rebuilt: 2026-09-06.

Requirements for which the current source has implementation evidence **and** a
validation this session confirmed. Provided for user review; it is not the
authoritative completion record. Only the user marks completion in
`docs/tasklist.xlsx` or changes a checkbox in `docs/tasklist.md`.

An entry earns a place here only when the behaviour was exercised — through the
real Qt event queue, or through the running application — during the session
that wrote the entry. A cited test name is not on its own evidence that the
behaviour still holds.

This file was emptied and rebuilt at the user's instruction. The two entries
below are carried over because they were re-validated in this session; every
other prior claim was cleared and its task returned to
`docs/UNADDRESSED_TASKS.md` for re-audit.

## Pages and document structure

- Multiple selected pages are deleted, duplicated, copied and pasted, and
  reordered as a run. The menu entry is two words — "Delete pages", "Duplicate
  pages", "Copy pages" — and names how many pages it is about in its tooltip.
  Evidence: the page-run tests from `test_several_pages_are_deleted_together`
  through `test_the_menu_says_how_many_pages_it_is_about`, green in a full
  1254-test run at `c91d4f3`; and confirmed against the running application,
  where picking two pages out in the Pages panel gives those three labels with
  "these 2 pages" in each tooltip.
- Pasted pages show where they will land and land there. The entry reads
  "Paste after" / "Paste before" and names the page it lands on in its
  tooltip. Evidence: `test_pasting_a_page_says_where_it_will_land` and
  `test_a_pasted_page_lands_where_it_said_and_is_shown`, green at `c91d4f3`;
  and confirmed against the running application, where the page-2 menu reads
  "Paste a page after page 2".
