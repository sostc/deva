"""
生成模拟回放测试数据（独立版本）

AI/算力/芯片/Token 相关主题股票池

Usage:
    python3 generate_test_replay_data.py
"""

import random
import sqlite3
import pickle
import time
from datetime import datetime, timedelta
from typing import Any, Dict

AI_STOCK_POOL = {
    "NVDA": {"name": "英伟达", "base_price": 800.0, "block": "AI芯片"},
    "AMD": {"name": "超微半导体", "base_price": 150.0, "block": "AI芯片"},
    "INTC": {"name": "英特尔", "base_price": 45.0, "block": "AI芯片"},
    "QCOM": {"name": "高通", "base_price": 180.0, "block": "AI芯片"},
    "AVGO": {"name": "博通", "base_price": 1200.0, "block": "AI芯片"},
    "TSLA": {"name": "特斯拉", "base_price": 250.0, "block": "AI应用"},
    "MSFT": {"name": "微软", "base_price": 400.0, "block": "AI应用"},
    "GOOGL": {"name": "谷歌", "base_price": 170.0, "block": "AI应用"},
    "META": {"name": "Meta", "base_price": 500.0, "block": "AI应用"},
    "AMZN": {"name": "亚马逊", "base_price": 180.0, "block": "AI应用"},
    "688041": {"name": "海光信息", "base_price": 80.0, "block": "AI芯片"},
    "688256": {"name": "寒武纪", "base_price": 200.0, "block": "AI芯片"},
    "002371": {"name": "北方华创", "base_price": 350.0, "block": "半导体设备"},
    "600745": {"name": "闻泰科技", "base_price": 60.0, "block": "半导体"},
    "002185": {"name": "华天科技", "base_price": 15.0, "block": "封装测试"},
    "600584": {"name": "长电科技", "base_price": 30.0, "block": "封装测试"},
    "688012": {"name": "中微公司", "base_price": 150.0, "block": "半导体设备"},
    "688008": {"name": "澜起科技", "base_price": 70.0, "block": "芯片设计"},
    "603501": {"name": "韦尔股份", "base_price": 100.0, "block": "芯片设计"},
    "002230": {"name": "科大讯飞", "base_price": 50.0, "block": "AI应用"},
    "603019": {"name": "中科曙光", "base_price": 45.0, "block": "HPC算力"},
    "000977": {"name": "浪潮信息", "base_price": 35.0, "block": "服务器"},
}


