'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const EPSILON = 0.01;
  const ENDPOINT_TRIM_RADIUS = 24;
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    revision: 0,
    observer: null,
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
    if (!first || !second) return Number.POSITIVE_INFINITY;
    return Math.hypot(first.x - second.x, first.y - second.y);
  }

  function samePoint(first, second) {
    return Boolean(first && second && distance(first, second) <= EPSILON);
  }

  function sameX(first, second) {
    return Boolean(first && second && Math.abs(first.x - second.x) <= EPSILON);
  }

  function sameY(first, second) {
    return Boolean(first && second && Math.abs(first.y - second.y) <= EPSILON);
  }

  function segmentAxis(first, second) {
    if (!first || !second) return null;
    if (sameX(first, second) && !sameY(first, second)) return 'vertical';
    if (sameY(first, second) && !sameX(first, second)) return 'horizontal';
    return null;
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

  function orientPoints(points, source, target) {
    if (points.length < 2 || !source || !target) return points;
    const forward = distance(points[0], source) + distance(points.at(-1), target);
    const reverse = distance(points.at(-1), source) + distance(points[0], target);
    return reverse < forward ? [...points].reverse() : points;
  }

  function trimEndpointPoints(points, source, target) {
    const values = [...points];
    while (values.length && distance(values[0], source) < ENDPOINT_TRIM_RADIUS) {
      values.shift();
    }
    while (values.length && distance(values.at(-1), target) < ENDPOINT_TRIM_RADIUS) {
      values.pop();
    }
    return values;
  }

  function appendOrthogonal(output, point, preferredAxis = null) {
    const current = validPoint(point);
    const previous = output.at(-1);
    if (!current) return;
    if (!previous) {
      output.push(current);
      return;
    }
    if (samePoint(previous, current)) return;
    if (!sameX(previous, current) && !sameY(previous, current)) {
      const horizontalFirst = preferredAxis === 'horizontal'
        || (
          preferredAxis == null
          && Math.abs(current.x - previous.x) >= Math.abs(current.y - previous.y)
        );
      const elbow = horizontalFirst
        ? { x: current.x, y: previous.y }
        : { x: previous.x, y: current.y };
      if (!samePoint(previous, elbow)) output.push(elbow);
    }
    if (!samePoint(output.at(-1), current)) output.push(current);
  }

  function collapseRepeatedVertices(points) {
    const output = [];
    points.forEach((point) => {
      const repeated = output.findIndex((value) => samePoint(value, point));
      if (repeated >= 0) {
        output.splice(repeated + 1);
        return;
      }
      output.push(point);
    });
    return output;
  }

  function removeRedundant(points) {
    let values = collapseRepeatedVertices(
      points.map(validPoint).filter(Boolean),
    );
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
        const collinear = (
          (sameX(previous, current) && sameX(current, following))
          || (sameY(previous, current) && sameY(current, following))
        );
        if (collinear) {
          changed = true;
          continue;
        }
        next.push(current);
      }
      const last = values.at(-1);
      if (!samePoint(next.at(-1), last)) next.push(last);
      else changed = true;
      values = collapseRepeatedVertices(next);
    }
    return values;
  }

  function validOrthogonalRoute(points) {
    return points.length >= 2
      && points.every((point) => Boolean(validPoint(point)))
      && points.slice(1).every((point, index) => (
        !samePoint(points[index], point)
        && Boolean(segmentAxis(points[index], point))
      ));
  }

  function fallbackRoute(source, target) {
    if (!source || !target || samePoint(source, target)) return [];
    if (sameX(source, target) || sameY(source, target)) return [source, target];
    const middleX = rounded(source.x + (target.x - source.x) / 2);
    return [
      source,
      { x: middleX, y: source.y },
      { x: middleX, y: target.y },
      target,
    ];
  }

  function canonicalizePoints(rawPoints, sourceValue, targetValue) {
    const source = validPoint(sourceValue);
    const target = validPoint(targetValue);
    if (!source || !target || samePoint(source, target)) return [];

    const candidates = orientPoints(
      (rawPoints || []).map(validPoint).filter(Boolean),
      source,
      target,
    );
    const interior = trimEndpointPoints(candidates, source, target);
    const sourceAxis = segmentAxis(candidates[0], candidates[1]);
    const targetAxis = segmentAxis(candidates.at(-2), candidates.at(-1));
    const output = [source];
    interior.forEach((point, index) => {
      appendOrthogonal(
        output,
        point,
        index === 0 ? sourceAxis : null,
      );
    });
    appendOrthogonal(output, target, targetAxis);

    let compact = removeRedundant(output);
    if (!validOrthogonalRoute(compact)) compact = fallbackRoute(source, target);
    if (!validOrthogonalRoute(compact)) return [];
    compact[0] = source;
    compact[compact.length - 1] = target;
    compact = removeRedundant(compact);
    return validOrthogonalRoute(compact) ? compact : fallbackRoute(source, target);
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
    if (!validOrthogonalRoute(points)) return '';
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
      element.classList.add('model-edge', className);
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
    first.classList.add('model-edge', className);
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

  function branchKey(group) {
    return [
      group.dataset.wireId || '',
      group.dataset.branchIndex || '0',
      group.dataset.targetTerminalId || '',
    ].join('::');
  }

  function uniqueWireGroups(root) {
    const seen = new Set();
    const groups = [];
    root.querySelectorAll('.vi-wire-group[data-wire-id]').forEach((group) => {
      const key = branchKey(group);
      if (seen.has(key)) {
        group.remove();
        return;
      }
      seen.add(key);
      groups.push(group);
    });
    return groups;
  }

  function planWire(group) {
    const branch = branchRecord(group);
    if (!branch) return { group, branch: null, points: [], path: '' };
    const points = stableProjectedWirePoints(
      branch.wire,
      branch.targetTerminalId,
      branch.targetObjectId,
    );
    return {
      group,
      branch,
      points,
      path: pathFromPoints(points),
    };
  }

  function setPath(element, path) {
    if (element.getAttribute('d') !== path) element.setAttribute('d', path);
  }

  function applyPlan(plan, revision) {
    const { group, points, path } = plan;
    if (!path) {
      group.classList.add('is-wire-route-unresolved');
      group.setAttribute('visibility', 'hidden');
      group.dataset.wireStable = 'unresolved';
      group.dataset.wireRevision = String(revision);
      return;
    }

    const visible = ensurePath(group, 'vi-wire');
    const hit = ensurePath(group, 'vi-wire-hit', visible);
    setPath(visible, path);
    setPath(hit, path);
    runtime.lastPaths.set(group, path);
    group.classList.remove('is-wire-route-unresolved');
    group.removeAttribute('visibility');
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
      const plans = uniqueWireGroups(root).map(planWire);
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
      runtime.scheduled = false;
      decorate();
    });
  }

  function patchProjection() {
    const P = projection();
    if (!P?.ready || runtime.originalProjectedWirePoints) return false;
    const coordinate = globalThis.VIComponentCoordinateSpace;
    runtime.originalProjectedWirePoints = P.projectedWirePoints;
    runtime.originalProjectionDecorate = P.decorate;
    runtime.originalProjectionSchedule = P.schedule;
    P.projectedWirePoints = stableProjectedWirePoints;
    P.decorate = function decorateWithStableWires(...args) {
      const result = runtime.originalProjectionDecorate?.apply(P, args);
      decorate();
      return result;
    };
    P.schedule = function scheduleWithStableWires(...args) {
      const result = runtime.originalProjectionSchedule?.apply(P, args);
      schedule();
      return result;
    };
    if (coordinate?.ready) coordinate.projectedWirePoints = stableProjectedWirePoints;
    return true;
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithStableWires(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      decorate();
      return result;
    };
    E.renderAll = function renderAllWithStableWires(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      decorate();
      return result;
    };
    return true;
  }

  function installObserver(root) {
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.applying) return;
      const pathChanged = mutations.some((mutation) => (
        mutation.type === 'attributes'
        && mutation.attributeName === 'd'
        && mutation.target.matches?.('.vi-wire,.vi-wire-hit')
      ));
      if (pathChanged) {
        // Mutation observers run before paint, so a late legacy reroute is
        // replaced by the canonical path without a visible intermediate frame.
        decorate();
        return;
      }
      if (mutations.some((mutation) => mutation.type === 'childList')) schedule();
    });
    runtime.observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['d'],
    });
  }

  function install() {
    const P = projection();
    const root = state()?.el?.modelGraphSvg;
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
    installObserver(root);
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
      validOrthogonalRoute,
      branchEndpoints,
      decorate,
      schedule,
    };
    decorate();
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
