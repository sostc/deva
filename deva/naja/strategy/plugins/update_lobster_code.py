"""
更新龙虾思想雷达策略的代码 - 支持多数据源
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB

# 新的策略代码 - 支持多数据源
new_strategy_code = '''
"""
龙虾思想雷达策略 - 实时记忆系统（多数据源版本）
支持同时处理多个数据源的数据流
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import traceback
import time
import numpy as np
from deva.naja.strategy.plugins.lobster_radar import LobsterRadarStrategy

# 初始化策略实例
_radar = LobsterRadarStrategy(config={
    "short_term_size": 1000,
    "topic_threshold": 0.5,  # 降低阈值，让新主题更容易创建
    "attention_threshold": 0.6,
    "max_topics": 50,
})

def _normalize_record(record):
    """
    将各种数据类型标准化为字典格式
    处理多数据源传入的数据格式
    """
    # 如果数据已经包含数据源信息（多数据源模式）
    if isinstance(record, dict) and "_datasource_id" in record:
        original_data = record.get("data", record)
        
        # 过滤掉流式状态信息
        if isinstance(original_data, dict) and original_data.get("status") == "streaming":
            # 这是流式数据源的状态信息，不是实际数据
            return None
        
        # 处理 numpy 数组
        if isinstance(original_data, np.ndarray):
            return {
                "data": {"array": original_data.tolist(), "shape": original_data.shape},
                "timestamp": time.time(),
                "source": record.get("_datasource_name", "unknown"),
                "_datasource_id": record.get("_datasource_id"),
                "_datasource_name": record.get("_datasource_name"),
            }
        
        # 处理非字典类型
        if not isinstance(original_data, dict):
            return {
                "data": {"raw": str(original_data)},
                "timestamp": time.time(),
                "source": record.get("_datasource_name", "unknown"),
                "_datasource_id": record.get("_datasource_id"),
                "_datasource_name": record.get("_datasource_name"),
            }
        
        # 已经是字典，添加数据源信息
        # 检查是否是新闻数据（包含 title 字段）
        if "title" in original_data:
            # 新闻数据，保持原样但添加数据源信息
            normalized = dict(original_data)
            normalized["_datasource_id"] = record.get("_datasource_id")
            normalized["_datasource_name"] = record.get("_datasource_name")
            if "source" not in normalized:
                normalized["source"] = record.get("_datasource_name", "unknown")
            if "timestamp" not in normalized:
                normalized["timestamp"] = time.time()
            return normalized
        else:
            # 其他字典数据，包装到 data 字段
            normalized = {
                "data": original_data,
                "_datasource_id": record.get("_datasource_id"),
                "_datasource_name": record.get("_datasource_name"),
                "source": record.get("_datasource_name", "unknown"),
                "timestamp": time.time(),
            }
            return normalized
    
    # 处理 numpy 数组类型的数据（单数据源模式）
    if isinstance(record, np.ndarray):
        return {
            "data": {"array": record.tolist(), "shape": record.shape},
            "timestamp": time.time(),
            "source": "numpy_array"
        }
    
    # 处理非字典类型
    if not isinstance(record, dict):
        return {
            "data": {"raw": str(record)},
            "timestamp": time.time(),
            "source": "unknown"
        }
    
    # 已经是字典，确保有必要的字段
    if "data" not in record:
        record = {"data": record, "timestamp": time.time(), "source": "dict"}
    
    return record

def process(record):
    """
    处理单条记录
    
    Args:
        record: 数据源记录，可能是：
            - 多数据源模式: {"_datasource_id": ..., "_datasource_name": ..., "data": ...}
            - 单数据源模式: 原始数据（numpy数组、字典等）
        
    Returns:
        信号列表或处理结果
    """
    try:
        # 标准化记录格式
        normalized_record = _normalize_record(record)
        
        # 如果标准化返回None（如流式状态信息），跳过处理
        if normalized_record is None:
            return {"signals": [], "stats": _radar.get_memory_report()}
        
        # 提取数据源信息用于日志
        ds_name = normalized_record.get("_datasource_name", "unknown")
        ds_id = normalized_record.get("_datasource_id", "unknown")
        
        signals = _radar.process_record(normalized_record)
        
        # 添加数据源信息到信号
        for signal in signals:
            signal["source_datasource"] = ds_name
            signal["source_datasource_id"] = ds_id
        
        # 输出信号到日志
        for signal in signals:
            print(f"[LOBSTER_SIGNAL] [{ds_name}] {signal['type']}: {signal['message']}")
        
        # 返回信号列表
        return {
            "signals": signals,
            "stats": _radar.get_memory_report(),
            "source": ds_name,
        }
    except Exception as e:
        print(f"[LOBSTER_ERROR] {e}")
        print(f"[LOBSTER_ERROR] Record type: {type(record)}")
        print(f"[LOBSTER_ERROR] Traceback: {traceback.format_exc()}")
        raise

# 可选：窗口处理函数
def process_window(records):
    """
    处理窗口数据
    
    Args:
        records: 记录列表
        
    Returns:
        处理结果
    """
    try:
        # 标准化所有记录
        processed_records = [_normalize_record(r) for r in records]
        
        signals = _radar.process_window(processed_records)
        return {
            "signals": signals,
            "window_size": len(processed_records),
            "stats": _radar.get_memory_report(),
        }
    except Exception as e:
        print(f"[LOBSTER_ERROR] process_window: {e}")
        print(f"[LOBSTER_ERROR] Traceback: {traceback.format_exc()}")
        raise
'''

def update_strategy():
    """更新策略代码"""
    db = NB('naja_strategies')
    
    for key, value in db.items():
        if isinstance(value, dict):
            name = value.get('metadata', {}).get('name', '')
            if name == '龙虾思想雷达':
                print(f'找到策略: {name} (ID: {key})')
                print()
                
                # 更新代码
                value['func_code'] = new_strategy_code
                value['metadata']['updated_at'] = __import__('time').time()
                
                # 保存
                db[key] = value
                
                print('✅ 策略代码已更新')
                print()
                print('更新内容:')
                print('  - 支持多数据源数据格式（包含 _datasource_id 和 _datasource_name）')
                print('  - 信号中包含数据源信息')
                print('  - 日志中显示数据源名称')
                return True
    
    print('❌ 未找到策略')
    return False

if __name__ == '__main__':
    print('=' * 60)
    print('更新龙虾思想雷达策略代码（多数据源版本）')
    print('=' * 60)
    print()
    
    if update_strategy():
        print()
        print('=' * 60)
        print('✅ 更新完成')
        print('=' * 60)
        print()
        print('请重启 naja 以应用更改:')
        print('  python -m deva.naja')
    else:
        print()
        print('=' * 60)
        print('❌ 更新失败')
        print('=' * 60)
