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

**Estado de implementação:** Camada 1 com código completo e auditado — pendente credenciais Meta e commit/deploy. Camada 2 tem schema (migration `0002`, 14 tabelas), modelos (`database.py`), classificador (CC #4), agregador semanal (CC #5) e — na **CC #6 (18/06)** — gerador de subconceito (Haiku) + prosa (Sonnet) + rota `/r/{token}` + seed de demo, com a migration `0003`. **CC #1–#6 commitadas e pushadas; a 0003 + rota `/r/{token}` foram DEPLOYADAS em produção em 18/06 (commit `3fcd947`).** Camada 3 continua sem código.

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
| Banco de dados | PostgreSQL | **18.3 em produção** · 16 no dev (Docker) — divergência a alinhar |
| ORM | SQLAlchemy (async) | 2.0.35 |
| Driver DB | asyncpg | 0.29.0 |
| Migrações DB | Alembic | 1.13.0 (baseline 0001 + migrations 0002 e **0003**; **0002 aplicada em produção 17/06 via SQL manual, Opção B**; **0003 aplicada em produção 18/06, mesma Opção B**) |
| IA / Parser + classificação + subconceito | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | via API HTTP (httpx) |
| IA / prosa do relatório (CC #6) | Claude Sonnet 4.6 (`claude-sonnet-4-6`, const `PROSA_MODEL` em `relatorio_gen.py`) | via API HTTP (httpx) |
| HTTP Client | httpx | 0.27.0 |
| Validação | Pydantic | 2.9.0 |
| Fila de tarefas | Celery + Redis | 5.4.0 / 5.1.0 (instalado, NÃO implementado) |
| Deploy | Railway (Nixpacks) | edubot-production-073e.up.railway.app |
| Containers (dev) | Docker Compose | PostgreSQL 16 + Redis 7 (⚠️ prod roda 18.3 — alinhar dev) |

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
│   │   ├── webhook.py       # GET+POST /webhook (WhatsApp) — público (HMAC)
│   │   └── relatorio.py     # GET /r/{token} (Camada 2, CC #6) — Jinja2, público (token UUID)
│   ├── services/
│   │   ├── parser.py        # ParserEngine — chama Claude API
│   │   ├── whatsapp.py      # Envio de mensagens + download de mídia (Meta API)
│   │   ├── onboarding.py    # Máquina de estados do onboarding do aluno
│   │   ├── classificador.py # ClassificadorEngine (Camada 2) — classifica msg em dúvidas
│   │   ├── agregador.py     # AgregadorEngine (Camada 2) — matching dúvida→conceito + agregação semanal
│   │   └── relatorio_gen.py # SubconceitoEngine (Haiku) + ProsaEngine (Sonnet) — enriquecimento (CC #6)
│   ├── templates/           # Jinja2: relatorio.html + relatorio_indisponivel.html (CC #6)
│   └── scripts/
│       ├── agregar.py       # Disparo manual do agregador (python -m app.scripts.agregar)
│       └── seed_demo_fin2.py  # Seed VERSIONÁVEL de demo (Fin II · 4DPA · Prof. exemplo) — CC #6
├── sql/
│   └── schema.sql           # Schema PostgreSQL completo (referência histórica; fonte da verdade agora é Alembic)
├── alembic/
│   ├── env.py               # Runner async com BLOQUEIO INCONDICIONAL contra Railway/produção
│   ├── script.py.mako       # Template de migration
│   └── versions/
│       ├── 0001_baseline_schema.py    # 6 tabelas Camada 1 (validada contra prod 16/05)
│       ├── 0002_camada2_schema.py     # 14 tabelas Camada 2 (validada em banco descartável 19/05)
│       └── 0003_prosa_acao_e_unique_wamid.py  # prosa_acao + UNIQUE parcial wamid (CC #6, local)
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

## 6. Banco de dados — 21 tabelas (6 Camada 1 + 15 Camada 2)

### Camada 1 (6 tabelas, intocadas pela migration 0002)

| Tabela | Propósito |
|---|---|
| `instituicao` | Faculdade/universidade cliente (B2B) |
| `aluno` | Usuário final (identificado pelo telefone WhatsApp). Campo `onboarding_completo` controla fluxo |
| `materia` | Disciplina vinculada ao aluno (cópia isolada por aluno — não serve para agregação institucional) |
| `evento_academico` | Cada item do cronograma do aluno (prova, quiz, entrega, etc.) |
| `notificacao_log` | Registro de mensagens enviadas |
| `conversa_sessao` | Contexto de conversa para onboarding e chat. Campo `contexto` (JSON) guarda estado da máquina de estados |

### Camada 2 (15 tabelas: 14 da migration 0002 + `coorte` da `0004`)

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

**Turma (coorte + 3):**
| Tabela | Propósito |
|---|---|
| `coorte` | **(migration 0004)** A "turma-Insper" (grade fechada que o `codigo_convite` abre) ACIMA da `turma`. FK `curso_id` → curso (RESTRICT), `letra`, `semestre`, `codigo_convite` UNIQUE, `ativo`, timestamps. UNIQUE(curso_id, letra, semestre). Agrupa turmas; cada turma mantém seu próprio `professor_id` |
| `turma` | Turma específica (classe-de-matéria, unidade do relatório). UNIQUE(materia, curso, letra, semestre). FKs ON DELETE RESTRICT em matéria e curso. **Ganhou `coorte_id NOT NULL` (FK → coorte, RESTRICT) na `0004`.** `letra VARCHAR(20)` |
| `progresso_turma` | Ponteiro "em qual aula a turma está agora". UNIQUE(turma_id) — 1 progresso por turma |
| `matricula` | **Aluno↔coorte (repontada na `0004`: era Aluno↔turma).** `turma_id` DROPADA; agora `coorte_id NOT NULL` (FK → coorte CASCADE), UNIQUE(coorte_id, aluno_telefone). O `aluno_telefone` segue STRING deliberadamente NÃO-FK (ponte Camada 1↔2 desacoplada); o acoplamento por FK existe só dentro da Camada 2, para a coorte |

**Consentimento (1):**
| Tabela | Propósito |
|---|---|
| `consentimento_camada2` | Rastro auditável LGPD. Guarda `texto_aceito` completo + `versao_texto` + `data_consentimento` + `data_revogacao`. Histórico via nova linha a cada mudança |

**Captura (3):**
| Tabela | Propósito |
|---|---|
| `mensagem` | Toda mensagem WhatsApp (entrada e saída) que passa pelo webhook. Fonte de verdade canônica das conversas. Imutável (sem updated_at) |
| `duvida` | Mensagem classificada (4 categorias: academica/organizacional/emocional/social). Tem flag `consentimento_camada2` travada no momento da criação. Tem coluna `embedding JSONB nullable` criada mas NÃO populada no MVP (upgrade futuro de clustering bottom-up). **`0004`: ganhou `coorte_id NOT NULL` (FK CASCADE); `turma_id` virou NULLABLE (FK → turma preservada, CASCADE).** |
| `relatorio` | Relatório semanal por turma. UNIQUE(turma_id, semana_inicio). Token UUID com expiração de 14 dias. **Coluna `prosa_acao TEXT NULL` (migration 0003) guarda a prosa do Sonnet.** Subconceitos vivem DENTRO do JSONB `conteudo` (sem coluna nova): caminho real `conteudo.academica.unidades[].conceitos[].subconceitos[]` = `{nome, alunos_count, reincidentes_count}` |

**Convenções compartilhadas:**
- PKs UUID com `gen_random_uuid()`; timestamps em TIMESTAMPTZ
- Trigger `atualizar_updated_at()` aplicado em 9 tabelas com `updated_at` (reusa função criada pela `0001`; `coorte` entrou na `0004`)
- Ponte Camada 1↔Camada 2 = `aluno_telefone` STRING (não FK) em 4 tabelas: matricula, mensagem, duvida, consentimento_camada2
- Schema vivo no Alembic (`alembic/versions/`). `sql/schema.sql` é referência histórica da Camada 1.

Modelos SQLAlchemy em `app/models/database.py` cobrem as 21 tabelas (6 Camada 1 + 15 Camada 2; `Coorte` adicionado na CC #7). Os modelos da Camada 2 NÃO têm `relationship()` nesta fase — só colunas, FKs e UNIQUE constraints fiéis ao schema (validado campo a campo contra banco descartável). Relacionamentos entram quando uma sessão futura precisar.

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
| GET | `/r/{token}` | token UUID (14 dias) | ✅ Funcional **em produção** (deploy 18/06, `3fcd947`) — Jinja2 server-side; token inválido/expirado → página "indisponível" 200, nunca 500 |

---

## 8. Estado atual (atualizar ao fim de cada sessão)

**Última atualização:** 30/06/2026 (CC #7 **DEPLOYADA**: migration `0004` — entidade `coorte` acima de `turma` — aplicada em produção via Opção B e verificada; ver subseção CC #7 abaixo e §15)

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
- **HEAD em produção (após este deploy de 08/05):** `fbdde4d` (o HEAD atual é `cb1ea24` — ver subseção de deploy 17/06)

### ✅ Fundação de banco para Camada 2 (Sessões CC #1 + #2)

- **Alembic configurado** (Sessão CC #1, 16/05/2026): runner async com asyncpg, BLOQUEIO INCONDICIONAL contra Railway/produção via lista de patterns no `env.py` (sem flag de destravar, decisão de segurança consciente)
- **Baseline `0001_baseline_schema.py`** das 6 tabelas da Camada 1. ⚠️ **Correção (17/06):** a comparação "campo a campo" contra produção (console read-only do Railway, 16/05) cobriu **tabelas e colunas — NÃO objetos não-tabela** (funções, triggers, views). O deploy de 17/06 provou que a prod tem só `pgcrypto` + as 6 tabelas: a função `atualizar_updated_at()`, os 3 triggers da Camada 1 (`trg_aluno/materia/conversa_updated`) e as 2 views (`proximos_eventos`, `eventos_hoje`) que a `0001` define **nunca chegaram à prod** (que nasceu do `sql/schema.sql` aplicado à mão, não do Alembic). No deploy: a função foi **criada** (pré-requisito dos triggers da `0002`); as 2 views são **vestigiais** (nenhum código as consulta — os endpoints `proximos-eventos`/`eventos-hoje` vão direto às tabelas via ORM); os 3 triggers seguem **ausentes** em prod (divergência registrada, fora do escopo aditivo do deploy). Ver §11 e §15. (Os 2 defeitos de `jsonb` pegos no banco descartável seguem corrigidos antes de produção.)
- **Migration `0002_camada2_schema.py`** (Sessão CC #2, 19/05/2026): 14 tabelas novas + 4 UNIQUE compostas + 16 FKs com `ON DELETE` corretos + 8 triggers `updated_at` reusando função da `0001`. Validação completa: `upgrade head` limpo em banco descartável, `pg_dump --schema-only` auditado campo a campo, `downgrade -1` reverte ao estado da `0001` sem erro
- **Commits `db61abf` (Alembic + baseline 0001) e `fb1df50` (migration 0002):** ✅ **pushados em 17/06** no pacote de deploy (`origin/main` em `cb1ea24`).
- **Stamp em produção:** ✅ **feito em 17/06 via Opção B** (SQL manual, fora do Alembic): `stamp 0001` → `CREATE OR REPLACE FUNCTION atualizar_updated_at()` → `0002.sql`. Resultado: `alembic_version='0002'`. Procedimento e achados na subseção de deploy abaixo e na §15. O princípio segue intacto: o bloqueio do `env.py` contra Railway permanece **incondicional**; migrations de produção são sempre manuais via Opção B.

### ✅ Modelos Camada 2 + persistência de mensagem (Sessão CC #3, 04/06/2026)

- **14 modelos SQLAlchemy** das tabelas da Camada 2 em `app/models/database.py`, junto com os 6 da Camada 1 (mesmo arquivo, mesmo padrão). Sem `relationship()` nesta fase. JSONB explícito (não JSON genérico). Validados campo a campo contra banco descartável: 14/14 sem divergência estrutural
- **Persistência de mensagem no webhook** (`app/routers/webhook.py`): toda mensagem de ENTRADA e SAÍDA é gravada na tabela `mensagem` (fonte de verdade canônica da Camada 2). Helpers novos: `_ja_processada`, `_gravar_mensagem`, `_responder`, `_conteudo_e_metadados`
- **Dedup por `whatsapp_message_id`**: antes de processar, checa se a mensagem já foi gravada; se sim, ignora TUDO (não grava, não roda onboarding, não responde) — blinda contra reenvio do Meta avançar a máquina de estados duas vezes. Resolvido só na aplicação (UNIQUE parcial ✅ migration `0003`, **aplicada em produção 18/06**)
- **`whatsapp.py` intocado**: a gravação da saída mora no webhook; saída grava com `whatsapp_message_id = NULL` (enviar_mensagem_texto retorna só bool)
- **Camada 1 intacta** (princípio aditivo): onboarding, criação de aluno/sessão e máquina de estados seguem operando — confirmado no teste local (fluxo NOVO → AGUARDANDO_NOME → AGUARDANDO_PLANO)
- **Commitado em `5403dc1` — ✅ pushado em 17/06** (deploy do pacote Camada 2).

### ✅ Classificador de mensagem (Sessão CC #4, 05/06/2026)

- **`app/services/classificador.py`** — `ClassificadorEngine` (espelha `ParserEngine`: httpx direto, Claude Haiku 4.5). `classificar(texto)` devolve `list[DuvidaClassificada]` (0/1/N itens) ou `None` em falha graciosa (erro HTTP, JSON malformado, validação) — provado em teste que o `None` nasce DENTRO do engine
- **Contrato JSON do Haiku:** `{"duvidas": [{"categoria": "<codigo>", "texto_extraido": "..."}]}`, sem markdown. 4 códigos: `academica` / `organizacional` / `emocional` / `social`. Validado por Pydantic; categoria fora do enum é descartada
- **Persistência seletiva:** só `academica` e `organizacional` viram linha em `duvida`. `social` (ruído) e `emocional` são detectadas mas **NÃO persistidas** no MVP (constante `CATEGORIAS_NAO_PERSISTIDAS`). Emocional adiada por exigir desenho próprio de agregação (evento temporal, não tópico) + risco de exposição individual — reversível, a mensagem crua fica em `mensagem`
- **Roda como BackgroundTask** agendado pelo `webhook.py` só para ENTRADA + `tipo == "text"`. Abre a própria sessão (`async_session`), nunca levanta exceção pro request
- **Resolução de turma via `matricula` ativa** (Caminho A): 0 matrículas → não classifica (estado esperado hoje, ninguém tem matrícula até CC #7); 2+ → guarda defensiva, não classifica; 1 → usa. `consentimento_camada2` é snapshot travado no momento da criação da dúvida (última linha por `data_consentimento`, true só se consentiu e não revogou)
- **`main.py`** instancia `ClassificadorEngine` no lifespan (cliente próprio, compartilhado) e fecha no shutdown
- **Validado em banco descartável `edubot_test_cc4`:** 7 cenários → 5 dúvidas gravadas (academica×3, organizacional×1, e os casos social/emocional/malformado/misto com o resultado esperado); consentimento t/f correto; `mensagem` crua intacta em todos. Falha graciosa do engine provada com JSON malformado → `None` + log
- **Fora de escopo (fast-follow):** lookup de conceito/aula via plano de aula, população de `embedding`, calibração de prompt por matéria — adiados para pós-CC #7
- **Commitado em `6271934` — ✅ pushado em 17/06.**

### ✅ Agregador semanal de dúvidas (Sessão CC #5, 07/06/2026)

- **`app/services/agregador.py`** — `AgregadorEngine` (espelha `ClassificadorEngine`: httpx + Haiku, falha graciosa). Faz matching dúvida→conceito EM LOTE (1 call por turma) e agrega a semana fechada da turma num JSON estatístico gravado em `relatorio`
- **Matching (D3):** só toca `duvida` `academica` consentida com `conceito_id IS NULL`. Sem confiança → NULL (balde "não classificadas"). Chute proibido — conceito errado corromperia o relatório. Re-run é estável (não re-sorteia conceito já casado). `mapear_conceitos()` devolve `None` em falha graciosa → tudo fica NULL
- **`aula_id` (D4):** heurística por data (aula com `data_prevista` mais recente ≤ data da dúvida; senão NULL). Sem Haiku
- **Janela:** domingo anterior → sábado (semana fechada), `America/Sao_Paulo` via `zoneinfo`. Relatório de domingo cobre a semana que terminou no sábado anterior. Filtro half-open `[domingo 00:00, próximo domingo 00:00)`
- **Privacidade (LGPD) — decisão de produto fechada na CC #5:** `relatorio.conteudo` é ESTATÍSTICA PURA. NENHUMA mensagem crua e NENHUM telefone entram no JSON — só contagens. "não classificadas" e "organizacional" são só `{volume}` / distribuição temporal. Razão: texto livre pode conter PII de terceiros ("eu e a Maria não entendemos X") — estatística entrega o valor pedagógico sem o risco
- **Consentimento (D1):** filtra pelo snapshot `duvida.consentimento_camada2 = true` (bool travado na criação pela CC #4); NÃO reconsulta a tabela `consentimento_camada2`
- **Idempotência:** upsert na UNIQUE `(turma_id, semana_inicio)`. Re-run ATUALIZA a linha; `token_acesso`/`created_at` preservados (token pode já ter ido ao professor) — provado em teste: re-run mantém 1 linha, token estável, `gerado_em` atualizado
- **`app/scripts/agregar.py`** — disparo manual (`python -m app.scripts.agregar [--data-ref YYYY-MM-DD] [--turma-id UUID]`). Celery+Redis é a CC #8
- **Validado em banco descartável `edubot_test_cc5`** (recriado do zero — o `edubot_test_cc4` foi dropado e o seed da CC #4 nunca foi commitado): 6 cenários (caminho feliz, matching NULL, consentimento=false fora, não-consolidação, organizacional separado, boundary de janela) + idempotência. SELECT bruto do `relatorio.conteudo` auditado (contagens batem com o seed)
- **Matching validado AO VIVO** (Haiku real, HTTP 200): das 6 dúvidas academicas na janela, 5 casaram com conceito e o "gráfico de barras no Excel" ficou em NULL (balde "não classificadas") — NULL honesto, sem chute. WACC casou 4× (aluno A 3× + aluno B 1×) e Risco/Retorno 1×. `aula_id` inferido por data bateu (06-01/06-02 → "Risco e Retorno"; 06-03 → "WACC"). A dúvida do aluno sem consentimento e a fora da janela não entraram no relatório
- **Fora de escopo:** prosa de relatório (Sonnet, CC #6), rota `/r/{token}` (CC #6), `embedding` (Nível 1, não populado), agendamento (CC #8)

### ✅ Deploy Camada 2 + rate limiting em produção (17/06/2026)

- **Migration `0002` aplicada em produção** via SQL manual (Opção B), em 3 passos atômicos: (1) `stamp 0001` (cria `alembic_version='0001'`); (2) `CREATE OR REPLACE FUNCTION atualizar_updated_at()` (pré-requisito que faltava em prod — ver §11/§15); (3) `0002.sql` (14 tabelas Camada 2 + 8 triggers + `UPDATE` versão → `'0002'`). Validado: 14 tabelas Camada 2 nascem, as 6 da Camada 1 **intactas** (contagens idênticas antes/depois), `alembic_version='0002'`.
- **Backup verificado via restore** antes da migration (regra 15): `pg_dump -Fc` da prod restaurado num clone Postgres 18 descartável, contagens batendo campo a campo. Plano de rollback escrito antes (Rota A: DROP cirúrgico das 14 tabelas; Rota B: restore do dump).
- **Ensaio em clone (2A) pegou 2 defeitos antes da prod:** o "stamp 0002" seria destrutivo (`CREATE TABLE` de tabela já existente) e a função `atualizar_updated_at()` não existia em prod. A receita final de 3 passos corrige os dois.
- **Rate limiting (Frente 3) deployado** — `slowapi`, teto global `300/min` em memória no `POST /webhook`, com 200-no-estouro pro Meta. Commit `cb1ea24`. Testado local (rajada de 360 → 300 passam, 61 cortadas, todas 200).
- **Push completo:** todos os commits locais acumulados (CC #1–#5 + docs + rate limiting) em `origin/main` (`cb1ea24`). Deploy Railway ACTIVE, boot limpo. Smoke test do pipeline real (botão Test do painel Meta) → linha nova em `mensagem` com o `wamid` do sample = recepção + HMAC + persistência vivos na versão nova. `/health` 200.
- **HEAD em produção:** `cb1ea24`.

### ✅ Relatório: subconceito + prosa + rota `/r/{token}` + seed de demo (Sessão CC #6, 18/06/2026)

> **DEPLOYADO em produção (18/06).** Build/teste local validados na sessão de 18/06; o deploy foi feito em sessão própria com o ritual da regra 15 — ver entrada "Deploy CC #6" na §15.

- **Migration `0003_prosa_acao_e_unique_wamid.py`** (down_revision `0002`): (a) `relatorio.prosa_acao TEXT NULL`; (b) **UNIQUE parcial** em `mensagem.whatsapp_message_id` (`WHERE whatsapp_message_id IS NOT NULL`) que **substitui** o índice normal `idx_mensagem_whatsapp_id` da `0002` — fecha a dívida de dedup só-na-aplicação da CC #2/#3. Validada local: `upgrade head` + `downgrade -1` limpos em `edubot_demo`.
- **`app/services/relatorio_gen.py`** — dois engines (espelham o agregador: httpx + falha graciosa):
  - **`SubconceitoEngine` (Haiku):** roda PÓS-agregação, só para Conceito com **volume ≥ 2**. Lê as dúvidas brutas do conceito (anonimizadas: `aluno_1…`, **telefone NUNCA vai ao LLM**), nomeia 2-4 subtemas na LÍNGUA DO CONCEITO. **Contagens (`alunos_count`/`reincidentes_count`) calculadas em Python**, não pedidas ao modelo. NULL honesto = lista vazia. Grava em `conteudo.academica.unidades[].conceitos[].subconceitos[]`. Prompt parametrizado por **categoria de matéria** (`financas` é a do seed). Texto bruto vai ao Haiku transitório, **nunca persiste** — só a estatística entra no JSONB.
  - **`ProsaEngine` (Sonnet, `claude-sonnet-4-6` via const `PROSA_MODEL`):** lê o `conteudo` JÁ enriquecido + taxonomia do plano + progresso + próximos marcos; escreve a "sugestão de ação" atacando o PORQUÊ (2-4 parágrafos). Sem texto cru, sem material proprietário. Falha graciosa → `None` (página renderiza sem o bloco, sem quebrar).
- **Ligação no agregador:** `processar_agregacao` recebe os dois engines (kwargs opcionais, default `None` → preserva comportamento CC #5); chama `enriquecer` entre montar conteúdo e upsert; `_upsert_relatorio` grava `prosa_acao`. `app/scripts/agregar.py` instancia e passa os engines.
- **`app/routers/relatorio.py` + `app/templates/`** — rota `GET /r/{token}` (Jinja2 server-side puro, Chart.js via CDN). Token inválido/expirado → `relatorio_indisponivel.html` via `TemplateResponse` (200, nunca 500). Gráfico de histórico mostra **só semanas ≤ a do token** (nunca futuro). Métricas: dúvidas, "Alunos com dúvida" X/total, conceitos travando, próxima aula (1ª após a semana-ref). `main.py` registra o router.
- **`app/scripts/seed_demo_fin2.py`** — seed **VERSIONÁVEL** (ativo de venda, não dado real): Finanças II · turma 4DPA · Prof. Exemplo (nome genérico — não usar nome de pessoa real em dado de demo), ~41 alunos (~68% consentem), plano FIXO (não usa o parser), ~58 dúvidas de histórico + ~45 na semana-ref (pré-PI), idempotente. **NÃO hardcoda subconceito nem prosa** — a pipeline real produz. Semana-ref **29/03-04/04** (`--data-ref 2026-04-05`).
- **Validado AO VIVO em `edubot_demo`** (Haiku + Sonnet reais, HTTP 200): 40 academicas/semana-ref, 39 casadas + 1 NULL honesto; subtemas com não-consolidação real ("5 alunos, 3 voltaram"); curva do histórico crescente (3→40); página renderiza com faixa LGPD no topo, subtema em destaque, vermelho na não-consolidação, prosa do Sonnet conectando à PI. Provado por SELECT bruto + screenshots.
- **Polimento futuro anotado** (não feito): agrupar conceitos da mesma unidade sob um cabeçalho só (hoje "MODELO DE ÍNDICE ÚNICO" repete por card). O beta caiu sob "Decomposição do risco" sozinho ao subir o volume — sem matching manual.

### ✅ Coorte acima de Turma — migration `0004` em produção (Sessão CC #7, 30/06/2026)

> **DEPLOYADA em produção (30/06) via Opção B**, com o ritual da regra 15: um dump ANTERIOR de prod (estado 0003+seed) foi **provado por restore** virando o clone do ensaio (up/down); e um **backup pré-deploy** foi tirado no minuto do deploy como rede de rollback (não re-verificado por restore). Ver entrada CC #7 na §15.

- **Entidade `coorte` nasce ACIMA de `turma`** (a "turma-Insper" / grade fechada que o `codigo_convite` abre). `turma` NÃO muda de significado: segue classe-de-matéria e unidade do relatório. Coorte agrupa turmas; cada turma mantém seu `professor_id`.
- **Migration `0004_coorte_acima_de_turma.py`** (down_revision `0003`), aditiva, DDL à mão (sem autogenerate). Como `turma`/`matricula`/`duvida` já estavam POPULADAS, cada coluna NOT NULL nova entrou nullable → backfill → SET NOT NULL; `coorte` (vazia) nasceu NOT NULL inline:
  - `coorte`: `curso_id` FK → curso (RESTRICT), `letra`, `semestre`, `codigo_convite` UNIQUE, `ativo`, timestamps; UNIQUE(curso_id, letra, semestre); trigger `trg_coorte_updated`.
  - `turma`: ganhou `coorte_id NOT NULL` (FK → coorte RESTRICT) + índice `idx_turma_coorte`.
  - `matricula`: **repontada** de `turma_id` → `coorte_id` — `turma_id` DROPADA, UNIQUE virou (coorte_id, aluno_telefone), FK → coorte CASCADE. Guarda `RAISE EXCEPTION` aborta se algum aluno estivesse em >1 turma da mesma coorte.
  - `duvida`: ganhou `coorte_id NOT NULL` (FK CASCADE); `turma_id` virou NULLABLE (FK → turma preservada, CASCADE) + índice `idx_duvida_coorte`.
- **Aplicada e verificada em produção:** transação atômica (`ON_ERROR_STOP=1`), COMMIT limpo, guarda não disparou. Backfill: 1 coorte, `turma` 1/1, `matricula` 41/41, `duvida` 104/104; `alembic_version='0004'`; `codigo_convite` no padrão `AUTO-…`. **Backup provado por restore** = o dump anterior (`prod_backup_0003_seed_20260630.dump`), que virou o clone do ensaio. **Backup pré-deploy** (rede de rollback, tirado imediatamente antes, **não** re-verificado por restore): `~/.edubot/prod_backup_0004_PRE_20260630_2228.dump`. Rollback: `downgrade()` da 0004 (provado no ensaio up/down do clone `edubot_clone_ensaio`).
- **Model (`app/models/database.py`):** classe `Coorte` nova + `coorte_id` em `Turma`, `Matricula` repontada (perde `turma_id`), `Duvida` com `turma_id` `Optional` e `coorte_id` NOT NULL. Reflete o estado final do schema.
- **Lição do ritual (Opção B):** no `alembic upgrade 0003:0004 --sql` offline, o próprio Alembic emite o `BEGIN/COMMIT` e o `UPDATE alembic_version` na mesma transação — **NÃO escrever à mão** (quebraria a contabilidade). Range `0003:0004` só vale offline; no online usa-se `upgrade head`.
- **Débito ABERTO (não tocado nesta migration):** o agregador (CC #5) precisa passar a filtrar `WHERE turma_id IS NOT NULL`, já que `duvida.turma_id` agora pode ser NULL — ver §11. E o `seed_demo_fin2.py` precisa ser adaptado ao schema coorte (fora deste commit).

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
- ✅ Frente 3 — Rate limiting (`slowapi`): **deployado em 17/06** (commit `cb1ea24`) — teto global `300/min` em memória no `POST /webhook`, 200-no-estouro pro Meta. Ver §10 e §8.
- Frente 4 — CORS restrito (lista explícita de origens em prod)
- eSIM dedicado para o número oficial (em andamento — Vivo)
- **Diretriz de produto — tutoria IA (quando construída; HOJE NÃO EXISTE — o bot só responde com strings fixas da máquina de estados de onboarding):** a tutoria por IA deve ser **100% acadêmica = escopo do curso** — responder dentro do universo do curso e **redirecionar gentilmente** o que estiver fora. NÃO é "recusar tudo que não for conceito puro": dúvida **emocional sobre a matéria** e **organizacional** (prazos/prova) seguem no escopo (isca legítima + sinal pro relatório). Coerente com "resposta é isco" — tutor restrito ao plano de aula.

### Médio prazo — Camada 2 (schema pronto, falta aplicação)

Sequência de Sessões CC pendentes, em ordem de dependência:

1. ✅ **Sessão CC #1 (16/05):** Alembic + baseline `0001` (concluída)
2. ✅ **Sessão CC #2 (19/05):** migration `0002` com as 14 tabelas (concluída, `fb1df50`, ✅ pushada 17/06 — **0002 aplicada em produção**)
3. ✅ **Sessão CC #3 (04/06) — Modelos SQLAlchemy da Camada 2 + persistência de mensagem no webhook** (concluída, validada local, ✅ pushada 17/06). Os 14 modelos em `database.py`; webhook grava cada mensagem (entrada e saída) em `mensagem` com dedup por `whatsapp_message_id`
4. ✅ **Sessão CC #4 (05/06) — Classificador de mensagem** (concluída, validada em banco descartável, ✅ pushada 17/06). `classificador.py` classifica msg de ENTRADA em 0/1/N dúvidas via Haiku, roda como BackgroundTask; só `academica`/`organizacional` persistem (`social`/`emocional` detectadas mas não gravadas); turma via matrícula ativa; falha graciosa devolve `None`. Conceito/aula/embedding/calibração por matéria ficam pra fast-follow pós-CC #7
5. ✅ **Sessão CC #5 (07/06) — Agregador semanal de dúvidas** (concluída, validada em banco descartável `edubot_test_cc5`, ✅ pushada 17/06). `agregador.py` faz matching dúvida→conceito em lote (Haiku, NULL quando sem confiança) + agrega a semana fechada da turma num JSON estatístico em `relatorio` (upsert idempotente). Disparo manual via `app/scripts/agregar.py`. Decisão de produto: relatório é estatística pura, zero texto cru / zero telefone no JSON. Matching validado ao vivo (Haiku real, HTTP 200): 5 de 6 academicas casadas, "gráfico no Excel" em NULL honesto

**✅ Deploy dos commits locais acumulados (Camada 2 CC #1–#5 + docs + rate limiting) — FEITO em 17/06, antes da CC #6.** O pacote foi pra produção como sessão de deploy dedicada: migration `0002` aplicada via SQL manual (Opção B, com a função `atualizar_updated_at()` criada como pré-requisito), rate limiting deployado, push completo (`origin/main` em `cb1ea24`), backup verificado via restore + plano de rollback, smoke test do pipeline OK. Detalhes na subseção de deploy da §8 e na §15. A CC #6 agora pode testar a rota `/r/{token}` contra ambiente real.

6. ✅ **Sessão CC #6 (18/06) — Subconceito (Haiku) + prosa (Claude Sonnet) + rota `/r/{token}` + migration 0003 + seed de demo** (concluída, **validada local, sem commit, sem prod**). Gerador de subconceito + prosa do bloco 3, relatório web servido pelo próprio app, gráfico de histórico só com semanas passadas. Detalhes na subseção CC #6 da §8 e na §15. **Deploy da 0003 + rota em produção = sessão separada (regra 15).**

   **Extração de subconceito por LLM entra no escopo da CC #6 (decisão 15/06/2026).** O nível de subconceito é o que faz o professor agir — o "tópico"/Conceito top-down do plano de aula é ruído pra ele. Mecanismo (decisão fechada): Haiku/Sonnet lê as dúvidas de cada Conceito-com-volume e nomeia os 2-4 subtemas recorrentes + reincidência por aluno, raciocinando semanticamente (funciona com pouco volume, situação do piloto). NÃO é clustering por embedding — esse segue adiado pra quando houver volume real (centenas de dúvidas); a coluna `embedding` continua criada e não populada. O "NULL honesto" se estende: Haiku sem confiança pra nomear subconceito deixa a dúvida no nível do Conceito. Custo: +1 chamada Haiku por Conceito-com-volume por semana (desprezível no piloto). **Resolvido na CC #6 (18/06):** o subconceito grava em `conteudo.academica.unidades[].conceitos[].subconceitos[]` (DENTRO do JSONB existente, **sem migration nova pra isso** — a `0003` só adiciona `prosa_acao` + UNIQUE wamid); contagens (`alunos_count`/`reincidentes_count`) calculadas em Python (não pedidas ao modelo); prompt parametrizado por categoria de matéria (`financas` primeiro). Volume mínimo do conceito pra chamar o Haiku = 2.
7. **Sessão CC #7 — Comandos WhatsApp + onboarding ampliado.** `/revogar`, `/ativar-feedback`, confirmação semanal de progresso pelo professor. Adicionar coleta de consentimento LGPD no fluxo de onboarding (apresentação única, sem barreira recorrente). Também: **rate limit por telefone do remetente** (cota por aluno) — o teto global de hoje (300/min) é extintor de anomalia de volume e NÃO cobre "aluno individual abusando"; faz sentido quando houver matrícula (escala com usuários).
8. **Sessão CC #8 — Agendamento automático (Celery + Redis). ❌ CORTADA do caminho do piloto.** Para 1-2 turmas, o agregador roda **manualmente** via `python -m app.scripts.agregar` todo domingo. Automatizar o processo semanal de 2 turmas é gold-plating. Disparo dominical automático + envio do relatório via WhatsApp pro professor só voltam à mesa quando houver volume real (e, para o envio, depois do BV: fora da janela de 24h exige template aprovado → app publicado no Meta → Business Verification do CNPJ)

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

#### Frente 3 — Rate limiting global no webhook (ativa em prod desde 17/06/2026)

- **Código:** `app/limiter.py` (Limiter `slowapi`, `key_func` constante → teto GLOBAL), `@limiter.limit("300/minute")` no `POST /webhook`, handler de `RateLimitExceeded` que devolve **200** pro `/webhook` no estouro (não 429 — pra não provocar reenvio do Meta; demais rotas recebem 429).
- **Natureza:** teto global em memória (`memory://`, in-process — não Redis), extintor contra loop/bug/reenvio do Meta, NÃO cota por aluno. `WEBHOOK_RATE_LIMIT` é constante única, afinável. **Extensão futura:** limite por telefone do remetente (cota por aluno), quando houver matrícula — ver CC #7 (§9) e débito (§11).
- **Dependência:** `slowapi==0.1.10` no `requirements.txt`. **Commit:** `cb1ea24` (deployado 17/06).

### Pendentes

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

### Dívidas técnicas registradas no deploy de 17/06/2026

- **Baseline `0001` diverge da produção real (IMPORTANTE).** A prod nasceu de `sql/schema.sql` aplicado à mão, NÃO pelo Alembic. Ela tem apenas `pgcrypto` + as 6 tabelas da Camada 1: a função `atualizar_updated_at()`, os 3 triggers (`trg_aluno/materia/conversa_updated`) e as 2 views (`proximos_eventos`, `eventos_hoje`) que a `0001` define **nunca existiram em prod**. A "validação fiel campo a campo" da `0001` (registrada em 16/05) cobriu só tabelas/colunas — não objetos não-tabela. Estado pós-deploy: a função foi criada (pré-requisito da `0002`); as views são vestigiais (sem uso no código); os 3 triggers continuam **ausentes**. **Decisão pendente:** se/como reconciliar a baseline `0001` com a prod real — sessão própria, não urgente. Liga com a **Regra 16** da §14 (validação de fidelidade deve cobrir objetos não-tabela).
- **Rate limit por telefone (cota por aluno) ainda não existe — só o teto global.** O `slowapi` deployado em 17/06 é um teto GLOBAL (300/min, extintor de anomalia de volume); NÃO limita um aluno individual abusando dos caminhos que chamam a API Anthropic. Quando houver matrícula (CC #7), adicionar limite por telefone do remetente, que escala com a base de usuários. Ver CC #7 na §9.

### Dívidas técnicas registradas na consultoria estratégica (15/06/2026)

*Nota: os dois itens abaixo foram nomeados na consultoria 15/06 como **riscos técnicos de não-dev** — pontos-cegos que vêm de Leo não ser desenvolvedor (risco prospectivo), não débito já contraído. Ficam registrados aqui por proximidade temática; não são dívida no sentido estrito da seção.*

- **Instrumentar a taxa de classificação por categoria desde o dia 1 em produção.** Logar a distribuição das categorias do classificador (`academica` / `organizacional` / `social` / `emocional` / `nao_classificadas`) a cada mensagem processada. Razão: o seed mostrou NULL honesto baixo, mas o português real de aluno (abreviação, ironia, mistura de matérias) pode elevar o balde "não classificadas" além do que o seed sugere — sem instrumentação, isso só apareceria tarde, com o relatório já pobre. Detectar cedo
- **Health check com alerta no webhook.** Hoje uma queda do serviço só é descoberta por reclamação de aluno. Falta um monitor ativo do `/health` (ou do webhook) que avise proativamente. Liga com a dívida "sem observabilidade" da subseção de infraestrutura abaixo. Estimativa: uma tarde

### Dívidas técnicas registradas na Sessão CC #7 (30/06/2026)

- **Agregador (CC #5) ainda assume `duvida.turma_id` NOT NULL.** A `0004` afrouxou `duvida.turma_id` para NULLABLE (a dúvida agora também se ancora na coorte via `coorte_id`). O matching dúvida→conceito/aula e as queries de agregação precisam passar a filtrar `WHERE turma_id IS NOT NULL` (ou migrar para agregar por `coorte_id`) — hoje uma dúvida com `turma_id` NULL entraria/quebraria silenciosamente. **Não foi tocado na 0004** (migration é só schema); é código de aplicação, próxima sessão
- **`app/scripts/seed_demo_fin2.py` desatualizado vs. schema coorte.** O seed provavelmente insere `matricula`/`duvida` com `turma_id`, que a 0004 removeu/afrouxou — precisa ser adaptado (criar `coorte` + repontar `matricula.coorte_id`) antes de re-rodar pra demo de julho. Ficou intocado no working tree, FORA deste commit — revisão própria

### Dívidas técnicas registradas na Sessão CC #5 (07/06/2026)

- **Matching é 1 chamada Haiku por turma/semana, sem cache.** Com muitas turmas isso vira custo/latência — reavaliar batch entre turmas ou cache quando houver volume real
- **"não classificadas" é só contagem (decisão de privacidade), então o professor não vê o que ficou fora do plano.** Quando `embedding`/clustering bottom-up entrar (pós dado real), o balde NULL vira fonte de descoberta de subtemas — hoje é só um número
- **`aula_id` por heurística de data ignora turmas adiantadas/atrasadas vs. `progresso_turma`.** Quando o ponteiro de progresso por turma for usado (CC #7), reavaliar inferir aula pelo progresso real, não só pela `data_prevista` do plano
- **Seed da Camada 2 (`seed_cc5.py`) precisa de flush em camadas** porque os modelos da Camada 2 não têm `relationship()` (decisão CC #3) — o unit of work do SQLAlchemy não ordena inserts entre tabelas sem isso. Vale pra qualquer seed/escrita em lote futura na Camada 2

### Dívidas técnicas registradas na Sessão CC #3 (04/06/2026)

- **Logging da mensagem de SAÍDA mora no `webhook.py`, não no `whatsapp.py`** (decisão consciente). Consequência: a saída grava com `whatsapp_message_id = NULL`, porque `enviar_mensagem_texto` retorna só `bool`. Quando notificações agendadas entrarem (CC #8), o envio acontecerá fora do webhook — reavaliar mover o logging pro serviço de envio e capturar o id que o Meta devolve, pra correlação com status updates (delivered/read)
- ✅ **(RESOLVIDO em produção — migration `0003` aplicada 18/06)** **Dedup de `whatsapp_message_id` era só na aplicação** (SELECT antes de inserir). A blindagem definitiva é o UNIQUE parcial (`WHERE whatsapp_message_id IS NOT NULL`) — **entrou na migration `0003`** (substitui o índice normal da 0002) e está **ativa em produção desde 18/06**.

### Dívidas técnicas registradas na Sessão CC #2 (19/05/2026)

- ✅ **(RESOLVIDO em produção — migration `0003` aplicada 18/06)** **`mensagem.whatsapp_message_id` era índice normal, não UNIQUE.** A `0003` dropa o índice normal e cria `UNIQUE WHERE whatsapp_message_id IS NOT NULL` (UNIQUE parcial; também serve de lookup, sem redundância). Ativo em produção desde 18/06.
- **`duvida.embedding JSONB` criado mas NÃO populado no MVP.** Clustering bottom-up de dúvidas (descoberta de subtemas fora do plano de aula) é upgrade pós-validação. Subida pra "Nível 3" (popular + clusterizar) acontece quando houver 4-6 semanas de dado real de turmas piloto pra tunar threshold com base na realidade, não em chute. Exige: chave de API de embedding (OpenAI ou Voyage), código de embedding no classificador, algoritmo de clustering, integração no relatório. Sessão de produto própria, não adendo
- **Onboarding da Camada 1 precisa ser ampliado** pra perguntar **letra da turma** quando Camada 2 estiver ativa. Hoje o aluno só identifica matéria; sem letra/curso é impossível agregar dúvidas na turma certa. Mudança vai pra Sessão CC #7 (comandos + onboarding ampliado)
- ✅ **(IMPLEMENTADO na CC #6)** **Página `/r/{token}` mostra histórico do semestre da turma** via gráfico (Chart.js), não apenas a semana de referência do token — e **só semanas ≤ a do token** (nunca futuro). Lógica na rota `app/routers/relatorio.py`; schema não mudou. Razão: professor decide o que revisitar baseado em tendência, não em foto isolada de uma semana
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
15. **Migration em produção exige backup verificado VIA RESTORE.** Antes de tocar o schema de produção (a começar pela migration `0002`), a sequência é obrigatória e nesta ordem: (1) `pg_dump` completo da produção; (2) restaurar o dump num banco clone descartável — isso **prova** que o backup funciona; (3) aplicar o SQL da migration nesse clone primeiro; (4) só então produção, com plano de rollback escrito antes. Princípio: **backup não restaurado é esperança, não backup.** **Comprovada na prática (deploy 17/06):** o ensaio em clone (passo 3) pegou **2 defeitos antes de produção** — o "stamp 0002" destrutivo e a função `atualizar_updated_at()` ausente em prod. A regra não é teórica; foi o ensaio que evitou um deploy quebrado.
16. **Validação de fidelidade contra produção deve cobrir objetos NÃO-tabela.** Comparar schema esperado vs. produção tem que incluir **funções, triggers, views e extensões** — não só tabelas e colunas. O deploy de 17/06 revelou que a baseline `0001` divergia da prod exatamente nos objetos não-tabela (função/3 triggers/2 views), porque a validação de 16/05 só olhou tabelas/colunas. Antes de qualquer migration que **dependa** de um objeto não-tabela (ex.: triggers que reusam uma função), confirme que esse objeto existe de fato em produção.

---

## 15. Histórico de mudanças importantes

### 30/06/2026 — Deploy CC #7: migration `0004` (coorte acima de turma) em produção

- **Entidade `coorte`** nasce ACIMA de `turma` (a "turma-Insper" / grade fechada do `codigo_convite`). `turma` intacta em significado (classe-de-matéria, unidade do relatório). `matricula` repontada de `turma` → `coorte` (perde `turma_id`); `duvida` ganha `coorte_id NOT NULL` e `turma_id` vira NULLABLE (FK preservada).
- **Migration `0004_coorte_acima_de_turma.py`** (down_revision `0003`), aditiva, DDL à mão (sem autogenerate — não enxerga o índice UNIQUE parcial da 0003 e injetaria regressão). Padrão populado: coluna NOT NULL nova entra nullable → backfill → SET NOT NULL; `coorte` (vazia) nasce NOT NULL inline. Guarda `RAISE EXCEPTION` (aluno em >1 turma da mesma coorte) no up; guarda simétrica (>1 turma por coorte) no down.
- **Ritual da regra 15 cumprido:** um `pg_dump -Fc` de prod (via `DATABASE_PUBLIC_URL`, host `proxy.rlwy.net`) do estado 0003+seed — `~/.edubot/prod_backup_0003_seed_20260630.dump` — foi **provado por restore** num clone Postgres 18 descartável (`edubot_clone_ensaio`, porta 5433): **prova por contagem** (21 tabelas, `alembic_version='0003'`, função + 8 triggers `updated_at`, `coorte` ausente) e **ensaio up/down** da 0004 (upgrade `head` + `downgrade -1` limpos, backfill 1/41/104 batendo, guarda sem disparar). Só então produção. Cliente `pg_dump`/`psql` 18.4 (libpq); prod é PG 18.3.
- **Aplicação em produção (Opção B):** `alembic upgrade 0003:0004 --sql` offline gerou `deploy_0004.sql` (revisado à parte) → `psql "$URL" -v ON_ERROR_STOP=1 -f deploy_0004.sql`. Transação atômica, COMMIT limpo, sem ERROR, guarda não disparou. Verificado: 1 coorte, `coorte_id` sem NULL em turma/matricula/duvida, `matricula`=41, `duvida`=104, `alembic_version`='0004', `codigo_convite`='AUTO-…'. Backup pré-deploy (rede de rollback, tirado no minuto do deploy, **não** re-verificado por restore): `~/.edubot/prod_backup_0004_PRE_20260630_2228.dump`; SQL aplicado: `~/.edubot/deploy_0004.sql`.
- **Lição (Opção B):** o `BEGIN/COMMIT` e o `UPDATE alembic_version` vêm do próprio Alembic no `--sql` offline — não escrever à mão. Range `0003:0004` só offline; online usa `upgrade head`.
- **Higiene do segredo:** a `DATABASE_PUBLIC_URL` foi lida via `$(cat ~/.edubot/.prod_url)`, nunca ecoada, e `shred -u` ao fim; nenhum arquivo em `~/.edubot/` contém a URL. Deploy do Railway roda só `uvicorn` (sem Alembic) — bloqueio incondicional do `env.py` contra Railway intacto.
- **Commit:** ver `git log` (mudança de código + este doc no mesmo commit). `seed_demo_fin2.py` deliberadamente FORA do commit — adaptação ao schema coorte é revisão própria (ver §11).

### 18/06/2026 — Deploy CC #6: migration 0003 em produção + rota `/r/{token}` viva (sessões A/B/C/D)

- **Commit `3fcd947` em `origin/main`** (saiu de `0c1426c`): 13 arquivos da CC #6 (migration 0003, `relatorio_gen.py`, rota + templates, seed, ligações no agregador, `database.py`, `requirements.txt`, `CLAUDE.md`). `.claude/` adicionado ao `.gitignore`.
- **Nome real de professor removido** do seed antes do deploy (era contato real do Insper): `nome="Exemplo"`, arquivo renomeado `seed_demo_fin2_ermel.py` → `seed_demo_fin2.py`, refs no CLAUDE.md ajustadas. Decisão de produto: não usar nome de pessoa real em dado de demo fabricado em produção.
- **Migration `0003` aplicada em produção** via Opção B (SQL manual atômico, `~/.edubot/0003.sql`): `ALTER TABLE relatorio ADD COLUMN prosa_acao TEXT` + `DROP INDEX` do normal + `CREATE UNIQUE INDEX ... WHERE whatsapp_message_id IS NOT NULL` + `UPDATE alembic_version='0003'`. Exit 0, COMMIT. Validado: coluna text/null, índice UNIQUE parcial, `alembic_version='0003'`, Camada 1+2 intactas dado-a-dado.
- **Ritual da regra 15 cumprido:** `pg_dump -Fc` da prod (via `DATABASE_PUBLIC_URL`, host proxy.rlwy.net — a URL interna `.railway.internal` não resolve local) → restore num clone Postgres 18 descartável → **prova por contagem** (20 tabelas idênticas prod vs clone) → ensaio da 0003 no clone (limpo) → produção. **Sem duplicatas de `whatsapp_message_id`** (o risco do UNIQUE parcial foi descartado por SELECT). `ROLLBACK_0003.md` escrito e aprovado; **Rota A do rollback provada por EXECUÇÃO no clone** (0003 → 0002 limpo).
- **Rota `/r/{token}` viva em produção:** `https://edubot-production-073e.up.railway.app/r/{token}`. Deploy Railway ACTIVE (só `uvicorn`, sem Alembic — bloqueio do `env.py` intacto). Smoke test: relatório válido HTTP 200 (renderiza, 0 tags Jinja cruas, prosa do Sonnet), `/r/token-invalido` → "indisponível" 200 (não 500).
- **Seed rodado em produção** (decisão de produto aprovada): turma fictícia 4DPA + Prof. Exemplo + ~41 alunos + relatório real (pipeline Haiku+Sonnet ao vivo: 40 academicas, 39 casadas, curva 3→40). Token de prova vence **03/07/2026** — é prova de funcionamento, NÃO a URL final; **re-rodar o seed perto da demo de julho**.
- **Higiene:** `DATABASE_PUBLIC_URL` removida do disco ao fim; preservados `~/.edubot/{0003.sql, ROLLBACK_0003.md, prod_backup_0003_pre.dump}`.

### 18/06/2026 — Sessão CC #6: subconceito + prosa + rota `/r/{token}` + migration 0003 + seed de demo (build/teste LOCAL)

- **Nada commitado, nada em produção.** Todo o trabalho ficou no working tree, validado em `edubot_demo` (Postgres local). O deploy da `0003` + rota é sessão SEPARADA com o ritual da regra 15.
- **Migration `0003_prosa_acao_e_unique_wamid.py`** (down_revision `0002`): `relatorio.prosa_acao TEXT NULL` + **UNIQUE parcial** em `mensagem.whatsapp_message_id` substituindo o índice normal da `0002`. `upgrade`/`downgrade` limpos em banco descartável.
- **`app/services/relatorio_gen.py`** — `SubconceitoEngine` (Haiku, pós-agregação, conceito com volume ≥ 2, grava em `conteudo.academica.unidades[].conceitos[].subconceitos[]`, NULL honesto = lista vazia, contagens em Python, prompt por categoria de matéria) + `ProsaEngine` (Sonnet `claude-sonnet-4-6` via `PROSA_MODEL`, lê o conteúdo já enriquecido, falha graciosa → `None`). Texto bruto vai ao Haiku transitório, nunca persiste.
- **Ligado no agregador** (`processar_agregacao` + `_upsert_relatorio` gravam `prosa_acao`; `agregar.py` passa os engines). Engines default `None` preservam o comportamento da CC #5.
- **Rota `GET /r/{token}`** (`app/routers/relatorio.py` + `app/templates/`): Jinja2 server-side, Chart.js via CDN, token 14 dias, página "indisponível" via `TemplateResponse` (200) para inválido/expirado, gráfico só com semanas passadas. `main.py` registra o router.
- **Seed VERSIONÁVEL `seed_demo_fin2.py`** (Fin II · 4DPA · Prof. exemplo · ~41 alunos · plano fixo · idempotente · semana-ref 29/03-04/04). Não hardcoda subconceito/prosa — a pipeline real produz.
- **Validado ao vivo** (Haiku+Sonnet reais): 40 academicas/semana-ref, 39 casadas + 1 NULL honesto, subtemas com não-consolidação real ("5 alunos, 3 voltaram"), curva 3→40, página renderiza no nível de venda. SELECT bruto + screenshots auditados.
- **Diagnóstico registrado:** o painel "Launch preview" do harness serve o arquivo `.html` CRU (sem Jinja); a rota real (`TemplateResponse`) resolve as tags — provado por `curl` bruto (0 tags `{%`/`{{`). Não confundir painel de preview com a rota servida.

### 17/06/2026 — Deploy: migration 0002 em produção + rate limiting + push (sessões 2A/2B/2C)

- **Migration `0002` aplicada em produção** via SQL manual (Opção B), em 3 passos atômicos: `stamp 0001` → `CREATE OR REPLACE FUNCTION atualizar_updated_at()` → `0002.sql` (14 tabelas Camada 2 + 8 triggers + `UPDATE` versão → `'0002'`). Validado contra prod: 14 tabelas Camada 2 nascem, 6 da Camada 1 intactas (contagens idênticas), `alembic_version='0002'`. Smoke test do pipeline real (botão Test do painel Meta) → linha nova em `mensagem`.
- **Backup verificado via restore (Regra 15, comprovada):** `pg_dump -Fc` da prod restaurado num clone Postgres 18 descartável antes de tocar produção; plano de rollback escrito antes (`ROLLBACK_2b.md`).
- **Ensaio em clone (2A) pegou 2 defeitos antes da prod:** (1) o "stamp 0002" gerado por `alembic stamp 0002 --sql` recria `alembic_version` do zero → seria destrutivo aplicado após o `0002.sql`; removido da receita. (2) a função `atualizar_updated_at()` não existia em prod → triggers da `0002` falhariam; adicionada como passo 2.
- **Produção é PostgreSQL 18.3, não 16** (repo/docker-compose assumiam 16). Cliente de deploy: pg_dump/psql 18.4. Divergência dev (16) / prod (18.3) registrada pra alinhar.
- **Baseline `0001` diverge da prod real:** prod nasceu de `sql/schema.sql` à mão, não do Alembic — tem só `pgcrypto` + as 6 tabelas. A função, os 3 triggers da Camada 1 e as 2 views (`proximos_eventos`, `eventos_hoje`) da `0001` nunca chegaram à prod. Views vestigiais (sem uso no código); função criada no deploy; triggers seguem ausentes (§11). Originou a **Regra 16** (§14).
- **Rate limiting (Frente 3) deployado:** `slowapi==0.1.10`, `app/limiter.py` (teto global `300/min` em memória no `POST /webhook`, 200-no-estouro pro Meta). Commit `cb1ea24`. Testado local (360 req → 300 passam, 61 cortadas).
- **Push completo:** todos os commits locais (CC #1–#5 + docs + rate limiting) em `origin/main` (`cb1ea24`). Deploy Railway ACTIVE, boot limpo. **Confirmado:** o Railway não roda Alembic no deploy (só `uvicorn` via Procfile/nixpacks) — o bloqueio incondicional do `env.py` contra Railway segue intacto; migrations de prod são sempre manuais via Opção B.
- **Artefatos do deploy** preservados em `~/.edubot/` (dumps, SQLs da espinha, `ROLLBACK_2b.md`); a `DATABASE_URL` de prod foi removida do disco ao fim.

### 07/06/2026 — Sessão CC #5: agregador semanal de dúvidas
- **`app/services/agregador.py`** criado: `AgregadorEngine` (httpx + Haiku, espelha o classificador). Matching dúvida→conceito em lote (1 call/turma) + agregação da semana fechada num JSON estatístico gravado em `relatorio` via upsert idempotente
- **Decisão de produto:** relatório é ESTATÍSTICA AGREGADA PURA — nenhuma mensagem crua, nenhum telefone no `relatorio.conteudo`, só contagens. "não classificadas"/"organizacional" viram só volume/distribuição temporal. Razão: texto livre carrega risco de PII de terceiros
- **Decisões técnicas:** matching só toca `conceito_id IS NULL` (re-run estável, sem chute); `aula_id` por heurística de data (sem Haiku); consentimento via snapshot na própria dúvida (D1); janela domingo→sábado fechada em `America/Sao_Paulo`
- **`app/scripts/agregar.py`** — disparo manual (`python -m`), parâmetro de domingo de referência. Celery é CC #8
- **Validado em `edubot_test_cc5`** (recriado do zero): 6 cenários + idempotência (1 linha, token estável), com SELECT bruto do JSON auditado. 4 arquivos novos (`agregador.py`, `scripts/__init__.py`, `scripts/agregar.py`, seed descartável). Camada 1 e classificador intactos. Sem commit/push
- **Matching validado AO VIVO** (Haiku real, HTTP 200, key nova reposta no `.env`): 5 de 6 academicas casadas, "gráfico de barras no Excel" em NULL honesto (sem chute); WACC 4× / Risco-Retorno 1×; `aula_id` por data correto; consentimento=false e fora-da-janela não entraram. Relatório auditado por SELECT bruto do `relatorio.conteudo`

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
- **Validação de fidelidade contra produção** (exigida no chat, contra a fonte certa): rodar baseline em banco de teste só prova que executa, não que bate com produção. Adicionado passo de comparação estrutural contra o banco real do Railway. Dois defeitos `jsonb` (server_default com aspas escapadas em `conversa_sessao.mensagens/contexto` e `instituicao.contato_diretoria`) pegos no banco de teste descartável, corrigidos antes de qualquer toque em produção. Comparação campo a campo das 6 tabelas via console read-only do Railway (sem senha trafegando) — baseline confirmada fiel *(⚠️ revisado em 17/06: essa comparação cobriu apenas **tabelas/colunas** — NÃO funções, triggers nem views. O deploy de 17/06 revelou que a função `atualizar_updated_at()`, os 3 triggers e as 2 views da `0001` nunca existiram em prod. Ver entrada de 17/06, §11 e Regra 16 da §14.)*

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
