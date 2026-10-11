"""
ManasEngine 单元测试
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.attention.kernel.manas_engine import (
    ManasEngine,
    TimingEngine,
    RegimeEngine,
    ConfidenceEngine,
    RiskEngine,
    MetaManas,
    BiasState,
    ManasOutput,
    MANAS_OUTPUT_GROUPS,
    HarmonyState,
    AttentionFocus,
    PortfolioSignal,
)
from deva.naja.attention.kernel.manas_inputs import (
    INPUT_CONTRACTS,
    DictBackedInputs,
    check_contract,
    missing_methods,
)


class TestTimingEngine(unittest.TestCase):
    """TimingEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = TimingEngine()
        score = engine.compute(session_manager=None, scanner=None)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_timing_range(self):
        """测试时机分数范围"""
        engine = TimingEngine()
        for _ in range(10):
            score = engine.compute()
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)


class TestRegimeEngine(unittest.TestCase):
    """RegimeEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = RegimeEngine()
        score = engine.compute(scanner=None, macro_signal=0.5)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, -1.0)
        self.assertLessEqual(score, 1.0)

    def test_regime_range(self):
        """测试环境分数范围"""
        engine = RegimeEngine()
        for macro in [0.0, 0.3, 0.5, 0.7, 1.0]:
            score = engine.compute(macro_signal=macro)
            self.assertGreaterEqual(score, -1.0)
            self.assertLessEqual(score, 1.0)


class TestConfidenceEngine(unittest.TestCase):
    """ConfidenceEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = ConfidenceEngine()
        score = engine.compute(bandit_tracker=None)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.5)

    def test_confidence_range(self):
        """测试自信度范围"""
        engine = ConfidenceEngine()
        for _ in range(10):
            score = engine.compute()
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.5)


