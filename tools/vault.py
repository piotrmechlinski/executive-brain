#!/usr/bin/env python3
"""The vault's housekeeping. Standard library only.

    python3 tools/vault.py status            what a session starts with: the Inbox, what is overdue, the check
    python3 tools/vault.py check             before every push: exits 1 if anything breaks the vault's rules
    python3 tools/vault.py refresh           rewrites the generated parts of Home.md and the project cards
    python3 tools/vault.py review            the weekly review: what changed, overdue, due soon, actions, stale
    python3 tools/vault.py next D            the next free ID with that prefix, here and on main on GitHub
    python3 tools/vault.py archive P3        moves a done project card to Archive/Projects/ (or an output to Archive/)
    python3 tools/vault.py private-term "X"  keeps X, as a hash, out of every note, register, card and output
    python3 tools/vault.py link NAME --from FILE   the Markdown link from FILE to the note or file called NAME
    python3 tools/vault.py brief P1 "Tom Becker" [--out FILE]   a brief on projects and people, every line cited

Every command takes --vault PATH, the folder of the vault; by default the folder above tools/.

The registers are the Markdown tables in Knowledge/ whose first column is ID (or Person, for the people). The columns
the tools read: ID, Project, Owner, Due, Status, Updated, Source. A row is closed when its Status is done, decided,
closed, dropped or confirmed; it is overdue when it is open and its Due date has passed.
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import zoneinfo
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote

VERSION = "1.0.1"  # the product's version: the first numbered heading of CHANGELOG.md names the same
TOOLS = Path(__file__).resolve().parent
SKIP = {"tools", "build", "examples"}  # at the top: the product's tools, what they build, the fictional example
NEVER = {".git", ".venv", "node_modules", "__pycache__"}  # anywhere: git's own folder, packages and caches
TOP_FILES = {"README.md", "SETUP.md", "CLAUDE.md", "AGENTS.md", "Home.md", "LICENSE", "CHANGELOG.md", "settings.json",
             "requirements.txt"}
FOLDERS = {"Inbox", "Sources", "Meetings", "Knowledge", "Projects", "Outputs", "Private", "Archive", "Templates"}
SAFE = ("Meetings", "Knowledge", "Projects", "Outputs", "Archive")  # and Home.md: where nothing confidential may appear
TEXT = {".md", ".txt", ".csv", ".json", ".html", ".htm", ".svg", ".xml", ".rtf", ".yml", ".yaml"}
PAGES = {".html", ".htm", ".svg", ".xml"}  # read as a browser shows them: tags are not words
DOCS = {".docx", ".xlsx", ".xlsm", ".pptx", ".odt", ".ods", ".odp", ".pdf", ".eml"}  # read by read_document.py
CLOSED = {"done", "decided", "closed", "dropped", "confirmed"}
STATUSES = {"open"} | CLOSED
MEETING_SOURCES = {"recording", "debrief", "notes", "email", "document"}
PROJECT_STATUS = {"active", "on hold", "done"}
ID_RE = re.compile(r"^([A-Z]{1,3})(\d+)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATED = re.compile(r"^\d{4}-\d{2}-\d{2} ")
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
MDLINK = re.compile(r"\]\((<[^>]+>|[^)\s]+)\)")
GENERATED = re.compile(r"(<!-- generated -->\n)(.*?)(<!-- /generated -->)", re.S)
CONFLICT = re.compile(r"^<{7}(?: |$)", re.M)  # the first line of an unresolved git conflict
PRIVATE_LINE = 40  # a line or sentence of Private/ this long or longer must appear nowhere else
CACHE = "check-cache.json"  # in build/: what the confidential check found in each file, by its hash
CACHE_FORM = 2  # in the cache's key: when the check reads files another way, it reads them all again
INLINE = re.compile(r"</?(?:a|abbr|b|bdi|bdo|cite|code|data|del|dfn|em|font|i|ins|kbd|mark|q|s|samp|small|span|"
                    r"strike|strong|sub|sup|time|tt|u|var|wbr)\b[^<>]*>", re.I)  # tags inside a word: Kes<b>trel</b>
# Letters of other alphabets that look Latin, and Latin letters that keep no accent to drop, after case folding
LOOKALIKE = str.maketrans(dict(zip("авекмнорстухіјѕԁһӏαβεζηικμνορτυχıłđøħ", "abekmhopctyxijsdhlabezhikmnoptyxildoh"),
                               æ="ae", œ="oe", þ="th"))
UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})  # Brücke, also as Bruecke


# ---------------- reading the vault ----------------

def front(text):
    """The frontmatter as a dict (lists in [a, b] form become lists) and the text after it."""
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, text
    data = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            key, value = line.split(":", 1)
            value = value.split(" #")[0].strip()
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            data[key.strip()] = value
    return data, text[m.end():]


def cells(line):
    """The cells of a table row. A pipe inside a wikilink, or written as \\|, stays in its cell."""
    protected = re.sub(r"\[\[[^\]]*\]\]", lambda m: m.group(0).replace("|", "\x00"), line.strip())
    protected = protected.replace("\\|", "\x00")
    return [c.strip().replace("\x00", "|") for c in protected.strip("|").split("|")]


def cell_out(text):
    return text.replace("|", "\\|")


def blank_out(m):
    """A removed passage keeps its line breaks, so line numbers after it stay right."""
    return "\n" * m.group(0).count("\n")


def strip_code(text):
    """The text without HTML comments, fenced code and inline code, where links are only examples."""
    text = re.sub(r"<!--.*?-->", blank_out, text, flags=re.S)
    text = re.sub(r"(?ms)^```.*?^```", blank_out, text)
    return re.sub(r"`[^`\n]*`", "", text)


def visible_html(text):
    """An HTML page without its scripts, styles and data: addresses, which hold code and fonts, not what it says."""
    text = re.sub(r"<(script|style)\b.*?</\1\s*>", blank_out, text, flags=re.S | re.I)
    return re.sub(r"data:[^\s\"')]+", "", text)


def untag(text, page=False):
    """Text as it shows: a tag inside a word (Kes<span></span>trel) is dropped, and a <br>, or in a page any other
    tag, parts words. Line breaks stay where they were."""
    text = re.sub(r"<br\s*/?>", " ", INLINE.sub(blank_out, text), flags=re.I)
    return re.sub(r"<[^<>]*>", lambda m: " " + blank_out(m), text) if page else text


def tables(text):
    """Every Markdown table: (heading, header, [(line number, cells)], line number of the header)."""
    out, heading, lines, i = [], "", text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+$", lines[i + 1].strip()):
            head, rows, j = cells(line), [], i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append((j + 1, cells(lines[j])))
                j += 1
            out.append((heading, head, rows, i + 1))
            i = j
            continue
        i += 1
    return out


def one(value):
    """A frontmatter value that should be single; a list such as [recording] is joined, and the check names it."""
    return ", ".join(value) if isinstance(value, list) else (value or "")


def conflicts(v):
    """[(file, line, inside a generated part)] for every unresolved git conflict in the vault's text files."""
    found = []
    for p in v.files:
        if p.suffix.lower() not in TEXT:
            continue
        text = v.text(p)
        if "<<<<<<<" not in text:
            continue
        spans = [m.span(2) for m in GENERATED.finditer(text)]
        for m in CONFLICT.finditer(text):
            inside = any(a <= m.start() < b for a, b in spans)
            found.append((p, text.count("\n", 0, m.start()) + 1, inside))
    return found


