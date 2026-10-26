"""Source candidates from the Common Crawl domain-level web graph (free).

The ranks file lists every domain that appears in the crawl's link graph, including
dead domains that are only known because live pages still link to them. Streaming
it and keeping niche-named domains gives a large pool of "still linked, maybe
dropped" names; check_availability.py then finds the ones you can register.

The file is ~2.4 GB gzipped and sorted by harmonic centrality, so --max-pos stops
early once you are past the authority band you care about.
"""
from __future__ import annotations

import argparse
import gzip
import io
import re
import urllib.request
from pathlib import Path

from common import (UA, http_request, load_niche, load_table, log, name_match, parse_tlds,
                    save_table, setup_console, suffix_of, upsert, MULTI_SUFFIXES)

GRAPH_BASE = "https://data.commoncrawl.org/projects/hyperlinkgraph"
FALLBACK_RELEASE = "cc-main-2026-aug-sep-oct"


def latest_release() -> str:
    status, body, _ = http_request("https://commoncrawl.org/web-graphs", timeout=30, retries=2)
    if status == 200:
        m = re.findall(r"cc-main-\d{4}-[a-z]{3}-[a-z]{3}-[a-z]{3}", body.decode("utf-8", "replace"))
        if m:
            return m[0]
    return FALLBACK_RELEASE


def unreverse(host_rev: str) -> str:
    parts = host_rev.split(".")
    return ".".join(reversed(parts))


def open_stream(a):
    if a.file:
        log(f"reading local file {a.file}")
        return gzip.open(a.file, "rt", encoding="utf-8", errors="replace")
    release = a.release if a.release != "latest" else latest_release()
    url = f"{GRAPH_BASE}/{release}/domain/{release}-domain-ranks.txt.gz"
    log(f"streaming {url}")
    resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120)
    return io.TextIOWrapper(gzip.GzipFile(fileobj=resp), encoding="utf-8", errors="replace")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--release", default="latest", help="web graph release, e.g. cc-main-2026-aug-sep-oct")
    ap.add_argument("--file", help="local copy of *-domain-ranks.txt.gz (skips the download)")
    ap.add_argument("--tlds", default="com,net,org")
    ap.add_argument("--max-pos", type=int, default=40_000_000, help="stop after this harmonic-centrality position")
    ap.add_argument("--min-pos", type=int, default=20_000, help="skip the top N (giant sites never drop)")
    ap.add_argument("--max-hosts", type=int, default=50, help="skip domains with more hosts than this (live platforms)")
    ap.add_argument("--max-keep", type=int, default=30_000, help="stop after keeping this many candidates")
    ap.add_argument("--word-only", action="store_true", help="keep only names where a token is a whole word (needs wordninja)")
    a = ap.parse_args(argv)
    setup_console()

    run = Path(a.run)
    niche = load_niche(run)
    tokens, negative = niche["tokens"], niche.get("negative", [])
    tok_re = re.compile("|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)))
    tlds = parse_tlds(a.tlds)
    rev_prefixes = tuple(".".join(reversed(t.split("."))) + "." for t in tlds)
    table = load_table(run)

    kept = scanned = 0
    stream = open_stream(a)
    try:
        for line in stream:
            if line.startswith("#"):
                continue
            scanned += 1
            if scanned % 5_000_000 == 0:
                log(f"scanned {scanned:,} lines, kept {kept:,}")
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5:
                continue
            pos = int(cols[0])
            if pos > a.max_pos:
                break
            if pos < a.min_pos:
                continue
            host_rev = cols[4]
            if not host_rev.startswith(rev_prefixes):
                continue
            n_hosts = int(cols[5]) if len(cols) > 5 and cols[5].isdigit() else 0
            if n_hosts > a.max_hosts:
                continue
            domain = unreverse(host_rev)
            suf = suffix_of(domain)
            if suf not in tlds or (domain.count(".") > 1 and suf not in MULTI_SUFFIXES):
                continue
            label = domain[: -(len(suf) + 1)]
            if not tok_re.search(label):
                continue
            hits, strength = name_match(label, tokens, negative)
            if not hits or (a.word_only and strength != "word"):
                continue
            upsert(table, domain, {
                "cc_hc_pos": pos,
                "cc_hc_val": cols[1],
                "cc_pr_pos": cols[2],
                "cc_hosts": n_hosts,
            }, source="commoncrawl")
            kept += 1
            if kept >= a.max_keep:
                log("reached --max-keep")
                break
    except Exception as e:  # network hiccup: keep what we have
        log(f"stream stopped early: {e}")
    finally:
        try:
            stream.close()
        except Exception:
            pass
    save_table(run, table)
    log(f"commoncrawl: scanned {scanned:,} lines, kept {kept:,}; table now {len(table):,} domains")


if __name__ == "__main__":
    main()
