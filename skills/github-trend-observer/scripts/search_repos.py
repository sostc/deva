"""
search_repos.py -- Direction Search: multi-keyword multi-dimensional GitHub repo search
Usage:
  Single keyword: python search_repos.py "agent swarm"
  Multi keyword:  python search_repos.py "agent swarm" --also "swarm orchestration" "agent fleet"
  Full:           python search_repos.py "agent swarm" --also "swarm coordination" --min-stars 50 --min-recall 50
Output: JSON { keywords[], total_found, repos[] }

Search strategy (three rounds per keyword + topic supplement):
  1. Main search (sort by stars, limit 30)
  2. New projects in the last 90 days (limit 20, lower threshold)
  3. Growing projects (stars min..5000, limit 20)
  4. Topic supplementary search -- extracts core words from keywords and searches by GitHub topic tags
     Catches head projects missed by keyword search (e.g., mem0, memU whose names don't contain keywords but topics match)
  All keyword results are merged and deduplicated before output

Minimum recall guarantee:
  --min-recall N (default 50): if fewer than N after dedup, automatically expand search with fallback keywords
  Fallback keywords provided via --expand, consumed in order until target is met or exhausted

Relevance filtering is handled by the Agent at the workflow level (not within this script):
  Layer 1 -- Agent generates keywords, self-reviews relevance, removes irrelevant ones before passing in
  Layer 2 -- After script returns results, Agent classifies relevance before analysis
"""

import sys
import argparse
from datetime import datetime, timedelta
from gh_utils import run_gh_search, print_json

TOPIC_STOP_WORDS = {
    "the", "a", "an", "for", "of", "in", "on", "with", "and", "or", "to",
    "is", "are", "was", "were", "be", "been", "based", "using", "via",
    "layer", "system", "management", "retrieval", "state", "context",
    "long", "term", "short", "conversation", "persistence",
}


def extract_topics(keywords):
    """Extract topic search words from keywords, sorted by frequency"""
    words = {}
    for kw in keywords:
        for w in kw.lower().split():
            w = w.strip("\"'")
            if w and w not in TOPIC_STOP_WORDS and len(w) > 2:
                words[w] = words.get(w, 0) + 1
    return sorted(words.keys(), key=lambda x: -words[x])


def search_by_topics(topics, all_repos, language=None, min_stars=100):
    """Supplementary search using GitHub topic tags, catching head projects missed by keyword search"""
    if len(topics) < 2:
        return 0

    lang_args = ["--language", language] if language else []
    added_total = 0
    seen_combos = set()

    # Generate topic pair combinations: anchor on the most frequent word, pair with others (up to 3)
    # Avoids noisy combos between non-core words (e.g., agent+llm matches all AI agent projects)
    anchor = topics[0]  # most frequent core word
    combos = []
    for t in topics[1:]:
        combo = tuple(sorted([anchor, t]))
        if combo not in seen_combos:
            seen_combos.add(combo)
            combos.append((anchor, t))
        if len(combos) >= 3:
            break

    for t1, t2 in combos:
        sys.stderr.write(f"  [topic] supplementary search: topic:{t1} + topic:{t2}...\n")
        results = run_gh_search(
            ["--sort", "stars", "--limit", "30", "--topic", t1, "--topic", t2] + lang_args
        )
        added = 0
        for r in results:
            if r.get("isArchived"):
                continue
            if r.get("stargazersCount", 0) < min_stars:
                continue
            key = f"{r['owner']['login']}/{r['name']}"
            if key not in all_repos:
                r["_source"] = f"topic:{t1}+{t2}"
                all_repos[key] = r
                added += 1
        added_total += added
        sys.stderr.write(f"  [topic] added {added} new\n")

    return added_total


