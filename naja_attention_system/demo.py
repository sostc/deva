"""
Naja Attention Scheduling System - Demo

演示如何使用注意力系统进行实时市场数据处理和策略调度
"""

import numpy as np
import time
import asyncio
from typing import Dict, List

from naja_attention_system import (
    AttentionSystem,
    AttentionSystemConfig,
    SectorConfig,
    StrategyConfig,
    StrategyParams,
    StrategyScope,
    StrategyType,
    Strategy,
    StrategyRegistry,
    FrequencyLevel
)


class DemoStrategy(Strategy):
    """演示策略"""
    
    async def on_activate(self):
        print(f"  [Strategy] {self.config.name} activated")
    
    async def on_deactivate(self):
        print(f"  [Strategy] {self.config.name} deactivated")
    
    async def execute(self, context: Dict) -> Dict:
        self.execution_count += 1
        self.last_execution_time = time.time()
        return {
            'strategy_id': self.config.strategy_id,
            'signal': 'buy' if np.random.random() > 0.5 else 'sell',
            'confidence': np.random.random()
        }


def create_demo_sectors() -> List[SectorConfig]:
    """创建演示板块"""
    return [
        SectorConfig(
            sector_id="tech",
            name="科技",
            symbols={"AAPL", "MSFT", "GOOGL", "NVDA", "META"},
            decay_half_life=300.0
        ),
        SectorConfig(
            sector_id="finance",
            name="金融",
            symbols={"JPM", "BAC", "WFC", "GS", "MS"},
            decay_half_life=300.0
        ),
        SectorConfig(
            sector_id="energy",
            name="能源",
            symbols={"XOM", "CVX", "COP", "EOG", "SLB"},
            decay_half_life=300.0
        ),
        SectorConfig(
            sector_id="healthcare",
            name="医疗",
            symbols={"JNJ", "PFE", "UNH", "ABBV", "MRK"},
            decay_half_life=300.0
        ),
    ]


def create_symbol_sector_map() -> Dict[str, List[str]]:
    """创建个股-板块映射"""
    return {
        # 科技
        "AAPL": ["tech"],
        "MSFT": ["tech"],
        "GOOGL": ["tech"],
        "NVDA": ["tech"],
        "META": ["tech"],
        # 金融
        "JPM": ["finance"],
        "BAC": ["finance"],
        "WFC": ["finance"],
        "GS": ["finance"],
        "MS": ["finance"],
        # 能源
        "XOM": ["energy"],
        "CVX": ["energy"],
        "COP": ["energy"],
        "EOG": ["energy"],
        "SLB": ["energy"],
        # 医疗
        "JNJ": ["healthcare"],
        "PFE": ["healthcare"],
        "UNH": ["healthcare"],
        "ABBV": ["healthcare"],
        "MRK": ["healthcare"],
    }


def create_demo_strategies(registry: StrategyRegistry):
    """创建演示策略"""
    
    # 全局策略
    global_strategies = [
        StrategyConfig(
            strategy_id="global_risk",
            name="全局风险控制",
            scope=StrategyScope.GLOBAL,
            strategy_type=StrategyType.RISK_CONTROL,
            params=StrategyParams(threshold=0.7, risk_limit=0.03),
            min_attention=0.0,
            max_attention=1.0
        ),
        StrategyConfig(
            strategy_id="global_trend",
            name="全局趋势跟踪",
            scope=StrategyScope.GLOBAL,
            strategy_type=StrategyType.TREND,
            params=StrategyParams(threshold=0.5, window=15),
            min_attention=0.3,
            max_attention=1.0
        ),
    ]
    
    # 板块策略
    sector_strategies = [
        StrategyConfig(
            strategy_id="sector_rotation",
            name="板块轮动",
            scope=StrategyScope.SECTOR,
            strategy_type=StrategyType.TREND,
            params=StrategyParams(threshold=0.4, window=10),
            min_attention=0.2,
            max_attention=1.0
        ),
        StrategyConfig(
            strategy_id="sector_momentum",
            name="板块动量",
            scope=StrategyScope.SECTOR,
            strategy_type=StrategyType.EVENT_DRIVEN,
            params=StrategyParams(threshold=0.3, window=5),
            min_attention=0.4,
            max_attention=1.0
        ),
    ]
    
    # 个股策略
    symbol_strategies = [
        StrategyConfig(
            strategy_id="symbol_breakout",
            name="个股突破",
            scope=StrategyScope.SYMBOL,
            strategy_type=StrategyType.EVENT_DRIVEN,
            params=StrategyParams(threshold=0.3, window=5, position_size=0.1),
            min_attention=0.3,
            max_attention=1.0
        ),
        StrategyConfig(
            strategy_id="symbol_mean_reversion",
            name="个股均值回归",
            scope=StrategyScope.SYMBOL,
            strategy_type=StrategyType.OBSERVATION,
            params=StrategyParams(threshold=0.6, window=20, position_size=0.05),
            min_attention=0.0,
            max_attention=0.5
        ),
    ]
    
    # 注册策略工厂
    registry.register_factory("observation", DemoStrategy)
    registry.register_factory("trend", DemoStrategy)
    registry.register_factory("event_driven", DemoStrategy)
    registry.register_factory("risk_control", DemoStrategy)
    
    # 创建并注册策略实例
    for config in global_strategies + sector_strategies + symbol_strategies:
        strategy = registry.create_strategy(config)
        if strategy:
            registry.register(strategy)


