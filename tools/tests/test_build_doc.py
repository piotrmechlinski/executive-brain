"""Tests for build_doc.py, the Word file and the PDF of a note, and for the project map's PDF. Needs python-docx.

    python3 -m unittest discover -s tools/tests -v

The PDF tests need Node and Playwright with its Chromium, as a Claude Code cloud session has them, and pypdf; without
them they are skipped.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = next(p / "tools" for p in Path(__file__).resolve().parents if (p / "tools" / "vault.py").exists())
EXAMPLE = TOOLS.parent / "examples" / "Brightwater"
CARD = EXAMPLE / "Projects" / "P1 Warehouse automation.md"
NO_TABLE = EXAMPLE / "Meetings" / "2026-10-19 Weekly review.md"


def can_print():
    if not (shutil.which("node") and importlib.util.find_spec("pypdf")):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], cwd=TOOLS, capture_output=True).returncode == 0


@unittest.skipUnless(importlib.util.find_spec("docx") and CARD.exists(), "needs python-docx and the example")
class WithoutNode(unittest.TestCase):
    def build(self, note):
        """build_doc.py on a PATH with Python and nothing else."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        bin_ = Path(tmp.name) / "bin"
        bin_.mkdir()
        os.symlink(sys.executable, bin_ / "python3")
        out = Path(tmp.name) / "out" / note.stem
        r = subprocess.run([str(bin_ / "python3"), str(TOOLS / "build_doc.py"), str(note), str(out)],
                           env={"PATH": str(bin_), "HOME": tmp.name, "VAULT_TODAY": "2026-10-22"},
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        return out.with_suffix(".docx"), r.stdout

    def test_the_word_file_is_built_with_a_warning(self):
        docx, said = self.build(CARD)
        self.assertTrue(docx.exists())
        self.assertIn("diagrams not drawn ([Errno 2]", said)
        self.assertIn("the PDF is not built", said)

    def test_the_word_file_has_the_title_no_author_and_today(self):
        import docx
        props = docx.Document(str(self.build(NO_TABLE)[0])).core_properties
        self.assertEqual(props.title, "2026-10-19 Weekly review")
        self.assertEqual((props.author, props.last_modified_by, props.comments), ("", "", ""))
        self.assertEqual(props.created.date().isoformat(), "2026-10-22")


@unittest.skipUnless(importlib.util.find_spec("docx") and CARD.exists() and can_print(),
                     "needs python-docx, Node, Playwright and pypdf")
class Printed(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def text(self, pdf):
        import pypdf
        return "\n".join(page.extract_text() for page in pypdf.PdfReader(str(pdf)).pages)

    def test_a_note_without_a_table_keeps_its_footer(self):
        out = self.tmp / "review"
        subprocess.run([sys.executable, str(TOOLS / "build_doc.py"), str(NO_TABLE), str(out), "--footer",
                        "Brightwater · internal"], check=True, capture_output=True, timeout=300)
        self.assertIn("Brightwater · internal", self.text(out.with_suffix(".pdf")))

    def test_the_map_comes_as_a_pdf_too(self):
        vault = self.tmp / "vault"
        shutil.copytree(EXAMPLE, vault, ignore=shutil.ignore_patterns("build"))
        r = subprocess.run([sys.executable, str(TOOLS / "build_map.py"), "--vault", str(vault)], capture_output=True,
                           text=True, timeout=300, env=dict(os.environ, VAULT_TODAY="2026-10-22"))
        self.assertIn("Built build/Project map.html and build/Project map.pdf", r.stdout)
        text = self.text(vault / "build" / "Project map.pdf")
        for expected in ("P1", "Warehouse automation", "Customer service reset", "Brightwater Logistics · internal"):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
