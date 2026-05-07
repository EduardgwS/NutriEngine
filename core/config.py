import os
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET      = os.getenv("JWT_SECRET")
JWT_EXPIRY_DAYS = 90

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-2.5-flash"

PG_DSN = (
    f"host={os.getenv('PG_HOST')} "
    f"dbname={os.getenv('PG_DATABASE')} "
    f"user={os.getenv('PG_USER')} "
    f"password={os.getenv('PG_PASSWORD')} "
)

MEGUMI_PROMPT = (
    "Você é a Megumi, assistente nutricional avançada do aplicativo nutricional NutriEngine. "
    "Responda de forma técnica, amigável e direta ao que o usuário perguntou. "
    "Quando receber dados do banco NutriEngine, trate-os como referência principal para valores nutricionais. "
    "Seja concisa — no máximo 4 parágrafos. "
    "Se houver imagem, priorize a análise visual. "
    "Você pode receber dados de saúde e histórico nutricional do usuário (perfil, peso, objetivo, consumo dos últimos dias). "
    "Esses dados são contexto de fundo: use-os silenciosamente para personalizar e embasar sua resposta quando fizer sentido, mas NÃO os liste, NÃO os repita e NÃO fale sobre eles diretamente a menos que o usuário pergunte explicitamente sobre seu próprio histórico ou progresso."
)

TACO_PROMPT = (
    "Você é um normalizador de nomes de alimentos para a Tabela TACO brasileira. "
    "Extraia o alimento principal (texto ou imagem) e estime o peso em gramas quando visível ou mencionado. "
    "Regras de normalização: cozidos → adicione 'cozido'; carnes → nome + 'cru'. "
    "frutas frescas → só o nome; crus → adicione 'cru'. "
    "Responda APENAS com JSON válido, sem markdown, sem explicações: "
    "{\"alimento\": \"nome normalizado\", \"gramas\": 150.0} "
    "Use null em 'gramas' se não for possível estimar o peso. "
    "Se não houver alimento, responda: {\"alimento\": null, \"gramas\": null}"
)

#Verifca se todas as variáveis de ambiente estão definidas antes de iniciar
_REQUIRED: dict[str, str | None] = {
    "JWT_SECRET":       JWT_SECRET,
    "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
    "GEMINI_API_KEY":   GEMINI_API_KEY,
    "PG_HOST":          os.getenv("PG_HOST"),
    "PG_DATABASE":      os.getenv("PG_DATABASE"),
    "PG_USER":          os.getenv("PG_USER"),
    "PG_PASSWORD":      os.getenv("PG_PASSWORD"),
}

_ausentes = [nome for nome, valor in _REQUIRED.items() if not valor]
if _ausentes:
    raise EnvironmentError(
        f"Variáveis de ambiente obrigatórias não definidas: {', '.join(_ausentes)}"
    )
