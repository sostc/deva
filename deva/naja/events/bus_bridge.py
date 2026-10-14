"""总线桥梁 - 连接认知总线和交易总线的桥梁

职责：
1. 监听重要认知事件，转换为交易信号
2. 监听交易决策，反馈给认知层
3. 提供跨总线的事件查询

❗**启用状态：默认关闭**（`NAJA_BUS_BRIDGE=1` 才在装配期打开，见
`enable_bridge_from_env()`）。关闭是**显式决策**，不是静默失效：装配期会打印
一行 `[BusBridge] 未启用（NAJA_BUS_BRIDGE 未设置）`，守卫也会核对这段语义。

------------------------------------------------------------------
为什么默认关：2026-10-15 全链路审计（docs/naja/p0_linkage_design_2026-10-15.md）
------------------------------------------------------------------
这条链路**从未跑通过一次**，审计挖出四层障碍，前三层是纯代码缺陷（已修），
第四层是**策略缺口（必须由人拍板，故保持关闭）**：

  a) ❗**模块从未被实例化**：全库没有任何生产代码 import 本模块或调用
     `get_bus_bridge()`，`enable_bridge(True)` 此前只出现在
     `events/__init__.py` 的 docstring 示例里。现由容器在
     `NAJA_BUS_BRIDGE=1` 时装配。
  b) ❗**订阅通道错了**（已修）：`NajaEventBus` 有两条**互不可见**的通道 ——
     认知信号通道（`subscribe_cognitive` / 按 `CognitiveEventType` 枚举路由）
     与 dataclass 通道（`subscribe('类名', cb)` / `publish(obj)` / 按类名字符串
     路由）。认知层实际产出的事件全是 dataclass，走的是**后者**；原实现订阅的是
     前者 → 一个事件都收不到。现改为按 dataclass 类名订阅。
  c) ❗**转换函数读的字段不存在**（已修）：原实现读 `event.stock_codes` /
     `event.narrative_type`，而真实事件只有 `symbols` / `current_narratives`；
     且 `importantance` / `confidence` 对 `NarrativeStateEvent` 而言**根本没有**
     （`getattr` 取到默认 0.0）→ 恒被阈值过滤，转换函数即使被调用也只会
     `return None`。现按各事件的**真实字段**推导。
  d) ⚠️**「叙事/板块 → 股票代码」的方向映射没有权威依据**（未修，故关闭）：
     认知层谈的是叙事与板块（`current_narratives=['AI']`、`symbols=[block_id]`），
     交易层要的是具体标的与方向。可用的解析器已经有了（见
     `_resolve_symbols`），但「叙事转强 = 买还是卖」**是策略决策**，
     代码里没有任何既有约定可依。硬开等于把一条拍脑袋的规则接进真钱链路 ——
     因此默认关，等策略口径确定后再打开。

  ❗另注（2026-10-15 复核）：认知层三条发射端此前**一条也没通** ——
    1) `events/__init__.py` 的 dataclass 导入名单里写了三个不存在的名字
       （`GlobalMarketEvent` / `create_risk_alert` / `EVENT_TYPE_MAP`），
       `from ... import (...)` 在第一个缺失名处抛 ImportError，导致缺失名之后的
       `create_narrative_update` 等**从未绑定**，而消费方一律 `except ImportError: pass`
       → 完全无声。已修（改为逐名对齐 + 失败告警）。
    2) `NarrativeTracker._publish_cognitive_update` 与
       `TimingNarrativeTracker._publish_cognitive_update` 的参数写错
       （前者 `narrative_id="narratives..."` 字面量垃圾，后者给只读 property
       传 `event_type=`）→ 即使被调用也必抛异常。已修。
    3) 这两个方法本身**仍然没有调用方**（真正在发的是 `_publish_narrative_state_event`
       与 `_send_narrative_state` 那条路径）→ `NarrativeUpdateEvent` /
       `TimingNarrativeShiftEvent` 目前依然不会被生产出来。
       也就是说，现在开桥能收到的仍然是 `NarrativeStateEvent` 与
       `ResonanceDetectedEvent` 两类；规则表里为 `NarrativeUpdateEvent` 预留的
       转换只在它的发射端被接上之后才会生效。
"""

import os
import re
import time
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import asdict

log = logging.getLogger(__name__)

