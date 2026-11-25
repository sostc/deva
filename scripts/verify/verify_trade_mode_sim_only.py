#!/usr/bin/env python3
"""守卫：交易模式必须「只模拟、不真实」。

为什么要有它
============
用户明确的部署纪律：**先把模拟交易跑一段时间，觉得合适再谈真实交易**。
所以本机必须满足两件事，且**这两件事都不能靠"记得去设置"**：

1. 模拟交易开关是**开**的（``NAJA_EXEC_BACKEND=futu_sim``）——
   不开就静默退回虚拟仓，页面上照样有持仓、有盈亏，看着一切正常，
   实际上券商那边一笔单都没发生。这种「以为在跑模拟盘」的假绿最难发现。
2. 真实交易**没有路径**——不是某个开关等于 0，而是 ``place_order`` 的
   唯一调用点硬编码 ``TrdEnv.SIMULATE``，且根本没有 real 后端可装配。

守什么
======
A. 全仓 AST 扫描：每个 ``place_order(...)`` 的 ``trd_env`` 必须是
   ``TrdEnv.SIMULATE``。这是唯一能真正把钱报出去的地方，逐处钉死。
B. ``BACKENDS`` 里不许出现真实后端；``NAJA_EXEC_BACKEND=real/live/实盘``
   必须回落虚拟仓（并报错），不许被当成合法值。
C. 部署开关 ``TRADE_ENV_DEFAULTS`` 必须钉 ``futu_sim``，且守望台执行腿
   单独保持关闭（它会把「批准」直接变成报单，属另一层授权）。
D. ``_merge_env`` 必须**保留**已有变量——原实现会把手写的
   ``NAJA_T_ROTATION_ON_SIM`` 等抹掉，用户点一下「登录自启」就退回虚拟盘。
E. 模拟组合（``futu_sim_portfolio``）只允许 SIMULATE，不许出现 REAL。

跑法
----
    python3 scripts/verify/verify_trade_mode_sim_only.py --strict
    python3 scripts/verify/verify_trade_mode_sim_only.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEVA = REPO / "deva"

EXEC_PY = DEVA / "naja" / "bandit" / "execution.py"
SIM_PF_PY = DEVA / "naja" / "bandit" / "futu_sim_portfolio.py"
AUTOSTART_PY = DEVA / "naja" / "infra" / "autostart" / "login_item_manager.py"


# ---------------------------------------------------------------- 加载

def _load(name: str, path: Path):
    """按文件路径重载模块。

    ❗不许用 ``import``：那会拿到 ``sys.modules`` 里的旧对象，注入改动
    根本进不来，守卫全绿但什么都没守。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    # ❗先登记再 exec：@dataclass 解析 KW_ONLY 时需要 sys.modules 里有这个模块。
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- A. 下单环境

