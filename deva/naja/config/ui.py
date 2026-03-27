"""统一配置编辑器 UI

提供统一的 UI 来编辑文件配置和 NB 配置。
支持双源：文件配置 和 NB 配置。
"""

from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass


@dataclass
class ConfigEditorField:
    """配置编辑器字段"""
    name: str
    label: str
    field_type: str  # "text", "number", "bool", "select", "code", "textarea", "json"
    default: Any = None
    options: List[Dict[str, str]] = None  # select 类型的选项
    rows: int = 5  # textarea 的行数
    code_language: str = "python"  # code 类型的语言
    required: bool = False
    description: str = ""


class ConfigSchema:
    """配置架构定义"""

    TASK_SCHEMA = {
        'metadata': [
            ConfigEditorField('name', '名称', 'text', required=True),
            ConfigEditorField('description', '描述', 'textarea'),
            ConfigEditorField('category', '分类', 'text'),
            ConfigEditorField('tags', '标签', 'text', description='逗号分隔'),
            ConfigEditorField('enabled', '启用', 'bool', default=True),
        ],
        'parameters': [
            ConfigEditorField('timeout', '超时时间(秒)', 'number', default=30),
            ConfigEditorField('retry_count', '重试次数', 'number', default=3),
            ConfigEditorField('retry_delay', '重试延迟(秒)', 'number', default=5),
        ],
        'config': [
            ConfigEditorField('task_type', '任务类型', 'select',
                            options=[{'label': '定时器', 'value': 'timer'},
                                   {'label': '调度器', 'value': 'scheduler'},
                                   {'label': '事件触发', 'value': 'event_trigger'}]),
            ConfigEditorField('execution_mode', '执行模式', 'select',
                            options=[{'label': 'Timer', 'value': 'timer'},
                                   {'label': 'Scheduler', 'value': 'scheduler'},
                                   {'label': 'EventTrigger', 'value': 'event_trigger'}]),
            ConfigEditorField('interval_seconds', '间隔(秒)', 'number', default=60),
            ConfigEditorField('scheduler_trigger', '调度触发', 'select',
                            options=[{'label': '间隔', 'value': 'interval'},
                                   {'label': 'Cron', 'value': 'cron'},
                                   {'label': '指定时间', 'value': 'date'}]),
            ConfigEditorField('cron_expr', 'Cron表达式', 'text'),
            ConfigEditorField('event_source', '事件源', 'text'),
            ConfigEditorField('event_condition', '事件条件', 'text'),
        ],
        'func_code': [
            ConfigEditorField('func_code', '执行代码', 'code', rows=15),
        ],
    }

    STRATEGY_SCHEMA = {
        'metadata': [
            ConfigEditorField('name', '名称', 'text', required=True),
            ConfigEditorField('description', '描述', 'textarea'),
            ConfigEditorField('category', '分类', 'text'),
            ConfigEditorField('tags', '标签', 'text'),
            ConfigEditorField('enabled', '启用', 'bool', default=True),
        ],
        'parameters': [
            ConfigEditorField('window_size', '窗口大小', 'number', default=5),
            ConfigEditorField('window_interval', '窗口间隔', 'text', default='10s'),
            ConfigEditorField('max_history_count', '最大历史数', 'number', default=100),
        ],
        'config': [
            ConfigEditorField('bound_datasource_id', '绑定的数据源ID', 'text'),
            ConfigEditorField('compute_mode', '计算模式', 'select',
                            options=[{'label': 'Record', 'value': 'record'},
                                   {'label': 'Batch', 'value': 'batch'}]),
            ConfigEditorField('window_type', '窗口类型', 'select',
                            options=[{'label': 'Sliding', 'value': 'sliding'},
                                   {'label': 'Tumbling', 'value': 'tumbling'}]),
            ConfigEditorField('strategy_type', '策略类型', 'select',
                            options=[{'label': 'Legacy', 'value': 'legacy'},
                                   {'label': 'River', 'value': 'river'},
                                   {'label': 'Plugin', 'value': 'plugin'}]),
            ConfigEditorField('handler_type', '处理器类型', 'select',
                            options=[{'label': 'Unknown', 'value': 'unknown'},
                                   {'label': 'Radar', 'value': 'radar'},
                                   {'label': 'Memory', 'value': 'memory'},
                                   {'label': 'Bandit', 'value': 'bandit'},
                                   {'label': 'LLM', 'value': 'llm'}]),
        ],
        'func_code': [
            ConfigEditorField('func_code', '策略代码', 'code', rows=15),
        ],
    }

    DATASOURCE_SCHEMA = {
        'metadata': [
            ConfigEditorField('name', '名称', 'text', required=True),
            ConfigEditorField('description', '描述', 'textarea'),
            ConfigEditorField('category', '分类', 'text'),
            ConfigEditorField('tags', '标签', 'text'),
            ConfigEditorField('enabled', '启用', 'bool', default=True),
        ],
        'parameters': [
            ConfigEditorField('interval_seconds', '间隔(秒)', 'number', default=5),
            ConfigEditorField('timeout', '超时时间(秒)', 'number', default=30),
            ConfigEditorField('batch_size', '批次大小', 'number', default=100),
        ],
        'config': [
            ConfigEditorField('source_type', '数据源类型', 'select',
                            options=[{'label': 'Timer', 'value': 'timer'},
                                   {'label': 'File', 'value': 'file'},
                                   {'label': 'Directory', 'value': 'directory'},
                                   {'label': 'Replay', 'value': 'replay'},
                                   {'label': 'Custom', 'value': 'custom'}]),
        ],
        'func_code': [
            ConfigEditorField('func_code', '数据获取代码', 'code', rows=15),
        ],
    }

    DICTIONARY_SCHEMA = {
        'metadata': [
            ConfigEditorField('name', '名称', 'text', required=True),
            ConfigEditorField('description', '描述', 'textarea'),
            ConfigEditorField('category', '分类', 'text'),
            ConfigEditorField('tags', '标签', 'text'),
            ConfigEditorField('enabled', '启用', 'bool', default=True),
        ],
        'parameters': [
            ConfigEditorField('refresh_interval', '刷新间隔(秒)', 'number', default=300),
            ConfigEditorField('max_cache_size', '最大缓存', 'number', default=10000),
        ],
        'config': [
            ConfigEditorField('dict_type', '字典类型', 'select',
                            options=[{'label': '维表', 'value': 'dimension'},
                                   {'label': '映射', 'value': 'mapping'},
                                   {'label': '股票板块', 'value': 'stock_basic_block'},
                                   {'label': '股票基础', 'value': 'stock_basic'},
                                   {'label': '行业', 'value': 'industry'}]),
            ConfigEditorField('source_mode', '数据来源', 'select',
                            options=[{'label': '仅上传', 'value': 'upload'},
                                   {'label': '仅任务', 'value': 'task'},
                                   {'label': '上传+任务', 'value': 'upload_and_task'}]),
            ConfigEditorField('execution_mode', '执行模式', 'select',
                            options=[{'label': 'Timer', 'value': 'timer'},
                                   {'label': 'Scheduler', 'value': 'scheduler'}]),
            ConfigEditorField('cron_expr', 'Cron表达式', 'text'),
        ],
        'func_code': [
            ConfigEditorField('func_code', '数据获取代码', 'code', rows=15),
        ],
    }

    @classmethod
    def get_schema(cls, config_type: str) -> Dict[str, List[ConfigEditorField]]:
        """获取指定类型的架构"""
        mapping = {
            'task': cls.TASK_SCHEMA,
            'strategy': cls.STRATEGY_SCHEMA,
            'datasource': cls.DATASOURCE_SCHEMA,
            'dictionary': cls.DICTIONARY_SCHEMA,
        }
        return mapping.get(config_type, {})


