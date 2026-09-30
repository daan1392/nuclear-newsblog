#!/usr/bin/env python3
"""Generate AI-written nuclear-sector news briefs from RSS/Atom feeds.

Reads scripts/feeds.yml, collects recent items that haven't been covered yet,
asks Claude to pick the most newsworthy distinct stories and write an original
brief for each, then writes Jekyll posts to _posts/ and records the source URLs
in _data/seen.json so they aren't covered twice.

Usage:
    ANTHROPIC_API_KEY=... python scripts/generate_articles.py
    python scripts/generate_articles.py --dry-run          # list candidates, no API call
    python scripts/generate_articles.py --since 2026-09-01 # backfill from a date, week by week
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = ROOT / "scripts" / "feeds.yml"
CATEGORIES_FILE = ROOT / "_data" / "categories.yml"
SEEN_FILE = ROOT / "_data" / "seen.json"
POSTS_DIR = ROOT / "_posts"

MODEL = os.environ.get("NEWSBLOG_MODEL", "claude-sonnet-5-5")
SEEN_LIMIT = 8000          # keep the dedup list from growing forever
MAX_ITEMS_PER_CALL = 120   # items sent to the model in one request
# Spending guard: a run stops calling the API once it has used this many input tokens.
MAX_INPUT_TOKENS = int(os.environ.get("MAX_INPUT_TOKENS", "1500000"))
TOKENS_IN = TOKENS_OUT = 0
THIN_SUMMARY = 250         # feed summaries shorter than this get enriched from the page
UAS = [
    "Mozilla/5.0 (compatible; NuclearNewswireBot/1.0)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 NuclearNewswireBot/1.0",
]


def load_categories() -> list[dict]:
    return yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))


CATEGORIES = load_categories()
CATEGORY_NAMES = [c["name"] for c in CATEGORIES if c.get("auto", True)]
CATEGORY_HELP = "\n".join(
    f"  - {c['name']}: {c['description']}" for c in CATEGORIES if c.get("auto", True))

SYSTEM_PROMPT = f"""You are the editor of "Nuclear Newswire", a news blog covering the
nuclear sector: power reactors and SMRs, nuclear medicine and isotopes, NORM and
radiation protection, fuel cycle and waste, fusion, research reactors and nuclear
science, regulation and policy, safety, and the industry.

You receive a list of recent news items (headline, outlet, link, feed summary).
Your job:
1. Choose the most newsworthy DISTINCT stories (merge items from different
   outlets that cover the same event into one article). Skip press-release
   fluff, event announcements, job ads, marketing and anything off-topic
   (the feeds include some general science news; keep only what is genuinely
   about nuclear technology, radiation, isotopes or the nuclear industry).
   Aim for a healthy spread across the categories below when the items allow.
2. For each chosen story, write an original news brief of 150-350 words.

Categories (pick exactly one per article):
{CATEGORY_HELP}

Rules for every brief:
- Write entirely in your own words. Never copy sentences from the summaries;
  at most one short quote (under 15 words) per article, attributed.
- Use only facts present in the supplied items. Do not invent numbers, dates,
  names or quotes. If something is unclear, say less rather than guess.
- If an item has almost no text (headline only), only cover it when the headline
  and outlet support a short factual brief; otherwise skip it.
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
                        "category": {"type": "string", "enum": CATEGORY_NAMES},
                        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                        "countries": {
                            "type": "array", "items": {"type": "string"}, "maxItems": 3,
                            "description": "Main countries the story is about (English names, e.g. Belgium, United States); empty if none or global.",
                        },
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
    with FEEDS_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen() -> list[str]:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text() or "[]")
    return []


def save_seen(seen: list[str]) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen[-SEEN_LIMIT:], indent=1) + "\n")


def norm(link: str) -> str:
    """Normalise a URL for duplicate detection (scheme, www and trailing slash don't matter)."""
    return re.sub(r"^https?://(www\.)?", "", link.strip()).rstrip("/").lower()


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = unescape(text)
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


def http_get(url: str, timeout: int = 30) -> str:
    """GET a page as text, trying each user agent in turn."""
    for i, ua in enumerate(UAS):
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read().decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError):  # HTTPError is a URLError
            if i == len(UAS) - 1:
                raise
    raise RuntimeError("unreachable")


