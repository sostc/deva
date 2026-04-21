"""
River 策略封装器

集成以下功能：
1. 模型持久化
2. LLM 参数调节
3. 状态管理
4. 信号输出增强
5. HTML 可视化

使用方式:
    from deva.naja.strategy.river_wrapper import (
        RiverStrategyWrapper,
        create_strategy,
    )

    # 创建策略
    strategy = create_strategy(
        name="early_trend",
        handler_type="radar",
        enable_persist=True,
        enable_llm=True,
    )
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from deva import NB

from .advanced_river_strategies import (
    EarlyTrendDetector,
    StockSelector,
    get_strategy as get_advanced_strategy,
)
from .bandit_stock_strategies import (
    BlockStockSelector,
    EarlyBullFinder,
    get_selector as get_bandit_strategy,
)
from .model_persist import get_model_manager
from .llm_controller import get_tuner


STRATEGY_MAP = {
    "early_trend": (EarlyTrendDetector, "radar"),
    "stock_selector": (StockSelector, "radar"),
    "block_stock_selector": (BlockStockSelector, "bandit"),
    "early_bull": (EarlyBullFinder, "bandit"),
}


class RiverStrategyWrapper:
    """River 策略封装器

    提供:
    - 模型持久化
    - LLM 参数调节
    - 状态管理
    - 信号增强
    """

    def __init__(
        self,
        strategy_name: str,
        strategy_id: str = "",
        handler_type: str = "radar",
        enable_persist: bool = True,
        enable_llm: bool = True,
        **strategy_kwargs,
    ):
        self.strategy_name = strategy_name
        self.strategy_id = strategy_id or f"strategy_{int(time.time())}"
        self.handler_type = handler_type
        self.enable_persist = enable_persist
        self.enable_llm = enable_llm
        self.strategy_kwargs = strategy_kwargs

        self._strategy = None
        self._model_manager = None
        self._tuner = None
        self._last_signal = None

        self._init_strategy()

    def _init_strategy(self) -> None:
        """初始化策略"""
        strategy_info = STRATEGY_MAP.get(self.strategy_name)
        if not strategy_info:
            raise ValueError(f"Unknown strategy: {self.strategy_name}")

        strategy_class, self.handler_type = strategy_info
        self._strategy = strategy_class(**self.strategy_kwargs)

        if self.enable_persist:
            self._model_manager = get_model_manager(self.strategy_id)

        if self.enable_llm:
            self._tuner = get_tuner(self.strategy_id)
            self._tuner.register_validator("sensitivity", lambda v: 0 <= v <= 1)
            self._tuner.register_validator("threshold", lambda v: 0 <= v <= 1)
            self._tuner.register_validator("top_n", lambda v: 1 <= v <= 20)

    def on_data(self, data: Any) -> None:
        """处理数据"""
        if self._strategy is None:
            return

        self._strategy.on_data(data)

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        if self._strategy is None:
            return None

        signal = self._strategy.get_signal()
        if signal is None:
            return None

        signal["strategy_id"] = self.strategy_id
        signal["strategy_name"] = self.strategy_name
        signal["handler_type"] = self.handler_type

        self._last_signal = signal
        return signal

    def update_params(self, params: Dict) -> None:
        """更新参数"""
        if self._strategy is None:
            return

        self._strategy.update_params(params)

        if self.enable_persist and self._model_manager:
            state = self.get_state()
            self._model_manager.save(state, metadata={"params": params})

    def get_state(self) -> Dict:
        """获取状态"""
        if self._strategy is None:
            return {}

        state = {}
        if hasattr(self._strategy, "get_state"):
            state = self._strategy.get_state()

        return {
            "strategy_name": self.strategy_name,
            "strategy_id": self.strategy_id,
            "handler_type": self.handler_type,
            "strategy_state": state,
            "timestamp": time.time(),
        }

    def set_state(self, state: Dict) -> None:
        """设置状态"""
        if self._strategy is None:
            return

        strategy_state = state.get("strategy_state", {})
        if hasattr(self._strategy, "set_state"):
            self._strategy.set_state(strategy_state)

    def save_model(self) -> str:
        """保存模型"""
        if not self.enable_persist or not self._model_manager:
            return ""

        state = self.get_state()
        version_id = self._model_manager.save(state)
        return version_id

    def load_model(self, version_id: Optional[str] = None) -> bool:
        """加载模型"""
        if not self.enable_persist or not self._model_manager:
            return False

        state = self._model_manager.load(version_id)
        if state:
            self.set_state(state)
            return True
        return False

    def reset(self) -> None:
        """重置策略"""
        if hasattr(self._strategy, "reset"):
            self._strategy.reset()

    def tune_with_llm(
        self,
        signal: Dict,
        llm_client: Optional[callable] = None,
    ) -> Dict:
        """使用 LLM 调节参数"""
        if not self.enable_llm or not self._tuner:
            return {}

        current_params = self._extract_current_params()

        result = self._tuner.tune_params(
            signal=signal,
            current_params=current_params,
            llm_client=llm_client,
        )

        if result.success:
            for change in result.applied_changes:
                self.update_params({change.param_name: change.new_value})

        return {
            "applied": [
                {"param": c.param_name, "value": c.new_value}
                for c in result.applied_changes
            ],
            "rejected": [
                {"param": c.param_name, "value": c.new_value}
                for c in result.rejected_changes
            ],
            "llm_response": result.llm_response,
        }

    def _extract_current_params(self) -> Dict:
        """提取当前参数"""
        params = {}

        if hasattr(self._strategy, "_sensitivity"):
            params["sensitivity"] = self._strategy._sensitivity
        if hasattr(self._strategy, "_top_n"):
            params["top_n"] = self._strategy._top_n
        if hasattr(self._strategy, "_min_score"):
            params["min_score"] = self._strategy._min_score
        if hasattr(self._strategy, "_min_price"):
            params["min_price"] = self._strategy._min_price
        if hasattr(self._strategy, "_min_volume"):
            params["min_volume"] = self._strategy._min_volume
        if hasattr(self._strategy, "_window_size"):
            params["window_size"] = self._strategy._window_size

        return params

    def close(self) -> None:
        """关闭并保存"""
        if self.enable_persist:
            self.save_model()


def create_strategy(
    name: str,
    strategy_id: str = "",
    handler_type: str = "radar",
    enable_persist: bool = True,
    enable_llm: bool = True,
    **kwargs,
) -> RiverStrategyWrapper:
    """创建策略的便捷函数"""
    return RiverStrategyWrapper(
        strategy_name=name,
        strategy_id=strategy_id,
        handler_type=handler_type,
        enable_persist=enable_persist,
        enable_llm=enable_llm,
        **kwargs,
    )


def get_available_strategies() -> List[Dict]:
    """获取可用策略列表"""
    return [
        {
            "name": name,
            "handler_type": info[1],
            "class": info[0].__name__,
        }
        for name, info in STRATEGY_MAP.items()
    ]
