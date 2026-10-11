#!/usr/bin/env python3
"""
校验 ManasEngine 的四类外部输入是否满足契约，并验证真实装配是否正确。

================================================================================
它解决什么问题
================================================================================

manas_engine.py 的所有取数都是「鸭子类型 + try/except 兜底」。当传入的对象
缺少某个方法时，异常被吞掉并返回一个默认值——于是「接口接错了」和「数据恰好
等于默认值」看起来一模一样。本脚本把这种静默失效显式化。

契约定义见 deva/naja/attention/kernel/manas_inputs.py（含静默回退对照表）。

================================================================================
三段检查
================================================================================

  ① 类级契约 —— 这些类的实例会出现在运行路径上，必须满足契约（静态）
  ② 装配检查 —— 实例化 OSAttentionKernel，注入真实依赖，检查
                get_manas_inputs() 实际吐出来的四路对象是否满足契约（动态）。
                这一段才是真正能抓到「接错线」的检查：类级检查只能证明
                「这个类有能力满足契约」，不能证明「它真的被传进去了」。
  ③ 行为差异 —— 同一场景下，「旧接线」（四路输入退化）与「新接线」（真实输入）
                的输出对比，用于确认修复方向正确（α 不再被压在下限）。

================================================================================
用法
================================================================================

    python3 -m scripts.verify.verify_manas_input_contract            # 报告模式
    python3 -m scripts.verify.verify_manas_input_contract --strict   # 违约退出码 1
"""

import argparse
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from deva.naja.attention.kernel.manas_inputs import (  # noqa: E402
    INPUT_CONTRACTS,
    check_contract,
)


# 必须满足契约的 (契约名, 模块, 类名, 角色说明)
REQUIRED_TARGETS = [
    ("ClockView", "deva.naja.radar.global_market_config", "MarketSessionManager",
     "契约的正确实现；内核经 scanner.session_manager 取到它"),
    ("MarketView", "deva.naja.radar.global_market_scanner", "GlobalMarketScanner",
     "内核与 manager 共用的市场数据源"),
    ("PortfolioView", "deva.naja.bandit.virtual_portfolio", "VirtualPortfolio",
     "由 container 注入内核的持仓数据源"),
    ("StrategyView", "deva.naja.bandit.tracker", "BanditPositionTracker",
     "由 container 注入内核的策略表现数据源"),
]

# 保留在仓库里、但**不再**作为该角色传入的类：只作说明，不计违约。
INFORMATIONAL_TARGETS = [
    ("ClockView", "deva.naja.radar.trading_clock", "TradingClock",
     "历史上被当作 session_manager 传入（缺陷来源）。已有 MarketSessionManager "
     "顶替，故不再要求它满足 ClockView；其 cn_phase / us_phase 语义另有用途，"
     "**不要**给它补 get_market_status —— 那会把时段语义混进 clock。"),
]

# 契约方法 → 缺失时的后果
CONSEQUENCES = {
    "ClockView.get_market_status": "TimingEngine 时间压力维恒 0.5",
    "ClockView.get_session_remaining_seconds": "TimingEngine 时间压力维恒 0.5",
    "MarketView.get_market_volatility": "Timing 波动率维恒 0.5；RiskEngine 波动率恒 1.0（保守/激进度判据永不触发）",
    "MarketView.get_last_data": "成交密度、指数趋势、题材扩散全部恒 0",
    "MarketView.get_market_summary": "结构断裂恒 0.5；RegimeEngine 自适应权重失效",
    "MarketView.get_liquidity_adjustment": "退化为 macro_signal * 2 - 1",
    "PortfolioView.get_summary": "cash_ratio 恒 0.5、drawdown 恒 0 → 风险温度 T 恒 1.25",
    "StrategyView.get_position_history": "hit_rate 恒 0.5、rolling_pnl 恒 0",
    "StrategyView.get_strategy_summary": "bandit_conf 恒 0.5 → confidence 恒 0.35",
}

# 四路输入 → 契约名
INPUT_ROLES = {
    "session_manager": "ClockView",
    "scanner": "MarketView",
    "portfolio": "PortfolioView",
    "bandit_tracker": "StrategyView",
}


def _load_class(module_path: str, class_name: str):
    """返回 (cls, error)。导入失败时 cls 为 None。"""
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # noqa: BLE001 - 导入失败要如实上报，不掩盖
        return None, "{}: {}".format(type(exc).__name__, exc)
    cls = getattr(module, class_name, None)
    if cls is None:
        return None, "模块内找不到类 {}".format(class_name)
    return cls, None


