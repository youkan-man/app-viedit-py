'use strict';

(() => {
  const TYPE_LABELS = {
    numeric: '数値',
    boolean: 'ブール',
    string: '文字列',
    path: 'パス',
    array: '配列',
    cluster: 'クラスタ',
    refnum: 'リファレンス',
    ring: 'リング / 列挙',
    table: '表',
    unknown: '型未判定',
  };
  const state = {
    history: [],
    future: [],
    pointerBefore: null,
    geometryBefore: null,
    keyBefore: null,
    applyingHistory: false,
    decorationQueued: false,
    lastRevision: '',
    initialized: false,
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function semanticState() {
    return editor()?.S;
  }

  function numeric(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function normalizeType(value) {
    const key = String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
    if (!key) return 'unknown';
    if (/(numeric|number|double|single|float|int|uint|fixed|complex)/.test(key)) return 'numeric';
    if (/(boolean|bool)/.test(key)) return 'boolean';
    if (/(string|text|char)/.test(key)) return 'string';
    if (/(path)/.test(key)) return 'path';
    if (/(array)/.test(key)) return 'array';
    if (/(cluster|record|struct)/.test(key)) return 'cluster';
    if (/(refnum|reference)/.test(key)) return 'refnum';
    if (/(ring|enum)/.test(key)) return 'ring';
    if (/(table)/.test(key)) return 'table';
    return 'unknown';
  }

  function objectType(item, seen = new Set()) {
    const S = semanticState();
    if (!item || seen.has(item.id)) return 'unknown';
    seen.add(item.id);

    const explicit = normalizeType(
      item.data_type || item.datatype || item.value_type || item.type_name,
    );
    if (explicit !== 'unknown') return explicit;

    const kind = normalizeType(item.kind);
    if (kind !== 'unknown') return kind;
    if (['add', 'subtract', 'multiply', 'divide'].includes(item.kind)) return 'numeric';
    if (['equal', 'greater', 'less', 'and', 'or', 'xor'].includes(item.kind)) return 'boolean';

    if (item.linked_object_id) {
      const linked = S?.objects.get(item.linked_object_id);
      const linkedType = objectType(linked, seen);
      if (linkedType !== 'unknown') return linkedType;
    }
    if (item.owner_object_id) {
      const owner = S?.objects.get(item.owner_object_id);
      const ownerType = objectType(owner, seen);
      if (ownerType !== 'unknown') return ownerType;
    }
    for (const id of item.linked_terminal_ids || []) {
      const linkedTerminal = S?.objects.get(id);
      const terminalType = objectType(linkedTerminal, seen);
      if (terminalType !== 'unknown') return terminalType;
    }
    return 'unknown';
  }

  function wireType(wire) {
    const S = semanticState();
    if (!wire || !S) return 'unknown';
    const ids = [
      wire.source_object_id,
      ...(wire.target_object_ids || []),
      wire.source_terminal_id,
      ...(wire.target_terminal_ids || []),
    ].filter(Boolean);
    for (const id of ids) {
      const type = objectType(S.objects.get(id));
      if (type !== 'unknown') return type;
    }
    return 'unknown';
  }

  function typeLabel(type) {
    return TYPE_LABELS[type] || TYPE_LABELS.unknown;
  }

  function surfaceLabel(surface) {
    if (surface === 'front-panel') return 'フロントパネル';
    if (surface === 'block-diagram') return 'ブロックダイアグラム';
    return '—';
  }

  function directionLabel(direction) {
    if (direction === 'source') return '出力';
    if (direction === 'sink') return '入力';
    return '方向未判定';
  }

  function roleLabel(item, wire) {
    const S = semanticState();
    if (wire) {
      const source = S?.objects.get(wire.source_object_id)?.name || '未解決';
      const targets = (wire.target_object_ids || [])
        .map((id) => S?.objects.get(id)?.name)
        .filter(Boolean);
      return `${source} → ${targets.join(', ') || '未解決'}`;
    }
    if (!item) return '—';
    if (item.category === 'control') return '入力コントロール';
    if (item.category === 'indicator') return '表示インジケータ';
    if (item.category === 'terminal') return `${directionLabel(item.direction)}端子`;
    if (item.category === 'node') return `${editor()?.label(item) || item.kind}ノード`;
    return editor()?.label(item) || item.kind || 'オブジェクト';
  }

  function connectionSummary(item, wire) {
    const S = semanticState();
    if (wire) {
      const targets = (wire.target_terminal_ids || wire.target_object_ids || []).length;
      const route = (wire.route_points || []).length ? '保存経路' : '自動経路';
      return `${targets}分岐 · ${wire.resolved ? '接続確定' : '未解決'} · ${route}`;
    }
    if (!item) return '—';
    if (item.category === 'node') {
      const terminals = (item.terminal_ids || [])
        .map((id) => S?.objects.get(id))
        .filter(Boolean);
      const inputs = terminals.filter((terminal) => terminal.direction === 'sink').length;
      const outputs = terminals.filter((terminal) => terminal.direction === 'source').length;
      return `${inputs}入力 / ${outputs}出力 · ${(item.wire_ids || []).length}配線`;
    }
    if (item.category === 'terminal') {
      const owner = S?.objects.get(item.owner_object_id || item.linked_object_id);
      return `${directionLabel(item.direction)} · ${(item.wire_ids || []).length}配線${owner ? ` · ${owner.name}` : ''}`;
    }
    return `${(item.wire_ids || []).length}配線 · ${(item.linked_terminal_ids || []).length}対応端子`;
  }

  function currentBounds(item) {
    const E = editor();
    if (!item || !E) return null;
    const bounds = E.effectiveBounds?.(item) || E.getBounds?.(item);
    if (!bounds) return null;
    return {
      x: numeric(bounds.x),
      y: numeric(bounds.y),
      width: numeric(bounds.width),
      height: numeric(bounds.height),
    };
  }

  function baselineBounds(item) {
    if (!item?.bounds) return null;
    return {
      x: numeric(item.bounds.x),
      y: numeric(item.bounds.y),
      width: numeric(item.bounds.width),
      height: numeric(item.bounds.height),
    };
  }

  function sameBounds(first, second) {
    if (!first || !second) return false;
    return ['x', 'y', 'width', 'height'].every(
      (key) => Math.abs(numeric(first[key]) - numeric(second[key])) < 0.01,
    );
  }

  function snapshot(id) {
    const S = semanticState();
    const item = S?.objects.get(id);
    const bounds = currentBounds(item);
    return item && bounds ? { id, bounds } : null;
  }

  function clearHistory() {
    state.history = [];
    state.future = [];
    updateHistoryControls();
  }

  function recordHistory(before, after, source) {
    if (!before || !after || before.id !== after.id || sameBounds(before.bounds, after.bounds)) return;
    state.history.push({ before, after, source });
    if (state.history.length > 100) state.history.shift();
    state.future = [];
    updateHistoryControls();
  }

  function applySnapshot(entry) {
    const E = editor();
    const S = semanticState();
    const item = S?.objects.get(entry?.id);
    if (!E || !S || !item || !entry?.bounds) return;
    const base = baselineBounds(item);
    if (base && sameBounds(base, entry.bounds)) {
      S.local.delete(item.id);
      S.dirty.delete(item.id);
    } else {
      S.local.set(item.id, { ...entry.bounds });
      S.dirty.add(item.id);
    }
    state.applyingHistory = true;
    E.renderAll?.(false);
    state.applyingHistory = false;
    queueDecoration();
    focusCanvasObject(item.id);
  }

  function undo() {
    const action = state.history.pop();
    if (!action) return;
    state.future.push(action);
    applySnapshot(action.before);
    updateHistoryControls();
  }

  function redo() {
    const action = state.future.pop();
    if (!action) return;
    state.history.push(action);
    applySnapshot(action.after);
    updateHistoryControls();
  }

  function escapeSelector(value) {
    return globalThis.CSS?.escape ? CSS.escape(value) : String(value).replace(/["\\]/g, '\\$&');
  }

  function focusCanvasObject(id) {
    requestAnimationFrame(() => {
      document.querySelector(`[data-object-id="${escapeSelector(id)}"]`)?.focus?.();
    });
  }

  function updateHistoryControls() {
    const S = semanticState();
    const undoButton = document.querySelector('#vi-undo-layout');
    const redoButton = document.querySelector('#vi-redo-layout');
    if (undoButton) {
      undoButton.disabled = !state.history.length || Boolean(S?.saving);
      undoButton.title = state.history.length
        ? `元に戻す: ${state.history.at(-1).source}`
        : '元に戻す変更はありません';
    }
    if (redoButton) {
      redoButton.disabled = !state.future.length || Boolean(S?.saving);
      redoButton.title = state.future.length
        ? `やり直す: ${state.future.at(-1).source}`
        : 'やり直す変更はありません';
    }
    document.querySelector('#vi-editor-shell')?.classList.toggle(
      'has-unsaved-layout',
      Boolean(S?.dirty.size),
    );
    const historyNote = document.querySelector('#vi-history-status');
    if (historyNote) {
      historyNote.textContent = S?.dirty.size
        ? `未保存 ${S.dirty.size}`
        : '保存済み';
    }
  }

  function makeButton(id, text, title) {
    const button = document.createElement('button');
    button.id = id;
    button.type = 'button';
    button.textContent = text;
    button.title = title;
    button.className = 'vi-editor-command';
    return button;
  }

  function buildCommands() {
    const fit = document.querySelector('#model-graph-fit');
    if (fit && !document.querySelector('#vi-focus-selection')) {
      const focus = makeButton('vi-focus-selection', '選択へ', '選択オブジェクトを中央に表示 (F)');
      focus.disabled = true;
      fit.before(focus);
    }

    const zoomIn = document.querySelector('#model-graph-zoom-in');
    if (zoomIn && !document.querySelector('#vi-zoom-status')) {
      const zoomStatus = document.createElement('output');
      zoomStatus.id = 'vi-zoom-status';
      zoomStatus.className = 'vi-zoom-status';
      zoomStatus.value = '100%';
      zoomStatus.textContent = '100%';
      zoomIn.after(zoomStatus);
    }

    const saveActions = document.querySelector('.vi-save-actions');
    if (saveActions && !document.querySelector('#vi-undo-layout')) {
      const historyStatus = document.createElement('span');
      historyStatus.id = 'vi-history-status';
      historyStatus.className = 'vi-history-status';
      historyStatus.textContent = '保存済み';
      const undoButton = makeButton('vi-undo-layout', '↶', '元に戻す (Ctrl+Z)');
      const redoButton = makeButton('vi-redo-layout', '↷', 'やり直す (Ctrl+Y)');
      undoButton.setAttribute('aria-label', '配置を元に戻す');
      redoButton.setAttribute('aria-label', '配置をやり直す');
      saveActions.prepend(historyStatus, undoButton, redoButton);
    }
  }

  function makeInspectorRow(labelText, id) {
    const wrapper = document.createElement('div');
    const term = document.createElement('dt');
    const value = document.createElement('dd');
    term.textContent = labelText;
    value.id = id;
    value.textContent = '—';
    wrapper.append(term, value);
    return wrapper;
  }

  function buildInspector() {
    const inspector = document.querySelector('#model-inspector');
    if (!inspector || document.querySelector('#vi-semantic-inspector-grid')) return;

    const semantic = document.createElement('dl');
    semantic.id = 'vi-semantic-inspector-grid';
    semantic.className = 'vi-semantic-inspector-grid';
    semantic.append(
      makeInspectorRow('種類', 'vi-inspector-kind'),
      makeInspectorRow('画面', 'vi-inspector-surface'),
      makeInspectorRow('役割', 'vi-inspector-role'),
      makeInspectorRow('データ型', 'vi-inspector-data-type'),
      makeInspectorRow('接続', 'vi-inspector-connections-summary'),
      makeInspectorRow('配置', 'vi-inspector-bounds'),
    );

    const geometry = document.querySelector('#vi-geometry-editor');
    inspector.insertBefore(semantic, geometry || inspector.firstChild);

    const jump = makeButton('vi-jump-counterpart', '対応画面の部品へ移動', 'フロントパネルとブロックダイアグラムを切り替えます');
    jump.classList.add('vi-counterpart-command');
    jump.hidden = true;
    inspector.insertBefore(jump, geometry || inspector.firstChild);

    const legacy = inspector.querySelector('.model-inspector-grid');
    if (legacy) {
      const details = document.createElement('details');
      details.id = 'vi-inspector-source-details';
      details.className = 'vi-inspector-source-details';
      const summary = document.createElement('summary');
      summary.textContent = '解析元情報（class / UID / XML）';
      details.append(summary, legacy);
      const propertiesButton = document.querySelector('#model-open-properties');
      inspector.insertBefore(details, propertiesButton || null);
    }
  }

  function renderSemanticInspector() {
    const S = semanticState();
    if (!S) return;
    const item = S.objects.get(S.selected);
    const wire = S.wires.get(S.selected);
    const record = item || wire;
    const focusButton = document.querySelector('#vi-focus-selection');
    if (focusButton) focusButton.disabled = !record;
    if (!record) return;

    const type = wire ? wireType(wire) : objectType(item);
    const bounds = item ? currentBounds(item) : null;
    const set = (id, value) => {
      const element = document.querySelector(`#${id}`);
      if (element) element.textContent = value || '—';
    };
    set('vi-inspector-kind', wire ? '配線' : editor()?.label(item));
    set('vi-inspector-surface', surfaceLabel(item?.surface || 'block-diagram'));
    set('vi-inspector-role', roleLabel(item, wire));
    set('vi-inspector-data-type', typeLabel(type));
    set('vi-inspector-connections-summary', connectionSummary(item, wire));
    set('vi-inspector-bounds', bounds ? editor()?.boundsText(bounds) : `${(wire?.route_points || []).length} 経路点`);

    const jump = document.querySelector('#vi-jump-counterpart');
    const counterpart = item ? editor()?.counterpartId?.(item) : null;
    if (jump) {
      jump.hidden = !counterpart;
      jump.dataset.targetId = counterpart || '';
    }
  }

  function orthogonalizePath(path) {
    if (!path || !path.includes('L')) return path;
    const numberPattern = '-?(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:e[-+]?\\d+)?';
    const diagonal = new RegExp(`\\bL\\s+(${numberPattern})\\s+(${numberPattern})`, 'gi');
    return path.replace(diagonal, 'H $1 V $2');
  }

  function selectedTerminalIds() {
    const S = semanticState();
    const ids = new Set();
    const selectedObject = S?.objects.get(S.selected);
    const selectedWire = S?.wires.get(S.selected);
    if (selectedObject) {
      if (selectedObject.category === 'terminal') ids.add(selectedObject.id);
      (selectedObject.terminal_ids || []).forEach((id) => ids.add(id));
      (selectedObject.linked_terminal_ids || []).forEach((id) => ids.add(id));
    }
    if (selectedWire) {
      (selectedWire.terminal_ids || []).forEach((id) => ids.add(id));
    }
    return ids;
  }

  function decorateTerminal(group, item, type, showCaption) {
    if (!group.querySelector('.vi-terminal-type-dot')) {
      const bounds = currentBounds(item) || { width: 8, height: 8 };
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.classList.add('vi-terminal-type-dot', `is-type-${type}`);
      dot.setAttribute('cx', String(Math.max(2, bounds.width / 2)));
      dot.setAttribute('cy', String(Math.max(2, bounds.height / 2)));
      dot.setAttribute('r', String(Math.max(1.5, Math.min(bounds.width, bounds.height) * 0.23)));
      group.append(dot);
    }
    if (showCaption && !group.querySelector('.vi-terminal-caption')) {
      const bounds = currentBounds(item) || { width: 8, height: 8 };
      const caption = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      caption.classList.add('vi-terminal-caption');
      caption.textContent = item.name || directionLabel(item.direction);
      caption.setAttribute('y', String(Math.max(8, bounds.height / 2 + 3)));
      if (item.direction === 'sink') {
        caption.setAttribute('x', '-5');
        caption.setAttribute('text-anchor', 'end');
      } else {
        caption.setAttribute('x', String(bounds.width + 5));
        caption.setAttribute('text-anchor', 'start');
      }
      group.append(caption);
    }
  }

  function decorateCanvas() {
    const S = semanticState();
    const root = document.querySelector('#model-graph-svg');
    if (!S || !root) return;
    root.classList.toggle('has-semantic-selection', Boolean(S.selected));
    const terminalIds = selectedTerminalIds();

    root.querySelectorAll('[data-object-id]').forEach((group) => {
      const item = S.objects.get(group.dataset.objectId);
      if (!item) return;
      const type = objectType(item);
      group.dataset.dataType = type;
      group.classList.add(`is-type-${type}`);
      if (item.category === 'terminal') {
        decorateTerminal(group, item, type, terminalIds.has(item.id));
      }
    });

    root.querySelectorAll('[data-wire-id]').forEach((group) => {
      const wire = S.wires.get(group.dataset.wireId);
      const type = wireType(wire);
      group.dataset.dataType = type;
      group.classList.add(`is-type-${type}`);
      group.querySelectorAll('.vi-wire,.vi-wire-hit').forEach((path) => {
        const current = path.getAttribute('d') || '';
        const orthogonal = orthogonalizePath(current);
        if (orthogonal !== current) path.setAttribute('d', orthogonal);
      });
    });
  }

  function decorateList() {
    const S = semanticState();
    if (!S) return;
    document.querySelectorAll('#vi-object-list [data-list-id]').forEach((button) => {
      const item = S.objects.get(button.dataset.listId);
      const wire = S.wires.get(button.dataset.listId);
      const type = wire ? wireType(wire) : objectType(item);
      button.dataset.dataType = type;
      button.classList.add(`is-type-${type}`);
      button.title = `${wire ? roleLabel(null, wire) : item?.name || ''} · ${typeLabel(type)}`;
      const count = wire
        ? (wire.target_terminal_ids || wire.target_object_ids || []).length
        : (item?.wire_ids || item?.terminal_ids || []).length;
      if (count > 0 && !button.querySelector('.vi-list-connection-count')) {
        const badge = document.createElement('span');
        badge.className = 'vi-list-connection-count';
        badge.textContent = String(count);
        badge.setAttribute('aria-label', `${count}接続`);
        button.append(badge);
      }
    });
  }

  function updateZoomStatus() {
    const S = semanticState();
    const output = document.querySelector('#vi-zoom-status');
    if (!S?.box || !S.fitBox || !output) return;
    const percent = Math.max(5, Math.min(3200, Math.round((S.fitBox.width / S.box.width) * 100)));
    output.value = `${percent}%`;
    output.textContent = `${percent}%`;
  }

  function queueDecoration() {
    if (state.decorationQueued) return;
    state.decorationQueued = true;
    requestAnimationFrame(() => {
      state.decorationQueued = false;
      const S = semanticState();
      if (state.lastRevision && S?.revision !== state.lastRevision && !state.applyingHistory) {
        clearHistory();
      }
      state.lastRevision = S?.revision || '';
      decorateCanvas();
      decorateList();
      renderSemanticInspector();
      updateZoomStatus();
      updateHistoryControls();
    });
  }

  function selectedWorldBounds() {
    const S = semanticState();
    if (!S?.selected) return null;
    const item = S.objects.get(S.selected);
    if (item) return currentBounds(item);
    const groups = [...document.querySelectorAll(`[data-wire-id="${escapeSelector(S.selected)}"]`)];
    if (!groups.length) return null;
    const boxes = groups.map((group) => group.getBBox()).filter((box) => box.width || box.height);
    if (!boxes.length) return null;
    const left = Math.min(...boxes.map((box) => box.x));
    const top = Math.min(...boxes.map((box) => box.y));
    const right = Math.max(...boxes.map((box) => box.x + box.width));
    const bottom = Math.max(...boxes.map((box) => box.y + box.height));
    return { x: left, y: top, width: right - left, height: bottom - top };
  }

  function focusSelection() {
    const S = semanticState();
    const bounds = selectedWorldBounds();
    const viewport = document.querySelector('#model-graph-viewport');
    const svgRoot = document.querySelector('#model-graph-svg');
    if (!S || !bounds || !viewport || !svgRoot) return;
    const rect = viewport.getBoundingClientRect();
    const aspect = Math.max(0.25, rect.width / Math.max(1, rect.height));
    let width = Math.max(180, bounds.width + 140);
    let height = Math.max(130, bounds.height + 110);
    if (width / height > aspect) height = width / aspect;
    else width = height * aspect;
    const box = {
      x: bounds.x + bounds.width / 2 - width / 2,
      y: bounds.y + bounds.height / 2 - height / 2,
      width,
      height,
    };
    S.box = box;
    svgRoot.setAttribute('viewBox', `${box.x} ${box.y} ${box.width} ${box.height}`);
    updateZoomStatus();
  }

  function clearSelection() {
    const E = editor();
    const S = semanticState();
    if (!E || !S?.selected) return;
    S.selected = null;
    E.renderAll?.(false);
    queueDecoration();
  }

  function attachHistoryListeners() {
    const S = semanticState();
    const svgRoot = document.querySelector('#model-graph-svg');
    if (!S || !svgRoot) return;

    svgRoot.addEventListener('pointerdown', (event) => {
      const group = event.target.closest?.('[data-object-id]');
      const item = group ? S.objects.get(group.dataset.objectId) : null;
      state.pointerBefore = item?.movable ? snapshot(item.id) : null;
    }, true);
    const commitPointer = () => {
      if (!state.pointerBefore) return;
      recordHistory(
        state.pointerBefore,
        snapshot(state.pointerBefore.id),
        'キャンバス操作',
      );
      state.pointerBefore = null;
      queueDecoration();
    };
    svgRoot.addEventListener('pointerup', commitPointer);
    svgRoot.addEventListener('pointercancel', () => { state.pointerBefore = null; });

    svgRoot.addEventListener('keydown', (event) => {
      const group = event.target.closest?.('[data-object-id]');
      const item = group ? S.objects.get(group.dataset.objectId) : null;
      if (!item?.movable || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
      const before = snapshot(item.id);
      setTimeout(() => {
        recordHistory(before, snapshot(item.id), 'キー移動');
        focusCanvasObject(item.id);
        queueDecoration();
      }, 0);
    }, true);

    ['vi-geometry-x', 'vi-geometry-y', 'vi-geometry-width', 'vi-geometry-height'].forEach((id) => {
      const input = document.querySelector(`#${id}`);
      input?.addEventListener('focusin', () => {
        state.geometryBefore = S.selected ? snapshot(S.selected) : null;
      });
      input?.addEventListener('change', () => {
        const before = state.geometryBefore;
        state.geometryBefore = null;
        setTimeout(() => {
          if (before) recordHistory(before, snapshot(before.id), '数値入力');
          queueDecoration();
        }, 0);
      });
    });
  }

  function attachListKeyboard() {
    const list = document.querySelector('#vi-object-list');
    const S = semanticState();
    if (!list || !S) return;
    list.addEventListener('keydown', (event) => {
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      const buttons = [...list.querySelectorAll('[data-list-id]')];
      if (!buttons.length) return;
      const current = Math.max(0, buttons.indexOf(event.target.closest('[data-list-id]')));
      let index = current;
      if (event.key === 'ArrowDown') index = Math.min(buttons.length - 1, current + 1);
      if (event.key === 'ArrowUp') index = Math.max(0, current - 1);
      if (event.key === 'Home') index = 0;
      if (event.key === 'End') index = buttons.length - 1;
      const id = buttons[index].dataset.listId;
      event.preventDefault();
      editor()?.select?.(id, false);
      requestAnimationFrame(() => {
        document.querySelector(`[data-list-id="${escapeSelector(id)}"]`)?.focus?.();
      });
    });
  }

  function attachCommands() {
    document.querySelector('#vi-focus-selection')?.addEventListener('click', focusSelection);
    document.querySelector('#vi-undo-layout')?.addEventListener('click', undo);
    document.querySelector('#vi-redo-layout')?.addEventListener('click', redo);
    document.querySelector('#vi-jump-counterpart')?.addEventListener('click', (event) => {
      const targetId = event.currentTarget.dataset.targetId;
      if (targetId) editor()?.select?.(targetId, true);
    });

    document.querySelector('#vi-revert-layout')?.addEventListener('click', () => {
      setTimeout(clearHistory, 0);
    });
    document.querySelector('#model-graph-refresh')?.addEventListener('click', () => {
      setTimeout(clearHistory, 0);
    });
    document.querySelector('#vi-save-layout')?.addEventListener('click', () => {
      let attempts = 0;
      const poll = () => {
        attempts += 1;
        const S = semanticState();
        if (!S?.saving && !S?.dirty.size) {
          clearHistory();
          return;
        }
        if (attempts < 200) setTimeout(poll, 25);
      };
      setTimeout(poll, 25);
    });

    document.addEventListener('keydown', (event) => {
      const target = event.target;
      const editing = target instanceof HTMLInputElement
        || target instanceof HTMLTextAreaElement
        || target instanceof HTMLSelectElement
        || target?.isContentEditable;
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
        return;
      }
      if (modifier && (event.key.toLowerCase() === 'y' || (event.shiftKey && event.key.toLowerCase() === 'z'))) {
        event.preventDefault();
        redo();
        return;
      }
      if (editing) return;
      if (event.key === '/') {
        event.preventDefault();
        document.querySelector('#model-graph-query')?.focus?.();
      } else if (event.key.toLowerCase() === 'f') {
        event.preventDefault();
        focusSelection();
      } else if (event.key === 'Escape') {
        clearSelection();
      }
    });
  }

  function installObservers() {
    const root = document.querySelector('#model-graph-svg');
    const list = document.querySelector('#vi-object-list');
    if (root) {
      new MutationObserver(queueDecoration).observe(root, {
        childList: true,
        subtree: true,
      });
      new MutationObserver(updateZoomStatus).observe(root, {
        attributes: true,
        attributeFilter: ['viewBox'],
      });
    }
    if (list) {
      new MutationObserver(queueDecoration).observe(list, {
        childList: true,
        subtree: true,
      });
    }
    window.addEventListener('resize', queueDecoration);
  }

  function install() {
    const E = editor();
    const S = semanticState();
    if (state.initialized || !E?.S || !document.querySelector('#vi-editor-shell')) return false;
    state.initialized = true;
    state.lastRevision = S?.revision || '';
    buildCommands();
    buildInspector();
    attachHistoryListeners();
    attachListKeyboard();
    attachCommands();
    installObservers();
    queueDecoration();
    globalThis.VISemanticEnhancements = {
      ready: true,
      objectType,
      wireType,
      orthogonalizePath,
      focusSelection,
      undo,
      redo,
      history: state,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 200) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VISemanticEnhancements = { ready: false };
  waitForEditor();
})();
