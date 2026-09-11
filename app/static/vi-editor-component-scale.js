'use strict';

(() => {
  const runtime = {
    ready: false,
    scheduled: false,
    lastMeasurement: null,
    originalDensityFit: null,
    originalEditorFit: null,
    originalInstall: null,
  };

  const POLICIES = {
    'front-panel': {
      minScale: 1,
      maxScale: 1.45,
      targetWidth: 96,
      targetHeight: 40,
    },
    'block-diagram': {
      minScale: 1,
      maxScale: 1.35,
      targetWidth: 50,
      targetHeight: 38,
    },
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function density() {
    return globalThis.VICanvasDensity;
  }

  function state() {
    return editor()?.S;
  }

  function shell() {
    return document.querySelector('#vi-editor-shell');
  }

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function median(values) {
    const sorted = values
      .map((value) => finite(value, Number.NaN))
      .filter(Number.isFinite)
      .sort((first, second) => first - second);
    if (!sorted.length) return 0;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[middle]
      : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function nativeSurface(item) {
    if (item?.native_surface) return item.native_surface;
    return item?.surface === 'block-diagram-inactive'
      ? 'block-diagram'
      : item?.surface;
  }

  function boundsFor(item) {
    const E = editor();
    return E?.effectiveBounds?.(item)
      || E?.getBounds?.(item)
      || item?.bounds
      || null;
  }

  function positioned(item, bounds) {
    if (!item || !bounds || item.positioned === false) return false;
    if (item.hidden_by_structure_frame) return false;
    if (item.surface === 'block-diagram-inactive') return false;
    const source = String(
      bounds.position_source
      || item.position_source
      || item.layout_source
      || '',
    ).toLowerCase();
    if (source.includes('fallback') || source.includes('synthetic-grid')) return false;
    const width = finite(bounds.width);
    const height = finite(bounds.height);
    return width >= 6 && height >= 6;
  }

  function isStructure(item) {
    return item?.visual_kind === 'structure'
      || String(item?.kind || '').startsWith('structure');
  }

  function isRepresentative(item, surface) {
    const bounds = boundsFor(item);
    if (!positioned(item, bounds) || nativeSurface(item) !== surface) return false;
    if (surface === 'front-panel') {
      return item.category === 'control' || item.category === 'indicator';
    }
    return item.category === 'node';
  }

  function representativeItems(surface = state()?.surface) {
    const S = state();
    if (!S || !POLICIES[surface]) return [];
    const records = [...S.objects.values()]
      .filter((item) => isRepresentative(item, surface))
      .map((item) => ({ item, bounds: boundsFor(item) }))
      .filter((record) => record.bounds);

    if (surface === 'front-panel') {
      const leaves = records.filter((record) => (
        record.item.visual_kind !== 'cluster'
        && record.item.data_type !== 'cluster'
        && !(record.item.child_object_ids || []).length
      ));
      return leaves.length >= 2 ? leaves : records;
    }
    const ordinaryNodes = records.filter((record) => !isStructure(record.item));
    return ordinaryNodes.length >= 2 ? ordinaryNodes : records;
  }

  function robustRecords(records) {
    if (records.length < 5) return records;
    const widths = records.map((record) => finite(record.bounds.width));
    const heights = records.map((record) => finite(record.bounds.height));
    const medianWidth = Math.max(1, median(widths));
    const medianHeight = Math.max(1, median(heights));
    const filtered = records.filter((record) => {
      const width = finite(record.bounds.width);
      const height = finite(record.bounds.height);
      return width >= medianWidth * 0.24
        && width <= medianWidth * 4.2
        && height >= medianHeight * 0.24
        && height <= medianHeight * 4.2;
    });
    return filtered.length >= 2 ? filtered : records;
  }

  function centerFor(records) {
    if (!records.length) return { x: 0, y: 0 };
    return {
      x: median(records.map((record) => (
        finite(record.bounds.x) + finite(record.bounds.width) / 2
      ))),
      y: median(records.map((record) => (
        finite(record.bounds.y) + finite(record.bounds.height) / 2
      ))),
    };
  }

  function scaleFor(records, surface) {
    const policy = POLICIES[surface];
    if (!policy || !records.length) return policy?.minScale || 1;
    const candidates = robustRecords(records);
    const width = Math.max(1, median(
      candidates.map((record) => finite(record.bounds.width)),
    ));
    const height = Math.max(1, median(
      candidates.map((record) => finite(record.bounds.height)),
    ));
    const widthScale = policy.targetWidth / width;
    const heightScale = policy.targetHeight / height;
    // Height is the strongest readability signal for LabVIEW controls and
    // nodes. Width still prevents very small square controls from remaining
    // unreadable, without blowing up long string/path controls.
    const desired = Math.max(heightScale, Math.min(widthScale, heightScale * 1.35));
    return clamp(desired, policy.minScale, policy.maxScale);
  }

  function viewportRect() {
    return state()?.el?.modelGraphViewport?.getBoundingClientRect?.() || null;
  }

  function measure(surface = state()?.surface) {
    const records = representativeItems(surface);
    const robust = robustRecords(records);
    const center = centerFor(robust.length ? robust : records);
    const scale = scaleFor(robust.length ? robust : records, surface);
    const measurement = {
      surface,
      objectCount: records.length,
      representativeCount: robust.length,
      medianWidth: median(robust.map((record) => finite(record.bounds.width))),
      medianHeight: median(robust.map((record) => finite(record.bounds.height))),
      center,
      scale,
      policy: { ...POLICIES[surface] },
    };
    runtime.lastMeasurement = measurement;
    return measurement;
  }

  function fitReadable(surface = state()?.surface) {
    const S = state();
    const canvasDensity = density();
    const rect = viewportRect();
    const measurement = measure(surface);
    if (!S || !rect || rect.width < 10 || rect.height < 10) return null;

    const scale = Math.max(1, measurement.scale || 1);
    const width = rect.width / scale;
    const height = rect.height / scale;
    const box = {
      x: measurement.center.x - width / 2,
      y: measurement.center.y - height / 2,
      width,
      height,
    };
    if (typeof canvasDensity?.applyBox === 'function') {
      canvasDensity.applyBox(box, 'readable', { remember: true });
    } else {
      S.box = { ...box };
      S.el.modelGraphSvg.setAttribute(
        'viewBox',
        `${box.x} ${box.y} ${box.width} ${box.height}`,
      );
    }
    const editorShell = shell();
    if (editorShell) {
      editorShell.dataset.viComponentScalePolicy = 'native-readable';
      editorShell.dataset.viComponentScale = scale.toFixed(3);
    }
    return { ...measurement, box };
  }

  function modeFrom(args) {
    const requested = args[0];
    if (requested == null || requested === '') return 'readable';
    if (typeof requested === 'string') return requested;
    return requested?.mode || 'readable';
  }

  function patchFit() {
    const canvasDensity = density();
    const E = editor();
    if (!canvasDensity || !E) return false;

    if (!runtime.originalDensityFit && typeof canvasDensity.fit === 'function') {
      runtime.originalDensityFit = canvasDensity.fit.bind(canvasDensity);
      canvasDensity.fit = (...args) => {
        const mode = modeFrom(args);
        if (mode === 'readable' || mode === 'fit') return fitReadable();
        return runtime.originalDensityFit(...args);
      };
    }

    if (!runtime.originalEditorFit && typeof E.fit === 'function') {
      runtime.originalEditorFit = E.fit.bind(E);
      E.fit = (...args) => {
        const mode = modeFrom(args);
        if (mode === 'readable' || mode === 'fit') return fitReadable();
        return runtime.originalEditorFit(...args);
      };
    }
    return true;
  }

  function shouldRepairInitialView() {
    const S = state();
    const canvasDensity = density();
    if (!S?.vi || !POLICIES[S.surface]) return false;
    const mode = canvasDensity?.runtime?.currentMode || 'readable';
    const scale = finite(canvasDensity?.runtime?.currentScale, 1);
    return ['readable', 'fit', 'initial'].includes(mode) || scale < 0.9;
  }

  function scheduleReadableFit({ force = false } = {}) {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        runtime.scheduled = false;
        patchFit();
        if (force || shouldRepairInitialView()) fitReadable();
      });
    });
  }

  function wrapInstall() {
    const E = editor();
    if (!E || runtime.originalInstall || typeof E.install !== 'function') {
      return false;
    }
    runtime.originalInstall = E.install;
    E.install = function installWithNativeComponentScale(vi) {
      const result = runtime.originalInstall.call(E, vi);
      scheduleReadableFit({ force: true });
      return result;
    };
    return true;
  }

  function install() {
    if (runtime.ready || !editor() || !density()) return false;
    runtime.ready = true;
    patchFit();
    wrapInstall();
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      button.addEventListener('click', () => scheduleReadableFit());
    });
    window.addEventListener('resize', () => scheduleReadableFit());
    if (state()?.vi) scheduleReadableFit({ force: true });
    globalThis.VISemanticComponentScale = {
      ready: true,
      runtime,
      policies: POLICIES,
      representativeItems,
      measure,
      fitReadable,
      scheduleReadableFit,
    };
    return true;
  }

  function waitForDependencies(attempt = 0) {
    if (install()) return;
    if (attempt < 360) setTimeout(() => waitForDependencies(attempt + 1), 25);
  }

  globalThis.VISemanticComponentScale = { ready: false, runtime };
  waitForDependencies();
})();
