#!/bin/bash
# Einmalige Einrichtung: venv, Python-Pakete, Chromium für Playwright, .env
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 nicht gefunden. Bitte Python 3.9 oder neuer installieren."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "→ Lege virtuelle Umgebung an (.venv)"
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "→ Installiere Python-Pakete"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r backend/requirements.txt

echo "→ Installiere Chromium für Kleinanzeigen-Veröffentlichung"
python -m playwright install chromium

if [ ! -f .env ]; then
  cp .env.example .env
  echo "→ .env aus .env.example angelegt"
fi

chmod +x start.sh

echo ""
echo "✅ Fertig."
if ! grep -qE '^ANTHROPIC_API_KEY=.+' .env; then
  echo "   1. Trage deinen ANTHROPIC_API_KEY in die .env ein"
  echo "   2. Starte mit ./start.sh und öffne http://localhost:8000"
else
  echo "   Starte mit ./start.sh und öffne http://localhost:8000"
fi
