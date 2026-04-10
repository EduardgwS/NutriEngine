import logging
from google import genai
from google.genai import types, errors
from config import GEMINI_API_KEY, GEMINI_MODEL, MEGUMI_PROMPT, TACO_PROMPT

log = logging.getLogger("megumi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

client = genai.Client(api_key=GEMINI_API_KEY)

# Normaliza o texto ou a imagem, pro padrão TACO
def extrair_alimento(texto: str, imagem_bytes: bytes | None = None) -> str:

    tem_texto  = bool(texto.strip())
    tem_imagem = bool(imagem_bytes)

    if not tem_texto and not tem_imagem:
        return ""

    try:
        parts: list = []

        if tem_imagem:
            parts.append(types.Part.from_bytes(data=imagem_bytes, mime_type="image/jpeg"))

        if tem_texto:
            parts.append(texto)
        elif tem_imagem:
            # Caso só tiver imagem (aba pesquisar)
            parts.append("Identifique o alimento principal nesta imagem.")

        response = client.models.generate_content(
            model   = GEMINI_MODEL,
            contents= parts,
            config  = types.GenerateContentConfig(
                system_instruction = TACO_PROMPT,
                temperature        = 0.0,
                max_output_tokens  = 32,
            ),
        )
        alimento = response.text.strip().lower()
        log.info(f"[EXTRAIR] Resultado: {alimento!r} (imagem={'sim' if tem_imagem else 'não'})")
        return "" if not alimento or alimento == "(nenhum)" else alimento

    except Exception:
        log.warning("[EXTRAIR] Falha ao extrair o alimento")
        return ""

# Converte aquele JSON da saúde do cara, para um formato mais amigável pra Megumi
def _formatar_saude(saude: dict) -> str:
    partes = []

    perfil = saude.get("perfil", {})
    if perfil:
        linha = []
        if "peso_kg"           in perfil: linha.append(f"peso {perfil['peso_kg']} kg")
        if "altura_m"          in perfil: linha.append(f"altura {perfil['altura_m']} m")
        if "idade"             in perfil: linha.append(f"{perfil['idade']} anos")
        if "sexo"              in perfil: linha.append(perfil["sexo"])
        if "objetivo"          in perfil: linha.append(f"objetivo: {perfil['objetivo']}")
        if "nivel_atividade"   in perfil: linha.append(f"atividade: {perfil['nivel_atividade']}")
        if "kcal_recomendadas" in perfil: linha.append(f"meta calórica: {perfil['kcal_recomendadas']} kcal/dia")
        if linha:
            partes.append("Perfil do usuário: " + ", ".join(linha))

    historico = saude.get("historico_nutricional", [])
    if historico:
        partes.append("Histórico nutricional dos últimos 7 dias:")
        for dia in historico:
            partes.append(
                f"  {dia['data']}: {dia['kcal']} kcal | "
                f"prot {dia['proteinas_g']}g | "
                f"carbo {dia['carboidratos_g']}g | "
                f"gord {dia['gorduras_g']}g"
            )

    return "\n".join(partes)

# Megumi, oq ela recebe e como vai responder.
def responder_megumi(
        texto:        str,
        contexto:     str             = "",
        imagem_bytes: bytes | None    = None,
        historico:    list[dict] | None = None,
        saude_json:   dict | None     = None,
) -> str:


    contents: list[types.Content] = []

    for msg in (historico or []):
        role = "user" if msg["papel"] == "user" else "model"
        contents.append(
            types.Content(
                role  = role,
                parts = [types.Part(text=msg["mensagem"])],
            )
        )

    turno_atual: list = []
    if imagem_bytes:
        turno_atual.append(types.Part.from_bytes(data=imagem_bytes, mime_type="image/jpeg"))

    # Junta TACO + saúde da pessoa
    partes_contexto = []
    if contexto:
        partes_contexto.append(contexto)
    if saude_json:
        partes_contexto.append(_formatar_saude(saude_json))

    contexto_completo = "\n\n".join(partes_contexto)
    texto_turno = f"{texto}\n\n{contexto_completo}".strip() or "Analise esta imagem nutricional."
    turno_atual.append(types.Part(text=texto_turno))

    contents.append(types.Content(role="user", parts=turno_atual))

    log.info(f"[MEGUMI] TEXTO    : {texto!r}")
    log.info(f"[MEGUMI] TACO     : {contexto or '(vazio)'}")
    log.info(f"[MEGUMI] SAÚDE    : {'sim' if saude_json else 'não'}")
    log.info(f"[MEGUMI] IMAGEM   : {'sim' if imagem_bytes else 'não'}")
    log.info(f"[MEGUMI] HISTÓRICO: {len(historico or [])} mensagens anteriores")

    try:
        response = client.models.generate_content(
            model   = GEMINI_MODEL,
            contents= contents,
            config  = types.GenerateContentConfig(
                system_instruction = MEGUMI_PROMPT,
                temperature        = 0.2,
                max_output_tokens  = 2048,
            ),
        )
        return response.text

    # Descobrir os erros. Caralho, toda hora da erro, maldito plano gratuíto
    except errors.ClientError as e:
        erro_msg = str(e)
        if "429" in erro_msg or "RESOURCE_EXHAUSTED" in erro_msg:
            log.error("[QUOTA] Tokens esgotados.")
            return "Desculpa, já estou cansada demais por hoje. Amanhã podemos conversar mais se quiser, mas vou sair por agora."

        log.error("[MEGUMI] Erro de cliente na API.")
        return "Tive um probleminha aqui, mas já volto!"

    # Deixa meu logzinho mais bonitinhoooo uwu. Odeio log, mas é útil. Sorte q n vou mexer niss dps
    except Exception:
        log.error("[MEGUMI] Erro inesperado.")
        return "Tive um problemão aqui, espera aí que eu vou tentar resolver e ja volto!"