#!/usr/bin/env python3
"""Sanity-check posts in _posts/ — run on every pull request.

Fails if a post is missing required front matter, has no source links,
or contains an obviously long verbatim-looking quote.
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("title", "date", "categories", "sources")
NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")


def check(path: Path) -> list[str]:
    errs = []
    if not NAME_RE.match(path.name):
        errs.append("filename must look like YYYY-MM-DD-slug.md")
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return errs + ["missing YAML front matter"]
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        return errs + [f"invalid YAML: {e}"]
    body = m.group(2)
    for key in REQUIRED:
        if not fm.get(key):
            errs.append(f"front matter missing '{key}'")
    for s in fm.get("sources") or []:
        if not str(s.get("url", "")).startswith("http"):
            errs.append(f"source without a valid url: {s}")
    words = len(re.findall(r"\w+", body))
    if words < 80:
        errs.append(f"body too short ({words} words)")
    for q in re.findall(r"[\"“]([^\"”]+)[\"”]", body):
        if len(q.split()) >= 25:
            errs.append(f"long quotation ({len(q.split())} words) — paraphrase instead")
    return errs


def main() -> int:
    failed = False
    for path in sorted((ROOT / "_posts").glob("*.md")):
        for err in check(path):
            print(f"{path.name}: {err}")
            failed = True
    print("All posts OK" if not failed else "Validation failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
