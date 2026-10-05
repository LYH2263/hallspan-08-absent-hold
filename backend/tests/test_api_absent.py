"""API 级测试：缺考策略切换/缺考标记与占用账、最新方案、统计的原子一致性。"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Candidate, Hall, PaperSet, SeatPlan


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = factory()
    hall = Hall(code="H1", name="室", rows=4, cols=4, min_manhattan=2)  # 策略未配置
    p1 = PaperSet(code="A", title="A卷")
    p2 = PaperSet(code="B", title="B卷")
    db.add_all([hall, p1, p2])
    db.flush()
    for i in range(1, 7):
        db.add(Candidate(
            hall_id=hall.id, name=f"考{i}", ticket_no=f"T{i}",
            paper_id=p1.id if i % 2 else p2.id, absent=(i == 6),
        ))
    db.commit()
    db.close()

    # 可注入的提交故障：置 True 后，flush 已落库到事务、但提交点抛错，
    # 用来验证“保存失败时策略字段、占用账、最新方案、统计整体回滚”。
    hooks = {"fail_commit": False}

    def override_get_db():
        s = factory()
        original_commit = s.commit

        def maybe_failing_commit():
            s.flush()  # 占用账/新方案行已写入事务
            if hooks["fail_commit"]:
                raise RuntimeError("disk full at commit")
            original_commit()

        s.commit = maybe_failing_commit
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield factory, hooks
    app.dependency_overrides.clear()


@pytest.fixture()
def factory(session_factory):
    return session_factory[0]


@pytest.fixture()
def hooks(session_factory):
    return session_factory[1]


@pytest.fixture()
def client(session_factory):
    return TestClient(app)


def _hall_strategy(factory):
    db = factory()
    val = db.get(Hall, 1).absent_strategy
    db.close()
    return val


def test_default_unconfigured_is_release(client):
    res = client.post("/api/seating/run?hall_id=1")
    assert res.status_code == 200
    body = res.json()
    assert body["absent_strategy"] == "release"
    # 缺考生 id=6 占用账无行
    assert all(a["candidate_id"] != 6 for a in body["assignments"])
    assert body["stats"]["occupied"] == body["stats"]["seated"]
    assert body["stats"]["held_absent"] == 0
    # 未排名单不得含缺考
    assert all(u["id"] != 6 for u in body["unplaced"])
    absent6 = [a for a in body["absent"] if a["id"] == 6][0]
    assert absent6["held"] is False and absent6["status"] == "released"


def test_switch_to_hold_rewrites_ledger_map_stats(client):
    client.post("/api/seating/run?hall_id=1")
    res = client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "hold"})
    assert res.status_code == 200
    body = res.json()
    assert body["absent_strategy"] == "hold"
    held = [a for a in body["assignments"] if a["candidate_id"] == 6]
    assert len(held) == 1 and held[0]["status"] == "reserved_absent"
    assert body["stats"]["occupied"] == body["stats"]["seated"] + 1
    assert body["stats"]["held_absent"] == 1

    # 最新方案（图/占用账/统计读取源）已按新策略重写，不残留旧策略空出结果
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert latest["absent_strategy"] == "hold"
    assert any(a["candidate_id"] == 6 and a["status"] == "reserved_absent" for a in latest["assignments"])
    stats = client.get("/api/seating/stats?hall_id=1").json()
    assert stats["occupied"] == body["stats"]["occupied"] and stats["held_absent"] == 1
    v = client.get("/api/seating/violations?hall_id=1").json()
    assert v["absent_strategy"] == "hold"
    assert all(u["id"] != 6 for u in v["unplaced"])


def test_hold_then_release_same_absent_row_disappears(client):
    client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "hold"})
    res = client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "release"})
    body = res.json()
    assert body["absent_strategy"] == "release"
    assert all(a["candidate_id"] != 6 for a in body["assignments"])
    assert body["stats"]["held_absent"] == 0
    assert body["stats"]["occupied"] == body["stats"]["seated"]
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert all(a["candidate_id"] != 6 for a in latest["assignments"])


def test_invalid_strategy_rejected_without_change(client, factory):
    res = client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "banana"})
    assert res.status_code == 422
    assert _hall_strategy(factory) is None


def test_strategy_save_failure_rolls_back_everything(client, factory, hooks):
    # 先有一份 release 基线方案
    base = client.post("/api/seating/run?hall_id=1").json()

    hooks["fail_commit"] = True
    res = client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "hold"})
    assert res.status_code == 500
    hooks["fail_commit"] = False

    # 策略字段回到保存前
    assert _hall_strategy(factory) is None
    # 最新方案仍是旧策略结果（flush 进去的新方案行随回滚作废，不残留旧策略占格）
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert latest["id"] == base["id"]
    assert latest["absent_strategy"] == "release"
    assert all(a["candidate_id"] != 6 for a in latest["assignments"])
    assert latest["stats"]["occupied"] == base["stats"]["occupied"]
    assert latest["stats"]["held_absent"] == 0
    # 方案行数没有增加
    db = factory()
    plan_count = db.query(SeatPlan).count()
    db.close()
    assert plan_count == 1


def test_absent_toggle_atomic_and_reranks(client, factory, hooks):
    client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "hold"})
    res = client.post("/api/candidates/3/absent", json={"absent": True})
    assert res.status_code == 200
    body = res.json()
    assert body["candidate"]["absent"] is True
    held_ids = {a["candidate_id"] for a in body["assignments"] if a["status"] == "reserved_absent"}
    assert held_ids == {3, 6}
    assert all(u["id"] not in {3, 6} for u in body["unplaced"])

    # 标记保存失败：缺考标记、占用账、最新方案、统计全部回到保存前
    hooks["fail_commit"] = True
    res = client.post("/api/candidates/3/absent", json={"absent": False})
    assert res.status_code == 500
    hooks["fail_commit"] = False

    db = factory()
    assert db.get(Candidate, 3).absent is True
    db.close()
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert {a["candidate_id"] for a in latest["assignments"] if a["status"] == "reserved_absent"} == {3, 6}
    assert latest["stats"]["held_absent"] == 2


def test_strategies_are_mutually_exclusive(client):
    # 任一时刻只生效一种：后写的 release 必须覆盖 hold，不能两种占格并存
    client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "hold"})
    body = client.post("/api/halls/1/absent-strategy", json={"absent_strategy": "release"}).json()
    assert body["absent_strategy"] == "release"
    assert all(a.get("status") != "reserved_absent" for a in body["assignments"])
