"""BanditOptimizer - Bandit系统/策略优化/UCB

别名/关键词: Bandit优化、UCB、贪婪、bandit optimizer

Bandit 策略优化器

提供 Multi-armed Bandit 算法实现，支持策略的在线自适应选择。
"""

from __future__ import annotations

import json
import logging
import math
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deva import NB
from deva.naja.attention.os.attention_os import get_attention_os

log = logging.getLogger(__name__)

BANDIT_STATS_TABLE = "naja_bandit_stats"
BANDIT_DECISIONS_TABLE = "naja_bandit_decisions"
BANDIT_ACTIONS_TABLE = "naja_bandit_actions"


@dataclass
class BanditDecision:
    """Bandit 决策记录"""
    id: str
    ts: float
    selected_arm: str
    available_arms: List[str]
    reward: float
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "decision_id": self.id,
            "timestamp": self.ts,
            "selected_arm": self.selected_arm,
            "available_arms": self.available_arms,
            "reward": self.reward,
            "reason": self.reason,
        }


@dataclass
class StrategyReward:
    """策略收益"""
    strategy_id: str
    position_id: str
    return_pct: float
    holding_duration: float
    reward: float
    timestamp: float


@dataclass
class BanditAction:
    """Bandit 产生的动作（与 LLM Controller 一致）"""
    strategy: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class BanditOptimizer:
    """Multi-armed Bandit 策略选择器
    
    与 LLM Controller 架构一致的设计：
    - 单例模式
    - 最小间隔控制
    - 决策记录持久化
    - 支持 dry_run
    
    支持的动作（与 LLM Controller 相同）：
    - update_params: 更新策略参数
    - update_strategy: 更新策略配置
    - reset: 重置策略状态
    - start: 启动策略
    - stop: 停止策略
    - restart: 重启策略
    """
    
    _instance = None
    _lock = threading.Lock()
    
    ALGORITHMS = ["epsilon_greedy", "ucb", "thompson"]
    SUPPORTED_ACTIONS = {"update_params", "update_strategy", "reset", "start", "stop", "restart"}
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        
        self._algorithm = "thompson"
        self._epsilon = 0.1
        self._c = 1.96
        
        self._arms: Dict[str, Dict[str, Any]] = {}
        self._last_update_ts = 0.0
        self._min_interval_seconds = 10
        self._min_interval_actions = 60
        
        self._db_stats = NB(BANDIT_STATS_TABLE)
        self._db_decisions = NB(BANDIT_DECISIONS_TABLE)
        self._db_actions = NB(BANDIT_ACTIONS_TABLE)
        
        # AttentionOS 集成相关
        self._attention_cache: Dict[str, float] = {}  # symbol -> attention_weight
        self._attention_cache_ts: float = 0.0
        self._attention_cache_ttl: float = 5.0  # 缓存有效期（秒）
        
        self._initialized = True
    
    def _get_attention_context(self) -> Dict[str, Any]:
        """获取 AttentionOS 上下文（带缓存）"""
        now = time.time()
        
        # 缓存检查
        if now - self._attention_cache_ts < self._attention_cache_ttl and self._attention_cache:
            return {
                "focus_symbols": list(self._attention_cache.keys()),
                "symbol_weights": self._attention_cache.copy(),
                "risk_temperature": self._attention_cache.get("_risk_temperature", 1.0),
                "cached": True
            }
        
        try:
            aos = get_attention_os()
            kernel = aos.get_kernel()
            
            # 获取 focus_symbols 和权重
            focus_weights = kernel.get_focus_weights()
            risk_temp = getattr(kernel.get_latest_output(), 'risk_temperature', 1.0)
            
            self._attention_cache = {symbol: weight for symbol, weight in focus_weights}
            self._attention_cache["_risk_temperature"] = risk_temp
            self._attention_cache_ts = now
            
            return {
                "focus_symbols": list(focus_weights.keys()),
                "symbol_weights": focus_weights,
                "risk_temperature": risk_temp,
                "cached": False
            }
        except Exception as e:
            log.warning(f"[Bandit] 获取 AttentionOS 上下文失败: {e}")
            return {
                "focus_symbols": [],
                "symbol_weights": {},
                "risk_temperature": 1.0,
                "cached": False
            }
    
    def _get_adaptive_epsilon(self, risk_temperature: float) -> float:
        """根据风险温度调整探索率
        
        - 高风险（risk_temp > 1.3）：降低探索，更保守
        - 低风险（risk_temp < 0.8）：增加探索，更激进
        """
        base_epsilon = self._epsilon
        
        if risk_temperature > 1.3:
            # 高风险：降低探索率 50%
            return base_epsilon * 0.5
        elif risk_temperature < 0.8:
            # 低风险：增加探索率 30%
            return min(base_epsilon * 1.3, 0.3)
        return base_epsilon
    
    def _apply_attention_to_arms(self, context: Dict[str, Any]):
        """根据 AttentionOS 上下文更新 arm 的注意力权重"""
        symbol_weights = context.get("symbol_weights", {})
        
        for arm_id in self._arms:
            # 从策略 ID 中提取品种（如果包含品种信息）
            # 格式如: "river_tick_hs_300750" -> "hs_300750"
            weight = 1.0
            
            # 尝试匹配 focus_symbols
            for symbol, attn_weight in symbol_weights.items():
                if symbol.lower() in arm_id.lower():
                    weight = attn_weight
                    break
            
            self._arms[arm_id]["attention_weight"] = weight
    
    def select_strategy(
        self,
        available_strategies: List[str],
        context: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> dict:
        """选择策略（AttentionOS 感知）
        
        Args:
            available_strategies: 可用策略列表
            context: 上下文信息 (用于 contextual bandit)
            dry_run: 是否仅模拟
            
        Returns:
            dict: {
                "success": bool,
                "selected": str,
                "reason": str,
                "all_scores": dict
            }
        """
        if not available_strategies:
            return {"success": False, "error": "没有可用策略"}
        
        # 获取 AttentionOS 上下文
        attn_context = self._get_attention_context()
        
        for s in available_strategies:
            if s not in self._arms:
                self._init_arm(s)
        
        # 应用注意力权重到 arms
        self._apply_attention_to_arms(attn_context)
        
        # 根据风险温度调整探索率
        adaptive_epsilon = self._get_adaptive_epsilon(attn_context["risk_temperature"])
        original_epsilon = self._epsilon
        self._epsilon = adaptive_epsilon
        
        selected = self._choose_arm(available_strategies, context)
        all_scores = {arm: self._get_arm_score(arm) for arm in available_strategies}
        
        # 恢复原始 epsilon
        self._epsilon = original_epsilon
        
        if dry_run:
            log.info(f"[Bandit] DRY RUN 选择策略: {selected}, 分数: {all_scores}, "
                    f"attention_focus: {attn_context['focus_symbols'][:3]}...")
            return {
                "success": True,
                "selected": selected,
                "reason": f"[DRY RUN] Bandit 选择策略: {selected}",
                "all_scores": all_scores,
                "dry_run": True,
                "attention_context": {
                    "focus_symbols": attn_context["focus_symbols"],
                    "risk_temperature": attn_context["risk_temperature"],
                }
            }
        
        self._record_decision(selected, available_strategies, 0.0, 
                             f"risk_temp={attn_context['risk_temperature']:.2f}")
        log.info(f"[Bandit] 选择策略: {selected}, 分数: {all_scores}, "
                f"risk_temp={attn_context['risk_temperature']:.2f}")
        
        return {
            "success": True,
            "selected": selected,
            "reason": f"Bandit 选择策略: {selected}",
            "all_scores": all_scores,
            "attention_context": {
                "focus_symbols": attn_context["focus_symbols"],
                "risk_temperature": attn_context["risk_temperature"],
            }
        }
    
    def update_reward(
        self,
        strategy_id: str,
        reward: float,
        dry_run: bool = False,
    ) -> dict:
        """更新策略收益
        
        Args:
            strategy_id: 策略 ID
            reward: 收益值
            dry_run: 是否仅模拟
            
        Returns:
            dict: 更新结果
        """
        now = time.time()
        
        if now - self._last_update_ts < self._min_interval_seconds:
            return {
                "success": False,
                "error": "更新过于频繁",
                "next_available_in": self._min_interval_seconds - (now - self._last_update_ts)
            }
        
        if strategy_id not in self._arms:
            self._init_arm(strategy_id)
        
        arm = self._arms[strategy_id]
        
        arm["pull_count"] += 1
        arm["total_reward"] += reward
        arm["avg_reward"] = arm["total_reward"] / arm["pull_count"]
        arm["last_updated"] = now
        
        if not dry_run:
            try:
                self._db_stats[strategy_id] = {
                    "strategy_id": strategy_id,
                    "pull_count": arm["pull_count"],
                    "total_reward": arm["total_reward"],
                    "avg_reward": arm["avg_reward"],
                    "last_updated": arm["last_updated"]
                }
            except Exception:
                pass
        
        self._last_update_ts = now
        
        return {
            "success": True,
            "strategy_id": strategy_id,
            "reward": reward,
            "new_avg": arm["avg_reward"],
            "pull_count": arm["pull_count"]
        }
    
    def get_stats(self, strategy_id: str) -> dict:
        """获取策略统计"""
        arm = self._arms.get(strategy_id)
        if not arm:
            return {
                "strategy_id": strategy_id,
                "pull_count": 0,
                "total_reward": 0.0,
                "avg_reward": 0.0,
                "last_updated": 0.0
            }
        return {
            "strategy_id": strategy_id,
            "pull_count": arm["pull_count"],
            "total_reward": arm["total_reward"],
            "avg_reward": arm["avg_reward"],
            "last_updated": arm.get("last_updated", 0.0)
        }
    
    def get_all_stats(self) -> List[dict]:
        """获取所有策略统计"""
        return [self.get_stats(sid) for sid in self._arms.keys()]
    
    def review_and_adjust(
        self,
        strategy_ids: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> dict:
        """审查并调节策略（与 LLM Controller.review_and_adjust 对应）
        
        根据 Bandit 统计决定是否需要调节策略参数或执行动作。
        
        Args:
            strategy_ids: 策略 ID 列表（None 表示所有）
            dry_run: 是否仅模拟
            
        Returns:
            dict: 决策结果
        """
        from ..strategy import get_strategy_manager
        
        now = time.time()
        if now - self._last_update_ts < self._min_interval_actions:
            return {
                "success": False,
                "error": "策略调节过于频繁",
                "next_available_in": self._min_interval_actions - (now - self._last_update_ts)
            }
        
        mgr = get_strategy_manager()
        actions = []
        
        target_ids = strategy_ids or list(self._arms.keys())
        
        for sid in target_ids:
            stats = self.get_stats(sid)
            action = self._generate_action(sid, stats)
            if action:
                actions.append(action)
        
        if not actions:
            self._last_update_ts = now
            log.info("[Bandit] 审查结果: 无需调节")
            return {
                "success": True,
                "summary": "无需调节",
                "actions": [],
                "reason": "所有策略表现正常"
            }
        
        apply_result = self._apply_actions(actions, mgr, dry_run)
        log.info(f"[Bandit] 审查完成: 生成 {len(actions)} 个调节动作")
        
        self._last_update_ts = now
        
        return {
            "success": True,
            "summary": f"生成 {len(actions)} 个调节动作",
            "actions": [a.__dict__ for a in actions],
            "apply_result": apply_result,
            "dry_run": dry_run
        }
    
    def _generate_action(self, strategy_id: str, stats: dict) -> Optional[BanditAction]:
        """根据统计生成调节动作
        
        Args:
            strategy_id: 策略 ID
            stats: 策略统计
            
        Returns:
            Optional[BanditAction]: 动作（如果需要调节）
        """
        pull_count = stats.get("pull_count", 0)
        avg_reward = stats.get("avg_reward", 0.0)
        
        if pull_count < 3:
            return None
        
        if avg_reward < -5:
            return BanditAction(
                strategy=strategy_id,
                action="stop",
                params={},
                reason=f"策略 {strategy_id} 连续亏损，平均收益 {avg_reward:.2f}%，停止策略"
            )
        elif avg_reward < -2:
            return BanditAction(
                strategy=strategy_id,
                action="update_params",
                params={"aggressive_mode": False},
                reason=f"策略 {strategy_id} 表现不佳 {avg_reward:.2f}%，降低风险参数"
            )
        elif avg_reward > 5:
            return BanditAction(
                strategy=strategy_id,
                action="update_params",
                params={"aggressive_mode": True},
                reason=f"策略 {strategy_id} 表现优秀 {avg_reward:.2f}%，增加仓位"
            )
        
        return None
    
    def _apply_actions(
        self,
        actions: List[BanditAction],
        mgr,
        dry_run: bool = False,
    ) -> dict:
        """应用动作（与 LLM Controller._apply_actions 对应）"""
        results = []
        
        for action in actions:
            entry = mgr.get(action.strategy) or mgr.get_by_name(action.strategy)
            if entry is None:
                results.append({
                    "strategy": action.strategy,
                    "success": False,
                    "error": "策略不存在"
                })
                continue
            
            if action.action not in self.SUPPORTED_ACTIONS:
                results.append({
                    "strategy": action.strategy,
                    "success": False,
                    "error": f"不支持的动作: {action.action}"
                })
                continue
            
            if not entry.supports_action(action.action):
                results.append({
                    "strategy": action.strategy,
                    "success": False,
                    "error": f"策略不支持动作: {action.action}"
                })
                continue
            
            if dry_run:
                results.append({
                    "strategy": action.strategy,
                    "success": True,
                    "dry_run": True,
                    "action": action.action
                })
                continue
            
            try:
                if action.action == "update_params":
                    result = entry.update_params(action.params)
                elif action.action == "update_strategy":
                    result = entry.update_strategy(action.params)
                elif action.action == "reset":
                    result = entry.reset()
                elif action.action == "start":
                    result = entry.start()
                elif action.action == "stop":
                    result = entry.stop()
                elif action.action == "restart":
                    entry.stop()
                    result = entry.start()
                else:
                    result = {"success": False, "error": "未知动作"}
                
                results.append({"strategy": action.strategy, **result})
                
                self._record_action(action)
                
            except Exception as e:
                results.append({
                    "strategy": action.strategy,
                    "success": False,
                    "error": str(e)
                })
        
        return {"results": results}
    
    def _init_arm(self, strategy_id: str):
        """初始化 arm"""
        self._arms[strategy_id] = {
            "pull_count": 0,
            "total_reward": 0.0,
            "avg_reward": 0.0,
            "last_updated": 0.0,
            "alpha": 1.0,
            "beta": 1.0,
        }
        
        try:
            saved = self._db_stats.get(strategy_id)
            if saved:
                self._arms[strategy_id].update(saved)
        except Exception:
            pass
    
    def _choose_arm(self, available: List[str], context: Optional[Dict[str, Any]]) -> str:
        """选择 arm"""
        if self._algorithm == "epsilon_greedy":
            return self._epsilon_greedy(available)
        elif self._algorithm == "ucb":
            return self._ucb(available)
        elif self._algorithm == "thompson":
            return self._thompson(available)
        else:
            return available[0]
    
    def _epsilon_greedy(self, available: List[str]) -> str:
        if random.random() < self._epsilon:
            return random.choice(available)
        
        best = max(available, key=lambda a: self._arms[a]["avg_reward"])
        return best
    
    def _ucb(self, available: List[str]) -> str:
        total_pulls = sum(self._arms[a]["pull_count"] for a in available)
        if total_pulls == 0:
            return available[0]
        
        best_arm = None
        best_score = float("-inf")
        
        for arm in available:
            a = self._arms[arm]
            avg = a["avg_reward"]
            pulls = a["pull_count"]
            
            if pulls > 0:
                uncertainty = self._c * math.sqrt(math.log(total_pulls) / pulls)
            else:
                uncertainty = float("inf")
            
            score = avg + uncertainty
            if score > best_score:
                best_score = score
                best_arm = arm
        
        return best_arm or available[0]
    
    def _thompson(self, available: List[str]) -> str:
        best_arm = None
        best_sample = float("-inf")
        
        for arm in available:
            a = self._arms[arm]
            sample = random.betavariate(a["alpha"], a["beta"])
            if sample > best_sample:
                best_sample = sample
                best_arm = arm
        
        return best_arm or available[0]
    
    def _get_arm_score(self, strategy_id: str) -> float:
        arm = self._arms.get(strategy_id, {})
        
        # 获取注意力权重（默认1.0）
        attention_weight = arm.get("attention_weight", 1.0)
        
        if self._algorithm == "epsilon_greedy":
            base_score = arm.get("avg_reward", 0.0)
        elif self._algorithm == "ucb":
            total = sum(self._arms[a]["pull_count"] for a in self._arms)
            pulls = arm.get("pull_count", 0)
            if pulls == 0:
                return float("inf") * attention_weight
            base_score = arm.get("avg_reward", 0.0) + self._c * math.sqrt(math.log(total) / pulls)
        elif self._algorithm == "thompson":
            base_score = arm.get("alpha", 1.0) / (arm.get("alpha", 1.0) + arm.get("beta", 1.0))
        else:
            base_score = arm.get("avg_reward", 0.0)
        
        # 应用注意力权重：focus 的品种加权更高
        # attention_weight 范围通常是 0.5-2.0
        return base_score * attention_weight
    
    def _record_decision(self, selected: str, available: List[str], reward: float, reason: str):
        """记录决策"""
        try:
            decision = BanditDecision(
                id=f"bandit_{int(time.time() * 1000)}",
                ts=time.time(),
                selected_arm=selected,
                available_arms=available,
                reward=reward,
                reason=reason
            )
            key = f"{int(decision.ts * 1000)}_{decision.id}"
            self._db_decisions[key] = decision.to_dict()
        except Exception:
            pass
    
    def _record_action(self, action: BanditAction):
        """记录动作"""
        try:
            key = f"{int(time.time() * 1000)}_{action.strategy}"
            self._db_actions[key] = {
                "strategy": action.strategy,
                "action": action.action,
                "params": action.params,
                "reason": action.reason,
                "timestamp": time.time()
            }
        except Exception:
            pass
    
    def set_algorithm(self, algorithm: str):
        if algorithm not in self.ALGORITHMS:
            raise ValueError(f"不支持的算法: {algorithm}, 支持: {self.ALGORITHMS}")
        self._algorithm = algorithm
    
    def set_epsilon(self, epsilon: float):
        self._epsilon = epsilon
    
    def set_c(self, c: float):
        self._c = c


_bandit_optimizer: Optional[BanditOptimizer] = None
_bandit_lock = threading.Lock()


def get_bandit_optimizer() -> BanditOptimizer:
    global _bandit_optimizer
    if _bandit_optimizer is None:
        with _bandit_lock:
            if _bandit_optimizer is None:
                _bandit_optimizer = BanditOptimizer()
    return _bandit_optimizer
