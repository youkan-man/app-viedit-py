'use strict';

let mainXmlDirty = false;
let activeWorkspaceTab = 'components';

async function componentExplorer() {
  return globalThis.viComponentExplorer || null;
}

function mountComponentExplorer() {
  const mount = $('#component-model-mount');
  const card = $('#component-model-card');
  if (mount && card && card.parentElement !== mount) mount.appendChild(card);
}

function activateWorkspaceTab(name, { focus = false } = {}) {
  const tabs = $$('.workspace-tab');
  const valid = tabs.some((tab) => tab.dataset.workspaceTab === name);
  const targetName = valid ? name : 'components';
  activeWorkspaceTab = targetName;

  tabs.forEach((tab) => {
    const selected = tab.dataset.workspaceTab === targetName;
    tab.classList.toggle('is-active', selected);
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  });

  $$('.workspace-panel').forEach((panel) => {
    const selected = panel.dataset.workspacePanel === targetName;
    panel.hidden = !selected;
    panel.classList.toggle('is-active', selected);
  });
}

function setupWorkspaceTabs() {
  const tabs = $$('.workspace-tab');
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activateWorkspaceTab(tab.dataset.workspaceTab));
    tab.addEventListener('keydown', (event) => {
      let nextIndex = null;
      if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') nextIndex = 0;
      if (event.key === 'End') nextIndex = tabs.length - 1;
      if (nextIndex == null) return;
      event.preventDefault();
      activateWorkspaceTab(tabs[nextIndex].dataset.workspaceTab, { focus: true });
    });
  });
}

function openConverter() {
  const converter = $('#converter-card');
  converter.open = true;
  converter.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeWorkspaceMenus(except = null) {
  $$('.workspace-menu[open]').forEach((menu) => {
    if (menu !== except) menu.open = false;
  });
}

async function loadEditor(job) {
  const editor = $('#xml-editor');
  const stateBadge = $('#editor-state');
  const note = $('#editor-note');
  const saveButton = $('#save-xml');

  if (!job.main_xml || !job.xml_editable) {
    editor.value = '';
    editor.disabled = true;
    editor.placeholder = job.main_xml
      ? 'XMLが画面編集サイズの上限を超えています。メインXMLをダウンロードして編集し、ZIPまたはXMLとして再アップロードしてください。'
      : 'メインXMLがありません。';
    stateBadge.textContent = job.main_xml ? 'サイズ上限' : 'XMLなし';
    stateBadge.className = 'state-badge';
    note.textContent = job.main_xml
      ? '大きなXMLはブラウザーの停止を避けるため、画面編集を無効にしています。'
      : 'このジョブには編集可能なメインXMLがありません。';
    saveButton.disabled = true;
    state.xmlLoadedForJob = null;
    mainXmlDirty = false;
    return;
  }

  editor.disabled = true;
  editor.placeholder = 'XMLを読み込んでいます…';
  stateBadge.textContent = '読込中';
  stateBadge.className = 'state-badge';
  saveButton.disabled = true;
  try {
    const response = await fetch(job.xml_url, { headers: { Accept: 'application/xml' } });
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const payload = await response.json();
        message = payload?.error?.message || message;
      } catch {
        // Keep HTTP status fallback.
      }
      throw new Error(message);
    }
    editor.value = await response.text();
    editor.disabled = false;
    editor.placeholder = '';
    stateBadge.textContent = '編集可能';
    stateBadge.className = 'state-badge is-ready';
    note.textContent = 'メインXMLを直接編集できます。保存後に再構成してください。';
    saveButton.disabled = false;
    state.xmlLoadedForJob = job.job_id;
    mainXmlDirty = false;
  } catch (error) {
    editor.value = '';
    editor.disabled = true;
    editor.placeholder = 'XMLを読み込めませんでした。';
    stateBadge.textContent = '読込失敗';
    stateBadge.className = 'state-badge is-dirty';
    note.textContent = error.message;
    state.xmlLoadedForJob = null;
    mainXmlDirty = false;
    showToast(`XML読込失敗: ${error.message}`, 'error');
  }
}

