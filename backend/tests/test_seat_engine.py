from app.services.seat_engine import (
    find_violations,
    manhattan,
    place_candidates,
    plan_to_dict,
    normalize_strategy,
    SeatAssign,
    STATUS_RESERVED_ABSENT,
    STATUS_SEATED,
    STRATEGY_HOLD,
    STRATEGY_RELEASE,
)


def test_manhattan():
    assert manhattan((0, 0), (2, 1)) == 3


def test_min_distance_placement():
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 2)} for i in range(4)]
    assigns, unplaced, _ = place_candidates(4, 4, 2, cands)
    assert len(assigns) + len(unplaced) == 4
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            assert manhattan((a.row, a.col), (b.row, b.col)) >= 2


def test_same_paper_not_adjacent_in_result():
    cands = [
        {"id": 1, "name": "A", "ticket_no": "T1", "paper_id": 1},
        {"id": 2, "name": "B", "ticket_no": "T2", "paper_id": 1},
        {"id": 3, "name": "C", "ticket_no": "T3", "paper_id": 2},
    ]
    assigns, _, _ = place_candidates(3, 3, 1, cands)
    viols = find_violations(3, 3, 1, assigns)
    assert not any(v.kind == "same_paper_adjacent" for v in viols)


def test_violation_detection():
    assigns = [
        SeatAssign(1, "A", "T1", 1, 0, 0),
        SeatAssign(2, "B", "T2", 1, 0, 1),
    ]
    viols = find_violations(2, 2, 2, assigns)
    kinds = {v.kind for v in viols}
    assert "distance" in kinds
    assert "same_paper_adjacent" in kinds


def _cands(n=5):
    return [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 2)} for i in range(1, n + 1)]


def test_unconfigured_strategy_defaults_release():
    assert normalize_strategy(None) == STRATEGY_RELEASE
    assert normalize_strategy("nonsense") == STRATEGY_RELEASE
    assigns, unplaced, absent = place_candidates(3, 3, 2, _cands(), absent_ids={5}, absent_strategy=None)
    assert all(a.candidate_id != 5 for a in assigns)
    assert all(u["id"] != 5 for u in unplaced)
    assert [a["id"] for a in absent] == [5]


def test_hold_leaves_one_ledger_row_per_absent():
    """占格保留：每个缺考生在占用账留一行占格；别人不得坐；统计占格含此人；未排不含缺考。"""
    assigns, unplaced, absent = place_candidates(
        4, 4, 2, _cands(6), absent_ids={3, 5}, absent_strategy=STRATEGY_HOLD
    )
    held = [a for a in assigns if a.status == STATUS_RESERVED_ABSENT]
    seated = [a for a in assigns if a.status == STATUS_SEATED]
    assert {a.candidate_id for a in held} == {3, 5}
    assert len(held) == 2
    # 占用账每个格唯一：占格别人不得坐
    positions = [(a.row, a.col) for a in assigns]
    assert len(positions) == len(set(positions))
    assert {a.candidate_id for a in seated}.isdisjoint({3, 5})
    # 缺考生不得进未排名单
    assert all(u["id"] not in {3, 5} for u in unplaced)
    # 占格统计含缺考保留者
    result = plan_to_dict(assigns, unplaced, [], 4, 4, absent=absent, absent_strategy=STRATEGY_HOLD)
    assert result["stats"]["occupied"] == len(assigns) == len(seated) + 2
    assert result["stats"]["held_absent"] == 2
    assert result["stats"]["seated"] == len(seated)
    assert all(a["held"] for a in result["absent"] if a["id"] in {3, 5})


def test_release_deletes_absent_ledger_rows():
    """释放空出：缺考生占用账无行，格子还给后续考生；统计占格不含此人。"""
    assigns, unplaced, absent = place_candidates(
        4, 4, 2, _cands(6), absent_ids={3}, absent_strategy=STRATEGY_RELEASE
    )
    assert all(a.candidate_id != 3 for a in assigns)
    assert all(a.status == STATUS_SEATED for a in assigns)
    assert all(u["id"] != 3 for u in unplaced)
    result = plan_to_dict(assigns, unplaced, [], 4, 4, absent=absent, absent_strategy=STRATEGY_RELEASE)
    assert result["stats"]["occupied"] == result["stats"]["seated"] == len(assigns)
    assert result["stats"]["held_absent"] == 0
    released = [a for a in result["absent"] if a["id"] == 3][0]
    assert released["held"] is False and released["status"] == "released"


def test_switch_hold_then_release_rewrites_ledger_and_stats():
    """先占格保留再改释放：同一缺考从占用账有行变为无行，图与统计一起变。"""
    held_assigns, _, absent = place_candidates(
        3, 3, 2, _cands(5), absent_ids={2}, absent_strategy=STRATEGY_HOLD
    )
    hold_plan = plan_to_dict(held_assigns, [], [], 3, 3, absent=absent, absent_strategy=STRATEGY_HOLD)
    held_row = [a for a in hold_plan["assignments"] if a["candidate_id"] == 2]
    assert len(held_row) == 1 and held_row[0]["status"] == STATUS_RESERVED_ABSENT
    held_pos = (held_row[0]["row"], held_row[0]["col"])

    rel_assigns, _, _ = place_candidates(
        3, 3, 2, _cands(5), absent_ids={2}, absent_strategy=STRATEGY_RELEASE
    )
    rel_plan = plan_to_dict(rel_assigns, [], [], 3, 3, absent=absent, absent_strategy=STRATEGY_RELEASE)
    # 占用账重写：同一缺考不再有行
    assert all(a["candidate_id"] != 2 for a in rel_plan["assignments"])
    # 格子还给后续考生：该格可被他人占用
    assert held_pos in {(a.row, a.col) for a in rel_assigns}
    # 统计一起变
    assert rel_plan["stats"]["occupied"] == hold_plan["stats"]["occupied"] - 1
    assert rel_plan["stats"]["held_absent"] == 0
    assert hold_plan["absent_strategy"] == STRATEGY_HOLD
    assert rel_plan["absent_strategy"] == STRATEGY_RELEASE


def test_absent_never_unplaced_even_when_capacity_tight():
    # 容量紧张到有考生排不下：缺考也不能被当作可调剂未排
    cands = _cands(6)
    for strat in (STRATEGY_HOLD, STRATEGY_RELEASE, None):
        _, unplaced, absent = place_candidates(2, 2, 2, cands, absent_ids={6}, absent_strategy=strat)
        assert all(u["id"] != 6 for u in unplaced)
        assert [a["id"] for a in absent] == [6]


def test_held_row_creates_no_violation_and_not_merged_in_detail():
    """缺考占格不产生间距/同卷违规说明，且不与违规说明并句。"""
    # 缺考 id=1 占住 (0,0)，后续考生可紧邻其占格就座，但违规判定不得牵涉缺考生
    assigns, _, _ = place_candidates(
        2, 2, 2, _cands(4), absent_ids={1}, absent_strategy=STRATEGY_HOLD
    )
    assert any(a.status == STATUS_RESERVED_ABSENT and a.candidate_id == 1 for a in assigns)
    viols = find_violations(2, 2, 2, assigns)
    assert all(v.a_id != 1 and v.b_id != 1 for v in viols)
    # 违规说明文本不并入缺考字样
    for v in viols:
        assert "缺考" not in v.detail
