"""策略执行结果存储模块

提供策略执行结果的存储、查询和导出功能。
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from queue import Queue
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva import NB

try:
    from ..log_stream import get_log_stream, log_strategy
    LOG_STREAM_AVAILABLE = True
except ImportError:
    LOG_STREAM_AVAILABLE = False

# 尝试导入锁监控模块
try:
    from ..performance.lock_monitor import LockMonitor, MonitoredLock, enable_lock_monitoring, disable_lock_monitoring
    LOCK_MONITOR_AVAILABLE = True
except ImportError:
    LOCK_MONITOR_AVAILABLE = False


@dataclass
class StrategyResult:
    """策略执行结果"""
    id: str
    strategy_id: str
    strategy_name: str
    ts: float
    success: bool
    input_preview: str = ""
    output_preview: str = ""
    output_full: Any = None
    process_time_ms: float = 0
    error: str = ""
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """序列化为用于持久化/传输的精简字典。

        设计目标：
        - 始终包含元信息与 preview（input/output_preview）
        - 默认不持久化 output_full，避免占用大量磁盘空间
          （完整结果在内存和下游组件中使用，如 SignalStream / Radar / Memory）
        """
        result = {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "ts": self.ts,
            "ts_readable": datetime.fromtimestamp(self.ts).strftime("%Y-%m-%d %H:%M:%S"),
            "success": self.success,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
            "process_time_ms": self.process_time_ms,
            "error": self.error,
            "metadata": self.metadata,
        }
        return result
    
    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "ts": self.ts,
            "ts_readable": datetime.fromtimestamp(self.ts).strftime("%Y-%m-%d %H:%M:%S"),
            "success": self.success,
            "process_time_ms": self.process_time_ms,
            "error": self.error[:100] if self.error else "",
        }


class ResultStore:
    """策略执行结果存储器"""
    
    _instance = None
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
        
        self._cache: Dict[str, deque] = {}
        self._db = NB("naja_strategy_results")
        self._index_db = NB("naja_result_index")  # 用于存储反向索引
        self._stats = {
            "total_results": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_process_time_ms": 0,
        }
        
        # 使用可监控的锁
        if LOCK_MONITOR_AVAILABLE:
            self._data_lock = MonitoredLock("ResultStore._data_lock")
        else:
            self._data_lock = threading.RLock()
        
        # 统计缓存
        self._stats_cache = None
        self._stats_cache_time = 0
        self._stats_cache_ttl = 2.0  # 缓存2秒
        
        # 异步写入相关
        self._write_queue = Queue(maxsize=10000)
        self._write_thread = threading.Thread(target=self._process_write_queue, daemon=True)
        self._write_thread.start()
        
        # 缓存管理
        self._max_cache_size = 100
        self._cache_stats = {}
        self._cache_cleanup_interval = 60  # 60秒
        self._last_cache_cleanup = time.time()
        
        # 数据清理管理
        self._data_cleanup_interval = 3600  # 1小时
        self._last_data_cleanup = time.time()
        
        # 写入速率限制
        self._write_rate_limit = 1000
        self._writes_in_period = 0
        self._last_rate_check = time.time()
        
        # 监控和限流
        self._monitoring = {
            'write_queue_size': 0,
            'write_rate': 0,
            'last_write_time': 0,
            'total_writes': 0,
            'failed_writes': 0
        }
        self._max_queue_size = 10000  # 最大队列大小
        self._max_history_days = 7  # 默认保留7天数据
        
        # 启动缓存清理线程（只启动一次）
        self._cache_cleanup_thread = threading.Thread(target=self._cleanup_cache, daemon=True)
        self._cache_cleanup_thread.start()
        
        # 启动数据清理线程（只启动一次）
        self._data_cleanup_thread = threading.Thread(target=self._cleanup_data, daemon=True)
        self._data_cleanup_thread.start()
        
        self._initialized = True
    
    def _get_cached_stats(self) -> dict:
        """获取缓存的统计数据（带缓存机制）- 非阻塞版本"""
        import time
        now = time.time()
        
        # 检查缓存是否有效（优先使用缓存）
        if self._stats_cache is not None and (now - self._stats_cache_time) < self._stats_cache_ttl:
            return self._stats_cache
        
        # 尝试非阻塞获取锁
        wait_start = time.time()
        acquired = self._data_lock.acquire(blocking=False)
        wait_time = (time.time() - wait_start) * 1000  # 转换为毫秒
        
        # 记录锁等待性能（只有超过阈值才记录，避免干扰）
        if wait_time > 10 and LOCK_MONITOR_AVAILABLE and LockMonitor.is_enabled():
            try:
                from ..performance import record_lock_wait
                record_lock_wait(
                    lock_name="ResultStore_stats",
                    wait_time_ms=wait_time,
                    operation="get_stats",
                )
            except Exception:
                pass
        
        if acquired:
            try:
                stats = dict(self._stats)
                self._stats_cache = stats
                self._stats_cache_time = now
                return stats
            finally:
                self._data_lock.release()
        else:
            # 如果无法获取锁，返回过期的缓存（避免阻塞）
            if self._stats_cache is not None:
                return self._stats_cache
            
            # 如果没有缓存，强制获取锁
            wait_start = time.time()
            with self._data_lock:
                wait_time = (time.time() - wait_start) * 1000
                # 记录锁等待性能
                if wait_time > 10 and LOCK_MONITOR_AVAILABLE and LockMonitor.is_enabled():
                    try:
                        from ..performance import record_lock_wait
                        record_lock_wait(
                            lock_name="ResultStore_stats",
                            wait_time_ms=wait_time,
                            operation="get_stats_fallback",
                        )
                    except Exception:
                        pass
                
                stats = dict(self._stats)
                self._stats_cache = stats
                self._stats_cache_time = now
                return stats
    
    def _invalidate_stats_cache(self):
        """使统计缓存失效"""
        self._stats_cache = None
    
    def _generate_id(self, strategy_id: str, ts: float) -> str:
        import hashlib
        hash_input = f"{strategy_id}_{ts}_{time.time()}".encode()
        return hashlib.md5(hash_input).hexdigest()[:12]
    
    def _truncate_preview(self, data: Any, max_len: int = 500) -> str:
        if data is None:
            return ""
        try:
            if isinstance(data, str):
                preview = data
            elif isinstance(data, dict):
                preview = json.dumps(data, ensure_ascii=False)
            elif hasattr(data, 'to_dict'):
                preview = json.dumps(data.to_dict(), ensure_ascii=False)
            elif hasattr(data, '__len__') and len(data) > 0:
                if hasattr(data, 'head'):
                    preview = str(data.head(3).to_dict())
                else:
                    preview = str(list(data)[:5])
            else:
                preview = str(data)
            return preview[:max_len] + "..." if len(preview) > max_len else preview
        except Exception:
            return str(type(data))
    
    def _process_write_queue(self):
        """后台线程处理写入队列（支持批量写入）"""
        batch_size = 100
        batch_timeout = 1.0  # 1秒超时
        batch = []
        last_batch_time = time.time()
        
        while True:
            try:
                # 非阻塞获取队列中的数据
                try:
                    item = self._write_queue.get(block=False)
                    if item is None:
                        break
                    batch.append(item)
                    last_batch_time = time.time()
                except Exception:
                    # 队列为空，检查是否需要执行批量写入
                    if batch and (len(batch) >= batch_size or time.time() - last_batch_time >= batch_timeout):
                        # 执行批量写入
                        self._batch_write(batch)
                        batch = []
                        last_batch_time = time.time()
                    else:
                        # 短暂休眠，避免CPU空转
                        time.sleep(0.01)
                        continue
                
                # 检查是否达到批量大小
                if len(batch) >= batch_size:
                    self._batch_write(batch)
                    batch = []
                    last_batch_time = time.time()
            except Exception as e:
                # 线程异常，记录并继续运行
                self._monitoring['failed_writes'] += 1
                time.sleep(0.1)
    
    def _batch_write(self, batch):
        """批量写入数据"""
        try:
            # 构建批量更新的映射
            batch_data = {}
            index_data = {}
            for item in batch:
                strategy_id, result_id, result_dict = item
                key = f"{strategy_id}:{result_id}"
                batch_data[key] = result_dict
                # 创建反向索引：result_id -> key
                index_data[f"id:{result_id}"] = key
            
            # 使用 bulk_update 进行真正的批量写入
            if batch_data:
                self._db.bulk_update(batch_data)
            
            # 批量更新索引
            if index_data:
                self._index_db.bulk_update(index_data)
            
            # 标记所有任务完成
            for _ in batch:
                self._write_queue.task_done()
        except Exception as e:
            # 批量写入失败，记录失败次数并确保所有任务都被标记为完成
            self._monitoring['failed_writes'] += len(batch)
            for _ in batch:
                self._write_queue.task_done()
    
    def _cleanup_cache(self):
        """定期清理缓存"""
        while True:
            try:
                time.sleep(self._cache_cleanup_interval)
                
                current_time = time.time()
                if current_time - self._last_cache_cleanup < self._cache_cleanup_interval:
                    continue
                
                self._last_cache_cleanup = current_time
                
                with self._data_lock:
                    # 清理长时间未使用的缓存
                    for strategy_id in list(self._cache.keys()):
                        if strategy_id not in self._cache_stats:
                            # 从未使用过的缓存，清理掉
                            del self._cache[strategy_id]
                            continue
                        
                        last_access = self._cache_stats.get(strategy_id, {}).get('last_access', 0)
                        if current_time - last_access > 3600:  # 1小时未使用
                            del self._cache[strategy_id]
                            if strategy_id in self._cache_stats:
                                del self._cache_stats[strategy_id]
            except Exception:
                # 清理线程异常，继续运行
                time.sleep(1)
    
    def _cleanup_data(self):
        """定期清理过期数据"""
        while True:
            try:
                time.sleep(self._data_cleanup_interval)
                
                current_time = time.time()
                if current_time - self._last_data_cleanup < self._data_cleanup_interval:
                    continue
                
                self._last_data_cleanup = current_time
                
                # 计算过期时间戳（7天前）
                expire_ts = current_time - (self._max_history_days * 24 * 3600)
                
                with self._data_lock:
                    # 遍历数据库获取过期数据的键
                    keys_to_delete = []
                    for key in self._db.keys():
                        data = self._db.get(key)
                        if isinstance(data, dict):
                            ts = data.get("ts", 0)
                            if ts < expire_ts:
                                keys_to_delete.append(key)
                    
                    # 收集要删除的索引
                    index_keys_to_delete = []
                    for key in keys_to_delete:
                        data = self._db.get(key)
                        if isinstance(data, dict):
                            result_id = data.get("id")
                            if result_id:
                                index_keys_to_delete.append(f"id:{result_id}")
                    
                    # 执行批量删除数据
                    for key in keys_to_delete:
                        try:
                            if key in self._db:
                                del self._db[key]
                        except KeyError:
                            pass
                    
                    # 执行批量删除索引
                    for index_key in index_keys_to_delete:
                        try:
                            if index_key in self._index_db:
                                del self._index_db[index_key]
                        except KeyError:
                            pass
                    
                    # 清理缓存中可能存在的过期数据
                    for strategy_id in list(self._cache.keys()):
                        cache_items = list(self._cache[strategy_id])
                        valid_items = [item for item in cache_items if item.ts >= expire_ts]
                        if valid_items:
                            self._cache[strategy_id] = deque(valid_items, maxlen=self._max_cache_size)
                        else:
                            del self._cache[strategy_id]
                            if strategy_id in self._cache_stats:
                                del self._cache_stats[strategy_id]
            except Exception:
                # 清理线程异常，继续运行
                time.sleep(1)
    
    def save(
        self,
        strategy_id: str,
        strategy_name: str,
        success: bool,
        input_data: Any = None,
        output_data: Any = None,
        process_time_ms: float = 0,
        error: str = "",
        metadata: Dict = None,
        persist: bool = True,
    ) -> StrategyResult:
        ts = time.time()
        result_id = self._generate_id(strategy_id, ts)
        
        result = StrategyResult(
            id=result_id,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            ts=ts,
            success=success,
            input_preview=self._truncate_preview(input_data),
            output_preview=self._truncate_preview(output_data),
            output_full=output_data if success else None,
            process_time_ms=process_time_ms,
            error=error,
            metadata=metadata or {},
        )
        
        # 先发送到信号流（始终发送，除非明确关闭）
        try:
            from ..signal.stream import get_signal_stream
            signal_stream = get_signal_stream()
            signal_stream.update(result)
        except Exception as e:
            pass
        
        # 发送到洞察池（用户注意力输出）
        try:
            from ..insight import get_insight_pool
            pool = get_insight_pool()
            pool.ingest_result(result)
        except Exception:
            pass

        # 检查输出配置
        try:
            from .output_controller import get_output_controller
            controller = get_output_controller()
            should_radar = controller.should_send_to(strategy_id, "radar")
            should_memory = controller.should_send_to(strategy_id, "memory")
            should_bandit = controller.should_send_to(strategy_id, "bandit")
        except Exception:
            should_radar = True  # 默认开启
            should_memory = True
            should_bandit = False

        # 规范化输出数据
        targets = set()
        if should_radar:
            targets.add("radar")
        if should_memory:
            targets.add("memory")
        if should_bandit:
            targets.add("bandit")
        
        try:
            from .output_schema import normalize_output
            normalized = normalize_output(result, targets)
        except Exception:
            normalized = {}

        # 发送到雷达引擎（根据配置，使用规范化数据）
        if should_radar and normalized.get("radar"):
            try:
                from ..radar import get_radar_engine
                radar = get_radar_engine()
                radar.ingest_result(result)
            except Exception:
                pass

        # 发送到记忆引擎（根据配置）
        if should_memory:
            try:
                from ..memory import get_memory_engine
                memory = get_memory_engine()
                memory.ingest_result(result)
            except Exception:
                pass
        
        # Bandit 信号处理（在信号流中过滤）
        if should_bandit:
            try:
                from ..bandit import get_bandit_optimizer
                optimizer = get_bandit_optimizer()
                score = normalized.get("bandit", {}).get("score", 0)
                if score != 0:
                    optimizer.update_reward(strategy_id, score)
            except Exception:
                pass
        
        # 记录策略执行日志
        if LOG_STREAM_AVAILABLE:
            try:
                signal_type = ""
                if isinstance(output_data, dict):
                    signal_type = output_data.get("signal_type", "")
                level = "INFO" if success else "ERROR"
                message = f"策略执行{'成功' if success else '失败'}: {strategy_name}, 信号类型: {signal_type}"
                log_strategy(level, strategy_id, strategy_name, message, 
                           score=output_data.get("score") if isinstance(output_data, dict) else None,
                           process_time_ms=process_time_ms)
            except Exception:
                pass
        
        with self._data_lock:
            if strategy_id not in self._cache:
                self._cache[strategy_id] = deque(maxlen=self._max_cache_size)
            self._cache[strategy_id].appendleft(result)
            
            # 更新缓存统计
            if strategy_id not in self._cache_stats:
                self._cache_stats[strategy_id] = {
                    'access_count': 0,
                    'last_access': ts,
                    'last_write': ts
                }
            else:
                self._cache_stats[strategy_id]['last_write'] = ts
            
            self._stats["total_results"] += 1
            if success:
                self._stats["total_success"] += 1
            else:
                self._stats["total_failed"] += 1
            self._stats["total_process_time_ms"] += process_time_ms
            
            # 使统计缓存失效
            self._invalidate_stats_cache()
            
            if persist:
                try:
                    # 检查速率限制
                    current_time = time.time()
                    if current_time - self._last_rate_check >= 60:  # 每分钟重置
                        self._writes_in_period = 0
                        self._last_rate_check = current_time
                    
                    if self._writes_in_period >= self._write_rate_limit:
                        # 超过速率限制，暂时不写入
                        return result
                    
                    # 检查队列大小
                    queue_size = self._write_queue.qsize()
                    if queue_size >= self._max_queue_size:
                        # 队列已满，暂时不写入
                        return result
                    
                    # 将写入操作放入队列，由后台线程处理
                    self._write_queue.put((strategy_id, result_id, result.to_dict()))
                    
                    # 更新监控统计
                    self._monitoring['write_queue_size'] = self._write_queue.qsize()
                    self._monitoring['last_write_time'] = current_time
                    self._monitoring['total_writes'] += 1
                    self._writes_in_period += 1
                    self._monitoring['write_rate'] = self._writes_in_period / max(1, current_time - self._last_rate_check) * 60
                except Exception:
                    self._monitoring['failed_writes'] += 1
                    pass
        
        return result
    
    def get_recent(
        self,
        strategy_id: str,
        limit: int = 10,
    ) -> List[StrategyResult]:
        current_time = time.time()
        
        with self._data_lock:
            if strategy_id in self._cache:
                results = list(self._cache[strategy_id])[:limit]
                if results:
                    # 更新缓存访问统计
                    if strategy_id in self._cache_stats:
                        self._cache_stats[strategy_id]['access_count'] += 1
                        self._cache_stats[strategy_id]['last_access'] = current_time
                    return results
            
            db_results = []
            
            # 利用时间切片获取最近的数据，避免全表扫描
            # 计算30天前的时间戳
            thirty_days_ago = current_time - (30 * 24 * 3600)
            start_str = datetime.fromtimestamp(thirty_days_ago).strftime("%Y-%m-%d %H:%M:%S")
            end_str = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
            
            # 使用时间切片获取键
            time_slice_keys = list(self._db[start_str:end_str])
            
            # 过滤策略ID
            strategy_keys = [key for key in time_slice_keys if key.startswith(f"{strategy_id}:")]
            
            # 如果时间切片内的数据不足，再使用原有逻辑
            if len(strategy_keys) < limit:
                # 只获取以strategy_id开头的键，避免遍历所有数据库项
                # 限制遍历数量，最多遍历limit * 2个键
                temp_keys = []
                count = 0
                max_scan = limit * 2
                for key in self._db.keys():
                    if key.startswith(f"{strategy_id}:"):
                        temp_keys.append(key)
                        count += 1
                        if count >= max_scan:
                            break
                strategy_keys = temp_keys
            
            for key in strategy_keys:
                data = self._db.get(key)
                if isinstance(data, dict):
                    # 过滤无效数据：时间戳必须有效，ID必须存在
                    ts = data.get("ts", 0)
                    result_id = data.get("id", "")
                    if ts > 1000000000 and result_id:  # 时间戳必须大于2001年
                        result = StrategyResult(
                            id=result_id,
                            strategy_id=data.get("strategy_id", ""),
                            strategy_name=data.get("strategy_name", ""),
                            ts=ts,
                            success=data.get("success", False),
                            input_preview=data.get("input_preview", ""),
                            output_preview=data.get("output_preview", ""),
                            output_full=data.get("output_full"),
                            process_time_ms=data.get("process_time_ms", 0),
                            error=data.get("error", ""),
                            metadata=data.get("metadata", {}),
                        )
                        db_results.append(result)
            
            db_results.sort(key=lambda x: x.ts, reverse=True)
            db_results = db_results[:limit]
            
            if db_results:
                if strategy_id not in self._cache:
                    self._cache[strategy_id] = deque(maxlen=self._max_cache_size)
                for result in reversed(db_results):
                    self._cache[strategy_id].appendleft(result)
                
                # 更新缓存统计
                if strategy_id not in self._cache_stats:
                    self._cache_stats[strategy_id] = {
                        'access_count': 1,
                        'last_access': current_time,
                        'last_write': current_time
                    }
                else:
                    self._cache_stats[strategy_id]['access_count'] += 1
                    self._cache_stats[strategy_id]['last_access'] = current_time
            
            return db_results
    
    def get_by_id(self, result_id: str) -> Optional[StrategyResult]:
        with self._data_lock:
            # 使用反向索引快速查找
            index_key = f"id:{result_id}"
            key = self._index_db.get(index_key)
            
            if key:
                data = self._db.get(key)
                if isinstance(data, dict) and data.get("id") == result_id:
                    return StrategyResult(
                        id=data.get("id", ""),
                        strategy_id=data.get("strategy_id", ""),
                        strategy_name=data.get("strategy_name", ""),
                        ts=data.get("ts", 0),
                        success=data.get("success", False),
                        input_preview=data.get("input_preview", ""),
                        output_preview=data.get("output_preview", ""),
                        output_full=data.get("output_full"),
                        process_time_ms=data.get("process_time_ms", 0),
                        error=data.get("error", ""),
                        metadata=data.get("metadata", {}),
                    )
            
            #  fallback: 如果索引不存在，使用原有逻辑
            for key in self._db.keys():
                if result_id in key:
                    data = self._db.get(key)
                    if isinstance(data, dict) and data.get("id") == result_id:
                        # 同时更新索引
                        self._index_db[index_key] = key
                        return StrategyResult(
                            id=data.get("id", ""),
                            strategy_id=data.get("strategy_id", ""),
                            strategy_name=data.get("strategy_name", ""),
                            ts=data.get("ts", 0),
                            success=data.get("success", False),
                            input_preview=data.get("input_preview", ""),
                            output_preview=data.get("output_preview", ""),
                            output_full=data.get("output_full"),
                            process_time_ms=data.get("process_time_ms", 0),
                            error=data.get("error", ""),
                            metadata=data.get("metadata", {}),
                        )
        return None
    
    def delete(self, result_id: str) -> bool:
        """删除指定结果"""
        with self._data_lock:
            # 使用反向索引快速查找
            index_key = f"id:{result_id}"
            key = self._index_db.get(index_key)
            
            if key:
                data = self._db.get(key)
                if isinstance(data, dict) and data.get("id") == result_id:
                    strategy_id = data.get("strategy_id", "")
                    del self._db[key]
                    # 删除对应的索引
                    del self._index_db[index_key]
                    
                    # 清除该策略的缓存，下次查询时会重新从数据库加载
                    if strategy_id in self._cache:
                        del self._cache[strategy_id]
                    
                    # 更新统计
                    if data.get("success"):
                        self._stats["total_success"] = max(0, self._stats["total_success"] - 1)
                    else:
                        self._stats["total_failed"] = max(0, self._stats["total_failed"] - 1)
                    self._stats["total_results"] = max(0, self._stats["total_results"] - 1)
                    
                    # 使统计缓存失效
                    self._invalidate_stats_cache()
                    
                    return True
            
            #  fallback: 如果索引不存在，使用原有逻辑
            for key in list(self._db.keys()):
                if result_id in key:
                    data = self._db.get(key)
                    if isinstance(data, dict) and data.get("id") == result_id:
                        strategy_id = data.get("strategy_id", "")
                        del self._db[key]
                        # 删除对应的索引
                        try:
                            if index_key in self._index_db:
                                del self._index_db[index_key]
                        except Exception:
                            pass
                        
                        # 清除该策略的缓存，下次查询时会重新从数据库加载
                        if strategy_id in self._cache:
                            del self._cache[strategy_id]
                        
                        # 更新统计
                        if data.get("success"):
                            self._stats["total_success"] = max(0, self._stats["total_success"] - 1)
                        else:
                            self._stats["total_failed"] = max(0, self._stats["total_failed"] - 1)
                        self._stats["total_results"] = max(0, self._stats["total_results"] - 1)
                        
                        # 使统计缓存失效
                        self._invalidate_stats_cache()
                        
                        return True
        return False
    
    def query(
        self,
        strategy_id: str = None,
        start_ts: float = None,
        end_ts: float = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[StrategyResult]:
        results = []
        
        with self._data_lock:
            # 利用DBStream的时间切片功能
            if start_ts or end_ts:
                # 转换为时间字符串格式
                start_str = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S") if start_ts else None
                end_str = datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S") if end_ts else None
                
                # 使用时间切片获取键
                time_slice_keys = list(self._db[start_str:end_str])
                
                # 过滤策略ID
                if strategy_id:
                    keys = [key for key in time_slice_keys if key.startswith(f"{strategy_id}:")]
                else:
                    keys = time_slice_keys
            else:
                # 未指定时间范围，使用时间切片获取最近数据
                current_time = time.time()
                # 计算30天前的时间戳
                thirty_days_ago = current_time - (30 * 24 * 3600)
                start_str = datetime.fromtimestamp(thirty_days_ago).strftime("%Y-%m-%d %H:%M:%S")
                end_str = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
                
                # 使用时间切片获取键
                time_slice_keys = list(self._db[start_str:end_str])
                
                # 过滤策略ID
                if strategy_id:
                    keys = [key for key in time_slice_keys if key.startswith(f"{strategy_id}:")]
                else:
                    keys = time_slice_keys
                
                # 如果时间切片内的数据不足，再使用原有逻辑
                if len(keys) < limit:
                    if strategy_id:
                        # 只获取以strategy_id开头的键，避免遍历所有数据库项
                        # 限制遍历数量，最多遍历limit * 2个键
                        temp_keys = []
                        count = 0
                        max_scan = limit * 2
                        for key in self._db.keys():
                            if key.startswith(f"{strategy_id}:"):
                                temp_keys.append(key)
                                count += 1
                                if count >= max_scan:
                                    break
                        keys = temp_keys
                    else:
                        # 对于未指定策略ID的情况，仍然使用时间切片结果
                        # 因为全表扫描可能会导致性能问题
                        pass
            
            for key in keys:
                data = self._db.get(key)
                if not isinstance(data, dict):
                    continue
                
                if strategy_id and data.get("strategy_id") != strategy_id:
                    continue
                
                ts = data.get("ts", 0)
                if start_ts and ts < start_ts:
                    continue
                if end_ts and ts > end_ts:
                    continue
                
                if success_only and not data.get("success", False):
                    continue
                
                result = StrategyResult(
                    id=data.get("id", ""),
                    strategy_id=data.get("strategy_id", ""),
                    strategy_name=data.get("strategy_name", ""),
                    ts=ts,
                    success=data.get("success", False),
                    input_preview=data.get("input_preview", ""),
                    output_preview=data.get("output_preview", ""),
                    output_full=data.get("output_full"),
                    process_time_ms=data.get("process_time_ms", 0),
                    error=data.get("error", ""),
                    metadata=data.get("metadata", {}),
                )
                results.append(result)
        
        results.sort(key=lambda x: x.ts, reverse=True)
        return results[:limit]
    
    def get_stats(self, strategy_id: str = None) -> dict:
        import time
        t0 = time.time()
        
        # 使用缓存的统计数据
        stats = self._get_cached_stats()
        
        t1 = time.time()
        
        if strategy_id:
            results = self.get_recent(strategy_id, limit=1000)
            if results:
                success_count = sum(1 for r in results if r.success)
                total_time = sum(r.process_time_ms for r in results)
                stats.update({
                    "results_count": len(results),
                    "success_count": success_count,
                    "failed_count": len(results) - success_count,
                    "avg_process_time_ms": total_time / len(results) if results else 0,
                    "success_rate": success_count / len(results) if results else 0,
                })
        
        t2 = time.time()
        if stats.get("total_results", 0) > 0:
            stats["avg_process_time_ms"] = stats["total_process_time_ms"] / stats["total_results"]
            stats["success_rate"] = stats["total_success"] / stats["total_results"]
        
        return stats
    
    def get_trend_data(
        self,
        strategy_id: str,
        interval_minutes: int = 5,
        limit: int = 100,
    ) -> dict:
        results = self.get_recent(strategy_id, limit=limit)
        
        if not results:
            return {
                "timestamps": [],
                "success_counts": [],
                "failed_counts": [],
                "avg_process_times": [],
                "process_counts": [],
            }
        
        interval_seconds = interval_minutes * 60
        
        buckets = {}
        for r in results:
            bucket_ts = int(r.ts // interval_seconds) * interval_seconds
            if bucket_ts not in buckets:
                buckets[bucket_ts] = {"success": 0, "failed": 0, "total_time": 0, "count": 0}
            
            if r.success:
                buckets[bucket_ts]["success"] += 1
            else:
                buckets[bucket_ts]["failed"] += 1
            buckets[bucket_ts]["total_time"] += r.process_time_ms
            buckets[bucket_ts]["count"] += 1
        
        sorted_buckets = sorted(buckets.items(), key=lambda x: x[0], reverse=True)[:limit]
        
        return {
            "timestamps": [datetime.fromtimestamp(ts).strftime("%H:%M") for ts, _ in sorted_buckets],
            "success_counts": [b["success"] for _, b in sorted_buckets],
            "failed_counts": [b["failed"] for _, b in sorted_buckets],
            "avg_process_times": [b["total_time"] / b["count"] if b["count"] > 0 else 0 for _, b in sorted_buckets],
            "process_counts": [b["count"] for _, b in sorted_buckets],
        }
    
    def cleanup(self, strategy_id: str, max_count: int):
        """清理超过限制的历史记录"""
        with self._data_lock:
            # 利用时间切片获取最近的数据，避免全表扫描
            import time
            current_time = time.time()
            # 计算30天前的时间戳（足够覆盖大部分数据）
            thirty_days_ago = current_time - (30 * 24 * 3600)
            start_str = datetime.fromtimestamp(thirty_days_ago).strftime("%Y-%m-%d %H:%M:%S")
            end_str = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
            
            # 使用时间切片获取键
            time_slice_keys = list(self._db[start_str:end_str])
            
            # 过滤策略ID
            keys = [key for key in time_slice_keys if key.startswith(f"{strategy_id}:")]
            
            # 如果时间切片内的数据不足，再使用原有逻辑
            if len(keys) < max_count:
                # 只获取以strategy_id开头的键，避免遍历所有数据库项
                keys = [key for key in self._db.keys() if key.startswith(f"{strategy_id}:")]
            
            if len(keys) > max_count:
                results = []
                for key in keys:
                    data = self._db.get(key)
                    if isinstance(data, dict):
                        results.append((key, data.get("ts", 0)))
                
                results.sort(key=lambda x: x[1], reverse=True)
                
                keys_to_delete = [key for key, _ in results[max_count:]]
                
                # 收集要删除的索引
                index_keys_to_delete = []
                for key in keys_to_delete:
                    data = self._db.get(key)
                    if isinstance(data, dict):
                        result_id = data.get("id")
                        if result_id:
                            index_keys_to_delete.append(f"id:{result_id}")
                
                # 执行批量删除数据
                for key in keys_to_delete:
                    try:
                        if key in self._db:
                            del self._db[key]
                    except KeyError:
                        pass
                
                # 执行批量删除索引
                for index_key in index_keys_to_delete:
                    try:
                        if index_key in self._index_db:
                            del self._index_db[index_key]
                    except KeyError:
                        pass
                
                if strategy_id in self._cache:
                    cache_results = list(self._cache[strategy_id])
                    if len(cache_results) > max_count:
                        self._cache[strategy_id] = deque(cache_results[:max_count], maxlen=self._max_cache_size)
    
    def cleanup_total(self, max_count: int):
        """清理总历史记录数（所有策略合计）"""
        from ..config import get_strategy_config
        
        with self._data_lock:
            # 利用时间切片获取最近的数据，避免全表扫描
            import time
            current_time = time.time()
            # 计算60天前的时间戳（足够覆盖大部分数据）
            sixty_days_ago = current_time - (60 * 24 * 3600)
            start_str = datetime.fromtimestamp(sixty_days_ago).strftime("%Y-%m-%d %H:%M:%S")
            end_str = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
            
            # 使用时间切片获取键
            time_slice_keys = list(self._db[start_str:end_str])
            
            # 如果时间切片内的数据不足，再使用原有逻辑
            if len(time_slice_keys) < max_count:
                # 只获取最近的数据，避免全表扫描
                # 这里使用限制遍历的方式，最多遍历2倍max_count的数据
                all_keys = []
                count = 0
                max_scan = max_count * 2
                for key in self._db.keys():
                    all_keys.append(key)
                    count += 1
                    if count >= max_scan:
                        break
            else:
                all_keys = time_slice_keys
            
            if len(all_keys) > max_count:
                results = []
                for key in all_keys:
                    data = self._db.get(key)
                    if isinstance(data, dict):
                        results.append((key, data.get("ts", 0)))
                
                results.sort(key=lambda x: x[1], reverse=True)
                
                keys_to_delete = [key for key, _ in results[max_count:]]
                
                # 收集要删除的索引
                index_keys_to_delete = []
                for key in keys_to_delete:
                    data = self._db.get(key)
                    if isinstance(data, dict):
                        result_id = data.get("id")
                        if result_id:
                            index_keys_to_delete.append(f"id:{result_id}")
                
                # 执行批量删除数据
                for key in keys_to_delete:
                    try:
                        if key in self._db:
                            del self._db[key]
                    except KeyError:
                        pass
                
                # 执行批量删除索引
                for index_key in index_keys_to_delete:
                    try:
                        if index_key in self._index_db:
                            del self._index_db[index_key]
                    except KeyError:
                        pass
                
                for sid in list(self._cache.keys()):
                    cache_results = list(self._cache[sid])
                    cache_items = [(k, r) for k, r in zip([f"{sid}:{r.id}" for r in cache_results], cache_results) if k not in keys_to_delete]
                    if cache_items:
                        self._cache[sid] = deque([r for _, r in cache_items], maxlen=self._max_cache_size)
                    else:
                        self._cache[sid] = deque(maxlen=self._max_cache_size)
    
    def clear_cache(self, strategy_id: str = None):
        with self._data_lock:
            if strategy_id:
                self._cache.pop(strategy_id, None)
            else:
                self._cache.clear()
    
    def clear_db(self, strategy_id: str = None):
        with self._data_lock:
            if strategy_id:
                keys_to_delete = [
                    k for k in self._db.keys()
                    if k.startswith(f"{strategy_id}:")
                ]
                
                # 收集要删除的索引
                index_keys_to_delete = []
                for key in keys_to_delete:
                    data = self._db.get(key)
                    if isinstance(data, dict):
                        result_id = data.get("id")
                        if result_id:
                            index_keys_to_delete.append(f"id:{result_id}")
                
                # 执行批量删除数据
                for key in keys_to_delete:
                    del self._db[key]
                
                # 执行批量删除索引
                for index_key in index_keys_to_delete:
                    if index_key in self._index_db:
                        del self._index_db[index_key]
            else:
                self._db.clear()
                self._index_db.clear()


store = ResultStore()


def get_result_store() -> ResultStore:
    return store
