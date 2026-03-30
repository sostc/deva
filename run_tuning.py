#!/usr/bin/env python
"""调参模式完整运行脚本"""
import os
import sys
import time
import pandas as pd

os.environ['NAJA_LAB_MODE'] = '1'
os.environ['NAJA_TUNE_MODE'] = '1'

print("=" * 70)
print("调参模式完整运行")
print("=" * 70)

from deva.naja.attention.center import get_orchestrator
from deva.naja.attention.strategies import get_strategy_manager
from deva.naja.bandit.tuner import get_bandit_tuner
from deva.naja.replay import get_replay_scheduler

def get_closed_trades_count(tuner):
    portfolio = tuner._get_portfolio()
    if not portfolio:
        return 0
    count = 0
    for pos in portfolio.get_all_positions():
        if pos.status == "CLOSED" and pos.exit_price > 0:
            count += 1
    return count

def get_open_positions_count(tuner):
    portfolio = tuner._get_portfolio()
    if not portfolio:
        return 0
    count = 0
    for pos in portfolio.get_all_positions():
        if pos.status == "OPEN":
            count += 1
    return count

_initialized = False

# 初始化
print("\n[1] 初始化...")
orch = get_orchestrator()
orch._ensure_initialized()
mgr = get_strategy_manager()
tuner = get_bandit_tuner()
scheduler = get_replay_scheduler()

print("    预热 AttentionKernel...")
sys.stdout.flush()
mock_data = pd.DataFrame({'code': ['000001'], 'now': [10.0], 'price': [10.0]})
orch.process_datasource_data('warmup', mock_data)
print("    AttentionKernel 预热完成")

# 只在第一帧时处理完整数据，之后只更新价格
scheduler._current_interval = 0.05
scheduler._target_interval = 0.05
scheduler.config.max_interval = 0.5
print(f"    调整回放间隔为 0.05 秒/帧（快速回放）")

# 获取所有持仓股票代码
def get_held_stocks():
    portfolio = tuner._get_portfolio()
    if not portfolio:
        return set()
    return {pos.stock_code for pos in portfolio.get_all_positions() if pos.status == "OPEN"}

# 注册回调
import time as time_module
_last_callback_time = time_module.time()
_callback_count = 0
_price_update_call_count = 0
_last_full_process_time = 0
_full_process_interval = 2.0  # 每2秒做一次完整处理
_initialized = False

def wrapped_callback(data):
    global _last_callback_time, _callback_count, _processed_data, _price_update_call_count
    global _last_full_process_time, _initialized

    try:
        now = time_module.time()
        elapsed_since_last = now - _last_callback_time if _last_callback_time > 0 else 0
        _callback_count += 1
        data_rows = len(data) if hasattr(data, '__len__') else 0

        held_stocks = get_held_stocks()
        open_count = len(held_stocks)

        if _callback_count <= 3 or _callback_count % 20 == 0:
            print(f"    [Callback #{_callback_count}] {data_rows}行, 持仓={open_count}个")
            sys.stdout.flush()

        # 只更新持仓股票的价格
        if isinstance(data, pd.DataFrame) and not data.empty and held_stocks:
            price_update_count = 0
            for _, row in data.iterrows():
                stock_code = str(row.get('code', ''))
                if stock_code in held_stocks:
                    current_price = row.get('now', row.get('price', 0))
                    if stock_code and current_price > 0:
                        tuner.on_price_update(stock_code, float(current_price))
                        price_update_count += 1
            if price_update_count > 0 and _callback_count <= 3:
                print(f"    [Callback #{_callback_count}] 更新 {price_update_count} 个持仓股票价格")
                sys.stdout.flush()

        should_full_process = (
            not _initialized or
            now - _last_full_process_time >= _full_process_interval
        )

        if should_full_process:
            _last_full_process_time = now
            if not _initialized:
                _initialized = True
                print(f"    [Callback #{_callback_count}] 首次完整处理...")
                sys.stdout.flush()

            start = time_module.time()
            orch.process_datasource_data('lab_replay', data)
            proc_time = time_module.time() - start

            if _callback_count % 20 == 0:
                closed_count = get_closed_trades_count(tuner)
                open_count = get_open_positions_count(tuner)
                print(f"    [Callback #{_callback_count}] 完整处理完成, 耗时: {proc_time:.1f}s, closed={closed_count}, open={open_count}")
                sys.stdout.flush()
        else:
            if _callback_count <= 3:
                print(f"    [Callback #{_callback_count}] 快速价格更新（距上次完整处理: {now - _last_full_process_time:.1f}s）")
                sys.stdout.flush()

        _last_callback_time = now

    except Exception as e:
        import traceback
        print(f"    [ERROR] 处理数据异常: {e}")
        traceback.print_exc()
        sys.stdout.flush()

