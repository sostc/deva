#!/usr/bin/env python3
"""归因分析系统测试脚本

测试归因分析系统的完整功能：
1. 记录模拟交易归因
2. 生成归因报告
3. 验证 UI 数据结构

使用方法：
    python3 test_attribution.py
"""

import sys
import time
from datetime import datetime

sys.path.insert(0, "/Users/spark/pycharmproject/deva")

from deva.naja.bandit.attribution import (
    get_attribution,
    record_trade_attribution,
    StrategyAttribution,
)


def test_record_trade():
    """测试记录交易归因"""
    print("\n" + "=" * 60)
    print("测试 1: 记录交易归因")
    print("=" * 60)

    attr = get_attribution()

    trades = [
        {
            "position_id": "pos_001",
            "strategy_id": "anomaly_sniper",
            "stock_code": "000001",
            "stock_name": "平安银行",
            "entry_price": 10.0,
            "exit_price": 10.8,
            "entry_time": time.time() - 3600 * 5,
            "exit_time": time.time(),
            "holding_seconds": 3600 * 5,
            "close_reason": "TAKE_PROFIT",
            "signal_confidence": 0.85,
            "market_liquidity": 0.75,
            "market_volatility": 0.3,
        },
        {
            "position_id": "pos_002",
            "strategy_id": "momentum_tracker",
            "stock_code": "000002",
            "stock_name": "万科A",
            "entry_price": 8.5,
            "exit_price": 8.2,
            "entry_time": time.time() - 3600 * 2,
            "exit_time": time.time(),
            "holding_seconds": 3600 * 2,
            "close_reason": "STOP_LOSS",
            "signal_confidence": 0.55,
            "market_liquidity": 0.4,
            "market_volatility": 0.6,
        },
        {
            "position_id": "pos_003",
            "strategy_id": "anomaly_sniper",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "entry_price": 1800.0,
            "exit_price": 1850.0,
            "entry_time": time.time() - 3600 * 8,
            "exit_time": time.time(),
            "holding_seconds": 3600 * 8,
            "close_reason": "TAKE_PROFIT",
            "signal_confidence": 0.9,
            "market_liquidity": 0.8,
            "market_volatility": 0.25,
        },
        {
            "position_id": "pos_004",
            "strategy_id": "sector_hunter",
            "stock_code": "600036",
            "stock_name": "招商银行",
            "entry_price": 35.0,
            "exit_price": 34.0,
            "entry_time": time.time() - 3600 * 1,
            "exit_time": time.time(),
            "holding_seconds": 3600 * 1,
            "close_reason": "STOP_LOSS",
            "signal_confidence": 0.35,
            "market_liquidity": 0.2,
            "market_volatility": 0.8,
        },
        {
            "position_id": "pos_005",
            "strategy_id": "momentum_tracker",
            "stock_code": "601318",
            "stock_name": "中国平安",
            "entry_price": 45.0,
            "exit_price": 46.5,
            "entry_time": time.time() - 3600 * 3,
            "exit_time": time.time(),
            "holding_seconds": 3600 * 3,
            "close_reason": "TAKE_PROFIT",
            "signal_confidence": 0.7,
            "market_liquidity": 0.65,
            "market_volatility": 0.4,
        },
    ]

    for trade in trades:
        result = record_trade_attribution(**trade)
        return_pct = (trade["exit_price"] - trade["entry_price"]) / trade["entry_price"] * 100
        print(f"  ✓ 记录交易: {trade['strategy_id']} {trade['stock_name']} "
              f"收益={return_pct:+.2f}% 信心度={trade['signal_confidence']}")

    print(f"\n共记录 {len(trades)} 笔交易")


def test_attribution_report():
    """测试归因报告"""
    print("\n" + "=" * 60)
    print("测试 2: 生成归因报告")
    print("=" * 60)

    attr = get_attribution()
    report = attr.get_full_attribution_report()

    print(f"\n📊 归因摘要:")
    summary = report.get("summary", {})
    print(f"  总策略数: {summary.get('total_strategies', 0)}")
    print(f"  总交易数: {summary.get('total_trades', 0)}")
    print(f"  总收益: {summary.get('total_return', 0):+.2f}%")
    print(f"  盈利策略: {summary.get('winning_strategies', 0)}个")
    print(f"  亏损策略: {summary.get('losing_strategies', 0)}个")

    print(f"\n🏅 策略贡献度排名:")
    contributions = report.get("contributions", [])
    for c in contributions:
        print(f"  #{c['rank']} {c['strategy_id']}: "
              f"总收益={c['total_return']:+.2f}% "
              f"交易数={c['total_trades']} "
              f"胜率={c['win_rate']:.1f}% "
              f"盈亏比={c['profit_loss_ratio']:.2f}")


