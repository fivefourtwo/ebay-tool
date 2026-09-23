'use strict';

const $ = id => document.getElementById(id);
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const STORAGE_KEY = 'inserat-studio-draft-v1';
const MAX_FILES = 12;
const MAX_SIZE = 10 * 1024 * 1024;
const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const PLATFORM_NAMES = { ebay: 'eBay', kleinanzeigen: 'Kleinanzeigen' };
let selectedFiles = [];
let imageUrls = [];
let analysisResult = null;
let activeTab = 'ebay';
let currentView = 'upload';
let busy = false;
let publishStates = {};
let connections = { ebay: null, kleinanzeigen: null };
let confirmAction = null;
let loadingTimer;
let storageAvailable = true;

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function prefix(platform) { return platform === 'ebay' ? 'ebay' : 'ka'; }
function money(value) {
  return value != null && Number.isFinite(Number(value))
    ? new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(Number(value)) : '–';
}
function safeUrl(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
async function request(url, options = {}) {
  let response;
  try { response = await fetch(url, options); }
  catch { throw new Error('Der lokale Server ist nicht erreichbar. Prüfe, ob die Anwendung läuft, und versuche es erneut.'); }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail || data?.error;
    throw new Error(typeof detail === 'string' ? detail : `Die Anfrage konnte nicht abgeschlossen werden (HTTP ${response.status}). Bitte versuche es erneut.`);
  }
  if (!data) throw new Error('Der Server hat keine lesbare Antwort gesendet. Bitte versuche es erneut.');
  return data;
}
function post(url, data) {
  return request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}
function showError(message) {
  $('app-message-text').textContent = message;
  $('app-message').hidden = false;
  $('app-message').focus();
}
$('dismiss-message').addEventListener('click', () => { $('app-message').hidden = true; });
// Account settings expand in place without leaving the current form.
function openAccounts(open = true) {
  $('page-connections').hidden = !open;
  $('accounts-toggle').setAttribute('aria-expanded', String(open));
  if (open) $('page-connections').scrollIntoView({ block: 'nearest' });
}
$('accounts-toggle').addEventListener('click', () => openAccounts($('page-connections').hidden));

function setView(view, focus = true) {
  currentView = view;
  ['upload', 'loading', 'review'].forEach(name => { $(`${name}-section`).hidden = name !== view; });
  $('new-btn').hidden = view !== 'review';
  $('page-title').textContent = view === 'review' ? 'Inserat bearbeiten' : 'Neues Inserat';
  if (focus) (view === 'loading' ? $('loading-title') : $('page-title')).focus({ preventScroll: true });
}
function setBusy(value) {
  busy = value;
  $('new-btn').disabled = value;
  for (const platform of Object.keys(PLATFORM_NAMES)) {
    const p = prefix(platform);
    $(`${p}-generate-btn`).disabled = value;
    const locked = ['success', 'pending', 'unknown'].includes(publishStates[platform]?.status);
    $(`${p}-fieldset`).disabled = value || locked;
    $(`${p}-confirm-btn`).disabled = value || locked;
  }
  if (analysisResult) renderPriceResearch();
}

