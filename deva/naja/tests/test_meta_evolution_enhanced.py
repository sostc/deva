"""
MetaEvolutionEnhanced 单元测试
"""

import unittest
from deva.naja.evolution.meta_evolution_enhanced import (
    MetaEvolutionEnhanced,
    StrategyGenerator,
    PatternRecognizer,
    ParameterTuner,
    TemplateLibrary,
    EvolutionaryOptimizer,
    StrategyEvaluator,
    GeneratedStrategy,
    StrategyPattern,
    StrategyType,
    EvolutionCandidate,
)


class TestPatternRecognizer(unittest.TestCase):
    """PatternRecognizer 测试"""

    def setUp(self):
        self.recognizer = PatternRecognizer()

    def test_learn_from_decisions(self):
        """测试从决策学习"""
        decisions = [
            {"success": True, "context": {"price_change": 3.0, "volume_ratio": 1.5}},
            {"success": True, "context": {"price_change": 2.5, "volume_ratio": 1.3}},
            {"success": True, "context": {"price_change": 2.0, "volume_ratio": 1.2}},
            {"success": True, "context": {"price_change": 1.8, "volume_ratio": 1.1}},
            {"success": True, "context": {"price_change": 1.5, "volume_ratio": 1.0}},
        ]

        patterns = self.recognizer.learn_from_decisions(decisions)
        self.assertGreater(len(patterns), 0)

    def test_get_pattern(self):
        """测试获取模式"""
        decisions = [
            {"success": True, "context": {"price_change": 3.0, "volume_ratio": 1.5}},
            {"success": True, "context": {"price_change": 2.5, "volume_ratio": 1.3}},
            {"success": True, "context": {"price_change": 2.0, "volume_ratio": 1.2}},
            {"success": True, "context": {"price_change": 1.8, "volume_ratio": 1.1}},
            {"success": True, "context": {"price_change": 1.5, "volume_ratio": 1.0}},
        ]

        patterns = self.recognizer.learn_from_decisions(decisions)
        if patterns:
            pattern_id = patterns[0].pattern_id
            pattern = self.recognizer.get_pattern(pattern_id)
            self.assertIsNotNone(pattern)


class TestParameterTuner(unittest.TestCase):
    """ParameterTuner 测试"""

    def setUp(self):
        self.tuner = ParameterTuner()

    def test_tune_parameters_low_performance(self):
        """测试低性能时调参"""
        current_params = {
            "stop_loss": 0.05,
            "take_profit": 0.10,
            "position_size": 0.3
        }

        new_params = self.tuner.tune_parameters(current_params, 0.3)
        self.assertIsInstance(new_params, dict)
        self.assertIn("stop_loss", new_params)

    def test_suggest_initial_params(self):
        """测试建议初始参数"""
        params = self.tuner.suggest_initial_params(StrategyType.MOMENTUM)
        self.assertIsInstance(params, dict)
        self.assertIn("stop_loss", params)
        self.assertIn("take_profit", params)


class TestTemplateLibrary(unittest.TestCase):
    """TemplateLibrary 测试"""

    def setUp(self):
        self.library = TemplateLibrary()

    def test_get_template(self):
        """测试获取模板"""
        template = self.library.get_template(StrategyType.MOMENTUM)
        self.assertIsNotNone(template)
        self.assertIn("name", template)
        self.assertIn("rules", template)

    def test_get_all_templates(self):
        """测试获取所有模板"""
        templates = self.library.get_all_templates(StrategyType.MOMENTUM)
        self.assertIsInstance(templates, list)
        self.assertGreater(len(templates), 0)


