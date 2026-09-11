'use strict';

(() => {
  const runtime = {
    ready: false,
    preparing: false,
    scheduled: false,
    observer: null,
    originalRenderCanvas: null,
    originalRenderAll: null,
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function logicalBounds(item, index = 0) {
    const E = editor();
    return E?.effectiveBounds?.(item, index)
      || E?.getBounds?.(item, index)
      || null;
  }

  function isFrontPanelContainer(item) {
    if (item?.surface !== 'front-panel') return false;
    const kind = [
      item.visual_kind,
      item.kind,
      item.class_name,
      item.data_type,
    ].filter(Boolean).join(' ').toLowerCase();
    return item.visual_kind === 'cluster'
      || item.visual_kind === 'array'
      || kind.includes('cluster-control')
      || kind.includes('cluster-indicator')
      || kind.includes('array-control')
      || kind.includes('array-indicator');
  }

  function markSemanticContainers() {
    const S = state();
    if (!S) return;
    S.objects.forEach((item) => {
      if (!isFrontPanelContainer(item)) return;
      item.is_container = true;
      item.component_projection_role = 'native-container';
    });
  }

  function setAttribute(element, name, value) {
    const next = String(value);
    if (element.getAttribute(name) !== next) element.setAttribute(name, next);
  }

  function normalizeCanonicalBodies() {
    const S = state();
    const root = S?.el?.modelGraphSvg;
    if (!S || !root) return;
    root.querySelectorAll('[data-object-id]').forEach((group) => {
      const item = S.objects.get(group.dataset.objectId);
      const bounds = logicalBounds(item);
      const body = group.querySelector([
        '.vi-front-panel-body',
        '.vi-block-node-body',
        '.vi-terminal-body',
      ].join(','));
      if (!item || !bounds || !body) return;
      setAttribute(body, 'x', 0);
      setAttribute(body, 'y', 0);
      setAttribute(body, 'width', bounds.width);
      setAttribute(body, 'height', bounds.height);
      body.dataset.nativeLogicalBody = 'true';
    });
  }

  function prepare() {
    if (runtime.preparing) return false;
    const S = state();
    if (!S?.vi) return false;
    runtime.preparing = true;
    try {
      markSemanticContainers();
      // These decorators create the LabVIEW-like body geometry. They must run
      // before the projection runtime wraps that geometry in a scaled group;
      // otherwise their insertBefore references can point into the wrapper.
      globalThis.VIRealism?.decorate?.();
      normalizeCanonicalBodies();
      globalThis.VIReadability?.decorate?.();
      return true;
    } finally {
      runtime.preparing = false;
    }
  }

  function schedule() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      runtime.scheduled = false;
      if (runtime.preparing) {
        schedule();
        return;
      }
      normalizeCanonicalBodies();
    });
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithNativeComponentPrimer(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      prepare();
      return result;
    };
    E.renderAll = function renderAllWithNativeComponentPrimer(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      prepare();
      return result;
    };
    return true;
  }

  function install() {
    const E = editor();
    const root = state()?.el?.modelGraphSvg;
    if (
      runtime.ready
      || !E
      || !root
      || !globalThis.VIRealism?.ready
      || !globalThis.VIReadability?.ready
    ) return false;
    runtime.ready = true;
    wrapRenderers();
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.preparing) return;
      const relevant = mutations.some((mutation) => (
        mutation.type === 'childList'
        || mutation.target?.matches?.([
          '.vi-front-panel-body',
          '.vi-block-node-body',
          '.vi-terminal-body',
        ].join(','))
      ));
      if (relevant) schedule();
    });
    runtime.observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['x', 'y', 'width', 'height'],
    });
    prepare();
    globalThis.VIComponentPrimer = {
      ready: true,
      runtime,
      prepare,
      schedule,
      markSemanticContainers,
      normalizeCanonicalBodies,
      isFrontPanelContainer,
    };
    return true;
  }

  function waitForDecorators(attempt = 0) {
    if (install()) return;
    if (attempt < 360) {
      setTimeout(() => waitForDecorators(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentPrimer = {
      ready: false,
      error: 'native component decorators did not become ready',
      runtime,
    };
  }

  globalThis.VIComponentPrimer = { ready: false, runtime };
  waitForDecorators();
})();
