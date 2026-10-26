# Candidate sources

Combine sources: each finds a different kind of expired domain. All of them merge into one
`domains.csv` per run.

## 0. How domains drop, and why the good ones are never simply "available"

- Lifecycle (gTLDs): expiry → auto-renew grace at the registrar (up to 45 days; large registrars
  auction the name here instead of deleting it) → redemption (30 days) → pendingDelete (5 days) →
  purge. Expiry to drop ≈ 65 days. RDAP status tells you where a name is: `pending delete` first
  seen on day D drops around D+5 (Verisign .com/.net release around 2 pm ET, .org around 1 pm ET);
  `redemption period` means ≥ 35 days; `auto renew period` means it will probably be auctioned.
- Drop-catchers (DropCatch, SnapNames, NameJet, Dynadot, GoDaddy, Namecheap, Spaceship) make
  > 80 % of registration attempts at the drop and win aged, archived, linked names within
  seconds. About one in five gTLD registrations is a re-registration. So:
  - a name with real links and history that reaches pendingDelete needs a **backorder**
    (Dynadot from $24.99, pay on success, place ≥ 24 h before; DropCatch $59; SnapNames $69;
    NameJet $69 + commission; GoDaddy no longer takes backorders);
  - names still in the registrar's grace period show up in **auctions/closeouts** (GoDaddy
    10-day auction, then $50 → $40 → $30 → $11 → $5 closeout; Namecheap closes at 11 am ET,
    $5 closeouts; Dynadot $30 → $15 → $5);
  - names that can be **hand-registered** were skipped by everyone: usually long dead (Common
    Crawl) or invisible on the lists (brandables, Wikipedia dead links).

## 1. DataForSEO WHOIS (`source_whois.py`), paid, ~$1.32 per 1,000 domains

DataForSEO's WHOIS Overview database includes domains whose registration just lapsed
(`registered = false`), with backlink counts and Google ranking data attached. The script asks
for niche names (regex on the domain), your TLDs, a minimum number of referring main domains and:

- `--max-rmd 1500`: link-selling networks push freshly dropped domains to 1,500–3,000 referring
  domains within weeks; above the cap the count is the network, not the domain.
- `--updated-days 30` (expired mode): rows whose WHOIS record was not updated recently are
  usually already re-registered by a catcher (47 of 60 in the first hunt). Fresh rows are free.
- sorted by `metrics.organic.count` (keywords it still ranks for, a sign it is still indexed),
  then referring domains.

Modes: `--mode expired` (lapsed; DataForSEO keeps these only for a short time, so run often) and
`--mode expiring` (past expiry within `--days-back` days but still registered: grace period,
often headed to GoDaddy, NameJet or Dynadot auctions). Always confirm with RDAP
(`check_availability.py` does); the WHOIS flag alone is not proof.

## 2. Common Crawl web graph (`source_commoncrawl.py`), free

Common Crawl publishes a domain-level link graph every few months (~200M domains; most are
"dangling": domains other sites link to but which had nothing crawlable). The ranks file is
sorted by harmonic centrality. Streaming it and keeping niche-named domains, then checking DNS
and RDAP, finds domains that **live pages still link to but nobody owns**: hand-registered at
normal price.

- What you get: cheap names with old editorial links. What you do not get: indexed domains —
  these have been dead for years and none of the first hunt's 22 were in Google or Bing. Use
  them when a name with some real links at $10 is enough, and budget time for IndexNow and
  Search Console after launch.
- Latest release is detected from https://commoncrawl.org/web-graphs. Pin one with
  `--release cc-main-2026-aug-sep-oct`.
- The file is ~2.4 GB. Streaming the first 40M positions takes about 7 minutes. For several
  niches, download it once and pass `--file`:
  `curl -O https://data.commoncrawl.org/projects/hyperlinkgraph/<release>/domain/<release>-domain-ranks.txt.gz`
- `--max-pos` controls depth: past ~40M, domains have very few links. `--word-only` keeps names
  where the niche token is a whole word (needs wordninja).

## 3. Niche outbound links (`source_outlinks.py`), free crawl, optional paid seeds

Old niche articles, resource pages, blogrolls and Wikipedia references link to sites that have
since died. Those dead sites are topical even when the niche word is not in the name, and they
are invisible to everyone filtering drop lists by referring-domain count. Seeds come from
`--seed-file` (one URL per line) and/or `--serp`, which takes Google top results for niche
keywords from DataForSEO (~$0.006 per keyword). The crawler follows a few same-site pages that
look like link lists, respects robots.txt and waits between requests.

Good seed files: Wikipedia articles and their reference lists for the niche (sweeps have found
thousands of expired domains this way), forum threads, "best X" lists from 2010–2018, resource
pages of clubs and associations. Skip .edu/.gov/.mil targets.

## 4. Imported lists (`import_list.py`)

Any CSV or TXT with domains works. Known columns (price, bids, end time, BL, DP, ABY, ACR,
TF/CF, DA/DR) are kept as `import_*` fields for the report.

- **ExpiredDomains.net** (free account): Pending Delete, Deleted Domains, GoDaddy closeouts,
  Namecheap, Dynadot, Sedo and Name.com tabs. Recommended filters: last 12–24 h, only available,
  no hyphens, no numbers, .com/.net/.org, DP ≥ 20, ABY (first Wayback year) ≥ 3–10 years ago,
  sort by TF; export CSV.
- **GoDaddy Auctions**: closeouts at $11 and $5 are the bargains; since Aug 2026 GoDaddy offers
  downloadable expiry inventory files and search/purchase APIs ($4.99/yr membership).
- **DropCatch / SnapNames / NameJet / Dynadot**: pending-delete lists by date.
- **SpamZilla / DomCop / CatchDoms**: exports from paid aggregators.
- **ICANN CZDS zone files** (free, per-registry approval): a day-over-day diff lists deletions.

Imported names that are still registered are treated as auctions, not rejected.

## Cheap bulk strategy

1. Run DataForSEO WHOIS `expired` daily or weekly with `--updated-days` to catch fresh drops
   while they are still free and still indexed.
2. Run Common Crawl with broad niche tokens and keep only `register` results for cheap names
   with old links.
3. Crawl niche resource pages and Wikipedia references (`outlinks`) for topical names nobody lists.
4. Let the bulk backlink pass (fractions of a cent per domain) cut the pool before any per-domain spend.
5. Spend per-domain money (deep backlinks with the clean count, index checks) only on the best 50–100.
6. Prefer backorders over auctions: a backorder is a fixed fee charged only on success.
