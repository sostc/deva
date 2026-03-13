"""
策略创建辅助脚本
基于 river 策略模板自动生成完整策略，支持数据源和数据字典整合
使用 data_schema 明确声明的数据格式
"""

import sys
import uuid
import time
import random
from typing import List, Dict, Any

sys.path.insert(0, '/Users/spark/pycharmproject/deva')
sys.path.insert(0, '/Users/spark/pycharmproject/deva/.trae/skills/strategy-creator/scripts')

from deva import NB

# 导入新的 principle 结构生成函数
from create_strategy_principle import (
    generate_fisherman_principle,
    generate_otter_principle,
    generate_heron_principle,
    generate_beaver_principle,
    generate_duck_principle,
    generate_lobster_principle,
)


def generate_strategy_id() -> str:
    """生成策略唯一ID"""
    return str(uuid.uuid4())[:16]


def get_all_datasources() -> List[Dict[str, Any]]:
    """获取所有可用的数据源，包含 data_schema"""
    db = NB('naja_datasources')
    datasources = []
    
    for ds_id, ds_data in db.items():
        if isinstance(ds_data, dict):
            metadata = ds_data.get('metadata', {})
            config = metadata.get('config', {})
            datasources.append({
                'id': ds_id,
                'name': metadata.get('name', '未命名'),
                'source_type': metadata.get('source_type', 'custom'),
                'description': metadata.get('description', ''),
                'data_schema': config.get('data_schema', {}),  # 使用 data_schema
            })
    
    return datasources


def get_all_dictionaries() -> List[Dict[str, Any]]:
    """获取所有可用的数据字典"""
    db = NB('naja_dictionary_entries')
    dictionaries = []
    
    for dict_id, dict_data in db.items():
        if isinstance(dict_data, dict):
            metadata = dict_data.get('metadata', {})
            dictionaries.append({
                'id': dict_id,
                'name': metadata.get('name', '未命名'),
                'dict_type': metadata.get('dict_type', 'custom'),
                'description': metadata.get('description', ''),
                'func_code': dict_data.get('func_code', ''),
            })
    
    return dictionaries


def get_datasource_schema(ds_id: str) -> Dict[str, Any]:
    """
    获取数据源的 data_schema
    
    Args:
        ds_id: 数据源ID
        
    Returns:
        data_schema 字典
    """
    db = NB('naja_datasources')
    ds_data = db.get(ds_id, {})
    
    if isinstance(ds_data, dict):
        metadata = ds_data.get('metadata', {})
        config = metadata.get('config', {})
        return config.get('data_schema', {})
    
    return {}


def analyze_dictionary_format(func_code: str) -> Dict[str, Any]:
    """分析数据字典的数据格式"""
    fields = []
    dict_type = "unknown"
    
    # 分析字典类型和字段
    if 'stock_list' in func_code or 'fundamentals' in func_code:
        dict_type = "stock_market"
        fields = ['code', 'name', 'industry', 'stock_list', 'fundamentals']
    elif 'blockname' in func_code:
        dict_type = "stock_basic_block"
        fields = ['code', 'name', 'industry', 'blockname']
    elif 'code' in func_code:
        dict_type = "stock_basic"
        fields = ['code', 'name', 'industry']
    
    return {'type': dict_type, 'fields': fields}


