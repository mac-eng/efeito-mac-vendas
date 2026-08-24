# Automação dos números da campanha Efeito MAC

O site é publicado por GitHub Pages a partir da branch `main`. Os números vivem
num bloco `const DATA = {...}` dentro de cinco arquivos:

| Arquivo | Conteúdo |
| --- | --- |
| `ranking-corretores.html` | Ranking de corretores (Salão/Online) |
| `ranking-gerentes.html` | Ranking de gerentes |
| `mural-corretores.html` | Mural para o telão |
| `mural-gerentes.html` | Mural para o telão |
| `painel.html` | Painel completo — **criptografado com StatiCrypt** |
| `conta-corrente.html` | Conta Corrente de Desconto — **criptografado com StatiCrypt** |

Toda segunda às 09:30 (Brasília), o GitHub Actions lê a planilha
**"Campanha Estoque - Geral - BP17"** no Drive e, numa tacada só: recalcula a
premiação e reescreve os cinco HTMLs de ranking; confere e regera a Conta
Corrente de Desconto; tira o screenshot das quatro artes `.jpg`; e commita tudo
na `main`. O Pages publica sozinho.

**Não há mais push manual.** Nada disso depende de nenhum computador ligado.

## Como as segundas ficaram

| Horário (Brasília) | Quem | O que faz |
| --- | --- | --- |
| 09:30 | GitHub Actions | Publica: números, conta corrente e artes. Commita sozinho. |
| 10:00 | Cowork — *conferir a publicação* | Compara o site com a planilha. Se o robô falhou, te avisa no celular. |
| 10:15 | Cowork — *e-mail de ranking* | Rascunho no Gmail a partir do que está no ar. Não gera arquivo. |
| 10:30 | Cowork — *e-mail de conta corrente* | Rascunho no Gmail para Isaac e Luiz. Não gera arquivo. |

A ordem é deliberada: **publica → confere → comunica**. As duas tarefas de e-mail
checam o carimbo "Atualizado em" antes de escrever; se o robô das 09:30 falhou,
elas não criam rascunho com número velho.

> **Atenção ao seu clone local.** A partir da primeira execução do workflow, o
> robô passa a commitar na `main`. Seu `C:\Git\efeito-mac-vendas` fica atrás do
> origin. Antes de qualquer push seu, rode `git pull` — senão o Git recusa.
> No dia a dia você não precisa mais mexer no repositório.

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
Manual. O workflow roda os testes **antes** de mexer nos HTMLs: se as regras
quebrarem, ele para e não publica número errado.

## Régua de leitura da planilha (desde 24/08/2026)

`scripts/planilha.py` classifica cada linha pela coluna **STATUS**, nesta ordem:

| STATUS | O que acontece |
| --- | --- |
| `NÃO` | descartada — desistência ou vaga extra. Não entra em VGV, unidades, curva, prêmio, listagem nem conta corrente. |
| `EM VALIDAÇÃO` | entra só na `projecao`; fica fora do `realizado` até o sinal compensar. |
| `VENDA OK` | régua completa. |
| `VENDA INTERNA` | entra no `realizado`, mas só no volume (ver abaixo). |

**Venda interna** é a linha com `GERENTE = "VENDA INTERNA"`. Ela soma no VGV, nas
unidades e no % da meta, e paga a Premiação Equipe Comercial (§9) e a verba de
desconto — mas **não** aparece em ranking nenhum e **não** gera prêmio de corretor
ou de gerente. No motor isso é o campo `Venda.interna`.

> **Nunca use a coluna `PERÍODO CAMPANHA` como filtro de campanha.** Ela devolve
> `OK` / `NÃO` sobre a janela de datas, nunca a palavra `CAMPANHA`. Até 24/08/2026
> o leitor filtrava por ela e descartava **100% das linhas** — o robô abortava com
> "Nenhuma venda de campanha encontrada" toda segunda e o site ficou congelado nos
> números de 14/08. A classificação está em `STATUS` e `VENDA VÁLIDA`.

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

**A conferência por unidade roda antes de tudo:** a soma do `DESCONTO PV` das
linhas de cada unidade tem de bater com a aba de conferência. Se não bater, o
rateio por share mudou na planilha — o script sai com erro e o workflow falha
**sem commitar**. Número de verba não vai para a diretoria sem conferir.

