"""Web Push sending (VAPID). Generate keys with scripts/generate_vapid_keys.py."""

import json
import logging
from dataclasses import dataclass

from pywebpush import WebPushException, webpush

from app.config import settings
from app.models import PushSubscription

logger = logging.getLogger(__name__)

# Push services cap payloads around 4KB after encryption.
MAX_PAYLOAD_BYTES = 3000


class PushNotConfigured(Exception):
    pass


@dataclass
class PushOutcome:
    ok: bool
    gone: bool = False  # 404/410: subscription is dead, delete it
    retry_after: float | None = None  # 429
    transient: bool = False  # 5xx / network
    error: str | None = None


def is_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY and settings.VAPID_SUBJECT)


def build_payload(title: str, body: str, url: str, tag: str) -> str:
    payload = {"title": title[:120], "body": body[:240], "url": url, "tag": tag, "icon": "/icons/icon-192.png"}
    data = json.dumps(payload, ensure_ascii=False)
    while len(data.encode("utf-8")) > MAX_PAYLOAD_BYTES and payload["body"]:
        payload["body"] = payload["body"][: len(payload["body"]) // 2]
        data = json.dumps(payload, ensure_ascii=False)
    return data


def send(subscription: PushSubscription, payload: str) -> PushOutcome:
    if not is_configured():
        raise PushNotConfigured("VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT not set in backend/.env")
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=settings.PUSH_TTL_SECONDS,
            timeout=20,
        )
        return PushOutcome(ok=True)
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        text = (exc.response.text[:300] if exc.response is not None else str(exc)) or str(exc)
        if status in (404, 410):
            return PushOutcome(ok=False, gone=True, error=f"HTTP {status}: {text}")
        if status == 429:
            retry = exc.response.headers.get("retry-after", "60") if exc.response is not None else "60"
            return PushOutcome(ok=False, retry_after=float(retry) if retry.isdigit() else 60.0, error=text)
        if status is None or status >= 500:
            return PushOutcome(ok=False, transient=True, error=f"HTTP {status}: {text}")
        return PushOutcome(ok=False, error=f"HTTP {status}: {text}")
    except Exception as exc:  # network errors from requests
        return PushOutcome(ok=False, transient=True, error=f"{type(exc).__name__}: {exc}")
