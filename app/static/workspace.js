'use strict';

let mainXmlDirty = false;
let modalBusy = false;
let selectedOpenFile = null;
let lastOpenedFile = null;
let lastOpenOptions = null;
let progressTimer = null;

function componentExplorer() {
  return globalThis.viComponentExplorer || null;
}

function mountComponentExplorer() {
  const mount = $('#component-model-mount');
  const card = $('#component-model-card');
  if (mount && card && card.parentElement !== mount) mount.appendChild(card);
}

function detectFileKind(file) {
  const extension = file?.name?.toLowerCase().match(/\.[^.]+$/)?.[0] || '';
  if (extension === '.xml' || extension === '.zip') return 'dataset';
  if (['.vi', '.vit', '.ctl', '.ctt', '.llb', '.lvlib', '.lvlibp', '.lvclass', '.lvproj', '.mnu', '.uir', '.lsb', '.rsrc'].includes(extension)) return 'vi';
  return 'unknown';
}

function sourceName(job) {
  return job?.source?.name || job?.dataset_upload?.name || job?.main_xml || 'ファイル未読込';
}

function updateJobStatus(job) {
  const badge = $('#job-status-badge');
  if (!badge) return;
  if (job.reconstructed?.stale || job.verification?.stale || job.status === 'xml_modified') {
    badge.textContent = '変更あり';
    badge.className = 'state-badge is-dirty';
  } else if (job.status === 'completed') {
    badge.textContent = '準備完了';
    badge.className = 'state-badge is-ready';
  } else {
    badge.textContent = job.status || '—';
    badge.className = 'state-badge';
  }
}

function setHeaderForJob(job) {
  const hasJob = Boolean(job?.job_id);
  $('#header-document-name').textContent = hasJob ? sourceName(job) : 'ファイル未読込';
  $('#header-reconvert').hidden = !hasJob;
  $('#header-refresh').hidden = !hasJob;
  $('#header-rebuild').hidden = !hasJob;
  $('#header-download-menu').hidden = !hasJob;
  $('#job-context').hidden = !hasJob;
  if (hasJob) {
    $('#context-file-name').textContent = sourceName(job);
    $('#copy-job').textContent = `job: ${job.job_id}`;
    $('#header-reconvert').querySelector('span:last-child').textContent = job.kind === 'vi_to_xml' ? '再変換' : '再読込';
  }
}

