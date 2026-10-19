"""
Token Monitor 组件 - TOKEN 消耗监控板块

展示 OpenRouter TOKEN 消耗、周期环比、异常告警级别、AI 算力趋势方向。

❗口径随数据粒度切换，不许写死：源是周频时显示「周消耗 / 上一周 / 周环比」，
源是日频时显示「单日 / 7 日合计 / 同星期环比」。写死哪一边都会把数字解释错。

两条硬规则（本文件曾经全踩过）：
1. 枚举必须全覆盖。分析层产出 6 个方向值、4 个告警级别，
   映射表少一个就会静默落成"未知"（曾经 direction=down 也显示 ❓未知）。
2. 空/陈旧必须写明原因。数据停止更新 160 天还显示"正常"，
   比报错危险得多。这里用灰阶 + 徽标把它顶到最显眼处。
"""

# 风险色（与 A 股涨红跌绿相反，因为这里衡量的是"算力需求强弱"而非股价）
# 红 = 不利 / 需求下滑；橙 = 偏弱；蓝 = 中性；绿 = 健康 / 需求上升；灰 = 不可用
C_RED = "#ef4444"
C_ORANGE = "#f59e0b"
C_BLUE = "#3b82f6"
C_GREEN = "#22c55e"
C_GRAY = "#94a3b8"

# 分析层 DIRECTION_VALUES 的 6 个值，一个都不能少
DIRECTION_STYLE = {
    "strong_up": ("🚀 强劲上升", C_GREEN),
    "up": ("📈 温和上升", C_GREEN),
    "flat": ("➡️ 横盘", C_BLUE),
    "down": ("📉 下降", C_ORANGE),
    "strong_down": ("⚠️ 快速下滑", C_RED),
    "unknown": ("❓ 数据不足", C_GRAY),
}

# AlertLevel 的 4 个值，一个都不能少
ALERT_STYLE = {
    "normal": ("🟢 正常", C_GREEN),
    "attention": ("🟡 关注", C_ORANGE),
    "warning": ("🟠 警告", "#f97316"),
    "critical": ("🔴 严重", C_RED),
}

# get_ai_compute_trend 的 4 个值（含 unknown，不许伪装成 stable）
TREND_DIR_STYLE = {
    "rising": ("📈 上升", C_GREEN),
    "stable": ("➡️ 平稳", C_BLUE),
    "falling": ("📉 下降", C_ORANGE),
    "unknown": ("❓ 数据不足", C_GRAY),
}

_CONFIDENCE_LABEL = {
    "high": "高置信",
    "medium": "中置信",
    "low": "低置信",
    "none": "无置信",
}


def _badge(text, color):
    return (
        f'<span style="font-size:11px;color:{color};background:{color}1f;'
        f'border:1px solid {color}55;padding:1px 6px;border-radius:3px;margin-left:4px;">'
        f"{text}</span>"
    )


def _cell(value, label, value_color, sub="", sub_color="#7b8aa0"):
    sub_html = (
        f'<div style="font-size:11px;color:{sub_color};margin-top:2px;">{sub}</div>' if sub else ""
    )
    return f"""
        <div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.14);
                    padding:8px 6px;border-radius:8px;text-align:center;min-width:0;">
            <div style="font-size:15px;color:{value_color};font-weight:700;white-space:nowrap;
                        overflow:hidden;text-overflow:ellipsis;">{value}</div>
            <div style="font-size:11px;color:#94a3b8;margin-top:1px;">{label}</div>
            {sub_html}
        </div>
    """


def _fmt_change(value):
    """环比数值：缺失时明确写 N/A，不拿 0 冒充"""
    if value is None:
        return "N/A", C_GRAY
    if value > 0:
        return f"{value:+.1f}%", C_GREEN
    if value < 0:
        return f"{value:+.1f}%", C_RED
    return "0.0%", C_BLUE


