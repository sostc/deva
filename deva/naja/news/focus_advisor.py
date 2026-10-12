"""
FocusAdvisor —— 从持仓推导「该关注的产业链主题」

═══════════════════════════════════════════════════════════════════════════
设计动机（用户 2026-10-12 原话）
═══════════════════════════════════════════════════════════════════════════

    "我应该说持仓什么就应该关注它周边供应链，或者它前面需求端的相关主题，
      而不是去随意地关注一些主题。"

所以本模块把**持仓**翻译成**关注主题**：

    持仓股票 ─┬─ 自身板块（``stock_block_map``）
              ├─ 上游供应链（``supply_chain_graph`` 的**直接**上游公司）
              └─ 下游需求端（**直接**下游公司）
                     ↓
               候选主题（带 score 与可读理由）

═══════════════════════════════════════════════════════════════════════════
权重口径（2026-10-12）
═══════════════════════════════════════════════════════════════════════════

    score(主题) = max(各持仓对该主题的贡献) + 共识加分

    自身板块        0.60   「我持有它，它是什么」
    上游供应链      0.50   「它靠谁活着」
    下游需求端      0.50   「谁在为它买单」
    共识加分        每多一只持仓命中 +0.10，上限 +0.30

用 ``max`` 而不是 ``sum``：否则高频词（AI / 芯片）会因为出现次数多而爆表，
把真正有区分度的主题压下去。共识加分单独承担"多只持仓共同指向"的含义。

═══════════════════════════════════════════════════════════════════════════
边界（如实说明，不粉饰）
═══════════════════════════════════════════════════════════════════════════

* 只覆盖 ``supply_chain_graph`` 里有的上下游（硬编码 AI 芯片链，39 家公司）。
  持仓不在图里 → 退化为「仅自身板块」，并在 ``degraded`` 里写明是**哪只**漏了。
* 只取 **depth=1 的直接上下游**。图谱的 ``get_upstream`` 默认做传递闭包
  （实测 CRWV 的上游会一路包含台积电/美光/ASML），对"我该关注什么"是噪声。
* 过宽的词（``AI`` / ``AI应用``）**整个**不进主题列表（连同它的 evidence 一起丢弃）
  ——它们会让几乎所有新闻都命中"关注叙事"档，重演 2026-10-12 那个"17 个宽泛主题
  命中一切、分组失效"的坑。注意：这些词若同时挂在别的主题的 evidence 里（如
  ``英伟达 自身属于「AI芯片」``）不受影响，被丢的只是"以它为主题"的那一条。
* **不覆盖已有主题**：某主题已在关注列表里（无论手动还是别的来源）就跳过，
  绝不改它的 ``source``——否则"撤销推导"会把用户手动的关注一起删掉。

═══════════════════════════════════════════════════════════════════════════
与其它模块的关系
═══════════════════════════════════════════════════════════════════════════

    focus_advisor   决定「关注什么」 → 写 ``naja_focus_config``
    news/focus.py   读「我们在关注什么」 → 生成 ``NewsFocusState``
    news/triage.py  用 ``NewsFocusState`` 给新闻打分
    —— 前者是**输入**，后两者是消费端，不要互相调用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)


# ── 权重 ────────────────────────────────────────────────────────────────
DERIVE_SELF_WEIGHT = 0.60
DERIVE_UPSTREAM_WEIGHT = 0.50
DERIVE_DOWNSTREAM_WEIGHT = 0.50
DERIVE_CONSENSUS_BONUS = 0.10
DERIVE_MAX_CONSENSUS_BONUS = 0.30
DERIVE_MAX_SCORE = 1.0

# 推导来源标记（写进 FocusItem.source）
SOURCE_DERIVED = "derived"
SOURCE_MANUAL_HINT = "user"

# 关注配置表（与 focus_manager.FOCUS_CONFIG_TABLE 同一张）
FOCUS_CONFIG_TABLE = "naja_focus_config"
# 用户明确撤销过的主题——自动采纳不再把它们加回来
_REVOKED_KEY = "revoked_derived_topics"

RELATION_SELF = "self"
RELATION_UPSTREAM = "upstream"
RELATION_DOWNSTREAM = "downstream"

RELATION_LABELS = {
    RELATION_SELF: "自身板块",
    RELATION_UPSTREAM: "上游供应链",
    RELATION_DOWNSTREAM: "下游需求端",
}

# 过宽的主题不进列表（见模块 docstring 的边界说明）
TOO_BROAD_TOPICS = frozenset({"AI", "AI应用"})

# 一次最多推荐多少个主题（避免"关注列表又变成啥都有"）
DEFAULT_MAX_TOPICS = 8
# 采纳阈值：0.50 恰好保住"仅上游贡献"的主题（用户点名要盯供应链）
DEFAULT_APPLY_MIN_SCORE = 0.50


def _dedupe(items: Sequence[str]) -> List[str]:
    """去重且保持首次出现顺序。

    推导是**逐持仓**遍历的，同一个上游公司（如 SK海力士）会被重复报同一条
    降级说明——不去重的话 degraded 里会有 N 条一模一样的噪声。
    """
    return list(dict.fromkeys(x for x in items if x))


def _load_revoked() -> List[str]:
    """读「用户撤销过的推导主题」。

    没有这个记录的话，自动采纳会在每次启动时把用户刚删掉的主题又加回来。
    """
    try:
        from deva import NB
        return [str(x) for x in (NB(FOCUS_CONFIG_TABLE).get(_REVOKED_KEY, []) or [])]
    except Exception as e:
        log.warning("[FocusAdvisor] 读取撤销记录失败（视为空）: %s", e)
        return []


def _record_revoked(topics: Sequence[str]) -> List[str]:
    """把主题记进「已撤销」名单（自动采纳时跳过）。返回记录后的全量名单。"""
    topics = [str(t) for t in topics if t]
    if not topics:
        return _load_revoked()
    try:
        from deva import NB
        nb = NB(FOCUS_CONFIG_TABLE)
        current = _load_revoked()
        for t in topics:
            if t not in current:
                current.append(t)
        nb[_REVOKED_KEY] = current
        return current
    except Exception as e:
        # 记不进去只影响"自动采纳会不会加回来"，不该让撤销本身失败
        log.warning("[FocusAdvisor] 记录撤销名单失败: %s", e)
        return _load_revoked()


def clear_revoked() -> Dict[str, Any]:
    """清空「已撤销」名单——之后自动采纳会重新考虑这些主题。"""
    try:
        from deva import NB
        nb = NB(FOCUS_CONFIG_TABLE)
        nb[_REVOKED_KEY] = []
        return {"ok": True, "reason": "", "count": 0}
    except Exception as e:
        return {"ok": False, "reason": f"清空撤销名单失败（{type(e).__name__}: {e}）"}


@dataclass(frozen=True)
class DerivedTopic:
    """一个推导出来的候选主题（纯数据，可安全序列化）。"""

    topic: str                                      # 主题名（写入 focus_id）
    score: float                                    # 综合权重 0~1
    relations: Tuple[str, ...] = ()                 # 涉及关系（self/upstream/downstream）
    from_holdings: Tuple[str, ...] = ()             # 由哪些持仓推出
    evidence: Tuple[str, ...] = ()                  # 可读的推导依据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "score": self.score,
            "relations": list(self.relations),
            "relation_labels": [RELATION_LABELS.get(r, r) for r in self.relations],
            "from_holdings": list(self.from_holdings),
            "evidence": list(self.evidence),
        }


# ── 依赖懒加载（避免 news → attention → bandit 的导入期耦合）──────────────

def _default_holdings() -> Tuple[List[Any], List[str]]:
    """返回 (持仓列表, 降级说明)。"""
    degraded: List[str] = []
    try:
        from deva.naja.attention.portfolio import get_portfolio
        pf = get_portfolio()
    except Exception as e:
        return [], [f"持仓：Portfolio 不可用（{type(e).__name__}: {e}）"]

    try:
        holdings = list(pf.get_all_holdings() or [])
    except Exception as e:
        return [], [f"持仓：读取失败（{type(e).__name__}: {e}）"]

    if not holdings:
        # 区分「真的没持仓」与「账户没建起来」——本项目的老病
        try:
            status = pf.get_account_status() or {}
            failures = status.get("failures") or []
            initialized = status.get("brokerage_initialized") or []
            if failures and not initialized:
                degraded.append(
                    f"持仓：账户初始化失败 {failures}，读到的空持仓**不代表真的没有**"
                )
            elif failures:
                degraded.append(f"持仓：部分账户初始化失败 {failures}（已读到其它账户）")
        except Exception:
            pass
    return holdings, degraded


def _default_graph() -> Any:
    from deva.naja.bandit.supply_chain_graph import get_supply_chain_graph
    return get_supply_chain_graph()


def _default_block_map() -> Any:
    from deva.naja.bandit.stock_block_map import get_stock_block_map
    return get_stock_block_map()


def _default_focus_manager() -> Any:
    from deva.naja.attention.focus_manager import get_attention_focus_manager
    return get_attention_focus_manager()


def _direct_neighbors(graph: Any, node_id: str, direction: str) -> List[Any]:
    """取**一跳**邻居（直接上下游）。

    为什么不用 ``graph.get_upstream(id, 1)``：它的 ``max_depth`` 是「额外跳数」
    （DFS 从 depth=0 起、剪枝条件 ``depth > max_depth``），传 1 实际走**两跳**
    ——实测 CRWV 的上游会一路包含台积电/美光/ASML。对"该关注哪些**直接**
    供应商/客户"来说二级节点是噪声。

    优先用图谱新增的 ``get_direct_*``（语义明确）；老版本没有时退化为
    ``max_depth=0``（在旧语义下同样表示一跳）。
    """
    up = direction == "up"
    direct = getattr(
        graph, "get_direct_upstream" if up else "get_direct_downstream", None
    )
    if callable(direct):
        return list(direct(node_id) or [])
    fn = getattr(graph, "get_upstream" if up else "get_downstream", None)
    if not callable(fn):
        return []
    return list(fn(node_id, 0) or [])


# ── 核心：推导 ──────────────────────────────────────────────────────────

def derive_topics(
    holdings: Optional[Sequence[Any]] = None,
    *,
    graph: Any = None,
    block_map: Any = None,
    max_topics: int = DEFAULT_MAX_TOPICS,
    min_score: float = 0.0,
) -> Dict[str, Any]:
    """从持仓推导候选关注主题（**纯计算，不写任何东西**）。

    Args:
        holdings: 持仓列表（``StockInfo``）；``None`` 时自动读合并持仓
        graph: 供应链图谱；``None`` 时取单例
        block_map: 股票板块映射；``None`` 时取单例
        max_topics: 最多返回多少条
        min_score: 过滤低于该分数的主题

    Returns:
        纯 dict：
            ``available``  是否成功推导出内容
            ``reason``     不可用时的原因（``available=False`` 才有）
            ``holdings``   参与推导的持仓（code/name/account）
            ``topics``     候选主题（``DerivedTopic.to_dict()``）
            ``degraded``   降级说明（**失败必须留痕**）
            ``sources``    数据来源标记
    """
    degraded: List[str] = []
    sources: List[str] = []

    if holdings is None:
        holdings, hold_degraded = _default_holdings()
        degraded.extend(hold_degraded)
        sources.append("portfolio")
    holdings = [h for h in (holdings or []) if getattr(h, "code", None)]

    holding_rows = [
        {
            "code": str(getattr(h, "code", "")),
            "name": str(getattr(h, "name", "") or getattr(h, "code", "")),
            "account": str(getattr(h, "account", "") or ""),
        }
        for h in holdings
    ]

    if not holdings:
        return {
            "available": False,
            "reason": "没有可用于推导的持仓",
            "holdings": [],
            "topics": [],
            "degraded": _dedupe(degraded),
            "sources": sources,
        }

    if graph is None:
        try:
            graph = _default_graph()
            sources.append("supply_chain_graph")
        except Exception as e:
            degraded.append(f"供应链图谱不可用（{type(e).__name__}: {e}），仅用自身板块")
            graph = None
    if block_map is None:
        try:
            block_map = _default_block_map()
            sources.append("stock_block_map")
        except Exception as e:
            degraded.append(f"板块映射不可用（{type(e).__name__}: {e}）")
            block_map = None

    if block_map is None and graph is None:
        return {
            "available": False,
            "reason": "推导所需的数据源都不可用（板块映射 + 供应链图谱）",
            "holdings": holding_rows,
            "topics": [],
            "degraded": _dedupe(degraded),
            "sources": sources,
        }

    # topic -> {"per_holding": {code: weight}, "best": (weight, relation), "evidence": [...]}
    acc: Dict[str, Dict[str, Any]] = {}

    def _bump(topic: Any, weight: float, relation: str, holding: str, evidence: str) -> None:
        topic_s = str(topic or "").strip()
        if not topic_s:
            return
        rec = acc.setdefault(topic_s, {"per_holding": {}, "best_weight": 0.0,
                                       "best_relation": relation, "evidence": []})
        prev = rec["per_holding"].get(holding, 0.0)
        if weight > prev:
            # 同一持仓对同一主题只计最大贡献（自身 > 上下游），避免重复累加
            rec["per_holding"][holding] = weight
        if weight >= rec["best_weight"]:
            rec["best_weight"] = weight
            rec["best_relation"] = relation
        if evidence and evidence not in rec["evidence"]:
            rec["evidence"].append(evidence)

    def _labels_for(code_l: str) -> Optional[List[str]]:
        """某公司代码对应的主题候选（叙事 + 板块）。None 表示查不到。"""
        if block_map is None:
            return None
        try:
            md = block_map.get_metadata(code_l)
        except Exception:
            return None
        if md is None:
            return None
        labels = [getattr(md, "narrative", "") or ""]
        labels.extend(getattr(md, "blocks", None) or [])
        return [x for x in labels if x]

    def _collect_company(node: Any, relation: str, holding_code: str,
                         holding_name: str, weight: float) -> None:
        """把一个上下游公司节点翻译成主题候选。"""
        node_type = getattr(getattr(node, "type", None), "value", "")
        if node_type and node_type != "company":
            return  # 产品/技术节点没有板块映射，跳过
        sub_code = getattr(node, "stock_code", None)
        sub_name = getattr(node, "name", "") or sub_code
        if not sub_code:
            return
        labels = _labels_for(str(sub_code).lower())
        if not labels:
            degraded.append(
                f"{sub_name}（{sub_code}）：图谱里有但板块表无映射，该环节未计入主题"
            )
            return
        rel_label = RELATION_LABELS.get(relation, relation)
        for label in labels:
            _bump(
                label, weight, relation, holding_code,
                f"{holding_name} {rel_label} → {sub_name}",
            )

    for h in holdings:
        code = str(getattr(h, "code", "") or "").strip()
        name = str(getattr(h, "name", "") or code)
        code_l = code.lower()
        if not code_l:
            continue

        # ① 自身板块
        self_labels = _labels_for(code_l)
        if self_labels:
            for label in self_labels:
                _bump(label, DERIVE_SELF_WEIGHT, RELATION_SELF, code_l,
                      f"{name} 自身属于「{label}」")
        else:
            degraded.append(f"{name}（{code}）：板块表无映射，自身板块未计入")

        # ② 上下游（**直接**，depth=1）
        node = None
        if graph is not None:
            try:
                node = graph.get_stock_node(code_l)
            except Exception as e:
                degraded.append(f"{name}（{code}）：图谱查询失败（{type(e).__name__}）")
                node = None
        if node is None:
            if graph is not None:
                degraded.append(f"{name}（{code}）：不在供应链图谱中，只推导了自身板块")
            continue

        try:
            upstream = _direct_neighbors(graph, node.id, "up")
        except Exception as e:
            degraded.append(f"{name}：上游查询失败（{type(e).__name__}）")
            upstream = []
        try:
            downstream = _direct_neighbors(graph, node.id, "down")
        except Exception as e:
            degraded.append(f"{name}：下游查询失败（{type(e).__name__}）")
            downstream = []

        for up in upstream:
            _collect_company(up, RELATION_UPSTREAM, code_l, name, DERIVE_UPSTREAM_WEIGHT)
        for down in downstream:
            _collect_company(down, RELATION_DOWNSTREAM, code_l, name, DERIVE_DOWNSTREAM_WEIGHT)

    # 聚合排序
    topics: List[DerivedTopic] = []
    for topic, rec in acc.items():
        if topic in TOO_BROAD_TOPICS:
            continue
        n_holding = len(rec["per_holding"])
        base = max(rec["per_holding"].values()) if rec["per_holding"] else 0.0
        bonus = min(DERIVE_CONSENSUS_BONUS * (n_holding - 1), DERIVE_MAX_CONSENSUS_BONUS)
        score = min(base + bonus, DERIVE_MAX_SCORE)
        if score < min_score:
            continue
        topics.append(DerivedTopic(
            topic=topic,
            score=round(score, 4),
            relations=tuple(sorted({rec["best_relation"]})),
            from_holdings=tuple(sorted(rec["per_holding"].keys())),
            evidence=tuple(rec["evidence"][:4]),
        ))

    topics.sort(key=lambda t: (-t.score, t.topic))
    topics = topics[:max_topics]

    return {
        "available": True,
        "reason": "",
        "holdings": holding_rows,
        "topics": [t.to_dict() for t in topics],
        "degraded": degraded,
        "sources": sources,
    }


# ── 采纳 / 撤销 ─────────────────────────────────────────────────────────

def apply_derived_topics(
    topics: Sequence[Any],
    *,
    manager: Any = None,
    min_score: float = DEFAULT_APPLY_MIN_SCORE,
    respect_revoked: bool = False,
) -> Dict[str, Any]:
    """把候选主题写进关注列表（``source="derived"``，可一键撤销）。

    **不覆盖已有主题**：某主题已在关注列表里就跳过并记 ``already``——
    否则推导会篡改用户手动关注的 ``source``，撤销时把手动的也删掉。

    Args:
        respect_revoked: ``True`` 时跳过「用户曾撤销过」的主题（自动采纳用）。
            手动点「推导并采纳」时传 ``False``——用户主动点的就应该照做。
    """
    try:
        fm = manager if manager is not None else _default_focus_manager()
    except Exception as e:
        return {"ok": False, "reason": f"关注管理器不可用（{type(e).__name__}: {e}）",
                "applied": [], "skipped": [], "already": []}

    try:
        existing = set(fm.get_watched_narratives() or [])
    except Exception as e:
        return {"ok": False, "reason": f"读取已有关注失败（{type(e).__name__}: {e}）",
                "applied": [], "skipped": [], "already": []}

    revoked = set(_load_revoked()) if respect_revoked else set()

    applied: List[str] = []
    skipped: List[Dict[str, Any]] = []
    already: List[str] = []

    for t in topics:
        if hasattr(t, "to_dict"):
            row = t.to_dict()
        elif isinstance(t, dict):
            row = t
        else:
            skipped.append({"topic": str(t), "reason": "无法识别的条目类型"})
            continue

        topic = str(row.get("topic") or "").strip()
        if not topic:
            skipped.append({"topic": "", "reason": "主题名为空"})
            continue
        if topic in existing:
            already.append(topic)
            continue
        if topic in revoked:
            skipped.append({"topic": topic, "reason": "你曾撤销过该主题，自动采纳已跳过"})
            continue
        try:
            score = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score < min_score:
            skipped.append({"topic": topic, "reason": f"低于阈值 {min_score:.2f}（score={score:.2f}）"})
            continue
        try:
            fm.follow_narrative(topic, priority=score, source=SOURCE_DERIVED)
            applied.append(topic)
        except Exception as e:
            skipped.append({"topic": topic, "reason": f"{type(e).__name__}: {e}"})

    return {"ok": True, "reason": "", "applied": applied, "skipped": skipped,
            "already": sorted(already)}


def revoke_derived_topics(*, manager: Any = None) -> Dict[str, Any]:
    """撤销**所有** ``source="derived"`` 的关注主题（手动关注不受影响）。"""
    try:
        fm = manager if manager is not None else _default_focus_manager()
    except Exception as e:
        return {"ok": False, "reason": f"关注管理器不可用（{type(e).__name__}: {e}）",
                "removed": [], "failed": []}

    try:
        summary = fm.get_summary()
        items = list(getattr(summary, "narratives", None) or [])
    except Exception as e:
        return {"ok": False, "reason": f"读取关注列表失败（{type(e).__name__}: {e}）",
                "removed": [], "failed": []}

    removed: List[str] = []
    failed: List[Dict[str, str]] = []
    for item in items:
        if getattr(item, "source", "") != SOURCE_DERIVED:
            continue
        focus_id = getattr(item, "focus_id", "")
        try:
            fm.unfollow_narrative(focus_id)
            removed.append(focus_id)
        except Exception as e:
            failed.append({"topic": focus_id, "reason": f"{type(e).__name__}: {e}"})

    # 记进「已撤销」名单：否则自动采纳下次启动会把它们原样加回来
    revoked = _record_revoked(removed)
    return {"ok": True, "reason": "", "removed": removed, "failed": failed,
            "revoked": revoked}


def auto_apply_derived(*, max_topics: int = DEFAULT_MAX_TOPICS) -> Dict[str, Any]:
    """**自动采纳**入口（用户 2026-10-12 选定的档位）。

    推导 → 采纳为 ``source="derived"``。与手动采纳的区别：
    跳过「用户曾撤销过」的主题，否则每次启动都会把刚删掉的又加回来。

    任何一步失败都返回 ``{"ok": False, "reason": ...}``，由调用方决定是否记日志——
    这里不做静默兜底。
    """
    preview = derive_topics(max_topics=max_topics)
    if not preview.get("available"):
        return {"ok": False,
                "reason": preview.get("reason") or "推导不可用",
                "applied": [], "skipped": [], "already": [],
                "derived": preview}

    try:
        result = apply_derived_topics(preview["topics"], respect_revoked=True)
    except Exception as e:
        return {"ok": False, "reason": f"采纳失败（{type(e).__name__}: {e}）",
                "applied": [], "skipped": [], "already": [], "derived": preview}

    result["derived"] = preview
    return result


# ── UI 出口（纯 dict）──────────────────────────────────────────────────

def get_focus_advisor_summary(*, max_topics: int = DEFAULT_MAX_TOPICS) -> Dict[str, Any]:
    """给 UI 的单一入口：候选主题 + 当前已采纳的推导主题 + 手动主题。

    任何一步失败都降级成 ``available=False`` + ``reason``，**绝不兜底合成**。
    """
    result = derive_topics(max_topics=max_topics)

    applied_derived: List[Dict[str, Any]] = []
    manual_topics: List[Dict[str, Any]] = []
    manager_reason = ""
    try:
        fm = _default_focus_manager()
        summary = fm.get_summary()
        for item in (getattr(summary, "narratives", None) or []):
            row = {
                "topic": getattr(item, "focus_id", ""),
                "display_name": getattr(item, "display_name", ""),
                "source": getattr(item, "source", ""),
                "priority": round(float(getattr(item, "priority", 0.0) or 0.0), 4),
                "status": getattr(item, "status", ""),
            }
            if row["source"] == SOURCE_DERIVED:
                applied_derived.append(row)
            else:
                manual_topics.append(row)
    except Exception as e:
        manager_reason = f"关注列表读取失败（{type(e).__name__}: {e}）"

    result["applied_derived"] = applied_derived
    result["manual_topics"] = manual_topics
    if manager_reason:
        result["degraded"] = _dedupe(list(result.get("degraded") or []) + [manager_reason])
    return result


__all__ = [
    "DerivedTopic",
    "derive_topics",
    "apply_derived_topics",
    "revoke_derived_topics",
    "auto_apply_derived",
    "clear_revoked",
    "get_focus_advisor_summary",
    "SOURCE_DERIVED",
    "RELATION_LABELS",
    "TOO_BROAD_TOPICS",
    "DEFAULT_MAX_TOPICS",
    "DEFAULT_APPLY_MIN_SCORE",
]