// File intake validates individual files and keeps accepted files when some fail.
$('dropzone').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', event => {
  addFiles(Array.from(event.target.files));
  event.target.value = '';
});
$('dropzone').addEventListener('dragover', event => {
  event.preventDefault(); $('dropzone').classList.add('dragover');
});
$('dropzone').addEventListener('dragleave', () => $('dropzone').classList.remove('dragover'));
$('dropzone').addEventListener('drop', event => {
  event.preventDefault(); $('dropzone').classList.remove('dragover');
  addFiles(Array.from(event.dataTransfer.files));
});
// Dropping outside the target must not replace the application with a file.
window.addEventListener('dragover', event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
window.addEventListener('drop', event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
function addFiles(files) {
  if (busy || currentView !== 'upload') return;
  const errors = [];
  for (const file of files) {
    if (!ALLOWED_TYPES.has(file.type)) { errors.push(`${file.name}: Bitte JPG, PNG oder WEBP verwenden.`); continue; }
    if (!file.size || file.size > MAX_SIZE) { errors.push(`${file.name}: Das Foto muss zwischen 1 Byte und 10 MB groß sein.`); continue; }
    if (selectedFiles.some(existing => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified)) {
      errors.push(`${file.name} ist bereits ausgewählt.`); continue;
    }
    if (selectedFiles.length >= MAX_FILES) { errors.push('Du kannst maximal zwölf Fotos pro Artikel hinzufügen.'); break; }
    selectedFiles.push(file);
  }
  $('upload-error').textContent = errors.join(' ');
  $('upload-error').hidden = !errors.length;
  renderPreviews();
}
function releaseImages() { imageUrls.forEach(url => URL.revokeObjectURL(url)); imageUrls = []; }
function renderPreviews() {
  releaseImages();
  $('preview-grid').replaceChildren();
  selectedFiles.forEach((file, index) => {
    const item = document.createElement('div'); item.className = 'preview-item';
    const img = document.createElement('img');
    img.src = URL.createObjectURL(file); imageUrls.push(img.src); img.alt = file.name;
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'preview-item__remove';
    remove.innerHTML = icon('close'); remove.setAttribute('aria-label', `${file.name} entfernen`);
    remove.addEventListener('click', () => {
      selectedFiles.splice(index, 1); renderPreviews();
      const buttons = $('preview-grid').querySelectorAll('button');
      (buttons[Math.min(index, buttons.length - 1)] || $('dropzone')).focus();
    });
    item.append(img, remove);
    if (!index) { const badge = document.createElement('span'); badge.className = 'cover-badge'; badge.textContent = 'Titelbild'; item.append(badge); }
    $('preview-grid').append(item);
  });
  $('photo-count').textContent = `${selectedFiles.length} / ${MAX_FILES}`;
  $('upload-meta').hidden = !selectedFiles.length;
  syncUploadButton();
}
$('clear-btn').addEventListener('click', () => {
  selectedFiles = []; $('upload-error').hidden = true; renderPreviews(); $('dropzone').focus();
});
function selectedPlatforms() { return Object.keys(PLATFORM_NAMES).filter(platform => $(`platform-${platform}`).checked); }
function syncUploadButton() {
  const none = selectedPlatforms().length === 0;
  $('platform-hint').hidden = !none;
  $('analyze-btn').disabled = busy || !selectedFiles.length || none;
}
['platform-ebay', 'platform-kleinanzeigen'].forEach(id => $(id).addEventListener('change', syncUploadButton));

$('analyze-btn').addEventListener('click', async () => {
  if (busy || !selectedFiles.length || !selectedPlatforms().length) return;
  $('app-message').hidden = true;
  setBusy(true); setView('loading');
  $('loading-hint').textContent = '';
  loadingTimer = setTimeout(() => { $('loading-hint').textContent = 'Verarbeitung läuft noch …'; }, 45000);
  try {
    const body = new FormData(); selectedFiles.forEach(file => body.append('images', file)); body.append('platforms', selectedPlatforms().join(','));
    const data = await request('/api/analyze', { method: 'POST', body });
    if (!data.analyse || (!data.ebay && !data.kleinanzeigen)) throw new Error('Es wurde kein vollständiger Entwurf erstellt. Bitte versuche es erneut.');
    analysisResult = data; publishStates = {}; activeTab = data.ebay ? 'ebay' : 'kleinanzeigen';
    renderReview(); saveDraft(); setView('review');
  } catch (error) { setView('upload'); showError(`Der Entwurf konnte nicht erstellt werden. ${error.message} Deine Fotos bleiben ausgewählt.`); }
  finally { clearTimeout(loadingTimer); setBusy(false); syncUploadButton(); }
});

function activateTab(platform, focus = false) {
  activeTab = platform;
  document.querySelectorAll('[role="tab"]').forEach(tab => {
    const active = tab.dataset.tab === platform;
    tab.classList.toggle('tab--active', active); tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1;
    if (active && focus) tab.focus();
    $(`tab-${tab.dataset.tab}`).hidden = !active;
  });
  renderPriceResearch();
}
document.querySelectorAll('[role="tab"]').forEach(tab => {
  tab.addEventListener('click', () => { activateTab(tab.dataset.tab); saveDraft(); });
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const target = event.key === 'Home' ? 'ebay' : event.key === 'End' ? 'kleinanzeigen' : activeTab === 'ebay' ? 'kleinanzeigen' : 'ebay';
    activateTab(target, true); saveDraft();
  });
});
function updateCounter(p) {
  const length = $(`${p}-titel`).value.length; const max = p === 'ebay' ? 80 : 60;
  $(`${p}-titel-count`).textContent = `${length} / ${max}`;
  $(`${p}-titel-count`).classList.toggle('warn', length > max * .85);
  $(`${p}-titel-count`).classList.toggle('over', length > max);
}
function renderReview(savedForms = {}) {
  renderAnalysisSummary();
  $('review-photos').replaceChildren();
  imageUrls.forEach((url, index) => { const img = document.createElement('img'); img.src = url; img.alt = `Produktfotos: Ansicht ${index + 1}`; $('review-photos').append(img); });
  if (!imageUrls.length) {
    const notice = document.createElement('p'); notice.className = 'restored-photos';
    notice.textContent = `${analysisResult.image_paths?.length || 0} ${analysisResult.image_paths?.length === 1 ? 'Foto' : 'Fotos'} gespeichert`;
    $('review-photos').append(notice);
  }
  for (const platform of Object.keys(PLATFORM_NAMES)) {
    renderPlatform(platform, analysisResult[platform]);
    if (savedForms[platform]) applySavedForm(platform, savedForms[platform]);
    updateCounter(prefix(platform));
    renderPublishState(platform);
  }
  activateTab(activeTab);
  syncPriceType();
}
function renderAnalysisSummary() {
  const a = analysisResult.analyse;
  const items = [['Zustand', a.zustand], ['Marke', a.marke || 'Nicht erkannt'], ['Kategorie', a.kategorie_vorschlag]];
  if (a.zustand_beschreibung) items.push(['Zustandsbeschreibung', a.zustand_beschreibung]);
  $('analysis-summary').innerHTML = `<h3 class="analysis-title">${esc(a.artikel_name || 'Dein Artikel')}</h3><div class="analysis-grid">${items.map(([label, value]) => `<div><span class="analysis-item__label">${label}</span><span class="analysis-item__value">${esc(value || '–')}</span></div>`).join('')}</div><div class="analysis-features">${(Array.isArray(a.features) ? a.features : []).map(item => `<span class="feature-pill">${esc(item)}</span>`).join('')}</div>`;
}
function renderPlatform(platform, listing) {
  const p = prefix(platform);
  $(`${p}-generate-prompt`).hidden = Boolean(listing);
  $(`${p}-fields`).hidden = !listing;
  $(`${p}-tab-state`).textContent = listing ? '' : '–';
  $(`${p}-fields`).reset();
  for (const name of ['titel', 'preis', 'beschreibung', 'kategorie']) clearFieldError($(`${p}-${name}`));
  if (!listing) return;
  $(`${p}-titel`).value = listing.titel || '';
  $(`${p}-beschreibung`).value = platform === 'ebay' ? descriptionText(listing.beschreibung || '') : listing.beschreibung || '';
  $(`${p}-kategorie`).value = listing.kategorie || '';
  const condition = analysisResult.analyse.zustand;
  $(`${p}-zustand`).value = ['Neu', 'Wie neu', 'Sehr gut', 'Gut', 'Akzeptabel'].includes(condition) ? condition : 'Gut';
  const price = analysisResult.preisrecherche?.vorschlag;
  $(`${p}-preis`).value = price != null && Number.isFinite(Number(price)) ? Number(price).toFixed(2) : '';
  $(`${p}-tags`).innerHTML = (Array.isArray(listing.tags) ? listing.tags : []).map(tag => `<span class="tag">${esc(tag)}</span>`).join('');
  updateCounter(p);
  if (platform === 'ebay') { $('ebay-beschreibung-preview').hidden = true; $('ebay-preview-toggle').setAttribute('aria-expanded', 'false'); $('ebay-preview-toggle').textContent = 'Vorschau'; }
}
function renderPriceResearch() {
  if (!analysisResult) return;
  const p = analysisResult.preisrecherche;
  if (!p || !p.anzahl_treffer) {
    $('price-research').innerHTML = '<p class="price-caption">Keine Vergleichspreise gefunden.</p>'; return;
  }
  const available = p.vorschlag != null && Number.isFinite(Number(p.vorschlag));
  $('price-research').innerHTML = `<p class="price-caption">Preisvorschlag</p><div class="suggested-price">${money(p.vorschlag)}</div><p class="price-caption">${esc(p.anzahl_treffer)} Vergleichsangebote</p><div class="price-range"><div><span>Minimum</span><strong>${money(p.min_preis)}</strong></div><div><span>Median</span><strong>${money(p.median)}</strong></div><div><span>Maximum</span><strong>${money(p.max_preis)}</strong></div></div><details class="price-comparisons"><summary>Angebote</summary><p class="field-hint">Durchschnitt: ${money(p.durchschnitt)}</p>${(Array.isArray(p.beispiele) ? p.beispiele : []).map(item => `<div class="price-example"><span>${esc(item.titel)}</span><strong>${money(item.preis)}</strong></div>`).join('')}</details>${available ? '<button class="btn btn-outline-secondary" id="apply-price" type="button">Übernehmen</button>' : ''}`;
  if (available) {
    const button = $('apply-price');
    button.disabled = busy || !analysisResult[activeTab] || ['success', 'pending', 'unknown'].includes(publishStates[activeTab]?.status) || (activeTab === 'kleinanzeigen' && ['GIVE_AWAY', 'ON_REQUEST'].includes($('ka-preistyp').value));
    button.addEventListener('click', () => {
      const input = $(`${prefix(activeTab)}-preis`); input.value = Number(p.vorschlag).toFixed(2); clearFieldError(input); saveDraft(); input.focus();
    });
  }
}
async function generatePlatform(platform) {
  if (busy || !analysisResult) return;
  const btn = $(`${prefix(platform)}-generate-btn`); const original = btn.textContent;
  setBusy(true); btn.textContent = 'Entwurf wird erstellt …';
  try {
    const data = await post('/api/generate', { analyse: analysisResult.analyse, platform });
    if (!data.listing) throw new Error('Der Server hat keinen Entwurf geliefert.');
    analysisResult[platform] = data.listing; renderPlatform(platform, data.listing); saveDraft();
  } catch (error) { showError(error.message); }
  finally { btn.textContent = original; setBusy(false); }
}
$('ebay-generate-btn').addEventListener('click', () => generatePlatform('ebay'));
$('ka-generate-btn').addEventListener('click', () => generatePlatform('kleinanzeigen'));

