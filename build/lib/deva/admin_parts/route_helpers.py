"""Small route helper utilities extracted from admin.py."""


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


def stream_click(ctx, streamname):
    ctx["put_markdown"]("> You click `%s` stream,show records:" % streamname)
    matched = [s for s in ctx["Stream"].instances() if s.name == streamname]
    if not matched:
        ctx["toast"](f"流不存在或尚未初始化: {streamname}", color="warning")
        return
    s = matched[0]
    ctx["popup"]("Stream Viewer", [ctx["put_html"](f'<iframe src="{hash(s)}" style="width:100%;height:80vh;border:none;"></iframe>')], size="large")
