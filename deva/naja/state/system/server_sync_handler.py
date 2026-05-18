"""
ServerDataSyncHandler - 服务器数据同步处理器

功能：
1. 从远程服务器 (ai.secsay.com) 同步市场数据
2. 支持 A股题材事件、美股热点、高分新闻、金十要闻
3. 本地数据缺失时自动从服务器补全
4. 托盘菜单和市场页面优先使用服务器数据

使用场景：
- Mac 电脑经常休眠/关机，本地数据不完整
- 服务器 24小时运行，数据更完整
- Wake 补作业时从服务器同步缺失数据
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from urllib import request, error

log = logging.getLogger(__name__)

# 服务器配置
SERVER_HOST = "ai.secsay.com"
SERVER_PORT = 8080
SERVER_BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# 本地缓存文件
LOCAL_CACHE_DIR = os.path.expanduser("~/.naja/server_sync")
SERVER_SYNC_STATE_FILE = os.path.join(LOCAL_CACHE_DIR, "server_sync_state.json")


class ServerDataSyncHandler:
    """
    服务器数据同步处理器
    
    实现 WakeSyncable 协议，在系统唤醒时自动同步服务器数据
    """

    @property
    def name(self) -> str:
        return "Server_Data_Sync"

    @property
    def description(self) -> str:
        return "从服务器同步市场数据（A股题材、美股热点、新闻）"

    @property
    def priority(self) -> int:
        return 1  # 最高优先级，先同步数据再执行其他操作

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要从服务器同步"""
        if last_active is None:
            log.info("[ServerSync] 首次启动，需要从服务器同步")
            return True

        gap_hours = (datetime.now() - last_active).total_seconds() / 3600
        
        # 休眠超过 1 小时就同步
        if gap_hours >= 1:
            log.info(f"[ServerSync] 休眠 {gap_hours:.1f} 小时，需要从服务器同步")
            return True
        
        log.info(f"[ServerSync] 仅休眠 {gap_hours:.1f} 小时，跳过同步")
        return False

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取同步时间范围"""
        now = datetime.now()
        
        # 从上次活跃时间开始同步
        start = last_active if last_active else now - timedelta(hours=max_hours)
        end = now
        
        # 限制最大同步范围
        if (end - start).total_seconds() > max_hours * 3600:
            start = end - timedelta(hours=max_hours)
        
        return start, end

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行同步 - 从服务器获取数据"""
        try:
            log.info(f"[ServerSync] 开始从服务器同步: {start} ~ {end}")
            
            results = {
                "cn_events": False,
                "us_events": False,
                "news": False,
                "jin10_news": False,
            }
            
            # 一次性从服务器获取所有事件
            try:
                all_events = self._fetch_all_events_from_server()
                
                cn_events = all_events.get("cn_events", [])
                us_events = all_events.get("us_events", [])
                news = all_events.get("news", [])
                jin10_news = all_events.get("jin10_news", [])
                
                if cn_events:
                    self._save_cn_events_to_local(cn_events)
                    results["cn_events"] = True
                    log.info(f"[ServerSync] A股题材同步成功: {len(cn_events)} 条")
                
                if us_events:
                    self._save_us_events_to_local(us_events)
                    results["us_events"] = True
                    log.info(f"[ServerSync] 美股热点同步成功: {len(us_events)} 条")
                
                if news:
                    self._save_news_to_local(news)
                    results["news"] = True
                    log.info(f"[ServerSync] 高分新闻同步成功: {len(news)} 条")
                
                if jin10_news:
                    self._save_jin10_news_to_local(jin10_news)
                    results["jin10_news"] = True
                    log.info(f"[ServerSync] 金十要闻同步成功: {len(jin10_news)} 条")
                    
            except Exception as e:
                log.warning(f"[ServerSync] 从服务器获取失败: {e}")
            
            success_count = sum(1 for v in results.values() if v)
            
            return {
                "success": success_count > 0,
                "message": f"服务器同步完成: {success_count}/4 项成功",
                "details": results
            }
            
        except Exception as e:
            log.error(f"[ServerSync] 同步异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"服务器同步异常: {str(e)}",
                "details": {}
            }

    def _fetch_all_events_from_server(self) -> Dict[str, List[Dict]]:
        """从服务器获取所有事件（一次性获取，再按类型分类）"""
        url = f"{SERVER_BASE_URL}/api/market/timeline"
        result = self._http_get(url, timeout=10)
        
        if not result:
            return {"cn_events": [], "us_events": [], "news": [], "jin10_news": []}
        
        timeline_list = result.get('list', [])
        
        cn_events = []
        us_events = []
        news = []
        jin10_news = []
        
        for item in timeline_list:
            event_type = item.get('type', '')
            if event_type == 'cn_event':
                cn_events.append(item)
            elif event_type == 'us_event':
                us_events.append(item)
            elif event_type == 'high_score_news':
                news.append(item)
            elif event_type == 'jin10_news':
                jin10_news.append(item)
        
        return {
            "cn_events": cn_events,
            "us_events": us_events,
            "news": news,
            "jin10_news": jin10_news,
        }

    def _http_get(self, url: str, timeout: int = 10) -> Optional[Dict]:
        """HTTP GET 请求获取 JSON 数据"""
        try:
            req = request.Request(url, headers={
                "User-Agent": "NajaClient/1.0",
                "Accept": "application/json"
            })
            with request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, dict):
                    return data
                return None
        except error.HTTPError as e:
            log.warning(f"[ServerSync] HTTP {e.code}: {url}")
            return None
        except error.URLError as e:
            log.warning(f"[ServerSync] URL Error: {e.reason}")
            return None
        except Exception as e:
            log.warning(f"[ServerSync] Request failed: {e}")
            return None

    def _http_get_json(self, url: str, timeout: int = 10) -> List[Dict]:
        """HTTP GET 请求获取 JSON 数据"""
        try:
            req = request.Request(url, headers={
                "User-Agent": "NajaClient/1.0",
                "Accept": "application/json"
            })
            with request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and 'data' in data:
                    return data['data']
                return []
        except error.HTTPError as e:
            log.warning(f"[ServerSync] HTTP {e.code}: {url}")
            return []
        except error.URLError as e:
            log.warning(f"[ServerSync] URL Error: {e.reason}")
            return []
        except Exception as e:
            log.warning(f"[ServerSync] Request failed: {e}")
            return []

    def _save_cn_events_to_local(self, events: List[Dict]):
        """保存 A股题材事件到本地缓存"""
        os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(LOCAL_CACHE_DIR, "cn_events_server.json")
        
        # 合并已有数据
        existing = []
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    existing = json.load(f)
            except:
                pass
        
        # 去重合并
        seen_timestamps = {e.get('timestamp') for e in existing}
        merged = existing.copy()
        for event in events:
            if event.get('timestamp') not in seen_timestamps:
                merged.append(event)
                seen_timestamps.add(event.get('timestamp'))
        
        # 只保留最近 48 小时的数据
        cutoff = time.time() - 48 * 3600
        merged = [e for e in merged if e.get('timestamp', 0) >= cutoff]
        
        with open(cache_file, 'w') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        
        log.debug(f"[ServerSync] 保存 A股题材: {len(merged)} 条")

    def _save_us_events_to_local(self, events: List[Dict]):
        """保存美股热点到本地缓存"""
        os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(LOCAL_CACHE_DIR, "us_events_server.json")
        
        existing = []
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    existing = json.load(f)
            except:
                pass
        
        seen_timestamps = {e.get('timestamp') for e in existing}
        merged = existing.copy()
        for event in events:
            if event.get('timestamp') not in seen_timestamps:
                merged.append(event)
                seen_timestamps.add(event.get('timestamp'))
        
        cutoff = time.time() - 48 * 3600
        merged = [e for e in merged if e.get('timestamp', 0) >= cutoff]
        
        with open(cache_file, 'w') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    def _save_news_to_local(self, news: List[Dict]):
        """保存高分新闻到本地缓存"""
        os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(LOCAL_CACHE_DIR, "news_server.json")
        
        existing = []
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    existing = json.load(f)
            except:
                pass
        
        seen_ids = {n.get('id') or n.get('timestamp') for n in existing}
        merged = existing.copy()
        for item in news:
            item_id = item.get('id') or item.get('timestamp')
            if item_id not in seen_ids:
                merged.append(item)
                seen_ids.add(item_id)
        
        cutoff = time.time() - 48 * 3600
        merged = [n for n in merged if n.get('timestamp', 0) >= cutoff]
        
        with open(cache_file, 'w') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    def _save_jin10_news_to_local(self, news: List[Dict]):
        """保存金十要闻到本地缓存"""
        os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(LOCAL_CACHE_DIR, "jin10_news_server.json")
        
        existing = []
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    existing = json.load(f)
            except:
                pass
        
        seen_ids = {n.get('flash_id') or n.get('timestamp') for n in existing}
        merged = existing.copy()
        for item in news:
            item_id = item.get('flash_id') or item.get('timestamp')
            if item_id not in seen_ids:
                merged.append(item)
                seen_ids.add(item_id)
        
        cutoff = time.time() - 48 * 3600
        merged = [n for n in merged if n.get('timestamp', 0) >= cutoff]
        
        with open(cache_file, 'w') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)


