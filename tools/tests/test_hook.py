"""Tests for the hook that holds Claude to the vault check (.claude/check_hook.py). Standard library and git.

    python3 -m unittest discover -s tools/tests -v

Each test copies the example vault, with the tools and the hook, to a temporary git repository, and pipes the JSON
that Claude Code sends to the hook command as .claude/settings.json gives it.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = next(p / "tools" for p in Path(__file__).resolve().parents if (p / "tools" / "vault.py").exists())
REPO = TOOLS.parent
EXAMPLE = REPO / "examples" / "Brightwater"
SETTINGS = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
SOURCELESS = "| D5 | Extend the night shift through the peak | P1 | Priya Shah | 2026-11-15 | open | | 2026-10-22 | |"
PRIVATE = "Private/2026-10-12 From the CFO.md"
OFFSITE = "Private/2026-10-20 Offsite in Łódź.md"  # a name git would quote


def command(event):
    entries = SETTINGS["hooks"][event]
    assert len(entries) == 1 and len(entries[0]["hooks"]) == 1, "the test expects one hook per event"
    return entries[0]["hooks"][0]["command"]


@unittest.skipUnless(shutil.which("git") and shutil.which("sh") and EXAMPLE.is_dir(), "needs git, sh and the example")
class Hook(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "vault"
        shutil.copytree(EXAMPLE, self.root, ignore=shutil.ignore_patterns("build"))
        shutil.copytree(TOOLS, self.root / "tools", ignore=shutil.ignore_patterns("tests", "__pycache__", "vendor",
                                                                                   "fonts", "node_modules"))
        shutil.copytree(REPO / ".claude", self.root / ".claude", ignore=shutil.ignore_patterns("skills"))
        shutil.copy(REPO / "CLAUDE.md", self.root / "CLAUDE.md")
        (self.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE_"))}
        self.env.update(CLAUDE_PROJECT_DIR=str(self.root), HOME=tmp.name, GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com", VAULT_TODAY="2026-10-22")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "The vault")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, env=self.env)

    def hook(self, event, data, env=None):
        r = subprocess.run(["sh", "-c", command(event)], input=json.dumps(data), capture_output=True, text=True,
                           env=dict(self.env, **(env or {})), timeout=60)
        return r.returncode, r.stdout, r.stderr

    def bash(self, cmd, cwd=None, env=None):
        return self.hook("PreToolUse", {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": "Bash",
                                        "cwd": str(cwd or self.root), "tool_input": {"command": cmd}}, env)

    def stop(self, active=False):
        return self.hook("Stop", {"session_id": "s", "hook_event_name": "Stop", "cwd": str(self.root),
                                  "stop_hook_active": active})

    def break_vault(self):
        with open(self.root / "Knowledge" / "Decisions.md", "a", encoding="utf-8") as f:
            f.write(SOURCELESS + "\n")

    def assertBlocked(self, result, fragment):
        code, _, err = result
        self.assertEqual(code, 2, "not blocked")
        self.assertIn(fragment, err)

    def assertPasses(self, result):
        self.assertEqual(result[0], 0, result[2])

    # pushes

    def test_a_push_goes_when_the_check_passes(self):
        code, out, err = self.bash("git pull --rebase origin main && git push origin main")
        self.assertEqual((code, out, err), (0, "", ""))

    def test_a_push_waits_while_a_row_has_no_source(self):
        self.break_vault()
        self.assertBlocked(self.bash("git push origin main"), "D5 has no source")

    def test_pushes_written_other_ways_are_caught(self):
        self.break_vault()
        for cmd in ("git -C . push", "FOO=bar git push", "git add -A && git commit -m x && git push",
                    "cd Knowledge && git push"):
            self.assertBlocked(self.bash(cmd), "the vault check fails")
        self.assertBlocked(self.bash("git push", cwd=self.root / "Knowledge"), "D5 has no source")

    def test_other_commands_pass_untouched(self):
        self.break_vault()
        for cmd in ("git stash push", "git status", "git log --oneline -3", "python3 tools/vault.py check", "ls"):
            self.assertEqual(self.bash(cmd), (0, "", ""), cmd)

    # commits

    def test_a_commit_goes_with_a_warning_while_the_check_fails(self):
        self.break_vault()
        code, out, _ = self.bash("git commit -am 'Decision: D5'")
        self.assertEqual(code, 0)
        note = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(note["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", note)  # a warning, not an approval
        self.assertIn("D5 has no source", note["additionalContext"])

    def test_a_commit_message_with_a_code_name_is_refused(self):
        self.assertBlocked(self.bash("git commit -am 'Meeting: Project kestrel and the depots'"),
                           "names a confidential term")

    def test_a_commit_that_would_keep_a_code_name_in_history_is_refused(self):
        with open(self.root / "Meetings" / "2026-10-19 Warehouse vendors.md", "a", encoding="utf-8") as f:
            f.write("- Project Kestrel came up again.\n")
        self.assertBlocked(self.bash("git commit -am 'Meeting: vendors'"), "a confidential term outside Private/")

    def private_note(self):
        """A Private/ note with no code name in it, committed."""
        (self.root / OFFSITE).write_text("# The offsite\n\nAlex wants the leadership offsite in Lisbon, not in "
                                         "London, and has not told the team yet.\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Private: 2026-10-20")

    def test_a_move_out_of_private_is_refused_unless_the_executive_asked(self):
        self.private_note()
        self.git("mv", OFFSITE, "Sources/2026-10-20 Offsite.md")
        self.assertBlocked(self.bash("git commit -m 'Source: offsite'"), "moves %s" % OFFSITE)
        self.assertPasses(self.bash("git commit -m 'Source: offsite, moved out of Private/ as Alex asked'"))

    def test_a_move_out_of_private_with_a_code_name_in_it_is_refused_anyway(self):
        self.git("mv", PRIVATE, "Meetings/2026-10-12 CFO, the private part.md")
        self.assertBlocked(self.bash("git commit -m 'Meeting: CFO, out of Private/ as Alex asked'"),
                           "a confidential term outside Private/")

    def test_a_move_not_yet_staged_is_seen_too(self):
        self.private_note()
        (self.root / OFFSITE).rename(self.root / "Sources" / "2026-10-20 Offsite.md")
        self.assertBlocked(self.bash("git add -A && git commit -m 'Meeting: CFO'"), "out of Private/")
        self.git("status")  # the real index was not touched
        staged = subprocess.run(["git", "-C", str(self.root), "diff", "--cached", "--name-only"], capture_output=True,
                                text=True, env=self.env).stdout
        self.assertEqual(staged, "")

    # what never blocks

    def test_a_slow_check_blocks_nothing(self):
        (self.root / "tools" / "vault.py").write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
        code, out, _ = self.bash("git push", env={"VAULT_HOOK_TIMEOUT": "1"})
        self.assertEqual(code, 0)
        self.assertIn("did not finish within 1 seconds", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_a_check_that_crashes_blocks_nothing(self):
        (self.root / "tools" / "vault.py").write_text("raise RuntimeError('broken on purpose')\n", encoding="utf-8")
        code, out, _ = self.bash("git push")
        self.assertEqual(code, 0)
        self.assertIn("broken on purpose", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_a_missing_script_blocks_nothing(self):
        (self.root / ".claude" / "check_hook.py").unlink()
        self.break_vault()
        self.assertEqual(self.bash("git push"), (0, "", ""))
        self.assertEqual(self.stop()[0], 0)

    def test_input_that_is_not_hook_json_blocks_nothing(self):
        r = subprocess.run(["sh", "-c", command("PreToolUse")], input="not json", capture_output=True, text=True,
                           env=self.env)
        self.assertEqual(r.returncode, 0)

    # the end of a turn

    def test_stop_sends_claude_back_once_while_the_check_fails(self):
        self.assertEqual(self.stop(), (0, "", ""))  # nothing to push
        self.break_vault()
        code, out, _ = self.stop()
        self.assertEqual(code, 0)
        self.assertIn("D5 has no source", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        code, out, _ = self.stop(active=True)
        self.assertEqual(code, 0)
        self.assertRegex(json.loads(out)["systemMessage"], r"still fails \(\d+ to fix\)")


if __name__ == "__main__":
    unittest.main()
