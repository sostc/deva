#!/usr/bin/env python3
"""
检查注意力系统数据是否正确流向 UI
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

print("="*60)
print("🔍 检查 UI 数据流")
print("="*60)

# 1. 检查历史追踪器
print("\n1️⃣ 检查历史追踪器")
print("-"*60)

try:
    from deva.naja.attention.history_tracker import get_history_tracker
    tracker = get_history_tracker()
    
    print(f"   ✅ 历史追踪器已创建: {tracker}")
    
    # 获取摘要
    summary = tracker.get_summary()
    print(f"   快照数: {summary['snapshot_count']}")
    print(f"   变化数: {summary['change_count']}")
    print(f"   最近变化: {summary['recent_changes']}")
    
    # 获取变化列表
    changes = tracker.get_recent_changes(n=20)
    print(f"   变化记录数: {len(changes)}")
    
    if changes:
        print("\n   最近变化:")
        for c in changes[-5:]:
            print(f"      {c.change_type}: {c.description}")
    else:
        print("\n   ⚠️ 没有变化记录")
        
except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 2. 检查 UI 函数
print("\n2️⃣ 检查 UI 函数")
print("-"*60)

try:
    from deva.naja.attention.ui import _get_attention_changes, _get_attention_shift_report, _render_attention_changes, _render_attention_shift_report
    
    # 测试获取变化
    changes = _get_attention_changes()
    print(f"   _get_attention_changes() 返回: {len(changes)} 条记录")
    
    # 测试渲染
    html = _render_attention_changes(changes)
    print(f"   _render_attention_changes() 返回 HTML 长度: {len(html)}")
    if html:
        print(f"   HTML 预览: {html[:200]}...")
    
    # 测试转移报告
    report = _get_attention_shift_report()
    print(f"\n   _get_attention_shift_report() 返回:")
    print(f"      has_shift: {report.get('has_shift')}")
    
    html2 = _render_attention_shift_report(report)
    print(f"   _render_attention_shift_report() 返回 HTML 长度: {len(html2)}")
    
except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 3. 检查注意力系统
print("\n3️⃣ 检查注意力系统")
print("-"*60)

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
            print(f"   全局注意力: {integration.attention_system._last_global_attention}")
            
except Exception as e:
    print(f"   ❌ 错误: {e}")

# 4. 检查调度中心
print("\n4️⃣ 检查调度中心")
print("-"*60)

try:
    from deva.naja.attention_orchestrator import get_orchestrator
    orchestrator = get_orchestrator()
    
    print(f"   ✅ 调度中心已创建")
    print(f"   处理帧数: {orchestrator._processed_frames}")
    print(f"   过滤帧数: {orchestrator._filtered_frames}")
    
    # 检查是否记录了快照
    if orchestrator._processed_frames > 0:
        print(f"\n   数据流正常: 已处理 {orchestrator._processed_frames} 帧")
    else:
        print(f"\n   ⚠️ 没有数据处理记录")
        
except Exception as e:
    print(f"   ❌ 错误: {e}")

print("\n" + "="*60)
print("检查完成")
print("="*60)

# 总结
print("\n📋 总结:")
print("-"*60)
print("如果上述检查都正常，但 UI 仍不显示变化，可能原因:")
print("1. 数据确实没有变化（历史行情数据稳定）")
print("2. 权重计算结果变化太小")
print("3. PyWebIO 渲染问题（尝试刷新页面）")
print("-"*60)