def check_place_order_is_sim() -> list:
    """全仓每个 place_order 调用的 trd_env 必须是 TrdEnv.SIMULATE。"""
    failures = []
    sites = 0
    for path in sorted(DEVA.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            fname = getattr(func, "attr", None) or getattr(func, "id", None)
            if fname != "place_order":
                continue
            sites += 1
            rel = path.relative_to(REPO)
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if "trd_env" not in kw:
                failures.append(
                    f"{rel}:{node.lineno} place_order 没显式传 trd_env —— "
                    f"默认环境可能是真实账户"
                )
                continue
            env_src = ast.unparse(kw["trd_env"]).strip()
            if env_src != "TrdEnv.SIMULATE":
                failures.append(
                    f"{rel}:{node.lineno} place_order 的 trd_env={env_src}，"
                    f"不是 TrdEnv.SIMULATE —— 真实报单路径被打开了"
                )
    # 下限保护：调用点被删/改名到别处时，不能让「0 处检查」冒充全绿
    if sites < 1:
        failures.append("全仓找不到任何 place_order 调用点 —— 守卫失去落点（判据失效）")
    return failures


# ---------------------------------------------------------------- B. 后端枚举

def check_backends_have_no_real(mod) -> list:
    failures = []
    backends = tuple(getattr(mod, "BACKENDS", ()))
    real_aliases = set(getattr(mod, "REAL_ALIASES", ()))
    if not real_aliases:
        failures.append("execution 没有 REAL_ALIASES —— real/live 会被当成普通未知值悄悄降级")
    for name in backends:
        if str(name).strip().lower() in (real_aliases | {"real", "live"}):
            failures.append(f"BACKENDS 里出现了真实后端 {name!r} —— 真实交易被打开了")
    if mod.BACKEND_FUTU_SIM not in backends:
        failures.append("BACKENDS 里没有 futu_sim —— 模拟交易无法开启")
    return failures


def check_real_falls_back_to_virtual(mod) -> list:
    """设成 real/live 时必须回落虚拟仓，且绝不能返回真实后端。"""
    failures = []
    old = os.environ.get(mod.ENV_BACKEND)
    try:
        for raw in ("real", "REAL", "live", "实盘", "真实"):
            os.environ[mod.ENV_BACKEND] = raw
            got = mod.selected_backend_name()
            if got != mod.BACKEND_VIRTUAL:
                failures.append(
                    f"{mod.ENV_BACKEND}={raw!r} 返回了 {got!r}，应当回落 "
                    f"{mod.BACKEND_VIRTUAL!r}（真实交易无实现）"
                )
        os.environ[mod.ENV_BACKEND] = "futu_sim"
        if mod.selected_backend_name() != mod.BACKEND_FUTU_SIM:
            failures.append("NAJA_EXEC_BACKEND=futu_sim 没生效 —— 模拟交易打不开")
        os.environ.pop(mod.ENV_BACKEND, None)
        if mod.selected_backend_name() != mod.BACKEND_VIRTUAL:
            failures.append("未配置后端时默认不是 virtual —— 装上代码就会自动报单")
    finally:
        if old is None:
            os.environ.pop(mod.ENV_BACKEND, None)
        else:
            os.environ[mod.ENV_BACKEND] = old
    return failures


def check_mode_summary_says_no_real(mod) -> list:
    """启动横幅必须如实写「真实交易未实现」。"""
    failures = []
    old = os.environ.get(mod.ENV_BACKEND)
    try:
        os.environ[mod.ENV_BACKEND] = "futu_sim"
        sim_text = mod.trading_mode_summary()
        if "模拟" not in sim_text or "未实现" not in sim_text:
            failures.append(f"模拟模式横幅没说清（缺「模拟」或「真实未实现」）：{sim_text}")

        os.environ[mod.ENV_BACKEND] = "real"
        real_text = mod.trading_mode_summary()
        if "虚拟仓" not in real_text or "未实现" not in real_text:
            failures.append(f"请求 real 时横幅没有回落说明：{real_text}")
    finally:
        if old is None:
            os.environ.pop(mod.ENV_BACKEND, None)
        else:
            os.environ[mod.ENV_BACKEND] = old
    return failures


# ---------------------------------------------------------------- C/D. 部署开关

def check_deploy_switches(mod) -> list:
    failures = []
    defaults = dict(getattr(mod, "TRADE_ENV_DEFAULTS", {}) or {})
    if not defaults:
        failures.append("login_item_manager 没有 TRADE_ENV_DEFAULTS —— 交易模式没有权威部署处")
        return failures
    if str(defaults.get("NAJA_EXEC_BACKEND", "")).lower() != "futu_sim":
        failures.append(
            f"TRADE_ENV_DEFAULTS 没把执行后端钉在 futu_sim（实际 "
            f"{defaults.get('NAJA_EXEC_BACKEND')!r}）—— 模拟交易会被静默关掉"
        )
    if str(defaults.get("NAJA_WATCH_EXEC_ENABLED", "1")) != "0":
        failures.append("TRADE_ENV_DEFAULTS 把守望台执行腿打开了 —— 批准会直接变成报单")
    if str(defaults.get("NAJA_T_ROTATION_ON_SIM", "0")) != "1":
        failures.append("TRADE_ENV_DEFAULTS 没打开做 T 的模拟账户路径")
    return failures


def check_merge_preserves_env(mod) -> list:
    """合并必须保留已有变量，且不得覆盖用户的显式选择。"""
    failures = []
    existing = {
        "NAJA_T_ROTATION_SYMBOLS": "588200,HK:00700,US:QQQ",
        "NAJA_EXEC_BACKEND": "virtual",   # 用户显式关掉模拟 → 必须尊重
    }
    env = mod._merge_env(existing)
    if env.get("NAJA_T_ROTATION_SYMBOLS") != existing["NAJA_T_ROTATION_SYMBOLS"]:
        failures.append("_merge_env 抹掉了 NAJA_T_ROTATION_SYMBOLS —— 点一次自启就丢配置")
    if env.get("NAJA_EXEC_BACKEND") != "virtual":
        failures.append("_merge_env 覆盖了用户显式的 NAJA_EXEC_BACKEND —— 设置被静默改写")
    filled = mod._merge_env({})
    if str(filled.get("NAJA_EXEC_BACKEND", "")).lower() != "futu_sim":
        failures.append("_merge_env 空配置时没补上 futu_sim —— 新机器默认不跑模拟盘")
    if filled.get("NAJA_AUTOSTART") != "1":
        failures.append("_merge_env 丢了 NAJA_AUTOSTART")
    plist = mod._build_launch_agent_plist(existing_env=existing)
    penv = plist.get("EnvironmentVariables") or {}
    if penv.get("NAJA_T_ROTATION_SYMBOLS") != existing["NAJA_T_ROTATION_SYMBOLS"]:
        failures.append("_build_launch_agent_plist 没把已有环境变量带进 plist")
    return failures


def check_local_plist_opts_in() -> list:
    """本机若用 LaunchAgent 跑 Naja，它的后端必须钉在 futu_sim。

    只在 plist 存在且确实是本服务时检查（别的机器没配自启就跳过），
    避免把「本机没开自启」误判成失败。
    """
    failures = []
    plist = Path.home() / "Library" / "LaunchAgents" / "com.naja.autostart.plist"
    if not plist.exists():
        return failures
    try:
        import plistlib
        data = plistlib.loads(plist.read_bytes())
    except Exception as e:  # noqa: BLE001
        return [f"读取本机 LaunchAgent 失败: {type(e).__name__}: {e}"]
    env = data.get("EnvironmentVariables") or {}
    if env.get("NAJA_AUTOSTART") != "1":
        return failures
    backend = str(env.get("NAJA_EXEC_BACKEND", "")).strip().lower()
    if backend != "futu_sim":
        failures.append(
            f"本机 LaunchAgent 的 NAJA_EXEC_BACKEND={backend!r}，不是 futu_sim —— "
            f"服务重启后会退回虚拟仓，模拟盘静默停摆"
        )
    if str(env.get("NAJA_WATCH_EXEC_ENABLED", "0")) != "0":
        failures.append("本机 LaunchAgent 打开了守望台执行腿 —— 批准会直接报单")
    return failures


# ---------------------------------------------------------------- E. 模拟组合

def check_sim_portfolio_only_simulate() -> list:
    failures = []
    if not SIM_PF_PY.exists():
        return ["找不到 futu_sim_portfolio.py —— 守卫失去落点"]
    src = SIM_PF_PY.read_text(encoding="utf-8")
    if "TrdEnv.REAL" in src:
        failures.append("futu_sim_portfolio 里出现 TrdEnv.REAL —— 会用真实账户持仓冒充模拟仓")
    if "TrdEnv.SIMULATE" not in src:
        failures.append("futu_sim_portfolio 没有 TrdEnv.SIMULATE —— 模拟账户路径断了")
    # 账户来源必须是 FutuSimBackend._resolve_account（它的 syncer 钉在 SIMULATE），
    # 不是自己再枚举一遍账户 —— 自己枚举就可能把真实账户选进来。
    if "_resolve_account" not in src:
        failures.append("futu_sim_portfolio 没走 FutuSimBackend._resolve_account —— 账户来源不受模拟环境约束")
    return failures


def check_sim_backend_syncer_is_simulate() -> list:
    """FutuSimBackend 的同步器必须钉在 SIMULATE。"""
    if not EXEC_PY.exists():
        return ["找不到 execution.py —— 守卫失去落点"]
    src = EXEC_PY.read_text(encoding="utf-8")
    if 'FutuPortfolioSyncer(trd_env="SIMULATE")' not in src:
        return ['FutuSimBackend 没用 FutuPortfolioSyncer(trd_env="SIMULATE") —— 可能拿真实账户当模拟仓']
    return []


# ---------------------------------------------------------------- 汇总

def _all_checks() -> list:
    failures = []
    failures += check_place_order_is_sim()
    failures += check_sim_portfolio_only_simulate()
    failures += check_sim_backend_syncer_is_simulate()
    failures += check_local_plist_opts_in()

    exec_mod = _load("exec_under_test", EXEC_PY)
    failures += check_backends_have_no_real(exec_mod)
    failures += check_real_falls_back_to_virtual(exec_mod)
    failures += check_mode_summary_says_no_real(exec_mod)

    auto_mod = _load("autostart_under_test", AUTOSTART_PY)
    failures += check_deploy_switches(auto_mod)
    failures += check_merge_preserves_env(auto_mod)
    return failures


INJECTIONS = [
    {
        "name": "把模拟单的环境改成真实环境",
        "file": EXEC_PY,
        "old": "                trd_env=TrdEnv.SIMULATE,",
        "new": "                trd_env=TrdEnv.REAL,",
    },
    {
        "name": "把 real 塞进合法后端枚举",
        "file": EXEC_PY,
        "old": 'BACKENDS = (BACKEND_VIRTUAL, BACKEND_FUTU_SIM)',
        "new": 'BACKENDS = (BACKEND_VIRTUAL, BACKEND_FUTU_SIM, "real")',
    },
    {
        "name": "部署默认值改成虚拟仓（模拟盘静默关掉）",
        "file": AUTOSTART_PY,
        "old": '    "NAJA_EXEC_BACKEND": "futu_sim",',
        "new": '    "NAJA_EXEC_BACKEND": "virtual",',
    },
    {
        "name": "模拟组合改用真实环境",
        "file": SIM_PF_PY,
        "old": "TrdEnv.SIMULATE",
        "new": "TrdEnv.REAL",
        "count": 1,
    },
]


def run_injections() -> int:
    caught = 0
    for inj in INJECTIONS:
        path: Path = inj["file"]
        original = path.read_text(encoding="utf-8")
        old = inj["old"]
        if original.count(old) < 1:
            print(f"❌ 注入锚点不存在：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        new = original.replace(old, inj["new"], inj.get("count", -1) if "count" in inj else -1)
        path.write_text(new, encoding="utf-8")
        try:
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
        if found:
            caught += 1
            print(f"  ✅ 被捕获：{found[0][:110]}")
        else:
            print("  ❌ 没抓到 —— 摆设")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获")
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="失败即非零退出")
    ap.add_argument("--exercise-injections", action="store_true", help="真实注入后必须报错")
    args = ap.parse_args()

    if args.exercise_injections:
        caught = run_injections()
        ok = caught == len(INJECTIONS)
        print("✅ 注入自证通过" if ok else "❌ 注入自证失败")
        return 0 if ok else 1

    failures = _all_checks()
    if failures:
        print(f"❌ 交易模式守卫失败 {len(failures)} 项：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 交易模式 = 仅模拟（futu_sim），真实交易无下单路径")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
