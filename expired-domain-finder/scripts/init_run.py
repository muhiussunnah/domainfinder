"""Create a run folder and the niche token list used to match domain names.

Examples:
  python init_run.py --niche "camping gear" --preset outdoor-camping --out domain-runs/camping
  python init_run.py --niche "espresso machines" --tokens espresso,coffee,barista,brew --expand
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from common import ASSETS, DataForSEO, DataForSEOError, load_lines, log, now_utc, setup_console

STOP = set("""a an and are as at be best buy by cheap for from get good how in is it near of on or our
the this to top under vs what which who why with without your you my me i we review reviews online shop store
sale deal deals price prices discount coupon amazon walmart ebay target com www near 2020 2021 2022 2023 2024
2025 2026 2027 inch pack set kit size small large mini pro plus new used men women kids black white""".split())


def presets() -> list[str]:
    return sorted(p.stem for p in (ASSETS / "niches").glob("*.txt"))


def expand_tokens(niche: str, seeds: list[str], run_dir: Path, location_code: int, max_cost: float | None,
                  limit: int = 300, top: int = 40) -> list[str]:
    """Pull Amazon + Google keyword ideas and keep the most frequent meaningful words."""
    dfs = DataForSEO(run_dir, max_cost=max_cost)
    phrases: list[str] = []
    for kw in [niche] + seeds[:2]:
        for endpoint, task in (
            ("dataforseo_labs/amazon/related_keywords/live",
             {"keyword": kw.lower(), "location_code": location_code, "language_code": "en", "depth": 2, "limit": limit}),
            ("dataforseo_labs/google/keyword_suggestions/live",
             {"keyword": kw.lower(), "location_code": location_code, "language_code": "en", "limit": limit}),
        ):
            try:
                t = dfs.post(endpoint, task, label=f"expand:{kw}", estimate=0.06)
            except DataForSEOError as e:
                log(f"keyword expansion skipped for {endpoint}: {e}")
                if e.is_access_problem:
                    return []
                continue
            for res in t.get("result") or []:
                for item in res.get("items") or []:
                    kd = item.get("keyword_data") or item
                    if kd.get("keyword"):
                        phrases.append(kd["keyword"])
                    for rk in item.get("related_keywords") or []:
                        if isinstance(rk, str):
                            phrases.append(rk)
    counts = Counter()
    for ph in phrases:
        for w in re.findall(r"[a-z]+", ph.lower()):
            if len(w) >= 4 and w not in STOP:
                counts[w] += 1
    log(f"expansion: {len(phrases)} phrases, ${dfs.spent:.3f} spent")
    return [w for w, _ in counts.most_common(top)]


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--niche", required=True, help="niche in plain words, e.g. 'camping gear'")
    ap.add_argument("--out", help="run folder (default domain-runs/<niche-slug>)")
    ap.add_argument("--preset", action="append", default=[], help=f"token preset(s): {', '.join(presets())}")
    ap.add_argument("--tokens", default="", help="extra comma-separated tokens to match in domain names")
    ap.add_argument("--negative", default="", help="comma-separated substrings that disqualify a name (e.g. campus,campaign)")
    ap.add_argument("--expand", action="store_true", help="add tokens from DataForSEO Amazon + Google keyword ideas (paid, ~$0.1)")
    ap.add_argument("--location-code", type=int, default=2840, help="DataForSEO location code (2840 = United States)")
    ap.add_argument("--max-cost", type=float, default=None)
    a = ap.parse_args(argv)

    slug = re.sub(r"[^a-z0-9]+", "-", a.niche.lower()).strip("-") or "niche"
    run_dir = Path(a.out or Path("domain-runs") / slug)
    run_dir.mkdir(parents=True, exist_ok=True)

    tokens: list[str] = []
    negative: list[str] = []
    for p in a.preset:
        f = ASSETS / "niches" / f"{p}.txt"
        if not f.exists():
            raise SystemExit(f"unknown preset {p!r}. Available: {', '.join(presets())}")
        for line in load_lines(f):
            if line.startswith("-"):
                negative.append(line[1:].strip().lower())
            else:
                tokens.append(line.lower())
    tokens += [t.strip().lower() for t in a.tokens.split(",") if t.strip()]
    tokens += [w for w in re.findall(r"[a-z]+", a.niche.lower()) if len(w) >= 4 and w not in STOP]
    negative += [t.strip().lower() for t in a.negative.split(",") if t.strip()]
    negative += load_lines(ASSETS / "negative_common.txt")

    if a.expand:
        tokens += expand_tokens(a.niche, tokens, run_dir, a.location_code, a.max_cost)

    tokens = sorted({t for t in tokens if len(t) >= 3})
    negative = sorted({n for n in negative if n})
    if not tokens:
        raise SystemExit("no tokens: pass --preset or --tokens")

    niche = {
        "niche": a.niche,
        "tokens": tokens,
        "negative": negative,
        "location_code": a.location_code,
        "created": now_utc().isoformat(timespec="seconds"),
    }
    (run_dir / "niche.json").write_text(json.dumps(niche, indent=2), encoding="utf-8")
    log(f"run folder {run_dir} | {len(tokens)} tokens | {len(negative)} negative")
    print(run_dir)


if __name__ == "__main__":
    main()
