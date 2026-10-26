# Lessons learned

Dated findings from real hunts and research passes. Read this before every hunt and append
to it after every hunt (see the Rules in SKILL.md). Newest first. Tags: **[FACT]** official
docs, measured data or verified in a run · **[PRACTICE]** consistent practitioner advice ·
**[FOLKLORE]** unverified or contradicted.

## 2026-10-26 — first hunt (all 23 presets, $0.90 of DataForSEO credit) and research pass

### What the hunt showed

1. **DataForSEO's Bing SERP returns nothing for `site:` queries** — "No Search Results" for
   every domain, including `site:wikihow.com`, with the keyword form, a direct Bing URL and
   `count=50`. The old `check_index.py` therefore reported *every* domain as "not in Bing". [FACT]
   Google's `serp/google/organic/live/regular` with `site:domain` works (craftsasgifts.com showed
   2 organic pages). A Bing name query (keyword = the bare domain, `target = *domain*`) returns
   the domain's own pages when Bing has it, so it is usable as a proxy; the real Bing check is a
   human `site:` search on bing.com (automated ones hit a captcha within a few queries).
2. **Link-selling networks blast every fresh drop.** craftsasgifts.com had 18 referring domains
   in Oct 2025, 243 in Sep 2026 and 2,708 by Oct 2026: 2,649 of them carry the anchor "Build
   Powerful SEO Authority with Premium Backlinks craftsasgifts.com" from .store/.shop/.site/
   .online/.space pages. aquaticinsect.net had 742 footer links from one Turkish site with the
   anchor "SCATTER HITAM". These push the backlink spam score to 44–60 while the domain's own
   `target_spam_score` stays at 1–4, and they make "sort WHOIS results by referring domains"
   surface the most-spammed names first. [FACT] Measure the profile with the networks removed
   (`backlinks_filters` on `referring_domains/live`): craftsasgifts.com has 25 clean referring
   domains, not 2,708.
3. **DataForSEO `bulk_spam_score` is the backlink-based score**, the same number as
   `backlinks_spam_score` in the summary (54 for craftsasgifts.com, whose target score is 1).
   Rejecting on it as if it were the domain's own score throws away every freshly dropped domain. [FACT]
4. **Common Crawl "dangling" domains that can still be hand-registered are years dead.** None of
   22 checked were in Google or Bing. They are a source of cheap names with old editorial links
   (hand-register at ~$10), not of still-indexed domains. [FACT]
5. **DataForSEO WHOIS `registered = false` rows are mostly stale.** Of 60 traffic-sorted rows,
   47 were already re-registered by drop-catchers (RDAP: registered, created 2025–2026). The
   genuinely free ones had `updated_datetime` within the last ~2 weeks. Filter on a recent
   `updated_datetime`, sort by `metrics.organic.count`, and always confirm with RDAP. [FACT]
6. **Wayback sampling missed hijack years.** aquaticinsect.net: Czech macro-photography site
   2011–2016, Japanese keyword-hack spam 2019, Thai casino 2022–2023, yet 6 samples over 13 years
   flagged only the 2023 casino. Sample every year (default now 10) and read the last 2–3 years
   closely. [FACT]
7. **Other connectors:** OpenSEO's `get_serp_results` does Google `site:` checks from its own
   credit pool (~2.5 credits per domain at depth 10) and is a good second opinion; Ubersuggest's
   backlinks tool returned HTTP 403 for every call. The DataForSEO MCP (OAuth, `/mcp` typed
   alone) works without credentials in the scripts; `scripts/mcp_inject.py` merges its responses.
8. **Budget reality:** a full all-niche pass cost $0.90: $0.06 bulk referring domains for 1,000
   names, $0.065 spam + rank for 236, $0.09 index checks, $0.49 WHOIS (two requests), $0.20
   deep checks for 2 domains. Minimum DataForSEO top-up is $50.

### Outcome

No domain passed every rule. The one real candidate, craftsasgifts.com (hand-registrable,
Google-indexed, 2019–2025 single-owner crafts/baking blog, target spam 1), carries a 2,650-link
spam network and only ~25 clean referring domains. With the fixes below it scores B / 71.

### What changed in the tool

