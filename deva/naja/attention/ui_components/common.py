"""注意力系统 UI 通用数据获取函数"""

from typing import Dict, List, Any
import pandas as pd


def get_attention_integration():
    """获取注意力系统集成"""
    try:
        from deva.naja.attention_integration import get_attention_integration
        return get_attention_integration()
    except Exception:
        return None


def get_strategy_manager():
    """获取策略管理器"""
    try:
        from deva.naja.attention.strategies import get_strategy_manager
        return get_strategy_manager()
    except Exception:
        return None


def get_history_tracker():
    """获取历史追踪器"""
    try:
        from deva.naja.attention.history_tracker import get_history_tracker
        return get_history_tracker()
    except Exception:
        return None


def get_hot_sectors_and_stocks() -> Dict[str, Any]:
    """获取热门板块和股票"""
    integration = get_attention_integration()
    if not integration:
        return {"sectors": [], "stocks": []}

    try:
        sector_weights = integration.attention_system.sector_attention.get_all_weights(filter_noise=True) if integration.attention_system else {}
        symbol_weights = integration.attention_system.weight_pool.get_all_weights() if integration.attention_system else {}

        hot_sectors = sorted(
            [(sector, weight) for sector, weight in sector_weights.items()],
            key=lambda x: x[1], reverse=True
        )[:5]

        hot_stocks = sorted(
            [(symbol, weight) for symbol, weight in symbol_weights.items()],
            key=lambda x: x[1], reverse=True
        )[:20]

        return {"sectors": hot_sectors, "stocks": hot_stocks}
    except Exception:
        return {"sectors": [], "stocks": []}


def get_attention_report() -> Dict[str, Any]:
    """获取注意力系统报告"""
    integration = get_attention_integration()
    if integration:
        try:
            return integration.get_attention_report()
        except Exception:
            pass
    return {}


def get_strategy_stats() -> Dict[str, Any]:
    """获取策略统计"""
    manager = get_strategy_manager()
    if manager:
        try:
            return manager.get_all_stats()
        except Exception:
            pass
    return {}


def get_attention_changes():
    """获取注意力变化记录"""
    tracker = get_history_tracker()
    if tracker:
        try:
            return tracker.get_recent_changes(n=20)
        except Exception:
            pass
    return []


def get_attention_shift_report():
    """获取注意力转移报告"""
    tracker = get_history_tracker()
    if tracker:
        try:
            return tracker.get_attention_shift_report()
        except Exception:
            pass
    return {'has_shift': False}


def register_stock_names(data: pd.DataFrame):
    """注册股票名称到历史追踪器"""
    tracker = get_history_tracker()
    if tracker is None or data is None or data.empty:
        return

    try:
        if 'code' in data.columns and 'name' in data.columns:
            for _, row in data.iterrows():
                symbol = row['code']
                name = row.get('name', symbol)
                if symbol and name:
                    tracker.register_symbol_name(symbol, name)
    except Exception:
        pass


def is_attention_initialized():
    """检查注意力系统是否已初始化"""
    integration = get_attention_integration()
    if integration is None:
        return False
    return integration.attention_system is not None


def initialize_attention_system():
    """初始化注意力系统"""
    try:
        from deva.naja.attention_config import load_config
        from deva.naja.attention_integration import initialize_attention_system
        from pywebio.session import run_js
        from pywebio.output import toast

        config = load_config()
        if config.enabled:
            attention_system = initialize_attention_system(config)
            toast("✅ 注意力系统初始化成功！", color="success")
            run_js("setTimeout(() => window.location.reload(), 1000)")
        else:
            toast("⚠️ 注意力系统被禁用", color="warning")
    except Exception as e:
        from pywebio.output import toast
        toast(f"❌ 初始化失败: {e}", color="error")
