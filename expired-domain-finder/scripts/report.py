"""Write report.md (for Claude and quick reading) and report.html (for people) from the scored table."""
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from pathlib import Path

from common import load_niche, load_table, log, now_utc, num, setup_console

ACTION = {
    "register": "Not registered: hand-register it now at any registrar (~$10).",
    "backorder": "Pending delete / redemption: place a backorder (DropCatch, SnapNames, NameJet) before it drops.",
    "auction": "Past expiry, held by the registrar: look for it in GoDaddy / NameJet / Dynadot auctions.",
    "watch": "On hold: watch the status and check again in a few days.",
    "check": "Status unclear: verify on ICANN Lookup before acting.",
}


def links(d: str, acquire: str) -> list[tuple[str, str]]:
    out = [("Google site:", f"https://www.google.com/search?q=site%3A{d}"),
           ("Bing site:", f"https://www.bing.com/search?q=site%3A{d}"),
           ("Wayback", f"https://web.archive.org/web/*/{d}"),
           ("ICANN lookup", f"https://lookup.icann.org/en/lookup?name={d}")]
    if acquire == "register":
        out.append(("Namecheap", f"https://www.namecheap.com/domains/registration/results/?domain={d}"))
    elif acquire == "backorder":
        out.append(("DropCatch", f"https://www.dropcatch.com/domain/{d}"))
    elif acquire == "auction":
        out.append(("GoDaddy", f"https://www.godaddy.com/domainsearch/find?domainToCheck={d}"))
    return out


def fmt(v, nd=0) -> str:
    if v in (None, ""):
        return "–"
    try:
        f = float(v)
        return f"{f:,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def rmd(r):
    vals = [num(r, k) for k in ("bl_rmd", "dfs_rmd", "whois_rmd")]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def rmd_str(r) -> str:
    """'clean/total' once the deep pass removed link-selling networks, else the raw count."""
    clean = num(r, "bl_clean_rmd")
    return f"{fmt(clean)}/{fmt(rmd(r))}" if clean is not None else fmt(rmd(r))


def spend(run: Path) -> float:
    p = run / "cost_log.csv"
    if not p.exists():
        return 0.0
    with p.open(newline="", encoding="utf-8") as fh:
        return sum(float(r.get("cost") or 0) for r in csv.DictReader(fh))


