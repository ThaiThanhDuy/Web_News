"""Raw-data store: one gzip'd JSON file per fetched document, already
PII-redacted, kept RAW_RETENTION_DAYS so the pipeline can be re-run.

Layout: {RAW_DATA_DIR}/{connector}/{yyyy}/{mm}/{dd}/{source_id}/{sha256}.json.gz

Phase-0 implementation writes to local disk; moving to object storage later
only changes this module (paths are stored relative to RAW_DATA_DIR).
"""

import gzip
import hashlib
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _root() -> Path:
    root = Path(settings.RAW_DATA_DIR)
    return root if root.is_absolute() else BACKEND_DIR / root


def save(connector: str, source_id: int, document: dict) -> str:
    body = json.dumps(document, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    today = datetime.now(timezone.utc)
    relative = Path(connector) / f"{today:%Y}" / f"{today:%m}" / f"{today:%d}" / str(source_id) / f"{digest}.json.gz"
    path = _root() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wb") as fh:
            fh.write(body)
        tmp.replace(path)
    return str(relative)


def load(relative_path: str) -> dict:
    with gzip.open(_root() / relative_path, "rb") as fh:
        return json.loads(fh.read())


def delete_older_than(days: int) -> int:
    """Removes whole day directories older than `days`. Returns how many."""
    cutoff = date.today() - timedelta(days=days)
    removed = 0
    root = _root()
    if not root.exists():
        return 0
    for day_dir in root.glob("*/*/*/*"):
        try:
            y, m, d = (int(p) for p in day_dir.relative_to(root).parts[1:4])
            if date(y, m, d) < cutoff:
                shutil.rmtree(day_dir)
                removed += 1
        except (ValueError, OSError):
            continue
    return removed
