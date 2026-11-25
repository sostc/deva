"""
geo_risk P1 存储层验收测试

三条冻结口径（对应 notes/2026-11-23 报告）：
    A. 写线程恒为 1
    B. 并发写不丢条、不报错、顺序可审计
    C. 字段冻结（PRAGMA table_info 与 FROZEN_COLUMNS 逐列一致）
"""

import sqlite3
import threading

import pytest

from deva.naja.geo_risk.seeds import load_seed
from deva.naja.geo_risk.store import FROZEN_COLUMNS, WRITER_THREAD_NAME, GeoRiskDB


@pytest.fixture
def db(tmp_path):
    d = GeoRiskDB(tmp_path / "geo_risk.db")
    yield d
    d.close()


def _writer_threads():
    return [t for t in threading.enumerate() if t.name == WRITER_THREAD_NAME]


def _row(i: int, tag: str = "t") -> dict:
    return {
        "evidence_id": f"ev_{tag}_{i}",
        "subject_type": "project",
        "subject_id": f"prj_{tag}",
        "source": "fixture.test",
        "url": f"fixture://test/{tag}/{i}",
        "quote": f"第 {i} 条（fixture）",
        "event_hint": "test",
    }


# --------------------------------------------------------------- C 字段冻结
@pytest.mark.parametrize("table", list(FROZEN_COLUMNS))
def test_schema_frozen(db, table):
    rows = db.query(f"PRAGMA table_info({table})")
    assert [r["name"] for r in rows] == FROZEN_COLUMNS[table]


def test_unknown_field_is_rejected(db):
    bad = {**_row(1), "unexpected_field": 1}
    with pytest.raises(ValueError, match="字段已冻结"):
        db.add_evidence([bad]).result()


# ------------------------------------------------------------- A 写线程恒为 1
def test_writer_thread_is_single(db):
    assert len(_writer_threads()) == 1, "初始化后应只有一条写线程"
    assert db.stats()["writer_threads"] == 1

    # 大量写入期间也不能分裂出第二条
    for batch in range(20):
        db.add_evidence([_row(i, tag=f"b{batch}") for i in range(25)]).result()
        assert len(_writer_threads()) == 1

    assert db.count("evidence") == 500
    assert db.stats()["writer_threads"] == 1

    db.close()
    assert _writer_threads() == [], "close() 之后写线程必须退出"


# ------------------------------------------------- B 并发写：不丢、不报错、顺序可审计
def test_concurrent_writes_no_loss(db):
    threads, per_thread = 8, 50
    errors: list = []

    def worker(tid: int):
        try:
            db.add_evidence([_row(i, tag=f"c{tid}") for i in range(per_thread)]).result()
        except BaseException as exc:  # noqa: BLE001
            errors.append((tid, repr(exc)))

    ts = [threading.Thread(target=worker, args=(t,)) for t in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)

    assert not errors, f"并发写出现异常: {errors}"
    assert db.count("evidence") == threads * per_thread

    rows = db.query("SELECT evidence_id, write_seq FROM evidence ORDER BY write_seq")
    ids = [r["evidence_id"] for r in rows]
    seqs = [r["write_seq"] for r in rows]
    assert len(set(ids)) == threads * per_thread, "有条目丢失"
    assert seqs == list(range(1, threads * per_thread + 1)), "write_seq 应连续且可审计"


def test_failed_job_does_not_break_writer(db):
    def boom(conn):
        conn.execute("INSERT INTO evidence (evidence_id, write_seq, subject_type, subject_id,"
                     " source, url, retrieved_at, content_hash) VALUES"
                     " ('ev_bad', 1, 'project', 'p', 's', 'u', 'now', 'h')")
        raise RuntimeError("故意失败")

    with pytest.raises(RuntimeError, match="故意失败"):
        db.submit(boom, label="boom").result()

    # 失败后写线程仍然可用，且没有留下脏数据
    assert db.count("evidence") == 0
    assert db.add_evidence([_row(1)]).result() == 1
    assert db.count("evidence") == 1


# ------------------------------------------------------------ evidence 只增不改
def test_evidence_is_append_only(db):
    db.add_evidence([_row(1)]).result()

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.submit(lambda conn: conn.execute("UPDATE evidence SET quote = '篡改'")).result()

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.submit(lambda conn: conn.execute("DELETE FROM evidence")).result()

    assert db.count("evidence") == 1


# ------------------------------------------------------------- 快照表可更新但保 created_at
def test_snapshot_upsert_keeps_created_at(db):
    db.upsert_entities([{
        "entity_id": "ent_x", "kind": "company", "canonical_name": "X 公司",
        "aliases": ["X"], "created_at": "2026-01-01T00:00:00+08:00",
    }]).result()
    first = db.get_entity("ent_x")
    assert first["aliases"] == ["X"]

    db.upsert_entities([{
        "entity_id": "ent_x", "kind": "company", "canonical_name": "X 公司（更名）",
        "updated_at": "2026-02-01T00:00:00+08:00",
    }]).result()
    second = db.get_entity("ent_x")
    assert second["canonical_name"] == "X 公司（更名）"
    assert second["created_at"] == first["created_at"], "快照更新不得改写 created_at"


# ------------------------------------------------------------------- 种子用例
def test_seed_same_project_two_sources(db):
    counts = load_seed(db)
    assert counts == {"entities": 10, "projects": 5, "evidence": 9}

    ytl = db.get_project("prj_ytl_johor")
    assert ytl is not None

    ev = db.list_evidence("project", "prj_ytl_johor")
    assert len(ev) == 2, "同一项目应能聚合两条不同来源的证据"
    assert {e["source"] for e in ev} == {
        "fixture.financing_news",
        "fixture.operator_announcement",
    }
    assert len({e["evidence_id"] for e in ev}) == 2
    # 别名可在实体上直接读到
    assert "杨忠礼电力" in db.get_entity("ent_ytl_power")["aliases"]
