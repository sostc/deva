#!/usr/bin/env python3
"""Naja 配置管理 CLI

提供命令行工具来管理配置文件（文件配置 vs NB 配置）。

使用方法:
    python -m deva.naja.config.cli [command] [options]

命令:
    init                    初始化配置目录
    status                  查看迁移状态
    list [type]             列出配置
    migrate [type]          迁移配置到文件 (dry-run 默认)
    migrate [type] --apply  执行迁移
    export [name]           导出单个配置到文件
    import [name]           从文件导入到 NB
    create-example          创建示例配置
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def cmd_init(args):
    """初始化配置目录"""
    from deva.naja.config.file_config import ensure_config_dirs, create_example_configs

    print("📁 初始化配置目录...")
    ensure_config_dirs()
    print("   创建示例配置...")
    create_example_configs()
    print("✅ 完成！配置目录：")
    print("   - config/dictionaries/")
    print("   - config/tasks/")
    print("   - config/strategies/")
    print("   - config/datasources/")


def cmd_status(args):
    """查看迁移状态"""
    from deva.naja.config.migration import get_migration_status

    print("📊 迁移状态")
    print("-" * 50)

    status = get_migration_status()

    for config_type, info in status.items():
        nb_count = info['nb_count']
        file_count = info['file_count']
        nb_table = info['nb_table']

        print(f"\n【{config_type.upper()}】")
        print(f"   NB 表: {nb_table}")
        print(f"   NB 配置数: {nb_count}")
        print(f"   文件配置数: {file_count}")

        if nb_count > 0 and file_count == 0:
            print(f"   状态: ⚠️  全部在 NB，建议迁移")
        elif nb_count > 0 and file_count > 0:
            print(f"   状态: 🔄 部分迁移中")
        elif nb_count == 0 and file_count > 0:
            print(f"   状态: ✅ 全部迁移完成")
        else:
            print(f"   状态: ➖ 暂无配置")


def cmd_list(args):
    """列出配置"""
    from deva.naja.config.file_config import get_file_config_manager
    from deva import NB

    config_type = args.type or "all"

    nb_table_map = {
        'task': 'naja_tasks',
        'strategy': 'naja_strategies',
        'datasource': 'naja_datasources',
        'dictionary': 'naja_dictionary_entries',
    }

    if config_type == "all":
        for ct in ['task', 'strategy', 'datasource', 'dictionary']:
            _list_type(ct, nb_table_map.get(ct, ''))
    else:
        _list_type(config_type, nb_table_map.get(config_type, ''))


def _list_type(config_type: str, nb_table: str):
    """列出指定类型的配置"""
    from deva.naja.config.file_config import get_file_config_manager
    from deva import NB

    print(f"\n【{config_type.upper()}】")

    file_mgr = get_file_config_manager(config_type)
    file_names = file_mgr.list_names()

    print(f"  📁 文件配置 ({len(file_names)}):")
    if file_names:
        for name in sorted(file_names)[:10]:
            print(f"     - {name}")
        if len(file_names) > 10:
            print(f"     ... 还有 {len(file_names) - 10} 个")
    else:
        print(f"     (无)")

    if nb_table:
        try:
            db = NB(nb_table)
            nb_names = [data.get('name', k) for k, data in db.items() if isinstance(data, dict)]
            print(f"  💾 NB 配置 ({len(nb_names)}):")
            if nb_names:
                for name in sorted(nb_names)[:10]:
                    print(f"     - {name}")
                if len(nb_names) > 10:
                    print(f"     ... 还有 {len(nb_names) - 10} 个")
            else:
                print(f"     (无)")
        except Exception as e:
            print(f"  💾 NB 配置: (无法读取: {e})")


def cmd_migrate(args):
    """迁移配置到文件"""
    from deva.naja.config.migration import (
        migrate_tasks_to_file,
        migrate_strategies_to_file,
        migrate_datasources_to_file,
        migrate_all_to_file,
    )

    config_type = args.type or "all"
    dry_run = not args.apply

    if dry_run:
        print("🔍 预演模式（加 --apply 执行实际迁移）")
        print("-" * 50)

    if config_type == "all":
        result = migrate_all_to_file(dry_run=dry_run)
        _print_migrate_result("全部", result)
    elif config_type == "task":
        result = migrate_tasks_to_file(dry_run=dry_run)
        _print_migrate_result("任务", result)
    elif config_type == "strategy":
        result = migrate_strategies_to_file(dry_run=dry_run)
        _print_migrate_result("策略", result)
    elif config_type == "datasource":
        result = migrate_datasources_to_file(dry_run=dry_run)
        _print_migrate_result("数据源", result)
    else:
        print(f"❌ 未知类型: {config_type}")
        print("   支持的类型: task, strategy, datasource, all")


def _print_migrate_result(type_name: str, result: dict):
    """打印迁移结果"""
    if 'total' in result:
        total = result.get('total', {})
        success = total.get('success', 0)
        skip = total.get('skip', 0)
        error = total.get('error', 0)
        migrated = []
        for detail in result.get('details', {}).values():
            migrated.extend(detail.get('migrated', []))
    else:
        success = result.get('success', 0)
        skip = result.get('skip', 0)
        error = result.get('error', 0)
        migrated = result.get('migrated', [])

    print(f"\n📊 {type_name}迁移结果:")
    print(f"   ✅ 成功: {success}")
    print(f"   ⏭️  跳过: {skip}")
    print(f"   ❌ 错误: {error}")

    if result.get('dry_run'):
        print(f"\n   这是预演，实际未执行。")
        print(f"   加 --apply 执行实际迁移。")

    if migrated:
        print(f"\n   将迁移的配置:")
        for name in migrated[:20]:
            print(f"     - {name}")
        if len(migrated) > 20:
            print(f"     ... 还有 {len(migrated) - 20} 个")


def cmd_export(args):
    """导出单个配置到文件"""
    from deva.naja.config.file_config import get_file_config_manager
    from deva import NB

    name = args.name
    config_type = args.type

    if not config_type:
        print("❌ 需要指定 --type")
        return

    mgr = get_file_config_manager(config_type)

    nb_table_map = {
        'task': 'naja_tasks',
        'strategy': 'naja_strategies',
        'datasource': 'naja_datasources',
        'dictionary': 'naja_dictionary_entries',
    }

    nb_table = nb_table_map.get(config_type, '')
    if not nb_table:
        print(f"❌ 未知类型: {config_type}")
        return

    db = NB(nb_table)

    entry_id = None
    data = None
    for k, v in db.items():
        if isinstance(v, dict) and v.get('name') == name:
            entry_id = k
            data = v
            break

    if not data:
        print(f"❌ 在 NB 中未找到: {name}")
        return

    print(f"📤 导出 {name} 到文件...")

    if config_type == 'task':
        from deva.naja.config.migration import task_entry_to_config_item
        item = task_entry_to_config_item(entry_id, data)
    elif config_type == 'strategy':
        from deva.naja.config.migration import strategy_entry_to_config_item
        item = strategy_entry_to_config_item(entry_id, data)
    elif config_type == 'datasource':
        from deva.naja.config.migration import datasource_entry_to_config_item
        item = datasource_entry_to_config_item(entry_id, data)
    else:
        print(f"❌ 不支持的类型: {config_type}")
        return

    if mgr.save(item):
        print(f"✅ 已导出到: config/{config_type}/{name}.yaml")
    else:
        print(f"❌ 导出失败")


def cmd_import(args):
    """从文件导入到 NB"""
    print("🔧 导入功能开发中...")
    print("   目前建议直接在 UI 中编辑后保存")


def cmd_cleanup(args):
    """清理 NB 中的重复数据"""
    from deva.naja.config.migration import cleanup_nb_duplicates

    dry_run = not args.apply

    if dry_run:
        print("🔍 预演模式（加 --apply 执行实际清理）")
        print("-" * 50)

    result = cleanup_nb_duplicates(dry_run=dry_run)

    print("\n📊 清理结果:")
    for config_type, info in result.items():
        deleted = info['deleted']
        kept = info['kept']
        print(f"\n【{config_type.upper()}】")
        print(f"   将删除: {deleted} 个")
        print(f"   保留: {kept} 个（NB中有但文件不存在）")

    if dry_run:
        print(f"\n   这是预演，实际未删除。")
        print(f"   加 --apply 执行实际清理。")


def main():
    parser = argparse.ArgumentParser(
        description="Naja 配置管理 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m deva.naja.config.cli init                    # 初始化
  python -m deva.naja.config.cli status                  # 查看状态
  python -m deva.naja.config.cli list task               # 列出任务
  python -m deva.naja.config.cli migrate task            # 预演迁移任务
  python -m deva.naja.config.cli migrate task --apply   # 执行迁移
  python -m deva.naja.config.cli cleanup                # 预演清理NB重复数据
  python -m deva.naja.config.cli cleanup --apply        # 执行清理
  python -m deva.naja.config.cli export my_task --type task  # 导出单个
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    parser_init = subparsers.add_parser('init', help='初始化配置目录')
    parser_init.set_defaults(func=cmd_init)

    parser_status = subparsers.add_parser('status', help='查看迁移状态')
    parser_status.set_defaults(func=cmd_status)

    parser_list = subparsers.add_parser('list', help='列出配置')
    parser_list.add_argument('type', nargs='?', default='all', help='类型: task, strategy, datasource, dictionary, all')
    parser_list.set_defaults(func=cmd_list)

    parser_migrate = subparsers.add_parser('migrate', help='迁移配置到文件')
    parser_migrate.add_argument('type', nargs='?', default='all', help='类型: task, strategy, datasource, all')
    parser_migrate.add_argument('--apply', action='store_true', help='执行实际迁移（默认只是预演）')
    parser_migrate.set_defaults(func=cmd_migrate)

    parser_export = subparsers.add_parser('export', help='导出单个配置到文件')
    parser_export.add_argument('name', help='配置名称')
    parser_export.add_argument('--type', required=True, help='类型: task, strategy, datasource')
    parser_export.set_defaults(func=cmd_export)

    parser_import = subparsers.add_parser('import', help='从文件导入到 NB（开发中）')
    parser_import.add_argument('name', help='配置名称')
    parser_import.add_argument('--type', required=True, help='类型')
    parser_import.set_defaults(func=cmd_import)

    parser_cleanup = subparsers.add_parser('cleanup', help='清理 NB 中的重复数据')
    parser_cleanup.add_argument('--apply', action='store_true', help='执行实际清理（默认只是预演）')
    parser_cleanup.set_defaults(func=cmd_cleanup)

    parser_create_example = subparsers.add_parser('create-example', help='创建示例配置')
    parser_create_example.set_defaults(func=lambda args: cmd_init(args))

    args = parser.parse_args()

    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
