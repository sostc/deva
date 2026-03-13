"""
deep_link.py — Mode 4: Deep Link Analysis
Usage: python deep_link.py <owner/repo or GitHub URL>
Output: JSON {
    repo, base, readme_excerpt, commits_distribution,
    star_history, contributors_top10, releases_recent,
    issue_analysis, high_star_forks, owner_other_repos,
    ecosystem, competitor_candidates
}

v2 changes:
  - Integrated star history (calls fetch_star_history.py)
  - Fetch first 500 chars of README
  - Commit distribution (7d/30d/90d breakdown)
  - Extended ecosystem search (description mentions + plugin/wrapper/extension)
  - Competitor candidate discovery (topic-based search for same-track projects)
"""

import subprocess
import json
import sys
import os
import re
from datetime import datetime, timedelta
from gh_utils import run_gh, parse_repo_input, print_json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_base_info(repo):
    """Basic metadata"""
    fields = "name,owner,description,url,stargazerCount,forkCount,watchers,createdAt,updatedAt,"
    fields += "primaryLanguage,licenseInfo,homepageUrl,repositoryTopics,isArchived"
    raw = run_gh(["repo", "view", repo, "--json", fields])
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return {}


def get_readme(repo):
    """Fetch first 500 chars of README"""
    raw = run_gh(["api", f"repos/{repo}/readme",
                  "-H", "Accept: application/vnd.github.raw"], timeout=10)
    if raw:
        lines = raw.split("\n")
        excerpt = ""
        for line in lines:
            if len(excerpt) + len(line) + 1 > 500:
                break
            excerpt += line + "\n"
        return excerpt.strip()
    return ""


