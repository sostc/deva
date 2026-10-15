#!/usr/bin/env python3
"""守卫：Manas 行动门必须**点名是哪个因子**卡住了（归因）。

守什么
------
2026-10-15 用户盯着守望台「决策中心怎么说」那一列：

    策略不自信 | 行动:hold | ✗未通过（档位=hold size_hint=0.00 置信度=0.5）

问「这些到底为什么没通过」。核查出两件事：

1. 「策略不自信」判的是 Manas **人和维**（``confidence_score < 0.4``），它算的是
   **策略历史战绩**（ConfidenceEngine ← bandit 战绩库）。而用户下达的是**人的
   意愿**（``intents.json`` 的 ``confidence``）。「我想持有」跟「策略历史胜率低」
   是两件不相干的事 —— 并列成一句理由，人就会**归错因**。
2. 真正卡住的那一刻是**风险温度 1.30 偏高**：地势维贡献 0.046/0.35、缺口 0.305，
   三维里最大。而原理由**一个字都没提它**。也就是：理由里写的那条不是主因，
   主因根本没写出来。

本守卫守四条硬性质
------------------
* **必点主因**：reason 必须出现 ``主因=<缺口最大的那一维>``，且**排在最前**
  —— 守望台那一列按 **46 字符**截断（``ui.py:_watch_rows`` 用 ``_cut(..., 46)``，
  开票流水用 70），放到末尾等于没写。
* **不许张冠李戴**：主因随输入变。环境主导写「地势」、时机主导写「天时」、
  策略维主导写「人和」。**写死一维**（永远「地势」）必须被抓住。
* **环境 / 策略分家**：人和维是**策略历史**，落在理由里必须显式标 ``策略维``，
  不能和「大环境适不适合动手」混成一句话。
* **结构化归因要落下来**：``gate_factors`` 必须随 ``ManasOutput.to_dict()``
  和行动门审计留痕一起走，否则 UI 只能啃那句被截断的字符串。

反方向用例（记忆硬规则：「一项保护会掩盖另一项缺失」）
--------------------------------------------------
只证明「写得出主因」是**假绿**——一句永远返回「主因=地势」的硬编码也能通过。
所以三个场景分别让 天时 / 地势 / 人和 当主因，三条理由必须**互不相同**、
且各写对各的主因；另配自定义权重用例防止把权重写死。

意愿放宽（方案 D）也在这里守
--------------------------
「人的意愿」此前只被写进 ``market_state['signal_confidence']`` 就没人读（权重恒 0）。
现在它可以在**有限**幅度内下调行动门槛，本守卫守住三条硬边界
（低于 min 恒 0 / 不超硬顶 / RESISTANCE 恒 0），外加「必须真能改变判定」
与「必须写进理由且用有效门槛比较」—— 只接线不改判定的假接线必被抓住。

用法
----
    python scripts/verify/verify_manas_attribution.py            # 全量
    python scripts/verify/verify_manas_attribution.py --strict   # CI 用
    python scripts/verify/verify_manas_attribution.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

ENGINE_PY = ROOT / "deva/naja/attention/kernel/manas_engine.py"
AUDIT_PY = ROOT / "deva/naja/attention/kernel/manas_gate_audit.py"
OS_KERNEL_PY = ROOT / "deva/naja/attention/os/os_kernel.py"

#: 意愿放宽的配置。**必须与 ManasConfig 默认值对齐** —— 改了产品默认值要同步这里，
#: 否则守卫会守着一个过时的期望值（这是「守卫腐烂」的常见形态）。
INTENT_LO, INTENT_HI, INTENT_CAP = 0.5, 0.75, 0.15

#: 守望台那一列的实际截断宽度（``ui.py:_watch_rows`` → ``_cut(..., 46)``）。
#: 「主因」必须落在这个宽度内，否则人在页面上看不到。
FRONT_WINDOW = 46

#: 场景：(名字, timing, risk_temperature, confidence, 期望主因 key)
#: 三档分别让 地势 / 天时 / 人和 当主因 —— 写死一维必被其中两条抓住。
SCENARIOS = [
    ("环境主导", 0.90, 1.50, 0.90, "risk"),
    ("天时主导", 0.00, 0.50, 0.95, "timing"),
    ("策略主导", 0.95, 0.50, 0.00, "confidence"),
]

#: 期望主因 key → 理由里该出现的中文标签
LABEL_OF = {"timing": "天时", "risk": "地势", "confidence": "人和"}

DEFAULT_WEIGHTS = {"timing": 0.4, "risk": 0.35, "confidence": 0.25}
RISK_SPAN = 1.5


def _reload_engine():
    """重新导入被测模块（注入 bug 之后必须 reload，否则测的还是旧对象）。"""
    mod = importlib.import_module("deva.naja.attention.kernel.manas_engine")
    return importlib.reload(mod)


def _expected(timing: float, risk_temperature: float, confidence: float,
              weights=None) -> dict:
    """**独立**复算三维贡献/缺口与主因。

    ❗判定基准不许读被测模块 —— 这里用纯算术，跟实现里的公式各写各的。
    """
    w = weights or DEFAULT_WEIGHTS
    safety = 1.0 - min(max(risk_temperature, 0.0), RISK_SPAN) / RISK_SPAN
    vals = {"timing": timing, "risk": safety, "confidence": confidence}
    factors = {}
    for key, value in vals.items():
        contrib = value * w[key]
        factors[key] = {"contrib": round(contrib, 4), "gap": round(w[key] - contrib, 4)}
    dominant = max(factors, key=lambda k: factors[k]["gap"])
    base = sum(vals[k] * w[k] for k in vals)
    return {"factors": factors, "dominant": dominant, "base": base}


def _expected_relax(intent, *, resistance=False,
                    lo=INTENT_LO, hi=INTENT_HI, cap=INTENT_CAP) -> float:
    """**独立**复算意愿放宽量（纯算术，不读被测模块）。"""
    if resistance or intent is None:
        return 0.0
    if intent <= lo:
        return 0.0
    return min(cap, cap * min(1.0, (intent - lo) / (hi - lo)))


def _mk_engine(engine_mod, weights=None):
    cfg = engine_mod.ManasConfig(**weights) if weights else engine_mod.ManasConfig()
    eng = engine_mod.ManasEngine(config=cfg)
    return eng, cfg


def check_factor_math() -> list:
    """三维贡献 / 缺口 / 主因 必须与独立复算一致，且随自定义权重走。"""
    failures = []
    engine_mod = _reload_engine()

    for name, timing, risk_t, conf, expect in SCENARIOS:
        eng, cfg = _mk_engine(engine_mod)
        exp = _expected(timing, risk_t, conf)
        base = exp["base"]
        got = eng._factor_attribution(
            timing=timing, risk_temperature=risk_t, confidence=conf,
            base_score=base, final_score=base, trace=[],
        )
        if got.get("dominant") != expect:
            failures.append(
                f"[{name}] 主因应为 {expect}，实得 {got.get('dominant')}"
            )
        by_key = {f["key"]: f for f in got.get("factors") or []}
        for key, spec in exp["factors"].items():
            g = by_key.get(key)
            if g is None:
                failures.append(f"[{name}] 缺因子 {key}")
                continue
            if abs(g["contrib"] - spec["contrib"]) > 1e-6:
                failures.append(
                    f"[{name}] {key} contrib 应为 {spec['contrib']}，实得 {g['contrib']}"
                )
            if abs(g["gap"] - spec["gap"]) > 1e-6:
                failures.append(
                    f"[{name}] {key} gap 应为 {spec['gap']}，实得 {g['gap']}"
                )

    # 自定义权重：贡献必须跟着 config 走，不许写死 0.4/0.35/0.25
    custom = {"weight_timing": 0.7, "weight_risk": 0.2, "weight_confidence": 0.1}
    eng, _ = _mk_engine(engine_mod, custom)
    # ❗地势维参与打分的是 **safety**（风险温度的反函数），不是温度本身 ——
    #   用例若按温度乘权重，算出来的期望值会错（这条正是先怀疑用例抓到的）。
    safety = 1.0 - min(max(1.0, 0.0), RISK_SPAN) / RISK_SPAN
    vals = {"timing": 0.5, "risk": safety, "confidence": 0.5}
    got = eng._factor_attribution(
        timing=0.5, risk_temperature=1.0, confidence=0.5,
        base_score=0.5, final_score=0.5, trace=[],
    )
    by_key = {f["key"]: f for f in got.get("factors") or []}
    custom_by_key = {k.replace("weight_", ""): v for k, v in custom.items()}
    for key, weight in custom_by_key.items():
        if abs(by_key[key]["weight"] - weight) > 1e-9:
            failures.append(
                f"[自定义权重] {key} 权重应为 {weight}（取自 config），实得 {by_key[key]['weight']}"
            )
        exp_contrib = vals[key] * weight
        if abs(by_key[key]["contrib"] - round(exp_contrib, 4)) > 1e-6:
            failures.append(
                f"[自定义权重] {key} contrib 应为 {round(exp_contrib, 4)}，实得 {by_key[key]['contrib']}"
            )
    return failures


def check_reason_attribution() -> list:
    """理由必须**点名主因且排在前面**；三场景互不相同；策略维必须标记。"""
    failures = []
    engine_mod = _reload_engine()
    seen = {}

    for name, timing, risk_t, conf, expect in SCENARIOS:
        eng, cfg = _mk_engine(engine_mod)
        exp = _expected(timing, risk_t, conf)
        base = exp["base"]
        attrib = eng._factor_attribution(
            timing=timing, risk_temperature=risk_t, confidence=conf,
            base_score=base, final_score=base, trace=[],
        )
        reason = eng._get_gate_reason(
            base, timing, 0.0, conf, engine_mod.BiasState.NEUTRAL,
            engine_mod.HarmonyState.NEUTRAL, engine_mod.ActionType.HOLD,
            attribution=attrib,
        )
        seen[name] = reason

        want = f"主因={LABEL_OF[expect]}"
        if want not in reason:
            failures.append(f"[{name}] 理由没点名主因：应含 {want}，实为 {reason}")
            continue
        pos = reason.index("主因")
        if pos >= FRONT_WINDOW:
            failures.append(
                f"[{name}] 「主因」在第 {pos} 字符，超出守望台 {FRONT_WINDOW} 字符截断窗口"
            )
        if "主因" in reason and reason.index("主因") > reason.index("行动:"):
            failures.append(f"[{name}] 「主因」排在了「行动:」之后：{reason}")
        if "✗未通过" not in reason:
            failures.append(f"[{name}] hold 的理由缺「✗未通过」：{reason}")

    # 三场景理由必须互不相同 —— 否则说明主因没随输入变化
    if len(set(seen.values())) != len(SCENARIOS):
        failures.append(f"三个场景理由应当互不相同，实得 {len(set(seen.values()))} 种")

    # 环境主导时，人和维（策略历史）必须显式标「策略维」——不许跟环境混为一谈
    env_reason = seen.get("环境主导", "")
    if "人和" in env_reason and "策略维" not in env_reason:
        failures.append(
            f"人和（策略历史）未标「策略维」，环境与策略混为一谈：{env_reason}"
        )
    # 用户当初被误导的那句话不许再出现在环境主导的场景里
    if "策略不自信" in env_reason:
        failures.append(f"环境主导时理由里仍出现「策略不自信」：{env_reason}")
    return failures


def check_no_self_contradiction() -> list:
    """绝不写「终分0.585<门槛0.500」这种自相矛盾的话。

    触发条件：分数其实过线，却被**档位**按住（RESISTANCE 直接 hold）。
    这种理由比没有理由更坏 —— 排查的人会当场怀疑这整套数字的可信度。
    """
    failures = []
    engine_mod = _reload_engine()
    eng, cfg = _mk_engine(engine_mod)
    score = cfg.action_threshold + 0.1
    attrib = eng._factor_attribution(
        timing=0.9, risk_temperature=1.5, confidence=0.9,
        base_score=score, final_score=score, trace=[],
    )
    reason = eng._get_gate_reason(
        score, 0.9, 0.0, 0.9, engine_mod.BiasState.NEUTRAL,
        engine_mod.HarmonyState.RESISTANCE, engine_mod.ActionType.HOLD,
        attribution=attrib,
    )
    if f"{score:.3f}<门槛" in reason:
        failures.append(f"理由自相矛盾（终分 {score:.3f} ≥ 门槛却写成「<门槛」）：{reason}")
    if "被档位" not in reason:
        failures.append(f"分数够却被档位按住时，理由未说明是档位按住的：{reason}")
    return failures


def check_discount_reported() -> list:
    """调节链的折/加成必须写进理由（只报结论不报过程 = 归因不完整）。"""
    failures = []
    engine_mod = _reload_engine()
    eng, _ = _mk_engine(engine_mod)
    exp = _expected(0.5, 1.0, 0.5)
    base = exp["base"]
    final = base * 0.85
    attrib = eng._factor_attribution(
        timing=0.5, risk_temperature=1.0, confidence=0.5,
        base_score=base, final_score=final, trace=[("base", base), ("regime", final)],
    )
    reason = eng._get_gate_reason(
        final, 0.5, 0.0, 0.5, engine_mod.BiasState.NEUTRAL,
        engine_mod.HarmonyState.NEUTRAL, engine_mod.ActionType.HOLD,
        attribution=attrib,
    )
    if "折扣0.85" not in reason:
        failures.append(f"调节链折扣未写进理由：{reason}")
    # 加成同样要写（只报坏消息也是失真）
    bonus = eng._factor_attribution(
        timing=0.5, risk_temperature=1.0, confidence=0.5,
        base_score=base, final_score=base * 1.1, trace=[],
    )
    reason_b = eng._get_gate_reason(
        base * 1.1, 0.5, 0.0, 0.5, engine_mod.BiasState.NEUTRAL,
        engine_mod.HarmonyState.NEUTRAL, engine_mod.ActionType.HOLD,
        attribution=bonus,
    )
    if "加成1.10" not in reason_b:
        failures.append(f"调节链加成未写进理由：{reason_b}")
    return failures


def check_output_and_audit_wiring() -> list:
    """gate_factors 必须随 to_dict / 审计留痕一起落下来（结构化，供 UI 用）。"""
    failures = []
    engine_mod = _reload_engine()
    audit_mod = importlib.reload(
        importlib.import_module("deva.naja.attention.kernel.manas_gate_audit")
    )
    eng, _ = _mk_engine(engine_mod)
    out = engine_mod.ManasOutput(
        action_gate_reason="主因=地势(风险温度1.30偏高)",
        gate_factors={"dominant": "risk", "discount": 0.85, "factors": []},
    )
    as_dict = out.to_dict()
    if "gate_factors" not in as_dict:
        failures.append("ManasOutput.to_dict() 丢了 gate_factors（UI 拿不到结构化归因）")
    if "gate_factors" not in engine_mod.MANAS_OUTPUT_GROUPS.get("gate", ()):
        failures.append("MANAS_OUTPUT_GROUPS['gate'] 未登记 gate_factors")
    # 意愿接线的三个字段同样要能落到 UI / 诊断手里
    for key in ("intent_confidence", "intent_relaxation", "effective_threshold"):
        if key not in as_dict:
            failures.append(f"ManasOutput.to_dict() 丢了 {key}（意愿放宽不可见）")
        if key not in engine_mod.MANAS_OUTPUT_GROUPS.get("gate", ()):
            failures.append(f"MANAS_OUTPUT_GROUPS['gate'] 未登记 {key}")

    entry = audit_mod.GateAuditLog._build_entry(out)
    if entry.get("dominant_factor") != "risk":
        failures.append(
            f"行动门审计未留主因（dominant_factor={entry.get('dominant_factor')!r}）"
        )
    if not entry.get("factors") and "factors" not in entry:
        failures.append("行动门审计未留 factors 明细")
    for key in ("intent_confidence", "intent_relaxation", "effective_threshold"):
        if key not in entry:
            failures.append(f"行动门审计未留 {key}（事后无法判断门槛被放宽了多少）")
    if "_build_entry" in ("",):
        pass
    # 构造器不许碰 DB（守卫不得写生产数据）
    log = audit_mod.GateAuditLog(table="naja_verify_attribution_tmp")
    if log._db is not None:
        failures.append("GateAuditLog 构造时就建了 NB 连接（守卫应保持只读）")
    return failures


def check_folded_entry_refreshes_values() -> list:
    """连续同一判定折叠时，数值字段必须刷新到**最新一次**。

    否则区间里环境变了（例如宏观流动性刚接上、regime_score 从 0 变成 0.4），
    审计里却永远停着区间首条的旧值 ——「显示的数不是现在的数」比不显示更误导。
    ts 保留区间起点（首次发生），last_ts 记最近一次。
    """
    failures = []
    engine_mod = _reload_engine()
    audit_mod = importlib.reload(
        importlib.import_module("deva.naja.attention.kernel.manas_gate_audit")
    )
    # 守卫不得写生产库：临时表名 + 把落盘节流推到无穷
    log_ = audit_mod.GateAuditLog(table="naja_verify_fold_tmp", persist_every=10 ** 9)

    def _mk(regime: float, timing: float):
        return engine_mod.ManasOutput(
            action_gate_reason="同一句话 | 行动:hold | ✗未通过",
            action_type=engine_mod.ActionType.HOLD,
            should_act=False,
            regime_score=regime,
            timing_score=timing,
        )

    log_.record(_mk(0.0, 0.10))
    log_.record(_mk(0.4, 0.90))
    if len(log_) != 1:
        failures.append(f"同一判定应当折叠成 1 条，实得 {len(log_)} 条")
        return failures

    e = log_.recent(1)[0]
    if e.get("occurrences") != 2:
        failures.append(f"折叠计数应为 2，实得 {e.get('occurrences')}")
    if abs(float(e.get("regime_score") or 0.0) - 0.4) > 1e-9:
        failures.append(
            f"折叠后 regime_score 应刷新为最新值 0.4，实得 {e.get('regime_score')}"
            "（数值停在区间首条 → 显示的数不是现在的数）"
        )
    if abs(float(e.get("timing_score") or 0.0) - 0.90) > 1e-9:
        failures.append(f"折叠后 timing_score 应刷新为 0.90，实得 {e.get('timing_score')}")
    if not e.get("ts"):
        failures.append("折叠后丢了区间起点 ts（看不出这一段从什么时候开始）")
    return failures


def check_compute_integration() -> list:
    """端到端：用 02:14:59 的真实数字跑 compute()，理由必须点名「地势」。"""
    failures = []
    engine_mod = _reload_engine()
    eng, _ = _mk_engine(engine_mod)
    # 复现那一分钟的三路输入（取自 naja_manas_gate_audit 实测值）
    eng.timing_engine.compute = lambda *a, **k: 0.425
    eng.risk_engine.compute = lambda *a, **k: 1.3049
    eng.confidence_engine.compute = lambda *a, **k: 0.29
    eng.regime_engine.compute = lambda *a, **k: 0.0

    out = eng.compute()
    reason = getattr(out, "action_gate_reason", "")
    factors = getattr(out, "gate_factors", {}) or {}

    if factors.get("dominant") != "risk":
        failures.append(f"实测场景主因应为 risk（地势），实得 {factors.get('dominant')!r}")
    if "主因=地势" not in reason:
        failures.append(f"实测场景理由没写「主因=地势」：{reason}")
    if "策略不自信" in reason:
        failures.append(f"实测场景理由仍在误导人（出现「策略不自信」）：{reason}")
    # 复算终分：base 0.288 × 折扣 0.85 = 0.2448
    try:
        base = float(factors.get("base"))
        disc = float(factors.get("discount"))
        final = float(factors.get("final"))
    except (TypeError, ValueError):
        failures.append(f"gate_factors 数值缺失：{factors!r}")
        return failures
    if abs(base - 0.2880) > 5e-3:
        failures.append(f"base 应为 ≈0.2880，实得 {base}")
    if abs(disc - 0.85) > 5e-3:
        failures.append(f"折扣系数应为 ≈0.85，实得 {disc}")
    if abs(base * disc - final) > 1e-3:
        failures.append(f"base×折扣 应等于 final：{base}×{disc} ≠ {final}")
    if abs(final - 0.2448) > 2e-3:
        failures.append(f"终分应为 ≈0.2448（<门槛 0.5 → hold），实得 {final}")
    if getattr(out, "action_type", None) not in (engine_mod.ActionType.HOLD,):
        failures.append("该场景应当仍是 hold（归因不得改变判定）")
    return failures


def check_intent_relaxation() -> list:
    """人的意愿只许在**有限**幅度内下调门槛，且不得穿透环境硬拦。

    意愿接线（方案 D）的三条硬边界，逐条独立复算：
      ① 低于 intent_relax_min → 恒 0（意愿弱到没表态就不该有杠杆）；
      ② 任意输入（含 99.0 / 负值 / None）→ 不超 intent_relax_max 硬顶；
      ③ RESISTANCE → 恒 0（环境说"不"时，意愿穿透不过去）。
    再验两件事：
      · 放宽必须**真能改变判定**（否则接线是摆设，看着接好了其实没生效）；
      · 放宽必须**写进理由**且用**有效门槛**比较，未放宽时不许凭空出现这句话。
    """
    failures = []
    engine_mod = _reload_engine()
    eng, cfg = _mk_engine(engine_mod)
    neutral = engine_mod.HarmonyState.NEUTRAL
    resist = engine_mod.HarmonyState.RESISTANCE

    # ① / ② 数值与硬顶（独立复算，不读被测模块）
    for intent in (None, -1.0, 0.0, 0.3, 0.5, 0.6, 0.65, 0.75, 0.95, 5.0, 99.0):
        want = _expected_relax(intent)
        got = eng._intent_relaxation(intent, neutral)
        if abs(got - want) > 1e-9:
            failures.append(f"[放宽量] 意愿={intent} 应为 {want}，实得 {got}")
        if got > cfg.intent_relax_max + 1e-9:
            failures.append(f"[硬顶] 意愿={intent} 放宽 {got} 超过硬顶 {cfg.intent_relax_max}")

    # ③ RESISTANCE 恒 0
    for intent in (0.65, 0.75, 1.0, 99.0):
        got = eng._intent_relaxation(intent, resist)
        if got != 0.0:
            failures.append(f"[环境硬拦] RESISTANCE 下意愿={intent} 仍放宽了 {got}（应为 0）")

    # 放宽必须真能改变判定
    score = cfg.action_threshold - cfg.intent_relax_max / 2   # 0.425：原门槛 0.5 下应为 hold
    if eng._determine_action_type(neutral, score, 0.4) != engine_mod.ActionType.HOLD:
        failures.append("[杠杆] 未放宽时该分数本应 hold")
    relaxed = eng._determine_action_type(
        neutral, score, 0.4,
        effective_threshold=cfg.action_threshold - cfg.intent_relax_max,
    )
    if relaxed == engine_mod.ActionType.HOLD:
        failures.append("[杠杆] 意愿拉满也没改变判定 —— 接线没生效")

    # 披露与自洽
    attrib = eng._factor_attribution(
        timing=0.5, risk_temperature=1.0, confidence=0.5,
        base_score=score, final_score=score, trace=[],
    )
    eff = cfg.action_threshold - 0.09
    reason = eng._get_gate_reason(
        score, 0.5, 0.0, 0.5, engine_mod.BiasState.NEUTRAL, neutral,
        engine_mod.ActionType.HOLD, attribution=attrib,
        effective_threshold=eff, intent_relaxation=0.09, intent_confidence=0.65,
    )
    if "意愿0.65放宽门槛" not in reason:
        failures.append(f"[披露] 理由未写出意愿放宽：{reason}")
    if f"{eff:.3f}" not in reason:
        failures.append(f"[自洽] 理由未用有效门槛 {eff:.3f} 比较：{reason}")
    reason2 = eng._get_gate_reason(
        score, 0.5, 0.0, 0.5, engine_mod.BiasState.NEUTRAL, neutral,
        engine_mod.ActionType.HOLD, attribution=attrib,
    )
    if "放宽门槛" in reason2:
        failures.append(f"[噪声] 未放宽却写了「放宽门槛」：{reason2}")

    # 端到端：意愿必须真的走完 compute()（接线里任何一环断了都要被抓到）。
    # 桩值使终分 ≈0.431（regime 折扣 0.85 后）：原门槛 0.5 下 hold，
    # 意愿 0.75 → 门槛 0.35 → 应当放行。
    out_relax = None
    for label, intent, expect_act in (("无意愿", None, False), ("意愿0.75", 0.75, True)):
        e2, _ = _mk_engine(engine_mod)
        e2.timing_engine.compute = lambda *a, **k: 0.6
        e2.risk_engine.compute = lambda *a, **k: 1.0
        e2.confidence_engine.compute = lambda *a, **k: 0.6
        e2.regime_engine.compute = lambda *a, **k: 0.0
        # ❗守卫不得写生产数据：行动门留痕是模块级单例，节流到 50 条会落盘 NB。
        e2._record_gate_audit = lambda output: None
        out = e2.compute(intent_confidence=intent)
        if expect_act and out.action_type == engine_mod.ActionType.HOLD:
            failures.append(f"[端到端/{label}] 意愿应把判定从 hold 抬起来，实得 {out.action_type.value}")
        if not expect_act and out.action_type != engine_mod.ActionType.HOLD:
            failures.append(f"[端到端/{label}] 未给意愿时不应放行，实得 {out.action_type.value}")
        if float(out.intent_relaxation or 0.0) > cfg.intent_relax_max + 1e-9:
            failures.append(f"[端到端/{label}] 放宽量 {out.intent_relaxation} 超硬顶")
        if expect_act:
            out_relax = out
    if out_relax is not None:
        r = out_relax.action_gate_reason or ""
        if "意愿0.75放宽门槛0.500→0.350" not in r:
            failures.append(f"[端到端] 理由未写出意愿放宽门槛：{r}")
    return failures


def check_intent_wiring_static() -> list:
    """静态：意愿要在 compute → 判定 → 输出 → 审计 → 内核调用 全链路上被接住。"""
    failures = []
    tree = ast.parse(ENGINE_PY.read_text(encoding="utf-8"))

    # ① compute() 调 _determine_action_type 必须带 effective_threshold
    wired = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "_determine_action_type":
            if any(kw.arg == "effective_threshold" for kw in node.keywords):
                wired = True
    if not wired:
        failures.append("compute() 调 _determine_action_type 时没传 effective_threshold（意愿没进判定）")

    # ② _intent_relaxation 必须读 config 旋钮，且带 RESISTANCE 护栏
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_intent_relaxation":
            body = ast.unparse(node)
            for needle in ("cfg.intent_relax_min", "cfg.intent_relax_full", "cfg.intent_relax_max"):
                if needle not in body:
                    failures.append(f"_intent_relaxation 未使用 {needle}（硬边界疑似写死）")
            if "RESISTANCE" not in body:
                failures.append("_intent_relaxation 未对 RESISTANCE 设护栏")

    # ③ 内核两处调用都要把意愿喂给 Manas，且必须按 human_intent 区分人与自动信号
    osk = OS_KERNEL_PY.read_text(encoding="utf-8")
    n = osk.count("intent_confidence=self._intent_confidence_from(market_state)")
    if n < 2:
        failures.append(f"os_kernel 只有 {n} 处把意愿传给 Manas（应 2 处）")

    # ❗这里只做 AST 静态检查，**不 import 内核类做行为测试**：注入改写文件之后
    #   模块已在 sys.modules 里，import 拿到的是旧对象 —— 行为测试会测到未注入的
    #   代码而「假通过」（实测踩过：去掉 human_intent 护栏却没被抓到）。
    # ❗扫描前必须**剥掉 docstring**：`_intent_confidence_from` 的说明里也写着
    #   ``human_intent``，不剥的话把护栏删了照样能"命中"字符串 → 假绿。
    osk_tree = ast.parse(osk)
    pick_fn = None
    for node in ast.walk(osk_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_intent_confidence_from":
            pick_fn = node
    if pick_fn is None:
        failures.append("os_kernel 缺 _intent_confidence_from（意愿取值没有单一出处）")
    else:
        stmts = [
            s for s in pick_fn.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        body = "\n".join(ast.unparse(s) for s in stmts)
        if "human_intent" not in body:
            failures.append(
                "_intent_confidence_from 未检查 human_intent"
                "（自动补底仓的信号会被当成「人想买」而放宽门槛）"
            )
    return failures


def static_checks() -> list:
    """静态：归因必须在 compute() 里被真正传进 _get_gate_reason，且权重取自 config。"""
    failures = []
    src = ENGINE_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # ① compute() 调 _get_gate_reason 时必须带 attribution=...
    call_ok = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "_get_gate_reason":
            if any(kw.arg == "attribution" for kw in node.keywords):
                call_ok = True
    if not call_ok:
        failures.append("compute() 调 _get_gate_reason 时没传 attribution（归因没接上）")

    # ② _factor_attribution 的权重必须读 cfg.weight_*，不许写字面量
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_factor_attribution":
            body = ast.unparse(node)
            for needle in ("cfg.weight_timing", "cfg.weight_risk", "cfg.weight_confidence"):
                if needle not in body:
                    failures.append(f"_factor_attribution 未使用 {needle}（权重疑似写死）")
            for literal in ("0.4", "0.35", "0.25"):
                # 权重字面量若出现在 spec 里，说明没走 config
                if f", {literal}, " in body:
                    failures.append(f"_factor_attribution 出现权重字面量 {literal}（应读 config）")
    return failures


INJECTIONS = [
    {
        "name": "主因写死成「地势」（张冠李戴）",
        "file": ENGINE_PY,
        "old": 'dominant = max(factors, key=lambda f: f["gap"])["key"]',
        "new": 'dominant = "risk"',
        "count": -1,
    },
    {
        "name": "主因取反（挑缺口最小的那维）",
        "file": ENGINE_PY,
        "old": 'dominant = max(factors, key=lambda f: f["gap"])["key"]',
        "new": 'dominant = min(factors, key=lambda f: f["gap"])["key"]',
        "count": -1,
    },
    {
        "name": "人和维不做「策略维」标记（环境与策略混为一谈）",
        "file": ENGINE_PY,
        "old": 'tag = "·策略维" if f["domain"] == "strategy" else ""',
        "new": 'tag = ""',
        "count": -1,
    },
    {
        "name": "权重写死（绕过 config）",
        "file": ENGINE_PY,
        "old": '("timing", float(timing), cfg.weight_timing, float(timing)),',
        "new": '("timing", float(timing), 0.4, float(timing)),',
        "count": -1,
    },
    {
        "name": "compute() 不传归因（退回并列旗标）",
        "file": ENGINE_PY,
        # ❗锚点只钉**条件行/单行**，不钉整块尾部 —— 早先钉的是
        #   `attribution=attribution,\n        )`，本次给该调用追加了
        #   effective_threshold 等 kwarg 之后锚点静默失配（打印一句「未命中」就跳过，
        #   看着还是"通过"）。锚点窄化到单行后不再受后续 kwarg 增删影响。
        "old": "            attribution=attribution,\n",
        "new": "            attribution=None,\n",
        "count": -1,
    },
    {
        # ❗这条必须保持**语法合法**：早先写成 `pass,` 会被 SyntaxError 抓住，
        #   看似「捕获」，实则测的不是这条不变量（用例无法区分成败 = 假绿）。
        "name": "gate_factors 不进 to_dict（UI 拿不到结构化归因）",
        "file": ENGINE_PY,
        "old": '            "gate_factors": self.gate_factors,',
        "new": '            "gate_factors_note": "见 action_gate_reason",',
        "count": -1,
    },
    {
        "name": "折叠时不刷新数值（显示的数不是现在的数）",
        "file": AUDIT_PY,
        "old": ("                for key, value in entry.items():\n"
                "                    if key != \"ts\":\n"
                "                        last[key] = value\n"),
        "new": "                pass\n",
    },
    {
        "name": "审计不留主因",
        "file": AUDIT_PY,
        "old": '            "dominant_factor": factors.get("dominant"),',
        "new": '            "dominant_factor": None,',
        "count": -1,
    },
    {
        "name": "分数够却被档位按住时写成「<门槛」（自相矛盾的假话）",
        "file": ENGINE_PY,
        "old": 'f"✗未通过(终分{manas_score:.3f}≥门槛{thr:.3f}，"',
        "new": 'f"✗未通过(终分{manas_score:.3f}<门槛{thr:.3f}，"',
        "count": -1,
    },
    {
        # ❗这条要同时打掉「封顶比 1.0」与「min(cap,…)」两层，否则外层 min 会把
        #   内层失控兜住，注入就抓不到 —— 用例必须能真的区分成败。
        "name": "意愿放宽取消硬顶（门槛被无限下调）",
        "file": ENGINE_PY,
        "old": ("        ratio = min(1.0, (intent - lo) / span)\n"
                "        # 再夹一次硬顶：即使未来有人把上面的公式改坏，放宽量也出不了 cap。\n"
                "        return max(0.0, min(cap, cap * ratio))"),
        "new": "        return max(0.0, cap * (intent - lo) / span)",
        "count": -1,
    },
    {
        "name": "意愿可穿透环境硬拦（RESISTANCE 护栏被去掉）",
        "file": ENGINE_PY,
        "old": ("        if harmony_state == HarmonyState.RESISTANCE:\n"
                "            return 0.0\n"
                "        if intent_confidence is None:"),
        "new": "        if intent_confidence is None:",
        "count": -1,
    },
    {
        "name": "意愿放宽不写进理由（接线了但看不见）",
        "file": ENGINE_PY,
        "old": "        if not intent_relaxation or intent_relaxation <= 1e-6:",
        "new": "        if True:",
        "count": -1,
    },
    {
        "name": "os_kernel 不把意愿喂给 Manas（信号到家门口又放下）",
        "file": OS_KERNEL_PY,
        "old": "            intent_confidence=self._intent_confidence_from(market_state),\n",
        "new": "",
        "count": -1,
    },
    {
        "name": "去掉 human_intent 区分（自动补底仓也被当成「人想买」而放宽）",
        "file": OS_KERNEL_PY,
        "old": '        if not market_state or not market_state.get("human_intent"):',
        "new": "        if not market_state:",
        "count": -1,
    },
]


def run_injections() -> int:
    """逐个把 bug 注进去，确认本守卫抓得到；每次注入后必须 reload 被测模块。

    ❗**锚点未命中一律判失败**，不许「打印一句就跳过」。静默跳过 = 这条注入其实
    没跑，计数却还是满分 —— 守卫腐烂最典型的形态：绿着，但什么都没守。
    """
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path: Path = inj["file"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original:
            # 锚点失配 = 被测代码已被改动，注入没跑 —— 必须显式失败，不是跳过。
            missed.append(inj["name"])
            print(f"❌ 注入锚点未命中（守卫腐烂信号，锚点该修了）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            # ❗注入后必须 reload，否则测的还是内存里的旧对象（记忆硬规则）
            _reload_engine()
            importlib.reload(
                importlib.import_module("deva.naja.attention.kernel.manas_gate_audit")
            )
            found = (
                static_checks()
                + check_factor_math()
                + check_reason_attribution()
                + check_no_self_contradiction()
                + check_discount_reported()
                + check_output_and_audit_wiring()
                + check_folded_entry_refreshes_values()
                + check_compute_integration()
                + check_intent_relaxation()
                + check_intent_wiring_static()
            )
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
            _reload_engine()
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            print(f"       · {found[0][:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（另有 {len(missed)} 条锚点未命中，已计失败）" if missed else ""))
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = (
        static_checks()
        + check_factor_math()
        + check_reason_attribution()
        + check_no_self_contradiction()
        + check_discount_reported()
        + check_output_and_audit_wiring()
        + check_folded_entry_refreshes_values()
        + check_compute_integration()
        + check_intent_relaxation()
        + check_intent_wiring_static()
    )
    if failures:
        print("❌ Manas 归因守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ Manas 归因守卫全绿（主因定位/环境策略分家/结构化留痕/端到端/意愿放宽三边界）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
