# Vetting methodology

How the pipeline judges a domain, what each number means, and the checklist to apply before
recommending one. `lessons-learned.md` records why each rule exists.

## Funnel (cheapest first)

| Stage | Cost | What it removes |
|---|---|---|
| Name match (tokens, negatives, trademarks, spam words) | free | off-niche and risky names |
| DNS over HTTPS + RDAP | free | domains someone still owns; tells register / backorder / auction |
| Bulk rank, backlink spam score, referring domains (1,000 per call) | ~$0.06 per 1,000 | linkless names, "high" backlink spam (> 60) |
| Deep backlinks: summary, anchors, referring domains, **clean count** | ~$0.10 per domain | toxic anchors, PBN footprints; separates real links from link-selling networks |
| Google `site:` and Bing name query | $0.002 per domain per engine | domains the engines have forgotten |
| Wayback history | free, ~15 s per domain | parked, hijacked, re-used, off-topic pasts |

## Score

`score = 30% authority + 25% cleanliness + 20% relevance + 15% search index + 10% buyability`

- **Authority**: DataForSEO rank (0–1000), referring main domains (log scale, the *clean* count
  once known), Common Crawl harmonic-centrality position, peak Google traffic, age.
- **Cleanliness**: starts at 100, minus the domain's own spam score (`target_spam_score`), minus
  the backlink spam score (× 0.5), spam-TLD share, spammy referring domains, link-selling anchors
  and links that appeared in the last 90 days, minus parked captures, content "eras" and redirects.
  Once the clean referring-domain count exists, the network share (1 − clean/raw) costs up to 25
  points and the raw backlink metrics are weighed by the clean share, because they describe the
  network, not the domain. Toxic anchors (casino, pharma, adult) and foreign-script anchors are
  never discounted. 50 when nothing is known yet.
- **Relevance**: niche word in the name (55 when it is a real word in the name, 35 for a long
  substring), distinct niche words in archived pages, niche words in backlink anchors, links
  from niche pages.
- **Search index**: Google indexed 60–100 (by result count), Bing only 50–70, +10 when both;
  checked and absent everywhere 0; unchecked 35. `idx_summary` says `both`, `google only`,
  `bing only` or `none`.
- **Buyability**: register 100, backorder 65, auction 45; minus for length over 10, hyphens,
  digits and non-.com.

Tiers: **A** ≥ 70 with at most one warning, Wayback checked and indexed in Google or Bing;
**B** ≥ 55; **C** below; **X** rejected.

## Hard rejects (defaults; change with score.py flags)

- Trademark in the name (`assets/trademarks.txt`), including any "amazon" or "kindle" variation.
- Spam word in the name (`assets/spam_names.txt`).
- Still registered with no expiry in sight (unless imported from an auction list or `--keep-registered`).
- The domain's own spam score above 30 (DataForSEO band "low" ends at 30).
- Backlink spam score above 60 ("high") **before** the deep pass. `bulk_spam_score` is this
  backlink-based metric, not the domain's own score; "medium" (31–60) usually means a
  link-selling network and is settled by the clean count.
- More than 10 % of anchors (by referring domains) are toxic spam phrases (`spam_terms.txt`), or
  more than 25 % are in foreign scripts. Link-selling anchors (`linkspam_terms.txt`) are a warning,
  not a reject.
- Any archived capture with spam, adult content, or a foreign-script takeover.
- Fewer than 5 referring main domains (the clean count when it exists).

## Warnings (shown, not rejected)

- Parked in some captures: common between owners; many parked years means the links are old.
- Content changed 2+ times (3+ eras): likely dropped and re-used, often as a PBN.
- Redirects in history: links may have been passed to another site.
- Google traffic collapsed before expiry: the site died or was penalised; look at the dates.
- Many referring domains on few IPs: private-blog-network footprint.
- Link-spam network hit: > 30 % link-selling anchors or > 50 % of the top referring domains
  first seen in the last 90 days. Judge by the clean count; expect those links to vanish.
- Backlink spam score above 30 (medium or high).
- Not in Google / not in Bing (the Bing check is a name query: confirm with `site:` on bing.com).

## Manual review checklist

For each pick you recommend, confirm:

1. History titles show a real site, ideally on the niche or a close neighbour. One clean owner
   for years is the best case. Read the last 2–3 years before expiry closely: that is where
   takeovers (Japanese keyword hack, Thai/Indonesian casino, essay or pharma spam) happen.
2. No foreign-language era in an English niche, no "cheap jerseys", casino, pills or essay content.
3. Top **clean** referring domains look like real sites (blogs, forums, news, .edu/.gov, resource
   pages), not `seo-*`, `*-links`, directories and spun blogs. The raw list of a fresh drop is
   usually the network; ignore it once the clean list is in hand.
4. Top anchors are the brand, the URL, or niche phrases, not money keywords repeated hundreds of
   times. "Premium backlinks <domain>" anchors are the network, not the domain.
5. Google shows real pages from it (sample URLs in the report); the "Try Google Search Console —
   Do you own X?" card alone means nothing. A DMCA notice in the footer means removals: check
   Lumen. Bing: open https://www.bing.com/search?q=site%3A<domain> yourself; Bing captchas
   automated queries after a few searches.
6. The name is something the user can build an honest brand on: no trademark (USPTO Trademark
   Search, WIPO Global Brand Database, TMview; similar spelling or sound counts), no Amazon mark
   or misspelling (Amazon Associates forbids them anywhere in the domain or store ID).
7. Not on Spamhaus DBL / SURBL / Google Safe Browsing.
8. The buy path is clear: register now, backorder before the drop date (Dynadot cheapest,
   DropCatch/SnapNames most successful), or the auction / closeout listing. Confirm status and
   price at the registrar before paying.
9. The plan is a same-topic rebuild with original content. Google's "expired domain abuse" policy
   targets repurposing for unrelated low-value content; a new, useful site on the old topic is fine.

## Known limits

- RDAP shows registry status, not aftermarket price. Expired-but-held names may be in an auction
  or marked for sale elsewhere.
- Spam scores and rank are DataForSEO's estimates. A low spam score does not prove a link profile
  is natural; read the anchors and referring domains. The clean count depends on the filter list
  in `enrich_backlinks.py` and the link-selling phrases in `assets/linkspam_terms.txt`.
- DataForSEO's Bing SERP cannot run `site:` queries (Oct 2026); the Bing column is a name-query proxy.
- The Wayback sample reads one homepage per year (10 by default). Raise `--samples` for a closer look.
- Common Crawl name matching only finds niche words in the name, and its hand-registrable domains
  are years dead (never indexed). Use the outlinks source for topical domains with brandable names.