globalThis.refreshMainXmlEditor = loadEditor;

async function renderJob(job, { scroll = true } = {}) {
  state.currentJob = job;
  document.body.classList.add('has-active-job');

  const workspace = $('#workspace');
  const converter = $('#converter-card');
  workspace.hidden = false;
  converter.open = false;
  $('#workspace-title').textContent = job.kind === 'vi_to_xml' ? 'VI → XML 変換結果' : 'XML → VI 再構成結果';
  $('#copy-job').textContent = `job: ${job.job_id}`;

  setArtifactLink('download-dataset', job.urls?.dataset);
  setArtifactLink('download-main-xml', job.urls?.main_xml);
  setArtifactLink('download-roundtrip', job.urls?.roundtrip);
  setArtifactLink('download-reconstructed', job.urls?.reconstructed);

  renderMetrics(job);
  renderFileList(job);
  renderLogs(job);
  $('#rebuild-name').value = defaultRebuildName(job);
  $('#rebuild-job').disabled = !job.main_xml;
  await loadEditor(job);
  globalThis.viXmlQuantizer?.setJob(job);
  mountComponentExplorer();
  const explorer = await componentExplorer();
  void explorer?.setJob(job);
  activateWorkspaceTab(activeWorkspaceTab);
  closeWorkspaceMenus();

  if (scroll) workspace.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

globalThis.renderJob = renderJob;
globalThis.activateWorkspaceTab = activateWorkspaceTab;

async function handleViSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const input = $('#vi-file');
  if (!input.files?.[0]) {
    showToast('VI / RSRCファイルを選択してください。', 'error');
    return;
  }
  const data = new FormData(form);
  data.set('verify_roundtrip', form.elements.verify_roundtrip.checked ? 'true' : 'false');
  data.set('raw_connectors', form.elements.raw_connectors.checked ? 'true' : 'false');
  setBusy(form, true, 'アップロード・展開中…');
  try {
    const job = await apiRequest('/api/convert/vi-to-xml', { method: 'POST', body: data });
    activeWorkspaceTab = 'components';
    await renderJob(job);
    showToast('XMLデータセットへの変換が完了しました。', 'success');
  } catch (error) {
    showToast(describeError(error), 'error', 10000);
  } finally {
    setBusy(form, false);
  }
}

async function handleXmlSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const input = $('#xml-file');
  if (!input.files?.[0]) {
    showToast('データセットZIPまたはXMLを選択してください。', 'error');
    return;
  }
  setBusy(form, true, 'アップロード・再構成中…');
  try {
    const job = await apiRequest('/api/convert/xml-to-vi', {
      method: 'POST',
      body: new FormData(form),
    });
    activeWorkspaceTab = 'components';
    await renderJob(job);
    showToast('VI / RSRCの再構成が完了しました。', 'success');
  } catch (error) {
    showToast(describeError(error), 'error', 10000);
  } finally {
    setBusy(form, false);
  }
}

async function saveXml() {
  const job = state.currentJob;
  const editor = $('#xml-editor');
  if (!job || editor.disabled) return false;
  const button = $('#save-xml');
  button.disabled = true;
  button.textContent = '保存中…';
  try {
    const updated = await apiRequest(job.xml_url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/xml; charset=utf-8' },
      body: editor.value,
    });
    state.currentJob = updated;
    setArtifactLink('download-dataset', updated.urls?.dataset);
    setArtifactLink('download-main-xml', updated.urls?.main_xml);
    setArtifactLink('download-roundtrip', updated.urls?.roundtrip);
    setArtifactLink('download-reconstructed', updated.urls?.reconstructed);
    renderMetrics(updated);
    renderFileList(updated);
    renderLogs(updated);
    $('#editor-state').textContent = '保存済み';
    $('#editor-state').className = 'state-badge is-ready';
    mainXmlDirty = false;
    globalThis.viXmlQuantizer?.onSaved(updated);
    const explorer = await componentExplorer();
    await explorer?.onDatasetChanged(updated);
    showToast('メインXMLを保存しました。', 'success');
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
  const button = $('#rebuild-job');
  button.disabled = true;
  button.textContent = '再構成中…';
  try {
    let activeJob = job;
    if (mainXmlDirty) {
      const saved = await saveXml();
      if (!saved) return;
      activeJob = state.currentJob;
    }
    const updated = await apiRequest(activeJob.rebuild_url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        output_name: $('#rebuild-name').value.trim() || null,
        text_encoding: activeJob.text_encoding || 'shift_jis',
        verbosity: 1,
      }),
    });
    await renderJob(updated, { scroll: false });
    showToast('現在のXMLデータセットから再構成しました。', 'success');
  } catch (error) {
    showToast(describeError(error), 'error', 10000);
  } finally {
    button.disabled = false;
    button.textContent = 'このXMLから再構成';
  }
}

