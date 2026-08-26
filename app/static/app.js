'use strict';

const state = {
  job: null,
  xmlLoaded: false,
  dirty: false,
};

const elements = {
  runtimePill: document.querySelector('#runtime-pill'),
  runtimeText: document.querySelector('#runtime-text'),
  extractForm: document.querySelector('#extract-form'),
  importForm: document.querySelector('#import-form'),
  resultSection: document.querySelector('#result-section'),
  jobStatus: document.querySelector('#job-status'),
  jobId: document.querySelector('#job-id'),
  verificationCard: document.querySelector('#verification-card'),
  verificationIcon: document.querySelector('#verification-icon'),
  verificationTitle: document.querySelector('#verification-title'),
  verificationCopy: document.querySelector('#verification-copy'),
  downloadBundle: document.querySelector('#download-bundle'),
  downloadXml: document.querySelector('#download-xml'),
  editorCard: document.querySelector('#editor-card'),
  xmlEditor: document.querySelector('#xml-editor'),
  dirtyIndicator: document.querySelector('#dirty-indicator'),
  saveXml: document.querySelector('#save-xml'),
  rebuildButton: document.querySelector('#rebuild-button'),
  rebuildFilename: document.querySelector('#rebuild-filename'),
  outputList: document.querySelector('#output-list'),
  datasetList: document.querySelector('#dataset-list'),
  datasetCount: document.querySelector('#dataset-count'),
  logLinks: document.querySelector('#log-links'),
  toastRegion: document.querySelector('#toast-region'),
};

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB'];
  let amount = value;
  let index = -1;
  do {
    amount /= 1024;
    index += 1;
  } while (amount >= 1024 && index < units.length - 1);
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[index]}`;
}

function showToast(message, type = '') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`.trim();
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 5200);
}

async function readError(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
    return JSON.stringify(body.detail || body);
  } catch (_) {
    return `${response.status} ${response.statusText}`;
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

function setButtonLoading(button, loading) {
  button.disabled = loading;
  button.classList.toggle('is-loading', loading);
}

function updateFileField(input) {
  const field = input.closest('.file-field');
  const strong = field.querySelector('.drop-copy strong');
  const span = field.querySelector('.drop-copy span');
  if (!input.files || input.files.length === 0) {
    field.classList.remove('has-file');
    return;
  }
  field.classList.add('has-file');
  if (input.files.length === 1) {
    strong.textContent = input.files[0].name;
    span.textContent = formatBytes(input.files[0].size);
  } else {
    strong.textContent = `${input.files.length} ファイルを選択`;
    span.textContent = Array.from(input.files).slice(0, 3).map(file => file.name).join(' / ');
  }
}

function setupFileFields() {
  document.querySelectorAll('.file-field input[type="file"]').forEach(input => {
    input.addEventListener('change', () => updateFileField(input));
    const field = input.closest('.file-field');
    ['dragenter', 'dragover'].forEach(name => field.addEventListener(name, () => field.classList.add('is-dragging')));
    ['dragleave', 'drop'].forEach(name => field.addEventListener(name, () => field.classList.remove('is-dragging')));
  });
}

function setupTabs() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(item => {
        const active = item === tab;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-selected', String(active));
      });
      document.querySelectorAll('.tab-panel').forEach(panel => {
        const active = panel.id === tab.dataset.tab;
        panel.classList.toggle('is-active', active);
        panel.hidden = !active;
      });
    });
  });
}

function fileRow({ name, size, type, href }) {
  const row = document.createElement(href ? 'a' : 'div');
  row.className = 'file-row';
  if (href) row.href = href;

  const nameWrap = document.createElement('span');
  nameWrap.className = 'file-name';
  const icon = document.createElement('span');
  icon.className = 'file-icon';
  icon.textContent = (type || 'file').slice(0, 5);
  const label = document.createElement('span');
  label.className = 'file-label';
  label.textContent = name;
  label.title = name;
  nameWrap.append(icon, label);

  const sizeLabel = document.createElement('span');
  sizeLabel.className = 'file-size';
  sizeLabel.textContent = formatBytes(size);
  row.append(nameWrap, sizeLabel);
  return row;
}

