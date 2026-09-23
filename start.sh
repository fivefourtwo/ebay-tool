#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "❌ Noch nicht eingerichtet. Bitte zuerst ./setup.sh ausführen."
  exit 1
fi
source .venv/bin/activate
cd backend
uvicorn main:app --reload
