from __future__ import annotations

import json,re,time
from bs4 import BeautifulSoup
from .base import CollectorResult, build_session
from ..models import Offer,Target
from ..normalize import detect_condition,extract_storage_gb,match_target,parse_brl

class StructuredPageCollector:
    name="Páginas oficiais"
    def __init__(self,cfg:dict):
        self.cfg=cfg; self.pages=cfg.get("pages",[]); self.timeout=float(cfg.get("timeout_seconds",12))
        self.delay=float(cfg.get("min_delay_seconds",1.5)); self.s=build_session(cfg.get("user_agent","Mozilla/5.0 SmartphoneDealMonitor/1.0"),int(cfg.get("retries",2)))
    def collect(self,targets:list[Target])->CollectorResult:
        tmap={t.id:t for t in targets}; offers=[]; errors=[]
        for i,p in enumerate(self.pages):
            if not p.get("enabled",True): continue
            try:
                r=self.s.get(p["url"],timeout=self.timeout); r.raise_for_status();
                o=self._parse(r.text,p,tmap.get(p.get("target_id")),targets)
                if o: offers.append(o)
                else: errors.append(f"{p.get('target_id')}: nenhum preço confiável no HTML")
            except Exception as e: errors.append(f"{p.get('target_id')}: {type(e).__name__}: {e}")
            if i<len(self.pages)-1: time.sleep(self.delay)
        return CollectorResult(self.name,offers,bool(offers) or not errors,f"{len(offers)} ofertas; "+(" | ".join(errors[:4]) if errors else "ok"))
    def _parse(self,html,p,target,targets):
        soup=BeautifulSoup(html,"html.parser"); candidates=[]; title=None; url=p["url"]
        for node in soup.select('script[type="application/ld+json"]'):
            try:
                data=json.loads(node.string or node.get_text())
                objs=data if isinstance(data,list) else [data]
                for obj in objs:
                    if not isinstance(obj,dict): continue
                    if obj.get("@type") in ("Product",["Product"]):
                        title=title or obj.get("name")
                        off=obj.get("offers")
                        if isinstance(off,dict): off=[off]
                        if isinstance(off,list):
                            for x in off:
                                if isinstance(x,dict):
                                    v=parse_brl(x.get("price") or x.get("lowPrice"));
                                    if v: candidates.append((v,"jsonld"))
            except Exception:
                continue
        for sel,attr in [('meta[property="product:price:amount"]','content'),('meta[itemprop="price"]','content')]:
            for n in soup.select(sel):
                v=parse_brl(n.get(attr));
                if v:candidates.append((v,"meta"))
        text=soup.get_text(" ",strip=True)
        if not title:
            h=soup.find("h1"); title=h.get_text(" ",strip=True) if h else (target.name if target else p.get("target_id","produto"))
        # Conservative text fallback. Reject impossible/parcel values later.
        for m in re.finditer(r"R\$\s*([0-9\.]+,[0-9]{2})",text):
            v=parse_brl(m.group(0));
            if v and 500<=v<=20000:candidates.append((v,"text"))
        if not candidates:return None
        # Prefer structured sources; if none, choose plausible full price nearest configured current threshold range, not installment values.
        structured=[v for v,s in candidates if s in {"jsonld","meta"} and v>=500]
        vals=structured or [v for v,s in candidates if v>=1000]
        if not vals:return None
        price=min(vals)
        found=target or match_target(title,targets)
        cond=detect_condition(title)
        lowtext=text.lower()
        pixvals=[]
        for m in re.finditer(r"R\$\s*([0-9\.]+,[0-9]{2}).{0,60}?pix",text,re.I):
            v=parse_brl(m.group(0));
            if v and v>=500: pixvals.append(v)
        pix=min(pixvals) if pixvals else None
        notes=[]
        if "troca smart" in lowtext or "troca seu" in lowtext:
            notes.append("programa de troca aparece na página; o monitor NÃO assume que o preço depende dele sem evidência no preço")
        return Offer(source="official_page_html",store=p.get("store","Loja oficial"),title=title,url=url,price_base=price,price_pix=pix,
                     seller=p.get("store"),is_official_store=True,condition=cond if cond!="unknown" else "new",target_id=found.id if found else None,
                     canonical_name=found.name if found else title,brand=found.brand if found else None,storage_gb=extract_storage_gb(title) or (found.storage_gb if found else None),
                     requires_tradein=False,notes=notes,raw={"parser":"jsonld/meta/text","price_candidates_count":len(candidates),"tradein_program_present":bool(notes)})
