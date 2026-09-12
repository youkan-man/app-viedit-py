'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const EPSILON = 0.01;
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    revision: 0,
    observer: null,
    resizeObserver: null,
    lastPaths: new WeakMap(),
    originalProjectedWirePoints: null,
    originalProjectionDecorate: null,
    originalProjectionSchedule: null,
    originalRenderCanvas: null,
    originalRenderAll: null,
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

  function finite(value, fallback = NaN) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function rounded(value) {
    return Math.round(finite(value, 0) * 1000) / 1000;
  }

  function validPoint(value) {
    const x = finite(value?.x);
    const y = finite(value?.y);
    return Number.isFinite(x) && Number.isFinite(y)
      ? { x: rounded(x), y: rounded(y) }
      : null;
  }

  function distance(first, second) {
    return Math.hypot(first.x - second.x, first.y - second.y);
  }

  function samePoint(first, second) {
    return Boolean(first && second && distance(first, second) <= EPSILON);
  }

  function sameX(first, second) {
    return Math.abs(first.x - second.x) <= EPSILON;
  }

  function sameY(first, second) {
    return Math.abs(first.y - second.y) <= EPSILON;
  }

  function projectedCenter(id) {
    if (!id) return null;
    return validPoint(projection()?.projectedCenter?.(id));
  }

  function branchEndpoints(wire, targetTerminalId, targetObjectId) {
    const source = projectedCenter(wire?.source_terminal_id)
      || projectedCenter(wire?.source_object_id);
    const target = projectedCenter(targetTerminalId)
      || projectedCenter(targetObjectId);
    return { source, target };
  }

  function appendOrthogonal(output, point, preferHorizontal = true) {
    const current = validPoint(point);
    const previous = output.at(-1);
    if (!current) return;
    if (!previous) {
      output.push(current);
      return;
    }
    if (samePoint(previous, current)) return;
    if (!sameX(previous, current) && !sameY(previous, current)) {
      output.push(preferHorizontal
        ? { x: current.x, y: previous.y }
        : { x: previous.x, y: current.y });
    }
    if (!samePoint(output.at(-1), current)) output.push(current);
  }

  function removeRedundant(points) {
    let values = points.filter(Boolean);
    let changed = true;
    while (changed && values.length > 2) {
      changed = false;
      const next = [values[0]];
      for (let index = 1; index < values.length - 1; index += 1) {
        const previous = next.at(-1);
        const current = values[index];
        const following = values[index + 1];
        if (samePoint(previous, current)) {
          changed = true;
          continue;
        }
        // Removing the middle point from any three points on the same axis
        // eliminates both harmless collinearity and immediate backtracking.
        if (
          (sameX(previous, current) && sameX(current, following))
          || (sameY(previous, current) && sameY(current, following))
        ) {
          changed = true;
          continue;
        }
        next.push(current);
      }
      const last = values.at(-1);
      if (!samePoint(next.at(-1), last)) next.push(last);
      else changed = true;
      values = next;
    }
    return values;
  }

  function fallbackRoute(source, target) {
    if (sameX(source, target) || sameY(source, target)) return [source, target];
    const middleX = rounded(source.x + (target.x - source.x) / 2);
    return [
      source,
      { x: middleX, y: source.y },
      { x: middleX, y: target.y },
      target,
    ];
  }

  function canonicalizePoints(rawPoints, source, target) {
    if (!source || !target) return [];
    const candidates = (rawPoints || []).map(validPoint).filter(Boolean);
    const interior = candidates.filter(
      (point, index) => !(
        index === 0 && distance(point, source) < 24
      ) && !(
        index === candidates.length - 1 && distance(point, target) < 24
      ),
    );
    const output = [source];
    interior.forEach((point, index) => {
      appendOrthogonal(output, point, index % 2 === 0);
    });
    appendOrthogonal(output, target, true);
    let compact = removeRedundant(output);
    if (compact.length < 2 || samePoint(compact[0], compact.at(-1))) {
      compact = fallbackRoute(source, target);
    }
    if (compact.length === 2 && !sameX(compact[0], compact[1]) && !sameY(compact[0], compact[1])) {
      compact = fallbackRoute(source, target);
    }
    compact[0] = source;
    compact[compact.length - 1] = target;
    return removeRedundant(compact);
  }

  function stableProjectedWirePoints(wire, targetTerminalId, targetObjectId) {
    const endpoints = branchEndpoints(wire, targetTerminalId, targetObjectId);
    if (!endpoints.source || !endpoints.target) return [];
    let raw = [];
    try {
      raw = runtime.originalProjectedWirePoints?.(
        wire,
        targetTerminalId,
        targetObjectId,
      ) || [];
    } catch {
      raw = [];
    }
    if (!raw.length) raw = wire?.route_points || [];
    return canonicalizePoints(raw, endpoints.source, endpoints.target);
  }

  function pathFromPoints(points) {
    if (points.length < 2) return '';
    const commands = [`M ${points[0].x} ${points[0].y}`];
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      if (sameY(previous, current)) commands.push(`H ${current.x}`);
      else if (sameX(previous, current)) commands.push(`V ${current.y}`);
      else return '';
    }
    return commands.join(' ');
  }

  function ensurePath(group, className, source = null) {
    const paths = [...group.querySelectorAll(`:scope > .${className}`)];
    const first = paths.shift() || (() => {
      const element = document.createElementNS(SVG_NS, 'path');
      element.classList.add(className);
      element.setAttribute('fill', 'none');
      if (source) {
        for (const attribute of source.attributes || []) {
          if (attribute.name === 'class' || attribute.name === 'd') continue;
          element.setAttribute(attribute.name, attribute.value);
        }
      }
      group.append(element);
      return element;
    })();
    paths.forEach((element) => element.remove());
    return first;
  }

  function branchRecord(group) {
    const S = state();
    const wire = S?.wires.get(group.dataset.wireId);
    if (!wire) return null;
    const branchIndex = Math.max(
      0,
      Number.parseInt(group.dataset.branchIndex || '0', 10) || 0,
    );
    return {
      wire,
      branchIndex,
      targetTerminalId: group.dataset.targetTerminalId
        || wire.target_terminal_ids?.[branchIndex]
        || null,
      targetObjectId: wire.target_object_ids?.[branchIndex] || null,
    };
  }

  function planWire(group) {
    const branch = branchRecord(group);
    if (!branch) return null;
    const points = stableProjectedWirePoints(
      branch.wire,
      branch.targetTerminalId,
      branch.targetObjectId,
    );
    const path = pathFromPoints(points);
    if (!path) return null;
    return { group, branch, points, path };
  }

  function applyPlan(plan, revision) {
    const { group, points, path } = plan;
    const visible = ensurePath(group, 'vi-wire');
    const hit = ensurePath(group, 'vi-wire-hit', visible);
    if (runtime.lastPaths.get(group) !== path || visible.getAttribute('d') !== path) {
      visible.setAttribute('d', path);
      hit.setAttribute('d', path);
      runtime.lastPaths.set(group, path);
    } else if (hit.getAttribute('d') !== path) {
      hit.setAttribute('d', path);
    }
    group.dataset.wireStable = 'true';
    group.dataset.wireRevision = String(revision);
    group.dataset.stablePointCount = String(points.length);
    group.dataset.projectedEndpoints = 'true';
    group.dataset.coordinateSpaceEndpoints = 'true';
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      const plans = [...root.querySelectorAll('.vi-wire-group[data-wire-id]')]
        .map(planWire)
        .filter(Boolean);
      const revision = ++runtime.revision;
      plans.forEach((plan) => applyPlan(plan, revision));
      root.dataset.wireStability = 'true';
      root.dataset.wireStabilityRevision = String(revision);
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
    if (!P?.ready || runtime.originalProjectedWirePoints) return false;
    runtime.originalProjectedWirePoints = P.projectedWirePoints;
    runtime.originalProjectionDecorate = P.decorate;
    runtime.originalProjectionSchedule = P.schedule;
    P.projectedWirePoints = stableProjectedWirePoints;
    P.decorate = function decorateWithStableWires(...args) {
      const result = runtime.originalProjectionDecorate?.apply(P, args);
      schedule();
      return result;
    };
    P.schedule = function scheduleWithStableWires(...args) {
      const result = runtime.originalProjectionSchedule?.apply(P, args);
      schedule();
      return result;
    };
    return true;
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithStableWires(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      schedule();
      return result;
    };
    E.renderAll = function renderAllWithStableWires(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      schedule();
      return result;
    };
    return true;
  }

  function install() {
    const P = projection();
    const root = state()?.el?.modelGraphSvg;
    const viewport = state()?.el?.modelGraphViewport;
    if (
      runtime.ready
      || !P?.ready
      || !globalThis.VIComponentCoordinateSpace?.ready
      || !globalThis.VICompactResizeHandles?.ready
      || !root
      || !editor()
    ) return false;

    runtime.ready = true;
    patchProjection();
    wrapRenderers();
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.applying) return;
      if (mutations.some((mutation) => (
        mutation.type === 'childList'
        || mutation.attributeName === 'viewBox'
        || mutation.attributeName === 'transform'
        || mutation.attributeName === 'data-projected-x'
        || mutation.attributeName === 'data-projected-y'
        || mutation.attributeName === 'data-projected-width'
        || mutation.attributeName === 'data-projected-height'
      ))) schedule();
    });
    runtime.observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: [
        'viewBox',
        'transform',
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
    document.addEventListener('vi-structure-frame-changed', schedule);

    globalThis.VIWireStability = {
      ready: true,
      runtime,
      canonicalizePoints,
      projectedWirePoints: stableProjectedWirePoints,
      pathFromPoints,
      decorate,
      schedule,
    };
    schedule();
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 600) {
      setTimeout(() => waitForEditor(attempt + 1), 25);
      return;
    }
    globalThis.VIWireStability = {
      ready: false,
      error: 'wire projection dependencies did not become ready',
      runtime,
    };
  }

  globalThis.VIWireStability = { ready: false, runtime };
  waitForEditor();
})();
