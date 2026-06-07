import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv, set_key

from modules.ebay_auth import get_valid_token, refresh_access_token

load_dotenv()

API_BASE          = "https://api.ebay.com"
TRADING_URL       = "https://api.ebay.com/ws/api.dll"
CATEGORY_TREE_ID  = "77"  # eBay Deutschland
AI_MODEL          = "claude-sonnet-4-6"

# eBay-Zustände sind kategorieabhängig. Wir kennen die conditionId<->Enum-
# Zuordnung der Inventory API und wählen pro Kategorie den passenden gültigen
# Zustand aus (siehe _resolve_condition).
_ID_TO_ENUM = {
    "1000": "NEW",
    "1500": "NEW_OTHER",
    "1750": "NEW_WITH_DEFECTS",
    "2750": "LIKE_NEW",
    "3000": "USED_EXCELLENT",       # generisches "Gebraucht" – die meisten Kategorien
    "4000": "USED_VERY_GOOD",       # nur Medien (Spiele, Bücher, Musik, Filme)
    "5000": "USED_GOOD",            # nur Medien
    "6000": "USED_ACCEPTABLE",      # nur Medien
    "7000": "FOR_PARTS_OR_NOT_WORKING",
}

# Pro Nutzer-Zustand bevorzugte conditionIds, beste Übereinstimmung zuerst.
# So fällt z.B. "Sehr gut" in Nicht-Medien-Kategorien sauber auf 3000 zurück.
_GRADE_PREFERENCE = {
    "Neu":        ["1000", "1500", "2750"],
    "Wie neu":    ["2750", "1500", "3000", "4000"],
    "Sehr gut":   ["4000", "3000", "2750", "5000"],
    "Gut":        ["5000", "3000", "4000", "6000"],
    "Akzeptabel": ["6000", "7000", "3000", "5000"],
}


def _json_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }


# ── Schritt 1 ─────────────────────────────────────────────────────────────────

def _ensure_location(token: str) -> None:
    print("[ebay_publisher] Schritt 1: Merchant Location prüfen...", flush=True)
    resp = requests.get(
        f"{API_BASE}/sell/inventory/v1/location",
        headers=_json_headers(token),
        timeout=15,
    )
    resp.raise_for_status()

    if resp.json().get("total", 0) > 0:
        print("[ebay_publisher] Location bereits vorhanden.", flush=True)
        return

    print("[ebay_publisher] Erstelle Location 'home'...", flush=True)
    resp = requests.post(
        f"{API_BASE}/sell/inventory/v1/location/home",
        headers=_json_headers(token),
        json={
            "location": {
                "address": {
                    "addressLine1": os.environ.get("EBAY_LOCATION_STREET", ""),
                    "city":         os.environ.get("EBAY_LOCATION_CITY", ""),
                    "postalCode":   os.environ.get("EBAY_LOCATION_ZIP", ""),
                    "country":      "DE",
                }
            },
            "locationTypes":          ["WAREHOUSE"],
            "name":                   "Zuhause",
            "merchantLocationStatus": "ENABLED",
        },
        timeout=15,
    )
    print(f"[ebay_publisher] Location erstellt: {resp.status_code}", flush=True)
    resp.raise_for_status()


# ── Schritt 2 ─────────────────────────────────────────────────────────────────

_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
         "png": "image/png",  "webp": "image/webp"}

_EBAY_NS = "urn:ebay:apis:eBLBaseComponents"

_XML_PAYLOAD = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<UploadSiteHostedPicturesRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
    "<RequesterCredentials>"
    "<eBayAuthToken>{token}</eBayAuthToken>"
    "</RequesterCredentials>"
    "<PictureSet>Standard</PictureSet>"
    "</UploadSiteHostedPicturesRequest>"
)


