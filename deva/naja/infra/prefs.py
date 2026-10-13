"""Naja 用户偏好持久化（``~/.naja/prefs.json``）。

只承载「托盘进程 与 服务进程 都要看、且跨重启必须记住」的少量开关。

设计约束：
- **读失败绝不致命**：偏好文件损坏/不存在时一律回退默认值——偏好坏掉不该拖垮服务。
- **写盘原子**：临时文件 + ``os.replace``，避免半截 JSON 让下次启动读到坏值。
- 默认值 = **历史行为**：从没写过偏好文件的用户，看到的就是改造前的样子。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

NAJA_DIR = Path.home() / ".naja"
PREFS_FILE = NAJA_DIR / "prefs.json"

# 键 → 默认值。新增键时把「改之前的行为」写在这里。
DEFAULTS: dict = {
    # Naja 服务启动时是否自动打开系统浏览器
    "open_browser_on_start": True,
}


def _resolve(path: Optional[Path]) -> Path:
    return Path(path) if path is not None else PREFS_FILE


def load_prefs(path: Optional[Path] = None) -> dict:
    """读取全部偏好（默认值打底，文件内容覆盖）。"""
    data = dict(DEFAULTS)
    p = _resolve(path)
    try:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
            else:
                logger.warning("偏好文件不是 JSON 对象，忽略: %s", p)
    except Exception as e:  # noqa: BLE001 - 读取偏好不该让调用方崩
        logger.warning("读取偏好失败，使用默认值: %s", e)
    return data


def get_pref(key: str, default: Any = None, path: Optional[Path] = None) -> Any:
    """读取单个偏好；缺失时回退 ``DEFAULTS``，再回退 ``default``。"""
    data = load_prefs(path)
    if key in data:
        return data[key]
    return DEFAULTS.get(key, default)


def set_pref(key: str, value: Any, path: Optional[Path] = None) -> bool:
    """写入单个偏好（保留其它键）。返回是否写盘成功。"""
    p = _resolve(path)
    tmp = p.with_name(f".{p.name}.tmp.{os.getpid()}")
    try:
        data = load_prefs(p)
        data[key] = value
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(tmp, p)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("写入偏好失败: %s", e)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return False