def section(text, title):
    """The first non-empty line of a level-2 section, comments aside."""
    m = re.search(r"^## %s\s*\n(.*?)(?=^## |\Z)" % re.escape(title), text, re.S | re.M)
    if not m:
        return ""
    for line in re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).splitlines():
        if line.strip():
            return line.strip().lstrip("-* ").strip()
    return ""


def closed(row):
    return row.get("Status", "").strip().lower() in CLOSED


def git_date(root, path):
    """The date of the last commit that touched a file, or None outside git."""
    try:
        out = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%cs", "--", str(path)],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return date.fromisoformat(out) if out else None
    except Exception:
        return None


def fold(text):
    """Text as the confidential check compares it: entities decoded, wide and look-alike letters mapped, accents,
    invisible characters and Markdown emphasis dropped, case folded. PROJECT Kés**trel** folds as project kestrel."""
    text = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", html.unescape(text)).casefold())
    text = "".join(c for c in text if unicodedata.category(c) not in ("Mn", "Cf") and c not in "*~`")
    return text.translate(LOOKALIKE)


def words(text):
    """The folded words of a text; an underscore parts two words."""
    return re.findall(r"[^\W_]+", fold(text))


def plain_words(text):
    """The words as the first terms were hashed, before the check folded text: such a term still matches."""
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())


def short_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def term_hash(text):
    return short_hash(" ".join(words(text)))


def skipped(parts):
    """Not part of the vault: tools/, build/ and examples/ at the top; git's folder, packages and caches anywhere."""
    return parts[0] in SKIP or any(part in NEVER for part in parts)


def hidden(parts):
    """A hidden file or folder, such as .github/ or Meetings/.drafts/: read for confidential words, and nothing else."""
    return any(part.startswith(".") for part in parts)


class Vault:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.rows, self.projects, self.meetings, self.problems = [], {}, [], []
        f = self.root / "settings.json"
        try:
            self.settings = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except ValueError as e:
            self.settings = {}
            self.problems.append("settings.json: not valid JSON (%s); the confidential words in it are not checked" % e)
        global ZONE
        ZONE, problem = time_zone(self.settings.get("timezone"))
        self.problems += [problem] if problem else []
        self.files, self.hidden = [], []
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root)
            if p.is_file() and not skipped(rel.parts):
                (self.hidden if hidden(rel.parts) else self.files).append(p)
        self.notes = [p for p in self.files if p.suffix == ".md"]
        self._read()

    def rel(self, p):
        return p.relative_to(self.root).as_posix()

    def top(self, p):
        return p.relative_to(self.root).parts[0]

    def text(self, p):
        return p.read_text(encoding="utf-8", errors="replace")

    def _read(self):
        for p in self.notes:
            top, name = self.top(p), p.name
            if name == "README.md" or top == "Templates":
                continue
            text = self.text(p)
            meta, body = front(text)
            offset = text[:len(text) - len(body)].count("\n")  # line numbers count from the top of the file
            if top == "Knowledge":
                read = set()
                for heading, head, rows, first in tables(body):
                    read |= {first, first + 1} | {line for line, _ in rows}
                    if not head or head[0] not in ("ID", "Person"):
                        continue
                    missing = [c for c in ("Updated", "Source") if c not in head]
                    if missing:
                        self.problems.append("%s: the table under '%s' has no %s column" % (self.rel(p), heading or p.stem, " or ".join(missing)))
                    for line, c in rows:
                        if len(c) != len(head):
                            self.problems.append("%s:%d: a row with %d cells under %d columns" % (self.rel(p), line + offset, len(c), len(head)))
                            continue
                        row = dict(zip(head, c))
                        self.rows.append({"file": p, "line": line + offset, "kind": head[0], "id": row[head[0]],
                                          "register": p.stem, "item": head[1] if len(head) > 1 else head[0],
                                          "heading": heading or p.stem, "head": head, "row": row})
                previous = ""
                for n, line in enumerate(body.split("\n"), 1):
                    if line.startswith("|") and n not in read and not previous.startswith("|"):
                        self.problems.append("%s:%d: a table row outside its table; the line above it breaks the table, so "
                                             "this row and the ones after it are not read" % (self.rel(p), n + offset))
                    previous = line if n not in read else ""
            elif meta.get("type") == "project" and top in ("Projects", "Archive"):
                pid = one(meta.get("id"))
                title = re.search(r"^# (.+)$", body, re.M)
                name_ = re.sub(r"^P\d+\s+", "", title.group(1).strip()) if title else p.stem
                self.projects.setdefault(pid, []).append({
                    "id": pid, "name": name_, "status": one(meta.get("status")), "owner": one(meta.get("owner")),
                    "path": p, "archived": top == "Archive", "goal": section(body, "Goal"),
                    "next": section(body, "Next step"), "meta": meta, "body": body})
            elif meta.get("type") == "meeting" and top in ("Meetings", "Archive"):
                self.meetings.append({"path": p, "meta": meta, "date": one(meta.get("date")),
                                      "projects": as_list(meta.get("projects")), "title": p.stem})
        self.meetings.sort(key=lambda m: (m["date"], m["title"]), reverse=True)

    def project(self, pid):
        found = self.projects.get(pid, [])
        return found[0] if found else None

    def projects_of(self, row):
        value = row["row"].get("Project", "").strip()
        if value in ("", "-"):
            return []
        return [t.strip() for t in re.split(r"[,;\s]+", value) if t.strip()]

    def registers(self):
        """Register files in the order of the template, then any others."""
        order = ["Decisions", "Actions", "Risks", "Milestones", "Assumptions", "Current State", "People"]
        names = sorted({r["register"] for r in self.rows} | {p.stem for p in self.notes
                        if self.top(p) == "Knowledge" and p.name != "README.md"},
                       key=lambda n: (order.index(n) if n in order else len(order), n))
        return names

    def link(self, from_file, target):
        """A Markdown link from one file to another, relative and percent-encoded."""
        rel = os.path.relpath(target, from_file.parent).replace(os.sep, "/")
        return quote(rel)

    def inside(self, path, top):
        """True when the path is in the vault (top None) or in one of its top folders."""
        try:
            parts = Path(path).resolve().relative_to(self.root).parts
        except ValueError:
            return False
        return top is None or (len(parts) > 1 and parts[0] == top)

    def named(self, name):
        """The files a wikilink or a name may mean: by path, by file name, or by note name."""
        name = name.strip()
        return [p for p in self.files if name in (self.rel(p), self.rel(p)[:-3], p.name, p.stem)]

    def index(self):
        paths = {self.rel(p) for p in self.files}
        paths |= {r[:-3] for r in paths if r.endswith(".md")}
        names = {p.name for p in self.files} | {p.stem for p in self.notes}
        return paths, names


