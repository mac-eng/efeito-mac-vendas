"""
Teste de regressão do motor de premiação.

A fixture abaixo são as 7 vendas lançadas até 14/08/2026 09:37. O bloco
`projecao` esperado foi copiado literalmente do DATA que está publicado no site
naquela data — se o motor reproduz esse bloco campo a campo, a implementação das
regras do Manual está fiel ao que já foi validado pelo time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from motor import Venda, montar_data, nome_corretor, nome_produto, arredonda_milhar  # noqa: E402


def _v(obra, unidade, corretor, gerente, canal, vendas, vgv, valida=False):
    return Venda(
        produto=nome_produto(obra),
        unidade=unidade,
        corretor=nome_corretor(corretor),
        gerente=gerente,
        canal=canal,
        vendas=vendas,
        vgv=vgv,
        valida=valida,
    )


FIXTURE_14_08 = [
    _v("AUTORIA MAC", "712", "CINTIA - CINTIA DE OLIVEIRA ROSA", "MITUI", "ONLINE", 1.0, 569000.0),
    _v("MAC BROOKLIN", "134", "ROBSON - ROBSON AZEVEDO", "DAMIAO", "SALÃO", 1.0, 1619000.0),
    _v("AUTORIA MAC", "1313", "JENIFFER DOS SANTOS SILVA", "DIEGO", "PARCERIAS", 1.0, 605289.0, valida=True),
    _v("AUTORIA MAC", "1609", "U REAL ESTATE LTDA", "DIEGO", "PARCERIAS", 0.5, 305434.79),
    _v("AUTORIA MAC", "1609", "FOXTER CONSULTORIA IMOBILIARIA LTDA", "DIEGO", "PARCERIAS", 0.5, 305434.79),
    _v("AUTORIA MAC", "1113", "ROBSON - ROBSON AZEVEDO", "DAMIAO", "SALÃO", 0.5, 293950.0),
    _v("AUTORIA MAC", "1113", "BRUNA - BRUNA GIOVANA CESARIO DE ANDRADE", "MITUI", "SALÃO", 0.5, 293950.0),
]

# Copiado do site publicado em 14/08/2026 09:37.
PROJECAO_PUBLICADA = {
    "vgv_total": 3992058.58,
    "unid_total": 5.0,
    "pct": 0.04509941371396559,
    "trigger": 0,
    "corretores": {
        "CINTIA": {"canal": "ONLINE", "gerente": "MITUI", "vgv": 569000.0, "vendas": 1.0,
                   "premiacao": 2000, "detalhe": ["1x Autoria MAC [sozinha] -> R$2,000"]},
        "ROBSON": {"canal": "SALÃO", "gerente": "DAMIAO", "vgv": 1912950.0, "vendas": 1.5,
                   "premiacao": 5000,
                   "detalhe": ["1x Mac Brooklin [sozinho (75%)] -> R$5,000",
                               "(0,5 de Autoria descartada — não fecha unidade)"]},
        "BRUNA": {"canal": "SALÃO", "gerente": "MITUI", "vgv": 293950.0, "vendas": 0.5,
                  "premiacao": 0, "detalhe": ["0,5 venda — não pontua até somar 1 unidade"]},
    },
    "gerentes": {
        "MITUI": {"vgv": 862950.0, "vendas": 1.5, "equipe": ["BRUNA", "CINTIA"], "premiacao": 1000,
                  "parcerias_fixo": 0, "total": 1000, "detalhe": ["1x Autoria MAC -> R$1,000"]},
        "DAMIAO": {"vgv": 1912950.0, "vendas": 1.5, "equipe": ["ROBSON"], "premiacao": 3000,
                   "parcerias_fixo": 0, "total": 3000,
                   "detalhe": ["1x Mac Brooklin [sozinho (75%)] -> R$3,000"]},
        "DIEGO": {"vgv": 1216158.58, "vendas": 2.0, "equipe": ["FOXTER", "JENIFFER", "U REAL ESTATE"],
                  "premiacao": 3000, "parcerias_fixo": 4000, "total": 7000,
                  "detalhe": ["2x Autoria MAC -> R$3,000"]},
    },
    "parcerias": {
        "DIEGO": {"vendas": 2.0, "vgv": 1216158.58, "unidades": 2, "fixo": 4000,
                  "corretores": [{"nome": "FOXTER", "vendas": 0.5, "vgv": 305434.79},
                                 {"nome": "JENIFFER", "vendas": 1.0, "vgv": 605289.0},
                                 {"nome": "U REAL ESTATE", "vendas": 0.5, "vgv": 305434.79}]},
    },
    "comercial": {"Luiz": 3992.06, "Bruno": 1619.0, "Danilo": 2373.06, "variavel_por_gestor": 0},
    "premio_extra": 0,
    "sorteio": "—",
}

REALIZADO_PUBLICADO = {
    "vgv_total": 605289.0,
    "unid_total": 1.0,
    "pct": 0.006838120854306832,
    "trigger": 0,
    "corretores": {},
    "gerentes": {
        "DIEGO": {"vgv": 605289.0, "vendas": 1.0, "equipe": ["JENIFFER"], "premiacao": 1000,
                  "parcerias_fixo": 2000, "total": 3000, "detalhe": ["1x Autoria MAC -> R$1,000"]},
    },
    "parcerias": {
        "DIEGO": {"vendas": 1.0, "vgv": 605289.0, "unidades": 1, "fixo": 2000,
                  "corretores": [{"nome": "JENIFFER", "vendas": 1.0, "vgv": 605289.0}]},
    },
    "comercial": {"Luiz": 605.29, "Bruno": 0.0, "Danilo": 605.29, "variavel_por_gestor": 0},
    "premio_extra": 0,
    "sorteio": "—",
}


def test_reproduz_projecao_publicada():
    assert montar_data(FIXTURE_14_08)["projecao"] == PROJECAO_PUBLICADA


def test_reproduz_realizado_publicado():
    assert montar_data(FIXTURE_14_08)["realizado"] == REALIZADO_PUBLICADO


def test_contadores():
    data = montar_data(FIXTURE_14_08)
    assert data["n_lancadas"] == 7
    assert data["n_validas"] == 1
    assert data["meta"] == {"vgv": 88516862, "unid": 73, "t60": 53110117,
                            "t80": 70813490, "t100": 88516862}


def test_nomes_de_corretor():
    assert nome_corretor("CINTIA - CINTIA DE OLIVEIRA ROSA") == "CINTIA"
    assert nome_corretor("JENIFFER DOS SANTOS SILVA") == "JENIFFER"
    assert nome_corretor("U REAL ESTATE LTDA") == "U REAL ESTATE"
    assert nome_corretor("FOXTER CONSULTORIA IMOBILIARIA LTDA") == "FOXTER"


def test_arredondamento_meio_sobe():
    # §3: valores terminados em ".500" sobem para o próximo múltiplo de 1.000.
    assert arredonda_milhar(4_500) == 5_000
    assert arredonda_milhar(4_499) == 4_000
    assert arredonda_milhar(3_249.3) == 3_000
    assert arredonda_milhar(4_873.95) == 5_000


def test_tabela_5_1_autoria_sozinha():
    """§5.1 — régua oficial de Autoria MAC sem combo, corretor e gerente."""
    esperado = {1: (2000, 1000), 2: (7000, 3000), 3: (9000, 4000),
                4: (13000, 5000), 5: (15000, 7000)}
    for unidades, (corr, ger) in esperado.items():
        vendas = [
            Venda(produto="Autoria MAC", unidade=str(i), corretor="X", gerente="G",
                  canal="SALÃO", vendas=1.0, vgv=100.0, valida=True)
            for i in range(unidades)
        ]
        data = montar_data(vendas)["realizado"]
        assert data["corretores"]["X"]["premiacao"] == corr, f"{unidades} un. (corretor)"
        assert data["gerentes"]["G"]["premiacao"] == ger, f"{unidades} un. (gerente)"


def test_exemplo_3_3_mac_pinheiros():
    """§3.3 — exemplo passo a passo do Manual, 1 unidade de Mac Pinheiros."""
    casos = {0: (6000, 4000), 1: (10000, 7000), 2: (12000, 8000), 3: (16000, 11000)}
    for autorias, (corr, ger) in casos.items():
        vendas = [Venda(produto="Mac Pinheiros", unidade="1", corretor="X", gerente="G",
                        canal="SALÃO", vendas=1.0, vgv=100.0, valida=True)]
        vendas += [
            Venda(produto="Autoria MAC", unidade=f"a{i}", corretor="X", gerente="G",
                  canal="SALÃO", vendas=1.0, vgv=100.0, valida=True)
            for i in range(autorias)
        ]
        data = montar_data(vendas)["realizado"]
        assert data["corretores"]["X"]["premiacao"] == corr, f"+{autorias} Autoria (corretor)"
        assert data["gerentes"]["G"]["premiacao"] == ger, f"+{autorias} Autoria (gerente)"
