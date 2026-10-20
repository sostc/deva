"""守卫：结构性增长页的 PE 必须是**真实抓到的**，且重定价的三个度量不许乱给数。

背景（2026-10-20 实测，不是推测）：

``FundamentalDataFetcher._enrich_us_fundamental`` 里曾经有一张硬编码表：

    us_fundamentals = {
        'NVDA': {'pe': 65.0, 'market_cap': 2800000000000},
        'MU': {'pe': 35.0}, ...
    }

实测真值：NVDA **PE 33.22 / 市值 5.26T**、MU **PE 20.37** —— 与硬编码的
65 / 2.8T **差了近一倍**。也就是说「结构性增长」页上的 PE 列、市值列显示的
数全是编的。拿它当锚点做重定价，算出来的「还有多少空间」全是幻觉 ——
它不报错、看着还很专业，是典型的「假新鲜比异常更毒」。

同一轮还挖出第二个静默失效：``_detect_market`` 的**美股白名单只有 14 个代码**，
ALAB / AVGO / CRDO / ANET / PLTR / MRVL 这些后加的标的一律被判 ``UNKNOWN``
→ 抓取直接返回 ``None`` → 页面显示「—」且不写原因。监控池里一半的股票
从来没取到过行情，而没人发现。

本守卫盯五件事：
1. 硬编码 PE 常量**不许复活**
2. 亏损股的 PE（新浪返回 ``--``）必须解析成 ``None``，不是 0
3. 市场判定不能只靠白名单（新标的要认得出来）
4. 分类数据不足必须返回 ``UNKNOWN``，不许默认 ``BASE``
5. 不对称比在现价跌破周期带时返回 ``None``，不是 ``inf``
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NAJA = REPO / "deva" / "naja"

FETCHER_PY = NAJA / "bandit" / "fundamental_data_fetcher.py"
CLASSIFIER_PY = NAJA / "structural_growth" / "pe_classifier.py"
REPRICING_PY = NAJA / "structural_growth" / "repricing.py"
FINFETCH_PY = NAJA / "structural_growth" / "financial_data_fetcher.py"
BANDS_PY = NAJA / "structural_growth" / "pe_bands.py"
SG_DIR = NAJA / "structural_growth"


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _load_sg(name: str, tag: str = ""):
    """加载 ``structural_growth`` 包内的模块，**保留相对导入**。

    ❗``pe_bands.py`` 里有 ``from .repricing import PeBand``，用 ``_load``
    单点加载会因为「没有父包」直接失败。这里手工造一个包命名空间。
    """
    import types

    pkg_name = f"_vf_sg_pkg{tag}"
    pkg = sys.modules.get(pkg_name)
    if pkg is None:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(SG_DIR)]
        sys.modules[pkg_name] = pkg
    full = f"{pkg_name}.{name}"
    spec = importlib.util.spec_from_file_location(full, SG_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


def _load(path: Path, name: str):
    """从文件路径**每次全新**加载模块。

    ❗不能用 importlib.import_module：``sys.modules`` 里留的是旧对象，
    注入后跑出来的是"假通过"（本项目踩过：注入后 import 被测类 → 全绿但测的是旧代码）。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    # ❗必须先登记再 exec：``dataclasses`` 在解析 ``KW_ONLY`` 类型时会去
    # ``sys.modules[cls.__module__].__dict__`` 取命名空间，没登记就会抛
    # ``AttributeError: 'NoneType' object has no attribute '__dict__'``
    # （本次实测踩到）。每次都是新建的模块对象，所以不会读到注入前的旧代码。
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- 1. 无硬编码


def check_no_hardcoded_pe() -> list:
    """不许再有写死的 PE / 市值常量表。"""
    tree = _parse(FETCHER_PY)
    if tree is None:
        return [f"{_rel(FETCHER_PY)} 解析失败"]

    bad = []
    for node in ast.walk(tree):
        # (a) 曾经那张表的名字不许再出现
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "us_fundamentals":
                    bad.append(f"{_rel(FETCHER_PY)}:{node.lineno} 又出现了 us_fundamentals 硬编码表")
        # (b) {'pe': 65.0} 这种「字面量 → 数字」的字典
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "pe" \
                        and isinstance(v, ast.Constant) and isinstance(v.value, (int, float)):
                    bad.append(
                        f"{_rel(FETCHER_PY)}:{node.lineno} 硬编码 PE 常量 {v.value} —— "
                        "PE 必须真实抓取，拿不到就报缺失"
                    )
    return bad


# ------------------------------------------------------- 2. 亏损股 PE = None


def check_loss_making_pe_is_none() -> list:
    """新浪对亏损股返回 ``--``（实测 INTC：EPS=-0.62、PE="--"）。

    ❗解析成 0 的话，页面上「PE 0」会被读成"白送"，是全场最危险的一个数。
    """
    mod = _load(FETCHER_PY, "_vf_fetcher")
    if mod is None or not hasattr(mod, "_parse_ratio_field"):
        return ["_parse_ratio_field 不存在（解析函数被改名/删除）"]

    fn = mod._parse_ratio_field
    cases = [("--", None), ("-", None), ("", None), ("N/A", None)]
    bad = []
    for raw, want in cases:
        got = fn(raw)
        if got is not None:
            bad.append(f"_parse_ratio_field({raw!r}) 返回 {got}，应为 None（缺失不能当 0）")

    # 反方向：正常的数字必须照常解析出来，不许"一律 None"
    got = fn("33.21")
    if got is None or abs(got - 33.21) > 1e-6:
        bad.append(f"_parse_ratio_field('33.21') 返回 {got}，应解析出 33.21")
    return bad


# --------------------------------------------------- 3. 市场判定不只靠白名单


def check_market_detection_not_whitelist_only() -> list:
    """后加的标的代码必须认得出来。

    白名单里没有 ALAB / AVGO / CRDO / ANET / PLTR / MRVL，若只靠白名单，
    这些票会被判 UNKNOWN → 抓取静默返回 None → 页面显示「—」且不给原因。

    ❗必须用 ``_load`` 从磁盘**重新**加载，不能用 ``import``：
    ``sys.modules`` 里留的是本次进程早先导入的旧对象，注入后的新代码根本
    没被读进来 —— 守卫会全绿但什么都没在守（本项目踩过，这次又踩了一次）。
    """
    mod = _load(FETCHER_PY, "_vf_fetcher_market")
    if mod is None or not hasattr(mod, "FundamentalDataFetcher"):
        return ["FundamentalDataFetcher 加载失败"]

    cls = mod.FundamentalDataFetcher
    bad = []
    # 用未绑定调用，避免 __init__ 里的 MCP 探测等副作用
    for code, want in [("ALAB", "US"), ("AVGO", "US"), ("CRDO", "US"),
                       ("ANET", "US"), ("MRVL", "US"), ("PLTR", "US")]:
        try:
            got = cls._detect_market(None, code)
        except Exception as e:  # noqa: BLE001
            bad.append(f"_detect_market({code}) 抛异常: {type(e).__name__}: {e}")
            continue
        if got.value != want:
            bad.append(f"_detect_market({code}) = {got.value}，应为 {want}")

    # 反方向：A 股不能被误判成美股（形态判定只对纯字母生效）
    for code, want in [("600519", "A"), ("000001", "A")]:
        got = cls._detect_market(None, code)
        if got.value != want:
            bad.append(f"_detect_market({code}) = {got.value}，应为 {want}（A 股被误判）")
    return bad


