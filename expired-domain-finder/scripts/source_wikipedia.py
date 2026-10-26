"""Source candidates from Wikipedia (free, no API key): external links on articles about
the niche, with priority for links editors already tagged {{Dead link}}.

Every domain found here has at least one Wikipedia article linking to it, which is the
strongest editorial link a hand-registered domain can come with. Wikipedia's search
operator hastemplate:"Dead link" finds articles that contain dead links; the article
wikitext then gives every external URL and which ones carry the tag. check_availability.py
decides which are free to register.

Usage:
  python source_wikipedia.py --run RUN                 # queries = the run's niche tokens
  python source_wikipedia.py --run RUN --terms "camping gear,tent,hiking boots"
"""
from __future__ import annotations

import argparse
import re
import urllib.parse
from pathlib import Path

from common import (ASSETS, UA, chunks, get_json, load_lines, load_niche, load_table, log, normalize_domain,
                    parse_tlds, save_table, setup_console, suffix_of, upsert)

API = "https://en.wikipedia.org/w/api.php"
URL_RE = re.compile(r"https?://[^\s|\]\}<>\"'\)]+")
DEAD_RE = re.compile(r"\{\{\s*dead\s*link", re.I)
SKIP = {"wikipedia.org", "wikimedia.org", "wikidata.org", "wiktionary.org", "archive.org", "doi.org",
        "worldcat.org", "jstor.org", "google.com", "youtube.com", "amazon.com", "facebook.com", "twitter.com",
        "x.com", "instagram.com", "nytimes.com", "bbc.co.uk", "theguardian.com", "imdb.com", "ncbi.nlm.nih.gov",
        "nih.gov", "loc.gov", "census.gov", "britannica.com", "books.google.com", "web.archive.org"}


def api(params: dict, delay: float) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    url = API + "?" + urllib.parse.urlencode(params)
    status, data = get_json(url, headers={"User-Agent": UA}, timeout=60, retries=3, min_interval=delay)
    return data if status == 200 and isinstance(data, dict) else {}


def search(term: str, limit: int, delay: float) -> list[tuple[int, str]]:
    data = api({"action": "query", "list": "search", "srnamespace": "0", "srlimit": str(limit),
                "srsearch": f'hastemplate:"Dead link" {term}'}, delay)
    return [(h["pageid"], h["title"]) for h in data.get("query", {}).get("search", [])]


def wikitext(pageids: list[int], delay: float) -> dict[int, tuple[str, str]]:
    data = api({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                "pageids": "|".join(str(p) for p in pageids)}, delay)
    out = {}
    for page in data.get("query", {}).get("pages", []):
        revs = page.get("revisions") or []
        if revs:
            out[page["pageid"]] = (page.get("title", ""), (revs[0].get("slots", {}).get("main", {}) or {}).get("content", ""))
    return out


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--terms", default="", help="comma-separated search terms (default: the niche tokens)")
    ap.add_argument("--per-term", type=int, default=30, help="articles per search term (max 50)")
    ap.add_argument("--max-pages", type=int, default=4000, help="stop after reading this many articles")
    ap.add_argument("--tlds", default="com,net,org")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between Wikipedia API calls")
    ap.add_argument("--all-links", action="store_true",
                    help="keep every external link, not only ones tagged {{Dead link}} (more candidates, more noise)")
    a = ap.parse_args(argv)

    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    tlds = parse_tlds(a.tlds)
    big = set(load_lines(ASSETS / "big_domains.txt")) | SKIP
    terms = [t.strip() for t in a.terms.split(",") if t.strip()] or list(niche["tokens"])

    pages: dict[int, str] = {}
    for i, term in enumerate(terms, 1):
        for pid, title in search(term, min(50, a.per_term), a.delay):
            pages.setdefault(pid, title)
        if i % 25 == 0:
            log(f"wikipedia search: {i}/{len(terms)} terms, {len(pages)} articles")
        if len(pages) >= a.max_pages:
            break
    ids = list(pages)[: a.max_pages]
    log(f"wikipedia: {len(ids)} articles with dead links about {len(terms)} terms; reading wikitext")

    found: dict[str, dict] = {}
    done = 0
    for group in chunks(ids, 50):
        for pid, (title, text) in wikitext(group, a.delay).items():
            for m in URL_RE.finditer(text):
                d = normalize_domain(m.group(0))
                if not d or suffix_of(d) not in tlds or d in big:
                    continue
                dead = bool(DEAD_RE.search(text, m.end(), m.end() + 300))
                if not dead and not a.all_links:
                    continue
                rec = found.setdefault(d, {"titles": set(), "dead": 0})
                rec["titles"].add(title)
                rec["dead"] = max(rec["dead"], int(dead))
        done += len(group)
        if done % 500 == 0:
            log(f"wikipedia wikitext: {done}/{len(ids)} articles, {len(found)} domains")
    for d, rec in found.items():
        upsert(table, d, {"wiki_pages": len(rec["titles"]), "wiki_dead_tagged": rec["dead"],
                          "wiki_titles": " | ".join(sorted(rec["titles"])[:4])}, source="wikipedia")
    save_table(run, table)
    tagged = sum(1 for r in found.values() if r["dead"])
    log(f"wikipedia: {len(found)} domains ({tagged} tagged dead) from {done} articles; table now {len(table)}")


if __name__ == "__main__":
    main()
