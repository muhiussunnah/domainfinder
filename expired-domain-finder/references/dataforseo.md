# DataForSEO reference

All calls go to `https://api.dataforseo.com/v3/` with HTTP Basic auth (API login and API password from https://app.dataforseo.com/api-access, not the website password). Every response includes its real `cost`; the pipeline logs it to `<run>/cost_log.csv` and enforces `--max-cost`.

| Use | Endpoint | Price (Oct 2026) |
|---|---|---|
| Balance, subscription | `GET appendix/user_data` | free |
| Expired / expiring domains with backlink counts | `POST domain_analytics/whois/overview/live` | $0.12 + $0.0012 per domain |
| Rank 0–1000 for up to 1,000 targets | `POST backlinks/bulk_ranks/live` | $0.024 + $0.000036 per row |
| Spam score for up to 1,000 targets | `POST backlinks/bulk_spam_score/live` | same |
| Referring domains for up to 1,000 targets | `POST backlinks/bulk_referring_domains/live` | same |
| Full backlink summary | `POST backlinks/summary/live` | $0.024 + rows |
| Anchor texts | `POST backlinks/anchors/live` | $0.024 + rows |
| Top referring domains | `POST backlinks/referring_domains/live` | $0.024 + rows |
| Bing `site:` check | `POST serp/bing/organic/live/regular` | $0.002 per SERP |
| Google `site:` check / seed URLs | `POST serp/google/organic/live/regular` | ~$0.002 per 10 results |
| Monthly Google traffic since 2020 | `POST dataforseo_labs/google/historical_bulk_traffic_estimation/live` | $0.12 + $0.0012 per domain |
| Amazon keyword ideas | `POST dataforseo_labs/amazon/related_keywords/live` | Labs rate |
| Google keyword ideas | `POST dataforseo_labs/google/keyword_suggestions/live` | Labs rate |

Prices change; the logged `cost` is the source of truth.

## WHOIS filters used

```json
[["domain","regex","(aquarium|cichlid|betta)"], "and", ["tld","in",["com","net","org"]],
 "and", ["backlinks_info.referring_main_domains", ">=", 5], "and", ["registered","=",false]]
```

Up to 8 filters per request; `order_by` up to 3 rules; `limit` up to 1,000 with `offset`.

## Backlinks subscription

The Backlinks endpoints need an active Backlinks API subscription on the account (`backlinks_subscription_expiry_date` in `user_data`). Without it they return an access error; the pipeline then skips backlink checks and says so. WHOIS still returns referring-domain counts, so candidates are not blind.

## MCP server (interactive use)

For one-off questions in chat, DataForSEO's MCP server exposes the same API (`api_request`, `docs_search`). Two ways to connect it in Claude Code:

- **Hosted, OAuth**: `https://mcp.dataforseo.com/v3/mcp` (type `http`). Sign in from the MCP servers list: type `/mcp` on its own, pick `dataforseo`, then Authenticate.
- **Local, uses the same environment variables as this skill**:

```json
{ "mcpServers": { "dataforseo": { "type": "stdio", "command": "cmd",
  "args": ["/c", "npx", "-y", "dataforseo-mcp-server"] } } }
```

(On macOS/Linux use `"command": "npx", "args": ["-y", "dataforseo-mcp-server"]`.) It reads `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`, so once `setup_credentials.ps1` has run and Claude has restarted, it works with no sign-in.

The scripts call the REST API directly: bulk results with thousands of rows are cheaper and faster outside the chat context.
