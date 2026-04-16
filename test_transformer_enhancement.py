#!/usr/bin/env python3
"""
测试 Transformer 增强器集成

验证市场热点模块的 Transformer 增强功能是否正常工作
"""

import numpy as np
import time
from deva.naja.market_hotspot.core.global_hotspot_engine import GlobalHotspotEngine, MarketSnapshot
from deva.naja.market_hotspot.core.block_engine import BlockHotspotEngine, BlockConfig


def test_global_hotspot_transformer():
    """测试全局热点引擎的 Transformer 增强"""
    print("=== 测试全局热点引擎 Transformer 增强 ===")
    
    # 初始化全局热点引擎
    engine = GlobalHotspotEngine(history_window=20)
    
    # 生成测试数据
    def generate_test_snapshot(timestamp):
        n_stocks = 100
        returns = np.random.normal(0, 2, n_stocks)
        volumes = np.random.uniform(1e6, 1e9, n_stocks)
        prices = np.random.uniform(10, 1000, n_stocks)
        block_ids = np.array([f"block_{i % 10}" for i in range(n_stocks)])
        symbols = np.array([f"stock_{i}" for i in range(n_stocks)])
        
        return MarketSnapshot(
            timestamp=timestamp,
            returns=returns,
            volumes=volumes,
            prices=prices,
            block_ids=block_ids,
            symbols=symbols
        )
    
    # 测试多个时间点
    for i in range(10):
        timestamp = time.time() + i * 60
        snapshot = generate_test_snapshot(timestamp)
        
        # 更新引擎
        hotspot = engine.update(snapshot)
        
        # 获取市场状态
        market_state = engine.get_market_state()
        
        print(f"时间点 {i+1}: 热点分数 = {hotspot:.4f}")
        print(f"  市场状态: {market_state['description']}")
        print(f"  增强分析: {market_state['enhanced_analysis']}")
        print()
    
    print("全局热点引擎 Transformer 增强测试完成！")
    print()


def test_block_hotspot_transformer():
    """测试题材热点引擎的 Transformer 增强"""
    print("=== 测试题材热点引擎 Transformer 增强 ===")
    
    # 初始化题材配置
    blocks = [
        BlockConfig(block_id="block_1", name="科技", symbols={"stock_1", "stock_2", "stock_3"}),
        BlockConfig(block_id="block_2", name="金融", symbols={"stock_4", "stock_5", "stock_6"}),
        BlockConfig(block_id="block_3", name="医药", symbols={"stock_7", "stock_8", "stock_9"}),
        BlockConfig(block_id="block_4", name="能源", symbols={"stock_10", "stock_11", "stock_12"}),
        BlockConfig(block_id="block_5", name="消费", symbols={"stock_13", "stock_14", "stock_15"}),
    ]
    
    # 初始化题材热点引擎
    engine = BlockHotspotEngine(blocks=blocks)
    
    # 生成测试数据
    def generate_test_data(timestamp):
        symbols = np.array([f"stock_{i}" for i in range(1, 16)])
        returns = np.random.normal(0, 2, 15)
        volumes = np.random.uniform(1e6, 1e9, 15)
        block_ids = np.array([f"block_{(i-1) // 3 + 1}" for i in range(1, 16)])
        
        return symbols, returns, volumes, block_ids
    
    # 测试多个时间点
    for i in range(5):
        timestamp = time.time() + i * 60
        symbols, returns, volumes, block_ids = generate_test_data(timestamp)
        
        # 更新引擎
        block_hotspots = engine.update(symbols, returns, volumes, timestamp, block_ids)
        
        # 获取热点最高的题材
        top_blocks = engine.get_top_blocks(n=3)
        
        print(f"时间点 {i+1}:")
        for block_id, score in top_blocks:
            block_name = next((b.name for b in blocks if b.block_id == block_id), block_id)
            print(f"  {block_name}: {score:.4f}")
        print()
    
    print("题材热点引擎 Transformer 增强测试完成！")
    print()


if __name__ == "__main__":
    # 运行测试
    test_global_hotspot_transformer()
    test_block_hotspot_transformer()
    
    print("所有 Transformer 增强测试完成！")
