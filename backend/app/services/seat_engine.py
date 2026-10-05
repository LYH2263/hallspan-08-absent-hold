"""Exam seating: min Manhattan distance; same paper_id cannot be 4-neighbor adjacent.

缺考策略（两策略互斥，只允许生效一种）：
- hold    占格保留：每个缺考生在占用账留一行占格（status=reserved_absent），
          该格别人不得坐；占用统计含此人；未排名单不含缺考生。
- release 释放空出：缺考生不进占用账（占用行被删除/作废），格子还给后续考生。
策略未配置（None）按 release 兼容现网。

排座图、占用账、统计、未排/缺考名单全部由本模块同一次排座结果派生，保证一致。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# 占格保留
STRATEGY_HOLD = "hold"
# 释放空出
STRATEGY_RELEASE = "release"
VALID_STRATEGIES = (STRATEGY_HOLD, STRATEGY_RELEASE)

# 占用账行状态
STATUS_SEATED = "seated"
STATUS_RESERVED_ABSENT = "reserved_absent"


def normalize_strategy(strategy: str | None) -> str:
    """策略未配置按释放兼容现网；非法值也回落到 release。"""
    return strategy if strategy in VALID_STRATEGIES else STRATEGY_RELEASE


@dataclass
class SeatAssign:
    """占用账行：每行占住一个格子。seat 行=已排考生，reserved_absent 行=缺考占格。"""
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int
    status: str = STATUS_SEATED

    @property
    def is_absent_hold(self) -> bool:
        return self.status == STATUS_RESERVED_ABSENT


@dataclass
class Violation:
    kind: str
    a_id: int
    b_id: int
    detail: str


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def place_candidates(
    rows: int,
    cols: int,
    min_dist: int,
    candidates: list[dict],
    absent_ids: set[int] | None = None,
    absent_strategy: str | None = None,
) -> tuple[list[SeatAssign], list[dict], list[dict]]:
    """排座，返回 (占用账, 未排名单, 缺考名单)。

    占用账是唯一的占格依据：
    - hold：缺考生先在占用账占一格（reserved_absent 行），后续任何人都不得坐该格；
            缺考生不进入未排名单（不得当作可调剂未排）。
    - release：缺考生不产生占用行，其格子还给后续考生；缺考生同样不进未排名单。
    """
    absent_ids = set(absent_ids or ())
    strategy = normalize_strategy(absent_strategy)

    # 占用账：坐标 -> 占格行（已排考生或缺考占格）。任何在该 dict 中的格子都不得再坐。
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    absent: list[dict] = []

    def first_free() -> tuple[int, int] | None:
        for r in range(rows):
            for c in range(cols):
                if (r, c) not in occupied:
                    return r, c
        return None

    def seat_ok(r: int, c: int, cand: dict) -> bool:
        for pos, other in occupied.items():
            # 缺考占格只占住格子：它不施加间距/同卷约束，占用本身（坐标已在 occupied）挡住该格即可。
            if other.is_absent_hold:
                continue
            if manhattan((r, c), pos) < min_dist:
                return False
            if other.paper_id == cand["paper_id"] and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
                return False
        for nr, nc in neighbors4(r, c, rows, cols):
            other = occupied.get((nr, nc))
            if other is not None and not other.is_absent_hold and other.paper_id == cand["paper_id"]:
                return False
        return True

    # 按名册顺序单趟处理：缺考生在轮到他时处理，占住的就是“他本会排到”的那个格。
    for cand in candidates:
        if cand["id"] in absent_ids:
            absent.append(cand)
            if strategy == STRATEGY_HOLD:
                # 占格保留：在占用账留一行占格，该格别人不得坐；不参与间距/同卷判定。
                # 优先占住“按正常规则他本会排到”的格；容量受限时退到任意空格，保证每人一行占格。
                hold_pos: tuple[int, int] | None = None
                for r in range(rows):
                    for c in range(cols):
                        if (r, c) not in occupied and seat_ok(r, c, cand):
                            hold_pos = (r, c)
                            break
                    if hold_pos:
                        break
                if hold_pos is None:
                    hold_pos = first_free()
                if hold_pos is not None:
                    r, c = hold_pos
                    occupied[hold_pos] = SeatAssign(
                        cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"],
                        r, c, status=STATUS_RESERVED_ABSENT,
                    )
            # 释放空出：不写占用行，格子留给后续考生。
            # 缺考生任何策略下都不进未排名单（不得当作可调剂未排）。
            continue

        placed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied:
                    continue
                if not seat_ok(r, c, cand):
                    continue
                occupied[(r, c)] = SeatAssign(
                    cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c
                )
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append(cand)

    return list(occupied.values()), unplaced, absent


def find_violations(rows: int, cols: int, min_dist: int, assigns: list[SeatAssign]) -> list[Violation]:
    """间距/同卷违规只在真实就座的考生之间判定；缺考占格不产生违规说明。"""
    viols: list[Violation] = []
    seated = [a for a in assigns if a.status == STATUS_SEATED]
    for i, a in enumerate(seated):
        for b in seated[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < min_dist:
                viols.append(Violation("distance", a.candidate_id, b.candidate_id,
                                       f"曼哈顿距离 {d} < 最小要求 {min_dist}"))
            if a.paper_id == b.paper_id and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols):
                viols.append(Violation("same_paper_adjacent", a.candidate_id, b.candidate_id,
                                       f"同试卷套 {a.paper_id} 四邻相邻"))
    return viols


def plan_to_dict(
    assigns: list[SeatAssign],
    unplaced: list[dict],
    viols: list[Violation],
    rows: int,
    cols: int,
    absent: list[dict] | None = None,
    absent_strategy: str | None = None,
) -> dict:
    """所有视图（排座图/占用账/统计/未排/缺考名单）的唯一数据源。"""
    absent = absent or []
    strategy = normalize_strategy(absent_strategy)
    seated = [a for a in assigns if a.status == STATUS_SEATED]
    held = [a for a in assigns if a.status == STATUS_RESERVED_ABSENT]
    held_ids = {a.candidate_id for a in held}
    absent_rows = [
        {**c, "held": c["id"] in held_ids, "status": STATUS_RESERVED_ABSENT if c["id"] in held_ids else "released"}
        for c in absent
    ]
    return {
        "rows": rows,
        "cols": cols,
        # 占用账：hold 时含每个缺考生的占格行；release 时无缺考行。
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "absent": absent_rows,
        "absent_strategy": strategy,
        "violations": [asdict(v) for v in viols],
        "stats": {
            # 实际就座考生
            "seated": len(seated),
            # 占用账行数 = 已排 + 缺考占格；统计占格含缺考保留者
            "occupied": len(assigns),
            # 缺考占格保留的格数
            "held_absent": len(held),
            "unplaced": len(unplaced),
            "absent": len(absent_rows),
            "violations": len(viols),
            "capacity": rows * cols,
        },
    }
