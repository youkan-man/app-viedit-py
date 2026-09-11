'use strict';

(() => {
  const runtime = {
    ready: false,
    loading: false,
    attempts: 0,
  };

  function loadPolicy() {
    if (runtime.ready || runtime.loading) return;
    if (
      !globalThis.VIRuntimeFixes?.ready
      || !globalThis.VICanvasDensity?.ready
      || !globalThis.VICanvasDensityMemory?.ready
      || !globalThis.VISemanticEditor
    ) {
      runtime.attempts += 1;
      if (runtime.attempts < 600) setTimeout(loadPolicy, 25);
      return;
    }

    const existing = document.querySelector(
      'script[data-vi-editor-component-scale-policy]',
    );
    if (existing) {
      if (globalThis.VISemanticComponentScale?.ready) runtime.ready = true;
      else setTimeout(loadPolicy, 25);
      return;
    }

    runtime.loading = true;
    const script = document.createElement('script');
    script.src = '/static/vi-editor-component-scale.js?v=2';
    script.async = false;
    script.dataset.viEditorComponentScalePolicy = '';
    script.addEventListener('load', () => {
      runtime.loading = false;
      runtime.ready = true;
    }, { once: true });
    script.addEventListener('error', () => {
      runtime.loading = false;
      runtime.attempts += 1;
      if (runtime.attempts < 600) setTimeout(loadPolicy, 100);
    }, { once: true });
    document.head.appendChild(script);
  }

  globalThis.VIComponentScaleBootstrap = runtime;
  loadPolicy();
})();
