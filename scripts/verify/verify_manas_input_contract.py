#!/usr/bin/env python3
"""
校验 ManasEngine 的四类外部输入是否满足契约。

================================================================================
它解决什么问题
================================================================================

manas_engine.py 的所有取数都是「鸭子类型 + try/except 兜底」。当传入的对象
缺少某个方法时，异常被吞掉并返回一个默认值——于是「接口接错了」和「数据恰好
等于默认值」看起来一模一样。本脚本把这种静默失效显式化。

契约定义见 deva/naja/attention/kernel/manas_inputs.py（含静默回退对照表）。

================================================================================
被检查的真实对象 & 它们实际出现在哪条调用路径上
================================================================================

    ClockView
      ├─ MarketSessionManager   ← 契约的正确实现
      └─ TradingClock           ← os_kernel 实际传的 session_manager
    MarketView
      └─ GlobalMarketScanner
    PortfolioView
      └─ VirtualPortfolio
    StrategyView
      └─ BanditPositionTracker

运行路径现状（本次校验暴露的核心问题）：
    os_kernel.py 的 OSAttentionKernel 自建 `ManasEngine()`（无依赖注入），
    process() 调用时传 portfolio=None / bandit_tracker=None，
    session_manager 传的是 TradingClock（不是 MarketSessionManager），
    而 scanner 上不存在 get_market_volatility()。
    → 内核打分路径上，T、confidence、时间压力、波动率四路输入全部退化为常数。

================================================================================
用法
================================================================================

    python3 -m scripts.verify.verify_manas_input_contract            # 报告模式（默认，恒 0）
    python3 -m scripts.verify.verify_manas_input_contract --strict   # 违约时退出码 1

报告模式默认不失败，是因为当前已知存在 4 处违约（属于待修复状态，
见 docs/naja/manas_upgrade_plan.md 的 P1）。修复完成后应改用 --strict 接入检查。
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


# (契约名, 类所在模块, 类名, 角色说明)
TARGETS = [
    ("ClockView", "deva.naja.radar.global_market_config", "MarketSessionManager",
     "契约的正确实现（期望全绿）"),
    ("ClockView", "deva.naja.radar.trading_clock", "TradingClock",
     "os_kernel 实际传入的 session_manager"),
    ("MarketView", "deva.naja.radar.global_market_scanner", "GlobalMarketScanner",
     "内核与 manager 共用的市场数据源"),
    ("PortfolioView", "deva.naja.bandit.virtual_portfolio", "VirtualPortfolio",
     "理想持仓数据源"),
    ("StrategyView", "deva.naja.bandit.tracker", "BanditPositionTracker",
     "理想策略表现数据源"),
]

# 契约方法 → 缺失时的后果，用于输出结论
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


def main() -> int:
    parser = argparse.ArgumentParser(description="ManasEngine 输入契约校验")
    parser.add_argument("--strict", action="store_true",
                        help="存在违约时返回退出码 1")
    args = parser.parse_args()

    print("=" * 78)
    print("ManasEngine 输入契约校验")
    print("=" * 78)

    violations = []   # (契约, 类名, 缺失方法)
    import_errors = []

    for contract_name, module_path, class_name, role in TARGETS:
        cls, error = _load_class(module_path, class_name)
        if error is not None:
            import_errors.append((class_name, error))
            print("\n[IMPORT FAILED] {}  ({})".format(class_name, module_path))
            print("    {}".format(error))
            continue

        missing = check_contract(cls, contract_name)
        ok = not missing
        mark = "OK  " if ok else "FAIL"
        print("\n[{}] {}  ↔  {}".format(mark, contract_name, class_name))
        print("    {}".format(role))
        if not ok:
            violations.append((contract_name, class_name, missing))
            for method in missing:
                key = "{}.{}".format(contract_name, method)
                print("    ✗ {:<42} {}".format(
                    method, CONSEQUENCES.get(key, "后果未登记")))
        else:
            print("    所有必需方法齐备")

    print("\n" + "=" * 78)
    print("结论")
    print("=" * 78)

    if not violations and not import_errors:
        print("✓ 全部契约满足。可将本脚本以 --strict 接入检查。")
        return 0

    if import_errors:
        print("! {} 个类导入失败（环境问题，非契约问题）：".format(len(import_errors)))
        for class_name, error in import_errors:
            print("    {} — {}".format(class_name, error))

    if violations:
        print("发现 {} 处契约违约：\n".format(len(violations)))
        for contract_name, class_name, missing in violations:
            print("  • {} 缺少 {}".format(class_name, "、".join(missing)))
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
