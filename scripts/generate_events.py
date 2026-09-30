#!/usr/bin/env python3
"""Collect upcoming nuclear-sector events from the pages in scripts/event_sources.yml.

Fetches each page as text, asks Claude to extract the events it explicitly
lists (with country and city), and merges them into _data/events.json, which
the /events/ page, the calendar feed and the map render. Existing entries are
kept untouched so manual edits and hand-added events survive; events that ended
more than RETENTION_DAYS ago are dropped.

Usage:
    ANTHROPIC_API_KEY=... python scripts/generate_events.py
    python scripts/generate_events.py --dry-run   # fetch pages, no API call
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "scripts" / "event_sources.yml"
COUNTRIES_FILE = ROOT / "_data" / "countries.yml"
EVENTS_FILE = ROOT / "_data" / "events.json"

MODEL = os.environ.get("NEWSBLOG_MODEL", "claude-sonnet-5-5")
PAGE_CHARS = 20000     # per-page cap sent to the model
RETENTION_DAYS = 90    # keep finished events this long (shown under "recently past")
TYPES = ["conference", "summer-school", "training", "technical-visit", "lecture", "contest", "social"]
FIELDS = ("title", "type", "start_date", "end_date", "country", "city", "location",
          "organizer", "summary", "url", "deadline", "source")
# Some sites reject one style of user agent and accept the other; try both.
UAS = [
    "Mozilla/5.0 (compatible; NuclearNewswireBot/1.0)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 NuclearNewswireBot/1.0",
]


def load_country_codes() -> list[str]:
    rows = yaml.safe_load(COUNTRIES_FILE.read_text(encoding="utf-8"))
    return [r["code"] for r in rows] + ["ONLINE", "UNKNOWN"]


COUNTRY_CODES = load_country_codes()

SYSTEM_PROMPT = """You maintain the events calendar of "Nuclear Newswire", a
nuclear-sector blog. You receive the text of event/news pages from nuclear
organisations, in any language (links appear as [text](url)). Extract UPCOMING
events of these types:
- conference: conferences, symposia, congresses, expos and meetings
- summer-school: summer/winter schools, PhD/academic schools, courses run as a school
- training: trainings, courses, workshops, webinars with a learning goal
- technical-visit: site visits, facility tours, technical visits
- lecture: evening lectures, seminars, colloquia and talks
- contest: science contests, competitions and quizzes with a scientific angle
- social: networking, fun and community events (drinks, "Nuclear Cafes", sports, get-togethers)
Skip anything already past, anything without a clear date, and pure
announcements that are not events (calls, news, job ads).

Rules:
- Use only facts stated on the page. Never invent dates, places or URLs.
- Write title and summary in English (translate if the page is in another language).
- start_date / end_date are ISO YYYY-MM-DD (end_date = start_date for one day;
  if only a month is given, skip the event).
- country: ISO 3166-1 alpha-2 code of the place it happens (BE, FR, GB, US...),
  ONLINE for virtual events, UNKNOWN only if truly unclear. If the listing gives
  no place and the source has a default country, use that. city: the city, or ''.
- location: the venue/city text as printed, or ''.
- deadline: registration or abstract deadline (YYYY-MM-DD) if the page states one, else ''.
- url must be a link that appears in the page text and points to the event
  (or, if none, the page it was found on). Prefer the specific event page.
