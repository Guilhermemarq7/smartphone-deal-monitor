from __future__ import annotations

import json, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .models import Offer, Target
from .pricing import summarize

SCHEMA="""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, brand TEXT, priority TEXT, upgrade_score REAL, aspirational INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS variants(
 id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL, storage_gb INTEGER NOT NULL,
 alert_below REAL, strong_buy_below REAL, dream_price REAL,
 UNIQUE(product_id, storage_gb), FOREIGN KEY(product_id) REFERENCES products(id)
);
CREATE TABLE IF NOT EXISTS stores(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, source TEXT);
CREATE TABLE IF NOT EXISTS sellers(
 id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER, external_id TEXT, name TEXT, reputation_level TEXT,
 is_official INTEGER DEFAULT 0, updated_at TEXT, UNIQUE(store_id, external_id, name)
);
CREATE TABLE IF NOT EXISTS price_observations(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 observed_at TEXT NOT NULL, product_id TEXT, storage_gb INTEGER, source TEXT NOT NULL, store TEXT NOT NULL,
 seller TEXT, url TEXT, title TEXT, price_base REAL, price_pix REAL, coupon_code TEXT, coupon_discount REAL DEFAULT 0,
 cashback REAL DEFAULT 0, shipping REAL, price_final_direct REAL NOT NULL, price_effective_cashback REAL NOT NULL,
 condition TEXT, stock TEXT, is_bootstrap INTEGER DEFAULT 0, bootstrap_kind TEXT,
 requires_tradein INTEGER DEFAULT 0, requires_card INTEGER DEFAULT 0, requires_subscription INTEGER DEFAULT 0,
 requires_first_purchase INTEGER DEFAULT 0, raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_prices_product_time ON price_observations(product_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_prices_url_time ON price_observations(url, observed_at);
CREATE TABLE IF NOT EXISTS promotions(
 id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT, product_id TEXT, store TEXT, kind TEXT, code TEXT,
 value REAL, conditions TEXT, url TEXT
);
CREATE TABLE IF NOT EXISTS alerts(
 id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, product_id TEXT, url TEXT, score REAL,
 classification TEXT, price REAL, UNIQUE(product_id, url, classification, price)
);
CREATE TABLE IF NOT EXISTS collector_runs(
 id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT, source TEXT, status TEXT, message TEXT, offers_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alert_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, product_id TEXT,
 url TEXT, store TEXT, seller TEXT, score REAL, classification TEXT, price REAL, channel TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_events_fp_time ON alert_events(fingerprint, created_at);
"""

