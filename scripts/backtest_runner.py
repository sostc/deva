#!/usr/bin/env python3
"""实验模式回测脚本

启动回测流程：
1. 清空现有持仓和归因数据
2. 启动 ReplayScheduler 回放历史数据
3. 监控信号和交易
4. 生成归因报告
"""

import sys
import time
import asyncio
import logging
from datetime import datetime

sys.path.insert(0, "/Users/spark/pycharmproject/deva")

log = logging.getLogger("backtest")

from deva.naja.bandit import get_virtual_portfolio, get_attribution
from deva.naja.replay import get_replay_scheduler
from deva.naja.strategy import get_strategy_manager


def clear_data():
    """清空现有数据"""
    print("\n" + "=" * 60)
    print("清空现有数据")
    print("=" * 60)

    # 清空持仓
    vp = get_virtual_portfolio()
    try:
        count = vp.clear_history()
        print(f"✓ 清空持仓: {count} 条")
    except Exception as e:
        print(f"清空持仓失败: {e}")

    # 清空归因数据
    from deva import NB
    attr_db = NB("naja_bandit_attribution")
    try:
        keys = list(attr_db.keys())
        for k in keys:
            del attr_db[k]
        print(f"✓ 清空归因数据: {len(keys)} 条")
    except Exception as e:
        print(f"清空归因数据失败: {e}")


def check_signal_flow():
    """检查信号流"""
    print("\n" + "=" * 60)
    print("检查信号流")
    print("=" * 60)

    # 检查 AttentionOrchestrator
    try:
        from deva.naja.attention.center import get_attention_orchestrator
        ao = get_attention_orchestrator()
        print(f"✓ AttentionOrchestrator: {ao.__class__.__name__}")

        # 检查策略
        strategies = ao.strategy_manager.list_strategies()
        print(f"  策略数量: {len(strategies)}")
        for s in strategies[:3]:
            print(f"    - {s.get('name', s.get('strategy_id', 'unknown'))}")
    except Exception as e:
        print(f"✗ AttentionOrchestrator: {e}")

    # 检查 SignalListener
    try:
        from deva.naja.bandit import get_signal_listener
        sl = get_signal_listener()
        print(f"✓ SignalListener: 已连接")
    except Exception as e:
        print(f"✗ SignalListener: {e}")

    # 检查 VirtualPortfolio
    vp = get_virtual_portfolio()
    positions = vp.get_all_positions()
    print(f"✓ VirtualPortfolio: {len(positions)} 个持仓")


def start_replay():
    """启动回放"""
    print("\n" + "=" * 60)
    print("启动历史数据回放")
    print("=" * 60)

    # 设置实验模式环境变量
    import os
    os.environ['NAJA_LAB_MODE'] = '1'

    # 设置回放数据回调，同时发送数据到 Attention
    from deva.naja.replay import get_replay_scheduler
    from deva.naja.attention.center import get_orchestrator

    scheduler = get_replay_scheduler()
    orchestrator = get_orchestrator()
    orchestrator._ensure_initialized()  # 确保初始化

    def on_replay_data(data):
        """回放数据回调：同时发送到 Attention"""
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame) and not data.empty:
                orchestrator.process_datasource_data("replay", data)
                log.info(f"[回放回调] 发送 {len(data)} 条数据到 Attention")
        except Exception as e:
            log.warning(f"[回放回调] 发送失败: {e}")

    scheduler.set_downstream_callback(on_replay_data)
    print("✓ 已注册回放回调（同时发送数据到 Attention）")

    # 启动 MarketObserver（更新价格触发止盈止损）
    from deva.naja.bandit import get_market_observer
    observer = get_market_observer()
    observer.start()
    print("✓ MarketObserver 已启动（更新持仓价格）")

    # 检查数据表
    table_name = "quant_snapshot_5min_window"
    from deva import NB
    db = NB(table_name)
    keys = list(db.keys())
    print(f"数据表 {table_name}: {len(keys)} 条")

    # 启动 ReplayScheduler
    print("\n启动回放...")
    try:
        scheduler.start()
        print(f"✓ ReplayScheduler 已启动")
    except Exception as e:
        print(f"启动回放失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 启动 BanditRunner
    try:
        from deva.naja.bandit import ensure_bandit_auto_runner
        runner = ensure_bandit_auto_runner()
        print(f"✓ BanditRunner 已启动")
    except Exception as e:
        print(f"启动 BanditRunner 失败: {e}")

    return True


def monitor_and_report():
    """监控并生成报告"""
    print("\n" + "=" * 60)
    print("监控状态")
    print("=" * 60)

    vp = get_virtual_portfolio()
    attr = get_attribution()

    for i in range(5):
        positions = vp.get_all_positions()
        open_count = len([p for p in positions if p.status == "OPEN"])
        closed_count = len([p for p in positions if p.status == "CLOSED"])

        print(f"[{i+1}/5] 持仓: {open_count} 开仓, {closed_count} 平仓")

        if i < 4:
            time.sleep(3)

    # 生成归因报告
    print("\n" + "=" * 60)
    print("归因报告")
    print("=" * 60)

    report = attr.get_full_attribution_report()
    summary = report.get("summary", {})

    print(f"\n总交易数: {summary.get('total_trades', 0)}")
    print(f"总收益: {summary.get('total_return', 0):+.2f}%")
    print(f"盈利策略: {summary.get('winning_strategies', 0)}")
    print(f"亏损策略: {summary.get('losing_strategies', 0)}")

    contributions = report.get("contributions", [])
    if contributions:
        print("\n策略排名:")
        for c in contributions[:5]:
            print(f"  #{c['rank']} {c['strategy_id']}: {c['total_return']:+.2f}% "
                  f"(胜率={c['win_rate']:.1f}%)")


def main():
    global vp, attr

    print("\n" + "=" * 60)
    print("🧪 NAJA 实验模式回测")
    print("=" * 60)

    clear_data()
    check_signal_flow()

    print("\n启动回放...")
    if not start_replay():
        print("回放启动失败，退出")
        return

    # 获取全局实例用于监控
    vp = get_virtual_portfolio()
    attr = get_attribution()

    print("\n监控 60 秒...")
    for i in range(12):
        positions = vp.get_all_positions()
        open_count = len([p for p in positions if p.status == "OPEN"])
        closed_count = len([p for p in positions if p.status == "CLOSED"])

        attr = get_attribution()
        report = attr.get_full_attribution_report()
        summary = report.get("summary", {})

        print(f"[{i+1}/12] 持仓: {open_count} 开仓, {closed_count} 平仓 | "
              f"总收益: {summary.get('total_return', 0):+.2f}%")

        time.sleep(5)

    # 生成归因报告
    print("\n" + "=" * 60)
    print("📊 最终归因报告")
    print("=" * 60)

    report = attr.get_full_attribution_report()
    summary = report.get("summary", {})

    print(f"\n总交易数: {summary.get('total_trades', 0)}")
    print(f"总收益: {summary.get('total_return', 0):+.2f}%")
    print(f"盈利策略: {summary.get('winning_strategies', 0)}")
    print(f"亏损策略: {summary.get('losing_strategies', 0)}")

    contributions = report.get("contributions", [])
    if contributions:
        print("\n策略排名:")
        for c in contributions:
            print(f"  #{c['rank']} {c['strategy_id']}: {c['total_return']:+.2f}% "
                  f"(胜率={c['win_rate']:.1f}%, 交易数={c['total_trades']})")


if __name__ == "__main__":
    main()