def as_list(value):
    if isinstance(value, list):
        return value
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


ZONE = None  # the vault's time zone, from "timezone" in settings.json, once a vault is read


def today():
    """Today where the executive is, so a debrief late in the evening gets that day's date."""
    fixed = os.environ.get("VAULT_TODAY")  # for tests: the date the vault is read on
    if fixed:
        return date.fromisoformat(fixed)
    return datetime.now(ZONE).date() if ZONE else date.today()


def time_zone(name):
    """(zone or None, a problem or None). A computer without a time-zone database is no problem: the local date is."""
    if not name:
        return None, None
    try:
        if not isinstance(name, str):
            raise ValueError(name)
        return zoneinfo.ZoneInfo(name), None
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        try:
            zoneinfo.ZoneInfo("UTC")
        except zoneinfo.ZoneInfoNotFoundError:
            return None, None
        return None, "settings.json: the time zone \"%s\" is not known; use a name such as \"Europe/Warsaw\"" % name


def due_of(row):
    d = row["row"].get("Due", "").strip()
    try:
        return date.fromisoformat(d) if DATE_RE.match(d) else None
    except ValueError:
        return None


# ---------------- the generated parts ----------------

def counts_line(v, pid):
    """The open rows of a project, such as "2 decisions · 1 risk"."""
    parts = []
    for reg in v.registers():
        rows = [r for r in v.rows if r["register"] == reg and pid in v.projects_of(r) and r["kind"] == "ID" and not closed(r["row"])]
        if rows:
            item = rows[0]["item"].lower()
            parts.append("%d %s" % (len(rows), item if len(rows) == 1 else item + "s"))
    return " · ".join(parts) or "-"


def home_block(v):
    home = v.root / "Home.md"
    out = ["## Projects", ""]
    live = sorted((p[0] for p in v.projects.values() if p and not p[0]["archived"]), key=lambda p: pid_key(p["id"]))
    if live:
        out += ["| Project | Status | Owner | Next step | Open |", "|---|---|---|---|---|"]
        for p in live:
            out.append("| [%s %s](%s) | %s | %s | %s | %s |" % (p["id"], cell_out(p["name"]), v.link(home, p["path"]),
                       p["status"], cell_out(p["owner"]), cell_out(p["next"]) or "-", counts_line(v, p["id"])))
    else:
        out.append("No projects yet. `/setup` creates the first ones.")
    out += ["", "## Registers", "", "| Register | Open | All |", "|---|---|---|"]
    for reg in v.registers():
        rows = [r for r in v.rows if r["register"] == reg]
        f = v.root / "Knowledge" / (reg + ".md")
        has_status = any("Status" in r["head"] for r in rows)
        open_ = str(len([r for r in rows if not closed(r["row"])])) if has_status else "-"
        out.append("| [%s](%s) | %s | %d |" % (reg, v.link(home, f), open_, len(rows)))
    out += ["", "## Latest meetings", ""]
    meetings = [m for m in v.meetings if v.top(m["path"]) == "Meetings"][:10]
    for m in meetings:
        tag = " · " + ", ".join(m["projects"]) if m["projects"] else ""
        out.append("- [%s](%s)%s" % (m["title"], v.link(home, m["path"]), tag))
    if not meetings:
        out.append("No meetings yet. `/debrief` after the next one.")
    return "\n".join(out) + "\n"


def pid_key(pid):
    m = ID_RE.match(pid or "")
    return (m.group(1), int(m.group(2))) if m else ("~", 0)


def row_key(r):
    m = ID_RE.match(r["id"])
    return (m.group(1), int(m.group(2))) if m else (r["id"], 0)


def card_block(v, p):
    card = p["path"]
    out = ["## From the registers", ""]
    any_rows = False
    for reg in v.registers():
        rows = [r for r in v.rows if r["register"] == reg and p["id"] in v.projects_of(r)]
        if not rows:
            continue
        any_rows = True
        f = rows[0]["file"]
        if rows[0]["kind"] == "Person":
            out += ["### " + rows[0]["heading"], "", "| Person | Role | Interests |", "|---|---|---|"]
            for r in sorted(rows, key=lambda r: r["id"]):
                out.append("| %s | %s | %s |" % (cell_out(r["id"]), cell_out(r["row"].get("Role", "")), cell_out(r["row"].get("Interests", ""))))
            out.append("")
            continue
        head = rows[0]["head"]
        extra = [c for c in ("Level", "Owner", "Due", "Status") if c in head]
        open_rows = sorted([r for r in rows if not closed(r["row"])], key=lambda r: (r["row"].get("Due", "") or "9999", row_key(r)))
        done_rows = sorted([r for r in rows if closed(r["row"])], key=lambda r: (r["row"].get("Updated", ""), row_key(r)), reverse=True)
        out += ["### " + rows[0]["heading"], "", "| ID | %s | %s |" % (rows[0]["item"], " | ".join(extra)),
                "|---|---|%s|" % "|".join("---" for _ in extra)]
        for r in open_rows + done_rows[:5]:
            out.append("| [%s](%s) | %s | %s |" % (r["id"], v.link(card, f), cell_out(r["row"].get(rows[0]["item"], "")),
                                                   " | ".join(cell_out(r["row"].get(c, "")) for c in extra)))
        if len(done_rows) > 5:
            out.append("")
            out.append("And %d more closed in [%s](%s)." % (len(done_rows) - 5, rows[0]["heading"], v.link(card, f)))
        out.append("")
    if not any_rows:
        out += ["Nothing in the registers names this project yet.", ""]
    meetings = [m for m in v.meetings if p["id"] in m["projects"]]
    if meetings:
        out += ["### Meetings", ""]
        out += ["- [%s](%s)" % (m["title"], v.link(card, m["path"])) for m in meetings]
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def refreshed(v):
    """{path: new text} for every file whose generated part is out of date."""
    changes = {}
    home = v.root / "Home.md"
    if home.exists():
        changes[home] = (v.text(home), home_block(v))
    for found in v.projects.values():
        for p in found:
            changes[p["path"]] = (v.text(p["path"]), card_block(v, p))
    out = {}
    for path, (text, block) in changes.items():
        if not GENERATED.search(text):
            continue
        new = GENERATED.sub(lambda m: m.group(1) + block + m.group(3), text, count=1)
        if new != text:
            out[path] = new
    return out


