#!/usr/bin/env python3
"""
Naja API 客户端脚本

用于调用 naja 系统的各种 API 端点，方便用户获取系统数据和状态。
"""

import requests
import json
import argparse
import time

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


# ── 认知系统 ──

def get_cognition_memory():
    return call_api("/api/cognition/memory")

def get_cognition_topics(lookback=50):
    return call_api("/api/cognition/topics", params={"lookback": lookback})

def get_cognition_attention(lookback=200):
    return call_api("/api/cognition/attention", params={"lookback": lookback})

def get_cognition_thought():
    return call_api("/api/cognition/thought")

# ── 注意力系统 ──

def get_manas_state():
    return call_api("/api/attention/manas/state")

def get_harmony():
    return call_api("/api/attention/harmony")

def get_attention_context():
    return call_api("/api/attention/context")

def get_decision():
    return call_api("/api/attention/decision")

def get_conviction():
    return call_api("/api/attention/conviction")

def get_conviction_timing():
    return call_api("/api/attention/conviction/timing")

def get_portfolio_summary():
    return call_api("/api/attention/portfolio/summary")

def get_position_metrics():
    return call_api("/api/attention/position/metrics")

def get_tracking_stats():
    return call_api("/api/attention/tracking/stats")

def get_focus():
    return call_api("/api/attention/focus")

def get_fusion():
    return call_api("/api/attention/fusion")

def get_blind_spots():
    return call_api("/api/attention/blind-spots")

def get_liquidity():
    return call_api("/api/attention/liquidity")

def get_strategy_top_symbols():
    return call_api("/api/attention/strategy/top-symbols")

def get_strategy_top_blocks():
    return call_api("/api/attention/strategy/top-blocks")

# ── 知识库 ──

def get_knowledge_list(status=None, category=None, limit=20, offset=0):
    params = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    return call_api("/api/knowledge/list", params=params)

def get_knowledge_stats():
    return call_api("/api/knowledge/stats")

def get_knowledge_detail(entry_id):
    return call_api("/api/knowledge/detail", params={"id": entry_id})

def get_knowledge_trading():
    return call_api("/api/knowledge/trading")

# ── 市场 ──

def get_market_hotspot():
    return call_api("/api/market/hotspot")

# ── 系统 ──

def get_system_runtime():
    return call_api("/api/system/runtime")

def get_system_modules():
    return call_api("/api/system/modules")

# ── 其他 ──

def get_radar_events():
    return call_api("/api/radar/events")

def get_bandit_stats():
    return call_api("/api/bandit/stats")

def get_datasource_list():
    return call_api("/api/datasource/list")

def get_strategy_list():
    return call_api("/api/strategy/list")

def get_alaya_status():
    return call_api("/api/alaya/status")

# ── 新添加的数据结构 API ──

def get_registry_status():
    return call_api("/api/registry/status")

def get_query_state():
    return call_api("/api/query/state")

def get_system_persistent():
    return call_api("/api/system/persistent")

def get_event_query(event_type=None, symbol=None, direction=None, min_confidence=None, max_confidence=None, days=7, limit=100, offset=0):
    params = {"limit": limit, "offset": offset}
    if event_type:
        params["event_type"] = event_type
    if symbol:
        params["symbol"] = symbol
    if direction:
        params["direction"] = direction
    if min_confidence:
        params["min_confidence"] = min_confidence
    if max_confidence:
        params["max_confidence"] = max_confidence
    if days:
        # 计算时间戳
        import time
        end_time = time.time()
        start_time = end_time - days * 86400
        params["start_time"] = start_time
        params["end_time"] = end_time
    return call_api("/api/events/query", params=params)

def get_event_stats(event_type="StrategySignalEvent", days=30):
    return call_api("/api/events/stats", params={"event_type": event_type, "days": days})

def get_app_container():
    return call_api("/api/app/container")


# ── 命令映射 ──