def generate_market_snapshot(timestamp: datetime, price_bases: Dict = None) -> Dict[str, Any]:
    """生成单个市场快照数据"""
    if price_bases is None:
        price_bases = {code: info["base_price"] for code, info in AI_STOCK_POOL.items()}

    market_change = random.uniform(-0.03, 0.05)
    volume = random.randint(1000000, 10000000)

    symbols = {}
    for code, base_price in price_bases.items():
        block = AI_STOCK_POOL[code]["block"]
        block_bias = {
            "AI芯片": random.uniform(-0.02, 0.04),
            "AI应用": random.uniform(-0.015, 0.035),
            "半导体设备": random.uniform(-0.025, 0.03),
            "封装测试": random.uniform(-0.02, 0.025),
            "芯片设计": random.uniform(-0.018, 0.032),
            "HPC算力": random.uniform(-0.02, 0.04),
            "服务器": random.uniform(-0.015, 0.03),
        }.get(block, 0)

        change_pct = market_change + block_bias
        price = base_price * (1 + change_pct)
        symbols[code] = {
            "price": round(price, 2),
            "change": round(change_pct, 4),
            "block": block,
        }

    return {
        "timestamp": timestamp.isoformat(),
        "market": {
            "change": market_change,
            "volume": volume,
            "advance_ratio": random.uniform(0.3, 0.7),
            "limit_up_count": random.randint(10, 50),
            "limit_down_count": random.randint(5, 30),
        },
        "symbols": symbols,
        "indices": {
            "SPX": {"change": market_change * random.uniform(0.8, 1.2)},
            "NDX": {"change": (market_change + 0.01) * random.uniform(0.8, 1.2)},
            "创业板": {"change": market_change * random.uniform(0.9, 1.3)},
            "科创50": {"change": (market_change + 0.015) * random.uniform(0.8, 1.4)},
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
            "affected_blocks": ["AI芯片", "半导体设备", "封装测试"],
        },
        "power_shortage": {
            "type": "电力供需",
            "content": "数据中心用电激增，多地电网超载",
            "keywords": ["电力", "数据中心", "用电激增", "电网"],
            "severity": "medium",
            "affected_blocks": ["电力设备", "绿色能源", "储能"],
        },
        "chip_ban": {
            "type": "芯片供给不足",
            "content": "美国扩大芯片出口限制，EUV设备禁运",
            "keywords": ["芯片", "制裁", "EUV", "出口限制"],
            "severity": "high",
            "affected_blocks": ["半导体设备", "国产替代", "成熟制程"],
        },
        "ai_demand_surge": {
            "type": "token需求爆发",
            "content": "ChatGPT用户激增，API调用量暴涨300%",
            "keywords": ["ChatGPT", "API", "用户激增", "算力需求"],
            "severity": "high",
            "affected_blocks": ["AI应用", "云服务", "算力基础设施"],
        },
        "breakthrough": {
            "type": "技术瓶颈突破",
            "content": "国产7nm芯片量产成功，良率达标",
            "keywords": ["国产", "7nm", "量产", "良率"],
            "severity": "medium",
            "affected_blocks": ["半导体制造", "芯片设计", "设备材料"],
        },
        "fed_rate": {
            "type": "美联储",
            "content": "美联储维持利率不变，鲍威尔暗示降息延后",
            "keywords": ["美联储", "利率", "降息", "鲍威尔"],
            "severity": "high",
            "affected_blocks": ["全局"],
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
    生成测试数据到 NB 数据库
    """
    if start_time is None:
        start_time = datetime.now() - timedelta(days=7)

    print(f"生成 {num_snapshots} 条测试数据...")
    print(f"AI/算力/芯片/Token 相关股票池: {len(AI_STOCK_POOL)} 只")
    print(f"时间范围: {start_time} ~ {start_time + timedelta(minutes=num_snapshots * interval_minutes)}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quant_snapshot_5min_window (
            key TEXT PRIMARY KEY,
            value BLOB
        )
    """)
    conn.commit()

    narrative_events = [
        "token_shortage",
        "power_shortage",
        "chip_ban",
        "ai_demand_surge",
        "breakthrough",
        "fed_rate",
    ]

    ai_trends = ["rising", "stable", "rising", "rising", "stable", "falling"]

    price_bases = {code: info["base_price"] for code, info in AI_STOCK_POOL.items()}

    for i in range(num_snapshots):
        timestamp = start_time + timedelta(minutes=i * interval_minutes)
        key = str(timestamp.timestamp())

        for code in price_bases:
            price_bases[code] *= random.uniform(0.995, 1.01)

        snapshot = generate_market_snapshot(timestamp, price_bases)
        value = pickle.dumps(snapshot)
        cursor.execute(
            "INSERT OR REPLACE INTO quant_snapshot_5min_window (key, value) VALUES (?, ?)",
            (key, value)
        )

        if i % 30 == 0:
            event_type = random.choice(narrative_events)
            event = generate_narrative_event(timestamp, event_type)
            value = pickle.dumps(event)
            cursor.execute(
                "INSERT OR REPLACE INTO quant_snapshot_5min_window (key, value) VALUES (?, ?)",
                (str(timestamp.timestamp()), value)
            )

        if i % 20 == 0:
            trend = random.choice(ai_trends)
            ai_compute = generate_ai_compute_trend(timestamp, trend)
            value = pickle.dumps(ai_compute)
            cursor.execute(
                "INSERT OR REPLACE INTO quant_snapshot_5min_window (key, value) VALUES (?, ?)",
                (str(timestamp.timestamp() + 0.5), value)
            )

        if (i + 1) % 50 == 0:
            print(f"  已生成 {i + 1}/{num_snapshots} 条数据...")
            conn.commit()

    conn.commit()
    conn.close()

    from deva.naja.tables import set_table_data
    watchlist_data = {
        "stocks": [
            {"code": code, "name": info["name"], "block": info["block"], "base_price": info["base_price"]}
            for code, info in AI_STOCK_POOL.items()
        ],
        "updated_at": datetime.now().isoformat(),
    }
    set_table_data("naja_watchlist", "ai_stocks", watchlist_data)

    print(f"\n✅ 数据生成完成！")
    print(f"  - AI股票池: {len(AI_STOCK_POOL)} 只")
    print(f"  - 行情快照: {num_snapshots} 条")
    print(f"  - 叙事事件: {num_snapshots // 30 + 1} 条")
    print(f"  - AI算力趋势: {num_snapshots // 20 + 1} 条")
    print(f"  - 自选股已保存到 naja_watchlist 表")

    print(f"\n启动命令:")
    print(f"  python -m deva.naja --lab --lab-table quant_snapshot_5min_window --lab-speed 3.0")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        num = int(sys.argv[1])
    else:
        num = 200
    generate_test_data(num_snapshots=num)
