'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const VISUAL_SIZE_PX = 5;
  const HIT_SIZE_PX = 14;
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    observer: null,
    resizeObserver: null,
    originalRenderCanvas: null,
    originalRenderAll: null,
    originalProjectionDecorate: null,
    originalProjectionSchedule: null,
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function projection() {
    return globalThis.VIComponentProjection;
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function setAttribute(element, name, value) {
    const next = String(value);
    if (element.getAttribute(name) !== next) element.setAttribute(name, next);
  }

  function logicalBounds(item) {
    const E = editor();
    return E?.effectiveBounds?.(item) || E?.getBounds?.(item) || null;
  }

  function screenScale(group) {
    const matrix = group.getScreenCTM?.();
    const scaleX = matrix ? Math.hypot(matrix.a, matrix.b) : 1;
    const scaleY = matrix ? Math.hypot(matrix.c, matrix.d) : 1;
    return {
      x: Math.max(0.01, scaleX || 1),
      y: Math.max(0.01, scaleY || 1),
    };
  }

  function projectedCorner(group, item) {
    const logical = logicalBounds(item);
    if (!logical) return null;
    const projectedX = finite(group.dataset.projectedX, logical.x);
    const projectedY = finite(group.dataset.projectedY, logical.y);
    const projectedWidth = finite(group.dataset.projectedWidth, logical.width);
    const projectedHeight = finite(group.dataset.projectedHeight, logical.height);
    return {
      x: projectedX - logical.x + projectedWidth,
      y: projectedY - logical.y + projectedHeight,
    };
  }

  function ensureHitTarget(group, visual) {
    let hit = group.querySelector('.vi-resize-hit-target');
    if (!hit) {
      hit = document.createElementNS(SVG_NS, 'rect');
      hit.classList.add('vi-resize-hit-target', 'vi-resize-handle');
      hit.dataset.resize = 'true';
      hit.setAttribute('fill', 'transparent');
      hit.setAttribute('stroke', 'none');
      hit.setAttribute('pointer-events', 'all');
      hit.setAttribute('aria-label', 'サイズ変更');
    } else {
      hit.classList.add('vi-resize-handle');
    }
    // The projection runtime excludes `.vi-resize-handle` from the scaled
    // component body. Re-parenting here also repairs an older pass that may
    // have moved the transparent target into `.vi-component-geometry`.
    if (hit.parentNode !== group || visual.nextSibling !== hit) {
      group.insertBefore(hit, visual.nextSibling);
    }
    return hit;
  }

  function removeHitTarget(group) {
    group.querySelector('.vi-resize-hit-target')?.remove();
  }

  function compactHandle(group) {
    const S = state();
    const item = S?.objects.get(group.dataset.objectId);
    const visual = group.querySelector(
      ':scope > .vi-resize-handle:not(.vi-resize-hit-target)',
    );
    if (!item || !visual) {
      removeHitTarget(group);
      return;
    }

    const multiCount = globalThis.VIMultiSelection?.runtime?.selectedIds?.size || 0;
    if (multiCount > 1 || !item.resizable || item.category === 'terminal') {
      visual.setAttribute('visibility', 'hidden');
      visual.removeAttribute('data-resize');
      removeHitTarget(group);
      return;
    }

    const corner = projectedCorner(group, item);
    if (!corner) return;
    const scale = screenScale(group);
    const visualWidth = VISUAL_SIZE_PX / scale.x;
    const visualHeight = VISUAL_SIZE_PX / scale.y;
    const hitWidth = HIT_SIZE_PX / scale.x;
    const hitHeight = HIT_SIZE_PX / scale.y;

    // Keep the visible square completely outside the component body. The
    // transparent target overlaps the corner slightly so resizing remains easy.
    const visualX = corner.x;
    const visualY = corner.y;
    const hitCenterX = corner.x + visualWidth / 2;
    const hitCenterY = corner.y + visualHeight / 2;

    visual.classList.add('is-compact-resize-handle');
    visual.setAttribute('visibility', 'visible');
    visual.removeAttribute('data-resize');
    visual.setAttribute('pointer-events', 'none');
    visual.setAttribute('aria-hidden', 'true');
    setAttribute(visual, 'x', visualX);
    setAttribute(visual, 'y', visualY);
    setAttribute(visual, 'width', visualWidth);
    setAttribute(visual, 'height', visualHeight);
    setAttribute(visual, 'rx', Math.min(1.25 / scale.x, visualWidth / 3));

    const hit = ensureHitTarget(group, visual);
    setAttribute(hit, 'x', hitCenterX - hitWidth / 2);
    setAttribute(hit, 'y', hitCenterY - hitHeight / 2);
    setAttribute(hit, 'width', hitWidth);
    setAttribute(hit, 'height', hitHeight);
    hit.dataset.resize = 'true';
    hit.dataset.visibleSizePx = String(VISUAL_SIZE_PX);
    hit.dataset.hitSizePx = String(HIT_SIZE_PX);
    group.dataset.compactResizeHandle = 'true';
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      root.querySelectorAll('[data-object-id]').forEach(compactHandle);
      root.dataset.compactResizeHandles = 'true';
      return true;
    } finally {
      runtime.applying = false;
    }
  }

  function schedule() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        runtime.scheduled = false;
        decorate();
      });
    });
  }

  function patchProjection() {
    const P = projection();
    if (!P?.ready || runtime.originalProjectionDecorate) return false;
    runtime.originalProjectionDecorate = P.decorate;
    runtime.originalProjectionSchedule = P.schedule;
    if (typeof runtime.originalProjectionDecorate === 'function') {
      P.decorate = function decorateWithCompactResizeHandles(...args) {
        const result = runtime.originalProjectionDecorate.apply(P, args);
        decorate();
        return result;
      };
    }
    if (typeof runtime.originalProjectionSchedule === 'function') {
      P.schedule = function scheduleWithCompactResizeHandles(...args) {
        const result = runtime.originalProjectionSchedule.apply(P, args);
        schedule();
        return result;
      };
    }
    return true;
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithCompactResizeHandles(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      schedule();
      return result;
    };
    E.renderAll = function renderAllWithCompactResizeHandles(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      schedule();
      return result;
    };
    return true;
  }

  function install() {
    const root = state()?.el?.modelGraphSvg;
    const viewport = state()?.el?.modelGraphViewport;
    if (
      runtime.ready
      || !root
      || !editor()
      || !projection()?.ready
      || !globalThis.VIComponentFit?.ready
      || !globalThis.VIMultiSelectionPolish?.ready
    ) {
      return false;
    }

    runtime.ready = true;
    patchProjection();
    wrapRenderers();
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.applying) return;
      if (mutations.some((mutation) => (
        mutation.type === 'childList'
        || mutation.attributeName === 'viewBox'
        || mutation.attributeName === 'transform'
        || mutation.attributeName === 'class'
        || mutation.attributeName === 'x'
        || mutation.attributeName === 'y'
        || mutation.attributeName === 'width'
        || mutation.attributeName === 'height'
        || mutation.attributeName?.startsWith('data-projected')
      ))) schedule();
    });
    runtime.observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: [
        'viewBox',
        'transform',
        'class',
        'x',
        'y',
        'width',
        'height',
        'data-projected-x',
        'data-projected-y',
        'data-projected-width',
        'data-projected-height',
      ],
    });
    if (viewport && globalThis.ResizeObserver) {
      runtime.resizeObserver = new ResizeObserver(schedule);
      runtime.resizeObserver.observe(viewport);
      viewport.addEventListener('wheel', schedule, { passive: true });
    }
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      button.addEventListener('click', schedule);
    });

    globalThis.VICompactResizeHandles = {
      ready: true,
      runtime,
      decorate,
      schedule,
      visualSizePx: VISUAL_SIZE_PX,
      hitSizePx: HIT_SIZE_PX,
    };
    projection()?.decorate?.();
    schedule();
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 600) {
      setTimeout(() => waitForEditor(attempt + 1), 25);
      return;
    }
    globalThis.VICompactResizeHandles = {
      ready: false,
      error: 'resize handle dependencies did not become ready',
      runtime,
    };
  }

  globalThis.VICompactResizeHandles = { ready: false, runtime };
  waitForEditor();
})();
