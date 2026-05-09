#!/usr/bin/env python3
"""Invoke the local Naja Agent API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def request_json(base_url: str, path: str, payload: dict | None = None, method: str | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Talk to the local Naja Agent")
    parser.add_argument(
        "command",
        nargs="?",
        default="ask",
        choices=["ask", "digest", "send", "capabilities", "endpoints"],
    )
    parser.add_argument("text", nargs="*", help="Question text for ask")
    parser.add_argument("--base-url", default="http://127.0.0.1:8888")
    parser.add_argument("--group", help="Filter endpoints by group, such as attention, market, cognition")
    parser.add_argument("--channel", action="append", dest="channels", help="Notification channel, repeatable")
    parser.add_argument("--confirm", action="store_true", help="Confirm external notification sending")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON")
    args = parser.parse_args()

    try:
        if args.command == "ask":
            question = " ".join(args.text).strip()
            result = request_json(args.base_url, "/api/naja/skill", {
                "skill": "ask",
                "payload": {"question": question},
            })
            data = result.get("data", {})
            output = data if args.raw else data.get("answer", "")
        elif args.command == "digest":
            result = request_json(args.base_url, "/api/naja/skill", {"skill": "digest"})
            data = result.get("data", {})
            output = data if args.raw else data.get("markdown", "")
        elif args.command == "endpoints":
            payload = {"skill": "api_catalog", "payload": {}}
            if args.group:
                payload["payload"]["group"] = args.group
            result = request_json(args.base_url, "/api/naja/skill", payload)
            data = result.get("data", {})
            output = data if args.raw else data.get("markdown", "")
        elif args.command == "send":
            result = request_json(args.base_url, "/api/naja/skill", {
                "skill": "send_digest",
                "confirm": args.confirm,
                "payload": {"channels": args.channels or ["dingtalk", "phone"], "force": True},
            })
            output = result if args.raw else json.dumps(result.get("data", {}), ensure_ascii=False, indent=2)
        else:
            result = request_json(args.base_url, "/api/naja/agent")
            output = result if args.raw else json.dumps(result.get("data", {}), ensure_ascii=False, indent=2)
    except urllib.error.URLError as exc:
        print(f"Naja Agent unavailable: {exc}", file=sys.stderr)
        return 1

    if isinstance(output, str):
        print(output)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