class TestRiskEngine(unittest.TestCase):
    """RiskEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = RiskEngine()
        T = engine.compute(portfolio=None, scanner=None)
        self.assertIsInstance(T, float)
        self.assertGreater(T, 0.0)
        self.assertLessEqual(T, 2.0)

    def test_temperature_range(self):
        """测试温度范围"""
        engine = RiskEngine()
        for _ in range(10):
            T = engine.compute()
            self.assertGreater(T, 0.0)
            self.assertLessEqual(T, 2.0)


class TestMetaManas(unittest.TestCase):
    """MetaManas 测试"""

    def test_bias_detection_greed(self):
        """测试贪检测"""
        meta = MetaManas()

        recent_pnl = [0.1, 0.1, 0.1, 0.1, 0.1]
        bias, correction = meta.detect_and_correct(
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.8
        )

        self.assertEqual(bias, BiasState.GREED)
        self.assertLess(correction, 1.0)

    def test_bias_detection_fear(self):
        """测试惧检测"""
        meta = MetaManas()

        recent_pnl = [-0.1, -0.1, -0.1, -0.1, -0.1]
        bias, correction = meta.detect_and_correct(
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.2
        )

        self.assertEqual(bias, BiasState.FEAR)
        self.assertLess(correction, 1.0)

    def test_bias_neutral(self):
        """测试中性状态"""
        meta = MetaManas()

        recent_pnl = [0.01, -0.01, 0.01, -0.01, 0.0]
        bias, correction = meta.detect_and_correct(
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.5
        )

        self.assertEqual(bias, BiasState.NEUTRAL)
        self.assertEqual(correction, 1.0)

    def test_insufficient_data(self):
        """测试数据不足时"""
        meta = MetaManas()

        recent_pnl = [0.1]
        bias, correction = meta.detect_and_correct(
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.5
        )

        self.assertEqual(bias, BiasState.NEUTRAL)
        self.assertEqual(correction, 1.0)


class TestManasOutput(unittest.TestCase):
    """ManasOutput 测试"""

    def test_to_dict(self):
        """测试字典转换"""
        output = ManasOutput(
            manas_score=0.7,
            timing_score=0.8,
            regime_score=0.5,
            confidence_score=0.6,
            risk_temperature=1.2,
            should_act=True,
            action_gate_reason="时机成熟 | 顺风 | ✓通过",
            bias_state=BiasState.NEUTRAL,
            bias_correction=1.0,
            alpha=0.9,
            attention_focus=0.7,
        )

        d = output.to_dict()

        self.assertIn('manas_score', d)
        self.assertIn('timing_score', d)
        self.assertIn('regime_score', d)
        self.assertIn('confidence_score', d)
        self.assertIn('risk_temperature', d)
        self.assertIn('should_act', d)
        self.assertIn('bias_state', d)
        self.assertIn('alpha', d)
        self.assertEqual(d['bias_state'], 'neutral')

        # to_dict() 必须覆盖 dataclass 的全部字段，一个都不能漏。
        # 这里原来漏了 ai_compute_direction（23 个字段只出了 22 个键），
        # 下游 KernelOutput 也就永远拿到默认的 "unknown"。
        import dataclasses

        self.assertEqual(
            set(d), {f.name for f in dataclasses.fields(ManasOutput)}
        )

    def test_groups_cover_all_fields_exactly(self):
        """分组必须是 dataclass 字段的一个划分：不重、不漏、不凭空。

        以后给 ManasOutput 加字段而忘了归组，to_grouped_dict() 会静默少一块，
        UI 上表现为"某个面板永远空着"——这类 bug 很难查，所以在这里卡死。
        """
        import dataclasses

        declared = {f.name for f in dataclasses.fields(ManasOutput)}
        grouped = [f for fields in MANAS_OUTPUT_GROUPS.values() for f in fields]

        self.assertEqual(len(grouped), len(set(grouped)), "有字段被重复归组")
        self.assertEqual(set(grouped), declared)

    def test_group_enum_values_match_to_dict(self):
        """group() 与 to_dict() 对同一字段必须给出同一个值。"""
        output = ManasOutput(
            manas_score=0.7,
            harmony_state=HarmonyState.RESONANCE,
            focus_enum=AttentionFocus.ACCUMULATE,
            portfolio_signal=PortfolioSignal.ACCUMULATE,
        )

        flat = output.to_dict()
        for group_name in MANAS_OUTPUT_GROUPS:
            for field, value in output.group(group_name).items():
                self.assertIn(field, flat, f"{group_name}.{field} 不在 to_dict() 里")
                self.assertEqual(value, flat[field], f"{group_name}.{field} 与 to_dict() 不一致")

        # 枚举必须落成 .value 而不是 Enum 实例
        self.assertEqual(output.group('harmony')['harmony_state'], 'resonance')
        self.assertEqual(output.group('focus')['focus_enum'], 'accumulate')

    def test_to_grouped_dict_is_json_serializable(self):
        """嵌套视图要能直接过 json.dumps（含 tuple 容器）。"""
        import json

        output = ManasOutput(hot_narratives=[('AI算力', 0.9), ('电力', 0.6)])
        nested = output.to_grouped_dict()

        self.assertEqual(set(nested), set(MANAS_OUTPUT_GROUPS))
        self.assertEqual(nested['cognition']['hot_narratives'], [['AI算力', 0.9], ['电力', 0.6]])
        json.dumps(nested, ensure_ascii=False)

    def test_unknown_group_raises_key_error(self):
        """拼错组名要立刻炸，不能静默返回空 dict。"""
        with self.assertRaises(KeyError):
            ManasOutput().group('not_a_group')


class TestManasEngine(unittest.TestCase):
    """ManasEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        manas = ManasEngine()
        output = manas.compute()

        self.assertIsInstance(output, ManasOutput)
        self.assertGreaterEqual(output.manas_score, 0.0)
        self.assertLessEqual(output.manas_score, 1.0)
        self.assertIsInstance(output.should_act, bool)

    def test_manas_score_range(self):
        """测试 manas 分数范围"""
        manas = ManasEngine()
        for _ in range(20):
            output = manas.compute()
            self.assertGreaterEqual(output.manas_score, 0.0)
            self.assertLessEqual(output.manas_score, 1.0)

    def test_gate_mechanism(self):
        """测试行动门"""
        manas = ManasEngine()

        output = manas.compute()

        if output.manas_score > 0.5:
            self.assertTrue(output.should_act)
        else:
            self.assertFalse(output.should_act)

    def test_record_pnl(self):
        """测试记录盈亏"""
        manas = ManasEngine()

        manas.record_pnl(0.05)
        manas.record_pnl(0.03)
        manas.record_pnl(-0.02)

        self.assertEqual(len(manas._recent_pnl), 3)

    def test_reset_bias(self):
        """测试重置偏差"""
        manas = ManasEngine()
        manas.meta_manas.bias_state = BiasState.GREED

        manas.reset_bias()

        self.assertEqual(manas.meta_manas.bias_state, BiasState.NEUTRAL)

    def test_get_state(self):
        """测试获取状态"""
        manas = ManasEngine()
        manas.compute()

        state = manas.get_state()

        self.assertIsInstance(state, dict)
        self.assertIn('manas_score', state)

    def test_compute_populates_ai_compute_direction(self):
        """compute() 必须把认知层的 AI 算力方向写进输出。

        dataclass 默认值是 "unknown"（哨兵值），compute() 原先从不赋值，
        于是下游 KernelOutput.ai_compute_direction 永远是 "unknown"。
        """
        output = ManasEngine().compute()
        self.assertIn(output.ai_compute_direction, ('up', 'down', 'neutral'))

    def test_alpha_calculation(self):
        """测试 alpha 计算"""
        manas = ManasEngine()
        output = manas.compute()

        self.assertGreaterEqual(output.alpha, 0.3)
        self.assertLessEqual(output.alpha, 1.5)

    def test_bias_correction_range(self):
        """测试偏差修正范围"""
        manas = ManasEngine()

        for i in range(20):
            output = manas.compute()

            self.assertGreaterEqual(output.bias_correction, 0.5)
            self.assertLessEqual(output.bias_correction, 1.0)