class TestEvolutionaryOptimizer(unittest.TestCase):
    """EvolutionaryOptimizer 测试"""

    def setUp(self):
        self.optimizer = EvolutionaryOptimizer(population_size=5)

    def test_initialize_population(self):
        """测试初始化种群"""
        strategy = GeneratedStrategy(
            strategy_id="test_1",
            name="测试策略",
            strategy_type=StrategyType.MOMENTUM,
            parameters={"stop_loss": 0.05, "take_profit": 0.10},
            rules=["rule1", "rule2"],
            expected_return=0.1,
            risk_level="medium",
            confidence=0.7,
            generation_method="test"
        )

        self.optimizer.initialize_population([strategy])
        self.assertEqual(len(self.optimizer._candidates), 1)

    def test_evaluate_fitness(self):
        """测试评估适应度"""
        strategy = GeneratedStrategy(
            strategy_id="test_1",
            name="测试策略",
            strategy_type=StrategyType.MOMENTUM,
            parameters={"stop_loss": 0.05, "take_profit": 0.10},
            rules=["rule1", "rule2"],
            expected_return=0.1,
            risk_level="medium",
            confidence=0.7,
            generation_method="test"
        )

        candidate = EvolutionCandidate(strategy=strategy, fitness=0.5)

        metrics = {
            "success_rate": 0.7,
            "avg_return": 0.15,
            "max_drawdown": 0.1
        }

        fitness = self.optimizer.evaluate_fitness(candidate, metrics)
        self.assertGreater(fitness, 0.5)

    def test_evolve(self):
        """测试进化"""
        strategies = [
            GeneratedStrategy(
                strategy_id=f"test_{i}",
                name=f"测试策略{i}",
                strategy_type=StrategyType.MOMENTUM,
                parameters={"stop_loss": 0.05, "take_profit": 0.10},
                rules=["rule1"],
                expected_return=0.1,
                risk_level="medium",
                confidence=0.7,
                generation_method="test"
            )
            for i in range(3)
        ]

        self.optimizer.initialize_population(strategies)
        new_generation = self.optimizer.evolve(top_k=2)

        self.assertEqual(len(new_generation), 5)
        self.assertEqual(self.optimizer.get_generation(), 1)


class TestStrategyEvaluator(unittest.TestCase):
    """StrategyEvaluator 测试"""

    def setUp(self):
        self.evaluator = StrategyEvaluator()

    def test_evaluate(self):
        """测试评估策略"""
        strategy = GeneratedStrategy(
            strategy_id="test_1",
            name="测试策略",
            strategy_type=StrategyType.MOMENTUM,
            parameters={
                "stop_loss": 0.05,
                "take_profit": 0.10,
                "position_size": 0.3
            },
            rules=["rule1", "rule2", "rule3"],
            expected_return=0.1,
            risk_level="medium",
            confidence=0.7,
            generation_method="test"
        )

        result = self.evaluator.evaluate(strategy)
        self.assertIn("overall_score", result)
        self.assertIn("quality_grade", result)
        self.assertIn("recommendation", result)
        self.assertGreater(result["overall_score"], 0)


class TestStrategyGenerator(unittest.TestCase):
    """StrategyGenerator 测试"""

    def setUp(self):
        self.generator = StrategyGenerator()

    def test_generate_from_template(self):
        """测试从模板生成"""
        strategy = self.generator.generate_from_template(StrategyType.MOMENTUM)
        self.assertIsInstance(strategy, GeneratedStrategy)
        self.assertEqual(strategy.strategy_type, StrategyType.MOMENTUM)
        self.assertGreater(strategy.confidence, 0)

    def test_generate_from_pattern(self):
        """测试从模式生成"""
        pattern = StrategyPattern(
            pattern_id="test_pattern",
            name="测试模式",
            description="测试",
            conditions={"price_change_min": 2.0, "volume_ratio_min": 1.5},
            actions={"action": "buy"},
            success_rate=0.7,
            sample_count=10
        )

        strategy = self.generator.generate_from_pattern(pattern)
        self.assertIsInstance(strategy, GeneratedStrategy)
        self.assertEqual(strategy.parent_pattern_id, "test_pattern")

    def test_evolve_strategy(self):
        """测试进化策略"""
        strategy = GeneratedStrategy(
            strategy_id="test_1",
            name="测试策略",
            strategy_type=StrategyType.MOMENTUM,
            parameters={"stop_loss": 0.05, "take_profit": 0.10},
            rules=["rule1"],
            expected_return=0.1,
            risk_level="medium",
            confidence=0.7,
            generation_method="test"
        )

        metrics = {
            "success_rate": 0.7,
            "avg_return": 0.15,
            "max_drawdown": 0.1
        }

        evolved = self.generator.evolve_strategy(strategy, metrics)
        self.assertIsInstance(evolved, GeneratedStrategy)

    def test_generate_batch(self):
        """测试批量生成"""
        strategies = self.generator.generate_batch(count=5, diversity=True)
        self.assertEqual(len(strategies), 5)

        types = set(s.strategy_type for s in strategies)
        self.assertGreater(len(types), 1)


