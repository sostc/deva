"""Event Bus 组件 —— 认知事件流

2026-10-19 重排 + 修 bug：

原实现把 `DATA_SOURCES` 写死成 `news / market / cognitive` 三个 key 去匹配
`insight['source']`，但 source 的真实取值是 `strategy:<策略名>`、
`hotspot`、`llm_reflection:refl_<流水号>`、`attention_os.make_decision` 这类
「来源类型 + 实例 id」的串（NB 库实测 198 个互不相同的值）。

结果是左边写「事件来源（98 种活跃）」，右边三行全 0 —— 屏上自相矛盾，
而人会把它读成「没有事件」。现在改成按 source 的前缀分桶：
`llm_reflection:refl_123` → `llm_reflection`，`strategy:xxx` → `strategy`，
桶由真实数据推导，不再依赖白名单，也不可能出现「有 98 种却全是 0」。
"""

from collections import Counter, defaultdict

from pywebio.output import put_html

from deva.naja.infra.ui.ui_style import format_timestamp

from .layout import card


#: 已知前缀的中文名与配色（未列出的前缀原样显示，不会丢数据）
_BUCKET_META = {
    "news": ("新闻事件", "📡", "#f97316"),
    "hotspot": ("热点事件", "🔥", "#f59e0b"),
    "strategy": ("策略结果", "📈", "#14b8a6"),
    "llm_reflection": ("LLM 反思", "🤖", "#0ea5e9"),
    "insight_engine": ("洞察引擎", "💡", "#a855f7"),
    "attention_os.make_decision": ("决策中心", "🧭", "#6366f1"),
    "attention_os": ("注意力", "👁️", "#8b5cf6"),
    "bandit": ("Bandit", "🎯", "#ec4899"),
    "radar": ("雷达", "📊", "#22c55e"),
}


def _bucket_of(source: str) -> str:
    """把 source 收敛成"来源类型"。

    规则：取第一个分隔符（``:`` 或 ``.``）之前的部分。
    ``llm_reflection:refl_1781357512835`` → ``llm_reflection``；
    ``attention_os.make_decision`` 有专门的映射键，仍能命中。
    """
    s = (source or "").strip()
    if not s:
        return "unknown"
    if s in _BUCKET_META:
        return s
    for sep in (":", "."):
        if sep in s:
            return s.split(sep, 1)[0]
    return s


def _get_insight_pool():
    """获取 InsightPool（AppContainer 优先，SR fallback 仅开发用）"""
    from deva.naja.application.container import get_app_container
    container = get_app_container()
    if container is not None:
        ip = getattr(container, 'insight_pool', None)
        if ip is not None:
            return ip
    from deva.naja.register import SR
    return SR('insight_pool')


def _fetch_insight_data():
    """统一获取 insight 数据，并按来源前缀分桶。"""
    try:
        insight_pool = _get_insight_pool()
        if not insight_pool:
            return {}, {}, []
        insights = insight_pool.get_recent_insights(limit=100)

        source_counts = Counter()
        recent_by_source = defaultdict(list)
        for insight in insights:
            bucket = _bucket_of(insight.get('source', ''))
            source_counts[bucket] += 1
            if len(recent_by_source[bucket]) < 2:
                recent_by_source[bucket].append(insight)

        return dict(source_counts), dict(recent_by_source), insights[:20]
    except Exception:
        return {}, {}, []


def _bucket_style(bucket: str):
    """前缀 → (中文名, 图标, 颜色)。未知前缀原样显示，不吞数据。"""
    return _BUCKET_META.get(bucket, (bucket, "•", "#64748b"))