# 环境开关名。约定同 NAJA_T_ESTABLISH_GATE / NAJA_WATCH_MARKET_CLOCK：设 "1"/"true" 开。
ENV_BRIDGE_SWITCH = "NAJA_BUS_BRIDGE"

# 单条认知事件最多扇出多少只标的。超过就截断，并**显式留痕**（不静默丢）。
MAX_SYMBOLS_PER_EVENT = 20

# 认知信号置信度折扣：认知事件不是策略信号，过桥后必须打折，
# 否则「叙事情绪」会以策略同等权重直接进决策中心。
COGNITIVE_CONFIDENCE_DISCOUNT = 0.6

# 叙事情绪（sentiment_score ∈ [0,1]，0.5 为中性）判定买卖的阈值。
# ❗这两条阈值是**占位口径**，不是权威策略：见模块 docstring (d)。
SENTIMENT_BUY_THRESHOLD = 0.6
SENTIMENT_SELL_THRESHOLD = 0.4

# 认知事件默认重要性下限。低于此值的事件不产生信号（防止噪声灌入链路）。
DEFAULT_IMPORTANCE_MIN = 0.6


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def bridge_enabled_by_env() -> bool:
    """读取环境开关（供容器装配期判断是否启用桥梁）"""
    return str(os.environ.get(ENV_BRIDGE_SWITCH, "")).strip().lower() in ("1", "true", "yes", "on")


