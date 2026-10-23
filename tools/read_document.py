#!/usr/bin/env python3
"""Print the text of Word, Excel, PowerPoint, OpenDocument and PDF files, for filing them.

    python3 tools/read_document.py FILE [FILE ...]

Formats: .docx, .xlsx and .xlsm, .pptx, .odt, .ods and .odp, .pdf, a saved e-mail (.eml), and plain text. Tables come
out one row per line, cells separated by " | ". Excel gives the values saved with the file, not the formulas. An e-mail
gives its sender, recipients, date and subject, its text, and the names of its attachments. A PDF is read with
pdftotext when it is installed, otherwise with pypdf; a PDF with no text layer, a scan, is reported as such, to be read
as pictures. Needs the packages in requirements.txt, except for e-mails and text.

Files come from other people, so the reader has limits: an Office or OpenDocument file may unpack to at most 50 MB of
text, a run of spaces is cut at 1,000, XML that declares entities or nests too deeply is refused, and pdftotext gets a
minute. A file past a limit is reported as an error, not read.
"""
import email
import email.policy
import html
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MAX_XML = 50 * 2**20  # bytes of XML an archive may unpack to; pictures and other media do not count
MAX_SPACES = 1000
PDF_TIMEOUT = 60  # seconds
ODF_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
ODF_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class DocumentError(Exception):
    """A file this tool will not read, and why."""


def guard_archive(path):
    """Refuse an Office or OpenDocument file whose XML is too large or declares entities, before any library reads it."""
    try:
        with zipfile.ZipFile(path) as z:
            parts = [i for i in z.infolist() if i.filename.endswith((".xml", ".rels"))]
            size = sum(i.file_size for i in parts)
            if size > MAX_XML:
                raise DocumentError("unpacks to %d MB of text, more than the %d MB this tool reads"
                                    % (size // 2**20, MAX_XML // 2**20))
            for i in parts:
                if b"<!ENTITY" in z.read(i):
                    raise DocumentError("declares XML entities in %s, which a document does not need" % i.filename)
    except zipfile.BadZipFile as e:
        raise DocumentError("is not a valid Office or OpenDocument file (%s)" % e)


def row(cells):
    cells = [c.strip() for c in cells]
    while cells and not cells[-1]:
        cells.pop()
    return " | ".join(cells)


def read_docx(path):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = docx.Document(path)
    out = []
    for child in doc.element.body.iterchildren():
        if child.tag == "{%s}p" % W:
            out.append(Paragraph(child, doc).text)
        elif child.tag == "{%s}tbl" % W:
            for r in Table(child, doc).rows:
                out.append(row(c.text for c in r.cells))
    return "\n".join(out)


def read_xlsx(path):
    import openpyxl
    book = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for sheet in book.worksheets:
        out.append("## Sheet: %s" % sheet.title)
        for values in sheet.iter_rows(values_only=True):
            line = row("" if v is None else str(v) for v in values)
            if line:
                out.append(line)
    return "\n".join(out)


def odf_text(el):
    parts = [el.text or ""]
    for child in el:
        tag = child.tag.split("}")[-1]
        if tag == "s":
            count = child.get("{%s}c" % ODF_TEXT, "1")
            parts.append(" " * min(int(count) if count.isdigit() else 1, MAX_SPACES))
        elif tag == "tab":
            parts.append("\t")
        elif tag == "line-break":
            parts.append("\n")
        else:
            parts.append(odf_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def read_odf(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    out = []

    def walk(el):
        tag = el.tag
        if tag in ("{%s}p" % ODF_TEXT, "{%s}h" % ODF_TEXT):
            out.append(odf_text(el))
        elif tag == "{%s}table-row" % ODF_TABLE:
            out.append(row(odf_text(c) for c in el if c.tag.endswith("table-cell")))
        else:
            for child in el:
                walk(child)
    walk(root)
    return "\n".join(out)


def read_pptx(path):
    from pptx import Presentation
    out = []
    for n, slide in enumerate(Presentation(path).slides, 1):
        out.append("## Slide %d" % n)
        for shape in slide.shapes:
            if shape.has_text_frame:
                out.append(shape.text_frame.text)
            elif getattr(shape, "has_table", False) and shape.has_table:
                for r in shape.table.rows:
                    out.append(row(c.text for c in r.cells))
    return "\n".join(out)


def read_eml(path):
    msg = email.message_from_bytes(Path(path).read_bytes(), policy=email.policy.default)
    out = ["%s: %s" % (h, msg[h]) for h in ("From", "To", "Cc", "Date", "Subject") if msg[h]]
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    if body is not None and body.get_content_type() == "text/html":
        text = re.sub(r"<(script|style)\b.*?</\1\s*>", "", text, flags=re.S | re.I)
        text = html.unescape(re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.I))
        text = re.sub(r"<[^>]+>", "", text)
    out += ["", text.strip()]
    names = [part.get_filename() or part.get_content_type() for part in msg.iter_attachments()]
    if names:
        out += ["", "Attachments, not read here: %s. Save them to Inbox/ to file them." % ", ".join(names)]
    return "\n".join(out)


def read_pdf(path):
    text = pdf_text(path)
    if not text.strip():
        raise DocumentError("has no text layer: it is a scan or a picture. Read its pages as pictures")
    return text


def pdf_text(path):
    if shutil.which("pdftotext"):
        try:
            return subprocess.run(["pdftotext", "-layout", "--", str(path), "-"], capture_output=True, text=True,
                                  check=True, timeout=PDF_TIMEOUT).stdout
        except subprocess.TimeoutExpired:
            pass  # pypdf may still read it, under its own limits
        except subprocess.CalledProcessError:
            pass
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DocumentError("could not be read: pdftotext failed or took over %d seconds, and pypdf is not installed"
                            % PDF_TIMEOUT)
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


READERS = {".eml": read_eml, ".docx": read_docx, ".xlsx": read_xlsx, ".xlsm": read_xlsx, ".pptx": read_pptx, ".odt": read_odf,
           ".ods": read_odf, ".odp": read_odf, ".pdf": read_pdf}


def read(path):
    """The text of one file. Raises DocumentError for a file past the limits."""
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if not reader:
        return path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() not in (".pdf", ".eml"):
        guard_archive(path)
    try:
        return reader(path)
    except RecursionError:
        raise DocumentError("is nested too deeply to read")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    failed = False
    for name in sys.argv[1:]:
        if len(sys.argv) > 2:
            print("# %s\n" % Path(name).name)
        try:
            print(read(name).rstrip() + "\n")
        except DocumentError as e:
            print("%s %s" % (Path(name).name, e), file=sys.stderr)
            failed = True
    sys.exit(1 if failed else 0)
