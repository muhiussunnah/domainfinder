"""Check each shortlisted domain's past on the Wayback Machine (free).

For every domain: monthly homepage captures, how many distinct HTML pages were archived,
and a sample of one homepage per year (spread over its life). Each sample is read
for parking pages, spam/adult content, foreign-script takeovers (e.g. the Japanese
keyword hack) and niche words, and title changes are grouped into "eras" to spot
domains that were dropped and re-used, often as PBN sites.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import (find_terms, foreign_ratio, http_request, load_asset_terms, load_niche, load_table,
                    log, parallel_map, parse_html, save_table, setup_console)
from score import ranked

CDX = "https://web.archive.org/cdx/search/cdx"
ACQUIRABLE = {"register", "backorder", "auction", "watch", "check"}
PARKED = ["domain is for sale", "this domain may be for sale", "buy this domain", "domain for sale",
          "is for sale!", "parked free", "parkingcrew", "sedoparking", "sedo domain parking", "bodis",
          "hugedomains", "dan.com", "afternic", "this domain has expired", "domain has been registered",
          "related searches", "parked domain", "future home of", "coming soon", "under construction",
          "website is for sale", "make an offer", "godaddy.com/domainsearch",
          "this web page is parked", "domain parking", "renew now", "this domain name has expired"]
ADULT = ["porn", "xxx", "sex cam", "escort", "nude", "hentai", "milf", "camgirl", "onlyfans leak", "bokep", "jav "]
WAYBACK_INTERVAL = 0.8


def cdx_rows(params: dict) -> tuple[int, list]:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    status, body, _ = http_request(f"{CDX}?{q}", timeout=60, retries=3, min_interval=WAYBACK_INTERVAL)
    if status != 200:
        return status, []
    try:
        data = json.loads(body.decode("utf-8", "replace") or "[]")
    except Exception:
        return status, []
    return status, data[1:] if data and data[0] and data[0][0] == "timestamp" else data


def page_count(domain: str) -> int | None:
    status, body, _ = http_request(
        f"{CDX}?url={domain}&matchType=domain&fl=urlkey&collapse=urlkey&filter=statuscode:200"
        f"&filter=mimetype:text/html&limit=2000", timeout=90, retries=2, min_interval=WAYBACK_INTERVAL)
    if status != 200:
        return None
    return len([ln for ln in body.decode("utf-8", "replace").splitlines() if ln.strip()])


def pick_samples(rows: list, k: int) -> list:
    by_year: dict[str, list] = {}
    for r in rows:
        by_year.setdefault(r[0][:4], []).append(r)
    years = sorted(by_year)
    if len(years) > k:
        idx = sorted({round(i * (len(years) - 1) / (k - 1)) for i in range(k)})
        years = [years[i] for i in idx]
    return [by_year[y][len(by_year[y]) // 2] for y in years]


def words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", title.lower()) if w not in {"the", "and", "for", "home", "welcome", "page"}}


def history(domain: str, tokens: list[str], spam_terms: list[str], samples: int) -> dict:
    status, rows = cdx_rows({"url": domain, "output": "json",
                             "fl": "timestamp,original,statuscode,mimetype,digest",
                             "collapse": "timestamp:6", "limit": "800"})
    out: dict = {"wb_checked": "1"}
    if status in (403, 451):
        out["wb_blocked"] = "1"
        return out
    ok = [r for r in rows if len(r) >= 3 and r[2] == "200"]
    redirects = sum(1 for r in rows if len(r) >= 3 and r[2].startswith("3"))
    out["wb_snapshots"] = len(ok)
    # http->https and www redirects are normal; only a homepage that mostly redirected matters
    out["wb_redirects"] = redirects if redirects > len(ok) else 0
    if not ok:
        return out
    years = sorted({r[0][:4] for r in ok})
    out.update({"wb_first": years[0], "wb_last": years[-1], "wb_years": len(years)})
    out["wb_pages"] = page_count(domain)

    parked = 0
    spam_hits: dict[str, str] = {}
    adult_hits: list[str] = []
    foreign: list[str] = []
    niche_hits = 0
    niche_tokens: set[str] = set()
    titles: list[str] = []
    langs: set[str] = set()
    eras = 0
    prev: set[str] | None = None
    for ts, original, *_ in pick_samples(ok, samples):
        st, body, _ = http_request(f"https://web.archive.org/web/{ts}id_/{original}", timeout=45, retries=2,
                                   min_interval=WAYBACK_INTERVAL, max_bytes=1_500_000)
        if st != 200 or not body:
            continue
        p = parse_html(body)
        yr = ts[:4]
        head = " ".join([p["title"], p["meta"], " ".join(p["h1"])])
        sample_text = (head + " " + p["text"][:6000])
        low = sample_text.lower()
        if p["lang"]:
            langs.add(p["lang"][:2])
        is_parked = any(x in low for x in PARKED) and len(p["text"]) < 4000
        if is_parked:
            parked += 1
        sp = find_terms(sample_text, spam_terms)
        if len(sp) >= 2 or find_terms(head, spam_terms):
            spam_hits[yr] = ",".join(sp[:3])
        ad = [x for x in ADULT if x in low]
        if ad:
            adult_hits.append(f"{yr}:{ad[0].strip()}")
        fr = foreign_ratio(p["text"][:5000])
        if fr > 0.3:
            foreign.append(f"{yr}:{p['lang'] or 'non-latin'}")
        found = {t for t in tokens if t in low}
        niche_tokens |= found
        niche_hits += sum(low.count(t) for t in found)
        title = p["title"] or (p["h1"][0] if p["h1"] else "")
        titles.append(f"{yr}: {title[:70] or '(no title)'}{' [parked]' if is_parked else ''}")
        if not is_parked:
            w = words(title)
            if w and (prev is None or len(w & prev) / max(1, len(w | prev)) < 0.2):
                eras += 1
            if w:
                prev = w
    out.update({
        "wb_parked": parked,
        "wb_spam": "; ".join(f"{y}:{t}" for y, t in spam_hits.items()),
        "wb_adult": "; ".join(adult_hits),
        "wb_foreign": "; ".join(foreign),
        "wb_niche_hits": niche_hits,
        "wb_niche_tokens": ",".join(sorted(niche_tokens)),
        "wb_eras": max(eras, 1),
        "wb_titles": " | ".join(titles),
        "wb_lang": ",".join(sorted(langs)),
    })
    return out


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--top", type=int, default=60, help="check the best N acquirable candidates")
    ap.add_argument("--domains", default="", help="comma-separated domains to check instead of the top N")
    ap.add_argument("--samples", type=int, default=6, help="homepage captures to read per domain")
    ap.add_argument("--workers", type=int, default=3, help="keep low; the Wayback Machine rate-limits")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    if a.domains:
        todo = [x for x in (d.strip().lower() for d in a.domains.split(",")) if x in table]
    else:
        todo = [d for d in ranked(table, niche) if table[d].get("acquire") in ACQUIRABLE][: a.top]
    todo = [d for d in todo if a.force or not table[d].get("wb_checked")]
    log(f"wayback: {len(todo)} domains (about {len(todo) * 8 // 60 + 1} min)")
    spam_terms = load_asset_terms("spam_terms.txt")
    tokens = [t.lower() for t in niche["tokens"]]
    done = 0
    for d, res, err in parallel_map(lambda x: history(x, tokens, spam_terms, a.samples), todo,
                                    workers=a.workers, desc="wayback", every=5):
        if res:
            table[d].update(res)
        elif err:
            log(f"wayback {d}: {err}")
        done += 1
        if done % 10 == 0:
            save_table(run, table)
    save_table(run, table)


if __name__ == "__main__":
    main()