def _upload_images(token: str, image_paths: list) -> list:
    print(f"[ebay_publisher] Schritt 2: {len(image_paths)} Bild(er) hochladen (Trading API)...", flush=True)
    image_urls = []

    for path in image_paths:
        p         = Path(path)
        mime_type = _MIME.get(p.suffix.lstrip(".").lower(), "image/jpeg")
        payload   = _XML_PAYLOAD.format(token=token).encode("utf-8")

        resp = requests.post(
            TRADING_URL,
            headers={
                "X-EBAY-API-CALL-NAME":          "UploadSiteHostedPictures",
                "X-EBAY-API-SITEID":              "77",
                "X-EBAY-API-RESPONSE-ENCODING":  "XML",
                "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            },
            files=[
                ("XML Payload", ("payload.xml", payload, "text/xml")),
                ("image",       (p.name, p.read_bytes(), mime_type)),
            ],
            timeout=30,
        )
        print(f"[ebay_publisher] Upload Status: {resp.status_code}", flush=True)
        print(f"[ebay_publisher] Upload Response: {resp.text[:500]}", flush=True)

        if resp.status_code >= 400:
            print("[ebay_publisher] WARNUNG: Bild-Upload fehlgeschlagen, Listing ohne Bilder fortsetzen.", flush=True)
            continue

        try:
            root     = ET.fromstring(resp.text)
            full_url = root.find(f".//{{{_EBAY_NS}}}SiteHostedPictureDetails/{{{_EBAY_NS}}}FullURL")
            if full_url is None:
                # Fallback ohne Namespace (falls Response ihn weglässt)
                full_url = root.find(".//SiteHostedPictureDetails/FullURL")

            if full_url is not None and full_url.text:
                print(f"[ebay_publisher] Image URL: {full_url.text}", flush=True)
                image_urls.append(full_url.text)
            else:
                print("[ebay_publisher] WARNUNG: Kein FullURL in XML-Response, Bild wird übersprungen.", flush=True)
        except ET.ParseError as exc:
            print(f"[ebay_publisher] WARNUNG: XML-Parse-Fehler: {exc}, Bild wird übersprungen.", flush=True)

    print(f"[ebay_publisher] {len(image_urls)}/{len(image_paths)} Bilder hochgeladen.", flush=True)
    return image_urls


# ── Schritt 3 ─────────────────────────────────────────────────────────────────

def _valid_condition_ids(token: str, category_id: str):
    """Fragt die gültigen conditionIds für eine Kategorie ab. None bei Fehler."""
    try:
        resp = requests.get(
            f"{API_BASE}/sell/metadata/v1/marketplace/EBAY_DE/get_item_condition_policies",
            headers={"Authorization": f"Bearer {token}"},
            params={"filter": f"categoryIds:{{{category_id}}}"},
            timeout=15,
        )
        if resp.status_code >= 400:
            print(f"[ebay_publisher] Condition-Policy Lookup fehlgeschlagen: {resp.status_code} {resp.text[:200]}", flush=True)
            return None
        policies = resp.json().get("itemConditionPolicies", [])
        if not policies:
            return None
        ids = {str(c["conditionId"]) for c in policies[0].get("itemConditions", [])}
        print(f"[ebay_publisher] Gültige Condition-IDs für Kategorie {category_id}: {sorted(ids)}", flush=True)
        return ids
    except Exception as exc:
        print(f"[ebay_publisher] Condition-Policy Fehler: {exc}", flush=True)
        return None


def _resolve_condition(token: str, category_id: str, grade: str) -> str:
    """Wählt das passende Inventory-API-Zustands-Enum für die Kategorie."""
    prefs = _GRADE_PREFERENCE.get(grade) or _GRADE_PREFERENCE["Gut"]
    valid = _valid_condition_ids(token, category_id)
    if valid:
        for cid in prefs:
            if cid in valid:
                return _ID_TO_ENUM[cid]
        # Keine Wunsch-ID gültig -> erste bekannte gültige ID nehmen
        for cid in sorted(valid):
            if cid in _ID_TO_ENUM:
                print(f"[ebay_publisher] Zustand '{grade}' nicht direkt gültig, nutze conditionId {cid}.", flush=True)
                return _ID_TO_ENUM[cid]
    # Metadata-Lookup fehlgeschlagen -> beste Schätzung
    return _ID_TO_ENUM[prefs[0]]


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def _required_aspects(token: str, category_id: str) -> list:
    """Pflicht-Artikelmerkmale der Kategorie (Name + erlaubte Werte)."""
    try:
        resp = requests.get(
            f"{API_BASE}/commerce/taxonomy/v1/category_tree/{CATEGORY_TREE_ID}/get_item_aspects_for_category",
            headers={"Authorization": f"Bearer {token}"},
            params={"category_id": category_id},
            timeout=15,
        )
        if resp.status_code >= 400:
            print(f"[ebay_publisher] Aspect-Lookup fehlgeschlagen: {resp.status_code} {resp.text[:200]}", flush=True)
            return []
        out = []
        for a in resp.json().get("aspects", []):
            constraint = a.get("aspectConstraint", {})
            if not constraint.get("aspectRequired"):
                continue
            out.append({
                "name":   a.get("localizedAspectName"),
                "values": [v.get("localizedValue") for v in a.get("aspectValues", []) if v.get("localizedValue")],
            })
        print(f"[ebay_publisher] Pflicht-Aspects für {category_id}: {[o['name'] for o in out]}", flush=True)
        return out
    except Exception as exc:
        print(f"[ebay_publisher] Aspect-Lookup Fehler: {exc}", flush=True)
        return []


def _generate_aspects(required: list, listing_data: dict) -> dict:
    """Befüllt die Pflicht-Aspects per KI. Rückgabe im eBay-Format {name: [wert]}."""
    if not required:
        return {}

    spec_lines = []
    for r in required:
        line = f"- {r['name']}"
        if r["values"]:
            line += f" (erlaubte Werte: {', '.join(r['values'][:30])})"
        spec_lines.append(line)

    context = {
        "titel":        listing_data.get("titel"),
        "beschreibung": listing_data.get("beschreibung"),
        "zustand":      listing_data.get("zustand"),
        "analyse":      listing_data.get("analyse", {}),
    }
    prompt = (
        "Fülle die folgenden eBay-Pflicht-Artikelmerkmale für diesen Artikel aus.\n"
        "Wenn erlaubte Werte vorgegeben sind, wähle exakt einen davon.\n"
        "Wenn ein Wert unbekannt ist, nutze eine sinnvolle Annahme, sonst 'Nicht zutreffend'.\n\n"
        f"Artikel:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Pflicht-Merkmale:\n{chr(10).join(spec_lines)}\n\n"
        'Antworte NUR mit JSON: {"Merkmalname": "Wert", ...}'
    )
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=1024,
            system="Du bist ein eBay-Listing-Experte. Antworte präzise auf Deutsch.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _extract_json(response.content[0].text)
    except Exception as exc:
        print(f"[ebay_publisher] Aspect-Generierung fehlgeschlagen: {exc}", flush=True)
        raw = {}

    aspects = {}
    for r in required:
        val = raw.get(r["name"])
        aspects[r["name"]] = [str(val)] if val else ["Nicht zutreffend"]
    print(f"[ebay_publisher] Aspects: {aspects}", flush=True)
    return aspects


def _create_inventory_item(token: str, sku: str, listing_data: dict, image_urls: list) -> None:
    print(f"[ebay_publisher] Schritt 3: Inventory Item erstellen (SKU: {sku})...", flush=True)
    category_id = str(listing_data["kategorie"])
    condition = _resolve_condition(
        token,
        category_id,
        listing_data.get("zustand", "Gut"),
    )
    print(f"[ebay_publisher] Zustand: '{listing_data.get('zustand', 'Gut')}' -> {condition}", flush=True)

    aspects = _generate_aspects(_required_aspects(token, category_id), listing_data)

    resp = requests.put(
        f"{API_BASE}/sell/inventory/v1/inventory_item/{sku}",
        headers={**_json_headers(token), "Content-Language": "de-DE"},
        json={
            "condition": condition,
            "product": {
                "title":       listing_data["titel"],
                "description": listing_data["beschreibung"],
                **({"aspects": aspects} if aspects else {}),
                **({"imageUrls": image_urls} if image_urls else {}),
            },
            "availability": {
                "shipToLocationAvailability": {"quantity": 1}
            },
        },
        timeout=15,
    )
    print(f"[ebay_publisher] Inventory Item: {resp.status_code}", flush=True)
    resp.raise_for_status()


# ── Schritt 4 ─────────────────────────────────────────────────────────────────

def _create_offer(token: str, sku: str, listing_data: dict) -> str:
    print("[ebay_publisher] Schritt 4: Offer erstellen...", flush=True)
    resp = requests.post(
        f"{API_BASE}/sell/inventory/v1/offer",
        headers={
            "Authorization":    f"Bearer {token}",
            "Content-Type":     "application/json",
            "Content-Language": "de-DE",
        },
        json={
            "sku":            sku,
            "marketplaceId":  "EBAY_DE",
            "format":         "FIXED_PRICE",
            "pricingSummary": {
                "price": {
                    "value":    str(listing_data["preis"]),
                    "currency": "EUR",
                }
            },
            "categoryId": str(listing_data["kategorie"]),
            "listingPolicies": {
                "fulfillmentPolicyId": str(listing_data["versand_policy_id"]),
                "returnPolicyId":      os.environ.get("EBAY_RETURN_POLICY_ID", ""),
                "paymentPolicyId":     os.environ.get("EBAY_PAYMENT_POLICY_ID", ""),
            },
            "merchantLocationKey": "home",
        },
        timeout=15,
    )
    print(f"[ebay_publisher] Offer: {resp.status_code} {resp.text[:300]}", flush=True)
    resp.raise_for_status()
    return resp.json()["offerId"]


# ── Schritt 5 ─────────────────────────────────────────────────────────────────

def _publish_offer(token: str, offer_id: str) -> str:
    print(f"[ebay_publisher] Schritt 5: Offer {offer_id} publishen...", flush=True)
    resp = requests.post(
        f"{API_BASE}/sell/inventory/v1/offer/{offer_id}/publish",
        headers=_json_headers(token),
        timeout=15,
    )
    print(f"[ebay_publisher] Publish: {resp.status_code} {resp.text[:300]}", flush=True)
    resp.raise_for_status()
    return resp.json()["listingId"]


# ── Hauptfunktion ──────────────────────────────────────────────────────────────

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"


def _category_is_valid(token: str, category_id: str) -> bool:
    if not category_id:
        return False
    try:
        resp = requests.get(
            f"{API_BASE}/commerce/taxonomy/v1/category_tree/{CATEGORY_TREE_ID}/get_item_aspects_for_category",
            headers={"Authorization": f"Bearer {token}"},
            params={"category_id": category_id},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _suggest_category(token: str, query: str):
    if not query:
        return None
    try:
        resp = requests.get(
            f"{API_BASE}/commerce/taxonomy/v1/category_tree/{CATEGORY_TREE_ID}/get_category_suggestions",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query},
            timeout=15,
        )
        if resp.status_code >= 400:
            print(f"[ebay_publisher] Kategorie-Vorschlag fehlgeschlagen: {resp.status_code} {resp.text[:200]}", flush=True)
            return None
        suggestions = resp.json().get("categorySuggestions", [])
        if not suggestions:
            return None
        return suggestions[0].get("category", {}).get("categoryId")
    except Exception as exc:
        print(f"[ebay_publisher] Kategorie-Vorschlag Fehler: {exc}", flush=True)
        return None


def _resolve_category(token: str, listing_data: dict) -> str:
    """Validiert die Kategorie-ID, holt sonst eine gültige Leaf-Kategorie."""
    given = str(listing_data.get("kategorie", "")).strip()
    if _category_is_valid(token, given):
        print(f"[ebay_publisher] Kategorie {given} gültig.", flush=True)
        return given

    query = (listing_data.get("titel")
             or listing_data.get("analyse", {}).get("artikel_name")
             or "")
    suggested = _suggest_category(token, query)
    if suggested:
        print(f"[ebay_publisher] Kategorie '{given}' ungültig -> Vorschlag {suggested} für '{query}'", flush=True)
        return suggested

    print(f"[ebay_publisher] Keine gültige Kategorie gefunden, nutze '{given}'.", flush=True)
    return given


def _do_publish(token: str, listing_data: dict, image_paths: list) -> dict:
    _ensure_location(token)
    listing_data = {**listing_data, "kategorie": _resolve_category(token, listing_data)}
    image_urls = _upload_images(token, image_paths)
    sku        = f"inserat-{int(time.time())}"
    _create_inventory_item(token, sku, listing_data, image_urls)
    offer_id   = _create_offer(token, sku, listing_data)
    listing_id = _publish_offer(token, offer_id)
    print(f"[ebay_publisher] Erfolgreich veroeffentlicht! Listing ID: {listing_id}", flush=True)
    return {
        "success":     True,
        "listing_id":  listing_id,
        "listing_url": f"https://www.ebay.de/itm/{listing_id}",
    }


def _refresh_and_save() -> str:
    print("[ebay_publisher] Token abgelaufen – versuche Refresh...", flush=True)
    new_token = refresh_access_token()
    os.environ["EBAY_ACCESS_TOKEN"] = new_token
    set_key(str(_ENV_PATH), "EBAY_ACCESS_TOKEN", new_token)
    print("[ebay_publisher] Token erneuert und in .env gespeichert.", flush=True)
    return new_token


def publish_to_ebay(listing_data: dict, image_paths: list) -> dict:
    try:
        token = get_valid_token()
        return _do_publish(token, listing_data, image_paths)

    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            try:
                token = _refresh_and_save()
                return _do_publish(token, listing_data, image_paths)
            except Exception as refresh_exc:
                print(f"[ebay_publisher] Refresh fehlgeschlagen: {refresh_exc}", flush=True)
                return {
                    "success": False,
                    "error":   f"Token abgelaufen und Refresh fehlgeschlagen: {refresh_exc}",
                    "details": "",
                }
        details = exc.response.text[:500] if exc.response is not None else ""
        print(f"[ebay_publisher] FEHLER: {exc} | {details}", flush=True)
        return {"success": False, "error": str(exc), "details": details}

    except Exception as exc:
        details = ""
        if hasattr(exc, "response") and exc.response is not None:
            details = exc.response.text[:500]
        print(f"[ebay_publisher] FEHLER: {exc} | {details}", flush=True)
        return {"success": False, "error": str(exc), "details": details}
