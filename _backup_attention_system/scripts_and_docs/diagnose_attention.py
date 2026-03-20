#!/usr/bin/env python3
"""
诊断注意力策略系统运行状态
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

print("="*60)
print("🔍 注意力策略系统诊断")
print("="*60)

# 1. 检查策略管理器状态
print("\n1️⃣ 策略管理器状态")
print("-"*60)

try:
    from naja_attention_strategies import get_strategy_manager
    manager = get_strategy_manager()
    
    stats = manager.get_all_stats()
    print(f"   运行状态: {'🟢 运行中' if stats['is_running'] else '🔴 已停止'}")
    print(f"   总策略数: {stats['total_strategies']}")
    print(f"   活跃策略: {stats['active_strategies']}")
    print(f"   总信号数: {stats['total_signals_generated']}")
    print(f"   运行时间: {stats['runtime_seconds']:.1f} 秒")
    
    # 实验模式
    exp_info = manager.get_experiment_info()
    print(f"\n   实验模式: {'🧪 运行中' if exp_info['active'] else '⚪ 未启动'}")
    if exp_info['active']:
        print(f"   实验数据源: {exp_info.get('datasource_id', 'N/A')}")
    
    # 各策略详情
    print("\n   各策略执行统计:")
    for strategy_id, strategy_stats in stats['strategy_stats'].items():
        print(f"\n   📊 {strategy_stats['name']}:")
        print(f"      状态: {'🟢' if strategy_stats['enabled'] else '🔴'} {'启用' if strategy_stats['enabled'] else '禁用'}")
        print(f"      执行次数: {strategy_stats['execution_count']}")
        print(f"      跳过次数: {strategy_stats['skip_count']}")
        print(f"      信号数量: {strategy_stats['signal_count']}")
        print(f"      全局注意力阈值: {strategy_stats['min_global_attention']}")
        print(f"      个股权重阈值: {strategy_stats['min_symbol_weight']}")
        
except Exception as e:
    print(f"   ❌ 获取策略管理器失败: {e}")
    import traceback
    traceback.print_exc()

# 2. 检查注意力系统状态
print("\n2️⃣ 注意力系统状态")
print("-"*60)

try:
    from deva.naja.attention_integration import get_attention_integration
    integration = get_attention_integration()
    
    report = integration.get_attention_report()
    print(f"   全局注意力: {report.get('global_attention', 0):.3f}")
    print(f"   处理快照数: {report.get('processed_snapshots', 0)}")
    print(f"   平均延迟: {report.get('avg_latency_ms', 0):.2f} ms")
    print(f"   状态: {report.get('status', 'unknown')}")
    
    freq_summary = report.get('frequency_summary', {})
    print(f"\n   高频股票: {freq_summary.get('high_frequency', 0)} 只")
    print(f"   中频股票: {freq_summary.get('medium_frequency', 0)} 只")
    print(f"   低频股票: {freq_summary.get('low_frequency', 0)} 只")
    
    # 高注意力股票
    high_attention = integration.get_high_attention_symbols(threshold=2.0)
    print(f"\n   高注意力股票 (权重>2.0): {len(high_attention)} 只")
    if high_attention:
        print(f"   示例: {list(high_attention)[:5]}")
    
    # 活跃板块
    active_sectors = integration.get_active_sectors(threshold=0.3)
    print(f"\n   活跃板块 (注意力>0.3): {len(active_sectors)} 个")
    if active_sectors:
        print(f"   列表: {active_sectors}")
        
except Exception as e:
    print(f"   ❌ 获取注意力系统失败: {e}")
    import traceback
    traceback.print_exc()

# 3. 检查调度中心状态
print("\n3️⃣ 调度中心状态")
print("-"*60)

try:
    from deva.naja.attention_orchestrator import get_orchestrator
    orchestrator = get_orchestrator()
    
    print(f"   处理帧数: {orchestrator._processed_frames}")
    print(f"   过滤帧数: {orchestrator._filtered_frames}")
    print(f"   注册数据源: {list(orchestrator._datasources.keys())}")
    print(f"   注册策略: {list(orchestrator._strategies.keys())}")
    
    context = orchestrator.get_attention_context()
    print(f"\n   全局注意力: {context.get('global_attention', 0):.3f}")
    print(f"   高注意力股票: {len(context.get('high_attention_symbols', []))} 只")
    print(f"   活跃板块: {len(context.get('active_sectors', []))} 个")
    
except Exception as e:
    print(f"   ❌ 获取调度中心失败: {e}")
    import traceback
    traceback.print_exc()

# 4. 检查信号流
print("\n4️⃣ 信号流状态")
print("-"*60)

try:
    from deva.naja.signal.stream import get_signal_stream
    stream = get_signal_stream()
    
    # 获取最近信号
    recent = stream.get_recent(limit=20)
    print(f"   最近信号数: {len(recent)}")
    
    if recent:
        print("\n   最近信号列表:")
        for r in recent[-10:]:
            print(f"      {r.strategy_name}: {r.output_preview}")
    else:
        print("   ⚠️ 暂无信号")
        
except Exception as e:
    print(f"   ❌ 获取信号流失败: {e}")

# 5. 分析可能的问题
print("\n5️⃣ 问题分析")
print("-"*60)

try:
    # 检查全局注意力
    global_attn = report.get('global_attention', 0)
    if global_attn < 0.3:
        print(f"   ⚠️ 全局注意力较低 ({global_attn:.3f})，策略可能因阈值限制不执行")
        print(f"      建议: 检查数据是否正常，或降低策略的 min_global_attention 阈值")
    
    # 检查高注意力股票数量
    high_count = len(high_attention) if 'high_attention' in locals() else 0
    if high_count == 0:
        print(f"   ⚠️ 没有高注意力股票，个股策略无法筛选出目标")
        print(f"      建议: 检查数据是否包含涨跌幅、成交量等字段")
    
    # 检查策略执行次数
    total_exec = sum(s['execution_count'] for s in stats['strategy_stats'].values())
    if total_exec == 0:
        print(f"   ⚠️ 策略从未执行，可能原因:")
        print(f"      1. 全局注意力低于策略阈值")
        print(f"      2. 执行间隔冷却期限制")
        print(f"      3. 数据源未正确推送数据到注意力系统")
    
    # 检查信号数量
    total_signals = stats['total_signals_generated']
    if total_signals == 0 and total_exec > 0:
        print(f"   ⚠️ 策略执行了但未生成信号，可能原因:")
        print(f"      1. 没有股票满足策略的买入/卖出条件")
        print(f"      2. 信号冷却期限制 (默认60秒)")
        print(f"      3. 策略分析逻辑未触发")
        
except Exception as e:
    print(f"   ❌ 分析问题失败: {e}")

print("\n" + "="*60)
print("诊断完成")
print("="*60)
