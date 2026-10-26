"""Add backlink and traffic-history data from DataForSEO.

Bulk pass (all acquirable candidates, 1,000 per request, ~$0.06 per 1,000):
  bulk_ranks, bulk_spam_score, bulk_referring_domains, and optional
  historical_bulk_traffic_estimation (--traffic, $0.12 + $0.0012 per domain).
Deep pass (--deep N best candidates, ~$0.10 per domain):
  summary, anchors, referring domains, and a *clean* referring-domain count that
  leaves out link-selling networks (spammy links, spam TLDs, "premium backlinks"
  anchors). Freshly dropped domains routinely pick up 1,500-3,000 such links within
  weeks, which inflates every raw count and spam score; the clean count is what the
  domain's real history looks like.

The Backlinks endpoints need an active Backlinks API subscription on the
DataForSEO account. Without one the stage logs it and moves on.
"""
from __future__ import annotations

import argparse
import math
from datetime import timedelta
from pathlib import Path

from common import (DataForSEO, DataForSEOError, chunks, find_terms, first_result, foreign_ratio,
                    load_asset_terms, load_niche, load_table, log, now_utc, parallel_map, save_table,
                    setup_console)
from score import ranked

ACQUIRABLE = {"register", "backorder", "auction", "watch", "check"}
SPAM_TLDS = {"ru", "cn", "xyz", "top", "pw", "tk", "ml", "ga", "cf", "gq", "su", "icu", "click", "loan",
             "work", "site", "online", "buzz", "monster", "rest", "cyou", "cfd", "sbs", "bid", "win", "vip",
             "store", "shop", "space", "link", "party", "world"}
# backlinks_filters for referring_domains/live: the dataset behind the "clean" count
CLEAN_FILTERS = [["backlink_spam_score", "<", 40], "and",
                 ["tld_from", "not_in", sorted(SPAM_TLDS)], "and",
                 ["anchor", "not_ilike", "%backlink%"], "and",
                 ["anchor", "not_ilike", "%link building%"], "and",
                 ["anchor", "not_ilike", "%pbn%"]]
RECENT_DAYS = 90


class Backlinks:
    def __init__(self, dfs: DataForSEO):
        self.dfs = dfs
        self.disabled = ""

    def post(self, endpoint, task, label, estimate):
        if self.disabled:
            return None
        try:
            return self.dfs.post(endpoint, task, label=label, estimate=estimate)
        except DataForSEOError as e:
            if e.is_access_problem:
                self.disabled = str(e)
                log(f"Backlinks API unavailable, skipping backlink checks: {e}")
            else:
                log(f"{endpoint} {label}: {e}")
            return None


def bulk_pass(bl: Backlinks, table: dict, domains: list[str]) -> None:
    for group in chunks(domains, 1000):
        est = 0.024 + 0.000036 * len(group)
        t = bl.post("backlinks/bulk_ranks/live", {"targets": group, "rank_scale": "one_thousand"}, "bulk_ranks", est)
        for it in (first_result(t).get("items") or []) if t else []:
            if it.get("target") in table:
                table[it["target"]]["dfs_rank"] = it.get("rank")
        t = bl.post("backlinks/bulk_spam_score/live", {"targets": group}, "bulk_spam_score", est)
        for it in (first_result(t).get("items") or []) if t else []:
            if it.get("target") in table:
                table[it["target"]]["dfs_spam"] = it.get("spam_score")
        t = bl.post("backlinks/bulk_referring_domains/live", {"targets": group}, "bulk_referring_domains", est)
        for it in (first_result(t).get("items") or []) if t else []:
            if it.get("target") in table:
                r = table[it["target"]]
                r["dfs_rd"] = it.get("referring_domains")
                r["dfs_rmd"] = it.get("referring_main_domains")
        for d in group:
            table[d]["dfs_bulk_checked"] = "1"
        log(f"bulk backlinks: {len(group)} domains, run spend ${bl.dfs.spent:.2f}")


def traffic_pass(dfs: DataForSEO, table: dict, domains: list[str], location_code: int) -> None:
    for group in chunks(domains, 1000):
        try:
            t = dfs.post("dataforseo_labs/google/historical_bulk_traffic_estimation/live",
                         {"targets": group, "location_code": location_code, "language_code": "en",
                          "date_from": "2020-10-01"},
                         label="historical_traffic", estimate=0.12 + 0.0012 * len(group))
        except DataForSEOError as e:
            log(f"historical traffic skipped: {e}")
            return
        for it in first_result(t).get("items") or []:
            d = it.get("target")
            if d not in table:
                continue
            series = sorted(((m.get("year", 0), m.get("month", 0), m.get("etv") or 0)
                             for m in ((it.get("metrics") or {}).get("organic") or [])), key=lambda x: (x[0], x[1]))
            r = table[d]
            r["hist_checked"] = "1"
            if not series:
                continue
            peak = max(series, key=lambda x: x[2])
            r["hist_peak_etv"] = round(peak[2], 1)
            r["hist_peak_month"] = f"{peak[0]}-{peak[1]:02d}"
            r["hist_last_etv"] = round(series[-1][2], 1)
            r["hist_months"] = sum(1 for s in series if s[2] > 0)
        log(f"historical traffic: {len(group)} domains, run spend ${dfs.spent:.2f}")


