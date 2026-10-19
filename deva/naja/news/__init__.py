"""新闻消化器 —— 复用 manas 的注意力原则，把「信息不过载」做成一件可查的产物。

回答的问题：**现在这么多新闻，我到底该看哪几条？**

三层结构：

    focus.py    「我们关心什么」      —— 持仓 / 自选 / 关注叙事 / 关注主题（复用 manas + Portfolio）
    triage.py   「哪条更值得看」      —— 分档制相关度打分与分组（纯计算，持仓数学上必然优先）
    digest.py   「呈现出来」          —— 每日 HTML 报告 / 纯文本 / UI 出口
    page.py     「给人看的页面」      —— ``/news`` 独立页面（复用报告的同一份片段）

另有一个横切的小模块：``dedup.py``「把同一件事折成一条」——金十每发一条快讯
会有中文版和英文版两条记录，不折叠的话托盘和面板的名额近一半被重复吃掉。

用法::

    from deva.naja.news import get_news_digest_summary

    digest = get_news_digest_summary()          # 纯 dict，可直接喂 UI
    print(digest["stats"], digest["groups"]["holding"])

单独用作库（不启动 Naja 容器）::

    from deva.naja.news import NewsFocusState, NewsTriage

    focus = NewsFocusState(holdings=("宁德时代",), themes=(("AI", ("大模型",)),))
    result = NewsTriage(focus).analyze([{"title": "宁德时代扩产", "importance_score": 0.6}])

注意：本包**只读**既有数据（已评分新闻池 + 关注配置），不重写 manas 或
评分器的任何逻辑——一份实现，多处复用。
"""

from .dedup import (
    DedupConfig,
    collapse,
    find_groups,
    format_dup_suffix,
    normalize_title,
)
from .digest import (
    DIGEST_DIR,
    build_digest,
    get_news_digest_summary,
    render_digest_fragment,
    render_digest_html,
    render_digest_text,
    run_daily_digest,
    write_daily_digest,
)
from .focus import (
    NewsFocusState,
    build_focus_state,
    build_manas_focus_state,
    invalidate_focus_cache,
)
from .triage import (
    GROUP_HOLDING,
    GROUP_LABELS,
    GROUP_MACRO,
    GROUP_ORDER,
    GROUP_THEME,
    PIERCE_MAX_SENTIMENT,
    PIERCE_MIN_IMPORTANCE,
    THEME_NUDGE,
    TIER_HOLDING,
    TIER_MACRO,
    TIER_ORDER,
    TIER_PIERCE,
    TIER_THEME,
    TIER_WATCHLIST,
    NewsTriage,
    ScoredNews,
    TierBand,
    TriageConfig,
)

__all__ = [
    # 焦点
    "NewsFocusState",
    "build_focus_state",
    "build_manas_focus_state",
    "invalidate_focus_cache",
    # 筛选
    "NewsTriage",
    "ScoredNews",
    "TriageConfig",
    "TierBand",
    "GROUP_HOLDING",
    "GROUP_THEME",
    "GROUP_MACRO",
    "GROUP_ORDER",
    "GROUP_LABELS",
    "TIER_HOLDING",
    "TIER_THEME",
    "TIER_WATCHLIST",
    "TIER_MACRO",
    "TIER_PIERCE",
    "TIER_ORDER",
    "THEME_NUDGE",
    "PIERCE_MIN_IMPORTANCE",
    "PIERCE_MAX_SENTIMENT",
    # 去重（呈现前折叠）
    "DedupConfig",
    "collapse",
    "find_groups",
    "format_dup_suffix",
    "normalize_title",
    # 报告
    "build_digest",
    "get_news_digest_summary",
    "render_digest_html",
    "render_digest_fragment",
    "render_digest_text",
    "write_daily_digest",
    "run_daily_digest",
    "DIGEST_DIR",
]
