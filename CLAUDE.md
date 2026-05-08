# CLAUDE.md — EduBot

> **Para quem é este arquivo:** o Claude Code lê este `CLAUDE.md` automaticamente ao iniciar qualquer sessão dentro do repo. Este documento é a **fonte da verdade técnica** sobre o EduBot — código, schema, endpoints, débito técnico, comandos.
>
> **Para tese estratégica, modelo de negócio, posicionamento e proposta de valor**, consulte `edubot_briefing.md` no Project do Claude (chat). Os dois documentos são complementares e devem ser mantidos sincronizados quando houver mudança relevante.

---

## 1. Visão geral do projeto

EduBot é uma **plataforma de inteligência pedagógica via WhatsApp** para universidades brasileiras, com três camadas de valor empilhadas:

1. **Camada 1 — Aluno:** organização (parsing de programa, lembretes) + tutoria via IA
2. **Camada 2 — Professor:** feedback em tempo real sobre dúvidas e gaps da turma
3. **Camada 3 — Instituição:** dashboard pedagógico + avaliação docente data-driven + IA proprietária educacional substituindo ChatGPT Enterprise

Modelo comercial é **B2B institucional** (não B2B2C). Para detalhes estratégicos, ver `edubot_briefing.md` no chat.

**Estado de implementação:** Camada 1 com código completo e auditado — pendente credenciais Meta e commit/deploy. Camadas 2 e 3 ainda não existem em código.

---

## 2. Sobre o desenvolvedor

- **Nome:** Leonardo (Leo) Passarelli, 22 anos
- **Formação:** Finanças no Insper (5º de 8 semestres), intercâmbio prévio no Babson College
- **Nível técnico:** Sem experiência prévia com desenvolvimento. Constrói o EduBot com ajuda de IA (Cursor + Claude no chat + Claude Code)
- **Idioma:** Português brasileiro. Toda comunicação em PT-BR
- **Estilo de trabalho:** Prefere explicações acessíveis (termos técnicos devem ser explicados brevemente), guidance passo-a-passo com confirmação entre etapas, e nunca despejos grandes de código sem contexto. Costuma confirmar verbalmente em vez de colar saídas reais — sempre peça a saída bruta do terminal antes de avançar em mudanças críticas.

---

## 3. Stack técnico

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Linguagem | Python | 3.12 |
| Framework web | FastAPI | 0.115.0 |
| Servidor | Uvicorn | 0.30.0 |
| Banco de dados | PostgreSQL | 16 (via Docker) |
| ORM | SQLAlchemy (async) | 2.0.35 |
| Driver DB | asyncpg | 0.29.0 |
| Migrações DB | Alembic | 1.13.0 (instalado, NÃO configurado) |
| IA / Parser | Claude Haiku 4.5 | via API HTTP (httpx) |
| HTTP Client | httpx | 0.27.0 |
| Validação | Pydantic | 2.9.0 |
| Fila de tarefas | Celery + Redis | 5.4.0 / 5.1.0 (instalado, NÃO implementado) |
| Deploy | Railway (Nixpacks) | edubot-production-073e.up.railway.app |
| Containers (dev) | Docker Compose | PostgreSQL 16 + Redis 7 |

---

## 4. Arquitetura e estrutura de pastas

```
edubot/
├── app/
│   ├── main.py              # FastAPI app — lifespan, CORS, rotas, guards de prod
│   ├── auth.py              # verify_api_key (Frente 2 — API key auth)
│   ├── models/
│   │   ├── database.py      # Modelos SQLAlchemy (6 tabelas)
│   │   └── connection.py    # Engine async + session factory
│   ├── routers/
│   │   ├── parser.py        # POST /api/v1/parser/{texto,pdf,imagem} — protegido
│   │   ├── alunos.py        # CRUD alunos + matérias + eventos — protegido
│   │   └── webhook.py       # GET+POST /webhook (WhatsApp) — público (HMAC)
│   └── services/
│       ├── parser.py        # ParserEngine — chama Claude API
│       ├── whatsapp.py      # Envio de mensagens + download de mídia (Meta API)
│       └── onboarding.py    # Máquina de estados do onboarding do aluno
├── sql/
│   └── schema.sql           # Schema PostgreSQL completo
├── docker-compose.yml       # PostgreSQL + Redis local
├── requirements.txt
├── Procfile                 # Deploy command
├── nixpacks.toml            # Config Railway
├── runtime.txt              # Python 3.12
└── .env.example             # Template de variáveis de ambiente
```

---

