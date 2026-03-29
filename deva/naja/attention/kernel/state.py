"""
QueryState - 全局查询状态

维护系统当前的注意力焦点状态
包含价值观系统集成
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any


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

    def __init__(self):
        self.strategy_state = {}
        self.portfolio_state = {}
        self.market_regime = {}
        self.attention_focus = {}
        self.risk_bias = 0.5
        self._market_history = {
            "returns": [],
            "volumes": [],
            "symbols": [],
            "last_update": 0,
        }
        self._value_system = None
        self.active_value_type = "trend"
        self.last_decision_reason = ""
        self.macro_liquidity_signal = 0.5

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

    def _get_value_system(self):
        """获取价值观系统（延迟初始化）"""
        if self._value_system is None:
            try:
                from deva.naja.attention.values import get_value_system
                self._value_system = get_value_system()
            except ImportError:
                pass
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
        if "strategy_state" in feedback:
            self.strategy_state = feedback["strategy_state"]
        if "portfolio_state" in feedback:
            self.portfolio_state = feedback["portfolio_state"]

    def update_from_market(self, symbols, returns, volumes, prices, timestamp=None, sector_ids=None, sector_map=None):
        """
        从市场数据更新 QueryState

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            prices: 价格数组
            timestamp: 时间戳
            sector_ids: 板块ID数组（可选）
            sector_map: 板块映射 dict{symbol: sector_name}（可选）
        """
        if timestamp is None:
            timestamp = time.time()

        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        prices = np.nan_to_num(prices, nan=0.0, posinf=1e6, neginf=0.0)

        self._detect_and_update_regime(returns, timestamp)

        self._update_macro_liquidity_signal(returns, volumes, timestamp)

        self._calculate_and_update_risk_bias(returns, volumes, timestamp)

        self._derive_and_update_attention_focus(
            symbols, returns, volumes, sector_ids, sector_map, timestamp
        )

        self._market_history["last_update"] = timestamp
        self._market_history["symbols"] = list(symbols[:100]) if len(symbols) > 100 else list(symbols)
        self._market_history["returns"] = list(returns[:100]) if len(returns) > 100 else list(returns)
        self._market_history["volumes"] = list(volumes[:100]) if len(volumes) > 100 else list(volumes)

    def _detect_and_update_regime(self, returns, timestamp):
        """检测并更新市场状态（趋势/震荡）"""
        if len(returns) == 0:
            return

        up_count = np.sum(returns > 0.5)
        down_count = np.sum(returns < -0.5)
        flat_count = np.sum(np.abs(returns) <= 0.5)
        total = len(returns)

        up_ratio = up_count / max(total, 1)
        down_ratio = down_count / max(total, 1)
        flat_ratio = flat_count / max(total, 1)

        avg_change = np.mean(np.abs(returns))
        change_std = np.std(returns)

        if up_ratio > 0.4 and avg_change > 1.0:
            regime_type = "trend_up"
        elif down_ratio > 0.4 and avg_change > 1.0:
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
            "timestamp": timestamp,
            "up_ratio": float(up_ratio),
            "down_ratio": float(down_ratio),
            "avg_change": float(avg_change),
            "change_std": float(change_std),
        }

    def _update_macro_liquidity_signal(self, returns, volumes, timestamp):
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

        avg_change = np.mean(returns)
        change_std = np.std(returns)

        avg_volume = np.mean(volumes)
        volume_std = np.std(volumes)

        volume_trend = volume_std / max(avg_volume, 1) if avg_volume > 0 else 0

        change_score = np.clip(-avg_change / 5.0, -1.0, 1.0)

        volatility_penalty = np.clip(change_std / 3.0, 0, 1.0)

        volume_score = np.clip(volume_trend / 0.5, -1.0, 1.0) if volume_trend > 0.2 else 0.3

        raw_signal = (change_score * 0.4 + volume_score * 0.3 - volatility_penalty * 0.3)

        raw_signal = (raw_signal + 1.0) / 2.0

        smoothing = 0.9
        self.macro_liquidity_signal = smoothing * self.macro_liquidity_signal + (1 - smoothing) * raw_signal

        self.macro_liquidity_signal = float(np.clip(self.macro_liquidity_signal, 0.1, 0.9))

    def _calculate_and_update_risk_bias(self, returns, volumes, timestamp):
        """根据市场波动率和持仓状态计算并更新风险偏好"""
        if len(returns) == 0:
            return

        volatility = np.std(returns)
        avg_volume = np.mean(volumes) if len(volumes) > 0 else 0
        volume_std = np.std(volumes) if len(volumes) > 0 else 0

        avg_change = np.mean(np.abs(returns))
        max_change = np.max(np.abs(returns))

        vol_intensity = volume_std / max(avg_volume, 1) if avg_volume > 0 else 0

        combined_risk = (volatility * 0.4 + vol_intensity * 0.3 + min(max_change / 10.0, 1.0) * 0.3)

        risk_bias = 1.0 - np.clip(combined_risk, 0.0, 1.0)
        risk_bias = float(np.clip(risk_bias, 0.1, 0.9))

        if self.portfolio_state:
            portfolio_return = self.portfolio_state.get("total_return", 0)
            portfolio_loss = self.portfolio_state.get("profit_loss", 0)

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

    def _derive_and_update_attention_focus(self, symbols, returns, volumes, sector_ids, sector_map, timestamp):
        """从板块表现推导注意力焦点"""
        if len(symbols) == 0 or len(returns) == 0:
            return

        symbol_returns = {}
        symbol_volumes = {}
        for i, sym in enumerate(symbols):
            if i < len(returns):
                symbol_returns[str(sym)] = float(returns[i])
            if i < len(volumes):
                symbol_volumes[str(sym)] = float(volumes[i])

        if sector_map:
            sector_perf = {}
            sector_vol = {}
            for sym, sectors in sector_map.items():
                if isinstance(sectors, list):
                    for sector in sectors:
                        if sector not in sector_perf:
                            sector_perf[sector] = []
                            sector_vol[sector] = []
                        if sym in symbol_returns:
                            sector_perf[sector].append(symbol_returns[sym])
                        if sym in symbol_volumes:
                            sector_vol[sector].append(symbol_volumes[sym])
                else:
                    sector = str(sectors)
                    if sector not in sector_perf:
                        sector_perf[sector] = []
                        sector_vol[sector] = []
                    if sym in symbol_returns:
                        sector_perf[sector].append(symbol_returns[sym])
                    if sym in symbol_volumes:
                        sector_vol[sector].append(symbol_volumes[sym])

            focus = {}
            for sector, perf_list in sector_perf.items():
                if perf_list:
                    avg_perf = np.mean(perf_list)
                    vol_list = sector_vol.get(sector, [])
                    avg_vol = np.mean(vol_list) if vol_list else 0

                    perf_score = np.clip(avg_perf / 3.0, -1.0, 1.0)
                    vol_score = np.clip(avg_vol / 1e8, 0, 1.0) if avg_vol > 0 else 0

                    focus[sector] = (perf_score * 0.7 + vol_score * 0.3 + 1.0) / 2.0

            if focus:
                max_focus = max(focus.values()) if focus else 1.0
                if max_focus > 0:
                    focus = {k: v / max_focus for k, v in focus.items()}

                top_focus = sorted(focus.items(), key=lambda x: x[1], reverse=True)[:5]
                self.attention_focus = {k: float(v) for k, v in top_focus}
        else:
            symbol_scores = {}
            for sym, ret in symbol_returns.items():
                vol = symbol_volumes.get(sym, 0)
                perf_score = np.clip(ret / 3.0, -1.0, 1.0)
                vol_score = np.clip(vol / 1e8, 0, 1.0) if vol > 0 else 0
                symbol_scores[sym] = (perf_score * 0.7 + vol_score * 0.3 + 1.0) / 2.0

            if symbol_scores:
                max_score = max(symbol_scores.values()) if symbol_scores else 1.0
                if max_score > 0:
                    symbol_scores = {k: v / max_score for k, v in symbol_scores.items()}

                top_symbols = sorted(symbol_scores.items(), key=lambda x: x[1], reverse=True)[:10]
                self.attention_focus = {str(k): float(v) for k, v in top_symbols}

    def _adjust_focus(self, reward):
        """
        根据奖励调整注意力焦点

        Args:
            reward: 奖励值，正值强化，负值抑制
        """
        if reward > 0:
            for key in self.attention_focus:
                self.attention_focus[key] *= (1 + reward * 0.1)
        else:
            for key in self.attention_focus:
                self.attention_focus[key] *= (1 + reward * 0.1)

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
        }
