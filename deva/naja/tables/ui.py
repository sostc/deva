"""数据表管理 UI"""

from datetime import datetime
from random import sample as rand_sample

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, use_scope, set_scope, clear, put_collapse, put_datatable, put_button, put_row
from pywebio.input import input_group, input, textarea, select, actions, file_upload
from pywebio.session import run_async
from pywebio import pin

from ..common.ui_style import apply_strategy_like_styles, render_empty_state, render_stats_cards
from . import (
    get_table_list,
    get_table_info,
    create_table,
    delete_table,
    update_table_desc,
    get_table_data,
    set_table_data,
    delete_table_data,
    upload_dataframe,
    validate_table_name,
    validate_key_name,
    compute_total_pages,
    filter_dataframe,
)


def render_tables_page(ctx: dict):
    """渲染数据表管理页面"""
    clear("tables_content")
    apply_strategy_like_styles(ctx, scope="tables_content", include_compact_table=True)
    ctx["put_html"](
        "<style>.pywebio-table .pywebio-btn-group{flex-wrap:nowrap!important;gap:6px!important;}</style>",
        scope="tables_content",
    )
    
    tables = get_table_list()
    
    ctx["put_html"](_render_stats_html(len(tables)), scope="tables_content")
    
    if tables:
        table_data = _build_table_list(ctx, tables)
        ctx["put_table"](table_data, header=["表名", "描述", "操作"], scope="tables_content")
    else:
        ctx["put_html"](render_empty_state("暂无数据表，点击下方按钮创建"), scope="tables_content")
    
    ctx["put_html"]('<div style="margin-top:16px;">', scope="tables_content")
    ctx["put_buttons"]([
        {"label": "➕ 创建表", "value": "create", "color": "primary"},
    ], onclick=lambda v, c=ctx: _handle_create_table(c), scope="tables_content")
    ctx["put_html"]('</div>', scope="tables_content")


def _render_stats_html(count: int) -> str:
    return render_stats_cards([
        {"label": "总表数", "value": count, "gradient": "linear-gradient(135deg,#667eea,#764ba2)", "shadow": "rgba(102,126,234,0.3)"},
    ])


def _build_table_list(ctx: dict, tables: list) -> list:
    """构建表列表数据"""
    default_db = ctx["NB"]("default")
    table_data = []
    
    for name in sorted(tables):
        if name.startswith("_"):
            continue
        try:
            desc = default_db.get(name) or ""
            
            actions = ctx["put_buttons"]([
                {"label": "查看", "value": f"view_{name}", "color": "info"},
                {"label": "删除", "value": f"delete_{name}", "color": "danger"},
            ], onclick=lambda v, c=ctx: _handle_table_action(v, c), small=True)
            
            table_data.append([
                ctx["put_html"](
                    f'<div style="max-width:260px;font-weight:600;color:#333;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{name}">{name}</div>'
                ),
                ctx["put_html"](
                    f'<div style="max-width:360px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#666;" title="{desc}">{desc or "-"}</div>'
                ),
                actions,
            ])
        except Exception:
            pass
    
    return table_data


def _handle_create_table(ctx: dict):
    """处理创建表"""
    run_async(_create_table_dialog(ctx))


async def _create_table_dialog(ctx: dict):
    """创建表对话框"""
    form = await ctx["input_group"]("创建新表", [
        ctx["input"]("表名", name="table_name", required=True, placeholder="仅支持字母/数字/_/-"),
        ctx["textarea"]("描述", name="table_desc", rows=2, placeholder="表描述（可选）"),
    ], cancelable=True)
    
    if form:
        if not form.get("table_name", "").strip():
            ctx["toast"]("表名不能为空", color="error")
            return
        
        result = create_table(form["table_name"], form.get("table_desc", ""))
        if result["success"]:
            ctx["toast"]("创建成功", color="success")
            render_tables_page(ctx)
        else:
            ctx["toast"](result["error"], color="error")


def _handle_table_action(action: str, ctx: dict):
    """处理表操作"""
    parts = action.split("_", 1)
    action_type = parts[0]
    table_name = parts[1] if len(parts) > 1 else ""
    
    if action_type == "view":
        run_async(_show_table_detail(ctx, table_name))
    elif action_type == "delete":
        run_async(_confirm_delete_table(ctx, table_name))


