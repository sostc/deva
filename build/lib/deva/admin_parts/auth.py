from typing import Callable, Union


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
    """Auth helper extracted from admin.py with dependency injection."""
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
