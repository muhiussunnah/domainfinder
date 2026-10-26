---
name: expired-domain-finder
description: Find high-quality expired or dropping domains for a niche (especially Amazon-affiliate product niches) that are still indexed in Bing, have clean backlink profiles and a clean history, and can be bought cheaply (hand-register, backorder or auction). Pulls candidates in bulk from DataForSEO WHOIS (just-expired domains with backlinks), the Common Crawl web graph (dead domains that live pages still link to), niche outbound-link crawls and imported lists (ExpiredDomains.net, GoDaddy Auctions, DropCatch), then checks availability (RDAP), backlinks and spam (DataForSEO), the Bing index (site: search) and Wayback history, and ranks them with evidence. Use whenever someone wants expired domains, aged domains, dropped domains, domains with backlinks or authority, a domain for a niche or affiliate site, or a bulk domain hunt, including Banglish requests like "expired domain khuje dao", "niche er jonno domain lagbe", "bing e index ache emon domain", or "amazon niche domain".
---

# Expired Domain Finder

Finds expired domains worth buying for a niche, cheapest checks first, and shows the evidence for every pick.

A good pick is all of these:
- **Buyable cheaply**: unregistered (hand-register for ~$10) beats backorder, which beats auction.
- **Still in Bing's index**: Bing re-crawls and ranks an expired domain it already knows in days or weeks; a brand-new domain can take about 3 months.
- **Real, clean backlinks**: enough referring domains, low spam score, no casino/pharma/adult or foreign-script anchors, no PBN footprint (many links from the same IPs).
- **Clean history**: was a genuine site on (or near) the niche, never parked for years, never hijacked (Japanese keyword hack, Thai/Chinese takeovers), not re-used several times.
- **Relevant and safe to own**: niche word in the name or niche content in its past; no trademark in the name. Amazon Associates forbids "amazon" or any variation in an affiliate domain.

## Files

- `scripts/run_pipeline.py`: runs every stage for one niche. Each stage is also its own script (`--help` on any of them).
- `scripts/check_balance.py`: DataForSEO balance and Backlinks subscription status (free).
- `assets/niches/*.txt`: ready token lists for Amazon niches (outdoor-camping, kitchen-cooking, coffee-tea, pets-dogs, pets-cats, pets-aquarium, pets-birds-small, baby-kids, fitness-gym, home-improvement-tools, garden-lawn, beauty-skincare, tech-gadgets, automotive, golf, fishing-archery, cycling, sleep-bedding, home-cleaning-organizing, crafts-sewing, music-instruments, office-wfh, travel-luggage).
- `references/methodology.md`: what every check means, the thresholds, and the manual review checklist. Read it before the final review.
- `references/sources.md`: where candidates come from and how to import lists from other tools.
- `references/dataforseo.md`: endpoints, prices, the Backlinks subscription, and the MCP alternative.
- `references/after-purchase.md`: what to do once a domain is bought.

Scripts are standard-library Python 3.9+. `pip install wordninja` makes name matching much more accurate (it splits `bettafishcare` into words); install it if `python -c "import wordninja"` fails.

## Workflow

### 1. Setup check (once per session)

Run from the skill's `scripts/` folder (use `python3` on macOS/Linux):

```bash
python check_balance.py
```

- Credentials missing: tell the user to run `scripts/setup_credentials.ps1` themselves on Windows (it asks for the DataForSEO API login and password and saves them as user environment variables), or to `export DATAFORSEO_LOGIN=... DATAFORSEO_PASSWORD=...` on macOS/Linux. The values are on https://app.dataforseo.com/api-access. Never ask for, type, or store the credentials yourself. Without credentials, the free stages still run (`--free-only`).
- Backlinks subscription not active: backlink checks are skipped automatically; say so, since the cleanliness verdict will then rest on Wayback history only.

### 2. Intake

Ask only what you cannot infer, in one message:
1. Niche or Amazon category (map it to a preset, or build tokens from the niche).
2. DataForSEO budget for this hunt (default $5; a full run is usually $2–8).
3. TLDs (default `com,net,org`) and how many final picks (default 25).
4. Buying style: only hand-register (cheapest), or also backorders and auctions.

Good tokens are specific product or hobby words of 4+ letters. Add negatives for words the tokens hide inside (`-campus` for `camp`). The niche name's own words become tokens too, so prefer "aquarium" over a broad phrase like "aquarium fish" (which makes every `*fish*` name a match).

### 3. Run

Create runs in the user's working folder, not in the skill folder. A full run takes 15–40 minutes (Common Crawl stream ~7 min, Wayback ~15 s per domain), so start it in the background and wait for it to finish:

```bash
python run_pipeline.py --niche "camping gear" --preset outdoor-camping --max-cost 5 --out domain-runs/camping-gear
```

Useful options: `--expand` (grow tokens from Amazon and Google keyword ideas, ~$0.10), `--traffic` (Google traffic history, ~$1.30 per 1,000 domains), `--sources whois,commoncrawl,outlinks`, `--seed-file urls.txt` (pages to crawl for dead outbound links), `--import list.csv` (repeatable), `--deep 60 --index-top 100 --history-top 60` (how many of the best candidates get each paid or slow check), `--free-only`.

`--max-cost` is a hard cap: the client refuses any call that would cross it and the pipeline continues with the free stages. If the user wants more checks, ask before raising it.

To re-check or extend part of a run, call the stage directly, e.g. `python check_history.py --run domain-runs/camping-gear --domains a.com,b.net --force`. Run one stage at a time per run folder: every stage rewrites `domains.csv`.

### 4. Review before you recommend

The score ranks; it does not decide. Read `report.md` in the run folder and, for each of the top ~15:
- Read the history titles. Off-topic past content is still a weak pick even with a niche word in the name (a novelty site called *allahfish* is not an aquarium site).
- Check the warnings: parked years, content changed several times, Google traffic collapse, shared IPs.
- When in doubt, open the Wayback link or re-run `check_history.py --domains <d> --samples 10 --force` for more captures.
- Drop anything that fails the checklist in `references/methodology.md`, and say why.

### 5. Answer

Give the user, in their language (Banglish if they wrote Banglish):
- A short table of the final picks: domain, tier and score, how to buy (register / backorder / auction), Bing indexed (results), rank and referring domains, spam score, active years, one-line reason.
- For each of the top 5: the evidence (Bing sample URLs, top referring domains, history) and the exact next step to buy.
- What was rejected and why, in counts.
- DataForSEO spend (from `cost_log.csv`) and the path to `report.html`.
- A reminder to confirm status and price at the registrar before paying, and to build a genuinely useful site on the same topic. Google's spam policies treat buying expired domains to host unrelated or low-value content as "expired domain abuse".

Offer the after-purchase plan in `references/after-purchase.md` once they pick a domain.

## Rules

- Never register, backorder or bid on a domain, and never enter payment details: give the user the link and the step.
- Never handle DataForSEO credentials: the user sets them with the setup script.
- Stay inside the agreed budget; ask before spending more.
- Report unknowns as unknown. "Not checked" is not "clean".
