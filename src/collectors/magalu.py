from __future__ import annotations

import re,time
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from .base import CollectorResult, build_session
from ..models import Offer, Target
from ..normalize import detect_condition, extract_storage_gb, is_accessory, match_target, infer_brand

class MagaluCollector:
    name="Magalu"
    def __init__(self,cfg:dict):
        self.cfg=cfg; self.timeout=float(cfg.get("timeout_seconds",12)); self.delay=float(cfg.get("min_delay_seconds",1.5))
        self.s=build_session(cfg.get("user_agent","Mozilla/5.0 SmartphoneDealMonitor/1.0"),int(cfg.get("retries",2)))

    def collect(self,targets:list[Target])->CollectorResult:
        offers=[]; errors=[]
        for i,t in enumerate(targets):
            try: offers.extend(self._search(t.name,t,targets))
            except Exception as e: errors.append(f"{t.id}: {type(e).__name__}: {e}")
            if i<len(targets)-1: time.sleep(self.delay)
        return CollectorResult(self.name,offers,bool(offers) or not errors,(f"{len(offers)} ofertas"+(f"; {len(errors)} falhas" if errors else "")))

    def discover(self,targets:list[Target])->CollectorResult:
        qs=self.cfg.get("discovery_queries",["galaxy s ultra","motorola edge pro","xiaomi","iphone"]); offers=[]; errors=[]
        for q in qs:
            try: offers.extend(self._search(q,None,targets))
            except Exception as e: errors.append(f"{q}: {e}")
            time.sleep(self.delay)
        return CollectorResult(self.name+" discovery",offers,bool(offers) or not errors,"; ".join(errors[:3]) if errors else f"{len(offers)} candidatos")

    def _search(self,q:str,target:Target|None,targets:list[Target]):
        url="https://www.magazineluiza.com.br/busca/"+quote(q,safe="")+"/"
        r=self.s.get(url,timeout=self.timeout); r.raise_for_status(); soup=BeautifulSoup(r.text,"html.parser")
        out=[]; links=soup.select('a[href*="/p/"]')
        for a in links:
            href=a.get("href") or ""; title=(a.get("title") or a.get("aria-label") or a.get_text(" ",strip=True) or "").strip()
            if len(title)<12:
                h=a.find(["h2","h3"]); title=h.get_text(" ",strip=True) if h else title
            if not title or is_accessory(title): continue
            cond=detect_condition(title)
            if cond in {"used","refurbished"}: continue
            container=a
            for _ in range(5):
                if container.parent: container=container.parent
                txt=container.get_text(" ",strip=True)
                if "R$" in txt and len(txt)<3500: break
            txt=container.get_text(" ",strip=True)
            pix=_context_price(txt,"pix")
            prices=_all_prices(txt)
            base=(pix or (min(prices) if prices else None))
            if not base or base<200: continue
            found=target or match_target(title,targets)
            storage=extract_storage_gb(title)
            if found and storage != found.storage_gb:
                continue
            if storage is None:
                continue
            seller="Magalu" if re.search(r"vendido\s+e\s+entregue\s+por\s+magalu",txt,re.I) else None
            coupon=_coupon_value(txt)
            notes=[]
            if coupon:
                notes.append(f"cupom anunciado de até R$ {coupon:.2f} NÃO aplicado automaticamente; conferir código/validade/eligibilidade no checkout")
            out.append(Offer(source="magalu_html",store="Magalu",title=title,url=urljoin("https://www.magazineluiza.com.br",href),price_base=float(base),price_pix=float(pix) if pix else None,
                coupon_discount=0.0,seller=seller,is_official_store=bool(seller),condition=cond,target_id=found.id if found else None,
                canonical_name=found.name if found else title[:90],brand=found.brand if found else infer_brand(title),storage_gb=storage,
                coupon_limited=bool(coupon),notes=notes,raw={"search_url":url,"snippet":txt[:600],"advertised_coupon_discount":coupon}))
        # hrefs may repeat for images/title; dedup by URL and keep cheapest parsed version.
        best={}
        for o in out:
            k=o.url
            if k not in best or o.price_final_direct<best[k].price_final_direct: best[k]=o
        return list(best.values())

def _all_prices(text):
    vals=[]
    for m in re.finditer(r"R\$\s*([0-9\.]+,[0-9]{2})",text):
        try:
            v=float(m.group(1).replace(".","").replace(",","."))
            if 200<=v<=30000: vals.append(v)
        except Exception:
            continue
    return vals

def _context_price(text,word):
    # price usually appears immediately before "no Pix" on Magalu pages/cards.
    pat=re.compile(r"R\$\s*([0-9\.]+,[0-9]{2}).{0,45}?"+re.escape(word),re.I)
    vals=[]
    for m in pat.finditer(text):
        try: vals.append(float(m.group(1).replace(".","").replace(",",".")))
        except Exception:
            continue
    return min(vals) if vals else None

def _coupon_value(text):
    m=re.search(r"(?:cupom\s*)?R\$\s*([0-9\.]+(?:,[0-9]{2})?)\s*OFF",text,re.I)
    if not m:return None
    try:return float(m.group(1).replace(".","").replace(",","."))
    except:return None
