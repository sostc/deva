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
    """调用 API 端点
    
    Args:
        endpoint: API 端点路径
        params: 请求参数
        
    Returns:
        响应数据
    """
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


def get_cognition_memory():
    """获取认知系统记忆报告"""
    return call_api("/api/cognition/memory")


def get_cognition_topics(lookback=50):
    """获取认知系统主题信号"""
    return call_api("/api/cognition/topics", params={"lookback": lookback})


def get_cognition_attention(lookback=200):
    """获取认知系统注意力提示"""
    return call_api("/api/cognition/attention", params={"lookback": lookback})


def get_cognition_thought():
    """获取认知系统思想报告"""
    return call_api("/api/cognition/thought")


def get_market_state():
    """获取市场状态"""
    return call_api("/api/market/state")


def get_market_hotspot_details():
    """获取市场热点详情"""
    return call_api("/api/market/hotspot/details")


def get_system_status():
    """获取系统状态"""
    return call_api("/api/system/status")


def get_system_modules():
    """获取系统模块状态"""
    return call_api("/api/system/modules")


def get_radar_events():
    """获取雷达事件"""
    return call_api("/api/radar/events")


def get_bandit_stats():
    """获取 Bandit 决策统计"""
    return call_api("/api/bandit/stats")


def get_datasource_list():
    """获取数据源列表"""
    return call_api("/api/datasource/list")


def get_strategy_list():
    """获取策略列表"""
    return call_api("/api/strategy/list")


def get_alaya_status():
    """获取阿那亚觉醒状态"""
    return call_api("/api/alaya/status")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Naja API 客户端")
    parser.add_argument("command", choices=[
        "cognition-memory", "cognition-topics", "cognition-attention", "cognition-thought",
        "market-state", "market-hotspot",
        "system-status", "system-modules",
        "radar-events",
        "bandit-stats",
        "datasource-list", "strategy-list",
        "alaya-status"
    ], help="API 命令")
    parser.add_argument("--lookback", type=int, help="回溯数量")
    parser.add_argument("--base-url", default=BASE_URL, help="API 基础 URL")
    parser.add_argument("--output", choices=["json", "text"], default="json", help="输出格式")
    
    args = parser.parse_args()
    
    global BASE_URL
    BASE_URL = args.base_url
    
    result = None
    
    if args.command == "cognition-memory":
        result = get_cognition_memory()
    elif args.command == "cognition-topics":
        lookback = args.lookback or 50
        result = get_cognition_topics(lookback)
    elif args.command == "cognition-attention":
        lookback = args.lookback or 200
        result = get_cognition_attention(lookback)
    elif args.command == "cognition-thought":
        result = get_cognition_thought()
    elif args.command == "market-state":
        result = get_market_state()
    elif args.command == "market-hotspot":
        result = get_market_hotspot_details()
    elif args.command == "system-status":
        result = get_system_status()
    elif args.command == "system-modules":
        result = get_system_modules()
    elif args.command == "radar-events":
        result = get_radar_events()
    elif args.command == "bandit-stats":
        result = get_bandit_stats()
    elif args.command == "datasource-list":
        result = get_datasource_list()
    elif args.command == "strategy-list":
        result = get_strategy_list()
    elif args.command == "alaya-status":
        result = get_alaya_status()
    
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("success"):
            print(f"✓ 调用成功")
            print(f"时间: {result.get('datetime')}")
            if "data" in result:
                data = result["data"]
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, (dict, list)):
                            print(f"{key}: {json.dumps(value, ensure_ascii=False)[:100]}...")
                        else:
                            print(f"{key}: {value}")
        else:
            print(f"✗ 调用失败: {result.get('error')}")


if __name__ == "__main__":
    main()
