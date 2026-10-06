import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from src.collectors.base import error_reason
from src.collectors.mercadolivre import MercadoLivreCollector
from src.collectors.magalu import MagaluCollector
from src.collectors.structured_pages import StructuredPageCollector
from src.normalize import detect_condition, match_target, is_accessory


def response(status=200, data=None, text=''):
    r = requests.Response()
    r.status_code = status
    r.url = 'https://api.example.test/path'
    r._content = (json.dumps(data) if data is not None else text).encode()
    return r


def item(**overrides):
    data = {'title': 'Samsung Galaxy S25 256GB', 'price': 3199.9, 'currency_id': 'BRL',
            'condition': 'new', 'permalink': 'https://produto.mercadolivre.com.br/item',
            'available_quantity': 1, 'original_price': 5999,
            'seller': {'id': 7, 'nickname': 'Loja', 'seller_reputation': {'level_id': '5_green'}},
            'official_store_id': 1, 'shipping': {'free_shipping': True}}
    data.update(overrides)
    return data


def test_ml_missing_token_never_calls_network(monkeypatch, targets):
    monkeypatch.delenv('ML_ACCESS_TOKEN', raising=False)
    c = MercadoLivreCollector({}, cloud=True)
    c.s.get = Mock(side_effect=AssertionError('API not allowed'))
    c.web.get = Mock(side_effect=AssertionError('HTML not allowed'))
    for result in (c.collect(targets), c.discover(targets)):
        assert result.state == 'skipped'
        assert result.reason == 'missing_credential'
        assert not result.offers
    c.s.get.assert_not_called()
    c.web.get.assert_not_called()


def test_ml_authenticated_payload_and_filters(monkeypatch, targets):
    monkeypatch.setenv('ML_ACCESS_TOKEN', 'mock-token')
    c = MercadoLivreCollector({'min_delay_seconds': 0}, cloud=True)
    c.s.get = Mock(return_value=response(data={'results': [
        item(), item(title='Samsung Galaxy S25 FE 256GB'), item(title='Capa Galaxy S25 256GB'),
        item(title='Galaxy S25 128GB'), item(condition='used'), item(condition='refurbished'),
        item(currency_id='USD'), item(available_quantity=0), item(price=float('nan')),
        item(attributes=[{'id': 'INTERNAL_MEMORY', 'value_name': '128GB'}]),
    ]}))
    result = c.collect(targets[:1])
    assert result.ok and len(result.offers) == 1
    offer = result.offers[0]
    assert (offer.price_base, offer.price_list, offer.shipping) == (3199.9, 5999, 0)
    assert offer.seller_id == '7' and offer.seller_level == '5_green' and offer.is_official_store
    kwargs = c.s.get.call_args.kwargs
    assert kwargs['headers'] == {'Authorization': 'Bearer mock-token'}
    assert kwargs['params']['condition'] == 'new'
    assert 'Authorization' not in c.web.headers


@pytest.mark.parametrize('status', [401, 403, 429])
def test_ml_access_denial_stops_collect_and_discovery(monkeypatch, targets, status):
    monkeypatch.setenv('ML_ACCESS_TOKEN', 'mock-token')
    c = MercadoLivreCollector({'min_delay_seconds': 0}, cloud=True)
    c.s.get = Mock(return_value=response(status))
    result = c.collect(targets)
    assert not result.ok and result.reason == f'http_{status}'
    assert c.discover(targets).state == 'skipped'
    assert c.s.get.call_count == 1
    assert 'mock-token' not in result.message


def test_ml_attribute_storage_and_discovery(monkeypatch, targets):
    monkeypatch.setenv('ML_ACCESS_TOKEN', 'mock-token')
    c = MercadoLivreCollector({'discovery_queries': ['Galaxy S25'], 'min_delay_seconds': 0}, cloud=True)
    c.s.get = Mock(return_value=response(data={'results': [item(title='Samsung Galaxy S25', attributes=[{'id': 'INTERNAL_MEMORY', 'value_name': '256GB'}])]}))
    result = c.discover(targets)
    assert result.ok and result.offers[0].target_id == 's25'


def test_ml_local_html_opt_in_does_not_receive_auth(monkeypatch, targets):
    monkeypatch.delenv('ML_ACCESS_TOKEN', raising=False)
    c = MercadoLivreCollector({'public_web_fallback': True, 'min_delay_seconds': 0})
    c.web.get = Mock(return_value=response(text='<div class="poly-card"><a class="poly-component__title" href="https://example.test/p">Galaxy S25 256GB novo lacrado</a><span>R$ 3.199,90</span></div>'))
    assert c.collect(targets[:1]).offers[0].target_id == 's25'
    assert 'headers' not in c.web.get.call_args.kwargs


def test_magalu_denial_circuit(targets):
    c = MagaluCollector({'min_delay_seconds': 0})
    c.s.get = Mock(return_value=response(403))
    result = c.collect(targets)
    assert not result.ok and result.reason == 'http_403'
    assert c.discover(targets).state == 'skipped'
    assert c.s.get.call_count == 1


def test_magalu_wrong_variant_is_not_assigned_to_query(targets):
    c = MagaluCollector({})
    c.s.get = Mock(return_value=response(text='<div><a href="/produto/p/123" title="Galaxy S25 FE 256GB novo lacrado">Galaxy S25 FE 256GB</a> R$ 2.500,00 no Pix</div>'))
    assert c._search('Galaxy S25', targets[0], targets) == []


