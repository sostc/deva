"""
MetaEvolution 增强 - 自动策略生成

扩展 MetaEvolution 模块，增加自动策略生成能力

核心功能：
1. PatternRecognizer: 从历史决策中识别有效模式
2. ParameterTuner: 根据绩效自动调优参数
3. StrategyGenerator: 基于模式+模板生成新策略
4. EvolutionaryOptimizer: 使用遗传算法进化策略
5. StrategyEvaluator: 评估生成策略的质量
"""

import time
import random
import logging
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

log = logging.getLogger(__name__)


class StrategyType(Enum):
    """策略类型"""
    MOMENTUM = "momentum"           # 动量策略
    REVERSAL = "reversal"          # 反转策略
    BREAKOUT = "breakout"          # 突破策略
    VALUE = "value"                # 价值策略
    GROWTH = "growth"               # 成长策略
    HYBRID = "hybrid"              # 混合策略


@dataclass
class StrategyPattern:
    """策略模式"""
    pattern_id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    actions: Dict[str, Any]
    success_rate: float = 0.0
    sample_count: int = 0
    avg_return: float = 0.0


@dataclass
class GeneratedStrategy:
    """生成的策略"""
    strategy_id: str
    name: str
    strategy_type: StrategyType
    parameters: Dict[str, float]
    rules: List[str]
    expected_return: float
    risk_level: str
    confidence: float
    generation_method: str
    parent_pattern_id: Optional[str] = None


@dataclass
class EvolutionCandidate:
    """进化候选"""
    strategy: GeneratedStrategy
    fitness: float
    age: int = 0


class PatternRecognizer:
    """
    模式识别器

    从历史决策中识别有效的策略模式
    """

    def __init__(self):
        self._patterns: Dict[str, StrategyPattern] = {}
        self._pattern_counter = 0

    def learn_from_decisions(
        self,
        decisions: List[Dict[str, Any]]
    ) -> List[StrategyPattern]:
        """
        从决策历史学习模式

        Args:
            decisions: 决策记录列表

        Returns:
            识别出的模式列表
        """
        patterns = []

        successful = [d for d in decisions if d.get("success") is True]

        if len(successful) < 5:
            return patterns

        momentum_decisions = self._identify_momentum_pattern(successful)
        if momentum_decisions:
            patterns.append(momentum_decisions)

        reversal_decisions = self._identify_reversal_pattern(successful)
        if reversal_decisions:
            patterns.append(reversal_decisions)

        breakout_decisions = self._identify_breakout_pattern(successful)
        if breakout_decisions:
            patterns.append(breakout_decisions)

        for pattern in patterns:
            self._patterns[pattern.pattern_id] = pattern

        return patterns

    def _identify_momentum_pattern(
        self,
        decisions: List[Dict[str, Any]]
    ) -> Optional[StrategyPattern]:
        """识别动量模式"""
        self._pattern_counter += 1

        avg_change = sum(d.get("context", {}).get("price_change", 0)
                        for d in decisions) / len(decisions)

        if avg_change > 1.0:
            return StrategyPattern(
                pattern_id=f"pattern_{self._pattern_counter}",
                name="动量增强模式",
                description="价格上涨时追涨，成功率较高",
                conditions={
                    "price_change_min": 2.0,
                    "volume_ratio_min": 1.2,
                    "trend": "up"
                },
                actions={
                    "action": "buy",
                    "position_size": "medium",
                    "stop_loss": 0.05
                },
                success_rate=len([d for d in decisions if d.get("success")]) / len(decisions),
                sample_count=len(decisions),
                avg_return=avg_change
            )
        return None

    def _identify_reversal_pattern(
        self,
        decisions: List[Dict[str, Any]]
    ) -> Optional[StrategyPattern]:
        """识别反转模式"""
        self._pattern_counter += 1

        oversold_decisions = [
            d for d in decisions
            if d.get("context", {}).get("price_change", 0) < -3.0
        ]

        if len(oversold_decisions) >= 3:
            return StrategyPattern(
                pattern_id=f"pattern_{self._pattern_counter}",
                name="超跌反弹模式",
                description="价格大幅下跌后反弹，成功率较高",
                conditions={
                    "price_change_max": -3.0,
                    "volume_ratio_min": 0.8,
                    "oversold_indicator": True
                },
                actions={
                    "action": "buy",
                    "position_size": "small",
                    "stop_loss": 0.08
                },
                success_rate=len([d for d in oversold_decisions if d.get("success")]) / len(oversold_decisions),
                sample_count=len(oversold_decisions),
                avg_return=abs(sum(d.get("context", {}).get("price_change", 0)
                                  for d in oversold_decisions) / len(oversold_decisions))
            )
        return None

    def _identify_breakout_pattern(
        self,
        decisions: List[Dict[str, Any]]
    ) -> Optional[StrategyPattern]:
        """识别突破模式"""
        self._pattern_counter += 1

        breakout_decisions = [
            d for d in decisions
            if d.get("context", {}).get("volume_ratio", 1.0) > 2.0
        ]

        if len(breakout_decisions) >= 3:
            return StrategyPattern(
                pattern_id=f"pattern_{self._pattern_counter}",
                name="放量突破模式",
                description="成交量放大时突破，成功率较高",
                conditions={
                    "volume_ratio_min": 2.0,
                    "price_change_min": 1.5,
                    "breakout_type": "volume"
                },
                actions={
                    "action": "buy",
                    "position_size": "large",
                    "stop_loss": 0.06
                },
                success_rate=len([d for d in breakout_decisions if d.get("success")]) / len(breakout_decisions),
                sample_count=len(breakout_decisions),
                avg_return=sum(d.get("context", {}).get("price_change", 0)
                              for d in breakout_decisions) / len(breakout_decisions)
            )
        return None

    def get_pattern(self, pattern_id: str) -> Optional[StrategyPattern]:
        """获取模式"""
        return self._patterns.get(pattern_id)

    def get_all_patterns(self) -> List[StrategyPattern]:
        """获取所有模式"""
        return list(self._patterns.values())


