# domainfinder: Expired Domain Finder skill for Claude

A Claude Code skill that hunts expired domains for a niche (built for Amazon-affiliate niches) and only recommends ones that are:

- **cheap to get**: unregistered (hand-register ~$10) first, then backorders (Dynadot from ~$25, DropCatch/SnapNames ~$60–70), then auctions and $5 closeouts
- **still indexed**: Google `site:` check plus a Bing check, reported as `both` / `google only` / `bing only` / `none`
- **clean**: real referring domains counted *after* the link-selling networks that hit every fresh drop are filtered out, low spam score, no casino/pharma/adult or foreign-script anchors, no PBN footprint
- **with a clean past**: a genuine site on the topic, not parked for years, never hijacked or re-used
- **safe**: no trademarks in the name (and never "amazon" or "kindle")

Every pick comes with evidence: Google sample URLs, Bing status, clean and raw referring domains, top anchors, the Wayback history by year, and the exact next step to buy it.

## How it works

```
sources ──► availability ──► bulk backlinks ──► deep backlinks + clean count ──► Google/Bing index ──► Wayback ──► score ──► report
(free + paid)   (free: DNS + RDAP)  (~$0.06 / 1,000)   (best 60, ~$0.10 each)          ($0.002 each)        (free)
```

Candidate sources:

1. **DataForSEO WHOIS**: domains that just expired, with backlink counts (paid, ~$1.32 per 1,000). Filtered to fresh rows, because stale "expired" rows are usually re-registered by drop-catchers already.
2. **Common Crawl web graph**: dead domains that live pages still link to. Free, hand-registrable, but long dead (not indexed).
3. **Niche outbound links**: dead sites linked from niche pages and Wikipedia references, even with brandable names.
4. **Your own lists**: CSV/TXT from ExpiredDomains.net, GoDaddy closeouts, DropCatch, SpamZilla…

A full hunt usually costs **$2–8** in DataForSEO credit and takes 15–40 minutes. Without DataForSEO credentials it still runs the free stages, and with the DataForSEO MCP connected Claude can make the paid calls from the chat and merge them (`scripts/mcp_inject.py`).

The skill keeps a log of what each hunt taught in `expired-domain-finder/references/lessons-learned.md` and updates its rules from it.

## Install

```powershell
git clone https://github.com/muhiussunnah/domainfinder.git
cd domainfinder
powershell -ExecutionPolicy Bypass -File install.ps1
```

macOS / Linux: `sh install.sh`

Then either save your DataForSEO API credentials (from https://app.dataforseo.com/api-access) once:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\expired-domain-finder\scripts\setup_credentials.ps1"
```

and fully quit and reopen Claude afterwards, or connect DataForSEO's MCP (`.mcp.json` with `https://mcp.dataforseo.com/v3/mcp`, then `/mcp` → dataforseo → Authenticate). The Backlinks checks need an active Backlinks API subscription on your DataForSEO account; without it they are skipped. Minimum DataForSEO top-up is $50.

## Use

Ask Claude in plain words:

> Find 20 expired domains for the camping gear niche, budget $5, .com only

> pets niche e expired domain khuje dao, google e index ache, backlink clean, budget 5 dollar

Claude asks what it needs (niche, budget, TLDs), runs the pipeline, reviews the shortlist and gives you the picks with reasons and buy links. The full report is in `domain-runs/<niche>/report.html`.

Or run it yourself:

```bash
cd ~/.claude/skills/expired-domain-finder/scripts
python run_pipeline.py --niche "camping gear" --preset outdoor-camping --max-cost 5 --out domain-runs/camping-gear
```

Presets in `expired-domain-finder/assets/niches/`: outdoor-camping, kitchen-cooking, coffee-tea, pets-dogs, pets-cats, pets-aquarium, pets-birds-small, baby-kids, fitness-gym, home-improvement-tools, garden-lawn, beauty-skincare, tech-gadgets, automotive, golf, fishing-archery, cycling, sleep-bedding, home-cleaning-organizing, crafts-sewing, music-instruments, office-wfh, travel-luggage.

## Bangla quick start

1. `install.ps1` chalan, tarpor `setup_credentials.ps1` diye DataForSEO-r API login/password save korun (password apni nije type korben), othoba DataForSEO MCP connect korun (`/mcp` likhe dataforseo → Authenticate).
2. Claude restart korun.
3. Claude-ke bolun: "kitchen niche e 20 ta expired domain khuje dao, budget $5".
4. Claude niche, budget, TLD jiggesh korbe, tarpor search kore shortlist dibe: kon domain, keno bhalo, Google/Bing-e index ache kina, clean backlink koyta, ar kivabe kinben (register / backorder / auction).

Domain kenar age registrar-e status ar dam abar check korben. Kinar por same topic-e ashol, kajer site banan: unrelated ba thin content bosale Google eta "expired domain abuse" hishebe dhore.

## Files

```
expired-domain-finder/
  SKILL.md                 instructions Claude follows
  scripts/                 the pipeline (stdlib Python 3.9+, optional wordninja) + mcp_inject.py for MCP mode
  assets/                  niche token presets, spam / link-spam / trademark lists
  references/              lessons learned, methodology, sources, DataForSEO notes, after-purchase plan
install.ps1 / install.sh   copy the skill into ~/.claude/skills
```

## DataForSEO MCP (optional)

The skill calls the DataForSEO REST API directly when credentials are set. With only the MCP connected, Claude runs the free stages, makes the paid calls in chat and merges them with `scripts/mcp_inject.py`; see `expired-domain-finder/references/dataforseo.md`.
