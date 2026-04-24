import json
import logging
from google import genai
from google.genai import types, errors
from config import GEMINI_API_KEY, GEMINI_MODEL, MEGUMI_PROMPT, TACO_PROMPT

log = logging.getLogger("megumi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

client = genai.Client(api_key=GEMINI_API_KEY)


# Normaliza o texto ou a imagem pro padrão TACO, e estima o peso se possível.
# Retorna dict {"alimento": str | None, "gramas": float | None}
def extrair_alimento(texto: str, imagem_bytes: bytes | None = None) -> dict:

    tem_texto  = bool(texto.strip())
    tem_imagem = bool(imagem_bytes)

    if not tem_texto and not tem_imagem:
        return {"alimento": None, "gramas": None}

    try:
        parts: list = []

        if tem_imagem:
            parts.append(types.Part.from_bytes(data=imagem_bytes, mime_type="image/jpeg"))

        if tem_texto:
            parts.append(texto)
        else:
            parts.append("Identifique o alimento principal nesta imagem e estime o peso em gramas.")

        response = client.models.generate_content(
            model   = GEMINI_MODEL,
            contents= parts,
            config  = types.GenerateContentConfig(
                system_instruction = TACO_PROMPT,
                temperature        = 0.0,
                max_output_tokens  = 64,
            ),
        )

        raw = response.text.strip()

        # Remove cercas de markdown caso o modelo as inclua por engano
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed   = json.loads(raw)
        alimento = parsed.get("alimento") or None
        gramas   = parsed.get("gramas")

        # Garante que gramas seja float ou None
        if gramas is not None:
            try:
                gramas = float(gramas)
            except (TypeError, ValueError):
                gramas = None

        if alimento:
            alimento = alimento.strip().lower()

        log.info(
            f"[EXTRAIR] alimento={alimento!r}  gramas={gramas}  "
            f"(imagem={'sim' if tem_imagem else 'não'})"
        )
        return {"alimento": alimento, "gramas": gramas}

    except Exception as e:
        log.warning("[EXTRAIR] Falha ao extrair o alimento: " + str(e))
        return {"alimento": None, "gramas": None}


# Converte a saúde da pessoa para um formato amigável para a Megumi
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

    except errors.ClientError as e:
        erro_msg = str(e)
        if "429" in erro_msg or "RESOURCE_EXHAUSTED" in erro_msg:
            log.error("[QUOTA] Tokens esgotados.")
            return "Desculpa, já estou cansada demais por hoje. Amanhã podemos conversar mais se quiser, mas vou sair por agora."

        log.error("[MEGUMI] Erro de cliente na API.")
        return "Tive um probleminha aqui, mas já volto!"

    except Exception:
        log.error("[MEGUMI] Erro inesperado.")
        return "Tive um problemão aqui, espera aí que eu vou tentar resolver e ja volto!"


def _gerar_motivo(produto: dict, gap: dict) -> str:
    """Gera um texto explicativo baseado no gap e na categoria do produto."""
    categoria = produto.get("categoria", "").lower()

    if gap["proteinas_g"] > 0 and categoria == "proteína":
        return f"Faltam {gap['proteinas_g']:.0f}g de proteína para sua meta"
    if gap["carboidratos_g"] > 0 and categoria == "carboidrato":
        return f"Faltam {gap['carboidratos_g']:.0f}g de carboidrato para sua meta"
    if gap["gorduras_g"] > 0 and categoria == "gordura":
        return f"Faltam {gap['gorduras_g']:.0f}g de gordura para sua meta"
    if gap["kcal"] > 0:
        return f"Faltam {gap['kcal']:.0f} kcal para bater sua meta diária"
    return "Complementa sua dieta de forma equilibrada"


def _pontuar_produto(produto: dict, gap: dict, objetivo: str) -> float:
    """
    Retorna uma pontuação (float >= 0) de relevância do produto para o gap.

    Critérios:
      - Contribuição proporcional de cada macro ao gap correspondente (peso 1.0)
      - Bônus por categoria alinhada ao objetivo do usuário          (peso 0.4)
      - Bônus por produto em promoção                                (peso 0.1)
    """
    score = 0.0

    prot  = produto["proteinas"]
    carbs = produto["carboidratos"]
    gord  = produto["gorduras"]
    kcal  = produto["kcal"]

    # Contribuição proporcional ao gap (cada macro vale no máximo 1.0)
    if gap["proteinas_g"]    > 0:
        score += min(prot  / gap["proteinas_g"],    1.0)
    if gap["carboidratos_g"] > 0:
        score += min(carbs / gap["carboidratos_g"], 1.0)
    if gap["gorduras_g"]     > 0:
        score += min(gord  / gap["gorduras_g"],     1.0)
    if gap["kcal"]           > 0:
        score += min(kcal  / gap["kcal"],           1.0) * 0.5  # peso menor: kcal é derivada

    # Bônus por objetivo
    objetivo_lower = objetivo.lower()
    categoria      = produto.get("categoria", "").lower()

    if "músculo" in objetivo_lower or "massa" in objetivo_lower:
        if categoria == "proteína":
            score += 0.4
        elif categoria == "carboidrato":
            score += 0.2

    elif "perder" in objetivo_lower or "emagrecer" in objetivo_lower:
        if categoria == "proteína":
            score += 0.4
        elif categoria in ("gordura", "snack"):
            score -= 0.2  # penaliza levemente

    elif "alimentação" in objetivo_lower or "saúde" in objetivo_lower:
        if categoria in ("proteína", "carboidrato", "gordura"):
            score += 0.2

    # Bônus por promoção
    if produto.get("preco_antigo") is not None:
        score += 0.1

    return max(score, 0.0)


def recomendar_produtos(
        perfil:       dict,
        consumo_hoje: dict,
        gap:          dict,
        produtos:     list[dict],
        n:            int = 6,
) -> list[dict]:
    """
    Seleciona e ordena os produtos mais relevantes para o gap nutricional
    do usuário sem usar nenhum modelo de linguagem.

    Retorna no máximo `n` produtos, priorizando variedade de categorias
    (no máximo 3 produtos por categoria).
    """
    objetivo = perfil.get("objetivo", "")

    # Pontua todos os produtos
    pontuados = [
        (produto, _pontuar_produto(produto, gap, objetivo))
        for produto in produtos
        if produto.get("ativo", True)
    ]

    # Ordena por pontuação decrescente
    pontuados.sort(key=lambda x: x[1], reverse=True)

    # Seleciona respeitando o limite por categoria (máx. 3 por categoria)
    resultado: list[dict]      = []
    contagem_cat: dict[str, int] = {}
    MAX_POR_CAT = 3

    for produto, _ in pontuados:
        if len(resultado) >= n:
            break
        cat = produto.get("categoria", "outro")
        if contagem_cat.get(cat, 0) >= MAX_POR_CAT:
            continue
        enriquecido           = dict(produto)
        enriquecido["motivo"] = _gerar_motivo(produto, gap)
        resultado.append(enriquecido)
        contagem_cat[cat]     = contagem_cat.get(cat, 0) + 1

    log.info(
        f"[RECOMENDACAO] {len(resultado)} produtos selecionados "
        f"(objetivo='{objetivo}', gap_prot={gap['proteinas_g']}g, "
        f"gap_carb={gap['carboidratos_g']}g, gap_gord={gap['gorduras_g']}g)"
    )
    return resultado