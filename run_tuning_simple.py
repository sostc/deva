#!/usr/bin/env python
"""调参模式 - 简化版，使用动量信号 + 回放结束强制平仓"""
import os
import sys
import time
import pandas as pd

os.environ['NAJA_LAB_MODE'] = '1'
os.environ['NAJA_TUNE_MODE'] = '1'

print("=" * 70)
print("调参模式 - 动量信号 + 回放结束强制平仓")
print("=" * 70)

from deva.naja.bandit.tuner import get_bandit_tuner
from deva.naja.replay import get_replay_scheduler

def get_closed_trades_count(tuner):
    portfolio = tuner._get_portfolio()
    if not portfolio:
        return 0
    return sum(1 for pos in portfolio.get_all_positions()
               if pos.status == "CLOSED" and pos.exit_price > 0)

def get_open_positions_count(tuner):
    portfolio = tuner._get_portfolio()
    if not portfolio:
        return 0
    return sum(1 for pos in portfolio.get_all_positions() if pos.status == "OPEN")

def get_total_pnl(tuner):
    portfolio = tuner._get_portfolio()
    if not portfolio:
        return 0
    return sum(p.profit_loss for p in portfolio.get_all_positions()
              if p.status == "CLOSED" and p.exit_price > 0)

def force_close_all(tuner, reason="FORCE_CLOSE"):
    """强制平仓所有持仓"""
    portfolio = tuner._get_portfolio()
    if not portfolio:
        return
    positions = portfolio.get_all_positions(status="OPEN")
    for pos in positions:
        exit_price = pos.current_price if pos.current_price > 0 else pos.entry_price
        portfolio.close_position(pos.position_id, exit_price, reason)
        print(f"    强制平仓: {pos.stock_code} @ {exit_price:.2f}, P&L={pos.profit_loss:.2f}")

print("\n[1] 初始化...")
tuner = get_bandit_tuner()
scheduler = get_replay_scheduler()

# 清空旧持仓
portfolio = tuner._get_portfolio()
if portfolio:
    old_positions = portfolio.get_all_positions(status="OPEN")
    if old_positions:
        print(f"    清空 {len(old_positions)} 个旧持仓...")
        for pos in old_positions:
            portfolio.close_position(pos.position_id, pos.current_price, "RESET")

    old_closed = portfolio.get_all_positions(status="CLOSED")
    if old_closed:
        print(f"    清空 {len(old_closed)} 个旧平仓记录...")
        for pos in old_closed:
            portfolio._positions.pop(pos.position_id, None)

# 重置调参状态
tuner._data_replay_finished = False
tuner._round = 0
tuner._total_rounds = 3
tuner._current_params = {
    'min_confidence': 0.35,
    'stop_loss_pct': -5.0,
    'take_profit_pct': 15.0,
    'position_size_pct': 20.0,
}
print(f"    参数: {tuner._current_params}")

scheduler._current_interval = 0.05
scheduler._target_interval = 0.05
scheduler.config.max_interval = 0.5
print(f"    回放间隔: 0.05 秒/帧")

_callback_count = 0
_signals_generated = 0

