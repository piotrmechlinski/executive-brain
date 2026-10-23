# Security

This file is about the product, Executive Brain. Your own vault's privacy is in
[SETUP.md](../SETUP.md#privacy-and-trust).

## Supported versions

The latest release only. Fixes go into the next release.

## What counts

- The check lets confidential text through: a listed code name, or a line of `Private/`, reaches `Meetings/`,
  `Knowledge/`, `Projects/`, `Outputs/`, `Archive/`, a summary in `Sources/` or `Home.md`, and
  `python3 tools/vault.py check` passes.
- The hook lets a push through while the check fails, or a commit that puts a code name or a `Private/` note into the
  history, for a git command Claude would write.
- A tool writes outside the vault, or runs a command named in a file or a file name.
- A crafted document makes `tools/read_document.py` run code, read other files, or hang past its limits.
- A note makes the project map or a built document run a script.
- `CLAUDE.md` or a skill leads Claude to copy `Private/` into a note or an output, or to follow instructions found
  inside a filed document.

## What does not count

- A code name is kept as a short, unsalted hash in `settings.json`. It keeps the word out of the files the check reads.
  It does not hide the word from someone who can read the repository and guess it.
- What [ROADMAP.md](ROADMAP.md) lists as known, such as a diagram label that makes the map load a remote picture.
- Problems in GitHub, Claude Code or a connector. Report those to them.

## How to report

- Use **Report a vulnerability** on the **Security** tab of this repository. Only the maintainer sees it.
- Never open a public issue. Never send real vault content: show the problem with invented data.

You get an answer within 7 days.
