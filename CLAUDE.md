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
| Migrações DB | Alembic | 1.13.0 (configurado; baseline 0001 + migration 0002 Camada 2) |
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
│   │   ├── database.py      # Modelos SQLAlchemy (20 tabelas: 6 Camada 1 + 14 Camada 2)
│   │   └── connection.py    # Engine async + session factory
│   ├── routers/
│   │   ├── parser.py        # POST /api/v1/parser/{texto,pdf,imagem} — protegido
│   │   ├── alunos.py        # CRUD alunos + matérias + eventos — protegido
│   │   └── webhook.py       # GET+POST /webhook (WhatsApp) — público (HMAC)
│   └── services/
│       ├── parser.py        # ParserEngine — chama Claude API
│       ├── whatsapp.py      # Envio de mensagens + download de mídia (Meta API)
│       ├── onboarding.py    # Máquina de estados do onboarding do aluno
│       └── classificador.py # ClassificadorEngine (Camada 2) — classifica msg em dúvidas
├── sql/
│   └── schema.sql           # Schema PostgreSQL completo (referência histórica; fonte da verdade agora é Alembic)
├── alembic/
│   ├── env.py               # Runner async com BLOQUEIO INCONDICIONAL contra Railway/produção
│   ├── script.py.mako       # Template de migration
│   └── versions/
│       ├── 0001_baseline_schema.py    # 6 tabelas Camada 1 (validada contra prod 16/05)
│       └── 0002_camada2_schema.py     # 14 tabelas Camada 2 (validada em banco descartável 19/05)
├── alembic.ini              # Config do Alembic
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
8. **(Camada 2, assíncrono)** Se a mensagem é de ENTRADA e `tipo == "text"`, o webhook agenda `classificador.processar_classificacao(...)` como **BackgroundTask** do FastAPI — roda DEPOIS da resposta ao aluno (a resposta é isco, responde rápido sempre). O task abre a PRÓPRIA sessão de banco, resolve turma via `matricula` ativa, chama o Haiku e grava 0/1/N linhas em `duvida`. Falha graciosa: qualquer erro loga e não grava nada — a `mensagem` crua fica intacta.

Estado do onboarding é persistido em `ConversaSessao.contexto` (JSON). Plano parseado fica em `contexto.plano_pendente` até confirmação.

---

## 6. Banco de dados — 20 tabelas (6 Camada 1 + 14 Camada 2)

### Camada 1 (6 tabelas, intocadas pela migration 0002)

| Tabela | Propósito |
|---|---|
| `instituicao` | Faculdade/universidade cliente (B2B) |
| `aluno` | Usuário final (identificado pelo telefone WhatsApp). Campo `onboarding_completo` controla fluxo |
| `materia` | Disciplina vinculada ao aluno (cópia isolada por aluno — não serve para agregação institucional) |
| `evento_academico` | Cada item do cronograma do aluno (prova, quiz, entrega, etc.) |
| `notificacao_log` | Registro de mensagens enviadas |
| `conversa_sessao` | Contexto de conversa para onboarding e chat. Campo `contexto` (JSON) guarda estado da máquina de estados |

### Camada 2 (14 tabelas, adicionadas pela migration 0002 — schema pronto, aplicação ainda não usa)

**Institucional (7):**
| Tabela | Propósito |
|---|---|
| `curso` | Curso da instituição (Adm, Eco) — ponte para casos onde matéria existe em currículos distintos |
| `materia_camada2` | Matéria como entidade institucional (nome propositalmente sufixado pra evitar colisão com `materia` legada) |
| `professor` | Professor titular de turma. Identificado por `telefone_whatsapp` UNIQUE |
| `plano_de_aula` | Documento institucional do semestre. UNIQUE(materia, semestre) — 1 plano por matéria por semestre |
| `unidade_tematica` | Nível 1 da taxonomia (bloco de aulas, ex: "Modelo de Índice Único") |
| `conceito` | Nível 2 da taxonomia (conceito específico, ex: "Decomposição de risco") |
| `aula` | Nível 3 (uma aula específica com data). Paralela a unidade/conceito, não FK direta |

