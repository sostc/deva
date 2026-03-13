"""
watch_signals.py -- Mode 3: Signal Watch candidate discovery
Usage:
  Global scan:   python watch_signals.py
  Domain scan:   python watch_signals.py --domain ai-agent
Output: JSON { scan_date, domain, candidates[], search_stats }

Search strategy (three windows + optional domain):
  1. Global, created within 7 days, stars > 100, top 30
  2. Global, created within 30 days, stars > 300, top 30
  3. Global, created within 90 days, stars > 1000, top 30
  4. (Optional) Domain keyword, created within 30 days, top 20

After dedup, compute rough velocity (stars/age) and fork_ratio, output sorted by rough velocity descending.
Growth pattern classification is handled by the Agent at the workflow level (not within this script).
"""

import json
import sys
import os
import argparse
from datetime import datetime, timedelta
from gh_utils import run_gh_search, print_json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
KEYWORDS_FILE = os.path.join(SKILL_DIR, "config", "domain_keywords.json")


def search_window(label, created_since, min_stars, limit, keyword=None):
    """Search for high-star projects within a specified time window"""
    date_str = (datetime.now() - timedelta(days=created_since)).strftime("%Y-%m-%d")
    args = [
        f"--created=>={date_str}",
        "--sort", "stars", "--limit", str(limit),
        f"--stars=>={min_stars}"
    ]
    if keyword:
        args.insert(0, keyword)

    sys.stderr.write(f"  [{label}] {created_since}d, >={min_stars} stars, limit {limit}...\n")
    return run_gh_search(args)


def collect_candidates(domain="all"):
    """Three-window global search + optional domain search, deduplicated and merged"""
    all_repos = {}
    stats = {"searches": 0, "raw_total": 0}

    # Window 1: 7 days
    results = search_window("global-7d", 7, 100, 30)
    stats["searches"] += 1
    for r in results:
        _add_repo(all_repos, r)
    stats["raw_total"] += len(results)

    # Window 2: 30 days
    results = search_window("global-30d", 30, 300, 30)
    stats["searches"] += 1
    for r in results:
        _add_repo(all_repos, r)
    stats["raw_total"] += len(results)

    # Window 3: 90 days
    results = search_window("global-90d", 90, 1000, 30)
    stats["searches"] += 1
    for r in results:
        _add_repo(all_repos, r)
    stats["raw_total"] += len(results)

    # Window 4: domain keywords (optional)
    if domain != "all":
        keywords = [domain]
        if os.path.exists(KEYWORDS_FILE):
            try:
                with open(KEYWORDS_FILE, encoding='utf-8') as f:
                    kw_map = json.load(f)
                keywords = kw_map.get(domain, [domain])
            except Exception:
                pass
        for kw in keywords[:3]:  # Use at most 3 keywords
            results = search_window(f"domain-{kw[:20]}", 30, 100, 20, keyword=kw)
            stats["searches"] += 1
            for r in results:
                _add_repo(all_repos, r)
            stats["raw_total"] += len(results)

    sys.stderr.write(f"  === {len(all_repos)} unique candidates from {stats['searches']} searches ===\n")
    stats["unique"] = len(all_repos)
    return all_repos, stats


def _add_repo(all_repos, r):
    """Add repo with deduplication"""
    if r.get("isArchived"):
        return
    key = f"{r['owner']['login']}/{r['name']}"
    if key not in all_repos:
        all_repos[key] = r


def enrich_candidates(all_repos):
    """Compute rough velocity and fork_ratio"""
    now = datetime.now()
    candidates = []

    for key, r in all_repos.items():
        stars = r.get("stargazersCount", 0)
        forks = r.get("forksCount", 0)
        created_str = r.get("createdAt", "")[:10]

        try:
            created = datetime.strptime(created_str, "%Y-%m-%d")
            age_days = max((now - created).days, 1)
        except ValueError:
            age_days = 1

        rough_velocity = round(stars / age_days, 1)
        fork_ratio = round(forks / stars, 3) if stars > 0 else 0

        candidates.append({
            "full_name": key,
            "description": r.get("description", "") or "",
            "stars": stars,
            "forks": forks,
            "language": r.get("language", "N/A") or "N/A",
            "created": created_str,
            "age_days": age_days,
            "url": r.get("url", ""),
            "rough_velocity": rough_velocity,
            "fork_ratio": fork_ratio,
        })

    # Sort by rough velocity descending
    candidates.sort(key=lambda x: x["rough_velocity"], reverse=True)
    return candidates


def main():
    parser = argparse.ArgumentParser(description="GitHub Radar: Signal Watch")
    parser.add_argument("--domain", "-d", default="all",
                        help="monitoring domain (ai-agent, llm-tools, ai-infra, mcp, all)")
    args = parser.parse_args()

    all_repos, stats = collect_candidates(args.domain)
    candidates = enrich_candidates(all_repos)

    print_json({
        "scan_date": datetime.now().strftime("%Y-%m-%d"),
        "domain": args.domain,
        "candidates": candidates,
        "search_stats": stats
    })


if __name__ == "__main__":
    main()
