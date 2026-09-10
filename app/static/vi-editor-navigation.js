'use strict';

(() => {
  const state = {
    initialized: false,
    pendingSelection: null,
    gesture: null,
    lastAction: 'waiting',
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function cancelPendingSelection() {
    if (state.pendingSelection == null) return;
    clearTimeout(state.pendingSelection);
    state.pendingSelection = null;
  }

  function recordForEvent(event) {
    const E = editor();
    const group = event.target.closest?.('[data-object-id]');
    const item = group ? E?.S?.objects?.get(group.dataset.objectId) : null;
    const targetId = item ? E?.counterpartId?.(item) : null;
    return { group, item, targetId };
  }

  function snapValue(value) {
    const S = editor()?.S;
    if (!S?.snap) return value;
    const grid = Math.max(1, Number(S.grid) || 1);
    return Math.round(value / grid) * grid;
  }

  function beginGesture(event) {
    const E = editor();
    const { item, targetId } = recordForEvent(event);
    if (!E || !item || !targetId || event.button !== 0) return;
    const bounds = E.effectiveBounds?.(item) || E.getBounds?.(item);
    if (!bounds) return;

    cancelPendingSelection();
    E.S.selected = item.id;
    state.gesture = {
      pointerId: event.pointerId,
      item,
      mode: event.target.dataset.resize ? 'resize' : 'move',
      startClientX: event.clientX,
      startClientY: event.clientY,
      startBounds: { ...bounds },
      moved: false,
      captured: false,
    };
    state.lastAction = 'pointerdown';

    // Do not invoke the core pointerdown handler here. It cancels the native
    // click sequence, which makes double-click navigation unreliable.
    // Pointer capture is deliberately deferred until actual movement starts;
    // capturing here retargets the following click to the SVG root.
    event.stopPropagation();
  }

  function moveGesture(event) {
    const E = editor();
    const gesture = state.gesture;
    if (!E || !gesture || event.pointerId !== gesture.pointerId) return;
    const item = gesture.item;
    const canEdit = gesture.mode === 'resize' ? item.resizable : item.movable;
    if (!canEdit) return;

    const rect = event.currentTarget.getBoundingClientRect();
    const view = E.S?.box;
    if (!view || rect.width <= 0 || rect.height <= 0) return;
    const dx = (event.clientX - gesture.startClientX) * view.width / rect.width;
    const dy = (event.clientY - gesture.startClientY) * view.height / rect.height;
    if (!gesture.moved && Math.hypot(dx, dy) < 1) return;
    if (!gesture.moved) {
      gesture.moved = true;
      gesture.captured = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }

    const next = gesture.mode === 'resize'
      ? {
        ...gesture.startBounds,
        width: Math.max(24, snapValue(gesture.startBounds.width + dx)),
        height: Math.max(20, snapValue(gesture.startBounds.height + dy)),
      }
      : {
        ...gesture.startBounds,
        x: snapValue(gesture.startBounds.x + dx),
        y: snapValue(gesture.startBounds.y + dy),
      };

    E.S.local.set(item.id, next);
    E.S.dirty.add(item.id);
    E.renderCanvas?.();
    E.renderInspector?.();
    E.saveState?.();
    state.lastAction = gesture.mode;
  }

  function finishGesture(event) {
    const gesture = state.gesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (gesture.captured) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    state.lastAction = gesture.moved ? `${gesture.mode}-end` : 'pointerup';
    state.gesture = null;
  }

  function activateCounterpart(event) {
    const E = editor();
    const { targetId } = recordForEvent(event);
    if (!E || !targetId) return false;
    cancelPendingSelection();
    state.lastAction = 'counterpart';
    event.preventDefault();
    event.stopImmediatePropagation();
    E.select(targetId, true);
    return true;
  }

  function handleClick(event) {
    const E = editor();
    const { item, targetId } = recordForEvent(event);
    if (!E || !item || !targetId) return;

    // Keep the SVG node alive between the two clicks. The first click is
    // committed as a normal selection only when no second click arrives.
    event.stopImmediatePropagation();
    if (event.detail >= 2) {
      activateCounterpart(event);
      return;
    }
    cancelPendingSelection();
    state.pendingSelection = setTimeout(() => {
      state.pendingSelection = null;
      state.lastAction = 'select';
      E.select(item.id);
    }, 220);
  }

  function install() {
    const root = document.querySelector('#model-graph-svg');
    if (state.initialized || !root) return false;

    // Bind to the stable SVG root as soon as it exists. The semantic editor
    // modules initialize later, but every event resolves their state lazily.
    state.initialized = true;
    state.lastAction = 'bound';
    root.dataset.counterpartNavigationBound = 'true';
    root.addEventListener('pointerdown', beginGesture, true);
    root.addEventListener('pointermove', moveGesture, true);
    root.addEventListener('pointerup', finishGesture, true);
    root.addEventListener('pointercancel', finishGesture, true);
    root.addEventListener('click', handleClick, true);
    root.addEventListener('dblclick', activateCounterpart, true);

    globalThis.VISemanticNavigationBridge = {
      ready: true,
      state,
    };
    return true;
  }

  function waitForRoot(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForRoot(attempt + 1), 25);
  }

  globalThis.VISemanticNavigationBridge = { ready: false, state };
  waitForRoot();
})();
