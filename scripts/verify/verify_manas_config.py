#!/usr/bin/env python3
"""回归：ManasConfig 默认值 == 重构前散落的字面量，且 config 真的被用上。

改动：manas_engine.py 里的策略参数收敛到 manas_config.ManasConfig，
5 处 append/pop(0) 滑窗收敛到 RollingWindow。

验证：
  1) RollingWindow：裁剪、tail、mean、空窗口、items 副本语义；
  2) ManasConfig 每个默认值与重构前的字面量逐一相等（这是本次改动的生命线）；
  3) 子引擎与 ManasEngine 确实读 config（改 config 能改变行为）；
  4) 死字段已消失（_trend_history / _trade_density_history / _rolling_pnl_history）。

跑法：
    TMPDIR=$(mktemp -d) python3 scripts/verify/verify_manas_config.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from deva.naja.attention.kernel.manas_config import ManasConfig, RollingWindow  # noqa: E402
from deva.naja.attention.kernel.manas_engine import (  # noqa: E402
    ManasEngine, MetaManas, TimingEngine, RegimeEngine, ConfidenceEngine, RiskEngine,
    ActionType,
)

# 重构前代码里逐字抄下来的字面量（来源：git show HEAD~ 的 manas_engine.py）
OLD = {
    "weight_timing": 0.4,
    "weight_risk": 0.35,
    "weight_confidence": 0.25,
    "risk_temperature_span": 1.5,
    "action_threshold": 0.5,
    "strong_action_threshold": 0.6,
    "resonance_timing_threshold": 0.7,
    "harmony_resistance_temperature": 1.4,
    "harmony_resistance_regime": -0.5,
    "harmony_resonance_temperature": 0.8,
    "harmony_resonance_timing": 0.6,
    "harmony_resonance_regime": 0.2,
    "regime_discount_floor": 0.7,
    "regime_discount_span": 0.3,
    "narrative_risk_threshold": 0.6,
    "narrative_risk_slope": 0.5,
    "ai_compute_strength_threshold": 0.6,
    "ai_compute_bonus_slope": 0.3,
    "resonance_score_threshold": 0.7,
    "resonance_sentiment_threshold": 0.2,
    "resonance_bonus_slope": 0.2,
    "resonance_bonus_cap": 0.10,
    "resonance_penalty_cap": 0.08,
    "alpha_min": 0.3,
    "alpha_max": 1.5,
    "market_deterioration_temperature": 1.3,
    "aggressiveness_window": 10,
    "bias_min_samples": 5,
    "greed_recent_avg": 0.05,
    "greed_overall_avg": 0.03,
    "greed_aggressiveness": 0.6,
    "fear_recent_avg": -0.03,
    "fear_losses": 3,
    "neutral_band": 0.02,
    "correction_greed": 0.7,
    "correction_fear": 0.5,
    "correction_fear_steady": 0.8,
    "pnl_window": 20,
    "volatility_window": 20,
    "hit_rate_window": 10,
    "drawdown_window": 10,
    "volatility_sample": 5,
    "update_interval": 1.0,
}
OLD_AWAKENING = {"enlightened": 1.15, "illuminated": 1.10, "awakening": 1.05}


def check_rolling_window():
    w = RollingWindow(3)
    assert len(w) == 0
    assert w.mean() == 0.0, "空窗口 mean 应为 0.0"

    for i in range(5):
        w.append(float(i))
    assert w.items == [2.0, 3.0, 4.0], w.items          # 0/1 被裁掉
    assert w.tail(2) == [3.0, 4.0], w.tail(2)
    assert abs(w.mean() - 3.0) < 1e-12, w.mean()        # 全窗口均值
    assert abs(w.mean(2) - 3.5) < 1e-12, w.mean(2)      # 近 2 个均值
    assert list(w) == [2.0, 3.0, 4.0]

    # 初始超长输入同样裁剪
    assert RollingWindow(2, [1, 2, 3, 4]).items == [3, 4]

    # items 是副本，改它不影响窗口
    items = w.items
    items.append(99)
    assert len(w) == 3

    try:
        RollingWindow(0)
        raise AssertionError("maxlen<=0 应抛 ValueError")
    except ValueError:
        pass
    print("1) RollingWindow 行为 OK")


def check_defaults():
    cfg = ManasConfig()
    for k, v in OLD.items():
        assert hasattr(cfg, k), f"config 缺少字段 {k}"
        got = getattr(cfg, k)
        assert got == v, f"{k}: 旧 {v} != 新 {got}"
    assert cfg.awakening_factors == OLD_AWAKENING, cfg.awakening_factors
    print(f"2) ManasConfig 默认值的 {len(OLD) + 1} 项与重构前字面量完全一致 OK")


def check_wired():
    """改 config 必须能改变行为，否则就是"搬了个寂寞" """
    # 门槛拉高 → 默认分数（≈0.29）下不再行动
    strict = ManasConfig(action_threshold=0.99, strong_action_threshold=0.995)
    e = ManasEngine(config=strict)
    out = e.compute()
    assert out.manas_score < 0.99
    assert out.action_type == ActionType.HOLD, out.action_type

    # 门槛降到 0 → 同一分数下应当行动
    loose = ManasConfig(action_threshold=0.0)
    out2 = ManasEngine(config=loose).compute()
    assert out2.action_type != ActionType.HOLD, out2.action_type

    # alpha 上限
    e3 = ManasEngine(config=ManasConfig(alpha_max=0.4))
    assert e3.compute().alpha <= 0.4 + 1e-12

    # 窗口长度：pnl_window=3 → 只保留最近 3 笔
    e4 = ManasEngine(config=ManasConfig(pnl_window=3))
    for i in range(5):
        e4.record_pnl(float(i))
    assert e4._recent_pnl.items == [2.0, 3.0, 4.0], e4._recent_pnl.items

    # 观照层暖机长度：bias_min_samples=2 → 2 笔即可判偏差
    meta = MetaManas(config=ManasConfig(bias_min_samples=2, greed_aggressiveness=0.0))
    bias, corr = meta.detect_and_correct([0.5, 0.5], 1.0)
    assert bias.value == "greed", (bias, corr)

    # 子引擎窗口长度
    assert TimingEngine(config=ManasConfig(volatility_window=7))._volatility_history.maxlen == 7
    assert ConfidenceEngine(config=ManasConfig(hit_rate_window=4))._hit_rate_history.maxlen == 4
    assert RiskEngine(config=ManasConfig(drawdown_window=6))._drawdown_history.maxlen == 6
    assert RegimeEngine(config=ManasConfig()).config.update_interval == 1.0

    # 缓存间隔
    assert ManasEngine(config=ManasConfig(update_interval=9.0))._update_interval == 9.0
    print("3) config 已在 ManasEngine / MetaManas / 四个子引擎中生效 OK")


def check_dead_fields():
    for cls, field_name in (
        (TimingEngine, "_trade_density_history"),
        (RegimeEngine, "_trend_history"),
        (ConfidenceEngine, "_rolling_pnl_history"),
    ):
        obj = cls()
        assert not hasattr(obj, field_name), f"{cls.__name__}.{field_name} 仍存在（只写不读的死字段）"
    print("4) 三处只写不读的滑窗字段已删除 OK")


def main():
    check_rolling_window()
    check_defaults()
    check_wired()
    check_dead_fields()
    print("\nALL PASS")


if __name__ == "__main__":
    main()
