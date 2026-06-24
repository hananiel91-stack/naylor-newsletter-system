"""
scraper/config.py
=================
Reads newsletters.json from the repo root and returns configs
that are active and due to run today.
"""

import json
import os
from datetime import datetime, timedelta


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "newsletters.json")


def load_all() -> list[dict]:
    """Load all newsletter configs from newsletters.json."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("newsletters", [])


def get_due(name_filter: str = "") -> list[dict]:
    """
    Return configs that should run today.
    If name_filter is set, return only that newsletter (useful for manual runs).
    Adds computed fields: cutoff_date (datetime), target_count (int).
    """
    all_configs = load_all()
    today = datetime.utcnow()
    results = []

    for cfg in all_configs:
        if cfg.get("active", "yes") != "yes":
            continue

        if name_filter and name_filter.lower() not in cfg.get("newsletter_name", "").lower():
            continue

        if not name_filter and not _is_due(cfg, today):
            continue

        # Compute derived fields
        days = int(cfg.get("cutoff_days", 30))
        cfg["cutoff_date"] = today - timedelta(days=days)
        cfg["target_count"] = int(cfg.get("target_count", 30))
        cfg["source_urls"] = [
            u.strip() for u in cfg.get("source_urls", "").split("\n")
            if u.strip().startswith("http")
        ]
        results.append(cfg)

    return results


def _is_due(cfg: dict, today: datetime) -> bool:
    freq    = cfg.get("frequency", "weekly").lower()
    run_day = cfg.get("run_day", "monday").lower()

    if freq == "daily":
        return True

    days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    today_name = days[today.weekday()]

    if freq == "weekly":
        return today_name == run_day

    if freq == "biweekly":
        week = today.isocalendar()[1]
        return today_name == run_day and week % 2 == 0

    if freq == "monthly":
        if run_day == "1st":  return today.day == 1
        if run_day == "15th": return today.day == 15
        first = today.replace(day=1)
        target = days.index(run_day) if run_day in days else 0
        first_occ = first.day + (target - first.weekday()) % 7
        return today.day == first_occ

    return False
