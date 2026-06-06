import os
import time

import requests
from dotenv import load_dotenv

from modules.ebay_auth import get_valid_token

load_dotenv()

API_BASE   = "https://api.ebay.com"
MEDIA_BASE = "https://apim.ebay.com"

CONDITION_MAP = {
    "Neu":        "NEW",
    "Wie neu":    "LIKE_NEW",
    "Sehr gut":   "USED_EXCELLENT",
    "Gut":        "USED_GOOD",
    "Akzeptabel": "USED_ACCEPTABLE",
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
            "location":               {"address": {"country": "DE"}},
            "locationTypes":          ["WAREHOUSE"],
            "name":                   "Zuhause",
            "merchantLocationStatus": "ENABLED",
        },
        timeout=15,
    )
    print(f"[ebay_publisher] Location erstellt: {resp.status_code}", flush=True)
    resp.raise_for_status()


# ── Schritt 2 ─────────────────────────────────────────────────────────────────

def _upload_images(token: str, image_paths: list) -> list:
    print(f"[ebay_publisher] Schritt 2: {len(image_paths)} Bild(er) hochladen...", flush=True)
    image_urls = []

    for path in image_paths:
        with open(path, "rb") as f:
            resp = requests.post(
                f"{MEDIA_BASE}/commerce/media/v1_beta/image",
                headers={"Authorization": f"Bearer {token}"},
                files={"image": f},
                timeout=30,
            )
        print(f"[ebay_publisher] Upload Status: {resp.status_code}", flush=True)
        resp.raise_for_status()

        location  = resp.headers.get("Location", "")
        image_id  = location.rstrip("/").split("/")[-1]
        print(f"[ebay_publisher] Image ID: {image_id}", flush=True)

        # Poll bis Bild verarbeitet ist
        for attempt in range(10):
            time.sleep(1)
            poll = requests.get(
                f"{MEDIA_BASE}/commerce/media/v1_beta/image/{image_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            poll.raise_for_status()
            url = poll.json().get("imageUrl")
            if url:
                print(f"[ebay_publisher] Image URL: {url}", flush=True)
                image_urls.append(url)
                break
            print(f"[ebay_publisher] Bild noch nicht bereit, Versuch {attempt + 1}/10...", flush=True)
        else:
            raise RuntimeError(f"Bild konnte nicht verarbeitet werden: {path}")

    return image_urls


# ── Schritt 3 ─────────────────────────────────────────────────────────────────

def _create_inventory_item(token: str, sku: str, listing_data: dict, image_urls: list) -> None:
    print(f"[ebay_publisher] Schritt 3: Inventory Item erstellen (SKU: {sku})...", flush=True)
    condition = CONDITION_MAP.get(listing_data.get("zustand", "Gut"), "USED_GOOD")

    resp = requests.put(
        f"{API_BASE}/sell/inventory/v1/inventory_item/{sku}",
        headers={**_json_headers(token), "Content-Language": "de-DE"},
        json={
            "condition": condition,
            "product": {
                "title":       listing_data["titel"],
                "description": listing_data["beschreibung"],
                "imageUrls":   image_urls,
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
        headers=_json_headers(token),
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

def publish_to_ebay(listing_data: dict, image_paths: list) -> dict:
    try:
        token = get_valid_token()

        _ensure_location(token)
        image_urls = _upload_images(token, image_paths)

        sku = f"inserat-{int(time.time())}"
        _create_inventory_item(token, sku, listing_data, image_urls)
        offer_id   = _create_offer(token, sku, listing_data)
        listing_id = _publish_offer(token, offer_id)

        print(f"[ebay_publisher] Erfolgreich veroeffentlicht! Listing ID: {listing_id}", flush=True)
        return {
            "success":     True,
            "listing_id":  listing_id,
            "listing_url": f"https://www.ebay.de/itm/{listing_id}",
        }

    except Exception as exc:
        details = ""
        if hasattr(exc, "response") and exc.response is not None:
            details = exc.response.text[:500]
        print(f"[ebay_publisher] FEHLER: {exc} | {details}", flush=True)
        return {
            "success": False,
            "error":   str(exc),
            "details": details,
        }
