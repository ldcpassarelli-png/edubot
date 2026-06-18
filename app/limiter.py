"""
EduBot — Rate limiter global (slowapi, in-process).

Teto GLOBAL de requisições no webhook, em memória do processo (não Redis — Redis
foi cortado do piloto na CC #8; o app roda uma instância no Railway Hobby). Função
de EXTINTOR contra loop/bug/reenvio do Meta que dispararia chamadas à API Anthropic
via classificador — não é cota por aluno.

key_func constante ("global") → todas as requisições limitadas dividem um único
balde, virando teto global em vez de por-IP (o tráfego do webhook vem todo do
range da Meta de qualquer forma).
"""
from slowapi import Limiter
from starlette.requests import Request


def _chave_global(request: Request) -> str:
    return "global"


# 300/min: folga deliberada. Sem dado de campo, errar pra cima é barato (um loop
# descontrolado faz milhares/min e ainda é cortado em segundos), enquanto errar pra
# baixo bloquearia uma turma real num pico — visível, na frente do professor parceiro.
# O pico humano de uma turma piloto fica bem abaixo de 300; um loop fica bem acima.
# Constante única, afinável conforme a base de usuários cresce.
WEBHOOK_RATE_LIMIT = "300/minute"

limiter = Limiter(key_func=_chave_global, default_limits=[])
