import os
import shutil
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modules.ebay_auth import exchange_code_for_token, get_auth_url
from modules.ebay_publisher import publish_to_ebay
from modules.image_analyzer import analyze_images
from modules.kleinanzeigen_publisher import PROFILE_DIR as KA_PROFILE_DIR
from modules.kleinanzeigen_publisher import publish_to_kleinanzeigen
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
ENV_PATH     = Path(__file__).parent.parent / ".env"
# Images are kept here after analysis so the publish endpoint can re-use them.
UPLOADS_DIR  = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


# ── Analyze ────────────────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(
    images: list[UploadFile] = File(...),
    platforms: str = Form("ebay,kleinanzeigen"),
):
    if not images:
        raise HTTPException(status_code=400, detail="Keine Bilder hochgeladen")

    selected = {p.strip() for p in platforms.split(",") if p.strip()}
    if not selected:
        raise HTTPException(status_code=400, detail="Keine Plattform ausgewählt")

    session_dir = UPLOADS_DIR / str(uuid.uuid4())
    session_dir.mkdir()
    try:
        image_paths = []
        for image in images:
            suffix = Path(image.filename or "image.jpg").suffix or ".jpg"
            dest = session_dir / f"{len(image_paths)}{suffix}"
            content = await image.read()
            dest.write_bytes(content)
            image_paths.append(str(dest))

        # Bildanalyse + Preisrecherche werden immer gebraucht; die platt-
        # formspezifische Inserat-Generierung nur für die ausgewählten.
        analyse        = analyze_images(image_paths)
        ebay           = generate_listing(analyse, "ebay") if "ebay" in selected else None
        kleinanzeigen  = generate_listing(analyse, "kleinanzeigen") if "kleinanzeigen" in selected else None
        preisrecherche = research_price(analyse)

        return {
            "analyse":        analyse,
            "ebay":           ebay,
            "kleinanzeigen":  kleinanzeigen,
            "preisrecherche": preisrecherche,
            "image_paths":    image_paths,
        }
    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


class GenerateBody(BaseModel):
    analyse:  dict
    platform: str


@app.post("/api/generate")
async def generate(body: GenerateBody):
    if body.platform not in ("ebay", "kleinanzeigen"):
        raise HTTPException(status_code=400, detail="Ungültige Plattform")
    try:
        listing = generate_listing(body.analyse, body.platform)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"listing": listing}


# ── eBay Publishing ────────────────────────────────────────────────────────────

class PublishEbayBody(BaseModel):
    listing:     dict
    image_paths: list[str]


@app.post("/api/publish/ebay")
async def publish_ebay(body: PublishEbayBody):
    for path in body.image_paths:
        if not Path(path).is_file():
            raise HTTPException(status_code=400, detail=f"Bilddatei nicht gefunden: {path}")
    result = publish_to_ebay(body.listing, body.image_paths)
    return result


# ── Kleinanzeigen Publishing ─────────────────────────────────────────────────────

class PublishKaBody(BaseModel):
    listing:     dict
    image_paths: list[str]


# Sync-Endpoint (def, nicht async): FastAPI führt ihn im Threadpool aus, sodass
# die Playwright-Sync-API nicht im laufenden asyncio-Loop kollidiert.
@app.post("/api/publish/kleinanzeigen")
def publish_kleinanzeigen(body: PublishKaBody):
    for path in body.image_paths:
        if not Path(path).is_file():
            raise HTTPException(status_code=400, detail=f"Bilddatei nicht gefunden: {path}")
    return publish_to_kleinanzeigen(body.listing, body.image_paths)


@app.get("/auth/kleinanzeigen/status")
async def kleinanzeigen_status():
    # Profil existiert + enthält Daten -> es gab mindestens einen Login.
    connected = KA_PROFILE_DIR.is_dir() and any(KA_PROFILE_DIR.iterdir())
    return {"connected": connected}


# ── eBay OAuth ─────────────────────────────────────────────────────────────────

@app.get("/auth/ebay")
async def ebay_auth():
    return {"auth_url": get_auth_url()}


@app.get("/auth/ebay/status")
async def ebay_status():
    return {"connected": bool(os.environ.get("EBAY_ACCESS_TOKEN", ""))}


class CallbackBody(BaseModel):
    code: str


@app.post("/auth/ebay/callback")
async def ebay_callback(body: CallbackBody):
    try:
        tokens = exchange_code_for_token(body.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    set_key(str(ENV_PATH), "EBAY_ACCESS_TOKEN",  tokens["access_token"])
    set_key(str(ENV_PATH), "EBAY_REFRESH_TOKEN", tokens["refresh_token"])
    os.environ["EBAY_ACCESS_TOKEN"]  = tokens["access_token"]
    os.environ["EBAY_REFRESH_TOKEN"] = tokens["refresh_token"]

    return {"success": True}


# ── Static frontend (must be last) ─────────────────────────────────────────────

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
