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
    # Other topics the story also belongs to (it's listed under them too).
    related_categories: list[CategoryOut] = []

    summary_bullets: list[str] | None = None
    one_line_takeaway: str | None = None
    keywords: list[str] | None = None
    sentiment: Literal["positive", "neutral", "negative"] | None = None

    hotness_score: float
    cross_source_count: int = 1
    # True for the "hottest first" items leading a feed page (sort=feed).
    is_featured: bool = False
    # Featured partly because it matches the reader's interests (part C).
    is_personalized: bool = False


class ArticlePage(BaseModel):
    items: list[ArticleOut]
    page: int
    page_size: int
    total: int
    has_more: bool


# ------------------------------------------------------------- web push


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    """The browser's PushSubscription.toJSON()."""

    endpoint: str
    keys: PushKeys


class PushSubscribeRequest(BaseModel):
    subscription: PushSubscriptionIn
    # Topic slugs; empty = every topic.
    topics: list[str] = []


class PushEndpointRequest(BaseModel):
    endpoint: str


class PushStatusOut(BaseModel):
    subscribed: bool
    topics: list[str] = []


class PushConfigOut(BaseModel):
    enabled: bool
    public_key: str | None = None


# --------------------------------------------------------------- search


class SearchOut(BaseModel):
    query: str
    # Items matching every word / #hashtag of the query (accent-insensitive).
    items: list[ArticleOut]
    # Semantically close items that don't contain the words (embeddings).
    related: list[ArticleOut]
    topics: list[CategoryOut]
    # Hashtag suggestions drawn from the matching items' keywords.
    tags: list[str]


class TrendingOut(BaseModel):
    tags: list[str]
