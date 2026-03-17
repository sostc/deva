"""
数据源创建辅助脚本
用于根据用户需求生成并保存数据源
"""

import sys
import hashlib
import time
import re
from typing import Dict, Any, List, Optional

sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB


# 数据格式模板
DATA_SCHEMA_TEMPLATES = {
    "tick": {
        "type": "tick",
        "description": "行情数据，包含股票价格、成交量等信息",
        "fields": [
            {"name": "symbol", "type": "string", "description": "股票代码", "required": True},
            {"name": "price", "type": "float", "description": "当前价格", "required": True},
            {"name": "volume", "type": "int", "description": "成交量", "required": False},
            {"name": "timestamp", "type": "float", "description": "时间戳", "required": True},
        ],
        "example": {
            "symbol": "AAPL",
            "price": 150.5,
            "volume": 1000,
            "timestamp": time.time()
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
        ],
        "example": {
            "id": "news_123456",
            "title": "某公司股票今日大涨10%",
            "content": "受利好消息影响...",
            "timestamp": time.time(),
            "type": "finance"
        }
    },
    "log": {
        "type": "log",
        "description": "日志数据，包含日志内容和时间戳",
        "fields": [
            {"name": "content", "type": "string", "description": "日志内容", "required": True},
            {"name": "timestamp", "type": "float", "description": "日志时间戳", "required": True},
            {"name": "level", "type": "string", "description": "日志级别", "required": False},
        ],
        "example": {
            "content": "System started successfully",
            "timestamp": time.time(),
            "level": "INFO"
        }
    },
    "file": {
        "type": "file",
        "description": "文件/目录监控数据，包含文件变更信息",
        "fields": [
            {"name": "event_type", "type": "string", "description": "事件类型(created/modified/deleted)", "required": True},
            {"name": "file_path", "type": "string", "description": "文件路径", "required": True},
            {"name": "timestamp", "type": "float", "description": "事件时间戳", "required": True},
        ],
        "example": {
            "event_type": "created",
            "file_path": "/path/to/file.txt",
            "timestamp": time.time()
        }
    }
}


def generate_datasource_id(name: str) -> str:
    """生成数据源唯一ID"""
    return hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]


def infer_source_type(description: str) -> str:
    """
    从描述中推断数据源类型
    
    Returns:
        timer/file/directory/replay/unknown
    """
    desc_lower = description.lower()
    
    if any(kw in desc_lower for kw in ['定时', '每隔', '每', '秒', '分钟', '小时', 'timer', 'interval', '定时器']):
        return "timer"
    elif any(kw in desc_lower for kw in ['文件', '日志文件', 'file', '监控文件', 'log file']):
        return "file"
    elif any(kw in desc_lower for kw in ['目录', '文件夹', 'directory', 'folder', '监控目录']):
        return "directory"
    elif any(kw in desc_lower for kw in ['回放', '历史数据', 'replay', '重放']):
        return "replay"
    else:
        return "unknown"


def infer_interval(description: str) -> float:
    """
    从描述中推断执行间隔（秒）
    
    Returns:
        间隔秒数，默认 5.0
    """
    # 匹配 "每X秒"、"每X分钟"、"每X小时"
    patterns = [
        (r'每\s*(\d+)\s*秒', 1),
        (r'每\s*(\d+)\s*分钟', 60),
        (r'每\s*(\d+)\s*小时', 3600),
        (r'(\d+)\s*秒.*一次', 1),
        (r'(\d+)\s*分钟.*一次', 60),
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, description)
        if match:
            return float(match.group(1)) * multiplier
    
    return 5.0  # 默认值


def infer_execution_mode(description: str) -> str:
    """推断执行模式"""
    desc_lower = description.lower()
    
    if any(kw in desc_lower for kw in ['cron', '定时任务', '计划任务']):
        return "scheduler"
    elif any(kw in desc_lower for kw in ['事件', '触发', 'event', 'trigger']):
        return "event_trigger"
    else:
        return "timer"


