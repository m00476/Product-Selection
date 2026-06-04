import csv
from datetime import datetime, timezone


def read_csv_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def to_float(value) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value) -> int | None:
    f = to_float(value)
    return int(f) if f is not None else None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
