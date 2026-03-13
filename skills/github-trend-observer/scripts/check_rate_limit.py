"""
check_rate_limit.py -- GitHub API rate limit checker
Usage: python check_rate_limit.py
Output: JSON { remaining, limit, reset_minutes, mode, warning? }
  mode: "full" (>=500) | "degraded" (100-499) | "minimal" (<100)
"""

import json
import sys
import time
from gh_utils import run_gh, print_json

def main():
    raw = run_gh(["api", "rate_limit", "--jq", ".rate"])
    if raw is None:
        print_json({
            "error": "gh command failed",
            "remaining": 0, "limit": 0, "mode": "minimal"
        })
        sys.exit(1)
    data = json.loads(raw)

    remaining = data["remaining"]
    limit = data["limit"]
    reset_ts = data["reset"]
    reset_minutes = max(0, int((reset_ts - time.time()) / 60))

    if remaining >= 500:
        mode = "full"
        warning = None
    elif remaining >= 100:
        mode = "degraded"
        warning = f"Quota low ({remaining}/{limit}): will skip star history fetch, using basic repo info only"
    else:
        mode = "minimal"
        warning = f"Quota critically low ({remaining}/{limit}): will only run gh search, no detail API calls"

    output = {
        "remaining": remaining,
        "limit": limit,
        "reset_minutes": reset_minutes,
        "mode": mode,
    }
    if warning:
        output["warning"] = warning

    print_json(output)

if __name__ == "__main__":
    main()
