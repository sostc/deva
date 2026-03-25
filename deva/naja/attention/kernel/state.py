"""
QueryState - 全局查询状态

维护系统当前的注意力焦点状态
"""


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