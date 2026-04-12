"""
双引擎协调器

协调 River 引擎和 PyTorch 引擎的执行：
- River 全量处理每个 tick
- 异常分数超阈值时激活 PyTorch
- 合并两个引擎的输出
"""

import numpy as np
from typing import Dict, List, Optional, Any
import time
import asyncio

from .models import AnomalyLevel, AnomalySignal, PatternSignal
from .river_engine import RiverEngine
from .pytorch_engine import PyTorchEngine


class DualEngineCoordinator:
    """
    双引擎协调器
    
    职责:
    1. 管理 River 和 PyTorch 引擎
    2. 处理触发逻辑
    3. 控制资源占用
    4. 避免重复触发
    """
    
    def __init__(
        self,
        river_engine: Optional[RiverEngine] = None,
        pytorch_engine: Optional[PyTorchEngine] = None,
        max_pytorch_triggers: int = 50  # 每轮最大 PyTorch 触发数
    ):
        self.river = river_engine or RiverEngine()
        self.pytorch = pytorch_engine or PyTorchEngine()
        self.max_pytorch_triggers = max_pytorch_triggers
        
        # 触发控制
        self._trigger_cooldown: Dict[str, float] = {}
        self._cooldown_period = 60.0  # 冷却期(秒)
        
        # 触发分数权重
        self._anomaly_weight = 0.4
        self._symbol_weight = 0.3
        self._block_weight = 0.2
        self._global_weight = 0.1
        
        # 统计
        self._trigger_count = 0
    
    def process_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        global_hotspot: float,
        block_hotspot: Dict[str, float],
        symbol_weight: float,
        timestamp: float
    ) -> Optional[PatternSignal]:
        """
        处理单个 tick
        
        流程:
        1. River 处理
        2. 如果异常，计算触发分数
        3. 如果触发分数高，提交到 PyTorch
        4. 返回 PyTorch 结果
        """
        # Step 0: 确保股票已注册
        if symbol not in self.river._symbol_to_idx:
            self.river.register_symbol(symbol)
        
        # Step 1: River 处理
        anomaly_signal = self.river.process_tick(symbol, price, volume, timestamp)
        
        if anomaly_signal is None:
            return None
        
        # Step 2: 计算触发分数
        trigger_score = self._calc_trigger_score(
            anomaly_signal,
            global_hotspot,
            block_hotspot,
            symbol_weight
        )
        
        # Step 3: 检查是否触发 PyTorch
        if not self._should_trigger_pytorch(symbol, trigger_score, timestamp):
            return None
        
        # Step 4: 提交到 PyTorch
        self.pytorch.submit(anomaly_signal)
        
        # 返回缓存的结果 (如果有)
        return self.pytorch.get_pattern(symbol)
    
    def _calc_trigger_score(
        self,
        anomaly_signal: AnomalySignal,
        global_hotspot: float,
        block_hotspot: Dict[str, float],
        symbol_weight: float
    ) -> float:
        """
        计算触发分数

        trigger_score = f(anomaly_score, symbol_weight, block_hotspot, global_hotspot)
        """
        try:
            # 题材热点取平均 - 添加数值检查
            if block_hotspot:
                values = list(block_hotspot.values())
                # 过滤掉异常值
                valid_values = [v for v in values if isinstance(v, (int, float)) and not np.isnan(v) and not np.isinf(v)]
                avg_block_hotspot = np.mean(valid_values) if valid_values else 0.0
            else:
                avg_block_hotspot = 0.0

            # 确保 global_hotspot 是有效数值
            if not isinstance(global_hotspot, (int, float)) or np.isnan(global_hotspot) or np.isinf(global_hotspot):
                global_hotspot = 0.0

            # 确保 symbol_weight 是有效数值
            if not isinstance(symbol_weight, (int, float)) or np.isnan(symbol_weight) or np.isinf(symbol_weight):
                symbol_weight = 0.0

            # 归一化 anomaly_score (假设正常范围 0-5)
            normalized_anomaly = min(max(anomaly_signal.anomaly_score, 0.0) / 5.0, 1.0)

            # 归一化 symbol_weight (假设正常范围 0-5)
            normalized_symbol = min(max(symbol_weight, 0.0) / 5.0, 1.0)

            # 限制 block_hotspot 和 global_hotspot 范围
            avg_block_hotspot = max(0.0, min(1.0, avg_block_hotspot))
            global_hotspot = max(0.0, min(1.0, global_hotspot))

            score = (
                normalized_anomaly * self._anomaly_weight +
                normalized_symbol * self._symbol_weight +
                avg_block_hotspot * self._block_weight +
                global_hotspot * self._global_weight
            )

            return max(0.0, min(1.0, score))
        except Exception:
            return 0.0
    
    def _should_trigger_pytorch(
        self,
        symbol: str,
        trigger_score: float,
        timestamp: float
    ) -> bool:
        """判断是否应该触发 PyTorch - 降低阈值版本"""
        # 检查冷却期
        last_trigger = self._trigger_cooldown.get(symbol, 0)
        if timestamp - last_trigger < self._cooldown_period:
            return False
        
        # 检查触发分数阈值 - 从 0.5 降低到 0.3，更容易触发
        if trigger_score < 0.3:
            return False
        
        # 更新冷却时间
        self._trigger_cooldown[symbol] = timestamp
        self._trigger_count += 1
        
        return True
    
    async def process_pytorch_batch(self) -> List[PatternSignal]:
        """处理 PyTorch 批量推理"""
        return await self.pytorch.process_batch()
    
    def get_trigger_summary(self) -> Dict[str, Any]:
        """获取触发摘要"""
        return {
            'trigger_count': self._trigger_count,
            'river_stats': self.river.get_stats(),
            'pytorch_stats': self.pytorch.get_stats()
        }
    
    def reset(self):
        """重置协调器"""
        self.river.reset()
        self.pytorch.reset()
        self._trigger_cooldown.clear()
        self._trigger_count = 0