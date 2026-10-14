#!/usr/bin/env python3
"""守卫：富途模拟执行后端（``DecisionPlan`` → 真的下一笔单）。

守三件事：
1. **不动手就不许动**：默认后端必须是虚拟仓；配置写错要回落虚拟仓，
   绝不能"因为装了新代码就开始报单"。
2. **每道闸各拦各的**：未知方向 / 卖出无底仓 / 判不出市场 / 市场不在白名单 /
   找不到模拟账户 / 取不到每手股数 / 金额买不起一手 / 槽位已占用 ——
   每条都要**独立**给出跳过与原因（不能合并成一句"失败"），
   且原因两两不同（一条保护掩盖另一条 = 假绿）。
   卖腿额外守三条：可卖量为 0 必须跳过、不足一手必须跳过、
   计划量大于可卖量按可卖量下调（不能按计划量硬报，富途会拒单）。
3. **失败要归还槽位**：报单失败不归还 → 该标的当天再也下不出单。

用法::

    python3 scripts/verify/verify_futu_sim_execution.py --strict
    python3 scripts/verify/verify_futu_sim_execution.py --self-test
    python3 scripts/verify/verify_futu_sim_execution.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import threading
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANDIT = REPO / "deva" / "naja" / "bandit"

EXEC_PY = BANDIT / "execution.py"
ADAPTIVE_PY = BANDIT / "adaptive_cycle.py"
SYNCER_PY = BANDIT / "futu_portfolio_syncer.py"
FRESHNESS_PY = BANDIT / "data_freshness.py"

# ---------------------------------------------------------------- ① 静态

STATIC_RULES = [
    (EXEC_PY, r'ENV_BACKEND\s*=\s*"NAJA_EXEC_BACKEND"',
     "缺少执行后端开关（没法回滚到虚拟仓）"),
    (EXEC_PY, r'BACKEND_VIRTUAL\s*=\s*"virtual"',
     "缺少默认后端名 virtual"),
    (EXEC_PY, r'os\.O_CREAT\s*\|\s*os\.O_EXCL',
     "幂等槽位未用 O_CREAT|O_EXCL 原子认领（先查后写会在并发下重复下单）"),
    (EXEC_PY, r'def floor_to_lot\(',
     "缺少整手折算（港股下单必须是每手整数倍）"),
    (EXEC_PY, r'if price <= 0 or lot_size <= 0 or amount <= 0:',
     "整手折算缺少非正数保护"),
    (EXEC_PY, r'release_order_slot\(key\)',
     "报单失败后未归还槽位（该标的当天再也下不出单）"),
    (EXEC_PY, r'skipped: bool = False',
     "结果契约缺少 skipped —— 跳过与失败必须分成两个维度"),
    (EXEC_PY, r'if market not in self\.markets:',
     "缺少市场白名单检查（美股信号会去撞不存在的模拟账户）"),
    (EXEC_PY, r'if not market:\s*\n\s*return skip\(why\)',
     "市场判不出来时未如实跳过（猜市场 = 把单下到别的盘口）"),
    (EXEC_PY, r'if lot_size <= 0:',
     "取不到每手股数时未跳过（凭猜报单必被拒）"),
    (ADAPTIVE_PY, r'resolve_backend\(portfolio=self\._portfolio\)',
     "AdaptiveCycle 未走执行后端（回到直连虚拟仓的老路）"),
    (ADAPTIVE_PY, r'outcome\s*=\s*self\._execution_backend\(\)\.submit\(',
     "AdaptiveCycle 未经由执行后端提交订单"),
    (ADAPTIVE_PY, r'if not outcome\.acted:',
     "AdaptiveCycle 未区分「跳过」与「失败」"),
    # ❗卖出方向必须**按 side 选择**：写死成 BUY 的话，做 T 的卖腿
    # 实际是在加仓 —— 份额守恒会被破坏，而且从日志上看不出来。
    # 探针只能记录 _place 的入参，抓不到 TrdSide 的真实取值，故用静态守。
    (EXEC_PY, r'TrdSide\.SELL if .* == "sell" else TrdSide\.BUY',
     "卖单方向未按 side 选择（做T 的卖腿会变成加仓）"),
    (EXEC_PY, r'can_sell_qty',
     "卖出未用 can_sell_qty（A股 T+1 当日买入不可卖，用 qty 会被富途拒单）"),
    # ❗买入决策记录必须用**实际成交股数**（outcome.quantity），与平仓侧
    # （position.quantity）同量纲 —— 这张表是复盘用的，混量纲事后无法解读。
    (ADAPTIVE_PY, r'quantity\s*=\s*(?:float\(\s*)?(?:getattr\(\s*)?outcome',
     "买入决策记录未用 outcome.quantity（实际成交股数）"),
]

STATIC_FORBIDDEN = [
    (EXEC_PY, r'TrdEnv\.REAL',
     "模拟后端出现 TrdEnv.REAL —— 会把模拟单报到真实账户"),
    (EXEC_PY, r'lot_size\s*=\s*\d+\s*$',
     "每手股数被写死（港股每手 20~10000 不等，必须实查）"),
    (EXEC_PY, r'def selected_backend_name[\s\S]{0,400}?return\s+BACKEND_FUTU_SIM\s*\n',
     "默认后端变成了 futu_sim —— 装上新代码就自动开始报单"),
    (ADAPTIVE_PY, r'self\._portfolio\.open_position\(',
     "AdaptiveCycle 绕过执行后端直接调 open_position"),
    (ADAPTIVE_PY, r'quantity\s*=\s*amount\b',
     "买入决策记录把**金额**当成 quantity —— 复盘表 naja_bandit_decision_context "
     "量纲混用（平仓侧传的是股数）"),
]

# 负向注入：改一处源码，check() 必须报错
INJECTIONS = [
    {
        "name": "把模拟单的环境改成真实环境",
        "file": EXEC_PY,
        "old": "                trd_env=TrdEnv.SIMULATE,",
        "new": "                trd_env=TrdEnv.REAL,",
    },
    {
        "name": "去掉「报单失败归还槽位」",
        "file": EXEC_PY,
        "old": "        if not order_id:\n"
               "            # 报单没成功 → 归还槽位，别把当天唯一的机会吃掉\n"
               "            release_order_slot(key)\n",
        "new": "        if not order_id:\n",
    },
    {
        "name": "整手折算改成不按手取整（回到小数股）",
        "file": EXEC_PY,
        "old": "    return int(amount // (price * float(lot_size))) * int(lot_size)",
        "new": "    return int(amount // price)",
    },
    {
        "name": "AdaptiveCycle 绕过后端直调虚拟仓",
        "file": ADAPTIVE_PY,
        "old": "        outcome = self._execution_backend().submit(\n",
        "new": "        from .execution import VirtualPortfolioBackend as _VPB\n"
               "        outcome = _VPB(self._portfolio).submit(\n",
    },
    {
        "name": "报单上下文不再显式指定市场过滤（回落 SDK 默认 TrdMarket.HK）",
        "file": EXEC_PY,
        "old": "            filter_trdmarket=trd_market(market), host=HOST, port=PORT, "
               "security_firm=firm,\n",
        "new": "            host=HOST, port=PORT, security_firm=firm,\n",
    },
    {
        "name": "同步器枚举账户时不再指定市场过滤（美股/A股模拟账户会静默消失）",
        "file": SYNCER_PY,
        "old": "                filter_trdmarket=TrdMarket.NONE, host=HOST, port=PORT,\n",
        "new": "                host=HOST, port=PORT,\n",
    },
    {
        "name": "限价不再对齐最小价差",
        "file": EXEC_PY,
        "old": "    return round(steps * tick, 6)",
        "new": "    return price",
    },
    {
        "name": "卖单不再校验可卖持仓（空仓也能卖出 → 富途拒单）",
        "file": EXEC_PY,
        "old": '            if avail <= 0:\n',
        "new": '            if False:\n',
    },
    {
        "name": "卖出方向被写死成买入（做T 的卖腿实际在加仓）",
        "file": EXEC_PY,
        "old": '        trd_side = TrdSide.SELL if str(side).strip().lower() == "sell" else TrdSide.BUY',
        "new": '        trd_side = TrdSide.BUY',
    },
    {
        "name": "槽位键忽略 tag（做T 第二轮起被幂等挡掉）",
        "file": EXEC_PY,
        "old": '    if tag:\n        key = f"{key}_{tag}"\n',
        "new": "",
    },
    {
        "name": "同步时不再剔除 DISABLED 账户",
        "file": SYNCER_PY,
        "old": '            and r.get("acc_status", "ACTIVE").upper() == "ACTIVE"\n',
        "new": "",
    },
    {
        "name": "买入分支又改回只认 amount（计划股数被重算，实盘少买一手）",
        "file": EXEC_PY,
        "old": "            if quantity is not None:\n"
               "                # ❗调用方（做 T 的补底仓",
        "new": "            if False:\n"
               "                # ❗调用方（做 T 的补底仓",
    },
    {
        "name": "买入决策记录把金额当 quantity（复盘表量纲混用）",
        "file": ADAPTIVE_PY,
        "old": '                quantity=float(getattr(outcome, "quantity", 0.0) or 0.0),',
        "new": "                quantity=amount,",
    },
]


# ---------------------------------------------------------------- 载入

def _stub_package(name: str, path=None):
    mod = types.ModuleType(name)
    if path is not None:
        mod.__path__ = [str(path)]
    sys.modules[name] = mod
    return mod


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    # 必须先登记进 sys.modules：@dataclass 解析注解时靠它反查所属模块
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


class Sandbox:
    """把被测模块加载进临时目录沙箱：不碰生产库、不碰真实报单目录。"""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="verify_sim_exec_"))
        self.exec_mod = None
        self.syncer_mod = None

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stub_deva(self):
        """用桩件顶掉 deva 包 —— 守卫绝不碰生产库。"""
        def _no_db(*_a, **_k):
            raise RuntimeError("守卫不访问数据库")

        deva = _stub_package("deva")
        deva.NB = _no_db
        _stub_package("deva.naja")
        _stub_package("deva.naja.bandit", BANDIT)

    def load(self):
        if self.exec_mod is not None:
            return self.exec_mod
        # ❗必须按**带包名**的模块名加载：execution.py 里会
        # ``from .stock_block_map import US_STOCK_BLOCKS``（懒加载美股注册表）。
        # 若用顶层名字加载，这个相对导入必然 ImportError → 被 except 吞掉 →
        # 注册表静默变成空集合 → 裸字母代码全部判不出市场，而守卫一无所知。
        self._stub_deva()
        self.exec_mod = _load_by_path("deva.naja.bandit.execution", EXEC_PY)
        # 报单目录改到沙箱，避免污染 ~/.naja
        self.exec_mod.order_dir = lambda: self.tmp
        return self.exec_mod

    def load_syncer(self):
        """加载同步器（用桩件替代 deva 包）。"""
        if self.syncer_mod is not None:
            return self.syncer_mod

        self._stub_deva()
        _load_by_path("deva.naja.bandit.data_freshness", FRESHNESS_PY)
        self.syncer_mod = _load_by_path("deva.naja.bandit.futu_portfolio_syncer", SYNCER_PY)
        return self.syncer_mod


# ---------------------------------------------------------------- ①b 上下文市场过滤

# 会构造富途交易上下文的地方。每个构造点都必须显式传 ``filter_trdmarket``。
CONTEXT_CALLEES = ("OpenSecTradeContext(", "OpenFutureTradeContext(")


def _call_snippets(src: str, callee: str) -> list:
    """把源码里 ``callee(...)`` 的**完整调用片段**抠出来（配平括号）。"""
    out, idx = [], 0
    while True:
        i = src.find(callee, idx)
        if i < 0:
            return out
        j = src.find("(", i + len(callee) - 1)
        depth, k = 0, j
        while k < len(src):
            if src[k] == "(":
                depth += 1
            elif src[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append(src[i:k + 1])
        idx = k + 1


def check_context_filter() -> list:
    """❗每个富途交易上下文构造点都必须显式传 ``filter_trdmarket``。

    ``futu.OpenSecTradeContext`` 的默认值是 ``TrdMarket.HK``。不传这个参数
    就**只看得见港股账户** —— 美股 / A 股模拟账户被服务端静默过滤掉，
    既不报错也不告警（实测：默认 2 个港股模拟账户 vs ``NONE`` 10 个账户）。

    这是本模块最隐蔽的坑，所以用静态扫描钉死：漏传一处就报出来。
    """
    failures = []
    total = 0
    for path in (EXEC_PY, SYNCER_PY):
        src = path.read_text(encoding="utf-8")
        for callee in CONTEXT_CALLEES:
            for snip in _call_snippets(src, callee):
                total += 1
                if "filter_trdmarket" not in snip:
                    flat = " ".join(snip.split())[:110]
                    failures.append(
                        f"{path.name}：构造 {callee.rstrip('(')} 时未传 filter_trdmarket"
                        f"（SDK 默认 TrdMarket.HK，会漏掉美股/A股账户）: {flat}")
    if total == 0:
        failures.append("一个富途交易上下文构造点都没扫到 —— 这条守卫的扫描规则已失效")
    return failures


# ---------------------------------------------------------------- ② 纯函数

def check_pure(mod) -> list:
    failures = []

    def eq(got, want, label):
        if got != want:
            failures.append(f"{label}: 得到 {got!r}，应为 {want!r}")

    # 市场判定
    eq(mod.infer_market("HK.06666")[0], "HK", "带前缀港股")
    eq(mod.infer_market("US.NVDA")[0], "US", "带前缀美股（富途前缀式）")
    eq(mod.infer_market("NVDA.US")[0], "US", "后缀式 NVDA.US 必须认出来（事件里就是这个写法）")
    eq(mod.infer_market("600519.SH")[0], "CN", "后缀式 600519.SH → A 股")
    eq(mod.infer_market("SH.600519")[0], "CN", "SH 前缀归 CN（模拟账户按 CN 授权）")
    eq(mod.infer_market("SZ.000001")[0], "CN", "SZ 前缀归 CN")
    eq(mod.infer_market("06666")[0], "HK", "5 位数字 → 港股")
    eq(mod.infer_market("000001")[0], "CN", "6 位数字 → A 股（与港股同形，靠位数区分）")
    eq(mod.infer_market("1234")[0], "", "4 位数字判不出市场")
    eq(mod.infer_market("")[0], "", "空代码判不出市场")
    eq(mod.infer_market("zzzznotreal")[0], "", "不在美股注册表内的裸字母不许猜市场")
    eq(mod.infer_market("AA.BB")[0], "", "前后缀都不是市场标记 → 不许猜")

    # ❗裸字母凭什么算美股：必须命中系统自有注册表（而不是"字母一律美股"）
    eq(mod.infer_market("nvda")[0], "US", "注册表内的裸字母 → 美股")
    eq(mod.infer_market("NVDA")[0], "US", "注册表匹配大小写不敏感")
    eq(mod.infer_market("zzzznotreal", {"market": "US"})[0], "US", "注册表没命中但信号明确声称 US")
    eq(mod.infer_market("zzzznotreal", {"market": "CN"})[0], "", "注册表没命中且声称 CN → 跳过")
    # ❗主生产者（market_hotspot）从不填 market → 恒为默认值 CN。
    # 注册表命中时必须以注册表为准，否则美股信号会被判成 A 股下到 A 股账户。
    eq(mod.infer_market("nvda", {"market": "CN"})[0], "US", "信号声称 CN 不得把 nvda 判成 A 股")
    eq(mod.infer_market("nvda", {"signal_event": {"market": "CN"}})[0], "US",
       "嵌套 signal_event.market 同样不得翻案")
    if not mod.infer_market("1234")[1]:
        failures.append("判不出市场时必须给出原因（不能返回空理由）")

    # 注册表必须真能加载 —— 加载失败会让裸字母代码**静默全部跳过**
    usyms = mod.us_symbols()
    if not usyms or "nvda" not in usyms:
        failures.append(f"美股注册表没加载出来（裸字母代码会静默全部失效）: {len(usyms)} 条")

    # 代码规范化
    eq(mod.futu_code("HK", "06666"), "HK.06666", "港股代码补零")
    eq(mod.futu_code("HK", "6666"), "HK.06666", "港股短代码补零到 5 位")
    eq(mod.futu_code("HK", "100"), "HK.00100", "港股代码补零（00100）")
    eq(mod.futu_code("HK", "HK.06666"), "HK.06666", "已带前缀不重复拼接")
    eq(mod.futu_code("US", "nvda"), "US.NVDA", "美股代码大写")
    eq(mod.futu_code("CN", "600519"), "SH.600519", "A 股沪市 → SH 前缀（富途没有 CN. 前缀）")
    eq(mod.futu_code("CN", "000001"), "SZ.000001", "A 股深市 → SZ 前缀")
    eq(mod.futu_code("CN", "300750"), "SZ.300750", "A 股创业板 → SZ 前缀")
    eq(mod.futu_code("CN", "88888"), "", "认不出交易所的 6 位码 → 空串（拒绝报单）")

    # ❗Market 枚举里**没有 CN** —— 必须落到 SH/SZ，且不许静默回落港股
    try:
        import futu as _futu
    except Exception:
        _futu = None
        print("⏭️  未安装 futu，跳过行情/交易市场枚举断言")
    if _futu is not None:
        eq(mod.quote_market("CN", "600519"), _futu.Market.SH, "A 股行情市场必须是 SH")
        eq(mod.quote_market("CN", "000001"), _futu.Market.SZ, "A 股行情市场必须是 SZ")
        eq(mod.quote_market("US", "nvda"), _futu.Market.US, "美股行情市场")
        eq(mod.quote_market("HK", "06666"), _futu.Market.HK, "港股行情市场")
        if mod.quote_market("XX", "y") is not None:
            failures.append("未知市场必须返回 None —— 回落港股会静默拿错市场查行情")
        if mod.quote_market("CN", "88888") is not None:
            failures.append("A 股认不出交易所时不得回落任何市场")
        # ❗交易账户过滤必须显式：默认值 TrdMarket.HK 会漏掉美股/A股模拟账户
        eq(mod.trd_market("CN"), _futu.TrdMarket.CN, "A 股账户过滤市场")
        eq(mod.trd_market("SH"), _futu.TrdMarket.CN, "SH 归 CN 账户")
        eq(mod.trd_market("US"), _futu.TrdMarket.US, "美股账户过滤市场")
        if mod.trd_market("XX") is not None:
            failures.append("未知市场必须返回 None（默认 TrdMarket.HK 会静默锁死港股）")

    # 限价对齐最小价差 —— 不对齐会被富途直接拒单
    eq(mod.round_to_tick(227.325, 0.01), 227.32, "美股限价对齐 0.01")
    eq(mod.round_to_tick(1.205, 0.001), 1.205, "港股限价对齐 0.001")
    eq(mod.round_to_tick(619.7, 0.2), 619.6, "港股大价差档 0.2")
    eq(mod.round_to_tick(0.5678, 0.0001), 0.5678, "美股低价档 0.0001")
    eq(mod.round_to_tick(100.0, 0), 0.0, "取不到最小价差 → 0（拒绝凭猜报单）")
    eq(mod.round_to_tick(0.0, 0.01), 0.0, "价格为 0 → 0")

    # 整手折算
    eq(mod.floor_to_lot(10000.0, 1.205, 500), 8000, "向下取整到手（16 手 × 500）")
    eq(mod.floor_to_lot(500.0, 1.205, 500), 0, "买不起一手 → 0")
    eq(mod.floor_to_lot(10000.0, 0.0, 500), 0, "价格为 0 → 0")
    eq(mod.floor_to_lot(10000.0, 10.0, 0), 0, "每手为 0 → 0")
    eq(mod.floor_to_lot(0.0, 10.0, 100), 0, "金额为 0 → 0")
    eq(mod.floor_to_lot(602500.0, 1.205, 500), 500000, "正好整手（1000 手）")
    eq(mod.floor_to_lot(37358.0, 373.58, 1), 100, "美股每手 1 股（可任意股数）")

    # 后端选择语义
    saved = {k: os.environ.get(k) for k in (mod.ENV_BACKEND, mod.ENV_SIM_MARKETS)}
    try:
        os.environ.pop(mod.ENV_BACKEND, None)
        eq(mod.selected_backend_name(), mod.BACKEND_VIRTUAL, "未配置时默认虚拟仓")
        eq(mod.futu_sim_enabled(), False, "未配置时不应启用模拟报单")
        os.environ[mod.ENV_BACKEND] = mod.BACKEND_FUTU_SIM
        eq(mod.selected_backend_name(), mod.BACKEND_FUTU_SIM, "显式开启模拟报单")
        os.environ[mod.ENV_BACKEND] = "nonsense"
        eq(mod.selected_backend_name(), mod.BACKEND_VIRTUAL, "未知配置回落虚拟仓")
        os.environ[mod.ENV_BACKEND] = "FUTU_SIM"
        eq(mod.selected_backend_name(), mod.BACKEND_FUTU_SIM, "大小写不敏感")

        os.environ[mod.ENV_SIM_MARKETS] = "hk, us"
        eq(sorted(mod.sim_markets()), ["HK", "US"], "白名单解析 + 大写归一")
        os.environ.pop(mod.ENV_SIM_MARKETS, None)
        eq(sorted(mod.sim_markets()), ["CN", "HK", "US"],
           "白名单默认应含三个已开通市场（港股/A股/美股模拟账户都在 OpenD 上）")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return failures


# ---------------------------------------------------------------- ③ 幂等槽位

def check_slots(mod) -> list:
    failures = []

    key = mod.order_slot_key("HK", "06666", "buy", day="20260101")
    if not mod.claim_order_slot(key):
        failures.append("首次认领槽位失败")
    if mod.claim_order_slot(key):
        failures.append("同一槽位被重复认领 —— 幂等失效，会重复下单")
    if not mod.slot_taken(key):
        failures.append("已认领的槽位查询不到")
    mod.release_order_slot(key)
    if mod.slot_taken(key):
        failures.append("归还槽位失败 —— 该标的当天再也下不出单")
    mod.release_order_slot(key)  # 二次归还不许抛

    # 键必须区分市场/标的/方向/日期
    keys = {
        mod.order_slot_key("HK", "06666", "buy", day="20260101"),
        mod.order_slot_key("HK", "06666", "sell", day="20260101"),
        mod.order_slot_key("US", "06666", "buy", day="20260101"),
        mod.order_slot_key("HK", "00100", "buy", day="20260101"),
        mod.order_slot_key("HK", "06666", "buy", day="20260102"),
    }
    if len(keys) != 5:
        failures.append(f"槽位键维度不足，{5} 种情形只产生 {len(keys)} 个键")

    # ❗tag 必须能开出**同标的同方向**的新槽位：做 T 一天要跑好几轮，
    #  默认键（日期+市场+标的+方向）只有一个，第二轮会被幂等挡掉。
    untagged = mod.order_slot_key("HK", "06666", "sell", day="20260101")
    tagged = {
        mod.order_slot_key("HK", "06666", "sell", day="20260101", tag="round_1"),
        mod.order_slot_key("HK", "06666", "sell", day="20260101", tag="round_2"),
        untagged,
    }
    if len(tagged) != 3:
        failures.append(f"slot_tag 未区分出不同轮次，{3} 个情形只产生 {len(tagged)} 个键")
    # 只比对**带 tag**的那两个：不带 tag 的那个本来就应该等于 keys 里的成员
    if any(k in keys for k in tagged if k != untagged):
        failures.append("带 tag 的键与不带 tag 的键撞车（会误拦或误放行）")

    # 并发认领：同一键 8 线程 × 40 次，必须**恰好** 1 次成功
    concur_key = mod.order_slot_key("HK", "00001", "buy", day="20260101")
    wins = []
    lock = threading.Lock()

    def worker():
        for _ in range(40):
            if mod.claim_order_slot(concur_key):
                with lock:
                    wins.append(1)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if sum(wins) != 1:
        failures.append(f"并发认领同一槽位成功了 {sum(wins)} 次，应恰好 1 次（会重复下单）")

    # 不同键互不干扰（避开上面已占用的 00001）
    codes = [f"{20000 + i:05d}" for i in range(60)]
    results = [mod.claim_order_slot(mod.order_slot_key("HK", c, "buy", day="20260101"))
               for c in codes]
    if not all(results):
        failures.append("不同标的的槽位互相干扰（应各自独立成功）")
    # 反方向：同一标的重复认领必须失败（一条保护不能掩盖另一条）
    again = [mod.claim_order_slot(mod.order_slot_key("HK", c, "buy", day="20260101"))
             for c in codes]
    if any(again):
        failures.append("已占用的标的槽位又被认领成功（幂等失效）")
    # 方向/日期的反方向：换个方向或换天，必须能再次认领
    fresh = [
        mod.claim_order_slot(mod.order_slot_key("HK", codes[0], "sell", day="20260101")),
        mod.claim_order_slot(mod.order_slot_key("HK", codes[0], "buy", day="20260102")),
    ]
    if not all(fresh):
        failures.append("换方向/换天后仍无法认领（幂等键维度过多，会误拦真实订单）")

    return failures


# ---------------------------------------------------------------- ④ 后端选择

class _FakeSyncer:
    def __init__(self, targets):
        self._targets = targets

    def get_sync_targets(self):
        return list(self._targets), [], {"FUTUSECURITIES"}


class _FakePosition:
    def __init__(self, **kw):
        self.position_id = "VP_X_1"
        self.quantity = kw.get("amount", 0) / kw.get("price", 1)
        self.entry_price = kw.get("price", 1)


class _FakePortfolio:
    def __init__(self, position=None, boom=False):
        self.calls = []
        self._position = position
        self._boom = boom

    def open_position(self, **kw):
        self.calls.append(kw)
        if self._boom:
            raise RuntimeError("虚拟仓炸了")
        return self._position


class _FakeSignal:
    def __init__(self, code, **kw):
        self.signal_id = "SIG-1"
        self.strategy_id = "river_main"
        self.strategy_name = "River"
        self.stock_code = code
        self.stock_name = code
        self.signal_type = "BUY"
        self.price = kw.get("price", 1.205)
        self.confidence = 0.8
        self.timestamp = 0.0
        self.raw_data = kw.get("raw_data", {})
        self.market_time = 0.0


def check_backends(mod, sandbox) -> list:
    failures = []
    hk_target = {
        "name": "FutuSimHK", "firm": "FUTUSECURITIES", "acc_id": 1973930,
        "card_num": "", "market_auth": ["HK"], "acc_type": "CASH", "trd_env": "SIMULATE",
    }

    # ---------- 装配：默认与未知都必须是虚拟仓 ----------
    portfolio = _FakePortfolio(position=_FakePosition(price=1.205, amount=10000))
    if not isinstance(mod.resolve_backend(portfolio=portfolio), mod.VirtualPortfolioBackend):
        failures.append("默认装配的不是虚拟仓后端")
    if not isinstance(mod.resolve_backend("nonsense", portfolio=portfolio), mod.VirtualPortfolioBackend):
        failures.append("未知后端名没有回落虚拟仓")
    if not isinstance(mod.resolve_backend(mod.BACKEND_FUTU_SIM, portfolio=portfolio), mod.FutuSimBackend):
        failures.append("显式指定 futu_sim 未装配模拟后端")

    # ---------- 虚拟仓后端 ----------
    sig = _FakeSignal("nvda", price=100.0)
    out = mod.VirtualPortfolioBackend(portfolio).submit(
        signal=sig, plan=None, side="buy", price=100.0, amount=10000.0)
    if not out.acted or out.position_id != "VP_X_1":
        failures.append("虚拟仓后端未按预期开仓")
    if out.backend != mod.BACKEND_VIRTUAL:
        failures.append("虚拟仓后端名字不对")
    got = portfolio.calls[-1]
    if got["stock_code"] != "nvda" or got["amount"] != 10000.0:
        failures.append(f"虚拟仓后端透传参数有误: {got}")

    out = mod.VirtualPortfolioBackend(None).submit(
        signal=sig, plan=None, side="buy", price=100.0, amount=10000.0)
    if out.ok or not out.reason:
        failures.append("虚拟仓不可用时必须失败并给原因")

    out = mod.VirtualPortfolioBackend(_FakePortfolio(position=None)).submit(
        signal=sig, plan=None, side="buy", price=100.0, amount=10000.0)
    if out.ok or not out.reason:
        failures.append("虚拟开仓被拒时必须失败并给原因")

    out = mod.VirtualPortfolioBackend(_FakePortfolio(boom=True)).submit(
        signal=sig, plan=None, side="buy", price=100.0, amount=10000.0)
    if out.ok or "异常" not in out.reason:
        failures.append("虚拟开仓抛异常时必须失败并给原因（不能冒泡打断循环）")

    # ---------- 模拟后端：每道闸独立跳过 ----------
    class Probe(mod.FutuSimBackend):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.lot = 500
            self.tick = 0.001
            self.place_result = "OID-1"
            self.place_calls = []
            self.slot_alive_at_place = None
            self.boom = False
            #: 模拟仓里的可卖数量（卖腿闸门用）。默认 0 = 没有底仓
            self.avail_qty = 0.0

        def _query_security(self, market, code):
            return {"last_price": 1.205, "lot_size": self.lot, "price_spread": self.tick}

        def _available_qty(self, market, code, target):
            return self.avail_qty

        def _place(self, market, code, quantity, price, target, side="buy"):
            if self.boom:
                raise RuntimeError("连接断了")
            self.place_calls.append((market, code, quantity, price, target["acc_id"], side))
            # 记下"报单那一刻槽位是否已认领"，验证认领早于报单
            self.slot_alive_at_place = mod.slot_taken(mod.order_slot_key(market, code, side))
            return self.place_result

    def probe(**kw):
        targets = kw.pop("targets", [hk_target])
        p = Probe(syncer=_FakeSyncer(targets), **kw)
        return p

    gate_reasons = []

    def gate(label, sig, *, side="buy", price=1.205, amount=10000.0, whitelist=None, targets=None,
             lot=500, tick=0.001, place="OID-1", boom=False, avail_qty=0.0,
             expect_ok=False, **kw):
        p = probe(**({"markets": whitelist} if whitelist is not None else {}))
        if targets is not None:
            p._syncer = _FakeSyncer(targets)
        p.lot = lot
        p.tick = tick
        p.place_result = place
        p.boom = boom
        p.avail_qty = avail_qty
        out = p.submit(signal=sig, plan=None, side=side, price=price, amount=amount, **kw)
        # ❗只有"应当被拦下"的用例才计入 gate_reasons（后面要校验
        #   「每道闸都真的拦了」且原因两两不同）。成功路径的用例
        #   混进去会让这条不变量永远不成立。
        if not expect_ok:
            gate_reasons.append((label, out.skipped, out.reason))
        return out, p

    # ① 未知方向（买入/卖出之外）
    out, _ = gate("未知方向", _FakeSignal("06666"), side="short")
    if not (out.skipped and not out.ok):
        failures.append("未知方向必须跳过")

    # ①b 卖出：无底仓（can_sell_qty=0）必须跳过 —— 空仓卖不出东西
    # ❗每个卖出用例都要带**独立的 slot_tag**：否则先成交的那一个会把
    #   「日期+市场+标的+方向」这个槽位占掉，后面的用例全被幂等挡住 ——
    #   表现为"守卫红了"，实际是用例自己撞车。
    out, _ = gate("卖出无底仓", _FakeSignal("06666"), side="sell",
                  quantity=1000.0, avail_qty=0.0, slot_tag="g_nobase")
    if not (out.skipped and not out.ok):
        failures.append("卖出但模拟仓无可卖持仓时必须跳过")
    elif "can_sell_qty=0" not in out.reason:
        # ❗必须是这条**专属**原因：下面「计划量>可卖量→下调」也会拒绝，
        #   两条若共用"可卖"字样，去掉本闸时守卫会被另一条掩盖（假绿）。
        failures.append(f"卖出无底仓必须给出 can_sell_qty=0 的专属原因: {out.reason}")

    # ①c 卖出：可卖量不足一手必须跳过
    out, _ = gate("卖出不足一手", _FakeSignal("06666"), side="sell",
                  quantity=1000.0, avail_qty=100.0, lot=500, slot_tag="g_lot")
    if not (out.skipped and not out.ok):
        failures.append("可卖量不足一手时必须跳过")

    # ①d 卖出：计划量大于可卖量 → 按可卖量下调，且仍成交
    out, p = gate("卖出超可卖", _FakeSignal("06666"), side="sell", expect_ok=True,
                  quantity=5000.0, avail_qty=1200.0, lot=500, slot_tag="g_cap")
    if out.skipped or not out.ok:
        failures.append(f"计划卖 5000 但可卖 1200 时应按 1200 下调成交: {out.reason}")
    elif abs(out.quantity - 1000.0) > 1e-9:
        failures.append(f"可卖 1200 / 每手 500 应下调到 1000，实得 {out.quantity}")

    # ①e 卖出：真的走到 place_order 且方向是 sell
    out, p = gate("卖出成交", _FakeSignal("06666"), side="sell", expect_ok=True,
                  quantity=1000.0, avail_qty=5000.0, slot_tag="g_ok")
    if not out.ok:
        failures.append(f"有底仓时卖单应成交: {out.reason}")
    elif not p.place_calls or p.place_calls[-1][5] != "sell":
        failures.append("卖单没有以 sell 方向送到 place_order")
    # ② 判不出市场
    out, _ = gate("判不出市场", _FakeSignal("1234"))
    if not out.skipped:
        failures.append("判不出市场必须跳过")
    # ③ 市场不在白名单（把白名单收窄到 HK，A 股信号必须被挡）
    out, _ = gate("白名单外", _FakeSignal("000001"), whitelist=["HK"])
    if not out.skipped:
        failures.append("白名单外市场必须跳过")
    # ④ 找不到模拟账户
    out, _ = gate("无模拟账户", _FakeSignal("06666"), targets=[])
    if not out.skipped:
        failures.append("找不到模拟账户必须跳过")
    # ⑤ 取不到每手股数
    out, _ = gate("无每手股数", _FakeSignal("06666"), lot=0)
    if not out.skipped:
        failures.append("取不到每手股数必须跳过（不许凭猜报单）")
    # ⑥ 取不到最小价差 —— 限价精度不合规会被富途直接拒单
    out, _ = gate("无最小价差", _FakeSignal("06666"), tick=0.0)
    if not out.skipped:
        failures.append("取不到最小价差必须跳过（不许回落到某个默认精度）")
    # ⑦ 金额买不起一手
    out, _ = gate("买不起一手", _FakeSignal("06666", price=1.205), amount=500.0)
    if not out.skipped:
        failures.append("买不起一手必须跳过")
    # ⑧ 价格无效
    out, _ = gate("价格无效", _FakeSignal("06666", price=0.0), price=0.0)
    if not out.skipped:
        failures.append("价格无效必须跳过")
    # ⑨ 金额无效
    out, _ = gate("金额无效", _FakeSignal("06666"), amount=0.0)
    if not out.skipped:
        failures.append("金额无效必须跳过")

    # 所有跳过原因必须**两两不同**且非空 —— 一条保护不能掩盖另一条
    reason_texts = [r for _, skipped, r in gate_reasons if skipped]
    if len(reason_texts) != len(gate_reasons):
        failures.append(f"有 {len(gate_reasons) - len(reason_texts)} 道闸没有跳过")
    if len(set(reason_texts)) != len(reason_texts):
        dup = [r for r in reason_texts if reason_texts.count(r) > 1]
        failures.append(f"跳过原因重复，守卫无区分度: {sorted(set(dup))}")
    if any(not r.strip() for r in reason_texts):
        failures.append("存在空的跳过原因（前端只会显示一句笼统的失败）")

    # ⑨ 槽位已占用
    sig = _FakeSignal("06666")
    taken = mod.order_slot_key("HK", "06666", "buy")
    mod.claim_order_slot(taken)
    out, p = gate("槽位占用", sig)
    if not out.skipped or "幂等" not in out.reason:
        failures.append(f"槽位已占用时必须跳过并说明幂等，实得: {out.reason!r}")
    if p.place_calls:
        failures.append("槽位已占用时仍然报了单")
    mod.release_order_slot(taken)

    # ⑩ 报单失败 → 必须归还槽位
    out, p = gate("报单失败", sig, place="")
    if out.ok or not out.reason:
        failures.append("报单未返回单号时必须失败")
    if mod.slot_taken(taken):
        failures.append("报单失败后槽位没归还 —— 该标的当天再也下不出单")

    # ⑪ 报单抛异常 → 必须归还槽位且不冒泡
    out, p = gate("报单异常", sig, boom=True)
    if out.ok or "异常" not in out.reason:
        failures.append("报单抛异常时必须失败并给原因")
    if mod.slot_taken(taken):
        failures.append("报单异常后槽位没归还")

    # ⑫ 正常路径
    out, p = gate("正常", sig, place="OID-9")
    if not out.acted:
        failures.append(f"正常路径应成功，实得 skipped={out.skipped} reason={out.reason!r}")
    else:
        if out.order_id != "OID-9":
            failures.append("成功路径未带回单号")
        if out.quantity != mod.floor_to_lot(10000.0, 1.205, 500):
            failures.append(f"下单股数未按整手折算: {out.quantity}")
        if int(out.quantity) % 500 != 0:
            failures.append(f"下单股数不是每手整数倍: {out.quantity}")
        if not p.slot_alive_at_place:
            failures.append("报单发生在认领槽位之前（并发下会重复下单）")
        if p.place_calls[-1][3] != 1.205 or p.place_calls[-1][2] != int(out.quantity):
            failures.append(f"报单参数有误: {p.place_calls[-1]}")
        if not mod.slot_taken(taken):
            failures.append("成功后槽位应保持占用（否则当天会重复下单）")
    mod.release_order_slot(taken)

    # ⑬ 买入：**给了计划股数就按计划股数下**，不许拿 amount 重算
    #    ❗实盘教训（做 T 补底仓）：计划 5900 股 @0.9858 → 限价被对齐到最小价差
    #    0.986 → 从 amount 反算成 5800 股，少买一手。成因是「同一个量算了两遍」。
    _qty, _price, _tick, _lot = 5000.0, 1.2055, 0.001, 100
    out, p = gate("买入按计划股数", _FakeSignal("06666"), side="buy", expect_ok=True,
                  price=_price, tick=_tick, lot=_lot,
                  quantity=_qty, amount=_qty * _price, slot_tag="g_buyqty")
    _amt_derived = mod.floor_to_lot(
        _qty * _price, mod.round_to_tick(_price, _tick), _lot
    )
    # ❗前提校验：本用例必须能「区分认股数 vs 从金额反算」，否则恒真 ——
    #   挑参数时要保证两者不相等（这里刻意让限价向上取整制造偏差）。
    if abs(_amt_derived - _qty) < 1e-9:
        failures.append(
            "用例失效：amount 反算与计划股数相同，无法区分两种实现（换参数）"
        )
    if not out.acted:
        failures.append(f"买入给了计划股数应成交，实得 skipped={out.skipped} {out.reason!r}")
    elif abs(out.quantity - _qty) > 1e-9:
        failures.append(
            f"买入未按计划股数执行：给 {_qty:.0f}，实得 {out.quantity:.0f}"
            f"（从 amount 反算会得到 {_amt_derived:.0f} —— 正是本用例要防的偏差）"
        )

    # 落流水：成功与跳过都要留痕（跳过也要可审计）
    journal = mod.read_journal(limit=50)
    if not journal:
        failures.append("执行流水为空 —— 跳过/失败事后无从追溯")
    else:
        if not any(rec.get("skipped") for rec in journal):
            failures.append("跳过没有进流水（无法回答'为什么没下单'）")
        if not any(rec.get("ok") for rec in journal):
            failures.append("成功没有进流水")

    return failures


# ---------------------------------------------------------------- ⑤ 环境隔离

def check_env_isolation(sandbox) -> list:
    """模拟同步绝不能清掉实盘账户 —— 这是接入前最危险的一条。"""
    failures = []
    try:
        syncer_mod = sandbox.load_syncer()
    except Exception as e:
        return [f"无法加载同步器: {e}"]

    existing = {"FutuHK", "MoomooUS", "Spark", "FutuSimHK", "FutuSimHKOption",
                "FutuSimUS", "FutuSimCN"}

    # 模拟：7 个品牌全部探测成功，也只许清 FutuSim 前缀
    sim = syncer_mod.FutuPortfolioSyncer(trd_env="SIMULATE")
    all_firms = set(syncer_mod.SECURITY_FIRM_ACCOUNT_NAMES)
    stale = sim._stale_account_names(
        existing, {"FutuSimHK", "FutuSimHKOption"}, all_firms)
    if stale & {"FutuHK", "MoomooUS", "Spark"}:
        failures.append(f"模拟同步会清掉实盘账户: {sorted(stale)}（跑一次模拟同步即抹掉全部实盘持仓）")
    if "FutuSimHKOption" in stale:
        failures.append("模拟同步把本次成功写库的账户也清了")

    # 模拟账户确实消失时才清
    stale = sim._stale_account_names(existing, {"FutuSimHK"}, all_firms)
    if "FutuSimHKOption" not in stale:
        failures.append("模拟账户已消失却仍保留（留下永不更新的僵尸块）")

    # 真实：不许碰 FutuSim 前缀
    real = syncer_mod.FutuPortfolioSyncer(trd_env="REAL")
    stale = real._stale_account_names(
        existing, {"FutuHK", "MoomooUS"}, {"FUTUSECURITIES", "FUTUINC"})
    if stale & {"FutuSimHK", "FutuSimHKOption"}:
        failures.append(f"真实同步会清掉模拟账户: {sorted(stale)}")

    # 模拟目标命名：三市场 + 同市场多品类都必须唯一
    sim_rows = [
        {"acc_id": 1973930, "market_auth": ["HK"], "sim_acc_type": "STOCK"},
        {"acc_id": 10836386, "market_auth": ["HK"], "sim_acc_type": "OPTION"},
        {"acc_id": 1973932, "market_auth": ["CN"], "sim_acc_type": "STOCK"},
        {"acc_id": 10819487, "market_auth": ["US"], "sim_acc_type": "STOCK_AND_OPTION"},
    ]
    names = [sim._sim_target_name(r) for r in sim_rows]
    if len(set(names)) != len(sim_rows):
        failures.append(f"模拟账户命名撞车: {names}")
    want = ["FutuSimCN", "FutuSimHK", "FutuSimHKOption", "FutuSimUS"]
    if sorted(names) != want:
        failures.append(f"模拟账户命名不符合预期: {sorted(names)}，应为 {want}")
    if any(syncer_mod.SIM_ACCOUNT_PREFIX not in n for n in names):
        failures.append(f"模拟账户名未带统一前缀: {names}")

    # ❗显式传 filter_trdmarket=NONE 后枚举结果里会多出 DISABLED 的真实子账户，
    # 必须剔除 —— 对着停用账户反复取数只会把页面徽章刷红
    mixed_rows = [
        {"acc_id": 1, "card_num": "1001367909756791", "acc_type": "MARGIN",
         "acc_status": "ACTIVE", "trd_env": "REAL", "market_auth": ["HK", "US"]},
        {"acc_id": 2, "card_num": "1001100101085018", "acc_type": "MARGIN",
         "acc_status": "DISABLED", "trd_env": "REAL", "market_auth": ["HK"]},
    ]
    picked = real._select_main_accounts(mixed_rows)
    if any(r["acc_id"] == 2 for r in picked):
        failures.append("停用（DISABLED）的账户仍被选中 —— 会一直刷同步失败")
    if not any(r["acc_id"] == 1 for r in picked):
        failures.append("正常（ACTIVE）的主账户没被选中 —— 过滤把该留的也滤掉了")

    return failures


# ---------------------------------------------------------------- 主检查

def check() -> int:
    sandbox = Sandbox()
    try:
        mod = sandbox.load()
    except Exception as e:
        print(f"❌ 无法加载被测模块: {e}")
        sandbox.close()
        return 1

    print(f"被测模块：{EXEC_PY.relative_to(REPO)}")
    print(f"          {ADAPTIVE_PY.relative_to(REPO)}")

    static_fail = []
    for path, pattern, desc in STATIC_RULES:
        if not re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE):
            static_fail.append(f"{path.name}：{desc}")
    for path, pattern, desc in STATIC_FORBIDDEN:
        if re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE):
            static_fail.append(f"{path.name}：{desc}")

    sections = [
        ("静态（后端开关/原子认领/整数手/失败归还）", static_fail),
        ("静态 · 交易上下文必须显式指定市场过滤", check_context_filter()),
        ("契约 · 市场判定、代码换算与限价对齐", check_pure(mod)),
        ("契约 · 幂等槽位（含并发）", check_slots(mod)),
        ("契约 · 后端装配与九道闸", check_backends(mod, sandbox)),
        ("契约 · 模拟/真实环境隔离", check_env_isolation(sandbox)),
    ]

    bad = 0
    for title, failures in sections:
        if failures:
            bad += 1
            print(f"❌ {title}：")
            for f in failures:
                print(f"    - {f}")
        else:
            print(f"✅ {title}：通过")

    sandbox.close()
    if bad:
        return 1
    print("\n✅ 通过：默认不报单、每道闸独立可辨、失败必归还槽位、模拟同步不碰实盘账户")
    return 0


# ---------------------------------------------------------------- 自证

def self_test() -> int:
    """规则有区分度：把源码改成"全坏"版本，必须被规则抓到。"""
    failures = []
    sandbox = Sandbox()
    try:
        mod = sandbox.load()
    except Exception as e:
        print(f"❌ 无法加载: {e}")
        sandbox.close()
        return 1

    # 每条静态规则都必须能在真实源码里命中（否则是写错的空规则）
    for path, pattern, desc in STATIC_RULES:
        if not re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE):
            failures.append(f"静态规则命中不了真实源码（规则写错了）：{desc}")
    for path, pattern, desc in STATIC_FORBIDDEN:
        if re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE):
            failures.append(f"禁用规则命中了真实源码：{desc}")

    # 行为检查必须有区分度：把关键函数替换成"错版本"，必须报错
    good_floor = mod.floor_to_lot
    mod.floor_to_lot = lambda amount, price, lot_size: int(amount // price) if price > 0 else 0
    try:
        if not check_pure(mod):
            failures.append("把整手折算换成不取整版本，check_pure 竟然全绿（无区分度）")
    finally:
        mod.floor_to_lot = good_floor

    good_name = mod.selected_backend_name
    mod.selected_backend_name = lambda: mod.BACKEND_FUTU_SIM
    try:
        if not check_pure(mod):
            failures.append("把默认后端换成 futu_sim，check_pure 竟然全绿（无区分度）")
    finally:
        mod.selected_backend_name = good_name

    good_us = mod.us_symbols
    mod.us_symbols = lambda: frozenset()
    try:
        if not check_pure(mod):
            failures.append("把美股注册表清空，check_pure 竟然全绿"
                            "（注册表加载失败会让裸字母静默全部跳过）")
    finally:
        mod.us_symbols = good_us

    good_tick = mod.round_to_tick
    mod.round_to_tick = lambda price, tick: price
    try:
        if not check_pure(mod):
            failures.append("把限价对齐换成不做对齐，check_pure 竟然全绿（无区分度）")
    finally:
        mod.round_to_tick = good_tick

    good_quote = mod.quote_market
    mod.quote_market = lambda market, code="": None
    try:
        if not check_pure(mod):
            failures.append("把行情市场换成一律认不出，check_pure 竟然全绿（无区分度）")
    finally:
        mod.quote_market = good_quote

    # 交易上下文过滤扫描必须真的扫到构造点（规则写错会静默变成空检查）
    ctx_fail = check_context_filter()
    if any("一个富途交易上下文构造点都没扫到" in f for f in ctx_fail):
        failures.append("交易上下文扫描规则失效（一个构造点都没扫到）")
    if ctx_fail:
        failures.append(f"真实源码里存在未传 filter_trdmarket 的构造点: {ctx_fail}")

    sandbox.close()
    if failures:
        print("❌ 自证失败：")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("✅ 自证通过：静态规则均命中真实源码，且行为检查有区分度")
    return 0


# ---------------------------------------------------------------- 注入

def exercise_injections() -> int:
    """逐例注入 → check() 必须报错 → 立即还原并确认。"""
    backups = {}
    problems = []

    for inj in INJECTIONS:
        path = inj["file"]
        original = path.read_text(encoding="utf-8")
        backups[path] = original
        if inj["old"] not in original:
            problems.append(f"[{inj['name']}] 注入锚点找不到，用例已失效")
            continue

        path.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
        try:
            rc = check()
        finally:
            path.write_text(original, encoding="utf-8")

        if rc == 0:
            problems.append(f"[{inj['name']}] 注入后守卫仍然全绿 —— 这条保护是假的")
        else:
            print(f"✅ 注入被捕获：{inj['name']}")
        # 立即确认已还原（restore 覆盖后续改动是踩过的坑）
        if path.read_text(encoding="utf-8") != original:
            problems.append(f"[{inj['name']}] 还原失败，源码未复位")

    if problems:
        print("\n❌ 注入自证失败：")
        for p in problems:
            print(f"    - {p}")
        return 1
    print(f"\n✅ 注入自证通过：{len(INJECTIONS)} 例注入全部被捕获，且已还原")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="富途模拟执行后端守卫")
    ap.add_argument("--strict", action="store_true", help="严格模式（默认行为）")
    ap.add_argument("--self-test", action="store_true", help="隔离自证：规则有区分度")
    ap.add_argument("--exercise-injections", action="store_true", help="真实注入后必须报错")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.exercise_injections:
        return exercise_injections()
    return check()


if __name__ == "__main__":
    sys.exit(main())
