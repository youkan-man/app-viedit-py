'use strict';

(() => {
  const PAGE_META = {
    model: { title: 'モデル', jobRequired: true },
    properties: { title: 'プロパティ', jobRequired: true },
    xml: { title: 'XML', jobRequired: true },
    align: { title: '座標', jobRequired: true },
    build: { title: '再構成', jobRequired: true },
  };

  const pageState = { activePage: 'model', jobId: null };

  function ensureSemanticLayoutStyles() {
    if (document.querySelector('link[data-vi-layout-overrides]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/semantic-workspace-layout.css?v=3';
    link.dataset.viLayoutOverrides = '';
    document.head.appendChild(link);
  }

  function pageFromHash() {
    const requested = window.location.hash.replace(/^#/, '').split('/')[0];
    return PAGE_META[requested] ? requested : 'model';
  }

  function updateStageMode(page) {
    const stack = $('#page-stack');
    const stage = stack?.closest('.azure-content-stage');
    const modelActive = page === 'model';
    stack?.classList.toggle('is-model-page', modelActive);
    stage?.classList.toggle('is-model-page-active', modelActive);
    document.body.dataset.activePage = page;
  }

  function updateNavigation(page) {
    $$('[data-app-page]').forEach((button) => {
      const active = button.dataset.appPage === page;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-current', active ? 'page' : 'false');
    });
    $$('[data-app-page-panel]').forEach((panel) => {
      const active = panel.dataset.appPagePanel === page;
      panel.hidden = !active;
      panel.classList.toggle('is-active', active);
    });
    updateStageMode(page);
    $('#header-page-title').textContent = PAGE_META[page]?.title || 'モデル';
    $('#model-context-section').hidden = page !== 'model' || !pageState.jobId;
  }

  function open(page, { replace = false, focus = false } = {}) {
    const target = PAGE_META[page] ? page : 'model';
    if (!pageState.jobId) {
      globalThis.viWorkbench?.openDialog();
      return false;
    }
    pageState.activePage = target;
    updateNavigation(target);
    const hash = `#${target}`;
    if (replace) window.history.replaceState(null, '', hash);
    else if (window.location.hash !== hash) window.history.pushState(null, '', hash);
    if (target === 'model') globalThis.viModelGraph?.activate();
    if (target === 'properties') {
      const selected = globalThis.viModelGraph?.selectedComponentId?.();
      if (selected) void globalThis.viComponentExplorer?.select?.(selected);
      else void globalThis.viComponentExplorer?.refresh?.();
    }
    if (focus) document.querySelector(`[data-app-page="${target}"]`)?.focus();
    return true;
  }

  function setJob(job, { openModel = false } = {}) {
    const previous = pageState.jobId;
    pageState.jobId = job?.job_id || null;
    $$('[data-job-required]').forEach((button) => { button.disabled = !pageState.jobId; });
    $('#empty-state').hidden = Boolean(pageState.jobId);
    $('#page-stack').hidden = !pageState.jobId;
    if (!pageState.jobId) return;
    const requested = pageFromHash();
    const target = openModel || previous !== pageState.jobId ? 'model' : requested;
    open(target, { replace: true });
  }

  function clearJob() {
    pageState.jobId = null;
    $$('[data-job-required]').forEach((button) => { button.disabled = true; });
    $('#empty-state').hidden = false;
    $('#page-stack').hidden = true;
    $('#model-context-section').hidden = true;
    $('#header-page-title').textContent = 'モデル';
    updateStageMode('model');
    window.history.replaceState(null, '', '#model');
  }

  function initialize() {
    ensureSemanticLayoutStyles();
    $$('[data-app-page]').forEach((button) => button.addEventListener('click', () => open(button.dataset.appPage, { focus: true })));
    $$('[data-open-page]').forEach((button) => button.addEventListener('click', () => open(button.dataset.openPage)));
    $('#model-open-properties').addEventListener('click', () => open('properties'));
    window.addEventListener('hashchange', () => {
      if (pageState.jobId) open(pageFromHash(), { replace: true });
    });
    clearJob();
  }

  globalThis.viPages = {
    open,
    setJob,
    clearJob,
    get activePage() { return pageState.activePage; },
  };

  ensureSemanticLayoutStyles();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
})();
