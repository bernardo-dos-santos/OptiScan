# OptiScan

Controle de estoque via WhatsApp com leitura automática de etiquetas e notas fiscais por IA.

O usuário manda uma foto da etiqueta do produto ou o PDF da NF-e no WhatsApp, e o sistema extrai os dados, atualiza o saldo no banco e reflete tudo numa planilha do Google Sheets. Também aceita comandos de texto para operações manuais.

> ⚠️ **Projeto arquivado.** Não está em produção nem recebe manutenção. O código fica aqui como registro.

## O que faz

- **Foto de etiqueta** → Gemini extrai referência, nome, especificação e quantidade. Legendas como "30 fardos" são multiplicadas pela quantidade unitária lida na imagem.
- **PDF de nota fiscal** → cruza o CNPJ do cliente com emitente/destinatário para decidir se é ENTRADA ou SAÍDA, extrai os itens e calcula custo unitário (tratando unidades em milheiro).
- **Comandos de texto** — `entrada <produto> <qtd>`, `saida <produto> <qtd>`, `estoque`, `financeiro`, `corrigir` (estorna a última operação), `ajuda`.
- **Comandos admin** — `!cadastrar`, `!add`, `!lista`, `!status`, restritos ao número do administrador.
- **Sincronização bidirecional com Google Sheets** — a planilha recebe os saldos e, via Apps Script, envia edições de volta pelos webhooks `/webhook_planilha`, `/webhook_sincronizacao_geral` e `/webhook_excluir`.
- **Rotinas agendadas** (APScheduler, fuso `America/Sao_Paulo`):
  - 18h diariamente: resumo dos itens abaixo do estoque mínimo.
  - Segundas às 9h: análise preditiva dos últimos 30 dias sugerindo novo estoque mínimo (só notifica se a variação passar de 10%).
- **Multi-tenant** — cada cliente tem sua planilha, seus números autorizados e um contexto de IA próprio para calibrar a leitura das etiquetas.

## Stack

- Python + Flask (webhook da WhatsApp Cloud API)
- Google Gemini (`gemini-2.5-flash`) para visão e extração estruturada
- PostgreSQL (Supabase) via `psycopg2`
- Google Sheets via `gspread`
- APScheduler para as tarefas de fundo
- Gunicorn para deploy

## Estrutura

```
app.py                  # Flask, rotas de webhook e scheduler
setup_nuvem.py          # cria as tabelas no Postgres
handlers/
  messages.py           # comandos de texto (cliente e admin)
  images.py             # fluxo de imagem e de PDF
services/
  meta.py               # envio/recebimento WhatsApp + validação de assinatura
  leitor.py             # prompts do Gemini para imagem e NF
  banco.py              # persistência, estorno, relatório financeiro
  sheets.py             # leitura/escrita na planilha
  analista.py           # análise preditiva de estoque mínimo
  uteis.py              # formatação numérica pt-BR
```

## Rodando localmente

```bash
pip install -r requirements.txt
python setup_nuvem.py   # cria/atualiza as tabelas (idempotente)
python app.py
```

### Testes

```bash
pip install -r requirements-dev.txt
pytest
```

Cobrem a validação da assinatura da Meta (`services/meta.py`) e a formatação/conversão de números pt-BR (`services/uteis.py`).

Variáveis de ambiente (`.env`):

```
WEBHOOK_VERIFY_TOKEN=
META_ACCESS_TOKEN=
META_PHONE_ID=
META_APP_SECRET=
ADMIN_NUMBER=
GEMINI_API_KEY=
DB_HOST=
DB_NAME=
DB_USER=
DB_PASS=
DB_PORT=5432
# Somente em desenvolvimento local, para aceitar webhooks sem assinatura:
# ALLOW_UNSIGNED_WEBHOOKS=true
```

Além disso, é preciso um `chave_nova.json` na raiz com as credenciais da service account do Google (Sheets + Drive), e a planilha compartilhada com o e-mail dessa conta.

## Limitações conhecidas

- Os testes cobrem só as funções puras (assinatura da Meta e formatação de números). Banco, Sheets e Gemini não têm testes (dependem de serviços externos).
- O schema da planilha é posicional (colunas A–I fixas).
- Sem migrações versionadas: `setup_nuvem.py` aplica `CREATE/ALTER ... IF NOT EXISTS`, o que serve para este tamanho de projeto, mas não substitui uma ferramenta de migração.
