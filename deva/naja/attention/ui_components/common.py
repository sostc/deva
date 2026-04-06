"""注意力系统 UI 通用数据获取函数"""

from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import os
import logging

def _lab_debug_log(msg: str):
    """实验室模式调试日志"""
    if os.environ.get("NAJA_LAB_DEBUG") == "true":
        logging.getLogger(__name__).info(f"[Lab-Debug-UI] {msg}")


def get_attention_integration():
    """获取注意力系统集成"""
    try:
        from deva.naja.attention.integration import get_attention_integration
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
        from deva.naja.cognition.history_tracker import get_history_tracker
        return get_history_tracker()
    except Exception:
        return None


def _is_b_share_symbol(symbol: str, name: str = "", stock_type: str = "") -> bool:
    """判断是否为 B 股（用于对外服务接口兜底过滤）"""
    if name:
        name_str = str(name)
        if name_str.endswith(("B", "Ｂ")) or "B股" in name_str or "含B股" in name_str:
            return True

    if stock_type:
        if str(stock_type).upper() in {"B", "B_SHARE", "B-SHARE", "B-SHARES"}:
            return True

    try:
        from deva.naja.common.stock_registry import StockCodeNormalizer
        sina = StockCodeNormalizer.to_sina_code(symbol)
        if sina.startswith("sh900") or sina.startswith("sz200"):
            return True
    except Exception:
        pass

    return False


def _is_b_share_sector(block_id: str, sector_name: Optional[str]) -> bool:
    """判断板块名称是否包含 B 股标识"""
    display = str(sector_name or block_id)
    return ("B股" in display) or ("含B股" in display)


def get_hot_blocks_and_stocks() -> Dict[str, Any]:
    """获取热门题材和股票"""
    integration = get_attention_integration()
    if not integration:
        _lab_debug_log("get_hot_blocks_and_stocks: integration 为空")
        return {"blocks": [], "stocks": []}

    try:
        block_weights = integration.attention_system.block_attention.get_all_weights(filter_noise=True) if integration.attention_system else {}
        symbol_weights = integration.attention_system.weight_pool.get_all_weights(filter_noise=True) if integration.attention_system else {}

        _lab_debug_log(f"get_hot_blocks_and_stocks: block_weights={len(block_weights)} 个, symbol_weights={len(symbol_weights)} 个")

        # 使用 BlockNoiseDetector 过滤噪声题材
        from deva.naja.attention.processing.block_noise_detector import get_block_noise_detector
        noise_detector = get_block_noise_detector()

        sorted_blocks = sorted(
            [(block_id, weight) for block_id, weight in block_weights.items()],
            key=lambda x: x[1], reverse=True
        )

        tracker = get_history_tracker()
        hot_blocks: List[Dict[str, Any]] = []
        filtered_noise_blocks = 0
        for block_id, weight in sorted_blocks:
            block_name = tracker.get_block_name(block_id) if tracker else block_id
            if noise_detector.is_noise(block_id, block_name):
                filtered_noise_blocks += 1
                continue
            hot_blocks.append({
                "block_id": block_id,
                "name": block_name,
                "weight": weight
            })
            if len(hot_blocks) >= 5:
                break

        if filtered_noise_blocks > 0:
            _lab_debug_log(f"get_hot_blocks_and_stocks: 过滤噪声题材 {filtered_noise_blocks} 个")

        sorted_stocks = sorted(
            [(symbol, weight) for symbol, weight in symbol_weights.items()],
            key=lambda x: x[1], reverse=True
        )

        from deva.naja.common.stock_registry import get_stock_registry
        registry = get_stock_registry()

        hot_stocks_with_name = []
        filtered_b_stocks = 0
        for symbol, weight in sorted_stocks:
            info = registry.get(symbol)
            stock_name = info.name if info else registry.get_name(symbol)
            stock_type = info.stock_type if info else ""
            if _is_b_share_symbol(symbol, stock_name, stock_type):
                filtered_b_stocks += 1
                continue
            hot_stocks_with_name.append({
                "symbol": symbol,
                "name": stock_name if stock_name else symbol,
                "weight": weight
            })
            if len(hot_stocks_with_name) >= 20:
                break

        if filtered_b_stocks > 0:
            _lab_debug_log(f"get_hot_blocks_and_stocks: 过滤 B 股股票 {filtered_b_stocks} 只")

        if hot_blocks:
            top_blocks = [(s["block_id"], s["name"], f"{s['weight']:.4f}") for s in hot_blocks[:3]]
            _lab_debug_log(f"热门 Block Top3: {top_blocks}")
        if hot_stocks_with_name:
            top_stocks = [(s["symbol"], s["name"], f"{s['weight']:.4f}") for s in hot_stocks_with_name[:3]]
            _lab_debug_log(f"热门股票 Top3: {top_stocks}")

        return {"blocks": hot_blocks, "stocks": hot_stocks_with_name}
    except Exception as e:
        _lab_debug_log(f"get_hot_blocks_and_stocks 异常: {e}")
        return {"blocks": [], "stocks": []}


