"""Score every candidate 0-100 and apply hard rejects.

score = 30% authority + 25% cleanliness + 20% niche relevance + 15% search index (Google + Bing) + 10% buyability
Each part only uses the data that exists so far, so the same scorer ranks the
cheap first pass (which domains deserve paid checks) and the final shortlist.
"""
from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime
from pathlib import Path

from common import (label_of, load_asset_terms, load_niche, load_table, log, name_match, now_utc,
                    num, save_table, setup_console, suffix_of)

# max_spam: the domain's own (target) spam score, DataForSEO band "low" is 0-30.
# max_bl_spam: the backlink-based spam score (bulk_spam_score and summary backlinks_spam_score are
# this metric); 31-60 is "medium" and usually means a link-selling network hit a fresh drop, so only
# "high" (>60) rejects before the deep pass; after it the clean referring-domain count decides.
DEFAULTS = {"min_rmd": 5, "max_spam": 30, "max_bl_spam": 60, "max_anchor_spam": 0.10,
            "max_anchor_foreign": 0.25, "keep_registered": False}
BUY = {"register": 100, "backorder": 65, "auction": 45, "watch": 25, "check": 30, "registered": 0}

_TERMS: dict[str, list[str]] = {}


def terms(name: str) -> list[str]:
    if name not in _TERMS:
        _TERMS[name] = load_asset_terms(name)
    return _TERMS[name]


def clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, x))


def wavg(parts: list[tuple[float | None, float]]) -> float | None:
    got = [(v, w) for v, w in parts if v is not None]
    if not got:
        return None
    return sum(v * w for v, w in got) / sum(w for _, w in got)


def best_rmd(r: dict) -> float | None:
    """Referring main domains, preferring the clean count (link-selling networks removed)."""
    clean = num(r, "bl_clean_rmd")
    if clean is not None:
        return clean
    vals = [num(r, k) for k in ("bl_rmd", "dfs_rmd", "whois_rmd")]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def age_years(r: dict) -> float | None:
    for k in ("rdap_created", "whois_created"):
        v = (r.get(k) or "")[:10]
        if v:
            try:
                return (now_utc().date() - datetime.fromisoformat(v).date()).days / 365.25
            except ValueError:
                pass
    wf = num(r, "wb_first")
    return (now_utc().year - wf) if wf else None


def authority(r: dict) -> float:
    rank = num(r, "bl_rank", num(r, "dfs_rank"))
    rmd = best_rmd(r)
    pos = num(r, "cc_hc_pos")
    etv = num(r, "hist_peak_etv", num(r, "whois_etv"))
    age = age_years(r)
    wiki = num(r, "wiki_links", num(r, "wiki_pages"))  # Wikipedia articles linking to it (free, exact)
    v = wavg([
        (clamp(rank / 4) if rank is not None else None, 0.30),
        (clamp(33 * math.log10(rmd + 1)) if rmd is not None else None, 0.25),
        (clamp(45 * math.log10(wiki + 1)) if wiki is not None else None, 0.20),
        (clamp(100 - 25 * math.log10(max(pos, 1) / 1e5)) if pos else None, 0.10),
        (clamp(25 * math.log10(etv + 1)) if etv is not None else None, 0.08),
        (clamp(age * 6) if age is not None else None, 0.07),
    ])
    return round(v or 0, 1)


def target_spam(r: dict) -> float | None:
    return num(r, "bl_target_spam")


def link_spam(r: dict) -> float | None:
    vals = [v for v in (num(r, "dfs_spam"), num(r, "bl_backlinks_spam")) if v is not None]
    return max(vals) if vals else None


def cleanliness(r: dict) -> float:
    signals = 0
    s = 100.0
    spam = target_spam(r)
    if spam is not None:
        signals += 1
        s -= spam
    # Link-selling networks hit every fresh drop with thousands of links, so the raw backlink
    # metrics describe the network, not the domain. Once the clean count exists, charge the
    # network itself (up to 25 points) and weigh the raw metrics by the share that is real.
    clean = num(r, "bl_clean_rmd")
    raw = max([v for v in (num(r, "bl_rmd"), num(r, "dfs_rmd")) if v is not None], default=None)
    scale = 1.0
    if clean is not None and raw:
        net = min(1.0, max(0.0, 1 - clean / raw))
        signals += 1
        s -= 25 * net
        scale = 1 - net
    ls = link_spam(r)
    if ls is not None:
        signals += 1
        s -= ls * 0.5 * scale
    for key, mult in (("bl_spam_tld_share", 40), ("rd_spammy_share", 60), ("anc_linkspam_ratio", 15),
                      ("rd_recent_share", 20)):
        v = num(r, key)
        if v is not None:
            signals += 1
            s -= v * mult * scale
    # real spam (casino, pharma, adult anchors; foreign-script anchors) is never discounted
    for key, mult in (("anc_spam_ratio", 300), ("anc_foreign_ratio", 150)):
        v = num(r, key)
        if v is not None:
            signals += 1
            s -= v * mult
    rd, ips = num(r, "bl_rd"), num(r, "bl_ips")
    if rd and ips is not None and rd >= 20 and ips / rd < 0.5:
        s -= 15
    if r.get("wb_checked"):
        signals += 1
        s -= min(15, 3 * (num(r, "wb_parked", 0) or 0))
        s -= 8 * max(0, (num(r, "wb_eras", 1) or 1) - 1)
        if (num(r, "wb_redirects", 0) or 0) > 0:
            s -= 5
    return round(clamp(s), 1) if signals else 50.0


