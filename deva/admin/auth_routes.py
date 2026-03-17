"""Auth and route helpers (merged from auth.py + route_helpers.py)."""

from typing import Callable, Union


# ---- Route helpers ----
class ExceedMaxTokenError(Exception):
    pass


class OmittedContentError(Exception):
    pass


def scope_clear(scope, session):
    target_scope = "#pywebio-scope-" + scope
    data = {
        "command": "output_ctl",
        "spec": {"clear": target_scope},
        "task_id": "callback_coro-eEh6wdXSnH",
    }
    return session.send_task_command(data)


FUNC_ATTR_STREAM_TYPES = ("map", "sink", "starmap", "filter")


def _get_func_info(stream):
    """获取流的执行函数信息（用于 map/sink/starmap/filter 等类型）"""
    stream_type = stream.__class__.__name__
    
    if stream_type == "filter":
        func = getattr(stream, "predicate", None)
    else:
        func = getattr(stream, "func", None)
    
    if func is None:
        return "-"
    
    func_name = getattr(func, "__name__", "")
    if func_name and func_name != "<lambda>":
        return func_name
    
    try:
        import inspect
        source_lines = inspect.getsource(func)
        source_lines = source_lines.strip()
        if len(source_lines) > 50:
            return source_lines[:50] + "..."
        return source_lines
    except Exception:
        if func_name:
            return func_name
        return str(func)[:50]


def _show_stream_detail_popup(ctx, stream, title_prefix="流详情"):
    """展示单个流的详情popup页面"""
    stream_id = str(hash(stream))
    stream_name = getattr(stream, "name", "") or "未命名"
    
    with ctx["popup"](f"{title_prefix}: {stream_name}", size="large"):
        ctx["put_markdown"]("## 基本信息")
        info_data = [
            ["属性", "值"],
            ["流名称", stream_name],
            ["流描述", getattr(stream, "description", None) or "无描述"],
            ["流类型", stream.__class__.__name__],
            ["流ID", stream_id],
            ["上游数量", str(len([u for u in stream.upstreams if u]))],
            ["下游数量", str(len(stream.downstreams))],
        ]
        
        stream_type = stream.__class__.__name__
        if stream_type in FUNC_ATTR_STREAM_TYPES:
            func_info = _get_func_info(stream)
            info_data.append(["执行函数", func_info])
        
        ctx["put_table"](info_data)
        
        upstreams = [u for u in stream.upstreams if u]
        if upstreams:
            ctx["put_markdown"]("## 上游流")
            upstream_data = [["序号", "流名称", "流类型", "执行函数", "操作"]]
            for i, upstream in enumerate(upstreams, 1):
                upstream_id = str(hash(upstream))
                upstream_name = getattr(upstream, "name", "") or "未命名"
                upstream_type = upstream.__class__.__name__
                upstream_func = _get_func_info(upstream) if upstream_type in FUNC_ATTR_STREAM_TYPES else "-"
                view_btn = ctx["put_buttons"](
                    [{"label": f"查看 {upstream_id[:8]}...", "value": upstream_id}],
                    onclick=lambda sid=upstream_id: _view_stream_by_id(ctx, sid)
                )
                upstream_data.append([
                    str(i),
                    upstream_name,
                    upstream_type,
                    upstream_func,
                    view_btn
                ])
            ctx["put_table"](upstream_data)
        
        if stream.downstreams:
            ctx["put_markdown"]("## 下游流")
            downstream_data = [["序号", "流名称", "流类型", "执行函数", "操作"]]
            for i, downstream in enumerate(stream.downstreams, 1):
                downstream_id = str(hash(downstream))
                downstream_name = getattr(downstream, "name", "") or "未命名"
                downstream_type = downstream.__class__.__name__
                downstream_func = _get_func_info(downstream) if downstream_type in FUNC_ATTR_STREAM_TYPES else "-"
                view_btn = ctx["put_buttons"](
                    [{"label": f"查看 {downstream_id[:8]}...", "value": downstream_id}],
                    onclick=lambda sid=downstream_id: _view_stream_by_id(ctx, sid)
                )
                downstream_data.append([
                    str(i),
                    downstream_name,
                    downstream_type,
                    downstream_func,
                    view_btn
                ])
            ctx["put_table"](downstream_data)
        
        ctx["put_markdown"]("## 缓存数据")
        if stream.is_cache and stream.cache:
            try:
                cache_items = list(stream.cache.items())
                recent_items = cache_items[-3:] if len(cache_items) >= 3 else cache_items
                
                if recent_items:
                    cache_table = [["序号", "时间戳", "数据预览"]]
                    for i, (timestamp, value) in enumerate(reversed(recent_items), 1):
                        from datetime import datetime
                        if isinstance(timestamp, datetime):
                            ts_str = timestamp.strftime("%H:%M:%S")
                        else:
                            ts_str = str(timestamp)
                        
                        if isinstance(value, dict):
                            value_str = str(value)[:100]
                            if len(str(value)) > 100:
                                value_str += "..."
                        elif isinstance(value, (list, tuple)):
                            value_str = f"[{len(value)}项] " + str(value)[:80]
                            if len(str(value)) > 80:
                                value_str += "..."
                        else:
                            value_str = str(value)[:100]
                            if len(str(value)) > 100:
                                value_str += "..."
                        
                        cache_table.append([str(i), ts_str, value_str])
                    
                    ctx["put_table"](cache_table)
                    ctx["put_markdown"](f"*显示最新{len(recent_items)}条数据，共{len(cache_items)}条缓存*")
                else:
                    ctx["put_text"]("缓存为空")
            except Exception as e:
                ctx["put_text"](f"读取缓存失败: {str(e)}")
        else:
            ctx["put_text"]("未启用缓存或缓存为空")
        
        ctx["put_markdown"]("## 实时数据")
        ctx["put_html"](
            f'<iframe src="/{stream_id}" style="width:100%;height:40vh;border:1px solid #e5e7eb;border-radius:12px;background:#fff;"></iframe>'
        )


