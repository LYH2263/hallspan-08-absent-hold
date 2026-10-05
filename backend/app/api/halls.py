from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.seating import rerank_and_persist
from app.database import get_db
from app.models.models import Hall
from app.services.seat_engine import VALID_STRATEGIES, normalize_strategy

router = APIRouter(prefix="/halls", tags=["halls"])


class StrategyBody(BaseModel):
    # hold=占格保留，release=释放空出，null=未配置（按释放兼容现网）
    absent_strategy: str | None = None


def hall_dict(r: Hall) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "rows": r.rows,
        "cols": r.cols,
        "min_manhattan": r.min_manhattan,
        "absent_strategy": normalize_strategy(r.absent_strategy) if r.absent_strategy else None,
    }


@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [hall_dict(r) for r in db.scalars(select(Hall).order_by(Hall.id)).all()]


@router.post("/{hall_id}/absent-strategy")
def set_absent_strategy(hall_id: int, body: StrategyBody, db: Session = Depends(get_db)):
    """切换缺考策略并立即按新策略重排。

    策略字段修改、占用账重写、最新方案、统计在同一事务提交；
    保存失败时整体回滚，全部回到保存前（最新方案仍是旧策略结果）。
    """
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    if body.absent_strategy is not None and body.absent_strategy not in VALID_STRATEGIES:
        raise HTTPException(422, "缺考策略仅支持 hold（占格保留）或 release（释放空出）")

    new_strategy = body.absent_strategy  # None 表示恢复“未配置”，按 release 兼容
    try:
        hall.absent_strategy = new_strategy
        plan, result = rerank_and_persist(hall, db)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "策略保存失败，策略字段、占用账与统计已恢复到保存前")
    db.refresh(plan)
    return {"id": plan.id, **hall_dict(hall), **result}
