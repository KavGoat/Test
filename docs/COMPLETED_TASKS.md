# MarkForge — evidence record

Audited: 2026-09-07 against `claude/markforge-python`, with the suite green
and `tools/session_fuzz.py` clean over two hundred rounds. Re-checked the same
day by driving the running application and looking at it, which is where the
last section came from.

**This is not the completion record.** It changes no checkbox in
`docs/tasklist.md` and no status in `docs/tasklist.xlsx`; only the user marks a
requirement complete. What it says is narrower and checkable: *here is the code
that implements this, and here is the test that holds it*. Where something is
built but nothing holds it, this says so — an untested feature is a feature
that will break quietly.

Everything below was re-checked against the branch as it stands, not carried
over from an earlier audit. The previous version of this file described the
calculation-era application and has been replaced; if you want that history it
is in the git log.

---


