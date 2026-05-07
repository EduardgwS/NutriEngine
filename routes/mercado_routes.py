from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from core.database import listar_parceiros, listar_produtos_ativos
from services.services import recomendar_por_tags, TAGS_VALIDAS

mercado_router = APIRouter(prefix="/mercado", tags=["mercado"])


# ── Modelo de entrada ─────────────────────────────────────────────────────────

class RecomendacoesRequest(BaseModel):
    necessidades: list[str]

    @field_validator("necessidades")
    @classmethod
    def validar_tags(cls, tags: list[str]) -> list[str]:
        tags_upper = [t.strip().upper() for t in tags]
        invalidas  = set(tags_upper) - TAGS_VALIDAS
        if invalidas:
            raise ValueError(
                f"Tags inválidas: {', '.join(sorted(invalidas))}. "
                f"Permitidas: {', '.join(sorted(TAGS_VALIDAS))}"
            )
        return tags_upper


# ── Rotas ─────────────────────────────────────────────────────────────────────

@mercado_router.get("/parceiros")
def get_parceiros():
    """Retorna todos os parceiros ativos."""
    return {"parceiros": listar_parceiros()}


@mercado_router.post("/recomendacoes")
def post_recomendacoes(
        body: RecomendacoesRequest,
):
    """
    Recebe uma lista de tags de necessidade do usuário e retorna os
    produtos mais relevantes do catálogo.

    Tags de macro  : ALTA_PROTEINA | CARBOIDRATO | GORDURA_BOA
    Tags de objetivo: GANHAR_MUSCULOS | PERDER_PESO | MELHORAR_ALIMENTACAO
    """
    produtos = listar_produtos_ativos()
    if not produtos:
        return {"recomendacoes": []}

    recomendacoes = recomendar_por_tags(body.necessidades, produtos)
    return {"recomendacoes": recomendacoes}