from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Target:
    id: str
    name: str
    brand: str
    aliases: list[str]
    storage_gb: int
    alert_below: float
    strong_buy_below: float
    dream_price: float
    priority: str
    upgrade_score: float
    bootstrap_recent: Optional[float] = None
    bootstrap_low: Optional[float] = None
    aspirational: bool = False


@dataclass
class Offer:
    source: str
    store: str
    title: str
    url: str
    price_base: float
    price_pix: Optional[float] = None
    coupon_code: Optional[str] = None
    coupon_discount: float = 0.0
    cashback: float = 0.0
    shipping: Optional[float] = None
    seller: Optional[str] = None
    seller_id: Optional[str] = None
    seller_level: Optional[str] = None
    is_official_store: bool = False
    condition: str = "unknown"
    stock: Optional[str] = None
    target_id: Optional[str] = None
    canonical_name: Optional[str] = None
    brand: Optional[str] = None
    storage_gb: Optional[int] = None
    requires_tradein: bool = False
    requires_card: bool = False
    requires_subscription: bool = False
    requires_first_purchase: bool = False
    coupon_limited: bool = False
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def price_final_direct(self) -> float:
        starting = self.price_pix if self.price_pix and self.price_pix > 0 else self.price_base
        shipping = self.shipping if self.shipping and self.shipping > 0 else 0.0
        return max(0.0, starting - max(0.0, self.coupon_discount) + shipping)

    @property
    def price_effective_cashback(self) -> float:
        return max(0.0, self.price_final_direct - max(0.0, self.cashback))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["price_final_direct"] = self.price_final_direct
        d["price_effective_cashback"] = self.price_effective_cashback
        return d


@dataclass
class Stats:
    median_7d: Optional[float] = None
    median_30d: Optional[float] = None
    median_90d: Optional[float] = None
    min_7d: Optional[float] = None
    min_30d: Optional[float] = None
    min_90d: Optional[float] = None
    volatility_30d: Optional[float] = None
    samples_30d: int = 0
    used_bootstrap: bool = False


@dataclass
class Deal:
    offer: Offer
    score: float
    classification: str
    discount_real: Optional[float]
    distance_from_low: Optional[float]
    stats: Stats
    suspicious_outlier: bool = False
    reasons: list[str] = field(default_factory=list)
