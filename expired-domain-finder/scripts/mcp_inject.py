"""Merge data fetched through an MCP server (DataForSEO, OpenSEO) into a run's domains.csv.

Use this when Claude has no DataForSEO credentials for the scripts but does have the
DataForSEO MCP (OAuth) in the chat: run the free stages with the scripts, call the API
through the MCP, save each response to a file and merge it here. Every merge keeps the
same column names the scripted stages use, so score.py and report.py need no changes.

  python mcp_inject.py --run RUN bulk FILE [FILE ...]      bulk_ranks / bulk_spam_score / bulk_referring_domains JSON
  python mcp_inject.py --run RUN deep DOMAIN summary=F.json anchors=F.json refdomains=F.json clean=F.json  (any subset)
  python mcp_inject.py --run RUN index ENGINE DOMAIN FILE   a serp/<engine>/organic/live/regular response for site:DOMAIN
  python mcp_inject.py --run RUN whois FILE                 a domain_analytics/whois/overview/live response
  python mcp_inject.py --run RUN fields FILE                {"domain": {"column": value, ...}, ...}
  python mcp_inject.py --run RUN cost ENDPOINT COST [LABEL] append to cost_log.csv (the MCP shows the real cost)
  python mcp_inject.py --run RUN list N [--acquire register,backorder]   best N candidates for the next MCP batch

Responses may be the raw API JSON (with a "tasks" array) or the MCP's trimmed form
({"items": [...]} or {"total_count": n, "items": [...]}).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_niche, load_table, save_table, upsert  # noqa: E402
from enrich_backlinks import anchors_signals, clean_signals, refdomains_signals, summary_signals  # noqa: E402
from check_index import serp_signals  # noqa: E402
from score import ranked  # noqa: E402
from source_whois import whois_fields  # noqa: E402


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def first_result(doc: dict) -> dict:
    """The first result object, whatever shape the response has."""
    if "tasks" in doc:
        for task in doc["tasks"] or []:
            for res in task.get("result") or []:
                return res
        return {}
    return doc


def items_of(doc: dict) -> list:
    return first_result(doc).get("items") or []


def add_cost(run: Path, endpoint: str, cost: str, label: str) -> None:
    p = run / "cost_log.csv"
    new = not p.exists()
    with p.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["time", "endpoint", "label", "cost"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), endpoint, label, cost])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("mode", choices=["bulk", "deep", "index", "whois", "fields", "cost", "list"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--acquire", default="register,backorder,auction,watch,check")
    a = ap.parse_args(argv)
    run = Path(a.run)

    if a.mode == "cost":
        add_cost(run, a.args[0], a.args[1], a.args[2] if len(a.args) > 2 else "mcp")
        return

    table = load_table(run)
    if a.mode == "list":
        want = set(a.acquire.split(","))
        n = int(a.args[0]) if a.args else 50
        for d in [d for d in ranked(table, load_niche(run)) if table[d].get("acquire") in want][:n]:
            print(d)
        return

    changed = 0
    if a.mode == "bulk":
        for f in a.args:
            for it in items_of(load_json(f)):
                d = it.get("target")
                if d not in table:
                    continue
                r = table[d]
                if "rank" in it:
                    r["dfs_rank"] = it.get("rank")
                if "spam_score" in it:
                    r["dfs_spam"] = it.get("spam_score")
                if "referring_main_domains" in it:
                    r["dfs_rd"] = it.get("referring_domains")
                    r["dfs_rmd"] = it.get("referring_main_domains")
                r["dfs_bulk_checked"] = "1"
                changed += 1
    elif a.mode == "deep":
        d = a.args[0].lower()
        if d not in table:
            raise SystemExit(f"{d} is not in the run")
        out: dict = {}
        for arg in a.args[1:]:
            kind, _, f = arg.partition("=")
            if not f:
                raise SystemExit(f"expected kind=file, got {arg!r}")
            doc = load_json(f)
            if kind == "summary":
                s = first_result(doc)
                if "backlinks" not in s and s.get("items"):  # the MCP wraps the summary in items[0]
                    s = s["items"][0]
                out.update(summary_signals(s))
            elif kind == "anchors":
                tokens = [t.lower() for t in load_niche(run)["tokens"]]
                out.update(anchors_signals(items_of(doc), tokens))
            elif kind == "refdomains":
                out.update(refdomains_signals(items_of(doc)))
            elif kind == "clean":
                out.update(clean_signals(first_result(doc)))
            else:
                raise SystemExit(f"unknown kind {kind!r}: use summary, anchors, refdomains or clean")
        table[d].update(out)
        changed = 1
    elif a.mode == "index":
        engine, d, f = a.args[0].lower(), a.args[1].lower(), a.args[2]
        if d not in table:
            raise SystemExit(f"{d} is not in the run")
        table[d].update(serp_signals(engine, d, first_result(load_json(f))))
        changed = 1
    elif a.mode == "whois":
        for it in items_of(load_json(a.args[0])):
            d = (it.get("domain") or "").lower()
            if d:
                upsert(table, d, whois_fields(it), source="whois_mcp")
                changed += 1
    else:
        for d, fields in load_json(a.args[0]).items():
            if d in table:
                table[d].update({k: ("" if v is None else v) for k, v in fields.items()})
                changed += 1
            else:
                print(f"not in table: {d}", file=sys.stderr)
    save_table(run, table)
    print(f"updated {changed} rows")


if __name__ == "__main__":
    main()
