"""
TradingCenter - 交易中枢

定位：Naja系统的协调中枢，协调各层模块完成交易决策

架构：
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TradingCenter (交易中枢)                               │
│                                                                             │
│  职责：                                                                     │
│    • 数据协调 - 接收市场数据，分发给各模块                                    │
│    • 快速决策 - 通过 AttentionOS.kernel.make_decision()                      │
│    • 慢思考融合 - 调用 FirstPrinciplesMind.think()                           │
│    • 模式匹配 - 调用 AwakenedAlaya.illuminate()                              │
│    • 决策融合 - 融合各模块输出生成最终决策                                    │
│    • 策略协调 - 协调策略执行                                                 │
│                                                                             │
│  内部模块：                                                                 │
│    • AttentionOS - 注意力计算和快速决策                                      │
│    • FirstPrinciplesMind - 因果推理                                           │
│    • AwakenedAlaya - 模式匹配/顿悟                                          │
└─────────────────────────────────────────────────────────────────────────────┘

使用方式：
    center = TradingCenter()
    decision = center.process_strategy_signal(signal)
"""

import os
import time
import logging
from collections import deque
from typing import Dict, Any, Optional, List, Deque
import threading

from deva.naja.cognition.narrative.tracker import get_narrative_tracker
from deva.naja.decision import (
    DecisionOrchestrator,
    DecisionPlan,
    FusionOutput,
    compute_plan_size_hint,
    side_from_signal_type,
)
from ..os.attention_os import AttentionOS, get_attention_os

# process_strategy_signal_event 需要的类型
try:
    from deva.naja.events import StrategySignalEvent, SignalDirection, DecisionResult
    _EVENT_TYPES_AVAILABLE = True
except ImportError:
    _EVENT_TYPES_AVAILABLE = False
    StrategySignalEvent = Any
    SignalDirection = None
    DecisionResult = None

log = logging.getLogger(__name__)

# 信号审批的置信度门槛。原先硬编码在 process_strategy_signal 里（0.4），
# 且与 DecisionFusion 的 0.3/0.5/0.7 分档是两套口径（见设计文档 G4）。
# 这里收口为单一常量，避免"改一处漏一处"。
MIN_APPROVAL_CONFIDENCE = 0.4

# 决策留痕的容量上限。dashboard 只展示"最近发生了什么决策"，
# 不需要无限增长的内存；20 条足够覆盖一轮 UI 刷新。
RECENT_DECISION_CAPACITY = 20


def get_min_approval_confidence() -> float:
    """审批置信度门槛（可用环境变量 ``NAJA_APPROVAL_CONFIDENCE`` 覆盖）。"""
    raw = os.environ.get("NAJA_APPROVAL_CONFIDENCE")
    if raw:
        try:
            return float(raw)
        except ValueError:
            log.warning(
                "[TradingCenter] 非法 NAJA_APPROVAL_CONFIDENCE=%r，回落 %s",
                raw, MIN_APPROVAL_CONFIDENCE,
            )
    return MIN_APPROVAL_CONFIDENCE


def _awakening_feedback_burst(pnl_pct: float) -> int:
    """按交易结果的显著性，决定投影几条弱信号给 ``AwakeningEngine``。

    依据：``AwakeningEngine`` 的弱信号半衰期只有 60 秒、新鲜度加权 ≈1，
    阈值是 DORMANT=3 / AWAKENING=8 / ILLUMINATED=15（按有效分数）。
    一次显著平仓结果可同时投影多个维度（策略有效性 / 环境匹配 / 执行质量 /
    市场状态变化），故按显著性给 1~5 条。

    ⚠️ 注意 DORMANT 阈值是 3，而新鲜度 `exp(-dt/60)` 恒略小于 1，
    因此**恰好 3 条**会落在 2.9999… 卡在边界（实测确认）。故显著档给 ≥4 条，
    留一条浮点余量，保证"显著结果能真的跨过阈值"而不是静默无效。

    可用 ``NAJA_AWAKENING_FEEDBACK_BURST`` 强制指定（灰调用）。
    """
    raw = os.environ.get("NAJA_AWAKENING_FEEDBACK_BURST")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    magnitude = abs(float(pnl_pct or 0.0))
    if magnitude >= 5.0:
        return 5
    if magnitude >= 2.0:
        return 4
    return 1


