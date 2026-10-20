"""首页状态卡

设计口径与「算力消耗」卡同构 —— 每张卡都必须回答三个问题：

    ① 现在多少        → 主数字（大字）
    ② 关键构成/比例   → 副行（带色的比率，类比算力卡的「环比 +4.5%」）
    ③ 这算好还是坏    → 判读行（结论 + 依据 + 风险色，类比「🟢 正常 · 周频 · 日期」）

============================================================================
分层：首页要回答的是「值不值得看」，不是「有多少模块」
============================================================================

系统里 13 个可数的东西 ≠ 13 个同样重要的东西。按「看到它会不会改变你的
操作」排序，只分三层（见 ``_GROUPS``）：

① 钱与决策 —— 账户盈亏、为什么不动、账户里的数字可不可信、成本。
   **这一层缺任何一张，首页就只是运维面板。**
② 链路在生产吗 —— 有没有在吃数据、任务/数据源是否真的在跑。
③ 反馈与配置 —— 历史胜率、策略与字典配置。

三条硬规则：

1. **主数字必须是状态量，不是总量**。总量（30 个任务）不会变，看不出任何问题；
   运行中 / 近 24h 产出 / 陈旧条目数才会变。
2. **拿不到数据一律写原因**，绝不用 0 冒充。0 是「确实是零」，缺失是「不知道」，
   两者混在一张卡上就等于把故障伪装成健康（本文件此前踩过两次：
   ``bandit.get_stats()`` 不存在、``signals_processed`` 全仓不存在，两张卡长期挂 0）。
3. **两套颜色，不许混用**：
   - 卡片主数字 / 判读行 = **风险色**（红=异常、橙=偏弱、蓝=中性、绿=健康、灰=不可用），
     与 A 股涨红跌绿**相反**，因为这里衡量的是系统健康度。
   - **盈亏数字 = A 股惯例（涨红跌绿）**，因为它衡量的是钱。
   页脚同时给出两个图例，避免「+1.1 万显示成绿色」这种误读。
"""

import re
import time
from collections import Counter

from deva.naja.bandit.virtual_portfolio import normalize_code
from deva.naja.register import SR

# 风险色（与 A 股涨红跌绿相反，因为这里衡量的是系统健康度而非股价）
C_RED = "#ef4444"
C_ORANGE = "#f59e0b"
C_BLUE = "#3b82f6"
C_GREEN = "#22c55e"
C_GRAY = "#94a3b8"

# 盈亏色（A 股惯例：涨红跌绿）—— 只用于钱，不用于健康度
C_UP = C_RED
C_DOWN = C_GREEN

_DAY = 86400.0

# 「为什么不动」的归因解析。gate_reason 形如：
#   主因=地势(风险温度1.30偏高) | 天时0.65 | ... | ✗未通过(终分0.332<门槛0.500)
_MAIN_REASON_RE = re.compile(r"主因=([^|]+)")
_GAP_RE = re.compile(
    r"终分\s*([0-9]+(?:\.[0-9]+)?)\s*<\s*门槛\s*([0-9]+(?:\.[0-9]+)?)"
)


def _ago(ts) -> str:
    """时间戳 → 「X 分钟前」。0/缺失返回「时间未知」，不返回「刚刚」。"""
    try:
        ts = float(ts or 0)
    except (TypeError, ValueError):
        return "时间未知"
    if ts <= 0:
        return "时间未知"
    delta = max(0.0, time.time() - ts)
    if delta < 90:
        return "刚刚"
    if delta < 5400:
        return f"{int(delta // 60)} 分钟前"
    if delta < 172800:
        return f"{int(delta // 3600)} 小时前"
    return f"{int(delta // 86400)} 天前"


def _money(value) -> str:
    """金额 → 1.2 万 / 3.45 亿。取不到返回「—」，不返回 0。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    a = abs(v)
    if a >= 1e8:
        return f"{v / 1e8:.2f} 亿"
    if a >= 1e4:
        return f"{v / 1e4:.1f} 万"
    return f"{v:,.0f}"


def _pnl(value, pct=None) -> str:
    """盈亏文本，按 A 股惯例上色（正=红、负=绿）。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f'<span style="color:{C_GRAY};">—</span>'
    color = C_UP if v > 0 else (C_DOWN if v < 0 else C_GRAY)
    text = f"{v:+,.0f}"
    if pct is not None:
        try:
            text += f"（{float(pct):+.1f}%）"
        except (TypeError, ValueError):
            pass
    return f'<b style="color:{color};">{text}</b>'


def _ratio(current: int, previous: int) -> str:
    """环比文本（带色）。分母为 0 时明说「前期无对比」，不编造百分比。"""
    if previous <= 0:
        return "前期无对比" if current > 0 else "持平"
    pct = (current - previous) / previous * 100
    color = C_GREEN if pct > 20 else (C_RED if pct < -20 else C_BLUE)
    sign = "+" if pct >= 0 else ""
    return f'<b style="color:{color};">{sign}{pct:.0f}%</b>'