def test_signal_quality():
    """测试信号质量分析"""
    print("\n" + "=" * 60)
    print("测试 3: 信号质量分析")
    print("=" * 60)

    attr = get_attribution()

    for strategy_id in ["anomaly_sniper", "momentum_tracker"]:
        sq = attr.get_signal_quality_analysis(strategy_id)
        print(f"\n📈 {strategy_id}:")
        print(f"  高信心交易: {sq.high_confidence_trades}笔, "
              f"平均收益: {sq.high_confidence_avg_return:+.2f}%")
        print(f"  中信心交易: {sq.medium_confidence_trades}笔, "
              f"平均收益: {sq.medium_confidence_avg_return:+.2f}%")
        print(f"  低信心交易: {sq.low_confidence_trades}笔, "
              f"平均收益: {sq.low_confidence_avg_return:+.2f}%")
        print(f"  信心-收益相关性: {sq.confidence_return_correlation:.3f}")


def test_market_condition():
    """测试市场条件归因"""
    print("\n" + "=" * 60)
    print("测试 4: 市场条件归因")
    print("=" * 60)

    attr = get_attribution()

    for strategy_id in ["anomaly_sniper", "momentum_tracker"]:
        mc = attr.get_market_condition_attribution(strategy_id)
        print(f"\n🌡️ {strategy_id}:")

        liq_high_avg = mc.liquidity_high_avg
        liq_mid_avg = mc.liquidity_mid_avg
        liq_low_avg = mc.liquidity_low_avg

        print(f"  高流动性环境: {mc.liquidity_high_count}笔交易, "
              f"平均收益: {liq_high_avg:+.2f}%")
        print(f"  中流动性环境: {mc.liquidity_mid_count}笔交易, "
              f"平均收益: {liq_mid_avg:+.2f}%")
        print(f"  低流动性环境: {mc.liquidity_low_count}笔交易, "
              f"平均收益: {liq_low_avg:+.2f}%")

        best_liq = "高流动性" if liq_high_avg >= liq_mid_avg and liq_high_avg >= liq_low_avg else \
            "中流动性" if liq_mid_avg >= liq_low_avg else "低流动性"
        print(f"  → 最佳环境: {best_liq}")


def test_attribution_breakdown():
    """测试收益归因分解"""
    print("\n" + "=" * 60)
    print("测试 5: 收益归因分解")
    print("=" * 60)

    attr = get_attribution()

    for strategy_id in ["anomaly_sniper", "momentum_tracker"]:
        breakdown = attr.get_attribution_breakdown(strategy_id)
        print(f"\n📊 {strategy_id}:")
        print(f"  选股贡献: {breakdown['selection_return']:+.2f}%")
        print(f"  时机贡献: {breakdown['timing_return']:+.2f}%")
        print(f"  仓位管理: {breakdown['position_return']:+.2f}%")
        print(f"  总收益: {breakdown['total_return']:+.2f}%")


def test_trade_history():
    """测试交易历史查询"""
    print("\n" + "=" * 60)
    print("测试 6: 交易历史查询")
    print("=" * 60)

    attr = get_attribution()

    print("\n最近交易历史:")
    history = attr.get_trade_history(limit=5, sort_by="exit_time")
    for h in history:
        entry_time = datetime.fromtimestamp(h["entry_time"]).strftime("%m-%d %H:%M")
        exit_time = datetime.fromtimestamp(h["exit_time"]).strftime("%m-%d %H:%M")
        print(f"  {h['strategy_id']} {h['stock_name']} "
              f"{h['total_return_pct']:+.2f}% "
              f"({entry_time} → {exit_time})")


def main():
    print("\n" + "=" * 60)
    print("🎯 Bandit 归因分析系统测试")
    print("=" * 60)

    test_record_trade()
    test_attribution_report()
    test_signal_quality()
    test_market_condition()
    test_attribution_breakdown()
    test_trade_history()

    print("\n" + "=" * 60)
    print("✅ 所有测试完成!")
    print("=" * 60)
    print("\n💡 提示：")
    print("  - 访问 http://localhost:8080/bandit_attribution 查看归因分析 UI")
    print("  - 或访问 http://localhost:8080/banditadmin 查看 Bandit 管理页面")


if __name__ == "__main__":
    main()
