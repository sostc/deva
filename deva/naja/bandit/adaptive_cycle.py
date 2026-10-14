"""自适应循环控制器

将信号监听、虚拟持仓、市场观察和 Bandit 调节串联起来。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from deva import NB

from .signal_listener import SignalListener, DetectedSignal
from .virtual_portfolio import VirtualPortfolio, VirtualPosition
from .market_observer import MarketDataObserver, get_market_observer
from .optimizer import get_bandit_optimizer
from .data_freshness import get_freshness_tracker, SOURCE_CN_PRICE
from .execution import resolve_backend, selected_backend_name
from deva.naja.register import SR
from deva.naja.decision import compute_order_amount, manas_sizing_enabled

log = logging.getLogger(__name__)

ADAPTIVE_CONFIG_TABLE = "naja_bandit_adaptive_config"

# 自适应止盈止损的开关（默认开）。设 "0" 回滚为固定口径（-8% / +15%），
# 即 2026-10-15 修复前的事实行为 —— 那时 Manas 输入是假接的，风险温度恒 1.25。
ENV_MANAS_ADAPTIVE_SL = "NAJA_MANAS_ADAPTIVE_SL"


def manas_adaptive_sl_enabled() -> bool:
    """是否启用「按真实 Manas 风险上下文」自适应调整止盈止损。

    默认 **启用**（与 NAJA_T_ESTABLISH_GATE / NAJA_WATCH_MARKET_CLOCK 同款约定：
    默认生效，置 "0"/"false" 关闭）。
    """
    import os
    return str(os.environ.get(ENV_MANAS_ADAPTIVE_SL, "1")).strip().lower() \
        not in ("0", "false", "no", "off")


class AdaptiveCycle:
    """自适应循环控制器
    
    串联所有组件形成完整的交易循环：
    
    信号流 → SignalListener → 识别股票
                              ↓
                          虚拟持仓 (VirtualPortfolio)
                              ↓
                    MarketDataObserver 更新价格
                              ↓
                          检查止盈止损
                              ↓
                         平仓 → Bandit 更新
                              ↓
                    BanditOptimizer 调整策略参数
    """
    
    def __init__(self, signal_listener=None, portfolio=None, market_observer=None, optimizer=None, tracker=None, runner=None):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._db = NB(ADAPTIVE_CONFIG_TABLE)
        
        from .market_observer import get_market_observer
        from .optimizer import get_bandit_optimizer
        # 显式注入：AppContainer 传入全部依赖，此处 fallback 仅用于开发/单测
        self._signal_listener = signal_listener or self._get_signal_listener_fallback()
        self._portfolio = portfolio or self._get_portfolio_fallback()
        self._market_observer = market_observer or get_market_observer()
        self._optimizer = optimizer or get_bandit_optimizer()
        self._tracker = tracker or self._get_tracker_fallback()
        self._runner = runner or self._get_runner_fallback()
        
        self._auto_start = True
        self._auto_buy_enabled = True
        self._auto_adjust_enabled = True

        # 仓位定量：base 是"乘子=1.0"时的基准额（原固定量 10000），
        # 实际额 = base × DecisionPlan.size_hint（见 decision/sizing.py）。
        # min 避免乘子很小时算出买不起 1 股的金额。
        self._base_order_amount = 10000.0
        self._min_order_amount = 1000.0

        self._manas_context_cache: Optional[Dict[str, Any]] = None
        self._last_manas_update = 0.0
        self._manas_update_interval = 60.0

        self._state_restored = False

        self._load_config()
        self._setup_callbacks()

        if self._running:
            self._restore_running_state()
    
    def _get_signal_listener_fallback(self):
        """SR() fallback 仅用于开发/单测"""
        from deva.naja.register import SR
        return SR('signal_listener')
    
    def _get_portfolio_fallback(self):
        from deva.naja.register import SR
        return SR('virtual_portfolio')
    
    def _get_tracker_fallback(self):
        from deva.naja.register import SR
        return SR('bandit_tracker')
    
    def _get_runner_fallback(self):
        from deva.naja.register import SR
        return SR('bandit_runner')
    
    def _restore_running_state(self):
        """恢复运行状态，重新追踪已持仓的股票"""
        if self._state_restored:
            log.debug("状态已恢复，跳过")
            return

        try:
            positions = self._portfolio.get_all_positions(status="OPEN")
            stock_codes = [pos.stock_code for pos in positions]
            if stock_codes:
                self._market_observer.track_stocks_batch(stock_codes)

            if self._signal_listener._running and not self._signal_listener._thread:
                self._signal_listener.start()
            if self._market_observer._running and not getattr(self._market_observer, '_thread', None):
                self._market_observer.start()
            if self._runner._running and not self._runner._thread:
                self._runner.start()

            self._state_restored = True
            log.info(f"✓ Bandit 恢复完成: 持仓({len(positions)})")
        except Exception as e:
            log.error(f"恢复运行状态失败: {e}")
    
    def _load_config(self):
        """加载配置"""
        try:
            config = self._db.get("adaptive_config")
            if config:
                self._auto_start = config.get("auto_start", True)
                self._auto_buy_enabled = config.get("auto_buy_enabled", True)
                self._auto_adjust_enabled = config.get("auto_adjust_enabled", True)
                
                if config.get("was_running", False) and self._auto_start:
                    self._running = True
                    log.debug("检测到上次运行状态为运行中，将自动启动")
        except Exception:
            pass
    
    def _save_config(self):
        """保存配置"""
        try:
            self._db["adaptive_config"] = {
                "auto_start": self._auto_start,
                "auto_buy_enabled": self._auto_buy_enabled,
                "auto_adjust_enabled": self._auto_adjust_enabled,
                "was_running": self._running
            }
        except Exception:
            pass

    def _get_manas_risk_context(self) -> Dict[str, Any]:
        """获取 Manas 的风险上下文，用于调整止盈止损

        数据来源（❗2026-10-15 修复前的写法是**假接**，见下）：
          复用内核的**单出口** `OSAttentionKernel.get_manas_inputs()` ——
          内核打分路径与 ManasManager 展示路径共用这一份输入，避免
          「同一个引擎被两种喂法喂出两个结论」。持仓兜底用本周期自己的
          `self._portfolio`（装配期由容器注入的 `virtual_portfolio` 单例，
          与内核拿到的是同一个对象）。

        Returns:
            {
                "risk_temperature": float,
                "timing_score": float,
                "regime_score": float,
                "harmony_strength": float,
            }

        ❗修复前的实际后果（比「全返 0」更精确）：
          `portfolio` 传的是**一个 dict**，而 `RiskEngine` 期望 VirtualPortfolio
          并按 `portfolio.get_summary()` 取数 → dict 无此方法 → AttributeError
          被 `_get_cash_ratio` 内的 except 吞掉 → `cash_ratio ≡ 0.5`、
          `drawdown ≡ 0`；`scanner=None` → `volatility ≡ 1.0`。
          于是 `base_T = 1 + (1-0.5)*0.5 = 1.25`，**risk_temperature 恒 1.25** ——
          永远落不进 `> 1.3` / `> 1.5` 两档，`_get_adaptive_stop_loss` 恒走
          else 分支，**「自适应」止盈止损从未生效过一次**（恒 -8% / +15%）。
        """
        current_time = time.time()

        if (current_time - self._last_manas_update < self._manas_update_interval
                and self._manas_context_cache is not None):
            return self._manas_context_cache

        if not manas_adaptive_sl_enabled():
            # 回滚开关：用于灰度/回滚。此时不读 Manas，直接返回固定口径，
            # 等价于改造前的行为（-8% / +15% 那一路）。
            return {
                "risk_temperature": 1.0,
                "timing_score": 0.5,
                "regime_score": 0.0,
                "harmony_strength": 0.5,
            }

        try:
            from deva.naja.attention.orchestration.trading_center import get_trading_center
            tc = get_trading_center()
            kernel = tc.get_attention_os().kernel
            manas_engine = kernel.get_manas_engine()

            # 单出口：与内核打分路径共用同一份输入（session_manager / portfolio /
            # scanner / bandit_tracker）。取不到就如实退化为 None，由引擎各自的
            # 兜底处理 —— 但**不再编造**一个假持仓。
            manas_inputs: Dict[str, Any] = {}
            if hasattr(kernel, "get_manas_inputs"):
                manas_inputs = dict(kernel.get_manas_inputs())

            if manas_inputs.get("portfolio") is None:
                manas_inputs["portfolio"] = self._portfolio

            manas_output = manas_engine.compute(
                macro_signal=0.5,
                narratives=self._current_narratives_for_manas(),
                **manas_inputs,
            )

            self._manas_context_cache = {
                "risk_temperature": manas_output.risk_temperature,
                "timing_score": manas_output.timing_score,
                "regime_score": manas_output.regime_score,
                "harmony_strength": manas_output.harmony_strength,
            }
            self._last_manas_update = current_time

            log.debug(
                "[AdaptiveCycle] Manas 上下文已刷新: risk_t=%.3f timing=%.3f "
                "regime=%.3f harmony=%.3f | 输入 portfolio=%s session=%s scanner=%s",
                manas_output.risk_temperature, manas_output.timing_score,
                manas_output.regime_score, manas_output.harmony_strength,
                type(manas_inputs.get("portfolio")).__name__ if manas_inputs.get("portfolio") else None,
                type(manas_inputs.get("session_manager")).__name__ if manas_inputs.get("session_manager") else None,
                type(manas_inputs.get("scanner")).__name__ if manas_inputs.get("scanner") else None,
            )

            return self._manas_context_cache
        except Exception as e:
            # 失败时退回固定口径（= 改造前行为），并**明确告警**：不能静默。
            log.warning(f"[AdaptiveCycle] 获取 Manas 上下文失败，本次退回固定止盈止损口径: {e}")
            return {
                "risk_temperature": 1.0,
                "timing_score": 0.5,
                "regime_score": 0.0,
                "harmony_strength": 0.5,
            }

    def _get_adaptive_stop_loss(self, base_return_pct: float = 0.0) -> tuple:
        """
        根据 Manas 风险上下文获取自适应止盈止损

        Args:
            base_return_pct: 持仓当前收益率

        Returns:
            (stop_loss_pct, take_profit_pct)
        """
        manas_context = self._get_manas_risk_context()
        risk_t = manas_context["risk_temperature"]
        timing = manas_context["timing_score"]

        base_stop_loss = -8.0
        base_take_profit = 15.0

        if risk_t > 1.5:
            stop_loss = base_stop_loss * 0.4
            take_profit = base_take_profit * 0.6
            log.warning(f"[AdaptiveCycle] 极高风险环境: stop_loss={stop_loss}%, take_profit={take_profit}%")
        elif risk_t > 1.3:
            stop_loss = base_stop_loss * 0.6
            take_profit = base_take_profit * 0.8
            log.info(f"[AdaptiveCycle] 高风险环境: stop_loss={stop_loss}%, take_profit={take_profit}%")
        elif timing < 0.4:
            stop_loss = base_stop_loss * 1.5
            take_profit = base_take_profit * 0.7
            log.info(f"[AdaptiveCycle] 时机不佳: stop_loss={stop_loss}%, take_profit={take_profit}%")
        else:
            stop_loss = base_stop_loss
            take_profit = base_take_profit
            # ❗这一档以前**不打日志**：修复前 risk_t 恒 1.25 必然落在这里，
            # 于是「自适应止盈止损」看起来像在工作、实则每次都是同一对常数，
            # 而日志里一片安静。现在把「用了哪一档」显式记出来。
            log.info(
                "[AdaptiveCycle] 常规风险环境: stop_loss=%s%%, take_profit=%s%% "
                "(risk_t=%.3f, timing=%.3f)",
                stop_loss, take_profit, risk_t, timing,
            )

        if base_return_pct > 5.0:
            stop_loss = max(stop_loss, -10.0)

        return stop_loss, take_profit

    def _current_narratives_for_manas(self) -> List[str]:
        """从认知总线上读最近一次叙事状态，作为 Manas 的 `narratives` 入参。

        ❗这是**只读**回路：只取 `NarrativeTracker` 已发布的最新叙事名，
        不触发任何计算、不写任何状态。取不到就返回空列表（如实为空，
        不编造），Manas 侧会对空叙事给中性处理。
        """
        try:
            from deva.naja.events import get_event_bus
            latest = get_event_bus().get_latest_event("NarrativeStateEvent")
            if latest is None:
                return []
            return list(getattr(latest, "current_narratives", []) or [])
        except Exception as e:  # noqa: BLE001
            log.debug("[AdaptiveCycle] 读取当前叙事失败（按空处理）: %s", e)
            return []

    def _resolve_order_amount(self, decision: Dict[str, Any]) -> float:
        """按决策计划（``DecisionPlan.size_hint``）折算下单金额。

        - Manas 定量开启（默认）：``amount = base × size_hint``，带下限。
        - ``NAJA_MANAS_SIZING=0`` 时回落固定 ``base``——灰度与回滚用。
        - 决策**不带 plan**（TradingCenter 不可用的降级路径）→ 回落固定 ``base``，
          保持原行为，绝不因为"没拿到计划"就不建仓。
        - 带了 plan 但 ``size_hint=0``（hold）→ 返回 0，调用方跳过建仓。
        """
        base = getattr(self, "_base_order_amount", 10000.0)
        if not manas_sizing_enabled():
            log.debug("[AdaptiveCycle] Manas 定量已关闭，使用固定量 %s", base)
            return base
        plan = decision.get("plan")
        if not plan:
            log.debug("[AdaptiveCycle] 决策未附带 plan，回落固定量 %s", base)
            return base
        size_hint = plan.get("size_hint", 0.0)
        amount = compute_order_amount(size_hint, base, min_amount=getattr(self, "_min_order_amount", 0.0))
        log.info(f"[AdaptiveCycle] 仓位定量: size_hint={size_hint} × base={base} → amount={amount}")
        return amount

    def _request_trading_center_approval(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        请求 TradingCenter 对信号进行决策

        Args:
            signal: 信号字典

        Returns:
            决策结果，包含 approved, final_confidence, reasoning 等
            如果请求失败返回 None
        """
        try:
            from deva.naja.attention.orchestration.trading_center import get_trading_center
            tc = get_trading_center()
            if tc is None:
                log.warning("[AdaptiveCycle] TradingCenter 不可用")
                return None

            if not hasattr(tc, 'process_strategy_signal'):
                log.warning("[AdaptiveCycle] TradingCenter 不支持 process_strategy_signal 方法")
                return None

            decision = tc.process_strategy_signal(signal)
            return decision

        except Exception as e:
            log.warning(f"[AdaptiveCycle] 请求 TradingCenter 决策失败: {e}")
            return None

    def _setup_callbacks(self):
        """设置回调"""

        # 使用实例属性存储回调函数，避免重复注册
        if not hasattr(self, '_callbacks_registered'):
            self._callbacks_registered = False

        if self._callbacks_registered:
            log.debug("[AdaptiveCycle] 回调已注册，跳过")
            return

        def on_signal(signal: DetectedSignal):
            if self._auto_buy_enabled:
                self._on_new_signal(signal)

        self._signal_listener.register_callback(on_signal)

        def on_price_update(stock_code: str, price: float):
            log.debug(f"[AdaptiveCycle] 收到价格更新: {stock_code} @ {price}")
            self._on_price_update(stock_code, price)

        self._market_observer.register_price_callback(on_price_update)

        def on_position_close(position_id: str, position: VirtualPosition, reason: str):
            self._on_position_closed(position_id, position, reason)

        self._portfolio.register_close_callback(on_position_close)

        self._callbacks_registered = True
        log.debug("[AdaptiveCycle] 回调注册完成")
    
    def _execution_backend(self):
        """取本次要用的执行后端（进程内复用）。

        每个信号都重新装配后端的话，``FutuSimBackend`` 每次都会重建一个
        同步器并把 7 个品牌的账户列表重新探测一遍 —— 纯浪费，而且丢掉
        上一次连接缓存。后端名变了（环境变量被改）才重新装配。
        """
        name = selected_backend_name()
        cached = getattr(self, "_exec_backend", None)
        if cached is None or getattr(cached, "name", None) != name:
            cached = resolve_backend(portfolio=self._portfolio)
            self._exec_backend = cached
            log.info(f"[AdaptiveCycle] 执行后端 = {cached.name}")
        return cached

    def _on_new_signal(self, signal: DetectedSignal):
        """处理新信号"""
        log.debug(f"[AdaptiveCycle] 收到信号: {signal.stock_code} {signal.stock_name} 价格={signal.price} 置信度={signal.confidence}")

        signal_type_upper = signal.signal_type.upper()
        is_buy_signal = "BUY" in signal_type_upper or "买入" in signal_type_upper

        if not is_buy_signal:
            log.debug(f"[AdaptiveCycle] 信号类型不支持: {signal.signal_type}")
            return

        if signal.price <= 0:
            log.warning(f"[AdaptiveCycle] 信号价格无效: {signal.stock_code}")
            return

        positions = self._portfolio.get_positions_by_stock(signal.stock_code)
        if positions:
            log.debug(f"[AdaptiveCycle] 股票已有持仓，跳过: {signal.stock_code}")
            return

        signal_dict = {
            'strategy_id': signal.strategy_id,
            'strategy_name': signal.strategy_name,
            'stock_code': signal.stock_code,
            'stock_name': signal.stock_name,
            'signal_type': signal.signal_type,
            'price': signal.price,
            'confidence': signal.confidence,
            'timestamp': signal.timestamp,
            'raw_data': signal.raw_data,
        }

        decision = self._request_trading_center_approval(signal_dict)
        if not decision:
            log.debug(f"[AdaptiveCycle] TradingCenter 决策请求失败，使用原始信号")
            decision = {'approved': True, 'final_confidence': signal.confidence}

        if not decision.get('approved'):
            approved_confidence = decision.get('final_confidence', 0)
            reasoning = decision.get('reasoning', [])
            log.info(f"[AdaptiveCycle] ❌ TradingCenter 否决信号: {signal.stock_code} "
                    f"(confidence={approved_confidence:.3f})")
            for r in reasoning[-3:]:
                log.info(f"[AdaptiveCycle]   决策理由: {r}")
            return

        approved_confidence = decision.get('final_confidence', 0)
        harmony = decision.get('harmony_strength', 0.5)
        manas_score = decision.get('manas_score', 0.5)
        awakening = decision.get('awakening_level', 'dormant')
        log.info(f"[AdaptiveCycle] ✅ TradingCenter 批准信号: {signal.stock_code} "
                f"(confidence={approved_confidence:.3f}, harmony={harmony:.3f}, "
                f"manas={manas_score:.3f}, awakening={awakening})")

        log.info(f"[AdaptiveCycle] 准备创建持仓: {signal.stock_code} @ {signal.price}")

        amount = self._resolve_order_amount(decision)
        if amount <= 0:
            log.info(f"[AdaptiveCycle] ⏸ 决策计划未给出有效仓位（size_hint=0），跳过建仓: {signal.stock_code}")
            return

        stop_loss_pct, take_profit_pct = self._get_adaptive_stop_loss()
        log.info(f"[AdaptiveCycle] 自适应止盈止损: stop_loss={stop_loss_pct}%, take_profit={take_profit_pct}%")

        # 执行后端：默认 ``virtual``（写虚拟仓，与改造前完全一致）；
        # 设 ``NAJA_EXEC_BACKEND=futu_sim`` 才改报到富途模拟账户。
        outcome = self._execution_backend().submit(
            signal=signal,
            plan=decision.get("plan"),
            side="buy",                     # 上面已确认是买入信号
            price=signal.price,
            amount=amount,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

        # ❗「跳过」与「失败」必须分开报：跳过是链路好、只是某道闸没放行
        # （原因要透出）；失败是链路坏了。混成一个布尔会制造假警报，
        # 或者反过来把故障埋成"长期正常"。
        if not outcome.acted:
            if outcome.skipped:
                log.info(f"[AdaptiveCycle] ⏭ 执行跳过 [{outcome.backend}]: "
                         f"{signal.stock_code} —— {outcome.reason}")
            else:
                log.error(f"[AdaptiveCycle] ❌ 执行失败 [{outcome.backend}]: "
                          f"{signal.stock_code} —— {outcome.reason or outcome.detail}")
            return

        log.info(f"[AdaptiveCycle] 🎉 执行成功 [{outcome.backend}]! "
                 f"ID={outcome.position_id} {signal.stock_name}({signal.stock_code}) @ {signal.price}")

        self._market_observer.track_stock(signal.stock_code)

        try:
            from deva.naja.bandit.notifier import get_bandit_notifier
            notifier = get_bandit_notifier()
            notifier.notify_position_opened(
                position_id=outcome.position_id,
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                price=signal.price,
                amount=amount,
            )
            notifier.notify_buy_signal(
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                price=signal.price,
                confidence=signal.confidence,
                strategy_name=signal.strategy_name,
                reason=f"信号触发: {signal.signal_type}",
            )
        except Exception as e:
            log.warning(f"[AdaptiveCycle] 发送交易通知失败: {e}")

        try:
            from deva.naja.state.snapshot import record_bandit_decision
            record_bandit_decision(
                action="BUY",
                symbol=signal.stock_code,
                price=signal.price,
                confidence=signal.confidence,
                # ❗这里必须是**股数**，不能是 amount（金额）。此前传的是 `amount`，
                #   而平仓侧（_on_position_closed）传的是 `position.quantity` ——
                #   同一个 `quantity` 字段在买入记录里装"元"、在卖出记录里装"股"，
                #   而这张表（naja_bandit_decision_context）是**用来复盘的**：
                #   量纲混用的历史数据事后无法解读。
                #   正确值就在手边：`outcome.quantity` 是本次实际成交股数
                #   （虚拟后端 = position.quantity，富途后端 = 取整后的 qty）。
                quantity=float(getattr(outcome, "quantity", 0.0) or 0.0),
                reason=f"信号触发: {signal.signal_type} from {signal.strategy_name}"
            )
        except Exception as e:
            log.debug(f"记录Bandit决策快照失败: {e}")

        self._optimizer.select_strategy(
            available_strategies=[signal.strategy_id],
            context={"stock_code": signal.stock_code, "price": signal.price}
        )

        log.info(f"[AdaptiveCycle] ✅ 自适应循环: {outcome.backend} 执行 "
                 f"{signal.stock_name}({signal.stock_code}) @ {signal.price}")
    
    def _on_price_update(self, stock_code: str, price: float):
        """处理价格更新"""
        log.debug(f"[AdaptiveCycle] 📈 收到价格更新: {stock_code} @ {price}")

        try:
            closed = self._portfolio.update_price(stock_code, price)
        except Exception as e:
            # 以前这里没有保护：异常会冒到 MarketObserver._update_price 的
            # `except Exception: log.debug(...)` 里被静默吞掉，页面上只表现为
            # "价格再也不动了"，看不到任何原因。现在如实登记失败。
            log.warning(f"[AdaptiveCycle] ❌ 价格更新失败 {stock_code} @ {price}: {e}")
            get_freshness_tracker().record_failure(SOURCE_CN_PRICE, f"{stock_code}: {e}")
            return

        get_freshness_tracker().record_success(SOURCE_CN_PRICE)
        log.debug(f"[AdaptiveCycle] 📊 止盈止损检查完成，平仓数量: {len(closed)}")

        for close_info in closed:
            log.debug(f"[AdaptiveCycle] 💰 触发止盈止损平仓 {stock_code} @ {price}")
    
    def _on_position_closed(self, position_id: str, position: VirtualPosition, reason: str):
        """处理持仓平仓"""
        result = self._tracker.on_position_closed(
            strategy_id=position.strategy_id,
            position_id=position_id,
            entry_price=position.entry_price,
            exit_price=position.current_price,
            open_timestamp=position.entry_time,
            trigger_adjust=self._auto_adjust_enabled,
            stock_code=position.stock_code,
            stock_name=position.stock_name,
            close_reason=reason,
            signal_confidence=getattr(position, 'signal_confidence', 0.5),
        )
        
        log.info(f"自适应循环: 平仓 {position.stock_name} 收益={position.return_pct:.2f}% "
                f"原因={reason} Bandit奖励={result.get('reward', 0):.2f}")

        try:
            from deva.naja.bandit.notifier import get_bandit_notifier
            notifier = get_bandit_notifier()
            notifier.notify_position_closed(
                position_id=position_id,
                stock_code=position.stock_code,
                stock_name=position.stock_name,
                open_price=position.entry_price,
                close_price=position.current_price,
                profit_pct=position.return_pct,
                reason=reason,
            )
        except Exception as e:
            log.warning(f"[AdaptiveCycle] 发送平仓通知失败: {e}")

        try:
            from deva.naja.state.snapshot import record_bandit_decision
            record_bandit_decision(
                action="SELL",
                symbol=position.stock_code,
                price=position.current_price,
                confidence=getattr(position, 'signal_confidence', 0.5),
                quantity=position.quantity,
                reason=f"平仓: {reason}, 收益率={position.return_pct:.2f}%"
            )
        except Exception as e:
            log.debug(f"记录Bandit决策快照失败: {e}")

        self._optimizer.update_reward(position.strategy_id, result.get('reward', position.return_pct))

        self._publish_trade_outcome(position, reason, result)

    def _publish_trade_outcome(self, position, reason: str, result) -> None:
        """把平仓结果发布为 TradeOutcomeEvent —— 闭环反馈的起点。

        消费者：EventSubscriberRegistrar 里的订阅 → TradingCenter.record_trade_outcome
        → 喂给共享 AwakenedAlaya（Bandit 侧的学习已由上面的 update_reward 完成）。
        """
        try:
            from deva.naja.events import TradeOutcomeEvent, get_trading_bus
            reward = result.get("reward", 0.0) if isinstance(result, dict) else 0.0
            event = TradeOutcomeEvent(
                symbol=getattr(position, "stock_code", ""),
                pnl_pct=float(getattr(position, "return_pct", 0.0) or 0.0),
                strategy_id=getattr(position, "strategy_id", ""),
                strategy_name=getattr(position, "strategy_name", ""),
                position_id=getattr(position, "position_id", ""),
                entry_price=float(getattr(position, "entry_price", 0.0) or 0.0),
                exit_price=float(getattr(position, "current_price", 0.0) or 0.0),
                close_reason=reason,
                reward=float(reward or 0.0),
            )
            get_trading_bus().publish(event)
        except Exception as e:
            log.debug(f"[AdaptiveCycle] 发布 TradeOutcomeEvent 失败: {e}")
    
    def start(self):
        """启动自适应循环"""
        if self._running:
            log.warning("AdaptiveCycle 已在运行")
            return

        self._running = True
        self._save_config()  # 保存运行状态

        # 重新设置回调（确保 MarketObserver 的回调已注册）
        self._setup_callbacks()

        self._signal_listener.start()
        self._market_observer.start()

        log.info("自适应循环已启动")
    
    def stop(self):
        """停止自适应循环"""
        if not self._running:
            return
        
        self._running = False
        self._save_config()  # 保存运行状态
        
        self._signal_listener.stop()
        self._market_observer.stop()
        
        log.info("自适应循环已停止")
    
    def run_once(self) -> dict:
        """手动运行一次"""
        results = {
            "signals": [],
            "prices": [],
            "bandit": {}
        }
        
        results["signals"] = self._signal_listener.get_status()
        results["prices"] = self._market_observer.get_status()
        
        try:
            results["bandit"] = self._optimizer.review_and_adjust()
        except Exception as e:
            results["bandit"] = {"error": str(e)}
        
        return results
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "auto_buy_enabled": self._auto_buy_enabled,
            "auto_adjust_enabled": self._auto_adjust_enabled,
            "signal_listener": self._signal_listener.get_status(),
            "market_observer": self._market_observer.get_status(),
            "portfolio": self._portfolio.get_summary(),
        }
    
    def get_positions(self) -> List[dict]:
        """获取当前持仓"""
        positions = self._portfolio.get_all_positions(status="OPEN")
        return [
            {
                "position_id": p.position_id,
                "strategy_name": p.strategy_name,
                "stock_code": p.stock_code,
                "stock_name": p.stock_name,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "quantity": p.quantity,
                "return_pct": p.return_pct,
                "profit_loss": p.profit_loss,
                "holding_seconds": p.holding_seconds,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "market_time": p.market_time,
                "entry_time": p.entry_time
            }
            for p in positions
        ]
    
    def get_history(self, limit: int = 50) -> List[dict]:
        """获取历史持仓"""
        positions = self._portfolio.get_all_positions(status="CLOSED")
        positions.sort(key=lambda x: x.exit_time or x.last_update_time, reverse=True)
        return [
            {
                "position_id": p.position_id,
                "strategy_name": p.strategy_name,
                "stock_code": p.stock_code,
                "stock_name": p.stock_name,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "current_price": p.current_price,
                "quantity": p.quantity,
                "return_pct": p.return_pct,
                "profit_loss": p.profit_loss,
                "holding_seconds": p.holding_seconds,
                "entry_time": p.entry_time,
                "exit_time": p.exit_time,
                "last_update_time": p.last_update_time,
                "close_reason": p.close_reason,  # 平仓原因
                "market_time": p.market_time
            }
            for p in positions[:limit]
        ]
    
    def set_auto_buy(self, enabled: bool):
        """设置自动买入"""
        self._auto_buy_enabled = enabled
        self._save_config()
    
    def set_auto_adjust(self, enabled: bool):
        """设置自动调节"""
        self._auto_adjust_enabled = enabled
        self._save_config()
    
    def close_position(self, position_id: str, reason: str = "MANUAL") -> bool:
        """手动平仓"""
        position = self._portfolio.get_position(position_id)
        if not position:
            return False
        
        return self._portfolio.close_position(position_id, position.current_price, reason) is not None

