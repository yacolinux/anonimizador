let currentData = null;
let allPositions = [];
let markedPositions = null;
let manualMarked = null;

const uploadArea = document.getElementById('upload-area');
const uploadBtn = document.getElementById('upload-btn');
const uploadContent = document.getElementById('upload-content');
const uploadProgress = document.getElementById('upload-progress');
const fileInput = document.getElementById('file-input');
const mainLayout = document.getElementById('main-layout');
const documentBody = document.getElementById('document-body');
const fileBadge = document.getElementById('file-badge');
const piiList = document.getElementById('pii-list');
const wordCount = document.getElementById('word-count');
const emptyState = document.getElementById('empty-state');
const addWordInput = document.getElementById('add-word-input');
const addWordBtn = document.getElementById('add-word-btn');
const exportFormat = document.getElementById('export-format');
const exportBtn = document.getElementById('export-btn');
const exportHint = document.getElementById('export-hint');
const replacementText = document.getElementById('replacement-text');
const toast = document.getElementById('toast');
const themeToggle = document.getElementById('theme-toggle');
const markAllCb = document.getElementById('mark-all-cb');
const reasonBtn = document.getElementById('reason-btn');
const reasonModal = document.getElementById('reason-modal');
const reasonContent = document.getElementById('reason-content');
const reasonClose = document.getElementById('reason-close');
const btnCopyText = document.getElementById('btn-copy-text');
const retryAiBtn = document.getElementById('retry-ai-btn');
const aiWaitModal = document.getElementById('ai-wait-modal');
const aiWaitText = document.getElementById('ai-wait-text');
const continueNoAiBtn = document.getElementById('continue-no-ai-btn');

let currentReasoning = '';
let aiRetryTimer = null;
let aiRetryCancelled = false;

const AI_RETRY_INTERVAL_MS = 5000;
const AI_RETRY_MAX_WAIT_MS = 60000;

function applyTheme(light) {
  document.body.classList.toggle('light-theme', light);
  localStorage.setItem('theme', light ? 'light' : 'dark');
}
const saved = localStorage.getItem('theme');
if (saved === 'light') applyTheme(true);
themeToggle.addEventListener('click', () => {
  applyTheme(!document.body.classList.contains('light-theme'));
});

function triggerFilePicker() { fileInput.click(); }
uploadArea.addEventListener('click', triggerFilePicker);
uploadBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) uploadFile(fileInput.files[0]);
});
uploadArea.addEventListener('dragover', (e) => {
  e.preventDefault(); uploadArea.classList.add('dragover');
});
uploadArea.addEventListener('dragleave', () => {
  uploadArea.classList.remove('dragover');
});
uploadArea.addEventListener('drop', (e) => {
  e.preventDefault(); uploadArea.classList.remove('dragover');
  if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
});

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}

async function uploadFile(file) {
  stopAiRetryLoop();
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['pdf', 'docx'].includes(ext)) {
    showToast('Solo se admiten archivos PDF y DOCX');
    return;
  }
  uploadContent.hidden = true;
  uploadProgress.hidden = false;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) {
      showToast('Error: ' + data.error);
      uploadContent.hidden = false;
      uploadProgress.hidden = true;
      return;
    }
    currentData = data;
    if (data.queue_notice) {
      showToast(data.queue_notice);
    }
    if (data.used_ocr) {
      showToast('Documento escaneado detectado. Procesamiento OCR aplicado.');
    }
    fileBadge.textContent = file.name;
    uploadProgress.hidden = true;
    mainLayout.hidden = false;
    uploadArea.style.padding = '20px';
    uploadContent.hidden = false;
    uploadBtn.textContent = 'Cargar nuevo documento';

    if (ext === 'pdf') {
      exportFormat.value = 'pdf';
      exportFormat.querySelector('option[value="docx"]').disabled = true;
      exportHint.hidden = false;
    } else {
      exportFormat.querySelector('option[value="docx"]').disabled = false;
      exportHint.hidden = true;
    }

    applyAnalysisResult(data, true);
    if (data.ai_status && data.ai_status !== 'ok') {
      retryAiBtn.hidden = false;
      startAiRetryLoop();
    } else {
      retryAiBtn.hidden = true;
    }
  } catch (err) {
    showToast('Error al subir el archivo');
    uploadContent.hidden = false;
    uploadProgress.hidden = true;
  }
}

