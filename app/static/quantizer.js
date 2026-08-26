'use strict';

(() => {
  const quantizer = {
    jobId: null,
    previewId: null,
    sourceContent: null,
    applying: false,
    elements: {},
  };

  const kindLabels = {
    object: 'object',
    connector: 'connector',
    wire: 'wire',
  };

  function cacheElements() {
    quantizer.elements = {
      form: $('#quantize-form'),
      gridSize: $('#quantize-grid-size'),
      rounding: $('#quantize-rounding'),
      objects: $('#quantize-objects'),
      connectors: $('#quantize-connectors'),
      wires: $('#quantize-wires'),
      resize: $('#quantize-resize'),
      preview: $('#quantize-preview'),
      apply: $('#quantize-apply'),
      clear: $('#quantize-clear'),
      state: $('#quantize-state'),
      report: $('#quantize-report'),
      matched: $('#quantize-matched'),
      changed: $('#quantize-changed'),
      values: $('#quantize-values'),
      breakdown: $('#quantize-breakdown'),
      warnings: $('#quantize-warnings'),
      samples: $('#quantize-samples-body'),
      editor: $('#xml-editor'),
    };
  }

  function setState(text, className = '') {
    const element = quantizer.elements.state;
    element.textContent = text;
    element.className = `state-badge${className ? ` ${className}` : ''}`;
  }

  async function discardServerPreview(previewId, jobId) {
    if (!previewId || !jobId) return;
    try {
      await apiRequest(
        `/api/jobs/${encodeURIComponent(jobId)}/quantize/preview/${encodeURIComponent(previewId)}`,
        { method: 'DELETE' },
      );
    } catch {
      // Preview files are temporary and job-scoped. A later preview replaces them,
      // so failure to discard is not fatal to the editor workflow.
    }
  }

  function clearReport({ keepAppliedState = false, discard = true } = {}) {
    const previewId = quantizer.previewId;
    const jobId = quantizer.jobId;
    quantizer.previewId = null;
    quantizer.sourceContent = null;
    quantizer.elements.report.hidden = true;
    quantizer.elements.samples.replaceChildren();
    quantizer.elements.warnings.replaceChildren();
    quantizer.elements.warnings.hidden = true;
    quantizer.elements.apply.disabled = true;
    quantizer.elements.clear.disabled = true;
    if (!keepAppliedState) setState('未解析');
    if (discard) void discardServerPreview(previewId, jobId);
  }

  function setControlsEnabled(enabled) {
    [
      quantizer.elements.gridSize,
      quantizer.elements.rounding,
      quantizer.elements.objects,
      quantizer.elements.connectors,
      quantizer.elements.wires,
      quantizer.elements.resize,
      quantizer.elements.preview,
    ].forEach((element) => {
      element.disabled = !enabled;
    });
    if (!enabled) clearReport();
  }

  function validateOptions() {
    const gridSize = Number(quantizer.elements.gridSize.value);
    if (!Number.isInteger(gridSize) || gridSize < 1 || gridSize > 256) {
      throw new Error('粒度は1〜256の整数で指定してください。');
    }
    const scopes = [
      quantizer.elements.objects.checked,
      quantizer.elements.connectors.checked,
      quantizer.elements.wires.checked,
    ];
    if (!scopes.some(Boolean)) {
      throw new Error('対象を少なくとも1つ選択してください。');
    }
    return {
      grid_size: gridSize,
      rounding: quantizer.elements.rounding.value,
      include_objects: quantizer.elements.objects.checked,
      include_connectors: quantizer.elements.connectors.checked,
      include_wires: quantizer.elements.wires.checked,
      resize_rectangles: quantizer.elements.resize.checked,
    };
  }

  function appendSample(sample) {
    const row = document.createElement('tr');
    const kindCell = document.createElement('td');
    const kind = document.createElement('span');
    kind.className = `quantize-kind ${sample.kind || ''}`.trim();
    kind.textContent = kindLabels[sample.kind] || sample.kind || 'coordinate';
    kindCell.appendChild(kind);

    const pathCell = document.createElement('td');
    const location = [sample.file, sample.path].filter(Boolean).join(' · ');
    pathCell.textContent = location || sample.tag || '—';
    pathCell.title = location;
    const beforeCell = document.createElement('td');
    beforeCell.textContent = sample.before || '—';
    beforeCell.title = sample.before || '';
    const afterCell = document.createElement('td');
    afterCell.textContent = sample.after || '—';
    afterCell.title = sample.after || '';
    row.append(kindCell, pathCell, beforeCell, afterCell);
    quantizer.elements.samples.appendChild(row);
  }

  function renderReport(report) {
    quantizer.elements.matched.textContent = String(report.matched_elements ?? 0);
    quantizer.elements.changed.textContent = String(report.changed_elements ?? 0);
    quantizer.elements.values.textContent = String(report.changed_values ?? 0);
    const byKind = report.changed_by_kind || {};
    quantizer.elements.breakdown.textContent = `${byKind.object || 0} / ${byKind.connector || 0} / ${byKind.wire || 0}`;

    quantizer.elements.samples.replaceChildren();
    const samples = Array.isArray(report.samples) ? report.samples : [];
    if (samples.length) {
      samples.forEach(appendSample);
    } else {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 4;
      cell.className = 'quantize-empty-row';
      cell.textContent = report.staged_files
        ? '座標差分はありませんが、未保存のメインXMLを反映できます。'
        : '現在の粒度では変更される座標がありません。';
      row.appendChild(cell);
      quantizer.elements.samples.appendChild(row);
    }

    const warnings = Array.isArray(report.warnings) ? report.warnings : [];
    quantizer.elements.warnings.replaceChildren();
    warnings.forEach((message) => {
      const paragraph = document.createElement('p');
      paragraph.textContent = message;
      quantizer.elements.warnings.appendChild(paragraph);
    });
    quantizer.elements.warnings.hidden = warnings.length === 0;
    quantizer.elements.report.hidden = false;
    quantizer.elements.apply.disabled = !(report.staged_files > 0);
    quantizer.elements.clear.disabled = false;
    setState(
      report.staged_files > 0 ? `${report.staged_files} file 差分` : '変更なし',
      report.staged_files > 0 ? 'is-dirty' : 'is-ready',
    );
  }

  async function preview(event) {
    event.preventDefault();
    const editor = quantizer.elements.editor;
    if (!quantizer.jobId || editor.disabled || !editor.value.trim()) {
      showToast('編集可能なXMLデータセットを読み込んでください。', 'error');
      return;
    }

    let options;
    try {
      options = validateOptions();
    } catch (error) {
      showToast(error.message, 'error');
      return;
    }

    clearReport();
    quantizer.elements.preview.disabled = true;
    quantizer.elements.preview.textContent = '解析中…';
    setState('解析中');
    try {
      const sourceContent = editor.value;
      const result = await apiRequest(
        `/api/jobs/${encodeURIComponent(quantizer.jobId)}/quantize/preview`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ current_main_xml: sourceContent, ...options }),
        },
      );
      quantizer.sourceContent = sourceContent;
      quantizer.previewId = result.preview_id;
      renderReport(result);
    } catch (error) {
      clearReport({ discard: false });
      showToast(describeError(error), 'error', 10000);
    } finally {
      quantizer.elements.preview.disabled = false;
      quantizer.elements.preview.textContent = '差分を解析';
    }
  }

  async function apply() {
    if (!quantizer.previewId || !quantizer.jobId || quantizer.sourceContent == null) return;
    const editor = quantizer.elements.editor;
    if (editor.value !== quantizer.sourceContent) {
      clearReport();
      showToast('解析後にXMLが変更されています。もう一度差分を解析してください。', 'error');
      return;
    }

    const previewId = quantizer.previewId;
    quantizer.elements.apply.disabled = true;
    quantizer.elements.apply.textContent = '反映中…';
    try {
      const updated = await apiRequest(
        `/api/jobs/${encodeURIComponent(quantizer.jobId)}/quantize/apply`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ preview_id: previewId }),
        },
      );
      quantizer.previewId = null;
      quantizer.sourceContent = null;
      quantizer.applying = true;
      await renderJob(updated, { scroll: false });
      quantizer.applying = false;
      setState('データセットへ反映済み', 'is-ready');
      showToast('座標クオンタイズをXMLデータセットへ保存しました。再構成して結果を確認してください。', 'success');
    } catch (error) {
      showToast(describeError(error), 'error', 10000);
      quantizer.elements.apply.disabled = false;
    } finally {
      quantizer.elements.apply.textContent = 'データセットへ反映';
    }
  }

  function optionsChanged() {
    if (quantizer.previewId) clearReport();
  }

  function setJob(job) {
    const changedJob = quantizer.jobId && quantizer.jobId !== job?.job_id;
    if (changedJob) clearReport();
    quantizer.jobId = job?.job_id || null;
    if (!quantizer.applying) clearReport({ discard: false });
    setControlsEnabled(Boolean(job?.main_xml && job?.xml_editable && !quantizer.elements.editor.disabled));
  }

  function clearJob() {
    clearReport();
    quantizer.jobId = null;
    setControlsEnabled(false);
  }

  function onSaved(job) {
    clearReport();
    quantizer.jobId = job?.job_id || quantizer.jobId;
    setControlsEnabled(Boolean(job?.main_xml && job?.xml_editable && !quantizer.elements.editor.disabled));
  }

  function initialize() {
    cacheElements();
    quantizer.elements.form.addEventListener('submit', preview);
    quantizer.elements.apply.addEventListener('click', apply);
    quantizer.elements.clear.addEventListener('click', () => clearReport());
    [
      quantizer.elements.gridSize,
      quantizer.elements.rounding,
      quantizer.elements.objects,
      quantizer.elements.connectors,
      quantizer.elements.wires,
      quantizer.elements.resize,
    ].forEach((element) => element.addEventListener('change', optionsChanged));
    quantizer.elements.editor.addEventListener('input', () => {
      if (!quantizer.applying && quantizer.previewId) clearReport();
    });
    setControlsEnabled(false);
  }

  globalThis.viXmlQuantizer = { setJob, clearJob, onSaved };
  document.addEventListener('DOMContentLoaded', initialize);
})();
