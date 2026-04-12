"""策略创建/编辑/实验模式对话框"""

import json
from datetime import datetime

from pywebio.session import run_async

from deva.naja.register import SR
from .table import _get_all_categories
from .detail import _show_result_detail_by_id


def _get_render_strategy_content():
    """延迟导入避免循环引用"""
    from . import _render_strategy_content
    return _render_strategy_content


DEFAULT_STRATEGY_CODE = '''# 策略处理函数
# 必须定义 process(data) 函数
# data 通常是 pandas DataFrame

def process(data):
    """
    策略执行主体函数
    
    参数:
        data: 输入数据 (通常为 pandas.DataFrame)
    
    返回:
        处理后的数据
    """
    import pandas as pd
    
    # 示例：直接返回原始数据
    return data
'''

DEFAULT_DECLARATIVE_CONFIG = {
    "pipeline": [
        {"type": "feature", "name": "price_change"},
        {"type": "feature", "name": "volume_spike"},
    ],
    "model": {"type": "logistic_regression"},
    "params": {"learning_rate": 0.01},
    "logic": {"type": "threshold", "buy": 0.7, "sell": 0.3},
    "state_persist": True,
    "state_persist_interval": 300,
    "state_persist_every_n": 200,
}


async def _show_history_dialog(ctx, mgr):
    """显示执行历史对话框"""
    from ..result_store import get_result_store

    store = get_result_store()
    entries = mgr.list_all()

    strategy_options = [
        {"label": "全部策略", "value": ""},
    ] + [
        {"label": e.name, "value": e.id}
        for e in entries
    ]

    form = await ctx["input_group"]("📜 查询执行历史", [
        ctx["select"]("策略", name="strategy_id", options=strategy_options, value=""),
        ctx["input"]("时间范围(分钟)", name="minutes", type="number", value=60, placeholder="查询最近N分钟"),
        ctx["checkbox"]("仅成功", name="success_only", options=[
                        {"label": "仅显示成功", "value": "success_only", "selected": False}]),
        ctx["input"]("限制条数", name="limit", type="number", value=100),
        ctx["actions"]("操作", [
            {"label": "查询", "value": "query"},
            {"label": "取消", "value": "cancel"},
        ], name="action"),
    ])

    if not form or form.get("action") == "cancel":
        return

    import time as time_module
    start_ts = time_module.time() - form["minutes"] * 60

    results = store.query(
        strategy_id=form["strategy_id"] or None,
        start_ts=start_ts,
        success_only="success_only" in form.get("success_only", []),
        limit=form["limit"],
    )

    with ctx["popup"]("📜 执行历史查询结果", size="large", closable=True):
        ctx["put_markdown"](f"### 📜 执行历史查询结果")
        ctx["put_markdown"](f"**查询条件:** 时间范围: {form['minutes']}分钟, 限制条数: {form['limit']}")
        ctx["put_markdown"](f"**查询结果:** 共找到 {len(results)} 条记录")

        if not results:
            ctx["put_html"](
                "<div style='padding:20px;background:#f8d7da;border-radius:4px;color:#721c24;'>未找到符合条件的记录</div>")
            return

        table_data = [["时间", "策略", "状态", "耗时", "预览", "操作"]]
        for r in results:
            status = "✅" if r.success else "❌"
            preview = (r.output_preview or r.error or "")[:50]
            from datetime import datetime
            ts_readable = datetime.fromtimestamp(r.ts).strftime(
                "%Y-%m-%d %H:%M:%S") if r.ts else ""
            table_data.append([
                ts_readable[:16],
                r.strategy_name[:15] if r.strategy_name else "",
                status,
                f"{r.process_time_ms:.1f}ms",
                preview[:50] + "..." if len(preview) >= 50 else preview,
                ctx["put_button"]("详情", onclick=lambda rid=r.id,
                                  c=ctx: _show_result_detail_by_id(c, rid), small=True),
            ])

        ctx["put_table"](table_data)


