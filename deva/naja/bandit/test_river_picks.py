#!/usr/bin/env python3
"""测试 River picks 格式解析"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("River Picks 格式解析测试")
print("=" * 60)

from deva.naja.bandit import get_signal_listener
from deva.naja.strategy.result_store import StrategyResult

print("\n[1] 测试 River short_term_up_probability 格式...")

river_output = {
    "signal": "short_term_up_probability",
    "top_n": 8,
    "picks": [
        {
            "code": "SZ000001",
            "name": "平安银行",
            "up_probability": 0.75,
            "price": 12.50,
            "blockname": "银行",
            "industry": "金融"
        },
        {
            "code": "SH600000",
            "name": "浦发银行",
            "up_probability": 0.68,
            "price": 8.20,
            "blockname": "银行",
            "industry": "金融"
        }
    ]
}

result = StrategyResult(
    id=f"river_test_{int(time.time() * 1000)}",
    strategy_id="river_short_term_up",
    strategy_name="短期上涨概率策略",
    ts=time.time(),
    success=True,
    output_full=river_output,
    output_preview=str(river_output)
)

listener = get_signal_listener()
detected = listener._parse_signal(result)

if detected:
    print(f"   ✅ 解析成功")
    print(f"      - 股票代码: {detected.stock_code}")
    print(f"      - 股票名称: {detected.stock_name}")
    print(f"      - 信号类型: {detected.signal_type}")
    print(f"      - 价格: {detected.price}")
    print(f"      - 置信度: {detected.confidence}")
else:
    print(f"   ❌ 解析失败")

print("\n[2] 测试 River order_flow_imbalance_lead 格式...")

river_output2 = {
    "signal": "order_flow_imbalance_lead",
    "top_n": 8,
    "picks": [
        {
            "code": "SZ000002",
            "name": "万科A",
            "order_flow_up_probability": 0.82,
            "price": 9.80,
            "ofi": 1500.5,
            "depth_imb": 0.3,
            "blockname": "房地产",
            "industry": "地产"
        }
    ]
}

result2 = StrategyResult(
    id=f"river_test2_{int(time.time() * 1000)}",
    strategy_id="river_order_flow",
    strategy_name="订单流失衡领先策略",
    ts=time.time(),
    success=True,
    output_full=river_output2,
    output_preview=str(river_output2)
)

detected2 = listener._parse_signal(result2)

if detected2:
    print(f"   ✅ 解析成功")
    print(f"      - 股票代码: {detected2.stock_code}")
    print(f"      - 股票名称: {detected2.stock_name}")
    print(f"      - 信号类型: {detected2.signal_type}")
    print(f"      - 价格: {detected2.price}")
    print(f"      - 置信度: {detected2.confidence}")
else:
    print(f"   ❌ 解析失败")

print("\n[3] 测试 River anomaly 格式...")

river_output3 = {
    "signal": "volume_anomaly",
    "top_n": 5,
    "picks": [
        {
            "code": "SZ000003",
            "name": "神州高铁",
            "anomaly_score": 8.5,
            "price": 4.20,
            "blockname": "铁路",
            "industry": "交运"
        }
    ]
}

result3 = StrategyResult(
    id=f"river_test3_{int(time.time() * 1000)}",
    strategy_id="river_anomaly",
    strategy_name="量价异常检测策略",
    ts=time.time(),
    success=True,
    output_full=river_output3,
    output_preview=str(river_output3)
)

detected3 = listener._parse_signal(result3)

if detected3:
    print(f"   ✅ 解析成功")
    print(f"      - 股票代码: {detected3.stock_code}")
    print(f"      - 股票名称: {detected3.stock_name}")
    print(f"      - 信号类型: {detected3.signal_type}")
    print(f"      - 价格: {detected3.price}")
    print(f"      - 置信度: {detected3.confidence}")
else:
    print(f"   ❌ 解析失败")

print("\n[4] 测试直接格式 (向后兼容)...")

direct_output = {
    "signal_type": "BUY",
    "stock_code": "SZ000001",
    "stock_name": "平安银行",
    "price": 12.50,
    "confidence": 0.85
}

result4 = StrategyResult(
    id=f"direct_test_{int(time.time() * 1000)}",
    strategy_id="direct_strategy",
    strategy_name="直接信号策略",
    ts=time.time(),
    success=True,
    output_full=direct_output,
    output_preview=str(direct_output)
)

detected4 = listener._parse_signal(result4)

if detected4:
    print(f"   ✅ 解析成功")
    print(f"      - 股票代码: {detected4.stock_code}")
    print(f"      - 股票名称: {detected4.stock_name}")
    print(f"      - 信号类型: {detected4.signal_type}")
    print(f"      - 价格: {detected4.price}")
    print(f"      - 置信度: {detected4.confidence}")
else:
    print(f"   ❌ 解析失败")

print("\n[5] 测试置信度过滤...")

listener.set_min_confidence(0.7)

if detected and detected.confidence >= 0.7:
    print(f"   ✅ 置信度过滤正常: {detected.confidence} >= 0.7")
else:
    print(f"   ⚠️ 置信度检查")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
