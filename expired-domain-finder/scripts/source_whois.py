"""Source candidates from DataForSEO's WHOIS Overview: domains that just expired
(registered = false) or are past expiry and sitting in grace/auction, filtered to
niche words in the name and a minimum number of referring domains.

Cost: $0.12 per request + $0.0012 per returned domain (1,000 domains = ~$1.32).
"""
from __future__ import annotations

import argparse
import re
from datetime import timedelta
from pathlib import Path

from common import (DataForSEO, DataForSEOError, chunks, load_niche, load_table, log, now_utc,
                    parse_tlds, save_table, setup_console, upsert)

ENDPOINT = "domain_analytics/whois/overview/live"


def dt(d) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S +00:00")


def build_filters(token_group, mode, tlds, min_rmd, days_back, max_rmd=0, updated_days=0):
    """At most 8 filters: name regex, tld, min/max referring domains, registered, and dates."""
    pattern = "(" + "|".join(re.escape(t) for t in token_group) + ")"
    f = [["domain", "regex", pattern], "and", ["tld", "in", sorted(tlds)], "and",
         ["backlinks_info.referring_main_domains", ">=", min_rmd]]
    if max_rmd:  # link-selling networks push fresh drops to 1,500-3,000 referring domains
        f += ["and", ["backlinks_info.referring_main_domains", "<=", max_rmd]]
    now = now_utc()
    if mode == "expired":
        f += ["and", ["registered", "=", False]]
        if updated_days:  # stale "expired" rows were re-registered long ago; fresh ones are really free
            f += ["and", ["updated_datetime", ">", dt(now - timedelta(days=updated_days))]]
    else:  # expiring: past the expiry date but still registered (grace / auction / redemption)
        f += ["and", ["registered", "=", True],
              "and", ["expiration_datetime", "<", dt(now + timedelta(days=7))],
              "and", ["expiration_datetime", ">", dt(now - timedelta(days=days_back))]]
    return f


def whois_fields(it: dict) -> dict:
    """One WHOIS Overview item -> whois_* columns (also used by mcp_inject.py)."""
    bl = it.get("backlinks_info") or {}
    org = (it.get("metrics") or {}).get("organic") or {}
    return {
        "whois_registered": it.get("registered"),
        "whois_created": (it.get("created_datetime") or "")[:10],
        "whois_expiration": (it.get("expiration_datetime") or "")[:10],
        "whois_updated": (it.get("updated_datetime") or "")[:10],
        "whois_registrar": it.get("registrar"),
        "whois_epp": ";".join(it.get("epp_status_codes") or []),
        "whois_rd": bl.get("referring_domains"),
        "whois_rmd": bl.get("referring_main_domains"),
        "whois_backlinks": bl.get("backlinks"),
        "whois_dofollow": bl.get("dofollow"),
        "whois_etv": org.get("etv"),
        "whois_kw_count": org.get("count"),
        "whois_top3": (org.get("pos_1") or 0) + (org.get("pos_2_3") or 0),
    }


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--mode", choices=["expired", "expiring", "both"], default="both")
    ap.add_argument("--tlds", default="com,net,org")
    ap.add_argument("--min-rmd", type=int, default=5, help="minimum referring main domains")
    ap.add_argument("--max-rmd", type=int, default=1500,
                    help="skip domains with more referring main domains (link-spam networks); 0 = no cap")
    ap.add_argument("--updated-days", type=int, default=30,
                    help="expired mode: WHOIS record updated within N days (older rows are usually re-registered); 0 = any")
    ap.add_argument("--days-back", type=int, default=40, help="expiring mode: expired at most N days ago")
    ap.add_argument("--max-results", type=int, default=1000, help="per mode and token group")
    ap.add_argument("--group-size", type=int, default=40, help="tokens per regex request")
    ap.add_argument("--max-cost", type=float, default=None)
    a = ap.parse_args(argv)

    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    dfs = DataForSEO(run, max_cost=a.max_cost)
    tlds = parse_tlds(a.tlds)
    modes = ["expired", "expiring"] if a.mode == "both" else [a.mode]
    added = 0
    for mode in modes:
        for group in chunks(niche["tokens"], a.group_size):
            offset = 0
            while offset < a.max_results:
                limit = min(1000, a.max_results - offset)
                # rank by keywords the domain still ranks for (a sign it is still indexed), then links
                task = {"limit": limit, "offset": offset,
                        "filters": build_filters(group, mode, tlds, a.min_rmd, a.days_back, a.max_rmd, a.updated_days),
                        "order_by": ["metrics.organic.count,desc", "backlinks_info.referring_main_domains,desc"]}
                try:
                    t = dfs.post(ENDPOINT, task, label=f"whois:{mode}", estimate=0.12 + 0.0012 * limit)
                except DataForSEOError as e:
                    log(f"whois {mode} failed: {e}")
                    if e.is_access_problem:
                        save_table(run, table)
                        raise SystemExit(1)
                    break
                res = (t.get("result") or [{}])[0] or {}
                items = res.get("items") or []
                for it in items:
                    d = (it.get("domain") or "").lower()
                    if not d:
                        continue
                    upsert(table, d, whois_fields(it), source=f"whois_{mode}")
                    added += 1
                total = res.get("total_count") or 0
                log(f"whois {mode}: got {len(items)} (total matching {total}) offset {offset}")
                offset += limit
                if len(items) < limit or offset >= total:
                    break
    save_table(run, table)
    log(f"whois: {added} rows upserted, table now {len(table)} domains, run spend ${dfs.spent:.2f}")


if __name__ == "__main__":
    main()