- summary: one plain sentence in your own words (what, for whom).
- Do not list the same event twice."""

EVENTS_TOOL = {
    "name": "record_events",
    "description": "Submit the extracted upcoming events.",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "type": {"type": "string", "enum": TYPES},
                        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "country": {"type": "string", "enum": COUNTRY_CODES},
                        "city": {"type": "string"},
                        "location": {"type": "string"},
                        "organizer": {"type": "string"},
                        "summary": {"type": "string"},
                        "url": {"type": "string"},
                        "deadline": {"type": "string", "description": "YYYY-MM-DD or empty"},
                        "source": {"type": "string", "description": "Name of the source page it came from."},
                    },
                    "required": ["title", "type", "start_date", "end_date", "country", "city",
                                 "organizer", "summary", "url", "source"],
                },
            }
        },
        "required": ["events"],
    },
}


class _TextExtractor(HTMLParser):
    """HTML -> plain text, keeping links as [text](absolute-url)."""

    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "article", "section"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.out: list[str] = []
        self.skip = 0
        self.href: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "a" and not self.skip:
            href = dict(attrs).get("href")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                self.href = urljoin(self.base, href)
                self.out.append("[")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "a" and self.href:
            self.out.append(f"]({self.href})")
            self.href = None

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def fetch_text(url: str) -> str:
    for i, ua in enumerate(UAS):
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                html = r.read().decode(charset, errors="replace")
            break
        except (urllib.error.URLError, TimeoutError):  # HTTPError is a URLError
            if i == len(UAS) - 1:
                raise
    p = _TextExtractor(url)
    p.feed(html)
    text = "".join(p.out)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def load_events() -> list[dict]:
    if EVENTS_FILE.exists():
        return json.loads(EVENTS_FILE.read_text(encoding="utf-8-sig") or "[]")
    return []


def event_key(e: dict) -> str:
    return e["url"].rstrip("/").lower() if e.get("url") else f"{e['title'].lower()}|{e['start_date']}"


def valid(e: dict) -> bool:
    try:
        start = date.fromisoformat(e["start_date"])
        end = date.fromisoformat(e["end_date"])
    except (KeyError, ValueError):
        return False
    if e.get("deadline"):
        try:
            date.fromisoformat(e["deadline"])
        except ValueError:
            e["deadline"] = ""
    return (e.get("type") in TYPES and bool(e.get("title")) and end >= start
            and e.get("country", "UNKNOWN") in COUNTRY_CODES
            and str(e.get("url", "")).startswith("http"))


def extract_events(pages: list[dict]) -> list[dict]:
    import anthropic

    def head(p):
        hint = f", default country: {p['default_country']}" if p.get("default_country") else ""
        return f"===== SOURCE: {p['name']} ({p['url']}{hint}) ====="

    body = "\n\n".join(f"{head(p)}\n{p['text']}" for p in pages)
    user_msg = (
        f"Today is {datetime.now(timezone.utc):%Y-%m-%d}. Extract the upcoming events from "
        f"the pages below. You must respond by calling record_events (empty list if none).\n\n{body}"
    )
    resp = anthropic.Anthropic().messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[EVENTS_TOOL],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": user_msg}],
    )
    print(f"tokens: {resp.usage.input_tokens} in, {resp.usage.output_tokens} out")
    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_events":
            return block.input.get("events", [])
    raise RuntimeError("Model did not return events")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="fetch pages and show sizes, don't call the API")
    args = ap.parse_args()

    cfg = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))
    defaults = {s["name"]: s.get("default_country") for s in cfg.get("sources", [])}
    pages = []
    for s in cfg.get("sources", []):
        if s.get("enabled", True) is False:
            continue
        try:
            text = fetch_text(s["url"])
        except Exception as exc:  # network errors, 403s, bad encodings: skip the source
            print(f"warning: could not read {s['name']} ({s['url']}): {exc}", file=sys.stderr)
            continue
        print(f"{s['name']}: {len(text)} characters")
        pages.append({"name": s["name"], "url": s["url"], "text": text[:PAGE_CHARS],
                      "default_country": s.get("default_country")})
    if args.dry_run:
        return 0
    if not pages:
        print("No pages could be read.", file=sys.stderr)
        return 1

    today = date.today()
    existing = load_events()
    # Entries from before countries existed: fill from the source's home country.
    for e in existing:
        e.setdefault("country", defaults.get(e.get("source")) or "UNKNOWN")
        e.setdefault("city", "")
        e.setdefault("deadline", "")
        e.setdefault("location", "")
    known = {event_key(e) for e in existing}
    added, per_source = 0, Counter()
    for e in extract_events(pages):
        per_source[e.get("source", "?")] += 1
        if e.get("country") in ("", None):
            e["country"] = defaults.get(e.get("source")) or "UNKNOWN"
        if not valid(e) or e["end_date"] < today.isoformat() or event_key(e) in known:
            continue
        existing.append({k: e.get(k, "") for k in FIELDS})
        known.add(event_key(e))
        print(f"+ {e['start_date']} [{e['type']}] {e['country']} {e['title']}")
        added += 1

    # Feed health: a source that used to work and now yields nothing is worth a look.
    for p in pages:
        if per_source[p["name"]] == 0:
            print(f"note: no events extracted from {p['name']}", file=sys.stderr)

    cutoff = (today - timedelta(days=RETENTION_DAYS)).isoformat()
    kept = sorted((e for e in existing if e["end_date"] >= cutoff),
                  key=lambda e: (e["start_date"], e["title"]))
    EVENTS_FILE.parent.mkdir(exist_ok=True)
    EVENTS_FILE.write_text(json.dumps(kept, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    upcoming = sum(e["end_date"] >= today.isoformat() for e in kept)
    print(f"{added} new event(s); {upcoming} upcoming, {len(kept) - upcoming} recently past")
    return 0


if __name__ == "__main__":
    sys.exit(main())
