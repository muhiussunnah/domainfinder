"""Run the whole expired-domain hunt for one niche, cheapest checks first.

  sources -> availability (free) -> bulk backlinks (cheap) -> deep backlinks on the best N
  -> Google + Bing index on the best N -> Wayback history on the best N (free) -> score -> report

Example:
  python run_pipeline.py --niche "camping gear" --preset outdoor-camping --max-cost 8
  python run_pipeline.py --niche "aquarium" --preset pets-aquarium --free-only
Every stage can also be run on its own; see each script's --help.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import check_availability
import check_history
import check_index
import enrich_backlinks
import import_list
import init_run
import report
import score
import source_commoncrawl
import source_outlinks
import source_whois
from common import BudgetExceeded, dataforseo_credentials, log, setup_console


def stage(name, fn, args):
    log(f"=== {name}: {' '.join(args)}")
    try:
        fn(args)
        return True
    except BudgetExceeded as e:
        log(f"{name} stopped: {e}")
    except SystemExit as e:
        if e.code not in (0, None):
            log(f"{name} stopped: {e}")
    except Exception as e:  # one failing stage should not lose the rest of the run
        log(f"{name} failed: {e!r}")
    return False


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--niche", required=True)
    ap.add_argument("--out")
    ap.add_argument("--preset", action="append", default=[])
    ap.add_argument("--tokens", default="")
    ap.add_argument("--negative", default="")
    ap.add_argument("--expand", action="store_true", help="grow the token list from Amazon/Google keyword ideas (paid)")
    ap.add_argument("--sources", default="", help="comma list: whois,commoncrawl,outlinks (default: whois+commoncrawl, or commoncrawl when free-only)")
    ap.add_argument("--import", dest="imports", action="append", default=[], help="CSV/TXT list to import (repeatable)")
    ap.add_argument("--seed-file", help="seed URLs for the outlinks source")
    ap.add_argument("--tlds", default="com,net,org")
    ap.add_argument("--min-rmd", type=int, default=5)
    ap.add_argument("--cc-file", help="local Common Crawl domain-ranks file")
    ap.add_argument("--cc-max-pos", type=int, default=40_000_000)
    ap.add_argument("--whois-max", type=int, default=1000)
    ap.add_argument("--traffic", action="store_true", help="add Google traffic history (paid)")
    ap.add_argument("--deep", type=int, default=60)
    ap.add_argument("--index-top", type=int, default=100)
    ap.add_argument("--engines", default="google,bing", help="index checks: google (site:) and/or bing (name query)")
    ap.add_argument("--updated-days", type=int, default=30, help="WHOIS expired rows must have been updated this recently")
    ap.add_argument("--max-rmd", type=int, default=1500, help="WHOIS: skip domains with more referring domains (spam networks)")
    ap.add_argument("--history-top", type=int, default=60)
    ap.add_argument("--report-top", type=int, default=25)
    ap.add_argument("--max-cost", type=float, default=5.0, help="DataForSEO budget for this run in USD")
    ap.add_argument("--free-only", action="store_true", help="no DataForSEO calls at all")
    a = ap.parse_args(argv)

    paid = not a.free_only
    if paid and not dataforseo_credentials():
        log("no DataForSEO credentials found: running the free stages only")
        paid = False
    slug = re.sub(r"[^a-z0-9]+", "-", a.niche.lower()).strip("-")
    run = Path(a.out or Path("domain-runs") / slug)
    budget = ["--max-cost", str(a.max_cost)]

    init = ["--niche", a.niche, "--out", str(run), "--tokens", a.tokens, "--negative", a.negative]
    for p in a.preset:
        init += ["--preset", p]
    if a.expand and paid:
        init += ["--expand"] + budget
    if not stage("init", init_run.main, init):
        return

    sources = [s.strip() for s in (a.sources or ("whois,commoncrawl" if paid else "commoncrawl")).split(",") if s.strip()]
    r = ["--run", str(run)]
    if "whois" in sources and paid:
        stage("source:whois", source_whois.main, r + ["--tlds", a.tlds, "--min-rmd", str(a.min_rmd),
                                                       "--max-rmd", str(a.max_rmd), "--updated-days", str(a.updated_days),
                                                       "--max-results", str(a.whois_max)] + budget)
    if "commoncrawl" in sources:
        cc = r + ["--tlds", a.tlds, "--max-pos", str(a.cc_max_pos)]
        if a.cc_file:
            cc += ["--file", a.cc_file]
        stage("source:commoncrawl", source_commoncrawl.main, cc)
    if "outlinks" in sources:
        ol = r + ["--tlds", a.tlds]
        if a.seed_file:
            ol += ["--seed-file", a.seed_file]
        if paid:
            ol += ["--serp"] + budget
        stage("source:outlinks", source_outlinks.main, ol)
    if a.imports:
        stage("import", import_list.main, r + a.imports)

    stage("availability", check_availability.main, r)
    stage("score", score.main, r + ["--min-rmd", str(a.min_rmd)])
    if paid:
        en = r + ["--deep", str(a.deep)] + budget
        if a.traffic:
            en.append("--traffic")
        stage("backlinks", enrich_backlinks.main, en)
        stage("score", score.main, r + ["--min-rmd", str(a.min_rmd)])
        stage("index", check_index.main, r + ["--top", str(a.index_top), "--engines", a.engines] + budget)
    stage("score", score.main, r + ["--min-rmd", str(a.min_rmd)])
    stage("wayback", check_history.main, r + ["--top", str(a.history_top)])
    stage("score", score.main, r + ["--min-rmd", str(a.min_rmd)])
    stage("report", report.main, r + ["--top", str(a.report_top)])
    print(run / "report.html")


if __name__ == "__main__":
    main()
