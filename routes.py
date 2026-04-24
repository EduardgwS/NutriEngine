from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel

from config import JWT_SECRET, JWT_EXPIRY_DAYS, GOOGLE_CLIENT_ID
from database import (
    upsert_user,
    buscar_alimento, search_food_list,
    salvar_mensagem, carregar_historico,
)
from services import extrair_alimento, responder_megumi

router = APIRouter()
bearer = HTTPBearer()


# JWT (login com o google). Aqui é onde declara ele, e usa.
# Do jeito atual, junto com a requisição http, vem a credencial de autorização JWT, sem ela o usuário n tem acesso

def criar_token(username: str, email: str, name: str) -> str:
    payload = {
        "sub":   username,
        "email": email,
        "name":  name,
        "exp":   datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def usuario_atual(credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        return {"user": payload["sub"], "email": payload["email"], "name": payload["name"]}
    # Venceu o prazo de login, aí o cara tem q logar dnv pra deixar de ser otário
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")


# Esquema pra entrar. O servidor só vai aceitar se for exatamente neste formato
class AndroidLoginRequest(BaseModel):
    id_token: str


# Auth do Google,
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


# A busca dos alimentos,
@router.get("/api/search")
def search(q: str = ""):
    return search_food_list(q.strip().lower())


# Busca de alimentos exclusivamente pela IA (visão).
# Retorna o nome normalizado (TACO) e o peso estimado em gramas quando detectável.
@router.post("/api/identificar-alimento")
async def identificar_alimento(
        user:  Annotated[dict, Depends(usuario_atual)],
        text:  str               = Form(default=""),
        image: UploadFile | None = File(default=None),
):
    texto_limpo  = text.strip()
    imagem_bytes = await image.read() if image else None

    if not texto_limpo and not imagem_bytes:
        raise HTTPException(400, "Envie pelo menos um texto ou uma imagem.")

    resultado = extrair_alimento(texto_limpo, imagem_bytes)

    return {
        "status":   "success",
        "alimento": resultado["alimento"],
        "gramas":   resultado["gramas"],
    }


# Chat da Megumi
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

    # Carrega o histórico, salva no banco, monta o contexto da tabela TACO, e o histórico de saúde do cara
    historico = carregar_historico(username, limite=10)

    if texto_limpo:
        salvar_mensagem(username, "user", texto_limpo)

    # extrair_alimento agora retorna dict; só o nome interessa para busca no TACO
    alimento_resultado = extrair_alimento(texto_limpo) if texto_limpo else {}
    alimento           = alimento_resultado.get("alimento") or ""
    dados_taco         = buscar_alimento(alimento) if alimento else ""

    import json as _json
    saude_json: dict | None = None
    if historico_saude.strip():
        try:
            saude_json = _json.loads(historico_saude)
        # Só pra n ter erro, se o cara n tiver saúde, q se foda tbm
        except Exception:
            pass

    contexto_parts = []
    if dados_taco:
        contexto_parts.append(dados_taco)

    # Resposta da Megumi uwu
    resposta = responder_megumi(
        texto_limpo,
        " — ".join(contexto_parts),
        imagem_bytes,
        historico,
        saude_json,
    )

    salvar_mensagem(username, "megumi", resposta)

    return {"status": "success", "response": resposta}


# History Channel, do chat da Megumi
@router.get("/megumi/historico")
def historico_chat(
        user:   Annotated[dict, Depends(usuario_atual)],
        limite: int = 50,
):
    msgs = carregar_historico(user["user"], limite=min(limite, 200))
    return {"status": "success", "mensagens": msgs}