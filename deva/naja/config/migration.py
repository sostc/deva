"""配置迁移工具

提供从 NB 迁移配置到文件的工具。
采用保守策略：先创建新系统，验证后再逐步清理旧数据。
"""

import time
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from .file_config import (
    get_file_config_manager,
    ConfigFileItem,
    BaseConfigMetadata,
    TaskConfigMetadata,
    StrategyConfigMetadata,
    DatasourceConfigMetadata,
    TASK_CONFIG_DIR,
    STRATEGY_CONFIG_DIR,
    DATASOURCE_CONFIG_DIR,
)


TASK_TABLE = "naja_tasks"
STRATEGY_TABLE = "naja_strategies"
DATASOURCE_TABLE = "naja_datasources"


def task_entry_to_config_item(entry_id: str, data: Dict[str, Any]) -> Optional[ConfigFileItem]:
    """将 Task NB 条目转换为 ConfigFileItem"""
    if not data:
        return None

    meta_dict = data.get('metadata', {})
    name = meta_dict.get('name', entry_id) if meta_dict else entry_id

    task_metadata = TaskConfigMetadata(
        id=entry_id,
        name=name,
        description=meta_dict.get('description', ''),
        tags=meta_dict.get('tags', []),
        category=meta_dict.get('category', ''),
        created_at=meta_dict.get('created_at', 0),
        updated_at=meta_dict.get('updated_at', time.time()),
        enabled=meta_dict.get('enabled', True),
        source='file',
        task_type=meta_dict.get('task_type', 'timer'),
        execution_mode=meta_dict.get('execution_mode', 'timer'),
        interval_seconds=meta_dict.get('interval_seconds', 60.0),
        scheduler_trigger=meta_dict.get('scheduler_trigger', 'interval'),
        cron_expr=meta_dict.get('cron_expr', ''),
        run_at=meta_dict.get('run_at', ''),
        event_source=meta_dict.get('event_source', 'log'),
        event_condition=meta_dict.get('event_condition', ''),
        event_condition_type=meta_dict.get('event_condition_type', 'contains'),
        func_code_file='',
    )

    parameters = {
        'timeout': meta_dict.get('timeout', 30),
        'retry_count': meta_dict.get('retry_count', 3),
        'retry_delay': meta_dict.get('retry_delay', 5),
        'enabled': meta_dict.get('enabled', True),
    }

    config = {
        'task_type': meta_dict.get('task_type', 'timer'),
        'execution_mode': meta_dict.get('execution_mode', 'timer'),
        'scheduler_trigger': meta_dict.get('scheduler_trigger', 'interval'),
        'cron_expr': meta_dict.get('cron_expr', ''),
        'run_at': meta_dict.get('run_at', ''),
    }

    func_code = data.get('func_code', '') or data.get('code', '')

    return ConfigFileItem(
        name=name,
        config_type='task',
        metadata=task_metadata,
        parameters=parameters,
        config=config,
        func_code=func_code,
    )


