import json
import logging
import re
from google import genai
from google.genai import types, errors
from core.config import GEMINI_API_KEY, GEMINI_MODEL, MEGUMI_PROMPT, TACO_PROMPT
from datetime import date
from pathlib import Path

log = logging.getLogger("megumi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

client = genai.Client(api_key=GEMINI_API_KEY)

# Compilado uma única vez no import, não a cada request
_JSON_RE = re.compile(r'\{.*?}', re.DOTALL)


def extrair_alimento(texto: str, imagem_bytes: bytes | None = None) -> dict:
    """
    Normaliza o texto ou a imagem pro padrão TACO e estima o peso se possível.
    Retorna dict {"alimento": str | None, "gramas": float | None}
    """
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
                max_output_tokens  = 600,
            ),
        )

        raw = response.text
        if not raw:
            candidate = (response.candidates or [None])[0]
            reason    = getattr(getattr(candidate, "finish_reason", None), "name", "UNKNOWN")
            log.warning(f"[EXTRAIR] Resposta vazia do modelo. finish_reason={reason}")
            return {"alimento": None, "gramas": None}

        raw = raw.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        log.info(f"[EXTRAIR] raw={raw!r}")

        match = _JSON_RE.search(raw)
        if not match:
            log.warning(f"[EXTRAIR] Nenhum JSON encontrado no raw: {raw!r}")
            return {"alimento": None, "gramas": None}

        parsed   = json.loads(match.group())
        alimento = parsed.get("alimento") or None
        gramas   = parsed.get("gramas")

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


def _formatar_saude(saude: dict) -> str:
    """Converte os dados de saúde do usuário para formato legível pela Megumi."""
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


# ── Motor de recomendações ────────────────────────────────────────────────────

TAGS_VALIDAS: frozenset[str] = frozenset({
    "ALTA_PROTEINA",
    "CARBOIDRATO",
    "GORDURA_BOA",
    "GANHAR_MUSCULOS",
    "PERDER_PESO",
    "MELHORAR_ALIMENTACAO",
})

_TAG_CONFIG: dict[str, dict] = {
    "ALTA_PROTEINA": {
        "categorias_alvo":      ["proteína"],
        "categorias_penalizar": [],
        "motivo":               "Excelente para bater sua meta de proteínas do dia.",
        "scorer": lambda p: min(p["proteinas"] / 30.0, 1.0),
    },
    "CARBOIDRATO": {
        "categorias_alvo":      ["carboidrato"],
        "categorias_penalizar": [],
        "motivo":               "Boa fonte de carboidrato para repor sua energia.",
        "scorer": lambda p: min(p["carboidratos"] / 50.0, 1.0),
    },
    "GORDURA_BOA": {
        "categorias_alvo":      ["gordura"],
        "categorias_penalizar": [],
        "motivo":               "Rico em gorduras boas para complementar sua dieta.",
        "scorer": lambda p: min(p["gorduras"] / 20.0, 1.0),
    },
    "GANHAR_MUSCULOS": {
        "categorias_alvo":      ["proteína", "carboidrato"],
        "categorias_penalizar": [],
        "motivo":               "Alta densidade calórica e proteica, ideal para ganho de massa.",
        "scorer": lambda p: min((p["proteinas"] * 1.5 + p["kcal"] * 0.01) / 50.0, 1.0),
    },
    "PERDER_PESO": {
        "categorias_alvo":      ["proteína"],
        "categorias_penalizar": ["gordura", "snack"],
        "motivo":               "Baixa caloria e bom teor proteico, aliado do seu processo de emagrecimento.",
        "scorer": lambda p: min(p["proteinas"] / max(p["kcal"], 1) * 10, 1.0),
    },
    "MELHORAR_ALIMENTACAO": {
        "categorias_alvo":      ["proteína", "carboidrato", "gordura"],
        "categorias_penalizar": ["snack"],
        "motivo":               "Produto de qualidade nutricional para uma alimentação mais equilibrada.",
        "scorer": lambda p: 0.5,
    },
}


