'use strict';

(() => {
  // Static compatibility contract retained for existing checks:
  // payload.graph, graph.models, graph.connections, model.position,
  // edge.source, edge.target, id="vi-geometry-editor".
  const SURFACES = {
    'front-panel': 'フロントパネル',
    'block-diagram': 'ブロックダイアグラム',
  };
  const KIND_LABELS = {
    'numeric-control': '数値入力',
    'numeric-indicator': '数値表示',
    'string-control': '文字列入力',
    'string-indicator': '文字列表示',
    'boolean-control': 'ブール入力',
    'boolean-indicator': 'ブール表示',
    control: '入力コントロール',
    indicator: 'インジケータ',
    add: '加算',
    subtract: '減算',
    multiply: '乗算',
    divide: '除算',
    equal: '等価比較',
    greater: '比較',
    less: '比較',
    and: '論理積',
    or: '論理和',
    xor: '排他的論理和',
    select: '選択',
    function: '関数',
    structure: '構造',
    subvi: 'SubVI',
    constant: '定数',
    node: 'ノード',
    terminal: '端子',
  };
  const S = {
    job: null,
    payload: null,
    vi: null,
    objects: new Map(),
    wires: new Map(),
    local: new Map(),
    fallback: new Map(),
    dirty: new Set(),
    selected: null,
    surface: 'front-panel',
    sequence: 0,
    revision: '',
    state: 'unloaded',
    box: null,
    fitBox: null,
    interaction: null,
    pan: null,
    snap: true,
    grid: 8,
    showTerminals: true,
    showLabels: true,
    drawerOpen: false,
    saving: false,
    el: {},
  };
  let initialized = false;

  function html(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }

  function svg(tag, attrs = {}) {
    const item = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value !== null && value !== undefined) item.setAttribute(key, String(value));
    });
    return item;
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function label(item) {
    return KIND_LABELS[item?.kind] || item?.kind || 'オブジェクト';
  }

  function revisionFor(job) {
    return [
      job?.job_id,
      job?.xml_sha256,
      job?.xml_modified_at,
      job?.component_modified_at,
      job?.dataset_xml_modified_at,
      job?.last_quantization?.applied_at,
      job?.files?.map((file) => `${file.path}:${file.size}`).join('|'),
    ].filter(Boolean).join('::');
  }

  function boundsText(bounds) {
    return bounds
      ? `X ${Math.round(bounds.x)} · Y ${Math.round(bounds.y)} · W ${Math.round(bounds.width)} · H ${Math.round(bounds.height)}`
      : '位置情報なし';
  }

  function typeClass(item) {
    if (item?.category === 'control') return 'is-control';
    if (item?.category === 'indicator') return 'is-indicator';
    if (item?.category === 'terminal') {
      return `is-terminal is-${item.direction || 'unknown'}`;
    }
    return `is-node is-${item?.kind || 'object'}`;
  }

  function wireName(wire) {
    const source = S.objects.get(wire?.source_object_id);
    const targets = (wire?.target_object_ids || [])
      .map((id) => S.objects.get(id))
      .filter(Boolean);
    return source && targets.length
      ? `${source.name} → ${targets.map((item) => item.name).join(', ')}`
      : wire?.name || '配線';
  }

  function getBounds(item, index = 0) {
    if (!item) return null;
    let bounds = S.local.get(item.id) || item.bounds;
    if (!bounds) {
      if (!S.fallback.has(item.id)) {
        S.fallback.set(item.id, {
          x: 40 + (index % 4) * 160,
          y: 45 + Math.floor(index / 4) * 86,
          width: 124,
          height: 44,
          generated: true,
        });
      }
      bounds = S.fallback.get(item.id);
    }
    bounds = { ...bounds };
    const ownerId = item.bounds?.relative_to_object_id;
    if (ownerId) {
      const owner = S.objects.get(ownerId);
      const original = owner?.bounds;
      const current = S.local.get(ownerId) || original;
      if (original && current) {
        bounds.x += current.x - original.x;
        bounds.y += current.y - original.y;
        if (item.direction === 'source') {
          bounds.x += current.width - original.width;
        }
      }
    }
    return bounds;
  }

  function snap(value) {
    return S.snap ? Math.round(value / S.grid) * S.grid : value;
  }

  function visible(item) {
    if (
      item.surface !== S.surface
      || (!S.showTerminals && item.category === 'terminal')
    ) {
      return false;
    }
    const query = S.el.modelGraphQuery?.value.trim().toLowerCase() || '';
    const kind = S.el.modelGraphKind?.value || '';
    if (kind && item.kind !== kind) return false;
    return !query || [item.name, label(item), item.class_name, item.widget, item.uid]
      .join(' ')
      .toLowerCase()
      .includes(query);
  }

  function surfaceObjects(allTerminals = false) {
    return [...S.objects.values()].filter((item) => (
      item.surface === S.surface
      && (allTerminals || S.showTerminals || item.category !== 'terminal')
    ));
  }

  function createMarkup() {
    const page = document.querySelector('#page-model');
    if (!page) return;
    page.innerHTML = `
      <div id="vi-editor-shell" class="vi-editor-shell">
        <header class="vi-editor-header">
          <div class="vi-surface-tabs" role="tablist" aria-label="VI編集画面">
            <button type="button" class="vi-surface-tab is-active" data-vi-surface="front-panel" aria-selected="true"><b>FP</b><span><strong>フロントパネル</strong><small>操作画面</small></span></button>
            <button type="button" class="vi-surface-tab" data-vi-surface="block-diagram" aria-selected="false"><b>BD</b><span><strong>ブロックダイアグラム</strong><small>処理と配線</small></span></button>
          </div>
          <div class="vi-header-actions"><span id="model-graph-state" class="state-badge" aria-live="polite">未解析</span><button id="vi-object-drawer-toggle" class="secondary-action button-reset" type="button">オブジェクト</button><button id="model-graph-refresh" class="secondary-action button-reset" type="button">再解析</button></div>
        </header>
        <section class="vi-summary" aria-label="VI概要">
          <div><span>入力</span><strong id="vi-summary-controls">0</strong><small>controls</small></div>
          <div><span>表示</span><strong id="vi-summary-indicators">0</strong><small>indicators</small></div>
          <div><span>処理</span><strong id="vi-summary-nodes">0</strong><small>nodes</small></div>
          <div><span>配線</span><strong id="vi-summary-wires">0</strong><small id="vi-summary-wire-note">0 resolved</small></div>
        </section>
        <div id="vi-diagnostics" class="vi-diagnostics" hidden></div>
        <div class="vi-editor-layout">
          <aside class="vi-object-pane">
            <div class="vi-pane-heading"><span><strong>オブジェクト</strong><small id="vi-object-count">0</small></span><button id="vi-object-pane-close" type="button" aria-label="オブジェクト一覧を閉じる">×</button></div>
            <input id="model-graph-query" class="vi-object-search" type="search" placeholder="名前・種類で検索">
            <div class="vi-filter-row"><select id="model-graph-kind"><option value="">すべての種類</option></select><label><input id="vi-show-terminals" type="checkbox" checked> 端子</label></div>
            <div id="vi-object-list" class="vi-object-list" role="listbox"></div>
          </aside>
          <main class="vi-canvas-pane">
            <div class="vi-canvas-toolbar">
              <div><strong id="vi-surface-title">フロントパネル</strong><small id="vi-surface-subtitle">操作部品の位置とサイズ</small></div>
              <div class="vi-canvas-actions"><label>グリッド <select id="vi-grid-size"><option>4</option><option selected>8</option><option>12</option><option>16</option></select></label><label><input id="vi-snap-grid" type="checkbox" checked> 吸着</label><label><input id="vi-show-labels" type="checkbox" checked> 名称</label><button id="model-graph-fit" type="button">全体</button><button id="model-graph-zoom-out" type="button" aria-label="縮小">−</button><button id="model-graph-zoom-in" type="button" aria-label="拡大">＋</button></div>
            </div>
            <div id="model-graph-viewport" class="vi-canvas-viewport is-front-panel"><svg id="model-graph-svg" class="model-graph-svg" tabindex="0"></svg><div id="model-graph-empty" class="model-graph-empty"><strong>VIオブジェクトを読み込んでいます</strong><span>意味モデルを構築しています。</span></div><div class="vi-canvas-help">ドラッグで移動 · 右下ハンドルでサイズ変更 · ダブルクリックで対応部品へ移動</div></div>
            <footer class="vi-canvas-statusbar"><span id="vi-selection-status" aria-live="polite">選択なし</span><span id="vi-coordinate-status">—</span><span class="vi-save-actions"><button id="vi-revert-layout" type="button" disabled>変更を戻す</button><button id="vi-save-layout" type="button" disabled>位置を保存</button></span></footer>
          </main>
        </div>
        <details id="vi-source-debug" class="vi-source-debug"><summary><span>解析元（デバッグ）</span><small>XMLは解析元としてのみ保持します</small></summary><div class="vi-source-debug-grid"><section><strong>解析ファイル <span id="model-document-count">0</span></strong><div id="model-document-list"></div></section><section><strong>未解決参照 <span id="model-unresolved-count">0</span></strong><div id="model-unresolved-list"></div></section></div></details>
        <div class="vi-compatibility-fields"><select id="model-graph-layer"><option value="front-panel">front-panel</option><option value="block-diagram">block-diagram</option></select><input id="model-graph-show-hierarchy" type="checkbox"><input id="model-graph-show-unpositioned" type="checkbox"><span id="model-graph-model-count">0</span><span id="model-graph-positioned-note"></span><span id="model-graph-edge-count">0</span><span id="model-graph-net-count">0</span><span id="model-graph-document-count">0</span><span id="model-graph-unresolved-note"></span></div>
      </div>`;
  }

  function enhanceInspector() {
    const section = document.querySelector('#model-context-section');
    const inspector = document.querySelector('#model-inspector');
    if (!section || !inspector) return;
    section.classList.add('vi-selection-context');
    const heading = section.querySelector('.context-heading span:first-child');
    if (heading) heading.textContent = '選択オブジェクト';
    const empty = document.querySelector('#model-inspector-empty');
    if (empty) empty.textContent = 'キャンバスまたは一覧から選択してください。';
    if (!document.querySelector('#vi-geometry-editor')) {
      const geometry = html('section', 'vi-geometry-editor');
      geometry.id = 'vi-geometry-editor';
      geometry.innerHTML = `<div class="vi-geometry-heading"><strong>配置</strong><span id="vi-editability">未選択</span></div><div class="vi-geometry-grid"><label>X<input id="vi-geometry-x" type="number"></label><label>Y<input id="vi-geometry-y" type="number"></label><label>幅<input id="vi-geometry-width" type="number"></label><label>高さ<input id="vi-geometry-height" type="number"></label></div><small id="vi-geometry-hint">キャンバスからも操作できます。</small>`;
      inspector.insertBefore(geometry, inspector.querySelector('.connection-heading'));
    }
    const detailButton = document.querySelector('#model-open-properties');
    if (detailButton) detailButton.textContent = '詳細プロパティを開く';
  }

  function cache() {
    const ids = [
      'model-graph-state', 'model-graph-refresh', 'model-graph-query',
      'model-graph-kind', 'model-graph-layer', 'model-graph-fit',
      'model-graph-zoom-in', 'model-graph-zoom-out', 'model-graph-svg',
      'model-graph-empty', 'model-graph-viewport', 'vi-editor-shell',
      'vi-diagnostics', 'vi-object-list', 'vi-object-count',
      'vi-show-terminals', 'vi-show-labels', 'vi-snap-grid', 'vi-grid-size',
      'vi-save-layout', 'vi-revert-layout', 'vi-selection-status',
      'vi-coordinate-status', 'vi-surface-title', 'vi-surface-subtitle',
      'vi-summary-controls', 'vi-summary-indicators', 'vi-summary-nodes',
      'vi-summary-wires', 'vi-summary-wire-note', 'model-document-list',
      'model-document-count', 'model-unresolved-list', 'model-unresolved-count',
      'vi-object-drawer-toggle', 'vi-object-pane-close',
      'model-inspector-empty', 'model-inspector', 'model-selection-kind',
      'model-inspector-name', 'model-inspector-class', 'model-inspector-uid',
      'model-inspector-file', 'model-inspector-path', 'model-inspector-position',
      'model-inspector-connection-count', 'model-inspector-connections',
      'vi-editability', 'vi-geometry-x', 'vi-geometry-y', 'vi-geometry-width',
      'vi-geometry-height', 'vi-geometry-hint',
    ];
    ids.forEach((id) => {
      const key = id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
      S.el[key] = document.querySelector(`#${id}`);
    });
  }

  function captureView() {
    if (!S.vi) return null;
    return {
      selected: S.selected,
      surface: S.surface,
      box: S.box ? { ...S.box } : null,
      drawerOpen: S.drawerOpen,
    };
  }

  function install(vi, restore = null) {
    S.vi = vi;
    S.objects = new Map((vi.objects || []).map((item) => [item.id, item]));
    S.wires = new Map((vi.wires || []).map((item) => [item.id, item]));
    S.local.clear();
    S.fallback.clear();
    S.dirty.clear();
    S.interaction = null;
    S.pan = null;
    S.fitBox = null;

    const hasFrontPanel = Boolean(vi.surfaces?.['front-panel']?.length);
    const hasBlockDiagram = Boolean(vi.surfaces?.['block-diagram']?.length);
    const defaultSurface = hasFrontPanel || !hasBlockDiagram
      ? 'front-panel'
      : 'block-diagram';
    S.surface = restore && SURFACES[restore.surface]
      ? restore.surface
      : defaultSurface;
    S.selected = restore?.selected
      && (S.objects.has(restore.selected) || S.wires.has(restore.selected))
      ? restore.selected
      : null;
    const selectedObject = S.objects.get(S.selected);
    if (selectedObject) S.surface = selectedObject.surface;
    if (S.wires.has(S.selected)) S.surface = 'block-diagram';
    S.box = restore?.box ? { ...restore.box } : null;
    S.drawerOpen = Boolean(restore?.drawerOpen);
    S.el.viEditorShell.classList.toggle('is-list-open', S.drawerOpen);
    S.el.modelGraphLayer.value = S.surface;
    if (S.box) {
      S.el.modelGraphSvg.setAttribute(
        'viewBox',
        `${S.box.x} ${S.box.y} ${S.box.width} ${S.box.height}`,
      );
    }
  }

  function setState(text, stateClass = '') {
    S.el.modelGraphState.className = `state-badge ${stateClass}`;
    S.el.modelGraphState.textContent = text;
  }

  function setSurface(surface, fit = true) {
    if (!SURFACES[surface]) return;
    S.surface = surface;
    S.el.modelGraphLayer.value = surface;
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      const active = button.dataset.viSurface === surface;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    });
    S.el.modelGraphViewport.className = `vi-canvas-viewport is-${surface}`;
    S.el.viSurfaceTitle.textContent = SURFACES[surface];
    S.el.viSurfaceSubtitle.textContent = surface === 'front-panel'
      ? '操作部品の位置とサイズ'
      : '演算ノード・端子・配線の接続';
    const selectedObject = S.objects.get(S.selected);
    if (
      selectedObject?.surface !== surface
      || (S.wires.has(S.selected) && surface !== 'block-diagram')
    ) {
      S.selected = null;
    }
    globalThis.VISemanticEditor.renderAll?.(fit);
  }

  function select(id, reveal = false) {
    const item = S.objects.get(id);
    const wire = S.wires.get(id);
    if (!item && !wire) return;
    if (item && item.surface !== S.surface) setSurface(item.surface, false);
    if (wire && S.surface !== 'block-diagram') setSurface('block-diagram', false);
    S.selected = id;
    globalThis.VISemanticEditor.renderAll?.(false);
    if (reveal) {
      document.querySelector(
        `[data-object-id="${CSS.escape(id)}"],[data-wire-id="${CSS.escape(id)}"]`,
      )?.focus?.();
    }
    if (S.drawerOpen && innerWidth <= 1220) toggleDrawer(false);
  }

  function toggleDrawer(open = !S.drawerOpen) {
    S.drawerOpen = Boolean(open);
    S.el.viEditorShell.classList.toggle('is-list-open', S.drawerOpen);
  }

  async function load(force = false, { preserveView = true } = {}) {
    if (!S.job?.job_id) return;
    const sequence = ++S.sequence;
    const restore = preserveView ? captureView() : null;
    setState('解析中');
    S.el.modelGraphRefresh.disabled = true;
    try {
      const suffix = force ? `?refresh=${Date.now()}` : '';
      const payload = await apiRequest(
        `/api/jobs/${encodeURIComponent(S.job.job_id)}/model${suffix}`,
      );
      if (sequence !== S.sequence) return;
      S.payload = payload;
      const vi = payload.vi
        || globalThis.VISemanticEditor.fallbackSemantic(payload.graph || {});
      install(vi, restore);
      const partial = Boolean(payload.summary?.failed_files);
      setState(partial ? '一部解析失敗' : '編集可能', partial ? 'is-dirty' : 'is-ready');
      S.state = partial ? 'partial' : 'ready';
      setSurface(S.surface, !restore?.box);
      if (!S.selected) {
        const preferred = [...S.objects.values()].find((item) => (
          item.surface === S.surface && item.category !== 'terminal'
        ));
        if (preferred) select(preferred.id);
      }
    } catch (error) {
      if (sequence !== S.sequence) return;
      S.state = 'error';
      setState('解析失敗', 'is-dirty');
      S.vi = null;
      S.el.modelGraphEmpty.hidden = false;
      S.el.modelGraphEmpty.querySelector('strong').textContent = 'VIオブジェクト解析に失敗しました';
      S.el.modelGraphEmpty.querySelector('span').textContent = describeError(error);
    } finally {
      S.el.modelGraphRefresh.disabled = false;
    }
  }

  async function setJob(job) {
    const previousJobId = S.job?.job_id || null;
    const sameJob = Boolean(job?.job_id && previousJobId === job.job_id);
    const changed = revisionFor(job) !== S.revision;
    S.job = job;
    S.revision = revisionFor(job);
    if (!job) {
      clearJob();
      return;
    }
    if (!sameJob || changed || !S.vi) {
      await load(changed, { preserveView: sameJob });
    } else {
      globalThis.VISemanticEditor.renderAll?.(false);
    }
  }

  async function onDatasetChanged(job) {
    const sameJob = Boolean(job?.job_id && S.job?.job_id === job.job_id);
    S.job = job || S.job;
    S.revision = revisionFor(S.job);
    S.vi = null;
    await load(true, { preserveView: sameJob });
  }

  function clearJob() {
    S.sequence += 1;
    S.job = null;
    S.payload = null;
    S.vi = null;
    S.objects.clear();
    S.wires.clear();
    S.local.clear();
    S.fallback.clear();
    S.dirty.clear();
    S.selected = null;
    S.box = null;
    S.fitBox = null;
    S.state = 'unloaded';
    S.el.modelGraphSvg.replaceChildren();
    S.el.modelGraphEmpty.hidden = false;
    setState('未解析');
  }

  function initialize() {
    if (initialized) return;
    initialized = true;
    createMarkup();
    enhanceInspector();
    cache();
    Object.assign(globalThis.VISemanticEditor, {
      S,
      SURFACES,
      KIND_LABELS,
      html,
      svg,
      number,
      label,
      typeClass,
      wireName,
      revisionFor,
      boundsText,
      getBounds,
      snap,
      visible,
      surfaceObjects,
      setSurface,
      select,
      toggleDrawer,
      load,
      captureView,
    });
    globalThis.VISemanticEditor.bindInteractions?.();
  }

  globalThis.VISemanticEditor = {
    S,
    SURFACES,
    KIND_LABELS,
    html,
    svg,
    number,
    label,
    typeClass,
    wireName,
    revisionFor,
    boundsText,
    getBounds,
    snap,
    visible,
    surfaceObjects,
  };
  globalThis.viModelGraph = {
    setJob,
    onDatasetChanged,
    clearJob,
    activate: () => S.vi && globalThis.VISemanticEditor.renderAll?.(false),
    refresh: () => load(true, { preserveView: true }),
    status: () => S.state,
    selectedComponentId: () => S.objects.get(S.selected)?.component_id || S.selected,
    select: (id) => select(id, true),
    surface: () => S.surface,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
})();