async def _open_experiment_dialog(ctx, mgr):
    """开启实验模式"""
    from deva.naja.datasource import get_datasource_manager

    entries = mgr.list_all()
    categories = _get_all_categories(entries)

    if not categories:
        ctx["toast"]("没有可用策略类别", color="warning")
        return

    ds_mgr = get_datasource_manager()
    ds_entries = ds_mgr.list_all()
    if not ds_entries:
        ctx["toast"]("没有可用数据源", color="warning")
        return

    default_categories = ["实验"] if "实验" in categories else []
    category_options = []
    for cat in categories:
        count = len([e for e in entries if getattr(e._metadata, "category", "默认") == cat])
        category_options.append({
            "label": f"{cat} ({count})",
            "value": cat,
            "selected": cat in default_categories,
        })

    ds_options = [{"label": ds.name, "value": ds.id} for ds in ds_entries]
    replay_ds = next((
        ds for ds in ds_entries
        if "回放" in ((getattr(ds, "name", "") or "").strip())
    ), None)
    default_ds_id = replay_ds.id if replay_ds else ds_entries[0].id

    form = await ctx["input_group"]("🧪 开启策略实验模式", [
        ctx["checkbox"]("策略类别（可逐项选择）", name="categories", options=category_options, value=default_categories),
        ctx["select"]("实验数据源", name="datasource_id", options=ds_options, value=default_ds_id),
        ctx["checkbox"]("包含注意力策略", name="include_attention", options=[
            {"label": "👁️ 同时运行注意力策略系统（5个策略）", "value": True, "selected": True}
        ], value=[True]),
        ctx["actions"]("操作", [
            {"label": "开启并启动策略", "value": "start"},
            {"label": "取消", "value": "cancel"},
        ], name="action"),
    ])

    if not form or form.get("action") == "cancel":
        return

    categories_selected = form.get("categories", []) or []
    datasource_id = form.get("datasource_id", "")
    include_attention = bool(form.get("include_attention", [True]))
    result = mgr.start_experiment(categories=categories_selected, datasource_id=datasource_id, include_attention=include_attention)

    if result.get("success"):
        if result.get("datasource_started"):
            ds_name = result.get("datasource_name", "实验数据源")
            ctx["toast"](f"已自动启动数据源：{ds_name}", color="info")
        failed_switch = len(result.get("failed_switch", []))
        failed_start = len(result.get("failed_start", []))
        
        # 构建成功消息
        msg_parts = []
        if result.get("target_count", 0) > 0:
            msg_parts.append(f"原有策略 {result['target_count']} 个")
        if result.get("include_attention"):
            msg_parts.append(f"注意力策略 5 个")
        
        msg = "实验模式已开启"
        if msg_parts:
            msg += "：" + "、".join(msg_parts)
        
        if failed_switch or failed_start:
            ctx["toast"](f"{msg}，切换失败 {failed_switch} 个，启动失败 {failed_start} 个", color="warning")
        else:
            ctx["toast"](msg, color="success")
        _get_render_strategy_content()(ctx)
        return

    ctx["toast"](f"开启失败: {result.get('error', 'unknown error')}", color="error")


def _close_experiment_mode(ctx, mgr):
    """关闭实验模式并恢复策略配置"""
    result = mgr.stop_experiment()
    if result.get("success"):
        # 构建详细的恢复信息
        restored_bind = result.get("restored_bind_count", 0)
        restored_state = result.get("restored_state_count", 0)
        restored_output = result.get("restored_output_count", 0)
        restored_params = result.get("restored_params_count", 0)
        restored_window = result.get("restored_window_count", 0)
        
        detail_parts = []
        if restored_output > 0:
            detail_parts.append(f"输出配置({restored_output})")
        if restored_params > 0:
            detail_parts.append(f"策略参数({restored_params})")
        if restored_window > 0:
            detail_parts.append(f"窗口配置({restored_window})")
        
        detail_str = "、" + "、".join(detail_parts) if detail_parts else ""
        ctx["toast"](f"实验模式已关闭，策略已恢复：数据源绑定({restored_bind})、运行状态({restored_state}){detail_str}", color="success")
    else:
        ctx["toast"](f"关闭失败: {result.get('error', 'unknown error')}", color="error")
    _get_render_strategy_content()(ctx)


