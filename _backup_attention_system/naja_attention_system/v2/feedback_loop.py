"""
Module 8: Attention Feedback Loop - 注意力反馈学习系统

核心能力:
- 记录每次 attention → strategy → outcome
- 统计哪些 attention 模式 → 高收益
- 识别噪音模式
- 使用 Bandit 算法进行在线学习

架构:
- FeedbackCollector: 收集策略执行结果
- Attention有效性分析器: 分析哪些 attention 是有效的
- BanditUpdater: 使用 bandit 算法更新注意力权重
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque, defaultdict
import time
import json
import pickle
from pathlib import Path


@dataclass
class StrategyOutcome:
    """策略执行结果"""
    strategy_id: str
    symbol: str
    sector_id: str
    attention_before: float
    attention_after: float
    prediction_score: float
    action: str
    pnl: float
    holding_period: int
    timestamp: float
    market_state: str


@dataclass
class AttentionEffectiveness:
    """注意力有效性评分"""
    pattern_id: str
    pattern_type: str
    attention_range: Tuple[float, float]
    hit_count: int
    total_return: float
    win_rate: float
    avg_pnl: float
    effectiveness_score: float
    last_updated: float


class FeedbackCollector:
    """
    反馈收集器
    
    职责:
    - 记录每次 attention → strategy → outcome
    - 维护历史记录
    """
    
    def __init__(
        self,
        max_history: int = 10000,
        store_path: Optional[str] = None
    ):
        self.max_history = max_history
        self.store_path = store_path
        
        self._outcomes: deque = deque(maxlen=max_history)
        self._pattern_outcomes: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
    def record(
        self,
        strategy_id: str,
        symbol: str,
        sector_id: str,
        attention_before: float,
        attention_after: float,
        prediction_score: float,
        action: str,
        pnl: float,
        holding_period: int,
        market_state: str = "unknown"
    ) -> StrategyOutcome:
        """
        记录一次策略执行结果
        """
        outcome = StrategyOutcome(
            strategy_id=strategy_id,
            symbol=symbol,
            sector_id=sector_id,
            attention_before=attention_before,
            attention_after=attention_after,
            prediction_score=prediction_score,
            action=action,
            pnl=pnl,
            holding_period=holding_period,
            timestamp=time.time(),
            market_state=market_state
        )
        
        self._outcomes.append(outcome)
        
        pattern_key = self._make_pattern_key(
            attention_before, prediction_score, market_state
        )
        self._pattern_outcomes[pattern_key].append(outcome)
        
        return outcome
    
    def _make_pattern_key(
        self,
        attention: float,
        prediction: float,
        market_state: str
    ) -> str:
        """生成模式键"""
        att_bucket = int(attention * 10) / 10
        pred_bucket = int(prediction * 10) / 10
        return f"{att_bucket:.1f}_{pred_bucket:.1f}_{market_state}"
    
    def get_outcomes_for_pattern(self, pattern_key: str) -> List[StrategyOutcome]:
        """获取指定模式的 outcomes"""
        return list(self._pattern_outcomes.get(pattern_key, []))
    
    def get_recent_outcomes(self, n: int = 100) -> List[StrategyOutcome]:
        """获取最近的 outcomes"""
        return list(self._outcomes)[-n:]
    
    def get_outcomes_by_strategy(
        self,
        strategy_id: str,
        n: Optional[int] = None
    ) -> List[StrategyOutcome]:
        """获取指定策略的 outcomes"""
        outcomes = [o for o in self._outcomes if o.strategy_id == strategy_id]
        if n:
            return outcomes[-n:]
        return outcomes
    
    def persist(self):
        """持久化到磁盘"""
        if not self.store_path:
            return
        
        path = Path(self.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'wb') as f:
            pickle.dump({
                'outcomes': list(self._outcomes),
                'pattern_outcomes': {
                    k: list(v) for k, v in self._pattern_outcomes.items()
                }
            }, f)
    
    def load(self):
        """从磁盘加载"""
        if not self.store_path or not Path(self.store_path).exists():
            return
        
        with open(self.store_path, 'rb') as f:
            data = pickle.load(f)
            self._outcomes = deque(data['outcomes'], maxlen=self.max_history)
            self._pattern_outcomes = {
                k: deque(v, maxlen=1000)
                for k, v in data['pattern_outcomes'].items()
            }
    
    def reset(self):
        """重置"""
        self._outcomes.clear()
        self._pattern_outcomes.clear()


class AttentionEffectivenessAnalyzer:
    """
    注意力有效性分析器
    
    职责:
    - 分析哪些 attention 模式是有效的
    - 计算有效性分数
    - 识别噪音模式
    """
    
    def __init__(
        self,
        min_samples: int = 10,
        effectiveness_threshold: float = 0.1
    ):
        self.min_samples = min_samples
        self.effectiveness_threshold = effectiveness_threshold
        
        self._effectiveness: Dict[str, AttentionEffectiveness] = {}
        
    def analyze(self, collector: FeedbackCollector) -> Dict[str, AttentionEffectiveness]:
        """
        分析注意力有效性
        """
        self._effectiveness.clear()
        
        for pattern_key, outcomes in collector._pattern_outcomes.items():
            if len(outcomes) < self.min_samples:
                continue
            
            effectiveness = self._calc_effectiveness(pattern_key, outcomes)
            self._effectiveness[pattern_key] = effectiveness
        
        return self._effectiveness
    
    def _calc_effectiveness(
        self,
        pattern_key: str,
        outcomes: List[StrategyOutcome]
    ) -> AttentionEffectiveness:
        """计算单个模式的 effectiveness"""
        pnls = [o.pnl for o in outcomes]
        wins = [1 for o in outcomes if o.pnl > 0]
        
        total_return = sum(pnls)
        win_rate = sum(wins) / len(pnls) if pnls else 0
        avg_pnl = total_return / len(pnls) if pnls else 0
        
        hit_count = len(outcomes)
        
        pattern_type = self._infer_pattern_type(pattern_key)
        
        if avg_pnl > 0 and win_rate > 0.5:
            effectiveness_score = min(avg_pnl * win_rate * 10, 1.0)
        elif avg_pnl < 0:
            effectiveness_score = max(avg_pnl * 5, -1.0)
        else:
            effectiveness_score = 0.0
        
        attention_range = self._parse_attention_range(pattern_key)
        
        return AttentionEffectiveness(
            pattern_id=pattern_key,
            pattern_type=pattern_type,
            attention_range=attention_range,
            hit_count=hit_count,
            total_return=total_return,
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            effectiveness_score=effectiveness_score,
            last_updated=time.time()
        )
    
    def _infer_pattern_type(self, pattern_key: str) -> str:
        """推断模式类型"""
        parts = pattern_key.split('_')
        if len(parts) >= 3:
            attention = float(parts[0])
            prediction = float(parts[1])
            
            if attention > 0.7 and prediction > 0.6:
                return "high_attention_high_prediction"
            elif attention > 0.7 and prediction <= 0.6:
                return "high_attention_low_prediction"
            elif attention <= 0.3 and prediction > 0.6:
                return "low_attention_high_prediction"
            else:
                return "moderate"
        return "unknown"
    
    def _parse_attention_range(self, pattern_key: str) -> Tuple[float, float]:
        """解析 attention 范围"""
        parts = pattern_key.split('_')
        if parts:
            try:
                attention = float(parts[0])
                return (attention, attention + 0.1)
            except:
                pass
        return (0.0, 1.0)
    
    def get_effective_patterns(self) -> List[str]:
        """获取有效模式列表"""
        return [
            k for k, v in self._effectiveness.items()
            if v.effectiveness_score > self.effectiveness_threshold
        ]
    
    def get_ineffective_patterns(self) -> List[str]:
        """获取无效模式（噪音）列表"""
        return [
            k for k, v in self._effectiveness.items()
            if v.effectiveness_score < -self.effectiveness_threshold
        ]
    
    def get_best_attention_adjustment(
        self,
        current_attention: float,
        prediction_score: float,
        market_state: str
    ) -> float:
        """
        获取最佳注意力调整建议
        
        Returns:
            adjustment factor (e.g., 1.2 means +20% attention)
        """
        pattern_key = f"{current_attention:.1f}_{prediction_score:.1f}_{market_state}"
        
        effectiveness = self._effectiveness.get(pattern_key)
        
        if effectiveness and effectiveness.hit_count >= self.min_samples:
            if effectiveness.effectiveness_score > 0.3:
                return 1.0 + effectiveness.effectiveness_score * 0.5
            elif effectiveness.effectiveness_score < -0.3:
                return 1.0 + effectiveness.effectiveness_score * 0.5
            else:
                return 1.0
        
        return 1.0
    
    def get_all_effectiveness(self) -> Dict[str, AttentionEffectiveness]:
        """获取所有有效性评分"""
        return self._effectiveness.copy()
    
    def reset(self):
        """重置"""
        self._effectiveness.clear()


class BanditUpdater:
    """
    Bandit 更新器
    
    使用 Contextual Bandit 进行在线学习:
    - 输入: attention pattern context
    - 输出: attention weight adjustment
    
    算法: 简化版 LinUCB 或 Thompson Sampling
    """
    
    def __init__(
        self,
        alpha: float = 0.1,
        exploration_rate: float = 0.1,
        learning_rate: float = 0.01
    ):
        self.alpha = alpha
        self.exploration_rate = exploration_rate
        self.learning_rate = learning_rate
        
        self._theta: Dict[str, np.ndarray] = {}
        self._context_dim = 5
        
        self._context_history: List[Tuple[np.ndarray, float]] = []
        self._reward_history: List[float] = []
        
    def _get_context(
        self,
        attention: float,
        prediction_score: float,
        volatility: float,
        volume_ratio: float,
        trend: float
    ) -> np.ndarray:
        """构建上下文向量"""
        return np.array([
            attention,
            prediction_score,
            volatility,
            volume_ratio,
            trend
        ], dtype=np.float64)
    
    def _get_action(self, context: np.ndarray) -> float:
        """根据上下文选择动作（attention weight adjustment）"""
        context_key = self._make_context_key(context)
        
        if context_key not in self._theta:
            self._theta[context_key] = np.zeros(self._context_dim)
        
        theta = self._theta[context_key]
        
        if np.random.random() < self.exploration_rate:
            adjustment = np.random.uniform(0.5, 1.5)
        else:
            adjustment = float(np.clip(np.dot(theta, context), 0.5, 1.5))
        
        return adjustment
    
    def _make_context_key(self, context: np.ndarray) -> str:
        """生成上下文键"""
        att_bucket = int(context[0] * 4) / 4
        pred_bucket = int(context[1] * 4) / 4
        return f"{att_bucket:.2f}_{pred_bucket:.2f}"
    
    def select_action(
        self,
        attention: float,
        prediction_score: float,
        volatility: float = 0.0,
        volume_ratio: float = 1.0,
        trend: float = 0.0
    ) -> float:
        """
        选择动作
        
        Returns:
            attention weight adjustment
        """
        context = self._get_context(
            attention, prediction_score, volatility, volume_ratio, trend
        )
        return self._get_action(context)
    
    def update(
        self,
        attention: float,
        prediction_score: float,
        volatility: float,
        volume_ratio: float,
        trend: float,
        reward: float
    ):
        """
        更新模型
        
        reward: 策略执行的收益 (归一化到 [-1, 1])
        """
        context = self._get_context(
            attention, prediction_score, volatility, volume_ratio, trend
        )
        
        self._context_history.append((context, reward))
        self._reward_history.append(reward)
        
        context_key = self._make_context_key(context)
        
        if len(self._context_history) > 1000:
            self._context_history = self._context_history[-500:]
            self._reward_history = self._reward_history[-500:]
        
        self._update_theta(context_key, context, reward)
    
    def _update_theta(self, context_key: str, context: np.ndarray, reward: float):
        """更新 theta 参数"""
        if context_key not in self._theta:
            self._theta[context_key] = np.zeros(self._context_dim)
        
        theta = self._theta[context_key]
        
        error = reward - np.dot(theta, context)
        
        theta = theta + self.learning_rate * error * context
        
        norm = np.linalg.norm(theta)
        if norm > 2.0:
            theta = theta * 2.0 / norm
        
        self._theta[context_key] = theta
    
    def get_theta(self, attention: float, prediction_score: float) -> np.ndarray:
        """获取指定上下文的 theta"""
        context_key = f"{attention:.2f}_{prediction_score:.2f}"
        return self._theta.get(context_key, np.zeros(self._context_dim))
    
    def reset(self):
        """重置"""
        self._theta.clear()
        self._context_history.clear()
        self._reward_history.clear()


class AttentionFeedbackLoop:
    """
    注意力反馈循环主控制器
    
    整合:
    - FeedbackCollector: 收集反馈
    - AttentionEffectivenessAnalyzer: 分析有效性
    - BanditUpdater: 在线学习
    
    数据流:
    Strategy执行结果 → FeedbackCollector → EffectivenessAnalyzer →
    BanditUpdater → Attention权重调整
    """
    
    def __init__(
        self,
        store_path: Optional[str] = None,
        enable_bandit: bool = True,
        enable_effectiveness: bool = True
    ):
        self.collector = FeedbackCollector(store_path=store_path)
        self.analyzer = AttentionEffectivenessAnalyzer()
        self.bandit = BanditUpdater() if enable_bandit else None
        self.enable_effectiveness = enable_effectiveness
        
        self._last_adjustment: Dict[str, float] = {}
        self._adjustment_history: List[Dict] = []
        
    def record_outcome(
        self,
        strategy_id: str,
        symbol: str,
        sector_id: str,
        attention_before: float,
        attention_after: float,
        prediction_score: float,
        action: str,
        pnl: float,
        holding_period: int,
        market_state: str = "unknown",
        volatility: float = 0.0,
        volume_ratio: float = 1.0,
        trend: float = 0.0
    ) -> StrategyOutcome:
        """
        记录一次策略执行结果并更新学习
        """
        outcome = self.collector.record(
            strategy_id=strategy_id,
            symbol=symbol,
            sector_id=sector_id,
            attention_before=attention_before,
            attention_after=attention_after,
            prediction_score=prediction_score,
            action=action,
            pnl=pnl,
            holding_period=holding_period,
            market_state=market_state
        )
        
        if self.enable_effectiveness:
            self.analyzer.analyze(self.collector)
        
        if self.bandit:
            reward = self._calc_reward(pnl, holding_period)
            self.bandit.update(
                attention_before,
                prediction_score,
                volatility,
                volume_ratio,
                trend,
                reward
            )
        
        return outcome
    
    def _calc_reward(self, pnl: float, holding_period: int) -> float:
        """
        计算奖励
        
        归一化到 [-1, 1]
        """
        pnl_norm = np.clip(pnl / 0.1, -1, 1)
        
        time_penalty = holding_period / 100.0
        
        return pnl_norm - time_penalty * 0.1
    
    def get_attention_adjustment(
        self,
        symbol: str,
        attention: float,
        prediction_score: float,
        market_state: str = "unknown",
        volatility: float = 0.0,
        volume_ratio: float = 1.0,
        trend: float = 0.0
    ) -> float:
        """
        获取注意力权重调整建议
        
        Returns:
            adjustment factor (e.g., 1.2 means +20%)
        """
        if self.bandit:
            bandit_adj = self.bandit.select_action(
                attention, prediction_score, volatility, volume_ratio, trend
            )
        else:
            bandit_adj = 1.0
        
        if self.enable_effectiveness:
            effective_adj = self.analyzer.get_best_attention_adjustment(
                attention, prediction_score, market_state
            )
        else:
            effective_adj = 1.0
        
        final_adj = 0.6 * bandit_adj + 0.4 * effective_adj
        
        self._last_adjustment[symbol] = final_adj
        
        return final_adj
    
    def get_adjustment_for_symbol(self, symbol: str) -> float:
        """获取上次对 symbol 的调整"""
        return self._last_adjustment.get(symbol, 1.0)
    
    def get_effective_patterns(self) -> List[str]:
        """获取有效模式"""
        return self.analyzer.get_effective_patterns()
    
    def get_ineffective_patterns(self) -> List[str]:
        """获取无效模式"""
        return self.analyzer.get_ineffective_patterns()
    
    def apply_adjustment(
        self,
        attention: float,
        adjustment: float
    ) -> float:
        """
        应用调整
        
        Returns:
            adjusted attention
        """
        return attention * adjustment
    
    def persist(self):
        """持久化"""
        self.collector.persist()
        
        if self.bandit and self._adjustment_history:
            path = Path("attention_bandit_state.pkl")
            with open(path, 'wb') as f:
                pickle.dump({
                    'theta': self.bandit._theta,
                    'history': self._adjustment_history[-1000:]
                }, f)
    
    def load(self):
        """加载"""
        self.collector.load()
        
        path = Path("attention_bandit_state.pkl")
        if path.exists():
            with open(path, 'rb') as f:
                data = pickle.load(f)
                if self.bandit:
                    self.bandit._theta = data.get('theta', {})
                self._adjustment_history = data.get('history', [])
    
    def get_summary(self) -> Dict[str, Any]:
        """获取反馈循环摘要"""
        return {
            'total_outcomes': len(self.collector._outcomes),
            'patterns_observed': len(self.collector._pattern_outcomes),
            'effective_patterns': len(self.get_effective_patterns()),
            'ineffective_patterns': len(self.get_ineffective_patterns()),
            'adjustment_history_size': len(self._adjustment_history),
            'bandit_enabled': self.bandit is not None,
            'effectiveness_enabled': self.enable_effectiveness
        }
    
    def reset(self):
        """重置"""
        self.collector.reset()
        self.analyzer.reset()
        if self.bandit:
            self.bandit.reset()
        self._last_adjustment.clear()
        self._adjustment_history.clear()
