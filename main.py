from fastapi import FastAPI
from routes.routes import router
from routes.mercado_routes import mercado_router
from fastapi.staticfiles import StaticFiles
app = FastAPI(title="NutriEngine API")


# Rotas
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.include_router(router)
app.include_router(mercado_router)