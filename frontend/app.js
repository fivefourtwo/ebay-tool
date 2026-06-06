'use strict';

// -- eBay OAuth --
(async function initEbayConnect() {
  const section   = document.getElementById('ebay-connect-section');
  const step1     = document.getElementById('connect-step-1');
  const step2     = document.getElementById('connect-step-2');
  const step3     = document.getElementById('connect-step-3');
  const connectBtn= document.getElementById('connect-ebay-btn');
  const codeInput = document.getElementById('oauth-code-input');
  const saveBtn   = document.getElementById('save-token-btn');
  const errorEl   = document.getElementById('connect-error');

  // Check current status
  try {
    const res  = await fetch('/auth/ebay/status');
    const data = await res.json();
    if (data.connected) return; // already connected, keep section hidden
  } catch (_) {}

  section.hidden = false;

  // Step 1: open eBay auth in new tab
  connectBtn.addEventListener('click', async () => {
    try {
      const res  = await fetch('/auth/ebay');
      const data = await res.json();
      window.open(data.auth_url, '_blank');
      step1.hidden = true;
      step2.hidden = false;
    } catch (err) {
      alert('Fehler beim Laden der Auth-URL: ' + err.message);
    }
  });

  // Step 2: exchange code
  saveBtn.addEventListener('click', async () => {
    const raw  = codeInput.value.trim();
    if (!raw) return;

    // Accept either the bare code or the full query string / URL
    let code = raw;
    try {
      const params = new URLSearchParams(
        raw.includes('?') ? raw.split('?')[1] : raw.startsWith('code=') ? raw : 'code=' + raw
      );
      if (params.get('code')) code = params.get('code');
    } catch (_) {}

    errorEl.hidden = true;
    saveBtn.disabled = true;
    saveBtn.textContent = 'Wird gespeichert...';

    try {
      const res = await fetch('/auth/ebay/callback', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ code }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }

      step2.hidden = true;
      step3.hidden = false;
      // Fade out banner after 3 s
      setTimeout(() => { section.hidden = true; }, 3000);
    } catch (err) {
      errorEl.textContent = 'Fehler: ' + err.message;
      errorEl.hidden      = false;
      saveBtn.disabled    = false;
      saveBtn.textContent = 'Token speichern';
    }
  });
})();

// -- State --
let selectedFiles = [];
let analysisResult = null;

// -- DOM refs --
const dropzone      = document.getElementById('dropzone');
const fileInput     = document.getElementById('file-input');
const previewGrid   = document.getElementById('preview-grid');
const uploadActions = document.getElementById('upload-actions');
const analyzeBtn    = document.getElementById('analyze-btn');
const clearBtn      = document.getElementById('clear-btn');

const uploadSection  = document.getElementById('upload-section');
const loadingSection = document.getElementById('loading-section');
const reviewSection  = document.getElementById('review-section');
const newBtn         = document.getElementById('new-btn');

// -- Upload / drag & drop --
dropzone.addEventListener('click', () => fileInput.click());

dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('dragover');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  addFiles(Array.from(e.dataTransfer.files));
});

fileInput.addEventListener('change', () => {
  addFiles(Array.from(fileInput.files));
  fileInput.value = '';
});

clearBtn.addEventListener('click', resetUpload);

function addFiles(files) {
  const imageFiles = files.filter(f => f.type.startsWith('image/'));
  selectedFiles = [...selectedFiles, ...imageFiles];
  renderPreviews();
}

function renderPreviews() {
  previewGrid.innerHTML = '';
  selectedFiles.forEach((file, index) => {
    const item = document.createElement('div');
    item.className = 'preview-item';

    const img = document.createElement('img');
    img.src = URL.createObjectURL(file);
    img.alt = file.name;

    const removeBtn = document.createElement('button');
    removeBtn.className = 'preview-item__remove';
    removeBtn.textContent = 'x';
    removeBtn.title = 'Bild entfernen';
    removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      selectedFiles.splice(index, 1);
      renderPreviews();
    });

    item.appendChild(img);
    item.appendChild(removeBtn);
    previewGrid.appendChild(item);
  });

  const hasFiles = selectedFiles.length > 0;
  uploadActions.hidden = !hasFiles;
}

function resetUpload() {
  selectedFiles = [];
  analysisResult = null;
  previewGrid.innerHTML = '';
  uploadActions.hidden = true;
}