class ParameterTuner:
    """
    参数调优器

    根据绩效反馈自动调整策略参数
    """

    def __init__(self):
        self._param_ranges: Dict[str, Tuple[float, float]] = {
            "stop_loss": (0.02, 0.15),
            "take_profit": (0.03, 0.25),
            "position_size": (0.1, 1.0),
            "volume_threshold": (0.5, 3.0),
            "price_change_threshold": (1.0, 5.0),
            "holding_period": (1, 20)
        }
        self._tuning_history: List[Dict[str, Any]] = []

    def tune_parameters(
        self,
        current_params: Dict[str, float],
        performance: float
    ) -> Dict[str, float]:
        """
        调优参数

        Args:
            current_params: 当前参数
            performance: 绩效指标 [0, 1]

        Returns:
            调整后的参数
        """
        new_params = current_params.copy()

        if performance < 0.4:
            adjustment_factor = 0.15
        elif performance < 0.6:
            adjustment_factor = 0.08
        else:
            adjustment_factor = 0.03

        for param_name, (min_val, max_val) in self._param_ranges.items():
            if param_name in current_params:
                current_val = current_params[param_name]
                range_size = max_val - min_val

                if performance < 0.5:
                    direction = -1 if random.random() < 0.5 else 1
                else:
                    direction = 1 if random.random() < 0.7 else -1

                adjustment = range_size * adjustment_factor * direction
                new_val = current_val + adjustment
                new_val = max(min_val, min(max_val, new_val))

                new_params[param_name] = round(new_val, 4)

        self._tuning_history.append({
            "timestamp": time.time(),
            "old_params": current_params,
            "new_params": new_params,
            "performance": performance
        })

        return new_params

    def suggest_initial_params(
        self,
        strategy_type: StrategyType
    ) -> Dict[str, float]:
        """根据策略类型建议初始参数"""
        base_params = {
            "stop_loss": 0.05,
            "take_profit": 0.10,
            "position_size": 0.3,
            "volume_threshold": 1.5,
            "price_change_threshold": 2.0,
            "holding_period": 5
        }

        if strategy_type == StrategyType.MOMENTUM:
            base_params.update({
                "stop_loss": 0.08,
                "take_profit": 0.15,
                "position_size": 0.4,
                "price_change_threshold": 2.5
            })
        elif strategy_type == StrategyType.REVERSAL:
            base_params.update({
                "stop_loss": 0.06,
                "take_profit": 0.12,
                "position_size": 0.25,
                "price_change_threshold": 3.0
            })
        elif strategy_type == StrategyType.BREAKOUT:
            base_params.update({
                "stop_loss": 0.07,
                "take_profit": 0.18,
                "position_size": 0.5,
                "volume_threshold": 2.0
            })
        elif strategy_type == StrategyType.VALUE:
            base_params.update({
                "stop_loss": 0.10,
                "take_profit": 0.20,
                "position_size": 0.2,
                "holding_period": 15
            })

        return base_params


