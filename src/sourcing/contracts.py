from dataclasses import dataclass
from datetime import datetime


@dataclass
class NormalizedProduct:
    source: str
    platform: str
    platform_product_id: str | None
    canonical_url: str | None
    source_record_id: str
    product_type: str
    title: str | None = None
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    is_own: bool = False


@dataclass
class PriceSnapshot:
    source: str
    platform: str
    platform_product_id: str | None
    price: float | None
    currency: str | None
    observed_at: datetime
    collected_at: datetime
    metric_source: str | None = None


@dataclass
class SalesSnapshot:
    source: str
    platform: str
    platform_product_id: str | None
    sales: float | None
    review_count: int | None
    review_rating: float | None
    observed_at: datetime
    collected_at: datetime
    metric_source: str | None = None
