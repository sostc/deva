"""
BanditStrategySelector - Bandit系统/策略选择

别名/关键词: 策略选择、学习、bandit selector、strategy selector

Module 11: Strategy Learning - 策略选择学习

核心能力:
- 让系统自动学习在什么市场状态下用什么策略
- 使用 Bandit 或 RL 进行在线学习
- 替代固定策略映射规则

输入:
- global_hotspot
- block_hotspot
- pattern_score (PyTorch)
- 历史策略表现

输出:
- strategy_selection
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
import time
import json
from abc import ABC, abstractmethod


@dataclass
class MarketState:
    """市场状态"""
    global_hotspot: float
    avg_block_hotspot: float
    max_block_hotspot: float
    pattern_score_avg: float
    volatility: float
    timestamp: float
    
    def to_context(self) -> np.ndarray:
        """转换为上下文向量"""
        return np.array([
            self.global_hotspot,
            self.avg_block_hotspot,
            self.max_block_hotspot,
            self.pattern_score_avg,
            self.volatility
        ], dtype=np.float64)
    
    def get_state_name(self) -> str:
        """获取状态名称"""
        if self.global_hotspot > 0.7:
            if self.volatility > 0.5:
                return "high_hotspot_high_volatility"
            else:
                return "high_hotspot_low_volatility"
        elif self.global_hotspot > 0.4:
            if self.pattern_score_avg > 0.5:
                return "moderate_hotspot_high_pattern"
            else:
                return "moderate_hotspot_low_pattern"
        else:
            return "low_hotspot"


@dataclass
class StrategyPerformance:
    """策略表现"""
    strategy_id: str
    total_reward: float
    episode_count: int
    avg_reward: float
    win_rate: float
    last_reward: float
    confidence: float
    last_updated: float


@dataclass
class StrategySelection:
    """策略选择结果"""
    selected_strategies: List[str]
    market_state: MarketState
    selection_confidence: float
    alternative_strategies: List[Tuple[str, float]]
    timestamp: float


class MarketStateDetector:
    """
    市场状态检测器
    
    从市场数据中检测当前状态
    """
    
    def __init__(
        self,
        hotspot_threshold_high: float = 0.7,
        hotspot_threshold_low: float = 0.3,
        volatility_threshold: float = 0.5
    ):
        self.hotspot_high = hotspot_threshold_high
        self.hotspot_low = hotspot_threshold_low
        self.volatility_threshold = volatility_threshold
        
        self._state_history: deque = deque(maxlen=100)
        
    def detect(
        self,
        global_hotspot: float,
        block_hotspot: Dict[str, float],
        pattern_scores: Optional[Dict[str, float]] = None
    ) -> MarketState:
        """
        检测当前市场状态
        """
        if block_hotspot:
            avg_block = np.mean(list(block_hotspot.values()))
            max_block = max(block_hotspot.values())
        else:
            avg_block = 0.0
            max_block = 0.0
        
        pattern_avg = 0.0
        if pattern_scores:
            pattern_avg = np.mean(list(pattern_scores.values()))
        
        volatility = abs(global_hotspot - avg_block) if avg_block > 0 else 0.0
        
        state = MarketState(
            global_hotspot=global_hotspot,
            avg_block_hotspot=avg_block,
            max_block_hotspot=max_block,
            pattern_score_avg=pattern_avg,
            volatility=volatility,
            timestamp=time.time()
        )
        
        self._state_history.append(state)
        
        return state
    
    def get_state_name(self, state: MarketState) -> str:
        """获取状态名称"""
        return state.get_state_name()
    
    def get_historical_states(self, n: int = 10) -> List[MarketState]:
        """获取历史状态"""
        return list(self._state_history)[-n:]
    
    def reset(self):
        """重置"""
        self._state_history.clear()


class BanditStrategySelector:
    """
    Bandit 策略选择器
    
    使用 Contextual Bandit 进行策略选择:
    - 输入: market state context
    - 输出: strategy selection
    """
    
    def __init__(
        self,
        exploration_rate: float = 0.1,
        learning_rate: float = 0.01,
        min_confidence: int = 5
    ):
        self.exploration_rate = exploration_rate
        self.learning_rate = learning_rate
        self.min_confidence = min_confidence
        
        self._strategy_rewards: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._strategy_episodes: Dict[str, int] = defaultdict(int)
        
        self._state_strategy_rewards: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        
        self._theta: Dict[str, np.ndarray] = {}
        self._context_dim = 5
        
    def _get_state_key(self, context: np.ndarray) -> str:
        """生成状态键"""
        att_bucket = int(context[0] * 2)
        vol_bucket = int(min(context[4], 1.0) * 2)
        return f"{att_bucket}_{vol_bucket}"
    
    def select(
        self,
        state: MarketState,
        available_strategies: List[str],
        top_k: int = 3
    ) -> StrategySelection:
        """
        选择策略
        
        Returns:
            StrategySelection
        """
        if not available_strategies:
            return StrategySelection(
                selected_strategies=[],
                market_state=state,
                selection_confidence=0.0,
                alternative_strategies=[],
                timestamp=time.time()
            )
        
        context = state.to_context()
        state_key = self._get_state_key(context)
        
        scores = {}
        
        for strategy_id in available_strategies:
            score = self._get_strategy_score(strategy_id, state_key, context)
            scores[strategy_id] = score
        
        sorted_strategies = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        selected = [s[0] for s in sorted_strategies[:top_k]]
        alternatives = [(s[0], s[1]) for s in sorted_strategies[top_k:top_k*2]]
        
        confidence = self._calc_confidence(selected[0] if selected else None, state_key)
        
        return StrategySelection(
            selected_strategies=selected,
            market_state=state,
            selection_confidence=confidence,
            alternative_strategies=alternatives,
            timestamp=time.time()
        )
    
    def _get_strategy_score(
        self,
        strategy_id: str,
        state_key: str,
        context: np.ndarray
    ) -> float:
        """获取策略分数"""
        if strategy_id not in self._theta:
            self._theta[strategy_id] = np.zeros(self._context_dim)
        
        theta = self._theta[strategy_id]
        
        exploitation = float(np.dot(theta, context))
        
        state_rewards = self._state_strategy_rewards.get(state_key, {}).get(strategy_id, [])
        if len(state_rewards) >= self.min_confidence:
            bayesian = np.mean(state_rewards)
        else:
            bayesian = 0.0
        
        score = 0.7 * exploitation + 0.3 * bayesian
        
        return score
    
    def _calc_confidence(self, strategy_id: Optional[str], state_key: str) -> float:
        """计算选择置信度"""
        if not strategy_id:
            return 0.0
        
        episodes = self._strategy_episodes.get(strategy_id, 0)
        if episodes < self.min_confidence:
            return episodes / self.min_confidence
        
        state_rewards = self._state_strategy_rewards.get(state_key, {}).get(strategy_id, [])
        if len(state_rewards) < self.min_confidence:
            return 0.5
        
        return min(0.9, len(state_rewards) / 20)
    
    def update(
        self,
        strategy_id: str,
        state: MarketState,
        reward: float
    ):
        """
        更新策略表现
        
        reward: 归一化的奖励 [-1, 1]
        """
        self._strategy_rewards[strategy_id].append(reward)
        self._strategy_episodes[strategy_id] += 1
        
        state_key = self._get_state_key(state.to_context())
        self._state_strategy_rewards[state_key][strategy_id].append(reward)
        
        if len(self._strategy_rewards[strategy_id]) > 1000:
            self._strategy_rewards[strategy_id] = deque(
                list(self._strategy_rewards[strategy_id])[-500:],
                maxlen=100
            )
        
        self._update_theta(strategy_id, state.to_context(), reward)
    
    def _update_theta(self, strategy_id: str, context: np.ndarray, reward: float):
        """更新 theta"""
        if strategy_id not in self._theta:
            self._theta[strategy_id] = np.zeros(self._context_dim)
        
        theta = self._theta[strategy_id]
        
        error = reward - np.dot(theta, context)
        
        theta = theta + self.learning_rate * error * context
        
        norm = np.linalg.norm(theta)
        if norm > 3.0:
            theta = theta * 3.0 / norm
        
        self._theta[strategy_id] = theta
    
    def get_strategy_performance(self, strategy_id: str) -> StrategyPerformance:
        """获取策略表现"""
        rewards = list(self._strategy_rewards.get(strategy_id, []))
        
        if not rewards:
            return StrategyPerformance(
                strategy_id=strategy_id,
                total_reward=0.0,
                episode_count=0,
                avg_reward=0.0,
                win_rate=0.0,
                last_reward=0.0,
                confidence=0.0,
                last_updated=time.time()
            )
        
        total = sum(rewards)
        avg = total / len(rewards)
        wins = sum(1 for r in rewards if r > 0)
        
        episodes = self._strategy_episodes.get(strategy_id, 0)
        confidence = min(1.0, episodes / 20)
        
        return StrategyPerformance(
            strategy_id=strategy_id,
            total_reward=total,
            episode_count=episodes,
            avg_reward=avg,
            win_rate=wins / len(rewards),
            last_reward=rewards[-1],
            confidence=confidence,
            last_updated=time.time()
        )
    
    def get_all_performance(self) -> Dict[str, StrategyPerformance]:
        """获取所有策略表现"""
        return {
            sid: self.get_strategy_performance(sid)
            for sid in self._theta.keys()
        }
    
    def get_best_for_state(self, state: MarketState) -> List[str]:
        """获取指定状态的最佳策略"""
        context = state.to_context()
        state_key = self._get_state_key(context)
        
        best_strategies = []
        
        for strategy_id in self._theta.keys():
            score = self._get_strategy_score(strategy_id, state_key, context)
            best_strategies.append((strategy_id, score))
        
        best_strategies.sort(key=lambda x: x[1], reverse=True)
        
        return [s[0] for s in best_strategies[:3]]
    
    def reset(self):
        """重置"""
        self._strategy_rewards.clear()
        self._strategy_episodes.clear()
        self._state_strategy_rewards.clear()
        self._theta.clear()


class RuleBasedStrategySelector:
    """
    基于规则的策略选择器 (备用)

    当 Bandit 没有足够数据时使用
    """

    def __init__(self):
        self._rules = {
            'high_hotspot_high_volatility': ['momentum_tracker', 'anomaly_sniper'],
            'high_hotspot_low_volatility': ['block_rotation_hunter', 'smart_money_detector'],
            'moderate_hotspot_high_pattern': ['global_sentinel'],
            'moderate_hotspot_low_pattern': ['block_rotation_hunter'],
            'low_hotspot': ['global_sentinel']
        }

        self._default_strategies = ['global_sentinel', 'block_rotation_hunter']

    def reset(self):
        """重置（规则选择器无需重置状态）"""
        pass

    def select(
        self,
        state: MarketState,
        available_strategies: List[str],
        top_k: int = 3
    ) -> StrategySelection:
        """
        选择策略
        """
        state_name = state.get_state_name()
        
        preferred = self._rules.get(state_name, self._default_strategies)
        
        selected = []
        for s in preferred:
            if s in available_strategies and len(selected) < top_k:
                selected.append(s)
        
        for s in available_strategies:
            if s not in selected and len(selected) < top_k:
                selected.append(s)
        
        alternatives = []
        for s in available_strategies:
            if s not in selected:
                alternatives.append((s, 0.5))
        
        return StrategySelection(
            selected_strategies=selected,
            market_state=state,
            selection_confidence=0.5,
            alternative_strategies=alternatives[:top_k],
            timestamp=time.time()
        )


class StrategyLearning:
    """
    策略选择学习主控制器
    
    整合:
    - MarketStateDetector: 市场状态检测
    - BanditStrategySelector: Bandit 策略选择
    - RuleBasedStrategySelector: 规则备用选择
    """
    
    def __init__(
        self,
        use_bandit: bool = True,
        use_rules_fallback: bool = True,
        exploration_rate: float = 0.1,
        learning_rate: float = 0.01,
        min_bandit_confidence: int = 5
    ):
        self.state_detector = MarketStateDetector()
        self.bandit = BanditStrategySelector(
            exploration_rate=exploration_rate,
            learning_rate=learning_rate,
            min_confidence=min_bandit_confidence
        ) if use_bandit else None
        self.rules = RuleBasedStrategySelector() if use_rules_fallback else None
        
        self._selection_history: List[StrategySelection] = []
        self._last_selection: Optional[StrategySelection] = None
        
    def select_strategies(
        self,
        global_hotspot: float,
        block_hotspot: Dict[str, float],
        available_strategies: List[str],
        pattern_scores: Optional[Dict[str, float]] = None,
        top_k: int = 3
    ) -> StrategySelection:
        """
        选择策略
        """
        state = self.state_detector.detect(
            global_hotspot,
            block_hotspot,
            pattern_scores
        )
        
        selection_confidence_threshold = 0.6
        
        if self.bandit and self.bandit._strategy_episodes:
            best_strategy = max(
                self.bandit._strategy_episodes.keys(),
                key=lambda s: self.bandit._strategy_episodes[s]
            )
            confidence = self.bandit.get_strategy_performance(best_strategy).confidence
            
            if confidence >= selection_confidence_threshold:
                selection = self.bandit.select(state, available_strategies, top_k)
                self._last_selection = selection
                self._selection_history.append(selection)
                return selection
        
        if self.rules:
            selection = self.rules.select(state, available_strategies, top_k)
            self._last_selection = selection
            self._selection_history.append(selection)
            return selection
        
        return StrategySelection(
            selected_strategies=available_strategies[:top_k],
            market_state=state,
            selection_confidence=0.0,
            alternative_strategies=[],
            timestamp=time.time()
        )
    
    def record_outcome(
        self,
        strategy_id: str,
        pnl: float,
        holding_time: int
    ):
        """
        记录策略执行结果并更新学习
        
        Args:
            strategy_id: 策略 ID
            pnl: 收益
            holding_time: 持仓时间
        """
        if not self._last_selection:
            return
        
        reward = self._calc_reward(pnl, holding_time)
        
        if self.bandit:
            self.bandit.update(
                strategy_id,
                self._last_selection.market_state,
                reward
            )
    
    def _calc_reward(self, pnl: float, holding_time: int) -> float:
        """
        计算奖励
        
        归一化到 [-1, 1]
        """
        pnl_norm = np.clip(pnl / 0.1, -1, 1)
        
        time_penalty = min(holding_time / 60.0, 1.0) * 0.2
        
        return pnl_norm - time_penalty
    
    def get_current_state(self) -> Optional[MarketState]:
        """获取当前市场状态"""
        if self._selection_history:
            return self._selection_history[-1].market_state
        return None
    
    def get_strategy_performance(self, strategy_id: str) -> Optional[StrategyPerformance]:
        """获取策略表现"""
        if self.bandit:
            return self.bandit.get_strategy_performance(strategy_id)
        return None
    
    def get_all_performance(self) -> Dict[str, StrategyPerformance]:
        """获取所有策略表现"""
        if self.bandit:
            return self.bandit.get_all_performance()
        return {}
    
    def get_selection_summary(self) -> Dict[str, Any]:
        """获取选择摘要"""
        return {
            'total_selections': len(self._selection_history),
            'current_state': (
                self._selection_history[-1].market_state.get_state_name()
                if self._selection_history else None
            ),
            'last_selection': {
                'selected': (
                    self._selection_history[-1].selected_strategies
                    if self._selection_history else []
                ),
                'confidence': (
                    self._selection_history[-1].selection_confidence
                    if self._selection_history else 0.0
                )
            },
            'bandit_enabled': self.bandit is not None,
            'rules_enabled': self.rules is not None
        }
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计"""
        if not self.bandit:
            return {}
        
        performance = self.bandit.get_all_performance()
        
        return {
            'total_strategies_learned': len(performance),
            'most_rewards': (
                max(performance.keys(), key=lambda s: performance[s].total_reward)
                if performance else None
            ),
            'highest_confidence': (
                max(performance.keys(), key=lambda s: performance[s].confidence)
                if performance else None
            ),
            'highest_win_rate': (
                max(performance.keys(), key=lambda s: performance[s].win_rate)
                if performance else None
            )
        }
    
    def persist(self, path: str = "strategy_learning_state.json"):
        """持久化"""
        if not self.bandit:
            return
        
        data = {
            'strategy_episodes': dict(self.bandit._strategy_episodes),
            'theta_keys': list(self.bandit._theta.keys()),
            'selection_history_size': len(self._selection_history)
        }
        
        with open(path, 'w') as f:
            json.dump(data, f)
    
    def load(self, path: str = "strategy_learning_state.json"):
        """加载"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            pass
    
    def reset(self):
        """重置"""
        self.state_detector.reset()
        if self.bandit:
            self.bandit.reset()
        if self.rules:
            self.rules.reset()
        self._selection_history.clear()
        self._last_selection = None
