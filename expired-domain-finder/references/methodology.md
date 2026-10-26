# Vetting methodology

How the pipeline judges a domain, what each number means, and the checklist to apply before recommending one.

## Funnel (cheapest first)

| Stage | Cost | What it removes |
|---|---|---|
| Name match (tokens, negatives, trademarks, spam words) | free | off-niche and risky names |
| DNS over HTTPS + RDAP | free | domains someone still owns |
| Bulk rank, spam score, referring domains (1,000 per call) | ~$0.06 per 1,000 | weak and spammy profiles |
| Deep backlinks: summary, anchors, referring domains | ~$0.08 per domain | toxic anchors, PBN footprints |
| Bing `site:` search | $0.002 per domain | domains Bing has forgotten |
| Wayback history | free, ~15 s per domain | parked, hijacked, re-used, off-topic pasts |

## Score

`score = 30% authority + 25% cleanliness + 20% relevance + 15% Bing index + 10% buyability`

- **Authority**: DataForSEO rank (0–1000), referring main domains (log scale), Common Crawl harmonic-centrality position, peak Google traffic, age.
- **Cleanliness**: starts at 100, minus spam score, backlink spam, spam/foreign anchor share, share of links from spam TLDs (.ru, .xyz, .top…), spammy referring domains, parked captures, content "eras" and redirects. 50 when nothing is known yet.
- **Relevance**: niche word in the name (55 when it is a real word in the name, 35 for a long substring), distinct niche words in archived pages, niche words in backlink anchors, links from niche pages.
- **Bing index**: indexed with results, 60–100; not indexed, 0; unchecked, 35.
- **Buyability**: register 100, backorder 65, auction 45; minus for length over 10, hyphens, digits and non-.com.

Tiers: **A** ≥ 70 with at most one warning and both Bing index and Wayback history verified, **B** ≥ 55, **C** below, **X** rejected.

## Hard rejects (defaults; change with score.py flags)

- Trademark in the name (`assets/trademarks.txt`), including any "amazon" variation.
- Spam word in the name (`assets/spam_names.txt`).
- Still registered with no expiry in sight (unless imported from an auction list or `--keep-registered`).
- DataForSEO spam score above 30, backlink spam score above 40.
- More than 10% of anchors (by referring domains) are spam phrases, or more than 25% are in foreign scripts.
- Any archived capture with spam, adult content, or a foreign-script takeover.
- Fewer than 5 referring main domains (when backlink data exists).

## Warnings (shown, not rejected)

- Parked in some captures: common between owners; many parked years means the links are old.
- Content changed 2+ times (3+ eras): likely dropped and re-used, often as a PBN.
- Redirects in history: links may have been passed to another site.
- Google traffic collapsed before expiry: the site died or was penalised; look at the dates.
- Many referring domains on few IPs: private-blog-network footprint.
- Not in Bing's index.

## Manual review checklist

For each pick you recommend, confirm:

1. History titles show a real site, ideally on the niche or a close neighbour. One clean owner for years is the best case.
2. No foreign-language era in an English niche, no "cheap jerseys", casino, pills or essay content, no Japanese keyword hack.
3. Top referring domains look like real sites (blogs, forums, news, .edu/.gov, resource pages), not a list of `seo-*`, `*-links`, directories and spun blogs.
4. Top anchors are the brand, the URL, or niche phrases, not money keywords repeated hundreds of times.
5. Bing still shows real pages from it (sample URLs in the report).
6. The name is something the user can build an honest brand on, without a trademark.
7. The buy path is clear: register now, backorder before the drop date, or the auction listing.

## Known limits

- RDAP shows registry status, not aftermarket price. Expired-but-held names may be in an auction or marked for sale elsewhere.
- Spam score and rank are DataForSEO's estimates. A low spam score does not prove a link profile is natural; read the anchors and referring domains.
- The Wayback sample reads one homepage per year (6 by default). Raise `--samples` for a closer look.
- Common Crawl name matching only finds niche words in the name. Use the outlinks source for topical domains with brandable names.