class TemplateLibrary:
    """
    策略模板库

    提供各种类型的策略模板
    """

    def __init__(self):
        self._templates: Dict[StrategyType, List[Dict[str, Any]]] = {
            StrategyType.MOMENTUM: [
                {
                    "name": "短期动量",
                    "description": "追涨杀跌，持有3-5天",
                    "rules": [
                        "if price_change > 2% and volume_ratio > 1.5: buy",
                        "if price_change < -2% and volume_ratio > 1.5: sell",
                        "holding_period <= 5 days"
                    ],
                    "expected_return": 0.08,
                    "risk_level": "medium"
                },
                {
                    "name": "动量突破",
                    "description": "动量强劲时买入",
                    "rules": [
                        "if momentum_score > 0.7 and price > ma20: buy",
                        "if momentum_score < 0.3: sell",
                        "position_size = momentum_score * 0.5"
                    ],
                    "expected_return": 0.12,
                    "risk_level": "high"
                }
            ],
            StrategyType.REVERSAL: [
                {
                    "name": "均值回归",
                    "description": "价格偏离均线时买入",
                    "rules": [
                        "if price < ma10 * 0.95: buy",
                        "if price > ma10 * 1.05: sell",
                        "stop_loss = 0.08"
                    ],
                    "expected_return": 0.06,
                    "risk_level": "medium"
                },
                {
                    "name": "超卖反弹",
                    "description": "RSI超卖时买入",
                    "rules": [
                        "if rsi < 30: buy",
                        "if rsi > 70: sell",
                        "position_size = (30 - rsi) / 30 * 0.5"
                    ],
                    "expected_return": 0.10,
                    "risk_level": "medium"
                }
            ],
            StrategyType.BREAKOUT: [
                {
                    "name": "突破买入",
                    "description": "价格突破时买入",
                    "rules": [
                        "if price > upper_band and volume > avg_volume * 2: buy",
                        "if price < lower_band: sell",
                        "stop_loss = 0.06"
                    ],
                    "expected_return": 0.15,
                    "risk_level": "high"
                }
            ],
            StrategyType.VALUE: [
                {
                    "name": "低估值买入",
                    "description": "PE和PB低时买入",
                    "rules": [
                        "if pe < 15 and pb < 2: buy",
                        "if pe > 30 or pb > 5: sell",
                        "position_size = (30 - pe) / 30 * 0.4"
                    ],
                    "expected_return": 0.10,
                    "risk_level": "low"
                }
            ],
            StrategyType.GROWTH: [
                {
                    "name": "成长股投资",
                    "description": "高成长性股票",
                    "rules": [
                        "if revenue_growth > 0.2 and profit_growth > 0.15: buy",
                        "if revenue_growth < 0.05: sell",
                        "position_size = growth_rate * 2"
                    ],
                    "expected_return": 0.18,
                    "risk_level": "high"
                }
            ]
        }

    def get_template(
        self,
        strategy_type: StrategyType,
        index: int = 0
    ) -> Optional[Dict[str, Any]]:
        """获取模板"""
        templates = self._templates.get(strategy_type, [])
        if index < len(templates):
            return templates[index]
        return None

    def get_all_templates(self, strategy_type: StrategyType) -> List[Dict[str, Any]]:
        """获取所有模板"""
        return self._templates.get(strategy_type, [])


