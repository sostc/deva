"""
生成模拟回放测试数据

Usage:
    python -m deva.naja.scripts.generate_test_replay_data
"""

import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from deva import NB


def generate_market_snapshot(timestamp: datetime, base_price: float = 100.0) -> Dict[str, Any]:
    """生成单个市场快照数据"""
    change_pct = random.uniform(-0.03, 0.05)
    volume = random.randint(1000000, 10000000)

    symbols = {
        "NVDA": {"price": base_price * random.uniform(0.9, 1.3), "change": change_pct + 0.02},
        "AAPL": {"price": base_price * random.uniform(0.95, 1.1), "change": change_pct - 0.01},
        "TSLA": {"price": base_price * random.uniform(0.8, 1.4), "change": change_pct + random.uniform(-0.02, 0.03)},
        "MSFT": {"price": base_price * random.uniform(0.9, 1.15), "change": change_pct + 0.01},
        "AMD": {"price": base_price * random.uniform(0.85, 1.25), "change": change_pct + random.uniform(-0.01, 0.04)},
    }

    return {
        "timestamp": timestamp.isoformat(),
        "market": {
            "change": change_pct,
            "volume": volume,
            "advance_ratio": random.uniform(0.3, 0.7),
            "limit_up_count": random.randint(10, 50),
            "limit_down_count": random.randint(5, 30),
        },
        "symbols": symbols,
        "indices": {
            "SPX": {"change": change_pct * random.uniform(0.8, 1.2)},
            "NDX": {"change": (change_pct + 0.01) * random.uniform(0.8, 1.2)},
            "DJI": {"change": (change_pct - 0.005) * random.uniform(0.8, 1.2)},
        },
    }


def generate_narrative_event(timestamp: datetime, event_type: str) -> Dict[str, Any]:
    """生成叙事/新闻事件"""
    events = {
        "token_shortage": {
            "type": "token供需",
            "content": "英伟达H100交付延迟，AI算力供给不足",
            "keywords": ["GPU", "算力", "交付延迟", "产能不足"],
            "severity": "high",
            "affected_sectors": ["AI芯片", "半导体设备", "封装测试"],
        },
        "power_shortage": {
            "type": "电力供需",
            "content": "数据中心用电激增，多地电网超载",
            "keywords": ["电力", "数据中心", "用电激增", "电网"],
            "severity": "medium",
            "affected_sectors": ["电力设备", "绿色能源", "储能"],
        },
        "chip_ban": {
            "type": "芯片供给不足",
            "content": "美国扩大芯片出口限制，EUV设备禁运",
            "keywords": ["芯片", "制裁", "EUV", "出口限制"],
            "severity": "high",
            "affected_sectors": ["半导体设备", "国产替代", "成熟制程"],
        },
        "ai_demand_surge": {
            "type": "token需求爆发",
            "content": "ChatGPT用户激增，API调用量暴涨300%",
            "keywords": ["ChatGPT", "API", "用户激增", "算力需求"],
            "severity": "high",
            "affected_sectors": ["AI应用", "云服务", "算力基础设施"],
        },
        "breakthrough": {
            "type": "技术瓶颈突破",
            "content": "国产7nm芯片量产成功，良率达标",
            "keywords": ["国产", "7nm", "量产", "良率"],
            "severity": "medium",
            "affected_sectors": ["半导体制造", "芯片设计", "设备材料"],
        },
        "fed_rate": {
            "type": "美联储",
            "content": "美联储维持利率不变，鲍威尔暗示降息延后",
            "keywords": ["美联储", "利率", "降息", "鲍威尔"],
            "severity": "high",
            "affected_sectors": ["全局"],
        },
    }

    base_event = events.get(event_type, events["token_shortage"])
    return {
        "timestamp": timestamp.isoformat(),
        **base_event,
        "confidence": random.uniform(0.6, 0.95),
    }


def generate_ai_compute_trend(timestamp: datetime, trend: str = "rising") -> Dict[str, Any]:
    """生成 AI 算力趋势数据"""
    trends = {
        "rising": {
            "trend_direction": "rising",
            "message": "AI算力需求持续上涨，本周增长23%",
            "base_strength": 0.7,
            "cumulative_growth": 1.85,
            "alert_level": "normal",
        },
        "falling": {
            "trend_direction": "falling",
            "message": "AI算力需求放缓，本周下降15%",
            "base_strength": 0.5,
            "cumulative_growth": 0.65,
            "alert_level": "normal",
        },
        "stable": {
            "trend_direction": "stable",
            "message": "AI算力需求平稳",
            "base_strength": 0.3,
            "cumulative_growth": 1.05,
            "alert_level": "normal",
        },
    }

    return {
        "timestamp": timestamp.isoformat(),
        **trends.get(trend, trends["stable"]),
    }


def generate_test_data(
    num_snapshots: int = 200,
    start_time: datetime = None,
    interval_minutes: int = 5,
    db_path: str = "/Users/spark/.deva/nb.sqlite"
):
    """
    生成测试数据

    Args:
        num_snapshots: 生成多少个行情快照
        start_time: 开始时间（默认：当前时间往前推）
        interval_minutes: 快照间隔（分钟）
        db_path: NB 数据库路径
    """
    if start_time is None:
        start_time = datetime.now() - timedelta(days=7)

    print(f"生成 {num_snapshots} 条测试数据...")
    print(f"时间范围: {start_time} ~ {start_time + timedelta(minutes=num_snapshots * interval_minutes)}")

    nb = NB("quant_snapshot_5min_window", key_mode='time', db_path=db_path)

    narrative_events = [
        "token_shortage",
        "power_shortage",
        "chip_ban",
        "ai_demand_surge",
        "breakthrough",
        "fed_rate",
    ]

    ai_trends = ["rising", "stable", "rising", "rising", "stable", "falling"]

    current_price = 100.0
    for i in range(num_snapshots):
        timestamp = start_time + timedelta(minutes=i * interval_minutes)
        key = timestamp.timestamp()

        current_price *= random.uniform(0.995, 1.01)

        snapshot = generate_market_snapshot(timestamp, current_price)
        nb.set(key, snapshot)

        if i % 30 == 0:
            event_type = random.choice(narrative_events)
            event = generate_narrative_event(timestamp, event_type)
            nb.set(timestamp.timestamp(), event)

        if i % 20 == 0:
            trend = random.choice(ai_trends)
            ai_compute = generate_ai_compute_trend(timestamp, trend)
            nb.set(timestamp.timestamp() + 0.5, ai_compute)

        if (i + 1) % 50 == 0:
            print(f"  已生成 {i + 1}/{num_snapshots} 条数据...")

    print(f"\n✅ 数据生成完成！")
    print(f"  - 行情快照: {num_snapshots} 条")
    print(f"  - 叙事事件: {num_snapshots // 30 + 1} 条")
    print(f"  - AI算力趋势: {num_snapshots // 20 + 1} 条")

    print(f"\n启动命令:")
    print(f"  python -m deva.naja --lab --lab-table quant_snapshot_5min_window --lab-speed 3.0")


if __name__ == "__main__":
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    num = int(os.environ.get("NUM_SNAPSHOTS", "200"))
    generate_test_data(num_snapshots=num)
