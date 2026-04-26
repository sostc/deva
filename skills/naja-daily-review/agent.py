"""
Naja Daily Review Agent

汇总 Naja 系统核心数据，生成结构化复盘报告并通过 iMessage 发送。
"""

import subprocess
from datetime import datetime


def send_imessage(phone: str, text: str) -> bool:
    """发送 iMessage"""
    try:
        escaped_text = text.replace('"', '\\"')
        cmd = [
            'osascript', '-e',
            f'''tell application "Messages"
                send "{escaped_text}" to buddy "{phone}"
            end tell'''
        ]
        subprocess.run(cmd, capture_output=True, timeout=15)
        return True
    except Exception as e:
        print(f"iMessage 发送失败: {e}")
        return False


def fetch_api(endpoint: str) -> dict:
    """获取 API 数据"""
    import requests
    try:
        resp = requests.get(f"http://localhost:8080{endpoint}", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"API 调用失败 {endpoint}: {e}")
    return {}


def format_hotspot_blocks(blocks: list) -> str:
    """格式化热点题材"""
    lines = []
    for b in blocks[:8]:
        if isinstance(b, dict) and b.get('weight', 0) > 0:
            lines.append(f"• {b['name']} {b['weight']:.2f}")
    return lines


def format_hotspot_stocks(stocks: list) -> str:
    """格式化热点股票"""
    lines = []
    for s in stocks[:5]:
        if isinstance(s, dict):
            name = s.get('name', s.get('symbol', ''))
            change = s.get('change_pct', 0)
            change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
            lines.append(f"• {name} ({change_str})")
    return lines


def generate_daily_review() -> str:
    """生成每日复盘报告"""
    today = datetime.now().strftime('%Y-%m-%d')

    memory = fetch_api("/api/cognition/memory")
    hotspot = fetch_api("/api/market/hotspot")
    harmony = fetch_api("/api/attention/harmony")
    manas = fetch_api("/api/attention/manas/state")
    bandit = fetch_api("/api/bandit/stats")
    knowledge = fetch_api("/api/knowledge/stats")

    narratives = []
    if memory.get('success') and memory.get('data', {}).get('narratives', {}).get('summary'):
        narratives = memory['data']['narratives']['summary'][:5]

    msg_parts = [f"📊 Naja 每日复盘 - {today}"]
    msg_parts.append("\n━━━━━━━━━━━━━━━━━━━━")
    msg_parts.append("📈 市场行情")
    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")

    if hotspot.get('success'):
        us_blocks = hotspot.get('data', {}).get('us', {}).get('hot_blocks', [])
        cn_blocks = hotspot.get('data', {}).get('cn', {}).get('hot_blocks', [])

        if us_blocks:
            us_formatted = format_hotspot_blocks(us_blocks)
            if us_formatted:
                msg_parts.append("【美股热门题材】")
                msg_parts.extend(us_formatted)
                msg_parts.append("")

        us_stocks = hotspot.get('data', {}).get('us', {}).get('hot_stocks', [])
        if us_stocks:
            stocks_formatted = format_hotspot_stocks(us_stocks)
            if stocks_formatted:
                msg_parts.append("【美股热门股票】")
                msg_parts.extend(stocks_formatted)
                msg_parts.append("")

        cn_blocks_active = [b for b in cn_blocks if isinstance(b, dict) and b.get('weight', 0) > 0]
        if cn_blocks_active:
            msg_parts.append("【A股热门题材】")
            msg_parts.extend(format_hotspot_blocks(cn_blocks_active))
            msg_parts.append("")

    msg_parts.append("🎯 Top5 叙事信号")
    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")

    if narratives:
        emoji_list = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i, n in enumerate(narratives):
            narrative = n.get('narrative', '未知')
            score = n.get('attention_score', 0)
            trend = n.get('trend', 0)
            trend_str = "↑" if trend > 0 else "↓" if trend < 0 else "→"
            stage = n.get('stage', '')

            msg_parts.append(f"{emoji_list[i]} {narrative} | {score:.3f} | {trend_str} | {stage}")

            keywords = n.get('keywords', [])
            if keywords:
                kw_str = " / ".join(keywords[:3])
                msg_parts.append(f"   关键词: {kw_str}")
    else:
        msg_parts.append("暂无叙事数据")

    msg_parts.append("")
    msg_parts.append("💼 持仓与系统")
    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")

    if harmony.get('success'):
        h_data = harmony.get('data', {})
        strength = h_data.get('harmony_strength', 0)
        state = h_data.get('harmony_state', 'unknown')
        should_act = h_data.get('should_act', False)
        msg_parts.append(f"• 和谐度: {strength:.3f} ({state})")
        msg_parts.append(f"• 行动信号: {'是' if should_act else '否'}")
    else:
        msg_parts.append("• 和谐度: 无数据")

    if bandit.get('success'):
        b_data = bandit.get('data', {})
        running = b_data.get('running', False)
        phase = b_data.get('current_phase', 'unknown')
        msg_parts.append(f"• Bandit: {'running' if running else 'stopped'}, phase={phase}")
    else:
        msg_parts.append("• Bandit: 无数据")

    msg_parts.append("")
    msg_parts.append("🧠 注意力系统")
    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")

    if manas.get('success'):
        m_data = manas.get('data', {})
        enabled = m_data.get('enabled', False)
        last_output = m_data.get('last_output')
        msg_parts.append(f"• Manas: {'enabled' if enabled else 'disabled'}")
        if last_output:
            action = last_output.get('action_type', 'none') if isinstance(last_output, dict) else 'none'
            msg_parts.append(f"• 当前动作: {action}")
    else:
        msg_parts.append("• Manas: 无数据")

    msg_parts.append("")
    msg_parts.append("📚 知识库")
    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")

    if knowledge.get('success'):
        k_data = knowledge.get('data', {})
        total = k_data.get('total', 0)
        by_state = k_data.get('by_state', {})
        qualified = by_state.get('qualified', 0)
        validating = by_state.get('validating', 0)
        observing = by_state.get('observing', 0)
        msg_parts.append(f"• 总知识: {total}条")
        msg_parts.append(f"• qualified: {qualified} | validating: {validating} | observing: {observing}")
    else:
        msg_parts.append("• 知识库: 无数据")

    msg_parts.append("")
    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")
    msg_parts.append("Generated by Naja Daily Review")

    return "\n".join(msg_parts)


def run():
    """执行复盘"""
    report = generate_daily_review()
    print(report)

    phone = "+8618626880688"
    if send_imessage(phone, report):
        print("\n✅ 复盘报告已发送到 iMessage")
    else:
        print("\n❌ iMessage 发送失败")


if __name__ == "__main__":
    run()