class EvolutionaryOptimizer:
    """
    进化优化器

    使用遗传算法思想进化策略
    """

    def __init__(self, population_size: int = 10):
        self._population_size = population_size
        self._candidates: List[EvolutionCandidate] = []
        self._generation = 0

    def initialize_population(
        self,
        base_strategies: List[GeneratedStrategy]
    ):
        """初始化种群"""
        self._candidates = [
            EvolutionCandidate(strategy=s, fitness=0.5, age=0)
            for s in base_strategies
        ]
        self._generation = 0

    def evaluate_fitness(
        self,
        candidate: EvolutionCandidate,
        metrics: Dict[str, float]
    ) -> float:
        """
        评估适应度

        Args:
            candidate: 进化候选
            metrics: 绩效指标，包含：
                - success_rate: 成功率
                - avg_return: 平均收益
                - max_drawdown: 最大回撤
                - Sharpe ratio: 夏普比率

        Returns:
            适应度分数 [0, 1]
        """
        success_rate = metrics.get("success_rate", 0.5)
        avg_return = metrics.get("avg_return", 0.0)
        max_drawdown = metrics.get("max_drawdown", 0.3)

        risk_penalty = min(1.0, max_drawdown / 0.3)

        fitness = (
            success_rate * 0.4 +
            min(1.0, avg_return / 0.2) * 0.3 +
            (1.0 - risk_penalty) * 0.3
        )

        return min(1.0, max(0.0, fitness))

    def evolve(
        self,
        top_k: int = 3
    ) -> List[EvolutionCandidate]:
        """
        进化下一代

        Args:
            top_k: 保留前k个最优策略

        Returns:
            新一代候选
        """
        if len(self._candidates) < 2:
            return self._candidates

        sorted_candidates = sorted(
            self._candidates,
            key=lambda c: c.fitness,
            reverse=True
        )

        elite = sorted_candidates[:top_k]

        new_generation = list(elite)

        while len(new_generation) < self._population_size:
            parent1, parent2 = random.sample(elite, 2)
            child = self._crossover(parent1, parent2)
            new_generation.append(child)

        for candidate in new_generation:
            candidate.age += 1

        self._candidates = new_generation
        self._generation += 1

        return new_generation

    def _crossover(
        self,
        parent1: EvolutionCandidate,
        parent2: EvolutionCandidate
    ) -> EvolutionCandidate:
        """交叉"""
        p1_params = parent1.strategy.parameters
        p2_params = parent2.strategy.parameters

        child_params = {}
        for key in p1_params:
            if key in p2_params:
                child_params[key] = (p1_params[key] + p2_params[key]) / 2

        mutation_rate = 0.1
        for key in child_params:
            if random.random() < mutation_rate:
                range_val = self._get_param_range(key)
                if range_val:
                    min_val, max_val = range_val
                    child_params[key] = random.uniform(min_val, max_val)

        child_strategy = GeneratedStrategy(
            strategy_id=f"evolved_{self._generation}_{random.randint(1000, 9999)}",
            name=f"进化策略-{self._generation}",
            strategy_type=parent1.strategy.strategy_type,
            parameters=child_params,
            rules=parent1.strategy.rules[:],
            expected_return=parent1.strategy.expected_return,
            risk_level=parent1.strategy.risk_level,
            confidence=0.5,
            generation_method="crossover"
        )

        return EvolutionCandidate(strategy=child_strategy, fitness=0.5)

    def _get_param_range(self, param_name: str) -> Optional[Tuple[float, float]]:
        """获取参数范围"""
        ranges = {
            "stop_loss": (0.02, 0.15),
            "take_profit": (0.03, 0.25),
            "position_size": (0.1, 1.0),
            "volume_threshold": (0.5, 3.0),
            "price_change_threshold": (1.0, 5.0),
            "holding_period": (1, 20)
        }
        return ranges.get(param_name)

    def get_best_candidate(self) -> Optional[EvolutionCandidate]:
        """获取最优候选"""
        if not self._candidates:
            return None
        return max(self._candidates, key=lambda c: c.fitness)

    def get_generation(self) -> int:
        """获取当前代数"""
        return self._generation


