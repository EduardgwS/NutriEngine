import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DICAS_PATH = BASE_DIR / "data" / "dicas.json"

with open(DICAS_PATH, "r", encoding="utf-8") as f:
    CATALOGO = json.load(f)


def selecionar_dica(maior_deficit: int, proteina_consumida: float):
    lista = CATALOGO.get(str(maior_deficit))

    if lista is None:
        return None

    seed = int(proteina_consumida * 10)

    return lista[seed % len(lista)]