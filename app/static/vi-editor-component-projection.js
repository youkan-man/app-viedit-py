'use strict';

(() => {
  if (
    globalThis.VIComponentProjection?.loading
    || globalThis.VIComponentProjection?.ready
  ) {
    return;
  }

  globalThis.VIComponentProjection = { loading: true, ready: false };

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    observer: null,
    resizeGesture: null,
    originalRenderCanvas: null,
    originalRenderAll: null,
  };

  const GEOMETRY_EXCLUSIONS = [
    '.vi-object-label',
    '.vi-terminal-caption',
    '.vi-cluster-count',
    '.vi-structure-frame-badge',
    '.vi-resize-handle',
    '.vi-component-hit-target',
    'title',
  ].join(',');

  /* These factors are a display projection only. The VI's native bounds stay
     intact and continue to be used for persistence and property editing. */
  const SURFACE_FACTORS = {
    'front-panel': {
      default: 0.58,
      boolean: 0.50,
      numeric: 0.58,
      string: 0.58,
      path: 0.58,
      ring: 0.56,
      table: 0.70,
      terminal: 0.36,
    },
    'block-diagram': {
      default: 0.50,
      primitive: 0.46,
      constant: 0.48,
      subvi: 0.50,
      terminal: 0.32,
    },
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

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function validRect(value) {
    if (!value || typeof value !== 'object') return null;
    const x = finite(value.x, NaN);
    const y = finite(value.y, NaN);
    const width = finite(value.width, NaN);
    const height = finite(value.height, NaN);
    if (![x, y, width, height].every(Number.isFinite)) return null;
    if (width <= 0 || height <= 0) return null;
    return { x, y, width, height };
  }

  function logicalBounds(item, index = 0) {
    const E = editor();
    return E?.effectiveBounds?.(item, index)
      || E?.getBounds?.(item, index)
      || null;
  }

  function normalizedKind(item) {
    return [
      item?.visual_kind,
      item?.kind,
      item?.category,
      item?.class_name,
      item?.data_type,
    ].filter(Boolean).join(' ').toLowerCase();
  }

  function isContainer(item) {
    const kind = normalizedKind(item);
    return Boolean(
      item?.structure_frames?.length
      || item?.is_container
      || item?.visual_kind === 'structure'
      || kind.includes('structure')
      || kind.includes('cluster-container')
      || kind.includes('array-container')
      || (item?.child_object_ids?.length && (
        kind.includes('cluster') || kind.includes('array')
      )),
    );
  }

  function explicitVisualRect(item) {
    const candidates = [
      item?.visual_bounds,
      item?.display_bounds,
      item?.body_bounds,
      item?.icon_bounds,
      item?.native_visual_bounds,
      item?.geometry?.visual_bounds,
      item?.geometry?.display_bounds,
      item?.geometry?.body_bounds,
      item?.geometry?.icon_bounds,
      item?.bounds?.visual_bounds,
      item?.bounds?.display_bounds,
      item?.bounds?.body_bounds,
      item?.bounds?.icon_bounds,
    ];
    return candidates.map(validRect).find(Boolean) || null;
  }

  function factorFor(item) {
    if (!item || isContainer(item)) return 1;
    const surface = item.surface === 'block-diagram-inactive'
      ? 'block-diagram'
      : item.surface;
    const policy = SURFACE_FACTORS[surface]
      || SURFACE_FACTORS['block-diagram'];
    if (item.category === 'terminal') return policy.terminal;
    const kind = normalizedKind(item);
    if (surface === 'front-panel') {
      for (const key of [
        'boolean',
        'numeric',
        'string',
        'path',
        'ring',
        'table',
      ]) {
        if (kind.includes(key)) return policy[key];
      }
      return policy.default;
    }
    if (
      kind.includes('primitive')
      || kind.includes('add')
      || kind.includes('operator')
    ) {
      return policy.primitive;
    }
    if (kind.includes('constant')) return policy.constant;
    if (kind.includes('subvi') || kind.includes('sub-vi')) {
      return policy.subvi;
    }
    return policy.default;
  }

  function ownerId(item) {
    return item?.owner_object_id
      || item?.bounds?.relative_to_object_id
      || null;
  }

  function projectExplicitRect(explicit, logical) {
    const isAbsolute = (
      explicit.x >= logical.x - 1
      && explicit.y >= logical.y - 1
      && explicit.x + explicit.width <= logical.x + logical.width + 1
      && explicit.y + explicit.height <= logical.y + logical.height + 1
    );
    const isLocal = (
      explicit.x >= -1
      && explicit.y >= -1
      && explicit.x + explicit.width <= logical.width + 1
      && explicit.y + explicit.height <= logical.height + 1
    );
    if (!isAbsolute && !isLocal) return null;
    const x = isAbsolute ? explicit.x : logical.x + explicit.x;
    const y = isAbsolute ? explicit.y : logical.y + explicit.y;
    return {
      x,
      y,
      width: Math.min(logical.width, explicit.width),
      height: Math.min(logical.height, explicit.height),
      factor_x: Math.min(1, explicit.width / Math.max(1, logical.width)),
      factor_y: Math.min(1, explicit.height / Math.max(1, logical.height)),
      source: 'native-visual-bounds',
    };
  }

  function projectNonTerminal(item, logical) {
    const explicit = explicitVisualRect(item);
    const nativeProjection = explicit
      ? projectExplicitRect(explicit, logical)
      : null;
    if (nativeProjection) return nativeProjection;

    const factor = factorFor(item);
    return {
      x: logical.x,
      y: logical.y,
      width: Math.max(8, logical.width * factor),
      height: Math.max(8, logical.height * factor),
      factor_x: factor,
      factor_y: factor,
      source: factor === 1 ? 'native-container' : 'semantic-fallback',
    };
  }

  function projectTerminal(item, logical, stack) {
    const factor = factorFor(item);
    let centerX = logical.x + logical.width / 2;
    let centerY = logical.y + logical.height / 2;
    const S = state();
    const parentId = ownerId(item);
    const owner = parentId && !stack.has(parentId)
      ? S?.objects.get(parentId)
      : null;

    if (owner) {
      const ownerLogical = logicalBounds(owner);
      if (ownerLogical) {
        const next = new Set(stack);
        next.add(item.id);
        const ownerProjected = projectBounds(owner, ownerLogical, next);
        const ratioX = clamp(
          (centerX - ownerLogical.x) / Math.max(1, ownerLogical.width),
          0,
          1,
        );
        const ratioY = clamp(
          (centerY - ownerLogical.y) / Math.max(1, ownerLogical.height),
          0,
          1,
        );
        const direction = String(item.direction || '').toLowerCase();
        if (direction === 'source') {
          centerX = ownerProjected.x + ownerProjected.width;
        } else if (direction === 'sink') {
          centerX = ownerProjected.x;
        } else {
          centerX = ratioX <= 0.5
            ? ownerProjected.x
            : ownerProjected.x + ownerProjected.width;
        }
        centerY = ownerProjected.y + ownerProjected.height * ratioY;
      }
    }

    const width = Math.max(6, logical.width * factor);
    const height = Math.max(6, logical.height * factor);
    return {
      x: centerX - width / 2,
      y: centerY - height / 2,
      width,
      height,
      factor_x: width / Math.max(1, logical.width),
      factor_y: height / Math.max(1, logical.height),
      source: parentId ? 'owner-boundary-terminal' : 'terminal-center',
    };
  }

  function projectBounds(item, suppliedBounds = null, stack = new Set()) {
    const logical = suppliedBounds || logicalBounds(item);
    if (!item || !logical) return null;
    if (item.category === 'terminal') {
      return projectTerminal(item, logical, stack);
    }
    return projectNonTerminal(item, logical);
  }

  function logicalCenter(id) {
    const item = state()?.objects.get(id);
    const logical = logicalBounds(item);
    return logical
      ? {
        x: logical.x + logical.width / 2,
        y: logical.y + logical.height / 2,
      }
      : null;
  }

  function projectedCenter(id) {
    const item = state()?.objects.get(id);
    const projected = projectBounds(item);
    return projected
      ? {
        x: projected.x + projected.width / 2,
        y: projected.y + projected.height / 2,
      }
      : null;
  }

  function directGeometryChildren(group) {
    return [...group.children].filter((child) => (
      !child.matches(GEOMETRY_EXCLUSIONS)
      && !child.classList.contains('vi-component-geometry')
    ));
  }

  function geometryWrapper(group) {
    let wrapper = group.querySelector(':scope > .vi-component-geometry');
    if (!wrapper) {
      wrapper = document.createElementNS(SVG_NS, 'g');
      wrapper.classList.add('vi-component-geometry');
      const firstOverlay = [...group.children].find((child) => (
        child.matches(GEOMETRY_EXCLUSIONS)
      ));
      group.insertBefore(wrapper, firstOverlay || null);
    }
    directGeometryChildren(group).forEach((child) => wrapper.append(child));
    return wrapper;
  }

  function ensureHitTarget(group, item, logical, projected) {
    let target = group.querySelector(':scope > .vi-component-hit-target');
    const projectedBody = projected.factor_x < 0.999
      || projected.factor_y < 0.999;
    const needed = projectedBody
      || item.category === 'terminal'
      || projected.width < 18
      || projected.height < 18;
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

  function moveOverlay(element, translateX, translateY) {
    if (!element.dataset.componentBaseTransform) {
      element.dataset.componentBaseTransform = element.getAttribute('transform') || '';
    }
    const base = element.dataset.componentBaseTransform;
    const shift = Math.abs(translateX) > 0.01 || Math.abs(translateY) > 0.01
      ? `translate(${translateX} ${translateY})`
      : '';
    const value = `${shift} ${base}`.trim();
    if (value) element.setAttribute('transform', value);
    else element.removeAttribute('transform');
  }

  function applyObjectProjection(group) {
    const S = state();
    const id = group.dataset.objectId;
    const item = S?.objects.get(id);
    const logical = logicalBounds(item);
    const projected = projectBounds(item, logical);
    if (!item || !logical || !projected) return;

    const wrapper = geometryWrapper(group);
    const translateX = projected.x - logical.x;
    const translateY = projected.y - logical.y;
    wrapper.setAttribute(
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
    group.classList.toggle(
      'has-component-projection',
      projected.factor_x < 0.999 || projected.factor_y < 0.999,
    );

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
      handle.setAttribute('x', String(translateX + projected.width - 7));
      handle.setAttribute('y', String(translateY + projected.height - 7));
    }
    ensureHitTarget(group, item, logical, projected);
  }

  function distance(first, second) {
    return Math.hypot(first.x - second.x, first.y - second.y);
  }

  function cleanPoints(wire) {
    return (wire.route_points || []).map((point) => ({
      x: finite(point?.x, NaN),
      y: finite(point?.y, NaN),
    })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  }

  function orient(points, source, target) {
    if (points.length < 2 || !source || !target) return points;
    const forward = distance(points[0], source) + distance(points.at(-1), target);
    const reverse = distance(points.at(-1), source) + distance(points[0], target);
    return reverse < forward ? [...points].reverse() : points;
  }

  function compress(points) {
    const result = [];
    points.forEach((point) => {
      const previous = result.at(-1);
      if (!previous || distance(previous, point) > 0.01) result.push(point);
    });
    if (result.length < 3) return result;
    const compact = [result[0]];
    for (let index = 1; index < result.length - 1; index += 1) {
      const previous = compact.at(-1);
      const current = result[index];
      const next = result[index + 1];
      const sameX = Math.abs(previous.x - current.x) < 0.01
        && Math.abs(current.x - next.x) < 0.01;
      const sameY = Math.abs(previous.y - current.y) < 0.01
        && Math.abs(current.y - next.y) < 0.01;
      if (!sameX && !sameY) compact.push(current);
    }
    compact.push(result.at(-1));
    return compact;
  }

  function orthogonalize(source, bends, target) {
    const points = [source];
    bends.forEach((bend) => {
      const previous = points.at(-1);
      if (
        Math.abs(previous.x - bend.x) > 0.01
        && Math.abs(previous.y - bend.y) > 0.01
      ) {
        const horizontalFirst = Math.abs(previous.x - bend.x)
          >= Math.abs(previous.y - bend.y);
        points.push(horizontalFirst
          ? { x: bend.x, y: previous.y }
          : { x: previous.x, y: bend.y });
      }
      points.push(bend);
    });
    const previous = points.at(-1);
    if (
      Math.abs(previous.x - target.x) > 0.01
      && Math.abs(previous.y - target.y) > 0.01
    ) {
      points.push({ x: target.x, y: previous.y });
    }
    points.push(target);
    return compress(points);
  }

  function pathFromPoints(points) {
    if (!points.length) return '';
    const commands = [`M ${points[0].x} ${points[0].y}`];
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      if (Math.abs(previous.y - current.y) < 0.01) {
        commands.push(`H ${current.x}`);
      } else if (Math.abs(previous.x - current.x) < 0.01) {
        commands.push(`V ${current.y}`);
      } else {
        commands.push(`L ${current.x} ${current.y}`);
      }
    }
    return commands.join(' ');
  }

  function projectedWirePoints(wire, targetTerminalId, targetObjectId) {
    const sourceId = wire.source_terminal_id || wire.source_object_id;
    const targetId = targetTerminalId || targetObjectId;
    const source = projectedCenter(sourceId)
      || projectedCenter(wire.source_object_id);
    const target = projectedCenter(targetId)
      || projectedCenter(targetObjectId);
    if (!source || !target) return [];

    const logicalSource = logicalCenter(sourceId)
      || logicalCenter(wire.source_object_id)
      || source;
    const logicalTarget = logicalCenter(targetId)
      || logicalCenter(targetObjectId)
      || target;
    let bends = orient(cleanPoints(wire), logicalSource, logicalTarget);
    if (
      bends.length
      && (
        distance(bends[0], logicalSource) < 24
        || distance(bends[0], source) < 24
      )
    ) {
      bends.shift();
    }
    if (
      bends.length
      && (
        distance(bends.at(-1), logicalTarget) < 24
        || distance(bends.at(-1), target) < 24
      )
    ) {
      bends.pop();
    }
    if (!bends.length) {
      const middle = source.x + (target.x - source.x) / 2;
      bends = [
        { x: middle, y: source.y },
        { x: middle, y: target.y },
      ];
    }
    return orthogonalize(source, bends, target);
  }

  function applyWireProjection(group) {
    const wire = state()?.wires.get(group.dataset.wireId);
    if (!wire) return;
    const branchIndex = Math.max(
      0,
      Number.parseInt(group.dataset.branchIndex || '0', 10),
    );
    const targetTerminalId = group.dataset.targetTerminalId
      || wire.target_terminal_ids?.[branchIndex]
      || null;
    const targetObjectId = wire.target_object_ids?.[branchIndex] || null;
    const points = projectedWirePoints(
      wire,
      targetTerminalId,
      targetObjectId,
    );
    const path = pathFromPoints(points);
    if (!path) return;
    group.querySelectorAll(':scope > .vi-wire,:scope > .vi-wire-hit')
      .forEach((element) => element.setAttribute('d', path));
    group.dataset.projectedEndpoints = 'true';
    group.dataset.projectedPointCount = String(points.length);
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      root.querySelectorAll('[data-object-id]').forEach(applyObjectProjection);
      root.querySelectorAll('[data-wire-id]').forEach(applyWireProjection);
      root.dataset.componentProjection = 'true';
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

  function clientToWorld(event) {
    const root = state()?.el?.modelGraphSvg;
    const matrix = root?.getScreenCTM?.();
    if (!root || !matrix) return null;
    return new DOMPoint(event.clientX, event.clientY)
      .matrixTransform(matrix.inverse());
  }

  function finishResize(event) {
    const gesture = runtime.resizeGesture;
    if (!gesture || (event && event.pointerId !== gesture.pointerId)) return;
    event?.preventDefault?.();
    event?.stopImmediatePropagation?.();
    try {
      gesture.handle.releasePointerCapture?.(gesture.pointerId);
    } catch {
      // The rendered handle can be replaced while the pointer is captured.
    }
    runtime.resizeGesture = null;
    document.removeEventListener('pointermove', moveResize, true);
    document.removeEventListener('pointerup', finishResize, true);
    document.removeEventListener('pointercancel', finishResize, true);
  }

  function moveResize(event) {
    const gesture = runtime.resizeGesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const world = clientToWorld(event);
    const E = editor();
    const S = state();
    if (!world || !E || !S) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const displayDeltaX = world.x - gesture.startWorld.x;
    const displayDeltaY = world.y - gesture.startWorld.y;
    const width = Math.max(
      8,
      gesture.logical.width
        + displayDeltaX / Math.max(0.05, gesture.factorX),
    );
    const height = Math.max(
      8,
      gesture.logical.height
        + displayDeltaY / Math.max(0.05, gesture.factorY),
    );
    S.local.set(gesture.id, {
      x: gesture.logical.x,
      y: gesture.logical.y,
      width,
      height,
    });
    S.dirty.add(gesture.id);
    E.renderCanvas();
    E.renderInspector();
    E.updateStatus?.();
  }

  function beginResize(event) {
    const handle = event.target.closest?.('.vi-resize-handle');
    const group = handle?.closest?.('[data-object-id]');
    const item = group ? state()?.objects.get(group.dataset.objectId) : null;
    const logical = logicalBounds(item);
    const projected = projectBounds(item, logical);
    const world = clientToWorld(event);
    if (!handle || !group || !item || !logical || !projected || !world) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    runtime.resizeGesture = {
      id: item.id,
      pointerId: event.pointerId,
      handle,
      startWorld: world,
      logical: {
        x: logical.x,
        y: logical.y,
        width: logical.width,
        height: logical.height,
      },
      factorX: projected.factor_x,
      factorY: projected.factor_y,
    };
    handle.setPointerCapture?.(event.pointerId);
    document.addEventListener('pointermove', moveResize, true);
    document.addEventListener('pointerup', finishResize, true);
    document.addEventListener('pointercancel', finishResize, true);
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithComponentProjection(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      decorate();
      return result;
    };
    E.renderAll = function renderAllWithComponentProjection(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      decorate();
      return result;
    };
    return true;
  }

  function projectedMetrics() {
    const root = state()?.el?.modelGraphSvg;
    const records = [...(root?.querySelectorAll('[data-object-id]') || [])]
      .map((group) => ({
        id: group.dataset.objectId,
        source: group.dataset.projectionSource || null,
        scaleX: finite(group.dataset.componentScaleX, 1),
        scaleY: finite(group.dataset.componentScaleY, 1),
        x: finite(group.dataset.projectedX, 0),
        y: finite(group.dataset.projectedY, 0),
        width: finite(group.dataset.projectedWidth, 0),
        height: finite(group.dataset.projectedHeight, 0),
      }));
    return {
      total: records.length,
      projected: records.filter(
        (record) => record.scaleX < 0.999 || record.scaleY < 0.999,
      ).length,
      records,
    };
  }

  function install() {
    const E = editor();
    const root = state()?.el?.modelGraphSvg;
    if (runtime.ready || !E || !root) return false;
    runtime.ready = true;
    wrapRenderers();
    root.addEventListener('pointerdown', beginResize, true);
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.applying) return;
      if (mutations.some(
        (mutation) => mutation.addedNodes.length || mutation.removedNodes.length,
      )) {
        schedule();
      }
    });
    runtime.observer.observe(root, { childList: true, subtree: true });
    globalThis.VIComponentProjection = {
      loading: false,
      ready: true,
      runtime,
      SURFACE_FACTORS,
      factorFor,
      projectBounds,
      projectedCenter,
      projectedWirePoints,
      decorate,
      schedule,
      projectedMetrics,
    };
    decorate();
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 360) {
      setTimeout(() => waitForEditor(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentProjection = {
      loading: false,
      ready: false,
      error: 'semantic editor did not become ready',
      runtime,
      SURFACE_FACTORS,
    };
  }

  waitForEditor();
})();
