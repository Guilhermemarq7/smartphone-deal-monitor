from __future__ import annotations

import argparse,logging,time
from datetime import datetime,timezone
from pathlib import Path
from dotenv import load_dotenv
from .config import load_config,targets_from_config
from .database import Database
from .collectors.mercadolivre import MercadoLivreCollector
from .collectors.magalu import MagaluCollector
from .collectors.structured_pages import StructuredPageCollector
from .discovery import filter_discovery
from .scoring import score_deal
from .reporting import write_reports,print_terminal
from .alerts import send_optional_alerts


def cli_main():
    parser=argparse.ArgumentParser(description="Radar de preços de smartphones no Brasil")
    parser.add_argument("--config",default="config.yaml"); parser.add_argument("--db",default=None)
    parser.add_argument("--watch",action="store_true"); parser.add_argument("--interval-minutes",type=float,default=None)
    parser.add_argument("--offline",action="store_true",help="Não acessa a internet; valida configuração/banco e gera relatório vazio")
    parser.add_argument("--validate",action="store_true",help="Valida configuração e banco e encerra")
    args=parser.parse_args(); load_dotenv()
    cfg=load_config(args.config); _setup_dirs(cfg); _setup_logging(cfg)
    targets=targets_from_config(cfg); db=Database(args.db or cfg.get("database",{}).get("path","data/radar.db"))
    db.upsert_targets(targets); db.seed_bootstrap(targets,cfg.get("bootstrap",{}).get("research_date","2026-10-05"))
    if args.validate:
        print(f"Configuração OK. {len(targets)} variantes monitoradas. Banco: {db.path}"); db.close(); return 0
    try:
        while True:
            run_once(cfg,targets,db,offline=args.offline)
            if not args.watch: break
            mins=args.interval_minutes or float(cfg["monitor"].get("interval_minutes",30))
            print(f"\nPróxima coleta em {mins:g} min. Ctrl+C para encerrar.")
            time.sleep(max(60,mins*60))
    except KeyboardInterrupt: print("\nMonitor encerrado pelo usuário.")
    finally: db.close()
    return 0


def run_once(cfg,targets,db,offline=False):
    statuses=[]; all_offers=[]
    if not offline:
        collectors=[]; scfg=cfg.get("sources",{})
        if scfg.get("mercadolivre",{}).get("enabled",True): collectors.append(MercadoLivreCollector(scfg["mercadolivre"]))
        if scfg.get("magalu",{}).get("enabled",True): collectors.append(MagaluCollector(scfg["magalu"]))
        if scfg.get("official_pages",{}).get("enabled",True): collectors.append(StructuredPageCollector(scfg["official_pages"]))
        for c in collectors:
            started=datetime.now(timezone.utc).isoformat()
            try:
                r=c.collect(targets); all_offers.extend(r.offers); statuses.append({"source":r.source,"ok":r.ok,"message":r.message}); db.record_run(started,r.source,"ok" if r.ok else "error",r.message,len(r.offers))
            except Exception as e:
                msg=f"{type(e).__name__}: {e}"; statuses.append({"source":getattr(c,"name",type(c).__name__),"ok":False,"message":msg}); db.record_run(started,getattr(c,"name",type(c).__name__),"error",msg,0)
        if cfg.get("discovery",{}).get("enabled",True):
            disc=[]
            for c in collectors:
                if hasattr(c,"discover"):
                    started=datetime.now(timezone.utc).isoformat()
                    try:
                        r=c.discover(targets); disc.extend(r.offers); statuses.append({"source":r.source,"ok":r.ok,"message":r.message}); db.record_run(started,r.source,"ok" if r.ok else "error",r.message,len(r.offers))
                    except Exception as e: statuses.append({"source":getattr(c,"name","collector")+" discovery","ok":False,"message":str(e)})
            all_offers.extend(filter_discovery(disc,cfg))
    else: statuses.append({"source":"offline","ok":True,"message":"rede desabilitada por --offline"})

    # Strict validation/dedup before persisting.
    unique={}
    tmap={t.id:t for t in targets}
    for o in all_offers:
        if o.condition in {"used","refurbished"}: continue
        if o.price_final_direct < 200 or o.price_final_direct > float(cfg.get("analysis",{}).get("max_plausible_price",20000)): continue
        if not o.target_id:
            canon=(o.canonical_name or o.title).strip().lower()[:80]
            o.target_id="discovery:"+canon
        key=(o.store,o.url,o.target_id,round(o.price_final_direct,2))
        if key not in unique: unique[key]=o
    offers=list(unique.values())

    # Score against history that existed BEFORE this collection. Only after scoring do we persist
    # the current observation, so an absurd current price cannot pull its own median downward.
    deals=[]
    for o in offers:
        target=tmap.get(o.target_id)
        stats=db.stats_for(o.target_id, target.bootstrap_recent if target else None, target.bootstrap_low if target else None)
        deals.append(score_deal(o,target,stats,cfg))
    for o in offers:
        db.add_offer(o)
    out=Path(cfg.get("output",{}).get("dir","output")); write_reports(deals,statuses,out); print_terminal(deals,statuses)
    send_optional_alerts(deals,cfg,db,Path(cfg.get("alerts",{}).get("log_file","logs/opportunities.log")))
    dcfg=cfg.get("database",{})
    db.prune(dcfg.get("retention_days",120),dcfg.get("collector_run_retention_days",30),dcfg.get("alert_event_retention_days",30))
    return deals


def _setup_dirs(cfg):
    for d in [Path("data"),Path(cfg.get("output",{}).get("dir","output")),Path("logs")]: d.mkdir(parents=True,exist_ok=True)

def _setup_logging(cfg):
    logging.basicConfig(filename=cfg.get("logging",{}).get("file","logs/radar.log"),level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",encoding="utf-8")
