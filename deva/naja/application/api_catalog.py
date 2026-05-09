"""Naja API catalog.

Central, skill-friendly description of the local HTTP surface. The web layer
registers handlers elsewhere; this catalog exists so agents and skills can
discover what the running system can answer.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ApiEndpoint:
    path: str
    methods: List[str]
    group: str
    description: str
    skill_hint: str
    external_effect: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


ENDPOINTS: List[ApiEndpoint] = [
    ApiEndpoint("/api/health", ["GET"], "system", "健康检查", "确认 Naja 服务是否在线"),
    ApiEndpoint("/api/system/runtime", ["GET"], "system", "运行时监控数据", "查看系统总体运行状态"),
    ApiEndpoint("/api/system/modules", ["GET"], "system", "模块状态", "检查核心模块是否初始化"),
    ApiEndpoint("/api/system/persistent", ["GET"], "system", "持久化状态", "查看保存/恢复状态"),
    ApiEndpoint("/api/app/container", ["GET"], "system", "应用容器状态", "诊断启动装配状态"),
    ApiEndpoint("/api/registry/status", ["GET"], "system", "注册表状态", "排查单例/组件注册问题"),
    ApiEndpoint("/api/query/state", ["GET"], "system", "QueryState 快照", "查看系统当前查询态"),
    ApiEndpoint("/api/events/query", ["GET"], "events", "事件查询", "检索事件总线历史"),
    ApiEndpoint("/api/events/stats", ["GET"], "events", "事件统计", "观察事件流量和类型分布"),
    ApiEndpoint("/api/market/hotspot", ["GET"], "market", "A股+美股市场热点", "看热点板块、个股、热点转移"),
    ApiEndpoint("/api/market/hotspot/stream", ["GET"], "market", "市场热点 SSE", "前端/客户端订阅热点推送"),
    ApiEndpoint("/api/radar/events", ["GET"], "radar", "雷达事件", "查看雷达检测到的市场/新闻事件"),
    ApiEndpoint("/api/news/stream", ["GET"], "radar", "新闻 SSE", "订阅高重要性新闻流"),
    ApiEndpoint("/api/cognition/memory", ["GET"], "cognition", "认知记忆报告", "查看 Naja 记住了什么"),
    ApiEndpoint("/api/cognition/topics", ["GET"], "cognition", "主题信号", "查看近期主题变化"),
    ApiEndpoint("/api/cognition/attention", ["GET"], "cognition", "注意力提示", "查看认知层给注意力系统的提示"),
    ApiEndpoint("/api/cognition/thought", ["GET"], "cognition", "思想报告", "查看认知系统自然语言总结"),
    ApiEndpoint("/api/knowledge/list", ["GET"], "knowledge", "知识列表", "查看学习到的因果知识"),
    ApiEndpoint("/api/knowledge/stats", ["GET"], "knowledge", "知识统计", "查看观察/验证/正式知识数量"),
    ApiEndpoint("/api/knowledge/detail", ["GET"], "knowledge", "知识详情", "按 id 查看知识条目"),
    ApiEndpoint("/api/knowledge/trading", ["GET"], "knowledge", "交易可用知识", "查看可注入交易决策的知识"),
    ApiEndpoint("/api/knowledge/action", ["POST"], "knowledge", "知识动作", "手动确认/调整知识状态"),
    ApiEndpoint("/api/datasource/list", ["GET"], "config", "数据源列表", "查看 Naja 当前数据源"),
    ApiEndpoint("/api/strategy/list", ["GET"], "strategy", "策略列表", "查看策略配置和状态"),
    ApiEndpoint("/api/bandit/stats", ["GET"], "strategy", "Bandit 统计", "查看自适应策略学习表现"),
    ApiEndpoint("/api/alaya/status", ["GET"], "cognition", "阿赖耶识状态", "查看长期记忆/顿悟系统状态"),
    ApiEndpoint("/api/attention/manas/state", ["GET"], "attention", "末那识状态", "查看天时地利人和融合结果"),
    ApiEndpoint("/api/attention/harmony", ["GET"], "attention", "和谐度", "查看行动/观望倾向"),
    ApiEndpoint("/api/attention/decision", ["GET"], "attention", "注意力决策", "查看当前决策输出"),
    ApiEndpoint("/api/attention/conviction", ["GET"], "attention", "确信度", "查看当前 conviction"),
    ApiEndpoint("/api/attention/conviction/timing", ["GET"], "attention", "时机确信", "查看加仓/行动时机"),
    ApiEndpoint("/api/attention/conviction/should-add", ["GET"], "attention", "是否加仓", "询问注意力层是否支持加仓"),
    ApiEndpoint("/api/attention/portfolio/summary", ["GET"], "attention", "持仓摘要", "查看组合层摘要"),
    ApiEndpoint("/api/attention/position/metrics", ["GET"], "attention", "持仓指标", "查看单/多持仓指标"),
    ApiEndpoint("/api/attention/tracking/hotspot", ["GET"], "attention", "注意力追踪热点", "查看注意力追踪的热点"),
    ApiEndpoint("/api/attention/tracking/stats", ["GET"], "attention", "追踪统计", "查看注意力追踪统计"),
    ApiEndpoint("/api/attention/blind-spots", ["GET"], "attention", "盲点", "查看系统未覆盖或低确信区域"),
    ApiEndpoint("/api/attention/fusion", ["GET"], "attention", "融合结果", "查看多源注意力融合"),
    ApiEndpoint("/api/attention/focus", ["GET"], "attention", "关注焦点", "查看当前焦点"),
    ApiEndpoint("/api/attention/narrative-block-matrix", ["GET"], "attention", "叙事-板块矩阵", "看叙事如何映射板块"),
    ApiEndpoint("/api/attention/report", ["GET"], "attention", "注意力报告", "生成注意力系统报告"),
    ApiEndpoint("/api/attention/lab/status", ["GET"], "attention", "实验室状态", "查看 lab/replay 状态"),
    ApiEndpoint("/api/attention/liquidity", ["GET"], "attention", "流动性", "查看流动性认知"),
    ApiEndpoint("/api/attention/strategy/top-symbols", ["GET"], "attention", "策略关注个股", "查看策略层 top symbols"),
    ApiEndpoint("/api/attention/strategy/top-blocks", ["GET"], "attention", "策略关注板块", "查看策略层 top blocks"),
    ApiEndpoint("/api/attention/context", ["GET"], "attention", "注意力上下文", "给 agent/LLM 的上下文入口"),
    ApiEndpoint("/api/naja/agent", ["GET"], "agent", "Naja Agent 能力", "查看 agent 技能和 API 目录"),
    ApiEndpoint("/api/naja/skill", ["POST"], "agent", "Naja Skill 调用", "通过 skill 方式调用 Naja"),
    ApiEndpoint("/api/naja/api-catalog", ["GET"], "agent", "API 能力目录", "查看全系统 API 端点目录"),
    ApiEndpoint("/api/naja/ask", ["GET", "POST"], "agent", "兼容问答入口", "直接问 Naja"),
    ApiEndpoint("/api/naja/digest", ["GET"], "agent", "市场学习汇报", "获取 Naja 市场值班官 digest"),
    ApiEndpoint("/api/naja/digest/send", ["POST"], "agent", "发送市场学习汇报", "发送到钉钉/手机", external_effect=True),
]


def get_api_catalog(group: Optional[str] = None) -> Dict[str, Any]:
    endpoints = ENDPOINTS
    if group:
        normalized = group.strip().lower()
        endpoints = [ep for ep in endpoints if ep.group == normalized]

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for endpoint in endpoints:
        groups.setdefault(endpoint.group, []).append(endpoint.to_dict())

    return {
        "total": len(endpoints),
        "groups": groups,
        "group_names": sorted(groups.keys()),
    }

