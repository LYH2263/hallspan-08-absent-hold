from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def ensure_columns() -> None:
    """轻量兼容旧库：补齐缺考策略/缺考标记列（create_all 不会改已存在的表）。"""
    inspector = inspect(engine)
    hall_cols = {c["name"] for c in inspector.get_columns("halls")}
    with engine.begin() as conn:
        if "absent_strategy" not in hall_cols:
            conn.execute(text("ALTER TABLE halls ADD COLUMN absent_strategy VARCHAR(16)"))
        cand_cols = {c["name"] for c in inspector.get_columns("candidates")}
        if "absent" not in cand_cols:
            conn.execute(text("ALTER TABLE candidates ADD COLUMN absent BOOLEAN NOT NULL DEFAULT false"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="HallSpan", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
