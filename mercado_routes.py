from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import usuario_atual                       # ← direto do auth.py, sem passar por routes.py
from database import listar_parceiros, listar_produtos_ativos
from services import recomendar_produtos

mercado_router = APIRouter(prefix="/mercado", tags=["mercado"])


# ── Modelos de entrada ────────────────────────────────────────────────────────

class PerfilRecomendacao(BaseModel):
    objetivo: str
    kcal_recomendadas: float
    sexo: str
    idade: int | None = None


class ConsumoHoje(BaseModel):
    kcal: float
    proteinas_g: float
    carboidratos_g: float
    gorduras_g: float


class GapNutricional(BaseModel):
    kcal: float
    proteinas_g: float
    carboidratos_g: float
    gorduras_g: float


class RecomendacoesRequest(BaseModel):
    perfil: PerfilRecomendacao
    consumo_hoje: ConsumoHoje
    gap: GapNutricional


# ── Rotas ─────────────────────────────────────────────────────────────────────

@mercado_router.get("/parceiros")
def get_parceiros():
    """Retorna todos os parceiros ativos."""
    parceiros = listar_parceiros()
    return {"parceiros": parceiros}


@mercado_router.post("/recomendacoes")
def post_recomendacoes(
        body: RecomendacoesRequest,
        user: Annotated[dict, Depends(usuario_atual)],
):
    """
    Recebe o perfil nutricional do usuário e retorna produtos
    recomendados pela IA com base no gap calórico/macronutrientes.
    """
    produtos = listar_produtos_ativos()

    if not produtos:
        return {"recomendacoes": []}

    recomendacoes = recomendar_produtos(
        perfil=body.perfil.model_dump(),
        consumo_hoje=body.consumo_hoje.model_dump(),
        gap=body.gap.model_dump(),
        produtos=produtos,
    )

    return {"recomendacoes": recomendacoes}