async function deleteCurrentJob() {
  const job = state.currentJob;
  if (!job?.job_id) return;
  if (!window.confirm('このジョブのアップロード、XML、再構成結果をすべて削除します。')) return;
  try {
    await apiRequest(job.delete_url, { method: 'DELETE' });
    state.currentJob = null;
    state.xmlLoadedForJob = null;
    globalThis.viXmlQuantizer?.clearJob();
    const explorer = await componentExplorer();
    explorer?.clearJob();
    $('#workspace').hidden = true;
    $('#converter-card').open = true;
    document.body.classList.remove('has-active-job');
    activeWorkspaceTab = 'components';
    closeWorkspaceMenus();
    showToast('ジョブを削除しました。', 'success');
  } catch (error) {
    showToast(describeError(error), 'error');
  }
}

function setupWorkspaceActions() {
  $('#save-xml').addEventListener('click', saveXml);
  $('#rebuild-job').addEventListener('click', rebuildCurrentJob);
  $('#delete-job').addEventListener('click', deleteCurrentJob);
  $('#new-job').addEventListener('click', () => {
    closeWorkspaceMenus();
    openConverter();
  });
  $('#copy-job').addEventListener('click', async () => {
    const jobId = state.currentJob?.job_id;
    if (!jobId) return;
    try {
      await navigator.clipboard.writeText(jobId);
      showToast('ジョブIDをコピーしました。', 'success');
    } catch {
      showToast('クリップボードへコピーできませんでした。', 'error');
    }
  });
  $('#xml-editor').addEventListener('input', async () => {
    if ($('#xml-editor').disabled) return;
    $('#editor-state').textContent = '未保存';
    $('#editor-state').className = 'state-badge is-dirty';
    mainXmlDirty = true;
    const explorer = await componentExplorer();
    explorer?.markExternalDirty();
  });

  $$('.workspace-menu').forEach((menu) => {
    menu.addEventListener('toggle', () => {
      if (menu.open) closeWorkspaceMenus(menu);
    });
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.workspace-menu')) closeWorkspaceMenus();
  });
}

function addEncodingOptions(encodings) {
  if (!Array.isArray(encodings)) return;
  $$('.encoding-select').forEach((select) => {
    const existing = new Set([...select.options].map((option) => option.value));
    encodings.forEach((encoding) => {
      if (existing.has(encoding)) return;
      const option = document.createElement('option');
      option.value = encoding;
      option.textContent = encoding;
      select.appendChild(option);
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
      text.textContent = 'エンジン稼働';
      pill.title = health.pylabview.version || 'readRSRC available';
    } else {
      pill.classList.add('is-error');
      text.textContent = 'エンジン未検出';
      pill.title = health.pylabview?.error || 'readRSRC unavailable';
    }
  } catch (error) {
    pill.classList.remove('is-checking');
    pill.classList.add('is-error');
    text.textContent = 'API接続失敗';
    pill.title = error.message;
  }
}

function bootstrap() {
  mountComponentExplorer();
  setupTabs();
  setupDropzones();
  setupWorkspaceTabs();
  setupWorkspaceActions();
  activateWorkspaceTab(activeWorkspaceTab);
  $('#vi-form').addEventListener('submit', handleViSubmit);
  $('#xml-form').addEventListener('submit', handleXmlSubmit);
  checkHealth();
}

document.addEventListener('DOMContentLoaded', bootstrap);
