#!/usr/bin/env python3
"""
Gera o custo-empreendimentos.html — custo da campanha alocado por produto.

Consome o MESMO vendas.json dos demais scripts (ver AUTOMACAO.md) e troca o
bloco `var DADOS = {...};` dentro da página, do mesmo jeito que o atualiza.py
troca o `const DATA` nos rankings.

  python scripts/custo_empreendimentos.py --json vendas.json
  python scripts/custo_empreendimentos.py --json vendas.json --dry-run

Como o custo é alocado
----------------------
1. PREMIAÇÃO (corretor, gerente, bônus de volume) — calculada pelo motor.py e
   depois rateada entre os produtos do bloco de cada pessoa na proporção do
   teto x unidades fechadas daquele produto. Critério extraído da página
   original de 14/09/2026 e conferido contra os valores dela.
   Corretor de Parcerias (B2B) recebe valor fixo por venda, então o fixo vai
   direto para o produto daquela venda, sem rateio.
2. RATEIOS (verba fixa de R$ 40.000, premiação da equipe comercial e prêmio
   extra por performance) — distribuídos entre os produtos conforme o VGV.

Vendas internas entram no VGV e nas unidades, mas ficam fora da premiação.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motor  # noqa: E402
from motor import (  # noqa: E402
    AUTORIA,
    META_UNID,
    META_VGV,
    TETOS,
    Venda,
)

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = "custo-empreendimentos.html"

VERBA_FIXA = 40_000

# `var DADOS = {...};`
RE_DADOS = re.compile(r"(var\s+DADOS\s*=\s*)(\{.*?\})(\s*;)", re.DOTALL)
RE_RODAPE = re.compile(r"(<footer>Atualizado em\s*)(\d{2}/\d{2}/\d{4})")

FUSO_SP = timezone(timedelta(hours=-3))

# Ordem de exibição e custo planejado por produto no cenário de 100% da curva.
# Valores do plano aprovado — constantes, não dependem das vendas.
ORDEM_PRODUTOS = [
    "Ateliê 365",
    "Mac Ibirapuera",
    "Mac Pinheiros",
    "Mac Vila Clementino",
    "Mac Brooklin",
    "Mac Vila Mariana",
    "Mac Campo Belo",
    AUTORIA,
]
PLANO_100 = {
    "Ateliê 365": 33_933,
    "Mac Ibirapuera": 71_082,
    "Mac Pinheiros": 146_840,
    "Mac Vila Clementino": 75_537,
    "Mac Brooklin": 96_416,
    "Mac Vila Mariana": 44_863,
    "Mac Campo Belo": 64_149,
    AUTORIA: 197_181,
}


# ------------------------------------------------------------------ alocação

def _pesos_por_produto(vendas: list[Venda]) -> dict[str, float]:
    """
    Peso de cada produto dentro do bloco de uma pessoa: teto x unidades
    fechadas. É a proporção usada para ratear a premiação dela entre os
    produtos que ela vendeu.
    """
    fechadas, _ = motor._unidades_fechadas(vendas)
    return {p: TETOS[p] * q for p, q in fechadas.items() if TETOS.get(p) and q > 0}


def _ratear(valor: float, pesos: dict[str, float]) -> dict[str, float]:
    """Distribui `valor` entre os produtos conforme `pesos`."""
    total = sum(pesos.values())
    if not total:
        return {}
    return {p: valor * peso / total for p, peso in pesos.items()}


def _liberacao(vendas: list[Venda], premiacao: float) -> float:
    """
    Parte da premiação da pessoa que só existe porque havia Autoria no bloco:
    a diferença entre o pool com Autoria (100% do teto + kicker) e o pool que
    o bloco pagaria sem ela (75% do teto + o valor fixo das Autorias).

    É o quanto a Autoria "acelerou" a venda dos outros produtos. Por decisão
    da Mari (07/10/2026), esse valor é debitado da Autoria MAC em vez de
    ficar no produto premium.
    """
    fechadas, _ = motor._unidades_fechadas(vendas)
    autorias = fechadas.get(AUTORIA, 0)
    premium = {p: q for p, q in fechadas.items() if p != AUTORIA and q > 0}
    if not autorias or not premium:
        return 0.0

    pool, _, _ = motor._pool_produtos(fechadas)
    base_premium = sum(TETOS[p] * q for p, q in premium.items())
    pool_sem_autoria = base_premium * motor.RETENCAO + autorias * motor.VALOR_AUTORIA
    if pool <= 0:
        return 0.0
    # Escala para a premiação efetivamente paga (o motor arredonda ao milhar).
    return (pool - pool_sem_autoria) * premiacao / pool


def _soma(destino: dict[str, float], parcelas: dict[str, float]) -> None:
    for produto, valor in parcelas.items():
        destino[produto] = destino.get(produto, 0.0) + valor


def _premiacao_por_produto(vendas: list[Venda], autoria_absorve: bool = True) -> tuple[dict, dict, dict]:
    """
    Devolve (corretor, gerente, bonus) — cada um um dicionário produto -> R$.

    A premiação de cada pessoa sai do motor.py (régua oficial) e é então
    rateada entre os produtos do bloco dela.
    """
    corretor: dict[str, float] = {}
    gerente: dict[str, float] = {}
    bonus: dict[str, float] = {}

    elegiveis = [v for v in vendas if not v.interna]

    # --- corretores de Parcerias (§4.3): valor fixo, apurado por gerente e em
    # unidades inteiras, exatamente como o motor.py faz — 1,5 venda paga 1
    # unidade, não 1,5. O fixo da equipe rateia entre os produtos que ela vendeu.
    b2b_por_gerente: dict[str, list[Venda]] = {}
    for v in elegiveis:
        if v.b2b and v.gerente:
            b2b_por_gerente.setdefault(v.gerente, []).append(v)

    for nome, linhas in b2b_por_gerente.items():
        unidades = int(sum(x.vendas for x in linhas))
        fixo = unidades * motor.B2B_FIXO_POR_VENDA
        if fixo:
            _soma(corretor, _ratear(fixo, _pesos_por_produto(linhas)))

    # --- demais corretores (Salão / Online)
    por_corretor: dict[str, list[Venda]] = {}
    for v in elegiveis:
        if not v.b2b:
            por_corretor.setdefault(v.corretor, []).append(v)

    for nome, proprias in por_corretor.items():
        valor, _ = motor._premiacao_corretor(proprias)
        if not valor:
            continue
        lib = _liberacao(proprias, valor) if autoria_absorve else 0.0
        if lib:
            corretor[AUTORIA] = corretor.get(AUTORIA, 0.0) + lib
            valor -= lib

        # §5 — o bônus de volume só existe no bloco só-Autoria, então é da
        # Autoria por definição; o resto rateia pelos pesos do bloco.
        fechadas, _ = motor._unidades_fechadas(proprias)
        so_autoria = not {p for p, q in fechadas.items() if p != AUTORIA and q > 0}
        valor_bonus = (
            motor.bonus_volume(fechadas.get(AUTORIA, 0)) if so_autoria else 0
        )
        if valor_bonus:
            bonus[AUTORIA] = bonus.get(AUTORIA, 0.0) + valor_bonus

        _soma(corretor, _ratear(valor - valor_bonus, _pesos_por_produto(proprias)))

    # --- gerentes (régua normal, inclusive sobre as vendas de Parcerias)
    por_gerente: dict[str, list[Venda]] = {}
    for v in elegiveis:
        por_gerente.setdefault(v.gerente, []).append(v)

    for nome, linhas in por_gerente.items():
        valor, _ = motor._premiacao_gerente(linhas)
        if not valor:
            continue
        lib = _liberacao(linhas, valor) if autoria_absorve else 0.0
        if lib:
            gerente[AUTORIA] = gerente.get(AUTORIA, 0.0) + lib
            valor -= lib
        _soma(gerente, _ratear(valor, _pesos_por_produto(linhas)))

    return corretor, gerente, bonus


def _blocos(vendas: list[Venda]) -> list[dict]:
    """Bloco de cada gerente: quem destravou a Autoria e quanto ficou retido."""
    elegiveis = [v for v in vendas if not v.interna]
    por_gerente: dict[str, list[Venda]] = {}
    for v in elegiveis:
        por_gerente.setdefault(v.gerente or "SEM GERENTE", []).append(v)

    saida = []
    for nome, linhas in por_gerente.items():
        fechadas, _ = motor._unidades_fechadas(linhas)
        autorias = fechadas.get(AUTORIA, 0)
        premium = {p: q for p, q in fechadas.items() if p != AUTORIA and q > 0}
        base_premium = sum(TETOS[p] * q for p, q in premium.items())

        pool, _, _ = motor._pool_produtos(fechadas)
        retido = base_premium * (1 - motor.RETENCAO) if (premium and not autorias) else 0.0
        valor, _ = motor._premiacao_gerente(linhas)

        saida.append({
            "gerente": nome.upper(),
            "autorias": autorias,
            "destravado": bool(autorias) or not premium,
            "premium": [{"nome": p, "un": q} for p, q in sorted(premium.items())],
            "gerenteValor": valor,
            "retido": round(retido, 2),
            "pool": round(pool, 2),
        })

    saida.sort(key=lambda b: (-b["gerenteValor"], b["gerente"]))
    return saida


# -------------------------------------------------------------------- bases

def _base(vendas: list[Venda], com_equipe_fixa: bool = False,
          com_verba_fixa: bool = False, autoria_absorve: bool = True) -> dict:
    """Monta o bloco de uma base de cálculo (realizado ou projeção)."""
    vgv_prod: dict[str, float] = {}
    un_prod: dict[str, float] = {}
    for v in vendas:
        vgv_prod[v.produto] = vgv_prod.get(v.produto, 0.0) + v.vgv
        un_prod[v.produto] = un_prod.get(v.produto, 0.0) + v.vendas

    vgv_total = sum(vgv_prod.values())
    un_total = sum(un_prod.values())
    atingido = vgv_total / META_VGV if META_VGV else 0.0

    corretor, gerente, bonus = _premiacao_por_produto(vendas, autoria_absorve)

    # §9 — equipe comercial. A variável por gestor só entra a partir de 60%.
    variavel = motor.variavel_por_gestor(atingido) * 3
    fixa = vgv_total * motor.COMISSAO_FIXA * 2 if com_equipe_fixa else 0.0
    # Luiz cobre todos os produtos (0,10%) e Bruno/Danilo dividem a mesma base
    # entre as duas carteiras, somando outros 0,10% — daí o fator 2.
    equipe_total = variavel + fixa

    extra_total = motor.PREMIO_EXTRA_TOTAL if atingido >= 0.80 else 0
    extra_ativo = atingido >= 0.80

    # Rateios proporcionais ao VGV de cada produto.
    pesos_vgv = {p: v for p, v in vgv_prod.items() if v > 0}
    verba = _ratear(VERBA_FIXA if com_verba_fixa else 0, pesos_vgv)
    equipe = _ratear(equipe_total, pesos_vgv)
    extra = _ratear(extra_total, pesos_vgv)

    produtos = []
    for nome in ORDEM_PRODUTOS:
        c = corretor.get(nome, 0.0)
        g = gerente.get(nome, 0.0)
        b = bonus.get(nome, 0.0)
        vf = verba.get(nome, 0.0)
        eq = equipe.get(nome, 0.0)
        ex = extra.get(nome, 0.0)
        vgv = vgv_prod.get(nome, 0.0)
        un = un_prod.get(nome, 0.0)
        total = c + g + b + vf + eq + ex
        produtos.append({
            "nome": nome,
            "un": un,
            "vgv": vgv,
            "corretor": c,
            "gerente": g,
            "bonus": b,
            "verbaFixa": vf,
            "equipe": eq,
            "extra": ex,
            "total": total,
            "pctVGV": (total / vgv) if vgv else 0,
            "custoUn": (total / un) if un else 0,
            "plano100": PLANO_100.get(nome, 0),
        })

    blocos = _blocos(vendas)
    total_geral = sum(p["total"] for p in produtos)

    return {
        "resumo": {
            "vgv": vgv_total,
            "un": un_total,
            "atingido": atingido,
            "total": total_geral,
            "pctVGV": (total_geral / vgv_total) if vgv_total else 0,
            "retido": round(sum(b["retido"] for b in blocos), 2),
            "corretor": sum(p["corretor"] for p in produtos),
            "gerente": sum(p["gerente"] for p in produtos),
            "bonus": sum(p["bonus"] for p in produtos),
            "verbaFixa": sum(p["verbaFixa"] for p in produtos),
            "equipe": sum(p["equipe"] for p in produtos),
            "extra": sum(p["extra"] for p in produtos),
            "extraAtivo": extra_ativo,
        },
        "produtos": produtos,
        "blocos": blocos,
    }


# --------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="arquivo JSON com as vendas")
    ap.add_argument("--raiz", default=str(RAIZ), help="pasta do repositório")
    ap.add_argument("--dry-run", action="store_true", help="não grava nada")
    ap.add_argument(
        "--com-equipe-fixa", action="store_true",
        help="inclui a comissão fixa de 0,10%% da Equipe Comercial no custo "
             "(fora por padrão: decisão da Mari em 07/10/2026)",
    )
    ap.add_argument(
        "--com-verba-fixa", action="store_true",
        help="inclui a verba fixa de R$ 40.000 no rateio (fora por padrão: já "
             "foi gasta e rateada por obra à parte)",
    )
    ap.add_argument(
        "--liberacao-no-premium", action="store_true",
        help="mantém a liberação destravada pela Autoria no produto premium "
             "(por padrão ela é debitada da Autoria MAC)",
    )
    args = ap.parse_args()

    raiz = Path(args.raiz)
    agora = datetime.now(FUSO_SP)

    vendas = [Venda(**linha) for linha in json.loads(Path(args.json).read_text("utf-8"))]
    realizado = [v for v in vendas if v.valida]

    dados = {
        "atualizado": agora.strftime("%d/%m/%Y"),
        "real": _base(realizado, args.com_equipe_fixa, args.com_verba_fixa,
                      not args.liberacao_no_premium),
        "proj": _base(vendas, args.com_equipe_fixa, args.com_verba_fixa,
                      not args.liberacao_no_premium),
    }

    for rotulo, chave in (("realizado", "real"), ("projeção ", "proj")):
        z = dados[chave]["resumo"]
        print(f"{rotulo}: R$ {z['vgv']:,.2f} ({z['atingido'] * 100:.2f}% da meta) "
              f"· {z['un']} un. · custo R$ {z['total']:,.2f} "
              f"({z['pctVGV'] * 100:.2f}% do VGV)")

    retidos = [b for b in dados["real"]["blocos"] if b["retido"]]
    if retidos:
        print("\nBlocos retidos em 75% por falta de Autoria (realizado):")
        for b in retidos:
            print(f"  {b['gerente']:12} retido R$ {b['retido']:,.2f}")

    caminho = raiz / PAGINA
    if not caminho.exists():
        print(f"\n! {PAGINA} não encontrado em {raiz}")
        return 1

    original = caminho.read_text(encoding="utf-8")
    dados_json = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))

    novo, trocas = RE_DADOS.subn(
        lambda m: m.group(1) + dados_json + m.group(3), original
    )
    if trocas == 0:
        print(f"\n! {PAGINA}: bloco 'var DADOS = {{...}}' não encontrado")
        return 1
    novo = RE_RODAPE.sub(lambda m: m.group(1) + dados["atualizado"], novo)

    if novo == original:
        print(f"\n= {PAGINA} (nada mudou)")
        return 0

    if not args.dry_run:
        caminho.write_text(novo, encoding="utf-8")
    print(f"\n~ {PAGINA} atualizado" + (" (dry-run: nada gravado)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
