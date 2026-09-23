"""Kleinanzeigen-Publishing via Playwright.

Hinweis: Kleinanzeigen ändert sein DOM regelmäßig. Die Selektoren unten sind
Best-Effort und in try/except mit Logging gekapselt. Der Browser läuft bewusst
headed (headless=False), damit man den Ablauf sieht und im Zweifel manuell
nachhelfen kann.

Benötigte Umgebungsvariable (.env):
    EBAY_LOCATION_ZIP=deine_postleitzahl
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

load_dotenv()

# Persistentes Browser-Profil statt storage_state-Datei. Ein echtes Profil
# (Cookies, LocalStorage, Fingerprint) wirkt für Kleinanzeigen wie ein normaler
# Nutzer -> Captcha muss nur EINMAL manuell gelöst werden, danach bleibt der
# Login im Profil erhalten.
PROFILE_DIR = Path(__file__).parent.parent / "kleinanzeigen_profile"

BASE_URL    = "https://www.kleinanzeigen.de"
LOGIN_URL   = f"{BASE_URL}/m-einloggen.html"
POSTAD_URL  = f"{BASE_URL}/p-anzeige-aufgeben.html"

# Anti-Bot-Maßnahmen: echtes Chrome statt Playwright-Chromium + maskierte
# Automatisierungs-Flags. Sonst erkennt Kleinanzeigen den Browser und das
# Captcha-Häkchen lässt sich nicht setzen.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]
STEALTH_JS = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    "window.chrome = window.chrome || {runtime: {}};"
    "Object.defineProperty(navigator, 'languages', {get: () => ['de-DE', 'de']});"
    "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
)

# Kleinanzeigen-interne Werte für die Preisart
PREISTYP_LABELS = {
    "FIXED":      "Festpreis",
    "NEGOTIABLE": "VB",
    "GIVE_AWAY":  "Zu verschenken",
    "ON_REQUEST": "Auf Anfrage",
}


# ── Cookie-Banner ────────────────────────────────────────────────────────────────

def _dismiss_cookie_banner(page) -> None:
    """GDPR-Consent wegklicken (verschiedene Varianten)."""
    selectors = [
        "#gdpr-banner-accept",
        "button[data-testid='gdpr-banner-accept']",
        "button:has-text('Alle akzeptieren')",
        "button:has-text('Akzeptieren')",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                print("[ka_publisher] Cookie-Banner akzeptiert.", flush=True)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


# ── Browser-Start (Anti-Bot) ──────────────────────────────────────────────────────

def _launch_context(p):
    """Startet einen persistenten Browser-Kontext mit Anti-Bot-Maßnahmen.

    Bevorzugt echtes Google Chrome (channel='chrome'), dann Edge, und fällt
    zuletzt auf das gebündelte Chromium zurück.
    """
    PROFILE_DIR.mkdir(exist_ok=True)
    last_err = None
    for channel in ("chrome", "msedge", None):
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                channel=channel,
                args=LAUNCH_ARGS,
                ignore_default_args=["--enable-automation"],
                user_agent=USER_AGENT,
                locale="de-DE",
                timezone_id="Europe/Berlin",
                viewport={"width": 1366, "height": 900},
            )
            context.add_init_script(STEALTH_JS)
            print(f"[ka_publisher] Browser gestartet (channel={channel or 'chromium'}).", flush=True)
            return context
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"Kein Browser startbar: {last_err}")


def _page(context):
    return context.pages[0] if context.pages else context.new_page()


# ── Login ──────────────────────────────────────────────────────────────────────────

def _is_login_page(page) -> bool:
    return "m-einloggen" in page.url


def _wait_for_manual_login(page, timeout: int = 180) -> bool:
    """Öffnet die Login-Seite und wartet, bis der Nutzer manuell eingeloggt ist.

    Bei sichtbarem, echtem Chrome kann das Captcha-Häkchen von Hand gesetzt
    werden. Erkennt den Login daran, dass die URL kein /m-einloggen mehr enthält.
    """
    print(f"[ka_publisher] Bitte im Fenster einloggen + ggf. Captcha lösen (max. {timeout}s)...", flush=True)
    page.goto(LOGIN_URL)
    _dismiss_cookie_banner(page)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _is_login_page(page):
            page.wait_for_timeout(2000)  # Auth-Cookies sammeln
            print("[ka_publisher] Login erkannt.", flush=True)
            return True
        page.wait_for_timeout(1000)

    print("[ka_publisher] Login-Timeout.", flush=True)
    return False


def ensure_logged_in() -> bool:
    """Öffnet das Profil und stellt sicher, dass eingeloggt ist (sonst manuell)."""
    with sync_playwright() as p:
        context = _launch_context(p)
        page = _page(context)
        try:
            page.goto(POSTAD_URL)
            _dismiss_cookie_banner(page)
            if not _is_login_page(page):
                print("[ka_publisher] Bereits eingeloggt (Profil gültig).", flush=True)
                return True
            return _wait_for_manual_login(page)
        finally:
            context.close()


# ── Einzelschritte ───────────────────────────────────────────────────────────────

def _select_category(page, kategorie_pfad: str) -> None:
    """Wählt die Kategorie anhand des Pfads, z.B. 'Elektronik > Konsolen'."""
    print(f"[ka_publisher] Schritt 2: Kategorie wählen: '{kategorie_pfad}'", flush=True)
    teile = [t.strip() for t in (kategorie_pfad or "").split(">") if t.strip()]

    for teil in teile:
        try:
            link = page.get_by_role("link", name=teil, exact=False).first
            if link.is_visible(timeout=3000):
                link.click()
                page.wait_for_timeout(800)
                print(f"[ka_publisher]   -> '{teil}' geklickt.", flush=True)
                continue
        except Exception:
            pass
        # Fallback: nach sichtbarem Text suchen
        try:
            el = page.get_by_text(teil, exact=False).first
            if el.is_visible(timeout=2000):
                el.click()
                page.wait_for_timeout(800)
                print(f"[ka_publisher]   -> '{teil}' (Text-Fallback) geklickt.", flush=True)
                continue
        except Exception:
            pass
        print(f"[ka_publisher]   ! Kategorieteil '{teil}' nicht gefunden.", flush=True)

    # Falls nichts gewählt wurde: 'Sonstiges' versuchen
    if not teile:
        try:
            page.get_by_text("Sonstiges", exact=False).first.click(timeout=2000)
            print("[ka_publisher]   -> Fallback 'Sonstiges' gewählt.", flush=True)
        except Exception:
            print("[ka_publisher]   ! Keine Kategorie wählbar, weiter ohne.", flush=True)


def _fill_first(page, selectors: list, value: str, label: str) -> bool:
    """Versucht mehrere Selektoren, füllt den ersten sichtbaren."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.fill(str(value))
                print(f"[ka_publisher]   {label} gesetzt ({sel}).", flush=True)
                return True
        except Exception:
            continue
    print(f"[ka_publisher]   ! {label} konnte nicht gesetzt werden.", flush=True)
    return False