class TestManasEngineIntegration(unittest.TestCase):
    """ManasEngine 集成测试"""

    def test_multiple_compute(self):
        """测试多次计算"""
        manas = ManasEngine()

        outputs = []
        for _ in range(10):
            output = manas.compute()
            outputs.append(output)

        self.assertEqual(len(outputs), 10)

        for out in outputs:
            self.assertIsInstance(out.manas_score, float)

    def test_pnl_feedback_loop(self):
        """测试盈亏反馈循环"""
        manas = ManasEngine()

        initial_output = manas.compute()

        for _ in range(5):
            manas.record_pnl(0.05)

        after_greed_output = manas.compute()

        self.assertIsInstance(after_greed_output.manas_score, float)

    def test_timing_consistency(self):
        """测试时机一致性"""
        manas = ManasEngine()

        outputs = []
        for _ in range(5):
            output = manas.compute()
            outputs.append(output)

        timing_scores = [o.timing_score for o in outputs]

        for ts in timing_scores:
            self.assertGreaterEqual(ts, 0.0)
            self.assertLessEqual(ts, 1.0)


class TestManasInputContract(unittest.TestCase):
    """ManasEngine 的四类外部输入契约。

    为什么需要契约：manas_engine.py 的取数全部是「鸭子类型 + try/except 兜底」，
    方法缺失时静默返回默认值 ——「接口接错了」和「数据恰好等于默认值」在外部
    完全无法区分。契约把这层静默失效显式化。
    """

    #: 正确的生产实现，必须始终满足各自契约
    SATISFIED = [
        ("ClockView", "deva.naja.radar.global_market_config", "MarketSessionManager"),
        ("MarketView", "deva.naja.radar.global_market_scanner", "GlobalMarketScanner"),
        ("PortfolioView", "deva.naja.bandit.virtual_portfolio", "VirtualPortfolio"),
        ("StrategyView", "deva.naja.bandit.tracker", "BanditPositionTracker"),
    ]

    #: P1 接线修复前存在的缺口：现在必须**已经补齐**。
    #: 保留这份清单是为了让「修复被回退」也能被测出来——
    #: 若这里重新出现缺失，说明有人把接线改回了旧状态。
    FIXED_GAPS = [
        ("ClockView", "deva.naja.radar.global_market_config", "MarketSessionManager",
         {"get_market_status", "get_session_remaining_seconds"}),
        ("MarketView", "deva.naja.radar.global_market_scanner", "GlobalMarketScanner",
         {"get_market_volatility"}),
    ]

    #: 不再承担该角色的类（保留在仓库里，仅作说明）。
    #: TradingClock 有 cn_phase / us_phase 语义，另有用途；不要给它补
    #: get_market_status —— 那会把时段语义混进 clock。
    NOT_USED_FOR_ROLE = [
        ("ClockView", "deva.naja.radar.trading_clock", "TradingClock",
         {"get_market_status", "get_session_remaining_seconds"}),
    ]

    def test_production_implementations_satisfy_contracts(self):
        """正确的生产实现必须满足契约；一旦有人删了方法，这里立刻失败。"""
        import importlib

        for contract_name, module_path, class_name in self.SATISFIED:
            cls = getattr(importlib.import_module(module_path), class_name)
            missing = check_contract(cls, contract_name)
            self.assertEqual(
                missing, [],
                "{} 不再满足 {}，缺失 {}".format(class_name, contract_name, missing),
            )

    def test_previously_known_gaps_are_closed(self):
        """P1 已补齐的缺口不许回退（收紧后 KNOWN_GAPS 为空集）。"""
        import importlib

        for contract_name, module_path, class_name, was_missing in self.FIXED_GAPS:
            self.assertTrue(was_missing, "FIXED_GAPS 条目不应为空")
            cls = getattr(importlib.import_module(module_path), class_name)
            actual = set(check_contract(cls, contract_name))
            self.assertEqual(
                actual, set(),
                "{} 的 {} 缺口被回退了，仍缺 {}".format(class_name, contract_name, sorted(actual)),
            )

    def test_deprecated_roles_are_documented_not_silent(self):
        """已弃用的角色要显式登记——防止有人把它当作「契约实现」重新接回去。"""
        import importlib

        for contract_name, module_path, class_name, expected_missing in self.NOT_USED_FOR_ROLE:
            cls = getattr(importlib.import_module(module_path), class_name)
            actual = set(check_contract(cls, contract_name))
            self.assertEqual(
                actual, set(expected_missing),
                "{} 对 {} 的实际缺失与登记不符：{}".format(
                    class_name, contract_name, sorted(actual)),
            )

    def test_kernel_wiring_satisfies_contracts(self):
        """内核真正吐出来的四路输入必须满足契约（P1.2 / P1.3 的回归网）。

        类级检查只能证明「这个类有能力满足契约」，证明不了「它真的被传进去了」——
        原始缺陷（portfolio / bandit_tracker 恒 None、session_manager 传
        TradingClock）恰恰是从类级检查里看不出来的。
        """
        from deva.naja.attention.os.os_kernel import OSAttentionKernel
        from deva.naja.bandit.virtual_portfolio import VirtualPortfolio
        from deva.naja.bandit.tracker import BanditPositionTracker

        kernel = OSAttentionKernel()
        # 模拟 container._create_manas_manager() 的装配动作
        kernel.set_manas_dependencies(
            portfolio=VirtualPortfolio(),
            bandit_tracker=BanditPositionTracker(),
        )

        inputs = kernel.get_manas_inputs()
        for key, contract_name in (("session_manager", "ClockView"),
                                   ("scanner", "MarketView"),
                                   ("portfolio", "PortfolioView"),
                                   ("bandit_tracker", "StrategyView")):
            obj = inputs.get(key)
            self.assertIsNotNone(obj, "内核装配的 {} 是 None（该维度会整体退化）".format(key))
            self.assertEqual(
                check_contract(obj, contract_name), [],
                "内核装配的 {} ({}) 不满足 {}".format(
                    key, type(obj).__name__, contract_name),
            )

    @staticmethod
    def _warm(engine, src=None, use_inputs=False):
        """连算 6 次并返回最后一次输出（波动率维需 volatility_sample=5 次热身）。"""
        out = None
        for _ in range(6):
            engine._last_output = None
            engine._last_update = 0.0
            kwargs = ({"session_manager": src, "scanner": src,
                       "portfolio": src, "bandit_tracker": src} if use_inputs else {})
            out = engine.compute(**kwargs)
        return out

    def test_real_inputs_defrost_the_frozen_dimensions(self):
        """接上真实输入后，T / confidence / timing 必须离开常数点。

        旧接线（四路输入退化）下 T 恒 1.25、confidence 恒 0.35、
        时间压力维恒 0.5；若哪天又退回常数，这条会红。
        """
        frozen = self._warm(ManasEngine())
        self.assertAlmostEqual(frozen.risk_temperature, 1.25, places=6)
        self.assertAlmostEqual(frozen.confidence_score, 0.35, places=6)

        src = DictBackedInputs(
            market_status="open", remaining_seconds=7200,
            market_volatility=1.8,
            ticks={"600000": 1.2, "000001": -0.4},
            us_trading_phase="trading",
            available_capital=30.0, total_capital=100.0, total_return=-6.0,
            position_returns=[0.02, -0.01, 0.03, 0.01], total_trades=12,
        )
        live_engine = ManasEngine()
        live_engine.set_portfolio(src)
        live_engine.set_bandit_tracker(src)
        live = self._warm(live_engine, src=src, use_inputs=True)

        self.assertGreater(live.risk_temperature, frozen.risk_temperature,
                           "波动率/回撤接上后 T 应上升（更保守）")
        self.assertNotAlmostEqual(live.confidence_score, frozen.confidence_score, places=6)
        self.assertNotAlmostEqual(live.timing_score, frozen.timing_score, places=6)

    def test_dict_backed_inputs_satisfy_all_contracts(self):
        """纯 dict 适配器必须同时满足四个契约（跨域复用的前提）。"""
        for contract_name in INPUT_CONTRACTS:
            self.assertEqual(check_contract(DictBackedInputs, contract_name), [])

    def test_protocols_are_runtime_checkable(self):
        """契约要能直接用于 isinstance（runtime_checkable）。"""
        from deva.naja.attention.kernel.manas_inputs import (
            ClockView, MarketView, PortfolioView, StrategyView,
        )

        src = DictBackedInputs()
        for protocol in (ClockView, MarketView, PortfolioView, StrategyView):
            self.assertIsInstance(src, protocol, "{} 不是 runtime_checkable".format(protocol))

    def test_checker_detects_missing_methods(self):
        """校验器必须真的能发现缺失，而不是恒返回空列表。"""

        class NotAClock:
            def get_market_status(self, market_id):
                return None

        self.assertEqual(check_contract(NotAClock, "ClockView"),
                         ["get_session_remaining_seconds"])
        self.assertEqual(missing_methods(NotAClock, ("get_market_status", "nope")), ["nope"])

    def test_unknown_contract_name_raises(self):
        """拼错契约名要立刻炸，不能静默「通过」。"""
        with self.assertRaises(KeyError):
            check_contract(DictBackedInputs, "ClocView")


