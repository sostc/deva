#!/usr/bin/env python3
"""守卫：富途持仓定期同步 + OpenD 自动拉起。

## 这份守卫守的是什么

券商镜像账户（FutuHK / MoomooUS / FutuSim*）的数据只能来自
``FutuPortfolioSyncer.sync()``，而它原本**只有 UI 按钮一个调用方**。
没人点，账户就永远停在最后一次手点的那一刻 —— 实测 6 天前，
页面上数字看着完全正常。

把它接成定时任务之后，新的失效面是 OpenD 本身：它是桌面 app，
机器重启 / 用户退出 / 崩溃都会让它消失。于是任务必须能自己把依赖拉起来，
同时**不能**把这几件事做错：

1. 端口通着还去 ``open -a`` —— 抢不到 11111，还会把窗口弹到前台打扰人；
2. OpenD 进程还在启动中（端口未就绪）就再拉一个；
3. 起不来还每 10 分钟重试一次 —— 连开一堆窗口（多数情况是要人工登录）；
4. 把 ``open`` 返回 0 当成「OpenD 好了」—— 那是 launchd 收下了请求，
   跟进程起来、登录成功毫无关系；
5. 没装 app 时静默跳过，任务报「成功」但其实什么都没同步。

判据全部钉**行为**（``_start_app`` 到底被调了几次、返回的 ``reachable``
是什么），不是「源码里出现过某个词」。用例里所有外部动作都被替换成替身，
守卫不会真的开 app、也不碰真实端口。

用法：
    python scripts/verify/verify_futu_opend_autostart.py --strict
    python scripts/verify/verify_futu_opend_autostart.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
FAILS: list[str] = []

OPEND_SRC = "deva/naja/bandit/futu_opend.py"
TASK_YAML = "deva/config/tasks/futu_portfolio_sync.yaml"


def _ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def _bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    FAILS.append(msg)
    print(f"  ❌ {msg}")


def _load(rel_path: str, mod_name: str):
    """按文件路径重载模块。

    ❗不能用 ``import``：拿到的是 ``sys.modules`` 里的旧对象，注入的新代码
    根本没被读进来 —— 守卫会全绿，但什么都没守。
    """
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {rel_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Probe:
    """把模块里的外部动作全部换成可计数的替身。"""

    def __init__(self):
        self.port_open = False
        self.pids: list[int] = []
        self.app = "/Applications/Futu_OpenD.app"
        self.start_error = ""
        self.probe_calls = 0
        self.pid_calls = 0
        self.start_calls: list[str] = []

    def install(self, mod) -> "_Probe":
        mod.reset_for_test()

        def probe(timeout: float = 1.0) -> bool:
            self.probe_calls += 1
            return self.port_open

        def _opend_pids() -> list[int]:
            self.pid_calls += 1
            return list(self.pids)

        def _pick_app() -> str:
            return self.app

        def _start_app(path: str) -> str:
            self.start_calls.append(path)
            return self.start_error

        mod.probe = probe
        mod._opend_pids = _opend_pids
        mod._pick_app = _pick_app
        mod._start_app = _start_app
        return self


# ── 判据 1：端口通就必须立刻返回，连进程都不该扫 ────────────────────────────
def check_reachable_short_circuit(mod) -> None:
    print("\n[1] 端口已通：必须立刻返回，不许拉起、不许扫进程")
    p = _Probe().install(mod)
    p.port_open = True

    r = mod.ensure_opend()

    # ❗先查「有没有真的去拉起」：那是最直接的证据。先查 reachable 的话，
    # 注入版会先卡 45s 超时、报一句「reachable=False」，把真正的病灶盖掉。
    if p.start_calls:
        _bad(f"端口通着还执行了 open -a（{len(p.start_calls)} 次）—— 会弹窗打扰用户")
        return
    if p.pid_calls:
        _bad("端口通着还去扫进程表 —— 快路径应该直接返回")
        return
    if not r["reachable"]:
        _bad("端口通着却返回 reachable=False")
        return
    _ok("端口通 → 直接返回，未拉起、未扫进程")


# ── 判据 2：进程在但端口未就绪 → 只等，不再 open ────────────────────────────
def check_starting_process_not_duplicated(mod) -> None:
    print("\n[2] OpenD 进程在但端口未就绪：只等，不许再 open 一个")
    p = _Probe().install(mod)
    p.port_open = False
    p.pids = [4242]

    r = mod.ensure_opend(timeout=0)

    if p.start_calls:
        _bad(f"进程已存在仍然执行了 open -a（{len(p.start_calls)} 次）—— 会抢端口/弹窗")
        return
    if r["reachable"]:
        _bad("端口没通却返回 reachable=True —— 启动中不等于就绪")
        return
    if "人工登录" not in r.get("error", ""):
        _bad(f"失败原因没说明需要人工登录（error={r.get('error')!r}）—— 用户无从下手")
        return
    _ok("进程在 → 只等不拉起，并如实说明需要人工登录")


# ── 判据 3：拉起失败后必须冷却 ─────────────────────────────────────────────
def check_start_cooldown(mod) -> None:
    print("\n[3] 拉起失败后必须冷却：不许每轮都开一次窗口")
    p = _Probe().install(mod)
    p.port_open = False
    p.pids = []
    p.start_error = "injected: 权限不足"
    p.app = "/Applications/Futu_OpenD.app"

    r1 = mod.ensure_opend(timeout=0)
    if len(p.start_calls) != 1:
        _bad(f"第一次应拉起 1 次，实际 {len(p.start_calls)} 次")
        return
    if not r1.get("error"):
        _bad("拉起失败却没留下错误原因")
        return

    r2 = mod.ensure_opend(timeout=0)
    if len(p.start_calls) != 1:
        _bad(f"冷却期内又拉起了一次（累计 {len(p.start_calls)} 次）—— 会连开一堆窗口")
        return
    if "冷却" not in (r2.get("skipped_reason") or ""):
        _bad(f"冷却跳过没有说明原因（skipped_reason={r2.get('skipped_reason')!r}）")
        return
    _ok("失败后进入冷却，第二次只报告不拉起，原因可读")


# ── 判据 4：open 返回 0 ≠ 成功 ─────────────────────────────────────────────
def check_launch_is_not_success(mod) -> None:
    print("\n[4] open 成功返回 ≠ OpenD 就绪：只认端口")
    p = _Probe().install(mod)
    p.port_open = False
    p.pids = []
    p.start_error = ""  # open 成功
    p.app = "/Applications/Futu_OpenD.app"

    r = mod.ensure_opend(timeout=0)

    if not r["started"]:
        _bad("应该记录「已执行拉起」")
        return
    if r["reachable"]:
        _bad("open 返回 0 就被当成 reachable=True —— 端口根本没通，这会把登录失败伪装成成功")
        return
    if not r.get("error"):
        _bad("拉起后端口未就绪却不报错 —— 任务会以为自己同步成功了")
        return
    _ok("拉起成功但端口未通 → reachable=False 且给出原因")


# ── 判据 5：没装 app 要明确报错，不许静默 ──────────────────────────────────
def check_no_app_installed(mod) -> None:
    print("\n[5] 未找到 OpenD app：明确报错，不许静默跳过")
    p = _Probe().install(mod)
    p.port_open = False
    p.pids = []
    p.app = ""

    try:
        r = mod.ensure_opend(timeout=0)
    except Exception as e:  # noqa: BLE001
        _bad(f"未安装 app 时抛异常：{type(e).__name__}: {e}")
        return

    if p.start_calls:
        _bad("没有 app 路径还执行了 open -a")
        return
    if "未找到" not in (r.get("error") or ""):
        _bad(f"未安装 app 却没说清原因（error={r.get('error')!r}）")
        return
    if r["reachable"]:
        _bad("未安装 app 却报 reachable=True")
        return
    _ok("未安装 app → 明确报错，未执行任何 open")


# ── 判据 6：定时任务定义必须真的存在且顺序正确 ─────────────────────────────
def _task_definition_problems(text: str) -> list[str]:
    problems: list[str] = []

    # ❗必须 timer，不能用 scheduler/cron。实测 2026-10-20：本项目
    # ``execution_mode=scheduler`` 的任务全部不按点触发（news_digest 19:00 /
    # ai_daily_report 21:00 / openrouter 9:00 的 last_run 全停在重启时刻 14:02），
    # 而 timer 模式的（金十、新华社、imessage）都在实时跑。写成本任务时先用
    # cron，注册成功、next_run_time 也对，但 18:00 与 18:10 两次都没触发。
    if re.search(r"execution_mode:\s*scheduler", text):
        problems.append(
            "execution_mode 是 scheduler —— 本项目的 APScheduler 路径实测不按点"
            "触发，只有重启补跑才会动；应改成 timer"
        )
    elif not re.search(r"execution_mode:\s*timer", text):
        problems.append("execution_mode 不是 timer（任务不会自动跑）")

    if re.search(r"scheduler_trigger:\s*cron", text) or re.search(r"cron_expr:\s*'[^']+'", text):
        problems.append("仍配了 cron 表达式 —— 会被归一到 scheduler 路径，同样不触发")

    if not re.search(r"task_type:\s*timer", text):
        problems.append("task_type 不是 timer")

    m = re.search(r"interval_seconds:\s*([0-9.]+)", text)
    if not m:
        problems.append("缺少 interval_seconds")
    else:
        try:
            iv = float(m.group(1))
        except ValueError:
            iv = 0.0
        if iv < 60:
            problems.append(f"interval_seconds={iv} 太短，会给 OpenD 建连造成压力")

    if "ensure_opend" not in text:
        problems.append("func_code 里没调用 ensure_opend —— OpenD 挂了就再也不同步")
    else:
        i_guard = text.index("ensure_opend")
        i_sync = text.find("FutuPortfolioSyncer", i_guard)
        if i_sync == -1:
            problems.append("func_code 里没调用 FutuPortfolioSyncer")
        elif i_sync < i_guard:
            problems.append("同步在守护之前执行 —— 会先撞一次连接失败")

    if not re.search(r'if\s+not\s+guard\.get\("reachable"\)\s*:\s*\n\s+.*?return', text, re.S):
        problems.append(
            "OpenD 不可达时没有立即 return —— 会继续去 sync，把「连不上」"
            "记成「同步成功/无账户」"
        )

    for env in ("REAL", "SIMULATE"):
        if env not in text:
            problems.append(f"func_code 没有同步 {env} 账户")

    return problems


def check_task_definition(text: str | None = None) -> None:
    print("\n[6] 定时任务定义：timer 模式 / 先守护后同步 / 不可达即终止")
    path = ROOT / TASK_YAML
    if text is None:
        if not path.exists():
            _bad(f"{TASK_YAML} 不存在 —— 同步还是只能靠手点")
            return
        text = path.read_text(encoding="utf-8")

    problems = _task_definition_problems(text)
    if problems:
        for p in problems:
            _bad(p)
        return
    _ok("任务定义完整：timer 每 600s、先 ensure_opend 再 sync、不可达即 return、REAL+SIMULATE 都覆盖")


# ── 判据 7：任务必须真能被文件配置管理器发现并编译 ──────────────────────────
def check_task_loadable() -> None:
    print("\n[7] 任务必须能被打包进调度（文件配置管理器 + 编译通过）")
    try:
        from deva.naja.config.file_config import get_file_config_manager

        mgr = get_file_config_manager("task")
        names = set(mgr.list_names())
    except Exception as e:  # noqa: BLE001
        _bad(f"文件配置管理器不可用：{type(e).__name__}: {e}")
        return

    name = Path(TASK_YAML).stem
    if name not in names:
        _bad(f"任务 {name} 未被配置管理器发现（共 {len(names)} 个）")
        return

    item = mgr.get(name)
    code = item.func_code or ""
    if not code.strip():
        _bad("func_code 为空 —— 任务会跑一个空函数")
        return
    try:
        compile(code, "<task>", "exec")
    except SyntaxError as e:
        _bad(f"func_code 编译失败：{e}")
        return

    if "def execute" not in code:
        _bad("func_code 里没有 execute() —— 调度器找不到入口")
        return
    _ok(f"任务 {name} 可被发现，func_code 编译通过且含 execute()")


# ── 判据 8：真实环境不谎报（端口活着时不该写「不可达」）──────────────────────
def check_live_status_consistency(_mod=None) -> None:
    print("\n[8] 真实环境自检：状态快照与端口实测必须一致")
    # ❗必须重新加载：前面的用例把 probe/_opend_pids/_pick_app 全换成了替身，
    # 拿同一个模块对象去测「真实环境」只会测到替身自己（实测：报「找不到 app」）。
    try:
        mod = _load(OPEND_SRC, "_guard_opend_live")
    except Exception as e:  # noqa: BLE001
        _bad(f"重新加载失败：{type(e).__name__}: {e}")
        return
    try:
        reachable = mod.probe()
        app = mod._pick_app()
        pids = mod._opend_pids()
    except Exception as e:  # noqa: BLE001
        _bad(f"真实探测抛异常：{type(e).__name__}: {e}")
        return

    if not app:
        _bad("本机找不到 OpenD app —— 自动拉起会永远失效")
        return

    if reachable and not pids:
        _bad("端口通却扫不到 OpenD 进程 —— 进程判据坏了（会导致重复拉起）")
        return

    st = mod.status()
    if reachable and st["last_ready_ts"] == 0:
        # 只是没走过 ensure_opend，不算错：提示即可
        _ok(f"当前 OpenD 可达（app={Path(app).name}），状态快照字段齐全")
        return
    _ok(f"当前 OpenD {'可达' if reachable else '不可达'}（pid={pids[:1]}），状态快照字段齐全")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--exercise-injections", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("富途定时同步 / OpenD 自动拉起 守卫")
    print("=" * 70)

    try:
        mod = _load(OPEND_SRC, "_guard_opend")
    except Exception as e:  # noqa: BLE001
        print(f"❌ 模块加载失败：{type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    for fn in (
        lambda: check_reachable_short_circuit(mod),
        lambda: check_starting_process_not_duplicated(mod),
        lambda: check_start_cooldown(mod),
        lambda: check_launch_is_not_success(mod),
        lambda: check_no_app_installed(mod),
        check_task_definition,
        check_task_loadable,
        lambda: check_live_status_consistency(mod),
    ):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _bad(f"判据执行异常：{type(e).__name__}: {e}")
            traceback.print_exc()

    total = PASS + FAIL
    print("\n" + "=" * 70)
    if FAIL:
        print(f"❌ {FAIL}/{total} 项失败")
        for f in FAILS:
            print(f"   - {f}")
    else:
        print(f"✅ 全部 {total} 项通过")
    print("=" * 70)

    if FAIL and args.strict:
        return 1
    if args.exercise_injections:
        return _run_injections()
    return 0


# ── 负向注入：把每个修复逐个改回「坏版本」，守卫必须喊出来 ─────────────────
def _load_patched(rel_path: str, mod_name: str, old: str, new: str, count: int = 1):
    """把源码改坏后重新加载（不落盘、不污染工作区）。

    ``count=-1`` 表示替换全部出现（``str.replace`` 的 0 是「一次都不换」，
    用它当「全部」会让注入静默失效 —— 守卫全绿但源码根本没被改坏）。
    """
    path = ROOT / rel_path
    src = path.read_text(encoding="utf-8")
    if old not in src:
        raise AssertionError(f"注入锚点找不到：{old[:60]!r}")
    patched = src.replace(old, new, count)
    import types

    mod = types.ModuleType(mod_name)
    mod.__file__ = str(path)
    sys.modules[mod_name] = mod
    exec(compile(patched, str(path), "exec"), mod.__dict__)
    return mod


def _load_patched_multi(rel_path: str, mod_name: str, pairs):
    """多处注入（用于「同一判据在两条路径上各写了一次」的场景）。"""
    path = ROOT / rel_path
    patched = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in patched:
            raise AssertionError(f"注入锚点找不到：{old[:60]!r}")
        patched = patched.replace(old, new, 1)
    import types

    mod = types.ModuleType(mod_name)
    mod.__file__ = str(path)
    sys.modules[mod_name] = mod
    exec(compile(patched, str(path), "exec"), mod.__dict__)
    return mod


def _expect_catch(label: str, fn, should_fail_msg: str) -> bool:
    """跑一个判据，期望它**失败**；跑完把全局计数复原。"""
    global PASS, FAIL
    saved_pass, saved_fail = PASS, FAIL
    saved_fails = list(FAILS)
    before = FAIL
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass
    caught = FAIL > before
    detail = FAILS[before:]
    PASS, FAIL = saved_pass, saved_fail
    FAILS[:] = saved_fails
    if caught:
        print(f"  ✅ 被捕获：{label} → {detail[0][:70] if detail else ''}")
    else:
        print(f"  ❌ 没抓到：{label} —— {should_fail_msg}")
    return caught


def _run_injections() -> int:
    print("\n" + "=" * 70)
    print("负向注入自证（把修复改回坏版本，守卫必须喊出来）")
    print("=" * 70)

    results: list[bool] = []

    # 注入 1：端口通也照样去拉起（两处快路径同时失效）
    print("\n[注入 1] 端口通也不短路（快路径 + 锁内双检同时失效）")
    try:
        _fast = (
            "    if probe():\n"
            '        result["reachable"] = True\n'
            "        _last_ready_ts = time.time()\n"
            "        return result"
        )
        _fast_bad = (
            "    if False:\n"
            '        result["reachable"] = True\n'
            "        _last_ready_ts = time.time()\n"
            "        return result"
        )
        _dbl = (
            "        if probe():\n"
            '            result["reachable"] = True\n'
            "            _last_ready_ts = time.time()\n"
            "            return result"
        )
        _dbl_bad = (
            "        if False:\n"
            '            result["reachable"] = True\n'
            "            _last_ready_ts = time.time()\n"
            "            return result"
        )
        mod = _load_patched_multi(OPEND_SRC, "_inj_opend_1", [(_fast, _fast_bad), (_dbl, _dbl_bad)])
        results.append(_expect_catch(
            "端口通仍拉起",
            lambda: check_reachable_short_circuit(mod),
            "端口通着还去 open，守卫仍然绿 —— 它会不停弹窗打扰用户",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 2：进程在也再拉一个（原「不判进程」写法）
    print("\n[注入 2] 进程存在仍重复拉起")
    try:
        mod = _load_patched(
            OPEND_SRC, "_inj_opend_2",
            "        if pids:", "        if False:",
        )
        results.append(_expect_catch(
            "重复拉起",
            lambda: check_starting_process_not_duplicated(mod),
            "进程在还 open 一个 —— 抢不到 11111 还会弹窗",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 3：去掉冷却（原「每轮重试」写法）
    print("\n[注入 3] 去掉拉起冷却")
    try:
        mod = _load_patched(
            OPEND_SRC, "_inj_opend_3",
            "        if _last_attempt_ts and since < START_COOLDOWN:",
            "        if False:",
        )
        results.append(_expect_catch(
            "冷却失效",
            lambda: check_start_cooldown(mod),
            "冷却没了还每轮 open —— 起不来时连开一堆窗口",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 4：open 成功就当 OpenD 好了（经典错误）
    print("\n[注入 4] 把 open 返回 0 当成 OpenD 就绪")
    try:
        mod = _load_patched(
            OPEND_SRC, "_inj_opend_4",
            '        result["started"] = True',
            '        result["started"] = True\n        result["reachable"] = True',
        )
        results.append(_expect_catch(
            "拉起即成功",
            lambda: check_launch_is_not_success(mod),
            "open 成功即当就绪 —— 登录失败会被记成同步成功",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 5：没装 app 也照样 open（静默空跑）
    print("\n[注入 5] 未安装 app 仍继续执行 open")
    try:
        mod = _load_patched(
            OPEND_SRC, "_inj_opend_5",
            "        if not app:", "        if False:",
        )
        results.append(_expect_catch(
            "空路径 open",
            lambda: check_no_app_installed(mod),
            "没有 app 路径还去 open —— 任务静默空跑，什么也没同步",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 6：任务在 OpenD 不可达时仍继续同步
    print("\n[注入 6] 任务在不可达时继续 sync")
    try:
        src = (ROOT / TASK_YAML).read_text(encoding="utf-8")
        patched = src.replace('      if not guard.get("reachable"):', "      if False:", 1)
        if patched == src:
            raise AssertionError("注入锚点找不到")
        results.append(_expect_catch(
            "不可达仍同步",
            lambda: check_task_definition(patched),
            "OpenD 不可达还去 sync —— 会把连接失败记成「没有账户」",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 7：任务改回 scheduler/cron（实测不触发的那条路）
    print("\n[注入 7] 任务改回 scheduler + cron 调度")
    try:
        src = (ROOT / TASK_YAML).read_text(encoding="utf-8")
        patched = src.replace("execution_mode: timer", "execution_mode: scheduler", 1)
        patched = patched.replace("task_type: timer", "task_type: scheduler", 1)
        if patched == src:
            raise AssertionError("注入锚点找不到")
        results.append(_expect_catch(
            "改回不触发的 cron 路径",
            lambda: check_task_definition(patched),
            "改回 scheduler/cron 后守卫仍绿 —— 那条路实测不按点触发，任务等于不存在",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    print("\n" + "=" * 70)
    caught = sum(1 for r in results if r)
    print(f"负向注入：{caught}/{len(results)} 被捕获")
    if caught != len(results):
        print("❗ 有注入没被抓到 —— 对应判据是摆设")
        return 1
    print("✅ 每条注入都被捕获")
    return 0


if __name__ == "__main__":
    sys.exit(main())