# --------------------------------------------------------------------------- deep signals
# Each function turns one API response into table columns, so mcp_inject.py can reuse them
# for responses fetched through the DataForSEO MCP.

def summary_signals(s: dict) -> dict:
    """backlinks/summary/live result -> bl_* columns."""
    if not s:
        return {}
    backlinks = s.get("backlinks") or 0
    tld = s.get("referring_links_tld") or {}
    tld_total = sum(v for v in tld.values() if isinstance(v, (int, float))) or 0
    attrs = s.get("referring_links_attributes") or {}
    plat = s.get("referring_links_platform_types") or {}
    loc = s.get("referring_links_semantic_locations") or {}
    loc_total = sum(v for v in loc.values() if isinstance(v, (int, float))) or 0
    info = s.get("info") or {}  # the domain's own spam score lives under info
    return {
        "bl_deep_checked": "1",
        "bl_rank": s.get("rank"), "bl_backlinks": backlinks, "bl_rd": s.get("referring_domains"),
        "bl_rmd": s.get("referring_main_domains"), "bl_ips": s.get("referring_ips"),
        "bl_subnets": s.get("referring_subnets"),
        "bl_target_spam": info.get("target_spam_score", s.get("target_spam_score")),
        "bl_backlinks_spam": s.get("backlinks_spam_score"), "bl_broken": s.get("broken_backlinks"),
        "bl_first_seen": (s.get("first_seen") or "")[:10],
        "bl_spam_tld_share": round(sum(v for k, v in tld.items() if k.lower() in SPAM_TLDS) / tld_total, 3) if tld_total else "",
        "bl_nofollow_share": round((attrs.get("nofollow") or 0) / backlinks, 3) if backlinks else "",
        "bl_footer_share": round((loc.get("footer") or 0) / loc_total, 3) if loc_total else "",
        "bl_platforms": ", ".join(f"{k}:{v}" for k, v in sorted(plat.items(), key=lambda x: -x[1])[:4]),
    }


def anchors_signals(items: list, tokens: list[str], spam_terms: list[str] | None = None,
                    linkspam_terms: list[str] | None = None) -> dict:
    """backlinks/anchors/live items -> anc_* columns (weights = referring domains per anchor)."""
    if not items:
        return {}
    spam_terms = spam_terms if spam_terms is not None else load_asset_terms("spam_terms.txt")
    linkspam_terms = linkspam_terms if linkspam_terms is not None else load_asset_terms("linkspam_terms.txt")
    tot = spam = linkspam = foreign = niche = 0.0
    top = []
    for it in items:
        a = (it.get("anchor") or "").strip()
        w = float(it.get("referring_domains") or 1)
        tot += w
        if find_terms(a, linkspam_terms):
            linkspam += w
        elif find_terms(a, spam_terms):
            spam += w
        if foreign_ratio(a) > 0.3:
            foreign += w
        if any(tk in a.lower() for tk in tokens):
            niche += w
        if len(top) < 6:
            top.append(f"{a[:40] or '(empty)'} [{int(w)}]")
    return {"anc_spam_ratio": round(spam / tot, 3), "anc_linkspam_ratio": round(linkspam / tot, 3),
            "anc_foreign_ratio": round(foreign / tot, 3), "anc_niche_ratio": round(niche / tot, 3),
            "anc_top": " | ".join(top)}


def refdomains_signals(items: list, recent_days: int = RECENT_DAYS) -> dict:
    """backlinks/referring_domains/live items (best by rank) -> rd_* columns."""
    if not items:
        return {}
    cutoff = (now_utc() - timedelta(days=recent_days)).strftime("%Y-%m-%d")
    spammy = sum(1 for it in items if (it.get("backlinks_spam_score") or 0) >= 50)
    strong = [it for it in items if (it.get("rank") or 0) >= 300]
    edu_gov = sum(1 for it in items if any((it.get("domain") or "").endswith(x) for x in (".edu", ".gov", ".ac.uk", ".gov.uk")))
    recent = sum(1 for it in items if (it.get("first_seen") or "")[:10] >= cutoff)
    return {"rd_spammy_share": round(spammy / len(items), 3), "rd_strong": len(strong), "rd_edu_gov": edu_gov,
            "rd_recent_share": round(recent / len(items), 3),
            "rd_top": " | ".join(f"{it.get('domain')} ({it.get('rank')})" for it in items[:6])}


