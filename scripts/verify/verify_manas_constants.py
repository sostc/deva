#!/usr/bin/env python3
"""回归：manas_engine._update_supply_chain_state 的常量提升。

改动：
  - risk_scores / ai_keywords 由每次事件重建 → 模块级常量；
  - ai_keywords 预先 lower，避免每事件每关键词重复 .lower()；
  - 删除函数内冗余的局部 `import time`。

验证：
  1) 模块级常量内容与原先字面量一致；
  2) 新/旧 ai 关键词命中计数在所有样例上一致；
  3) _update_supply_chain_state 仍能正常更新状态。

跑法（必须清环境）：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_manas_constants.py
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

M = importlib.import_module("deva.naja.attention.kernel.manas_engine")

_OLD_AI_KEYWORDS = ["AI", "算力", "芯片", "GPU", "数据中心", "大模型", "模型训练",
                    "H100", "B100", "GB200", "Blackwell", "算力需求", "AI服务器"]
_OLD_RISK_SCORES = {"HIGH": 0.8, "MEDIUM": 0.5, "LOW": 0.2}


def old_hits(narratives):
    lower = [n.lower() for n in narratives]
    return sum(1 for kw in _OLD_AI_KEYWORDS if any(kw.lower() in n for n in lower))


def new_hits(narratives):
    lower = [n.lower() for n in narratives]
    return sum(1 for kw in M._AI_COMPUTE_KEYWORDS_LOWER if any(kw in n for n in lower))


class Ev:
    def __init__(self, risk_level="LOW", importance=0.5, narratives=None,
                 stock_codes=None, event_type=None):
        self.risk_level = risk_level
        self.importance = importance
        self.narratives = narratives or []
        self.stock_codes = stock_codes or []
        self.event_type = event_type


def main():
    # 1) 常量内容一致
    assert M._RISK_LEVEL_SCORES == _OLD_RISK_SCORES, M._RISK_LEVEL_SCORES
    assert set(M._AI_COMPUTE_KEYWORDS_LOWER) == {k.lower() for k in _OLD_AI_KEYWORDS}
    assert all(k == k.lower() for k in M._AI_COMPUTE_KEYWORDS_LOWER)
    print("1) 模块级常量内容一致 OK")

    # 2) 命中计数一致（覆盖多种组合）
    samples = [
        [],
        ["普通新闻", "无关叙事"],
        ["AI算力需求爆发", "GPU供不应求", "数据中心扩张"],
        ["ai", "gpu", "h100", "gb200", "blackwell"],
        ["芯片涨价", "大模型训练需求", "AI服务器出货"],
        ["混合 Mixed Case AI 与 算力需求"],
    ]
    for s in samples:
        o, n = old_hits(s), new_hits(s)
        assert o == n, (s, o, n)
    print(f"2) {len(samples)} 组样例命中计数一致 OK")

    # 3) 状态更新仍正常
    eng = M.ManasEngine.__new__(M.ManasEngine)  # 跳过 __init__（避免重副作用）
    eng._supply_chain_state = {}
    ev = Ev(risk_level="HIGH", importance=0.9,
            narratives=["AI算力需求爆发", "GPU供不应求", "数据中心扩张"],
            stock_codes=["NVDA"])
    eng._update_supply_chain_state(ev)
    st = eng._supply_chain_state
    assert st["risk_level"] == "HIGH", st["risk_level"]
    assert st["ai_compute_trend"] == "up", st["ai_compute_trend"]   # 3+ 命中 → up
    assert st["ai_compute_strength"] > 0.5, st["ai_compute_strength"]
    assert st["narrative_risk"] > 0.5, st["narrative_risk"]
    print(f"3) 状态更新 OK risk={st['narrative_risk']:.3f} trend={st['ai_compute_trend']}")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
