"""
TextFocusedEvent 轻量级持久化存储

只存储最近 ``CACHE_HOURS`` 小时的评分新闻数据，用于系统重启后恢复。

❗保留时长必须 **>= `/news` 页面的最大窗口（72h）**：池子只留 24h 时，
页面上的「48h / 72h」按钮参数虽然真的透传到了取数层，但上游根本没有那么久的
数据 —— 三个按钮返回同一批，用户点完只看到页头数字变了、内容没有任何变化，
会以为按钮坏了。这类「接线正确但永远无效」比报错更难发现。
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
# ❗这两个数不是随便定的：
#   CACHE_HOURS 必须 >= /news 的最大窗口（72h），否则 48h/72h 按钮永远等价于 24h；
#   MAX_CACHE_SIZE 必须容得下 CACHE_HOURS 的流量（实测约 7.8 条/小时 →
#   72h ≈ 560 条，留 ~40% 余量取 800），否则高峰期会被裁剪到"看起来只有最近几小时"。
MAX_CACHE_SIZE = 800  # 最多 800 条（约 0.8 MB）
CACHE_HOURS = 72  # 保留最近 72 小时（与 /news 窗口上限对齐）

#: ``/news`` 页面提供的窗口（小时）。存储保留时长要覆盖它 —— 守卫
#: ``verify_news_digest`` 会静态校验 ``CACHE_HOURS >= max(NEWS_WINDOWS)``。
NEWS_WINDOWS = (24, 48, 72)


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
    
    def get_coverage(self) -> Dict[str, Any]:
        """池子**实际覆盖**了多长的时间（不是配置里的保留时长）。

        用途：``/news`` 的「48h / 72h」按钮只有在池子里真有那么久的数据时才有
        意义。一旦窗口超过实际覆盖，结果与更小窗口逐字相同 —— 不报错、不提示，
        用户只会以为按钮没用。所以把「实际覆盖」如实交出去，让 UI 能说明原因。

        Returns:
            total: 池内条数
            oldest_age_hours: 最早一条距现在多少小时；**空池为 None**（不是 0，
                0 会被理解成"刚采到"，与"没有数据"语义相反）
            retention_hours / capacity: 配置的保留时长与容量上限
            at_capacity: 是否已顶到容量上限（此时"覆盖时长"是被裁剪出来的）
        """
        with self._lock_inner:
            total = len(self._news_list)
            oldest_age_hours: Optional[float] = None
            if total:
                oldest = min(n.get('timestamp', 0) for n in self._news_list)
                if oldest > 0:
                    oldest_age_hours = max(0.0, (time.time() - oldest) / 3600.0)
            return {
                "total": total,
                "oldest_age_hours": oldest_age_hours,
                "retention_hours": CACHE_HOURS,
                "capacity": MAX_CACHE_SIZE,
                "at_capacity": total >= MAX_CACHE_SIZE,
            }

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
                'last_24h': sum(1 for n in self._news_list if n.get('timestamp', 0) >= cutoff_24h),
                'today': sum(1 for n in self._news_list if n.get('timestamp', 0) >= today_start),
                'cache_file': str(self._cache_file),
                'max_size': MAX_CACHE_SIZE,
                'retention_hours': CACHE_HOURS,
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
