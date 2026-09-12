'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const MAX_SELECTION = 500;
  const runtime = {
    ready: false,
    internalSelect: false,
    applyingBatchHistory: false,
    decorating: false,
    decorationScheduled: false,
    renderScheduled: false,
    suppressClickUntil: 0,
    selectedIds: new Set(),
    primaryId: null,
    rangeAnchorId: null,
    gesture: null,
    marquee: null,
    originalSelect: null,
    originalInstall: null,
    originalRenderCanvas: null,
    originalRenderAll: null,
    elements: {},
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function enhancements() {
    return globalThis.VISemanticEnhancements;
  }

  function navigationHistory() {
    return globalThis.VINavigationHistoryStability;
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function cloneBounds(bounds) {
    if (!bounds) return null;
    const result = {
      x: finite(bounds.x, NaN),
      y: finite(bounds.y, NaN),
      width: finite(bounds.width, NaN),
      height: finite(bounds.height, NaN),
    };
    if (!Object.values(result).every(Number.isFinite)) return null;
    if (result.width <= 0 || result.height <= 0) return null;
    return result;
  }

  function sameBounds(first, second, tolerance = 0.01) {
    if (!first || !second) return false;
    return ['x', 'y', 'width', 'height'].every((key) => (
      Math.abs(finite(first[key]) - finite(second[key])) <= tolerance
    ));
  }

  function effectiveBounds(item, index = 0) {
    const E = editor();
    return E?.effectiveBounds?.(item, index)
      || E?.getBounds?.(item, index)
      || null;
  }

  function objectExists(id) {
    return Boolean(id && state()?.objects.has(id));
  }

  function selectedObjects() {
    const S = state();
    if (!S) return [];
    return [...runtime.selectedIds]
      .map((id) => S.objects.get(id))
      .filter(Boolean);
  }

  function visibleSelectedObjects() {
    const S = state();
    return selectedObjects().filter((item) => item.surface === S?.surface);
  }

  function ownerIds(item) {
    return [
      item?.owner_object_id,
      item?.parent_object_id,
      item?.bounds?.relative_to_object_id,
    ].filter(Boolean);
  }

  function hasMovableSelectedAncestor(item, movableIds) {
    const S = state();
    if (!S || !item) return false;
    const queue = [...ownerIds(item)];
    const visited = new Set();
    while (queue.length) {
      const id = queue.shift();
      if (!id || visited.has(id)) continue;
      visited.add(id);
      if (movableIds.has(id)) return true;
      const owner = S.objects.get(id);
      if (owner) queue.push(...ownerIds(owner));
    }
    return false;
  }

  function movementRoots() {
    const candidates = visibleSelectedObjects().filter((item) => item.movable);
    const movableIds = new Set(candidates.map((item) => item.id));
    return candidates.filter((item) => !hasMovableSelectedAncestor(item, movableIds));
  }

  function selectionBounds(items = visibleSelectedObjects()) {
    const boxes = items.map((item, index) => cloneBounds(effectiveBounds(item, index)))
      .filter(Boolean);
    if (!boxes.length) return null;
    const left = Math.min(...boxes.map((box) => box.x));
    const top = Math.min(...boxes.map((box) => box.y));
    const right = Math.max(...boxes.map((box) => box.x + box.width));
    const bottom = Math.max(...boxes.map((box) => box.y + box.height));
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
    };
  }

  function labelFor(item) {
    return item?.name || editor()?.label?.(item) || item?.id || '名称なし';
  }

  function typeFor(item) {
    return enhancements()?.objectType?.(item)
      || item?.data_type
      || item?.kind
      || 'unknown';
  }

  function normalizedSelection(ids, primaryId = null) {
    const S = state();
    if (!S) return { ids: [], primaryId: null };
    const values = [...new Set(ids)]
      .filter((id) => S.objects.has(id))
      .filter((id) => S.objects.get(id)?.surface === S.surface)
      .slice(0, MAX_SELECTION);
    const primary = values.includes(primaryId)
      ? primaryId
      : values.at(-1) || null;
    return { ids: values, primaryId: primary };
  }

  function setPrimarySelection(id, reveal = false) {
    const E = editor();
    if (!E || !id) return false;
    runtime.internalSelect = true;
    try {
      runtime.originalSelect.call(E, id, reveal);
    } finally {
      runtime.internalSelect = false;
    }
    return true;
  }

  function renderAfterSelection() {
    const E = editor();
    E?.renderList?.();
    E?.renderCanvas?.();
    E?.renderInspector?.();
    E?.updateStatus?.();
    scheduleDecoration();
  }

  function setSelection(ids, primaryId = null, options = {}) {
    const S = state();
    if (!S) return false;
    const { reveal = false, render = true } = options;
    const normalized = normalizedSelection(ids, primaryId);
    runtime.selectedIds = new Set(normalized.ids);
    runtime.primaryId = normalized.primaryId;
    if (normalized.primaryId) {
      setPrimarySelection(normalized.primaryId, reveal);
      runtime.rangeAnchorId = normalized.primaryId;
    } else {
      S.selected = null;
      if (render) renderAfterSelection();
    }
    if (normalized.primaryId && render) scheduleDecoration();
    return true;
  }

  function clearSelection({ render = true } = {}) {
    const S = state();
    if (!S) return false;
    runtime.selectedIds.clear();
    runtime.primaryId = null;
    runtime.rangeAnchorId = null;
    S.selected = null;
    if (render) renderAfterSelection();
    return true;
  }

  function toggleSelection(id, { reveal = false } = {}) {
    if (!objectExists(id)) return false;
    const next = new Set(runtime.selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    const primary = next.has(id) ? id : [...next].at(-1) || null;
    return setSelection([...next], primary, { reveal });
  }

  function visibleListButtons() {
    return [...document.querySelectorAll('#vi-object-list [data-list-id]')]
      .filter((button) => objectExists(button.dataset.listId))
      .filter((button) => !button.hidden && button.getClientRects().length > 0);
  }

  function selectListRange(id, { additive = false } = {}) {
    const buttons = visibleListButtons();
    const ids = buttons.map((button) => button.dataset.listId);
    const targetIndex = ids.indexOf(id);
    const anchorIndex = ids.indexOf(runtime.rangeAnchorId);
    if (targetIndex < 0 || anchorIndex < 0) {
      return setSelection(additive ? [...runtime.selectedIds, id] : [id], id);
    }
    const start = Math.min(anchorIndex, targetIndex);
    const end = Math.max(anchorIndex, targetIndex);
    const range = ids.slice(start, end + 1);
    return setSelection(
      additive ? [...runtime.selectedIds, ...range] : range,
      id,
    );
  }

  function updateSelectionClasses() {
    const S = state();
    if (!S) return;
    const selected = runtime.selectedIds;
    const multiple = selected.size > 1;
    document.querySelectorAll('#model-graph-svg [data-object-id]').forEach((group) => {
      const id = group.dataset.objectId;
      const active = selected.has(id);
      group.classList.toggle('is-multi-selected', active);
      group.classList.toggle('is-multi-primary', active && id === runtime.primaryId);
      group.setAttribute('aria-selected', String(active));
    });
    document.querySelectorAll('#vi-object-list [data-list-id]').forEach((button) => {
      const id = button.dataset.listId;
      const active = selected.has(id);
      button.classList.toggle('is-multi-selected', active);
      button.classList.toggle('is-multi-primary', active && id === runtime.primaryId);
      button.setAttribute('aria-selected', String(active));
    });
    const shell = document.querySelector('#vi-editor-shell');
    shell?.classList.toggle('has-multi-selection', multiple);
    shell?.classList.toggle('has-any-object-selection', selected.size > 0);
    if (S.el?.modelGraphSvg) {
      S.el.modelGraphSvg.dataset.multiSelectionCount = String(selected.size);
    }
  }

  function ensureBoundsOverlay() {
    const root = state()?.el?.modelGraphSvg;
    if (!root) return null;
    let rect = root.querySelector(':scope > #vi-multi-selection-bounds');
    if (!rect) {
      rect = document.createElementNS(SVG_NS, 'rect');
      rect.id = 'vi-multi-selection-bounds';
      rect.classList.add('vi-multi-selection-bounds');
      rect.setAttribute('pointer-events', 'none');
      root.append(rect);
    }
    return rect;
  }

  function updateBoundsOverlay() {
    const rect = ensureBoundsOverlay();
    const bounds = runtime.selectedIds.size > 1 ? selectionBounds() : null;
    if (!rect) return;
    rect.hidden = !bounds;
    if (!bounds) return;
    rect.setAttribute('x', String(bounds.x));
    rect.setAttribute('y', String(bounds.y));
    rect.setAttribute('width', String(bounds.width));
    rect.setAttribute('height', String(bounds.height));
  }

  function selectionSummary() {
    const S = state();
    const items = visibleSelectedObjects();
    const roots = movementRoots();
    const bounds = selectionBounds(items);
    const surfaces = [...new Set(items.map((item) => item.surface))];
    return {
      count: items.length,
      primaryId: runtime.primaryId,
      primaryName: labelFor(S?.objects.get(runtime.primaryId)),
      surface: surfaces.length === 1 ? surfaces[0] : 'mixed',
      bounds,
      movableCount: roots.length,
      items,
    };
  }

  function summaryText() {
    const summary = selectionSummary();
    const surface = summary.surface === 'front-panel'
      ? 'フロントパネル'
      : summary.surface === 'block-diagram'
        ? 'ブロックダイアグラム'
        : '複数Surface';
    const bounds = summary.bounds
      ? `X=${summary.bounds.x.toFixed(1)}, Y=${summary.bounds.y.toFixed(1)}, W=${summary.bounds.width.toFixed(1)}, H=${summary.bounds.height.toFixed(1)}`
      : '範囲なし';
    const lines = [
      `選択: ${summary.count}件`,
      `画面: ${surface}`,
      `主選択: ${summary.primaryName || 'なし'}`,
      `移動対象: ${summary.movableCount}件`,
      `範囲: ${bounds}`,
      '',
      ...summary.items.map((item, index) => (
        `${index + 1}. ${labelFor(item)} [${item.category || item.kind || 'object'} / ${typeFor(item)}] (${item.id})`
      )),
    ];
    return lines.join('\n');
  }

  async function copySummary() {
    const text = summaryText();
    let copied = false;
    try {
      await navigator.clipboard?.writeText?.(text);
      copied = true;
    } catch {
      copied = false;
    }
    if (!copied) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.className = 'vi-multi-selection-clipboard';
      document.body.append(textarea);
      textarea.select();
      copied = document.execCommand('copy');
      textarea.remove();
    }
    const button = runtime.elements.copy;
    if (button) {
      const previous = button.textContent;
      button.textContent = copied ? 'コピー済み' : 'コピー失敗';
      setTimeout(() => { button.textContent = previous; }, 1200);
    }
    return copied;
  }

  function buildInspector() {
    const inspector = document.querySelector('#model-inspector');
    if (!inspector || document.querySelector('#vi-multi-selection-inspector')) return;
    const section = document.createElement('section');
    section.id = 'vi-multi-selection-inspector';
    section.className = 'vi-multi-selection-inspector';
    section.hidden = true;
    section.innerHTML = `
      <div class="vi-multi-selection-heading">
        <strong>複数選択</strong>
        <button id="vi-copy-selection-summary" type="button">選択内容をコピー</button>
      </div>
      <dl class="vi-multi-selection-grid">
        <div><dt>選択</dt><dd id="vi-multi-selection-count">0件</dd></div>
        <div><dt>画面</dt><dd id="vi-multi-selection-surface">—</dd></div>
        <div><dt>主選択</dt><dd id="vi-multi-selection-primary">—</dd></div>
        <div><dt>移動</dt><dd id="vi-multi-selection-movable">0件</dd></div>
        <div class="is-wide"><dt>範囲</dt><dd id="vi-multi-selection-geometry">—</dd></div>
      </dl>
      <p class="vi-multi-selection-note">グループのリサイズは無効です。各オブジェクトの相対位置を保ったまま移動できます。</p>`;
    const geometry = document.querySelector('#vi-geometry-editor');
    if (geometry?.parentElement === inspector) inspector.insertBefore(section, geometry);
    else inspector.prepend(section);
    runtime.elements.inspector = section;
    runtime.elements.copy = section.querySelector('#vi-copy-selection-summary');
    runtime.elements.count = section.querySelector('#vi-multi-selection-count');
    runtime.elements.surface = section.querySelector('#vi-multi-selection-surface');
    runtime.elements.primary = section.querySelector('#vi-multi-selection-primary');
    runtime.elements.movable = section.querySelector('#vi-multi-selection-movable');
    runtime.elements.geometry = section.querySelector('#vi-multi-selection-geometry');
    runtime.elements.copy.addEventListener('click', () => void copySummary());
  }

  function buildStatus() {
    const actions = document.querySelector('.vi-canvas-actions');
    if (!actions || document.querySelector('#vi-multi-selection-status')) return;
    const output = document.createElement('output');
    output.id = 'vi-multi-selection-status';
    output.className = 'vi-multi-selection-status';
    output.hidden = true;
    actions.prepend(output);
    runtime.elements.status = output;
  }

  function updateInspector() {
    buildInspector();
    buildStatus();
    const summary = selectionSummary();
    const multiple = summary.count > 1;
    if (runtime.elements.inspector) runtime.elements.inspector.hidden = !multiple;
    if (runtime.elements.status) {
      runtime.elements.status.hidden = !multiple;
      runtime.elements.status.textContent = multiple
        ? `選択 ${summary.count} · 移動可 ${summary.movableCount}`
        : '';
    }
    if (!multiple) return;
    const surface = summary.surface === 'front-panel'
      ? 'フロントパネル'
      : summary.surface === 'block-diagram'
        ? 'ブロックダイアグラム'
        : '複数Surface';
    runtime.elements.count.textContent = `${summary.count}件`;
    runtime.elements.surface.textContent = surface;
    runtime.elements.primary.textContent = summary.primaryName || '—';
    runtime.elements.movable.textContent = `${summary.movableCount}件`;
    runtime.elements.geometry.textContent = summary.bounds
      ? `X ${summary.bounds.x.toFixed(1)} / Y ${summary.bounds.y.toFixed(1)} / W ${summary.bounds.width.toFixed(1)} / H ${summary.bounds.height.toFixed(1)}`
      : '—';
  }

  function decorate() {
    if (runtime.decorating) return false;
    runtime.decorating = true;
    try {
      const S = state();
      if (!S?.vi) return false;
      runtime.selectedIds = new Set(
        [...runtime.selectedIds].filter((id) => S.objects.has(id)),
      );
      if (!runtime.selectedIds.has(runtime.primaryId)) {
        runtime.primaryId = [...runtime.selectedIds].at(-1) || null;
      }
      updateSelectionClasses();
      updateBoundsOverlay();
      updateInspector();
      updateHistoryControls();
      return true;
    } finally {
      runtime.decorating = false;
    }
  }

  function scheduleDecoration() {
    if (runtime.decorationScheduled) return;
    runtime.decorationScheduled = true;
    requestAnimationFrame(() => {
      runtime.decorationScheduled = false;
      decorate();
    });
  }

  function scheduleRender() {
    if (runtime.renderScheduled) return;
    runtime.renderScheduled = true;
    requestAnimationFrame(() => {
      runtime.renderScheduled = false;
      const E = editor();
      E?.renderCanvas?.();
      E?.renderInspector?.();
      E?.updateStatus?.();
      scheduleDecoration();
    });
  }

  function clientToWorld(event) {
    const bridge = globalThis.VISemanticNavigationBridge;
    if (bridge?.ready && typeof bridge.clientToWorld === 'function') {
      return bridge.clientToWorld(event.clientX, event.clientY);
    }
    const root = state()?.el?.modelGraphSvg;
    const matrix = root?.getScreenCTM?.();
    if (!matrix) return null;
    const point = root.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const result = point.matrixTransform(matrix.inverse());
    return { x: result.x, y: result.y };
  }

  function magneticSnapDelta(before, dx, dy) {
    const S = state();
    if (!S?.snap) return { dx, dy };
    const grid = Math.max(1, finite(S.grid, 1));
    const threshold = Math.min(2, grid * 0.25);
    const targetX = before.x + dx;
    const targetY = before.y + dy;
    const snappedX = Math.round(targetX / grid) * grid;
    const snappedY = Math.round(targetY / grid) * grid;
    return {
      dx: Math.abs(snappedX - targetX) <= threshold
        ? snappedX - before.x
        : dx,
      dy: Math.abs(snappedY - targetY) <= threshold
        ? snappedY - before.y
        : dy,
    };
  }

  function beforeMapForRoots(roots = movementRoots()) {
    return new Map(roots.map((item, index) => [
      item.id,
      cloneBounds(effectiveBounds(item, index)),
    ]).filter(([, bounds]) => Boolean(bounds)));
  }

  function applyTranslation(beforeMap, dx, dy) {
    const S = state();
    if (!S) return;
    beforeMap.forEach((before, id) => {
      const item = S.objects.get(id);
      if (!item?.movable) return;
      S.local.set(id, {
        x: before.x + dx,
        y: before.y + dy,
        width: before.width,
        height: before.height,
      });
      S.dirty.add(id);
    });
    scheduleRender();
  }

  function batchHistoryState() {
    return enhancements()?.history || null;
  }

  function updateHistoryControls() {
    const historyState = batchHistoryState();
    if (!historyState) return;
    const undo = document.querySelector('#vi-undo-layout');
    const redo = document.querySelector('#vi-redo-layout');
    const status = document.querySelector('#vi-history-status');
    if (undo) undo.disabled = historyState.history.length === 0;
    if (redo) redo.disabled = historyState.future.length === 0;
    if (status) {
      const action = historyState.history.at(-1);
      status.textContent = action?.multi_selection
        ? `${action.source} · ${action.entries.length}件`
        : historyState.history.length
          ? `${historyState.history.length}操作`
          : '保存済み';
    }
  }

  function recordBatch(beforeMap, source) {
    const historyState = batchHistoryState();
    const S = state();
    if (!historyState || !S || runtime.applyingBatchHistory) return false;
    const entries = [];
    beforeMap.forEach((before, id) => {
      const item = S.objects.get(id);
      const after = cloneBounds(effectiveBounds(item));
      if (before && after && !sameBounds(before, after)) {
        entries.push({ id, before: { ...before }, after: { ...after } });
      }
    });
    if (!entries.length) return false;
    historyState.history.push({
      multi_selection: true,
      source,
      entries,
      selectedIds: [...runtime.selectedIds],
      primaryId: runtime.primaryId,
      timestamp: Date.now(),
    });
    if (historyState.history.length > 80) historyState.history.shift();
    historyState.future = [];
    updateHistoryControls();
    return true;
  }

  function applyBatch(action, direction) {
    const S = state();
    const E = editor();
    if (!S || !E || !action?.multi_selection) return false;
    runtime.applyingBatchHistory = true;
    try {
      const targets = action.entries.map((entry) => ({
        id: entry.id,
        item: S.objects.get(entry.id),
        bounds: cloneBounds(direction === 'undo' ? entry.before : entry.after),
      })).filter((entry) => entry.item && entry.bounds);
      const baselines = new Map(targets.map((entry) => [
        entry.id,
        cloneBounds(E.getBounds?.(entry.item)),
      ]));
      targets.forEach(({ id, bounds }) => {
        const baseline = baselines.get(id);
        if (baseline && sameBounds(bounds, baseline)) {
          S.local.delete(id);
          S.dirty.delete(id);
        } else {
          S.local.set(id, { ...bounds });
          S.dirty.add(id);
        }
      });
      runtime.selectedIds = new Set(
        (action.selectedIds || []).filter((id) => S.objects.has(id)),
      );
      runtime.primaryId = runtime.selectedIds.has(action.primaryId)
        ? action.primaryId
        : [...runtime.selectedIds].at(-1) || null;
      S.selected = runtime.primaryId;
      E.renderAll?.(false);
      scheduleDecoration();
      return true;
    } finally {
      runtime.applyingBatchHistory = false;
    }
  }

  function undoBatch() {
    const historyState = batchHistoryState();
    const action = historyState?.history.at(-1);
    if (!action?.multi_selection) return false;
    historyState.history.pop();
    historyState.future.push(action);
    applyBatch(action, 'undo');
    updateHistoryControls();
    return true;
  }

  function redoBatch() {
    const historyState = batchHistoryState();
    const action = historyState?.future.at(-1);
    if (!action?.multi_selection) return false;
    historyState.future.pop();
    historyState.history.push(action);
    applyBatch(action, 'redo');
    updateHistoryControls();
    return true;
  }

  function beginGroupGesture(event, group, item) {
    const roots = movementRoots();
    const before = beforeMapForRoots(roots);
    const startWorld = clientToWorld(event);
    if (!before.size || !startWorld) return false;
    runtime.gesture = {
      pointerId: event.pointerId,
      group,
      item,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startWorld,
      before,
      moved: false,
      lastDx: 0,
      lastDy: 0,
    };
    state()?.el?.modelGraphViewport?.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function moveGroupGesture(event) {
    const gesture = runtime.gesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return false;
    const world = clientToWorld(event);
    if (!world) return false;
    const clientDistance = Math.hypot(
      event.clientX - gesture.startClientX,
      event.clientY - gesture.startClientY,
    );
    if (!gesture.moved && clientDistance < 2) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return true;
    }
    gesture.moved = true;
    let dx = world.x - gesture.startWorld.x;
    let dy = world.y - gesture.startWorld.y;
    const anchor = gesture.before.values().next().value;
    if (anchor) ({ dx, dy } = magneticSnapDelta(anchor, dx, dy));
    gesture.lastDx = dx;
    gesture.lastDy = dy;
    applyTranslation(gesture.before, dx, dy);
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function finishGroupGesture(event) {
    const gesture = runtime.gesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return false;
    runtime.gesture = null;
    try {
      state()?.el?.modelGraphViewport?.releasePointerCapture?.(event.pointerId);
    } catch {
      // Pointer capture can be released when the SVG subtree is redrawn.
    }
    if (gesture.moved) {
      runtime.suppressClickUntil = performance.now() + 350;
      recordBatch(gesture.before, '複数移動');
    }
    scheduleDecoration();
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function marqueeElement() {
    if (runtime.elements.marquee) return runtime.elements.marquee;
    const element = document.createElement('div');
    element.id = 'vi-multi-selection-marquee';
    element.className = 'vi-multi-selection-marquee';
    element.hidden = true;
    document.body.append(element);
    runtime.elements.marquee = element;
    return element;
  }

  function marqueeRect(startX, startY, endX, endY) {
    return {
      left: Math.min(startX, endX),
      top: Math.min(startY, endY),
      right: Math.max(startX, endX),
      bottom: Math.max(startY, endY),
      width: Math.abs(endX - startX),
      height: Math.abs(endY - startY),
    };
  }

  function updateMarqueeElement(rect) {
    const element = marqueeElement();
    element.hidden = false;
    element.style.left = `${rect.left}px`;
    element.style.top = `${rect.top}px`;
    element.style.width = `${rect.width}px`;
    element.style.height = `${rect.height}px`;
  }

  function beginMarquee(event, viewport) {
    runtime.marquee = {
      pointerId: event.pointerId,
      viewport,
      startX: event.clientX,
      startY: event.clientY,
      endX: event.clientX,
      endY: event.clientY,
      additive: event.ctrlKey || event.metaKey || event.shiftKey,
      moved: false,
    };
    viewport.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function moveMarquee(event) {
    const marquee = runtime.marquee;
    if (!marquee || event.pointerId !== marquee.pointerId) return false;
    marquee.endX = event.clientX;
    marquee.endY = event.clientY;
    const rect = marqueeRect(
      marquee.startX,
      marquee.startY,
      marquee.endX,
      marquee.endY,
    );
    if (!marquee.moved && Math.hypot(rect.width, rect.height) >= 3) {
      marquee.moved = true;
    }
    if (marquee.moved) updateMarqueeElement(rect);
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function objectsInMarquee(rect) {
    const S = state();
    if (!S) return [];
    return [...document.querySelectorAll('#model-graph-svg [data-object-id]')]
      .filter((group) => {
        const item = S.objects.get(group.dataset.objectId);
        if (!item || item.surface !== S.surface) return false;
        if (group.closest('[aria-hidden="true"]')) return false;
        const style = getComputedStyle(group);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const box = group.getBoundingClientRect();
        if (box.width <= 0 || box.height <= 0) return false;
        const centerX = box.left + box.width / 2;
        const centerY = box.top + box.height / 2;
        return centerX >= rect.left
          && centerX <= rect.right
          && centerY >= rect.top
          && centerY <= rect.bottom;
      })
      .map((group) => group.dataset.objectId);
  }

  function finishMarquee(event) {
    const marquee = runtime.marquee;
    if (!marquee || event.pointerId !== marquee.pointerId) return false;
    runtime.marquee = null;
    try {
      marquee.viewport.releasePointerCapture?.(event.pointerId);
    } catch {
      // The pointer can already be released by the browser.
    }
    const element = marqueeElement();
    element.hidden = true;
    element.removeAttribute('style');
    if (marquee.moved) {
      const rect = marqueeRect(
        marquee.startX,
        marquee.startY,
        marquee.endX,
        marquee.endY,
      );
      const ids = objectsInMarquee(rect);
      setSelection(
        marquee.additive ? [...runtime.selectedIds, ...ids] : ids,
        ids.at(-1) || (marquee.additive ? runtime.primaryId : null),
      );
    } else if (!marquee.additive) {
      clearSelection();
    }
    runtime.suppressClickUntil = performance.now() + 250;
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function modifierSelectionPointerDown(event) {
    if (event.button !== 0) return false;
    const listButton = event.target.closest?.('#vi-object-list [data-list-id]');
    const group = event.target.closest?.('#model-graph-svg [data-object-id]');
    const id = listButton?.dataset.listId || group?.dataset.objectId;
    if (!id || !objectExists(id)) return false;
    if (event.shiftKey && listButton) {
      selectListRange(id, { additive: event.ctrlKey || event.metaKey });
    } else if (event.ctrlKey || event.metaKey) {
      toggleSelection(id, { reveal: false });
    } else {
      return false;
    }
    runtime.suppressClickUntil = performance.now() + 350;
    event.preventDefault();
    event.stopImmediatePropagation();
    requestAnimationFrame(() => {
      (listButton || group)?.focus?.({ preventScroll: true });
    });
    return true;
  }

  function handlePointerDown(event) {
    if (!state()?.vi || event.button !== 0) return;
    if (modifierSelectionPointerDown(event)) return;
    const group = event.target.closest?.('#model-graph-svg [data-object-id]');
    const item = group ? state()?.objects.get(group.dataset.objectId) : null;
    if (
      group
      && item
      && runtime.selectedIds.size > 1
      && runtime.selectedIds.has(item.id)
      && !event.target.closest?.('.vi-resize-handle')
    ) {
      beginGroupGesture(event, group, item);
      return;
    }
    const viewport = event.target.closest?.('#model-graph-viewport');
    const interactive = event.target.closest?.(
      '[data-object-id],[data-wire-id],button,input,select,textarea,a',
    );
    if (viewport && !interactive) beginMarquee(event, viewport);
  }

  function handlePointerMove(event) {
    if (runtime.gesture && moveGroupGesture(event)) return;
    if (runtime.marquee) moveMarquee(event);
  }

  function handlePointerUp(event) {
    if (runtime.gesture && finishGroupGesture(event)) return;
    if (runtime.marquee) finishMarquee(event);
  }

  function handleSuppressedClick(event) {
    if (performance.now() >= runtime.suppressClickUntil) return;
    if (!event.target.closest?.('#model-graph-viewport,#vi-object-list')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function moveSelectionBy(dx, dy, source = 'キー移動') {
    const before = beforeMapForRoots();
    if (!before.size) return false;
    const S = state();
    before.forEach((bounds, id) => {
      S.local.set(id, {
        x: bounds.x + dx,
        y: bounds.y + dy,
        width: bounds.width,
        height: bounds.height,
      });
      S.dirty.add(id);
    });
    recordBatch(before, source);
    scheduleRender();
    return true;
  }

  function editingTarget(target) {
    return target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || target?.isContentEditable;
  }

  function handleKeydown(event) {
    if (!state()?.vi) return;
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && event.key.toLowerCase() === 'z') {
      const handled = event.shiftKey ? redoBatch() : undoBatch();
      if (handled) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    if (modifier && event.key.toLowerCase() === 'y') {
      if (redoBatch()) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    if (runtime.selectedIds.size <= 1 || editingTarget(event.target)) return;
    if (modifier && event.key.toLowerCase() === 'c') {
      event.preventDefault();
      event.stopImmediatePropagation();
      void copySummary();
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopImmediatePropagation();
      clearSelection();
      return;
    }
    if (event.altKey || modifier) return;
    const step = event.shiftKey ? 10 : 1;
    const delta = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    }[event.key];
    if (!delta) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    moveSelectionBy(delta[0], delta[1], '複数キー移動');
  }

  function interceptHistoryButton(event) {
    const undo = event.target.closest?.('#vi-undo-layout');
    const redo = event.target.closest?.('#vi-redo-layout');
    if (!undo && !redo) return;
    const handled = undo ? undoBatch() : redoBatch();
    if (!handled) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function reset(reason = 'model-installed') {
    runtime.selectedIds.clear();
    runtime.primaryId = null;
    runtime.rangeAnchorId = null;
    runtime.gesture = null;
    runtime.marquee = null;
    runtime.elements.inspector?.setAttribute('data-reset-reason', reason);
    scheduleDecoration();
  }

  function wrapEditor() {
    const E = editor();
    if (!E || runtime.originalSelect) return false;
    runtime.originalSelect = E.select;
    runtime.originalInstall = E.install;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;

    E.select = function selectWithMultiSelection(id, reveal = false) {
      if (runtime.internalSelect || runtime.applyingBatchHistory) {
        return runtime.originalSelect.call(E, id, reveal);
      }
      const result = runtime.originalSelect.call(E, id, reveal);
      if (state()?.objects.has(id)) {
        runtime.selectedIds = new Set([id]);
        runtime.primaryId = id;
        runtime.rangeAnchorId = id;
      } else {
        runtime.selectedIds.clear();
        runtime.primaryId = null;
        runtime.rangeAnchorId = null;
      }
      scheduleDecoration();
      return result;
    };

    if (typeof runtime.originalInstall === 'function') {
      E.install = function installWithMultiSelectionReset(vi) {
        reset('model-installed');
        return runtime.originalInstall.call(E, vi);
      };
    }

    if (typeof runtime.originalRenderCanvas === 'function') {
      E.renderCanvas = function renderCanvasWithMultiSelection(...args) {
        const result = runtime.originalRenderCanvas.apply(E, args);
        scheduleDecoration();
        return result;
      };
    }

    if (typeof runtime.originalRenderAll === 'function') {
      E.renderAll = function renderAllWithMultiSelection(...args) {
        const result = runtime.originalRenderAll.apply(E, args);
        scheduleDecoration();
        return result;
      };
    }
    return true;
  }

  function install() {
    const E = editor();
    const S = state();
    if (
      runtime.ready
      || !E?.S
      || !S?.el?.modelGraphSvg
      || !enhancements()?.ready
      || !navigationHistory()?.ready
      || !globalThis.VIComponentFit?.ready
      || !globalThis.VISemanticNavigationBridge?.ready
    ) {
      return false;
    }
    runtime.ready = true;
    wrapEditor();
    buildInspector();
    buildStatus();
    marqueeElement();
    window.addEventListener('pointerdown', handlePointerDown, true);
    window.addEventListener('pointermove', handlePointerMove, true);
    window.addEventListener('pointerup', handlePointerUp, true);
    window.addEventListener('pointercancel', handlePointerUp, true);
    window.addEventListener('click', handleSuppressedClick, true);
    window.addEventListener('keydown', handleKeydown, true);
    document.addEventListener('click', interceptHistoryButton, true);
    new MutationObserver(scheduleDecoration).observe(S.el.modelGraphSvg, {
      childList: true,
    });
    const list = S.el.viObjectList || document.querySelector('#vi-object-list');
    if (list) {
      new MutationObserver(scheduleDecoration).observe(list, {
        childList: true,
        subtree: true,
      });
    }
    if (S.selected && S.objects.has(S.selected)) {
      runtime.selectedIds.add(S.selected);
      runtime.primaryId = S.selected;
      runtime.rangeAnchorId = S.selected;
    }
    globalThis.VIMultiSelection = {
      ready: true,
      runtime,
      setSelection,
      clearSelection,
      toggleSelection,
      selectListRange,
      selectedObjects,
      movementRoots,
      selectionBounds,
      selectionSummary,
      summaryText,
      copySummary,
      moveSelectionBy,
      undo: undoBatch,
      redo: redoBatch,
      decorate,
      reset,
    };
    decorate();
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 480) {
      setTimeout(() => waitForEditor(attempt + 1), 25);
      return;
    }
    globalThis.VIMultiSelection = {
      ready: false,
      error: 'multi-selection dependencies did not become ready',
      runtime,
    };
  }

  globalThis.VIMultiSelection = { ready: false, runtime };
  waitForEditor();
})();