def search_one_keyword(keyword, all_repos, language=None, min_stars=100):
    """Execute three rounds of search for a single keyword, merging results into all_repos"""
    lang_args = ["--language", language] if language else []
    date_90d = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    added = 0

    # Search 1: main keyword
    sys.stderr.write(f"  [{keyword}] 1/3: main search...\n")
    results = run_gh_search([keyword, "--sort", "stars", "--limit", "30"] + lang_args)
    for r in results:
        if r.get("isArchived"):
            continue
        if r.get("stargazersCount", 0) < min_stars:
            continue
        key = f"{r['owner']['login']}/{r['name']}"
        if key not in all_repos:
            r["_source"] = f"main:{keyword}"
            all_repos[key] = r
            added += 1

    # Search 2: new projects in the last 90 days
    sys.stderr.write(f"  [{keyword}] 2/3: projects from the last 90 days...\n")
    results = run_gh_search(
        [keyword, "--sort", "stars", "--limit", "20", f"--created=>={date_90d}"] + lang_args
    )
    for r in results:
        if r.get("isArchived"):
            continue
        if r.get("stargazersCount", 0) < 20:
            continue
        key = f"{r['owner']['login']}/{r['name']}"
        if key not in all_repos:
            r["_source"] = f"recent:{keyword}"
            all_repos[key] = r
            added += 1

    # Search 3: growing projects
    sys.stderr.write(f"  [{keyword}] 3/3: growing projects...\n")
    results = run_gh_search(
        [keyword, "--sort", "stars", "--limit", "20", f"--stars={min_stars}..5000"] + lang_args
    )
    for r in results:
        if r.get("isArchived"):
            continue
        key = f"{r['owner']['login']}/{r['name']}"
        if key not in all_repos:
            r["_source"] = f"growth:{keyword}"
            all_repos[key] = r
            added += 1

    sys.stderr.write(f"  [{keyword}] added {added} new\n")
    return added


def search(keywords, language=None, min_stars=100, min_recall=50, expand_keywords=None, topics=None):
    """Search all keywords and merge with dedup; expand with expand_keywords if below min_recall"""
    all_repos = {}

    # Round 1: primary keywords
    for kw in keywords:
        search_one_keyword(kw, all_repos, language, min_stars)

    sys.stderr.write(f"\n  === Round 1 complete: {len(all_repos)} deduplicated results (target: {min_recall}) ===\n\n")

    # Topic supplementary search: catch head projects missed by keyword search
    topic_list = topics if topics else extract_topics(keywords)
    if len(topic_list) >= 2:
        topic_added = search_by_topics(topic_list, all_repos, language, min_stars)
        sys.stderr.write(f"\n  === Topic supplement complete: {topic_added} new, {len(all_repos)} total deduplicated ===\n\n")

    # Round 2: if below min_recall, expand with fallback keywords
    used_expand = []
    if expand_keywords and len(all_repos) < min_recall:
        for kw in expand_keywords:
            if kw in keywords:
                continue
            sys.stderr.write(f"  [expand] Recall insufficient, adding keyword: {kw}\n")
            search_one_keyword(kw, all_repos, language, min_stars)
            used_expand.append(kw)
            if len(all_repos) >= min_recall:
                sys.stderr.write(f"\n  === Expansion complete: {len(all_repos)} deduplicated results, target met ===\n\n")
                break

        if len(all_repos) < min_recall:
            sys.stderr.write(f"\n  === Expansion exhausted: {len(all_repos)} deduplicated results, target not met ===\n\n")

    keywords = keywords + used_expand

    # Sort by stars descending
    repos_list = sorted(all_repos.values(), key=lambda x: x.get("stargazersCount", 0), reverse=True)

    # Clean output format
    cleaned = []
    for r in repos_list:
        cleaned.append({
            "full_name": f"{r['owner']['login']}/{r['name']}",
            "description": r.get("description", ""),
            "stars": r.get("stargazersCount", 0),
            "forks": r.get("forksCount", 0),
            "language": r.get("language", "N/A") or "N/A",
            "updated": r.get("updatedAt", "")[:10],
            "created": r.get("createdAt", "")[:10],
            "url": r.get("url", ""),
            "license": (r.get("license") or {}).get("name", "N/A") if isinstance(r.get("license"), dict) else (r.get("license") or "N/A"),
            "archived": r.get("isArchived", False),
            "_source": r.get("_source", "")
        })

    return {
        "keywords": keywords,
        "language_filter": language,
        "min_stars": min_stars,
        "total_found": len(cleaned),
        "repos": cleaned
    }


def main():
    parser = argparse.ArgumentParser(description="GitHub Radar: Direction Search")
    parser.add_argument("keyword", help="Primary search keyword")
    parser.add_argument("--also", "-a", nargs="+", default=[], help="Additional keywords (expand recall)")
    parser.add_argument("--expand", "-e", nargs="+", default=[], help="Fallback keywords (auto-enabled when recall is insufficient)")
    parser.add_argument("--topics", "-t", nargs="+", default=None, help="Topic tags for supplementary search (auto-extracted from keywords if not provided)")
    parser.add_argument("--language", "-l", default=None, help="Programming language filter")
    parser.add_argument("--min-stars", "-s", type=int, default=100, help="Minimum star count (default: 100)")
    parser.add_argument("--min-recall", "-r", type=int, default=50, help="Minimum recall count (default: 50)")
    args = parser.parse_args()

    keywords = [args.keyword] + args.also
    result = search(keywords, args.language, args.min_stars, args.min_recall, args.expand, args.topics)
    print_json(result)


if __name__ == "__main__":
    main()