def strategy_entry_to_config_item(entry_id: str, data: Dict[str, Any]) -> Optional[ConfigFileItem]:
    """将 Strategy NB 条目转换为 ConfigFileItem"""
    if not data:
        return None

    meta_dict = data.get('metadata', {})
    name = meta_dict.get('name', entry_id) if meta_dict else entry_id

    strategy_metadata = StrategyConfigMetadata(
        id=entry_id,
        name=name,
        description=meta_dict.get('description', ''),
        tags=meta_dict.get('tags', []),
        category=meta_dict.get('category', '默认'),
        created_at=meta_dict.get('created_at', 0),
        updated_at=meta_dict.get('updated_at', time.time()),
        enabled=meta_dict.get('enabled', True),
        source='nb',
        bound_datasource_id=meta_dict.get('bound_datasource_id', ''),
        bound_datasource_ids=meta_dict.get('bound_datasource_ids', []),
        compute_mode=meta_dict.get('compute_mode', 'record'),
        window_size=meta_dict.get('window_size', 5),
        window_type=meta_dict.get('window_type', 'sliding'),
        window_interval=meta_dict.get('window_interval', '10s'),
        window_return_partial=meta_dict.get('window_return_partial', False),
        dictionary_profile_ids=meta_dict.get('dictionary_profile_ids', []),
        max_history_count=meta_dict.get('max_history_count', 100),
        strategy_type=meta_dict.get('strategy_type', 'legacy'),
        handler_type=meta_dict.get('handler_type', 'unknown'),
        version=meta_dict.get('version', 1),
        func_code_file='',
    )

    parameters = {
        'enabled': meta_dict.get('enabled', True),
        'max_history_count': meta_dict.get('max_history_count', 100),
        'window_size': meta_dict.get('window_size', 5),
        'window_interval': meta_dict.get('window_interval', '10s'),
    }

    config = {
        'compute_mode': meta_dict.get('compute_mode', 'record'),
        'window_type': meta_dict.get('window_type', 'sliding'),
        'strategy_type': meta_dict.get('strategy_type', 'legacy'),
        'handler_type': meta_dict.get('handler_type', 'unknown'),
    }

    func_code = data.get('func_code', '') or data.get('code', '') or data.get('strategy_code', '')

    return ConfigFileItem(
        name=name,
        config_type='strategy',
        metadata=strategy_metadata,
        parameters=parameters,
        config=config,
        func_code=func_code,
    )


def datasource_entry_to_config_item(entry_id: str, data: Dict[str, Any]) -> Optional[ConfigFileItem]:
    """将 Datasource NB 条目转换为 ConfigFileItem"""
    if not data:
        return None

    meta_dict = data.get('metadata', {})
    name = meta_dict.get('name', entry_id) if meta_dict else entry_id

    ds_metadata = DatasourceConfigMetadata(
        id=entry_id,
        name=name,
        description=meta_dict.get('description', ''),
        tags=meta_dict.get('tags', []),
        category=meta_dict.get('category', ''),
        created_at=meta_dict.get('created_at', 0),
        updated_at=meta_dict.get('updated_at', time.time()),
        enabled=meta_dict.get('enabled', True),
        source='file',
        source_type=meta_dict.get('source_type', 'timer'),
        interval_seconds=meta_dict.get('interval', 5.0),
        enabled_types=meta_dict.get('enabled_types', []),
        func_code_file='',
    )

    parameters = {
        'enabled': meta_dict.get('enabled', True),
        'interval_seconds': meta_dict.get('interval', 5.0),
        'timeout': meta_dict.get('timeout', 30),
    }

    config = {
        'source_type': meta_dict.get('source_type', 'timer'),
        'config': meta_dict.get('config', {}),
    }

    func_code = data.get('func_code', '')

    return ConfigFileItem(
        name=name,
        config_type='datasource',
        metadata=ds_metadata,
        parameters=parameters,
        config=config,
        func_code=func_code,
    )


def migrate_tasks_to_file(dry_run: bool = False) -> Dict[str, Any]:
    """迁移 Task 配置到文件

    Args:
        dry_run: 如果为 True，只报告不实际迁移

    Returns:
        迁移结果统计
    """
    from deva import NB

    db = NB(TASK_TABLE)
    mgr = get_file_config_manager('task')

    success_count = 0
    skip_count = 0
    error_count = 0
    errors = []
    migrated_names = []

    for entry_id, data in list(db.items()):
        if not isinstance(data, dict):
            skip_count += 1
            continue

        try:
            item = task_entry_to_config_item(entry_id, data)
            if not item:
                skip_count += 1
                continue

            if mgr.exists(item.name):
                existing = mgr.get(item.name)
                if existing and existing.metadata.updated_at >= item.metadata.updated_at:
                    skip_count += 1
                    continue

            if dry_run:
                migrated_names.append(item.name)
                success_count += 1
            else:
                if mgr.save(item):
                    migrated_names.append(item.name)
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"{entry_id}: save failed")
        except Exception as e:
            error_count += 1
            errors.append(f"{entry_id}: {str(e)}")

    return {
        'type': 'task',
        'success': success_count,
        'skip': skip_count,
        'error': error_count,
        'migrated': migrated_names,
        'errors': errors[:10],
        'dry_run': dry_run,
    }