def _fill_form(page, listing_data: dict) -> None:
    print("[ka_publisher] Schritt 3: Formular ausfüllen...", flush=True)

    titel = str(listing_data.get("titel", ""))[:60]
    _fill_first(page, ["#postad-title", "#pstad-title", "input[name='title']"], titel, "Titel")
    _fill_first(page, ["#pstad-descrptn", "#postad-description", "textarea[name='description']"],
                listing_data.get("beschreibung", ""), "Beschreibung")

    preistyp = listing_data.get("preistyp", "NEGOTIABLE")
    # Bei 'Zu verschenken' / 'Auf Anfrage' wird kein Preis benötigt
    if preistyp not in ("GIVE_AWAY", "ON_REQUEST"):
        _fill_first(page, ["#pstad-price", "#postad-price", "input[name='price']"],
                    listing_data.get("preis", ""), "Preis")

    _select_preistyp(page, preistyp)

    plz = os.environ.get("EBAY_LOCATION_ZIP", "")
    if plz:
        _fill_first(page, ["#pstad-zip", "#postad-zipCode", "input[name='postalCode']", "input[name='zipCode']"],
                    plz, "PLZ")
    else:
        print("[ka_publisher]   ! EBAY_LOCATION_ZIP nicht gesetzt.", flush=True)


