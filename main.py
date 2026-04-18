from fastapi import FastAPI
from database import init_db
from routes import router

app = FastAPI(title="NutriEngine API")

# Tabelas
init_db()

# Rotas
app.include_router(router)
