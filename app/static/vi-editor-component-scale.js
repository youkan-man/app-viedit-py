'use strict';

(() => {
  const POLICIES = {
    'front-panel': {
      minScale: 1,
      maxScale: 1.45,
      targetWidth: 96,
      targetHeight: 38,
      paddingPx: 42,
    },
    'block-diagram': {
      minScale: 1,
      maxScale: 1.35,
      targetWidth: 48,
      targetHeight: 38,
      paddingPx: 42,
    },
  };

  const runtime = {
    ready: false,
    wrapped: false,
    originalFit: null,
    originalInstall: null,
    scheduled: false,
    initializedViews: new Set(),
    metrics: new Map(),
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function density() {
    return globalThis.VICanvasDensity;
  }

  function state() {
    return editor()?.S;
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function median(values) {
    const sorted = values
      .map(Number)
      .filter((value) => Number.isFinite(value) && value > 0)
      .sort((first, second) => first - second);
    if (!sorted.length) return 0;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[middle]
      : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function effectiveBounds(item) {
    const E = editor();
    const bounds = E?.effectiveBounds?.(item)
      || E?.getBounds?.(item)
      || item?.bounds;
    if (!bounds) return null;
    const value = {
      x: finite(bounds.x, Number.NaN),
      y: finite(bounds.y, Number.NaN),
      width: finite(bounds.width, Number.NaN),
      height: finite(bounds.height, Number.NaN),
    };
    if (
      !Number.isFinite(value.x)
      || !Number.isFinite(value.y)
      || !Number.isFinite(value.width)
      || !Number.isFinite(value.height)
      || value.width <= 0
      || value.height <= 0
    ) return null;
    return value;
  }

  function isFallbackPosition(item) {
    const source = String(
      item?.position_source
      || item?.positioning_source
      || item?.bounds?.source
      || '',
    ).toLowerCase();
    return Boolean(
      item?.fallback_positioned
      || item?.synthetic_position
      || item?.positioned === false
      || source.includes('fallback')
      || source.includes('synthetic')
    );
  }

  function eligibleItem(item, surface) {
    if (!item || item.surface !== surface) return false;
    if (item.hidden_by_structure_frame || item.surface === 'block-diagram-inactive') {
      return false;
    }
    if (isFallbackPosition(item) || !effectiveBounds(item)) return false;
    if (surface === 'front-panel') {
      return item.category === 'control' || item.category === 'indicator';
    }
    return item.category === 'node';
  }

  function representativeItems(surface) {
    const S = state();
    if (!S) return [];
    return [...S.objects.values()].filter((item) => eligibleItem(item, surface));
  }

  function contentBounds(items) {
    const boxes = items.map(effectiveBounds).filter(Boolean);
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

  function representativeMetrics(surface, items) {
    const policy = POLICIES[surface] || POLICIES['block-diagram'];
    const boxes = items.map(effectiveBounds).filter(Boolean);
    const medianWidth = median(boxes.map((box) => box.width));
    const medianHeight = median(boxes.map((box) => box.height));
    const widthScale = medianWidth > 0 ? policy.targetWidth / medianWidth : 1;
    const heightScale = medianHeight > 0 ? policy.targetHeight / medianHeight : 1;
    const scale = clamp(
      Math.max(policy.minScale, widthScale, heightScale),
      policy.minScale,
      policy.maxScale,
    );
    return {
      count: boxes.length,
      medianWidth,
      medianHeight,
      scale,
      screenMedianWidth: medianWidth * scale,
      screenMedianHeight: medianHeight * scale,
    };
  }

  function viewKey() {
    const S = state();
    return `${S?.job?.job_id || 'unloaded'}::${S?.surface || 'unknown'}`;
  }

  function readableBox(surface, scale, bounds) {
    const S = state();
    const viewport = S?.el?.modelGraphViewport;
    if (!viewport || !bounds) return null;
    const rect = viewport.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    const width = rect.width / scale;
    const height = rect.height / scale;
    const padding = (POLICIES[surface]?.paddingPx || 42) / scale;
    const availableWidth = Math.max(1, width - padding * 2);
    const availableHeight = Math.max(1, height - padding * 2);

    let x = bounds.x - padding;
    let y = bounds.y - padding;
    if (bounds.width < availableWidth) {
      x = bounds.x + bounds.width / 2 - width / 2;
    }
    if (bounds.height < availableHeight) {
      y = bounds.y + bounds.height / 2 - height / 2;
    }
    return { x, y, width, height };
  }

  function updateStatus(metrics) {
    const S = state();
    const status = document.querySelector('#vi-canvas-zoom-status');
    if (status) {
      status.textContent = `${Math.round(metrics.scale * 100)}% · 部品 ${Math.round(metrics.screenMedianWidth)}×${Math.round(metrics.screenMedianHeight)}px`;
      status.title = '適正表示はVIコンポーネントの画面上サイズを基準にしています。';
    }
    const shell = document.querySelector('#vi-editor-shell');
    if (shell) {
      shell.dataset.viComponentScale = metrics.scale.toFixed(4);
      shell.dataset.viComponentMedianWidth = metrics.screenMedianWidth.toFixed(2);
      shell.dataset.viComponentMedianHeight = metrics.screenMedianHeight.toFixed(2);
      shell.dataset.viFitBasis = 'component-screen-size';
    }
    if (S?.el?.modelGraphSvg) {
      S.el.modelGraphSvg.dataset.viFitBasis = 'component-screen-size';
    }
  }

  function fitReadable({ remember = true, initialize = false } = {}) {
    const S = state();
    const D = density();
    if (!S?.vi || !D?.ready) return false;
    const surface = S.surface;
    const items = representativeItems(surface);
    const bounds = contentBounds(items);
    const metrics = representativeMetrics(surface, items);
    const box = readableBox(surface, metrics.scale, bounds);
    if (!items.length || !box) {
      return runtime.originalFit?.call(D, 'readable') ?? false;
    }

    if (typeof D.applyBox === 'function') {
      D.applyBox(box, 'readable', { remember });
    } else {
      S.box = { ...box };
      S.el.modelGraphSvg.setAttribute(
        'viewBox',
        `${box.x} ${box.y} ${box.width} ${box.height}`,
      );
    }
    const value = {
      ...metrics,
      surface,
      box,
      initialize,
      fitBasis: 'component-screen-size',
    };
    runtime.metrics.set(viewKey(), value);
    runtime.initializedViews.add(viewKey());
    updateStatus(value);
    document.dispatchEvent(new CustomEvent('vi-component-scale-fit', {
      detail: value,
    }));
    return true;
  }

  function fit(mode = 'readable', ...args) {
    const normalized = String(mode || 'readable').toLowerCase();
    if (['readable', 'fit', '適正'].includes(normalized)) {
      return fitReadable();
    }
    return runtime.originalFit?.call(density(), mode, ...args) ?? false;
  }

  function scheduleInitialFit({ force = false } = {}) {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        runtime.scheduled = false;
        if (!state()?.vi) return;
        if (!force && runtime.initializedViews.has(viewKey())) return;
        fitReadable({ initialize: true });
      });
    });
  }

  function wrapDensity() {
    const D = density();
    if (!D?.ready || runtime.wrapped) return false;
    runtime.wrapped = true;
    runtime.originalFit = D.fit;
    D.fit = fit;
    return true;
  }

  function wrapInstall() {
    const E = editor();
    if (!E || runtime.originalInstall) return false;
    runtime.originalInstall = E.install;
    E.install = function installWithComponentScale(vi) {
      const previousJob = jobId();
      const result = runtime.originalInstall.call(E, vi);
      if (previousJob !== jobId()) runtime.initializedViews.clear();
      scheduleInitialFit({ force: true });
      return result;
    };
    return true;
  }

  function jobId() {
    return String(state()?.job?.job_id || 'unloaded');
  }

  function interceptFitButton(event) {
    const button = event.target.closest?.('#model-graph-fit');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    fitReadable();
  }

  function bindSurfaceInitialization() {
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      button.addEventListener('click', () => {
        requestAnimationFrame(() => scheduleInitialFit());
      });
    });
  }

  function installStyles() {
    if (document.querySelector('link[data-vi-component-scale]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/semantic-component-scale.css?v=1';
    link.dataset.viComponentScale = '';
    document.head.appendChild(link);
  }

  function install() {
    if (
      runtime.ready
      || !editor()
      || !density()?.ready
      || !document.querySelector('#model-graph-viewport')
    ) return false;
    runtime.ready = true;
    installStyles();
    wrapDensity();
    wrapInstall();
    bindSurfaceInitialization();
    document.addEventListener('click', interceptFitButton, true);
    document.addEventListener('vi-structure-frame-changed', () => {
      runtime.initializedViews.delete(viewKey());
      scheduleInitialFit();
    });
    globalThis.VIComponentScale = {
      ready: true,
      runtime,
      policies: POLICIES,
      fit,
      fitReadable,
      representativeItems,
      representativeMetrics,
      contentBounds,
      readableBox,
    };
    scheduleInitialFit({ force: true });
    return true;
  }

  function waitForDensity(attempt = 0) {
    if (install()) return;
    if (attempt < 400) setTimeout(() => waitForDensity(attempt + 1), 25);
  }

  globalThis.VIComponentScale = { ready: false, runtime };
  waitForDensity();
})();