function applyAnalysisResult(data, resetManual) {
  currentReasoning = data.reasoning || '';
  allPositions = (data.positions || []).map(p => ({
    segment: p.segment,
    start: p.start,
    end: p.end,
    word: p.word,
    type: p.type
  }));
  markedPositions = new Set(allPositions.map(p => key(p)));
  if (resetManual) {
    manualMarked = new Set();
  }
  if (currentData && currentData.segments) {
    renderDocument(currentData.segments);
  }
  renderPiiList();
}

function stopAiRetryLoop() {
  if (aiRetryTimer) {
    clearTimeout(aiRetryTimer);
    aiRetryTimer = null;
  }
  aiWaitModal.hidden = true;
}

function startAiRetryLoop() {
  if (!currentData || !currentData.filename) return;
  aiRetryCancelled = false;
  aiWaitModal.hidden = false;
  const startedAt = Date.now();

  const tick = async () => {
    if (aiRetryCancelled) {
      stopAiRetryLoop();
      retryAiBtn.hidden = false;
      showToast('Se continuo sin IA. Podes reintentar luego.');
      return;
    }

    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    aiWaitText.textContent = `Proveedor ocupado, en espera. Reintentando cada 5s (${elapsed}s).`;

    if (Date.now() - startedAt > AI_RETRY_MAX_WAIT_MS) {
      stopAiRetryLoop();
      retryAiBtn.hidden = false;
      showToast('Tiempo maximo de espera alcanzado. Se continua sin IA.');
      return;
    }

    try {
      const res = await fetch('/reanalyze-ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: currentData.filename })
      });
      const data = await res.json();
      if (data.queue_notice) showToast(data.queue_notice);
      if (res.ok && data.ai_status === 'ok') {
        stopAiRetryLoop();
        currentData.keywords = data.keywords || [];
        currentData.default_keywords = data.default_keywords || [];
        currentData.positions = data.positions || [];
        currentData.reasoning = data.reasoning || '';
        applyAnalysisResult(currentData, false);
        retryAiBtn.hidden = true;
        showToast('Analisis IA completado correctamente');
        return;
      }
    } catch (err) {
      // retry silently
    }

    aiRetryTimer = setTimeout(tick, AI_RETRY_INTERVAL_MS);
  };

  tick();
}

continueNoAiBtn.addEventListener('click', () => {
  aiRetryCancelled = true;
});

retryAiBtn.addEventListener('click', () => {
  if (!currentData || !currentData.filename) return;
  startAiRetryLoop();
});

function key(p) { return `${p.segment}:${p.start}:${p.end}`; }

function renderDocument(segments) {
  let html = '';
  for (let si = 0; si < segments.length; si++) {
    const seg = segments[si];
    const segPositions = allPositions.filter(p => p.segment === si);
    const parts = buildSpans(seg.text, segPositions);
    html += '<div class="segment segment-' + seg.type + '">' + parts.join('') + '</div>';
  }
  documentBody.innerHTML = html;
  documentBody.querySelectorAll('.word-token').forEach(el => {
    el.addEventListener('click', onWordClick);
  });
}

function getAnonymizedText() {
  if (!currentData) return '';
  const replacement = replacementText.value || '[REDACTADO]';
  const lines = [];
  for (let si = 0; si < currentData.segments.length; si++) {
    const seg = currentData.segments[si];
    const segPositions = allPositions.filter(p => p.segment === si);
    const sorted = [...segPositions].sort((a, b) => a.start - b.start);
    let text = seg.text;
    const replacements = [];
    for (const pos of sorted) {
      const mk = key(pos);
      if (markedPositions.has(mk)) {
        replacements.push({ start: pos.start, end: pos.end, word: pos.word });
      }
    }
    for (const r of replacements.reverse()) {
      text = text.slice(0, r.start) + replacement + text.slice(r.end);
    }
    for (const w of manualMarked) {
      const regex = new RegExp('\\b' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'gi');
      text = text.replace(regex, replacement);
    }
    lines.push(text);
  }
  return lines.join('\n\n');
}