def clean_signals(res: dict) -> dict:
    """referring_domains/live result fetched with CLEAN_FILTERS -> the real referring-domain count."""
    if not res:
        return {}
    items = res.get("items") or []
    out = {"bl_clean_rmd": res.get("total_count") if res.get("total_count") is not None else len(items)}
    if items:
        out["rd_clean_top"] = " | ".join(f"{it.get('domain')} ({it.get('rank')})" for it in items[:6])
        out["rd_clean_strong"] = sum(1 for it in items if (it.get("rank") or 0) >= 300)
    return out


def deep_one(bl: Backlinks, d: str, tokens: list[str], spam_terms: list[str], linkspam_terms: list[str]) -> dict:
    out: dict = {}
    t = bl.post("backlinks/summary/live", {"target": d, "include_subdomains": True,
                                            "backlinks_status_type": "live", "rank_scale": "one_thousand"},
                f"summary:{d}", 0.025)
    out.update(summary_signals(first_result(t) if t else {}))
    t = bl.post("backlinks/anchors/live", {"target": d, "limit": 100, "order_by": ["referring_domains,desc"],
                                            "include_subdomains": True}, f"anchors:{d}", 0.03)
    out.update(anchors_signals((first_result(t).get("items") or []) if t else [], tokens, spam_terms, linkspam_terms))
    t = bl.post("backlinks/referring_domains/live", {"target": d, "limit": 100, "order_by": ["rank,desc"],
                                                      "include_subdomains": True}, f"refdomains:{d}", 0.03)
    out.update(refdomains_signals((first_result(t).get("items") or []) if t else []))
    # backlinks_filters drops the spam links before counting; filters then drops referring domains
    # whose remaining links still average a medium/high spam score
    t = bl.post("backlinks/referring_domains/live", {"target": d, "limit": 20, "order_by": ["rank,desc"],
                                                      "include_subdomains": True, "backlinks_filters": CLEAN_FILTERS,
                                                      "filters": ["backlinks_spam_score", "<", 40]},
                f"clean:{d}", 0.025)
    out.update(clean_signals(first_result(t) if t else {}))
    return out


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--bulk-limit", type=int, default=5000, help="max candidates for the bulk pass")
    ap.add_argument("--traffic", action="store_true", help="add Google traffic history (paid)")
    ap.add_argument("--deep", type=int, default=0, help="run summary/anchors/referring domains/clean count on the best N")
    ap.add_argument("--domains", default="", help="comma-separated domains for the deep pass instead of the best N")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-cost", type=float, default=None)
    a = ap.parse_args(argv)

    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    dfs = DataForSEO(run, max_cost=a.max_cost)
    bl = Backlinks(dfs)

    pool = [d for d in ranked(table, niche) if table[d].get("acquire") in ACQUIRABLE]
    bulk = [d for d in pool if a.force or not table[d].get("dfs_bulk_checked")][: a.bulk_limit]
    try:
        log(f"bulk pass: {len(bulk)} domains (~${math.ceil(len(bulk) / 1000) * 3 * 0.06:.2f})")
        if bulk:
            bulk_pass(bl, table, bulk)
            save_table(run, table)
        if a.traffic:
            todo = [d for d in pool[: a.bulk_limit] if a.force or not table[d].get("hist_checked")]
            traffic_pass(dfs, table, todo, niche.get("location_code", 2840))
            save_table(run, table)
        if (a.deep or a.domains) and not bl.disabled:
            if a.domains:
                top = [x for x in (d.strip().lower() for d in a.domains.split(",")) if x in table]
            else:
                top = [d for d in ranked(table, niche) if table[d].get("acquire") in ACQUIRABLE][: a.deep]
            todo = [d for d in top if a.force or not table[d].get("bl_deep_checked")]
            log(f"deep pass: {len(todo)} domains (~${len(todo) * 0.11:.2f})")
            spam_terms = load_asset_terms("spam_terms.txt")
            linkspam_terms = load_asset_terms("linkspam_terms.txt")
            tokens = [t.lower() for t in niche["tokens"]]
            for d, res, err in parallel_map(lambda x: deep_one(bl, x, tokens, spam_terms, linkspam_terms), todo,
                                            workers=a.workers, desc="deep", every=10):
                if res:
                    table[d].update(res)
                elif err:
                    log(f"deep {d}: {err}")
    finally:
        save_table(run, table)
    log(f"enrich done, run spend ${dfs.spent:.2f}")


if __name__ == "__main__":
    main()
