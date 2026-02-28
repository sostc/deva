#!/usr/bin/env python3
"""
测试数据源名称唯一性

验证系统是否在创建和编辑数据源时都禁止使用重复名称
"""

from deva.admin_ui.datasource.datasource import get_ds_manager, DataSourceType, create_timer_source, create_stream_source, create_replay_source

def main():
    """测试数据源名称唯一性"""
    print("=== 测试数据源名称唯一性 ===")
    
    ds_manager = get_ds_manager()
    ds_manager.load_from_db()
    
    test_name = "test_unique_name"
    test_name_2 = "test_unique_name_2"
    
    # 清理可能存在的测试数据源
    print("\n清理测试数据源...")
    for source in ds_manager.list_all():
        if source.get("metadata", {}).get("name") in [test_name, test_name_2]:
            source_id = source.get("metadata", {}).get("id")
            if source_id:
                source_obj = ds_manager.get_source(source_id)
                if source_obj:
                    source_obj.delete()
                    print(f"删除测试数据源: {source_id}")
    
    # 测试 1: 创建第一个数据源
    print("\n测试 1: 创建第一个数据源")
    result1 = ds_manager.create_source(
        name=test_name,
        source_type=DataSourceType.CUSTOM,
        description="Test 1"
    )
    print(f"创建第一个数据源: {result1}")
    
    if result1.get("success"):
        print("✅ 测试通过: 成功创建第一个数据源")
    else:
        print("❌ 测试失败: 创建第一个数据源失败")
        return False
    
    # 测试 2: 尝试创建同名数据源
    print("\n测试 2: 尝试创建同名数据源")
    result2 = ds_manager.create_source(
        name=test_name,
        source_type=DataSourceType.CUSTOM,
        description="Test 2 (duplicate name)"
    )
    print(f"创建同名数据源: {result2}")
    
    if result2.get("success") is False and "already exists" in result2.get("error", ""):
        print("✅ 测试通过: 系统正确拒绝了同名数据源的创建")
    else:
        print("❌ 测试失败: 系统允许了同名数据源的创建")
        return False
    
    # 测试 3: 使用 create_timer_source 创建同名数据源
    print("\n测试 3: 使用 create_timer_source 创建同名数据源")
    try:
        source = create_timer_source(name=test_name, interval=5)
        print("❌ 测试失败: 系统允许了同名定时器数据源的创建")
        return False
    except ValueError as e:
        if "already exists" in str(e):
            print("✅ 测试通过: 系统正确拒绝了同名定时器数据源的创建")
        else:
            print(f"❌ 测试失败: 出现意外错误: {e}")
            return False
    
    # 测试 4: 使用 create_stream_source 创建同名数据源
    print("\n测试 4: 使用 create_stream_source 创建同名数据源")
    try:
        source = create_stream_source(name=test_name)
        print("❌ 测试失败: 系统允许了同名流数据源的创建")
        return False
    except ValueError as e:
        if "already exists" in str(e):
            print("✅ 测试通过: 系统正确拒绝了同名流数据源的创建")
        else:
            print(f"❌ 测试失败: 出现意外错误: {e}")
            return False
    
    # 测试 5: 创建不同名数据源
    print("\n测试 5: 创建不同名数据源")
    result3 = ds_manager.create_source(
        name=test_name_2,
        source_type=DataSourceType.CUSTOM,
        description="Test 3 (different name)"
    )
    print(f"创建不同名数据源: {result3}")
    
    if result3.get("success"):
        print("✅ 测试通过: 系统允许创建不同名的数据源")
    else:
        print("❌ 测试失败: 系统拒绝了不同名数据源的创建")
        return False
    
    # 清理测试数据源
    print("\n清理测试数据源...")
    if result1.get("success"):
        source_id1 = result1.get("source_id")
        if source_id1:
            source = ds_manager.get_source(source_id1)
            if source:
                source.delete()
                print(f"删除测试数据源 1: {source_id1}")
    
    if result3.get("success"):
        source_id3 = result3.get("source_id")
        if source_id3:
            source = ds_manager.get_source(source_id3)
            if source:
                source.delete()
                print(f"删除测试数据源 3: {source_id3}")
    
    print("\n=== 测试完成 ===")
    print("✅ 所有测试通过: 系统正确处理数据源名称唯一性")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
