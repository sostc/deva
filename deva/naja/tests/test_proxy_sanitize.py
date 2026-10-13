"""启动期「代理环境卫生」—— 防止失效的本地代理劫持大模型请求。

背景（2026-10-13）：托盘「一键总结」突然全部失败，日志里是
``openai.APIConnectionError: Connection error.``。排查发现请求被送进了
``HTTP_PROXY=http://127.0.0.1:53631`` —— 一个随集成终端会话生灭、当时
已无人监听的沙箱代理。``openai`` / ``httpx`` 默认 ``trust_env=True``，
于是**所有**大模型请求都撞在这个死端口上，而代码本身毫无问题。

修法：启动入口 ``sanitize_proxy_env()`` 剔除「回环地址 + 端口无人监听」
的代理变量；真实代理（Surge / Clash 在监听）一律保留。
"""

import socket

import pytest

from deva.naja.infra.runtime.daemon import _proxy_url_target, sanitize_proxy_env


@pytest.fixture
def live_port():
    """开一个临时本地监听端口，模拟「真实存在、可连接的代理」。

    只 listen 不 accept —— TCP 三次握手由内核完成，``connect()`` 即成功。
    """
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    try:
        yield srv.getsockname()[1]
    finally:
        srv.close()


# ── ① 代理 URL 解析 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("http://127.0.0.1:53631", ("127.0.0.1", 53631)),
    ("127.0.0.1:6152", ("127.0.0.1", 6152)),          # 省略 scheme
    ("http://localhost:7890", ("localhost", 7890)),
    ("socks5://127.0.0.1:6153", ("127.0.0.1", 6153)),
    ("http://8.8.8.8:8080", ("8.8.8.8", 8080)),
    ("", (None, None)),
    ("http://127.0.0.1", ("127.0.0.1", None)),        # 无端口 → 不探测、保留
])
def test_proxy_url_target(raw, expected):
    assert _proxy_url_target(raw) == expected


# ── ② 死代理必须被剔除 ──────────────────────────────────────────────────


def test_dead_loopback_proxy_is_removed():
    env = {"HTTP_PROXY": "http://127.0.0.1:53631",
           "https_proxy": "http://127.0.0.1:9"}
    removed = sanitize_proxy_env(env)
    assert set(removed) == {"HTTP_PROXY", "https_proxy"}
    assert env == {}          # 必须从环境里真正删掉，否则 copy 给子进程照样带毒


# ── ③ 活代理必须保留（假警报比不报警更伤）────────────────────────────────


def test_live_loopback_proxy_is_kept(live_port):
    env = {"HTTP_PROXY": f"http://127.0.0.1:{live_port}"}
    assert sanitize_proxy_env(env) == {}
    assert "HTTP_PROXY" in env


def test_non_loopback_proxy_is_never_touched():
    """非回环代理一律尊重用户设置，不做探测。"""
    env = {"HTTPS_PROXY": "http://8.8.8.8:8080",
           "ALL_PROXY": "socks5://1.2.3.4:1080"}
    assert sanitize_proxy_env(env) == {}
    assert len(env) == 2


# ── ④ 无副作用 / 幂等 ───────────────────────────────────────────────────


def test_clean_env_is_noop():
    assert sanitize_proxy_env({}) == {}


def test_idempotent():
    env = {"HTTP_PROXY": "http://127.0.0.1:53631"}
    assert set(sanitize_proxy_env(env)) == {"HTTP_PROXY"}
    assert sanitize_proxy_env(env) == {}


# ── ⑤ 失败提示要能自证 ──────────────────────────────────────────────────


def test_error_hint_classifies_connection_error():
    tray = pytest.importorskip("deva.naja.infra.ui.menu_bar_tray")
    hint = tray.MenuBarTray._summarize_error_hint(
        Exception("Connection error."))
    assert "代理" in hint


def test_error_hint_classifies_auth_and_quota():
    tray = pytest.importorskip("deva.naja.infra.ui.menu_bar_tray")
    hint = tray.MenuBarTray._summarize_error_hint
    assert "Key" in hint(Exception("Error code: 401 - Unauthorized"))
    assert "额度" in hint(Exception("402 Insufficient Balance"))
    assert hint(Exception("something totally unexpected")) == "发生错误"
