'use strict';

const RSRC_EXTENSIONS = Object.freeze({
  LVCC: '.ctl',
  LVDL: '.dlog',
  CLIB: '.lvclass',
  LVPJ: '.lvproj',
  LIBR: '.lvlib',
  LIBP: '.lvlibp',
  LVAR: '.llb',
  LMNU: '.mnu',
  sVCC: '.ctt',
  sVIN: '.vit',
  LVXC: '.xctl',
  iUWl: '.uir',
  LVSB: '.lsb',
  LVIN: '.vi',
});

const state = {
  currentJob: null,
  xmlLoadedForJob: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

class ApiError extends Error {
  constructor(message, payload = null, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.payload = payload;
    this.status = status;
  }
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  let payload = null;
  if (contentType.includes('application/json')) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }
  if (!response.ok) {
    const error = payload?.error;
    const message = error?.message || (typeof payload === 'string' && payload) || `HTTP ${response.status}`;
    throw new ApiError(message, error, response.status);
  }
  return payload;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let size = bytes / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const digits = size >= 100 ? 0 : size >= 10 ? 1 : 2;
  return `${size.toFixed(digits)} ${units[index]}`;
}

function showToast(message, type = 'info', timeout = 5000) {
  const region = $('#toast-region');
  const toast = document.createElement('div');
  toast.className = `toast${type === 'error' ? ' is-error' : type === 'success' ? ' is-success' : ''}`;
  toast.textContent = message;
  region.appendChild(toast);
  window.setTimeout(() => toast.remove(), timeout);
}

function describeError(error) {
  if (!(error instanceof ApiError)) return error?.message || '不明なエラーです。';
  const details = error.payload?.details || {};
  const parts = [error.message];
  if (Array.isArray(details.candidates) && details.candidates.length) {
    parts.push(`候補: ${details.candidates.join(', ')}`);
  }
  if (details.reason) parts.push(String(details.reason));
  if (details.stderr) {
    const stderr = String(details.stderr).trim();
    if (stderr) parts.push(stderr.slice(-1200));
  }
  return parts.join('\n');
}

function setBusy(form, busy, label = '') {
  form.classList.toggle('is-busy', busy);
  const button = $('button[type="submit"]', form);
  const buttonLabel = $('.button-label', form);
  if (!button.dataset.defaultLabel) button.dataset.defaultLabel = buttonLabel.textContent;
  button.disabled = busy;
  buttonLabel.textContent = busy ? label || '処理中…' : button.dataset.defaultLabel;
}

function activateTab(name) {
  const isVi = name === 'vi';
  $('#tab-vi').classList.toggle('is-active', isVi);
  $('#tab-vi').setAttribute('aria-selected', String(isVi));
  $('#tab-xml').classList.toggle('is-active', !isVi);
  $('#tab-xml').setAttribute('aria-selected', String(!isVi));
  $('#panel-vi').hidden = !isVi;
  $('#panel-xml').hidden = isVi;
}

function setupTabs() {
  $('#tab-vi').addEventListener('click', () => activateTab('vi'));
  $('#tab-xml').addEventListener('click', () => activateTab('xml'));
}

function updateDropzone(dropzone, file) {
  const selected = $('.selected-file', dropzone);
  dropzone.classList.toggle('has-file', Boolean(file));
  selected.textContent = file ? `${file.name} · ${formatBytes(file.size)}` : '';
}

function setupDropzones() {
  $$('.dropzone').forEach((dropzone) => {
    const input = $(`#${dropzone.dataset.input}`);
    input.addEventListener('change', () => updateDropzone(dropzone, input.files?.[0]));
    dropzone.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        input.click();
      }
    });
    ['dragenter', 'dragover'].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dropzone.classList.add('is-dragging');
      });
    });
    ['dragleave', 'drop'].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dropzone.classList.remove('is-dragging');
      });
    });
    dropzone.addEventListener('drop', (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (!file) return;
      try {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
      } catch {
        showToast('このブラウザーではドロップ選択を反映できません。クリックして選択してください。', 'error');
        return;
      }
      updateDropzone(dropzone, file);
    });
  });
}

function setArtifactLink(id, url) {
  const element = $(`#${id}`);
  element.hidden = !url;
  if (url) element.href = url;
  else element.removeAttribute('href');
}