**Turma (3):**
| Tabela | Propósito |
|---|---|
| `turma` | Turma específica. UNIQUE(materia, curso, letra, semestre). FKs com ON DELETE RESTRICT em matéria e curso (defesa contra exclusão acidental). `letra VARCHAR(20)` |
| `progresso_turma` | Ponteiro "em qual aula a turma está agora". UNIQUE(turma_id) — 1 progresso por turma |
| `matricula` | Aluno↔turma. **`aluno_telefone` é STRING, deliberadamente NÃO FK** — desacopla camadas em nível de banco |

**Consentimento (1):**
| Tabela | Propósito |
|---|---|
| `consentimento_camada2` | Rastro auditável LGPD. Guarda `texto_aceito` completo + `versao_texto` + `data_consentimento` + `data_revogacao`. Histórico via nova linha a cada mudança |

**Captura (3):**
| Tabela | Propósito |
|---|---|
| `mensagem` | Toda mensagem WhatsApp (entrada e saída) que passa pelo webhook. Fonte de verdade canônica das conversas. Imutável (sem updated_at) |
| `duvida` | Mensagem classificada (4 categorias: academica/organizacional/emocional/social). Tem flag `consentimento_camada2` travada no momento da criação. Tem coluna `embedding JSONB nullable` criada mas NÃO populada no MVP (upgrade futuro de clustering bottom-up) |
| `relatorio` | Relatório semanal por turma. UNIQUE(turma_id, semana_inicio). Token UUID com expiração de 14 dias |

**Convenções compartilhadas:**
- PKs UUID com `gen_random_uuid()`; timestamps em TIMESTAMPTZ
- Trigger `atualizar_updated_at()` aplicado em 8 tabelas com `updated_at` (reusa função criada pela `0001`)
- Ponte Camada 1↔Camada 2 = `aluno_telefone` STRING (não FK) em 4 tabelas: matricula, mensagem, duvida, consentimento_camada2
- Schema vivo no Alembic (`alembic/versions/`). `sql/schema.sql` é referência histórica da Camada 1.

