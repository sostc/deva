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


def stream_click(ctx, streamname):
    ctx["put_markdown"]("> You click `%s` stream,show records:" % streamname)
    matched = [s for s in ctx["Stream"].instances() if s.name == streamname]
    if not matched:
        ctx["toast"](f"流不存在或尚未初始化: {streamname}", color="warning")
        return
    s = matched[0]
    ctx["popup"]("Stream Viewer", [ctx["put_html"](f'<iframe src="{hash(s)}" style="width:100%;height:80vh;border:none;"></iframe>')], size="large")


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
