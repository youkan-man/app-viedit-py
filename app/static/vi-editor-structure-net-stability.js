'use strict';

(() => {
  const runtime = {
    ready: false,
    queued: false,
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function isFrameStructure(item) {
    return Array.isArray(item?.structure_frames) && item.structure_frames.length > 1;
  }

  function normalizeNetEndpoints() {
    const S = state();
    if (!S?.vi) return;
    (S.vi.nets || []).forEach((net) => {
      const previous = net.target_object_ids || [];
      net.target_object_ids = (net.target_terminal_ids || []).map((terminalId, index) => {
        const terminal = S.objects.get(terminalId);
        return terminal?.linked_object_id
          || terminal?.owner_object_id
          || previous[index]
          || null;
      });
      const sourceTerminal = S.objects.get(net.source_terminal_id);
      net.source_object_id = sourceTerminal?.linked_object_id
        || sourceTerminal?.owner_object_id
        || net.source_object_id
        || null;
    });
  }

  function stabilizeStructureTitles() {
    const S = state();
    const root = S?.el?.modelGraphSvg;
    if (!S || !root) return;
    root.querySelectorAll('[data-object-id]').forEach((group) => {
      const item = S.objects.get(group.dataset.objectId);
      if (!isFrameStructure(item)) return;
      // The visible SVG title already carries the active frame. Remove the
      // nested <title> before the workflow decorator runs; repeatedly appending
      // text to it would otherwise retrigger its MutationObserver forever.
      group.querySelector(':scope > title')?.remove();
      group.setAttribute(
        'aria-description',
        `表示中フレーム: ${item.active_frame_label || item.active_frame_index || 0}`,
      );
    });
  }

  function run() {
    normalizeNetEndpoints();
    stabilizeStructureTitles();
  }

  function queue() {
    if (runtime.queued) return;
    runtime.queued = true;
    queueMicrotask(() => {
      runtime.queued = false;
      run();
    });
  }

  function install() {
    const root = document.querySelector('#model-graph-svg');
    if (runtime.ready || !root) return false;
    runtime.ready = true;
    new MutationObserver(queue).observe(root, {
      childList: true,
      subtree: true,
    });
    document.addEventListener('vi-structure-frame-changed', run);
    queue();
    globalThis.VIStructureNetStability = {
      ready: true,
      runtime,
      normalizeNetEndpoints,
      stabilizeStructureTitles,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 360) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIStructureNetStability = { ready: false, runtime };
  waitForEditor();
})();
