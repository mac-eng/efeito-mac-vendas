"""
Renderiza o painel HTML da Conta Corrente de Desconto por Produto.

Layout enxuto e deliberado: UMA LINHA POR PRODUTO, tudo fechado por padrão.
A versão de cards empilhados foi descartada por poluição visual — não voltar a ela.
"""

from __future__ import annotations

from datetime import datetime

from conta_corrente import A_CONFIRMAR, FORA_DA_CONTA, Produto, resumo

META_VGV = 88_516_862

SELOS = {
    "folga": ("em folga", "#1f7a4d", "#e6f4ec"),
    "atenção": ("atenção", "#8a6a10", "#fdf3d8"),
    "acelerado": ("acelerado", "#a4521a", "#fbe9db"),
    "estouro": ("estouro", "#a01f1f", "#fbe0e0"),
}


def brl(valor: float, casas: int = 2) -> str:
    txt = f"{abs(valor):,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("- R$ " if valor < 0 else "R$ ") + txt


def pct(valor: float, casas: int = 1) -> str:
    return f"{valor * 100:.{casas}f}".replace(".", ",") + "%"


def _extrato(produto: Produto) -> str:
    if not produto.lancamentos:
        return '<p class="vazio">Nenhuma venda lançada para este produto até agora.</p>'

    linhas = []
    for l in produto.lancamentos:
        marcador = ('<span class="sinal ok">sinal compensado</span>' if l.sinal_compensado
                    else '<span class="sinal wait">aguardando sinal</span>')
        classe = "agio" if l.desconto > 0 else ""
        share = f"{l.share:.1f}".replace(".", ",")
        linhas.append(
            f'<tr><td class="mono">{l.data}</td>'
            f'<td>un. <b>{l.unidade}</b><span class="sub">{l.corretor or "—"} · {l.canal.title()}</span></td>'
            f'<td class="mono num">{share}</td>'
            f'<td class="mono num {classe}">{brl(l.desconto)}</td>'
            f'<td class="mono num">{brl(l.acumulado)}</td>'
            f'<td>{marcador}</td></tr>'
        )

    return f"""<table class="extrato">
    <thead><tr><th>Data</th><th>Unidade</th><th class="num">Share</th>
      <th class="num">Desconto PV</th><th class="num">Consumo acum.</th><th>Status</th></tr></thead>
    <tbody>{''.join(linhas)}</tbody>
    <tfoot><tr><td colspan="3">Subtotais</td>
      <td class="num mono">com sinal {brl(produto.consumido_com_sinal)}</td>
      <td class="num mono">aguardando {brl(produto.consumido_aguardando)}</td>
      <td></td></tr></tfoot>
  </table>"""


def _barra(produto: Produto, completa: bool) -> str:
    consumo = min(produto.pct_consumo, 1.0) * 100
    vendas = min(produto.pct_vendas, 1.0) * 100
    cor = SELOS[produto.ritmo][1]

    marcas = ""
    if completa:
        for unidades, valor in produto.checkpoints:
            pos = min(valor / produto.verba, 1.0) * 100
            marcas += (f'<i class="cp" style="left:{pos:.2f}%" '
                       f'title="{unidades} vendas · {brl(valor, 0)}"></i>')
        pos50 = 50.0
        marcas += f'<i class="cp meio" style="left:{pos50:.2f}%" title="50% da verba"></i>'

    return (f'<div class="barra{" grande" if completa else ""}">'
            f'<i class="fill" style="width:{consumo:.2f}%;background:{cor}"></i>'
            f'<i class="marca-vendas" style="left:{vendas:.2f}%"></i>{marcas}</div>')


