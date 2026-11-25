"""
geo_risk —— 东南亚 AI 算力政策与金融风险监控

分层（对应 notes/2026-11-23 报告）：
- store：一个 sqlite 库、一条写线程（``geo-risk-db-writer``），写入排队；
- entities / events：别名匹配、跨来源同一项目归并（纯派生视图）；
- collectors：Federal Register / RSS / GPU 定价等采集器，只写 evidence；
- model：LTV / DSCR / 压力测试 / 评级，纯函数，不读库、不进实时 tick。

设计约束（对应报告 §2.2、§5）：
- 不使用 NB / SqliteDict：每开一张 NB 表就会多一条永不回收的写线程。
- 一个库只允许一条写线程；所有写请求进同一队列串行执行。
- entity / project 是当前快照；evidence 是历史轨迹，append-only。
"""

from .store import GeoRiskDB, get_db, close_all

__all__ = ["GeoRiskDB", "get_db", "close_all"]
