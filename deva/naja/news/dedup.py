"""新闻去重（呈现前折叠）——把同一件事的多条记录合成一条，只保留条数。

为什么需要它
------------
金十每发一条快讯，会**中文先发、英文翻译版 4~16 秒后补发**，两条是独立的
flash（``id`` 也不同），于是新闻池里同一条事件有两行。托盘的 12 个名额
实测有近一半被这种成对重复吃掉；「今日新闻消化」面板同理。

而原有去重（``triage._dedupe``）的判据是**标题字符串完全相同**——在这批
数据上命中率为 0（``scanned 101 == deduped 101``，一条都没去掉，且不报错）。
所以本模块换判据：**不用字符相似度**（中英两版标题的字符交集是 0，
Jaccard 恒低于 0.5），改用三条**结构性**规则。

三条规则（全部是整数/字符串运算，不加载模型、不联网）
------------------------------------------------------
=========== ================================================== ==========
规则         判据                                                抓什么
=========== ================================================== ==========
``L1``      规范化后标题全等（去序号/【】/``金十数据X月X日讯``）    同一条重发
``L2``      同语言 + 前缀包含（短侧 ≥12 字）                      截断版 / 追加版
``L3``      **中英一对一配对**：时间窗 ≤20s + 全局最小间隔        ★中英双版
=========== ================================================== ==========

``L3`` 是主力（实测 22~23 组、零错配）。它成立的前提是**发布流水线的时间
结构**——同一条事件的两种语言版本几乎同时落地，这比"标题长得像"可靠得多。
``L1``/``L2`` 在当前数据上命中 0 次，成本接近 0，留作重发/截断的安全网。

刻意**不做**的
--------------
* **近似指纹（SimHash）**：实测 113 条只多合 1 条，耗时却是 10 倍，
  还会把统计局发布会的两条**不同要点**误合成一条（``内需贡献率超七成`` /
  ``内需逐步改善``）。留着代码路径（``enable_fuzzy``），默认关。
* **语义聚类**：同事件但标题字面零交集（``泽连斯基指特朗普施压投降`` vs
  ``美恢复对乌情报分享``）需要向量模型，不属于"轻量本地"，不做。

三条守约
--------
1. **不改数据**：只在呈现前折叠，新闻池/评分/决策链一行不动，随时可回滚。
2. **合了必须留痕**：返回 ``dup_count`` 与 ``stats["merged"]``，UI 上要能看见
   "折叠了几条"——否则又变成"看起来正常"的静默失效。
3. **中文优先**：代表条优先取中文版（阅读体验），英文版只作为证据计入条数。
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# ── 归一化用到的正则（模块级编译一次，避免每条新闻重复编译）──────────────
_SEQ_PREFIX = re.compile(r"^\s*\d+[.、)]\s*")
_JIN10_BOILERPLATE = re.compile(r"金十数据\s*\d+月\d+日\s*讯[，,:：]?")
_BRACKETS = re.compile(r"[【】\[\]（）()《》〈〉\"'“”‘’]")
_NON_WORD = re.compile(r"[^\w\u4e00-\u9fff%]+", re.U)
_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")

_ENV_VAR = "NAJA_NEWS_DEDUP"

#: 语言标记
LANG_ZH = "zh"
LANG_EN = "en"
LANG_UNKNOWN = "?"

#: 合并规则的标识（stats / 留痕用）
RULE_EXACT = "L1"
RULE_PREFIX = "L2"
RULE_FUZZY = "L2f"
RULE_XLANG = "L3"


@dataclass(frozen=True)
class DedupConfig:
    """折叠口径。冻结 + 可被环境变量覆盖，便于不改代码地关掉某一层。"""

    #: L3 中英配对的时间窗（秒）。实测同一事件的两版相隔 4~16 秒。
    xlang_gap: float = 20.0
    #: L2 前缀包含判定的最短长度（太短的标题前缀容易误合）
    prefix_min: int = 12
    #: L1/L2 的时间窗（秒）：同一标题只在 6 小时内视为重复，
    #: 避免把「每天中午都发的固定栏目」当成一条
    same_title_window: float = 6 * 3600.0
    enable_exact: bool = True
    enable_prefix: bool = True
    #: 近似指纹（SimHash）。默认关——见模块 docstring
    enable_fuzzy: bool = False
    fuzzy_ham: int = 3
    fuzzy_min_ratio: float = 0.85
    #: 代表条优先语言
    prefer_lang: str = LANG_ZH
    origin: str = "default"
    degraded: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xlang_gap": self.xlang_gap,
            "prefix_min": self.prefix_min,
            "same_title_window": self.same_title_window,
            "enable_exact": self.enable_exact,
            "enable_prefix": self.enable_prefix,
            "enable_fuzzy": self.enable_fuzzy,
            "prefer_lang": self.prefer_lang,
            "origin": self.origin,
            "degraded": list(self.degraded),
        }

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "DedupConfig":
        """``NAJA_NEWS_DEDUP=0`` 一键关掉；``NAJA_NEWS_DEDUP_FUZZY=1`` 开近似层。

        解析失败不抛、不静默改口径：回退默认并把原因写进 ``degraded``。
        """
        env = env if env is not None else os.environ
        raw = (env.get(_ENV_VAR) or "").strip()
        if raw in ("0", "false", "False", "off"):
            return cls(enable_exact=False, enable_prefix=False,
                       enable_fuzzy=False, origin=f"env:{_ENV_VAR}=off")
        fuzzy = (env.get(_ENV_VAR + "_FUZZY") or "").strip()
        if fuzzy in ("1", "true", "True", "on"):
            return cls(enable_fuzzy=True, origin=f"env:{_ENV_VAR}_FUZZY")
        if raw:
            return cls(degraded=(f"{_ENV_VAR}={raw!r} 无法识别（只认 0/1），已用默认",))
        return cls()


# ── 基础工具 ────────────────────────────────────────────────────────────


def normalize_title(title: Any) -> str:
    """标题归一化：去序号、去``【】``、去金十模板语、去标点空白、小写。

    只做**不影响语义**的搬运，所以两条归一化后相等 = 同一条内容。
    """
    text = unicodedata.normalize("NFKC", str(title or ""))
    text = _SEQ_PREFIX.sub("", text)
    text = _JIN10_BOILERPLATE.sub("", text)
    text = _BRACKETS.sub("", text)
    return _NON_WORD.sub("", text.lower())


def detect_lang(text: Any) -> str:
    """字数比判语言。中文里夹英文公司名仍判 ``zh``（拉丁字母要超过汉字 2 倍）。

    ❗不能用"纯字母大写 = 股票代码"那类判据——``'XYZ'.isupper()`` 为真，
    会把任意英文单词当代码（见 MEMORY 里的历史事故）。这里只判语言。
    """
    s = str(text or "")
    latin = len(_LATIN.findall(s))
    cjk = len(_CJK.findall(s))
    if not latin and not cjk:
        return LANG_UNKNOWN
    return LANG_EN if latin > cjk * 2 else LANG_ZH


def _as_ts(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _union_find(size: int):
    parent = list(range(size))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[rb] = ra
        return True

    return find, union


# ── 核心：找出哪些记录属于同一件事 ──────────────────────────────────────


def find_groups(
    records: Sequence[Mapping[str, Any]],
    *,
    config: Optional[DedupConfig] = None,
    title_key: str = "title",
    time_key: str = "timestamp",
) -> Tuple[List[List[int]], Dict[str, Any]]:
    """把记录按同一事件分组，返回 ``(groups, stats)``。

    Args:
        records: 每条至少要有标题。缺标题的记录**不参与合并**，单独成组
            （宁可多显示一条，也不要凭空把两条无标题记录粘在一起）。

    Returns:
        ``groups`` 每个元素是原记录的下标列表（顺序 = 组内最靠前的下标升序），
        调用方据此挑代表条、算 dup_count。
    """
    cfg = config if config is not None else DedupConfig.from_env()
    total = len(records)
    titles: List[str] = []
    norms: List[str] = []
    langs: List[str] = []
    stamps: List[float] = []

    for rec in records:
        raw_title = str(rec.get(title_key) or "")
        titles.append(raw_title)
        norms.append(normalize_title(raw_title))
        langs.append(detect_lang(raw_title))
        stamps.append(_as_ts(rec.get(time_key)))

    find, union = _union_find(total)
    by_rule: Dict[str, int] = {RULE_EXACT: 0, RULE_PREFIX: 0,
                               RULE_FUZZY: 0, RULE_XLANG: 0}

    # ── L1 精确：归一化后全等 + 时间窗内 ──────────────────────────────
    if cfg.enable_exact:
        buckets: Dict[str, List[int]] = {}
        for i, key in enumerate(norms):
            if not key:
                continue
            hit = None
            for j in buckets.get(key, ()):  # 最多几条，线性扫描足够
                if abs(stamps[i] - stamps[j]) <= cfg.same_title_window:
                    hit = j
                    break
            if hit is None:
                buckets.setdefault(key, []).append(i)
            elif union(hit, i):
                by_rule[RULE_EXACT] += 1

    # ── L2 前缀包含：同语言 + 短侧够长 + 时间窗内 ────────────────────
    # 用"前 prefix_min 字"做桶，避免 O(n²) 全量两两比较。
    if cfg.enable_prefix:
        buckets = {}
        for i, key in enumerate(norms):
            if len(key) < cfg.prefix_min:
                continue
            buckets.setdefault(key[: cfg.prefix_min], []).append(i)
        for members in buckets.values():
            for a_pos in range(len(members)):
                a = members[a_pos]
                for b in members[a_pos + 1:]:
                    if find(a) == find(b) or langs[a] != langs[b]:
                        continue
                    if abs(stamps[a] - stamps[b]) > cfg.same_title_window:
                        continue
                    short, long_ = (norms[a], norms[b]) if len(norms[a]) <= len(norms[b]) \
                        else (norms[b], norms[a])
                    # 桶已保证前 prefix_min 字相同，这里只确认"短的是长的前缀"
                    if long_.startswith(short) and union(a, b):
                        by_rule[RULE_PREFIX] += 1

    # ── L2f 近似指纹：默认关（见 docstring 的取舍）────────────────────
    if cfg.enable_fuzzy:
        from ._simhash import hamming, simhash64  # 惰性导入，关闭时零成本

        prints = [simhash64(n) if len(n) >= 8 else None for n in norms]
        reps: List[int] = []
        for i, sig in enumerate(prints):
            if sig is None:
                continue
            hit = None
            for r in reps:
                if find(r) == find(i) or langs[r] != langs[i]:
                    continue
                la, lb = len(norms[r]), len(norms[i])
                if min(la, lb) / max(la, lb) < cfg.fuzzy_min_ratio:
                    continue
                if hamming(prints[r], sig) <= cfg.fuzzy_ham:
                    hit = r
                    break
            if hit is None:
                reps.append(i)
            elif union(hit, i):
                by_rule[RULE_FUZZY] += 1

    # ── L3 中英一对一：时间窗 + 全局最小间隔，双方各只配一次 ──────────
    if cfg.xlang_gap > 0:
        en = sorted((i for i in range(total) if langs[i] == LANG_EN),
                    key=lambda i: stamps[i])
        zh = sorted((i for i in range(total) if langs[i] == LANG_ZH),
                    key=lambda i: stamps[i])
        cands: List[Tuple[float, int, int]] = []
        lo = 0
        for i in en:
            ti = stamps[i]
            while lo < len(zh) and stamps[zh[lo]] < ti - cfg.xlang_gap:
                lo += 1
            k = lo
            while k < len(zh) and stamps[zh[k]] <= ti + cfg.xlang_gap:
                cands.append((abs(stamps[zh[k]] - ti), i, zh[k]))
                k += 1
        cands.sort()
        used_en, used_zh = set(), set()
        for _gap, i, j in cands:
            # 一对一：一条英文只折叠一条中文，反向同理。
            # 少了这层约束会"链式传染"——一处错配把无关新闻拖进同一簇。
            if i in used_en or j in used_zh or find(i) == find(j):
                continue
            if union(i, j):
                used_en.add(i)
                used_zh.add(j)
                by_rule[RULE_XLANG] += 1

    # ── 收口：按组内最小下标排序，保持输入顺序 ───────────────────────
    grouped: Dict[int, List[int]] = {}
    for i in range(total):
        grouped.setdefault(find(i), []).append(i)
    groups = sorted(grouped.values(), key=lambda g: g[0])

    stats: Dict[str, Any] = {
        "input": total,
        "output": len(groups),
        "merged": total - len(groups),
        "by_rule": by_rule,
        "untitled": sum(1 for n in norms if not n),
        "config": cfg.to_dict(),
    }
    return groups, stats


def pick_representative(
    records: Sequence[Mapping[str, Any]],
    members: Sequence[int],
    *,
    config: Optional[DedupConfig] = None,
    title_key: str = "title",
    time_key: str = "timestamp",
) -> int:
    """挑代表条：**中文优先** → 同语言取最新的一条。

    中文优先是用户选定的口径：菜单和面板是给人看的，英文版只作为
    "这条还有一版"的证据计入条数，不该占正位。
    """
    cfg = config if config is not None else DedupConfig.from_env()
    prefer = cfg.prefer_lang

    def rank(i: int) -> Tuple[int, float]:
        lang = detect_lang(records[i].get(title_key))
        return (0 if lang == prefer else 1, -_as_ts(records[i].get(time_key)))

    return min(members, key=rank)


def collapse(
    items: Sequence[Mapping[str, Any]],
    *,
    config: Optional[DedupConfig] = None,
    title_key: str = "title",
    time_key: str = "timestamp",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """便利封装：返回**折叠后的 dict 副本**（带 ``dup_count`` / ``dup_langs``）。

    不动入参；调用方拿到的是新 dict，可以随意加字段。
    """
    groups, stats = find_groups(items, config=config,
                                title_key=title_key, time_key=time_key)
    out: List[Dict[str, Any]] = []
    for members in groups:
        rep = items[pick_representative(items, members, config=config,
                                        title_key=title_key, time_key=time_key)]
        row = dict(rep)
        row["dup_count"] = len(members)
        row["dup_langs"] = sorted({detect_lang(items[i].get(title_key))
                                   for i in members})
        out.append(row)
    return out, stats


def format_dup_suffix(dup_count: Any) -> str:
    """``×N`` 后缀——只显示条数，不显示语言/来源（用户选定的呈现口径）。"""
    try:
        n = int(dup_count or 1)
    except (TypeError, ValueError):
        return ""
    return f" ×{n}" if n > 1 else ""


__all__ = [
    "DedupConfig",
    "LANG_EN",
    "LANG_UNKNOWN",
    "LANG_ZH",
    "RULE_EXACT",
    "RULE_FUZZY",
    "RULE_PREFIX",
    "RULE_XLANG",
    "collapse",
    "detect_lang",
    "find_groups",
    "format_dup_suffix",
    "normalize_title",
    "pick_representative",
]
