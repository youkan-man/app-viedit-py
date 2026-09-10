'use strict';

(() => {
  const runtime = { ready: false, saving: false };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function semanticState() {
    return editor()?.S;
  }

  function absoluteBounds(item) {
    const E = editor();
    return E?.effectiveBounds?.(item) || E?.getBounds?.(item) || null;
  }

  function sourceBounds(item, bounds) {
    const S = semanticState();
    if (!item || !bounds || !S) return bounds;
    if (item.bounds?.source_coordinate_space !== 'parent-relative') {
      return { ...bounds };
    }
    const parentId = item.parent_object_id || item.bounds?.relative_to_object_id;
    const parent = S.objects.get(parentId);
    const parentBounds = absoluteBounds(parent);
    if (!parentBounds) return { ...bounds };
    return {
      ...bounds,
      x: bounds.x - parentBounds.x,
      y: bounds.y - parentBounds.y,
    };
  }

  function nearlyEqual(first, second, tolerance = 1.1) {
    if (!first || !second) return false;
    return ['x', 'y', 'width', 'height'].every(
      (key) => Math.abs(Number(first[key]) - Number(second[key])) <= tolerance,
    );
  }

  function geometryProperty(item, detail) {
    const properties = detail.properties || [];
    const preferredIds = [
      item.bounds?.source_property_id,
      detail.bounds?.property_id,
    ].filter(Boolean);
    for (const id of preferredIds) {
      const property = properties.find(
        (candidate) => candidate.id === id && candidate.editable,
      );
      if (property) return property;
    }
    return properties.find((candidate) => {
      if (!candidate.editable) return false;
      const name = String(candidate.field_name || candidate.name || '').toLowerCase();
      return candidate.value_type === 'rect' || name.includes('bounds');
    }) || null;
  }

  function updateButton() {
    const S = semanticState();
    const save = document.querySelector('#vi-save-layout');
    const revert = document.querySelector('#vi-revert-layout');
    if (!S || !save) return;
    save.disabled = runtime.saving || !S.dirty.size;
    if (revert) revert.disabled = runtime.saving || !S.dirty.size;
    save.textContent = runtime.saving
      ? '保存して再読込中…'
      : S.dirty.size
        ? `位置を保存 (${S.dirty.size})`
        : '位置を保存';
  }

  function restorePending(pending) {
    const E = editor();
    const S = semanticState();
    if (!E || !S) return;
    pending.forEach((entry, id) => {
      if (!S.objects.has(id)) return;
      S.local.set(id, { ...entry.bounds });
      S.dirty.add(id);
    });
    E.renderAll?.(false);
  }

  function resetHistory() {
    const history = globalThis.VISemanticEnhancements?.history;
    if (history) {
      history.history.length = 0;
      history.future.length = 0;
    }
    const undo = document.querySelector('#vi-undo-layout');
    const redo = document.querySelector('#vi-redo-layout');
    const status = document.querySelector('#vi-history-status');
    if (undo) undo.disabled = true;
    if (redo) redo.disabled = true;
    if (status) status.textContent = '保存済み';
  }

  async function persistLayout(event) {
    event?.preventDefault();
    event?.stopImmediatePropagation();
    const E = editor();
    const S = semanticState();
    if (!E || !S?.job || runtime.saving || !S.dirty.size) return;

    runtime.saving = true;
    S.saving = true;
    updateButton();
    const pending = new Map();
    [...S.dirty].forEach((id) => {
      const item = S.objects.get(id);
      const bounds = item ? absoluteBounds(item) : null;
      if (item && bounds) {
        pending.set(id, { item: { ...item }, bounds: { ...bounds } });
      }
    });
    let latestJob = S.job;

    try {
      for (const [id, entry] of pending) {
        const item = S.objects.get(id) || entry.item;
        const detail = await apiRequest(
          `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
        );
        const property = geometryProperty(item, detail);
        const propertyId = property?.id;
        if (!propertyId) {
          throw new Error(`${item.name} の実座標プロパティを更新できません。`);
        }
        const storedBounds = sourceBounds(item, entry.bounds);
        const response = await apiRequest(
          `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              expected_file_sha256: detail.file_sha256,
              updates: [{
                property_id: propertyId,
                value: E.serializeBounds(item, storedBounds),
              }],
            }),
          },
        );
        latestJob = response.job || latestJob;
      }

      // Do not assign S.revision here. renderJob must observe the new
      // component_modified_at value and force a fresh /model response before
      // the local edited geometry is discarded.
      await globalThis.renderJob(latestJob, { scroll: false });

      const reloaded = semanticState();
      const mismatches = [];
      pending.forEach((entry, id) => {
        const item = reloaded?.objects.get(id);
        const bounds = item ? absoluteBounds(item) : null;
        if (!item || !nearlyEqual(bounds, entry.bounds)) {
          mismatches.push(entry.item.name || id);
        }
      });
      if (mismatches.length) {
        throw new Error(`保存後の再解析座標が一致しません: ${mismatches.join(', ')}`);
      }

      reloaded?.local.clear();
      reloaded?.dirty.clear();
      resetHistory();
      E.renderAll?.(false);
      showToast(`${pending.size}個の配置をXMLと意味モデルへ保存しました。`, 'success');
    } catch (error) {
      restorePending(pending);
      showToast(`配置保存: ${describeError(error)}`, 'error', 10000);
    } finally {
      const latestState = semanticState();
      if (latestState) latestState.saving = false;
      runtime.saving = false;
      updateButton();
    }
  }

  function install() {
    const button = document.querySelector('#vi-save-layout');
    if (runtime.ready || !button) return false;
    runtime.ready = true;
    button.dataset.persistenceBound = 'true';
    button.addEventListener('click', persistLayout, true);
    globalThis.VIPersistence = {
      ready: true,
      runtime,
      persistLayout,
      sourceBounds,
      nearlyEqual,
      geometryProperty,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIPersistence = { ready: false, runtime };
  waitForEditor();
})();