class BusBridge:
    """
    连接认知总线和交易总线的桥梁

    通信场景：
    1. 认知 → 交易：重要叙事/风险事件触发交易信号
    2. 交易 → 认知：交易结果反馈认知调整
    """

    def __init__(self, cognitive_bus=None, trading_bus=None):
        """
        Args:
            cognitive_bus: 认知总线实例（NajaEventBus，从 cognitive_bus 导入）
            trading_bus: 交易总线实例（从 trading_bus 导入）
        """
        self.cognitive_bus = cognitive_bus
        self.trading_bus = trading_bus
        self._bridge_enabled = False

        # 转发规则配置。
        # ❗key 必须是 **dataclass 事件类名**（与 `publish()` 的路由口径一致：
        # `event_type = type(event).__name__`），不是 `CognitiveEventType` 成员名 ——
        # 认知层真正在发的事件走 dataclass 通道，用枚举名匹配会恒不命中。
        # value = (重要性阈值, 转换函数)；转换函数返回 List[StrategySignalEvent]。
        self._cognitive_to_trading_rules: Dict[str, Tuple[float, Any]] = {
            "NarrativeUpdateEvent": (
                0.70, self._narrative_update_to_signals
            ),
            "NarrativeStateEvent": (
                DEFAULT_IMPORTANCE_MIN, self._narrative_state_to_signals
            ),
            "ResonanceDetectedEvent": (
                0.75, self._resonance_to_signals
            ),
        }

        # 已订阅的 dataclass 事件类名 → 回调（用于 disable 时精确退订）
        self._dc_subscriptions: Dict[str, Any] = {}

        # 统计
        self._bridge_stats = {
            'cognitive_to_trading': 0,
            'trading_to_cognitive': 0,
            'filtered_by_importance': 0,
            'conversion_errors': 0,
            # ❗「信号发出但一只标的都没解析出来」必须单独计数：
            # 与「链路断了」是两件事（既不报错也不产出的空值家族）。
            'dropped_unresolved_symbols': 0,
            'dropped_no_direction': 0,
            'signals_truncated': 0,
        }

        log.info(
            "[BusBridge] 桥梁初始化完成（未启用；置 %s=1 由容器装配启用）",
            ENV_BRIDGE_SWITCH,
        )

    # ============== 生命周期 ==============

    def enable_bridge(self, enable: bool = True) -> bool:
        """启用/禁用桥梁（幂等：反复调用不抛异常、不重复订阅）"""
        if enable and (self.cognitive_bus is None or self.trading_bus is None):
            log.error("[BusBridge] 启用失败：总线实例未设置")
            return False

        if enable == self._bridge_enabled:
            # 幂等：同状态重复调用直接返回，避免重复挂订阅
            return True

        self._bridge_enabled = enable

        if enable:
            self._setup_cognitive_subscriptions()
            self.setup_trading_feedback()
            log.info("[BusBridge] 桥梁已启用")
        else:
            self._teardown_cognitive_subscriptions()
            log.info("[BusBridge] 桥梁已禁用")

        return True

    def set_buses(self, cognitive_bus, trading_bus):
        """设置总线实例"""
        self.cognitive_bus = cognitive_bus
        self.trading_bus = trading_bus
        log.info("[BusBridge] 总线实例已设置")

        if self._bridge_enabled:
            self._teardown_cognitive_subscriptions()
            self._setup_cognitive_subscriptions()

    def get_stats(self) -> Dict[str, Any]:
        """获取桥梁统计"""
        return dict(self._bridge_stats)

    # ============== 认知 → 交易转换 ==============

    def _setup_cognitive_subscriptions(self):
        """按 **dataclass 类名**订阅认知总线。

        ❗必须走 `subscribe(类名, cb)`（dataclass 通道）。认知层实际产出的事件
        （`NarrativeStateEvent` 由 NarrativeTracker 发布、`ResonanceDetectedEvent`
        由 CrossSignalAnalyzer 发布）都是 dataclass，`NajaEventBus.publish()` 按
        `type(event).__name__` 路由；而 `subscribe_cognitive` 走的是另一条按
        `CognitiveEventType` 枚举路由的通道，**两者互不可见**。
        """
        if self.cognitive_bus is None:
            return

        for event_name, (_threshold, convert) in self._cognitive_to_trading_rules.items():

            def _callback(event, _convert=convert):
                self._process_cognitive_event(event, _convert)

            try:
                self.cognitive_bus.subscribe(event_name, _callback, priority=15)
                self._dc_subscriptions[event_name] = _callback
                log.info("[BusBridge] 已订阅认知事件（dataclass 通道）: %s", event_name)
            except Exception as e:  # noqa: BLE001
                log.error("[BusBridge] 订阅 %s 失败: %s", event_name, e)

    def _teardown_cognitive_subscriptions(self):
        """退订认知事件（按 callback 精确退订 dataclass 通道）"""
        if self.cognitive_bus is None:
            self._dc_subscriptions.clear()
            return
        for event_name, callback in list(self._dc_subscriptions.items()):
            try:
                self.cognitive_bus.unsubscribe(event_name, callback)
            except Exception as e:  # noqa: BLE001
                log.debug("[BusBridge] 退订 %s 失败（可忽略）: %s", event_name, e)
        self._dc_subscriptions.clear()

    def _process_cognitive_event(self, event, convert=None) -> None:
        """处理认知事件，转换为交易信号并发布到交易总线"""
        if not self._bridge_enabled or self.trading_bus is None:
            return

        event_type = type(event).__name__
        if convert is None:
            rule = self._cognitive_to_trading_rules.get(event_type)
            if rule is None:
                return
            _, convert = rule

        try:
            importance = self._importance_of(event)
            threshold, _ = self._cognitive_to_trading_rules.get(
                event_type, (DEFAULT_IMPORTANCE_MIN, None)
            )

            if importance < threshold:
                self._bridge_stats['filtered_by_importance'] += 1
                log.debug(
                    "[BusBridge] 认知事件重要性不足: %s importance=%.2f < %.2f",
                    event_type, importance, threshold,
                )
                return

            signals = convert(event) or []
            if not signals:
                return

            for signal in signals:
                delivered = self.trading_bus.publish(signal)
                if delivered > 0:
                    self._bridge_stats['cognitive_to_trading'] += 1
                    log.info(
                        "[BusBridge] 认知→交易: %s → %s %s %s (conf=%.2f, 分发 %d)",
                        event_type, signal.strategy_name, signal.symbol,
                        signal.direction.value, signal.confidence, delivered,
                    )

        except Exception as e:  # noqa: BLE001
            self._bridge_stats['conversion_errors'] += 1
            log.error("[BusBridge] 认知事件转换失败 (%s): %s", event_type, e)

    @staticmethod
    def _importance_of(event) -> float:
        """从**真实字段**推导事件重要性。

        ❗`NarrativeStateEvent` 没有 `importance` 字段，原实现 `getattr(event,
        'importance', 0.0)` 恒取 0.0 → 一律被阈值过滤。这里对没有该字段的事件，
        用其携带的强度/情绪推导。
        """
        raw = getattr(event, "importance", None)
        if raw is not None:
            return _clamp01(raw)

        strength = getattr(event, "narrative_strength", None)
        sentiment = getattr(event, "sentiment_score", None)
        candidates = []
        if strength is not None:
            candidates.append(_clamp01(strength))
        if sentiment is not None:
            candidates.append(_clamp01(abs(float(sentiment) - 0.5) * 2.0))
        return max(candidates) if candidates else 0.0

    # ---------- 标的解析 ----------

    @staticmethod
    def _looks_like_code(token: str) -> bool:
        """判断 token 是否**已经是**可交易代码（而非板块/叙事名）。

        ❗必须只能是**带市场标记的严格形态**：
          - A股：`sh600487` / `sz000636` / `bj920056`（无点前缀，与行情总线、
            题材策略的实际写法一致），或裸 6 位数字；
          - 港美股：`AAPL.US` / `00700.HK`（带显式市场后缀）。

        ❗**不要**把「纯字母大写」当代码。反例：`"不存在的叙事XYZ".isupper()`
        为 True —— Python 的 `isupper()` 只看**有大小写的字符**，CJK 不参与判断，
        于是任何「中文名 + 大写字母」都会被误判成股票代码，进而**凭空造出一个
        标的**送进决策中心。叙事名与板块名一律走解析器；判不出来就如实丢弃，
        绝不兜底成编造的代码。
        """
        t = (token or "").strip()
        if not t or not t.isascii():
            return False
        if re.fullmatch(r"(?i)(sh|sz|bj)\d{6}", t):
            return True
        if re.fullmatch(r"\d{6}", t):
            return True
        if re.fullmatch(r"(?i)[A-Z0-9]{1,10}\.(us|hk)", t):
            return True
        return False

    def _resolve_symbols(
        self,
        narratives: Optional[List[str]] = None,
        block_ids: Optional[List[str]] = None,
        market: str = "CN",
    ) -> List[str]:
        """把「叙事名 / 板块ID」解析成股票代码。

        解析顺序（全部**如实失败**：解析不出来就返回空列表并留痕，
        绝不兜底成编造的代码）：
          1. 已经是可交易代码的 token 直接采用；
          2. `BlockRegistry`（注意力层的板块语义中心）：
             叙事名 → `get_blocks_for_narrative()` → `BlockDescriptor.symbols`
             （symbols 由 `FocusManager.link_symbol_to_block` 真实填充）；
          3. `cognition.narrative.block_mapping.get_linked_blocks()` 把叙事名
             翻成题材ID，再由 `dictionary.blocks.get_block_stocks()` 取成分股
             （A股题材名如「3D打印」，数据在 cn_blocks.yaml）。
        """
        found: Set[str] = set()
        unresolved: List[str] = []

        tokens: List[str] = []
        for t in (block_ids or []) + (narratives or []):
            if t and t not in tokens:
                tokens.append(t)

        # 1) 直接是代码
        for t in tokens:
            if self._looks_like_code(t):
                found.add(t.strip())

        # 2) BlockRegistry
        try:
            from deva.naja.attention.block_registry import get_block_registry
            registry = get_block_registry()

            for b in (block_ids or []):
                desc = registry.get(b)
                if desc is not None and desc.symbols:
                    found.update(desc.symbols)

            for n in (narratives or []):
                for desc in registry.get_blocks_for_narrative(n):
                    if desc.symbols:
                        found.update(desc.symbols)
        except Exception as e:  # noqa: BLE001
            log.debug("[BusBridge] BlockRegistry 解析失败: %s", e)

        # 3) 叙事 → 题材ID → 成分股
        try:
            from deva.naja.cognition.narrative.block_mapping import get_linked_blocks
            from deva.naja.dictionary.blocks import get_block_stocks

            candidate_blocks: List[str] = [b for b in (block_ids or []) if not self._looks_like_code(b)]
            for n in (narratives or []):
                candidate_blocks.extend(get_linked_blocks(n))

            seen_blocks: List[str] = []
            for b in candidate_blocks:
                if b and b not in seen_blocks:
                    seen_blocks.append(b)

            for b in seen_blocks:
                stocks = get_block_stocks(b, market) or []
                if stocks:
                    found.update(stocks)
                else:
                    unresolved.append(b)
        except Exception as e:  # noqa: BLE001
            log.debug("[BusBridge] 叙事→题材→成分股 解析失败: %s", e)

        symbols = sorted(found)

        if len(symbols) > MAX_SYMBOLS_PER_EVENT:
            self._bridge_stats['signals_truncated'] += 1
            log.warning(
                "[BusBridge] 单事件扇出 %d 只标的，超过上限 %d 已截断（tokens=%s）",
                len(symbols), MAX_SYMBOLS_PER_EVENT, tokens,
            )
            symbols = symbols[:MAX_SYMBOLS_PER_EVENT]

        if not symbols:
            self._bridge_stats['dropped_unresolved_symbols'] += 1
            log.info(
                "[BusBridge] 认知事件未能解析出任何标的，已丢弃（这不是链路故障，"
                "而是映射缺失）: tokens=%s market=%s 未命中题材=%s",
                tokens, market, unresolved[:5],
            )

        return symbols

    def _build_signals(
        self,
        event,
        symbols: List[str],
        direction,
        confidence: float,
        strategy_name: str,
        signal_type: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """按解析出的标的逐只生成 StrategySignalEvent"""
        if not symbols:
            return []

        from .trading_events import StrategySignalEvent

        market = str(getattr(event, "market", "") or "CN").upper()
        signals: List[Any] = []
        for code in symbols:
            signals.append(StrategySignalEvent(
                symbol=code,
                direction=direction,
                confidence=confidence,
                strategy_name=strategy_name,
                signal_type=signal_type,
                current_price=None,   # 认知侧没有行情；决策中心会另取
                price_change_pct=0.0,
                importance=self._importance_of(event),
                market=market,
                metadata={
                    "cognitive_source": getattr(event, "source", ""),
                    "cognitive_event": type(event).__name__,
                    **(extra_metadata or {}),
                },
                timestamp=time.time(),
            ))
        return signals

    def _narrative_update_to_signals(self, event) -> List[Any]:
        """叙事更新事件 → 策略信号。

        ❗这是**唯一一个自带 `symbols`（真实股票代码）的认知事件**，所以它比
        `NarrativeStateEvent` 更适合过桥。真实字段：
        `narrative_id`、`narrative_type`（block/global）、`symbols`、
        `strength_change ∈ [-1, 1]`、`new_strength`。

        方向用 `strength_change` 的符号 —— 这是该字段注释里写明的语义
        （「强度变化（-1到1）」）。为 0 时**不发信号**（没有方向证据就不猜）。
        兼容：`narrative_type` 为 risk/alert/warning 时按卖出处理。
        """
        from .trading_events import SignalDirection

        try:
            strength_change = float(getattr(event, "strength_change", 0.0) or 0.0)
        except (TypeError, ValueError):
            strength_change = 0.0

        narrative_type = str(getattr(event, "narrative_type", "") or "").lower()

        if narrative_type in ("risk", "alert", "warning"):
            direction = SignalDirection.SELL
        elif strength_change > 0.05:
            direction = SignalDirection.BUY
        elif strength_change < -0.05:
            direction = SignalDirection.SELL
        else:
            self._bridge_stats['dropped_no_direction'] += 1
            log.debug(
                "[BusBridge] 叙事更新无方向证据（strength_change=%.3f, type=%s），不发信号",
                strength_change, narrative_type,
            )
            return []

        raw_symbols = list(getattr(event, "symbols", []) or [])
        symbols = self._resolve_symbols(
            block_ids=raw_symbols,
            market=str(getattr(event, "market", "") or "CN"),
        )
        if not symbols:
            return []

        confidence = _clamp01(
            max(abs(strength_change), _clamp01(getattr(event, "confidence", 0.5)))
            * COGNITIVE_CONFIDENCE_DISCOUNT
        )

        return self._build_signals(
            event,
            symbols=symbols,
            direction=direction,
            confidence=confidence,
            strategy_name="认知驱动:叙事更新",
            signal_type="cognitive_narrative_update",
            extra_metadata={
                "narrative_id": getattr(event, "narrative_id", ""),
                "narrative_type": narrative_type,
                "strength_change": strength_change,
            },
        )

    def _narrative_state_to_signals(self, event) -> List[Any]:
        """叙事状态事件 → 策略信号。

        `NarrativeStateEvent` 的真实字段（`events/cognitive_events.py`）：
        `current_narratives: List[str]`（叙事名，**不是股票代码**）、
        `narrative_strength`、`narrative_risk`、`sentiment_score ∈ [0,1]`。
        没有 `importance` / `confidence` / `stock_codes`。
        """
        from .trading_events import SignalDirection

        narratives = list(getattr(event, "current_narratives", []) or [])
        if not narratives:
            return []

        sentiment = event.sentiment_score
        try:
            sentiment = float(sentiment)
        except (TypeError, ValueError):
            return []

        # 方向：只用情绪这一条可解释的证据，判不出来就**不发信号**（不猜）。
        if sentiment > SENTIMENT_BUY_THRESHOLD:
            direction = SignalDirection.BUY
        elif sentiment < SENTIMENT_SELL_THRESHOLD:
            direction = SignalDirection.SELL
        else:
            self._bridge_stats['dropped_no_direction'] += 1
            log.debug(
                "[BusBridge] 叙事情绪中性（sentiment=%.2f），不发信号: %s",
                sentiment, narratives[:3],
            )
            return []

        symbols = self._resolve_symbols(
            narratives=narratives,
            market=str(getattr(event, "market", "") or "CN"),
        )
        if not symbols:
            return []

        confidence = _clamp01(
            (0.5 * _clamp01(event.narrative_strength) + 0.5 * abs(sentiment - 0.5) * 2.0)
            * COGNITIVE_CONFIDENCE_DISCOUNT
        )

        return self._build_signals(
            event,
            symbols=symbols,
            direction=direction,
            confidence=confidence,
            strategy_name="认知驱动:叙事状态",
            signal_type="cognitive_narrative",
            extra_metadata={
                "narrative_names": narratives[:5],
                "narrative_strength": _clamp01(event.narrative_strength),
                "narrative_risk": event.narrative_risk,
                "sentiment_score": sentiment,
            },
        )

    def _resonance_to_signals(self, event) -> List[Any]:
        """共振检测事件 → 策略信号。

        `ResonanceDetectedEvent` 的真实字段：`resonance_id`、`resonance_type`、
        `symbols`（❗生产方 `CrossSignalAnalyzer._emit_to_cognitive_bus` 填的是
        `[resonance.block_id]` —— **是板块ID，不是股票代码**，必须过解析器）、
        `strength`、`metadata`（含 `sentiment` = 新闻情绪）。
        """
        from .trading_events import SignalDirection

        metadata = dict(getattr(event, "metadata", {}) or {})
        sentiment = metadata.get("sentiment")

        # 方向：优先用新闻情绪（口径 ∈ [-1, 1]，0 中性）；拿不到就不发信号。
        if sentiment is None:
            self._bridge_stats['dropped_no_direction'] += 1
            log.debug("[BusBridge] 共振事件缺少 sentiment，不发信号: %s", event.resonance_id)
            return []
        try:
            sentiment = float(sentiment)
        except (TypeError, ValueError):
            return []

        if sentiment > 0.1:
            direction = SignalDirection.BUY
        elif sentiment < -0.1:
            direction = SignalDirection.SELL
        else:
            self._bridge_stats['dropped_no_direction'] += 1
            log.debug("[BusBridge] 共振情绪中性（sentiment=%.2f），不发信号", sentiment)
            return []

        raw_symbols = list(getattr(event, "symbols", []) or [])
        symbols = self._resolve_symbols(
            block_ids=raw_symbols,
            market=str(getattr(event, "market", "") or "CN"),
        )
        if not symbols:
            return []

        confidence = _clamp01(
            _clamp01(getattr(event, "strength", 0.0)) * COGNITIVE_CONFIDENCE_DISCOUNT
        )

        return self._build_signals(
            event,
            symbols=symbols,
            direction=direction,
            confidence=confidence,
            strategy_name="认知驱动:共振",
            signal_type="cognitive_resonance",
            extra_metadata={
                "resonance_id": getattr(event, "resonance_id", ""),
                "resonance_type": getattr(event, "resonance_type", ""),
                "resonance_strength": _clamp01(getattr(event, "strength", 0.0)),
                "news_sentiment": sentiment,
                "resolved_from": raw_symbols[:5],
            },
        )

    # ============== 交易 → 认知反馈 ==============

    def setup_trading_feedback(self):
        """设置交易决策反馈"""
        if self.trading_bus is None:
            return

        try:
            self._trading_subscription_id = self.trading_bus.subscribe(
                event_type='TradeDecisionEvent',
                callback=self._process_trade_decision,
                subscription_id='bridge_trading_feedback',
            )
            log.info(
                "[BusBridge] 已订阅交易决策反馈 (id=%s)", self._trading_subscription_id
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[BusBridge] 订阅交易决策反馈失败: %s", e)

    def _process_trade_decision(self, event):
        """处理交易决策，反馈给认知层"""
        if not self._bridge_enabled or self.cognitive_bus is None:
            return

        try:
            decision = event.decision.value
            approval_score = event.approval_score
            signal_event = event.signal_event

            if decision == 'APPROVED':
                self._reinforce_narrative(signal_event, approval_score)
            elif decision == 'REJECTED':
                self._adjust_risk_cognition(signal_event, approval_score)

            self._bridge_stats['trading_to_cognitive'] += 1

        except Exception as e:  # noqa: BLE001
            log.error("[BusBridge] 交易决策反馈处理失败: %s", e)

    def _reinforce_narrative(self, signal_event, approval_score):
        """增强叙事信心

        ❗**尚未实现实质动作**：只记 debug 日志。这里是「交易结果 → 认知调整」
        的正向通路，目前是空实现 —— 阅读者不要误以为反馈闭环已生效。
        """
        log.debug("[BusBridge] 交易通过，增强相关叙事信心: %s", signal_event)

    def _adjust_risk_cognition(self, signal_event, approval_score):
        """调整风险认知

        ❗同样**尚未实现实质动作**，只记 debug 日志。
        """
        log.debug("[BusBridge] 交易被拒，调整风险认知: %s", signal_event)

    # ============== 公共接口 ==============

    def get_cross_bus_history(self, event_types: List[str], limit: int = 50) -> List[Dict]:
        """
        跨总线查询事件历史

        Args:
            event_types: 事件类型列表
            limit: 每类事件限制

        Returns:
            合并的事件历史
        """
        results = []

        # 从认知总线查询（dataclass 通道）
        if self.cognitive_bus:
            for event_type in event_types:
                try:
                    history = self.cognitive_bus.get_event_history(event_type, limit)
                    for item in history:
                        row = asdict(item) if hasattr(item, '__dataclass_fields__') else {'value': str(item)}
                        row['bus_type'] = 'cognitive'
                        results.append(row)
                except Exception:  # noqa: BLE001
                    pass

        # 从交易总线查询
        if self.trading_bus:
            for event_type in event_types:
                try:
                    history = self.trading_bus.get_history(event_type, limit)
                    for item in history:
                        item = dict(item) if isinstance(item, dict) else {'value': str(item)}
                        item['bus_type'] = 'trading'
                        results.append(item)
                except Exception:  # noqa: BLE001
                    pass

        results.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return results[:limit]


# ============== 单例实例 ==============

_bridge_instance = None


def get_bus_bridge() -> BusBridge:
    """获取桥梁单例"""
    global _bridge_instance

    if _bridge_instance is None:
        try:
            from .cognitive_bus import get_event_bus as get_cognitive_bus
            from .trading_bus import get_trading_bus

            _bridge_instance = BusBridge(get_cognitive_bus(), get_trading_bus())
            log.info("[get_bus_bridge] 桥梁单例已创建")

        except ImportError as e:
            log.warning("[get_bus_bridge] 无法导入总线实例: %s", e)
            _bridge_instance = BusBridge()

    return _bridge_instance


def enable_bridge_from_env() -> bool:
    """装配期调用：读 `NAJA_BUS_BRIDGE`，为真时启用桥梁单例。

    返回是否已启用。**无论开关如何都会留一行日志** —— 「没开」必须是显式状态，
    不能像修复前那样只能靠读代码才知道（见模块 docstring）。
    """
    if not bridge_enabled_by_env():
        log.info(
            "[BusBridge] 未启用（%s 未设置）。认知层产出不会转换为交易信号；"
            "启用方法：设置 %s=1 后重启服务。",
            ENV_BRIDGE_SWITCH, ENV_BRIDGE_SWITCH,
        )
        return False

    bridge = get_bus_bridge()
    ok = bridge.enable_bridge(True)
    if ok:
        log.warning(
            "[BusBridge] ⚠️ 认知→交易桥梁已启用（%s=1）：认知事件将转换为"
            " StrategySignalEvent 进入决策中心。方向口径为占位规则，见模块 docstring (d)。",
            ENV_BRIDGE_SWITCH,
        )
    return ok


def create_bus_bridge(cognitive_bus, trading_bus) -> BusBridge:
    """手动创建桥梁（用于测试）"""
    return BusBridge(cognitive_bus, trading_bus)
