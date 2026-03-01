#!/usr/bin/env python3
"""
验证任务管理UI功能

这个脚本验证任务管理界面的核心功能是否可用。
"""

import asyncio

def test_core_functionality():
    """测试核心功能"""
    print("=" * 60)
    print("验证任务管理UI功能")
    print("=" * 60)
    
    success_count = 0
    total_tests = 6
    
    print("\n1. 测试任务管理模块导入")
    try:
        from deva.admin_ui.tasks.task_admin import render_task_admin
        print("✅ 任务管理模块导入成功")
        success_count += 1
    except Exception as e:
        print(f"❌ 任务管理模块导入失败: {e}")
    
    print("\n2. 测试任务对话框功能导入")
    try:
        from deva.admin_ui.tasks.task_dialog import (
            show_create_task_dialog,
            show_edit_task_dialog,
            validate_task_code
        )
        print("✅ 任务对话框功能导入成功")
        success_count += 1
    except Exception as e:
        print(f"❌ 任务对话框功能导入失败: {e}")
    
    print("\n3. 测试任务代码验证功能")
    try:
        from deva.admin_ui.tasks.task_dialog import validate_task_code
        
        test_code = '''
async def execute(context=None):
    """测试任务"""
    return "任务执行完成"
'''
        result = validate_task_code(test_code)
        if result['valid']:
            print("✅ 任务代码验证功能正常")
            success_count += 1
        else:
            print(f"❌ 任务代码验证失败: {result}")
    except Exception as e:
        print(f"❌ 任务代码验证功能异常: {e}")
    
    print("\n4. 测试AI代码生成器")
    try:
        from deva.admin_ui.ai.ai_code_generator import TaskAIGenerator
        
        generator = TaskAIGenerator()
        template = generator._get_default_task_template()
        if "async def execute" in template:
            print("✅ AI代码生成器功能正常")
            success_count += 1
        else:
            print(f"❌ AI代码生成器模板异常")
    except Exception as e:
        print(f"❌ AI代码生成器功能异常: {e}")
    
    print("\n5. 测试任务管理器集成")
    try:
        from deva.admin_ui.tasks.task_manager import get_task_manager
        
        task_manager = get_task_manager()
        stats = task_manager.get_overall_stats()
        print(f"✅ 任务管理器集成成功 (任务数: {stats.get('basic_stats', {}).get('total_items', 0)})")
        success_count += 1
    except Exception as e:
        print(f"❌ 任务管理器集成失败: {e}")
    
    print("\n6. 测试任务单元功能")
    try:
        from deva.admin_ui.tasks.task_unit import TaskUnit, TaskMetadata, TaskState, TaskExecution, TaskType
        
        metadata = TaskMetadata(
            id="test_task",
            name="测试任务",
            description="测试描述",
            task_type=TaskType.INTERVAL,
            schedule_config={"interval": 60}
        )
        
        state = TaskState(
            status="stopped",
            last_run_time=0,
            next_run_time=0,
            run_count=0,
            error_count=0
        )
        
        execution = TaskExecution(
            job_code="async def execute(context=None): return 'test'",
            execution_history=[]
        )
        
        task_unit = TaskUnit(metadata=metadata, state=state, execution=execution)
        
        if task_unit.name == "测试任务":
            print("✅ 任务单元功能正常")
            success_count += 1
        else:
            print(f"❌ 任务单元功能异常")
    except Exception as e:
        print(f"❌ 任务单元功能异常: {e}")
    
    print("\n" + "=" * 60)
    print(f"测试结果: {success_count}/{total_tests} 通过")
    
    if success_count == total_tests:
        print("🎉 所有功能测试通过！任务管理UI已就绪")
        print("\n✨ 主要特性:")
        print("• AI智能代码生成与审核编辑")
        print("• 多种代码输入方式（AI/手动/模板/文件）")
        print("• 实时代码验证和安全检查")
        print("• 用户友好的审核确认流程")
        print("• 完整的任务生命周期管理")
        print("• 统计信息和执行历史展示")
        print("• 批量操作和管理功能")
        return True
    else:
        print("⚠️  部分功能测试失败，需要检查配置")
        return False


def test_ui_integration():
    """测试UI集成"""
    print("\n" + "=" * 60)
    print("测试UI集成路径")
    print("=" * 60)
    
    try:
        with open('/Users/spark/pycharmproject/deva/deva/admin.py', 'r') as f:
            content = f.read()
            
        if 'task_admin' in content and 'render_task_admin' in content:
            print("✅ admin.py已集成任务管理")
            
            if 'taskadmin' in content:
                print("✅ 任务管理路由已配置")
                return True
            else:
                print("❌ 任务管理路由未找到")
                return False
        else:
            print("❌ admin.py未集成任务管理")
            return False
            
    except Exception as e:
        print(f"❌ 检查admin.py失败: {e}")
        return False


def main():
    """主测试函数"""
    print("开始验证任务管理UI功能...")
    
    core_test_passed = test_core_functionality()
    
    ui_test_passed = test_ui_integration()
    
    print("\n" + "=" * 60)
    print("最终测试结果:")
    
    if core_test_passed and ui_test_passed:
        print("🎉 任务管理UI集成成功！")
        print("\n📋 用户现在可以:")
        print("1. 访问任务管理界面 (/taskadmin)")
        print("2. 使用AI代码生成功能创建任务")
        print("3. 通过多种方式输入任务代码")
        print("4. 享受完整的代码审核编辑流程")
        print("5. 管理任务生命周期和监控执行状态")
        
        print("\n🔧 技术实现:")
        print("• 统一的AI代码生成架构")
        print("• 完整的用户审核流程")
        print("• 实时代码验证系统")
        print("• 与现有任务管理器无缝集成")
        print("• PyWebIO界面优化和用户体验提升")
        
        return True
    else:
        print("⚠️  测试中发现问题，需要进一步调试")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
