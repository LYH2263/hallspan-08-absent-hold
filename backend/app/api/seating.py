import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import (
    find_violations,
    normalize_strategy,
    place_candidates,
    plan_to_dict,
)

router = APIRouter(prefix="/seating", tags=["seating"])


def candidates_of_hall(db: Session, hall_id: int) -> list[Candidate]:
    return list(
        db.scalars(
            select(Candidate).where(Candidate.hall_id == hall_id).order_by(Candidate.id)
        ).all()
    )


def build_plan_result(hall: Hall, db: Session) -> dict:
    """按考室当前的缺考策略与缺考标记重算整套结果。

    排座图、占用账、统计、未排/缺考名单全部来自这里的同一次计算，保证同一套结果。
    """
    cands_rows = candidates_of_hall(db, hall.id)
    cands = [
        {"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
        for c in cands_rows
    ]
    absent_ids = {c.id for c in cands_rows if c.absent}
    strategy = normalize_strategy(hall.absent_strategy)
    assigns, unplaced, absent = place_candidates(
        hall.rows, hall.cols, hall.min_manhattan, cands,
        absent_ids=absent_ids, absent_strategy=strategy,
    )
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    result = plan_to_dict(
        assigns, unplaced, viols, hall.rows, hall.cols,
        absent=absent, absent_strategy=strategy,
    )
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    return result


def rerank_and_persist(hall: Hall, db: Session) -> tuple[SeatPlan, dict]:
    """按新策略/新标记重排，并把最新方案写入（占用账与图随之整体重写）。

    只 flush 不 commit：调用方把策略字段/缺考标记的修改与本次写入放在同一事务里，
    任一步失败整体回滚，策略字段、占用账、最新方案、统计全部回到保存前。
    """
    result = build_plan_result(hall, db)
    plan = SeatPlan(
        hall_id=hall.id,
        created_at=datetime.utcnow(),
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(plan)
    db.flush()
    return plan, result


@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    try:
        plan, result = rerank_and_persist(hall, db)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "排座保存失败，已恢复到保存前结果")
    db.refresh(plan)
    return {"id": plan.id, **result}


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    plan = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())
    ).first()
    if not plan:
        return run_seating(hall_id=hall_id, db=db)
    data = json.loads(plan.result_json)
    return {"id": plan.id, **data}


@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {
        "hall_id": hall_id,
        "violations": data.get("violations", []),
        "unplaced": data.get("unplaced", []),
        "absent": data.get("absent", []),
        "absent_strategy": data.get("absent_strategy", normalize_strategy(None)),
    }


@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, **data.get("stats", {})}
