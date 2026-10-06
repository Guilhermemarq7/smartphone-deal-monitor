import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import requests

from src.alerts import send_operational_alert
from src.app import cli_main, run_once
from src.collectors.base import CollectorResult
from src.database import Database
from src.health import collection_health
from src.models import Offer
from src.config import load_config


def offer(target, store='Samsung', price=3199.9):
    return Offer('test_live', store, target.name, 'https://example.test/' + target.id,
                 price, condition='new', target_id=target.id, storage_gb=target.storage_gb)


def status(ok=True, reason='', name='Fonte'):
    return {'source': name, 'ok': ok, 'reason': reason, 'message': reason, 'state': 'live'}


@pytest.mark.parametrize('offers_spec,statuses,level', [
    ([(0,'Samsung'), (1,'Motorola')], [status()], 'HEALTHY'),
    ([(0,'Samsung'), (1,'Samsung')], [status()], 'DEGRADED'),
    ([(0,'Samsung'), (1,'Motorola')], [status(False,'http_403')], 'DEGRADED'),
    ([(0,'Samsung'), (1,'Motorola')], [status(False,'missing_credential')], 'DEGRADED'),
    ([(0,'Samsung'), (1,'Motorola')], [status(False,'cloud_disabled')], 'HEALTHY'),
    ([(0,'Samsung')], [status()], 'CRITICAL'),
    ([], [status()], 'CRITICAL'),
])
def test_health_counts_accepted_stores_and_coverage(targets, offers_spec, statuses, level):
    offers = [offer(targets[index], store) for index, store in offers_spec]
    assert collection_health(offers, statuses, targets, {}).level == level


def test_offline_and_discovery_never_prove_readiness(targets):
    unknown = offer(targets[0])
    unknown.target_id = 'discovery:unknown'
    assert collection_health([unknown], [], targets, {}).level == 'CRITICAL'
    assert collection_health([], [], targets, {}, offline=True).level == 'OFFLINE'


def test_operational_alert_persists_and_cooldown(monkeypatch, tmp_path, targets):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'mock-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'mock-chat')
    client = Mock()
    monkeypatch.setattr('src.alerts.TelegramClient', Mock(return_value=client))
    cfg = {'alerts': {'telegram': {'enabled': True}}, 'health': {'alert_cooldown_hours': 24}}
    health = collection_health([], [status(False, 'http_403')], targets, cfg)
    db = Database(tmp_path/'x.db')
    assert send_operational_alert(health, cfg, db)
    db.close()
    db = Database(tmp_path/'x.db')
    assert not send_operational_alert(health, cfg, db)
    assert client.send_message.call_count == 1
    message = client.send_message.call_args.args[1]
    assert 'ALERTA OPERACIONAL' in message and 'CRITICAL' in message
    assert db.conn.execute('SELECT count(*) FROM alert_events').fetchone()[0] == 0
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    with db.conn:
        db.conn.execute('UPDATE operational_alerts SET sent_at=?', (old,))
    assert send_operational_alert(health, cfg, db)
    assert client.send_message.call_count == 2
    db.close()


def test_failed_operational_delivery_retries_and_hides_token(monkeypatch, tmp_path, targets, capsys):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'mock-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'mock-chat')
    client = Mock()
    client.send_message.side_effect = requests.ConnectionError('https://api.telegram.org/botmock-token/sendMessage')
    monkeypatch.setattr('src.alerts.TelegramClient', Mock(return_value=client))
    cfg = {'alerts': {'telegram': {'enabled': True}}}
    health = collection_health([], [], targets, cfg)
    db = Database(tmp_path/'x.db')
    assert not send_operational_alert(health, cfg, db)
    assert not send_operational_alert(health, cfg, db)
    assert client.send_message.call_count == 2
    assert not db.operational_alert_recent('collection-critical-v1')
    assert 'mock-token' not in capsys.readouterr().out
    db.close()


def test_noncritical_and_missing_bindings_do_not_send(monkeypatch, tmp_path, targets):
    factory = Mock()
    monkeypatch.setattr('src.alerts.TelegramClient', factory)
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    cfg = {'alerts': {'telegram': {'enabled': True}}}
    db = Database(tmp_path/'x.db')
    for health in [collection_health([], [], targets, cfg), collection_health([], [], targets, cfg, offline=True)]:
        assert not send_operational_alert(health, cfg, db)
    factory.assert_not_called()
    db.close()


