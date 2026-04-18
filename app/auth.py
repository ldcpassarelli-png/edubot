"""
Autenticação por API key para endpoints internos.

Endpoints administrativos (ex: /alunos/*) exigem o header X-API-Key
com valor igual à variável de ambiente INTERNAL_API_KEY.

O webhook do WhatsApp NÃO usa esse mecanismo — ele é protegido por
HMAC (ver Frente 1).
"""

import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> None:
    """
    Valida o header X-API-Key contra INTERNAL_API_KEY.

    Lança 401 Unauthorized se:
    - O header estiver ausente
    - O valor não bater com INTERNAL_API_KEY
    - INTERNAL_API_KEY não estiver configurada no servidor

    Usa secrets.compare_digest para evitar timing attacks.
    """
    expected = os.getenv("INTERNAL_API_KEY", "")

    if not expected:
        # Servidor mal configurado — falha fechada, nunca aberta.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_API_KEY não configurada no servidor",
        )

    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
