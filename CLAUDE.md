# CLAUDE.md — EduBot

## 1. Visão geral do projeto

EduBot é um copiloto acadêmico via WhatsApp para estudantes universitários brasileiros. O aluno envia seu plano de aula (texto colado, PDF ou foto) pelo WhatsApp, o sistema usa Claude Haiku 4.5 para extrair automaticamente todas as datas e atividades (provas, quizzes, entregas, etc.), e passa a enviar notificações diárias e semanais para manter o aluno organizado. Modelo B2B — o cliente é a instituição de ensino.

## 2. Sobre o desenvolvedor

- **Nome:** Leonardo (Leo) Passarelli, 22 anos
- **Formação:** Finanças no Insper (5º de 8 semestres), intercâmbio prévio no Babson College
- **Nível técnico:** Sem experiência prévia com desenvolvimento. Construiu o EduBot com ajuda de IA (Cursor + Claude)
- **Idioma:** Português brasileiro. Toda comunicação deve ser em PT-BR
- **Estilo de trabalho:** Prefere explicações acessíveis (termos técnicos devem ser explicados brevemente), guidance passo-a-passo com confirmação entre etapas, e nunca despejos grandes de código sem contexto. Costuma confirmar verbalmente em vez de colar saídas reais — sempre peça a saída bruta do terminal antes de avançar em mudanças críticas.

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

## 4. Arquitetura e fluxo principal