def _section(title: str):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def check_static_contracts(violations, import_errors):
    """① 类级契约检查"""
    _section("① 类级契约检查（静态）")

    for contract_name, module_path, class_name, role in REQUIRED_TARGETS:
        cls, error = _load_class(module_path, class_name)
        if error is not None:
            import_errors.append((class_name, error))
            print("\n[IMPORT FAILED] {}  ({})".format(class_name, module_path))
            print("    {}".format(error))
            continue

        missing = check_contract(cls, contract_name)
        ok = not missing
        print("\n[{}] {}  ↔  {}".format("OK  " if ok else "FAIL", contract_name, class_name))
        print("    {}".format(role))
        if ok:
            print("    所有必需方法齐备")
            continue
        violations.append((contract_name, class_name, missing))
        for method in missing:
            key = "{}.{}".format(contract_name, method)
            print("    ✗ {:<42} {}".format(method, CONSEQUENCES.get(key, "后果未登记")))

    if INFORMATIONAL_TARGETS:
        print("\n—— 以下类不再承担该角色，仅作说明（不计违约）——")
        for contract_name, module_path, class_name, note in INFORMATIONAL_TARGETS:
            cls, error = _load_class(module_path, class_name)
            if error is not None:
                print("  · {} ({})：导入失败 {}".format(class_name, contract_name, error))
                continue
            missing = check_contract(cls, contract_name)
            print("  · {} ↔ {}：缺 {}".format(
                class_name, contract_name, "、".join(missing) if missing else "无"))
            print("      {}".format(note))


def check_runtime_wiring(violations):
    """② 装配检查：真正检查内核吐出来的四路对象"""
    _section("② 装配检查（动态：内核 get_manas_inputs() 实际返回值）")

    try:
        from deva.naja.attention.os.os_kernel import OSAttentionKernel
        from deva.naja.bandit.virtual_portfolio import VirtualPortfolio
        from deva.naja.bandit.tracker import BanditPositionTracker
    except Exception as exc:  # noqa: BLE001
        print("  跳过：依赖导入失败 {}: {}".format(type(exc).__name__, exc))
        return

    kernel = OSAttentionKernel()

    # 模拟 container._create_manas_manager() 的装配动作
    kernel.set_manas_dependencies(
        portfolio=VirtualPortfolio(),
        bandit_tracker=BanditPositionTracker(),
    )

    inputs = kernel.get_manas_inputs()
    print()
    for key, contract_name in INPUT_ROLES.items():
        obj = inputs.get(key)
        if obj is None:
            print("[FAIL] {:<16} ↔ {:<14} 实际传入 None（该维度会整体退化）".format(key, contract_name))
            violations.append((contract_name, "内核装配({})".format(key), ["<None>"]))
            continue
        missing = check_contract(obj, contract_name)
        ok = not missing
        print("[{}] {:<16} ↔ {:<14} {}".format(
            "OK  " if ok else "FAIL", key, contract_name, type(obj).__name__))
        if not ok:
            violations.append((contract_name, "内核装配({})".format(key), missing))
            for method in missing:
                key2 = "{}.{}".format(contract_name, method)
                print("    ✗ {:<42} {}".format(method, CONSEQUENCES.get(key2, "后果未登记")))

    # 形状检查：光有方法还不够。VirtualPortfolio 的实例满足 PortfolioView
    # （有 get_summary），但它返回的字典曾经缺 total_capital —— cash_ratio 的
    # 分母因此兜底成 1，比值退化成「可用资金的数值本身」，T 撞下限 0.5。
    # 类级契约检查看不见这一层，必须在装配检查里验证返回形状。
    portfolio = inputs.get("portfolio")
    if portfolio is not None:
        print()
        try:
            summary = portfolio.get_summary()
        except Exception as exc:  # noqa: BLE001
            print("[FAIL] portfolio.get_summary() 抛异常: {}: {}".format(type(exc).__name__, exc))
            violations.append(("PortfolioView.get_summary", "内核装配(portfolio)", ["<raise>"]))
        else:
            required = ("available_capital", "total_capital", "total_return")
            missing_keys = [k for k in required if k not in summary]
            if missing_keys:
                print("[FAIL] portfolio.get_summary() 缺键：{}".format("、".join(missing_keys)))
                print("    ✗ cash_ratio 的分母缺失 → RiskEngine 的 T 会撞下限")
                violations.append(("PortfolioView.get_summary", "内核装配(portfolio)", missing_keys))
            else:
                avail = summary.get("available_capital", 0) or 0
                total = summary.get("total_capital", 0) or 0
                ratio = (avail / total) if total else None
                print("[OK  ] portfolio.get_summary() 形状完整")
                print("    available_capital={:.2f} total_capital={:.2f} "
                      "total_return={:.4f}(%) → cash_ratio={}".format(
                          avail, total, summary.get("total_return", 0),
                          "{:.4f}".format(ratio) if ratio is not None else "N/A"))
                if ratio is not None and not (0.0 <= ratio <= 1.0):
                    print("    ✗ cash_ratio 越界（应落在 [0,1]）")
                    violations.append((
                        "PortfolioView.get_summary", "内核装配(portfolio)", ["cash_ratio 越界"]))