class TestManasEngineDecoupling(unittest.TestCase):
    """ManasEngine 是否真的消费了外部输入。

    这些测试用 DictBackedInputs 直接喂数，绕开真实接线，因此可以精确定位
    「引擎有没有读这个维度」；接线层面的问题由 TestManasInputContract 暴露。
    """

    def setUp(self):
        self.src = DictBackedInputs(
            market_status="open",
            remaining_seconds=3600,
            market_volatility=1.8,
            ticks={"600000": 1.5, "000001": -0.5, "600519": 0.8},
            us_trading_phase="trading",
            available_capital=20.0,
            total_capital=100.0,
            total_return=0.06,
            position_returns=[0.05, 0.04, 0.03, 0.06, 0.02],
            total_trades=60,
        )

    def test_engine_runs_on_dict_inputs_only(self):
        """只给 dict 适配器，ManasEngine 就能算出非退化分数。

        这同时是跨域复用的可行性证明：引擎不依赖任何交易对象。
        """
        output = ManasEngine().compute(
            session_manager=self.src,
            scanner=self.src,
            portfolio=self.src,
            bandit_tracker=self.src,
        )

        # 时间压力 0.8 + 波动率 0.5 + 密度 0.6 + 结构 0.8 → 明显不等于全兜底的 0.5
        self.assertGreater(output.timing_score, 0.6)

        # T = (1 + (1-0.2)*0.5) * 1.1(回撤 0.06) * 1.1(波动 1.8) = 1.694
        self.assertGreater(output.risk_temperature, 1.3)
        self.assertLess(output.risk_temperature, 2.0)  # 未撞 clamp，说明是算出来的

        # confidence = 1.0(命中率)*0.4 + 0.02*0.3 + 0.9(bandit)*0.3 ≈ 0.676
        self.assertGreater(output.confidence_score, 0.5)

    def test_dimension_engines_consume_inputs_individually(self):
        """逐个维度确认引擎确实读了输入，而不是走了兜底。"""
        timing = TimingEngine().compute(session_manager=self.src, scanner=self.src)
        self.assertNotAlmostEqual(timing, 0.5, places=3)

        regime = RegimeEngine().compute(scanner=self.src, macro_signal=0.5)
        self.assertNotAlmostEqual(regime, 0.0, places=3)

        risk = RiskEngine().compute(portfolio=self.src, scanner=self.src)
        self.assertGreater(risk, 1.3)

        conf = ConfidenceEngine().compute(bandit_tracker=self.src)
        self.assertGreater(conf, 0.5)

    def test_all_none_inputs_degrade_to_fixed_constants(self):
        """全 None 时各引擎退化成的固定值 —— 这是「接线缺口」的指纹。

        注意这几个常数**不是**安全兜底，而是把整条维度摘掉：
        TimingEngine 四个维度里两个、RiskEngine 三个输入里两个、ConfidenceEngine
        三个维度里三个，全部变成常数。P1 修的是接线（不再传 None），不是这些兜底值，
        所以本测试在 P1 之后仍应成立。
        """
        self.assertAlmostEqual(
            TimingEngine().compute(session_manager=None, scanner=None), 0.5, places=6)
        self.assertAlmostEqual(
            RegimeEngine().compute(scanner=None, macro_signal=0.5), 0.0, places=6)
        self.assertAlmostEqual(
            RiskEngine().compute(portfolio=None, scanner=None), 1.25, places=6)
        self.assertAlmostEqual(
            ConfidenceEngine().compute(bandit_tracker=None), 0.35, places=6)


