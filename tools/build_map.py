#!/usr/bin/env python3
"""One page with every project: status, timeline, maps and open items. Writes build/Project map.html and a PDF of it.

    python3 tools/build_map.py           every active and on-hold project
    python3 tools/build_map.py P1 P3     only these
    python3 tools/build_map.py --all     done and archived projects too
    python3 tools/build_map.py --send P1 a map to send: no links to GitHub, no commit

Takes --vault PATH like vault.py. The page works offline in any browser: the fonts and Mermaid are inside it. Links
to notes open them on GitHub when the vault has a GitHub remote. The PDF, build/Project map.pdf, opens on a phone; it
needs Node and Playwright with its Chromium, as a Claude Code cloud session has them, and without them only the page is
built. To keep or send a map, copy it to Outputs/ with the date in front of its name.
"""
import base64
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import vault as V  # noqa: E402

THEME = {"paper": "#FFFFFF", "ink": "#1F2328", "muted": "#59636E", "rule": "#D0D7DE", "soft": "#F6F8FA",
         "accent": "#0B5FAD", "alert": "#CF222E"}
FONTS = [("Archivo", "Archivo-Regular.ttf", 400), ("Archivo", "Archivo-Bold.ttf", 700),
         ("Plex", "IBMPlexMono-Medium.ttf", 500)]
E = html.escape
MERMAID = "11.17.2"  # the version in tools/vendor/mermaid.min.js; its notices are in tools/vendor/
COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")  # the only form a colour may take: it goes into the page's style and script


def repo_url(root):
    """The vault's files on GitHub, from the git remote, or None."""
    try:
        remote = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", remote)
    if not m or not top:
        return None
    sub = Path(root).resolve().relative_to(Path(top).resolve()).as_posix()
    return "https://github.com/%s/blob/main/%s" % (m.group(1), "" if sub == "." else sub + "/")


class Page:
    def __init__(self, v, links=True):
        self.v = v
        self.base = repo_url(v.root) if links else None
        theme = v.settings.get("theme", {}) if isinstance(v.settings.get("theme"), dict) else {}
        bad = sorted(k for k, c in theme.items() if k in THEME and not COLOUR.match(str(c)))
        if bad:
            print("  colours in settings.json that are not #RRGGBB, left at their defaults: %s" % ", ".join(bad))
        self.theme = dict(THEME, **{k: c for k, c in theme.items() if k in THEME and k not in bad})

    def note(self, path, text=None):
        text = E(text if text is not None else path.stem)
        if not self.base:
            return text
        return "<a href='%s%s'>%s</a>" % (self.base, quote(self.v.rel(path)), text)

    def inline(self, md):
        """Wikilinks, Markdown links, bold, italics and code in a cell or a line."""
        out = E(md)

        def wikilink(m):
            target, _, alias = html.unescape(m.group(1)).partition("|")
            name = target.split("#")[0].split("/")[-1]
            found = next((p for p in self.v.files if p.stem == name or p.name == name), None)
            return self.note(found, alias or name) if found else E(alias or name)
        out = re.sub(r"\[\[([^\]]+)\]\]", wikilink, out)

        def mdlink(m):  # [name](<path>) or [name](path), as the registers write their sources
            text, url = m.group(1), html.unescape(m.group(2)).strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
                return "<a href='%s'>%s</a>" % (E(url), text)
            name = unquote(url).split("#")[0].split("/")[-1]
            found = next((p for p in self.v.files if p.name == name and self.v.top(p) != "Private"), None)
            return self.note(found, html.unescape(text)) if found else text
        out = re.sub(r"(?<!!)\[([^\]]+)\]\((&lt;[^)]*?&gt;|[^)\s]+)\)", mdlink, out)
        out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
        out = re.sub(r"(?<![*\w])\*([^*\s][^*]*?)\*(?![*\w])", r"<i>\1</i>", out)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", out)


