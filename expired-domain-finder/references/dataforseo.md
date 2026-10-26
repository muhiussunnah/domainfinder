# DataForSEO reference

All calls go to `https://api.dataforseo.com/v3/` with HTTP Basic auth (API login and API
password from https://app.dataforseo.com/api-access, not the website password). Every response
includes its real `cost`; the pipeline logs it to `<run>/cost_log.csv` and enforces `--max-cost`.
Minimum top-up is $50.

| Use | Endpoint | Price (Oct 2026) |
|---|---|---|
| Balance, subscription | `GET appendix/user_data` | free |
| Expired / expiring domains with backlink counts | `POST domain_analytics/whois/overview/live` | $0.12 + $0.0012 per domain |
| Rank 0–1000 for up to 1,000 targets | `POST backlinks/bulk_ranks/live` | $0.024 + $0.000036 per row |
| Backlink spam score for up to 1,000 targets | `POST backlinks/bulk_spam_score/live` | same |
| Referring domains for up to 1,000 targets | `POST backlinks/bulk_referring_domains/live` | same |
| Full backlink summary (incl. `info.target_spam_score`) | `POST backlinks/summary/live` | $0.024 + rows |
| Anchor texts | `POST backlinks/anchors/live` | $0.024 + rows |
| Top referring domains | `POST backlinks/referring_domains/live` | $0.024 + rows |
| Clean referring-domain count | same endpoint with `backlinks_filters` + `filters` (below) | $0.024 + rows |
| Google `site:` check | `POST serp/google/organic/live/regular` | $0.002 per SERP |
| Bing name-query check | `POST serp/bing/organic/live/regular` with `target` | $0.002 per SERP |
| Monthly Google traffic since 2020 | `POST dataforseo_labs/google/historical_bulk_traffic_estimation/live` | $0.12 + $0.0012 per domain |
| Amazon keyword ideas | `POST dataforseo_labs/amazon/related_keywords/live` | Labs rate |
| Google keyword ideas | `POST dataforseo_labs/google/keyword_suggestions/live` | Labs rate |

Prices change; the logged `cost` is the source of truth.

## Things that bit us (see lessons-learned.md)

- `serp/bing/organic/live/regular` returns "No Search Results" for every `site:` query, even
  `site:wikihow.com`, whether sent as `keyword` or as a direct `url`. Use Google for `site:` and,
  for Bing, a name query: `{"keyword": "<domain>", "target": "*<domain>*"}` returns the domain's
  own pages only when Bing has it (`se_results_count` describes the whole query, so count the
  matching `items`).
- `bulk_spam_score` is the **backlink-based** spam score (identical to `backlinks_spam_score` in
  the summary). The domain's own score is `info.target_spam_score` in `backlinks/summary/live`.
  Bands: 0–30 low, 31–60 medium, 61–100 high.
- Freshly dropped domains carry thousands of link-selling links. The clean count:

```json
{"target": "example.com", "limit": 20, "order_by": ["rank,desc"], "include_subdomains": true,
 "backlinks_filters": [["backlink_spam_score", "<", 40], "and",
                       ["tld_from", "not_in", ["store", "shop", "site", "online", "space", "xyz", "top", "..."]], "and",
                       ["anchor", "not_ilike", "%backlink%"], "and",
                       ["anchor", "not_ilike", "%link building%"], "and",
                       ["anchor", "not_ilike", "%pbn%"]],
 "filters": ["backlinks_spam_score", "<", 40]}
```

  `backlinks_filters` chooses which links count (fields of `backlinks/backlinks/live`);
  `filters` then drops referring domains whose remaining links still average a medium spam
  score. `total_count` is the clean referring-domain count.

## WHOIS filters used

```json
[["domain","regex","(aquarium|cichlid|betta)"], "and", ["tld","in",["com","net","org"]],
 "and", ["backlinks_info.referring_main_domains", ">=", 5],
 "and", ["backlinks_info.referring_main_domains", "<=", 1500],
 "and", ["registered","=",false],
 "and", ["updated_datetime", ">", "2026-09-26 00:00:00 +00:00"]]
```

Up to 8 filters per request; `order_by` up to 3 rules (we use
`["metrics.organic.count,desc", "backlinks_info.referring_main_domains,desc"]`); `limit` up to
1,000 with `offset`. `registered = false` rows without a recent `updated_datetime` are usually
re-registered already; RDAP decides.

## Backlinks subscription

The Backlinks endpoints need an active Backlinks API subscription on the account
(`backlinks_subscription_expiry_date` in `user_data`). Without it they return an access error;
the pipeline then skips backlink checks and says so. WHOIS still returns referring-domain counts,
so candidates are not blind.

## MCP mode (no credentials in the scripts)

DataForSEO's hosted MCP exposes the same API (`api_request`, `docs_search`) after an OAuth
sign-in: `https://mcp.dataforseo.com/v3/mcp` (type `http`) in `.mcp.json`, then type `/mcp` on
its own, pick `dataforseo`, Authenticate. Two ways to combine it with the pipeline:

- **Local server, same credentials as the scripts** (no sign-in once `setup_credentials.ps1` has
  run and Claude restarted):

```json
{ "mcpServers": { "dataforseo": { "type": "stdio", "command": "cmd",
  "args": ["/c", "npx", "-y", "dataforseo-mcp-server"] } } }
```

  (On macOS/Linux use `"command": "npx", "args": ["-y", "dataforseo-mcp-server"]`.)

- **Hosted MCP only** (the scripts have no credentials): run the free stages with the scripts
  (`--free-only`), call the paid endpoints through the MCP from the chat, save each response
  to a file in the run folder and merge it with `scripts/mcp_inject.py`:

```bash
python mcp_inject.py --run RUN list 1000 > RUN/batch.txt            # who to check next
python mcp_inject.py --run RUN bulk RUN/bulk_rd.json RUN/bulk_spam.json RUN/bulk_rank.json
python mcp_inject.py --run RUN index google example.com RUN/g.json  # a site: response
python mcp_inject.py --run RUN index bing example.com RUN/b.json    # a name-query response
python mcp_inject.py --run RUN deep example.com summary=RUN/s.json anchors=RUN/a.json refdomains=RUN/r.json clean=RUN/c.json
python mcp_inject.py --run RUN whois RUN/whois.json
python mcp_inject.py --run RUN cost backlinks/bulk_referring_domains/live 0.06 "bulk 1000"
```

  Then `score.py`, `check_history.py` and `report.py` as usual. Ask the MCP for the raw response
  (`noAiMode: true`) when a trimmed one lacks `total_count` or `se_results_count`. Bulk results
  with thousands of rows are cheaper and faster through the REST scripts.
