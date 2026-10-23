---
name: setup
description: The first session in a new vault. Ask a few questions, write the first project cards and show Home and the project map within minutes, then offer to fill in people, decisions, risks and dates. Use when the user types /setup, or when "About me" in CLAUDE.md still says "(not set)".
---

# Setup

Two rounds. The first ends with something to look at: Home and the project map. The second is offered, never forced.

1. Read `CLAUDE.md`. If "About me" is already filled in, ask whether to start again or only add to it.
2. **Round one.** Take what the message with the command already gives, and ask only for the rest, in one message and
   in the executive's language. Say that a dictated answer is fine.
   - their name, role and organisation;
   - the city they work from, for the time zone;
   - each project they run or own, in one line: a name, who owns it, the next step. Three to seven is usual;
   - one line on their company's rules for AI tools, recordings or what may be written down, or "none I know of".
3. Write round one at once:
   - "About me" in `CLAUDE.md`, the company's rules included; in `settings.json`, `title` and `footer` (for example
     `"Alex Morgan · COO · Brightwater"` and `"Brightwater · internal"`) and `timezone`, an IANA name such as
     `"Europe/Warsaw"`;
   - `Meetings/YYYY-MM-DD Setup.md` from `Templates/Meeting.md`, with `source: debrief`: what they said;
   - one card per project in `Projects/` from `Templates/Project.md`, each with the next ID from
     `python3 tools/vault.py next P`, its owner and next step, its goal if they gave one ("not set yet" if not), and
     a first map of three boxes: today, the next step, the goal, a few words each;
   - each next step as an action in `Knowledge/Actions.md`, with its owner and its date if it has one, the setup note
     as its source;
   - `README.md` replaced with this page, filled in, so that GitHub opens their vault and not the product:

     ```markdown
     # <Name>'s vault

     Kept by Claude Code. Start at [Home](Home.md): the projects, what is open and what is overdue.

     The rules Claude follows are in [CLAUDE.md](CLAUDE.md), the setup in [SETUP.md](SETUP.md). Made with
     [Executive Brain](https://github.com/piotrmechlinski/executive-brain).
     ```
   - `examples/` removed with `git rm -r -q examples`, if it is there: it is a fictional vault, and its facts must
     never be taken for theirs.
4. `python3 tools/vault.py refresh`, `python3 tools/vault.py check`, then `python3 tools/build_map.py` and copy
   `build/Project map.pdf` to `Outputs/YYYY-MM-DD Project map.pdf`. Commit as `Setup`, then pull and push `main` as
   `CLAUDE.md` says under "Git".
5. Show the result in a few lines: the projects as Home lists them, with links to `Home.md` and the map's PDF on
   GitHub. Then offer round two: "Shall we add the people, the decisions, the risks and the dates now? Or drop a
   strategy, an organisation chart or a board pack into `Inbox/` and I start from it."
6. **Round two,** when they want it, a few questions at a time:
   - the people who matter: name, role, and what they need from the executive;
   - decisions, commitments, risks and dates already known;
   - the language for notes, and anything about style;
   - for each project, the goal in one line and what it is worth, if not given yet.

   File it as `CLAUDE.md` says under "What goes where", with the setup note as the source. If `Inbox/` holds material,
   file it as `/ingest` does. Refresh, check, build the map again, commit as `Setup: round two`, then pull and push
   `main`.
7. Tell them how to work from now on, in four lines: `/debrief` after a meeting, material into `Inbox/` and
   `/ingest`, `/brief` before a meeting, `/review` once a week.
