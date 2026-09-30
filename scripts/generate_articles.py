#!/usr/bin/env python3
"""Generate AI-written nuclear-sector news briefs from RSS/Atom feeds.

Reads scripts/feeds.yml, collects recent items that haven't been covered yet,
asks Claude to pick the most newsworthy distinct stories and write an original
brief for each, then writes Jekyll posts to _posts/ and records the source URLs
in _data/seen.json so they aren't covered twice.

Usage:
    ANTHROPIC_API_KEY=... python scripts/generate_articles.py
    python scripts/generate_articles.py --dry-run   # list candidates, no API call
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = ROOT / "scripts" / "feeds.yml"
SEEN_FILE = ROOT / "_data" / "seen.json"
POSTS_DIR = ROOT / "_posts"

MODEL = os.environ.get("NEWSBLOG_MODEL", "claude-sonnet-5-5")
SEEN_LIMIT = 5000  # keep the dedup list from growing forever

SYSTEM_PROMPT = """You are the editor of "Nuclear Newswire", a news blog covering the
nuclear sector: power reactors and SMRs, fuel cycle and waste, fusion, research
reactors and nuclear science, regulation and policy, safety, and the industry.

You receive a list of recent news items (headline, outlet, link, feed summary).
Your job:
1. Choose the most newsworthy DISTINCT stories (merge items from different
   outlets that cover the same event into one article). Skip press-release
   fluff, event announcements, job ads and anything off-topic.
2. For each chosen story, write an original news brief of 150-350 words.

Rules for every brief:
- Write entirely in your own words. Never copy sentences from the summaries;
  at most one short quote (under 15 words) per article, attributed.
- Use only facts present in the supplied items. Do not invent numbers, dates,
  names or quotes. If something is unclear, say less rather than guess.
- Neutral, factual tone for a technically literate audience. Explain jargon
  briefly on first use.
- Structure: a one-sentence lede, then 2-4 short paragraphs of context and
  significance. No headings inside the body. Markdown allowed for emphasis
  and links.
- Every article must list the source item links it is based on."""

PUBLISH_TOOL = {
    "name": "publish_articles",
    "description": "Submit the finished briefs for editorial review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "articles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Headline, max ~90 chars."},
                        "summary": {"type": "string", "description": "One-sentence teaser for the index page."},
                        "category": {
                            "type": "string",
                            "enum": ["Reactors", "Fuel cycle", "Fusion", "Research",
                                     "Policy", "Regulation", "Safety", "Industry"],
                        },
                        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                        "body": {"type": "string", "description": "Markdown body, no title, no sources list."},
                        "source_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "IDs of the input items this article is based on.",
                        },
                    },
                    "required": ["title", "summary", "category", "tags", "body", "source_ids"],
                },
            }
        },
        "required": ["articles"],
    },
}


# ---------------------------------------------------------------- helpers
def load_config() -> dict:
    with FEEDS_FILE.open() as f:
        return yaml.safe_load(f)


def load_seen() -> list[str]:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text() or "[]")
    return []


def save_seen(seen: list[str]) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen[-SEEN_LIMIT:], indent=1) + "\n")


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slugify(text: str, maxlen: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:maxlen].rstrip("-") or "article"


def entry_time(entry) -> float | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return calendar.timegm(t)
    return None


# ---------------------------------------------------------------- pipeline
def collect_items(cfg: dict, seen: set[str]) -> list[dict]:
    max_age = cfg.get("max_age_hours", 48) * 3600
    now = time.time()
    items: list[dict] = []
    for feed in cfg.get("feeds", []):
        if feed.get("enabled", True) is False:
            continue
        parsed = feedparser.parse(feed["url"], agent="NuclearNewswireBot/1.0")
        if parsed.bozo and not parsed.entries:
            print(f"warning: could not read {feed['name']} ({feed['url']}): "
                  f"{parsed.get('bozo_exception')}", file=sys.stderr)
            continue
        kept = 0
        for e in parsed.entries:
            link = e.get("link")
            if not link or link in seen:
                continue
            ts = entry_time(e)
            if ts is not None and now - ts > max_age:
                continue
            items.append({
                "outlet": feed["name"],
                "title": clean_html(e.get("title", "")),
                "link": link,
                "published": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
                "summary": clean_html(e.get("summary", ""))[:1200],
            })
            kept += 1
        print(f"{feed['name']}: {kept} new item(s)")
    for i, item in enumerate(items):
        item["id"] = i
    return items


def write_articles(items: list[dict], max_articles: int) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic()
    listing = json.dumps(
        [{k: it[k] for k in ("id", "outlet", "title", "link", "published", "summary")} for it in items],
        indent=1, ensure_ascii=False,
    )
    user_msg = (
        f"Today is {datetime.now(timezone.utc):%Y-%m-%d}. Here are {len(items)} recent items. "
        f"Write at most {max_articles} briefs (fewer is fine if little is newsworthy; "
        f"zero if nothing is). You must respond by calling the publish_articles tool (with an empty list if nothing qualifies).\n\n{listing}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        tools=[PUBLISH_TOOL],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": user_msg}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "publish_articles":
            return block.input.get("articles", [])[:max_articles]
    raise RuntimeError("Model did not return articles")


def yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # JSON strings are valid YAML scalars


def render_post(article: dict, sources: list[dict], now: datetime) -> str:
    tags = ", ".join(yaml_str(t) for t in article.get("tags", []))
    src_yaml = "\n".join(
        f"  - title: {yaml_str(s['title'])}\n    outlet: {yaml_str(s['outlet'])}\n    url: {yaml_str(s['link'])}"
        for s in sources
    )
    src_md = "\n".join(f"- [{s['title']}]({s['link']}) — *{s['outlet']}*" for s in sources)
    return f"""---
layout: post
title: {yaml_str(article['title'])}
date: {now:%Y-%m-%d %H:%M:%S} +0000
categories: [{yaml_str(article['category'])}]
tags: [{tags}]
excerpt: {yaml_str(article['summary'])}
ai_generated: true
model: {MODEL}
sources:
{src_yaml}
---

{article['body'].strip()}

---

**Sources**

{src_md}

<small>*This brief was written by an AI model from the sources above and reviewed before publication. Check the originals before relying on specific figures.*</small>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list candidate items, don't call the API")
    args = ap.parse_args()

    cfg = load_config()
    seen = load_seen()
    items = collect_items(cfg, set(seen))
    print(f"{len(items)} candidate item(s) in total")

    if args.dry_run:
        for it in items:
            print(f"  [{it['id']}] {it['outlet']}: {it['title']}")
        return 0
    if not items:
        print("Nothing new — no PR needed.")
        return 0

    articles = write_articles(items, cfg.get("max_articles", 5))
    now = datetime.now(timezone.utc)
    POSTS_DIR.mkdir(exist_ok=True)
    by_id = {it["id"]: it for it in items}
    written = 0
    for art in articles:
        sources = [by_id[i] for i in art.get("source_ids", []) if i in by_id]
        if not sources:
            print(f"skipping '{art.get('title')}': no valid sources", file=sys.stderr)
            continue
        path = POSTS_DIR / f"{now:%Y-%m-%d}-{slugify(art['title'])}.md"
        n = 2
        while path.exists():
            path = POSTS_DIR / f"{now:%Y-%m-%d}-{slugify(art['title'])}-{n}.md"
            n += 1
        path.write_text(render_post(art, sources, now), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
        written += 1

    # Mark every candidate as seen, including ones the editor skipped,
    # so the same items aren't reconsidered tomorrow.
    save_seen(seen + [it["link"] for it in items])
    print(f"{written} article(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
