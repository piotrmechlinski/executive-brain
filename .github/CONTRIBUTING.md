# Contributing

This file is about the product, Executive Brain. If you are an executive using your own copy, you can ignore it.

## Before anything: nothing private

This repository is public. Never put anything from a real vault in an issue, a pull request or a commit: no names,
no notes, no register rows, no file names. Show a problem with [the example](../examples/Brightwater) or with
invented data. Examples stay fictional.

## Report a problem

Open an issue and choose **Something does not work**. Give the version that `python3 tools/vault.py status` shows,
what you did and what happened. A security problem goes to [SECURITY.md](SECURITY.md), never to an issue.

## Propose a change

1. Open an issue first, unless the change is a typo or a broken link.
2. Read [ROADMAP.md](ROADMAP.md): what is planned and what is out.
3. Keep a pull request to one change.

## Welcome

- Fixes to the tools, with a test in `tools/tests/`.
- A clearer README, SETUP or skill.
- Readers for more document formats in `tools/read_document.py`.
- A new register template.

## Not welcome

- Anything that sends vault content to a service outside GitHub and Claude.
- New top-level folders or files in the vault.
- Dependencies outside `requirements.txt`; `tools/vault.py` stays on the standard library.

## The checks

Run these before you push. All must pass; the same run on every pull request.

    python3 tools/vault.py check
    python3 tools/vault.py check --vault examples/Brightwater
    python3 -m unittest discover -s tools/tests

## A new Mermaid

Copy `dist/mermaid.min.js` from the npm package into `tools/vendor/`, set `MERMAID` in `tools/build_map.py`, and run
`python3 tools/vendor/make_notices.py VERSION` to write the notices of the packages it bundles.

## House style

- Plain words, short sentences, no emoji, no hype.
- Every claim in the README is true of the code.
- One commit per change, with a message that says what changed.
- A change that users notice gets a line in [CHANGELOG.md](../CHANGELOG.md), under the coming version.