function defaultRebuildName(job) {
  if (job.reconstructed?.name) return job.reconstructed.name;
  const sourceName = job.source?.name || job.dataset_upload?.name || job.main_xml || 'reconstructed.vi';
  const plain = sourceName.replace(/\.zip$/i, '');
  const index = plain.lastIndexOf('.');
  const stem = index > 0 ? plain.slice(0, index) : plain;
  const sourceExtension = job.source?.name?.includes('.')
    ? job.source.name.slice(job.source.name.lastIndexOf('.'))
    : '';
  const rsrcType = job.main_xml_attributes?.Type;
  const inferredExtension = RSRC_EXTENSIONS[rsrcType] || '.vi';
  const extension = sourceExtension || inferredExtension;
  return `${stem}-reconstructed${extension}`.replace(/[^\p{L}\p{N}._()\[\] -]/gu, '_');
}

function renderMetrics(job) {
  $('#metric-xml').textContent = job.main_xml || '—';
  $('#metric-xml-detail').textContent = job.main_xml_size != null
    ? `${formatBytes(job.main_xml_size)} · ${job.main_xml_attributes?.Type || job.main_xml_attributes?.TypeHex || 'RSRC'}`
    : 'メインXML未検出';

  const files = Array.isArray(job.files) ? job.files : [];
  $('#metric-files').textContent = `${files.length}${job.files_truncated ? '+' : ''} files`;
  const total = files.reduce((sum, file) => sum + Number(file.size || 0), 0);
  $('#metric-files-detail').textContent = `${formatBytes(total)}${job.files_truncated ? '（一覧省略あり）' : ''}`;

  const result = $('#metric-result');
  const detail = $('#metric-result-detail');
  if (job.reconstructed) {
    result.textContent = job.reconstructed.stale ? '再構成結果は旧版' : '再構成済み';
    detail.textContent = `${job.reconstructed.name} · ${formatBytes(job.reconstructed.size)}${job.reconstructed.stale ? ' · XML保存後に再実行してください' : ''}`;
    return;
  }
  const verification = job.verification;
  if (verification?.stale) {
    result.textContent = '検証結果は旧版';
    detail.textContent = 'XML保存後の内容は未検証です。再構成してLabVIEWで確認してください。';
  } else if (verification?.status === 'completed') {
    result.textContent = verification.binary_identical ? 'Binary identical' : 'SHA差分あり';
    detail.textContent = verification.binary_identical
      ? '元ファイルと再構成ファイルが完全一致'
      : '形式上の差分があり得ます。LabVIEWで読込確認してください。';
  } else if (verification?.status === 'failed') {
    result.textContent = '検証失敗';
    detail.textContent = verification.message || 'ログを確認してください。';
  } else if (verification?.requested) {
    result.textContent = '検証中';
    detail.textContent = 'ラウンドトリップを実行しています。';
  } else {
    result.textContent = job.status === 'completed' ? '処理完了' : job.status || '—';
    detail.textContent = '必要に応じてXMLを編集し再構成できます。';
  }
}

function renderFileList(job) {
  const container = $('#file-list');
  container.replaceChildren();
  const files = Array.isArray(job.files) ? job.files : [];
  if (!files.length) {
    const empty = document.createElement('div');
    empty.className = 'file-more';
    empty.textContent = 'ファイル一覧はありません。';
    container.appendChild(empty);
    return;
  }
  files.slice(0, 250).forEach((file) => {
    const row = document.createElement('div');
    row.className = 'file-item';
    const name = document.createElement('span');
    name.textContent = file.path;
    name.title = file.path;
    const size = document.createElement('small');
    size.textContent = formatBytes(file.size);
    row.append(name, size);
    container.appendChild(row);
  });
  if (files.length > 250 || job.files_truncated) {
    const more = document.createElement('div');
    more.className = 'file-more';
    more.textContent = `ほか ${Math.max(0, files.length - 250)} 件${job.files_truncated ? '以上' : ''}`;
    container.appendChild(more);
  }
}

function renderLogs(job) {
  const lines = [];
  const logs = job.logs || {};
  Object.entries(logs).forEach(([stage, value]) => {
    if (!value) return;
    lines.push(`===== ${stage.toUpperCase()} =====`);
    if (value.command) lines.push(`$ ${value.command}`);
    if (value.returncode != null) lines.push(`exit=${value.returncode}  duration=${value.duration_ms ?? '?'}ms`);
    if (value.stdout?.trim()) lines.push('\n[stdout]\n' + value.stdout.trim());
    if (value.stderr?.trim()) lines.push('\n[stderr]\n' + value.stderr.trim());
    lines.push('');
  });
  if (job.error) {
    lines.push('===== JOB ERROR =====');
    lines.push(JSON.stringify(job.error, null, 2));
  }
  $('#job-log').textContent = lines.length ? lines.join('\n') : 'ログはまだありません。';
}
