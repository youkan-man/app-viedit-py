'use strict';

(() => {
  const state = { initialized: false, queued: false, decorating: false };
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function svg(tag, className, attributes = {}) {
    const element = document.createElementNS(SVG_NS, tag);
    if (className) element.setAttribute('class', className);
    Object.entries(attributes).forEach(([name, value]) => {
      element.setAttribute(name, String(value));
    });
    return element;
  }

  function boundsFor(item) {
    const E = editor();
    return E?.effectiveBounds?.(item) || E?.getBounds?.(item) || item?.bounds || null;
  }

  function removeGenericValue(group) {
    group.querySelectorAll('.vi-control-display,.vi-control-value').forEach(
      (element) => element.remove(),
    );
  }

  function insertBeforeOverlay(group, element) {
    const overlay = group.querySelector('.vi-object-label,.vi-resize-handle,title');
    group.insertBefore(element, overlay || null);
  }

  function decorateCluster(group, item, bounds) {
    group.classList.add('is-cluster-container');
    removeGenericValue(group);
    if (!group.querySelector('.vi-cluster-interior')) {
      const interior = svg('rect', 'vi-cluster-interior', {
        x: 5,
        y: 16,
        width: Math.max(20, bounds.width - 10),
        height: Math.max(16, bounds.height - 21),
        rx: 1,
      });
      const header = svg('path', 'vi-cluster-header', {
        d: `M 5 16 H ${Math.max(25, bounds.width - 5)}`,
      });
      const count = svg('text', 'vi-cluster-count', {
        x: Math.max(10, bounds.width - 9),
        y: 12,
        'text-anchor': 'end',
      });
      const childCount = (item.child_object_ids || []).length;
      count.textContent = childCount ? `${childCount} element${childCount === 1 ? '' : 's'}` : 'cluster';
      insertBeforeOverlay(group, interior);
      insertBeforeOverlay(group, header);
      insertBeforeOverlay(group, count);
    }
  }

  function decorateArray(group, item, bounds) {
    group.classList.add('is-array-container');
    removeGenericValue(group);
    if (!group.querySelector('.vi-array-index')) {
      const index = svg('rect', 'vi-array-index', {
        x: 5,
        y: 5,
        width: Math.min(30, Math.max(18, bounds.width * 0.23)),
        height: 15,
      });
      const viewport = svg('rect', 'vi-array-viewport', {
        x: 5,
        y: 24,
        width: Math.max(20, bounds.width - 10),
        height: Math.max(16, bounds.height - 29),
      });
      insertBeforeOverlay(group, index);
      insertBeforeOverlay(group, viewport);
    }
  }

  function decorateBoolean(group, item, bounds) {
    if (item.surface !== 'front-panel') return;
    group.classList.add('is-boolean-control');
    removeGenericValue(group);
    if (!group.querySelector('.vi-boolean-led')) {
      const diameter = Math.max(12, Math.min(bounds.width, bounds.height) - 14);
      const led = svg('circle', 'vi-boolean-led', {
        cx: bounds.width / 2,
        cy: bounds.height / 2 + 2,
        r: diameter / 2,
      });
      const shine = svg('circle', 'vi-boolean-shine', {
        cx: bounds.width / 2 - diameter * 0.16,
        cy: bounds.height / 2 - diameter * 0.14,
        r: Math.max(1.5, diameter * 0.12),
      });
      insertBeforeOverlay(group, led);
      insertBeforeOverlay(group, shine);
    }
  }

  function decorateNumeric(group, item, bounds) {
    if (item.surface !== 'front-panel' || group.querySelector('.vi-numeric-spinner')) return;
    const display = group.querySelector('.vi-control-display');
    if (!display || bounds.width < 44) return;
    const spinnerWidth = Math.min(14, Math.max(9, bounds.width * 0.14));
    const x = Math.max(8, bounds.width - 8 - spinnerWidth);
    const y = Number(display.getAttribute('y') || 13);
    const height = Number(display.getAttribute('height') || 18);
    const spinner = svg('g', 'vi-numeric-spinner');
    spinner.append(
      svg('rect', 'vi-spinner-body', { x, y, width: spinnerWidth, height }),
      svg('path', 'vi-spinner-arrow', {
        d: `M ${x + 3} ${y + height * 0.4} L ${x + spinnerWidth / 2} ${y + 3} L ${x + spinnerWidth - 3} ${y + height * 0.4} Z`,
      }),
      svg('path', 'vi-spinner-arrow', {
        d: `M ${x + 3} ${y + height * 0.6} L ${x + spinnerWidth / 2} ${y + height - 3} L ${x + spinnerWidth - 3} ${y + height * 0.6} Z`,
      }),
    );
    insertBeforeOverlay(group, spinner);
  }

  function decorateString(group, item) {
    if (item.surface === 'front-panel') group.classList.add('is-string-control');
  }

  function primitivePath(bounds) {
    const width = Math.max(18, bounds.width);
    const height = Math.max(18, bounds.height);
    const shoulder = Math.max(5, Math.min(12, width * 0.25));
    return [
      `M 1 2`,
      `H ${width - shoulder}`,
      `L ${width - 1} ${height / 2}`,
      `L ${width - shoulder} ${height - 2}`,
      `H 1`,
      `L ${Math.min(7, shoulder)} ${height / 2}`,
      'Z',
    ].join(' ');
  }

  function decorateArithmetic(group, item, bounds) {
    group.classList.add('is-native-primitive', `is-primitive-${item.kind}`);
    const body = group.querySelector('.vi-block-node-body');
    body?.classList.add('is-replaced-body');
    if (!group.querySelector('.vi-primitive-body')) {
      const path = svg('path', 'vi-primitive-body', { d: primitivePath(bounds) });
      group.insertBefore(path, group.querySelector('.vi-node-symbol') || null);
    }
  }

  function decorateStructure(group, item, bounds) {
    group.classList.add('is-native-structure');
    if (!group.querySelector('.vi-structure-titlebar')) {
      const titlebar = svg('rect', 'vi-structure-titlebar', {
        x: 1,
        y: 1,
        width: Math.min(Math.max(56, String(item.name || '').length * 7 + 18), Math.max(56, bounds.width - 2)),
        height: 18,
      });
      const title = svg('text', 'vi-structure-title', { x: 7, y: 14 });
      title.textContent = item.name || 'Structure';
      group.insertBefore(titlebar, group.querySelector('.vi-node-symbol') || null);
      group.insertBefore(title, group.querySelector('.vi-node-symbol') || null);
    }
  }

  function decorateSubvi(group, item, bounds) {
    group.classList.add('is-native-subvi');
    if (!group.querySelector('.vi-subvi-icon')) {
      const size = Math.max(18, Math.min(bounds.width, bounds.height) - 8);
      const x = (bounds.width - size) / 2;
      const y = (bounds.height - size) / 2;
      const icon = svg('g', 'vi-subvi-icon');
      icon.append(
        svg('rect', 'vi-subvi-icon-body', { x, y, width: size, height: size }),
        svg('path', 'vi-subvi-icon-grid', {
          d: `M ${x + size / 2} ${y} V ${y + size} M ${x} ${y + size / 2} H ${x + size}`,
        }),
      );
      const text = svg('text', 'vi-subvi-icon-text', {
        x: bounds.width / 2,
        y: bounds.height / 2 + 4,
        'text-anchor': 'middle',
      });
      text.textContent = 'VI';
      icon.append(text);
      group.insertBefore(icon, group.querySelector('.vi-node-symbol') || null);
    }
  }

  function decorateConstant(group, item, bounds) {
    group.classList.add('is-native-constant');
    const symbol = group.querySelector('.vi-node-symbol');
    if (symbol) symbol.textContent = item.display_value || '0';
    if (bounds.width < 30 && group.querySelector('.vi-block-node-body')) {
      group.querySelector('.vi-block-node-body').setAttribute('width', '30');
    }
  }

  function decorateTerminal(group, item) {
    group.classList.add('is-native-terminal');
    const body = group.querySelector('.vi-terminal-body');
    if (!body) return;
    body.setAttribute('rx', item.direction === 'source' ? '0' : '1');
    if (item.direction === 'source') body.classList.add('is-output-terminal');
    if (item.direction === 'sink') body.classList.add('is-input-terminal');
  }

  function decorateObject(group, item) {
    const bounds = boundsFor(item);
    if (!bounds) return;
    group.dataset.parentObjectId = item.parent_object_id || '';
    group.dataset.nestingDepth = String(item.nesting_depth || 0);
    group.dataset.visualKind = item.visual_kind || '';
    group.classList.toggle('is-nested-object', Boolean(item.parent_object_id));

    if (item.category === 'terminal') {
      decorateTerminal(group, item);
      return;
    }
    if (item.visual_kind === 'cluster') decorateCluster(group, item, bounds);
    else if (item.visual_kind === 'array') decorateArray(group, item, bounds);
    else if (item.visual_kind === 'boolean') decorateBoolean(group, item, bounds);
    else if (item.visual_kind === 'numeric') decorateNumeric(group, item, bounds);
    else if (item.visual_kind === 'string') decorateString(group, item);
    else if (item.visual_kind === 'arithmetic' || item.visual_kind === 'primitive') {
      decorateArithmetic(group, item, bounds);
    } else if (item.visual_kind === 'structure') decorateStructure(group, item, bounds);
    else if (item.visual_kind === 'subvi') decorateSubvi(group, item, bounds);
    else if (item.visual_kind === 'constant') decorateConstant(group, item, bounds);
  }

  function sortObjectLayers(root, S) {
    const current = [...root.querySelectorAll(':scope > .vi-object')];
    if (current.length < 2) return;
    const desired = [...current].sort((first, second) => {
      const firstItem = S.objects.get(first.dataset.objectId) || {};
      const secondItem = S.objects.get(second.dataset.objectId) || {};
      const depthDifference = Number(firstItem.nesting_depth || 0) - Number(secondItem.nesting_depth || 0);
      if (depthDifference) return depthDifference;
      const firstContainer = (firstItem.child_object_ids || []).length ? 0 : 1;
      const secondContainer = (secondItem.child_object_ids || []).length ? 0 : 1;
      return firstContainer - secondContainer;
    });
    if (desired.every((element, index) => element === current[index])) return;
    desired.forEach((element) => root.append(element));
  }

  function decorateList(S) {
    document.querySelectorAll('#vi-object-list [data-list-id]').forEach((button) => {
      const item = S.objects.get(button.dataset.listId);
      if (!item) return;
      button.dataset.nestingDepth = String(item.nesting_depth || 0);
      button.style.setProperty('--vi-nesting-depth', String(item.nesting_depth || 0));
      if (item.parent_object_id) button.classList.add('is-nested-object');
      const childCount = (item.child_object_ids || []).length;
      if (childCount && !button.querySelector('.vi-list-child-count')) {
        const badge = document.createElement('span');
        badge.className = 'vi-list-child-count';
        badge.textContent = `${childCount}内包`;
        button.append(badge);
      }
    });
  }

  function decorate() {
    if (state.decorating) return;
    const E = editor();
    const S = E?.S;
    const root = document.querySelector('#model-graph-svg');
    if (!S || !root) return;
    state.decorating = true;
    try {
      root.querySelectorAll('[data-object-id]').forEach((group) => {
        const item = S.objects.get(group.dataset.objectId);
        if (item) decorateObject(group, item);
      });
      sortObjectLayers(root, S);
      decorateList(S);
      root.dataset.nativeStyleProjection = 'true';
    } finally {
      state.decorating = false;
    }
  }

  function queue() {
    if (state.queued) return;
    state.queued = true;
    requestAnimationFrame(() => {
      state.queued = false;
      decorate();
    });
  }

  function install() {
    const root = document.querySelector('#model-graph-svg');
    const list = document.querySelector('#vi-object-list');
    if (state.initialized || !root || !list) return false;
    state.initialized = true;
    new MutationObserver(queue).observe(root, { childList: true, subtree: true });
    new MutationObserver(queue).observe(list, { childList: true, subtree: true });
    queue();
    globalThis.VIRealism = { ready: true, decorate, state };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIRealism = { ready: false, state };
  waitForEditor();
})();
