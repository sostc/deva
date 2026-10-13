"""守卫专用沙箱：让 NB 落到一个**临时 SQLite**，而不是 ``~/.deva/nb.sqlite``。

为什么需要这个
--------------
``NB(name)`` 由 ``global_namespace`` 缓存，**实例化时才**读环境变量
``DEVA_DB_PATH`` 决定落盘位置（``deva/core/store.py``）。也就是说：

* 环境变量必须在**任何一次 ``NB(...)`` 之前**设置好；
* 一旦用了真实账号（哪怕叫 ``T_WIRING_GUARD`` 这种一看就是测试的名字），
  守卫跑一遍就会把假持仓、假价格写进生产库。

真实踩过：``verify_t_rotation_core.py`` 跑完，真实库里多出
``T_ROTATION_TEST`` 账户的 588200 持仓 9000 份 @3350.25 —— 那是守卫构造的
假价格序列，却跟真钱躺在同一个 sqlite 里。

用法
----
在脚本**最顶部**（``sys.path`` 处理好之后、任何 deva 导入之前）::

    sys.path.insert(0, VERIFY_DIR)          # scripts/verify
    from guard_sandbox import isolate_guard_db
    isolate_guard_db()

适用范围
--------
只给**自造数据、且确实会写**的守卫用。
依赖真实数据的守卫（如 ``verify_focus_advisor.py`` 要读真实持仓推导供应链）
不能换库——它会因为读不到持仓而失去守护意义；那一类沿用既有的
「临时表名 / 临时账户 + 跑完清理 + 真实表前后比对」约定。
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import warnings

DEV_DB_PATH_ENV = "DEVA_DB_PATH"
DEFAULT_DEV_DB = "~/.deva/nb.sqlite"

_FLAG = "_GUARD_SANDBOX_ISOLATED"


def real_db_path() -> str:
    """生产库路径（``~/.deva/nb.sqlite``）。"""
    return os.path.expanduser(DEFAULT_DEV_DB)


def isolate_guard_db(prefix: str = "naja_guard_") -> str:
    """把 NB 的落盘位置重定向到一个临时 sqlite。

    Returns:
        str: 实际使用的 sqlite 路径

    Raises:
        RuntimeError: 已经连到别的库（重复调用且换了目标）
    """
    if os.environ.get(_FLAG) == "1":
        # 幂等：同一个进程里重复调用不再新建目录
        return os.environ[DEV_DB_PATH_ENV]

    # 晚了就晚了 —— 但必须喊出来，否则"看起来隔离了其实没有"。
    if "deva.core.namespace" in sys.modules:
        warnings.warn(
            "isolate_guard_db() 在 deva.core.namespace 导入之后才调用："
            "若此前已有 NB(...) 建过对象，它会指向旧库。"
            "请把调用挪到脚本最顶部。",
            RuntimeWarning,
            stacklevel=2,
        )

    target_dir = os.environ.get("NAJA_GUARD_TMPDIR") or None
    tmpdir = (
        os.path.join(target_dir, prefix + str(os.getpid()))
        if target_dir
        else __import__("tempfile").mkdtemp(prefix=prefix)
    )
    os.makedirs(tmpdir, exist_ok=True)
    db_path = os.path.join(tmpdir, "nb.sqlite")

    os.environ[DEV_DB_PATH_ENV] = db_path
    os.environ[_FLAG] = "1"

    # 跑完抹掉痕迹。清理失败无所谓（只是临时文件），别让它掩盖守卫结果。
    try:
        atexit.register(shutil.rmtree, tmpdir, True)
    except Exception:  # pragma: no cover
        pass

    return db_path


def is_isolated() -> bool:
    """当前进程是否已重定向到临时库。"""
    return os.environ.get(_FLAG) == "1" and os.environ.get(DEV_DB_PATH_ENV) != real_db_path()


__all__ = ["isolate_guard_db", "is_isolated", "real_db_path", "DEV_DB_PATH_ENV"]
