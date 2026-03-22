"""
Global Attention Module - 全市场注意力计算

功能:
- 从全市场 snapshot 中提取市场状态
- 分离计算"注意力"和"活跃度"
- 输出连续值 global_attention ∈ [0, 1]
- 用于控制整体策略激进程度和数据源频率基线

性能目标:
- O(n) 复杂度，n 为股票数量
- 单次处理延迟 < 10ms
- 向量化计算，无 Python 层循环
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """市场快照数据"""
    timestamp: float
    returns: np.ndarray      # 涨跌幅数组
    volumes: np.ndarray      # 成交量数组
    prices: np.ndarray      # 价格数组
    sector_ids: np.ndarray  # 板块ID数组
    symbols: Optional[np.ndarray] = None  # 股票代码数组


class GlobalAttentionEngine:
    """
    全局注意力引擎

    分离计算两个核心指标:
    1. 注意力 (Attention): 市场焦点分布 ∈ [0, 1]
       - 衡量: 资金和关注点集中在哪里
       - 看相对排名，不受历史影响
       - 越高说明焦点越集中

    2. 活跃度 (Activity): 市场热闘程度 ∈ [0, 1]
       - 衡量: 市场波动和成交活跃程度
       - 看绝对波动，和历史无关
       - 越高说明市场越活跃
    """

    def __init__(
        self,
        history_window: int = 20,
    ):
        self.history_window = history_window

        self._history_buffer: deque = deque(maxlen=history_window)

        self._last_attention: float = 0.0
        self._last_activity: float = 0.0
        self._last_calc_time: float = 0.0

        self._activity_history: deque = deque(maxlen=100)
        self._returns_abs_history: deque = deque(maxlen=100)
        self._volatility_history: deque = deque(maxlen=100)

        self._ema_attention: float = 0.3
        self._ema_activity: float = 0.3
        self._ema_alpha: float = 0.3

    def update(self, snapshot: MarketSnapshot) -> float:
        """
        更新并计算全局注意力分数（旧API，保持向后兼容）

        Returns:
            全局注意力分数 ∈ [0, 1]
        """
        attention, activity = self.get_attention_and_activity(snapshot)

        # 更新历史（只存 returns 用于后续计算）
        self._history_buffer.append({
            'returns': snapshot.returns.copy(),
            'volumes': snapshot.volumes.copy(),
            'attention': attention,
            'activity': activity,
            'timestamp': snapshot.timestamp
        })

        self._last_attention = attention
        self._last_activity = activity
        self._last_calc_time = time.time()

        return attention

    def get_attention_and_activity(self, snapshot: MarketSnapshot) -> Tuple[float, float]:
        """
        计算注意力分数和市场活跃度（分离计算）

        Args:
            snapshot: 市场快照数据

        Returns:
            Tuple[attention, activity]:
                attention: 全局注意力分数 ∈ [0, 1] - 市场焦点在哪（相对排名）
                activity: 市场活跃度分数 ∈ [0, 1] - 市场热不热（绝对波动）
        """
        returns = snapshot.returns
        volumes = snapshot.volumes

        if len(returns) == 0:
            return 0.0, 0.0

        # 清理异常值
        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)

        # ===== 1. 市场活跃度（历史百分位） =====
        mean_abs_return = np.mean(np.abs(returns))
        volatility = np.std(returns)

        self._returns_abs_history.append(mean_abs_return)
        self._volatility_history.append(volatility)

        if len(self._returns_abs_history) >= 10:
            abs_values = list(self._returns_abs_history)
            vol_values = list(self._volatility_history)

            abs_percentile = sum(1 for v in abs_values if v < mean_abs_return) / len(abs_values)
            vol_percentile = sum(1 for v in vol_values if v < volatility) / len(vol_values)

            activity = (abs_percentile * 0.6 + vol_percentile * 0.4)
            activity = 0.1 + activity * 0.8
        else:
            raw_activity = mean_abs_return / 0.6 + volatility / 1.0
            activity = min(raw_activity / 4.0, 0.8)

        activity = max(0.05, min(0.95, activity))

        self._activity_history.append(activity)

        # ===== 2. 全局注意力（蓄势市场评分法） =====
        up_count = np.sum(returns > 0.1)
        down_count = np.sum(returns < -0.1)
        flat_count = len(returns) - up_count - down_count
        total = max(len(returns), 1)

        up_ratio = up_count / total
        down_ratio = down_count / total
        flat_ratio = flat_count / total
        direction_total = up_ratio + down_ratio

        if flat_ratio > 0.95:
            attention = 0.5
        elif flat_ratio > 0.80:
            attention = 0.4
        elif flat_ratio > 0.50:
            if direction_total < 0.05:
                attention = 0.35
            else:
                max_dir = max(up_ratio, down_ratio)
                attention = 0.3 + (max_dir - 0.5) * 0.6 * (1 - 0.3)
        else:
            max_dir = max(up_ratio, down_ratio)
            attention = 0.5 + max_dir * 0.3

        attention = max(0.1, min(0.9, attention))

        if len(self._activity_history) > 1:
            self._ema_attention = self._ema_alpha * attention + (1 - self._ema_alpha) * self._ema_attention
            self._ema_activity = self._ema_alpha * activity + (1 - self._ema_alpha) * self._ema_activity
        else:
            self._ema_attention = attention
            self._ema_activity = activity

        return self._ema_attention, self._ema_activity

    def get_market_state(self) -> Dict:
        """获取当前市场状态摘要"""
        if not self._history_buffer:
            return {
                'attention': 0.0,
                'activity': 0.0,
                'trend': 'unknown',
                'description': '等待数据...'
            }

        recent = list(self._history_buffer)[-5:]
        avg_attention = np.mean([h['attention'] for h in recent])
        avg_activity = np.mean([h['activity'] for h in recent])

        # 判断市场状态
        if avg_activity > 0.6:
            if avg_attention > 0.6:
                trend = 'high_activity_focused'
                description = '市场活跃且焦点集中'
            else:
                trend = 'high_activity_scattered'
                description = '市场活跃但热点散乱'
        elif avg_activity > 0.3:
            if avg_attention > 0.6:
                trend = 'moderate_activity_focused'
                description = '市场温和但焦点集中'
            else:
                trend = 'moderate_activity_scattered'
                description = '市场温和且热点散乱'
        else:
            trend = 'quiet'
            description = '市场平淡，观望为主'

        return {
            'attention': self._last_attention,
            'activity': self._last_activity,
            'avg_attention': avg_attention,
            'avg_activity': avg_activity,
            'trend': trend,
            'description': description
        }

    def get_attention_details(self, snapshot: 'MarketSnapshot') -> Dict:
        """
        获取注意力计算的详细数据（用于UI展示）
        """
        returns = np.nan_to_num(snapshot.returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(snapshot.volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)

        if len(returns) == 0:
            return {
                'up_count': 0, 'down_count': 0, 'flat_count': 0,
                'up_ratio': 0, 'down_ratio': 0, 'flat_ratio': 0,
                'mean_abs_return': 0, 'volatility': 0,
                'attention': 0, 'activity': 0,
                'attention_level': '无数据',
                'activity_level': '无数据',
                'attention_formula': '无数据',
                'activity_formula': '无数据',
                'total_stocks': 0,
            }

        mean_abs_return = float(np.mean(np.abs(returns)))
        volatility = float(np.std(returns))

        raw_activity = mean_abs_return / 0.6 + volatility / 1.0
        activity = min(raw_activity / 4.0, 0.8)
        activity = max(0.05, activity)

        up_count = int(np.sum(returns > 0.1))
        down_count = int(np.sum(returns < -0.1))
        flat_count = len(returns) - up_count - down_count
        total = max(len(returns), 1)

        up_ratio = up_count / total
        down_ratio = down_count / total
        flat_ratio = flat_count / total
        direction_total = up_ratio + down_ratio

        if flat_ratio > 0.95:
            attention = 0.5
            formula = "平盘占比>95%，注意力极高"
        elif flat_ratio > 0.80:
            attention = 0.4
            formula = "平盘占比>80%，注意力较高"
        elif flat_ratio > 0.50:
            if direction_total < 0.05:
                attention = 0.35
                formula = "方向占比<5%，几乎无方向"
            else:
                max_dir = max(up_ratio, down_ratio)
                attention = 0.3 + (max_dir - 0.5) * 0.6 * (1 - 0.3)
                formula = f"平盘50-80%，max_dir={max_dir:.1%}"
        else:
            max_dir = max(up_ratio, down_ratio)
            attention = 0.5 + max_dir * 0.3
            formula = f"平盘<50%，主导方向占比={max_dir:.1%}"

        attention = max(0.1, min(0.9, attention))

        if attention >= 0.7:
            att_level = "焦点集中"
        elif attention >= 0.5:
            att_level = "焦点较集中"
        elif attention >= 0.3:
            att_level = "焦点分散"
        else:
            att_level = "焦点涣散"

        if activity >= 0.7:
            act_level = "非常活跃"
        elif activity >= 0.4:
            act_level = "温和"
        elif activity >= 0.15:
            act_level = "清淡"
        else:
            act_level = "冷清"

        return {
            'up_count': up_count,
            'down_count': down_count,
            'flat_count': flat_count,
            'up_ratio': up_ratio,
            'down_ratio': down_ratio,
            'flat_ratio': flat_ratio,
            'mean_abs_return': mean_abs_return,
            'volatility': volatility,
            'attention': attention,
            'activity': activity,
            'attention_level': att_level,
            'activity_level': act_level,
            'attention_formula': formula,
            'activity_formula': f"均值={mean_abs_return:.4f}, 波动率={volatility:.4f}",
            'total_stocks': total,
        }

    def reset(self):
        """重置引擎状态"""
        self._history_buffer.clear()
        self._last_attention = 0.0
        self._last_activity = 0.0
        self._last_calc_time = 0.0
