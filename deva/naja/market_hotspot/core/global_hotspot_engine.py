"""
Global Hotspot Module - 全市场热点计算

功能:
- 从全市场 snapshot 中提取市场状态
- 分离计算"热点"和"活跃度"
- 输出连续值 global_hotspot ∈ [0, 1]
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
    block_ids: np.ndarray  # 题材ID数组
    symbols: Optional[np.ndarray] = None  # 股票代码数组


class GlobalHotspotEngine:
    """
    全局热点引擎

    分离计算两个核心指标:
    1. 热点 (Hotspot): 市场焦点分布 ∈ [0, 1]
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

        self._last_hotspot: float = 0.0
        self._last_activity: float = 0.0
        self._last_calc_time: float = 0.0

        self._activity_history: deque = deque(maxlen=100)
        self._returns_abs_history: deque = deque(maxlen=100)
        self._volatility_history: deque = deque(maxlen=100)

        self._ema_hotspot: float = 0.3
        self._ema_activity: float = 0.3
        self._ema_alpha: float = 0.3

    def update(self, snapshot: MarketSnapshot) -> float:
        """
        更新并计算全局热点分数（旧API，保持向后兼容）

        Returns:
            全局热点分数 ∈ [0, 1]
        """
        hotspot, activity = self.get_hotspot_and_activity(snapshot)

        # 更新历史（只存 returns 用于后续计算）
        self._history_buffer.append({
            'returns': snapshot.returns.copy(),
            'volumes': snapshot.volumes.copy(),
            'hotspot': hotspot,
            'activity': activity,
            'timestamp': snapshot.timestamp
        })

        self._last_hotspot = hotspot
        self._last_activity = activity
        self._last_calc_time = time.time()

        return hotspot

    def get_hotspot_and_activity(self, snapshot: MarketSnapshot) -> Tuple[float, float]:
        """
        计算热点分数和市场活跃度（分离计算）

        Args:
            snapshot: 市场快照数据

        Returns:
            Tuple[hotspot, activity]:
                hotspot: 全局热点分数 ∈ [0, 1] - 市场焦点在哪（相对排名）
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

        # ===== 2. 全局热点（蓄势市场评分法） =====
        up_count = np.sum(returns > 0.1)
        down_count = np.sum(returns < -0.1)
        flat_count = len(returns) - up_count - down_count
        total = max(len(returns), 1)

        up_ratio = up_count / total
        down_ratio = down_count / total
        flat_ratio = flat_count / total
        direction_total = up_ratio + down_ratio

        if flat_ratio > 0.95:
            hotspot = 0.5
        elif flat_ratio > 0.80:
            hotspot = 0.4
        elif flat_ratio > 0.50:
            if direction_total < 0.05:
                hotspot = 0.35
            else:
                max_dir = max(up_ratio, down_ratio)
                hotspot = 0.3 + (max_dir - 0.5) * 0.6 * (1 - 0.3)
        else:
            max_dir = max(up_ratio, down_ratio)
            hotspot = 0.5 + max_dir * 0.3

        hotspot = max(0.1, min(0.9, hotspot))

        if len(self._activity_history) > 1:
            self._ema_hotspot = self._ema_alpha * hotspot + (1 - self._ema_alpha) * self._ema_hotspot
            self._ema_activity = self._ema_alpha * activity + (1 - self._ema_alpha) * self._ema_activity
        else:
            self._ema_hotspot = hotspot
            self._ema_activity = activity

        return self._ema_hotspot, self._ema_activity

    def get_market_state(self) -> Dict:
        """获取当前市场状态摘要"""
        if not self._history_buffer:
            return {
                'hotspot': 0.0,
                'activity': 0.0,
                'trend': 'unknown',
                'description': '等待数据...'
            }

        recent = list(self._history_buffer)[-5:]
        avg_hotspot = np.mean([h['hotspot'] for h in recent])
        avg_activity = np.mean([h['activity'] for h in recent])

        # 判断市场状态
        if avg_activity > 0.6:
            if avg_hotspot > 0.6:
                trend = 'high_activity_focused'
                description = '市场活跃且焦点集中'
            else:
                trend = 'high_activity_scattered'
                description = '市场活跃但热点散乱'
        elif avg_activity > 0.3:
            if avg_hotspot > 0.6:
                trend = 'moderate_activity_focused'
                description = '市场温和但焦点集中'
            else:
                trend = 'moderate_activity_scattered'
                description = '市场温和且热点散乱'
        else:
            trend = 'quiet'
            description = '市场平淡，观望为主'

        return {
            'hotspot': self._last_hotspot,
            'activity': self._last_activity,
            'avg_hotspot': avg_hotspot,
            'avg_activity': avg_activity,
            'trend': trend,
            'description': description
        }

    def get_hotspot_details(self, snapshot: 'MarketSnapshot') -> Dict:
        """
        获取热点计算的详细数据（用于UI展示）
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
                'hotspot': 0, 'activity': 0,
                'hotspot_level': '无数据',
                'activity_level': '无数据',
                'hotspot_formula': '无数据',
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
            hotspot = 0.5
            formula = "平盘占比>95%，热点极高"
        elif flat_ratio > 0.80:
            hotspot = 0.4
            formula = "平盘占比>80%，热点较高"
        elif flat_ratio > 0.50:
            if direction_total < 0.05:
                hotspot = 0.35
                formula = "方向占比<5%，几乎无方向"
            else:
                max_dir = max(up_ratio, down_ratio)
                hotspot = 0.3 + (max_dir - 0.5) * 0.6 * (1 - 0.3)
                formula = f"平盘50-80%，max_dir={max_dir:.1%}"
        else:
            max_dir = max(up_ratio, down_ratio)
            hotspot = 0.5 + max_dir * 0.3
            formula = f"平盘<50%，主导方向占比={max_dir:.1%}"

        hotspot = max(0.1, min(0.9, hotspot))

        if hotspot >= 0.7:
            hotspot_level = "焦点集中"
        elif hotspot >= 0.5:
            hotspot_level = "焦点较集中"
        elif hotspot >= 0.3:
            hotspot_level = "焦点分散"
        else:
            hotspot_level = "焦点涣散"

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
            'hotspot': hotspot,
            'activity': activity,
            'hotspot_level': hotspot_level,
            'activity_level': act_level,
            'hotspot_formula': formula,
            'activity_formula': f"均值={mean_abs_return:.4f}, 波动率={volatility:.4f}",
            'total_stocks': total,
        }

    def save_state(self) -> Dict:
        """保存引擎状态用于持久化"""
        return {
            'history_buffer': [
                {
                    'returns': h['returns'].tolist() if isinstance(h['returns'], np.ndarray) else list(h['returns']),
                    'volumes': h['volumes'].tolist() if isinstance(h['volumes'], np.ndarray) else list(h['volumes']),
                    'hotspot': h['hotspot'],
                    'activity': h['activity'],
                    'timestamp': h['timestamp'],
                }
                for h in self._history_buffer
            ],
            'ema_hotspot': self._ema_hotspot,
            'ema_activity': self._ema_activity,
            'activity_history': list(self._activity_history),
            'returns_abs_history': list(self._returns_abs_history),
            'volatility_history': list(self._volatility_history),
            'last_hotspot': self._last_hotspot,
            'last_activity': self._last_activity,
            'last_calc_time': self._last_calc_time,
        }

    def load_state(self, state: Dict) -> bool:
        """从持久化状态恢复"""
        try:
            if not state:
                return False

            self._history_buffer = deque(maxlen=self.history_window)
            for h in state.get('history_buffer', []):
                self._history_buffer.append({
                    'returns': np.array(h['returns']),
                    'volumes': np.array(h['volumes']),
                    'hotspot': h['hotspot'],
                    'activity': h['activity'],
                    'timestamp': h['timestamp'],
                })

            self._ema_hotspot = state.get('ema_hotspot', 0.3)
            self._ema_activity = state.get('ema_activity', 0.3)

            self._activity_history = deque(state.get('activity_history', []), maxlen=100)
            self._returns_abs_history = deque(state.get('returns_abs_history', []), maxlen=100)
            self._volatility_history = deque(state.get('volatility_history', []), maxlen=100)

            self._last_hotspot = state.get('last_hotspot', 0.0)
            self._last_activity = state.get('last_activity', 0.0)
            self._last_calc_time = state.get('last_calc_time', 0.0)

            return True
        except Exception as e:
            log.warning(f"[GlobalHotspotEngine] load_state 失败: {e}")
            return False

    def reset(self):
        """重置引擎状态"""
        self._history_buffer.clear()
        self._last_hotspot = 0.0
        self._last_activity = 0.0
        self._last_calc_time = 0.0