- `check_index.py`: Google `site:` (reliable) plus Bing name query (proxy); per-engine columns and
  `idx_summary` = both / google only / bing only / none. The report shows Google and Bing side by side.
- `enrich_backlinks.py`: deep pass adds a **clean referring-domain count** (spam links, spam TLDs
  and link-selling anchors filtered out), `anc_linkspam_ratio` (link-selling anchors, counted
  separately from toxic spam) and `rd_recent_share` (top referring domains first seen in the last
  90 days). `assets/linkspam_terms.txt` holds the link-selling phrases. Target spam is read from
  `info.target_spam_score`.
- `score.py`: the domain's own spam score (≤ 30) and the backlink spam score (≤ 60 before the deep
  pass; afterwards the clean count decides) are separate rules; cleanliness charges the network
  itself (up to 25 points) and weighs raw metrics by the clean share; the referring-domain rule
  uses the clean count when it exists; index score and tier A need Google or Bing.
- `source_whois.py`: `--updated-days 30` (expired rows must be fresh), `--max-rmd 1500` (skip
  network-inflated counts), sort by organic keyword count then referring domains.
- `check_history.py`: 10 samples by default.
- `scripts/mcp_inject.py`: MCP mode — merge bulk, deep, index and WHOIS responses saved from the chat.

### Later the same day: the free path, and two mistakes

- **Wikipedia is the one free source of high-authority links.** `source_wikipedia.py` searches
  articles about the niche that carry `{{Dead link}}` tags and reads their wikitext; 4,000
  articles gave 2,263 dead-tagged domains, 97 hand-registrable and 5 in backorder, every one
  still linked from an article. A plain crawl of 1,622 niche articles (`source_outlinks.py`)
  gave 10,161 external domains and 97 buyable. `enrich_wikipedia.py` (list=exturlusage) counts
  the linking articles exactly, for free. [FACT]
- **Most Wikipedia-linked drops were hijacked at least once** (Chinese lottery, Japanese or
  Korean spam eras in 2019–2024); read the last years of the archive before recommending. The
  user's own `site:` checks on google.com and bing.com are the best free index check: no captcha
  for a person. Ahrefs' free backlink checker needs a Cloudflare tick that Claude must not do.
- **Mistake: a domain on `clientHold` with its expiry in 2027 was shown as a candidate.**
  `classify()` returned `on_hold` → `watch` for any hold; now a hold with a future expiry is
  `registered`, and reports list only `register` / `backorder` / `auction`. 209 rows across the
  day's runs were reclassified.
- **Mistake: a live site (pianomode.com) was shown in a results table** because DataForSEO's
  WHOIS `registered = false` row was stale. Never show a WHOIS row the RDAP check contradicts.
- **OpenSEO's SERP tool spent ~410 credits on 30 `site:` checks and one backlinks overview**,
  far more than its description suggests; check `whoami` before and after a batch.

### Research digest: sourcing and buying

- **Drop lifecycle [FACT]:** expiry → `autoRenewPeriod` (registrar grace, up to 45 days; large
  registrars auction the name here instead of deleting) → `redemptionPeriod` (30 days) →
  `pendingDelete` (5 days) → purge. Expiry to drop is usually ~65 days (35–80). RDAP status
  `pending delete` first seen on day D means the drop lands about D+5; `redemption period`
  means ≥ 35 days; `auto renew period` means it will probably be auctioned and may never drop.
- **Drop times [PRACTICE]:** Verisign (.com/.net) releases around 2 pm ET over 1–2 hours, PIR
  (.org) around 1 pm ET; re-check availability about 2:15 pm ET on drop day.
- **Competition [FACT]:** only ~10 % of pending-delete names are re-registered on day one, but
  the caught ones are exactly the aged, archived, linked names this tool wants; catchers make
  > 80 % of create attempts and win most .org names within 30 seconds. A name with real links and
  Wayback history that reaches pendingDelete will not be hand-registrable at the drop: backorder
  it, or buy it before it appears on public lists. ~20 % of all gTLD registrations are re-registrations.
