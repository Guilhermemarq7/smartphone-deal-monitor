from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class CollectionHealth:
    level: str
    live_stores: list[str]
    covered_targets: list[str]
    target_count: int
    offers_count: int
    failures: list[str]
    message: str

    def to_dict(self):
        return asdict(self)


def collection_health(offers, statuses, targets, cfg, offline=False):
    known = {t.id for t in targets}
    # Bootstrap and discovery cannot turn a broken watchlist into HEALTHY.
    watched = [o for o in offers if o.target_id in known]
    stores = sorted({o.store for o in watched})
    covered = sorted({o.target_id for o in watched})
    failures = sorted({s['source'] for s in statuses if not s['ok'] and s.get('reason') not in {'cloud_disabled', 'disabled', 'not_configured'}})
    hcfg = cfg.get('health', {})
    critical_min = min(len(known), int(hcfg.get('critical_min_targets', 2)))
    if offline:
        level, message = 'OFFLINE', 'Execução sem rede: saúde live não avaliada.'
    elif not watched or len(covered) < critical_min:
        level, message = 'CRITICAL', 'Cobertura live insuficiente; não confie na ausência de alertas de preço.'
    elif (len(stores) >= int(hcfg.get('healthy_min_stores', 2))
          and len(covered) / max(1, len(known)) >= float(hcfg.get('healthy_min_coverage', 0.5)) and not failures):
        level, message = 'HEALTHY', 'Múltiplas lojas e cobertura mínima produziram ofertas validadas.'
    else:
        level, message = 'DEGRADED', 'Há preços live úteis, mas existem falhas ou cobertura limitada.'
    return CollectionHealth(level, stores, covered, len(known), len(offers), failures, message)