async function loadEditor(job) {
  const editor = $('#xml-editor');
  const stateBadge = $('#editor-state');
  const note = $('#editor-note');
  const saveButton = $('#save-xml');
  if (!job.main_xml || !job.xml_editable) {
    editor.value = '';
    editor.disabled = true;
    editor.placeholder = job.main_xml ? 'XMLが画面編集サイズの上限を超えています。' : 'メインXMLがありません。';
    stateBadge.textContent = job.main_xml ? 'サイズ上限' : 'XMLなし';
    stateBadge.className = 'state-badge';
    note.textContent = job.main_xml ? 'メインXMLをダウンロードして外部エディターで編集してください。' : '編集可能なメインXMLがありません。';
    saveButton.disabled = true;
    state.xmlLoadedForJob = null;
    mainXmlDirty = false;
    return;
  }
  editor.disabled = true;
  editor.placeholder = 'XMLを読み込んでいます…';
  stateBadge.textContent = '読込中';
  saveButton.disabled = true;
  try {
    const response = await fetch(job.xml_url, { headers: { Accept: 'application/xml' } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    editor.value = await response.text();
    editor.disabled = false;
    editor.placeholder = '';
    stateBadge.textContent = '編集可能';
    stateBadge.className = 'state-badge is-ready';
    note.textContent = '保存するとモデルと接続を再解析します。';
    saveButton.disabled = false;
    state.xmlLoadedForJob = job.job_id;
    mainXmlDirty = false;
  } catch (error) {
    editor.value = '';
    editor.disabled = true;
    stateBadge.textContent = '読込失敗';
    stateBadge.className = 'state-badge is-dirty';
    note.textContent = error.message;
    state.xmlLoadedForJob = null;
    showToast(`XML読込失敗: ${error.message}`, 'error');
  }
}

globalThis.refreshMainXmlEditor = loadEditor;

async function renderJob(job, { scroll = false } = {}) {
  const previousJobId = state.currentJob?.job_id || null;
  state.currentJob = job;
  setHeaderForJob(job);
  updateJobStatus(job);
  setArtifactLink('download-dataset', job.urls?.dataset);
  setArtifactLink('download-main-xml', job.urls?.main_xml);
  setArtifactLink('download-roundtrip', job.urls?.roundtrip);
  setArtifactLink('download-reconstructed', job.urls?.reconstructed);
  renderMetrics(job);
  renderFileList(job);
  renderLogs(job);
  const outputName = defaultRebuildName(job);
  $('#rebuild-name').value = outputName;
  $('#build-output-name').value = outputName;
  $('#rebuild-job').disabled = !job.main_xml;
  $('#build-run').disabled = !job.main_xml;
  await loadEditor(job);
  globalThis.viXmlQuantizer?.setJob(job);
  mountComponentExplorer();
  void componentExplorer()?.setJob(job);
  await globalThis.viModelGraph?.setJob(job);
  globalThis.viPages?.setJob(job, { openModel: previousJobId !== job.job_id });
  if (scroll) window.scrollTo({ top: 0, behavior: 'smooth' });
}

globalThis.renderJob = renderJob;

function updateOpenSelection(file) {
  selectedOpenFile = file || null;
  const kind = detectFileKind(file);
  $('#open-selected-file').textContent = file ? `${file.name} · ${formatBytes(file.size)}` : 'ファイル未選択';
  $('#open-file-kind').textContent = kind === 'vi' ? 'LabVIEW VI / RSRC' : kind === 'dataset' ? 'XMLデータセット' : file ? '未対応形式' : '—';
  $('#open-vi-options').hidden = kind !== 'vi';
  $('#open-dataset-options').hidden = kind !== 'dataset';
  $('#open-submit').disabled = kind === 'unknown' || !file;
  $('#open-dropzone').classList.toggle('has-file', Boolean(file));
}

function resetProgress() {
  window.clearInterval(progressTimer);
  progressTimer = null;
  $('#open-input-view').hidden = false;
  $('#open-progress-view').hidden = true;
  $('#open-progress-bar').className = 'progress-bar';
  $('#open-progress-bar').style.width = '0%';
  ['upload', 'extract', 'model', 'complete'].forEach((name) => {
    $(`#progress-step-${name}`).className = name === 'upload' ? 'is-active' : '';
  });
}

function setProgressStep(step, stage, detail) {
  const order = ['upload', 'extract', 'model', 'complete'];
  const index = order.indexOf(step);
  order.forEach((name, position) => {
    const element = $(`#progress-step-${name}`);
    element.className = position < index ? 'is-complete' : position === index ? 'is-active' : '';
  });
  $('#open-progress-stage').textContent = stage;
  $('#open-progress-detail').textContent = detail;
}

function beginProcessingProgress(kind) {
  $('#open-progress-bar').className = 'progress-bar is-indeterminate';
  $('#open-progress-bar').style.removeProperty('width');
  const stages = kind === 'vi'
    ? [
        ['extract', 'pylabviewでRSRCを解析しています', 'メインXMLと補助XML/BINを展開しています。'],
        ['model', 'LabVIEWモデルを統合しています', '複数XMLのUID、端子、ワイヤ、参照を接続しています。'],
      ]
    : [
        ['extract', 'データセットを検証しています', 'XML/BINの相対パスとメインXMLを確認しています。'],
        ['model', 'モデルを解析しています', '位置、端子、ワイヤ、XML間参照を統合しています。'],
      ];
  let index = 0;
  setProgressStep(...stages[index]);
  progressTimer = window.setInterval(() => {
    index = Math.min(stages.length - 1, index + 1);
    setProgressStep(...stages[index]);
  }, 3200);
}

function setModalBusy(busy) {
  modalBusy = busy;
  $('#open-dialog-close').disabled = busy;
  $('#open-cancel').disabled = busy;
  $('#open-submit').disabled = busy || !selectedOpenFile || detectFileKind(selectedOpenFile) === 'unknown';
  $('#open-input-view').hidden = busy;
  $('#open-progress-view').hidden = !busy;
}

function openDialog({ reuse = false } = {}) {
  if (modalBusy) return;
  resetProgress();
  if (reuse && lastOpenedFile) updateOpenSelection(lastOpenedFile);
  else if (!reuse) {
    $('#open-file').value = '';
    updateOpenSelection(null);
  }
  const dialog = $('#open-dialog');
  if (!dialog.open) dialog.showModal();
}

function closeDialog() {
  if (modalBusy) return;
  $('#open-dialog').close();
}

function xhrForm(url, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', url);
    request.responseType = 'json';
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100));
    });
    request.upload.addEventListener('load', () => onProgress(null));
    request.addEventListener('load', () => {
      const payload = request.response || (() => { try { return JSON.parse(request.responseText); } catch { return null; } })();
      if (request.status >= 200 && request.status < 300) resolve(payload);
      else reject(new ApiError(payload?.error?.message || `HTTP ${request.status}`, payload?.error || payload, request.status));
    });
    request.addEventListener('error', () => reject(new Error('アップロード中にネットワークエラーが発生しました。')));
    request.send(formData);
  });
}