// -- Analyze --
analyzeBtn.addEventListener('click', async () => {
  if (selectedFiles.length === 0) return;

  setView('loading');

  try {
    const formData = new FormData();
    selectedFiles.forEach(file => formData.append('images', file));

    const res = await fetch('/api/analyze', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Unbekannter Fehler');
    }

    analysisResult = await res.json();
    renderReview(analysisResult);
    setView('review');
  } catch (err) {
    setView('upload');
    alert('Fehler: ' + err.message);
  }
});

// -- View switching --
function setView(view) {
  uploadSection.hidden  = view !== 'upload';
  loadingSection.hidden = view !== 'loading';
  reviewSection.hidden  = view !== 'review';
}

newBtn.addEventListener('click', () => {
  resetUpload();
  setView('upload');
});

// -- Tabs --
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('tab--active'));
    tab.classList.add('tab--active');
    document.querySelectorAll('.tab-content').forEach(c => { c.hidden = true; });
    document.getElementById('tab-' + tab.dataset.tab).hidden = false;
  });
});

// -- Character counters --
function setupCounter(inputId, counterId, max) {
  const input   = document.getElementById(inputId);
  const counter = document.getElementById(counterId);
  const update  = () => {
    const len = input.value.length;
    counter.textContent = len + '/' + max;
    counter.classList.toggle('warn', len > max * 0.85);
    counter.classList.toggle('over', len >= max);
  };
  input.addEventListener('input', update);
  return update;
}

const updateEbayCount = setupCounter('ebay-titel', 'ebay-titel-count', 80);
const updateKaCount   = setupCounter('ka-titel',   'ka-titel-count',   60);

// -- HTML description preview --
(function setupPreviewToggle() {
  const toggle    = document.getElementById('ebay-preview-toggle');
  const textarea  = document.getElementById('ebay-beschreibung');
  const previewEl = document.getElementById('ebay-beschreibung-preview');
  if (!toggle || !previewEl) return;

  let visible = false;

  function syncPreview() {
    previewEl.innerHTML = textarea.value;
  }

  toggle.addEventListener('click', () => {
    visible = !visible;
    previewEl.hidden = !visible;
    toggle.textContent = visible ? 'Vorschau ausblenden' : 'Vorschau anzeigen';
    if (visible) syncPreview();
  });

  textarea.addEventListener('input', () => {
    if (visible) syncPreview();
  });
})();

// -- Price info renderer --
function fmt(value) {
  if (value == null) return '--';
  return value.toFixed(2).replace('.', ',') + ' EUR';
}

function renderPreisInfo(p) {
  const stats = [
    { label: 'Vorschlag', value: fmt(p.vorschlag), highlight: true },
    { label: 'Min',       value: fmt(p.min_preis) },
    { label: 'Max',       value: fmt(p.max_preis) },
    { label: 'Durchschnitt', value: fmt(p.durchschnitt) },
    { label: 'Median',    value: fmt(p.median) },
    { label: p.anzahl_treffer + ' Angebote', value: null, muted: true },
  ];

  const statHtml = stats.map(s => {
    const cls = 'preis-stat' +
      (s.highlight ? ' preis-stat--highlight' : '') +
      (s.muted     ? ' preis-stat--muted'     : '');
    const text = s.value ? s.label + ': ' + s.value : s.label;
    return '<span class="' + cls + '">' + esc(text) + '</span>';
  }).join('');

  const beispiele = (p.beispiele || []).map(b =>
    '<div class="preis-beispiel">' +
      '<span class="preis-beispiel__titel">' + esc(b.titel) + '</span>' +
      '<span class="preis-beispiel__preis">' + fmt(b.preis) + '</span>' +
    '</div>'
  ).join('');

  return '<div class="preis-stats">' + statHtml + '</div>' +
         (beispiele ? '<div class="preis-beispiele">' + beispiele + '</div>' : '');
}

// -- Render review --
function renderReview(data) {
  renderAnalysisSummary(data.analyse);
  renderForm('ebay',          data.ebay,          data.analyse.zustand, data.preisrecherche);
  renderForm('kleinanzeigen', data.kleinanzeigen,  data.analyse.zustand, data.preisrecherche);
}