class StrategyEvaluator:
    """
    策略评估器

    评估生成策略的质量
    """

    def __init__(self):
        self._evaluation_history: List[Dict[str, Any]] = []

    def evaluate(
        self,
        strategy: GeneratedStrategy,
        historical_performance: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        评估策略

        Args:
            strategy: 生成的策略
            historical_performance: 历史绩效数据

        Returns:
            评估结果
        """
        scores = {}

        scores["complexity"] = self._evaluate_complexity(strategy)
        scores["diversity"] = self._evaluate_diversity(strategy)
        scores["consistency"] = self._evaluate_consistency(strategy)
        scores["realism"] = self._evaluate_realism(strategy)

        if historical_performance:
            scores["backtest"] = historical_performance.get("success_rate", 0.5)

        overall_score = sum(scores.values()) / len(scores)

        result = {
            "strategy_id": strategy.strategy_id,
            "scores": scores,
            "overall_score": overall_score,
            "quality_grade": self._score_to_grade(overall_score),
            "recommendation": self._get_recommendation(overall_score)
        }

        self._evaluation_history.append(result)

        return result

    def _evaluate_complexity(self, strategy: GeneratedStrategy) -> float:
        """评估复杂度"""
        rule_count = len(strategy.rules)
        param_count = len(strategy.parameters)

        complexity = min(1.0, (rule_count * 0.3 + param_count * 0.2) / 3.0)

        return 1.0 - complexity

    def _evaluate_diversity(self, strategy: GeneratedStrategy) -> float:
        """评估多样性"""
        param_values = list(strategy.parameters.values())
        if len(param_values) < 2:
            return 0.5

        variance = sum((v - sum(param_values)/len(param_values))**2
                      for v in param_values) / len(param_values)

        diversity = min(1.0, variance * 10)
        return diversity

    def _evaluate_consistency(self, strategy: GeneratedStrategy) -> float:
        """评估一致性"""
        return 0.7

    def _evaluate_realism(self, strategy: GeneratedStrategy) -> float:
        """评估现实性"""
        params = strategy.parameters

        if params.get("position_size", 0) > 1.0:
            return 0.2
        if params.get("stop_loss", 0) > 0.3:
            return 0.3
        if params.get("take_profit", 0) > 0.5:
            return 0.3

        return 0.8

    def _score_to_grade(self, score: float) -> str:
        """评分转等级"""
        if score >= 0.85:
            return "A+"
        elif score >= 0.75:
            return "A"
        elif score >= 0.65:
            return "B+"
        elif score >= 0.55:
            return "B"
        elif score >= 0.45:
            return "C"
        else:
            return "D"

    def _get_recommendation(self, score: float) -> str:
        """获取建议"""
        if score >= 0.75:
            return "建议实盘测试"
        elif score >= 0.55:
            return "建议回测验证"
        elif score >= 0.45:
            return "需要进一步优化"
        else:
            return "不建议使用"


class StrategyGenerator:
    """
    策略生成器

    结合模式识别和模板生成新策略
    """

    def __init__(self):
        self.pattern_recognizer = PatternRecognizer()
        self.parameter_tuner = ParameterTuner()
        self.template_library = TemplateLibrary()
        self.evolutionary_optimizer = EvolutionaryOptimizer()
        self.evaluator = StrategyEvaluator()
        self._generation_counter = 0

    def generate_from_pattern(
        self,
        pattern: StrategyPattern
    ) -> GeneratedStrategy:
        """
        从模式生成策略

        Args:
            pattern: 策略模式

        Returns:
            生成的策略
        """
        self._generation_counter += 1

        strategy_type = self._infer_strategy_type(pattern)

        initial_params = self.parameter_tuner.suggest_initial_params(strategy_type)

        rules = [
            f"if price_change > {pattern.conditions.get('price_change_min', 2.0)}%: buy",
            f"if volume_ratio > {pattern.conditions.get('volume_ratio_min', 1.5)}: confirm",
            f"stop_loss = {initial_params.get('stop_loss', 0.05)}",
            f"holding_period <= {int(initial_params.get('holding_period', 5))} days"
        ]

        strategy = GeneratedStrategy(
            strategy_id=f"gen_{self._generation_counter}",
            name=f"{pattern.name}-策略",
            strategy_type=strategy_type,
            parameters=initial_params,
            rules=rules,
            expected_return=pattern.avg_return if pattern.avg_return > 0 else 0.1,
            risk_level=self._estimate_risk_level(pattern),
            confidence=min(0.9, pattern.success_rate + 0.1),
            generation_method="pattern_based",
            parent_pattern_id=pattern.pattern_id
        )

        return strategy

    def generate_from_template(
        self,
        strategy_type: StrategyType,
        customizations: Optional[Dict[str, Any]] = None
    ) -> GeneratedStrategy:
        """
        从模板生成策略

        Args:
            strategy_type: 策略类型
            customizations: 自定义参数

        Returns:
            生成的策略
        """
        self._generation_counter += 1

        template = self.template_library.get_template(strategy_type)
        if not template:
            template = self.template_library.get_template(StrategyType.MOMENTUM)

        params = self.parameter_tuner.suggest_initial_params(strategy_type)

        if customizations:
            params.update(customizations)

        strategy = GeneratedStrategy(
            strategy_id=f"gen_{self._generation_counter}",
            name=template.get("name", f"{strategy_type.value}策略"),
            strategy_type=strategy_type,
            parameters=params,
            rules=template.get("rules", []),
            expected_return=template.get("expected_return", 0.1),
            risk_level=template.get("risk_level", "medium"),
            confidence=0.6,
            generation_method="template_based"
        )

        return strategy

    def evolve_strategy(
        self,
        strategy: GeneratedStrategy,
        performance_metrics: Dict[str, float]
    ) -> GeneratedStrategy:
        """
        进化策略

        Args:
            strategy: 原始策略
            performance_metrics: 绩效指标

        Returns:
            进化后的策略
        """
        self._generation_counter += 1

        candidate = EvolutionCandidate(
            strategy=strategy,
            fitness=0.5
        )

        new_fitness = self.evolutionary_optimizer.evaluate_fitness(
            candidate,
            performance_metrics
        )
        candidate.fitness = new_fitness

        self.evolutionary_optimizer.initialize_population([strategy])

        evolved_candidates = self.evolutionary_optimizer.evolve(top_k=1)

        if evolved_candidates:
            evolved = evolved_candidates[0]
            evolved.strategy.strategy_id = f"evolved_{self._generation_counter}"
            evolved.strategy.generation_method = "evolutionary"
            evolved.strategy.confidence = min(0.9, new_fitness + 0.2)

            return evolved.strategy

        new_params = self.parameter_tuner.tune_parameters(
            strategy.parameters,
            performance_metrics.get("success_rate", 0.5)
        )

        strategy.parameters = new_params
        strategy.strategy_id = f"tuned_{self._generation_counter}"
        strategy.generation_method = "parameter_tuning"

        return strategy

    def generate_batch(
        self,
        count: int,
        diversity: bool = True
    ) -> List[GeneratedStrategy]:
        """
        批量生成策略

        Args:
            count: 生成数量
            diversity: 是否保证多样性

        Returns:
            生成的策略列表
        """
        strategies = []

        pattern = StrategyPattern(
            pattern_id="batch_pattern",
            name="批量生成模式",
            description="批量生成的默认模式",
            conditions={"price_change_min": 2.0, "volume_ratio_min": 1.5},
            actions={"action": "buy"},
            success_rate=0.6,
            sample_count=10
        )

        for i in range(count):
            if diversity:
                strategy_type = list(StrategyType)[i % len(StrategyType)]
            else:
                strategy_type = StrategyType.MOMENTUM

            if i % 2 == 0:
                strategy = self.generate_from_pattern(pattern)
            else:
                strategy = self.generate_from_template(strategy_type)

            strategies.append(strategy)

        return strategies

    def _infer_strategy_type(self, pattern: StrategyPattern) -> StrategyType:
        """推断策略类型"""
        conditions = pattern.conditions

        if conditions.get("trend") == "up" and conditions.get("price_change_min", 0) > 2:
            return StrategyType.MOMENTUM
        elif conditions.get("oversold_indicator"):
            return StrategyType.REVERSAL
        elif conditions.get("breakout_type") == "volume":
            return StrategyType.BREAKOUT
        elif pattern.name and "价值" in pattern.name:
            return StrategyType.VALUE
        elif pattern.name and "成长" in pattern.name:
            return StrategyType.GROWTH

        return StrategyType.MOMENTUM

    def _estimate_risk_level(self, pattern: StrategyPattern) -> str:
        """估算风险等级"""
        if pattern.avg_return > 0.15:
            return "high"
        elif pattern.avg_return > 0.08:
            return "medium"
        else:
            return "low"


class MetaEvolutionEnhanced:
    """
    增强版元进化引擎

    在原 MetaEvolution 基础上增加自动策略生成能力
    """

    def __init__(self):
        self.strategy_generator = StrategyGenerator()
        self._generated_strategies: List[GeneratedStrategy] = []
        self._strategy_performance: Dict[str, Dict[str, float]] = {}
        self._last_generation_time = 0.0

    def generate_strategy(
        self,
        strategy_type: Optional[StrategyType] = None,
        based_on_pattern: bool = False
    ) -> Optional[GeneratedStrategy]:
        """
        生成新策略

        Args:
            strategy_type: 策略类型（随机选择如果为None）
            based_on_pattern: 是否基于识别的模式生成

        Returns:
            生成的策略
        """
        patterns = self.strategy_generator.pattern_recognizer.get_all_patterns()

        if based_on_pattern and patterns:
            pattern = max(patterns, key=lambda p: p.success_rate)
            strategy = self.strategy_generator.generate_from_pattern(pattern)
        elif strategy_type:
            strategy = self.strategy_generator.generate_from_template(strategy_type)
        else:
            strategy_type = random.choice(list(StrategyType))
            strategy = self.strategy_generator.generate_from_template(strategy_type)

        self._generated_strategies.append(strategy)
        self._last_generation_time = time.time()

        return strategy

    def evolve_existing_strategy(
        self,
        strategy_id: str,
        performance: Dict[str, float]
    ) -> Optional[GeneratedStrategy]:
        """
        进化现有策略

        Args:
            strategy_id: 策略ID
            performance: 绩效指标

        Returns:
            进化后的策略
        """
        strategy = None
        for s in self._generated_strategies:
            if s.strategy_id == strategy_id:
                strategy = s
                break

        if not strategy:
            return None

        evolved = self.strategy_generator.evolve_strategy(strategy, performance)

        for i, s in enumerate(self._generated_strategies):
            if s.strategy_id == strategy_id:
                self._generated_strategies[i] = evolved
                break

        self._strategy_performance[evolved.strategy_id] = performance

        return evolved

    def get_generated_strategies(
        self,
        min_confidence: float = 0.0,
        strategy_type: Optional[StrategyType] = None
    ) -> List[GeneratedStrategy]:
        """
        获取生成的策略

        Args:
            min_confidence: 最低置信度
            strategy_type: 策略类型过滤

        Returns:
            策略列表
        """
        strategies = self._generated_strategies

        if min_confidence > 0:
            strategies = [s for s in strategies if s.confidence >= min_confidence]

        if strategy_type:
            strategies = [s for s in strategies if s.strategy_type == strategy_type]

        return sorted(strategies, key=lambda s: s.confidence, reverse=True)

    def get_best_strategy(self) -> Optional[GeneratedStrategy]:
        """获取最佳策略"""
        strategies = self.get_generated_strategies(min_confidence=0.5)
        if strategies:
            return max(strategies, key=lambda s: s.expected_return)
        return None

    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "total_generated": len(self._generated_strategies),
            "last_generation_time": self._last_generation_time,
            "pattern_count": len(self.strategy_generator.pattern_recognizer.get_all_patterns()),
            "strategy_types": {
                st.value: len([s for s in self._generated_strategies if s.strategy_type == st])
                for st in StrategyType
            },
            "best_strategy": (
                self.get_best_strategy().__dict__
                if self.get_best_strategy() else None
            )
        }
