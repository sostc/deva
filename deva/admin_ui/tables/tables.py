"""Table-related helpers and facades for admin DB management."""

from __future__ import annotations

import math
import re
import time
from io import BytesIO, StringIO
from ..utils import stable_widget_id


TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}$")
DEFAULT_RESERVED_TABLES = {"default"}
DEFAULT_ALLOWED_EXTS = {".csv", ".xls", ".xlsx"}
DEFAULT_ALLOWED_MIME = {
    "text/csv",
    "application/csv",
    "application/octet-stream",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


async def create_new_table(impl):
    return await impl()


async def delete_table(impl, tablename):
    return await impl(tablename)


def refresh_table_display(impl):
    return impl()


async def create_new_table_ui(ctx):
    table_info = await ctx["input_group"]("新建表", [
        ctx["input"]("表名", name="table_name", required=True),
        ctx["textarea"]("表描述", name="table_desc")
    ])
    ok, table_name_or_msg = validate_table_name(
        table_info.get("table_name"),
        existing_tables=set(ctx["NB"]("default").tables),
    )
    if not ok:
        ctx["toast"](table_name_or_msg, color="error")
        return
    table_name = table_name_or_msg
    try:
        ctx["NB"](table_name)
        ctx["NB"]("default")[table_name] = table_info.get("table_desc")
        ctx["toast"]("表创建成功")
        ctx["refresh_table_display"]()
        ctx["table_click"](table_name)
    except Exception as e:
        ctx["toast"](f"创建表失败: {str(e)}", color="error")


async def delete_table_ui(ctx, tablename):
    confirm = await ctx["pin"]["delete_confirm_name"]
    if str(confirm).strip() != str(tablename).strip():
        ctx["toast"]("请输入正确表名以确认删除", color="warning")
        return

    default_db = ctx["NB"]("default")
    old_desc = default_db.get(tablename, None)
    metadata_removed = False
    try:
        if tablename in default_db:
            del default_db[tablename]
            metadata_removed = True
    except Exception as e:
        (f"删除表元数据失败: table={tablename}, error={e}") >> ctx["warn"]
        ctx["toast"](f"删除表元数据失败: {str(e)}", color="error")
        return

    try:
        record_delete_audit(ctx["NB"], tablename, old_desc)
        ctx["NB"](tablename).db.drop()
    except Exception as e:
        if metadata_removed and old_desc is not None:
            try:
                default_db[tablename] = old_desc
            except Exception as rollback_error:
                (f"回滚表元数据失败: table={tablename}, error={rollback_error}") >> ctx["warn"]
        (f"删除表数据失败: table={tablename}, error={e}") >> ctx["warn"]
        ctx["toast"](f"删除表失败: {str(e)}", color="error")
        return

    ctx["toast"](f"表 {tablename} 已删除", color="success")
    ctx["refresh_table_display"]()
    ctx["table_click"]("default")
    ctx["close_popup"]()


def refresh_table_display_ui(ctx):
    ctx["clear"]("table_display")
    with ctx["use_scope"]("table_display"):
        ctx["put_markdown"]("### 数据表")
        ctx["put_buttons"](ctx["NB"]("default").tables | ctx["ls"], onclick=ctx["table_click"])
        ctx["put_button"]("+新建表", onclick=lambda: ctx["run_async"](ctx["create_new_table"]()))


def validate_table_name(
    name,
    *,
    existing_tables=None,
    reserved_tables=None,
):
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


def validate_key_name(key, *, max_len=128):
    text = str(key or "").strip()
    if not text:
        return False, "键名不能为空"
    if len(text) > max_len:
        return False, f"键名长度不能超过{max_len}"
    return True, text


def compute_total_pages(total_rows, page_size):
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if total_rows <= 0:
        return 1
    return max(1, math.ceil(total_rows / page_size))


def filter_dataframe(df, keyword):
    kw = (keyword or "").strip()
    if not kw:
        return df
    # Use vectorized string contains to avoid row-wise apply overhead.
    text_df = df.astype(str)
    contains = text_df.apply(lambda col: col.str.contains(kw, case=False, na=False, regex=False))
    return df[contains.any(axis=1)]


def validate_upload_payload(
    file_payload,
    *,
    max_bytes=10 * 1024 * 1024,
    allowed_exts=None,
    allowed_mime=None,
):
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
    file_payload,
    pd_module,
    *,
    max_rows=50_000,
    max_cols=200,
):
    ok, msg, ext = validate_upload_payload(file_payload)
    if not ok:
        raise ValueError(msg)

    content = file_payload["content"]
    if ext == ".csv":
        text = content.decode("utf-8")
        df = pd_module.read_csv(StringIO(text))
    else:
        df = pd_module.read_excel(BytesIO(content))

    if df.columns.empty:
        raise ValueError("文件必须包含列名")
    if df.empty:
        raise ValueError("上传的文件不能为空")
    if len(df) > max_rows:
        raise ValueError(f"数据行数超过限制({max_rows})")
    if len(df.columns) > max_cols:
        raise ValueError(f"列数超过限制({max_cols})")
    return df


