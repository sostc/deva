"""
fetch_star_history.py -- Fetch repo stargazer timeline, aggregate by day and compute growth metrics
Usage: python fetch_star_history.py <owner/repo>
Output: JSON {
    repo, total_stars, precision,
    growth_7d, growth_30d, avg_daily_7d, avg_daily_30d,
    acceleration, consecutive_growth_days,
    trend_direction, peak_recency, burst_ratio,
    peak_day, recent_7_days[], signals[]
}

Additional metrics:
  trend_direction -- avg of last 3 days / avg of previous 4 days; >1 accelerating, <1 decelerating
  peak_recency   -- days since peak_day to today; 0=today, larger=colder
  burst_ratio    -- peak_day stars / 7d daily avg; high=spike type, low=even type

Smart rate limiting:
  stars < 20000    -> fetch all       -> precision: "exact"
  20000 ~ 50000    -> last 2000 items -> precision: "estimated"
  > 50000          -> last 1000 items -> precision: "trend"
"""

import json
import sys
import time
from datetime import datetime, timedelta
from collections import Counter
from gh_utils import run_gh, parse_repo_input, print_json


def get_star_count(repo):
    raw = run_gh(["api", f"repos/{repo}", "--jq", ".stargazers_count"])
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None

def fetch_stargazers_graphql(repo, max_records):
    """Use GraphQL API to fetch the most recent stargazers.
    Required for repos with >40k stars where REST API can't reach recent data
    (REST returns oldest-first, capped at 400 pages = 40k items)."""
    owner, name = repo.split("/", 1)
    dates = []
    cursor = None
    remaining = max_records

    while remaining > 0:
        batch = min(100, remaining)
        before = f', before: "{cursor}"' if cursor else ""

        query = (
            '{ repository(owner: "' + owner + '", name: "' + name + '") { '
            'stargazers(last: ' + str(batch) + before
            + ', orderBy: {field: STARRED_AT, direction: ASC}) { '
            'edges { starredAt } '
            'pageInfo { hasPreviousPage startCursor } '
            '} } }'
        )

        raw = run_gh(["api", "graphql", "-f", f"query={query}"], timeout=30)
        if raw is None:
            sys.stderr.write("  GraphQL request failed, falling back to REST\n")
            return None

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

        errors = data.get("errors")
        if errors:
            sys.stderr.write(f"  GraphQL error: {errors[0].get('message', '')}\n")
            return None

        sg = data.get("data", {}).get("repository", {}).get("stargazers", {})
        edges = sg.get("edges", [])
        page_info = sg.get("pageInfo", {})

        for edge in edges:
            dates.append(edge["starredAt"][:10])

        remaining -= len(edges)

        if not page_info.get("hasPreviousPage") or len(edges) < batch:
            break

        cursor = page_info["startCursor"]
        time.sleep(0.2)

    return dates


