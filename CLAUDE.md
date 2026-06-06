# Inserat-Tool

Lokale Web-App zum automatischen Erstellen von eBay- und Kleinanzeigen-Inseraten aus Fotos.

## Stack
- Backend: Python, FastAPI, uvicorn
- Frontend: Vanilla HTML/CSS/JS (kein Framework)
- KI: Anthropic Python SDK (claude-sonnet-4-6)
- Umgebungsvariablen: python-dotenv, .env-Datei

## Projektstruktur
inserat-tool/
├── backend/
│   ├── main.py
│   ├── modules/
│   │   ├── image_analyzer.py
│   │   ├── listing_generator.py
│   │   ├── price_researcher.py
│   │   ├── ebay_publisher.py
│   │   └── kleinanzeigen_publisher.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── .env
└── CLAUDE.md

Aktualisiere in CLAUDE.md den Abschnitt "Aktueller Stand":
Phase 1: Upload + KI-Analyse + Review-UI ✅
Phase 2: Preisrecherche (eBay Browse API + Kleinanzeigen Scraping) ✅
Phase 3: eBay Publishing + Kleinanzeigen Playwright (ausstehend)

## Hinweise
- Alle Inserate auf Deutsch generieren
- Artikel sind hauptsächlich gebraucht, gemischte Kategorien
- Versand oder Abholung je nach Artikel wählbar
- API-Keys kommen aus .env, nie hardcoden

## Lokale Umgebung"

- venv liegt unter .venv/ im Projektroot
- Aktivieren: source .venv/bin/activate
- App starten: cd backend && uvicorn main:app --reload
- pip install immer innerhalb des aktiven venv (kein --break-system-packages nötig)
- Python-Version: 3.9 (System)