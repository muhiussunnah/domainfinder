"""Check whether each shortlisted domain still has pages in Bing's index (site: search
through DataForSEO's Bing SERP API, $0.002 per domain). Expired domains that Bing
still indexes usually get crawled and ranked again much faster than new domains.

Optionally checks Google too (--engines bing,google).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import (BudgetExceeded, DataForSEO, load_niche, load_table, log, parallel_map,
                    save_table, setup_console)
from score import ranked

ACQUIRABLE = {"register", "backorder", "auction", "watch", "check"}


def site_check(dfs: DataForSEO, engine: str, domain: str, location_code: int) -> dict:
    t = dfs.post(f"serp/{engine}/organic/live/regular",
                 {"keyword": f"site:{domain}", "location_code": location_code, "language_code": "en", "depth": 10},
                 label=f"{engine}:{domain}", estimate=0.002)
    res = (t.get("result") or [{}])[0] or {}
    hits = []
    for it in res.get("items") or []:
        if it.get("type") != "organic":
            continue
        host = (it.get("domain") or "").lower()
        if host == domain or host.endswith("." + domain):
            hits.append(it)
    p = engine
    return {
        f"{p}_indexed": "yes" if hits else "no",
        f"{p}_results": res.get("se_results_count") or len(hits) if hits else 0,
        f"{p}_urls": len(hits),
        f"{p}_sample": " | ".join(f"{(h.get('title') or '')[:60]} <{h.get('url')}>" for h in hits[:3]),
    }


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--top", type=int, default=100, help="check the best N acquirable candidates")
    ap.add_argument("--engines", default="bing")
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
    top = [d for d in ranked(table, niche) if table[d].get("acquire") in ACQUIRABLE][: a.top]
    for engine in [e.strip() for e in a.engines.split(",") if e.strip()]:
        todo = [d for d in top if a.force or not table[d].get(f"{engine}_indexed")]
        log(f"{engine} site: checks for {len(todo)} domains (~${len(todo) * 0.002:.2f})")
        stop = False
        for d, res, err in parallel_map(lambda x: site_check(dfs, engine, x, loc), todo,
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
    n_yes = sum(1 for d in top if table[d].get("bing_indexed") == "yes")
    log(f"index: {n_yes}/{len(top)} still in Bing; run spend ${dfs.spent:.2f}")


if __name__ == "__main__":
    main()
