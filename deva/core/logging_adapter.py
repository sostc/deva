"""deva.* 日志适配层：统一 record 归一化、行格式与默认 handler。

从 core.py 拆出（P2 #11）。
"""
from __future__ import absolute_import, division, print_function
from typing import Any, Dict
import datetime as _dt
import os

import logging

try:
    from tornado import gen
except ImportError:
    gen = None
try:
    from tornado.ioloop import PollIOLoop
except ImportError:
    PollIOLoop = None  # dropped in tornado 6.0


__all__ = [
    'LEVEL_ORDER', 'should_emit_level', 'normalize_record', 'format_line',
    'DevaFormatter', 'setup_deva_logging',
]

logger = logging.getLogger(__name__)


LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_HANDLER_MARK = "_deva_adapter_handler"


def should_emit_level(level_name: str) -> bool:
    current = (os.getenv("DEVA_LOG_LEVEL", "INFO") or "INFO").upper()
    min_v = LEVEL_ORDER.get(current, LEVEL_ORDER["INFO"])
    now_v = LEVEL_ORDER.get(str(level_name).upper(), LEVEL_ORDER["INFO"])
    return now_v >= min_v


def normalize_record(x: Any, *, default_level="INFO", default_source="deva") -> Dict[str, Any]:
    now = _dt.datetime.now().isoformat(sep=" ", timespec="seconds")
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
        return {"ts": now, "level": "ERROR", "source": default_source, "message": f"{type(x).__name__}: {x}", "extra": {}}
    return {"ts": now, "level": str(default_level).upper(), "source": default_source, "message": str(x), "extra": {}}


def format_line(record: Dict[str, Any]) -> str:
    import json as _json
    extra = record.get("extra") or {}
    extra_text = ""
    if extra:
        try:
            extra_text = " | " + _json.dumps(extra, ensure_ascii=False,
                                             default=str, separators=(",", ":"))
        except Exception:
            extra_text = " | " + str(extra)
    return f"[{record['ts']}][{record['level']}][{record['source']}] {record['message']}{extra_text}"


class DevaFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        source = getattr(record, "deva_source", None) or record.name
        extra = getattr(record, "deva_extra", {}) or {}
        payload = {
            "ts": _dt.datetime.fromtimestamp(record.created).isoformat(sep=" ", timespec="seconds"),
            "level": record.levelname,
            "source": source,
            "message": record.getMessage(),
            "extra": extra,
        }
        line = format_line(payload)
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


_HANDLER_MARK = "__deva_handler_installed__"


def setup_deva_logging() -> logging.Logger:
    """Install a default handler for deva.* loggers once."""
    use_colorful = os.environ.get('NAJA_COLORFUL_LOG', '').lower() == 'true'

    if use_colorful:
        try:
            from deva.naja.infra.log.colorful_logger import setup_colorful_logger as _setup_colorful
            _setup_colorful(level=logging.INFO, force_color=True)
            return logging.getLogger("deva")
        except ImportError:
            pass

    def _install_for(name: str):
        logger_ = logging.getLogger(name)
        if not any(getattr(h, _HANDLER_MARK, False) for h in logger_.handlers):
            handler_ = logging.StreamHandler()
            setattr(handler_, _HANDLER_MARK, True)
            handler_.setFormatter(DevaFormatter())
            logger_.addHandler(handler_)
        logger_.propagate = False
        return logger_
    logger_ = _install_for("deva")
    _install_for("sqlitedict")
    _install_for("simhash")
    level_name = (os.getenv("DEVA_LOG_LEVEL", "INFO") or "INFO").upper()
    logger_.setLevel(getattr(logging, level_name, logging.INFO))
    logging.getLogger("sqlitedict").setLevel(getattr(logging, level_name, logging.INFO))
    logging.getLogger("simhash").setLevel(getattr(logging, level_name, logging.INFO))
    return logger_
