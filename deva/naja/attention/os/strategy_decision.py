"""
StrategyDecisionMaker - 策略决策器

Attention OS 应用层，基于 AttentionKernel 的决策进行策略执行判断。

从 attention_os.py 拆分出来。
"""

import logging
from typing import Dict, Any, List

from ..models.output import AttentionKernelOutput

log = logging.getLogger(__name__)


class StrategyDecisionMaker:
    """
    策略决策器 - Attention OS 应用层

    职责：
    - 基于 AttentionKernel 的决策进行策略执行判断
    - 决定是否应该执行交易策略
    - 时机选择和置信度评估

    依托 AttentionKernel 获取和谐度、时机评分和置信度
    """

    def __init__(self, kernel):
        self.kernel = kernel

        self._block_weights: Dict[str, float] = {}
        self._symbol_weights: Dict[str, float] = {}
        self._frequency_level: str = "medium"
        self._strategy_allocations: Dict[str, float] = {}
        self._last_schedule_time: float = 0.0
        self._schedule_interval: float = 60.0

    def schedule(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行市场调度

        Args:
            market_data: 市场数据

        Returns:
            调度结果
        """
        import time
        current_time = time.time()

        kernel_output = self.kernel.make_decision(market_data)

        harmony_strength = kernel_output.harmony_strength
        should_act = kernel_output.should_act
        action_type = kernel_output.action_type

        timing_score = kernel_output.timing_score
        regime_score = kernel_output.regime_score
        confidence_score = kernel_output.confidence_score

        self._adjust_frequency(harmony_strength, timing_score, regime_score, current_time)

        # 获取上下文学习信息并添加到market_data中
        kernel_output_dict = kernel_output.to_dict()
        in_context_info = kernel_output_dict.get("_in_context", {})
        market_data_with_context = market_data.copy()
        if in_context_info:
            market_data_with_context["_in_context"] = in_context_info

        self._allocate_weights(market_data_with_context, kernel_output)

        self._allocate_strategies(kernel_output, market_data_with_context)

        self._last_schedule_time = current_time

        return {
            "block_weights": self._block_weights,
            "symbol_weights": self._symbol_weights,
            "strategy_allocations": self._strategy_allocations,
            "frequency_level": self._frequency_level,
            "schedule_interval": self._schedule_interval,
            "should_act": should_act,
            "action_type": action_type,
            "harmony_strength": harmony_strength,
            "timing_score": timing_score,
            "regime_score": regime_score,
            "confidence_score": confidence_score,
            "in_context_info": in_context_info,
            "kernel_output": kernel_output_dict,
        }

    def _adjust_frequency(
        self,
        harmony_strength: float,
        timing_score: float = 0.5,
        regime_score: float = 0.0,
        current_time: float = 0.0
    ):
        """
        根据和谐强度和其他因素调整频率

        频率等级：
        - high: harmony > 0.7 且时机好 → 1-5秒
        - medium: harmony 0.4-0.7 → 30-60秒
        - low: harmony < 0.4 或时机差 → 5-10分钟
        """
        composite_score = (
            harmony_strength * 0.5 +
            timing_score * 0.3 +
            (1.0 if regime_score > 0 else 0.3) * 0.2
        )

        if composite_score > 0.75:
            self._frequency_level = "high"
            self._schedule_interval = 1.0 + (1.0 - composite_score) * 4.0
        elif composite_score > 0.5:
            self._frequency_level = "medium"
            self._schedule_interval = 30.0 + (1.0 - composite_score) * 60.0
        elif composite_score > 0.25:
            self._frequency_level = "low"
            self._schedule_interval = 300.0 + (0.5 - composite_score) * 600.0
        else:
            self._frequency_level = "ultra_low"
            self._schedule_interval = 600.0

        self._schedule_interval = max(1.0, min(600.0, self._schedule_interval))

    def _allocate_weights(self, market_data: Dict[str, Any], kernel_output: AttentionKernelOutput):
        """分配个股权重和题材权重（支持多 blocks）"""
        base_weights = market_data.get("symbol_weights", {})
        block_hotspot = market_data.get("block_hotspot", {})

        if not base_weights:
            log.debug(f"[StrategyDecisionMaker] 警告: market_data 中没有 symbol_weights")
            return

        alpha = kernel_output.alpha
        harmony = kernel_output.harmony_strength
        confidence = kernel_output.confidence_score

        # 从kernel_output中获取上下文学习信息
        in_context_info = market_data.get("_in_context", {})
        
        self._symbol_weights = {}
        self._block_weights = {}

        block_totals: Dict[str, float] = {}

        for symbol, base_weight in base_weights.items():
            attention_weight = kernel_output.attention_weights.get(symbol, 0.5)
            
            # 计算最终权重，考虑上下文学习的调整
            final_weight = base_weight * attention_weight * alpha * harmony * confidence
            
            # 如果有上下文学习的调整信息，应用到权重中
            if in_context_info:
                # 基于历史成功经验调整权重
                historical_success = in_context_info.get("historical_success", 1.0)
                final_weight *= (1.0 + historical_success * 0.2)
                
                # 基于相关示范数量调整权重
                num_demos = in_context_info.get("num_demos", 0)
                if num_demos > 0:
                    final_weight *= (1.0 + num_demos * 0.1)

            self._symbol_weights[symbol] = max(0.0, min(1.0, final_weight))

            blocks = self._get_symbol_blocks(symbol, block_hotspot)
            if not blocks:
                blocks = ["other"]
            weight_per_block = final_weight / len(blocks)
            for block in blocks:
                if block not in block_totals:
                    block_totals[block] = 0.0
                block_totals[block] += weight_per_block

        for block, total in block_totals.items():
            self._block_weights[block] = min(1.0, total / max(1, len(block_totals)))

    def _get_symbol_blocks(self, symbol: str, block_hotspot: Dict[str, float]) -> List[str]:
        """根据个股代码和题材热点确定该个股属于哪些题材"""
        blocks = []
        symbol_upper = symbol.upper()
        for block_name in block_hotspot.keys():
            if block_name.upper() in symbol_upper or any(c in symbol_upper for c in ['AI', 'TECH', 'FIN', 'MED', 'ENE', 'CON']):
                blocks.append(block_name)
        return blocks if blocks else list(block_hotspot.keys())[:3]

    def _allocate_strategies(
        self,
        kernel_output: AttentionKernelOutput,
        market_data: Dict[str, Any]
    ):
        """
        分配策略执行权重

        根据 action_type 和市场状态决定策略分配
        """
        action_type = kernel_output.action_type
        harmony = kernel_output.harmony_strength
        timing = kernel_output.timing_score
        regime = kernel_output.regime_score

        # 获取上下文学习信息
        in_context_info = market_data.get("_in_context", {})

        self._strategy_allocations = {}

        if action_type == "hold":
            self._strategy_allocations = {
                "momentum": 0.1,
                "mean_reversion": 0.1,
                "breakout": 0.0,
                "grid": 0.2,
                "wait": 0.6,
            }
        elif action_type in ("act_fully", "buy", "long"):
            if harmony > 0.8 and timing > 0.7:
                self._strategy_allocations = {
                    "momentum": 0.5,
                    "breakout": 0.3,
                    "mean_reversion": 0.1,
                    "grid": 0.0,
                    "wait": 0.1,
                }
            elif harmony > 0.6:
                self._strategy_allocations = {
                    "momentum": 0.3,
                    "breakout": 0.2,
                    "mean_reversion": 0.2,
                    "grid": 0.1,
                    "wait": 0.2,
                }
            else:
                self._strategy_allocations = {
                    "momentum": 0.2,
                    "breakout": 0.1,
                    "mean_reversion": 0.3,
                    "grid": 0.2,
                    "wait": 0.2,
                }
        elif action_type in ("act_carefully", "sell", "short"):
            self._strategy_allocations = {
                "momentum": 0.1,
                "mean_reversion": 0.4,
                "breakout": 0.0,
                "grid": 0.3,
                "wait": 0.2,
            }
        elif action_type == "act_minimally":
            self._strategy_allocations = {
                "momentum": 0.15,
                "mean_reversion": 0.25,
                "breakout": 0.1,
                "grid": 0.25,
                "wait": 0.25,
            }
        else:
            self._strategy_allocations = {
                "momentum": 0.2,
                "mean_reversion": 0.2,
                "breakout": 0.1,
                "grid": 0.2,
                "wait": 0.3,
            }

        regime_factor = 1.0 + regime * 0.2
        
        # 根据上下文学习信息调整策略分配
        if in_context_info:
            # 基于历史成功经验调整策略权重
            historical_success = in_context_info.get("historical_success", 0.0)
            if historical_success > 0.1:
                # 历史成功时，增加动量策略的权重
                if "momentum" in self._strategy_allocations:
                    self._strategy_allocations["momentum"] *= (1.0 + historical_success * 0.3)
                if "breakout" in self._strategy_allocations:
                    self._strategy_allocations["breakout"] *= (1.0 + historical_success * 0.2)
            
            # 基于相关示范数量调整策略权重
            num_demos = in_context_info.get("num_demos", 0)
            if num_demos > 1:
                # 有多个相关示范时，增加策略的确定性
                if "wait" in self._strategy_allocations:
                    self._strategy_allocations["wait"] *= 0.8  # 减少等待策略的权重
        
        # 应用市场状态因子
        for k in self._strategy_allocations:
            self._strategy_allocations[k] *= regime_factor
            self._strategy_allocations[k] = min(1.0, self._strategy_allocations[k])
        
        # 归一化策略权重
        total_weight = sum(self._strategy_allocations.values())
        if total_weight > 0:
            for k in self._strategy_allocations:
                self._strategy_allocations[k] /= total_weight

    def get_frequency_config(self) -> Dict[str, Any]:
        """获取频率配置"""
        return {
            "level": self._frequency_level,
            "interval_seconds": self._schedule_interval,
        }

    def get_top_symbols(self, n: int = 10) -> List[Dict[str, Any]]:
        """获取权重最高的 n 只股票"""
        sorted_weights = sorted(
            self._symbol_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [
            {"symbol": sym, "weight": wgt}
            for sym, wgt in sorted_weights[:n]
        ]

    def get_top_blocks(self, n: int = 5) -> List[Dict[str, Any]]:
        """获取权重最高的 n 个 block"""
        sorted_weights = sorted(
            self._block_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [
            {"block": blk, "weight": wgt}
            for blk, wgt in sorted_weights[:n]
        ]
