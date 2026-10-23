"""Tests for sessions that share one vault on GitHub: the session start, IDs and conflicts. Standard library and git.

    python3 -m unittest discover -s tools/tests -v

Each test makes a scratch "GitHub" (a bare repository) holding the example vault on main, and clones it the way a
cloud session does.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = next(p / "tools" for p in Path(__file__).resolve().parents if (p / "tools" / "vault.py").exists())
REPO = TOOLS.parent
EXAMPLE = REPO / "examples" / "Brightwater"
sys.path.insert(0, str(TOOLS))
import vault  # noqa: E402

ROW = "| %s | Extend the night shift through the peak | P1 | Priya Shah | 2026-11-15 | open | | 2026-10-22 | %s |"
RISK = ("| R3 | The peak season starts before the pilot ends | P1 | medium | Hold the pilot until January | Priya Shah | "
        "open | 2026-10-22 | %s |")


@unittest.skipUnless(shutil.which("git") and shutil.which("bash") and EXAMPLE.is_dir(),
                     "needs git, bash and the example vault")
class Sessions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE_"))}
        self.env.update(HOME=str(self.tmp), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com", VAULT_TODAY="2026-10-22")
        seed = self.tmp / "seed"
        shutil.copytree(EXAMPLE, seed)
        (seed / "tools").mkdir()
        shutil.copy(TOOLS / "vault.py", seed / "tools" / "vault.py")
        (seed / ".claude").mkdir()
        shutil.copy(REPO / ".claude" / "start.sh", seed / ".claude" / "start.sh")
        (seed / "requirements.txt").write_text("", encoding="utf-8")  # nothing to install in a test
        (seed / ".gitignore").write_text("build/\n", encoding="utf-8")
        self.git(seed, "init", "-q", "-b", "main")
        self.git(seed, "add", "-A")
        self.git(seed, "commit", "-q", "-m", "The vault")
        self.append(seed, "README.md", "\nA second commit, so that a clone of depth 1 is shallow.")
        self.git(seed, "commit", "-q", "-am", "A blank line")
        self.origin = self.tmp / "origin.git"
        self.git(self.tmp, "clone", "-q", "--bare", str(seed), str(self.origin))

    def git(self, cwd, *args, check=True):
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=self.env)
        if check and r.returncode:
            self.fail("git %s: %s" % (" ".join(args), r.stderr))
        return r.stdout.strip()

    def clone(self, name, *args):
        path = self.tmp / name
        self.git(self.tmp, "clone", "-q", *args, "file://" + str(self.origin), str(path))
        return path

    def append(self, root, rel, line):
        with open(root / rel, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def tool(self, root, *args):
        r = subprocess.run([sys.executable, str(root / "tools" / "vault.py"), *args], cwd=root, capture_output=True,
                           text=True, env=self.env)
        return r.returncode, r.stdout.strip()

    def start(self, root, remote=True):
        env = dict(self.env, CLAUDE_CODE_REMOTE="true") if remote else self.env
        r = subprocess.run(["bash", str(root / ".claude" / "start.sh")], cwd=self.tmp, capture_output=True, text=True,
                           env=env, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def file_meeting(self, root, did):
        """What a session does to file a decision: the row, a refresh, a commit."""
        self.append(root, "Knowledge/Decisions.md", ROW % (did, "[[2026-10-19 Warehouse vendors]]"))
        self.assertEqual(self.tool(root, "refresh")[0], 0)
        self.git(root, "commit", "-q", "-am", "Decision %s" % did)

    # the session start

    def test_the_hook_runs_at_every_start(self):
        hooks = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        self.assertTrue(all("matcher" not in h for h in hooks), "a matcher leaves out /clear, compactions or forks")

    def test_a_cloud_session_starts_on_an_up_to_date_main(self):
        work = self.clone("work", "--depth", "1")
        self.git(work, "checkout", "-q", "-b", "claude/session-1")
        self.assertEqual(self.git(work, "rev-parse", "--is-shallow-repository"), "true")
        other = self.clone("other")
        self.file_meeting(other, "D5")
        self.git(other, "push", "-q", "origin", "main")

        out = self.start(work)
        self.assertEqual(self.git(work, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(self.git(work, "rev-parse", "HEAD"), self.git(self.origin, "rev-parse", "main"))
        self.assertEqual(self.git(work, "rev-parse", "--is-shallow-repository"), "false")
        self.assertIn("Vault status, 2026-10-22", out)
        self.assertIn("| D5 |", (work / "Knowledge" / "Decisions.md").read_text(encoding="utf-8"))

    def test_a_session_branch_with_work_of_its_own_stays(self):
        work = self.clone("work")
        self.git(work, "checkout", "-q", "-b", "claude/session-2")
        self.file_meeting(work, "D5")
        out = self.start(work)
        self.assertEqual(self.git(work, "rev-parse", "--abbrev-ref", "HEAD"), "claude/session-2")
        self.assertIn("holds work not yet on main", out)
        self.assertIn("Vault status", out)

    def test_uncommitted_work_stays_where_it_is(self):
        work = self.clone("work")
        self.git(work, "checkout", "-q", "-b", "claude/session-3")
        self.append(work, "Knowledge/Decisions.md", ROW % ("D5", "[[2026-10-19 Warehouse vendors]]"))
        out = self.start(work)
        self.assertEqual(self.git(work, "rev-parse", "--abbrev-ref", "HEAD"), "claude/session-3")
        self.assertIn("holds work not yet on main", out)
        self.assertIn("| D5 |", (work / "Knowledge" / "Decisions.md").read_text(encoding="utf-8"))

    def test_a_failing_status_says_so_in_one_line(self):
        work = self.clone("work")
        (work / "tools" / "vault.py").write_text("raise SystemExit('broken on purpose')\n", encoding="utf-8")
        out = self.start(work, remote=False)
        self.assertEqual(out.strip().splitlines(), [
            "Vault status: not available (broken on purpose). Run python3 tools/vault.py status to see why."])

    def test_the_start_sets_the_executives_time_zone(self):
        work = self.clone("work")
        settings = work / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        envfile = self.tmp / "env"
        for zone, expected in (("Europe/Warsaw", "export TZ=Europe/Warsaw\n"), ("Mars/Base", "")):
            settings.write_text(json.dumps(dict(data, timezone=zone)), encoding="utf-8")
            envfile.write_text("", encoding="utf-8")
            env = dict(self.env, CLAUDE_ENV_FILE=str(envfile))
            r = subprocess.run(["bash", str(work / ".claude" / "start.sh")], cwd=self.tmp, capture_output=True, text=True,
                               env=env, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(envfile.read_text(encoding="utf-8"), expected, zone)

    # two sessions at once

    def test_next_reads_main_on_github(self):
        a, b = self.clone("a"), self.clone("b")
        self.assertEqual(self.tool(a, "next", "D")[1], "D5")
        self.file_meeting(a, "D5")
        self.git(a, "push", "-q", "origin", "main")
        self.assertEqual(self.tool(b, "next", "D")[1], "D6")  # b has not pulled; next fetches main and sees D5
        self.assertEqual(self.tool(b, "next", "P")[1], "P4")

    def test_a_conflict_in_a_generated_part_is_cleared_by_refresh(self):
        a, b = self.clone("a"), self.clone("b")
        self.file_meeting(a, "D5")
        self.git(a, "push", "-q", "origin", "main")
        self.append(b, "Knowledge/Risks.md", RISK % "[[2026-10-19 Warehouse vendors]]")
        self.assertEqual(self.tool(b, "refresh")[0], 0)
        self.git(b, "commit", "-q", "-am", "Risk R3")

        self.git(b, "pull", "-q", "--rebase", "origin", "main", check=False)
        found = vault.conflicts(vault.Vault(b))
        self.assertTrue(found, "the two sessions did not conflict; the test no longer shows anything")
        self.assertTrue(all(inside for _, _, inside in found), "a conflict outside a generated part: %s" % found)
        self.assertEqual(self.tool(b, "refresh")[0], 0)
        self.assertEqual(self.tool(b, "check")[0], 0)
        self.git(b, "add", "-A")
        self.git(b, "-c", "core.editor=true", "rebase", "--continue")
        self.git(b, "push", "-q", "origin", "main")
        main = self.clone("main")
        self.assertIn("| D5 |", (main / "Knowledge" / "Decisions.md").read_text(encoding="utf-8"))
        self.assertIn("| R3 |", (main / "Knowledge" / "Risks.md").read_text(encoding="utf-8"))
        self.assertEqual(self.tool(main, "check")[0], 0)


if __name__ == "__main__":
    unittest.main()
