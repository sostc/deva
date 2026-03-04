"""数据表管理模块"""

from __future__ import annotations

import math
import re
import time
import threading
from io import BytesIO, StringIO
from typing import Any, Callable, Dict, List, Optional, Tuple

from deva import NB


TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}$")
DEFAULT_RESERVED_TABLES = {"default", "naja_strategies", "naja_datasources", "naja_dictionaries", "naja_tasks"}
DEFAULT_ALLOWED_EXTS = {".csv", ".xls", ".xlsx"}
DEFAULT_ALLOWED_MIME = {
    "text/csv",
    "application/csv",
    "application/octet-stream",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def validate_table_name(
    name: str,
    *,
    existing_tables: set = None,
    reserved_tables: set = None,
) -> Tuple[bool, str]:
    """验证表名"""
    raw = (name or "").strip()
    if not raw:
        return False, "表名不能为空"
    if not TABLE_NAME_RE.match(raw):
        return False, "表名仅支持字母/数字/_/-，且不能以符号开头，长度<=64"

    reserved = DEFAULT_RESERVED_TABLES if reserved_tables is None else set(reserved_tables)
    if raw in reserved:
        return False, f"表名 `{raw}` 为系统保留名称"

    if existing_tables is not None and raw in set(existing_tables):
        return False, "表已存在"
    return True, raw


def validate_key_name(key: str, *, max_len: int = 128) -> Tuple[bool, str]:
    """验证键名"""
    text = str(key or "").strip()
    if not text:
        return False, "键名不能为空"
    if len(text) > max_len:
        return False, f"键名长度不能超过{max_len}"
    return True, text


def compute_total_pages(total_rows: int, page_size: int) -> int:
    """计算总页数"""
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if total_rows <= 0:
        return 1
    return max(1, math.ceil(total_rows / page_size))


def filter_dataframe(df, keyword: str):
    """过滤 DataFrame"""
    import pandas as pd
    kw = (keyword or "").strip()
    if not kw:
        return df
    text_df = df.astype(str)
    contains = text_df.apply(lambda col: col.str.contains(kw, case=False, na=False, regex=False))
    return df[contains.any(axis=1)]


def validate_upload_payload(
    file_payload: dict,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    allowed_exts: set = None,
    allowed_mime: set = None,
) -> Tuple[bool, str, str]:
    """验证上传文件"""
    if not file_payload:
        return False, "请选择要上传的文件", None

    filename = str(file_payload.get("filename", "")).strip()
    if "." not in filename:
        return False, "文件缺少扩展名", None

    ext = "." + filename.rsplit(".", 1)[1].lower()
    exts = DEFAULT_ALLOWED_EXTS if allowed_exts is None else set(allowed_exts)
    if ext not in exts:
        return False, "仅支持csv或excel文件", ext

    content = file_payload.get("content")
    if not isinstance(content, (bytes, bytearray)) or len(content) == 0:
        return False, "上传文件为空", ext
    if len(content) > max_bytes:
        return False, f"文件过大，最大支持{max_bytes // (1024 * 1024)}MB", ext

    mime = (file_payload.get("mime_type") or "").lower()
    mimes = DEFAULT_ALLOWED_MIME if allowed_mime is None else {m.lower() for m in allowed_mime}
    if mime and mime not in mimes:
        return False, f"不支持的文件类型: {mime}", ext

    return True, "", ext


def parse_uploaded_dataframe(
    file_payload: dict,
    *,
    max_rows: int = 50_000,
    max_cols: int = 200,
):
    """解析上传的文件为 DataFrame"""
    import pandas as pd
    
    ok, msg, ext = validate_upload_payload(file_payload)
    if not ok:
        raise ValueError(msg)

    content = file_payload["content"]
    if ext == ".csv":
        text = content.decode("utf-8")
        df = pd.read_csv(StringIO(text))
    else:
        df = pd.read_excel(BytesIO(content))

    if df.columns.empty:
        raise ValueError("文件必须包含列名")
    if df.empty:
        raise ValueError("上传的文件不能为空")
    if len(df) > max_rows:
        raise ValueError(f"数据行数超过限制({max_rows})")
    if len(df.columns) > max_cols:
        raise ValueError(f"列数超过限制({max_cols})")
    return df


def record_delete_audit(tablename: str, desc: str):
    """记录删除审计"""
    audit = NB("__deleted_tables_meta")
    audit[tablename] = {
        "desc": desc,
        "deleted_at": time.time(),
    }


def get_table_list() -> List[str]:
    """获取所有表名"""
    return NB("default").tables


def get_table_info(tablename: str) -> dict:
    """获取表信息"""
    db = NB(tablename)
    default_db = NB("default")
    
    return {
        "name": tablename,
        "desc": default_db.get(tablename) or "",
        "count": len(db),
        "maxsize": db.maxsize or "无限制",
        "filename": db.db.filename,
        "data_types": {},
    }


def create_table(name: str, desc: str = "") -> dict:
    """创建新表"""
    existing = set(NB("default").tables)
    ok, msg = validate_table_name(name, existing_tables=existing)
    if not ok:
        return {"success": False, "error": msg}
    
    try:
        NB(msg)
        NB("default")[msg] = desc
        return {"success": True, "name": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_table(tablename: str) -> dict:
    """删除表"""
    default_db = NB("default")
    old_desc = default_db.get(tablename, None)
    
    try:
        if tablename in default_db:
            del default_db[tablename]
    except Exception as e:
        return {"success": False, "error": f"删除表元数据失败: {str(e)}"}

    try:
        record_delete_audit(tablename, old_desc)
        NB(tablename).db.drop()
    except Exception as e:
        if old_desc is not None:
            try:
                default_db[tablename] = old_desc
            except Exception:
                pass
        return {"success": False, "error": f"删除表数据失败: {str(e)}"}

    return {"success": True}


def update_table_desc(tablename: str, desc: str) -> dict:
    """更新表描述"""
    try:
        NB("default")[tablename] = desc
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_table_data(tablename: str, sample_size: int = 10) -> dict:
    """获取表数据（分类）"""
    import pandas as pd
    from random import sample as rand_sample
    
    db = NB(tablename)
    items = list(db.items())
    
    if len(items) > sample_size:
        items = rand_sample(items, sample_size)
    
    categorized = {
        "dataframes": [],
        "strings": [],
        "timeseries": [],
        "others": [],
    }
    
    for k, v in items:
        if isinstance(v, pd.DataFrame):
            categorized["dataframes"].append((k, v))
        elif isinstance(v, (str, int, float)) and not str(k).replace(".", "").isdigit():
            categorized["strings"].append((k, v))
        elif isinstance(k, (float, int)) or str(k).replace(".", "").isdigit():
            categorized["timeseries"].append((k, v))
        else:
            categorized["others"].append((k, v))
    
    return categorized


def set_table_data(tablename: str, key: str, value: Any) -> dict:
    """设置表数据"""
    try:
        NB(tablename)[key] = value
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_table_data(tablename: str, key: str) -> dict:
    """删除表数据"""
    try:
        del NB(tablename)[key]
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_dataframe(tablename: str, key: str, file_payload: dict) -> dict:
    """上传 DataFrame 到表"""
    try:
        ok, msg = validate_key_name(key)
        if not ok:
            return {"success": False, "error": msg}
        
        df = parse_uploaded_dataframe(file_payload)
        NB(tablename)[key] = df
        return {"success": True, "rows": len(df), "cols": len(df.columns)}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"上传失败: {str(e)}"}
