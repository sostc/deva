"""
QueryState - 全局查询状态

维护系统当前的注意力焦点状态
包含价值观系统集成
"""

import time
from collections import deque
import numpy as np
from typing import Dict, List, Optional, Any


#: 每个字段的“保鲜期”（秒）。读方据此判断这个结论还能不能用 ——
#: QueryState 是进程内快照，没有任何字段会自己过期，不标 TTL 就只能
#: 无限期沿用旧值（历史上 regime 曾停在启动首扫 38 分钟）。
FIELD_TTL: Dict[str, float] = {
    "market_regime": 180.0,
    "macro_liquidity_signal": 300.0,
    "risk_bias": 300.0,
    "attention_focus": 180.0,
    "narrative_state": 1800.0,
    "cognitive_insights": 3600.0,
    "liquidity_state": 1800.0,
    "economic_cycle": 86400.0,
    "portfolio_state": 120.0,
    "strategy_state": 600.0,
    # 季频数据：7 天。财报一年只变四次，日频刷新没有意义，但也不能无限期沿用
    "fundamentals": 7 * 86400.0,
}

#: regime 聚合窗口：单批快照 12~62 只不等，直接覆盖会让 regime 跟着批次抖。
#: 60 秒内的批次按样本量加权 —— 这样 62 只的整批比 12 只的档位批次更有话语权。
REGIME_WINDOW_SECONDS = 60.0

#: 量能基准：单标的累计成交量增量 / 间隔秒数，与自身 EMA 比。
VOL_RATE_EMA_ALPHA = 0.15
VOL_MIN_INTERVAL = 5.0
VOL_MAX_INTERVAL = 600.0


