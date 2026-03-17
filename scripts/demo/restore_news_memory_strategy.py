#!/usr/bin/env python3
"""恢复新闻舆情记忆策略的代码"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva.naja.strategy import get_strategy_manager


def restore_news_memory_strategy():
    """恢复新闻舆情记忆策略的代码"""
    strategy_mgr = get_strategy_manager()
    strategy_mgr.load_from_db()

    strategy_name = "新闻舆情记忆"

    entry = strategy_mgr.get_by_name(strategy_name)
    if not entry:
        print(f"[ERROR] 未找到策略: {strategy_name}")
        return False

    print(f"[INFO] 找到策略: {strategy_name} (ID: {entry.id})")

    strategy_code = '''"""
新闻舆情记忆策略 - 实时记忆系统

流式学习 + 分层记忆 + 周期性自我反思
实时分析tick、新闻、文本数据，生成主题信号和注意力信号
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva.naja.memory import get_memory_engine

_radar = get_memory_engine()

def process(data):
    """
    处理单条记录（naja策略接口）

    Args:
        data: 数据源记录

    Returns:
        信号列表或处理结果
    """
    if data is None:
        return None

    signals = _radar.process_record(data)

    for signal in signals:
        print(f"[NEWS_MEMORY_SIGNAL] {signal.get('type', 'unknown')}: {signal.get('message', signal.get('content', ''))}")

    return {
        "signals": signals,
        "stats": _radar.get_memory_report(),
    }

def process_window(records):
    """
    处理窗口数据

    Args:
        records: 记录列表

    Returns:
        处理结果
    """
    signals = _radar.process_window(records)
    return {
        "signals": signals,
        "window_size": len(records) if records else 0,
        "stats": _radar.get_memory_report(),
    }

def get_report():
    """获取记忆报告"""
    return _radar.get_memory_report()

def get_thought_report():
    """获取思想报告"""
    return _radar.generate_thought_report()
'''

    result = entry.update_config(
        func_code=strategy_code,
    )

    if result.get("success"):
        print(f"[SUCCESS] 策略代码已恢复")
        print(f"  - 代码长度: {len(strategy_code)} chars")
    else:
        print(f"[ERROR] 更新失败: {result.get('error')}")
        return False

    return True


if __name__ == "__main__":
    success = restore_news_memory_strategy()
    if success:
        print("\n✅ 新闻舆情记忆策略代码已恢复！")
    else:
        print("\n❌ 恢复失败")
