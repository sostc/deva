#!/usr/bin/env python3
"""
分析数据源显示问题

检查数据库中的数据源数量、状态和结构，分析为什么有些数据源可能没有显示出来
"""

from deva import NB

def main():
    """分析数据源显示问题"""
    print("=== 分析数据源显示问题 ===")
    
    # 1. 检查 data_sources 表
    print("\n=== 检查 data_sources 表 ===")
    data_sources_db = NB("data_sources")
    all_sources = list(data_sources_db.items())
    print(f"data_sources 表中有 {len(all_sources)} 条记录")
    
    # 3. 分析数据源结构
    print("\n=== 分析数据源结构 ===")
    valid_sources = []
    invalid_sources = []
    
    for source_id, source_data in all_sources:
        print(f"\n检查数据源: {source_id}")
        
        # 检查数据类型
        if not isinstance(source_data, dict):
            print(f"  ❌ 数据类型错误: {type(source_data)}")
            invalid_sources.append((source_id, "数据类型错误"))
            continue
        
        # 检查必要字段
        required_fields = ["metadata", "state", "stats"]
        missing_fields = []
        for field in required_fields:
            if field not in source_data:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"  ❌ 缺少字段: {missing_fields}")
            invalid_sources.append((source_id, f"缺少字段: {missing_fields}"))
            continue
        
        # 检查 metadata 结构
        metadata = source_data.get("metadata", {})
        if not isinstance(metadata, dict):
            print(f"  ❌ metadata 不是字典类型")
            invalid_sources.append((source_id, "metadata 结构错误"))
            continue
        
        # 检查 name 字段
        name = metadata.get("name", "")
        if not name:
            print(f"  ⚠️  缺少名称")
        else:
            print(f"  ✅ 名称: {name}")
        
        # 检查 state 结构
        state = source_data.get("state", {})
        if not isinstance(state, dict):
            print(f"  ❌ state 不是字典类型")
            invalid_sources.append((source_id, "state 结构错误"))
            continue
        
        # 检查 status 字段
        status = state.get("status", "")
        print(f"  状态: {status}")
        
        # 检查运行状态
        is_running = state.get("is_running", False)
        print(f"  运行状态: {is_running}")
        
        # 检查最后更新时间
        last_update = state.get("last_update", 0)
        if last_update > 0:
            print(f"  最后更新: {last_update}")
        
        valid_sources.append((source_id, name, status, is_running))
    
    # 4. 总结
    print("\n=== 分析总结 ===")
    print(f"总数据源数量: {len(all_sources)}")
    print(f"有效数据源: {len(valid_sources)}")
    print(f"无效数据源: {len(invalid_sources)}")
    
    if invalid_sources:
        print("\n无效数据源列表:")
        for source_id, reason in invalid_sources:
            print(f"  - {source_id}: {reason}")
    
    print("\n有效数据源状态分布:")
    status_count = {}
    for _, _, status, _ in valid_sources:
        status_count[status] = status_count.get(status, 0) + 1
    
    for status, count in status_count.items():
        print(f"  - {status}: {count} 个")
    
    print("\n有效数据源运行状态分布:")
    running_count = {}
    for _, _, _, is_running in valid_sources:
        running_count[str(is_running)] = running_count.get(str(is_running), 0) + 1
    
    for is_running, count in running_count.items():
        print(f"  - 运行中: {is_running}: {count} 个")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
