# Inserat-Tool

A local web app that turns product photos into ready-to-publish listings for **eBay** and **Kleinanzeigen** using Claude AI vision. Upload one or more photos, get a complete listing draft with title, HTML description, tags, and a market price suggestion — all in German.

<img width="1439" height="784" alt="image" src="https://github.com/user-attachments/assets/fbe5e8e9-a027-4028-8214-5d02177a0022" />


## Schnellstart (zum Testen)

Voraussetzungen: macOS oder Linux, Python 3.9+, ein eigener [Anthropic API-Key](https://console.anthropic.com).

```bash
git clone https://github.com/fivefourtwo/ebay-tool.git
cd ebay-tool
./setup.sh
```

Dann in der `.env` den `ANTHROPIC_API_KEY` eintragen und starten:

```bash
./start.sh
```

Anschließend [http://localhost:8000](http://localhost:8000) öffnen.

**Was ohne eBay-Keys funktioniert:** Foto-Upload, KI-Analyse, Inserat-Generierung und Veröffentlichen auf Kleinanzeigen. Beim ersten Kleinanzeigen-Inserat öffnet sich ein Chrome-Fenster, in dem du dich einmal selbst einloggst. Die Session bleibt lokal gespeichert.
**Nur mit eBay-Keys:** Preisrecherche und Veröffentlichen auf eBay (siehe `.env.example`).

> Bitte immer eigene Keys und Konten verwenden. Die `.env` und das Kleinanzeigen-Profil bleiben lokal und werden nie committet.

## Features

- Drag-and-drop image upload (JPG, PNG, WEBP, multiple files)
- AI-powered product analysis via Claude Vision (condition, brand, category, features)
- Listing generation for eBay (HTML description, ≤ 80 char title) and Kleinanzeigen (plain text, ≤ 60 char title)
- Live HTML description preview
- Market price research via eBay Browse API (min / max / average / median / suggested price)
- eBay publishing via OAuth + Inventory/Offer API (category & condition resolved automatically)
- Kleinanzeigen publishing via Playwright (visible browser, persistent login session)
- All output in German

## Tech Stack

| Layer      | Technology                              |
|------------|-----------------------------------------|
| Backend    | Python, FastAPI, uvicorn                |
| Frontend   | Vanilla HTML / CSS / JS + Bootstrap 5.3.8 (locally hosted) |
| AI         | Anthropic Python SDK (`claude-sonnet-4-6`) |
| Pricing    | eBay Browse API (OAuth 2.0 client credentials) |
| Publishing | eBay Sell APIs, Playwright (Chromium) for Kleinanzeigen |

## Manuelle Einrichtung

`setup.sh` erledigt diese Schritte automatisch:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install chromium
cp .env.example .env   # dann Werte eintragen
```

## Project Structure

```
ebay-tool/
├── backend/
│   ├── main.py                        # FastAPI app, API + OAuth endpoints
│   └── modules/
│       ├── image_analyzer.py          # Claude Vision → structured product data
│       ├── listing_generator.py       # Generates eBay / Kleinanzeigen listings
│       ├── price_researcher.py        # eBay Browse API price research
│       ├── ebay_auth.py               # eBay OAuth flow
│       ├── ebay_publisher.py          # eBay Inventory/Offer/Publish
│       └── kleinanzeigen_publisher.py # Playwright automation
├── frontend/                          # index.html, style.css, app.js
├── tests/
├── .env.example                       # Vorlage für .env (nicht committet)
├── setup.sh                           # Einmalige Einrichtung
├── start.sh                           # App starten
└── README.md
```

## Roadmap

- [x] Phase 1 — Image upload, AI analysis, editable review UI
- [x] Phase 2 — eBay market price research
- [x] Phase 3a — eBay API publishing
- [x] Phase 3b — Kleinanzeigen publishing via Playwright

## Oberfläche

Eine einzelne Werkzeugseite für Fotos, Plattformwahl und Inseratbearbeitung.
Konten und Preisvergleich sind aufklappbar. Gestaltung nach
[fabricerio.com](https://www.fabricerio.com/): Hellgrau, Schwarz, Sora und IBM Plex Sans.
Bootstrap und Schriften werden lokal ausgeliefert.

Entwürfe bleiben innerhalb desselben Browser-Tabs nach Neuladen erhalten.
[Technische Hinweise](docs/design-and-ux.md).

```bash
.venv/bin/python -m unittest discover -s tests -v
```
