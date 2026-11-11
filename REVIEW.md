# Review instructions — plow-wiki

Repo-specific reviewer policy. The universal review policy is prepended by the
reviewer and is not restated here.

## What this repo is

**A curated, Obsidian-compatible wiki of durable facts for Plow agents.** A
Python CLI (`wiki init|validate|index|snapshot|history`) over plain Markdown in
`~/Plow/wiki` on the owner's Mac, plus the `plow-wiki` agent skill. Agents
reach it as a latch plugin (`latch-plugin.json`); `obsidian-wiki` supplies the
other wiki skills.

**Stage:** internal. Used by the operator's own agents on their Mac.

## Review bar

Report **Critical** and **Important** findings only. Nits and style go
unmentioned.

- **No security against coworkers.** Everyone with push access, and our own
  agents, are trusted. Don't propose guards, validation or sandboxing
  against them.
- **Simplest code wins.** Prefer deleting a branch to adding one; don't guard
  cases that can't happen at the current operating point.

## Where the real risks are

- **Owner content is sacred.** `wiki index` must never clobber hand-edited
  text outside generated tables; flag a change that can.
- **Snapshot leaks.** `wiki snapshot` commits the wiki to git after a
  credential scan; flag a change that weakens the scan or commits `.env`.
