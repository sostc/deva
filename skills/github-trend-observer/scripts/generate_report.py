"""
generate_report.py -- Fill Agent analysis JSON into HTML template and output the final report
Usage: python generate_report.py <analysis.json> [--mode radar-pulse] [--output path]

analysis.json structure (radar-pulse):
{
  "date": "2026-03-04",
  "total_scanned": 86,
  "picks_count": 12,
  "api_remaining": 5000, "api_limit": 5000, "api_mode": "full",
  "paradigm_signal": "HTML paragraphs...",
  "picks": [ { "full_name", "url", "layer", "layer_class", "description",
               "stars_fmt", "growth_30d_fmt", "growth_7d_fmt", "precision",
               "language", "created", "signals": [],
               "why", "paradigm", "suggestion" } ],
  "others": [ { "full_name", "url", "layer", "layer_class", "stars_fmt", "one_liner" } ],
  "filtered_groups": [ { "label", "count", "reason", "items" } ]
}

analysis.json structure (direction-search):
{
  "topic": "agent infra",
  "date": "2026-03-05",
  "meta": "63 recalled, 49 highly relevant, competitive landscape across 3 subcategories",
  "headline": "A paradigm-level judgment...",
  "legend_html": "<span>...</span>...",
  "keywords_count": 10,
  "keywords_html": "<code>kw1</code> <code>kw2</code>...",
  "picks": [ { "full_name", "url", "badge_html", "signals_html",
               "description", "metrics_html", "why", "paradigm" } ],
  "landscape_html": "Full competitive landscape HTML (with subcategory headers and tables)",
  "paradigm_content": "Paradigm analysis HTML (with <strong> and <br>)",
  "suggestions": [ { "name", "url", "suggestion" } ],
  "filtered_summary": "14",
  "filtered_html": "Filtered out items HTML",
  "footer_stats": "2026-03-05 · 63 repos scanned, 10 keywords..."
}
"""

import json
import sys
import os
import re
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)


def load_template(mode, lang="en"):
    path = os.path.join(PROJECT_DIR, lang, "templates", f"{mode}.html")
    if not os.path.exists(path):
        sys.stderr.write(f"  Template not found: {path}\n")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


LABEL_CN = {
    "sustained": "持续增长", "accelerating": "加速中",
    "spike": "爆发", "step": "阶梯式增长", "spike+decay": "冲高回落",
    "market-leader": "市场领先", "established": "成熟项目",
    "google-official": "Google 官方", "openai-official": "OpenAI 官方",
    "anthropic-official": "Anthropic 官方", "meta-official": "Meta 官方",
}


def preprocess_data(data, lang="en"):
    """Preprocess data: flatten nested list fields into _html strings to avoid template nesting"""
    for pick in data.get("picks", []):
        signals = pick.get("signals", [])
        if lang == "cn":
            signals = [LABEL_CN.get(s, s) for s in signals]
            if pick.get("pattern_label"):
                pick["pattern_label"] = LABEL_CN.get(pick["pattern_label"], pick["pattern_label"])
        pick["signals_html"] = "".join(
            f'<span class="signal-tag">{s}</span>' for s in signals
        )
    if lang == "cn":
        for detail in data.get("pick_details", []):
            if detail.get("pattern_label"):
                detail["pattern_label"] = LABEL_CN.get(detail["pattern_label"], detail["pattern_label"])
    return data


def render_simple(template, data):
    """Simple template rendering: {{key}} replacement + {{#each list}}...{{/each}} single-level loop"""

    def replace_each(match):
        key = match.group(1)
        block = match.group(2)
        items = data.get(key, [])
        parts = []
        for item in items:
            rendered = block
            if isinstance(item, dict):
                for k, v in item.items():
                    if isinstance(v, (str, int, float)):
                        rendered = rendered.replace("{{" + k + "}}", str(v))
            else:
                rendered = rendered.replace("{{this}}", str(item))
            parts.append(rendered)
        return "\n".join(parts)

    output = re.sub(
        r'{{#each (\w+)}}(.*?){{/each}}',
        replace_each,
        template,
        flags=re.DOTALL
    )

    # Replace top-level {{key}} variables
    for k, v in data.items():
        if isinstance(v, (str, int, float)):
            output = output.replace("{{" + k + "}}", str(v))

    return output


def strip_html(text):
    """Simple HTML tag removal for MD output"""
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', r'[\2](\1)', text)
    text = text.replace("<strong>", "**").replace("</strong>", "**")
    text = text.replace("<br>", "\n")
    return re.sub(r'<[^>]+>', '', text)


