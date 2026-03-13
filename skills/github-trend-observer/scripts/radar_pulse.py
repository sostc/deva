"""
radar_pulse.py -- Mode 1: Active exploration, fetch recently trending AI/ML projects
Usage: python radar_pulse.py [--days 7]
Output: JSON { scan_date, candidates[], filtered_out_summary }

Strategy:
  1. Search high-star projects created in the last N days (all domains)
  2. Search recent projects under AI/ML related topics
  3. Search actively growing projects (stars 500-10000, recently updated)
  Merge -> AI keyword filter -> output candidate list
"""

import json
import sys
import argparse
from datetime import datetime, timedelta
from gh_utils import run_gh_search, print_json

# AI/ML related keywords (for filtering)
AI_KEYWORDS = [
    "ai", "llm", "agent", "gpt", "model", "inference", "embedding",
    "rag", "vector", "prompt", "copilot", "assistant", "chatbot",
    "transformer", "neural", "machine-learning", "deep-learning",
    "nlp", "language-model", "fine-tune", "training", "mcp",
    "anthropic", "openai", "claude", "gemini", "ollama", "langchain",
    "autogen", "crew", "agentic", "tool-calling", "function-calling"
]

AI_TOPICS = ["llm", "ai-agent", "machine-learning", "generative-ai", "langchain", "rag"]

def infer_topics(repo):
    """Infer topics from search strategy tags (gh search repos does not return the topics field)"""
    strategy = repo.get("_strategy", "")
    topics = []
    if strategy.startswith("topic_"):
        topics.append(strategy.replace("topic_", ""))
    if strategy.startswith("active_growth_"):
        topics.append(strategy.replace("active_growth_", ""))
    return topics

def is_ai_related(repo):
    """Determine whether a repo is AI/ML related (name + description + inferred topics)"""
    text = " ".join([
        (repo.get("description") or "").lower(),
        (repo.get("name") or "").lower()
    ])
    topics = infer_topics(repo)
    combined = text + " " + " ".join(topics)
    return any(kw in combined for kw in AI_KEYWORDS)

def main():
    parser = argparse.ArgumentParser(description="GitHub Radar: Radar Pulse")
    parser.add_argument("--days", "-d", type=int, default=7, help="Search time window (default: 7 days)")
    args = parser.parse_args()

    date_start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    date_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    all_repos = {}

    # Strategy 1: High-star projects created in the last N days
    sys.stderr.write(f"  Strategy 1/3: High-star projects created in the last {args.days} days...\n")
    results = run_gh_search([f"--created=>={date_start}", "--sort", "stars", "--limit", "30"])
    for r in results:
        if not r.get("isArchived"):
            key = f"{r['owner']['login']}/{r['name']}"
            r["_strategy"] = "new_high_star"
            all_repos[key] = r

    # Strategy 2: AI-related topic projects in the last 30 days
    sys.stderr.write("  Strategy 2/3: AI-related topic projects...\n")
    for topic in AI_TOPICS[:3]:  # Limit API calls
        results = run_gh_search([
            f"--topic={topic}", "--sort", "stars", "--limit", "15",
            f"--created=>={date_30d}"
        ])
        for r in results:
            if not r.get("isArchived"):
                key = f"{r['owner']['login']}/{r['name']}"
                if key not in all_repos:
                    r["_strategy"] = f"topic_{topic}"
                    all_repos[key] = r

    # Strategy 3: Actively growing AI projects (add topic filter to reduce non-AI noise)
    sys.stderr.write("  Strategy 3/3: Actively growing AI projects...\n")
    growth_repos_found = 0
    for topic in ["llm", "ai-agent", "generative-ai", "machine-learning"]:
        if growth_repos_found >= 20:
            break
        results = run_gh_search([
            f"--topic={topic}", "--stars=500..10000", "--sort", "updated", "--limit", "10"
        ])
        for r in results:
            if not r.get("isArchived"):
                key = f"{r['owner']['login']}/{r['name']}"
                if key not in all_repos:
                    r["_strategy"] = f"active_growth_{topic}"
                    all_repos[key] = r
                    growth_repos_found += 1

    # AI filter
    ai_repos = []
    non_ai_count = 0
    for key, r in all_repos.items():
        if is_ai_related(r):
            ai_repos.append({
                "full_name": key,
                "description": r.get("description", ""),
                "stars": r.get("stargazersCount", 0),
                "forks": r.get("forksCount", 0),
                "language": r.get("language", "N/A") or "N/A",
                "created": r.get("createdAt", "")[:10],
                "updated": r.get("updatedAt", "")[:10],
                "url": r.get("url", ""),
                "topics": infer_topics(r),
                "_strategy": r.get("_strategy", "")
            })
        else:
            non_ai_count += 1

    # Sort by star count
    ai_repos.sort(key=lambda x: x["stars"], reverse=True)

    print_json({
        "scan_date": datetime.now().strftime("%Y-%m-%d"),
        "days_window": args.days,
        "total_scanned": len(all_repos),
        "ai_related": len(ai_repos),
        "filtered_non_ai": non_ai_count,
        "candidates": ai_repos
    })

if __name__ == "__main__":
    main()
