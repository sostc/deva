"""Admin modularized components."""

# Core modules
from . import runtime
from . import auth_routes
from . import contexts
from . import main_ui
from . import menus

# Feature modules
from . import tasks
from . import ai
from . import document
from . import monitor
from . import tables
from . import config
from . import follow
from . import browser

__all__ = [
    # Core
    'runtime',
    'auth_routes',
    'contexts',
    'main_ui',
    'menus',
    # Features
    'tasks',
    'ai',
    'document',
    'monitor',
    'tables',
    'config',
    'follow',
    'browser',
    # 兼容导出（见下方 watch_topic）
    'watch_topic',
]


# --- 兼容导出 -----------------------------------------------------------
# deva/admin.py 是与本包同名的遗留单体模块。Python 里同名包（目录）优先于
# 模块（文件），所以 `from deva.admin import watch_topic` 只会解析到本
# __init__.py，永远拿不到 admin.py 里的同名函数 —— 定时任务
# 「新华社重要新闻」就是这样一直报 cannot import name 的。
# 这里把仍被外部引用的公共函数重新导出，实现直接委托给 llm_service，
# 不加载 admin.py，避免把它的 UI 注册与调度器副作用拖进定时任务进程。


def _llm_ctx():
    """构造 llm_service.get_gpt_response 需要的上下文。

    定时任务跑在没有 PyWebIO 会话的环境里，所以 toast / put_out 一律静默
    降级成日志：显示层不该有能力把后台任务拖崩。
    """
    import traceback as _traceback

    import requests as _requests
    from openai import AsyncOpenAI as _AsyncOpenAI

    from deva import NB, log
    from deva.core.bus import warn

    try:
        from deva.llm.worker_runtime import run_ai_in_worker
    except Exception:
        run_ai_in_worker = None

    def _put_out(msg, *args, **kwargs):
        str(msg) >> log

    def _toast(msg, *args, **kwargs):
        try:
            from pywebio.output import toast
            toast(msg, *args, **kwargs)
        except Exception:
            str(msg) >> log

    return {
        'NB': NB,
        'warn': warn,
        'log': log,
        'requests': _requests,
        'AsyncOpenAI': _AsyncOpenAI,
        'put_out': _put_out,
        'toast': _toast,
        'traceback': _traceback,
        'run_ai_in_worker': run_ai_in_worker,
    }


async def watch_topic(topic):
    """关注一个话题，返回 6 条一句话新闻（每行：图标 + 粗体概括词 —— 摘要）。"""
    from . import llm_service as _llm_service

    full_prompt = (
        f" 获取{topic},要求返回的内容每一行都是一个一句话，开头用一个和内容对应的图标，"
        "然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，再后面是一句话摘要，"
        "用破折号区隔开。每行一个内容，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。"
    )
    return await _llm_service.get_gpt_response(
        _llm_ctx(), full_prompt, model_type="kimi"
    )