def integrate_data_formats(
    datasource_schemas: List[Dict[str, Any]],
    dictionary_formats: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    整合数据源和数据字典的数据格式
    
    Args:
        datasource_schemas: 数据源的 data_schema 列表
        dictionary_formats: 数据字典格式列表
        
    Returns:
        整合后的数据格式信息
    """
    # 收集所有字段
    all_datasource_fields = []
    for schema in datasource_schemas:
        fields = schema.get('fields', [])
        all_datasource_fields.extend([f['name'] for f in fields])
    
    all_dictionary_fields = []
    for fmt in dictionary_formats:
        all_dictionary_fields.extend(fmt.get('fields', []))
    
    # 识别关联字段
    join_fields = []
    common_codes = ['symbol', 'code', 'name', 'id']
    for field in all_datasource_fields:
        if field in all_dictionary_fields or field in common_codes:
            join_fields.append(field)
    
    # 如果没有共同字段，尝试映射
    if not join_fields:
        if 'symbol' in all_datasource_fields and 'code' in all_dictionary_fields:
            join_fields = ['symbol', 'code']
        elif 'code' in all_datasource_fields and 'symbol' in all_dictionary_fields:
            join_fields = ['code', 'symbol']
    
    # 获取数据类型
    datasource_types = [schema.get('type', 'unknown') for schema in datasource_schemas]
    
    return {
        'datasource_fields': list(set(all_datasource_fields)),
        'dictionary_fields': list(set(all_dictionary_fields)),
        'join_fields': join_fields,
        'datasource_types': datasource_types,
        'dictionary_types': [fmt['type'] for fmt in dictionary_formats],
        'datasource_schemas': datasource_schemas  # 保留完整的 schema 信息
    }


def generate_strategy_name(user_logic: str, datasource_types: List[str], has_dictionary: bool) -> str:
    """根据用户逻辑自动生成策略名称"""
    # 根据关键词生成名称
    if any(kw in user_logic for kw in ['价格', 'price', '超过', '大于', '阈值']):
        base_name = "价格监控策略"
    elif any(kw in user_logic for kw in ['新闻', '关键词', 'keyword', '标题']):
        base_name = "新闻关键词监控策略"
    elif any(kw in user_logic for kw in ['平均', 'mean', '统计', '窗口']):
        base_name = "滑动窗口统计策略"
    elif any(kw in user_logic for kw in ['日志', 'log', 'error', '错误']):
        base_name = "日志监控策略"
    elif any(kw in user_logic for kw in ['文件', 'file', '目录', 'folder']):
        base_name = "文件变更监控策略"
    elif any(kw in user_logic for kw in ['板块', '行业', 'industry', 'block']):
        base_name = "板块行业监控策略"
    elif any(kw in user_logic for kw in ['基本面', '财务', 'fundamental', '市盈率']):
        base_name = "基本面筛选策略"
    else:
        type_names = {'tick': '行情', 'news': '新闻', 'log': '日志', 'file': '文件'}
        type_name = type_names.get(datasource_types[0], '数据') if datasource_types else '数据'
        base_name = f"{type_name}处理策略"
    
    # 如果有数据字典，添加标识
    if has_dictionary:
        base_name = base_name.replace("策略", "智能策略")
    
    return base_name


def generate_strategy_description(
    name: str,
    user_logic: str,
    datasource_names: List[str],
    dictionary_names: List[str]
) -> str:
    """自动生成策略描述"""
    ds_desc = "、".join(datasource_names) if datasource_names else "指定数据源"
    
    if dictionary_names:
        dict_desc = "、".join(dictionary_names)
        return f"基于{ds_desc}数据源和{dict_desc}数据字典的{name}。{user_logic}"
    else:
        return f"基于{ds_desc}的{name}。{user_logic}"


def generate_diagram_info(
    name: str,
    user_logic: str,
    datasource_types: List[str],
    has_dictionary: bool
) -> Dict[str, Any]:
    """
    生成 diagram_info 可视化信息，包含河流比喻（使用 principle 字段）
    
    Args:
        name: 策略名称
        user_logic: 用户逻辑描述
        datasource_types: 数据源类型列表
        has_dictionary: 是否绑定了数据字典
        
    Returns:
        完整的 diagram_info 字典
    """
    # 图标映射
    icon_map = {
        '价格': '📈', '新闻': '📰', '日志': '📝', '文件': '📁',
        '行情': '📊', '板块': '🏢', '基本面': '💰', '智能': '🤖',
        '监控': '👁️', '筛选': '🔍', '统计': '📉', '分析': '🔬'
    }
    
    # 颜色映射
    color_map = {
        '价格': '#E74C3C', '新闻': '#F39C12', '日志': '#1ABC9C',
        '行情': '#E74C3C', '板块': '#9B59B6', '基本面': '#2ECC71',
        '监控': '#3498DB', '筛选': '#8E44AD', '统计': '#34495E',
        '分析': '#16A085'
    }
    
    # 确定图标和颜色
    icon = '📊'
    color = '#3498DB'
    for key, val in icon_map.items():
        if key in name:
            icon = val
            color = color_map.get(key, color)
            break
    
    # 生成逻辑步骤
    logic_steps = [
        "1. 接收数据源输入",
        "2. 提取关键字段"
    ]
    
    if has_dictionary:
        logic_steps.extend([
            "3. 查询数据字典",
            "4. 关联数据源和字典数据"
        ])
        step_num = 5
    else:
        step_num = 3
    
    logic_steps.extend([
        f"{step_num}. 执行用户定义的处理逻辑",
        f"{step_num + 1}. 返回处理结果"
    ])
    
    # 生成河流比喻（使用 principle 字段结构）
    principle = generate_principle(name, user_logic, datasource_types, has_dictionary)
    
    return {
        "icon": icon,
        "color": color,
        "description": user_logic[:100] + "..." if len(user_logic) > 100 else user_logic,
        "formula": generate_formula(name, user_logic, has_dictionary),
        "logic": logic_steps,
        "output": "signal + data",
        "principle": principle  # 使用 principle 字段，不是 river_metaphor
    }


def generate_principle(
    name: str,
    user_logic: str,
    datasource_types: List[str],
    has_dictionary: bool
) -> Dict[str, Any]:
    """
    生成 principle 字段（河流比喻结构）
    
    根据策略类型和数据源类型生成相应的河流比喻，使用 five_dimensions 结构
    """
    # 根据策略类型选择生物和场景（按优先级排序）
    if any(kw in name for kw in ['价格', '行情']):
        return generate_fisherman_principle(user_logic, has_dictionary)
    elif any(kw in name for kw in ['新闻', '关键词']):
        return generate_otter_principle(user_logic, has_dictionary)
    elif any(kw in name for kw in ['日志']):
        return generate_heron_principle(user_logic, has_dictionary)
    elif any(kw in name for kw in ['文件', '目录']):
        return generate_beaver_principle(user_logic, has_dictionary)
    elif any(kw in name for kw in ['板块', '行业']):
        return generate_duck_principle(user_logic, has_dictionary)
    elif 'tick' in datasource_types:
        return generate_fisherman_principle(user_logic, has_dictionary)
    elif 'news' in datasource_types:
        return generate_otter_principle(user_logic, has_dictionary)
    elif 'log' in datasource_types:
        return generate_heron_principle(user_logic, has_dictionary)
    elif 'file' in datasource_types:
        return generate_beaver_principle(user_logic, has_dictionary)
    else:
        return generate_lobster_principle(user_logic, has_dictionary)


def generate_formula(name: str, user_logic: str, has_dictionary: bool) -> str:
    """生成策略公式描述"""
    if has_dictionary:
        return f"Strategy = Process(数据源) + Query(数据字典) + Logic({user_logic[:30]})"
    else:
        return f"Strategy = Process(数据源) + Logic({user_logic[:30]})"


def generate_process_code(
    compute_mode: str,
    integrated_format: Dict[str, Any],
    user_logic: str,
    dictionary_ids: List[str]
) -> str:
    """生成策略 process 函数代码"""
    
    code_lines = []
    has_dictionary = len(dictionary_ids) > 0
    ds_fields = integrated_format.get('datasource_fields', [])
    dict_fields = integrated_format.get('dictionary_fields', [])
    join_fields = integrated_format.get('join_fields', [])
    datasource_schemas = integrated_format.get('datasource_schemas', [])
    
    # 函数定义和文档字符串
    code_lines.append('def process(data, context=None):')
    code_lines.append('    """')
    code_lines.append(f'    策略处理函数')
    code_lines.append(f'    ')
    code_lines.append(f'    用户逻辑：{user_logic}')
    if has_dictionary:
        code_lines.append(f'    数据整合：数据源字段 + 数据字典字段')
    code_lines.append(f'    ')
    code_lines.append(f'    Args:')
    code_lines.append(f'        data: 输入数据')
    code_lines.append(f'        context: 上下文信息')
    code_lines.append(f'    ')
    code_lines.append(f'    Returns:')
    code_lines.append(f'        处理结果（字典或None）')
    code_lines.append(f'    """')
    code_lines.append(f'    import time')
    if has_dictionary:
        code_lines.append(f'    from deva import NB')
    code_lines.append('')
    
    # 数据提取逻辑
    if compute_mode == 'window':
        code_lines.extend([
            '    # window 模式: data 是记录列表',
            '    if not isinstance(data, list):',
            '        return None',
            '    ',
            '    results = []',
            '    for record in data:',
            '        if not isinstance(record, dict):',
            '            continue',
            '        ',
            '        raw_data = record.get("data", {})',
            '        datasource_name = record.get("_datasource_name", "unknown")',
            '        ',
            '        result = _process_single(raw_data, datasource_name)',
            '        if result:',
            '            results.append(result)',
            '    ',
            '    if results:',
            '        return {',
            '            "signal": "batch_results",',
            '            "count": len(results),',
            '            "results": results,',
            '            "timestamp": time.time()',
            '        }',
            '    return None',
            '',
            '',
            'def _process_single(raw_data, datasource_name):',
            '    """处理单条数据"""'
        ])
    else:
        code_lines.extend([
            '    # record 模式: data 是单条记录',
            '    if not isinstance(data, dict):',
            '        return None',
            '    ',
            '    raw_data = data.get("data", {})',
            '    datasource_name = data.get("_datasource_name", "unknown")',
            ''
        ])
    
    # 提取数据源字段（使用 data_schema 中的字段定义）
    code_lines.append('    # 提取数据源字段')
    for field in ds_fields[:4]:
        code_lines.append(f'    {field} = raw_data.get("{field}", "")')
    code_lines.append('')
    
    # 数据字典查询和整合
    if has_dictionary:
        code_lines.extend([
            '    # 查询数据字典',
            '    matched_info = None'
        ])
        
        # 生成关联逻辑
        if join_fields:
            join_key = join_fields[0] if join_fields[0] in ds_fields else ds_fields[0] if ds_fields else 'symbol'
            code_lines.extend([
                f'    join_key = {join_key}',
                '    if join_key:',
                '        # 从数据字典中查询匹配信息',
            ])
            
            for dict_id in dictionary_ids:
                code_lines.extend([
                    f'        dict_data_{dict_id[:8]} = NB("naja_dictionary_payloads").get("{dict_id}:latest", {{}})',
                    f'        if dict_data_{dict_id[:8]}:',
                    f'            for item in dict_data_{dict_id[:8]}.get("data", []):',
                    f'                if item.get("code") == join_key or item.get("symbol") == join_key:',
                    f'                    matched_info = item',
                    f'                    break'
                ])
        
        code_lines.append('    ')
        code_lines.append('    # 整合数据源和字典数据')
        code_lines.append('    integrated_data = {')
        
        # 添加数据源字段
        for field in ds_fields[:3]:
            code_lines.append(f'        "{field}": {field},')
        
        # 添加字典字段
        for field in dict_fields[:3]:
            code_lines.append(f'        "{field}": matched_info.get("{field}", "") if matched_info else "",')
        
        code_lines.append('    }')
        code_lines.append('')
    
    # 用户自定义处理逻辑
    code_lines.append(f'    # TODO: 实现用户逻辑：{user_logic}')
    code_lines.append('    # 示例：基于整合后的数据进行判断')
    code_lines.append('    result = {')
    code_lines.append('        "signal": "processed_signal",')
    
    if has_dictionary:
        code_lines.append('        "data": integrated_data,')
    else:
        for field in ds_fields[:2]:
            code_lines.append(f'        "{field}": {field},')
    
    code_lines.extend([
        '        "source": datasource_name,',
        '        "timestamp": time.time()',
        '    }',
        '    return result'
    ])
    
    return '\n'.join(code_lines)


def create_strategy_from_template(
    user_logic: str,
    datasource_ids: List[str],
    dictionary_ids: List[str] = None,
    compute_mode: str = "record",
    window_size: int = 5,
    window_type: str = "sliding"
) -> Dict[str, Any]:
    """基于 river 策略模板创建完整策略"""
    
    if dictionary_ids is None:
        dictionary_ids = []
    
    # 获取数据源信息（使用 data_schema）
    all_datasources = get_all_datasources()
    selected_datasources = [ds for ds in all_datasources if ds['id'] in datasource_ids]
    
    # 获取数据字典信息
    all_dictionaries = get_all_dictionaries()
    selected_dictionaries = [d for d in all_dictionaries if d['id'] in dictionary_ids]
    
    # 获取数据源的 data_schema
    datasource_schemas = [ds['data_schema'] for ds in selected_datasources if ds['data_schema']]
    
    # 分析数据字典格式
    dictionary_formats = []
    for d in selected_dictionaries:
        fmt = analyze_dictionary_format(d['func_code'])
        fmt['dictionary_name'] = d['name']
        dictionary_formats.append(fmt)
    
    # 整合数据格式
    integrated_format = integrate_data_formats(datasource_schemas, dictionary_formats)
    
    # 获取名称列表
    datasource_types = integrated_format.get('datasource_types', [])
    datasource_names = [ds['name'] for ds in selected_datasources]
    dictionary_names = [d['name'] for d in selected_dictionaries]
    
    # 自动生成策略字段
    strategy_id = generate_strategy_id()
    name = generate_strategy_name(user_logic, datasource_types, len(dictionary_ids) > 0)
    description = generate_strategy_description(name, user_logic, datasource_names, dictionary_names)
    diagram_info = generate_diagram_info(name, user_logic, datasource_types, len(dictionary_ids) > 0)
    func_code = generate_process_code(compute_mode, integrated_format, user_logic, dictionary_ids)
    
    # 构建完整的策略字典
    strategy_record = {
        "metadata": {
            "id": strategy_id,
            "name": name,
            "description": description,
            "tags": datasource_types + [fmt['type'] for fmt in dictionary_formats],
            "bound_datasource_id": datasource_ids[0] if datasource_ids else "",
            "bound_datasource_ids": datasource_ids,
            "dictionary_profile_ids": dictionary_ids,
            "compute_mode": compute_mode,
            "window_size": window_size,
            "window_type": window_type,
            "window_interval": "10s",
            "window_return_partial": False,
            "max_history_count": 300,
            "diagram_info": diagram_info,
            "category": "实验",
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
            "run_count": 0
        },
        "func_code": func_code,
        "was_running": False
    }
    
    return strategy_record


def save_strategy_to_db(strategy_record: Dict[str, Any]) -> str:
    """保存策略到数据库"""
    strategy_id = strategy_record['metadata']['id']
    db = NB('naja_strategies')
    db[strategy_id] = strategy_record
    return strategy_id


if __name__ == '__main__':
    print("策略创建辅助脚本 - 基于 river 模板（使用 data_schema）")
    print("=" * 70)
    
    # 测试获取数据源（使用 data_schema）
    print("\n可用数据源（使用 data_schema）：")
    datasources = get_all_datasources()
    for i, ds in enumerate(datasources, 1):
        schema_type = ds['data_schema'].get('type', 'unknown')
        print(f"{i}. [{schema_type}] {ds['name']}")
    
    # 测试创建策略（带数据字典）
    print("\n测试创建策略（使用 data_schema）：")
    test_strategy = create_strategy_from_template(
        user_logic="当股票价格超过100元且属于科技板块时发出警报",
        datasource_ids=["realtime_quant_5s"],
        dictionary_ids=["953b771d7e1d"],
        compute_mode="record"
    )
    
    print(f"策略名称: {test_strategy['metadata']['name']}")
    print(f"策略描述: {test_strategy['metadata']['description']}")
    print(f"绑定数据源: {test_strategy['metadata']['bound_datasource_ids']}")
    print(f"绑定数据字典: {test_strategy['metadata']['dictionary_profile_ids']}")
    print(f"代码预览:\n{test_strategy['func_code'][:800]}...")
