"""
为现有数据源添加 data_schema 定义
明确声明每个数据源的数据格式
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time
from deva import NB


# 预定义的数据格式模板
DATA_SCHEMA_TEMPLATES = {
    "tick": {
        "type": "tick",
        "description": "行情数据，包含股票价格、成交量等信息",
        "fields": [
            {"name": "symbol", "type": "string", "description": "股票代码", "required": True},
            {"name": "price", "type": "float", "description": "当前价格", "required": True},
            {"name": "volume", "type": "int", "description": "成交量", "required": False},
            {"name": "timestamp", "type": "float", "description": "时间戳", "required": True},
            {"name": "high", "type": "float", "description": "最高价", "required": False},
            {"name": "low", "type": "float", "description": "最低价", "required": False},
            {"name": "open", "type": "float", "description": "开盘价", "required": False},
            {"name": "close", "type": "float", "description": "收盘价", "required": False},
        ],
        "example": {
            "symbol": "AAPL",
            "price": 150.5,
            "volume": 1000,
            "timestamp": 1773168000.0,
            "high": 152.0,
            "low": 149.0,
            "open": 149.5,
            "close": 150.5
        }
    },
    "news": {
        "type": "news",
        "description": "新闻数据，包含标题、内容等信息",
        "fields": [
            {"name": "id", "type": "string", "description": "新闻ID", "required": True},
            {"name": "title", "type": "string", "description": "新闻标题", "required": True},
            {"name": "content", "type": "string", "description": "新闻内容", "required": True},
            {"name": "timestamp", "type": "float", "description": "发布时间戳", "required": True},
            {"name": "type", "type": "string", "description": "新闻类型", "required": False},
            {"name": "importance", "type": "string", "description": "重要程度", "required": False},
            {"name": "sentiment", "type": "string", "description": "情感倾向", "required": False},
            {"name": "keywords", "type": "list", "description": "关键词列表", "required": False},
        ],
        "example": {
            "id": "news_123456",
            "title": "某公司股票今日大涨10%",
            "content": "受利好消息影响，某公司股票今日大涨10%，市场信心增强...",
            "timestamp": 1773168000.0,
            "type": "finance",
            "importance": "高",
            "sentiment": "positive",
            "keywords": ["股票", "上涨", "市场"]
        }
    },
    "log": {
        "type": "log",
        "description": "日志数据，包含日志内容和时间戳",
        "fields": [
            {"name": "content", "type": "string", "description": "日志内容", "required": True},
            {"name": "timestamp", "type": "float", "description": "日志时间戳", "required": True},
            {"name": "level", "type": "string", "description": "日志级别", "required": False},
            {"name": "source", "type": "string", "description": "日志来源", "required": False},
        ],
        "example": {
            "content": "System started successfully",
            "timestamp": 1773168000.0,
            "level": "INFO",
            "source": "system"
        }
    },
    "file": {
        "type": "file",
        "description": "文件/目录监控数据，包含文件变更信息",
        "fields": [
            {"name": "event_type", "type": "string", "description": "事件类型(created/modified/deleted)", "required": True},
            {"name": "file_path", "type": "string", "description": "文件路径", "required": True},
            {"name": "timestamp", "type": "float", "description": "事件时间戳", "required": True},
            {"name": "file_size", "type": "int", "description": "文件大小", "required": False},
            {"name": "file_name", "type": "string", "description": "文件名", "required": False},
        ],
        "example": {
            "event_type": "created",
            "file_path": "/path/to/file.txt",
            "timestamp": 1773168000.0,
            "file_size": 1024,
            "file_name": "file.txt"
        }
    },
    "unknown": {
        "type": "unknown",
        "description": "未知数据类型",
        "fields": [
            {"name": "raw_data", "type": "any", "description": "原始数据", "required": True},
            {"name": "timestamp", "type": "float", "description": "时间戳", "required": True},
        ],
        "example": {
            "raw_data": {},
            "timestamp": 1773168000.0
        }
    }
}


# 数据源名称到数据类型的映射
DATASOURCE_TYPE_MAP = {
    # tick 类型
    "symbol_tick_source": "tick",
    "sliding_window信号": "tick",
    "test_always_run": "tick",
    "realtime_quant_5s_alltime": "tick",
    "realtime_quant_5s": "tick",
    "行情回放": "tick",
    
    # news 类型
    "财经新闻模拟源": "news",
    
    # log 类型
    "系统日志监控": "log",
    
    # file 类型
    "下载目录监控": "file",
}


def add_data_schema_to_datasource(ds_id: str, ds_data: dict) -> bool:
    """
    为单个数据源添加 data_schema
    
    Args:
        ds_id: 数据源ID
        ds_data: 数据源数据
        
    Returns:
        是否成功添加
    """
    metadata = ds_data.get('metadata', {})
    name = metadata.get('name', '')
    config = metadata.get('config', {})
    
    # 如果已经有 data_schema，跳过
    if 'data_schema' in config:
        print(f"  {name}: 已有 data_schema，跳过")
        return False
    
    # 确定数据类型
    data_type = DATASOURCE_TYPE_MAP.get(name, 'unknown')
    
    # 获取 data_schema 模板
    schema_template = DATA_SCHEMA_TEMPLATES.get(data_type, DATA_SCHEMA_TEMPLATES['unknown'])
    
    # 添加到 config
    config['data_schema'] = schema_template
    metadata['config'] = config
    metadata['updated_at'] = time.time()
    
    return True


def main():
    """主函数"""
    print("=" * 80)
    print("为现有数据源添加 data_schema")
    print("=" * 80)
    print()
    
    # 获取所有数据源
    db = NB('naja_datasources')
    
    updated_count = 0
    skipped_count = 0
    
    for ds_id, ds_data in db.items():
        if isinstance(ds_data, dict):
            name = ds_data.get('metadata', {}).get('name', '未命名')
            print(f"处理数据源: {name} (ID: {ds_id})")
            
            if add_data_schema_to_datasource(ds_id, ds_data):
                # 保存更新
                db[ds_id] = ds_data
                print(f"  ✓ 已添加 data_schema")
                updated_count += 1
            else:
                skipped_count += 1
    
    print()
    print("=" * 80)
    print(f"完成！更新: {updated_count}, 跳过: {skipped_count}")
    print("=" * 80)


if __name__ == '__main__':
    main()