def get_attention_report() -> Dict[str, Any]:
    """获取注意力系统报告"""
    integration = get_attention_integration()
    if integration:
        try:
            report = integration.get_attention_report()
            _lab_debug_log(f"get_attention_report: global_attention={report.get('global_attention', 0):.4f}, activity={report.get('activity', 0):.4f}")
            return report
        except Exception as e:
            _lab_debug_log(f"get_attention_report 异常: {e}")
            pass
    else:
        _lab_debug_log("get_attention_report: integration 为空")
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
        from deva.naja.attention.config import load_config
        from deva.naja.attention.integration import initialize_attention_system
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


def _format_next_time(raw_time: str) -> str:
    if not raw_time:
        return ""
    try:
        import pytz
        from datetime import datetime

        local_tz = pytz.timezone("Asia/Shanghai")
        us_eastern = pytz.timezone("America/New_York")
        
        # 尝试解析时间字符串
        raw_time_clean = raw_time.replace('Z', '+00:00')
        dt = datetime.fromisoformat(raw_time_clean)

        # 如果有明确的时区信息，直接转换到北京时间
        if dt.tzinfo is not None:
            # 检查时区偏移量来判断是美东时间还是北京时间
            utc_offset = dt.utcoffset()
            if utc_offset is not None:
                offset_hours = utc_offset.total_seconds() / 3600
                # 美东时间：UTC-5 (冬令时) 或 UTC-4 (夏令时)
                # 北京时间：UTC+8
                if -6 <= offset_hours <= -4:
                    # 美东时间，需要转换
                    dt_local = dt.astimezone(local_tz)
                elif 7 <= offset_hours <= 9:
                    # 北京时间或相近时区，直接使用
                    dt_local = dt.astimezone(local_tz)
                else:
                    # 其他时区，转换为北京时间
                    dt_local = dt.astimezone(local_tz)
            else:
                dt_local = dt.astimezone(local_tz)
        else:
            # 没有时区信息时，假设是北京时间（用于 A 股交易时钟）
            dt_local = local_tz.localize(dt)

        now_local = datetime.now(local_tz)
        if dt_local.date() != now_local.date():
            return dt_local.strftime("次日%H:%M")
        return dt_local.strftime("%H:%M")
    except Exception:
        if "T" in raw_time:
            return raw_time.split("T")[1][:5]
        return raw_time


def _get_market_time_context() -> Dict[str, Any]:
    """获取市场时间上下文（支持回放模式）"""
    try:
        from deva.naja.common.market_time import get_market_time_service
        mts = get_market_time_service()
        market_time = mts.get_market_time()
        is_replay = mts.is_replay_mode()
    except Exception:
        market_time = None
        is_replay = False

    if market_time:
        try:
            from datetime import datetime
            market_dt = datetime.fromtimestamp(market_time)
            market_time_str = market_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            market_dt = None
            market_time_str = ""
    else:
        market_dt = None
        market_time_str = ""

    return {
        'is_replay': is_replay,
        'market_time': market_time,
        'market_dt': market_dt,
        'market_time_str': market_time_str,
    }


def get_ui_mode_context() -> Dict[str, Any]:
    """获取当前 UI 模式上下文（实盘/回放/强制）"""
    try:
        from deva.naja.attention.integration import get_mode_manager
        mode_manager = get_mode_manager()
        mode_info = mode_manager.get_diagnostic_info()
        mode = mode_info.get('current_mode', 'realtime')
        is_force = mode_info.get('is_force_realtime', False)
        is_lab = mode_info.get('is_lab', False)
    except Exception:
        mode = 'realtime'
        is_force = False
        is_lab = False

    time_ctx = _get_market_time_context()
    is_replay = time_ctx.get('is_replay', False)

    if is_lab or is_replay:
        mode_label = "回放/实验模式"
    elif is_force:
        mode_label = "强制实盘"
    else:
        mode_label = "实盘模式"

    return {
        'mode': mode,
        'is_lab': is_lab,
        'is_force': is_force,
        'is_replay': is_replay,
        'mode_label': mode_label,
        'market_time': time_ctx.get('market_time'),
        'market_time_str': time_ctx.get('market_time_str', ''),
        'market_dt': time_ctx.get('market_dt'),
    }