def gantt(v, projects):
    """A Mermaid timeline of the dated milestones and open decisions of the projects."""
    lines = ["gantt", "    dateFormat YYYY-MM-DD", "    axisFormat %d %b", "    todayMarker on"]
    n = 0
    for p in projects:
        rows = [r for r in v.rows if p["id"] in v.projects_of(r) and V.due_of(r)
                and (r["register"] == "Milestones" or (r["register"] == "Decisions" and not V.closed(r["row"])))]
        if not rows:
            continue
        lines.append("    section %s" % re.sub(r"[:#;]", " ", "%s %s" % (p["id"], p["name"]))[:40])
        for r in sorted(rows, key=lambda r: (V.due_of(r), V.row_key(r))):
            label = re.sub(r"[:#;]", " ", "%s %s" % (r["id"], r["row"].get(r["item"], "")))
            label = label if len(label) <= 48 else label[:47].rsplit(" ", 1)[0] + "…"
            tags = ["milestone"]
            if V.closed(r["row"]):
                tags.insert(0, "done")
            elif V.due_of(r) < V.today():
                tags.insert(0, "crit")
            n += 1
            lines.append("    %s :%s, t%d, %s, 0d" % (label, ", ".join(tags), n, V.due_of(r).isoformat()))
    return "\n".join(lines) if n else ""


def open_items(page, p):
    v, out = page.v, []
    for reg in v.registers():
        rows = [r for r in v.rows if r["register"] == reg and p["id"] in v.projects_of(r) and r["kind"] == "ID" and not V.closed(r["row"])]
        if not rows:
            continue
        head = rows[0]["head"]
        extra = [c for c in ("Level", "Owner", "Due", "Status") if c in head]
        trs = []
        for r in sorted(rows, key=lambda r: (r["row"].get("Due", "") or "9999", V.row_key(r))):
            late = V.due_of(r) and V.due_of(r) < V.today()
            cells = "".join("<td%s>%s</td>" % (" class='late'" if c == "Due" and late else "", page.inline(r["row"].get(c, ""))) for c in extra)
            trs.append("<tr><td class='id'>%s</td><td>%s</td>%s</tr>" % (page.note(r["file"], r["id"]), page.inline(r["row"].get(r["item"], "")), cells))
        out.append("<h4>%s</h4><div class='scroll'><table><thead><tr><th>ID</th><th>%s</th>%s</tr></thead><tbody>%s</tbody>"
                   "</table></div>"
                   % (E(rows[0]["heading"]), E(rows[0]["item"]), "".join("<th>%s</th>" % E(c) for c in extra), "".join(trs)))
    return "".join(out) or "<p class='muted'>Nothing open in the registers.</p>"


def maps(p):
    body = V.GENERATED.sub("", p["body"])
    return re.findall(r"(?ms)^```mermaid\n(.*?)^```", body)


