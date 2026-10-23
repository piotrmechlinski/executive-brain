#!/usr/bin/env python3
"""Writes tools/vendor/THIRD-PARTY-NOTICES.txt: the licences of the packages bundled in tools/vendor/mermaid.min.js.

    python3 tools/vendor/make_notices.py 11.17.2

For the maintainers of Executive Brain, after a new Mermaid is vendored; a vault never needs it. It reads the npm
registry: Mermaid's dependencies, resolved to the newest versions published before that Mermaid release, as its build
would have found them, and the licence file of each. Type packages (@types/*) are left out: they are not in the bundle.
Standard library only; set SSL_CERT_FILE if a proxy signs the registry's certificate.
"""
import io
import json
import re
import ssl
import sys
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import quote

VENDOR = Path(__file__).resolve().parent
REGISTRY = "https://registry.npmjs.org/"
LICENCE_FILE = re.compile(r"^package/(licen[cs]e|copying)(\.(md|txt|markdown))?$", re.I)
CONTEXT = ssl.create_default_context()
# Packages whose own build holds some of their development dependencies, so that npm does not list them as
# dependencies, though their code is in the bundle: Mermaid's parser carries langium and chevrotain.
BUILT_IN = {"@mermaid-js/parser": ("langium", "chevrotain")}
_docs = {}


def fetch(url):
    with urllib.request.urlopen(url, context=CONTEXT, timeout=60) as r:
        return r.read()


def doc(name):
    if name not in _docs:
        _docs[name] = json.loads(fetch(REGISTRY + quote(name, safe="@")))
    return _docs[name]


def version_key(v):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v)
    return tuple(int(x) for x in m.groups()) if m else None


def satisfies(v, spec):
    """npm's ranges as Mermaid's tree uses them: ^, ~, >=, <, x, exact, and || between alternatives."""
    t = version_key(v)
    if t is None:
        return False
    for alt in spec.split("||"):
        ok = True
        alt = re.sub(r"(>=|<=|>|<|=|\^|~)\s+", r"\1", alt)  # ">= 2.1.2" is ">=2.1.2"
        if " - " in alt:  # a hyphen range: "1 - 2" is >=1.0.0 and <3.0.0
            lo, hi = (s.strip().split(".") for s in alt.split(" - "))
            hi_parts = [int(x) for x in hi if x.isdigit()]
            top = tuple(hi_parts) + (0,) * (3 - len(hi_parts))
            if len(hi_parts) < 3:
                top = tuple(hi_parts[:-1]) + (hi_parts[-1] + 1,) + (0,) * (3 - len(hi_parts))
                below = t < top
            else:
                below = t <= top
            low = tuple(int(x) for x in lo if x.isdigit()) + (0,) * (3 - len([x for x in lo if x.isdigit()]))
            if low <= t and below:
                return True
            continue
        for part in alt.split() or ["*"]:
            if part in ("*", "x", "latest"):
                continue
            m = re.match(r"^(\^|~|>=|<=|>|<|=)?v?(\d+)(?:\.(\d+|x|\*))?(?:\.(\d+|x|\*))?$", part)
            if not m:
                ok = False
                break
            op, a, b, c = m.group(1) or "", int(m.group(2)), m.group(3), m.group(4)
            bx, cx = b in (None, "x", "*"), c in (None, "x", "*")
            base = (a, 0 if bx else int(b), 0 if cx else int(c))
            if op == "^":
                top = (a + 1, 0, 0) if a else ((0, base[1] + 1, 0) if base[1] else (0, 0, base[2] + 1))
                ok = base <= t < top
            elif op == "~":
                ok = base <= t < ((a + 1, 0, 0) if bx else (a, base[1] + 1, 0))
            elif op in (">=", ">", "<", "<="):
                ok = {">=": t >= base, ">": t > base, "<": t < base, "<=": t <= base}[op]
            else:
                ok = t[0] == a if bx else (t[:2] == base[:2] if cx else t == base)
            if not ok:
                break
        if ok:
            return True
    return False


def resolve(name, spec, cutoff):
    d = doc(name)
    found = [v for v in d["versions"] if satisfies(v, spec) and d["time"].get(v, "9") < cutoff]
    return max(found, key=version_key) if found else None


def licence_of(meta):
    lic = meta.get("license") or meta.get("licenses") or "not stated"
    if isinstance(lic, dict):
        lic = lic.get("type", "not stated")
    if isinstance(lic, list):
        lic = " or ".join(x.get("type", "?") if isinstance(x, dict) else str(x) for x in lic)
    return str(lic)


def licence_text(meta):
    data = fetch(meta["dist"]["tarball"])
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile() and LICENCE_FILE.match(member.name):
                return tar.extractfile(member).read().decode("utf-8", "replace").strip()
    return None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    version = sys.argv[1]
    mermaid = doc("mermaid")
    cutoff = mermaid["time"][version]
    seen, todo = {}, sorted(mermaid["versions"][version]["dependencies"].items())
    while todo:
        name, spec = todo.pop(0)
        if name.startswith("@types/"):
            continue
        v = resolve(name, spec, cutoff)
        if v is None:
            sys.exit("%s@%s: no version published before %s" % (name, spec, cutoff))
        if (name, v) in seen:
            continue
        meta = doc(name)["versions"][v]
        seen[(name, v)] = meta
        todo += sorted((meta.get("dependencies") or {}).items())
        dev = meta.get("devDependencies") or {}
        todo += [(d, dev[d]) for d in BUILT_IN.get(name, ()) if d in dev]
    rows, texts = [], []
    for (name, v), meta in sorted(seen.items()):
        text = licence_text(meta)
        holder = next((line.strip() for line in (text or "").splitlines()
                       if re.match(r"\s*(copyright\b|\(c\)\s*\d|©)", line, re.I)
                       and not re.search(r"\[yyyy\]|copyright (notice|license|owner|statement)", line, re.I)), "")
        lic = licence_of(meta)
        if lic == "not stated" and text and "Permission is hereby granted, free of charge" in text:
            lic = "MIT, by its licence file"
        rows.append("- %s@%s, %s%s" % (name, v, lic, "; " + holder if holder else ""))
        texts.append("=== %s@%s ===\n\n%s" % (name, v, text or "The package has no licence file. Its licence, as the "
                                              "package states it: %s." % licence_of(meta)))
    head = """Third-party notices for tools/vendor/mermaid.min.js

mermaid.min.js is the standalone build of Mermaid %s, copied unchanged from its npm package. Mermaid's own licence
(MIT) is in LICENSE-mermaid.txt next to this file. The build bundles packages from Mermaid's dependency tree. This
file gives the licence of every package in that tree, %d of them, a few more than a browser build holds. The
versions are the newest that matched before Mermaid %s was published (%s), and their licence texts are
the ones below. The bundle names few versions itself; DOMPurify's, 3.4.12, is earlier than the one listed.
Every project map built by tools/build_map.py carries this code, and so these notices apply to it too.

Rebuilt with: python3 tools/vendor/make_notices.py %s

The packages
""" % (version, len(rows), version, cutoff[:10], version)
    out = head + "\n".join(rows) + "\n\nThe licence texts\n\n" + "\n\n".join(texts) + "\n"
    (VENDOR / "THIRD-PARTY-NOTICES.txt").write_text(out, encoding="utf-8")
    print("Wrote THIRD-PARTY-NOTICES.txt: %d packages" % len(rows))


if __name__ == "__main__":
    main()
