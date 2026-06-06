import base64
import os
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

_SCOPES = " ".join([
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
])


def _is_sandbox() -> bool:
    return os.environ.get("EBAY_SANDBOX", "false").lower() == "true"


def _auth_base() -> str:
    return "https://auth.sandbox.ebay.com" if _is_sandbox() else "https://auth.ebay.com"


def _api_base() -> str:
    return "https://api.sandbox.ebay.com" if _is_sandbox() else "https://api.ebay.com"


def _basic_header() -> str:
    client_id     = os.environ.get("EBAY_CLIENT_ID", "")
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "")
    return "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


def get_auth_url() -> str:
    params = {
        "client_id":     os.environ.get("EBAY_CLIENT_ID", ""),
        "redirect_uri":  os.environ.get("EBAY_RUNAME", ""),
        "response_type": "code",
        "scope":         _SCOPES,
    }
    return f"{_auth_base()}/oauth2/authorize?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    resp = requests.post(
        f"{_api_base()}/identity/v1/oauth2/token",
        headers={
            "Authorization": _basic_header(),
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": os.environ.get("EBAY_RUNAME", ""),
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token":  data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_in":    data.get("expires_in", 7200),
    }


def refresh_access_token() -> str:
    refresh_token = os.environ.get("EBAY_REFRESH_TOKEN", "")
    if not refresh_token:
        raise ValueError("EBAY_REFRESH_TOKEN nicht gesetzt")

    resp = requests.post(
        f"{_api_base()}/identity/v1/oauth2/token",
        headers={
            "Authorization": _basic_header(),
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "scope":         _SCOPES,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_valid_token() -> str:
    token = os.environ.get("EBAY_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError(
            "Kein eBay Access Token vorhanden. "
            "Bitte zuerst eBay OAuth unter /auth/ebay durchführen."
        )
    return token