function currentOpenOptions() {
  return {
    encoding: $('#open-encoding').value,
    verbosity: $('#open-verbosity').value,
    verify: $('#open-verify').checked,
    raw: $('#open-raw').checked,
    mainXml: $('#open-main-xml').value.trim(),
    outputName: $('#open-output-name').value.trim(),
  };
}

async function processFile(file, options) {
  const kind = detectFileKind(file);
  if (kind === 'unknown') throw new Error('対応していないファイル形式です。');
  setModalBusy(true);
  setProgressStep('upload', 'ファイルをアップロードしています', `${file.name} · ${formatBytes(file.size)}`);
  $('#open-progress-bar').style.width = '0%';
  const data = new FormData();
  let endpoint;
  if (kind === 'vi') {
    endpoint = '/api/convert/vi-to-xml';
    data.set('file', file);
    data.set('text_encoding', options.encoding);
    data.set('verbosity', options.verbosity);
    data.set('verify_roundtrip', options.verify ? 'true' : 'false');
    data.set('raw_connectors', options.raw ? 'true' : 'false');
  } else {
    endpoint = '/api/convert/xml-to-vi';
    data.set('dataset', file);
    data.set('main_xml', options.mainXml);
    data.set('output_name', options.outputName);
    data.set('text_encoding', options.encoding);
    data.set('verbosity', options.verbosity);
  }
  try {
    const job = await xhrForm(endpoint, data, (percent) => {
      if (percent == null) beginProcessingProgress(kind);
      else {
        $('#open-progress-bar').className = 'progress-bar';
        $('#open-progress-bar').style.width = `${percent}%`;
        $('#open-progress-detail').textContent = `${formatBytes(file.size)} · ${percent}%`;
      }
    });
    window.clearInterval(progressTimer);
    setProgressStep('complete', '解析が完了しました', 'モデル、位置、接続情報を表示します。');
    $('#open-progress-bar').className = 'progress-bar';
    $('#open-progress-bar').style.width = '100%';
    lastOpenedFile = file;
    lastOpenOptions = { ...options };
    await renderJob(job);
    await new Promise((resolve) => window.setTimeout(resolve, 260));
    modalBusy = false;
    $('#open-dialog').close();
    showToast(kind === 'vi' ? 'VIの解析が完了しました。' : 'XMLデータセットを読み込みました。', 'success');
  } finally {
    window.clearInterval(progressTimer);
    progressTimer = null;
    setModalBusy(false);
    resetProgress();
  }
}

async function handleOpenSubmit(event) {
  event.preventDefault();
  if (!selectedOpenFile || modalBusy) return;
  try {
    await processFile(selectedOpenFile, currentOpenOptions());
  } catch (error) {
    showToast(describeError(error), 'error', 10000);
  }
}

