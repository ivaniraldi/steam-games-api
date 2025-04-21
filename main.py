import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from typing import Optional
import json
import csv
import re

app = FastAPI(title="Games API", description="API para consultar datos de juegos desde un archivo CSV y scrapear datos de Steam")

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# Función del scraper de Steam
def scrape_steam_app(url: str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        game_info = {}
        
        title = soup.find('div', id='appHubAppName')
        game_info['title'] = title.text.strip() if title else 'N/A'
        
        price = soup.find('div', class_='game_purchase_price')
        game_info['price'] = price.text.strip() if price else 'N/A'
        
        discount_price = soup.find('div', class_='discount_final_price')
        game_info['discount_price'] = discount_price.text.strip() if discount_price else 'N/A'
        
        description = soup.find('div', class_='game_description_snippet')
        game_info['description'] = description.text.strip() if description else 'N/A'
        
        release_date = soup.find('div', class_='date')
        game_info['release_date'] = release_date.text.strip() if release_date else 'N/A'
        
        developer = soup.find('div', id='developers_list')
        game_info['developer'] = developer.text.strip() if developer else 'N/A'
        
        publisher = soup.find('div', class_='summary column', id='game_area_publisher')
        game_info['publisher'] = publisher.text.strip() if publisher else 'N/A'
        
        tags = soup.find_all('a', class_='app_tag')
        game_info['tags'] = [tag.text.strip() for tag in tags] if tags else []
        
        reviews = soup.find('span', class_='game_review_summary')
        review_count = soup.find('meta', itemprop='reviewCount')
        game_info['reviews'] = {
            'summary': reviews.text.strip() if reviews else 'N/A',
            'count': review_count['content'] if review_count else 'N/A'
        }
        
        requirements = soup.find_all('div', class_='game_area_sys_req')
        game_info['system_requirements'] = []
        for req in requirements:
            req_type = req.find('h2')
            req_details = req.find_all('li')
            req_dict = {
                'type': req_type.text.strip() if req_type else 'N/A',
                'details': [detail.text.strip() for detail in req_details]
            }
            game_info['system_requirements'].append(req_dict)
        
        features = soup.find('div', class_='game_area_features_list')
        game_info['features'] = [feature.text.strip() for feature in features.find_all('a')] if features else []
        
        screenshots = soup.find_all('a', class_='highlight_screenshot_link')
        game_info['screenshots'] = [img['href'] for img in screenshots if img.get('href')] if screenshots else []
        
        videos = soup.find('div', class_='highlight_player_item highlight_movie')
        game_info['videos'] = videos['data-mp4-source'] if videos and videos.get('data-mp4-source') else 'N/A'
        
        platforms = soup.find_all('div', class_='game_area_purchase_platform')
        game_info['platforms'] = []
        for platform in platforms:
            platform_spans = platform.find_all('span', class_='platform_img')
            game_info['platforms'].extend([span['class'][1] for span in platform_spans])
        
        return game_info
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error al hacer la solicitud HTTP: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante el scraping: {str(e)}")

# Endpoint para consultar juegos por app_id desde el CSV
@app.get("/games/{app_id}")
async def get_game_by_id(app_id: int):
    game = df[df["app_id"] == app_id]
    if game.empty:
        raise HTTPException(status_code=404, detail="Juego no encontrado")
    return game.to_dict(orient="records")[0]

# Endpoint para consultar juegos con filtros desde el CSV
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

# Endpoint para estadísticas desde el CSV
@app.get("/stats/")
async def get_stats():
    stats = {
        "total_games": len(df),
        "free_games": len(df[df["is_free"] == True]),
        "paid_games": len(df[df["is_free"] == False]),
        "types": df["type"].value_counts().to_dict()
    }
    return stats

# Nuevo endpoint para scrapear datos de Steam
@app.get("/scrape_game/")
async def scrape_game(url: str):
    if not url.startswith("https://store.steampowered.com/app/"):
        raise HTTPException(status_code=400, detail="La URL debe ser una página válida de Steam (https://store.steampowered.com/app/)")
    return scrape_steam_app(url)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)