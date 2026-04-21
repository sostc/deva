"""
River 策略适配器 - 将 River 策略挂载到热点系统

架构原则:
- 热点聚焦: 只在值得计算的时候计算
- 分层执行: 全量低频 / 板块中频 / 个股高频
- 动态调度: 根据热点自动调整执行频率
- 不追高: 热点太高的股票跳过,只在启动前/启动时捕获

分层设计:
┌─ 全量扫描层 (低频 5-10分钟): 发现即将进入热点的潜力股
├─ 热点确认层 (中频 1-3分钟): 捕捉正在进入热点的启动点
└─ 热点跟踪层 (低频 3-5分钟): 持仓管理 + 退潮预警
"""

from __future__ import annotations

import time
import numpy as np
from typing import Dict, List, Optional, Any

from .base import HotspotStrategyBase, Signal

from deva.naja.strategy.advanced_river_strategies import (
    EarlyTrendDetector,
    StockSelector,
)
from deva.naja.strategy.bandit_stock_strategies import (
    BlockStockSelector,
    EarlyBullFinder,
)


class RiverEarlyBullAdapter(HotspotStrategyBase):
    """早期牛股发现 - 全量扫描层 (低频)
    
    目标: 发现还没进热点但有启动迹象的股票
    热点范围: 全市场扫描,权重 < 3 的股票
    
    【测试模式】参数已放宽，优先保证信号产出，跑通数据流。
    """
    
    def __init__(self):
        super().__init__(
            strategy_id="river_early_bull",
            name="River 早期牛股发现",
            scope='symbol',
            market_scope='ALL',
            min_global_hotspot=0.0,    # 放宽: 无热点门槛
            min_symbol_weight=0.0,     # 放宽: 所有股票
            max_symbol_weight=10.0,    # 放宽: 几乎不限制上限
            cooldown_period=60.0,      # 放宽: 1分钟冷却 (原300s)
        )
        self._core = EarlyBullFinder(
            rise_threshold=0.5,         # 放宽: 涨幅>0.5%即触发 (原2.0%)
            volume_boost=1.0,           # 放宽: 量比>1.0即可 (原1.5)
            momentum_window=3,          # 放宽: 更短的动量窗口
        )
    
    def _on_signal(self, signal: Signal):
        print(f"[早期牛股] {signal.signal_type.upper()} | {signal.symbol} | "
              f"得分:{signal.score:.2f} | {signal.reason}")
    
    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        signals = []
        if data is None or (hasattr(data, 'empty') and data.empty):
            return signals
        
        self._core.on_data({"data": data})
        core_signal = self._core.get_signal()
        if not core_signal:
            log.debug(f"[{self.name}] 核心策略返回空信号, history_count={len(self._core._score_history) if hasattr(self._core, '_score_history') else 'N/A'}")
            return signals
        
        candidates = core_signal.get("candidates", [])
        log.debug(f"[{self.name}] 核心策略返回 {len(candidates)} 个候选: {candidates[:3]}")
        for c in candidates[:5]:  # 放宽: 每次最多5个 (原3个)
            code = c.get("stock_code", "")
            weight = self.get_symbol_weight(code)
            
            if weight >= self.max_symbol_weight:
                log.debug(f"[{self.name}] {code} 跳过: weight={weight} >= max={self.max_symbol_weight}")
                continue
            
            if not self.can_emit_signal(code):
                log.debug(f"[{self.name}] {code} 跳过: 冷却中")
                continue
            
            signal = Signal(
                strategy_name=self.name,
                symbol=code,
                signal_type='buy',
                confidence=c.get("momentum_score", 0) / 10.0,
                score=min(1.0, c.get("momentum_score", 0) / 10.0),
                reason=f"早期牛股 | 涨幅:{c.get('change',0):.1f}% 量比:{c.get('volume_ratio',0):.1f}x",
                timestamp=self._get_market_time(),
                metadata=c
            )
            self.emit_signal(signal)
            signals.append(signal)
            log.info(f"[{self.name}] 产生信号: {code} | {signal.reason}")
        
        return signals


class RiverStockSelectorAdapter(HotspotStrategyBase):
    """全市场选股 - 全量扫描层 (低频)
    
    目标: 全市场打分,找出得分高但热点权重还低的潜力股
    热点范围: 全市场扫描,权重 < 5 的股票
    
    【测试模式】参数已放宽，优先保证信号产出，跑通数据流。
    """
    
    def __init__(self):
        super().__init__(
            strategy_id="river_stock_selector",
            name="River 全市场选股",
            scope='symbol',
            market_scope='ALL',
            min_global_hotspot=0.0,    # 放宽: 无热点门槛
            min_symbol_weight=0.0,     # 放宽: 所有股票
            max_symbol_weight=10.0,    # 放宽: 几乎不限制上限
            cooldown_period=60.0,      # 放宽: 1分钟冷却 (原300s)
        )
        self._core = StockSelector(
            top_n=10,                   # 放宽: 每次选10个 (原5个)
            min_score=0.0,              # 放宽: 无最低分门槛
        )
    
    def _on_signal(self, signal: Signal):
        print(f"[全市场选股] {signal.signal_type.upper()} | {signal.symbol} | "
              f"得分:{signal.score:.2f} | {signal.reason}")
    
    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        signals = []
        if data is None or (hasattr(data, 'empty') and data.empty):
            return signals
        
        self._core.on_data({"data": data})
        core_signal = self._core.get_signal()
        if not core_signal:
            return signals
        
        selected = core_signal.get("selected_stocks", [])
        for s in selected:
            code = s.get("stock_code", "")
            weight = self.get_symbol_weight(code)
            
            if weight >= self.max_symbol_weight:
                continue
            
            if not self.can_emit_signal(code):
                continue
            
            signal = Signal(
                strategy_name=self.name,
                symbol=code,
                signal_type='buy',
                confidence=s.get("score", 0),
                score=s.get("score", 0),
                reason=f"精选股 | 评分:{s.get('score',0):.2f} 涨幅:{s.get('change',0):.1f}%",
                timestamp=self._get_market_time(),
                metadata=s
            )
            self.emit_signal(signal)
            signals.append(signal)
        
        return signals


