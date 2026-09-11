'use strict';

(() => {
  const runtime = {
    ready: false,
    wrapped: false,
    originalInstall: null,
  };

  function unique(values) {
    return [...new Set(values.filter(Boolean))];
  }

  function workflow() {
    return globalThis.VIStructureWorkflow;
  }

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function isTerminal(id) {
    return state()?.objects.get(id)?.category === 'terminal';
  }

  function terminalCandidates(wire) {
    return unique([
      wire.source_terminal_id,
      ...(wire.target_terminal_ids || []),
      ...(wire.terminal_ids || []),
    ]).filter(isTerminal);
  }

  function chooseSource(wire, candidates) {
    if (isTerminal(wire.source_terminal_id)) return wire.source_terminal_id;
    return candidates.find((id) => state()?.objects.get(id)?.direction === 'source')
      || candidates[0]
      || null;
  }

  function normalizeWire(wire) {
    const candidates = terminalCandidates(wire);
    const sourceTerminalId = chooseSource(wire, candidates);
    const explicitTargets = unique(wire.target_terminal_ids || []).filter(
      (id) => id !== sourceTerminalId && isTerminal(id),
    );
    const targetTerminalIds = explicitTargets.length
      ? explicitTargets
      : candidates.filter((id) => id !== sourceTerminalId);
    const sourceTerminal = state()?.objects.get(sourceTerminalId);
    const sourceObjectId = sourceTerminal?.linked_object_id
      || sourceTerminal?.owner_object_id
      || sourceTerminal?.bounds?.relative_to_object_id
      || wire.source_object_id
      || null;
    const targetObjectIds = targetTerminalIds.map((id, index) => {
      const terminal = state()?.objects.get(id);
      return terminal?.linked_object_id
        || terminal?.owner_object_id
        || terminal?.bounds?.relative_to_object_id
        || wire.target_object_ids?.[index]
        || null;
    });
    return {
      ...wire,
      source_terminal_id: sourceTerminalId,
      target_terminal_ids: targetTerminalIds,
      terminal_ids: unique([sourceTerminalId, ...targetTerminalIds]),
      source_object_id: sourceObjectId,
      target_object_ids: targetObjectIds,
      endpoint_object_ids: unique([sourceObjectId, ...targetObjectIds]),
      target_terminal_count: targetTerminalIds.length,
      hidden_by_structure_frame: Boolean(wire.hidden_by_structure_frame),
    };
  }

  function normalizeCatalog() {
    const activeWorkflow = workflow();
    const S = state();
    if (!activeWorkflow?.ready || !S?.vi) return false;
    const normalized = new Map();
    activeWorkflow.runtime.wireCatalog.forEach((wire, id) => {
      normalized.set(id, normalizeWire(wire));
    });
    activeWorkflow.runtime.wireCatalog = normalized;
    activeWorkflow.runtime.baseObjects.forEach((base, id) => {
      const item = S.objects.get(id);
      if (!item) return;
      if (
        item.surface === 'block-diagram'
        || item.surface === 'block-diagram-inactive'
        || item.native_surface === 'block-diagram'
      ) {
        base.surface = 'block-diagram';
      }
    });
    return true;
  }

  function normalizeAndProject({ render = true } = {}) {
    const activeWorkflow = workflow();
    if (!normalizeCatalog()) return false;
    return activeWorkflow.applyFrameVisibility(null, {
      render,
      announce: false,
      restoreFrameSession: false,
    });
  }

  function wrapInstall() {
    const E = editor();
    if (!E || runtime.wrapped) return false;
    runtime.wrapped = true;
    runtime.originalInstall = E.install;
    E.install = function installWithNormalizedFrameWires(vi) {
      const result = runtime.originalInstall.call(E, vi);
      normalizeAndProject({ render: true });
      return result;
    };
    return true;
  }

  function install() {
    if (runtime.ready || !workflow()?.ready || !editor()) return false;
    runtime.ready = true;
    wrapInstall();
    if (state()?.vi) normalizeAndProject({ render: true });
    globalThis.VIStructureWorkflowCatalogFix = {
      ready: true,
      runtime,
      normalizeWire,
      normalizeCatalog,
      normalizeAndProject,
    };
    return true;
  }

  function waitForWorkflow(attempt = 0) {
    if (install()) return;
    if (attempt < 360) setTimeout(() => waitForWorkflow(attempt + 1), 25);
  }

  globalThis.VIStructureWorkflowCatalogFix = { ready: false, runtime };
  waitForWorkflow();
})();