# ---------------- the check ----------------

def private_index(v):
    """(the hashed terms, {a line or sentence of Private/, as its folded words: the note it is in})."""
    terms = {(t["n"], t["h"]) for t in v.settings.get("private_terms", [])}
    lines = {}
    for p in v.files:
        if v.top(p) == "Private" and p.suffix in (".md", ".txt") and p.name != "README.md":
            for line in v.text(p).splitlines():
                s = re.sub(r"^\s*(?:[-*]|\d+\.|#+)\s*", "", line).strip()
                for piece in [s] + re.split(r"(?<=[.!?;])\s+", s):  # the line, and each of its sentences
                    if len(piece) >= PRIVATE_LINE and len(words(piece)) >= 3:
                        lines[" ".join(words(piece))] = v.rel(p)
    return terms, lines


def doc_text(p):
    sys.path.insert(0, str(TOOLS))
    import read_document
    return read_document.read(p)


def ignored(v, paths):
    """The paths that git ignores, such as .claude/settings.local.json: they never reach GitHub."""
    try:
        r = subprocess.run(["git", "-C", str(v.root), "check-ignore", "-z", "--stdin"], input="\0".join(paths),
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(r.stdout.split("\0")) - {""}


def safe_files(v):
    """Where nothing confidential may appear: the notes, registers, cards and outputs, the summaries that Claude
    writes in Sources/, and hidden files and folders, such as .github/, outside Private/, Sources/, Inbox/ and
    Templates/, unless git ignores them. The rest of Sources/ holds the material as it came, confidential parts
    included."""
    skip = ignored(v, [v.rel(p) for p in v.hidden]) if v.hidden else set()
    for p in v.files + [p for p in v.hidden if v.rel(p) not in skip]:
        top = v.top(p)
        summary = top == "Sources" and p.name.endswith(" — summary.md")
        if (top in SAFE or v.rel(p) == "Home.md" or summary or top.startswith(".")) and p.name != "README.md":
            yield p


def extra_texts(v):
    """[(name, text)]: what the executive writes outside the folders. CLAUDE.md, where "About me" says what they work
    on, and the title and footer that settings.json puts on every map and document."""
    f = v.root / "CLAUDE.md"
    out = [("CLAUDE.md", v.text(f))] if f.is_file() else []
    for key in ("title", "footer"):
        if isinstance(v.settings.get(key), str):
            out.append(('settings.json, "%s"' % key, v.settings[key]))
    return out


def found_in(text, terms, sizes, lines):
    """(the lines where a confidential term starts, the Private/ notes the text quotes). Both are matched over the
    folded words of the whole text, so a term or a line split over two lines, rows or list items is still found."""
    at = [(n, w) for n, line in enumerate(text.splitlines(), 1) for w in words(line)]
    seq = [w for _, w in at]
    starts = {at[k][0] for n in sizes for k in range(len(seq) - n + 1)
              if (n, short_hash(" ".join(seq[k:k + n]))) in terms}
    for n, line in enumerate(text.splitlines(), 1):
        w = plain_words(line) if not line.isascii() or "_" in line else []
        if any((m, short_hash(" ".join(w[k:k + m]))) in terms for m in sizes for k in range(len(w) - m + 1)):
            starts.add(n)
    joined = " %s " % " ".join(seq)
    return sorted(starts), sorted({note for line, note in lines.items() if " %s " % line in joined})


def hits(text, terms, sizes):
    """True when the text holds a confidential term."""
    return bool(found_in(text, terms, sizes, {})[0])


def confidential(v):
    """({file: (lines with a confidential term, Private/ notes it quotes)}, warnings for files that could not be read).

    What each file held is kept in build/check-cache.json under the file's hash, so a file that has not changed since
    the last check, such as a large map in Outputs/, is not read again. A new term or a changed Private/ note clears it.
    """
    terms, lines = private_index(v)
    if not terms and not lines:
        return {}, []
    sizes = sorted({n for n, _ in terms})
    key = hashlib.sha256(json.dumps([CACHE_FORM, sorted(terms), sorted(lines.items())]).encode("utf-8")).hexdigest()
    cache_file = v.root / "build" / CACHE
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        old = cache["files"] if cache.get("key") == key and isinstance(cache.get("files"), dict) else {}
    except (OSError, ValueError, AttributeError):
        old = {}
    new, found, unreadable = {}, {}, []
    for p in safe_files(v):
        suffix, rel = p.suffix.lower(), v.rel(p)
        if hits(rel, terms, sizes):
            found[rel + " (its name)"] = ([0], [])
        if suffix not in TEXT and suffix not in DOCS:
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        seen = old.get(rel)
        if isinstance(seen, dict) and seen.get("sha") == digest and {"terms", "private"} <= set(seen):
            term_lines, sources = seen["terms"], seen["private"]
        else:
            if suffix in DOCS:
                try:
                    text = doc_text(p)
                except Exception as e:
                    unreadable.append("%s: could not be read for the confidential check (%s)" % (rel, e.__class__.__name__))
                    continue
            else:
                text = untag(visible_html(v.text(p)), True) if suffix in PAGES else untag(v.text(p))
            term_lines, sources = found_in(text, terms, sizes, lines)
        new[rel] = {"sha": digest, "terms": term_lines, "private": sources}
        if term_lines or sources:
            found[rel] = (term_lines, sources)
    for name, text in extra_texts(v):
        term_lines, sources = found_in(text, terms, sizes, lines)
        if term_lines or sources:
            found[name] = (term_lines if name == "CLAUDE.md" else [0] * bool(term_lines), sources)
    if new != old:
        try:
            cache_file.parent.mkdir(exist_ok=True)
            cache_file.write_text(json.dumps({"key": key, "files": new}), encoding="utf-8")
        except OSError:
            pass
    return found, unreadable


def source_problem(v, register, cell):
    """(what is wrong with a row's Source, or None; 1 if it is an old [[wikilink]], else 0)."""
    targets = []
    for m in MDLINK.finditer(cell):
        url = m.group(1).strip()
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
            continue  # a web address may stand next to the source, never in its place
        targets.append((url, (register.parent / unquote(url.strip("<>").split("#")[0])).resolve()))
    wikis = [m.group(1).split("|")[0].split("#")[0].strip() for m in WIKILINK.finditer(cell)]
    if not targets and not wikis:
        if re.search(r"\]\([^)<>]*\s[^)]*\)", cell):
            return "has a link with a space in its path, which no one can click; write it as [name](<path>)", 0
        if MDLINK.search(cell):
            return "has only a web address as its source; save the page to Sources/ and link it there", 0
        return "has no source; link the meeting note, the summary or the file", 0
    for url, target in targets:
        if not v.inside(target, None):
            return "has a source outside the vault: %s" % url, 0
        if target.is_dir():
            return "has a folder as its source: %s; link the note or the file in it" % url, 0
        if v.inside(target, "Private"):
            return "has a Private/ note as its source; a fact that rests on it goes to Private/ too", 0
    for name in wikis:
        found = v.named(name)
        if found and all(v.top(f) == "Private" for f in found):
            return "has a Private/ note as its source; a fact that rests on it goes to Private/ too", 0
    return None, 1 if wikis else 0


def check(v):
    errors, warnings = list(v.problems), []
    wikilinked = {}
    extra = set(v.settings.get("folders", []))
    # the top level
    for p in sorted(v.root.iterdir()):
        if skipped([p.name]) or hidden([p.name]):
            continue
        if p.is_file() and p.name not in TOP_FILES:
            errors.append("%s: a file at the top level; it belongs in a folder" % p.name)
        if p.is_dir() and p.name not in FOLDERS | extra:
            errors.append("%s/: a folder the vault does not know; add it to \"folders\" in settings.json if it is meant" % p.name)
    # names and frontmatter
    for p in v.files:
        top, rel = v.top(p), v.rel(p)
        if p.name == "README.md" or top in ("Templates", "Archive", "Private", "Knowledge") or len(p.relative_to(v.root).parts) == 1:
            continue
        if top in ("Sources", "Outputs", "Meetings") and not DATED.match(p.name):
            errors.append("%s: the name starts with its date, YYYY-MM-DD" % rel)
        if top == "Inbox":
            warnings.append("%s: waiting in the Inbox" % rel)
        if top == "Meetings" and p.suffix == ".md":
            meta, _ = front(v.text(p))
            if meta.get("type") != "meeting":
                errors.append("%s: no meeting frontmatter (type: meeting)" % rel)
                continue
            for key in ("date", "source", "consent"):
                if isinstance(meta.get(key), list):
                    errors.append("%s: %s takes one value, not a list" % (rel, key))
            if one(meta.get("date")) != p.name[:10]:
                errors.append("%s: the date in the frontmatter is not the date in the name" % rel)
            if one(meta.get("source")) not in MEETING_SOURCES:
                errors.append("%s: source is one of %s" % (rel, ", ".join(sorted(MEETING_SOURCES))))
            if one(meta.get("source")) == "recording" and one(meta.get("consent")).lower() != "yes":
                errors.append("%s: a recording without consent: yes" % rel)
            for pid in as_list(meta.get("projects")):
                if pid not in v.projects:
                    errors.append("%s: unknown project %s" % (rel, pid))
        if top == "Projects" and p.suffix == ".md":
            meta, body = front(v.text(p))
            for key in ("id", "status", "owner"):
                if isinstance(meta.get(key), list):
                    errors.append("%s: %s takes one value, not a list" % (rel, key))
            pid = one(meta.get("id"))
            if meta.get("type") != "project" or not re.match(r"^P\d+$", pid):
                errors.append("%s: no project frontmatter (type: project, id: P1)" % rel)
                continue
            if not p.name.startswith(pid + " "):
                errors.append("%s: the name starts with its ID, %s" % (rel, pid))
            if one(meta.get("status")) not in PROJECT_STATUS:
                errors.append("%s: status is one of active, on hold, done" % rel)
            if not meta.get("owner"):
                errors.append("%s: no owner" % rel)
            if not GENERATED.search(v.text(p)):
                errors.append("%s: no <!-- generated --> part" % rel)
            if meta.get("status") == "done":
                warnings.append("%s: done; archive it with: python3 tools/vault.py archive %s" % (rel, pid))
    for pid, found in v.projects.items():
        if len(found) > 1:
            errors.append("project %s: %d cards (%s)" % (pid, len(found), ", ".join(v.rel(p["path"]) for p in found)))
    # the registers
    seen, prefixes = {}, {}
    for r in v.rows:
        where = "%s:%d" % (v.rel(r["file"]), r["line"])
        row = r["row"]
        if r["kind"] == "ID":
            m = ID_RE.match(r["id"])
            if not m:
                errors.append("%s: the ID %r is not a prefix and a number, such as D7" % (where, r["id"]))
            else:
                if m.group(1) == "P":
                    errors.append("%s: P is the prefix of projects; a register needs its own" % where)
                prefixes.setdefault((r["file"], m.group(1)), where)
            if r["id"] in seen:
                errors.append("%s: %s is already used at %s" % (where, r["id"], seen[r["id"]]))
            seen.setdefault(r["id"], where)
        elif not r["id"]:
            errors.append("%s: a row without a person" % where)
        for pid in v.projects_of(r):
            if pid != "all" and pid not in v.projects:
                errors.append("%s: unknown project %s" % (where, pid))
        if "Updated" in row and not DATE_RE.match(row["Updated"]):
            errors.append("%s: Updated is a date, YYYY-MM-DD" % where)
        problem, old_form = source_problem(v, r["file"], row.get("Source", ""))
        if problem:
            errors.append("%s: %s %s" % (where, r["id"], problem))
        wikilinked[r["file"]] = wikilinked.get(r["file"], 0) + old_form
        if "Status" in row and row["Status"].strip().lower() not in STATUSES:
            said = "has the Status %r" % row["Status"].strip() if row["Status"].strip() else "has no Status"
            errors.append("%s: %s %s; it is open, or closed as done, decided, closed, dropped or confirmed"
                          % (where, r["id"], said))
        if "Owner" in row and not row["Owner"].strip() and not closed(row):
            errors.append("%s: %s is open without an owner" % (where, r["id"]))
        if row.get("Due", "").strip() and not DATE_RE.match(row["Due"].strip()):
            errors.append("%s: Due is a date, YYYY-MM-DD" % where)
        d = due_of(r)
        if d and d < today() and not closed(row):
            warnings.append("%s: %s is overdue since %s" % (where, r["id"], d.isoformat()))
    for f, n in sorted(wikilinked.items()):
        if n:
            warnings.append("%s: %d sources are [[wikilinks]], which GitHub does not open; write them as Markdown links, "
                            "with python3 tools/vault.py link NAME --from %s" % (v.rel(f), n, v.rel(f)))
    by_file = {}
    for (f, prefix), where in prefixes.items():
        by_file.setdefault(f, []).append(prefix)
    for f, found in by_file.items():
        if len(found) > 1:
            errors.append("%s: one prefix per register, found %s" % (v.rel(f), ", ".join(sorted(found))))
    # links
    paths, names = v.index()
    for p in v.notes:
        top = v.top(p)
        if p.name == "README.md" or top in ("Templates", "Inbox") or (top not in FOLDERS and v.rel(p) != "Home.md"):
            continue
        text = strip_code(v.text(p))
        if top == "Knowledge":  # a fact written as a bullet carries its date and its source, as a row does
            for n_line, line in enumerate(text.splitlines(), 1):
                if re.match(r"^\s*[-*] \S", line) and not (re.search(r"\d{4}-\d{2}-\d{2}", line) and (WIKILINK.search(line) or MDLINK.search(line))):
                    errors.append("%s:%d: a fact without its date and source: %s" % (v.rel(p), n_line, line.strip()[:70]))
        for m in WIKILINK.finditer(text):
            target = m.group(1).split("|")[0].split("#")[0].strip()
            if target and target not in paths and target.split("/")[-1] not in names:
                errors.append("%s: [[%s]] leads nowhere" % (v.rel(p), target))
            elif target and top != "Private" and all(v.top(f) == "Private" for f in v.named(target)):
                errors.append("%s: [[%s]] leads into Private/, which nothing outside it may link to" % (v.rel(p), target))
        for m in MDLINK.finditer(text):
            url = m.group(1).strip("<>")
            if re.match(r"^[a-z]+:", url) or url.startswith("#"):
                continue
            target = (p.parent / unquote(url.split("#")[0])).resolve()
            if not target.exists():
                errors.append("%s: the link %s leads nowhere" % (v.rel(p), url))
            elif top != "Private" and v.inside(target, "Private"):
                errors.append("%s: the link %s leads into Private/, which nothing outside it may link to" % (v.rel(p), url))
    # nothing confidential outside Private/ and Sources/
    found, unreadable = confidential(v)
    for rel, (term_lines, sources) in sorted(found.items()):
        errors += ["%s%s: a confidential term outside Private/" % (rel, ":%d" % n if n else "") for n in term_lines]
        errors += ["%s: holds a line of %s" % (rel, source) for source in sources]
    warnings += unreadable
    # unresolved git conflicts
    for p, line, inside in conflicts(v):
        if inside:
            errors.append("%s:%d: an unresolved git conflict in the generated part; run python3 tools/vault.py refresh"
                          % (v.rel(p), line))
        else:
            errors.append("%s:%d: an unresolved git conflict; keep the right lines and remove the <<<<<<<, ======= and "
                          ">>>>>>> lines" % (v.rel(p), line))
    # the generated parts
    for path in refreshed(v):
        errors.append("%s: the generated part is out of date; run python3 tools/vault.py refresh" % v.rel(path))
    return errors, warnings


# ---------------- the commands ----------------

def overdue_and_soon(v, days=14):
    late, soon = [], []
    for r in v.rows:
        d = due_of(r)
        if not d or closed(r["row"]):
            continue
        if d < today():
            late.append((d, r))
        elif d <= today() + timedelta(days=days):
            soon.append((d, r))
    return sorted(late, key=lambda x: (x[0], row_key(x[1]))), sorted(soon, key=lambda x: (x[0], row_key(x[1])))


def describe(r, owner=True):
    row = r["row"]
    parts = ["%s %s" % (r["id"], row.get(r["item"], ""))]
    if row.get("Project", "-") not in ("", "-"):
        parts.append(row["Project"])
    if row.get("Due"):
        parts.append("due " + row["Due"])
    if owner and row.get("Owner"):
        parts.append(row["Owner"])
    return " · ".join(parts)


def inbox(v):
    return [p for p in v.files if v.top(p) == "Inbox" and p.name != "README.md"]


def last_review(v):
    """The date of the last weekly review note, or None."""
    reviews = [m for m in v.meetings if "weekly review" in m["title"].lower() and DATE_RE.match(m["date"])]
    return date.fromisoformat(reviews[0]["date"]) if reviews else None


def updated_of(r):
    d = r["row"].get("Updated", "").strip()
    try:
        return date.fromisoformat(d) if DATE_RE.match(d) else None
    except ValueError:
        return None


def unverified(r):
    """A row that still carries *unverified* from its source: the executive was not sure of it."""
    return any("unverified" in value.lower() for key, value in r["row"].items() if key != "Source")


def cmd_status(v):
    print("Vault status, %s (Executive Brain %s)" % (today().isoformat(), VERSION))
    claude = v.root / "CLAUDE.md"
    if claude.exists() and "(not set)" in v.text(claude):
        print("- Setup: \"About me\" in CLAUDE.md is not filled in. Run /setup first.")
    waiting = inbox(v)
    if waiting:
        print("- Inbox: %d waiting (%s). File them first, with /ingest." % (len(waiting), ", ".join(p.name for p in waiting[:5])))
    else:
        print("- Inbox: empty.")
    late, soon = overdue_and_soon(v)
    print("- Overdue: %d%s" % (len(late), "".join("\n    " + describe(r) for _, r in late[:5])))
    print("- Due within 14 days: %d" % len(soon))
    last = last_review(v)
    if last:
        print("- Weekly review: last on %s%s" % (last, ", due now (/review)" if today() - last >= timedelta(days=7) else ""))
    else:
        print("- Weekly review: none yet (/review).")
    errors, _ = check(v)
    print("- Check: %s" % ("passes." if not errors else "%d to fix (python3 tools/vault.py check)." % len(errors)))


def cmd_check(v):
    errors, warnings = check(v)
    if warnings:
        print("Worth a look:")
        print("\n".join("  " + w for w in warnings))
    if errors:
        print("To fix before the push:")
        print("\n".join("  " + e for e in errors))
        sys.exit(1)
    print("The vault is in order: %d notes, %d register rows, %d projects." % (len(v.notes), len(v.rows), len(v.projects)))


def cmd_refresh(v):
    hard = [(p, line) for p, line, inside in conflicts(v) if not inside]
    if hard:
        print("Resolve these git conflicts first; refresh would rebuild the generated parts from half a file:")
        print("\n".join("  %s:%d" % (v.rel(p), line) for p, line in hard))
        sys.exit(1)
    changes = refreshed(v)
    for path, text in changes.items():
        path.write_text(text, encoding="utf-8")
        print("refreshed %s" % v.rel(path))
    if not changes:
        print("Everything generated is up to date.")


def last_change(v, p):
    dates = [git_date(v.root, p["path"])]
    for r in v.rows:
        if p["id"] in v.projects_of(r) and DATE_RE.match(r["row"].get("Updated", "")):
            dates.append(date.fromisoformat(r["row"]["Updated"]))
    dates += [date.fromisoformat(m["date"]) for m in v.meetings if p["id"] in m["projects"] and DATE_RE.match(m["date"])]
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def cmd_review(v):
    late, soon = overdue_and_soon(v)
    stale_days = int(v.settings.get("stale_days", 30))
    stale = []
    for found in v.projects.values():
        p = found[0]
        if p["archived"] or p["status"] != "active":
            continue
        last = last_change(v, p)
        if last is None or today() - last > timedelta(days=stale_days):
            stale.append((p, last))
    done = [found[0] for found in v.projects.values() if not found[0]["archived"] and found[0]["status"] == "done"]
    risks = [r for r in v.rows if r["register"] == "Risks" and not closed(r["row"]) and not r["row"].get("Mitigation", "").strip()]
    undated = [r for r in v.rows if r["register"] == "Decisions" and not closed(r["row"]) and not r["row"].get("Due", "").strip()]
    actions = sorted((r for r in v.rows if r["register"] == "Actions" and not closed(r["row"])),
                     key=lambda r: (r["row"].get("Owner", "").strip().lower(), r["row"].get("Due", "") or "9999", row_key(r)))
    doubtful = sorted((r for r in v.rows if r["kind"] == "ID" and not closed(r["row"]) and unverified(r)), key=row_key)
    waiting = inbox(v)

    reviewed = last_review(v)
    since = reviewed or today() - timedelta(days=7)
    changed = sorted((r for r in v.rows if r["kind"] == "ID" and updated_of(r) and updated_of(r) > since),
                     key=lambda r: (r["register"] != "Decisions", row_key(r)))
    decided = [r for r in changed if r["row"].get("Status", "").strip().lower() == "decided"]
    finished = [r for r in changed if closed(r["row"]) and r not in decided]
    opened = [r for r in changed if not closed(r["row"])]

    def block(title, items):
        print("\n## %s (%d)" % (title, len(items)))
        print("\n".join("- " + i for i in items) if items else "- nothing")

    def outcome(r):
        said = r["row"].get("Outcome", "").strip()
        return describe(r) + (": " + said if said else "")

    print("# Weekly review, %s" % today().isoformat())
    print("\n## %s" % ("Since the last review, on %s" % reviewed if reviewed else "In the last 7 days (no review yet)"))
    for title, items in (("Decided", [outcome(r) for r in decided]),
                         ("Closed", ["%s (%s)" % (describe(r), r["row"]["Status"].strip().lower()) for r in finished]),
                         ("New or changed", [describe(r) for r in opened])):
        print("- %s (%d)%s" % (title, len(items), "".join("\n  - " + i for i in items)))
    block("Overdue", [describe(r) for _, r in late])
    block("Due within 14 days", [describe(r) for _, r in soon])
    block("Open actions, by owner",
          ["%s: %s" % (r["row"].get("Owner", "").strip() or "no owner", describe(r, owner=False)) for r in actions])
    block("Projects with no change in %d days" % stale_days,
          ["%s %s · last change %s" % (p["id"], p["name"], last or "unknown") for p, last in stale])
    block("Waiting in the Inbox", [p.name for p in waiting])
    block("Done projects to archive", ["%s %s" % (p["id"], p["name"]) for p in done])
    block("Open risks without a mitigation", [describe(r) for r in risks])
    block("Open decisions without a due date", [describe(r) for r in undated])
    block("Marked unverified, to confirm", [describe(r) for r in doubtful])


def on_main(root, prefix):
    """The numbers of the IDs with this prefix on main on GitHub, fetched first: another session may have taken one."""
    git = ["git", "-C", str(root)]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if prefix == "P":
        pattern, where = r"^id: *P[0-9]+", ["Projects", "Archive"]
    else:
        pattern, where = r"^\| *%s[0-9]+ *\|" % re.escape(prefix), ["Knowledge"]
    try:
        subprocess.run(git + ["fetch", "-q", "origin", "main"], capture_output=True, timeout=30, env=env)
        out = subprocess.run(git + ["grep", "-h", "-o", "-E", pattern, "origin/main", "--"] + where,
                             capture_output=True, text=True, timeout=20, env=env).stdout
    except Exception:
        return []
    return [int(n) for n in re.findall(r"\d+", out)]


def cmd_next(v, prefix):
    prefix = prefix.upper()
    numbers = [int(ID_RE.match(r["id"]).group(2)) for r in v.rows if ID_RE.match(r["id"]) and ID_RE.match(r["id"]).group(1) == prefix]
    if prefix == "P":
        numbers += [int(pid[1:]) for pid in v.projects if re.match(r"^P\d+$", pid)]
    print("%s%d" % (prefix, max(numbers + on_main(v.root, prefix), default=0) + 1))


def cmd_archive(v, what, force=False):
    if re.match(r"^P\d+$", what):
        p = v.project(what)
        if not p or p["archived"]:
            sys.exit("archive: no active card for %s" % what)
        if p["status"] != "done" and not force:
            sys.exit("archive: %s is %s, not done; set its status to done first, or add --force" % (what, p["status"]))
        dest = v.root / "Archive" / "Projects" / p["path"].name
    else:
        src = (v.root / what).resolve()
        if not src.exists() or v.top(src) != "Outputs":
            sys.exit("archive: give a project ID, such as P3, or a file in Outputs/")
        p = {"path": src}
        dest = v.root / "Archive" / "Outputs" / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p["path"]), str(dest))
    print("moved %s to %s" % (v.rel(p["path"]) if p["path"].exists() else what, dest.relative_to(v.root).as_posix()))
    cmd_refresh(Vault(v.root))