function renderVerification(verification) {
  const card = elements.verificationCard;
  card.hidden = true;
  card.classList.remove('warning', 'error');
  if (!verification || !verification.requested) return;

  card.hidden = false;
  if (verification.status === 'identical') {
    elements.verificationIcon.textContent = '✓';
    elements.verificationTitle.textContent = 'バイナリ完全一致';
    elements.verificationCopy.textContent = `SHA-256 ${verification.original_sha256}`;
  } else if (verification.status === 'different') {
    card.classList.add('warning');
    elements.verificationIcon.textContent = '≠';
    elements.verificationTitle.textContent = '再構成できましたが、バイナリは一致しません';
    elements.verificationCopy.textContent = `original ${verification.original_size} B / rebuilt ${verification.rebuilt_size} B`;
  } else {
    card.classList.add('error');
    elements.verificationIcon.textContent = '×';
    elements.verificationTitle.textContent = '自動再構成に失敗';
    elements.verificationCopy.textContent = verification.error || 'ログを確認してください。';
  }
}

function renderOutputs(job) {
  elements.outputList.replaceChildren();
  const outputs = Array.isArray(job.outputs) ? job.outputs : [];
  const verification = job.verification || {};
  if (verification.output_name && !outputs.some(item => item.name === verification.output_name)) {
    outputs.unshift({
      name: verification.output_name,
      size: verification.rebuilt_size,
      sha256: verification.rebuilt_sha256,
    });
  }
  if (outputs.length === 0) {
    elements.outputList.className = 'file-list empty-state';
    elements.outputList.textContent = 'まだ生成されていません。';
    return;
  }
  elements.outputList.className = 'file-list';
  outputs.forEach(output => {
    const row = fileRow({
      name: output.name,
      size: output.size,
      type: output.name.split('.').pop(),
      href: `/api/jobs/${job.id}/outputs/${encodeURIComponent(output.name)}`,
    });
    if (output.sha256) row.title = `SHA-256: ${output.sha256}`;
    elements.outputList.append(row);
  });
}

function renderDataset(job) {
  elements.datasetList.replaceChildren();
  const files = Array.isArray(job.dataset_files) ? job.dataset_files : [];
  elements.datasetCount.textContent = String(files.length);
  files.forEach(file => {
    elements.datasetList.append(fileRow({
      name: file.name,
      size: file.size,
      type: file.type,
      href: `/api/jobs/${job.id}/dataset/${file.name.split('/').map(encodeURIComponent).join('/')}`,
    }));
  });
}

function renderLogs(job) {
  elements.logLinks.replaceChildren();
  const names = new Set();
  ['extract_log', 'last_log'].forEach(key => {
    if (typeof job[key] === 'string') names.add(job[key]);
  });
  if (job.verification && typeof job.verification.log === 'string') names.add(job.verification.log);
  if (job.status === 'failed' && names.size === 0) {
    const note = document.createElement('span');
    note.textContent = job.error || 'ログはありません。';
    elements.logLinks.append(note);
    return;
  }
  names.forEach(name => {
    const link = document.createElement('a');
    link.href = `/api/jobs/${job.id}/logs/${encodeURIComponent(name)}`;
    link.textContent = name;
    elements.logLinks.append(link);
  });
}

async function loadXml(job) {
  state.xmlLoaded = false;
  elements.xmlEditor.disabled = true;
  elements.xmlEditor.value = 'XMLを読み込み中…';
  try {
    const response = await fetch(`/api/jobs/${job.id}/xml`);
    if (!response.ok) throw new Error(await readError(response));
    elements.xmlEditor.value = await response.text();
    elements.xmlEditor.disabled = false;
    state.xmlLoaded = true;
    state.dirty = false;
    elements.dirtyIndicator.hidden = true;
  } catch (error) {
    elements.xmlEditor.value = String(error.message || error);
    elements.xmlEditor.disabled = true;
    state.xmlLoaded = false;
  }
}

