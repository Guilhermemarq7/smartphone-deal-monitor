from __future__ import annotations

import argparse
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .config import load_config, targets_from_config
from .database import Database
from .collectors.base import CollectorResult, error_reason
from .collectors.mercadolivre import MercadoLivreCollector
from .collectors.magalu import MagaluCollector
from .collectors.structured_pages import StructuredPageCollector
from .collectors.vtex import VtexCollector
from .discovery import filter_discovery
from .normalize import extract_storage_gb, is_accessory, match_target
from .scoring import score_deal
from .reporting import write_reports, print_terminal
from .health import collection_health
from .alerts import send_optional_alerts, send_operational_alert


def cli_main():
    parser = argparse.ArgumentParser(description='Radar de preços de smartphones no Brasil')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--db', default=None)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval-minutes', type=float, default=None)
    parser.add_argument('--offline', action='store_true', help='Não acessa a internet; saúde live não avaliada')
    parser.add_argument('--validate', action='store_true', help='Valida configuração e banco e encerra')
    parser.add_argument('--cloud', action='store_true', help='Usa somente fontes habilitadas para cloud; automático no GitHub Actions')
    parser.add_argument('--no-alerts', action='store_true', help='Não envia mensagens durante a coleta controlada')
    parser.add_argument('--fail-on-critical', action='store_true', help='Retorna 2 quando a coleta live é CRITICAL; gera relatórios primeiro')
    args = parser.parse_args()
    load_dotenv()
    cfg = load_config(args.config)
    _setup_dirs(cfg)
    _setup_logging(cfg)
    targets = targets_from_config(cfg)
    db = Database(args.db or cfg.get('database', {}).get('path', 'data/radar.db'))
    exit_code = 0
    try:
        db.upsert_targets(targets)
        db.seed_bootstrap(targets, cfg.get('bootstrap', {}).get('research_date', '2026-10-05'))
        if args.validate:
            print(f'Configuração OK. {len(targets)} variantes monitoradas. Banco: {db.path}')
            return 0
        while True:
            _, health = run_once(cfg, targets, db, offline=args.offline,
                                 cloud=args.cloud or os.getenv('GITHUB_ACTIONS', '').lower() == 'true',
                                 no_alerts=args.no_alerts, return_health=True)
            exit_code = 2 if args.fail_on_critical and health.level == 'CRITICAL' else 0
            if not args.watch:
                break
            mins = args.interval_minutes or float(cfg['monitor'].get('interval_minutes', 30))
            print(f'\nPróxima coleta em {mins:g} min. Ctrl+C para encerrar.')
            time.sleep(max(60, mins * 60))
    except KeyboardInterrupt:
        print('\nMonitor encerrado pelo usuário.')
    finally:
        db.close()
    return exit_code


def _collectors(cfg, cloud):
    factories = {'mercadolivre': MercadoLivreCollector, 'magalu': MagaluCollector,
                 'official_pages': StructuredPageCollector, 'structured_pages': StructuredPageCollector,
                 'vtex': VtexCollector}
    for name, factory in factories.items():
        scfg = cfg.get('sources', {}).get(name)
        if scfg is None:
            continue
        if not scfg.get('enabled', True):
            yield name, None, 'disabled'
        elif cloud and not scfg.get('cloud_enabled', name != 'magalu'):
            yield name, None, 'cloud_disabled'
        else:
            yield name, factory(scfg, cloud=cloud) if name == 'mercadolivre' else factory(scfg), ''


def _execute(collector, method, targets, db):
    started = datetime.now(timezone.utc).isoformat()
    name = collector.name + (' discovery' if method == 'discover' else '')
    try:
        result = getattr(collector, method)(targets)
    except Exception as exc:
        reason = error_reason(exc)
        result = CollectorResult(name, [], False, reason, reason=reason)
    db.record_run(started, result.source, result.state if result.state != 'live' else ('ok' if result.ok else 'error'), result.message, len(result.offers))
    status = {'source': result.source, 'ok': result.ok, 'message': result.message,
              'state': result.state, 'reason': result.reason, 'offers_count': len(result.offers)}
    return result.offers, status


