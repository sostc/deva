#!/usr/bin/env python3
"""
检查数据源 -> 注意力系统的完整数据流
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

print("="*70)
print("🔍 检查数据源 -> 注意力系统数据流")
print("="*70)

# 1. 检查数据源状态
print("\n1️⃣ 检查数据源状态")
print("-"*70)

try:
    from deva.naja.datasource import get_datasource_manager
    ds_mgr = get_datasource_manager()
    
    # 列出所有数据源
    datasources = ds_mgr.list()
    print(f"   总数据源数: {len(datasources)}")
    
    # 查找运行的数据源
    running_ds = [ds for ds in datasources if ds.is_running]
    print(f"   运行中数据源: {len(running_ds)}")
    
    for ds in running_ds:
        print(f"\n   🟢 {ds.name} (ID: {ds.id})")
        print(f"      类型: {ds.source_type}")
        print(f"      状态: 运行中")
        
except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 2. 检查调度中心接收数据
print("\n2️⃣ 检查调度中心")
print("-"*70)

try:
    from deva.naja.attention_orchestrator import get_orchestrator
    orchestrator = get_orchestrator()
    
    print(f"   ✅ 调度中心已创建")
    print(f"   处理帧数: {orchestrator._processed_frames}")
    print(f"   过滤帧数: {orchestrator._filtered_frames}")
    print(f"   注册数据源: {list(orchestrator._datasources.keys())}")
    
    if orchestrator._processed_frames == 0:
        print("\n   ⚠️ 警告: 调度中心没有处理任何数据！")
        print("      可能原因:")
        print("      1. 数据源没有 emit 数据")
        print("      2. 数据源没有正确绑定到调度中心")
        print("      3. 数据格式不正确（不是 DataFrame）")
    else:
        print(f"\n   ✅ 数据流正常: 已处理 {orchestrator._processed_frames} 帧")
        
except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 3. 检查注意力系统
print("\n3️⃣ 检查注意力系统")
print("-"*70)

try:
    from deva.naja.attention_integration import get_attention_integration
    integration = get_attention_integration()
    
    if integration is None:
        print("   ❌ 注意力集成未初始化")
    else:
        print(f"   ✅ 注意力集成已创建")
        
        if integration.attention_system is None:
            print("   ❌ 注意力系统未初始化")
        else:
            print(f"   ✅ 注意力系统已创建")
            
            # 获取报告
            report = integration.get_attention_report()
            print(f"\n   全局注意力: {report.get('global_attention', 0):.3f}")
            print(f"   处理快照数: {report.get('processed_snapshots', 0)}")
            print(f"   状态: {report.get('status', 'unknown')}")
            
            # 获取权重
            sector_weights = integration.attention_system.sector_attention.get_all_weights()
            symbol_weights = integration.attention_system.weight_pool.get_all_weights()
            
            print(f"\n   板块权重数: {len(sector_weights)}")
            print(f"   个股权重数: {len(symbol_weights)}")
            
            if len(symbol_weights) == 0:
                print("\n   ⚠️ 警告: 没有计算任何个股权重！")
                print("      可能原因:")
                print("      1. 数据源没有推送数据")
                print("      2. 数据格式不正确（缺少 code/volume/p_change 字段）")
            else:
                # 显示Top 5
                top_symbols = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"\n   Top 5 股票:")
                for symbol, weight in top_symbols:
                    print(f"      {symbol}: {weight:.3f}")
                
except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 4. 检查历史追踪器
print("\n4️⃣ 检查历史追踪器")
print("-"*70)

try:
    from deva.naja.attention.history_tracker import get_history_tracker
    tracker = get_history_tracker()
    
    print(f"   ✅ 历史追踪器已创建")
    
    summary = tracker.get_summary()
    print(f"\n   快照数: {summary['snapshot_count']}")
    print(f"   变化数: {summary['change_count']}")
    
    if summary['snapshot_count'] == 0:
        print("\n   ⚠️ 警告: 历史追踪器没有记录任何快照！")
        print("      可能原因:")
        print("      1. 调度中心没有调用 record_snapshot")
        print("      2. 注意力系统没有更新")
    
    # 检查是否有变化
    changes = tracker.get_recent_changes(n=10)
    print(f"\n   变化记录数: {len(changes)}")
    
    if len(changes) == 0 and summary['snapshot_count'] > 1:
        print("\n   ⚠️ 警告: 有快照但没有检测到变化！")
        print("      可能原因:")
        print("      1. 权重变化太小（低于阈值）")
        print("      2. 数据没有变化")
        
except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 5. 检查策略管理器
print("\n5️⃣ 检查策略管理器")
print("-"*70)

try:
    from naja_attention_strategies import get_strategy_manager
    manager = get_strategy_manager()
    
    stats = manager.get_all_stats()
    print(f"   运行状态: {'🟢 运行中' if stats['is_running'] else '🔴 已停止'}")
    print(f"   总策略数: {stats['total_strategies']}")
    print(f"   活跃策略: {stats['active_strategies']}")
    print(f"   总信号数: {stats['total_signals_generated']}")
    
    if stats['total_strategies'] == 0:
        print("\n   ⚠️ 警告: 没有注册任何策略！")
        print("      可能原因:")
        print("      1. 策略管理器没有初始化")
        print("      2. initialize_default_strategies 没有被调用")
        
    if stats['is_running'] and stats['total_strategies'] > 0:
        print("\n   各策略统计:")
        for strategy_id, strategy_stats in stats['strategy_stats'].items():
            print(f"      {strategy_stats['name']}: 执行 {strategy_stats['execution_count']} 次, 信号 {strategy_stats['signal_count']} 个")
        
except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 6. 检查实验模式
print("\n6️⃣ 检查实验模式")
print("-"*70)

try:
    from deva.naja.strategy import get_strategy_manager
    strategy_mgr = get_strategy_manager()
    exp_info = strategy_mgr.get_experiment_info()
    
    print(f"   实验模式: {'🧪 运行中' if exp_info.get('active') else '⚪ 未启动'}")
    if exp_info.get('active'):
        print(f"   数据源: {exp_info.get('datasource_id', 'N/A')}")
        print(f"   策略数: {exp_info.get('target_count', 0)}")
        
    # 检查注意力策略的实验模式
    from naja_attention_strategies import get_strategy_manager as get_attention_manager
    attn_manager = get_attention_manager()
    attn_exp = attn_manager.get_experiment_info()
    
    print(f"\n   注意力策略实验模式: {'🧪 运行中' if attn_exp.get('active') else '⚪ 未启动'}")
    if attn_exp.get('active'):
        print(f"   数据源: {attn_exp.get('datasource_id', 'N/A')}")
        print(f"   策略数: {attn_exp.get('strategy_count', 0)}")
        
except Exception as e:
    print(f"   ❌ 错误: {e}")

print("\n" + "="*70)
print("诊断完成")
print("="*70)

# 总结
print("\n📋 问题诊断总结:")
print("-"*70)

issues = []

# 根据检查结果总结问题
if 'orchestrator' in dir() and orchestrator._processed_frames == 0:
    issues.append("❌ 调度中心没有接收到数据 - 检查数据源是否正确 emit 数据")

if 'integration' in dir() and integration and integration.attention_system:
    symbol_weights = integration.attention_system.weight_pool.get_all_weights()
    if len(symbol_weights) == 0:
        issues.append("❌ 注意力系统没有计算权重 - 检查数据格式是否正确")

if 'tracker' in dir() and tracker.get_summary()['snapshot_count'] == 0:
    issues.append("❌ 历史追踪器没有记录 - 检查调度中心是否正确调用 record_snapshot")

if 'manager' in dir() and manager.get_all_stats()['total_strategies'] == 0:
    issues.append("❌ 策略管理器没有注册策略 - 需要初始化策略")

if not issues:
    print("✅ 所有组件正常运行，数据流应该正常")
    print("\n如果 UI 仍不显示变化，可能原因:")
    print("1. 历史行情数据本身变化很小")
    print("2. 权重计算结果变化低于阈值")
    print("3. PyWebIO 渲染问题（尝试刷新页面）")
else:
    print("发现以下问题:")
    for issue in issues:
        print(f"   {issue}")

print("-"*70)
