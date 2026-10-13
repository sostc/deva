"""守卫：日志格式器必须保留异常堆栈。

背景（真实事故）：
    `/banditadmin` 页面报 "Unhandled error in pywebio app"，但 naja.log 里
    只有这一行消息，**没有任何 traceback**，导致线上错误完全不可诊断。
    根因是 ColorfulFormatter / PlainFormatter 都重写了 `Formatter.format()`，
    而基类中「把 record.exc_info 渲染并追加」的逻辑正好在被覆盖的那段里。

本守卫锁两件事：
    1. 正向：`logger.exception()` / `logger.error(exc_info=True)` 的输出里
       必须同时包含消息与 traceback 关键帧。
    2. 区分度（负向）：把 `_append_exception_text` 还原成恒等函数（等价于修复前
       的行为）后，堆栈必须消失 —— 否则说明断言抓错了东西。
    3. 不回归：无异常的普通日志行不得被追加换行/堆栈。

用法：
    python3 scripts/verify/verify_log_traceback.py [--strict]
"""

import importlib.util
import logging
import os
import sys
import io

MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "deva", "naja", "infra", "log", "colorful_logger.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("_naja_colorful_logger_standalone", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _emit(formatter, with_exc: bool) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger("verify_log_traceback.%s" % id(formatter))
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    if with_exc:
        try:
            raise ValueError("boom-from-guard")
        except ValueError:
            logger.exception("Unhandled error in pywebio app")
    else:
        logger.info("普通日志行")
    return stream.getvalue()


def main() -> int:
    if not os.path.exists(MODULE_PATH):
        print(f"❌ 找不到 {MODULE_PATH}")
        return 1

    mod = _load_module()
    failures = []

    formatters = [
        ("PlainFormatter", mod.PlainFormatter(show_timestamp=True)),
        ("ColorfulFormatter(color)", mod.ColorfulFormatter(use_color=True, show_timestamp=True)),
        ("ColorfulFormatter(plain)", mod.ColorfulFormatter(use_color=False, show_timestamp=True)),
    ]

    # ---- 1. 正向：堆栈必须在 ----
    for name, fmt in formatters:
        out = _emit(fmt, with_exc=True)
        if "Unhandled error in pywebio app" not in out:
            failures.append(f"[{name}] 消息本身丢失")
        if "Traceback (most recent call last)" not in out:
            failures.append(f"[{name}] traceback 丢失（这正是被修掉的缺陷）")
        if "boom-from-guard" not in out:
            failures.append(f"[{name}] 异常内容丢失")
        if "ValueError" not in out:
            failures.append(f"[{name}] 异常类型丢失")

    # ---- 2. 不回归：普通行不得被污染 ----
    for name, fmt in formatters:
        out = _emit(fmt, with_exc=False)
        if "Traceback" in out:
            failures.append(f"[{name}] 无异常的日志行被追加了堆栈")
        if out.endswith("\n\n"):
            failures.append(f"[{name}] 无异常的日志行被追加了多余换行")
        if "普通日志行" not in out.rstrip("\n"):
            failures.append(f"[{name}] 普通日志消息丢失")

    # ---- 3. 区分度：注入「修复前行为」后堆栈必须消失 ----
    print("— 负向验证（注入修复前行为）—")
    original = mod._append_exception_text
    try:
        mod._append_exception_text = lambda message, record: message
        dropped = 0
        for name, fmt in formatters:
            out = _emit(fmt, with_exc=True)
            if "Traceback (most recent call last)" not in out:
                dropped += 1
                print(f"  ✅ [{name}] 还原旧写法后堆栈如期消失（守卫有区分度）")
            else:
                failures.append(f"[{name}] 还原旧写法后堆栈仍在 → 守卫断言没有区分度")
        if dropped == 0:
            failures.append("三个格式器都无法复现缺陷 → 用例没有区分度")
    finally:
        mod._append_exception_text = original

    # ---- 4. 还原后必须重新可见 ----
    restored = _emit(formatters[0][1], with_exc=True)
    if "Traceback (most recent call last)" not in restored:
        failures.append("还原后堆栈不可见 → 守卫状态泄漏")

    print()
    if failures:
        print("❌ 守卫失败：")
        for f in failures:
            print("   -", f)
        return 1
    print("✅ 通过：日志格式器保留异常堆栈，且普通日志行未被污染")
    return 0


if __name__ == "__main__":
    code = main()
    if "--strict" in sys.argv and code != 0:
        sys.exit(code)
    sys.exit(code)
