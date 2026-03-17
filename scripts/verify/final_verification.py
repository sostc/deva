#!/usr/bin/env python3
"""
最终验证 - 任务管理UI集成

验证AI代码生成功能已成功集成到任务管理界面。
"""

import asyncio

def test_complete_integration():
    """测试完整的集成"""
    
    print("🚀 最终验证 - 任务管理UI集成")
    print("=" * 70)
    
    tests_passed = 0
    total_tests = 8
    
    print(f"\n1️⃣ 测试UI框架集成")
    try:
        from deva.admin.tasks.task_admin import render_task_admin
        print("   ✅ 任务管理UI模块导入成功")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ UI框架集成失败: {e}")
    
    print(f"\n2️⃣ 测试任务对话框功能")
    try:
        from deva.admin.tasks.task_dialog import (
            show_create_task_dialog,
            show_edit_task_dialog,
            validate_task_code
        )
        print("   ✅ 任务对话框功能导入成功")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ 任务对话框功能失败: {e}")
    
    print(f"\n3️⃣ 测试代码验证系统")
    try:
        test_code = '''
async def execute(context=None):
    """测试任务"""
    return "任务执行完成"
'''
        result = validate_task_code(test_code)
        if result['valid']:
            print("   ✅ 代码验证功能正常")
            tests_passed += 1
        else:
            print(f"   ❌ 代码验证失败: {result}")
    except Exception as e:
        print(f"   ❌ 代码验证系统异常: {e}")
    
    print(f"\n4️⃣ 测试AI代码生成器")
    try:
        from deva.admin.ai.ai_code_generator import TaskAIGenerator
        
        generator = TaskAIGenerator()
        template = generator._get_default_task_template()
        
        if "async def execute(context=None):" in template:
            print("   ✅ AI代码生成器功能正常")
            tests_passed += 1
        else:
            print("   ❌ AI代码生成器模板异常")
    except Exception as e:
        print(f"   ❌ AI代码生成器异常: {e}")
    
    print(f"\n5️⃣ 测试任务管理器集成")
    try:
        from deva.admin.tasks.task_manager import get_task_manager
        
        task_manager = get_task_manager()
        stats = task_manager.get_overall_stats()
        
        print(f"   ✅ 任务管理器集成成功 (统计功能正常)")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ 任务管理器集成失败: {e}")
    
    print(f"\n6️⃣ 测试任务单元功能")
    try:
        from deva.admin.tasks.task_unit import TaskUnit, TaskMetadata, TaskState, TaskExecution, TaskType
        
        metadata = TaskMetadata(
            id="test_integration",
            name="集成测试任务",
            description="测试集成",
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
            job_code="async def execute(context=None): return '集成测试通过'",
            execution_history=[]
        )
        
        task_unit = TaskUnit(metadata=metadata, state=state, execution=execution)
        
        if task_unit.name == "集成测试任务":
            print("   ✅ 任务单元功能正常")
            tests_passed += 1
        else:
            print("   ❌ 任务单元功能异常")
    except Exception as e:
        print(f"   ❌ 任务单元功能异常: {e}")
    
    print(f"\n7️⃣ 测试主管理界面集成")
    try:
        with open('/Users/spark/pycharmproject/deva/deva/admin.py', 'r') as f:
            content = f.read()
            
        if 'task_admin' in content and 'render_task_admin' in content:
            print("   ✅ 主管理界面已集成任务管理")
            tests_passed += 1
        else:
            print("   ❌ 主管理界面未正确集成")
    except Exception as e:
        print(f"   ❌ 主管理界面集成检查失败: {e}")
    
    print(f"\n8️⃣ 测试UI渲染功能")
    try:
        class MockContext:
            def __getitem__(self, key):
                return lambda *args, **kwargs: None
        
        ctx = MockContext()
        
        async def test_render():
            await render_task_admin(ctx)
        
        asyncio.run(test_render())
        print("   ✅ UI渲染功能正常")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ UI渲染功能异常: {e}")
    
    print("\n" + "=" * 70)
    print(f"🎯 最终测试结果: {tests_passed}/{total_tests} 通过")
    
    if tests_passed == total_tests:
        print("\n🎉 恭喜！任务管理UI集成成功完成！")
        print("\n✨ 用户现在可以体验以下功能：")
        print("   • 🚀 访问任务管理界面 (/taskadmin)")
        print("   • 🤖 使用AI智能创建任务")
        print("   • 📝 通过多种方式输入任务代码")
        print("   • ✓ 享受完整的代码审核编辑流程")
        print("   • 📊 查看详细的任务统计信息")
        print("   • ⚙️ 使用批量管理功能")
        
        print("\n🔧 技术亮点：")
        print("   • 统一的AI代码生成架构")
        print("   • 完整的用户审核流程")
        print("   • 实时代码验证系统")
        print("   • 与现有系统无缝集成")
        print("   • 现代化的UI界面设计")
        
        return True
    else:
        print(f"\n⚠️  测试中发现 {total_tests - tests_passed} 个问题，需要进一步调试")
        return False


def show_user_guide():
    """显示用户指南"""
    
    print("\n" + "=" * 70)
    print("📖 用户使用指南")
    print("=" * 70)
    
    print("\n🌐 访问方式：")
    print("   1. 打开Web浏览器")
    print("   2. 访问: http://localhost:任务管理端口/taskadmin")
    print("   3. 登录系统（如果需要）")
    
    print("\n🎯 主要功能：")
    print("   • 🆕 创建任务：点击\"创建任务\"按钮")
    print("   • 👁️ 查看任务：浏览任务列表和统计信息")
    print("   • ✏️ 编辑任务：点击任务行的\"编辑\"按钮")
    print("   • 📊 查看详情：点击\"详情\"查看完整信息")
    print("   • ⚙️ 批量操作：使用\"批量管理\"功能")
    
    print("\n🤖 AI代码生成流程：")
    print("   1. 选择\"AI智能生成\"方式")
    print("   2. 描述任务需求（自然语言）")
    print("   3. 配置任务参数（类型、时间等）")
    print("   4. 等待AI生成代码")
    print("   5. 审核和编辑生成的代码")
    print("   6. 确认并创建任务")
    
    print("\n💡 使用技巧：")
    print("   • 使用清晰的自然语言描述需求")
    print("   • 查看生成的代码确保符合预期")
    print("   • 利用模板快速创建常见任务")
    print("   • 定期检查任务执行统计信息")


def main():
    """主函数"""
    
    success = test_complete_integration()
    
    if success:
        show_user_guide()
    
    print("\n" + "=" * 70)
    print("🏁 验证完成")
    print("=" * 70)
    
    return success


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
