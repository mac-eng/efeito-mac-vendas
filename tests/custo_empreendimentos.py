#!/usr/bin/env python3
"""
Rateio da premiação de corretores e gerentes por empreendimento.

Responde "quanto cada empreendimento paga" da premiação do Motor de Vendas,
a partir dos mesmos valores que o motor publica nos rankings (motor.py).

Regras do rateio (definidas em 07/10/2026):
  * Gerente com produto premium + Autoria: cada produto lê a célula da matriz
    com todas as Autorias da equipe. Dentro da célula, a parte da Autoria
    (40% x R$ 3.408 por Autoria) é paga pelo Autoria MAC; o restante (teto,
    kicker e arredondamento) é pago pelo produto premium. O kicker sai sempre
    do orçamento do produto premium.
  * Gerente sem Autoria: o produto premium paga tudo (75% do teto).
  * Gerente só com Autoria: Autoria MAC paga tudo.
  * Corretor Salão/Online: mesma separação, com 60%. Bônus de volume da
    Autoria vendida sozinha é pago pelo Autoria MAC.
  * Corretor B2B (Parcerias): R$ 2.000 fixos por unidade fechada, pagos pelo
    produto da unidade.
  * Metades (0,5) que não fecham uma unidade do mesmo produto não pagam nada.

  python scripts/custo_empreendimentos.py --json vendas.json            # grava o HTML
  python scripts/custo_empreendimentos.py --json vendas.json --dry-run  # só mostra
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from motor import (  # noqa: E402
    AUTORIA, B2B_FIXO_POR_VENDA, SPLIT_CORRETOR, SPLIT_GERENTE, TETOS, VALOR_AUTORIA,
    Venda, _pool_produtos, _unidades_fechadas, arredonda_milhar, bonus_volume, montar_data,
)

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = "custo-empreendimentos.html"
FUSO_SP = timezone(timedelta(hours=-3))
PRODUTOS = list(TETOS)  # ordem de exibição: premium do maior teto ao menor, Autoria por último
COMPONENTES = ("gerente", "corretor", "b2b", "bonus")


def _vazio() -> dict[str, dict[str, float]]:
    return {p: {c: 0.0 for c in COMPONENTES} for p in PRODUTOS}


def _divide_premium(valor: float, premium: dict[str, int]) -> dict[str, float]:
    """Reparte um valor entre produtos premium pelo peso teto x unidades."""
    pesos = {p: TETOS[p] * q for p, q in premium.items()}
    soma = sum(pesos.values())
    return {p: valor * w / soma for p, w in pesos.items()}


def rateio_gerente(vendas: list[Venda]) -> tuple[int, dict[str, float]]:
    """Mesmo cálculo de motor._premiacao_gerente, devolvendo quanto cada produto paga."""
    fechadas, _ = _unidades_fechadas(vendas)
    autorias = fechadas.get(AUTORIA, 0)
    premium = {p: q for p, q in fechadas.items() if p != AUTORIA}
    paga: dict[str, float] = {}

    if not premium:
        if autorias:
            pool, _, _ = _pool_produtos(fechadas)
            paga[AUTORIA] = arredonda_milhar(pool * SPLIT_GERENTE)
        return int(sum(paga.values())), paga

    for produto, qtd in premium.items():
        bloco = {produto: qtd}
        if autorias:
            bloco[AUTORIA] = autorias
        pool, _, _ = _pool_produtos(bloco)
        celula = arredonda_milhar(pool * SPLIT_GERENTE)
        parte_autoria = SPLIT_GERENTE * autorias * VALOR_AUTORIA
        paga[produto] = paga.get(produto, 0) + celula - parte_autoria
        if autorias:
            paga[AUTORIA] = paga.get(AUTORIA, 0) + parte_autoria
    return int(round(sum(paga.values()))), paga


def rateio_corretor(vendas: list[Venda]) -> tuple[int, dict[str, float], float]:
    """Mesmo cálculo de motor._premiacao_corretor. Devolve (total, por produto, bônus)."""
    fechadas, _ = _unidades_fechadas(vendas)
    if not fechadas:
        return 0, {}, 0.0
    autorias = fechadas.get(AUTORIA, 0)
    premium = {p: q for p, q in fechadas.items() if p != AUTORIA}
    pool, _, so_autoria = _pool_produtos(fechadas)

    if so_autoria:
        bonus = bonus_volume(autorias)
        total = arredonda_milhar(pool * SPLIT_CORRETOR + bonus)
        # O arredondamento fica com a parcela da premiação, não com o bônus.
        return total, {AUTORIA: total - bonus}, float(bonus)

    total = arredonda_milhar(pool * SPLIT_CORRETOR)
    parte_autoria = SPLIT_CORRETOR * autorias * VALOR_AUTORIA
    paga = _divide_premium(total - parte_autoria, premium)
    if autorias:
        paga[AUTORIA] = parte_autoria
    return total, paga, 0.0


def _b2b_por_produto(linhas: list[Venda]) -> dict[str, float]:
    """R$ 2.000 por unidade B2B fechada, no produto da unidade."""
    soma: dict[str, float] = {}
    for v in linhas:
        if v.b2b:
            soma[v.produto] = soma.get(v.produto, 0.0) + v.vendas
    return {p: int(q) * B2B_FIXO_POR_VENDA for p, q in soma.items() if int(q) > 0}


def _cenario(vendas: list[Venda], publicado: dict) -> dict:
    produtos = _vazio()
    vgv = {p: 0.0 for p in PRODUTOS}
    un = {p: 0.0 for p in PRODUTOS}
    for v in vendas:
        if v.produto in vgv:
            vgv[v.produto] += v.vgv
            un[v.produto] += v.vendas

    # --- gerentes (e B2B, que é contado por gerente no motor) ---
    gerentes = []
    por_gerente: dict[str, list[Venda]] = {}
    for v in vendas:
        if v.interna or not v.gerente:
            continue
        por_gerente.setdefault(v.gerente, []).append(v)

    for nome, linhas in por_gerente.items():
        total, paga = rateio_gerente(linhas)
        esperado = publicado["gerentes"][nome]["premiacao"]
        if total != esperado:
            raise SystemExit(f"rateio do gerente {nome} = {total}, motor publica {esperado}")
        for p, val in paga.items():
            produtos[p]["gerente"] += val

        b2b = _b2b_por_produto(linhas)
        if sum(b2b.values()) != publicado["gerentes"][nome]["parcerias_fixo"]:
            raise SystemExit(f"fixo B2B do gerente {nome} não bate com o motor")
        for p, val in b2b.items():
            produtos[p]["b2b"] += val

        fechadas, _ = _unidades_fechadas(linhas)
        gerentes.append({
            "gerente": nome,
            "autorias": fechadas.get(AUTORIA, 0),
            "premium": [{"nome": p, "un": q} for p, q in fechadas.items() if p != AUTORIA],
            "valor": total,
            "b2b": sum(b2b.values()),
            "paga": {p: round(v, 2) for p, v in sorted(paga.items(), key=lambda x: -x[1])},
        })

    # --- corretores Salão/Online ---
    por_corretor: dict[str, list[Venda]] = {}
    for v in vendas:
        if v.interna or v.b2b or not v.corretor:
            continue
        por_corretor.setdefault(v.corretor, []).append(v)
    for nome, linhas in por_corretor.items():
        total, paga, bonus = rateio_corretor(linhas)
        if total != publicado["corretores"][nome]["premiacao"]:
            raise SystemExit(f"rateio do corretor {nome} não bate com o motor")
        for p, val in paga.items():
            produtos[p]["corretor"] += val
        produtos[AUTORIA]["bonus"] += bonus

    linhas_saida = []
    for p in PRODUTOS:
        c = produtos[p]
        total = sum(c.values())
        linhas_saida.append({
            "nome": p, "un": round(un[p], 2), "vgv": round(vgv[p], 2),
            **{k: round(v, 2) for k, v in c.items()},
            "total": round(total, 2),
            "pctVGV": total / vgv[p] if vgv[p] else 0,
            "custoUn": total / un[p] if un[p] else 0,
        })

    resumo = {k: round(sum(x[k] for x in linhas_saida), 2)
              for k in ("vgv", "un", "gerente", "corretor", "b2b", "bonus", "total")}
    resumo["pctVGV"] = resumo["total"] / resumo["vgv"] if resumo["vgv"] else 0
    resumo["atingido"] = publicado["pct"]
    gerentes.sort(key=lambda g: -g["valor"])
    return {"resumo": resumo, "produtos": linhas_saida, "gerentes": gerentes}


def montar(vendas: list[Venda], agora: datetime) -> dict:
    data = montar_data(vendas)
    validas = [v for v in vendas if v.valida]
    return {
        "atualizado": agora.strftime("%d/%m/%Y"),
        "real": _cenario(validas, data["realizado"]),
        "proj": _cenario(vendas, data["projecao"]),
    }


RE_DADOS = re.compile(r"(var DADOS = )(\{.*?\})(;\n)", re.DOTALL)
RE_RODAPE = re.compile(r"(Atualizado em )(\d{2}/\d{2}/\d{4})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="vendas.json (mesmo do atualiza.py)")
    ap.add_argument("--raiz", default=str(RAIZ))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    agora = datetime.now(FUSO_SP)
    vendas = [Venda(**x) for x in json.loads(Path(args.json).read_text("utf-8"))]
    dados = montar(vendas, agora)

    for base, rotulo in (("real", "realizado"), ("proj", "projeção")):
        r = dados[base]["resumo"]
        print(f"{rotulo}: premiação R$ {r['total']:,.0f} "
              f"(gerente {r['gerente']:,.0f} · corretor {r['corretor']:,.0f} · "
              f"B2B {r['b2b']:,.0f} · bônus {r['bonus']:,.0f})")

    caminho = Path(args.raiz) / PAGINA
    html = caminho.read_text("utf-8")
    js = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    novo, n = RE_DADOS.subn(lambda m: m.group(1) + js + m.group(3), html)
    if n != 1:
        raise SystemExit(f"{PAGINA}: bloco 'var DADOS = {{...}};' não encontrado")
    novo = RE_RODAPE.sub(lambda m: m.group(1) + dados["atualizado"], novo)
    if not args.dry_run:
        caminho.write_text(novo, "utf-8")
    print(f"  {'~' if novo != html else '='} {PAGINA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