def record_delete_audit(nb_func, tablename, desc):
    audit = nb_func("__deleted_tables_meta")
    audit[tablename] = {
        "desc": desc,
        "deleted_at": time.time(),
    }


def paginate_dataframe(ctx, scope, df, page_size):
    pd_module = ctx["pd"]
    pin = ctx["pin"]
    use_scope = ctx["use_scope"]
    put_text = ctx["put_text"]
    put_datatable = ctx["put_datatable"]
    put_buttons = ctx["put_buttons"]
    put_button = ctx["put_button"]
    put_row = ctx["put_row"]
    put_input = ctx["put_input"]
    run_async = ctx["run_async"]

    for column in df.columns:
        if pd_module.api.types.is_datetime64_any_dtype(df[column]):
            df[column] = df[column].dt.strftime("%Y-%m-%d %H:%M:%S")
    df = df.fillna("")
    df = df.infer_objects(copy=False)

    def show_page(page, filtered_df=None):
        if filtered_df is None:
            filtered_df = df
        total_pages = compute_total_pages(len(filtered_df), page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        page_data = filtered_df.iloc[start:end]

        with use_scope("table_scope" + scope, clear=True):
            if len(page_data) == 0:
                put_text("没有找到匹配的结果")
            else:
                put_datatable(page_data.to_dict(orient="records"), height="auto")

        with use_scope("buttons_scope" + scope, clear=True):
            put_text(f"第 {page} 页 / 共 {total_pages} 页")
            buttons = []
            if page > 1:
                buttons.append({"label": "上一页", "value": "prev"})
            if page < total_pages:
                buttons.append({"label": "下一页", "value": "next"})
            put_buttons(buttons, onclick=lambda v: show_page(page - 1 if v == "prev" else page + 1, filtered_df))

    async def search():
        keyword = await pin["search_input" + scope]
        show_page(1, filter_dataframe(df, keyword))

    show_page(1)
    put_row([
        put_input("search_input" + scope, placeholder="搜索..."),
        put_button("搜索", onclick=lambda: run_async(search())),
    ])


def display_table_basic_info(ctx, db, tablename):
    put_markdown = ctx["put_markdown"]
    put_row = ctx["put_row"]
    put_table = ctx["put_table"]
    NB = ctx["NB"]

    data_types = {}
    for _, value in db.items():
        data_type = type(value).__name__
        data_types[data_type] = data_types.get(data_type, 0) + 1
    type_rows = [[dtype, count] for dtype, count in data_types.items()]

    put_markdown(f"> 您点击了 `{tablename}` 表格，表基本信息：")
    put_row([
        put_table([
            ["属性", "值"],
            ["记录数", len(db)],
            ["最大容量", db.maxsize or "无限制"],
            ["存储路径", db.db.filename],
            ["表描述", NB("default").get(db.name) or "无描述"],
        ]),
        put_table([["数据类型", "数量"], *type_rows]),
    ])


def table_click(ctx, tablename):
    NB = ctx["NB"]
    clear = ctx["clear"]
    put_markdown = ctx["put_markdown"]
    put_row = ctx["put_row"]
    put_button = ctx["put_button"]
    popup = ctx["popup"]
    put_input = ctx["put_input"]
    put_buttons = ctx["put_buttons"]
    run_async = ctx["run_async"]
    close_popup = ctx["close_popup"]
    sample = ctx["sample"]
    pd_module = ctx["pd"]
    put_collapse = ctx["put_collapse"]
    put_table = ctx["put_table"]
    put_text = ctx["put_text"]
    put_file_upload = ctx["put_file_upload"]
    pin = ctx["pin"]
    toast = ctx["toast"]
    log = ctx["log"]
    traceback = ctx["traceback"]
    use_scope = ctx["use_scope"]

    db = NB(tablename)
    clear("table_content")
    put_markdown(f"#### 表：{tablename} ")
    display_table_basic_info(ctx, db, tablename)

    async def save_table_desc():
        new_desc = await pin["table_desc"]
        NB("default").update((db.name, new_desc))
        close_popup()
        ctx["table_click"](db.name)

    put_row([
        put_button("修改表描述", onclick=lambda: popup("修改表描述", [
            put_input("table_desc", value=NB("default").get(db.name) or "", placeholder="请输入表描述"),
            put_buttons(["保存", "取消"], onclick=[lambda: run_async(save_table_desc()), close_popup])
        ])),
        put_button("删除表", onclick=lambda: popup("删除表", [
            ctx["put_markdown"]("### ⚠️警告：此操作不可逆！"),
            ctx["put_markdown"](f"请输入表名 `{tablename}` 以确认删除"),
            put_input("delete_confirm_name", placeholder=f"请输入 {tablename}"),
            put_buttons(["删除", "取消"], onclick=[lambda: run_async(ctx["delete_table"](tablename)), close_popup])
        ]), color="danger")
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    put_markdown("####  数据表内容")
    put_markdown("> 仅仅随机展示 10 条信息：")
    items = NB(tablename).items() >> sample(10)
    categorized_data = {
        "dataframes": [(k, v) for k, v in items if isinstance(v, pd_module.DataFrame)],
        "strings": [(k, v) for k, v in items if isinstance(v, (str, int, float)) and not str(k).replace(".", "").isdigit()],
        "timeseries": [(k, v) for k, v in items if isinstance(k, (float, int)) or str(k).replace(".", "").isdigit()],
        "others": [(k, v) for k, v in items if not isinstance(v, (pd_module.DataFrame, str)) and not isinstance(v, (float, int, str)) and not (isinstance(k, (float, int)) and str(k).replace(".", "").isdigit())]
    }

    put_button("新增数据", onclick=lambda: edit_data_popup(ctx, categorized_data["strings"], tablename=tablename))

    async def upload_table_data():
        key = await pin["upload_key"]
        ok, key_or_msg = validate_key_name(key)
        if not ok:
            toast(key_or_msg, color="error")
            return
        key = key_or_msg
        file_payload = await pin["upload_file"]
        try:
            df = parse_uploaded_dataframe(file_payload, pd_module, max_rows=50_000, max_cols=200)
            (key, df) >> NB(tablename)
            toast("上传成功", color="success")
            close_popup()
            ctx["table_click"](tablename)
        except ValueError as e:
            toast(str(e), color="error")
        except Exception as e:
            toast(f"上传失败: {str(e)}", color="error")
            log(f"上传失败详情: {traceback.format_exc()}")

    put_button("上传表格数据", onclick=lambda: popup("上传表格数据", [
        put_input("upload_key", placeholder="请输入key值"),
        put_file_upload("upload_file", accept=".csv,.xls,.xlsx", max_size="10M"),
        put_buttons(["上传", "取消"], onclick=[lambda: run_async(upload_table_data()), close_popup])
    ]))

    if categorized_data["strings"]:
        with put_collapse("strings", open=True):
            put_table([["键", "值"]] + [[k, v] for k, v in categorized_data["strings"]])
            put_button("编辑数据", onclick=lambda: edit_data_popup(ctx, categorized_data["strings"], tablename=tablename))

    if categorized_data["others"]:
        with put_collapse("其他对象", open=True):
            for key, value in categorized_data["others"]:
                with put_collapse(key, open=True):
                    if isinstance(value, (dict, object)):
                        def format_value(val):
                            if isinstance(val, dict):
                                return [[str(k), format_value(v)] for k, v in val.items()]
                            if hasattr(val, "__dict__"):
                                attrs = {k: v for k, v in val.__dict__.items() if not k.startswith("_")}
                                return [[str(k), format_value(v)] for k, v in attrs.items()]
                            return str(val)
                        formatted_data = format_value(value)
                        put_table(formatted_data) if formatted_data else put_text(str(value))
                    else:
                        put_text(str(value))

    if categorized_data["dataframes"]:
        with put_collapse("dataframe", open=True):
            for df_name, df in categorized_data["dataframes"]:
                df_label = str(df_name)
                if any("\u4e00" <= char <= "\u9fff" for char in df_label):
                    from pypinyin import pinyin, Style
                    scope_name = "".join([item[0] for item in pinyin(df_label, style=Style.NORMAL)])
                else:
                    scope_name = stable_widget_id(df_label, prefix="dfscope")
                with put_collapse(df_label, open=True):
                    paginate_dataframe(ctx, scope=scope_name, df=df, page_size=10)
                    with use_scope(f"analysis_{scope_name}"):
                        put_buttons(["描述性统计", "数据透视表", "分组聚合", "缺失值分析"], onclick=[
                            lambda df=df, scope=scope_name: run_async(show_descriptive_stats(df, scope)),
                            lambda df=df, scope=scope_name: run_async(show_pivot_table(df, scope)),
                            lambda df=df, scope=scope_name: run_async(show_groupby_analysis(df, scope)),
                            lambda df=df, scope=scope_name: run_async(show_missing_values(df, scope)),
                        ])
                    with use_scope(f"analysis_result_{scope_name}"):
                        pass
                    put_button(f"删除 {df_label}", onclick=lambda name=df_name: run_async(delete_dataframe(ctx, name, tablename)))

        async def show_descriptive_stats(df, scope):
            with use_scope(f"analysis_result_{scope}"):
                put_markdown("### 描述性统计")
                stats = df.describe(include="all").T
                put_table(stats.reset_index().values.tolist())

        async def show_pivot_table(df, scope):
            with use_scope(f"analysis_result_{scope}"):
                put_markdown("### 数据透视表")
                numeric_cols = df.select_dtypes(include="number").columns.tolist()
                category_cols = df.select_dtypes(include="object").columns.tolist()
                if not category_cols or not numeric_cols:
                    toast("需要至少一个分类列和一个数值列", color="error")
                    return
                put_input("pivot_index", placeholder="选择行索引（分类列）")
                put_input("pivot_columns", placeholder="选择列索引（可选，分类列）")
                put_input("pivot_values", placeholder="选择聚合值（数值列）")
                put_buttons(["生成"], onclick=[lambda: run_async(generate_pivot(df, scope))])

        async def generate_pivot(df, scope):
            index = await pin["pivot_index"]
            columns = await pin["pivot_columns"] or None
            values = await pin["pivot_values"]
            try:
                pivot = df.pivot_table(index=index, columns=columns, values=values, aggfunc="mean")
                with use_scope(f"analysis_result_{scope}"):
                    put_table(pivot.reset_index().values.tolist())
            except Exception as e:
                toast(f"生成数据透视表失败: {str(e)}", color="error")

        async def show_groupby_analysis(df, scope):
            with use_scope(f"analysis_result_{scope}"):
                put_markdown("### 分组聚合分析")
                group_cols = df.select_dtypes(include="object").columns.tolist()
                agg_cols = df.select_dtypes(include="number").columns.tolist()
                if not group_cols or not agg_cols:
                    toast("需要至少一个分类列和一个数值列", color="error")
                    return
                put_input("groupby_col", placeholder="选择分组列（分类列）")
                put_input("agg_col", placeholder="选择聚合列（数值列）")
                put_buttons(["分析"], onclick=[lambda: run_async(generate_groupby(df, scope))])

        async def generate_groupby(df, scope):
            group_col = await pin["groupby_col"]
            agg_col = await pin["agg_col"]
            try:
                grouped = df.groupby(group_col)[agg_col].agg(["mean", "sum", "count"])
                with use_scope(f"analysis_result_{scope}"):
                    put_table(grouped.reset_index().values.tolist())
            except Exception as e:
                toast(f"分组聚合失败: {str(e)}", color="error")

        async def show_missing_values(df, scope):
            with use_scope(f"analysis_result_{scope}"):
                put_markdown("### 缺失值分析")
                missing = df.isnull().sum()
                missing_pct = (missing / len(df)) * 100
                missing_df = pd_module.DataFrame({"缺失值数量": missing, "缺失值比例(%)": missing_pct})
                put_table(missing_df.reset_index().values.tolist())

    if categorized_data["timeseries"]:
        with put_collapse("时间序列数据", open=True):
            put_button("编辑数据", onclick=lambda: edit_data_popup(ctx, categorized_data["timeseries"], tablename=tablename))
            table_data = [["时间戳", "可读时间", "值"]]
            datetime_cls = ctx["datetime"]
            for key, value in categorized_data["timeseries"]:
                try:
                    timestamp = float(key)
                    min_valid_ts = datetime_cls.min.timestamp() if hasattr(datetime_cls.min, 'timestamp') else -62135596800
                    max_valid_ts = datetime_cls.max.timestamp() if hasattr(datetime_cls.max, 'timestamp') else 253402300799
                    if min_valid_ts <= timestamp <= max_valid_ts:
                        readable_time = datetime_cls.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        readable_time = "时间戳超出有效范围"
                except (ValueError, TypeError, OverflowError):
                    readable_time = "无效时间戳"
                table_data.append([key, readable_time, value])
            put_table(table_data)


async def save_string(ctx, key, data, tablename):
    new_value = await ctx["pin"][stable_widget_id(key, prefix="value")]
    ctx["NB"](tablename).update((key, new_value))
    for i, (k, _) in enumerate(data):
        if k == key:
            data[i] = (key, new_value)
            break
    ctx["table_click"](tablename)
    ctx["close_popup"]()
    edit_data_popup(ctx, data, tablename=tablename)


async def delete_dataframe(ctx, df_name, tablename):
    try:
        del ctx["NB"](tablename)[df_name]
        ctx["toast"](f"已删除DataFrame: {df_name}", color="success")
        ctx["table_click"](tablename)
    except Exception as e:
        ctx["toast"](f"删除失败: {str(e)}", color="error")


async def delete_string(ctx, key, data, tablename):
    del ctx["NB"](tablename)[key]
    data[:] = [item for item in data if item[0] != key]
    ctx["table_click"](tablename)
    ctx["close_popup"]()
    edit_data_popup(ctx, data, tablename=tablename)


async def add_string(ctx, data, tablename):
    new_key = await ctx["pin"]["new_key"]
    new_value = await ctx["pin"]["new_value"]
    ok, key_or_msg = validate_key_name(new_key)
    if not ok:
        ctx["toast"](key_or_msg, color="error")
        return
    if not new_value:
        ctx["toast"]("键值不能为空", color="error")
        return
    new_key = key_or_msg
    data.append((new_key, new_value))
    ctx["NB"](tablename).update((new_key, new_value))
    ctx["clear"]("add_form")
    ctx["table_click"](tablename)
    ctx["close_popup"]()
    edit_data_popup(ctx, data, tablename=tablename)


def edit_data_popup(ctx, data, tablename):
    run_async = ctx["run_async"]
    return ctx["popup"]("编辑数据", [
        ctx["put_row"]([
            ctx["put_input"]("new_key", placeholder="新键名"),
            ctx["put_input"]("new_value", placeholder="新值"),
            ctx["put_button"]("新增", onclick=lambda: run_async(add_string(ctx, data, tablename))),
        ]),
        ctx["put_table"]([
            ["键", "值", "操作"],
            *[
                [
                    ctx["put_text"](key),
                    ctx["put_input"](stable_widget_id(key, prefix="value"), value=value),
                    ctx["put_buttons"](
                        [{"label": "保存", "value": "save"}, {"label": "删除", "value": "delete"}],
                        onclick=lambda v, k=key: run_async(save_string(ctx, k, data, tablename)) if v == "save" else run_async(delete_string(ctx, k, data, tablename)),
                    ),
                ]
                for key, value in data
            ],
        ]),
    ], size="large")
