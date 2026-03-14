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
        self._min_confidence = 0.5
        
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
                self._min_confidence = config.get("min_confidence", 0.5)
        except Exception:
            pass
    
    def _save_config(self):
        """保存配置"""
        try:
            db = NB(SIGNAL_CONFIG_TABLE)
            db["listener_config"] = {
                "poll_interval": self._poll_interval,
                "min_confidence": self._min_confidence
            }
        except Exception:
            pass
    
    def register_callback(self, callback: Callable[[DetectedSignal], None]):
        """注册信号处理回调"""
        self._callbacks.append(callback)
        log.info(f"已注册信号回调: {callback.__name__}")
    
    def unregister_callback(self, callback: Callable[[DetectedSignal], None]):
        """注销信号处理回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def start(self):
        """启动监听"""
        if self._running:
            log.warning("SignalListener 已在运行")
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        log.info(f"SignalListener 已启动 (轮询间隔: {self._poll_interval}s)")
    
    def stop(self):
        """停止监听"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
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
            
            if signal.confidence < self._min_confidence:
                log.debug(f"信号置信度低于阈值: {signal.confidence} < {self._min_confidence}")
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
        """解析信号"""
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
            
            stock_code = self._extract_stock_code(signal_data)
            stock_name = signal_data.get('name', '') or signal_data.get('stock_name', '')
            
            if not stock_code:
                return None
            
            price = self._extract_price(signal_data)
            confidence = float(signal_data.get('confidence', 0.7))
            signal_type = signal_data.get('signal_type', signal_data.get('type', 'BUY'))
            
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
                raw_data=signal_data
            )
            
        except Exception as e:
            log.debug(f"解析信号失败: {e}")
            return None
    
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