class Database:
    def __init__(self,path:str|Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(self.path)
        self.conn.row_factory=sqlite3.Row
        self.conn.executescript(SCHEMA); self.conn.commit()

    def close(self):
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.commit()
        finally:
            self.conn.close()

    def upsert_targets(self, targets:list[Target]):
        with self.conn:
            for t in targets:
                self.conn.execute("INSERT INTO products(id,name,brand,priority,upgrade_score,aspirational) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,brand=excluded.brand,priority=excluded.priority,upgrade_score=excluded.upgrade_score,aspirational=excluded.aspirational",
                                  (t.id,t.name,t.brand,t.priority,t.upgrade_score,int(t.aspirational)))
                self.conn.execute("INSERT INTO variants(product_id,storage_gb,alert_below,strong_buy_below,dream_price) VALUES(?,?,?,?,?) ON CONFLICT(product_id,storage_gb) DO UPDATE SET alert_below=excluded.alert_below,strong_buy_below=excluded.strong_buy_below,dream_price=excluded.dream_price",
                                  (t.id,t.storage_gb,t.alert_below,t.strong_buy_below,t.dream_price))

    def seed_bootstrap(self, targets:list[Target], source_date:str="2026-10-05"):
        key="bootstrap_seed_v1"
        if self.conn.execute("SELECT 1 FROM metadata WHERE key=?",(key,)).fetchone(): return
        at=f"{source_date}T12:00:00-03:00"
        with self.conn:
            for t in targets:
                vals=[("recent_reference",t.bootstrap_recent),("historical_low",t.bootstrap_low)]
                for kind,price in vals:
                    if price:
                        self.conn.execute("""INSERT INTO price_observations(observed_at,product_id,storage_gb,source,store,title,price_base,price_final_direct,price_effective_cashback,condition,is_bootstrap,bootstrap_kind,raw_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(at,t.id,t.storage_gb,"markdown_initial_research","reference",t.name,price,price,price,"new",1,kind,json.dumps({"source":"data/bootstrap/radar_celulares_10-10_2026.md"},ensure_ascii=False)))
            self.conn.execute("INSERT INTO metadata(key,value) VALUES(?,?)",(key,datetime.now(timezone.utc).isoformat()))

    def add_offer(self,o:Offer):
        now=datetime.now(timezone.utc).isoformat()
        self.conn.execute("""INSERT INTO price_observations(observed_at,product_id,storage_gb,source,store,seller,url,title,price_base,price_pix,coupon_code,coupon_discount,cashback,shipping,price_final_direct,price_effective_cashback,condition,stock,is_bootstrap,requires_tradein,requires_card,requires_subscription,requires_first_purchase,raw_json)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (now,o.target_id,o.storage_gb,o.source,o.store,o.seller,o.url,o.title,o.price_base,o.price_pix,o.coupon_code,o.coupon_discount,o.cashback,o.shipping,o.price_final_direct,o.price_effective_cashback,o.condition,o.stock,0,int(o.requires_tradein),int(o.requires_card),int(o.requires_subscription),int(o.requires_first_purchase),json.dumps(o.raw,ensure_ascii=False,default=str)))
        self.conn.commit()

    def stats_for(self, product_id:str, bootstrap_recent:float|None=None, bootstrap_low:float|None=None):
        now=datetime.now(timezone.utc)
        since=(now-timedelta(days=90)).isoformat()
        rows=self.conn.execute("SELECT observed_at,price_final_direct FROM price_observations WHERE product_id=? AND is_bootstrap=0 AND observed_at>=? AND condition NOT IN ('used','refurbished')",(product_id,since)).fetchall()
        vals=[]
        for r in rows:
            try:
                dt=datetime.fromisoformat(r["observed_at"])
                if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                age=(now-dt.astimezone(timezone.utc)).total_seconds()/86400
                vals.append((max(0,age),float(r["price_final_direct"])))
            except Exception:
                continue
        return summarize(vals,bootstrap_recent=bootstrap_recent,bootstrap_low=bootstrap_low)

    def stats_for_title(self, canonical_name:str, storage_gb:int|None, bootstrap_recent:float|None=None, bootstrap_low:float|None=None):
        return self.stats_for("discovery:"+canonical_name,bootstrap_recent,bootstrap_low)

    def record_alert(self, product_id:str|None, url:str, score:float, classification:str, price:float) -> bool:
        try:
            self.conn.execute("INSERT INTO alerts(created_at,product_id,url,score,classification,price) VALUES(?,?,?,?,?,?)",
                              (datetime.now(timezone.utc).isoformat(),product_id,url,score,classification,round(price,2)))
            self.conn.commit(); return True
        except sqlite3.IntegrityError:
            return False


    def was_alerted_recently(self, fingerprint:str, within_hours:float=24) -> bool:
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=max(0,float(within_hours)))).isoformat()
        row=self.conn.execute("SELECT 1 FROM alert_events WHERE fingerprint=? AND created_at>=? LIMIT 1",(fingerprint,cutoff)).fetchone()
        return bool(row)

    def record_alert_event(self, fingerprint:str, deal, channel:str="remote"):
        o=deal.offer
        self.conn.execute("""INSERT INTO alert_events(fingerprint,created_at,product_id,url,store,seller,score,classification,price,channel)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(fingerprint,datetime.now(timezone.utc).isoformat(),o.target_id,o.url,o.store,o.seller,deal.score,deal.classification,round(o.price_final_direct,2),channel))
        self.conn.commit()


    def prune(self, price_days:int=120, run_days:int=30, alert_days:int=30):
        now=datetime.now(timezone.utc)
        pcut=(now-timedelta(days=max(1,int(price_days)))).isoformat()
        rcut=(now-timedelta(days=max(1,int(run_days)))).isoformat()
        acut=(now-timedelta(days=max(1,int(alert_days)))).isoformat()
        with self.conn:
            self.conn.execute("DELETE FROM price_observations WHERE is_bootstrap=0 AND observed_at<?",(pcut,))
            self.conn.execute("DELETE FROM collector_runs WHERE finished_at<?",(rcut,))
            self.conn.execute("DELETE FROM alert_events WHERE created_at<?",(acut,))

    def record_run(self, started:str, source:str, status:str, message:str, count:int):
        self.conn.execute("INSERT INTO collector_runs(started_at,finished_at,source,status,message,offers_count) VALUES(?,?,?,?,?,?)",
                          (started,datetime.now(timezone.utc).isoformat(),source,status,message,count)); self.conn.commit()