def get_commits_distribution(repo):
    """Commit distribution: 7d / 30d / 90d"""
    now = datetime.now()
    windows = {
        "7d": (now - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z"),
        "30d": (now - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z"),
        "90d": (now - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z"),
    }

    result = {}
    for label, since in windows.items():
        raw = run_gh([
            "api", f"repos/{repo}/commits?since={since}&per_page=1",
            "--include"
        ], timeout=10)
        if not raw:
            result[label] = 0
            continue
        match = re.search(r'page=(\d+)>; rel="last"', raw)
        result[label] = int(match.group(1)) if match else 1

    return result


def get_star_history(repo):
    """Call fetch_star_history.py to get star growth data"""
    script = os.path.join(SCRIPT_DIR, "fetch_star_history.py")
    try:
        result = subprocess.run(
            [sys.executable, script, repo],
            capture_output=True, text=True, timeout=120,
            encoding='utf-8', errors='replace'
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        sys.stderr.write(f"  star history failed: {e}\n")
    return {}


def get_contributors(repo):
    """Top 10 contributors"""
    raw = run_gh(["api", f"repos/{repo}/contributors?per_page=10",
                  "--jq", "[.[] | {login, contributions}]"])
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return []


def get_releases(repo):
    """Recent 10 releases"""
    raw = run_gh(["release", "list", "-R", repo, "--limit", "10",
                  "--json", "tagName,publishedAt,name"])
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return []


def analyze_issues(repo):
    """Issue composition analysis"""
    raw = run_gh(["issue", "list", "-R", repo, "--limit", "100", "--state", "all",
                  "--json", "title,labels,createdAt,comments,state"])
    if not raw:
        return {"total_sampled": 0, "breakdown": {}}

    try:
        issues = json.loads(raw)
    except json.JSONDecodeError:
        return {"total_sampled": 0, "breakdown": {}}

    categories = {
        "integration": 0,
        "feature_request": 0,
        "bug": 0,
        "ecosystem_question": 0,
        "other": 0
    }

    for iss in issues:
        title = (iss.get("title") or "").lower()
        labels = " ".join(l.get("name", "").lower() for l in (iss.get("labels") or []))
        text = f"{title} {labels}"

        if any(w in text for w in ["integrat", "support for", "connect", "compat", "work with"]):
            categories["integration"] += 1
        elif any(w in text for w in ["feature", "request", "enhancement", "proposal", "suggest"]):
            categories["feature_request"] += 1
        elif any(w in text for w in ["bug", "fix", "error", "crash", "broken", "fail"]):
            categories["bug"] += 1
        elif any(w in text for w in ["how to", "example", "tutorial", "use with", "question"]):
            categories["ecosystem_question"] += 1
        else:
            categories["other"] += 1

    total = sum(categories.values())
    breakdown = {}
    if total > 0:
        for k, v in categories.items():
            breakdown[k] = {"count": v, "pct": round(v / total * 100, 1)}

    # Issue engagement metrics
    def _comment_count(iss):
        c = iss.get("comments", 0)
        return len(c) if isinstance(c, list) else int(c or 0)

    comment_counts = [_comment_count(iss) for iss in issues]
    avg_comments = round(sum(comment_counts) / len(comment_counts), 1) if comment_counts else 0
    high_engagement = sum(1 for c in comment_counts if c >= 5)
    zero_reply = sum(1 for c in comment_counts if c == 0)

    other_pct = round(categories["other"] / total * 100, 1) if total > 0 else 0

    recent_titles = []
    if other_pct > 50:
        sorted_issues = sorted(issues, key=lambda x: x.get("createdAt", ""), reverse=True)
        for iss in sorted_issues[:10]:
            recent_titles.append({
                "title": iss.get("title", ""),
                "state": iss.get("state", ""),
                "comments": _comment_count(iss),
                "labels": [l.get("name", "") for l in (iss.get("labels") or [])]
            })

    return {
        "total_sampled": total,
        "breakdown": breakdown,
        "engagement": {
            "avg_comments": avg_comments,
            "high_engagement_count": high_engagement,
            "zero_reply_count": zero_reply,
            "zero_reply_pct": round(zero_reply / total * 100, 1) if total > 0 else 0
        },
        "classification_quality": "low" if other_pct > 50 else "normal",
        "recent_titles": recent_titles
    }


def get_high_star_forks(repo):
    """Forks with stars"""
    raw = run_gh(["api", f"repos/{repo}/forks?sort=stargazers&per_page=10",
                  "--jq", "[.[] | {full_name, stars: .stargazers_count, description, url: .html_url}]"])
    if not raw:
        return []
    try:
        forks = json.loads(raw)
        return [f for f in forks if f.get("stars", 0) > 0]
    except json.JSONDecodeError:
        return []


def get_owner_repos(owner, exclude_repo):
    """Other repos by the same owner"""
    raw = run_gh(["api", f"users/{owner}/repos?sort=stars&per_page=20",
                  "--jq",
                  f'[.[] | select(.name != "{exclude_repo}") | '
                  f'{{full_name, stars: .stargazers_count, description, language, url: .html_url}}]'])
    if not raw:
        return []
    try:
        repos = json.loads(raw)
        return repos[:10]
    except json.JSONDecodeError:
        return []


def search_ecosystem(repo, repo_name):
    """Extended ecosystem search: plugin/wrapper/extension + description mentions"""
    eco = {"by_suffix": [], "by_mention": []}

    for suffix in ["plugin", "wrapper", "extension", "integration"]:
        query = f"{repo_name} {suffix}"
        raw = run_gh(["search", "repos", query, "--sort", "stars", "--limit", "5",
                      "--json", "name,owner,stargazersCount,description,url"])
        if raw:
            try:
                results = json.loads(raw)
                for r in results:
                    full = f"{r['owner']['login']}/{r['name']}"
                    if full.lower() != repo.lower() and r.get("stargazersCount", 0) > 0:
                        item = {
                            "full_name": full,
                            "stars": r.get("stargazersCount", 0),
                            "description": r.get("description", "") or "",
                            "url": r.get("url", ""),
                            "match": suffix
                        }
                        if not any(e["full_name"] == full for e in eco["by_suffix"]):
                            eco["by_suffix"].append(item)
            except json.JSONDecodeError:
                pass

    raw = run_gh(["search", "repos", f'"{repo_name}" in:description,readme',
                  "--sort", "stars", "--limit", "10",
                  "--json", "name,owner,stargazersCount,description,url"])
    if raw:
        try:
            results = json.loads(raw)
            for r in results:
                full = f"{r['owner']['login']}/{r['name']}"
                if full.lower() != repo.lower() and r.get("stargazersCount", 0) > 0:
                    item = {
                        "full_name": full,
                        "stars": r.get("stargazersCount", 0),
                        "description": r.get("description", "") or "",
                        "url": r.get("url", "")
                    }
                    if not any(e["full_name"] == full for e in eco["by_mention"]):
                        eco["by_mention"].append(item)
        except json.JSONDecodeError:
            pass

    return eco


def find_competitor_candidates(repo, base_info):
    """Search for same-track projects as competitor candidates based on topics"""
    topics = []
    for t in (base_info.get("repositoryTopics") or []):
        name = t.get("name", "") if isinstance(t, dict) else str(t)
        if name:
            topics.append(name)

    if not topics:
        desc = (base_info.get("description") or "")[:100]
        if desc:
            topics = [desc]

    candidates = []
    seen = set()
    seen.add(repo.lower())

    for topic in topics[:3]:
        raw = run_gh(["search", "repos", f"topic:{topic}",
                      "--sort", "stars", "--limit", "5",
                      "--json", "name,owner,stargazersCount,description,url,createdAt"])
        if not raw:
            continue
        try:
            results = json.loads(raw)
            for r in results:
                full = f"{r['owner']['login']}/{r['name']}"
                if full.lower() not in seen and r.get("stargazersCount", 0) > 50:
                    seen.add(full.lower())
                    candidates.append({
                        "full_name": full,
                        "stars": r.get("stargazersCount", 0),
                        "description": r.get("description", "") or "",
                        "url": r.get("url", ""),
                        "matched_topic": topic
                    })
        except json.JSONDecodeError:
            pass

    candidates.sort(key=lambda x: x["stars"], reverse=True)
    return candidates[:10]


def main():
    if len(sys.argv) < 2:
        print("Usage: python deep_link.py <owner/repo or GitHub URL>")
        sys.exit(1)

    owner, repo_name = parse_repo_input(sys.argv[1])
    if not owner or not repo_name:
        print(json.dumps({"error": f"Cannot parse repo: {sys.argv[1]}"}))
        sys.exit(1)

    repo = f"{owner}/{repo_name}"
    sys.stderr.write(f"  Deep analysis {repo}...\n")

    sys.stderr.write("  1/9 Basic info...\n")
    base = get_base_info(repo)

    sys.stderr.write("  2/9 README...\n")
    readme = get_readme(repo)

    sys.stderr.write("  3/9 Commit distribution...\n")
    commits = get_commits_distribution(repo)

    sys.stderr.write("  4/9 Star history...\n")
    star_history = get_star_history(repo)

    sys.stderr.write("  5/9 Contributors...\n")
    contributors = get_contributors(repo)

    sys.stderr.write("  6/9 Releases...\n")
    releases = get_releases(repo)

    sys.stderr.write("  7/9 Issue analysis...\n")
    issues = analyze_issues(repo)

    sys.stderr.write("  8/9 Forks + owner repos + ecosystem...\n")
    forks = get_high_star_forks(repo)
    owner_repos = get_owner_repos(owner, repo_name)
    ecosystem = search_ecosystem(repo, repo_name)

    sys.stderr.write("  9/9 Competitor candidates...\n")
    competitors = find_competitor_candidates(repo, base)

    # Adoption depth signals
    stars = base.get("stargazerCount", 0) or 0
    fork_count = base.get("forkCount", 0) or 0
    watchers = 0
    if isinstance(base.get("watchers"), dict):
        watchers = base["watchers"].get("totalCount", 0)
    elif isinstance(base.get("watchers"), int):
        watchers = base["watchers"]

    adoption = {
        "fork_ratio": round(fork_count / stars * 100, 1) if stars > 0 else 0,
        "watchers": watchers,
        "watcher_ratio": round(watchers / stars * 100, 1) if stars > 0 else 0,
        "issue_rate": round(issues.get("total_sampled", 0) / stars * 100, 2) if stars > 0 else 0,
        "high_star_forks_count": len(forks),
    }

    print_json({
        "repo": repo,
        "base": base,
        "readme_excerpt": readme,
        "commits_distribution": commits,
        "star_history": star_history,
        "contributors_top10": contributors,
        "releases_recent": releases,
        "issue_analysis": issues,
        "high_star_forks": forks,
        "owner_other_repos": owner_repos,
        "ecosystem": ecosystem,
        "competitor_candidates": competitors,
        "adoption_signals": adoption
    })


if __name__ == "__main__":
    main()