async def _edit_strategy_dialog(ctx: dict, mgr, entry_id: str):
    """编辑策略对话框"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return

    from deva.naja.datasource import get_datasource_manager

    ds_mgr = get_datasource_manager()
    dict_mgr = SR('dictionary_manager')

    # 构建数据源选项（用于checkbox）
    source_options = []
    for ds in ds_mgr.list_all():
        source_options.append({"label": f"{ds.name} ({ds.id[:8]}...)", "value": ds.id})

    dict_options = []
    for d in dict_mgr.list_all():
        dict_options.append({"label": d.name, "value": d.id})

    # 获取现有类别
    entries = mgr.list_all()
    existing_categories = _get_all_categories(entries)
    current_category = getattr(entry._metadata, "category", "默认") or "默认"
    category_options = [{"label": "默认", "value": "默认"}]
    for cat in existing_categories:
        if cat != "默认":
            category_options.append({"label": cat, "value": cat})
    category_options.append({"label": "+ 新建类别...", "value": "__new__"})

    with ctx["popup"](f"编辑策略: {entry.name}", size="large", closable=True):
        
        # 先获取输出目标配置（在 popup 里面，表单之前）
        from ..output_controller import get_output_controller
        output_ctrl = get_output_controller()
        current_config = output_ctrl.get_config(entry_id)
        
        # 显示输出目标配置
        ctx["put_html"]("""
        <div style="margin-bottom:15px;padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
            <div style="font-weight:600;color:#334155;margin-bottom:10px;">📤 输出目标配置</div>
            <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px;">
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_signal" """ + ("checked" if current_config.signal else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">💰 信号流</span>
                    <span style="font-size:11px;color:#64748b;">(存储)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_radar" """ + ("checked" if current_config.radar else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">📡 雷达</span>
                    <span style="font-size:11px;color:#f59e0b;">(技术)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_memory" """ + ("checked" if current_config.memory else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">🧠 记忆</span>
                    <span style="font-size:11px;color:#8b5cf6;">(叙事)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_bandit" """ + ("checked" if current_config.bandit else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">🎰 Bandit</span>
                    <span style="font-size:11px;color:#f43f5e;">(交易)</span>
                </label>
            </div>
            
            <!-- 输出结构规范说明 -->
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;">
                <div style="font-size:11px;color:#64748b;margin-bottom:8px;">📋 输出结构规范（开启目标后需按此结构输出）</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:10px;">
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f5576c;">
                        <div style="font-weight:600;color:#f5576c;margin-bottom:4px;">💰 信号流</div>
                        <div style="color:#666;">输出所有结果</div>
                        <div style="color:#999;">任意格式均支持</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f59e0b;">
                        <div style="font-weight:600;color:#f59e0b;margin-bottom:4px;">📡 雷达</div>
                        <div style="color:#666;">signal_type, score</div>
                        <div style="color:#999;">例: fast_anomaly</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #8b5cf6;">
                        <div style="font-weight:600;color:#8b5cf6;margin-bottom:4px;">🧠 记忆</div>
                        <div style="color:#666;">content 必需</div>
                        <div style="color:#999;">topic, sentiment</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f43f5e;grid-column:span 3;">
                        <div style="font-weight:600;color:#f43f5e;margin-bottom:4px;">🎰 Bandit</div>
                        <div style="color:#666;">signal_type(BUY/SELL), stock_code, price</div>
                        <div style="color:#999;">confidence, amount, reason 可选</div>
                    </div>
                </div>
            </div>
        </div>
        """)
        
        compute_mode = getattr(entry._metadata, "compute_mode", "record")
        window_type = getattr(entry._metadata, "window_type", "sliding")
        window_return_partial = getattr(entry._metadata, "window_return_partial", False)
        strategy_type = getattr(entry._metadata, "strategy_type", "legacy") or "legacy"
        strategy_config = getattr(entry._metadata, "strategy_config", {}) or {}
        strategy_params = getattr(entry._metadata, "strategy_params", {}) or {}
        config_json = json.dumps(strategy_config, ensure_ascii=False, indent=2) if strategy_config else json.dumps(DEFAULT_DECLARATIVE_CONFIG, ensure_ascii=False, indent=2)
        params_json = json.dumps(strategy_params, ensure_ascii=False, indent=2) if strategy_params else "{}"
        param_help = strategy_config.get("param_help", {}) if isinstance(strategy_config, dict) else {}
        # 支持多数据源绑定
        bound_datasource_ids = getattr(entry._metadata, "bound_datasource_ids", [])
        if not bound_datasource_ids:
            # 兼容旧版本单数据源
            bound_datasource_id = getattr(entry._metadata, "bound_datasource_id", "")
            if bound_datasource_id:
                bound_datasource_ids = [bound_datasource_id]
        dictionary_profile_ids = getattr(entry._metadata, "dictionary_profile_ids", [])

        if param_help:
            ctx["put_html"](
                "<div style='margin:0 0 8px 0; color:#64748b; font-size:12px;'>"
                "<div style='font-weight:600; color:#475569; margin-bottom:4px;'>参数说明</div>"
                + "".join([f"<div><code>{k}</code>：{v}</div>" for k, v in param_help.items()])
                + "</div>"
            )

        ctx["put_html"]("""
        <div style="margin:0 0 15px 0;padding:10px 12px;background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;font-size:12px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <div><b style="color:#6366f1;">legacy</b> - 传统代码模式，编写 Python process 函数处理数据</div>
                <div><b style="color:#10b981;">river</b> - 使用 River 机器学习库，适合在线学习/预测场景</div>
                <div><b style="color:#f59e0b;">declarative</b> - 声明式配置，通过 pipeline/model/logic 定义处理流程</div>
                <div><b style="color:#ec4899;">plugin</b> - 插件模式，通过类路径加载自定义策略实现</div>
            </div>
        </div>
        """)

        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, value=entry.name),
            ctx["textarea"]("描述", name="description", rows=2,
                            value=getattr(entry._metadata, "description", "") or ""),
            ctx["select"]("类别", name="category_select", options=category_options, value=current_category),
            ctx["input"]("新类别名称", name="category_new", placeholder="输入新类别名称（如选择新建类别）"),
            ctx["checkbox"]("绑定数据源", name="datasource_ids", options=source_options,
                            value=bound_datasource_ids),
            ctx["select"]("字典配置", name="dictionary_profile_ids", options=dict_options,
                          multiple=True, value=dictionary_profile_ids),
            ctx["select"]("计算模式", name="compute_mode", options=[
                {"label": "逐条处理", "value": "record"},
                {"label": "窗口处理", "value": "window"},
            ], value=compute_mode),
            ctx["select"]("窗口类型", name="window_type", options=[
                {"label": "滑动窗口", "value": "sliding"},
                {"label": "定时窗口", "value": "timed"},
            ], value=window_type),
            ctx["input"]("窗口大小", name="window_size", type="number",
                         value=getattr(entry._metadata, "window_size", 5)),
            ctx["input"]("定时窗口间隔", name="window_interval",
                         value=getattr(entry._metadata, "window_interval", "10s"),
                         placeholder="如 5s / 1min / 1h"),
            ctx["select"]("窗口未满是否输出", name="window_return_partial", options=[
                {"label": "否", "value": "false"},
                {"label": "是", "value": "true"},
            ], value="true" if window_return_partial else "false"),
            ctx["input"]("历史保留条数", name="max_history_count", type="number",
                         value=getattr(entry._metadata, "max_history_count", 100)),
            ctx["select"]("策略类型", name="strategy_type", options=[
                {"label": "legacy（代码）", "value": "legacy"},
                {"label": "river", "value": "river"},
                {"label": "declarative（声明式）", "value": "declarative"},
                {"label": "plugin", "value": "plugin"},
            ], value=strategy_type),
            ctx["textarea"]("结构化配置(JSON)", name="strategy_config_json",
                            value=config_json, rows=8,
                            code={"mode": "application/json", "theme": "darcula"}),
            ctx["textarea"]("可调参数(JSON)", name="strategy_params_json",
                            value=params_json, rows=6,
                            code={"mode": "application/json", "theme": "darcula"}),
            ctx["textarea"]("代码", name="code",
                            value=entry.func_code or DEFAULT_STRATEGY_CODE,
                            rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

        if form and form.get("action") == "save":
            form_window_return_partial = str(
                form.get("window_return_partial", "false")).lower() in ("true", "1", "yes")

            # 处理类别
            category = form.get("category_select", "默认")
            if category == "__new__" and form.get("category_new"):
                category = form.get("category_new").strip()
            elif category == "__new__":
                category = current_category

            # 获取多数据源绑定列表
            datasource_ids = form.get("datasource_ids", [])
            # 兼容处理：如果是字符串（单选情况），转换为列表
            if isinstance(datasource_ids, str):
                datasource_ids = [datasource_ids] if datasource_ids else []

            stype = str(form.get("strategy_type") or "legacy").strip().lower()
            config_text = (form.get("strategy_config_json") or "").strip()
            params_text = (form.get("strategy_params_json") or "").strip()
            try:
                strategy_config = json.loads(config_text) if config_text else {}
            except Exception:
                ctx["toast"]("结构化配置 JSON 解析失败", color="error")
                return
            try:
                strategy_params = json.loads(params_text) if params_text else {}
            except Exception:
                ctx["toast"]("可调参数 JSON 解析失败", color="error")
                return

            if stype == "declarative" and not strategy_config:
                strategy_config = DEFAULT_DECLARATIVE_CONFIG.copy()

            if stype == "declarative":
                logic = dict(strategy_config.get("logic") or {})
                if form.get("code") and (not logic or str(logic.get("type", "")).lower() == "python"):
                    logic["type"] = "python"
                    logic["code"] = form.get("code")
                    strategy_config["logic"] = logic
            
            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                bound_datasource_id=datasource_ids[0] if datasource_ids else "",  # 兼容单数据源
                bound_datasource_ids=datasource_ids,  # 多数据源
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode"),
                window_type=form.get("window_type"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=form_window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
                func_code=form.get("code") if stype == "legacy" else "",
                category=category,
                strategy_type=stype,
                strategy_config=strategy_config,
                strategy_params=strategy_params,
            )

            # 保存输出目标配置
            try:
                from ..output_controller import get_output_controller
                output_ctrl = get_output_controller()
                output_ctrl.update_targets(
                    entry_id,
                    signal=form.get("output_signal", True),
                    radar=form.get("output_radar", True),
                    memory=form.get("output_memory", True),
                    bandit=form.get("output_bandit", False),
                )
            except Exception as e:
                print(f"保存输出配置失败: {e}")

            if result.get("success"):
                ctx["toast"]("保存成功", color="success")
                ctx["close_popup"]()
                _get_render_strategy_content()(ctx)
            else:
                ctx["toast"](f"保存失败: {result.get('error')}", color="error")



def _create_strategy_dialog(mgr, ctx: dict):
    """创建策略对话框"""
    run_async(_create_strategy_dialog_async(mgr, ctx))


async def _create_strategy_dialog_async(mgr, ctx: dict):
    """创建策略对话框（异步）"""
    from deva.naja.datasource import get_datasource_manager

    ds_mgr = get_datasource_manager()
    dict_mgr = SR('dictionary_manager')

    # 构建数据源选项（用于checkbox）
    source_options = []
    for ds in ds_mgr.list_all():
        source_options.append({"label": f"{ds.name} ({ds.id[:8]}...)", "value": ds.id})

    dict_options = []
    for d in dict_mgr.list_all():
        dict_options.append({"label": d.name, "value": d.id})

    # 获取现有类别
    entries = mgr.list_all()
    existing_categories = _get_all_categories(entries)
    category_options = [{"label": "默认", "value": "默认"}]
    for cat in existing_categories:
        if cat != "默认":
            category_options.append({"label": cat, "value": cat})
    category_options.append({"label": "+ 新建类别...", "value": "__new__"})

    with ctx["popup"]("创建策略", size="large", closable=True):
        ctx["put_markdown"]("### 创建策略")
        ctx["put_html"]("""
        <div style="margin:0 0 15px 0;padding:10px 12px;background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;font-size:12px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <div><b style="color:#6366f1;">legacy</b> - 传统代码模式，编写 Python process 函数处理数据</div>
                <div><b style="color:#10b981;">river</b> - 使用 River 机器学习库，适合在线学习/预测场景</div>
                <div><b style="color:#f59e0b;">declarative</b> - 声明式配置，通过 pipeline/model/logic 定义处理流程</div>
                <div><b style="color:#ec4899;">plugin</b> - 插件模式，通过类路径加载自定义策略实现</div>
            </div>
        </div>
        """)

        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["textarea"]("描述", name="description", rows=2, placeholder="策略描述（可选）"),
            ctx["select"]("类别", name="category_select", options=category_options, value="默认"),
            ctx["input"]("新类别名称", name="category_new", placeholder="输入新类别名称（如选择新建类别）"),
            ctx["checkbox"]("绑定数据源", name="datasource_ids", options=source_options, value=[]),
            ctx["select"]("字典配置", name="dictionary_profile_ids",
                          options=dict_options, multiple=True, value=[]),
            ctx["select"]("计算模式", name="compute_mode", options=[
                {"label": "逐条处理", "value": "record"},
                {"label": "窗口处理", "value": "window"},
            ], value="record"),
            ctx["select"]("窗口类型", name="window_type", options=[
                {"label": "滑动窗口", "value": "sliding"},
                {"label": "定时窗口", "value": "timed"},
            ], value="sliding"),
            ctx["input"]("窗口大小", name="window_size", type="number", value=5),
            ctx["input"]("定时窗口间隔", name="window_interval", value="10s", placeholder="如 5s / 1min"),
            ctx["select"]("窗口未满是否输出", name="window_return_partial", options=[
                {"label": "否", "value": "false"},
                {"label": "是", "value": "true"},
            ], value="false"),
            ctx["input"]("历史保留条数", name="max_history_count", type="number", value=100),
            ctx["select"]("策略类型", name="strategy_type", options=[
                {"label": "legacy（代码）", "value": "legacy"},
                {"label": "river", "value": "river"},
                {"label": "declarative（声明式）", "value": "declarative"},
                {"label": "plugin", "value": "plugin"},
            ], value="legacy"),
            ctx["textarea"]("结构化配置(JSON)", name="strategy_config_json",
                            value=json.dumps(DEFAULT_DECLARATIVE_CONFIG, ensure_ascii=False, indent=2),
                            rows=8, code={"mode": "application/json", "theme": "darcula"}),
            ctx["textarea"]("可调参数(JSON)", name="strategy_params_json",
                            value="{}", rows=6, code={"mode": "application/json", "theme": "darcula"}),
            ctx["textarea"]("代码", name="code",
                            value=DEFAULT_STRATEGY_CODE,
                            rows=14,
                            code={"mode": "python", "theme": "darcula"}),
        ])

        # 添加输出目标配置（创建时默认全部开启信号）
        ctx["put_html"]("""
        <div style="margin:15px 0;padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
            <div style="font-weight:600;color:#334155;margin-bottom:10px;">📤 输出目标配置</div>
            <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px;">
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_signal" checked style="width:16px;height:16px;">
                    <span style="font-size:13px;">📡 信号流</span>
                    <span style="font-size:11px;color:#64748b;">(存储)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_radar" checked style="width:16px;height:16px;">
                    <span style="font-size:13px;">📡 雷达</span>
                    <span style="font-size:11px;color:#f59e0b;">(技术)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_memory" checked style="width:16px;height:16px;">
                    <span style="font-size:13px;">🧠 记忆</span>
                    <span style="font-size:11px;color:#8b5cf6;">(叙事)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_bandit" style="width:16px;height:16px;">
                    <span style="font-size:13px;">🎰 Bandit</span>
                    <span style="font-size:11px;color:#f43f5e;">(交易)</span>
                </label>
            </div>
            <div style="font-size:11px;color:#94a3b8;">
                新策略默认开启信号流、雷达、记忆输出。Bandit 交易需要手动开启。
            </div>
            
            <!-- 输出结构规范说明 -->
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;">
                <div style="font-size:11px;color:#64748b;margin-bottom:8px;">📋 输出结构规范</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:10px;">
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f5576c;">
                        <div style="font-weight:600;color:#f5576c;margin-bottom:4px;">💰 信号流</div>
                        <div style="color:#666;">输出所有结果</div>
                        <div style="color:#999;">任意格式均支持</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f59e0b;">
                        <div style="font-weight:600;color:#f59e0b;margin-bottom:4px;">📡 雷达</div>
                        <div style="color:#666;">signal_type, score</div>
                        <div style="color:#999;">例: fast_anomaly</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #8b5cf6;">
                        <div style="font-weight:600;color:#8b5cf6;margin-bottom:4px;">🧠 记忆</div>
                        <div style="color:#666;">content 必需</div>
                        <div style="color:#999;">topic, sentiment</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f43f5e;grid-column:span 3;">
                        <div style="font-weight:600;color:#f43f5e;margin-bottom:4px;">🎰 Bandit</div>
                        <div style="color:#666;">signal_type(BUY/SELL), stock_code, price</div>
                        <div style="color:#999;">confidence, amount, reason 可选</div>
                    </div>
                </div>
            </div>
        </div>
        """)

        form = await ctx["input_group"]("确认", [
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

        if form and form.get("action") == "create":
            window_return_partial = str(
                form.get("window_return_partial", "false")).lower() in ("true", "1", "yes")

            # 处理类别
            category = form.get("category_select", "默认")
            if category == "__new__" and form.get("category_new"):
                category = form.get("category_new").strip()
            elif category == "__new__":
                category = "默认"

            # 获取多数据源绑定列表
            datasource_ids = form.get("datasource_ids", [])
            # 兼容处理：如果是字符串（单选情况），转换为列表
            if isinstance(datasource_ids, str):
                datasource_ids = [datasource_ids] if datasource_ids else []

            stype = str(form.get("strategy_type") or "legacy").strip().lower()
            config_text = (form.get("strategy_config_json") or "").strip()
            params_text = (form.get("strategy_params_json") or "").strip()
            try:
                strategy_config = json.loads(config_text) if config_text else {}
            except Exception:
                ctx["toast"]("结构化配置 JSON 解析失败", color="error")
                return
            try:
                strategy_params = json.loads(params_text) if params_text else {}
            except Exception:
                ctx["toast"]("可调参数 JSON 解析失败", color="error")
                return

            if stype == "declarative" and not strategy_config:
                strategy_config = DEFAULT_DECLARATIVE_CONFIG.copy()

            if stype == "declarative":
                logic = dict(strategy_config.get("logic") or {})
                if form.get("code") and (not logic or str(logic.get("type", "")).lower() == "python"):
                    logic["type"] = "python"
                    logic["code"] = form.get("code")
                    strategy_config["logic"] = logic

            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", "") if stype == "legacy" else "",
                description=form.get("description", "").strip(),
                bound_datasource_id=datasource_ids[0] if datasource_ids else "",  # 兼容单数据源
                bound_datasource_ids=datasource_ids,  # 多数据源
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode", "record"),
                window_type=form.get("window_type", "sliding"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
                category=category,
                strategy_type=stype,
                strategy_config=strategy_config,
                strategy_params=strategy_params,
            )

            # 创建成功后设置默认输出目标配置
            if result.get("success"):
                try:
                    from ..output_controller import get_output_controller
                    output_ctrl = get_output_controller()
                    # 新策略默认开启：信号流、雷达、记忆
                    strategy_id = result.get("strategy_id", "")
                    if strategy_id:
                        output_ctrl.update_targets(
                            strategy_id,
                            signal=True,
                            radar=True,
                            memory=True,
                            bandit=False
                        )
                except Exception:
                    pass

                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
                _get_render_strategy_content()(ctx)
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
