#!/usr/bin/env python3
"""
清理 admin_ui 下面 v1 和 v2 版本的数据源、策略、数据字典所有数据表
"""

from deva import NB

# 数据源相关表（v1）
DATA_SOURCE_V1_TABLES = [
    "data_sources",
    "data_source_latest_data",
    "data_source_type_instances",
    "data_source_code_versions"
]

# 数据源相关表（v2）
DATA_SOURCE_V2_TABLES = [
    "data_sources_v2",
    "ds_v2_latest_data",
    "ds_v2_code_versions"
]

# 策略相关表（v1）
STRATEGY_V1_TABLES = [
    "strategy_units",
    "strategy_results",
    "strategy_logic"
]

# 策略相关表（v2）
STRATEGY_V2_TABLES = [
    "strategies_v2",
    "strategy_v2_results"
]

# 数据字典相关表（v2）
DICTIONARY_V2_TABLES = [
    "dictionary_entries_v2",
    "dictionary_payloads_v2"
]

# 所有需要清理的表
ALL_TABLES = (
    DATA_SOURCE_V1_TABLES +
    DATA_SOURCE_V2_TABLES +
    STRATEGY_V1_TABLES +
    STRATEGY_V2_TABLES +
    DICTIONARY_V2_TABLES
)

def clear_table(table_name):
    """清理指定表的所有数据"""
    try:
        db = NB(table_name)
        # 清空表
        for key in list(db.keys()):
            del db[key]
        print(f"✅ 清理表 {table_name} 成功")
        return True
    except Exception as e:
        print(f"❌ 清理表 {table_name} 失败: {str(e)}")
        return False

def main():
    print("开始清理 admin_ui 相关数据表...")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    for table in ALL_TABLES:
        if clear_table(table):
            success_count += 1
        else:
            failed_count += 1
    
    print("=" * 60)
    print(f"清理完成: 成功 {success_count} 个表, 失败 {failed_count} 个表")
    print("所有 v1 和 v2 版本的数据源、策略、数据字典表已清理完毕")

if __name__ == "__main__":
    main()
