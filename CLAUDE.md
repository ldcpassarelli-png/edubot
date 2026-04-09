# CLAUDE.md — EduBot

## 1. Visão geral do projeto

EduBot é um copiloto acadêmico via WhatsApp para estudantes universitários brasileiros. O aluno envia seu plano de aula (texto colado, PDF ou foto) pelo WhatsApp, o sistema usa Claude Haiku 4.5 para extrair automaticamente todas as datas e atividades (provas, quizzes, entregas, etc.), e passa a enviar notificações diárias e semanais para manter o aluno organizado. Modelo B2B — o cliente é a instituição de ensino.

## 2. Sobre o desenvolvedor

- **Nome:** Leonardo (Leo) Passarelli, 22 anos
- **Formação:** Finanças no Insper (5º de 8 semestres), intercâmbio prévio no Babson College
- **Nível técnico:** Sem experiência prévia com desenvolvimento. Construiu o EduBot com ajuda de IA (Cursor + Claude)
- **Idioma:** Português brasileiro. Toda comunicação deve ser em PT-BR
- **Estilo de trabalho:** Prefere explicações acessíveis (termos técnicos devem ser explicados brevemente), guidance passo-a-passo com confirmação entre etapas, e nunca despejos grandes de código sem contexto

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
│   ├── main.py              # FastAPI app — lifespan, CORS, rotas
│   ├── models/
│   │   ├── database.py      # Modelos SQLAlchemy (6 tabelas)
│   │   └── connection.py    # Engine async + session factory
│   ├── routers/
│   │   ├── parser.py        # POST /api/v1/parser/{texto,pdf,imagem}
│   │   ├── alunos.py        # CRUD alunos + matérias + eventos
│   │   └── webhook.py       # GET+POST /webhook (WhatsApp)
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
3. `webhook.py` valida assinatura, identifica tipo (texto/PDF/imagem)
4. Texto longo (>200 chars) → `ParserEngine.parsear_texto()`
5. ParserEngine envia para Claude API com prompt especializado
6. Claude retorna JSON estruturado (matéria, eventos, datas)
7. Sistema gera resumo de confirmação formatado para WhatsApp
8. **[NÃO IMPLEMENTADO]** Envia resumo de volta ao aluno
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

| Método | Rota | Status |
|--------|------|--------|
| POST | `/api/v1/parser/texto` | Funcional |
| POST | `/api/v1/parser/pdf` | Funcional |
| POST | `/api/v1/parser/imagem` | Funcional |
| POST | `/api/v1/alunos` | Funcional |
| POST | `/api/v1/alunos/{id}/materias` | Funcional |
| GET | `/api/v1/alunos/{id}/proximos-eventos` | Funcional |
| GET | `/api/v1/alunos/{id}/eventos-hoje` | Funcional |
| GET | `/webhook` | Funcional (verificação Meta) |
| POST | `/webhook` | Parcial (recebe mas não responde) |
| GET | `/health` | Funcional |

## 5. Status atual

### Funciona

- Parser de texto, PDF e imagem via endpoints da API REST
- CRUD de alunos (criar/buscar por telefone)
- Adicionar matéria com eventos parseados
- Consulta de próximos eventos e eventos de hoje
- Verificação do webhook do WhatsApp (GET)
- Recepção de mensagens no webhook (POST) — identifica tipo e parseia texto longo
- Schema do banco completo com índices, views e triggers
- Deploy no Railway rodando

### Incompleto — TODOs no webhook.py

- Enviar mensagens de volta ao aluno via WhatsApp API
- Fluxo de onboarding (boas-vindas, criar aluno)
- Salvar eventos após confirmação do aluno
- Processar PDF e imagem recebidos pelo WhatsApp (baixar via Media API)
- Chat interativo (processar perguntas, buscar contexto)
- Armazenamento temporário no Redis (resultado do parser pré-confirmação)

### Ausente

- Sistema de notificações (Celery workers/tasks não existem)
- Alembic não configurado (sem pasta alembic/ nem alembic.ini)
- Zero testes automatizados
- Compliance LGPD no código (consentimento, direito ao esquecimento)

## 6. Pontos de atenção críticos

### Segurança (prioridade máxima)

1. **Webhook sem verificação obrigatória**: Se `WA_APP_SECRET` estiver vazio (padrão), qualquer pessoa pode enviar webhooks falsos. Em produção, isso DEVE ser obrigatório.
2. **Endpoints sem autenticação**: Todos os endpoints `/api/v1/*` são públicos. Qualquer pessoa com a URL pode chamar o parser (gerando custos na API Anthropic) ou manipular dados de alunos.
3. **Sem rate limiting**: Risco de explosão de custos na API Anthropic se alguém abusar do parser.
4. **CORS aberto**: Fallback é `"*"` (aceita qualquer origem). Em produção, restringir.

