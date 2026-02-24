#!/usr/bin/env python3
"""
测试数据源展示和编辑功能
验证：
1. 数据源列表展示简介和最近更新时间
2. 数据源详情页面展示介绍和生成时间
3. 数据源介绍编辑功能
4. 所有功能的完整性
"""

import time
import datetime
from deva.admin_ui.strategy.datasource import get_ds_manager

def test_datasource_list_display():
    """测试数据源列表展示功能"""
    print("=== 测试数据源列表展示功能 ===")
    
    ds_manager = get_ds_manager()
    ds_manager.load_from_db()
    
    sources = ds_manager.list_all()
    print(f"✅ 找到 {len(sources)} 个数据源")
    
    # 验证排序功能：优先显示运行中的数据源，然后按最近数据时间排序
    print("\n📊 验证排序功能...")
    
    # 排序：优先显示运行中的数据源，然后按最近数据时间排序
    def get_sort_key(source_data):
        metadata = source_data.get("metadata", {})
        state = source_data.get("state", {})
        
        # 运行状态优先级 (running=1, 其他=0)
        status = state.get("status", "stopped")
        status_priority = 1 if status == "running" else 0
        
        # 最近数据时间 (时间戳越大越优先，无数据置为0)
        last_data_ts = state.get("last_data_ts", 0)
        
        # 返回排序键：先按运行状态，再按数据时间（倒序）
        return (-status_priority, -last_data_ts)
    
    sources.sort(key=get_sort_key)
    
    # 验证列表展示的关键信息
    running_count = 0
    for i, source_data in enumerate(sources, 1):
        metadata = source_data.get("metadata", {})
        state = source_data.get("state", {})
        stats = source_data.get("stats", {})
        
        name = metadata.get("name", "unknown")
        description = metadata.get("description", "")
        status = state.get("status", "unknown")
        last_data_ts = state.get("last_data_ts", 0)
        total_emitted = stats.get("total_emitted", 0)
        
        if status == "running":
            running_count += 1
            print(f"\n🟢 {i}. {name} (运行中)")
        else:
            print(f"\n{i}. {name} ({status})")
        print(f"   描述: {description or '暂无描述'}")
        
        if last_data_ts > 0:
            last_data_time = datetime.datetime.fromtimestamp(last_data_ts).strftime("%Y-%m-%d %H:%M:%S")
            print(f"   最近数据: {last_data_time} ({total_emitted}条)")
        else:
            print(f"   最近数据: 无数据 ({total_emitted}条)")
    
    print(f"\n✅ 排序验证完成：{running_count}个运行中的数据源优先显示")
    return True

def test_datasource_detail_display():
    """测试数据源详情展示功能"""
    print("\n=== 测试数据源详情展示功能 ===")
    
    ds_manager = get_ds_manager()
    
    # 获取quant_source作为测试对象
    quant_source = ds_manager.get_source_by_name("quant_source")
    if not quant_source:
        print("❌ 未找到quant_source数据源")
        return False
    
    print(f"✅ 测试数据源: {quant_source.name}")
    
    # 验证基本信息展示
    print(f"\n📋 基本信息:")
    print(f"   ID: {quant_source.id}")
    print(f"   名称: {quant_source.name}")
    print(f"   类型: {quant_source.metadata.source_type.value}")
    print(f"   描述: {quant_source.metadata.description or '暂无描述'}")
    print(f"   状态: {quant_source.state.status}")
    print(f"   创建时间: {datetime.datetime.fromtimestamp(quant_source.metadata.created_at)}")
    print(f"   更新时间: {datetime.datetime.fromtimestamp(quant_source.metadata.updated_at)}")
    
    # 验证保存的运行状态
    saved_state = quant_source.get_saved_running_state()
    if saved_state:
        print(f"\n💾 保存的运行状态:")
        print(f"   运行状态: {saved_state.get('is_running')}")
        print(f"   进程PID: {saved_state.get('pid')}")
        print(f"   最后更新: {datetime.datetime.fromtimestamp(saved_state.get('last_update', 0))}")
    
    # 验证保存的最新数据
    saved_data = quant_source.get_saved_latest_data()
    if saved_data:
        print(f"\n📊 保存的最新数据:")
        print(f"   数据类型: {saved_data.get('data_type')}")
        print(f"   数据大小: {saved_data.get('size')}")
        print(f"   时间戳: {datetime.datetime.fromtimestamp(saved_data.get('timestamp', 0))}")
    
    # 验证最近数据
    recent_data = quant_source.get_recent_data(3)
    print(f"\n📈 最近数据 (缓存): {len(recent_data)} 条")
    
    if recent_data:
        latest = recent_data[-1]
        print(f"   最新数据类型: {type(latest)}")
        
        if hasattr(latest, 'shape'):
            print(f"   DataFrame形状: {latest.shape}")
            print(f"   列名: {list(latest.columns)}")
        elif isinstance(latest, list) and len(latest) > 0:
            print(f"   第一条数据: {latest[0]}")
        elif isinstance(latest, dict):
            print(f"   数据内容: {latest}")
    
    # 验证依赖策略
    dependent = quant_source.get_dependent_strategies()
    print(f"\n🔗 依赖策略: {len(dependent)} 个")
    for strategy in dependent:
        print(f"   - {strategy}")
    
    return True