## 5. Fluxo: mensagem WhatsApp → resposta

1. Aluno envia mensagem no WhatsApp
2. Meta faz POST para `/webhook` no servidor
3. `webhook.py` valida assinatura HMAC (Frente 1)
4. `_extrair_mensagem(payload)` extrai `{telefone, tipo, conteudo}` do payload
5. **`onboarding.processar_mensagem(...)`** roteia pelo estado atual do aluno:
   - `NOVO` → boas-vindas + pede nome
   - `AGUARDANDO_NOME` → salva nome, pede PDF
   - `AGUARDANDO_PLANO` → recebe PDF, baixa via `whatsapp.baixar_midia()`, parseia com `ParserEngine`, mostra resumo
   - `AGUARDANDO_CONFIRMACAO_PLANO` → SIM salva no banco; NÃO descarta e pede outro PDF
   - `AGUARDANDO_MAIS_MATERIAS` → SIM volta a pedir PDF; NÃO finaliza onboarding
   - `ATIVO` → onboarding completo (notificações automáticas ainda não implementadas)
6. **`whatsapp.enviar_mensagem_texto(telefone, resposta)`** envia a resposta de volta
7. Webhook retorna 200 ao Meta (sempre — para evitar reenvio)

Estado do onboarding é persistido em `ConversaSessao.contexto` (JSON). Plano parseado fica em `contexto.plano_pendente` até confirmação.

---

## 6. Banco de dados — 6 tabelas

| Tabela | Propósito |
|---|---|
| `instituicao` | Faculdade/universidade cliente (B2B) |
| `aluno` | Usuário final (identificado pelo telefone WhatsApp). Campo `onboarding_completo` controla fluxo |
| `materia` | Disciplina vinculada ao aluno |
| `evento_academico` | Cada item do cronograma (prova, quiz, entrega, etc.) |
| `notificacao_log` | Registro de mensagens enviadas |
| `conversa_sessao` | Contexto de conversa para onboarding e chat. Campo `contexto` (JSON) guarda estado da máquina de estados |

Schema completo em `sql/schema.sql`. Modelos SQLAlchemy em `app/models/database.py`.

---

## 7. Endpoints da API

| Método | Rota | Proteção | Status |
|--------|------|----------|--------|
| POST | `/api/v1/parser/texto` | X-API-Key | ✅ Funcional |
| POST | `/api/v1/parser/pdf` | X-API-Key | ✅ Funcional |
| POST | `/api/v1/parser/imagem` | X-API-Key | ✅ Funcional |
| POST | `/api/v1/alunos` | X-API-Key | ✅ Funcional |
| POST | `/api/v1/alunos/{id}/materias` | X-API-Key | ✅ Funcional |
| GET | `/api/v1/alunos/{id}/proximos-eventos` | X-API-Key | ✅ Funcional |
| GET | `/api/v1/alunos/{id}/eventos-hoje` | X-API-Key | ⚠️ Funcional, mas retorna 500 quando aluno não existe (deveria ser 404) |
| GET | `/webhook` | verify_token (Meta) | ✅ Funcional |
| POST | `/webhook` | HMAC (Meta) | ⚠️ **Código completo e smoke-testado — uncommitted** |
| GET | `/health` | público | ✅ Funcional |

---

## 8. Estado atual (atualizar ao fim de cada sessão)

**Última atualização:** 07/05/2026 (auditoria + hardening + smoke test via chat)

### ✅ Pronto e em produção

- Backend FastAPI no Railway, rodando em `ENVIRONMENT=production`
- Parser de texto/PDF/imagem (Claude Haiku 4.5) com endpoints REST autenticados
- Schema completo das 6 tabelas
- CRUD de alunos, matérias, eventos
- Webhook GET (verify_token) configurado e subscrito ao evento `messages` no painel Meta
- **Frente 1 ativa:** validação HMAC obrigatória em produção (`WA_APP_SECRET` configurado, commit `c995f81`)
- **Frente 2 ativa:** API key auth em endpoints internos (`INTERNAL_API_KEY`, commit `fb0403c`)
- Landing page (Gamma)

### ✅ Implementado e smoke-testado localmente (não deployado)