async def _show_table_detail(ctx: dict, tablename: str):
    """显示表详情"""
    info = get_table_info(tablename)
    data = get_table_data(tablename, sample_size=10)
    
    with ctx["popup"](f"表: {tablename}", size="large", closable=True):
        ctx["put_markdown"]("### 基本信息")
        
        type_rows = [[dtype, count] for dtype, count in info["data_types"].items()]
        
        ctx["put_row"]([
            ctx["put_table"]([
                ["属性", "值"],
                ["记录数", info["count"]],
                ["最大容量", info["maxsize"]],
                ["存储路径", info["filename"]],
                ["表描述", info["desc"]],
            ]),
            ctx["put_table"]([["数据类型", "数量"], *type_rows]) if type_rows else ctx["put_text"](""),
        ])
        
        ctx["put_markdown"]("### 操作")
        ctx["put_row"]([
            ctx["put_button"]("修改描述", onclick=lambda: run_async(_edit_desc_dialog(ctx, tablename))),
            ctx["put_button"]("新增数据", onclick=lambda: run_async(_add_data_dialog(ctx, tablename))),
            ctx["put_button"]("上传表格", onclick=lambda: run_async(_upload_dialog(ctx, tablename))),
        ])
        
        ctx["put_markdown"]("### 数据预览（随机10条）")
        
        if data["strings"]:
            with ctx["put_collapse"]("字符串数据", open=True):
                ctx["put_table"]([["键", "值", "操作"]] + [
                    [k, str(v)[:100], ctx["put_buttons"]([
                        {"label": "编辑", "value": f"edit_{k}", "small": True},
                        {"label": "删除", "value": f"del_{k}", "small": True, "color": "danger"},
                    ], onclick=lambda v, t=tablename, c=ctx: run_async(_handle_string_action(v, t, c)))]
                    for k, v in data["strings"]
                ])
        
        if data["dataframes"]:
            with ctx["put_collapse"]("DataFrame 数据", open=True):
                for df_name, df in data["dataframes"]:
                    with ctx["put_collapse"](str(df_name), open=False):
                        _render_dataframe_preview(ctx, df, scope=str(df_name))
                        ctx["put_buttons"]([
                            {"label": f"🗑️ 删除 {df_name}", "value": f"del_{df_name}", "color": "danger"},
                        ], onclick=lambda v, t=tablename, n=df_name, c=ctx: run_async(_delete_dataframe(c, t, n)))
        
        if data["timeseries"]:
            with ctx["put_collapse"]("时间序列数据", open=True):
                ts_data = [["时间戳", "可读时间", "值"]]
                for k, v in data["timeseries"]:
                    try:
                        ts = float(k)
                        readable = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError, OverflowError):
                        readable = "无效时间戳"
                    ts_data.append([k, readable, str(v)[:50]])
                ctx["put_table"](ts_data)
        
        if data["others"]:
            with ctx["put_collapse"]("其他数据", open=True):
                for k, v in data["others"]:
                    with ctx["put_collapse"](str(k), open=False):
                        if isinstance(v, dict):
                            ctx["put_table"]([["键", "值", "类型"]] + [
                                [sub_k, str(sub_v)[:100] if len(str(sub_v)) > 100 else str(sub_v), type(sub_v).__name__]
                                for sub_k, sub_v in v.items()
                            ])
                        elif isinstance(v, (list, tuple)) and len(v) < 20:
                            ctx["put_table"]([["索引", "值", "类型"]] + [
                                [i, str(item)[:100] if len(str(item)) > 100 else str(item), type(item).__name__]
                                for i, item in enumerate(v)
                            ])
                        else:
                            ctx["put_text"](f"类型: {type(v).__name__}")
                            ctx["put_code"](str(v)[:500], language="text")


