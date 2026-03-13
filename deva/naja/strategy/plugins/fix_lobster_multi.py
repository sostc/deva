"""
修复龙虾思想雷达策略，添加多数据源支持
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB
import time
import hashlib


def fix_lobster_strategy():
    """修复龙虾思想雷达策略，添加多数据源支持"""
    
    # 打开策略表
    db = NB('naja_strategies')
    
    # 查找龙虾思想雷达策略
    strategy_key = None
    strategy_data = None
    
    for key, value in db.items():
        if isinstance(value, dict):
            name = value.get('metadata', {}).get('name', '')
            if name == '龙虾思想雷达':
                strategy_key = key
                strategy_data = value
                break
    
    if not strategy_key:
        print('[ERROR] 未找到龙虾思想雷达策略')
        return False
    
    print(f'[INFO] 找到策略: {strategy_key}')
    print()
    
    # 获取当前绑定的数据源
    current_ds_id = strategy_data.get('metadata', {}).get('bound_datasource_id', '')
    print(f'当前绑定数据源: {current_ds_id}')
    
    # 查找所有可用的数据源
    ds_db = NB('naja_datasources')
    available_ds = []
    
    print()
    print('可用的数据源:')
    for ds_key, ds_value in ds_db.items():
        if isinstance(ds_value, dict):
            ds_name = ds_value.get('metadata', {}).get('name', '未知')
            ds_type = ds_value.get('metadata', {}).get('source_type', 'unknown')
            print(f'  - {ds_name} (ID: {ds_key}, 类型: {ds_type})')
            
            # 收集行情相关的数据源
            if any(keyword in ds_name.lower() for keyword in ['tick', '行情', 'market', 'replay', '回放']):
                available_ds.append((ds_key, ds_name))
    
    if len(available_ds) < 2:
        print()
        print('[WARN] 可用的行情数据源不足2个，无法创建多数据源绑定')
        print('[INFO] 当前策略保持单数据源绑定')
        return False
    
    # 选择前两个数据源进行绑定
    selected_ds = available_ds[:2]
    selected_ds_ids = [ds[0] for ds in selected_ds]
    
    print()
    print('将绑定的数据源:')
    for i, (ds_id, ds_name) in enumerate(selected_ds, 1):
        print(f'  {i}. {ds_name} (ID: {ds_id})')
    
    # 更新策略数据
    print()
    print('[INFO] 更新策略数据...')
    
    # 更新单数据源字段（兼容）
    strategy_data['metadata']['bound_datasource_id'] = selected_ds_ids[0]
    
    # 添加多数据源字段
    strategy_data['metadata']['bound_datasource_ids'] = selected_ds_ids
    strategy_data['metadata']['updated_at'] = time.time()
    
    # 保存回数据库
    db[strategy_key] = strategy_data
    
    print('[SUCCESS] 策略已更新')
    print()
    print('更新后的策略信息:')
    print(f'  名称: {strategy_data["metadata"]["name"]}')
    print(f'  单数据源: {strategy_data["metadata"]["bound_datasource_id"]}')
    print(f'  多数据源: {strategy_data["metadata"].get("bound_datasource_ids", [])}')
    print(f'  数据源数量: {len(selected_ds_ids)}')
    
    return True


def verify_strategy():
    """验证策略数据"""
    print()
    print('=' * 60)
    print('验证策略数据')
    print('=' * 60)
    print()
    
    db = NB('naja_strategies')
    
    for key, value in db.items():
        if isinstance(value, dict):
            name = value.get('metadata', {}).get('name', '')
            if name == '龙虾思想雷达':
                print(f'策略: {name}')
                print(f'ID: {key}')
                print()
                
                single_ds = value.get('metadata', {}).get('bound_datasource_id', '')
                multi_ds = value.get('metadata', {}).get('bound_datasource_ids', [])
                
                print(f'单数据源字段: {single_ds}')
                print(f'多数据源字段: {multi_ds}')
                print(f'数据源数量: {len(multi_ds) if multi_ds else (1 if single_ds else 0)}')
                
                if multi_ds:
                    print()
                    print('绑定的数据源:')
                    for i, ds_id in enumerate(multi_ds, 1):
                        print(f'  {i}. {ds_id}')
                
                return True
    
    print('[ERROR] 未找到策略')
    return False


def main():
    """主函数"""
    print('=' * 60)
    print('修复龙虾思想雷达策略 - 添加多数据源支持')
    print('=' * 60)
    print()
    
    if fix_lobster_strategy():
        print()
        verify_strategy()
        print()
        print('=' * 60)
        print('✅ 修复完成')
        print('=' * 60)
        print()
        print('请重启naja以应用更改:')
        print('  1. 停止当前naja进程')
        print('  2. 重新启动: python -m deva.naja')
        print('  3. 访问 http://localhost:8080/strategyadmin 查看效果')
    else:
        print()
        print('=' * 60)
        print('❌ 修复失败')
        print('=' * 60)


if __name__ == '__main__':
    main()
