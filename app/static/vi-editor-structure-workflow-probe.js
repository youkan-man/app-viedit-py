'use strict';

(() => {
  function workflow() {
    return globalThis.VIStructureWorkflow;
  }

  function state() {
    return globalThis.VISemanticEditor?.S;
  }

  function baseFor(id) {
    return workflow()?.runtime?.baseObjects?.get(id) || {};
  }

  function itemRecord(id, hidden) {
    const item = state()?.objects?.get(id);
    const base = baseFor(id);
    const nativeSurface = base.surface
      || item?.native_surface
      || (item?.surface === 'block-diagram-inactive'
        ? 'block-diagram'
        : item?.surface)
      || null;
    return {
      id: id || null,
      exists: Boolean(item),
      hidden: Boolean(id && hidden.has(id)),
      surface: item?.surface || null,
      nativeSurface,
      visibleByWorkflowRule: Boolean(
        id
        && item
        && !hidden.has(id)
        && nativeSurface !== 'block-diagram-inactive'
      ),
      ownerObjectId: base.ownerObjectId || item?.owner_object_id || null,
      linkedObjectId: base.linkedObjectId || item?.linked_object_id || null,
      relativeToObjectId: base.relativeToObjectId
        || item?.bounds?.relative_to_object_id
        || null,
    };
  }

  function terminalOwnerId(terminalId, fallback = null) {
    const terminal = state()?.objects?.get(terminalId);
    const base = baseFor(terminalId);
    return base.linkedObjectId
      || base.ownerObjectId
      || base.relativeToObjectId
      || terminal?.linked_object_id
      || terminal?.owner_object_id
      || terminal?.bounds?.relative_to_object_id
      || fallback
      || null;
  }

  function wireRecord([id, wire], hidden) {
    const sourceObjectId = terminalOwnerId(
      wire.source_terminal_id,
      wire.source_object_id,
    );
    const targets = (wire.target_terminal_ids || []).map(
      (terminalId, index) => {
        const objectId = terminalOwnerId(
          terminalId,
          wire.target_object_ids?.[index],
        );
        return {
          index,
          terminal: itemRecord(terminalId, hidden),
          object: itemRecord(objectId, hidden),
          objectOptional: !objectId,
        };
      },
    );
    const sourceTerminal = itemRecord(wire.source_terminal_id, hidden);
    const sourceObject = itemRecord(sourceObjectId, hidden);
    const visibleTargets = targets.filter((target) => (
      target.terminal.visibleByWorkflowRule
      && (target.objectOptional || target.object.visibleByWorkflowRule)
    ));
    let rejection = null;
    if (!wire.source_terminal_id) rejection = 'missing-source-terminal-id';
    else if (!sourceTerminal.visibleByWorkflowRule) {
      rejection = 'source-terminal-not-visible';
    } else if (sourceObjectId && !sourceObject.visibleByWorkflowRule) {
      rejection = 'source-object-not-visible';
    } else if (!visibleTargets.length) {
      rejection = 'no-visible-targets';
    }
    return {
      id,
      rejection,
      sourceTerminal,
      sourceObject,
      targetTerminalIds: [...(wire.target_terminal_ids || [])],
      targetObjectIds: [...(wire.target_object_ids || [])],
      targets,
      visibleTargetCount: visibleTargets.length,
      terminalIds: [...(wire.terminal_ids || [])],
      endpointObjectIds: [...(wire.endpoint_object_ids || [])],
      hiddenFlag: Boolean(wire.hidden_by_structure_frame),
    };
  }

  function report() {
    const activeWorkflow = workflow();
    const hidden = activeWorkflow?.hiddenObjectIds?.() || new Set();
    return {
      hiddenIds: [...hidden].sort(),
      catalog: activeWorkflow
        ? [...activeWorkflow.runtime.wireCatalog.entries()].map(
          (entry) => wireRecord(entry, hidden),
        )
        : [],
      visibleWireIds: state() ? [...state().wires.keys()].sort() : [],
    };
  }

  globalThis.VIStructureWorkflowProbe = {
    ready: true,
    report,
  };
})();
