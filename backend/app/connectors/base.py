"""Connector contract. One implementation per kind of source, all with the
same interface. Connectors only fetch and normalize — they never call AI
and never write to the database (the fetch.source job does that, so the
cursor only advances once the items are committed)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.models import Source


@dataclass
class DiscoveredItem:
    external_id: str  # canonical URL
    url: str
    title: str
    published_at: datetime
    thumbnail_url: str | None = None
    summary: str | None = None  # feed description (already cleaned/redacted)


@dataclass
class FetchResult:
    items: list[DiscoveredItem]
    cursor: dict  # the cursor to store once the items are committed
    http_status: int | None = None
    not_modified: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    message: str
    sample_titles: list[str] = field(default_factory=list)


@dataclass
class HealthStatus:
    ok: bool
    message: str


class Connector(Protocol):
    def validate(self, source: Source) -> ValidationResult: ...

    def fetch(self, source: Source, cursor: dict) -> FetchResult: ...

    def health(self, result: FetchResult) -> HealthStatus: ...


class BaseConnector:
    """Shared validate/health on top of a subclass's fetch()."""

    def fetch(self, source: Source, cursor: dict) -> FetchResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def validate(self, source: Source) -> ValidationResult:
        try:
            result = self.fetch(source, {})
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            return ValidationResult(False, f"{type(exc).__name__}: {exc}")
        health = self.health(result)
        return ValidationResult(health.ok, health.message, [i.title for i in result.items[:5]])

    def health(self, result: FetchResult) -> HealthStatus:
        if result.not_modified:
            return HealthStatus(True, "not modified")
        if not result.items:
            return HealthStatus(False, f"HTTP {result.http_status} but 0 items parsed (bot protection or feed format changed?)")
        missing_dates = sum(1 for i in result.items if i.published_at is None)
        if missing_dates:
            return HealthStatus(True, f"{len(result.items)} items ({missing_dates} without a date)")
        return HealthStatus(True, f"{len(result.items)} items")
