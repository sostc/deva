#!/usr/bin/env python3
"""守卫：富途持仓同步必须覆盖**所有品牌**（含 moomoo），且每个账户独立成块

为什么有这个守卫
----------------
富途牛牛与 moomoo 共用同一套 OpenD + futu-api，靠 ``security_firm`` 区分品牌：
``FUTUSECURITIES`` = 富途证券（香港），``FUTUINC`` = moomoo 美国。而老实现

    security_firm: str = "FUTUSECURITIES"      # 构造函数里写死一个品牌

于是无论用户开了多少 moomoo 账户，**同步器只会连富途香港**：实测用户
moomoo 美国的 6 只持仓（含 NVDA）从来没进过页面，且不报任何错 —— 页面上
数字看着齐全，其实缺了一整个账户。这正是最该防的形状：静默漏数据。

本守卫盯住三层
--------------
① 静态：品牌表必须含 moomoo、逐品牌遍历、逐账户同步、position_id 用**真实
   市场**前缀；并且把「写死单一品牌」的老写法列为**禁止模式**（回归即报错）。
② 契约：主账户选择规则、僵尸账户清理规则、币种判定、整体成败语义 ——
   尤其两条容易写错且后果很重的不变量：
     * 品牌**探测失败**时不得清理它的旧数据（一次网络抖动不能把页面清空）；
     * 持仓成本必须取 ``average_cost``，**不得**回落到 ``cost_price``
       （后者是摊薄成本口径，会把亏损显示成盈利）。
③ 覆盖：每个账户的持仓能原样喂给 ``USStockPosition``（键集合与 dataclass
   字段对齐，多一个会 TypeError、少一个也会 TypeError）。

负向注入 3 例（真实改源码，逐例立即还原）：删掉 moomoo 品牌、去掉
「探测失败不清」的守卫、把 position_id 改回写死的 ``US_`` 前缀。

刻意不 import deva 包：既避免初始化生产库/日志（守卫不得有副作用），
也让本守卫在没装 futu-api 的环境里照样能跑。
"""

import argparse
import ast
import importlib.util
import re
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANDIT = REPO / "deva" / "naja" / "bandit"

SYNCER_PY = BANDIT / "futu_portfolio_syncer.py"
FRESHNESS_PY = BANDIT / "data_freshness.py"
UI_PY = BANDIT / "ui.py"
PM_PY = BANDIT / "portfolio_manager.py"

# ---------------------------------------------------------------- ① 静态

# (文件, 必须匹配的正则, 说明)
STATIC_RULES = [
    (SYNCER_PY, r'"FUTUSECURITIES":\s*"FutuHK"',
     "品牌表缺少 富途香港(FUTUSECURITIES → FutuHK)"),
    (SYNCER_PY, r'"FUTUINC":\s*"MoomooUS"',
     "品牌表缺少 moomoo 美国(FUTUINC → MoomooUS) —— 本次漏数据的根因就是它"),
    (SYNCER_PY, r'LEGACY_ACCOUNT_NAMES\s*=\s*frozenset\(\s*\{\s*"FutuReal"\s*\}\s*\)',
     "缺少旧账户名清理表（改名后旧记录会变成永不更新的僵尸账户）"),
    (SYNCER_PY, r"for firm in self\.firms:",
     "未遍历品牌列表（写死单一品牌就会漏掉 moomoo）"),
    (SYNCER_PY, r"for target in targets:",
     "未逐账户同步（只同步一个账户会漏掉其余账户的持仓）"),
    (SYNCER_PY, r'position_id = f"\{market\}_\{name\}_\{code\}"',
     'position_id 未使用真实市场前缀（港股会被标成 US_xxx）'),
    (SYNCER_PY, r"if firm not in probed_ok:\s*\n\s*continue",
     "缺少「品牌探测失败则不清旧数据」的保护（一次网络抖动会清空页面）"),
    (SYNCER_PY, r'currency = self\._decide_account_currency\(target, positions\)',
     "资金查询未按账户本币口径（港币净资产会被标成美元）"),
    (SYNCER_PY, r'return decide_currency\(target\["firm"\], positions\)',
     "币种决断丢失「按持仓多数决」口径"),
    (SYNCER_PY, r'if not positions and self\._is_simulate\(\):',
     "模拟账户无持仓时退回品牌币种（美股模拟盘会被凭空标成 HKD）"),
    (SYNCER_PY, r'SIM_ACCOUNT_PREFIX\s*=\s*"FutuSim"',
     "缺少模拟账户统一前缀（模拟账户顶着品牌名 → 7 个品牌互相重名）"),
    (SYNCER_PY, r'selected = \[r for r in selected if r\["acc_id"\] not in seen_acc_ids\]',
     "模拟账户未跨品牌按 acc_id 去重（同一批账户会被写 7 遍）"),
    (SYNCER_PY, r'name = self\._sim_target_name\(row\)',
     "模拟账户未用无品牌命名（同市场「股票+期权」模拟账户会撞名）"),
    (SYNCER_PY, r'if self\._is_simulate\(\):\s*\n\s*for name in existing:',
     "僵尸清理未按环境隔离（跑一次模拟同步会抹掉 FutuHK/MoomooUS 实盘账户）"),
    (SYNCER_PY, r'if r\["card_num"\]',
     "缺「按 uni_card_num 识别主账户」的规则（查子账户会拿到空持仓）"),
    (UI_PY, r"for acc in result\.accounts:",
     "同步按钮未逐账户交代成败（半成功会被说成成功）"),
    (UI_PY, r"for account_name in all_account_names:",
     "缺失逐账户渲染持仓块"),
]