class TestMetaEvolutionEnhanced(unittest.TestCase):
    """MetaEvolutionEnhanced 测试"""

    def setUp(self):
        self.enhanced = MetaEvolutionEnhanced()

    def test_generate_strategy(self):
        """测试生成策略"""
        strategy = self.enhanced.generate_strategy(strategy_type=StrategyType.MOMENTUM)
        self.assertIsInstance(strategy, GeneratedStrategy)

    def test_generate_strategy_based_on_pattern(self):
        """测试基于模式生成策略"""
        decisions = [
            {"success": True, "context": {"price_change": 3.0, "volume_ratio": 1.5}},
            {"success": True, "context": {"price_change": 2.5, "volume_ratio": 1.3}},
            {"success": True, "context": {"price_change": 2.0, "volume_ratio": 1.2}},
            {"success": True, "context": {"price_change": 1.8, "volume_ratio": 1.1}},
            {"success": True, "context": {"price_change": 1.5, "volume_ratio": 1.0}},
        ]
        self.enhanced.strategy_generator.pattern_recognizer.learn_from_decisions(decisions)

        strategy = self.enhanced.generate_strategy(based_on_pattern=True)
        self.assertIsInstance(strategy, GeneratedStrategy)

    def test_evolve_existing_strategy(self):
        """测试进化现有策略"""
        strategy = self.enhanced.generate_strategy(strategy_type=StrategyType.MOMENTUM)
        self.assertIsNotNone(strategy)

        performance = {
            "success_rate": 0.7,
            "avg_return": 0.15,
            "max_drawdown": 0.1,
            "sharpe_ratio": 1.2
        }

        evolved = self.enhanced.evolve_existing_strategy(strategy.strategy_id, performance)
        self.assertIsInstance(evolved, GeneratedStrategy)

    def test_get_generated_strategies(self):
        """测试获取生成的策略"""
        self.enhanced.generate_strategy(strategy_type=StrategyType.MOMENTUM)
        self.enhanced.generate_strategy(strategy_type=StrategyType.REVERSAL)

        strategies = self.enhanced.get_generated_strategies()
        self.assertGreaterEqual(len(strategies), 2)

    def test_get_generated_strategies_with_filter(self):
        """测试带过滤获取策略"""
        self.enhanced.generate_strategy(strategy_type=StrategyType.MOMENTUM)
        self.enhanced.generate_strategy(strategy_type=StrategyType.REVERSAL)

        strategies = self.enhanced.get_generated_strategies(strategy_type=StrategyType.MOMENTUM)
        for s in strategies:
            self.assertEqual(s.strategy_type, StrategyType.MOMENTUM)

    def test_get_best_strategy(self):
        """测试获取最佳策略"""
        self.enhanced.generate_strategy(strategy_type=StrategyType.MOMENTUM)
        self.enhanced.generate_strategy(strategy_type=StrategyType.REVERSAL)

        best = self.enhanced.get_best_strategy()
        self.assertIsInstance(best, GeneratedStrategy)

    def test_get_status(self):
        """测试获取状态"""
        self.enhanced.generate_strategy(strategy_type=StrategyType.MOMENTUM)
        self.enhanced.generate_strategy(strategy_type=StrategyType.REVERSAL)

        status = self.enhanced.get_status()
        self.assertIn("total_generated", status)
        self.assertIn("pattern_count", status)
        self.assertIn("strategy_types", status)


if __name__ == "__main__":
    unittest.main()
