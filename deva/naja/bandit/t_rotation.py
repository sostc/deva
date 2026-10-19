"""TRotationEngine——A 股「做 T 降成本」引擎

别名/关键词: 做T、T+0、降成本、核心底仓、回购义务、t rotation

要解决的事
----------
用户的需求原话：

    「如果持仓里面有的话，咱们就把持仓里面的做 T 去降低成本嘛。
      我们其实还要长期持有一个半导体指数……不过中间可以做 T，
      但要利用这种流动性的机会，做完之后一定要买回来，保证我们长期持有。」

拆成三条要交付的东西：

1. **持仓里的票做 T 降成本** → :meth:`TRotationEngine.on_tick` 驱动的两种打法
2. **长期持有OPEN半导体/芯片指数ETF作为底仓** → :meth:`register_target`，
   目标份额以内**永不卖出**（这是"随时能做 T 的权利"，不是用来炒的筹码）
3. **做完必须买回** → 份额守恒铁律（见下）

★ 份额守恒铁律
--------------
任何一次做 T 结束时，该标的的**约定持有份额**（真实持仓 + 未履行回购义务）
不得低于做 T 开始时的水平。这是本模块唯一的、不可协商的约束。

实现方式是把 "effective_shares = 真实持仓 + 未履行回购义务" 作为唯一口径：

    | 阶段           | 真实持仓 | 回购义务 | effective | 是否守恒 |
    |----------------|----------|----------|-----------|----------|
    | 起始           | 10000    | 0        | 10000     | —        |
    | 倒T 卖出 2000  |  8000    | 2000     | 10000     | ✓        |
    | 倒T 买回 2000  | 10000    | 0        | 10000     | ✓        |
    | 正T 买入 2000  | 12000    | 0        | 12000     | ✓        |
    | 正T 卖出 2000  | 10000    | 0        | 10000     | ✓        |

每个 round 结束时都会真刀真枪地校验一次，不符即记 error 并暴露给调用方。

这里用 `realized_edge` 而不是「盈亏」这个词：做 T 的收益本质上是
**冲抵底仓持有成本**，不是新赚了一笔钱。抬高成本的情况必须能显现为负数。

为什么两种打法都依赖底仓
------------------------
这是用户的洞察，也是 A 股 T+1 的直接后果：

* **正 T（先买后卖）**：低点买 N 份 → 卖出**更早持有**的 N 份。
  当日买入的当日不可卖，所以必须手里先有"昨天的票"。
* **倒 T（先卖后买）**：高点卖 N 份底仓 → 低点买回。
  卖的就是底仓。

**两种都要求持仓不为 0**。空仓时连做的资格都没有，遇到今天这种
6% 振幅的日子只能干看着 —— 这就是必须长期持有底仓的理由。

刻意不做的事
------------
* **不接方向/传导预测**。判据只用日内偏离度（见 intraday_deviation）。
  前一轮查证已经证明方向预测可以全错而做 T 照样赚钱。
* **不做空**。A 股不可做空个股/ETF（融资融券标的有限且成本高），
  而且做空与"长期持有α"的目标相悖。
* **不自动实盘下单**。全程走虚拟仓。
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .core_position import (
    CorePositionLedger,
    CorePlan,
    get_core_position_ledger,
)
from .intraday_deviation import (
    ACTION_BUY_T,
    ACTION_NONE,
    ACTION_SELL_T,
    DeviationSnapshot,
    IntradayDeviationTracker,
    RotationSignal,
    RotationThresholds,
    evaluate_deviation,
)

log = logging.getLogger(__name__)

#: 正 T：先低价买，再高价卖昨天的票
KIND_FORWARD = "正T"
#: 倒 T：先高价卖底仓，再低价买回
KIND_REVERSE = "倒T"

ROUND_OPEN = "OPEN"
ROUND_CLOSED = "CLOSED"
#: 到期/收盘前被强制了结（价格未必有利，但份额必须先回来）
ROUND_FORCED = "FORCED"
#: 正 T 未能了结，买入份额转为加仓（不违背策略，但需告警）
ROUND_CARRIED = "CARRIED"

T_ROTATION_TABLE = "naja_t_rotation_rounds"

#: 逆风日「跌了是机会」的分批系数：第 1/2/3 次低吸依次递减，用完即止。
#: 不设这一层，趋势下跌里会一路接飞刀把子弹打光。
DIP_BATCH_SCALES = (0.5, 0.3, 0.2)


@dataclass
class TRotationConfig:
    """引擎级参数。"""

    strategy_id: str = "t_rotation"
    strategy_name: str = "做T降本"

    #: 单次最多动用可用轮换份额的比例。留有余地，别一次打光
    max_round_pct: float = 0.30
    #: 单次最大金额（元），防止一次动太多。
    #: 与 max_round_pct 是"与"的关系，两者取小；算 set 到要比最大单品种底仓的
    #: 30% 还小才有意义（默认 20 万 ≈ 百万账户单次不超过 20%）。
    max_round_amount: float = 200000.0
    #: 正 T 需要备用资金；保留可用资金的比例不动用
    cash_reserve_pct: float = 0.20
    #: 份额整手粒度（ETF 100 份起）
    round_lot: float = 100.0
    #: 单次最少份额，低于此不值得做（摩擦成本占比过高）
    min_round_shares: float = 100.0

    enable_forward_t: bool = True
    enable_reverse_t: bool = True

    #: 了结用「跟踪回撤」而非固定目标：
    #: 开仓严格（要偏离够大、还要等右侧确认），了结则从最高点回撤这么多百分比才走。
    #: 这样单边拉升时能一直持有，把 6% 的空间真正吃到，而不是 0.5% 就落袋。
    close_drawdown_pct: float = 0.3
    #: 倒 T 镜像：价格从卖出后的最低点反弹这么多百分比才买回（确认跌不动了）。
    #: 道理同上——不要在单边下坠中途急着接。
    buyback_rebound_pct: float = 0.3
    #: 收盘前 N 分钟，未了结的倒 T 一律强制买回
    force_close_minutes: float = 10.0


@dataclass
class SymbolContext:
    """单个标的的会话上下文。"""

    stock_code: str
    name: str = ""
    prev_close: float = 0.0
    session_open_ts: float = 0.0
    round_lot: float = 100.0
    bar_seq: int = 0
    last_action_bar: int = -9999


@dataclass
class RotationRound:
    """一轮做 T 的完整记录。

    一轮 = 两腿。只有两腿都落地才算 CLOSED，否则带着 obligation 悬在那里，
    ``settle_before_close`` 会来收拾。
    """

    round_id: str
    stock_code: str
    kind: str
    planned_qty: float
    first_price: float
    first_time: float
    first_position_id: str = ""
    obligation_id: str = ""
    second_price: float = 0.0
    second_time: float = 0.0
    status: str = ROUND_OPEN
    realized_edge: float = 0.0
    forced: bool = False
    note: str = ""
    #: 做 T 开启前的约定持有份额，用于收工时校验守恒
    effective_before: float = 0.0
    #: 持有期间的极值：正 T 记最高（判断回撤），倒 T 记最低（判断反弹）
    peak_price: float = 0.0
    trough_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.status == ROUND_OPEN

    @property
    def edge_pct(self) -> float:
        """差价百分比。正=降成本，负=抬高成本。"""
        if not self.realized_edge or self.planned_qty <= 0 or self.first_price <= 0:
            return 0.0
        return self.realized_edge / (self.first_price * self.planned_qty) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_id": self.round_id,
            "stock_code": self.stock_code,
            "kind": self.kind,
            "planned_qty": self.planned_qty,
            "first_price": self.first_price,
            "first_time": self.first_time,
            "first_position_id": self.first_position_id,
            "obligation_id": self.obligation_id,
            "second_price": self.second_price,
            "second_time": self.second_time,
            "status": self.status,
            "realized_edge": self.realized_edge,
            "edge_pct": self.edge_pct,
            "forced": self.forced,
            "note": self.note,
            "effective_before": self.effective_before,
            "peak_price": self.peak_price,
            "trough_price": self.trough_price,
            "open": self.is_open,
        }


class TRotationEngine:
    """A 股做 T 引擎。

    被外部行情驱动：每个分时点喂一次 :meth:`on_tick`，它决定要不要动、
    以及要不要收拾上一次留下的摊子。

    全流程走虚拟仓，不会触发任何真实下单。
    """

    def __init__(
        self,
        portfolio,
        ledger: Optional[CorePositionLedger] = None,
        thresholds: Optional[RotationThresholds] = None,
        config: Optional[TRotationConfig] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        self._portfolio = portfolio
        self._ledger = ledger if ledger is not None else CorePositionLedger(
            persist=False
        )
        self._thresholds = thresholds or RotationThresholds()
        self._config = config or TRotationConfig()
        self._now = clock or time.time

        self._ctx: Dict[str, SymbolContext] = {}
        self._trackers: Dict[str, IntradayDeviationTracker] = {}
        self._rounds: Dict[str, RotationRound] = {}
        self._lock = threading.RLock()

        #: 逐标的的参数档（市场不同，尺度也不同 —— 见 core_holdings.MarketProfile）
        self._thr_by_code: Dict[str, RotationThresholds] = {}
        self._cfg_by_code: Dict[str, TRotationConfig] = {}
        self._lot_by_code: Dict[str, float] = {}

        self._on_round_event: List[Callable[[str, RotationRound], None]] = []

        errs = self._thresholds.validate()
        if errs:
            # 参数错要当场炸，不要等到实盘才发现一直在给券商打工
            raise ValueError(f"RotationThresholds 参数非法: {'; '.join(errs)}")

    # ------------------------------------------------------------------
    # 逐标的参数档
    # ------------------------------------------------------------------
    def set_symbol_profile(
        self,
        code: str,
        *,
        thresholds: Optional[RotationThresholds] = None,
        config: Optional[TRotationConfig] = None,
        round_lot: Optional[float] = None,
    ):
        """给单个标的挂上它自己那套参数。

        为什么必须有这个
        ----------------
        判据是按「日内波动尺度」标出来的，而三个市场的尺度差一个数量级
        （实测当日振幅：A 股 588200 6.02% ｜ 港股 00700 1.36% ｜ 美股 QQQ 0.72%）。
        全引擎共用一套参数的话，QQQ 连"死水"闸门（``min_amplitude``）都过不去
        —— **永不触发**，且不报错不告警，看上去就是"今天没机会"。

        每手股数同理：美股 1 股起，按 A 股 100 股一手去买 QQQ，
        一手就是七万多美元，`max_round_amount` 再怎么用人民币衡量都是错的。
        """
        if thresholds is not None:
            errs = thresholds.validate()
            if errs:
                raise ValueError(f"{code} 的 RotationThresholds 参数非法: {'; '.join(errs)}")
            self._thr_by_code[code] = thresholds
        if config is not None:
            self._cfg_by_code[code] = config
        if round_lot is not None and round_lot > 0:
            self._lot_by_code[code] = float(round_lot)
            ctx = self._ctx.get(code)
            if ctx is not None:
                ctx.round_lot = float(round_lot)

    def _thresholds_for(self, code: str) -> RotationThresholds:
        return self._thr_by_code.get(code, self._thresholds)

    def _set_leg_tag(self, tag: Optional[str]) -> None:
        """把本轮做 T 的轮次号注入组合（幂等槽位的标签）。

        为什么需要
        ----------
        富途模拟仓的幂等槽位默认是「日期+市场+标的+方向」—— 一个标的
        一天只能各买一次卖一次。做 T 一天要跑好几轮，**第二轮起会被
        静默挡掉**（跳过日志只有一行 info，看起来就是"今天没机会"）。
        传 round_id 后：同一轮重复提交仍被挡（防重放），不同轮各自成槽。

        虚拟盘没有这个概念 → 用 hasattr 探测，缺失即忽略。
        """
        setter = getattr(self._portfolio, "set_slot_tag", None)
        if not callable(setter):
            return
        try:
            setter(tag)
        except Exception as e:  # pragma: no cover
            log.warning("[TRotation] 注入轮次标签失败（幂等可能误拦）: %s", e)

    def _config_for(self, code: str) -> TRotationConfig:
        return self._cfg_by_code.get(code, self._config)

    def config_for(self, code: str) -> TRotationConfig:
        """公开访问器：运行器要读 ``force_close_minutes`` 判断何时收盘结算。"""
        return self._config_for(code)

    # ------------------------------------------------------------------
    # 登记与上下文
    # ------------------------------------------------------------------
    def register_target(
        self, stock_code: str, target_shares: float, name: str = "", note: str = ""
    ) -> CorePlan:
        """登记长期持有目标份额（核心底仓）。

        target 以内的份额不参与任何卖出。这是"随时能做 T 的权利"。
        """
        self._ensure_symbol(stock_code, name=name)
        return self._ledger.set_plan(stock_code, target_shares, name, note)

    def _ensure_symbol(self, stock_code: str, name: str = "") -> SymbolContext:
        ctx = self._ctx.get(stock_code)
        if ctx is None:
            ctx = SymbolContext(
                stock_code=stock_code,
                name=name,
                round_lot=self._lot_by_code.get(stock_code, self._config.round_lot),
            )
            self._ctx[stock_code] = ctx
            self._trackers[stock_code] = IntradayDeviationTracker(stock_code)
        elif name and not ctx.name:
            ctx.name = name
        return ctx

    def set_prev_close(self, stock_code: str, prev_close: float, name: str = ""):
        """昨收必须显式给 —— 所有百分比的基准，缺了整个判据失效。"""
        ctx = self._ensure_symbol(stock_code, name=name)
        ctx.prev_close = float(prev_close)
        self._trackers[stock_code].set_prev_close(float(prev_close))

    def start_session(
        self, stock_code: str, prev_close: float, name: str = "",
        session_open_ts: Optional[float] = None,
    ):
        """每个交易日开盘时调用一次，重置日内序列。"""
        ctx = self._ensure_symbol(stock_code, name=name)
        self._trackers[stock_code].reset_session(prev_close=prev_close)
        ctx.prev_close = float(prev_close)
        ctx.session_open_ts = (
            session_open_ts if session_open_ts else self._now()
        )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def on_tick(
        self,
        stock_code: str,
        price: float,
        timestamp: Optional[float] = None,
        volume: float = 0.0,
        minutes_to_close: Optional[float] = None,
        session_open_ts: Optional[float] = None,
        env: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """每个分时点调用。

        Args:
            stock_code: 标的代码
            price: 最新价
            timestamp: 时间戳
            volume: 成交量（用于 VWAP，可选）
            minutes_to_close: 距收盘分钟数。**务必提供**，
                它决定能否新开倒 T、以及是否触发强制买回。
                给 None 时倒 T 与强保逻辑都会退化，这是刻意的保守行为。
            env: 环境门。粗字段 ``allow_open`` 表示「整体宜不宜加仓」，
                但正 T / 倒 T 的风险方向相反，实际准入由
                ``allow_forward`` / ``allow_reverse`` 分别决定
                （缺省时回落到 ``allow_open``）；缩放用
                ``forward_size_scale`` / ``reverse_size_scale``。
                逆风日正 T 还会检查 ``require_dip`` 许可：
                ``dip_ok``（不弱于同批中位数）、``dip_ratio``（跌幅需达阈值的倍数）、
                ``dip_batch_scales``（分批递减，用完即止）。
                只影响**新开轮次**的准入与仓位，不影响了结/买回 ——
                拦住开仓可以，拦住平仓会把人锁死在里面。

        Returns:
            诊断字典，永远包含 signal / action / reason，便于排查为什么没动。
        """
        now = timestamp if timestamp is not None else self._now()
        ctx = self._ensure_symbol(stock_code)
        if ctx.prev_close <= 0:
            return {
                "stock_code": stock_code,
                "action": ACTION_NONE,
                "reason": "未设置昨收，百分比基准缺失",
                "signal": None,
            }

        session_open = session_open_ts or ctx.session_open_ts or None
        tracker = self._trackers[stock_code]
        snapshot = tracker.update(price, timestamp=now, volume=volume)
        ctx.bar_seq += 1

        diag: Dict[str, Any] = {
            "stock_code": stock_code,
            "snapshot": snapshot.to_dict(),
            "action": ACTION_NONE,
            "reason": "",
            "round": None,
        }

        # ① 先收拾未了结的旧摊子 —— 了结永远优先于开新仓
        open_round = self._open_round(stock_code)
        if open_round is not None:
            done, why = self._try_close_round(
                open_round, snapshot, minutes_to_close, now, session_open
            )
            diag["round"] = open_round.to_dict()
            if done:
                diag["action"] = "CLOSE_" + ("BUY" if open_round.kind == KIND_REVERSE else "SELL")
                diag["reason"] = why
                return diag
            diag["reason"] = f"持有未完成轮次: {why}"
            # 已有未了结轮次时不再开新的，一次只做一轮，避免叠仓失控
            return diag

        # ② 评估是否开新一轮
        bars_since = ctx.bar_seq - ctx.last_action_bar
        signal = evaluate_deviation(
            snapshot,
            self._thresholds_for(stock_code),
            now=now,
            minutes_to_close=minutes_to_close,
            bars_since_last_action=bars_since,
        )
        diag["signal"] = signal.to_dict()

        if not signal.actionable:
            diag["reason"] = signal.reason
            return diag

        ok, reason, round_obj = self._open_round_for(
            signal, snapshot, now, session_open, minutes_to_close, env=env
        )
        diag["reason"] = reason
        if ok and round_obj is not None:
            diag["action"] = signal.action
            diag["round"] = round_obj.to_dict()
            ctx.last_action_bar = ctx.bar_seq
        return diag

    # ------------------------------------------------------------------
    # 开仓
    # ------------------------------------------------------------------
    @staticmethod
    def _env_gate(
        env: Optional[Dict[str, Any]], action: Optional[str] = None
    ) -> Tuple[bool, str, float]:
        """解析环境门：返回 (是否允许开仓, 原因, 仓位缩放)。

        ``allow_open`` 是「整体宜不宜加仓」的粗结论，但正 T 与倒 T 的风险方向
        恰好相反：下跌日里倒 T 是顺风的（先卖后买，跌了更容易买回），
        正 T 才是「接下跌的刀」。一刀切会把这天最好用的工具一起收起来。

        因此按动作分别解析：优先读 ``allow_forward`` / ``allow_reverse``，
        缺失时回落到 ``allow_open``（兼容只给粗结论的老调用方）。
        """
        if not env:
            return True, "", 1.0
        if action == ACTION_BUY_T:
            allowed = env.get("allow_forward", env.get("allow_open", True))
            scale_key = "forward_size_scale"
        elif action == ACTION_SELL_T:
            allowed = env.get("allow_reverse", env.get("allow_open", True))
            scale_key = "reverse_size_scale"
        else:
            allowed = env.get("allow_open", True)
            scale_key = "size_scale"
        if allowed is False:
            return False, str(env.get("reason") or "环境门拦截新开仓"), 0.0
        raw = env.get(scale_key, env.get("size_scale", 1.0))
        try:
            scale = float(raw)
        except (TypeError, ValueError):
            scale = 1.0
        return True, "", max(0.1, min(1.0, scale))

    def _forward_rounds_today(self, code: str, now: float) -> int:
        """该标的今天已经开了几轮正 T（用于逆势抄底的分批递减）。"""
        today = time.localtime(now)[:3]
        n = 0
        for rnd in self._rounds.values():
            if rnd.stock_code != code or rnd.kind != KIND_FORWARD:
                continue
            try:
                if time.localtime(rnd.first_time)[:3] == today:
                    n += 1
            except (OSError, OverflowError, ValueError):
                continue
        return n

    def _forward_gate(
        self,
        signal: RotationSignal,
        env: Optional[Dict[str, Any]],
        now: float,
    ) -> Tuple[bool, str, float]:
        """正 T 的准入：环境门 + 逆势抄底许可（dip license）。

        逆风日不是「一律不许买」，而是把「好公司跌了是机会」翻译成可判定条件：
        核心持仓（本引擎只跑核心持仓，天然满足）+ 不弱于同批中位数
        + 跌够深 + 分批递减。四条缺一不可，缺的那条就是接飞刀的入口。
        """
        allowed, why, scale = self._env_gate(env, ACTION_BUY_T)
        if not allowed:
            return False, why, 0.0
        if not env or not env.get("require_dip"):
            return True, "", scale

        if env.get("dip_ok") is False:
            return False, str(env.get("dip_reason") or "个股弱于同批中位数，不抄底"), 0.0

        thr = self._thresholds_for(signal.stock_code)
        try:
            ratio = float(env.get("dip_ratio", 1.5) or 1.5)
        except (TypeError, ValueError):
            ratio = 1.5
        need = thr.buy_dev_close * ratio
        if signal.ret > -need:
            return False, (
                f"逆风日正 T 需跌幅 ≥{need:.1f}%（当前 {signal.ret:+.2f}%），浅跌不接"
            ), 0.0

        batches = env.get("dip_batch_scales") or list(DIP_BATCH_SCALES)
        n = self._forward_rounds_today(signal.stock_code, now)
        if n >= len(batches):
            return False, f"今日逆势低吸批次已用完（{n}/{len(batches)}）", 0.0
        return True, "", scale * float(batches[n])

    def _open_round_for(
        self,
        signal: RotationSignal,
        snapshot: DeviationSnapshot,
        now: float,
        session_open: Optional[float],
        minutes_to_close: Optional[float],
        env: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Optional[RotationRound]]:
        code = signal.stock_code
        ctx = self._ctx[code]
        cfg = self._config_for(code)

        if signal.action == ACTION_BUY_T:
            if not cfg.enable_forward_t:
                return False, "正 T 已停用", None
            ok, why, scale = self._forward_gate(signal, env, now)
            if not ok:
                return False, why, None
            opened, reason, rnd = self._open_forward_t(
                signal, snapshot, now, session_open, size_scale=scale
            )
            if opened and rnd is not None and env and env.get("require_dip"):
                # 留痕：复盘时能把「逆势低吸」单独拎出来算胜率
                rnd.note = f"{rnd.note} ·dip_buy"
            return opened, reason, rnd

        if signal.action == ACTION_SELL_T:
            if not cfg.enable_reverse_t:
                return False, "倒 T 已停用", None
            allowed, why, scale = self._env_gate(env, ACTION_SELL_T)
            if not allowed:
                return False, why, None
            return self._open_reverse_t(
                signal, snapshot, now, session_open, minutes_to_close, size_scale=scale
            )

        return False, f"未知动作 {signal.action}", None

    def _lot_size(self, code: str, raw_qty: float) -> float:
        ctx = self._ctx[code]
        lot = max(1.0, ctx.round_lot)
        return math.floor(raw_qty / lot) * lot

    # ---- 正 T：先买后卖 ----
    def _open_forward_t(
        self,
        signal: RotationSignal,
        snapshot: DeviationSnapshot,
        now: float,
        session_open: Optional[float],
        size_scale: float = 1.0,
    ) -> Tuple[bool, str, Optional[RotationRound]]:
        code = signal.stock_code
        ctx = self._ctx[code]
        cfg = self._config_for(code)

        # 正 T 需要底仓：买入后要靠卖出「更早持有」的等量份额来了结，
        # 当日买入当日不可卖 → 必须手里先有昨天的票。
        sellable = self._ledger.sellable_today_shares(
            code, self._portfolio, now=now, session_open_ts=session_open
        )
        if sellable <= 0:
            return False, (
                f"{code} 无昨夜传承的可卖份额（持仓为 0 或当日新买入），"
                f"正 T 无法了结，不开仓"
            ), None

        summary = self._portfolio.get_summary()
        usable_cash = max(
            0.0, summary.get("available_capital", 0.0)
        ) * (1 - cfg.cash_reserve_pct)
        if usable_cash <= 0:
            return False, f"可用资金不足（已扣 {cfg.cash_reserve_pct:.0%} 备用金）", None

        cap_by_cash = usable_cash / snapshot.last if snapshot.last > 0 else 0
        # ❗max_round_amount 的单位是**该市场的本币**（用户拍板各市场独立本币
        # 记账），价格也是本币 —— 两边同源才除得动。
        cap_by_amount = cfg.max_round_amount / snapshot.last if snapshot.last > 0 else 0
        cap_by_pos = sellable * cfg.max_round_pct

        raw_qty = min(cap_by_cash, cap_by_amount, cap_by_pos) * size_scale
        qty = self._lot_size(code, raw_qty)
        if qty < max(ctx.round_lot, cfg.min_round_shares):
            return False, (
                f"可买份额 {qty:.0f} < 最小 {cfg.min_round_shares:.0f} 份"
                f"（资金上限 {cap_by_cash:.0f} / 持仓上限 {cap_by_pos:.0f}"
                f" / 环境缩放 {size_scale:.2f}）"
            ), None

        before = self._ledger.effective_shares(
            code, self._portfolio, now=now, session_open_ts=session_open
        )
        # ❗轮次号必须在下单**之前**定下来：这一腿本身就是本轮的第一笔，
        # 等开完仓再生成 round_id，这一腿就没有幂等标签了。
        rid = f"tr_{uuid.uuid4().hex[:10]}"
        self._set_leg_tag(rid)
        pos = self._portfolio.open_position(
            strategy_id=cfg.strategy_id,
            strategy_name=cfg.strategy_name,
            stock_code=code,
            stock_name=ctx.name or code,
            price=snapshot.last,
            quantity=qty,
            # ⚠️ 必须把止损止盈推到不可达：update_price 会在触发时自动平仓，
            # 半路被强平的做 T 腿会让整个轮次闭环失败。
            stop_loss_pct=-95.0,
            take_profit_pct=995.0,
            signal_confidence=signal.confidence,
        )
        if pos is None:
            return False, f"虚拟开仓失败（可能撞仓位限额）", None

        rnd = RotationRound(
            round_id=rid,
            stock_code=code,
            kind=KIND_FORWARD,
            planned_qty=qty,
            first_price=snapshot.last,
            first_time=now,
            first_position_id=pos.position_id,
            effective_before=before,
            note=f"低吸 dev={snapshot.dev_vwap:.2f}%",
        )
        with self._lock:
            self._rounds[rnd.round_id] = rnd
        log.info(
            f"[TRotation] 🟢 正T 低吸 {ctx.name or code}({code}) "
            f"{qty:.0f} 份 @{snapshot.last:.3f}（VWAP {snapshot.vwap:.3f}，"
            f"偏离 {snapshot.dev_vwap:+.2f}%）"
        )
        return True, rnd.note, rnd

    # ---- 倒 T：先卖后买 ----
    def _open_reverse_t(
        self,
        signal: RotationSignal,
        snapshot: DeviationSnapshot,
        now: float,
        session_open: Optional[float],
        minutes_to_close: Optional[float],
        size_scale: float = 1.0,
    ) -> Tuple[bool, str, Optional[RotationRound]]:
        code = signal.stock_code
        ctx = self._ctx[code]
        cfg = self._config_for(code)

        quota = self._ledger.session_quota(
            code, self._portfolio, now=now, session_open_ts=session_open
        )
        if quota <= 0:
            plan = self._ledger.get_plan(code)
            target = plan.target_shares if plan else 0.0
            carried = self._ledger.carried_in_shares(
                code, self._portfolio, now=now, session_open_ts=session_open
            )
            return False, (
                f"{code} 今日无倒T额度：开盘持有 {carried:.0f} 份，"
                f"需长期持有 {target:.0f} 份"
            ), None

        cap_by_amount = cfg.max_round_amount / snapshot.last if snapshot.last > 0 else 0
        raw_qty = min(quota * cfg.max_round_pct, cap_by_amount) * size_scale
        qty = self._lot_size(code, raw_qty)
        if qty < max(ctx.round_lot, cfg.min_round_shares):
            return False, (
                f"可做T份额 {qty:.0f} < 最小 {cfg.min_round_shares:.0f} 份"
                f"（今日额度 {quota:.0f}，单次上限 {cfg.max_round_pct:.0%}"
                f"，环境缩放 {size_scale:.2f}）"
            ), None

        allowed, why = self._ledger.can_sell(
            code, qty, self._portfolio, now=now, session_open_ts=session_open
        )
        if not allowed:
            return False, why, None

        # 轮次号先定下来：卖腿是本轮第一笔，晚了就没幂等标签（见 _set_leg_tag）
        rid = f"tr_{uuid.uuid4().hex[:10]}"
        self._set_leg_tag(rid)
        sold = self._reduce_symbol(code, qty, snapshot.last, now, session_open)
        if sold <= 0:
            return False, f"实际减仓失败（可卖份额不足）", None

        deadline = None
        if minutes_to_close is not None:
            deadline = now + max(
                1.0, minutes_to_close - cfg.force_close_minutes
            ) * 60.0

        before = self._ledger.effective_shares(
            code, self._portfolio, now=now, session_open_ts=session_open
        )
        ob = self._ledger.open_obligation(
            code, sold, snapshot.last, deadline=deadline, now=now,
            session_open_ts=session_open, note=f"倒T高抛 dev={snapshot.dev_vwap:.2f}%",
        )

        rnd = RotationRound(
            round_id=rid,
            stock_code=code,
            kind=KIND_REVERSE,
            planned_qty=sold,
            first_price=snapshot.last,
            first_time=now,
            obligation_id=ob.obligation_id,
            effective_before=before,
            note=f"高抛 dev={snapshot.dev_vwap:+.2f}%",
        )
        with self._lock:
            self._rounds[rnd.round_id] = rnd
        log.info(
            f"[TRotation] 🔴 倒T 高抛 {ctx.name or code}({code}) "
            f"{sold:.0f} 份 @{snapshot.last:.3f}（VWAP {snapshot.vwap:.3f}，"
            f"偏离 {snapshot.dev_vwap:+.2f}%）→ 必须买回"
        )
        return True, rnd.note, rnd

    # ------------------------------------------------------------------
    # 了结
    # ------------------------------------------------------------------
    def _open_round(self, stock_code: str) -> Optional[RotationRound]:
        for r in self._rounds.values():
            if r.stock_code == stock_code and r.is_open:
                return r
        return None

    def _try_close_round(
        self,
        rnd: RotationRound,
        snapshot: DeviationSnapshot,
        minutes_to_close: Optional[float],
        now: float,
        session_open: Optional[float],
    ) -> Tuple[bool, str]:
        """尝试了结一轮。

        开仓严格（偏离够大 + 右侧确认），**了结用跟踪回撤**：
        一直涨就一直拿，只有从最高点回撤够了才走。
        这样单边拉升时能把 6% 的空间吃到，而不是刚翻红就落袋。
        """
        cfg = self._config_for(rnd.stock_code)
        price = snapshot.last

        if rnd.kind == KIND_FORWARD:
            rnd.peak_price = max(rnd.peak_price or price, price)
            dd = (
                (rnd.peak_price - price) / rnd.peak_price * 100
                if rnd.peak_price > 0
                else 0.0
            )
            gain = (
                (price - rnd.first_price) / rnd.first_price * 100
                if rnd.first_price > 0
                else 0.0
            )
            if dd >= cfg.close_drawdown_pct and gain > 0:
                self._close_forward_t(rnd, snapshot, now, session_open, False)
                return True, (
                    f"自最高 {rnd.peak_price:.2f} 回撤 {dd:.2f}%"
                    f"(≥{cfg.close_drawdown_pct}%)，正T了结，浮盈兑现"
                )
            if minutes_to_close is not None and minutes_to_close <= cfg.force_close_minutes:
                ok, why = self._close_forward_t(
                    rnd, snapshot, now, session_open, True
                )
                return ok, why if ok else f"收盘未能了结: {why}"
            return False, (
                f"正T持有中（相对买点 {gain:+.2f}%，峰值回撤 {dd:.2f}%）"
            )

        # 倒 T：回购义务优先
        ob = None
        for cand in self._ledger.outstanding(rnd.stock_code):
            if cand.obligation_id == rnd.obligation_id:
                ob = cand
                break
        if ob is None:
            # 义务已不在（被外部结清），把轮次收掉，别悬着
            rnd.status = ROUND_CLOSED
            rnd.second_time = now
            rnd.note = "回购义务已不在账本（外部结清）"
            return True, rnd.note

        # 倒 T 用镜像逻辑：等价格从最低点反弹够了，确认跌不动才买回
        rnd.trough_price = min(rnd.trough_price, price) if rnd.trough_price > 0 else price
        reb = (
            (price - rnd.trough_price) / rnd.trough_price * 100
            if rnd.trough_price > 0
            else 0.0
        )
        # 回购义务优先：deadline / 收盘不等 any longer
        if ob.is_overdue(now):
            return self._close_reverse_t(rnd, ob, snapshot, now, True)
        if minutes_to_close is not None and minutes_to_close <= cfg.force_close_minutes:
            return self._close_reverse_t(rnd, ob, snapshot, now, True)

        if reb >= cfg.buyback_rebound_pct:
            self._close_reverse_t(rnd, ob, snapshot, now, False)
            return True, (
                f"自最低 {rnd.trough_price:.2f} 反弹 {reb:.2f}%"
                f"(≥{cfg.buyback_rebound_pct}%)，确认跌不动，倒T买回"
            )

        remain = ob.deadline - now
        return False, (
            f"倒T等待回落买回（当前 {((snapshot.last - ob.sell_price) / ob.sell_price * 100):+.2f}%，"
            f"自低点反弹 {reb:.2f}%，距 deadline {remain / 60:.0f} 分钟）"
        )

    def _close_forward_t(
        self, rnd, snapshot, now, session_open, forced: bool
    ) -> Tuple[bool, str]:
        """正 T 了结：卖出「更早持有」的等量份额（当日买入的不可卖）。"""
        code = rnd.stock_code
        qty = min(rnd.planned_qty, self._ledger.sellable_today_shares(
            code, self._portfolio, now=now, session_open_ts=session_open
        ))
        if qty <= 0:
            return False, "暂无昨日可卖份额，正T无法在今天了结"
        self._set_leg_tag(rnd.round_id)
        sold = self._reduce_symbol(code, qty, snapshot.last, now, session_open)
        if sold <= 0:
            return False, "减仓失败"

        buy_cost = rnd.first_price * sold
        sell_gain = snapshot.last * sold
        rnd.second_price = snapshot.last
        rnd.second_time = now
        rnd.realized_edge = sell_gain - buy_cost
        rnd.status = ROUND_CLOSED if sold >= rnd.planned_qty - 1e-9 else ROUND_CARRIED
        ctx = self._ctx.get(code)
        log.info(
            f"[TRotation] ✅ 正T 了结 {getattr(ctx, 'name', code) or code}({code}) "
            f"{sold:.0f} 份 @{snapshot.last:.3f}，"
            f"兑现差价 {rnd.realized_edge:+.2f}（{(snapshot.last - rnd.first_price) / rnd.first_price * 100:+.2f}%）"
        )
        self._verify_conservation(rnd, now, session_open)
        return True, f"正T了结，兑现 {rnd.realized_edge:+.2f}"

    def _close_reverse_t(
        self, rnd, ob, snapshot, now, forced: bool
    ) -> Tuple[bool, str]:
        """倒 T 买回。这是「保证长期持有」的兑现点 —— 再贵也要买回来。"""
        code = rnd.stock_code
        ctx = self._ctx.get(code)
        cfg = self._config_for(code)
        qty = ob.quantity

        self._set_leg_tag(rnd.round_id)
        pos = self._portfolio.open_position(
            strategy_id=cfg.strategy_id,
            strategy_name=cfg.strategy_name,
            stock_code=code,
            stock_name=(ctx.name if ctx else code) or code,
            price=snapshot.last,
            quantity=qty,
            stop_loss_pct=-95.0,
            take_profit_pct=995.0,
            # 回购义务是必须完成的，不能被仓位限额挡回来
            bypass_limits=True,
        )
        if pos is None:
            log.error(
                f"[TRotation] 🚨🚨 买回失败！{code} {qty:.0f} 份仍悬空，"
                f"必须人工介入确保份额回归"
            )
            return False, "买回失败（连同 bypass 都没建成），需人工介入"

        self._ledger.fulfill_obligation(ob.obligation_id, snapshot.last, now=now)
        rnd.second_price = snapshot.last
        rnd.second_time = now
        rnd.realized_edge = (rnd.first_price - snapshot.last) * qty
        rnd.status = ROUND_FORCED if forced else ROUND_CLOSED
        rnd.forced = forced

        tag = "🚨 强制" if forced else "✅"
        log.info(
            f"[TRotation] {tag} 倒T 买回 {getattr(ctx, 'name', code) or code}({code}) "
            f"{qty:.0f} 份 @{snapshot.last:.3f}（卖出 @{rnd.first_price:.3f}），"
            f"兑现差价 {rnd.realized_edge:+.2f}"
        )
        self._verify_conservation(rnd, now, None)
        return True, f"倒T买回，兑现 {rnd.realized_edge:+.2f}"

    # ------------------------------------------------------------------
    # 减仓执行：按数量比例分摊，维持加权平均成本
    # ------------------------------------------------------------------
    def _reduce_symbol(
        self, stock_code: str, qty: float, exit_price: float,
        now: float, session_open: Optional[float],
    ) -> float:
        """从「昨夜传承下来」的持仓里按数量比例减仓。

        比例分摊保证剩余份额的加权平均成本不变 —— 与 A 股卖出采用
        **加权平均成本法**（不指定批次）的实际行为一致。
        """
        session_open = self._ledger.resolve_session_open(now, session_open)
        candidates = [
            p
            for p in self._portfolio.get_all_positions(status="OPEN")
            if getattr(p, "stock_code", None) == stock_code
            and float(getattr(p, "entry_time", 0.0) or 0.0) < session_open
        ]
        avail = sum(float(p.quantity) for p in candidates)
        if avail <= 0 or qty <= 0:
            return 0.0

        take_total = min(qty, avail)
        sold = 0.0
        for p in candidates:
            share = (float(p.quantity) / avail) if avail > 0 else 0.0
            take = take_total * share
            if take <= 0:
                continue
            self._portfolio.reduce_position(
                p.position_id, take, exit_price, reason="T_ROTATION"
            )
            sold += take
        return sold

    # ------------------------------------------------------------------
    # ★ 份额守恒校验
    # ------------------------------------------------------------------
    def _verify_conservation(
        self, rnd: RotationRound, now: float, session_open: Optional[float]
    ) -> bool:
        """校验一轮做 T 结束后份额没有流失。

        这是全局唯一的铁律。违反时必须**响亮地**暴露出来，而不是悄悄记账。
        """
        after = self._ledger.effective_shares(
            rnd.stock_code, self._portfolio, now=now, session_open_ts=session_open
        )
        before = rnd.effective_before
        # 正 T 未完全了结时允许多出来的部分（转为加仓），但绝不允许少
        tolerance = max(1.0, abs(before) * 1e-6)
        if after < before - tolerance:
            log.error(
                f"[TRotation] 🚨🚨 份额守恒被破坏！{rnd.stock_code} "
                f"轮次 {rnd.round_id}（{rnd.kind}）：开始前 {before:.2f} → "
                f"现在 {after:.2f}，缺口 {before - after:.2f} 份。"
                f"必须补回，否则长期持有承诺失效。"
            )
            return False
        if after > before + tolerance and rnd.kind == KIND_REVERSE:
            log.warning(
                f"[TRotation] ⚠️ 倒T 结束后份额反而多了 "
                f"({before:.2f} → {after:.2f})，请核对是否重复买回"
            )
        return True

    # ------------------------------------------------------------------
    # 收盘结算
    # ------------------------------------------------------------------
    def settle_before_close(
        self,
        stock_code: str,
        price: float,
        now: Optional[float] = None,
        session_open_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """收盘前结算：**所有未买回的份额一律买回**。

        这是「保证我们长期持有」的最后一道兜底。哪怕价格不利也要买——
        份额流失违背了整个策略的前提。

        Returns:
            结算报告
        """
        now = self._now() if now is None else now
        ctx = self._ctx.get(stock_code)
        report: Dict[str, Any] = {
            "stock_code": stock_code,
            "forced_buyback": 0,
            "carried_forward": 0,
            "messages": [],
        }

        snapshot = None
        tracker = self._trackers.get(stock_code)
        if tracker is not None:
            snapshot = tracker.update(price, timestamp=now)

        cfg = self._config_for(stock_code)
        for ob in list(self._ledger.outstanding(stock_code)):
            rnd = self._round_for_obligation(ob.obligation_id)
            self._set_leg_tag(rnd.round_id if rnd else None)
            pos = self._portfolio.open_position(
                strategy_id=cfg.strategy_id,
                strategy_name=cfg.strategy_name,
                stock_code=stock_code,
                stock_name=(ctx.name if ctx else stock_code) or stock_code,
                price=price,
                quantity=ob.quantity,
                stop_loss_pct=-95.0,
                take_profit_pct=995.0,
                bypass_limits=True,
            )
            if pos is None:
                report["messages"].append(
                    f"🚨 {stock_code} 强制买回失败，"
                    f"{ob.quantity:.0f} 份仍悬空！"
                )
                log.error(
                    f"[TRotation] 🚨🚨 收盘强制买回失败: {stock_code} "
                    f"{ob.quantity:.0f} 份"
                )
                continue

            self._ledger.mark_forced(ob.obligation_id, price, now)
            report["forced_buyback"] += ob.quantity
            edge = (ob.sell_price - price) * ob.quantity
            report["messages"].append(
                f"🚨 强制买回 {ob.quantity:.0f} 份 @{price:.3f}"
                f"（卖出 @{ob.sell_price:.3f}，差价 {edge:+.2f}）"
            )
            if rnd is not None:
                rnd.second_price = price
                rnd.second_time = now
                rnd.status = ROUND_FORCED
                rnd.forced = True
                rnd.realized_edge = edge
                self._verify_conservation(rnd, now, session_open_ts)

        # 正 T 只买未卖的：不追杀亏损平仓，把买入份额转为加仓
        # （标的本来就是长期持有，加仓不违背策略；但必须显式告知）
        for rnd in list(self._rounds.values()):
            if (
                rnd.stock_code == stock_code
                and rnd.is_open
                and rnd.kind == KIND_FORWARD
            ):
                unrealized = (price - rnd.first_price) * rnd.planned_qty
                rnd.status = ROUND_CARRIED
                rnd.second_time = now
                rnd.note = (
                    f"收盘未了结，{rnd.planned_qty:.0f} 份转为加仓"
                    f"（浮盈 {unrealized:+.2f}）"
                )
                report["carried_forward"] += rnd.planned_qty
                report["messages"].append(f"ℹ️ {rnd.note}")
                log.warning(f"[TRotation] ⚠️ {stock_code} {rnd.note}")

        return report

    def _round_for_obligation(self, obligation_id: str) -> Optional[RotationRound]:
        for r in self._rounds.values():
            if r.obligation_id == obligation_id:
                return r
        return None

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def list_rounds(self, stock_code: Optional[str] = None) -> List[RotationRound]:
        rs = self._rounds.values()
        if stock_code:
            rs = [r for r in rs if r.stock_code == stock_code]
        return sorted(rs, key=lambda r: r.first_time, reverse=True)

    def realized_edge_total(self, stock_code: Optional[str] = None) -> float:
        """累计兑现差价（金额）。正 = 确实降低了持仓成本。"""
        return sum(
            r.realized_edge
            for r in self._rounds.values()
            if r.status in (ROUND_CLOSED, ROUND_FORCED)
            and (stock_code is None or r.stock_code == stock_code)
        )

    def get_status(self, stock_code: Optional[str] = None) -> Dict[str, Any]:
        codes = [stock_code] if stock_code else list(self._ctx.keys())
        items = []
        for code in codes:
            ctx = self._ctx.get(code)
            tracker = self._trackers.get(code)
            rnd = self._open_round(code)
            summary = self._ledger.get_summary(
                code,
                self._portfolio,
                now=self._now(),
                session_open_ts=ctx.session_open_ts if ctx else None,
            )
            summary.update(
                {
                    "name": ctx.name if ctx else "",
                    "samples": tracker.bar_count if tracker else 0,
                    "open_round": rnd.to_dict() if rnd else None,
                    "realized_edge": self.realized_edge_total(code),
                    "rounds_total": sum(
                        1 for r in self._rounds.values() if r.stock_code == code
                    ),
                }
            )
            items.append(summary)
        return {
            "symbols": items,
            "totals": {
                "rounds": len(self._rounds),
                "open_rounds": sum(1 for r in self._rounds.values() if r.is_open),
                "realized_edge": self.realized_edge_total(),
            },
            "ledger": self._ledger.get_stats(),
            "thresholds": {
                "round_trip_cost_pct": self._thresholds.round_trip_cost_pct(),
                "buy_dev_vwap": self._thresholds.buy_dev_vwap,
                "sell_dev_vwap": self._thresholds.sell_dev_vwap,
                "min_amplitude": self._thresholds.min_amplitude,
                "min_net_edge": self._thresholds.min_net_edge,
            },
        }