def generate_md_direction_search(data):
    """Generate Markdown report for Direction Search"""
    lines = []
    lines.append(f"# Direction Search: {data['topic']} -- {data['date']}")
    lines.append(f"> {data.get('meta', '')}")
    lines.append("")
    lines.append(f"**{data['headline']}**")
    lines.append("")
    lines.append("---")

    # Notable Picks
    lines.append("")
    lines.append("## Notable Picks")
    for p in data.get("picks", []):
        lines.append("")
        lines.append(f"### [{p['full_name']}]({p['url']})")
        lines.append(f"> {p['description']}")
        lines.append("")
        lines.append(strip_html(p.get('metrics_html', '')))
        lines.append("")
        lines.append(f"**Why it matters** -- {strip_html(p.get('why', ''))}")
        lines.append("")
        lines.append(f"**Paradigm signal** -- {strip_html(p.get('paradigm', ''))}")

    # Competitive Landscape
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Competitive Landscape")
    lines.append("")
    lines.append(strip_html(data.get('landscape_html', '')))

    # Paradigm Analysis
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Paradigm Analysis")
    lines.append("")
    lines.append(strip_html(data.get('paradigm_content', '')))

    # Suggested Deep Dives
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Suggested Deep Dives")
    lines.append("")
    lines.append("| Repo | Suggestion |")
    lines.append("|------|------|")
    for s in data.get("suggestions", []):
        lines.append(f"| [{s['name']}]({s['url']}) | {s['suggestion']} |")

    # Filtered Out
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## Filtered Out ({data.get('filtered_summary', '')})")
    lines.append("")
    lines.append(strip_html(data.get('filtered_html', '')))

    return "\n".join(lines)


def generate_md(data, mode):
    """Generate Markdown version of the report"""
    if mode == "direction-search":
        return generate_md_direction_search(data)
    if mode != "radar-pulse":
        sys.stderr.write(f"  MD generation only supports radar-pulse / direction-search, got: {mode}\n")
        return ""

    lines = []
    lines.append(f"# Radar Pulse -- {data['date']}")
    lines.append(f"> Filtered {data['picks_count']} notable picks from {data['total_scanned']} candidates")
    lines.append("")
    lines.append(f"**{data['headline']}**")
    lines.append("")
    lines.append("> L1 Model/Inference · L2 Agent Runtime · L3 Dev Framework/SDK · L4 Vertical Product · L5 Wrapper/Demo")
    lines.append("")
    lines.append("---")

    # Featured Picks
    lines.append("")
    lines.append("## Featured Picks")
    for p in data.get("picks", []):
        lines.append("")
        signals_str = " ".join(f"[{s}]" for s in p.get("signals", []))
        lines.append(f"### {p['full_name']} [{p['layer']}] {signals_str}")
        lines.append(f"> {p['description']}")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|------|------|")
        lines.append(f"| Stars | {p['stars_fmt']} [{p['precision']}] |")
        lines.append(f"| 30d Growth | {p['growth_30d_fmt']} [{p['precision']}] |")
        lines.append(f"| 7d Growth | {p['growth_7d_fmt']} [{p['precision']}] |")
        lines.append(f"| Language | {p['language']} |")
        lines.append(f"| Created | {p['created']} |")
        lines.append("")
        lines.append(f"**Why it matters**: {p['why']}")
        lines.append("")
        lines.append(f"**Paradigm signal**: {p['paradigm']}")

    lines.append("")
    lines.append("---")

    # Trend Narrative
    lines.append("")
    lines.append("## Trend Narrative")
    for t in data.get("trends", []):
        lines.append("")
        lines.append(f"### {t['title']}")
        lines.append("")
        lines.append(t['narrative'])
        repos_md = strip_html(t.get('repos_html', ''))
        if repos_md:
            lines.append(f"\n> {repos_md}")

    lines.append("")
    lines.append("---")

    # Also Worth Watching
    lines.append("")
    lines.append("## Also Worth Watching")
    lines.append("")
    lines.append("| Repo | Layer | Stars | Summary |")
    lines.append("|------|-------|-------|--------|")
    for o in data.get("scan_overview", []):
        lines.append(f"| [{o['full_name']}]({o['url']}) | {o['layer']} | {o['stars_fmt']} | {o['one_liner']} |")

    # Filtered Out
    lines.append("")
    lines.append("## Filtered Out")
    lines.append("")
    for fg in data.get("filtered_groups", []):
        lines.append(f"**{fg['label']} ({fg['count']})** -- {fg['reason']}")
        lines.append(f"- {fg['items']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="GitHub Radar Report Generator")
    parser.add_argument("analysis_json", help="Agent analysis result JSON file")
    parser.add_argument("--mode", "-m", default="radar-pulse", help="Report mode (default: radar-pulse)")
    parser.add_argument("--output", "-o", default=None, help="Output path prefix (without extension; generates both .html and .md)")
    parser.add_argument("--lang", "-l", default="en", choices=["en", "cn"], help="Language for templates (default: en)")
    args = parser.parse_args()

    with open(args.analysis_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Preprocess: flatten nested data
    data = preprocess_data(data, args.lang)

    # HTML
    template = load_template(args.mode, args.lang)
    html = render_simple(template, data)

    # MD
    md = generate_md(data, args.mode)

    # Output path
    if args.output:
        out_prefix = args.output
    else:
        out_dir = os.path.join(os.path.dirname(SCRIPT_DIR), "output")
        out_prefix = os.path.join(out_dir, f"{args.mode}_{data.get('date', 'unknown')}")

    html_path = out_prefix + ".html"
    md_path = out_prefix + ".md"

    os.makedirs(os.path.dirname(html_path), exist_ok=True)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    # Token statistics
    html_tokens = len(html) // 4  # Rough estimate: 1 token ~= 4 chars
    md_tokens = len(md) // 4

    result = {
        "html_path": html_path,
        "md_path": md_path,
        "html_chars": len(html),
        "md_chars": len(md),
        "html_tokens_est": html_tokens,
        "md_tokens_est": md_tokens,
        "savings_pct": round((1 - md_tokens / html_tokens) * 100, 1) if html_tokens > 0 else 0
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
