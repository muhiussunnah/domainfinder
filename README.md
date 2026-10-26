# domainfinder: Expired Domain Finder skill for Claude

A Claude Code skill that hunts expired domains for a niche (built for Amazon-affiliate niches) and only recommends ones that are:

- **cheap to get**: unregistered (hand-register ~$10) first, then backorders, then auctions
- **still indexed in Bing**: faster crawl and ranking than a brand-new domain
- **clean**: real referring domains, low spam score, no casino/pharma/adult or foreign-script anchors, no PBN footprint
- **with a clean past**: a genuine site on the topic, not parked for years, never hijacked or re-used
- **safe**: no trademarks in the name (and never "amazon")

Every pick comes with evidence: Bing sample URLs, top referring domains and anchors, the Wayback history by year, and the exact next step to buy it.

## How it works

```
sources ──► availability ──► bulk backlinks ──► deep backlinks ──► Bing index ──► Wayback ──► score ──► report
(free + paid)   (free: DNS + RDAP)  (~$0.06 / 1,000)   (best 60, ~$0.08 each) ($0.002 each)  (free)
```

Candidate sources:

1. **DataForSEO WHOIS**: domains that just expired, with backlink counts (paid, ~$1.32 per 1,000).
2. **Common Crawl web graph**: dead domains that live pages still link to. Free, and the cheapest buys (they are unregistered).
3. **Niche outbound links**: dead sites linked from niche pages, even with brandable names.
4. **Your own lists**: CSV/TXT from ExpiredDomains.net, GoDaddy Auctions, DropCatch, SpamZilla…

A full hunt usually costs **$2–8** in DataForSEO credit and takes 15–40 minutes. Without DataForSEO credentials it still runs the free stages.

## Install

```powershell
git clone https://github.com/muhiussunnah/domainfinder.git
cd domainfinder
powershell -ExecutionPolicy Bypass -File install.ps1
```

macOS / Linux: `sh install.sh`

Then save your DataForSEO API credentials (from https://app.dataforseo.com/api-access) once:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\expired-domain-finder\scripts\setup_credentials.ps1"
```

Fully quit and reopen Claude afterwards. The Backlinks checks need an active Backlinks API subscription on your DataForSEO account; without it they are skipped.

## Use

Ask Claude in plain words:

> Find 20 expired domains for the camping gear niche, budget $5, .com only

> pets niche e expired domain khuje dao, bing e index ache, backlink clean, budget 5 dollar

Claude asks what it needs (niche, budget, TLDs), runs the pipeline, reviews the shortlist and gives you the picks with reasons and buy links. The full report is in `domain-runs/<niche>/report.html`.

Or run it yourself:

```bash
cd ~/.claude/skills/expired-domain-finder/scripts
python run_pipeline.py --niche "camping gear" --preset outdoor-camping --max-cost 5 --out domain-runs/camping-gear
```

Presets in `expired-domain-finder/assets/niches/`: outdoor-camping, kitchen-cooking, coffee-tea, pets-dogs, pets-cats, pets-aquarium, pets-birds-small, baby-kids, fitness-gym, home-improvement-tools, garden-lawn, beauty-skincare, tech-gadgets, automotive, golf, fishing-archery, cycling, sleep-bedding, home-cleaning-organizing, crafts-sewing, music-instruments, office-wfh, travel-luggage.

## Bangla quick start

1. `install.ps1` chalan, tarpor `setup_credentials.ps1` diye DataForSEO-r API login/password save korun (password apni nije type korben).
2. Claude restart korun.
3. Claude-ke bolun: "kitchen niche e 20 ta expired domain khuje dao, budget $5".
4. Claude niche, budget, TLD jiggesh korbe, tarpor search kore shortlist dibe: kon domain, keno bhalo, Bing-e index ache kina, backlink clean kina, ar kivabe kinben (register / backorder / auction).

Domain kenar age registrar-e status ar dam abar check korben. Kinar por same topic-e ashol, kajer site banan: unrelated ba thin content bosale Google eta "expired domain abuse" hishebe dhore.

## Files

```
expired-domain-finder/
  SKILL.md                 instructions Claude follows
  scripts/                 the pipeline (stdlib Python 3.9+, optional wordninja)
  assets/                  niche token presets, spam and trademark lists
  references/              methodology, sources, DataForSEO notes, after-purchase plan
install.ps1 / install.sh   copy the skill into ~/.claude/skills
```

## DataForSEO MCP (optional)

The skill calls the DataForSEO REST API directly. For ad-hoc questions in chat you can also connect DataForSEO's MCP server; see `expired-domain-finder/references/dataforseo.md`.
