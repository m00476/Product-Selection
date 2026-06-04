import re
from urllib.parse import urlsplit

_OZON_RE = re.compile(r"/product/(?:[^/]*-)?(\d+)")
_AE_RE = re.compile(r"/item/(\d+)\.html")


def normalize_product_url(url: str | None) -> tuple[str, str | None, str | None]:
    """返回 (platform, platform_product_id, canonical_url)。"""
    if not url or not url.strip():
        return ("unknown", None, None)
    raw = url.strip()
    parts = urlsplit(raw if "://" in raw else "https://" + raw)
    host = parts.netloc.lower()
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    path = parts.path.rstrip("/")

    if "ozon.ru" in host:
        match = _OZON_RE.search(path)
        if match:
            pid = match.group(1)
            return ("ozon", pid, f"https://www.ozon.ru/product/{pid}")
        return ("ozon", None, None)

    if "aliexpress" in host:
        match = _AE_RE.search(path)
        if match:
            pid = match.group(1)
            return ("aliexpress", pid, f"https://www.aliexpress.com/item/{pid}.html")
        return ("aliexpress", None, None)

    return ("unknown", None, None)
