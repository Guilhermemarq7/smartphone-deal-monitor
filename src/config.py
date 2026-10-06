from __future__ import annotations

from pathlib import Path
import yaml
from .models import Target


def load_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Configuração não encontrada: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    validate_config(data)
    return data


def validate_config(cfg: dict) -> None:
    for key in ("budget", "monitor", "phones", "sources"):
        if key not in cfg:
            raise ValueError(f"config.yaml: seção obrigatória ausente: {key}")
    budget = cfg["budget"]
    if not (budget["ideal"] <= budget["soft_limit"] <= budget["exceptional_limit"]):
        raise ValueError("budget deve obedecer ideal <= soft_limit <= exceptional_limit")
    ids=set()
    for group in (cfg.get("phones", []), cfg.get("aspirational", [])):
        for item in group:
            if item["id"] in ids:
                raise ValueError(f"ID duplicado: {item['id']}")
            ids.add(item["id"])
            if item["strong_buy_below"] > item["alert_below"]:
                raise ValueError(f"{item['id']}: strong_buy_below deve ser <= alert_below")
            if item["dream_price"] > item["strong_buy_below"]:
                raise ValueError(f"{item['id']}: dream_price deve ser <= strong_buy_below")


def targets_from_config(cfg: dict) -> list[Target]:
    out=[]
    for aspirational, group in ((False, cfg.get("phones", [])), (True, cfg.get("aspirational", []))):
        for x in group:
            out.append(Target(
                id=x["id"], name=x["name"], brand=x["brand"], aliases=x.get("aliases", [x["name"]]),
                storage_gb=int(x["storage_gb"]), alert_below=float(x["alert_below"]),
                strong_buy_below=float(x["strong_buy_below"]), dream_price=float(x["dream_price"]),
                priority=x.get("priority", "medium"), upgrade_score=float(x.get("upgrade_score", 60)),
                bootstrap_recent=_f(x.get("bootstrap_recent")), bootstrap_low=_f(x.get("bootstrap_low")),
                aspirational=aspirational,
            ))
    return out


def _f(v):
    return None if v is None else float(v)