def _produto(produto: Produto) -> str:
    rotulo, cor, fundo = SELOS[produto.ritmo]
    unid = f"{produto.unidades_vendidas:.1f}".replace(".", ",").replace(",0", "")
    tem_venda = "sim" if produto.lancamentos else "nao"
    alerta = "sim" if produto.ritmo != "folga" else "nao"
    nota = A_CONFIRMAR.get(produto.nome, "")

    return f"""<details class="produto" data-venda="{tem_venda}" data-alerta="{alerta}" data-nome="{produto.nome}">
  <summary>
    <span class="nome">{produto.nome}<span class="unid">{unid} de {produto.unidades_campanha} un.</span></span>
    {_barra(produto, completa=False)}
    <span class="cifras">
      <span><em>verba</em>{brl(produto.verba, 0)}</span>
      <span><em>consumido</em>{brl(produto.consumido)}</span>
      <span class="disp"><em>disponível</em>{brl(produto.disponivel)}</span>
    </span>
    <span class="selo" style="color:{cor};background:{fundo}">{rotulo}</span>
  </summary>
  <div class="detalhe">
    {_barra(produto, completa=True)}
    <div class="indicadores">
      <span><em>verba consumida</em>{pct(produto.pct_consumo)}</span>
      <span><em>unidades vendidas</em>{pct(produto.pct_vendas)}</span>
      <span><em>ritmo</em>{rotulo}</span>
      <span><em>disponível por unidade restante</em>{
        brl(produto.disponivel / max(produto.unidades_campanha - produto.unidades_vendidas, 1), 0)}</span>
    </div>
    {f'<p class="confirmar">{nota}</p>' if nota else ''}
    {_extrato(produto)}
  </div>
</details>"""


