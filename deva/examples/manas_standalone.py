#!/usr/bin/env python3
"""manas 独立使用示例 —— 把「决策中枢」当通用原语用，不碰交易系统。

跑法::

    cd <项目根>
    /Users/spark/.local/bin/python3 deva/examples/manas_standalone.py

它回答的是「现在该不该动 / 多确信 / 多危险」三个问题。这里的输入是**手搓的**
dict，真实接入时换成你自己的数据源即可（契约见 manas_inputs.ClockView 等）。

想要一个**完整小应用**的骨架（一天的快照时间线 → 决策报告），看
`deva/examples/manas_decision_desk.py`（典型案例）。
"""

from __future__ import annotations

from deva.naja.manas import ManasConfig, create_engine

# 场景 A：顺风——开市中、波动低、持仓舒服、策略近期在赚
FAVORABLE = dict(
    market_status="open",
    remaining_seconds=5400,          # 距收盘 1.5 小时
    market_volatility=0.8,           # 低波动
    ticks={"600000": 1.2, "000001": 0.9, "600519": 0.7},
    us_trading_phase="trading",
    available_capital=70.0,          # 七成现金
    total_capital=100.0,
    total_return=6.0,                # 组合 +6%（百分数口径）
    position_returns=[0.02, 0.03, -0.01, 0.04],
    total_trades=30,
)

# 场景 B：逆风——休市中、波动飙高、仓位吃紧、组合在亏
ADVERSE = dict(
    market_status="closed",
    remaining_seconds=None,
    market_volatility=2.6,           # 高波动
    ticks={"600000": -1.5, "000001": -2.0},
    us_trading_phase="closed",
    available_capital=20.0,          # 只剩两成现金
    total_capital=100.0,
    total_return=-12.0,              # 组合 -12%
    position_returns=[-0.02, -0.03, 0.01],
    total_trades=30,
)


def show(title: str, out) -> None:
    print(f"\n── {title} " + "─" * (46 - len(title)))
    print(f"  综合分 manas_score   : {out.manas_score:.4f}")
    print(f"  行动档位 action_type : {out.action_type.value}")
    print(f"  该不该动 should_act  : {out.should_act}")
    print(f"  置信度 α             : {out.alpha:.4f}")
    print(f"  风险温度 T           : {out.risk_temperature:.3f}")
    gate = getattr(out, "gate_reason", None)
    if gate:
        print(f"  行动门理由           : {gate}")


def main() -> None:
    print("=" * 60)
    print("manas 独立使用示例（无任何交易对象）")
    print("=" * 60)

    # ① 最直接：自己 new 引擎，自己喂输入
    from deva.naja.manas import DictBackedInputs, ManasEngine

    src = DictBackedInputs(**FAVORABLE)
    out = ManasEngine(config=ManasConfig(update_interval=0.0)).compute(
        session_manager=src, scanner=src, portfolio=src, bandit_tracker=src
    )
    show("最直接用法（ManasEngine + DictBackedInputs）", out)

    # ② 便利封装：引擎 + 输入源一起管，改输入就改字段
    session = create_engine(throttle=False, **FAVORABLE)   # throttle=False → 每次立即重算
    show("顺风", session.compute())

    session.update(**ADVERSE)                              # 换一批输入
    show("逆风（同一会话改输入后重算）", session.compute())

    # ③ 按组取输出（给 UI / 日志用，可直接 json.dumps）
    grouped = session.compute().to_grouped_dict()
    print("\n── 分组输出（8 组）" + "─" * 44)
    for name in sorted(grouped):
        print(f"  {name:12s}: {grouped[name]}")

    print("\n提示：compute() 默认缓存 1 秒结果；要每次立即重算，构造时传 throttle=False。")
    print("详细复用指南：docs/naja/manas_reuse_guide.md")


if __name__ == "__main__":
    main()
