"""Bandit 与萧何 (XiaoHe) 的集成模块

提供萧何持仓平仓时自动触发 Bandit 更新的能力。
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


class XiaoHeBanditIntegration:
    """萧何与 Bandit 的集成类
    
    在萧何的持仓平仓时自动调用 Bandit 更新。
    使用方式：在萧何的 close_position 中调用集成方法。
    """
    
    def __init__(self):
        self._enabled = True
        self._trigger_adjust_on_close = True
    
    def on_position_closed(
        self,
        strategy_name: str,
        position_id: str,
        entry_price: float,
        exit_price: float,
        open_timestamp: float,
    ) -> Optional[dict]:
        """持仓平仓时调用
        
        Args:
            strategy_name: 策略名称
            position_id: 持仓 ID
            entry_price: 入场价格
            exit_price: 出场价格
            open_timestamp: 开仓时间戳
            
        Returns:
            Optional[dict]: Bandit 更新结果
        """
        if not self._enabled:
            return None
        
        try:
            from deva.naja.bandit.tracker import get_bandit_tracker
            
            tracker = get_bandit_tracker()
            result = tracker.on_position_closed(
                strategy_id=strategy_name,
                position_id=position_id,
                entry_price=entry_price,
                exit_price=exit_price,
                open_timestamp=open_timestamp,
                trigger_adjust=self._trigger_adjust_on_close
            )
            
            log.info(f"Bandit 追踪: 策略={strategy_name}, 持仓={position_id}, "
                    f"收益={result.get('return_pct', 0):.2f}%, 奖励={result.get('reward', 0):.2f}")
            
            return result
            
        except Exception as e:
            log.error(f"Bandit 集成错误: {e}")
            return None
    
    def enable(self):
        """启用集成"""
        self._enabled = True
    
    def disable(self):
        """禁用集成"""
        self._enabled = False
    
    def set_trigger_adjust(self, enabled: bool):
        """设置是否在平仓时触发调节"""
        self._trigger_adjust_on_close = enabled


_integration: Optional[XiaoHeBanditIntegration] = None


def get_xiaohe_bandit_integration() -> XiaoHeBanditIntegration:
    """获取萧何与 Bandit 的集成实例"""
    global _integration
    if _integration is None:
        _integration = XiaoHeBanditIntegration()
    return _integration


def patch_xiaohe_close_position():
    """为萧何的 close_position 方法打补丁
    
    在萧何的 close_position 方法末尾添加 Bandit 更新调用。
    """
    from deva.naja.agent import xiaohe
    
    original_close_position = xiaohe.XiaoHeAgent.close_position
    
    def patched_close_position(self, position_id: str, price: float):
        position = self._positions.get(position_id)
        
        result = original_close_position(self, position_id, price)
        
        if position and self._enabled:
            try:
                integration = get_xiaohe_bandit_integration()
                integration.on_position_closed(
                    strategy_name=position.strategy_name,
                    position_id=position_id,
                    entry_price=position.avg_price,
                    exit_price=price,
                    open_timestamp=position.open_timestamp
                )
            except Exception as e:
                log.error(f"平仓时 Bandit 更新失败: {e}")
        
        return result
    
    xiaohe.XiaoHeAgent.close_position = patched_close_position


def enable_xiaohe_bandit():
    """启用萧何与 Bandit 的集成"""
    global _integration
    if _integration is None:
        _integration = XiaoHeBanditIntegration()
    _integration.enable()
    
    patch_xiaohe_close_position()
    
    log.info("萧何与 Bandit 集成已启用")


def disable_xiaohe_bandit():
    """禁用萧何与 Bandit 的集成"""
    global _integration
    if _integration:
        _integration.disable()
    log.info("萧何与 Bandit 集成已禁用")
