'use strict';

(() => {
  const runtime = { ready: false };

  function closeMenu(details) {
    if (details?.open) details.open = false;
  }

  function install() {
    const actions = document.querySelector('.vi-canvas-actions');
    if (runtime.ready || !actions) return false;

    runtime.ready = true;
    const labels = [...actions.children].filter((element) => (
      element.matches('label')
      && !element.closest('.vi-density-options')
    ));
    if (labels.length) {
      const details = document.createElement('details');
      details.id = 'vi-density-options';
      details.className = 'vi-density-options';
      const summary = document.createElement('summary');
      summary.className = 'secondary-action button-reset vi-density-control';
      summary.textContent = '表示';
      summary.title = 'グリッド、吸着、名称表示';
      const panel = document.createElement('div');
      panel.className = 'vi-density-options-panel';
      labels.forEach((label) => panel.append(label));
      details.append(summary, panel);

      const anchor = document.querySelector('#vi-toggle-context-pane');
      if (anchor?.parentElement === actions) anchor.after(details);
      else actions.prepend(details);

      document.addEventListener('pointerdown', (event) => {
        if (!details.contains(event.target)) closeMenu(details);
      });
      document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeMenu(details);
      });
    }

    actions.dataset.densityToolbarReady = 'true';
    globalThis.VICanvasDensityToolbar = {
      ready: true,
      runtime,
    };
    return true;
  }

  function waitForToolbar(attempt = 0) {
    if (install()) return;
    if (attempt < 320) setTimeout(() => waitForToolbar(attempt + 1), 25);
  }

  globalThis.VICanvasDensityToolbar = { ready: false, runtime };
  waitForToolbar();
})();