def cmd_private_term(v, text):
    if not words(text):
        sys.exit("private-term: give the word or phrase")
    forms = {unicodedata.normalize("NFC", text), unicodedata.normalize("NFC", text).translate(UMLAUT)}
    terms = v.settings.setdefault("private_terms", [])
    entries = [e for e in ({"n": len(words(f)), "h": term_hash(f)} for f in sorted(forms)) if e not in terms]
    if not entries:
        print("Already kept.")
        return
    terms += [e for i, e in enumerate(entries) if e not in entries[:i]]  # Brücke is kept as brucke and as bruecke
    (v.root / "settings.json").write_text(json.dumps(v.settings, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("Kept as a hash in settings.json. The check now stops on it outside Private/ and Sources/.")


def cmd_link(v, name, origin):
    """Prints the Markdown link to write in FILE for the note or file called NAME, the form GitHub opens."""
    if not origin:
        sys.exit("Say where the link goes: python3 tools/vault.py link NAME --from Knowledge/Decisions.md")
    here = (v.root / origin).resolve()
    found = [p for p in v.named(name) if v.top(p) != "Private" or v.inside(here, "Private")]
    if len(found) != 1:
        sys.exit("No note or file is called %s." % name if not found else
                 "%s could be %s; give its path, such as %s." % (name, ", ".join(v.rel(p) for p in found), v.rel(found[0])))
    target = found[0]
    path = os.path.relpath(target, here.parent).replace(os.sep, "/")
    print("[%s](<%s>)" % (target.stem if target.suffix == ".md" else target.name, path))


def relink(v, cell, from_file, to_file):
    """The links in a cell, written for a file elsewhere in the vault: the same targets, new relative paths."""
    def md(m):
        url = m.group(2).strip()
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("#"):
            return m.group(0)
        target = (from_file.parent / unquote(url.strip("<>").split("#")[0])).resolve()
        return "[%s](<%s>)" % (m.group(1), os.path.relpath(target, to_file.parent).replace(os.sep, "/"))

    def wiki(m):
        target, _, alias = m.group(1).partition("|")
        found = [f for f in v.named(target.split("#")[0]) if v.top(f) != "Private"]
        if len(found) != 1:
            return m.group(0)
        name = alias or (found[0].stem if found[0].suffix == ".md" else found[0].name)
        return "[%s](<%s>)" % (name, os.path.relpath(found[0], to_file.parent).replace(os.sep, "/"))
    return WIKILINK.sub(wiki, re.sub(r"\[([^\]]*)\]\((<[^>]+>|[^)\s]+)\)", md, cell))


def brief(v, targets, out):
    """A brief on projects and people, as Markdown: what is overdue, open and unverified, who they are, and the last
    meetings. Every line names its row and links its source, written for the file OUT."""
    owners = {r["row"].get("Owner", "").strip().lower() for r in v.rows if r["row"].get("Owner", "").strip()}
    persons = {r["id"].strip().lower(): r for r in v.rows if r["kind"] == "Person"}
    pids, people = [], []
    for target in targets:
        if target in v.projects:
            pids.append(target)
        elif target.strip().lower() in persons or target.strip().lower() in owners:
            people.append(target.strip())
        else:
            sys.exit("%s is neither a project ID nor a person in the registers." % target)
    names = {n.lower() for n in people}

    def concerns(r):
        return bool(set(v.projects_of(r)) & set(pids)) or r["row"].get("Owner", "").strip().lower() in names

    def line(r):
        row = r["row"]
        parts = ["**%s** %s" % (r["id"], row.get(r["item"], ""))]
        parts += [row["Project"]] if row.get("Project", "-").strip() not in ("", "-") else []
        parts += ["due " + row["Due"]] if row.get("Due", "").strip() else []
        parts += [row["Owner"]] if row.get("Owner", "").strip() else []
        return "- %s · %s" % (" · ".join(parts), relink(v, row.get("Source", ""), r["file"], out))

    rows = sorted((r for r in v.rows if r["kind"] == "ID" and not closed(r["row"]) and concerns(r)), key=row_key)
    late = [r for r in rows if due_of(r) and due_of(r) < today()]
    rest = [r for r in rows if r not in late]
    subject = " · ".join(["%s %s" % (pid, v.project(pid)["name"]) for pid in pids] + people)
    out_lines = ["# Brief: %s" % subject, "",
                 "Built from the vault on %s by `vault.py brief`. Every line names its row and links its source;" % today(),
                 "nothing here comes from outside the vault."]

    def block(title, found):
        out_lines.extend(["", "## %s" % title, ""] + ([line(r) for r in found] or ["- Nothing in the vault."]))
    block("Overdue", late)
    for register, title in (("Decisions", "Open decisions"), ("Actions", "Open actions"), ("Risks", "Open risks"),
                            ("Milestones", "Milestones ahead"), ("Assumptions", "Assumptions to test")):
        block(title, [r for r in rest if r["register"] == register])
    others = [r for r in rest if r["register"] not in ("Decisions", "Actions", "Risks", "Milestones", "Assumptions")]
    for heading in sorted({r["heading"] for r in others}):  # the role's own registers, and the issues
        block("Open %s" % heading.lower(), [r for r in others if r["heading"] == heading])
    block("Marked unverified", [r for r in rows if unverified(r)])
    who = [r for r in v.rows if r["kind"] == "Person" and (r["id"].strip().lower() in names or set(v.projects_of(r)) & set(pids))]
    out_lines.extend(["", "## People", ""] + (["- **%s**, %s: %s · %s" % (r["id"], r["row"].get("Role", ""),
                      r["row"].get("Interests", "") or "-", relink(v, r["row"].get("Source", ""), r["file"], out))
                      for r in sorted(who, key=lambda r: r["id"])] or ["- Nothing in the vault."]))
    met = [m for m in v.meetings if set(m["projects"]) & set(pids)
           or {str(n).strip().lower() for n in as_list(m["meta"].get("people"))} & names][:5]
    out_lines.extend(["", "## The last meetings", ""] + (["- [%s](<%s>): %s" % (m["title"], os.path.relpath(
                      m["path"], out.parent).replace(os.sep, "/"), section(v.text(m["path"]), "In short") or "-")
                      for m in met] or ["- None in the vault."]))
    return "\n".join(out_lines) + "\n"


def cmd_brief(v, targets, out):
    path = (v.root / out).resolve() if out else v.root / "Brief.md"
    text = brief(v, targets, path)
    if not out:
        print(text, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print("Wrote %s" % v.rel(path))


def main():
    args = sys.argv[1:]
    root = TOOLS.parent
    if "--vault" in args:
        i = args.index("--vault")
        root = Path(args[i + 1])
        del args[i:i + 2]
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    origin = None
    if "--from" in args and args.index("--from") + 1 < len(args):
        i = args.index("--from")
        origin = args[i + 1]
        del args[i:i + 2]
    out = None
    if "--out" in args and args.index("--out") + 1 < len(args):
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    if not args or args[0] not in ("status", "check", "refresh", "review", "next", "archive", "private-term", "link",
                                   "brief"):
        sys.exit(__doc__)
    v = Vault(root)
    cmd = args[0]
    if cmd in ("next", "archive", "private-term", "link", "brief") and len(args) < 2:
        sys.exit(__doc__)
    {"status": lambda: cmd_status(v), "check": lambda: cmd_check(v), "refresh": lambda: cmd_refresh(v),
     "review": lambda: cmd_review(v), "next": lambda: cmd_next(v, args[1]),
     "archive": lambda: cmd_archive(v, args[1], force), "private-term": lambda: cmd_private_term(v, args[1]),
     "link": lambda: cmd_link(v, args[1], origin), "brief": lambda: cmd_brief(v, args[1:], out)}[cmd]()


if __name__ == "__main__":
    main()
