"""
TextFocusedEvent 轻量级持久化存储

只存储最近 24 小时的评分新闻数据，用于系统重启后恢复。
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

# 存储配置
CACHE_DIR = Path.home() / ".naja"
NEWS_CACHE_FILE = CACHE_DIR / "focused_news_cache.json"
MAX_CACHE_SIZE = 200  # 最多 200 条
CACHE_HOURS = 24  # 保留最近 24 小时


class FocusedNewsStore:
    """评分新闻轻量存储"""
    
    _instance: Optional['FocusedNewsStore'] = None
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
        self._cache_file = NEWS_CACHE_FILE
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._news_list: List[Dict[str, Any]] = []
        self._load_cache()
        self._initialized = True
        self._last_cleanup = time.time()
        
        log.info(f"[FocusedNewsStore] 初始化完成，缓存文件: {self._cache_file}")
    
    def _load_cache(self):
        """从文件加载缓存"""
        if not self._cache_file.exists():
            log.debug("[FocusedNewsStore] 缓存文件不存在")
            return
        
        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._news_list = data.get('news', [])
            log.info(f"[FocusedNewsStore] 加载了 {len(self._news_list)} 条历史评分新闻")
            
            # 清理过期数据
            self._cleanup_expired()
        except Exception as e:
            log.warning(f"[FocusedNewsStore] 加载缓存失败: {e}")
            self._news_list = []
    
    def _save_cache(self):
        """保存缓存到文件"""
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'news': self._news_list,
                    'updated_at': time.time(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"[FocusedNewsStore] 保存缓存失败: {e}")
    
    def _cleanup_expired(self):
        """清理过期数据"""
        now = time.time()
        cutoff = now - CACHE_HOURS * 3600
        
        original_len = len(self._news_list)
        self._news_list = [
            n for n in self._news_list
            if n.get('timestamp', 0) >= cutoff
        ]
        
        if len(self._news_list) < original_len:
            log.debug(f"[FocusedNewsStore] 清理了 {original_len - len(self._news_list)} 条过期新闻")
        
        self._last_cleanup = now
    
    def _trim_to_max_size(self):
        """确保不超过最大存储数量"""
        if len(self._news_list) > MAX_CACHE_SIZE:
            # 按时间排序，保留最新的
            self._news_list.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            self._news_list = self._news_list[:MAX_CACHE_SIZE]
            log.debug(f"[FocusedNewsStore] 裁剪到 {MAX_CACHE_SIZE} 条记录")
    
    def add_news(self, news: Dict[str, Any]):
        """
        添加一条评分新闻
        
        Args:
            news: 新闻字典，必须包含 timestamp 和 importance_score
        """
        with self._lock_inner:
            # 避免重复添加（基于标题和时间戳去重）
            is_duplicate = any(
                n.get('title') == news.get('title') and
                abs(n.get('timestamp', 0) - news.get('timestamp', 0)) < 60
                for n in self._news_list
            )
            
            if is_duplicate:
                return
            
            self._news_list.append(news)
            self._trim_to_max_size()
            self._save_cache()
            
            log.debug(f"[FocusedNewsStore] 添加新闻: {news.get('title', '')[:30]}...")
    
    def add_from_event(self, event) -> bool:
        """
        从 TextFocusedEvent 添加
        
        Args:
            event: TextFocusedEvent 实例
            
        Returns:
            是否添加成功
        """
        # 只添加 deep 级别的（重要性 >= 0.6）
        if hasattr(event, 'routing_level') and event.routing_level != 'deep':
            return False
        
        if hasattr(event, 'importance_score') and event.importance_score < 0.6:
            return False
        
        news = {
            'title': getattr(event, 'title', ''),
            'text': getattr(event, 'text', ''),
            'source': getattr(event, 'source', ''),
            'url': getattr(event, 'url', ''),
            'timestamp': getattr(event, 'timestamp', time.time()),
            'importance_score': getattr(event, 'importance_score', 0.5),
            'summary': getattr(event, 'summary', ''),
            'stock_codes': getattr(event, 'stock_codes', []),
            'topics': getattr(event, 'topics', []),
            'sentiment': getattr(event, 'sentiment', 0.5),
        }
        
        self.add_news(news)
        return True
    
    def get_recent_news(self, hours: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取最近的评分新闻
        
        Args:
            hours: 时间窗口（小时），None 表示不限
            limit: 最多返回条数
            
        Returns:
            新闻列表（按时间倒序）
        """
        with self._lock_inner:
            # 定期清理
            if time.time() - self._last_cleanup > 3600:
                self._cleanup_expired()
            
            news = self._news_list
            
            # 时间过滤
            if hours is not None:
                cutoff = time.time() - hours * 3600
                news = [n for n in news if n.get('timestamp', 0) >= cutoff]
            
            # 按时间倒序
            news = sorted(news, key=lambda x: x.get('timestamp', 0), reverse=True)
            
            return news[:limit]
    
    def get_today_news(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取今天的评分新闻"""
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        
        with self._lock_inner:
            news = [
                n for n in self._news_list
                if n.get('timestamp', 0) >= today_start
            ]
            news = sorted(news, key=lambda x: x.get('timestamp', 0), reverse=True)
            return news[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        with self._lock_inner:
            now = time.time()
            cutoff_24h = now - 24 * 3600
            today_start = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).timestamp()
            
            return {
                'total': len(self._news_list),
                'last_24h': len([n for n in self._news_list if n.get('timestamp', 0) >= cutoff_24h]),
                'today': len([n for n in self._news_list if n.get('timestamp', 0) >= today_start]),
                'cache_file': str(self._cache_file),
                'max_size': MAX_CACHE_SIZE,
            }


# 单例访问函数
_store: Optional[FocusedNewsStore] = None


def get_focused_news_store() -> FocusedNewsStore:
    """获取评分新闻存储单例"""
    global _store
    if _store is None:
        _store = FocusedNewsStore()
    return _store


def add_focused_news(event) -> bool:
    """快捷函数：添加评分新闻"""
    return get_focused_news_store().add_from_event(event)


def get_recent_focused_news(hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
    """快捷函数：获取最近评分新闻"""
    return get_focused_news_store().get_recent_news(hours=hours, limit=limit)


def get_today_focused_news(limit: int = 50) -> List[Dict[str, Any]]:
    """快捷函数：获取今天评分新闻"""
    return get_focused_news_store().get_today_news(limit=limit)