# ------------------------------------------------- 4. 数据不足必须 UNKNOWN


def check_classifier_unknown_on_sparse_data() -> list:
    """❗数据不足必须返回 ``UNKNOWN``。

    默认成 ``BASE`` 的后果：「没数据」被读成「稳态」，然后被拿去重定价 ——
    这正是本项目反复踩的「合法的空比异常更危险」。
    """
    mod = _load(CLASSIFIER_PY, "_vf_classifier")
    if mod is None:
        return ["pe_classifier.py 加载失败"]

    bad = []
    for n in (0, 1, 2, 3):
        inp = mod.ClassificationInput(code="TEST", net_profit_yoy=[5.0] * n)
        res = mod.classify(inp)
        if res.regime.value != "unknown":
            bad.append(
                f"{n} 期数据时分类为 {res.regime.value}，应为 unknown"
                "（数据不足不许默认 base）"
            )

    # 反方向：数据够且特征明确时，必须真的定得出类（不许"一律 unknown"）
    inp = mod.ClassificationInput(
        code="TEST",
        net_profit_yoy=[12.0, 25.0, 40.0, 62.0],
        gross_margin=[40.0, 43.0, 46.0, 49.0],
        cashflow_to_profit=[0.9, 0.95, 1.0, 1.05],
    )
    res = mod.classify(inp)
    if res.regime.value != "structural":
        bad.append(f"明确的成长特征被判为 {res.regime.value}，应为 structural")
    if not res.evidence:
        bad.append("分类结果没有带证据 —— 结论必须可审计")
    return bad


# ---------------------------------- 4b. 周期反转 ≠ 结构性改善


def check_margin_swing_is_cyclical() -> list:
    """毛利率从负数爬回来是**周期反转**，不是结构性成长。

    MU 实测：毛利率 −9.11% → 80.72%（+89.8pp 单调上升）、净利同比
    −167% → +895%。只看"单调扩张"它是全场最像成长股的一个，但它是典型
    周期股 —— 把这个误判成成长，等于把周期顶部的低 PE 读成"便宜的成长股"。
    """
    mod = _load(CLASSIFIER_PY, "_vf_classifier_swing")
    if mod is None:
        return ["pe_classifier.py 加载失败"]

    inp = mod.ClassificationInput(
        code="MU",
        net_profit_yoy=[-167.1, 113.3, 997.6, 895.1],
        gross_margin=[-9.11, 22.35, 39.79, 80.72],
        cashflow_to_profit=[1.06],
    )
    res = mod.classify(inp)
    bad = []
    if res.regime.value != "cyclical":
        bad.append(f"MU 型周期反转被判为 {res.regime.value}，应为 cyclical")
    if not any("剧烈摆动" in e for e in res.evidence):
        bad.append("没把「毛利率剧烈摆动」记为周期证据 —— 周期反转被当成了结构改善")

    # ❗第二条用例直接钉住「这条成长证据不该被生成」本身。
    # 光断言 regime 是不够的：毛利率摆动 >20pp 时 C3 也会命中，两边都够 2 条，
    # 去掉上限可能改变不了最终分类 —— 但那条虚假的成长证据已经混进 counter_evidence，
    # 会在 UI 上给周期股背书。所以必须按证据文本断言。
    inp2 = mod.ClassificationInput(
        code="SWING",
        net_profit_yoy=[5.0, 40.0, 90.0, 150.0],
        gross_margin=[30.0, 40.0, 48.0, 55.0],   # 单调 +25pp，超过 20pp 上限
        cashflow_to_profit=[1.0],
    )
    res2 = mod.classify(inp2)
    all_ev = list(res2.evidence) + list(res2.counter_evidence)
    if any("毛利率单调扩张" in e for e in all_ev):
        bad.append(
            "毛利率扩张 +25pp（超过 20pp 上限）仍被记为结构性成长证据 —— "
            "周期反转被当成了结构改善"
        )
    return bad


# ------------------------------------------- 5. 不对称比不许返回 inf


def check_asymmetry_none_below_cyclical() -> list:
    """现价跌破周期带时，下行空间 ≤ 0 → 必须返回 ``None``。

    返回 ``inf`` 会让"最危险的票"在排序里排最前面 —— 那正是价值陷阱的样子。
    """
    mod = _load(REPRICING_PY, "_vf_repricing")
    if mod is None:
        return ["repricing.py 加载失败"]

    PeBand = mod.PeBand
    cyclical = PeBand("周期", 12.0, 18.0)
    structural = PeBand("结构性", 35.0, 48.0)

    bad = []
    # 现价 10x，低于周期带中值 15x → 分母为负
    ratio, up, down, note = mod.asymmetry(10.0, cyclical, structural)
    if ratio is not None:
        bad.append(f"跌破周期带时 asymmetry 返回 {ratio}，应为 None（不许 inf/大数）")
    if not note:
        bad.append("跌破周期带时没写原因 —— 拿不到必须说清楚，不许静默")

    # 正常情形必须算得出正数
    ratio, up, down, note = mod.asymmetry(32.4, cyclical, structural)
    if ratio is None or ratio <= 0:
        bad.append(f"正常情形 asymmetry 返回 {ratio}，应为正数")

    # PE 缺失 → None
    ratio, _, _, _ = mod.asymmetry(None, cyclical, structural)
    if ratio is not None:
        bad.append("PE 缺失时 asymmetry 应返回 None")

    # priced_in 同样不许乱给
    if mod.priced_in_ratio(None, cyclical, structural) is not None:
        bad.append("PE 缺失时 priced_in_ratio 应返回 None")
    return bad


# ---------------------------------------------------- 6. 九宫格不许有空格


