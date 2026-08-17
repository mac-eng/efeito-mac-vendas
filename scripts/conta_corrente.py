"""
Conta Corrente de Desconto por Produto — campanha Efeito MAC.

Controle de VERBA: cada produto entra na campanha com o desconto autorizado
integral. Desconto concedido consome verba; ágio praticado devolve. O que
importa é o RITMO — se a verba queima mais rápido que a venda, o produto chega
ao fim da campanha sem desconto para negociar.

Regras que não mudam:
  - saldo inicial de cada produto é a verba integral (não é zero acumulando);
  - DESCONTO PV negativo consome, positivo devolve (ágio);
  - o desconto JÁ VEM RATEADO POR SHARE na planilha: em venda 0,5 cada linha
    carrega metade do desconto da unidade. Somar as linhas, nunca deduplicar;
  - todas as vendas entram, validadas ou não — desconto é dinheiro real desde a
    assinatura. O sinal vira marcador e subtotal separado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AUTORIA = "Autoria MAC"

# Produtos COM conta corrente: (verba autorizada, unidades da campanha)
VERBAS: dict[str, tuple[int, int]] = {
    AUTORIA: (460_000, 34),
    "Mac Brooklin": (840_000, 6),
    "Mac Vila Clementino": (450_000, 4),
    "Mac Vila Mariana": (330_000, 4),   # Documento Mãe traz 5 un. — a confirmar
}
TOTAL_APROVADO = sum(v for v, _ in VERBAS.values())   # R$ 2.080.000

# Checkpoints extras do Autoria MAC: avaliar a cada 9 vendas (R$ 115.000/bloco).
CHECKPOINTS = {AUTORIA: [(9, 115_000), (17, 230_000), (26, 345_000)]}

# Produtos SEM conta corrente — desconto apurado por outro modelo. Nunca invente
# verba para eles; aparecem só na nota de rodapé.
FORA_DA_CONTA = {
    "Ateliê 365": "preço por metro quadrado, sem conta corrente de desconto",
    "Mac Ibirapuera": "desconto apurado por perda no PV, sem limite de vendas",
    "Mac Pinheiros": "desconto apurado por perda no PV, sem limite de vendas",
    "Mac Campo Belo": "desconto apurado por perda no PV, sem conta corrente (a confirmar)",
}

A_CONFIRMAR = {
    "Mac Vila Mariana": "Documento Mãe traz 5 unidades; aqui está 4 — a confirmar.",
    "Mac Campo Belo": "Ausência de conta corrente a confirmar.",
}


@dataclass
class Lancamento:
    data: str
    obra: str
    unidade: str
    corretor: str
    gerente: str
    canal: str
    share: float
    vgv: float
    desconto: float          # negativo consome verba, positivo devolve
    sinal_compensado: bool
    acumulado: float = 0.0   # consumo acumulado do produto até esta linha


@dataclass
class Produto:
    nome: str
    verba: int
    unidades_campanha: int
    lancamentos: list[Lancamento] = field(default_factory=list)

    @property
    def consumido(self) -> float:
        """Positivo = verba consumida. Ágio reduz o consumo."""
        return -sum(l.desconto for l in self.lancamentos)

    @property
    def consumido_com_sinal(self) -> float:
        return -sum(l.desconto for l in self.lancamentos if l.sinal_compensado)

    @property
    def consumido_aguardando(self) -> float:
        return -sum(l.desconto for l in self.lancamentos if not l.sinal_compensado)

    @property
    def disponivel(self) -> float:
        return self.verba - self.consumido

    @property
    def unidades_vendidas(self) -> float:
        return sum(l.share for l in self.lancamentos)

    @property
    def pct_consumo(self) -> float:
        return self.consumido / self.verba if self.verba else 0.0

    @property
    def pct_vendas(self) -> float:
        return self.unidades_vendidas / self.unidades_campanha if self.unidades_campanha else 0.0

    @property
    def ritmo(self) -> str:
        """folga · atenção · acelerado · estouro"""
        if self.pct_consumo > 1.0:
            return "estouro"
        avanco = (self.pct_consumo - self.pct_vendas) * 100  # em pontos percentuais
        if avanco <= 0:
            return "folga"
        if avanco <= 10:
            return "atenção"
        return "acelerado"

    @property
    def checkpoints(self) -> list[tuple[int, int]]:
        return CHECKPOINTS.get(self.nome, [])


def conferir(lancamentos: list[Lancamento], quadro: dict[tuple[str, str], float],
             tolerancia: float = 0.02) -> list[str]:
    """
    A soma do DESCONTO PV das linhas de cada unidade tem de bater com o quadro
    por unidade da planilha. Divergência significa que o rateio por share mudou
    — nesse caso NÃO se publica número para a diretoria.

    Devolve a lista de divergências (vazia = tudo certo).
    """
    somado: dict[tuple[str, str], float] = {}
    for l in lancamentos:
        chave = (l.obra, str(l.unidade))
        somado[chave] = somado.get(chave, 0.0) + l.desconto

    problemas = []
    for chave, esperado in quadro.items():
        obtido = somado.get(chave)
        if obtido is None:
            problemas.append(f"{chave[0]} un. {chave[1]}: no quadro ({esperado:,.2f}) "
                             f"mas sem linha de lançamento")
        elif abs(obtido - esperado) > tolerancia:
            problemas.append(f"{chave[0]} un. {chave[1]}: lançamentos somam {obtido:,.2f}, "
                             f"quadro diz {esperado:,.2f}")
    for chave, obtido in somado.items():
        if chave not in quadro:
            problemas.append(f"{chave[0]} un. {chave[1]}: lançado {obtido:,.2f} "
                             f"mas ausente do quadro por unidade")
    return problemas


def montar(lancamentos: list[Lancamento]) -> tuple[dict[str, Produto], list[Lancamento]]:
    """
    Distribui os lançamentos entre os produtos com conta corrente e devolve
    também os lançamentos dos produtos que ficam de fora (para a nota de rodapé).
    """
    produtos = {
        nome: Produto(nome=nome, verba=verba, unidades_campanha=unid)
        for nome, (verba, unid) in VERBAS.items()
    }
    de_fora: list[Lancamento] = []

    for l in sorted(lancamentos, key=lambda x: (x.data, x.unidade)):
        if l.obra in produtos:
            produtos[l.obra].lancamentos.append(l)
        elif l.desconto:
            de_fora.append(l)

    for produto in produtos.values():
        acumulado = 0.0
        for l in produto.lancamentos:
            acumulado += -l.desconto
            l.acumulado = acumulado

    return produtos, de_fora


def resumo(produtos: dict[str, Produto]) -> dict:
    consumido = sum(p.consumido for p in produtos.values())
    return {
        "aprovado": TOTAL_APROVADO,
        "consumido": consumido,
        "disponivel": TOTAL_APROVADO - consumido,
        "pct_consumido": consumido / TOTAL_APROVADO if TOTAL_APROVADO else 0.0,
        "em_alerta": [p.nome for p in produtos.values() if p.ritmo != "folga"],
    }