def wrapped_callback(data):
    global _callback_count, _signals_generated

    try:
        _callback_count += 1

        if not isinstance(data, pd.DataFrame) or data.empty:
            return

        held_stocks = {pos.stock_code: pos for pos in tuner._get_portfolio().get_all_positions()
                      if pos.status == "OPEN"}

        for _, row in data.iterrows():
            stock_code = str(row.get('code', ''))
            if stock_code in held_stocks:
                current_price = row.get('now', row.get('price', 0))
                if current_price > 0:
                    tuner.on_price_update(stock_code, float(current_price))

        if len(held_stocks) < 5:
            min_confidence = tuner._current_params['min_confidence']

            for _, row in data.iterrows():
                stock_code = str(row.get('code', ''))
                if not stock_code or stock_code in held_stocks:
                    continue

                p_change = row.get('p_change', 0)
                now = row.get('now', 0)

                if abs(p_change) >= 0.02 and now > 0:
                    confidence = min(1.0, abs(p_change) * 10)

                    if confidence >= min_confidence:
                        from deva.naja.strategy.result_store import StrategyResult
                        result = StrategyResult(
                            id=f"momentum_{stock_code}_{int(time.time()*1000)}",
                            strategy_id="MomentumTuner",
                            strategy_name="MomentumTuner",
                            ts=time.time(),
                            success=True,
                            input_preview=f"{stock_code}: p_change={p_change:.2%}",
                            output_preview=f"置信度: {confidence:.2f}",
                            output_full={
                                'signal_type': 'BUY',
                                'stock_code': stock_code,
                                'price': float(now),
                                'confidence': confidence,
                                'p_change': float(p_change),
                            },
                            process_time_ms=0,
                            error="",
                            metadata={'source': 'tuning_momentum'}
                        )

                        tuner.on_signal(result)
                        _signals_generated += 1
                        held_stocks[stock_code] = None

                        if len(held_stocks) >= 5:
                            break

        if _callback_count % 20 == 0:
            closed = get_closed_trades_count(tuner)
            open_pos = get_open_positions_count(tuner)
            total_pnl = get_total_pnl(tuner)
            progress = f"{scheduler._key_index}/{len(scheduler._data_keys)}"
            print(f"    [{_callback_count:4d}帧 {progress}] 持仓={open_pos}, 平仓={closed}, P&L={total_pnl:.0f}, 信号={_signals_generated}")
            sys.stdout.flush()

    except Exception as e:
        import traceback
        print(f"    [ERROR] 回调异常: {e}")
        traceback.print_exc()
        sys.stdout.flush()

print("\n[2] 启动...")
scheduler.set_downstream_callback(wrapped_callback)
scheduler.start()
tuner.start()

print("\n[3] 运行中...")

try:
    while scheduler._running and scheduler._has_more_data:
        time.sleep(1)

        elapsed = int(time.time() - time.time())
        closed = get_closed_trades_count(tuner)
        open_pos = get_open_positions_count(tuner)
        total_pnl = get_total_pnl(tuner)

        if scheduler._key_index >= len(scheduler._data_keys) - 1:
            print(f"\n    数据回放接近结束，强制平仓...")
            force_close_all(tuner, "END_OF_REPLAY")
            break

except KeyboardInterrupt:
    print("\n\n    用户中断，强制平仓...")
    force_close_all(tuner, "USER_INTERRUPT")

print("\n" + "=" * 70)
print("运行结果")
print("=" * 70)

portfolio = tuner._get_portfolio()
if portfolio:
    closed_trades = [p for p in portfolio.get_all_positions()
                    if p.status == "CLOSED" and p.exit_price > 0]
    total_pnl = sum(p.profit_loss for p in closed_trades)

    print(f"\n总交易次数: {len(closed_trades)}")
    print(f"总盈亏: {total_pnl:.2f} ({total_pnl/1000000*100:.2f}%)")
    print(f"参数: {tuner._current_params}")

    if closed_trades:
        winning = [p for p in closed_trades if p.profit_loss > 0]
        losing = [p for p in closed_trades if p.profit_loss <= 0]
        print(f"胜率: {len(winning)}/{len(closed_trades)} ({len(winning)/len(closed_trades)*100:.1f}%)")
        if winning:
            print(f"平均盈利: {sum(p.profit_loss for p in winning)/len(winning):.2f}")
        if losing:
            print(f"平均亏损: {abs(sum(p.profit_loss for p in losing)/len(losing)):.2f}")

        print(f"\n平仓明细:")
        for p in closed_trades[:10]:
            print(f"  {p.stock_code}: 入={p.entry_price:.2f} 出={p.exit_price:.2f} P&L={p.profit_loss:.2f} ({p.return_pct:.2f}%) {p.close_reason}")

print("\n" + "=" * 70)