def migrate_strategies_to_file(dry_run: bool = False) -> Dict[str, Any]:
    """迁移 Strategy 配置到文件

    Args:
        dry_run: 如果为 True，只报告不实际迁移

    Returns:
        迁移结果统计
    """
    from deva import NB

    db = NB(STRATEGY_TABLE)
    mgr = get_file_config_manager('strategy')

    success_count = 0
    skip_count = 0
    error_count = 0
    errors = []
    migrated_names = []

    for entry_id, data in list(db.items()):
        if not isinstance(data, dict):
            skip_count += 1
            continue

        try:
            item = strategy_entry_to_config_item(entry_id, data)
            if not item:
                skip_count += 1
                continue

            if mgr.exists(item.name):
                existing = mgr.get(item.name)
                if existing and existing.metadata.updated_at >= item.metadata.updated_at:
                    skip_count += 1
                    continue

            if dry_run:
                migrated_names.append(item.name)
                success_count += 1
            else:
                if mgr.save(item):
                    migrated_names.append(item.name)
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"{entry_id}: save failed")
        except Exception as e:
            error_count += 1
            errors.append(f"{entry_id}: {str(e)}")

    return {
        'type': 'strategy',
        'success': success_count,
        'skip': skip_count,
        'error': error_count,
        'migrated': migrated_names,
        'errors': errors[:10],
        'dry_run': dry_run,
    }


def migrate_datasources_to_file(dry_run: bool = False) -> Dict[str, Any]:
    """迁移 Datasource 配置到文件

    Args:
        dry_run: 如果为 True，只报告不实际迁移

    Returns:
        迁移结果统计
    """
    from deva import NB

    db = NB(DATASOURCE_TABLE)
    mgr = get_file_config_manager('datasource')

    success_count = 0
    skip_count = 0
    error_count = 0
    errors = []
    migrated_names = []

    for entry_id, data in list(db.items()):
        if not isinstance(data, dict):
            skip_count += 1
            continue

        try:
            item = datasource_entry_to_config_item(entry_id, data)
            if not item:
                skip_count += 1
                continue

            if mgr.exists(item.name):
                existing = mgr.get(item.name)
                if existing and existing.metadata.updated_at >= item.metadata.updated_at:
                    skip_count += 1
                    continue

            if dry_run:
                migrated_names.append(item.name)
                success_count += 1
            else:
                if mgr.save(item):
                    migrated_names.append(item.name)
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"{entry_id}: save failed")
        except Exception as e:
            error_count += 1
            errors.append(f"{entry_id}: {str(e)}")

    return {
        'type': 'datasource',
        'success': success_count,
        'skip': skip_count,
        'error': error_count,
        'migrated': migrated_names,
        'errors': errors[:10],
        'dry_run': dry_run,
    }


def migrate_all_to_file(dry_run: bool = False) -> Dict[str, Any]:
    """迁移所有配置到文件

    Args:
        dry_run: 如果为 True，只报告不实际迁移

    Returns:
        所有迁移结果的汇总
    """
    results = {
        'task': migrate_tasks_to_file(dry_run),
        'strategy': migrate_strategies_to_file(dry_run),
        'datasource': migrate_datasources_to_file(dry_run),
    }

    total_success = sum(r['success'] for r in results.values())
    total_skip = sum(r['skip'] for r in results.values())
    total_error = sum(r['error'] for r in results.values())

    return {
        'total': {
            'success': total_success,
            'skip': total_skip,
            'error': total_error,
        },
        'details': results,
        'dry_run': dry_run,
    }


def get_migration_status() -> Dict[str, Any]:
    """获取当前迁移状态

    比较 NB 和文件中的配置数量和状态
    """
    from deva import NB

    status = {}

    for config_type, nb_table in [
        ('task', TASK_TABLE),
        ('strategy', STRATEGY_TABLE),
        ('datasource', DATASOURCE_TABLE),
    ]:
        db = NB(nb_table)
        nb_count = len([k for k, v in list(db.items()) if isinstance(v, dict)])

        mgr = get_file_config_manager(config_type)
        file_count = len(mgr.list_names())

        status[config_type] = {
            'nb_count': nb_count,
            'file_count': file_count,
            'nb_table': nb_table,
        }

    return status