def _view_stream_by_id(ctx, stream_id):
    """根据流ID查找并展示流详情"""
    for stream in ctx["Stream"].instances():
        if str(hash(stream)) == str(stream_id):
            _show_stream_detail_popup(ctx, stream, "流详情")
            return
    ctx["toast"](f"流不存在: {stream_id}", color="error")


def stream_click(ctx, streamname):
    ctx["put_markdown"]("> You click `%s` stream,show records:" % streamname)
    matched = [s for s in ctx["Stream"].instances() if s.name == streamname]
    if not matched:
        ctx["toast"](f"流不存在或尚未初始化: {streamname}", color="warning")
        return
    s = matched[0]
    _show_stream_detail_popup(ctx, s, "流详情")


# ---- Auth ----
async def basic_auth(
    verify_func: Callable[[str, str], bool],
    secret: Union[str, bytes],
    *,
    expire_days=7,
    token_name='pywebio_auth_token',
    decode_signed_value,
    create_signed_value,
    get_localstorage,
    set_localstorage,
    input_group,
    input,
    PASSWORD,
    toast,
    log,
):
    """Auth helper with dependency injection."""
    token = await get_localstorage(token_name)
    username = decode_signed_value(secret, token_name, token, max_age_days=expire_days)
    if username:
        username = username.decode('utf8')

    if not token or not username:
        while True:
            user = await input_group('登录', [
                input('用户名', name='username'),
                input('密码', type=PASSWORD, name='password'),
            ])
            username = user['username']
            ok = verify_func(username, user['password'])
            ok >> log
            if ok:
                signed = create_signed_value(secret, token_name, username).decode('utf-8')
                set_localstorage(token_name, signed)
                break
            toast('用户名或密码错误', color='error')

    return username