// Preview has both a sandbox and a strict allowlist; generated markup cannot run scripts.
function safeDescription(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const allowed = new Set(['H1','H2','H3','H4','H5','H6','P','UL','OL','LI','BR','STRONG','EM','B','I','U','DIV','SPAN','TABLE','TBODY','THEAD','TD','TR','TH','BLOCKQUOTE','HR']);
  for (const element of [...doc.body.querySelectorAll('*')]) {
    if (['SCRIPT','STYLE','IFRAME','OBJECT','EMBED','FORM','INPUT','BUTTON','LINK','META','SVG','MATH'].includes(element.tagName)) element.remove();
    else if (!allowed.has(element.tagName)) element.replaceWith(...element.childNodes);
    else for (const attribute of [...element.attributes]) element.removeAttribute(attribute.name);
  }
  return doc.body.innerHTML;
}
function descriptionText(html) {
  const doc = new DOMParser().parseFromString(safeDescription(html), 'text/html');
  function text(node) {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent;
    if (node.nodeName === 'BR') return '\n';
    const content = Array.from(node.childNodes, text).join('');
    if (node.nodeName === 'LI') return `• ${content.trim()}\n`;
    if (/^(P|DIV|H[1-6]|UL|OL|BLOCKQUOTE|TR)$/.test(node.nodeName)) return `${content.trim()}\n\n`;
    return content;
  }
  return text(doc.body).replace(/\n{3,}/g, '\n\n').trim();
}
function ebayDescriptionMarkup() {
  const value = $('ebay-beschreibung').value.trim();
  const original = analysisResult?.ebay?.beschreibung || '';
  // Preserve generated headings/lists until the user changes the description.
  if (value === descriptionText(original)) return safeDescription(original);
  return value.split(/\n\s*\n/).filter(Boolean).map(paragraph => {
    const lines = paragraph.split('\n');
    if (lines.every(line => /^[•*-] /.test(line))) return `<ul>${lines.map(line => `<li>${esc(line.slice(2))}</li>`).join('')}</ul>`;
    return `<p>${esc(paragraph).replace(/\n/g, '<br>')}</p>`;
  }).join('');
}
function updatePreview() {
  $('ebay-beschreibung-preview').srcdoc = `<!doctype html><html lang="de"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';"><style>body{font:14px/1.7 -apple-system,BlinkMacSystemFont,sans-serif;color:#111;padding:14px}h1,h2,h3{font-size:17px}ul,ol{padding-left:22px}</style></head><body>${ebayDescriptionMarkup()}</body></html>`;
}
$('ebay-preview-toggle').addEventListener('click', () => {
  const visible = $('ebay-beschreibung-preview').hidden;
  $('ebay-beschreibung-preview').hidden = !visible;
  $('ebay-preview-toggle').textContent = visible ? 'Vorschau ausblenden' : 'Vorschau';
  $('ebay-preview-toggle').setAttribute('aria-expanded', String(visible));
  if (visible) updatePreview();
});