# 在 orch 层面添加 price_update 计数
_original_on_price_update = None
def _patched_on_price_update(stock_code, current_price):
    global _price_update_call_count
    _price_update_call_count += 1
    if _price_update_call_count <= 5:
        print(f"    [PriceUpdate #{_price_update_call_count}] {stock_code}@{current_price}")
    return _original_on_price_update(stock_code, current_price)

from deva.naja.bandit.tuner import get_bandit_tuner
tuner = get_bandit_tuner()
_original_on_price_update = tuner.on_price_update
tuner.on_price_update = _patched_on_price_update

scheduler.set_downstream_callback(wrapped_callback)

print(f"    attention_system: ✓")
print(f"    strategy_manager: is_running={mgr.is_running}, strategies={len(mgr.strategies)}")
print(f"    scheduler: {len(scheduler._data_keys)} data keys")
print(f"    tuner: running={tuner._running}")

# 启动
print("\n[2] 启动调度器...")
scheduler.start()
tuner.start()

# 等待数据处理
print("\n[3] 等待数据处理...")
print("    (最多等待 5 分钟或数据回放完成)")
start_time = time.time()
last_closed_count = 0
no_change_count = 0

try:
    while scheduler._running and scheduler._has_more_data:
        time.sleep(2)

        elapsed = int(time.time() - start_time)
        progress = f"{scheduler._key_index}/{len(scheduler._data_keys)}"

        closed_count = get_closed_trades_count(tuner)
        open_count = get_open_positions_count(tuner)

        # 检查进度
        if closed_count != last_closed_count:
            last_closed_count = closed_count
            no_change_count = 0
        else:
            no_change_count += 1

        # 打印状态
        print(f"    [{elapsed:3d}s] {progress:15s} closed={closed_count:4d} open={open_count:3d}  (params: conf={tuner._current_params['min_confidence']:.2f})")

        # 如果 60 秒没有新平仓，且已有持仓，可以提前结束
        if no_change_count >= 30 and open_count > 0 and elapsed > 120:
            print(f"\n    60 个周期无新平仓，已有持仓，继续等待回放完成...")
            # 不退出，继续等待所有帧处理完

        # 超时 5 分钟
        if elapsed >= 300:
            print(f"\n    超时 5 分钟，停止等待")
            break

except KeyboardInterrupt:
    print("\n\n    用户中断")

# 最终统计
print("\n" + "=" * 70)
print("运行结果")
print("=" * 70)

elapsed = int(time.time() - start_time)
print(f"\n运行时间: {elapsed} 秒")
print(f"处理帧数: {orch._processed_frames}")

closed_count = get_closed_trades_count(tuner)
open_count = get_open_positions_count(tuner)
print(f"平仓交易: {closed_count} 个")
print(f"持仓中: {open_count} 个")

print(f"\n当前参数:")
for k, v in tuner._current_params.items():
    print(f"  {k}: {v}")

# Portfolio 统计
portfolio = tuner._get_portfolio()
if portfolio:
    total_pnl = 0
    for pos in portfolio.get_all_positions():
        if pos.status == "CLOSED" and pos.exit_price > 0:
            total_pnl += pos.profit_loss

    print(f"\nPortfolio 统计:")
    print(f"  总资金: {portfolio._total_capital:.2f}")
    print(f"  已用资金: {portfolio._used_capital:.2f}")
    print(f"  累计盈亏: {total_pnl:.2f} ({total_pnl/1000000*100:.2f}%)")

    # 平仓交易明细
    if closed_count > 0:
        winning = [p for p in portfolio.get_all_positions() if p.status == "CLOSED" and p.profit_loss > 0]
        losing = [p for p in portfolio.get_all_positions() if p.status == "CLOSED" and p.profit_loss <= 0]
        print(f"\n  胜率: {len(winning)}/{closed_count} ({len(winning)/closed_count*100:.1f}%)")
        if winning:
            avg_win = sum(p.profit_loss for p in winning) / len(winning)
            print(f"  平均盈利: {avg_win:.2f}")
        if losing:
            avg_loss = abs(sum(p.profit_loss for p in losing) / len(losing))
            print(f"  平均亏损: {avg_loss:.2f}")

# 尝试评估
if closed_count >= 3:
    print(f"\n[评估] 收集到足够交易，开始评估...")
    tuner._evaluate_and_adjust()
    print(f"    评估后参数: {tuner._current_params}")
else:
    print(f"\n[提示] 平仓交易不足 ({closed_count} < 3)，需要放宽参数或等待更多数据")

print("\n" + "=" * 70)
print("运行完成")
print("=" * 70)