btnCopyText.addEventListener('click', async () => {
  const text = getAnonymizedText();
  if (!text) {
    showToast('No hay documento cargado');
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast('Texto anonimizado copiado al portapapeles');
  } catch (err) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('Texto anonimizado copiado al portapapeles');
  }
});

function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML;
}

function markedWord(w) {
  return manualMarked.has(w.toLowerCase());
}

function buildSpans(text, segPositions) {
  const sorted = [...segPositions].sort((a, b) => a.start - b.start);
  const parts = [];
  let cursor = 0;

  for (const pos of sorted) {
    if (pos.start > cursor) {
      parts.push(buildTextSpans(text.slice(cursor, pos.start)));
    }
    if (pos.end > cursor) {
      const token = text.slice(pos.start, pos.end);
      const mk = key(pos);
      const isMarked = markedPositions.has(mk);
      const cls = 'word-token pii' + (isMarked ? '' : ' unmarked');
      parts.push(`<span class="${cls}" data-k="${escapeHtml(mk)}" data-word="${escapeHtml(token)}">${escapeHtml(token)}</span>`);
      cursor = pos.end;
    }
  }

  if (cursor < text.length) {
    parts.push(buildTextSpans(text.slice(cursor)));
  }
  return parts;
}

function buildTextSpans(text) {
  const words = text.split(/\b/);
  let html = '';
  for (const w of words) {
    if (/^\w+$/.test(w) && w.length >= 2) {
      const isMarked = markedWord(w);
      const cls = 'word-token' + (isMarked ? ' pii' : '');
      html += `<span class="${cls}" data-k="manual" data-word="${escapeHtml(w)}">${escapeHtml(w)}</span>`;
    } else {
      html += escapeHtml(w);
    }
  }
  return html;
}

function onWordClick(e) {
  const el = e.currentTarget;
  const k = el.dataset.k;
  const word = el.dataset.word;
  const wl = word.toLowerCase();

  if (k && k !== 'manual') {
    const isMarked = markedPositions.has(k);
    if (markAllCb.checked) {
      const matching = allPositions.filter(p => p.word.toLowerCase() === wl);
      if (isMarked) {
        for (const p of matching) markedPositions.delete(key(p));
      } else {
        for (const p of matching) markedPositions.add(key(p));
      }
    } else {
      if (isMarked) markedPositions.delete(k);
      else markedPositions.add(k);
    }
  } else {
    if (manualMarked.has(wl)) manualMarked.delete(wl);
    else manualMarked.add(wl);
  }
  if (!currentData) return;
  renderDocument(currentData.segments);
  renderPiiList();
}

addWordBtn.addEventListener('click', () => {
  const word = addWordInput.value.trim();
  if (!word) return;
  addWordInput.value = '';
  manualMarked.add(word.toLowerCase());
  if (!currentData) return;
  renderDocument(currentData.segments);
  renderPiiList();
});
addWordInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') addWordBtn.click();
});

function renderPiiList() {
  const grouped = {};
  for (const p of allPositions) {
    if (markedPositions.has(key(p))) {
      const wl = p.word.toLowerCase();
      if (!grouped[wl]) grouped[wl] = { word: p.word, type: p.type, count: 0 };
      grouped[wl].count++;
    }
  }
  for (const w of manualMarked) {
    if (!grouped[w]) grouped[w] = { word: w, type: 'manual', count: 1 };
  }

  const activeWords = Object.values(grouped);
  wordCount.textContent = activeWords.length;
  exportBtn.disabled = activeWords.length === 0;
  reasonBtn.disabled = !currentReasoning;

  if (activeWords.length === 0) {
    piiList.innerHTML = '';
    piiList.appendChild(emptyState);
    return;
  }
  emptyState.remove();
  let html = '';
  for (const gw of activeWords) {
    const cnt = gw.count > 1 ? ` (${gw.count})` : '';
    html += `<div class="pii-item"><div><span class="word-text">${escapeHtml(gw.word)}${cnt}</span><span class="word-type">${gw.type}</span></div><button class="remove-btn" data-word="${escapeHtml(gw.word)}">&times;</button></div>`;
  }
  piiList.innerHTML = html;
  piiList.querySelectorAll('.remove-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const wl = btn.dataset.word.toLowerCase();
      for (const p of allPositions) {
        if (p.word.toLowerCase() === wl) markedPositions.delete(key(p));
      }
      manualMarked.delete(wl);
      renderDocument(currentData.segments);
      renderPiiList();
    });
  });
}

