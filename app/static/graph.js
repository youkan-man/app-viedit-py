'use strict';

(() => {
  // Static compatibility contract retained for existing checks: payload.graph, model.position, graph.connections.
  const E = globalThis.VISemanticEditor = globalThis.VISemanticEditor || {};
  const NS = 'http://www.w3.org/2000/svg';
  const SURFACES = { 'front-panel': 'フロントパネル', 'block-diagram': 'ブロックダイアグラム' };
  const LABELS = {
    'numeric-control': '数値入力', 'numeric-indicator': '数値表示',
    'string-control': '文字列入力', 'string-indicator': '文字列表示',
    'boolean-control': 'ブール入力', 'boolean-indicator': 'ブール表示',
    'ring-control': 'リング入力', 'ring-indicator': 'リング表示',
    'path-control': 'パス入力', 'path-indicator': 'パス表示',
    control: '入力コントロール', indicator: 'インジケータ',
    add: '加算', subtract: '減算', multiply: '乗算', divide: '除算',
    equal: '等価比較', greater: '比較', less: '比較', and: '論理積', or: '論理和',
    xor: '排他的論理和', select: '選択', function: '関数', structure: '構造',
    subvi: 'SubVI', constant: '定数', node: 'ノード', terminal: '端子', wire: '配線',
  };
  const S = {
    job: null, payload: null, vi: null, objects: new Map(), wires: new Map(), local: new Map(), dirty: new Set(),
    selected: null, surface: 'front-panel', status: 'unloaded', sequence: 0, revision: '',
    box: null, fitBox: null, interaction: null, pan: null, snap: true, grid: 8,
    showTerminals: true, showLabels: true, drawer: false, saving: false, el: {},
  };
  const $ = (selector) => document.querySelector(selector);
  const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const label = (item) => LABELS[item?.kind] || item?.kind || 'オブジェクト';
  const html = (tag, className, text) => { const node = document.createElement(tag); node.className = className || ''; node.textContent = text ?? ''; return node; };
  const svg = (tag, attrs = {}) => { const node = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([key, value]) => value == null || node.setAttribute(key, String(value))); return node; };
  const boundsText = (bounds) => bounds ? `X ${Math.round(bounds.x)} · Y ${Math.round(bounds.y)} · W ${Math.round(bounds.width)} · H ${Math.round(bounds.height)}` : '位置なし';
  const snap = (value) => S.snap ? Math.round(value / S.grid) * S.grid : Math.round(value);

  function addStylesheet() {
    if ($('link[data-semantic-workspace-style]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = '/static/semantic-workspace.css'; link.dataset.semanticWorkspaceStyle = '';
    document.head.append(link);
  }

  function createMarkup() {
    const page = $('#page-model');
    if (!page) return;
    page.innerHTML = `
      <div id="vi-editor-shell" class="vi-editor-shell">
        <header class="vi-editor-header">
          <div class="vi-surface-tabs" role="tablist" aria-label="VI編集画面">
            <button class="vi-surface-tab is-active" data-vi-surface="front-panel" role="tab" aria-selected="true"><b>FP</b><span>フロントパネル<small>操作画面</small></span></button>
            <button class="vi-surface-tab" data-vi-surface="block-diagram" role="tab" aria-selected="false"><b>BD</b><span>ブロックダイアグラム<small>処理と配線</small></span></button>
          </div>
          <div class="vi-header-actions"><span id="model-graph-state" class="state-badge">未解析</span><button id="vi-object-drawer-toggle" class="secondary-action button-reset">オブジェクト</button><button id="model-graph-refresh" class="secondary-action button-reset">再解析</button></div>
        </header>
        <section class="vi-summary" aria-label="VIオブジェクト概要">
          <div><span>入力</span><strong id="vi-summary-controls">0</strong><small>controls</small></div>
          <div><span>表示</span><strong id="vi-summary-indicators">0</strong><small>indicators</small></div>
          <div><span>処理</span><strong id="vi-summary-nodes">0</strong><small>nodes</small></div>
          <div><span>配線</span><strong id="vi-summary-wires">0</strong><small id="vi-summary-wire-note">0 resolved</small></div>
        </section>
        <div id="vi-diagnostics" class="vi-diagnostics" hidden></div>
        <div class="vi-editor-layout">
          <aside class="vi-object-pane">
            <div class="vi-pane-heading"><span><strong>オブジェクト</strong><small id="vi-object-count">0</small></span><button id="vi-object-pane-close" class="icon-command" aria-label="一覧を閉じる">×</button></div>
            <label class="vi-search-field"><span class="sr-only">検索</span><input id="model-graph-query" type="search" placeholder="名前・種類で検索"></label>
            <div class="vi-filter-row"><select id="model-graph-kind"><option value="">すべての種類</option></select><label><input id="vi-show-terminals" type="checkbox" checked>端子</label></div>
            <div id="vi-object-list" class="vi-object-list" role="listbox"></div>
            <div class="vi-list-legend"><span><i class="is-control"></i>入力</span><span><i class="is-indicator"></i>表示</span><span><i class="is-node"></i>処理</span><span><i class="is-wire"></i>配線</span></div>
          </aside>
          <main class="vi-canvas-pane">
            <div class="vi-canvas-toolbar"><div><strong id="vi-surface-title">フロントパネル</strong><span id="vi-surface-subtitle">操作部品の位置とサイズ</span></div><div class="vi-canvas-actions"><label>グリッド<select id="vi-grid-size"><option>4</option><option selected>8</option><option>12</option><option>16</option></select></label><label><input id="vi-snap-grid" type="checkbox" checked>吸着</label><label><input id="vi-show-labels" type="checkbox" checked>名称</label><button id="model-graph-fit" class="secondary-action button-reset">全体表示</button><button id="model-graph-zoom-out" class="icon-command" aria-label="縮小">−</button><button id="model-graph-zoom-in" class="icon-command" aria-label="拡大">＋</button></div></div>
            <div id="model-graph-viewport" class="vi-canvas-viewport is-front-panel"><svg id="model-graph-svg" class="model-graph-svg vi-canvas-svg" role="application" tabindex="0"></svg><div id="model-graph-empty" class="vi-canvas-empty"><strong>VIオブジェクトを読み込んでいます</strong><span>解析結果から編集画面を構成します。</span></div><div class="vi-canvas-help">ドラッグで移動 · 右下ハンドルでサイズ変更 · 矢印キーで微調整</div></div>
            <footer class="vi-canvas-statusbar"><span id="vi-selection-status">選択なし</span><span id="vi-coordinate-status">—</span><div><button id="vi-revert-layout" class="secondary-action button-reset" disabled>変更を戻す</button><button id="vi-save-layout" class="primary-small button-reset" disabled>位置を保存</button></div></footer>
          </main>
        </div>
        <details id="vi-source-debug" class="vi-source-debug"><summary><span>解析元（デバッグ）</span><small>XMLは解析元としてのみ保持します</small></summary><div class="vi-source-debug-grid"><section><div class="pane-heading"><strong>解析ファイル</strong><span id="model-document-count">0</span></div><div id="model-document-list"></div></section><section><div class="pane-heading"><strong>未解決参照</strong><span id="model-unresolved-count">0</span></div><div id="model-unresolved-list"></div></section></div></details>
        <div class="vi-compatibility-fields" aria-hidden="true"><select id="model-graph-layer"><option value="front-panel">front-panel</option><option value="block-diagram">block-diagram</option></select><span id="model-graph-model-count"></span><span id="model-graph-positioned-note"></span><span id="model-graph-edge-count"></span><span id="model-graph-net-count"></span><span id="model-graph-document-count"></span><span id="model-graph-unresolved-note"></span></div>
      </div>`;
  }

  function enhanceInspector() {
    const inspector = $('#model-inspector');
    if (!inspector || $('#vi-geometry-editor')) return;
    $('#model-context-section .context-heading span')?.replaceChildren(document.createTextNode('選択オブジェクト'));
    const section = document.createElement('section');
    section.id = 'vi-geometry-editor'; section.className = 'vi-geometry-editor';
    section.innerHTML = `<div class="context-heading"><span>位置とサイズ</span><span id="vi-editability">—</span></div><div class="vi-geometry-grid"><label>X<input id="vi-geometry-x" type="number"></label><label>Y<input id="vi-geometry-y" type="number"></label><label>幅<input id="vi-geometry-width" type="number" min="1"></label><label>高さ<input id="vi-geometry-height" type="number" min="1"></label></div><small id="vi-geometry-hint">キャンバス上でも編集できます。</small>`;
    inspector.insertBefore(section, inspector.querySelector('.connection-heading'));
  }

  function cacheElements() {
    const ids = ['vi-editor-shell','model-graph-state','model-graph-refresh','vi-object-drawer-toggle','vi-object-pane-close','vi-summary-controls','vi-summary-indicators','vi-summary-nodes','vi-summary-wires','vi-summary-wire-note','vi-diagnostics','vi-object-count','model-graph-query','model-graph-kind','vi-show-terminals','vi-object-list','vi-surface-title','vi-surface-subtitle','vi-grid-size','vi-snap-grid','vi-show-labels','model-graph-fit','model-graph-zoom-out','model-graph-zoom-in','model-graph-viewport','model-graph-svg','model-graph-empty','vi-selection-status','vi-coordinate-status','vi-revert-layout','vi-save-layout','model-graph-layer','model-document-count','model-document-list','model-unresolved-count','model-unresolved-list','model-inspector-empty','model-inspector','model-selection-kind','model-inspector-name','model-inspector-class','model-inspector-uid','model-inspector-file','model-inspector-path','model-inspector-position','model-inspector-connection-count','model-inspector-connections','vi-editability','vi-geometry-x','vi-geometry-y','vi-geometry-width','vi-geometry-height','vi-geometry-hint'];
    ids.forEach((id) => { S.el[id.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = document.getElementById(id); });
  }

  function revisionFor(job) {
    return [job?.job_id, job?.component_modified_at, job?.xml_modified_at, job?.quantized_at, job?.status, ...(job?.files || []).map((file) => `${file.path}:${file.size}`)].join('|');
  }

  function setStatus(text, className = '') {
    if (!S.el.modelGraphState) return;
    S.el.modelGraphState.textContent = text;
    S.el.modelGraphState.className = `state-badge${className ? ` ${className}` : ''}`;
  }

  async function load(force = false) {
    if (!S.job?.job_id) return;
    const sequence = ++S.sequence;
    S.el.modelGraphRefresh.disabled = true; S.status = 'loading'; setStatus('解析中');
    try {
      const suffix = force ? `?refresh=${Date.now()}` : '';
      const payload = await apiRequest(`/api/jobs/${encodeURIComponent(S.job.job_id)}/model${suffix}`);
      if (sequence !== S.sequence) return;
      S.payload = payload; E.install(payload.vi || E.fallbackSemantic(payload.graph || {}));
      const failed = number(payload.summary?.failed_files);
      S.status = failed ? 'partial' : 'ready'; setStatus(failed ? '一部解析失敗' : '編集可能', failed ? 'is-dirty' : 'is-ready');
      E.renderAll(true);
      const first = (S.vi.objects || []).find((item) => item.surface === S.surface && item.category !== 'terminal');
      if (first) E.select(first.id);
    } catch (error) {
      if (sequence !== S.sequence) return;
      S.status = 'error'; S.vi = null; setStatus('解析失敗', 'is-dirty');
      S.el.modelGraphSvg.replaceChildren(); S.el.modelGraphEmpty.hidden = false;
      S.el.modelGraphEmpty.querySelector('strong').textContent = 'VIオブジェクト解析に失敗しました';
      S.el.modelGraphEmpty.querySelector('span').textContent = describeError(error);
      showToast(`VI編集モデル: ${describeError(error)}`, 'error', 10000);
    } finally { S.el.modelGraphRefresh.disabled = false; }
  }

  async function setJob(job) {
    const nextRevision = revisionFor(job), changed = nextRevision !== S.revision, same = S.job?.job_id === job?.job_id;
    S.job = job || null; S.revision = nextRevision;
    if (!job) { clearJob(); return; }
    if (!same || changed || !S.vi) await load(changed); else E.renderAll(false);
  }

  async function onDatasetChanged(job) {
    S.job = job || S.job; S.revision = revisionFor(S.job); S.vi = null; await load(true);
  }

  function clearJob() {
    S.sequence += 1; S.job = null; S.payload = null; S.vi = null; S.selected = null; S.status = 'unloaded';
    S.objects.clear(); S.wires.clear(); S.local.clear(); S.dirty.clear(); S.box = null; S.fitBox = null;
    S.el.modelGraphSvg?.replaceChildren(); S.el.viObjectList?.replaceChildren();
    if (S.el.modelGraphEmpty) S.el.modelGraphEmpty.hidden = false;
    setStatus('未解析'); E.saveState?.();
  }

  function toggleDrawer(open = !S.drawer) {
    S.drawer = Boolean(open); S.el.viEditorShell.classList.toggle('is-list-open', S.drawer);
    S.el.viObjectDrawerToggle.setAttribute('aria-expanded', String(S.drawer));
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script'); script.src = src; script.async = false;
      script.addEventListener('load', resolve, { once: true }); script.addEventListener('error', () => reject(new Error(`${src} を読み込めません。`)), { once: true });
      document.head.append(script);
    });
  }

  let readyResolve, readyReject;
  const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject; });

  async function initialize() {
    try {
      addStylesheet(); createMarkup(); enhanceInspector(); cacheElements();
      await loadScript('/static/vi-editor-list.js');
      await loadScript('/static/vi-editor-canvas.js');
      E.bindInteractions(); readyResolve();
    } catch (error) {
      S.status = 'error'; setStatus('UI初期化失敗', 'is-dirty'); readyReject(error); console.error(error);
    }
  }

  Object.assign(E, { NS, SURFACES, LABELS, S, $, number, label, html, svg, boundsText, snap, revisionFor, setStatus, load, setJob, onDatasetChanged, clearJob, toggleDrawer });
  globalThis.viModelGraph = {
    setJob: async (job) => { await ready; return setJob(job); },
    onDatasetChanged: async (job) => { await ready; return onDatasetChanged(job); },
    clearJob: () => { void ready.then(clearJob); },
    activate: () => { void ready.then(() => S.job && !S.vi ? load() : S.vi && E.renderAll(false)); },
    refresh: () => ready.then(() => load(true)), status: () => S.status,
    selectedComponentId: () => S.objects.get(S.selected)?.component_id || S.selected,
    select: (id) => { void ready.then(() => E.select(id, true)); }, surface: () => S.surface,
  };
  document.addEventListener('DOMContentLoaded', initialize);
})();
