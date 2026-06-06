import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from modules.image_analyzer import analyze_images
from modules.listing_generator import generate_listing
from modules.price_researcher import research_price

load_dotenv()

app = FastAPI(title="Inserat-Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.post("/api/analyze")
async def analyze(images: list[UploadFile] = File(...)):
    if not images:
        raise HTTPException(status_code=400, detail="Keine Bilder hochgeladen")

    tmp_dir = tempfile.mkdtemp()
    try:
        image_paths = []
        for image in images:
            suffix = Path(image.filename or "image.jpg").suffix or ".jpg"
            tmp_path = os.path.join(tmp_dir, f"{len(image_paths)}{suffix}")
            content = await image.read()
            with open(tmp_path, "wb") as f:
                f.write(content)
            image_paths.append(tmp_path)

        analyse = analyze_images(image_paths)
        ebay = generate_listing(analyse, "ebay")
        kleinanzeigen = generate_listing(analyse, "kleinanzeigen")
        preisrecherche = research_price(analyse)

        return {
            "analyse": analyse,
            "ebay": ebay,
            "kleinanzeigen": kleinanzeigen,
            "preisrecherche": preisrecherche,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