class RiverEarlyTrendAdapter(HotspotStrategyBase):
    """早期趋势检测 - 热点确认层 (中频)
    
    目标: 确认正在进入热点的趋势形成
    热点范围: 权重 1-6 的股票 (正在进入热点)
    
    【测试模式】参数已放宽，优先保证信号产出，跑通数据流。
    """
    
    def __init__(self):
        super().__init__(
            strategy_id="river_early_trend",
            name="River 早期趋势检测",
            scope='symbol',
            market_scope='ALL',
            min_global_hotspot=0.0,    # 放宽: 无热点门槛
            min_symbol_weight=0.0,     # 放宽: 所有股票
            max_symbol_weight=10.0,    # 放宽: 几乎不限制上限
            cooldown_period=30.0,      # 放宽: 30秒冷却 (原60s)
        )
        self._core = EarlyTrendDetector(
            n_trees=10,                 # 放宽: 更少的树，更容易出信号
            height=6,                   # 放宽: 更浅的树
            window_size=30,             # 放宽: 更短的窗口
            sensitivity=0.1,            # 放宽: 高敏感度 (原0.3)
        )
    
    def _on_signal(self, signal: Signal):
        print(f"[趋势检测] {signal.signal_type.upper()} | {signal.symbol} | "
              f"得分:{signal.score:.2f} | {signal.reason}")
    
    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        signals = []
        if data is None or (hasattr(data, 'empty') and data.empty):
            return signals
        
        self._core.on_data({"data": data})
        core_signal = self._core.get_signal()
        if not core_signal:
            return signals
        
        weight = self.get_symbol_weight(core_signal.get("symbol", ""))
        if weight >= self.max_symbol_weight:
            return signals
        
        if not self.can_emit_signal(core_signal.get("symbol", "")):
            return signals
        
        signal = Signal(
            strategy_name=self.name,
            symbol=core_signal.get("symbol", ""),
            signal_type='watch' if core_signal.get("direction", 1) > 0 else 'watch',
            confidence=min(1.0, core_signal.get("score", 0)),
            score=core_signal.get("score", 0),
            reason=f"趋势信号 | 方向:{core_signal.get('direction',0)} 得分:{core_signal.get('score',0):.2f}",
            timestamp=self._get_market_time(),
            metadata=core_signal
        )
        self.emit_signal(signal)
        signals.append(signal)
        
        return signals


class RiverBlockStockSelectorAdapter(HotspotStrategyBase):
    """题材牛股精选 - 热点跟踪层 (中频)
    
    目标: 热点板块内谁最强,用于持仓管理和加仓判断
    热点范围: 板块层,权重 > 3 的股票
    
    【测试模式】参数已放宽，优先保证信号产出，跑通数据流。
    """
    
    def __init__(self):
        super().__init__(
            strategy_id="river_block_stock_selector",
            name="River 题材牛股精选",
            scope='symbol',
            market_scope='ALL',
            min_global_hotspot=0.0,    # 放宽: 无热点门槛
            min_symbol_weight=0.0,     # 放宽: 所有股票
            cooldown_period=30.0,      # 放宽: 30秒冷却 (原120s)
        )
        self._core = BlockStockSelector(
            top_n=10,                   # 放宽: 每次选10个 (原5个)
            min_score=0.0,              # 放宽: 无最低分门槛
        )
    
    def _on_signal(self, signal: Signal):
        print(f"[题材牛股] {signal.signal_type.upper()} | {signal.symbol} | "
              f"得分:{signal.score:.2f} | {signal.reason}")
    
    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        signals = []
        if data is None or (hasattr(data, 'empty') and data.empty):
            return signals
        
        self._core.on_data({"data": data})
        core_signal = self._core.get_signal()
        if not core_signal:
            return signals
        
        selected = core_signal.get("selected_stocks", [])
        for s in selected:
            code = s.get("stock_code", "")
            
            if not self.can_emit_signal(code):
                continue
            
            signal = Signal(
                strategy_name=self.name,
                symbol=code,
                signal_type='buy',
                confidence=s.get("score", 0),
                score=s.get("score", 0),
                reason=f"题材牛股 | 评分:{s.get('score',0):.2f} 题材:{s.get('block_name','')}",
                timestamp=self._get_market_time(),
                metadata=s
            )
            self.emit_signal(signal)
            signals.append(signal)
        
        return signals
