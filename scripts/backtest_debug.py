#!/usr/bin/env python3
"""实验模式回测脚本 - 带详细日志"""

import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, "/Users/spark/pycharmproject/deva")

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger("backtest")

from deva.naja.bandit import get_virtual_portfolio, get_attribution, get_signal_listener, get_adaptive_cycle
from deva.naja.replay import get_replay_scheduler
from deva.naja.attention.center import get_orchestrator
from deva.naja.register import SR


def clear_data():
    """清空现有数据"""
    print("\n" + "=" * 60)
    print("清空现有数据")
    print("=" * 60)

    vp = SR('virtual_portfolio')
    try:
        count = vp.clear_history()
        print(f"✓ 清空持仓: {count} 条")
    except Exception as e:
        print(f"清空持仓失败: {e}")

    from deva import NB
    attr_db = NB("naja_bandit_attribution")
    try:
        keys = list(attr_db.keys())
        for k in keys:
            del attr_db[k]
        print(f"✓ 清空归因数据: {len(keys)} 条")
    except Exception as e:
        print(f"清空归因数据失败: {e}")


def start_replay():
    """启动回放"""
    print("\n" + "=" * 60)
    print("启动历史数据回放")
    print("=" * 60)

    import os
    os.environ['NAJA_LAB_MODE'] = '1'

    scheduler = get_replay_scheduler()
    orchestrator = get_orchestrator()
    orchestrator._ensure_initialized()

    def on_replay_data(data):
        """回放数据回调"""
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame) and not data.empty:
                orchestrator.process_datasource_data("replay", data)
                print(f"[回调] 发送 {len(data)} 条数据到 Attention")
        except Exception as e:
            print(f"[回调] 发送失败: {e}")

    scheduler.set_downstream_callback(on_replay_data)
    print("✓ 已注册回放回调")

    from deva.naja.bandit import get_market_observer
    observer = get_market_observer()
    observer.start()
    print("✓ MarketObserver 已启动")

    # 启动 SignalListener
    listener = get_signal_listener()
    listener._force_mode = True  # 强制模式，忽略交易阶段
    listener.start()
    print(f"✓ SignalListener 已启动 (强制模式, 轮询间隔: {listener._poll_interval}s)")

    # 启动 AdaptiveCycle
    cycle = get_adaptive_cycle()
    print(f"✓ AdaptiveCycle 已启动 (自动调整: {cycle._auto_adjust_enabled})")

    # 检查数据表
    from deva import NB
    db = NB("quant_snapshot_5min_window")
    keys = list(db.keys())
    print(f"数据表: {len(keys)} 条")

    print("\n启动回放...")
    scheduler.start()
    print(f"✓ ReplayScheduler 已启动")


def main():
    print("\n" + "=" * 60)
    print("🧪 NAJA 实验模式回测 (详细日志)")
    print("=" * 60)

    clear_data()

    start_replay()

    from deva.naja.signal.stream import get_signal_stream

    print("\n" + "=" * 60)
    print("监控 120 秒...")
    print("=" * 60)

    vp = SR('virtual_portfolio')
    listener = get_signal_listener()

    last_signal_check = 0
    last_position_check = 0

    for i in range(24):  # 2分钟
        now = time.time()

        # 每5秒检查一次信号
        if now - last_signal_check > 5:
            signal_stream = get_signal_stream()
            recent = signal_stream.get_recent(limit=10) if signal_stream else []
            print(f"[{i+1}/24] 信号队列: {len(recent)} 个")
            last_signal_check = now

        # 每10秒检查一次持仓
        if now - last_position_check > 10:
            positions = vp.get_all_positions()
            open_count = len([p for p in positions if p.status == "OPEN"])
            closed_count = len([p for p in positions if p.status == "CLOSED"])

            attr = get_attribution()
            report = attr.get_full_attribution_report()
            summary = report.get("summary", {})

            if open_count > 0 or closed_count > 0:
                print(f"[{i+1}/24] 持仓: {open_count} 开仓, {closed_count} 平仓 | "
                      f"总收益: {summary.get('total_return', 0):+.2f}%")
            last_position_check = now

        time.sleep(5)

    # 最终报告
    print("\n" + "=" * 60)
    print("📊 最终归因报告")
    print("=" * 60)

    attr = get_attribution()
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
