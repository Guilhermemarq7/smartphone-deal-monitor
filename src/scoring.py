from __future__ import annotations

from .models import Offer, Target, Stats, Deal
from .pricing import real_discount, distance_from_low, suspicious_outlier
from .normalize import infer_quality_score

TRUST={"A":1.0,"B":0.78,"C":0.48,"D":0.15,"unknown":0.40}


def score_deal(offer: Offer, target: Target | None, stats: Stats, cfg: dict) -> Deal:
    current=offer.price_final_direct
    budget=cfg["budget"]
    upgrade=(target.upgrade_score if target else infer_quality_score(offer.title))
    s=25*(upgrade/100)
    reasons=[]

    ideal=float(budget["ideal"]); exceptional=float(budget["exceptional_limit"])
    if target:
        # A R$3.45k S24 Ultra can be extraordinary even though it is above the generic R$3k ideal.
        # Per-model thresholds from the research therefore take precedence for the price-fit component.
        if current <= target.dream_price: pfit=15
        elif current <= target.strong_buy_below: pfit=13
        elif current <= target.alert_below: pfit=10
        elif current <= target.alert_below * 1.10: pfit=5
        else: pfit=0
    else:
        if current <= ideal: pfit=15
        elif current <= exceptional: pfit=15*(exceptional-current)/(exceptional-ideal)
        else: pfit=max(0, 6*(exceptional*1.3-current)/(exceptional*0.3))
    s += max(0,pfit)

    disc=real_discount(current, stats.median_30d)
    if disc is not None:
        s += max(0, min(20, (disc/0.25)*20))
        reasons.append(f"desconto real {disc*100:.1f}% vs mediana")

    low=stats.min_90d
    dist=distance_from_low(current, low)
    if dist is not None:
        if dist <= 0: hist=15
        elif dist <= .05: hist=13
        elif dist <= .10: hist=10
        elif dist <= .20: hist=5
        else: hist=0
        s += hist

    store_level=store_trust_level(offer)
    seller_level=seller_trust_level(offer)
    s += 10*TRUST[store_level]
    s += 7*TRUST[seller_level]

    friction=5.0
    if offer.requires_tradein: friction -= 4
    if offer.requires_card: friction -= 2
    if offer.requires_subscription: friction -= 2
    if offer.requires_first_purchase: friction -= 1.5
    if offer.coupon_limited: friction -= 1
    if offer.cashback > 0: friction -= 1.5
    s += max(0,friction)
    s += 3 if (offer.storage_gb or 0) >= 256 else 1

    outlier=suspicious_outlier(current, stats.median_30d, cfg.get("analysis",{}).get("outlier_ratio",.60))
    if outlier:
        reasons.append("preço abaixo do limiar de outlier; exige verificação")
        s=min(s,60)
    if offer.condition in {"used","refurbished"}:
        s=min(s,25)
        reasons.append("produto não é novo")
    elif offer.condition == "unknown":
        s=max(0,s-5)
        reasons.append("condição não confirmada pela fonte")
    if seller_level == "D":
        s=min(s,50)
        reasons.append("seller de baixa confiança")

    score=round(max(0,min(100,s)),1)
    classification=classify(score, outlier, offer, target)
    return Deal(offer=offer, score=score, classification=classification, discount_real=disc,
                distance_from_low=dist, stats=stats, suspicious_outlier=outlier, reasons=reasons)


def classify(score: float, outlier: bool, offer: Offer, target: Target | None) -> str:
    if outlier: return "OUTLIER — VERIFICAR"
    if offer.condition in {"used","refurbished"}: return "IGNORAR — NÃO É NOVO"
    if target and offer.price_final_direct <= target.dream_price and score >= 75: return "PREÇO HISTÓRICO / EXCEPCIONAL"
    if score >= 88: return "OFERTA EXCEPCIONAL"
    if score >= 76: return "ÓTIMA OFERTA"
    if score >= 62: return "PREÇO BOM"
    return "NORMAL"


def store_trust_level(o: Offer) -> str:
    if o.is_official_store or o.store.lower() in {"samsung", "motorola"}: return "A"
    if o.store.lower() in {"mercado livre", "magalu", "kabum", "fast shop", "casas bahia"}: return "B"
    return "C"


def seller_trust_level(o: Offer) -> str:
    if o.is_official_store: return "A"
    lv=(o.seller_level or "").lower()
    if any(x in lv for x in ["5_green","green","platinum","mercadolider platinum"]): return "A"
    if any(x in lv for x in ["4_light_green","gold","mercadolider"]): return "B"
    if any(x in lv for x in ["red","orange","yellow"]): return "D"
    if o.seller and o.seller.lower() in {"magalu","amazon","samsung","motorola"}: return "A"
    return "C"
