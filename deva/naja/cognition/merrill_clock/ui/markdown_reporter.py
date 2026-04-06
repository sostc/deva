"""
美林时钟 UI 组件

提供美林时钟周期状态的可视化展示
"""

import logging
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def get_merrill_clock_display() -> Dict[str, Any]:
    """
    获取美林时钟展示数据
    
    Returns:
        包含周期状态、资产配置、图表数据的字典
    """
    try:
        from ...merrill_clock import get_engine as get_merrill_clock_engine
        
        clock_engine = get_merrill_clock_engine()
        signal = clock_engine.get_current_signal()
        
        if not signal:
            return {
                "status": "no_data",
                "message": "暂无经济数据，请运行定时任务获取数据",
            }
        
        # 周期阶段对应的颜色和图标
        phase_config = {
            "复苏": {
                "color": "#4ade80",  # 绿色
                "icon": "🌱",
                "description": "经济复苏，企业盈利改善",
                "best_asset": "股票",
            },
            "过热": {
                "color": "#f97316",  # 橙色
                "icon": "🔥",
                "description": "经济过热，通胀上升",
                "best_asset": "商品",
            },
            "滞胀": {
                "color": "#ef4444",  # 红色
                "icon": "⚠️",
                "description": "滞胀环境，现金为王",
                "best_asset": "现金",
            },
            "衰退": {
                "color": "#60a5fa",  # 蓝色
                "icon": "❄️",
                "description": "经济衰退，债券最佳",
                "best_asset": "债券",
            },
        }
        
        phase_info = phase_config.get(signal.phase.value, {})
        
        # 资产偏好可视化
        asset_emoji = {
            "股票": "📈",
            "债券": "📊",
            "商品": "🛢️",
            "现金": "💵",
        }
        
        asset_ranking_display = []
        for i, asset in enumerate(signal.asset_ranking):
            emoji = asset_emoji.get(asset, "•")
            rank = "★★★★★" if i == 0 else ("★★★★☆" if i == 1 else ("★★★☆☆" if i == 2 else "★★☆☆☆"))
            asset_ranking_display.append(f"{emoji} {asset}: {rank}")
        
        # 增长和通胀指标可视化
        growth_indicator = "↑" if signal.growth_score > 0 else ("↓" if signal.growth_score < 0 else "→")
        inflation_indicator = "↑" if signal.inflation_score > 0 else ("↓" if signal.inflation_score < 0 else "→")
        
        # 历史趋势
        history = clock_engine.get_history(limit=10)
        history_data = []
        for h in history:
            history_data.append({
                "timestamp": h.timestamp,
                "phase": h.phase.value,
                "confidence": round(h.confidence, 3),
            })
        
        return {
            "status": "active",
            "phase": {
                "name": signal.phase.value,
                "icon": phase_info.get("icon", "•"),
                "color": phase_info.get("color", "#999999"),
                "description": phase_info.get("description", ""),
                "best_asset": phase_info.get("best_asset", ""),
            },
            "confidence": {
                "value": round(signal.confidence, 3),
                "level": "高" if signal.confidence > 0.7 else ("中" if signal.confidence > 0.5 else "低"),
            },
            "scores": {
                "growth": {
                    "value": round(signal.growth_score, 3),
                    "indicator": growth_indicator,
                    "level": "强" if signal.growth_score > 0.3 else ("弱" if signal.growth_score < -0.3 else "中"),
                },
                "inflation": {
                    "value": round(signal.inflation_score, 3),
                    "indicator": inflation_indicator,
                    "level": "高" if signal.inflation_score > 0.3 else ("低" if signal.inflation_score < -0.3 else "中"),
                },
            },
            "asset_allocation": {
                "ranking": signal.asset_ranking,
                "ranking_display": asset_ranking_display,
                "overweight": signal.overweight,
                "underweight": signal.underweight,
                "reason": signal.reason,
            },
            "data_summary": signal.data_summary,
            "history": history_data,
            "last_update": signal.timestamp,
            "next_update": "下一个交易日",
        }
        
    except Exception as e:
        log.error(f"[MerrillClockUI] 获取展示数据失败：{e}")
        return {
            "status": "error",
            "message": str(e),
        }


def get_merrill_clock_markdown() -> str:
    """
    获取 Markdown 格式的美林时钟报告
    
    Returns:
        Markdown 字符串
    """
    data = get_merrill_clock_display()
    
    if data.get("status") != "active":
        return "## 🕰️ 美林时钟\n\n暂无数据"
    
    phase = data["phase"]
    confidence = data["confidence"]
    scores = data["scores"]
    allocation = data["asset_allocation"]
    
    lines = [
        "## 🕰️ 美林时钟",
        "",
        f"### {phase['icon']} 当前阶段：{phase['name']}",
        "",
        f"**置信度**: {confidence['value']:.0%} ({confidence['level']})",
        "",
        f"**经济状态**: {phase['description']}",
        "",
        f"**最佳资产**: {allocation['ranking'][0] if allocation['ranking'] else 'N/A'}",
        "",
        "---",
        "",
        "### 📊 经济指标",
        "",
        f"| 维度 | 评分 | 方向 | 状态 |",
        f"|------|------|------|------|",
        f"| 增长 | {scores['growth']['value']:+.2f} | {scores['growth']['indicator']} | {scores['growth']['level']} |",
        f"| 通胀 | {scores['inflation']['value']:+.2f} | {scores['inflation']['indicator']} | {scores['inflation']['level']} |",
        "",
        "---",
        "",
        "### 💼 资产配置建议",
        "",
        "**偏好排序**:",
    ]
    
    for item in allocation["ranking_display"]:
        lines.append(f"- {item}")
    
    lines.append("")
    lines.append("**超配建议**:")
    for item in allocation["overweight"]:
        lines.append(f"- ✅ {item}")
    
    lines.append("")
    lines.append("**低配建议**:")
    for item in allocation["underweight"]:
        lines.append(f"- ❌ {item}")
    
    lines.append("")
    lines.append(f"**理由**: {allocation['reason']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 历史趋势
    history = data.get("history", [])
    if history:
        lines.append("### 📈 历史趋势")
        lines.append("")
        lines.append("| 时间 | 周期阶段 | 置信度 |")
        lines.append("|------|---------|--------|")
        for h in history[-5:]:  # 最近 5 次
            ts = time.strftime("%Y-%m-%d", time.localtime(h["timestamp"]))
            lines.append(f"| {ts} | {h['phase']} | {h['confidence']:.0%} |")
        lines.append("")
    
    return "\n".join(lines)


# ========== 测试 ==========

if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("美林时钟 UI 组件测试")
    print("=" * 60)
    
    # 获取展示数据
    data = get_merrill_clock_display()
    
    print(f"\n状态：{data.get('status')}")
    if data.get("status") == "active":
        print(f"周期阶段：{data['phase']['icon']} {data['phase']['name']}")
        print(f"置信度：{data['confidence']['value']:.0%} ({data['confidence']['level']})")
        print(f"最佳资产：{data['phase']['best_asset']}")
        print(f"\n资产配置排序：{data['asset_allocation']['ranking']}")
    
    print(f"\n" + "=" * 60)
    print("\nMarkdown 报告:\n")
    print(get_merrill_clock_markdown())
    print("=" * 60)