def _select_preistyp(page, preistyp: str) -> None:
    label = PREISTYP_LABELS.get(preistyp, "VB")
    print(f"[ka_publisher]   Preisart: {preistyp} ({label})", flush=True)

    # Variante A: <select>
    for sel in ["#priceType", "select[name='priceType']", "#micro-frontend-price-type"]:
        try:
            dropdown = page.locator(sel).first
            if dropdown.is_visible(timeout=1500):
                try:
                    dropdown.select_option(value=preistyp)
                except Exception:
                    dropdown.select_option(label=label)
                print(f"[ka_publisher]   Preisart via Dropdown gesetzt ({sel}).", flush=True)
                return
        except Exception:
            continue

    # Variante B: Radio-Button / Label-Text
    try:
        page.get_by_text(label, exact=False).first.click(timeout=1500)
        print("[ka_publisher]   Preisart via Label-Klick gesetzt.", flush=True)
        return
    except Exception:
        print("[ka_publisher]   ! Preisart konnte nicht gesetzt werden.", flush=True)


def _upload_images(page, image_paths: list) -> None:
    print(f"[ka_publisher] Schritt 4: {len(image_paths)} Bild(er) hochladen...", flush=True)
    if not image_paths:
        return
    try:
        file_input = page.locator("input[type='file']").first
        file_input.set_input_files([str(Path(p)) for p in image_paths])
        # Warten bis Uploads verarbeitet sind
        page.wait_for_timeout(4000)
        print("[ka_publisher]   Bilder übergeben.", flush=True)
    except Exception as exc:
        print(f"[ka_publisher]   ! Bild-Upload fehlgeschlagen: {exc}", flush=True)


def _submit(page) -> str:
    print("[ka_publisher] Schritt 5: Anzeige aufgeben...", flush=True)
    for sel in ["#pstad-submit", "button:has-text('Anzeige aufgeben')",
                "button[type='submit']:has-text('aufgeben')"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                break
        except Exception:
            continue

    # Auf Bestätigung warten
    try:
        page.wait_for_url("**/s-anzeige/**", timeout=20000)
    except PlaywrightTimeout:
        page.wait_for_timeout(3000)

    url = page.url
    print(f"[ka_publisher]   Aktuelle URL: {url}", flush=True)
    return url


# ── Hauptfunktion ────────────────────────────────────────────────────────────────

def publish_to_kleinanzeigen(listing_data: dict, image_paths: list) -> dict:
    # Alles in EINEM persistenten Kontext: das Profil-Verzeichnis ist gesperrt,
    # solange der Browser offen ist – ein zweiter paralleler Launch würde fehlschlagen.
    with sync_playwright() as p:
        context = _launch_context(p)
        page = _page(context)

        try:
            print("[ka_publisher] Schritt 1: Anzeige-aufgeben-Seite öffnen...", flush=True)
            page.goto(POSTAD_URL)
            _dismiss_cookie_banner(page)

            # Falls Login nötig: inline im selben Fenster einloggen lassen
            if _is_login_page(page):
                print("[ka_publisher] Login nötig...", flush=True)
                if not _wait_for_manual_login(page):
                    return {"success": False, "error": "Nicht eingeloggt – Login abgebrochen oder Timeout."}
                page.goto(POSTAD_URL)
                _dismiss_cookie_banner(page)
                if _is_login_page(page):
                    return {"success": False, "error": "Login fehlgeschlagen."}

            _select_category(page, listing_data.get("kleinanzeigen_kategorie", ""))
            page.wait_for_timeout(1000)
            _fill_form(page, listing_data)
            _upload_images(page, image_paths)
            listing_url = _submit(page)

            success = "/s-anzeige/" in listing_url
            if success:
                print("[ka_publisher] Anzeige erfolgreich aufgegeben.", flush=True)
                return {"success": True, "listing_url": listing_url}

            print("[ka_publisher] Keine Bestätigungs-URL erkannt.", flush=True)
            return {
                "success": False,
                "error":   "Anzeige konnte nicht bestätigt werden (keine /s-anzeige/-URL). "
                           "Bitte im geöffneten Browser prüfen.",
            }

        except Exception as exc:
            print(f"[ka_publisher] FEHLER: {exc}", flush=True)
            return {"success": False, "error": str(exc)}
        finally:
            # Profil persistiert automatisch auf der Platte; Kontext schließen.
            try:
                context.close()
            except Exception:
                pass
