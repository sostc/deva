#!/usr/bin/env python3
"""
测试市场热点模块的嵌入技术增强

测试GlobalHotspotEngine和BlockHotspotEngine的新功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import time
from deva.naja.market_hotspot.core.global_hotspot_engine import GlobalHotspotEngine, MarketSnapshot
from deva.naja.market_hotspot.core.block_engine import BlockHotspotEngine, BlockConfig


def test_global_hotspot_engine():
    """测试GlobalHotspotEngine的嵌入技术增强"""
    print("\n" + "="*60)
    print("测试 GlobalHotspotEngine 嵌入技术增强")
    print("="*60)
    
    # 创建引擎
    engine = GlobalHotspotEngine()
    
    # 生成测试数据
    def generate_test_snapshot(timestamp):
        n = 100
        returns = np.random.normal(0, 2, n)
        volumes = np.random.normal(1000000, 500000, n)
        prices = np.random.normal(100, 20, n)
        block_ids = np.random.randint(1, 10, n)
        symbols = np.array([f"SYM{i}" for i in range(n)])
        return MarketSnapshot(
            timestamp=timestamp,
            returns=returns,
            volumes=volumes,
            prices=prices,
            block_ids=block_ids,
            symbols=symbols
        )
    
    # 测试多次更新
    for i in range(10):
        timestamp = time.time() + i
        snapshot = generate_test_snapshot(timestamp)
        hotspot, activity = engine.get_hotspot_and_activity(snapshot)
        print(f"更新 {i+1}: 热点={hotspot:.3f}, 活跃度={activity:.3f}")
    
    # 测试市场状态
    market_state = engine.get_market_state()
    print("\n市场状态:")
    print(f"  热点: {market_state['hotspot']:.3f}")
    print(f"  活跃度: {market_state['activity']:.3f}")
    print(f"  趋势: {market_state['trend']}")
    print(f"  描述: {market_state['description']}")
    
    # 验证嵌入向量是否生成
    print(f"\n嵌入向量数量: {len(engine.state_embeddings)}")
    if engine.state_embeddings:
        print(f"嵌入向量维度: {engine.state_embeddings[0].shape}")
    
    print("\n✓ GlobalHotspotEngine 测试完成")


def test_block_hotspot_engine():
    """测试BlockHotspotEngine的嵌入技术增强"""
    print("\n" + "="*60)
    print("测试 BlockHotspotEngine 嵌入技术增强")
    print("="*60)
    
    # 创建测试题材
    blocks = [
        BlockConfig(
            block_id="tech",
            name="科技",
            symbols={"NVDA", "AMD", "MSFT", "GOOGL"}
        ),
        BlockConfig(
            block_id="finance",
            name="金融",
            symbols={"JPM", "BAC", "C", "WFC"}
        ),
        BlockConfig(
            block_id="energy",
            name="能源",
            symbols={"XOM", "CVX", "COP", "SLB"}
        )
    ]
    
    # 创建引擎
    engine = BlockHotspotEngine(blocks=blocks)
    
    # 生成测试数据
    def generate_test_data():
        symbols = np.array(["NVDA", "AMD", "MSFT", "GOOGL", "JPM", "BAC", "C", "WFC", "XOM", "CVX", "COP", "SLB"])
        returns = np.random.normal(0, 2, len(symbols))
        volumes = np.random.normal(1000000, 500000, len(symbols))
        block_ids = np.array(["tech", "tech", "tech", "tech", "finance", "finance", "finance", "finance", "energy", "energy", "energy", "energy"])
        return symbols, returns, volumes, block_ids
    
    # 测试多次更新
    for i in range(5):
        timestamp = time.time() + i
        symbols, returns, volumes, block_ids = generate_test_data()
        result = engine.update(symbols, returns, volumes, timestamp, block_ids)
        
        print(f"\n更新 {i+1} 结果:")
        for block_id, score in result.items():
            block_name = engine._blocks[block_id].name if block_id in engine._blocks else block_id
            print(f"  {block_name}: {score:.3f}")
    
    # 验证嵌入向量是否生成
    print(f"\n题材嵌入向量数量: {len(engine.block_embeddings)}")
    for block_id, embedding in engine.block_embeddings.items():
        block_name = engine._blocks[block_id].name if block_id in engine._blocks else block_id
        print(f"  {block_name}: {embedding.shape}")
    
    # 测试自注意力是否应用
    print("\n✓ BlockHotspotEngine 测试完成")


def main():
    """主测试函数"""
    print("开始测试市场热点模块的嵌入技术增强")
    
    # 测试GlobalHotspotEngine
    test_global_hotspot_engine()
    
    # 测试BlockHotspotEngine
    test_block_hotspot_engine()
    
    print("\n" + "="*60)
    print("所有测试完成!")
    print("="*60)


if __name__ == "__main__":
    main()