### Estrutura de pastas

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
│       └── parser.py        # ParserEngine — chama Claude API
├── sql/
│   └── schema.sql           # Schema PostgreSQL completo
├── docker-compose.yml       # PostgreSQL + Redis local
├── requirements.txt
├── Procfile                 # Deploy command
├── nixpacks.toml            # Config Railway
├── runtime.txt              # Python 3.12
└── .env.example             # Template de variáveis de ambiente
```

### Fluxo: mensagem WhatsApp → resposta

1. Aluno envia mensagem no WhatsApp
2. Meta faz POST para `/webhook` no servidor
3. `webhook.py` valida assinatura HMAC (Frente 1), identifica tipo (texto/PDF/imagem)
4. Texto longo (>200 chars) → `ParserEngine.parsear_texto()`
5. ParserEngine envia para Claude API com prompt especializado
6. Claude retorna JSON estruturado (matéria, eventos, datas)
7. Sistema gera resumo de confirmação formatado para WhatsApp
8. **[NÃO IMPLEMENTADO]** Envia resumo de volta ao aluno (código de envio inexistente)
9. **[NÃO IMPLEMENTADO]** Aluno confirma → salva no banco
10. **[NÃO IMPLEMENTADO]** Celery envia notificações diárias/semanais

### Banco de dados — 6 tabelas

- `instituicao` — faculdade/universidade cliente (B2B)
- `aluno` — usuário final (identificado pelo telefone WhatsApp)
- `materia` — disciplina vinculada ao aluno
- `evento_academico` — cada item do cronograma (prova, quiz, etc.)
- `notificacao_log` — registro de mensagens enviadas
- `conversa_sessao` — contexto de conversa para chat interativo

### Endpoints da API

| Método | Rota | Proteção | Status |
|--------|------|----------|--------|
| POST | `/api/v1/parser/texto` | X-API-Key | Funcional |
| POST | `/api/v1/parser/pdf` | X-API-Key | Funcional |
| POST | `/api/v1/parser/imagem` | X-API-Key | Funcional |
| POST | `/api/v1/alunos` | X-API-Key | Funcional |
| POST | `/api/v1/alunos/{id}/materias` | X-API-Key | Funcional |
| GET | `/api/v1/alunos/{id}/proximos-eventos` | X-API-Key | Funcional |
| GET | `/api/v1/alunos/{id}/eventos-hoje` | X-API-Key | Funcional |
| GET | `/webhook` | verify_token (Meta) | Funcional |
| POST | `/webhook` | HMAC (Meta) | Recebe mas não responde |
| GET | `/health` | público | Funcional |

## 5. Status atual

### Funciona

- Parser de texto, PDF e imagem via endpoints da API REST (autenticados)
- CRUD de alunos (criar/buscar por telefone)
- Adicionar matéria com eventos parseados
- Consulta de próximos eventos e eventos de hoje
- Verificação do webhook do WhatsApp (GET) com verify_token
- Validação HMAC obrigatória em produção (Frente 1)
- Autenticação por API key em endpoints internos (Frente 2)
- Recepção de POST do webhook (após HMAC ok) — identifica tipo, parseia texto longo
- Schema do banco completo com índices, views e triggers
- Deploy no Railway rodando em `ENVIRONMENT=production`
- Webhook configurado e subscrito ao evento `messages` no painel do Meta (desde 18/abr/2026)

### Incompleto — TODOs no webhook.py

- **CRÍTICO**: Enviar mensagens de volta ao aluno via WhatsApp API (código de envio nunca foi escrito; sem isso, o bot não responde nada)
- Fluxo de onboarding (boas-vindas, criar aluno)
- Salvar eventos após confirmação do aluno
- Processar PDF e imagem recebidos pelo WhatsApp (baixar via Media API)
- Chat interativo (processar perguntas, buscar contexto)
- Armazenamento temporário no Redis (resultado do parser pré-confirmação)

### Ausente

- Função/serviço de **envio** de mensagens WhatsApp (não existe `WA_ACCESS_TOKEN` sendo lido em lugar nenhum do código)
- Sistema de notificações (Celery workers/tasks não existem)
- Alembic não configurado (sem pasta alembic/ nem alembic.ini)
- Zero testes automatizados
- Compliance LGPD no código (consentimento, direito ao esquecimento)
- Rate limiting (Frente 3 — slowapi pendente)
- CORS restrito (Frente 4 — hoje é `"*"` por fallback)

## 6. Frentes de segurança

### Concluídas

#### Frente 1 — HMAC + verify_token do webhook (ativa em prod desde 18/abr/2026)

- **Código**: `routers/webhook.py` (validação HMAC do POST + verify_token do GET)
- **Variável obrigatória em prod**: `WA_APP_SECRET` (vem do painel Meta)
- **Comportamento**: em produção, se `WA_APP_SECRET` estiver vazio, o app crasha no startup (`RuntimeError`). Em dev, apenas warning.
- **Histórico**: o código foi commitado em `c995f81` (semanas antes de 18/abr/2026), mas o guard só efetivamente disparava em `ENVIRONMENT=production`. Como `ENVIRONMENT` não estava setado no Railway, o app rodava em modo dev mesmo em prod, e a validação HMAC era pulada silenciosamente. Corrigido em 18/abr/2026 ao adicionar `ENVIRONMENT=production` e `WA_APP_SECRET` ao Railway.

#### Frente 2 — API key auth para endpoints internos (ativa em prod desde 18/abr/2026)

- **Código**: `app/auth.py` (função `verify_api_key`), aplicado via `Depends` em `routers/parser.py` e `routers/alunos.py` no nível do router
- **Variável obrigatória em prod**: `INTERNAL_API_KEY` (gere com `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`)
- **Header esperado**: `X-API-Key: <chave>`
- **Comportamento**: 401 sem chave / chave errada; passa adiante se chave correta. Usa `secrets.compare_digest` (anti timing-attack). Em produção, se `INTERNAL_API_KEY` estiver vazia, o app crasha no startup.
- **Importante**: chaves devem ser DIFERENTES entre dev e prod. Vazamento da chave dev não compromete prod.
- **Commit**: `fb0403c`

### Pendentes

- **Frente 3 — Rate limiting**: usar `slowapi`. Risco principal: explosão de custo na API Anthropic se alguém abusar do parser, mesmo com API key.
- **Frente 4 — CORS restrito**: hoje é `os.getenv("CORS_ORIGINS", "*")`. Em prod, deve ser lista explícita de origens permitidas.

## 7. Débito técnico conhecido

### Bugs e code smells

- `services/parser.py:105`: atribuição duplicada `self.client = self.client = httpx.AsyncClient(...)` — funciona mas é cheiro de copy-paste
- `requirements.txt:24-25`: `python-dotenv` listado duas vezes
- Parser usa `httpx` direto em vez do SDK oficial `anthropic` — menos robusto (sem retries automáticos, sem tratamento de rate limit nativo)
- Código de limpeza de JSON duplicado nos 3 métodos do parser (texto, PDF, imagem)
- Endpoint `GET /api/v1/alunos/{id}/eventos-hoje` retorna **500** quando aluno não existe (deveria ser 404). Não tratado.
- `.env.backup-frente2` ficou untracked no repo após Frente 2 — confirmar que `.gitignore` cobre `.env*` (não só `.env` exato)

### Falta de infraestrutura

- Sem testes automatizados (nem unit, nem integração, nem e2e)
- Sem CI (lint, test, type-check antes do deploy)
- Sem observabilidade (sem Sentry, sem APM, sem logs estruturados além do `logging.basicConfig` padrão)
- Sem rollback documentado (Railway tem botão "Rollback" mas não há runbook)

## 8. Prioridades atuais (em ordem)

1. **Implementar envio de mensagens via WhatsApp** — sem isso, o bot literalmente não responde aluno. Envolve: gerar `WA_ACCESS_TOKEN` (temporário 24h ou permanente via System User), adicionar `WA_ACCESS_TOKEN` no Railway, criar `app/services/whatsapp.py` com função `enviar_mensagem(phone, texto)`, integrar no handler `POST /webhook`, decidir lógica de produto (o que responder).
2. **Frentes 3 e 4 de segurança** — rate limiting e CORS restrito. Frente 3 é especialmente urgente pelo risco financeiro (custo Anthropic).
3. **Adicionar seu número como recipient de teste no Meta** — necessário pra o bot conseguir enviar mensagem em modo "Em desenvolvimento". Sem isso, mesmo com código pronto, Meta bloqueia o envio.
4. **Notificações agendadas** — Celery workers para lembretes diários e semanais.
5. **Compliance LGPD** — logs de consentimento, direito ao esquecimento, política de privacidade.
6. **Futuro**: app React Native como interface complementar.

## 9. Modelo de negócio

- **Produto:** Copiloto acadêmico via WhatsApp para universitários brasileiros
- **Modelo:** B2B — vendido para departamentos acadêmicos de universidades
- **Preço:** R$ 69,90 por aluno por semestre
- **Meta 5 anos:** 1.000 a 50.000 alunos pagantes
- **Status:** Pré-lançamento. Nenhuma universidade cliente ainda
- **Equipe:** Leonardo sozinho (produto + negócio + dev com IA). Sem cofundador técnico

## 10. Restrições legais

- **LGPD:** Pré-lançamento exige conformidade total (dados de alunos brasileiros menores ou maiores de idade)
- **Trademark:** Nome "EduBot" precisa ser verificado/registrado
- **Termos de uso + Política de privacidade:** Devem existir ANTES de qualquer aluno real usar o sistema
- **Assessoria legal:** Madrasta do Leonardo (advogada especializada em direitos creditórios) está ajudando com checklist legal — trabalho em andamento

## 11. Regras de engajamento

Ao trabalhar neste projeto, SEMPRE siga estas regras:

- **Explica o "porquê" antes do "como"** — Leonardo precisa entender a motivação antes de ver código
- **Plano primeiro, código depois** — Para qualquer mudança, descreve o plano em alto nível e espera aprovação antes de editar arquivos
- **Mudanças grandes em passos pequenos** — Divide em etapas e confirma cada uma
- **Alerta proativo** — Se o pedido tem problema (técnico, segurança, negócio, estratégico), alerta com clareza ANTES de executar
- **Linguagem acessível** — Termos técnicos devem ser explicados brevemente. Não assuma conhecimento que Leonardo não demonstrou ter
- **Mostra como testar** — Sempre indica como validar uma mudança depois de feita
- **Git com permissão** — Sugere mensagem de commit mas NUNCA commita sem confirmação explícita
- **Deploy manual** — NUNCA faz deploy sozinho. Leonardo controla quando subir para produção
- **Pede saída real do terminal** — Leonardo costuma confirmar verbalmente em vez de colar saídas. Para mudanças críticas (env vars, deploys, comandos destrutivos), sempre exija a saída bruta antes de avançar.
- **Idioma:** Toda comunicação em português brasileiro

## 12. Comandos úteis

```bash
# --- Desenvolvimento local ---

