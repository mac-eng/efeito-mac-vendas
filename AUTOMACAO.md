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

Toda segunda às 09:30 (Brasília), o GitHub Actions lê a planilha
**"Campanha Estoque - Geral - BP17"** no Drive, recalcula a premiação, reescreve
os cinco arquivos e commita na `main`. O Pages publica sozinho. Nada disso
depende de nenhum computador ligado.

Se nenhum número mudou desde a semana anterior, o robô não commita nada.

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

`realizado` conta só vendas com sinal compensado (coluna *VENDAS VÁLIDAS* > 0);
`projecao` conta tudo que foi lançado no período da campanha.

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

python scripts/atualiza.py --dry-run   # mostra o que mudaria, sem gravar
python scripts/atualiza.py             # grava os HTMLs
```

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
| `Nenhuma venda de campanha encontrada` | a coluna *PERÍODO CAMPANHA* está vazia ou a aba foi zerada |
| `403` / `PERMISSION_DENIED` | a planilha não está compartilhada com a service account |

Em todos esses casos o robô **aborta sem alterar o site** — o que está no ar
continua no ar.

## Pontos de atenção

- A meta usada é **R$ 88.516.862 / 73 unidades**, que é a do Manual Operacional e
  a que já estava no site. O quadro resumo da planilha usa R$ 98.000.000 numa
  célula própria — se a meta oficial mudar, ajuste `META_VGV` em
  `scripts/motor.py` e rode os testes.
- As artes `.jpg` (ranking-corretores.jpg etc.) **não** são regeneradas pelo robô;
  continuam sendo produzidas à parte.
- Nomes de corretor saem da coluna *CORRETOR* (`"CINTIA - CINTIA DE OLIVEIRA ROSA"`
  vira `CINTIA`; razões sociais perdem os sufixos de PJ). Para forçar um apelido
  específico, use o parâmetro `apelidos` de `nome_corretor`.
