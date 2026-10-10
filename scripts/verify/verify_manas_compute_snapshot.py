#!/usr/bin/env python3
"""
manas compute() 输出快照

用途：重构 `ManasEngine.compute()` 前后各跑一次，逐字段比对，证明行为等价。

    # 重构前：存基线
    python scripts/verify/verify_manas_compute_snapshot.py --save baseline.json

    # 重构后：比对
    python scripts/verify/verify_manas_compute_snapshot.py --check baseline.json

覆盖 compute() 里每一条调节分支（regime / narrative_risk / ai_compute /
resonance 正反 / awakening 三档 / bias 贪惧），并额外覆盖「多分支同时命中」
的组合场景——组合场景最容易暴露「中间 clamp 位置被挪动」这类等价性破坏。
"""
import argparse
import json
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from deva.naja.attention.kernel.manas_engine import ManasEngine, BiasState  # noqa: E402


def _greed(e):
    """贪偏差：稳态返回 0.7"""
    for _ in range(6):
        e.record_pnl(0.10)
    e.meta_manas.bias_state = BiasState.GREED


def _fear(e):
    """惧偏差：稳态返回 0.8"""
    for _ in range(6):
        e.record_pnl(-0.05)
    e.meta_manas.bias_state = BiasState.FEAR


def _awakening(level):
    def _set(e):
        e._get_awakening_level = lambda: level
    return _set


def _multi(*fns):
    def _set(e):
        for f in fns:
            f(e)
    return _set


def _narrative_high(e):
    e._supply_chain_state["narrative_risk"] = 0.85


def _ai_up(e):
    e._supply_chain_state["ai_compute_trend"] = "up"
    e._supply_chain_state["ai_compute_strength"] = 0.9


def _ai_down(e):
    e._supply_chain_state["ai_compute_trend"] = "down"
    e._supply_chain_state["ai_compute_strength"] = 0.9


def _resonance_pos(e):
    e._supply_chain_state["resonance_score"] = 0.9
    e._supply_chain_state["resonance_sentiment"] = 0.5


def _resonance_neg(e):
    e._supply_chain_state["resonance_score"] = 0.9
    e._supply_chain_state["resonance_sentiment"] = -0.5


def _watchlist(e):
    e._supply_chain_state["watchlist_bonus"] = 1.3


SCENARIOS = [
    ("default", lambda e: None),
    ("narrative_high", _narrative_high),
    ("ai_up", _ai_up),
    ("ai_down", _ai_down),
    ("resonance_pos", _resonance_pos),
    ("resonance_neg", _resonance_neg),
    ("awaken_enlightened", _awakening("enlightened")),
    ("awaken_illuminated", _awakening("illuminated")),
    ("awaken_awakening", _awakening("awakening")),
    ("bias_greed", _greed),
    ("bias_fear", _fear),
    ("watchlist_bonus", _watchlist),
    # 组合场景：中间 clamp 一旦挪位就会在这里露馅
    ("combo_all_positive", _multi(_ai_up, _resonance_pos, _awakening("enlightened"))),
    ("combo_all_negative", _multi(_narrative_high, _resonance_neg, _fear)),
    ("combo_greed_positive", _multi(_ai_up, _resonance_pos, _greed)),
]


def run_snapshot():
    """跑完所有场景，返回 {场景名: ManasOutput 字典}"""
    snap = {}
    for name, setup in SCENARIOS:
        e = ManasEngine()
        setup(e)
        # compute() 有 _update_interval 缓存，强制重算
        e._last_output = None
        e._last_update = 0.0
        out = e.compute()
        snap[name] = out.to_dict()
    return snap


def _flat(d, prefix=""):
    """摊平成 {路径: 值}，便于逐字段比对"""
    items = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            items.update(_flat(v, key + "."))
        elif isinstance(v, (list, tuple)):
            items[key] = json.dumps(v, ensure_ascii=False, sort_keys=True)
        else:
            items[key] = v
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", help="把快照写入文件")
    ap.add_argument("--check", help="与基线文件比对")
    ap.add_argument("--show", action="store_true", help="打印快照")
    args = ap.parse_args()

    snap = run_snapshot()

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2, default=str, sort_keys=True)
        print(f"已保存 {len(snap)} 个场景 -> {args.save}")

    if args.show:
        print(json.dumps(snap, ensure_ascii=False, indent=2, default=str, sort_keys=True))

    if args.check:
        with open(args.check, encoding="utf-8") as f:
            baseline = json.load(f)
        diffs = 0
        for name in sorted(set(baseline) | set(snap)):
            if name not in baseline:
                print(f"[新增场景] {name}")
                continue
            if name not in snap:
                print(f"[缺失场景] {name}")
                diffs += 1
                continue
            b, c = _flat(baseline[name]), _flat(snap[name])
            for k in sorted(set(b) | set(c)):
                if k not in b:
                    print(f"  {name}.{k}: 新增 = {c[k]}")
                    continue
                if k not in c:
                    print(f"  {name}.{k}: 缺失（基线 {b[k]}）")
                    diffs += 1
                    continue
                if isinstance(b[k], float) and isinstance(c[k], float):
                    same = abs(b[k] - c[k]) < 1e-9
                else:
                    same = str(b[k]) == str(c[k])
                if not same:
                    print(f"  {name}.{k}: 基线 {b[k]} -> 现在 {c[k]}")
                    diffs += 1
        print(f"\n比对场景数 {len(snap)}，差异字段 {diffs}")
        return 1 if diffs else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
