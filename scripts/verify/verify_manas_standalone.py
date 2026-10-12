#!/usr/bin/env python3
"""验证 manas 可以**脱离交易系统单独使用**（独立可用性）。

为什么需要这个脚本
------------------
「ManasEngine 能裸构造」这件事，单测已经证明（`TestObjectFreeReuse`）。但那只覆盖
**运行期**：喂 dict 能出分数。真正决定「别的应用能不能单独用它」的还有一层
——**加载期**：

    别处的应用 `import` 它时，会不会被迫把整个交易 / 认知域（TradingCenter /
    AttentionOS / orchestration）一起拉起来？

改造前实测：`import deva.naja.attention.kernel.manas_engine` = 3.4s / 3158 模块，
其中 10 个是交易域模块——而 ManasEngine 本体只依赖 stdlib。这叫「能力能复用，
但没人愿意为它付这个加载成本」。

本脚本用**子进程**验证改造结果（子进程才算数：本进程可能早就 import 过重模块）。

跑法
----
    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_manas_standalone.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_manas_standalone.py --strict

退出码：0 = PASS；--strict 下有违约则 1。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 子进程用同一份环境，但不带宿主注入的 PYTHONPATH（shim 会干扰导入计时/副作用）
_CHILD_ENV = dict(os.environ)
_CHILD_ENV.pop("PYTHONPATH", None)

# 交易域模块特征：命中任一即算「被拖进来了」
_TRADING_MARKERS = ("trading_center", "orchestration", "attention.os", "bandit")

# 子进程要跑的东西：全新进程里只 import 门面，报告代价与「是否拖入交易域」
_CHILD_SNIPPET = r"""
import sys, time
sys.path.insert(0, {root!r})

t0 = time.time()
from deva.naja.manas import create_engine, ManasEngine, DictBackedInputs  # noqa
elapsed = time.time() - t0