def render_event_bus(ui, source_counts=None, recent_by_source=None, recent_insights=None):
    """渲染认知事件流。"""
    try:
        from deva.naja.events import get_event_bus
        bus = get_event_bus()
        bus_len = len(getattr(bus, '_recent_events', []))
        subscriber_count = sum(len(subs) for subs in getattr(bus, '_subscribers', {}).values())
        dedup_window = int(getattr(bus, '_dedup_window', 30))
    except Exception:
        bus_len = 0
        subscriber_count = 0
        dedup_window = 30

    if source_counts is None or recent_by_source is None:
        source_counts, recent_by_source, recent_insights = _fetch_insight_data()
    if recent_insights is None:
        recent_insights = []

    # ── 左列：事件来源（按桶计数，取前 5）──
    total_insights = sum(source_counts.values())
    top_buckets = sorted(source_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
    max_count = max((c for _, c in top_buckets), default=0) or 1

    if top_buckets:
        rows = ""
        for bucket, count in top_buckets:
            name, icon, color = _bucket_style(bucket)
            width = max(4, int(count / max_count * 100))
            rows += f"""
            <div style="margin-bottom: 7px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px;
                            color: #94a3b8; margin-bottom: 3px;">
                    <span>{icon} {name}</span>
                    <span style="color: {color}; font-weight: 600;">{count}</span>
                </div>
                <div style="height: 3px; background: rgba(255,255,255,.06); border-radius: 2px;">
                    <div style="width: {width}%; height: 100%; background: {color}; border-radius: 2px;"></div>
                </div>
            </div>
            """
        source_html = rows
    else:
        source_html = '<div style="font-size: 11px; color: #64748b;">暂无来源数据</div>'

    # ── 中列：处理流程（去掉散文式说明，改成紧凑链）──
    flow_steps = [
        ("📡", "雷达", "事件入队", "#14b8a6"),
        ("🔄", "跨信号", "共振检测", "#a855f7"),
        ("🤖", "LLM反思", "深度洞察", "#0ea5e9"),
        ("📊", "反馈", "注意力调度", "#4ade80"),
    ]
    flow_html = "".join(
        f"""
        <div style="display: flex; align-items: center; gap: 6px; padding: 5px 8px;
                    background: {color}14; border-radius: 4px; margin-bottom: 5px; font-size: 11px;">
            <span>{icon}</span>
            <span style="color: {color};">{name}</span>
            <span style="color: #475569;">→</span>
            <span style="color: #94a3b8;">{desc}</span>
        </div>
        """
        for icon, name, desc, color in flow_steps
    )

    # ── 右列：最近事件 ──
    recent_html = ""
    for bucket in list(source_counts.keys())[:3]:
        items = recent_by_source.get(bucket, [])
        if not items:
            continue
        name, icon, color = _bucket_style(bucket)
        lines = "".join(
            f"""
            <div style="display: flex; justify-content: space-between; gap: 8px; font-size: 11px;
                        color: #94a3b8; padding: 2px 0;">
                <span style="color: {color}; flex-shrink: 0;">{format_timestamp(float(i.get('ts', 0)))[-8:]}</span>
                <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    {str(i.get('theme', '-'))[:24]}
                </span>
            </div>
            """
            for i in items
        )
        recent_html += f"""
        <div style="margin-bottom: 3px;">
            <div style="font-size: 11px; color: {color}; font-weight: 600; margin-bottom: 2px;">{icon} {name}</div>
            {lines}
        </div>
        """
    if not recent_html:
        recent_html = '<div style="font-size: 11px; color: #64748b;">暂无事件</div>'

    body = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px;">
        <div>
            <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">
                事件来源 · {len(source_counts)} 类 / {total_insights} 条
            </div>
            {source_html}
        </div>
        <div>
            <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">处理流程</div>
            {flow_html}
        </div>
        <div>
            <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">最近事件</div>
            {recent_html}
        </div>
    </div>
    """

    put_html(card(
        title="认知事件流",
        icon="🌊",
        meta=f"事件 <b>{bus_len}</b> · 订阅者 <b>{subscriber_count}</b> · 去重 <b>{dedup_window}s</b>",
        body=body,
    ))