def build(v, wanted, include_all, send=False):
    page = Page(v, links=not send)
    projects = [found[0] for found in v.projects.values() if found]
    if wanted:
        projects = [p for p in projects if p["id"] in wanted]
    elif not include_all:
        projects = [p for p in projects if not p["archived"] and p["status"] != "done"]
    projects.sort(key=lambda p: V.pid_key(p["id"]))
    late_all, _ = V.overdue_and_soon(v)
    rows = []
    for p in projects:
        late = [r for _, r in late_all if p["id"] in v.projects_of(r)]
        rows.append("<tr><td class='id'><a href='#%s'>%s</a></td><td>%s</td><td><span class='chip %s'>%s</span></td>"
                    "<td>%s</td><td>%s</td><td>%s</td><td class='%s'>%d</td></tr>"
                    % (E(p["id"]), E(p["id"]), E(p["name"]), "on" if p["status"] == "active" else "off", E(p["status"]),
                       E(p["owner"]), page.inline(p["next"]) or "-", E(V.counts_line(v, p["id"])),
                       "late" if late else "", len(late)))
    timeline = gantt(v, projects)
    sections = []
    for p in projects:
        diagrams = "".join("<div class='diagram'><pre class='mermaid'>%s</pre></div>" % E(m) for m in maps(p))
        meetings = [m for m in v.meetings if p["id"] in m["projects"]][:5]
        sections.append(
            "<section id='%s'><h2><span class='pid'>%s</span> %s <span class='chip %s'>%s</span></h2>"
            "<p class='meta'>Owner %s · card %s</p><dl><dt>Goal</dt><dd>%s</dd><dt>Next step</dt><dd>%s</dd></dl>%s"
            "<h3>Open</h3>%s<h3>Latest meetings</h3>%s</section>"
            % (E(p["id"]), E(p["id"]), E(p["name"]), "on" if p["status"] == "active" else "off", E(p["status"]), E(p["owner"]),
               page.note(p["path"], p["path"].name), page.inline(p["goal"]) or "-", page.inline(p["next"]) or "-",
               diagrams, open_items(page, p),
               "<ul>%s</ul>" % "".join("<li>%s</li>" % page.note(m["path"], m["title"]) for m in meetings) if meetings
               else "<p class='muted'>None yet.</p>"))
    faces = "".join("@font-face{font-family:%s;src:url(data:font/ttf;base64,%s);font-weight:%d}" % (
        fam, base64.b64encode((TOOLS / "fonts" / f).read_bytes()).decode(), w) for fam, f, w in FONTS)
    t = page.theme
    asof = V.today().isoformat()
    try:
        commit = "" if send else subprocess.run(["git", "-C", str(v.root), "log", "-1", "--format=%h"],
                                                capture_output=True, text=True).stdout.strip()
        asof += " · commit " + commit if commit else ""
    except Exception:
        pass
    doc = TEMPLATE % {
        "fonts": faces, "title": E(v.settings.get("title", "Executive Brain")), "asof": E(asof),
        "paper": t["paper"], "ink": t["ink"], "muted": t["muted"], "rule": t["rule"], "soft": t["soft"],
        "accent": t["accent"], "alert": t["alert"],
        "nav": "".join("<a href='#%s'>%s</a>" % (E(p["id"]), E("%s %s" % (p["id"], p["name"]))) for p in projects),
        "rows": "".join(rows) or "<tr><td colspan='7' class='muted'>No projects.</td></tr>",
        "timeline": "<h2>Timeline</h2><div class='diagram timeline'><pre class='mermaid'>%s</pre></div>" % E(timeline)
                    if timeline else "",
        "sections": "".join(sections), "footer": E(v.settings.get("footer", "")),
        "mermaid": (TOOLS / "vendor" / "mermaid.min.js").read_text(encoding="utf-8"), "mermaid_version": MERMAID,
        "mtheme": json.dumps({"primaryColor": t["paper"], "primaryBorderColor": t["ink"], "primaryTextColor": t["ink"],
                              "lineColor": t["muted"], "secondaryColor": t["soft"], "tertiaryColor": t["soft"],
                              "fontFamily": "Archivo", "taskBkgColor": t["accent"], "critBkgColor": t["alert"],
                              "doneTaskBkgColor": t["muted"], "todayLineColor": t["alert"]}),
    }
    out = v.root / "build" / "Project map.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    made = [out.relative_to(v.root).as_posix()]
    if pdf(out):
        made.append(out.with_suffix(".pdf").relative_to(v.root).as_posix())
    print("Built %s: %d projects%s%s" % (" and ".join(made), len(projects), ", a timeline" if timeline else "",
                                         ", without links, to send" if send else ""))
    return out


def pdf(page):
    """The page printed to an A4 PDF next to it, once its diagrams are drawn. False when Node or Playwright is missing."""
    target = page.with_suffix(".pdf")
    try:
        subprocess.run(["node", str(TOOLS / "render.js"), "pdf", str(page), str(target)], check=True,
                       capture_output=True, text=True, timeout=300)
        return True
    except Exception as e:
        text = str(getattr(e, "stderr", "") or e).strip()
        print("  the PDF is not built (%s); the page is" % (text.splitlines()[-1][:120] if text else type(e).__name__))
        target.unlink(missing_ok=True)  # never leave an older PDF next to a newer page
        return False


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Project map · %(title)s</title>
<style>
%(fonts)s
:root { --paper: %(paper)s; --ink: %(ink)s; --muted: %(muted)s; --rule: %(rule)s; --soft: %(soft)s; --accent: %(accent)s;
        --alert: %(alert)s; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 400 15px/1.5 Archivo, system-ui, sans-serif; }
.wrap { max-width: 1160px; margin: 0 auto; padding: 36px 28px 60px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 14px; margin-bottom: 18px; }
.eyebrow { font: 500 11px Plex, monospace; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); margin: 0; }
h1 { font-size: 34px; line-height: 1.1; margin: 6px 0 0; }
h2 { font-size: 22px; margin: 34px 0 10px; }
h3 { font: 500 11px Plex, monospace; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); margin: 22px 0 8px; }
h4 { font-size: 14px; margin: 14px 0 6px; }
nav { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; }
nav a { font: 500 12px Plex, monospace; padding: 4px 8px; border: 1px solid var(--rule); color: var(--ink); text-decoration: none; }
nav a:hover { border-color: var(--accent); color: var(--accent); }
a { color: var(--accent); }
table { border-collapse: collapse; width: 100%%; font-size: 13.5px; margin: 4px 0 10px; }
th { text-align: left; font: 500 10.5px Plex, monospace; letter-spacing: .1em; text-transform: uppercase; color: var(--muted);
     border-bottom: 1.5px solid var(--ink); padding: 6px 8px; }
