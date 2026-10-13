"""守卫：`market_time_service` 不得被别名成 `trading_clock`。

真实事故（2026-10-14）：
    /banditadmin 打开即报 "Unhandled error in pywebio app"。堆栈落点是
    VirtualPosition.holding_seconds -> SR('market_time_service').get_market_time()，
    但注册表里这个名字拿到的是 TradingClock，而 TradingClock **没有**
    get_market_time —— AttributeError。

    污染源是 AppContainer._register_container_components_as_singletons() 里的一行：
        "market_time_service": self._trading_clock,   # 别名：旧代码可能用这个名
    下面挂着的 components dict 会在装配完成后「覆盖注册」到 SingletonRegistry，
    于是 register.py 声明式表里正确的 MarketTimeService 被顶掉。

    两个名字背后的接口互不相通，永远不该共享实例：
        MarketTimeService -> get_market_time / get_market_datetime / set_replay_mode
        TradingClock      -> cn_phase / us_phase / get_global_status

守卫内容：
    1. 静态：container 的组件注册映射里，
       a) 不得出现 `market_time_service` 键；
       b) 不同名字不得指向同一个属性（别名 = 把两套接口强行等同）。
    2. 契约：MarketTimeService 必须提供三个回放时间接口；
       TradingClock 必须**不**提供它们 —— 这正是"不可互换"的判据。
    3. 负向验证：把别名行注回源码，静态检查必须立刻失败（否则守卫没有区分度）。

用法：
    python3 scripts/verify/verify_market_time_alias.py [--strict]
"""

import ast
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTAINER_PY = os.path.join(REPO, "deva", "naja", "application", "container.py")
REGISTER_PY = os.path.join(REPO, "deva", "naja", "register.py")
MARKET_TIME_PY = os.path.join(REPO, "deva", "naja", "infra", "runtime", "market_time.py")
TRADING_CLOCK_PY = os.path.join(REPO, "deva", "naja", "radar", "trading_clock.py")

BANNED_KEY = "market_time_service"
MTS_INTERFACE = ("get_market_time", "get_market_datetime", "set_replay_mode")


# ---------------------------------------------------------------- 静态检查

def _components_dict(node: ast.AST):
    """取出 _register_container_components_as_singletons 里的 components = {...}"""
    for fn in ast.walk(node):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                fn.name == "_register_container_components_as_singletons":
            for stmt in ast.walk(fn):
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                        and isinstance(stmt.targets[0], ast.Name) \
                        and stmt.targets[0].id == "components" \
                        and isinstance(stmt.value, ast.Dict):
                    return stmt.value
    return None


def _attr_label(value: ast.AST) -> str:
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
        return f"{value.value.id}.{value.attr}"
    return ast.dump(value)


def check_container_source(src: str):
    """返回失败原因列表（空列表 = 通过）"""
    failures = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"container.py 语法错误: {e}"]

    d = _components_dict(tree)
    if d is None:
        failures.append("找不到 _register_container_components_as_singletons 里的 components dict"
                        "（结构变了，守卫需要同步更新）")
        return failures

    keys = [k.value for k in d.keys if isinstance(k, ast.Constant)]
    values = [_attr_label(v) for v in d.values]

    # a) 点名禁止
    if BANNED_KEY in keys:
        idx = keys.index(BANNED_KEY)
        failures.append(
            f"components 里又出现了 '{BANNED_KEY}' 键（当前指向 {values[idx]}）—— "
            f"它会覆盖注册表里真正的 MarketTimeService，请删除该键"
        )

    # b) 通用禁令：不同名字不得指向同一属性
    seen = {}
    for k, v in zip(keys, values):
        if v in seen:
            failures.append(f"注册映射里 '{seen[v]}' 与 '{k}' 指向同一个对象 {v} —— "
                            f"名字别名会把两套接口强行等同，禁止")
        else:
            seen[v] = k
    return failures


