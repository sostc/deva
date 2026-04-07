#!/usr/bin/env python3
"""单例替换脚本 - 将 get_xxx() 替换为 SR('xxx')

使用方式:
    python scripts/replace_singleton_getters.py [--dry-run]

参数:
    --dry-run: 只显示将要进行的替换，不实际修改文件
"""

import os
import re
import sys

# 需要替换的映射表：(旧函数名, 新名称)
# 注意：只替换已在注册表中注册的单例
REPLACEMENTS = {
    # attention 系统核心单例
    'get_attention_integration()': "SR('attention_integration')",
    'get_attention_os()': "SR('attention_os')",
    'get_trading_center()': "SR('trading_center')",
    'get_mode_manager()': "SR('mode_manager')",
    'get_signal_executor()': "SR('signal_executor')",
    'get_data_processor()': "SR('data_processor')",

    # 应用层单例
    'get_attention_fusion()': "SR('attention_fusion')",
    'get_portfolio()': "SR('portfolio')",
    'get_attention_focus_manager()': "SR('focus_manager')",
    'get_conviction_validator()': "SR('conviction_validator')",
    'get_blind_spot_investigator()': "SR('blind_spot_investigator')",
    'get_snapshot_manager()': "SR('snapshot_manager')",

    # bandit 模块单例
    'get_market_data_bus()': "SR('market_data_bus')",
    'get_market_observer()': "SR('market_observer')",
    'get_stock_sector_map()': "SR('stock_sector_map')",

    # 认知模块单例
    'get_cognition_bus()': "SR('cognition_bus')",
    'get_history_tracker()': "SR('history_tracker')",
    'get_text_pipeline()': "SR('text_pipeline')",
    'get_attention_router()': "SR('attention_router')",
    'get_cross_signal_analyzer()': "SR('cross_signal_analyzer')",
    'get_narrative_block_linker()': "SR('narrative_block_linker')",
    'get_llm_reflection_engine()': "SR('llm_reflection_engine')",

    # 处理模块单例
    'get_noise_manager()': "SR('noise_manager')",
    'get_block_noise_detector()': "SR('block_noise_detector')",
    'get_state_querier()': "SR('state_querier')",
    'get_block_registry()': "SR('block_registry')",

    # 策略模块单例
    'get_strategy_manager()': "SR('strategy_manager')",

    # 其他单例
    'get_data_fetcher()': "SR('realtime_data_fetcher')",
    'get_manas_manager()': "SR('manas_manager')",
    'get_auto_tuner()': "SR('auto_tuner')",
    'get_liquidity_manager()': "SR('liquidity_manager')",
    'get_replay_scheduler()': "SR('daily_review_scheduler')",
    'get_cognition_orchestrator()': "SR('cognition_orchestrator')",

    # 基础层
    'get_stock_registry()': "SR('stock_registry')",
    'get_datasource_manager()': "SR('datasource_manager')",
}

# 不需要替换的函数（不在注册表中，或者是其他类型的函数）
SKIP_PATTERNS = [
    'get_registry_status',
    'get_last_boot_report',
    'get_system_bootstrap',
    'get_dictionary_manager',
    'get_task_manager',
    'get_supervisor',
    'get_signal_stream',
    'get_merrill_clock_engine',
    'get_running_replay_id',
    'get_naja_config',
    'get_radar_config',
    'get_bandit_notifier',
    'get_noise_filter',
    'get_tick_noise_filter',
    'get_attention_report',
    'get_hot_sectors_and_stocks',
    'get_strategy_stats',
    'get_attention_changes',
    'get_attention_shift_report',
    'get_ui_mode_context',
    'get_market_phase_summary',
    'get_attention_monitor_data',
    'get_system_capability_summary',
    'get_attention_snapshots',
    'get_classic_moments',
    'get_intelligence_system',
    'get_sector_name',
    'get_primary_strategy',
    'get_secondary_strategies',
    'get_strategy_principles',
    'get_strategy_indicators',
    'get_all_strategies_for_value',
    'get_linked_blocks',
    'get_linked_markets',
    'get_market_config',
    'get_linked_narratives',
    'get_linked_narratives_for_market',
    'get_narrative_category',
    'get_report_generator',
    'get_replay_history',
    'get_price_monitor',
    'get_us_attention_data',
    'get_us_market_summary',
    'get_attention_kernel',
    'get_default_heads',
    'get_regime_aware_heads',
    '_get_',  # 内部函数
]


def should_skip(line: str, old_pattern: str) -> bool:
    """检查是否应该跳过这行"""
    for skip in SKIP_PATTERNS:
        if skip in line:
            return True
    # 检查是否是注释
    if line.strip().startswith('#'):
        return True
    # 检查是否在字符串中
    if '"' in line or "'" in line:
        # 简单检查：如果 get_xxx() 在引号内则跳过
        for skip in SKIP_PATTERNS:
            if f'"{skip}' in line or f"'{skip}" in line:
                return True
    return False


def replace_in_file(filepath: str, dry_run: bool = True) -> list:
    """替换文件中的单例获取函数"""
    changes = []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')

    new_lines = []
    modified = False

    for i, line in enumerate(lines):
        new_line = line
        for old_pattern, new_pattern in REPLACEMENTS.items():
            if old_pattern in line:
                if should_skip(line, old_pattern):
                    continue
                new_line = new_line.replace(old_pattern, new_pattern)
                if new_line != line:
                    changes.append({
                        'file': filepath,
                        'line': i + 1,
                        'old': line.strip(),
                        'new': new_line.strip(),
                        'pattern': old_pattern,
                    })
                    modified = True

        new_lines.append(new_line)

    if not dry_run and modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))

    return changes


def main():
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("🔍 DRY RUN 模式 - 只会显示将要进行的替换，不会实际修改文件")
    else:
        print("⚠️  正式模式 - 将实际修改文件")

    naja_dir = os.path.join(os.path.dirname(__file__), '..', 'deva', 'naja')

    all_changes = []
    files_to_process = []

    for root, dirs, files in os.walk(naja_dir):
        # 跳过 __pycache__
        dirs[:] = [d for d in dirs if d != '__pycache__']

        for filename in files:
            if filename.endswith('.py'):
                filepath = os.path.join(root, filename)
                files_to_process.append(filepath)

    print(f"\n📁 将扫描 {len(files_to_process)} 个 Python 文件...\n")

    for filepath in files_to_process:
        try:
            changes = replace_in_file(filepath, dry_run=dry_run)
            all_changes.extend(changes)
        except Exception as e:
            print(f"❌ 处理文件失败: {filepath} - {e}")

    # 按文件分组显示
    print("\n" + "=" * 80)
    print(f"📊 替换统计: {len(all_changes)} 处修改")
    print("=" * 80)

    changes_by_file = {}
    for change in all_changes:
        f = change['file']
        if f not in changes_by_file:
            changes_by_file[f] = []
        changes_by_file[f].append(change)

    for filepath, file_changes in sorted(changes_by_file.items()):
        rel_path = os.path.relpath(filepath, os.path.dirname(__file__))
        print(f"\n📄 {rel_path} ({len(file_changes)} 处)")
        for change in file_changes[:5]:  # 只显示前5处
            print(f"   L{change['line']}: {change['pattern']}")
            print(f"       → {change['new']}")
        if len(file_changes) > 5:
            print(f"   ... 还有 {len(file_changes) - 5} 处")

    if dry_run:
        print("\n" + "=" * 80)
        print("💡 要执行实际替换，请运行: python scripts/replace_singleton_getters.py")
    else:
        print("\n" + "=" * 80)
        print("✅ 替换完成！")


if __name__ == '__main__':
    main()
