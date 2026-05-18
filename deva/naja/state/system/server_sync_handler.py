"""
ServerDataSyncHandler - 智能服务器数据同步处理器

核心功能：
1. 智能增量同步：只补本地缺失的数据
2. 根据休眠时长动态调整同步范围
3. 数据级别去重：基于时间戳/ID避免重复
4. 支持优先级同步：关键数据优先
5. 幂等性保障：重复调用不产生副作用

同步策略：
- 短休眠(<1小时)：仅同步关键数据（持仓价格）
- 中等休眠(1-4小时)：同步核心数据（价格+新闻+题材）
- 较长休眠(4-24小时)：完整同步所有数据
- 长时间休眠(>24小时)：恢复模式，同步最近24小时

使用场景：
- Mac 电脑经常休眠/关机，本地数据不完整
- 服务器 24小时运行，数据更完整
- Wake 补作业时从服务器智能同步缺失数据
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

    def _get_sync_scope(self, last_active: datetime) -> str:
        """
        根据休眠时长判断同步范围
        
        返回值：
        - 'minimal': 短休眠(<1小时)，仅同步关键数据
        - 'core': 中等休眠(1-4小时)，同步核心数据
        - 'full': 较长休眠(4-24小时)，完整同步
        - 'recovery': 长时间休眠(>24小时)，恢复模式
        """
        if last_active is None:
            return 'recovery'  # 首次启动，恢复模式
        
        gap_hours = (datetime.now() - last_active).total_seconds() / 3600
        
        if gap_hours < 1:
            return 'minimal'
        elif gap_hours < 4:
            return 'core'
        elif gap_hours < 24:
            return 'full'
        else:
            return 'recovery'

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要从服务器同步"""
        if last_active is None:
            log.info("[ServerSync] 首次启动，需要从服务器同步")
            return True

        gap_hours = (datetime.now() - last_active).total_seconds() / 3600
        
        # 休眠超过 30 分钟就同步（比之前更敏感）
        if gap_hours >= 0.5:
            scope = self._get_sync_scope(last_active)
            log.info(f"[ServerSync] 休眠 {gap_hours:.1f} 小时，同步范围: {scope}")
            return True
        
        log.info(f"[ServerSync] 仅休眠 {gap_hours:.1f} 小时，跳过同步")
        return False

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取同步时间范围"""
        now = datetime.now()
        scope = self._get_sync_scope(last_active)
        
        # 根据同步范围确定起始时间
        if scope == 'minimal':
            # 短休眠：只同步最近30分钟
            start = now - timedelta(minutes=30)
        elif scope == 'core':
            # 中等休眠：同步从上次活跃时间开始
            start = last_active if last_active else now - timedelta(hours=4)
        elif scope == 'full':
            # 较长休眠：同步从上次活跃时间开始
            start = last_active if last_active else now - timedelta(hours=24)
        else:  # recovery
            # 恢复模式：最多同步最近24小时
            start = now - timedelta(hours=24)
        
        end = now
        
        # 限制最大同步范围
        max_delta = timedelta(hours=max_hours)
        if end - start > max_delta:
            start = end - max_delta
        
        log.info(f"[ServerSync] 同步范围: {scope}，时间区间: {start} ~ {end}")
        return start, end

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行智能增量同步 - 根据休眠时长动态选择同步内容"""
        try:
            log.info(f"[ServerSync] 开始智能同步: {start} ~ {end}")
            
            # 获取本地已有数据的时间戳范围（用于增量判断）
            local_stats = self._get_local_data_stats()
            
            results = {
                "cn_events": {"success": False, "added": 0, "skipped": 0},
                "us_events": {"success": False, "added": 0, "skipped": 0},
                "news": {"success": False, "added": 0, "skipped": 0},
                "jin10_news": {"success": False, "added": 0, "skipped": 0},
            }
            
            # 根据同步范围决定要同步的数据类型
            scope = self._get_sync_scope(self._last_active_time)
            log.info(f"[ServerSync] 当前同步范围: {scope}")
            
            # 构建要同步的数据类型列表
            sync_types = []
            if scope == 'minimal':
                # 短休眠：只同步最关键的数据
                sync_types = ['cn_events', 'us_events']
            elif scope == 'core':
                # 中等休眠：同步核心数据
                sync_types = ['cn_events', 'us_events', 'jin10_news']
            else:
                # full/recovery：同步所有数据
                sync_types = ['cn_events', 'us_events', 'news', 'jin10_news']
            
            log.info(f"[ServerSync] 需要同步的数据类型: {sync_types}")
            
            # 一次性从服务器获取所有事件
            try:
                all_events = self._fetch_all_events_from_server()
                
                for data_type in sync_types:
                    events = all_events.get(data_type, [])
                    if not events:
                        log.debug(f"[ServerSync] {data_type}: 服务器无数据")
                        continue
                    
                    # 增量同步：过滤掉本地已有的数据
                    filtered_events, skipped_count = self._filter_existing_data(events, data_type, local_stats)
                    
                    if filtered_events:
                        save_method = getattr(self, f"_save_{data_type}_to_local", None)
                        if save_method:
                            save_method(filtered_events)
                            results[data_type] = {
                                "success": True,
                                "added": len(filtered_events),
                                "skipped": skipped_count
                            }
                            log.info(f"[ServerSync] {data_type} 同步成功: 新增 {len(filtered_events)} 条，跳过 {skipped_count} 条")
                        else:
                            log.warning(f"[ServerSync] {data_type}: 没有对应的保存方法")
                    else:
                        results[data_type] = {
                            "success": True,
                            "added": 0,
                            "skipped": skipped_count
                        }
                        log.info(f"[ServerSync] {data_type}: 本地数据已完整，无需同步")
                    
            except Exception as e:
                log.warning(f"[ServerSync] 从服务器获取失败: {e}")
            
            # 统计成功数量
            success_count = sum(1 for v in results.values() if v.get('success'))
            total_added = sum(v.get('added', 0) for v in results.values())
            total_skipped = sum(v.get('skipped', 0) for v in results.values())
            
            return {
                "success": success_count > 0,
                "message": f"智能同步完成: {success_count}/{len(sync_types)} 项成功，新增 {total_added} 条，跳过 {total_skipped} 条（本地已有）",
                "details": results,
                "scope": scope,
                "sync_types": sync_types,
                "stats": {"added": total_added, "skipped": total_skipped}
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

    def _get_local_data_stats(self) -> Dict[str, Dict[str, float]]:
        """获取本地各数据类型的时间戳统计"""
        stats = {}
        cutoff = time.time() - 48 * 3600  # 只考虑最近48小时
        
        for data_type in ['cn_events', 'us_events', 'news', 'jin10_news']:
            cache_file = os.path.join(LOCAL_CACHE_DIR, f"{data_type}_server.json")
            stats[data_type] = {
                'latest_ts': 0,
                'count': 0
            }
            
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                        if data:
                            # 获取最近时间戳
                            timestamps = []
                            for item in data:
                                ts = item.get('timestamp')
                                if ts:
                                    if isinstance(ts, str):
                                        try:
                                            ts = float(ts)
                                        except:
                                            continue
                                    timestamps.append(ts)
                            
                            if timestamps:
                                stats[data_type]['latest_ts'] = max(timestamps)
                                stats[data_type]['count'] = len([t for t in timestamps if t >= cutoff])
                except Exception as e:
                    log.debug(f"[ServerSync] 读取本地统计失败 {data_type}: {e}")
        
        log.debug(f"[ServerSync] 本地数据统计: {stats}")
        return stats

    def _filter_existing_data(self, events: List[Dict], data_type: str, local_stats: Dict) -> Tuple[List[Dict], int]:
        """
        过滤掉本地已有的数据，实现增量同步
        
        返回：(需要新增的事件列表, 已跳过的数量)
        """
        if not events:
            return [], 0
        
        local_latest_ts = local_stats.get(data_type, {}).get('latest_ts', 0)
        
        filtered = []
        skipped = 0
        
        for event in events:
            # 获取事件时间戳
            ts = event.get('timestamp')
            if ts:
                if isinstance(ts, str):
                    try:
                        ts = float(ts)
                    except:
                        filtered.append(event)
                        continue
            
            # 如果事件时间戳大于本地最新时间戳，说明是新数据
            if not ts or ts > local_latest_ts:
                filtered.append(event)
            else:
                skipped += 1
        
        return filtered, skipped

    @property
    def _last_active_time(self) -> Optional[datetime]:
        """获取上次活跃时间（用于判断同步范围）"""
        try:
            if os.path.exists(SERVER_SYNC_STATE_FILE):
                with open(SERVER_SYNC_STATE_FILE, 'r') as f:
                    state = json.load(f)
                    last_sync = state.get('last_sync_time')
                    if last_sync:
                        return datetime.fromisoformat(last_sync)
        except:
            pass
        return None

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
