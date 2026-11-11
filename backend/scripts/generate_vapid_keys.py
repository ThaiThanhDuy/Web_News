"""Generates a VAPID key pair for Web Push and writes it into backend/.env
(VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY, plus a placeholder VAPID_SUBJECT if
none is set). Refuses to overwrite existing keys: rotating them invalidates
every browser subscription.

Usage (from backend/, with the venv active):
    python scripts/generate_vapid_keys.py
"""

import base64
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main() -> None:
    env = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    existing = re.search(r"^VAPID_PRIVATE_KEY=(.+)$", env, re.MULTILINE)
    if existing and existing.group(1).strip():
        sys.exit("VAPID keys already set in backend/.env — not overwriting (would break existing subscriptions).")

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    values = {"VAPID_PUBLIC_KEY": b64url(public_raw), "VAPID_PRIVATE_KEY": b64url(private_raw)}
    if not re.search(r"^VAPID_SUBJECT=.+$", env, re.MULTILINE):
        values["VAPID_SUBJECT"] = "mailto:admin@example.com"

    for key, value in values.items():
        pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
        if pattern.search(env):
            env = pattern.sub(f"{key}={value}", env)
        else:
            env = env.rstrip("\n") + f"\n{key}={value}\n"
    ENV_PATH.write_text(env, encoding="utf-8")
    print("VAPID keys written to backend/.env.")
    if "VAPID_SUBJECT" in values:
        print("Set VAPID_SUBJECT to a real contact (mailto:you@yourdomain or https://yourdomain) before production.")


if __name__ == "__main__":
    main()
