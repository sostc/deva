"""
SystemStateManager - 系统状态持久化管理

负责：
1. 记录系统上次活跃时间（last_active_time）
2. 记录系统唤醒时间（last_wake_time）
3. 记录任务执行历史

存储位置：deva/naja/system_state/state.json

设计要点：
- 使用线程锁保护状态更新，避免并发写入冲突
- 心跳更新(record_active)仅更新内存，批量写入减少 I/O
- 关键操作(record_wake)强制立即写入
"""

import json
import time
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

log = logging.getLogger(__name__)

BATCH_WRITE_INTERVAL = 60.0


class SystemStateManager:
    """
    系统状态管理器

    管理系统的持久化状态，用于：
    1. 判断系统休眠时长
    2. 检测需要补执行的任务
    3. 记录任务执行历史

    线程安全设计：
    - 所有状态更新通过线程锁保护
    - record_active() 批量写入，避免频繁 I/O
    - 关键操作立即写入
    """

    STATE_DIR = Path(__file__).parent
    STATE_FILE = STATE_DIR / "state.json"

    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._dirty = False
        self._last_save_time = 0.0
        self._save_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ensure_dir()
        self._load()
        self._start_batch_writer()

    def _start_batch_writer(self):
        """启动批量写入线程"""
        self._save_thread = threading.Thread(
            target=self._batch_write_loop,
            daemon=True,
            name="SystemStateBatchWriter"
        )
        self._save_thread.start()

    def _batch_write_loop(self):
        """批量写入循环"""
        while not self._stop_event.is_set():
            self._stop_event.wait(BATCH_WRITE_INTERVAL)
            if self._stop_event.is_set():
                break
            self._flush_if_dirty()

    def _flush_if_dirty(self):
        """如果有未保存的更改，则写入"""
        with self._lock:
            if self._dirty and time.time() - self._last_save_time >= BATCH_WRITE_INTERVAL:
                self._save()
                self._dirty = False

    def _ensure_dir(self):
        """确保目录存在"""
        self.STATE_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """加载状态"""
        valid_keys = set(self._default_state().keys())
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # 只保留当前版本识别的字段，过滤掉历史遗留字段
                self._state = {k: loaded[k] for k in valid_keys if k in loaded}
                # 补全缺失字段（向前兼容）
                defaults = self._default_state()
                for k in valid_keys:
                    if k not in self._state:
                        self._state[k] = defaults[k]
                log.info(f"[SystemState] 已加载状态，上次活跃: {self.get_last_active_time()}")
            except Exception as e:
                log.warning(f"[SystemState] 加载状态失败: {e}")
                self._state = self._default_state()
        else:
            self._state = self._default_state()
        self._save_unsafe()

    def _default_state(self) -> Dict[str, Any]:
        """默认状态"""
        return {
            "version": "1.0",
            "last_active_time": None,
            "last_wake_time": None,
            "system_uptime_start": datetime.now().isoformat(),
            "task_execution_records": {},
            "created_at": datetime.now().isoformat(),
        }

    def _save_unsafe(self):
        """保存状态（必须在持有锁时调用）"""
        self._state["updated_at"] = datetime.now().isoformat()
        try:
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            self._last_save_time = time.time()
        except Exception as e:
            log.error(f"[SystemState] 保存状态失败: {e}")

    def _save(self, force: bool = False):
        """保存状态

        Args:
            force: 是否强制立即写入
        """
        with self._lock:
            self._save_unsafe()
            self._dirty = False

    def _mark_dirty(self):
        """标记为脏，等待批量写入"""
        with self._lock:
            self._dirty = True

    def get_last_active_time(self) -> Optional[datetime]:
        """获取上次活跃时间"""
        with self._lock:
            if self._state.get("last_active_time"):
                return datetime.fromisoformat(self._state["last_active_time"])
            return None

    def get_last_wake_time(self) -> Optional[datetime]:
        """获取上次唤醒时间"""
        with self._lock:
            if self._state.get("last_wake_time"):
                return datetime.fromisoformat(self._state["last_wake_time"])
            return None

    def get_sleep_duration_seconds(self) -> float:
        """
        获取休眠时长（秒）

        Returns:
            休眠时长，如果无法计算则返回 0
        """
        with self._lock:
            last_active = self._state.get("last_active_time")
            if not last_active:
                return 0
            last_active_dt = datetime.fromisoformat(last_active)
            now = datetime.now()
            duration = (now - last_active_dt).total_seconds()
            return max(0, duration)

    def record_wake(self):
        """
        记录系统唤醒

        调用时机：系统启动时
        注意：只更新 last_wake_time，不修改 last_active_time
            last_active_time 由心跳 record_active() 维护，保证休眠时长计算始终由真实活跃时间决定
        """
        with self._lock:
            now = datetime.now()
            self._state["last_wake_time"] = now.isoformat()
            self._save(force=True)
        log.info(f"[SystemState] 已记录唤醒时间: {now}")

    def record_active(self):
        """
        记录系统活跃

        调用时机：系统完成某个重要操作后，或心跳定时任务
        优化：仅更新内存，由后台线程批量写入
        """
        with self._lock:
            self._state["last_active_time"] = datetime.now().isoformat()
            self._dirty = True
            if time.time() - self._last_save_time >= BATCH_WRITE_INTERVAL:
                self._save_unsafe()
                self._dirty = False

    def record_task_execution(self, task_name: str, execution_time: datetime, result: str = "success"):
        """
        记录任务执行

        Args:
            task_name: 任务名称
            execution_time: 执行时间
            result: 执行结果
        """
        with self._lock:
            if "task_execution_records" not in self._state:
                self._state["task_execution_records"] = {}

            if task_name not in self._state["task_execution_records"]:
                self._state["task_execution_records"][task_name] = []

            self._state["task_execution_records"][task_name].append({
                "execution_time": execution_time.isoformat(),
                "result": result,
                "recorded_at": datetime.now().isoformat()
            })

            recent_records = self._state["task_execution_records"][task_name][-100:]
            self._state["task_execution_records"][task_name] = recent_records

            self._dirty = True
            self._save_unsafe()
            self._dirty = False

    def was_task_executed_today(self, task_name: str) -> bool:
        """
        检查任务今天是否已执行

        Args:
            task_name: 任务名称

        Returns:
            True if 任务今天已执行
        """
        with self._lock:
            today = datetime.now().date()
            records = self._state.get("task_execution_records", {}).get(task_name, [])
            for record in records:
                exec_time = datetime.fromisoformat(record["execution_time"])
                if exec_time.date() == today:
                    return True
            return False

    def get_task_last_execution(self, task_name: str) -> Optional[datetime]:
        """
        获取任务上次执行时间

        Args:
            task_name: 任务名称

        Returns:
            上次执行时间，如果没有记录返回 None
        """
        with self._lock:
            records = self._state.get("task_execution_records", {}).get(task_name, [])
            if not records:
                return None
            last_record = records[-1]
            return datetime.fromisoformat(last_record["execution_time"])

    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        with self._lock:
            last_active = self._state.get("last_active_time")
            if last_active:
                last_active_dt = datetime.fromisoformat(last_active)
                sleep_duration = (datetime.now() - last_active_dt).total_seconds()
            else:
                sleep_duration = 0.0
            return {
                "last_active_time": last_active,
                "last_wake_time": self._state.get("last_wake_time"),
                "sleep_duration_hours": round(sleep_duration / 3600, 2),
                "sleep_duration_seconds": round(max(0, sleep_duration), 1),
                "needs_wake_sync": sleep_duration > 3600,
                "task_count": len(self._state.get("task_execution_records", {})),
            }

    def shutdown(self):
        """优雅关闭，停止批量写入线程并保存最后状态"""
        self._stop_event.set()
        if self._save_thread and self._save_thread.is_alive():
            self._save_thread.join(timeout=2.0)
        with self._lock:
            if self._dirty:
                self._save_unsafe()