async function renderJob(job, { loadEditor = true } = {}) {
  state.job = job;
  localStorage.setItem('viedit-current-job', job.id);
  elements.resultSection.hidden = false;
  elements.jobStatus.textContent = job.status || 'unknown';
  elements.jobStatus.classList.toggle('failed', job.status === 'failed');
  elements.jobId.textContent = job.id;
  elements.jobId.title = job.id;
  elements.downloadBundle.href = `/api/jobs/${job.id}/bundle`;
  elements.downloadXml.href = `/api/jobs/${job.id}/xml/download`;
  elements.rebuildFilename.value = job.default_output_filename || job.rebuilt_output || 'rebuilt.vi';
  renderVerification(job.verification);
  renderOutputs(job);
  renderDataset(job);
  renderLogs(job);

  const hasXml = typeof job.main_xml === 'string';
  elements.editorCard.hidden = !hasXml;
  elements.downloadBundle.hidden = !hasXml;
  elements.downloadXml.hidden = !hasXml;
  if (hasXml && loadEditor) await loadXml(job);
  elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function submitExtract(event) {
  event.preventDefault();
  const button = elements.extractForm.querySelector('button[type="submit"]');
  setButtonLoading(button, true);
  const formData = new FormData(elements.extractForm);
  formData.set('verify_roundtrip', String(elements.extractForm.elements.verify_roundtrip.checked));
  formData.set('raw_connectors', String(elements.extractForm.elements.raw_connectors.checked));
  try {
    const job = await fetchJson('/api/extract', { method: 'POST', body: formData });
    await renderJob(job);
    showToast('VIの抽出が完了しました。', 'success');
  } catch (error) {
    showToast(error.message || String(error), 'error');
  } finally {
    setButtonLoading(button, false);
  }
}

async function submitImport(event) {
  event.preventDefault();
  const button = elements.importForm.querySelector('button[type="submit"]');
  setButtonLoading(button, true);
  try {
    const formData = new FormData(elements.importForm);
    const job = await fetchJson('/api/import', { method: 'POST', body: formData });
    await renderJob(job);
    showToast('VIの再構成が完了しました。', 'success');
  } catch (error) {
    showToast(error.message || String(error), 'error');
  } finally {
    setButtonLoading(button, false);
  }
}

async function saveXml() {
  if (!state.job || !state.xmlLoaded) return;
  elements.saveXml.disabled = true;
  try {
    const job = await fetchJson(`/api/jobs/${state.job.id}/xml`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: elements.xmlEditor.value }),
    });
    state.dirty = false;
    elements.dirtyIndicator.hidden = true;
    await renderJob(job, { loadEditor: false });
    showToast('XMLを保存しました。', 'success');
    return true;
  } catch (error) {
    showToast(error.message || String(error), 'error');
    return false;
  } finally {
    elements.saveXml.disabled = false;
  }
}

async function rebuild() {
  if (!state.job) return;
  setButtonLoading(elements.rebuildButton, true);
  try {
    if (state.dirty) {
      const saved = await saveXml();
      if (!saved) return;
    }
    const job = await fetchJson(`/api/jobs/${state.job.id}/rebuild`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ output_filename: elements.rebuildFilename.value }),
    });
    await renderJob(job, { loadEditor: false });
    showToast('VIを再構成しました。', 'success');
  } catch (error) {
    showToast(error.message || String(error), 'error');
  } finally {
    setButtonLoading(elements.rebuildButton, false);
  }
}

async function loadRuntime() {
  try {
    const runtime = await fetchJson('/api/runtime');
    if (runtime.pylabview && runtime.pylabview.available) {
      elements.runtimePill.classList.add('is-ready');
      elements.runtimeText.textContent = runtime.pylabview.version || 'pylabview ready';
    } else {
      elements.runtimePill.classList.add('is-error');
      elements.runtimeText.textContent = 'pylabview unavailable';
      showToast(runtime.pylabview?.error || 'pylabviewを起動できません。', 'error');
    }
  } catch (error) {
    elements.runtimePill.classList.add('is-error');
    elements.runtimeText.textContent = 'runtime error';
  }
}

async function restoreLastJob() {
  const jobId = localStorage.getItem('viedit-current-job');
  if (!jobId) return;
  try {
    const job = await fetchJson(`/api/jobs/${jobId}`);
    await renderJob(job);
  } catch (_) {
    localStorage.removeItem('viedit-current-job');
  }
}

function initialize() {
  setupTabs();
  setupFileFields();
  elements.extractForm.addEventListener('submit', submitExtract);
  elements.importForm.addEventListener('submit', submitImport);
  elements.saveXml.addEventListener('click', saveXml);
  elements.rebuildButton.addEventListener('click', rebuild);
  elements.xmlEditor.addEventListener('input', () => {
    if (!state.xmlLoaded) return;
    state.dirty = true;
    elements.dirtyIndicator.hidden = false;
  });
  window.addEventListener('beforeunload', event => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = '';
  });
  loadRuntime();
  restoreLastJob();
}

initialize();