markers = {markers!r}
trading = sorted(m for m in sys.modules if any(x in m for x in markers))
print("MANAS_STANDALONE_JSON", __import__("json").dumps({{
    "elapsed": elapsed,
    "trading_modules": trading,
    "total_modules": len(sys.modules),
    "numpy_loaded": "numpy" in sys.modules,
}}))
"""


def _probe_child() -> tuple[bool, dict | None, str]:
    """在全新进程里 import 门面，拿回代价指标。"""
    snippet = _CHILD_SNIPPET.format(root=str(PROJECT_ROOT), markers=_TRADING_MARKERS)
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        env=_CHILD_ENV,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in (proc.stdout or "").splitlines():
        if line.startswith("MANAS_STANDALONE_JSON "):
            import json

            return proc.returncode == 0, json.loads(line.split(" ", 1)[1]), out.strip()
    return False, None, out.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}" + (f"  —— {detail}" if detail else ""))
        if not ok:
            violations.append(name)

    # ── ① 全新进程里 import 门面的代价 ────────────────────────────────────
    print("=" * 68)
    print("① 子进程只 import `deva.naja.manas`——加载期是否还被交易域拖累？")
    print("=" * 68)
    ok, data, raw = _probe_child()
    check("子进程导入成功", ok and data is not None, "" if ok else raw[-400:])
    if not (ok and data):
        print("\n❌ 子进程未能完成导入，后续检查跳过")
        return 1 if args.strict else 0

    trading = data["trading_modules"]
    check(
        "未拖入任何交易域模块（trading_center / orchestration / attention.os / bandit）",
        trading == [],
        f"命中 {len(trading)} 个: {trading[:5]}",
    )
    check(
        "模块总数远低于改造前（3158）",
        data["total_modules"] < 2000,
        f"total={data['total_modules']}",
    )
    check(
        "导入耗时可接受（< 3.0s，改造前 3.4s）",
        data["elapsed"] < 3.0,
        f"elapsed={data['elapsed']:.3f}s",
    )
    print(f"  ℹ️  numpy_loaded={data['numpy_loaded']}（`deva` 命名空间自带，非 kernel 拖入）")

    # ── ② 门面等价性：re-export 不得造第二份实现 ──────────────────────────
    print()
    print("=" * 68)
    print("② 门面是**同一份实现**的 re-export，不是副本")
    print("=" * 68)
    from deva.naja import manas as facade
    from deva.naja.attention.kernel import manas_config, manas_engine, manas_inputs

    check(
        "ManasEngine 是同一个对象",
        facade.ManasEngine is manas_engine.ManasEngine,
        f"{facade.ManasEngine!r}",
    )
    check(
        "ManasConfig 是同一个对象",
        facade.ManasConfig is manas_config.ManasConfig,
        "",
    )
    check(
        "DictBackedInputs 是同一个对象",
        facade.DictBackedInputs is manas_inputs.DictBackedInputs,
        "",
    )
    check(
        "四契约 Protocol 是同一个对象",
        (facade.ClockView, facade.MarketView, facade.PortfolioView, facade.StrategyView)
        == (
            manas_inputs.ClockView,
            manas_inputs.MarketView,
            manas_inputs.PortfolioView,
            manas_inputs.StrategyView,
        ),
        "",
    )

    # ── ③ __all__ 里每个名字都真能取到（防「导出了但取不到」）────────────
    print()
    print("=" * 68)
    print("③ 门面 __all__ 中的每个名字都能取到")
    print("=" * 68)
    missing = [name for name in facade.__all__ if not hasattr(facade, name)]
    check("无缺失名字", missing == [], f"missing={missing}")

    # ── ④ 端到端：两个不同场景必须给出不同分数（防退化成常数）────────────
    print()
    print("=" * 68)
    print("④ 端到端：顺风 / 逆风两个场景，分数必须不同")
    print("=" * 68)
    favorable = facade.create_engine(
        throttle=False,
        market_status="open", remaining_seconds=5400, market_volatility=0.8,
        ticks={"600000": 1.2, "000001": 0.9, "600519": 0.7}, us_trading_phase="trading",
        available_capital=70.0, total_capital=100.0, total_return=6.0,
        position_returns=[0.02, 0.03, -0.01, 0.04], total_trades=30,
    )
    adverse = facade.create_engine(
        throttle=False,
        market_status="closed", remaining_seconds=None, market_volatility=2.6,
        ticks={"600000": -1.5, "000001": -2.0}, us_trading_phase="closed",
        available_capital=20.0, total_capital=100.0, total_return=-12.0,
        position_returns=[-0.02, -0.03, 0.01], total_trades=30,
    )
    out_fav = favorable.compute()
    out_adv = adverse.compute()
    print(
        f"  ℹ️  顺风: manas_score={out_fav.manas_score:.4f} T={out_fav.risk_temperature:.3f} "
        f"action={out_fav.action_type.value}"
    )
    print(
        f"  ℹ️  逆风: manas_score={out_adv.manas_score:.4f} T={out_adv.risk_temperature:.3f} "
        f"action={out_adv.action_type.value}"
    )
    check("两个场景 manas_score 不同", abs(out_fav.manas_score - out_adv.manas_score) > 1e-6, "")
    check(
        "逆风风险温度更高（T 是「温度」，越高越谨慎）",
        out_adv.risk_temperature > out_fav.risk_temperature,
        f"{out_adv.risk_temperature:.3f} vs {out_fav.risk_temperature:.3f}",
    )
    check("action_type 是人话档位（hold / act_*）",
          out_fav.action_type.value in ("hold", "act_minimally", "act_carefully", "act_fully"),
          out_fav.action_type.value)

    # ── ⑤ 静态守卫：包入口必须是惰性的，别回退成 eager ──────────────────
    print()
    print("=" * 68)
    print("⑤ 静态守卫：包入口保持 PEP 562 惰性（防回退）")
    print("=" * 68)
    for rel in ("deva/naja/attention/__init__.py", "deva/naja/attention/kernel/__init__.py"):
        src = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        check(f"{rel} 定义了 __getattr__（PEP 562）", "def __getattr__" in src, "")
        check(f"{rel} 定义了 _LAZY_EXPORTS", "_LAZY_EXPORTS" in src, "")

    att_src = (PROJECT_ROOT / "deva/naja/attention/__init__.py").read_text(encoding="utf-8")
    for bad in ("from .os import", "from .orchestration import", "from .portfolio import"):
        check(f"attention/__init__.py 不再 eager 导入 {bad!r}", bad not in att_src, "")

    # ── ⑥ 语义保持：旧用法（直接取交易域名字）仍要能取到 ────────────────
    print()
    print("=" * 68)
    print("⑥ 惰性导出未破坏旧用法（老代码照旧能取到重名字）")
    print("=" * 68)
    from deva.naja.attention import AttentionEvent, TradingCenter, get_attention_os  # noqa

    check("from deva.naja.attention import TradingCenter 仍可用",
          TradingCenter.__name__ == "TradingCenter", "")
    check("AttentionEvent 可用", AttentionEvent is not None, "")
    check("get_attention_os 是函数", callable(get_attention_os), "")

    import deva.naja.attention as att

    try:
        att.DefinitelyNotAThing  # noqa: B018
        check("未知名字抛 AttributeError（不静默）", False, "竟然没抛")
    except AttributeError:
        check("未知名字抛 AttributeError（不静默）", True, "")

    # ── 汇总 ─────────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)} 项:")
        for v in violations:
            print(f"   · {v}")
        return 1 if args.strict else 0
    print("✅ 全部通过：manas 已可脱离交易系统单独导入使用（加载期 0 交易域依赖）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
