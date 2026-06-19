"""
EduBot — Disparo manual do agregador semanal (Camada 2).

Uso:
    python -m app.scripts.agregar                        # domingo de hoje, todas as turmas com dúvida
    python -m app.scripts.agregar --data-ref 2026-06-07  # outro domingo de referência
    python -m app.scripts.agregar --turma-id <uuid>      # só uma turma

Agendamento automático (Celery+Redis) é a CC #8 — aqui é manual.
"""

import argparse
import asyncio
import logging
import os
import uuid
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

from app.services.agregador import (
    AgregadorEngine, calcular_janela, processar_agregacao, turmas_com_duvidas,
)
from app.services.relatorio_gen import ProsaEngine, SubconceitoEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("edubot.scripts.agregar")


async def main() -> None:
    ap = argparse.ArgumentParser(description="Agregador semanal de dúvidas (EduBot Camada 2).")
    ap.add_argument("--data-ref", type=str, default=None,
                    help="Domingo de referência YYYY-MM-DD (default: hoje).")
    ap.add_argument("--turma-id", type=str, default=None,
                    help="UUID de uma turma específica (default: todas com dúvida na janela).")
    args = ap.parse_args()

    data_ref = (
        datetime.strptime(args.data_ref, "%Y-%m-%d").date()
        if args.data_ref else date.today()
    )
    semana_inicio, semana_fim = calcular_janela(data_ref)
    logger.info(f"Janela: {semana_inicio} (dom) .. {semana_fim} (sáb) | ref={data_ref}")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY ausente — matching falha graciosamente (tudo NULL).")
    engine = AgregadorEngine(api_key=api_key)
    subc_engine = SubconceitoEngine(api_key=api_key)
    prosa_engine = ProsaEngine(api_key=api_key)

    try:
        if args.turma_id:
            turmas = [uuid.UUID(args.turma_id)]
        else:
            turmas = await turmas_com_duvidas(data_ref)
            logger.info(f"{len(turmas)} turma(s) com dúvida na janela.")
        for turma_id in turmas:
            await processar_agregacao(
                turma_id, data_ref, engine,
                subc_engine=subc_engine, prosa_engine=prosa_engine,
            )
    finally:
        await engine.close()
        await subc_engine.close()
        await prosa_engine.close()


if __name__ == "__main__":
    asyncio.run(main())
