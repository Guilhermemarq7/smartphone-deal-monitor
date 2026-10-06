from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from .models import Deal


def brl(v):
    if v is None:return "—"
    return (f"R$ {v:,.2f}").replace(",","X").replace(".",",").replace("X",".")

def pct(v): return "—" if v is None else f"{v*100:.1f}%"

def write_reports(deals:list[Deal],statuses:list[dict],outdir:Path):
    outdir.mkdir(parents=True,exist_ok=True)
    ordered=sorted(deals,key=lambda d:(d.score,-d.offer.price_final_direct),reverse=True)
    fields=["classification","score","model","store","seller","price_base","price_pix","coupon_discount","cashback","price_final_direct","price_effective_cashback","median_30d","min_90d","discount_real","condition","source","url"]
    with (outdir/"latest_prices.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for d in ordered:w.writerow(_row(d))
    with (outdir/"best_deals.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for d in ordered:
            if d.score>=62:w.writerow(_row(d))
    lines=["# Radar de smartphones — relatório atual","",f"Gerado em: {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S %Z')}","","## Status das fontes",""]
    for s in statuses: lines.append(f"- **{'OK' if s['ok'] else 'ERRO'} — {s['source']}**: {s['message']}")
    lines += ["","## Melhores oportunidades",""]
    if not ordered: lines += ["Nenhuma oferta válida foi coletada nesta execução.",""]
    for d in ordered[:30]:
        o=d.offer; lines += [f"### {d.classification} — {o.canonical_name or o.title}","",f"- Loja: **{o.store}**"+(f" — seller: {o.seller}" if o.seller else ""),f"- Preço direto: **{brl(o.price_final_direct)}**",f"- Custo efetivo com cashback: **{brl(o.price_effective_cashback)}**" if o.cashback else "- Cashback: não contabilizado como desconto direto",f"- Mediana 30d: {brl(d.stats.median_30d)}",f"- Menor 90d: {brl(d.stats.min_90d)}",f"- Desconto real vs mediana: {pct(d.discount_real)}",f"- Score: **{d.score:.1f}/100**",f"- Condição: {o.condition}",f"- Fonte técnica: `{o.source}`",f"- Link: {o.url}",""]
        if o.notes: lines += ["Observações: "+"; ".join(o.notes),""]
        if d.suspicious_outlier: lines += ["> **OUTLIER:** verificar variante, seller, condição, cupom e possível erro de preço antes de comprar.",""]
    (outdir/"report.md").write_text("\n".join(lines),encoding="utf-8")

def print_terminal(deals:list[Deal],statuses:list[dict]):
    print("="*68);print(" RADAR DE SMARTPHONES — 10/10 DEAL MONITOR");print("="*68)
    print("Status das fontes:")
    for s in statuses: print(f"[{'OK' if s['ok'] else 'ERRO'}] {s['source']}: {s['message']}")
    print("-"*68)
    ordered=sorted(deals,key=lambda d:d.score,reverse=True)
    if not ordered: print("Nenhuma oferta válida nesta execução. Consulte logs e output/report.md."); return
    for d in ordered[:20]:
        o=d.offer
        print(f"\n{d.classification} | {d.score:.1f}/100")
        print(o.canonical_name or o.title)
        print(f"Loja: {o.store}"+(f" | Seller: {o.seller}" if o.seller else ""))
        print(f"Preço direto: {brl(o.price_final_direct)}",end="")
        if o.cashback: print(f" | efetivo c/ cashback: {brl(o.price_effective_cashback)}",end="")
        print()
        print(f"Mediana 30d: {brl(d.stats.median_30d)} | menor 90d: {brl(d.stats.min_90d)} | queda real: {pct(d.discount_real)}")
        if d.stats.used_bootstrap: print("Histórico: cold-start usando referência inicial do Markdown + dados próprios disponíveis")
        if o.notes: print("Obs.: "+"; ".join(o.notes[:2]))
        print(o.url)

def _row(d):
    o=d.offer
    return {"classification":d.classification,"score":d.score,"model":o.canonical_name or o.title,"store":o.store,"seller":o.seller,"price_base":o.price_base,"price_pix":o.price_pix,"coupon_discount":o.coupon_discount,"cashback":o.cashback,"price_final_direct":o.price_final_direct,"price_effective_cashback":o.price_effective_cashback,"median_30d":d.stats.median_30d,"min_90d":d.stats.min_90d,"discount_real":d.discount_real,"condition":o.condition,"source":o.source,"url":o.url}
