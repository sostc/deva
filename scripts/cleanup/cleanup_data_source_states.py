#!/usr/bin/env python3
"""
清理data_source_states表中的所有记录

由于数据源状态已合并到data_sources表中，
该脚本会清理data_source_states表中的所有记录，因为它们已经不再需要了。
"""

import sys

# 添加项目根目录到Python路径
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB

def main() -> bool:
    """清理data_source_states表中的所有记录"""
    print("=== 开始清理data_source_states表 ===")
    
    try:
        # 获取所有状态记录
        state_db = NB("data_source_states")
        state_keys = list(state_db.keys())
        
        print(f"✓ 从data_source_states表中获取到 {len(state_keys)} 个状态记录")
        
        # 执行删除操作
        deleted_count = 0
        
        for state_key in state_keys:
            try:
                if state_key in state_db:
                    del state_db[state_key]
                    deleted_count += 1
                    print(f"  - 删除状态记录: {state_key}")
            except Exception as e:
                print(f"  - 删除状态记录失败 {state_key}: {e}")
        
        # 总结
        print("\n=== 清理完成 ===")
        print(f"共检查 {len(state_keys)} 个状态记录")
        print(f"删除 {deleted_count} 个状态记录")
        
        # 验证结果
        remaining_state_keys = list(state_db.keys())
        print(f"剩余 {len(remaining_state_keys)} 个状态记录")
        
        if remaining_state_keys:
            print(f"⚠️  仍然存在 {len(remaining_state_keys)} 个记录")
            for state_key in remaining_state_keys[:5]:  # 只显示前5个
                print(f"  - {state_key}")
            if len(remaining_state_keys) > 5:
                print(f"  ... 还有 {len(remaining_state_keys) - 5} 个记录")
            return False
        else:
            print("✅ 所有状态记录都已删除")
            print("\n注意: 数据源状态现在存储在data_sources表的state字段中")
            return True
            
    except Exception as e:
        print(f"❌ 清理过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
