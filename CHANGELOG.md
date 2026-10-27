# Changelog

The version follows the vault: a major version when a vault that passed the check would fail it or has to be moved
over; a minor one for a new command, skill or register template; a patch for fixes and documents. `vault.py status`
shows the version a vault runs.

## 1.0.1 (2026-10-27)

- **macOS:** the tests pass on a Mac.
  - The session start runs git without timeout(1) where the system has none, as on macOS. A test runs it on a PATH
    without timeout.
  - The project map's test compares paths the way the vault resolves its root: on macOS, `/var` is `/private/var`.
- **README:** a new section, Updating: how a copy gets a new release.

## 1.0.0 (2026-10-23)

The first public release. What it is:

- **The vault:** five kinds of data (sources, meetings, knowledge, projects, outputs), one folder each, with the Inbox,
  Private, Archive and Templates, and one direction of flow.
- **The registers:** people, decisions, actions, risks, milestones, assumptions and current state, shared by the
  role, every row with a project, a date and a source. A new register for the role is a copy of a template.
- **The rules for Claude** in `CLAUDE.md`, and five commands: `/setup`, `/debrief`, `/ingest`, `/brief` and `/review`.
- **The tools:** the check before every push and the hook that holds a push to it, the refresh of project cards and
  Home, the weekly review, briefs, the project map, documents from notes, and the reader of Office and PDF files.
- **An example:** the vault of a fictional COO, in `examples/Brightwater`.

What changed while it was made ready:

- **Licence:** MIT. Mermaid's own MIT notice ships next to it, in `tools/vendor/LICENSE-mermaid.txt`.
- **The author** is named in the README.
- **The check** applies its rules on notes and names to no hidden file or folder, such as `.github/`, so a vault can
  carry its own automation; it still reads them for confidential words. It skips `tools/`, `build/` and `examples/`
  at the top level only.
- **SETUP** suggests `my-executive-brain` as the name of your copy.
- **The check never passes in silence:**
  - an unresolved git conflict, a table broken by a stray line, an unknown Status and a frontmatter list where one
    value belongs are errors, not dropped rows or a crash; `refresh` will not rebuild from a file with a conflict;
  - register rows and facts are reported at their line in the file;
  - an HTML output is read without its scripts, styles and embedded data, and what each file held is remembered in
    `build/` by its hash, so a vault full of maps is checked in about a second;
  - a `settings.json` that is not valid JSON is an error, not a crash.
- **Tests** in `tools/tests`: `python3 -m unittest discover -s tools/tests`.
- **The README** opens with what it is, who it is for, a picture of the project map, a short demo, how it differs and
  how to start. "How it compares" sets it against five groups of tools. It no longer promises a brief, or that a voice
  memo is transcribed.
- **The example** opens with three commands that try it with git and Python alone, on the example's own date.
- **The map's timeline** keeps its labels clear of the project names, with lighter grid lines.
- **Commitments get a home:** an Actions register (`T`), with an owner and a date only if one was set, and one table
  in `CLAUDE.md`, "What goes where", that the skills follow. `/debrief` also asks what is still to be decided.
- **The weekly review shows progress:** what was decided, closed or changed since the last review, the open actions by
  owner, and the rows still marked *(unverified)*. The map shows italics, and never puts actions on the timeline.
- **The example** has its commitments as actions, and its unverified turnover figure marked as such.
- **Community files** in `.github/`: CONTRIBUTING, a security policy (GitHub's private reporting, an answer within
  7 days), issue forms that open with "This is the public repository of the product, not your vault" and ask to
  confirm that nothing private is in them, a pull request template and a roadmap. `CLAUDE.md` and `AGENTS.md`: no
  vault content in a public place; a problem is reported with invented data.
- **SETUP says what is needed and what works:** the plans, "Use this template" with "Include all branches" unticked,
  the vault opened on its own, the 25 MiB upload limit, a part on working on a computer, and an "Updating" that names
  every product file and how to bring a release in. `read_document.py` reads a saved e-mail (`.eml`) with its sender,
  date and attachments, and names a scanned PDF as one, to be read as pictures; `/ingest` reads a file before it
  names it.
