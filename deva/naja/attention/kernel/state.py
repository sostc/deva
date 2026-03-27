"""
QueryState - 全局查询状态

维护系统当前的注意力焦点状态
"""

import time
import numpy as np


class QueryState:
    """
    全局 Query 状态

    属性:
        strategy_state: 当前策略状态
        portfolio_state: 当前持仓状态
        market_regime: 市场状态（趋势/震荡）
        attention_focus: 当前注意力焦点
        risk_bias: 风险偏好 [0, 1]
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
        }
