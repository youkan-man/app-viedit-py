'use strict';

(() => {
  const E = globalThis.VISemanticEditor;
  const { S, SURFACES, number, label, html } = E;

  function fallbackSemantic(graph) {
    const connections = graph.connections || [];
    const objects = (graph.models || [])
      .filter((model) => ['front-panel', 'block-diagram'].includes(model.layer) && !['wire', 'container', 'decoration'].includes(model.kind))
      .map((model) => {
        const sourcePosition = model.position;
        return {
          id: model.id, component_id: model.id, surface: model.layer,
          kind: model.kind === 'control' ? 'control' : model.kind,
          category: model.kind === 'connector' ? 'terminal' : model.layer === 'front-panel' ? 'control' : 'node',
          name: model.name || model.class_name || model.kind, symbol: model.kind === 'function' ? 'ƒ' : '',
          class_name: model.class_name || '', uid: model.uid || '',
          bounds: sourcePosition ? {
            x: number(sourcePosition.x), y: number(sourcePosition.y),
            width: Math.max(8, number(sourcePosition.width, 40)), height: Math.max(8, number(sourcePosition.height, 24)),
            source_property_id: sourcePosition.source_property_id,
          } : null,
          positioned: Boolean(sourcePosition), movable: Boolean(sourcePosition), resizable: Boolean(sourcePosition),
          terminal_ids: [], linked_terminal_ids: [], wire_ids: [],
          source: { file: model.file || '', xml_path: model.xml_path || '' },
        };
      });
    const wires = (graph.nets || []).map((net) => ({
      id: net.wire_id || net.id, name: net.name || '配線',
      source_terminal_id: net.connector_ids?.[0] || null,
      target_terminal_ids: (net.connector_ids || []).slice(1), terminal_ids: net.connector_ids || [],
      source_object_id: net.endpoint_ids?.[0] || null, target_object_ids: (net.endpoint_ids || []).slice(1),
      route_points: net.points || [], resolved: (net.endpoint_ids || []).length > 1,
    }));
    return {
      version: 0, objects, wires,
      summary: {
        controls: objects.filter((item) => item.surface === 'front-panel').length,
        indicators: 0, block_diagram_nodes: objects.filter((item) => item.category === 'node').length,
        wires: wires.length, resolved_wires: wires.filter((wire) => wire.resolved).length,
      },
      warnings: connections.length ? ['意味モデル未生成のため接続グラフを簡易表示しています。'] : [],
      debug: { unresolved_references: graph.unresolved?.length || 0 },
    };
  }

  function install(vi) {
    S.vi = vi;
    S.objects = new Map((vi.objects || []).map((item) => [item.id, item]));
    S.wires = new Map((vi.wires || []).map((wire) => [wire.id, wire]));
    S.local.clear(); S.dirty.clear(); S.selected = null; S.box = null; S.fitBox = null;
  }

  function fallbackBounds(item, index = 0) {
    const key = `fallback:${item.surface}:${item.id}`;
    if (!S.local.has(key)) {
      S.local.set(key, {
        x: 40 + (index % 4) * 140, y: 40 + Math.floor(index / 4) * 88,
        width: item.category === 'terminal' ? 10 : 100, height: item.category === 'terminal' ? 10 : 42,
        fallback: true,
      });
    }
    return S.local.get(key);
  }

  function getBounds(item, index = 0) {
    if (!item) return null;
    if (S.local.has(item.id)) return S.local.get(item.id);
    if (item.bounds) {
      return {
        x: number(item.bounds.x), y: number(item.bounds.y),
        width: Math.max(4, number(item.bounds.width, 40)), height: Math.max(4, number(item.bounds.height, 24)),
      };
    }
    return fallbackBounds(item, index);
  }

  function surfaceObjects() {
    return (S.vi?.objects || []).filter((item) => item.surface === S.surface && (S.showTerminals || item.category !== 'terminal'));
  }

  function visible(item) {
    const query = S.el.modelGraphQuery.value.trim().toLowerCase();
    const kind = S.el.modelGraphKind.value;
    return (!kind || item.kind === kind || item.category === kind)
      && (!query || `${item.name} ${item.kind} ${item.class_name || ''}`.toLowerCase().includes(query));
  }

  function typeClass(item) {
    if (item.category === 'control') return 'is-control';
    if (item.category === 'indicator') return 'is-indicator';
    if (item.category === 'terminal') return `is-terminal is-${item.direction || 'unknown'}`;
    return `is-node is-${item.kind || 'node'}`;
  }

  function setSurface(surface, fit = true) {
    if (!SURFACES[surface]) return;
    S.surface = surface; S.selected = null; S.el.modelGraphLayer.value = surface;
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      const active = button.dataset.viSurface === surface;
      button.classList.toggle('is-active', active); button.setAttribute('aria-selected', String(active));
    });
    S.el.viSurfaceTitle.textContent = SURFACES[surface];
    S.el.viSurfaceSubtitle.textContent = surface === 'front-panel' ? '操作部品の位置とサイズ' : 'ノード、端子、配線の接続関係';
    S.el.modelGraphViewport.classList.toggle('is-front-panel', surface === 'front-panel');
    E.renderAll(fit);
  }

  function renderSummary() {
    const summary = S.vi?.summary || {};
    S.el.viSummaryControls.textContent = number(summary.controls || summary.numeric_controls).toLocaleString('ja-JP');
    S.el.viSummaryIndicators.textContent = number(summary.indicators || summary.numeric_indicators).toLocaleString('ja-JP');
    S.el.viSummaryNodes.textContent = number(summary.block_diagram_nodes).toLocaleString('ja-JP');
    S.el.viSummaryWires.textContent = number(summary.wires).toLocaleString('ja-JP');
    S.el.viSummaryWireNote.textContent = `${number(summary.resolved_wires).toLocaleString('ja-JP')} resolved`;
    document.querySelector('#model-graph-model-count').textContent = (S.vi?.objects || []).length;
    document.querySelector('#model-graph-edge-count').textContent = number(summary.wires);
    document.querySelector('#model-graph-net-count').textContent = number(summary.wires);
  }

  function renderDiagnostics() {
    const warnings = S.vi?.warnings || [];
    S.el.viDiagnostics.hidden = !warnings.length;
    S.el.viDiagnostics.textContent = warnings.join(' ');
  }

  function renderDebug() {
    const graph = S.payload?.graph || {}, documents = graph.documents || [], unresolved = graph.unresolved || [];
    S.el.modelDocumentCount.textContent = documents.length; S.el.modelUnresolvedCount.textContent = unresolved.length;
    document.querySelector('#model-graph-document-count').textContent = documents.length;
    document.querySelector('#model-graph-unresolved-note').textContent = `${unresolved.length} unresolved`;
    S.el.modelDocumentList.replaceChildren(...(documents.length ? documents.map((documentModel) => {
      const row = html('div', 'vi-debug-row');
      row.append(html('strong', '', documentModel.path), html('small', '', `${documentModel.layer || 'metadata'} · ${documentModel.model_count || 0} objects`));
      return row;
    }) : [html('div', 'vi-debug-empty', '解析ファイルなし')]));
    S.el.modelUnresolvedList.replaceChildren(...(unresolved.length ? unresolved.slice(0, 50).map((edge) => {
      const row = html('div', 'vi-debug-row');
      row.append(html('strong', '', edge.label || edge.type || '参照'), html('small', '', `${edge.source || 'unknown'} → ${edge.target_key || 'unknown'}`));
      return row;
    }) : [html('div', 'vi-debug-empty', '未解決参照なし')]));
  }

  function renderKinds() {
    const current = S.el.modelGraphKind.value;
    const kinds = [...new Set((S.vi?.objects || []).filter((item) => item.surface === S.surface).map((item) => item.kind))].sort();
    S.el.modelGraphKind.replaceChildren(new Option('すべての種類', ''), ...kinds.map((kind) => new Option(label({ kind }), kind)));
    if (kinds.includes(current)) S.el.modelGraphKind.value = current;
  }

  function select(id, reveal = false) {
    if (!S.objects.has(id) && !S.wires.has(id)) return;
    S.selected = id;
    const item = S.objects.get(id);
    if (reveal && item?.surface !== S.surface) setSurface(item.surface, false);
    renderList(); E.renderCanvas(); E.renderInspector();
    if (reveal) document.querySelector(`[data-list-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  function wireName(wire) {
    if (!wire) return '配線';
    const source = S.objects.get(wire.source_object_id);
    const targets = (wire.target_object_ids || []).map((id) => S.objects.get(id)).filter(Boolean);
    return source && targets.length ? `${source.name} → ${targets.map((item) => item.name).join(', ')}` : wire.name || '配線';
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
      heading.append(html('span', '', title), html('small', '', items.length)); fragment.append(heading);
      items.forEach((item) => {
        const isWire = S.wires.has(item.id), button = document.createElement('button');
        button.type = 'button'; button.dataset.listId = item.id; button.role = 'option';
        button.className = `vi-object-list-item ${isWire ? 'is-wire' : typeClass(item)}${S.selected === item.id ? ' is-selected' : ''}`;
        const copy = html('span', 'vi-list-copy');
        copy.append(
          html('strong', '', isWire ? wireName(item) : item.name),
          html('small', '', isWire ? (item.resolved ? '接続確定' : '方向未確定') : `${label(item)}${item.positioned ? '' : ' · 位置なし'}`),
        );
        button.append(html('i', 'vi-list-glyph', isWire ? '⌁' : item.symbol || (item.category === 'terminal' ? '●' : '◇')), copy);
        button.addEventListener('click', () => select(item.id)); fragment.append(button);
      });
    });
    if (!fragment.childNodes.length) fragment.append(html('div', 'vi-list-empty', '条件に一致するオブジェクトはありません。'));
    S.el.viObjectList.replaceChildren(fragment);
  }

  Object.assign(E, {
    fallbackSemantic, install, getBounds, surfaceObjects, visible, typeClass, setSurface,
    renderSummary, renderDiagnostics, renderDebug, renderKinds, renderList, select, wireName,
  });
})();
