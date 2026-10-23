#!/usr/bin/env python3
"""Holds Claude to the vault check. A Claude Code hook (see .claude/settings.json). Standard library only.

PreToolUse on Bash, for a command that runs `git push` or `git commit` anywhere in it:
- a push waits while `python3 tools/vault.py check` fails: the command is blocked (exit 2) and Claude reads, on stderr,
  what to fix;
- a commit goes ahead with the check's report as a warning for Claude, unless it would put something confidential into
  the history, which stays there: a code name in the command or its message, a line of a Private/ note outside it, or
  a note moved out of Private/ without the words "out of Private/" in the message;
- a check that does not finish in time, or cannot run, blocks nothing: Claude is told to run it and say so;
- a command that runs `vault.py refresh` before it commits, such as `vault.py refresh && git commit -am x && git push`,
  is not held for generated parts that are out of date: the refresh brings them up to date before the commit.
Any other command passes untouched.

Stop: when Claude is about to end its turn with work not yet pushed and the check fails, Claude is sent back once to
fix it or to say what it needs from the executive. On the second stop of the same turn it may stop, and the executive
sees a one-line warning.

The vault is the folder at or above the hook's cwd that holds tools/vault.py and CLAUDE.md, else $CLAUDE_PROJECT_DIR.
The hook changes no file of the vault.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent)
TIMEOUT = float(os.environ.get("VAULT_HOOK_TIMEOUT", "20"))  # seconds; the hook's own limit in settings.json is 30
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
FALLBACK = re.compile(r"\bgit\b[^;&|\n]*?\s(commit|push)\b|\bvault\.py\s+(refresh)\b")
LEAK = re.compile(r": a confidential term outside Private/$|: holds a line of Private/")
REFRESHED = re.compile(r": the generated part is out of date;|: an unresolved git conflict in the generated part;")
FIX = ("Run python3 tools/vault.py refresh if it says a generated part is out of date, fix the rest in the notes and "
       "registers, and run python3 tools/vault.py check until it passes. Never invent a source, an owner or a date: "
       "if a fact is missing, ask the executive. Do not work around this hook.")


def steps(command):
    """In order, the 'refresh' of vault.py and the git 'commit' and 'push' that the Bash command runs."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = [t.strip("`") for t in lex]
    except ValueError:  # unbalanced quotes: fall back to a plain search
        return [git or refresh for git, refresh in FALLBACK.findall(command)]
    found = []
    for i, tok in enumerate(tokens):
        if tok.endswith("vault.py") and tokens[i + 1:i + 2] == ["refresh"]:
            found.append("refresh")
        if tok != "git" and not tok.endswith("/git"):
            continue
        j = i + 1
        while j < len(tokens) and tokens[j].startswith("-"):
            j += 2 if tokens[j] in GIT_OPTS_WITH_VALUE else 1
        if j < len(tokens) and tokens[j] in ("commit", "push"):
            found.append(tokens[j])
    return found


def git_actions(command):
    """The set of 'commit' and 'push' that the Bash command runs anywhere in it."""
    return set(steps(command)) - {"refresh"}


def refreshes_first(command):
    """True when the command runs vault.py refresh before its first commit, and pushes, if it does, after it."""
    order = steps(command)
    if "refresh" not in order or "commit" not in order or order.index("refresh") > order.index("commit"):
        return False
    return "push" not in order or order.index("push") > order.index("commit")


def vault_root(cwd):
    """The vault Claude is working in: the nearest folder at or above cwd with tools/vault.py, else the project."""
    here = Path(cwd or PROJECT)
    for p in [here] + list(here.parents):
        if (p / "tools" / "vault.py").is_file() and (p / "CLAUDE.md").is_file():
            return p
    return PROJECT


def run_check(root):
    """('passed' | 'failed' | 'unknown', report). Only a check that ran and found errors is 'failed'."""
    try:
        r = subprocess.run([sys.executable, str(root / "tools" / "vault.py"), "check", "--vault", str(root)],
                           capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return "unknown", "The check did not finish within %d seconds." % TIMEOUT
    except OSError as e:
        return "unknown", "The check could not run: %s" % e
    if r.returncode == 0:
        return "passed", r.stdout.strip()
    if r.returncode == 1 and "To fix before the push:" in r.stdout:
        return "failed", r.stdout.strip()
    tail = (r.stderr or r.stdout).strip().splitlines()[-5:]
    return "unknown", "The check could not run (exit %d):\n%s" % (r.returncode, "\n".join(tail))


def git(root, *args, env=None):
    return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True, timeout=10, env=env)


def code_names(root, text):
    """True when the text holds a word listed with vault.py private-term."""
    try:
        settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        terms = {(t["n"], t["h"]) for t in settings.get("private_terms", [])}
        if not terms:
            return False
        sys.path.insert(0, str(root / "tools"))
        import vault
        return vault.hits(text, terms, sorted({n for n, _ in terms}))
    except Exception:
        return False


def moved_out_of_private(root):
    """[(from, to)] for the notes that the work in progress moves out of Private/, staged or not, as git sees moves."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))  # a scratch index: the real one stays
            if git(root, "read-tree", "HEAD", env=env).returncode:
                return []
            git(root, "add", "-A", "--", ".", env=env)
            out = git(root, "diff", "--cached", "-M", "--name-status", "-z", "--relative", "HEAD", env=env).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    fields, moves = out.split("\0"), []
    while fields and fields[0]:
        status = fields.pop(0)
        if status.startswith(("R", "C")):
            moves.append((fields.pop(0), fields.pop(0)))
        else:
            fields.pop(0)
    return [(a, b) for a, b in moves if a.startswith("Private/") and not b.startswith("Private/")]


def work_not_pushed(root):
    """True when the working tree has changes or the branch has commits its upstream lacks."""
    try:
        if git(root, "status", "--porcelain").stdout.strip():
            return True
        ahead = git(root, "rev-list", "--count", "@{upstream}..HEAD")
        return ahead.returncode != 0 or ahead.stdout.strip() not in ("", "0")
    except (OSError, subprocess.TimeoutExpired):
        return True  # cannot tell: treat as work in progress


def errors_of(report):
    tail = report.partition("To fix before the push:")[2]
    return len([line for line in tail.splitlines() if line.startswith("  ")]) or 1


def context(text):
    """A note for Claude that lets the command go ahead."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}))
    return 0


def block(text):
    print(text, file=sys.stderr)
    return 2


def pre_tool_use(data, root):
    command = (data.get("tool_input") or {}).get("command") or ""
    actions = git_actions(command)
    if not actions:
        return 0
    action = "push" if "push" in actions else "commit"
    if "commit" in actions:
        if code_names(root, command):
            return block("Blocked: this git commit names a confidential term, which would stay in the history. Write "
                         "the commit message without it, as in CLAUDE.md, \"Confidential\".")
        moves = moved_out_of_private(root)
        if moves and "out of private/" not in command.lower():
            return block("Blocked: this git commit moves %s out of Private/. A note leaves Private/ only when the "
                         "executive asks for it in plain words. If they did, say so in the commit message, with the "
                         "words \"out of Private/\"; if not, move it back."
                         % ", ".join("%s to %s" % m for m in moves))
    state, report = run_check(root)
    if state == "passed":
        return 0
    if state == "unknown":
        return context("The vault check gave no answer, so this git %s was not held: %s Run python3 tools/vault.py "
                       "check yourself before you push, and tell the executive if it does not run." % (action, report))
    leaks = [line.strip() for line in report.splitlines() if LEAK.search(line)]
    if "commit" in actions and leaks:
        return block("Blocked: the vault check finds something confidential outside Private/, and a commit would keep "
                     "it in the history:\n\n%s\n\nTake it out, or move it to Private/, then commit." % "\n".join(leaks))
    errors = [line for line in report.partition("To fix before the push:")[2].splitlines() if line.startswith("  ")]
    if errors and all(REFRESHED.search(line) for line in errors) and refreshes_first(command):
        return 0  # the command's own refresh brings the generated parts up to date before it commits
    if action == "commit":
        return context("The vault check fails. The commit goes ahead, but the push will wait until the check "
                       "passes.\n\n%s\n\n%s" % (report, FIX))
    return block("Blocked: the vault check fails, so this git push must wait.\n\n%s\n\n%s" % (report, FIX))


def stop(data, root):
    if not work_not_pushed(root):
        return 0
    state, report = run_check(root)
    if state != "failed":
        return 0
    if data.get("stop_hook_active"):  # Claude was already sent back once this turn: let it stop, tell the executive
        print(json.dumps({"systemMessage": "The vault check still fails (%d to fix), so nothing should be pushed yet. "
                                           "Ask Claude to fix what python3 tools/vault.py check reports."
                                           % errors_of(report)}))
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext":
          "Before you stop: the vault check fails and there is work not yet pushed.\n\n%s\n\n%s Then commit and push. "
          "If you are waiting for the executive's answer, or the fix needs a fact only they have, say in one line what "
          "is missing and stop." % (report, FIX)}}))
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0  # not hook input: no objection
    root = vault_root(data.get("cwd"))
    if not (root / "tools" / "vault.py").is_file():
        return 0  # not a vault
    event = data.get("hook_event_name")
    if event == "PreToolUse" and data.get("tool_name") == "Bash":
        return pre_tool_use(data, root)
    if event == "Stop":
        return stop(data, root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
