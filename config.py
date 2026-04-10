import os
from dotenv import load_dotenv

load_dotenv()

# Configuração para o login com o google, e a API do gemini
JWT_SECRET      = os.getenv("JWT_SECRET")
JWT_EXPIRY_DAYS = 90

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-2.5-flash"

# Postgree SQL
PG_DSN = (
    f"host={os.getenv('PG_HOST')} "
    f"dbname={os.getenv('PG_DATABASE')} "
    f"user={os.getenv('PG_USER')} "
    f"password={os.getenv('PG_PASSWORD')} "
)


# Promts da Megumi e do Taco (Gemini mas pra fazer a pesquisa dos alimentos antes de passar pra megumi)
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
    "Se a conversa for relacionada a alimentos, extraia o alimento principal do texto e normalize para o padrão TACO."
    "Regras: cozidos → adicione 'cozido'; carnes → nome + 'cozido'; "
    "frutas frescas → só o nome; crus → adicione 'cru'. "
    "Responda APENAS com o nome normalizado, sem artigos, pontuação ou explicações. "
    "Se não houver alimento, responda exatamente: (nenhum)"
)
