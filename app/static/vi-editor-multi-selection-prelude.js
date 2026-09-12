'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: true,
    marquee: null,
    primaryCandidate: null,
    suppressPrimaryClickUntil: 0,
    suppressPrimaryClickId: null,
    copied: 0,
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

  function editingTarget(target) {
    return target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || target?.isContentEditable;
  }

  function clientToWorld(clientX, clientY) {
    const bridge = globalThis.VISemanticNavigationBridge;
    if (bridge?.ready && typeof bridge.clientToWorld === 'function') {
      return bridge.clientToWorld(clientX, clientY);
    }
    const root = state()?.el?.modelGraphSvg;
    const matrix = root?.getScreenCTM?.();
    if (!root || !matrix) return null;
    const point = root.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    const result = point.matrixTransform(matrix.inverse());
    return { x: result.x, y: result.y };
  }

  function ensureMarquee() {
    const root = state()?.el?.modelGraphSvg;
    if (!root) return null;
    let element = root.querySelector(':scope > #vi-multi-selection-marquee-safe');
    if (!element) {
      element = document.createElementNS(SVG_NS, 'rect');
      element.id = 'vi-multi-selection-marquee-safe';
      element.classList.add('vi-multi-selection-marquee');
      element.setAttribute('pointer-events', 'none');
      element.setAttribute('visibility', 'hidden');
      root.append(element);
    }
    return element;
  }

  function clientRect(startX, startY, endX, endY) {
    return {
      left: Math.min(startX, endX),
      top: Math.min(startY, endY),
      right: Math.max(startX, endX),
      bottom: Math.max(startY, endY),
      width: Math.abs(endX - startX),
      height: Math.abs(endY - startY),
    };
  }

  function worldRect(start, end) {
    return {
      x: Math.min(start.x, end.x),
      y: Math.min(start.y, end.y),
      width: Math.abs(end.x - start.x),
      height: Math.abs(end.y - start.y),
    };
  }

  function updateMarquee(start, end) {
    const element = ensureMarquee();
    if (!element) return;
    const rect = worldRect(start, end);
    element.setAttribute('visibility', 'visible');
    element.setAttribute('x', String(rect.x));
    element.setAttribute('y', String(rect.y));
    element.setAttribute('width', String(rect.width));
    element.setAttribute('height', String(rect.height));
  }

  function hideMarquee() {
    ensureMarquee()?.setAttribute('visibility', 'hidden');
  }

  function visibleObjectIdsInRect(rect) {
    const S = state();
    if (!S) return [];
    return [...document.querySelectorAll('#model-graph-svg [data-object-id]')]
      .filter((group) => {
        const item = S.objects.get(group.dataset.objectId);
        if (!item || item.surface !== S.surface || item.hidden_by_structure_frame) {
          return false;
        }
        if (group.closest('[aria-hidden="true"]')) return false;
        const style = getComputedStyle(group);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const box = group.getBoundingClientRect();
        if (box.width <= 0 || box.height <= 0) return false;
        const centerX = box.left + box.width / 2;
        const centerY = box.top + box.height / 2;
        return centerX >= rect.left
          && centerX <= rect.right
          && centerY >= rect.top
          && centerY <= rect.bottom;
      })
      .map((group) => group.dataset.objectId);
  }

  function beginMarquee(event, viewport) {
    const startWorld = clientToWorld(event.clientX, event.clientY);
    if (!startWorld) return false;
    runtime.marquee = {
      pointerId: event.pointerId,
      viewport,
      startClientX: event.clientX,
      startClientY: event.clientY,
      endClientX: event.clientX,
      endClientY: event.clientY,
      startWorld,
      endWorld: startWorld,
      additive: event.ctrlKey || event.metaKey || event.shiftKey,
      moved: false,
    };
    viewport.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function moveMarquee(event) {
    const gesture = runtime.marquee;
    if (!gesture || gesture.pointerId !== event.pointerId) return false;
    const world = clientToWorld(event.clientX, event.clientY);
    if (!world) return false;
    gesture.endClientX = event.clientX;
    gesture.endClientY = event.clientY;
    gesture.endWorld = world;
    const distance = Math.hypot(
      gesture.endClientX - gesture.startClientX,
      gesture.endClientY - gesture.startClientY,
    );
    if (!gesture.moved && distance >= 3) gesture.moved = true;
    if (gesture.moved) updateMarquee(gesture.startWorld, gesture.endWorld);
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function finishMarquee(event) {
    const gesture = runtime.marquee;
    if (!gesture || gesture.pointerId !== event.pointerId) return false;
    runtime.marquee = null;
    try {
      gesture.viewport.releasePointerCapture?.(event.pointerId);
    } catch {
      // The browser can release capture while the SVG subtree is redrawn.
    }
    hideMarquee();
    const M = multi();
    if (M?.ready) {
      if (gesture.moved) {
        const rect = clientRect(
          gesture.startClientX,
          gesture.startClientY,
          gesture.endClientX,
          gesture.endClientY,
        );
        const ids = visibleObjectIdsInRect(rect);
        M.setSelection(
          gesture.additive ? [...M.runtime.selectedIds, ...ids] : ids,
          ids.at(-1) || (gesture.additive ? M.runtime.primaryId : null),
        );
      } else if (!gesture.additive) {
        M.clearSelection();
      }
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  }

  function capturePrimaryCandidate(event) {
    const M = multi();
    if (
      !M?.ready
      || event.button !== 0
      || event.ctrlKey
      || event.metaKey
      || event.shiftKey
    ) {
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
    runtime.suppressPrimaryClickId = candidate.id;
    runtime.suppressPrimaryClickUntil = performance.now() + 400;
    queueMicrotask(() => {
      const M = multi();
      if (
        M?.ready
        && M.runtime.selectedIds.size > 1
        && M.runtime.selectedIds.has(candidate.id)
      ) {
        M.setSelection([...M.runtime.selectedIds], candidate.id);
      }
    });
  }

  async function copySummary() {
    const M = multi();
    if (!M?.ready) return false;
    const text = M.summaryText();
    let copied = false;
    if (typeof navigator.clipboard?.writeText === 'function') {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch {
        copied = false;
      }
    }
    if (!copied) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.className = 'vi-multi-selection-clipboard';
      document.body.append(textarea);
      textarea.select();
      copied = document.execCommand('copy');
      textarea.remove();
    }
    const button = document.querySelector('#vi-copy-selection-summary');
    if (button) {
      const previous = button.textContent;
      button.textContent = copied ? 'コピー済み' : 'コピー失敗';
      setTimeout(() => { button.textContent = previous; }, 1200);
    }
    if (copied) runtime.copied += 1;
    return copied;
  }

  function handlePointerDown(event) {
    if (!state()?.vi || event.button !== 0) return;
    capturePrimaryCandidate(event);
    const viewport = event.target.closest?.('#model-graph-viewport');
    const interactive = event.target.closest?.(
      '[data-object-id],[data-wire-id],button,input,select,textarea,a',
    );
    if (viewport && !interactive) beginMarquee(event, viewport);
  }

  function handlePointerMove(event) {
    trackPrimaryCandidate(event);
    if (runtime.marquee) moveMarquee(event);
  }

  function handlePointerUp(event) {
    finishPrimaryCandidate(event);
    if (runtime.marquee) finishMarquee(event);
  }

  function handleClick(event) {
    if (
      performance.now() < runtime.suppressPrimaryClickUntil
      && runtime.suppressPrimaryClickId
    ) {
      const group = event.target.closest?.('#model-graph-svg [data-object-id]');
      if (group?.dataset.objectId === runtime.suppressPrimaryClickId) {
        const M = multi();
        if (M?.ready && M.runtime.selectedIds.has(runtime.suppressPrimaryClickId)) {
          M.setSelection(
            [...M.runtime.selectedIds],
            runtime.suppressPrimaryClickId,
          );
        }
        runtime.suppressPrimaryClickId = null;
        runtime.suppressPrimaryClickUntil = 0;
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
    }
    const copyButton = event.target.closest?.('#vi-copy-selection-summary');
    if (!copyButton) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void copySummary();
  }

  function handleKeydown(event) {
    const M = multi();
    if (
      !M?.ready
      || M.runtime.selectedIds.size <= 1
      || editingTarget(event.target)
    ) {
      return;
    }
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && event.key.toLowerCase() === 'c' && !event.altKey) {
      event.preventDefault();
      event.stopImmediatePropagation();
      void copySummary();
    }
  }

  window.addEventListener('pointerdown', handlePointerDown, true);
  window.addEventListener('pointermove', handlePointerMove, true);
  window.addEventListener('pointerup', handlePointerUp, true);
  window.addEventListener('pointercancel', handlePointerUp, true);
  window.addEventListener('click', handleClick, true);
  window.addEventListener('keydown', handleKeydown, true);

  globalThis.VIMultiSelectionPrelude = {
    ready: true,
    runtime,
    copySummary,
    visibleObjectIdsInRect,
  };
})();