def fetch_stargazers(repo, star_count):
    """Select strategy based on star count and fetch stargazer timeline"""
    if star_count > 50000:
        precision = "trend"
        max_records = 1000
    elif star_count > 20000:
        precision = "estimated"
        max_records = 3000
    else:
        precision = "exact"
        max_records = star_count

    # GitHub REST stargazers API caps at 400 pages (40,000 items, oldest first).
    # For repos >40k stars, REST returns old data, not recent. Use GraphQL instead.
    if star_count > 40000:
        sys.stderr.write(f"  Stars > 40k, using GraphQL API for recent data...\n")
        dates = fetch_stargazers_graphql(repo, max_records)
        if dates is not None:
            return dates, precision, len(dates)
        sys.stderr.write("  GraphQL failed, falling back to REST API...\n")

    per_page = 100
    total_pages_needed = min((max_records + per_page - 1) // per_page, 50)

    # For large repos, fetch from the last few pages (newest data)
    # GitHub API hard limit: stargazers max 400 pages (40000 items)
    MAX_API_PAGE = 400
    if precision != "exact":
        total_pages = min((star_count + per_page - 1) // per_page, MAX_API_PAGE)
        start_page = max(1, total_pages - total_pages_needed + 1)
    else:
        start_page = 1

    dates = []
    page = start_page
    fetched = 0

    for _ in range(total_pages_needed):
        raw = run_gh([
            "api", f"repos/{repo}/stargazers?per_page={per_page}&page={page}",
            "-H", "Accept: application/vnd.github.v3.star+json",
            "--jq", ".[].starred_at"
        ])

        if raw is None or not raw:
            break

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        for line in lines:
            dates.append(line[:10])  # YYYY-MM-DD
        fetched += len(lines)

        if len(lines) < per_page:
            break

        page += 1
        time.sleep(0.1)  # Rate control

    return dates, precision, fetched

def analyze(dates, repo, star_count, precision, fetched):
    """Aggregate by day and compute growth metrics"""
    if not dates:
        return {
            "repo": repo,
            "total_stars": star_count,
            "precision": precision,
            "fetched_records": fetched,
            "error": "no stargazer data retrieved"
        }

    daily = Counter(dates)
    today = datetime.now()
    d7 = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    d30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    growth_7d = sum(v for k, v in daily.items() if k >= d7)
    growth_30d = sum(v for k, v in daily.items() if k >= d30)
    avg_7d = round(growth_7d / 7, 1)
    avg_30d = round(growth_30d / 30, 1)
    acceleration = round(avg_7d / avg_30d, 2) if avg_30d > 0 else 0

    # Consecutive growth days
    consecutive = 0
    started = False
    for i in range(90):
        day_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        count = daily.get(day_str, 0)
        if not started:
            if count > 0:
                started = True
                consecutive = 1
        else:
            if count > 0:
                consecutive += 1
            else:
                break

    # Single-day peak
    peak_day = max(daily.items(), key=lambda x: x[1])

    # Last 7 days detail
    recent_7 = []
    for i in range(7):
        day_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        recent_7.append({"date": day_str, "stars": daily.get(day_str, 0)})

    # trend_direction: avg of last 3 days vs avg of previous 4 days
    recent_3 = [recent_7[i]["stars"] for i in range(min(3, len(recent_7)))]
    prev_4 = [recent_7[i]["stars"] for i in range(3, min(7, len(recent_7)))]
    avg_recent_3 = sum(recent_3) / len(recent_3) if recent_3 else 0
    avg_prev_4 = sum(prev_4) / len(prev_4) if prev_4 else 0
    trend_direction = round(avg_recent_3 / avg_prev_4, 2) if avg_prev_4 > 0 else None

    # peak_recency: days since peak_day
    try:
        peak_date = datetime.strptime(peak_day[0], "%Y-%m-%d")
        peak_recency = (today - peak_date).days
    except ValueError:
        peak_recency = -1

    # burst_ratio: peak_day stars / 7d daily avg
    burst_ratio = round(peak_day[1] / avg_7d, 2) if avg_7d > 0 else 0

    return {
        "repo": repo,
        "total_stars": star_count,
        "precision": precision,
        "fetched_records": fetched,
        "growth_7d": growth_7d,
        "growth_30d": growth_30d,
        "avg_daily_7d": avg_7d,
        "avg_daily_30d": avg_30d,
        "acceleration": acceleration,
        "consecutive_growth_days": consecutive,
        "trend_direction": trend_direction,
        "peak_recency": peak_recency,
        "burst_ratio": burst_ratio,
        "peak_day": {"date": peak_day[0], "stars": peak_day[1]},
        "recent_7_days": recent_7,
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_star_history.py <owner/repo>")
        sys.exit(1)

    raw = sys.argv[1]
    owner, repo_name = parse_repo_input(raw)
    if owner and repo_name:
        repo = f"{owner}/{repo_name}"
    else:
        repo = raw.strip().strip("/")

    star_count = get_star_count(repo)
    if star_count is None:
        print_json({"error": f"Unable to fetch info for {repo}", "repo": repo})
        sys.exit(1)

    if star_count == 0:
        print_json({
            "repo": repo, "total_stars": 0, "precision": "exact",
            "growth_7d": 0, "growth_30d": 0, "signals": []
        })
        return

    sys.stderr.write(f"  Fetching star history for {repo} ({star_count} stars)...\n")
    dates, precision, fetched = fetch_stargazers(repo, star_count)
    result = analyze(dates, repo, star_count, precision, fetched)
    print_json(result)

if __name__ == "__main__":
    main()