function renderAnalysisSummary(analyse) {
  const el       = document.getElementById('analysis-summary');
  const features = Array.isArray(analyse.features) ? analyse.features : [];

  el.innerHTML =
    '<div class="analysis-title">Erkannter Artikel: ' + esc(analyse.artikel_name) + '</div>' +
    '<div class="analysis-grid">' +
      '<div class="analysis-item">' +
        '<span class="analysis-item__label">Zustand</span>' +
        '<span class="analysis-item__value">' + esc(analyse.zustand) + '</span>' +
      '</div>' +
      '<div class="analysis-item">' +
        '<span class="analysis-item__label">Marke</span>' +
        '<span class="analysis-item__value">' + esc(analyse.marke || '--') + '</span>' +
      '</div>' +
      '<div class="analysis-item">' +
        '<span class="analysis-item__label">Kategorie</span>' +
        '<span class="analysis-item__value">' + esc(analyse.kategorie_vorschlag) + '</span>' +
      '</div>' +
    '</div>' +
    (analyse.zustand_beschreibung
      ? '<div class="analysis-item" style="margin-top:10px">' +
          '<span class="analysis-item__label">Zustandsbeschreibung</span>' +
          '<span class="analysis-item__value">' + esc(analyse.zustand_beschreibung) + '</span>' +
        '</div>'
      : '') +
    (features.length
      ? '<div class="analysis-features">' +
          '<div class="analysis-features__label">Merkmale</div>' +
          features.map(f => '<span class="feature-pill">' + esc(f) + '</span>').join('') +
        '</div>'
      : '');
}

function renderForm(platform, listing, zustand, preisrecherche) {
  const isEbay  = platform === 'ebay';
  const prefix  = isEbay ? 'ebay' : 'ka';

  const titel       = document.getElementById(prefix + '-titel');
  const beschreibung= document.getElementById(prefix + '-beschreibung');
  const kategorie   = document.getElementById(prefix + '-kategorie');
  const zustandEl   = document.getElementById(prefix + '-zustand');
  const tagsEl      = document.getElementById(prefix + '-tags');
  const preisEl     = document.getElementById(prefix + '-preis');
  const preisInfoEl = document.getElementById(prefix + '-preis-info');

  titel.value        = listing.titel || '';
  beschreibung.value = listing.beschreibung || '';
  kategorie.value    = listing.kategorie || '';

  const zustandOptions = ['Neu', 'Wie neu', 'Sehr gut', 'Gut', 'Akzeptabel'];
  zustandEl.value = zustandOptions.includes(zustand) ? zustand : 'Gut';

  if (preisInfoEl) {
    if (preisrecherche && preisrecherche.anzahl_treffer) {
      if (preisrecherche.vorschlag != null) {
        preisEl.value = preisrecherche.vorschlag;
      }
      preisInfoEl.innerHTML = renderPreisInfo(preisrecherche);
    } else {
      preisInfoEl.innerHTML = '<span class="preis-info--empty">Keine Vergleichspreise gefunden</span>';
    }
  }

  tagsEl.innerHTML = '';
  const tags = Array.isArray(listing.tags) ? listing.tags : [];
  tags.forEach(tag => {
    const span = document.createElement('span');
    span.className = 'tag';
    span.textContent = tag;
    tagsEl.appendChild(span);
  });

  if (isEbay) updateEbayCount();
  else        updateKaCount();
}

// -- Confirm buttons --
document.getElementById('ebay-confirm-btn').addEventListener('click', () => {
  const data = collectForm('ebay');
  console.log('[eBay] Inserat:', data);
  alert('eBay-Inserat gespeichert (siehe Konsole).');
});

document.getElementById('ka-confirm-btn').addEventListener('click', () => {
  const data = collectForm('kleinanzeigen');
  console.log('[Kleinanzeigen] Inserat:', data);
  alert('Kleinanzeigen-Inserat gespeichert (siehe Konsole).');
});

function collectForm(platform) {
  const prefix      = platform === 'ebay' ? 'ebay' : 'ka';
  const versandRadio= document.querySelector('input[name="' + prefix + '-versand"]:checked');

  return {
    plattform:    platform,
    titel:        document.getElementById(prefix + '-titel').value,
    beschreibung: document.getElementById(prefix + '-beschreibung').value,
    preis:        parseFloat(document.getElementById(prefix + '-preis').value) || 0,
    zustand:      document.getElementById(prefix + '-zustand').value,
    versand:      versandRadio ? versandRadio.value : '',
    kategorie:    document.getElementById(prefix + '-kategorie').value,
    tags:         Array.from(document.querySelectorAll('#' + prefix + '-tags .tag')).map(t => t.textContent),
    analyse:      analysisResult ? analysisResult.analyse : {},
  };
}

// -- Utils --
function esc(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
