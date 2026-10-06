from __future__ import annotations

import re
import unicodedata
from typing import Optional
from .models import Target

ACCESSORY_WORDS = {
    "capa", "pelicula", "carregador", "case", "capinha", "display", "tela para", "bateria para",
    "placa", "conector", "cabo", "fone", "suporte", "kit acessorios", "camera lens", "lente protetora",
}
USED_WORDS = {"usado", "seminovo", "semi novo", "recondicionado", "refurbished", "caixa aberta", "open box", "vitrine"}


def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    s = strip_accents(s.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_brl(value: str | float | int | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("R$", "").replace("\xa0", " ").strip()
    m = re.search(r"\d[\d\.]*[,]\d{2}|\d[\d\.]*", s)
    if not m:
        return None
    token = m.group(0)
    if "," in token:
        token = token.replace(".", "").replace(",", ".")
    else:
        parts=token.split(".")
        if len(parts)>1 and all(len(p)==3 for p in parts[1:]):
            token="".join(parts)
    try:
        return float(token)
    except ValueError:
        return None


def extract_storage_gb(text: str) -> Optional[int]:
    t = norm(text)
    vals=[]
    for n, unit in re.findall(r"\b(\d{1,4})\s*(gb|tb)\b", t):
        v=int(n) * (1024 if unit == "tb" else 1)
        if v in {64, 128, 256, 512, 1024, 2048}:
            vals.append(v)
    return max(vals) if vals else None


def detect_condition(text: str, explicit: str | None = None) -> str:
    e=norm(explicit or "")
    t=norm(text)
    if "recondicionado" in e or "refurb" in e or "recondicionado" in t or "refurb" in t:
        return "refurbished"
    if "usado" in e or any(w in t for w in USED_WORDS):
        return "used"
    if e in {"new", "novo", "2230284"} or "novo lacrado" in t or "lacrado" in t:
        return "new"
    return "unknown"


def is_accessory(text: str) -> bool:
    t=norm(text)
    return any(w in t for w in ACCESSORY_WORDS)


def match_target(title: str, targets: list[Target]) -> Optional[Target]:
    tnorm=norm(title)
    storage=extract_storage_gb(title)
    best=None
    best_score=-1
    for target in targets:
        if storage is not None and storage != target.storage_gb:
            continue
        for alias in target.aliases:
            a=norm(alias)
            toks=[x for x in a.split() if x not in {"samsung","apple","motorola","xiaomi","poco","gb"} and not x.isdigit()]
            score=sum(1 for tok in toks if tok in tnorm.split())
            must=[tok for tok in toks if re.search(r"\d", tok)]
            if must and not all(tok in tnorm.split() for tok in must):
                continue
            if score > best_score and score >= max(1, len(toks)-1):
                best=target; best_score=score
    return best


def infer_brand(title: str) -> Optional[str]:
    t=norm(title)
    for brand in ("samsung", "apple", "motorola", "xiaomi", "poco"):
        if brand in t.split(): return brand.title() if brand != "poco" else "POCO"
    if "iphone" in t: return "Apple"
    if "galaxy" in t: return "Samsung"
    return None


def infer_quality_score(title: str) -> float:
    t=norm(title)
    # conservative: unknown devices should not dominate discovery
    if any(x in t for x in ["galaxy s24 ultra", "galaxy s25 ultra", "galaxy s26 ultra"]): return 96
    if any(x in t for x in ["galaxy s26", "galaxy s25 ", "iphone 16", "iphone 17", "edge 70 pro", "xiaomi 15t pro"]): return 88
    if any(x in t for x in ["xiaomi 15t", "poco f7", "edge 60 pro", "iphone 15"]): return 80
    if " fe " in f" {t} ": return 68
    if any(x in t for x in ["galaxy a", "moto g", "redmi note"]): return 45
    return 60
