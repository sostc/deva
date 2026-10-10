#!/usr/bin/env python3
"""回归：bus.py 的 _infer_sender_from_stack 从 inspect.stack() 改为 sys._getframe()。

验证：
  1) 类方法 / 普通函数场景下推断结果与旧实现一致；
  2) 新实现更快（inspect.stack 会为每帧读取源码上下文）。

跑法（必须清环境）：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_bus_sender_inference.py
"""
import importlib
import inspect
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# 注意：deva.core 包把 `bus` 这个名字重绑定到了 Topic 对象上，
# `from deva.core import bus` 拿到的不是子模块，必须走 importlib。
B = importlib.import_module("deva.core.bus")


# ── 旧实现（改前版本）────────────────────────────────────────────────
def _old_infer_from_stack():
    try:
        stack = inspect.stack()
        for frame in stack[2:]:
            filename = frame.filename
            base = os.path.basename(filename)
            if base in B._INTERNAL_SENDER_FILES:
                continue
            if "site-packages" in filename and "deva" not in filename:
                continue
            fn = frame.function
            locals_ = frame.frame.f_locals
            self_obj = locals_.get("self")
            if self_obj is not None:
                return f"{self_obj.__class__.__name__}.{fn}"
            cls_obj = locals_.get("cls")
            if cls_obj is not None and hasattr(cls_obj, "__name__"):
                return f"{cls_obj.__name__}.{fn}"
            return fn
    except Exception:
        pass
    return B._default_bus_sender()


def _old_normalize(payload):
    if isinstance(payload, dict):
        out = dict(payload)
        if not out.get("sender"):
            out["sender"] = _old_infer_from_stack()
        if not out.get("ts"):
            out["ts"] = time.time()
        return out
    return payload


class ProbeNew:
    """经 _normalize_bus_payload 走一遍，模拟真实 bus.emit 路径。"""

    def call(self):
        return B._normalize_bus_payload({"message": "x"})["sender"]


class ProbeOld:
    def call(self):
        return _old_normalize({"message": "x"})["sender"]


def plain_call_new():
    return B._normalize_bus_payload({"message": "x"})["sender"]


def plain_call_old():
    return _old_normalize({"message": "x"})["sender"]


def main():
    pnew, pold = ProbeNew(), ProbeOld()

    new_method = pnew.call()
    old_method = pold.call()
    print(f"1) 类方法  新={new_method!r}  旧={old_method!r}")
    assert new_method == "ProbeNew.call", new_method
    assert old_method == "ProbeOld.call", old_method
    # 方法名（帧选择的正确性）一致
    assert new_method.split(".")[-1] == old_method.split(".")[-1] == "call"

    new_func = plain_call_new()
    old_func = plain_call_old()
    print(f"2) 普通函数 新={new_func!r}  旧={old_func!r}")
    assert new_func == "plain_call_new", new_func
    assert old_func == "plain_call_old", old_func

    # 3) 带 sender 的 payload 不被覆盖（新旧一致）
    assert B._normalize_bus_payload({"sender": "me"})["sender"] == "me"
    print("3) 显式 sender 不被覆盖 OK")

    # 4) 性能：新实现应显著快于旧的 inspect.stack()
    N = 20000
    t = time.perf_counter()
    for _ in range(N):
        pold.call()
    t_old = time.perf_counter() - t

    t = time.perf_counter()
    for _ in range(N):
        pnew.call()
    t_new = time.perf_counter() - t

    print(f"4) {N} 次调用：旧={t_old:.4f}s  新={t_new:.4f}s  加速={t_old / max(t_new, 1e-9):.1f}x")
    assert t_new < t_old, (t_new, t_old)

    print("\nALL PASS")


if __name__ == "__main__":
    main()
