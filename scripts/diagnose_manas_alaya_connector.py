#!/usr/bin/env python
"""诊断脚本：验证 ManasAlayaConnector 完整性"""
import os
import sys

os.environ['NAJA_LAB_MODE'] = '1'

print("=" * 70)
print("诊断：Manas-Alaya 连接器完整性")
print("=" * 70)

from deva.naja.manas_alaya_connector import get_connector, ManasAlayaConnector
from deva.naja.register import SR

print("\n[1] 获取 ManasAlayaConnector 实例...")
connector = SR('connector')
print(f"    connector: {connector}")
print(f"    type: {type(connector).__name__}")

print("\n[2] 检查子组件...")
print(f"    _manas: {connector._manas}")
print(f"    _alaya: {connector._alaya}")
print(f"    _epiphany_engine: {connector._epiphany_engine}")
print(f"    _wisdom_retriever: {connector._wisdom_retriever}")

print("\n[3] 模拟 compute 调用...")
portfolio_data = {
    "held_symbols": ["000001", "000002"],
    "total_return": 0.05,
    "cash_ratio": 0.3,
}
market_data = {"sector": "tech", "market_status": "trading"}

result = connector.compute(
    portfolio_data=portfolio_data,
    market_data=market_data,
    macro_signal=0.6
)

print(f"    compute 成功: {result is not None}")
if result:
    print(f"    attention_focus: {result.get('attention_focus')}")
    print(f"    should_act: {result.get('should_act')}")
    print(f"    has_epiphany: {result.get('has_epiphany')}")

print("\n[4] 检查 WisdomRetriever...")
w_stats = connector.get_wisdom_stats()
print(f"    wisdom_stats: {w_stats}")

print("\n[5] 检查单例模式...")
connector2 = SR('connector')
print(f"    两次获取是同一实例: {connector is connector2}")

print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)