def check_entry_grid_complete() -> list:
    """阶段 × 定价进度 的九宫格**每一格都要有文案**。

    空白格在页面上就是黑屏 —— "合法的空"比报错更难发现。
    """
    mod = _load(REPRICING_PY, "_vf_repricing")
    if mod is None:
        return ["repricing.py 加载失败"]

    grid = getattr(mod, "_ENTRY_GRID", None)
    if not isinstance(grid, dict):
        return ["_ENTRY_GRID 不存在"]

    bad = []
    for stage in ("early", "mid", "late"):
        for ratio in ("low", "mid", "high"):
            text = grid.get((stage, ratio))
            if not text or not text.strip():
                bad.append(f"九宫格 ({stage}, {ratio}) 没有判读文案")
    if len(grid) != 9:
        bad.append(f"九宫格有 {len(grid)} 项，应为 9")
    return bad


# ------------------------------------------------- 7. 周期股高定价 = 陷阱


def check_cyclical_overpriced_is_trap() -> list:
    """同样的 priced_in 0.8，成长股是"快到顶"，周期股是"已经泡沫"。

    ❗分类必须参与判读，否则「预期差 +5%」到底是机会还是陷阱，系统答不了。
    """
    mod = _load(REPRICING_PY, "_vf_repricing")
    if mod is None:
        return ["repricing.py 加载失败"]

    PeBand = mod.PeBand
    cyclical = PeBand("周期", 12.0, 18.0)
    structural = PeBand("结构性", 35.0, 48.0)

    cyc = mod.evaluate_repricing("X", 40.0, cyclical, structural,
                                 phase="S2", regime="cyclical")
    grow = mod.evaluate_repricing("X", 40.0, cyclical, structural,
                                  phase="S2", regime="structural")
    if cyc.verdict == grow.verdict:
        return ["周期股与成长股在高定价区给出同样的判读 —— 分类没参与判读"]

    if "陷阱" not in cyc.verdict:
        return [f"周期股高定价应判为陷阱，实际：{cyc.verdict}"]
    return []


# -------------------------------- 9. C2 门槛：单期负增长不算周期证据


def check_single_negative_is_not_cyclical() -> list:
    """4 期里只有 1 期负增长（25%）**不算**周期证据。

    校准前 C2 是「出现过负增长就命中」，33 只票里命中 **29 只（88%）** ——
    那是必然事件，不是证据（这批年度数据覆盖 2022-23 半导体下行，谁都有一年负增长）。
    一个 88% 命中的判据，等价于没判。
    """
    mod = _load(CLASSIFIER_PY, "_vf_cls_c2")
    if mod is None:
        return ["pe_classifier.py 加载失败"]

    inp = mod.ClassificationInput(
        code="ONENEG",
        net_profit_yoy=[-5.0, 30.0, 40.0, 50.0],   # 只有 1/4 = 25% 负增长
        gross_margin=[40.0, 40.5, 41.0, 41.5],      # 极差 1.5pp，不命中 C3
    )
    res = mod.classify(inp)
    bad = []
    all_ev = list(res.evidence) + list(res.counter_evidence)
    if any("负增长期数占比" in e for e in all_ev):
        bad.append("只有 1 期负增长（25%）仍被记为周期证据 —— C2 门槛被退回「出现即命中」")
    if res.regime.value != "structural":
        bad.append(f"明显的成长特征被判为 {res.regime.value}，应为 structural")

    # 反方向：占比真的高（≥1/3）时必须命中，不许"一律不命中"
    inp2 = mod.ClassificationInput(
        code="HALFNEG",
        net_profit_yoy=[-40.0, 60.0, -20.0, 80.0],   # 2/4 = 50%
    )
    res2 = mod.classify(inp2)
    all_ev2 = list(res2.evidence) + list(res2.counter_evidence)
    if not any("负增长期数占比" in e for e in all_ev2):
        bad.append("负增长占比 50% 却没记为周期证据 —— C2 门槛被抬过头了")
    return bad


# ------------------------- 10. 只有弱证据不许定类（EQIX 型）


def check_weak_evidence_alone_cannot_classify() -> list:
    """毛利率温和扩张 + 现金流达标，两条**弱**证据不足以定「结构性成长」。

    校准前是「命中 2 条就定类」，于是 LRCX / KLAC / AMAT（半导体设备周期股）
    和 EQIX（REIT）全被判成结构性成长 —— 靠的就是 S2 + S3。可这两条在
    **周期上行期一样成立**，它们根本不区分周期与成长。
    """
    mod = _load(CLASSIFIER_PY, "_vf_cls_weak")
    if mod is None:
        return ["pe_classifier.py 加载失败"]

    inp = mod.ClassificationInput(
        code="WEAKONLY",
        net_profit_yoy=[5.0, -3.0, 8.0, 10.0],       # 最近 3 期 -3,8,10 → S1 不命中
        gross_margin=[40.0, 41.0, 42.0, 43.0],       # 单调 +3pp → S2（弱）
        cashflow_to_profit=[1.5],                     # S3（弱）
    )
    res = mod.classify(inp)
    bad = []
    if res.regime.value != "base":
        bad.append(
            f"只有两条弱证据却被判为 {res.regime.value}，应为 base —— "
            "弱证据不许单独定类"
        )
    if "弱证据" not in res.note:
        bad.append(f"没说明「只有弱证据」，note={res.note!r}")
    return bad


# -------------------- 11. 亏损公司的「负增长」不是周期证据（SNOW vs INTC）


def check_unprofitable_negative_is_weak() -> list:
    """最近一期仍亏损时，C2（负增长）必须**降级为弱证据**。

    对亏损公司，"净利同比为负"衡量的是**亏损扩大速度**，不是周期波动。
    SNOW 4 期同比全负（−381/−5/−54/−4），按占比 100% 会命中强 C2 被判成周期股，
    但它是"还没盈利的成长股"，不是周期股。

    ❗这一项必须有**反方向**用例：INTC 同样亏损（−267M），但波动巨大
    （对数 sd 4.40），靠 C1 仍然要判周期 —— 降级不能一刀切把亏损公司全变成稳态。
    """
    mod = _load(CLASSIFIER_PY, "_vf_cls_unprof")
    if mod is None:
        return ["pe_classifier.py 加载失败"]

    bad = []
    # SNOW 型：全负增长 + 仍亏损 → 不该判周期
    snow = mod.ClassificationInput(
        code="SNOW", net_profit_yoy=[-380.5, -4.9, -53.8, -3.6],
        latest_net_profit=-1331.6e6,
    )
    res = mod.classify(snow)
    if res.regime.value == "cyclical":
        bad.append("持续亏损的成长股被判为 cyclical —— 亏损公司的负增长不是周期证据")
    if not any("仍亏损" in e for e in (res.evidence + res.counter_evidence)):
        bad.append("C2 降级了但证据文本没写明「仍亏损」，读的人无法判断这条为什么是弱的")

    # INTC 型：同样亏损，但波动巨大 → 必须判周期（反方向）
    intc = mod.ClassificationInput(
        code="INTC", net_profit_yoy=[-59.7, -78.9, -1210.5, 98.6],
        latest_net_profit=-267e6,
    )
    res2 = mod.classify(intc)
    if res2.regime.value != "cyclical":
        bad.append(
            f"INTC 型（亏损但波动巨大）被判为 {res2.regime.value}，应为 cyclical —— "
            "亏损降级不能一刀切"
        )
    return bad


