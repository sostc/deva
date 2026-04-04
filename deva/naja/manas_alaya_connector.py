"""
ManasAlayaConnector - ManasEngine 与 AwakenedAlaya 连接器

将 ManasEngine 的决策输出传递给 AwakenedAlaya，触发持仓顿悟
同时触发 WisdomRetriever，从爸爸的知识库中检索相关文章
"""

import logging
from typing import Dict, Any, Optional

from .alaya.awakened_alaya import AwakenedAlaya
from .alaya.epiphany_engine import EpiphanyEngine
from .wisdom.wisdom_retriever import WisdomRetriever, TriggerContext

log = logging.getLogger(__name__)


_connector: Optional["ManasAlayaConnector"] = None


def get_connector() -> "ManasAlayaConnector":
    """获取全局 ManasAlayaConnector 单例"""
    global _connector
    if _connector is None:
        _connector = ManasAlayaConnector()
    return _connector


class ManasAlayaConnector:
    """
    ManasEngine 与 AwakenedAlaya 连接器

    数据流：
    1. ManasEngine.compute() → 决策输出
    2. 将输出传递给 AwakenedAlaya.illuminate()
    3. 触发持仓顿悟
    4. 返回完整的决策+顿悟结果
    """

    def __init__(self):
        from deva.naja.attention.trading_center import get_trading_center
        tc = get_trading_center()
        self._manas_engine = tc.get_attention_os().kernel.get_manas_engine()

        self._alaya = AwakenedAlaya()
        self._epiphany_engine = EpiphanyEngine()
        self._wisdom_retriever = WisdomRetriever()

        self._alaya.set_epiphany_engine(self._epiphany_engine)

        self._last_combined_result: Optional[Dict[str, Any]] = None

    def compute(
        self,
        portfolio_data: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
        scanner=None,
        session_manager=None,
        bandit_tracker=None,
        macro_signal: float = 0.5
    ) -> Dict[str, Any]:
        """
        完整计算流程

        Args:
            portfolio_data: 持仓数据
            market_data: 市场数据
            scanner: GlobalMarketScanner
            session_manager: TradingClock/MarketSessionManager
            bandit_tracker: BanditPositionTracker
            macro_signal: 宏观流动性信号

        Returns:
            包含 manas_output, alaya_output, combined_result 的字典
        """
        manas_output = self._manas_engine.compute(
            portfolio=portfolio_data or {},
            scanner=scanner,
            session_manager=session_manager,
            bandit_tracker=bandit_tracker,
            macro_signal=macro_signal,
            narratives=market_data.get("narratives", []) if market_data else []
        )

        manas_dict = manas_output.to_dict()

        alaya_output = self._alaya.illuminate(
            market_data=market_data or {},
            unified_manas_output=manas_dict
        )

        attention_focus_value = manas_dict.get("attention_focus", "unknown")
        if hasattr(attention_focus_value, 'value'):
            attention_focus_value = attention_focus_value.value

        combined = {
            "manas": manas_dict,
            "alaya": alaya_output,
            "attention_focus": attention_focus_value,
            "should_act": manas_output.should_act,
            "has_epiphany": alaya_output.get("portfolio_awakening") is not None,
            "epiphany_content": (alaya_output.get("portfolio_awakening").illumination_content
                                if alaya_output.get("portfolio_awakening") else "")
        }

        context = TriggerContext.from_manas_output(manas_dict)
        wisdom_result = self._wisdom_retriever.retrieve(context)
        combined["wisdom"] = wisdom_result

        if wisdom_result.get("should_speak"):
            combined["wisdom_to_speak"] = wisdom_result.get("best_snippet")
            log.info(f"[ManasAlayaConnector] Wisdom triggered: {wisdom_result.get('query')}")

        self._last_combined_result = combined

        log.info(f"[ManasAlayaConnector] focus={attention_focus_value}, "
                 f"should_act={manas_output.should_act}, "
                 f"epiphany={combined['has_epiphany']}")

        return combined

    def record_feedback(
        self,
        outcome: Dict[str, Any],
        market_data: Optional[Dict[str, Any]] = None
    ):
        """记录反馈到闭环"""
        pass

    def get_manas_engine(self):
        """获取 ManasEngine 实例"""
        return self._manas_engine

    def get_alaya(self) -> AwakenedAlaya:
        """获取 AwakenedAlaya 实例"""
        return self._alaya

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        """获取最近一次计算结果"""
        return self._last_combined_result

    def get_wisdom_retriever(self) -> WisdomRetriever:
        """获取 WisdomRetriever 实例"""
        return self._wisdom_retriever

    def get_wisdom_stats(self) -> Dict[str, Any]:
        """获取 wisdom 统计信息"""
        return self._wisdom_retriever.get_stats()
