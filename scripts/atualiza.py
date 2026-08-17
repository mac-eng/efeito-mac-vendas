#!/usr/bin/env python3
"""
Atualiza os números do site da campanha Efeito MAC a partir da planilha do Drive.

  python scripts/atualiza.py                 # lê a planilha e grava os HTMLs
  python scripts/atualiza.py --dry-run       # só mostra o que mudaria
  python scripts/atualiza.py --json dados.json   # usa um JSON local em vez do Drive

Variáveis de ambiente:
  SHEET_ID                      id da planilha no Drive (obrigatório)
  GOOGLE_SERVICE_ACCOUNT_JSON   credencial da service account (obrigatório)
  STATICRYPT_PASSWORD           senha do painel.html (opcional; sem ela o painel
                                é pulado e os demais arquivos são atualizados)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import staticrypt  # noqa: E402
from motor import montar_data  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

# Arquivos com o bloco DATA em texto aberto.
ABERTOS = [
    "ranking-corretores.html",
    "ranking-gerentes.html",
    "mural-corretores.html",
    "mural-gerentes.html",
]
CRIPTOGRAFADO = "painel.html"

# `const DATA={...};` (rankings/murais) e `const DATA = {...};` (painel)
RE_DATA = re.compile(r"(const\s+DATA\s*=\s*)(\{.*?\})(\s*;)", re.DOTALL)
RE_CARIMBO = re.compile(r"(Atualizado em\s*<b>)(.*?)(</b>)")
RE_CARIMBO_PAINEL = re.compile(r"(🔄 Atualizado em\s*)(\d{2}/\d{2}/\d{4})")

FUSO_SP = timezone(timedelta(hours=-3))


def _substituir(html: str, data_json: str, agora: datetime) -> tuple[str, int]:
    """Troca o bloco DATA e os carimbos de data. Devolve (html, nº de trocas)."""
    novo, trocas = RE_DATA.subn(lambda m: m.group(1) + data_json + m.group(3), html)
    if trocas == 0:
        raise ValueError("bloco 'const DATA = {...}' não encontrado")

    completo = agora.strftime("%d/%m/%Y às %H:%M")
    curto = agora.strftime("%d/%m/%Y")
    novo = RE_CARIMBO.sub(lambda m: m.group(1) + completo + m.group(3), novo)
    novo = RE_CARIMBO_PAINEL.sub(lambda m: m.group(1) + curto, novo)
    return novo, trocas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="não grava nada")
    ap.add_argument("--json", help="lê as vendas de um JSON local (para testes)")
    ap.add_argument("--raiz", default=str(RAIZ), help="pasta do repositório")
    args = ap.parse_args()

    raiz = Path(args.raiz)
    agora = datetime.now(FUSO_SP)

    if args.json:
        from motor import Venda
        vendas = [Venda(**linha) for linha in json.loads(Path(args.json).read_text("utf-8"))]
    else:
        from planilha import carregar_vendas
        sheet_id = os.environ.get("SHEET_ID")
        if not sheet_id:
            print("erro: SHEET_ID não definido", file=sys.stderr)
            return 2
        vendas = carregar_vendas(sheet_id)

    data = montar_data(vendas)
    data_json = json.dumps(data, ensure_ascii=False, separators=(", ", ": "))

    print(f"vendas lançadas: {data['n_lancadas']} | com sinal compensado: {data['n_validas']}")
    print(f"realizado: R$ {data['realizado']['vgv_total']:,.2f} "
          f"({data['realizado']['pct'] * 100:.2f}% da meta) "
          f"· {data['realizado']['unid_total']} un.")
    print(f"projeção:  R$ {data['projecao']['vgv_total']:,.2f} "
          f"({data['projecao']['pct'] * 100:.2f}% da meta) "
          f"· {data['projecao']['unid_total']} un.")

    alterados: list[str] = []

    for nome in ABERTOS:
        caminho = raiz / nome
        if not caminho.exists():
            print(f"  ! {nome}: não encontrado, pulando")
            continue
        original = caminho.read_text(encoding="utf-8")
        try:
            novo, _ = _substituir(original, data_json, agora)
        except ValueError as e:
            print(f"  ! {nome}: {e}")
            continue
        if novo != original:
            alterados.append(nome)
            if not args.dry_run:
                caminho.write_text(novo, encoding="utf-8")
        print(f"  {'~' if novo != original else '='} {nome}")

    # painel.html: descriptografa, troca o DATA, re-criptografa com o mesmo salt.
    senha = os.environ.get("STATICRYPT_PASSWORD")
    caminho = raiz / CRIPTOGRAFADO
    if not caminho.exists():
        print(f"  ! {CRIPTOGRAFADO}: não encontrado, pulando")
    elif not senha:
        print(f"  ! {CRIPTOGRAFADO}: STATICRYPT_PASSWORD não definida, pulando")
    else:
        original = caminho.read_text(encoding="utf-8")
        plano = staticrypt.descriptografar(original, senha)
        novo_plano, _ = _substituir(plano, data_json, agora)
        if novo_plano != plano:
            alterados.append(CRIPTOGRAFADO)
            if not args.dry_run:
                caminho.write_text(
                    staticrypt.recriptografar(original, novo_plano, senha),
                    encoding="utf-8",
                )
            print(f"  ~ {CRIPTOGRAFADO}")
        else:
            print(f"  = {CRIPTOGRAFADO}")

    if not alterados:
        print("\nNenhum número mudou desde a última publicação.")
        return 0

    print(f"\n{len(alterados)} arquivo(s) atualizado(s): {', '.join(alterados)}")
    if args.dry_run:
        print("(dry-run: nada foi gravado)")

    # Sinaliza para o workflow que há o que commitar.
    if resumo := os.environ.get("GITHUB_OUTPUT"):
        with open(resumo, "a", encoding="utf-8") as fh:
            fh.write("mudou=true\n")
            fh.write(f"resumo=realizado R$ {data['realizado']['vgv_total']:,.2f} "
                     f"({data['realizado']['pct'] * 100:.2f}% da meta), "
                     f"{data['n_validas']}/{data['n_lancadas']} vendas com sinal\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
