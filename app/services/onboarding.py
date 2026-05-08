"""
EduBot — Máquina de estados do onboarding do aluno.

Fluxo reativo (só responde quando aluno manda mensagem):

    NOVO
      → bot manda boas-vindas + pede nome
    AGUARDANDO_NOME
      → aluno manda texto (nome) → bot salva nome, pede PDF
    AGUARDANDO_PLANO
      → aluno manda PDF → baixa, parseia, mostra resumo, pede confirmação
      → aluno manda texto/imagem/outro → pede PDF gentilmente
    AGUARDANDO_CONFIRMACAO_PLANO
      → aluno responde SIM → salva no banco, pergunta se quer mais matéria
      → aluno responde NÃO → descarta parse, volta pra AGUARDANDO_PLANO
    AGUARDANDO_MAIS_MATERIAS
      → aluno responde SIM → volta pra AGUARDANDO_PLANO (pede próximo PDF)
      → aluno responde NÃO → vai pra ATIVO (onboarding completo)
    ATIVO
      → por enquanto responde "Em breve novidades" (chat e notificações ficam
        pra próximas sessões)

Estado é persistido em ConversaSessao.contexto (JSON). Nenhuma alteração de
schema é necessária.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Aluno, Materia, EventoAcademico, ConversaSessao
from app.services.parser import ParserEngine, PlanoExtraido
from app.services import whatsapp

logger = logging.getLogger("edubot.onboarding")


# ============================================================
# Estados
# ============================================================

ESTADO_NOVO = "NOVO"
ESTADO_AGUARDANDO_NOME = "AGUARDANDO_NOME"
ESTADO_AGUARDANDO_PLANO = "AGUARDANDO_PLANO"
ESTADO_AGUARDANDO_CONFIRMACAO = "AGUARDANDO_CONFIRMACAO_PLANO"
ESTADO_AGUARDANDO_MAIS_MATERIAS = "AGUARDANDO_MAIS_MATERIAS"
ESTADO_ATIVO = "ATIVO"


# ============================================================
# Helpers — interpretação de SIM/NÃO
# ============================================================

_PALAVRAS_SIM = {
    "sim", "s", "yes", "y",
    "quero", "claro", "beleza", "blz",
    "ok", "okay", "pode",
    "confirma", "confirmo", "confirmar",
    "vai", "bora", "vamos",
    "positivo", "afirmativo",
}

_PALAVRAS_NAO = {
    "não", "nao", "n", "no",
    "nope", "nunca", "negativo",
    "nem", "jamais",
    "rejeita", "rejeitar",
    "cancela", "cancelar",
    "refaz", "refazer",
}


def _eh_sim(texto: str) -> bool:
    """Reconhece afirmações generosamente (SIM, S, Quero, Claro, Beleza, etc.)."""
    if not texto:
        return False
    t = texto.strip().lower().rstrip("!.?")
    return t in _PALAVRAS_SIM


def _eh_nao(texto: str) -> bool:
    """Reconhece negações generosamente."""
    if not texto:
        return False
    t = texto.strip().lower().rstrip("!.?")
    return t in _PALAVRAS_NAO


# ============================================================
# Helpers — acesso ao banco
# ============================================================

async def _buscar_ou_criar_aluno(telefone: str, db: AsyncSession) -> Aluno:
    """Busca aluno pelo telefone ou cria um novo sem nome ainda."""
    result = await db.execute(
        select(Aluno).where(Aluno.telefone_whatsapp == telefone)
    )
    aluno = result.scalar_one_or_none()

    if aluno is None:
        aluno = Aluno(telefone_whatsapp=telefone)
        db.add(aluno)
        await db.flush()  # garante que aluno.id existe pra relacionamentos
        logger.info(f"✨ Novo aluno criado: {telefone}")

    return aluno


async def _buscar_ou_criar_sessao(aluno: Aluno, db: AsyncSession) -> ConversaSessao:
    """Busca sessão do aluno ou cria uma nova com estado NOVO."""
    result = await db.execute(
        select(ConversaSessao).where(ConversaSessao.aluno_id == aluno.id)
    )
    sessao = result.scalar_one_or_none()

    if sessao is None:
        sessao = ConversaSessao(
            aluno_id=aluno.id,
            mensagens=[],
            contexto={"estado": ESTADO_NOVO},
        )
        db.add(sessao)
        await db.flush()
        logger.info(f"💬 Nova sessão criada para aluno {aluno.id}")

    # Garante que contexto tem pelo menos a chave "estado"
    if not sessao.contexto or "estado" not in sessao.contexto:
        sessao.contexto = {"estado": ESTADO_NOVO}

    return sessao


async def _salvar_materia(
    aluno: Aluno,
    plano: PlanoExtraido,
    db: AsyncSession,
) -> Materia:
    """Persiste uma matéria e seus eventos no banco."""
    from datetime import date

    materia = Materia(
        aluno_id=aluno.id,
        nome=plano.materia,
        professor=plano.professor,
        semestre=plano.semestre,
        fonte="whatsapp_pdf",
        dados_extraidos=plano.model_dump(exclude={"raw_response"}),
    )
    db.add(materia)
    await db.flush()  # pra conseguir materia.id

    eventos_salvos = 0
    for ev in plano.eventos:
        try:
            data_evento = date.fromisoformat(ev.data)
        except (ValueError, TypeError):
            logger.warning(f"Data inválida no evento: {ev.data} — pulando")
            continue

        evento_db = EventoAcademico(
            materia_id=materia.id,
            data=data_evento,
            tipo=ev.tipo,
            titulo=ev.titulo,
            descricao=ev.descricao,
            material_leitura=ev.material_leitura,
            peso_nota=ev.peso_nota,
            urgencia=ev.urgencia,
        )
        db.add(evento_db)
        eventos_salvos += 1

    logger.info(
        f"💾 Matéria '{plano.materia}' salva para aluno {aluno.id} "
        f"({eventos_salvos}/{len(plano.eventos)} eventos)"
    )
    return materia


def _atualizar_contexto(sessao: ConversaSessao, **updates) -> None:
    """
    Atualiza contexto da sessão preservando valores existentes.

    Importante: SQLAlchemy + JSON mutável no Postgres exige reatribuir o dict
    pra marcar como dirty. Por isso fazemos `sessao.contexto = {**sessao.contexto, ...}`.
    """
    novo_contexto = dict(sessao.contexto or {})
    novo_contexto.update(updates)
    sessao.contexto = novo_contexto


# ============================================================
# Handlers por estado
# ============================================================

async def _handler_novo(aluno: Aluno, sessao: ConversaSessao) -> str:
    """Primeira mensagem do aluno. Manda boas-vindas e pede nome."""
    _atualizar_contexto(sessao, estado=ESTADO_AGUARDANDO_NOME)
    return (
        "Olá! 👋 Eu sou o EduBot, seu copiloto acadêmico.\n\n"
        "Vou te ajudar a não esquecer provas, trabalhos e prazos das suas matérias.\n\n"
        "Pra começar, como você se chama?"
    )


async def _handler_aguardando_nome(
    aluno: Aluno,
    sessao: ConversaSessao,
    texto: str,
) -> str:
    """Aluno respondeu o nome. Salva e pede o primeiro PDF."""
    nome = (texto or "").strip()

    # Validação gentil: pelo menos 2 caracteres, não só espaços/símbolos
    if len(nome) < 2 or not any(c.isalpha() for c in nome):
        return (
            "Hmm, não entendi seu nome. 🤔\n"
            "Pode me mandar só seu primeiro nome? Ex: 'Leonardo'"
        )

    # Trunca pra caber no banco (String 255) e pega primeiro nome pra tratamento informal
    nome = nome[:255]
    primeiro_nome = nome.split()[0] if nome else "aluno"

    aluno.nome = nome
    _atualizar_contexto(
        sessao,
        estado=ESTADO_AGUARDANDO_PLANO,
        primeiro_nome=primeiro_nome,
    )

    return (
        f"Prazer, {primeiro_nome}! 🎓\n\n"
        "Agora preciso do plano de aula de uma das suas matérias.\n\n"
        "📎 Me manda o *PDF* do plano (você pode baixar do portal da faculdade "
        "e anexar aqui no WhatsApp).\n\n"
        "_Por enquanto só aceito PDF — em breve texto e imagem também._"
    )


async def _handler_aguardando_plano(
    aluno: Aluno,
    sessao: ConversaSessao,
    tipo: str,
    conteudo: dict,
    parser: ParserEngine,
) -> str:
    """
    Aluno deve mandar PDF aqui.
    - PDF: baixa, parseia, mostra resumo, vai pra AGUARDANDO_CONFIRMACAO.
    - Qualquer outra coisa: pede PDF gentilmente, mantém estado.
    """
    primeiro_nome = sessao.contexto.get("primeiro_nome", "")

    # Caso feliz: chegou um PDF
    if tipo == "document" and "pdf" in conteudo.get("mime_type", "").lower():
        media_id = conteudo.get("media_id", "")
        resultado_download = await whatsapp.baixar_midia(media_id)

        if resultado_download is None:
            return (
                "Tive um problema pra baixar seu PDF. 😕\n"
                "Pode mandar de novo?"
            )

        pdf_bytes, _ = resultado_download
        resultado = await parser.parsear_pdf(pdf_bytes)

        if not resultado.sucesso or resultado.dados is None:
            logger.warning(
                f"Parser falhou pra aluno {aluno.id}: {resultado.erro}"
            )
            return (
                "Não consegui entender esse PDF. 😕\n"
                "Será que você pode tentar com outro arquivo? "
                "Ou me mandar esse mesmo de novo?"
            )

        # Guarda o plano parseado em JSON no contexto pra confirmar depois
        plano = resultado.dados
        plano_dict = plano.model_dump(exclude={"raw_response"})

        _atualizar_contexto(
            sessao,
            estado=ESTADO_AGUARDANDO_CONFIRMACAO,
            plano_pendente=plano_dict,
        )

        resumo = parser.gerar_resumo_confirmacao(plano)
        return resumo

    # Caso: aluno mandou texto quando deveria mandar PDF
    if tipo == "text":
        return (
            "Ainda preciso do *PDF* do plano de aula. 📎\n"
            "Pode mandar o arquivo aqui no WhatsApp?"
        )

    # Caso: imagem, áudio, sticker, etc.
    return (
        "Por enquanto só consigo ler *PDF*. 📎\n"
        "Pode me mandar o plano de aula como arquivo PDF?"
    )


async def _handler_aguardando_confirmacao(
    aluno: Aluno,
    sessao: ConversaSessao,
    texto: str,
    db: AsyncSession,
) -> str:
    """Aluno deve responder SIM (salvar) ou NÃO (descartar e pedir outro PDF)."""
    primeiro_nome = sessao.contexto.get("primeiro_nome", "")

    if _eh_sim(texto):
        plano_dict = sessao.contexto.get("plano_pendente")
        if not plano_dict:
            # Segurança: estado inconsistente, volta pro início do fluxo
            logger.error(f"Estado inconsistente pra aluno {aluno.id}: sem plano_pendente")
            _atualizar_contexto(sessao, estado=ESTADO_AGUARDANDO_PLANO, plano_pendente=None)
            return (
                "Ops, perdi o plano anterior. 😕\n"
                "Pode me mandar o PDF de novo?"
            )

        # Reconstrói PlanoExtraido a partir do dict salvo
        try:
            plano = PlanoExtraido(**plano_dict)
        except Exception as e:
            logger.error(f"Falha ao reconstruir plano pra aluno {aluno.id}: {e}")
            _atualizar_contexto(sessao, estado=ESTADO_AGUARDANDO_PLANO, plano_pendente=None)
            return "Ops, algo deu errado. Pode me mandar o PDF de novo?"

        await _salvar_materia(aluno, plano, db)

        _atualizar_contexto(
            sessao,
            estado=ESTADO_AGUARDANDO_MAIS_MATERIAS,
            plano_pendente=None,
        )
        return (
            f"Salvo! ✅\n\n"
            f"Quer adicionar outra matéria? (sim/não)"
        )

    if _eh_nao(texto):
        _atualizar_contexto(
            sessao,
            estado=ESTADO_AGUARDANDO_PLANO,
            plano_pendente=None,
        )
        return (
            "Beleza, vamos tentar de novo. 🔄\n"
            "Me manda o PDF do plano da matéria."
        )

    # Resposta ambígua — reperguntar
    return (
        "Não entendi. 🤔\n"
        "Tá certo o que eu achei no PDF? Responde *sim* pra salvar ou *não* pra refazer."
    )


async def _handler_aguardando_mais_materias(
    aluno: Aluno,
    sessao: ConversaSessao,
    texto: str,
) -> str:
    """Aluno decide se adiciona outra matéria ou finaliza onboarding."""
    primeiro_nome = sessao.contexto.get("primeiro_nome", aluno.nome or "")

    if _eh_sim(texto):
        _atualizar_contexto(sessao, estado=ESTADO_AGUARDANDO_PLANO)
        return (
            "Beleza! 🎯\n"
            "Me manda o PDF do plano da próxima matéria."
        )

    if _eh_nao(texto):
        aluno.onboarding_completo = True
        _atualizar_contexto(sessao, estado=ESTADO_ATIVO)
        nome_saudacao = primeiro_nome or "aluno"
        return (
            f"Perfeito, {nome_saudacao}! 🎉\n\n"
            "Seu EduBot tá pronto. Em breve você vai começar a receber "
            "lembretes das suas provas e entregas.\n\n"
            "_Notificações diárias e semanais entram no ar em breve._ ⏰"
        )

    return (
        "Não entendi. 🤔\n"
        "Quer adicionar mais uma matéria? Responde *sim* ou *não*."
    )


async def _handler_ativo(aluno: Aluno, sessao: ConversaSessao) -> str:
    """Onboarding completo. Chat interativo e notificações vêm em sessões futuras."""
    primeiro_nome = sessao.contexto.get("primeiro_nome", aluno.nome or "")
    saudacao = f", {primeiro_nome}" if primeiro_nome else ""
    return (
        f"Oi{saudacao}! 👋\n\n"
        "Seu cadastro tá completo. Em breve vou começar a te mandar lembretes "
        "das suas provas e entregas automaticamente. ⏰\n\n"
        "_Chat e notificações estão a caminho nas próximas atualizações._"
    )


# ============================================================
# Entry point — roteamento por estado
# ============================================================

async def processar_mensagem(
    telefone: str,
    tipo: str,
    conteudo: dict,
    parser: ParserEngine,
    db: AsyncSession,
) -> Optional[str]:
    """
    Processa uma mensagem recebida e retorna o texto de resposta a enviar.

    Args:
        telefone: número do aluno (ex: "5511999999999")
        tipo: "text" | "document" | "image" | outros tipos do WhatsApp
        conteudo: dict com dados específicos do tipo:
                  - text:     {"texto": "..."}
                  - document: {"media_id": "...", "mime_type": "application/pdf"}
                  - image:    {"media_id": "...", "mime_type": "image/jpeg"}
        parser: instância do ParserEngine (já inicializada em app.state.parser)
        db: sessão do banco (commit é feito automaticamente pelo get_db)

    Returns:
        Texto a enviar ao aluno, ou None se nada a responder.
    """
    aluno = await _buscar_ou_criar_aluno(telefone, db)
    sessao = await _buscar_ou_criar_sessao(aluno, db)

    estado = sessao.contexto.get("estado", ESTADO_NOVO)
    logger.info(
        f"🔀 Processando msg de {telefone}: estado={estado}, tipo={tipo}"
    )

    # Roteamento por estado
    if estado == ESTADO_NOVO:
        return await _handler_novo(aluno, sessao)

    if estado == ESTADO_AGUARDANDO_NOME:
        if tipo != "text":
            return (
                "Pode me mandar seu nome em texto, por favor? 🙂"
            )
        texto = conteudo.get("texto", "")
        return await _handler_aguardando_nome(aluno, sessao, texto)

    if estado == ESTADO_AGUARDANDO_PLANO:
        return await _handler_aguardando_plano(
            aluno, sessao, tipo, conteudo, parser
        )

    if estado == ESTADO_AGUARDANDO_CONFIRMACAO:
        if tipo != "text":
            return (
                "Antes de continuar, me responde se o resumo tá certo: "
                "*sim* pra salvar ou *não* pra refazer."
            )
        texto = conteudo.get("texto", "")
        return await _handler_aguardando_confirmacao(aluno, sessao, texto, db)

    if estado == ESTADO_AGUARDANDO_MAIS_MATERIAS:
        if tipo != "text":
            return (
                "Quer adicionar mais uma matéria? Responde *sim* ou *não*."
            )
        texto = conteudo.get("texto", "")
        return await _handler_aguardando_mais_materias(aluno, sessao, texto)

    if estado == ESTADO_ATIVO:
        return await _handler_ativo(aluno, sessao)

    # Segurança: estado desconhecido, reinicia fluxo
    logger.warning(
        f"Estado desconhecido '{estado}' para aluno {aluno.id} — reiniciando fluxo."
    )
    _atualizar_contexto(sessao, estado=ESTADO_NOVO)
    return await _handler_novo(aluno, sessao)