class QueryState:
    """
    全局 Query 状态

    属性:
        strategy_state: 当前策略状态
        portfolio_state: 当前持仓状态
        market_regime: 市场状态（趋势/震荡）
        attention_focus: 当前注意力焦点
        risk_bias: 风险偏好 [0, 1]
        active_value_type: 当前激活的价值观类型
        value_system: 价值观系统引用
        last_decision_reason: 最后决策的理由
    """

    def __init__(self, value_system=None):
        self.strategy_state = {}
        self.portfolio_state = {}
        self.market_regime = {
            "type": "neutral",
            "timestamp": time.time(),
            "up_ratio": 0.5,
            "down_ratio": 0.5,
            "avg_change": 0.0,
            "change_std": 0.0,
        }
        self.attention_focus = {}
        self.risk_bias = 0.5
        self._market_history = {
            "returns": [],
            "volumes": [],
            "symbols": [],
            "last_update": 0,
        }
        self._value_system = value_system
        self.active_value_type = "trend"
        self.last_decision_reason = ""
        self.macro_liquidity_signal = 0.5
        
        # 认知系统相关字段
        self.narrative_state = {
            "current_narratives": [],
            "narrative_strength": 0.0,
            "narrative_risk": 0.0,
            "sentiment_score": 0.5
        }
        
        self.cognitive_insights = {
            "insights": [],
            "confidence": 0.5,
            "timeliness": 0.0
        }
        
        self.liquidity_state = {
            "prediction": 0.5,
            "risk": 0.0,
            "signal": 0.5
        }
        
        self.economic_cycle = {
            "phase": "unknown",
            "asset_allocation": {}
        }

        # 每只标的的基本面裁决：{symbol: {tier, total, allows_dip, pe, pe_percentile, ...}}
        # 这是**按标的**的结论，不是市场级信号，所以单独放在这里而不是塞进 market_regime。
        self.fundamentals: Dict[str, Dict[str, Any]] = {}

        # ---- 字段元数据：谁、什么时候、用多少样本写的 ----
        # 没有这层信息时，「值为 0.5」既可能是中性，也可能是从没写过。
        self._field_meta: Dict[str, Dict[str, Any]] = {
            field: {"ts": 0.0, "source": "init", "sample_size": 0}
            for field in FIELD_TTL
        }

        # regime 聚合窗口：[(ts, n, up, down, flat, signed_sum, abs_sum, sq_sum)]
        self._regime_window: deque = deque(maxlen=60)

        # 量能基准：symbol -> (累计成交量, 时间戳)
        self._vol_snapshot: Dict[str, tuple] = {}
        # 全市场成交量速率（股/秒）的 EMA，用来判断「放量还是缩量」
        self._vol_rate_ema: Optional[float] = None
        # 最近一次流动性信号的分解，便于解释（对外只读）
        self.liquidity_components: Dict[str, float] = {}

    def set_value_system(self, value_system):
        """显式设置 ValueSystem（依赖注入）"""
        self._value_system = value_system

    # ------------------------------------------------------------------
    # 字段元数据 / 新鲜度
    # ------------------------------------------------------------------
    def _mark(self, field: str, ts: Optional[float] = None,
              source: str = "", sample_size: int = 0) -> None:
        """记录某字段本次写入的时间、来源与样本量（内部写入口统一走这里）。"""
        self._field_meta[field] = {
            "ts": float(ts if ts is not None else time.time()),
            "source": str(source or ""),
            "sample_size": int(sample_size or 0),
        }

    def mark_field(self, field: str, ts: Optional[float] = None,
                   source: str = "", sample_size: int = 0) -> None:
        """公开的字段留痕入口（供 QueryStateUpdater 等外部写入方调用）。"""
        self._mark(field, ts=ts, source=source, sample_size=sample_size)

    def field_age(self, field: str, now: Optional[float] = None) -> Optional[float]:
        """字段年龄（秒）。从未写过返回 None —— 与「刚写过」严格区分。"""
        meta = self._field_meta.get(field)
        if not meta or not meta.get("ts"):
            return None
        return max(0.0, (now if now is not None else time.time()) - float(meta["ts"]))

    def is_stale(self, field: str, now: Optional[float] = None) -> bool:
        """字段是否已过期（从未写入也算过期：不确定就不该当确定用）。"""
        age = self.field_age(field, now=now)
        if age is None:
            return True
        return age > FIELD_TTL.get(field, 300.0)

    def health(self, now: Optional[float] = None) -> Dict[str, Any]:
        """所有字段的新鲜度体检。供 API / 决策侧判断「这个结论还能不能用」。"""
        ts = now if now is not None else time.time()
        fields: Dict[str, Dict[str, Any]] = {}
        stale_fields: List[str] = []
        for name, ttl in FIELD_TTL.items():
            meta = self._field_meta.get(name, {})
            age = self.field_age(name, now=ts)
            stale = age is None or age > ttl
            if stale:
                stale_fields.append(name)
            fields[name] = {
                "age": None if age is None else round(age, 1),
                "ttl": ttl,
                "stale": stale,
                "source": meta.get("source", ""),
                "sample_size": meta.get("sample_size", 0),
            }
        live = [n for n in FIELD_TTL if n not in stale_fields]
        return {
            "ok": not stale_fields,
            "live_fields": live,
            "stale_fields": stale_fields,
            "fields": fields,
        }

    def set_fundamental(self, symbol: str, payload: Optional[Dict[str, Any]],
                        source: str = "fundamental",
                        ts: Optional[float] = None) -> None:
        """写入/清除某只标的的基本面裁决。

        ``payload=None`` 表示「确实没有基本面」（ETF/基金），要**显式删除**而不是
        留着一个空字典 —— 空字典在下游会被误当成「有数据但全是 0」。

        ``ts`` 用于重启预热：写入的是两小时前算出的结论时，字段年龄应该体现
        这个两小时，而不是假装刚刚算过。
        """
        key = str(symbol).strip().lower()
        if not key:
            return
        if payload is None:
            self.fundamentals.pop(key, None)
        else:
            self.fundamentals[key] = dict(payload)
        self._mark("fundamentals", ts=ts, source=source, sample_size=len(self.fundamentals))

    def get_fundamental(self, symbol: str) -> Optional[Dict[str, Any]]:
        """读某只标的的基本面裁决；过期（>7 天）返回 None，由调用方决定是否放行。"""
        if self.is_stale("fundamentals"):
            return None
        return self.fundamentals.get(str(symbol).strip().lower())

    def relative_strength(self, symbol: str) -> Optional[float]:
        """个股相对强度：个股当日涨跌 − 同批标的中位数（单位：百分点）。

        用途是回答「这次跌是跟着大盘跌，还是自己出事」。同批中位数比
        「指数涨跌」更贴近持仓所处的水位，且不需要额外行情源。

        Returns:
            None 表示该标的不在最近一批快照里（例如 A 股标的不在美股热点池），
            调用方应当**退回只看跌幅**，而不是凭空假设相对强度为 0。
        """
        try:
            syms = list(self._market_history.get("symbols") or [])
            rets = list(self._market_history.get("returns") or [])
            n = min(len(syms), len(rets))
            if n < 5:
                return None
            pairs = [
                (str(syms[i]).lower(), float(rets[i])) for i in range(n)
            ]
            key = str(symbol).lower()
            table = dict(pairs)
            if key not in table:
                return None
            values = sorted(v for _, v in pairs)
            mid = len(values) // 2
            median = (
                values[mid]
                if len(values) % 2
                else (values[mid - 1] + values[mid]) / 2.0
            )
            return float(table[key] - median)
        except Exception:
            return None

    def set_macro_liquidity_signal(self, signal: float):
        """
        设置宏观流动性信号

        Args:
            signal: 流动性信号值 (0-1)
                   < 0.4: 紧张
                   0.4-0.6: 中性
                   > 0.6: 宽松
        """
        self.macro_liquidity_signal = float(np.clip(signal, 0.1, 0.9))
        self._mark("macro_liquidity_signal", source="setter")

    def _get_value_system(self):
        """获取价值观系统"""
        return self._value_system

    def set_value_type(self, value_type: str) -> bool:
        """
        设置价值观类型

        Args:
            value_type: 价值观类型 (trend/contrarian/value/momentum/liquidity/balanced)

        Returns:
            是否成功
        """
        vs = self._get_value_system()
        if vs:
            return vs.set_active_value_type(value_type)
        self.active_value_type = value_type
        return True

    def get_value_weights(self) -> Dict[str, float]:
        """
        获取当前价值观权重

        Returns:
            价值观权重字典
        """
        vs = self._get_value_system()
        if vs:
            return vs.get_active_weights().to_dict()
        return {
            "price_sensitivity": 0.5,
            "volume_sensitivity": 0.5,
            "sentiment_weight": 0.3,
            "liquidity_weight": 0.4,
            "fundamentals_weight": 0.3,
        }

    def get_value_preferences(self) -> Dict[str, Any]:
        """
        获取当前价值观偏好

        Returns:
            价值观偏好字典
        """
        vs = self._get_value_system()
        if vs:
            return vs.get_active_preferences().to_dict()
        return {
            "risk_preference": 0.5,
            "time_horizon": 0.5,
            "concentration": 0.5,
        }

    def calculate_value_alignment(self, features: Dict[str, Any]) -> float:
        """
        计算事件特征与当前价值观的匹配度

        Args:
            features: 事件特征字典

        Returns:
            匹配度 (0-1)
        """
        vs = self._get_value_system()
        if vs:
            return vs.calculate_alignment(features)
        return 0.5

    def explain_focus(self, symbol: str, features: Dict[str, Any]) -> str:
        """
        解释为什么关注这个标的

        Args:
            symbol: 股票代码
            features: 事件特征

        Returns:
            解释字符串
        """
        alignment = self.calculate_value_alignment(features)
        vs = self._get_value_system()

        if vs:
            reason = vs.generate_focus_reason(features)
            vs.record_attention(symbol, alignment, reason)
            self.last_decision_reason = reason
            return reason

        price_change = features.get("price_change", 0)
        volume_spike = features.get("volume_spike", 1)
        return f"价格变化{price_change:+.2f}%，成交量{volume_spike:.1f}倍，匹配度{alignment:.2f}"

    def record_value_feedback(self, value_type: str, return_pct: float):
        """
        记录价值观表现反馈

        Args:
            value_type: 价值观类型
            return_pct: 收益百分比
        """
        vs = self._get_value_system()
        if vs:
            vs.record_performance(value_type, return_pct)

    def get_value_suggestions(self) -> List[str]:
        """
        获取价值观调整建议

        Returns:
            建议列表
        """
        vs = self._get_value_system()
        if vs:
            return vs.get_suggestions()
        return []

    def get_value_profile_info(self) -> Dict[str, Any]:
        """
        获取当前价值观配置信息

        Returns:
            价值观配置字典
        """
        vs = self._get_value_system()
        if vs:
            return vs.to_dict()
        return {
            "active_type": self.active_value_type,
            "active_type_display": self.active_value_type,
        }

    def update(self, feedback):
        """
        根据反馈更新状态

        Args:
            feedback: dict，包含 reward、action 等
        """
        if "reward" in feedback:
            self._adjust_focus(feedback["reward"])
        if "regime" in feedback:
            self.market_regime = feedback["regime"]
            self._mark("market_regime", source="feedback")
        if "strategy_state" in feedback:
            self.strategy_state = feedback["strategy_state"]
            self._mark("strategy_state", source="feedback")
        if "portfolio_state" in feedback:
            self.portfolio_state = feedback["portfolio_state"]
            self._mark(
                "portfolio_state",
                source="feedback",
                sample_size=len((feedback["portfolio_state"] or {}).get("held_symbols") or []),
            )

    def update_from_market(
        self,
        symbols,
        returns,
        volumes,
        prices,
        timestamp=None,
        block_ids=None,
        block_map=None,
        source="market",
    ):
        """
        从市场数据更新 QueryState

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组（**百分数**，+1.5 表示涨 1.5%）
            volumes: 成交量数组（当日**累计**成交量，股/份）
            prices: 价格数组
            timestamp: 时间戳
            block_ids: 题材ID数组（可选）
            block_map: 题材映射 dict{symbol: block_name}（可选）
            source: 数据来源标记（hotspot / scanner / market）
        """
        if timestamp is None:
            timestamp = time.time()

        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        prices = np.nan_to_num(prices, nan=0.0, posinf=1e6, neginf=0.0)

        n = int(len(returns))

        self._detect_and_update_regime(returns, timestamp)
        self._mark("market_regime", timestamp, source, n)

        self._update_macro_liquidity_signal(returns, volumes, timestamp, symbols)
        self._mark("macro_liquidity_signal", timestamp, source, n)

        self._calculate_and_update_risk_bias(returns, volumes, timestamp)
        self._mark("risk_bias", timestamp, source, n)

        if block_ids is None:
            block_ids = block_ids
        if block_map is None:
            block_map = block_map

        self._derive_and_update_attention_focus(
            symbols, returns, volumes, block_ids, block_map, timestamp
        )
        self._mark("attention_focus", timestamp, source, n)

        self._market_history["last_update"] = timestamp
        self._market_history["symbols"] = list(symbols[:100]) if len(symbols) > 100 else list(symbols)
        self._market_history["returns"] = list(returns[:100]) if len(returns) > 100 else list(returns)
        self._market_history["volumes"] = list(volumes[:100]) if len(volumes) > 100 else list(volumes)

    def _detect_and_update_regime(self, returns, timestamp):
        """检测并更新市场状态（趋势/震荡）。

        ❗聚合口径：单批快照 12~62 只不等，直接覆盖会让 regime 跟着批次抖；
        60 秒内的批次按**样本量加权**聚合后再判定。整批（62 只）的话语权
        自然大于档位批次（12 只），不需要额外的权重表。

        ❗字段口径：
        * ``avg_change`` 是**有符号**均值（跌市为负），此前存的是 ``mean(|r|)``，
          于是 ``trend_down`` 配着 ``avg_change=3.94`` 看起来像「涨了 3.94%」；
        * 幅度判断（``> 1.0``）改用 ``abs_change``（平均绝对涨跌幅）。
        """
        if len(returns) == 0:
            return

        returns = np.asarray(returns, dtype=float)

        up_count = int(np.sum(returns > 0.5))
        down_count = int(np.sum(returns < -0.5))
        flat_count = int(np.sum(np.abs(returns) <= 0.5))
        total = len(returns)

        self._regime_window.append({
            "ts": float(timestamp),
            "n": total,
            "up": up_count,
            "down": down_count,
            "flat": flat_count,
            "signed_sum": float(np.sum(returns)),
            "abs_sum": float(np.sum(np.abs(returns))),
            "sq_sum": float(np.sum(returns ** 2)),
        })
        cutoff = float(timestamp) - REGIME_WINDOW_SECONDS
        while self._regime_window and self._regime_window[0]["ts"] < cutoff:
            self._regime_window.popleft()

        agg_n = sum(b["n"] for b in self._regime_window) or 1
        up_ratio = sum(b["up"] for b in self._regime_window) / agg_n
        down_ratio = sum(b["down"] for b in self._regime_window) / agg_n
        flat_ratio = sum(b["flat"] for b in self._regime_window) / agg_n

        avg_change = sum(b["signed_sum"] for b in self._regime_window) / agg_n
        abs_change = sum(b["abs_sum"] for b in self._regime_window) / agg_n
        change_std = float(np.sqrt(max(
            0.0, sum(b["sq_sum"] for b in self._regime_window) / agg_n - avg_change ** 2
        )))

        if up_ratio > 0.4 and abs_change > 1.0:
            regime_type = "trend_up"
        elif down_ratio > 0.4 and abs_change > 1.0:
            regime_type = "trend_down"
        elif change_std < 1.0 and flat_ratio > 0.6:
            regime_type = "neutral"
        elif up_ratio > down_ratio * 1.3:
            regime_type = "weak_trend_up"
        elif down_ratio > up_ratio * 1.3:
            regime_type = "weak_trend_down"
        else:
            regime_type = "mixed"

        self.market_regime = {
            "type": regime_type,
            "timestamp": float(timestamp),
            "up_ratio": float(up_ratio),
            "down_ratio": float(down_ratio),
            "avg_change": float(avg_change),
            "abs_change": float(abs_change),
            "change_std": float(change_std),
            "sample_size": int(agg_n),
            "window_batches": len(self._regime_window),
            "window_seconds": REGIME_WINDOW_SECONDS,
        }

    def _volume_rate_score(self, symbols, volumes, timestamp):
        """量能趋势分：当前成交量速率相对自身基准，放量为正、缩量为负。

        ❗此前用 ``std(volume)/mean(volume)`` 当「量能趋势」，那是**横截面
        离散度**（不同股票的成交量本来就差几个数量级），与「今天比平时
        放量还是缩量」毫无关系；而且低于阈值时硬编码 ``0.3``，等于给流动性
        信号垫了一个恒定的正偏置。

        这里用**同一批标的的累计成交量增量 / 时间间隔**得到速率，再与自身
        EMA 比：数据源给的是当日累计量，增量才是「刚刚成交了多少」。
        基准不足（首次、隔夜重置、间隔异常）时返回 None，由调用方按中性处理。
        """
        if not symbols or len(symbols) != len(volumes):
            return None

        dt_now = float(timestamp)
        rates: List[float] = []
        for sym, cum in zip(symbols, volumes):
            key = str(sym)
            cum = float(cum)
            prev = self._vol_snapshot.get(key)
            if prev is None:
                self._vol_snapshot[key] = (cum, dt_now)
                continue
            prev_cum, prev_ts = prev
            dt = dt_now - prev_ts

            # 隔夜/换日累计量归零，或间隔过长（断流）→ 重建基准
            if cum < prev_cum or dt > VOL_MAX_INTERVAL:
                self._vol_snapshot[key] = (cum, dt_now)
                continue

            # ❗间隔太短时**不要更新基准**：热点事件会 2~3 秒推一批同一快照，
            #   若每批都把基准重置到「现在」，dt 永远 < 5 秒，量能项就永远算不出来
            #   （线上实测 volume_available 一直是 0）。这里保留旧基准，等累计
            #   间隔够了再算一次。
            if dt < VOL_MIN_INTERVAL:
                continue

            rates.append((cum - prev_cum) / dt)
            self._vol_snapshot[key] = (cum, dt_now)

        if len(rates) < max(3, int(len(symbols) * 0.2)):
            return None

        rate = float(np.mean(rates))
        if self._vol_rate_ema is None or self._vol_rate_ema <= 0:
            self._vol_rate_ema = rate
            return None

        ratio = rate / max(self._vol_rate_ema, 1e-9)
        self._vol_rate_ema = (
            (1 - VOL_RATE_EMA_ALPHA) * self._vol_rate_ema + VOL_RATE_EMA_ALPHA * rate
        )
        # ratio=1 → 中性；放量 1.7 倍 → +1；缩量到 0.4 倍 → -1
        return float(np.clip((ratio - 1.0) * 1.5, -1.0, 1.0))

    def _update_macro_liquidity_signal(self, returns, volumes, timestamp, symbols=None):
        """
        根据市场数据更新宏观流动性信号

        流动性信号范围 0-1：
        - < 0.4: 流动性紧张，需要谨慎
        - 0.4-0.6: 中性
        - > 0.6: 流动性宽松，可以更激进

        流动性判断依据：
        1. 市场整体涨跌（跌 → 紧张）
        2. 成交量变化（缩量 → 紧张）
        3. 波动率（高波动 → 紧张）
        """
        if len(returns) == 0 or len(volumes) == 0:
            return

        avg_change = float(np.mean(returns))
        change_std = float(np.std(returns))

        # ❗符号：文档写的是「跌 → 紧张」，但旧代码取的是 `-avg_change`，
        #   跌市反而把信号推高（实测 -3.7% 的盘面给出 0.51 的「中性偏松」）。
        #   这里按文档契约改成 `avg_change`：跌 → 负 → 收紧。
        change_score = float(np.clip(avg_change / 5.0, -1.0, 1.0))
        # 波动惩罚以 0.5% 为「正常」，3.5% 以上视为极端，避免长期顶满 1.0
        volatility_penalty = float(np.clip((change_std - 0.5) / 3.5, 0.0, 1.0))

        volume_score = self._volume_rate_score(symbols or [], volumes, timestamp)
        volume_available = volume_score is not None
        if volume_score is None:
            volume_score = 0.0  # 基准不足 → 中性，不再垫 0.3 的正偏置

        # 三项权重之和为 1，raw ∈ [-1, 1]
        raw_signal = (
            change_score * 0.45
            + volume_score * 0.25
            - volatility_penalty * 0.30
        )
        mapped = (raw_signal + 1.0) / 2.0

        smoothing = 0.9
        self.macro_liquidity_signal = smoothing * self.macro_liquidity_signal + (1 - smoothing) * mapped
        self.macro_liquidity_signal = float(np.clip(self.macro_liquidity_signal, 0.1, 0.9))

        self.liquidity_components = {
            "change_score": round(change_score, 4),
            "volume_score": round(float(volume_score), 4),
            "volume_available": 1.0 if volume_available else 0.0,
            "volatility_penalty": round(volatility_penalty, 4),
            "raw": round(float(raw_signal), 4),
            "mapped": round(float(mapped), 4),
            "signed_avg_change": round(avg_change, 4),
        }

    def _calculate_and_update_risk_bias(self, returns, volumes, timestamp):
        """根据市场波动率和持仓状态计算并更新风险偏好。

        ❗旧公式 ``volatility*0.4 + vol_intensity*0.3 + min(max_change/10,1)*0.3``
        直接把「百分点」当 [0,1] 用：美股日内波动 3~4% 是常态，三项各自都能
        顶满，``combined_risk`` 长期 ≥1 → ``risk_bias`` 恒等于下限 0.1，
        这个字段实际上退化成了常量（实测 0.1）。这里先把三个分量各自
        归一到 [0,1]，再合成，保证它有真实的动态范围。
        """
        if len(returns) == 0:
            return

        volatility = float(np.std(returns))
        avg_volume = float(np.mean(volumes)) if len(volumes) > 0 else 0.0
        volume_std = float(np.std(volumes)) if len(volumes) > 0 else 0.0
        max_change = float(np.max(np.abs(returns)))

        vol_intensity = volume_std / max(avg_volume, 1.0) if avg_volume > 0 else 0.0

        # 分量归一：6% 日波动 / 1.5 的量能离散度 / 12% 单票极值 = 各维度的「极端」
        vol_norm = float(np.clip(volatility / 6.0, 0.0, 1.0))
        intensity_norm = float(np.clip(vol_intensity / 1.5, 0.0, 1.0))
        extreme_norm = float(np.clip(max_change / 12.0, 0.0, 1.0))

        combined_risk = vol_norm * 0.45 + intensity_norm * 0.25 + extreme_norm * 0.30

        risk_bias = 1.0 - 0.9 * float(np.clip(combined_risk, 0.0, 1.0))
        risk_bias = float(np.clip(risk_bias, 0.15, 0.9))

        if self.portfolio_state:
            portfolio_return = self.portfolio_state.get("total_return", 0)

            if portfolio_return < -5:
                risk_bias *= 0.7
            elif portfolio_return < -2:
                risk_bias *= 0.85
            elif portfolio_return > 10:
                risk_bias = min(risk_bias * 1.1, 0.95)

            if self.portfolio_state.get("concentration", 0) > 0.5:
                risk_bias *= 0.8

        if self.macro_liquidity_signal < 0.4:
            risk_bias *= 0.85
        elif self.macro_liquidity_signal > 0.7:
            risk_bias = min(risk_bias * 1.1, 0.95)

        self.risk_bias = float(np.clip(risk_bias, 0.1, 0.9))

    def _derive_and_update_attention_focus(self, symbols, returns, volumes, block_ids, block_map, timestamp):
        """从题材表现推导注意力焦点"""
        if len(symbols) == 0 or len(returns) == 0:
            return

        symbol_returns = {}
        symbol_volumes = {}
        for i, sym in enumerate(symbols):
            if i < len(returns):
                symbol_returns[str(sym)] = float(returns[i])
            if i < len(volumes):
                symbol_volumes[str(sym)] = float(volumes[i])

        if block_map:
            block_perf = {}
            block_vol = {}
            for sym, blocks in block_map.items():
                if isinstance(blocks, list):
                    for block in blocks:
                        if block not in block_perf:
                            block_perf[block] = []
                            block_vol[block] = []
                        if sym in symbol_returns:
                            block_perf[block].append(symbol_returns[sym])
                        if sym in symbol_volumes:
                            block_vol[block].append(symbol_volumes[sym])
                else:
                    block = str(blocks)
                    if block not in block_perf:
                        block_perf[block] = []
                        block_vol[block] = []
                    if sym in symbol_returns:
                        block_perf[block].append(symbol_returns[sym])
                    if sym in symbol_volumes:
                        block_vol[block].append(symbol_volumes[sym])

            focus = {}
            for block, perf_list in block_perf.items():
                if perf_list:
                    avg_perf = np.mean(perf_list)
                    vol_list = block_vol.get(block, [])
                    avg_vol = np.mean(vol_list) if vol_list else 0

                    perf_score = np.clip(avg_perf / 3.0, -1.0, 1.0)
                    vol_score = np.clip(avg_vol / 1e8, 0, 1.0) if avg_vol > 0 else 0

                    focus[block] = (perf_score * 0.7 + vol_score * 0.3 + 1.0) / 2.0

            if focus:
                # ❗不再除以 max：归一化会让榜首永远是 1.0，于是「涨 9% 的题材」
                #   和「涨 0.9% 的题材」在下游看起来一模一样（`compute_priority`
                #   的 ×(1+0.5w) 变成了恒定加成）。这里保留**绝对强度** 0~1。
                top_focus = sorted(focus.items(), key=lambda x: x[1], reverse=True)[:5]
                self.attention_focus = {
                    k: float(np.clip(v, 0.0, 1.0)) for k, v in top_focus
                }
        else:
            symbol_scores = {}
            for sym, ret in symbol_returns.items():
                vol = symbol_volumes.get(sym, 0)
                perf_score = np.clip(ret / 3.0, -1.0, 1.0)
                vol_score = np.clip(vol / 1e8, 0, 1.0) if vol > 0 else 0
                symbol_scores[sym] = (perf_score * 0.7 + vol_score * 0.3 + 1.0) / 2.0

            if symbol_scores:
                top_symbols = sorted(symbol_scores.items(), key=lambda x: x[1], reverse=True)[:10]
                self.attention_focus = {
                    str(k): float(np.clip(v, 0.0, 1.0)) for k, v in top_symbols
                }

    def _adjust_focus(self, reward):
        """
        根据奖励调整注意力焦点

        Args:
            reward: 奖励值，正值强化，负值抑制
        """
        for key in list(self.attention_focus):
            self.attention_focus[key] = float(np.clip(
                self.attention_focus[key] * (1 + reward * 0.1), 0.0, 1.0
            ))

    def get_summary(self):
        """获取状态摘要"""
        return {
            "market_regime": self.market_regime.get("type", "unknown") if self.market_regime else "unknown",
            "risk_bias": self.risk_bias,
            "attention_focus_count": len(self.attention_focus),
            "top_attention": list(self.attention_focus.keys())[:3] if self.attention_focus else [],
            "strategy_count": len(self.strategy_state),
            "portfolio_count": len(self.portfolio_state),
            "active_value_type": self.active_value_type,
            "value_weights": self.get_value_weights(),
            "narrative_state": self.narrative_state,
            "cognitive_insights": self.cognitive_insights,
            "liquidity_state": self.liquidity_state,
            "economic_cycle": self.economic_cycle,
            "liquidity_components": self.liquidity_components,
            "fundamentals": self.fundamentals,
            "health": {
                "stale_fields": self.health()["stale_fields"],
            },
        }
