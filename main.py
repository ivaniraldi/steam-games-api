from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware  # Importar CORSMiddleware
import pandas as pd
from typing import Optional
import json
import csv

app = FastAPI(title="Games API", description="API para consultar datos de juegos desde un archivo CSV")

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todos los orígenes (puedes restringirlo a tu dominio)
    allow_credentials=True,
    allow_methods=["*"],  # Permitir todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permitir todos los encabezados
)

# Cargar el CSV con manejo de errores
try:
    df = pd.read_csv(
        "games.csv",
        dtype={
            "app_id": int,
            "name": str,
            "release_date": str,
            "is_free": bool,
            "price_overview": str,
            "languages": str,
            "type": str
        },
        low_memory=False,
        quoting=csv.QUOTE_ALL,
        escapechar='\\',
        on_bad_lines='warn',
        encoding='utf-8'
    )
except Exception as e:
    print(f"Error al cargar el CSV: {e}")
    raise

# Función para parsear price_overview
def parse_price_overview(price_str):
    if pd.isna(price_str) or price_str == "\\N":
        return None
    try:
        return json.loads(price_str.replace("'", "\""))
    except:
        return None

df["price_overview"] = df["price_overview"].apply(parse_price_overview)

@app.get("/games/{app_id}")
async def get_game_by_id(app_id: int):
    game = df[df["app_id"] == app_id]
    if game.empty:
        raise HTTPException(status_code=404, detail="Juego no encontrado")
    return game.to_dict(orient="records")[0]

@app.get("/games/")
async def get_games(
    name: Optional[str] = None,
    is_free: Optional[bool] = None,
    type: Optional[str] = None,
    language: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = 10,
    offset: int = 0
):
    result = df
    if name:
        result = result[result["name"].str.contains(name, case=False, na=False)]
    if is_free is not None:
        result = result[result["is_free"] == is_free]
    if type:
        result = result[result["type"].str.lower() == type.lower()]
    if language:
        result = result[result["languages"].str.contains(language, case=False, na=False)]
    if max_price is not None:
        result = result[result["price_overview"].apply(
            lambda x: x["final"] / 100 <= max_price if x and "final" in x else False
        )]
    total = len(result)
    result = result.iloc[offset:offset + limit]
    if result.empty:
        return {"total": total, "games": []}
    return {
        "total": total,
        "games": result.to_dict(orient="records")
    }

@app.get("/stats/")
async def get_stats():
    stats = {
        "total_games": len(df),
        "free_games": len(df[df["is_free"] == True]),
        "paid_games": len(df[df["is_free"] == False]),
        "types": df["type"].value_counts().to_dict()
    }
    return stats

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)