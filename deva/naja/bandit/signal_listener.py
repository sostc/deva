"""信号监听器

监听信号流，识别股票，创建虚拟持仓。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..signal.stream import get_signal_stream
from ..strategy.result_store import StrategyResult

log = logging.getLogger(__name__)

SIGNAL_CONFIG_TABLE = "naja_bandit_signal_config"


@dataclass
class DetectedSignal:
    """检测到的信号"""
    signal_id: str
    strategy_id: str
    strategy_name: str
    stock_code: str
    stock_name: str
    signal_type: str
    price: float
    confidence: float
    timestamp: float
    raw_data: Dict[str, Any] = field(default_factory=dict)
    market_time: float = 0.0  # 行情数据时间


class SignalListener:
    """信号监听器
    
    监听信号流：
    1. 实时获取信号流中的新信号
    2. 识别信号中的股票信息
    3. 过滤和转换信号格式
    4. 触发虚拟持仓创建回调
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._signal_stream = get_signal_stream()
        self._last_processed_ts = 0.0
        
        self._callbacks: List[Callable[[DetectedSignal], None]] = []
        
        self._poll_interval = 2.0
        self._min_confidence = 0.6
        
        self._processed_signals: Dict[str, float] = {}
        self._max_processed = 1000
        
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        try:
            db = NB(SIGNAL_CONFIG_TABLE)
            config = db.get("listener_config")
            if config:
                self._poll_interval = config.get("poll_interval", 2.0)
                self._min_confidence = config.get("min_confidence", 0.6)
                # 恢复运行状态
                was_running = config.get("was_running", False)
                if was_running:
                    self._running = True
                    log.debug("SignalListener 上次运行中，将自动恢复")
        except Exception:
            pass
    
    def _save_config(self):
        """保存配置"""
        try:
            db = NB(SIGNAL_CONFIG_TABLE)
            db["listener_config"] = {
                "poll_interval": self._poll_interval,
                "min_confidence": self._min_confidence,
                "was_running": self._running  # 保存运行状态
            }
        except Exception:
            pass
    
    def register_callback(self, callback: Callable[[DetectedSignal], None]):
        """注册信号处理回调"""
        self._callbacks.append(callback)
        log.debug(f"已注册信号回调: {callback.__name__}")
    
    def unregister_callback(self, callback: Callable[[DetectedSignal], None]):
        """注销信号处理回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def start(self):
        """启动监听"""
        if self._running and self._thread and self._thread.is_alive():
            log.warning("SignalListener 已在运行")
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        self._save_config()  # 保存运行状态

        log.debug(f"SignalListener 已启动 (轮询间隔: {self._poll_interval}s)")
    
    def stop(self):
        """停止监听"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        self._save_config()  # 保存运行状态
        
        log.info("SignalListener 已停止")
    
    def _run_loop(self):
        """主循环"""
        while self._running and not self._stop_event.is_set():
            try:
                self._process_signals()
            except Exception as e:
                log.error(f"SignalListener 处理错误: {e}")
            
            self._stop_event.wait(self._poll_interval)
    
    def _process_signals(self):
        """处理信号流中的新信号"""
        try:
            recent = self._signal_stream.get_recent(limit=50)
            log.debug(f"[Bandit] 获取到 {len(recent)} 个信号")
        except Exception as e:
            log.error(f"获取信号流失败: {e}")
            return
        
        for result in recent:
            if result.ts <= self._last_processed_ts:
                continue
            
            if self._is_processed(result.id):
                continue
            
            signal = self._parse_signal(result)
            if signal is None:
                continue
            
            log.debug(f"[Bandit] 收到信号: {signal.stock_code} {signal.stock_name} 置信度={signal.confidence} 类型={signal.signal_type}")

            if signal.confidence < self._min_confidence:
                log.debug(f"[Bandit] 置信度低于阈值: {signal.confidence} < {self._min_confidence}")
                continue

            self._mark_processed(result.id, result.ts)

            if result.ts > self._last_processed_ts:
                self._last_processed_ts = result.ts

            for callback in self._callbacks:
                try:
                    callback(signal)
                except Exception as e:
                    log.error(f"信号回调执行失败: {e}")
    
    def _parse_signal(self, result: StrategyResult) -> Optional[DetectedSignal]:
        """解析信号
        
        支持两种格式：
        1. 直接格式: {signal_type: "BUY", stock_code: "xxx", price: xxx}
        2. River picks 格式: {signal: "xxx", picks: [{code, name, price, up_probability}]}
        """
        try:
            output = result.output_full
            if not output:
                output = result.output_preview
            
            if isinstance(output, dict):
                signal_data = output
            elif hasattr(output, 'to_dict'):
                signal_data = output.to_dict()
            else:
                return None
            
            stock_code = ""
            stock_name = ""
            price = 0.0
            confidence = 0.7
            signal_type = "BUY"
            market_time = 0.0
            
            if 'picks' in signal_data and isinstance(signal_data['picks'], list) and signal_data['picks']:
                picks = signal_data['picks']
                top_pick = picks[0]
                
                stock_code = str(top_pick.get('code', '') or top_pick.get('stock_code', ''))
                stock_name = top_pick.get('name', '') or top_pick.get('stock_name', '')
                price = float(top_pick.get('price', 0) or top_pick.get('close', 0) or top_pick.get('current', 0))
                
                signal_type = "BUY"
                
                prob_fields = ['up_probability', 'order_flow_up_probability', 'anomaly_score', 'probability']
                for pf in prob_fields:
                    if pf in top_pick:
                        confidence = float(top_pick[pf])
                        if pf == 'anomaly_score':
                            confidence = min(1.0, confidence / 10.0)
                        break
                
                if signal_data.get('signal'):
                    signal_type = f"BUY ({signal_data['signal']})"
            else:
                stock_code = self._extract_stock_code(signal_data)
                stock_name = signal_data.get('name', '') or signal_data.get('stock_name', '')
                price = self._extract_price(signal_data)
                confidence = float(signal_data.get('confidence', 0.7))
                signal_type = signal_data.get('signal_type', signal_data.get('type', 'BUY'))
            
            if not stock_code:
                return None
            
            # 提取行情时间
            market_time = self._extract_market_time(signal_data, result.ts)
            
            return DetectedSignal(
                signal_id=result.id,
                strategy_id=result.strategy_id,
                strategy_name=result.strategy_name,
                stock_code=stock_code,
                stock_name=stock_name,
                signal_type=signal_type,
                price=price,
                confidence=confidence,
                timestamp=result.ts,
                raw_data=signal_data,
                market_time=market_time
            )
            
        except Exception as e:
            log.debug(f"解析信号失败: {e}")
            return None
    
    def _extract_market_time(self, data: Dict[str, Any], default_ts: float) -> float:
        """提取行情数据时间
        
        尝试从多个可能的字段中提取行情时间：
        - data_time: 行情数据时间
        - datetime: 日期时间
        - timestamp: 时间戳
        - market_time: 市场时间
        """
        try:
            # 尝试直接获取时间戳字段
            for key in ['data_time', 'timestamp', 'market_time', 'ts']:
                if key in data:
                    value = data[key]
                    if isinstance(value, (int, float)) and value > 1000000000:
                        return float(value)
            
            # 尝试解析 datetime 字符串
            for key in ['datetime', 'time', 'date']:
                if key in data:
                    value = data[key]
                    if isinstance(value, str):
                        try:
                            from datetime import datetime
                            # 尝试多种格式
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y%m%d%H%M%S', '%H:%M:%S']:
                                try:
                                    dt = datetime.strptime(value, fmt)
                                    # 如果是只有时间格式，使用当前日期
                                    if fmt == '%H:%M:%S':
                                        from datetime import datetime as dt2
                                        now = dt2.now()
                                        dt = dt.replace(year=now.year, month=now.month, day=now.day)
                                    return dt.timestamp()
                                except ValueError:
                                    continue
                        except Exception:
                            pass
            
            # 如果从 picks 中获取，尝试第一个 pick 的时间字段
            if 'picks' in data and isinstance(data['picks'], list) and data['picks']:
                top_pick = data['picks'][0]
                for key in ['data_time', 'timestamp', 'market_time', 'ts']:
                    if key in top_pick:
                        value = top_pick[key]
                        if isinstance(value, (int, float)) and value > 1000000000:
                            return float(value)
            
            # 如果都没有找到，使用默认时间戳
            return default_ts
            
        except Exception as e:
            log.debug(f"提取行情时间失败: {e}")
            return default_ts
    
    def _extract_stock_code(self, data: Dict[str, Any]) -> str:
        """提取股票代码"""
        for key in ['code', 'stock_code', 'symbol', 'Code', 'Symbol']:
            if key in data:
                return str(data[key])
        return ''
    
    def _extract_price(self, data: Dict[str, Any]) -> float:
        """提取价格"""
        for key in ['price', 'close', 'current', 'last', ' Price']:
            if key in data:
                try:
                    return float(data[key])
                except (ValueError, TypeError):
                    continue
        return 0.0
    
    def _is_processed(self, signal_id: str) -> bool:
        """检查信号是否已处理"""
        return signal_id in self._processed_signals
    
    def _mark_processed(self, signal_id: str, timestamp: float):
        """标记信号已处理"""
        self._processed_signals[signal_id] = timestamp
        
        if len(self._processed_signals) > self._max_processed:
            sorted_items = sorted(self._processed_signals.items(), key=lambda x: x[1])
            self._processed_signals = dict(sorted_items[-self._max_processed//2:])
    
    def set_poll_interval(self, seconds: float):
        """设置轮询间隔"""
        self._poll_interval = max(0.5, seconds)
        self._save_config()
    
    def set_min_confidence(self, confidence: float):
        """设置最小置信度"""
        self._min_confidence = max(0.0, min(1.0, confidence))
        self._save_config()
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "poll_interval": self._poll_interval,
            "min_confidence": self._min_confidence,
            "last_processed_ts": self._last_processed_ts,
            "processed_count": len(self._processed_signals),
            "callbacks_count": len(self._callbacks)
        }


_listener: Optional[SignalListener] = None
_listener_lock = threading.Lock()


def get_signal_listener() -> SignalListener:
    global _listener
    if _listener is None:
        with _listener_lock:
            if _listener is None:
                _listener = SignalListener()
    return _listener