# (文件, 禁止匹配的正则, 说明) —— 老写法回归即报错
STATIC_FORBIDDEN = [
    (SYNCER_PY, r'security_firm:\s*str\s*=\s*"FUTUSECURITIES"',
     "构造函数又把品牌写死成单一 FUTUSECURITIES（本次事故的原形状）"),
    (SYNCER_PY, r'position_id = f"US_\{',
     'position_id 又写死了 "US_" 前缀'),
    (SYNCER_PY, r'row\.get\(\s*"cost_price"',
     "成本价回落到 cost_price —— 摊薄成本口径会把亏损显示成盈利"),
    (SYNCER_PY, r'row\.get\(\s*"pl_ratio"\s*[,)]',
     "盈亏比例回落到 pl_ratio —— 摊薄成本口径，与 APP 显示不一致"),
    (SYNCER_PY, r'set\(accounts_data\),\s*set\(payloads\)',
     "僵尸清理把「本轮取数成功」当成「账户还活着」——取数失败即删账户"),
]

# 负向注入：改一处源码，check() 必须报错
INJECTIONS = [
    {
        "name": "品牌表里删掉 moomoo 美国（回到只连富途香港）",
        "file": SYNCER_PY,
        "old": '    "FUTUINC": "MoomooUS",',
        "new": "",
    },
    {
        "name": "去掉「品牌探测失败则不清旧数据」的守卫",
        "file": SYNCER_PY,
        "old": "            if firm not in probed_ok:\n                continue\n",
        "new": "",
    },
    {
        "name": 'position_id 改回写死的 "US_" 前缀',
        "file": SYNCER_PY,
        "old": 'position_id = f"{market}_{name}_{code}"',
        "new": 'position_id = f"US_{name}_{code}"',
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
    sys.modules[name] = mod          # 必须先登记：@dataclass 解析注解要靠它
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _load_syncer():
    """按文件路径加载被测模块，用桩件替代 deva 包（守卫不碰生产库）。"""
    def _no_db(*_a, **_k):
        raise RuntimeError("守卫不访问数据库")

    deva = _stub_package("deva")
    deva.NB = _no_db
    _stub_package("deva.naja")
    _stub_package("deva.naja.bandit", BANDIT)

    _load_by_path("deva.naja.bandit.data_freshness", FRESHNESS_PY)
    return _load_by_path("_futu_syncer_under_test", SYNCER_PY)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_static() -> list:
    failures = []
    for path, pattern, desc in STATIC_RULES:
        if not path.exists():
            failures.append(f"{path.name} 不存在")
            continue
        if not re.search(pattern, _read(path), re.MULTILINE):
            failures.append(f"{path.name}：{desc}")

    for path, pattern, desc in STATIC_FORBIDDEN:
        if path.exists() and re.search(pattern, _read(path), re.MULTILINE):
            failures.append(f"{path.name}：{desc}")

    failures.extend(check_ui_branch_order())
    return failures


def check_ui_branch_order() -> list:
    """富途账户必须走「落盘表」分支渲染，且该分支要排在 PM 分支前面。

    两个分支都命中时，谁写在前面谁生效。若 PM 分支在前，富途账户会走
    USStockPortfolio 渲染路径，丢掉多市场/多币种处理；而两个来源都命中时
    不去重又会把同一个账户渲染两遍。
    """
    failures = []
    src = _read(UI_PY)
    futu_at = src.find("if account_name in futu_nb_accounts:")
    pm_at = src.find("elif pm and account_name in us_account_names:")
    if futu_at == -1:
        failures.append("ui.py：找不到富途账户渲染分支")
    if pm_at == -1:
        failures.append("ui.py：找不到美股账户渲染分支")
    if futu_at != -1 and pm_at != -1 and futu_at > pm_at:
        failures.append("ui.py：富途分支排在美股分支之后 —— 富途账户会走错渲染路径")

    dedup_at = src.find("all_account_names += [n for n in us_account_names if n not in futu_nb_accounts]")
    if dedup_at == -1:
        failures.append("ui.py：账户名未去重 —— 富途账户同时存在于落盘表与 PM 名册时会渲染两遍")
    return failures


# ---------------------------------------------------------------- ② 契约

def _row(acc_id, env="REAL", card="", auth=(), firm="FUTUSECURITIES"):
    return {
        "acc_id": acc_id,
        "card_num": card,
        "acc_type": "MARGIN",
        "trd_env": env,
        "market_auth": list(auth),
        "acc_role": "NORMAL",
        "security_firm": firm,
    }


MAIN_HK = _row(1001, card="1001200156527585", auth=["HK", "US", "HKCC", "HKFUND", "USFUND", "JP"],
               firm="FUTUSECURITIES")
SUB_HK = _row(1002, auth=["HK"], firm="FUTUSECURITIES")
SUB_US = _row(1003, auth=["US"], firm="FUTUSECURITIES")
MAIN_US = _row(2001, card="1007201500505626", auth=["HK", "US"], firm="FUTUINC")
SUB_US_M = _row(2002, auth=["US"], firm="FUTUINC")
SIM = _row(9001, env="SIMULATE", auth=["US"], firm="FUTUSECURITIES")


def check_select_main_accounts(mod) -> list:
    failures = []
    syncer = mod.FutuPortfolioSyncer()

    picked = syncer._select_main_accounts([MAIN_HK, SUB_HK, SUB_US, SIM])
    if [r["acc_id"] for r in picked] != [1001]:
        failures.append(
            f"主账户选择有误：应只取主综合账户 1001（子账户持仓恒为 0），实际 {[r['acc_id'] for r in picked]}"
        )

    # 主账户没覆盖的市场必须补进来，否则那个市场的持仓会整块漏掉。
    # 注意 MAIN_HK 的权限是 HK/US/HKCC/HKFUND/USFUND/JP，所以这里要用
    # 真正不在其内的市场（SG），否则用例本身是错的。
    picked = syncer._select_main_accounts(
        [MAIN_HK, _row(3001, auth=["SG"], firm="FUTUSECURITIES")]
    )
    if sorted(r["acc_id"] for r in picked) != [1001, 3001]:
        failures.append(
            f"主账户未覆盖的市场被漏掉：应取 [1001, 3001]，实际 {sorted(r['acc_id'] for r in picked)}"
        )

    # 反过来：已被主账户覆盖的市场不得重复取（否则同一笔持仓会算两遍）
    picked = syncer._select_main_accounts(
        [MAIN_HK, _row(3002, auth=["JP"], firm="FUTUSECURITIES")]
    )
    if [r["acc_id"] for r in picked] != [1001]:
        failures.append(
            f"已被主账户覆盖的市场被重复取：应只取 [1001]，实际 {[r['acc_id'] for r in picked]}"
        )

    # 一个主账户都没有时不能什么都不取（宁可多查也不能漏）
    picked = syncer._select_main_accounts([SUB_HK, SUB_US])
    if sorted(r["acc_id"] for r in picked) != [1002, 1003]:
        failures.append("没有任何带账号的主账户时，应退回全部实盘账户")

    # 模拟账户不分主/子
    sim_syncer = mod.FutuPortfolioSyncer(trd_env="SIMULATE")
    picked = sim_syncer._select_main_accounts([SIM, MAIN_HK])
    if [r["acc_id"] for r in picked] != [9001]:
        failures.append(f"模拟环境应只取 SIMULATE 账户，实际 {[r['acc_id'] for r in picked]}")

    return failures


def check_stale_rules(mod) -> list:
    failures = []
    syncer = mod.FutuPortfolioSyncer()

    existing = {"FutuHK", "MoomooUS", "FutuReal", "FutuSim", "Spark"}

    # ① 品牌探测失败 → 一律不清（分不清「账户没了」与「连不上」）
    stale = syncer._stale_account_names(existing, {"FutuHK"}, probed_ok={"FUTUSECURITIES"})
    if "MoomooUS" in stale:
        failures.append("FUTUINC 探测失败却清掉了 MoomooUS —— 一次网络抖动就会清空页面数据")
    if "FutuReal" not in stale:
        failures.append("FUTUSECURITIES 探测成功时，旧名 FutuReal 应被清掉（否则留下僵尸账户）")

    # ② 品牌探测成功且账户已不在同步结果里 → 清
    stale = syncer._stale_account_names(
        existing, {"FutuHK"}, probed_ok={"FUTUSECURITIES", "FUTUINC"}
    )
    if "MoomooUS" not in stale:
        failures.append("FUTUINC 探测成功且账户已消失，却仍保留 MoomooUS")
    if "FutuHK" in stale:
        failures.append("清掉了本次成功同步的 FutuHK —— 不能删自己刚写的数据")

    # ③ 与本品牌无关的账户（FutuSim / Spark）不得被牵连
    if "FutuSim" in stale or "Spark" in stale:
        failures.append("清理规则误伤其它账户（FutuSim / Spark）")

    # ④ 返回集合与本次成功账户无交集
    for probed in ({"FUTUSECURITIES"}, {"FUTUSECURITIES", "FUTUINC"}, set()):
        got = syncer._stale_account_names(existing, {"FutuHK", "MoomooUS"}, probed_ok=probed)
        if got & {"FutuHK", "MoomooUS"}:
            failures.append(f"清理集合与本次账户相交（probed_ok={probed}）：{sorted(got)}")

    # ⑤ 一个品牌都没有探测成功时不得清理任何东西
    stale = syncer._stale_account_names(existing, set(), probed_ok=set())
    if stale:
        failures.append(f"全部品牌探测失败却仍做清理：{sorted(stale)}")

    return failures


def check_currency(mod) -> list:
    failures = []
    d = mod.decide_currency

    if d("FUTUSECURITIES", [{"market": "HK", "currency": "HKD"}]) != "HKD":
        failures.append("港股持仓的账户币种应为 HKD")
    if d("FUTUINC", [{"market": "US", "currency": "USD"}]) != "USD":
        failures.append("美股持仓的账户币种应为 USD")
    if d("FUTUINC", []) != "USD":
        failures.append("无持仓时应退回品牌本地币种（FUTUINC → USD）")
    if d("FUTUSECURITIES", []) != "HKD":
        failures.append("无持仓时应退回品牌本地币种（FUTUSECURITIES → HKD）")
    mixed = [{"market": "US", "currency": "USD"}, {"market": "US", "currency": "USD"},
             {"market": "HK", "currency": "HKD"}]
    if d("FUTUINC", mixed) != "USD":
        failures.append("混合持仓应按多数决取币种")
    return failures


def check_sync_result(mod) -> list:
    failures = []

    def res(accts, probe_errors=()):
        return mod.SyncResult(
            accounts=[mod.AccountSyncResult(*a) for a in accts],
            probe_errors=list(probe_errors),
        )

    ok_one = res([("FutuHK", "FUTUSECURITIES", 1001, 2, True, "")])
    if not ok_one.ok or not bool(ok_one):
        failures.append("全部账户成功时 SyncResult 应为成功")

    # 最关键的语义：一个账户失败，整体就不能报成功（否则漏数据会被说成正常）
    partial = res([("FutuHK", "FUTUSECURITIES", 1001, 2, True, ""),
                   ("MoomooUS", "FUTUINC", 2001, 0, False, "连接超时")])
    if partial.ok or bool(partial):
        failures.append("部分账户失败时 SyncResult 仍报成功 —— 漏数据会被说成正常")
    if "MoomooUS" not in partial.failure_reason():
        failures.append("失败原因里没有点名失败的账户")

    empty = res([])
    if empty.ok or bool(empty):
        failures.append("一个账户都没同步时不得报成功")

    probe_bad = res([("FutuHK", "FUTUSECURITIES", 1001, 2, True, "")],
                    probe_errors=["FUTUINC 账户列表查询失败"])
    if probe_bad.ok:
        failures.append("品牌探测失败时不得报成功（那意味着可能漏了整个 moomoo）")

    # summary 必须点名每个账户
    text = partial.summary()
    if "FutuHK" not in text or "MoomooUS" not in text:
        failures.append("summary 未逐账户交代")
    return failures


def _us_position_fields() -> tuple:
    """从 portfolio_manager.py 解析 USStockPosition 的 (必填字段, 全部字段)。"""
    tree = ast.parse(_read(PM_PY))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "USStockPosition":
            required, all_fields = set(), set()
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    name = item.target.id
                    all_fields.add(name)
                    if item.value is None:
                        required.add(name)
            return required, all_fields
    raise RuntimeError("portfolio_manager.py 里找不到 USStockPosition")


def check_record_shape(mod) -> list:
    failures = []
    required, all_fields = _us_position_fields()

    target = {
        "name": "MoomooUS", "firm": "FUTUINC", "acc_id": 2001,
        "card_num": "1007201500505626", "market_auth": ["HK", "US"], "acc_type": "MARGIN",
    }
    data = {
        "currency": "USD",
        "funds": {"total_assets": 344161.02, "cash": -88641.18, "market_val": 432802.18,
                  "power": 176454.62, "currency": "USD"},
        "positions": [
            {"code": "nvda", "name": "英伟达", "qty": 1090.0, "average_cost": 228.86,
             "nominal_price": 186.5, "market_val": 203285, "unrealized_pl": -46420,
             "pl_ratio": -18.6, "prev_close": 0.0, "currency": "USD",
             "market": "US", "original_code": "US.NVDA"},
            {"code": "06666", "name": "恒大物业", "qty": 27500.0, "average_cost": 3.589,
             "nominal_price": 1.0, "market_val": 27500, "unrealized_pl": -71197,
             "pl_ratio": -72.1, "prev_close": 0.0, "currency": "HKD",
             "market": "HK", "original_code": "HK.06666"},
        ],
    }

    record = mod.FutuPortfolioSyncer()._build_account_record(target, data)
    if record.get("account_type") != "futu":
        failures.append("账户记录缺少 account_type=futu（页面靠它识别富途账户）")
    for key in ("security_firm", "acc_id", "card_num", "currency", "equity"):
        if key not in record:
            failures.append(f"账户记录缺少字段 {key}")
    if record.get("currency") != "USD":
        failures.append("账户记录未带上本币币种")

    ids = set(record.get("positions", {}))
    if not any(pid.startswith("US_MoomooUS_") for pid in ids):
        failures.append("美股持仓的 position_id 未带 US_ 前缀")
    if not any(pid.startswith("HK_MoomooUS_") for pid in ids):
        failures.append('港股持仓的 position_id 未带 HK_ 前缀（老实现写死 "US_"）')

    for pid, pos in record.get("positions", {}).items():
        keys = set(pos)
        missing = required - keys
        extra = keys - all_fields
        if missing:
            failures.append(f"{pid} 缺字段 {sorted(missing)} → USStockPosition(**) 会 TypeError")
        if extra:
            failures.append(f"{pid} 多出字段 {sorted(extra)} → USStockPosition(**) 会 TypeError")
        if pos["market"] not in pid:
            failures.append(f"{pid} 的市场前缀与持仓市场不一致")

    # equity 必须来自资金接口，而不是把持仓市值凑上来
    if abs(record["equity"] - 344161.02) > 1e-6:
        failures.append("equity 未取资金接口的 total_assets")
    return failures


class _FakePosDF:
    """最小 DataFrame 替身：只要 len() 与 iloc[i].get() 够 ``_parse_positions`` 用。"""

    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    @property
    def iloc(self):
        return self._rows


def check_parse_positions(mod) -> list:
    failures = []
    syncer = mod.FutuPortfolioSyncer()

    df = _FakePosDF([
        {"code": "US.SKUU", "stock_name": "2倍做多海力士ETF", "qty": 247.0,
         "average_cost": 18.644, "nominal_price": 19.62, "market_val": 4846.14,
         "unrealized_pl": 241.17, "pl_ratio_avg_cost": 5.23, "currency": "USD"},
        {"code": "HK.06666", "stock_name": "恒大物业", "qty": 27500.0,
         "average_cost": 3.589, "nominal_price": 1.0, "currency": "HKD"},
    ])
    parsed = syncer._parse_positions(df)
    if len(parsed) != 2:
        failures.append(f"持仓解析条数有误：期望 2，实际 {len(parsed)}")
        return failures

    us, hk = parsed[0], parsed[1]
    if (us["code"], us["market"], us["currency"]) != ("skuu", "US", "USD"):
        failures.append(f"美股持仓解析有误：{us['code']} {us['market']} {us['currency']}")
    if (hk["code"], hk["market"], hk["currency"]) != ("06666", "HK", "HKD"):
        failures.append(f"港股持仓解析有误：{hk['code']} {hk['market']} {hk['currency']}")
    if abs(us["average_cost"] - 18.644) > 1e-9 or abs(us["pl_ratio"] - 5.23) > 1e-9:
        failures.append("成本价/盈亏比例未取 average_cost / pl_ratio_avg_cost")

    # ★ 摊薄成本禁令：只有 cost_price / pl_ratio 时不得采用它们的值
    thin = _FakePosDF([{"code": "US.NVDA", "qty": 10.0, "cost_price": 100.0,
                        "pl_ratio": 42.0, "pl_val": 999.0}])
    got = syncer._parse_positions(thin)[0]
    if got["average_cost"] != 0.0:
        failures.append("成本价回落到 cost_price（摊薄口径）—— 会把亏损显示成盈利")
    if got["pl_ratio"] != 0.0:
        failures.append("盈亏比例回落到 pl_ratio（摊薄口径）—— 与 APP 显示不一致")

    # 空/异常输入不得炸
    if syncer._parse_positions(None) != [] or syncer._parse_positions(_FakePosDF([])) != []:
        failures.append("空持仓应返回空列表")
    return failures


def check() -> int:
    print(f"被测模块：{SYNCER_PY.relative_to(REPO)}")
    try:
        mod = _load_syncer()
    except Exception as e:  # noqa: BLE001
        print(f"❌ 无法加载被测模块：{e}")
        return 1

    groups = [
        ("静态（品牌覆盖/逐账户/真实市场前缀）", check_static()),
        ("契约 · 主账户选择", check_select_main_accounts(mod)),
        ("契约 · 僵尸账户清理", check_stale_rules(mod)),
        ("契约 · 币种判定", check_currency(mod)),
        ("契约 · 整体成败语义", check_sync_result(mod)),
        ("契约 · 持仓解析（摊薄成本禁令）", check_parse_positions(mod)),
        ("覆盖 · 记录能喂给 USStockPosition", check_record_shape(mod)),
    ]

    failed = False
    for title, fails in groups:
        if fails:
            failed = True
            print(f"\n❌ {title}：")
            for f in fails:
                print(f"    - {f}")
        else:
            print(f"✅ {title}：通过")

    if failed:
        return 1
    print("\n✅ 通过：品牌全覆盖、每账户独立成块、清理规则不误伤、摊薄成本未回流")
    return 0


# ---------------------------------------------------------------- 自证

def self_test() -> int:
    """隔离自证：不碰真实文件，验证规则本身有区分度。"""
    failures = []
    mod = _load_syncer()

    if len(STATIC_RULES) < 8:
        failures.append(f"静态规则过少（{len(STATIC_RULES)} 条），覆盖不全")
    for _, _, desc in STATIC_RULES + STATIC_FORBIDDEN:
        if not desc.strip():
            failures.append("存在没有说明文字的静态规则")

    # 每条「必须匹配」规则都得真的匹配到目标文件
    for path, pattern, desc in STATIC_RULES:
        if not re.search(pattern, _read(path), re.MULTILINE):
            failures.append(f"规则「{desc}」匹配不到 {path.name} —— 规则可能是死的")

    # 每条「禁止」规则当前必须不匹配（否则等于进门就是红的）
    for path, pattern, desc in STATIC_FORBIDDEN:
        if re.search(pattern, _read(path), re.MULTILINE):
            failures.append(f"禁止规则「{desc}」当前已命中 —— 源码里确实存在该问题")

    # 区分度：改坏一条规则的目标，它必须不再匹配
    seed = SYNCER_PY.read_text(encoding="utf-8").replace('"FUTUINC": "MoomooUS",', "")
    if re.search(STATIC_RULES[1][1], seed, re.MULTILINE):
        failures.append("品牌覆盖规则对「删掉 moomoo」不敏感 —— 没有区分度")

    # 契约检查在未注入时必须全绿（否则守卫自身有问题）
    for name, fails in [
        ("主账户选择", check_select_main_accounts(mod)),
        ("僵尸账户清理", check_stale_rules(mod)),
        ("币种判定", check_currency(mod)),
        ("整体成败语义", check_sync_result(mod)),
        ("持仓解析", check_parse_positions(mod)),
        ("记录形状", check_record_shape(mod)),
    ]:
        if fails:
            failures.append(f"契约「{name}」在未注入时却报错（守卫自身有问题）：")
            failures.extend(fails)

    if failures:
        print("❌ 自证失败：")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("✅ 自证通过：规则均有区分度，且未注入时不误报")
    return 0


def exercise_injections() -> int:
    """行为自证：往真实源码注入已知 bug，check() 必须报错；逐例立即还原。"""
    failures = []
    for case in INJECTIONS:
        path, old, new = case["file"], case["old"], case["new"]
        if not path.exists():
            failures.append(f"[{case['name']}] 目标文件不存在")
            continue

        original = path.read_text(encoding="utf-8")
        if old not in original:
            failures.append(f"[{case['name']}] 注入锚点找不到（源码已变，请更新守卫）")
            continue

        try:
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            code = check()
            if code == 0:
                failures.append(f"[{case['name']}] 注入后守卫仍返回 0 —— 没有区分度")
            else:
                print(f"  ✅ 注入「{case['name']}」→ 守卫如期报错")
        finally:
            path.write_text(original, encoding="utf-8")
            if path.read_text(encoding="utf-8") != original:
                failures.append(f"[{case['name']}] 源码还原失败，请手动检查 {path}")

    if check() != 0:
        failures.append("注入用例跑完后守卫仍不通过 —— 还原不干净")

    if failures:
        print("\n❌ 注入自证失败：")
        for f in failures:
            print(f"    - {f}")
        return 1
    print(f"\n✅ 注入自证通过：{len(INJECTIONS)} 例注入全部被捕获，且已还原")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="富途多账户同步守卫")
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
