#!/usr/bin/env python3
"""Compile a weekly roundup post from the last 7 days of articles plus the
events coming up in the next 30 days.

No API call: it only reorganises what is already on the site (titles, teasers
and links from the posts' front matter), so it cannot introduce new claims.

Usage: python scripts/weekly_roundup.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "_posts"
MIN_ARTICLES = 3


def front_matter(path: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="end of the week (default: today)")
    args = ap.parse_args()
    end = date.fromisoformat(args.date) if args.date else date.today()
    start = end - timedelta(days=6)

    by_cat: dict[str, list[tuple]] = defaultdict(list)
    count = 0
    for p in sorted(POSTS.glob("*.md"), reverse=True):
        d = p.name[:10]
        if not (start.isoformat() <= d <= end.isoformat()) or "weekly-roundup" in p.name:
            continue
        fm = front_matter(p)
        cat = (fm.get("categories") or ["Other"])[0]
        if cat == "Weekly roundup":
            continue
        by_cat[cat].append((d, fm.get("title", p.stem), fm.get("excerpt", ""), p.stem))
        count += 1
    if count < MIN_ARTICLES:
        print(f"Only {count} article(s) this week — no roundup.")
        return 0

    cfg = yaml.safe_load((ROOT / "_config.yml").read_text(encoding="utf-8"))
    site = (cfg.get("url", "") + cfg.get("baseurl", "")).rstrip("/")
    order = [c["name"] for c in yaml.safe_load((ROOT / "_data" / "categories.yml").read_text(encoding="utf-8"))]

    lines = [f"Here is what we published between {start:%-d %B} and {end:%-d %B %Y}, "
             f"{count} articles across {len(by_cat)} topics, followed by events coming up in the next month.", ""]
    for cat in sorted(by_cat, key=lambda c: order.index(c) if c in order else 99):
        lines += [f"## {cat}", ""]
        for d, title, excerpt, stem in by_cat[cat]:
            lines.append(f"- [{title}]({{% post_url {stem} %}}): {excerpt}")
        lines.append("")

    events_path = ROOT / "_data" / "events.json"
    events = json.loads(events_path.read_text(encoding="utf-8-sig") or "[]") if events_path.exists() else []
    soon = [e for e in events if end.isoformat() <= e["start_date"] <= (end + timedelta(days=30)).isoformat()]
    if soon:
        lines += ["## Coming up", ""]
        for e in sorted(soon, key=lambda e: e["start_date"])[:15]:
            where = ", ".join(x for x in (e.get("city"), e.get("country")) if x and x != "UNKNOWN")
            lines.append(f"- {e['start_date']}: [{e['title']}]({e['url']})" + (f" ({where})" if where else ""))
        lines += ["", "See the full [events calendar]({{ '/events/' | relative_url }})."]

    body = "\n".join(lines).strip() + "\n"
    slug = f"{end:%Y-%m-%d}-weekly-roundup-{end:%Y-%m-%d}"
    front = {
        "layout": "post",
        "title": f"Weekly roundup: week ending {end:%-d %B %Y}",
        "date": f"{end:%Y-%m-%d} 18:00:00 +0000",
        "categories": ["Weekly roundup"],
        "tags": ["roundup"],
        "countries": [],
        "excerpt": f"{count} articles from the past week, grouped by topic, plus upcoming events.",
        "ai_generated": False,
        "sources": [{"title": "Nuclear Newswire archive", "outlet": "Nuclear Newswire", "url": f"{site}/archive/"}],
    }
    text = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in front.items()) + "\n---\n\n" + body
    (POSTS / f"{slug}.md").write_text(text, encoding="utf-8")
    print(f"wrote _posts/{slug}.md ({count} articles, {len(soon)} upcoming events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
