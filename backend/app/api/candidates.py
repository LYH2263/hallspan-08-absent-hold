from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.seating import rerank_and_persist
from app.database import get_db
from app.models.models import Candidate, Hall

router = APIRouter(prefix="/candidates", tags=["candidates"])


class AbsentBody(BaseModel):
    absent: bool


def candidate_dict(r: Candidate) -> dict:
    return {
        "id": r.id,
        "hall_id": r.hall_id,
        "name": r.name,
        "ticket_no": r.ticket_no,
        "paper_id": r.paper_id,
        "absent": bool(r.absent),
    }


@router.get("")
def list_candidates(db: Session = Depends(get_db)):
    return [candidate_dict(r)
            for r in db.scalars(select(Candidate).order_by(Candidate.id)).all()]


@router.post("/{candidate_id}/absent")
def set_candidate_absent(candidate_id: int, body: AbsentBody, db: Session = Depends(get_db)):
    """标记/取消缺考并立即按当前缺考策略重排。

    缺考标记、占用账、最新方案、统计同一事务提交；保存失败整体回滚到保存前。
    """
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "考生不存在")
    hall = db.get(Hall, cand.hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    try:
        cand.absent = body.absent
        plan, result = rerank_and_persist(hall, db)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "缺考标记保存失败，标记、占用账与统计已恢复到保存前")
    db.refresh(plan)
    return {"id": plan.id, "candidate": candidate_dict(cand), **result}
