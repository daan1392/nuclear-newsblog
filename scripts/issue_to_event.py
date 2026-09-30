#!/usr/bin/env python3
"""Turn a submitted "Submit an event" issue into an entry in _data/events.json.

Reads the issue body from the ISSUE_BODY environment variable (never from the
command line, since it is untrusted user text). The result is checked by
validate_events.py and reviewed in a pull request before it is published.
"""
import json
import os
import re
import sys
from pathlib import Path

EVENTS_FILE = Path(__file__).resolve().parent.parent / "_data" / "events.json"
FIELDS = ["title", "type", "start_date", "end_date", "country", "city", "organizer", "url", "deadline", "summary"]
LABELS = {  # issue-form label -> field
    "Title": "title", "Type": "type", "Start date": "start_date", "End date": "end_date",
    "Country code": "country", "City": "city", "Organiser": "organizer",
    "Link to the event page": "url", "Registration or abstract deadline (optional)": "deadline",
    "One-sentence description": "summary",
}


def parse(body: str) -> dict:
    ev = {f: "" for f in FIELDS}
    for label, value in re.findall(r"###\s+(.+?)\s*\n+(.*?)(?=\n###\s|\Z)", body, re.S):
        field = LABELS.get(label.strip())
        if field:
            v = value.strip()
            ev[field] = "" if v == "_No response_" else " ".join(v.split())
    ev["country"] = ev["country"].upper()
    return ev


def main() -> int:
    ev = parse(os.environ.get("ISSUE_BODY", ""))
    ev["location"] = ev["city"]
    ev["source"] = "Community submission"
    events = json.loads(EVENTS_FILE.read_text(encoding="utf-8-sig") or "[]")
    if any(e["url"].rstrip("/").lower() == ev["url"].rstrip("/").lower() for e in events):
        print("Already listed.")
        return 0
    events.append(ev)
    events.sort(key=lambda e: (e["start_date"], e["title"]))
    EVENTS_FILE.write_text(json.dumps(events, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added: {ev['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
