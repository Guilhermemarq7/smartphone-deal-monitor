from __future__ import annotations

from collections import defaultdict
from statistics import median
from .models import Offer
from .normalize import infer_quality_score,norm


def filter_discovery(offers:list[Offer],cfg:dict)->list[Offer]:
    dcfg=cfg.get("discovery",{})
    max_price=float(dcfg.get("max_offer_price",cfg["budget"]["exceptional_limit"]))
    min_quality=float(dcfg.get("min_quality_score",70))
    known={x["id"] for x in cfg.get("phones",[])+cfg.get("aspirational",[])}
    out=[]
    for o in offers:
        if o.target_id in known: continue
        if o.price_final_direct>max_price: continue
        if infer_quality_score(o.title)<min_quality: continue
        if o.condition in {"used","refurbished"}:continue
        if not o.brand:continue
        # Discovery is conservative: these are leads, not automatic buy recommendations.
        o.notes.append("descoberta automática: confirmar modelo/variante e condições antes da compra")
        out.append(o)
    return dedup(out)

def dedup(items):
    best={}
    for o in items:
        k=(norm(o.canonical_name or o.title),o.storage_gb,o.store)
        if k not in best or o.price_final_direct<best[k].price_final_direct:best[k]=o
    return list(best.values())
