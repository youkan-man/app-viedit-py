'use strict';

(() => {
  const MAX_HISTORY = 50;
  const MAX_RECENT = 16;
  const MAX_RESULTS = 60;
  const SURFACE_LABELS = {
    'front-panel': 'フロントパネル',
    'block-diagram': 'ブロックダイアグラム',
  };
  const SURFACE_BADGES = {
    'front-panel': 'FP',
    'block-diagram': 'BD',
  };
  const CATEGORY_LABELS = {
    control: '入力',
    indicator: '表示',
    node: '処理',
    terminal: '端子',
    wire: '配線',
  };
  const runtime = {
    ready: false,
    open: false,
    replaying: false,
    installed: false,
    history: [],
    cursor: -1,
    recent: [],
    results: [],
    activeIndex: 0,
    jobKey: '',
    restoreFocus: null,
    inertStates: [],
    originalSelect: null,
    originalInstall: null,
    originalRenderAll: null,
    elements: {},
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function density() {
    return globalThis.VICanvasDensity;
  }

  function enhancements() {
    return globalThis.VISemanticEnhancements;
  }

  function cloneBox(box) {
    if (!box) return null;
    const values = ['x', 'y', 'width', 'height'].map((key) => Number(box[key]));
    if (!values.every(Number.isFinite) || values[2] <= 0 || values[3] <= 0) {
      return null;
    }
    return {
      x: values[0],
      y: values[1],
      width: values[2],
      height: values[3],
    };
  }

  function currentMode() {
    return density()?.runtime?.currentMode || 'manual';
  }

  function currentSnapshot(id = state()?.selected) {
    const S = state();
    if (!S || !id || (!S.objects.has(id) && !S.wires.has(id))) return null;
    return {
      id,
      surface: S.objects.get(id)?.surface || 'block-diagram',
      box: cloneBox(S.box),
      mode: currentMode(),
      revision: S.revision || '',
      jobKey: jobKey(),
    };
  }

  function jobKey() {
    const S = state();
    return [S?.job?.job_id, S?.revision].filter(Boolean).join('::');
  }

  function samePlace(first, second) {
    return Boolean(
      first
      && second
      && first.id === second.id
      && first.surface === second.surface
      && first.jobKey === second.jobKey
    );
  }

  function recordName(id) {
    const S = state();
    const item = S?.objects.get(id);
    const wire = S?.wires.get(id);
    if (item) return item.name || editor()?.label?.(item) || id;
    if (wire) return editor()?.wireName?.(wire) || wire.name || id;
    return id || '選択なし';
  }

  function syncCurrentView() {
    const S = state();
    const current = runtime.history[runtime.cursor];
    if (!S?.selected || !current || current.id !== S.selected) return;
    current.box = cloneBox(S.box);
    current.mode = currentMode();
    current.surface = S.surface;
  }

  function rememberRecent(id) {
    if (!id) return;
    runtime.recent = [id, ...runtime.recent.filter((value) => value !== id)]
      .filter((value) => state()?.objects.has(value) || state()?.wires.has(value))
      .slice(0, MAX_RECENT);
  }

  function appendHistory(snapshot) {
    if (!snapshot) return;
    const current = runtime.history[runtime.cursor];
    if (samePlace(current, snapshot)) {
      runtime.history[runtime.cursor] = snapshot;
      rememberRecent(snapshot.id);
      updateHistoryControls();
      return;
    }
    runtime.history = runtime.history.slice(0, runtime.cursor + 1);
    runtime.history.push(snapshot);
    if (runtime.history.length > MAX_HISTORY) runtime.history.shift();
    runtime.cursor = runtime.history.length - 1;
    rememberRecent(snapshot.id);
    updateHistoryControls();
  }

  function resetHistory(reason = 'job') {
    runtime.history = [];
    runtime.cursor = -1;
    runtime.recent = [];
    runtime.results = [];
    runtime.activeIndex = 0;
    runtime.jobKey = jobKey();
    runtime.elements.dialog?.setAttribute('data-reset-reason', reason);
    updateHistoryControls();
  }

  function restoreBox(snapshot) {
    if (!snapshot?.box) return;
    const activeDensity = density();
    if (activeDensity?.ready && typeof activeDensity.applyBox === 'function') {
      activeDensity.applyBox(snapshot.box, snapshot.mode || 'manual');
      return;
    }
    const S = state();
    if (!S?.el?.modelGraphSvg) return;
    S.box = { ...snapshot.box };
    S.el.modelGraphSvg.setAttribute(
      'viewBox',
      `${snapshot.box.x} ${snapshot.box.y} ${snapshot.box.width} ${snapshot.box.height}`,
    );
  }

  function focusSelected({ fit = false } = {}) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const S = state();
        const id = S?.selected;
        if (!id) return;
        if (fit) density()?.fit?.('focus');
        const selector = S.wires.has(id)
          ? `[data-wire-id="${CSS.escape(id)}"]`
          : `[data-object-id="${CSS.escape(id)}"]`;
        document.querySelector(selector)?.focus?.({ preventScroll: true });
        document.querySelector(`[data-list-id="${CSS.escape(id)}"]`)
          ?.scrollIntoView?.({ block: 'nearest' });
      });
    });
  }

  function replayHistory(index) {
    const E = editor();
    const S = state();
    const snapshot = runtime.history[index];
    if (!E || !S || !snapshot) return false;
    if (snapshot.jobKey !== jobKey()) {
      resetHistory('revision-changed');
      return false;
    }
    if (!S.objects.has(snapshot.id) && !S.wires.has(snapshot.id)) {
      runtime.history.splice(index, 1);
      runtime.cursor = Math.min(runtime.cursor, runtime.history.length - 1);
      updateHistoryControls();
      return false;
    }
    syncCurrentView();
    runtime.replaying = true;
    runtime.cursor = index;
    try {
      runtime.originalSelect.call(E, snapshot.id, true);
    } finally {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          restoreBox(snapshot);
          runtime.replaying = false;
          updateHistoryControls();
          focusSelected();
        });
      });
    }
    return true;
  }

  function goBack() {
    if (runtime.cursor <= 0) return false;
    return replayHistory(runtime.cursor - 1);
  }

  function goForward() {
    if (runtime.cursor < 0 || runtime.cursor >= runtime.history.length - 1) {
      return false;
    }
    return replayHistory(runtime.cursor + 1);
  }

  function updateHistoryControls() {
    const back = runtime.elements.back;
    const forward = runtime.elements.forward;
    const status = runtime.elements.historyStatus;
    const previous = runtime.history[runtime.cursor - 1];
    const next = runtime.history[runtime.cursor + 1];
    if (back) {
      back.disabled = runtime.cursor <= 0;
      back.title = previous
        ? `前の選択へ戻る: ${recordName(previous.id)} (Alt+←)`
        : '前の選択はありません (Alt+←)';
    }
    if (forward) {
      forward.disabled = runtime.cursor < 0
        || runtime.cursor >= runtime.history.length - 1;
      forward.title = next
        ? `次の選択へ進む: ${recordName(next.id)} (Alt+→)`
        : '次の選択はありません (Alt+→)';
    }
    if (status) {
      status.textContent = runtime.cursor >= 0
        ? `${runtime.cursor + 1}/${runtime.history.length}`
        : '0/0';
      status.title = '選択履歴';
    }
  }

  function normalize(value) {
    return String(value || '')
      .normalize('NFKC')
      .toLocaleLowerCase('ja-JP')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function surfaceLabel(surface) {
    return SURFACE_LABELS[surface] || surface || '不明';
  }

  function categoryLabel(item, wire = false) {
    if (wire) return CATEGORY_LABELS.wire;
    return CATEGORY_LABELS[item?.category]
      || editor()?.label?.(item)
      || item?.kind
      || 'オブジェクト';
  }

  function dataType(record, wire = false) {
    if (wire) return enhancements()?.wireType?.(record) || 'unknown';
    return enhancements()?.objectType?.(record) || record?.data_type || 'unknown';
  }

  function connectionCount(record, wire = false) {
    if (wire) {
      return Math.max(
        record?.target_terminal_ids?.length || 0,
        record?.target_object_ids?.length || 0,
      );
    }
    return new Set([
      ...(record?.wire_ids || []),
      ...(record?.terminal_ids || []),
      ...(record?.linked_terminal_ids || []),
    ]).size;
  }

  function descriptor(id) {
    const S = state();
    const item = S?.objects.get(id);
    const wire = S?.wires.get(id);
    if (!item && !wire) return null;
    const isWire = Boolean(wire);
    const record = item || wire;
    const surface = item?.surface || 'block-diagram';
    const name = isWire
      ? editor()?.wireName?.(wire) || wire.name || '配線'
      : item.name || editor()?.label?.(item) || item.id;
    const kind = categoryLabel(item, isWire);
    const type = dataType(record, isWire);
    const count = connectionCount(record, isWire);
    const source = item?.source || {};
    const searchText = normalize([
      name,
      kind,
      type,
      surfaceLabel(surface),
      SURFACE_BADGES[surface],
      item?.kind,
      item?.class_name,
      item?.uid,
      item?.symbol,
      item?.data_type,
      source.file,
      source.xml_path,
      wire?.name,
      wire?.net_id,
    ].filter(Boolean).join(' '));
    return {
      id,
      item,
      wire,
      isWire,
      surface,
      name,
      kind,
      type,
      count,
      searchText,
      badge: SURFACE_BADGES[surface] || 'VI',
      glyph: isWire ? '⌁' : item.symbol || (item.category === 'terminal' ? '●' : '◇'),
    };
  }

  function allDescriptors() {
    const S = state();
    if (!S?.vi) return [];
    return [
      ...S.objects.keys(),
      ...S.wires.keys(),
    ].map(descriptor).filter(Boolean);
  }

  function connectedIds() {
    const E = editor();
    const S = state();
    const selected = S?.selected;
    const ids = new Set();
    const item = S?.objects.get(selected);
    const wire = S?.wires.get(selected);
    if (item) {
      [
        E?.counterpartId?.(item),
        item.owner_object_id,
        item.linked_object_id,
        ...(item.terminal_ids || []),
        ...(item.linked_terminal_ids || []),
        ...(item.wire_ids || []),
      ].filter(Boolean).forEach((id) => ids.add(id));
      (item.wire_ids || []).forEach((wireId) => {
        const relatedWire = S.wires.get(wireId);
        [
          relatedWire?.source_object_id,
          relatedWire?.source_terminal_id,
          ...(relatedWire?.target_object_ids || []),
          ...(relatedWire?.target_terminal_ids || []),
        ].filter(Boolean).forEach((id) => ids.add(id));
      });
    }
    if (wire) {
      [
        wire.source_object_id,
        wire.source_terminal_id,
        ...(wire.target_object_ids || []),
        ...(wire.target_terminal_ids || []),
      ].filter(Boolean).forEach((id) => ids.add(id));
    }
    ids.delete(selected);
    return [...ids].filter((id) => S.objects.has(id) || S.wires.has(id));
  }

  function scoreDescriptor(value, query, recentIndex, related) {
    const tokens = normalize(query).split(' ').filter(Boolean);
    if (!tokens.length) return 0;
    if (!tokens.every((token) => value.searchText.includes(token))) {
      return Number.NEGATIVE_INFINITY;
    }
    const normalizedName = normalize(value.name);
    const normalizedKind = normalize(value.kind);
    let score = 0;
    tokens.forEach((token) => {
      if (normalizedName === token) score += 1200;
      else if (normalizedName.startsWith(token)) score += 800;
      else if (normalizedName.includes(token)) score += 520;
      if (normalizedKind === token) score += 260;
      else if (normalizedKind.includes(token)) score += 140;
      if (normalize(value.type).includes(token)) score += 90;
    });
    if (value.surface === state()?.surface) score += 35;
    if (related.has(value.id)) score += 180;
    if (recentIndex.has(value.id)) score += Math.max(0, 80 - recentIndex.get(value.id) * 4);
    return score;
  }

  function defaultResults() {
    const S = state();
    const seen = new Set();
    const values = [];
    const append = (id, group) => {
      if (!id || seen.has(id)) return;
      const value = descriptor(id);
      if (!value) return;
      seen.add(id);
      values.push({ ...value, group });
    };
    connectedIds().forEach((id) => append(id, '現在の選択に接続'));
    runtime.recent.forEach((id) => append(id, '最近の選択'));
    if (!values.length) {
      allDescriptors()
        .filter((value) => value.surface === S?.surface && !value.isWire)
        .slice(0, 16)
        .forEach((value) => append(value.id, surfaceLabel(value.surface)));
    }
    return values.slice(0, MAX_RESULTS);
  }

  function searchResults(query) {
    if (!normalize(query)) return defaultResults();
    const related = new Set(connectedIds());
    const recentIndex = new Map(runtime.recent.map((id, index) => [id, index]));
    return allDescriptors()
      .map((value) => ({
        ...value,
        group: '検索結果',
        score: scoreDescriptor(value, query, recentIndex, related),
      }))
      .filter((value) => Number.isFinite(value.score))
      .sort((first, second) => (
        second.score - first.score
        || first.name.localeCompare(second.name, 'ja')
      ))
      .slice(0, MAX_RESULTS);
  }

  function setActiveIndex(index, { scroll = true } = {}) {
    if (!runtime.results.length) {
      runtime.activeIndex = 0;
      runtime.elements.query?.removeAttribute('aria-activedescendant');
      return;
    }
    runtime.activeIndex = Math.max(0, Math.min(runtime.results.length - 1, index));
    runtime.elements.results
      ?.querySelectorAll('[data-navigation-result]')
      .forEach((element, itemIndex) => {
        const active = itemIndex === runtime.activeIndex;
        element.classList.toggle('is-active', active);
        element.setAttribute('aria-selected', String(active));
        if (active) {
          runtime.elements.query?.setAttribute('aria-activedescendant', element.id);
          if (scroll) element.scrollIntoView({ block: 'nearest' });
        }
      });
  }

  function resultElement(value, index) {
    const button = document.createElement('button');
    button.type = 'button';
    button.id = `vi-navigation-result-${index}`;
    button.className = 'vi-navigation-result';
    button.dataset.navigationResult = value.id;
    button.setAttribute('role', 'option');
    button.setAttribute('aria-selected', String(index === runtime.activeIndex));

    const badge = document.createElement('span');
    badge.className = `vi-navigation-surface is-${value.surface}`;
    badge.textContent = value.badge;

    const glyph = document.createElement('span');
    glyph.className = 'vi-navigation-glyph';
    glyph.textContent = value.glyph;

    const copy = document.createElement('span');
    copy.className = 'vi-navigation-copy';
    const title = document.createElement('strong');
    title.textContent = value.name;
    const meta = document.createElement('small');
    meta.textContent = `${surfaceLabel(value.surface)} · ${value.kind} · ${value.type}`;
    copy.append(title, meta);

    const count = document.createElement('span');
    count.className = 'vi-navigation-count';
    count.textContent = value.count ? `${value.count}接続` : '接続なし';

    button.append(badge, glyph, copy, count);
    return button;
  }

  function renderResults() {
    const query = runtime.elements.query?.value || '';
    runtime.results = searchResults(query);
    runtime.activeIndex = Math.min(runtime.activeIndex, Math.max(0, runtime.results.length - 1));
    const fragment = document.createDocumentFragment();
    let previousGroup = null;
    runtime.results.forEach((value, index) => {
      if (value.group !== previousGroup) {
        const heading = document.createElement('div');
        heading.className = 'vi-navigation-group';
        heading.setAttribute('role', 'presentation');
        heading.textContent = value.group;
        fragment.append(heading);
        previousGroup = value.group;
      }
      fragment.append(resultElement(value, index));
    });
    if (!runtime.results.length) {
      const empty = document.createElement('div');
      empty.className = 'vi-navigation-empty';
      empty.textContent = '一致するVIオブジェクトはありません。名称・種類・UIDを変えて検索してください。';
      fragment.append(empty);
    }
    runtime.elements.results?.replaceChildren(fragment);
    if (runtime.elements.summary) {
      runtime.elements.summary.textContent = normalize(query)
        ? `${runtime.results.length}件 · 全Surfaceを検索`
        : runtime.results.length
          ? '接続先と最近の選択'
          : '検索語を入力してください';
    }
    setActiveIndex(runtime.activeIndex, { scroll: false });
  }

  function clearRevealFilters(id) {
    const S = state();
    const item = S?.objects.get(id);
    if (!S) return;
    if (S.el?.modelGraphQuery) S.el.modelGraphQuery.value = '';
    if (S.el?.modelGraphKind) S.el.modelGraphKind.value = '';
    if (item?.category === 'terminal' && !S.showTerminals) {
      S.showTerminals = true;
      if (S.el?.viShowTerminals) S.el.viShowTerminals.checked = true;
    }
  }

  function navigateTo(id, { fit = true, close = true } = {}) {
    const E = editor();
    if (!E || (!state()?.objects.has(id) && !state()?.wires.has(id))) return false;
    clearRevealFilters(id);
    E.select(id, true);
    if (close) closePalette();
    focusSelected({ fit });
    return true;
  }

  function chooseActive() {
    const value = runtime.results[runtime.activeIndex];
    if (value) navigateTo(value.id);
  }

  function setBackgroundInert(value) {
    if (value) {
      runtime.inertStates = [
        document.querySelector('.topbar'),
        document.querySelector('.azure-application-shell'),
      ].filter(Boolean).map((element) => ({
        element,
        inert: element.inert,
      }));
      runtime.inertStates.forEach(({ element }) => { element.inert = true; });
      return;
    }
    runtime.inertStates.forEach(({ element, inert }) => { element.inert = inert; });
    runtime.inertStates = [];
  }

  function openPalette(initialQuery = '') {
    if (!state()?.vi || !runtime.elements.overlay) return false;
    if (runtime.open) {
      runtime.elements.query?.focus();
      return true;
    }
    runtime.open = true;
    runtime.restoreFocus = document.activeElement;
    runtime.elements.overlay.hidden = false;
    document.body.classList.add('vi-navigation-open');
    setBackgroundInert(true);
    runtime.elements.query.value = initialQuery;
    runtime.activeIndex = 0;
    renderResults();
    requestAnimationFrame(() => {
      runtime.elements.query?.focus();
      runtime.elements.query?.select();
    });
    return true;
  }

  function closePalette() {
    if (!runtime.open) return;
    runtime.open = false;
    runtime.elements.overlay.hidden = true;
    document.body.classList.remove('vi-navigation-open');
    setBackgroundInert(false);
    const target = runtime.restoreFocus;
    runtime.restoreFocus = null;
    requestAnimationFrame(() => target?.focus?.());
  }

  function focusableElements() {
    return [
      runtime.elements.query,
      ...runtime.elements.results.querySelectorAll('button:not(:disabled)'),
      runtime.elements.close,
    ].filter((element) => element && !element.hidden);
  }

  function trapTab(event) {
    const values = focusableElements();
    if (!values.length) return;
    const current = values.indexOf(document.activeElement);
    const next = event.shiftKey
      ? (current <= 0 ? values.length - 1 : current - 1)
      : (current < 0 || current === values.length - 1 ? 0 : current + 1);
    event.preventDefault();
    values[next].focus();
  }

  function handlePaletteKeydown(event) {
    if (!runtime.open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopImmediatePropagation();
      closePalette();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex(runtime.activeIndex + 1);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex(runtime.activeIndex - 1);
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      setActiveIndex(runtime.results.length - 1);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      chooseActive();
      return;
    }
    if (event.key === 'Tab') trapTab(event);
  }

  function editingTarget(target) {
    return target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || target?.isContentEditable;
  }

  function handleGlobalKeydown(event) {
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (runtime.open) closePalette();
      else openPalette();
      return;
    }
    if (runtime.open) {
      handlePaletteKeydown(event);
      return;
    }
    if (editingTarget(event.target)) return;
    if (event.altKey && event.key === 'ArrowLeft') {
      event.preventDefault();
      event.stopImmediatePropagation();
      goBack();
    } else if (event.altKey && event.key === 'ArrowRight') {
      event.preventDefault();
      event.stopImmediatePropagation();
      goForward();
    }
  }

  function buildHistoryControls() {
    const actions = document.querySelector('.vi-canvas-actions');
    if (!actions || document.querySelector('#vi-selection-history')) return;
    const group = document.createElement('span');
    group.id = 'vi-selection-history';
    group.className = 'vi-selection-history';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', '選択履歴');

    const back = document.createElement('button');
    back.id = 'vi-selection-back';
    back.type = 'button';
    back.className = 'vi-selection-history-button';
    back.textContent = '←';
    back.setAttribute('aria-label', '前の選択へ戻る');

    const forward = document.createElement('button');
    forward.id = 'vi-selection-forward';
    forward.type = 'button';
    forward.className = 'vi-selection-history-button';
    forward.textContent = '→';
    forward.setAttribute('aria-label', '次の選択へ進む');

    const status = document.createElement('output');
    status.id = 'vi-selection-history-status';
    status.className = 'vi-selection-history-status';
    status.textContent = '0/0';

    group.append(back, forward, status);
    actions.prepend(group);
    runtime.elements.back = back;
    runtime.elements.forward = forward;
    runtime.elements.historyStatus = status;
    back.addEventListener('click', goBack);
    forward.addEventListener('click', goForward);
  }

  function buildLauncher() {
    const actions = document.querySelector('.vi-header-actions');
    if (!actions || document.querySelector('#vi-navigation-launcher')) return;
    const button = document.createElement('button');
    button.id = 'vi-navigation-launcher';
    button.type = 'button';
    button.className = 'secondary-action button-reset vi-navigation-launcher';
    button.innerHTML = '<span aria-hidden="true">⌕</span><span>検索して移動</span><kbd>Ctrl K</kbd>';
    button.title = 'VI全体からオブジェクトを検索して移動 (Ctrl+K)';
    actions.insertBefore(button, actions.firstChild);
    runtime.elements.launcher = button;
    button.addEventListener('click', () => openPalette());
  }

  function buildDialog() {
    if (document.querySelector('#vi-navigation-overlay')) return;
    const overlay = document.createElement('div');
    overlay.id = 'vi-navigation-overlay';
    overlay.className = 'vi-navigation-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <section id="vi-navigation-dialog" class="vi-navigation-dialog" role="dialog" aria-modal="true" aria-labelledby="vi-navigation-title">
        <header class="vi-navigation-header">
          <div><strong id="vi-navigation-title">検索して移動</strong><small>フロントパネルとブロックダイアグラムを横断</small></div>
          <button id="vi-navigation-close" type="button" aria-label="検索して移動を閉じる">×</button>
        </header>
        <label class="vi-navigation-query-wrap" for="vi-navigation-query">
          <span aria-hidden="true">⌕</span>
          <input id="vi-navigation-query" type="search" autocomplete="off" spellcheck="false" placeholder="名称、種類、役割、class、UID、データ型" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="vi-navigation-results">
          <kbd>Ctrl K</kbd>
        </label>
        <div class="vi-navigation-summary"><span id="vi-navigation-summary">検索語を入力してください</span><span>FP / BD / 端子 / 配線</span></div>
        <div id="vi-navigation-results" class="vi-navigation-results" role="listbox" aria-label="VIオブジェクト検索結果"></div>
        <footer class="vi-navigation-footer"><span><kbd>↑</kbd><kbd>↓</kbd> 候補</span><span><kbd>Enter</kbd> 移動</span><span><kbd>Esc</kbd> 閉じる</span><span><kbd>Alt</kbd>+<kbd>←</kbd>/<kbd>→</kbd> 履歴</span></footer>
      </section>`;
    document.body.append(overlay);
    runtime.elements.overlay = overlay;
    runtime.elements.dialog = overlay.querySelector('#vi-navigation-dialog');
    runtime.elements.query = overlay.querySelector('#vi-navigation-query');
    runtime.elements.results = overlay.querySelector('#vi-navigation-results');
    runtime.elements.summary = overlay.querySelector('#vi-navigation-summary');
    runtime.elements.close = overlay.querySelector('#vi-navigation-close');

    runtime.elements.query.addEventListener('input', () => {
      runtime.activeIndex = 0;
      renderResults();
    });
    runtime.elements.dialog.addEventListener('keydown', handlePaletteKeydown, true);
    runtime.elements.results.addEventListener('click', (event) => {
      const button = event.target.closest('[data-navigation-result]');
      if (button) navigateTo(button.dataset.navigationResult);
    });
    runtime.elements.results.addEventListener('pointermove', (event) => {
      const button = event.target.closest('[data-navigation-result]');
      if (!button) return;
      const buttons = [...runtime.elements.results.querySelectorAll('[data-navigation-result]')];
      const index = buttons.indexOf(button);
      if (index >= 0 && index !== runtime.activeIndex) setActiveIndex(index, { scroll: false });
    });
    runtime.elements.close.addEventListener('click', closePalette);
    overlay.addEventListener('pointerdown', (event) => {
      if (event.target === overlay) closePalette();
    });
  }

  function wrapEditor() {
    const E = editor();
    if (!E || runtime.originalSelect) return false;
    runtime.originalSelect = E.select;
    runtime.originalInstall = E.install;
    runtime.originalRenderAll = E.renderAll;

    E.select = function selectWithNavigationHistory(id, reveal = false) {
      if (runtime.replaying) {
        return runtime.originalSelect.call(E, id, reveal);
      }
      syncCurrentView();
      const result = runtime.originalSelect.call(E, id, reveal);
      requestAnimationFrame(() => {
        appendHistory(currentSnapshot());
        updateHistoryControls();
      });
      return result;
    };

    if (typeof runtime.originalInstall === 'function') {
      E.install = function installWithNavigationReset(vi) {
        const result = runtime.originalInstall.call(E, vi);
        resetHistory('model-installed');
        return result;
      };
    }

    if (typeof runtime.originalRenderAll === 'function') {
      E.renderAll = function renderAllWithNavigationSync(...args) {
        const previousJob = runtime.jobKey;
        const result = runtime.originalRenderAll.apply(E, args);
        const nextJob = jobKey();
        if (previousJob && nextJob && previousJob !== nextJob) {
          resetHistory('revision-changed');
        } else {
          runtime.jobKey = nextJob;
          updateHistoryControls();
        }
        return result;
      };
    }
    return true;
  }

  function install() {
    const E = editor();
    const S = state();
    if (
      runtime.ready
      || !E?.S
      || !S?.el?.modelGraphSvg
      || !density()?.ready
      || !globalThis.VIComponentFit?.ready
    ) {
      return false;
    }
    runtime.ready = true;
    buildHistoryControls();
    buildLauncher();
    buildDialog();
    wrapEditor();
    runtime.jobKey = jobKey();
    if (S.selected) appendHistory(currentSnapshot());
    updateHistoryControls();
    document.addEventListener('keydown', handleGlobalKeydown, true);
    globalThis.VINavigationWorkflow = {
      ready: true,
      runtime,
      open: openPalette,
      close: closePalette,
      search: searchResults,
      navigateTo,
      goBack,
      goForward,
      resetHistory,
      connectedIds,
      allDescriptors,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 400) {
      setTimeout(() => waitForEditor(attempt + 1), 25);
      return;
    }
    globalThis.VINavigationWorkflow = {
      ready: false,
      error: 'VI editor navigation dependencies did not become ready',
      runtime,
    };
  }

  globalThis.VINavigationWorkflow = { ready: false, runtime };
  waitForEditor();
})();
