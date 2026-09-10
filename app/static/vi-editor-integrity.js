'use strict';

(() => {
  const runtime = {
    ready: false,
    queued: false,
    decorating: false,
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function distance(first, second) {
    return Math.hypot(first.x - second.x, first.y - second.y);
  }

  function center(item) {
    const E = editor();
    const bounds = E?.effectiveBounds?.(item) || E?.getBounds?.(item);
    return bounds
      ? {
        x: number(bounds.x) + number(bounds.width) / 2,
        y: number(bounds.y) + number(bounds.height) / 2,
      }
      : null;
  }

  function endpoint(terminalId, objectId) {
    const S = state();
    return center(S?.objects.get(terminalId) || S?.objects.get(objectId));
  }

  function cleanPoints(wire) {
    return (wire.route_points || [])
      .map((point) => ({ x: number(point?.x, NaN), y: number(point?.y, NaN) }))
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  }

  function orient(points, source, target) {
    if (points.length < 2) return points;
    const forward = distance(points[0], source) + distance(points.at(-1), target);
    const reversed = distance(points.at(-1), source) + distance(points[0], target);
    return reversed < forward ? [...points].reverse() : points;
  }

  function axis(first, second) {
    if (!first || !second) return null;
    const dx = Math.abs(first.x - second.x);
    const dy = Math.abs(first.y - second.y);
    return dx >= dy ? 'horizontal' : 'vertical';
  }

  function samePoint(first, second) {
    return distance(first, second) < 0.01;
  }

  function appendOrthogonal(points, next, preferredAxis = null) {
    const previous = points.at(-1);
    if (!previous || samePoint(previous, next)) return;
    if (Math.abs(previous.x - next.x) < 0.01 || Math.abs(previous.y - next.y) < 0.01) {
      points.push(next);
      return;
    }
    const elbow = preferredAxis === 'vertical'
      ? { x: previous.x, y: next.y }
      : { x: next.x, y: previous.y };
    if (!samePoint(previous, elbow)) points.push(elbow);
    if (!samePoint(points.at(-1), next)) points.push(next);
  }

  function compress(points) {
    const output = [];
    points.forEach((point) => {
      if (!output.length || !samePoint(output.at(-1), point)) output.push(point);
    });
    if (output.length < 3) return output;
    const compact = [output[0]];
    for (let index = 1; index < output.length - 1; index += 1) {
      const previous = compact.at(-1);
      const current = output[index];
      const next = output[index + 1];
      const vertical = Math.abs(previous.x - current.x) < 0.01
        && Math.abs(current.x - next.x) < 0.01;
      const horizontal = Math.abs(previous.y - current.y) < 0.01
        && Math.abs(current.y - next.y) < 0.01;
      if (!vertical && !horizontal) compact.push(current);
    }
    compact.push(output.at(-1));
    return compact;
  }

  function routePoints(wire, targetTerminalId, targetObjectId) {
    const source = endpoint(wire.source_terminal_id, wire.source_object_id);
    const target = endpoint(targetTerminalId, targetObjectId);
    if (!source || !target) return [];

    const native = orient(cleanPoints(wire), source, target);
    if (native.length < 2) {
      const middle = source.x + (target.x - source.x) / 2;
      return compress([
        source,
        { x: middle, y: source.y },
        { x: middle, y: target.y },
        target,
      ]);
    }

    const sourceAxis = axis(native[0], native[1]);
    const targetAxis = axis(native.at(-2), native.at(-1));
    const bends = [...native];
    if (distance(bends[0], source) <= 12) bends.shift();
    if (bends.length && distance(bends.at(-1), target) <= 12) bends.pop();

    const output = [source];
    bends.forEach((bend, index) => {
      appendOrthogonal(output, bend, index === 0 ? sourceAxis : null);
    });
    appendOrthogonal(output, target, targetAxis);
    return compress(output);
  }

  function pathFromPoints(points) {
    if (!points.length) return '';
    const commands = [`M ${points[0].x} ${points[0].y}`];
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      if (Math.abs(previous.y - current.y) < 0.01) commands.push(`H ${current.x}`);
      else if (Math.abs(previous.x - current.x) < 0.01) commands.push(`V ${current.y}`);
      else commands.push(`L ${current.x} ${current.y}`);
    }
    return commands.join(' ');
  }

  function repairWirePaths() {
    const S = state();
    if (!S) return;
    document.querySelectorAll('#model-graph-svg [data-wire-id]').forEach((group) => {
      const wire = S.wires.get(group.dataset.wireId);
      if (!wire) return;
      const targetTerminalId = group.dataset.targetTerminalId || wire.target_terminal_ids?.[0];
      const branchIndex = Math.max(0, number(group.dataset.branchIndex));
      const targetObjectId = wire.target_object_ids?.[branchIndex] || null;
      const points = routePoints(wire, targetTerminalId, targetObjectId);
      const path = pathFromPoints(points);
      if (!path) return;
      group.querySelectorAll('.vi-wire,.vi-wire-hit').forEach((element) => {
        element.setAttribute('d', path);
      });
      group.dataset.routePointCount = String(points.length);
      group.dataset.routeIntegrity = 'orthogonal-endpoints';
    });
  }

  function applyNetSelection() {
    const S = state();
    if (!S) return;
    const selectedWire = S.wires.get(S.selected);
    const selectedNet = selectedWire?.net_id || null;
    document.querySelectorAll('#model-graph-svg [data-wire-id]').forEach((group) => {
      const wire = S.wires.get(group.dataset.wireId);
      group.dataset.netId = wire?.net_id || '';
      group.classList.toggle(
        'is-net-related',
        Boolean(selectedNet && wire?.net_id === selectedNet && wire.id !== S.selected),
      );
    });
  }

  function applyFilterVisibility() {
    const S = state();
    if (!S) return;
    const query = document.querySelector('#model-graph-query')?.value?.trim() || '';
    const kind = document.querySelector('#model-graph-kind')?.value || '';
    const filtering = Boolean(query || kind);
    const rendered = new Set(
      [...document.querySelectorAll('#model-graph-svg [data-object-id]')]
        .map((element) => element.dataset.objectId),
    );
    document.querySelectorAll('#model-graph-svg [data-wire-id]').forEach((group) => {
      const wire = S.wires.get(group.dataset.wireId);
      const endpoints = [
        wire?.source_terminal_id,
        wire?.source_object_id,
        ...(wire?.target_terminal_ids || []),
        ...(wire?.target_object_ids || []),
      ].filter(Boolean);
      const visible = !filtering
        || wire?.id === S.selected
        || endpoints.some((id) => rendered.has(id));
      group.classList.toggle('is-filter-hidden', !visible);
      group.setAttribute('aria-hidden', String(!visible));
    });
  }

  function ensureIntegrityStatus() {
    const S = state();
    const summary = S?.vi?.summary || {};
    const parser = S?.vi?.parser || {};
    const integrity = S?.vi?.integrity || {};
    const toolbar = document.querySelector('.vi-canvas-toolbar > div:first-child');
    if (!toolbar || !S?.vi) return;
    let status = document.querySelector('#vi-semantic-integrity-status');
    if (!status) {
      status = document.createElement('small');
      status.id = 'vi-semantic-integrity-status';
      status.className = 'vi-semantic-integrity-status';
      toolbar.append(status);
    }
    const authoritative = parser.mode === 'authoritative';
    status.classList.toggle('is-warning', !authoritative || number(integrity.type_conflicts) > 0);
    status.textContent = authoritative
      ? `${number(summary.block_diagram_nodes)}ノード · ${number(summary.wire_nets, summary.wires)}ネット · 意味解析済み`
      : '意味解析未確定 — 誤ったブロック図は表示しません';
  }

  function decorate() {
    if (runtime.decorating) return;
    runtime.decorating = true;
    try {
      repairWirePaths();
      applyNetSelection();
      applyFilterVisibility();
      ensureIntegrityStatus();
    } finally {
      runtime.decorating = false;
    }
  }

  function queue() {
    if (runtime.queued) return;
    runtime.queued = true;
    requestAnimationFrame(() => {
      runtime.queued = false;
      decorate();
    });
  }

  function install() {
    const root = document.querySelector('#model-graph-svg');
    if (runtime.ready || !root) return false;
    runtime.ready = true;
    new MutationObserver(queue).observe(root, { childList: true, subtree: true });
    document.querySelector('#model-graph-query')?.addEventListener('input', queue);
    document.querySelector('#model-graph-kind')?.addEventListener('change', queue);
    root.addEventListener('click', queue);
    root.addEventListener('pointerup', queue);
    queue();
    globalThis.VIEditorIntegrity = {
      ready: true,
      runtime,
      decorate,
      routePoints,
      pathFromPoints,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 320) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIEditorIntegrity = { ready: false, runtime };
  waitForEditor();
})();