# Subir banco + Redis
docker compose up -d

# Instalar dependências
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Rodar a API localmente
uvicorn app.main:app --reload --port 8000

# Docs interativos (Swagger)
# http://localhost:8000/docs

# Testar parser de texto (com API key local)
DEVKEY=$(grep "^INTERNAL_API_KEY=" .env | cut -d= -f2)
curl -X POST http://localhost:8000/api/v1/parser/texto \
  -H "X-API-Key: $DEVKEY" \
  -H "Content-Type: application/json" \
  -d '{"texto": "Finanças III\nAula 1 - 10/02\nProva - 24/02 peso 30%"}'

# Health check (público, sem auth)
curl http://localhost:8000/health

# --- Produção (Railway) ---
# URL: https://edubot-production-073e.up.railway.app
# Deploy: push para main (Railway faz deploy automático)
# NUNCA fazer push para main sem confirmação do Leonardo
```

## 13. Variáveis de ambiente necessárias

Ver `.env.example` para o template completo. Resumo:

### Obrigatórias em produção (app crasha sem elas)

- `ENVIRONMENT=production` — ativa guards de segurança em prod
- `WA_APP_SECRET` — Secret do app Meta (Frente 1 — HMAC do webhook)
- `INTERNAL_API_KEY` — Chave para endpoints `/api/v1/*` (Frente 2 — API key auth). Gere com `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. **Use chaves diferentes entre dev e prod.**
- `ANTHROPIC_API_KEY` — Chave da API Anthropic (sem ela, parser não funciona)
- `DATABASE_URL` — URL de conexão PostgreSQL

### Necessárias mas sem guard

- `WA_VERIFY_TOKEN` — Token de verificação do webhook WhatsApp (string inventada por você, deve bater com o que está configurado no painel Meta)
- `WA_PHONE_NUMBER_ID` — ID do número de telefone WhatsApp Business
- `PARSER_MODEL` — Modelo Claude (default: `claude-haiku-4-5-20251001`)

### Pendentes (referenciadas em planos futuros)

- `WA_ACCESS_TOKEN` — Token de acesso da API WhatsApp para **enviar** mensagens. **Ainda não usado pelo código** (envio não implementado). Em modo dev do Meta, dura 24h.
- `REDIS_URL` — URL do Redis (Celery e cache não implementados)
- `CORS_ORIGINS` — Origens permitidas (Frente 4 pendente; hoje fallback é `"*"`)

## 14. Histórico de mudanças importantes

### 18/abr/2026 — Frentes 1 e 2 ativas em produção

- **Frente 2 implementada e deployada** (commit `fb0403c`): API key auth via header `X-API-Key` em todos os endpoints `/api/v1/*`. Usa `secrets.compare_digest` para evitar timing attacks. Variável `INTERNAL_API_KEY` adicionada ao Railway com chave distinta da dev.
- **Frente 1 ativada de verdade**: descoberto que apesar do código HMAC estar commitado há semanas (`c995f81`), o app rodava em `ENVIRONMENT=development` no Railway, pulando o guard. Corrigido adicionando `ENVIRONMENT=production` e `WA_APP_SECRET` ao Railway.
- **Webhook WhatsApp configurado pela primeira vez no painel Meta**: callback URL registrada (`https://edubot-production-073e.up.railway.app/webhook`), verify_token sincronizado entre Railway e Meta, subscrição ao evento `messages` ativada.
- **Confirmado** que o bot **nunca respondeu** mensagem no WhatsApp — não por bug, mas porque o código de envio nunca foi escrito (`WA_ACCESS_TOKEN` referenciada em planos mas nunca lida pelo código). Ficou como prioridade 1 para próxima sessão.