# ============ 数据获取函数（优先从服务器，失败回退本地）============

def get_cn_events_from_server_or_local(hours: int = 24) -> List[Dict]:
    """
    获取 A股题材事件，优先从服务器缓存获取
    
    策略：
    1. 先尝试从服务器缓存读取
    2. 如果数据不足，再尝试从本地获取
    3. 合并去重后返回
    """
    events = []
    
    # 1. 从服务器缓存读取
    server_cache = os.path.join(LOCAL_CACHE_DIR, "cn_events_server.json")
    if os.path.exists(server_cache):
        try:
            with open(server_cache, 'r') as f:
                server_events = json.load(f)
            cutoff = time.time() - hours * 3600
            events = [e for e in server_events if e.get('timestamp', 0) >= cutoff]
            log.debug(f"[ServerSync] 从服务器缓存读取 A股题材: {len(events)} 条")
        except Exception as e:
            log.warning(f"[ServerSync] 读取服务器缓存失败: {e}")
    
    # 2. 如果服务器数据不足，补充本地数据
    if len(events) < 5:
        try:
            from deva.naja.market_hotspot.storing.block_events_store import get_cn_block_events
            local_events = get_cn_block_events(hours=hours)
            
            # 合并去重
            seen_timestamps = {e.get('timestamp') for e in events}
            for event in local_events:
                if event.get('timestamp') not in seen_timestamps:
                    events.append(event)
                    seen_timestamps.add(event.get('timestamp'))
            
            log.debug(f"[ServerSync] 补充本地 A股题材: {len(events)} 条")
        except Exception as e:
            log.warning(f"[ServerSync] 获取本地数据失败: {e}")
    
    return events


