#!/usr/bin/env python3
"""
测试回放数据源功能
"""

from deva import Stream, timer, Deva, log, NB
from deva.admin_ui.strategy.datasource import create_replay_source, get_replay_tables, DataSourceManager
import random
import time

# 先创建一些测试数据
def create_test_data():
    """创建测试数据"""
    # 创建一个时间键模式的表
    signals = NB('test_signals', key_mode='time')
    
    # 生成10条测试数据
    for i in range(10):
        price = round(10 + random.uniform(-0.8, 0.8), 3)
        score = round(random.uniform(0, 1), 3)
        side = "BUY" if score > 0.7 else "HOLD" if score > 0.4 else "SELL"
        data = {
            "ts": time.time(),
            "symbol": "600519.SH",
            "price": price,
            "score": score,
            "side": side,
        }
        signals.append(data)
        print(f"创建测试数据: {data}")
        time.sleep(0.5)  # 确保时间戳不同

# 测试回放数据源
def test_replay_source():
    """测试回放数据源"""
    # 获取支持回放的表
    replay_tables = get_replay_tables()
    print(f"支持回放的表: {replay_tables}")
    
    if not replay_tables:
        print("没有找到支持回放的表，请先运行 create_test_data()")
        return
    
    # 查找 test_signals 表
    table_name = None
    for table in replay_tables:
        if table['name'] == 'test_signals':
            table_name = table['name']
            break
    
    if not table_name:
        print("没有找到 test_signals 表，请先运行 create_test_data()")
        return
    
    print(f"使用表: {table_name}")
    
    # 创建回放数据源
    source = create_replay_source(
        name="Test Replay Source",
        table_name=table_name,
        interval=0.5,  # 每0.5秒回放一条数据
        description="测试回放数据源",
        auto_start=False
    )
    
    # 监听数据源的输出
    source.sink(lambda x: print(f"回放数据: {x}"))
    
    # 启动数据源
    print("启动回放数据源...")
    result = source.start()
    print(f"启动结果: {result}")
    
    # 等待回放完成
    print("等待回放完成...")
    while source.status == "running":
        time.sleep(1)  # 每秒检查一次状态
    
    # 检查数据源状态
    print(f"数据源状态: {source.status}")

if __name__ == "__main__":
    # 先创建测试数据
    print("创建测试数据...")
    create_test_data()
    
    # 然后测试回放数据源
    print("\n测试回放数据源...")
    test_replay_source()
    
    # 运行Deva事件循环
    print("\n运行Deva事件循环...")
    Deva.run()
