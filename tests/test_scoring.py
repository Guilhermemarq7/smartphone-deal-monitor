from src.models import Offer, Target, Stats
from src.scoring import score_deal

CFG={'budget':{'ideal':3000,'soft_limit':3200,'exceptional_limit':3500},'analysis':{'outlier_ratio':.60}}
T=Target('s24u','Galaxy S24 Ultra 256GB','Samsung',['Galaxy S24 Ultra 256GB'],256,3900,3700,3500,'very_high',96)

def test_exceptional_legit_offer():
    o=Offer('test','Samsung','Galaxy S24 Ultra 256GB','https://x',3449,seller='Samsung',is_official_store=True,condition='new',storage_gb=256,target_id='s24u')
    d=score_deal(o,T,Stats(median_30d=4300,min_90d=3447),CFG)
    assert d.score >= 80
    assert 'OUTLIER' not in d.classification

def test_outlier_is_capped():
    o=Offer('test','Mercado Livre','Galaxy S24 Ultra 256GB','https://x',1900,condition='new',storage_gb=256,target_id='s24u')
    d=score_deal(o,T,Stats(median_30d=4300,min_90d=3447),CFG)
    assert d.suspicious_outlier
    assert d.score <= 60
    assert d.classification == 'OUTLIER — VERIFICAR'