def _render_dataframe_preview(ctx: dict, df, scope: str, page_size: int = 10):
    """渲染 DataFrame 预览（分页）"""
    import pandas as pd
    import hashlib
    import re
    
    # 确保 scope 名称只包含合法字符（字母、数字、连字符、下划线）
    if not re.match(r'^[a-zA-Z0-9_-]+$', str(scope)):
        scope = hashlib.md5(str(scope).encode()).hexdigest()[:12]
    
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            df[column] = df[column].dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 处理缺失值，避免 FutureWarning
    pd.set_option('future.no_silent_downcasting', True)
    df = df.fillna("")
    df = df.infer_objects(copy=False)
    pd.set_option('future.no_silent_downcasting', False)
    
    # 预先创建 scope
    set_scope(f"table_scope_{scope}")
    set_scope(f"buttons_scope_{scope}")
    set_scope(f"analysis_{scope}")
    set_scope(f"analysis_result_{scope}")
    
    def show_page(page: int, filtered_df=None):
        if filtered_df is None:
            filtered_df = df
        total_pages = compute_total_pages(len(filtered_df), page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        page_data = filtered_df.iloc[start:end]
        
        clear(f"table_scope_{scope}")
        if len(page_data) == 0:
            ctx["put_text"]("没有找到匹配的结果", scope=f"table_scope_{scope}")
        else:
            ctx["put_datatable"](page_data.to_dict(orient="records"), height="auto", scope=f"table_scope_{scope}")
        
        clear(f"buttons_scope_{scope}")
        ctx["put_text"](f"第 {page} 页 / 共 {total_pages} 页", scope=f"buttons_scope_{scope}")
        buttons = []
        if page > 1:
            buttons.append({"label": "上一页", "value": "prev"})
        if page < total_pages:
            buttons.append({"label": "下一页", "value": "next"})
        if buttons:
            ctx["put_buttons"](buttons, onclick=lambda v: show_page(page - 1 if v == "prev" else page + 1, filtered_df), scope=f"buttons_scope_{scope}")
    
    async def search():
        keyword = await pin.pin[f"search_input_{scope}"]
        show_page(1, filter_dataframe(df, keyword))
    
    show_page(1)
    
    ctx["put_row"]([
        pin.put_input(f"search_input_{scope}", placeholder="搜索..."),
        ctx["put_button"]("搜索", onclick=lambda: run_async(search())),
    ])
    
    # 分析功能
    ctx["put_buttons"]([
        {"label": "📊 描述性统计", "value": "stats"},
        {"label": "📈 数据透视表", "value": "pivot"},
        {"label": "📊 分组聚合", "value": "groupby"},
        {"label": "❓ 缺失值分析", "value": "missing"},
    ], onclick=lambda v: run_async(_show_analysis(ctx, df, scope, v)), scope=f"analysis_{scope}")


async def _show_analysis(ctx: dict, df, scope: str, analysis_type: str):
    """显示数据分析结果"""
    import pandas as pd
    
    clear(f"analysis_result_{scope}")
    
    if analysis_type == "stats":
        ctx["put_markdown"]("### 描述性统计", scope=f"analysis_result_{scope}")
        stats = df.describe(include="all").T
        ctx["put_table"](stats.reset_index().values.tolist(), scope=f"analysis_result_{scope}")
    
    elif analysis_type == "pivot":
        ctx["put_markdown"]("### 数据透视表", scope=f"analysis_result_{scope}")
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        category_cols = df.select_dtypes(include="object").columns.tolist()
        if not category_cols or not numeric_cols:
            ctx["toast"]("需要至少一个分类列和一个数值列", color="error")
            return
        ctx["put_text"](f"分类列: {', '.join(category_cols)}", scope=f"analysis_result_{scope}")
        ctx["put_text"](f"数值列: {', '.join(numeric_cols)}", scope=f"analysis_result_{scope}")
        pin.put_input(f"pivot_index_{scope}", placeholder="选择行索引（分类列）", scope=f"analysis_result_{scope}")
        pin.put_input(f"pivot_columns_{scope}", placeholder="选择列索引（可选）", scope=f"analysis_result_{scope}")
        pin.put_input(f"pivot_values_{scope}", placeholder="选择聚合值（数值列）", scope=f"analysis_result_{scope}")
        ctx["put_buttons"]([{"label": "生成", "value": "generate"}], 
                          onclick=lambda v: run_async(_generate_pivot(ctx, df, scope)), scope=f"analysis_result_{scope}")
    
    elif analysis_type == "groupby":
        ctx["put_markdown"]("### 分组聚合分析", scope=f"analysis_result_{scope}")
        group_cols = df.select_dtypes(include="object").columns.tolist()
        agg_cols = df.select_dtypes(include="number").columns.tolist()
        if not group_cols or not agg_cols:
            ctx["toast"]("需要至少一个分类列和一个数值列", color="error")
            return
        ctx["put_text"](f"分类列: {', '.join(group_cols)}", scope=f"analysis_result_{scope}")
        ctx["put_text"](f"数值列: {', '.join(agg_cols)}", scope=f"analysis_result_{scope}")
        pin.put_input(f"groupby_col_{scope}", placeholder="选择分组列（分类列）", scope=f"analysis_result_{scope}")
        pin.put_input(f"agg_col_{scope}", placeholder="选择聚合列（数值列）", scope=f"analysis_result_{scope}")
        ctx["put_buttons"]([{"label": "分析", "value": "analyze"}], 
                          onclick=lambda v: run_async(_generate_groupby(ctx, df, scope)), scope=f"analysis_result_{scope}")
    
    elif analysis_type == "missing":
        ctx["put_markdown"]("### 缺失值分析", scope=f"analysis_result_{scope}")
        missing = df.isnull().sum()
        missing_pct = (missing / len(df)) * 100
        missing_df = pd.DataFrame({"缺失值数量": missing, "缺失值比例(%)": missing_pct})
        ctx["put_table"](missing_df.reset_index().values.tolist(), scope=f"analysis_result_{scope}")


async def _generate_pivot(ctx: dict, df, scope: str):
    """生成数据透视表"""
    index = await pin.pin[f"pivot_index_{scope}"]
    columns = await pin.pin[f"pivot_columns_{scope}"] or None
    values = await pin.pin[f"pivot_values_{scope}"]
    
    try:
        pivot = df.pivot_table(index=index, columns=columns, values=values, aggfunc="mean")
        clear(f"analysis_result_{scope}")
        ctx["put_markdown"]("### 数据透视表结果", scope=f"analysis_result_{scope}")
        ctx["put_table"](pivot.reset_index().values.tolist(), scope=f"analysis_result_{scope}")
    except Exception as e:
        ctx["toast"](f"生成数据透视表失败: {str(e)}", color="error")


async def _generate_groupby(ctx: dict, df, scope: str):
    """生成分组聚合结果"""
    group_col = await pin.pin[f"groupby_col_{scope}"]
    agg_col = await pin.pin[f"agg_col_{scope}"]
    
    try:
        grouped = df.groupby(group_col)[agg_col].agg(["mean", "sum", "count"])
        clear(f"analysis_result_{scope}")
        ctx["put_markdown"]("### 分组聚合结果", scope=f"analysis_result_{scope}")
        ctx["put_table"](grouped.reset_index().values.tolist(), scope=f"analysis_result_{scope}")
    except Exception as e:
        ctx["toast"](f"分组聚合失败: {str(e)}", color="error")


async def _edit_desc_dialog(ctx: dict, tablename: str):
    """编辑表描述对话框"""
    info = get_table_info(tablename)
    
    # 先关闭当前的 popup
    ctx["close_popup"]()
    
    form = await ctx["input_group"]("修改表描述", [
        ctx["input"]("描述", name="desc", value=info["desc"], placeholder="请输入表描述"),
    ], cancelable=True)
    
    if form:
        result = update_table_desc(tablename, form["desc"])
        if result["success"]:
            ctx["toast"]("修改成功", color="success")
            run_async(_show_table_detail(ctx, tablename))
        else:
            ctx["toast"](result["error"], color="error")
    else:
        run_async(_show_table_detail(ctx, tablename))


async def _handle_string_action(action: str, tablename: str, ctx: dict):
    """处理字符串数据操作"""
    parts = action.split("_", 1)
    action_type = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    
    if action_type == "edit":
        await _edit_string_data(ctx, tablename, key)
    elif action_type == "del":
        await _delete_string_data(ctx, tablename, key)


async def _edit_string_data(ctx: dict, tablename: str, key: str):
    """编辑字符串数据"""
    from deva import NB
    current_value = NB(tablename).get(key, "")
    
    # 先关闭当前的 popup，再显示编辑对话框
    ctx["close_popup"]()
    
    form = await ctx["input_group"](f"编辑数据: {key}", [
        ctx["textarea"]("值", name="value", value=str(current_value), rows=5, placeholder="请输入值"),
    ], cancelable=True)
    
    if form:
        result = set_table_data(tablename, key, form["value"])
        if result["success"]:
            ctx["toast"]("修改成功", color="success")
            run_async(_show_table_detail(ctx, tablename))
        else:
            ctx["toast"](result["error"], color="error")
    else:
        # 用户取消，重新显示表详情
        run_async(_show_table_detail(ctx, tablename))


async def _delete_string_data(ctx: dict, tablename: str, key: str):
    """删除字符串数据"""
    result = delete_table_data(tablename, key)
    if result["success"]:
        ctx["toast"](f"已删除: {key}", color="success")
        ctx["close_popup"]()
        run_async(_show_table_detail(ctx, tablename))
    else:
        ctx["toast"](result["error"], color="error")


async def _delete_dataframe(ctx: dict, tablename: str, df_name: str):
    """删除 DataFrame"""
    result = delete_table_data(tablename, df_name)
    if result["success"]:
        ctx["toast"](f"已删除: {df_name}", color="success")
        ctx["close_popup"]()
        run_async(_show_table_detail(ctx, tablename))
    else:
        ctx["toast"](result["error"], color="error")


async def _add_data_dialog(ctx: dict, tablename: str):
    """新增数据对话框"""
    # 先关闭当前的 popup
    ctx["close_popup"]()
    
    form = await ctx["input_group"]("新增数据", [
        ctx["input"]("键名", name="key", placeholder="请输入键名"),
        ctx["textarea"]("值", name="value", rows=3, placeholder="请输入值（字符串）"),
    ], cancelable=True)
    
    if form:
        result = set_table_data(tablename, form["key"], form["value"])
        if result["success"]:
            ctx["toast"]("添加成功", color="success")
            run_async(_show_table_detail(ctx, tablename))
        else:
            ctx["toast"](result["error"], color="error")
    else:
        run_async(_show_table_detail(ctx, tablename))


async def _upload_dialog(ctx: dict, tablename: str):
    """上传表格数据对话框"""
    # 先关闭当前的 popup
    ctx["close_popup"]()
    
    form = await ctx["input_group"]("上传表格数据", [
        ctx["input"]("键名", name="key", placeholder="请输入键名"),
        file_upload("文件", name="file", accept=".csv,.xls,.xlsx", max_size="10M"),
    ], cancelable=True)
    
    if form and form.get("file"):
        result = upload_dataframe(tablename, form["key"], form["file"])
        if result["success"]:
            ctx["toast"](f"上传成功: {result['rows']} 行, {result['cols']} 列", color="success")
            run_async(_show_table_detail(ctx, tablename))
        else:
            ctx["toast"](result["error"], color="error")
    elif form:
        ctx["toast"]("请选择要上传的文件", color="warning")
        run_async(_show_table_detail(ctx, tablename))
    else:
        run_async(_show_table_detail(ctx, tablename))


async def _confirm_delete_table(ctx: dict, tablename: str):
    """确认删除表对话框"""
    ctx["popup"]("⚠️ 确认删除", [
        ctx["put_markdown"](f"此操作不可逆！请输入表名 `{tablename}` 以确认删除："),
        pin.put_input("confirm_name", placeholder=f"请输入 {tablename}"),
        ctx["put_buttons"]([
            {"label": "确认删除", "value": "confirm", "color": "danger"},
            {"label": "取消", "value": "cancel"},
        ], onclick=lambda v: run_async(_do_delete_table(ctx, tablename, v))),
    ])
    
async def _do_delete_table(ctx: dict, tablename: str, action: str):
    """执行删除表操作"""
    if action == "cancel":
        ctx["close_popup"]()
        return
    
    confirm_name = await pin.pin["confirm_name"]
    if confirm_name == tablename:
        result = delete_table(tablename)
        if result["success"]:
            ctx["toast"](f"表 {tablename} 已删除", color="success")
            ctx["close_popup"]()
            render_tables_page(ctx)
        else:
            ctx["toast"](result["error"], color="error")
    else:
        ctx["toast"]("表名不匹配", color="warning")