def _valid_offer(o, targets, cfg):
    if is_accessory(o.title) or o.condition in {'used', 'refurbished'}:
        return False
    if cfg.get('condition', {}).get('new_only', True) and o.condition != 'new':
        return False
    if any((o.requires_tradein, o.requires_card, o.requires_subscription, o.requires_first_purchase)):
        return False
    if o.coupon_limited and o.coupon_discount:
        return False
    if not math.isfinite(o.price_final_direct) or not 200 <= o.price_final_direct <= float(cfg.get('analysis', {}).get('max_plausible_price', 20000)):
        return False
    if not o.url.startswith('https://') or not o.storage_gb:
        return False
    explicit_storage = extract_storage_gb(o.title)
    if explicit_storage and explicit_storage != o.storage_gb:
        return False
    if o.target_id:
        matched = match_target(o.title if explicit_storage else o.title + f' {o.storage_gb}GB', targets)
        if not matched or matched.id != o.target_id or matched.storage_gb != o.storage_gb:
            return False
    return True


def run_once(cfg, targets, db, offline=False, cloud=None, no_alerts=False, return_health=False):
    if cloud is None:
        cloud = os.getenv('GITHUB_ACTIONS', '').lower() == 'true'
    statuses, all_offers = [], []
    if not offline:
        collectors = []
        for name, collector, reason in _collectors(cfg, cloud):
            if collector is None:
                statuses.append({'source': name, 'ok': True, 'message': 'Fonte desabilitada: ' + reason,
                                 'state': 'skipped', 'reason': reason, 'offers_count': 0})
                continue
            collectors.append(collector)
            offers, status = _execute(collector, 'collect', targets, db)
            all_offers.extend(offers)
            statuses.append(status)
        if cfg.get('discovery', {}).get('enabled', True):
            discovery = []
            for collector in collectors:
                if hasattr(collector, 'discover'):
                    offers, status = _execute(collector, 'discover', targets, db)
                    discovery.extend(offers)
                    statuses.append(status)
            all_offers.extend(filter_discovery(discovery, cfg))
    else:
        statuses.append({'source': 'offline', 'ok': True, 'message': 'rede desabilitada por --offline', 'state': 'skipped'})

    unique = {}
    tmap = {t.id: t for t in targets}
    for offer in all_offers:
        if not _valid_offer(offer, targets, cfg):
            continue
        if not offer.target_id:
            canon = (offer.canonical_name or offer.title).strip().lower()[:80]
            offer.target_id = 'discovery:' + canon
        key = (offer.store, offer.url, offer.target_id, round(offer.price_final_direct, 2))
        unique.setdefault(key, offer)
    offers = list(unique.values())
    # Score before any current observation is persisted; keep bootstrap/history semantics.
    deals = []
    for offer in offers:
        target = tmap.get(offer.target_id)
        stats = db.stats_for(offer.target_id, target.bootstrap_recent if target else None, target.bootstrap_low if target else None)
        deals.append(score_deal(offer, target, stats, cfg))
    for offer in offers:
        db.add_offer(offer)
    health = collection_health(offers, statuses, targets, cfg, offline)
    out = Path(cfg.get('output', {}).get('dir', 'output'))
    write_reports(deals, statuses, out, health)
    print_terminal(deals, statuses, health)
    if not no_alerts:
        send_optional_alerts(deals, cfg, db, Path(cfg.get('alerts', {}).get('log_file', 'logs/opportunities.log')))
        send_operational_alert(health, cfg, db)
    dcfg = cfg.get('database', {})
    db.prune(dcfg.get('retention_days', 120), dcfg.get('collector_run_retention_days', 30), dcfg.get('alert_event_retention_days', 30))
    return (deals, health) if return_health else deals


def _setup_dirs(cfg):
    for d in [Path('data'), Path(cfg.get('output', {}).get('dir', 'output')), Path('logs')]:
        d.mkdir(parents=True, exist_ok=True)


def _setup_logging(cfg):
    logging.basicConfig(filename=cfg.get('logging', {}).get('file', 'logs/radar.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
