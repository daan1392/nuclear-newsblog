#!/usr/bin/env python3
"""Sanity-check _data/events.json: required fields, valid dates, known country
codes and types, http(s) URLs, no duplicates. Exit code 1 on any problem.

Used by CI on pull requests and as the gate for optional auto-merge.
"""
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TYPES = {"conference", "summer-school", "training", "technical-visit", "lecture", "contest", "social"}
REQUIRED = ("title", "type", "start_date", "end_date", "country", "organizer", "summary", "url")


def main() -> int:
    countries = {c["code"] for c in yaml.safe_load((ROOT / "_data" / "countries.yml").read_text(encoding="utf-8"))}
    countries |= {"ONLINE", "UNKNOWN"}
    events = json.loads((ROOT / "_data" / "events.json").read_text(encoding="utf-8") or "[]")
    errors, seen = [], set()
    for i, e in enumerate(events):
        name = f"#{i} {str(e.get('title', '?'))[:50]}"
        for key in REQUIRED:
            if not e.get(key):
                errors.append(f"{name}: missing '{key}'")
        if e.get("type") not in TYPES:
            errors.append(f"{name}: unknown type '{e.get('type')}'")
        if e.get("country") not in countries:
            errors.append(f"{name}: unknown country '{e.get('country')}'")
        for key in ("start_date", "end_date", "deadline"):
            if e.get(key):
                try:
                    date.fromisoformat(e[key])
                except ValueError:
                    errors.append(f"{name}: bad {key} '{e[key]}'")
        if e.get("start_date") and e.get("end_date") and e["end_date"] < e["start_date"]:
            errors.append(f"{name}: ends before it starts")
        if not str(e.get("url", "")).startswith(("http://", "https://")):
            errors.append(f"{name}: url must start with http(s)")
        key = str(e.get("url", "")).rstrip("/").lower()
        if key in seen:
            errors.append(f"{name}: duplicate url")
        seen.add(key)
    for err in errors:
        print(err)
    print(f"{len(events)} event(s) checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