def render_token_monitor(ui):
    try:
        from deva.naja.cognition.openrouter_monitor import (
            get_openrouter_trend, get_ai_compute_trend, format_tokens,
        )
    except Exception:
        return

    from pywebio.output import put_html

    from .layout import card, empty_line, legend_bar

    try:
        or_trend = get_openrouter_trend()
        ai_trend = get_ai_compute_trend()
    except Exception:
        or_trend = None
        ai_trend = None

    if not or_trend and not ai_trend:
        put_html(card(
            title="TOKEN 消耗监控",
            icon="🔥",
            body=empty_line(
                "尚未采集",
                "缓存为空（openrouter_trend 表无 trend 记录），任务可能从未成功运行过",
            ),
        ))
        return

    blocks = []

    # ================= 头部 =================
    alert_level = (or_trend or {}).get("alert_level", "normal")
    alert_label, alert_color = ALERT_STYLE.get(alert_level, ("❓ 未知级别", C_GRAY))
    is_stale = bool((or_trend or {}).get("is_stale"))
    if is_stale:
        # 数据都停了，业务告警「正常」只会误导：改成明确的不可用
        alert_label, alert_color = "⚪ 数据不可用", C_GRAY

    # ================= 陈旧 / 失败横幅 =================
    if or_trend:
        age = or_trend.get("data_age_days")
        last_ok = (or_trend.get("last_success_ts") or "")[:10]
        last_err = or_trend.get("last_error") or ""
        fails = or_trend.get("consecutive_failures") or 0

        if is_stale:
            detail = f"最新数据 {or_trend.get('latest_date') or '未知'}"
            if age is not None:
                detail += f"，距今 {age} 天"
            if last_ok:
                detail += f" · 上次成功 {last_ok}"
            if fails:
                detail += f" · 连续失败 {fails} 次"
            if last_err:
                detail += f"：{last_err}"
            blocks.append(f"""
            <div style="background:rgba(148,163,184,0.12);border-left:3px solid {C_GRAY};
                        padding:7px 11px;margin:0 0 10px 0;border-radius:0 6px 6px 0;">
                <div style="font-size:11px;color:{C_GRAY};font-weight:600;">
                    ⚠️ 数据已停止更新，下方结论不可采信
                </div>
                <div style="font-size:11px;color:#64748b;margin-top:2px;">{detail}</div>
            </div>
            """)
        elif fails and last_err:
            blocks.append(f"""
            <div style="background:rgba(239,68,68,0.10);border-left:3px solid {C_RED};
                        padding:7px 11px;margin:0 0 10px 0;border-radius:0 6px 6px 0;">
                <div style="font-size:11px;color:{C_RED};">
                    本次取数失败（连续 {fails} 次）：{last_err}，以下为上次成功的数据
                </div>
            </div>
            """)

    # ================= OpenRouter 主区 =================
    if or_trend:
        latest_fmt = or_trend.get("latest_total_formatted") or "N/A"
        latest_date = or_trend.get("latest_date") or "未知"
        period_days = int(or_trend.get("period_days") or 1)
        gran = or_trend.get("granularity") or "unknown"
        is_weekly = gran == "weekly"
        period_label = or_trend.get("period_label") or ("周" if is_weekly else "日")

        week_fmt = or_trend.get("rolling_7d_formatted") or "N/A"
        week_change = or_trend.get("rolling_7d_change_pct")
        prev_fmt = or_trend.get("previous_total_formatted") or "N/A"
        latest_change = or_trend.get("latest_change")
        wow = or_trend.get("wow_same_weekday_pct")
        wow_base_fmt = or_trend.get("wow_base_formatted") or "N/A"
        raw_direction = or_trend.get("direction", "unknown")

        # 口径改造前写入的缓存没有 trend_basis —— 它的 direction 是旧算法产物，
        # 不能拿来冒充新口径结论（否则"下降"会和"可比点 0"同时挂在屏幕上）
        has_new_schema = bool(or_trend.get("trend_basis"))
        direction = raw_direction if has_new_schema else "unknown"

        dir_label, dir_color = DIRECTION_STYLE.get(direction, DIRECTION_STYLE["unknown"])
        confidence = or_trend.get("trend_confidence", "none")
        conf_label = _CONFIDENCE_LABEL.get(confidence, confidence)
        if not has_new_schema:
            conf_label = "旧缓存"
        trend_basis = or_trend.get("trend_basis", "insufficient")
        basis_label = {
            "week_over_week": "周环比",
            "rolling_7d": "7 日滚动",
            "same_weekday": "同星期对齐",
            "insufficient": "数据不足",
        }.get(trend_basis, trend_basis)
        points = or_trend.get("comparable_points") or 0
        data_points = or_trend.get("data_points") or or_trend.get("data_days") or 0
        missing = or_trend.get("rolling_window_missing_days") or 0
        conflict = or_trend.get("momentum_conflict") or ""

        # 背离时方向标签必须跟着改：屏幕上不许同时出现「🚀 强劲上升」和「-4.5%」
        if conflict == "trend_up_latest_down":
            dir_label, dir_color = "⚠️ 上升转弱", C_RED
        elif conflict == "trend_down_latest_up":
            dir_label, dir_color = "🔄 下降转强", C_BLUE

        wow_val, wow_color = _fmt_change(wow)
        week_val, week_color = _fmt_change(week_change)
        latest_val, latest_color = _fmt_change(latest_change)
        avg_trend = float(or_trend.get("recent_avg_change") or 0.0)

        # ---- 徽标：每一种异常都必须自己解释自己 ----
        badges = ""
        if is_stale:
            age_txt = or_trend.get("data_age_days")
            badges += _badge(f"⚠️ 陈旧 {age_txt} 天" if age_txt is not None else "⚠️ 陈旧", C_GRAY)
        if conflict == "trend_up_latest_down":
            badges += _badge("⚠️ 涨势逆转", C_RED)
        elif conflict == "trend_down_latest_up":
            badges += _badge("🔄 跌势反转", C_BLUE)
        if or_trend.get("is_anomaly"):
            badges += _badge("⚠️ 异常", C_RED)
        if confidence == "low":
            badges += _badge("低置信", C_BLUE)
        if not is_weekly and or_trend.get("rolling_7d") is None and missing:
            badges += _badge(f"7日缺 {missing} 天", C_ORANGE)

        # ---- 当前周期是否走完：周频源里最新桶通常只有一两天的量 ----
        incomplete_line = ""
        if or_trend.get("is_incomplete_period"):
            inc_fmt = or_trend.get("incomplete_total_formatted") or "N/A"
            incomplete_line = f"""
            <div style="font-size:11px;color:{C_ORANGE};margin:0 0 10px 0;">
                ⏳ 本{period_label}未完，已录 {inc_fmt} —— 上方为最近一个完整{period_label}，不参与环比
            </div>
            """

        # ---- 四格：按粒度换标签，绝不把日频标签贴到周频数据上 ----
        if is_weekly:
            cells = (
                _cell(latest_fmt, f"本{period_label}消耗", "#f59e0b", f"{latest_date} 起 {period_days} 天")
                + _cell(prev_fmt, f"上一{period_label}", "#94a3b8", "环比基准")
                + _cell(latest_val, f"{period_label}环比", latest_color, f"vs {prev_fmt}")
                + _cell(
                    dir_label, "趋势方向", dir_color,
                    f"{conf_label} · 4期趋势 {avg_trend:+.1f}%" if conflict else f"{conf_label} · {points} {period_label}",
                )
            )
            sample_label = f"样本 {data_points} 周"
            header_txt = "📡 OpenRouter 用量（周频 · 全站）"
        else:
            if or_trend.get("rolling_7d") is None:
                week_sub = f"窗口缺 {missing} 天" if missing else "待下次采集"
            elif week_change is not None:
                week_sub = f"环比 {week_change:+.1f}%"
            else:
                week_sub = "环比 N/A"
            wow_sub = f"vs {wow_base_fmt}" if or_trend.get("wow_base_total") else "旧缓存无此口径"
            cells = (
                _cell(latest_fmt, "单日消耗", "#f59e0b", latest_date)
                + _cell(week_fmt, "7 日合计", "#f59e0b", week_sub, week_color)
                + _cell(wow_val, "同星期环比", wow_color, wow_sub)
                + _cell(dir_label, "趋势方向", dir_color, f"{conf_label} · {points} 点")
            )
            sample_label = f"样本 {data_points} 天" if data_points else "样本 未知"
            header_txt = "📡 OpenRouter 用量（日频）"

        # 表头必须自证粒度：只看这一行的人也要知道下面 4 个格子是周桶还是日桶
        blocks.append(f"""
        <div style="font-size:11px;color:#94a3b8;margin-bottom:6px;font-weight:500;">
            {header_txt}{badges}
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:6px;">
            {cells}
        </div>
        {incomplete_line}
        """)

        # 趋势强度条 + 口径说明
        strength = abs(or_trend.get("strength") or 0) if has_new_schema else 0.0
        strength_pct = min(int(strength * 100), 100)
        accel = (or_trend.get("acceleration") or 0) if has_new_schema else 0.0
        blocks.append(f"""
        <div style="background:rgba(245,158,11,0.05);border:1px solid rgba(245,158,11,0.10);
                    border-radius:8px;padding:8px 12px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                <span style="font-size:11px;color:#94a3b8;">趋势强度 {strength:.2f}</span>
                <span style="font-size:11px;color:#64748b;">
                    口径 {basis_label} · 可比点 {points} · {sample_label} · 加速 {accel:+.1f}pp
                </span>
            </div>
            <div style="height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden;">
                <div style="width:{strength_pct}%;height:100%;background:{dir_color};border-radius:3px;"></div>
            </div>
        </div>
        """)

        # ---- 构成：谁在撑这个数（Others 是残差桶，代表 top-9 之外的全部模型）----
        top_models = [m for m in (or_trend.get("top_models") or []) if m.get("name") != "Others"][:5]
        other_share = or_trend.get("other_share_pct")
        if top_models:
            bars = ""
            for m in top_models:
                share = float(m.get("share_pct") or 0)
                short = str(m.get("name", "")).split("/")[-1]
                bars += f"""
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
                    <span style="font-size:11px;color:#94a3b8;width:150px;overflow:hidden;
                                 text-overflow:ellipsis;white-space:nowrap;">{short}</span>
                    <div style="flex:1;height:4px;background:rgba(255,255,255,0.05);border-radius:2px;">
                        <div style="width:{min(share * 4, 100):.1f}%;height:100%;
                                    background:rgba(168,85,247,0.55);border-radius:2px;"></div>
                    </div>
                    <span style="font-size:11px;color:#cbd5e1;width:52px;text-align:right;">{m.get("formatted")}</span>
                    <span style="font-size:11px;color:#64748b;width:38px;text-align:right;">{share:.1f}%</span>
                </div>
                """
            other_txt = f" · Others {other_share:.1f}%" if other_share is not None else ""
            blocks.append(f"""
            <details class="cog-fold">
                <summary>{period_label}消耗构成（Top {len(top_models)} 模型{other_txt}）</summary>
                <div class="cog-fold-body">{bars}</div>
            </details>
            """)

        recommendation = or_trend.get("recommendation") or ""
        if not has_new_schema:
            # 旧口径的方向结论已作废，别拿"算力需求下降，建议减仓"去指导人
            recommendation = "旧口径缓存：方向结论已作废，等下一次采集成功后重新评估"
        if recommendation:
            rec_color = C_RED if conflict or or_trend.get("is_anomaly") else C_ORANGE
            if is_stale:
                rec_color = C_GRAY
            blocks.append(f"""
            <div style="background:rgba(245,158,11,0.04);border-left:3px solid rgba(245,158,11,0.3);
                        padding:6px 10px;margin-bottom:12px;border-radius:0 6px 6px 0;">
                <div style="font-size:11px;color:{rec_color};">💡 {recommendation}</div>
            </div>
            """)

    # ================= AI 算力趋势 =================
    if ai_trend:
        ai_direction = ai_trend.get("trend_direction", "unknown")
        ai_label, ai_color = TREND_DIR_STYLE.get(ai_direction, TREND_DIR_STYLE["unknown"])
        ai_stale = bool(ai_trend.get("is_stale"))
        if ai_stale:
            ai_color = C_GRAY

        total_tokens = ai_trend.get("total_tokens") or 0
        total_fmt = format_tokens(total_tokens) if total_tokens else "N/A"
        cum = ai_trend.get("cumulative_growth") or 0.0
        ai_period = int(ai_trend.get("period_days") or 1)
        win = ai_trend.get("growth_window_days") or 0
        win_unit = "周" if ai_period >= 7 else "日"
        win_label = f"{win} {win_unit}" if win else "窗口"
        conf = _CONFIDENCE_LABEL.get(ai_trend.get("trend_confidence", "none"), "无置信")

        ai_badges = _badge("⚠️ 陈旧", C_GRAY) if ai_stale else ""
        if ai_trend.get("is_abnormal"):
            ai_badges += _badge("⚠️ 异常", C_RED)
        ai_conflict = ai_trend.get("momentum_conflict") or ""
        # 背离时 ai_label 已经改成「上升转弱 / 下降转强」，再挂一个同义徽标
        # 就是并排两句话说同一件事，这里只在不冲突时补徽标。
        if ai_conflict == "trend_up_latest_down":
            ai_label, ai_color = "⚠️ 上升转弱", C_RED
        elif ai_conflict == "trend_down_latest_up":
            ai_label, ai_color = "🔄 下降转强", C_BLUE

        # ❗`get_ai_compute_trend()` 读的是**同一张** TREND_TABLE，只是给决策层换了个视角：
        # 四格里「总量 / 趋势方向 / 环比」跟上方 OpenRouter 主区逐字相同，
        # 再铺一遍等于把同三个数字放两次。两者同时有数据时压成一行，
        # 只保留它独有的信息（需求强度、增长窗口、置信度）。
        if or_trend:
            blocks.append(f"""
            <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;
                        padding:7px 11px;border-radius:8px;margin-bottom:10px;
                        background:rgba(168,85,247,0.05);border:1px solid rgba(168,85,247,0.14);">
                <span style="font-size:11px;color:#94a3b8;">🖥️ 算力需求信号</span>
                <span style="font-size:11px;color:{ai_color};font-weight:600;">{ai_label}</span>{ai_badges}
                <span style="font-size:11px;color:#64748b;">·</span>
                <span style="font-size:11px;color:#94a3b8;">需求强度
                    <b style="color:#a855f7;">{ai_trend.get('base_strength') or 0:.2f}</b></span>
                <span style="font-size:11px;color:#64748b;">·</span>
                <span style="font-size:11px;color:#94a3b8;">{win_label}增长
                    <b style="color:{C_GREEN if cum > 0 else (C_RED if cum < 0 else C_BLUE)};">{cum:+.1%}</b></span>
                <span style="font-size:11px;color:#64748b;">·</span>
                <span style="font-size:11px;color:#64748b;">{conf}</span>
            </div>
            """)
        else:
            # 只有 AI 趋势有数（OpenRouter 主区拿不到）时，数字得自己站出来
            blocks.append(f"""
            <div style="font-size:11px;color:#94a3b8;margin:10px 0 6px;font-weight:500;">
                🖥️ AI 算力趋势{ai_badges}
            </div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px;">
                {_cell(total_fmt, f"本{'周' if ai_period >= 7 else '日'}消耗", "#a855f7", ai_trend.get("latest_date") or "未知")}
                {_cell(f"{cum:+.1%}", f"{win_label}增长", C_GREEN if cum > 0 else (C_RED if cum < 0 else C_BLUE), win_label + "滚动")}
                {_cell(ai_label, "趋势", ai_color, conf)}
                {_cell(f"{ai_trend.get('base_strength') or 0:.2f}", "需求强度", "#a855f7", "0~1")}
            </div>
            """)

        ai_message = ai_trend.get("message") or ""
        # ❗message 是同一份趋势数据的自然语言复述（「周消耗 164.04T(+4.5%) …
        # 本周未完 已录 4.52T」），每个数字上方四格与「本周未完」提示都已经写过。
        # 主区在时不重复；只有 AI 段单独存在时它才是唯一的信息来源。
        if ai_message and not ai_stale and not or_trend:
            blocks.append(f"""
            <div style="background:rgba(168,85,247,0.04);border-left:3px solid rgba(168,85,247,0.3);
                        padding:6px 10px;border-radius:0 6px 6px 0;">
                <div style="font-size:11px;color:#a855f7;">🖥️ {ai_message}</div>
            </div>
            """)

    put_html(card(
        title="TOKEN 消耗监控",
        icon="🔥",
        meta=f'告警: <b style="color: {alert_color};">{alert_label}</b>',
        body=f'{legend_bar()}<div style="margin-top: 8px;">{"".join(blocks)}</div>',
    ))
