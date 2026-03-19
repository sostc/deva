#!/usr/bin/env python3
"""
实时监控注意力系统数据流

运行此脚本可以查看：
1. 注意力系统是否初始化
2. 数据源是否在发送数据
3. 注意力系统是否在处理数据
4. 历史追踪器是否记录变化
"""

import time
import sys
from datetime import datetime

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def print_section(text):
    print(f"\n{'-'*40}")
    print(f"  {text}")
    print(f"{'-'*40}")

def check_attention_system():
    """检查注意力系统状态"""
    print_header("注意力系统实时监控")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 检查注意力集成
    print_section("1. 注意力集成状态")
    try:
        from deva.naja.attention_integration import get_attention_integration
        integration = get_attention_integration()
        
        if integration is None:
            print("❌ 注意力集成未初始化")
            return False
        
        print("✅ 注意力集成已创建")
        
        if integration.attention_system is None:
            print("❌ 注意力系统未初始化")
            print("   提示: 需要使用 --attention 参数启动 naja")
            return False
        
        print("✅ 注意力系统已创建")
        
        # 获取报告
        report = integration.get_attention_report()
        print(f"   全局注意力: {report.get('global_attention', 0):.3f}")
        print(f"   处理快照数: {report.get('processed_snapshots', 0)}")
        print(f"   状态: {report.get('status', 'unknown')}")
        
        # 获取权重
        sector_weights = integration.attention_system.sector_attention.get_all_weights()
        symbol_weights = integration.attention_system.weight_pool.get_all_weights()
        
        print(f"   板块权重数: {len(sector_weights)}")
        print(f"   个股权重数: {len(symbol_weights)}")
        
        if len(symbol_weights) > 0:
            print("   Top 5 股票:")
            top_symbols = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:5]
            for symbol, weight in top_symbols:
                print(f"     {symbol}: {weight:.3f}")
        else:
            print("   ⚠️ 没有计算任何个股权重 - 数据可能未流入")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 2. 检查调度中心
    print_section("2. 调度中心状态")
    try:
        from deva.naja.attention_orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        
        print("✅ 调度中心已创建")
        print(f"   处理帧数: {orchestrator._processed_frames}")
        print(f"   过滤帧数: {orchestrator._filtered_frames}")
        print(f"   注册数据源: {list(orchestrator._datasources.keys())}")
        
        if orchestrator._processed_frames == 0:
            print("   ⚠️ 调度中心没有处理任何数据！")
            print("   可能原因:")
            print("   1. 数据源没有 emit 数据")
            print("   2. 数据源没有正确绑定到调度中心")
            print("   3. 数据格式不正确（不是 DataFrame）")
            print("   4. 历史回放没有运行")
        else:
            print(f"   ✅ 数据流正常: 已处理 {orchestrator._processed_frames} 帧")
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. 检查历史追踪器
    print_section("3. 历史追踪器状态")
    try:
        from deva.naja.attention.history_tracker import get_history_tracker
        tracker = get_history_tracker()
        
        print("✅ 历史追踪器已创建")
        
        summary = tracker.get_summary()
        print(f"   快照数: {summary['snapshot_count']}")
        print(f"   变化数: {summary['change_count']}")
        print(f"   最近变化: {summary['recent_changes']}")
        
        if summary['snapshot_count'] == 0:
            print("   ⚠️ 历史追踪器没有记录任何快照！")
        
        # 显示变化
        changes = tracker.get_recent_changes(n=10)
        if changes:
            print(f"   最近 {len(changes)} 条变化:")
            for change in changes[-5:]:
                emoji = {
                    'new_hot': '🔥',
                    'cooled': '❄️',
                    'strengthen': '📈',
                    'weaken': '📉'
                }.get(change.change_type, '•')
                print(f"     {emoji} {change.description}")
        else:
            print("   暂无变化记录")
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 4. 检查策略管理器
    print_section("4. 策略管理器状态")
    try:
        from naja_attention_strategies import get_strategy_manager
        manager = get_strategy_manager()
        
        stats = manager.get_all_stats()
        
        if stats['is_running']:
            print("🟢 策略管理器运行中")
        else:
            print("🔴 策略管理器已停止")
        
        print(f"   总策略数: {stats['total_strategies']}")
        print(f"   活跃策略: {stats['active_strategies']}")
        print(f"   总信号数: {stats['total_signals_generated']}")
        
        if stats['total_strategies'] == 0:
            print("   ⚠️ 没有注册任何策略！")
        else:
            print("   各策略统计:")
            for strategy_id, strategy_stats in stats['strategy_stats'].items():
                status = "🟢" if strategy_stats['enabled'] else "🔴"
                print(f"     {status} {strategy_stats['name']}: 执行 {strategy_stats['execution_count']} 次, 信号 {strategy_stats['signal_count']} 个")
        
        # 实验模式
        exp_info = manager.get_experiment_info()
        if exp_info.get('active'):
            print(f"   🧪 实验模式运行中: {exp_info.get('datasource_id')}")
        else:
            print("   ⚪ 实验模式未启动")
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 5. 检查数据源
    print_section("5. 数据源状态")
    try:
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        
        # 尝试获取数据源信息
        try:
            datasources = ds_mgr.list_all()
            print(f"   数据源数量: {len(datasources)}")
            
            for ds in datasources:
                status = "🟢 运行中" if getattr(ds, 'is_running', False) else "🔴 停止"
                name = getattr(ds, 'name', 'Unknown')
                print(f"     {status}: {name}")
                
                # 检查是否是实验模式数据源
                if 'replay' in name.lower() or 'experiment' in name.lower():
                    print(f"        📊 这可能是实验模式数据源")
        except Exception as e:
            print(f"   无法获取数据源列表: {e}")
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("监控完成")
    print("="*60)
    
    return True

def continuous_monitor(interval=5):
    """持续监控"""
    print("开始持续监控，按 Ctrl+C 停止...")
    print(f"刷新间隔: {interval} 秒\n")
    
    try:
        while True:
            # 清屏
            print("\033[2J\033[H")
            check_attention_system()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n监控已停止")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="监控注意力系统状态")
    parser.add_argument("--continuous", "-c", action="store_true", help="持续监控")
    parser.add_argument("--interval", "-i", type=int, default=5, help="刷新间隔（秒）")
    
    args = parser.parse_args()
    
    if args.continuous:
        continuous_monitor(args.interval)
    else:
        check_attention_system()
