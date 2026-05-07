import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
from services.services import receita_do_dia, OBJETIVOS_RECEITAS
from services.dicas import selecionar_dica

from core.auth import criar_token, usuario_atual
from core.config import GOOGLE_CLIENT_ID
from core.database import (
    upsert_user,
    buscar_alimento, search_food_list,
    salvar_mensagem, carregar_historico,
)
from services.services import extrair_alimento, responder_megumi

router = APIRouter()


# ── Autenticação ──────────────────────────────────────────────────────────────

class GoogleTokenRequest(BaseModel):
    id_token: str

@router.post("/auth/google/android")
def auth_google_android(body: GoogleTokenRequest):
    try:
        info = id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Token inválido")

    email    = info["email"]
    name     = info.get("name", email)
    username = email.split("@")[0]

    upsert_user(username, name, email)
    token = criar_token(username, email, name)

    return {"token": token, "name": name}


# ── Megumi ────────────────────────────────────────────────────────────────────

@router.post("/megumi/chat")
async def megumi_chat(
    text:            str              = Form(...),
    image:           UploadFile | None = File(None),
    historico_saude: str | None       = Form(None),
    usuario:         dict             = Depends(usuario_atual),
):
    imagem_bytes = await image.read() if image else None
    saude_json   = None

    if historico_saude:
        try:
            saude_json = json.loads(historico_saude)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="historico_saude não é um JSON válido")

    contexto  = buscar_alimento(text)
    historico = carregar_historico(usuario["user"], limite=20)
    resposta  = responder_megumi(
        texto        = text,
        contexto     = contexto,
        imagem_bytes = imagem_bytes,
        historico    = historico,
        saude_json   = saude_json,
    )

    salvar_mensagem(usuario["user"], "user",   text)
    salvar_mensagem(usuario["user"], "megumi", resposta)

    return {"response": resposta}


@router.get("/megumi/historico")
def megumi_historico(
    limite:  int  = 50,
    usuario: dict = Depends(usuario_atual),
):
    msgs = carregar_historico(usuario["user"], limite=limite)
    return {
        "mensagens": [
            {"mensagem": m["mensagem"], "papel": m["papel"]}
            for m in msgs
        ]
    }


# ── Alimentos ─────────────────────────────────────────────────────────────────

@router.get("/api/search")
def search(q: str = ""):
    return search_food_list(q)


@router.post("/api/identificar-alimento")
async def identificar_alimento(image: UploadFile = File(...)):
    imagem_bytes = await image.read()
    resultado    = extrair_alimento("", imagem_bytes)

    if not resultado["alimento"]:
        raise HTTPException(status_code=422, detail="Não foi possível identificar o alimento na imagem.")

    return {
        "status":   "success",
        "alimento": resultado["alimento"],
        "gramas":   resultado["gramas"] or 0.0,
    }


# ── Sugestões ─────────────────────────────────────────────────────────────────

@router.get("/api/receita-do-dia")
def receita_do_dia_endpoint(objetivo: str = ""):
    objetivo_upper = objetivo.upper()
    if objetivo_upper not in OBJETIVOS_RECEITAS:
        raise HTTPException(
            status_code=400,
            detail=f"Objetivo inválido. Use um de: {', '.join(OBJETIVOS_RECEITAS)}"
        )

    receita = receita_do_dia(objetivo_upper)
    return {"status": "success", "receita": receita}


@router.get("/api/dicas-macrocard")
def dicas_macrocard(
    maior_deficit:      int   = 0,
    proteina_consumida: float = 0.0,
):
    dica = selecionar_dica(maior_deficit, proteina_consumida)
    if dica is None:
        raise HTTPException(status_code=400, detail="Parâmetro maior_deficit inválido.")

    return {
        "status": "success",
        "dica": {
            "icone":  dica.icone,
            "titulo": dica.titulo,
            "corpo":  dica.corpo,
        },
    }