# ------------------- 12. confidence 必须反映净优势，不能只看自己一侧


def check_confidence_is_net_margin() -> list:
    """confidence 必须同时反映「赢了多少」和「证据绝对量」。

    校准前用「自己一侧得分 / 一侧满分」，于是：
    - CRM（成长 4 分，但周期侧也有 2 分强证据）显示 **1.00** —— 明明争议很大
    - ENPH（周期侧只有 2 分，一条判据）也显示 **1.00** —— 单条证据就满分
    改成 净优势/满分 后：CRM 0.50、ENPH 0.40、只有 WDC（5/5 且反侧 0）是 1.00。
    """
    mod = _load(CLASSIFIER_PY, "_vf_cls_conf")
    if mod is None:
        return ["pe_classifier.py 加载失败"]

    bad = []
    # (a) 反侧有强证据时不该满分：成长 4 分 vs 周期 2 分
    crm = mod.ClassificationInput(
        code="CRM",
        net_profit_yoy=[-86.0, 1888.0, 50.0, 20.0],   # C1 命中（波动大）→ 周期侧 2 分
        gross_margin=[70.0, 72.0, 74.0, 74.3],        # S2 命中
        cashflow_to_profit=[2.0],                      # S3 命中
    )
    res = mod.classify(crm)
    if res.str_score >= 2 and res.cyc_score >= 2 and res.confidence >= 0.9:
        bad.append(
            f"反侧也有 {res.cyc_score} 分强证据，confidence 却是 {res.confidence} —— "
            "confidence 没反映净优势"
        )

    # (b) 只命中一条强证据时不该满分
    weak = mod.ClassificationInput(
        code="ONEHIT", net_profit_yoy=[12.0, 30.0, 55.0, 90.0],
    )
    res2 = mod.classify(weak)
    if res2.confidence >= 0.9:
        bad.append(
            f"只命中一条强证据（{res2.str_score} 分）却给出 confidence {res2.confidence} "
            "—— 单条证据不该满分"
        )
    if res2.confidence <= 0:
        bad.append("明确定类却给出 confidence 0 —— confidence 完全失效")
    return bad


# ------------------------- 13. 上游标记缺失的样本必须被剔除


def check_missing_flagged_samples_excluded() -> list:
    """上游把「取不到」填成 0.0，但同时在 ``missing`` 里写了名字。

    只判 ``is not None`` 会把假 0 当真值收进来：
    - 毛利率假 0（AMZN/GOOGL/KLAC/EQIX 实测全是 0，真实值 50%/58%/60%/49%）
      → 极差 0、升降 0，被读成「毛利率纹丝不动」，C3/S2 两条判据直接失效
    - 净利同比假 0 → 拉低标准差、破坏「持续为正」判据

    ❗剔除还必须**可见**：悄悄丢样本会让"4 期"看起来是完整的 4 期。
    """
    mod = _load(CLASSIFIER_PY, "_vf_cls_excl")
    if mod is None:
        return ["pe_classifier.py 加载失败"]

    class _Fin:
        def __init__(self, yoy, gm, missing, np_v=100.0, cf=150.0):
            self.net_profit_yoy = yoy
            self.gross_margin = gm
            self.missing = missing
            self.net_profit = np_v
            self.cashflow = cf
            self.report_date = "2025"

    fins = [
        _Fin(10.0, 0.0, ["gross_margin"]),        # 毛利率缺失（填了 0）
        _Fin(20.0, 45.0, []),
        _Fin(30.0, 0.0, ["gross_margin"]),        # 毛利率缺失（填了 0）
        _Fin(40.0, 47.0, []),
    ]
    inp = mod.build_input_from_financials("TEST", fins)
    bad = []
    if len(inp.gross_margin) != 2:
        bad.append(
            f"4 期里 2 期毛利率被标缺失，却收进了 {len(inp.gross_margin)} 期 "
            "—— 缺失填充的 0.0 被当成了真实毛利率"
        )
    if inp.excluded.get("gross_margin") != 2:
        bad.append(
            f"剔除了样本但 excluded 记的是 {inp.excluded}，应为 {{'gross_margin': 2}} "
            "—— 剔除必须可见"
        )
    if len(inp.net_profit_yoy) != 4:
        bad.append("正常样本被误剔除")
    return bad


# ---------------------------- 14. 净利缺失不许伪造 −100% 同比


def check_missing_net_profit_not_forged() -> list:
    """``net_income.get(year, 0.0)`` 会把缺失填成 0，进而算出 **−100%** 假同比。

    实测 AVGO：FY2025 取不到 NetIncomeLoss（该标签在 AVGO 里只有 2024 和 2018
    两年），填 0 后同比 = (0 − 前值)/|前值| = **−100%**，凭空造出一次「由盈转亏」
    —— 而 AVGO 当年真实净利数百亿美元。这个假 −100% 会直接命中强 C2 周期判据。
    """
    tree = _parse(FINFETCH_PY)
    if tree is None:
        return [f"{_rel(FINFETCH_PY)} 解析失败"]

    bad = []
    for node in ast.walk(tree):
        # net_income.get(year, 0.0) —— 带 0.0 默认值 = 缺失被伪装成 0
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in ("net_income", "prev_ni"):
            if len(node.args) == 2 and isinstance(node.args[1], ast.Constant) \
                    and node.args[1].value == 0.0:
                bad.append(
                    f"{_rel(FINFETCH_PY)}:{node.lineno} "
                    f"{node.func.value.id}.get(..., 0.0) —— 缺失被填成 0，"
                    "会伪造出 −100% 的净利同比"
                )
    return bad


# ---------------------------- 15. 波动度量必须抗极端值（对数尺度）