def evidence(r: dict) -> list[tuple[str, str]]:
    ev = []
    if r.get("idx_summary"):
        ev.append(("Index", r["idx_summary"]))
    for engine in ("google", "bing"):
        v = r.get(f"{engine}_indexed")
        if not v:
            continue
        how = "site: query" if (r.get(f"{engine}_method") or "site") == "site" else "name query, a proxy: confirm with site: on bing.com"
        ev.append((engine.capitalize(), f"{'indexed' if v == 'yes' else 'not indexed'} ({how})"
                                        f"{' — ' + fmt(r.get(f'{engine}_results')) + ' results' if v == 'yes' else ''}"
                                        f"{'; ' + r[f'{engine}_sample'] if r.get(f'{engine}_sample') else ''}"))
    rank = r.get("bl_rank") or r.get("dfs_rank")
    if rank or rmd(r) is not None:
        parts = [f"rank {fmt(rank)} / 1000", f"{fmt(rmd(r))} referring main domains"]
        if r.get("bl_clean_rmd") not in (None, ""):
            parts.append(f"{fmt(r['bl_clean_rmd'])} clean (link-selling networks removed)")
        if r.get("bl_backlinks"):
            parts += [f"{fmt(r['bl_backlinks'])} backlinks", f"{fmt(r.get('bl_ips'))} IPs", f"{fmt(r.get('rd_edu_gov'))} edu/gov"]
        ev.append(("Backlinks", ", ".join(parts)))
    spam = r.get("bl_target_spam") or r.get("dfs_spam")
    if spam not in (None, ""):
        parts = [f"spam score {fmt(spam)}"]
        for key, name in (("bl_backlinks_spam", "backlink spam"),):
            if r.get(key) not in (None, ""):
                parts.append(f"{name} {fmt(r[key])}")
        for key, name in (("anc_spam_ratio", "spam anchors"), ("anc_foreign_ratio", "foreign anchors")):
            if num(r, key) is not None:
                parts.append(f"{name} {num(r, key) * 100:.0f}%")
        ev.append(("Spam", ", ".join(parts)))
    wl = num(r, "wiki_links")
    if wl is not None or r.get("wiki_pages"):
        n = int(wl) if wl is not None else int(num(r, "wiki_pages", 0) or 0)
        titles = r.get("wiki_link_titles") or r.get("wiki_titles") or ""
        tag = " (link tagged dead by editors)" if (r.get("wiki_dead_tagged") or "") in ("1", "True") else ""
        ev.append(("Wikipedia", f"{n} article(s) link to it{tag}: {titles}" if n else "no article links to it"))
    if num(r, "anc_linkspam_ratio") is not None or num(r, "rd_recent_share") is not None:
        ev.append(("Link-spam network", f"{(num(r, 'anc_linkspam_ratio', 0) or 0) * 100:.0f}% of anchors are link-selling spam, "
                                        f"{(num(r, 'rd_recent_share', 0) or 0) * 100:.0f}% of the top referring domains appeared in the last 90 days"))
    if r.get("anc_top"):
        ev.append(("Top anchors", r["anc_top"]))
    if r.get("rd_clean_top"):
        ev.append(("Top clean referring domains", r["rd_clean_top"]))
    if r.get("rd_top"):
        ev.append(("Top referring domains (raw)", r["rd_top"]))
    if r.get("wb_checked"):
        pages = fmt(r.get("wb_pages")) + ("+" if num(r, "wb_pages") == 2000 else "")
        ev.append(("Wayback", f"{r.get('wb_first') or '?'}–{r.get('wb_last') or '?'}, {fmt(r.get('wb_snapshots'))} monthly captures, "
                              f"{pages} pages archived, niche words seen: {r.get('wb_niche_tokens') or 'none'}"))
        if r.get("wb_titles"):
            ev.append(("History", r["wb_titles"]))
    if r.get("hist_peak_etv"):
        ev.append(("Google traffic", f"peak {fmt(r['hist_peak_etv'])}/mo in {r.get('hist_peak_month')}, latest {fmt(r.get('hist_last_etv'))}/mo"))
    created = r.get("rdap_created") or r.get("whois_created")
    age = [f"first registered {created}"] if created else []
    if r.get("cc_hc_pos"):
        age.append(f"Common Crawl link-graph position #{fmt(r['cc_hc_pos'])} of ~135M")
    if age:
        ev.append(("Age / links", "; ".join(age)))
    if r.get("outlink_from"):
        ev.append(("Linked from", r["outlink_from"]))
    return ev