def relevance(r: dict, niche: dict) -> float:
    _, strength = name_match(label_of(r["domain"]), niche["tokens"], niche.get("negative", []))
    s = {"word": 55, "substring": 35}.get(strength, 0)
    distinct = len([t for t in (r.get("wb_niche_tokens") or "").split(",") if t])
    hits = num(r, "wb_niche_hits", 0) or 0
    s += min(35, 9 * distinct + 3 * math.log2(1 + hits))
    s += min(20, 100 * (num(r, "anc_niche_ratio", 0) or 0))
    s += min(15, 5 * (num(r, "outlink_refs", 0) or 0))
    return round(clamp(s), 1)


ENGINES = ("google", "bing")


def index_summary(r: dict) -> str:
    """'both', 'google only', 'bing only', 'google', 'bing', 'none' or '' when unchecked."""
    checked = [e for e in ENGINES if r.get(f"{e}_indexed")]
    yes = [e for e in checked if (r.get(f"{e}_indexed") or "").lower() == "yes"]
    if not checked:
        return ""
    if len(yes) == len(ENGINES):
        return "both"
    if yes:
        return f"{yes[0]} only" if len(checked) == len(ENGINES) else yes[0]
    return "none"


def index_score(r: dict) -> float:
    s = index_summary(r)
    if not s:
        return 35.0
    if s == "none":
        return 0.0
    if (r.get("google_indexed") or "").lower() == "yes":
        v = 60 + 15 * math.log10((num(r, "google_results", 0) or 0) + 1)
    else:  # Bing only: the name-query check is a proxy, so it earns a little less
        v = 50 + 10 * math.log10((num(r, "bing_urls", 0) or 0) + 1)
    if s == "both":
        v += 10
    return round(clamp(v), 1)


def buy_score(r: dict) -> float:
    s = BUY.get(r.get("acquire") or "check", 30)
    label = label_of(r["domain"])
    n = len(label)
    s -= 0 if n <= 10 else 5 if n <= 15 else 15 if n <= 20 else 25
    s -= 15 * label.count("-")
    s -= 10 if any(c.isdigit() for c in label) else 0
    suf = suffix_of(r["domain"])
    s -= 0 if suf == "com" else 5 if suf in ("net", "org") else 10
    return round(clamp(s), 1)


def reject_reasons(r: dict, cfg: dict) -> list[str]:
    out = []
    label = label_of(r["domain"]).lower()
    tm = [t for t in terms("trademarks.txt") if t in label]
    if tm:
        out.append("trademark:" + tm[0])
    sp = [t for t in terms("spam_names.txt") if t in label]
    if sp:
        out.append("spam-name:" + sp[0])
    if r.get("acquire") == "registered" and not cfg["keep_registered"]:
        out.append("registered")
    spam = target_spam(r)
    if spam is not None and spam > cfg["max_spam"]:
        out.append(f"spam-score:{spam:.0f}")
    bls = link_spam(r)
    # the raw backlink spam score is dominated by link-selling networks once the clean count exists
    if bls is not None and bls > cfg["max_bl_spam"] and num(r, "bl_clean_rmd") is None:
        out.append(f"backlink-spam:{bls:.0f}")
    a = num(r, "anc_spam_ratio")
    if a is not None and a > cfg["max_anchor_spam"]:
        out.append(f"spam-anchors:{a:.0%}")
    f = num(r, "anc_foreign_ratio")
    if f is not None and f > cfg["max_anchor_foreign"]:
        out.append(f"foreign-anchors:{f:.0%}")
    for flag in ("wb_spam", "wb_adult", "wb_foreign"):
        if (r.get(flag) or "").strip() not in ("", "0", "no", "False"):
            out.append(f"{flag[3:]}-history:{r.get(flag)}")
    rmd = best_rmd(r)
    if rmd is not None and rmd < cfg["min_rmd"]:
        out.append(f"few-ref-domains:{rmd:.0f}")
    return out