### Bugs e code smells

- `webhook.py:64`: `hmac.new()` — verificar se funciona (módulo Python usa `hmac.new`)
- `services/parser.py:105`: Atribuição duplicada `self.client = self.client = httpx.AsyncClient(...)`
- `requirements.txt:24-25`: `python-dotenv` listado duas vezes
- Parser usa httpx direto em vez da SDK oficial `anthropic` — menos robusto (sem retries automáticos)
- Código de limpeza de JSON duplicado nos 3 métodos do parser (texto, PDF, imagem)

## 7. Prioridades atuais (em ordem)

1. **Segurança**: Corrigir vulnerabilidades críticas da API (verificação de assinatura obrigatória, autenticação nos endpoints, rate limiting)
2. **Fluxo WhatsApp end-to-end**: Implementar todos os TODOs do webhook.py — o bot precisa realmente conversar com o aluno
3. **Notificações agendadas**: Implementar Celery workers para lembretes diários e semanais
4. **Compliance LGPD**: Logs de consentimento, direito ao esquecimento, política de privacidade
5. **Futuro**: App React Native como interface complementar

## 8. Modelo de negócio

- **Produto:** Copiloto acadêmico via WhatsApp para universitários brasileiros
- **Modelo:** B2B — vendido para departamentos acadêmicos de universidades
- **Preço:** R$ 69,90 por aluno por semestre
- **Meta 5 anos:** 1.000 a 50.000 alunos pagantes
- **Status:** Pré-lançamento. Nenhuma universidade cliente ainda
- **Equipe:** Leonardo sozinho (produto + negócio + dev com IA). Sem cofundador técnico

## 9. Restrições legais

- **LGPD:** Pré-lançamento exige conformidade total (dados de alunos brasileiros menores ou maiores de idade)
- **Trademark:** Nome "EduBot" precisa ser verificado/registrado
- **Termos de uso + Política de privacidade:** Devem existir ANTES de qualquer aluno real usar o sistema
- **Assessoria legal:** Madrasta do Leonardo (advogada especializada em direitos creditórios) está ajudando com checklist legal — trabalho em andamento

## 10. Regras de engajamento

Ao trabalhar neste projeto, SEMPRE siga estas regras:

- **Explica o "porquê" antes do "como"** — Leonardo precisa entender a motivação antes de ver código
- **Plano primeiro, código depois** — Para qualquer mudança, descreve o plano em alto nível e espera aprovação antes de editar arquivos
- **Mudanças grandes em passos pequenos** — Divide em etapas e confirma cada uma
- **Alerta proativo** — Se o pedido tem problema (técnico, segurança, negócio, estratégico), alerta com clareza ANTES de executar
- **Linguagem acessível** — Termos técnicos devem ser explicados brevemente. Não assuma conhecimento que Leonardo não demonstrou ter
- **Mostra como testar** — Sempre indica como validar uma mudança depois de feita
- **Git com permissão** — Sugere mensagem de commit mas NUNCA commita sem confirmação explícita
- **Deploy manual** — NUNCA faz deploy sozinho. Leonardo controla quando subir para produção
- **Idioma:** Toda comunicação em português brasileiro

## 11. Comandos úteis

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

# Testar parser de texto
curl -X POST http://localhost:8000/api/v1/parser/texto \
  -H "Content-Type: application/json" \
  -d '{"texto": "Finanças III\nAula 1 - 10/02\nProva - 24/02 peso 30%"}'

# Health check
curl http://localhost:8000/health

# --- Produção (Railway) ---
# URL: https://edubot-production-073e.up.railway.app
# Deploy: push para main (Railway faz deploy automático)
# NUNCA fazer push para main sem confirmação do Leonardo
```

## 12. Variáveis de ambiente necessárias

Ver `.env.example` para o template completo. Principais:

- `ANTHROPIC_API_KEY` — Chave da API Anthropic (obrigatória)
- `PARSER_MODEL` — Modelo Claude a usar (default: claude-haiku-4-5-20251001)
- `DATABASE_URL` — URL de conexão PostgreSQL
- `WA_VERIFY_TOKEN` — Token de verificação do webhook WhatsApp
- `WA_APP_SECRET` — Secret do app Meta (DEVE ser configurado em produção)
- `WA_PHONE_NUMBER_ID` — ID do número de telefone WhatsApp Business
- `WA_ACCESS_TOKEN` — Token de acesso da API WhatsApp
- `REDIS_URL` — URL do Redis
- `CORS_ORIGINS` — Origens permitidas (restringir em produção)