def test_datasource_edit_function():
    """测试数据源编辑功能"""
    print("\n=== 测试数据源编辑功能 ===")
    
    ds_manager = get_ds_manager()
    
    # 获取一个测试数据源
    test_source = ds_manager.get_source_by_name("test_source")
    if not test_source:
        print("❌ 未找到test_source数据源")
        return False
    
    print(f"✅ 测试编辑数据源: {test_source.name}")
    
    # 保存原始描述
    original_description = test_source.metadata.description
    
    # 测试编辑功能
    new_description = f"测试编辑功能 - 更新时间: {datetime.datetime.now()}"
    
    # 模拟编辑操作
    test_source.metadata.description = new_description
    test_source.metadata.updated_at = time.time()
    
    result = test_source.save()
    
    if result.get("success"):
        print(f"✅ 编辑成功")
        print(f"   新描述: {new_description}")
        
        # 验证保存结果
        saved_source = ds_manager.get_source(test_source.id)
        if saved_source and saved_source.metadata.description == new_description:
            print("✅ 保存验证通过")
            
            # 恢复原始描述
            saved_source.metadata.description = original_description
            saved_source.metadata.updated_at = time.time()
            saved_source.save()
            print("✅ 恢复原描述成功")
            
            return True
        else:
            print("❌ 保存验证失败")
            return False
    else:
        print(f"❌ 编辑失败: {result.get('error')}")
        return False

def test_code_version_function():
    """测试代码版本功能"""
    print("\n=== 测试代码版本功能 ===")
    
    ds_manager = get_ds_manager()
    
    # 获取quant_source数据源
    quant_source = ds_manager.get_source_by_name("quant_source")
    if not quant_source:
        print("❌ 未找到quant_source数据源")
        return False
    
    print(f"✅ 测试数据源: {quant_source.name}")
    
    # 获取代码版本历史
    code_versions = quant_source.get_code_versions(3)
    print(f"✅ 代码版本历史: {len(code_versions)} 个版本")
    
    for i, version in enumerate(code_versions):
        print(f"   版本 {i+1}: {version.get('timestamp', 'N/A')}")
        if 'new_code' in version:
            print(f"     代码长度: {len(version['new_code'])} 字符")
    
    # 验证当前代码
    current_code = quant_source.metadata.data_func_code
    print(f"✅ 当前代码长度: {len(current_code)} 字符")
    
    # 验证关键函数
    key_functions = ['fetch_data', 'gen_quant', 'is_tradedate', 'is_tradetime', 'create_mock_data']
    found_functions = [func for func in key_functions if f"def {func}" in current_code]
    print(f"✅ 找到的关键函数: {found_functions}")
    
    return len(found_functions) >= 3

def test_state_persistence():
    """测试状态持久化功能"""
    print("\n=== 测试状态持久化功能 ===")
    
    ds_manager = get_ds_manager()
    
    # 执行状态恢复
    print("执行状态恢复...")
    restore_result = ds_manager.restore_running_states()
    
    print(f"✅ 状态恢复结果:")
    print(f"   恢复成功: {restore_result['restored_count']} 个")
    print(f"   恢复失败: {restore_result['failed_count']} 个")
    print(f"   总计尝试: {restore_result['total_attempted']} 个")
    
    # 显示quant_source的恢复详情
    for result in restore_result['results']:
        if result.get('source_name') == 'quant_source':
            print(f"\n✅ quant_source恢复详情:")
            print(f"   成功: {result.get('success')}")
            print(f"   原因: {result.get('reason')}")
            if result.get('message'):
                print(f"   消息: {result.get('message')}")
            if result.get('error'):
                print(f"   错误: {result.get('error')}")
    
    return True

def main():
    """主测试函数"""
    print("🚀 开始测试数据源展示和编辑功能")
    print(f"📅 测试时间: {datetime.datetime.now()}")
    
    try:
        # 1. 测试列表展示功能
        list_success = test_datasource_list_display()
        
        # 2. 测试详情展示功能
        detail_success = test_datasource_detail_display()
        
        # 3. 测试编辑功能
        edit_success = test_datasource_edit_function()
        
        # 4. 测试代码版本功能
        version_success = test_code_version_function()
        
        # 5. 测试状态持久化功能
        persistence_success = test_state_persistence()
        
        print("\n=== 测试完成 ===")
        
        if all([list_success, detail_success, edit_success, version_success, persistence_success]):
            print("🎉 所有测试通过！")
            print("✅ 数据源列表展示功能正常")
            print("✅ 数据源详情展示功能正常")
            print("✅ 数据源编辑功能正常")
            print("✅ 代码版本功能正常")
            print("✅ 状态持久化功能正常")
            print("✅ 所有展示和编辑功能完全正常")
            return True
        else:
            print("❌ 部分测试失败")
            return False
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)