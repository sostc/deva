#!/usr/bin/env python3
"""Generate demo logs for log_watchdog example."""

import argparse
import random
import time

LEVELS = [
    ("INFO", 0.55),
    ("WARNING", 0.25),
    ("ERROR", 0.15),
    ("CRITICAL", 0.05),
]

MESSAGES = [
    "health check passed",
    "db connection retry",
    "cache miss ratio elevated",
    "request timeout",
    "upstream unavailable",
    "payment callback delayed",
    "worker queue backlog",
]


def weighted_level():
    r = random.random()
    s = 0.0
    for level, prob in LEVELS:
        s += prob
        if r <= s:
            return level
    return "INFO"


def main():
    parser = argparse.ArgumentParser(description="Generate sample app logs")
    parser.add_argument("--file", default="./app.log", help="target log file")
    parser.add_argument("--interval", type=float, default=0.4, help="seconds between lines")
    parser.add_argument("--burst-every", type=int, default=25, help="inject burst every N lines")
    args = parser.parse_args()

    count = 0
    print(f"writing logs to {args.file}")

    while True:
        count += 1
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        if args.burst_every > 0 and count % args.burst_every == 0:
            # simulate an incident burst
            burst_level = random.choice(["ERROR", "CRITICAL", "WARNING"])
            for _ in range(6):
                message = random.choice(MESSAGES)
                line = f"{now} [{burst_level}] service=api request_id={count} msg={message}\n"
                with open(args.file, "a", encoding="utf-8") as f:
                    f.write(line)
                print(line, end="")
                time.sleep(0.05)
        else:
            level = weighted_level()
            message = random.choice(MESSAGES)
            line = f"{now} [{level}] service=api request_id={count} msg={message}\n"
            with open(args.file, "a", encoding="utf-8") as f:
                f.write(line)
            print(line, end="")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
