# Como os números da campanha Efeito MAC vão para o ar

O site é publicado por GitHub Pages a partir da branch `main`. Os números vivem
num bloco `const DATA = {...}` dentro de seis arquivos:

| Arquivo | Conteúdo |
| --- | --- |
| `ranking-corretores.html` | Ranking de corretores (Salão/Online) |
| `ranking-gerentes.html` | Ranking de gerentes |
| `mural-corretores.html` | Mural para o telão |
| `mural-gerentes.html` | Mural para o telão |
| `painel.html` | Painel completo — **criptografado com StatiCrypt** |
| `conta-corrente.html` | Conta Corrente de Desconto — **criptografado com StatiCrypt** |

**O site é estático e o repositório não fala com o Google.** Não há robô, não há
service account, não há secret de credencial. Os HTMLs já chegam à `main` com os
números dentro — quem lê a planilha, calcula e gera os arquivos é o Cowork, com o
acesso do próprio usuário; quem publica é a Mari, subindo a versão do dia.

> **Por que assim.** Até 11/09/2026 existia um workflow (`Atualiza números da
> campanha`) que rodaria às 09:30, leria a planilha com uma service account e
> commitaria sozinho. Ele **nunca funcionou**: o secret `GOOGLE_SERVICE_ACCOUNT_JSON`
> nunca foi criado (o log da run de 31/08 morre em `RuntimeError: GOOGLE_SERVICE_ACCOUNT_JSON
> não definido`) e a service account nunca entrou no compartilhamento da planilha.
> Em 10/09/2026 o Fabio avaliou que liberar esse acesso não seria seguro, e a
> decisão foi tirar o robô do caminho em vez de destravá-lo. O workflow e o
> `scripts/planilha.py` foram removidos em 11/09/2026 — estão no histórico do Git
> se um dia houver um caminho seguro para voltar atrás.

## O ciclo, hoje

| Quem | O que faz |
| --- | --- |
| **Cowork** (segundas e quintas, 10:00) | Lê a planilha no Drive, recalcula tudo do zero, roda os scripts, gera os 6 HTMLs e as 4 artes, e entrega um `.zip`. |
| **Mari** | Descompacta o `.zip` e sobe os **10 arquivos** (não o `.zip`) na `main`. O Pages publica sozinho. |
| **Cowork** | Deixa os dois rascunhos de e-mail no Gmail, com os mesmos números. |

A ordem importa: **gera → publica → comunica.** Os e-mails levam os números do
Cowork, que são a fonte da verdade; se o site ainda não tiver sido republicado, o
resumo avisa e o e-mail não deve sair antes.

**Como subir:** o caminho mais curto é
<https://github.com/mac-eng/efeito-mac-vendas/upload/main>, que já abre a tela de
upload. Arraste os 10 arquivos, escreva a mensagem, deixe marcado *Commit directly
to the main branch* e clique em *Commit changes*. Arrastar o `.zip` fechado não
publica nada.

> **Atenção ao clone local.** Se você também mexe no `C:\Git\efeito-mac-vendas`,
> rode `git pull` antes de qualquer push — senão o Git recusa.

## Como o cálculo é feito

`scripts/motor.py` implementa as regras do *Manual Operacional — Motor de Vendas*:
retenção de 25% quando não há Autoria no bloco (§3), tetos por produto (§3.1),
kicker de 20% a partir da 3ª Autoria (§3.2), split 60/40 entre corretor e gerente
(§4), agregação por equipe no cálculo do gerente (§4.2), regime B2B com valor fixo
de R$ 2.000 por venda (§4.3), bônus de volume da Autoria sozinha (§5), Prêmio Extra
por Performance a partir de 80% da meta (§7) e a Premiação Equipe Comercial (§9).

`tests/test_motor.py` guarda as 7 vendas lançadas até 14/08/2026 e o `DATA` que
estava publicado no site naquele dia. O teste exige que o motor reproduza aquele
bloco campo a campo, além de conferir a régua da §5.1 e o exemplo da §3.3 do
Manual. **Rode os testes antes de gerar** — se as regras quebrarem, é melhor não
publicar do que publicar número errado.

## Régua de leitura da planilha (desde 24/08/2026)

