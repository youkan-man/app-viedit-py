'use strict';

(() => {
  const runtime = {
    ready: false,
    scheduled: false,
    pendingMode: null,
    originalRenderAll: null,
    originalSetSurface: null,
  };

  const TARGETS = {
    'front-panel': {
      width: 92,
      height: 34,
      minimumScale: 0.62,
      maximumScale: 1.28,
      overviewMinimum: 0.08,
      focusMinimum: 0.82,
      focusMaximum: 1.65,
      padding: 54,
    },
    'block-diagram': {
      width: 44,
      height: 30,
      minimumScale: 0.68,
      maximumScale: 1.30,
      overviewMinimum: 0.08,
      focusMinimum: 0.84,
      focusMaximum: 1.60,
      padding: 58,
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
      && !item.bounds?.generated
      && (S?.showTerminals || item.category !== 'terminal')
      && (!E?.visible || E.visible(item)),
    );
  }

  function projectedRecord(item, index = 0) {
    const E = editor();
    const logical = E?.effectiveBounds?.(item, index) || E?.getBounds?.(item, index);
    const projected = projection()?.projectBounds?.(item, logical) || logical;
    if (!projected) return null;
    const x = finite(projected.x, NaN);
    const y = finite(projected.y, NaN);
    const width = finite(projected.width, NaN);
    const height = finite(projected.height, NaN);
    if (![x, y, width, height].every(Number.isFinite)) return null;
    if (width <= 0 || height <= 0) return null;
    return { item, x, y, width, height };
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
    return records.length ? records : currentRecords(surface).filter(
      ({ item }) => item.category !== 'terminal',
    );
  }

  function boundsFromRecords(records) {
    if (!records.length) return null;
    const left = Math.min(...records.map((record) => record.x));
    const top = Math.min(...records.map((record) => record.y));
    const right = Math.max(...records.map((record) => record.x + record.width));
    const bottom = Math.max(...records.map((record) => record.y + record.height));
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
    };
  }

  function selectedRecords() {
    const S = state();
    if (!S?.selected) return [];
    const wire = S.wires.get(S.selected);
    if (wire) {
      const ids = [
        wire.source_terminal_id,
        wire.source_object_id,
        ...(wire.target_terminal_ids || []),
        ...(wire.target_object_ids || []),
      ].filter(Boolean);
      return ids.map((id) => S.objects.get(id))
        .filter((item) => visibleItem(item))
        .map(projectedRecord)
        .filter(Boolean);
    }
    const item = S.objects.get(S.selected);
    if (!item) return [];
    const ids = new Set([
      item.id,
      ...(item.terminal_ids || []),
      ...(item.child_object_ids || []),
    ]);
    return [...ids].map((id) => S.objects.get(id))
      .filter((record) => visibleItem(record))
      .map(projectedRecord)
      .filter(Boolean);
  }

  function wirePoints() {
    const S = state();
    const project = projection();
    if (!S || S.surface !== 'block-diagram') return [];
    return [...S.wires.values()].flatMap((wire) => {
      if (project?.projectedWirePoints) {
        return (wire.target_terminal_ids || []).flatMap((terminalId, index) => (
          project.projectedWirePoints(
            wire,
            terminalId,
            wire.target_object_ids?.[index] || null,
          )
        ));
      }
      return wire.route_points || [];
    }).map((point) => ({
      x: finite(point?.x, NaN),
      y: finite(point?.y, NaN),
    })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  }

  function projectedContentBounds({ selectionOnly = false, includeWires = true } = {}) {
    const records = selectionOnly ? selectedRecords() : currentRecords();
    const objectBounds = boundsFromRecords(records);
    const points = includeWires && !selectionOnly ? wirePoints() : [];
    if (!objectBounds && !points.length) return null;
    const xs = [
      ...(objectBounds ? [objectBounds.x, objectBounds.x + objectBounds.width] : []),
      ...points.map((point) => point.x),
    ];
    const ys = [
      ...(objectBounds ? [objectBounds.y, objectBounds.y + objectBounds.height] : []),
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

  function representativeMetrics() {
    const records = representativeRecords();
    return {
      count: records.length,
      medianWidth: median(records.map((record) => record.width)),
      medianHeight: median(records.map((record) => record.height)),
      medianCenterX: median(records.map((record) => record.x + record.width / 2)),
      medianCenterY: median(records.map((record) => record.y + record.height / 2)),
    };
  }

  function scaleForMode(mode, bounds, rect) {
    const policy = settings();
    const availableWidth = Math.max(80, rect.width - policy.padding * 2);
    const availableHeight = Math.max(80, rect.height - policy.padding * 2);
    const ideal = Math.min(
      availableWidth / Math.max(1, bounds.width),
      availableHeight / Math.max(1, bounds.height),
    );
    if (mode === 'overview') {
      return clamp(ideal, policy.overviewMinimum, policy.maximumScale);
    }
    if (mode === 'focus') {
      return clamp(ideal, policy.focusMinimum, policy.focusMaximum);
    }
    const metrics = representativeMetrics();
    const componentScale = metrics.medianWidth && metrics.medianHeight
      ? Math.max(
        policy.width / metrics.medianWidth,
        policy.height / metrics.medianHeight,
      )
      : 1;
    return clamp(componentScale, policy.minimumScale, policy.maximumScale);
  }

  function centerForMode(mode, bounds) {
    if (mode !== 'readable') {
      return {
        x: bounds.x + bounds.width / 2,
        y: bounds.y + bounds.height / 2,
      };
    }
    const metrics = representativeMetrics();
    return {
      x: metrics.medianCenterX ?? bounds.x + bounds.width / 2,
      y: metrics.medianCenterY ?? bounds.y + bounds.height / 2,
    };
  }

  function boxFor(bounds, scale, rect, mode) {
    const width = rect.width / scale;
    const height = rect.height / scale;
    let center = centerForMode(mode, bounds);
    if (
      mode === 'readable'
      && bounds.width <= width - settings().padding * 2
      && bounds.height <= height - settings().padding * 2
    ) {
      center = {
        x: bounds.x + bounds.width / 2,
        y: bounds.y + bounds.height / 2,
      };
    }
    return {
      x: center.x - width / 2,
      y: center.y - height / 2,
      width,
      height,
    };
  }

  function fit(mode = 'readable') {
    const view = viewport();
    const activeDensity = density();
    if (!view || !activeDensity?.applyBox) return false;
    const selectionOnly = mode === 'focus';
    const bounds = projectedContentBounds({
      selectionOnly,
      includeWires: mode === 'overview',
    }) || { x: 0, y: 0, width: 640, height: 420 };
    const scale = scaleForMode(mode, bounds, view.rect);
    const applied = activeDensity.applyBox(
      boxFor(bounds, scale, view.rect, mode),
      mode,
    );
    if (applied && state()) {
      state().fitBox = mode === 'readable' ? { ...state().box } : state().fitBox;
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

  function bindControls() {
    document.addEventListener('click', (event) => {
      const button = event.target.closest?.(
        '#model-graph-fit,#model-graph-overview,#model-graph-focus',
      );
      if (!button) return;
      const mode = button.id === 'model-graph-overview'
        ? 'overview'
        : button.id === 'model-graph-focus'
          ? 'focus'
          : 'readable';
      schedule(mode);
    }, true);
    state()?.el?.modelGraphViewport?.addEventListener('dblclick', (event) => {
      if (!event.target.closest?.('.vi-object,.vi-wire-group')) schedule('readable');
    }, true);
  }

  function wrapEditor() {
    const E = editor();
    if (!E || runtime.originalRenderAll) return false;
    runtime.originalRenderAll = E.renderAll;
    runtime.originalSetSurface = E.setSurface;
    E.renderAll = function renderAllWithProjectedFit(fitRequested = false) {
      const result = runtime.originalRenderAll.call(E, false);
      if (fitRequested || !density()?.runtime?.surfaceViews?.has(state()?.surface)) {
        schedule('readable');
      }
      return result;
    };
    E.setSurface = function setSurfaceWithProjectedFit(surface, fitRequested = true) {
      const hasSaved = density()?.runtime?.surfaceViews?.has(surface);
      const result = runtime.originalSetSurface.call(E, surface, false);
      if (fitRequested || !hasSaved) schedule('readable');
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
    wrapEditor();
    bindControls();
    globalThis.VIComponentFit = {
      ready: true,
      runtime,
      TARGETS,
      currentRecords,
      representativeRecords,
      representativeMetrics,
      projectedContentBounds,
      scaleForMode,
      fit,
      schedule,
    };
    if (state()?.vi) schedule('readable');
    return true;
  }

  function waitForDependencies(attempt = 0) {
    if (install()) return;
    if (attempt < 400) setTimeout(() => waitForDependencies(attempt + 1), 25);
  }

  globalThis.VIComponentFit = { ready: false, runtime, TARGETS };
  waitForDependencies();
})();
