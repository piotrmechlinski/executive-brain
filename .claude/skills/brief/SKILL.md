---
name: brief
description: A brief before a meeting, or on a person or a project. What is overdue, open and unverified, who the people are and the last meetings, every line with its ID and source, as a note, a Word file or a PDF. Use when the user types /brief, or asks to be briefed or prepared for a meeting.
---

# Brief

1. Work out what the brief is for from what they said: a meeting (who will be there, which projects), a person, or a
   project. Ask only if it is unclear.
2. Write it from the vault, with the project IDs and the people's names as the registers spell them:
   `python3 tools/vault.py brief P1 "Tom Becker" --out "Outputs/YYYY-MM-DD Brief — Subject.md"`. The tool writes every
   line with its ID and a link to its source. Change nothing in it by hand: a correction goes into the registers, and
   the brief is built again.
3. In the chat, give three to five lines for the meeting: what is decided, what is still open and who owns it, what is
   overdue or unverified. Each line names its IDs, as `CLAUDE.md` says under "Answers"; nothing comes from memory or
   the web.
4. If they want a file to read or send: `python3 tools/build_doc.py "Outputs/YYYY-MM-DD Brief — Subject.md"`, then
   copy the PDF or the Word file from `build/` into `Outputs/` under the same name.
5. `python3 tools/vault.py refresh`, then `python3 tools/vault.py check`. Commit as `Brief: Subject`, then pull and
   push `main` as `CLAUDE.md` says under "Git". Give the links to the brief and its files on GitHub.
