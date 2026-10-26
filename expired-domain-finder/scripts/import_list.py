"""Import domain lists you exported elsewhere: ExpiredDomains.net, GoDaddy Auctions,
DropCatch, NameJet, SnapNames, Dynadot, SpamZilla, or any CSV/TXT with domains in it.

Known price/bid/end-time columns are kept as import_* fields for the report.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from common import load_table, log, normalize_domain, save_table, setup_console, upsert

DOMAIN_COLS = ("domain", "domain name", "domainname", "name", "domain_name", "url", "site")
KEEP = {"price": "import_price", "current price": "import_price", "min bid": "import_price", "bid": "import_price",
        "bids": "import_bids", "end time": "import_ends", "end date": "import_ends", "auction end": "import_ends",
        "enddate": "import_ends", "drop date": "import_ends", "status": "import_status", "type": "import_type",
        "bl": "import_bl", "dp": "import_dp", "aby": "import_aby", "acr": "import_acr", "dmoz": "import_dmoz",
        "tf": "import_tf", "cf": "import_cf", "da": "import_da", "dr": "import_dr"}


def rows_from_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    sample = text[:4096]
    if path.suffix.lower() in (".csv", ".tsv") or sample.count(",") + sample.count("\t") > 5:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(text.splitlines(), dialect=dialect)
        if reader.fieldnames:
            lower = {f.lower().strip(): f for f in reader.fieldnames if f}
            dcol = next((lower[c] for c in DOMAIN_COLS if c in lower), None)
            if dcol:
                for r in reader:
                    extra = {}
                    for k, v in r.items():
                        if k and k.lower().strip() in KEEP and v:
                            extra[KEEP[k.lower().strip()]] = v.strip()
                    yield r.get(dcol, ""), extra
                return
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        yield token, {}


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    run = Path(a.run)
    table = load_table(run)
    for f in a.files:
        p = Path(f)
        n = 0
        for raw, extra in rows_from_file(p):
            d = normalize_domain(raw)
            if d:
                upsert(table, d, extra, source=f"import:{p.name}")
                n += 1
        log(f"{p.name}: {n} domains")
    save_table(run, table)
    log(f"table now {len(table)} domains")


if __name__ == "__main__":
    main()