def test_structured_graph_for_additional_store(targets):
    html = Path('tests/fixtures/structured_product.html').read_text()
    c = StructuredPageCollector({'pages': []})
    offer = c._parse(html, {'url': 'https://loja.example.test/s25', 'store': 'Loja de teste'}, targets[0], targets)
    assert offer.price_base == 3199.9 and offer.price_final_direct == 3199.9
    assert offer.storage_gb == 256 and offer.condition == 'new'
    assert not offer.is_official_store and offer.seller == 'Loja de teste'
    assert offer.coupon_discount == offer.cashback == 0


@pytest.mark.parametrize('change', [
    {'name': 'Samsung Galaxy S25 FE 256GB'}, {'name': 'Samsung Galaxy S25 128GB'},
    {'name': 'Capa Samsung Galaxy S25 256GB'}, {'name': 'Samsung Galaxy S25'},
    {'name': 'Samsung Galaxy S25 256GB recondicionado'},
    {'offers': {'price': '3199.90', 'priceCurrency': 'USD'}},
    {'offers': {'price': '3199.90', 'priceCurrency': 'BRL', 'itemCondition': 'https://schema.org/UsedCondition'}},
    {'offers': {'price': '3199.90', 'priceCurrency': 'BRL', 'availability': 'https://schema.org/OutOfStock'}},
    {'offers': {'@type': 'AggregateOffer', 'lowPrice': '3199.90', 'priceCurrency': 'BRL'}},
    {'offers': {'price': '3199.90', 'priceCurrency': 'BRL', 'priceValidUntil': '2000-01-01'}},
    {'offers': {'price': '3199.90', 'priceCurrency': 'BRL', 'eligibleCustomerType': 'members'}},
    {'offers': {'price': '3199.90', 'priceCurrency': 'BRL', 'description': 'Preço com troca smart'}},
    {'offers': {'price': 'NaN', 'priceCurrency': 'BRL'}},
])
def test_structured_rejects_unproven_prices(targets, change):
    product = {'@type': 'Product', 'name': 'Samsung Galaxy S25 256GB', 'offers': {'price': '3199.90', 'priceCurrency': 'BRL'}}
    product.update(change)
    html = '<script type="application/ld+json">' + json.dumps(product) + '</script><h1>Galaxy S25 256GB</h1><meta property="product:price:amount" content="1999"><meta property="product:price:currency" content="BRL">'
    assert StructuredPageCollector({})._parse(html, {'url': 'https://shop.samsung.com/br/p', 'store': 'Samsung'}, targets[0], targets) is None


def test_structured_does_not_use_text_installment_or_assume_capacity(targets):
    c = StructuredPageCollector({})
    page = {'url': 'https://shop.samsung.com/br/p', 'store': 'Samsung'}
    assert c._parse('<h1>Galaxy S25 256GB</h1>12x R$ 299,00; cashback R$ 500,00', page, targets[0], targets) is None
    assert c._parse('<h1>Galaxy S25</h1><meta property="product:price:amount" content="3199.90"><meta property="product:price:currency" content="BRL">', page, targets[0], targets) is None


def test_structured_403_per_host_and_other_host_survives(targets):
    c = StructuredPageCollector({'min_delay_seconds': 0, 'pages': [
        {'url': 'https://shop.samsung.com/p', 'store': 'Samsung', 'target_id': 's25'},
        {'url': 'https://shop.samsung.com/p2', 'store': 'Samsung', 'target_id': 's26'},
        {'url': 'https://other.example.test/p', 'store': 'Loja', 'target_id': 's25'}]})
    c.s.get = Mock(side_effect=[response(403), response(text=Path('tests/fixtures/structured_product.html').read_text())])
    result = c.collect(targets)
    assert not result.ok and len(result.offers) == 1
    assert c.s.get.call_count == 2


@pytest.mark.parametrize('title', ['Galaxy S25 FE 256GB', 'Galaxy S25 Ultra 256GB', 'Galaxy S25 Plus 256GB', 'Galaxy S25+ 256GB', 'Galaxy S25 Edge 256GB', 'Galaxy S26 128GB', 'Capa Galaxy S25 256GB'])
def test_variant_matching_is_exact(targets, title):
    assert match_target(title, targets) is None


def test_condition_and_accessory_word_boundaries():
    assert detect_condition('Galaxy S25 256GB', 'used') == 'used'
    assert detect_condition('Galaxy S25 256GB', 'https://schema.org/RefurbishedCondition') == 'refurbished'
    assert not is_accessory('Telefone Galaxy S25 capacidade 256GB')
    assert is_accessory('Capa para Galaxy S25')


def test_camera_and_ram_plus_symbols_do_not_change_phone_model(targets):
    assert match_target('Samsung Galaxy S25 256GB 12GB RAM+12GB Boost Câmera 50+12+10MP',targets).id == 's25'


def test_model_numbers_and_spaced_capacity_are_preserved():
    from src.config import load_config,targets_from_config
    targets=targets_from_config(load_config('config.yaml'))
    assert match_target('Motorola Edge 70 Pro 256 GB',targets).id == 'edge_70_pro_256'
    assert match_target('Motorola Edge 60 Pro 256GB',targets) is None
    assert match_target('Motorola Edge 70 Pro 512GB',targets) is None
    assert match_target('Apple iPhone 16 128 GB',targets).id == 'iphone_16_128'
    assert match_target('Apple iPhone 15 128 GB',targets).id == 'iphone_15_128'
    assert match_target('Realme 15T 256GB',targets) is None
    assert match_target('Xiaomi 15T 256GB',targets).id == 'xiaomi_15t_256'
    assert match_target('Xiaomi POCO F7 512GB',targets).id == 'poco_f7_512'


def test_diagnostics_do_not_echo_secret_urls():
    exc = requests.ConnectionError('https://api.telegram.org/botSECRET/sendMessage')
    assert error_reason(exc) == 'connection_error'
