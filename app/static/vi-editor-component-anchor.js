'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    terminalAnchors: new WeakMap(),
    observer: null,
    originalProjectBounds: null,
    originalProjectedCenter: null,
    originalProjectedWirePoints: null,
    originalDecorate: null,
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

  function baseRect(item, fallback) {
    return validRect(item?.bounds) || validRect(fallback);
  }

  function isParentRelative(item, owner, terminalBase, ownerBase) {
    const coordinateSpace = String(
      item?.bounds?.source_coordinate_space
      || item?.source_coordinate_space
      || '',
    ).toLowerCase();
    if (
      coordinateSpace === 'parent-relative'
      || item?.bounds?.relative_to_object_id === owner?.id
    ) {
      return true;
    }
    const centerX = terminalBase.x + terminalBase.width / 2;
    const centerY = terminalBase.y + terminalBase.height / 2;
    const absoluteFits = (
      centerX >= ownerBase.x - terminalBase.width * 2
      && centerX <= ownerBase.x + ownerBase.width + terminalBase.width * 2
      && centerY >= ownerBase.y - terminalBase.height * 2
      && centerY <= ownerBase.y + ownerBase.height + terminalBase.height * 2
    );
    const localFits = (
      centerX >= -terminalBase.width * 2
      && centerX <= ownerBase.width + terminalBase.width * 2
      && centerY >= -terminalBase.height * 2
      && centerY <= ownerBase.height + terminalBase.height * 2
    );
    return !absoluteFits && localFits;
  }

  function anchorFor(item, owner, logical, ownerLogical) {
    const existing = runtime.terminalAnchors.get(item);
    if (existing?.owner === owner) return existing;

    const terminalBase = baseRect(item, logical);
    const ownerBase = baseRect(owner, ownerLogical);
    if (!terminalBase || !ownerBase) return null;
    const local = isParentRelative(item, owner, terminalBase, ownerBase);
    const centerX = terminalBase.x + terminalBase.width / 2;
    const centerY = terminalBase.y + terminalBase.height / 2;
    let ratioX = local
      ? centerX / Math.max(1, ownerBase.width)
      : (centerX - ownerBase.x) / Math.max(1, ownerBase.width);
    let ratioY = local
      ? centerY / Math.max(1, ownerBase.height)
      : (centerY - ownerBase.y) / Math.max(1, ownerBase.height);

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

    const anchor = {
      owner,
      ratioX: clamp(ratioX, 0, 1),
      ratioY: clamp(ratioY, 0, 1),
      horizontalSide: ratioX <= 0.5 ? 'left' : 'right',
      source: local ? 'parent-relative-native-bounds' : 'absolute-native-bounds',
    };
    runtime.terminalAnchors.set(item, anchor);
    return anchor;
  }

  function anchoredProjectBounds(item, suppliedBounds = null, stack = new Set()) {
    const P = projection();
    const logical = suppliedBounds || logicalBounds(item);
    if (!item || !logical || item.category !== 'terminal') {
      return runtime.originalProjectBounds?.(item, suppliedBounds, stack) || null;
    }

    const S = state();
    const parentId = ownerId(item);
    const owner = parentId && !stack.has(parentId)
      ? S?.objects.get(parentId)
      : null;
    if (!owner) {
      return runtime.originalProjectBounds?.(item, suppliedBounds, stack) || null;
    }

    const ownerLogical = logicalBounds(owner);
    if (!ownerLogical) {
      return runtime.originalProjectBounds?.(item, suppliedBounds, stack) || null;
    }
    const next = new Set(stack);
    next.add(item.id);
    const ownerProjected = anchoredProjectBounds(owner, ownerLogical, next);
    const anchor = anchorFor(item, owner, logical, ownerLogical);
    if (!ownerProjected || !anchor) {
      return runtime.originalProjectBounds?.(item, suppliedBounds, stack) || null;
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
      source: `owner-boundary-terminal-anchor:${anchor.source}`,
    };
  }

  function anchoredProjectedCenter(id) {
    const item = state()?.objects.get(id);
    const projected = anchoredProjectBounds(item);
    return projected
      ? {
        x: projected.x + projected.width / 2,
        y: projected.y + projected.height / 2,
      }
      : null;
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

  function anchoredProjectedWirePoints(wire, targetTerminalId, targetObjectId) {
    const sourceId = wire.source_terminal_id || wire.source_object_id;
    const targetId = targetTerminalId || targetObjectId;
    const source = anchoredProjectedCenter(sourceId)
      || anchoredProjectedCenter(wire.source_object_id);
    const target = anchoredProjectedCenter(targetId)
      || anchoredProjectedCenter(targetObjectId);
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

  function moveOverlay(element, translateX, translateY) {
    const base = element.dataset.componentBaseTransform
      ?? element.getAttribute('transform')
      ?? '';
    element.dataset.componentBaseTransform = base;
    const shift = Math.abs(translateX) > 0.01 || Math.abs(translateY) > 0.01
      ? `translate(${translateX} ${translateY})`
      : '';
    const value = `${shift} ${base}`.trim();
    if (value) element.setAttribute('transform', value);
    else element.removeAttribute('transform');
  }

  function updateHitTarget(group, logical, projected) {
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
    target.dataset.projectedBodyTarget = 'terminal-anchor';
  }

  function applyTerminal(group) {
    const item = state()?.objects.get(group.dataset.objectId);
    if (item?.category !== 'terminal') return;
    const logical = logicalBounds(item);
    const projected = anchoredProjectBounds(item, logical);
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
    group.querySelectorAll([
      ':scope > .vi-object-label',
      ':scope > .vi-terminal-caption',
      ':scope > .vi-cluster-count',
      ':scope > .vi-structure-frame-badge',
    ].join(',')).forEach((overlay) => moveOverlay(
      overlay,
      translateX,
      translateY,
    ));
    const handle = group.querySelector(':scope > .vi-resize-handle');
    if (handle) {
      handle.setAttribute('x', String(translateX + projected.width - 7));
      handle.setAttribute('y', String(translateY + projected.height - 7));
    }
    updateHitTarget(group, logical, projected);
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
    const points = anchoredProjectedWirePoints(
      wire,
      targetTerminalId,
      targetObjectId,
    );
    const path = pathFromPoints(points);
    if (!path) return;
    group.querySelectorAll(':scope > .vi-wire,:scope > .vi-wire-hit')
      .forEach((element) => element.setAttribute('d', path));
    group.dataset.projectedEndpoints = 'true';
    group.dataset.terminalAnchorEndpoints = 'true';
    group.dataset.projectedPointCount = String(points.length);
  }

  function decorate() {
    const root = state()?.el?.modelGraphSvg;
    if (!root || runtime.applying) return false;
    runtime.applying = true;
    try {
      root.querySelectorAll('[data-object-id]').forEach(applyTerminal);
      root.querySelectorAll('[data-wire-id]').forEach(applyWire);
      root.dataset.componentTerminalAnchors = 'true';
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
    if (!P?.ready || runtime.originalProjectBounds) return false;
    runtime.originalProjectBounds = P.projectBounds;
    runtime.originalProjectedCenter = P.projectedCenter;
    runtime.originalProjectedWirePoints = P.projectedWirePoints;
    runtime.originalDecorate = P.decorate;
    P.projectBounds = anchoredProjectBounds;
    P.projectedCenter = anchoredProjectedCenter;
    P.projectedWirePoints = anchoredProjectedWirePoints;
    P.decorate = function decorateWithTerminalAnchors(...args) {
      const result = runtime.originalDecorate.apply(P, args);
      decorate();
      return result;
    };
    return true;
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithTerminalAnchors(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      decorate();
      return result;
    };
    E.renderAll = function renderAllWithTerminalAnchors(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      decorate();
      return result;
    };
    return true;
  }

  function install() {
    const P = projection();
    const E = editor();
    const root = state()?.el?.modelGraphSvg;
    if (runtime.ready || !P?.ready || !E || !root) return false;
    runtime.ready = true;
    patchProjection();
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
    globalThis.VIComponentAnchors = {
      ready: true,
      runtime,
      anchorFor,
      projectBounds: anchoredProjectBounds,
      projectedCenter: anchoredProjectedCenter,
      projectedWirePoints: anchoredProjectedWirePoints,
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
    globalThis.VIComponentAnchors = {
      ready: false,
      error: 'component projection did not become ready',
      runtime,
    };
  }

  globalThis.VIComponentAnchors = { ready: false, runtime };
  waitForProjection();
})();
