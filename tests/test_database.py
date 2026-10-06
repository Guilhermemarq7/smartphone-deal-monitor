from src.database import Database
from src.models import Target

def test_bootstrap_seed_once(tmp_path):
    db=Database(tmp_path/'x.db')
    t=Target('x','Phone X 256GB','X',['Phone X 256GB'],256,3000,2800,2600,'high',80,3200,2500)
    db.upsert_targets([t]); db.seed_bootstrap([t]); db.seed_bootstrap([t])
    n=db.conn.execute('select count(*) from price_observations where is_bootstrap=1').fetchone()[0]
    assert n == 2
    s=db.stats_for('x',3200,2500)
    assert s.median_30d == 3200
    assert s.min_90d == 2500
    db.close()
