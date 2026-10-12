"""新闻消化器 —— 复用 manas 的注意力原则，把「信息不过载」做成一件可查的产物。

回答的问题：**现在这么多新闻，我到底该看哪几条？**

三层结构：

    focus.py    「我们关心什么」      —— 持仓 / 自选 / 关注叙事 / 关注主题（复用 manas + Portfolio）
    triage.py   「哪条更值得看」      —— 持仓优先的相关度打分与分组（纯计算）
    digest.py   「呈现出来」          —— 每日 HTML 报告 / 纯文本 / UI 出口

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

from .digest import (
    DIGEST_DIR,
    build_digest,
    get_news_digest_summary,
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
    NewsTriage,
    ScoredNews,
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
    "GROUP_HOLDING",
    "GROUP_THEME",
    "GROUP_MACRO",
    "GROUP_ORDER",
    "GROUP_LABELS",
    # 报告
    "build_digest",
    "get_news_digest_summary",
    "render_digest_html",
    "render_digest_text",
    "write_daily_digest",
    "run_daily_digest",
    "DIGEST_DIR",
]