def create_example_files():
    """创建示例配置文件"""
    from .file_config import ensure_config_dirs

    ensure_config_dirs()

    task_example = {
        'metadata': {
            'id': 'example_task',
            'name': '示例任务',
            'description': '这是一个示例任务配置',
            'tags': ['示例'],
            'category': '示例',
            'enabled': True,
        },
        'parameters': {
            'timeout': 30,
            'retry_count': 3,
        },
        'config': {
            'task_type': 'timer',
            'execution_mode': 'timer',
            'interval_seconds': 60.0,
        },
        'func_code': '''def execute():
    print("Hello from example task")
'''
    }

    strategy_example = {
        'metadata': {
            'id': 'example_strategy',
            'name': '示例策略',
            'description': '这是一个示例策略配置',
            'tags': ['示例'],
            'category': '示例',
            'enabled': True,
        },
        'parameters': {
            'window_size': 5,
            'max_history_count': 100,
        },
        'config': {
            'compute_mode': 'record',
            'window_type': 'sliding',
            'strategy_type': 'legacy',
        },
        'func_code': '''def compute(data):
    return {"signal": "hold"}
'''
    }

    datasource_example = {
        'metadata': {
            'id': 'example_datasource',
            'name': '示例数据源',
            'description': '这是一个示例数据源配置',
            'tags': ['示例'],
            'category': '示例',
            'enabled': True,
        },
        'parameters': {
            'interval_seconds': 5.0,
            'timeout': 30,
        },
        'config': {
            'source_type': 'timer',
        },
        'func_code': '''def fetch():
    return []
'''
    }

    for path, example in [
        (TASK_CONFIG_DIR / '_examples' / 'example_task.yaml', task_example),
        (STRATEGY_CONFIG_DIR / '_examples' / 'example_strategy.yaml', strategy_example),
        (DATASOURCE_CONFIG_DIR / '_examples' / 'example_datasource.yaml', datasource_example),
    ]:
        try:
            import yaml
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(example, f, allow_unicode=True, default_flow_style=False)
            print(f"[Migration] Created example: {path}")
        except Exception as e:
            print(f"[Migration] Create example failed: {e}")


def cleanup_nb_duplicates(dry_run: bool = True) -> Dict[str, Any]:
    """清理 NB 中的重复数据（文件已存在则删除 NB）

    保守策略：只删除 NB 中与文件同名的配置，保留文件不存在的配置

    Args:
        dry_run: 如果为 True，只报告不实际删除

    Returns:
        清理结果统计
    """
    from deva import NB

    results = {}

    for config_type, nb_table in [
        ('task', TASK_TABLE),
        ('strategy', STRATEGY_TABLE),
        ('datasource', DATASOURCE_TABLE),
    ]:
        db = NB(nb_table)
        file_mgr = get_file_config_manager(config_type)
        file_names = set(file_mgr.list_names())

        deleted_count = 0
        kept_count = 0
        to_delete = []

        for entry_id, data in list(db.items()):
            if not isinstance(data, dict):
                continue

            metadata = data.get('metadata', {})
            name = metadata.get('name', '') if metadata else ''

            if name in file_names:
                to_delete.append(entry_id)
                deleted_count += 1
            else:
                kept_count += 1

        if not dry_run:
            for entry_id in to_delete:
                try:
                    del db[entry_id]
                except Exception:
                    pass

        results[config_type] = {
            'deleted': deleted_count,
            'kept': kept_count,
            'dry_run': dry_run,
        }

    return results


__all__ = [
    'TASK_TABLE',
    'STRATEGY_TABLE',
    'DATASOURCE_TABLE',
    'task_entry_to_config_item',
    'strategy_entry_to_config_item',
    'datasource_entry_to_config_item',
    'migrate_tasks_to_file',
    'migrate_strategies_to_file',
    'migrate_datasources_to_file',
    'migrate_all_to_file',
    'get_migration_status',
    'create_example_files',
]