- **`app/services/whatsapp.py`** (criado 19/abr/2026) — `enviar_mensagem_texto()` e `baixar_midia()`. Lê `WA_ACCESS_TOKEN` e `WA_PHONE_NUMBER_ID`. Tratamento de erro distingue token expirado (code 190), número não autorizado (131030), rate limit (429), timeout
- **`app/services/onboarding.py`** (criado 19/abr/2026) — máquina de estados com 6 estados, reconhecimento generoso de SIM/NÃO, persistência em `ConversaSessao.contexto`, integração com parser e banco
- **Smoke test local (07/05/2026):** transições NOVO → AGUARDANDO_NOME → AGUARDANDO_PLANO validadas com curl + psql. Webhook retorna 200 mesmo quando envio downstream falha (correto por design)

### ⚠️ Código completo — 4 arquivos uncommitted

Auditoria de 07/05/2026 confirmou que o código está completo e coerente fim-a-fim. O briefing anterior chamava de "integração pela metade" — na verdade era código pronto, só não commitado.

Arquivos pendentes de commit:
- **`app/main.py`** — adicionado warning não-fatal no lifespan: em production, avisa se `WA_ACCESS_TOKEN` ou `WA_PHONE_NUMBER_ID` faltarem (não crasha, apenas log warning)
- **`app/routers/webhook.py`** — integração completa com onboarding: `_extrair_mensagem()`, chamada a `onboarding.processar_mensagem()`, envio de resposta via `whatsapp.enviar_mensagem_texto()`. Backup antigo em `webhook.py.backup-antes-onboarding`
- **`app/services/whatsapp.py`** — novo arquivo (19/abr/2026), envio e download de mídia via Meta API
- **`app/services/onboarding.py`** — novo arquivo (19/abr/2026), máquina de estados com 6 estados. Consolidação cosmética aplicada em 07/05: duas chamadas seguidas de `_atualizar_contexto` em `_handler_aguardando_confirmacao` unificadas em uma só

### ❌ Bloqueadores para teste fim-a-fim

- **`WA_ACCESS_TOKEN` retornando 401 do Meta** — token recém-rotacionado (07/05/2026) não está funcionando. Hipóteses: paste cortado, char invisível, token pertence a app diferente. Investigar antes de deploy
- Token permanente via System User no Business Manager ainda não gerado — tokens temporários de 24h não servem para produção
- `WA_PHONE_NUMBER_ID` precisa ser confirmado no Railway
- 4 arquivos com mudanças não commitadas — deploy traz versão antiga
- Número pessoal do Leo precisa ser registrado como test recipient no painel Meta (modo dev bloqueia envio para números não autorizados — code 131030)

### ⚠️ Incidente operacional — 07/05/2026

- Credenciais coladas no chat (Anthropic API key, Internal API key, WA Access Token). Todas rotacionadas no mesmo dia
- Aproveitada rotação para limpar duplicação de `INTERNAL_API_KEY` no `.env` local

### ❌ Camadas 2 e 3 — não existem em código

- Tutoria conversacional (responder dúvidas de matéria — diferente de comandos de organização)
- Sistema de captura/categorização de dúvidas para análise pedagógica
- Consentimento LGPD explícito no onboarding (bloqueante para Camadas 2/3)
- Dashboard de professor
- Dashboard institucional

---

## 9. Próximos passos (ordem)

### Sessão imediata — fechar Camada 1 fim-a-fim

~~1. Revisar e completar `webhook.py`~~ ✅ Auditado em 07/05 — código completo
~~2. Testar localmente com payload simulado~~ ✅ Smoke test passou em 07/05
3. **Debug 401 do Meta** — descobrir por que o `WA_ACCESS_TOKEN` rotacionado está sendo rejeitado
4. Commit dos 4 arquivos pendentes (`main.py`, `webhook.py`, `whatsapp.py`, `onboarding.py`)
5. Deploy no Railway + configurar `WA_ACCESS_TOKEN` e `WA_PHONE_NUMBER_ID` no Railway
6. Gerar **`WA_ACCESS_TOKEN` permanente** via System User no Business Manager
7. Registrar número pessoal do Leo como test recipient no painel Meta
8. Teste fim-a-fim: mandar mensagem real do WhatsApp → validar fluxo NOVO → ATIVO
9. Validar fluxo em produção

### Curto prazo — completar Camada 1

- Notificações agendadas (Celery + Redis): lembretes diários e semanais de eventos
- Texto de consentimento LGPD no onboarding (preparando Camadas 2/3)
- Frente 3 — Rate limiting (`slowapi`): risco financeiro real (custo Anthropic se alguém abusar do parser)
- Frente 4 — CORS restrito (lista explícita de origens em prod)
- eSIM dedicado para o número oficial (em andamento — Vivo)

### Médio prazo — destravar Camada 2

