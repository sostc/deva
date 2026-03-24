#!/usr/bin/env python3
"""
检查注意力系统性能状态
"""

def check_performance():
    print("=" * 60)
    print("注意力系统性能检查")
    print("=" * 60)
    
    # 1. 检查注意力集成
    print("\n1. 检查注意力集成...")
    try:
        from deva.naja.attention.integration import get_attention_integration
        integration = get_attention_integration()
        
        if integration is None:
            print("❌ 注意力集成未初始化")
            return
        
        print(f"✅ 注意力集成已创建")
        
        if integration.attention_system is None:
            print("❌ 注意力系统未初始化")
            return
        
        print(f"✅ 注意力系统已创建")
        
        # 获取报告
        report = integration.get_attention_report()
        print(f"\n   处理快照数: {report.get('processed_snapshots', 0)}")
        print(f"   全局注意力: {report.get('global_attention', 0):.3f}")
        
        # 双引擎统计
        dual = report.get('dual_engine_summary', {})
        river = dual.get('river_stats', {})
        pytorch = dual.get('pytorch_stats', {})
        
        print(f"\n   River Engine:")
        print(f"     处理数: {river.get('processed_count', 0)}")
        print(f"     异常数: {river.get('anomaly_count', 0)}")
        print(f"     活跃股票: {river.get('active_symbols', 0)}")
        
        print(f"\n   PyTorch Engine:")
        print(f"     推理数: {pytorch.get('inference_count', 0)}")
        print(f"     队列大小: {pytorch.get('pending_queue_size', 0)}")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 2. 检查调度中心
    print("\n2. 检查调度中心...")
    try:
        from deva.naja.attention.center import get_orchestrator
        orchestrator = get_orchestrator()
        
        print(f"✅ 调度中心已创建")
        print(f"   处理帧数: {orchestrator._processed_frames}")
        print(f"   过滤帧数: {orchestrator._filtered_frames}")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    # 3. 检查数据源
    print("\n3. 检查数据源...")
    try:
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        
        datasources = ds_mgr.list_all() if hasattr(ds_mgr, 'list_all') else []
        print(f"   数据源数量: {len(datasources)}")
        
        for ds in datasources:
            name = getattr(ds, 'name', 'Unknown')
            is_running = getattr(ds, 'is_running', False)
            if '回放' in name or 'replay' in name.lower():
                status = "🟢 运行中" if is_running else "🔴 停止"
                print(f"   {status}: {name}")
                
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    print("\n" + "=" * 60)
    
    # 性能分析
    print("\n📊 性能分析:")
    print("- 如果 processed_snapshots = 0，说明数据没有流入注意力系统")
    print("- 如果 数据源停止，需要启动历史行情回放")
    print("- 正常情况下，回放模式应该比实时模式快 10-100 倍")

if __name__ == "__main__":
    check_performance()
