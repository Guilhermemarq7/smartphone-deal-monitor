from __future__ import annotations

import time
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from .base import CollectorResult, build_session, error_reason, stop_source
from .structured_pages import _price
from ..models import Offer
from ..normalize import detect_condition, extract_storage_gb, infer_brand, is_accessory, match_target, parse_brl, norm


SEARCH_PATH = '/api/catalog_system/pub/products/search'


def _pix_price(commercial):
    """Use full one-payment Pix totals in cents, never installment value minima."""
    options = commercial.get('PaymentOptions') or {}
    systems = {str(s['id']) for s in options.get('paymentSystems', [])
               if s.get('groupName') == 'instantPaymentPaymentGroup'
               and s.get('requiresAuthentication') is False}
    prices = []
    for option in options.get('installmentOptions', []):
        if str(option.get('paymentSystem')) not in systems or option.get('bin'):
            continue
        for installment in option.get('installments', []):
            total = parse_brl(installment.get('total'))
            if (installment.get('count') == 1 and installment.get('hasInterestRate') is False
                    and total is not None and total > 0):
                prices.append(total / 100)
    return min(prices) if prices else None


class VtexCollector:
    """Read documented public catalog searches from explicitly configured retailers.

    No private catalog API, checkout mutation, cookies or authentication is used.
    Stores must be live-verified before being enabled. Bound queries and results.
    """
    name = 'Catálogos públicos VTEX'

    def __init__(self, cfg):
        self.cfg = cfg
        self.stores = cfg.get('stores', [])
        self.timeout = float(cfg.get('timeout_seconds', 12))
        self.delay = float(cfg.get('min_delay_seconds', 1.5))
        self.limit = max(1, min(50, int(cfg.get('results_per_query', 50))))
        self.s = build_session(cfg.get('user_agent', 'SmartphoneDealMonitor/1.0'), int(cfg.get('retries', 1)))
        self.blocked = set()

    def collect(self, targets):
        plan = [(store, target.name, target) for store in self.stores if store.get('enabled', True)
                for target in targets if not store.get('target_ids') or target.id in store['target_ids']]
        return self._queries(plan, targets, self.name)

    def discover(self, targets):
        plan = [(store, query, None) for store in self.stores if store.get('enabled', True)
                for query in store.get('discovery_queries', [])]
        if not plan:
            return CollectorResult(self.name + ' discovery', [], True, 'Discovery não configurado', 'skipped', 'not_configured')
        return self._queries(plan, targets, self.name + ' discovery')

    def _queries(self, plan, targets, name):
        offers, errors = [], []
        queried = 0
        for i, (store, query, target) in enumerate(plan):
            origin = store['base_url'].rstrip('/')
            if origin in self.blocked:
                continue
            try:
                queried += 1
                # This public endpoint rejects '+' for spaces with HTTP 400.
                # Use standard percent-encoding (%20), keeping the same honest UA.
                query_params={'ft': query, '_from': 0, '_to': self.limit - 1}
                if store.get('filters'): query_params['fq']=store['filters']
                params=urlencode(query_params,doseq=True,quote_via=quote)
                response = self.s.get(origin + SEARCH_PATH, params=params, timeout=self.timeout)
                response.raise_for_status()
                products = response.json()
                if not isinstance(products, list):
                    raise ValueError('Resposta de catálogo deve ser uma lista')
                offers.extend(self._parse(products, store, target, targets))
            except Exception as exc:
                reason = error_reason(exc)
                errors.append(f"{store['name']}: {reason}")
                if stop_source(exc):
                    self.blocked.add(origin)
            if i < len(plan) - 1:
                time.sleep(self.delay)
        unique = {(o.store, o.raw['sku_id'], o.seller_id): o for o in offers}
        message = f'{len(unique)} ofertas; {queried} consultas públicas'
        if errors:
            message += '; ' + ' | '.join(sorted(set(errors)))
        state = 'skipped' if plan and queried == 0 else 'live'
        return CollectorResult(name, list(unique.values()), not errors and state == 'live', message, state,
                               'source_blocked' if state == 'skipped' else ('partial_failure' if errors else ''))

    def _parse(self, products, store, target, targets):
        out = []
        if store.get('currency') != 'BRL':
            return out
        origin = urlparse(store['base_url'])
        for product in products:
            if not isinstance(product, dict):
                continue
            product_title = str(product.get('productName') or '')
            if is_accessory(product_title):
                continue
            categories = ' '.join(product.get('categories') or [])
            for sku in product.get('items') or []:
                if not isinstance(sku, dict) or sku.get('isKit'):
                    continue
                title = str(sku.get('nameComplete') or product_title)
                if is_accessory(title):
                    continue
                condition = detect_condition(title + ' ' + categories)
                if condition in {'used', 'refurbished'}:
                    continue
                storage = extract_storage_gb(title)
                found = match_target(title, targets)
                if not storage or (target and (not found or target.id != found.id)):
                    continue
                catalog_brand=norm(str(product.get('brand') or ''))
                if found and catalog_brand and catalog_brand != norm(found.brand):
                    if not (norm(found.brand) == 'poco' and catalog_brand == 'xiaomi'):
                        continue
                # Accept only an explicit retail seller allowlist; unknown marketplace
                # sellers cannot inherit trust/condition from a catalog title.
                for seller in sku.get('sellers') or []:
                    seller_id = str(seller.get('sellerId') or '')
                    if seller_id not in store.get('seller_ids', ['1']):
                        continue
                    commercial = seller.get('commertialOffer') or {}
                    if not commercial.get('IsAvailable') or commercial.get('AvailableQuantity', 0) <= 0:
                        continue
                    price = _price({'price': commercial.get('Price'), 'priceCurrency': store['currency'],
                                    'priceValidUntil': commercial.get('PriceValidUntil')})
                    if price is None:
                        continue
                    pix = _pix_price(commercial)
                    # Pix below plausible full-device floor must not become a price.
                    if pix is not None and not 500 <= pix <= price:
                        pix = None
                    url = product.get('link') or ''
                    parsed = urlparse(url)
                    if parsed.scheme != 'https' or parsed.hostname != origin.hostname:
                        continue
                    params = dict(parse_qsl(parsed.query))
                    params[store.get('sku_query_param', 'skuId')] = str(sku['itemId'])
                    url = urlunparse(parsed._replace(query=urlencode(params)))
                    new = condition == 'new' or store.get('new_products_only', False)
                    if not new:
                        continue
                    out.append(Offer(source='vtex_public_api', store=store['name'], title=title,
                                     url=url, price_base=price, price_pix=pix, price_list=parse_brl(commercial.get('ListPrice')),
                                     seller=seller.get('sellerName'), seller_id=seller_id,
                                     is_official_store=bool(store.get('manufacturer_official', False)), condition='new', stock='available',
                                     storage_gb=storage, target_id=found.id if found else None,
                                     canonical_name=found.name if found else title, brand=found.brand if found else infer_brand(title),
                                     notes=['Catálogo público por SKU; estoque/preço podem variar no checkout. Frete não consultado.'],
                                     raw={'product_id': product.get('productId'), 'sku_id': str(sku['itemId']),
                                          'price_list': commercial.get('ListPrice'), 'currency': 'BRL',
                                          'price_valid_until': commercial.get('PriceValidUntil'),
                                          'teasers_ignored': len(commercial.get('Teasers') or [])}))
        return out
