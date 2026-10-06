from src.alerts import alert_fingerprint, should_notify
from src.models import Deal, Offer, Stats

CFG={"alerts":{"min_score":76,"alert_outliers":True}}

def deal(price=3000, score=90, outlier=False, classification="OFERTA EXCEPCIONAL"):
    o=Offer("test","Loja","Phone X 256GB","https://x",price,condition="new",storage_gb=256,target_id="x",seller="Seller")
    return Deal(o,score,classification,None,None,Stats(median_30d=4000,min_90d=2900),outlier,[])

def test_outlier_not_silenced_by_score_cap():
    d=deal(price=1900,score=60,outlier=True,classification="OUTLIER — VERIFICAR")
    assert should_notify(d,CFG)

def test_fingerprint_changes_when_price_changes():
    assert alert_fingerprint(deal(3000)) != alert_fingerprint(deal(2900))
