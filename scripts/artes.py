#!/usr/bin/env python3
"""
Gera as artes .jpg da campanha a partir das próprias páginas do site.

Abre cada HTML num Chromium headless, força a visão "Projeção · vendas
lançadas" (que é a exibida nas artes históricas), espera as fontes carregarem e
salva o screenshot no mesmo tamanho dos arquivos que já estavam no repositório.

  python scripts/artes.py                # gera as 4 artes
  python scripts/artes.py --so-mudadas   # só regrava se a imagem mudou de fato
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent

# (html, jpg, largura, altura) — dimensões iguais às das artes já publicadas.
ARTES = [
    ("ranking-corretores.html", "ranking-corretores.jpg", 1080, 1080),
    ("ranking-gerentes.html", "ranking-gerentes.jpg", 1080, 1080),
    ("mural-corretores.html", "mural-corretores.jpg", 1080, 607),
    ("mural-gerentes.html", "mural-gerentes.jpg", 1080, 607),
]

# Fixa a visão de projeção e congela a auto-rotação do mural, para o screenshot
# não depender do instante em que foi tirado.
PREPARAR = """
() => {
  for (let i = 1; i < 100000; i++) window.clearInterval(i);
  if (typeof setView === 'function') setView('projecao');
  const rot = document.getElementById('rot');
  if (rot && rot.style.display !== 'none') rot.textContent = 'PRÉVIA · vendas lançadas';
}
"""


def gerar(raiz: Path, so_mudadas: bool = False) -> list[str]:
    alteradas: list[str] = []

    with sync_playwright() as p:
        navegador = p.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none"])
        try:
            for html, jpg, largura, altura in ARTES:
                origem = raiz / html
                destino = raiz / jpg
                if not origem.exists():
                    print(f"  ! {html}: não encontrado, pulando")
                    continue

                pagina = navegador.new_page(viewport={"width": largura, "height": altura})
                pagina.goto(origem.as_uri(), wait_until="networkidle")
                pagina.evaluate(PREPARAR)
                # Sem as fontes carregadas o texto sai com a métrica errada.
                pagina.evaluate("() => document.fonts.ready")
                pagina.wait_for_timeout(400)

                novo = pagina.screenshot(type="jpeg", quality=88)
                pagina.close()

                if so_mudadas and destino.exists() and destino.read_bytes() == novo:
                    print(f"  = {jpg}")
                    continue

                destino.write_bytes(novo)
                alteradas.append(jpg)
                print(f"  ~ {jpg} ({largura}x{altura}, {len(novo) // 1024} KB)")
        finally:
            navegador.close()

    return alteradas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=str(RAIZ))
    ap.add_argument("--so-mudadas", action="store_true",
                    help="não regrava artes cujo screenshot ficou idêntico")
    args = ap.parse_args()

    alteradas = gerar(Path(args.raiz).resolve(), args.so_mudadas)
    print(f"\n{len(alteradas)} arte(s) atualizada(s)" if alteradas else "\nNenhuma arte mudou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