Vale para quem monta o JSON. Cada linha é classificada pela coluna **STATUS**,
nesta ordem:

| STATUS | O que acontece |
| --- | --- |
| `NÃO` | descartada — desistência ou vaga extra. Não entra em VGV, unidades, curva, prêmio, listagem nem conta corrente. |
| `EM VALIDAÇÃO` | entra só na `projecao`; fica fora do `realizado` até o sinal compensar. |
| `VENDA OK` | régua completa. |
| `VENDA INTERNA` | entra no `realizado`, mas só no volume (ver abaixo). |

É uma linha por corretor: venda dividida vira duas linhas de 0,5, com VGV e
DESCONTO PV já rateados por share. **Some as linhas, nunca deduplique.**

**Venda interna** é a linha com `GERENTE = "VENDA INTERNA"`. Ela soma no VGV, nas
unidades e no % da meta, e paga a Premiação Equipe Comercial (§9) e a verba de
desconto — mas **não** aparece em ranking nenhum e **não** gera prêmio de corretor
ou de gerente. No motor isso é o campo `Venda.interna`.

> **Nunca use a coluna `PERÍODO CAMPANHA` como filtro de campanha.** Ela devolve
> `OK` / `NÃO` sobre a janela de datas, nunca a palavra `CAMPANHA`. Até 24/08/2026
> o leitor filtrava por ela e descartava **100% das linhas** — o site ficou
> congelado nos números de 14/08. A classificação está em `STATUS` e `VENDA VÁLIDA`.

**Linhas mudam de status entre execuções.** Uma venda "EM VALIDAÇÃO" pode virar
"NÃO" (foi o que aconteceu com o Mac Campo Belo un. 24 entre 07/09 e 10/09).
Recalcule sempre do zero; nunca reaproveite número de execução anterior.

`realizado` conta só vendas com sinal compensado (coluna *VENDAS VÁLIDAS* > 0);
`projecao` conta o realizado mais tudo que está em validação.

## Conta Corrente de Desconto

`scripts/conta_corrente.py` trata o desconto como **verba**: cada produto começa
com o valor autorizado integral, desconto concedido consome e ágio devolve. Só
quatro produtos têm conta corrente — Autoria MAC (R$ 460.000 / 34 un.), Mac
Brooklin (R$ 840.000 / 6), Mac Vila Clementino (R$ 450.000 / 4) e Mac Vila
Mariana (R$ 330.000 / 4), somando R$ 2.080.000. Ateliê 365, Ibirapuera,
Pinheiros e Campo Belo aparecem só na nota de rodapé; o desconto deles é apurado
por outro modelo e o script nunca inventa verba para eles.

O *ritmo* compara a % da verba consumida com a % das unidades vendidas: em folga,
atenção (até 10 p.p. à frente), acelerado, estouro.

> **O campo `obra` do lançamento tem de vir com o rótulo do site** — `Autoria MAC`,
> `Mac Brooklin`, `Mac Vila Clementino`, `Mac Vila Mariana` —, e não com o nome em
> caixa alta da planilha. Use `motor.nome_produto()` para converter. Com o nome
> errado o script não reclama: ele joga tudo em "produtos de fora" e o consumo sai
> **R$ 0,00**.

**A conferência por unidade roda antes de tudo:** a soma do `DESCONTO PV` das
linhas de cada unidade tem de bater com a aba de conferência. Se não bater, o
rateio por share mudou na planilha — o script sai com erro **sem gravar nada**.
Número de verba não vai para a diretoria sem conferir.

O painel sai sempre criptografado. Sem `STATICRYPT_PASSWORD` o script aborta, em
vez de publicar verba em texto aberto.

## Artes .jpg

`scripts/artes.py` abre as próprias páginas do site num Chromium headless, força
a visão **"Realizado · sinal compensado"**, congela a auto-rotação dos murais e
salva o screenshot — 1080×1080 para os rankings, 1080×607 para os murais. O número
grande da arte é sempre o **realizado**; confira isso antes de entregar.

Se o Playwright não achar o Chromium sozinho, aponte o caminho por variável de
ambiente em vez de editar o script:

```bash
export PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
```

## Rodar na mão

