#!/usr/bin/env python3
"""
Naja 最新状态查看器

用于快速查看 naja 系统的最新认识和状态，以友好的格式展示。
"""

import requests
import json
import time
import argparse
from datetime import datetime

BASE_URL = "http://localhost:8080"


def call_api(endpoint, params=None):
    """调用 API 端点"""
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": False,
            "error": str(e)
        }


def print_section(title):
    """打印分区标题"""
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def print_subsection(title):
    """打印子分区标题"""
    print(f"\n  ─── {title} ─────────────────────────────────────────")


def print_item(index, title, content=None, max_length=80):
    """打印项目"""
    if content:
        # 截断长文本
        if len(str(content)) > max_length:
            content = str(content)[:max_length] + "..."
        print(f"  {index:2d}. {title}: {content}")
    else:
        print(f"  {index:2d}. {title}")


def display_latest_insights():
    """显示最新认识"""
    print_section("🌐 NAJA 最新状态")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 获取最新认识
    result = call_api("/api/cognition/latest_insights", {
        "limit": 5,
        "lookback": 200,
        "news_limit": 10,
        "narrative_limit": 5
    })

    if not result.get("success"):
        print(f"\n  ❌ 获取失败: {result.get('error')}")
        return

    data = result.get("data", {})

    # 显示洞察
    if data.get("top_insights"):
        print_subsection("📊 TOP 洞察")
        for i, insight in enumerate(data["top_insights"], 1):
            score = insight.get("score", 0)
            content = insight.get("content", "")
            print_item(i, f"评分 {score:.2f}", content, max_length=100)

    if data.get("recent_insights"):
        print_subsection("🆕 最近洞察")
        for i, insight in enumerate(data["recent_insights"], 1):
            content = insight.get("content", "")
            print_item(i, "洞察", content, max_length=100)

    # 显示新闻事件
    if data.get("hot_events"):
        print_subsection("🔥 高分新闻事件")
        for i, event in enumerate(data["hot_events"], 1):
            score = event.get("score", 0)
            msg = event.get("message", "")
            strategy = event.get("strategy_name", "")
            print_item(i, f"{strategy} (评分 {score:.2f})", msg, max_length=100)

    if data.get("recent_events"):
        print_subsection("📰 最近事件")
        for i, event in enumerate(data["recent_events"][:5], 1):
            msg = event.get("message", "")
            strategy = event.get("strategy_name", "")
            print_item(i, strategy, msg, max_length=100)

    # 显示叙事
    if data.get("active_narratives"):
        print_subsection("📖 活跃叙事")
        for i, narrative in enumerate(data["active_narratives"], 1):
            name = narrative.get("name", "")
            phase = narrative.get("phase", "")
            attention = narrative.get("attention_score", 0)
            summary = narrative.get("summary", "")
            print_item(i, f"{name} ({phase}) - 注意力 {attention:.2f}", summary, max_length=100)

    if data.get("world_narrative"):
        print_subsection("🌍 世界叙事")
        world_nar = data["world_narrative"]
        if isinstance(world_nar, dict):
            for key, value in world_nar.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {world_nar}")

    if data.get("narrative_blocks"):
        print_subsection("📦 叙事与板块")
        for i, block in enumerate(data["narrative_blocks"], 1):
            print_item(i, "板块", str(block), max_length=100)

    if data.get("narrative_summary"):
        print_subsection("📝 叙事摘要")
        summary = data["narrative_summary"]
        if isinstance(summary, dict):
            for key, value in summary.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {summary}")

    if data.get("tiandao_minxin"):
        print_subsection("⚖️ 天道民心")
        tm = data["tiandao_minxin"]
        if isinstance(tm, dict):
            for key, value in tm.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {tm}")

    # 显示知识库
    if data.get("latest_knowledge"):
        print_subsection("📚 最新知识")
        for i, knowledge in enumerate(data["latest_knowledge"], 1):
            cause = knowledge.get("cause", "")
            effect = knowledge.get("effect", "")
            confidence = knowledge.get("confidence", 0)
            status = knowledge.get("status", "")
            print_item(i, f"{cause} → {effect} (置信度 {confidence:.2f}, {status})", "", max_length=100)

    if data.get("knowledge_stats"):
        print_subsection("📊 知识库统计")
        stats = data["knowledge_stats"]
        if isinstance(stats, dict):
            for key, value in stats.items():
                print(f"  {key}: {value}")

    # 显示注意力
    if data.get("attention_hints"):
        print_subsection("👁️ 注意力提示")
        hints = data["attention_hints"]
        if isinstance(hints, dict):
            for key, value in hints.items():
                if isinstance(value, list):
                    print(f"  {key}: {', '.join(str(x) for x in value[:5])}")
                else:
                    print(f"  {key}: {value}")

    if data.get("memory_report"):
        print_subsection("🧠 记忆报告")
        report = data["memory_report"]
        if isinstance(report, dict):
            for key, value in report.items():
                print(f"  {key}: {value}")


def main():
    global BASE_URL

    parser = argparse.ArgumentParser(
        description="Naja 最新状态查看器",
        epilog="""
示例:
  python3 get_naja_status.py
  python3 get_naja_status.py --base-url http://192.168.1.100:8080
        """
    )
    parser.add_argument("--base-url", default=BASE_URL, help="API 基础 URL")

    args = parser.parse_args()
    BASE_URL = args.base_url

    display_latest_insights()


if __name__ == "__main__":
    main()