function syncPriceType() {
  const optional = ['GIVE_AWAY', 'ON_REQUEST'].includes($('ka-preistyp').value);
  $('ka-preis').disabled = optional;
  $('ka-preis').required = !optional;
  $('ka-preis-hint').textContent = optional ? '' : '';
  if (optional) clearFieldError($('ka-preis'));
  renderPriceResearch();
}
$('ka-preistyp').addEventListener('change', syncPriceType);
function clearFieldError(input) {
  input.removeAttribute('aria-invalid');
  const error = $(`${input.id}-error`); if (error) { error.textContent = ''; error.hidden = true; }
}
function fieldError(input, message) {
  input.setAttribute('aria-invalid', 'true');
  const error = $(`${input.id}-error`); if (error) { error.textContent = message; error.hidden = false; }
  const details = input.closest('details'); if (details) details.open = true;
}
function validateForm(platform) {
  const p = prefix(platform); const errors = [];
  const title = $(`${p}-titel`), price = $(`${p}-preis`), desc = $(`${p}-beschreibung`), category = $(`${p}-kategorie`);
  [title, price, desc, category].forEach(clearFieldError);
  if (!title.value.trim() || title.value.length > (platform === 'ebay' ? 80 : 60)) errors.push([title, `Bitte gib einen Titel mit 1 bis ${platform === 'ebay' ? 80 : 60} Zeichen ein.`]);
  if (!price.disabled && (!price.value || !Number.isFinite(price.valueAsNumber) || price.valueAsNumber <= 0 || price.validity.stepMismatch)) errors.push([price, 'Bitte gib einen Preis größer als 0 € mit höchstens zwei Nachkommastellen ein.']);
  const text = desc.value;
  if (!text.trim()) errors.push([desc, 'Bitte ergänze eine Beschreibung für deinen Artikel.']);
  if (platform === 'ebay' && category.value.trim() && !/^\d+$/.test(category.value.trim())) errors.push([category, 'Die eBay-Kategorie-ID darf nur Ziffern enthalten.']);
  errors.forEach(([input, message]) => fieldError(input, message));
  if (errors.length) errors[0][0].focus();
  return errors.length === 0;
}
function collectForm(platform) {
  const p = prefix(platform);
  const listing = {
    plattform: platform,
    titel: $(`${p}-titel`).value.trim(), beschreibung: platform === 'ebay' ? ebayDescriptionMarkup() : $(`${p}-beschreibung`).value.trim(),
    preis: Number($(`${p}-preis`).value) || 0, zustand: $(`${p}-zustand`).value,
    kategorie: $(`${p}-kategorie`).value.trim(),
    tags: Array.from($(`${p}-tags`).querySelectorAll('.tag')).map(tag => tag.textContent),
    analyse: analysisResult?.analyse || {},
  };
  if (platform === 'ebay') listing.versand_policy_id = $('ebay-versand-policy').value;
  else {
    listing.versand = $('ka-versand').value; listing.preistyp = $('ka-preistyp').value; listing.kleinanzeigen_kategorie = listing.kategorie;
    if (['GIVE_AWAY', 'ON_REQUEST'].includes(listing.preistyp)) listing.preis = 0;
  }
  return listing;
}

