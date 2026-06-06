# Inserat-Tool

A local web app that turns product photos into ready-to-publish listings for **eBay** and **Kleinanzeigen** using Claude AI vision. Upload one or more photos, get a complete listing draft with title, HTML description, tags, and a market price suggestion — all in German.

<img width="1439" height="784" alt="image" src="https://github.com/user-attachments/assets/fbe5e8e9-a027-4028-8214-5d02177a0022" />


## Features

- Drag-and-drop image upload (JPG, PNG, WEBP, multiple files)
- AI-powered product analysis via Claude Vision (condition, brand, category, features)
- Listing generation for eBay (HTML description, ≤ 80 char title) and Kleinanzeigen (plain text, ≤ 60 char title)
- Live HTML description preview
- Market price research via eBay Browse API (min / max / average / median / suggested price)
- All output in German

## Tech Stack

| Layer    | Technology                              |
|----------|-----------------------------------------|
| Backend  | Python, FastAPI, uvicorn                |
| Frontend | Vanilla HTML / CSS / JS (no framework)  |
| AI       | Anthropic Python SDK (`claude-sonnet-4-6`) |
| Pricing  | eBay Browse API (OAuth 2.0 client credentials) |

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd inserat-tool
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# eBay (https://developer.ebay.com/my/keys)
EBAY_CLIENT_ID=YourApp-...
EBAY_CLIENT_SECRET=YourSecret-...

# Set to true to use eBay Sandbox for publishing (Phase 3)
# Price research always uses Production regardless of this setting
EBAY_SANDBOX=false
```

### 4. Start the app

```bash
./start.sh
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

> **Note:** `start.sh` activates the venv and launches uvicorn with hot-reload.  
> Make sure it is executable: `chmod +x start.sh`

## Project Structure

```
inserat-tool/
├── backend/
│   ├── main.py                    # FastAPI app, /api/analyze endpoint
│   └── modules/
│       ├── image_analyzer.py      # Claude Vision → structured product data
│       ├── listing_generator.py   # Generates eBay / Kleinanzeigen listings
│       └── price_researcher.py    # eBay Browse API price research
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── .env                           # Not committed
├── start.sh
└── README.md
```

## Roadmap

- [x] Phase 1 — Image upload, AI analysis, editable review UI
- [x] Phase 2 — eBay market price research
- [ ] Phase 3 — eBay API publishing + Kleinanzeigen via Playwright
