"""
QueryStateUpdater - 事件驱动的QueryState更新器

统一处理各类事件并更新QueryState，实现松耦合的架构设计。
"""

import logging
import threading
import time
import hashlib
from typing import Dict, Any, Iterable, List, Optional

from deva.naja.events import get_event_bus

log = logging.getLogger(__name__)

_query_state_updater: Optional["QueryStateUpdater"] = None
_query_state_updater_lock = threading.Lock()

# 市场级状态（regime / 宏观流动性 / 风险偏好）的最小样本量。
# 热点事件按频率档位分批推送（实测有 6 / 12 / 18 只的批次），拿 6 个标的的
# 涨跌比去判 regime，噪声就能把「trend_down」翻成「trend_up」。整批快照
# （61~63 只）每分钟都会来，所以薄样本批次直接不参与市场级更新。
MIN_MARKET_SAMPLE = 10


class QueryStateUpdater:
    """
    事件驱动的QueryState更新器
    
    订阅各类事件并统一更新QueryState，实现松耦合的架构设计。
    """
    
    def __init__(self, query_state=None):
        self.qs = query_state
        self._event_bus = get_event_bus()
        self._subscribe_to_events()
        self._hotspot_counter = 0
        self._hotspot_log_interval = 10
        self._last_data_hash: Optional[str] = None
        self._last_symbol_count = 0
        # 因「热点事件未携带真实行情」而跳过更新的累计次数（节流告警用，见
        # _note_skipped_hotspot —— 跳过是刻意的，但**不许静默**）
        self._hotspot_skip_count = 0
        self._hotspot_skip_log_every = 20
        self._min_market_sample = MIN_MARKET_SAMPLE
        # 持仓快照刷新：portfolio_state 此前只有死代码 `state.py::update()` 写，
        # 线上恒为 None → compute_priority 的「已持仓折价」和 risk_bias 的
        # 持仓调整全部空转。这里起一个轻量后台线程，每 15 秒从
        # VirtualPortfolio 拉一次（不订阅回调，避免漏事件导致快照卡住）。
        self._portfolio_stop = threading.Event()
        self._portfolio_thread: Optional[threading.Thread] = None
        self._fundamental_stop = threading.Event()
        self._fundamental_thread: Optional[threading.Thread] = None
        if query_state is not None:
            self._start_portfolio_refresh()
            self._warm_start_fundamentals()
            self._start_fundamental_refresh()
        log.info("[QueryStateUpdater] 初始化完成")

    def set_query_state(self, query_state):
        """显式设置 QueryState（依赖注入）"""
        self.qs = query_state
    
    def _subscribe_to_events(self):
        """订阅各类事件"""
        try:
            # 订阅热点计算事件
            self._event_bus.subscribe(
                'HotspotComputedEvent',
                self._on_hotspot_computed,
                priority=10
            )
            
            # 订阅全局市场数据事件
            self._event_bus.subscribe(
                'GlobalMarketDataEvent',
                self._on_global_market_data,
                priority=9
            )
            
            # 订阅新闻聚焦事件
            self._event_bus.subscribe(
                'TextFocusedEvent',
                self._on_text_focused,
                priority=8
            )
            
            # 订阅策略信号事件
            self._event_bus.subscribe(
                'StrategySignalEvent',
                self._on_strategy_signal,
                priority=7
            )
            
            # 订阅认知洞察事件
            self._event_bus.subscribe(
                'CognitiveInsightEvent',
                self._on_cognitive_insight,
                priority=6
            )
            
            # 订阅叙事状态事件
            self._event_bus.subscribe(
                'NarrativeStateEvent',
                self._on_narrative_state,
                priority=6
            )
            
            # 订阅流动性信号事件
            self._event_bus.subscribe(
                'LiquiditySignalEvent',
                self._on_liquidity_signal,
                priority=6
            )
            
            # 订阅美林时钟事件
            self._event_bus.subscribe(
                'MerrillClockEvent',
                self._on_merrill_clock,
                priority=6
            )
            
            log.info("[QueryStateUpdater] 已订阅所有事件")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 订阅事件失败: {e}")
    
    def _on_hotspot_computed(self, event):
        """处理热点计算完成事件
        
        使用真实市场数据（returns/volumes/prices）更新 QueryState。
        如果数据未发生变化，则跳过更新以避免无意义的循环。
        """
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 标的清单以事件的 `symbols` 为准（与 returns/volumes/prices 逐位对齐）。
            # ❗不能用 `symbol_weights.keys()`：那是 WeightPool 的**注册表全集**
            #   （进程内注册过的所有 symbol 的并集，`register_symbol` 只增不删），
            #   而三件套只覆盖**当次快照**（分批拉取 + 噪音过滤后条数会少几只）。
            #   拿注册表长度去校验快照数组，长度永远不等 → 每轮都跳过。
            #   线上实测：注册表 62 只、当次快照 55~61 只，一个进程内累计跳过 500 次，
            #   QueryState 的市场维度（regime/流动性/风险偏好）自启动后一直停在首扫值。
            #   兼容老事件：没有 `symbols` 字段时退回 symbol_weights 的 key。
            symbols = list(getattr(event, "symbols", None) or [])
            if not symbols:
                symbols = list(event.symbol_weights.keys())
            if not symbols:
                log.debug("[QueryStateUpdater] 热点事件没有股票数据")
                return

            # ❗ returns / volumes / prices **必须全部**是事件携带的真实行情，
            #   缺任何一项就跳过本次更新 —— 绝不用 symbol_weights 顶替。
            #   旧写法在缺数据时拿 `symbol_weights[s] * 100` 冒充涨跌幅，而
            #   symbol_weights 的量级是 1.0~1.45，×100 就成了「平均涨幅 142%」。
            #   QueryState 是与 GlobalMarketScanner 共享的单例，这个伪造值会
            #   **覆盖**真市场数据，并被 RegimeEngine 拿去算 regime_score 与
            #   宏观流动性(macro_liquidity_signal)，把决策的环境输入变成人造数。
            #   实测：线上 /api/query/state 的 avg_change=142.3390579620452 与
            #   symbol_weights 均值×100 逐位相等（Δ=0），而同一批 hot_stocks
            #   里的真实 change_pct 是 +1.67 / −3.72 / −3.94 …
            #   宁可少更新一次，也不给决策喂假数。
            if not self._has_real_market_data(event, len(symbols)):
                self._note_skipped_hotspot(event, len(symbols))
                return
            min_sample = getattr(self, "_min_market_sample", MIN_MARKET_SAMPLE)
            if len(symbols) < min_sample:
                log.debug(
                    "[QueryStateUpdater] 热点事件(%s)仅 %d 个标的 < %d，薄样本跳过市场级更新",
                    getattr(event, "market", "?"), len(symbols), min_sample,
                )
                return
            returns = list(event.returns)
            volumes = list(event.volumes)
            prices = list(event.prices)

            # 变化检测：数据未变则跳过更新
            data_repr = f"{','.join(symbols)}|{','.join(f'{r:.2f}' for r in returns[:100])}"
            data_hash = hashlib.md5(data_repr.encode()).hexdigest()
            if data_hash == self._last_data_hash:
                # 数据无变化，静默跳过
                return
            self._last_data_hash = data_hash

            # 更新QueryState（使用真实数据）
            self.qs.update_from_market(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                timestamp=event.timestamp,
                source="hotspot",
            )
            
            # 只在数据真正变化时记录日志
            if len(symbols) != self._last_symbol_count:
                log.info(f"[QueryStateUpdater] 热点数据更新({event.market}): {len(symbols)}个股票")
                self._last_symbol_count = len(symbols)
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理热点事件失败: {e}")

    @staticmethod
    def _has_real_market_data(event, n_symbols: int) -> bool:
        """事件是否携带**逐标的、长度对齐**的真实行情三件套。

        三个字段都要有：`update_from_market` 会分别用 returns 算涨跌/波动、
        用 volumes 算量能离散度、用 prices 算派生特征，少一个就会出现
        「一半真一半假」的口径混用。
        """
        for field in ("returns", "volumes", "prices"):
            values = getattr(event, field, None)
            if not isinstance(values, (list, tuple)) or len(values) != n_symbols:
                return False
        return True

    def _note_skipped_hotspot(self, event, n_symbols: int) -> None:
        """热点事件缺真实行情 → 跳过更新，并留痕（节流告警，绝不静默）。

        为什么宁可跳过：QueryState 是 scanner 与本更新器**共享**的单例，
        这里的写入会覆盖 scanner 刚写的真市场数据。用权重凑出来的假数
        比「这次不更新」危险得多（后者只是旧值，前者是错的数）。
        """
        self._hotspot_skip_count += 1
        n = self._hotspot_skip_count
        if n == 1 or n % self._hotspot_skip_log_every == 0:
            log.warning(
                "[QueryStateUpdater] 热点事件(%s, %d 个标的)未携带真实行情"
                "(returns/volumes/prices)，跳过 QueryState 更新（累计 %d 次）"
                "—— 拒绝用 symbol_weights 伪造涨跌幅",
                getattr(event, "market", "?"), n_symbols, n,
            )

    def _on_global_market_data(self, event):
        """处理全局市场数据事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 从事件中提取数据
            symbols = event.symbols
            returns = event.returns
            volumes = event.volumes
            prices = event.prices
            
            if not symbols:
                log.debug("[QueryStateUpdater] 全局市场事件没有股票数据")
                return
            
            # 更新QueryState
            self.qs.update_from_market(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                timestamp=event.timestamp,
                source="scanner",
            )
            
            log.info(f"[QueryStateUpdater] 已更新全局市场数据: {len(symbols)}个股票")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理全局市场事件失败: {e}")
    
    def _on_text_focused(self, event):
        """处理文本聚焦事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            log.debug(f"[QueryStateUpdater] source={event.source}, importance={event.importance_score}, title={event.title[:30] if event.title else None}...")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理文本事件失败: {e}")
    
    def _on_strategy_signal(self, event):
        """处理策略信号事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 这里可以根据需要更新QueryState中的策略相关字段
            # 例如更新策略状态、信号强度等
            log.debug(f"[QueryStateUpdater] 处理策略信号: {event.strategy_name} {event.symbol}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理策略信号失败: {e}")
    
    def _on_cognitive_insight(self, event):
        """处理认知洞察事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新认知洞察数据
            self.qs.cognitive_insights = {
                "insights": event.insights,
                "confidence": event.confidence,
                "timeliness": time.time() - event.timestamp
            }
            
            log.info(f"[QueryStateUpdater] 已更新认知洞察: {len(event.insights)}个洞察, 置信度={event.confidence:.2f}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理认知洞察事件失败: {e}")
    
    def _on_narrative_state(self, event):
        """处理叙事状态事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新叙事状态数据
            self.qs.narrative_state = {
                "current_narratives": event.current_narratives,
                "narrative_strength": event.narrative_strength,
                "narrative_risk": event.narrative_risk,
                "sentiment_score": event.sentiment_score
            }
            
            narrative_list = event.current_narratives[:5]
            excess = len(event.current_narratives) - 5
            narrative_str = f"{narrative_list}{f'... (+{excess})' if excess > 0 else ''}"
            log.info(f"[QueryStateUpdater] 已更新叙事状态: {narrative_str}, 强度={event.narrative_strength:.2f}, 风险={event.narrative_risk:.2f}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理叙事状态事件失败: {e}")
    
    def _on_liquidity_signal(self, event):
        """处理流动性信号事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新流动性状态数据
            self.qs.liquidity_state = {
                "prediction": event.prediction,
                "risk": event.risk,
                "signal": event.signal
            }
            
            log.info(f"[QueryStateUpdater] 已更新流动性信号: 预测={event.prediction:.2f}, 风险={event.risk:.2f}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理流动性信号事件失败: {e}")
    
    def _on_merrill_clock(self, event):
        """处理美林时钟事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新经济周期数据
            self.qs.economic_cycle = {
                "phase": event.phase,
                "asset_allocation": event.asset_allocation
            }
            
            log.info(f"[QueryStateUpdater] 已更新经济周期: 阶段={event.phase}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理美林时钟事件失败: {e}")
    
    def get_query_state(self):
        """获取QueryState实例"""
        return self.qs

    # ------------------------------------------------------------------
    # 持仓快照
    # ------------------------------------------------------------------
    def _start_portfolio_refresh(self, interval: float = 15.0) -> None:
        """启动持仓快照刷新线程（daemon，随进程退出）。"""
        if self._portfolio_thread is not None:
            return

        def _loop():
            while True:
                try:
                    self.refresh_portfolio_state()
                except Exception as e:  # pragma: no cover - 兜底，线程不能死
                    log.debug("[QueryStateUpdater] 持仓快照刷新异常: %s", e)
                if self._portfolio_stop.wait(interval):
                    break

        self._portfolio_thread = threading.Thread(
            target=_loop, name="qs-portfolio-refresh", daemon=True
        )
        self._portfolio_thread.start()

    def refresh_portfolio_state(self, portfolio=None) -> bool:
        """把 VirtualPortfolio 的持仓压成 QueryState.portfolio_state。

        字段契约（消费方只依赖这四个键）：
        * ``held_symbols``：小写代码列表，与 attention_focus 的键同一口径；
        * ``total_return``：百分数（3.5 表示 +3.5%），与 state.py 的阈值一致；
        * ``concentration``：持仓市值 / 总资金，0~1；
        * ``position_count`` / ``available_capital``：展示用。
        """
        if not self.qs:
            return False
        try:
            if portfolio is None:
                from deva.naja.application import get_app_container
                container = get_app_container()
                portfolio = getattr(container, "virtual_portfolio", None) if container else None
            if portfolio is None:
                return False

            positions = portfolio.get_all_positions(status="OPEN") or []
            summary = portfolio.get_summary() or {}

            held = sorted({
                str(getattr(p, "stock_code", "") or "").strip().lower()
                for p in positions
                if getattr(p, "stock_code", None)
            })
            total_capital = float(summary.get("total_capital") or 0.0)
            total_value = float(summary.get("total_value") or 0.0)

            self.qs.portfolio_state = {
                "held_symbols": held,
                "position_count": len(held),
                "total_return": float(summary.get("total_return") or 0.0),
                "profit_loss": float(summary.get("total_profit_loss") or 0.0),
                "concentration": (total_value / total_capital) if total_capital > 0 else 0.0,
                "total_value": total_value,
                "available_capital": float(summary.get("available_capital") or 0.0),
            }
            self.qs.mark_field(
                "portfolio_state", source="virtual_portfolio", sample_size=len(held)
            )
            return True
        except Exception as e:
            log.debug("[QueryStateUpdater] 获取持仓快照失败: %s", e)
            return False

    def stop(self) -> None:
        """停止后台刷新线程。"""
        self._portfolio_stop.set()
        self._fundamental_stop.set()

    # ------------------------------------------------------------------
    # 基本面裁决（季频，每 6 小时刷一次）
    # ------------------------------------------------------------------
    def refresh_fundamentals(self, symbols: Optional[Iterable[str]] = None) -> Dict[str, str]:
        """给持仓 + 关注标的算一遍基本面档位，写进 QueryState.fundamentals。

        刻意做得慢：5 年日线 + SEC 全量 facts，单只 1~3 秒。所以放在后台线程里
        每 6 小时跑一次，而不是像行情那样秒级刷新。财报本来就是季频。

        Returns:
            {symbol: tier}；失败/无财报的标的不会写入（``None ≠ 中性``）。
        """
        if not self.qs:
            return {}
        try:
            from deva.naja.fundamental.service import get_fundamental_service

            service = get_fundamental_service()
            if symbols is None:
                symbols = self._fundamental_universe()
            out: Dict[str, str] = {}
            for symbol in symbols:
                try:
                    result = service.evaluate(symbol)
                except Exception as e:  # noqa: BLE001 - 单只失败不影响其他
                    log.debug("[QueryStateUpdater] %s 基本面评估失败: %s", symbol, e)
                    continue
                if not result.get("ok"):
                    if result.get("no_fundamental"):
                        # ETF/基金：**确实没有**企业财报。写显式 NA，
                        # 让环境门知道这是「结构性无数据」，不是「没取到」。
                        self.qs.set_fundamental(
                            symbol,
                            {
                                "tier": "NA",
                                "total": 0.0,
                                "allows_dip": False,
                                "forward_scale": 1.0,
                                "flags": [],
                                "note": "ETF/基金无企业财报",
                                "as_of": result.get("as_of"),
                            },
                            source="fundamental_service",
                        )
                    else:
                        # 取数失败/过期：删掉旧档位，别让它冒充新鲜结论
                        self.qs.set_fundamental(symbol, None, source="fundamental")
                    out[symbol] = str(result.get("tier") or "NA")
                    continue
                self.qs.set_fundamental(
                    symbol,
                    {
                        "tier": result.get("tier"),
                        "total": result.get("total"),
                        "allows_dip": bool(result.get("allows_dip")),
                        "forward_scale": result.get("forward_scale"),
                        "pe": (result.get("valuation") or {}).get("pe"),
                        "pe_percentile": (result.get("valuation") or {}).get("pe_percentile"),
                        "pb": (result.get("valuation") or {}).get("pb"),
                        "pb_percentile": (result.get("valuation") or {}).get("pb_percentile"),
                        "roe": (result.get("fundamental") or {}).get("roe"),
                        "flags": (result.get("score") or {}).get("flags") or [],
                        "period_end": (result.get("fundamental") or {}).get("period_end"),
                        "basis": (result.get("fundamental") or {}).get("basis"),
                        "as_of": result.get("as_of"),
                    },
                    source="fundamental_service",
                )
                out[symbol] = str(result.get("tier"))
            if out:
                log.info("[QueryStateUpdater] 基本面裁决更新: %s", out)
            return out
        except Exception as e:  # pragma: no cover - 不能影响主流程
            log.warning("[QueryStateUpdater] 基本面刷新失败: %s", e)
            return {}

    def _warm_start_fundamentals(self) -> int:
        """用上一次落库的估值结果预热 QueryState。

        没有这一步时，每次重启都会让 ``fundamentals`` 空白 1~2 分钟，
        环境门把空白读成「不知道」→ 正 T 自动打七折。而这份数据一天只变一次，
        重启丢掉它没有任何道理。
        """
        try:
            from deva.naja.fundamental.service import get_fundamental_service

            service = get_fundamental_service()
            count = 0
            for symbol in self._fundamental_universe():
                payload = service.warm_payload(symbol)
                if not payload:
                    continue
                ts = payload.pop("_computed_at", None)
                payload.pop("_warm", None)
                self.qs.set_fundamental(
                    symbol, payload, source="warm_start", ts=ts
                )
                count += 1
            if count:
                log.info("[QueryStateUpdater] 基本面预热 %s 只标的", count)
            return count
        except Exception as e:  # pragma: no cover
            log.debug("[QueryStateUpdater] 基本面预热失败: %s", e)
            return 0

    def _fundamental_universe(self) -> List[str]:
        """持仓 + 核心标的清单。去重后保持稳定顺序。"""
        symbols: List[str] = []
        try:
            from deva.naja.application import get_app_container

            container = get_app_container()
            portfolio = getattr(container, "virtual_portfolio", None) if container else None
            if portfolio is not None:
                for p in portfolio.get_all_positions(status="OPEN") or []:
                    code = str(getattr(p, "stock_code", "") or "").strip()
                    if code:
                        symbols.append(code)
        except Exception:
            pass
        try:
            from deva.naja.bandit.core_holdings import load_core_holdings

            for spec in load_core_holdings():
                code = str(getattr(spec, "code", "") or "").strip()
                if code:
                    symbols.append(code)
        except Exception:
            pass
        seen = set()
        out = []
        for s in symbols:
            key = s.strip()
            if key and key.lower() not in seen:
                seen.add(key.lower())
                out.append(key)
        return out

    def _start_fundamental_refresh(self, interval: float = 6 * 3600.0,
                                   initial_delay: float = 60.0) -> None:
        """启动基本面刷新线程：错开启动高峰，等 1 分钟再算第一轮。"""
        if self._fundamental_thread is not None:
            return

        def _loop():
            if self._fundamental_stop.wait(initial_delay):
                return
            while True:
                try:
                    self.refresh_fundamentals()
                except Exception as e:  # pragma: no cover
                    log.debug("[QueryStateUpdater] 基本面线程异常: %s", e)
                if self._fundamental_stop.wait(interval):
                    break

        self._fundamental_thread = threading.Thread(
            target=_loop, name="qs-fundamental-refresh", daemon=True
        )
        self._fundamental_thread.start()


def get_query_state_updater() -> QueryStateUpdater:
    """获取 QueryStateUpdater 单例。

    优先从 AppContainer 获取（生产环境）；AppContainer 不可用时
    （如测试环境）回退到模块级单例缓存。
    """
    global _query_state_updater
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container and container.query_state_updater:
        return container.query_state_updater
    if _query_state_updater is None:
        with _query_state_updater_lock:
            if _query_state_updater is None:
                _query_state_updater = QueryStateUpdater()
    return _query_state_updater