- Diferenciar tipos de mensagem do aluno: comando vs. dúvida acadêmica
- Estrutura de armazenamento de dúvidas (tema, conceito, timestamp, turma, professor)
- Algoritmo de agrupamento/categorização de dúvidas

### Longo prazo — Camada 3 (a venda real)

- Dashboard institucional (frontend React separado, consumindo API)
- Métricas pedagógicas agregadas (curva de dúvidas por professor, gaps por matéria, comparativo entre turmas)
- Demo Insper como prova de conceito (substituição do ChatGPT institucional)

---

## 10. Frentes de segurança

### Concluídas

#### Frente 1 — HMAC + verify_token do webhook (ativa em prod desde 18/abr/2026)

- **Código:** `routers/webhook.py` (validação HMAC do POST + verify_token do GET)
- **Variável obrigatória em prod:** `WA_APP_SECRET` (vem do painel Meta)
- **Comportamento:** em produção, se `WA_APP_SECRET` estiver vazio, o app crasha no startup. Em dev, apenas warning.
- **Histórico:** código commitado em `c995f81` (semanas antes), mas só ativou em prod após `ENVIRONMENT=production` ser setado no Railway em 18/abr/2026.

#### Frente 2 — API key auth para endpoints internos (ativa em prod desde 18/abr/2026)

- **Código:** `app/auth.py` (função `verify_api_key`), aplicado via `Depends` em `routers/parser.py` e `routers/alunos.py`
- **Variável obrigatória em prod:** `INTERNAL_API_KEY`. Gerar com: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- **Header esperado:** `X-API-Key: <chave>`
- **Comportamento:** 401 sem chave/chave errada. Usa `secrets.compare_digest` (anti timing-attack). Em prod, se `INTERNAL_API_KEY` vazia, app crasha no startup.
- **Importante:** chaves DIFERENTES entre dev e prod. Vazamento de dev não compromete prod.
- **Commit:** `fb0403c`

### Pendentes

- **Frente 3 — Rate limiting** (`slowapi`). Risco principal: explosão de custo na API Anthropic se alguém abusar do parser, mesmo com API key.
- **Frente 4 — CORS restrito.** Hoje é `os.getenv("CORS_ORIGINS", "*")`. Em prod, deve ser lista explícita.

---

## 11. Débito técnico conhecido

### Bugs e code smells

- `services/parser.py:105`: atribuição duplicada `self.client = self.client = httpx.AsyncClient(...)` — funciona mas é cheiro de copy-paste
- `requirements.txt:24-25`: `python-dotenv` listado duas vezes
- Parser usa `httpx` direto em vez do SDK oficial `anthropic` — menos robusto (sem retries automáticos, sem tratamento de rate limit nativo)
- Código de limpeza de JSON duplicado nos 3 métodos do parser (texto, PDF, imagem)
- Endpoint `GET /api/v1/alunos/{id}/eventos-hoje` retorna 500 quando aluno não existe (deveria ser 404)
- `webhook.py.backup-antes-onboarding` precisa ser removido após commit do novo webhook

### Falta de infraestrutura

- Sem testes automatizados (nem unit, nem integração, nem e2e)
- Sem CI (lint, test, type-check antes do deploy)
- Sem observabilidade (Sentry, APM, logs estruturados)
- Sem rollback documentado

---

## 12. Variáveis de ambiente necessárias

Ver `.env.example` para o template completo.

### Obrigatórias em produção (app crasha sem elas)

- `ENVIRONMENT=production`
- `WA_APP_SECRET` — Secret do app Meta (Frente 1)
- `INTERNAL_API_KEY` — Frente 2. Use chaves diferentes entre dev e prod.
- `ANTHROPIC_API_KEY` — sem ela, parser não funciona
- `DATABASE_URL` — PostgreSQL

### Necessárias para WhatsApp funcionar (warning no startup em prod, não-fatal)

- `WA_VERIFY_TOKEN` — token de verificação do webhook (string inventada por você, deve bater com painel Meta)
- `WA_PHONE_NUMBER_ID` — ID do número WhatsApp Business
- `WA_ACCESS_TOKEN` — **token permanente** via System User do Business Manager. Token temporário de 24h não é adequado para produção.

### Pendentes (planos futuros)

- `REDIS_URL` (Celery não implementado)
- `CORS_ORIGINS` (Frente 4 pendente; hoje fallback `"*"`)
- `PARSER_MODEL` (default: `claude-haiku-4-5-20251001`)

---

## 13. Comandos úteis

