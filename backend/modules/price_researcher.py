import base64
import os
import re
import statistics
import time

import requests
from dotenv import load_dotenv

load_dotenv()

# Preisrecherche läuft immer gegen den Production-Endpoint, da die Sandbox
# keine realen Marktdaten enthält. EBAY_SANDBOX gilt nur für Phase 3 (Publishing).
_TOKEN_URL  = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

_EMPTY_RESULT = {
    "min_preis":      None,
    "max_preis":      None,
    "durchschnitt":   None,
    "median":         None,
    "vorschlag":      None,
    "anzahl_treffer": None,
    "beispiele":      [],
}

# Modulweiter Token-Cache: verhindert einen neuen Auth-Request pro Suche
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _get_app_token() -> str:
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    client_id     = os.getenv("EBAY_CLIENT_ID", "")
    client_secret = os.getenv("EBAY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError("EBAY_CLIENT_ID oder EBAY_CLIENT_SECRET nicht gesetzt")

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope":      "https://api.ebay.com/oauth/api_scope",
        },
        timeout=10,
    )
    print(f"[price_researcher] Token-Status: {resp.status_code}", flush=True)
    resp.raise_for_status()

    token_data = resp.json()
    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"]   = time.time() + int(token_data.get("expires_in", 7200))
    return _token_cache["access_token"]


def _psychological_price(value: float) -> float:
    if value < 1:
        return value
    if value < 10:
        return round(value - 0.1, 1)
    if value < 100:
        floored = int(value)
        remainder = floored % 10
        base = floored - remainder
        return float(base + 9 if remainder > 0 else floored - 1)
    remainder = int(value) % 100
    base = int(value) - remainder
    if remainder > 0:
        return float(base + 99) if base + 99 < value else float(base - 1)
    return float(int(value) - 1)


_NOISE_PHRASES = re.compile(
    r"\b(deutsche[rn]?\s+version|europäische[rn]?\s+ausgabe|"
    r"limited\s+edition|special\s+edition|game\s+of\s+the\s+year|"
    r"collector['']?s\s+edition|complete\s+edition|definitive\s+edition|"
    r"bundle|set|paket)\b",
    re.IGNORECASE,
)


def _build_query(artikel: str, marke: str) -> str:
    cleaned = re.sub(r"[–—:/()\[\]{}&+]", " ", artikel)
    cleaned = _NOISE_PHRASES.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    words = cleaned.split()[:5]

    if marke and marke.lower() not in " ".join(words).lower():
        words.insert(0, marke)

    return " ".join(words)[:80].strip()


def research_price(analysis: dict) -> dict:
    print("=== PREISRECHERCHE GESTARTET ===", flush=True)

    artikel = analysis.get("artikel_name", "")
    marke   = analysis.get("marke", "")
    query   = _build_query(artikel, marke)
    print(f"[price_researcher] Query: {query!r}", flush=True)
    if not query:
        return _EMPTY_RESULT

    try:
        token = _get_app_token()
    except Exception as exc:
        print(f"[price_researcher] Token-Fehler: {exc}", flush=True)
        return {**_EMPTY_RESULT, "fehler": str(exc)}

    try:
        resp = requests.get(
            _SEARCH_URL,
            headers={
                "Authorization":           f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
            },
            params={
                "q":      query,
                "filter": "buyingOptions:{FIXED_PRICE}",
                "limit":  "20",
            },
            timeout=10,
        )
        print(f"[price_researcher] URL:    {resp.url}", flush=True)
        print(f"[price_researcher] Status: {resp.status_code}", flush=True)
        print(f"[price_researcher] Body:   {resp.text[:500]}", flush=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {**_EMPTY_RESULT, "fehler": str(exc)}

    items = data.get("itemSummaries", [])
    total = data.get("total", 0)

    if not items:
        return _EMPTY_RESULT

    preise    = []
    beispiele = []

    for item in items:
        try:
            preis = float(item["price"]["value"])
            preise.append(preis)
        except (KeyError, ValueError, TypeError):
            continue

        if len(beispiele) < 5:
            beispiele.append({
                "titel": item.get("title", ""),
                "preis": preis,
                "datum": "",
            })

    if not preise:
        return _EMPTY_RESULT

    avg    = round(statistics.mean(preise), 2)
    median = round(statistics.median(preise), 2)

    return {
        "min_preis":      round(min(preise), 2),
        "max_preis":      round(max(preise), 2),
        "durchschnitt":   avg,
        "median":         median,
        "vorschlag":      _psychological_price(median),
        "anzahl_treffer": total,
        "beispiele":      beispiele,
    }
