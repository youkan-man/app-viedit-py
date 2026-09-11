'use strict';

(() => {
  const PAGE_META = {
    model: { title: 'VI編集', jobRequired: true },
    properties: { title: 'プロパティ一覧', jobRequired: true },
    xml: { title: 'RAWデータ', jobRequired: true },
    align: { title: '整列ツール', jobRequired: true },
    build: { title: '成果物', jobRequired: true },
  };

  const pageState = { activePage: 'model', jobId: null };

  function stabilizeSemanticWorkspace() {
    const shell = document.querySelector('#vi-editor-shell');
    if (!shell) return false;
    shell.classList.add('is-layout-ready');
    shell.dataset.layoutReady = 'true';
    return true;
  }

  function ensureStylesheet(selector, href, datasetKey) {
    if (document.querySelector(selector)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset[datasetKey] = '';
    document.head.appendChild(link);
  }

  function ensureScript(selector, src, datasetKey) {
    if (document.querySelector(selector)) return;
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.dataset[datasetKey] = '';
    document.head.appendChild(script);
  }

  function ensureSemanticLayoutStyles() {
    ensureStylesheet(
      'link[data-vi-layout-overrides]',
      '/static/semantic-workspace-layout.css?v=3',
      'viLayoutOverrides',
    );
    ensureStylesheet(
      'link[data-vi-runtime-overrides]',
      '/static/semantic-workspace-runtime.css?v=2',
      'viRuntimeOverrides',
    );
    ensureStylesheet(
      'link[data-vi-semantic-enhancements]',
      '/static/semantic-workspace-enhancements.css?v=1',
      'viSemanticEnhancements',
    );
    ensureStylesheet(
      'link[data-vi-realism]',
      '/static/semantic-workspace-realism.css?v=1',
      'viRealism',
    );
    ensureStylesheet(
      'link[data-component-property-semantics]',
      '/static/component-properties-semantic.css?v=1',
      'componentPropertySemantics',
    );
    ensureStylesheet(
      'link[data-vi-type-definitions]',
      '/static/semantic-type-definitions.css?v=1',
      'viTypeDefinitions',
    );
    ensureStylesheet(
      'link[data-vi-semantic-integrity]',
      '/static/semantic-integrity.css?v=1',
      'viSemanticIntegrity',
    );
    ensureStylesheet(
      'link[data-vi-canvas-density]',
      '/static/semantic-density.css?v=2',
      'viCanvasDensity',
    );
    ensureStylesheet(
      'link[data-vi-canvas-density-runtime]',
      '/static/semantic-density-runtime.css?v=2',
      'viCanvasDensityRuntime',
    );
    ensureStylesheet(
      'link[data-vi-readability]',
      '/static/semantic-readability.css?v=1',
      'viReadability',
    );
  }

  function ensureSemanticEditorScripts() {
    ensureScript(
      'script[data-vi-editor-navigation]',
      '/static/vi-editor-navigation.js?v=3',
      'viEditorNavigation',
    );
    ensureScript(
      'script[data-vi-editor-enhancements]',
      '/static/vi-editor-enhancements.js?v=1',
      'viEditorEnhancements',
    );
    ensureScript(
      'script[data-vi-runtime-fixes]',
      '/static/vi-editor-runtime-fixes.js?v=7',
      'viRuntimeFixes',
    );
  }

  function bindSemanticEditorInteractions() {
    const editor = globalThis.VISemanticEditor;
    const shell = document.querySelector('#vi-editor-shell');
    if (
      !shell
      || shell.dataset.interactionsBound === 'true'
      || typeof editor?.bindInteractions !== 'function'
    ) {
      return;
    }
    shell.dataset.interactionsBound = 'true';
    editor.bindInteractions();
  }

  function finalizeSemanticEditor() {
    stabilizeSemanticWorkspace();
    bindSemanticEditorInteractions();
    ensureSemanticEditorScripts();
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
    $('#header-page-title').textContent = PAGE_META[page]?.title || 'VI編集';
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
    requestAnimationFrame(stabilizeSemanticWorkspace);
  }

  function clearJob() {
    pageState.jobId = null;
    $$('[data-job-required]').forEach((button) => { button.disabled = true; });
    $('#empty-state').hidden = false;
    $('#page-stack').hidden = true;
    $('#model-context-section').hidden = true;
    $('#header-page-title').textContent = 'VI編集';
    updateStageMode('model');
    window.history.replaceState(null, '', '#model');
  }

  function initialize() {
    ensureSemanticLayoutStyles();
    ensureSemanticEditorScripts();
    $$('[data-app-page]').forEach((button) => {
      button.addEventListener('click', () => open(button.dataset.appPage, { focus: true }));
    });
    $$('[data-open-page]').forEach((button) => {
      button.addEventListener('click', () => open(button.dataset.openPage));
    });
    window.addEventListener('hashchange', () => {
      if (pageState.jobId) open(pageFromHash(), { replace: true });
    });
    clearJob();
  }

  globalThis.viPages = {
    open,
    setJob,
    clearJob,
    stabilizeSemanticWorkspace,
    get activePage() { return pageState.activePage; },
  };

  ensureSemanticLayoutStyles();
  ensureSemanticEditorScripts();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
  if (document.readyState === 'complete') {
    finalizeSemanticEditor();
  } else {
    window.addEventListener('load', finalizeSemanticEditor, { once: true });
  }
})();
