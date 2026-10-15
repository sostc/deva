"""
ManasManager - 末那识引擎管理器

管理 ManasEngine 的生命周期和状态

使用方式：
    manager = ManasManager(kernel)
    manager.set_enabled(True)

    # 在主循环中调用
    manas_output = manager.compute()
"""

import time
import logging
from typing import Optional

from .manas_engine import ManasEngine

log = logging.getLogger(__name__)


class ManasManager:
    """
    末那识引擎管理器

    管理 ManasEngine 的生命周期和状态

    使用方式：
        # 方式1: 独立模式（推荐）
        manager = ManasManager()
        manager.set_enabled(True)

        # 在主循环中调用
        manas_output = manager.compute()
    """

    def __init__(self, kernel=None, trading_clock=None, virtual_portfolio=None, bandit_tracker=None):
        self.kernel = kernel
        self._trading_clock = trading_clock
        self._virtual_portfolio = virtual_portfolio
        self._bandit_tracker = bandit_tracker
        self._manas_engine = None
        self._enabled = False
        self._last_compute_time = 0.0
        self._last_output: Optional[dict] = None

    def set_trading_clock(self, trading_clock):
        """显式设置 TradingClock（依赖注入）"""
        self._trading_clock = trading_clock

    def set_virtual_portfolio(self, virtual_portfolio):
        """显式设置 VirtualPortfolio（依赖注入）"""
        self._virtual_portfolio = virtual_portfolio

    def set_bandit_tracker(self, bandit_tracker):
        """显式设置 BanditTracker（依赖注入）"""
        self._bandit_tracker = bandit_tracker

    def set_enabled(self, enabled: bool):
        """
        设置是否启用末那识引擎

        Args:
            enabled: 是否启用
        """
        if enabled and not self._enabled:
            self._enabled = True
            if self.kernel is not None:
                # 兼容 OSAttentionKernel（无 set_manas_enabled）和标准 AttentionKernel
                if hasattr(self.kernel, 'set_manas_enabled'):
                    self.kernel.set_manas_enabled(True)
                # OSAttentionKernel 内部已持有 ManasEngine，通过 get_manas_engine 获取
                if hasattr(self.kernel, 'get_manas_engine'):
                    self._manas_engine = self.kernel.get_manas_engine()
            else:
                self._manas_engine = ManasEngine(
                    session_manager=self._trading_clock,
                    portfolio=self._virtual_portfolio,
                    bandit_tracker=self._bandit_tracker
                )

            # 引擎就绪后再挂事件总线：ManasEngine 构造期不再自订阅，
            # 这里是离创建点最近的装配位置（幂等，重复调用无副作用）
            self._attach_event_bus()
            log.info("[ManasManager] 末那识引擎已启用")
        elif not enabled:
            self._enabled = False
            if self.kernel is not None and hasattr(self.kernel, 'set_manas_enabled'):
                self.kernel.set_manas_enabled(False)
            log.info("[ManasManager] 末那识引擎已关闭")

    def _attach_event_bus(self) -> bool:
        """把当前引擎挂到认知事件总线（幂等）

        ManasEngine 的事件订阅已按架构基准 §6.3 移出构造函数，因此启用引擎后
        必须显式挂载一次；否则 _cognitive_state 不会随认知事件更新，
        叙事风险 / 共振分数 / AI 算力趋势会一直停在默认值。
        """
        engine = self.get_manas_engine()
        if engine is None:
            log.warning("[ManasManager] 引擎未就绪，跳过事件订阅")
            return False
        if not hasattr(engine, "subscribe_cognitive_events"):
            log.warning("[ManasManager] 引擎不支持 subscribe_cognitive_events，跳过")
            return False
        return bool(engine.subscribe_cognitive_events())

    def is_enabled(self) -> bool:
        """返回是否启用了末那识引擎"""
        return self._enabled
    
    def get_manas_engine(self) -> Optional[ManasEngine]:
        """
        获取 ManasEngine 实例
        
        Returns:
            ManasEngine 实例或 None
        """
        if self.kernel is not None:
            if hasattr(self.kernel, 'get_manas_engine'):
                return self.kernel.get_manas_engine()
            return None
        return self._manas_engine

    def compute(self) -> Optional[dict]:
        """
        计算末那识输出

        Returns:
            ManasOutput dict 或 None（如果未启用）
        """
        if not self._enabled:
            return None

        current_time = time.time()
        if current_time - self._last_compute_time < 1.0 and self._last_output is not None:
            return self._last_output

        if self.kernel is not None:
            manas_engine = self.kernel.get_manas_engine()
        else:
            manas_engine = self._manas_engine

        if manas_engine is None:
            return None

        # 与内核打分路径共用同一套输入（P1.4）：持有 kernel 时一律走
        # kernel.get_manas_inputs()，避免「一个引擎两种喂法」——
        # 历史问题：内核侧 portfolio=None / session_manager=TradingClock，
        # manager 侧传真实对象，两边结论可能不一致。
        if self.kernel is not None and hasattr(self.kernel, "get_manas_inputs"):
            inputs = dict(self.kernel.get_manas_inputs())
        else:
            inputs = {
                "session_manager": self._get_session_manager(),
                "portfolio": self._get_portfolio(),
                "scanner": self._get_scanner(),
                "bandit_tracker": self._get_bandit_tracker(),
            }

        # 宏观流动性：与内核打分路径**同一口径**（唯一出口见
        # ``kernel/macro_liquidity``）。❗此前这里恒传 0.5 —— 展示路径的
        # regime_score 因此恒 0（流动性分量 macro*2-1 ≡ 0），与内核路径结论
        # 不一致；而它又是行动门审计的主要写入者，会让「宏观流动性已进决策」
        # 在可观测层面证不出来。
        # ❗拿不到真值时**不传这个 kwarg**（而不是传 None）：ManasEngine 的
        #   形参默认值就是 0.5，而 None 会在 `macro_signal * 2 - 1` 处直接
        #   TypeError 炸掉整条链（_get_liquidity_signal 的 try 只包 scanner 分支）。
        kwargs = dict(inputs)
        macro_signal = self._get_macro_signal()
        if macro_signal is not None:
            kwargs["macro_signal"] = macro_signal

        output = manas_engine.compute(**kwargs)

        self._last_output = output.to_dict()
        self._last_compute_time = current_time

        return self._last_output

    def get_state(self) -> dict:
        """获取末那识引擎状态"""
        kernel_manas_enabled = False
        if self.kernel is not None:
            if hasattr(self.kernel, 'is_manas_enabled'):
                kernel_manas_enabled = self.kernel.is_manas_enabled()
            elif hasattr(self.kernel, 'get_manas_engine'):
                kernel_manas_enabled = self.kernel.get_manas_engine() is not None
        return {
            "enabled": self._enabled,
            "kernel_manas_enabled": kernel_manas_enabled,
            "last_output": self._last_output,
            # P2.1 行为偏差镜子：把 MetaManas 的内部纠偏乘子翻译成可读信号
            "bias": self._get_bias_state(),
            # P2.2 行动门留痕：按次可查「为什么不让你动」
            "gate_audit": self._get_gate_audit_summary(),
        }

    def _get_bias_state(self) -> dict:
        """读观照层的偏差状态（含给人看的教练语）。失败只降级为空 dict。"""
        try:
            engine = self.get_manas_engine()
            meta = getattr(engine, "meta_manas", None)
            if meta is None or not hasattr(meta, "get_state"):
                return {}
            return meta.get_state()
        except Exception as e:  # noqa: BLE001
            log.debug("[ManasManager] 读取行为偏差状态失败: %s", e)
            return {}

    def _get_gate_audit_summary(self, limit: int = 20) -> dict:
        """读行动门留痕的汇总与最近记录。失败只降级为空 dict。"""
        try:
            from .manas_gate_audit import get_gate_audit_log
            audit = get_gate_audit_log()
            return {"stats": audit.stats(), "recent": audit.recent(limit=limit)}
        except Exception as e:  # noqa: BLE001
            log.debug("[ManasManager] 读取行动门留痕失败: %s", e)
            return {}

    def _get_session_manager(self):
        """获取交易时段管理器

        ManasEngine 侧该依赖名为 session_manager（构造参数与 compute() 参数同名），
        因此这里的取数方法必须叫 _get_session_manager，与 compute() 的调用点保持一致。
        """
        return self._trading_clock

    def _get_portfolio(self):
        """获取虚拟持仓"""
        return self._virtual_portfolio

    def _get_bandit_tracker(self):
        """获取 bandit tracker"""
        return self._bandit_tracker

    def _get_scanner(self):
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            return get_global_market_scanner()
        except ImportError:
            return None

    def _get_macro_signal(self) -> Optional[float]:
        """取当前宏观流动性信号（QueryState，0~1），与决策路径**同一出处**。

        返回 ``None`` = 本次拿不到真值 → 调用方**不传该参数**，Manas 沿用默认
        0.5（中性）。刻意与「真值恰好是 0.5」区分开并留痕：拿不到是链路问题，
        不是「环境中性」。

        ❗历史 bug：这里曾硬编码 ``return 0.5``。展示路径（UI / 守望台 /
        ``/api/attention/manas/state``）因此永远看到「环境中性」，而它高频调用
        ``ManasEngine.compute()``、把行动门审计刷成 ``regime_score`` 恒 0.0 /
        折扣恒 0.85 —— 于是「宏观流动性到底进没进决策」在可观测层面根本证不出来。
        """
        from .macro_liquidity import read_macro_liquidity_signal, warn_missing

        value, why = read_macro_liquidity_signal()
        if value is None:
            warn_missing("ManasManager", why)
        return value


def get_manas_manager() -> Optional[ManasManager]:
    """获取全局末那识管理器"""
    # 从 AppContainer 获取
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container is not None:
        return container.manas_manager
    return None
