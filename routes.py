from typing import Annotated
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel

from auth import criar_token, usuario_atual          # ← vem do auth.py
from config import GOOGLE_CLIENT_ID
from database import (
    upsert_user,
    buscar_alimento, search_food_list,
    salvar_mensagem, carregar_historico,
)
from services import extrair_alimento, responder_megumi

router = APIRouter()


class AndroidLoginRequest(BaseModel):
    id_token: str


@router.post("/auth/google/android")
def auth_android(body: AndroidLoginRequest):
    try:
        info = id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(401, "Token Google inválido ou expirado")

    email    = info["email"]
    name     = info.get("name", "")
    username = email.split("@")[0]

    upsert_user(username, name, email)
    token = criar_token(username, email, name)

    return {"token": token, "user": username, "name": name, "email": email}


@router.get("/api/search")
def search(q: str = ""):
    return search_food_list(q)


@router.post("/api/identificar-alimento")
async def identificar_alimento(
        text:  str               = Form(default=""),
        image: UploadFile | None = File(default=None),
):
    imagem_bytes = await image.read() if image else None

    if not text and not imagem_bytes:
        raise HTTPException(400, "Envie pelo menos um texto ou uma imagem.")

    alimento = extrair_alimento(text, imagem_bytes)

    return {
        "status":   "success",
        "alimento": alimento if alimento else None,
    }


@router.post("/megumi/chat")
async def megumi_chat(
        user:            Annotated[dict, Depends(usuario_atual)],
        text:            str               = Form(default=""),
        image:           UploadFile | None = File(default=None),
        historico_saude: str               = Form(default=""),
):
    texto_limpo  = text.strip()
    imagem_bytes = await image.read() if image else None

    if not texto_limpo and not imagem_bytes:
        raise HTTPException(400)

    username = user["user"]
    historico = carregar_historico(username, limite=10)

    if texto_limpo:
        salvar_mensagem(username, "user", texto_limpo)

    alimento   = extrair_alimento(texto_limpo) if texto_limpo else ""
    dados_taco = buscar_alimento(alimento) if alimento else ""

    saude_json = None
    if historico_saude.strip():
        try:
            saude_json = json.loads(historico_saude)
        except Exception:
            pass

    resposta = responder_megumi(
        texto_limpo,
        dados_taco,
        imagem_bytes,
        historico,
        saude_json,
    )

    salvar_mensagem(username, "megumi", resposta)

    return {"status": "success", "response": resposta}


@router.get("/megumi/historico")
def historico_chat(
        user:   Annotated[dict, Depends(usuario_atual)],
        limite: int = 50,
):
    msgs = carregar_historico(user["user"], limite=min(limite, 200))
    return {"status": "success", "mensagens": msgs}