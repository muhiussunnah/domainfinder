# Candidate sources

Combine sources: each finds a different kind of expired domain. All of them merge into one `domains.csv` per run.

## 1. DataForSEO WHOIS (`source_whois.py`), paid, ~$1.32 per 1,000 domains

DataForSEO's WHOIS Overview database includes domains whose registration just lapsed (`registered = false`), with backlink counts and Google ranking data attached. The script asks for niche names (regex on the domain), your TLDs and a minimum number of referring main domains, sorted by referring domains.

- `--mode expired`: registration lapsed. Usually pending delete or about to drop; DataForSEO keeps these only for a short time, so run often.
- `--mode expiring`: past expiry within `--days-back` days but still registered. These are in the registrar's grace period and often go to GoDaddy, NameJet or Dynadot auctions.

## 2. Common Crawl web graph (`source_commoncrawl.py`), free

Common Crawl publishes a domain-level link graph every few months (about 135M domains; about 90M are "dangling": domains other sites link to but which had nothing crawlable). The ranks file is sorted by harmonic centrality. Streaming it and keeping niche-named domains, then checking DNS and RDAP, finds domains that **live pages still link to but nobody owns**. That is the cheapest source of all: they can be hand-registered at normal price.

- Latest release is detected from https://commoncrawl.org/web-graphs. Pin one with `--release cc-main-2026-aug-sep-oct`.
- The file is ~2.4 GB. Streaming the first 40M positions takes about 7 minutes. For several niches, download it once and pass `--file`:
  `curl -O https://data.commoncrawl.org/projects/hyperlinkgraph/<release>/domain/<release>-domain-ranks.txt.gz`
- `--max-pos` controls depth: past ~40M, domains have very few links.

This is the method of "download Common Crawl data, clean it, then research in bulk with the DataForSEO API": the pipeline does the clean-up (name matching, negatives, DNS/RDAP) and then the bulk DataForSEO checks.

## 3. Niche outbound links (`source_outlinks.py`), free crawl, optional paid seeds

Old niche articles, resource pages and blogrolls link to sites that have since died. Those dead sites are topical even when the niche word is not in the name. Seeds come from `--seed-file` (one URL per line) and/or `--serp`, which takes Google top results for niche keywords from DataForSEO (~$0.006 per keyword). The crawler follows a few same-site pages that look like link lists, respects robots.txt and waits between requests.

Good seed files: forum threads, "best X" lists from 2010–2018, Wikipedia references for the niche, resource pages of clubs and associations.

## 4. Imported lists (`import_list.py`)

Any CSV or TXT with domains works. Known columns (price, bids, end time, BL, DP, ABY, ACR, TF/CF, DA/DR) are kept as `import_*` fields for the report.

- **ExpiredDomains.net** (free account): filter by keyword, TLD, BL, ACR and "available", then export CSV.
- **GoDaddy Auctions**: search the keyword, export or copy results. Expiring listings often close cheaply.
- **DropCatch / SnapNames / NameJet**: pending-delete lists by date.
- **SpamZilla / Domain Hunter Gatherer**: exports from paid tools.

Imported names that are still registered are treated as auctions, not rejected.

## Cheap bulk strategy

1. Run Common Crawl with broad niche tokens and keep only `register` results: these cost the normal registration fee.
2. Add DataForSEO WHOIS `expired` daily or weekly to catch fresh drops while they have their full link profile.
3. Let the bulk backlink pass (fractions of a cent per domain) cut the pool before any per-domain spend.
4. Spend per-domain money (deep backlinks, Bing) only on the best 50–100.
5. Prefer backorders over auctions: a backorder usually costs a fixed fee (~$60–80) and is only charged on success.
