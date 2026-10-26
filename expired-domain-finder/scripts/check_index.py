"""Check whether each shortlisted domain is still in the search index (DataForSEO SERP
API, $0.002 per domain per engine). An expired domain a search engine still knows is
re-crawled and ranked much faster than a brand-new one.

Google: a `site:domain` query; organic results from the domain mean it is indexed. Reliable.
Bing:   DataForSEO's Bing SERP returns nothing for `site:` queries (verified Oct 2026, even
        for wikihow.com), so Bing is checked with a name query (the bare domain as keyword)
        filtered to the domain with `target`: a domain Bing has indexed ranks for its own name.
        Treat "bing: no" as "probably not"; a manual https://www.bing.com/search?q=site%3A<domain>
        check settles doubts.

Columns per engine: <engine>_indexed (yes/no), <engine>_results, <engine>_urls, <engine>_sample,
<engine>_method (site / name). score.py combines them into idx_summary (both / google only /
bing only / none).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import (BudgetExceeded, DataForSEO, load_niche, load_table, log, parallel_map,
                    save_table, setup_console)
from score import ranked

ACQUIRABLE = {"register", "backorder", "auction", "watch", "check"}
METHOD = {"google": "site", "bing": "name"}


def task_for(engine: str, domain: str, location_code: int) -> dict:
    base = {"location_code": location_code, "language_code": "en", "depth": 10}
    if METHOD.get(engine, "site") == "site":
        return {**base, "keyword": f"site:{domain}"}
    return {**base, "keyword": domain, "target": f"*{domain}*"}


def serp_signals(engine: str, domain: str, res: dict) -> dict:
    """Turn one serp/<engine>/organic/live/regular result object into table columns."""
    hits = []
    for it in res.get("items") or []:
        if it.get("type") != "organic":
            continue
        host = (it.get("domain") or "").lower()
        if host == domain or host.endswith("." + domain):
            hits.append(it)
    method = METHOD.get(engine, "site")
    # se_results_count describes the whole query; only a site: query is about this domain
    count = (res.get("se_results_count") or len(hits)) if method == "site" and hits else len(hits)
    return {
        f"{engine}_indexed": "yes" if hits else "no",
        f"{engine}_results": count,
        f"{engine}_urls": len(hits),
        f"{engine}_sample": " | ".join(f"{(h.get('title') or '')[:60]} <{h.get('url')}>" for h in hits[:3]),
        f"{engine}_method": method,
    }


def check(dfs: DataForSEO, engine: str, domain: str, location_code: int) -> dict:
    t = dfs.post(f"serp/{engine}/organic/live/regular", task_for(engine, domain, location_code),
                 label=f"{engine}:{domain}", estimate=0.002)
    res = (t.get("result") or [{}])[0] or {}
    return serp_signals(engine, domain, res)


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--top", type=int, default=100, help="check the best N acquirable candidates")
    ap.add_argument("--engines", default="google,bing", help="comma list: google (site:), bing (name query)")
    ap.add_argument("--domains", default="", help="comma-separated domains to check instead of the top N")
    ap.add_argument("--location-code", type=int, default=None)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-cost", type=float, default=None)
    a = ap.parse_args(argv)

    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    dfs = DataForSEO(run, max_cost=a.max_cost)
    loc = a.location_code or niche.get("location_code", 2840)
    if a.domains:
        top = [x for x in (d.strip().lower() for d in a.domains.split(",")) if x in table]
    else:
        top = [d for d in ranked(table, niche) if table[d].get("acquire") in ACQUIRABLE][: a.top]
    engines = [e.strip().lower() for e in a.engines.split(",") if e.strip()]
    for engine in engines:
        todo = [d for d in top if a.force or not table[d].get(f"{engine}_indexed")]
        log(f"{engine} index checks ({METHOD.get(engine, 'site')} query) for {len(todo)} domains (~${len(todo) * 0.002:.2f})")
        stop = False
        for d, res, err in parallel_map(lambda x: check(dfs, engine, x, loc), todo,
                                        workers=a.workers, desc=engine, every=20):
            if res:
                table[d].update(res)
            elif isinstance(err, BudgetExceeded):
                stop = True
            elif err:
                log(f"{engine} {d}: {err}")
        save_table(run, table)
        if stop:
            log("budget reached, stopping index checks")
            break
    for engine in engines:
        n_yes = sum(1 for d in top if table[d].get(f"{engine}_indexed") == "yes")
        log(f"index: {n_yes}/{len(top)} in {engine}")
    log(f"run spend ${dfs.spent:.2f}")


if __name__ == "__main__":
    main()
