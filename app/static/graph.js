'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const MODEL_KINDS = new Set([
    'component', 'control', 'connector', 'wire', 'structure',
    'subvi', 'function', 'constant', 'container', 'decoration',
  ]);

  const graphState = {
    job: null,
    payload: null,
    selectedId: null,
    loadSequence: 0,
    active: false,
    baseViewBox: null,
    currentViewBox: null,
    revision: '',
    layerInitialized: false,
    elements: {},
  };

  function cacheElements() {
    graphState.elements = {
      state: $('#model-graph-state'),
      refresh: $('#model-graph-refresh'),
      query: $('#model-graph-query'),
      layer: $('#model-graph-layer'),
      kind: $('#model-graph-kind'),
      showHierarchy: $('#model-graph-show-hierarchy'),
      showUnpositioned: $('#model-graph-show-unpositioned'),
      fit: $('#model-graph-fit'),
      zoomIn: $('#model-graph-zoom-in'),
      zoomOut: $('#model-graph-zoom-out'),
      svg: $('#model-graph-svg'),
      empty: $('#model-graph-empty'),
      viewport: $('#model-graph-viewport'),
      modelCount: $('#model-graph-model-count'),
      positionedNote: $('#model-graph-positioned-note'),
      edgeCount: $('#model-graph-edge-count'),
      netCount: $('#model-graph-net-count'),
      documentCount: $('#model-graph-document-count'),
      unresolvedNote: $('#model-graph-unresolved-note'),
      documentList: $('#model-document-list'),
      documentListCount: $('#model-document-count'),
      unresolvedList: $('#model-unresolved-list'),
      unresolvedCount: $('#model-unresolved-count'),
      inspectorEmpty: $('#model-inspector-empty'),
      inspector: $('#model-inspector'),
      inspectorKind: $('#model-selection-kind'),
      inspectorName: $('#model-inspector-name'),
      inspectorClass: $('#model-inspector-class'),
      inspectorUid: $('#model-inspector-uid'),
      inspectorFile: $('#model-inspector-file'),
      inspectorPath: $('#model-inspector-path'),
      inspectorPosition: $('#model-inspector-position'),
      inspectorConnectionCount: $('#model-inspector-connection-count'),
      inspectorConnections: $('#model-inspector-connections'),
    };
  }

  function setState(text, className = '') {
    graphState.elements.state.textContent = text;
    graphState.elements.state.className = `state-badge${className ? ` ${className}` : ''}`;
  }

  function revisionFor(job) {
    if (!job) return '';
    return [
      job.job_id,
      job.xml_sha256,
      job.xml_modified_at,
      job.component_modified_at,
      job.dataset_xml_modified_at,
      job.dataset_xml_modified_path,
      job.last_quantization?.applied_at,
      job.files?.map((file) => `${file.path}:${file.size}`).join('|'),
    ].filter(Boolean).join('::');
  }

  function svgElement(name, attrs = {}) {
    const element = document.createElementNS(SVG_NS, name);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value !== null && value !== undefined) element.setAttribute(key, String(value));
    });
    return element;
  }

  function clearElement(element) {
    element.replaceChildren();
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text ?? '';
    return element;
  }

  function populateSelect(select, entries, labeler) {
    const previous = select.value;
    const first = select.options[0]?.cloneNode(true);
    select.replaceChildren(first || new Option('すべて', ''));
    entries.forEach((entry) => {
      const option = document.createElement('option');
      option.value = entry;
      option.textContent = labeler(entry);
      select.appendChild(option);
    });
    if ([...select.options].some((option) => option.value === previous)) select.value = previous;
  }

  function renderSummary(graph) {
    const summary = graph.summary || {};
    graphState.elements.modelCount.textContent = Number(summary.models || 0).toLocaleString('ja-JP');
    graphState.elements.positionedNote.textContent = `${Number(summary.positioned_models || 0).toLocaleString('ja-JP')} positioned`;
    graphState.elements.edgeCount.textContent = Number(summary.connections || 0).toLocaleString('ja-JP');
    graphState.elements.netCount.textContent = Number(summary.nets || 0).toLocaleString('ja-JP');
    graphState.elements.documentCount.textContent = Number(summary.documents || 0).toLocaleString('ja-JP');
    graphState.elements.unresolvedNote.textContent = `${Number(summary.unresolved || 0).toLocaleString('ja-JP')} unresolved`;

    populateSelect(
      graphState.elements.layer,
      Object.keys(summary.layers || {}).sort(),
      (value) => `${value} (${summary.layers[value]})`,
    );
    populateSelect(
      graphState.elements.kind,
      Object.keys(summary.kinds || {}).sort(),
      (value) => `${value} (${summary.kinds[value]})`,
    );
    if (!graphState.layerInitialized) {
      const layers = summary.layers || {};
      if (layers['block-diagram']) graphState.elements.layer.value = 'block-diagram';
      else if (layers['front-panel']) graphState.elements.layer.value = 'front-panel';
      graphState.layerInitialized = true;
    }
  }

  function renderDocuments(graph) {
    const list = graphState.elements.documentList;
    clearElement(list);
    const documents = graph.documents || [];
    graphState.elements.documentListCount.textContent = String(documents.length);
    if (!documents.length) {
      list.append(textElement('div', 'model-list-empty', 'XMLファイルはありません。'));
      return;
    }
    documents.forEach((documentModel) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'model-document-item';
      button.dataset.layer = documentModel.layer;
      button.append(
        textElement('strong', '', documentModel.path),
        textElement(
          'small',
          '',
          `${documentModel.layer} · ${documentModel.model_count} models · ${documentModel.outbound_document_ids?.length || 0} refs`,
        ),
      );
      button.addEventListener('click', () => {
        graphState.elements.layer.value = documentModel.layer === 'other' ? '' : documentModel.layer;
        render();
      });
      list.appendChild(button);
    });
  }

  function renderUnresolved(graph) {
    const list = graphState.elements.unresolvedList;
    clearElement(list);
    const unresolved = graph.unresolved || [];
    graphState.elements.unresolvedCount.textContent = String(unresolved.length);
    if (!unresolved.length) {
      list.append(textElement('div', 'model-list-empty is-good', 'すべて解決済み'));
      return;
    }
    unresolved.slice(0, 80).forEach((edge) => {
      const row = document.createElement('div');
      row.className = 'model-unresolved-item';
      row.append(
        textElement('strong', '', `${edge.scope === 'document' ? 'XML' : 'model'} · ${edge.label || edge.type}`),
        textElement('small', '', `${edge.source || 'source unknown'} → ${edge.target_key || 'target unknown'}`),
      );
      list.appendChild(row);
    });
    if (unresolved.length > 80) {
      list.append(textElement('div', 'model-list-empty', `ほか ${unresolved.length - 80} 件`));
    }
  }

  function filteredModels(graph) {
    const query = graphState.elements.query.value.trim().toLowerCase();
    const layer = graphState.elements.layer.value;
    const kind = graphState.elements.kind.value;
    const includeUnpositioned = graphState.elements.showUnpositioned.checked;
    return (graph.models || []).filter((model) => {
      if (!MODEL_KINDS.has(model.kind)) return false;
      if (layer && model.layer !== layer) return false;
      if (kind && model.kind !== kind) return false;
      if (!includeUnpositioned && !model.positioned) return false;
      if (query) {
        const haystack = [
          model.name, model.class_name, model.uid, model.file,
          model.xml_path, model.kind, ...(model.aliases || []),
        ].join(' ').toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }

  function displayRect(model, unpositionedIndex) {
    if (model.position) {
      return {
        x: Number(model.position.x || 0),
        y: Number(model.position.y || 0),
        width: Math.max(18, Math.abs(Number(model.position.width || 0))),
        height: Math.max(18, Math.abs(Number(model.position.height || 0))),
      };
    }
    const column = unpositionedIndex % 4;
    const row = Math.floor(unpositionedIndex / 4);
    return { x: column * 170, y: row * 70, width: 150, height: 48 };
  }

  function nodeCenter(rect) {
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  }

  function edgePath(sourceRect, targetRect) {
    const source = nodeCenter(sourceRect);
    const target = nodeCenter(targetRect);
    const middleX = source.x + (target.x - source.x) / 2;
    return `M ${source.x} ${source.y} H ${middleX} V ${target.y} H ${target.x}`;
  }

  function renderGraph(graph, models) {
    const svg = graphState.elements.svg;
    clearElement(svg);
    const rects = new Map();
    let unpositionedIndex = 0;
    models.forEach((model) => {
      rects.set(model.id, displayRect(model, model.positioned ? 0 : unpositionedIndex++));
    });

    const visibleIds = new Set(models.map((model) => model.id));
    const showHierarchy = graphState.elements.showHierarchy.checked;
    const visibleEdges = (graph.connections || []).filter((edge) => (
      edge.resolved
      && visibleIds.has(edge.source)
      && visibleIds.has(edge.target)
      && (showHierarchy || edge.type !== 'containment')
    ));

    const defs = svgElement('defs');
    const marker = svgElement('marker', {
      id: 'model-edge-arrow',
      markerWidth: 8,
      markerHeight: 8,
      refX: 7,
      refY: 4,
      orient: 'auto',
      markerUnits: 'strokeWidth',
    });
    marker.appendChild(svgElement('path', { d: 'M 0 0 L 8 4 L 0 8 z', class: 'model-edge-arrow' }));
    defs.appendChild(marker);
    svg.appendChild(defs);

    visibleEdges.forEach((edge) => {
      const sourceRect = rects.get(edge.source);
      const targetRect = rects.get(edge.target);
      if (!sourceRect || !targetRect) return;
      const path = svgElement('path', {
        d: edgePath(sourceRect, targetRect),
        class: `model-edge is-${edge.type}`,
        'data-edge-id': edge.id,
        'marker-end': edge.direction === 'directed' ? 'url(#model-edge-arrow)' : null,
      });
      const title = svgElement('title');
      title.textContent = `${edge.label} · ${edge.type}`;
      path.appendChild(title);
      svg.appendChild(path);
    });

    models.forEach((model) => {
      const rect = rects.get(model.id);
      const group = svgElement('g', {
        class: `model-node is-${model.kind}${graphState.selectedId === model.id ? ' is-selected' : ''}`,
        tabindex: 0,
        role: 'button',
        'data-model-id': model.id,
      });
      const shape = svgElement('rect', {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        rx: 2,
      });
      const label = svgElement('text', {
        x: rect.x + 5,
        y: rect.y + Math.min(15, Math.max(12, rect.height / 2)),
        class: 'model-node-label',
      });
      label.textContent = model.name || model.class_name || model.kind;
      const detail = svgElement('text', {
        x: rect.x + 5,
        y: rect.y + Math.min(rect.height - 4, 29),
        class: 'model-node-detail',
      });
      detail.textContent = [model.class_name, model.uid && `#${model.uid}`].filter(Boolean).join(' · ');
      const title = svgElement('title');
      title.textContent = `${model.name}\n${model.file}${model.xml_path}\n${model.kind} · ${model.class_name || 'class unknown'}`;
      group.append(shape, label);
      if (rect.height >= 28) group.append(detail);
      group.append(title);
      const select = () => selectModel(model.id);
      group.addEventListener('click', select);
      group.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          select();
        }
      });
      svg.appendChild(group);
    });

    if (!models.length) {
      graphState.elements.empty.hidden = false;
      graphState.baseViewBox = null;
      svg.removeAttribute('viewBox');
      return;
    }
    graphState.elements.empty.hidden = true;
    const values = [...rects.values()];
    const minX = Math.min(...values.map((rect) => rect.x));
    const minY = Math.min(...values.map((rect) => rect.y));
    const maxX = Math.max(...values.map((rect) => rect.x + rect.width));
    const maxY = Math.max(...values.map((rect) => rect.y + rect.height));
    const padding = Math.max(24, Math.min(120, Math.max(maxX - minX, maxY - minY) * 0.05));
    graphState.baseViewBox = {
      x: minX - padding,
      y: minY - padding,
      width: Math.max(120, maxX - minX + padding * 2),
      height: Math.max(120, maxY - minY + padding * 2),
    };
    fitGraph();
  }

  function applyViewBox(box) {
    if (!box) return;
    graphState.currentViewBox = { ...box };
    graphState.elements.svg.setAttribute(
      'viewBox',
      `${box.x} ${box.y} ${box.width} ${box.height}`,
    );
    graphState.elements.svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  }

  function fitGraph() {
    if (!graphState.baseViewBox) return;
    applyViewBox(graphState.baseViewBox);
  }

  function zoomGraph(factor, clientX = null, clientY = null) {
    const box = graphState.currentViewBox || graphState.baseViewBox;
    if (!box) return;
    const viewportRect = graphState.elements.viewport.getBoundingClientRect();
    const relativeX = clientX == null || viewportRect.width === 0
      ? 0.5
      : Math.max(0, Math.min(1, (clientX - viewportRect.left) / viewportRect.width));
    const relativeY = clientY == null || viewportRect.height === 0
      ? 0.5
      : Math.max(0, Math.min(1, (clientY - viewportRect.top) / viewportRect.height));
    const nextWidth = Math.max(20, Math.min(box.width * factor, graphState.baseViewBox.width * 12));
    const nextHeight = Math.max(20, Math.min(box.height * factor, graphState.baseViewBox.height * 12));
    applyViewBox({
      x: box.x + (box.width - nextWidth) * relativeX,
      y: box.y + (box.height - nextHeight) * relativeY,
      width: nextWidth,
      height: nextHeight,
    });
  }

  function modelConnections(graph, modelId) {
    return (graph.connections || []).filter((edge) => (
      edge.source === modelId || edge.target === modelId
    ));
  }

  function renderInspector(graph) {
    const model = (graph.models || []).find((item) => item.id === graphState.selectedId);
    graphState.elements.inspectorEmpty.hidden = Boolean(model);
    graphState.elements.inspector.hidden = !model;
    if (!model) {
      graphState.elements.inspectorKind.textContent = '—';
      return;
    }
    graphState.elements.inspectorKind.textContent = model.kind;
    graphState.elements.inspectorName.textContent = model.name || model.tag;
    graphState.elements.inspectorClass.textContent = model.class_name || '—';
    graphState.elements.inspectorUid.textContent = model.uid || (model.aliases || []).join(', ') || '—';
    graphState.elements.inspectorFile.textContent = model.file;
    graphState.elements.inspectorFile.title = model.file;
    graphState.elements.inspectorPath.textContent = model.xml_path;
    graphState.elements.inspectorPath.title = model.xml_path;
    graphState.elements.inspectorPosition.textContent = model.position
      ? `x=${model.position.x}, y=${model.position.y}, w=${model.position.width}, h=${model.position.height}`
      : '位置情報なし';

    const connections = modelConnections(graph, model.id);
    graphState.elements.inspectorConnectionCount.textContent = String(connections.length);
    clearElement(graphState.elements.inspectorConnections);
    if (!connections.length) {
      graphState.elements.inspectorConnections.append(
        textElement('div', 'model-list-empty', '接続は検出されていません。'),
      );
      return;
    }
    const byId = new Map((graph.models || []).map((item) => [item.id, item]));
    connections.slice(0, 120).forEach((edge) => {
      const otherId = edge.source === model.id ? edge.target : edge.source;
      const other = byId.get(otherId);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'model-connection-item';
      button.disabled = !other;
      button.append(
        textElement('strong', '', other?.name || edge.target_key || '未解決'),
        textElement(
          'small',
          '',
          `${edge.type} · ${edge.label} · ${edge.confidence || 'unknown'}${edge.resolution ? ` / ${edge.resolution}` : ''}`,
        ),
      );
      if (other) button.addEventListener('click', () => selectModel(other.id));
      graphState.elements.inspectorConnections.appendChild(button);
    });
  }

  function selectModel(modelId) {
    graphState.selectedId = modelId;
    render();
  }

  function render() {
    const graph = graphState.payload?.graph;
    if (!graph) return;
    renderSummary(graph);
    renderDocuments(graph);
    renderUnresolved(graph);
    const models = filteredModels(graph);
    if (graphState.selectedId && !models.some((model) => model.id === graphState.selectedId)) {
      graphState.selectedId = models[0]?.id || null;
    }
    renderGraph(graph, models);
    renderInspector(graph);
  }

  async function load({ force = false } = {}) {
    if (!graphState.job?.job_id) return;
    const sequence = ++graphState.loadSequence;
    graphState.elements.refresh.disabled = true;
    setState('解析中');
    try {
      const payload = await apiRequest(`/api/jobs/${encodeURIComponent(graphState.job.job_id)}/model${force ? `?refresh=${Date.now()}` : ''}`);
      if (sequence !== graphState.loadSequence) return;
      graphState.payload = payload;
      const graph = payload.graph;
      if (!graph) throw new Error('統合モデルグラフがAPI応答にありません。');
      setState('解析済み', 'is-ready');
      const preferred = (graph.models || []).find((model) => (
        MODEL_KINDS.has(model.kind) && model.positioned && model.layer === 'block-diagram'
      )) || (graph.models || []).find((model) => MODEL_KINDS.has(model.kind) && model.positioned);
      if (!graphState.selectedId) graphState.selectedId = preferred?.id || null;
      render();
      const warnings = graph.warnings || [];
      if (warnings.length) {
        showToast(`モデル解析: ${warnings[0]}`, 'info', 7000);
      }
    } catch (error) {
      if (sequence !== graphState.loadSequence) return;
      graphState.payload = null;
      setState('解析失敗', 'is-dirty');
      graphState.elements.empty.hidden = false;
      graphState.elements.empty.querySelector('strong').textContent = 'モデル解析に失敗しました';
      graphState.elements.empty.querySelector('span').textContent = describeError(error);
      showToast(`モデル解析: ${describeError(error)}`, 'error', 10000);
    } finally {
      graphState.elements.refresh.disabled = false;
    }
  }

  async function setJob(job) {
    const sameJob = graphState.job?.job_id === job?.job_id;
    const nextRevision = revisionFor(job);
    const revisionChanged = nextRevision !== graphState.revision;
    graphState.job = job || null;
    graphState.revision = nextRevision;
    if (!job) {
      clearJob();
      return;
    }
    if (!sameJob || revisionChanged || !graphState.payload) {
      graphState.payload = null;
      graphState.selectedId = null;
      graphState.layerInitialized = false;
      await load({ force: revisionChanged });
    } else {
      render();
    }
  }

  async function onDatasetChanged(job) {
    graphState.job = job || graphState.job;
    graphState.revision = revisionFor(graphState.job);
    graphState.payload = null;
    graphState.selectedId = null;
    graphState.layerInitialized = false;
    await load({ force: true });
  }

  function clearJob() {
    graphState.loadSequence += 1;
    graphState.job = null;
    graphState.payload = null;
    graphState.selectedId = null;
    graphState.revision = '';
    graphState.layerInitialized = false;
    graphState.baseViewBox = null;
    graphState.currentViewBox = null;
    clearElement(graphState.elements.svg);
    clearElement(graphState.elements.documentList);
    clearElement(graphState.elements.unresolvedList);
    graphState.elements.empty.hidden = false;
    graphState.elements.inspector.hidden = true;
    graphState.elements.inspectorEmpty.hidden = false;
    setState('未解析');
  }

  function activate() {
    graphState.active = true;
    if (graphState.job && !graphState.payload) void load();
    else if (graphState.payload) render();
  }

  function initialize() {
    cacheElements();
    let queryTimer;
    graphState.elements.query.addEventListener('input', () => {
      window.clearTimeout(queryTimer);
      queryTimer = window.setTimeout(render, 180);
    });
    [
      graphState.elements.layer,
      graphState.elements.kind,
      graphState.elements.showHierarchy,
      graphState.elements.showUnpositioned,
    ].forEach((element) => element.addEventListener('change', render));
    graphState.elements.fit.addEventListener('click', fitGraph);
    graphState.elements.zoomIn.addEventListener('click', () => zoomGraph(0.8));
    graphState.elements.zoomOut.addEventListener('click', () => zoomGraph(1.25));
    graphState.elements.refresh.addEventListener('click', () => void load({ force: true }));

    graphState.elements.viewport.addEventListener('wheel', (event) => {
      if (!graphState.currentViewBox) return;
      event.preventDefault();
      zoomGraph(event.deltaY < 0 ? 0.86 : 1.16, event.clientX, event.clientY);
    }, { passive: false });

    let pan = null;
    graphState.elements.viewport.addEventListener('pointerdown', (event) => {
      if (
        event.button !== 0
        || !graphState.currentViewBox
        || event.target.closest?.('.model-node')
      ) return;
      pan = {
        x: event.clientX,
        y: event.clientY,
        box: { ...graphState.currentViewBox },
      };
      graphState.elements.viewport.classList.add('is-panning');
      graphState.elements.viewport.setPointerCapture?.(event.pointerId);
    });
    graphState.elements.viewport.addEventListener('pointermove', (event) => {
      if (!pan) return;
      const rect = graphState.elements.viewport.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      applyViewBox({
        x: pan.box.x - (event.clientX - pan.x) * pan.box.width / rect.width,
        y: pan.box.y - (event.clientY - pan.y) * pan.box.height / rect.height,
        width: pan.box.width,
        height: pan.box.height,
      });
    });
    const endPan = (event) => {
      if (!pan) return;
      pan = null;
      graphState.elements.viewport.classList.remove('is-panning');
      graphState.elements.viewport.releasePointerCapture?.(event.pointerId);
    };
    graphState.elements.viewport.addEventListener('pointerup', endPan);
    graphState.elements.viewport.addEventListener('pointercancel', endPan);
    graphState.elements.viewport.addEventListener('dblclick', fitGraph);
  }

  globalThis.viModelGraph = {
    setJob,
    onDatasetChanged,
    clearJob,
    activate,
    refresh: () => load({ force: true }),
  };

  document.addEventListener('DOMContentLoaded', initialize);
})();
