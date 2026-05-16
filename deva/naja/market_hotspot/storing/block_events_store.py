"""
市场题材事件轻量级持久化存储

存储 A股 和 美股 的题材轮动事件，用于系统重启后恢复。
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".naja"
CN_EVENTS_FILE = CACHE_DIR / "cn_block_events.json"
US_EVENTS_FILE = CACHE_DIR / "us_block_events.json"

MAX_CN_EVENTS = 500  # A股最多 500 条
MAX_US_EVENTS = 300  # 美股最多 300 条
CACHE_HOURS = 48  # 保留 48 小时（跨两个交易日）


class BlockEventsStore:
    """题材事件存储"""
    
    _instance: Optional['BlockEventsStore'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._lock_inner = threading.Lock()
        self._cn_cache_file = CN_EVENTS_FILE
        self._us_cache_file = US_EVENTS_FILE
        self._cn_cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._cn_events: List[Dict[str, Any]] = []
        self._us_events: List[Dict[str, Any]] = []
        
        self._load_cn_events()
        self._load_us_events()
        
        self._initialized = True
        self._last_cleanup = time.time()
        
        log.info(f"[BlockEventsStore] 初始化完成")
        log.info(f"  - A股缓存: {self._cn_cache_file} ({len(self._cn_events)} 条)")
        log.info(f"  - 美股缓存: {self._us_cache_file} ({len(self._us_events)} 条)")
    
    def _load_cn_events(self):
        """加载A股事件"""
        if not self._cn_cache_file.exists():
            return
        try:
            with open(self._cn_cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._cn_events = data.get('events', [])
            self._cleanup_expired(self._cn_events)
        except Exception as e:
            log.warning(f"[BlockEventsStore] 加载A股事件失败: {e}")
            self._cn_events = []
    
    def _load_us_events(self):
        """加载美股事件"""
        if not self._us_cache_file.exists():
            return
        try:
            with open(self._us_cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._us_events = data.get('events', [])
            self._cleanup_expired(self._us_events)
        except Exception as e:
            log.warning(f"[BlockEventsStore] 加载美股事件失败: {e}")
            self._us_events = []
    
    def _save_cn_events(self):
        """保存A股事件"""
        try:
            with open(self._cn_cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'events': self._cn_events,
                    'updated_at': time.time(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"[BlockEventsStore] 保存A股事件失败: {e}")
    
    def _save_us_events(self):
        """保存美股事件"""
        try:
            with open(self._us_cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'events': self._us_events,
                    'updated_at': time.time(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"[BlockEventsStore] 保存美股事件失败: {e}")
    
    def _cleanup_expired(self, events_list: List[Dict]):
        """清理过期数据"""
        now = time.time()
        cutoff = now - CACHE_HOURS * 3600
        
        original_len = len(events_list)
        events_list[:] = [
            e for e in events_list
            if e.get('timestamp', 0) >= cutoff
        ]
        
        if len(events_list) < original_len:
            log.debug(f"[BlockEventsStore] 清理了 {original_len - len(events_list)} 条过期事件")
    
    def _trim_to_max_size(self, events_list: List[Dict], max_size: int):
        """确保不超过最大存储数量"""
        if len(events_list) > max_size:
            events_list.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            del events_list[max_size:]
    
    def add_cn_event(self, event_data: Dict[str, Any]) -> bool:
        """添加A股题材事件"""
        with self._lock_inner:
            timestamp = event_data.get('timestamp', time.time())
            
            # 去重
            is_duplicate = any(
                e.get('block_id') == event_data.get('block_id') and
                abs(e.get('timestamp', 0) - timestamp) < 300  # 5分钟内不重复
                for e in self._cn_events
            )
            
            if is_duplicate:
                return False
            
            self._cn_events.append(event_data)
            self._trim_to_max_size(self._cn_events, MAX_CN_EVENTS)
            self._save_cn_events()
            
            log.debug(f"[BlockEventsStore] 添加A股事件: {event_data.get('block_name', '')}")
            return True
    
    def add_us_event(self, event_data: Dict[str, Any]) -> bool:
        """添加美股题材事件"""
        with self._lock_inner:
            timestamp = event_data.get('timestamp', time.time())
            
            # 去重
            is_duplicate = any(
                e.get('block_id') == event_data.get('block_id') and
                abs(e.get('timestamp', 0) - timestamp) < 300
                for e in self._us_events
            )
            
            if is_duplicate:
                return False
            
            self._us_events.append(event_data)
            self._trim_to_max_size(self._us_events, MAX_US_EVENTS)
            self._save_us_events()
            
            log.debug(f"[BlockEventsStore] 添加美股事件: {event_data.get('block_name', '')}")
            return True
    
    def get_cn_events(self, hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取A股事件"""
        with self._lock_inner:
            if time.time() - self._last_cleanup > 3600:
                self._cleanup_expired(self._cn_events)
                self._last_cleanup = time.time()
            
            events = self._cn_events
            
            if hours is not None:
                cutoff = time.time() - hours * 3600
                events = [e for e in events if e.get('timestamp', 0) >= cutoff]
            
            return sorted(events, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    def get_us_events(self, hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取美股事件"""
        with self._lock_inner:
            if time.time() - self._last_cleanup > 3600:
                self._cleanup_expired(self._us_events)
                self._last_cleanup = time.time()
            
            events = self._us_events
            
            if hours is not None:
                cutoff = time.time() - hours * 3600
                events = [e for e in events if e.get('timestamp', 0) >= cutoff]
            
            return sorted(events, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        with self._lock_inner:
            now = time.time()
            cutoff_24h = now - 24 * 3600
            cutoff_48h = now - 48 * 3600
            
            return {
                'cn_total': len(self._cn_events),
                'cn_last_24h': len([e for e in self._cn_events if e.get('timestamp', 0) >= cutoff_24h]),
                'cn_last_48h': len([e for e in self._cn_events if e.get('timestamp', 0) >= cutoff_48h]),
                'us_total': len(self._us_events),
                'us_last_24h': len([e for e in self._us_events if e.get('timestamp', 0) >= cutoff_24h]),
                'us_last_48h': len([e for e in self._us_events if e.get('timestamp', 0) >= cutoff_48h]),
            }


# 单例访问
_store: Optional[BlockEventsStore] = None


def get_block_events_store() -> BlockEventsStore:
    """获取题材事件存储单例"""
    global _store
    if _store is None:
        _store = BlockEventsStore()
    return _store


def add_cn_block_event(event_data: Dict[str, Any]) -> bool:
    """快捷函数：添加A股题材事件"""
    return get_block_events_store().add_cn_event(event_data)


def add_us_block_event(event_data: Dict[str, Any]) -> bool:
    """快捷函数：添加美股题材事件"""
    return get_block_events_store().add_us_event(event_data)


def get_cn_block_events(hours: Optional[int] = 48) -> List[Dict[str, Any]]:
    """快捷函数：获取A股题材事件"""
    return get_block_events_store().get_cn_events(hours=hours)


def get_us_block_events(hours: Optional[int] = 48) -> List[Dict[str, Any]]:
    """快捷函数：获取美股题材事件"""
    return get_block_events_store().get_us_events(hours=hours)