async function reconvertCurrent() {
  if (lastOpenedFile && lastOpenOptions) {
    openDialog({ reuse: true });
    try {
      await processFile(lastOpenedFile, lastOpenOptions);
    } catch (error) {
      showToast(describeError(error), 'error', 10000);
    }
    return;
  }
  openDialog();
  showToast('ブラウザーの制約により、元ファイルをもう一度選択してください。', 'info', 7000);
}

async function refreshModels() {
  const button = $('#header-refresh');
  button.disabled = true;
  try {
    await globalThis.viModelGraph?.refresh();
    await componentExplorer()?.refresh?.();
    showToast('モデルとプロパティを再解析しました。', 'success');
  } catch (error) {
    showToast(describeError(error), 'error');
  } finally {
    button.disabled = false;
  }
}

async function notifyDatasetChanged(updated) {
  globalThis.viXmlQuantizer?.onSaved(updated);
  await componentExplorer()?.onDatasetChanged(updated);
  await globalThis.viModelGraph?.onDatasetChanged(updated);
}

async function saveXml() {
  const job = state.currentJob;
  const editor = $('#xml-editor');
  if (!job || editor.disabled) return false;
  const button = $('#save-xml');
  button.disabled = true;
  button.textContent = '保存中…';
  try {
    const updated = await apiRequest(job.xml_url, { method: 'PUT', headers: { 'Content-Type': 'application/xml; charset=utf-8' }, body: editor.value });
    state.currentJob = updated;
    setArtifactLink('download-dataset', updated.urls?.dataset);
    setArtifactLink('download-main-xml', updated.urls?.main_xml);
    setArtifactLink('download-roundtrip', updated.urls?.roundtrip);
    setArtifactLink('download-reconstructed', updated.urls?.reconstructed);
    renderMetrics(updated);
    renderFileList(updated);
    renderLogs(updated);
    updateJobStatus(updated);
    $('#editor-state').textContent = '保存済み';
    $('#editor-state').className = 'state-badge is-ready';
    mainXmlDirty = false;
    await notifyDatasetChanged(updated);
    showToast('XMLを保存し、モデルを再解析しました。', 'success');
    return true;
  } catch (error) {
    showToast(describeError(error), 'error', 10000);
    return false;
  } finally {
    button.disabled = false;
    button.textContent = 'XMLを保存';
  }
}

globalThis.saveMainXml = saveXml;

async function rebuildCurrentJob() {
  const job = state.currentJob;
  if (!job?.job_id) return;
  const buttons = [$('#rebuild-job'), $('#build-run'), $('#header-rebuild')];
  buttons.forEach((button) => { if (button) button.disabled = true; });
  try {
    let activeJob = job;
    if (mainXmlDirty) {
      const saved = await saveXml();
      if (!saved) return;
      activeJob = state.currentJob;
    }
    const outputName = ($('#build-output-name').value || $('#rebuild-name').value).trim() || null;
    const updated = await apiRequest(activeJob.rebuild_url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ output_name: outputName, text_encoding: activeJob.text_encoding || 'shift_jis', verbosity: 1 }),
    });
    await renderJob(updated);
    globalThis.viPages?.open('build');
    showToast('VI / RSRCを再構成しました。', 'success');
  } catch (error) {
    showToast(describeError(error), 'error', 10000);
  } finally {
    buttons.forEach((button) => { if (button) button.disabled = false; });
  }
}

async function deleteCurrentJob() {
  const job = state.currentJob;
  if (!job?.job_id || !window.confirm('このジョブのアップロード、XML、成果物をすべて削除します。')) return;
  try {
    await apiRequest(job.delete_url, { method: 'DELETE' });
    state.currentJob = null;
    state.xmlLoadedForJob = null;
    mainXmlDirty = false;
    setHeaderForJob(null);
    globalThis.viXmlQuantizer?.clearJob();
    globalThis.viModelGraph?.clearJob();
    componentExplorer()?.clearJob();
    globalThis.viPages?.clearJob();
    showToast('ジョブを削除しました。', 'success');
  } catch (error) {
    showToast(describeError(error), 'error');
  }
}

