"""Naja API 端点

提供热点题材和股票数据的 JSON API 端点
"""

import json
import time
from typing import Dict, Any, Optional, List
from tornado.web import RequestHandler

from deva.naja.register import SR


def _get_market_hotspot_integration():
    """获取热点系统集成"""
    try:
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        return get_market_hotspot_integration()
    except Exception:
        return None


def _get_history_tracker():
    """获取历史追踪器"""
    try:
        from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
        return get_history_tracker()
    except Exception:
        return None


def _get_block_dictionary():
    """获取题材字典"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        return get_block_dictionary()
    except Exception:
        return None


def _get_hot_blocks_and_stocks(market: str = 'CN') -> Dict[str, Any]:
    """获取热门题材和股票

    Args:
        market: 市场类型 ('CN' 或 'US')

    Returns:
        包含热门题材和股票的字典
    """
    integration = _get_market_hotspot_integration()
    if not integration:
        return {"blocks": [], "stocks": []}

    try:
        tracker = _get_history_tracker()
        bd = _get_block_dictionary()

        if market == 'US':
            block_weights = {}
            symbol_weights = {}
            try:
                from deva.naja.market_hotspot.integration.market_hotspot_integration import get_mode_manager
                mode_manager = get_mode_manager()
                if mode_manager and hasattr(mode_manager, '_us_integration'):
                    us_integration = mode_manager._us_integration
                    if us_integration and us_integration.hotspot_system:
                        block_weights = us_integration.hotspot_system.block_hotspot.get_all_weights(
                            filter_noise=True
                        ) if us_integration.hotspot_system else {}
                        symbol_weights = us_integration.hotspot_system.weight_pool.get_all_weights(
                            filter_noise=True
                        ) if us_integration.hotspot_system else {}
            except Exception:
                pass
        else:
            block_weights = integration.hotspot_system.block_hotspot.get_all_weights(
                filter_noise=True
            ) if integration.hotspot_system else {}
            symbol_weights = integration.hotspot_system.weight_pool.get_all_weights(
                filter_noise=True
            ) if integration.hotspot_system else {}

        sorted_blocks = sorted(
            [(block_id, weight) for block_id, weight in block_weights.items()],
            key=lambda x: x[1], reverse=True
        )

        hot_blocks: List[Dict[str, Any]] = []
        for block_id, weight in sorted_blocks:
            block_name = tracker.get_block_name(block_id) if tracker else block_id
            hot_blocks.append({
                "block_id": block_id,
                "name": block_name,
                "weight": float(weight)
            })
            if len(hot_blocks) >= 10:
                break

        sorted_stocks = sorted(
            [(symbol, weight) for symbol, weight in symbol_weights.items()],
            key=lambda x: x[1], reverse=True
        )

        hot_stocks_with_name = []
        for symbol, weight in sorted_stocks:
            stock_name = symbol
            if bd:
                info = bd.get_stock_info(symbol)
                if info:
                    stock_name = info.name
            hot_stocks_with_name.append({
                "symbol": symbol,
                "name": stock_name,
                "weight": float(weight)
            })
            if len(hot_stocks_with_name) >= 30:
                break

        return {"blocks": hot_blocks, "stocks": hot_stocks_with_name}
    except Exception:
        return {"blocks": [], "stocks": []}


class HealthHandler(RequestHandler):
    """健康检查端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        """健康检查"""
        result = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "ok",
            "service": "naja"
        }
        self.write(json.dumps(result, ensure_ascii=False))