- **Backorder fees (re-verify before quoting) [FACT at research time]:** DropCatch $59 (3-day
  auction if several backorders), SnapNames $69, NameJet $69 + commission, Dynadot from $24.99
  (pay only on success, place ≥ 24 h before the drop; cheapest). GoDaddy stopped taking
  backorders in Aug 2024 and ended the service in Oct 2025. Namecheap Market only auctions its
  own expiring names.
- **Cheap auction paths [FACT]:** GoDaddy expired auctions run 10 days; unsold names enter a
  5-day closeout ladder $50 → $40 → $30 → $11 → $5 plus renewal, and since Aug 2026 GoDaddy
  publishes downloadable expiry inventory files and search/purchase APIs. Namecheap closes all
  auctions at 11 am ET and extends no-bid closeouts 24 h at $5. Dynadot closeouts $30 → $15 → $5.
- **Lists [FACT/PRACTICE]:** ExpiredDomains.net (free login) has Pending Delete, Deleted, GoDaddy
  closeouts, Namecheap, Dynadot, Sedo, Name.com tabs with Majestic BL, SEOkicks DP, first Wayback
  year (ABY) and crawl count (ACR). Recommended filters: last 12–24 h, only available, no hyphens,
  no numbers, .com/.net/.org, DP ≥ 20, ABY ≥ 3–10 years, sort by TF; buy from "Deleted Domains"
  at hand-register price. ICANN CZDS zone files are free (per-registry approval) and a daily diff
  yields deletions. SpamZilla (~$37/mo), DomCop (~$816/yr), CatchDoms (€39/mo) aggregate the same.
