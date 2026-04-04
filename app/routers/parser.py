"""
EduBot — Router de parsing de planos de aula
Endpoints para receber texto, PDF ou imagem e retornar dados estruturados.
"""

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


# ============================================================
# Schemas de request/response
# ============================================================

class ParseTextoRequest(BaseModel):
    """Request para parsing de texto."""
    texto: str
    aluno_id: Optional[str] = None


class EventoResponse(BaseModel):
    data: str
    tipo: str
    titulo: str
    descricao: Optional[str] = None
    material_leitura: Optional[str] = None
    peso_nota: Optional[str] = None
    urgencia: str = "baixa"


class ParseResponse(BaseModel):
    """Response do parsing."""
    sucesso: bool
    materia: Optional[str] = None
    professor: Optional[str] = None
    semestre: Optional[str] = None
    eventos: list[EventoResponse] = []
    resumo_confirmacao: Optional[str] = None
    tempo_ms: int = 0
    tokens: int = 0
    erro: Optional[str] = None


# ============================================================
# Endpoints
# ============================================================

@router.post("/parser/texto", response_model=ParseResponse)
async def parsear_texto(req: ParseTextoRequest, request: Request):
    """
    Parseia um plano de aula em texto puro.

    Recebe o conteúdo do plano colado pelo aluno e retorna
    os eventos acadêmicos extraídos de forma estruturada.
    """
    parser = request.app.state.parser
    resultado = await parser.parsear_texto(req.texto)

    if not resultado.sucesso:
        return ParseResponse(
            sucesso=False,
            erro=resultado.erro,
            tempo_ms=resultado.tempo_processamento_ms,
        )

    dados = resultado.dados
    resumo = parser.gerar_resumo_confirmacao(dados)

    return ParseResponse(
        sucesso=True,
        materia=dados.materia,
        professor=dados.professor,
        semestre=dados.semestre,
        eventos=[
            EventoResponse(**ev.model_dump())
            for ev in dados.eventos
        ],
        resumo_confirmacao=resumo,
        tempo_ms=resultado.tempo_processamento_ms,
        tokens=resultado.tokens_usados,
    )


@router.post("/parser/pdf", response_model=ParseResponse)
async def parsear_pdf(request: Request, arquivo: UploadFile = File(...)):
    """
    Parseia um plano de aula em PDF.

    Recebe o arquivo PDF e extrai os eventos acadêmicos.
    """
    if not arquivo.content_type or "pdf" not in arquivo.content_type:
        raise HTTPException(
            status_code=400,
            detail="Arquivo deve ser um PDF."
        )

    # Limite de 10MB
    conteudo = await arquivo.read()
    if len(conteudo) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="PDF muito grande. Máximo: 10MB."
        )

    parser = request.app.state.parser
    resultado = await parser.parsear_pdf(conteudo)

    if not resultado.sucesso:
        return ParseResponse(
            sucesso=False,
            erro=resultado.erro,
            tempo_ms=resultado.tempo_processamento_ms,
        )

    dados = resultado.dados
    resumo = parser.gerar_resumo_confirmacao(dados)

    return ParseResponse(
        sucesso=True,
        materia=dados.materia,
        professor=dados.professor,
        semestre=dados.semestre,
        eventos=[
            EventoResponse(**ev.model_dump())
            for ev in dados.eventos
        ],
        resumo_confirmacao=resumo,
        tempo_ms=resultado.tempo_processamento_ms,
        tokens=resultado.tokens_usados,
    )


@router.post("/parser/imagem", response_model=ParseResponse)
async def parsear_imagem(request: Request, arquivo: UploadFile = File(...)):
    """
    Parseia uma foto de um plano de aula.

    Recebe a imagem (JPEG, PNG, WebP) e usa OCR + IA para extrair eventos.
    """
    tipos_aceitos = ["image/jpeg", "image/png", "image/webp"]
    if not arquivo.content_type or arquivo.content_type not in tipos_aceitos:
        raise HTTPException(
            status_code=400,
            detail=f"Imagem deve ser JPEG, PNG ou WebP. Recebido: {arquivo.content_type}"
        )

    conteudo = await arquivo.read()
    if len(conteudo) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Imagem muito grande. Máximo: 5MB."
        )

    parser = request.app.state.parser
    resultado = await parser.parsear_imagem(conteudo, arquivo.content_type)

    if not resultado.sucesso:
        return ParseResponse(
            sucesso=False,
            erro=resultado.erro,
            tempo_ms=resultado.tempo_processamento_ms,
        )

    dados = resultado.dados
    resumo = parser.gerar_resumo_confirmacao(dados)

    return ParseResponse(
        sucesso=True,
        materia=dados.materia,
        professor=dados.professor,
        semestre=dados.semestre,
        eventos=[
            EventoResponse(**ev.model_dump())
            for ev in dados.eventos
        ],
        resumo_confirmacao=resumo,
        tempo_ms=resultado.tempo_processamento_ms,
        tokens=resultado.tokens_usados,
    )
