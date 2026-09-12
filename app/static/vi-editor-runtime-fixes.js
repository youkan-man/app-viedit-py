'use strict';

(() => {
  const MODULES = [
    ['vi-editor-realism', '/static/vi-editor-realism.js?v=2'],
    ['vi-editor-persistence', '/static/vi-editor-persistence.js?v=1'],
    ['vi-editor-actions', '/static/vi-editor-actions.js?v=1'],
    ['vi-editor-inline-properties', '/static/vi-editor-inline-properties.js?v=1'],
    ['vi-editor-ui-labels', '/static/vi-editor-ui-labels.js?v=1'],
    ['component-properties-semantic', '/static/component-properties-semantic.js?v=1'],
    ['vi-editor-type-definitions', '/static/vi-editor-type-definitions.js?v=1'],
    ['vi-editor-integrity', '/static/vi-editor-integrity.js?v=1'],
    ['vi-editor-density', '/static/vi-editor-density.js?v=1'],
    ['vi-editor-density-toolbar', '/static/vi-editor-density-toolbar.js?v=1'],
    ['vi-editor-density-memory', '/static/vi-editor-density-memory.js?v=1'],
    ['vi-editor-readability', '/static/vi-editor-readability.js?v=1'],
    [
      'vi-editor-component-visuals',
      '/static/vi-editor-component-visuals.js?v=1',
      'VIComponentVisuals',
    ],
    [
      'vi-editor-component-primer',
      '/static/vi-editor-component-primer.js?v=1',
      'VIComponentPrimer',
    ],
    [
      'vi-editor-component-projection',
      '/static/vi-editor-component-projection.js?v=1',
      'VIComponentProjection',
    ],
    [
      'vi-editor-component-anchor',
      '/static/vi-editor-component-anchor.js?v=1',
      'VIComponentAnchors',
    ],
    [
      'vi-editor-component-coordinate-space',
      '/static/vi-editor-component-coordinate-space.js?v=1',
      'VIComponentCoordinateSpace',
    ],
    [
      'vi-editor-component-terminal-visual',
      '/static/vi-editor-component-terminal-visual.js?v=1',
      'VIComponentTerminalVisual',
    ],
    [
      'vi-editor-component-geometry-consistency',
      '/static/vi-editor-component-geometry-consistency.js?v=1',
      'VIComponentGeometryConsistency',
    ],
    [
      'vi-editor-component-fit',
      '/static/vi-editor-component-fit.js?v=1',
      'VIComponentFit',
    ],
    [
      'vi-editor-navigation-workflow',
      '/static/vi-editor-navigation-workflow.js?v=1',
      'VINavigationWorkflow',
    ],
    [
      'vi-editor-navigation-keyboard-guard',
      '/static/vi-editor-navigation-keyboard-guard.js?v=1',
      'VINavigationKeyboardGuard',
    ],
    [
      'vi-editor-multi-selection-prelude',
      '/static/vi-editor-multi-selection-prelude.js?v=1',
      'VIMultiSelectionPrelude',
    ],
    [
      'vi-editor-multi-selection',
      '/static/vi-editor-multi-selection.js?v=1',
      'VIMultiSelection',
    ],
    [
      'vi-editor-multi-selection-polish',
      '/static/vi-editor-multi-selection-polish.js?v=1',
      'VIMultiSelectionPolish',
    ],
    [
      'vi-editor-compact-resize-handles',
      '/static/vi-editor-compact-resize-handles.js?v=1',
      'VICompactResizeHandles',
    ],
    [
      'vi-editor-wire-stability',
      '/static/vi-editor-wire-stability.js?v=1',
      'VIWireStability',
    ],
  ];

  function loadScript(flag, src) {
    const existing = document.querySelector(`script[data-${flag}]`);
    if (existing) {
      if (existing.dataset.loaded === 'true') return Promise.resolve();
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', reject, { once: true });
      });
    }
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = false;
      script.setAttribute(`data-${flag}`, 'true');
      script.addEventListener('load', () => {
        script.dataset.loaded = 'true';
        resolve();
      }, { once: true });
      script.addEventListener('error', reject, { once: true });
      document.head.appendChild(script);
    });
  }

  async function waitForReady(globalName, flag) {
    if (!globalName) return;
    for (let attempt = 0; attempt < 480; attempt += 1) {
      const value = globalThis[globalName];
      if (value?.ready === true) return;
      if (value?.error) {
        throw new Error(`${flag} failed to initialize: ${value.error}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error(`${flag} did not become ready`);
  }

  async function loadModules() {
    const loaded = [];
    for (const [flag, src, readyGlobal] of MODULES) {
      await loadScript(flag, src);
      await waitForReady(readyGlobal, flag);
      loaded.push(flag);
    }
    globalThis.VIRuntimeFixes = {
      ready: true,
      modules: loaded,
    };
  }

  globalThis.VIRuntimeFixes = { ready: false, modules: [] };
  void loadModules().catch((error) => {
    globalThis.VIRuntimeFixes = {
      ready: false,
      error: String(error?.message || error),
      modules: [],
    };
  });
})();