COMMANDS = {
    # 认知
    "cognition-memory": (get_cognition_memory, "认知记忆报告"),
    "cognition-topics": (lambda: get_cognition_topics(50), "认知主题信号"),
    "cognition-attention": (lambda: get_cognition_attention(200), "认知注意力"),
    "cognition-thought": (get_cognition_thought, "思想雷达报告"),
    # 注意力
    "manas-state": (get_manas_state, "Manas 末那识状态"),
    "harmony": (get_harmony, "和谐度"),
    "attention-context": (get_attention_context, "注意力上下文"),
    "decision": (get_decision, "决策信号"),
    "conviction": (get_conviction, "信念验证"),
    "conviction-timing": (get_conviction_timing, "时机信号"),
    "portfolio-summary": (get_portfolio_summary, "持仓汇总"),
    "position-metrics": (get_position_metrics, "持仓指标"),
    "tracking-stats": (get_tracking_stats, "跟踪统计"),
    "focus": (get_focus, "关注焦点"),
    "fusion": (get_fusion, "融合信号"),
    "blind-spots": (get_blind_spots, "盲区发现"),
    "liquidity": (get_liquidity, "流动性"),
    "strategy-top-symbols": (get_strategy_top_symbols, "策略Top股票"),
    "strategy-top-blocks": (get_strategy_top_blocks, "策略Top题材"),
    # 知识库
    "knowledge-list": (get_knowledge_list, "知识列表"),
    "knowledge-stats": (get_knowledge_stats, "知识统计"),
    "knowledge-detail": (get_knowledge_detail, "知识详情"),
    "knowledge-trading": (get_knowledge_trading, "交易决策知识"),
    # 市场
    "market-hotspot": (get_market_hotspot, "市场热点"),
    # 系统
    "system-runtime": (get_system_runtime, "系统运行时监控"),
    "system-modules": (get_system_modules, "模块状态"),
    # 其他
    "radar-events": (get_radar_events, "雷达事件"),
    "bandit-stats": (get_bandit_stats, "Bandit 统计"),
    "datasource-list": (get_datasource_list, "数据源列表"),
    "strategy-list": (get_strategy_list, "策略列表"),
    "alaya-status": (get_alaya_status, "阿那亚状态"),
    # 新添加的数据结构 API
    "registry-status": (get_registry_status, "单例注册表状态"),
    "query-state": (get_query_state, "查询状态"),
    "system-persistent": (get_system_persistent, "系统持久化状态"),
    "event-query": (get_event_query, "事件查询"),
    "event-stats": (get_event_stats, "事件统计"),
    "app-container": (get_app_container, "应用容器状态"),
}


def main():
    global BASE_URL

    parser = argparse.ArgumentParser(
        description="Naja API 客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 api_client.py system-runtime
  python3 api_client.py knowledge-list --status qualified --limit 10
  python3 api_client.py knowledge-detail --id abc12345
  python3 api_client.py manas-state
  python3 api_client.py harmony
  python3 api_client.py cognition-memory
        """
    )
    parser.add_argument("command", choices=list(COMMANDS.keys()), help="API 命令")
    parser.add_argument("--status", help="知识状态筛选 (observing/validating/qualified/expired)")
    parser.add_argument("--category", help="知识分类筛选")
    parser.add_argument("--id", help="知识条目 ID")
    parser.add_argument("--limit", type=int, default=20, help="返回数量")
    parser.add_argument("--offset", type=int, default=0, help="偏移量")
    parser.add_argument("--lookback", type=int, help="回溯数量")
    parser.add_argument("--event-type", help="事件类型")
    parser.add_argument("--symbol", help="股票代码")
    parser.add_argument("--direction", choices=["buy", "sell"], help="方向")
    parser.add_argument("--min-confidence", type=float, help="最小置信度")
    parser.add_argument("--max-confidence", type=float, help="最大置信度")
    parser.add_argument("--days", type=int, default=7, help="天数")
    parser.add_argument("--base-url", default=BASE_URL, help="API 基础 URL")
    parser.add_argument("--output", choices=["json", "text"], default="json", help="输出格式")

    args = parser.parse_args()
    BASE_URL = args.base_url

    # 获取命令对应的函数
    func, desc = COMMANDS[args.command]

    # 特殊参数处理
    if args.command == "knowledge-list":
        result = get_knowledge_list(status=args.status, category=args.category, limit=args.limit, offset=args.offset)
    elif args.command == "knowledge-detail":
        if not args.id:
            print("错误: knowledge-detail 需要 --id 参数")
            return
        result = get_knowledge_detail(args.id)
    elif args.command == "cognition-topics" and args.lookback:
        result = get_cognition_topics(args.lookback)
    elif args.command == "cognition-attention" and args.lookback:
        result = get_cognition_attention(args.lookback)
    elif args.command == "event-query":
        result = get_event_query(
            event_type=args.event_type,
            symbol=args.symbol,
            direction=args.direction,
            min_confidence=args.min_confidence,
            max_confidence=args.max_confidence,
            days=args.days,
            limit=args.limit,
            offset=args.offset
        )
    elif args.command == "event-stats":
        result = get_event_stats(
            event_type=args.event_type or "StrategySignalEvent",
            days=args.days
        )
    else:
        result = func()

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("success"):
            print(f"✓ {desc} - 调用成功")
            print(f"时间: {result.get('datetime')}")
            if "data" in result:
                data = result["data"]
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, (dict, list)):
                            print(f"{key}: {json.dumps(value, ensure_ascii=False)[:150]}")
                        else:
                            print(f"{key}: {value}")
                elif isinstance(data, list):
                    print(f"共 {len(data)} 条")
                    for item in data[:5]:
                        if isinstance(item, dict):
                            print(f"  - {item.get('cause', item.get('name', item.get('symbol', str(item))))[:60]}")
                        else:
                            print(f"  - {str(item)[:60]}")
        else:
            print(f"✗ {desc} - 调用失败: {result.get('error')}")


if __name__ == "__main__":
    main()
