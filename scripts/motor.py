"""
Motor de premiação da campanha Efeito MAC — Motor de Vendas 2º Sem. 2026.

Implementa as regras do "Manual_Operacional_Motor_de_Vendas_ATUALIZADO 3":
  §3   retenção/liberação (75% sem Autoria, 100% com Autoria no bloco)
  §3.1 tetos por produto
  §3.2 kicker de 20% a partir da 3ª Autoria
  §4   split 60% corretor / 40% gerente
  §4.2 agregação por equipe no cálculo do gerente
  §4.3 B2B (canal PARCERIAS): corretor fixo R$ 2.000/venda, gerente na régua normal
  §5   bônus de volume do Autoria vendido sozinho (só corretor)
  §7   Prêmio Extra por Performance (gatilho em 80% da meta)
  §9   Premiação Equipe Comercial (Luiz / Bruno / Danilo)

Este módulo é puro: recebe linhas já normalizadas e devolve o dicionário DATA
que os HTMLs do site consomem. Sem I/O, para poder ser testado offline.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------- parâmetros

META_VGV = 88_516_862
META_UNID = 73

AUTORIA = "Autoria MAC"
VALOR_AUTORIA = 3_408

# §3.1 — teto de premiação por unidade, valor cheio (100%)
TETOS = {
    "Ateliê 365": 20_000,
    "Mac Ibirapuera": 13_704,
    "Mac Pinheiros": 12_918,
    "Mac Vila Clementino": 12_995,
    "Mac Brooklin": 10_831,
    "Mac Vila Mariana": 7_513,
    "Mac Campo Belo": 5_000,
    AUTORIA: VALOR_AUTORIA,
}

SPLIT_CORRETOR = 0.60
SPLIT_GERENTE = 0.40
RETENCAO = 0.75          # §3 — produto premium vendido sem Autoria no bloco
KICKER = 1.20            # §3.2 — a partir da 3ª Autoria no bloco
B2B_FIXO_POR_VENDA = 2_000   # §4.3
PREMIO_EXTRA_TOTAL = 85_000  # §7.2 — pago a partir de 80% da meta

# §5 — bônus de volume, exclusivo do corretor, só para Autoria vendida sozinha
def bonus_volume(unidades: int) -> int:
    if unidades >= 4:
        return 5_000
    if unidades >= 2:
        return 2_500
    return 0


# §9.1 — carteiras da Equipe Comercial (Luiz responde por todos os produtos)
CARTEIRA_BRUNO = {
    "Ateliê 365", "Mac Campo Belo", "Mac Pinheiros",
    "Mac Ibirapuera", "Mac Brooklin",
}
CARTEIRA_DANILO = {"Mac Vila Mariana", "Mac Vila Clementino", AUTORIA}
COMISSAO_FIXA = 0.0010  # 0,10% sobre o VGV da carteira

# §9.3 — premiação variável por gestor, por cenário de curva
def variavel_por_gestor(pct: float) -> int:
    if pct >= 1.00:
        return 20_000
    if pct >= 0.80:
        return 15_000
    if pct >= 0.60:
        return 10_000
    return 0


# Produtos femininos, só para o texto do detalhe ("sozinha" vs "sozinho")
FEMININOS = {AUTORIA}

# Marcadores de razão social — usados para encurtar nomes de parceiros B2B
MARCADORES_PJ = {
    "LTDA", "EPP", "ME", "EIRELI", "SA", "S/A",
    "CONSULTORIA", "IMOBILIARIA", "IMOBILIARIOS", "IMOVEIS", "NEGOCIOS",
    "ASSESSORIA", "INTERMEDIACOES", "ADMINISTRACAO", "EMPREENDIMENTOS",
}


# ------------------------------------------------------------- normalizações

def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def nome_produto(obra: str) -> str:
    """Converte o nome da obra da planilha para o rótulo usado no site."""
    alvo = _sem_acento(obra or "").strip().upper()
    for rotulo in TETOS:
        if _sem_acento(rotulo).upper() == alvo:
            return rotulo
    return (obra or "").strip().title()


def nome_corretor(bruto: str, apelidos: dict[str, str] | None = None) -> str:
    """
    Extrai o nome curto do corretor.

    "CINTIA - CINTIA DE OLIVEIRA ROSA"        -> "CINTIA"
    "JENIFFER DOS SANTOS SILVA"               -> "JENIFFER"   (pessoa física)
    "U REAL ESTATE LTDA"                      -> "U REAL ESTATE"
    "FOXTER CONSULTORIA IMOBILIARIA LTDA"     -> "FOXTER"
    """
    bruto = (bruto or "").strip()
    if apelidos and bruto in apelidos:
        return apelidos[bruto]
    if not bruto:
        return ""

    # Formato "APELIDO - NOME COMPLETO"
    if " - " in bruto:
        return bruto.split(" - ")[0].strip().upper()

    tokens = bruto.upper().split()
    limpos = [t for t in tokens if _sem_acento(t).strip(".") not in MARCADORES_PJ]
    tinha_marcador = len(limpos) != len(tokens)

    if tinha_marcador:
        # Pessoa jurídica: mantém o que sobrou da razão social.
        return " ".join(limpos) if limpos else bruto.upper()
    # Pessoa física sem apelido: primeiro nome.
    return tokens[0] if tokens else bruto.upper()


def arredonda_milhar(valor: float) -> int:
    """
    §3 — arredondamento da campanha: para o milhar mais próximo, com o meio
    (".500") sempre subindo. math.floor(x/1000 + 0.5) evita o arredondamento
    bancário do round() nativo.
    """
    return int(math.floor(valor / 1000.0 + 0.5) * 1000)


# ------------------------------------------------------------------ estrutura

@dataclass(frozen=True)
class Venda:
    """Uma linha da planilha, já normalizada."""
    produto: str
    unidade: str
    corretor: str
    gerente: str
    canal: str          # SALÃO | ONLINE | PARCERIAS | VENDA INTERNA
    vendas: float       # 1,0 ou 0,5 (venda dividida)
    vgv: float
    valida: bool        # sinal compensado

    @property
    def b2b(self) -> bool:
        return _sem_acento(self.canal).upper() == "PARCERIAS"


# ---------------------------------------------------------- núcleo do cálculo

def _pool_produtos(unidades_por_produto: dict[str, int]) -> tuple[float, str, bool]:
    """
    §3.2 — pool de premiação (corretor + gerente, antes do split) para um bloco
    com `unidades_por_produto` unidades fechadas.

    Devolve (pool, rótulo, so_autoria). O rótulo alimenta o campo "detalhe"
    exibido no site; `so_autoria` sinaliza o bloco sem produto premium, caso em
    que o corretor (e só ele) ganha o sufixo "[sozinha]" e o bônus de volume.
    """
    autorias = unidades_por_produto.get(AUTORIA, 0)
    premium = {p: q for p, q in unidades_por_produto.items() if p != AUTORIA and q > 0}

    if not premium:
        # Só Autoria: valor fixo, sem retenção (§3.1).
        if not autorias:
            return 0.0, "", True
        return autorias * VALOR_AUTORIA, f"{autorias}x {AUTORIA}", True

    base_premium = sum(TETOS[p] * q for p, q in premium.items())

    if autorias == 0:
        # §3 — sem Autoria no bloco, só 75% do teto (valor retido não é pago).
        pool = base_premium * RETENCAO
        partes = [
            f"{q}x {p} [{'sozinha' if p in FEMININOS else 'sozinho'} (75%)]"
            for p, q in premium.items()
        ]
        return pool, " + ".join(partes), False

    partes = [f"{q}x {p}" for p, q in premium.items()]
    if autorias <= 2:
        pool = base_premium + autorias * VALOR_AUTORIA
        rotulo = " + ".join(partes + [f"{autorias}x {AUTORIA}"])
    else:
        # §3.2 — kicker de 20% sobre produto + 2 Autorias; extras somam cheio.
        pool = (base_premium + 2 * VALOR_AUTORIA) * KICKER
        pool += (autorias - 2) * VALOR_AUTORIA
        rotulo = " + ".join(partes + [f"{autorias}x {AUTORIA}"]) + " [kicker 20%]"

    return pool, rotulo, False


def _unidades_fechadas(vendas: list[Venda]) -> tuple[dict[str, int], dict[str, float]]:
    """
    Agrupa vendas por produto e converte para unidades inteiras.
    Frações (0,5) que não fecham uma unidade são descartadas do cálculo de
    premiação, mas devolvidas separadamente para virar nota no detalhe.
    """
    por_produto: dict[str, float] = {}
    for v in vendas:
        por_produto[v.produto] = por_produto.get(v.produto, 0.0) + v.vendas

    fechadas = {p: int(q) for p, q in por_produto.items() if int(q) > 0}
    restos = {p: round(q - int(q), 2) for p, q in por_produto.items() if q - int(q) > 0}
    return fechadas, restos


def _fmt_moeda(valor: int) -> str:
    return f"R${valor:,}"


def _num_br(valor: float) -> str:
    """0.5 -> '0,5' ; 1.0 -> '1'"""
    txt = f"{valor:.2f}".rstrip("0").rstrip(".")
    return txt.replace(".", ",")


def _premiacao_corretor(vendas: list[Venda]) -> tuple[int, list[str]]:
    """§4/§5 — 60% do pool + bônus de volume quando é Autoria vendida sozinha."""
    fechadas, restos = _unidades_fechadas(vendas)
    if not fechadas:
        total_frac = sum(v.vendas for v in vendas)
        return 0, [f"{_num_br(total_frac)} venda — não pontua até somar 1 unidade"]

    pool, rotulo, so_autoria = _pool_produtos(fechadas)
    valor = pool * SPLIT_CORRETOR

    # §5 — bônus exclusivo do corretor, só quando não há produto premium.
    if so_autoria:
        valor += bonus_volume(fechadas[AUTORIA])
        rotulo += " [sozinha]"

    total = arredonda_milhar(valor)
    detalhe = [f"{rotulo} -> {_fmt_moeda(total)}"]
    for produto, resto in restos.items():
        nome = "Autoria" if produto == AUTORIA else produto
        detalhe.append(f"({_num_br(resto)} de {nome} descartada — não fecha unidade)")
    return total, detalhe


def _premiacao_gerente(vendas: list[Venda]) -> tuple[int, list[str]]:
    """
    §4.2 — o "bloco" do gerente é a produção agregada da equipe no período.
    Uma única Autoria de qualquer corretor libera o preço cheio de todos os
    produtos premium vendidos pela equipe. Sem bônus de volume (§5, FAQ) e sem
    a nota de fração descartada, que é informação de corretor.
    """
    fechadas, _ = _unidades_fechadas(vendas)
    if not fechadas:
        return 0, []

    pool, rotulo, _so_autoria = _pool_produtos(fechadas)
    total = arredonda_milhar(pool * SPLIT_GERENTE)
    return total, [f"{rotulo} -> {_fmt_moeda(total)}"]


# ------------------------------------------------------------------ cenário

def _cenario(vendas: list[Venda]) -> dict:
    """Monta um cenário completo (realizado OU projeção) a partir das vendas."""
    vgv_total = round(sum(v.vgv for v in vendas), 2)
    unid_total = round(sum(v.vendas for v in vendas), 2)
    pct = (vgv_total / META_VGV) if META_VGV else 0.0

    # --- corretores (Salão/Online; B2B não entra no ranking de corretor) ---
    corretores: dict[str, dict] = {}
    por_corretor: dict[str, list[Venda]] = {}
    for v in vendas:
        if v.b2b or not v.corretor:
            continue
        por_corretor.setdefault(v.corretor, []).append(v)

    for nome, linhas in por_corretor.items():
        premiacao, detalhe = _premiacao_corretor(linhas)
        corretores[nome] = {
            "canal": linhas[0].canal,
            "gerente": linhas[0].gerente,
            "vgv": round(sum(x.vgv for x in linhas), 2),
            "vendas": round(sum(x.vendas for x in linhas), 2),
            "premiacao": premiacao,
            "detalhe": detalhe,
        }

    # --- gerentes (agregado da equipe, todos os canais) ---
    gerentes: dict[str, dict] = {}
    parcerias: dict[str, dict] = {}
    por_gerente: dict[str, list[Venda]] = {}
    for v in vendas:
        if not v.gerente:
            continue
        por_gerente.setdefault(v.gerente, []).append(v)

    for nome, linhas in por_gerente.items():
        premiacao, detalhe = _premiacao_gerente(linhas)

        linhas_b2b = [x for x in linhas if x.b2b]
        unidades_b2b = int(sum(x.vendas for x in linhas_b2b))
        fixo = unidades_b2b * B2B_FIXO_POR_VENDA

        equipe = sorted({x.corretor for x in linhas if x.corretor})
        gerentes[nome] = {
            "vgv": round(sum(x.vgv for x in linhas), 2),
            "vendas": round(sum(x.vendas for x in linhas), 2),
            "equipe": equipe,
            "premiacao": premiacao,
            "parcerias_fixo": fixo,
            "total": premiacao + fixo,
            "detalhe": detalhe,
        }

        if linhas_b2b:
            agrupado: dict[str, dict] = {}
            for x in linhas_b2b:
                item = agrupado.setdefault(x.corretor, {"nome": x.corretor, "vendas": 0.0, "vgv": 0.0})
                item["vendas"] = round(item["vendas"] + x.vendas, 2)
                item["vgv"] = round(item["vgv"] + x.vgv, 2)
            parcerias[nome] = {
                "vendas": round(sum(x.vendas for x in linhas_b2b), 2),
                "vgv": round(sum(x.vgv for x in linhas_b2b), 2),
                "unidades": unidades_b2b,
                "fixo": fixo,
                "corretores": sorted(agrupado.values(), key=lambda c: c["nome"]),
            }

    # --- §9 Equipe Comercial ---
    vgv_bruno = sum(v.vgv for v in vendas if v.produto in CARTEIRA_BRUNO)
    vgv_danilo = sum(v.vgv for v in vendas if v.produto in CARTEIRA_DANILO)
    comercial = {
        "Luiz": round(vgv_total * COMISSAO_FIXA, 2),
        "Bruno": round(vgv_bruno * COMISSAO_FIXA, 2),
        "Danilo": round(vgv_danilo * COMISSAO_FIXA, 2),
        "variavel_por_gestor": variavel_por_gestor(pct),
    }

    # --- §7 Prêmio Extra por Performance ---
    atingiu_gatilho = pct >= 0.80
    premio_extra = PREMIO_EXTRA_TOTAL if atingiu_gatilho else 0

    return {
        "vgv_total": vgv_total,
        "unid_total": unid_total,
        "pct": pct,
        "trigger": 1 if atingiu_gatilho else 0,
        "corretores": corretores,
        "gerentes": gerentes,
        "parcerias": parcerias,
        "comercial": comercial,
        "premio_extra": premio_extra,
        "sorteio": "BYD Dolphin Mini" if pct >= 1.0 else "—",
    }


def montar_data(vendas: list[Venda]) -> dict:
    """
    Monta o dicionário DATA completo consumido pelos HTMLs.

    `realizado` = só vendas com sinal compensado.
    `projecao`  = todas as vendas lançadas no período da campanha.
    """
    validas = [v for v in vendas if v.valida]
    return {
        "meta": {
            "vgv": META_VGV,
            "unid": META_UNID,
            "t60": round(META_VGV * 0.60),
            "t80": round(META_VGV * 0.80),
            "t100": META_VGV,
        },
        "realizado": _cenario(validas),
        "projecao": _cenario(vendas),
        "n_lancadas": len(vendas),
        "n_validas": len(validas),
    }
