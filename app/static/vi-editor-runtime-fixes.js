'use strict';

(() => {
  const runtime = {
    initialized: false,
    saving: false,
    rebuilding: false,
    propertyDetail: null,
    propertyChanges: new Map(),
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function semanticState() {
    return editor()?.S;
  }

  function currentJob() {
    if (typeof state !== 'undefined' && state.currentJob) return state.currentJob;
    return semanticState()?.job || null;
  }

  function nearlyEqual(first, second, tolerance = 1.1) {
    if (!first || !second) return false;
    return ['x', 'y', 'width', 'height'].every(
      (key) => Math.abs(Number(first[key]) - Number(second[key])) <= tolerance,
    );
  }

  function absoluteBounds(item) {
    const E = editor();
    return E?.effectiveBounds?.(item) || E?.getBounds?.(item) || null;
  }

  function sourceBounds(item, bounds) {
    const S = semanticState();
    if (!item || !bounds || !S) return bounds;
    if (item.bounds?.source_coordinate_space !== 'parent-relative') {
      return { ...bounds };
    }
    const parentId = item.parent_object_id || item.bounds?.relative_to_object_id;
    const parent = S.objects.get(parentId);
    const parentBounds = absoluteBounds(parent);
    if (!parentBounds) return { ...bounds };
    return {
      ...bounds,
      x: bounds.x - parentBounds.x,
      y: bounds.y - parentBounds.y,
    };
  }

  function saveButtonState() {
    const S = semanticState();
    const button = document.querySelector('#vi-save-layout');
    const revert = document.querySelector('#vi-revert-layout');
    if (!S || !button) return;
    button.disabled = runtime.saving || !S.dirty.size;
    if (revert) revert.disabled = runtime.saving || !S.dirty.size;
    button.textContent = runtime.saving
      ? '保存して再読込中…'
      : S.dirty.size
        ? `位置を保存 (${S.dirty.size})`
        : '位置を保存';
  }

  function restorePending(pending) {
    const E = editor();
    const S = semanticState();
    if (!E || !S) return;
    pending.forEach((entry, id) => {
      if (!S.objects.has(id)) return;
      S.local.set(id, { ...entry.bounds });
      S.dirty.add(id);
    });
    E.renderAll?.(false);
  }

  function clearHistoryAfterSave() {
    const enhancements = globalThis.VISemanticEnhancements;
    if (enhancements?.history) {
      enhancements.history.history.length = 0;
      enhancements.history.future.length = 0;
    }
    const undo = document.querySelector('#vi-undo-layout');
    const redo = document.querySelector('#vi-redo-layout');
    if (undo) undo.disabled = true;
    if (redo) redo.disabled = true;
    const note = document.querySelector('#vi-history-status');
    if (note) note.textContent = '保存済み';
  }

  async function persistLayout(event) {
    event?.preventDefault();
    event?.stopImmediatePropagation();
    const E = editor();
    const S = semanticState();
    if (!E || !S?.job || runtime.saving || !S.dirty.size) return;

    runtime.saving = true;
    S.saving = true;
    saveButtonState();
    const pending = new Map();
    [...S.dirty].forEach((id) => {
      const item = S.objects.get(id);
      const bounds = item ? absoluteBounds(item) : null;
      if (item && bounds) pending.set(id, { item: { ...item }, bounds: { ...bounds } });
    });
    let latestJob = S.job;

    try {
      for (const [id, entry] of pending) {
        const item = S.objects.get(id) || entry.item;
        const detail = await apiRequest(
          `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
        );
        const propertyId = item.bounds?.source_property_id || detail.bounds?.property_id;
        const property = (detail.properties || []).find(
          (candidate) => candidate.id === propertyId,
        );
        if (!propertyId || !property?.editable) {
          throw new Error(`${item.name} の実座標プロパティを更新できません。`);
        }
        const storedBounds = sourceBounds(item, entry.bounds);
        const response = await apiRequest(
          `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              expected_file_sha256: detail.file_sha256,
              updates: [{
                property_id: propertyId,
                value: E.serializeBounds(item, storedBounds),
              }],
            }),
          },
        );
        latestJob = response.job || latestJob;
      }

      // Keep the old revision until renderJob calls viModelGraph.setJob(). That
      // revision difference is what forces a fresh semantic model. Clearing it
      // early was the reason saved positions immediately reverted on screen.
      await globalThis.renderJob(latestJob, { scroll: false });

      const reloaded = semanticState();
      const mismatches = [];
      pending.forEach((entry, id) => {
        const item = reloaded?.objects.get(id);
        const bounds = item ? absoluteBounds(item) : null;
        if (!item || !nearlyEqual(bounds, entry.bounds)) {
          mismatches.push(entry.item.name || id);
        }
      });
      if (mismatches.length) {
        throw new Error(`保存後の再解析座標が一致しません: ${mismatches.join(', ')}`);
      }

      reloaded?.local.clear();
      reloaded?.dirty.clear();
      clearHistoryAfterSave();
      E.renderAll?.(false);
      showToast(`${pending.size}個の配置をXMLと意味モデルへ保存しました。`, 'success');
    } catch (error) {
      restorePending(pending);
      showToast(`配置保存: ${describeError(error)}`, 'error', 10000);
    } finally {
      const latestState = semanticState();
      if (latestState) latestState.saving = false;
      runtime.saving = false;
      saveButtonState();
    }
  }

  function setActionStatus(text, stateClass = '') {
    let status = document.querySelector('#vi-action-status');
    if (!status) {
      status = document.createElement('span');
      status.id = 'vi-action-status';
      status.className = 'state-badge';
      const actions = document.querySelector('.header-actions');
      actions?.insertBefore(status, document.querySelector('#health-pill'));
    }
    status.textContent = text;
    status.className = `state-badge${stateClass ? ` ${stateClass}` : ''}`;
    status.hidden = !text;
  }

  async function rebuildInPlace(event) {
    event?.preventDefault();
    event?.stopImmediatePropagation();
    const job = currentJob();
    if (!job?.job_id || runtime.rebuilding) return;
    runtime.rebuilding = true;
    const activePage = globalThis.viPages?.activePage || 'model';
    const buttons = [
      document.querySelector('#rebuild-job'),
      document.querySelector('#build-run'),
      document.querySelector('#header-rebuild'),
    ].filter(Boolean);
    buttons.forEach((button) => { button.disabled = true; });
    setActionStatus('再構成中');

    try {
      let activeJob = job;
      if (typeof mainXmlDirty !== 'undefined' && mainXmlDirty) {
        const saved = await globalThis.saveMainXml?.();
        if (!saved) return;
        activeJob = currentJob();
      }
      const outputName = (
        document.querySelector('#build-output-name')?.value
        || document.querySelector('#rebuild-name')?.value
        || ''
      ).trim() || null;
      const updated = await apiRequest(activeJob.rebuild_url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_name: outputName,
          text_encoding: activeJob.text_encoding || 'shift_jis',
          verbosity: 1,
        }),
      });
      await globalThis.renderJob(updated, { scroll: false });
      if (globalThis.viPages?.activePage !== activePage) {
        globalThis.viPages?.open(activePage, { replace: true });
      }
      setActionStatus('再構成済み', 'is-ready');
      showToast('現在の画面を維持したままVI / RSRCを再構成しました。', 'success');
    } catch (error) {
      setActionStatus('再構成失敗', 'is-dirty');
      showToast(`再構成: ${describeError(error)}`, 'error', 10000);
    } finally {
      runtime.rebuilding = false;
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  function propertyCategory(prop) {
    const name = String(prop.field_name || prop.name || '').toLowerCase();
    if (prop.value_type === 'rect' || prop.value_type === 'point' || name.includes('bounds')) return '配置';
    if (name.includes('color') || name.includes('font') || name.includes('visible')) return '外観';
    if (name.includes('name') || name.includes('label') || name.includes('text')) return '表示';
    if (name.includes('value') || name.includes('min') || name.includes('max') || name.includes('step')) return '値';
    return 'その他';
  }

  function isRawProperty(prop) {
    return Boolean(
      prop.structural
      || prop.reference_like
      || prop.binary
      || prop.value_type === 'reference'
      || prop.value_type === 'path'
    );
  }

  function ensurePropertyPanel() {
    let panel = document.querySelector('#vi-inline-properties');
    if (panel) return panel;
    panel = document.createElement('section');
    panel.id = 'vi-inline-properties';
    panel.className = 'vi-inline-properties';
    panel.hidden = true;
    panel.innerHTML = `
      <header>
        <div><strong>プロパティ詳細</strong><small id="vi-inline-properties-state">未読込</small></div>
        <button id="vi-inline-properties-close" type="button" aria-label="プロパティ詳細を閉じる">×</button>
      </header>
      <div id="vi-inline-properties-meaningful" class="vi-inline-properties-list"></div>
      <details id="vi-inline-properties-raw" class="vi-inline-raw">
        <summary>RAWデータ</summary>
        <div id="vi-inline-properties-raw-content"></div>
      </details>
      <footer>
        <span id="vi-inline-properties-change-count">変更なし</span>
        <button id="vi-inline-properties-save" type="button" disabled>変更を保存</button>
      </footer>`;
    document.querySelector('#model-inspector')?.append(panel);
    panel.querySelector('#vi-inline-properties-close')?.addEventListener('click', () => {
      panel.hidden = true;
    });
    panel.querySelector('#vi-inline-properties-save')?.addEventListener('click', () => {
      void saveInlineProperties();
    });
    return panel;
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }

  function propertyControl(prop) {
    if (!prop.editable) {
      return textElement('div', 'vi-inline-property-value', prop.value ?? prop.preview ?? '—');
    }
    const value = String(prop.value ?? prop.preview ?? '');
    const input = value.length > 100 || value.includes('\n')
      ? document.createElement('textarea')
      : document.createElement('input');
    if (input instanceof HTMLInputElement) input.type = 'text';
    input.value = value;
    input.dataset.propertyId = prop.id;
    input.addEventListener('input', () => {
      const original = String(prop.value ?? prop.preview ?? '');
      if (input.value === original) runtime.propertyChanges.delete(prop.id);
      else runtime.propertyChanges.set(prop.id, input.value);
      updateInlineSaveState();
    });
    return input;
  }

  function propertyRow(prop) {
    const row = document.createElement('label');
    row.className = 'vi-inline-property-row';
    const copy = document.createElement('span');
    copy.append(
      textElement('strong', '', prop.name || prop.field_name || 'property'),
      textElement('small', '', `${propertyCategory(prop)} · ${prop.value_type}${prop.editable ? '' : ' · 読み取り専用'}`),
    );
    row.append(copy, propertyControl(prop));
    return row;
  }

  function updateInlineSaveState() {
    const count = runtime.propertyChanges.size;
    const note = document.querySelector('#vi-inline-properties-change-count');
    const button = document.querySelector('#vi-inline-properties-save');
    if (note) note.textContent = count ? `${count}件変更` : '変更なし';
    if (button) button.disabled = !count;
  }

  function renderInlineProperties(detail) {
    runtime.propertyDetail = detail;
    runtime.propertyChanges.clear();
    const meaningful = document.querySelector('#vi-inline-properties-meaningful');
    const raw = document.querySelector('#vi-inline-properties-raw-content');
    const stateElement = document.querySelector('#vi-inline-properties-state');
    if (!meaningful || !raw) return;
    meaningful.replaceChildren();
    raw.replaceChildren();

    const properties = detail.properties || [];
    const semanticProperties = properties.filter((prop) => !isRawProperty(prop));
    const rawProperties = properties.filter(isRawProperty);
    semanticProperties.slice(0, 80).forEach((prop) => meaningful.append(propertyRow(prop)));
    if (!semanticProperties.length) {
      meaningful.append(textElement('div', 'vi-inline-properties-empty', '編集対象となる意味プロパティはありません。'));
    }

    const identity = document.createElement('dl');
    identity.className = 'vi-inline-raw-identity';
    [
      ['class', detail.class_name || '—'],
      ['UID', detail.uid || '—'],
      ['file', detail.file || '—'],
      ['XML path', detail.path || '—'],
    ].forEach(([name, value]) => {
      const item = document.createElement('div');
      item.append(textElement('dt', '', name), textElement('dd', '', value));
      identity.append(item);
    });
    raw.append(identity);
    rawProperties.slice(0, 160).forEach((prop) => {
      const item = document.createElement('div');
      item.className = 'vi-inline-raw-property';
      item.append(
        textElement('strong', '', prop.name || prop.field_name || 'property'),
        textElement('small', '', `${prop.path || ''} · ${prop.value_type}`),
        textElement('code', '', String(prop.value ?? prop.preview ?? '')),
      );
      raw.append(item);
    });
    if (stateElement) {
      stateElement.textContent = `${semanticProperties.length}項目 · RAW ${rawProperties.length}項目`;
    }
    updateInlineSaveState();
  }

  async function openInlineProperties(event) {
    event?.preventDefault();
    event?.stopImmediatePropagation();
    const S = semanticState();
    const item = S?.objects.get(S.selected);
    if (!S?.job || !item) return;
    const panel = ensurePropertyPanel();
    panel.hidden = false;
    const stateElement = panel.querySelector('#vi-inline-properties-state');
    if (stateElement) stateElement.textContent = '読込中…';
    try {
      const detail = await apiRequest(
        `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
      );
      if (semanticState()?.selected !== item.id) return;
      renderInlineProperties(detail);
    } catch (error) {
      if (stateElement) stateElement.textContent = '読込失敗';
      showToast(`プロパティ詳細: ${describeError(error)}`, 'error', 10000);
    }
  }

  async function saveInlineProperties() {
    const detail = runtime.propertyDetail;
    const job = currentJob();
    if (!detail || !job || !runtime.propertyChanges.size) return;
    const button = document.querySelector('#vi-inline-properties-save');
    if (button) button.disabled = true;
    try {
      const payload = await apiRequest(
        `/api/jobs/${encodeURIComponent(job.job_id)}/components/${encodeURIComponent(detail.id)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_file_sha256: detail.file_sha256,
            updates: [...runtime.propertyChanges].map(([property_id, value]) => ({
              property_id,
              value,
            })),
          }),
        },
      );
      runtime.propertyChanges.clear();
      await globalThis.renderJob(payload.job, { scroll: false });
      const selected = semanticState()?.objects.get(detail.id);
      if (selected) semanticState().selected = selected.id;
      showToast(`${payload.updated_properties.length}件のプロパティを保存しました。`, 'success');
      document.querySelector('#vi-inline-properties').hidden = true;
    } catch (error) {
      showToast(`プロパティ保存: ${describeError(error)}`, 'error', 10000);
      updateInlineSaveState();
    }
  }

  function renameViewsAndRawData() {
    const navigation = document.querySelector('.azure-navigation');
    navigation?.setAttribute('aria-label', 'ビュー切り替え');
    const title = navigation?.querySelector('.navigation-section-title');
    if (title) title.textContent = 'ビュー';
    const labels = {
      model: ['VI編集', '部品・ノード・配線'],
      properties: ['プロパティ一覧', 'VIオブジェクト情報'],
      xml: ['RAWデータ', 'XMLと抽出ファイル'],
      align: ['整列ツール', '一括座標処理'],
      build: ['成果物', '再構成ログと出力'],
    };
    Object.entries(labels).forEach(([page, values]) => {
      const button = document.querySelector(`[data-app-page="${page}"]`);
      if (!button) return;
      const strong = button.querySelector('strong');
      const small = button.querySelector('small');
      if (strong) strong.textContent = values[0];
      if (small) small.textContent = values[1];
    });
    const rawDescription = document.querySelector('#page-xml .blade-description');
    if (rawDescription) rawDescription.textContent = '解析元のRAW XMLとデータセットファイル。通常の部品編集には使用しません。';
    const buildDescription = document.querySelector('#page-build .blade-description');
    if (buildDescription) buildDescription.textContent = '再構成済み成果物と実行ログ。再構成ボタンは現在の画面で処理を実行します。';
    const legacySummary = document.querySelector('#vi-inspector-source-details > summary');
    if (legacySummary) legacySummary.textContent = 'RAWデータ（class / UID / XML）';
    const detailButton = document.querySelector('#model-open-properties');
    if (detailButton) detailButton.textContent = 'プロパティ詳細';
  }

  function bindCapture(selector, handler) {
    document.querySelectorAll(selector).forEach((element) => {
      if (element.dataset.runtimeFixBound === 'true') return;
      element.dataset.runtimeFixBound = 'true';
      element.addEventListener('click', handler, true);
    });
  }

  function install() {
    if (runtime.initialized || !document.querySelector('#vi-editor-shell')) return false;
    runtime.initialized = true;
    renameViewsAndRawData();
    ensurePropertyPanel();
    bindCapture('#vi-save-layout', persistLayout);
    bindCapture('#header-rebuild,#rebuild-job,#build-run', rebuildInPlace);
    bindCapture('#model-open-properties', openInlineProperties);
    new MutationObserver(() => {
      renameViewsAndRawData();
      saveButtonState();
    }).observe(document.querySelector('#model-context-section') || document.body, {
      childList: true,
      subtree: true,
    });
    globalThis.VIRuntimeFixes = {
      ready: true,
      persistLayout,
      rebuildInPlace,
      openInlineProperties,
      sourceBounds,
      runtime,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIRuntimeFixes = { ready: false, runtime };
  waitForEditor();
})();