def check_volatility_metric_is_scale_robust() -> list:
    """净利同比是比率，直接用标准差会被一期极端值支配。

    实测 WDC 有一期 +3242%（低基数反弹），原始 sd = 1393.6 —— 一个数就定死了
    整批样本的尺度，阈值怎么切都区分不开（25pp→76% 命中，80pp→还有 55%）。

    ❗判据钉「排序关系」而不是阈值本身：原始 sd 口径下 ISRG（稳定成长，94.5）
    比 LRCX（半导体设备周期，23.7）**还高 4 倍** —— 结论完全反了。
    """
    mod = _load(CLASSIFIER_PY, "_vf_cls_logsd")
    if mod is None:
        return ["pe_classifier.py 加载失败"]
    fn = getattr(mod, "_log_sd", None)
    if fn is None:
        return ["_log_sd 不存在（波动度量被改名/删除）"]

    wdc = [-119.0, 307.0, -53.0, 3242.0]     # 典型周期，含极端值
    isrg = [247.0, 36.0, 29.0, 23.0]         # 稳定成长，含一个高基数
    lrcx = [-2.0, -15.0, 40.0, 36.0]         # 半导体设备周期，幅度温和

    bad = []
    a, b, c = fn(wdc), fn(isrg), fn(lrcx)
    if a is None or b is None:
        return ["_log_sd 返回 None"]
    if not a > b * 2:
        bad.append(
            f"对数尺度下 WDC（{a:.2f}）不到 ISRG（{b:.2f}）的 2 倍 —— "
            "极端值仍在支配，度量失效"
        )
    # 原始 sd 口径下 ISRG(94.5) > LRCX(23.7)，结论是反的；对数口径必须纠正过来
    if not b < c:
        bad.append(
            f"对数尺度下 ISRG（{b:.2f}）仍不低于 LRCX（{c:.2f}） —— "
            "稳定成长股不该比设备周期股看起来更波动"
        )
    return bad


def _heavy_tail_peers(mod) -> list:
    """构造一个重尾 PE 池（复刻实测池子的形状）。

    实测池子：多数票 15–80x，但 TSLA 307x / PLTR 202x / AMD 175x 拖出长尾。
    正是这个长尾让第一版尺子失效 —— 分位尺子必须扛得住它。
    """
    base = [15.4, 18.9, 20.2, 22.9, 23.9, 24.7, 25.98, 27.9, 29.7, 30.9,
            31.7, 33.0, 34.9, 38.1, 38.6, 46.9, 51.2, 51.8, 54.1, 54.9,
            61.7, 61.8, 65.7, 66.0, 67.3, 80.4]
    tail = [174.7, 180.2, 202.2, 306.7]
    return [mod.PeerPe(code=f"C{i}", pe=v) for i, v in enumerate(base + tail)]


def check_bands_measured_when_enough_samples() -> list:
    """样本够时必须用实测分位，不许退回经验常量。

    ❗「有样本却用了常量」是最难发现的一种失效：它不报错，读数看起来也合理，
    只是和真实分布对不上。第一版的 12–18 / 35–48 就是这么来的。
    """
    mod = _load_sg("pe_bands", "_bands1")
    if mod is None:
        return ["pe_bands.py 加载失败"]
    peers = _heavy_tail_peers(mod)
    bs = mod.build_bands(peers)
    bad = []
    for key in ("cyclical", "base", "structural"):
        band = getattr(bs, key)
        if band.source != "measured":
            bad.append(f"{key} 带来源={band.source}，样本 {len(peers)} 只足够，应为 measured")
    if bs.samples != len(peers):
        bad.append(f"samples={bs.samples}，应为 {len(peers)}")
    return bad


def check_bands_never_invert() -> list:
    """三条带必须单调递增，结构性锚必须高于周期锚。

    实测第一版（按分类分组造尺子）造出来的尺子是**反的**：
    周期带 26–65 / 结构性带 37–65 → 15/36 只票「尺子不可用」。
    分位尺子在结构上不可能反转，这条钉住它不许退化回去。
    """
    mod = _load_sg("pe_bands", "_bands2")
    if mod is None:
        return ["pe_bands.py 加载失败"]
    bs = mod.build_bands(_heavy_tail_peers(mod))
    bad = []
    if not bs.is_valid():
        bad.append(f"重尾样本下尺子无效：{bs.note}")
    if not bs.structural.low > bs.cyclical.low:
        bad.append(f"结构性锚 {bs.structural.low:.1f} 未高于周期锚 {bs.cyclical.low:.1f}")
    if not (bs.cyclical.high <= bs.base.high <= bs.structural.high):
        bad.append("三条带上沿不单调：周期/基准/结构性必须递增")
    return bad


def check_priced_in_uses_lower_edge_not_mid() -> list:
    """锚点必须用**下沿**，不是中值。

    实测教训：结构性带上沿被 TSLA/PLTR/AMD 顶到 176x，中值 117x。
    拿中值当上行目标算出 NVDA 上行 +256%、SMCI +661% —— 那是把
    「池子里最贵那一档」当成了目标价，不是重估空间。
    """
    bands_mod = _load_sg("pe_bands", "_bands3")
    rp = _load_sg("repricing", "_bands3")
    if bands_mod is None or rp is None:
        return ["模块加载失败"]
    bs = bands_mod.build_bands(_heavy_tail_peers(bands_mod))

    pe = 33.0
    _ratio, up, _down, _note = rp.asymmetry(pe, bs.cyclical, bs.structural)
    if up is None:
        return ["asymmetry 返回 upside=None"]

    expected = (bs.structural.low - pe) / pe * 100
    bad = []
    if abs(up - expected) > 0.5:
        bad.append(
            f"上行空间 {up:.1f}% 不等于按下沿算的 {expected:.1f}% —— "
            f"锚点被换成了中值（结构性带中值 {bs.structural.mid:.1f}x 被长尾拉爆）"
        )
    # 顺带钉住：用中值算出来的数一定大得离谱，这里守住合理上界
    if up > 150:
        bad.append(f"上行空间 {up:.1f}%（>150%），读数已经不是重估空间了")
    return bad


def check_asymmetry_none_on_tiny_downside() -> list:
    """下行空间趋零时，不对称比必须返回 None。

    实测 GOOGL：PE 25.98 几乎贴着周期锚，下行只剩 3.9% → 比值 32。
    那是**分母趋零的数学假象**，不是「赔率极好」。
    """
    bands_mod = _load_sg("pe_bands", "_bands4")
    rp = _load_sg("repricing", "_bands4")
    if bands_mod is None or rp is None:
        return ["模块加载失败"]
    bs = bands_mod.build_bands(_heavy_tail_peers(bands_mod))

    # 恰好落在周期锚上方一点点 → 下行空间 < 15%
    pe = bs.cyclical.low * 1.02
    ratio, up, down, note = rp.asymmetry(pe, bs.cyclical, bs.structural)
    bad = []
    if down is not None and down < rp.MIN_DOWNSIDE_PCT and ratio is not None:
        bad.append(
            f"下行仅 {down:.1f}% 却返回了不对称比 {ratio:.1f} —— "
            "分母趋零会把比值顶到几十上百，是假象不是赔率"
        )
    if not note:
        bad.append("返回 None 却没写原因（页面上看不出是失效还是没算）")
    return bad


