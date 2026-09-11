'use strict';

(() => {
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    originalProjectBounds: null,
    originalDecorate: null,
    originalSchedule: null,
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

  function normalizedProjectBounds(
    item,
    suppliedBounds = null,
    stack = new Set(),
  ) {
    const logical = suppliedBounds || logicalBounds(item);
    const projected = runtime.originalProjectBounds?.(
      item,
      suppliedBounds,
      stack,
    );
    if (!logical || !projected) return projected || null;
    const width = finite(projected.width, NaN);
    const height = finite(projected.height, NaN);
    if (!Number.isFinite(width) || !Number.isFinite(height)) return projected;
    return {
      ...projected,
      factor_x: width / Math.max(1, finite(logical.width, 1)),
      factor_y: height / Math.max(1, finite(logical.height, 1)),
      projection_scale_consistent: true,
    };
  }

  function setAttribute(element, name, value) {
    const next = String(value);
    if (element.getAttribute(name) !== next) element.setAttribute(name, next);
  }

  function applyObject(group) {
    const item = state()?.objects.get(group.dataset.objectId);
    const logical = logicalBounds(item);
    const projected = normalizedProjectBounds(item, logical);
    const wrapper = group.querySelector(':scope > .vi-component-geometry');
    if (!item || !logical || !projected || !wrapper) return;
    const translateX = finite(projected.x) - finite(logical.x);
    const translateY = finite(projected.y) - finite(logical.y);
    setAttribute(
      wrapper,
      'transform',
      `translate(${translateX} ${translateY}) scale(${projected.factor_x} ${projected.factor_y})`,
    );
    wrapper.dataset.projectionScaleConsistent = 'true';
    group.dataset.componentScaleX = projected.factor_x.toFixed(4);
    group.dataset.componentScaleY = projected.factor_y.toFixed(4);
    group.dataset.projectedX = finite(projected.x).toFixed(3);
    group.dataset.projectedY = finite(projected.y).toFixed(3);
    group.dataset.projectedWidth = finite(projected.width).toFixed(3);
    group.dataset.projectedHeight = finite(projected.height).toFixed(3);
    group.dataset.projectionScaleConsistent = 'true';
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      root.querySelectorAll('[data-object-id]').forEach(applyObject);
      root.dataset.componentGeometryConsistent = 'true';
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
      projection()?.decorate?.();
    });
  }

  function patchProjection() {
    const P = projection();
    if (!P?.ready || runtime.originalProjectBounds) return false;
    runtime.originalProjectBounds = P.projectBounds;
    runtime.originalDecorate = P.decorate;
    runtime.originalSchedule = P.schedule;
    P.projectBounds = normalizedProjectBounds;
    P.decorate = function decorateWithConsistentGeometry(...args) {
      const result = runtime.originalDecorate?.apply(P, args);
      decorate();
      return result;
    };
    P.schedule = schedule;
    return true;
  }

  function install() {
    const P = projection();
    const root = state()?.el?.modelGraphSvg;
    if (
      runtime.ready
      || !P?.ready
      || !globalThis.VIComponentTerminalVisual?.ready
      || !root
    ) return false;
    runtime.ready = true;
    patchProjection();
    globalThis.VIComponentGeometryConsistency = {
      ready: true,
      runtime,
      projectBounds: normalizedProjectBounds,
      decorate,
      schedule,
    };
    P.decorate?.();
    return true;
  }

  function waitForTerminalVisual(attempt = 0) {
    if (install()) return;
    if (attempt < 360) {
      setTimeout(() => waitForTerminalVisual(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentGeometryConsistency = {
      ready: false,
      error: 'terminal visual projection did not become ready',
      runtime,
    };
  }

  globalThis.VIComponentGeometryConsistency = { ready: false, runtime };
  waitForTerminalVisual();
})();