def extract_path(description: str) -> Optional[str]:
    """从描述中提取文件或目录路径"""
    # 匹配常见的路径格式
    patterns = [
        r'(/[\w/\-\.]+\.[\w]+)',  # Unix 文件路径
        r'(/[\w/\-]+)',  # Unix 目录路径
        r'(C:\\\\[\\w\\\\\.]+)',  # Windows 路径
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            return match.group(1)
    
    return None


def generate_datasource_name(description: str) -> str:
    """根据描述生成数据源名称"""
    # 提取关键词
    keywords = []
    
    if any(kw in description for kw in ['股票', '行情', '价格', 'stock', 'tick']):
        keywords.append('股票行情')
    elif any(kw in description for kw in ['新闻', 'news', '资讯']):
        keywords.append('新闻')
    elif any(kw in description for kw in ['日志', 'log', '系统日志']):
        keywords.append('日志监控')
    elif any(kw in description for kw in ['文件', 'file']):
        keywords.append('文件监控')
    elif any(kw in description for kw in ['目录', '文件夹', 'directory']):
        keywords.append('目录监控')
    else:
        keywords.append('数据')
    
    if any(kw in description for kw in ['定时', '定时器', 'timer']):
        keywords.append('定时')
    
    return ''.join(keywords) + '数据源'


def infer_data_schema(description: str, source_type: str) -> Dict[str, Any]:
    """
    推断数据格式 schema

    Args:
        description: 用户描述
        source_type: 数据源类型

    Returns:
        data_schema 字典
    """
    desc_lower = description.lower()

    # 根据关键词推断数据类型
    if any(kw in desc_lower for kw in ['股票', '行情', '价格', 'stock', 'tick', 'price', 'symbol']):
        return DATA_SCHEMA_TEMPLATES["tick"].copy()
    elif any(kw in desc_lower for kw in ['新闻', 'news', '标题', 'title', 'content']):
        return DATA_SCHEMA_TEMPLATES["news"].copy()
    elif any(kw in desc_lower for kw in ['日志', 'log']):
        return DATA_SCHEMA_TEMPLATES["log"].copy()
    elif source_type in ["file", "directory"]:
        return DATA_SCHEMA_TEMPLATES["file"].copy()
    else:
        # 默认 tick 类型
        return DATA_SCHEMA_TEMPLATES["tick"].copy()


def infer_is_async(description: str) -> bool:
    """
    推断是否应该使用异步函数

    Args:
        description: 用户描述

    Returns:
        是否使用异步（涉及网络IO时返回True）
    """
    desc_lower = description.lower()

    # 涉及网络IO的关键词
    network_keywords = [
        'api', 'http', 'https', '请求', '网络', '爬虫', '抓取',
        'fetch', 'request', 'web', 'url', '接口', 'rest',
        '股票', '行情', '新闻', '资讯', '数据', '实时'
    ]

    return any(kw in desc_lower for kw in network_keywords)


def generate_timer_func_code(data_fields: List[str], fetch_logic: str = "", is_async: bool = True) -> str:
    """
    生成 timer 类型的 func_code

    Args:
        data_fields: 数据字段列表
        fetch_logic: 用户描述的获取逻辑
        is_async: 是否生成异步函数（涉及网络IO时推荐使用）

    Returns:
        func_code 字符串
    """
    if is_async:
        code = '''async def fetch_data():
    """
    获取数据（异步版本）
    涉及网络IO，使用异步以提高性能
    """
    import aiohttp
    import json
    import time

    # TODO: 实现数据获取逻辑
    # 用户描述：''' + fetch_logic + '''

    # 示例：HTTP 请求
    # url = "https://api.example.com/data"
    # try:
    #     async with aiohttp.ClientSession() as session:
    #         async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
    #             data = await resp.json()
    # except Exception as e:
    #     print(f"请求失败: {e}")
    #     return None

    # 模拟数据（请替换为实际逻辑）
    import random

'''
    else:
        code = '''def fetch_data():
    """
    获取数据
    """
    import time
    import random

    # TODO: 实现数据获取逻辑
    # 用户描述：''' + fetch_logic + '''

'''

    # 根据字段生成示例数据
    code += '    data = {\n'
    for field in data_fields:
        if field == "timestamp":
            code += '        "timestamp": time.time(),\n'
        elif field == "symbol":
            code += '        "symbol": "AAPL",  # 股票代码\n'
        elif field == "price":
            code += '        "price": round(random.uniform(100, 200), 2),  # 价格\n'
        elif field == "volume":
            code += '        "volume": random.randint(1000, 10000),  # 成交量\n'
        elif field == "id":
            code += '        "id": f"data_{int(time.time())}",  # ID\n'
        elif field == "title":
            code += '        "title": "示例标题",  # 标题\n'
        elif field == "content":
            code += '        "content": "示例内容",  # 内容\n'
        else:
            code += f'        "{field}": "",  # {field}\n'

    code += '''    }

    return data
'''

    return code


def generate_file_func_code(process_logic: str = "") -> str:
    """生成 file 类型的 func_code"""
    return '''def fetch_data(line):
    """
    处理文件中的一行数据
    
    Args:
        line: 文件中的一行内容
    
    Returns:
        处理后的数据，返回 None 则跳过该行
    """
    import time
    
    # TODO: 实现数据处理逻辑
    # 用户描述：''' + process_logic + '''
    
    if line and line.strip():
        return {
            "content": line.strip(),
            "timestamp": time.time()
        }
    
    return None
'''


def generate_directory_func_code(process_logic: str = "") -> str:
    """生成 directory 类型的 func_code"""
    return '''def fetch_data(event):
    """
    处理目录变化事件
    
    Args:
        event: {
            "event": "created" | "modified" | "deleted",
            "path": "文件完整路径",
            "file_info": {"path": ..., "name": ..., "size": ..., "mtime": ...},
            "old_info": {...}  # 仅 modified 事件有
        }
    
    Returns:
        处理后的数据
    """
    import time
    
    # TODO: 实现事件处理逻辑
    # 用户描述：''' + process_logic + '''
    
    return {
        "event_type": event.get("event"),
        "file_path": event.get("path"),
        "timestamp": time.time()
    }
'''


def create_datasource(
    name: str,
    description: str,
    source_type: str,
    interval: float = 5.0,
    execution_mode: str = "timer",
    config: Dict[str, Any] = None,
    func_code: str = "",
    data_schema: Dict[str, Any] = None,
    tags: List[str] = None
) -> str:
    """
    创建并保存数据源（立即生效，无需重启 naja）
    
    Args:
        name: 数据源名称
        description: 描述
        source_type: 类型 (timer/file/directory/replay)
        interval: 执行间隔
        execution_mode: 执行模式
        config: 配置字典
        func_code: 代码字符串
        data_schema: 数据格式定义
        tags: 标签列表
        
    Returns:
        数据源ID
    """
    if config is None:
        config = {}
    if tags is None:
        tags = []
    
    # 检查名称是否已存在
    db = NB('naja_datasources')
    for existing_id, existing_data in db.items():
        if isinstance(existing_data, dict):
            existing_name = existing_data.get('metadata', {}).get('name', '')
            if existing_name == name:
                raise ValueError(f"数据源名称 '{name}' 已存在")
    
    # 生成ID
    datasource_id = generate_datasource_id(name)
    
    # 添加 data_schema 到 config
    if data_schema:
        config['data_schema'] = data_schema
    
    # 构建数据源字典
    datasource_record = {
        "metadata": {
            "id": datasource_id,
            "name": name,
            "description": description,
            "tags": tags,
            "source_type": source_type,
            "config": config,
            "interval": interval,
            "execution_mode": execution_mode,
            "scheduler_trigger": "interval",
            "cron_expr": "",
            "run_at": "",
            "event_source": "log",
            "event_condition": "",
            "event_condition_type": "contains",
            "created_at": time.time(),
            "updated_at": time.time(),
        },
        "state": {
            "status": "stopped",
            "start_time": 0,
            "last_activity_ts": 0,
            "error_count": 0,
            "last_error": "",
            "last_error_ts": 0,
            "run_count": 0,
            "last_data_ts": 0,
            "total_emitted": 0,
            "pid": 0,
        },
        "func_code": func_code,
        "was_running": False
    }
    
    # 保存到数据库 - 立即生效，无需重启
    db[datasource_id] = datasource_record
    
    return datasource_id


def create_datasource_immediate(
    name: str,
    description: str,
    source_type: str,
    interval: float = 5.0,
    execution_mode: str = "timer",
    config: Dict[str, Any] = None,
    func_code: str = "",
    data_schema: Dict[str, Any] = None,
    tags: List[str] = None,
    auto_start: bool = False
) -> Dict[str, Any]:
    """
    创建数据源并立即生效（无需重启 naja）
    
    这是推荐的方式，数据源保存到数据库后立即生效，naja 会自动检测并加载。
    
    Args:
        name: 数据源名称
        description: 描述
        source_type: 类型 (timer/file/directory/replay)
        interval: 执行间隔
        execution_mode: 执行模式
        config: 配置字典
        func_code: 代码字符串
        data_schema: 数据格式定义
        tags: 标签列表
        auto_start: 是否立即启动（设置 was_running=True）
        
    Returns:
        包含 success, id, message 的字典
    """
    try:
        # 创建数据源
        datasource_id = create_datasource(
            name=name,
            description=description,
            source_type=source_type,
            interval=interval,
            execution_mode=execution_mode,
            config=config,
            func_code=func_code,
            data_schema=data_schema,
            tags=tags
        )
        
        # 如果设置为自动启动，更新 was_running
        if auto_start:
            db = NB('naja_datasources')
            ds_data = db.get(datasource_id)
            if ds_data:
                ds_data['was_running'] = True
                ds_data['state']['status'] = 'running'
                db[datasource_id] = ds_data
        
        return {
            "success": True,
            "id": datasource_id,
            "message": f"数据源 '{name}' 已创建并立即生效，无需重启 naja！",
            "details": {
                "name": name,
                "source_type": source_type,
                "interval": interval,
                "auto_start": auto_start
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "id": None,
            "message": f"创建失败: {str(e)}"
        }


def analyze_user_requirement(description: str) -> Dict[str, Any]:
    """
    分析用户需求，推断数据源配置
    
    Args:
        description: 用户描述
        
    Returns:
        推断的配置字典
    """
    # 推断类型
    source_type = infer_source_type(description)
    
    # 推断名称
    name = generate_datasource_name(description)
    
    # 推断间隔
    interval = infer_interval(description)
    
    # 推断执行模式
    execution_mode = infer_execution_mode(description)
    
    # 推断路径
    path = extract_path(description)
    
    # 推断数据格式
    data_schema = infer_data_schema(description, source_type)

    # 推断是否使用异步（涉及网络IO时使用异步）
    is_async = infer_is_async(description)

    # 构建配置
    config = {}
    if source_type == "file" and path:
        config = {
            "file_path": path,
            "poll_interval": 0.1,
            "read_mode": "tail"
        }
    elif source_type == "directory" and path:
        config = {
            "directory_path": path,
            "poll_interval": 1.0,
            "file_pattern": "*",
            "watch_events": ["created", "modified"]
        }
    elif source_type == "timer":
        config = {
            "interval": interval
        }

    return {
        "name": name,
        "source_type": source_type,
        "description": description,
        "interval": interval,
        "execution_mode": execution_mode,
        "config": config,
        "data_schema": data_schema,
        "path": path,
        "is_async": is_async
    }


if __name__ == '__main__':
    print("数据源创建辅助脚本 - 支持立即生效")
    print("=" * 60)
    
    # 测试分析功能
    test_descriptions = [
        "创建一个定时获取股票行情的数据源，每5秒获取一次",
        "创建一个监控日志文件的数据源，监控 /var/log/app.log",
        "创建一个监控下载目录的数据源，当有新文件时通知",
    ]
    
    for desc in test_descriptions:
        print(f"\n用户描述: {desc}")
        config = analyze_user_requirement(desc)
        print(f"推断配置:")
        print(f"  名称: {config['name']}")
        print(f"  类型: {config['source_type']}")
        print(f"  间隔: {config['interval']}秒")
        print(f"  路径: {config.get('path', '无')}")
        print(f"  数据类型: {config['data_schema']['type']}")
    
    # 测试立即创建功能
    print("\n" + "=" * 60)
    print("测试立即创建功能（立即生效，无需重启 naja）")
    print("=" * 60)
    
    result = create_datasource_immediate(
        name="测试时间戳数据源",
        description="测试立即生效功能的时间戳数据源",
        source_type="timer",
        interval=3.0,
        func_code="""def fetch_data():
    import time
    from datetime import datetime
    ts = time.time()
    return {
        'id': f'test_{int(ts)}',
        'timestamp': ts,
        'datetime': datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    }
""",
        data_schema={
            "type": "timestamp",
            "description": "测试时间戳数据",
            "fields": [
                {"name": "id", "type": "string", "required": True},
                {"name": "timestamp", "type": "float", "required": True},
                {"name": "datetime", "type": "string", "required": True}
            ]
        },
        auto_start=False
    )
    
    print(f"\n创建结果:")
    print(f"  成功: {result['success']}")
    print(f"  ID: {result['id']}")
    print(f"  消息: {result['message']}")
    
    if result['success']:
        print(f"\n✅ 数据源已立即生效！")
        print(f"你可以刷新 naja Web 界面查看新数据源")
