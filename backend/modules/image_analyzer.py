import base64
import io
import json
import os
import re

import anthropic
from dotenv import load_dotenv
from PIL import Image, ImageOps

load_dotenv()

MODEL = "claude-sonnet-4-6"

# Anthropic empfiehlt max. 1568 px an der langen Kante; größere Bilder werden
# ohnehin serverseitig herunterskaliert. Wir verkleinern lokal vorab, damit die
# Request-Größe (Base64!) auch bei mehreren Fotos unter dem API-Limit bleibt.
MAX_EDGE = 1568
JPEG_QUALITY = 85


def _encode_image(path: str) -> dict:
    """Lädt ein Bild, skaliert es herunter und liefert einen Base64-JPEG-Block."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)  # EXIF-Rotation anwenden
        img = img.convert("RGB")
        img.thumbnail((MAX_EDGE, MAX_EDGE))  # behält Seitenverhältnis bei
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=JPEG_QUALITY)

    data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": data,
        },
    }


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def analyze_images(image_paths: list[str]) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    content = [_encode_image(path) for path in image_paths]

    content.append({
        "type": "text",
        "text": (
            "Analysiere die Bilder und gib eine strukturierte JSON-Antwort zurück.\n\n"
            "Antworte NUR mit einem JSON-Objekt (kein Markdown, keine Erklärungen):\n"
            "{\n"
            '  "artikel_name": "Präziser Name des Artikels",\n'
            '  "zustand": "Neu|Wie neu|Sehr gut|Gut|Akzeptabel",\n'
            '  "zustand_beschreibung": "Detaillierte Beschreibung des Zustands",\n'
            '  "features": ["Feature 1", "Feature 2"],\n'
            '  "marke": "Markenname oder leerer String wenn unbekannt",\n'
            '  "kategorie_vorschlag": "Passende Produktkategorie",\n'
            '  "besonderheiten": "Besondere Merkmale oder Auffälligkeiten"\n'
            "}"
        ),
    })

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system="Du bist ein Experte für gebrauchte Artikel. Analysiere die Bilder präzise und objektiv auf Deutsch.",
        messages=[{"role": "user", "content": content}],
    )

    return _extract_json(response.content[0].text)
