"""
SystemStateManager - 系统状态持久化管理

负责：
1. 记录系统上次活跃时间（last_active_time）
2. 记录系统休眠/退出时间（last_sleep_time）
3. 记录系统唤醒时间（last_wake_time）
4. 记录任务执行历史

存储位置：deva/naja/system_state/state.json
"""

import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

log = logging.getLogger(__name__)


class SystemStateManager:
    """
    系统状态管理器

    管理系统的持久化状态，用于：
    1. 判断系统休眠时长
    2. 检测需要补执行的任务
    3. 记录任务执行历史
    """

    STATE_DIR = Path(__file__).parent
    STATE_FILE = STATE_DIR / "state.json"

    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._ensure_dir()
        self._load()

    def _ensure_dir(self):
        """确保目录存在"""
        self.STATE_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """加载状态"""
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    self._state = json.load(f)
                log.info(f"[SystemState] 已加载状态，上次活跃: {self.get_last_active_time()}")
            except Exception as e:
                log.warning(f"[SystemState] 加载状态失败: {e}")
                self._state = self._default_state()
        else:
            self._state = self._default_state()
            self._save()

    def _default_state(self) -> Dict[str, Any]:
        """默认状态"""
        return {
            "version": "1.0",
            "last_active_time": None,
            "last_sleep_time": None,
            "last_wake_time": None,
            "system_uptime_start": datetime.now().isoformat(),
            "task_execution_records": {},
            "created_at": datetime.now().isoformat(),
        }

    def _save(self):
        """保存状态"""
        self._state["updated_at"] = datetime.now().isoformat()
        try:
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"[SystemState] 保存状态失败: {e}")

    def get_last_active_time(self) -> Optional[datetime]:
        """获取上次活跃时间"""
        if self._state.get("last_active_time"):
            return datetime.fromisoformat(self._state["last_active_time"])
        return None

    def get_last_sleep_time(self) -> Optional[datetime]:
        """获取上次休眠时间"""
        if self._state.get("last_sleep_time"):
            return datetime.fromisoformat(self._state["last_sleep_time"])
        return None

    def get_last_wake_time(self) -> Optional[datetime]:
        """获取上次唤醒时间"""
        if self._state.get("last_wake_time"):
            return datetime.fromisoformat(self._state["last_wake_time"])
        return None

    def get_sleep_duration_seconds(self) -> float:
        """
        获取休眠时长（秒）

        Returns:
            休眠时长，如果无法计算则返回 0
        """
        last_active = self.get_last_active_time()
        if not last_active:
            return 0

        now = datetime.now()
        duration = (now - last_active).total_seconds()

        return max(0, duration)

    def record_sleep(self):
        """
        记录系统休眠/退出

        调用时机：系统即将休眠或退出时
        注意：程序没退出时不会自动调用，使用心跳机制判断休眠
        """
        now = datetime.now()
        self._state["last_sleep_time"] = now.isoformat()
        self._state["last_active_time"] = now.isoformat()
        self._save()
        log.info(f"[SystemState] 已记录休眠时间: {now}")

    def record_wake(self):
        """
        记录系统唤醒

        调用时机：系统启动时
        """
        now = datetime.now()
        self._state["last_wake_time"] = now.isoformat()
        self._state["last_active_time"] = now.isoformat()
        self._save()
        log.info(f"[SystemState] 已记录唤醒时间: {now}")

    def record_active(self):
        """
        记录系统活跃

        调用时机：系统完成某个重要操作后，或心跳定时任务
        """
        now = datetime.now()
        self._state["last_active_time"] = now.isoformat()
        self._save()

    def record_task_execution(self, task_name: str, execution_time: datetime, result: str = "success"):
        """
        记录任务执行

        Args:
            task_name: 任务名称
            execution_time: 执行时间
            result: 执行结果
        """
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

        self._save()

    def was_task_executed_today(self, task_name: str) -> bool:
        """
        检查任务今天是否已执行

        Args:
            task_name: 任务名称

        Returns:
            True if 任务今天已执行
        """
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
        records = self._state.get("task_execution_records", {}).get(task_name, [])
        if not records:
            return None

        last_record = records[-1]
        return datetime.fromisoformat(last_record["execution_time"])

    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        sleep_duration = self.get_sleep_duration_seconds()
        last_active = self.get_last_active_time()

        return {
            "last_active_time": self._state.get("last_active_time"),
            "last_sleep_time": self._state.get("last_sleep_time"),
            "last_wake_time": self._state.get("last_wake_time"),
            "sleep_duration_hours": round(sleep_duration / 3600, 2),
            "sleep_duration_seconds": round(sleep_duration, 1),
            "needs_wake_sync": sleep_duration > 3600,
            "task_count": len(self._state.get("task_execution_records", {})),
        }