def renderizar(produtos: dict[str, Produto], de_fora: list, vgv_vendido: float,
               unidades_vendidas: float, agora: datetime) -> str:
    r = resumo(produtos)
    carimbo = agora.strftime("%d/%m/%Y às %H:%M")

    ordenados = sorted(produtos.values(), key=lambda p: (-p.pct_consumo, p.nome))
    linhas = "\n".join(_produto(p) for p in ordenados)

    opcoes = "\n".join(f'<option value="{p.nome}">{p.nome}</option>' for p in ordenados)

    nota_fora = "".join(
        f"<li><b>{nome}</b> — {motivo}."
        + (f' Lançado até agora: {brl(-sum(l.desconto for l in de_fora if l.obra == nome))}.'
           if any(l.obra == nome for l in de_fora) else "")
        + "</li>"
        for nome, motivo in FORA_DA_CONTA.items()
    )

    alerta = ""
    if r["em_alerta"]:
        alerta = (f'<div class="alerta">Fora de “em folga”: '
                  f'<b>{", ".join(r["em_alerta"])}</b>. A verba está queimando mais rápido '
                  f'que a venda nesses produtos.</div>')

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Conta Corrente de Desconto — Efeito MAC Vendas</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root{{--ink:#111112;--paper:#fff;--g1:#f4f4f3;--g2:#e7e7e5;--g4:#a9a7a2;--g5:#6d6b66;
--accent:#b4894d;--accent2:#d8b271;--go:#1f7a4d;--radius:16px;
--shadow:0 1px 2px rgba(17,17,18,.06),0 10px 30px rgba(17,17,18,.08)}}
*{{box-sizing:border-box}}html,body{{margin:0}}
body{{font-family:Archivo,system-ui,Arial,sans-serif;background:var(--g1);color:var(--ink);
-webkit-font-smoothing:antialiased}}
.mono{{font-variant-numeric:tabular-nums}}
.wrap{{max-width:1120px;margin:0 auto;padding:20px 20px 60px}}
.top{{background:var(--ink);color:#fff;border-radius:var(--radius);padding:24px 30px;box-shadow:var(--shadow)}}
.l1{{font-size:11px;font-weight:800;letter-spacing:.30em;color:#cfcfcd}}
.l2{{font-size:28px;font-weight:900;line-height:1.05;margin-top:2px}}
.l3{{font-size:12px;color:#a9a7a2;margin-top:8px}}
.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}}
.kpi{{background:var(--paper);border:1px solid var(--g2);border-left:5px solid var(--accent);
border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}}
.kpi .k{{font-size:10.5px;font-weight:800;letter-spacing:.10em;color:var(--g5);text-transform:uppercase}}
.kpi .v{{font-size:26px;font-weight:900;margin-top:4px}}
.kpi .s{{font-size:12.5px;color:var(--g5);margin-top:3px}}
.kpi .s.ok{{color:var(--go);font-weight:800}}
.alerta{{background:#fbe9db;border:1px solid #f0d2b8;border-radius:12px;padding:12px 16px;
font-size:13.5px;margin-bottom:12px}}
.controles{{display:flex;gap:8px;align-items:center;margin:18px 0 10px;flex-wrap:wrap}}
select,button{{font-family:inherit;font-size:13px;font-weight:700;padding:9px 14px;border-radius:10px;
border:1px solid var(--g2);background:var(--paper);color:var(--ink);cursor:pointer}}
button:hover{{border-color:var(--accent)}}
h2{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--g5);margin:22px 0 8px}}
.produto{{background:var(--paper);border:1px solid var(--g2);border-radius:14px;margin-bottom:8px;
box-shadow:var(--shadow);overflow:hidden}}
.produto[hidden]{{display:none}}
.produto>summary{{list-style:none;cursor:pointer;display:grid;
grid-template-columns:minmax(190px,1.1fr) minmax(120px,.9fr) minmax(300px,1.5fr) auto;
gap:16px;align-items:center;padding:14px 18px}}
.produto>summary::-webkit-details-marker{{display:none}}
.produto>summary:hover{{background:#fafaf9}}
.nome{{font-weight:900;font-size:15px;display:flex;flex-direction:column}}
.nome .unid{{font-weight:600;font-size:11.5px;color:var(--g5);margin-top:2px}}
.barra{{position:relative;height:8px;background:var(--g2);border-radius:999px}}
.barra.grande{{height:14px;margin:4px 0 16px}}
.barra .fill{{position:absolute;left:0;top:0;bottom:0;border-radius:999px}}
.barra .marca-vendas{{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--go)}}
.barra .cp{{position:absolute;top:-4px;bottom:-4px;width:1px;background:var(--g4)}}
.barra .cp.meio{{background:var(--ink);opacity:.35}}
.cifras{{display:flex;gap:18px;justify-content:flex-end;font-size:13px;font-variant-numeric:tabular-nums}}
.cifras span{{display:flex;flex-direction:column;text-align:right;font-weight:800}}
.cifras em{{font-style:normal;font-size:10px;font-weight:700;letter-spacing:.06em;
text-transform:uppercase;color:var(--g5);margin-bottom:2px}}
.cifras .disp{{color:var(--go)}}
.selo{{font-size:11px;font-weight:900;padding:5px 11px;border-radius:999px;white-space:nowrap}}
.detalhe{{padding:4px 18px 20px;border-top:1px solid var(--g2)}}
.indicadores{{display:flex;gap:26px;flex-wrap:wrap;margin-bottom:14px}}
.indicadores span{{display:flex;flex-direction:column;font-weight:800;font-size:14px}}
.indicadores em{{font-style:normal;font-size:10px;font-weight:700;letter-spacing:.06em;
text-transform:uppercase;color:var(--g5);margin-bottom:2px}}
.confirmar{{font-size:12.5px;color:#8a6a10;background:#fdf3d8;border-radius:8px;padding:8px 12px}}
table.extrato{{width:100%;border-collapse:collapse;font-size:12.5px}}
table.extrato th{{text-align:left;font-size:10px;letter-spacing:.06em;text-transform:uppercase;
color:var(--g5);padding:8px 10px;border-bottom:1px solid var(--g2)}}
table.extrato td{{padding:9px 10px;border-bottom:1px solid #f0f0ee;vertical-align:top}}
table.extrato .num,table.extrato th.num{{text-align:right}}
table.extrato .sub{{display:block;font-size:11px;color:var(--g5);font-weight:600}}
table.extrato tfoot td{{font-weight:800;color:var(--g5);border-top:1px solid var(--g2);border-bottom:none}}
.agio{{color:var(--go)}}
.sinal{{font-size:10px;font-weight:800;padding:3px 8px;border-radius:999px;white-space:nowrap}}
.sinal.ok{{background:#e6f4ec;color:var(--go)}}
.sinal.wait{{background:var(--g2);color:var(--g5)}}
.vazio{{font-size:13px;color:var(--g5);margin:6px 0 0}}
details.ajuda{{background:var(--paper);border:1px solid var(--g2);border-radius:14px;padding:12px 18px;margin-top:18px}}
details.ajuda summary{{cursor:pointer;font-weight:800;font-size:13px}}
details.ajuda p,details.ajuda li{{font-size:13px;color:#3a3a3c;line-height:1.55}}
.rodape{{font-size:12px;color:var(--g5);margin-top:20px;line-height:1.6}}
.rodape ul{{padding-left:18px;margin:6px 0}}
@media(max-width:900px){{.kpis{{grid-template-columns:1fr}}
.produto>summary{{grid-template-columns:1fr;gap:10px}}.cifras{{justify-content:flex-start}}}}
</style></head><body><div class="wrap">

<header class="top">
  <div class="l1">EFEITO MAC · VENDAS</div>
  <div class="l2">Conta Corrente de Desconto por Produto</div>
  <div class="l3">Motor de Vendas · Ago+Set 2026 &nbsp;·&nbsp; Atualizado em <b>{carimbo}</b></div>
</header>

<div class="kpis">
  <div class="kpi"><div class="k">Conta corrente aprovado</div>
    <div class="v mono">{brl(r['aprovado'], 0)}</div>
    <div class="s ok">{brl(r['disponivel'])} disponíveis</div></div>
  <div class="kpi"><div class="k">Consumido</div>
    <div class="v mono">{brl(r['consumido'])}</div>
    <div class="s">{pct(r['pct_consumido'])} da verba aprovada</div></div>
  <div class="kpi"><div class="k">VGV vendido</div>
    <div class="v mono">{brl(vgv_vendido, 0)}</div>
    <div class="s">{f'{unidades_vendidas:.1f}'.replace('.0', '').replace('.', ',')} un. · {pct(vgv_vendido / META_VGV)} da meta</div></div>
</div>

{alerta}

<div class="controles">
  <select id="filtro">
    <option value="todos">Todos os produtos</option>
    <option value="venda">Só com venda</option>
    <option value="alerta">Só em alerta</option>
    {opcoes}
  </select>
  <button id="abrir">Abrir todos</button>
</div>

<h2>Produtos com conta corrente</h2>
{linhas}

<details class="ajuda"><summary>Como ler</summary>
  <p>Cada produto começa a campanha com a <b>verba de desconto integral</b>. Desconto
  concedido consome verba; ágio praticado devolve (aparece em verde no extrato).</p>
  <p>A barra mostra a <b>verba já consumida</b>. O traço verde vertical marca o
  <b>avanço das vendas</b>. Se a barra passa do traço, a verba está queimando mais
  rápido que a venda:</p>
  <ul>
    <li><b>em folga</b> — consumo menor ou igual ao avanço das vendas;</li>
    <li><b>atenção</b> — consumo até 10 pontos percentuais à frente;</li>
    <li><b>acelerado</b> — mais que isso;</li>
    <li><b>estouro</b> — a verba do produto passou de 100%.</li>
  </ul>
  <p>Todas as vendas entram, validadas ou não — desconto é dinheiro real desde a
  assinatura. O status de sinal aparece linha a linha e nos subtotais.</p>
  <p>Em vendas divididas (share 0,5) cada linha carrega metade do desconto da
  unidade, do mesmo jeito que o VGV.</p>
</details>

<div class="rodape">
  <b>Produtos fora da conta corrente</b> — não têm verba nem limite de vendas; o
  desconto é apurado por outro modelo:
  <ul>{nota_fora}</ul>
</div>

</div>
<script>
const filtro = document.getElementById('filtro');
const botao = document.getElementById('abrir');
const produtos = [...document.querySelectorAll('.produto')];

filtro.addEventListener('change', () => {{
  const v = filtro.value;
  produtos.forEach(p => {{
    p.hidden = !(v === 'todos'
      || (v === 'venda' && p.dataset.venda === 'sim')
      || (v === 'alerta' && p.dataset.alerta === 'sim')
      || v === p.dataset.nome);
  }});
}});

botao.addEventListener('click', () => {{
  const visiveis = produtos.filter(p => !p.hidden);
  const abrir = visiveis.some(p => !p.open);
  visiveis.forEach(p => p.open = abrir);
  botao.textContent = abrir ? 'Fechar todos' : 'Abrir todos';
}});
</script>
</body></html>"""