def check_self_excluded_from_own_ruler() -> list:
    """一只票不许参与定义衡量自己的尺子。

    小池子里把自己算进分布会把 priced_in 系统性拉向 0.5 ——
    读数「永远是中间」，看起来很合理，其实什么都没测。
    """
    mod = _load_sg("pe_bands", "_bands5")
    if mod is None:
        return ["pe_bands.py 加载失败"]
    peers = _heavy_tail_peers(mod)
    n = len(peers)
    bs = mod.build_bands(peers, exclude_code="C0")
    bad = []
    if bs.samples != n - 1:
        bad.append(f"exclude_code 未生效：samples={bs.samples}，应为 {n - 1}")
    return bad


def check_ifrs_namespace_not_dropped() -> list:
    """外国发行人（TSM/ASML…）以 20-F 报送，命名空间是 ``ifrs-full``。

    只读 ``us-gaap`` 会让这类票**静默地一期都取不到**（2026-10-20 实测
    TSM / ASML 都是 0 期，页面上只是含糊的「分类未定」，看不出是我们读不到
    还是它真没有）。合并视图必须把其它命名空间也带上，且 ``us-gaap`` 优先。
    """
    mod = _load_sg("financial_data_fetcher", "_ns")
    if mod is None:
        return ["financial_data_fetcher.py 加载失败"]
    fn = getattr(mod, "_normalize_namespaces", None)
    if fn is None:
        return ["找不到 _normalize_namespaces（IFRS 支持被删了？）"]
    bad = []
    merged = fn({"ifrs-full": {"Revenue": {"units": {"EUR": []}}}})
    if "Revenue" not in merged:
        bad.append("ifrs-full 命名空间被丢弃 —— TSM/ASML 这类票会一期都取不到")
    merged2 = fn({"us-gaap": {"Revenues": {"units": {"USD": []}}},
                  "ifrs-full": {"Revenues": {"units": {"EUR": []}}}})
    body = merged2.get("Revenues") or {}
    if "USD" not in (body.get("units") or {}):
        bad.append("同名 tag 没有让 us-gaap 胜出（EUR 把 USD 顶掉了）")
    return bad


def check_financial_disk_cache() -> list:
    """财报必须落盘：内存缓存重启即空。

    实测全池 36 只冷启动 **1337 秒**（22 分钟），页面第一次打开根本打不开。
    年度数据的 TTL 是一天，落盘后重启 + 二次请求都可以秒回。
    """
    import tempfile

    mod = _load_sg("financial_data_fetcher", "_disk")
    if mod is None:
        return ["financial_data_fetcher.py 加载失败"]
    SF = getattr(mod, "StockFinancial", None)
    if SF is None:
        return ["找不到 StockFinancial"]

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        sample = [SF(stock_code="ZZZ", report_date="2025",
                     revenue=100.0, net_profit=10.0, gross_margin=50.0)]
        writer = mod.FinancialDataFetcher(cache_dir=d)
        try:
            writer._disk_write("ZZZ", sample, mod.ST_OK, "")
        except Exception as e:  # noqa: BLE001
            return [f"写入磁盘缓存异常：{type(e).__name__}: {e}"]

        bad = []
        hit = mod.FinancialDataFetcher(cache_dir=d)._disk_read("ZZZ")
        if hit is None:
            bad.append("另一个实例读不到磁盘缓存（重启后又要重拉一遍全池）")
        elif len(hit[0]) != 1 or abs(hit[0][0].gross_margin - 50.0) > 1e-6:
            bad.append(f"磁盘缓存回读失真：{hit[0]}")
        elif hit[1] != mod.ST_OK:
            bad.append(f"磁盘缓存丢了抓取状态：{hit[1]}")

        # 损坏文件必须按未命中处理，不能炸
        (d / "ZZZ.json").write_text("{ 这不是 json", encoding="utf-8")
        try:
            if mod.FinancialDataFetcher(cache_dir=d)._disk_read("ZZZ") is not None:
                bad.append("损坏的缓存文件被当成有效数据读了")
        except Exception as e:  # noqa: BLE001
            bad.append(f"读损坏缓存文件抛异常（应当优雅降级）：{type(e).__name__}")

        # 负缓存：失败要比成功更早过期，不能把一次故障冻一天
        if not (getattr(mod, "ERROR_TTL", 0) < getattr(mod, "OK_TTL", 0)):
            bad.append("负缓存 TTL 不短于正缓存 —— 一次网络故障会被冻住一整天")
        return bad


def check_fetch_status_not_silently_folded() -> list:
    """``empty``（这家真没有财报）和 ``error``（我们没取到）不许合并。

    两者表象都是空列表。合并成一句「财报不足或缺失」＝用户分不清该等待还是该
    排除 —— 这正是「合法的空比异常更危险」那条。
    """
    tree = _parse(FINFETCH_PY)
    if tree is None:
        return ["financial_data_fetcher.py 语法错误"]
    returns = {"ST_EMPTY": 0, "ST_ERROR": 0}
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
            for el in node.value.elts:
                if isinstance(el, ast.Attribute):
                    if el.attr in returns:
                        returns[el.attr] += 1
                elif isinstance(el, ast.Name) and el.id in returns:
                    returns[el.id] += 1
    bad = []
    if returns["ST_EMPTY"] < 1:
        bad.append("没有任何地方返回 ST_EMPTY —— 「确实没有财报」这一档丢了")
    if returns["ST_ERROR"] < 2:
        bad.append(f"ST_ERROR 只有 {returns['ST_ERROR']} 处返回，失败路径大概是折叠进了 empty")

    def _const_text(node) -> str:
        out = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.append(sub.value)
        return " ".join(out)

    def _status_name(el) -> str:
        if isinstance(el, ast.Name):
            return el.id
        if isinstance(el, ast.Attribute):
            return el.attr
        if isinstance(el, ast.Call):
            return _status_name(el.func)
        return (getattr(el, "value", None) or "") if False else ""

    # ❗HTTP 状态码失败是**我们的故障**，不是「这家公司没有财报」。
    #   把它标成 empty 会让运维以为该标的天生无量，永久跳过一次其实可恢复的失败。
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)):
            continue
        elts = node.value.elts
        if len(elts) != 3:
            continue
        reason = _const_text(elts[2])
        status = _status_name(elts[1])
        if "HTTP" in reason and status != "ST_ERROR":
            bad.append(
                f"HTTP 失败被标成 {status or '未知'}（{reason[:40]}）—— "
                "这是抓取失败，不是「该标的无财报」"
            )

    svc = _parse(SG_DIR / "repricing_service.py")
    if svc is None:
        return bad + ["repricing_service.py 语法错误"]
    src = svc and (SG_DIR / "repricing_service.py").read_text(encoding="utf-8") or ""
    if 'status == "error"' not in src or 'status == "empty"' not in src:
        bad.append("编排层没有按 fetch status 分文案 —— 失败和缺失又会合成一句话")
    return bad