def _pontuar_por_tags(produto: dict, tags: list[str]) -> tuple[float, str]:
    score  = 0.0
    motivo = "Complementa sua dieta de forma equilibrada."
    cat    = produto.get("categoria", "").lower()

    for tag in tags:
        cfg = _TAG_CONFIG.get(tag)
        if not cfg:
            continue

        score += cfg["scorer"](produto)

        if cat in [c.lower() for c in cfg["categorias_alvo"]]:
            score += 0.4
            motivo = cfg["motivo"]

        for pen_cat in cfg["categorias_penalizar"]:
            if cat == pen_cat.lower():
                score -= 0.3

    if produto.get("preco_antigo") is not None:
        score += 0.1

    return max(score, 0.0), motivo


def recomendar_por_tags(
        tags:     list[str],
        produtos: list[dict],
        n:        int = 6,
) -> list[dict]:
    """
    Seleciona e ordena os produtos mais relevantes para as tags recebidas.
    Garante variedade: no máximo 3 produtos por categoria.
    """
    pontuados = [
        (produto, *_pontuar_por_tags(produto, tags))
        for produto in produtos
        if produto.get("ativo", True)
    ]
    pontuados.sort(key=lambda x: x[1], reverse=True)

    resultado: list[dict]        = []
    contagem_cat: dict[str, int] = {}
    MAX_POR_CAT = 3

    for produto, score, motivo in pontuados:
        if len(resultado) >= n:
            break
        cat = produto.get("categoria", "outro")
        if contagem_cat.get(cat, 0) >= MAX_POR_CAT:
            continue

        resultado.append({
            "id":           produto["id"],
            "nome":         produto["nome"],
            "marca":        produto.get("marca", ""),
            "imagem_url":   produto.get("imagem_url", ""),
            "nome_mercado": produto.get("nome_mercado", ""),
            "logo_mercado": produto.get("logo_mercado", ""),
            "preco_atual":  produto["preco_atual"],
            "preco_antigo": produto.get("preco_antigo"),
            "quantidade_g": produto.get("quantidade_g", 0.0),
            "motivo":       motivo,
            "url_compra":   produto["url_compra"],
            "categoria":    produto.get("categoria", ""),
            "kcal":         produto.get("kcal", 0.0),
            "proteinas":    produto.get("proteinas", 0.0),
            "carboidratos": produto.get("carboidratos", 0.0),
            "gorduras":     produto.get("gorduras", 0.0),
        })
        contagem_cat[cat] = contagem_cat.get(cat, 0) + 1

    log.info(
        f"[RECOMENDACAO] tags={tags}  "
        f"produtos_selecionados={len(resultado)}"
    )
    return resultado


def _carregar_receitas() -> dict:
    # Adicionamos a pasta 'data' no caminho
    caminho = Path(__file__).parent / "data" / "receitas.json"

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Esse log agora é seu melhor amigo para debugar
        log.error(f"[RECEITAS] Arquivo não encontrado em: {caminho.absolute()}")
        return {}
    except json.JSONDecodeError:
        log.error(f"[RECEITAS] Erro de formatação no JSON.")
        return {}

def receita_do_dia(objetivo: str) -> dict | None:
    """
    Seleciona uma receita do catálogo JSON com base no dia do ano.
    """
    catalogo = _carregar_receitas()

    # Busca a lista de receitas para o objetivo (ex: "PERDER_PESO")
    lista = catalogo.get(objetivo.upper())

    if not lista:
        log.warning(f"[RECEITAS] Objetivo '{objetivo}' não encontrado ou lista vazia.")
        return None

    # Lógica determinística: troca a receita a cada 24h
    dia_do_ano = date.today().timetuple().tm_yday
    indice = dia_do_ano % len(lista)

    return lista[indice]

# Exporta as chaves do JSON como os objetivos aceitos
_receitas_temp = _carregar_receitas()
OBJETIVOS_RECEITAS = frozenset(_receitas_temp.keys())

