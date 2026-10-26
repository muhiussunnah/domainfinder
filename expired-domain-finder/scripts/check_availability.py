"""Check whether each candidate can be bought, for free: DNS over HTTPS, then RDAP
(the registry's official successor to WHOIS).

acquire column:
  register  - not registered: hand-register at normal price (cheapest)
  backorder - pendingDelete / redemption: drops soon, backorder at DropCatch/SnapNames/NameJet
  auction   - past expiry but still held by the registrar: look on GoDaddy/NameJet/Dynadot auctions
  watch     - on hold, status unclear
  registered- someone owns it (skipped unless you imported it from an auction list)
  check     - lookup failed; verify manually
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from common import (get_json, http_request, load_table, log, now_utc, parallel_map, save_table,
                    setup_console, suffix_of)

BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"


def rdap_bases(run: Path) -> dict[str, str]:
    cache = run / "rdap_bootstrap.json"
    data = None
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        status, data = get_json(BOOTSTRAP_URL, timeout=30)
        if data:
            cache.write_text(json.dumps(data), encoding="utf-8")
    bases = {}
    for tlds, urls in (data or {}).get("services", []):
        url = next((u for u in urls if u.startswith("https")), urls[0] if urls else None)
        for t in tlds:
            if url:
                bases[t.lower()] = url if url.endswith("/") else url + "/"
    return bases


def dns_check(domain: str) -> str:
    for url in (f"https://cloudflare-dns.com/dns-query?name={domain}&type=NS",
                f"https://dns.google/resolve?name={domain}&type=NS"):
        status, data = get_json(url, headers={"Accept": "application/dns-json"}, timeout=15, retries=2,
                                min_interval=0.01)
        if status == 200 and isinstance(data, dict):
            st = data.get("Status")
            if st == 3:
                return "nxdomain"
            if st == 0:
                return "ns" if data.get("Answer") or data.get("Authority") else "noanswer"
            if st == 2:  # SERVFAIL: lame delegation, often an expired domain still in the zone
                return "servfail"
    return "error"


def parse_rdap(doc: dict) -> dict:
    statuses = [s.lower() for s in doc.get("status") or []]
    events = {e.get("eventAction"): (e.get("eventDate") or "")[:10] for e in doc.get("events") or []}
    registrar = ""
    for ent in doc.get("entities") or []:
        if "registrar" in (ent.get("roles") or []):
            for item in (ent.get("vcardArray") or [None, []])[1]:
                if item and item[0] == "fn":
                    registrar = item[3]
    return {"statuses": statuses, "expiration": events.get("expiration", ""),
            "created": events.get("registration", ""), "registrar": registrar}


def classify(info: dict) -> str:
    s = " ".join(info["statuses"])
    if "pending delete" in s or "pendingdelete" in s:
        return "pending_delete"
    if "redemption" in s:
        return "redemption"
    exp = info.get("expiration")
    expired = None
    if exp:
        try:
            expired = datetime.fromisoformat(exp).date() < now_utc().date()
        except ValueError:
            pass
    if expired:
        return "expired_grace"
    # a hold on a domain whose expiry is still ahead is the owner's or registrar's problem,
    # not a drop in progress: it is registered, and never a candidate
    if ("server hold" in s or "client hold" in s) and expired is None:
        return "on_hold"
    return "registered"


ACQUIRE = {"available": "register", "likely_available": "register", "pending_delete": "backorder",
           "redemption": "backorder", "expired_grace": "auction", "on_hold": "watch",
           "registered": "registered", "unknown": "check"}


def rdap_check(domain: str, bases: dict[str, str]) -> dict:
    base = bases.get(suffix_of(domain).split(".")[-1])
    if not base:
        return {"rdap_status": "no_rdap"}
    url = f"{base}domain/{domain}"
    status, body, _ = http_request(url, headers={"Accept": "application/rdap+json"}, timeout=20,
                                   retries=3, min_interval=0.15)
    if status == 404:
        return {"rdap_status": "available"}
    if status == 200:
        try:
            info = parse_rdap(json.loads(body.decode("utf-8", "replace")))
        except Exception:
            return {"rdap_status": "unknown"}
        return {"rdap_status": classify(info), "rdap_expiration": info["expiration"],
                "rdap_created": info["created"], "rdap_registrar": info["registrar"],
                "rdap_flags": ";".join(info["statuses"])[:200]}
    return {"rdap_status": "unknown", "rdap_error": f"HTTP {status}"}


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--rdap-all", action="store_true", help="also RDAP domains whose DNS still answers")
    ap.add_argument("--force", action="store_true", help="re-check rows already checked")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args(argv)

    run = Path(a.run)
    table = load_table(run)
    todo = [d for d, r in table.items() if a.force or not r.get("acquire")]
    log(f"availability: {len(todo)} of {len(table)} to check")

    for d, res, err in parallel_map(dns_check, todo, workers=a.workers * 2, desc="dns", every=500):
        table[d]["dns"] = res if not err else "error"
    save_table(run, table)

    bases = rdap_bases(run)

    def needs_rdap(d):
        r = table[d]
        src = r.get("sources") or ""
        return a.rdap_all or r.get("dns") != "ns" or "whois" in src or "import:" in src

    rdap_todo = [d for d in todo if needs_rdap(d)]
    log(f"rdap: {len(rdap_todo)} lookups")
    for d, res, err in parallel_map(lambda x: rdap_check(x, bases), rdap_todo, workers=a.workers,
                                    desc="rdap", every=200):
        if err or not res:
            res = {"rdap_status": "unknown"}
        if res.get("rdap_status") == "no_rdap":
            res["rdap_status"] = "likely_available" if table[d].get("dns") == "nxdomain" else "unknown"
        table[d].update(res)

    counts: dict[str, int] = {}
    for d in todo:
        r = table[d]
        st = r.get("rdap_status") or ("registered" if r.get("dns") == "ns" else "unknown")
        r["rdap_status"] = st
        acq = ACQUIRE.get(st, "check")
        if acq == "registered" and "import:" in (r.get("sources") or ""):
            acq = "auction"  # auction/backorder lists contain registered names on purpose
        r["acquire"] = acq
        counts[acq] = counts.get(acq, 0) + 1
    save_table(run, table)
    log("availability: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
