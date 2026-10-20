"""守卫：通知手机号**不许再出现在仓库里** —— 本仓库是公开的。

背景（2026-10-20 实测）：

``github.com/sostc/deva`` 的 ``private`` 是 ``false``，而手机号曾硬编码在
8 个 .py（ai_daily_report / ai_knowledge_injector / unified_article_monitor /
wake_sync_handlers / news.digest / daily_review / examples.search_sql /
skills.naja-daily-review.agent）与 2 个根目录文档（MEMORY.md / TOOLS.md）里，
等于长期公开暴露。

修法是收敛到 ``deva/naja/infra/notify_recipient.py`` 一个入口，号码从
环境变量 / 本机 ``~/.naja/notify.json`` / Naja 配置取。但**改一次没用** ——
下次谁顺手在代码里写个号码，又泄露了。所以本守卫把「写回号码」变成守卫失败：

    A. 扫**已入库**文件（``git ls-files``），断言不含真实号码；
    B. 扫描文件数必须 >= MIN_SCAN —— 防止扫描源失效导致「0 文件 → 0 命中 → 假绿」；
    C. 统一入口在三处来源都为空时必须返回 ``""`` —— **不许拿硬编码兜底**
       （把「没配置」伪装成「配置好了」是本项目反复踩的静默失效）。

负向注入把 A/B/C 各破坏一次，确认断言真的会红。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECIPIENT_PATH = ROOT / "deva/naja/infra/notify_recipient.py"

#: 扫描文件数下限（❗同 fleet_registry 守卫：没有这条，扫描源一失效就全绿）
MIN_SCAN = 100

#: 只扫这些后缀（二进制/图片扫不出文本，也没意义）
SCAN_SUFFIXES = (".py", ".md", ".yaml", ".yml", ".json", ".sh", ".txt", ".toml")

#: 这些路径即便含号码也不算泄露（守卫自己要用模式串做检测）
SCAN_EXCLUDE = ("scripts/verify/verify_no_hardcoded_phone.py",)

#: 本机号码来源（用于拿到「真实号码」做精确匹配）
LOCAL_FILE = Path.home() / ".naja" / "notify.json"

#: 未配置真实号码时的退化模式：疑似中国大陆手机号。
#: ❗只在拿不到真实号码时启用 —— 宽松正则会误报，别让它当常态判据。
PHONE_LIKE_RE = re.compile(r"(?<!\d)(?:\+?86)?1[3-9]\d{9}(?!\d)")


def _known_phones() -> list:
    """拿「真实号码」：本机配置 + 环境变量。拿不到返回空（退化为正则）。"""
    phones = []
    env_phone = os.environ.get("NAJA_NOTIFY_PHONE", "").strip()
    if env_phone:
        phones.append(env_phone)
    try:
        import json
        if LOCAL_FILE.exists():
            data = json.loads(LOCAL_FILE.read_text(encoding="utf-8") or "{}")
            phone = str((data or {}).get("phone") or "").strip()
            if phone:
                phones.append(phone)
    except Exception:
        pass
    return phones


def _scan_files() -> list:
    """列出**已入库**的待扫文件（未入库的文件不算「泄露到公开仓库」）。"""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=30,
        )
        names = [l.strip() for l in (out.stdout or "").splitlines() if l.strip()]
    except Exception:
        names = []
    return [n for n in names
            if n.endswith(SCAN_SUFFIXES) and not any(n.startswith(e) for e in SCAN_EXCLUDE)]


def _load_recipient():
    """重加载被测模块（❗不许用 import：会拿到 sys.modules 里的旧对象）。"""
    spec = importlib.util.spec_from_file_location("_notify_recipient_under_test",
                                                 RECIPIENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _check_a_scan(fails: list) -> int:
    """A：已入库文件里不许出现真实号码。"""
    files = _scan_files()
    if len(files) < MIN_SCAN:
        fails.append(f"B. 扫描到的入库文件只有 {len(files)} 个（下限 {MIN_SCAN}）—— "
                     "扫描源失效，结果是假绿")
        return len(files)

    phones = _known_phones()
    use_regex = not phones
    hits = []
    for name in files:
        path = ROOT / name
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if use_regex:
                if PHONE_LIKE_RE.search(line):
                    hits.append(f"{name}:{i}")
            else:
                for p in phones:
                    if p in line:
                        hits.append(f"{name}:{i}")
                        break
    for h in hits[:20]:
        fails.append(f"A. 仓库里又出现了通知手机号（公开仓库！）：{h}")
    if use_regex:
        # 退化模式下只警告：拿不到真实号码时宁可漏报也不刷屏误报
        print(f"  ⚠️ 本机未配置号码，退化用宽松正则扫描（命中 {len(hits)} 处，仅供参考）")
    return len(files)


def _check_c_no_fallback(fails: list):
    """C：三处来源都为空时必须返回空字符串，不许拿硬编码兜底。"""
    mod = _load_recipient()
    with tempfile.TemporaryDirectory() as td:
        mod.reset_cache()
        mod.LOCAL_FILE = Path(td) / "no_such_notify.json"
        saved_env = os.environ.pop("NAJA_NOTIFY_PHONE", None)
        try:
            # 内存配置也清掉：monkeypatch 掉 naja config 的读取
            original = mod._read_naja_config
            mod._read_naja_config = lambda: ""
            try:
                got = mod.get_notify_phone(refresh=True)
            finally:
                mod._read_naja_config = original
        finally:
            if saved_env is not None:
                os.environ["NAJA_NOTIFY_PHONE"] = saved_env
            mod.LOCAL_FILE = LOCAL_FILE
            mod.reset_cache()
    if got != "":
        fails.append(f"C. 三处来源都为空时 get_notify_phone() 返回了 {got!r} —— "
                     "又拿硬编码兜底了（把「没配置」伪装成「配置好了」）")


def _check_d_normalize(fails: list):
    """D：号码归一化必须把「+86 前缀」和「裸 11 位」判为同一个号码。

    ❗漏了这条，iMessage 白名单会把本人发来的消息当成别人的（写法不同而已）。
    """
    mod = _load_recipient()
    norm = mod.normalize_phone
    pairs = (("+8613800000000", "13800000000"), ("+86 138 0000 0000", "13800000000"))
    for a, b in pairs:
        if norm(a) != norm(b):
            fails.append(f"D. normalize_phone 没把 {a!r} 与 {b!r} 归一到同一个号码"
                         f"（得到 {norm(a)!r} / {norm(b)!r}）")
    if norm("") != "":
        fails.append("D. normalize_phone('') 应返回空字符串")


def _all_checks() -> list:
    fails = []
    _check_a_scan(fails)
    _check_c_no_fallback(fails)
    _check_d_normalize(fails)
    return fails


INJECTIONS = (
    {
        # ❗占位符 {phone} 在运行时替换成**真实号码**：守卫只认真实号码，
        # 拿占位号码注入当然扫不到 —— 那是「守卫看起来在守其实没守」。
        "name": "A. 代码里写回硬编码号码（最典型的复辟）",
        "target": "deva/naja/news/digest.py",
        "old": '    phone = get_notify_phone()',
        "new": '    phone = "{phone}"',
        "reload": False,
    },
    {
        # ❗注入打的是**守卫自己**的源码：改磁盘不影响已加载模块，
        # 必须 spec_from_file_location 重载一份再跑，否则永远「抓不到」。
        "name": "B. 扫描源改坏（0 文件 → 0 命中 → 假绿）",
        "target": "scripts/verify/verify_no_hardcoded_phone.py",
        "old": '    return [n for n in names\n            if n.endswith(SCAN_SUFFIXES)'
               ' and not any(n.startswith(e) for e in SCAN_EXCLUDE)]',
        "new": '    return []',
        "reload": True,
    },
    {
        "name": "C. 统一入口偷偷加硬编码兜底",
        "target": "deva/naja/infra/notify_recipient.py",
        "old": '    _cache, _cache_checked = phone, True',
        "new": '    phone = phone or "{phone}"\n'
               '    _cache, _cache_checked = phone, True',
        "reload": False,
    },
    {
        "name": "D. 归一化漏剥国家码（+86 与裸号判成两个人）",
        "target": "deva/naja/infra/notify_recipient.py",
        "old": '    if s.startswith("86") and len(s) == len("86") + 11:\n        s = s[2:]',
        "new": '    if False:\n        s = s[2:]',
        "reload": False,
    },
)


def _reload_self_checks():
    """重载**本守卫**后再跑一遍检查（注入 B 打的是本文件）。"""
    self_path = Path(__file__).resolve()
    spec = importlib.util.spec_from_file_location("_phone_guard_under_test", self_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod._all_checks()


def run_injections() -> int:
    caught = 0
    phones = _known_phones()
    real_phone = phones[0] if phones else ""
    if not real_phone:
        print("  ⚠️ 本机没配号码，注入 A/C 无法构造真实号码，跳过")
    for inj in INJECTIONS:
        if "{phone}" in inj["new"] and not real_phone:
            continue
        target = ROOT / inj["target"]
        original = target.read_text(encoding="utf-8")
        if inj["old"] not in original:
            print(f"  ⚠️ 锚点未命中，跳过：{inj['name']}")
            continue
        try:
            target.write_text(
                original.replace(inj["old"], inj["new"].format(phone=real_phone), 1),
                encoding="utf-8")
            fails = _reload_self_checks() if inj["reload"] else _all_checks()
        finally:
            target.write_text(original, encoding="utf-8")
        if fails:
            caught += 1
            print(f"  ✅ 捕获：{inj['name']} → {fails[0][:70]}")
        else:
            print(f"  ❌ 漏掉：{inj['name']}（断言没生效！）")
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        print("── 负向注入：故意破坏，确认守卫会红 ──")
        caught = run_injections()
        total = len(INJECTIONS)
        print(f"\n注入捕获 {caught}/{total}")
        return 0 if caught == total else 1

    fails = _all_checks()
    if fails:
        for f in fails:
            print(f"❌ {f}")
        return 1
    phones = _known_phones()
    print(f"✅ 已入库文件里没有通知手机号（精确匹配 {len(phones)} 个已知号码）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
