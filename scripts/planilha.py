"""
Leitura da planilha "Campanha Estoque - Geral" no Google Drive.

Autentica com uma service account (JSON no secret GOOGLE_SERVICE_ACCOUNT_JSON) e
devolve a lista de Vendas já normalizada para o motor.

A aba é localizada pelo conteúdo do cabeçalho (procura "DATA VENDA"), não pelo
nome nem pela posição — assim renomear ou reordenar abas não quebra o robô.
"""

from __future__ import annotations

import json
import os
import unicodedata

import gspread
from google.oauth2.service_account import Credentials

from motor import Venda, nome_corretor, nome_produto

ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

COL_DATA = "DATA VENDA"
OBRIGATORIAS = [COL_DATA, "OBRA", "VGV", "VENDAS", "GERENTE", "CORRETOR"]


def _chave(texto: str) -> str:
    """Normaliza um cabeçalho: sem acento, maiúsculo, sem espaços extras."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


def _numero(valor) -> float:
    """Converte '1.619.000,00' / '0,50' / 1619000 para float. Vazio -> 0.0"""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    txt = str(valor).strip().replace("R$", "").replace(" ", "")
    if not txt or txt in {"-", "—"}:
        return 0.0
    negativo = txt.startswith("-")
    txt = txt.lstrip("-")
    # pt-BR: ponto é separador de milhar, vírgula é decimal.
    txt = txt.replace(".", "").replace(",", ".")
    try:
        n = float(txt)
    except ValueError:
        return 0.0
    return -n if negativo else n


def abrir_planilha(sheet_id: str):
    bruto = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not bruto:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON não definido. "
            "No GitHub: Settings > Secrets and variables > Actions."
        )
    creds = Credentials.from_service_account_info(json.loads(bruto), scopes=ESCOPOS)
    return gspread.authorize(creds).open_by_key(sheet_id)


def _aba_de_vendas(planilha):
    alvo = _chave(COL_DATA)
    for aba in planilha.worksheets():
        linhas = aba.get_values("A1:AZ12")
        for i, linha in enumerate(linhas):
            if any(_chave(c) == alvo for c in linha):
                return aba, i
    raise RuntimeError(
        f"Nenhuma aba com a coluna '{COL_DATA}' no cabeçalho. "
        "A planilha mudou de estrutura?"
    )


def carregar_vendas(sheet_id: str) -> list[Venda]:
    planilha = abrir_planilha(sheet_id)
    aba, linha_cabecalho = _aba_de_vendas(planilha)
    tabela = aba.get_values()

    cabecalho = [_chave(c) for c in tabela[linha_cabecalho]]
    faltando = [c for c in OBRIGATORIAS if _chave(c) not in cabecalho]
    if faltando:
        raise RuntimeError(f"Colunas ausentes na planilha: {', '.join(faltando)}")

    idx = {nome: i for i, nome in enumerate(cabecalho) if nome}

    def campo(linha, nome, padrao=""):
        i = idx.get(_chave(nome))
        if i is None or i >= len(linha):
            return padrao
        return linha[i]

    vendas: list[Venda] = []
    for linha in tabela[linha_cabecalho + 1:]:
        if not any(str(c).strip() for c in linha):
            continue
        obra = str(campo(linha, "OBRA")).strip()
        if not obra or not str(campo(linha, COL_DATA)).strip():
            continue

        # Só o que está marcado como período da campanha.
        periodo = _chave(str(campo(linha, "PERÍODO CAMPANHA", "CAMPANHA")))
        if periodo and periodo != "CAMPANHA":
            continue

        qtd = _numero(campo(linha, "VENDAS"))
        if qtd <= 0:
            continue

        vendas.append(
            Venda(
                produto=nome_produto(obra),
                unidade=str(campo(linha, "UNIDADE")).strip(),
                corretor=nome_corretor(str(campo(linha, "CORRETOR"))),
                gerente=str(campo(linha, "GERENTE")).strip().upper(),
                canal=str(campo(linha, "CANAL VENDAS")).strip().upper(),
                vendas=qtd,
                vgv=_numero(campo(linha, "VGV")),
                # Sinal compensado: a planilha zera "VENDAS VÁLIDAS" até o sinal cair.
                valida=_numero(campo(linha, "VENDAS VÁLIDAS")) > 0,
            )
        )

    if not vendas:
        raise RuntimeError("Nenhuma venda de campanha encontrada — abortando sem alterar o site.")
    return vendas


# ------------------------------------------------------- conta corrente

COL_QUADRO = "DESCONTO"


def carregar_conta_corrente(sheet_id: str):
    """
    Devolve (lancamentos, quadro) para a Conta Corrente de Desconto.

    `lancamentos` sai da aba de vendas (uma linha por corretor, com o DESCONTO PV
    já rateado por share). `quadro` sai da aba "por unidade" e serve só de
    conferência — a soma dos lançamentos de cada unidade tem de bater com ele.
    """
    from conta_corrente import Lancamento

    planilha = abrir_planilha(sheet_id)
    aba, linha_cabecalho = _aba_de_vendas(planilha)
    tabela = aba.get_values()
    cabecalho = [_chave(c) for c in tabela[linha_cabecalho]]
    idx = {nome: i for i, nome in enumerate(cabecalho) if nome}

    if _chave("DESCONTO PV") not in idx:
        raise RuntimeError("Coluna 'DESCONTO PV' ausente na aba de vendas.")

    def campo(linha, nome, padrao=""):
        i = idx.get(_chave(nome))
        if i is None or i >= len(linha):
            return padrao
        return linha[i]

    lancamentos = []
    for linha in tabela[linha_cabecalho + 1:]:
        obra = str(campo(linha, "OBRA")).strip()
        data = str(campo(linha, COL_DATA)).strip()
        if not obra or not data:
            continue
        periodo = _chave(str(campo(linha, "PERÍODO CAMPANHA", "CAMPANHA")))
        if periodo and periodo != "CAMPANHA":
            continue
        share = _numero(campo(linha, "VENDAS"))
        if share <= 0:
            continue

        lancamentos.append(
            Lancamento(
                data=data,
                obra=nome_produto(obra),
                unidade=str(campo(linha, "UNIDADE")).strip(),
                corretor=nome_corretor(str(campo(linha, "CORRETOR"))),
                gerente=str(campo(linha, "GERENTE")).strip().upper(),
                canal=str(campo(linha, "CANAL VENDAS")).strip().upper(),
                share=share,
                vgv=_numero(campo(linha, "VGV")),
                desconto=_numero(campo(linha, "DESCONTO PV")),
                sinal_compensado=_numero(campo(linha, "VENDAS VÁLIDAS")) > 0,
            )
        )

    return lancamentos, _quadro_por_unidade(planilha)


def _quadro_por_unidade(planilha) -> dict[tuple[str, float], float]:
    """Aba de conferência: uma linha por unidade, com o desconto total dela."""
    alvo_obra, alvo_unid, alvo_desc = _chave("OBRA"), _chave("UNIDADE"), _chave(COL_QUADRO)

    for aba in planilha.worksheets():
        tabela = aba.get_values()
        for i, linha in enumerate(tabela[:12]):
            chaves = [_chave(c) for c in linha]
            # O quadro tem OBRA/UNIDADE/DESCONTO mas NÃO tem a coluna DESCONTO PV.
            if (alvo_obra in chaves and alvo_unid in chaves and alvo_desc in chaves
                    and _chave("DESCONTO PV") not in chaves):
                col = {c: j for j, c in enumerate(chaves) if c}
                quadro: dict[tuple[str, str], float] = {}
                for l in tabela[i + 1:]:
                    if len(l) <= max(col[alvo_obra], col[alvo_unid], col[alvo_desc]):
                        continue
                    obra = str(l[col[alvo_obra]]).strip()
                    unidade = str(l[col[alvo_unid]]).strip()
                    if not obra or not unidade:
                        continue
                    chave = (nome_produto(obra), unidade)
                    quadro[chave] = quadro.get(chave, 0.0) + _numero(l[col[alvo_desc]])
                if quadro:
                    return quadro
    raise RuntimeError(
        "Aba de conferência por unidade (OBRA / UNIDADE / DESCONTO) não encontrada."
    )
