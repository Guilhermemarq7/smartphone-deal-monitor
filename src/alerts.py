from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import requests
from .models import Deal
from .telegram import TelegramClient
from .collectors.base import error_reason


def _brl(v: float) -> str:
    return (f"R$ {v:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def format_alert(d: Deal) -> str:
    o = d.offer
    icon = "🚨" if d.suspicious_outlier else ("🔥" if d.score >= 88 else "🟢")
    lines = [
        f"{icon} {d.classification}",
        "",
        f"{o.canonical_name or o.title}",
        f"💰 Preço direto: {_brl(o.price_final_direct)}",
        f"🏪 Loja: {o.store}" + (f" | Seller: {o.seller}" if o.seller else ""),
        f"📊 Score: {d.score:.1f}/100",
    ]
    if d.stats.median_30d:
        lines.append(f"📉 Mediana 30d: {_brl(d.stats.median_30d)}")
    if d.stats.min_90d:
        lines.append(f"🏆 Menor 90d/ref.: {_brl(d.stats.min_90d)}")
    if d.discount_real is not None:
        lines.append(f"📉 Queda real: {d.discount_real*100:.1f}%")
    if o.cashback > 0:
        lines.append(f"💳 Efetivo c/ cashback: {_brl(o.price_effective_cashback)} (cashback não é desconto imediato)")
    if o.coupon_code:
        lines.append(f"🎟 Cupom: {o.coupon_code}")
    if d.suspicious_outlier:
        lines += ["", "⚠️ Preço fora da curva. Verifique variante, vendedor, condição, cupom e possível erro antes de comprar."]
    if o.notes:
        lines.append("Obs.: " + "; ".join(o.notes[:3]))
    lines += ["", "🔗 " + o.url]
    return "\n".join(lines)


def alert_fingerprint(d: Deal) -> str:
    o = d.offer
    payload = {
        "product": o.target_id,
        "store": o.store,
        "seller": o.seller,
        "url": o.url,
        "price": round(o.price_final_direct, 2),
        "cashback": round(o.cashback, 2),
        "coupon_code": o.coupon_code,
        "coupon_discount": round(o.coupon_discount, 2),
        "classification": d.classification,
        "tradein": o.requires_tradein,
        "card": o.requires_card,
        "subscription": o.requires_subscription,
        "first_purchase": o.requires_first_purchase,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def should_notify(d: Deal, cfg: dict) -> bool:
    acfg = cfg.get("alerts", {})
    if d.offer.condition in {"used", "refurbished"}:
        return False
    if any((d.offer.requires_tradein,d.offer.requires_card,d.offer.requires_subscription,d.offer.requires_first_purchase)):
        return False
    if d.offer.coupon_limited and d.offer.coupon_discount:
        return False
    if d.suspicious_outlier and acfg.get("alert_outliers", True):
        return True
    min_score = float(acfg.get("min_score", 76))
    return d.score >= min_score and not d.classification.startswith(("NORMAL", "IGNORAR"))


def send_optional_alerts(deals: list[Deal], cfg: dict, db, log_path: Path):
    acfg = cfg.get("alerts", {})
    repeat_hours = float(acfg.get("repeat_after_hours", 24))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    telegram_enabled = bool(acfg.get("telegram", {}).get("enabled", False))
    discord_enabled = bool(acfg.get("discord", {}).get("enabled", False))

    telegram = None
    if telegram_enabled:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if token and chat:
            try:
                telegram = (TelegramClient(token), chat)
            except Exception as exc:
                print(f"[ALERTA] Telegram não inicializado: {error_reason(exc)}")
        else:
            print("[ALERTA] Telegram habilitado, mas TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID não estão configurados.")

    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip() if discord_enabled else ""
    discord_session = requests.Session() if discord_url else None

    sent = 0
    for d in sorted(deals, key=lambda x: x.score, reverse=True):
        if not should_notify(d, cfg):
            continue
        fp = alert_fingerprint(d)
        if db.was_alerted_recently(fp, repeat_hours):
            continue
        msg = format_alert(d)
        delivered = False

        if telegram:
            try:
                telegram[0].send_message(telegram[1], msg)
                delivered = True
                print(f"[ALERTA] Telegram enviado: {d.offer.canonical_name or d.offer.title} — {_brl(d.offer.price_final_direct)}")
            except Exception as exc:
                print(f"[ALERTA] Telegram falhou: {error_reason(exc)}")

        if discord_session and discord_url:
            try:
                discord_session.post(discord_url, json={"content": msg[:1900]}, timeout=10).raise_for_status()
                delivered = True
            except Exception as exc:
                print(f"[ALERTA] Discord falhou: {error_reason(exc)}")

        # Local/no-channel mode still deduplicates the opportunity log. When a configured
        # remote channel fails, do NOT mark success: the next run will retry delivery.
        no_remote_channel = not telegram_enabled and not discord_enabled
        if delivered or no_remote_channel:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(msg + "\n" + "-" * 70 + "\n")
            db.record_alert_event(fp, d, "remote" if delivered else "local")
            sent += 1

    return sent


def send_operational_alert(health,cfg,db):
    """One CRITICAL notification per cooldown, separate from promotion fingerprints."""
    hcfg=cfg.get("health",{})
    if health.level != "CRITICAL" or not hcfg.get("operational_alerts",True):
        return False
    if not cfg.get("alerts",{}).get("telegram",{}).get("enabled",False):
        return False
    fingerprint="collection-critical-v1"
    if db.operational_alert_recent(fingerprint,hcfg.get("alert_cooldown_hours",24)):
        return False
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:
        return False
    message=("⚠️ ALERTA OPERACIONAL — Radar CRITICAL\n"
             +health.message+f"\nCobertura: {len(health.covered_targets)}/{health.target_count} variantes; "
             +f"{len(health.live_stores)} lojas com preços válidos.\n"
             +"Fontes com falha: "+(", ".join(health.failures) or "nenhuma; cobertura insuficiente")
             +"\nConsulte o Job Summary. Este aviso não é uma promoção.")
    try:
        TelegramClient(token).send_message(chat,message[:4000])
    except Exception as exc:
        print(f"[SAÚDE] Alerta operacional não entregue: {error_reason(exc)}")
        return False
    db.record_operational_alert(fingerprint)
    return True