td { border-bottom: 1px solid var(--rule); padding: 7px 8px; vertical-align: top; }
td.id { font: 500 12.5px Plex, monospace; white-space: nowrap; }
.late { color: var(--alert); font-weight: 700; }
.chip { font: 500 10.5px Plex, monospace; letter-spacing: .08em; text-transform: uppercase; padding: 2px 7px; border: 1px solid; vertical-align: middle; }
.chip.on { color: var(--accent); border-color: var(--accent); }
.chip.off { color: var(--muted); border-color: var(--rule); }
section { border-top: 1px solid var(--rule); margin-top: 30px; }
.pid { font: 500 18px Plex, monospace; color: var(--accent); }
.meta, .muted { color: var(--muted); }
dl { display: grid; grid-template-columns: 110px 1fr; gap: 4px 14px; margin: 10px 0; }
dt { font: 500 11px Plex, monospace; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); padding-top: 3px; }
dd { margin: 0; }
.diagram { background: var(--soft); border: 1px solid var(--rule); padding: 14px; margin: 12px 0; overflow-x: auto; }
.diagram pre { margin: 0; background: none; }
.diagram .grid .tick line { stroke: var(--rule); }
.diagram.timeline pre { min-width: 760px; }  /* narrower, the labels would cross the project names: it scrolls */
.scroll { overflow-x: auto; }
.scroll.wide table { min-width: 720px; }
code { font: 500 12.5px Plex, monospace; background: var(--soft); padding: 0 3px; }
footer { margin-top: 48px; padding-top: 10px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 12px;
         display: flex; justify-content: space-between; }
@media (max-width: 600px) { .wrap { padding: 20px 14px 40px; } h1 { font-size: 26px; } dl { grid-template-columns: 1fr; } }
@page { size: A4; margin: 14mm 12mm; }
@media print { .wrap { padding: 0; } nav { display: none; } h2, h3, h4 { break-after: avoid; } tr, .diagram { break-inside: avoid; }
               .scroll { overflow: visible; } .scroll.wide table, .diagram.timeline pre { min-width: 0; } }
</style>
<!-- Mermaid %(mermaid_version)s, MIT, and the packages it bundles, under MIT, ISC, BSD-3-Clause, Apache-2.0,
     MPL-2.0 or Apache-2.0, and the Unlicense: their notices are in tools/vendor/LICENSE-mermaid.txt and
     tools/vendor/THIRD-PARTY-NOTICES.txt of Executive Brain, https://github.com/piotrmechlinski/executive-brain.
     The fonts, Archivo and IBM Plex Mono, are under the SIL Open Font Licence 1.1. -->
<script>%(mermaid)s</script>
</head><body><div class="wrap">
<header><p class="eyebrow">Project map · %(asof)s</p><h1>%(title)s</h1></header>
<nav>%(nav)s</nav>
<h2>Projects</h2>
<div class="scroll wide"><table><thead><tr><th>ID</th><th>Project</th><th>Status</th><th>Owner</th><th>Next step</th><th>Open</th>
<th>Overdue</th></tr></thead><tbody>%(rows)s</tbody></table></div>
%(timeline)s
%(sections)s
<footer><span>%(footer)s</span><span>Built from the vault, %(asof)s</span></footer>
</div>
<script>
mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables: %(mtheme)s,
  flowchart: { htmlLabels: true, curve: "basis" },
  gantt: { barHeight: 18, fontSize: 12, sectionFontSize: 12, leftPadding: 180, rightPadding: 20 } });
document.fonts.ready.then(() => mermaid.run({ querySelector: ".mermaid", suppressErrors: true }))
  .finally(() => { window.__ready = true; });  // a diagram that fails shows its error; the others are drawn
</script>
</body></html>
"""


def main():
    args = sys.argv[1:]
    root = TOOLS.parent
    if "--vault" in args:
        i = args.index("--vault")
        root = Path(args[i + 1])
        del args[i:i + 2]
    include_all, send = "--all" in args, "--send" in args
    wanted = [a for a in args if re.match(r"^P\d+$", a)]
    build(V.Vault(root), wanted, include_all, send)


if __name__ == "__main__":
    main()