// Drafts are scoped to this tab; original price text is retained, including an empty field.
function captureForms() {
  const forms = {};
  for (const platform of Object.keys(PLATFORM_NAMES)) {
    if (!analysisResult?.[platform]) continue;
    forms[platform] = {};
    $(`${prefix(platform)}-fields`).querySelectorAll('input,select,textarea').forEach(input => { forms[platform][input.id] = input.value; });
  }
  return forms;
}
function applySavedForm(platform, values) {
  $(`${prefix(platform)}-fields`).querySelectorAll('input,select,textarea').forEach(input => { if (typeof values[input.id] === 'string') input.value = values[input.id]; });
}
function saveDraft() {
  if (!analysisResult) return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, result: analysisResult, forms: captureForms(), activeTab, publishStates }));
    storageAvailable = true; $('draft-status').textContent = 'Gespeichert';
  } catch { storageAvailable = false; $('draft-status').textContent = 'Nicht gespeichert'; }
}
function restoreDraft() {
  try {
    const draft = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    if (!draft || draft.version !== 1 || !draft.result?.analyse || (!draft.result.ebay && !draft.result.kleinanzeigen)) return;
    analysisResult = draft.result; activeTab = Object.hasOwn(PLATFORM_NAMES, draft.activeTab) ? draft.activeTab : 'ebay';
    publishStates = draft.publishStates || {};
    for (const state of Object.values(publishStates)) {
      if (state.status === 'pending') { state.status = 'unknown'; state.error = 'Der Tab wurde während der Veröffentlichung neu geladen. Prüfe zuerst auf der Plattform, ob das Inserat bereits online ist.'; }
    }
    renderReview(draft.forms); setView('review', false); setBusy(false); saveDraft();

  } catch { storageAvailable = false; }
}
for (const platform of Object.keys(PLATFORM_NAMES)) {
  const p = prefix(platform);
  $(`${p}-fields`).addEventListener('input', event => {
    if (event.target.matches('input,textarea,select')) clearFieldError(event.target);
    updateCounter(p);
    if (event.target.id === 'ebay-beschreibung' && !$('ebay-beschreibung-preview').hidden) updatePreview();
    saveDraft();
  });
  $(`${p}-fields`).addEventListener('change', saveDraft);
  $(`${p}-fields`).addEventListener('submit', event => { event.preventDefault(); preparePublish(platform); });
}
window.addEventListener('beforeunload', event => {
  if (busy || (!analysisResult && selectedFiles.length) || (analysisResult && !storageAvailable)) { event.preventDefault(); event.returnValue = ''; }
});