def main(argv=None):
    setup_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args(argv)
    run = Path(a.run)
    niche = load_niche(run)
    table = load_table(run)
    rows = [r for r in table.values() if r.get("tier") and r["tier"] != "X"]
    rows.sort(key=lambda r: -float(r.get("score") or 0))
    top = rows[: a.top]
    rejected = Counter()
    for r in table.values():
        for reason in filter(None, (r.get("reject") or "").split("; ")):
            rejected[reason.split(":")[0]] += 1
    acq = Counter(r.get("acquire") or "unchecked" for r in table.values())
    funnel = {
        "candidates": len(table),
        "buyable (register/backorder/auction)": sum(acq[k] for k in ("register", "backorder", "auction")),
        "backlink-checked": sum(1 for r in table.values() if r.get("bl_deep_checked")),
        "index-checked": sum(1 for r in table.values() if r.get("google_indexed") or r.get("bing_indexed")),
        "Wayback-checked": sum(1 for r in table.values() if r.get("wb_checked")),
        "passed all filters": len(rows),
        "tier A": sum(1 for r in rows if r["tier"] == "A"),
    }
    date = now_utc().strftime("%Y-%m-%d")
    cost = spend(run)

    # ---------------- markdown
    md = [f"# Expired domains for {niche['niche']}", "",
          f"{date} · DataForSEO spend ${cost:.2f} · tokens: {', '.join(niche['tokens'][:15])}{' …' if len(niche['tokens']) > 15 else ''}", "",
          "## Funnel", ""]
    md += [f"- {k}: {v:,}" for k, v in funnel.items()]
    md += ["", "## Shortlist", "",
           "Index: both = Google and Bing, google only / bing only, none; Ref. domains: clean/total once deep-checked.", "",
           "| # | Domain | Tier | Score | Buy | Index | Google | Bing | Wiki | Rank | Ref. domains | Spam | Since | Warnings |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(top, 1):
        md.append(f"| {i} | {r['domain']} | {r['tier']} | {r['score']} | {r.get('acquire') or '–'} | "
                  f"{r.get('idx_summary') or '–'} | {r.get('google_indexed') or '–'} | {r.get('bing_indexed') or '–'} | "
                  f"{fmt(r.get('wiki_links') if r.get('wiki_links') not in (None, '') else r.get('wiki_pages'))} | "
                  f"{fmt(r.get('bl_rank') or r.get('dfs_rank'))} | {rmd_str(r)} | {fmt(r.get('bl_target_spam') or r.get('dfs_spam'))} | "
                  f"{r.get('wb_first') or (r.get('rdap_created') or r.get('whois_created') or '')[:4] or '–'} | {r.get('warnings') or ''} |")
    md += ["", "## Evidence", ""]
    for i, r in enumerate(top, 1):
        md += [f"### {i}. {r['domain']} — tier {r['tier']}, score {r['score']}", "",
               f"**Action:** {ACTION.get(r.get('acquire') or 'check', ACTION['check'])}", ""]
        md += [f"- **{k}:** {v}" for k, v in evidence(r)]
        if r.get("warnings"):
            md.append(f"- **Warnings:** {r['warnings']}")
        md.append("- **Links:** " + " · ".join(f"[{n}]({u})" for n, u in links(r["domain"], r.get("acquire") or "")))
        md.append("")
    md += ["## Rejected", ""] + [f"- {k}: {v:,}" for k, v in rejected.most_common()]
    (run / "report.md").write_text("\n".join(md), encoding="utf-8")

    # ---------------- html
    e = html.escape
    trs = []
    for i, r in enumerate(top, 1):
        trs.append(
            f"<tr><td>{i}</td><td><a href='#d{i}'>{e(r['domain'])}</a></td><td><span class='t t{e(r['tier'])}'>{e(r['tier'])}</span></td>"
            f"<td data-v='{r['score']}'>{r['score']}</td><td>{e(r.get('acquire') or '–')}</td>"
            f"<td>{e(r.get('idx_summary') or '–')}</td><td>{e(r.get('google_indexed') or '–')}</td><td>{e(r.get('bing_indexed') or '–')}</td>"
            f"<td data-v='{num(r, 'wiki_links', num(r, 'wiki_pages', 0)) or 0}'>{fmt(r.get('wiki_links') if r.get('wiki_links') not in (None, '') else r.get('wiki_pages'))}</td>"
            f"<td data-v='{num(r, 'bl_rank', num(r, 'dfs_rank', 0))}'>{fmt(r.get('bl_rank') or r.get('dfs_rank'))}</td>"
            f"<td data-v='{num(r, 'bl_clean_rmd', rmd(r)) or 0}'>{rmd_str(r)}</td><td>{fmt(r.get('bl_target_spam') or r.get('dfs_spam'))}</td>"
            f"<td>{e(r.get('wb_first') or '–')}</td></tr>")
    cards = []
    for i, r in enumerate(top, 1):
        ev = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in evidence(r))
        warn = f"<p class='warn'>⚠ {e(r['warnings'])}</p>" if r.get("warnings") else ""
        lk = " · ".join(f"<a href='{e(u)}' target='_blank' rel='noopener'>{e(n)}</a>" for n, u in links(r["domain"], r.get("acquire") or ""))
        cards.append(
            f"<section class='card' id='d{i}'><h3>{i}. {e(r['domain'])} <span class='t t{e(r['tier'])}'>{e(r['tier'])}</span>"
            f"<span class='sc'>{r['score']}</span></h3>"
            f"<p class='act'>{e(ACTION.get(r.get('acquire') or 'check', ACTION['check']))}</p>"
            f"<div class='bars'>" + "".join(
                f"<div><span>{lbl}</span><i style='--w:{num(r, key, 0)}%'></i><b>{fmt(r.get(key))}</b></div>"
                for lbl, key in (("Authority", "s_auth"), ("Clean", "s_clean"), ("Relevance", "s_rel"),
                                 ("Index", "s_index"), ("Buyability", "s_buy"))) +
            f"</div><dl>{ev}</dl>{warn}<p class='links'>{lk}</p></section>")
    fun = "".join(f"<div><b>{v:,}</b><span>{e(k)}</span></div>" for k, v in funnel.items())
    rej = "".join(f"<li>{e(k)}: {v:,}</li>" for k, v in rejected.most_common())
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Expired Domains: {e(niche['niche'])}</title><style>
:root{{--bg:#f7f7f5;--fg:#1c1c1a;--mut:#6b6b66;--card:#fff;--line:#e4e3de;--acc:#2f6f4f;--a:#2f6f4f;--b:#b07a1c;--c:#7a7a75;--warn:#9a3b1c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151614;--fg:#ecebe6;--mut:#a3a29c;--card:#1e1f1c;--line:#33342f;--acc:#7cc39b;--a:#7cc39b;--b:#e0b25c;--c:#a3a29c;--warn:#f08a6a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 64px}}h1{{font-size:26px;margin:0 0 4px}}.sub{{color:var(--mut);margin:0 0 20px}}
.funnel{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:0 0 24px}}.funnel div{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}}
.funnel b{{display:block;font-size:20px}}.funnel span{{color:var(--mut);font-size:12px}}
.wrap{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}}table{{border-collapse:collapse;width:100%;min-width:720px}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}th{{cursor:pointer;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}}
a{{color:var(--acc)}}.t{{display:inline-block;min-width:22px;text-align:center;border-radius:6px;padding:0 6px;font-weight:700;color:#fff;font-size:12px}}
.tA{{background:var(--a)}}.tB{{background:var(--b)}}.tC{{background:var(--c)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}}.card h3{{margin:0 0 6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.sc{{margin-left:auto;font-size:22px}}.act{{margin:0 0 10px;color:var(--mut)}}.bars{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:6px 16px;margin:0 0 12px}}
.bars div{{display:grid;grid-template-columns:80px 1fr 34px;align-items:center;gap:6px;font-size:12px;color:var(--mut)}}
.bars i{{height:6px;border-radius:3px;background:linear-gradient(90deg,var(--acc) var(--w),var(--line) var(--w))}}
dl{{display:grid;grid-template-columns:150px 1fr;gap:4px 12px;margin:0;font-size:14px}}dt{{color:var(--mut)}}dd{{margin:0;overflow-wrap:anywhere}}
.warn{{color:var(--warn);margin:10px 0 0}}.links{{margin:10px 0 0}}h2{{margin:32px 0 10px}}
@media (max-width:600px){{dl{{grid-template-columns:1fr}}dt{{margin-top:6px}}}}
</style></head><body><main>
<h1>Expired domains: {e(niche['niche'])}</h1><p class="sub">{date} · DataForSEO spend ${cost:.2f} · {len(niche['tokens'])} niche tokens</p>
<div class="funnel">{fun}</div>
<h2>Shortlist</h2><p class="sub">Index: both = Google and Bing · Ref. domains: clean/total once deep-checked</p><div class="wrap"><table id="tb"><thead><tr><th>#</th><th>Domain</th><th>Tier</th><th>Score</th><th>Buy</th><th>Index</th><th>Google</th><th>Bing</th><th>Wiki</th><th>Rank</th><th>Ref. domains</th><th>Spam</th><th>Since</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<h2>Evidence</h2>{''.join(cards)}
<h2>Rejected</h2><ul>{rej}</ul>
<p class="sub">Verify status and price at the registrar before paying. Build a genuinely useful site on the same topic; Google treats buying expired domains to host unrelated or low-value content as spam ("expired domain abuse").</p>
</main><script>
document.querySelectorAll('#tb th').forEach((th,i)=>th.onclick=()=>{{const tb=th.closest('table').tBodies[0];const rows=[...tb.rows];const d=th.dataset.d=th.dataset.d==='1'?'-1':'1';
rows.sort((a,b)=>{{const x=a.cells[i],y=b.cells[i];const vx=x.dataset.v??x.textContent,vy=y.dataset.v??y.textContent;const nx=parseFloat(vx),ny=parseFloat(vy);
return (isNaN(nx)||isNaN(ny)?String(vx).localeCompare(vy):nx-ny)*d}});rows.forEach(r=>tb.appendChild(r))}});
</script></body></html>"""
    (run / "report.html").write_text(page, encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({"funnel": funnel, "spend": round(cost, 4),
                                                  "top": [r["domain"] for r in top]}, indent=2), encoding="utf-8")
    log(f"report: {run / 'report.html'} and report.md ({len(top)} domains)")


if __name__ == "__main__":
    main()