def warnings(r: dict) -> list[str]:
    w = []
    if r.get("wb_checked"):
        if (num(r, "wb_snapshots", 0) or 0) == 0:
            w.append("no Wayback history")
        if (num(r, "wb_parked", 0) or 0) > 0:
            w.append(f"parked in {int(num(r, 'wb_parked'))} snapshot(s)")
        if (num(r, "wb_eras", 1) or 1) >= 3:
            w.append(f"content changed {int(num(r, 'wb_eras')) - 1}x (possible re-use as PBN)")
        if (num(r, "wb_redirects", 0) or 0) > 0:
            w.append("homepage mostly redirected elsewhere in the archive")
    peak, last = num(r, "hist_peak_etv"), num(r, "hist_last_etv")
    if peak and peak > 200 and last is not None and last < 0.05 * peak:
        w.append(f"Google traffic fell from {peak:.0f} to {last:.0f} (site went down or penalty)")
    if (r.get("google_indexed") or "").lower() == "no":
        w.append("not in Google index")
    if (r.get("bing_indexed") or "").lower() == "no":
        w.append("not in Bing (name query; confirm with site: on bing.com)")
    rd, ips = num(r, "bl_rd"), num(r, "bl_ips")
    if rd and ips is not None and rd >= 20 and ips / rd < 0.5:
        w.append("many referring domains share IPs (PBN footprint)")
    ls, recent = num(r, "anc_linkspam_ratio", 0) or 0, num(r, "rd_recent_share", 0) or 0
    if ls > 0.3 or recent > 0.5:
        w.append(f"link-spam network hit ({ls:.0%} link-selling anchors, {recent:.0%} of top referring domains "
                 "appeared in the last 90 days): judge by the clean count, expect these links to vanish")
    bls = link_spam(r)
    if bls is not None and bls > 30:
        w.append(f"backlink spam score {bls:.0f} ({'medium' if bls <= 60 else 'high'}"
                 f"{', inflated by the network above' if ls > 0.3 or recent > 0.5 else ''})")
    return w


def score_row(r: dict, niche: dict, cfg: dict) -> dict:
    parts = {"s_auth": authority(r), "s_clean": cleanliness(r), "s_rel": relevance(r, niche),
             "s_index": index_score(r), "s_buy": buy_score(r)}
    total = (0.30 * parts["s_auth"] + 0.25 * parts["s_clean"] + 0.20 * parts["s_rel"]
             + 0.15 * parts["s_index"] + 0.10 * parts["s_buy"])
    rej = reject_reasons(r, cfg)
    warn = warnings(r)
    idx = index_summary(r)
    verified = bool(r.get("wb_checked")) and idx not in ("", "none")
    tier = "X" if rej else "A" if total >= 70 and len(warn) <= 1 and verified else "B" if total >= 55 else "C"
    return {**parts, "idx_summary": idx, "score": round(total, 1), "tier": tier, "reject": "; ".join(rej),
            "warnings": "; ".join(warn)}


def ranked(table: dict, niche: dict, cfg: dict | None = None, acquirable_only: bool = True) -> list[str]:
    """Domains not rejected, best first. Used by the paid stages to pick what to check."""
    cfg = {**DEFAULTS, **(cfg or {})}
    out = []
    for d, r in table.items():
        sc = score_row(r, niche, cfg)
        if sc["reject"]:
            continue
        if acquirable_only and r.get("acquire") in ("registered",):
            continue
        out.append((sc["score"], d))
    return [d for _, d in sorted(out, reverse=True)]


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--min-rmd", type=int, default=DEFAULTS["min_rmd"])
    ap.add_argument("--max-spam", type=int, default=DEFAULTS["max_spam"])
    ap.add_argument("--max-bl-spam", type=int, default=DEFAULTS["max_bl_spam"])
    ap.add_argument("--keep-registered", action="store_true")
    a = ap.parse_args(argv)
    cfg = {**DEFAULTS, "min_rmd": a.min_rmd, "max_spam": a.max_spam, "max_bl_spam": a.max_bl_spam,
           "keep_registered": a.keep_registered}
    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    for r in table.values():
        r.update(score_row(r, niche, cfg))
    save_table(run, table)
    rows = sorted(table.values(), key=lambda r: (r["tier"] == "X", -float(r["score"])))
    cols = ["domain", "tier", "score", "acquire", "s_auth", "s_clean", "s_rel", "s_index", "s_buy",
            "idx_summary", "google_indexed", "google_results", "bing_indexed", "bing_urls",
            "wiki_links", "wiki_link_titles", "bl_rank", "dfs_rank", "bl_clean_rmd", "bl_rmd", "dfs_rmd", "whois_rmd",
            "dfs_spam", "bl_backlinks_spam", "anc_linkspam_ratio", "wb_first", "wb_last", "wb_niche_hits",
            "reject", "warnings"]
    with (run / "shortlist.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            if r["tier"] != "X":
                w.writerow(r)
    tiers: dict[str, int] = {}
    for r in table.values():
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    log("tiers: " + ", ".join(f"{k}={v}" for k, v in sorted(tiers.items())))


if __name__ == "__main__":
    main()