def get_us_events_from_server_or_local(hours: int = 24) -> List[Dict]:
    """获取美股热点，优先从服务器缓存获取"""
    events = []
    
    server_cache = os.path.join(LOCAL_CACHE_DIR, "us_events_server.json")
    if os.path.exists(server_cache):
        try:
            with open(server_cache, 'r') as f:
                server_events = json.load(f)
            cutoff = time.time() - hours * 3600
            events = [e for e in server_events if e.get('timestamp', 0) >= cutoff]
        except Exception as e:
            log.warning(f"[ServerSync] 读取服务器缓存失败: {e}")
    
    if len(events) < 3:
        try:
            from deva.naja.market_hotspot.storing.block_events_store import get_us_block_events
            local_events = get_us_block_events(hours=hours)
            
            seen_timestamps = {e.get('timestamp') for e in events}
            for event in local_events:
                if event.get('timestamp') not in seen_timestamps:
                    events.append(event)
                    seen_timestamps.add(event.get('timestamp'))
        except Exception as e:
            log.warning(f"[ServerSync] 获取本地数据失败: {e}")
    
    return events


def get_news_from_server_or_local(hours: int = 24) -> List[Dict]:
    """获取高分新闻，优先从服务器缓存获取"""
    news = []
    
    server_cache = os.path.join(LOCAL_CACHE_DIR, "news_server.json")
    if os.path.exists(server_cache):
        try:
            with open(server_cache, 'r') as f:
                server_news = json.load(f)
            cutoff = time.time() - hours * 3600
            news = [n for n in server_news if n.get('timestamp', 0) >= cutoff]
        except Exception as e:
            log.warning(f"[ServerSync] 读取服务器缓存失败: {e}")
    
    if len(news) < 5:
        try:
            from deva.naja.events.focused_news_store import get_today_focused_news
            local_news = get_today_focused_news(limit=50)
            
            seen_ids = {n.get('id') or n.get('timestamp') for n in news}
            for item in local_news:
                item_id = item.get('id') or item.get('timestamp')
                if item_id not in seen_ids:
                    news.append(item)
                    seen_ids.add(item_id)
        except Exception as e:
            log.warning(f"[ServerSync] 获取本地数据失败: {e}")
    
    return news


def get_jin10_news_from_server_or_local(hours: int = 24) -> List[Dict]:
    """获取金十要闻，优先从服务器缓存获取"""
    news = []
    
    server_cache = os.path.join(LOCAL_CACHE_DIR, "jin10_news_server.json")
    if os.path.exists(server_cache):
        try:
            with open(server_cache, 'r') as f:
                server_news = json.load(f)
            cutoff = time.time() - hours * 3600
            news = [n for n in server_news if n.get('timestamp', 0) >= cutoff]
        except Exception as e:
            log.warning(f"[ServerSync] 读取服务器缓存失败: {e}")
    
    if len(news) < 5:
        try:
            # 尝试从本地 jin10 缓存读取
            local_cache = os.path.expanduser("~/.naja/jin10_news.json")
            if os.path.exists(local_cache):
                with open(local_cache, 'r') as f:
                    local_news = json.load(f)
                
                cutoff = time.time() - hours * 3600
                seen_ids = {n.get('flash_id') or n.get('timestamp') for n in news}
                for item in local_news:
                    item_id = item.get('flash_id') or item.get('timestamp')
                    if item_id not in seen_ids:
                        # 解析时间
                        display_time = item.get('display_time', '')
                        if display_time:
                            try:
                                dt = datetime.strptime(display_time, "%Y-%m-%d %H:%M:%S")
                                ts = dt.timestamp()
                                if ts >= cutoff:
                                    item['timestamp'] = ts
                                    news.append(item)
                                    seen_ids.add(item_id)
                            except:
                                pass
        except Exception as e:
            log.warning(f"[ServerSync] 获取本地数据失败: {e}")
    
    return news