def generate_mock_snapshot(
    symbols: List[str],
    timestamp: float,
    volatility: float = 1.0
) -> Dict:
    """生成模拟市场快照"""
    n = len(symbols)
    
    # 生成模拟数据
    returns = np.random.normal(0, volatility, n)
    volumes = np.random.exponential(1000000, n)
    prices = 100 + np.cumsum(returns) + np.random.normal(0, 0.1, n)
    
    # 板块映射
    sector_map = create_symbol_sector_map()
    sector_ids = []
    for symbol in symbols:
        sectors = sector_map.get(symbol, [])
        sector_ids.append(hash(sectors[0]) if sectors else 0)
    
    return {
        'symbols': np.array(symbols),
        'returns': returns,
        'volumes': volumes,
        'prices': prices,
        'sector_ids': np.array(sector_ids),
        'timestamp': timestamp
    }


async def run_demo():
    """运行演示"""
    print("=" * 70)
    print("Naja Attention Scheduling System Demo")
    print("=" * 70)
    
    # 1. 创建配置
    config = AttentionSystemConfig(
        global_history_window=20,
        max_sectors=10,
        max_symbols=100,
        low_interval=60.0,
        medium_interval=10.0,
        high_interval=1.0
    )
    
    # 2. 创建系统
    attention_system = AttentionSystem(config)
    
    # 3. 初始化板块和个股
    sectors = create_demo_sectors()
    symbol_sector_map = create_symbol_sector_map()
    attention_system.initialize(sectors, symbol_sector_map)
    
    print("\n[1] 系统初始化完成")
    print(f"    - 板块数量: {len(sectors)}")
    print(f"    - 个股数量: {len(symbol_sector_map)}")
    
    # 4. 创建策略
    create_demo_strategies(attention_system.strategy_allocator.registry)
    print(f"\n[2] 策略注册完成")
    print(f"    - 策略数量: {len(attention_system.strategy_allocator.registry.get_all())}")
    
    # 5. 模拟市场数据
    symbols = list(symbol_sector_map.keys())
    
    print("\n[3] 开始模拟市场数据处理")
    print("-" * 70)
    
    for i in range(10):
        timestamp = time.time() + i * 5  # 每5秒一个快照
        
        # 模拟不同市场状态
        if i < 3:
            volatility = 0.5  # 平静期
        elif i < 6:
            volatility = 2.0  # 波动期
        else:
            volatility = 1.0  # 恢复期
        
        snapshot = generate_mock_snapshot(symbols, timestamp, volatility)
        
        # 处理快照
        result = attention_system.process_snapshot(**snapshot)
        
        # 打印结果
        print(f"\n[Snapshot {i+1}] t={timestamp:.1f}")
        print(f"  Global Attention: {result['global_attention']:.3f}")
        print(f"  Market State: {result['market_state']['trend']}")
        print(f"  Latency: {result['latency_ms']:.2f}ms")
        
        # 板块注意力
        top_sectors = sorted(
            result['sector_attention'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        print(f"  Top Sectors: {[(s, f'{v:.3f}') for s, v in top_sectors]}")
        
        # 高权重个股
        top_symbols = sorted(
            result['symbol_weights'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        print(f"  Top Symbols: {[(s, f'{v:.3f}') for s, v in top_symbols]}")
        
        # 频率分布
        freq_summary = attention_system.frequency_scheduler.get_schedule_summary()
        print(f"  Frequency: HIGH={freq_summary['high_frequency']}, "
              f"MEDIUM={freq_summary['medium_frequency']}, "
              f"LOW={freq_summary['low_frequency']}")
        
        # 策略分配
        strategy_summary = attention_system.strategy_allocator.get_allocation_summary()
        print(f"  Active Strategies: {strategy_summary['active_count']}")
        
        # 模式识别信号
        if result['pattern_signals']:
            print(f"  Pattern Signals: {len(result['pattern_signals'])}")
            for signal in result['pattern_signals'][:2]:
                print(f"    - {signal.symbol}: {signal.pattern_type} "
                      f"(conf={signal.confidence:.2f})")
        
        # 模拟 PyTorch 批量处理
        if i % 3 == 0:
            patterns = await attention_system.process_pytorch_batch()
            if patterns:
                print(f"  PyTorch Batch: {len(patterns)} patterns processed")
        
        # 小延迟模拟实时
        await asyncio.sleep(0.1)
    
    print("\n" + "-" * 70)
    print("\n[4] 系统状态总结")
    status = attention_system.get_system_status()
    print(f"  Total Snapshots: {status['processing_count']}")
    print(f"  Avg Latency: {status['avg_latency_ms']:.2f}ms")
    print(f"  Final Global Attention: {status['global_attention']:.3f}")
    
    print("\n[5] 数据源控制指令")
    control = attention_system.get_datasource_control()
    print(f"  High Frequency: {len(control['high_freq_symbols'])} symbols")
    print(f"  Medium Frequency: {len(control['medium_freq_symbols'])} symbols")
    print(f"  Low Frequency: {len(control['low_freq_symbols'])} symbols")
    print(f"  Intervals: HIGH={control['intervals']['high']}s, "
          f"MEDIUM={control['intervals']['medium']}s, "
          f"LOW={control['intervals']['low']}s")
    
    print("\n" + "=" * 70)
    print("Demo completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_demo())