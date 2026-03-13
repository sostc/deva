#!/usr/bin/env python3
"""
创建一个策略，绑定realtime_tick_5s数据源，每五分钟存储数据到quant_snapshot_5min_window表
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time
import hashlib
from deva import NB

def generate_strategy_id(name: str) -> str:
    """生成策略唯一ID"""
    return hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

def create_quant_snapshot_strategy():
    """创建量化快照策略"""
    print("📋 创建量化快照策略...")
    
    # 连接策略数据库
    db = NB('naja_strategies')
    
    # 策略配置
    strategy_name = "量化快照5分钟策略"
    strategy_id = generate_strategy_id(strategy_name)
    
    # 查找realtime_tick_5s数据源ID
    ds_db = NB('naja_datasources')
    realtime_tick_5s_id = None
    for ds_id, ds_data in ds_db.items():
        if isinstance(ds_data, dict):
            metadata = ds_data.get('metadata', {})
            name = metadata.get('name', '')
            if name == 'realtime_tick_5s':
                realtime_tick_5s_id = ds_id
                print(f"   🔍 找到realtime_tick_5s数据源: {ds_id}")
                break
    
    if not realtime_tick_5s_id:
        print("❌ 未找到realtime_tick_5s数据源")
        return False
    
    # 策略代码
    strategy_code = '''
"""
量化快照5分钟策略
每五分钟存储realtime_tick_5s数据源的数据到quant_snapshot_5min_window表
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time
import pandas as pd
from datetime import datetime
from deva import NS, NB

def process(record):
    """处理数据"""
    # 获取数据源数据
    data = record.get('data', None)
    
    if data is None:
        return {"success": False, "message": "No data received"}
    
    try:
        # 确保数据是DataFrame格式
        if isinstance(data, pd.DataFrame):
            df = data
        else:
            return {"success": False, "message": "Data is not DataFrame"}
        
        # 确保code列存在
        if 'code' not in df.columns:
            df['code'] = df.index
        
        # 添加时间戳
        timestamp = time.time()
        df['timestamp'] = timestamp
        df['datetime'] = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        # 存储到quant_snapshot_5min_window表
        db = NB('quant_snapshot_5min_window')
        
        # 生成唯一键
        key = f"snapshot_{int(timestamp)}"
        
        # 存储数据
        db[key] = {
            'timestamp': timestamp,
            'datetime': df['datetime'].iloc[0] if len(df) > 0 else None,
            'data': df.to_dict('records'),
            'record_count': len(df),
            'created_at': time.time()
        }
        
        print(f"✅ 成功存储量化快照数据: {len(df)} 条记录")
        
        return {
            "success": True,
            "message": f"Stored {len(df)} records to quant_snapshot_5min_window",
            "record_count": len(df)
        }
        
    except Exception as e:
        print(f"❌ 存储数据失败: {str(e)}")
        return {"success": False, "message": str(e)}


def initialize():
    """初始化策略"""
    print("🔄 初始化量化快照策略")
    # 确保表存在
    db = NB('quant_snapshot_5min_window')
    print("✅ 策略初始化完成")
    return {"success": True}


def cleanup():
    """清理策略"""
    print("🧹 清理量化快照策略")
    return {"success": True}
'''
    
    # 创建策略记录
    strategy_record = {
        "metadata": {
            "id": strategy_id,
            "name": strategy_name,
            "description": "每五分钟存储realtime_tick_5s数据源的数据到quant_snapshot_5min_window表",
            "category": "量化分析",
            "bound_datasource_id": realtime_tick_5s_id,
            "created_at": time.time(),
            "updated_at": time.time(),
            "config": {
                "window_size": 5,
                "window_interval": "5m",
                "max_history": 1000
            }
        },
        "func_code": strategy_code,
        "state": {
            "status": "stopped",
            "last_executed": None,
            "last_success": None,
            "last_error": None,
            "execution_count": 0,
            "success_count": 0,
            "error_count": 0,
            "runtime": 0
        }
    }
    
    # 保存到数据库
    print(f"💾 保存策略到数据库...")
    db[strategy_id] = strategy_record
    print(f"✅ 策略已保存 (ID: {strategy_id})")
    
    # 验证保存
    print(f"🔍 验证策略保存...")
    if strategy_id in db:
        saved_strategy = db[strategy_id]
        print(f"   ✅ 策略验证成功")
        print(f"   名称: {saved_strategy['metadata']['name']}")
        print(f"   绑定数据源: {saved_strategy['metadata']['bound_datasource_id']}")
        print(f"   状态: {saved_strategy['state']['status']}")
    else:
        print("   ❌ 策略验证失败")
        return False
    
    return True

def main():
    """主函数"""
    print("=" * 60)
    print("创建量化快照5分钟策略")
    print("=" * 60)
    print()
    
    # 创建策略
    success = create_quant_snapshot_strategy()
    
    if success:
        print("\n✅ 任务完成！")
        print("量化快照5分钟策略已成功创建")
        print("策略功能：")
        print("  - 绑定realtime_tick_5s数据源")
        print("  - 每五分钟接收一次数据")
        print("  - 将数据存储到quant_snapshot_5min_window表")
        print("  - 自动添加时间戳和记录数")
        print("\n请重启naja以应用更改：")
        print("  python -m deva.naja")
    else:
        print("\n❌ 任务失败！")
        print("策略创建失败，请检查错误信息")

if __name__ == '__main__':
    main()