- **Where nobody else bids [PRACTICE, well argued]:** everyone filters the same lists by
  referring-domain count, so competition tracks counts, not quality. Edges: dead external links
  on Wikipedia (one sweep found ~4,100 expired domains in popular English articles; "Link
  Lazarus" found 1,862 across four languages), outbound links of resource pages and old niche
  blogs, the Common Crawl graph (209 M nodes; ~2.75 % of candidates survive link and spam
  screening, median 10–50 referring domains) and brandable names without the niche keyword.
  Score "a few editorial links from strong topical sites" above raw counts; down-weight names
  already visible in two or more aggregators.
- **[FOLKLORE]** published backorder "success rates", "registrars cut grace to 10 days", "AI
  bidding wars already inflate prices", predicting the exact second of a drop.

### Research digest: vetting

- **Google policy [FACT]:** "expired domain abuse" (spam policies since 5 Mar 2024) = buying a
  domain and repurposing it primarily to manipulate rankings with low-value content; Google's
  examples are affiliate content on an ex-government site, medical products on an ex-charity
  site, casino content on a former school site. Google: "it's fine to use an old domain name for
  a new, original site that's designed to serve people first." Mueller (2025): the old state,
  including parked periods, "takes a lot of time to be shaken off"; after Search Console
  verification check pending URL removals and manual actions; redirecting an old domain to an
  unrelated site passes nothing. Rule: same-topic rebuild with original content only.
- **Spam scores [FACT]:** DataForSEO spam score bands 0–30 low, 31–60 medium, 61–100 high;
  biggest inputs are HTTP-only (+30), > 100 external links (+20), external:internal > 3 (+15),
  spam TLD (+20). Its TLD list (.surf .cn .cfd .ga .biz .hk .pw .icu .top .tw .gq .work .cf .cam
  .ml .xyz .best) does not include .store/.shop/.site/.online/.space, which is why the networks
  above read as "medium" rather than "high". Majestic: re-check when TF < 0.5 × CF. Ahrefs DR
  counts dofollow referring domains logarithmically, so DR far above what the referring-domain
  quality justifies means it was pumped.
- **PBN / link-spam footprints [PRACTICE]:** new referring domains per day > 2.5× the 30-day
  average, ≥ 5 new domains on one IP block, one exact-match commercial anchor > 15 % of new
  links, linking pages with 200+ outbound links, sitewide footer links, shared IP/C-class,
  nameservers, registrant, theme or analytics IDs. A junk inherited profile is the one footprint
  a buyer cannot fix. [FOLKLORE] any "ideal" dofollow:nofollow ratio.
- **Index checks [FACT]:** Google's `site:` shows *some* indexed pages, not a count; automated
  `site:` queries trigger captchas; the "Try Google Search Console — Do you own X?" card is an ad,
  not an index signal (an organic result from the domain is). A footer "In response to a
  complaint we received under the US DMCA, we have removed N result(s)" means DMCA removals:
  cross-check Lumen and Google's Copyright Transparency Report. Bing's Search APIs were retired
  in Aug 2025; Bing Webmaster Tools is the reliable Bing check after purchase. [FOLKLORE] "Bing
  re-indexes an expired domain faster than Google": a month-long test re-registering dropped
  domains had Google index ~73 % within days, with success tracking live followed referring
  domains; IndexNow pushes get Bing to crawl in seconds to minutes.
- **Wayback [FACT/PRACTICE]:** CDX `collapse=timestamp:4` for one capture a year, `timestamp:6`
  per month, `filter=statuscode:200&filter=mimetype:text/html`. Read one capture per year for the
  whole life and one per month for the last 24–36 months (the takeover window). 5–10 captures
  over a decade = low significance or robots-blocked; 1–2 parked snapshots between owners is
  normal, years parked = junk profile. Gambling takeovers are measured, not folklore: of 3,692
  auctioned domains (Jan 2024–May 2026) at least 448 became gambling sites, 1 in 5 of those sold
  above $25k. Japanese keyword hack: autogenerated Japanese text in random directories, cloaked
  from humans; scan captures for Thai/CJK script and tokens such as slot, gacor, casino,
  สล็อต, カジノ, viagra, essay.
- **Safety [FACT]:** trademark screen on USPTO Trademark Search (tmsearch.uspto.gov), WIPO
  Global Brand Database and TMview — similar spelling/sound/meaning, not exact only; a different
  class is no safe harbour. Amazon Associates forbids "amazon", "kindle" or any Amazon mark,
  variant or misspelling in the domain, subdomain, store ID or tag. Blocklists: Spamhaus DBL via
  DNS (NXDOMAIN = clean; 127.0.1.2 spam, .4 phish, .5 malware, .6 botnet), SURBL
  `multi.surbl.org`, Google Safe Browsing Lookup API / Transparency Report site status.
  Manual-action history is visible only in Search Console after purchase.

### Sources

- https://www.icann.org/resources/pages/epp-status-codes-2014-06-16-en
- https://www.namesilo.com/blog/en/domain-backorder/drop-times-and-why-they-vary
- https://www.securitee.org/files/dropcatching_www2018.pdf
- https://usenix.org/conference/usenixsecurity17/technical-sessions/presentation/lauinger
- https://www.infoblox.com/blog/threat-intelligence/drop-something-dont-worry-someone-caught-it/
- https://domaindetails.com/kb/domain-investing/domain-backorder-services
- https://www.godaddy.com/resources/news/announcing-deadline-extension-for-backorders
- https://www.godaddy.com/resources/news/godaddy-auctions-expiry-apis-automate-domain-acquisition
- https://domaininvesting.com/namecheap-adjusts-auction-end-times-and-closeout-process/
- https://www.dynadot.com/market/backorder
- https://www.expireddomains.net/domain-lists/
- https://getrevised.com/knowledge/seo-fundamentals/how-to-find-expired-domains-with-backlinks
- https://metehan.ai/blog/link-lazarus-method
- https://developers.google.com/search/docs/essentials/spam-policies
- https://www.seroundtable.com/google-old-domain-history-40184.html
- https://dataforseo.com/help-center/what-is-spam-score-and-how-is-it-calculated
- https://blog.majestic.com/general/power-user-tips-using-flow-metrics-properly/
- https://www.searchenginejournal.com/googles-site-operator-wont-show-you-everything-thats-indexed/490092/
- https://www.billhartzer.com/domain-names/test-reveals-expired-domains-indexing/
- https://web.dev/articles/fixing-the-japanese-keyword-hack
- https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md
- https://www.casino.org/news/report-offshore-gambling-sites-spent-millions-expired-domains/
- https://affiliate-program.amazon.com/help/operating/policies
- https://check.spamhaus.org/faqs/domain-blocklist/
- https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement
- https://archivarix.com/en/blog/expired-domains/
