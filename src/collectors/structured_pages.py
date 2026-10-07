from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import CollectorResult, build_session, error_reason, stop_source
from ..models import Offer, Target
from ..normalize import detect_condition, extract_storage_gb, match_target, parse_brl, norm


def _objects(value):
    """Walk public JSON-LD graphs, including ProductGroup/hasVariant."""
    if isinstance(value, list):
        for item in value:
            yield from _objects(item)
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _objects(child)


def _kind(obj, kind):
    types = obj.get('@type') or []
    if isinstance(types, str):
        types = [types]
    if not isinstance(types,list): return False
    return any(str(t).rsplit('/', 1)[-1] == kind for t in types)


def _price(offer):
    # AggregateOffer.lowPrice may belong to a different capacity or seller.
    if _kind(offer, 'AggregateOffer') or offer.get('priceCurrency') != 'BRL':
        return None
    if any(offer.get(k) for k in ('eligibleCustomerType', 'eligibleQuantity', 'eligibleDuration', 'addOn', 'eligibleTransactionVolume')):
        return None
    specs = offer.get('priceSpecification', [])
    if isinstance(specs, dict):
        specs = [specs]
    if not isinstance(specs,list): return None
    terms=norm(' '.join(str(offer.get(k) or '') for k in ('description','name')))
    if any(word in terms for word in ('troca', 'cashback', 'assinatura', 'cupom', 'cartao', 'membro')):
        return None
    for spec in specs:
        if not isinstance(spec, dict):
            return None
        if any(spec.get(k) for k in ('validForMemberTier', 'billingDuration', 'billingIncrement', 'eligibleQuantity')):
            return None
        if spec.get('priceType') and not str(spec['priceType']).endswith('SalePrice'):
            return None
    until = offer.get('priceValidUntil') or offer.get('validThrough')
    if until:
        try:
            expiry = datetime.fromisoformat(str(until).replace('Z', '+00:00'))
            if len(str(until)) == 10:
                if expiry.date() < datetime.now(timezone.utc).date():
                    return None
            else:
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry < datetime.now(timezone.utc):
                    return None
        except ValueError:
            return None
    availability = str(offer.get('availability', '')).rsplit('/', 1)[-1]
    if availability and availability not in {'InStock', 'LimitedAvailability', 'OnlineOnly'}:
        return None
    raw_price=offer.get('price')
    if isinstance(raw_price,str) and not re.fullmatch(r'\d+(?:[.,]\d{1,2})?',raw_price.strip()): return None
    value = parse_brl(raw_price)
    return value if value is not None and 500 <= value <= 20000 else None


class StructuredPageCollector:
    name = 'Páginas oficiais'

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.name = cfg.get('name', self.name)
        self.pages = cfg.get('pages', [])
        self.timeout = float(cfg.get('timeout_seconds', 12))
        self.delay = float(cfg.get('min_delay_seconds', 1.5))
        self.s = build_session(cfg.get('user_agent', 'SmartphoneDealMonitor/1.0'), int(cfg.get('retries', 2)))

    def collect(self, targets: list[Target]) -> CollectorResult:
        tmap = {t.id: t for t in targets}
        offers, errors, blocked = [], [], set()
        pages = [p for p in self.pages if p.get('enabled', True)]
        if not pages:
            return CollectorResult(self.name, [], True, 'Nenhuma página configurada', 'skipped', 'not_configured')
        for i, page in enumerate(pages):
            host = urlparse(page['url']).hostname
            if host in blocked:
                continue
            try:
                r = self.s.get(page['url'], timeout=self.timeout)
                r.raise_for_status()
                target = tmap.get(page.get('target_id'))
                if page.get('target_id') and target is None:
                    raise ValueError('target desconhecido')
                offer = self._parse(r.text, page, target, targets)
                if offer:
                    offers.append(offer)
                else:
                    errors.append(f"{page.get('target_id', host)}: no_reliable_price")
            except Exception as exc:
                errors.append(f"{page.get('target_id', host)}: {error_reason(exc)}")
                if stop_source(exc):
                    blocked.add(host)
            if i < len(pages) - 1:
                time.sleep(self.delay)
        return CollectorResult(self.name, offers, not errors, f'{len(offers)} ofertas; ' + (' | '.join(errors) if errors else 'ok'), reason='partial_failure' if errors else '')

    def _parse(self, html, p, target, targets):
        soup = BeautifulSoup(html, 'html.parser')
        objects = []
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                objects.extend(_objects(json.loads(script.get_text())))
            except (ValueError, TypeError):
                continue
        by_id = {o['@id']: o for o in objects if isinstance(o.get('@id'),str) and len(o) > 1}
        candidates = []
        for product in objects:
            if not _kind(product, 'Product'):
                continue
            title = str(product.get('name') or '')
            found = match_target(title, targets)
            storage = extract_storage_gb(title)
            if not found or storage != found.storage_gb or (target and found.id != target.id):
                continue
            # Bind condition/price to this product, never a recommendation or text minimum.
            offers = product.get('offers', [])
            if isinstance(offers, dict):
                offers = [offers]
            if not isinstance(offers,list): continue
            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                offer = by_id.get(offer.get('@id'), offer)
                condition = detect_condition(title, offer.get('itemCondition') or product.get('itemCondition'))
                if condition in {'used', 'refurbished'}:
                    continue
                value = _price(offer)
                if value is not None:
                    candidates.append(self._offer(p, found, title, value, condition, offer, 'jsonld'))
        if candidates:
            return min(candidates, key=lambda o: o.price_final_direct)
        # Do not override a rejected JSON-LD variant/price using metadata.
        if any(_kind(obj, 'Product') for obj in objects):
            return None
        h1 = soup.find('h1')
        title = h1.get_text(' ', strip=True) if h1 else ''
        found = match_target(title, targets)
        if not found or extract_storage_gb(title) != found.storage_gb or (target and found.id != target.id):
            return None
        currency = soup.select_one('meta[property="product:price:currency"]')
        price = soup.select_one('meta[property="product:price:amount"]')
        if not currency or not price:
            return None
        raw = {'priceCurrency': currency.get('content'), 'price': price.get('content')}
        value = _price(raw)
        condition = detect_condition(title)
        if value is None or condition in {'used', 'refurbished'}:
            return None
        return self._offer(p, found, title, value, condition, raw, 'meta')

    def _offer(self, page, target, title, price, condition, raw, parser):
        store = page.get('store', 'Loja')
        host = urlparse(page['url']).hostname
        official = (store == 'Samsung' and host == 'shop.samsung.com') or (store == 'Motorola' and host == 'www.motorola.com.br')
        seller = raw.get('seller')
        seller = seller.get('name') if isinstance(seller, dict) else None
        return Offer(source='structured_page', store=store, title=title, url=page['url'], price_base=price,
                     seller=seller or (store if official else None), is_official_store=official,
                     condition='new' if official and condition == 'unknown' else condition,
                     target_id=target.id, canonical_name=target.name, brand=target.brand, storage_gb=target.storage_gb,
                     stock=str(raw.get('availability') or 'unknown'),
                     notes=['Preço estruturado; frete e condições devem ser confirmados no checkout.'],
                     raw={'parser': parser, 'priceCurrency': 'BRL', 'availability': raw.get('availability')})