class TradingCenter:
    """
    交易中枢

    协调 AttentionOS、FirstPrinciplesMind、AwakenedAlaya 完成交易决策
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, attention_os=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._attention_os_param = attention_os
        return cls._instance

    def __init__(self, attention_os=None):
        if self._initialized:
            return

        # 优先使用 __new__ 中传递的参数，然后是 __init__ 中传递的参数，最后使用 get_attention_os()
        if hasattr(self, '_attention_os_param') and self._attention_os_param is not None:
            self.attention_os = self._attention_os_param
        else:
            self.attention_os = attention_os or get_attention_os()

        self._first_principles_mind = None
        self._awakened_alaya = None
        self._in_context_learner = None

        # 感知系统模块（从 AwakeningController 迁移）
        self._volatility_surface = None
        self._pre_taste = None
        self._prophet_sense = None
        self._realtime_taste = None

        self._awakened_state: Dict[str, Any] = {
            "fused_confidence": 0.5,
            "adaptive_decisions": 0,
            "fusion_note": "",
            "pre_taste_count": 0,
            "prophet_signals": 0,
            "taste_signals": 0,
            "volatility_signals": 0,
        }

        # 决策留痕：每次产出 DecisionPlan（含降级/否决路径）都记一条，
        # 供 dashboard 经查询接口读取（§6.4：UI 只吃 dict，不深入核心对象）。
        self._recent_plans: Deque[Dict[str, Any]] = deque(maxlen=RECENT_DECISION_CAPACITY)

        self._decision_orchestrator = DecisionOrchestrator(
            attention_os=self.attention_os,
            awakened_state=self._awakened_state,
            get_first_principles_mind=self._get_first_principles_mind,
            get_awakened_alaya=self._get_awakened_alaya,
            get_in_context_learner=self._get_in_context_learner,
            get_volatility_surface=self._get_volatility_surface,
            get_pre_taste=self._get_pre_taste,
            get_prophet_sense=self._get_prophet_sense,
            get_realtime_taste=self._get_realtime_taste,
            logger=log,
        )

        self._initialized = True
        
        # 🚀 事件订阅已迁移到 EventSubscriberRegistrar（应用层）
        # 不再在内部自动订阅
        
        log.info("[TradingCenter] 初始化完成")

    def set_attention_os(self, attention_os) -> None:
        """显式设置 AttentionOS（依赖注入）"""
        self.attention_os = attention_os

    def _get_first_principles_mind(self):
        """获取 FirstPrinciplesMind"""
        if self._first_principles_mind is None:
            try:
                from deva.naja.cognition.analysis.first_principles_mind import FirstPrinciplesMind
                self._first_principles_mind = FirstPrinciplesMind()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 FirstPrinciplesMind: {e}")
        return self._first_principles_mind

    def _get_awakened_alaya(self):
        """获取 AwakenedAlaya"""
        if self._awakened_alaya is None:
            try:
                from deva.naja.knowledge.alaya.awakened_alaya import AwakenedAlaya
                self._awakened_alaya = AwakenedAlaya()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 AwakenedAlaya: {e}")
        return self._awakened_alaya

    def _get_volatility_surface(self):
        """获取波动率曲面感知"""
        if self._volatility_surface is None:
            try:
                from deva.naja.radar.senses.volatility_surface import VolatilitySurfaceSense
                self._volatility_surface = VolatilitySurfaceSense()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 VolatilitySurfaceSense: {e}")
        return self._volatility_surface

    def _get_pre_taste(self):
        """获取预尝味感知"""
        if self._pre_taste is None:
            try:
                from deva.naja.radar.senses import PreTasteSense
                self._pre_taste = PreTasteSense()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 PreTasteSense: {e}")
        return self._pre_taste

    def _get_prophet_sense(self):
        """获取先知感知"""
        if self._prophet_sense is None:
            try:
                from deva.naja.radar.senses import ProphetSense
                self._prophet_sense = ProphetSense()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 ProphetSense: {e}")
        return self._prophet_sense

    def _get_realtime_taste(self):
        """获取实时尝味感知"""
        if self._realtime_taste is None:
            try:
                from deva.naja.radar.senses import RealtimeTaste
                self._realtime_taste = RealtimeTaste()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 RealtimeTaste: {e}")
        return self._realtime_taste
    
    def _get_in_context_learner(self):
        """获取上下文学习器"""
        if self._in_context_learner is None:
            try:
                from deva.naja.attention.kernel.in_context_learner import get_in_context_learner
                self._in_context_learner = get_in_context_learner()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 InContextLearner: {e}")
        return self._in_context_learner

    def _get_current_narratives(self) -> List[str]:
        """获取当前活跃的叙事列表"""
        try:
            tracker = get_narrative_tracker()
            if tracker is None:
                return []
            summary = tracker.get_summary(limit=10)
            return [item["narrative"] for item in summary]
        except Exception:
            pass
        return []

    def _get_awakening_level(self) -> str:
        """获取觉醒级别（读共享 ``AwakenedAlaya`` 的 ``awakening_engine``）。

        历史 bug（觉醒三重断点 #2）：这里读的是 ``self._awakened_state``——
        一个**从未被写入**的字典，于是恒返回 "dormant"。真正的来源是它自己
        缓存的 ``AwakenedAlaya``（决策路径 run_full_pipeline 用的是同一实例）。
        """
        alaya = self._get_awakened_alaya()
        engine = getattr(alaya, "awakening_engine", None) if alaya is not None else None
        if engine is not None:
            try:
                return str(engine.get_awakening_level())
            except Exception as e:
                log.debug(f"[TradingCenter] 读取觉醒等级失败: {e}")
        return self._awakened_state.get("awakening_level", "dormant")

    def get_awakening_level(self) -> str:
        """[公开] 当前觉醒等级（供 Manas 觉醒维度等外部读取）。"""
        return self._get_awakening_level()

    def record_trade_outcome(
        self,
        symbol: str,
        pnl_pct: float,
        *,
        strategy_id: str = "",
        strategy_name: str = "",
        position_id: str = "",
        close_reason: str = "",
    ) -> bool:
        """把一次交易结果回流成弱信号，喂给共享 ``AwakenedAlaya``（觉醒三重断点 #3）。

        闭环反馈的决策端入口。由 ``EventSubscriberRegistrar`` 订阅
        ``TradeOutcomeEvent`` 后调用，也供测试直接调用。

        ⚠️ 时效说明：``AwakeningEngine`` 的弱信号半衰期只有 **60 秒**，
        所以"觉醒等级"是**短时放大器**而非长期成长值——一次结果只会在几分钟内
        抬高等级，随后自然衰减回 dormant。要稳定提升需要**成簇**的高置信信号。

        Returns:
            True 表示信号已喂入；False 表示 AwakenedAlaya 不可用或输入非法。
        """
        alaya = self._get_awakened_alaya()
        engine = getattr(alaya, "awakening_engine", None) if alaya is not None else None
        if engine is None:
            return False
        try:
            pnl = float(pnl_pct)
        except (TypeError, ValueError):
            return False

        win = pnl > 0
        # 5% 的盈亏记满信心，不足按比例（下限 0.1，避免"零信心"信号）
        confidence = max(0.1, min(1.0, abs(pnl) / 5.0))
        burst = _awakening_feedback_burst(pnl)
        for _ in range(burst):
            try:
                engine.receive_signal(
                    signal_type="trade_outcome_win" if win else "trade_outcome_loss",
                    content=f"{symbol} {'盈利' if win else '亏损'} {pnl:.2f}% ({close_reason})",
                    confidence=confidence,
                    conditions={
                        "symbol": symbol,
                        "pnl_pct": pnl,
                        "win": win,
                        "strategy_id": strategy_id,
                        "strategy_name": strategy_name,
                        "position_id": position_id,
                        "close_reason": close_reason,
                    },
                )
            except Exception as e:
                log.debug(f"[TradingCenter] 喂觉醒弱信号失败: {e}")
                return False

        log.info(
            f"[TradingCenter] 交易结果回流: {symbol} {pnl:+.2f}% "
            f"→ 觉醒={self._get_awakening_level()} (burst={burst})"
        )
        return True

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "awakening": self._awakened_state,
            "volatility_surface": self._get_volatility_surface_state(),
        }

    def get_attention_context(self) -> Dict[str, Any]:
        """获取注意力上下文"""
        return {
            "awakening_level": self._get_awakening_level(),
            "volatility_surface": self._get_volatility_surface_state(),
            "contradiction": self._check_contradiction(),
        }

    # ── 决策留痕（DecisionPlan）────────────────────────────────────────────
    # §6.4：UI 不深入核心对象。这里只把 ``DecisionPlan.to_dict()`` 的副本
    # 存进有界队列，查询接口再返回副本，UI 拿到的是纯 dict。

    def _recent_plans_deque(self) -> Deque[Dict[str, Any]]:
        """取留痕队列；``__init__`` 早退（单例已初始化）时兜底补建。"""
        deque_ = getattr(self, "_recent_plans", None)
        if deque_ is None:
            deque_ = deque(maxlen=RECENT_DECISION_CAPACITY)
            self._recent_plans = deque_
        return deque_

    def _record_plan(self, plan: DecisionPlan, *, approved: Optional[bool] = None) -> None:
        """记录一条决策产物。任何一条 ``DecisionPlan`` 都应经此留痕。"""
        try:
            entry = plan.to_dict()
        except Exception as e:  # pragma: no cover - to_dict 不该抛
            log.debug(f"[TradingCenter] 记录 DecisionPlan 失败: {e}")
            return
        entry = dict(entry)
        entry["recorded_at"] = time.time()
        if approved is not None:
            entry["approved"] = bool(approved)
        self._recent_plans_deque().append(entry)

    def get_recent_decisions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """[公开] 最近若干条决策产物（最新在前，纯 dict 副本）。"""
        try:
            n = max(0, int(limit))
        except (TypeError, ValueError):
            n = 10
        items = list(self._recent_plans_deque())
        items.reverse()
        return [dict(item) for item in items[:n]]

    def get_latest_decision(self) -> Optional[Dict[str, Any]]:
        """[公开] 最新一条决策产物；从未产生过决策时返回 ``None``。

        刻意不兜底合成一条"看起来像"的计划——那会把"还没决策"伪装成
        "决策了"，正是本项目反复踩的静默失效。
        """
        recent = self.get_recent_decisions(limit=1)
        return recent[0] if recent else None

    def get_decision_plan_summary(self, limit: int = 10) -> Dict[str, Any]:
        """[公开] dashboard 用的决策面板数据（纯 dict）。"""
        recent = self.get_recent_decisions(limit=limit)
        approved = sum(1 for item in recent if item.get("approved") is True)
        actionable = sum(1 for item in recent if self._plan_entry_actionable(item))
        return {
            "available": bool(recent),
            "latest": recent[0] if recent else None,
            "recent": recent,
            "stats": {
                "total": len(self._recent_plans_deque()),
                "shown": len(recent),
                "approved": approved,
                "actionable": actionable,
            },
        }

    @staticmethod
    def _plan_entry_actionable(entry: Dict[str, Any]) -> bool:
        """留痕条目是否代表一次"真会动手"的计划（与 ``DecisionPlan.is_actionable`` 同口径）。"""
        from deva.naja.decision import action_severity

        return (
            bool(entry.get("should_act"))
            and action_severity(entry.get("action_type")) > 0
            and float(entry.get("size_hint") or 0.0) > 0.0
        )

    def _get_volatility_surface_state(self) -> Dict[str, Any]:
        """获取波动率曲面状态"""
        vol_surface = self._get_volatility_surface()
        if vol_surface:
            try:
                return {
                    "regime": getattr(vol_surface, 'regime', 'normal'),
                    "volatility": getattr(vol_surface, 'volatility', 0.5),
                }
            except Exception:
                pass
        return {"regime": "normal", "volatility": 0.5}

    def _check_contradiction(self) -> Dict[str, Any]:
        """检查矛盾信号"""
        return {
            "has_contradiction": False,
            "description": "",
            "severity": 0.0,
        }

    def apply_pre_taste_filter(self, signals: List, data) -> List:
        """应用预尝味过滤到信号"""
        if not signals:
            return signals

        pre_taste = self._get_pre_taste()
        if pre_taste:
            try:
                for signal in signals:
                    symbol = getattr(signal, 'symbol', None) or getattr(signal, 'stock_code', None)
                    if symbol:
                        taste_result = pre_taste.judge(symbol, data)
                        if taste_result and hasattr(signal, 'metadata'):
                            signal.metadata['pre_taste'] = taste_result
            except Exception as e:
                log.debug(f"[TradingCenter] 应用预尝味过滤失败: {e}")

        return signals

    def _full_decision_pipeline(
        self,
        market_state: Dict[str, Any],
        snapshot: Optional[Dict] = None,
    ) -> FusionOutput:
        return self._decision_orchestrator.run_full_pipeline(market_state, snapshot)

    def _fuse_decisions(
        self,
        kernel_output,
        fp_insights: List[Dict],
        awakening_level: str
    ) -> FusionOutput:
        return self._decision_orchestrator.fuse_decisions(kernel_output, fp_insights, awakening_level)

    def get_harmony(self) -> Dict[str, Any]:
        """获取当前和谐状态"""
        return self.attention_os.get_harmony()

    def get_attention_os(self) -> AttentionOS:
        """获取 AttentionOS"""
        return self.attention_os

    def process_datasource_data(self, datasource_id: str, data: Any) -> None:
        """
        处理数据源数据（兼容旧接口）

        Args:
            datasource_id: 数据源ID
            data: 数据
        """
        try:
            if isinstance(data, dict):
                self.attention_os.schedule_market(data)
        except Exception as e:
            log.warning(f"[TradingCenter] process_datasource_data 失败: {e}")

    def process_strategy_signal_event(self, event: StrategySignalEvent) -> Dict[str, Any]:
        """
        处理 StrategySignalEvent 事件（新架构）
        
        将事件转换为旧格式，调用原有的 process_strategy_signal 方法，
        然后将结果转换为新格式的决策字典。
        """
        try:
            start_time = time.time()
            
            # 转换事件为旧格式（兼容现有逻辑）
            signal_dict = {
                'strategy_id': event.strategy_name,
                'stock_code': event.symbol,
                'stock_name': event.symbol.split('.')[0] if '.' in event.symbol else event.symbol,
                'signal_type': 'buy' if event.is_buy else ('sell' if event.is_sell else 'neutral'),
                'price': event.current_price,
                'confidence': event.confidence,
                'position_size': event.position_size,
                'stop_loss_pct': event.stop_loss_pct,
                'take_profit_pct': event.take_profit_pct,
                'narrative_tags': event.narrative_tags,
                'block_name': event.block_name,
                'timeframe': event.timeframe,
                'timestamp': event.timestamp,
                'metadata': event.metadata,
                'event_type': 'strategy_signal',
                'direction': event.direction.value,
            }
            
            log.info(f"[TradingCenter] 收到策略信号事件: {event.strategy_name} {event.symbol} {event.direction.value} @ {event.current_price}")
            
            # 调用原来的处理方法
            result = self.process_strategy_signal(signal_dict)
            
            # 构建结果字典
            if result is None:
                # 处理失败
                return {
                    'decision': DecisionResult.REJECTED,
                    'approval_score': 0.0,
                    'approved_symbol': event.symbol,
                    'approved_direction': event.direction,
                    'position_size': 0.0,
                    'entry_price': event.current_price,
                    'reason': "处理过程失败",
                    'subsystems_opinions': {},
                }
            
            # 转换结果
            processing_time = time.time() - start_time
            approved = result.get('approved', False)
            
            if approved:
                decision = DecisionResult.APPROVED
                approval_score = result.get('final_confidence', event.confidence)
                action_type = result.get('action_type', 'buy')
                
                # 构建子系统意见字典
                subsystems_opinions = {
                    "manas_engine": {
                        "score": result.get('manas_score', 0.5),
                        "reason": f"Manas评分: {result.get('manas_score', 0.5):.3f}"
                    },
                    "attention_os": {
                        "score": result.get('final_confidence', 0.5),
                        "reason": f"最终置信度: {result.get('final_confidence', 0.5):.3f}"
                    }
                }
                
                return {
                    'decision': decision,
                    'approval_score': approval_score,
                    'approved_symbol': event.symbol,
                    'approved_direction': (event.direction if action_type in ['buy', 'sell'] 
                                          else SignalDirection.NEUTRAL),
                    'position_size': event.position_size,
                    'entry_price': event.current_price,
                    'stop_loss_price': (event.current_price * (1 - event.stop_loss_pct/100) 
                                      if event.stop_loss_pct else None),
                    'take_profit_price': (event.current_price * (1 + event.take_profit_pct/100) 
                                        if event.take_profit_pct else None),
                    'reason': f"批准执行: {', '.join(result.get('reasoning', []))}"[:200],
                    'subsystems_opinions': subsystems_opinions,
                    'processing_time_ms': processing_time * 1000,
                }
            else:
                decision = DecisionResult.REJECTED
                return {
                    'decision': decision,
                    'approval_score': result.get('final_confidence', 0.3),
                    'approved_symbol': event.symbol,
                    'approved_direction': SignalDirection.NEUTRAL,
                    'position_size': 0.0,
                    'entry_price': event.current_price,
                    'reason': f"否决执行: {', '.join(result.get('reasoning', ['置信度不足']))}"[:200],
                    'subsystems_opinions': {
                        "attention_os": {
                            "score": result.get('final_confidence', 0.3),
                            "reason": f"置信度不足: {result.get('final_confidence', 0.3):.3f} < 0.4"
                        }
                    },
                    'processing_time_ms': processing_time * 1000,
                }
                
        except Exception as e:
            log.error(f"[TradingCenter] process_strategy_signal_event 失败: {e}")
            return {
                'decision': DecisionResult.REJECTED,
                'approval_score': 0.0,
                'approved_symbol': event.symbol if hasattr(event, 'symbol') else '',
                'approved_direction': SignalDirection.NEUTRAL,
                'position_size': 0.0,
                'entry_price': 0.0,
                'reason': f"处理异常: {str(e)}",
                'subsystems_opinions': {},
                'processing_time_ms': 0.0,
            }

    def process_strategy_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理策略信号，经过 TradingCenter 决策后再执行

        Args:
            signal: 策略信号，包含 strategy_id, stock_code, stock_name,
                    signal_type, price, confidence, timestamp

        Returns:
            决策结果 dict（含 approved 字段），或 None（异常时）
        """
        try:
            strategy_id = signal.get('strategy_id', 'unknown')
            stock_code = signal.get('stock_code', '')
            stock_name = signal.get('stock_name', stock_code)
            signal_type = signal.get('signal_type', 'buy').upper()
            price = signal.get('price', 0)
            confidence = signal.get('confidence', 0.5)

            log.info(f"[TradingCenter] 收到策略信号: {strategy_id} {stock_code} {signal_type} @ {price}")

            if self.attention_os is None:
                log.warning("[TradingCenter] attention_os 不可用，使用简化决策")
                # 降级路径：Manas 不可用，只能按信号自带置信度粗分档。
                # 这不是"融合层重新定义档位"，而是判断层缺席时的兜底（已在 reasons 标注）。
                if confidence >= 0.7:
                    fallback_action = "act_fully"
                elif confidence >= 0.5:
                    fallback_action = "act_carefully"
                elif confidence > 0:
                    fallback_action = "act_minimally"
                else:
                    fallback_action = "hold"
                fallback_plan = DecisionPlan(
                    symbol=stock_code,
                    side=side_from_signal_type(signal_type),
                    action_type=fallback_action,
                    confidence=confidence,
                    should_act=fallback_action != "hold",
                    gate_reason="attention_os 不可用：按信号置信度兜底分档",
                    reasons=["简化决策：attention_os 不可用"],
                    source_signal=signal,
                )
                self._record_plan(fallback_plan, approved=True)
                return {
                    'approved': True,
                    'action_type': 'buy',
                    'final_confidence': confidence,
                    'reasoning': ['简化决策：attention_os 不可用'],
                    'plan': fallback_plan.to_dict(),
                }

            market_state = {
                'market_phase': 'trading',
                'hotspot_signal': signal,
                'focus_stock': stock_code,
                'focus_stock_name': stock_name,
                'signal_confidence': confidence,
                'signal_strategy': strategy_id,
            }

            narratives = self._get_current_narratives()
            if narratives:
                market_state['narratives'] = narratives

            snapshot = {'symbol': stock_code, 'price': price}

            fusion = self._full_decision_pipeline(market_state, snapshot)

            approval_threshold = get_min_approval_confidence()
            approved = fusion.should_act and fusion.fused_confidence >= approval_threshold

            # 决策产物：一条 DecisionPlan（动什么 / 怎么动 / 为什么）。
            # size_hint 由 decision.sizing 单一口径产出（D2）；此处先留 0。
            plan = DecisionPlan.from_fusion(
                fusion,
                symbol=stock_code,
                side=side_from_signal_type(signal_type),
                source_signal=signal,
                size_hint=compute_plan_size_hint(fusion),
            )

            if approved:
                log.info(f"[TradingCenter] ✅ 信号批准: {stock_code} {fusion.action_type} "
                        f"(confidence={fusion.fused_confidence:.3f}, manas={fusion.manas_score:.3f})")
                self._record_plan(plan, approved=True)
                return {
                    'approved': True,
                    'action_type': fusion.action_type,
                    'final_confidence': fusion.fused_confidence,
                    'harmony_strength': fusion.harmony_strength,
                    'manas_score': fusion.manas_score,
                    'timing_score': fusion.timing_score,
                    'regime_score': fusion.regime_score,
                    'awakening_level': fusion.awakening_level,
                    'reasoning': fusion.final_decision.get('reasoning', []),
                    'recalled_patterns': fusion.recalled_patterns,
                    'signal': signal,
                    'plan': plan.to_dict(),
                }
            else:
                log.info(f"[TradingCenter] ❌ 信号否决: {stock_code} "
                        f"(confidence={fusion.fused_confidence:.3f} < {approval_threshold})")
                self._record_plan(plan, approved=False)
                return {
                    'approved': False,
                    'action_type': fusion.action_type,
                    'final_confidence': fusion.fused_confidence,
                    'reasoning': fusion.final_decision.get('reasoning', []),
                    'signal': signal,
                    'plan': plan.to_dict(),
                }

        except Exception as e:
            log.error(f"[TradingCenter] process_strategy_signal 失败: {e}")
            return None

    def register_datasource(self, datasource_id: str) -> None:
        """注册数据源（兼容旧接口）"""
        pass

    def unregister_datasource(self, datasource_id: str) -> None:
        """注销数据源（兼容旧接口）"""
        pass

    def get_cached_market_time(self) -> str:
        """获取缓存的市场时间（兼容旧接口）"""
        return ""


def get_trading_center() -> TradingCenter:
    """获取 TradingCenter 单例。

    优先从 AppContainer 获取（生产环境）；AppContainer 不可用时
    （如测试环境）回退到直接实例化单例——TradingCenter 本身是
    单例，其 __init__ 会通过 get_attention_os() 获取 AttentionOS。
    """
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container and container.trading_center:
        return container.trading_center
    return TradingCenter()