Modelos SQLAlchemy em `app/models/database.py` cobrem as 20 tabelas (6 Camada 1 + 14 Camada 2, adicionados na Sessão CC #3). Os 14 modelos novos NÃO têm `relationship()` nesta fase — só colunas, FKs e UNIQUE constraints fiéis ao schema (validado campo a campo contra banco descartável). Relacionamentos entram quando uma sessão futura precisar.

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
| POST | `/webhook` | HMAC (Meta) | ✅ Funcional (deploy `0bbe444`, 08/05/2026) |
| GET | `/health` | público | ✅ Funcional |

---

## 8. Estado atual (atualizar ao fim de cada sessão)

**Última atualização:** 05/06/2026 (Sessão CC #4 — classificador de mensagem da Camada 2, validado em banco descartável)

### ✅ Pronto e em produção

- Backend FastAPI no Railway, rodando em `ENVIRONMENT=production`
- Parser de texto/PDF/imagem (Claude Haiku 4.5) com endpoints REST autenticados
- Schema completo das 6 tabelas
- CRUD de alunos, matérias, eventos
- Webhook GET (verify_token) configurado e subscrito ao evento `messages` no painel Meta
- **Frente 1 ativa:** validação HMAC obrigatória em produção (`WA_APP_SECRET` configurado, commit `c995f81`)
- **Frente 2 ativa:** API key auth em endpoints internos (`INTERNAL_API_KEY`, commit `fb0403c`)
- Landing page (Gamma)

### ✅ Deploy Camada 1 completo (08/05/2026)

- **`app/services/whatsapp.py`** — cliente HTTP Meta Graph API: `enviar_mensagem_texto()` + `baixar_midia()`. Tratamento de erro: token expirado (190), número não autorizado (131030), rate limit (429), timeout. Commit `0bbe444`
- **`app/services/onboarding.py`** — máquina de estados com 6 estados (NOVO → ATIVO), reconhecimento generoso de SIM/NÃO, persistência em `ConversaSessao.contexto`. Commit `0bbe444`
- **`app/routers/webhook.py`** — handler completo: extrai mensagem → delega pro onboarding → envia resposta. Sempre retorna 200 ao Meta. Commit `0bbe444`
- **`app/main.py`** — warning não-fatal no lifespan se `WA_ACCESS_TOKEN` ou `WA_PHONE_NUMBER_ID` faltarem em prod. Commit `2b6e373`
- **Token permanente Meta** — System User `edubot-api`, app EduBot (`1510528877441440`), scopes `whatsapp_business_messaging` + `whatsapp_business_management`, `expires_at=0`. Validado via curl + debug_token em 08/05/2026
- **Pipeline ponta-a-ponta validado (08/05/2026):** webhook de teste do painel Meta → HMAC valida → onboarding cria aluno + sessão + transiciona estado → retorna 200. Envio falha corretamente com log "número não autorizado" (esperado em Dev Mode)
- **HEAD em produção:** `fbdde4d`

### ✅ Fundação de banco para Camada 2 (Sessões CC #1 + #2)

- **Alembic configurado** (Sessão CC #1, 16/05/2026): runner async com asyncpg, BLOQUEIO INCONDICIONAL contra Railway/produção via lista de patterns no `env.py` (sem flag de destravar, decisão de segurança consciente)
- **Baseline `0001_baseline_schema.py`** das 6 tabelas existentes da Camada 1 — validada contra produção campo a campo via console read-only do Railway. Dois defeitos de `jsonb` (server_default com aspas escapadas) pegos no banco de teste descartável e corrigidos antes de qualquer toque em produção
- **Migration `0002_camada2_schema.py`** (Sessão CC #2, 19/05/2026): 14 tabelas novas + 4 UNIQUE compostas + 16 FKs com `ON DELETE` corretos + 8 triggers `updated_at` reusando função da `0001`. Validação completa: `upgrade head` limpo em banco descartável, `pg_dump --schema-only` auditado campo a campo, `downgrade -1` reverte ao estado da `0001` sem erro
- **Commits locais (sem push):** `db61abf` (setup Alembic + baseline 0001), `fb1df50` (migration 0002 Camada 2). Branch `main` 2 commits à frente de `origin/main`
- **Stamp em produção:** ainda não feito. Quando feito, segue **exclusivamente** Opção B: `alembic stamp 0001 --sql` → SQL revisado manualmente → aplicado fora do Alembic via psql/console Railway. Mesmo procedimento para `0002` quando chegar a hora. Princípio: não instalar a chave do cofre ao lado do cofre

### ✅ Modelos Camada 2 + persistência de mensagem (Sessão CC #3, 04/06/2026)

- **14 modelos SQLAlchemy** das tabelas da Camada 2 em `app/models/database.py`, junto com os 6 da Camada 1 (mesmo arquivo, mesmo padrão). Sem `relationship()` nesta fase. JSONB explícito (não JSON genérico). Validados campo a campo contra banco descartável: 14/14 sem divergência estrutural
- **Persistência de mensagem no webhook** (`app/routers/webhook.py`): toda mensagem de ENTRADA e SAÍDA é gravada na tabela `mensagem` (fonte de verdade canônica da Camada 2). Helpers novos: `_ja_processada`, `_gravar_mensagem`, `_responder`, `_conteudo_e_metadados`
- **Dedup por `whatsapp_message_id`**: antes de processar, checa se a mensagem já foi gravada; se sim, ignora TUDO (não grava, não roda onboarding, não responde) — blinda contra reenvio do Meta avançar a máquina de estados duas vezes. Resolvido só na aplicação (UNIQUE parcial fica pra migration 0003)
- **`whatsapp.py` intocado**: a gravação da saída mora no webhook; saída grava com `whatsapp_message_id = NULL` (enviar_mensagem_texto retorna só bool)
- **Camada 1 intacta** (princípio aditivo): onboarding, criação de aluno/sessão e máquina de estados seguem operando — confirmado no teste local (fluxo NOVO → AGUARDANDO_NOME → AGUARDANDO_PLANO)
- **Commitado em 5403dc1, sem push pro Railway.**

### ✅ Classificador de mensagem (Sessão CC #4, 05/06/2026)

- **`app/services/classificador.py`** — `ClassificadorEngine` (espelha `ParserEngine`: httpx direto, Claude Haiku 4.5). `classificar(texto)` devolve `list[DuvidaClassificada]` (0/1/N itens) ou `None` em falha graciosa (erro HTTP, JSON malformado, validação) — provado em teste que o `None` nasce DENTRO do engine
- **Contrato JSON do Haiku:** `{"duvidas": [{"categoria": "<codigo>", "texto_extraido": "..."}]}`, sem markdown. 4 códigos: `academica` / `organizacional` / `emocional` / `social`. Validado por Pydantic; categoria fora do enum é descartada
- **Persistência seletiva:** só `academica` e `organizacional` viram linha em `duvida`. `social` (ruído) e `emocional` são detectadas mas **NÃO persistidas** no MVP (constante `CATEGORIAS_NAO_PERSISTIDAS`). Emocional adiada por exigir desenho próprio de agregação (evento temporal, não tópico) + risco de exposição individual — reversível, a mensagem crua fica em `mensagem`
- **Roda como BackgroundTask** agendado pelo `webhook.py` só para ENTRADA + `tipo == "text"`. Abre a própria sessão (`async_session`), nunca levanta exceção pro request
- **Resolução de turma via `matricula` ativa** (Caminho A): 0 matrículas → não classifica (estado esperado hoje, ninguém tem matrícula até CC #7); 2+ → guarda defensiva, não classifica; 1 → usa. `consentimento_camada2` é snapshot travado no momento da criação da dúvida (última linha por `data_consentimento`, true só se consentiu e não revogou)
- **`main.py`** instancia `ClassificadorEngine` no lifespan (cliente próprio, compartilhado) e fecha no shutdown
- **Validado em banco descartável `edubot_test_cc4`:** 7 cenários → 5 dúvidas gravadas (academica×3, organizacional×1, e os casos social/emocional/malformado/misto com o resultado esperado); consentimento t/f correto; `mensagem` crua intacta em todos. Falha graciosa do engine provada com JSON malformado → `None` + log
- **Fora de escopo (fast-follow):** lookup de conceito/aula via plano de aula, população de `embedding`, calibração de prompt por matéria — adiados para pós-CC #7
- **Commitado em `6271934`, sem push pro Railway.**

### ❌ Bloqueador ativo — Meta Dev Mode

- App está em **Dev Mode** no Meta. Mensagens reais de WhatsApp **não disparam webhook** — só webhooks de teste do painel funcionam
- Solução: **Business Verification** do CNPJ no Meta Business Manager → janela estimada 2-4 semanas
- Detalhes operacionais em `pendencias_operacionais.md` no Project do Claude (chat), não no repo
- Número pessoal do Leo precisa ser registrado como test recipient (modo dev bloqueia envio para números não autorizados — code 131030)

### ⚠️ Incidente operacional — 07/05/2026

- Credenciais coladas no chat (Anthropic API key, Internal API key, WA Access Token). Todas rotacionadas no mesmo dia
- Aproveitada rotação para limpar duplicação de `INTERNAL_API_KEY` no `.env` local
- Vars rotacionadas e aplicadas no Railway em 08/05/2026: `WA_ACCESS_TOKEN`, `ANTHROPIC_API_KEY`, `INTERNAL_API_KEY`. Restart limpo, sem warnings

### 🟡 Camada 2 — schema pronto, código de aplicação ainda não existe

Schema completo das 14 tabelas no banco (migration 0002, validada em banco descartável). Falta toda a camada de aplicação:

- Modelos SQLAlchemy das 14 tabelas novas (hoje `database.py` só cobre a Camada 1)
- Persistência de mensagem ligada ao webhook (tabela `mensagem` — fundação de toda Camada 2)
- ~~Classificador de mensagem (Claude Haiku, 4 categorias, com fallback "captura sem classificar")~~ ✅ CC #4 (05/06)
- Agregador semanal de dúvidas por turma
- Gerador de relatório (Claude Sonnet, sem material proprietário no MVP)
- Rota `/r/{token}` no FastAPI (servida pelo próprio app — embrião natural da Camada 3)
- Comandos WhatsApp: `/revogar`, `/ativar-feedback`, confirmação semanal de progresso pelo professor
- Texto de consentimento LGPD efetivo (em revisão jurídica externa, fora do repo)
- Agendamento automático de envio do relatório (bloqueado pelo mesmo gargalo do BV — exige template aprovado pra enviar fora da janela de 24h)

### ❌ Camada 3 — Instituição

Não existe em código. Bloqueada por LGPD (consentimento maduro é pré-requisito) e por Camada 2 estável.

- Dashboard institucional autenticado (frontend React separado, consumindo API)
- Métricas pedagógicas agregadas (curva de dúvidas por professor, gaps por matéria, comparativo entre turmas)
- Avaliação docente data-driven

---

## 9. Próximos passos (ordem)

### Sessão imediata — fechar Camada 1 fim-a-fim

~~1. Revisar e completar `webhook.py`~~ ✅ Auditado em 07/05
~~2. Testar localmente com payload simulado~~ ✅ Smoke test passou em 07/05
~~3. Debug 401 do Meta~~ ✅ Resolvido em 08/05 — "E" duplicado no paste + token temporário expirado
~~4. Commit dos 5 arquivos pendentes~~ ✅ 3 commits em 08/05 (`0bbe444`, `2b6e373`, `fbdde4d`)
~~5. Deploy no Railway + configurar vars~~ ✅ Push + vars aplicadas em 08/05, restart limpo
~~6. Gerar token permanente via System User~~ ✅ `edubot-api`, expires_at=0, validado via curl
7. **Registrar número pessoal do Leo como test recipient** no painel Meta
8. **Aguardar Business Verification** do CNPJ no Meta (2-4 semanas) → sair de Dev Mode
9. Teste fim-a-fim: mandar mensagem real do WhatsApp → validar fluxo NOVO → ATIVO

### Curto prazo — completar Camada 1

- Notificações agendadas (Celery + Redis): lembretes diários e semanais de eventos
- Texto de consentimento LGPD no onboarding (preparando Camadas 2/3)
- Frente 3 — Rate limiting (`slowapi`): risco financeiro real (custo Anthropic se alguém abusar do parser)
- Frente 4 — CORS restrito (lista explícita de origens em prod)
- eSIM dedicado para o número oficial (em andamento — Vivo)

### Médio prazo — Camada 2 (schema pronto, falta aplicação)

Sequência de Sessões CC pendentes, em ordem de dependência:

1. ✅ **Sessão CC #1 (16/05):** Alembic + baseline `0001` (concluída)
2. ✅ **Sessão CC #2 (19/05):** migration `0002` com as 14 tabelas (concluída, commit local `fb1df50`, sem push)
3. ✅ **Sessão CC #3 (04/06) — Modelos SQLAlchemy da Camada 2 + persistência de mensagem no webhook** (concluída, validada local, sem push). Os 14 modelos em `database.py`; webhook grava cada mensagem (entrada e saída) em `mensagem` com dedup por `whatsapp_message_id`
4. ✅ **Sessão CC #4 (05/06) — Classificador de mensagem** (concluída, validada em banco descartável, sem push). `classificador.py` classifica msg de ENTRADA em 0/1/N dúvidas via Haiku, roda como BackgroundTask; só `academica`/`organizacional` persistem (`social`/`emocional` detectadas mas não gravadas); turma via matrícula ativa; falha graciosa devolve `None`. Conceito/aula/embedding/calibração por matéria ficam pra fast-follow pós-CC #7
5. **Sessão CC #5 — Agregador semanal de dúvidas.** Lote rodando aos domingos, junta dúvidas da semana por turma, formata estrutura JSON do relatório (3 blocos da Decisão 5 da Sessão 1)
6. **Sessão CC #6 — Gerador de relatório (Claude Sonnet) + rota `/r/{token}` no FastAPI.** Geração da prosa do bloco 3 + servindo o relatório web pelo próprio app. Mostra histórico do semestre quando aberto (token vence em 14 dias, mas a página agrega todas as semanas da turma daquele semestre)
7. **Sessão CC #7 — Comandos WhatsApp + onboarding ampliado.** `/revogar`, `/ativar-feedback`, confirmação semanal de progresso pelo professor. Adicionar coleta de consentimento LGPD no fluxo de onboarding (apresentação única, sem barreira recorrente)
8. **Sessão CC #8 — Agendamento automático (Celery + Redis).** Disparo dominical do agregador + envio do relatório via WhatsApp pro professor. **Bloqueado por:** envio fora da janela de 24h exige template aprovado → exige app publicado no Meta → exige Business Verification do CNPJ. Adiar até BV aprovado

**Frente paralela off-Claude (caminho crítico):** Business Verification do CNPJ no Meta (janela 2-4 semanas, detalhada em `pendencias_operacionais.md` no Project do chat). Sem BV, Camada 1 não tem WhatsApp real e Camada 2 não tem agendamento de envio. Sessões CC #3-#7 podem rodar em paralelo à BV.

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
- ~~`webhook.py.backup-antes-onboarding` precisa ser removido~~ ✅ removido em 08/05/2026

### Dívidas técnicas registradas na Sessão CC #3 (04/06/2026)

- **Logging da mensagem de SAÍDA mora no `webhook.py`, não no `whatsapp.py`** (decisão consciente). Consequência: a saída grava com `whatsapp_message_id = NULL`, porque `enviar_mensagem_texto` retorna só `bool`. Quando notificações agendadas entrarem (CC #8), o envio acontecerá fora do webhook — reavaliar mover o logging pro serviço de envio e capturar o id que o Meta devolve, pra correlação com status updates (delivered/read)
- **Dedup de `whatsapp_message_id` é só na aplicação** (SELECT antes de inserir). Há uma janela de corrida estreita entre dois reenvios quase simultâneos do Meta. A blindagem definitiva é o UNIQUE parcial (`WHERE whatsapp_message_id IS NOT NULL`) — fica pra migration `0003`, antes de produção real

### Dívidas técnicas registradas na Sessão CC #2 (19/05/2026)

- **`mensagem.whatsapp_message_id` é índice normal, não UNIQUE.** Dedup de webhook reenviado fica como responsabilidade da aplicação. Revisar em migration futura antes de produção real — preferência: `UNIQUE WHERE whatsapp_message_id IS NOT NULL` (UNIQUE parcial)
- **`duvida.embedding JSONB` criado mas NÃO populado no MVP.** Clustering bottom-up de dúvidas (descoberta de subtemas fora do plano de aula) é upgrade pós-validação. Subida pra "Nível 3" (popular + clusterizar) acontece quando houver 4-6 semanas de dado real de turmas piloto pra tunar threshold com base na realidade, não em chute. Exige: chave de API de embedding (OpenAI ou Voyage), código de embedding no classificador, algoritmo de clustering, integração no relatório. Sessão de produto própria, não adendo
- **Onboarding da Camada 1 precisa ser ampliado** pra perguntar **letra da turma** quando Camada 2 estiver ativa. Hoje o aluno só identifica matéria; sem letra/curso é impossível agregar dúvidas na turma certa. Mudança vai pra Sessão CC #7 (comandos + onboarding ampliado)
- **Página `/r/{token}` mostra histórico do semestre da turma**, não apenas a semana de referência do token. Schema não muda; é lógica da rota — implementar na Sessão CC #6. Razão: professor decide o que revisitar baseado em tendência, não em foto isolada de uma semana
- **Modelo "Pessoa + PapelNaTurma" descartado.** Versões anteriores do design da Camada 2 mencionavam multi-papel (mesma pessoa como aluno em uma turma, monitor em outra). Decisão final (16/05): monitor não acessa Camada 2, simplificação confirmada. Schema atual tem entidades separadas `aluno` (Camada 1) e `professor` (Camada 2). Se um dia precisar voltar atrás, é refatoração consciente, não esquecimento

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

### 05/06/2026 — Sessão CC #4: classificador de mensagem da Camada 2
- **`app/services/classificador.py`** criado: `ClassificadorEngine` (httpx direto + Claude Haiku 4.5, mesmo padrão do `ParserEngine`). `classificar()` devolve lista de dúvidas ou `None` em falha graciosa. Orquestrador `processar_classificacao()` abre própria sessão, resolve turma via matrícula, grava em `duvida`, nunca levanta
- **`webhook.py`** agenda a classificação como BackgroundTask só para ENTRADA + `tipo == "text"`, após gravar a `mensagem` e responder ao aluno. `main.py` instancia/fecha o engine no lifespan
- **Decisão de produto:** `social` e `emocional` são detectadas mas NÃO persistidas no MVP (`CATEGORIAS_NAO_PERSISTIDAS`). Emocional adiada por exigir agregação por evento temporal + risco de exposição individual — reversível (mensagem crua intacta)
- **Resolução de turma (Caminho A):** via `matricula` ativa. 0 → não classifica (estado esperado até CC #7); 2+ → guarda defensiva; 1 → usa. Consentimento é snapshot travado na criação da dúvida
- **Validação em banco descartável `edubot_test_cc4`:** 7 cenários → 5 dúvidas (academica×3, organizacional×1; social/emocional/malformado/misto com resultado esperado); consentimento t/f correto; `mensagem` crua intacta. Falha graciosa do engine provada com JSON malformado → `None` + log de erro
- **Fora de escopo (fast-follow pós-CC #7):** conceito/aula via plano de aula, população de `embedding`, calibração de prompt por matéria
- 3 arquivos tocados (`classificador.py` novo, `webhook.py`, `main.py`). Camada 1 intacta. Commitado local, sem push

### 04/06/2026 — Sessão CC #3: modelos Camada 2 + persistência de mensagem
- 14 modelos SQLAlchemy da Camada 2 em `database.py` (sem relationship, JSONB explícito); validados campo a campo contra banco descartável (14/14 fiéis; diferenças de nullable só em colunas com default, idênticas ao padrão da Camada 1)
- Webhook passa a gravar entrada e saída em `mensagem`; dedup por `whatsapp_message_id` blinda reenvio do Meta (testado: reenvio não duplica linha nem avança estado)
- `whatsapp.py` intocado; saída grava com id NULL. Duas dívidas registradas (outbound logging no webhook; dedup só na aplicação até migration 0003)
- 2 arquivos tocados (`database.py`, `webhook.py`). Camada 1 confirmada intacta. Sem commit/push ainda

### 19/05/2026 — Sessão CC #2: migration 0002 com 14 tabelas da Camada 2

- **Arquitetura técnica da Camada 2 fechada no chat** antes do CC: 14 tabelas (não 13 como previsto na Sessão 2 de 16/05 — `curso` adicionado como entidade separada porque no Insper "Finanças III" existe em currículos distintos de Adm e Eco com turmas separadas, mesma matéria)
- **Decisões de produto novas fechadas na sessão:** letra da turma como discriminador (não horário), `letra VARCHAR(20)`, UNIQUE composta de 4 colunas em `turma`, token de relatório UUID com expiração de 14 dias, página `/r/{token}` mostra histórico do semestre da turma, embedding criado no schema mas não populado no MVP (Nível 1)
- **Migration `0002_camada2_schema.py`** escrita pelo CC seguindo padrão da `0001`: 14 tabelas + 17 índices novos + 4 UNIQUE compostas + 16 FKs (com ON DELETE RESTRICT em `turma.materia_camada2_id` e `turma.curso_id`, SET NULL em FKs nullable, CASCADE no resto) + 8 triggers `updated_at` reusando função da `0001`
- **Validação em banco descartável `edubot_test_0002`:** `upgrade head` limpo, `pg_dump --schema-only` auditado linha a linha contra a especificação (sem nenhum desvio, sem bug de JSONB), `downgrade -1` reverte limpo ao estado da `0001`
- **2 commits locais (sem push):** `db61abf` (chore: instala Alembic + baseline 0001 — incluído porque a Sessão CC #1 ainda estava untracked), `fb1df50` (feat: migration 0002 da Camada 2). Branch `main` 2 commits à frente de `origin/main`
- **Dívidas técnicas registradas:** `whatsapp_message_id` como índice normal (não UNIQUE) — dedup responsabilidade da aplicação; `embedding` criado mas não populado (sessão de produto futura quando houver dado real); onboarding da Camada 1 precisa ser ampliado pra perguntar letra de turma quando Camada 2 ativar; `/r/{token}` mostra histórico do semestre (lógica de rota, não schema)
- Stamp em produção ainda não feito. Quando feito, exclusivamente via Opção B (`alembic stamp 0001 --sql` + aplicação manual fora do Alembic). Decisão consciente registrada em 16/05: bloqueio de produção no `env.py` fica INCONDICIONAL, sem flag de destravar

### 16/05/2026 — Sessões 1+2 de arquitetura da Camada 2 + Sessão CC #1 (Alembic + baseline)

- **Sessão 1 de arquitetura (produto)** no chat: 6 decisões da Camada 2 fechadas — unidade de agregação = turma; modelo de papéis (titular dono, monitor não acessa Camada 2 — decisão final); definição de dúvida (4 categorias: academica/organizacional/emocional/social); taxonomia hierárquica de 3 níveis derivada do plano de aula; entrega de relatório semanal domingo 15h via WhatsApp + link web; consentimento LGPD opt-in com flag por dúvida sem barreira recorrente
- **5 planos de aula reais analisados** (Marketing, GOS, ECC, Econometria, Finanças II do Insper) — confirmaram empiricamente que estrutura institucional é parseable (4 colunas-chave + datas + agrupamento temático), plano é único por matéria por semestre, execução diverge entre turmas (cada turma com ponteiro de progresso próprio)
- **Sessão 2 de arquitetura (técnica)** no chat: plano arquitetural das 7 frentes aprovado — schema aditivo nunca destrutivo, `Aluno` legado da Camada 1 intocado, `Turma` é a entidade compartilhada central, ponte Camada 1↔Camada 2 = telefone como string (NÃO FK), agregação em lote semanal (não tempo real), relatório servido pelo próprio FastAPI (embrião natural da Camada 3)
- **Sessão CC #1 — Alembic + baseline**: instalado controle de versão de schema async com asyncpg ANTES de criar qualquer tabela nova; baseline `0001` das 6 tabelas da Camada 1 escrita à mão (fidelidade ao `sql/schema.sql`)
- **Decisão de segurança consciente:** CC propôs flag `ALEMBIC_ALLOW_PROD` para destravar bloqueio de produção no futuro — **recusada por Leo**. Bloqueio fica incondicional, sem chave. Princípio: não instalar a chave do cofre ao lado do cofre
- **Validação de fidelidade contra produção** (exigida no chat, contra a fonte certa): rodar baseline em banco de teste só prova que executa, não que bate com produção. Adicionado passo de comparação estrutural contra o banco real do Railway. Dois defeitos `jsonb` (server_default com aspas escapadas em `conversa_sessao.mensagens/contexto` e `instituicao.contato_diretoria`) pegos no banco de teste descartável, corrigidos antes de qualquer toque em produção. Comparação campo a campo das 6 tabelas via console read-only do Railway (sem senha trafegando) — baseline confirmada fiel

### 08/05/2026 — Deploy Camada 1 + token permanente + validação pipeline
- **Token permanente Meta:** System User `edubot-api`, app EduBot, scopes `whatsapp_business_messaging` + `whatsapp_business_management`, `expires_at=0`. Debug do 401 revelou "E" duplicado no paste + token temporário expirado
- **3 commits deployados:** `0bbe444` (feat: WhatsApp client + onboarding + webhook), `2b6e373` (chore: hardening warnings), `fbdde4d` (docs: CLAUDE.md). HEAD em produção: `fbdde4d`
- **Vars rotacionadas no Railway:** `WA_ACCESS_TOKEN`, `ANTHROPIC_API_KEY`, `INTERNAL_API_KEY`. Restart limpo, sem warnings no log
- **Pipeline validado:** webhook de teste do painel Meta → HMAC → onboarding cria aluno + sessão → retorna 200. Envio falha com "número não autorizado" (esperado: Dev Mode)
- **Bloqueio identificado:** app em Dev Mode no Meta. Mensagens reais não disparam webhook. Solução: Business Verification do CNPJ (2-4 semanas)
- Backups antigos removidos: `CLAUDE.md.backup-pre-v2`, `webhook.py.backup-antes-onboarding`

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