def _median(values):
    vals = sorted(float(v) for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def _stat_card(*, icon, title, main, color, sub, judge, judge_color, tip, gradient) -> str:
    """渲染一张四层卡（主数字 / 标题 / 副行 / 判读行）。"""
    sub_html = (
        f'<div style="font-size:11px;color:#94a3b8;margin-top:5px;">{sub}</div>' if sub else ""
    )
    return f"""
        <div title="{tip}" style="background: {gradient}; border-radius: 12px; padding: 18px 14px;
                    text-align: center; transition: transform 0.2s; cursor: default;
                    display: flex; flex-direction: column; justify-content: flex-start;">
            <div style="font-size: 30px; font-weight: 700; color: {color}; line-height: 1.15;
                        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{main}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 6px;">{icon} {title}</div>
            {sub_html}
            <div style="font-size: 10px; color: {judge_color}; margin-top: 4px;
                        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{judge}</div>
        </div>
    """


# ── ① 钱与决策 ───────────────────────────────────────────────────────────────

def _portfolio():
    """取虚拟组合；取不到返回 (None, 原因)。"""
    try:
        return SR("virtual_portfolio"), ""
    except Exception as e:
        return None, f"组合不可用（{type(e).__name__}）"


def _group_positions(positions):
    """按标的（归一代码）聚合持仓记录，返回 ``{code: [pos, ...]}``。

    ❗底仓分批建仓会让**同一只票**在账本里留下几十条独立 OPEN 记录
    （实测 588200 有 38 条，合计 42.95 万股）。直接把 ``len(positions)``
    当「持仓只数」显示，首页就会出现「持仓 40」而实际只有 3 只票，
    「40/40 只超 3 天」也就变成一句吓人但没有信息量的话。
    """
    grouped = {}
    for pos in positions:
        code = str(getattr(pos, "stock_code", "") or "")
        key = normalize_code(code) or code
        grouped.setdefault(key, []).append(pos)
    return grouped


def _account_card() -> dict:
    """💰 账户：总资产 + 持仓 + 浮盈亏 —— 整个首页唯一回答「赚没赚」的地方。"""
    card = dict(
        icon="💰", title="账户（虚拟）",
        gradient="linear-gradient(135deg, #14324a 0%, #0a1c2b 100%)",
        main="—", color=C_GRAY, sub="",
        judge="组合不可用", judge_color=C_GRAY,
        tip="虚拟组合（account_name=虚拟测试）的总资产、未平仓持仓数与浮盈亏。"
            "⚠️ 浮盈亏按持仓里存着的 current_price 计算，价格不更新它就只是历史快照 —— "
            "可不可信看隔壁「持仓风险」卡的陈旧只数。"
            "颜色为 A 股惯例：正红负绿，与卡片判读行的风险色无关。",
    )
    vp, err = _portfolio()
    if vp is None:
        card["judge"] = err
        return card

    try:
        summary = vp.get_summary()
    except Exception as e:
        card["judge"] = f"组合摘要读取失败（{type(e).__name__}）"
        return card

    if not isinstance(summary, dict):
        card["judge"] = f"组合摘要返回异常类型（{type(summary).__name__}）"
        return card

    capital = float(summary.get("total_capital") or 0)
    available = float(summary.get("available_capital") or 0)
    market_value = float(summary.get("total_value") or 0)
    count = int(summary.get("position_count") or 0)
    pnl = float(summary.get("total_profit_loss") or 0)
    ret = summary.get("total_return")

    if capital <= 0:
        card["main"] = "—"
        card["judge"] = "未配置本金 · 无法计算收益率"
        return card

    assets = available + market_value
    total_ret = (assets - capital) / capital * 100

    # 标的数 ≠ 记录数：底仓分 38 批买同一只票，账本里就是 38 条记录。
    # 主行显示标的数，括号里补记录数，避免「持仓 40」被读成 40 只票。
    codes = 0
    try:
        codes = len(_group_positions(vp.get_all_positions(status="OPEN") or []))
    except Exception:
        codes = 0

    card["main"] = _money(assets)
    card["color"] = "#38bdf8"
    card["sub"] = (
        f"持仓 {codes} 只（{count} 笔）· 浮动 {_pnl(pnl, ret)}"
        if codes and codes != count else
        f"持仓 {count} · 浮动 {_pnl(pnl, ret)}"
    )
    card["judge"] = (
        f"累计 {total_ret:+.1f}% · 可用 {_money(available)}"
        if count
        else f"空仓 · 可用 {_money(available)}"
    )
    card["judge_color"] = C_GREEN if total_ret >= 0 else C_ORANGE
    return card


def _position_risk_card() -> dict:
    """📈 持仓风险：价格陈旧只数 + 最差持仓 —— 判断账户里的浮盈亏能不能信。

    这是「假新鲜比异常更毒」那条规则的首页落点：持仓价格 3 天没动，
    账户卡上的浮盈亏就还是 3 天前的快照，但它长得和实时数字一模一样。
    """
    card = dict(
        icon="📈", title="持仓风险",
        gradient="linear-gradient(135deg, #3a2a1a 0%, #241609 100%)",
        main="—", color=C_GRAY, sub="",
        judge="组合不可用", judge_color=C_GRAY,
        tip="主数字 = 价格超过 3 天未更新的持仓只数（不是持仓总数）。"
            "持仓价格停更时，账户卡上的浮盈亏只是历史快照，必须显式标出来。",
    )
    vp, err = _portfolio()
    if vp is None:
        card["judge"] = err
        return card

    try:
        positions = vp.get_all_positions(status="OPEN") or []
    except Exception as e:
        card["judge"] = f"持仓读取失败（{type(e).__name__}）"
        return card

    count = len(positions)
    if count == 0:
        card["main"] = "0"
        card["judge"] = "无未平仓持仓"
        return card

    # ❗陈旧度按**标的**算，不按记录算：588200 有 38 条记录，但它们共用
    # 同一份行情，一条更新就全组更新。按记录数当分母会把「3 只票都停更」
    # 说成「40/40 只超 3 天」，数字越大越像灾难，实际只有 3 件事。
    grouped = _group_positions(positions)
    code_count = len(grouped)
    now = time.time()
    ages = [
        now - max(float(getattr(p, "last_update_time", 0) or 0) for p in group)
        for group in grouped.values()
    ]
    stale3 = sum(1 for a in ages if a > 3 * _DAY)
    stale7 = sum(1 for a in ages if a > 7 * _DAY)
    oldest = max(ages) if ages else 0.0

    try:
        worst = min(positions, key=lambda p: float(p.return_pct))
        worst_text = f"最差 {getattr(worst, 'stock_code', '?')} {float(worst.return_pct):+.1f}%"
    except Exception:
        worst_text = "最差 —"

    card["main"] = str(stale3)
    card["sub"] = f"{code_count} 只标的（{count} 笔）· {worst_text}"

    if stale7:
        card["color"] = C_RED
        # 主数字是 >3 天的只数，判读行必须用同一个分母，否则「3」和「40 只」
        # 并排出现会让人以为是两件不同的事
        card["judge"] = (
            f"⚠ {stale3}/{code_count} 只超 3 天未更新（最旧 {oldest / _DAY:.0f} 天）· 浮盈亏不可信"
        )
        card["judge_color"] = C_RED
    elif stale3:
        card["color"] = C_ORANGE
        card["judge"] = f"{stale3}/{code_count} 只超 3 天未更新（最旧 {oldest / _DAY:.0f} 天）"
        card["judge_color"] = C_ORANGE
    else:
        card["color"] = C_GREEN
        card["judge"] = f"价格均在 3 天内更新 · 最旧 {oldest / 3600:.0f} 小时"
        card["judge_color"] = C_GREEN
    return card


def _decision_card() -> dict:
    """🧠 决策：近 24h 决策数 + 放行数 + **为什么不动**。

    只写「全 hold」等于什么都没说 —— 真正要回答的是「卡在哪、差多少」。
    这两项都能从 ``gate_reason`` 里直接解析出来（Manas 自己写的归因）。
    """
    card = dict(
        icon="🧠", title="决策",
        gradient="linear-gradient(135deg, #1a3a5c 0%, #0d2137 100%)",
        main="—", color=C_GRAY, sub="",
        judge="决策中心不可用", judge_color=C_GRAY,
        tip="近 24 小时决策中心写下的决策留痕条数（DecisionPlan），以及放行数与"
            "「为什么不动」——主因与终分/门槛的差距都从 gate_reason 解析。"
            "长期 hold 是等待时机的代价，不等于故障。",
    )
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        tc = get_trading_center()
    except Exception as e:
        card["judge"] = f"决策中心不可用（{type(e).__name__}）"
        return card

    try:
        # 按时间窗取（而不是「最近 N 条」再自己过滤）：24h 内的真实条数一次性拿到
        window = tc.get_decision_history(hours=24, limit=500) or []
    except Exception as e:
        card["judge"] = f"决策留痕读取失败（{type(e).__name__}）"
        return card

    latest = window[0] if window else None
    if latest is None:
        # 24h 内没有决策时才多查一次，用来判断「等了多久」而不是「没有数据」
        try:
            recent_one = tc.get_recent_decisions(limit=1) or []
            latest = recent_one[0] if recent_one else None
        except Exception:
            latest = None

    approved = sum(1 for r in window if r.get("approved") is True)

    # ── 从 gate_reason 提炼归因 ──
    main_reasons = []
    gaps = []
    risk_temps = []
    for record in window:
        reason = str(record.get("gate_reason") or "")
        if reason:
            m = _MAIN_REASON_RE.search(reason)
            if m:
                main_reasons.append(m.group(1).strip())
            g = _GAP_RE.search(reason)
            if g:
                gaps.append((float(g.group(1)), float(g.group(2))))
        try:
            rt = float(record.get("risk_temperature"))
            if rt > 0:
                risk_temps.append(rt)
        except (TypeError, ValueError):
            pass

    top_reason = Counter(main_reasons).most_common(1)
    top_reason = top_reason[0][0] if top_reason else ""
    # 主因的括号里通常就是数值（如「地势(风险温度1.30偏高)」）——
    # 括号留给判读行放具体数字，副行只留类别，避免同一句话重复两遍
    short_reason = re.sub(r"[（(].*?[）)]", "", top_reason).strip()
    med_score = _median([g[0] for g in gaps])
    med_gate = _median([g[1] for g in gaps])
    med_risk = _median(risk_temps)

    # ── 副行 ──
    sub_parts = [f"放行 {approved}" if approved else "全 hold"]
    if short_reason:
        sub_parts.append(f"主因 {short_reason}")
    card["sub"] = " · ".join(sub_parts)

    if latest is None:
        card["main"] = "0"
        card["judge"] = "从未产生决策 · 等首次信号"
        card["judge_color"] = C_GRAY
        return card

    # 查询本身有上限，满 500 时真实条数只会更多，不能显示成精确值
    card["main"] = f"≥{len(window)}" if len(window) >= 500 else str(len(window))

    if not window:
        idle = time.time() - float(latest.get("recorded_at") or 0)
        if idle > 7 * _DAY:
            card["color"] = C_RED
            card["judge"] = f"⚠ {int(idle // _DAY)} 天无决策 · 可能已断链"
            card["judge_color"] = C_RED
        else:
            card["color"] = C_ORANGE
            card["judge"] = f"等待时机 · 最近 {_ago(latest.get('recorded_at'))}"
            card["judge_color"] = C_ORANGE
        return card

    card["color"] = "#00d4ff"
    if approved:
        card["judge"] = f"有放行 · 最近 {_ago(latest.get('recorded_at'))}"
        card["judge_color"] = C_GREEN
    elif med_score is not None and med_gate is not None:
        # 差距就是「还差多少才动手」——比一句 hold 有用得多
        # 风险温度是反向指标：≥1.30 说明环境本身在报警，不只是策略不自信
        if med_risk is not None and med_risk >= 1.30:
            card["judge"] = (
                f"风险温度 {med_risk:.2f} 偏高 · 终分 {med_score:.2f}<门槛 {med_gate:.2f}"
            )
            card["judge_color"] = C_ORANGE
        else:
            card["judge"] = (
                f"终分 {med_score:.2f} < 门槛 {med_gate:.2f}（差 {med_gate - med_score:.2f}）"
            )
            card["judge_color"] = C_BLUE
    else:
        card["judge"] = f"全 hold · 最近 {_ago(latest.get('recorded_at'))}"
        card["judge_color"] = C_BLUE
    return card


def _compute_card() -> dict:
    """🔥 算力消耗：口径全部来自 get_compute_headline()，与认知页共用，不在这里重算。"""
    compute = {
        "state": "unavailable",
        "value": "—",
        "label": "算力消耗",
        "change": "",
        "change_color": C_GRAY,
        "color": C_GRAY,
        "alert": ("未采集", C_GRAY),
        "sub": "监控任务尚无数据",
    }
    try:
        from deva.naja.cognition.ui.components.token_monitor import get_compute_headline
        compute = get_compute_headline()
    except Exception as e:
        compute["alert"] = (f"取数失败（{type(e).__name__}）", C_GRAY)

    sub = compute["label"]
    if compute["change"]:
        sub += (
            ' · 环比 <b style="color:'
            + compute["change_color"]
            + ';">'
            + compute["change"]
            + "</b>"
        )

    alert_text, alert_color = compute["alert"]
    return dict(
        icon="🔥", title="算力消耗",
        gradient="linear-gradient(135deg, #3a2a0a 0%, #2a1a05 100%)",
        main=compute["value"], color=compute["color"], sub=sub,
        judge=f"{alert_text} · {compute['sub']}", judge_color=alert_color,
        tip="算力消耗（OpenRouter 用量）。风险色衡量的是用量/需求强弱，与股价涨红跌绿相反："
            "环比上升=绿、下降=红。数据停止更新时整卡转灰并标注停更天数。",
    )


# ── ② 链路在生产吗 ───────────────────────────────────────────────────────────

def _datasource_card(ds: dict) -> dict:
    """📡 数据源：运行中 / 总数 —— 口径来自 FleetRegistry（全系统），不再只数注册体系。

    ❗改口径的原因：原来只读 ``DatasourceManager.get_stats()``，那是**注册体系**
    里的 5 个 yaml 数据源。但系统里还有十几个取数点（新浪行情总线、美股价格、
    富途同步、FRED、SEC/东财、IMA、文章监控…）压根不在体系内，首页永远看不到。
    现在统一从 FleetRegistry 读，注册体系 + 探针 + 声明式登记一视同仁。
    """
    card = dict(
        icon="📡", title="数据源",
        gradient="linear-gradient(135deg, #1a3a3a 0%, #0d2727 100%)",
        main="—", color=C_GRAY, sub="",
        judge="", judge_color=C_GRAY,
        tip="全系统**所有**对外取数点：数据源体系内注册的条目 + 散落各处的取数器"
            "（由探针自动上报）。主数字=运行中；副行=总数与近 24h 真有数据回来的条数。"
            "❗「未观测到调用」= 已登记但还没见它取过数（日频 cron 或未用到），"
            "这是「不知道」，不是「坏了」，所以显示成中性蓝而不是红色。",
    )
    total = int(ds.get("total") or 0)
    running = int(ds.get("running") or 0)
    active = int(ds.get("active") or 0)
    unknown = int(ds.get("unknown") or 0)
    stale = ds.get("stale") or []
    recent_err = ds.get("error_recent") or []
    hist_err = ds.get("error_historical") or []
    last_err_ts = float(ds.get("last_error_ts") or 0)
    last_ok_ts = float(ds.get("last_success_ts") or 0)

    card["main"] = str(running)
    card["sub"] = f"共 {total} 个 · 近 24h 有数据 {active}" if total else "无数据源"

    if total == 0:
        card["color"] = C_GRAY
        card["judge"] = "尚未登记任何取数点"
        card["judge_color"] = C_GRAY
    elif running == 0:
        card["color"] = C_RED
        card["judge"] = f"⚠ 全部未运行（{total} 个）· 检查是否被停止"
        card["judge_color"] = C_RED
    elif recent_err:
        # error_count 是累计值：199 天前炸过一次也会一直挂着。只有**近期**失败
        # 才算当前问题，否则会让人对着早已自愈的条目做无用排查。
        card["color"] = C_RED
        names = "、".join(c.name for c in recent_err[:2])
        more = f" 等 {len(recent_err)} 个" if len(recent_err) > 2 else ""
        card["judge"] = f"⚠ {names}{more} 报错 · {_ago(last_err_ts)}"
        card["judge_color"] = C_RED
    elif stale:
        card["color"] = C_ORANGE
        oldest = min((c.last_success_ts for c in stale), default=0)
        card["judge"] = f"{len(stale)} 个停更 · 最旧 {_ago(oldest)}"
        card["judge_color"] = C_ORANGE
    elif hist_err:
        card["color"] = C_BLUE
        card["judge"] = f"{len(hist_err)} 个有历史错误 · 最近 {_ago(last_err_ts)}"
        card["judge_color"] = C_BLUE
    elif unknown:
        card["color"] = C_BLUE
        card["judge"] = f"{unknown} 个未观测到调用 · 见下方清单"
        card["judge_color"] = C_BLUE
    else:
        card["color"] = "#00d4ff"
        card["judge"] = f"最近取数 {_ago(last_ok_ts)}"
        card["judge_color"] = C_GREEN
    return card


def _task_card(task_stats: dict) -> dict:
    """⏰ 任务：运行中 / 总数 + 有失败记录的条目数。"""
    card = dict(
        icon="⏰", title="任务",
        gradient="linear-gradient(135deg, #3a1a3a 0%, #2a0d2a 100%)",
        main="—", color=C_GRAY, sub="",
        judge="", judge_color=C_GRAY,
        tip="运行中的任务数量与总数。判读看的是「有几个任务带了失败记录」"
            "（failed_tasks），而不是累计失败次数 —— 一个任务炸 50 次和 50 个任务各炸一次，"
            "在累计次数上完全相同。",
    )
    total = int(task_stats.get("total") or 0)
    running = int(task_stats.get("running") or 0)
    failed = int(task_stats.get("failed_tasks") or 0)
    fails = int(task_stats.get("total_failure") or 0)
    last_fail_ts = float(task_stats.get("last_failure_ts") or 0)

    card["main"] = str(running)
    card["sub"] = f"共 {total} 个 · 累计失败 {fails} 次" if total else "无任务"

    # 同数据源：failure_count 是累计值，只有近期失败才算「当前有任务在报错」
    recent_fail = last_fail_ts > 0 and (time.time() - last_fail_ts) < 2 * _DAY
    if total == 0:
        card["color"] = C_GRAY
        card["judge"] = "尚未创建任务"
        card["judge_color"] = C_GRAY
    elif running == 0:
        card["color"] = C_RED
        card["judge"] = f"⚠ 全部未运行（{total} 个）"
        card["judge_color"] = C_RED
    elif failed > 0 and recent_fail:
        card["color"] = C_ORANGE
        card["judge"] = f"{failed} 个任务有失败 · {_ago(last_fail_ts)}"
        card["judge_color"] = C_ORANGE
    elif failed > 0:
        card["color"] = C_BLUE
        card["judge"] = f"{failed} 个有历史失败 · 最近 {_ago(last_fail_ts)}"
        card["judge_color"] = C_BLUE
    else:
        card["color"] = "#f093fb"
        card["judge"] = f"无失败记录 · 最近执行 {_ago(task_stats.get('last_run_ts'))}"
        card["judge_color"] = C_GREEN
    return card


def _radar_card() -> dict:
    """📡 雷达：近 24h 事件数 —— 全量按时间过滤，不是「最近 100 条」的截断长度。"""
    card = dict(
        icon="🛰", title="雷达事件",
        gradient="linear-gradient(135deg, #2a2a3a 0%, #171724 100%)",
        main="—", color=C_GRAY, sub="",
        judge="雷达引擎不可用", judge_color=C_GRAY,
        tip="近 24 小时雷达事件数与较前 24 小时的环比。口径是全库按时间窗过滤"
            "（radar.summarize），不是「取最近 100 条再数长度」—— 后者最多只能显示 100，"
            "爆表时分不清是刚好 100 还是早就超出。",
    )
    try:
        from deva.naja.radar import get_radar_engine
        radar = get_radar_engine()
    except Exception as e:
        card["judge"] = f"雷达引擎不可用（{type(e).__name__}）"
        return card

    try:
        cur = radar.summarize(window_seconds=86400)
        wide = radar.summarize(window_seconds=172800)
    except Exception as e:
        card["judge"] = f"事件统计失败（{type(e).__name__}）"
        return card

    n = int(cur.get("event_count") or 0)
    # 48h 窗口减去 24h 窗口 = 前一个 24h
    n_prev = max(int(wide.get("event_count") or 0) - n, 0)
    types = cur.get("event_type_counts") or {}
    events = cur.get("events") or []
    last_ts = max((float(e.get("timestamp") or 0) for e in events), default=0.0)

    card["main"] = str(n)
    sub_parts = [f"较前 24h {_ratio(n, n_prev)}"]
    if types:
        top_name, top_n = max(types.items(), key=lambda kv: kv[1])
        sub_parts.append(f"{top_name} {top_n}")
    card["sub"] = " · ".join(sub_parts)

    if n > 0:
        card["color"] = "#f59e0b"
        card["judge"] = f"最近事件 {_ago(last_ts)}"
        card["judge_color"] = C_GREEN if (time.time() - last_ts) < 21600 else C_ORANGE
    elif last_ts > 0:
        card["color"] = C_ORANGE
        card["judge"] = f"近 24h 无事件 · 最近 {_ago(last_ts)}"
        card["judge_color"] = C_ORANGE
    else:
        card["color"] = C_GRAY
        card["judge"] = "从未产生事件 · 检查雷达是否在扫描"
        card["judge_color"] = C_GRAY
    return card


def _cognition_card() -> dict:
    """🧩 认知：累计摄入事件 + 高注意力/活跃主题 —— 认知层有没有在吃东西。"""
    card = dict(
        icon="🧩", title="认知",
        gradient="linear-gradient(135deg, #2a1a3a 0%, #1a0d2a 100%)",
        main="—", color=C_GRAY, sub="",
        judge="认知系统不可用", judge_color=C_GRAY,
        tip="认知系统累计摄入的事件数、其中高注意力事件数、活跃主题数。"
            "原口径读 cognition_stats['signals_processed']，但这个键在全仓不存在；"
            "取数用的 get_cognition_system() 也不存在 —— 两处都抛异常被吞掉，"
            "所以这张卡长期显示 0。",
    )
    try:
        # 真身是 CognitionEngine（注册名 cognition_engine），它内部持有 NewsMindStrategy
        cog = SR("cognition_engine")
        stats = cog.get_stats()
    except Exception as e:
        card["judge"] = f"认知系统不可用（{type(e).__name__}）"
        return card

    if not isinstance(stats, dict):
        # 拿到的不是 dict 说明接口契约变了；直接崩会把整页卡片一起带走
        card["judge"] = f"认知统计返回异常类型（{type(stats).__name__}）"
        return card

    total = int(stats.get("total_events") or 0)
    high = int(stats.get("high_attention_events") or 0)
    topics = int(stats.get("active_topics") or 0)
    last_ts = stats.get("last_event_ts")

    card["main"] = str(total)
    card["sub"] = (
        f"高注意力 <b style=\"color:{C_BLUE};\">{high}</b> · 主题 {topics}"
    )

    if total == 0:
        card["color"] = C_GRAY
        card["judge"] = "尚未摄入事件 · 等数据源喂入"
        card["judge_color"] = C_GRAY
    else:
        card["color"] = "#8b5cf6"
        card["judge"] = f"最近摄入 {_ago(last_ts)}"
        stale = last_ts is None or (time.time() - float(last_ts)) > 2 * _DAY
        card["judge_color"] = C_ORANGE if stale else C_GREEN
    return card


# ── ③ 反馈与配置 ─────────────────────────────────────────────────────────────

def _bandit_card() -> dict:
    """🎰 Bandit：平仓笔数 + 胜率 —— 反馈闭环有没有真的转起来。"""
    card = dict(
        icon="🎰", title="Bandit",
        gradient="linear-gradient(135deg, #3a1a2a 0%, #2a0d1a 100%)",
        main="—", color=C_GRAY, sub="",
        judge="Bandit 追踪器不可用", judge_color=C_GRAY,
        tip="最近 200 笔平仓记录（BanditPositionTracker）的笔数与胜率。"
            "原口径调用 bandit.get_stats()，但 BanditAutoRunner 上并没有这个方法，"
            "被 hasattr 挡掉后这张卡长期恒为 0。",
    )
    try:
        tracker = SR("bandit_tracker")
    except Exception as e:
        card["judge"] = f"Bandit 追踪器不可用（{type(e).__name__}）"
        return card

    try:
        records = tracker.get_position_history(limit=200) or []
    except Exception as e:
        card["judge"] = f"平仓记录读取失败（{type(e).__name__}）"
        return card

    n = len(records)
    if n == 0:
        card["main"] = "0"
        card["color"] = C_GRAY
        card["sub"] = "胜率 —"
        card["judge"] = "尚无平仓记录 · 反馈闭环未形成"
        card["judge_color"] = C_GRAY
        return card

    wins = sum(1 for r in records if float(r.get("return_pct") or 0) > 0)
    win_rate = wins / n * 100
    last_ts = max((float(r.get("timestamp") or 0) for r in records), default=0.0)

    card["main"] = f"≥{n}" if n >= 200 else str(n)
    rate_color = C_GREEN if win_rate >= 55 else (C_BLUE if win_rate >= 40 else C_ORANGE)
    card["color"] = rate_color
    card["sub"] = (
        f"胜率 <b style=\"color:{rate_color};\">{win_rate:.0f}%</b>"
        f"（{wins}/{n}{'+' if n >= 200 else ''}）"
    )
    card["judge"] = f"最近平仓 {_ago(last_ts)}"
    card["judge_color"] = C_GREEN if (time.time() - last_ts) < 3 * _DAY else C_ORANGE
    return card


def _strategy_card(st: dict) -> dict:
    """📊 策略：运行中 / 总数 —— 口径来自 FleetRegistry（yaml 策略 + 热点策略 + 常驻 runner）。

    ❗改口径的原因：原来只读 ``StrategyManager.get_stats()``，那是 17 个 yaml 声明式
    策略。但热点策略体系那十几个**正在跑并向 TradingCenter 送信号**的策略，因为汇入
    代码里一个不存在的 import 名字 + ``except: pass``，从没进过 StrategyManager
    ——首页完全看不到它们。现在三套清单一起数。
    """
    card = dict(
        icon="📊", title="策略",
        gradient="linear-gradient(135deg, #1a3a4a 0%, #0d2a3a 100%)",
        main="—", color=C_GRAY, sub="",
        judge="", judge_color=C_GRAY,
        tip="全系统**所有**在跑的决策单元：yaml 声明式策略 + 热点策略体系 + 常驻"
            "运行器（Bandit / 做T / 守望台 / 复盘 / 持仓监控 / 雷达 / 认知编排）。"
            "产出为 0 说明在跑但没有信号。副行括号里给出各来源构成。",
    )
    total = int(st.get("total") or 0)
    running = int(st.get("running") or 0)
    output = int(st.get("output_total") or 0)
    unknown = int(st.get("unknown") or 0)
    by_source = st.get("by_source") or {}

    # 来源构成：让人一眼看出「这 N 个是哪几套清单凑出来的」
    label = {"strategy_mgr": "声明式", "hotspot": "热点", "runner": "常驻"}
    compose = " · ".join(
        f"{label.get(k, k)} {v}" for k, v in sorted(by_source.items(), key=lambda kv: -kv[1])
    )

    card["main"] = str(running)
    card["sub"] = (f"共 {total} 个（{compose}）· 产出 {output}" if compose
                   else (f"共 {total} 个 · 产出 {output}" if total else "无策略"))
    if total == 0:
        card["color"] = C_GRAY
        card["judge"] = "尚未登记策略"
        card["judge_color"] = C_GRAY
    elif running == 0:
        card["color"] = C_RED
        card["judge"] = f"⚠ 全部未运行（{total} 个）"
        card["judge_color"] = C_RED
    elif running < total:
        card["color"] = C_BLUE
        card["judge"] = f"{total - running} 个未运行" + (f"（{unknown} 个状态未知）" if unknown else "")
        card["judge_color"] = C_BLUE
    else:
        card["color"] = "#4facfe"
        card["judge"] = "全部运行中"
        card["judge_color"] = C_GREEN
    return card


def _dictionary_card(dict_stats: dict) -> dict:
    """📚 字典：总数 + 加载成功/失败。"""
    card = dict(
        icon="📚", title="字典",
        gradient="linear-gradient(135deg, #1a3a1a 0%, #0d2a0d 100%)",
        main="—", color=C_GRAY, sub="",
        judge="", judge_color=C_GRAY,
        tip="字典总数，以及按最近一次加载状态统计的成功/失败条目数。",
    )
    total = int(dict_stats.get("total") or 0)
    success = int(dict_stats.get("success") or 0)
    errors = int(dict_stats.get("error") or 0)

    card["main"] = str(total)
    card["sub"] = f"加载成功 {success} · 失败 {errors}" if total else "无字典"
    if errors > 0:
        card["color"] = C_ORANGE
        card["judge"] = f"{errors} 个字典加载失败"
        card["judge_color"] = C_ORANGE
    elif total == 0:
        card["color"] = C_GRAY
        card["judge"] = "尚未配置字典"
        card["judge_color"] = C_GRAY
    else:
        card["color"] = "#43e97b"
        card["judge"] = "加载正常"
        card["judge_color"] = C_GREEN
    return card


def _wisdom_card() -> dict:
    """📚 智慧陪伴：触发次数 + 最近聚焦。"""
    card = dict(
        icon="📖", title="智慧陪伴",
        gradient="linear-gradient(135deg, #2a2a2a 0%, #171717 100%)",
        main="—", color=C_GRAY, sub="",
        judge="智慧检索器不可用", judge_color=C_GRAY,
        tip="智慧检索器累计触发次数与最近一次聚焦的主题。从未触发是「静默」，不等于故障。",
    )
    try:
        # 真身是 WisdomRetriever（注册名 wisdom_retriever），方法叫 get_stats()
        retriever = SR("wisdom_retriever")
        w_stats = retriever.get_stats()
    except Exception as e:
        card["judge"] = f"智慧检索器不可用（{type(e).__name__}）"
        return card

    if not isinstance(w_stats, dict):
        card["judge"] = f"智慧统计返回异常类型（{type(w_stats).__name__}）"
        return card

    count = int(w_stats.get("trigger_count") or 0)
    focus = w_stats.get("last_focus") or ""
    card["main"] = str(count)
    card["sub"] = focus if focus else "最近聚焦 —"
    if count > 0:
        card["color"] = "#a855f7"
        card["judge"] = "已触发"
        card["judge_color"] = C_GREEN
    else:
        card["color"] = C_GRAY
        card["judge"] = "静默中 · 尚未触发"
        card["judge_color"] = C_GRAY
    return card


# ── 渲染 ─────────────────────────────────────────────────────────────────────

#: 首页分层。顺序即优先级：看不到第一层就等于没看首页。
_GROUPS = (
    ("① 钱与决策", "账户赚没赚 · 为什么不动 · 账户里的数字可不可信 · 成本"),
    ("② 链路在生产吗", "有没有在吃数据 · 数据源与任务是否真的在跑"),
    ("③ 反馈与配置", "历史胜率 · 策略与字典配置"),
)


def _group_html(title: str, desc: str, cards) -> str:
    body = "".join(_stat_card(**c) for c in cards)
    # ❗分层标题写在**页面底色**上，不是卡片底色上。首页是白底
    #   （body 实测 rgb(255,255,255)），所以这里必须用深色字；
    #   曾经写成 #e2e8f0 这种近白色，在截图里几乎看不见。
    return f"""
    <div style="display:flex;align-items:center;gap:8px;margin:18px 0 3px 2px;">
        <div style="width:3px;height:15px;border-radius:2px;background:#0ea5e9;"></div>
        <div style="font-size:15px;color:#1e293b;font-weight:700;letter-spacing:0.5px;">{title}</div>
    </div>
    <div style="font-size:11px;color:#64748b;margin:0 0 8px 13px;">{desc}</div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 0 0 14px 0;">
        {body}
    </div>
    """


def render_stats_cards(ctx: dict, ds_stats: dict, task_stats: dict,
                       strategy_stats: dict, dict_stats: dict):
    """渲染首页状态卡（三层，每层 4 张四层结构卡）。"""
    groups = (
        (
            _account_card(),
            _decision_card(),
            _position_risk_card(),
            _compute_card(),
        ),
        (
            _datasource_card(ds_stats or {}),
            _task_card(task_stats or {}),
            _radar_card(),
            _cognition_card(),
        ),
        (
            _bandit_card(),
            _strategy_card(strategy_stats or {}),
            _dictionary_card(dict_stats or {}),
            _wisdom_card(),
        ),
    )

    blocks = "".join(
        _group_html(title, desc, cards)
        for (title, desc), cards in zip(_GROUPS, groups)
    )

    ctx["put_html"](f"""
    {blocks}
    <div style="font-size:11px;color:#64748b;margin:4px 0 20px 2px;line-height:1.7;">
        判读色（系统健康度，与 A 股相反）：<span style="color:{C_GREEN};">● 健康</span>
        <span style="color:{C_BLUE};">● 中性</span>
        <span style="color:{C_ORANGE};">● 偏弱 / 待观察</span>
        <span style="color:{C_RED};">● 异常</span>
        <span style="color:{C_GRAY};">● 不可用（附原因）</span>
        <br/>
        盈亏数字（钱，按 A 股惯例）：<span style="color:{C_UP};">● 盈利</span>
        <span style="color:{C_DOWN};">● 亏损</span>
        —— 两套颜色故意不统一：一个是「系统有没有病」，一个是「钱多了还是少了」。
    </div>
    """)
