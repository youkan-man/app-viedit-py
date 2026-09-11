'use strict';

(() => {
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    observer: null,
    anchors: new WeakMap(),
    originalProjectionDecorate: null,
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

  function ownerId(item) {
    return item?.owner_object_id
      || item?.bounds?.relative_to_object_id
      || item?.parent_object_id
      || null;
  }

  function coordinateSpace(item) {
    return String(
      item?.bounds?.source_coordinate_space
      || item?.source_coordinate_space
      || '',
    ).trim().toLowerCase();
  }

  function explicitAnchor(item) {
    const x = finite(
      item?.bounds?.anchor_x ?? item?.anchor_x,
      NaN,
    );
    const y = finite(
      item?.bounds?.anchor_y ?? item?.anchor_y,
      NaN,
    );
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return {
      ratioX: clamp(x, 0, 1),
      ratioY: clamp(y, 0, 1),
      source: 'semantic-anchor',
    };
  }

  function nativeRect(item, fallback) {
    return validRect(item?.bounds) || validRect(fallback);
  }

  function classifyCoordinates(item, owner, terminalRect, ownerRect) {
    const space = coordinateSpace(item);
    if (
      space.includes('absolute')
      || space.includes('owner-anchored')
      || space.includes('diagram')
      || space.includes('canvas')
    ) {
      return 'absolute';
    }
    if (
      space.includes('parent-relative')
      || space.includes('owner-relative')
      || space === 'local'
      || space.endsWith('-local')
    ) {
      return 'relative';
    }

    const centerX = terminalRect.x + terminalRect.width / 2;
    const centerY = terminalRect.y + terminalRect.height / 2;
    const absoluteFits = (
      centerX >= ownerRect.x - terminalRect.width * 2
      && centerX <= ownerRect.x + ownerRect.width + terminalRect.width * 2
      && centerY >= ownerRect.y - terminalRect.height * 2
      && centerY <= ownerRect.y + ownerRect.height + terminalRect.height * 2
    );
    const relativeFits = (
      centerX >= -terminalRect.width * 2
      && centerX <= ownerRect.width + terminalRect.width * 2
      && centerY >= -terminalRect.height * 2
      && centerY <= ownerRect.height + terminalRect.height * 2
    );
    if (absoluteFits && !relativeFits) return 'absolute';
    if (relativeFits && !absoluteFits) return 'relative';
    if (item?.bounds?.relative_to_object_id === owner?.id) return 'relative';
    return absoluteFits ? 'absolute' : 'relative';
  }

  function nativeAnchor(item, owner, logical, ownerLogical) {
    const cached = runtime.anchors.get(item);
    if (cached?.owner === owner) return cached;

    const semantic = explicitAnchor(item);
    if (semantic) {
      const value = {
        owner,
        ...semantic,
        horizontalSide: semantic.ratioX <= 0.5 ? 'left' : 'right',
      };
      runtime.anchors.set(item, value);
      return value;
    }

    const terminalRect = nativeRect(item, logical);
    const ownerRect = nativeRect(owner, ownerLogical);
    if (!terminalRect || !ownerRect) return null;
    const classification = classifyCoordinates(
      item,
      owner,
      terminalRect,
      ownerRect,
    );
    const centerX = terminalRect.x + terminalRect.width / 2;
    const centerY = terminalRect.y + terminalRect.height / 2;
    let ratioX = classification === 'relative'
      ? centerX / Math.max(1, ownerRect.width)
      : (centerX - ownerRect.x) / Math.max(1, ownerRect.width);
    let ratioY = classification === 'relative'
      ? centerY / Math.max(1, ownerRect.height)
      : (centerY - ownerRect.y) / Math.max(1, ownerRect.height);

    if (!Number.isFinite(ratioX) || ratioX < -0.5 || ratioX > 1.5) {
      ratioX = (
        logical.x + logical.width / 2 - ownerLogical.x
      ) / Math.max(1, ownerLogical.width);
    }
    if (!Number.isFinite(ratioY) || ratioY < -0.5 || ratioY > 1.5) {
      ratioY = (
        logical.y + logical.height / 2 - ownerLogical.y
      ) / Math.max(1, ownerLogical.height);
    }

    const value = {
      owner,
      ratioX: clamp(ratioX, 0, 1),
      ratioY: clamp(ratioY, 0, 1),
      horizontalSide: ratioX <= 0.5 ? 'left' : 'right',
      source: `${classification}-native-bounds`,
    };
    runtime.anchors.set(item, value);
    return value;
  }

  function baseProjectBounds(item, suppliedBounds = null, stack = new Set()) {
    const anchorRuntime = globalThis.VIComponentAnchors?.runtime;
    const original = anchorRuntime?.originalProjectBounds;
    if (typeof original === 'function') {
      return original(item, suppliedBounds, stack);
    }
    return null;
  }

  function projectBounds(item, suppliedBounds = null, stack = new Set()) {
    const P = projection();
    const logical = suppliedBounds || logicalBounds(item);
    if (!item || !logical || item.category !== 'terminal') {
      return baseProjectBounds(item, suppliedBounds, stack)
        || P?.projectBounds?.(item, suppliedBounds, stack)
        || null;
    }

    const S = state();
    const parentId = ownerId(item);
    const owner = parentId && !stack.has(parentId)
      ? S?.objects.get(parentId)
      : null;
    if (!owner) return baseProjectBounds(item, suppliedBounds, stack);

    const ownerLogical = logicalBounds(owner);
    if (!ownerLogical) return baseProjectBounds(item, suppliedBounds, stack);
    const next = new Set(stack);
    next.add(item.id);
    const ownerProjected = projectBounds(owner, ownerLogical, next);
    const anchor = nativeAnchor(item, owner, logical, ownerLogical);
    if (!ownerProjected || !anchor) {
      return baseProjectBounds(item, suppliedBounds, stack);
    }

    const factor = P?.factorFor?.(item) || 1;
    const width = Math.max(6, logical.width * factor);
    const height = Math.max(6, logical.height * factor);
    const direction = String(item.direction || '').toLowerCase();
    let centerX;
    if (direction === 'source') {
      centerX = ownerProjected.x + ownerProjected.width;
    } else if (direction === 'sink') {
      centerX = ownerProjected.x;
    } else {
      centerX = anchor.horizontalSide === 'left'
        ? ownerProjected.x
        : ownerProjected.x + ownerProjected.width;
    }
    const centerY = ownerProjected.y + ownerProjected.height * anchor.ratioY;
    return {
      x: centerX - width / 2,
      y: centerY - height / 2,
      width,
      height,
      factor_x: width / Math.max(1, logical.width),
      factor_y: height / Math.max(1, logical.height),
      source: `owner-boundary-terminal:${anchor.source}`,
    };
  }

  function projectedCenter(id) {
    const item = state()?.objects.get(id);
    const projected = projectBounds(item);
    return projected ? {
      x: projected.x + projected.width / 2,
      y: projected.y + projected.height / 2,
    } : null;
  }

  function logicalCenter(id) {
    const item = state()?.objects.get(id);
    const bounds = logicalBounds(item);
    return bounds ? {
      x: bounds.x + bounds.width / 2,
      y: bounds.y + bounds.height / 2,
    } : null;
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
    const output = [];
    points.forEach((point) => {
      if (!output.length || distance(output.at(-1), point) > 0.01) {
        output.push(point);
      }
    });
    if (output.length < 3) return output;
    const compact = [output[0]];
    for (let index = 1; index < output.length - 1; index += 1) {
      const previous = compact.at(-1);
      const current = output[index];
      const next = output[index + 1];
      const sameX = Math.abs(previous.x - current.x) < 0.01
        && Math.abs(current.x - next.x) < 0.01;
      const sameY = Math.abs(previous.y - current.y) < 0.01
        && Math.abs(current.y - next.y) < 0.01;
      if (!sameX && !sameY) compact.push(current);
    }
    compact.push(output.at(-1));
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
    ) bends.shift();
    if (
      bends.length
      && (
        distance(bends.at(-1), logicalTarget) < 24
        || distance(bends.at(-1), target) < 24
      )
    ) bends.pop();
    if (!bends.length) {
      const middle = source.x + (target.x - source.x) / 2;
      bends = [
        { x: middle, y: source.y },
        { x: middle, y: target.y },
      ];
    }
    return orthogonalize(source, bends, target);
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

  function applyTerminal(group) {
    const item = state()?.objects.get(group.dataset.objectId);
    if (item?.category !== 'terminal') return;
    const logical = logicalBounds(item);
    const projected = projectBounds(item, logical);
    const wrapper = group.querySelector(':scope > .vi-component-geometry');
    if (!logical || !projected || !wrapper) return;
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
  }

  function applyWire(group) {
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
    const points = projectedWirePoints(wire, targetTerminalId, targetObjectId);
    const path = pathFromPoints(points);
    if (!path) return;
    group.querySelectorAll(':scope > .vi-wire,:scope > .vi-wire-hit')
      .forEach((element) => element.setAttribute('d', path));
    group.dataset.projectedEndpoints = 'true';
    group.dataset.coordinateSpaceEndpoints = 'true';
    group.dataset.projectedPointCount = String(points.length);
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      root.querySelectorAll('[data-object-id]').forEach(applyTerminal);
      root.querySelectorAll('[data-wire-id]').forEach(applyWire);
      root.dataset.componentCoordinateSpace = 'true';
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
    const A = globalThis.VIComponentAnchors;
    if (!P?.ready) return false;
    P.runtime?.observer?.disconnect?.();
    A?.runtime?.observer?.disconnect?.();
    runtime.originalProjectionDecorate = P.decorate;
    P.projectBounds = projectBounds;
    P.projectedCenter = projectedCenter;
    P.projectedWirePoints = projectedWirePoints;
    P.decorate = function decorateWithCoordinateSpaces(...args) {
      const result = runtime.originalProjectionDecorate?.apply(P, args);
      decorate();
      return result;
    };
    P.schedule = schedule;
    if (A?.ready) {
      A.projectBounds = projectBounds;
      A.projectedCenter = projectedCenter;
      A.projectedWirePoints = projectedWirePoints;
      A.decorate = decorate;
      A.schedule = schedule;
    }
    return true;
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithCoordinateSpaces(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      decorate();
      return result;
    };
    E.renderAll = function renderAllWithCoordinateSpaces(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      decorate();
      return result;
    };
    return true;
  }

  function install() {
    const P = projection();
    const root = state()?.el?.modelGraphSvg;
    if (runtime.ready || !P?.ready || !root || !editor()) return false;
    runtime.ready = true;
    patchProjection();
    wrapRenderers();
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.applying) return;
      if (mutations.some(
        (mutation) => mutation.addedNodes.length || mutation.removedNodes.length,
      )) schedule();
    });
    runtime.observer.observe(root, { childList: true, subtree: true });
    globalThis.VIComponentCoordinateSpace = {
      ready: true,
      runtime,
      coordinateSpace,
      classifyCoordinates,
      nativeAnchor,
      projectBounds,
      projectedCenter,
      projectedWirePoints,
      decorate,
      schedule,
    };
    decorate();
    schedule();
    return true;
  }

  function waitForProjection(attempt = 0) {
    if (install()) return;
    if (attempt < 360) {
      setTimeout(() => waitForProjection(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentCoordinateSpace = {
      ready: false,
      error: 'component projection did not become ready',
      runtime,
    };
  }

  globalThis.VIComponentCoordinateSpace = { ready: false, runtime };
  waitForProjection();
})();
