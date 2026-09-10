'use strict';

(() => {
  const runtime = {
    ready: false,
    applying: false,
    queued: false,
    currentJobId: null,
    originalInstall: null,
    originalRenderAll: null,
    originalRenderCanvas: null,
    originalRenderInspector: null,
    originalRenderList: null,
    originalSelect: null,
    baseObjects: new Map(),
    allWires: new Map(),
    frameSelections: new Map(),
    activeNetId: null,
    endpointCursor: 0,
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

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function escapeSelector(value) {
    return globalThis.CSS?.escape
      ? CSS.escape(String(value))
      : String(value).replace(/["\\]/g, '\\$&');
  }

  function frameKey(structureId) {
    return `${runtime.currentJobId || 'unloaded'}::${structureId}`;
  }

  function framesFor(item) {
    return Array.isArray(item?.structure_frames) ? item.structure_frames : [];
  }

  function nativeSurface(item) {
    const base = runtime.baseObjects.get(item?.id);
    if (base?.surface) return base.surface;
    if (item?.native_surface) return item.native_surface;
    return item?.surface === 'block-diagram-inactive'
      ? 'block-diagram'
      : item?.surface;
  }

  function structures() {
    const S = state();
    return S
      ? [...S.objects.values()].filter((item) => framesFor(item).length > 1)
      : [];
  }

  function currentFrameIndex(item) {
    const frames = framesFor(item);
    if (!frames.length) return 0;
    const stored = runtime.frameSelections.get(frameKey(item.id));
    return Math.max(
      0,
      Math.min(
        frames.length - 1,
        stored == null ? integer(item.active_frame_index) : integer(stored),
      ),
    );
  }

  function allWireRecords(vi) {
    const records = [
      ...(vi?.wires || []),
      ...(vi?.inactive_structure_frame_wires || []),
      ...(vi?.all_structure_frame_wires || []),
    ];
    return new Map(
      records.filter((wire) => wire?.id).map((wire) => [wire.id, wire]),
    );
  }

  function captureModel(vi) {
    const S = state();
    if (!S || !vi) return;
    const nextJobId = String(S.job?.job_id || 'unloaded');
    if (runtime.currentJobId && runtime.currentJobId !== nextJobId) {
      runtime.frameSelections.clear();
      runtime.activeNetId = null;
      runtime.endpointCursor = 0;
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
        },
      ]),
    );
    runtime.allWires = allWireRecords(vi);
    structures().forEach((item) => {
      const key = frameKey(item.id);
      if (!runtime.frameSelections.has(key)) {
        runtime.frameSelections.set(key, currentFrameIndex(item));
      }
    });
    applyFrameVisibility(null, { render: false, announce: false });
  }

  function hiddenObjectIds() {
    const S = state();
    if (!S) return new Set();
    const hidden = new Set();
    const active = new Set();

    structures().forEach((structure) => {
      const frames = framesFor(structure);
      const selectedIndex = currentFrameIndex(structure);
      frames.forEach((frame, index) => {
        frame.is_active = index === selectedIndex;
        (frame.object_ids || []).forEach((id) => {
          if (index === selectedIndex) active.add(id);
          else hidden.add(id);
        });
      });
      structure.active_frame_index = selectedIndex;
      structure.active_frame_label = frames[selectedIndex]?.label || `Frame ${selectedIndex}`;
      structure.frame_view_mode = 'browser-only';
    });
    active.forEach((id) => hidden.delete(id));

    let changed = true;
    while (changed) {
      changed = false;
      S.objects.forEach((item) => {
        if (hidden.has(item.id) || nativeSurface(item) !== 'block-diagram') return;
        const base = runtime.baseObjects.get(item.id) || {};
        if (
          hidden.has(base.parentObjectId || item.parent_object_id)
          || hidden.has(base.ownerObjectId || item.owner_object_id)
        ) {
          hidden.add(item.id);
          changed = true;
        }
      });
    }
    return hidden;
  }

  function wireEndpointIds(wire) {
    return unique([
      wire.source_terminal_id,
      ...(wire.target_terminal_ids || []),
      wire.source_object_id,
      ...(wire.target_object_ids || []),
    ]);
  }

  function wireVisible(wire, hidden) {
    const S = state();
    if (!S || !wire?.source_terminal_id || !(wire.target_terminal_ids || []).length) {
      return false;
    }
    const terminals = [wire.source_terminal_id, ...wire.target_terminal_ids];
    return terminals.every((id) => {
      const item = S.objects.get(id);
      return item && !hidden.has(id) && nativeSurface(item) === 'block-diagram';
    }) && wireEndpointIds(wire).every((id) => !hidden.has(id));
  }

  function visibleObject(item, hidden) {
    return Boolean(item && !hidden.has(item.id));
  }

  function resetRelationships() {
    state()?.objects.forEach((item) => {
      item.terminal_ids = [];
      item.linked_terminal_ids = [];
      item.wire_ids = [];
      item.child_object_ids = [];
    });
  }

  function rebuildRelationships(visibleWires, hidden) {
    const S = state();
    if (!S) return;
    resetRelationships();

    S.objects.forEach((item) => {
      if (!visibleObject(item, hidden)) return;
      const base = runtime.baseObjects.get(item.id) || {};
      const parentId = base.parentObjectId || item.parent_object_id;
      const ownerId = base.ownerObjectId || item.owner_object_id;
      const linkedId = base.linkedObjectId || item.linked_object_id;
      if (parentId && visibleObject(S.objects.get(parentId), hidden)) {
        S.objects.get(parentId).child_object_ids.push(item.id);
      }
      if (item.category !== 'terminal') return;
      if (ownerId && visibleObject(S.objects.get(ownerId), hidden)) {
        S.objects.get(ownerId).terminal_ids.push(item.id);
      }
      if (linkedId && visibleObject(S.objects.get(linkedId), hidden)) {
        S.objects.get(linkedId).linked_terminal_ids.push(item.id);
      }
    });

    S.objects.forEach((item) => {
      item.terminal_ids.sort((first, second) => (
        integer(S.objects.get(first)?.port_index, 99999)
        - integer(S.objects.get(second)?.port_index, 99999)
      ));
      item.child_object_ids.sort((first, second) => {
        const firstBounds = S.objects.get(first)?.bounds || {};
        const secondBounds = S.objects.get(second)?.bounds || {};
        return number(firstBounds.y, 999999) - number(secondBounds.y, 999999)
          || number(firstBounds.x, 999999) - number(secondBounds.x, 999999);
      });
    });

    visibleWires.forEach((wire) => {
      const sourceTerminal = S.objects.get(wire.source_terminal_id);
      const targetTerminals = (wire.target_terminal_ids || [])
        .map((id) => S.objects.get(id))
        .filter(Boolean);
      if (!sourceTerminal || !targetTerminals.length) return;
      wire.source_object_id = sourceTerminal.linked_object_id
        || sourceTerminal.owner_object_id
        || wire.source_object_id
        || null;
      wire.target_object_ids = targetTerminals.map((terminal, index) => (
        terminal.linked_object_id
        || terminal.owner_object_id
        || wire.target_object_ids?.[index]
        || null
      ));
      wire.terminal_ids = [wire.source_terminal_id, ...wire.target_terminal_ids];
      wire.endpoint_object_ids = unique([
        wire.source_object_id,
        ...wire.target_object_ids,
      ]);
      wire.hidden_by_structure_frame = false;
      wire.terminal_ids.forEach((id) => {
        const terminal = S.objects.get(id);
        if (terminal && !terminal.wire_ids.includes(wire.id)) {
          terminal.wire_ids.push(wire.id);
        }
      });
      wire.endpoint_object_ids.forEach((id) => {
        const endpoint = S.objects.get(id);
        if (endpoint && !endpoint.wire_ids.includes(wire.id)) {
          endpoint.wire_ids.push(wire.id);
        }
      });
    });
  }

  function stableNetId(wire) {
    if (wire.net_id) return String(wire.net_id);
    if (wire.native_signal_uid) return `net:${wire.native_signal_uid}`;
    const native = String(wire.native_uid || '');
    const base = wire.branch_index || /_[1-9][0-9]*$/.test(native)
      ? native.replace(/_[1-9][0-9]*$/, '')
      : native;
    return `net:${base || wire.source_terminal_id}`;
  }

  function rebuildNets(visibleWires) {
    const S = state();
    const groups = new Map();
    visibleWires.forEach((wire) => {
      const id = stableNetId(wire);
      wire.net_id = id;
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(wire);
    });
    return [...groups.entries()].map(([id, branches]) => {
      const targets = new Map();
      branches.forEach((wire) => {
        wire.branch_count = branches.length;
        (wire.target_terminal_ids || []).forEach((terminalId, index) => {
          if (targets.has(terminalId)) return;
          const terminal = S?.objects.get(terminalId);
          targets.set(
            terminalId,
            terminal?.linked_object_id
              || terminal?.owner_object_id
              || wire.target_object_ids?.[index]
              || null,
          );
        });
      });
      const definitions = unique(branches.map((wire) => wire.type_definition_id));
      const types = unique(branches.map((wire) => wire.data_type).filter(
        (value) => value && value !== 'unknown',
      ));
      return {
        id,
        native_signal_uid: branches[0]?.native_signal_uid || branches[0]?.native_uid || '',
        source_terminal_id: branches[0]?.source_terminal_id || null,
        source_object_id: branches[0]?.source_object_id || null,
        target_terminal_ids: [...targets.keys()],
        target_object_ids: [...targets.values()],
        branch_ids: branches.map((wire) => wire.id),
        branch_count: branches.length,
        data_type: types.length === 1 ? types[0] : types.length ? 'conflict' : 'unknown',
        type_definition_id: definitions.length === 1 ? definitions[0] : null,
        type_definition_ids: definitions,
      };
    });
  }

  function updateSummary(hidden, wires, nets) {
    const S = state();
    if (!S) return;
    const visibleDiagram = [...S.objects.values()].filter(
      (item) => nativeSurface(item) === 'block-diagram' && !hidden.has(item.id),
    );
    const summary = S.vi.summary ||= {};
    summary.block_diagram_nodes = visibleDiagram.filter(
      (item) => item.category === 'node',
    ).length;
    summary.terminals = visibleDiagram.filter(
      (item) => item.category === 'terminal',
    ).length;
    summary.wires = wires.length;
    summary.resolved_wires = wires.filter((wire) => wire.resolved !== false).length;
    summary.wire_nets = nets.length;
    summary.hidden_structure_frame_objects = hidden.size;
    summary.hidden_structure_frame_wires = runtime.allWires.size - wires.length;
    summary.structure_frames = structures().reduce(
      (total, item) => total + framesFor(item).length,
      0,
    );
    S.vi.surfaces ||= {};
    S.vi.surfaces['block-diagram'] = visibleDiagram.map((item) => item.id);
    S.vi.hierarchy ||= {};
    S.vi.hierarchy.roots = visibleDiagram.filter(
      (item) => !item.parent_object_id,
    ).map((item) => item.id);
    S.vi.hierarchy.containers = visibleDiagram.filter(
      (item) => item.child_object_ids?.length,
    ).map((item) => item.id);
    S.vi.hierarchy.children_by_parent = Object.fromEntries(
      visibleDiagram.filter((item) => item.child_object_ids?.length)
        .map((item) => [item.id, [...item.child_object_ids]]),
    );
    S.vi.integrity ||= {};
    S.vi.integrity.structure_frame_runtime = {
      browser_only: true,
      hidden_object_count: hidden.size,
      hidden_wire_count: runtime.allWires.size - wires.length,
      visible_net_count: nets.length,
      selections: structures().map((item) => ({
        object_id: item.id,
        frame_index: currentFrameIndex(item),
        frame_label: item.active_frame_label,
      })),
    };
  }

  function preserveSelection(structureId, hidden, visibleWireIds) {
    const S = state();
    if (!S?.selected) return;
    const selectedItem = S.objects.get(S.selected);
    if (selectedItem && hidden.has(selectedItem.id)) {
      S.selected = structureId || null;
      return;
    }
    if (runtime.allWires.has(S.selected) && !visibleWireIds.has(S.selected)) {
      S.selected = structureId || null;
    }
  }

  function applyFrameVisibility(
    changedStructureId = null,
    { render = true, announce = true } = {},
  ) {
    const E = editor();
    const S = state();
    if (!E || !S?.vi || runtime.applying) return false;
    runtime.applying = true;
    const preservedBox = S.box ? { ...S.box } : null;
    const preservedMode = globalThis.VICanvasDensity?.runtime?.currentMode || 'manual';
    try {
      const hidden = hiddenObjectIds();
      S.objects.forEach((item) => {
        if (nativeSurface(item) !== 'block-diagram') return;
        const hiddenItem = hidden.has(item.id);
        item.native_surface = 'block-diagram';
        item.surface = hiddenItem ? 'block-diagram-inactive' : 'block-diagram';
        item.hidden_by_structure_frame = hiddenItem;
      });
      const visibleWires = [];
      const inactiveWires = [];
      runtime.allWires.forEach((wire) => {
        if (wireVisible(wire, hidden)) visibleWires.push(wire);
        else {
          wire.hidden_by_structure_frame = true;
          inactiveWires.push(wire);
        }
      });
      rebuildRelationships(visibleWires, hidden);
      const nets = rebuildNets(visibleWires);
      const visibleWireIds = new Set(visibleWires.map((wire) => wire.id));
      preserveSelection(changedStructureId, hidden, visibleWireIds);
      S.vi.wires = visibleWires;
      S.vi.inactive_structure_frame_wires = inactiveWires;
      S.vi.all_structure_frame_wires = [...runtime.allWires.values()];
      S.vi.nets = nets;
      S.wires = new Map(visibleWires.map((wire) => [wire.id, wire]));
      updateSummary(hidden, visibleWires, nets);
      if (runtime.activeNetId && !nets.some((net) => net.id === runtime.activeNetId)) {
        runtime.activeNetId = null;
        runtime.endpointCursor = 0;
      }
      if (render) {
        E.renderAll?.(false);
        requestAnimationFrame(() => {
          if (preservedBox && globalThis.VICanvasDensity?.applyBox) {
            globalThis.VICanvasDensity.applyBox(
              preservedBox,
              preservedMode,
              { remember: true },
            );
          }
          decorate();
        });
      }
      if (announce && changedStructureId) {
        const structure = S.objects.get(changedStructureId);
        globalThis.showToast?.(
          `${structure?.name || 'Structure'}: ${structure?.active_frame_label || 'Frame'} を表示しました（閲覧のみ）。`,
          'success',
        );
      }
      document.dispatchEvent(new CustomEvent('vi-structure-frame-changed', {
        detail: {
          structureId: changedStructureId,
          hiddenObjectCount: hidden.size,
          visibleWireCount: visibleWires.length,
          visibleNetCount: nets.length,
        },
      }));
      return true;
    } finally {
      runtime.applying = false;
      renderWorkflowInspector();
      queueDecoration();
    }
  }

  function switchFrame(structureId, frameIndex) {
    const structure = state()?.objects.get(structureId);
    const frames = framesFor(structure);
    if (!structure || !frames.length) return false;
    const index = Math.max(0, Math.min(frames.length - 1, integer(frameIndex)));
    runtime.frameSelections.set(frameKey(structure.id), index);
    return applyFrameVisibility(structure.id);
  }

  function structureAncestor(item) {
    const S = state();
    if (!S || !item) return null;
    if (framesFor(item).length > 1) return item;
    let parentId = runtime.baseObjects.get(item.id)?.parentObjectId
      || item.parent_object_id
      || item.owner_object_id;
    const seen = new Set();
    while (parentId && !seen.has(parentId)) {
      seen.add(parentId);
      const parent = S.objects.get(parentId);
      if (!parent) return null;
      if (framesFor(parent).length > 1) return parent;
      parentId = runtime.baseObjects.get(parent.id)?.parentObjectId
        || parent.parent_object_id
        || parent.owner_object_id;
    }
    return null;
  }

  function selectedStructure() {
    const S = state();
    if (!S?.selected) return null;
    const item = S.objects.get(S.selected);
    if (item) return structureAncestor(item);
    const wire = S.wires.get(S.selected);
    return wire
      ? wireEndpointIds(wire)
        .map((id) => structureAncestor(S.objects.get(id)))
        .find(Boolean) || null
      : null;
  }

  function netById(id) {
    return (state()?.vi?.nets || []).find((net) => net.id === id) || null;
  }

  function netIdsForItem(item) {
    const S = state();
    return S && item
      ? unique((item.wire_ids || []).map((id) => S.wires.get(id)?.net_id))
      : [];
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
      runtime.endpointCursor = 0;
    }
    return netById(runtime.activeNetId);
  }

  function endpointObject(terminalId, objectId) {
    const S = state();
    const terminal = S?.objects.get(terminalId);
    return S?.objects.get(
      terminal?.linked_object_id || terminal?.owner_object_id || objectId,
    ) || terminal || null;
  }

  function netEndpoints(net) {
    if (!net) return { source: null, targets: [] };
    return {
      source: endpointObject(net.source_terminal_id, net.source_object_id),
      targets: (net.target_terminal_ids || []).map((terminalId, index) => (
        endpointObject(terminalId, net.target_object_ids?.[index])
      )).filter(Boolean),
    };
  }

  function typeLabel(type) {
    return TYPE_LABELS[type] || type || TYPE_LABELS.unknown;
  }

  function createSection(id, className) {
    const section = document.createElement('section');
    section.id = id;
    section.className = className;
    section.hidden = true;
    return section;
  }

  function ensureInspectorSections() {
    const inspector = document.querySelector('#model-inspector');
    if (!inspector) return false;
    const geometry = document.querySelector('#vi-geometry-editor');
    if (!document.querySelector('#vi-structure-frame-section')) {
      const section = createSection(
        'vi-structure-frame-section',
        'vi-workflow-section vi-structure-frame-section',
      );
      section.innerHTML = `
        <header><span><strong>Structureフレーム</strong><small id="vi-structure-frame-structure">—</small></span><em>閲覧のみ</em></header>
        <div class="vi-frame-controls">
          <button id="vi-structure-frame-previous" type="button" aria-label="前のフレーム">‹</button>
          <select id="vi-structure-frame-select" aria-label="表示中フレーム"></select>
          <button id="vi-structure-frame-next" type="button" aria-label="次のフレーム">›</button>
        </div>
        <small id="vi-structure-frame-note" class="vi-workflow-note">VIファイルの表示フレームは変更しません。</small>`;
      inspector.insertBefore(section, geometry || inspector.firstChild);
      section.querySelector('#vi-structure-frame-select').addEventListener('change', (event) => {
        const structureId = event.currentTarget.dataset.structureId;
        if (structureId) switchFrame(structureId, event.currentTarget.value);
      });
      section.querySelector('#vi-structure-frame-previous').addEventListener('click', () => {
        const select = section.querySelector('#vi-structure-frame-select');
        if (select?.dataset.structureId) {
          switchFrame(select.dataset.structureId, integer(select.value) - 1);
        }
      });
      section.querySelector('#vi-structure-frame-next').addEventListener('click', () => {
        const select = section.querySelector('#vi-structure-frame-select');
        if (select?.dataset.structureId) {
          switchFrame(select.dataset.structureId, integer(select.value) + 1);
        }
      });
    }
    if (!document.querySelector('#vi-net-inspector-section')) {
      const section = createSection(
        'vi-net-inspector-section',
        'vi-workflow-section vi-net-inspector-section',
      );
      section.innerHTML = `
        <header><span><strong>配線ネット</strong><small id="vi-net-title">—</small></span><span id="vi-net-type" class="vi-net-type">型未判定</span></header>
        <label id="vi-net-select-row" class="vi-net-select-row">接続ネット<select id="vi-net-select"></select></label>
        <dl class="vi-net-facts">
          <div><dt>送信元</dt><dd id="vi-net-source-name">—</dd></div>
          <div><dt>接続先</dt><dd id="vi-net-target-count">0</dd></div>
          <div><dt>分岐</dt><dd id="vi-net-branch-count">0</dd></div>
        </dl>
        <div class="vi-net-actions"><button id="vi-net-focus" type="button">ネット全体</button><button id="vi-net-next-endpoint" type="button">次の端点</button></div>
        <div id="vi-net-endpoints" class="vi-net-endpoints"></div>
        <details class="vi-net-branches"><summary>配線分岐 <span id="vi-net-branch-summary">0</span></summary><div id="vi-net-branch-list"></div></details>`;
      inspector.insertBefore(section, geometry || inspector.firstChild);
      section.querySelector('#vi-net-select').addEventListener('change', (event) => {
        selectNet(event.currentTarget.value);
      });
      section.querySelector('#vi-net-focus').addEventListener('click', () => {
        focusNet(selectedNet());
      });
      section.querySelector('#vi-net-next-endpoint').addEventListener('click', () => {
        cycleNetEndpoint(selectedNet());
      });
    }
    return true;
  }

  function renderFramePanel() {
    const section = document.querySelector('#vi-structure-frame-section');
    if (!section) return;
    const structure = selectedStructure();
    const frames = framesFor(structure);
    section.hidden = !structure || frames.length < 2 || state()?.surface !== 'block-diagram';
    if (section.hidden) return;
    const index = currentFrameIndex(structure);
    const select = section.querySelector('#vi-structure-frame-select');
    select.dataset.structureId = structure.id;
    select.replaceChildren(...frames.map((frame, frameIndex) => {
      const option = document.createElement('option');
      option.value = String(frameIndex);
      option.textContent = `${frameIndex + 1}/${frames.length} · ${frame.label || `Frame ${frameIndex}`}`;
      return option;
    }));
    select.value = String(index);
    section.querySelector('#vi-structure-frame-previous').disabled = index === 0;
    section.querySelector('#vi-structure-frame-next').disabled = index === frames.length - 1;
    section.querySelector('#vi-structure-frame-structure').textContent = structure.name || 'Structure';
    const visible = frames[index]?.object_ids?.length || 0;
    const hidden = frames.reduce(
      (total, frame, frameIndex) => total + (
        frameIndex === index ? 0 : (frame.object_ids?.length || 0)
      ),
      0,
    );
    section.querySelector('#vi-structure-frame-note').textContent = (
      `${frames[index]?.label || `Frame ${index}`}を表示 · 直接要素 ${visible} · 他フレーム ${hidden}要素 · VIには未保存`
    );
  }

  function netDisplayName(net) {
    const endpoints = netEndpoints(net);
    const source = endpoints.source?.name || '未解決';
    const target = endpoints.targets[0]?.name || '未解決';
    const extra = Math.max(0, endpoints.targets.length - 1);
    return `${source} → ${target}${extra ? ` ほか${extra}` : ''}`;
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
    const section = document.querySelector('#vi-net-inspector-section');
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
      option.textContent = netDisplayName(netById(id));
      return option;
    }));
    select.value = net.id;
    section.querySelector('#vi-net-select-row').hidden = candidates.length < 2;
    const endpoints = netEndpoints(net);
    section.querySelector('#vi-net-title').textContent = netDisplayName(net);
    section.querySelector('#vi-net-type').textContent = typeLabel(net.data_type);
    section.querySelector('#vi-net-type').dataset.type = net.data_type || 'unknown';
    section.querySelector('#vi-net-source-name').textContent = endpoints.source?.name || '未解決';
    section.querySelector('#vi-net-target-count').textContent = String(endpoints.targets.length);
    section.querySelector('#vi-net-branch-count').textContent = String(net.branch_ids?.length || 0);
    section.querySelector('#vi-net-branch-summary').textContent = String(net.branch_ids?.length || 0);
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
        button.textContent = `${index + 1}. ${editor()?.wireName?.(wire) || wire?.name || id}`;
        button.classList.toggle('is-selected', S.selected === id);
        button.addEventListener('click', () => {
          runtime.activeNetId = net.id;
          editor()?.select?.(id, true);
        });
        return button;
      }),
    );
  }

  function renderWorkflowInspector() {
    if (!ensureInspectorSections()) return;
    renderFramePanel();
    renderNetPanel();
  }

  function selectNet(id) {
    const net = netById(id);
    if (!net) return false;
    runtime.activeNetId = id;
    runtime.endpointCursor = 0;
    if (net.branch_ids?.[0]) editor()?.select?.(net.branch_ids[0], true);
    else renderWorkflowInspector();
    return true;
  }

  function cycleNetEndpoint(net) {
    if (!net) return false;
    const endpoints = netEndpoints(net);
    const records = unique([
      endpoints.source?.id,
      ...endpoints.targets.map((item) => item.id),
    ]).map((id) => state()?.objects.get(id)).filter(Boolean);
    if (!records.length) return false;
    runtime.endpointCursor = (runtime.endpointCursor + 1) % records.length;
    runtime.activeNetId = net.id;
    editor()?.select?.(records[runtime.endpointCursor].id, true);
    return true;
  }

  function focusNet(net) {
    const E = editor();
    const S = state();
    if (!net || !E || !S) return false;
    const wires = (net.branch_ids || []).map((id) => S.wires.get(id)).filter(Boolean);
    const endpoints = netEndpoints(net);
    const objects = [endpoints.source, ...endpoints.targets].filter(Boolean);
    const boxes = objects.map(
      (item) => E.effectiveBounds?.(item) || E.getBounds?.(item),
    ).filter(Boolean);
    const points = wires.flatMap((wire) => wire.route_points || []);
    if (!boxes.length && !points.length) return false;
    const xs = [
      ...boxes.flatMap((box) => [number(box.x), number(box.x) + number(box.width)]),
      ...points.map((point) => number(point.x)),
    ];
    const ys = [
      ...boxes.flatMap((box) => [number(box.y), number(box.y) + number(box.height)]),
      ...points.map((point) => number(point.y)),
    ];
    const left = Math.min(...xs) - 48;
    const top = Math.min(...ys) - 42;
    const right = Math.max(...xs) + 48;
    const bottom = Math.max(...ys) + 42;
    const viewport = S.el.modelGraphViewport.getBoundingClientRect();
    const scale = Math.max(0.55, Math.min(
      1.28,
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
      S.box = box;
      S.el.modelGraphSvg.setAttribute(
        'viewBox',
        `${box.x} ${box.y} ${box.width} ${box.height}`,
      );
    }
    return true;
  }

  function decorateStructureFrames() {
    const root = state()?.el?.modelGraphSvg;
    if (!root) return;
    structures().forEach((item) => {
      const group = root.querySelector(
        `[data-object-id="${escapeSelector(item.id)}"]`,
      );
      if (!group) return;
      const label = item.active_frame_label || `Frame ${currentFrameIndex(item)}`;
      group.dataset.activeFrameIndex = String(currentFrameIndex(item));
      group.dataset.activeFrameLabel = label;
      group.setAttribute('aria-description', `表示中フレーム: ${label}`);
      const title = group.querySelector('.vi-structure-title');
      const visibleTitle = `${item.name || 'Structure'} · ${label}`;
      if (title && title.textContent !== visibleTitle) title.textContent = visibleTitle;
      // Keep the native tooltip deterministic; never append on each mutation.
      const tooltip = group.querySelector(':scope > title');
      if (tooltip) {
        const tooltipText = `${item.name || 'Structure'}\n表示中フレーム: ${label}`;
        if (tooltip.textContent !== tooltipText) tooltip.textContent = tooltipText;
      }
    });
  }

  function decorateNet() {
    const S = state();
    const root = S?.el?.modelGraphSvg;
    if (!S || !root) return;
    const net = selectedNet();
    const activeId = net?.id || null;
    root.classList.toggle('has-net-workflow-selection', Boolean(activeId));
    root.querySelectorAll('[data-wire-id]').forEach((group) => {
      const wire = S.wires.get(group.dataset.wireId);
      group.classList.toggle(
        'is-net-selected',
        Boolean(activeId && wire?.net_id === activeId),
      );
      group.dataset.netId = wire?.net_id || '';
    });
    root.querySelectorAll('[data-object-id]').forEach((group) => {
      group.classList.remove('is-net-endpoint', 'is-net-source', 'is-net-sink');
    });
    if (net) {
      unique([net.source_terminal_id, net.source_object_id]).forEach((id) => {
        root.querySelector(`[data-object-id="${escapeSelector(id)}"]`)
          ?.classList.add('is-net-endpoint', 'is-net-source');
      });
      unique([
        ...(net.target_terminal_ids || []),
        ...(net.target_object_ids || []),
      ]).forEach((id) => {
        root.querySelector(`[data-object-id="${escapeSelector(id)}"]`)
          ?.classList.add('is-net-endpoint', 'is-net-sink');
      });
    }
    document.querySelectorAll('#vi-object-list [data-list-id]').forEach((button) => {
      const wire = S.wires.get(button.dataset.listId);
      const item = S.objects.get(button.dataset.listId);
      const inNet = wire?.net_id === activeId
        || Boolean(item && netIdsForItem(item).includes(activeId));
      button.classList.toggle('is-net-selected', inNet);
    });
  }

  function decorate() {
    decorateStructureFrames();
    decorateNet();
    renderWorkflowInspector();
  }

  function queueDecoration() {
    if (runtime.queued) return;
    runtime.queued = true;
    requestAnimationFrame(() => {
      runtime.queued = false;
      decorate();
    });
  }

  function updateActiveNetForSelection(id) {
    const S = state();
    const wire = S?.wires.get(id);
    if (wire?.net_id) {
      runtime.activeNetId = wire.net_id;
      runtime.endpointCursor = 0;
      return;
    }
    const candidates = netIdsForItem(S?.objects.get(id));
    if (!candidates.includes(runtime.activeNetId)) {
      runtime.activeNetId = candidates[0] || null;
      runtime.endpointCursor = 0;
    }
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

    if (typeof runtime.originalInstall === 'function') {
      E.install = function installWithStructureFrames(vi) {
        const result = runtime.originalInstall.call(E, vi);
        captureModel(vi);
        queueDecoration();
        return result;
      };
    }
    if (typeof runtime.originalRenderAll === 'function') {
      E.renderAll = function renderAllWithStructureNet(...args) {
        const result = runtime.originalRenderAll.apply(E, args);
        renderWorkflowInspector();
        queueDecoration();
        return result;
      };
    }
    if (typeof runtime.originalRenderCanvas === 'function') {
      E.renderCanvas = function renderCanvasWithStructureNet(...args) {
        const result = runtime.originalRenderCanvas.apply(E, args);
        queueDecoration();
        return result;
      };
    }
    if (typeof runtime.originalRenderInspector === 'function') {
      E.renderInspector = function renderInspectorWithStructureNet(...args) {
        const result = runtime.originalRenderInspector.apply(E, args);
        renderWorkflowInspector();
        queueDecoration();
        return result;
      };
    }
    if (typeof runtime.originalRenderList === 'function') {
      E.renderList = function renderListWithStructureNet(...args) {
        const result = runtime.originalRenderList.apply(E, args);
        queueDecoration();
        return result;
      };
    }
    if (typeof runtime.originalSelect === 'function') {
      E.select = function selectWithStructureNet(id, reveal = false) {
        updateActiveNetForSelection(id);
        const result = runtime.originalSelect.call(E, id, reveal);
        renderWorkflowInspector();
        queueDecoration();
        return result;
      };
    }
    return true;
  }

  function install() {
    const E = editor();
    const root = document.querySelector('#model-graph-svg');
    const inspector = document.querySelector('#model-inspector');
    if (runtime.ready || !E || !root || !inspector) return false;
    runtime.ready = true;
    wrapEditor();
    ensureInspectorSections();
    // Observe only the SVG. The inspector is rendered by the wrappers above;
    // observing our own replaceChildren calls would create a perpetual RAF loop.
    new MutationObserver(queueDecoration).observe(root, {
      childList: true,
      subtree: true,
    });
    root.addEventListener('click', queueDecoration);
    document.querySelector('#vi-object-list')?.addEventListener('click', queueDecoration);
    if (state()?.vi) captureModel(state().vi);
    queueDecoration();
    globalThis.VIStructureNetWorkflow = {
      ready: true,
      runtime,
      captureModel,
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

  globalThis.VIStructureNetWorkflow = { ready: false, runtime };
  waitForEditor();
})();