def _meta(html: str, *names: str) -> str:
    for name in names:
        for pat in (
            rf'<meta[^>]+(?:property|name)=["\']{name}["\'][^>]+content=["\']([^"\']*)["\']',
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{name}["\']',
        ):
            m = re.search(pat, html, re.I)
            if m:
                return clean_html(m.group(1))
    return ""


def fetch_page(url: str) -> dict:
    """Title and opening text (description + first paragraphs) of an article page."""
    html = http_get(url)
    title = _meta(html, "og:title", "twitter:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = clean_html(m.group(1)) if m else ""
    desc = _meta(html, "og:description", "description")
    body = re.sub(r"<(script|style|noscript|nav|footer|header)\b.*?</\1>", " ", html, flags=re.S | re.I)
    paras = [clean_html(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", body, re.S | re.I)]
    text = " ".join(p for p in paras if len(p) > 60)
    summary = (desc + " " + text).strip() if desc and desc not in text else text or desc
    return {"title": title, "summary": summary[:1500]}


# ---------------------------------------------------------------- pipeline
def read_feed(feed: dict, min_ts: float, deep: bool) -> list[tuple]:
    """(entry, timestamp) pairs of one feed. Pages deeper only when `deep` and the feed supports it."""
    out, pages = [], (6 if deep and feed.get("paged") else 1)
    for n in range(1, pages + 1):
        url = feed["url"]
        if n > 1:
            url += ("&" if "?" in url else "?") + f"paged={n}"
        parsed = feedparser.parse(url, agent=UAS[0])
        if parsed.bozo and not parsed.entries:
            if n == 1:
                print(f"warning: could not read {feed['name']} ({feed['url']}): "
                      f"{parsed.get('bozo_exception')}", file=sys.stderr)
            break
        stamps = []
        for e in parsed.entries:
            ts = entry_time(e)
            if ts is not None:
                stamps.append(ts)
            out.append((e, ts))
        if not stamps or min(stamps) < min_ts:
            break
    return out


def collect_items(cfg: dict, seen: set[str], since_ts: float | None) -> list[dict]:
    now = time.time()
    min_ts = since_ts if since_ts is not None else now - cfg.get("max_age_hours", 72) * 3600
    have = {norm(s) for s in seen}
    items: list[dict] = []

    for feed in cfg.get("feeds", []):
        if feed.get("enabled", True) is False:
            continue
        kept = 0
        for e, ts in read_feed(feed, min_ts, deep=since_ts is not None):
            link = (e.get("link") or "").strip()
            if not link or norm(link) in have:
                continue
            if ts is None and since_ts is not None:
                continue  # can't place undated items in a backfill
            if ts is not None and ts < min_ts:
                continue
            have.add(norm(link))
            items.append({
                "outlet": feed["name"],
                "title": clean_html(e.get("title", "")),
                "link": link,
                "ts": ts,
                "summary": clean_html(e.get("summary", ""))[:1200],
            })
            kept += 1
        print(f"{feed['name']}: {kept} new item(s)")

    if since_ts is not None:
        # Sitemaps hold older articles than the feeds still carry; stop 2 days
        # before today because sitemap dates are unreliable for very recent pages.
        cutoff = date.fromtimestamp(now - 2 * 86400)
        since_d = date.fromtimestamp(since_ts)
        for sm in cfg.get("backfill_sitemaps", []):
            xml = http_get(sm["url"], timeout=90)
            kept = 0
            for loc, lastmod in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", xml):
                if sm.get("include", "") not in loc:
                    continue
                try:
                    d = date.fromisoformat(lastmod[:10])
                except ValueError:
                    continue
                if not (since_d <= d <= cutoff):
                    continue
                if sm.get("host"):
                    loc = re.sub(r"^(https?://)[^/]+", rf"\g<1>{sm['host']}", loc)
                if norm(loc) in have:
                    continue
                try:
                    page = fetch_page(loc)
                except Exception as exc:
                    print(f"warning: skipping {loc}: {exc}", file=sys.stderr)
                    continue
                time.sleep(0.3)
                have.add(norm(loc))
                ts = datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp()
                items.append({"outlet": sm["name"], "title": page["title"], "link": loc,
                              "ts": ts, "summary": page["summary"]})
                kept += 1
            print(f"{sm['name']} (sitemap): {kept} archive item(s)")

    # Feeds that publish only headlines (IAEA) or PDFs (NRC): pull text from the page.
    for it in items:
        if (len(it["summary"]) < THIN_SUMMARY and not it["link"].lower().endswith(".pdf")
                and not any(h in it["link"] for h in cfg.get("no_enrich_hosts", []))):
            try:
                page = fetch_page(it["link"])
                it["summary"] = (it["summary"] + " " + page["summary"]).strip()[:1500]
                time.sleep(0.2)
            except Exception as exc:
                print(f"warning: could not enrich {it['link']}: {exc}", file=sys.stderr)

    items.sort(key=lambda i: i["ts"] or now)
    for i, item in enumerate(items):
        item["id"] = i
        item["published"] = datetime.fromtimestamp(item["ts"], timezone.utc).isoformat() if item["ts"] else None
    return items


def make_chunks(items: list[dict], weekly: bool) -> list[list[dict]]:
    """One chunk for the daily run; ISO-week chunks (split if large) for a backfill."""
    if not weekly:
        return [items[-MAX_ITEMS_PER_CALL * 2:]] if items else []
    weeks: dict[tuple, list[dict]] = {}
    for it in items:
        d = datetime.fromtimestamp(it["ts"], timezone.utc).isocalendar()
        weeks.setdefault((d.year, d.week), []).append(it)
    chunks = []
    for key in sorted(weeks):
        wk = weeks[key]
        parts = math.ceil(len(wk) / MAX_ITEMS_PER_CALL)
        size = math.ceil(len(wk) / parts)
        chunks += [wk[i:i + size] for i in range(0, len(wk), size)]
    return chunks


def write_articles(items: list[dict], max_articles: int) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic()
    listing = json.dumps(
        [{"id": it["id"], "outlet": it["outlet"], "title": it["title"], "link": it["link"],
          "published": it["published"], "summary": it["summary"][:900]} for it in items],
        indent=1, ensure_ascii=False,
    )
    stamps = [it["ts"] for it in items if it["ts"]]
    span = (f"published between {datetime.fromtimestamp(min(stamps), timezone.utc):%Y-%m-%d} and "
            f"{datetime.fromtimestamp(max(stamps), timezone.utc):%Y-%m-%d}" if stamps else "recent")
    user_msg = (
        f"Here are {len(items)} news items, {span}. Write at most {max_articles} briefs "
        f"(fewer is fine if little is newsworthy; zero if nothing is). Write in the past "
        f"tense where the events are past. You must respond by calling the publish_articles "
        f"tool (with an empty list if nothing qualifies).\n\n{listing}"
    )
    global TOKENS_IN, TOKENS_OUT
    if TOKENS_IN > MAX_INPUT_TOKENS:
        raise RuntimeError(f"Stopping: {TOKENS_IN} input tokens used, above the MAX_INPUT_TOKENS guard "
                           f"({MAX_INPUT_TOKENS}). Raise the environment variable to allow more.")
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[PUBLISH_TOOL],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": user_msg}],
    )
    TOKENS_IN += resp.usage.input_tokens
    TOKENS_OUT += resp.usage.output_tokens
    for block in resp.content:
        if block.type == "tool_use" and block.name == "publish_articles":
            return block.input.get("articles", [])[:max_articles]
    raise RuntimeError("Model did not return articles")


def yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # JSON strings are valid YAML scalars


def render_post(article: dict, sources: list[dict], when: datetime) -> str:
    tags = ", ".join(yaml_str(t) for t in article.get("tags", []))
    src_yaml = "\n".join(
        f"  - title: {yaml_str(s['title'])}\n    outlet: {yaml_str(s['outlet'])}\n    url: {yaml_str(s['link'])}"
        for s in sources
    )
    src_md = "\n".join(f"- [{s['title']}]({s['link']}) — *{s['outlet']}*" for s in sources)
    return f"""---
layout: post
title: {yaml_str(article['title'])}
date: {when:%Y-%m-%d %H:%M:%S} +0000
categories: [{yaml_str(article['category'])}]
tags: [{tags}]
countries: [{", ".join(yaml_str(c) for c in article.get("countries", []))}]
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


def post_time(sources: list[dict]) -> datetime:
    """Publication time of the newest source (never in the future); now if undated."""
    now = datetime.now(timezone.utc)
    stamps = [s["ts"] for s in sources if s.get("ts")]
    if not stamps:
        return now
    return min(datetime.fromtimestamp(max(stamps), timezone.utc), now)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list candidate items, don't call the API")
    ap.add_argument("--since", help="backfill: cover everything published since YYYY-MM-DD, week by week")
    args = ap.parse_args()

    since_ts = None
    if args.since:
        d = date.fromisoformat(args.since)
        since_ts = datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()

    cfg = load_config()
    seen = load_seen()
    items = collect_items(cfg, set(seen), since_ts)
    print(f"{len(items)} candidate item(s) in total")

    if args.dry_run:
        for it in items:
            print(f"  [{it['id']}] {(it['published'] or '')[:10]} {it['outlet']}: {it['title']} ({len(it['summary'])} chars)")
        return 0
    if not items:
        print("Nothing new — no PR needed.")
        return 0

    per_call = (cfg.get("backfill_articles_per_chunk", 12) if since_ts is not None
                else cfg.get("max_articles", 12))
    POSTS_DIR.mkdir(exist_ok=True)
    written = 0
    for n, chunk in enumerate(make_chunks(items, weekly=since_ts is not None), 1):
        print(f"--- chunk {n}: {len(chunk)} item(s)")
        articles = write_articles(chunk, per_call)
        by_id = {it["id"]: it for it in chunk}
        for art in articles:
            sources = [by_id[i] for i in art.get("source_ids", []) if i in by_id]
            if not sources or art.get("category") not in CATEGORY_NAMES:
                print(f"skipping '{art.get('title')}': no valid sources or category", file=sys.stderr)
                continue
            when = post_time(sources)
            base = f"{when:%Y-%m-%d}-{slugify(art['title'])}"
            path, k = POSTS_DIR / f"{base}.md", 2
            while path.exists():
                path = POSTS_DIR / f"{base}-{k}.md"
                k += 1
            path.write_text(render_post(art, sources, when), encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
            written += 1
        # Mark every candidate as seen, including ones the editor skipped,
        # so the same items aren't reconsidered tomorrow.
        seen += [it["link"] for it in chunk]
        save_seen(seen)
    print(f"{written} article(s) written; tokens used: {TOKENS_IN} in, {TOKENS_OUT} out")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Articles run\n{written} article(s) written from {len(items)} candidate item(s); "
                    f"{TOKENS_IN:,} input / {TOKENS_OUT:,} output tokens.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
