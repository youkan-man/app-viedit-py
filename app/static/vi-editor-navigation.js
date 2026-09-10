'use strict';

(() => {
  const state = {
    initialized: false,
    pendingSelection: null,
    gesture: null,
    suppressClickUntil: 0,
    lastAction: 'waiting',
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function rootElement() {
    return document.querySelector('#model-graph-svg');
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

  function clientToWorld(clientX, clientY) {
    const root = rootElement();
    if (!root) return null;
    const matrix = root.getScreenCTM?.();
    if (matrix) {
      try {
        const point = root.createSVGPoint();
        point.x = clientX;
        point.y = clientY;
        const transformed = point.matrixTransform(matrix.inverse());
        return { x: transformed.x, y: transformed.y };
      } catch {
        // Fall through to a preserveAspectRatio-aware calculation.
      }
    }

    const rect = root.getBoundingClientRect();
    const viewBox = root.viewBox?.baseVal;
    if (!viewBox || rect.width <= 0 || rect.height <= 0) return null;
    const scale = Math.min(rect.width / viewBox.width, rect.height / viewBox.height);
    const renderedWidth = viewBox.width * scale;
    const renderedHeight = viewBox.height * scale;
    const offsetX = rect.left + (rect.width - renderedWidth) / 2;
    const offsetY = rect.top + (rect.height - renderedHeight) / 2;
    return {
      x: viewBox.x + (clientX - offsetX) / scale,
      y: viewBox.y + (clientY - offsetY) / scale,
    };
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
    if (!E || !item || event.button !== 0) return;
    const bounds = E.effectiveBounds?.(item) || E.getBounds?.(item);
    const startWorld = clientToWorld(event.clientX, event.clientY);
    if (!bounds || !startWorld) return;

    cancelPendingSelection();
    E.S.selected = item.id;
    state.gesture = {
      pointerId: event.pointerId,
      item,
      targetId,
      mode: event.target.dataset.resize ? 'resize' : 'move',
      startClientX: event.clientX,
      startClientY: event.clientY,
      startWorld,
      grabOffset: {
        x: startWorld.x - bounds.x,
        y: startWorld.y - bounds.y,
      },
      startBounds: { ...bounds },
      moved: false,
      captured: false,
    };
    state.lastAction = 'pointerdown';

    // The core renderer also binds pointerdown to each SVG object. Stop the
    // event before it reaches that handler, but keep same-root capture
    // listeners alive for undo history. Pointer capture is deliberately
    // deferred until movement starts so click and double-click stay native.
    event.stopPropagation();
  }

  function moveGesture(event) {
    const E = editor();
    const gesture = state.gesture;
    if (!E || !gesture || event.pointerId !== gesture.pointerId) return;
    const item = gesture.item;
    const canEdit = gesture.mode === 'resize' ? item.resizable : item.movable;
    if (!canEdit) return;

    const world = clientToWorld(event.clientX, event.clientY);
    if (!world) return;
    const clientDistance = Math.hypot(
      event.clientX - gesture.startClientX,
      event.clientY - gesture.startClientY,
    );
    if (!gesture.moved && clientDistance < 2) return;
    if (!gesture.moved) {
      gesture.moved = true;
      gesture.captured = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }

    const dx = world.x - gesture.startWorld.x;
    const dy = world.y - gesture.startWorld.y;
    const next = gesture.mode === 'resize'
      ? {
        ...gesture.startBounds,
        width: Math.max(24, snapValue(gesture.startBounds.width + dx)),
        height: Math.max(20, snapValue(gesture.startBounds.height + dy)),
      }
      : {
        ...gesture.startBounds,
        x: snapValue(world.x - gesture.grabOffset.x),
        y: snapValue(world.y - gesture.grabOffset.y),
      };

    E.S.local.set(item.id, next);
    E.S.dirty.add(item.id);
    E.renderCanvas?.();
    E.renderInspector?.();
    E.saveState?.();
    state.lastAction = gesture.mode;
    event.preventDefault();
    event.stopPropagation();
  }

  function finishGesture(event) {
    const gesture = state.gesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (gesture.captured) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    if (gesture.moved) {
      state.suppressClickUntil = performance.now() + 350;
    }
    state.lastAction = gesture.moved ? `${gesture.mode}-end` : 'pointerup';
    state.gesture = null;
    event.stopPropagation();
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
    if (!E || !item) return;

    event.stopImmediatePropagation();
    if (performance.now() < state.suppressClickUntil) {
      event.preventDefault();
      return;
    }
    if (targetId && event.detail >= 2) {
      activateCounterpart(event);
      return;
    }
    cancelPendingSelection();
    if (!targetId) {
      state.lastAction = 'select';
      E.select(item.id);
      return;
    }

    // Preserve the original SVG node until the second click has had a chance
    // to arrive. A single click is committed after the double-click window.
    state.pendingSelection = setTimeout(() => {
      state.pendingSelection = null;
      state.lastAction = 'select';
      E.select(item.id);
    }, 220);
  }

  function install() {
    const root = rootElement();
    if (state.initialized || !root) return false;

    state.initialized = true;
    state.lastAction = 'bound';
    root.dataset.counterpartNavigationBound = 'true';
    root.dataset.svgCoordinateDrag = 'true';
    root.addEventListener('pointerdown', beginGesture, true);
    root.addEventListener('pointermove', moveGesture, true);
    root.addEventListener('pointerup', finishGesture, true);
    root.addEventListener('pointercancel', finishGesture, true);
    root.addEventListener('click', handleClick, true);
    root.addEventListener('dblclick', activateCounterpart, true);

    globalThis.VISemanticNavigationBridge = {
      ready: true,
      state,
      clientToWorld,
    };
    return true;
  }

  function waitForRoot(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForRoot(attempt + 1), 25);
  }

  globalThis.VISemanticNavigationBridge = {
    ready: false,
    state,
    clientToWorld,
  };
  waitForRoot();
})();
