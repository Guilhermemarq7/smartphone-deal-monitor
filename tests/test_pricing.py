from src.pricing import real_discount, suspicious_outlier, summarize

def test_real_discount():
    assert round(real_discount(3000, 3600),4) == 0.1667

def test_outlier():
    assert suspicious_outlier(2000, 4000, .60)
    assert not suspicious_outlier(2800, 4000, .60)

def test_bootstrap_low_does_not_drag_median():
    s=summarize([],bootstrap_recent=3284.10,bootstrap_low=2149)
    assert s.median_30d == 3284.10
    assert s.min_90d == 2149
    assert s.used_bootstrap