- **Answers and briefs that cite:** `CLAUDE.md` asks every answer to name its rows and link their sources, and to say
  so when the vault holds nothing. `/brief`, with `vault.py brief`, writes a brief before a meeting, or on a person or
  a project: what is overdue, open and unverified, who the people are and the last meetings, every line with its ID
  and source, for a Word file or a PDF. Word and PDF files show italics and code as such.
- **No known advisories in what the product pins:** pypdf 6.21.2 (from 5.1.0; `pip-audit` finds nothing) and Mermaid
  11.17.2 (from 11.13.0), which no longer lets a `classDef` put HTML outside its diagram or a Gantt chart freeze the
  map. A diagram that fails no longer stops the others. The packages Mermaid bundles have their notices in
  `tools/vendor/THIRD-PARTY-NOTICES.txt`, and every map points to them.
- **Files from others are read within limits:** `read_document.py` refuses an archive that unpacks to more than 50 MB of
  text, XML that declares entities or nests too deeply, cuts a run of spaces at 1,000 and gives `pdftotext` a minute;
  the map escapes a project ID and takes only `#RRGGBB` colours.
- **Privacy and trust, said as it is:** a README section on what GitHub, Anthropic and connectors see, what
  `Private/` and the check do and do not do, and what the hash guards against; a part of `SETUP.md` for a legal or
  IT team, with how to export, delete and remove a leak; `CLAUDE.md`, `Private/README.md` and the skills claim no more
  than the check does. Filed material is data: a request inside it is reported, never carried out, and the vault's
  settings deny web fetches, `curl` and `wget`. Summaries in `Sources/` are checked like notes.
- **Sources open with one click on GitHub:** a row's Source is a Markdown link, its path in angle brackets or with
  `%20` for each space, which `vault.py link NAME --from FILE` writes. The check names a path with spaces and no `<>`, and refuses a folder, a
  path outside the vault, a web address alone or a `Private/` note as a source; an old `[[wikilink]]` still passes,
  with a warning. Nothing outside `Private/` may link into it, and a `Private/` note takes a name of its own. The map
  shows Markdown links as links. The example is converted.
- **The confidential check compares words, not characters:** case, accents, invisible characters, look-alike letters,
  HTML tags and entities, Markdown, white space and line breaks no longer hide a code name or a `Private/` line, and a
  code name with an umlaut is kept without it too. It also reads hidden folders, `CLAUDE.md`, the title and footer in
  `settings.json`, file names, `Private/` notes in `.txt`, and outputs in OpenDocument, e-mail, SVG and RTF. A code
  name kept before keeps working.
- **`/setup` in two rounds:** one message (name, role, city, the projects in a line each, the company's rules) gives
  the project cards, an action for each next step, Home and the map as a PDF; people, decisions, risks and dates come
  in a second round, or from a document. It sets the time zone, which the tools and the session start now use,
  replaces the copy's `README.md` with a page that points to Home, and removes the fictional example.
- **`/debrief` and `/ingest`** take what was said with the command first and ask only for the rest.
- **The map on a phone:** `build_map.py` also writes a PDF; on a narrow screen the projects table and the timeline
  scroll in their boxes, and no label crosses a project name. `--send` builds a map without links to GitHub or the
  commit, for someone else.
- **Word and PDF files:** without Node, `build_doc.py` writes the Word file with a warning instead of crashing; a Word
  file has the note's title, no author and today's date; a PDF keeps its footer when the note has no table.
- **A hook holds Claude to the check** (`.claude/check_hook.py`): a push waits while the check fails; a commit goes
  ahead with a warning, unless it would put a code name or a `Private/` note into the history; a check that is slow or
  cannot run holds nothing back; at the end of a turn with unpushed work and a failing check, Claude is sent back once.
  A command that runs `vault.py refresh` before it commits is not held for the generated parts that refresh updates.
- **Every session lands on `main`:**
  - in a cloud session, the session start fetches `main`, completes a shallow clone and switches to `main`, unless the
    session's branch holds work of its own, which it names;
  - it runs after `/clear` and a compaction too, says in one line when the status cannot be read, and works without
    `CLAUDE_PROJECT_DIR`;
  - `vault.py next` also counts the IDs on `main` on GitHub, so two sessions at once do not take the same ID;
  - `CLAUDE.md`, under "Git", and the skills say how to push `main` from a cloud session and how to settle a conflict
    with another session.
