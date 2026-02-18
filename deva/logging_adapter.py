"""Unified logging adapter for deva.

This module keeps standard ``logging`` usage while enforcing the same
human-readable output format as deva ``log/warn/debug`` streams.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any, Dict


LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}

_HANDLER_MARK = "_deva_adapter_handler"


def should_emit_level(level_name: str) -> bool:
    current = (os.getenv("DEVA_LOG_LEVEL", "INFO") or "INFO").upper()
    min_v = LEVEL_ORDER.get(current, LEVEL_ORDER["INFO"])
    now_v = LEVEL_ORDER.get(str(level_name).upper(), LEVEL_ORDER["INFO"])
    return now_v >= min_v


def normalize_record(x: Any, *, default_level="INFO", default_source="deva") -> Dict[str, Any]:
    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    if isinstance(x, dict):
        level = str(x.get("level", default_level)).upper()
        source = str(x.get("source", default_source))
        return {
            "ts": x.get("ts") or now,
            "level": level,
            "source": source,
            "message": str(x.get("message", x)),
            "extra": {k: v for k, v in x.items() if k not in {"ts", "level", "source", "message"}},
        }
    if isinstance(x, Exception):
        return {
            "ts": now,
            "level": "ERROR",
            "source": default_source,
            "message": f"{type(x).__name__}: {x}",
            "extra": {},
        }
    return {
        "ts": now,
        "level": str(default_level).upper(),
        "source": default_source,
        "message": str(x),
        "extra": {},
    }


def format_line(record: Dict[str, Any]) -> str:
    extra = record.get("extra") or {}
    extra_text = ""
    if extra:
        try:
            extra_text = " | " + json.dumps(extra, ensure_ascii=False, default=str, separators=(",", ":"))
        except Exception:
            extra_text = " | " + str(extra)
    return f"[{record['ts']}][{record['level']}][{record['source']}] {record['message']}{extra_text}"


class DevaFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        source = getattr(record, "deva_source", None) or record.name
        extra = getattr(record, "deva_extra", {}) or {}
        payload = {
            "ts": datetime.datetime.fromtimestamp(record.created).isoformat(sep=" ", timespec="seconds"),
            "level": record.levelname,
            "source": source,
            "message": record.getMessage(),
            "extra": extra,
        }
        line = format_line(payload)
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def setup_deva_logging() -> logging.Logger:
    """Install a default handler for `deva.*` loggers once."""
    def _install_for(name: str):
        logger = logging.getLogger(name)
        if not any(getattr(h, _HANDLER_MARK, False) for h in logger.handlers):
            handler = logging.StreamHandler()
            setattr(handler, _HANDLER_MARK, True)
            handler.setFormatter(DevaFormatter())
            logger.addHandler(handler)
        logger.propagate = False
        return logger

    logger = _install_for("deva")
    # vendored utilities that still log under their historical names.
    _install_for("sqlitedict")
    _install_for("simhash")

    level_name = (os.getenv("DEVA_LOG_LEVEL", "INFO") or "INFO").upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logging.getLogger("sqlitedict").setLevel(getattr(logging, level_name, logging.INFO))
    logging.getLogger("simhash").setLevel(getattr(logging, level_name, logging.INFO))
    return logger
