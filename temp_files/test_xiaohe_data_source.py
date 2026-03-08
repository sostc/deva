#!/usr/bin/env python3
"""
测试萧何智能体的数据源订阅和价格更新功能
"""

from deva.naja.agent.xiaohe import XiaoHeAgent
from deva import Stream, PeriodicCallback
import time
import random

# 模拟行情回放数据源
class MockReplayDataSource:
    def __init__(self):
        self.name = "模拟行情回放数据源"
        self.stream = Stream()
        self.is_running = True
    
    def start(self):
        self.is_running = True
        return {'success': True}
    
    def _emit(self, data):
        self.stream._emit(data)

def generate_price_updates():
    """生成模拟的价格更新数据"""
    # 模拟一些股票的价格更新
    stocks = [
        {'code': '600000', 'name': '浦发银行', 'price': random.uniform(8.0, 10.0)},
        {'code': '600519', 'name': '贵州茅台', 'price': random.uniform(1500.0, 1800.0)},
        {'code': '000001', 'name': '平安银行', 'price': random.uniform(12.0, 15.0)},
    ]
    return stocks

def test_xiaohe_data_source():
    """测试萧何智能体的数据源订阅和价格更新功能"""
    print("=== 测试萧何智能体的数据源订阅和价格更新功能 ===")
    
    # 创建萧何智能体
    xiaohe = XiaoHeAgent()
    
    # 启动萧何
    xiaohe._do_start()
    
    # 创建模拟的行情回放数据源
    data_source = MockReplayDataSource()
    
    # 让萧何订阅模拟数据源
    xiaohe.subscribe_to_data_source(data_source)
    
    # 添加一些持仓
    xiaohe.add_position("测试策略", 100, 9.0, "600000", "浦发银行")
    xiaohe.add_position("测试策略", 10, 1600.0, "600519", "贵州茅台")
    
    # 启动模拟数据源，定期发送价格更新
    PeriodicCallback(lambda: data_source._emit(generate_price_updates()), 2000)
    
    # 等待一段时间，让价格更新生效
    print("等待价格更新...")
    time.sleep(5)
    
    # 汇报持仓情况
    print("\n=== 持仓情况 ===")
    xiaohe.report_positions()
    
    # 停止萧何
    xiaohe._do_stop()
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_xiaohe_data_source()
