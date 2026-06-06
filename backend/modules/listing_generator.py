import json
import os
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"

_EBAY_PROMPT = """Erstelle ein eBay-Inserat auf Deutsch basierend auf der Artikelanalyse.

Regeln:
- titel: MAXIMAL 80 Zeichen, prägnant und suchoptimiert (Marke, Modell, Zustand)
- beschreibung: HTML-Format mit <h2>-Überschriften und <ul>-Listen, professionell und überzeugend
- kategorie: eBay-Kategorie-ID als Zahl-String (z.B. "9355" für Handys, "1249" für Notebooks)
- tags: 5-10 relevante Suchbegriffe als Array

Antworte NUR mit JSON:
{
  "titel": "...",
  "beschreibung": "<h2>Beschreibung</h2><p>...</p><h2>Eigenschaften</h2><ul><li>...</li></ul>",
  "kategorie": "12345",
  "tags": ["tag1", "tag2"]
}"""

_KLEINANZEIGEN_PROMPT = """Erstelle ein Kleinanzeigen-Inserat auf Deutsch basierend auf der Artikelanalyse.

Regeln:
- titel: MAXIMAL 60 Zeichen, klar und direkt
- beschreibung: Reiner Plaintext ohne HTML, freundlich und informativ, max. 1500 Zeichen
- kategorie: Kleinanzeigen-Kategorie als Text (z.B. "Elektronik > Handys")
- tags: 5 relevante Suchbegriffe als Array

Antworte NUR mit JSON:
{
  "titel": "...",
  "beschreibung": "...",
  "kategorie": "...",
  "tags": ["tag1", "tag2"]
}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def generate_listing(analysis: dict, plattform: str) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = _EBAY_PROMPT if plattform == "ebay" else _KLEINANZEIGEN_PROMPT
    analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=(
            "Du bist ein Experte für Online-Marktplätze und erstellst "
            "überzeugende Verkaufsinserate auf Deutsch."
        ),
        messages=[{
            "role": "user",
            "content": f"{prompt}\n\nArtikelanalyse:\n{analysis_text}",
        }],
    )

    return _extract_json(response.content[0].text)
