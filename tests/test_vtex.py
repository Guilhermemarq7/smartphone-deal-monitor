import json
from pathlib import Path
from urllib.parse import parse_qs
from unittest.mock import Mock

import pytest
import requests

from src.collectors.vtex import VtexCollector, _pix_price

STORE = {'name': 'Fast Shop', 'base_url': 'https://site.fastshop.com.br', 'currency': 'BRL', 'seller_ids': ['1'], 'new_products_only': True}


def product(**changes):
    data = {'productId': '12', 'productName': 'Samsung Galaxy S25 256GB',
            'link': 'https://site.fastshop.com.br/galaxy-s25/p', 'categories': ['/Celulares/'],
            'items': [{'itemId': '34', 'nameComplete': 'Samsung Galaxy S25 256GB Preto',
                       'sellers': [{'sellerId': '1', 'sellerName': 'Fast Shop',
                                    'commertialOffer': {'Price': 3500, 'ListPrice': 5999, 'IsAvailable': True, 'AvailableQuantity': 10,
                                                       'Teasers': [{'Name': 'Cupom não confirmado'}], 'RewardValue': 200,
                                                       'Installments': [{'Value': 350, 'NumberOfInstallments': 10}],
                                                       'PaymentOptions': {'paymentSystems': [
                                                           {'id': 125, 'groupName': 'instantPaymentPaymentGroup', 'requiresAuthentication': False},
                                                           {'id': 99, 'groupName': 'creditCardPaymentGroup', 'requiresAuthentication': False}],
                                                           'installmentOptions': [
                                                               {'paymentSystem': '125', 'bin': None, 'installments': [{'count': 1, 'hasInterestRate': False, 'total': 315000}]},
                                                               {'paymentSystem': '99', 'installments': [{'count': 1, 'hasInterestRate': False, 'total': 100000}]}]}}}]}]}
    data.update(changes)
    return data


def parse(data, targets):
    return VtexCollector({})._parse([data], STORE, targets[0], targets)


def test_public_api_preserves_full_price_pix_seller_and_sku(targets):
    offers = parse(product(), targets)
    assert len(offers) == 1
    o = offers[0]
    assert (o.price_base, o.price_pix, o.price_final_direct, o.price_list) == (3500, 3150, 3150, 5999)
    assert o.cashback == o.coupon_discount == 0
    assert o.shipping is None and o.seller_id == '1'
    assert o.condition == 'new' and o.storage_gb == 256 and o.target_id == 's25'
    assert o.raw['sku_id'] == '34' and 'skuId=34' in o.url
    assert not o.is_official_store


@pytest.mark.parametrize('title', ['Galaxy S25 128GB', 'Galaxy S25+ 256GB', 'Galaxy S25 FE 256GB',
                                   'Capa Galaxy S25 256GB', 'Galaxy S25 256GB Usado', 'Galaxy S25 256GB Recondicionado', 'Galaxy S25'])
def test_sku_filters(targets, title):
    p = product()
    p['items'][0]['nameComplete'] = title
    assert parse(p, targets) == []


@pytest.mark.parametrize('field,value', [('IsAvailable',False), ('AvailableQuantity',0), ('Price',float('nan')), ('PriceValidUntil','2000-01-01')])
def test_stock_and_price_filters(targets, field, value):
    p = product()
    p['items'][0]['sellers'][0]['commertialOffer'][field] = value
    assert parse(p, targets) == []


def test_first_party_new_only_and_product_link_scope(targets):
    p = product()
    p['items'][0]['sellers'][0]['sellerId'] = 'marketplace'
    assert parse(p, targets) == []
    p = product(categories=['/Seminovos/'])
    assert parse(p, targets) == []
    assert parse(product(link='https://evil.example.test/p'), targets) == []
    p = product(); p['items'][0]['isKit'] = True
    assert parse(p, targets) == []
    assert VtexCollector({})._parse([product()], dict(STORE, currency='USD'), targets[0], targets) == []
    assert parse(product(brand='Realme'),targets) == []


def test_pix_not_installment_card_or_authenticated_discount():
    c = product()['items'][0]['sellers'][0]['commertialOffer']
    assert _pix_price(c) == 3150
    c['PaymentOptions']['paymentSystems'][0]['requiresAuthentication'] = True
    assert _pix_price(c) is None
    c['PaymentOptions']['paymentSystems'][0]['requiresAuthentication'] = False
    c['PaymentOptions']['installmentOptions'][0]['installments'][0]['count'] = 10
    assert _pix_price(c) is None
    c['PaymentOptions']['installmentOptions'][0]['installments'][0]['count'] = 1
    c['PaymentOptions']['installmentOptions'][0]['bin'] = 'restricted-card'
    assert _pix_price(c) is None


def test_vtex_query_bounded_and_discovery_mocked(targets):
    c = VtexCollector({'stores': [dict(STORE, discovery_queries=['Samsung Galaxy S25'])], 'results_per_query': 900, 'min_delay_seconds': 0})
    r = Mock(); r.json.return_value = [product()]
    c.s.get = Mock(return_value=r)
    assert c.collect(targets[:1]).offers[0].price_pix == 3150
    params=c.s.get.call_args.kwargs['params']
    assert parse_qs(params) == {'ft': [targets[0].name], '_from': ['0'], '_to': ['49']}
    assert '%20' in params and '+' not in params
    assert 'Authorization' not in c.s.headers
    assert c.discover(targets).offers[0].target_id == 's25'


def test_blocked_retailer_does_not_stop_other_retailer_and_discovery(targets):
    other = dict(STORE, name='Motorola', base_url='https://www.motorola.com.br')
    c = VtexCollector({'stores': [dict(STORE, discovery_queries=['Samsung']), other], 'min_delay_seconds': 0})
    denied = requests.Response(); denied.status_code = 403
    p = product(link='https://www.motorola.com.br/s25/p')
    good = Mock(); good.json.return_value = [p]
    c.s.get = Mock(side_effect=[denied,good,good])
    result = c.collect(targets)
    assert len(result.offers) == 1 and not result.ok
    assert c.s.get.call_count == 3
    assert c.discover(targets).state == 'skipped'
    assert c.s.get.call_count == 3


def test_malformed_response_is_reported_not_silent_zero(targets):
    c = VtexCollector({'stores': [STORE], 'min_delay_seconds': 0})
    r = Mock(); r.json.return_value = {'error': 'not a catalog'}
    c.s.get = Mock(return_value=r)
    result = c.collect(targets[:1])
    assert not result.ok and 'invalid_response' in result.message


def test_captured_fastshop_catalog_core_fields():
    from src.config import load_config, targets_from_config
    cfg = load_config('config.yaml')
    targets = targets_from_config(cfg)
    fixture = json.loads(Path('tests/fixtures/vtex_fastshop_product.json').read_text())
    offers = VtexCollector({})._parse([fixture], cfg['sources']['vtex']['stores'][0], None, targets)
    assert len(offers) == 1
    assert offers[0].target_id == 'galaxy_s25_fe_256'
    assert offers[0].seller == 'Ponto'
    assert (offers[0].price_base, offers[0].price_pix) == (4398.99, 4091.06)
    assert offers[0].raw['sku_id'] == '147839'


def test_model_numbers_cannot_be_inferred_from_memory_capacity():
    from src.config import load_config, targets_from_config
    targets = targets_from_config(load_config('config.yaml'))
    store = dict(STORE, name='Motorola')
    p = product(productName='Motorola Edge 60 Pro 256GB')
    p['items'][0]['nameComplete'] = 'Motorola Edge 60 Pro 256GB'
    assert VtexCollector({})._parse([p], store, targets[2], targets) == []
