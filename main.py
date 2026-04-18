from fastapi import FastAPI
from database import init_db
from routes import router
from mercado_routes import mercado_router

app = FastAPI(title="NutriEngine API")

# Tabelas
init_db()

# Rotas
app.include_router(router)
app.include_router(mercado_router)