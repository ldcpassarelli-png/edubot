"""
EduBot — Seed de DEMO (Camada 2, CC #6). Finanças II · turma 4DPA · Prof. Exemplo.

ESTE ARQUIVO É VERSIONÁVEL — é um ativo de venda reproduzível, não dado real.
(O que vai pro .gitignore é dump de produção, não o seed de demo.)

O que ele faz: planta de forma DETERMINÍSTICA uma turma de Finanças II com ~9
semanas de dúvidas reais de aluno (PT informal, com abreviação e erro como aluno
escreve), volume crescente, com pico na semana de referência (pré-PI). NÃO usa o
parser de PDF — a estrutura do plano é fixa no código (demo tem que sair igual
toda vez).

O que ele NÃO faz: NÃO classifica conceito, NÃO extrai subconceito, NÃO escreve
prosa. Isso é trabalho da PIPELINE REAL (matching Haiku + subconceito Haiku +
prosa Sonnet), disparada depois pelo agregador. As dúvidas foram calibradas para
que, AO PASSAR pela pipeline, produzam os subtemas-alvo da semana de referência.

Idempotente: limpa as linhas da demo e refaz. Rodável quantas vezes quiser.

Uso (banco LOCAL, nunca produção):
    DATABASE_URL=postgresql+asyncpg://edubot:edubot@localhost:5432/edubot_demo \
        python -m app.scripts.seed_demo_fin2

Depois, gerar o relatório da semana de referência pela pipeline real:
    python -m app.scripts.agregar --data-ref 2026-04-05 --turma-id 4d000000-0000-4000-8000-000000000001
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import delete, select

from app.models.connection import async_session
from app.models.database import (
    Aula, Conceito, ConsentimentoCamada2, Curso, Duvida, Instituicao,
    Matricula, MateriaCamada2, Mensagem, PlanoDeAula, Professor,
    ProgressoTurma, Turma, UnidadeTematica,
)
from app.services.agregador import TZ

# ---- UUIDs fixos das entidades estruturais (estáveis p/ cleanup + agregar) ----
INST = uuid.UUID("4d000000-0000-4000-8000-0000000000a1")
CURSO = uuid.UUID("4d000000-0000-4000-8000-0000000000a2")
MATERIA = uuid.UUID("4d000000-0000-4000-8000-0000000000a3")
PROF = uuid.UUID("4d000000-0000-4000-8000-0000000000a4")
PLANO = uuid.UUID("4d000000-0000-4000-8000-0000000000a5")
TURMA = uuid.UUID("4d000000-0000-4000-8000-000000000001")
PROGRESSO = uuid.UUID("4d000000-0000-4000-8000-0000000000a6")

SEMESTRE = "2026.1"

# ---- 41 alunos; ~2/3 consentem (índice 1-based não divisível por 3) ----
ALUNOS = [f"+5511900{i:06d}" for i in range(1, 42)]   # +5511900000001 .. 041


def _consent(idx0: int) -> bool:
    """Aluno consente se a posição (1-based) não é múltiplo de 3 → ~68%."""
    return (idx0 + 1) % 3 != 0


# ============================================================
# Estrutura FIXA do plano de Finanças II (Bloco 1, 2, 3)
# ============================================================

# (nome da unidade, ordem, [conceitos...])
UNIDADES = [
    ("Teoria de Carteiras", 1, [
        "Retorno e risco de um ativo",
        "Retorno e risco de uma carteira de dois ativos",
        "Matriz de covariâncias",
        "Conjunto de possibilidades de investimento",
        "Carteira de risco ótima",
        "Utilidade do investidor",
        "Teorema da Separação",
    ]),
    ("Modelo de Índice Único", 2, [
        "Modelo de índice único",
        "Decomposição do risco (sistemático e específico)",
        "Simplificação da matriz de covariância",
        "Carteira ótima com parcela ativa e passiva",
    ]),
    ("Mercado Eficiente e Revisão", 3, [
        "Hipótese do mercado eficiente (três formas)",
        "Revisão para a Prova Intermediária",
    ]),
]

# (numero, data ISO, titulo)
AULAS = [
    (1, "2026-02-10", "Introdução: retorno e risco de um ativo"),
    (2, "2026-02-12", "Risco e retorno de carteira de dois ativos"),
    (3, "2026-02-17", "Matriz de covariâncias"),
    (4, "2026-02-19", "Conjunto de possibilidades de investimento"),
    (5, "2026-02-24", "Carteira de risco ótima"),
    (6, "2026-02-26", "Utilidade do investidor"),
    (7, "2026-03-05", "Teorema da Separação"),
    (8, "2026-03-10", "Modelo de índice único"),
    (9, "2026-03-12", "Decomposição do risco: sistemático e específico"),
    (10, "2026-03-17", "Simplificação da matriz de covariância"),
    (11, "2026-03-19", "Carteira ótima: parcela ativa e passiva"),
    (12, "2026-03-24", "Hipótese do mercado eficiente (três formas)"),
    (13, "2026-03-26", "Mercado eficiente: implicações"),
    (14, "2026-03-31", "Revisão para a Prova Intermediária"),
    (15, "2026-04-02", "Revisão: resolução de exercícios"),
    (16, "2026-04-07", "Prova Intermediária"),
]
AULA_PROGRESSO_NUMERO = 14   # turma está na revisão pré-PI

# ============================================================
# Dúvidas
# ============================================================
# A semana de referência (pré-PI) é a domingo 2026-03-29 .. sábado 2026-04-04.
# Dúvidas são datadas pelos dias úteis dessa semana (seg=30/03 .. sex=03/04).
# Cada tupla: (idx_aluno, categoria, texto, dia_offset_desde_domingo, hora).

REF_DOMINGO = date(2026, 3, 29)

# --- Semana de referência (PICO pré-PI, alta densidade ~40 dúvidas) ---
# Subtemas-alvo com volume real de turma densa + não-consolidação forte (vários
# alunos reincidentes no mesmo subtema → o vermelho do relatório ganha peso).
# Autores são todos consententes (idx % 3 != 2); idx 2 entra só pra provar exclusão.
REF_DUVIDAS = [
    # === Decomposição do risco · subtema "por que decompor" (5 alunos, 3 voltaram) ===
    (0, "academica", "pq separa risco em sistematico e especifico? qual a utilidade disso", 1, 10),
    (0, "academica", "voltando: ainda nao entendi por que decompor o risco em duas partes", 3, 14),   # reincidente
    (1, "academica", "qual a vantagem de dividir o risco em sistematico e nao sistematico?", 1, 11),
    (1, "academica", "de novo sobre decompor risco, nao consegui ver pq isso ajuda", 4, 9),   # reincidente
    (3, "academica", "porque a gente separa o risco em dois tipos mesmo?", 2, 9),
    (3, "academica", "fiquei na duvida de novo: pra que serve decompor o risco?", 4, 16),   # reincidente
    (4, "academica", "nao entendi o motivo de separar risco sistematico e especifico", 2, 13),
    (6, "academica", "qual o sentido de quebrar o risco em sistematico e especifico?", 3, 11),
    # === Beta na prática (5 alunos, 3 voltaram) ===
    (7, "academica", "o beta mede oq na pratica? a formula eu sei mas nao a intuiçao", 1, 14),
    (7, "academica", "voltei no beta, ainda nao entendi o que ele significa no mundo real", 3, 10),   # reincidente
    (9, "academica", "intuiçao do beta? oq quer dizer um beta 1.3 na real", 2, 16),
    (9, "academica", "de novo o beta, fiquei perdido no que ele representa", 4, 11),   # reincidente
    (10, "academica", "beta alto significa oq sobre a açao?", 1, 12),
    (10, "academica", "voltando ao beta, ele é so risco de mercado?", 4, 15),   # reincidente
    (12, "academica", "o que o beta de uma açao diz na pratica?", 2, 10),
    (13, "academica", "como interpreto o beta de um ativo?", 3, 13),
    # === Simplificação da matriz de covariância (6 alunos, 2 voltaram) ===
    (15, "academica", "pq o indice unico simplifica a matriz de covariancia?", 1, 9),
    (15, "academica", "voltei na covariancia com indice unico, ainda me perco", 4, 14),   # reincidente
    (16, "academica", "como o indice unico reduz as contas da covariancia?", 2, 11),
    (16, "academica", "de novo, pq nao precisa calcular a matriz toda com indice unico?", 4, 16),   # reincidente
    (18, "academica", "qual a vantagem do indice unico pra covariancia?", 1, 13),
    (19, "academica", "porque com indice unico a covariancia fica mais facil?", 2, 9),
    (21, "academica", "indice unico simplifica a covariancia como exatamente?", 3, 10),
    (22, "academica", "nao entendi a simplificaçao da matriz com indice unico", 3, 15),
    # === Carteira ótima parcela ativa/passiva (5 alunos, 1 voltou) ===
    (24, "academica", "qual a diferença entre parcela ativa e passiva da carteira?", 1, 10),
    (24, "academica", "voltando: ainda confuso em parcela ativa vs passiva", 4, 12),   # reincidente
    (25, "academica", "nao entendi parcela ativa e passiva da carteira otima", 2, 11),
    (27, "academica", "a parte ativa e a passiva, oq muda na pratica?", 2, 15),
    (28, "academica", "quando uso parcela ativa e quando passiva?", 3, 9),
    (30, "academica", "diferença entre componente ativo e passivo da carteira?", 3, 14),
    # === Mercado eficiente · três formas se confundem (6 alunos, 2 voltaram) ===
    (31, "academica", "as 3 formas de mercado eficiente (fraca semiforte forte) se misturam na minha cabeça", 1, 13),
    (31, "academica", "voltei nas formas de eficiencia, ainda confundo fraca e semiforte", 4, 10),   # reincidente
    (33, "academica", "diferença entre eficiencia fraca e semiforte?", 2, 11),
    (33, "academica", "de novo as tres formas, nao consigo separar forte de semiforte", 4, 9),   # reincidente
    (34, "academica", "nao consigo separar as tres formas de eficiencia de mercado", 2, 15),
    (36, "academica", "forma forte do mercado eficiente é qual mesmo?", 3, 10),
    (37, "academica", "semiforte inclui informaçao publica e a fraca nao?", 3, 13),
    (39, "academica", "qual a diferença pratica entre as tres formas de eficiencia?", 5, 9),
    # === NULL honesto: fora dos conceitos do plano (CAPM/otimização são pós-PI) ===
    (1, "academica", "como o CAPM entra nisso tudo? acho que a gente ainda nao viu", 5, 12),
    (4, "academica", "fronteira eficiente tem relaçao com otimizaçao/programaçao linear?", 5, 13),
    # === Não-consentido (prova exclusão do agregado): conceito do plano, mas não conta ===
    (2, "academica", "o que é o teorema da separaçao mesmo?", 2, 9),
    # === Organizacional (bloco separado, sem matching) ===
    (10, "organizacional", "quando é a PI mesmo?", 1, 8),
    (13, "organizacional", "a PI vale quanto da nota final?", 2, 8),
    (15, "organizacional", "pode levar calculadora financeira na prova?", 3, 8),
    (1, "organizacional", "a PI cobre ate qual aula?", 4, 8),
    (24, "organizacional", "a prova é com consulta?", 5, 8),
]

# --- Histórico (volume crescente). (domingo_offset_semanas_antes, [(idx, texto)]) ---
# Só academicas; volume sobe semana a semana até o pico da referência.
HISTORICO = [
    (7, [  # 08-14/02 — Bloco 1 início
        (0, "como calcula o retorno esperado de um ativo?"),
        (3, "risco de um ativo é so o desvio padrao?"),
        (6, "diferença entre retorno esperado e retorno realizado?"),
    ]),
    (6, [  # 15-21/02
        (1, "como combina o risco de dois ativos numa carteira?"),
        (4, "a covariancia entre dois ativos mede oq?"),
        (7, "correlaçao negativa reduz o risco da carteira?"),
        (9, "pq a carteira de dois ativos pode ter risco menor que os ativos sozinhos?"),
    ]),
    (5, [  # 22-28/02
        (0, "o que é o conjunto de possibilidades de investimento?"),
        (3, "fronteira eficiente é a parte de cima do grafico?"),
        (6, "como acho a carteira de risco otima?"),
        (10, "a carteira otima é a de maior sharpe?"),
        (12, "porque escolher a carteira tangente?"),
    ]),
    (4, [  # 01-07/03
        (1, "como a utilidade do investidor entra na escolha da carteira?"),
        (4, "aversao ao risco muda a carteira escolhida?"),
        (7, "o que diz o teorema da separaçao?"),
        (9, "pq separa a decisao de investir do perfil do investidor?"),
        (13, "curva de indiferença é a utilidade?"),
        (15, "investidor mais avesso fica mais no ativo livre de risco?"),
    ]),
    (3, [  # 08-14/03 — Bloco 2 início
        (0, "o que é o modelo de indice unico?"),
        (3, "pq usar um indice de mercado como referencia?"),
        (6, "o indice unico substitui a matriz de covariancia?"),
        (10, "alfa e beta no modelo de indice unico, oq é cada um?"),
        (12, "o modelo de indice unico é o mesmo que o CAPM?"),
        (16, "porque o indice unico é mais pratico?"),
        (18, "o R quadrado do modelo de indice unico diz oq?"),
    ]),
    (2, [  # 15-21/03
        (0, "decompor risco em sistematico e especifico, como assim?"),
        (1, "risco especifico da pra diversificar e o sistematico nao?"),
        (3, "o beta é a medida do risco sistematico?"),
        (4, "como o indice unico estima o risco de um ativo?"),
        (6, "indice unico simplifica a covariancia como exatamente?"),
        (7, "alfa positivo quer dizer que o ativo bateu o indice?"),
        (9, "parcela ativa da carteira é a aposta no alfa?"),
        (10, "risco nao sistematico e risco especifico sao a mesma coisa?"),
        (12, "quando a parcela ativa vale a pena?"),
        (13, "a parcela passiva replica o indice de mercado?"),
        (15, "risco sistematico afeta todos os ativos igual?"),
        (18, "beta de uma carteira é a media dos betas?"),
        (21, "porque o risco especifico some na carteira diversificada?"),
    ]),
    (1, [  # 22-28/03 — Bloco 3 início (mercado eficiente)
        (0, "o que é a hipotese do mercado eficiente?"),
        (1, "as tres formas de eficiencia, quais sao?"),
        (3, "mercado eficiente quer dizer que nao da pra ganhar do mercado?"),
        (4, "forma fraca usa só os preços passados?"),
        (6, "ainda confuso na decomposiçao do risco, pode revisar?"),
        (7, "se o mercado é eficiente, analise tecnica nao serve?"),
        (9, "a covariancia com indice unico ainda me pega"),
        (10, "forma semiforte reage a noticia publica na hora?"),
        (12, "parcela ativa e passiva, qual a diferença mesmo?"),
        (13, "o que é anomalia de mercado entao?"),
        (15, "semiforte inclui informaçao publica?"),
        (16, "indice unico ainda me confunde na parte da covariancia"),
        (18, "forma forte inclui informaçao privada/insider?"),
        (19, "beta continua sendo risco sistematico no indice unico?"),
        (21, "como o mercado eficiente afeta a gestao ativa?"),
        (22, "a hipotese de mercado eficiente vale pra qualquer ativo?"),
        (24, "diferença pratica entre as tres formas de eficiencia?"),
        (25, "parcela ativa é apostar contra o mercado eficiente?"),
        (27, "como testar se um mercado é eficiente?"),
        (28, "forma forte existe na pratica?"),
    ]),
]


def _dia(domingo: date, offset: int, hora: int) -> datetime:
    d = domingo + timedelta(days=offset)
    return datetime(d.year, d.month, d.day, hora, 0, tzinfo=TZ)


async def _limpar(db) -> None:
    """Remove tudo da demo, em ordem segura de dependência. Idempotência."""
    await db.execute(delete(Duvida).where(Duvida.turma_id == TURMA))
    await db.execute(delete(Mensagem).where(Mensagem.aluno_telefone.in_(ALUNOS)))
    await db.execute(delete(ConsentimentoCamada2).where(ConsentimentoCamada2.aluno_telefone.in_(ALUNOS)))
    # relatorio é gerado pela pipeline; limpa se já houver de uma rodada anterior.
    from app.models.database import Relatorio
    await db.execute(delete(Relatorio).where(Relatorio.turma_id == TURMA))
    await db.execute(delete(Matricula).where(Matricula.turma_id == TURMA))
    await db.execute(delete(ProgressoTurma).where(ProgressoTurma.turma_id == TURMA))
    await db.execute(delete(Turma).where(Turma.id == TURMA))
    await db.execute(delete(Aula).where(Aula.plano_de_aula_id == PLANO))
    unidade_ids = (await db.execute(
        select(UnidadeTematica.id).where(UnidadeTematica.plano_de_aula_id == PLANO)
    )).scalars().all()
    if unidade_ids:
        await db.execute(delete(Conceito).where(Conceito.unidade_tematica_id.in_(unidade_ids)))
    await db.execute(delete(UnidadeTematica).where(UnidadeTematica.plano_de_aula_id == PLANO))
    await db.execute(delete(PlanoDeAula).where(PlanoDeAula.id == PLANO))
    await db.execute(delete(Professor).where(Professor.id == PROF))
    await db.execute(delete(MateriaCamada2).where(MateriaCamada2.id == MATERIA))
    await db.execute(delete(Curso).where(Curso.id == CURSO))
    await db.execute(delete(Instituicao).where(Instituicao.id == INST))
    await db.commit()


async def seed() -> None:
    # Os modelos da Camada 2 não têm relationship() (decisão CC #3): flush em
    # camadas de dependência garante que cada FK exista antes do filho.
    async with async_session() as db:
        await _limpar(db)

        # ---- institucional ----
        db.add(Instituicao(id=INST, nome="Insper"))
        await db.flush()
        db.add(Curso(id=CURSO, instituicao_id=INST, nome="Administração"))
        db.add(MateriaCamada2(
            id=MATERIA, instituicao_id=INST, nome="Finanças II",
            codigo="FIN2", categoria="financas",
        ))
        db.add(Professor(
            id=PROF, instituicao_id=INST, nome="Exemplo",
            telefone_whatsapp="+5511980000014",
        ))
        await db.flush()
        db.add(Turma(
            id=TURMA, materia_camada2_id=MATERIA, curso_id=CURSO,
            letra="4DPA", semestre=SEMESTRE, professor_id=PROF,
        ))
        await db.flush()

        # ---- taxonomia: plano → unidades → conceitos; aulas ----
        db.add(PlanoDeAula(id=PLANO, materia_camada2_id=MATERIA, semestre=SEMESTRE))
        await db.flush()
        for unome, uordem, conceitos in UNIDADES:
            u = UnidadeTematica(plano_de_aula_id=PLANO, nome=unome, ordem=uordem)
            db.add(u)
            await db.flush()
            for cordem, cnome in enumerate(conceitos, start=1):
                db.add(Conceito(unidade_tematica_id=u.id, nome=cnome, ordem=cordem))

        aula_por_numero = {}
        for numero, data_iso, titulo in AULAS:
            a = Aula(
                plano_de_aula_id=PLANO, numero=numero,
                data_prevista=date.fromisoformat(data_iso), titulo=titulo,
            )
            db.add(a)
            aula_por_numero[numero] = a
        await db.flush()

        # ---- progresso da turma (revisão pré-PI) ----
        db.add(ProgressoTurma(
            id=PROGRESSO, turma_id=TURMA,
            aula_atual_id=aula_por_numero[AULA_PROGRESSO_NUMERO].id,
            confirmado_pelo_professor=True,
        ))

        # ---- matrículas + consentimento dos 41 alunos ----
        for idx, tel in enumerate(ALUNOS):
            db.add(Matricula(turma_id=TURMA, aluno_telefone=tel, ativo=True))
            db.add(ConsentimentoCamada2(
                aluno_telefone=tel, versao_texto="v1", consentiu=_consent(idx),
                data_consentimento=_dia(REF_DOMINGO - timedelta(days=70), 0, 9),
                texto_aceito="Aceito participar do feedback pedagógico (demo)." if _consent(idx)
                else "Não autorizo o uso das minhas mensagens (demo).",
            ))
        await db.flush()

        # ---- dúvidas: mensagem (entrada) + duvida, sem conceito (pipeline casa) ----
        async def add_duvida(idx_aluno, categoria, texto, quando):
            tel = ALUNOS[idx_aluno]
            msg_id = uuid.uuid4()
            db.add(Mensagem(
                id=msg_id, aluno_telefone=tel, direcao="entrada",
                conteudo=texto, recebida_em=quando, created_at=quando,
            ))
            await db.flush()
            db.add(Duvida(
                mensagem_id=msg_id, turma_id=TURMA, categoria=categoria,
                texto_extraido=texto, consentimento_camada2=_consent(idx_aluno),
                aluno_telefone=tel, created_at=quando,
            ))

        # histórico (volume crescente)
        total_hist = 0
        for semanas_antes, duvidas in HISTORICO:
            domingo = REF_DOMINGO - timedelta(days=7 * semanas_antes)
            for j, (idx, texto) in enumerate(duvidas):
                dia_offset = 1 + (j % 5)   # espalha seg..sex
                await add_duvida(idx, "academica", texto, _dia(domingo, dia_offset, 9 + (j % 6)))
                total_hist += 1

        # semana de referência (pico)
        for idx, categoria, texto, offset, hora in REF_DUVIDAS:
            await add_duvida(idx, categoria, texto, _dia(REF_DOMINGO, offset, hora))

        await db.commit()

    consentem = sum(1 for i in range(len(ALUNOS)) if _consent(i))
    semana_fim = REF_DOMINGO + timedelta(days=6)
    print("Seed de demo OK — Finanças II · turma 4DPA · Prof. Exemplo")
    print(f"  Turma: {TURMA}")
    print(f"  Alunos: {len(ALUNOS)} ({consentem} consentem)")
    print(f"  Histórico: {total_hist} dúvidas em {len(HISTORICO)} semanas")
    print(f"  Semana de referência: {REF_DOMINGO} (dom) .. {semana_fim} (sáb)")
    print(f"  Próximo passo: python -m app.scripts.agregar --data-ref 2026-04-05 --turma-id {TURMA}")


if __name__ == "__main__":
    asyncio.run(seed())
