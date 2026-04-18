import psycopg2
import psycopg2.extras
from config import PG_DSN

# Conecta com o banco, e traduz pra dicionário
def conn():
    return psycopg2.connect(PG_DSN, cursor_factory=psycopg2.extras.RealDictCursor)



# DDL
def init_db():
    with conn() as c, c.cursor() as cur:
        cur.execute("""
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
            CREATE TABLE IF NOT EXISTS users (
                id       SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                name     TEXT,
                email    TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id         SERIAL PRIMARY KEY,
                username   TEXT        NOT NULL REFERENCES users(username),
                papel      TEXT        NOT NULL CHECK (papel IN ('user', 'megumi')),
                mensagem   TEXT        NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE INDEX IF NOT EXISTS idx_chat_history_username
                ON chat_history (username, created_at DESC);
        """)


# Usuários
def upsert_user(username: str, name: str, email: str):
    with conn() as c, c.cursor() as cur:
        cur.execute("""
            INSERT INTO users (username, name, email)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
        """, (username, name, email))



# Salvar mensagens no histórico
def salvar_mensagem(username: str, papel: str, mensagem: str):
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_history (username, papel, mensagem) VALUES (%s, %s, %s)",
            (username, papel, mensagem)
        )

# Carrega as mensagens com a Megumi
def carregar_historico(username: str, limite: int = 20) -> list[dict]:

    with conn() as c, c.cursor() as cur:
        cur.execute("""
            SELECT papel, mensagem, created_at
            FROM (
                SELECT papel, mensagem, created_at
                FROM chat_history
                WHERE username = %s
                ORDER BY created_at DESC
                LIMIT %s
            ) sub
            ORDER BY created_at ASC
        """, (username, limite))
        rows = cur.fetchall()
    return [
        {
            "papel":      row["papel"],
            "mensagem":   row["mensagem"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


# Busca do banco TACO para a Megumi.
def buscar_alimento(query: str) -> str:

    if not query or len(query) < 2:
        return ""

    palavras    = [p for p in query.strip().lower().split() if len(p) > 2] or query.split()
    and_clauses = " AND ".join(["lower(a.descricao) LIKE %s"] * len(palavras))
    or_clauses  = " OR  ".join(["lower(a.descricao) LIKE %s"] * len(palavras))
    count_expr  = " + ".join(
        ["(CASE WHEN lower(a.descricao) LIKE %s THEN 1 ELSE 0 END)"] * len(palavras)
    )
    like_params = [f"%{p}%" for p in palavras]

    sql = f"""
        SELECT
            a.descricao,
            MAX(CASE WHEN n.componente = 'Energia..kcal.'    THEN n.valor END) AS kcal,
            MAX(CASE WHEN n.componente = 'Proteína..g.'      THEN n.valor END) AS protein,
            MAX(CASE WHEN n.componente = 'Carboidrato..g.'   THEN n.valor END) AS carbs,
            MAX(CASE WHEN n.componente = 'Lipídeos..g.'      THEN n.valor END) AS fat,
            ({count_expr})                     AS word_score,
            similarity(lower(a.descricao), %s) AS sim_score
        FROM alimento a
        LEFT JOIN nutriente n ON n.codigo_alimento = a.codigo
        WHERE ({and_clauses}) OR ({or_clauses}) OR similarity(lower(a.descricao), %s) > 0.2
        GROUP BY a.codigo, a.descricao
        ORDER BY word_score DESC, sim_score DESC, length(a.descricao)
        LIMIT 1
    """
    params = like_params + [query] + like_params + like_params + [query]

    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()

    if not row:
        return ""

    return (
        f"[Dados NutriEngine – {row['descricao']}]: "
        f"Proteína: {row['protein'] or 0}g, "
        f"Carboidrato: {row['carbs'] or 0}g, "
        f"Gordura: {row['fat'] or 0}g, "
        f"Energia: {row['kcal'] or 0} kcal."
    )

# Busca no banco para ser usado na lista de pesquisa
def search_food_list(query: str) -> list[dict]:
    if not query:
        return []

    palavras    = [p for p in query.strip().lower().split() if len(p) > 2] or query.split()
    or_clauses  = " OR ".join(["lower(a.descricao) LIKE %s"] * len(palavras))
    count_expr  = " + ".join(
        ["(CASE WHEN lower(a.descricao) LIKE %s THEN 1 ELSE 0 END)"] * len(palavras)
    )
    like_params = [f"%{p}%" for p in palavras]

    sql = f"""
        SELECT
            a.codigo, a.descricao, a.classe,
            MAX(CASE WHEN n.componente = 'Energia..kcal.'    THEN n.valor END) AS kcal,
            MAX(CASE WHEN n.componente = 'Proteína..g.'      THEN n.valor END) AS protein,
            MAX(CASE WHEN n.componente = 'Carboidrato..g.'   THEN n.valor END) AS carbs,
            MAX(CASE WHEN n.componente = 'Lipídeos..g.'      THEN n.valor END) AS fat,
            ({count_expr})                     AS word_score,
            similarity(lower(a.descricao), %s) AS sim_score
        FROM alimento a
        LEFT JOIN nutriente n ON n.codigo_alimento = a.codigo
        WHERE ({or_clauses}) OR similarity(lower(a.descricao), %s) > 0.2
        GROUP BY a.codigo, a.descricao, a.classe
        ORDER BY word_score DESC, sim_score DESC, length(a.descricao)
        LIMIT 10
    """
    params = like_params + [query] + like_params + [query]

    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "id":          row["codigo"],
            "description": row["descricao"],
            "category":    row["classe"],
            "macros": {
                "kcal":    float(row["kcal"]    or 0),
                "protein": float(row["protein"] or 0),
                "carbs":   float(row["carbs"]   or 0),
                "fat":     float(row["fat"]     or 0),
            },
        }
        for row in rows
    ]

MERCADO_DDL = """
    CREATE TABLE IF NOT EXISTS parceiros (
        id        SERIAL PRIMARY KEY,
        nome      TEXT NOT NULL,
        logo_url  TEXT,
        site_url  TEXT,
        ativo     BOOLEAN NOT NULL DEFAULT true,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
    );
 
    CREATE TABLE IF NOT EXISTS produtos (
        id            TEXT PRIMARY KEY,          -- ex: "prod_123"
        parceiro_id   INT  NOT NULL REFERENCES parceiros(id) ON DELETE CASCADE,
        nome          TEXT NOT NULL,
        marca         TEXT,
        imagem_url    TEXT,
        preco_atual   NUMERIC(10,2) NOT NULL,
        preco_antigo  NUMERIC(10,2),             -- NULL = sem desconto
        quantidade_g  NUMERIC(10,1),
        url_compra    TEXT NOT NULL,
        categoria     TEXT,                      -- "Proteína", "Carboidrato", etc.
        kcal          NUMERIC(8,1) DEFAULT 0,
        proteinas     NUMERIC(8,1) DEFAULT 0,
        carboidratos  NUMERIC(8,1) DEFAULT 0,
        gorduras      NUMERIC(8,1) DEFAULT 0,
        ativo         BOOLEAN NOT NULL DEFAULT true,
        criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
"""


def listar_parceiros() -> list[dict]:
    """Retorna todos os parceiros ativos."""
    with conn() as c, c.cursor() as cur:
        cur.execute("""
            SELECT id, nome, logo_url, site_url
            FROM   parceiros
            WHERE  ativo = true
            ORDER  BY nome
        """)
        rows = cur.fetchall()
    return [
        {
            "id":       str(row["id"]),
            "nome":     row["nome"],
            "logo_url": row["logo_url"] or "",
            "site_url": row["site_url"] or "",
        }
        for row in rows
    ]


def listar_produtos_ativos() -> list[dict]:
    """
    Retorna todos os produtos ativos junto com nome e logo do parceiro.
    Usado pelo serviço de recomendação para montar o catálogo.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute("""
            SELECT
                p.id, p.nome, p.marca,
                p.imagem_url, p.preco_atual, p.preco_antigo,
                p.quantidade_g, p.url_compra, p.categoria,
                p.kcal, p.proteinas, p.carboidratos, p.gorduras,
                pa.nome     AS nome_mercado,
                pa.logo_url AS logo_mercado
            FROM   produtos  p
            JOIN   parceiros pa ON pa.id = p.parceiro_id
            WHERE  p.ativo = true AND pa.ativo = true
            ORDER  BY p.categoria, p.nome
        """)
        rows = cur.fetchall()

    return [
        {
            "id":            row["id"],
            "nome":          row["nome"],
            "marca":         row["marca"] or "",
            "imagem_url":    row["imagem_url"] or "",
            "preco_atual":   float(row["preco_atual"]),
            "preco_antigo":  float(row["preco_antigo"]) if row["preco_antigo"] else None,
            "quantidade_g":  float(row["quantidade_g"] or 0),
            "url_compra":    row["url_compra"],
            "categoria":     row["categoria"] or "",
            "kcal":          float(row["kcal"] or 0),
            "proteinas":     float(row["proteinas"] or 0),
            "carboidratos":  float(row["carboidratos"] or 0),
            "gorduras":      float(row["gorduras"] or 0),
            "nome_mercado":  row["nome_mercado"],
            "logo_mercado":  row["logo_mercado"] or "",
        }
        for row in rows
    ]
