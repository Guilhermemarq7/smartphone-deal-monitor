from src.database import Database
from src.models import Deal, Offer, Stats


def test_alert_dedupe_window(tmp_path):
    db=Database(tmp_path/'x.db')
    o=Offer('test','Loja','Phone X 256GB','https://x',2999,condition='new',target_id='x',storage_gb=256)
    d=Deal(o,90,'OFERTA EXCEPCIONAL',None,None,Stats())
    assert not db.was_alerted_recently('abc',24)
    db.record_alert_event('abc',d,'telegram')
    assert db.was_alerted_recently('abc',24)
    assert not db.was_alerted_recently('different',24)
    db.close()
