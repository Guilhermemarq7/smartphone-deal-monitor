from __future__ import annotations

import os,re,time
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
from .base import CollectorResult, build_session, error_reason, stop_source
from ..models import Offer, Target
from ..normalize import detect_condition, extract_storage_gb, is_accessory, match_target, infer_brand, norm, parse_brl

class MercadoLivreCollector:
    name="Mercado Livre"
    API="https://api.mercadolibre.com"
    WEB="https://lista.mercadolivre.com.br"

    def __init__(self,cfg:dict,cloud:bool=False):
        self.cfg=cfg
        self.timeout=float(cfg.get("timeout_seconds",12)); self.delay=float(cfg.get("min_delay_seconds",1.2))
        self.limit=int(cfg.get("results_per_query",20)); self.token=os.getenv("ML_ACCESS_TOKEN","").strip()
        self.s=build_session(cfg.get("user_agent","SmartphoneDealMonitor/1.0"),int(cfg.get("retries",2)))
        self.cloud=cloud
        self.web=build_session(cfg.get("user_agent","SmartphoneDealMonitor/1.0"),int(cfg.get("retries",2)))
        self.blocked=""

    def collect(self, targets:list[Target]) -> CollectorResult:
        return self._queries([(t.name,t) for t in targets],targets,self.name)

    def discover(self, targets:list[Target]) -> CollectorResult:
        queries=self.cfg.get("discovery_queries",["Samsung Galaxy 256GB","Motorola Edge Pro 256GB","Xiaomi 256GB","POCO 512GB","iPhone 128GB"])
        return self._queries([(q,None) for q in queries],targets,self.name+" discovery")

    def _queries(self,queries,targets,name):
        fallback=not self.cloud and self.cfg.get("public_web_fallback",False)
        if self.blocked:
            return CollectorResult(name,[],False,"Fonte suspensa nesta coleta: "+self.blocked,"skipped",self.blocked)
        if not self.token and not fallback:
            return CollectorResult(name,[],False,"ML_ACCESS_TOKEN ausente; API não consultada. Fallback HTML desativado.","skipped","missing_credential")
        offers=[]; errors=[]
        for i,(q,target) in enumerate(queries):
            try:
                offers.extend(self._api_search(q,target,targets) if self.token else self._web_search(q,target,targets))
            except Exception as exc:
                reason=error_reason(exc); errors.append(reason)
                if stop_source(exc):
                    self.blocked=reason
                    break
            if i < len(queries)-1:
                time.sleep(self.delay)
        msg=f"{len(offers)} ofertas; {len(errors)} falhas"
        if errors: msg+="; "+", ".join(sorted(set(errors)))+". 401/403 não prova que um token resolverá acesso."
        return CollectorResult(name,_dedup(offers),not errors,msg,reason=errors[0] if errors else "")

    def _api_search(self,q:str,target:Target|None,targets:list[Target]):
        url=self.API+"/sites/MLB/search"
        if not self.token:
            raise ValueError("ML_ACCESS_TOKEN ausente")
        # Authentication is scoped to the official API, never the HTML fallback.
        r=self.s.get(url,params={"q":q,"limit":self.limit,"condition":"new"},headers={"Authorization":"Bearer "+self.token},timeout=self.timeout)
        r.raise_for_status(); data=r.json(); out=[]
        for item in data.get("results",[]):
            title=str(item.get("title") or "")
            if is_accessory(title): continue
            cond=detect_condition(title,_condition_from_attributes(item) or str(item.get("condition") or ""))
            if cond in {"used","refurbished"}: continue
            price=item.get("price")
            price=parse_brl(price)
            if price is None or price<200 or item.get("currency_id") != "BRL": continue
            if item.get("available_quantity") == 0: continue
            title_storage=extract_storage_gb(title)
            attribute_storage=_storage_from_attributes(item)
            if title_storage and attribute_storage and title_storage != attribute_storage: continue
            storage=title_storage or attribute_storage
            found=match_target(title+f" {storage}GB" if storage else title,targets)
            if target and (not found or found.id != target.id): continue
            if found and storage != found.storage_gb:
                continue
            if storage is None:
                continue
            seller=item.get("seller") or {}
            seller_level=seller.get("reputation_level_id") or seller.get("seller_reputation",{}).get("level_id")
            url=item.get("permalink") or ""
            if not url.startswith("https://"): continue
            o=Offer(source="mercadolivre_api",store="Mercado Livre",title=title,url=url,price_base=float(price),
                    seller=str(seller.get("nickname") or seller.get("id") or "") or None,seller_id=str(seller.get("id") or "") or None,
                    seller_level=str(seller_level or "") or None,is_official_store=bool(item.get("official_store_id")),condition=cond,
                    shipping=0.0 if (item.get("shipping") or {}).get("free_shipping") is True else None,
                    stock="available" if (item.get("available_quantity") or 0)>0 else None,target_id=found.id if found else None,
                    canonical_name=found.name if found else _canonical_guess(title),brand=found.brand if found else infer_brand(title),storage_gb=storage,
                    price_list=parse_brl(item.get("original_price")),raw={"id":item.get("id"),"original_price":item.get("original_price"),"official_store_id":item.get("official_store_id"),"catalog_product_id":item.get("catalog_product_id")})
            out.append(o)
        return _dedup(out)

    def _web_search(self,q:str,target:Target|None,targets:list[Target]):
        slug=re.sub(r"[^a-zA-Z0-9]+","-",q).strip("-")
        r=self.web.get(f"{self.WEB}/{quote_plus(slug)}",timeout=self.timeout); r.raise_for_status()
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
            found=match_target(title,targets)
            if target and (not found or found.id != target.id): continue
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
