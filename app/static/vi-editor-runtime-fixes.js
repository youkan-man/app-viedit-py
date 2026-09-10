'use strict';

(() => {
  const MODULES = [
    ['vi-editor-realism', '/static/vi-editor-realism.js?v=1'],
    ['vi-editor-persistence', '/static/vi-editor-persistence.js?v=1'],
    ['vi-editor-actions', '/static/vi-editor-actions.js?v=1'],
    ['vi-editor-inline-properties', '/static/vi-editor-inline-properties.js?v=1'],
    ['vi-editor-ui-labels', '/static/vi-editor-ui-labels.js?v=1'],
    ['component-properties-semantic', '/static/component-properties-semantic.js?v=1'],
    ['vi-editor-type-definitions', '/static/vi-editor-type-definitions.js?v=1'],
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

  async function loadModules() {
    for (const [flag, src] of MODULES) {
      await loadScript(flag, src);
    }
    globalThis.VIRuntimeFixes = {
      ready: true,
      modules: MODULES.map(([flag]) => flag),
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
