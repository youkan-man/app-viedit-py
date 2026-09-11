'use strict';

(() => {
  const runtime = {
    ready: false,
    preparing: false,
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

  function normalizeCanonicalBodies() {
    const S = state();
    const root = S?.el?.modelGraphSvg;
    if (!S || !root) return;
    root.querySelectorAll('[data-object-id]').forEach((group) => {
      const item = S.objects.get(group.dataset.objectId);
      const bounds = logicalBounds(item);
      const body = group.querySelector([
        ':scope > .vi-front-panel-body',
        ':scope > .vi-block-node-body',
        ':scope > .vi-terminal-body',
      ].join(','));
      if (!item || !bounds || !body) return;
      body.setAttribute('x', '0');
      body.setAttribute('y', '0');
      body.setAttribute('width', String(bounds.width));
      body.setAttribute('height', String(bounds.height));
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
    if (
      runtime.ready
      || !E
      || !globalThis.VIRealism?.ready
      || !globalThis.VIReadability?.ready
    ) return false;
    runtime.ready = true;
    wrapRenderers();
    prepare();
    globalThis.VIComponentPrimer = {
      ready: true,
      runtime,
      prepare,
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
