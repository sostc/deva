"""数据表管理模块

NB数据库表注册表:
- 所有使用 NB() 访问的表都应该在此注册
- 表名格式: naja_<category>_<name>
"""

from __future__ import annotations

import math
import re
import time
import threading
from io import BytesIO, StringIO
from typing import Any, Callable, Dict, List, Optional, Tuple

from deva import NB


TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}$")

NAJA_TABLE_REGISTRY = {
    # ===== 配置相关(已迁移到文件) =====
    "naja_tasks": "Task配置表(已迁移到文件: config/tasks/)",
    "naja_strategies": "Strategy配置表(已迁移到文件: config/strategies/)",
    "naja_datasources": "Datasource配置表(已迁移到文件: config/datasources/)",

    # ===== 运行时状态 =====
    "naja_config": "Naja运行时配置",
    "naja_meta": "Naja元数据(版本信息等)",
    "naja_running_states": "组件运行状态",

    # ===== 策略相关 =====
    "naja_strategy_results": "策略执行结果(历史)",
    "naja_strategy_metrics": "策略性能指标",
    "naja_strategy_experiment": "策略实验记录",
    "naja_strategy_runtime_state": "策略运行时状态(DeclarativeStrategy)",
    "naja_strategy_registry": "策略注册表",
    "naja_strategy_models": "策略模型持久化",
    "naja_strategy_resets": "策略重置记录",
    "naja_strategy_output_targets": "策略输出目标配置",

    # ===== LLM相关 =====
    "naja_llm_decisions": "LLM决策记录",
    "naja_llm_tuning": "LLM调优参数",
    "naja_llm_resets": "LLM重置记录",
    "naja_llm_reflections": "LLM反思记录",

    # ===== 数据源相关 =====
    "naja_ds_latest_data": "数据源最新数据缓存",

    # ===== 字典相关 =====
    "naja_dictionary_entries": "字典条目表",
    "naja_dictionary_payloads": "字典载荷表",

    # ===== 注意力系统 =====
    "naja_attention_tracker": "注意力追踪器状态",
    "naja_attention_snapshots": "注意力榜单快照(用于复盘)",
    "naja_price_monitor_config": "价格监控配置",
    "naja_realtime_quotes": "实时行情缓存",
    "naja_signal_tuner": "信号调优器状态",

    # ===== Bandit系统 =====
    "naja_bandit_config": "Bandit基础配置",
    "naja_bandit_market_config": "Bandit市场数据配置",
    "naja_bandit_signal_config": "Bandit信号配置",
    "naja_bandit_adaptive_config": "Bandit自适应配置",
    "naja_bandit_portfolio_manager": "Bandit组合管理器",
    "naja_bandit_positions": "Bandit统一持仓表(所有账户持仓)",

    "naja_bandit_stats": "Bandit统计",
    "naja_bandit_decisions": "Bandit决策记录",
    "naja_bandit_actions": "Bandit动作记录",
    "naja_bandit_position_rewards": "Bandit持仓收益",
    "naja_bandit_attribution": "Bandit归因分析",

    # ===== 雷达/新闻 =====
    "naja_radar_events": "雷达事件",
    "naja_news_radar_state": "新闻雷达状态",
    "naja_market_state_daily": "市场状态每日快照(用于复盘)",
    "naja_bandit_decision_context": "Bandit决策上下文快照(用于复盘)",

    # ===== 洞察/认知 =====
    "naja_insight_pool": "洞察池",
    "naja_insight_state": "洞察系统状态",
    "naja_narrative_tracker_state": "叙事追踪器状态",
    "naja_market_analysis": "市场分析结果",
    "naja_daily_review_state": "市场回放状态",
    "naja_daily_review_history": "市场回放历史",
    "naja_lobster_radar_state": "LOBSTER雷达状态",
    "naja_openrouter_trend": "OpenRouter趋势数据",
    "naja_loop_audit": "循环审计记录",
    "naja_test_state": "测试状态",
    "naja_radar_thread": "雷达线程状态",
    "naja_signals": "信号记录",

    # ===== 任务 =====
    "naja_task_history": "任务执行历史",

    # ===== 页面帮助 =====
    "naja_page_help": "页面帮助信息",
}