```bash
# --- Desenvolvimento local ---

# Subir banco + Redis
docker compose up -d

# Ativar venv
source venv/bin/activate

# Rodar a API localmente
uvicorn app.main:app --reload --port 8001

# Docs interativos (Swagger)
# http://localhost:8001/docs

# Health check
curl http://localhost:8001/health

# Testar parser de texto (com API key local)
DEVKEY=$(grep "^INTERNAL_API_KEY=" .env | cut -d= -f2)
curl -X POST http://localhost:8001/api/v1/parser/texto \
  -H "X-API-Key: $DEVKEY" \
  -H "Content-Type: application/json" \
  -d '{"texto": "Finanças III\nAula 1 - 10/02\nProva - 24/02 peso 30%"}'

# --- Auditoria de estado ---

# Estado do git
git status
git log --oneline -10

# O que está uncommitted
git diff app/routers/webhook.py

# --- Produção (Railway) ---
# URL: https://edubot-production-073e.up.railway.app
# Deploy: push para main (Railway faz deploy automático)
# NUNCA fazer push para main sem confirmação do Leonardo
```

---

## 14. Regras de engajamento (inegociável)

1. **Antes de planejar**, peça o estado atual do repo (estrutura, conteúdo dos arquivos relevantes). Não assuma — verifique.
2. **Apresente o plano completo** (funções, dependências, env vars, endpoints) antes de escrever código.
3. **Mostre diff completo** de cada arquivo antes de qualquer edição. Nunca substitua diff por resumo.
4. **Aguarde aprovação explícita** antes de qualquer escrita, commit ou deploy.
5. **Testes locais antes de qualquer push.** Nada vai pro Railway sem aprovação explícita.
6. **Em passos críticos**, peça output bruto do terminal — não aceite "tudo certo" verbal. Atenção a artefatos `[200~` (bracketed paste mode).
7. **Explica o "porquê" antes do "como"** — Leo precisa entender a motivação antes de ver código.
8. **Mudanças grandes em passos pequenos** — divide em etapas e confirma cada uma.
9. **Alerta proativo** — se o pedido tem problema (técnico, segurança, negócio, estratégico), alerta com clareza ANTES de executar.
10. **Linguagem acessível** — termos técnicos devem ser explicados brevemente.
11. **Mostra como testar** — sempre indica como validar uma mudança.
12. **Git com permissão** — sugere mensagem de commit mas NUNCA commita sem confirmação explícita.
13. **Deploy manual** — NUNCA faz deploy sozinho.
14. **Idioma** — toda comunicação em PT-BR.

---

## 15. Histórico de mudanças importantes

### 07/05/2026 — Auditoria completa + hardening + smoke test
- Auditoria dos 4 arquivos core (`webhook.py`, `whatsapp.py`, `onboarding.py`, `main.py`): código confirmado completo e coerente fim-a-fim
- Hardening em `main.py`: warning não-fatal no lifespan se credenciais WhatsApp faltarem em produção
- Consolidação cosmética em `onboarding.py`: duas chamadas `_atualizar_contexto` → uma só
- Smoke test local: transições NOVO → AGUARDANDO_NOME → AGUARDANDO_PLANO validadas via curl + psql
- Descoberta arqueológica: banco local tinha registro de 19/abr do número do Leo no estado AGUARDANDO_NOME — mensagem real chegou em prod, máquina rodou, só envio falhou (confirma que gap era credenciais, não código)
- Incidente: credenciais vazadas no chat, todas rotacionadas no mesmo dia
- Bloqueio identificado: `WA_ACCESS_TOKEN` rotacionado retorna 401 — investigar antes de deploy

### 04/05/2026 — Auditoria do repo via chat
- Confirmado que `whatsapp.py` e `onboarding.py` foram criados em 19/abr/2026 (untracked, ainda não commitados)
- Confirmado que `webhook.py` está modificado mas não commitado, em meio à integração com onboarding
- Atualização da tese de produto: B2B institucional com 3 camadas (ver `edubot_briefing.md`)
- Decisão estratégica: priorizar finalização da Camada 1 antes de Camadas 2/3
- Conversa inicial com pessoa do Insper rendeu pedido de proposta — deck Gamma será produzido no chat

### 18/abr/2026 — Frentes 1 e 2 ativas em produção
- Frente 2 implementada e deployada (commit `fb0403c`)
- Frente 1 ativada de verdade após `ENVIRONMENT=production` ser setado no Railway
- Webhook WhatsApp configurado pela primeira vez no painel Meta (callback URL, verify_token, subscrição a `messages`)
- Confirmado que o bot nunca havia respondido — código de envio inexistente até então
