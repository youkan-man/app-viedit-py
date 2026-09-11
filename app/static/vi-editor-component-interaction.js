'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: false,
    applying: false,
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

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function logicalBounds(item) {
    const E = editor();
    return E?.effectiveBounds?.(item) || E?.getBounds?.(item) || null;
  }

  function projectedBounds(group) {
    const x = finite(group.dataset.projectedX, NaN);
    const y = finite(group.dataset.projectedY, NaN);
    const width = finite(group.dataset.projectedWidth, NaN);
    const height = finite(group.dataset.projectedHeight, NaN);
    if (![x, y, width, height].every(Number.isFinite)) return null;
    if (width <= 0 || height <= 0) return null;
    return { x, y, width, height };
  }

  function ensureHitTarget(group) {
    const item = state()?.objects.get(group.dataset.objectId);
    const logical = logicalBounds(item);
    const projected = projectedBounds(group);
    if (!item || !logical || !projected) return;

    const factorX = finite(group.dataset.componentScaleX, 1);
    const factorY = finite(group.dataset.componentScaleY, 1);
    const projectedBody = factorX < 0.999 || factorY < 0.999;
    const needed = projectedBody
      || item.category === 'terminal'
      || projected.width < 18
      || projected.height < 18;
    let target = group.querySelector(':scope > .vi-component-hit-target');
    if (!needed) {
      target?.remove();
      return;
    }
    if (!target) {
      target = document.createElementNS(SVG_NS, 'rect');
      target.classList.add('vi-component-hit-target');
      target.setAttribute('fill', 'transparent');
      target.setAttribute('stroke', 'none');
      target.setAttribute('pointer-events', 'all');
      group.insertBefore(target, group.firstChild);
    }
    const width = Math.max(16, projected.width);
    const height = Math.max(16, projected.height);
    target.setAttribute(
      'x',
      String(projected.x - logical.x - (width - projected.width) / 2),
    );
    target.setAttribute(
      'y',
      String(projected.y - logical.y - (height - projected.height) / 2),
    );
    target.setAttribute('width', String(width));
    target.setAttribute('height', String(height));
    target.dataset.projectedBodyTarget = projectedBody ? 'true' : 'minimum-size';
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      root.querySelectorAll('[data-object-id][data-projected-width]')
        .forEach(ensureHitTarget);
      root.dataset.componentInteraction = 'true';
      return true;
    } finally {
      runtime.applying = false;
    }
  }

  function schedule() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      runtime.scheduled = false;
      decorate();
    });
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithProjectedHitTargets(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      decorate();
      return result;
    };
    E.renderAll = function renderAllWithProjectedHitTargets(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      decorate();
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
      || !globalThis.VIComponentProjection?.ready
    ) return false;
    runtime.ready = true;
    wrapRenderers();
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.applying) return;
      if (mutations.some(
        (mutation) => mutation.addedNodes.length || mutation.removedNodes.length,
      )) {
        schedule();
      }
    });
    runtime.observer.observe(root, { childList: true });
    globalThis.VIComponentInteraction = {
      ready: true,
      runtime,
      decorate,
      schedule,
    };
    decorate();
    return true;
  }

  function waitForProjection(attempt = 0) {
    if (install()) return;
    if (attempt < 360) {
      setTimeout(() => waitForProjection(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentInteraction = {
      ready: false,
      error: 'component projection did not become ready',
      runtime,
    };
  }

  globalThis.VIComponentInteraction = { ready: false, runtime };
  waitForProjection();
})();