def build_editor_form(config_type: str, data: Dict[str, Any]) -> List:
    """根据配置类型和数据构建表单字段列表

    Args:
        config_type: 配置类型
        data: 当前配置数据

    Returns:
        pywebio 表单字段列表
    """
    from pywebio.input import input, input_group, textarea, select, actions

    schema = ConfigSchema.get_schema(config_type)
    fields = []

    sections = [
        ('metadata', '基本信息'),
        ('parameters', '控制参数'),
        ('config', '高级配置'),
        ('func_code', '执行代码'),
    ]

    for section_key, section_label in sections:
        if section_key not in schema:
            continue

        section_fields = schema[section_key]

        for field in section_fields:
            section_data = data.get(section_key, {})

            if field.field_type == 'text':
                fields.append(input(
                    field.label,
                    name=f"{section_key}.{field.name}",
                    value=section_data.get(field.name, field.default),
                    placeholder=field.description or None
                ))
            elif field.field_type == 'number':
                fields.append(input(
                    field.label,
                    name=f"{section_key}.{field.name}",
                    type='number',
                    value=section_data.get(field.name, field.default),
                ))
            elif field.field_type == 'bool':
                value = section_data.get(field.name, field.default)
                fields.append(select(
                    field.label,
                    name=f"{section_key}.{field.name}",
                    options=[{'label': '是', 'value': True}, {'label': '否', 'value': False}],
                    value=value,
                ))
            elif field.field_type == 'select':
                fields.append(select(
                    field.label,
                    name=f"{section_key}.{field.name}",
                    options=field.options or [],
                    value=section_data.get(field.name, field.default),
                ))
            elif field.field_type == 'textarea':
                fields.append(textarea(
                    field.label,
                    name=f"{section_key}.{field.name}",
                    value=section_data.get(field.name, field.default) or '',
                    rows=field.rows,
                    placeholder=field.description or None
                ))
            elif field.field_type == 'code':
                fields.append(textarea(
                    field.label,
                    name=f"{section_key}.{field.name}",
                    value=section_data.get(field.name, field.default) or '',
                    rows=field.rows,
                    code={'mode': field.code_language},
                ))

    return fields