reasonBtn.addEventListener('click', () => {
  if (!currentReasoning) return;
  reasonContent.textContent = currentReasoning;
  reasonModal.hidden = false;
});

reasonClose.addEventListener('click', () => {
  reasonModal.hidden = true;
});
reasonModal.addEventListener('click', (e) => {
  if (e.target === reasonModal) reasonModal.hidden = true;
});

exportBtn.addEventListener('click', async () => {
  if (!currentData) { showToast('No hay documento cargado'); return; }
  const grouped = {};
  for (const p of allPositions) {
    if (markedPositions.has(key(p))) {
      grouped[p.word.toLowerCase()] = { word: p.word, type: p.type };
    }
  }
  for (const w of manualMarked) {
    grouped[w] = { word: w, type: 'manual' };
  }
  const kw = Object.values(grouped);
  if (kw.length === 0) { showToast('No hay palabras seleccionadas para anonimizar'); return; }

  exportBtn.disabled = true;
  exportBtn.textContent = 'Exportando...';
  try {
    const res = await fetch('/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: currentData.filename,
        keywords: kw,
        format: exportFormat.value,
        replacement: replacementText.value || '[REDACTADO]'
      })
    });
    if (!res.ok) {
      const err = await res.json();
      showToast('Error: ' + (err.error || 'Error al exportar'));
      exportBtn.disabled = false;
      exportBtn.textContent = 'Exportar';
      return;
    }
    const blob = await res.blob();
    const ext = exportFormat.value;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `anonimizado_${currentData.filename.replace(/\.(pdf|docx)$/, '.' + ext)}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Documento exportado exitosamente');
  } catch (err) {
    showToast('Error al exportar');
  } finally {
    exportBtn.disabled = false;
    exportBtn.textContent = 'Exportar';
  }
});

exportBtn.disabled = true;
reasonBtn.disabled = true;

const adminTrigger = document.getElementById('admin-trigger');
const adminModal = document.getElementById('admin-modal');
const adminClose = document.getElementById('admin-close');
const adminLoginForm = document.getElementById('admin-login-form');
const adminPanel = document.getElementById('admin-panel');
const adminUserInput = document.getElementById('admin-user');
const adminPassInput = document.getElementById('admin-pass');
const adminLoginBtn = document.getElementById('admin-login-btn');
const adminLoginError = document.getElementById('admin-login-error');
const adminPromptTextarea = document.getElementById('admin-prompt');
const adminPatternsTextarea = document.getElementById('admin-patterns');
const adminSavePromptBtn = document.getElementById('admin-save-prompt');
const adminSavePatternsBtn = document.getElementById('admin-save-patterns');
const adminLogoutBtn = document.getElementById('admin-logout-btn');
const adminTabs = document.querySelectorAll('.admin-tab');
const adminModelUrlInput = document.getElementById('admin-model-url');
const adminModelNameInput = document.getElementById('admin-model-name');
const adminSaveModelBtn = document.getElementById('admin-save-model');

let adminConfig = null;

adminTrigger.addEventListener('click', () => {
  adminModal.hidden = false;
  adminLoginForm.hidden = false;
  adminPanel.hidden = true;
  adminLoginError.textContent = '';
  adminUserInput.value = '';
  adminPassInput.value = '';
});

adminClose.addEventListener('click', () => {
  adminModal.hidden = true;
});
adminModal.addEventListener('click', (e) => {
  if (e.target === adminModal) adminModal.hidden = true;
});

adminLoginBtn.addEventListener('click', async () => {
  const user = adminUserInput.value.trim();
  const password = adminPassInput.value;
  if (!user || !password) {
    adminLoginError.textContent = 'Completá ambos campos';
    return;
  }
  try {
    const res = await fetch('/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user, password })
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      adminLoginForm.hidden = true;
      adminPanel.hidden = false;
      adminLoginError.textContent = '';
      loadAdminConfig();
    } else {
      adminLoginError.textContent = data.error || 'Credenciales inválidas';
    }
  } catch (err) {
    adminLoginError.textContent = 'Error de conexión';
  }
});

adminLogoutBtn.addEventListener('click', async () => {
  await fetch('/admin/logout', { method: 'POST' });
  adminLoginForm.hidden = false;
  adminPanel.hidden = true;
  adminUserInput.value = '';
  adminPassInput.value = '';
});

async function loadAdminConfig() {
  try {
    const res = await fetch('/admin/config');
    const data = await res.json();
    adminConfig = data;
    adminPromptTextarea.value = data.prompt || '';
    adminPatternsTextarea.value = JSON.stringify(data.patterns, null, 2);
    adminModelUrlInput.value = data.model_url || '';
    adminModelNameInput.value = data.model_name || '';
  } catch (err) {
    showToast('Error cargando configuración');
  }
}

adminTabs.forEach(tab => {
  tab.addEventListener('click', () => {
    adminTabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const target = tab.dataset.tab;
    document.getElementById('admin-tab-prompt').hidden = target !== 'prompt';
    document.getElementById('admin-tab-patterns').hidden = target !== 'patterns';
    document.getElementById('admin-tab-model').hidden = target !== 'model';
  });
});

adminSavePromptBtn.addEventListener('click', async () => {
  const prompt = adminPromptTextarea.value.trim();
  if (!prompt) {
    showToast('El prompt no puede estar vacío');
    return;
  }
  try {
    const res = await fetch('/admin/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, patterns: adminConfig.patterns })
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      showToast('Prompt guardado correctamente');
      adminConfig.prompt = prompt;
    } else {
      showToast('Error: ' + (data.error || 'No se pudo guardar'));
    }
  } catch (err) {
    showToast('Error de conexión');
  }
});

adminSavePatternsBtn.addEventListener('click', async () => {
  let patterns;
  try {
    patterns = JSON.parse(adminPatternsTextarea.value);
    if (!Array.isArray(patterns)) throw new Error('Debe ser un array');
    for (const p of patterns) {
      if (!p.pattern || !p.type) throw new Error('Cada patrón debe tener pattern y type');
    }
  } catch (err) {
    showToast('JSON inválido: ' + err.message);
    return;
  }
  try {
    const res = await fetch('/admin/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patterns, prompt: adminConfig.prompt, model_url: adminConfig.model_url, model_name: adminConfig.model_name })
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      showToast('Patrones guardados correctamente');
      adminConfig.patterns = patterns;
    } else {
      showToast('Error: ' + (data.error || 'No se pudo guardar'));
    }
  } catch (err) {
    showToast('Error de conexión');
  }
});

adminSaveModelBtn.addEventListener('click', async () => {
  const modelUrl = adminModelUrlInput.value.trim();
  const modelName = adminModelNameInput.value.trim();
  if (!modelUrl || !modelName) {
    showToast('Completá ambos campos');
    return;
  }
  try {
    const res = await fetch('/admin/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patterns: adminConfig.patterns, prompt: adminConfig.prompt, model_url: modelUrl, model_name: modelName })
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      showToast('Modelo guardado correctamente');
      adminConfig.model_url = modelUrl;
      adminConfig.model_name = modelName;
    } else {
      showToast('Error: ' + (data.error || 'No se pudo guardar'));
    }
  } catch (err) {
    showToast('Error de conexión');
  }
});