class TestPortfolioViewShape(unittest.TestCase):
    """PortfolioView.get_summary() 的**返回形状**，不只是「方法是否存在」。

    踩过的坑：VirtualPortfolio 有 get_summary（类级契约检查通过），但它返回的
    字典缺 total_capital。下游三处都写 `summary.get('total_capital', 1)`，
    分母兜底成 1，cash_ratio 于是退化成「可用资金的数值本身」（如 590000），
    RiskEngine 的 base_T 变成大负数再撞下限 —— T 恒 0.5，看起来像「市场极度安全」。
    类级契约检查看不见这一层，所以这里单独锁返回形状。
    """

    REQUIRED_KEYS = ("available_capital", "total_capital", "total_return")

    def test_virtual_portfolio_summary_shape(self):
        from deva.naja.bandit.virtual_portfolio import VirtualPortfolio

        summary = VirtualPortfolio().get_summary()
        for key in self.REQUIRED_KEYS:
            self.assertIn(
                key, summary,
                "get_summary() 缺 {}：cash_ratio 的分母会失守".format(key))

    def test_risk_engine_cash_ratio_stays_in_unit_interval(self):
        """cash_ratio ∈ [0,1]，T ∈ [0.5,2]；越界说明分母又没接上。"""
        from deva.naja.bandit.virtual_portfolio import VirtualPortfolio

        vp = VirtualPortfolio()
        engine = RiskEngine()
        ratio = engine._get_cash_ratio(vp)
        self.assertGreaterEqual(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)
        T = engine.compute(portfolio=vp)
        self.assertGreaterEqual(T, 0.5)
        self.assertLessEqual(T, 2.0)

    def test_missing_total_capital_falls_back_instead_of_exploding(self):
        """分母缺失时用 available+used 复原，而不是把比值算成资金数值本身。"""

        class _NoTotalCapital:
            def get_summary(self):
                return {"available_capital": 590000.0,
                        "used_capital": 410000.0,
                        "total_return": 0.0}

        ratio = RiskEngine()._get_cash_ratio(_NoTotalCapital())
        self.assertAlmostEqual(ratio, 0.59, places=6)
        self.assertLessEqual(ratio, 1.0)

    def test_total_return_is_interpreted_as_percent(self):
        """total_return 口径是百分数：-6.0 表示 -6%（应落进止损档），不是 -600%。"""
        src = DictBackedInputs(total_return=-6.0)
        engine = ManasEngine()
        engine._last_output = None
        engine._last_update = 0.0
        out = engine.compute(portfolio=src)

        self.assertAlmostEqual(out.portfolio_loss_pct, -0.06, places=6)
        # -6% 落在「止损」档（-0.05 以下）。注意 focus_enum 的止损档阈值是
        # -0.1，与 portfolio_signal 的 -0.05 并不一致（既有口径差异，未动）。
        self.assertEqual(out.portfolio_signal, PortfolioSignal.STOP_LOSS)


