'use strict';

(() => {
  const MAX_SETTLE_ATTEMPTS = 24;
  const runtime = {
    ready: false,
    token: 0,
    settling: false,
    originalGoBack: null,
    originalGoForward: null,
  };

  function workflow() {
    return globalThis.VINavigationWorkflow;
  }

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function density() {
    return globalThis.VICanvasDensity;
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

  function jobKey() {
    const S = state();
    return [S?.job?.job_id, S?.revision].filter(Boolean).join('::');
  }

  function sameBox(first, second, tolerance = 0.05) {
    if (!first || !second) return false;
    return ['x', 'y', 'width', 'height'].every((key) => (
      Math.abs(Number(first[key]) - Number(second[key])) <= tolerance
    ));
  }

  function recordName(id) {
    const E = editor();
    const S = state();
    const item = S?.objects.get(id);
    const wire = S?.wires.get(id);
    if (item) return item.name || E?.label?.(item) || id;
    if (wire) return E?.wireName?.(wire) || wire.name || id;
    return id || '選択なし';
  }

  function currentMode() {
    return density()?.runtime?.currentMode || 'manual';
  }

  function rememberCurrentEntry() {
    const W = workflow();
    const R = W?.runtime;
    const S = state();
    const current = R?.history?.[R.cursor];
    if (!S?.selected || !current || current.id !== S.selected) return;
    current.box = cloneBox(S.box);
    current.mode = currentMode();
    current.surface = S.surface;
  }

  function updateControls() {
    const R = workflow()?.runtime;
    if (!R) return;
    const back = R.elements?.back;
    const forward = R.elements?.forward;
    const status = R.elements?.historyStatus;
    const previous = R.history[R.cursor - 1];
    const next = R.history[R.cursor + 1];
    if (back) {
      back.disabled = R.cursor <= 0;
      back.title = previous
        ? `前の選択へ戻る: ${recordName(previous.id)} (Alt+←)`
        : '前の選択はありません (Alt+←)';
    }
    if (forward) {
      forward.disabled = R.cursor < 0 || R.cursor >= R.history.length - 1;
      forward.title = next
        ? `次の選択へ進む: ${recordName(next.id)} (Alt+→)`
        : '次の選択はありません (Alt+→)';
    }
    if (status) {
      status.textContent = R.cursor >= 0
        ? `${R.cursor + 1}/${R.history.length}`
        : '0/0';
    }
  }

  function primeSurfaceView(snapshot) {
    const D = density();
    const S = state();
    const box = cloneBox(snapshot?.box);
    if (!D?.runtime?.surfaceViews || !box || !snapshot.surface) return;
    const viewport = S?.el?.modelGraphViewport?.getBoundingClientRect?.();
    const scale = viewport
      ? Math.min(viewport.width / box.width, viewport.height / box.height)
      : 1;
    D.runtime.surfaceViews.set(snapshot.surface, {
      box: { ...box },
      scale,
      mode: snapshot.mode || 'manual',
    });
  }

  function applySnapshotBox(snapshot) {
    const D = density();
    const S = state();
    const box = cloneBox(snapshot?.box);
    if (!box || !S) return false;
    if (D?.ready && typeof D.applyBox === 'function') {
      return D.applyBox(box, snapshot.mode || 'manual');
    }
    if (!S.el?.modelGraphSvg) return false;
    S.box = { ...box };
    S.el.modelGraphSvg.setAttribute(
      'viewBox',
      `${box.x} ${box.y} ${box.width} ${box.height}`,
    );
    return true;
  }

  function focusSelected() {
    requestAnimationFrame(() => {
      const S = state();
      const id = S?.selected;
      if (!id) return;
      const selector = S.wires.has(id)
        ? `[data-wire-id="${CSS.escape(id)}"]`
        : `[data-object-id="${CSS.escape(id)}"]`;
      document.querySelector(selector)?.focus?.({ preventScroll: true });
      document.querySelector(`[data-list-id="${CSS.escape(id)}"]`)
        ?.scrollIntoView?.({ block: 'nearest' });
    });
  }

  function finishReplay(token, snapshot) {
    const W = workflow();
    const R = W?.runtime;
    if (!R || token !== runtime.token) return;
    applySnapshotBox(snapshot);
    R.replaying = false;
    runtime.settling = false;
    updateControls();
    focusSelected();
  }

  function settleReplay(token, snapshot, attempt = 0, stableFrames = 0) {
    requestAnimationFrame(() => {
      const W = workflow();
      const R = W?.runtime;
      const S = state();
      const D = density()?.runtime;
      if (!R || !S || token !== runtime.token) return;

      const selectionReady = S.selected === snapshot.id;
      const surfaceReady = S.surface === snapshot.surface;
      const densityIdle = !D?.scheduled && !D?.pendingSurface && !D?.applying;
      if (!selectionReady || !surfaceReady || !densityIdle) {
        if (attempt >= MAX_SETTLE_ATTEMPTS) {
          finishReplay(token, snapshot);
          return;
        }
        setTimeout(
          () => settleReplay(token, snapshot, attempt + 1, 0),
          16,
        );
        return;
      }

      applySnapshotBox(snapshot);
      const stable = sameBox(S.box, snapshot.box) ? stableFrames + 1 : 0;
      if (stable >= 2 || attempt >= MAX_SETTLE_ATTEMPTS) {
        finishReplay(token, snapshot);
        return;
      }
      setTimeout(
        () => settleReplay(token, snapshot, attempt + 1, stable),
        24,
      );
    });
  }

  function stableReplay(index) {
    const W = workflow();
    const R = W?.runtime;
    const E = editor();
    const S = state();
    const source = R?.history?.[index];
    if (!W?.ready || !R || !E || !S || !source) return false;
    if (source.jobKey !== jobKey()) {
      W.resetHistory?.('revision-changed');
      return false;
    }
    if (!S.objects.has(source.id) && !S.wires.has(source.id)) {
      R.history.splice(index, 1);
      R.cursor = Math.min(R.cursor, R.history.length - 1);
      updateControls();
      return false;
    }

    rememberCurrentEntry();
    const snapshot = {
      ...source,
      box: cloneBox(source.box),
    };
    const token = ++runtime.token;
    runtime.settling = true;
    R.replaying = true;
    R.cursor = index;
    updateControls();
    primeSurfaceView(snapshot);
    R.originalSelect.call(E, snapshot.id, true);
    settleReplay(token, snapshot);
    return true;
  }

  function goBack() {
    const R = workflow()?.runtime;
    if (!R || R.cursor <= 0) return false;
    return stableReplay(R.cursor - 1);
  }

  function goForward() {
    const R = workflow()?.runtime;
    if (!R || R.cursor < 0 || R.cursor >= R.history.length - 1) return false;
    return stableReplay(R.cursor + 1);
  }

  function editingTarget(target) {
    return target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || target?.isContentEditable;
  }

  function handleHistoryKey(event) {
    const R = workflow()?.runtime;
    if (!R || R.open || editingTarget(event.target) || !event.altKey) return;
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (event.key === 'ArrowLeft') goBack();
    else goForward();
  }

  function bindButton(button, handler) {
    button?.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      handler();
    }, true);
  }

  function cancelPendingReplay(event) {
    if (!runtime.settling) return;
    if (event.target?.closest?.('#vi-selection-history')) return;
    runtime.token += 1;
    runtime.settling = false;
    const R = workflow()?.runtime;
    if (R) R.replaying = false;
  }

  function install() {
    const W = workflow();
    const R = W?.runtime;
    if (
      runtime.ready
      || !W?.ready
      || !R?.originalSelect
      || !density()?.ready
    ) return false;

    runtime.ready = true;
    runtime.originalGoBack = W.goBack;
    runtime.originalGoForward = W.goForward;
    W.goBack = goBack;
    W.goForward = goForward;
    W.stableReplay = stableReplay;

    window.addEventListener('keydown', handleHistoryKey, true);
    bindButton(R.elements?.back, goBack);
    bindButton(R.elements?.forward, goForward);
    state()?.el?.modelGraphViewport?.addEventListener(
      'pointerdown',
      cancelPendingReplay,
      true,
    );
    state()?.el?.modelGraphViewport?.addEventListener(
      'wheel',
      cancelPendingReplay,
      true,
    );

    globalThis.VINavigationHistoryStability = {
      ready: true,
      runtime,
      stableReplay,
      goBack,
      goForward,
      settleReplay,
      primeSurfaceView,
    };
    updateControls();
    return true;
  }

  function waitForWorkflow(attempt = 0) {
    if (install()) return;
    if (attempt < 400) {
      setTimeout(() => waitForWorkflow(attempt + 1), 25);
      return;
    }
    globalThis.VINavigationHistoryStability = {
      ready: false,
      error: 'navigation workflow did not become ready',
      runtime,
    };
  }

  globalThis.VINavigationHistoryStability = { ready: false, runtime };
  waitForWorkflow();
})();
