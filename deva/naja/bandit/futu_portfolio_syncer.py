"""FutuPortfolioSyncer - 富途持仓同步器

功能：
1. 从 Futu OpenD 获取**各品牌实盘账户**的持仓（富途牛牛 + moomoo 各市场）
2. 每个账户在 Bandit 里独立成一个账户块（FutuHK / MoomooUS / ...）
3. 支持手动 / 定时同步

为什么必须遍历品牌，而不是写死一个
----------------------------------
富途牛牛与 moomoo **共用同一套 OpenD + futu-api**，靠 ``security_firm``
区分品牌与地区：``FUTUSECURITIES`` = 富途证券（香港），``FUTUINC`` =
moomoo 美国，其余为 moomoo 各地。老实现只连 ``FUTUSECURITIES``，
于是 moomoo 美国的持仓**一直同步不过来**，页面上完全看不到。

为什么一个账户一块，而不是合并成一块
------------------------------------
它们是各自独立的券商账户：币种不同（HKD / USD）、净资产不同、风控不同。
合并会把两种币种的市值直接相加（页面汇总不做汇率换算），总市值与总盈亏
都会失真。

为什么取「主综合账户」而不是子账户
----------------------------------
实测（2026-10-14，本机 OpenD）：
  * 富途香港主账户 1001200156527585 → HK.06666/27500、HK.00100/120
    （HK / US / HKCC 三个分市场子账户查询**恒为 0**）
  * moomoo 美国主账户 1007201500505626 → SKUU/NVDA/JPM/CRWV/AMD/ALAB 共 6 只
所以持仓**归集在主账户**上：查主账户既不会漏，也不会重复计。
判定「主账户」依据 ``uni_card_num``（= 手机上看到的账号）非空。

用法：
    syncer = FutuPortfolioSyncer()
    result = syncer.sync()
    for acc in result.accounts:
        print(acc.name, acc.positions, acc.ok, acc.error)

调度示例（每5分钟同步）：
    from deva import scheduler
    scheduler.every(300).seconds.do(lambda: FutuPortfolioSyncer().sync())
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from deva import NB
from deva.naja.bandit.data_freshness import get_freshness_tracker, SOURCE_FUTU_SYNC

log = logging.getLogger(__name__)

UNIFIED_POSITIONS_TABLE = "naja_bandit_positions"
FUTU_ACCOUNTS_TABLE = "naja_bandit_futu_accounts"

HOST = "127.0.0.1"
PORT = 11111

# 券商标识 → Bandit 账户名。
# 账户名会出现在 Bandit 页面区块标题与 PortfolioManager 名册里，
# 所以必须能一眼看出「哪家券商、哪个地区」。
SECURITY_FIRM_ACCOUNT_NAMES: Dict[str, str] = {
    "FUTUSECURITIES": "FutuHK",   # 富途证券（香港）
    "FUTUINC": "MoomooUS",        # moomoo 美国
    "FUTUSG": "MoomooSG",
    "FUTUAU": "MoomooAU",
    "FUTUCA": "MoomooCA",
    "FUTUJP": "MoomooJP",
    "FUTUMY": "MoomooMY",
}

# 品牌本地币种：用来在没有持仓（推不出币种）时给资金查询兜底
SECURITY_FIRM_DEFAULT_CURRENCY: Dict[str, str] = {
    "FUTUSECURITIES": "HKD",
    "FUTUINC": "USD",
    "FUTUSG": "SGD",
    "FUTUAU": "AUD",
    "FUTUCA": "CAD",
    "FUTUJP": "JPY",
    "FUTUMY": "MYR",
}

# 历史账户名。``FutuReal`` 是 ``FutuHK`` 的旧名：不清掉就会在页面上留下
# 一个永不更新的僵尸账户 —— 位置还在、数字永远停在改名那一刻。
LEGACY_ACCOUNT_NAMES = frozenset({"FutuReal"})

# 模拟账户（``TrdEnv.SIMULATE``）账户块的统一前缀。
#
# 为什么**不复用品牌名**（FutuHK / MoomooUS）
# ------------------------------------------
# 富途的模拟账户是**全局共享、不分品牌**的：逐品牌调 ``get_acc_list()``，
# 7 个品牌每一个都会把**同一批**模拟账户原样返回一遍。若沿用品牌命名，
# 同一批账户会被重复写入 7 次且彼此重名（实测：14 个目标 / 7 组重名）。
# 模拟账户也用不上 ``security_firm``（该字段对模拟账户恒为 ``N/A``）。
SIM_ACCOUNT_PREFIX = "FutuSim"

# 模拟账户品类 → 账户名后缀。STOCK / STOCK_AND_OPTION 视为默认品类不加后缀，
# 其余加后缀，好让同市场下的多个模拟账户（如港股股票 + 港股期权）名字唯一。
SIM_ACC_TYPE_SUFFIX: Dict[str, str] = {
    "STOCK": "",
    "STOCK_AND_OPTION": "",
    "OPTION": "Option",
    "FUTURES": "Futures",
}

_MARKET_CURRENCY: Dict[str, str] = {
    "HK": "HKD",
    "US": "USD",
    "HKCC": "CNH",
    "CN": "CNH",
    "SG": "SGD",
    "JP": "JPY",
}


# ------------------------------------------------------------------ 工具

def _clean(value: Any) -> str:
    """富途用 ``N/A`` 表示「不适用」；统一成空串，免得被当成有效值使用。"""
    text = str(value).strip()
    return "" if text in ("", "N/A", "None", "nan", "NaN") else text


def _num(value: Any) -> float:
    """安全转 float —— 富途不少字段会返回 ``N/A``（非保证金账户尤甚）。"""
    try:
        if value is None or (isinstance(value, str) and _clean(value) == ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _card_num(row) -> str:
    """主账户在手机上显示的账号（``uni_card_num``）；子账户/模拟账户为空。"""
    return _clean(row.get("uni_card_num", ""))


def _market_auth(row) -> List[str]:
    """该账户拥有交易权限的市场列表（可能是 list，也可能是字符串形式）。"""
    raw = row.get("trdmarket_auth")
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x) for x in raw]
    return [p.strip().strip("'\"") for p in str(raw).strip("[]").split(",") if p.strip()]


def _split_code(code: str) -> Tuple[str, str]:
    """``HK.06666`` / ``US.NVDA`` → ``("HK", "06666")``；无前缀按美股处理。"""
    if "." in code:
        prefix, _, rest = code.partition(".")
        return (prefix.upper() or "US"), rest
    return "US", code


def decide_currency(firm: str, positions: Sequence[Dict[str, Any]]) -> str:
    """决定用哪个币种口径查询资金（页面上也用它挑货币符号）。

    优先按持仓市场多数决 —— 这样 HKD 账户的资金不会被显示成美元数字，
    美元账户也不会被显示成港币数字。没有持仓时退回品牌本地币种。
    """
    counts: Dict[str, int] = {}
    for pos in positions:
        ccy = _clean(pos.get("currency", "")) or _MARKET_CURRENCY.get(pos.get("market", ""), "")
        if ccy:
            counts[ccy] = counts.get(ccy, 0) + 1
    if counts:
        return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return SECURITY_FIRM_DEFAULT_CURRENCY.get(firm, "USD")


# ------------------------------------------------------------------ 结果

@dataclass
class AccountSyncResult:
    """单个富途账户的同步结果。"""

    name: str
    firm: str
    acc_id: Optional[int] = None
    positions: int = 0
    ok: bool = False
    error: str = ""

    def describe(self) -> str:
        if self.ok:
            return f"{self.name} {self.positions} 只"
        return f"{self.name} 失败（{self.error}）"


@dataclass
class SyncResult:
    """一次同步的整体结果。

    ``__bool__`` 走 ``ok``：全部账户成功才算成功 —— 一个账户静默失败
    而整体报「成功」，正是这个页面最该避免的事（数字看着新，其实是旧的）。
    """

    accounts: List[AccountSyncResult] = field(default_factory=list)
    probe_errors: List[str] = field(default_factory=list)
    stale_removed: List[str] = field(default_factory=list)
    wrote: bool = False

    @property
    def ok(self) -> bool:
        return (
            bool(self.accounts)
            and all(a.ok for a in self.accounts)
            and not self.probe_errors
        )

    def __bool__(self) -> bool:  # 让 `if syncer.sync():` 仍然可用
        return self.ok

    def summary(self) -> str:
        if not self.accounts:
            return "；".join(self.probe_errors) or "未发现可同步的实盘账户"
        return "；".join(a.describe() for a in self.accounts)

    def failure_reason(self) -> str:
        parts = list(self.probe_errors)
        parts += [f"{a.name}：{a.error}" for a in self.accounts if not a.ok]
        return "；".join(parts)


# ------------------------------------------------------------------ 主体

class FutuPortfolioSyncer:
    """富途持仓同步器（多品牌、多账户）

    默认同步 REAL 真实环境；如需同步模拟持仓，传 ``trd_env="SIMULATE"``。
    """

    def __init__(
        self,
        trd_env: str = "REAL",
        firms: Optional[Sequence[str]] = None,
    ):
        self.trd_env = trd_env
        self.firms = list(firms) if firms else list(SECURITY_FIRM_ACCOUNT_NAMES)
        self._ctx = None

    # ---------------------------------------------------------- 连接

    def _ensure_futu_api(self) -> bool:
        """确保 futu-api 已安装"""
        try:
            import futu  # noqa: F401
            return True
        except ImportError:
            log.error("futu-api 未安装，请运行: pip install futu-api")
            return False

    def _create_trade_context(self, firm: str):
        """按品牌创建交易上下文"""
        if not self._ensure_futu_api():
            return None

        try:
            from futu import OpenSecTradeContext, SecurityFirm

            target = getattr(SecurityFirm, firm, SecurityFirm.FUTUSECURITIES)
            return OpenSecTradeContext(host=HOST, port=PORT, security_firm=target)
        except Exception as e:
            log.error("[FutuSyncer] 创建交易上下文失败（%s）: %s", firm, e)
            return None

    def _close_context(self, ctx=None):
        """关闭上下文"""
        target = ctx if ctx is not None else self._ctx
        if target is None:
            return
        try:
            target.close()
        except Exception:
            pass
        if target is self._ctx:
            self._ctx = None

    def _get_futu_trd_env(self):
        """获取 Futu 交易环境枚举"""
        try:
            from futu import TrdEnv
            return TrdEnv.SIMULATE if self.trd_env == "SIMULATE" else TrdEnv.REAL
        except Exception:
            return 0

    def _is_simulate(self) -> bool:
        """本次同步是否走模拟环境。"""
        return self.trd_env.upper() == "SIMULATE"

    @staticmethod
    def _sim_target_name(row: Dict[str, Any]) -> str:
        """给一个模拟账户起名，如 ``FutuSimHK`` / ``FutuSimHKOption``。

        模拟账户**没有品牌**（``security_firm`` 恒为 N/A），所以名字里只带
        市场与品类：市场保证看得出交易范围，品类保证同市场多账户不撞名。
        """
        market = (row.get("market_auth") or ["X"])[0]
        kind = str(row.get("sim_acc_type") or "").upper()
        return f"{SIM_ACCOUNT_PREFIX}{market}{SIM_ACC_TYPE_SUFFIX.get(kind, kind.title())}"

    # ---------------------------------------------------------- 账户探测

    def _probe_firm(self, firm: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """枚举一个品牌下的账户。

        Returns:
            ``(是否查询成功, 账户行列表)``。第二个值为 False 时表示
            **分不清「没有账户」与「连不上」** —— 调用方必须区别对待，
            否则一次网络抖动就会把页面上的数据清成空。
        """
        if not self._ensure_futu_api():
            return False, []

        try:
            from futu import OpenSecTradeContext, RET_OK, SecurityFirm

            ctx = OpenSecTradeContext(
                host=HOST, port=PORT,
                security_firm=getattr(SecurityFirm, firm, SecurityFirm.FUTUSECURITIES),
            )
            try:
                ret, data = ctx.get_acc_list()
            finally:
                ctx.close()

            if ret != RET_OK:
                log.debug("[FutuSyncer] %s 账户枚举失败: %s", firm, str(data)[:120])
                return False, []

            rows: List[Dict[str, Any]] = []
            for i in range(0 if data is None else len(data)):
                row = data.iloc[i]
                rows.append({
                    "acc_id": int(row.get("acc_id", 0) or 0),
                    "card_num": _card_num(row),
                    "acc_type": _clean(row.get("acc_type", "")),
                    "trd_env": _clean(row.get("trd_env", "")),
                    "market_auth": _market_auth(row),
                    "acc_role": _clean(row.get("acc_role", "")),
                    "sim_acc_type": _clean(row.get("sim_acc_type", "")),
                    "security_firm": firm,
                })
            return True, rows
        except Exception as e:
            log.debug("[FutuSyncer] %s 账户枚举异常: %s", firm, e)
            return False, []

    def get_accounts(self) -> List[Dict[str, Any]]:
        """列出所有品牌下的全部账户（含模拟账户），供界面展示。"""
        accounts: List[Dict[str, Any]] = []
        for firm in self.firms:
            ok, rows = self._probe_firm(firm)
            if ok:
                accounts.extend(rows)
        log.info("[FutuSyncer] 发现 %d 个富途账户", len(accounts))
        return accounts

    def _select_main_accounts(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从某品牌的账户行里挑出本次要同步的账户。"""
        wanted = [r for r in rows if r["trd_env"].upper() == self.trd_env.upper()]
        if not wanted:
            return []
        if self.trd_env.upper() != "REAL":
            return wanted                       # 模拟账户不分主/子，全取

        mains = [r for r in wanted if r["card_num"]]
        if not mains:
            return wanted

        covered: Set[str] = set()
        for main in mains:
            covered |= set(main["market_auth"])

        selected = list(mains)
        for row in wanted:
            if row in mains:
                continue
            # 主账户没覆盖的市场必须单独取，否则该市场的持仓会漏掉
            if set(row["market_auth"]) - covered:
                selected.append(row)
        return selected

    def get_sync_targets(
        self,
    ) -> Tuple[List[Dict[str, Any]], List[str], Set[str]]:
        """决定本次要同步的账户。

        Returns:
            ``(目标账户列表, 枚举失败的品牌说明, 枚举成功的品牌集合)``

        模拟环境（``trd_env="SIMULATE"``）与真实环境的取法**必须分开**：

        * 模拟账户**全局共享、不分品牌** —— 逐品牌枚举会让同一批账户
          被返回 7 遍。这里**按 ``acc_id`` 跨品牌去重**，只保留首次见到的那份。
        * 模拟账户命名**不带品牌**（``FutuSimHK`` / ``FutuSimHKOption``）：
          同一个品牌下可能同时有股票与期权两个模拟账户，同市场下
          ``f"{base}_{market}"`` 必然撞名（实测 ``FutuHK_HK`` × 2）。
        """
        targets: List[Dict[str, Any]] = []
        probe_errors: List[str] = []
        probed_ok: Set[str] = set()
        is_sim = self._is_simulate()
        seen_acc_ids: Set[int] = set()

        for firm in self.firms:
            ok, rows = self._probe_firm(firm)
            if not ok:
                probe_errors.append(f"{firm} 账户列表查询失败")
                continue
            probed_ok.add(firm)

            selected = self._select_main_accounts(rows)
            if is_sim:
                # 模拟账户跨品牌重复：同一个 acc_id 只取一次
                selected = [r for r in selected if r["acc_id"] not in seen_acc_ids]
                seen_acc_ids.update(r["acc_id"] for r in selected)

            multi = len(selected) > 1
            base = SECURITY_FIRM_ACCOUNT_NAMES.get(firm, firm)
            for row in selected:
                if is_sim:
                    name = self._sim_target_name(row)
                elif multi:
                    # 一个品牌有多个账户时才加市场后缀，避免名字撞车
                    market = (row["market_auth"] or ["X"])[0]
                    name = f"{base}_{market}"
                else:
                    name = base
                targets.append({
                    "name": name,
                    "firm": firm,
                    "acc_id": row["acc_id"],
                    "card_num": row["card_num"],
                    "market_auth": list(row["market_auth"]),
                    "acc_type": row["acc_type"],
                    "trd_env": self.trd_env.upper(),
                })
        return targets, probe_errors, probed_ok

    # ---------------------------------------------------------- 取数

    def _parse_positions(self, pos_data) -> List[Dict[str, Any]]:
        """把 ``position_list_query`` 的结果转成统一的持仓字典。

        字段口径以 moomoo APP 显示为准（见 futuapi skill）：
        用 ``average_cost`` / ``nominal_price`` / ``pl_ratio_avg_cost``，
        **不用** ``cost_price`` / ``pl_val`` / ``pl_ratio`` —— 后三者是
        「摊薄成本」口径，会把成本价拉低、让亏损看起来像盈利。
        """
        out: List[Dict[str, Any]] = []
        if pos_data is None or len(pos_data) == 0:
            return out

        for i in range(len(pos_data)):
            row = pos_data.iloc[i]
            raw_code = (
                _clean(row.get("code", ""))
                or _clean(row.get("stock_code", ""))
                or _clean(row.get("symbol", ""))
            )
            market, bare = _split_code(raw_code)
            if not bare:
                continue

            name = _clean(row.get("stock_name", "")) or _clean(row.get("name", ""))
            currency = _clean(row.get("currency", "")) or _MARKET_CURRENCY.get(market, "USD")

            average_cost = _num(row.get("average_cost", 0))
            if average_cost == 0:
                log.debug("[FutuSyncer] %s 无 average_cost 字段，成本价按 0 处理", raw_code)

            out.append({
                "code": bare.lower(),
                "name": name,
                "qty": _num(row.get("qty", 0)),
                "average_cost": average_cost,
                "nominal_price": _num(row.get("nominal_price", 0)),
                "market_val": _num(row.get("market_val", 0)),
                "unrealized_pl": _num(row.get("unrealized_pl", 0)),
                "pl_ratio": _num(row.get("pl_ratio_avg_cost", 0)),
                "prev_close": _num(row.get("prev_close_price", 0) or row.get("prev_close", 0)),
                "currency": currency,
                "market": market,
                "original_code": raw_code,
            })
        return out

    def _query_funds(self, ctx, acc_id: int, currency: str) -> Dict[str, Any]:
        """查询账户资金。币种按调用方指定，避免港币账户显示美元数字。"""
        from futu import RET_OK

        kwargs: Dict[str, Any] = {
            "trd_env": self._get_futu_trd_env(),
            "acc_id": acc_id,
            "refresh_cache": True,
        }
        try:
            from futu import Currency
            enum_value = getattr(Currency, currency, None)
            if enum_value is not None:
                kwargs["currency"] = enum_value
        except Exception:
            pass

        ret, data = ctx.accinfo_query(**kwargs)
        if ret != RET_OK:
            log.warning("[FutuSyncer] 资金查询失败: %s", str(data)[:120])
            return {}
        if data is None or len(data) == 0:
            return {}

        row = data.iloc[0]
        return {
            "total_assets": _num(row.get("total_assets", 0)),
            "cash": _num(row.get("cash", 0)),
            "market_val": _num(row.get("market_val", 0)),
            "power": _num(row.get("power", 0)),
            "currency": _clean(row.get("currency", "")) or currency,
        }

    def _fetch_account(self, ctx, target: Dict[str, Any]) -> Dict[str, Any]:
        """在既有连接里取一个账户的持仓与资金。"""
        from futu import RET_OK

        acc_id = target["acc_id"]
        ret, pos_data = ctx.position_list_query(
            trd_env=self._get_futu_trd_env(), acc_id=acc_id, refresh_cache=True,
        )
        if ret != RET_OK:
            raise RuntimeError(f"持仓查询失败: {str(pos_data)[:120]}")

        positions = self._parse_positions(pos_data)
        currency = self._decide_account_currency(target, positions)
        funds = self._query_funds(ctx, acc_id, currency)
        return {"funds": funds, "positions": positions, "currency": currency}

    def _decide_account_currency(
        self, target: Dict[str, Any], positions: Sequence[Dict[str, Any]],
    ) -> str:
        """决定账户的资金查询币种。

        有持仓时沿用 :func:`decide_currency`（按持仓多数决）。但**模拟账户
        无持仓时不能退回「品牌本地币种」**：模拟账户不分品牌，代码把
        ``target["firm"]`` 记成首个枚举到它的品牌（通常是 ``FUTUSECURITIES``
        → HKD），对港股模拟盘碰巧对，对**美股模拟盘就是凭空造币种**。
        这种情况改按账户自己的市场推。
        """
        if not positions and self._is_simulate():
            market = (target.get("market_auth") or [""])[0]
            return _MARKET_CURRENCY.get(market, "USD")
        return decide_currency(target["firm"], positions)

    def get_portfolio(
        self, acc_id: Optional[int] = None, firm: Optional[str] = None,
    ) -> Dict[str, Any]:
        """取单个账户的持仓与资金（调试/脚本用；页面走 ``sync()``）。

        Returns:
            ``{"funds": {...}, "positions": [...], "currency": "HKD"}``
        """
        targets, _, _ = self.get_sync_targets()
        picked = [
            t for t in targets
            if (firm is None or t["firm"] == firm)
            and (acc_id is None or t["acc_id"] == acc_id)
        ]
        if not picked:
            log.warning("[FutuSyncer] 未找到匹配的账户（firm=%s acc_id=%s）", firm, acc_id)
            return {"funds": {}, "positions": [], "currency": ""}

        target = picked[0]
        ctx = self._create_trade_context(target["firm"])
        if ctx is None:
            return {"funds": {}, "positions": [], "currency": ""}
        try:
            return self._fetch_account(ctx, target)
        finally:
            self._close_context(ctx)

    # ---------------------------------------------------------- 同步

    def _sync_one_target(
        self, target: Dict[str, Any],
    ) -> Tuple[AccountSyncResult, Optional[Dict[str, Any]]]:
        """同步单个账户：取数（失败重试 3 次）+ 写库。"""
        name, firm = target["name"], target["firm"]
        last_error = "取数失败"

        for attempt in range(3):
            ctx = self._create_trade_context(firm)
            if ctx is None:
                last_error = "创建交易连接失败"
                time.sleep(1)
                continue

            data: Optional[Dict[str, Any]] = None
            try:
                data = self._fetch_account(ctx, target)
            except Exception as e:
                last_error = str(e)
                log.warning(
                    "[FutuSyncer] %s 取数失败 (尝试 %d/3): %s", name, attempt + 1, e,
                )
            finally:
                self._close_context(ctx)

            if data is None:
                time.sleep(1)
                continue

            log.info(
                "[FutuSyncer] %s(%s) 取到 %d 个持仓，净资产 %s %s",
                name, firm, len(data["positions"]),
                f"{data['funds'].get('total_assets', 0):,.2f}" if data["funds"] else "-",
                data["currency"],
            )
            return AccountSyncResult(name, firm, target["acc_id"],
                                     positions=len(data["positions"]), ok=True), data

        return AccountSyncResult(name, firm, target["acc_id"], ok=False,
                                 error=last_error), None

    def sync(self) -> SyncResult:
        """同步所有富途实盘账户到 Bandit 系统。

        Returns:
            :class:`SyncResult`（``bool(result)`` 为 True 表示**全部账户**成功）
        """
        result = SyncResult()
        targets, probe_errors, probed_ok = self.get_sync_targets()
        result.probe_errors = probe_errors

        if not targets:
            reason = "；".join(probe_errors) or "未发现可同步的实盘账户（OpenD 未运行或未登录？）"
            log.warning("[FutuSyncer] %s", reason)
            get_freshness_tracker().record_failure(SOURCE_FUTU_SYNC, reason)
            return result

        log.info("[FutuSyncer] 本次同步 %d 个账户: %s",
                 len(targets), "、".join(t["name"] for t in targets))

        payloads: Dict[str, Dict[str, Any]] = {}
        for target in targets:
            account_result, data = self._sync_one_target(target)
            result.accounts.append(account_result)
            if data is not None:
                payloads[target["name"]] = data

        if not payloads:
            # 一个字都不写：页面保留上一次的数据，徽章如实报红
            reason = "全部账户同步失败：" + result.failure_reason()
            log.error("[FutuSyncer] %s", reason)
            get_freshness_tracker().record_failure(SOURCE_FUTU_SYNC, reason)
            return result

        try:
            result.stale_removed = self._write_accounts(targets, payloads, probed_ok)
            result.wrote = True
        except Exception as e:
            log.error("[FutuSyncer] 写入持仓失败: %s", e, exc_info=True)
            get_freshness_tracker().record_failure(SOURCE_FUTU_SYNC, f"写入失败: {e}")
            raise

        if result.ok:
            get_freshness_tracker().record_success(SOURCE_FUTU_SYNC)
        else:
            updated = "、".join(a.name for a in result.accounts if a.ok)
            detail = result.failure_reason()
            get_freshness_tracker().record_failure(
                SOURCE_FUTU_SYNC,
                f"{detail}（{updated} 已更新）" if updated else detail,
            )

        log.info("[FutuSyncer] 同步完成: %s%s", result.summary(),
                 f"；已清理过期账户 {result.stale_removed}" if result.stale_removed else "")
        return result

    # ---------------------------------------------------------- 落盘

    def _build_account_record(
        self, target: Dict[str, Any], data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """把一个账户的取数结果组织成统一持仓表里的记录。"""
        name = target["name"]
        now = time.time()

        positions: Dict[str, Any] = {}
        for pos in data["positions"]:
            code = pos.get("code", "")
            if not code:
                continue
            market = pos.get("market", "US")
            # position_id 带**真实市场**前缀：老实现写死 "US_"，港股持仓
            # 也会被标成 US_xxx，看 id 根本分不出市场
            position_id = f"{market}_{name}_{code}"
            positions[position_id] = {
                "position_id": position_id,
                "account_name": name,
                "stock_code": code,
                "stock_name": pos.get("name", code),
                "entry_price": pos.get("average_cost", 0),
                "current_price": pos.get("nominal_price", 0),
                "quantity": pos.get("qty", 0),
                "entry_time": now,
                "last_update_time": now,
                "status": "OPEN",
                "prev_close": pos.get("prev_close", 0),
                "market": market,
                "currency": pos.get("currency", data.get("currency", "USD")),
            }

        funds = data.get("funds", {}) or {}
        is_sim = (target.get("trd_env") or self.trd_env).upper() == "SIMULATE"
        return {
            "account_type": "futu",
            # 模拟账户不分品牌（``security_firm`` 对它恒为 N/A）→ 留空，
            # 免得页面显示一个它其实并不属于的品牌
            "security_firm": "" if is_sim else target["firm"],
            "trd_env": target.get("trd_env", self.trd_env.upper()),
            "acc_id": target["acc_id"],
            "card_num": target["card_num"],
            "market_auth": target.get("market_auth", []),
            "currency": data.get("currency", ""),
            "equity": funds.get("total_assets", 0),
            "cash": funds.get("cash", 0),
            "market_val": funds.get("market_val", 0),
            "power": funds.get("power", 0),
            "last_sync_time": now,
            "positions": positions,
        }

    def _stale_account_names(
        self, existing: Set[str], current: Set[str], probed_ok: Set[str],
    ) -> Set[str]:
        """算出该清理的旧账户名。

        三条规矩：
        1. **探测失败的品牌一律不清** —— 分不清「账户没了」还是「连不上」，
           宁可留着旧数据，也不能因为一次网络抖动把页面清空。
        2. 只有「品牌探测成功、但它名下的账户已不在本次同步结果里」才清。
        3. ❗**只管本次环境名下的账户** —— 真实与模拟账户共用同一张
           ``accounts`` 表（同一份 ``naja_bandit_positions``）。模拟同步时
           7 个品牌会**全部探测成功**，若沿用「品牌名 → 品牌名下账户」的规则，
           ``FutuHK`` / ``MoomooUS`` 会被判成「已不在本次结果里」而**被清空**
           —— 即**跑一次模拟同步就会抹掉全部实盘持仓**。
           故：模拟环境只允许清 ``FutuSim`` 前缀；真实环境只清品牌前缀。
        """
        stale: Set[str] = set()

        if self._is_simulate():
            for name in existing:
                if name.startswith(SIM_ACCOUNT_PREFIX) and name not in current:
                    stale.add(name)
            return stale - current

        for firm, base in SECURITY_FIRM_ACCOUNT_NAMES.items():
            if firm not in probed_ok:
                continue
            for name in existing:
                if (name == base or name.startswith(base + "_")) and name not in current:
                    stale.add(name)

        if "FUTUSECURITIES" in probed_ok:
            stale |= LEGACY_ACCOUNT_NAMES & existing

        return stale - current

    def _write_accounts(
        self,
        targets: Sequence[Dict[str, Any]],
        payloads: Dict[str, Dict[str, Any]],
        probed_ok: Set[str],
    ) -> List[str]:
        """写统一持仓表 + 清理僵尸账户 + 注册 PortfolioManager。"""
        nb = NB(UNIFIED_POSITIONS_TABLE)
        accounts_data = dict(nb.get("accounts", {}) or {})
        by_name = {t["name"]: t for t in targets}

        for name, data in payloads.items():
            target = by_name[name]
            accounts_data[name] = self._build_account_record(target, data)

        # ❗`current` 必须是**本次目标账户名**（账户确实还在），不是**取数成功**
        # 的账户名（``payloads``）：否则「账户还在、只是这一轮 3 次重试都失败」
        # 会被判成「已消失」而删掉 —— 拿一次网络故障当结论，白清页面数据。
        stale = self._stale_account_names(set(accounts_data), set(by_name), probed_ok)
        for name in stale:
            accounts_data.pop(name, None)

        nb["accounts"] = accounts_data
        nb.persist()

        self._register_with_pm(accounts_data, set(payloads))
        self._save_futu_accounts(targets, payloads, stale)
        return sorted(stale)

    def _register_with_pm(self, accounts_data: Dict[str, Any], current: Set[str]):
        """把同步结果刷进 PortfolioManager 的内存缓存。

        PortfolioManager 的账户名不持久化（每次同步重新注册），所以这里
        只更新本次真正同步成功的账户；消失的账户会随进程重启自然消失。
        """
        try:
            from .portfolio_manager import USStockPosition, get_portfolio_manager

            pm = get_portfolio_manager()
            if not pm:
                return
            for name in current:
                account = pm.register_futu_account(name)
                if not account:
                    continue
                record = accounts_data.get(name, {})
                account._positions = {
                    pid: USStockPosition(**p)
                    for pid, p in (record.get("positions") or {}).items()
                }
                account._equity = record.get("equity", 0)
            log.debug("[FutuSyncer] 已刷新 PortfolioManager 缓存: %s", sorted(current))
        except Exception as e:
            log.debug("[FutuSyncer] 更新缓存跳过: %s", e)

    def _save_futu_accounts(
        self,
        targets: Sequence[Dict[str, Any]],
        payloads: Dict[str, Dict[str, Any]],
        stale: Set[str],
    ):
        """保存富途账户信息（每个账户一份，便于排查）。"""
        by_name = {t["name"]: t for t in targets}
        accounts: Dict[str, Any] = {}
        for name, data in payloads.items():
            target = by_name[name]
            accounts[name] = {
                "security_firm": target["firm"],
                "acc_id": target["acc_id"],
                "card_num": target["card_num"],
                "currency": data.get("currency", ""),
                "funds": data.get("funds", {}),
                "position_count": len(data.get("positions", [])),
                "last_sync_time": time.time(),
            }

        nb = NB(FUTU_ACCOUNTS_TABLE)
        nb["last_sync_time"] = time.time()
        nb["account_names"] = sorted(accounts)
        nb["accounts"] = accounts
        nb["removed_accounts"] = sorted(stale)
        nb.persist()


_singleton: Optional[FutuPortfolioSyncer] = None


def get_futu_syncer() -> FutuPortfolioSyncer:
    """获取 FutuPortfolioSyncer 单例"""
    global _singleton
    if _singleton is None:
        _singleton = FutuPortfolioSyncer()
    return _singleton


if __name__ == "__main__":
    syncer = FutuPortfolioSyncer()

    accounts = syncer.get_accounts()
    print(f"发现 {len(accounts)} 个富途账户:")
    for acc in accounts:
        print(f"  - {acc['security_firm']:16s} {acc['trd_env']:9s} "
              f"acc_id={acc['acc_id']} 账号={acc['card_num'] or '-'} "
              f"市场={acc['market_auth']}")

    targets, probe_errors, _ = syncer.get_sync_targets()
    print(f"\n本次同步目标（{len(targets)} 个）:")
    for t in targets:
        print(f"  - {t['name']:12s} ← {t['firm']} acc_id={t['acc_id']}")
    for err in probe_errors:
        print(f"  ! {err}")

    print("\n同步持仓...")
    result = syncer.sync()
    print(f"结果: {'✅ 全部成功' if result.ok else '❌ 有失败'} —— {result.summary()}")
    if result.stale_removed:
        print(f"已清理过期账户: {result.stale_removed}")

    for t in targets:
        portfolio = syncer.get_portfolio(acc_id=t["acc_id"], firm=t["firm"])
        print(f"\n【{t['name']}】资金 {portfolio['funds']}")
        for pos in portfolio["positions"]:
            print(f"  {pos['code']} {pos['name']}: {pos['qty']}股 @ {pos['average_cost']:.3f}")