function openDialog({ title, description, details = '', confirmLabel, cancelLabel = 'Abbrechen', action }) {
  $('dialog-title').textContent = title; $('dialog-description').textContent = description; $('dialog-details').innerHTML = details;
  $('dialog-confirm').textContent = confirmLabel; $('dialog-cancel').textContent = cancelLabel; confirmAction = action;
  $('confirm-dialog').showModal(); $('dialog-cancel').focus();
}
function closeDialog() { $('confirm-dialog').close(); confirmAction = null; }
$('dialog-close').addEventListener('click', closeDialog);
$('dialog-cancel').addEventListener('click', closeDialog);
$('confirm-dialog').addEventListener('cancel', () => { confirmAction = null; });
$('dialog-confirm').addEventListener('click', () => { const action = confirmAction; closeDialog(); if (action) action(); });
$('new-btn').addEventListener('click', () => {
  if (busy) return;
  openDialog({ title: 'Entwurf verwerfen?', description: 'Die Änderungen an diesem Entwurf gehen verloren.', confirmLabel: 'Verwerfen', action: resetWorkspace });
});
function resetWorkspace() {
  if (busy) return;
  analysisResult = null; selectedFiles = []; publishStates = {}; activeTab = 'ebay';
  try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* session storage can be unavailable */ }
  for (const platform of Object.keys(PLATFORM_NAMES)) {
    const p = prefix(platform); $(`${p}-fields`).reset(); $(`${p}-fieldset`).disabled = false; $(`${p}-publish-result`).hidden = true;
    $(`${p}-confirm-btn`).disabled = false; $(`${p}-confirm-btn`).innerHTML = 'Veröffentlichen';
  }
  $('ebay-beschreibung-preview').srcdoc = ''; $('ebay-beschreibung-preview').hidden = true;
  $('app-message').hidden = true; $('upload-error').hidden = true;
  renderPreviews(); setView('upload'); window.scrollTo({ top: 0 });
}
function preparePublish(platform) {
  if (busy || !analysisResult?.[platform] || ['success', 'pending', 'unknown'].includes(publishStates[platform]?.status)) return;
  if (!validateForm(platform)) return;
  if (!analysisResult.image_paths?.length) { showError('Die Fotos zu diesem Entwurf fehlen. Starte einen neuen Artikel und lade die Fotos erneut hoch.'); return; }
  if (platform === 'ebay' && connections.ebay !== true) {
    openDialog({ title: 'eBay verbinden', description: 'Zum Veröffentlichen fehlt die Kontoverbindung.', confirmLabel: 'Konten öffnen', action: () => openAccounts() }); return;
  }
  const listing = collectForm(platform);
  const price = listing.preistyp === 'GIVE_AWAY' ? 'Zu verschenken' : listing.preistyp === 'ON_REQUEST' ? 'Auf Anfrage' : money(listing.preis) + (listing.preistyp === 'NEGOTIABLE' ? ' VB' : '');
  const shipping = platform === 'ebay' ? $('ebay-versand-policy').selectedOptions[0].textContent : listing.versand;
  const details = `<div class="dialog-summary"><strong>${esc(listing.titel)}</strong><dl><div><dt>Plattform</dt><dd>${PLATFORM_NAMES[platform]}</dd></div><div><dt>Preis</dt><dd>${esc(price)}</dd></div><div><dt>Zustand</dt><dd>${esc(listing.zustand)}</dd></div><div><dt>Versand</dt><dd>${esc(shipping)}</dd></div><div><dt>Fotos</dt><dd>${analysisResult.image_paths.length}</dd></div></dl></div>${platform === 'kleinanzeigen' ? '<p class="dialog-notice">Anmeldung erfolgt im geöffneten Browserfenster.</p>' : ''}`;
  openDialog({ title: `Auf ${PLATFORM_NAMES[platform]} veröffentlichen?`, description: '', details, confirmLabel: 'Veröffentlichen', action: () => publish(platform, listing) });
}
async function publish(platform, listing) {
  if (busy) return;
  publishStates[platform] = { status: 'pending' }; setBusy(true); renderPublishState(platform); saveDraft();
  try {
    const data = await post(`/api/publish/${platform}`, { listing, image_paths: analysisResult.image_paths });
    if (data.success) {
      publishStates[platform] = { status: 'success', url: safeUrl(data.listing_url) };

    } else {
      publishStates[platform] = { status: 'error', error: data.error || data.detail || 'Die Plattform konnte das Inserat nicht veröffentlichen.' };
    }
  } catch (error) {
    // A lost response does not establish whether the platform already published.
    publishStates[platform] = { status: 'unknown', error: `${error.message} Der Veröffentlichungsstatus ist unklar. Prüfe dein Konto auf ${PLATFORM_NAMES[platform]}, bevor du es erneut versuchst.` };
  } finally {
    setBusy(false); renderPublishState(platform); saveDraft(); setView('review', false); activateTab(activeTab);
    $(`${prefix(platform)}-publish-result`).scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}
function renderPublishState(platform) {
  const p = prefix(platform), state = publishStates[platform], result = $(`${p}-publish-result`), button = $(`${p}-confirm-btn`);
  const locked = ['success', 'pending', 'unknown'].includes(state?.status);
  $(`${p}-fieldset`).disabled = busy || locked; button.disabled = busy || locked;
  result.hidden = !state;
  button.innerHTML = 'Veröffentlichen';
  if (!state) return;
  result.className = `publish-result${['error', 'unknown'].includes(state.status) ? ' publish-result--error' : ''}`;
  if (state.status === 'pending') {
    button.textContent = 'Wird veröffentlicht …'; result.textContent = platform === 'kleinanzeigen' ? 'Veröffentlichung läuft. Bei Bedarf im Browserfenster anmelden.' : 'Veröffentlichung läuft …';
  } else if (state.status === 'success') {
    button.innerHTML = `${icon('check')} Veröffentlicht`;
    $(`${p}-tab-state`).textContent = 'Online';
    const url = safeUrl(state.url);
    result.innerHTML = `<strong>Veröffentlicht.</strong>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Inserat auf ${PLATFORM_NAMES[platform]} ansehen ↗</a>` : ''}`;
  } else {
    button.textContent = state.status === 'unknown' ? 'Status auf der Plattform prüfen' : 'Erneut prüfen';
    result.textContent = state.error;
    if (state.status === 'unknown') {
      const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'btn btn-outline-secondary mt-3'; retry.textContent = 'Geprüft: Inserat wurde nicht erstellt';
      retry.addEventListener('click', () => {
        if (busy) return;
        delete publishStates[platform]; renderPublishState(platform); setBusy(false); saveDraft();
      }); result.append(document.createElement('br'), retry);
    }
  }
}

// Account setup is independent of draft generation and has its own destination.
async function refreshConnections() {
  const refresh = $('refresh-connections'); refresh.disabled = true; refresh.textContent = 'Wird geprüft …';
  await Promise.all(Object.keys(PLATFORM_NAMES).map(async platform => {
    const p = prefix(platform); const badge = $(`${p}-connection-badge`);
    try {
      const data = await request(`/auth/${platform}/status`); connections[platform] = Boolean(data.connected);
      badge.textContent = data.connected ? (platform === 'ebay' ? 'Zugang hinterlegt' : 'Profil vorhanden') : (platform === 'ebay' ? 'Nicht verbunden' : 'Anmeldung erforderlich');
      badge.classList.toggle('connected', Boolean(data.connected));
      if (platform === 'ebay') {
        $('ebay-connect-section').hidden = Boolean(data.connected); $('connect-step-3').hidden = !data.connected;
      } else {
        $('ka-status-text').textContent = data.connected ? '' : 'Anmeldung beim Veröffentlichen.';
      }
    } catch {
      connections[platform] = null; badge.textContent = 'Status nicht erreichbar'; badge.classList.remove('connected');
      if (platform === 'ebay') { $('ebay-connect-section').hidden = false; $('connect-step-3').hidden = true; }
    }
  }));
  refresh.disabled = false; refresh.textContent = 'Aktualisieren';
}
$('refresh-connections').addEventListener('click', refreshConnections);
$('connect-ebay-btn').addEventListener('click', async () => {
  // Open synchronously to avoid popup blocking after the network request.
  const authWindow = window.open('about:blank', '_blank');
  if (authWindow) authWindow.opener = null;
  $('connect-ebay-btn').disabled = true; $('connect-error').hidden = true;
  try {
    const data = await request('/auth/ebay'); const url = safeUrl(data.auth_url);
    if (!url) throw new Error('Der Server hat keine gültige Anmelde-URL geliefert.');
    if (!authWindow) throw new Error('Bitte erlaube Pop-ups für diese lokale Anwendung und versuche es erneut.');
    authWindow.location = url;
    $('oauth-reopen-link').href = url; $('oauth-reopen-link').hidden = false;
    $('connect-step-1').hidden = true; $('connect-step-2').hidden = false; $('oauth-code-input').focus();
  } catch (error) {
    authWindow?.close(); $('connect-error').textContent = error.message; $('connect-error').hidden = false;
  } finally { $('connect-ebay-btn').disabled = false; }
});
$('connect-step-2').addEventListener('submit', async event => {
  event.preventDefault(); const raw = $('oauth-code-input').value.trim(); if (!raw) return;
  let code = raw;
  try {
    if (raw.includes('?')) code = new URLSearchParams(raw.slice(raw.indexOf('?') + 1)).get('code') || raw;
    else if (raw.startsWith('code=')) code = new URLSearchParams(raw).get('code') || raw;
    else if (raw.includes('%')) code = decodeURIComponent(raw);
  } catch { /* A bare authorization code can legitimately be non-URL text. */ }
  $('save-token-btn').disabled = true; $('save-token-btn').textContent = 'Wird gespeichert …'; $('connect-error').hidden = true;
  try {
    await post('/auth/ebay/callback', { code }); $('oauth-code-input').value = ''; $('connect-step-2').hidden = true;
    await refreshConnections();
  } catch (error) { $('connect-error').textContent = error.message; $('connect-error').hidden = false; }
  finally { $('save-token-btn').disabled = false; $('save-token-btn').textContent = 'Speichern'; }
});

restoreDraft();
refreshConnections();
