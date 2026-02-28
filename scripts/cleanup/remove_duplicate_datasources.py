#!/usr/bin/env python3
"""
删除数据库中重复名称的数据源

对于每个重复名称的数据源组，只保留一个，删除其余的
"""

from deva import NB
import time

def main():
    """删除重复名称的数据源"""
    print("=== 开始删除重复名称的数据源 ===")
    
    # 1. 获取所有数据源
    data_sources_db = NB("data_sources")
    all_sources = list(data_sources_db.items())
    print(f"找到 {len(all_sources)} 个数据源")
    
    # 2. 按名称分组
    sources_by_name = {}
    for source_id, source_data in all_sources:
        if isinstance(source_data, dict):
            name = source_data.get("metadata", {}).get("name", "Unknown")
            if name not in sources_by_name:
                sources_by_name[name] = []
            sources_by_name[name].append((source_id, source_data))
    
    print(f"\n数据源名称分组: {len(sources_by_name)} 个不同名称")
    
    # 3. 处理重复名称
    deleted_count = 0
    for name, sources in sources_by_name.items():
        if len(sources) > 1:
            print(f"\n处理重复名称: {name} (共 {len(sources)} 个数据源)")
            
            # 按更新时间排序，保留最新的一个
            sources.sort(key=lambda x: x[1].get("metadata", {}).get("updated_at", 0), reverse=True)
            
            # 保留第一个（最新的），删除其余的
            for i, (source_id, source_data) in enumerate(sources):
                if i == 0:
                    print(f"  ✅ 保留: {source_id} (最新更新)")
                else:
                    print(f"  ❌ 删除: {source_id}")
                    
                    # 删除数据源主记录
                    if source_id in data_sources_db:
                        del data_sources_db[source_id]
                    
                    # 删除相关的最新数据记录
                    try:
                        data_db = NB("data_source_latest_data")
                        data_key = f"{source_id}_latest_data"
                        if data_key in data_db:
                            del data_db[data_key]
                    except Exception as e:
                        print(f"    - 删除最新数据记录失败: {e}")
                    
                    # 删除相关的代码版本记录
                    try:
                        version_db = NB("data_source_code_versions")
                        keys_to_delete = []
                        for key in version_db.keys():
                            if key.startswith(f"{source_id}_code_"):
                                keys_to_delete.append(key)
                        for key in keys_to_delete:
                            if key in version_db:
                                del version_db[key]
                    except Exception as e:
                        print(f"    - 删除代码版本记录失败: {e}")
                    
                    deleted_count += 1
    
    # 4. 总结
    print("\n=== 删除完成 ===")
    print(f"共删除 {deleted_count} 个重复名称的数据源")
    
    # 5. 验证结果
    remaining_sources = list(data_sources_db.items())
    print(f"\n剩余数据源: {len(remaining_sources)} 个")
    
    # 检查是否还有重复名称
    remaining_names = {}
    for source_id, source_data in remaining_sources:
        if isinstance(source_data, dict):
            name = source_data.get("metadata", {}).get("name", "Unknown")
            if name not in remaining_names:
                remaining_names[name] = []
            remaining_names[name].append(source_id)
    
    print(f"剩余数据源名称: {len(remaining_names)} 个不同名称")
    
    # 检查是否还有重复
    has_duplicates = any(len(ids) > 1 for ids in remaining_names.values())
    if has_duplicates:
        print("\n⚠️  仍然存在重复名称:")
        for name, ids in remaining_names.items():
            if len(ids) > 1:
                print(f"  - {name}: {len(ids)} 个数据源")
    else:
        print("\n✅ 所有重复名称已删除，每个名称只保留一个数据源")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
