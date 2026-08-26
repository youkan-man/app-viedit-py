'use strict';

(() => {
  const PAGE_META = {
    import: { title: '取込', jobRequired: false },
    model: { title: 'モデル', jobRequired: true },
    xml: { title: 'XML', jobRequired: true },
    align: { title: '座標', jobRequired: true },
    build: { title: '再構成', jobRequired: true },
  };

  const pageState = {
    activePage: 'import',
    modelView: 'graph',
    jobId: null,
  };

  function pageFromHash() {
    const requested = window.location.hash.replace(/^#/, '').split('/')[0];
    return PAGE_META[requested] ? requested : 'import';
  }

  function canOpen(page) {
    return !PAGE_META[page].jobRequired || Boolean(state.currentJob?.job_id);
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
    $('#page-context-title').textContent = PAGE_META[page].title;
  }

  function open(page, { replace = false, focus = true } = {}) {
    const target = PAGE_META[page] ? page : 'import';
    if (!canOpen(target)) {
      showToast('先にVIまたはXMLデータセットを取込んでください。', 'error');
      return false;
    }
    pageState.activePage = target;
    updateNavigation(target);
    const hash = `#${target}`;
    if (replace) window.history.replaceState(null, '', hash);
    else if (window.location.hash !== hash) window.history.pushState(null, '', hash);

    if (target === 'model') {
      globalThis.viModelGraph?.activate();
    }
    if (focus) {
      const heading = $(`[data-app-page-panel="${target}"] h1`);
      heading?.focus?.({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    return true;
  }

  function setModelView(view) {
    const target = view === 'properties' ? 'properties' : 'graph';
    pageState.modelView = target;
    $$('[data-model-view]').forEach((button) => {
      const active = button.dataset.modelView === target;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    });
    $$('[data-model-view-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.modelViewPanel !== target;
    });
    if (target === 'graph') globalThis.viModelGraph?.activate();
    else globalThis.viComponentExplorer?.refresh?.();
  }

  function setJob(job, { openModel = false } = {}) {
    const previousJob = pageState.jobId;
    pageState.jobId = job?.job_id || null;
    $$('[data-job-required]').forEach((button) => {
      button.disabled = !pageState.jobId;
    });
    if (!pageState.jobId && PAGE_META[pageState.activePage].jobRequired) {
      open('import', { replace: true });
      return;
    }
    if (openModel || (pageState.jobId && pageState.jobId !== previousJob)) {
      open('model');
    }
  }

  function clearJob() {
    pageState.jobId = null;
    $$('[data-job-required]').forEach((button) => {
      button.disabled = true;
    });
    open('import', { replace: true });
  }

  function initialize() {
    $$('[data-app-page]').forEach((button) => {
      button.addEventListener('click', () => open(button.dataset.appPage));
    });
    $$('[data-open-page]').forEach((button) => {
      button.addEventListener('click', () => open(button.dataset.openPage));
    });
    $$('[data-model-view]').forEach((button) => {
      button.addEventListener('click', () => setModelView(button.dataset.modelView));
    });
    $$('[data-open-model-properties]').forEach((button) => {
      button.addEventListener('click', () => {
        open('model', { focus: false });
        setModelView('properties');
      });
    });
    window.addEventListener('hashchange', () => open(pageFromHash(), { replace: true, focus: false }));
    setModelView('graph');
    open(pageFromHash(), { replace: true, focus: false });
  }

  globalThis.viPages = {
    open,
    setJob,
    clearJob,
    setModelView,
    get activePage() {
      return pageState.activePage;
    },
  };

  document.addEventListener('DOMContentLoaded', initialize);
})();
