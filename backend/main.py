import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modules.ebay_auth import exchange_code_for_token, get_auth_url
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
ENV_PATH     = Path(__file__).parent.parent / ".env"


# ── Analyze ────────────────────────────────────────────────────────────────────

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

        analyse        = analyze_images(image_paths)
        ebay           = generate_listing(analyse, "ebay")
        kleinanzeigen  = generate_listing(analyse, "kleinanzeigen")
        preisrecherche = research_price(analyse)

        return {
            "analyse":        analyse,
            "ebay":           ebay,
            "kleinanzeigen":  kleinanzeigen,
            "preisrecherche": preisrecherche,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── eBay OAuth ─────────────────────────────────────────────────────────────────

@app.get("/auth/ebay")
async def ebay_auth():
    return {"auth_url": get_auth_url()}


@app.get("/auth/ebay/status")
async def ebay_status():
    connected = bool(os.environ.get("EBAY_ACCESS_TOKEN", ""))
    return {"connected": connected}


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

    # Make tokens available in the current process without restart
    os.environ["EBAY_ACCESS_TOKEN"]  = tokens["access_token"]
    os.environ["EBAY_REFRESH_TOKEN"] = tokens["refresh_token"]

    return {"success": True}


# ── Static frontend (must be last) ─────────────────────────────────────────────

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
