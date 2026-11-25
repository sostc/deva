"""
geo_risk 表结构：entity / project / evidence（P1 冻结）+ series（P3 时序）

❗P1 三表字段已冻结。`test_schema_frozen` 会逐列比对，任何新增/改名都必须同步改
`FROZEN_COLUMNS`，不允许悄悄漂移。`series` 是后加的独立表，不进 P1 冻结集合。

存储约定（对应 notes/2026-11-23 报告 §2.2）：
- entity / project 是「当前快照」，允许按主键 upsert；
- evidence 是「历史轨迹」，append-only：UPDATE / DELETE 由触发器直接 ABORT；
  `write_seq` 由写线程单调分配，事后可按它审计写入顺序；
- 同一 url + 同一内容摘要只允许存在一条 evidence（去重键在 DDL 的 UNIQUE 里）；
- series 是模型输入的 append-only 时序：只写真实抽取到的字段，缺失就缺失，
  绝不用 0 或默认值把「不知道」伪装成「知道」。
"""

WRITER_THREAD_NAME = "geo-risk-db-writer"

ENTITY_KINDS = ("company", "project", "datacenter", "bank", "regulator", "other")

#: 冻结列（顺序即建表顺序，PRAGMA table_info 会按这个顺序返回）
FROZEN_COLUMNS = {
    "entity": [
        "entity_id",
        "kind",
        "canonical_name",
        "country",
        "ticker",
        "cik",
        "parent_id",
        "aliases",
        "created_at",
        "updated_at",
    ],
    "project": [
        "project_id",
        "operator_entity_id",
        "name",
        "site",
        "country",
        "state",
        "capacity_mw",
        "gpu_count",
        "customer_mix",
        "financing_refs",
        "status",
        "created_at",
        "updated_at",
    ],
    "evidence": [
        "evidence_id",
        "write_seq",
        "subject_type",
        "subject_id",
        "source",
        "url",
        "published_at",
        "retrieved_at",
        "quote",
        "content_hash",
        "event_hint",
    ],
}

#: JSON 列：写入前统一序列化，读出后由调用方自行反序列化
JSON_COLUMNS = {
    "entity": ("aliases",),
    "project": ("customer_mix", "financing_refs"),
}

DDL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS entity (
    entity_id      TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    country        TEXT,
    ticker         TEXT,
    cik            TEXT,
    parent_id      TEXT,
    aliases        TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project (
    project_id        TEXT PRIMARY KEY,
    operator_entity_id TEXT NOT NULL,
    name              TEXT NOT NULL,
    site              TEXT,
    country           TEXT,
    state             TEXT,
    capacity_mw       REAL,
    gpu_count         INTEGER,
    customer_mix      TEXT NOT NULL DEFAULT '{}',
    financing_refs    TEXT NOT NULL DEFAULT '[]',
    status            TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- history 表：只增不改。write_seq 由写线程分配，用于审计写入顺序。
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id  TEXT PRIMARY KEY,
    write_seq    INTEGER NOT NULL UNIQUE,
    subject_type TEXT NOT NULL,
    subject_id   TEXT NOT NULL,
    source       TEXT NOT NULL,
    url          TEXT NOT NULL,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    quote        TEXT,
    content_hash TEXT NOT NULL,
    event_hint   TEXT,
    UNIQUE (content_hash, subject_type, subject_id, url)
);

CREATE INDEX IF NOT EXISTS idx_evidence_subject ON evidence (subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_evidence_hash ON evidence (content_hash);

CREATE TRIGGER IF NOT EXISTS evidence_no_update
BEFORE UPDATE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence 是 append-only：禁止 UPDATE');
END;

CREATE TRIGGER IF NOT EXISTS evidence_no_delete
BEFORE DELETE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence 是 append-only：禁止 DELETE');
END;

-- model 输入的时间序列：只写真实抽取到的字段，缺就缺失，绝不填 0 伪装事实。
-- 主键含 source_id，同一来源重复抓取是覆盖不是新增；审计靠 observed_at。
CREATE TABLE IF NOT EXISTS series (
    series_id    TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    metric       TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    value        TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    observed_at  TEXT NOT NULL,
    quality      TEXT
);

CREATE INDEX IF NOT EXISTS idx_series_project_metric ON series (project_id, metric, as_of);
CREATE TRIGGER IF NOT EXISTS series_no_update
BEFORE UPDATE ON series
BEGIN
    SELECT RAISE(ABORT, 'series 是 append-only：禁止 UPDATE');
END;

CREATE TRIGGER IF NOT EXISTS series_no_delete
BEFORE DELETE ON series
BEGIN
    SELECT RAISE(ABORT, 'series 是 append-only：禁止 DELETE');
END;
"""
