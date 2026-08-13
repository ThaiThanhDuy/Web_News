from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    homepage_url: str
    logo_url: str


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    original_url: str
    thumbnail_url: str | None = None
    published_at: datetime

    source: SourceOut
    category: CategoryOut | None = None

    summary_bullets: list[str] | None = None
    one_line_takeaway: str | None = None
    keywords: list[str] | None = None
    sentiment: Literal["positive", "neutral", "negative"] | None = None

    hotness_score: float
    cross_source_count: int = 1


class ArticlePage(BaseModel):
    items: list[ArticleOut]
    page: int
    page_size: int
    total: int
    has_more: bool