SYSTEM_TABLE_REGISTRY = {
    # ===== 系统表 =====
    "default": "默认命名空间(表描述存储)",
    "__deleted_tables_meta": "已删除表审计记录",
    "deva_config": "Deva主配置",
    "deva_bus_clients": "Deva总线客户端注册",
    "deva_tasks": "Deva任务配置",
    "naja": "Naja启动状态标记",


    # ===== 临时/演示表 =====
    "tmp": "临时数据(测试用)",
    "sample": "示例数据",
    "numbers": "数字序列数据",

    "temp": "临时数据存储",
    "users": "用户数据(示例)",

    # ===== 外部集成 =====
    "dtalk_archive": "钉钉消息归档",
    "dtalk_deva": "钉钉配置(Webhook/Secret)",
    "mail": "邮件配置(SMTP)",

    # ===== 其他表 =====
    "bookmarks": "书签",
    "page_prompts": "页面提示词",
    "people": "人物数据",
    "topics": "主题数据",
    "康熙字典": "康熙字典数据",
    "生僻字": "生僻字数据",
    "system_config": "系统配置",
    "openrouter_trend": "OpenRouter趋势",

    # ===== 行情数据 =====
    "quant_snapshot_5min_window": "5分钟窗口行情快照",
    "replay_tick_analysis": "回放Tick分析",
    "us_stock_prices": "美股价格(统一存储)",
    "test_price": "测试价格数据",
    "test_price_123": "测试价格数据123",

    # ===== 新闻数据 =====
    "新华社热点": "新华社热点新闻",
    "新华社蓝字新闻": "新华社蓝字新闻",
    "财报日历": "财报发布日历",
}

ALL_TABLE_REGISTRIES = {**NAJA_TABLE_REGISTRY, **SYSTEM_TABLE_REGISTRY}
DEFAULT_RESERVED_TABLES = set(NAJA_TABLE_REGISTRY.keys())
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
    import pandas as pd
    import time
    
    db = NB(tablename)
    default_db = NB("default")
    
    # 计算记录数，对于大表使用估计值
    if tablename == "naja_strategy_results":
        # 对于策略结果表，使用时间切片快速估算
        current_time = time.time()
        one_day_ago = current_time - (24 * 3600)
        start_str = pd.Timestamp(one_day_ago).strftime("%Y-%m-%d %H:%M:%S")
        end_str = pd.Timestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
        
        if start_str and end_str:
            try:
                # 获取一天内的记录数，然后估算总记录数
                day_count = len(list(db[start_str:end_str]))
                # 假设数据均匀分布，估算7天的记录数
                estimated_count = day_count * 7
                count = estimated_count
            except:
                # 如果估算失败，返回一个合理的估计值
                count = "大量记录（估算）"
        else:
            count = "大量记录"
    else:
        # 对于其他表，尝试计算实际记录数，但限制最大计数
        try:
            count = 0
            max_count = 10000  # 最多计数10000条
            for _ in db.keys():
                count += 1
                if count >= max_count:
                    count = f"{max_count}+"
                    break
        except:
            count = "未知"
    
    return {
        "name": tablename,
        "desc": default_db.get(tablename) or "",
        "count": count,
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
    
    # 特别处理策略结果表，利用时间切片功能
    if tablename == "naja_strategy_results":
        # 获取最近的sample_size条记录
        import time
        current_time = time.time()
        # 计算7天前的时间戳
        seven_days_ago = current_time - (7 * 24 * 3600)
        # 转换为时间字符串格式
        start_str = pd.Timestamp(seven_days_ago).strftime("%Y-%m-%d %H:%M:%S")
        end_str = pd.Timestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
        
        # 使用时间切片获取键
        time_slice_keys = list(db[start_str:end_str])
        
        # 如果时间范围内的记录不足sample_size，获取所有键
        if len(time_slice_keys) < sample_size:
            all_keys = list(db.keys())
            # 按时间戳排序，取最近的sample_size条
            try:
                # 尝试按时间戳排序
                sorted_keys = sorted(all_keys, key=lambda x: float(x.split(":")[1]) if ":" in x else 0, reverse=True)
                keys_to_use = sorted_keys[:sample_size]
            except:
                # 如果排序失败，随机采样
                if len(all_keys) > sample_size:
                    keys_to_use = rand_sample(all_keys, sample_size)
                else:
                    keys_to_use = all_keys
        else:
            # 按时间戳排序，取最近的sample_size条
            try:
                sorted_keys = sorted(time_slice_keys, key=lambda x: float(x.split(":")[1]) if ":" in x else 0, reverse=True)
                keys_to_use = sorted_keys[:sample_size]
            except:
                # 如果排序失败，随机采样
                keys_to_use = rand_sample(time_slice_keys, sample_size)
        
        # 构建items列表
        items = []
        for key in keys_to_use:
            try:
                value = db.get(key)
                items.append((key, value))
            except:
                pass
    else:
        # 对于其他表，使用原逻辑，但限制最大加载数量
        max_load = min(1000, sample_size * 10)  # 最多加载1000条
        items = []
        count = 0
        for k, v in db.items():
            items.append((k, v))
            count += 1
            if count >= max_load:
                break
        
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
