"""
市场交易时间工具

处理A股市场的交易时间、节假日、隔夜跳空等特殊场景
"""

from datetime import datetime, time, timedelta
from typing import Optional, Tuple
import logging

log = logging.getLogger(__name__)


class MarketTimeConfig:
    """A股市场时间配置"""
    
    # 交易时段
    MORNING_START = time(9, 30)
    MORNING_END = time(11, 30)
    AFTERNOON_START = time(13, 0)
    AFTERNOON_END = time(15, 0)
    
    # 盘前盘后（用于识别隔夜）
    PRE_MARKET_START = time(9, 15)  # 集合竞价开始
    POST_MARKET_END = time(15, 30)  # 收盘后处理时间
    

class MarketTimeUtils:
    """市场交易时间工具类"""
    
    @staticmethod
    def is_trading_time(dt: datetime) -> bool:
        """检查是否在交易时间内"""
        # 周末不交易
        if dt.weekday() >= 5:  # 5=周六, 6=周日
            return False
        
        t = dt.time()
        
        # 上午交易时段 9:30-11:30
        if MarketTimeConfig.MORNING_START <= t <= MarketTimeConfig.MORNING_END:
            return True
        
        # 下午交易时段 13:00-15:00
        if MarketTimeConfig.AFTERNOON_START <= t <= MarketTimeConfig.AFTERNOON_END:
            return True
        
        return False
    
    @staticmethod
    def is_trading_day(dt: datetime) -> bool:
        """检查是否是交易日（简化版，不考虑节假日）"""
        return dt.weekday() < 5  # 周一到周五
    
    @staticmethod
    def get_time_of_day(dt: datetime) -> str:
        """获取时间段描述"""
        t = dt.time()
        
        if t < MarketTimeConfig.MORNING_START:
            return "pre_market"  # 盘前
        elif MarketTimeConfig.MORNING_START <= t <= MarketTimeConfig.MORNING_END:
            return "morning_session"  # 上午交易
        elif MarketTimeConfig.MORNING_END < t < MarketTimeConfig.AFTERNOON_START:
            return "noon_break"  # 午休
        elif MarketTimeConfig.AFTERNOON_START <= t <= MarketTimeConfig.AFTERNOON_END:
            return "afternoon_session"  # 下午交易
        else:
            return "post_market"  # 盘后
    
    @staticmethod
    def calculate_trading_time_gap(dt1: datetime, dt2: datetime) -> Tuple[float, str]:
        """
        计算两个时间点之间的实际交易时间跨度
        
        Returns:
            (trading_seconds, gap_type)
            gap_type: 'intraday', 'overnight', 'weekend', 'holiday'
        """
        if dt2 < dt1:
            dt1, dt2 = dt2, dt1
        
        total_seconds = (dt2 - dt1).total_seconds()
        
        # 判断是否跨天
        same_day = dt1.date() == dt2.date()
        
        # 判断是否跨周末
        days_diff = (dt2.date() - dt1.date()).days
        
        if same_day:
            # 同一天内
            if MarketTimeUtils.is_trading_time(dt1) and MarketTimeUtils.is_trading_time(dt2):
                return (total_seconds, 'intraday')
            else:
                return (total_seconds, 'intraday_non_trading')
        
        elif days_diff == 1:
            # 隔夜（相邻交易日）
            return (total_seconds, 'overnight')
        
        elif days_diff <= 3 and dt1.weekday() + days_diff >= 5:
            # 跨周末
            return (total_seconds, 'weekend')
        
        else:
            # 跨节假日（3天以上）
            return (total_seconds, 'holiday')
    
    @staticmethod
    def get_adjusted_threshold(
        base_threshold: float,
        gap_type: str,
        time_gap_seconds: float
    ) -> float:
        """
        根据时间跨度类型获取调整后的阈值
        
        Args:
            base_threshold: 基础阈值（如20%）
            gap_type: 时间跨度类型
            time_gap_seconds: 实际时间跨度（秒）
        
        Returns:
            调整后的阈值
        """
        if gap_type == 'intraday':
            # 日内交易，使用正常阈值
            return base_threshold
        
        elif gap_type == 'overnight':
            # 隔夜跳空，允许更大的变化
            # 隔夜变化通常可以达到日内的3-5倍
            return base_threshold * 5.0
        
        elif gap_type == 'weekend':
            # 周末跳空，允许更大的变化
            # 周末两天可能有重大消息
            return base_threshold * 10.0
        
        elif gap_type == 'holiday':
            # 节假日跳空，允许最大变化
            return base_threshold * 20.0
        
        else:
            return base_threshold
    
    @staticmethod
    def should_reset_history(dt1: datetime, dt2: datetime) -> bool:
        """
        判断是否应该在dt2重置历史数据
        
        当跨天、跨周末、跨节假日时，应该重置历史
        """
        if dt1.date() != dt2.date():
            return True
        
        # 如果跨了非交易时段（如午休后），也考虑重置
        tod1 = MarketTimeUtils.get_time_of_day(dt1)
        tod2 = MarketTimeUtils.get_time_of_day(dt2)
        
        if tod1 in ['morning_session'] and tod2 in ['afternoon_session']:
            # 跨午休，不重置
            return False
        
        if tod1 in ['post_market', 'pre_market'] or tod2 in ['post_market', 'pre_market']:
            # 跨开盘收盘，重置
            return True
        
        return False
    
    @staticmethod
    def is_market_open(dt: datetime) -> bool:
        """检查市场是否处于开盘状态"""
        return MarketTimeUtils.is_trading_time(dt)
    
    @staticmethod
    def is_market_close(dt: datetime) -> bool:
        """检查市场是否处于收盘状态"""
        return not MarketTimeUtils.is_trading_time(dt)
    
    @staticmethod
    def format_time_gap(seconds: float) -> str:
        """格式化时间跨度为可读字符串"""
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            return f"{seconds/60:.1f}分钟"
        elif seconds < 86400:
            return f"{seconds/3600:.1f}小时"
        else:
            return f"{seconds/86400:.1f}天"


class MarketSessionTracker:
    """市场时段追踪器"""
    
    def __init__(self):
        self._last_trading_day: Optional[datetime] = None
        self._session_start: Optional[datetime] = None
        self._market_state: str = "unknown"  # open, close, pre, post
    
    def update(self, dt: datetime):
        """更新市场状态"""
        if MarketTimeUtils.is_trading_time(dt):
            if self._market_state != "open":
                # 市场刚开盘
                self._session_start = dt
                self._market_state = "open"
                log.debug(f"市场开盘: {dt}")
        else:
            if self._market_state == "open":
                # 市场刚收盘
                self._last_trading_day = dt
                self._market_state = "close"
                log.debug(f"市场收盘: {dt}")
        
        # 记录交易日
        if MarketTimeUtils.is_trading_day(dt):
            self._last_trading_day = dt
    
    def get_session_info(self) -> dict:
        """获取当前会话信息"""
        return {
            'market_state': self._market_state,
            'session_start': self._session_start,
            'last_trading_day': self._last_trading_day,
        }


# 全局实例
_market_utils = MarketTimeUtils()
_session_tracker = MarketSessionTracker()


def get_market_utils() -> MarketTimeUtils:
    """获取市场时间工具实例"""
    return _market_utils


def get_session_tracker() -> MarketSessionTracker:
    """获取市场时段追踪器"""
    return _session_tracker
