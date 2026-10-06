from __future__ import annotations

import os,re,time
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
from .base import CollectorResult, build_session
from ..models import Offer, Target
from ..normalize import detect_condition, extract_storage_gb, is_accessory, match_target, infer_brand, norm

class MercadoLivreCollector:
    name="Mercado Livre"
    API="https://api.mercadolibre.com"
    WEB="https://lista.mercadolivre.com.br"

    def __init__(self,cfg:dict):
        self.cfg=cfg
        self.timeout=float(cfg.get("timeout_seconds",12)); self.delay=float(cfg.get("min_delay_seconds",1.2))
        self.limit=int(cfg.get("results_per_query",20)); self.token=os.getenv("ML_ACCESS_TOKEN","").strip()
        self.s=build_session(cfg.get("user_agent","Mozilla/5.0 SmartphoneDealMonitor/1.0"),int(cfg.get("retries",2)))
        if self.token: self.s.headers["Authorization"]="Bearer "+self.token

    def collect(self, targets:list[Target]) -> CollectorResult:
        offers=[]; errors=[]
        for i,t in enumerate(targets):
            q=t.name
            try:
                got=self._api_search(q,t,targets)
                offers.extend(got)
            except Exception as e:
                errors.append(f"API {t.id}: {type(e).__name__}: {e}")
                try: offers.extend(self._web_search(q,t,targets))
                except Exception as e2: errors.append(f"web {t.id}: {type(e2).__name__}: {e2}")
            if i < len(targets)-1: time.sleep(self.delay)
        ok=bool(offers) or not errors
        msg=f"{len(offers)} ofertas" + (f"; {len(errors)} falhas parciais" if errors else "")
        if errors: msg += " | " + " || ".join(errors[:3])
        return CollectorResult(self.name,offers,ok,msg)

    def discover(self, targets:list[Target]) -> CollectorResult:
        queries=self.cfg.get("discovery_queries",["Samsung Galaxy 256GB","Motorola Edge Pro 256GB","Xiaomi 256GB","POCO 512GB","iPhone 128GB"])
        offers=[]; errors=[]
        for q in queries:
            try: offers.extend(self._api_search(q,None,targets))
            except Exception as e:
                errors.append(f"API {q}: {type(e).__name__}: {e}")
                try: offers.extend(self._web_search(q,None,targets))
                except Exception as e2: errors.append(f"web {q}: {type(e2).__name__}: {e2}")
            time.sleep(self.delay)
        return CollectorResult(self.name+" discovery",offers,bool(offers) or not errors,"; ".join(errors[:3]) if errors else f"{len(offers)} candidatos")

    def _api_search(self,q:str,target:Target|None,targets:list[Target]):
        url=self.API+"/sites/MLB/search"
        r=self.s.get(url,params={"q":q,"limit":self.limit},timeout=self.timeout)
        if r.status_code in (401,403): raise RuntimeError(f"HTTP {r.status_code}; configure ML_ACCESS_TOKEN ou use fallback web")
        r.raise_for_status(); data=r.json(); out=[]
        for item in data.get("results",[]):
            title=str(item.get("title") or "")
            if is_accessory(title): continue
            cond=detect_condition(title,_condition_from_attributes(item) or str(item.get("condition") or ""))
            if cond in {"used","refurbished"}: continue
            price=item.get("price")
            if not isinstance(price,(int,float)) or price<200: continue
            found=target or match_target(title,targets)
            storage=extract_storage_gb(title) or _storage_from_attributes(item)
            if found and storage != found.storage_gb:
                continue
            if storage is None:
                continue
            seller=item.get("seller") or {}
            seller_level=seller.get("reputation_level_id") or seller.get("seller_reputation",{}).get("level_id")
            o=Offer(source="mercadolivre_api",store="Mercado Livre",title=title,url=item.get("permalink") or "",price_base=float(price),
                    seller=str(seller.get("nickname") or seller.get("id") or "") or None,seller_id=str(seller.get("id") or "") or None,
                    seller_level=str(seller_level or "") or None,is_official_store=bool(item.get("official_store_id")),condition=cond,
                    shipping=0.0 if (item.get("shipping") or {}).get("free_shipping") is True else None,
                    stock="available" if (item.get("available_quantity") or 0)>0 else None,target_id=found.id if found else None,
                    canonical_name=found.name if found else _canonical_guess(title),brand=found.brand if found else infer_brand(title),storage_gb=storage,
                    raw={"id":item.get("id"),"original_price":item.get("original_price"),"official_store_id":item.get("official_store_id"),"catalog_product_id":item.get("catalog_product_id")})
            out.append(o)
        return _dedup(out)

    def _web_search(self,q:str,target:Target|None,targets:list[Target]):
        slug=re.sub(r"[^a-zA-Z0-9]+","-",q).strip("-")
        r=self.s.get(f"{self.WEB}/{quote_plus(slug)}",timeout=self.timeout); r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser"); out=[]
        cards=soup.select("li.ui-search-layout__item, div.poly-card, div.ui-search-result")
        if not cards:
            cards=[a.parent for a in soup.select("a.poly-component__title, a.ui-search-item__group__element") if a.parent]
        for c in cards:
            a=c.select_one("a.poly-component__title, a.ui-search-item__group__element, a[href]")
            if not a: continue
            title=(a.get("title") or a.get_text(" ",strip=True) or "").strip()
            if not title or is_accessory(title): continue
            cond=detect_condition(title)
            if cond in {"used","refurbished"}: continue
            p=_first_price(c.get_text(" ",strip=True))
            if not p or p<200: continue
            found=target or match_target(title,targets)
            storage=extract_storage_gb(title)
            if found and storage != found.storage_gb:
                continue
            if storage is None:
                continue
            out.append(Offer(source="mercadolivre_web",store="Mercado Livre",title=title,url=urljoin("https://www.mercadolivre.com.br",a.get("href") or ""),price_base=p,
                             condition=cond,target_id=found.id if found else None,canonical_name=found.name if found else _canonical_guess(title),
                             brand=found.brand if found else infer_brand(title),storage_gb=storage,
                             raw={"fallback":"public_search_html"}))
        return _dedup(out)

