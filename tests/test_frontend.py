"""Browser regression tests. All API calls are mocked; nothing is published.
Run: .venv/bin/python -m unittest discover -s tests -v
Screenshots: /tmp/inserat-studio-qa/
"""
import base64
import copy
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
LISTING = {'titel': 'Sony WH-1000XM4 Kopfhörer – sehr guter Zustand', 'beschreibung': '<h2>Musik ohne Ablenkung.</h2><p>Ich verkaufe meine Sony WH-1000XM4 Kopfhörer. Voll funktionsfähig, mit Tasche und Ladekabel.</p><ul><li>Aktive Geräuschunterdrückung</li><li>Bis zu 30 Stunden Akkulaufzeit</li></ul>', 'kategorie': '112529', 'tags': ['Sony', 'Bluetooth', 'Kopfhörer', 'Noise Cancelling']}
RESULT = {
    'analyse': {'artikel_name': 'Sony WH-1000XM4', 'zustand': 'Sehr gut', 'marke': 'Sony', 'kategorie_vorschlag': 'Audio & Hi-Fi', 'zustand_beschreibung': 'Leichte Gebrauchsspuren am Bügel, Polster in sehr gutem Zustand.', 'features': ['Bluetooth', 'Noise Cancelling', 'Mit Transportetui']},
    'ebay': LISTING,
    'kleinanzeigen': {**LISTING, 'beschreibung': 'Ich verkaufe meine Sony WH-1000XM4 Kopfhörer. Sehr guter Zustand, mit Tasche und Ladekabel.', 'kategorie': 'Elektronik > Audio & Hifi'},
    'preisrecherche': {'vorschlag': 145, 'min_preis': 119, 'max_preis': 189, 'durchschnitt': 152, 'median': 149, 'anzahl_treffer': 18, 'beispiele': [{'titel': 'Sony WH-1000XM4 mit Tasche', 'preis': 149}]},
    'image_paths': ['/mock/photo.jpg'],
}

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(ROOT / 'frontend'))
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.shots = Path('/tmp/inserat-studio-qa')
        cls.shots.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1050})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.api_calls = []
        self.result = copy.deepcopy(RESULT)
        self.analyze_fail = False
        self.defer_analysis = False
        self.pending_analysis = []
        self.publish_mode = 'success'
        self.connected = True
        self.auth_down = False
        self.context.route('**/api/**', self.api)
        self.context.route('**/auth/**', self.auth)
        self.page.goto(self.base)
        expect(self.page.locator('#ebay-connection-badge')).to_have_text('Zugang hinterlegt')

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], 'No uncaught browser errors')

    def reply(self, route, body, status=200):
        route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

    def auth(self, route):
        if self.auth_down:
            self.reply(route, {'detail': 'offline'}, 503)
        elif route.request.url.endswith('/callback'):
            self.reply(route, {'success': True})
        elif route.request.url.endswith('/auth/ebay'):
            self.reply(route, {'auth_url': self.base + '/mock-ebay-login'})
        else:
            self.reply(route, {'connected': self.connected})

    def api(self, route):
        self.api_calls.append((route.request.url, (route.request.post_data_buffer or b'').decode('utf-8', errors='replace')))
        if '/analyze' in route.request.url:
            if self.defer_analysis:
                self.pending_analysis.append(route)
                return
            self.reply(route, {'detail': 'Test: Analyse nicht verfügbar'} if self.analyze_fail else self.result, 500 if self.analyze_fail else 200)
        elif '/generate' in route.request.url:
            self.reply(route, {'listing': RESULT['kleinanzeigen']})
        elif '/publish/' in route.request.url:
            if self.publish_mode == 'disconnect':
                route.abort('failed')
            elif self.publish_mode == 'error':
                self.reply(route, {'success': False, 'error': 'Bitte Versandoption überprüfen.'})
            else:
                self.reply(route, {'success': True, 'listing_url': 'https://www.ebay.de/itm/mock-id'})

    def upload(self):
        self.page.locator('#file-input').set_input_files({'name': 'artikel.png', 'mimeType': 'image/png', 'buffer': PNG})

    def review(self):
        self.upload()
        self.page.locator('#analyze-btn').click()
        expect(self.page.locator('#review-section')).to_be_visible()
        expect(self.page.locator('#ebay-confirm-btn')).to_be_enabled()

    def publish_calls(self):
        return [call for call in self.api_calls if '/publish/' in call[0]]

    def test_initial_responsive_layout_and_accounts(self):
        expect(self.page.locator('#analyze-btn')).to_be_disabled()
        self.page.screenshot(path=str(self.shots / 'desktop-upload.png'), full_page=True)
        for width in [320, 375, 390, 768, 1024, 1440]:
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'No horizontal overflow at {width}')
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.screenshot(path=str(self.shots / 'mobile-upload.png'), full_page=True)
        self.page.locator('#accounts-toggle').click()
        expect(self.page.locator('#page-connections')).to_be_visible()
        expect(self.page.locator('#ebay-connection-badge')).to_have_text('Zugang hinterlegt')
        self.page.locator('#accounts-toggle').click()
        expect(self.page.locator('#page-connections')).to_be_hidden()
        expect(self.page.locator('#upload-section')).to_be_visible()

    def test_file_validation_remove_and_keyboard(self):
        with self.page.expect_file_chooser() as chooser:
            self.page.locator('#dropzone').press('Enter')
        chooser.value.set_files([])
        self.page.locator('#file-input').set_input_files([
            {'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'not an image'},
            {'name': 'photo.png', 'mimeType': 'image/png', 'buffer': PNG},
        ])
        expect(self.page.locator('#upload-error')).to_contain_text('JPG, PNG oder WEBP')
        expect(self.page.locator('#photo-count')).to_have_text('1 / 12')
        self.page.locator('#platform-ebay').uncheck()
        self.page.locator('#platform-kleinanzeigen').uncheck()
        expect(self.page.locator('#analyze-btn')).to_be_disabled()
        expect(self.page.locator('#platform-hint')).to_be_visible()
        self.page.locator('#platform-ebay').check()
        expect(self.page.locator('#analyze-btn')).to_be_enabled()
        self.page.get_by_role('button', name='photo.png entfernen').click()
        expect(self.page.locator('#dropzone')).to_be_focused()
        expect(self.page.locator('#analyze-btn')).to_be_disabled()

    def test_upload_limits(self):
        files = [{'name': f'{i}.png', 'mimeType': 'image/png', 'buffer': PNG} for i in range(13)]
        self.page.locator('#file-input').set_input_files(files)
        expect(self.page.locator('.preview-item')).to_have_count(12)
        expect(self.page.locator('#upload-error')).to_contain_text('maximal zwölf')
        self.page.locator('#clear-btn').click()
        self.page.locator('#file-input').set_input_files({'name': 'large.png', 'mimeType': 'image/png', 'buffer': b'x' * (10 * 1024 * 1024 + 1)})
        expect(self.page.locator('#upload-error')).to_contain_text('10 MB')
        expect(self.page.locator('.preview-item')).to_have_count(0)

    def test_analysis_error_preserves_photos(self):
        self.analyze_fail = True
        self.upload()
        self.page.locator('#analyze-btn').click()
        expect(self.page.locator('#app-message')).to_contain_text('Deine Fotos bleiben ausgewählt')
        expect(self.page.locator('#upload-section')).to_be_visible()
        expect(self.page.locator('.preview-item')).to_have_count(1)
        expect(self.page.locator('#analyze-btn')).to_be_enabled()

    def test_loading_keeps_work_when_opening_accounts(self):
        self.defer_analysis = True
        self.upload()
        self.page.locator('#analyze-btn').click()
        expect(self.page.locator('#loading-section')).to_be_visible()
        self.page.locator('#accounts-toggle').click()
        self.reply(self.pending_analysis.pop(), self.result)
        expect(self.page.locator('#page-connections')).to_be_visible()
        self.page.locator('#accounts-toggle').click()
        expect(self.page.locator('#review-section')).to_be_visible()
        expect(self.page.locator('#ebay-titel')).to_have_value(LISTING['titel'])

    def test_edit_tabs_reload_and_price(self):
        self.review()
        self.page.locator('#ebay-titel').fill('Mein bearbeiteter Titel')
        self.page.locator('#ebay-preis').fill('163.50')
        self.page.locator('#tab-button-ebay').focus()
        self.page.keyboard.press('ArrowRight')
        expect(self.page.locator('#tab-button-kleinanzeigen')).to_have_attribute('aria-selected', 'true')
        self.page.locator('#ka-preis').fill('')
        self.page.reload()
        expect(self.page.locator('#ka-preis')).to_have_value('')
        self.page.locator('#tab-button-ebay').click()
        expect(self.page.locator('#ebay-titel')).to_have_value('Mein bearbeiteter Titel')
        expect(self.page.locator('#ebay-preis')).to_have_value('163.50')
        self.page.locator('#review-context > summary').click()
        self.page.locator('#apply-price').click()
        expect(self.page.locator('#ebay-preis')).to_have_value('145.00')
        self.page.locator('#ebay-preis').blur()
        self.page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        self.page.screenshot(path=str(self.shots / 'desktop-review.png'), full_page=True)
        for width in [320, 390, 768, 1024]:
            self.page.set_viewport_size({'width': width, 'height': 844})
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.screenshot(path=str(self.shots / 'mobile-review.png'), full_page=True)

    def test_lazy_platform_generation(self):
        self.result['kleinanzeigen'] = None
        self.review()
        self.page.locator('#tab-button-kleinanzeigen').click()
        expect(self.page.locator('#ka-generate-prompt')).to_be_visible()
        self.page.locator('#ka-generate-btn').click()
        expect(self.page.locator('#ka-fields')).to_be_visible()
        expect(self.page.locator('#ka-titel')).to_have_value(LISTING['titel'])

    def test_publish_validation_confirmation_and_duplicate_prevention(self):
        self.review()
        self.page.locator('#ebay-titel').fill('')
        self.page.locator('#ebay-confirm-btn').click()
        expect(self.page.locator('#ebay-titel-error')).to_be_visible()
        expect(self.page.locator('#ebay-titel')).to_be_focused()
        self.assertEqual(self.publish_calls(), [])
        self.page.locator('#ebay-titel').fill('Prüfartikel')
        self.page.locator('#ebay-confirm-btn').click()
        expect(self.page.locator('#confirm-dialog')).to_be_visible()
        expect(self.page.locator('#dialog-details')).to_contain_text('145,00')
        self.page.screenshot(path=str(self.shots / 'publish-confirmation.png'))
        self.page.keyboard.press('Escape')
        self.assertEqual(self.publish_calls(), [])
        self.page.locator('#ebay-confirm-btn').click()
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#ebay-publish-result')).to_contain_text('Veröffentlicht.')
        expect(self.page.locator('#ebay-confirm-btn')).to_be_disabled()
        expect(self.page.locator('#ebay-titel')).to_be_disabled()
        self.page.reload()
        expect(self.page.locator('#ebay-confirm-btn')).to_be_disabled()
        self.assertEqual(len(self.publish_calls()), 1)
        payload = json.loads(self.publish_calls()[0][1])
        self.assertEqual(payload['listing']['titel'], 'Prüfartikel')
        self.assertEqual(payload['listing']['versand_policy_id'], '258528333010')
        self.assertEqual(payload['image_paths'], ['/mock/photo.jpg'])

    def test_unknown_publish_status_requires_check(self):
        self.review()
        self.publish_mode = 'disconnect'
        self.page.locator('#ebay-confirm-btn').click()
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#ebay-publish-result')).to_contain_text('Veröffentlichungsstatus ist unklar')
        expect(self.page.locator('#ebay-confirm-btn')).to_be_disabled()
        self.page.reload()
        expect(self.page.locator('#ebay-confirm-btn')).to_be_disabled()
        self.page.get_by_role('button', name='Geprüft: Inserat wurde nicht erstellt').click()
        expect(self.page.locator('#ebay-confirm-btn')).to_be_enabled()

    def test_platform_failure_allows_explicit_retry(self):
        self.review()
        self.publish_mode = 'error'
        self.page.locator('#ebay-confirm-btn').click()
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#ebay-publish-result')).to_contain_text('Versandoption überprüfen')
        expect(self.page.locator('#ebay-titel')).to_be_enabled()
        self.assertEqual(len(self.publish_calls()), 1)
        self.publish_mode = 'success'
        self.page.locator('#ebay-confirm-btn').click()
        self.assertEqual(len(self.publish_calls()), 1)
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#ebay-publish-result')).to_contain_text('Veröffentlicht.')
        self.assertEqual(len(self.publish_calls()), 2)

    def test_giveaway_and_new_article_reset(self):
        self.review()
        self.page.locator('#tab-button-kleinanzeigen').click()
        self.page.locator('#ka-preistyp').select_option('GIVE_AWAY')
        expect(self.page.locator('#ka-preis')).to_be_disabled()
        expect(self.page.locator('#apply-price')).to_be_disabled()
        self.page.locator('#ka-confirm-btn').click()
        expect(self.page.locator('#dialog-details')).to_contain_text('Zu verschenken')
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#ka-publish-result')).to_contain_text('Veröffentlicht.')
        self.assertEqual(json.loads(self.publish_calls()[0][1])['listing']['preis'], 0)
        self.page.locator('#new-btn').click()
        self.page.locator('#dialog-cancel').click()
        expect(self.page.locator('#review-section')).to_be_visible()
        self.page.locator('#new-btn').click()
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#upload-section')).to_be_visible()
        self.result['preisrecherche'] = None
        self.review()
        expect(self.page.locator('#ebay-preis')).to_have_value('')
        self.page.locator('#tab-button-kleinanzeigen').click()
        expect(self.page.locator('#ka-preis')).to_be_enabled()
        expect(self.page.locator('#ka-preistyp')).to_have_value('NEGOTIABLE')

    def test_preview_sanitization(self):
        self.result['ebay']['beschreibung'] = '<h2>Safe preview</h2><img src="bad" onerror="parent.hacked=true"><script>parent.hacked=true</script><a href="javascript:alert(1)">Text</a>'
        self.review()
        expect(self.page.locator('#ebay-beschreibung')).to_have_value('Safe preview\n\nText')
        self.page.locator('#ebay-preview-toggle').click()
        expect(self.page.frame_locator('#ebay-beschreibung-preview').locator('h2')).to_have_text('Safe preview')
        expect(self.page.frame_locator('#ebay-beschreibung-preview').locator('script,img,a')).to_have_count(0)
        self.assertFalse(self.page.evaluate('Boolean(window.hacked)'))
        self.page.locator('#ebay-beschreibung').fill('Mein Text & mehr.\n\n• Tasche\n• Ladekabel')
        expect(self.page.frame_locator('#ebay-beschreibung-preview').locator('li')).to_have_count(2)
        self.page.locator('#ebay-confirm-btn').click()
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#ebay-publish-result')).to_contain_text('Veröffentlicht.')
        description = json.loads(self.publish_calls()[0][1])['listing']['beschreibung']
        self.assertEqual(description, '<p>Mein Text &amp; mehr.</p><ul><li>Tasche</li><li>Ladekabel</li></ul>')

    def test_disconnected_account_keeps_draft(self):
        self.review()
        self.connected = False
        self.page.locator('#accounts-toggle').click()
        self.page.locator('#refresh-connections').click()
        expect(self.page.locator('#ebay-connect-section')).to_be_visible()
        self.page.locator('#accounts-toggle').click()
        self.page.locator('#ebay-confirm-btn').click()
        expect(self.page.locator('#dialog-title')).to_contain_text('eBay verbinden')
        self.page.locator('#dialog-confirm').click()
        expect(self.page.locator('#page-connections')).to_be_visible()
        self.assertEqual(self.publish_calls(), [])
        self.auth_down = True
        self.page.locator('#refresh-connections').click()
        expect(self.page.locator('#ebay-connection-badge')).to_have_text('Status nicht erreichbar')

    def test_oauth_popup_and_code_exchange(self):
        self.connected = False
        self.page.locator('#accounts-toggle').click()
        self.page.locator('#refresh-connections').click()
        expect(self.page.locator('#connect-ebay-btn')).to_be_visible()
        with self.context.expect_page() as popup:
            self.page.locator('#connect-ebay-btn').click()
        expect(self.page.locator('#connect-step-2')).to_be_visible()
        expect(self.page.locator('#oauth-reopen-link')).to_have_attribute('href', self.base + '/mock-ebay-login')
        self.page.locator('#oauth-code-input').fill('https://example.test/callback?code=test%2Bcode')
        self.connected = True
        with self.page.expect_request('**/auth/ebay/callback') as callback:
            self.page.locator('#save-token-btn').click()
        self.assertEqual(json.loads(callback.value.post_data)['code'], 'test+code')
        expect(self.page.locator('#connect-step-3')).to_be_visible()
        expect(self.page.locator('#oauth-code-input')).to_have_value('')
        popup.value.close()

if __name__ == '__main__':
    unittest.main()
