"""Tests for the vault's check and the project map. Standard library only.

    python3 -m unittest discover -s tools/tests -v

Each test copies the example vault to a temporary folder, breaks one rule and asserts that the check names it.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = next(p / "tools" for p in Path(__file__).resolve().parents if (p / "tools" / "vault.py").exists())
EXAMPLE = TOOLS.parent / "examples" / "Brightwater"
sys.path.insert(0, str(TOOLS))
import vault  # noqa: E402
import build_map  # noqa: E402

CFO = "Meetings/2026-10-12 Weekly with the CFO.md"
CFO_LINK = "[2026-10-12 Weekly with the CFO](<../Meetings/2026-10-12 Weekly with the CFO.md>)"
VENDORS = "Meetings/2026-10-19 Warehouse vendors.md"


@unittest.skipUnless(EXAMPLE.is_dir(), "no example vault in this copy")
class ExampleVault(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "vault"
        shutil.copytree(EXAMPLE, self.root)
        env = mock.patch.dict(os.environ, {"VAULT_TODAY": "2026-10-22"})
        env.start()
        self.addCleanup(env.stop)

    def edit(self, rel, old, new):
        p = self.root / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text, "the example has changed: %s" % rel)
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    def append(self, rel, line):
        with open(self.root / rel, "a", encoding="utf-8") as f:
            f.write("\n" + line + "\n")

    def errors(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return vault.check(vault.Vault(self.root))[0]

    def assertError(self, fragment):
        errors = self.errors()
        self.assertTrue(any(fragment in e for e in errors), "no error with %r in:\n  %s" % (fragment, "\n  ".join(errors)))

    # the example itself

    def test_example_passes(self):
        self.assertEqual(self.errors(), [])

    # the registers

    def test_row_without_a_source(self):
        self.edit("Knowledge/Decisions.md", "| 2026-10-12 | %s |" % CFO_LINK, "| 2026-10-12 | - |")
        self.assertError("D2 has no source")

    def source(self, cell):
        """D2 with this Source; the check's errors and warnings."""
        self.edit("Knowledge/Decisions.md", "| 2026-10-12 | %s |" % CFO_LINK, "| 2026-10-12 | %s |" % cell)
        with contextlib.redirect_stdout(io.StringIO()):
            return vault.check(vault.Vault(self.root))

    def test_a_source_opens_on_github_in_either_form(self):
        for cell in (CFO_LINK, "[CFO](../Meetings/2026-10-12%20Weekly%20with%20the%20CFO.md)",
                     CFO_LINK + " and [the minutes](https://example.com/minutes)"):
            self.setUp()
            errors, warnings = self.source(cell)
            self.assertEqual(errors, [], cell)
            self.assertFalse(any("wikilinks" in w for w in warnings), cell)

    def test_a_source_that_cannot_be_clicked_or_does_not_count(self):
        cases = [("[CFO](../Meetings/2026-10-12 Weekly with the CFO.md)", "D2 has a link with a space in its path"),
                 ("[the meetings](<../Meetings>)", "D2 has a folder as its source"),
                 ("[elsewhere](<../../outside.md>)", "D2 has a source outside the vault"),
                 ("[the minutes](https://example.com/minutes)", "D2 has only a web address as its source"),
                 ("[CFO](<../Private/2026-10-12 From the CFO.md>)", "D2 has a Private/ note as its source"),
                 ("[[2026-10-12 From the CFO]]", "D2 has a Private/ note as its source")]
        (self.root.parent / "outside.md").write_text("# Outside the vault\n", encoding="utf-8")
        for cell, error in cases:
            self.setUp()
            (self.root.parent / "outside.md").write_text("# Outside the vault\n", encoding="utf-8")
            errors = self.source(cell)[0]
            self.assertTrue(any(error in e for e in errors), "%s: no %r in %s" % (cell, error, errors))

    def test_an_old_wikilink_passes_with_a_warning(self):
        errors, warnings = self.source("[[2026-10-12 Weekly with the CFO]]")
        self.assertEqual(errors, [])
        self.assertIn("Knowledge/Decisions.md: 1 sources are [[wikilinks]], which GitHub does not open", "\n".join(warnings))

    def test_nothing_outside_private_links_into_it(self):
        self.append(CFO, "See [the rest](<../Private/2026-10-12 From the CFO.md>).")
        self.assertError("leads into Private/")

    def test_link_prints_the_link_to_write(self):
        def link(name, origin):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                vault.cmd_link(vault.Vault(self.root), name, origin)
            return out.getvalue().strip()
        self.assertEqual(link("2026-10-12 Weekly with the CFO", "Knowledge/Decisions.md"), CFO_LINK)
        self.assertEqual(link("2026-10-01 Operations strategy memo.docx", "Knowledge/Current State.md"),
                         "[2026-10-01 Operations strategy memo.docx](<../Sources/2026-10-01 Operations strategy memo.docx>)")
        with self.assertRaises(SystemExit):
            link("2026-10-12 From the CFO", "Knowledge/Decisions.md")  # a Private/ note, linked from outside it

    def test_open_row_without_an_owner(self):
        self.edit("Knowledge/Decisions.md", "| P1 | Tom Becker | 2026-11-30 | open |", "| P1 |  | 2026-11-30 | open |")
        self.assertError("D2 is open without an owner")

    def test_unknown_project_in_a_row(self):
        self.edit("Knowledge/Decisions.md", "or wait a year | P1 |", "or wait a year | P9 |")
        self.assertError(": unknown project P9")

    def test_duplicate_id(self):
        self.edit("Knowledge/Decisions.md", "| D4 |", "| D1 |")
        self.assertError("D1 is already used at Knowledge/Decisions.md:")

    def test_register_errors_name_the_line_of_the_file(self):
        self.edit("Knowledge/Decisions.md", "or wait a year | P1 |", "or wait a year | P9 |")
        self.assertError("Knowledge/Decisions.md:11: unknown project P9")  # D1 is on line 11

    # the meetings

    def test_unknown_project_in_a_meeting(self):
        self.edit(VENDORS, "projects: [P1]", "projects: [P9]")
        self.assertError(VENDORS + ": unknown project P9")

    def test_recording_without_consent(self):
        self.edit(VENDORS, "consent: yes", "consent: no")
        self.assertError(VENDORS + ": a recording without consent: yes")

    # what is confidential

    def test_confidential_term_outside_private(self):
        self.append(CFO, "PROJECT kestrel came up again.")  # the example's term, in any case
        self.assertError(CFO + ":")
        self.assertError("a confidential term outside Private/")

    def test_new_private_term(self):
        with contextlib.redirect_stdout(io.StringIO()):
            vault.cmd_private_term(vault.Vault(self.root), "Harbour Lane")
        self.assertNotIn("Harbour Lane", (self.root / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(self.errors(), [])
        self.append(CFO, "The harbour lane site was mentioned.")
        self.assertError("a confidential term outside Private/")

    def test_private_line_outside_private(self):
        line = "The regional manager plans to move the night shift to the north site."
        (self.root / "Private" / "2026-10-20 Night shift.md").write_text("- %s\n" % line, encoding="utf-8")
        self.assertEqual(self.errors(), [])
        self.append(CFO, line)
        self.assertError("holds a line of Private/2026-10-20 Night shift.md")

    def test_a_term_is_found_however_it_is_written(self):
        note = (self.root / CFO).read_text(encoding="utf-8")
        for written in ("Project Késtrel", "PROJECT\n  kestrel", "Project\n| Kestrel |", "Project **Kes**trel",
                        "Project Kes­trel", "Project Kes​trel", "Project Kеstrel", "ＰＲＯＪＥＣＴ Kestrel",
                        "Project_Kestrel", "Project Kestr&#101;l", "Project Kes<span></span>trel",
                        '"Project<br>Kestrel"'):
            with self.subTest(written=written):
                (self.root / CFO).write_text(note + "\n- %s came up.\n" % written, encoding="utf-8")
                self.assertError(CFO + ":")
        (self.root / CFO).write_text(note + "\n- Project Kestrels and the kestrel project came up.\n", encoding="utf-8")
        self.assertEqual(self.errors(), [])  # a plural, or the words in another order, is not the term

    def test_a_term_kept_before_folding_still_matches(self):
        old = __import__("hashlib").sha256("brücke".encode("utf-8")).hexdigest()[:16]  # as 1.0.0's drafts kept it
        settings = json.loads((self.root / "settings.json").read_text(encoding="utf-8"))
        settings["private_terms"].append({"n": 1, "h": old})
        (self.root / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        self.append(CFO, "- BRÜCKE came up.")
        self.assertError(CFO + ":")

    def test_a_new_term_is_kept_without_its_accents_and_its_umlauts(self):
        with contextlib.redirect_stdout(io.StringIO()):
            vault.cmd_private_term(vault.Vault(self.root), "Brücke")
        note = (self.root / CFO).read_text(encoding="utf-8")
        for written in ("Brücke", "BRUCKE", "Bruecke", "Brücke"):
            with self.subTest(written=written):
                (self.root / CFO).write_text(note + "\n- %s came up.\n" % written, encoding="utf-8")
                self.assertError(CFO + ":")

    def test_a_private_line_is_found_rewrapped_or_restyled(self):
        line = "The regional manager plans to move the night shift to the north site."
        (self.root / "Private" / "2026-10-20 Night shift.txt").write_text(line + "\n", encoding="utf-8")
        note = (self.root / CFO).read_text(encoding="utf-8")
        for written in (line.lower(), line.replace(" to the north", "\n  to the north"),
                        line.replace("night shift", "**night shift**"), line.replace(" ", "  ")):
            with self.subTest(written=written):
                (self.root / CFO).write_text(note + "\n- %s\n" % written, encoding="utf-8")
                self.assertError("holds a line of Private/2026-10-20 Night shift.txt")

    def test_outputs_in_other_formats_are_read(self):
        (self.root / "Outputs").mkdir(exist_ok=True)
        for name, content in (("2026-10-21 Map.svg", "<svg><text>Project</text><text>Kestrel</text></svg>\n"),
                              ("2026-10-21 Draft.eml", "Subject: Project Kestrel\n\nHello\n"),
                              ("2026-10-21 Note.rtf", "{\\rtf1 Project Kestrel}\n")):
            with self.subTest(name=name):
                (self.root / "Outputs" / name).write_text(content, encoding="utf-8")
                self.assertError("Outputs/%s" % name)

    def test_hidden_folders_names_claude_md_and_the_title_are_checked(self):
        for rel, text in ((".github/notes.md", "Project Kestrel"), ("Meetings/.drafts/x.md", "Project Kestrel"),
                          (".notes.md", "Project Kestrel"), ("Outputs/build/2026-10-21 Brief.md", "Project Kestrel"),
                          ("Knowledge/tools/x.md", "Project Kestrel"),
                          ("Outputs/2026-10-21 Project Kestrel.txt", "Clean.")):
            with self.subTest(rel=rel):
                (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.root / rel).write_text(text + "\n", encoding="utf-8")
                self.assertError(rel + (":1" if text != "Clean." else " (its name)"))
                (self.root / rel).unlink()
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "x.yml").write_text("on: push\n", encoding="utf-8")
        self.assertEqual(self.errors(), [])  # a hidden folder holds no notes: only confidential words count there
        (self.root / "CLAUDE.md").write_text("# CLAUDE.md\n\n## About me\n\n- **What I am working on:** Project "
                                             "Kestrel.\n", encoding="utf-8")
        self.assertError("CLAUDE.md:5: a confidential term outside Private/")
        (self.root / "CLAUDE.md").unlink()
        self.edit("settings.json", "Brightwater Logistics · internal", "Project Kestrel · internal")
        self.assertError('settings.json, "footer": a confidential term outside Private/')

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_a_hidden_file_that_git_ignores_is_not_read(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text(".claude/settings.local.json\n", encoding="utf-8")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.local.json").write_text('{"allow": ["Bash(echo Project Kestrel)"]}\n',
                                                                   encoding="utf-8")
        self.assertEqual(self.errors(), [])  # it never reaches GitHub
        (self.root / ".claude" / "settings.json").write_text('{"allow": ["Bash(echo Project Kestrel)"]}\n',
                                                             encoding="utf-8")
        self.assertError(".claude/settings.json:1: a confidential term outside Private/")

    # the top level

    def test_unknown_folder_unless_declared(self):
        (self.root / "Drafts").mkdir()
        (self.root / "Drafts" / "plan.md").write_text("# Plan\n", encoding="utf-8")
        self.assertError("Drafts/: a folder the vault does not know")
        settings = self.root / "settings.json"
        settings.write_text(settings.read_text(encoding="utf-8").replace('"stale_days"', '"folders": ["Drafts"], "stale_days"'),
                            encoding="utf-8")
        self.assertEqual(self.errors(), [])

    # the generated parts

    def test_generated_part_out_of_date_until_refresh(self):
        self.edit("Projects/P1 Warehouse automation.md", "Priya Shah sends the vendor shortlist", "Priya Shah sends the final shortlist")
        self.assertError("Home.md: the generated part is out of date")
        with contextlib.redirect_stdout(io.StringIO()):
            vault.cmd_refresh(vault.Vault(self.root))
        self.assertEqual(self.errors(), [])
        self.assertIn("sends the final shortlist", (self.root / "Home.md").read_text(encoding="utf-8"))

    # the command line and the map

    def test_check_exit_codes_and_a_file_at_the_top_level(self):
        def run():
            return subprocess.run([sys.executable, str(TOOLS / "vault.py"), "check", "--vault", str(self.root)],
                                  capture_output=True, text=True, timeout=60)
        ok = run()
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("The vault is in order", ok.stdout)
        (self.root / "notes.txt").write_text("a stray note\n", encoding="utf-8")
        bad = run()
        self.assertEqual(bad.returncode, 1)
        self.assertIn("To fix before the push", bad.stdout)
        self.assertIn("notes.txt: a file at the top level", bad.stdout)

    def test_project_map_builds(self):
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(build_map, "pdf", return_value=False):
            out = build_map.build(vault.Vault(self.root), [], False)
        page = out.read_text(encoding="utf-8")
        self.assertEqual(out, self.root / "build" / "Project map.html")
        self.assertIn("P1 Warehouse automation", page)
        self.assertIn("P2 Customer service reset", page)
        self.assertNotIn("Route planning pilot", page)  # archived, so only with --all
        self.assertIn("<pre class='mermaid'>gantt", page)
        self.assertNotIn("Kestrel", page)

    def test_a_map_to_send_has_no_links_and_no_commit(self):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        for args in (["init", "-q", "-b", "main"], ["remote", "add", "origin", "https://github.com/someone/vault.git"],
                     ["add", "-A"], ["-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", "v"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, env=env)
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(build_map, "pdf", return_value=False):
            own = build_map.build(vault.Vault(self.root), [], False).read_text(encoding="utf-8")
            sent = build_map.build(vault.Vault(self.root), ["P1"], False, send=True).read_text(encoding="utf-8")
        self.assertIn("https://github.com/someone/vault/blob/main/", own)
        self.assertIn(" · commit ", own)
        self.assertNotIn("github.com/someone", sent)
        self.assertNotIn(" · commit ", sent)
        self.assertIn("P1 Warehouse automation", sent)
        self.assertNotIn("P2 Customer service reset", sent)

    def test_a_crafted_id_or_colour_stays_out_of_the_page(self):
        card = next((self.root / "Archive" / "Projects").glob("P3 *.md"))
        text = card.read_text(encoding="utf-8")
        card.write_text(text.replace("id: P3", "id: P3' onmouseover='alert(1)"), encoding="utf-8")
        self.edit("settings.json", '"accent": "#0B5FAD"', '"accent": "red;}</style><script>alert(2)</script>"')
        said = io.StringIO()
        with contextlib.redirect_stdout(said), mock.patch.object(build_map, "pdf", return_value=False):
            page = build_map.build(vault.Vault(self.root), [], True).read_text(encoding="utf-8")
        self.assertNotIn("onmouseover='alert(1)'", page)
        self.assertIn("<section id='P3&#x27; onmouseover=&#x27;alert(1)'>", page)
        self.assertNotIn("alert(2)", page)
        self.assertIn("--accent: %s;" % build_map.THEME["accent"], page)
        self.assertIn("not #RRGGBB, left at their defaults: accent", said.getvalue())

    def test_without_node_the_page_is_built_and_no_older_pdf_stays(self):
        old = self.root / "build" / "Project map.pdf"
        old.parent.mkdir(exist_ok=True)
        old.write_bytes(b"%PDF-1.4 an older map")
        said = io.StringIO()
        missing = FileNotFoundError(2, "No such file or directory", "node")
        with contextlib.redirect_stdout(said), mock.patch.object(build_map.subprocess, "run", side_effect=missing):
            page = build_map.build(vault.Vault(self.root), [], False)
        self.assertTrue(page.exists())
        self.assertFalse(old.exists())
        self.assertIn("the PDF is not built", said.getvalue())


    # what the check must never let pass in silence

    def conflict_around(self, rel, row_start):
        """Wraps one row in git conflict markers, as a failed merge would; returns the marker's line."""
        p = self.root / rel
        lines = p.read_text(encoding="utf-8").split("\n")
        i = next(n for n, line in enumerate(lines) if line.startswith(row_start))
        lines[i:i + 1] = ["<<<<<<< HEAD", lines[i], "=======", lines[i].replace("open", "decided"), ">>>>>>> origin/main"]
        p.write_text("\n".join(lines), encoding="utf-8")
        return i + 1

    def test_conflict_markers_are_an_error_at_their_line(self):
        line = self.conflict_around("Knowledge/Decisions.md", "| D1 ")
        self.assertError("Knowledge/Decisions.md:%d: an unresolved git conflict; keep the right lines" % line)
        self.assertError("a table row outside its table")

    def test_refresh_refuses_a_conflict_and_drops_no_rows(self):
        home = (self.root / "Home.md").read_text(encoding="utf-8")
        self.conflict_around("Knowledge/Decisions.md", "| D1 ")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            vault.cmd_refresh(vault.Vault(self.root))
        self.assertEqual((self.root / "Home.md").read_text(encoding="utf-8"), home)

    def test_a_conflict_in_a_generated_part_is_cleared_by_refresh(self):
        home = self.root / "Home.md"
        text = home.read_text(encoding="utf-8")
        line = text[:text.index("<!-- generated -->")].count("\n") + 2
        home.write_text(text.replace("<!-- generated -->\n", "<!-- generated -->\n<<<<<<< HEAD\nold\n=======\nnew\n"
                                     ">>>>>>> origin/main\n", 1), encoding="utf-8")
        self.assertError("Home.md:%d: an unresolved git conflict in the generated part; run" % line)
        with contextlib.redirect_stdout(io.StringIO()):
            vault.cmd_refresh(vault.Vault(self.root))
        self.assertEqual(self.errors(), [])

    def test_a_table_that_resumes_after_a_stray_line(self):
        self.edit("Knowledge/Decisions.md", "\n| D3 |", "\nA note in the middle of the table.\n| D3 |")
        self.assertError("Knowledge/Decisions.md:14: a table row outside its table")  # D3 moved from line 13 to 14

    def test_an_unknown_status_is_an_error(self):
        p = self.root / "Knowledge" / "Milestones.md"
        p.write_text("\n".join(line.replace("| open |", "| completed |") if line.startswith("| M4 ") else line
                               for line in p.read_text(encoding="utf-8").split("\n")), encoding="utf-8")
        self.assertError("M4 has the Status 'completed'")
        p.write_text(p.read_text(encoding="utf-8").replace("| completed |", "|  |"), encoding="utf-8")
        self.assertError("M4 has no Status")

    def test_a_damaged_cache_is_ignored(self):
        self.assertEqual(self.errors(), [])
        cache = self.root / "build" / vault.CACHE
        for damaged in ("not json", '{"key": 1, "files": []}', '{"files": {"Home.md": {"sha": 1}}}'):
            cache.write_text(damaged, encoding="utf-8")
            self.assertEqual(self.errors(), [])

    def test_a_list_where_one_value_belongs_is_an_error_not_a_crash(self):
        self.edit(VENDORS, "source: recording", "source: [recording]")
        self.edit("Projects/P1 Warehouse automation.md", "id: P1", "id: [P1]")
        self.assertError(VENDORS + ": source takes one value, not a list")
        self.assertError("Projects/P1 Warehouse automation.md: id takes one value, not a list")

    def test_a_fact_without_its_source_names_its_line(self):
        rel = "Knowledge/Current State.md"
        p = self.root / rel
        lines = p.read_text(encoding="utf-8").split("\n")
        i = next(n for n, line in enumerate(lines) if line.startswith("- Customer service"))
        lines.insert(i + 1, "- The night shift has twelve pickers.")
        p.write_text("\n".join(lines), encoding="utf-8")
        self.assertError("%s:%d: a fact without its date and source" % (rel, i + 2))

    def test_settings_that_are_not_json_are_an_error_not_a_crash(self):
        (self.root / "settings.json").write_text("{ not json", encoding="utf-8")
        self.assertError("settings.json: not valid JSON")

    def test_an_html_output_is_read_without_its_scripts_and_keeps_its_lines(self):
        (self.root / "Outputs").mkdir(exist_ok=True)
        page = "<html><head><script>\n" + "draw();\n" * 50 + "</script></head><body>\n<p>About Project Kestrel</p>\n</body></html>\n"
        (self.root / "Outputs" / "2026-10-21 Map.html").write_text(page, encoding="utf-8")
        self.assertError("Outputs/2026-10-21 Map.html:53: a confidential term outside Private/")

    def test_the_check_reads_again_what_changed(self):
        self.assertEqual(self.errors(), [])
        self.assertTrue((self.root / "build" / vault.CACHE).exists())
        self.append(CFO, "The harbour lane site was mentioned.")
        self.assertEqual(self.errors(), [])  # not a confidential word yet
        with contextlib.redirect_stdout(io.StringIO()):
            vault.cmd_private_term(vault.Vault(self.root), "Harbour Lane")
        self.assertError(CFO + ":")  # the file did not change, but the words to look for did
        self.append("Meetings/2026-10-05 Setup.md", "Project Kestrel, again.")
        self.assertError("Meetings/2026-10-05 Setup.md:")  # a changed file is read again

    # actions and the weekly review

    def add_row(self, rel, row):
        with open(self.root / rel, "a", encoding="utf-8") as f:
            f.write(row + "\n")

    def review(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            vault.cmd_review(vault.Vault(self.root))
        return out.getvalue()

    def test_an_action_without_a_date_is_listed_by_its_owner(self):
        self.assertIn("## Open actions, by owner (1)\n- Maria Lopez: T2 Plan the two weeks with both ticket systems",
                      self.review())

    def test_an_open_action_needs_an_owner(self):
        self.edit("Knowledge/Actions.md", "| P2 | Maria Lopez | | open |", "| P2 | | | open |")
        self.assertError("T2 is open without an owner")

    def test_the_review_says_what_changed_since_the_last_one(self):
        self.edit("Knowledge/Decisions.md", "| Tom Becker | | open | | 2026-10-12 |",
                  "| Tom Becker | | decided | Tom Becker builds it, with one sheet per project | 2026-10-21 |")
        self.add_row("Knowledge/Actions.md", "| T3 | Send the board paper to Tom | P1 | Priya Shah | | open | 2026-10-21 | "
                                             "[[2026-10-19 Warehouse vendors]] |")
        self.edit("Knowledge/Actions.md", "| Maria Lopez | | open | 2026-10-19 |", "| Maria Lopez | | done | 2026-10-20 |")
        since = self.review().split("## Overdue")[0]
        self.assertIn("## Since the last review, on 2026-10-19", since)
        self.assertIn("- Decided (1)\n  - D4 One cost model for both projects, and who builds it · P1, P2 · Tom Becker: "
                      "Tom Becker builds it, with one sheet per project", since)
        self.assertIn("- Closed (1)\n  - T2 Plan the two weeks", since)
        self.assertIn("- New or changed (1)\n  - T3 Send the board paper to Tom", since)
        self.assertNotIn("D3", since)  # decided at the last review itself

    def test_a_row_marked_unverified_is_listed_until_confirmed(self):
        self.assertIn("## Marked unverified, to confirm (1)\n- R2 Agent turnover", self.review())
        self.edit("Knowledge/Risks.md", " *(unverified)*", "")
        self.assertIn("## Marked unverified, to confirm (0)", self.review())

    def test_actions_stay_off_the_timeline(self):
        self.add_row("Knowledge/Actions.md", "| T3 | Send the board paper to Tom | P1 | Priya Shah | 2026-11-02 | open | "
                                             "2026-10-21 | [[2026-10-19 Warehouse vendors]] |")
        v = vault.Vault(self.root)
        timeline = build_map.gantt(v, [p[0] for p in v.projects.values()])
        self.assertIn("M1 Vendor shortlist", timeline)
        self.assertNotIn("T3", timeline)

    def test_the_time_zone_sets_today(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        os.environ.pop("VAULT_TODAY")  # restored by the mock in setUp
        for zone in ("Pacific/Kiritimati", "Etc/GMT+12"):  # 26 hours apart: one of them is not on UTC's date
            self.edit("settings.json", '"title"', '"timezone": "%s", "title"' % zone)
            vault.Vault(self.root)
            self.assertEqual(vault.today(), datetime.now(ZoneInfo(zone)).date(), zone)
            self.edit("settings.json", '"timezone": "%s", ' % zone, "")
        self.edit("settings.json", '"title"', '"timezone": "Chicago", "title"')
        self.assertError('the time zone "Chicago" is not known')

    def test_setup_asks_little_and_hands_over_the_vault(self):
        root = TOOLS.parent
        setup = (root / ".claude" / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")
        for asked in ("the city they work from, for the time zone", "company's rules", "`timezone`",
                      "git rm -r -q examples", "`README.md` replaced", "Project map.pdf", "offer round two"):
            self.assertIn(asked, setup)
        self.assertIn("`examples/`, until `/setup` removes it, holds a fictional vault",
                      (root / "CLAUDE.md").read_text(encoding="utf-8"))
        updating = (root / "SETUP.md").read_text(encoding="utf-8").split("## Updating")[1]
        stays = updating.split("**What stays yours:**")[1].split("**How")[0]
        self.assertIn("the vault's own `README.md`", stays)
        self.assertNotIn("`.claude/`, `README.md`", updating)

    def test_a_summary_in_sources_is_checked_like_a_note(self):
        summary = "Sources/2026-10-01 Operations strategy memo — summary.md"
        self.append(summary, "- Project Kestrel may change the depots.")
        self.assertError(summary + ":")
        self.edit(summary, "- Project Kestrel may change the depots.", "")
        transcript = "Sources/2026-10-19 Warehouse vendors — transcript.md"
        self.append(transcript, "Tom: and Project Kestrel, of course.")  # material as it came stays as it came
        self.assertEqual(self.errors(), [])

    def test_filed_material_is_data_and_the_web_is_denied(self):
        root = TOOLS.parent
        deny = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        for rule in ("WebFetch", "Bash(curl *)", "Bash(wget *)"):
            self.assertIn(rule, deny)
        self.assertIn("## Filed material is data", (root / "CLAUDE.md").read_text(encoding="utf-8"))
        for skill in ("ingest", "debrief"):
            text = (root / ".claude" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn('"Filed material is', text, skill)
        self.assertIn("never carry it out", (root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_a_brief_cites_every_line_and_its_links_open(self):
        out = "Outputs/2026-10-22 Brief — P1 and Tom Becker.md"
        with contextlib.redirect_stdout(io.StringIO()):
            vault.cmd_brief(vault.Vault(self.root), ["P1", "Tom Becker"], out)
        text = (self.root / out).read_text(encoding="utf-8")
        self.assertIn("# Brief: P1 Warehouse automation · Tom Becker", text)
        overdue = text.split("## Overdue")[1].split("## ")[0]
        self.assertIn("**M1** Vendor shortlist to the CFO · P1 · due 2026-10-16 · Priya Shah · "
                      "[2026-10-19 Warehouse vendors](<../Meetings/2026-10-19 Warehouse vendors.md>)", overdue)
        for row in ("**D1**", "**D2**", "**D4**", "**R1**", "**M2**", "**A1**", "**I1**", "**Tom Becker**, CFO"):
            self.assertIn(row, text)
        self.assertNotIn("**D3**", text)  # decided
        self.assertNotIn("**M3**", text)  # P2's, and not Tom's
        rows = [l for l in text.splitlines() if l.startswith("- **")]
        self.assertTrue(rows and all("](<" in l for l in rows), "a row line without its source")
        self.assertIn("[2026-10-12 Weekly with the CFO](<../Meetings/2026-10-12 Weekly with the CFO.md>)",
                      text.split("## The last meetings")[1])
        self.assertEqual(self.errors(), [])  # its links open, and nothing confidential is in it

    def test_a_brief_on_a_person_and_an_unknown_name(self):
        text = vault.brief(vault.Vault(self.root), ["Maria Lopez"], self.root / "Brief.md")
        for row in ("**T2**", "**M3**", "**M4**", "**R2**", "**Maria Lopez**, Head of Customer Service"):
            self.assertIn(row, text)
        self.assertIn("**R2**", text.split("## Marked unverified")[1])
        with self.assertRaises(SystemExit):
            vault.brief(vault.Vault(self.root), ["Somebody Else"], self.root / "Brief.md")

    def test_the_version_is_the_changelogs(self):
        import re
        changelog = (TOOLS.parent / "CHANGELOG.md").read_text(encoding="utf-8")
        first = re.search(r"^## (\d+\.\d+\.\d+)\b", changelog, re.M)
        self.assertIsNotNone(first, "no numbered heading in CHANGELOG.md")
        self.assertEqual(vault.VERSION, first.group(1))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            vault.cmd_status(vault.Vault(self.root))
        self.assertIn("(Executive Brain %s)" % vault.VERSION, out.getvalue().splitlines()[0])

    def test_the_issue_forms_keep_vault_content_out(self):
        forms = TOOLS.parent / ".github" / "ISSUE_TEMPLATE"
        if not forms.is_dir():
            self.skipTest("no issue forms in this copy")
        for form in sorted(forms.glob("*.yml")):
            text = form.read_text(encoding="utf-8")
            if form.name == "config.yml":
                self.assertIn("blank_issues_enabled: false", text)
                self.assertIn("https://github.com/piotrmechlinski/executive-brain/security/policy", text)
                continue
            self.assertIn("This is the public repository of the product, not your vault.", text, form.name)
            box = text.split("label: Nothing private")[1].split("- type:")[0]
            self.assertIn("required: true", box, form.name)
        for rules in ("CLAUDE.md", "AGENTS.md"):
            self.assertIn("invented data", (TOOLS.parent / rules).read_text(encoding="utf-8"), rules)

    def test_every_skill_that_files_points_to_what_goes_where(self):
        claude = (TOOLS.parent / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("## What goes where", claude)
        for skill in ("setup", "debrief", "ingest"):
            text = (TOOLS.parent / ".claude" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn('"What goes where"', text, skill)


if __name__ == "__main__":
    unittest.main()
