"""Tests for read_document.py's limits, with tiny crafted files. Standard library; pypdf where installed.

    python3 -m unittest discover -s tools/tests -v

Each crafted file is a few hundred bytes. Without the limits, some of them unpack to gigabytes or hang.
"""
import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

TOOLS = next(p / "tools" for p in Path(__file__).resolve().parents if (p / "tools" / "vault.py").exists())
sys.path.insert(0, str(TOOLS))
import read_document as R  # noqa: E402

NS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
      'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"')


def content(body, doctype=""):
    return ('<?xml version="1.0"?>%s<office:document-content %s><office:body><office:text>%s</office:text>'
            '</office:body></office:document-content>' % (doctype, NS, body))


class Limits(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def odt(self, xml, name="note.odt"):
        path = self.tmp / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            z.writestr("content.xml", xml)
        return path

    def test_a_plain_document_is_read(self):
        self.assertEqual(R.read(self.odt(content("<text:p>Hello</text:p><text:p>world</text:p>"))), "Hello\nworld")

    def test_an_archive_that_unpacks_too_far_is_refused(self):
        path = self.odt(content("<text:p>%s</text:p>" % ("x" * 5000)))
        self.assertLess(path.stat().st_size, 1000)  # it packs small: the size that counts is the unpacked one
        with mock.patch.object(R, "MAX_XML", 4000), self.assertRaisesRegex(R.DocumentError, "unpacks to"):
            R.read(path)

    def test_a_run_of_spaces_is_cut(self):
        text = R.read(self.odt(content('<text:p>a<text:s text:c="1000000000"/>b</text:p>')))
        self.assertEqual(text, "a" + " " * R.MAX_SPACES + "b")

    def test_deep_nesting_is_an_error_not_a_crash(self):
        deep = "<text:span>" * 5000 + "x" + "</text:span>" * 5000
        with self.assertRaisesRegex(R.DocumentError, "nested too deeply"):
            R.read(self.odt(content("<text:p>%s</text:p>" % deep)))

    def test_entities_are_refused(self):
        laughs = '<!DOCTYPE d [<!ENTITY a "haha"><!ENTITY b "&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;">]>'
        with self.assertRaisesRegex(R.DocumentError, "declares XML entities"):
            R.read(self.odt(content("<text:p>&c;</text:p>", laughs)))

    def test_a_file_that_is_not_an_archive_is_an_error(self):
        path = self.tmp / "fake.docx"
        path.write_bytes(b"not a zip at all")
        with self.assertRaisesRegex(R.DocumentError, "not a valid Office"):
            R.read(path)

    def test_the_command_says_why_and_exits_1(self):
        path = self.tmp / "fake.xlsx"
        path.write_bytes(b"not a zip at all")
        r = subprocess.run([sys.executable, str(TOOLS / "read_document.py"), str(path)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("fake.xlsx is not a valid Office or OpenDocument file", r.stderr)

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "needs pypdf to make the scan")
    def test_a_scan_is_named_as_one(self):
        from pypdf import PdfWriter
        w = PdfWriter()
        w.add_blank_page(width=200, height=200)  # a page with no text, as a scanner makes it
        with open(self.tmp / "scan.pdf", "wb") as f:
            w.write(f)
        with self.assertRaisesRegex(R.DocumentError, "no text layer: it is a scan or a picture. Read its pages"):
            R.read(self.tmp / "scan.pdf")

    @unittest.skipUnless(sys.platform != "win32", "a fake pdftotext needs a shell script")
    def test_a_pdftotext_that_hangs_gets_a_minute_here_one_second(self):
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        fake = bin_ / "pdftotext"
        fake.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        pdf = self.tmp / "blank.pdf"
        if importlib.util.find_spec("pypdf"):
            from pypdf import PdfWriter
            w = PdfWriter()
            w.add_blank_page(width=200, height=200)
            with open(pdf, "wb") as f:
                w.write(f)
        else:
            pdf.write_bytes(b"%PDF-1.4\n")
        start = time.monotonic()
        with mock.patch.dict(os.environ, {"PATH": str(bin_) + os.pathsep + os.environ["PATH"]}), \
                mock.patch.object(R, "PDF_TIMEOUT", 1):
            if importlib.util.find_spec("pypdf"):
                with self.assertRaisesRegex(R.DocumentError, "no text layer"):  # pypdf read it, and found no text
                    R.read(pdf)
            else:
                with self.assertRaisesRegex(R.DocumentError, "pdftotext failed or took over 1 seconds"):
                    R.read(pdf)
        self.assertLess(time.monotonic() - start, 10)


class Email(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def eml(self, msg):
        path = self.tmp / "mail.eml"
        path.write_bytes(bytes(msg))
        return R.read(path)

    def message(self):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = "Dana <dana@example.com>", "Alex <alex@example.org>", "Recap: the demo"
        msg["Date"] = "Tue, 20 Oct 2026 17:42:00 +0200"
        return msg

    def test_a_plain_mail_in_quoted_printable_comes_out_as_text(self):
        msg = self.message()
        msg.set_content("The demo cell picked 1,140 lines an hour — two errors.\n", cte="quoted-printable")
        self.assertIn("=E2=80=94", bytes(msg).decode("ascii"))  # what the old reader printed
        text = self.eml(msg)
        self.assertIn("From: Dana <dana@example.com>", text)
        self.assertIn("Date: Tue, 20 Oct 2026 17:42:00 +0200", text)
        self.assertIn("1,140 lines an hour — two errors.", text)

    def test_html_in_base64_with_an_attachment(self):
        msg = self.message()
        msg.set_content("<p>Pricing by <b>30 October</b>.</p><style>p{}</style>", subtype="html", cte="base64")
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="quote.pdf")
        text = self.eml(msg)
        self.assertIn("Pricing by 30 October.", text)
        self.assertNotIn("<b>", text)
        self.assertIn("Attachments, not read here: quote.pdf.", text)


if __name__ == "__main__":
    unittest.main()
