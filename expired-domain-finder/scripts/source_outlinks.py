"""Source candidates by crawling niche pages for outbound links to other domains.

Old niche articles, resource pages and blogrolls link to sites that have since died.
Those dead sites are topical by definition, even when the niche word is not in the
name. Seeds come from a URL file and/or DataForSEO Google results for niche keywords.

The crawler is polite: it honours robots.txt and waits between requests per host.
"""
from __future__ import annotations

import argparse
import urllib.parse
import urllib.robotparser
from collections import defaultdict
from pathlib import Path

from common import (ASSETS, DataForSEO, DataForSEOError, http_request, load_lines, load_niche,
                    load_table, log, normalize_domain, parallel_map, parse_html, parse_tlds,
                    save_table, setup_console, suffix_of, upsert, UA)

HINTS = ("resource", "links", "blogroll", "recommend", "partner", "friends", "favorite", "best",
         "guide", "review", "directory", "tools", "useful", "sites", "list")


def serp_seeds(run: Path, keywords: list[str], depth: int, location_code: int, max_cost: float | None) -> list[str]:
    dfs = DataForSEO(run, max_cost=max_cost)
    urls = []
    for kw in keywords:
        try:
            t = dfs.post("serp/google/organic/live/regular",
                         {"keyword": kw, "location_code": location_code, "language_code": "en", "depth": depth},
                         label=f"outlink-seed:{kw}", estimate=0.002 * max(1, depth // 10))
        except DataForSEOError as e:
            log(f"seed SERP failed for {kw!r}: {e}")
            if e.is_access_problem:
                break
            continue
        for res in t.get("result") or []:
            for it in res.get("items") or []:
                if it.get("type") == "organic" and it.get("url"):
                    urls.append(it["url"])
    log(f"SERP seeds: {len(urls)} urls, ${dfs.spent:.3f} spent")
    return urls


class Robots:
    def __init__(self):
        self.cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self.cache:
            rp = urllib.robotparser.RobotFileParser()
            status, body, _ = http_request(base + "/robots.txt", timeout=15, retries=1)
            if status == 200:
                rp.parse(body.decode("utf-8", "replace").splitlines())
                self.cache[base] = rp
            else:
                self.cache[base] = None
        rp = self.cache[base]
        return True if rp is None else rp.can_fetch(UA, url)


def crawl_site(seed: str, robots: Robots, pages_per_site: int, delay: float) -> tuple[str, set[str]]:
    """Fetch the seed page plus a few same-site pages that look like link lists."""
    seed_dom = normalize_domain(seed) or ""
    queue, seen, external = [seed], set(), set()
    while queue and len(seen) < pages_per_site:
        url = queue.pop(0)
        if url in seen or not robots.allowed(url):
            seen.add(url)
            continue
        seen.add(url)
        status, body, headers = http_request(url, timeout=20, retries=1, min_interval=delay, max_bytes=3_000_000)
        ctype = (headers.get("Content-Type") or headers.get("content-type") or "")
        if status != 200 or "html" not in ctype:
            continue
        page = parse_html(body)
        for href in page["links"]:
            absu = urllib.parse.urljoin(url, href)
            if not absu.startswith("http"):
                continue
            dom = normalize_domain(absu)
            if not dom:
                continue
            if dom == seed_dom:
                low = absu.lower()
                if any(h in low for h in HINTS) and absu not in seen and len(queue) < 50:
                    queue.append(absu.split("#")[0])
            else:
                external.add(dom)
    return seed_dom, external


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--seed-file", help="text file with one seed URL per line")
    ap.add_argument("--serp", action="store_true", help="add seeds from DataForSEO Google results (paid, ~$0.005/keyword)")
    ap.add_argument("--keywords", default="", help="comma-separated SERP keywords (default: niche + top tokens)")
    ap.add_argument("--depth", type=int, default=30, help="SERP results per keyword")
    ap.add_argument("--pages-per-site", type=int, default=8)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to the same host")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tlds", default="com,net,org")
    ap.add_argument("--max-cost", type=float, default=None)
    a = ap.parse_args(argv)

    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    seeds: list[str] = []
    if a.seed_file:
        seeds += [u for u in load_lines(Path(a.seed_file)) if u.startswith("http")]
    if a.serp:
        kws = [k.strip() for k in a.keywords.split(",") if k.strip()] or \
              [niche["niche"]] + [f"best {t}" for t in niche["tokens"][:6]] + [f"{niche['niche']} blog", f"{niche['niche']} resources"]
        seeds += serp_seeds(run, kws, a.depth, niche.get("location_code", 2840), a.max_cost)
    seeds = list(dict.fromkeys(seeds))
    if not seeds:
        raise SystemExit("no seeds: pass --seed-file and/or --serp")

    skip = set(load_lines(ASSETS / "big_domains.txt"))
    tlds = parse_tlds(a.tlds)
    robots = Robots()
    linked_from: dict[str, set[str]] = defaultdict(set)
    for seed, res, err in parallel_map(lambda s: crawl_site(s, robots, a.pages_per_site, a.delay),
                                       seeds, workers=a.workers, desc="crawl", every=10):
        if err or not res:
            continue
        seed_dom, ext = res
        for d in ext:
            if d not in skip and suffix_of(d) in tlds:
                linked_from[d].add(seed_dom)

    for d, refs in linked_from.items():
        upsert(table, d, {"outlink_refs": len(refs), "outlink_from": "|".join(sorted(refs)[:5])},
               source="outlinks")
    save_table(run, table)
    log(f"outlinks: {len(seeds)} seeds -> {len(linked_from)} external domains; table now {len(table)}")


if __name__ == "__main__":
    main()
