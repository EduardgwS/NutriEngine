from fastapi import FastAPI
from database import init_db
from routes import router

app = FastAPI(title="NutriEngine API")

# Cria aquela merda daquelas tabelas do banco se n existirem
init_db()

# rotas, todas esburacadas
app.include_router(router)
