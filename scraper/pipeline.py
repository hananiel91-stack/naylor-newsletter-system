"""
scraper/pipeline.py
===================
Main entry point. Called by GitHub Actions.
Reads configs, runs the full pipeline for each due newsletter.
"""

import logging
import os
import re
import sys
import time
from datetime import datetime

from config import get_due
from web import make_session, fetch, find_articles, fetch_body, CRAWL_DELAY
from summarize import summarize_articles
from email_brevo import send_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)


def run():
    name_filter = os.environ.get("NEWSLETTER_NAME", "").strip()
    configs = get_due(name_filter)

    if not configs:
        label = f"matching '{name_filter}'" if name_filter else "due today"
        logging.info(f"No newsletters {label}. Nothing to do.")
        return

    logging.info(f"Running {len(configs)} newsletter(s).")
    results = [_run_one(cfg) for cfg in configs]

    sent   = sum(1 for r in results if r["status"] == "sent")
    failed = len(results) - sent
    logging.info(f"Done. {sent} sent, {failed} failed.")

    if failed:
        sys.exit(1)


def _run_one(cfg: dict) -> dict:
    name    = cfg["newsletter_name"]
    cutoff  = cfg["cutoff_date"]
    target  = cfg["target_count"]
    sources = cfg["source_urls"]
    editor  = cfg["editor_email"]

    # New config fields (with safe defaults for existing newsletters)
    topic_focus      = cfg.get("topic_focus", "").strip()
    custom_prompt    = cfg.get("custom_prompt", "").strip()
    web_search       = cfg.get("web_search_enabled", "yes") != "no"
    allow_undated    = cfg.get("allow_undated", "yes") != "no"

    logging.info(f"--- {name} | {len(sources)} sources | cutoff {cutoff.date()} ---")
    session = make_session()

    # ── Phase 1: Crawl ────────────────────────────────────────────────────────
    candidates, blocked, site_results = [], [], {}

    for url in sources:
        site = url.split("/")[2].replace("www.", "")
        html, final_url = fetch(url, session)
        if not html:
            blocked.append(site)
            site_results[site] = {"dated": 0, "undated": 0, "blocked": True}
            time.sleep(CRAWL_DELAY)
            continue

        articles = find_articles(html, final_url)
        dated    = [a for a in articles if a["pub_date"] and a["pub_date"] >= cutoff]
        undated  = [a for a in articles if not a["pub_date"]]
        site_results[site] = {"dated": len(dated), "undated": len(undated), "blocked": False}

        logging.info(f"  {site}: {len(dated)} dated, {len(undated)} undated")
        candidates.extend(dated)
        if allow_undated:
            for a in undated[:3]:
                a["undated"] = True
            candidates.extend(undated[:3])
        time.sleep(CRAWL_DELAY)

    dated_first  = [a for a in candidates if not a.get("undated")]
    undated_rest = [a for a in candidates if a.get("undated")]
    to_process   = (dated_first + undated_rest)[:min(target + 5, 50)]

    logging.info(f"  Total: {len(dated_first)} dated + {len(undated_rest)} undated")

    if not to_process and not web_search:
        logging.warning(f"  No articles found for {name}.")
        return {"newsletter": name, "status": "no_articles"}

    # ── Phase 2: Fetch bodies ─────────────────────────────────────────────────
    for art in to_process:
        art["body"] = fetch_body(art["url"], session)
        time.sleep(CRAWL_DELAY)

    # ── Phase 3: Summarize (+ optional web search) ────────────────────────────
    results = summarize_articles(
        to_process, name,
        topic_focus=topic_focus,
        custom_prompt=custom_prompt,
        web_search_enabled=web_search,
        recency_days=cfg.get("cutoff_days", 30)
    )
    if not results:
        return {"newsletter": name, "status": "summarization_failed"}

    # Split into fixed-source and discovered
    fixed      = [r for r in results if not r.get("discovered")]
    discovered = [r for r in results if r.get("discovered")]

    # Trim fixed to target, keep all discovered (they're bonus)
    fixed = fixed[:target]
    results = fixed + discovered

    # ── Phase 4: Build run summary ────────────────────────────────────────────
    run_summary = _build_run_summary(
        cfg=cfg,
        site_results=site_results,
        blocked=blocked,
        dated_count=len(dated_first),
        undated_count=len(undated_rest),
        fixed_count=len(fixed),
        discovered_count=len(discovered),
        web_search=web_search,
        topic_focus=topic_focus,
    )

    # ── Phase 5: Format digest ────────────────────────────────────────────────
    digest = _format(results, cfg, run_summary)

    # ── Phase 6: Email ────────────────────────────────────────────────────────
    ok, msg = send_digest(editor, name, digest)
    logging.info(f"  Email: {'✓' if ok else '✗'} {msg}")
    if blocked:
        logging.warning(f"  Blocked sites: {', '.join(blocked)}")

    return {"newsletter": name, "status": "sent" if ok else "email_failed"}


def _build_run_summary(cfg, site_results, blocked, dated_count, undated_count,
                        fixed_count, discovered_count, web_search, topic_focus):
    """Plain-English summary shown at the top of every digest email."""
    lines = []
    total_sources = len(site_results)
    working = sum(1 for s in site_results.values() if not s["blocked"])

    lines.append(f"Articles from your source list: {fixed_count} of {cfg['target_count']} requested")
    lines.append(f"Sources checked: {working} of {total_sources} responded")

    if blocked:
        lines.append(f"Inaccessible this run ({len(blocked)}): {', '.join(blocked)}")
        lines.append("  → This is normal. These sites occasionally block automated access.")

    if dated_count == 0 and undated_count > 0:
        lines.append(f"Note: {undated_count} articles found but publish dates couldn't be confirmed — included as fallback.")

    if web_search:
        if discovered_count > 0:
            lines.append(f"New sources discovered via web search: {discovered_count} article(s) — marked below with ★")
        else:
            lines.append("Web search ran but found no additional articles beyond your source list.")
    
    if topic_focus:
        lines.append(f"Topic focus applied: \"{topic_focus}\"")

    return lines


def _format(results, cfg, run_summary):
    """Format the full digest with run summary header."""
    cutoff = cfg["cutoff_date"]
    lines = [
        "=" * 65,
        "NAYLOR NEWSLETTER CONTENT DIGEST",
        f"Newsletter: {cfg['newsletter_name']}",
        f"Articles since: {cutoff.strftime('%B %-d, %Y')}",
        f"Generated: {datetime.utcnow().strftime('%B %-d, %Y at %-I:%M %p')} UTC",
        "",
        "── THIS RUN ─────────────────────────────────────────────",
    ]
    for line in run_summary:
        lines.append(f"  {line}")
    lines += ["─" * 65, ""]

    for i, a in enumerate(results, 1):
        prefix = "★ " if a.get("discovered") else ""
        lines.append(f"{i}. {prefix}{a['title']}")
        lines.append(f"   {a['summary']} (_{a['source_name']}_)")
        lines.append(f"   {a['url']}")
        lines.append("")

    lines += ["─" * 65, "Naylor Newsletter Content System"]
    return "\n".join(lines)


if __name__ == "__main__":
    run()
