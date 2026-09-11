'use strict';

(() => {
  const runtime = {
    ready: false,
    scheduled: false,
    originalInstall: null,
    originalRenderCanvas: null,
    report: null,
  };

  const TARGETS = {
    terminal: { width: 8, height: 8 },
    'front-boolean': { width: 28, height: 28 },
    'front-field': { width: 96, height: 30 },
    'front-text': { width: 116, height: 30 },
    'front-container': { width: 180, height: 116 },
    'block-primitive': { width: 28, height: 28 },
    'block-constant': { width: 58, height: 24 },
    'block-subvi': { width: 36, height: 36 },
    'block-structure': { width: 180, height: 116 },
    'block-node': { width: 40, height: 32 },
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

  function normalizedText(item) {
    return [
      item?.kind,
      item?.visual_kind,
      item?.data_type,
      item?.class_name,
      item?.name,
    ].filter(Boolean).join(' ').toLowerCase();
  }

  function profileFor(item) {
    if (item?.category === 'terminal') return 'terminal';
    const text = normalizedText(item);
    if (item?.surface === 'front-panel') {
      if (/cluster|array|table|tab|container|group/.test(text)) {
        return 'front-container';
      }
      if (/bool|boolean|led|switch|button|stop/.test(text)) {
        return 'front-boolean';
      }
      if (/string|path|text|visa|resource/.test(text)) return 'front-text';
      return 'front-field';
    }
    if (/structure|case|sequence|event|loop|while|for-loop/.test(text)) {
      return 'block-structure';
    }
    if (/subvi|sub-vi|call|invoke|visa|function/.test(text)) return 'block-subvi';
    if (/constant|string-constant|numeric-constant|boolean-constant/.test(text)) {
      return 'block-constant';
    }
    if (/primitive|add|subtract|multiply|divide|comparison|logic|select/.test(text)) {
      return 'block-primitive';
    }
    return 'block-node';
  }

  function targetFor(item) {
    return TARGETS[profileFor(item)] || TARGETS['block-node'];
  }

  function hasAuthoritativeBounds(item) {
    const bounds = item?.bounds;
    if (!bounds || item?.positioned === false) return false;
    const values = [bounds.x, bounds.y, bounds.width, bounds.height].map(Number);
    if (!values.every(Number.isFinite)) return false;
    if (values[2] <= 0 || values[3] <= 0) return false;
    return true;
  }

  function fallbackPosition(item, index) {
    const S = state();
    const parentId = item?.parent_object_id || item?.owner_object_id;
    const parent = parentId ? S?.objects.get(parentId) : null;
    const parentBounds = parent && hasAuthoritativeBounds(parent)
      ? parent.bounds
      : null;
    if (parentBounds) {
      const column = index % 4;
      const row = Math.floor(index / 4) % 5;
      return {
        x: finite(parentBounds.x) + 24 + column * 64,
        y: finite(parentBounds.y) + 32 + row * 54,
      };
    }
    return {
      x: 40 + (index % 5) * 132,
      y: 45 + Math.floor(index / 5) * 74,
    };
  }

  function fallbackFor(item, index) {
    const target = targetFor(item);
    const position = fallbackPosition(item, index);
    return {
      x: position.x,
      y: position.y,
      width: target.width,
      height: target.height,
      generated: true,
      geometry_profile: profileFor(item),
      geometry_source: 'kind-specific-fallback',
    };
  }

  function seedFallbackGeometry() {
    const S = state();
    if (!S?.objects || !S.fallback) return 0;
    let changed = 0;
    [...S.objects.values()].forEach((item, index) => {
      item.geometry_profile = profileFor(item);
      item.geometry_source = hasAuthoritativeBounds(item)
        ? 'authoritative-bounds'
        : 'kind-specific-fallback';
      if (hasAuthoritativeBounds(item)) return;
      const next = fallbackFor(item, index);
      const current = S.fallback.get(item.id);
      if (
        !current
        || current.width !== next.width
        || current.height !== next.height
        || current.x !== next.x
        || current.y !== next.y
      ) {
        S.fallback.set(item.id, next);
        changed += 1;
      }
    });
    return changed;
  }

  function median(values) {
    const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return null;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[middle]
      : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function canvasScale() {
    const S = state();
    const viewport = S?.el?.modelGraphViewport?.getBoundingClientRect();
    const box = S?.box;
    if (!viewport || !box?.width || !box?.height) return null;
    return Math.min(viewport.width / box.width, viewport.height / box.height);
  }

  function geometrySource(item) {
    return item?.geometry_source
      || (hasAuthoritativeBounds(item) ? 'authoritative-bounds' : 'legacy-fallback');
  }

  function bodyElement(group) {
    return group.querySelector([
      '.vi-front-panel-body',
      '.vi-block-node-body',
      '.vi-terminal-body',
      '.vi-cluster-frame',
      '.vi-structure-frame',
    ].join(','));
  }

  function measure() {
    const S = state();
    const root = S?.el?.modelGraphSvg;
    if (!S || !root) return null;
    const scale = canvasScale();
    const records = [];
    root.querySelectorAll('[data-object-id]').forEach((group) => {
      const item = S.objects.get(group.dataset.objectId);
      const body = bodyElement(group);
      if (!item || !body) return;
      const bodyRect = body.getBoundingClientRect();
      const groupRect = group.getBoundingClientRect();
      const effective = editor()?.effectiveBounds?.(item) || null;
      const record = {
        id: item.id,
        name: item.name || item.id,
        surface: item.surface,
        category: item.category,
        kind: item.kind,
        profile: profileFor(item),
        source: geometrySource(item),
        positioned: item.positioned !== false,
        effective_width: finite(effective?.width, null),
        effective_height: finite(effective?.height, null),
        body_screen_width: bodyRect.width,
        body_screen_height: bodyRect.height,
        group_screen_width: groupRect.width,
        group_screen_height: groupRect.height,
      };
      records.push(record);
      group.dataset.geometryProfile = record.profile;
      group.dataset.geometrySource = record.source;
    });

    const profiles = {};
    Object.keys(TARGETS).forEach((profile) => {
      const matching = records.filter((record) => record.profile === profile);
      if (!matching.length) return;
      profiles[profile] = {
        count: matching.length,
        authoritative: matching.filter(
          (record) => record.source === 'authoritative-bounds'
        ).length,
        fallback: matching.filter(
          (record) => record.source !== 'authoritative-bounds'
        ).length,
        median_effective_width: median(matching.map((record) => record.effective_width)),
        median_effective_height: median(matching.map((record) => record.effective_height)),
        median_screen_width: median(matching.map((record) => record.body_screen_width)),
        median_screen_height: median(matching.map((record) => record.body_screen_height)),
        target: { ...TARGETS[profile] },
      };
    });
    runtime.report = {
      job_id: S.job?.job_id || null,
      surface: S.surface,
      scale,
      object_count: records.length,
      profiles,
      records,
    };
    return runtime.report;
  }

  function decorate() {
    seedFallbackGeometry();
    measure();
  }

  function schedule() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      runtime.scheduled = false;
      decorate();
    });
  }

  function wrapEditor() {
    const E = editor();
    if (!E || runtime.originalInstall) return false;
    runtime.originalInstall = E.install;
    runtime.originalRenderCanvas = E.renderCanvas;

    E.install = function installWithComponentGeometry(vi) {
      const result = runtime.originalInstall.call(E, vi);
      const changed = seedFallbackGeometry();
      if (changed) runtime.originalRenderCanvas.call(E);
      schedule();
      return result;
    };

    E.renderCanvas = function renderCanvasWithComponentGeometry(...args) {
      seedFallbackGeometry();
      const result = runtime.originalRenderCanvas.apply(E, args);
      schedule();
      return result;
    };
    return true;
  }

  function install() {
    const E = editor();
    const root = document.querySelector('#model-graph-svg');
    if (runtime.ready || !E || !root) return false;
    runtime.ready = true;
    wrapEditor();
    const changed = seedFallbackGeometry();
    if (changed && state()?.vi) runtime.originalRenderCanvas.call(E);
    const observer = new MutationObserver(schedule);
    observer.observe(root, { childList: true });
    globalThis.VIComponentGeometry = {
      ready: true,
      runtime,
      TARGETS,
      profileFor,
      targetFor,
      hasAuthoritativeBounds,
      fallbackFor,
      seedFallbackGeometry,
      measure,
      report: () => runtime.report || measure(),
    };
    schedule();
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 360) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIComponentGeometry = { ready: false, runtime, TARGETS };
  waitForEditor();
})();