O painel sai sempre criptografado. Sem `STATICRYPT_PASSWORD` o script aborta, em
vez de publicar verba em texto aberto.

## Artes .jpg

`scripts/artes.py` abre as próprias páginas do site num Chromium headless, força
a visão **"Realizado · sinal compensado"**, congela a auto-rotação dos murais e
salva o screenshot — 1080×1080 para os rankings, 1080×607 para os murais, iguais aos
arquivos que já estavam publicados. Não há mais arte gerada à mão.

## Configuração (uma vez só)

### 1. Service account do Google

1. No [Google Cloud Console](https://console.cloud.google.com/), crie um projeto
   (ou use um existente) e ative a **Google Sheets API**.
2. Em *IAM e administrador > Contas de serviço*, crie uma conta de serviço —
   sugestão de nome: `efeito-mac-site`.
3. Na conta criada, aba *Chaves*, **Adicionar chave > Criar nova chave > JSON**.
   Baixe o arquivo.
4. Copie o e-mail da conta (algo como
   `efeito-mac-site@<projeto>.iam.gserviceaccount.com`) e **compartilhe a planilha
   com esse e-mail como Leitor**. Sem esse passo o robô não enxerga a planilha.

### 2. Secrets e variáveis no GitHub

Em *Settings > Secrets and variables > Actions* do repositório:

**Secrets** (aba *Secrets*):

| Nome | Valor |
| --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | conteúdo inteiro do arquivo JSON baixado |
| `STATICRYPT_PASSWORD` | senha do `painel.html` |

**Variável** (aba *Variables*):

| Nome | Valor |
| --- | --- |
| `SHEET_ID` | `1KkpBhKvUL6nxIovp8ukP5ZlnhLzNPW910UifvmzHVXo` |

### 3. Permissão de escrita para o Actions

Em *Settings > Actions > General > Workflow permissions*, marque
**Read and write permissions**. É o que autoriza o robô a commitar.

### 4. Primeiro teste

Na aba **Actions > Atualiza números da campanha > Run workflow**. O log mostra o
realizado, a projeção e quais arquivos mudaram.

## Rodar na mão

```bash
pip install -r scripts/requirements.txt

export SHEET_ID=1KkpBhKvUL6nxIovp8ukP5ZlnhLzNPW910UifvmzHVXo
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat caminho/para/credencial.json)"
export STATICRYPT_PASSWORD='...'

python scripts/atualiza.py --dry-run              # mostra o que mudaria, sem gravar
python scripts/atualiza.py                        # números dos rankings e do painel
python scripts/atualiza_conta_corrente.py         # conta corrente
python scripts/artes.py --so-mudadas              # artes .jpg
```

Para as artes é preciso ter o Chromium do Playwright: `python -m playwright
install chromium`.

## Sobre o painel.html

O `painel.html` é criptografado com StatiCrypt. `scripts/staticrypt.py` reproduz
o esquema em Python: descriptografa o payload, troca o bloco `DATA` e
re-criptografa **preservando o mesmo salt** — os "remember me" já salvos nos
navegadores do time continuam valendo. Se `STATICRYPT_PASSWORD` não estiver
definida, o painel é pulado e os outros quatro arquivos são atualizados
normalmente.

## Quando algo quebrar

| Sintoma no log | Causa provável |
| --- | --- |
| `Nenhuma aba com a coluna 'DATA VENDA'` | a estrutura da planilha mudou |
| `Colunas ausentes na planilha` | alguma coluna foi renomeada |
| `Senha incorreta: o HMAC do payload não confere` | o `painel.html` foi republicado com outra senha |
| `Nenhuma venda encontrada depois do filtro de STATUS` | a coluna *STATUS* mudou de valores ou a aba foi zerada |
| `403` / `PERMISSION_DENIED` | a planilha não está compartilhada com a service account |
| `CONFERÊNCIA NÃO BATEU` | o rateio por share mudou: a soma do *DESCONTO PV* de uma unidade não bate com o quadro de conferência |
| `Aba de conferência por unidade não encontrada` | a aba com OBRA / UNIDADE / DESCONTO sumiu ou foi renomeada |

Em todos esses casos o robô **aborta sem alterar o site** — o que está no ar
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