def check_revenue_tags_cover_common_variants() -> list:
    """营收标签必须覆盖常见变体。

    实测两处翻车：CRWD 报 ``RevenueFromContractWithCustomer**Including**
    AssessedTax``（我们只认 Excluding）→ 整票被判「无年度营收标签」；
    多家 IFRS 发行人用 ``Revenue`` / ``RevenueFromSaleOfGoods``。
    """
    src = FINFETCH_PY.read_text(encoding="utf-8")
    need = {
        "CRWD 用的 Including 变体": "RevenueFromContractWithCustomerIncludingAssessedTax",
        "IFRS 通用 Revenue": '"Revenue"',
        "IFRS 的场景拆分": "RevenueFromContractsWithCustomers",
        "IFRS 现金流": "CashFlowsFromUsedInOperatingActivities",
        "IFRS capex": "PurchaseOfPropertyPlantAndEquipment",
    }
    return [f"候选标签缺 {desc}（{tag}）" for desc, tag in need.items() if tag not in src]


def check_pool_warmed_before_evaluate() -> list:
    """``evaluate_all`` 必须先并发预热全池。

    不预热的话第一只票要串行等地 36 只票的网络往返（实测分钟级），而 UI 是
    在一次请求里同步等的 —— 页面就会「看起来卡死但不报错」。
    """
    path = SG_DIR / "repricing_service.py"
    tree = _parse(path)
    if tree is None:
        return ["repricing_service.py 语法错误"]
    src = path.read_text(encoding="utf-8")
    bad = []
    if "ThreadPoolExecutor" not in src:
        bad.append("没有并发：全池冷启动会是串行叠加，实测可达分钟级")
    calls_warm = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_all":
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "warm"):
                    calls_warm = True
    if not calls_warm:
        bad.append("evaluate_all 没有调 warm() —— 预热写了但没接上等于没写")
    return bad


_ALL = [
    check_no_hardcoded_pe,
    check_loss_making_pe_is_none,
    check_market_detection_not_whitelist_only,
    check_classifier_unknown_on_sparse_data,
    check_margin_swing_is_cyclical,
    check_asymmetry_none_below_cyclical,
    check_entry_grid_complete,
    check_cyclical_overpriced_is_trap,
    check_single_negative_is_not_cyclical,
    check_weak_evidence_alone_cannot_classify,
    check_unprofitable_negative_is_weak,
    check_confidence_is_net_margin,
    check_missing_flagged_samples_excluded,
    check_missing_net_profit_not_forged,
    check_volatility_metric_is_scale_robust,
    check_bands_measured_when_enough_samples,
    check_bands_never_invert,
    check_priced_in_uses_lower_edge_not_mid,
    check_asymmetry_none_on_tiny_downside,
    check_self_excluded_from_own_ruler,
    check_ifrs_namespace_not_dropped,
    check_financial_disk_cache,
    check_fetch_status_not_silently_folded,
    check_revenue_tags_cover_common_variants,
    check_pool_warmed_before_evaluate,
]


def _all_checks() -> list:
    failures: list = []
    for fn in _ALL:
        try:
            failures.extend(fn())
        except Exception as e:  # noqa: BLE001
            failures.append(f"{fn.__name__} 抛异常: {type(e).__name__}: {e}")
    return failures


# ------------------------------------------------------------ 负向注入

