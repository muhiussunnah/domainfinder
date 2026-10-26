"""Count the Wikipedia articles that link to each buyable candidate (free, no API key).

Uses list=exturlusage, which lists every page whose external links include a domain.
A hand-registered domain that Wikipedia still links to starts with an editorial link
from one of the strongest sites on the web, so the count feeds the authority score and
the report shows the article titles as evidence.
"""
from __future__ import annotations

import argparse
import urllib.parse
from pathlib import Path

from common import UA, get_json, load_niche, load_table, log, parallel_map, save_table, setup_console
from score import ranked

API = "https://en.wikipedia.org/w/api.php"
ACQUIRABLE = {"register", "backorder", "auction", "watch", "check"}


def usage(domain: str, delay: float) -> dict:
    pages: dict[int, str] = {}
    for proto in ("http", "https"):
        params = {"action": "query", "list": "exturlusage", "euquery": f"*.{domain}", "euprotocol": proto,
                  "eunamespace": "0", "eulimit": "100", "format": "json", "formatversion": "2"}
        status, data = get_json(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA},
                                timeout=60, retries=3, min_interval=delay)
        if status != 200 or not isinstance(data, dict):
            continue
        for it in data.get("query", {}).get("exturlusage", []):
            pages[it["pageid"]] = it.get("title", "")
    return {"wiki_links": len(pages), "wiki_link_titles": " | ".join(sorted(pages.values())[:4]), "wiki_checked": "1"}


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--top", type=int, default=300, help="check the best N acquirable candidates")
    ap.add_argument("--domains", default="", help="comma-separated domains instead of the top N")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    run = Path(a.run)
    table = load_table(run)
    if a.domains:
        todo = [x for x in (d.strip().lower() for d in a.domains.split(",")) if x in table]
    else:
        todo = [d for d in ranked(table, load_niche(run)) if table[d].get("acquire") in ACQUIRABLE][: a.top]
    todo = [d for d in todo if a.force or not table[d].get("wiki_checked")]
    log(f"wikipedia links: {len(todo)} domains (about {len(todo) * 2 * a.delay / max(1, a.workers) / 60 + 1:.0f} min)")
    n = 0
    for d, res, err in parallel_map(lambda x: usage(x, a.delay), todo, workers=a.workers, desc="wikipedia", every=50):
        if res:
            table[d].update(res)
            n += 1 if res["wiki_links"] else 0
        elif err:
            log(f"wikipedia {d}: {err}")
    save_table(run, table)
    log(f"wikipedia links: {n}/{len(todo)} domains have at least one linking article")


if __name__ == "__main__":
    main()