def _cn_phase_at(dt) -> str:
    """按 A 股规则计算指定时间的交易阶段"""
    try:
        if dt.weekday() >= 5:
            return 'closed'
        total_minutes = dt.hour * 60 + dt.minute
        CALL_AUCTION_START = 9 * 60 + 15
        CALL_AUCTION_END = 9 * 60 + 25
        PRE_START = 9 * 60 + 25
        PRE_END = 9 * 60 + 30
        MORNING_END = 11 * 60 + 30
        LUNCH_END = 13 * 60
        AFTERNOON_END = 15 * 60
        POST_END = 15 * 60 + 30

        if total_minutes < CALL_AUCTION_START:
            return 'closed'
        if CALL_AUCTION_START <= total_minutes < CALL_AUCTION_END:
            return 'call_auction'
        if PRE_START <= total_minutes < PRE_END:
            return 'pre_market'
        if PRE_END <= total_minutes < MORNING_END:
            return 'trading'
        if MORNING_END <= total_minutes < LUNCH_END:
            return 'lunch'
        if LUNCH_END <= total_minutes < AFTERNOON_END:
            return 'trading'
        if AFTERNOON_END <= total_minutes < POST_END:
            return 'post_market'
        return 'closed'
    except Exception:
        return 'closed'


def get_market_phase_summary() -> Dict[str, Any]:
    """获取A股/美股交易时段摘要信息（用于UI文案）"""
    from deva.naja.radar.trading_clock import get_trading_clock
    from deva.naja.radar.global_market_config import get_market_session_manager

    cn_phase_names = {
        'trading': '交易中',
        'pre_market': '盘前',
        'call_auction': '集合竞价',
        'post_market': '盘后',
        'lunch': '午休',
        'closed': '休市',
    }
    us_phase_names = {
        'trading': '交易中',
        'pre_market': '盘前',
        'post_market': '盘后',
        'closed': '休市',
    }

    time_ctx = _get_market_time_context()
    market_dt = time_ctx.get('market_dt')
    is_replay = time_ctx.get('is_replay', False)

    if is_replay and market_dt:
        try:
            cn_phase = _cn_phase_at(market_dt)
        except Exception:
            cn_phase = 'closed'
        cn_signal = {
            'phase': cn_phase,
            'next_phase': '',
            'next_change_time': '',
        }
        try:
            mgr = get_market_session_manager()
            us_phase = mgr.get_us_trading_phase(market_dt)
        except Exception:
            us_phase = 'closed'
        us_signal = {
            'phase': us_phase,
            'next_phase': '',
            'next_change_time': '',
        }
    else:
        try:
            cn_signal = get_trading_clock().get_current_signal()
        except Exception:
            cn_signal = {}
        try:
            from deva.naja.radar.trading_clock import get_us_trading_clock
            us_signal = get_us_trading_clock().get_current_signal()
        except Exception:
            us_signal = {}

    def build(signal: Dict[str, Any], names: Dict[str, str]) -> Dict[str, Any]:
        phase = signal.get('phase', 'closed')
        next_phase = signal.get('next_phase', '')
        next_change_time = _format_next_time(signal.get('next_change_time', '') or '')
        phase_name = names.get(phase, phase)
        next_phase_name = names.get(next_phase, next_phase) if next_phase else ''
        active = phase in ('trading', 'pre_market', 'call_auction')
        return {
            'phase': phase,
            'phase_name': phase_name,
            'next_phase': next_phase,
            'next_phase_name': next_phase_name,
            'next_change_time': next_change_time,
            'active': active,
        }

    cn_info = build(cn_signal, cn_phase_names)
    us_info = build(us_signal, us_phase_names)

    return {
        'cn': cn_info,
        'us': us_info,
        'is_replay': is_replay,
        'market_time_str': time_ctx.get('market_time_str', ''),
    }
