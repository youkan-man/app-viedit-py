'use strict';

(() => {
  const E = globalThis.VISemanticEditor;
  const { S, SURFACES, number, label, html } = E;

  function clamp(value, minimum = 0, maximum = 1) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function fallbackSemantic(graph) {
    // A generic XML relationship graph is useful for RAW diagnostics, but it
    // does not identify LabVIEW dataflow nodes or signal direction. Showing it
    // as a block diagram fabricated components and wires. Preserve only the
    // front-panel objects that have an explicit front-panel layer, and leave
    // the block diagram empty until the authoritative semantic parser returns.
    const objects = (graph.models || [])
      .filter((model) => (
        model.layer === 'front-panel'
        && !['wire', 'container', 'decoration'].includes(model.kind)
      ))
      .map((model) => {
        const sourcePosition = model.position;
        const indicator = model.kind === 'indicator';
        return {
          id: model.id,
          component_id: model.id,
          surface: 'front-panel',
          kind: model.kind === 'control' ? 'control' : model.kind,
          category: indicator ? 'indicator' : 'control',
          name: model.name || model.class_name || model.kind,
          symbol: indicator ? 'OUT' : 'IN',
          class_name: model.class_name || '',
          uid: model.uid || '',
          bounds: sourcePosition ? {
            ...sourcePosition,
            x: number(sourcePosition.x),
            y: number(sourcePosition.y),
            width: Math.max(8, number(sourcePosition.width, 40)),
            height: Math.max(8, number(sourcePosition.height, 24)),
            source_property_id: sourcePosition.source_property_id,
          } : null,
          positioned: Boolean(sourcePosition),
          movable: Boolean(sourcePosition?.source_property_id),
          resizable: Boolean(sourcePosition?.source_property_id),
          terminal_ids: [],
          linked_terminal_ids: [],
          wire_ids: [],
          semantic_source: 'generic-front-panel-fallback',
          parser_confidence: 'front-panel-only',
          source: { file: model.file || '', xml_path: model.xml_path || '' },
        };
      });
    const omittedBlockObjects = (graph.models || []).filter(
      (model) => model.layer === 'block-diagram',
    ).length;
    const omittedEdges = (graph.connections || []).length;
    return {
      version: 0,
      objects,
      wires: [],
      nets: [],
      summary: {
        controls: objects.filter((item) => item.category === 'control').length,
        indicators: objects.filter((item) => item.category === 'indicator').length,
        block_diagram_nodes: 0,
        wires: 0,
        wire_nets: 0,
        resolved_wires: 0,
      },
      warnings: omittedBlockObjects || omittedEdges
        ? ['意味解析結果がないため、誤ったブロックダイアグラムは表示していません。RAW参照グラフは解析元欄で確認できます。']
        : [],
      parser: {
        name: 'component-model',
        mode: 'front-panel-only',
        generic_graph_used_for_block_diagram: false,
      },
      debug: {
        unresolved_references: graph.unresolved?.length || 0,
        omitted_generic_block_objects: omittedBlockObjects,
        omitted_generic_edges: omittedEdges,
      },
    };
  }

  function install(vi) {
    S.vi = vi;
    S.objects = new Map((vi.objects || []).map((item) => [item.id, item]));
    S.wires = new Map((vi.wires || []).map((wire) => [wire.id, wire]));
    S.local.clear();
    S.dirty.clear();
    S.selected = null;
    S.box = null;
    S.fitBox = null;
  }

  function fallbackBounds(item, index = 0) {
    const key = `fallback:${item.surface}:${item.id}`;
    if (!S.local.has(key)) {
      S.local.set(key, {
        x: 40 + (index % 4) * 140,
        y: 40 + Math.floor(index / 4) * 88,
        width: item.category === 'terminal' ? 10 : 100,
        height: item.category === 'terminal' ? 10 : 42,
        fallback: true,
      });
    }
    return S.local.get(key);
  }

  function relativeTerminalBounds(item, index) {
    const owner = S.objects.get(item.bounds?.relative_to_object_id);
    const ownerBounds = owner ? getBounds(owner, index) : null;
    if (!owner || !ownerBounds) return null;

    const originalOwner = owner.bounds || ownerBounds;
    const originalWidth = Math.max(1, number(originalOwner.width, ownerBounds.width));
    const originalHeight = Math.max(1, number(originalOwner.height, ownerBounds.height));
    const rawX = number(
      item.bounds.raw_x,
      number(item.bounds.x) - number(originalOwner.x),
    );
    const rawY = number(
      item.bounds.raw_y,
      number(item.bounds.y) - number(originalOwner.y),
    );

    let anchorX = clamp(rawX / originalWidth);
    let anchorY = clamp(rawY / originalHeight);
    if (item.bounds.anchor_x != null) anchorX = clamp(number(item.bounds.anchor_x));
    if (item.bounds.anchor_y != null) anchorY = clamp(number(item.bounds.anchor_y));
    if (item.direction === 'source' && rawX >= originalWidth * 0.6) anchorX = 1;
    if (item.direction === 'sink' && rawX <= originalWidth * 0.4) anchorX = 0;

    return {
      x: ownerBounds.x + rawX + (ownerBounds.width - originalWidth) * anchorX,
      y: ownerBounds.y + rawY + (ownerBounds.height - originalHeight) * anchorY,
      width: Math.max(4, number(item.bounds.width, 8)),
      height: Math.max(4, number(item.bounds.height, 8)),
      relative_to_object_id: owner.id,
      anchor_x: anchorX,
      anchor_y: anchorY,
    };
  }

  function getBounds(item, index = 0) {
    if (!item) return null;
    if (S.local.has(item.id)) return S.local.get(item.id);
    if (item.category === 'terminal' && item.bounds?.relative_to_object_id) {
      const relative = relativeTerminalBounds(item, index);
      if (relative) return relative;
    }
    if (item.bounds) {
      return {
        x: number(item.bounds.x),
        y: number(item.bounds.y),
        width: Math.max(4, number(item.bounds.width, 40)),
        height: Math.max(4, number(item.bounds.height, 24)),
      };
    }
    return fallbackBounds(item, index);
  }

  function surfaceObjects() {
    return (S.vi?.objects || []).filter((item) => (
      item.surface === S.surface && (S.showTerminals || item.category !== 'terminal')
    ));
  }

  function visible(item) {
    const query = S.el.modelGraphQuery.value.trim().toLowerCase();
    const kind = S.el.modelGraphKind.value;
    const searchable = `${item.name || ''} ${item.kind || ''} ${item.class_name || ''}`.toLowerCase();
    return (!kind || item.kind === kind || item.category === kind)
      && (!query || searchable.includes(query));
  }

  function typeClass(item) {
    if (item.category === 'control') return 'is-control';
    if (item.category === 'indicator') return 'is-indicator';
    if (item.category === 'terminal') return `is-terminal is-${item.direction || 'unknown'}`;
    return `is-node is-${item.kind || 'node'}`;
  }

  function setSurface(surface, fit = true) {
    if (!SURFACES[surface]) return;
    S.surface = surface;
    S.selected = null;
    S.el.modelGraphLayer.value = surface;
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      const active = button.dataset.viSurface === surface;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    });
    S.el.viSurfaceTitle.textContent = SURFACES[surface];
    S.el.viSurfaceSubtitle.textContent = surface === 'front-panel'
      ? '操作部品の位置とサイズ'
      : 'ノード、端子、配線の接続関係';
    S.el.modelGraphViewport.classList.toggle('is-front-panel', surface === 'front-panel');
    E.renderAll(fit);
  }

  function renderSummary() {
    const summary = S.vi?.summary || {};
    const wireCount = number(summary.wires);
    const netCount = number(summary.wire_nets, wireCount);
    const resolvedCount = number(summary.resolved_wires);
    S.el.viSummaryControls.textContent = number(summary.controls || summary.numeric_controls).toLocaleString('ja-JP');
    S.el.viSummaryIndicators.textContent = number(summary.indicators || summary.numeric_indicators).toLocaleString('ja-JP');
    S.el.viSummaryNodes.textContent = number(summary.block_diagram_nodes).toLocaleString('ja-JP');
    S.el.viSummaryWires.textContent = wireCount.toLocaleString('ja-JP');
    S.el.viSummaryWireNote.textContent = `${resolvedCount.toLocaleString('ja-JP')}枝 · ${netCount.toLocaleString('ja-JP')}ネット`;
    document.querySelector('#model-graph-model-count').textContent = (S.vi?.objects || []).length;
    document.querySelector('#model-graph-edge-count').textContent = wireCount;
    document.querySelector('#model-graph-net-count').textContent = netCount;
  }

  function renderDiagnostics() {
    const warnings = S.vi?.warnings || [];
    S.el.viDiagnostics.hidden = !warnings.length;
    S.el.viDiagnostics.textContent = warnings.join(' ');
  }

  function renderDebug() {
    const graph = S.payload?.graph || {};
    const documents = graph.documents || [];
    const unresolved = graph.unresolved || [];
    S.el.modelDocumentCount.textContent = documents.length;
    S.el.modelUnresolvedCount.textContent = unresolved.length;
    document.querySelector('#model-graph-document-count').textContent = documents.length;
    document.querySelector('#model-graph-unresolved-note').textContent = `${unresolved.length} unresolved`;
    S.el.modelDocumentList.replaceChildren(...(documents.length ? documents.map((documentModel) => {
      const row = html('div', 'vi-debug-row');
      row.append(
        html('strong', '', documentModel.path),
        html('small', '', `${documentModel.layer || 'metadata'} · ${documentModel.model_count || 0} objects`),
      );
      return row;
    }) : [html('div', 'vi-debug-empty', '解析ファイルなし')]));
    S.el.modelUnresolvedList.replaceChildren(...(unresolved.length ? unresolved.slice(0, 50).map((edge) => {
      const row = html('div', 'vi-debug-row');
      row.append(
        html('strong', '', edge.label || edge.type || '参照'),
        html('small', '', `${edge.source || 'unknown'} → ${edge.target_key || 'unknown'}`),
      );
      return row;
    }) : [html('div', 'vi-debug-empty', '未解決参照なし')]));
  }

  function renderKinds() {
    const current = S.el.modelGraphKind.value;
    const kinds = [...new Set(
      (S.vi?.objects || [])
        .filter((item) => item.surface === S.surface && item.category !== 'terminal')
        .map((item) => item.kind),
    )].sort();
    S.el.modelGraphKind.replaceChildren(
      new Option('すべての種類', ''),
      ...kinds.map((kind) => new Option(label({ kind }), kind)),
    );
    if (kinds.includes(current)) S.el.modelGraphKind.value = current;
  }

  function select(id, reveal = false) {
    if (!S.objects.has(id) && !S.wires.has(id)) return;
    const item = S.objects.get(id);
    if (reveal && item?.surface !== S.surface) setSurface(item.surface, false);
    if (reveal && S.wires.has(id) && S.surface !== 'block-diagram') setSurface('block-diagram', false);
    S.selected = id;
    renderList();
    E.renderCanvas();
    E.renderInspector();
    if (reveal) document.querySelector(`[data-list-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  function wireName(wire) {
    if (!wire) return '配線';
    const source = S.objects.get(wire.source_object_id);
    const targets = (wire.target_object_ids || []).map((id) => S.objects.get(id)).filter(Boolean);
    return source && targets.length
      ? `${source.name} → ${targets.map((item) => item.name).join(', ')}`
      : wire.name || '配線';
  }

  function renderList() {
    const records = [
      ...surfaceObjects().filter(visible),
      ...(S.surface === 'block-diagram' ? [...S.wires.values()].filter(visible) : []),
    ];
    S.el.viObjectCount.textContent = records.length;
    const groups = [
      ['入力', records.filter((item) => item.category === 'control')],
      ['表示', records.filter((item) => item.category === 'indicator')],
      ['処理', records.filter((item) => item.category === 'node')],
      ['端子', records.filter((item) => item.category === 'terminal')],
      ['配線', records.filter((item) => S.wires.has(item.id))],
    ];
    const fragment = document.createDocumentFragment();
    groups.forEach(([title, items]) => {
      if (!items.length) return;
      const heading = html('div', 'vi-list-group');
      heading.append(html('span', '', title), html('small', '', items.length));
      fragment.append(heading);
      items.forEach((item) => {
        const isWire = S.wires.has(item.id);
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.listId = item.id;
        button.role = 'option';
        button.setAttribute('aria-selected', String(S.selected === item.id));
        button.className = `vi-object-list-item ${isWire ? 'is-wire' : typeClass(item)}${S.selected === item.id ? ' is-selected' : ''}`;
        const copy = html('span', 'vi-list-copy');
        copy.append(
          html('strong', '', isWire ? wireName(item) : item.name),
          html('small', '', isWire
            ? (item.resolved ? '接続確定' : '方向未確定')
            : `${label(item)}${item.positioned ? '' : ' · 位置なし'}`),
        );
        button.append(
          html('i', 'vi-list-glyph', isWire ? '⌁' : item.symbol || (item.category === 'terminal' ? '●' : '◇')),
          copy,
        );
        button.addEventListener('click', () => select(item.id));
        fragment.append(button);
      });
    });
    if (!fragment.childNodes.length) {
      fragment.append(html('div', 'vi-list-empty', '条件に一致するオブジェクトはありません。'));
    }
    S.el.viObjectList.replaceChildren(fragment);
  }

  Object.assign(E, {
    fallbackSemantic,
    install,
    getBounds,
    surfaceObjects,
    visible,
    typeClass,
    setSurface,
    renderSummary,
    renderDiagnostics,
    renderDebug,
    renderKinds,
    renderList,
    select,
    wireName,
  });
})();
