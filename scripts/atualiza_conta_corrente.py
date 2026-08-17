#!/usr/bin/env python3
"""
Gera o painel conta-corrente.html a partir da planilha do Drive.

A conferência por unidade roda ANTES de qualquer coisa: se a soma dos
lançamentos não bater com o quadro por unidade, o rateio por share mudou na
planilha e o script aborta sem gravar nada — número de verba não vai para a
diretoria sem conferir.

  python scripts/atualiza_conta_corrente.py
  python scripts/atualiza_conta_corrente.py --json vendas.json --quadro quadro.json
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
from conta_corrente import Lancamento, conferir, montar, resumo  # noqa: E402
from painel_conta_corrente import brl, pct, renderizar  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = "conta-corrente.html"
FUSO_SP = timezone(timedelta(hours=-3))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=str(RAIZ))
    ap.add_argument("--json", help="lançamentos de um arquivo local (testes)")
    ap.add_argument("--quadro", help="quadro por unidade de um arquivo local (testes)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raiz = Path(args.raiz)
    agora = datetime.now(FUSO_SP)

    if args.json:
        lancamentos = [Lancamento(**l) for l in json.loads(Path(args.json).read_text("utf-8"))]
        bruto = json.loads(Path(args.quadro).read_text("utf-8")) if args.quadro else []
        quadro = {(q["obra"], str(q["unidade"])): q["desconto"] for q in bruto}
    else:
        from planilha import carregar_conta_corrente
        sheet_id = os.environ.get("SHEET_ID")
        if not sheet_id:
            print("erro: SHEET_ID não definido", file=sys.stderr)
            return 2
        lancamentos, quadro = carregar_conta_corrente(sheet_id)

    # --- conferência obrigatória ---
    problemas = conferir(lancamentos, quadro)
    if problemas:
        print("CONFERÊNCIA NÃO BATEU — nada foi gravado:", file=sys.stderr)
        for p in problemas:
            print(f"  · {p}", file=sys.stderr)
        print("\nO rateio por share provavelmente mudou na planilha. "
              "Não publique número de verba antes de conferir.", file=sys.stderr)
        return 1
    print(f"conferência OK: {len(quadro)} unidades batem com os lançamentos")

    produtos, de_fora = montar(lancamentos)
    r = resumo(produtos)

    vgv = sum(l.vgv for l in lancamentos)
    unidades = round(sum(l.share for l in lancamentos), 1)

    print(f"aprovado {brl(r['aprovado'], 0)} | consumido {brl(r['consumido'])} "
          f"({pct(r['pct_consumido'])}) | disponível {brl(r['disponivel'])}")
    for p in sorted(produtos.values(), key=lambda x: -x.pct_consumo):
        print(f"  {p.nome:22} consumo {pct(p.pct_consumo):>7} · "
              f"vendas {pct(p.pct_vendas):>7} · {p.ritmo}")
    if r["em_alerta"]:
        print(f"  ATENÇÃO — fora de folga: {', '.join(r['em_alerta'])}")

    html = renderizar(produtos, de_fora, vgv, unidades, agora)

    # Este painel expõe verba e desconto por produto: nunca sai em texto aberto.
    senha = os.environ.get("STATICRYPT_PASSWORD")
    if not senha:
        print("erro: STATICRYPT_PASSWORD não definida. O painel de conta corrente expõe "
              "verba e desconto por produto e não pode ser publicado sem senha.",
              file=sys.stderr)
        return 2

    destino = raiz / SAIDA
    if destino.exists():
        # Reaproveita o salt já publicado, preservando os "remember me" do time.
        molde = destino.read_text("utf-8")
        # O IV do AES é aleatório a cada execução, então comparar o arquivo
        # cifrado acusaria mudança toda semana. A comparação tem de ser no
        # conteúdo decifrado, senão o robô commita à toa.
        try:
            if staticrypt.descriptografar(molde, senha) == html:
                print(f"\n{SAIDA} sem mudanças.")
                return 0
        except ValueError as e:
            print(f"  ! não deu para ler o {SAIDA} publicado ({e}); regravando do zero")
    else:
        # Primeira publicação: usa o painel.html como casca de criptografia. Ele
        # já tem o scaffolding do StatiCrypt e a MESMA senha, então a chave
        # derivada é a mesma — só o conteúdo cifrado muda.
        painel = raiz / "painel.html"
        if not painel.exists():
            print("erro: nem conta-corrente.html nem painel.html existem — não há de onde "
                  "tirar a casca do StatiCrypt.", file=sys.stderr)
            return 2
        print(f"  {SAIDA} ainda não existe: usando painel.html como casca do StatiCrypt")
        molde = painel.read_text("utf-8")

    html = staticrypt.recriptografar(molde, html, senha)
    html = re.sub(r"<title>.*?</title>",
                  "<title>Conta Corrente de Desconto — Efeito MAC Vendas</title>",
                  html, count=1, flags=re.S)

    if not args.dry_run:
        destino.write_text(html, encoding="utf-8")
    print(f"\n{SAIDA} atualizado{' (dry-run: não gravado)' if args.dry_run else ''}")

    if saida := os.environ.get("GITHUB_OUTPUT"):
        with open(saida, "a", encoding="utf-8") as fh:
            fh.write("mudou=true\n")
            fh.write(f"resumo=conta corrente: {brl(r['disponivel'])} disponíveis "
                     f"de {brl(r['aprovado'], 0)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
