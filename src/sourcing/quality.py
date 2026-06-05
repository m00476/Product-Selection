from sourcing.readers.common import read_csv_rows, to_float, to_int
from sourcing.urls import normalize_product_url


def _present(value) -> bool:
    return value not in (None, "", "None")


def _record_url(row: dict) -> str | None:
    return row.get("product_url") or row.get("productUrl") or row.get("url")


def _record_id(row: dict) -> str | None:
    return row.get("sku") or row.get("productId") or row.get("product_id")


def _base_report(source: str, product_type: str, total: int) -> dict:
    return {
        "source": source,
        "product_type": product_type,
        "total_rows": total,
        "missing_product_url": 0,
        "missing_price": 0,
        "missing_cost_price": 0,
        "missing_stock": 0,
        "unknown_platform": 0,
        "deterministic": 0,
        "fuzzy_pending": 0,
    }


def inspect_csv_quality(path: str, *, source: str, product_type: str) -> dict:
    rows = read_csv_rows(path)
    report = _base_report(source, product_type, len(rows))
    for row in rows:
        if source in {"seerfar", "ixspy"}:
            url = _record_url(row)
            platform, platform_product_id, _canonical_url = normalize_product_url(url)
            if not _present(url):
                report["missing_product_url"] += 1
            if to_float(row.get("price")) is None:
                report["missing_price"] += 1
            if platform == "unknown":
                report["unknown_platform"] += 1
            if platform_product_id:
                report["deterministic"] += 1
            else:
                report["fuzzy_pending"] += 1
            if not _present(_record_id(row)) and not platform_product_id:
                report.setdefault("missing_source_record_id", 0)
                report["missing_source_record_id"] += 1
        elif source == "erp":
            if to_float(row.get("cost_price")) is None:
                report["missing_cost_price"] += 1
            if to_int(row.get("stock")) is None:
                report["missing_stock"] += 1
            report["fuzzy_pending"] += 1
    return report
