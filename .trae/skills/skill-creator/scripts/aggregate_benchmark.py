#!/usr/bin/env python3
"""Aggregate benchmark results into a summary."""

import json
import argparse
from pathlib import Path
from statistics import mean, stdev


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path, help="Path to iteration workspace")
    parser.add_argument("--skill-name", required=True, help="Skill name for reporting")
    args = parser.parse_args()

    workspace = args.workspace
    skill_name = args.skill_name

    # Find all run directories
    runs = []
    for path in workspace.iterdir():
        if not path.is_dir():
            continue
        if path.name.startswith("eval-"):
            for config_dir in path.iterdir():
                if config_dir.is_dir() and config_dir.name in ["with_skill", "without_skill", "old_skill"]:
                    runs.append((path.name, config_dir.name))

    if not runs:
        print(f"No runs found in {workspace}")
        return 1

    # Collect data
    data = {}
    for eval_name, config in runs:
        run_dir = workspace / eval_name / config
        timing_path = run_dir / "timing.json"
        grading_path = run_dir / "grading.json"

        if not timing_path.exists():
            print(f"Missing timing.json for {eval_name}/{config}")
            continue

        with open(timing_path, "r") as f:
            timing = json.load(f)

        passes = None
        if grading_path.exists():
            with open(grading_path, "r") as f:
                grading = json.load(f)
            if "expectations" in grading:
                passes = sum(1 for e in grading["expectations"] if e.get("passed", False))
                total = len(grading["expectations"])
                passes = f"{passes}/{total}"

        data[(eval_name, config)] = {
            "time": timing.get("total_duration_seconds", 0),
            "tokens": timing.get("total_tokens", 0),
            "passes": passes
        }

    # Aggregate by config
    by_config = {}
    for (eval_name, config), metrics in data.items():
        if config not in by_config:
            by_config[config] = {
                "times": [],
                "tokens": [],
                "pass_rates": []
            }
        by_config[config]["times"].append(metrics["time"])
        by_config[config]["tokens"].append(metrics["tokens"])
        if metrics["passes"]:
            num, den = metrics["passes"].split("/")
            by_config[config]["pass_rates"].append(int(num) / int(den))

    # Generate summary
    summary = []
    for config, metrics in by_config.items():
        summary.append({
            "config": config,
            "mean_time": mean(metrics["times"]),
            "std_time": stdev(metrics["times"]) if len(metrics["times"]) > 1 else 0,
            "mean_tokens": mean(metrics["tokens"]),
            "std_tokens": stdev(metrics["tokens"]) if len(metrics["tokens"]) > 1 else 0,
            "mean_pass_rate": mean(metrics["pass_rates"]) if metrics["pass_rates"] else None,
            "std_pass_rate": stdev(metrics["pass_rates"]) if len(metrics["pass_rates"]) > 1 else None
        })

    # Write benchmark.json
    benchmark_json = {
        "skill_name": skill_name,
        "summary": summary,
        "raw_data": data
    }

    with open(workspace / "benchmark.json", "w") as f:
        json.dump(benchmark_json, f, indent=2)

    # Write benchmark.md
    with open(workspace / "benchmark.md", "w") as f:
        f.write(f"# Benchmark Results for {skill_name}\n\n")
        for item in summary:
            f.write(f"## {item['config']}\n")
            f.write(f"- Mean time: {item['mean_time']:.2f}s ± {item['std_time']:.2f}s\n")
            f.write(f"- Mean tokens: {item['mean_tokens']:.0f} ± {item['std_tokens']:.0f}\n")
            if item['mean_pass_rate'] is not None:
                f.write(f"- Mean pass rate: {item['mean_pass_rate']:.2f} ± {item['std_pass_rate']:.2f}\n")
            f.write("\n")

    print(f"Benchmark results written to {workspace / 'benchmark.json'} and {workspace / 'benchmark.md'}")
    return 0


if __name__ == "__main__":
    exit(main())