```bash
pip install -r scripts/requirements.txt
export STATICRYPT_PASSWORD='...'

python -m pytest tests/ -q                                              # 1. as regras ainda valem?
python scripts/atualiza.py --json vendas.json                           # 2. rankings, murais e painel
python scripts/atualiza_conta_corrente.py --json lanc.json \
                                          --quadro quadro.json          # 3. conta corrente
python scripts/artes.py                                                 # 4. artes .jpg
```

Os três JSONs são montados a partir da planilha e seguem as dataclasses do
próprio repositório:

| Arquivo | Formato | Campos |
| --- | --- | --- |
| `vendas.json` | `motor.Venda` | `produto` (via `nome_produto`), `unidade`, `corretor` (via `nome_corretor`), `gerente`, `canal`, `vendas`, `vgv`, `valida`, `interna` |
| `lanc.json` | `conta_corrente.Lancamento` | `data`, `obra` (via `nome_produto`), `unidade`, `corretor`, `gerente`, `canal`, `share`, `vgv`, `desconto`, `sinal_compensado` |
| `quadro.json` | quadro por unidade | `obra`, `unidade`, `desconto` |

Em todos eles, as linhas com STATUS `NÃO` ficam **de fora**.

Para as artes é preciso o Chromium do Playwright: `python -m playwright install chromium`.

## Sobre o painel.html

O `painel.html` é criptografado com StatiCrypt. `scripts/staticrypt.py` reproduz
o esquema em Python: descriptografa o payload, troca o bloco `DATA` e
re-criptografa **preservando o mesmo salt** — os "remember me" já salvos nos
navegadores do time continuam valendo. Se `STATICRYPT_PASSWORD` não estiver
definida, o painel é pulado e os outros arquivos são atualizados normalmente.

> **O repositório é público.** O StatiCrypt é criptografia do lado do cliente: a
> senha protege contra quem abre o link por acaso, não contra quem quiser
> trabalhar em cima do arquivo. Não trate o `painel.html` nem o
> `conta-corrente.html` como confidenciais de verdade.

## Quando algo quebrar

| Sintoma | Causa provável |
| --- | --- |
| `CONFERÊNCIA NÃO BATEU` | o rateio por share mudou: a soma do *DESCONTO PV* de uma unidade não bate com o quadro de conferência |
| consumo da conta corrente sai `R$ 0,00` | o campo `obra` dos lançamentos veio em caixa alta, fora do rótulo do site |
| `Senha incorreta: o HMAC do payload não confere` | o `painel.html` foi republicado com outra senha |
| `bloco 'const DATA = {...}' não encontrado` | o HTML foi editado à mão e perdeu o marcador |
| teste do motor falhando | alguma regra de premiação mudou sem atualizar `tests/test_motor.py` |
| site com carimbo velho | o `.zip` não foi publicado, ou subiu fechado em vez dos 10 arquivos |

Nos casos de erro os scripts **abortam sem alterar os HTMLs** — o que está no ar
continua no ar.

## Pontos de atenção

- A meta usada é **R$ 88.516.862 / 73 unidades**, confirmada em 24/08/2026 como a
  oficial. A aba oculta `Simulação 100%` da planilha traz R$ 98.000.000 numa
  célula própria — está descartada. Se a meta mudar, ajuste `META_VGV` em
  `scripts/motor.py` e rode os testes.
- As verbas da conta corrente (R$ 2.080.000 no total) e as unidades de campanha
  estão em `VERBAS`, no topo de `scripts/conta_corrente.py`. Duas pendências
  marcadas como *a confirmar*: as unidades do Mac Vila Mariana (o Documento Mãe
  traz 5, aqui está 4) e a ausência de conta corrente do Mac Campo Belo.
- Nomes de corretor saem da coluna *CORRETOR* (`"CINTIA - CINTIA DE OLIVEIRA ROSA"`
  vira `CINTIA`; razões sociais perdem os sufixos de PJ). Para forçar um apelido
  específico, use o parâmetro `apelidos` de `nome_corretor`.
- Planilha: `1KkpBhKvUL6nxIovp8ukP5ZlnhLzNPW910UifvmzHVXo` — *Campanha Estoque -
  Geral - BP17*, aba **Lista Vendas - Campanha**.
