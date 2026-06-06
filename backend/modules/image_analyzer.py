import base64
import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"


def _get_media_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


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

    content = []
    for path in image_paths:
        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _get_media_type(path),
                "data": image_data,
            },
        })

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
