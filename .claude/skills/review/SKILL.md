---
name: review
description: The weekly review of the vault, covering what is overdue, what is due soon, projects that have not moved, the Inbox and done projects to archive. Use when the user types /review or asks what needs their attention.
---

# Weekly review

1. `git pull --rebase origin main`, then `python3 tools/vault.py review`.
2. Show it short. First what was decided, closed or changed since the last review, in a few lines the executive can
   forward. Then each with its owner: overdue, due within 14 days, the open actions by owner, projects with no change
   in 30 days, the Inbox, done projects to archive, open risks without a mitigation, rows marked unverified.
3. Propose one step for each: close it, move its date (with the reason), chase its owner (draft the message), confirm
   or correct an unverified row, or archive the project.
4. Apply what the executive agrees. Write the review down as `Meetings/YYYY-MM-DD Weekly review.md` with
   `source: debrief`, and make it the source of every row you change.
5. `python3 tools/vault.py refresh`, then `python3 tools/vault.py check`. Commit as `Weekly review YYYY-MM-DD`, then
   pull and push `main` as `CLAUDE.md` says under "Git".
