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

    # Summary
    sent    = sum(1 for r in results if r["status"] == "sent")
    failed  = len(results) - sent
    logging.info(f"Done. {sent} sent, {failed} failed.")

    if failed:
        sys.exit(1)   # Causes the GitHub Actions run to show as failed


def _run_one(cfg: dict) -> dict:
    name    = cfg["newsletter_name"]
    cutoff  = cfg["cutoff_date"]
    target  = cfg["target_count"]
    sources = cfg["source_urls"]
    editor  = cfg["editor_email"]

    logging.info(f"--- {name} | {len(sources)} sources | cutoff {cutoff.date()} ---")
    session = make_session()

    # Phase 1: crawl
    candidates, blocked = [], []
    for url in sources:
        site = url.split("/")[2].replace("www.", "")
        html, final_url = fetch(url, session)
        if not html:
            blocked.append(site)
            time.sleep(CRAWL_DELAY)
            continue

        articles = find_articles(html, final_url)
        dated    = [a for a in articles if a["pub_date"] and a["pub_date"] >= cutoff]
        undated  = [a for a in articles if not a["pub_date"]]
        logging.info(f"  {site}: {len(dated)} dated, {len(undated)} undated")

        candidates.extend(dated)
        for a in undated[:3]:
            a["undated"] = True
        candidates.extend(undated[:3])
        time.sleep(CRAWL_DELAY)

    dated_first  = [a for a in candidates if not a.get("undated")]
    undated_rest = [a for a in candidates if a.get("undated")]
    to_process   = (dated_first + undated_rest)[:min(target + 5, 50)]

    logging.info(f"  Total: {len(dated_first)} dated + {len(undated_rest)} undated")

    if not to_process:
        logging.warning(f"  No articles found for {name}.")
        return {"newsletter": name, "status": "no_articles"}

    # Phase 2: fetch bodies
    for art in to_process:
        art["body"] = fetch_body(art["url"], session)
        time.sleep(CRAWL_DELAY)

    # Phase 3: summarize
    results = summarize_articles(to_process, name)
    if not results:
        return {"newsletter": name, "status": "summarization_failed"}
    results = results[:target]

    # Phase 4: format
    digest = _format(results, cfg)

    # Phase 5: email
    ok, msg = send_digest(editor, name, digest)
    logging.info(f"  Email: {'✓' if ok else '✗'} {msg}")
    if blocked:
        logging.warning(f"  Blocked sites: {', '.join(blocked)}")

    return {"newsletter": name, "status": "sent" if ok else "email_failed"}


def _format(results: list[dict], cfg: dict) -> str:
    cutoff = cfg["cutoff_date"]
    lines = [
        "=" * 65,
        "NAYLOR NEWSLETTER CONTENT DIGEST",
        f"Newsletter: {cfg['newsletter_name']}",
        f"Articles since: {cutoff.strftime('%B %-d, %Y')}",
        f"Articles found: {len(results)} of {cfg['target_count']} requested",
        f"Generated: {datetime.utcnow().strftime('%B %-d, %Y at %-I:%M %p')} UTC",
        "=" * 65, "",
    ]
    for i, a in enumerate(results, 1):
        lines.append(f"{i}. {a['title']}")
        lines.append(f"   {a['summary']} (_{a['source_name']}_)")
        lines.append(f"   {a['url']}")
        lines.append("")
    lines += ["─" * 65, "Naylor Newsletter Content System"]
    return "\n".join(lines)


if __name__ == "__main__":
    run()
