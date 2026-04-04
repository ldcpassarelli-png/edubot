-- ============================================================
-- EduBot — Schema do Banco de Dados (PostgreSQL)
-- Versão: MVP Sprint 1
-- ============================================================

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ============================================================
-- TABELA: instituicao
-- Faculdade/universidade cliente (B2B)
-- ============================================================
CREATE TABLE instituicao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome VARCHAR(255) NOT NULL,
    dominio_email VARCHAR(255),           -- ex: "insper.edu.br"
    plano VARCHAR(50) DEFAULT 'trial',    -- trial | basico | premium
    max_alunos INTEGER DEFAULT 50,
    contato_diretoria JSONB DEFAULT '{}', -- nome, email, cargo
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- TABELA: aluno
-- Usuário final que interage pelo WhatsApp
-- ============================================================
CREATE TABLE aluno (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome VARCHAR(255),
    telefone_whatsapp VARCHAR(20) UNIQUE NOT NULL, -- formato: 5511999999999
    instituicao_id UUID REFERENCES instituicao(id) ON DELETE SET NULL,
    timezone VARCHAR(50) DEFAULT 'America/Sao_Paulo',
    horario_notificacao_diaria TIME DEFAULT '07:00',
    dia_resumo_semanal VARCHAR(10) DEFAULT 'sexta', -- sexta | sabado
    onboarding_completo BOOLEAN DEFAULT false,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_aluno_telefone ON aluno(telefone_whatsapp);
CREATE INDEX idx_aluno_instituicao ON aluno(instituicao_id);
CREATE INDEX idx_aluno_ativo ON aluno(ativo) WHERE ativo = true;

-- ============================================================
-- TABELA: materia
-- Disciplina acadêmica do aluno
-- ============================================================
CREATE TABLE materia (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aluno_id UUID NOT NULL REFERENCES aluno(id) ON DELETE CASCADE,
    nome VARCHAR(255) NOT NULL,               -- ex: "Finanças III"
    professor VARCHAR(255),
    semestre VARCHAR(20),                      -- ex: "2025.1"
    fonte VARCHAR(50) DEFAULT 'manual',        -- manual | blackboard | pdf | foto
    blackboard_course_id VARCHAR(255),         -- para integração futura
    raw_plan_url TEXT,                          -- URL do arquivo original no S3
    dados_extraidos JSONB,                     -- JSON bruto retornado pelo parser
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_materia_aluno ON materia(aluno_id);

-- ============================================================
-- TABELA: evento_academico
-- Cada item do cronograma: prova, quiz, case, entrega, aula...
-- ============================================================
CREATE TABLE evento_academico (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    materia_id UUID NOT NULL REFERENCES materia(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    tipo VARCHAR(50) NOT NULL,                -- prova | quiz | case | trabalho | seminario | aula | leitura
    titulo VARCHAR(500) NOT NULL,
    descricao TEXT,
    material_leitura TEXT,                     -- leitura obrigatória associada
    peso_nota VARCHAR(50),                    -- ex: "30% da nota final"
    urgencia VARCHAR(10) DEFAULT 'baixa',     -- alta | media | baixa
    notificado_diario BOOLEAN DEFAULT false,
    notificado_semanal BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_evento_materia ON evento_academico(materia_id);
CREATE INDEX idx_evento_data ON evento_academico(data);
CREATE INDEX idx_evento_tipo ON evento_academico(tipo);
-- Índice composto para queries de notificação
CREATE INDEX idx_evento_notificacao_diaria
    ON evento_academico(data, notificado_diario)
    WHERE notificado_diario = false;

-- ============================================================
-- TABELA: notificacao_log
-- Registro de todas as mensagens enviadas
-- ============================================================
CREATE TABLE notificacao_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aluno_id UUID NOT NULL REFERENCES aluno(id) ON DELETE CASCADE,
    tipo VARCHAR(20) NOT NULL,                -- diaria | semanal | lembrete | resposta | onboarding
    conteudo TEXT NOT NULL,
    enviado_em TIMESTAMPTZ DEFAULT now(),
    status VARCHAR(20) DEFAULT 'enviado',     -- enviado | entregue | lido | erro
    whatsapp_message_id VARCHAR(255),
    erro_detalhes TEXT
);

CREATE INDEX idx_notificacao_aluno ON notificacao_log(aluno_id);
CREATE INDEX idx_notificacao_enviado ON notificacao_log(enviado_em);

-- ============================================================
-- TABELA: conversa_sessao
-- Contexto de conversa para o chat interativo
-- ============================================================
CREATE TABLE conversa_sessao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aluno_id UUID NOT NULL REFERENCES aluno(id) ON DELETE CASCADE,
    mensagens JSONB DEFAULT '[]'::jsonb,      -- histórico recente da conversa
    contexto JSONB DEFAULT '{}'::jsonb,       -- estado atual (matéria ativa, etc)
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_conversa_aluno ON conversa_sessao(aluno_id);

-- ============================================================
-- VIEW: proximos_eventos
-- Eventos dos próximos 7 dias para notificações
-- ============================================================
CREATE OR REPLACE VIEW proximos_eventos AS
SELECT
    e.id AS evento_id,
    e.data,
    e.tipo,
    e.titulo,
    e.descricao,
    e.material_leitura,
    e.peso_nota,
    e.urgencia,
    m.nome AS materia_nome,
    m.professor,
    a.id AS aluno_id,
    a.nome AS aluno_nome,
    a.telefone_whatsapp,
    a.horario_notificacao_diaria,
    (e.data - CURRENT_DATE) AS dias_restantes
FROM evento_academico e
JOIN materia m ON e.materia_id = m.id
JOIN aluno a ON m.aluno_id = a.id
WHERE e.data >= CURRENT_DATE
  AND e.data <= CURRENT_DATE + INTERVAL '7 days'
  AND a.ativo = true
ORDER BY e.data ASC, e.urgencia DESC;

-- ============================================================
-- VIEW: eventos_hoje
-- Eventos de hoje para notificação diária matinal
-- ============================================================
CREATE OR REPLACE VIEW eventos_hoje AS
SELECT
    e.id AS evento_id,
    e.data,
    e.tipo,
    e.titulo,
    e.descricao,
    e.material_leitura,
    e.peso_nota,
    e.urgencia,
    m.nome AS materia_nome,
    a.id AS aluno_id,
    a.telefone_whatsapp,
    a.horario_notificacao_diaria
FROM evento_academico e
JOIN materia m ON e.materia_id = m.id
JOIN aluno a ON m.aluno_id = a.id
WHERE e.data = CURRENT_DATE
  AND a.ativo = true
  AND e.notificado_diario = false
ORDER BY a.id, e.urgencia DESC;

-- ============================================================
-- FUNÇÃO: atualizar_updated_at
-- Trigger para manter updated_at atualizado
-- ============================================================
CREATE OR REPLACE FUNCTION atualizar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_aluno_updated
    BEFORE UPDATE ON aluno
    FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();

CREATE TRIGGER trg_materia_updated
    BEFORE UPDATE ON materia
    FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();

CREATE TRIGGER trg_conversa_updated
    BEFORE UPDATE ON conversa_sessao
    FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();
