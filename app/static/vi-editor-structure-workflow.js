'use strict';

(() => {
  const runtime = {
    ready: false,
    applying: false,
    scheduled: false,
    currentJobId: null,
    baseObjects: new Map(),
    wireCatalog: new Map(),
    frameIndexes: new Map(),
    frameSessions: new Map(),
    activeNetId: null,
    endpointCursor: -1,
    originalInstall: null,
    originalRenderAll: null,
    originalRenderCanvas: null,
    originalRenderInspector: null,
    originalRenderList: null,
    originalSelect: null,
  };

  const TYPE_LABELS = {
    numeric: '数値',
    boolean: 'ブール',
    string: '文字列',
    path: 'パス',
    array: '配列',
    cluster: 'クラスタ',
    refnum: 'リファレンス',
    ring: 'リング / 列挙',
    table: '表',
    conflict: '型矛盾',
    unknown: '型未判定',
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function unique(values) {
    return [...new Set(values.filter(Boolean))];
  }

  function integer(value, fallback = 0) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function escapeSelector(value) {
    return globalThis.CSS?.escape
      ? CSS.escape(String(value))
      : String(value).replace(/["\\]/g, '\\$&');
  }

  function jobId() {
    return String(state()?.job?.job_id || 'unloaded');
  }

  function frameKey(structureId) {
    return `${jobId()}::${structureId}`;
  }

  function sessionKey(structureId, frameIndex) {
    return `${frameKey(structureId)}::${frameIndex}`;
  }

  function framesFor(item) {
    return Array.isArray(item?.structure_frames) ? item.structure_frames : [];
  }

  function isStructure(item) {
    return framesFor(item).length > 1;
  }

  function nativeSurface(item) {
    const base = runtime.baseObjects.get(item?.id);
    if (base?.surface) return base.surface;
    if (item?.native_surface) return item.native_surface;
    return item?.surface === 'block-diagram-inactive'
      ? 'block-diagram'
      : item?.surface;
  }

  function baseFor(item) {
    return runtime.baseObjects.get(item?.id) || {};
  }

  function parentIds(item) {
    const base = baseFor(item);
    return unique([
      base.parentObjectId,
      base.ownerObjectId,
      base.relativeToObjectId,
      item?.parent_object_id,
      item?.owner_object_id,
      item?.bounds?.relative_to_object_id,
    ]);
  }

  function structures() {
    const S = state();
    if (!S) return [];
    return [...S.objects.values()].filter(isStructure);
  }

  function currentFrameIndex(structure) {
    const frames = framesFor(structure);
    if (!frames.length) return 0;
    const stored = runtime.frameIndexes.get(frameKey(structure.id));
    const requested = stored == null
      ? integer(structure.active_frame_index)
      : integer(stored);
    return Math.max(0, Math.min(frames.length - 1, requested));
  }

  function frameLabel(frame, index) {
    return String(
      frame?.label
      ?? frame?.selector_value
      ?? frame?.event_name
      ?? frame?.name
      ?? `Frame ${index}`,
    );
  }

  function cloneWire(wire) {
    return {
      ...wire,
      target_terminal_ids: [...(wire.target_terminal_ids || [])],
      terminal_ids: [...(wire.terminal_ids || [])],
      target_object_ids: [...(wire.target_object_ids || [])],
      endpoint_object_ids: [...(wire.endpoint_object_ids || [])],
      type_definition_ids: [...(wire.type_definition_ids || [])],
      route_points: (wire.route_points || []).map((point) => ({ ...point })),
    };
  }

  function catalogWires(vi) {
    const records = [
      ...(vi?.all_structure_frame_wires || []),
      ...(vi?.inactive_structure_frame_wires || []),
      ...(vi?.wires || []),
    ];
    const byId = new Map();
    records.forEach((wire) => {
      if (wire?.id) byId.set(wire.id, cloneWire(wire));
    });
    return byId;
  }

  function captureModel(vi) {
    const S = state();
    if (!S || !vi) return false;
    const nextJobId = jobId();
    if (runtime.currentJobId !== nextJobId) {
      runtime.frameIndexes.clear();
      runtime.frameSessions.clear();
      runtime.activeNetId = null;
      runtime.endpointCursor = -1;
    }
    runtime.currentJobId = nextJobId;
    runtime.baseObjects = new Map(
      (vi.objects || []).filter((item) => item?.id).map((item) => [
        item.id,
        {
          surface: item.native_surface
            || (item.surface === 'block-diagram-inactive'
              ? 'block-diagram'
              : item.surface),
          parentObjectId: item.parent_object_id || null,
          ownerObjectId: item.owner_object_id || null,
          linkedObjectId: item.linked_object_id || null,
          relativeToObjectId: item.bounds?.relative_to_object_id || null,
          direction: item.direction || 'unknown',
          wireRoles: [...(item.wire_roles || [])],
        },
      ]),
    );
    runtime.wireCatalog = catalogWires(vi);
    structures().forEach((structure) => {
      const key = frameKey(structure.id);
      if (!runtime.frameIndexes.has(key)) {
        runtime.frameIndexes.set(key, currentFrameIndex(structure));
      }
    });
    return applyFrameVisibility(null, {
      render: false,
      announce: false,
      restoreFrameSession: false,
    });
  }

  function directInactiveIds() {
    const hidden = new Set();
    structures().forEach((structure) => {
      const frames = framesFor(structure);
      const activeIndex = currentFrameIndex(structure);
      const activeIds = new Set(frames[activeIndex]?.object_ids || []);
      frames.forEach((frame, index) => {
        frame.is_active = index === activeIndex;
        if (index === activeIndex) return;
        (frame.object_ids || []).forEach((id) => {
          if (!activeIds.has(id)) hidden.add(id);
        });
      });
      structure.active_frame_index = activeIndex;
      structure.active_frame_label = frameLabel(frames[activeIndex], activeIndex);
      structure.frame_view_mode = 'browser-only';
    });
    return hidden;
  }

  function hiddenObjectIds() {
    const S = state();
    if (!S) return new Set();
    const hidden = directInactiveIds();
    let changed = true;
    while (changed) {
      changed = false;
      S.objects.forEach((item) => {
        if (hidden.has(item.id) || nativeSurface(item) !== 'block-diagram') return;
        if (parentIds(item).some((id) => hidden.has(id))) {
          hidden.add(item.id);
          changed = true;
        }
      });
    }
    return hidden;
  }

  function objectVisible(id, hidden) {
    if (!id) return true;
    const item = state()?.objects.get(id);
    return Boolean(
      item
      && !hidden.has(id)
      && nativeSurface(item) !== 'block-diagram-inactive',
    );
  }

  function terminalOwnerId(terminalId, fallback = null) {
    const terminal = state()?.objects.get(terminalId);
    const base = baseFor(terminal);
    return base.linkedObjectId
      || base.ownerObjectId
      || base.relativeToObjectId
      || terminal?.linked_object_id
      || terminal?.owner_object_id
      || terminal?.bounds?.relative_to_object_id
      || fallback
      || null;
  }

  function projectWire(wire, hidden) {
    const S = state();
    if (!S || !wire?.source_terminal_id) return null;
    if (!objectVisible(wire.source_terminal_id, hidden)) return null;

    const sourceObjectId = terminalOwnerId(
      wire.source_terminal_id,
      wire.source_object_id,
    );
    if (sourceObjectId && !objectVisible(sourceObjectId, hidden)) return null;

    const targetTerminalIds = wire.target_terminal_ids || [];
    const pairs = targetTerminalIds.map((terminalId, index) => ({
      terminalId,
      objectId: terminalOwnerId(terminalId, wire.target_object_ids?.[index]),
      index,
    }));
    const visiblePairs = pairs.filter((pair) => (
      objectVisible(pair.terminalId, hidden)
      && (!pair.objectId || objectVisible(pair.objectId, hidden))
    ));
    if (!visiblePairs.length) return null;

    const projected = cloneWire(wire);
    projected.source_object_id = sourceObjectId;
    projected.target_terminal_ids = visiblePairs.map((pair) => pair.terminalId);
    projected.target_object_ids = visiblePairs.map((pair) => pair.objectId);
    projected.terminal_ids = [
      projected.source_terminal_id,
      ...projected.target_terminal_ids,
    ];
    projected.endpoint_object_ids = unique([
      projected.source_object_id,
      ...projected.target_object_ids,
    ]);
    projected.hidden_target_terminal_ids = pairs
      .filter((pair) => !visiblePairs.includes(pair))
      .map((pair) => pair.terminalId);
    projected.visible_branch_count = visiblePairs.length;
    projected.hidden_by_structure_frame = false;
    return projected;
  }

  function visibleWireProjection(hidden) {
    const visible = [];
    const inactive = [];
    let hiddenBranches = 0;
    runtime.wireCatalog.forEach((wire) => {
      const projected = projectWire(wire, hidden);
      if (!projected) {
        const record = cloneWire(wire);
        record.hidden_by_structure_frame = true;
        inactive.push(record);
        hiddenBranches += Math.max(1, wire.target_terminal_ids?.length || 0);
        return;
      }
      hiddenBranches += projected.hidden_target_terminal_ids.length;
      visible.push(projected);
    });
    return { visible, inactive, hiddenBranches };
  }

  function visibleItem(item, hidden) {
    return Boolean(item && !hidden.has(item.id));
  }

  function resetRelationships() {
    const S = state();
    if (!S) return;
    S.objects.forEach((item) => {
      const base = baseFor(item);
      item.parent_object_id = base.parentObjectId || null;
      item.owner_object_id = base.ownerObjectId || null;
      item.linked_object_id = base.linkedObjectId || null;
      item.terminal_ids = [];
      item.linked_terminal_ids = [];
      item.wire_ids = [];
      item.child_object_ids = [];
      if (item.category === 'terminal') {
        item.direction = base.direction || 'unknown';
        item.wire_roles = [];
        item.is_bidirectional = false;
      }
    });
  }

  function addOnce(item, key, value) {
    if (!item || !value) return;
    item[key] ||= [];
    if (!item[key].includes(value)) item[key].push(value);
  }

  function rebuildRelationships(wires, hidden) {
    const S = state();
    if (!S) return;
    resetRelationships();

    S.objects.forEach((item) => {
      if (!visibleItem(item, hidden)) return;
      const base = baseFor(item);
      const parentId = base.parentObjectId;
      const ownerId = base.ownerObjectId || base.relativeToObjectId;
      const linkedId = base.linkedObjectId;
      if (parentId && visibleItem(S.objects.get(parentId), hidden)) {
        addOnce(S.objects.get(parentId), 'child_object_ids', item.id);
      }
      if (item.category !== 'terminal') return;
      if (ownerId && visibleItem(S.objects.get(ownerId), hidden)) {
        addOnce(S.objects.get(ownerId), 'terminal_ids', item.id);
      }
      if (linkedId && visibleItem(S.objects.get(linkedId), hidden)) {
        addOnce(S.objects.get(linkedId), 'linked_terminal_ids', item.id);
      }
    });

    wires.forEach((wire) => {
      const sourceTerminal = S.objects.get(wire.source_terminal_id);
      if (sourceTerminal) addOnce(sourceTerminal, 'wire_roles', 'source');
      (wire.target_terminal_ids || []).forEach((id) => {
        addOnce(S.objects.get(id), 'wire_roles', 'sink');
      });
      (wire.terminal_ids || []).forEach((id) => {
        addOnce(S.objects.get(id), 'wire_ids', wire.id);
      });
      (wire.endpoint_object_ids || []).forEach((id) => {
        addOnce(S.objects.get(id), 'wire_ids', wire.id);
      });
    });

    S.objects.forEach((item) => {
      item.terminal_ids.sort((first, second) => (
        integer(S.objects.get(first)?.port_index, 999999)
        - integer(S.objects.get(second)?.port_index, 999999)
      ));
      item.child_object_ids.sort((first, second) => {
        const firstBounds = S.objects.get(first)?.bounds || {};
        const secondBounds = S.objects.get(second)?.bounds || {};
        return finite(firstBounds.y, 999999) - finite(secondBounds.y, 999999)
          || finite(firstBounds.x, 999999) - finite(secondBounds.x, 999999);
      });
      if (item.category !== 'terminal') return;
      const roles = new Set(item.wire_roles || []);
      if (roles.has('source') && roles.has('sink')) {
        item.direction = 'bidirectional';
        item.is_bidirectional = true;
      } else if (roles.has('source')) {
        item.direction = 'source';
      } else if (roles.has('sink')) {
        item.direction = 'sink';
      }
    });
  }

  function stableNetId(wire) {
    if (wire.net_id) return String(wire.net_id);
    if (wire.native_signal_uid) return `net:${wire.native_signal_uid}`;
    const nativeUid = String(wire.native_uid || '');
    const withoutBranch = wire.branch_index
      ? nativeUid.replace(/_[1-9][0-9]*$/, '')
      : nativeUid;
    return `net:${withoutBranch || wire.source_terminal_id || wire.id}`;
  }

  function rebuildNets(wires) {
    const groups = new Map();
    wires.forEach((wire) => {
      const id = stableNetId(wire);
      wire.net_id = id;
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(wire);
    });

    return [...groups.entries()].map(([id, branches]) => {
      const targets = new Map();
      branches.forEach((wire) => {
        (wire.target_terminal_ids || []).forEach((terminalId, index) => {
          if (!targets.has(terminalId)) {
            targets.set(terminalId, terminalOwnerId(
              terminalId,
              wire.target_object_ids?.[index],
            ));
          }
        });
      });
      const sourceTerminalIds = unique(
        branches.map((wire) => wire.source_terminal_id),
      );
      const sourceObjectIds = unique(
        branches.map((wire) => wire.source_object_id),
      );
      const branchCount = branches.reduce(
        (total, wire) => total + Math.max(1, wire.target_terminal_ids?.length || 0),
        0,
      );
      const types = unique(
        branches.map((wire) => wire.data_type).filter(
          (value) => value && value !== 'unknown',
        ),
      );
      const definitions = unique([
        ...branches.map((wire) => wire.type_definition_id),
        ...branches.flatMap((wire) => wire.type_definition_ids || []),
      ]);
      branches.forEach((wire) => {
        wire.branch_count = branchCount;
        wire.net_branch_count = branchCount;
      });
      return {
        id,
        native_signal_uid: branches[0]?.native_signal_uid || branches[0]?.native_uid || '',
        source_terminal_id: sourceTerminalIds[0] || null,
        source_terminal_ids: sourceTerminalIds,
        source_object_id: sourceObjectIds[0] || null,
        source_object_ids: sourceObjectIds,
        target_terminal_ids: [...targets.keys()],
        target_object_ids: [...targets.values()],
        branch_ids: branches.map((wire) => wire.id),
        branch_count: branchCount,
        wire_record_count: branches.length,
        data_type: types.length === 1 ? types[0] : types.length ? 'conflict' : 'unknown',
        type_definition_id: definitions.length === 1 ? definitions[0] : null,
        type_definition_ids: definitions,
        source_conflict: sourceTerminalIds.length > 1 || sourceObjectIds.length > 1,
      };
    });
  }

  function updateModelMetadata(hidden, projection, nets) {
    const S = state();
    if (!S) return;
    const allVisible = [...S.objects.values()].filter(
      (item) => !hidden.has(item.id) && item.surface !== 'block-diagram-inactive',
    );
    const visibleDiagram = allVisible.filter(
      (item) => nativeSurface(item) === 'block-diagram',
    );
    S.vi.wires = projection.visible;
    S.vi.inactive_structure_frame_wires = projection.inactive;
    S.vi.all_structure_frame_wires = [...runtime.wireCatalog.values()].map(cloneWire);
    S.vi.nets = nets;
    S.vi.surfaces ||= {};
    S.vi.surfaces['block-diagram'] = visibleDiagram.map((item) => item.id);

    const hierarchy = S.vi.hierarchy ||= {};
    hierarchy.roots = allVisible.filter((item) => {
      const parentId = baseFor(item).parentObjectId;
      return !parentId || hidden.has(parentId);
    }).map((item) => item.id);
    hierarchy.containers = allVisible.filter(
      (item) => item.child_object_ids?.length,
    ).map((item) => item.id);
    hierarchy.children_by_parent = Object.fromEntries(
      allVisible.filter((item) => item.child_object_ids?.length)
        .map((item) => [item.id, [...item.child_object_ids]]),
    );

    const summary = S.vi.summary ||= {};
    summary.block_diagram_nodes = visibleDiagram.filter(
      (item) => item.category === 'node',
    ).length;
    summary.terminals = visibleDiagram.filter(
      (item) => item.category === 'terminal',
    ).length;
    summary.wires = projection.visible.length;
    summary.resolved_wires = projection.visible.filter(
      (wire) => wire.resolved !== false,
    ).length;
    summary.wire_nets = nets.length;
    summary.hidden_structure_frame_objects = hidden.size;
    summary.hidden_structure_frame_wires = projection.inactive.length;
    summary.hidden_structure_frame_wire_branches = projection.hiddenBranches;
    summary.structure_frames = structures().reduce(
      (total, structure) => total + framesFor(structure).length,
      0,
    );

    const integrity = S.vi.integrity ||= {};
    integrity.structure_frame_runtime = {
      browser_only: true,
      inactive_object_count: hidden.size,
      inactive_wire_count: projection.inactive.length,
      hidden_branch_count: projection.hiddenBranches,
      visible_net_count: nets.length,
      selections: structures().map((structure) => ({
        object_id: structure.id,
        frame_index: currentFrameIndex(structure),
        frame_label: structure.active_frame_label,
      })),
    };
  }

  function isVisibleSelection(id, hidden, wireIds) {
    if (!id) return false;
    if (wireIds.has(id)) return true;
    return state()?.objects.has(id) && !hidden.has(id);
  }

  function structureAncestor(item) {
    const S = state();
    if (!S || !item) return null;
    if (isStructure(item)) return item;
    const pending = parentIds(item);
    const seen = new Set();
    while (pending.length) {
      const id = pending.shift();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const parent = S.objects.get(id);
      if (!parent) continue;
      if (isStructure(parent)) return parent;
      pending.push(...parentIds(parent));
    }
    return null;
  }

  function selectedStructure() {
    const S = state();
    if (!S?.selected) return null;
    const item = S.objects.get(S.selected);
    if (item) return structureAncestor(item);
    const wire = S.wires.get(S.selected);
    if (!wire) return null;
    return unique([
      wire.source_terminal_id,
      wire.source_object_id,
      ...(wire.target_terminal_ids || []),
      ...(wire.target_object_ids || []),
    ]).map((id) => structureAncestor(S.objects.get(id))).find(Boolean) || null;
  }

  function belongsToStructure(id, structureId) {
    const S = state();
    if (!S || !id || !structureId) return false;
    const objectBelongs = (item) => {
      if (!item) return false;
      if (item.id === structureId) return true;
      const pending = parentIds(item);
      const seen = new Set();
      while (pending.length) {
        const parentId = pending.shift();
        if (!parentId || seen.has(parentId)) continue;
        seen.add(parentId);
        if (parentId === structureId) return true;
        const parent = S.objects.get(parentId);
        if (parent) pending.push(...parentIds(parent));
      }
      return false;
    };
    const item = S.objects.get(id);
    if (item) return objectBelongs(item);
    const wire = S.wires.get(id) || runtime.wireCatalog.get(id);
    if (!wire) return false;
    return unique([
      wire.source_terminal_id,
      wire.source_object_id,
      ...(wire.target_terminal_ids || []),
      ...(wire.target_object_ids || []),
    ]).some((endpointId) => objectBelongs(S.objects.get(endpointId)));
  }

  function rememberFrameSession(structure) {
    const S = state();
    if (!S || !structure) return;
    const index = currentFrameIndex(structure);
    const selectedId = belongsToStructure(S.selected, structure.id)
      ? S.selected
      : structure.id;
    runtime.frameSessions.set(sessionKey(structure.id, index), {
      box: S.box ? { ...S.box } : null,
      mode: globalThis.VICanvasDensity?.runtime?.currentMode || 'manual',
      selectedId,
    });
  }

  function restoreView(box, mode) {
    const S = state();
    if (!S || !box) return;
    if (globalThis.VICanvasDensity?.applyBox) {
      globalThis.VICanvasDensity.applyBox(box, mode || 'manual', { remember: true });
      return;
    }
    S.box = { ...box };
    S.el.modelGraphSvg.setAttribute(
      'viewBox',
      `${box.x} ${box.y} ${box.width} ${box.height}`,
    );
  }

  function applyFrameVisibility(
    changedStructureId = null,
    {
      render = true,
      announce = true,
      restoreFrameSession = true,
    } = {},
  ) {
    const E = editor();
    const S = state();
    if (!E || !S?.vi || runtime.applying) return false;
    runtime.applying = true;
    const preservedView = S.box ? { ...S.box } : null;
    const preservedMode = globalThis.VICanvasDensity?.runtime?.currentMode || 'manual';
    try {
      const hidden = hiddenObjectIds();
      S.objects.forEach((item) => {
        if (nativeSurface(item) !== 'block-diagram') return;
        const inactive = hidden.has(item.id);
        item.native_surface = 'block-diagram';
        item.surface = inactive ? 'block-diagram-inactive' : 'block-diagram';
        item.hidden_by_structure_frame = inactive;
      });

      const projection = visibleWireProjection(hidden);
      rebuildRelationships(projection.visible, hidden);
      const nets = rebuildNets(projection.visible);
      const wireIds = new Set(projection.visible.map((wire) => wire.id));
      let targetSession = null;
      if (changedStructureId && restoreFrameSession) {
        const changed = S.objects.get(changedStructureId);
        targetSession = runtime.frameSessions.get(
          sessionKey(changedStructureId, currentFrameIndex(changed)),
        ) || null;
      }
      const preferredSelection = targetSession?.selectedId || S.selected;
      S.selected = isVisibleSelection(preferredSelection, hidden, wireIds)
        ? preferredSelection
        : changedStructureId || null;
      S.wires = new Map(projection.visible.map((wire) => [wire.id, wire]));
      updateModelMetadata(hidden, projection, nets);
      if (runtime.activeNetId && !nets.some((net) => net.id === runtime.activeNetId)) {
        runtime.activeNetId = null;
        runtime.endpointCursor = -1;
      }

      if (render) {
        E.renderAll(false);
        const box = targetSession?.box || preservedView;
        const mode = targetSession?.mode || preservedMode;
        requestAnimationFrame(() => {
          restoreView(box, mode);
          decorate();
          globalThis.VIReadability?.schedule?.();
        });
      }
      document.dispatchEvent(new CustomEvent('vi-structure-frame-changed', {
        detail: {
          structureId: changedStructureId,
          hiddenObjectCount: hidden.size,
          visibleWireCount: projection.visible.length,
          visibleNetCount: nets.length,
        },
      }));
      if (announce && changedStructureId) {
        const structure = S.objects.get(changedStructureId);
        globalThis.showToast?.(
          `${structure?.name || 'Structure'}: ${structure?.active_frame_label || 'Frame'} を表示しました（閲覧のみ）。`,
          'success',
        );
      }
      return true;
    } finally {
      runtime.applying = false;
      renderWorkflowPanels();
      scheduleDecoration();
    }
  }

  function switchFrame(structureId, requestedIndex) {
    const S = state();
    const structure = S?.objects.get(structureId);
    const frames = framesFor(structure);
    if (!structure || !frames.length) return false;
    rememberFrameSession(structure);
    const index = Math.max(
      0,
      Math.min(frames.length - 1, integer(requestedIndex)),
    );
    if (index === currentFrameIndex(structure)) return true;
    runtime.frameIndexes.set(frameKey(structure.id), index);
    return applyFrameVisibility(structure.id);
  }

  function netById(id) {
    return (state()?.vi?.nets || []).find((net) => net.id === id) || null;
  }

  function netIdsForItem(item) {
    const S = state();
    if (!S || !item) return [];
    return unique((item.wire_ids || []).map((id) => S.wires.get(id)?.net_id));
  }

  function netCandidates() {
    const S = state();
    if (!S?.selected) return [];
    const wire = S.wires.get(S.selected);
    if (wire?.net_id) return [wire.net_id];
    return netIdsForItem(S.objects.get(S.selected));
  }

  function selectedNet() {
    const candidates = netCandidates();
    if (!candidates.length) return null;
    if (!runtime.activeNetId || !candidates.includes(runtime.activeNetId)) {
      runtime.activeNetId = candidates[0];
      runtime.endpointCursor = -1;
    }
    return netById(runtime.activeNetId);
  }

  function netEndpoints(net) {
    const S = state();
    if (!S || !net) return { source: null, targets: [] };
    const endpoint = (terminalId, objectId) => {
      const terminal = S.objects.get(terminalId);
      const resolvedId = terminalOwnerId(terminalId, objectId);
      return S.objects.get(resolvedId) || terminal || null;
    };
    return {
      source: endpoint(net.source_terminal_id, net.source_object_id),
      targets: (net.target_terminal_ids || []).map((terminalId, index) => (
        endpoint(terminalId, net.target_object_ids?.[index])
      )).filter(Boolean),
    };
  }

  function selectNet(id) {
    const net = netById(id);
    if (!net) return false;
    runtime.activeNetId = id;
    runtime.endpointCursor = -1;
    const branchId = net.branch_ids?.[0];
    if (branchId) editor()?.select?.(branchId, true);
    else renderWorkflowPanels();
    return true;
  }

  function cycleNetEndpoint(net) {
    if (!net) return false;
    const endpoints = netEndpoints(net);
    const ids = unique([
      endpoints.source?.id,
      ...endpoints.targets.map((item) => item.id),
    ]);
    if (!ids.length) return false;
    runtime.endpointCursor = (runtime.endpointCursor + 1) % ids.length;
    runtime.activeNetId = net.id;
    editor()?.select?.(ids[runtime.endpointCursor], true);
    return true;
  }

  function focusNet(net) {
    const E = editor();
    const S = state();
    if (!E || !S || !net) return false;
    const wires = (net.branch_ids || [])
      .map((id) => S.wires.get(id))
      .filter(Boolean);
    const endpoints = netEndpoints(net);
    const objects = [endpoints.source, ...endpoints.targets].filter(Boolean);
    const boxes = objects.map((item) => (
      E.effectiveBounds?.(item) || E.getBounds?.(item)
    )).filter(Boolean);
    const points = wires.flatMap((wire) => wire.route_points || []);
    if (!boxes.length && !points.length) return false;
    const xs = [
      ...boxes.flatMap((box) => [finite(box.x), finite(box.x) + finite(box.width)]),
      ...points.map((point) => finite(point.x)),
    ];
    const ys = [
      ...boxes.flatMap((box) => [finite(box.y), finite(box.y) + finite(box.height)]),
      ...points.map((point) => finite(point.y)),
    ];
    const left = Math.min(...xs) - 48;
    const top = Math.min(...ys) - 42;
    const right = Math.max(...xs) + 48;
    const bottom = Math.max(...ys) + 42;
    const viewport = S.el.modelGraphViewport.getBoundingClientRect();
    const scale = Math.max(0.55, Math.min(
      1.4,
      (viewport.width - 40) / Math.max(80, right - left),
      (viewport.height - 40) / Math.max(80, bottom - top),
    ));
    const width = viewport.width / scale;
    const height = viewport.height / scale;
    const box = {
      x: (left + right) / 2 - width / 2,
      y: (top + bottom) / 2 - height / 2,
      width,
      height,
    };
    if (globalThis.VICanvasDensity?.applyBox) {
      globalThis.VICanvasDensity.applyBox(box, 'focus', { remember: true });
    } else {
      restoreView(box, 'focus');
    }
    return true;
  }

  function typeLabel(value) {
    return TYPE_LABELS[value] || value || TYPE_LABELS.unknown;
  }

  function createSection(id, className) {
    const section = document.createElement('section');
    section.id = id;
    section.className = className;
    section.hidden = true;
    return section;
  }

  function ensureWorkflowPanels() {
    const inspector = document.querySelector('#model-inspector');
    if (!inspector) return false;
    const anchor = document.querySelector('#vi-type-definition-section')
      || document.querySelector('#vi-geometry-editor')
      || inspector.firstChild;

    if (!document.querySelector('#vi-structure-frame-workflow')) {
      const section = createSection(
        'vi-structure-frame-workflow',
        'vi-workflow-section vi-structure-frame-workflow',
      );
      section.innerHTML = `
        <header>
          <span><strong>Structureフレーム</strong><small id="vi-frame-structure-name">—</small></span>
          <em>閲覧のみ</em>
        </header>
        <div class="vi-frame-workflow-controls">
          <button id="vi-frame-previous" type="button" aria-label="前のフレーム">‹</button>
          <select id="vi-frame-select" aria-label="表示中フレーム"></select>
          <button id="vi-frame-next" type="button" aria-label="次のフレーム">›</button>
        </div>
        <small id="vi-frame-workflow-note" class="vi-workflow-note">VIファイルの表示フレームは変更しません。</small>`;
      inspector.insertBefore(section, anchor);
      section.querySelector('#vi-frame-select').addEventListener('change', (event) => {
        const structureId = event.currentTarget.dataset.structureId;
        if (structureId) switchFrame(structureId, event.currentTarget.value);
      });
      section.querySelector('#vi-frame-previous').addEventListener('click', () => {
        const select = section.querySelector('#vi-frame-select');
        if (select?.dataset.structureId) {
          switchFrame(select.dataset.structureId, integer(select.value) - 1);
        }
      });
      section.querySelector('#vi-frame-next').addEventListener('click', () => {
        const select = section.querySelector('#vi-frame-select');
        if (select?.dataset.structureId) {
          switchFrame(select.dataset.structureId, integer(select.value) + 1);
        }
      });
    }

    if (!document.querySelector('#vi-net-workflow')) {
      const section = createSection(
        'vi-net-workflow',
        'vi-workflow-section vi-net-workflow',
      );
      section.innerHTML = `
        <header>
          <span><strong>配線ネット</strong><small id="vi-net-name">—</small></span>
          <span id="vi-net-type" class="vi-net-type">型未判定</span>
        </header>
        <label id="vi-net-select-row" class="vi-net-select-row">接続ネット<select id="vi-net-select"></select></label>
        <dl class="vi-net-facts">
          <div><dt>送信元</dt><dd id="vi-net-source">—</dd></div>
          <div><dt>接続先</dt><dd id="vi-net-target-count">0</dd></div>
          <div><dt>分岐</dt><dd id="vi-net-branch-count">0</dd></div>
        </dl>
        <div class="vi-net-actions">
          <button id="vi-net-focus" type="button">ネット全体</button>
          <button id="vi-net-next-endpoint" type="button">次の端点</button>
          <button id="vi-net-open-type" type="button" hidden>タイプ定義</button>
        </div>
        <div id="vi-net-endpoints" class="vi-net-endpoints"></div>
        <details class="vi-net-branches">
          <summary>配線レコード <span id="vi-net-wire-count">0</span></summary>
          <div id="vi-net-branch-list"></div>
        </details>`;
      inspector.insertBefore(section, anchor);
      section.querySelector('#vi-net-select').addEventListener('change', (event) => {
        selectNet(event.currentTarget.value);
      });
      section.querySelector('#vi-net-focus').addEventListener('click', () => {
        focusNet(selectedNet());
      });
      section.querySelector('#vi-net-next-endpoint').addEventListener('click', () => {
        cycleNetEndpoint(selectedNet());
      });
      section.querySelector('#vi-net-open-type').addEventListener('click', () => {
        const id = selectedNet()?.type_definition_id;
        if (id) globalThis.VITypeDefinitions?.open?.(id);
      });
    }
    return true;
  }

  function renderFramePanel() {
    const section = document.querySelector('#vi-structure-frame-workflow');
    if (!section) return;
    const structure = selectedStructure();
    const frames = framesFor(structure);
    section.hidden = !structure
      || frames.length < 2
      || state()?.surface !== 'block-diagram';
    if (section.hidden) return;

    const index = currentFrameIndex(structure);
    const select = section.querySelector('#vi-frame-select');
    select.dataset.structureId = structure.id;
    select.replaceChildren(...frames.map((frame, frameIndex) => {
      const option = document.createElement('option');
      option.value = String(frameIndex);
      option.textContent = `${frameIndex + 1}/${frames.length} · ${frameLabel(frame, frameIndex)} · ${(frame.object_ids || []).length}要素`;
      return option;
    }));
    select.value = String(index);
    section.querySelector('#vi-frame-previous').disabled = index <= 0;
    section.querySelector('#vi-frame-next').disabled = index >= frames.length - 1;
    section.querySelector('#vi-frame-structure-name').textContent = structure.name || 'Structure';
    const hiddenCount = frames.reduce(
      (total, frame, frameIndex) => total + (
        frameIndex === index ? 0 : (frame.object_ids || []).length
      ),
      0,
    );
    section.querySelector('#vi-frame-workflow-note').textContent = (
      `${structure.active_frame_label}を表示 · 他フレーム ${hiddenCount}要素 · 選択と表示位置をフレーム別に記憶 · VIには未保存`
    );
  }

  function netName(net) {
    const endpoints = netEndpoints(net);
    const source = endpoints.source?.name || '未解決';
    const target = endpoints.targets[0]?.name || '未解決';
    const rest = Math.max(0, endpoints.targets.length - 1);
    return `${source} → ${target}${rest ? ` ほか${rest}` : ''}`;
  }

  function endpointButton(item, role, net) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `vi-net-endpoint is-${role}`;
    button.textContent = `${role === 'source' ? '送信元' : '接続先'} · ${item?.name || '未解決端点'}`;
    button.disabled = !item?.id;
    button.addEventListener('click', () => {
      runtime.activeNetId = net.id;
      if (item?.id) editor()?.select?.(item.id, true);
    });
    return button;
  }

  function renderNetPanel() {
    const section = document.querySelector('#vi-net-workflow');
    if (!section) return;
    const S = state();
    const candidates = netCandidates();
    const net = selectedNet();
    section.hidden = !net || S?.surface !== 'block-diagram';
    if (section.hidden) return;

    const select = section.querySelector('#vi-net-select');
    select.replaceChildren(...candidates.map((id) => {
      const option = document.createElement('option');
      option.value = id;
      option.textContent = netName(netById(id));
      return option;
    }));
    select.value = net.id;
    section.querySelector('#vi-net-select-row').hidden = candidates.length < 2;

    const endpoints = netEndpoints(net);
    section.querySelector('#vi-net-name').textContent = netName(net);
    section.querySelector('#vi-net-type').textContent = typeLabel(net.data_type);
    section.querySelector('#vi-net-type').dataset.type = net.data_type || 'unknown';
    section.querySelector('#vi-net-source').textContent = endpoints.source?.name || '未解決';
    section.querySelector('#vi-net-target-count').textContent = String(endpoints.targets.length);
    section.querySelector('#vi-net-branch-count').textContent = String(net.branch_count || 0);
    section.querySelector('#vi-net-wire-count').textContent = String(net.wire_record_count || net.branch_ids?.length || 0);
    section.querySelector('#vi-net-open-type').hidden = !net.type_definition_id;
    section.querySelector('#vi-net-endpoints').replaceChildren(
      endpointButton(endpoints.source, 'source', net),
      ...endpoints.targets.map((target) => endpointButton(target, 'sink', net)),
    );
    section.querySelector('#vi-net-branch-list').replaceChildren(
      ...(net.branch_ids || []).map((id, index) => {
        const wire = S.wires.get(id);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'vi-net-branch';
        button.classList.toggle('is-selected', S.selected === id);
        button.textContent = `${index + 1}. ${editor()?.wireName?.(wire) || wire?.name || id}`;
        button.addEventListener('click', () => {
          runtime.activeNetId = net.id;
          editor()?.select?.(id, true);
        });
        return button;
      }),
    );
  }

  function renderWorkflowPanels() {
    if (!ensureWorkflowPanels()) return;
    renderFramePanel();
    renderNetPanel();
  }

  function updateActiveNet(id) {
    const S = state();
    if (!S) return;
    const wire = S.wires.get(id);
    if (wire?.net_id) {
      runtime.activeNetId = wire.net_id;
      runtime.endpointCursor = -1;
      return;
    }
    const candidates = netIdsForItem(S.objects.get(id));
    if (!candidates.includes(runtime.activeNetId)) {
      runtime.activeNetId = candidates[0] || null;
      runtime.endpointCursor = -1;
    }
  }

  function decorate() {
    const S = state();
    const root = S?.el?.modelGraphSvg;
    if (!S || !root) return;
    const net = selectedNet();
    const activeId = net?.id || null;
    root.classList.toggle('has-workflow-net', Boolean(activeId));
    root.querySelectorAll('[data-wire-id]').forEach((group) => {
      const wire = S.wires.get(group.dataset.wireId);
      const inNet = Boolean(activeId && wire?.net_id === activeId);
      group.dataset.netId = wire?.net_id || '';
      group.classList.toggle('is-workflow-net', inNet);
    });
    root.querySelectorAll('[data-object-id]').forEach((group) => {
      group.classList.remove('is-workflow-net-endpoint', 'is-workflow-net-source', 'is-workflow-net-sink');
    });
    if (net) {
      unique([net.source_terminal_id, net.source_object_id]).forEach((id) => {
        root.querySelector(`[data-object-id="${escapeSelector(id)}"]`)
          ?.classList.add('is-workflow-net-endpoint', 'is-workflow-net-source');
      });
      unique([
        ...(net.target_terminal_ids || []),
        ...(net.target_object_ids || []),
      ]).forEach((id) => {
        root.querySelector(`[data-object-id="${escapeSelector(id)}"]`)
          ?.classList.add('is-workflow-net-endpoint', 'is-workflow-net-sink');
      });
    }
    document.querySelectorAll('#vi-object-list [data-list-id]').forEach((button) => {
      const wire = S.wires.get(button.dataset.listId);
      const item = S.objects.get(button.dataset.listId);
      const inNet = Boolean(
        activeId
        && (wire?.net_id === activeId || netIdsForItem(item).includes(activeId)),
      );
      button.classList.toggle('is-workflow-net', inNet);
    });
    renderWorkflowPanels();
  }

  function scheduleDecoration() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      runtime.scheduled = false;
      decorate();
    });
  }

  function wrapEditor() {
    const E = editor();
    if (!E || runtime.originalInstall) return false;
    runtime.originalInstall = E.install;
    runtime.originalRenderAll = E.renderAll;
    runtime.originalRenderCanvas = E.renderCanvas;
    runtime.originalRenderInspector = E.renderInspector;
    runtime.originalRenderList = E.renderList;
    runtime.originalSelect = E.select;

    E.install = function installWithStructureWorkflow(vi) {
      const result = runtime.originalInstall.call(E, vi);
      captureModel(vi);
      scheduleDecoration();
      return result;
    };
    E.renderAll = function renderAllWithStructureWorkflow(...args) {
      const result = runtime.originalRenderAll.apply(E, args);
      renderWorkflowPanels();
      scheduleDecoration();
      return result;
    };
    E.renderCanvas = function renderCanvasWithStructureWorkflow(...args) {
      const result = runtime.originalRenderCanvas.apply(E, args);
      scheduleDecoration();
      return result;
    };
    E.renderInspector = function renderInspectorWithStructureWorkflow(...args) {
      const result = runtime.originalRenderInspector.apply(E, args);
      renderWorkflowPanels();
      return result;
    };
    E.renderList = function renderListWithStructureWorkflow(...args) {
      const result = runtime.originalRenderList.apply(E, args);
      scheduleDecoration();
      return result;
    };
    E.select = function selectWithStructureWorkflow(id, reveal = false) {
      updateActiveNet(id);
      const result = runtime.originalSelect.call(E, id, reveal);
      renderWorkflowPanels();
      scheduleDecoration();
      return result;
    };
    return true;
  }

  function install() {
    const E = editor();
    const root = document.querySelector('#model-graph-svg');
    const inspector = document.querySelector('#model-inspector');
    if (runtime.ready || !E || !root || !inspector) return false;
    runtime.ready = true;
    wrapEditor();
    ensureWorkflowPanels();
    if (state()?.vi) captureModel(state().vi);
    document.addEventListener('vi-structure-frame-changed', scheduleDecoration);
    root.addEventListener('click', scheduleDecoration);
    document.querySelector('#vi-object-list')?.addEventListener('click', scheduleDecoration);
    scheduleDecoration();
    globalThis.VIStructureWorkflow = {
      ready: true,
      runtime,
      captureModel,
      hiddenObjectIds,
      applyFrameVisibility,
      switchFrame,
      selectedStructure,
      selectedNet,
      selectNet,
      cycleNetEndpoint,
      focusNet,
      rebuildNets,
      netEndpoints,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 360) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIStructureWorkflow = { ready: false, runtime };
  waitForEditor();
})();
