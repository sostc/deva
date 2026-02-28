#!/usr/bin/env python3
"""
测试数据源名称唯一性

验证系统是否禁止创建同名的数据源
"""

from deva.admin_ui.datasource.datasource import get_ds_manager, DataSourceType

def main():
    """测试数据源名称唯一性"""
    print("=== 测试数据源名称唯一性 ===")
    
    ds_manager = get_ds_manager()
    ds_manager.load_from_db()
    
    # 测试 1: 尝试创建两个同名的数据源
    print("\n测试 1: 尝试创建两个同名的数据源")
    
    # 第一个数据源
    result1 = ds_manager.create_source(
        name="test_duplicate",
        source_type=DataSourceType.CUSTOM,
        description="Test duplicate name 1"
    )
    print(f"创建第一个数据源: {result1}")
    
    # 第二个数据源（同名）
    result2 = ds_manager.create_source(
        name="test_duplicate",
        source_type=DataSourceType.CUSTOM,
        description="Test duplicate name 2"
    )
    print(f"创建第二个数据源（同名）: {result2}")
    
    if result2.get("success") is False and "already exists" in result2.get("error", ""):
        print("✅ 测试通过: 系统正确拒绝了同名数据源的创建")
    else:
        print("❌ 测试失败: 系统允许了同名数据源的创建")
    
    # 测试 2: 尝试创建不同名的数据源
    print("\n测试 2: 尝试创建不同名的数据源")
    result3 = ds_manager.create_source(
        name="test_unique",
        source_type=DataSourceType.CUSTOM,
        description="Test unique name"
    )
    print(f"创建不同名数据源: {result3}")
    
    if result3.get("success") is True:
        print("✅ 测试通过: 系统允许创建不同名的数据源")
    else:
        print("❌ 测试失败: 系统拒绝了不同名数据源的创建")
    
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
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