def parse_editor_form(config_type: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """解析表单数据，组装回配置结构

    Args:
        config_type: 配置类型
        form_data: 表单数据

    Returns:
        组装后的配置数据
    """
    schema = ConfigSchema.get_schema(config_type)
    result = {
        'metadata': {},
        'parameters': {},
        'config': {},
        'func_code': '',
    }

    for section_key in result.keys():
        if section_key not in schema:
            continue

        section_data = {}
        for field in schema[section_key]:
            key = f"{section_key}.{field.name}"
            if key in form_data:
                value = form_data[key]
                if field.field_type == 'number' and value:
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        pass
                section_data[field.name] = value

        if section_key == 'func_code' and 'func_code.func_code' in form_data:
            result['func_code'] = form_data['func_code.func_code']
        else:
            result[section_key] = section_data

    return result


async def render_config_editor(
    ctx: dict,
    config_type: str,
    config_name: str,
    config_data: Dict[str, Any],
    source: str = "file",
    on_save: Callable = None,
    on_cancel: Callable = None,
):
    """渲染配置编辑器

    Args:
        ctx: pywebio 上下文
        config_type: 配置类型
        config_name: 配置名称
        config_data: 配置数据
        source: 数据来源 "file" 或 "nb"
        on_save: 保存回调
        on_cancel: 取消回调
    """
    from pywebio.output import put_html, put_buttons, popup, close_popup
    from pywebio.input import input_group, actions

    title = f"编辑配置: {config_name}"
    if source == "file":
        title += " [文件配置]"
    else:
        title += " [NB配置]"

    with popup(title, size="large", closable=True):
        put_html(f"<p style='color:#666;font-size:13px;'>来源: {source}</p>")

        fields = build_editor_form(config_type, config_data)
        fields.append(actions("操作", [
            {"label": "💾 保存", "value": "save", "color": "primary"},
            {"label": "📁 另存为文件", "value": "save_as_file", "color": "info"},
            {"label": "取消", "value": "cancel"},
        ], name="action"))

        form = await input_group("配置信息", fields)

        if not form or form.get('action') == 'cancel':
            if on_cancel:
                await on_cancel()
            return

        parsed = parse_editor_form(config_type, form)

        if form.get('action') == 'save_as_file':
            await _save_as_file(ctx, config_type, config_name, parsed)
            return

        if on_save:
            success = await on_save(parsed, source=source)
            if success:
                ctx["toast"]("保存成功", color="success")
            else:
                ctx["toast"]("保存失败", color="error")


async def _save_as_file(ctx, config_type: str, config_name: str, config_data: Dict[str, Any]):
    """另存为文件配置"""
    from pywebio.output import toast, put_input, put_text, put_buttons, popup, close_popup
    from pywebio.input import input, actions

    try:
        from ..config.file_config import get_file_config_manager, ConfigFileItem, BaseConfigMetadata

        mgr = get_file_config_manager(config_type)

        item = mgr.get(config_name)
        if item:
            metadata = item.metadata
        else:
            metadata = BaseConfigMetadata(name=config_name)

        metadata.source = 'file'

        new_item = ConfigFileItem(
            name=config_name,
            config_type=config_type,
            metadata=metadata,
            parameters=config_data.get('parameters', {}),
            config=config_data.get('config', {}),
            func_code=config_data.get('func_code', ''),
        )

        if mgr.save(new_item):
            ctx["toast"]("已保存为文件配置", color="success")
        else:
            ctx["toast"]("保存失败", color="error")
    except Exception as e:
        ctx["toast"](f"保存失败: {e}", color="error")


async def render_config_list(ctx: dict, config_type: str):
    """渲染配置列表页面

    Args:
        ctx: pywebio 上下文
        config_type: 配置类型 ("task", "strategy", "datasource", "dictionary")
    """
    from pywebio.output import put_html, put_table, put_buttons, clear, popup
    from pywebio.input import actions
    from deva.naja.config.file_config import get_file_config_manager
    from deva import NB

    scope_name = f"{config_type}_list"

    def render_list_content():
        clear(scope_name)

        nb_table_map = {
            'task': 'naja_tasks',
            'strategy': 'naja_strategies',
            'datasource': 'naja_datasources',
            'dictionary': 'naja_dictionary_entries',
        }

        nb_table = nb_table_map.get(config_type, '')
        file_mgr = get_file_config_manager(config_type)

        file_names = set(file_mgr.list_names())

        nb_items = []
        if nb_table:
            try:
                db = NB(nb_table)
                for entry_id, data in list(db.items()):
                    if isinstance(data, dict) and data.get('name'):
                        nb_items.append({
                            'id': entry_id,
                            'name': data.get('name', ''),
                            'source': 'nb',
                            'data': data,
                        })
            except Exception:
                pass

        table_data = []

        for name in sorted(file_names):
            item = file_mgr.get(name)
            if not item:
                continue

            edit_btn = put_buttons(
                [{"label": "编辑", "value": f"edit_file_{name}", "color": "primary"}],
                onclick=lambda v, n=name: None
            )

            table_data.append([
                name,
                "📁 文件",
                item.metadata.category or '-',
                len(item.func_code) if item.func_code else 0,
                edit_btn,
            ])

        for nb_item in nb_items:
            name = nb_item['name']
            if name in file_names:
                continue

            edit_btn = put_buttons(
                [{"label": "编辑", "value": f"edit_nb_{name}", "color": "info"}],
                onclick=lambda v, n=name, d=nb_item['data']: None
            )

            migrate_btn = put_buttons(
                [{"label": "迁移", "value": f"migrate_{name}", "color": "warning"}],
                onclick=lambda v, n=name: None
            )

            table_data.append([
                name,
                "💾 NB",
                nb_item['data'].get('category', '-') or '-',
                len(nb_item['data'].get('func_code', '')) if nb_item['data'].get('func_code') else 0,
                edit_btn,
                migrate_btn,
            ])

        put_html(f"<h4>{config_type.capitalize()} 配置列表</h4>", scope=scope_name)

        if table_data:
            headers = ["名称", "来源", "分类", "代码行数", "操作", "迁移"]
            if all(len(row) == 5 for row in table_data):
                headers = ["名称", "来源", "分类", "代码行数", "操作"]
            put_table(table_data, header=headers, scope=scope_name)
        else:
            put_html('<div style="padding:20px;text-align:center;color:#999;">暂无配置</div>', scope=scope_name)

        put_html('<div style="margin-top:16px;display:flex;gap:12px;">', scope=scope_name)
        put_buttons(
            [{"label": "➕ 新建配置", "value": "create", "color": "primary"}],
            onclick=lambda v: None,
            scope=scope_name
        )
        put_buttons(
            [{"label": "🔄 刷新", "value": "refresh", "color": "default"}],
            onclick=lambda v: None,
            scope=scope_name
        )
        put_html("</div>", scope=scope_name)

    render_list_content()


__all__ = [
    'ConfigEditorField',
    'ConfigSchema',
    'build_editor_form',
    'parse_editor_form',
    'render_config_editor',
    'render_config_list',
]
