#!/usr/bin/env python3
"""Bandit 模块测试脚本

测试 bandit 模块的完整工作流程：
1. 信号流是否正常工作
2. SignalListener 能否正确解析信号
3. 虚拟持仓能否正确创建和管理
4. Bandit 优化器能否正确更新收益
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("Bandit 模块测试")
print("=" * 60)

print("\n[1] 测试导入模块...")
try:
    from deva.naja.bandit import (
        get_signal_listener,
        get_virtual_portfolio,
        get_market_observer,
        get_bandit_optimizer,
        get_adaptive_cycle,
        get_bandit_tracker,
        SignalListener,
        VirtualPortfolio,
        BanditOptimizer,
    )
    print("   ✅ 所有模块导入成功")
except Exception as e:
    print(f"   ❌ 模块导入失败: {e}")
    sys.exit(1)

print("\n[2] 测试信号流获取...")
try:
    from deva.naja.signal.stream import get_signal_stream
    signal_stream = get_signal_stream()
    recent_signals = signal_stream.get_recent(limit=5)
    print(f"   ✅ 信号流正常工作，当前缓存 {len(signal_stream.cache)} 条")
    if recent_signals:
        print(f"   📊 最近信号数量: {len(recent_signals)}")
        for i, sig in enumerate(recent_signals[:3]):
            print(f"      [{i+1}] {sig.strategy_name}: {sig.output_preview[:50]}...")
    else:
        print("   📊 暂无历史信号")
except Exception as e:
    print(f"   ❌ 信号流获取失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[3] 测试 SignalListener 初始化...")
try:
    listener = get_signal_listener()
    status = listener.get_status()
    print(f"   ✅ SignalListener 初始化成功")
    print(f"      - 运行状态: {status['running']}")
    print(f"      - 轮询间隔: {status['poll_interval']}s")
    print(f"      - 最小置信度: {status['min_confidence']}")
    print(f"      - 已处理信号数: {status['processed_count']}")
except Exception as e:
    print(f"   ❌ SignalListener 初始化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[4] 测试虚拟持仓初始化...")
try:
    portfolio = get_virtual_portfolio()
    summary = portfolio.get_summary()
    print(f"   ✅ VirtualPortfolio 初始化成功")
    print(f"      - 总资金: ¥{summary['total_value']:,.2f}")
    print(f"      - 已用: ¥{summary['used_capital']:,.2f}")
    print(f"      - 可用: ¥{summary['available_capital']:,.2f}")
    print(f"      - 持仓数量: {summary['position_count']}")
except Exception as e:
    print(f"   ❌ VirtualPortfolio 初始化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[5] 测试 BanditOptimizer 初始化...")
try:
    optimizer = get_bandit_optimizer()
    all_stats = optimizer.get_all_stats()
    print(f"   ✅ BanditOptimizer 初始化成功")
    print(f"      - 算法: Thompson Sampling")
    print(f"      - 已追踪策略数: {len(optimizer._arms)}")
    if all_stats:
        for stat in all_stats[:5]:
            print(f"      - {stat['strategy_id']}: 次数={stat['pull_count']}, 平均收益={stat['avg_reward']:.2f}%")
    else:
        print("      - 暂无策略统计")
except Exception as e:
    print(f"   ❌ BanditOptimizer 初始化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[6] 测试创建模拟信号...")
try:
    from deva.naja.strategy.result_store import StrategyResult
    
    test_signal = {
        "signal_type": "BUY",
        "stock_code": "SZ000001",
        "stock_name": "平安银行",
        "price": 12.50,
        "confidence": 0.85,
        "reason": "测试信号"
    }
    
    result = StrategyResult(
        id=f"test_{int(time.time() * 1000)}",
        strategy_id="test_strategy",
        strategy_name="测试策略",
        ts=time.time(),
        success=True,
        output_full=test_signal,
        output_preview=str(test_signal)
    )
    
    signal_stream = get_signal_stream()
    signal_stream.update(result)
    print(f"   ✅ 测试信号已发送到信号流")
    
    time.sleep(0.5)
    
    recent = signal_stream.get_recent(limit=3)
    if recent and recent[0].id == result.id:
        print(f"   ✅ 信号已正确添加到信号流")
    else:
        print(f"   ⚠️ 信号可能未被正确添加")
        
except Exception as e:
    print(f"   ❌ 测试信号创建失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[7] 测试信号解析...")
try:
    listener = get_signal_listener()
    
    test_result = StrategyResult(
        id=f"parse_test_{int(time.time() * 1000)}",
        strategy_id="test_strategy",
        strategy_name="测试策略",
        ts=time.time(),
        success=True,
        output_full={
            "signal_type": "BUY",
            "stock_code": "SZ000001",
            "stock_name": "平安银行",
            "price": 12.50,
            "confidence": 0.85
        }
    )
    
    detected = listener._parse_signal(test_result)
    
    if detected:
        print(f"   ✅ 信号解析成功")
        print(f"      - 信号ID: {detected.signal_id}")
        print(f"      - 股票代码: {detected.stock_code}")
        print(f"      - 股票名称: {detected.stock_name}")
        print(f"      - 信号类型: {detected.signal_type}")
        print(f"      - 价格: {detected.price}")
        print(f"      - 置信度: {detected.confidence}")
    else:
        print(f"   ❌ 信号解析失败")
        
except Exception as e:
    print(f"   ❌ 信号解析测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[8] 测试虚拟开仓...")
try:
    portfolio = get_virtual_portfolio()
    
    position = portfolio.open_position(
        strategy_id="test_strategy",
        strategy_name="测试策略",
        stock_code="SZ000001",
        stock_name="平安银行",
        price=12.50,
        amount=10000,
        stop_loss_pct=-5.0,
        take_profit_pct=10.0
    )
    
    if position:
        print(f"   ✅ 虚拟开仓成功")
        print(f"      - 持仓ID: {position.position_id}")
        print(f"      - 股票: {position.stock_name}({position.stock_code})")
        print(f"      - 入场价: ¥{position.entry_price:.2f}")
        print(f"      - 数量: {position.quantity:.2f}")
        print(f"      - 止损: ¥{position.stop_loss:.2f}")
        print(f"      - 止盈: ¥{position.take_profit:.2f}")
    else:
        print(f"   ❌ 虚拟开仓失败")
        
except Exception as e:
    print(f"   ❌ 虚拟开仓测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[9] 测试价格更新和止盈止损...")
try:
    portfolio = get_virtual_portfolio()
    
    positions = portfolio.get_all_positions(status="OPEN")
    if positions:
        pos = positions[0]
        print(f"   测试持仓: {pos.stock_name}")
        
        higher_price = pos.entry_price * 1.12
        closed = portfolio.update_price(pos.stock_code, higher_price)
        if closed:
            print(f"   ✅ 触发止盈，模拟平仓")
        else:
            print(f"   📊 价格更新到 ¥{higher_price:.2f}，未触发止盈止损")
        
        summary = portfolio.get_summary()
        print(f"      - 总收益: {summary['total_return']:.2f}%")
    else:
        print(f"   ⚠️ 无持仓，跳过价格更新测试")
        
except Exception as e:
    print(f"   ❌ 价格更新测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[10] 测试 Bandit 更新收益...")
try:
    optimizer = get_bandit_optimizer()
    tracker = get_bandit_tracker()
    
    result = tracker.on_position_closed(
        strategy_id="test_strategy",
        position_id="test_pos_001",
        entry_price=12.50,
        exit_price=13.00,
        open_timestamp=time.time() - 3600,
        trigger_adjust=False
    )
    
    if result.get("success"):
        print(f"   ✅ Bandit 收益更新成功")
        print(f"      - 收益率: {result['return_pct']:.2f}%")
        print(f"      - 持仓时长: {result['holding_seconds']:.0f}秒")
        print(f"      - 奖励值: {result['reward']:.2f}")
    else:
        print(f"   ❌ Bandit 更新失败: {result.get('error')}")
        
    stats = optimizer.get_stats("test_strategy")
    print(f"      - 策略统计: 次数={stats['pull_count']}, 平均收益={stats['avg_reward']:.2f}%")
        
except Exception as e:
    print(f"   ❌ Bandit 更新测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[11] 测试策略选择...")
try:
    optimizer = get_bandit_optimizer()
    
    strategies = ["strategy_a", "strategy_b", "strategy_c"]
    
    for s in strategies:
        optimizer._init_arm(s)
    
    result = optimizer.select_strategy(strategies, dry_run=True)
    
    if result.get("success"):
        print(f"   ✅ 策略选择成功")
        print(f"      - 选中策略: {result['selected']}")
        print(f"      - 所有分数: {result['all_scores']}")
    else:
        print(f"   ❌ 策略选择失败: {result.get('error')}")
        
except Exception as e:
    print(f"   ❌ 策略选择测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[12] 检查潜在问题...")
issues = []

try:
    listener = get_signal_listener()
    status = listener.get_status()
    
    if not status['running']:
        issues.append("SignalListener 未运行 - 需要手动启动或配置自动启动")
    
    positions = get_virtual_portfolio().get_all_positions(status="OPEN")
    if len(positions) > 0:
        print(f"   📊 当前有 {len(positions)} 个持仓")
except Exception as e:
    issues.append(f"检查状态失败: {e}")

if issues:
    print("   ⚠️ 发现以下问题:")
    for issue in issues:
        print(f"      - {issue}")
else:
    print("   ✅ 未发现明显问题")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)

print("""
📋 Bandit 模块工作流程总结:

1. 信号流 (SignalStream)
   - 策略执行结果 → 信号流缓存
   - 持久化到数据库 (naja_signals)

2. SignalListener (信号监听器)
   - 每 2 秒轮询信号流
   - 解析 output_full 提取股票信息
   - 支持多种字段名兼容 (code/symbol, name/stock_name, price/close/current)

3. VirtualPortfolio (虚拟持仓)
   - 根据信号创建虚拟买入
   - 管理止盈止损 (-5% / +10%)
   - 持久化持仓状态

4. MarketDataObserver (市场观察)
   - 获取实时股票价格
   - 更新持仓当前价格
   - 触发止盈止损检查

5. BanditPositionTracker (持仓追踪)
   - 平仓时计算收益率
   - 计算奖励值 (可配置多种算法)
   - 更新 Bandit 策略统计

6. BanditOptimizer (策略优化)
   - Thompson Sampling / UCB / Epsilon-Greedy
   - 根据收益自动调节策略参数
   - 决策持久化记录

🔧 注意事项:
- 需要在 output_controller 中启用 bandit 输出
- 信号需要包含 signal_type=BUY 和 stock_code
- 建议使用 standardize_output 规范化输出格式
""")
