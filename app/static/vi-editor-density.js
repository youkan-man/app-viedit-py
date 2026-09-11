'use strict';

(() => {
  const POLICIES = {
    'front-panel': {
      padding: 56,
      componentTargetShortSide: 28,
      minComponentScale: 0.24,
      maxComponentScale: 0.86,
      fallbackComponentScale: 0.62,
      focusMultiplier: 1.35,
      focusMinScale: 0.48,
      focusMaxScale: 1.35,
    },
    'block-diagram': {
      padding: 64,
      componentTargetShortSide: 24,
      minComponentScale: 0.20,
      maxComponentScale: 0.78,
      fallbackComponentScale: 0.54,
      focusMultiplier: 1.45,
      focusMinScale: 0.44,
      focusMaxScale: 1.25,
    },
  };
  const ABSOLUTE_MIN_SCALE = 0.08;
  const ABSOLUTE_MAX_SCALE = 4;
  const STORAGE_KEY = 'vi-editor-density:v1';
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    currentScale: 1,
    currentMode: 'readable',
    currentJobId: null,
    surfaceViews: new Map(),
    previousViewport: null,
    pendingSurface: null,
    originalRenderAll: null,
    originalSetSurface: null,
    originalSelect: null,
    objectPaneCollapsed: false,
    contextPaneCollapsed: false,
    lastComponentMetrics: null,
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function median(values) {
    const sorted = values
      .filter(Number.isFinite)
      .sort((first, second) => first - second);
    if (!sorted.length) return null;
    const middle = Math.floor(sorted.length / 2);
    if (sorted.length % 2) return sorted[middle];
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function policy(surface = state()?.surface) {
    return POLICIES[surface] || POLICIES['block-diagram'];
  }

  function viewport() {
    const element = state()?.el?.modelGraphViewport;
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 40) return null;
    return { element, rect };
  }

  function boundsFor(item, index = 0) {
    const E = editor();
    const bounds = E?.effectiveBounds?.(item, index) || E?.getBounds?.(item, index);
    if (!bounds) return null;
    const x = finite(bounds.x, NaN);
    const y = finite(bounds.y, NaN);
    const width = Math.max(1, finite(bounds.width, NaN));
    const height = Math.max(1, finite(bounds.height, NaN));
    if (![x, y, width, height].every(Number.isFinite)) return null;
    return { x, y, width, height };
  }

  function filtering() {
    const S = state();
    return Boolean(
      S?.el?.modelGraphQuery?.value?.trim()
      || S?.el?.modelGraphKind?.value,
    );
  }

  function hasRealBounds(item) {
    const S = state();
    return Boolean(
      item
      && item.positioned !== false
      && !item.hidden_by_structure_frame
      && item.surface !== 'block-diagram-inactive'
      && (item.bounds || S?.local?.has(item.id)),
    );
  }

  function currentItems(surface = state()?.surface) {
    const E = editor();
    const S = state();
    if (!E || !S) return [];
    return [...S.objects.values()].filter((item) => (
      item.surface === surface
      && hasRealBounds(item)
      && (S.showTerminals || item.category !== 'terminal')
      && (!filtering() || E.visible?.(item))
    ));
  }

  function isStructure(item) {
    return Boolean(
      item?.visual_kind === 'structure'
      || String(item?.kind || '').startsWith('structure'),
    );
  }

  function componentItems(surface = state()?.surface) {
    const items = currentItems(surface).filter(
      (item) => item.category !== 'terminal',
    );
    if (surface === 'front-panel') {
      const components = items.filter((item) => (
        item.category === 'control' || item.category === 'indicator'
      ));
      return components.length ? components : items;
    }
    const ordinaryNodes = items.filter((item) => (
      item.category === 'node' && !isStructure(item)
    ));
    if (ordinaryNodes.length) return ordinaryNodes;
    const nodes = items.filter((item) => item.category === 'node');
    return nodes.length ? nodes : items;
  }

  function componentRecords(surface = state()?.surface) {
    const all = componentItems(surface)
      .map((item, index) => ({ item, bounds: boundsFor(item, index) }))
      .filter((record) => record.bounds);
    const representative = all.filter(({ bounds }) => {
      const shortSide = Math.min(bounds.width, bounds.height);
      const longSide = Math.max(bounds.width, bounds.height);
      return shortSide >= 10 && shortSide <= 240 && longSide <= 720;
    });
    return representative.length ? representative : all;
  }

  function componentMetrics(surface = state()?.surface) {
    const records = componentRecords(surface);
    const widths = records.map((record) => record.bounds.width);
    const heights = records.map((record) => record.bounds.height);
    const shortSides = records.map((record) => (
      Math.min(record.bounds.width, record.bounds.height)
    ));
    const longSides = records.map((record) => (
      Math.max(record.bounds.width, record.bounds.height)
    ));
    const metrics = {
      surface,
      count: records.length,
      medianWidth: median(widths),
      medianHeight: median(heights),
      medianShortSide: median(shortSides),
      medianLongSide: median(longSides),
    };
    runtime.lastComponentMetrics = metrics;
    return metrics;
  }

  function componentScale(surface = state()?.surface) {
    const settings = policy(surface);
    const metrics = componentMetrics(surface);
    if (!metrics.count || !metrics.medianShortSide) {
      return settings.fallbackComponentScale;
    }
    return clamp(
      settings.componentTargetShortSide / metrics.medianShortSide,
      settings.minComponentScale,
      settings.maxComponentScale,
    );
  }

  function componentScreenMetrics(
    scale = runtime.currentScale,
    surface = state()?.surface,
  ) {
    const metrics = componentMetrics(surface);
    return {
      ...metrics,
      scale,
      medianScreenWidth: metrics.medianWidth == null
        ? null
        : metrics.medianWidth * scale,
      medianScreenHeight: metrics.medianHeight == null
        ? null
        : metrics.medianHeight * scale,
      medianScreenShortSide: metrics.medianShortSide == null
        ? null
        : metrics.medianShortSide * scale,
      medianScreenLongSide: metrics.medianLongSide == null
        ? null
        : metrics.medianLongSide * scale,
    };
  }

  function selectedRecords() {
    const S = state();
    if (!S?.selected) return { items: [], wires: [] };
    const item = S.objects.get(S.selected);
    const wire = S.wires.get(S.selected);
    if (wire) {
      const ids = [
        wire.source_terminal_id,
        wire.source_object_id,
        ...(wire.target_terminal_ids || []),
        ...(wire.target_object_ids || []),
      ].filter(Boolean);
      return {
        items: ids.map((id) => S.objects.get(id)).filter(hasRealBounds),
        wires: [wire],
      };
    }
    if (!item || !hasRealBounds(item)) return { items: [], wires: [] };
    const ids = new Set([
      item.id,
      ...(item.terminal_ids || []),
      ...(item.child_object_ids || []),
    ]);
    const wires = (item.wire_ids || [])
      .map((id) => S.wires.get(id))
      .filter(Boolean);
    wires.forEach((record) => {
      [
        record.source_terminal_id,
        ...(record.target_terminal_ids || []),
      ].filter(Boolean).forEach((id) => ids.add(id));
    });
    return {
      items: [...ids]
        .map((id) => S.objects.get(id))
        .filter(hasRealBounds),
      wires,
    };
  }

  function fitItems(items, surface = state()?.surface) {
    if (!items.length) return [];
    if (surface === 'front-panel') {
      const components = items.filter((item) => (
        item.category === 'control' || item.category === 'indicator'
      ));
      return components.length ? components : items;
    }
    const nodes = items.filter((item) => item.category === 'node');
    return nodes.length ? nodes : items;
  }

  function wireVisibleForItems(wire, itemIds) {
    const endpoints = [
      wire.source_terminal_id,
      wire.source_object_id,
      ...(wire.target_terminal_ids || []),
      ...(wire.target_object_ids || []),
    ].filter(Boolean);
    return endpoints.some((id) => itemIds.has(id));
  }

  function boundedWirePoints(wires, boxes) {
    if (!boxes.length) return [];
    const left = Math.min(...boxes.map((box) => box.x));
    const top = Math.min(...boxes.map((box) => box.y));
    const right = Math.max(...boxes.map((box) => box.x + box.width));
    const bottom = Math.max(...boxes.map((box) => box.y + box.height));
    const width = Math.max(1, right - left);
    const height = Math.max(1, bottom - top);
    const marginX = Math.max(96, width * 0.12);
    const marginY = Math.max(96, height * 0.12);
    return wires.flatMap((wire) => wire.route_points || [])
      .map((point) => ({
        x: finite(point?.x, NaN),
        y: finite(point?.y, NaN),
      }))
      .filter((point) => (
        Number.isFinite(point.x)
        && Number.isFinite(point.y)
        && point.x >= left - marginX
        && point.x <= right + marginX
        && point.y >= top - marginY
        && point.y <= bottom + marginY
      ));
  }

  function contentBounds({ selectionOnly = false } = {}) {
    const S = state();
    if (!S) return null;
    const selected = selectionOnly ? selectedRecords() : null;
    const rawItems = selected?.items || currentItems();
    const items = selectionOnly ? rawItems : fitItems(rawItems);
    const itemIds = new Set();
    items.forEach((item) => {
      itemIds.add(item.id);
      (item.terminal_ids || []).forEach((id) => itemIds.add(id));
      (item.linked_terminal_ids || []).forEach((id) => itemIds.add(id));
    });
    const boxes = items
      .map((item, index) => boundsFor(item, index))
      .filter(Boolean);
    let wires = selected?.wires || [];
    if (!selectionOnly && S.surface === 'block-diagram') {
      wires = [...S.wires.values()].filter(
        (wire) => wireVisibleForItems(wire, itemIds),
      );
    }
    const points = boundedWirePoints(wires, boxes);

    if (!boxes.length && !points.length) return null;
    const xs = [
      ...boxes.flatMap((box) => [box.x, box.x + box.width]),
      ...points.map((point) => point.x),
    ];
    const ys = [
      ...boxes.flatMap((box) => [box.y, box.y + box.height]),
      ...points.map((point) => point.y),
    ];
    const left = Math.min(...xs);
    const top = Math.min(...ys);
    const right = Math.max(...xs);
    const bottom = Math.max(...ys);
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
    };
  }

  function boxFor(bounds, scale, rect) {
    const width = rect.width / scale;
    const height = rect.height / scale;
    const centerX = bounds.x + bounds.width / 2;
    const centerY = bounds.y + bounds.height / 2;
    return {
      x: centerX - width / 2,
      y: centerY - height / 2,
      width,
      height,
    };
  }

  function scaleFor(bounds, mode, rect) {
    const settings = policy();
    const availableWidth = Math.max(80, rect.width - settings.padding * 2);
    const availableHeight = Math.max(80, rect.height - settings.padding * 2);
    const ideal = Math.min(
      availableWidth / Math.max(1, bounds.width),
      availableHeight / Math.max(1, bounds.height),
    );
    if (mode === 'overview') {
      return clamp(ideal, ABSOLUTE_MIN_SCALE, settings.maxComponentScale);
    }
    const readable = componentScale();
    if (mode === 'focus') {
      return clamp(
        Math.max(readable * settings.focusMultiplier, Math.min(ideal, 1)),
        settings.focusMinScale,
        settings.focusMaxScale,
      );
    }
    return readable;
  }

  function lodForScale(scale, mode = runtime.currentMode) {
    const metrics = runtime.lastComponentMetrics || componentMetrics();
    const screenShortSide = metrics.medianShortSide == null
      ? 0
      : metrics.medianShortSide * scale;
    if (mode === 'overview') {
      return scale < 0.45 ? 'overview' : 'compact';
    }
    if (screenShortSide && screenShortSide < 12) return 'overview';
    if (screenShortSide && screenShortSide < 20) return 'compact';
    if (!screenShortSide || screenShortSide <= 48) return 'normal';
    return 'detail';
  }

  function updateControls(scale, mode) {
    const shell = state()?.el?.viEditorShell;
    const status = document.querySelector('#vi-canvas-zoom-status');
    const metrics = componentScreenMetrics(scale);
    if (shell) {
      shell.dataset.viLod = lodForScale(scale, mode);
      shell.dataset.viViewMode = mode;
      shell.dataset.viScale = scale.toFixed(3);
      shell.dataset.viComponentCount = String(metrics.count || 0);
      shell.dataset.viMedianComponentWidth = metrics.medianWidth == null
        ? ''
        : metrics.medianWidth.toFixed(2);
      shell.dataset.viMedianComponentHeight = metrics.medianHeight == null
        ? ''
        : metrics.medianHeight.toFixed(2);
      shell.dataset.viMedianComponentShortSide = metrics.medianShortSide == null
        ? ''
        : metrics.medianShortSide.toFixed(2);
      shell.dataset.viMedianScreenComponentShortSide = (
        metrics.medianScreenShortSide == null
          ? ''
          : metrics.medianScreenShortSide.toFixed(2)
      );
    }
    if (status) {
      status.textContent = `${Math.round(scale * 100)}%`;
      const componentText = metrics.medianScreenShortSide == null
        ? ''
        : `、代表部品短辺 ${Math.round(metrics.medianScreenShortSide)}px`;
      status.title = `VI部品表示倍率 ${Math.round(scale * 100)}%${componentText}`;
    }
    document.querySelectorAll('[data-density-mode]').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.densityMode === mode);
      button.setAttribute(
        'aria-pressed',
        String(button.dataset.densityMode === mode),
      );
    });
    const focus = document.querySelector('#model-graph-focus');
    if (focus) focus.disabled = !state()?.selected;
  }

  function applyBox(box, mode, { remember = true } = {}) {
    const S = state();
    const view = viewport();
    if (!S || !view || !box) return false;
    const safe = {
      x: finite(box.x),
      y: finite(box.y),
      width: Math.max(20, finite(box.width, 640)),
      height: Math.max(20, finite(box.height, 420)),
    };
    runtime.applying = true;
    S.box = safe;
    S.el.modelGraphSvg.setAttribute(
      'viewBox',
      `${safe.x} ${safe.y} ${safe.width} ${safe.height}`,
    );
    const scale = Math.min(
      view.rect.width / safe.width,
      view.rect.height / safe.height,
    );
    runtime.currentScale = scale;
    runtime.currentMode = mode;
    if (mode === 'readable') S.fitBox = { ...safe };
    if (remember && S.surface) {
      runtime.surfaceViews.set(S.surface, {
        box: { ...safe },
        scale,
        mode,
      });
    }
    updateControls(scale, mode);
    runtime.applying = false;
    return true;
  }

  function fit(mode = 'readable') {
    const S = state();
    const view = viewport();
    if (!S || !view) return false;
    const selectionOnly = mode === 'focus';
    const bounds = contentBounds({ selectionOnly })
      || { x: 0, y: 0, width: 640, height: 420 };
    const scale = scaleFor(bounds, mode, view.rect);
    return applyBox(boxFor(bounds, scale, view.rect), mode);
  }

  function rememberCurrentView(mode = runtime.currentMode) {
    const S = state();
    const view = viewport();
    if (!S?.box || !S.surface || !view) return;
    const scale = Math.min(
      view.rect.width / S.box.width,
      view.rect.height / S.box.height,
    );
    runtime.currentScale = scale;
    runtime.currentMode = mode;
    runtime.surfaceViews.set(S.surface, {
      box: { ...S.box },
      scale,
      mode,
    });
    updateControls(scale, mode);
  }

  function restoreSurfaceView(surface, fallbackMode = 'readable') {
    const saved = runtime.surfaceViews.get(surface);
    if (saved) return applyBox(saved.box, saved.mode, { remember: false });
    return fit(fallbackMode);
  }

  function zoomAt(multiplier, clientX = null, clientY = null) {
    const S = state();
    const view = viewport();
    if (!S?.box || !view) return;
    const currentScale = Math.min(
      view.rect.width / S.box.width,
      view.rect.height / S.box.height,
    );
    const nextScale = clamp(
      currentScale * multiplier,
      ABSOLUTE_MIN_SCALE,
      ABSOLUTE_MAX_SCALE,
    );
    const px = clientX == null
      ? 0.5
      : clamp((clientX - view.rect.left) / view.rect.width, 0, 1);
    const py = clientY == null
      ? 0.5
      : clamp((clientY - view.rect.top) / view.rect.height, 0, 1);
    const anchorX = S.box.x + S.box.width * px;
    const anchorY = S.box.y + S.box.height * py;
    const width = view.rect.width / nextScale;
    const height = view.rect.height / nextScale;
    applyBox({
      x: anchorX - width * px,
      y: anchorY - height * py,
      width,
      height,
    }, 'manual');
  }

  function savePanePreference() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        objectPaneCollapsed: runtime.objectPaneCollapsed,
        contextPaneCollapsed: runtime.contextPaneCollapsed,
      }));
    } catch {
      // Storage can be disabled without affecting the editor.
    }
  }

  function loadPanePreference() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      runtime.objectPaneCollapsed = Boolean(value.objectPaneCollapsed);
      runtime.contextPaneCollapsed = Boolean(value.contextPaneCollapsed);
    } catch {
      runtime.objectPaneCollapsed = false;
      runtime.contextPaneCollapsed = false;
    }
  }

  function updatePaneControls() {
    const shell = state()?.el?.viEditorShell;
    shell?.classList.toggle(
      'is-object-pane-collapsed',
      runtime.objectPaneCollapsed,
    );
    document.body.classList.toggle(
      'vi-context-pane-collapsed',
      runtime.contextPaneCollapsed,
    );
    const objectButton = document.querySelector('#vi-toggle-object-pane');
    const contextButton = document.querySelector('#vi-toggle-context-pane');
    if (objectButton) {
      objectButton.classList.toggle('is-active', !runtime.objectPaneCollapsed);
      objectButton.setAttribute('aria-pressed', String(!runtime.objectPaneCollapsed));
      objectButton.textContent = runtime.objectPaneCollapsed ? '一覧を開く' : '一覧';
    }
    if (contextButton) {
      contextButton.classList.toggle('is-active', !runtime.contextPaneCollapsed);
      contextButton.setAttribute('aria-pressed', String(!runtime.contextPaneCollapsed));
      contextButton.textContent = runtime.contextPaneCollapsed ? '詳細を開く' : '詳細';
    }
  }

  function toggleObjectPane() {
    runtime.objectPaneCollapsed = !runtime.objectPaneCollapsed;
    updatePaneControls();
    savePanePreference();
  }

  function toggleContextPane() {
    runtime.contextPaneCollapsed = !runtime.contextPaneCollapsed;
    updatePaneControls();
    savePanePreference();
  }

  function button(id, text, mode = null) {
    const element = document.createElement('button');
    element.id = id;
    element.type = 'button';
    element.className = 'secondary-action button-reset vi-density-control';
    element.textContent = text;
    if (mode) {
      element.dataset.densityMode = mode;
      element.setAttribute('aria-pressed', 'false');
    }
    return element;
  }

  function ensureControls() {
    const actions = document.querySelector('.vi-canvas-actions');
    const fitButton = document.querySelector('#model-graph-fit');
    if (!actions || !fitButton) return false;
    fitButton.textContent = '適正';
    fitButton.title = 'VIコンポーネントの画面上サイズを基準に表示する';
    fitButton.classList.add('vi-density-control');
    fitButton.dataset.densityMode = 'readable';
    fitButton.setAttribute('aria-pressed', 'false');

    if (!document.querySelector('#model-graph-overview')) {
      const overview = button('model-graph-overview', '全体', 'overview');
      overview.title = 'VI全体を確認する低倍率の俯瞰表示';
      fitButton.after(overview);
    }
    if (!document.querySelector('#model-graph-focus')) {
      const focus = button('model-graph-focus', '選択', 'focus');
      focus.title = '選択コンポーネントと接続へフォーカス';
      document.querySelector('#model-graph-overview').after(focus);
    }
    document.querySelector('#vi-zoom-status')?.remove();
    if (!document.querySelector('#vi-canvas-zoom-status')) {
      const status = document.createElement('span');
      status.id = 'vi-canvas-zoom-status';
      status.className = 'vi-zoom-status';
      status.textContent = '—';
      document.querySelector('#model-graph-zoom-in').after(status);
    }
    if (!document.querySelector('#vi-toggle-object-pane')) {
      const objectToggle = button('vi-toggle-object-pane', '一覧');
      objectToggle.title = 'オブジェクト一覧の表示切替';
      actions.prepend(objectToggle);
    }
    if (!document.querySelector('#vi-toggle-context-pane')) {
      const contextToggle = button('vi-toggle-context-pane', '詳細');
      contextToggle.title = '選択詳細ペインの表示切替';
      document.querySelector('#vi-toggle-object-pane').after(contextToggle);
    }
    updatePaneControls();
    return true;
  }

  function stop(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function bindCapture(element, type, handler) {
    if (!element || element.dataset.densityBound?.includes(type)) return;
    const values = new Set((element.dataset.densityBound || '').split(' ').filter(Boolean));
    values.add(type);
    element.dataset.densityBound = [...values].join(' ');
    element.addEventListener(type, handler, true);
  }

  function bindControls() {
    bindCapture(document.querySelector('#model-graph-fit'), 'click', (event) => {
      stop(event);
      fit('readable');
    });
    bindCapture(document.querySelector('#model-graph-overview'), 'click', (event) => {
      stop(event);
      fit('overview');
    });
    bindCapture(document.querySelector('#model-graph-focus'), 'click', (event) => {
      stop(event);
      fit('focus');
    });
    bindCapture(document.querySelector('#model-graph-zoom-in'), 'click', (event) => {
      stop(event);
      zoomAt(1.2);
    });
    bindCapture(document.querySelector('#model-graph-zoom-out'), 'click', (event) => {
      stop(event);
      zoomAt(1 / 1.2);
    });
    bindCapture(document.querySelector('#vi-toggle-object-pane'), 'click', (event) => {
      stop(event);
      toggleObjectPane();
    });
    bindCapture(document.querySelector('#vi-toggle-context-pane'), 'click', (event) => {
      stop(event);
      toggleContextPane();
    });

    const viewportElement = state()?.el?.modelGraphViewport;
    bindCapture(viewportElement, 'wheel', (event) => {
      stop(event);
      zoomAt(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX, event.clientY);
    });
    bindCapture(viewportElement, 'dblclick', (event) => {
      if (event.target.closest?.('.vi-object,.vi-wire-group')) return;
      stop(event);
      fit('readable');
    });
    viewportElement?.addEventListener('pointerup', () => {
      requestAnimationFrame(() => rememberCurrentView('manual'));
    });
    viewportElement?.addEventListener('pointercancel', () => {
      requestAnimationFrame(() => rememberCurrentView('manual'));
    });
  }

  function syncJob() {
    const jobId = state()?.job?.job_id || null;
    if (jobId === runtime.currentJobId) return;
    runtime.currentJobId = jobId;
    runtime.surfaceViews.clear();
    runtime.currentMode = 'readable';
    runtime.currentScale = 1;
    runtime.lastComponentMetrics = null;
  }

  function scheduleView(action) {
    runtime.pendingSurface = action;
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      runtime.scheduled = false;
      const pending = runtime.pendingSurface;
      runtime.pendingSurface = null;
      if (pending === 'fit') fit('readable');
      else if (pending === 'restore') restoreSurfaceView(state()?.surface);
      else {
        const saved = runtime.surfaceViews.get(state()?.surface);
        if (saved) applyBox(saved.box, saved.mode, { remember: false });
        else if (state()?.vi) fit('readable');
      }
    });
  }

  function wrapEditor() {
    const E = editor();
    if (!E || runtime.originalRenderAll) return;
    runtime.originalRenderAll = E.renderAll;
    runtime.originalSetSurface = E.setSurface;
    runtime.originalSelect = E.select;

    if (typeof runtime.originalRenderAll === 'function') {
      E.renderAll = function renderAllWithDensity(fitRequested = false) {
        syncJob();
        runtime.originalRenderAll.call(E, false);
        scheduleView(fitRequested ? 'fit' : null);
      };
    }

    if (typeof runtime.originalSetSurface === 'function') {
      E.setSurface = function setSurfaceWithDensity(surface, fitRequested = true) {
        if (surface === state()?.surface) {
          runtime.originalSetSurface.call(E, surface, false);
          scheduleView(fitRequested ? 'fit' : 'restore');
          return;
        }
        rememberCurrentView();
        runtime.originalSetSurface.call(E, surface, false);
        scheduleView(runtime.surfaceViews.has(surface) && !fitRequested ? 'restore' : 'fit');
      };
    }

    if (typeof runtime.originalSelect === 'function') {
      E.select = function selectWithDensity(id, reveal = false) {
        const S = state();
        const item = S?.objects.get(id);
        const wire = S?.wires.get(id);
        const targetSurface = item?.surface || (wire ? 'block-diagram' : S?.surface);
        const changedSurface = Boolean(targetSurface && targetSurface !== S?.surface);
        if (changedSurface) rememberCurrentView();
        runtime.originalSelect.call(E, id, reveal);
        if (changedSurface) {
          scheduleView(runtime.surfaceViews.has(targetSurface) ? 'restore' : 'fit');
        } else {
          updateControls(runtime.currentScale, runtime.currentMode);
        }
      };
    }
  }

  function preserveScaleOnResize(entries) {
    const entry = entries[0];
    const S = state();
    if (!entry || !S?.box || runtime.applying) return;
    const rect = entry.target.getBoundingClientRect();
    const previous = runtime.previousViewport;
    runtime.previousViewport = { width: rect.width, height: rect.height };
    if (
      !previous
      || Math.abs(previous.width - rect.width) < 1
        && Math.abs(previous.height - rect.height) < 1
    ) {
      return;
    }
    const scale = runtime.currentScale || Math.min(
      previous.width / S.box.width,
      previous.height / S.box.height,
    );
    const centerX = S.box.x + S.box.width / 2;
    const centerY = S.box.y + S.box.height / 2;
    const width = rect.width / scale;
    const height = rect.height / scale;
    applyBox({
      x: centerX - width / 2,
      y: centerY - height / 2,
      width,
      height,
    }, runtime.currentMode);
  }

  function install() {
    const E = editor();
    const S = E?.S;
    if (runtime.ready || !S?.el?.modelGraphViewport || typeof E.renderAll !== 'function') {
      return false;
    }
    runtime.ready = true;
    loadPanePreference();
    ensureControls();
    bindControls();
    wrapEditor();

    const observer = new MutationObserver(() => {
      ensureControls();
      updateControls(runtime.currentScale, runtime.currentMode);
    });
    observer.observe(S.el.modelGraphSvg, { childList: true, subtree: true });
    new ResizeObserver(preserveScaleOnResize).observe(S.el.modelGraphViewport);
    runtime.previousViewport = (() => {
      const rect = S.el.modelGraphViewport.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    })();

    globalThis.VICanvasDensity = {
      ready: true,
      runtime,
      POLICIES,
      contentBounds,
      componentItems,
      componentMetrics,
      componentScale,
      componentScreenMetrics,
      scaleFor,
      fit,
      zoomAt,
      applyBox,
      rememberCurrentView,
      toggleObjectPane,
      toggleContextPane,
    };
    if (S.vi) scheduleView('fit');
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 320) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VICanvasDensity = { ready: false, runtime, POLICIES };
  waitForEditor();
})();
