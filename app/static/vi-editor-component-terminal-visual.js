'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    observer: null,
    originalProjectBounds: null,
    originalDecorate: null,
    originalSchedule: null,
    originalRenderCanvas: null,
    originalRenderAll: null,
  };

  function projection() {
    return globalThis.VIComponentProjection;
  }

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

  function logicalBounds(item, index = 0) {
    const E = editor();
    return E?.effectiveBounds?.(item, index)
      || E?.getBounds?.(item, index)
      || null;
  }

  function owner(item) {
    const S = state();
    const id = item?.owner_object_id
      || item?.bounds?.relative_to_object_id
      || item?.parent_object_id
      || null;
    return id ? S?.objects.get(id) || null : null;
  }

  function isStructure(item) {
    const value = owner(item);
    const kind = [
      value?.visual_kind,
      value?.kind,
      value?.class_name,
    ].filter(Boolean).join(' ').toLowerCase();
    return value?.visual_kind === 'structure'
      || value?.structure_frames?.length > 0
      || kind.includes('structure');
  }

  function terminalSize(item) {
    return isStructure(item) ? 10 : 8;
  }

  function cappedProjectBounds(item, suppliedBounds = null, stack = new Set()) {
    const P = projection();
    const projected = runtime.originalProjectBounds?.(
      item,
      suppliedBounds,
      stack,
    );
    if (!projected || item?.category !== 'terminal') return projected;
    const logical = suppliedBounds || logicalBounds(item);
    if (!logical) return projected;
    const size = terminalSize(item);
    const centerX = finite(projected.x) + finite(projected.width) / 2;
    const centerY = finite(projected.y) + finite(projected.height) / 2;
    return {
      ...projected,
      x: centerX - size / 2,
      y: centerY - size / 2,
      width: size,
      height: size,
      factor_x: size / Math.max(1, finite(logical.width, 1)),
      factor_y: size / Math.max(1, finite(logical.height, 1)),
      source: `${projected.source || 'terminal'}:compact-port`,
      terminal_visual_size: size,
      projection_runtime: P?.ready ? 'component-projection' : 'fallback',
    };
  }

  function setAttribute(element, name, value) {
    const next = String(value);
    if (element.getAttribute(name) !== next) element.setAttribute(name, next);
  }

  function moveOverlay(element, translateX, translateY) {
    if (!element.dataset.componentBaseTransform) {
      element.dataset.componentBaseTransform = element.getAttribute('transform') || '';
    }
    const base = element.dataset.componentBaseTransform;
    const shift = Math.abs(translateX) > 0.01 || Math.abs(translateY) > 0.01
      ? `translate(${translateX} ${translateY})`
      : '';
    const value = `${shift} ${base}`.trim();
    if (value) setAttribute(element, 'transform', value);
    else element.removeAttribute('transform');
  }

  function ensureHitTarget(group, logical, projected) {
    let target = group.querySelector(':scope > .vi-component-hit-target');
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
    setAttribute(
      target,
      'x',
      projected.x - logical.x - (width - projected.width) / 2,
    );
    setAttribute(
      target,
      'y',
      projected.y - logical.y - (height - projected.height) / 2,
    );
    setAttribute(target, 'width', width);
    setAttribute(target, 'height', height);
    target.dataset.projectedBodyTarget = 'compact-terminal-port';
  }

  function applyTerminal(group) {
    const item = state()?.objects.get(group.dataset.objectId);
    if (item?.category !== 'terminal') return;
    const logical = logicalBounds(item);
    const projected = cappedProjectBounds(item, logical);
    const wrapper = group.querySelector(':scope > .vi-component-geometry');
    if (!logical || !projected || !wrapper) return;
    const translateX = projected.x - logical.x;
    const translateY = projected.y - logical.y;
    setAttribute(
      wrapper,
      'transform',
      `translate(${translateX} ${translateY}) scale(${projected.factor_x} ${projected.factor_y})`,
    );
    wrapper.dataset.projectionSource = projected.source;
    group.dataset.componentScaleX = projected.factor_x.toFixed(4);
    group.dataset.componentScaleY = projected.factor_y.toFixed(4);
    group.dataset.projectedX = projected.x.toFixed(3);
    group.dataset.projectedY = projected.y.toFixed(3);
    group.dataset.projectedWidth = projected.width.toFixed(3);
    group.dataset.projectedHeight = projected.height.toFixed(3);
    group.dataset.projectionSource = projected.source;
    group.dataset.terminalVisualSize = String(projected.terminal_visual_size);
    group.classList.add('has-compact-terminal-port');
    group.querySelectorAll([
      ':scope > .vi-object-label',
      ':scope > .vi-terminal-caption',
      ':scope > .vi-cluster-count',
      ':scope > .vi-structure-frame-badge',
    ].join(',')).forEach((overlay) => {
      moveOverlay(overlay, translateX, translateY);
    });
    const handle = group.querySelector(':scope > .vi-resize-handle');
    if (handle) {
      setAttribute(handle, 'x', translateX + projected.width - 7);
      setAttribute(handle, 'y', translateY + projected.height - 7);
    }
    ensureHitTarget(group, logical, projected);
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      root.querySelectorAll('[data-object-id]').forEach(applyTerminal);
      root.dataset.compactTerminalPorts = 'true';
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
        projection()?.decorate?.();
      });
    });
  }

  function patchProjection() {
    const P = projection();
    if (!P?.ready || runtime.originalProjectBounds) return false;
    const coordinate = globalThis.VIComponentCoordinateSpace;
    runtime.originalProjectBounds = P.projectBounds;
    runtime.originalDecorate = P.decorate;
    runtime.originalSchedule = P.schedule;
    P.projectBounds = cappedProjectBounds;
    P.decorate = function decorateWithCompactTerminals(...args) {
      const result = runtime.originalDecorate?.apply(P, args);
      decorate();
      return result;
    };
    P.schedule = schedule;
    if (coordinate?.ready) {
      coordinate.projectBounds = cappedProjectBounds;
      coordinate.decorate = decorate;
      coordinate.schedule = schedule;
    }
    return true;
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithCompactTerminalPorts(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      projection()?.decorate?.();
      return result;
    };
    E.renderAll = function renderAllWithCompactTerminalPorts(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      projection()?.decorate?.();
      return result;
    };
    return true;
  }

  function install() {
    const P = projection();
    const root = state()?.el?.modelGraphSvg;
    if (
      runtime.ready
      || !P?.ready
      || !globalThis.VIComponentCoordinateSpace?.ready
      || !root
      || !editor()
    ) return false;
    runtime.ready = true;
    globalThis.VIComponentCoordinateSpace.runtime?.observer?.disconnect?.();
    patchProjection();
    wrapRenderers();
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.applying) return;
      if (mutations.some(
        (mutation) => mutation.addedNodes.length || mutation.removedNodes.length,
      )) schedule();
    });
    runtime.observer.observe(root, { childList: true, subtree: true });
    globalThis.VIComponentTerminalVisual = {
      ready: true,
      runtime,
      terminalSize,
      projectBounds: cappedProjectBounds,
      decorate,
      schedule,
    };
    projection()?.decorate?.();
    return true;
  }

  function waitForCoordinateSpace(attempt = 0) {
    if (install()) return;
    if (attempt < 360) {
      setTimeout(() => waitForCoordinateSpace(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentTerminalVisual = {
      ready: false,
      error: 'coordinate-space projection did not become ready',
      runtime,
    };
  }

  globalThis.VIComponentTerminalVisual = { ready: false, runtime };
  waitForCoordinateSpace();
})();
