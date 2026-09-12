'use strict';

(() => {
  if (globalThis.VIComponentFit?.loading || globalThis.VIComponentFit?.ready) {
    return;
  }

  globalThis.VIComponentFit = { loading: true, ready: false };

  const runtime = {
    ready: false,
    scheduled: false,
    pendingMode: null,
    originalRenderAll: null,
    originalSetSurface: null,
    lastMetrics: null,
    lastDecision: null,
  };

  const TARGETS = {
    'front-panel': {
      width: 84,
      height: 32,
      minimumScale: 0.42,
      maximumScale: 1.35,
      overviewMinimum: 0.08,
      focusMinimum: 0.72,
      focusMaximum: 1.75,
      padding: 54,
      labelMargin: 16,
    },
    'block-diagram': {
      width: 34,
      height: 28,
      minimumScale: 0.64,
      maximumScale: 1.82,
      overviewMinimum: 0.08,
      focusMinimum: 0.82,
      focusMaximum: 2.10,
      padding: 64,
      horizontalGap: 44,
      verticalGap: 30,
      bendRun: 22,
      labelGap: 18,
      labelMargin: 22,
      flowOccupancy: 0.58,
      flowStartViewportRatio: 0.18,
      metricLimit: 480,
    },
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function density() {
    return globalThis.VICanvasDensity;
  }

  function projection() {
    return globalThis.VIComponentProjection;
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function median(values) {
    const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return null;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[middle]
      : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function quantile(values, ratio) {
    const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return null;
    if (sorted.length === 1) return sorted[0];
    const offset = clamp(ratio, 0, 1) * (sorted.length - 1);
    const lower = Math.floor(offset);
    const upper = Math.ceil(offset);
    if (lower === upper) return sorted[lower];
    const weight = offset - lower;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  }

  function distance(first, second) {
    return Math.hypot(first.x - second.x, first.y - second.y);
  }

  function settings(surface = state()?.surface) {
    return TARGETS[surface] || TARGETS['block-diagram'];
  }

  function viewport() {
    const element = state()?.el?.modelGraphViewport;
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return rect.width > 40 && rect.height > 40 ? { element, rect } : null;
  }

  function visibleItem(item, surface = state()?.surface) {
    const E = editor();
    const S = state();
    return Boolean(
      item
      && item.surface === surface
      && item.surface !== 'block-diagram-inactive'
      && !item.hidden_by_structure_frame
      && item.positioned !== false
      && (S?.showTerminals || item.category !== 'terminal')
      && (!E?.visible || E.visible(item)),
    );
  }

  function projectedRecord(item, index = 0) {
    const E = editor();
    const logical = E?.effectiveBounds?.(item, index)
      || E?.getBounds?.(item, index);
    if (!logical || logical.generated) return null;
    const projected = projection()?.projectBounds?.(item, logical) || logical;
    if (!projected) return null;
    const x = finite(projected.x, NaN);
    const y = finite(projected.y, NaN);
    const width = finite(projected.width, NaN);
    const height = finite(projected.height, NaN);
    if (![x, y, width, height].every(Number.isFinite)) return null;
    if (width <= 0 || height <= 0) return null;
    return {
      item,
      x,
      y,
      width,
      height,
      centerX: x + width / 2,
      centerY: y + height / 2,
      right: x + width,
      bottom: y + height,
    };
  }

  function currentRecords(surface = state()?.surface) {
    const S = state();
    if (!S) return [];
    return [...S.objects.values()]
      .filter((item) => visibleItem(item, surface))
      .map(projectedRecord)
      .filter(Boolean);
  }

  function representativeRecords(surface = state()?.surface) {
    const records = currentRecords(surface).filter(({ item }) => {
      if (item.category === 'terminal') return false;
      if (projection()?.factorFor?.(item) >= 0.999) return false;
      const kind = [
        item.visual_kind,
        item.kind,
        item.category,
        item.class_name,
      ].filter(Boolean).join(' ').toLowerCase();
      return !kind.includes('structure')
        && !kind.includes('cluster-container')
        && !kind.includes('array-container');
    });
    return records.length
      ? records
      : currentRecords(surface).filter(
        ({ item }) => item.category !== 'terminal',
      );
  }

  function boundsFromRecords(records, margin = 0) {
    if (!records.length) return null;
    const left = Math.min(...records.map((record) => record.x)) - margin;
    const top = Math.min(...records.map((record) => record.y)) - margin;
    const right = Math.max(
      ...records.map((record) => record.x + record.width),
    ) + margin;
    const bottom = Math.max(
      ...records.map((record) => record.y + record.height),
    ) + margin;
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
    };
  }

  function wireEndpointIds(wire) {
    return [
      wire.source_terminal_id,
      wire.source_object_id,
      ...(wire.target_terminal_ids || []),
      ...(wire.target_object_ids || []),
    ].filter(Boolean);
  }

  function wiresForItem(item) {
    const S = state();
    if (!S || !item) return [];
    const explicit = new Set(item.wire_ids || []);
    return [...S.wires.values()].filter((wire) => (
      explicit.has(wire.id)
      || wireEndpointIds(wire).includes(item.id)
      || (item.terminal_ids || []).some((id) => wireEndpointIds(wire).includes(id))
    ));
  }

  function normalizePoints(points) {
    const clean = (points || []).map((point) => ({
      x: finite(point?.x, NaN),
      y: finite(point?.y, NaN),
    })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
    const result = [];
    clean.forEach((point) => {
      const previous = result.at(-1);
      if (!previous || distance(previous, point) > 0.01) result.push(point);
    });
    return result;
  }

  function routesForWire(wire) {
    const project = projection();
    const targets = wire.target_terminal_ids || [];
    const targetObjects = wire.target_object_ids || [];
    if (project?.projectedWirePoints && targets.length) {
      return targets.map((terminalId, index) => ({
        wire,
        targetTerminalId: terminalId,
        targetObjectId: targetObjects[index] || null,
        points: normalizePoints(project.projectedWirePoints(
          wire,
          terminalId,
          targetObjects[index] || null,
        )),
      })).filter((route) => route.points.length);
    }
    const points = normalizePoints(wire.route_points || []);
    return points.length
      ? [{
        wire,
        targetTerminalId: targets[0] || null,
        targetObjectId: targetObjects[0] || null,
        points,
      }]
      : [];
  }

  function wireRoutes(wires = null) {
    const S = state();
    if (!S || S.surface !== 'block-diagram') return [];
    return [...(wires || S.wires.values())].flatMap(routesForWire);
  }

  function selectedContext() {
    const S = state();
    if (!S?.selected) return { records: [], routes: [] };
    const selectedWire = S.wires.get(S.selected);
    let wires = selectedWire ? [selectedWire] : [];
    const ids = new Set();

    if (selectedWire) {
      wireEndpointIds(selectedWire).forEach((id) => ids.add(id));
    } else {
      const item = S.objects.get(S.selected);
      if (!item) return { records: [], routes: [] };
      [
        item.id,
        ...(item.terminal_ids || []),
        ...(item.child_object_ids || []),
      ].filter(Boolean).forEach((id) => ids.add(id));
      wires = wiresForItem(item);
      wires.forEach((wire) => wireEndpointIds(wire).forEach((id) => ids.add(id)));
    }

    const records = [...ids]
      .map((id) => S.objects.get(id))
      .filter((item) => visibleItem(item))
      .map(projectedRecord)
      .filter(Boolean);
    return { records, routes: wireRoutes(wires) };
  }

  function selectedRecords() {
    return selectedContext().records;
  }

  function wirePoints(routes = wireRoutes()) {
    return routes.flatMap((route) => route.points);
  }

  function projectedContentBounds({
    selectionOnly = false,
    includeWires = true,
    includeLabels = false,
  } = {}) {
    const selected = selectionOnly ? selectedContext() : null;
    const records = selected?.records || currentRecords();
    const margin = includeLabels ? settings().labelMargin || 0 : 0;
    const objectBounds = boundsFromRecords(records, margin);
    const routes = selectionOnly ? selected.routes : wireRoutes();
    const points = includeWires ? wirePoints(routes) : [];
    if (!objectBounds && !points.length) return null;
    const xs = [
      ...(objectBounds
        ? [objectBounds.x, objectBounds.x + objectBounds.width]
        : []),
      ...points.map((point) => point.x),
    ];
    const ys = [
      ...(objectBounds
        ? [objectBounds.y, objectBounds.y + objectBounds.height]
        : []),
      ...points.map((point) => point.y),
    ];
    const left = Math.min(...xs);
    const top = Math.min(...ys);
    const right = Math.max(...xs);
    const bottom = Math.max(...ys);
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
    };
  }

  function representativeMetrics(records = representativeRecords()) {
    return {
      count: records.length,
      medianWidth: median(records.map((record) => record.width)),
      medianHeight: median(records.map((record) => record.height)),
      medianCenterX: median(records.map((record) => record.centerX)),
      medianCenterY: median(records.map((record) => record.centerY)),
    };
  }

  function sampledRecords(records) {
    const limit = settings().metricLimit || records.length;
    if (records.length <= limit) return records;
    const stride = records.length / limit;
    return Array.from(
      { length: limit },
      (_, index) => records[Math.floor(index * stride)],
    );
  }

  function directionalPairs(records, axis) {
    const values = sampledRecords(records);
    const pairs = [];
    values.forEach((first) => {
      let best = null;
      let bestScore = Infinity;
      values.forEach((second) => {
        if (first === second) return;
        const primary = axis === 'x'
          ? second.centerX - first.centerX
          : second.centerY - first.centerY;
        if (primary <= 0.5) return;
        const cross = axis === 'x'
          ? Math.abs(second.centerY - first.centerY)
          : Math.abs(second.centerX - first.centerX);
        const overlap = axis === 'x'
          ? Math.min(first.bottom, second.bottom) - Math.max(first.y, second.y)
          : Math.min(first.right, second.right) - Math.max(first.x, second.x);
        const score = primary + cross * (overlap > 0 ? 0.18 : 0.72);
        if (score < bestScore) {
          bestScore = score;
          best = second;
        }
      });
      if (!best) return;
      const gap = axis === 'x'
        ? best.x - first.right
        : best.y - first.bottom;
      pairs.push({ first, second: best, gap });
    });
    return pairs;
  }

  function nodeSpacingMetrics(records = representativeRecords()) {
    const horizontalPairs = directionalPairs(records, 'x');
    const verticalPairs = directionalPairs(records, 'y');
    const horizontalGaps = horizontalPairs
      .map((pair) => pair.gap)
      .filter((value) => value >= 0);
    const verticalGaps = verticalPairs
      .map((pair) => pair.gap)
      .filter((value) => value >= 0);
    return {
      horizontalPairs,
      verticalPairs,
      medianHorizontalGap: median(horizontalGaps),
      lowerHorizontalGap: quantile(horizontalGaps, 0.25),
      medianVerticalGap: median(verticalGaps),
      lowerVerticalGap: quantile(verticalGaps, 0.25),
      horizontalOverlapCount: horizontalPairs.filter((pair) => pair.gap < 0).length,
      verticalOverlapCount: verticalPairs.filter((pair) => pair.gap < 0).length,
    };
  }

  function wireBendMetrics(routes = wireRoutes()) {
    const bendRuns = [];
    const leadRuns = [];
    routes.forEach((route) => {
      const points = route.points;
      if (points.length >= 2) {
        leadRuns.push(distance(points[0], points[1]));
        leadRuns.push(distance(points.at(-2), points.at(-1)));
      }
      for (let index = 1; index < points.length - 1; index += 1) {
        const previous = points[index - 1];
        const current = points[index];
        const next = points[index + 1];
        const first = {
          x: current.x - previous.x,
          y: current.y - previous.y,
        };
        const second = {
          x: next.x - current.x,
          y: next.y - current.y,
        };
        const cross = Math.abs(first.x * second.y - first.y * second.x);
        if (cross <= 0.01) continue;
        bendRuns.push(Math.min(distance(previous, current), distance(current, next)));
      }
    });
    const validBends = bendRuns.filter((value) => value > 0.5);
    const validLeads = leadRuns.filter((value) => value > 0.5);
    return {
      routeCount: routes.length,
      bendCount: validBends.length,
      medianBendRun: median(validBends),
      lowerBendRun: quantile(validBends, 0.25),
      medianLeadRun: median(validLeads),
    };
  }

  function flowMetrics(records = representativeRecords()) {
    const S = state();
    const byId = new Map(records.map((record) => [record.item.id, record]));
    const incoming = new Map();
    const outgoing = new Map();
    const connected = new Set();
    let forwardEdges = 0;
    let backwardEdges = 0;
    let neutralEdges = 0;

    [...(S?.wires?.values?.() || [])].forEach((wire) => {
      const source = byId.get(wire.source_object_id);
      (wire.target_object_ids || []).forEach((targetId) => {
        const target = byId.get(targetId);
        if (!source || !target) return;
        connected.add(source);
        connected.add(target);
        outgoing.set(source.item.id, (outgoing.get(source.item.id) || 0) + 1);
        incoming.set(target.item.id, (incoming.get(target.item.id) || 0) + 1);
        const delta = target.centerX - source.centerX;
        if (delta > 1) forwardEdges += 1;
        else if (delta < -1) backwardEdges += 1;
        else neutralEdges += 1;
      });
    });

    const connectedRecords = connected.size ? [...connected] : records;
    const sources = connectedRecords.filter(
      (record) => (outgoing.get(record.item.id) || 0) > 0
        && !(incoming.get(record.item.id) || 0),
    );
    const sinks = connectedRecords.filter(
      (record) => (incoming.get(record.item.id) || 0) > 0
        && !(outgoing.get(record.item.id) || 0),
    );
    const directionalEdges = forwardEdges + backwardEdges;
    const centersX = connectedRecords.map((record) => record.centerX);
    const centersY = connectedRecords.map((record) => record.centerY);
    const startX = median((sources.length ? sources : connectedRecords)
      .map((record) => record.centerX))
      ?? quantile(centersX, 0.15);
    const endX = median((sinks.length ? sinks : connectedRecords)
      .map((record) => record.centerX))
      ?? quantile(centersX, 0.85);
    return {
      connectedCount: connectedRecords.length,
      sourceCount: sources.length,
      sinkCount: sinks.length,
      forwardEdges,
      backwardEdges,
      neutralEdges,
      directionality: directionalEdges
        ? forwardEdges / directionalEdges
        : null,
      flowStartX: startX,
      flowEndX: endX,
      flowCenterX: startX != null && endX != null
        ? (startX + endX) / 2
        : median(centersX),
      flowCenterY: median(centersY),
      flowSpan: startX != null && endX != null
        ? Math.max(0, endX - startX)
        : null,
    };
  }

  function estimatedLabelWidth(record) {
    const value = String(record.item.name || record.item.label || '');
    return clamp(value.length * 6.4 + 10, 20, 180);
  }

  function labelMetrics(spacing) {
    const clearances = spacing.horizontalPairs.map(({ first, second }) => {
      const labelRight = first.x + Math.max(first.width, estimatedLabelWidth(first));
      return second.x - labelRight;
    }).filter((value) => value >= 0);
    return {
      medianLabelClearance: median(clearances),
      lowerLabelClearance: quantile(clearances, 0.25),
      medianEstimatedWidth: median(
        spacing.horizontalPairs.map(({ first }) => estimatedLabelWidth(first)),
      ),
    };
  }

  function readabilityMetrics() {
    const records = representativeRecords();
    const representative = representativeMetrics(records);
    const spacing = nodeSpacingMetrics(records);
    const bends = wireBendMetrics();
    const flow = flowMetrics(records);
    const labels = labelMetrics(spacing);
    const result = {
      surface: state()?.surface || null,
      representative,
      spacing: {
        medianHorizontalGap: spacing.medianHorizontalGap,
        lowerHorizontalGap: spacing.lowerHorizontalGap,
        medianVerticalGap: spacing.medianVerticalGap,
        lowerVerticalGap: spacing.lowerVerticalGap,
        horizontalOverlapCount: spacing.horizontalOverlapCount,
        verticalOverlapCount: spacing.verticalOverlapCount,
      },
      bends,
      flow,
      labels,
    };
    runtime.lastMetrics = result;
    return result;
  }

  function componentScaleFor(metrics, policy) {
    const width = metrics.representative.medianWidth;
    const height = metrics.representative.medianHeight;
    return width && height
      ? Math.max(policy.width / width, policy.height / height)
      : 1;
  }

  function positiveScale(target, measured) {
    return Number.isFinite(measured) && measured > 0.5
      ? target / measured
      : null;
  }

  function scaleDecision(mode, bounds, rect) {
    const policy = settings();
    const availableWidth = Math.max(80, rect.width - policy.padding * 2);
    const availableHeight = Math.max(80, rect.height - policy.padding * 2);
    const ideal = Math.min(
      availableWidth / Math.max(1, bounds.width),
      availableHeight / Math.max(1, bounds.height),
    );
    const metrics = readabilityMetrics();

    if (mode === 'overview') {
      return {
        mode,
        reason: 'full-content',
        ideal,
        candidates: { ideal },
        scale: clamp(ideal, policy.overviewMinimum, policy.maximumScale),
        metrics,
      };
    }
    if (mode === 'focus') {
      return {
        mode,
        reason: 'selected-flow',
        ideal,
        candidates: { ideal },
        scale: clamp(ideal, policy.focusMinimum, policy.focusMaximum),
        metrics,
      };
    }

    const candidates = {
      component: componentScaleFor(metrics, policy),
    };
    if (state()?.surface === 'block-diagram') {
      candidates.horizontalGap = positiveScale(
        policy.horizontalGap,
        metrics.spacing.medianHorizontalGap,
      );
      candidates.verticalGap = positiveScale(
        policy.verticalGap,
        metrics.spacing.medianVerticalGap,
      );
      candidates.bendRun = positiveScale(
        policy.bendRun,
        metrics.bends.medianBendRun,
      );
      candidates.labelGap = positiveScale(
        policy.labelGap,
        metrics.labels.medianLabelClearance,
      );
      if (
        metrics.representative.count >= 3
        && Number.isFinite(metrics.flow.flowSpan)
        && metrics.flow.flowSpan > 1
      ) {
        candidates.flowOccupancy = (
          availableWidth * policy.flowOccupancy / metrics.flow.flowSpan
        );
      }
    }

    const valid = Object.entries(candidates)
      .filter(([, value]) => Number.isFinite(value) && value > 0);
    const [reason, requested] = valid.reduce(
      (current, candidate) => (
        candidate[1] > current[1] ? candidate : current
      ),
      ['component', candidates.component || 1],
    );
    return {
      mode,
      reason,
      ideal,
      candidates,
      requested,
      scale: clamp(requested, policy.minimumScale, policy.maximumScale),
      metrics,
    };
  }

  function scaleForMode(mode, bounds, rect) {
    return scaleDecision(mode, bounds, rect).scale;
  }

  function centerForMode(mode, bounds, metrics = runtime.lastMetrics) {
    if (mode !== 'readable') {
      return {
        x: bounds.x + bounds.width / 2,
        y: bounds.y + bounds.height / 2,
      };
    }
    const representative = metrics?.representative || representativeMetrics();
    if (state()?.surface !== 'block-diagram') {
      return {
        x: representative.medianCenterX ?? bounds.x + bounds.width / 2,
        y: representative.medianCenterY ?? bounds.y + bounds.height / 2,
      };
    }
    const flow = metrics?.flow || {};
    return {
      x: flow.flowCenterX
        ?? representative.medianCenterX
        ?? bounds.x + bounds.width / 2,
      y: flow.flowCenterY
        ?? representative.medianCenterY
        ?? bounds.y + bounds.height / 2,
    };
  }

  function clampCenter(center, bounds, width, height, padding) {
    const minimumX = bounds.x - padding + width / 2;
    const maximumX = bounds.x + bounds.width + padding - width / 2;
    const minimumY = bounds.y - padding + height / 2;
    const maximumY = bounds.y + bounds.height + padding - height / 2;
    return {
      x: minimumX <= maximumX
        ? clamp(center.x, minimumX, maximumX)
        : bounds.x + bounds.width / 2,
      y: minimumY <= maximumY
        ? clamp(center.y, minimumY, maximumY)
        : bounds.y + bounds.height / 2,
    };
  }

  function boxFor(bounds, scale, rect, mode, metrics = runtime.lastMetrics) {
    const policy = settings();
    const width = rect.width / scale;
    const height = rect.height / scale;
    const padding = policy.padding / Math.max(scale, 0.05);
    const fits = (
      bounds.width <= width - padding * 2
      && bounds.height <= height - padding * 2
    );
    let center = centerForMode(mode, bounds, metrics);

    if (mode === 'readable' && fits) {
      center = {
        x: bounds.x + bounds.width / 2,
        y: bounds.y + bounds.height / 2,
      };
    } else if (
      mode === 'readable'
      && state()?.surface === 'block-diagram'
      && (metrics?.flow?.directionality ?? 0) >= 0.55
      && Number.isFinite(metrics?.flow?.flowStartX)
    ) {
      center.x = (
        metrics.flow.flowStartX
        + width * (0.5 - policy.flowStartViewportRatio)
      );
    }
    center = clampCenter(center, bounds, width, height, padding);
    return {
      x: center.x - width / 2,
      y: center.y - height / 2,
      width,
      height,
    };
  }

  function publishDecision(decision) {
    runtime.lastDecision = decision;
    const shell = state()?.el?.viEditorShell;
    if (!shell) return;
    shell.dataset.viFitReason = decision.reason;
    shell.dataset.viFitRequestedScale = finite(
      decision.requested,
      decision.scale,
    ).toFixed(3);
    const metrics = decision.metrics;
    shell.dataset.viFlowDirectionality = Number.isFinite(
      metrics?.flow?.directionality,
    )
      ? metrics.flow.directionality.toFixed(3)
      : '';
    shell.dataset.viHorizontalGap = Number.isFinite(
      metrics?.spacing?.medianHorizontalGap,
    )
      ? metrics.spacing.medianHorizontalGap.toFixed(2)
      : '';
    shell.dataset.viBendRun = Number.isFinite(metrics?.bends?.medianBendRun)
      ? metrics.bends.medianBendRun.toFixed(2)
      : '';
  }

  function fit(mode = 'readable') {
    const view = viewport();
    const activeDensity = density();
    if (!view || !activeDensity?.applyBox) return false;
    const selectionOnly = mode === 'focus';
    const bounds = projectedContentBounds({
      selectionOnly,
      includeWires: true,
      includeLabels: true,
    }) || { x: 0, y: 0, width: 640, height: 420 };
    const decision = scaleDecision(mode, bounds, view.rect);
    const applied = activeDensity.applyBox(
      boxFor(bounds, decision.scale, view.rect, mode, decision.metrics),
      mode,
    );
    if (applied) {
      publishDecision(decision);
      if (state() && mode === 'readable') {
        state().fitBox = { ...state().box };
      }
    }
    return applied;
  }

  function schedule(mode = 'readable') {
    runtime.pendingMode = mode;
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        runtime.scheduled = false;
        const pending = runtime.pendingMode || 'readable';
        runtime.pendingMode = null;
        fit(pending);
      });
    });
  }

  function modeForButton(button) {
    if (button.id === 'model-graph-overview') return 'overview';
    if (button.id === 'model-graph-focus') return 'focus';
    return 'readable';
  }

  function bindControls() {
    document.addEventListener('click', (event) => {
      const button = event.target.closest?.(
        '#model-graph-fit,#model-graph-overview,#model-graph-focus',
      );
      if (button) schedule(modeForButton(button));
    }, true);
    document.addEventListener('dblclick', (event) => {
      const viewportElement = state()?.el?.modelGraphViewport;
      if (
        viewportElement?.contains(event.target)
        && !event.target.closest?.('.vi-object,.vi-wire-group')
      ) {
        schedule('readable');
      }
    }, true);
  }

  function wrapEditor() {
    const E = editor();
    if (!E || runtime.originalRenderAll) return false;
    runtime.originalRenderAll = E.renderAll;
    runtime.originalSetSurface = E.setSurface;
    E.renderAll = function renderAllWithProjectedFit(fitRequested = false) {
      const result = runtime.originalRenderAll.call(E, false);
      const hasSaved = density()?.runtime?.surfaceViews?.has(state()?.surface);
      if (fitRequested || !hasSaved) schedule('readable');
      return result;
    };
    E.setSurface = function setSurfaceWithProjectedFit(
      surface,
      fitRequested = true,
    ) {
      const hasSaved = density()?.runtime?.surfaceViews?.has(surface);
      const result = runtime.originalSetSurface.call(E, surface, false);
      if (!hasSaved && fitRequested) schedule('readable');
      return result;
    };
    return true;
  }

  function install() {
    const activeDensity = density();
    const activeProjection = projection();
    if (
      runtime.ready
      || !activeDensity?.ready
      || !activeProjection?.ready
      || !state()?.el?.modelGraphViewport
    ) {
      return false;
    }
    runtime.ready = true;
    if (activeDensity.POLICIES) {
      Object.assign(activeDensity.POLICIES['front-panel'], {
        minReadableScale: TARGETS['front-panel'].minimumScale,
        maxReadableScale: TARGETS['front-panel'].maximumScale,
      });
      Object.assign(activeDensity.POLICIES['block-diagram'], {
        minReadableScale: TARGETS['block-diagram'].minimumScale,
        maxReadableScale: TARGETS['block-diagram'].maximumScale,
      });
    }
    activeDensity.fit = fit;
    activeDensity.projectedContentBounds = projectedContentBounds;
    activeDensity.representativeMetrics = representativeMetrics;
    activeDensity.readabilityMetrics = readabilityMetrics;
    wrapEditor();
    bindControls();
    document.addEventListener(
      'vi-structure-frame-changed',
      () => schedule('readable'),
    );
    globalThis.VIComponentFit = {
      loading: false,
      ready: true,
      runtime,
      TARGETS,
      currentRecords,
      representativeRecords,
      representativeMetrics,
      wireRoutes,
      selectedContext,
      projectedContentBounds,
      nodeSpacingMetrics,
      wireBendMetrics,
      flowMetrics,
      labelMetrics,
      readabilityMetrics,
      scaleDecision,
      scaleForMode,
      boxFor,
      fit,
      schedule,
    };
    if (state()?.vi) schedule('readable');
    return true;
  }

  function waitForDependencies(attempt = 0) {
    if (install()) return;
    if (attempt < 400) {
      setTimeout(() => waitForDependencies(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentFit = {
      loading: false,
      ready: false,
      error: 'component projection dependencies did not become ready',
      runtime,
      TARGETS,
    };
  }

  waitForDependencies();
})();