def check_register_table(src: str):
    """register.py 里两个名字必须分别落到各自的类上。

    market_time_service 走声明式 4 元组表；
    trading_clock 走 _register_custom_singletons 的显式工厂（带 start()），
    两条路径都要认，否则守卫会对着「合法实现」误报。
    """
    failures = []
    tree = ast.parse(src)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) == 4:
            head = node.elts[0]
            if isinstance(head, ast.Constant) and head.value in (BANNED_KEY, "trading_clock"):
                mod = node.elts[1]
                cls = node.elts[2]
                if isinstance(mod, ast.Constant) and isinstance(cls, ast.Constant):
                    found[head.value] = (mod.value, cls.value)

    if BANNED_KEY not in found:
        failures.append(f"register.py 声明式表里找不到单例 '{BANNED_KEY}'")
    else:
        mod, cls = found[BANNED_KEY]
        if cls != "MarketTimeService":
            failures.append(f"'{BANNED_KEY}' 注册成了 {mod}:{cls}，期望 MarketTimeService")
        if "market_time" not in mod:
            failures.append(f"'{BANNED_KEY}' 的模块路径不含 'market_time'：{mod}")

    # trading_clock：显式工厂路径也算合法
    has_custom_factory = (
        "register_singleton('trading_clock'" in src
        and "from .radar.trading_clock import TradingClock" in src
    )
    if "trading_clock" not in found and not has_custom_factory:
        failures.append("register.py 里找不到单例 'trading_clock' 的注册（表或显式工厂都没有）")

    return failures


def _class_method_names(path: str, class_name: str):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names = set()
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(sub.name)
                # property 装饰的方法同样是 FunctionDef，已被覆盖
            return names
    return None


def check_interfaces():
    failures = []
    mts = _class_method_names(MARKET_TIME_PY, "MarketTimeService")
    tc = _class_method_names(TRADING_CLOCK_PY, "TradingClock")

    if mts is None:
        failures.append("找不到 MarketTimeService 类")
    else:
        for m in MTS_INTERFACE:
            if m not in mts:
                failures.append(f"MarketTimeService 缺少接口 {m}()")
    if tc is None:
        failures.append("找不到 TradingClock 类")
    else:
        for m in MTS_INTERFACE:
            if m in tc:
                failures.append(
                    f"TradingClock 竟然有了 {m}() —— 两个类开始趋同，"
                    f"本守卫的『不可互换』前提需要重新评估（不要默默放开别名）"
                )
    return failures


# ---------------------------------------------------------------- 主流程

def main() -> int:
    failures = []

    with open(CONTAINER_PY, encoding="utf-8") as f:
        container_src = f.read()
    with open(REGISTER_PY, encoding="utf-8") as f:
        register_src = f.read()

    print("— 1. 静态：组件注册映射 —")
    for msg in check_container_source(container_src):
        failures.append(msg)
        print(f"  ❌ {msg}")
    if not check_container_source(container_src):
        print("  ✅ 注册映射里没有 market_time_service 别名，也没有重复指向")

    print("— 2. 静态：声明式单例表 —")
    for msg in check_register_table(register_src):
        failures.append(msg)
        print(f"  ❌ {msg}")
    if not check_register_table(register_src):
        print("  ✅ market_time_service / trading_clock 各自指向正确的类")

    print("— 3. 契约：两套接口不可互换 —")
    iface = check_interfaces()
    for msg in iface:
        failures.append(msg)
        print(f"  ❌ {msg}")
    if not iface:
        print("  ✅ MarketTimeService 提供回放时间接口，TradingClock 不提供")

    print("— 4. 负向验证（把别名注回源码）—")
    needle = '            "trading_clock": self._trading_clock,\n'
    if needle not in container_src:
        failures.append("注入锚点未命中（'trading_clock' 行被改写），负向验证无法进行")
        print("  ❌ 注入锚点未命中")
    else:
        injected = container_src.replace(
            needle,
            needle + f'            "{BANNED_KEY}": self._trading_clock,\n',
            1,
        )
        inj_failures = check_container_source(injected)
        hit_banned = any(BANNED_KEY in m for m in inj_failures)
        hit_dup = any("指向同一个对象" in m for m in inj_failures)
        if hit_banned and hit_dup:
            print("  ✅ 注回别名后两条检查同时报错（守卫有区分度）")
        else:
            failures.append("注回别名后静态检查没有如期报错 → 守卫没有区分度")
            print(f"  ❌ 注入后仅得到: {inj_failures}")

    print("— 5. 还原后复核 —")
    if check_container_source(container_src):
        failures.append("还原后静态检查仍失败 → 状态泄漏")
        print("  ❌ 仍失败")
    else:
        print("  ✅ 通过")

    print()
    if failures:
        print(f"❌ 守卫失败（{len(failures)} 项）")
        return 1
    print("✅ 通过：market_time_service 与 trading_clock 是两个互不通婚的单例")
    return 0


if __name__ == "__main__":
    sys.exit(main())
