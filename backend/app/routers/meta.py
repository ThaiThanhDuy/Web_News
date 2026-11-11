from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Source, Topic
from app.schemas import CategoryOut, SourceOut

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.execute(select(Source).where(Source.is_active.is_(True)).order_by(Source.name)).scalars().all()


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    """Public topics (Hướng 1). Kept under the old /categories path."""
    return (
        db.execute(select(Topic).where(Topic.is_public.is_(True)).order_by(Topic.sort_order, Topic.name))
        .scalars()
        .all()
    )
