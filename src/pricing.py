from __future__ import annotations

from statistics import median, pstdev
from .models import Stats


def real_discount(current: float, median_30d: float | None) -> float | None:
    if not median_30d or median_30d <= 0:
        return None
    return 1 - current / median_30d


def distance_from_low(current: float, low: float | None) -> float | None:
    if not low or low <= 0:
        return None
    return current / low - 1


def suspicious_outlier(current: float, median_30d: float | None, ratio: float = 0.60) -> bool:
    return bool(median_30d and current < median_30d * ratio)


def summarize(
    prices_by_age: list[tuple[float, float]],
    bootstrap_recent: float | None = None,
    bootstrap_low: float | None = None,
) -> Stats:
    """Compute rolling stats.

    During cold start, the Markdown's *recent/current reference* may support the median,
    while its historical low is used only as a floor. This avoids an exceptional one-off
    historical low dragging the median down.
    """
    def vals(days):
        return [p for age, p in prices_by_age if age <= days and p > 0]

    own7, own30, own90 = vals(7), vals(30), vals(90)
    v7, v30, v90 = own7[:], own30[:], own90[:]
    used = False
    if len(own30) < 5 and bootstrap_recent:
        used = True
        v30.append(float(bootstrap_recent))
        v90.append(float(bootstrap_recent))
        if not v7 and not prices_by_age:
            v7.append(float(bootstrap_recent))

    def med(v): return median(v) if v else None
    def mn(v): return min(v) if v else None

    min7 = mn(v7)
    min30 = mn(v30)
    min90 = mn(v90)
    if bootstrap_low:
        used = used or len(own90) < 5
        # The historical reference is a floor signal, not evidence of today's median.
        min90 = min(x for x in [min90, float(bootstrap_low)] if x is not None)
        if not own30:
            min30 = min(x for x in [min30, float(bootstrap_low)] if x is not None)
        if not own7 and not prices_by_age:
            min7 = min(x for x in [min7, float(bootstrap_low)] if x is not None)

    m30 = med(v30)
    vol = (pstdev(v30) / m30) if len(v30) >= 2 and m30 else None
    return Stats(
        median_7d=med(v7), median_30d=m30, median_90d=med(v90),
        min_7d=min7, min_30d=min30, min_90d=min90,
        volatility_30d=vol, samples_30d=len(own30), used_bootstrap=used,
    )