class TestVisibility(unittest.TestCase):
    """P2：只增不改的可见性（子引擎分量 / 行为偏差镜子 / 行动门留痕）。"""

    def test_sub_engines_record_last_components(self):
        """四个子引擎 compute 后都要留下分量——UI 面板此前读的属性从未存在。"""
        timing = TimingEngine()
        timing.compute(session_manager=None, scanner=None)
        comp = timing.get_last_components()
        for key in ("time_pressure", "volatility", "density", "structure", "timing_score"):
            self.assertIn(key, comp)

        regime = RegimeEngine()
        regime.compute(scanner=None, macro_signal=0.5)
        comp = regime.get_last_components()
        for key in ("trend", "liquidity", "diffusion", "regime_score"):
            self.assertIn(key, comp)

        confidence = ConfidenceEngine()
        confidence.compute(bandit_tracker=None)
        comp = confidence.get_last_components()
        for key in ("hit_rate", "rolling_pnl", "bandit_confidence", "confidence_score"):
            self.assertIn(key, comp)

        risk = RiskEngine()
        risk.compute(portfolio=None, scanner=None)
        comp = risk.get_last_components()
        for key in ("cash_ratio", "drawdown", "volatility", "risk_temperature"):
            self.assertIn(key, comp)

    def test_components_match_reported_scores(self):
        """记录的分量必须与 compute() 的返回值一致（面板不会和打分对不上）。"""
        timing = TimingEngine()
        score = timing.compute(session_manager=None, scanner=None)
        self.assertAlmostEqual(
            timing.get_last_components()["timing_score"], score, places=9)

        risk = RiskEngine()
        temp = risk.compute(portfolio=None, scanner=None)
        self.assertAlmostEqual(
            risk.get_last_components()["risk_temperature"], temp, places=9)

    def test_bias_message_covers_all_states(self):
        """三种偏差状态都要有一句给人看的说明（中性也不能是空串）。"""
        meta = MetaManas()
        for state in (BiasState.NEUTRAL, BiasState.GREED, BiasState.FEAR):
            meta.bias_state = state
            msg = meta.bias_message()
            self.assertTrue(msg, "{} 的教练语为空".format(state.value))
            # get_state() 必须把它一并导出，否则 UI 拿不到
            self.assertEqual(meta.get_state()["bias_message"], msg)

    def test_gate_audit_folds_consecutive_duplicates(self):
        """连续同一判定应折叠成一行（occurrences 累加），否则心跳会刷满缓冲。"""
        from deva.naja.attention.kernel.manas_gate_audit import GateAuditLog

        audit = GateAuditLog(maxlen=10, persist_every=10_000)
        engine = ManasEngine()
        for _ in range(4):
            engine._last_output = None
            engine._last_update = 0.0
            out = engine.compute()
            audit.record(out)

        # 同一次 compute 的判定应与上一次相同 → 折成 1 行
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit.recent(1)[0]["occurrences"], 4)

        stats = audit.stats()
        self.assertEqual(stats["total_decisions"], 4)
        self.assertIsNotNone(stats["hold_ratio"])
        self.assertTrue(stats["top_reasons"])

    def test_gate_audit_appends_on_decision_change(self):
        """判定变化时要新开一行（不能把不同理由折叠掉）。"""
        from deva.naja.attention.kernel.manas_gate_audit import GateAuditLog
        from deva.naja.attention.kernel.manas_engine import ManasOutput, ActionType

        audit = GateAuditLog(maxlen=10, persist_every=10_000)
        audit.record(ManasOutput(action_type=ActionType.HOLD, should_act=False,
                                 action_gate_reason="A"))
        audit.record(ManasOutput(action_type=ActionType.HOLD, should_act=False,
                                 action_gate_reason="A"))
        audit.record(ManasOutput(action_type=ActionType.ACT_FULLY, should_act=True,
                                 action_gate_reason="B"))

        self.assertEqual(len(audit), 2)
        self.assertEqual(audit.recent(2)[0]["occurrences"], 2)
        self.assertEqual(audit.recent(2)[1]["action_type"], "act_fully")

    def test_gate_audit_never_raises(self):
        """留痕是旁路：坏输入只能降级，绝不能把决策路径带崩。"""
        from deva.naja.attention.kernel.manas_gate_audit import GateAuditLog

        audit = GateAuditLog(persist_every=10_000)

        # 完全没有预期字段的对象：走 getattr 默认值，降级成一条「空判定」
        entry = audit.record(object())
        self.assertIsNotNone(entry)
        self.assertEqual(entry["action_type"], None)

        class _Exploding:
            @property
            def should_act(self):
                raise RuntimeError("boom")

        # 取值直接抛异常：构造失败 → 返回 None，且不向外抛
        self.assertIsNone(audit.record(_Exploding()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
