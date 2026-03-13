"""
gh_utils.py -- GitHub CLI unified utility functions
Shared gh invocation, repo parsing, and output encoding handling for all scripts.
"""

import subprocess
import json
import sys
import re
import time

GH = "gh"


def run_gh(args, timeout=15):
    """Execute a gh command and return the stdout string. Returns None on failure."""
    try:
        result = subprocess.run(
            [GH] + args,
            capture_output=True, text=True,
            timeout=timeout,
            encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, Exception):
        return None


def run_gh_search(query_args, timeout=30, retry_on_rate_limit=True):
    """Execute gh search repos and return the parsed JSON list. Returns [] on failure.

    Automatically handles rate limits: waits 60s then retries once.
    """
    json_fields = "name,owner,description,stargazersCount,forksCount,updatedAt,language,url,createdAt,isArchived"
    cmd = [GH, "search", "repos"] + query_args + ["--json", json_fields]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout,
            encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "rate limit" in stderr.lower() and retry_on_rate_limit:
                sys.stderr.write("  rate limit, waiting 60s...\n")
                time.sleep(60)
                return run_gh_search(query_args, timeout=timeout, retry_on_rate_limit=False)
            sys.stderr.write(f"  search failed: {stderr[:100]}\n")
            return []
        return json.loads(result.stdout) if result.stdout.strip() else []
    except Exception as e:
        sys.stderr.write(f"  search error: {e}\n")
        return []


def parse_repo_input(raw):
    """Parse owner/repo or full GitHub URL, returning (owner, repo_name)."""
    raw = raw.strip().rstrip("/")
    match = re.search(r"github\.com/([^/]+)/([^/]+)", raw)
    if match:
        return match.group(1), match.group(2)
    parts = raw.split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, None


def setup_utf8_stdout():
    """Ensure stdout outputs UTF-8 encoding (Windows compatible)."""
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def print_json(data):
    """Output JSON to stdout with automatic encoding handling."""
    setup_utf8_stdout()
    print(json.dumps(data, ensure_ascii=False, indent=2))
