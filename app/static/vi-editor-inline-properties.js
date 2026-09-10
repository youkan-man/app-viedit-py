'use strict';

(() => {
  const runtime = {
    ready: false,
    detail: null,
    selectedObjectId: null,
    changes: new Map(),
  };

  function semanticState() {
    return globalThis.VISemanticEditor?.S;
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }

  function propertyCategory(prop) {
    const name = String(prop.field_name || prop.name || '').toLowerCase();
    if (prop.value_type === 'rect' || prop.value_type === 'point' || name.includes('bounds')) return '配置';
    if (name.includes('color') || name.includes('font') || name.includes('visible')) return '外観';
    if (name.includes('name') || name.includes('label') || name.includes('text')) return '表示';
    if (name.includes('value') || name.includes('min') || name.includes('max') || name.includes('step')) return '値';
    if (name.includes('type') || name.includes('datatype')) return 'データ型';
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

  function ensurePanel() {
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
      void saveChanges();
    });
    return panel;
  }

  function updateSaveState() {
    const count = runtime.changes.size;
    const note = document.querySelector('#vi-inline-properties-change-count');
    const button = document.querySelector('#vi-inline-properties-save');
    if (note) note.textContent = count ? `${count}件変更` : '変更なし';
    if (button) button.disabled = !count;
  }

  function propertyControl(prop) {
    if (!prop.editable) {
      return textElement(
        'div',
        'vi-inline-property-value',
        String(prop.value ?? prop.preview ?? '—'),
      );
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
      if (input.value === original) runtime.changes.delete(prop.id);
      else runtime.changes.set(prop.id, input.value);
      updateSaveState();
    });
    return input;
  }

  function propertyRow(prop) {
    const row = document.createElement('label');
    row.className = 'vi-inline-property-row';
    const copy = document.createElement('span');
    copy.append(
      textElement('strong', '', prop.name || prop.field_name || 'property'),
      textElement(
        'small',
        '',
        `${propertyCategory(prop)} · ${prop.value_type}${prop.editable ? '' : ' · 読み取り専用'}`,
      ),
    );
    row.append(copy, propertyControl(prop));
    return row;
  }

  function renderRaw(detail, rawProperties) {
    const raw = document.querySelector('#vi-inline-properties-raw-content');
    if (!raw) return;
    raw.replaceChildren();
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
  }

  function render(detail) {
    runtime.detail = detail;
    runtime.changes.clear();
    const list = document.querySelector('#vi-inline-properties-meaningful');
    const stateElement = document.querySelector('#vi-inline-properties-state');
    if (!list) return;
    list.replaceChildren();

    const properties = detail.properties || [];
    const semanticProperties = properties.filter((prop) => !isRawProperty(prop));
    const rawProperties = properties.filter(isRawProperty);
    semanticProperties.slice(0, 80).forEach((prop) => list.append(propertyRow(prop)));
    if (!semanticProperties.length) {
      list.append(
        textElement(
          'div',
          'vi-inline-properties-empty',
          '編集対象となるVIプロパティはありません。',
        ),
      );
    }
    renderRaw(detail, rawProperties);
    if (stateElement) {
      stateElement.textContent = `${semanticProperties.length}項目 · RAW ${rawProperties.length}項目`;
    }
    updateSaveState();
  }

  async function open(event) {
    event?.preventDefault();
    event?.stopImmediatePropagation();
    const S = semanticState();
    const item = S?.objects.get(S.selected);
    if (!S?.job || !item) return;
    const panel = ensurePanel();
    panel.hidden = false;
    runtime.selectedObjectId = item.id;
    const status = panel.querySelector('#vi-inline-properties-state');
    if (status) status.textContent = '読込中…';
    try {
      const detail = await apiRequest(
        `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
      );
      if (semanticState()?.selected !== item.id) return;
      render(detail);
    } catch (error) {
      if (status) status.textContent = '読込失敗';
      showToast(`プロパティ詳細: ${describeError(error)}`, 'error', 10000);
    }
  }

  async function saveChanges() {
    const detail = runtime.detail;
    const S = semanticState();
    if (!detail || !S?.job || !runtime.changes.size) return;
    const button = document.querySelector('#vi-inline-properties-save');
    if (button) button.disabled = true;
    try {
      const payload = await apiRequest(
        `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(detail.id)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_file_sha256: detail.file_sha256,
            updates: [...runtime.changes].map(([property_id, value]) => ({
              property_id,
              value,
            })),
          }),
        },
      );
      runtime.changes.clear();
      await globalThis.renderJob(payload.job, { scroll: false });
      document.querySelector('#vi-inline-properties').hidden = true;
      showToast(`${payload.updated_properties.length}件のプロパティを保存しました。`, 'success');
    } catch (error) {
      showToast(`プロパティ保存: ${describeError(error)}`, 'error', 10000);
      updateSaveState();
    }
  }

  function install() {
    const button = document.querySelector('#model-open-properties');
    if (runtime.ready || !button || !document.querySelector('#model-inspector')) return false;
    runtime.ready = true;
    ensurePanel();
    button.textContent = 'プロパティ詳細';
    button.dataset.inlinePropertiesBound = 'true';
    button.addEventListener('click', open, true);
    globalThis.VIInlineProperties = {
      ready: true,
      runtime,
      open,
      saveChanges,
      isRawProperty,
    };
    return true;
  }

  function waitForInspector(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForInspector(attempt + 1), 25);
  }

  globalThis.VIInlineProperties = { ready: false, runtime };
  waitForInspector();
})();