function setupModal() {
  const fileInput = $('#open-file');
  const dropzone = $('#open-dropzone');
  $('#header-open').addEventListener('click', () => openDialog());
  $('#empty-open').addEventListener('click', () => openDialog());
  $('#open-file-button').addEventListener('click', () => fileInput.click());
  $('#open-dialog-close').addEventListener('click', closeDialog);
  $('#open-cancel').addEventListener('click', closeDialog);
  $('#open-form').addEventListener('submit', handleOpenSubmit);
  $('#open-dialog').addEventListener('cancel', (event) => { if (modalBusy) event.preventDefault(); });
  fileInput.addEventListener('change', () => updateOpenSelection(fileInput.files?.[0]));
  dropzone.addEventListener('keydown', (event) => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target === dropzone) { event.preventDefault(); fileInput.click(); }
  });
  ['dragenter', 'dragover'].forEach((type) => dropzone.addEventListener(type, (event) => { event.preventDefault(); dropzone.classList.add('is-dragging'); }));
  ['dragleave', 'drop'].forEach((type) => dropzone.addEventListener(type, (event) => { event.preventDefault(); dropzone.classList.remove('is-dragging'); }));
  dropzone.addEventListener('drop', (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
    } catch {
      // Directly retain the File object even if input.files is read-only.
    }
    updateOpenSelection(file);
  });
}

function setupWorkspaceActions() {
  $('#save-xml').addEventListener('click', saveXml);
  $('#rebuild-job').addEventListener('click', rebuildCurrentJob);
  $('#build-run').addEventListener('click', rebuildCurrentJob);
  $('#header-rebuild').addEventListener('click', rebuildCurrentJob);
  $('#header-reconvert').addEventListener('click', reconvertCurrent);
  $('#header-refresh').addEventListener('click', refreshModels);
  $('#delete-job').addEventListener('click', deleteCurrentJob);
  $('#copy-job').addEventListener('click', async () => {
    const jobId = state.currentJob?.job_id;
    if (!jobId) return;
    try { await navigator.clipboard.writeText(jobId); showToast('ジョブIDをコピーしました。', 'success'); }
    catch { showToast('クリップボードへコピーできませんでした。', 'error'); }
  });
  $('#xml-editor').addEventListener('input', () => {
    if ($('#xml-editor').disabled) return;
    $('#editor-state').textContent = '未保存';
    $('#editor-state').className = 'state-badge is-dirty';
    mainXmlDirty = true;
    componentExplorer()?.markExternalDirty();
  });
  $('#build-output-name').addEventListener('input', () => { $('#rebuild-name').value = $('#build-output-name').value; });
  $('#rebuild-name').addEventListener('input', () => { $('#build-output-name').value = $('#rebuild-name').value; });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.header-menu')) $$('.header-menu[open]').forEach((menu) => { menu.open = false; });
  });
}

function addEncodingOptions(encodings) {
  if (!Array.isArray(encodings)) return;
  $$('.encoding-select').forEach((select) => {
    const existing = new Set([...select.options].map((option) => option.value));
    encodings.forEach((encoding) => {
      if (existing.has(encoding)) return;
      select.add(new Option(encoding, encoding));
      existing.add(encoding);
    });
  });
}

async function checkHealth() {
  const pill = $('#health-pill');
  const text = $('#health-text');
  try {
    const health = await apiRequest('/api/health');
    addEncodingOptions(health.encodings);
    pill.classList.remove('is-checking');
    if (health.pylabview?.available) {
      pill.classList.add('is-ok');
      text.textContent = '稼働';
      pill.title = health.pylabview.version || 'readRSRC available';
    } else {
      pill.classList.add('is-error');
      text.textContent = '未検出';
      pill.title = health.pylabview?.error || 'readRSRC unavailable';
    }
  } catch (error) {
    pill.classList.remove('is-checking');
    pill.classList.add('is-error');
    text.textContent = '接続失敗';
    pill.title = error.message;
  }
}

function bootstrap() {
  mountComponentExplorer();
  setupModal();
  setupWorkspaceActions();
  setHeaderForJob(null);
  resetProgress();
  checkHealth();
}

globalThis.viWorkbench = { openDialog, renderJob, rebuildCurrentJob, refreshModels };
document.addEventListener('DOMContentLoaded', bootstrap);