INJECTIONS = [
    {
        "name": "硬编码 PE 常量复活",
        "path": FETCHER_PY,
        "old": "        # 形态判定：纯 ASCII 字母（1-5 位）＝美股 ticker。",
        "new": "        us_fundamentals = {'NVDA': {'pe': 65.0, 'market_cap': 2800000000000}}\n"
               "        # 形态判定：纯 ASCII 字母（1-5 位）＝美股 ticker。",
    },
    {
        "name": "亏损股 PE 解析成 0（把「--」当成 0 倍）",
        "path": FETCHER_PY,
        "old": "    if not text or text in (\"--\", \"-\", \"N/A\", \"null\", \"None\"):\n        return None",
        "new": "    if not text or text in (\"--\", \"-\", \"N/A\", \"null\", \"None\"):\n        return 0.0",
    },
    {
        "name": "市场判定退回只靠白名单（新标的认不出）",
        "path": FETCHER_PY,
        "old": "        if stock_code.isascii() and stock_code.isalpha() and 1 <= len(stock_code) <= 5:\n            return Market.US",
        "new": "        if False:\n            return Market.US",
    },
    {
        "name": "数据不足时默认成 BASE（把「没数据」读成「稳态」）",
        "path": CLASSIFIER_PY,
        "old": "            regime=ValuationRegime.UNKNOWN,\n            confidence=0.0,",
        "new": "            regime=ValuationRegime.BASE,\n            confidence=0.0,",
    },
    {
        "name": "去掉毛利率扩张上限（周期反转被当成结构性改善）",
        "path": CLASSIFIER_PY,
        "old": "            if monotonic and MARGIN_EXPANSION_PP <= uplift <= MAX_MARGIN_UPLIFT_PP:",
        "new": "            if monotonic and uplift >= MARGIN_EXPANSION_PP:",
    },
    {
        "name": "不对称比在跌破周期带时返回 inf",
        "path": REPRICING_PY,
        "old": "        return (None, upside_pct, downside_pct,\n                \"已跌破周期锚：下行空间失效，需人工判断（可能是价值陷阱）\")",
        "new": "        return (float('inf'), upside_pct, downside_pct, \"\")",
    },
    {
        "name": "九宫格挖掉一格（页面出现黑屏）",
        "path": REPRICING_PY,
        "old": "    (\"late\", \"high\"): \"业绩兑现即出货区：利润已兑现且已定价，剩余空间靠不到重估。\",",
        "new": "",
    },
    {
        "name": "只在注释里写 65.0（不该误报）",
        "path": FETCHER_PY,
        "old": "        # 形态判定：纯 ASCII 字母（1-5 位）＝美股 ticker。",
        "new": "        # 历史值：NVDA pe 65.0（仅作说明，不参与计算）\n"
               "        # 形态判定：纯 ASCII 字母（1-5 位）＝美股 ticker。",
        "expect_clean": True,
    },
    {
        "name": "C2 退回「出现负增长即命中」（88% 必然事件）",
        "path": CLASSIFIER_PY,
        "old": "    if neg_share >= NEG_SHARE_MIN:",
        "new": "    if any(v < 0 for v in yoy):",
    },
    {
        "name": "强证据门槛退回用分数判断（两条弱证据也能定类）",
        "path": CLASSIFIER_PY,
        "old": "    str_ok = str_strong >= 1",
        "new": "    str_ok = str_score >= MIN_SCORE",
    },
    {
        # ❗注入必须落在**真正管降级**的那一行。只把 c2_weight 改成 STRONG_WEIGHT
        # 是不够的：``if not unprofitable: cyc_strong += 1`` 还在，cyc_strong 仍然
        # 不加，SNOW 照样不定周期 —— 注入看着生效、守卫全绿，其实是摆设。
        "name": "亏损公司的负增长不降级（SNOW 被误判成周期股）",
        "path": CLASSIFIER_PY,
        "old": "        cyc_score += c2_weight\n"
               "        if not unprofitable:\n"
               "            cyc_strong += 1\n"
               "        cyc_hits.append(f\"负增长期数占比 {neg_share:.0%}",
        "new": "        cyc_score += STRONG_WEIGHT\n"
               "        cyc_strong += 1\n"
               "        cyc_hits.append(f\"负增长期数占比 {neg_share:.0%}",
    },
    {
        "name": "confidence 退回「只看自己一侧」（争议案例显示满分）",
        "path": CLASSIFIER_PY,
        "old": "    confidence = round(max(0.0, margin) / ideal, 2) if ideal else 0.0",
        "new": "    confidence = round(side_score / side_max, 2) if side_max else 0.0",
    },
    {
        "name": "不剔除缺失样本（毛利率假 0 被当成真实毛利率）",
        "path": CLASSIFIER_PY,
        "old": "        if m is None or _missing(f, \"gross_margin\"):",
        "new": "        if m is None:",
    },
    {
        "name": "净利缺失填 0（伪造出 −100% 同比，AVGO 型）",
        "path": FINFETCH_PY,
        "old": "            ni = net_income.get(year)\n            if ni is None:\n                ni = net_income_alt.get(year)",
        "new": "            ni = net_income.get(year, 0.0)",
    },
    {
        "name": "波动度量退回原始标准差（极端值支配尺度）",
        "path": CLASSIFIER_PY,
        "old": "        compressed = [math.copysign(math.log1p(abs(v)), v) for v in yoy]",
        "new": "        compressed = list(yoy)",
    },
    {
        "name": "样本足够却退回经验常量（尺子变成拍脑袋）",
        "path": BANDS_PY,
        "old": "MIN_SAMPLES = 8",
        "new": "MIN_SAMPLES = 10 ** 9",
    },
    {
        "name": "分位切点错配导致尺子反转（周期带比结构性带还贵）",
        "path": BANDS_PY,
        "old": "LOW_Q = (0.15, 0.40)",
        "new": "LOW_Q = (0.65, 0.90)",
    },
    {
        "name": "锚点退回中值（长尾把上行目标顶到 117x）",
        "path": REPRICING_PY,
        "old": "    return cyclical.low, structural.low",
        "new": "    return cyclical.low, structural.mid",
    },
    {
        "name": "取消下行空间护栏（分母趋零造出假的不对称比）",
        "path": REPRICING_PY,
        "old": "MIN_DOWNSIDE_PCT = 15.0",
        "new": "MIN_DOWNSIDE_PCT = 0.0",
    },
    {
        "name": "自己参与定义衡量自己的尺子",
        "path": BANDS_PY,
        "old": '        if (p.code or "").upper() == skip:',
        "new": '        if False and (p.code or "").upper() == skip:',
    },
    {
        "name": "命名空间退回只读 us-gaap（TSM/ASML 静默取不到数）",
        "path": FINFETCH_PY,
        "old": "    for ns in list(reversed(rest)) + list(reversed(order)):",
        "new": "    for ns in list(reversed(rest)) + list(reversed([])):",
    },
    {
        "name": "财报缓存退回只存内存（重启即冷启动 20 分钟）",
        "path": FINFETCH_PY,
        "old": "            os.replace(tmp, path)     # 原子替换：读到的一定是完整文件",
        "new": "            os.replace(tmp, path)\n            if True: path.unlink(missing_ok=True)",
    },
    {
        "name": "抓取失败被折叠成「无财报」（故障与事实混淆）",
        "path": FINFETCH_PY,
        "old": '            return [], ST_ERROR, f"SEC companyfacts HTTP {resp.status_code}"',
        "new": '            return [], ST_EMPTY, f"SEC companyfacts HTTP {resp.status_code}"',
    },
    {
        "name": "营收标签删掉 CRWD 用的 Including 变体",
        "path": FINFETCH_PY,
        "old": '            "RevenueFromContractWithCustomerIncludingAssessedTax",\n',
        "new": "",
    },
    {
        "name": "evaluate_all 不预热全池（首屏串行等 36 次网络）",
        "path": SG_DIR / "repricing_service.py",
        "old": "        targets = list(codes or self.all_codes)\n        self.warm(targets)",
        "new": "        targets = list(codes or self.all_codes)\n        _ = self.warm",
    },
]


def run_injections() -> int:
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path = Path(inj["path"])
        original = path.read_text(encoding="utf-8")
        hits = original.count(inj["old"])
        if hits != 1:
            missed.append(inj["name"])
            print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")

        if inj.get("expect_clean"):
            if found:
                print(f"  ❌ 反方向用例被误报：{found[0][:110]}")
            else:
                caught += 1
                print("  ✅ 正确地没有报警（注释不算硬编码）")
        elif found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            for f in found[:2]:
                print(f"       · {f[:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")

        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")

    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（另有 {len(missed)} 条锚点未命中，已计失败）" if missed else ""))
    return caught if not missed else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    if failures:
        print("❌ 结构性增长 PE 守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 结构性增长 PE 守卫全绿"
          "（无硬编码 PE · 亏损股报缺失 · 新标的认得出 · 数据不足 unknown · "
          "跌破周期带返 None · 九宫格无空格 · 周期股高定价判陷阱）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