def _behaviour_delta():
    """③ 行为差异：旧接线（常数）vs 新接线（真实输入）"""
    _section("③ 行为差异（同一场景：旧接线 vs 新接线）")

    from deva.naja.attention.kernel.manas_engine import ManasEngine
    from deva.naja.attention.kernel.manas_inputs import DictBackedInputs

    # 场景 A：危险 + 弱策略 —— 高风险本就该低 α，α 撞下限是「正确行为」
    hostile = DictBackedInputs(
        market_status="open", remaining_seconds=7200,      # A 股盘中，距收盘 2h
        market_volatility=1.8,                             # >1.5 → Risk 保守档
        ticks={"600000": 1.2, "000001": -0.4, "000002": 0.9},
        us_trading_phase="trading",
        available_capital=30.0, total_capital=100.0,       # cash_ratio 0.3
        total_return=-6.0,                                 # 回撤 6% → 1.1×（百分数口径）
        position_returns=[0.02, -0.01, 0.03, 0.01],        # 3胜1负
        total_trades=12,
    )

    # 场景 B：顺风 + 强策略 —— α 必须能离开下限，否则说明它被系统性钉死
    favourable = DictBackedInputs(
        market_status="open", remaining_seconds=7200,
        market_volatility=0.6,                             # 低波动
        ticks={"600000": 1.5, "000001": 1.1, "000002": 0.8},
        us_trading_phase="trading",
        available_capital=80.0, total_capital=100.0,       # cash_ratio 0.8
        total_return=-1.0,                                 # 回撤 1%，不触发加档（百分数口径）
        position_returns=[0.03, 0.02, 0.04, 0.01, 0.02],   # 全胜
        total_trades=30,
    )

    def _run(use_inputs: bool, src):
        e = ManasEngine()
        if use_inputs:
            e.set_portfolio(src)
            e.set_bandit_tracker(src)
        out = None
        # 波动率维需要 volatility_sample(=5) 次历史才生效，先热身
        for _ in range(6):
            e._last_output = None
            e._last_update = 0.0
            kwargs = (dict(session_manager=src, scanner=src,
                           portfolio=src, bandit_tracker=src)
                      if use_inputs else {})
            out = e.compute(**kwargs)
        return out

    for label, src in (("场景 A｜危险 + 弱策略", hostile),
                       ("场景 B｜顺风 + 强策略", favourable)):
        old = _run(False, src)
        new = _run(True, src)
        print("\n  {}".format(label))
        print("  {:<18} {:>10} {:>10}   {}".format("字段", "旧接线", "新接线", "变化"))
        print("  " + "-" * 62)
        for name in ("timing_score", "risk_temperature", "confidence_score",
                     "manas_score", "alpha"):
            ov, nv = getattr(old, name), getattr(new, name)
            flag = "← 复活" if abs(ov - nv) > 1e-9 else "（无变化）"
            print("  {:<18} {:>10.4f} {:>10.4f}   {}".format(name, ov, nv, flag))

    print("\n  判读：旧接线四路输入全退化（portfolio=None / tracker=None /")
    print("  无 session_manager / scanner 无 get_market_volatility），")
    print("  因此 T 恒 1.25、confidence 恒 0.35、时间压力恒 0.5。")
    print("  场景 A 的 α 仍撞下限是正确的（高风险本就该压 α）；")
    print("  关键是场景 B 的 α 必须离开下限——否则只是换了个常数。")


def main() -> int:
    parser = argparse.ArgumentParser(description="ManasEngine 输入契约校验 + 装配检查")
    parser.add_argument("--strict", action="store_true",
                        help="存在违约时返回退出码 1")
    args = parser.parse_args()

    print("=" * 78)
    print("ManasEngine 输入契约校验")
    print("=" * 78)

    violations = []   # (契约, 对象名, 缺失方法)
    import_errors = []

    check_static_contracts(violations, import_errors)
    check_runtime_wiring(violations)
    try:
        _behaviour_delta()
    except Exception as exc:  # noqa: BLE001
        print("\n  行为差异段跳过：{}: {}".format(type(exc).__name__, exc))

    _section("结论")

    if not violations and not import_errors:
        print("✓ 全部契约满足，且内核装配吐出的四路对象均合规。")
        print("  可将本脚本以 --strict 接入检查。")
        return 0

    if import_errors:
        print("! {} 个类导入失败（环境问题，非契约问题）：".format(len(import_errors)))
        for class_name, error in import_errors:
            print("    {} — {}".format(class_name, error))

    if violations:
        print("发现 {} 处契约违约：\n".format(len(violations)))
        for contract_name, obj_name, missing in violations:
            print("  • {} ↔ {} 缺少 {}".format(obj_name, contract_name, "、".join(missing)))
        print("\n这些缺失不会抛错，只会让对应维度静默退化为常数——"
              "即「看起来在算，其实一半输入是常量」。")
        print("修复方案见 docs/naja/manas_upgrade_plan.md 的 P1。")

    if args.strict and violations:
        print("\n[strict] 存在违约，退出码 1")
        return 1

    print("\n[report] 报告模式，退出码 0（加 --strict 可在 CI 中断言）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
