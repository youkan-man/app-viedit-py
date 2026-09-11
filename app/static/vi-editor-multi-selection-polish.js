'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: false,
    decorating: false,
    scheduled: false,
    primaryCandidate: null,
    observer: null,
    originalRenderCanvas: null,
    originalRenderAll: null,
  };

  function multi() {
    return globalThis.VIMultiSelection;
  }

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function projection() {
    return globalThis.VIComponentProjection;
  }

  function editingTarget(target) {
    return target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || target?.isContentEditable;
  }

  function visibleObjectIds() {
    const S = state();
    if (!S) return [];
    return [...document.querySelectorAll('#model-graph-svg [data-object-id]')]
      .filter((group) => {
        const item = S.objects.get(group.dataset.objectId);
        if (!item || item.surface !== S.surface) return false;
        if (item.category === 'terminal') return false;
        if (item.hidden_by_structure_frame) return false;
        if (group.closest('[aria-hidden="true"]')) return false;
        const style = getComputedStyle(group);
        return style.display !== 'none' && style.visibility !== 'hidden';
      })
      .map((group) => group.dataset.objectId);
  }

  function handleKeydown(event) {
    const M = multi();
    const S = state();
    if (!M?.ready || !S?.vi || editingTarget(event.target)) return;
    const modifier = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();

    if (modifier && key === 'a' && !event.altKey) {
      const ids = visibleObjectIds();
      if (!ids.length) return;
      const primary = ids.includes(M.runtime.primaryId)
        ? M.runtime.primaryId
        : ids.at(-1);
      M.setSelection(ids, primary);
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    if (M.runtime.selectedIds.size <= 1) return;
    if (modifier && key === 'c' && !event.altKey) {
      event.preventDefault();
      event.stopImmediatePropagation();
      void M.copySummary();
      return;
    }
    if (modifier && key === 'z' && !event.altKey) {
      const handled = event.shiftKey ? M.redo() : M.undo();
      if (handled) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    if (modifier && key === 'y' && !event.altKey) {
      if (M.redo()) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    if (event.key === 'Escape') {
      M.clearSelection();
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (modifier || event.altKey) return;
    const step = event.shiftKey ? 10 : 1;
    const movement = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    }[event.key];
    if (!movement) return;
    if (M.moveSelectionBy(movement[0], movement[1], '複数キー移動')) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }

  function capturePrimaryCandidate(event) {
    const M = multi();
    if (!M?.ready || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) {
      runtime.primaryCandidate = null;
      return;
    }
    const group = event.target.closest?.('#model-graph-svg [data-object-id]');
    const id = group?.dataset.objectId;
    if (
      !id
      || M.runtime.selectedIds.size <= 1
      || !M.runtime.selectedIds.has(id)
      || event.target.closest?.('.vi-resize-handle')
    ) {
      runtime.primaryCandidate = null;
      return;
    }
    runtime.primaryCandidate = {
      pointerId: event.pointerId,
      id,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    };
  }

  function trackPrimaryCandidate(event) {
    const candidate = runtime.primaryCandidate;
    if (!candidate || candidate.pointerId !== event.pointerId) return;
    if (
      Math.hypot(
        event.clientX - candidate.startX,
        event.clientY - candidate.startY,
      ) >= 3
    ) {
      candidate.moved = true;
    }
  }

  function finishPrimaryCandidate(event) {
    const candidate = runtime.primaryCandidate;
    if (!candidate || candidate.pointerId !== event.pointerId) return;
    runtime.primaryCandidate = null;
    if (candidate.moved) return;
    queueMicrotask(() => {
      const M = multi();
      if (
        !M?.ready
        || M.runtime.selectedIds.size <= 1
        || !M.runtime.selectedIds.has(candidate.id)
      ) {
        return;
      }
      M.setSelection([...M.runtime.selectedIds], candidate.id);
    });
  }

  function normalizeSurfaceSelection() {
    const M = multi();
    const S = state();
    if (!M?.ready || !S?.vi) return false;
    const before = [...M.runtime.selectedIds];
    const visible = before.filter((id) => S.objects.get(id)?.surface === S.surface);
    if (visible.length === before.length) return false;
    M.runtime.selectedIds = new Set(visible);
    M.runtime.primaryId = visible.includes(M.runtime.primaryId)
      ? M.runtime.primaryId
      : visible.at(-1) || null;
    M.runtime.rangeAnchorId = M.runtime.primaryId;
    if (S.objects.has(S.selected) && S.objects.get(S.selected)?.surface !== S.surface) {
      S.selected = M.runtime.primaryId;
      editor()?.renderInspector?.();
    }
    return true;
  }

  function projectedLocalBounds(item) {
    const E = editor();
    const logical = E?.effectiveBounds?.(item) || E?.getBounds?.(item);
    if (!logical) return null;
    const projected = projection()?.projectBounds?.(item, logical) || logical;
    return {
      x: projected.x - logical.x,
      y: projected.y - logical.y,
      width: projected.width,
      height: projected.height,
    };
  }

  function itemOutline(group, active) {
    let outline = group.querySelector(':scope > .vi-multi-selection-item-outline');
    if (!active) {
      outline?.remove();
      return;
    }
    const item = state()?.objects.get(group.dataset.objectId);
    const bounds = projectedLocalBounds(item);
    if (!item || !bounds) return;
    if (!outline) {
      outline = document.createElementNS(SVG_NS, 'rect');
      outline.classList.add('vi-multi-selection-item-outline');
      outline.setAttribute('pointer-events', 'none');
      group.append(outline);
    }
    outline.setAttribute('x', String(bounds.x));
    outline.setAttribute('y', String(bounds.y));
    outline.setAttribute('width', String(Math.max(1, bounds.width)));
    outline.setAttribute('height', String(Math.max(1, bounds.height)));
  }

  function decorate() {
    const M = multi();
    const S = state();
    if (!M?.ready || !S?.vi || runtime.decorating) return false;
    runtime.decorating = true;
    try {
      const changed = normalizeSurfaceSelection();
      document.querySelectorAll('#model-graph-svg [data-object-id]').forEach((group) => {
        itemOutline(group, M.runtime.selectedIds.has(group.dataset.objectId));
      });
      const geometry = document.querySelector('#vi-geometry-editor');
      if (geometry) {
        geometry.dataset.multiSelectionDisabled = String(
          M.runtime.selectedIds.size > 1,
        );
      }
      if (changed) M.decorate();
      return true;
    } finally {
      runtime.decorating = false;
    }
  }

  function schedule() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      runtime.scheduled = false;
      decorate();
    });
  }

  function wrapRenderers() {
    const E = editor();
    if (!E || runtime.originalRenderCanvas) return false;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderAll = E.renderAll;
    E.renderCanvas = function renderCanvasWithMultiSelectionPolish(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      schedule();
      return result;
    };
    E.renderAll = function renderAllWithMultiSelectionPolish(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      schedule();
      return result;
    };
    return true;
  }

  function install() {
    const M = multi();
    const root = state()?.el?.modelGraphSvg;
    if (runtime.ready || !M?.ready || !root || !editor()) return false;
    runtime.ready = true;
    wrapRenderers();
    runtime.observer = new MutationObserver(schedule);
    runtime.observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class'],
    });
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      button.addEventListener('click', () => requestAnimationFrame(schedule));
    });
    globalThis.VIMultiSelectionPolish = {
      ready: true,
      runtime,
      visibleObjectIds,
      normalizeSurfaceSelection,
      decorate,
      schedule,
    };
    decorate();
    return true;
  }

  function waitForMultiSelection(attempt = 0) {
    if (install()) return;
    if (attempt < 600) {
      setTimeout(() => waitForMultiSelection(attempt + 1), 25);
      return;
    }
    globalThis.VIMultiSelectionPolish = {
      ready: false,
      error: 'multi-selection runtime did not become ready',
      runtime,
    };
  }

  window.addEventListener('keydown', handleKeydown, true);
  window.addEventListener('pointerdown', capturePrimaryCandidate, true);
  window.addEventListener('pointermove', trackPrimaryCandidate, true);
  window.addEventListener('pointerup', finishPrimaryCandidate, true);
  window.addEventListener('pointercancel', finishPrimaryCandidate, true);
  globalThis.VIMultiSelectionPolish = { ready: false, runtime };
  waitForMultiSelection();
})();