def _condition_from_attributes(item):
    for a in item.get("attributes") or []:
        if str(a.get("id") or "").upper() == "ITEM_CONDITION":
            return str(a.get("value_name") or a.get("value_id") or "")
    return ""

def _storage_from_attributes(item):
    for a in item.get("attributes") or []:
        aid=str(a.get("id") or "").upper()
        name=str(a.get("name") or "").lower()
        if aid in {"INTERNAL_MEMORY","STORAGE_CAPACITY","MEMORY_STORAGE_CAPACITY"} or "memória interna" in name or "armazenamento interno" in name:
            v=extract_storage_gb(str(a.get("value_name") or a.get("value_id") or ""))
            if v:
                return v
    return None

def _first_price(text:str):
    m=re.search(r"R\$\s*([0-9\.]+(?:,[0-9]{2})?)",text)
    if not m:return None
    try:return float(m.group(1).replace(".","").replace(",","."))
    except:return None

def _canonical_guess(title:str):
    t=norm(title)
    # Stable enough for grouping repeated discovery observations; original title remains available.
    t=re.sub(r"\b(5g|dual chip|smartphone|celular|novo|lacrado|ram|galaxy ai)\b"," ",t)
    t=re.sub(r"\b\d{1,2}\s*gb\s*ram\b"," ",t)
    t=re.sub(r"\s+"," ",t).strip()
    return t[:90]

def _dedup(items):
    seen=set(); out=[]
    for o in items:
        k=(o.url,o.title,round(o.price_final_direct,2))
        if k not in seen: seen.add(k); out.append(o)
    return out
