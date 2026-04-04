# 🎓 EduBot — Copiloto Acadêmico via WhatsApp

## O que é

EduBot recebe planos de aula dos alunos (texto, PDF ou foto) pelo WhatsApp, extrai automaticamente todas as datas e atividades, e passa a enviar notificações diárias e semanais para manter o aluno organizado.

## Setup rápido

### 1. Subir banco e Redis

```bash
docker compose up -d
```

Isso cria o PostgreSQL (com schema pronto) e Redis locais.

### 2. Instalar dependências

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 3. Configurar variáveis

```bash
cp .env.example .env
# Editar .env com sua ANTHROPIC_API_KEY
```

### 4. Rodar a API

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Testar o parser

```bash
curl -X POST http://localhost:8000/api/v1/parser/texto \
  -H "Content-Type: application/json" \
  -d '{"texto": "Finanças III\nAula 1 - 10/02\nProva - 24/02 peso 30%"}'
```

## Estrutura do projeto

```
edubot/
├── app/
│   ├── main.py              # FastAPI app principal
│   ├── models/
│   │   ├── database.py      # Modelos SQLAlchemy
│   │   └── connection.py    # Conexão async com PostgreSQL
│   ├── routers/
│   │   ├── parser.py        # Endpoints de parsing
│   │   ├── alunos.py        # CRUD alunos e eventos
│   │   └── webhook.py       # Webhook WhatsApp
│   └── services/
│       └── parser.py        # Engine de parsing (Claude Haiku)
├── sql/
│   └── schema.sql           # Schema PostgreSQL completo
├── docker-compose.yml        # PostgreSQL + Redis local
├── requirements.txt
├── .env.example
└── README.md
```

## API Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/v1/parser/texto` | Parseia plano de aula (texto) |
| POST | `/api/v1/parser/pdf` | Parseia plano de aula (PDF) |
| POST | `/api/v1/parser/imagem` | Parseia foto do plano |
| POST | `/api/v1/alunos` | Cria/busca aluno |
| POST | `/api/v1/alunos/{id}/materias` | Adiciona matéria + eventos |
| GET | `/api/v1/alunos/{id}/proximos-eventos` | Lista próximos eventos |
| GET | `/api/v1/alunos/{id}/eventos-hoje` | Eventos do dia |
| GET | `/webhook` | Verificação WhatsApp |
| POST | `/webhook` | Recebe mensagens WhatsApp |
| GET | `/health` | Health check |

## Docs interativos

Com o servidor rodando, acesse `http://localhost:8000/docs` para o Swagger UI completo.
