#!/usr/bin/env python3
"""Check that the URLs of upcoming events still resolve.

Prints a markdown report of dead links (404/410/5xx/DNS failures) and exits 1
if there are any, so a workflow can open an issue. Sites that block bots
(403/429/999) are not counted as dead.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (compatible; NuclearNewswireBot/1.0)"
BLOCKED = {401, 403, 429, 999}


def status(url: str) -> int:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 405, 501):
                continue  # some servers reject HEAD; retry with GET
            return e.code
        except Exception:
            if method == "GET":
                return 0
    return 0


def main() -> int:
    events = json.loads((ROOT / "_data" / "events.json").read_text(encoding="utf-8-sig") or "[]")
    today = date.today().isoformat()
    dead = []
    for e in events:
        if e["end_date"] < today:
            continue
        code = status(e["url"])
        if code == 0 or code in (404, 410) or code >= 500:
            dead.append((e, code))
    if not dead:
        print("All upcoming event links respond.")
        return 0
    print("The following upcoming event links look dead:\n")
    for e, code in dead:
        print(f"- [{e['title']}]({e['url']}) ({e['start_date']}, {e['organizer']}): "
              f"{'no response' if code == 0 else 'HTTP ' + str(code)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