def test_one_source_failure_does_not_break_reports_or_history(monkeypatch, tmp_path, targets):
    cfg = {'budget': {'ideal': 3000, 'soft_limit': 3200, 'exceptional_limit': 3500},
           'output': {'dir': str(tmp_path/'output')}, 'discovery': {'enabled': True}}
    failed = Mock(name='failed')
    failed.name = 'Falhou'
    failed.collect.side_effect = requests.ConnectionError('secret must not be logged')
    failed.discover.return_value = CollectorResult('Falhou discovery', [], False, 'connection_error')
    good = Mock(name='good')
    good.name = 'Funcionou'
    good.collect.return_value = CollectorResult('Funcionou', [offer(t) for t in targets], True)
    good.discover.return_value = CollectorResult('Funcionou discovery', [], True)
    monkeypatch.setattr('src.app._collectors', lambda *_: iter([('bad',failed,''), ('good',good,'')]))
    db = Database(tmp_path/'x.db')
    db.upsert_targets(targets)
    db.seed_bootstrap(targets)
    deals, health = run_once(cfg, targets, db, no_alerts=True, return_health=True)
    assert len(deals) == 2 and health.level == 'DEGRADED'
    assert deals[0].stats.samples_30d == 0
    assert deals[0].stats.median_30d == 4000
    assert db.stats_for('s25',4000,3000).samples_30d == 1
    assert db.conn.execute('SELECT count(*) FROM collector_runs').fetchone()[0] == 4
    report = (tmp_path/'output/report.md').read_text()
    assert 'DEGRADED' in report and 'connection_error' in report
    assert 'secret must not be logged' not in report
    db.close()


def test_invalid_offer_cannot_make_health_healthy(monkeypatch, tmp_path, targets):
    cfg = {'budget': {'ideal': 3000, 'soft_limit': 3200, 'exceptional_limit': 3500},
           'output': {'dir': str(tmp_path/'output')}, 'discovery': {'enabled': False}}
    wrong = offer(targets[0]); wrong.title = 'Galaxy S25 FE 256GB'
    conditional = offer(targets[1]); conditional.requires_tradein = True
    bad = Mock(); bad.name = 'Invalid'
    bad.collect.return_value = CollectorResult('Invalid', [wrong, conditional], True)
    monkeypatch.setattr('src.app._collectors', lambda *_: iter([('bad',bad,'')]))
    db = Database(tmp_path/'x.db')
    deals, health = run_once(cfg, targets, db, no_alerts=True, return_health=True)
    assert deals == [] and health.level == 'CRITICAL'
    assert db.conn.execute('SELECT count(*) FROM price_observations').fetchone()[0] == 0
    db.close()


def test_cloud_skips_magalu_and_does_not_require_telegram(monkeypatch, tmp_path, targets):
    cfg = {'budget': {'ideal': 3000, 'soft_limit': 3200, 'exceptional_limit': 3500},
           'sources': {'magalu': {'enabled': True, 'cloud_enabled': False}, 'mercadolivre': {'enabled': True}},
           'discovery': {'enabled': True}, 'output': {'dir': str(tmp_path/'output')}}
    monkeypatch.delenv('ML_ACCESS_TOKEN', raising=False)
    monkeypatch.setattr('src.app.MagaluCollector', Mock(side_effect=AssertionError('Magalu must be skipped')))
    monkeypatch.setattr('requests.Session.get', Mock(side_effect=AssertionError('No network without token')))
    db = Database(tmp_path/'x.db')
    _, health = run_once(cfg, targets, db, cloud=True, no_alerts=True, return_health=True)
    assert health.level == 'CRITICAL'
    report = (tmp_path/'output/report.md').read_text()
    assert 'cloud_disabled' in report and 'ML_ACCESS_TOKEN ausente' in report
    db.close()


def test_critical_exit_code_still_generates_summary_and_closes_db(monkeypatch, tmp_path):
    cfg = load_config('config.yaml')
    cfg['sources'] = {}
    cfg['output'] = {'dir': str(tmp_path/'output')}
    cfg['database']['path'] = str(tmp_path/'x.db')
    monkeypatch.setattr('src.app.load_config', lambda _: cfg)
    monkeypatch.setattr('sys.argv', ['main.py', '--cloud', '--no-alerts', '--fail-on-critical'])
    assert cli_main() == 2
    result = json.loads((tmp_path/'output/health.json').read_text())
    assert result['level'] == 'CRITICAL'
    assert 'CRITICAL' in (tmp_path/'output/report.md').read_text()
    db = Database(tmp_path/'x.db')
    assert db.conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()
    monkeypatch.setattr('sys.argv', ['main.py', '--offline', '--no-alerts', '--fail-on-critical'])
    assert cli_main() == 0
    assert json.loads((tmp_path/'output/health.json').read_text())['level'] == 'OFFLINE'
