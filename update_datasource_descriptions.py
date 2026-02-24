#!/usr/bin/env python3
"""
为现有数据源补齐介绍信息
"""

from deva.admin_ui.strategy.datasource import get_ds_manager

def update_datasource_descriptions():
    """为数据源更新描述信息"""
    print("📝 开始为数据源补齐介绍信息...")
    
    ds_manager = get_ds_manager()
    ds_manager.load_from_db()
    
    # 数据源描述映射
    descriptions = {
        "error_test_source": "用于测试错误处理机制的数据源，模拟各种异常情况",
        "trading_time_test": "交易时间判断测试数据源，验证交易日和交易时间逻辑",
        "quant_source_test": "行情数据测试数据源，用于验证股票行情数据获取功能",
        "working_quant_source": "可工作的行情数据源，包含完整的行情获取和降级机制",
        "simple_quant_source": "简化版行情数据源，用于基础功能测试",
        "imported_test_source": "通过状态导入创建的测试数据源",
        "test_db_import": "数据库导入测试数据源，验证状态持久化功能",
        "test_always_run": "总是运行的测试数据源，忽略交易时间限制",
        "quant_source": "主行情数据源，定时从新浪获取A股实时行情数据，支持自动降级",
        "test_source": "基础测试数据源，用于功能验证和开发测试"
    }
    
    updated_count = 0
    skipped_count = 0
    
    # 获取所有数据源
    sources = ds_manager.list_all()
    
    for source_data in sources:
        metadata = source_data.get("metadata", {})
        source_id = metadata.get("id")
        name = metadata.get("name", "")
        current_description = metadata.get("description", "")
        
        if not source_id:
            continue
            
        # 获取数据源对象
        source = ds_manager.get_source(source_id)
        if not source:
            print(f"⚠️  找不到数据源: {name} ({source_id})")
            continue
        
        # 检查是否需要更新描述
        if current_description and current_description != "":
            print(f"✅ {name}: 已有描述，跳过")
            skipped_count += 1
            continue
        
        # 获取新描述
        new_description = descriptions.get(name, "")
        if not new_description:
            # 生成默认描述
            source_type = metadata.get("source_type", "unknown")
            interval = metadata.get("interval", 0)
            
            if source_type == "timer":
                new_description = f"定时数据源，每{interval}秒执行一次数据获取"
            elif source_type == "stream":
                new_description = "命名流数据源，消费现有的数据流"
            else:
                new_description = f"{source_type}类型数据源"
        
        # 更新描述
        source.metadata.description = new_description
        source.metadata.updated_at = time.time()
        
        result = source.save()
        if result.get("success"):
            print(f"✅ {name}: 描述已更新")
            print(f"   新描述: {new_description}")
            updated_count += 1
        else:
            print(f"❌ {name}: 更新失败 - {result.get('error')}")
    
    print(f"\n📊 更新完成:")
    print(f"   已更新: {updated_count} 个数据源")
    print(f"   已跳过: {skipped_count} 个数据源")
    print(f"   总计: {len(sources)} 个数据源")
    
    return updated_count

def verify_updates():
    """验证更新结果"""
    print("\n🔍 验证更新结果...")
    
    ds_manager = get_ds_manager()
    ds_manager.load_from_db()
    
    sources = ds_manager.list_all()
    
    print("📋 当前数据源描述状态:")
    for i, source_data in enumerate(sources, 1):
        metadata = source_data.get("metadata", {})
        name = metadata.get("name", "unknown")
        description = metadata.get("description", "")
        
        status = "✅" if description else "⚠️"
        desc_preview = description[:60] + "..." if len(description) > 60 else description
        
        print(f"{i:2d}. {status} {name}")
        if description:
            print(f"     描述: {desc_preview}")
        print()

def main():
    """主函数"""
    try:
        # 执行更新
        updated = update_datasource_descriptions()
        
        # 验证结果
        verify_updates()
        
        print("🎉 数据源描述更新完成！")
        return True
        
    except Exception as e:
        print(f"❌ 更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import time
    success = main()
    exit(0 if success else 1)