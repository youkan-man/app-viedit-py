'use strict';

(() => {
  const PAGE_SIZE = 200;
  const TREE_NODE_BUDGET = 900;
  const PROPERTY_RENDER_LIMIT = 1200;

  const explorer = {
    job: null,
    model: null,
    components: [],
    total: 0,
    offset: 0,
    selectedId: null,
    detail: null,
    changes: new Map(),
    externalDirty: false,
    loadSequence: 0,
    propertyFilter: '',
    elements: {},
  };

  const kindLabels = {
    file: 'file',
    section: 'section',
    component: 'component',
    control: 'control',
    connector: 'connector',
    wire: 'wire',
    structure: 'structure',
    subvi: 'subVI',
    function: 'function',
    constant: 'constant',
    container: 'container',
    decoration: 'decoration',
    'xml-node': 'XML node',
  };

  function ensureStylesheet() {
    if (document.querySelector('link[data-component-explorer-style]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/components.css';
    link.dataset.componentExplorerStyle = 'true';
    document.head.appendChild(link);
  }

  function createMarkup() {
    if ($('#component-model-card')) return;
    const metrics = $('.metrics');
    if (!metrics) return;
    const section = document.createElement('section');
    section.id = 'component-model-card';
    section.className = 'component-model-card';
    section.hidden = true;
    section.setAttribute('aria-labelledby', 'component-model-title');
    section.innerHTML = `
      <div class="component-model-head">
        <div>
          <span class="section-kicker">COMPONENT MODEL</span>
          <h3 id="component-model-title">VI構造・コンポーネント</h3>
          <p>ジョブ内の全XML要素・属性・値を解析し、SL__object、セクション、参照、配列をコンポーネント単位の構造として表示します。安全に変更できる値だけをフォームから保存できます。</p>
        </div>
        <div class="component-model-actions">
          <span id="component-model-state" class="state-badge">未解析</span>
          <button id="component-model-refresh" class="secondary-action button-reset" type="button">再解析</button>
        </div>
      </div>
      <div id="component-model-warning" class="component-model-warning" hidden></div>
      <div class="component-model-summary" aria-label="構造解析サマリー">
        <div><span>XML files</span><strong id="component-model-files">0</strong><small id="component-model-files-note">—</small></div>
        <div><span>Elements</span><strong id="component-model-elements">0</strong><small id="component-model-elements-note">—</small></div>
        <div><span>Components</span><strong id="component-model-components">0</strong><small id="component-model-components-note">—</small></div>
        <div><span>Properties</span><strong id="component-model-properties">0</strong><small id="component-model-properties-note">—</small></div>
        <div><span>Classes</span><strong id="component-model-classes">0</strong><small id="component-model-classes-note">—</small></div>
        <div><span>References</span><strong id="component-model-relations">0</strong><small id="component-model-relations-note">—</small></div>
      </div>
      <div id="component-class-inventory" class="component-class-inventory" hidden></div>
      <div class="component-model-toolbar">
        <label>検索<input id="component-query" type="search" placeholder="名前、class、UID、XMLパス"></label>
        <label>XML file<select id="component-file-filter"><option value="">すべて</option></select></label>
        <label>kind<select id="component-kind-filter"><option value="">すべて</option></select></label>
        <button id="component-clear-filter" class="secondary-action button-reset" type="button">フィルター解除</button>
      </div>
      <div class="component-model-layout">
        <aside class="component-pane component-files-pane" aria-label="XMLファイル">
          <div class="component-pane-head"><strong>XML files</strong><span id="component-file-count">0</span></div>
          <div id="component-file-list" class="component-file-list"></div>
        </aside>
        <section class="component-pane component-list-pane" aria-label="コンポーネント一覧">
          <div class="component-pane-head"><strong>Components</strong><span id="component-list-count">0</span></div>
          <div class="component-table-wrap">
            <table class="component-table">
              <thead><tr><th>Name / path</th><th>Kind / class</th><th>UID / properties</th><th>Position</th></tr></thead>
              <tbody id="component-list-body"></tbody>
            </table>
          </div>
          <div class="component-pager">
            <span id="component-page-info">0–0 / 0</span>
            <div><button id="component-prev" type="button">前へ</button><button id="component-next" type="button">次へ</button></div>
          </div>
        </section>
        <aside class="component-pane component-inspector-pane" aria-label="コンポーネントプロパティ">
          <div class="component-pane-head"><strong>Properties</strong><span id="component-inspector-count">—</span></div>
          <div class="component-inspector-scroll">
            <div id="component-inspector-empty" class="component-inspector-empty">コンポーネントを選択してください。</div>
            <div id="component-inspector" class="component-inspector-body" hidden></div>
          </div>
        </aside>
      </div>`;
    metrics.insertAdjacentElement('afterend', section);
  }

  function cacheElements() {
    explorer.elements = {
      card: $('#component-model-card'),
      state: $('#component-model-state'),
      warning: $('#component-model-warning'),
      refresh: $('#component-model-refresh'),
      summaryFiles: $('#component-model-files'),
      summaryFilesNote: $('#component-model-files-note'),
      summaryElements: $('#component-model-elements'),
      summaryElementsNote: $('#component-model-elements-note'),
      summaryComponents: $('#component-model-components'),
      summaryComponentsNote: $('#component-model-components-note'),
      summaryProperties: $('#component-model-properties'),
      summaryPropertiesNote: $('#component-model-properties-note'),
      summaryClasses: $('#component-model-classes'),
      summaryClassesNote: $('#component-model-classes-note'),
      summaryRelations: $('#component-model-relations'),
      summaryRelationsNote: $('#component-model-relations-note'),
      classInventory: $('#component-class-inventory'),
      query: $('#component-query'),
      fileFilter: $('#component-file-filter'),
      kindFilter: $('#component-kind-filter'),
      clearFilter: $('#component-clear-filter'),
      fileCount: $('#component-file-count'),
      fileList: $('#component-file-list'),
      listCount: $('#component-list-count'),
      listBody: $('#component-list-body'),
      pageInfo: $('#component-page-info'),
      prev: $('#component-prev'),
      next: $('#component-next'),
      inspectorCount: $('#component-inspector-count'),
      inspectorEmpty: $('#component-inspector-empty'),
      inspector: $('#component-inspector'),
    };
  }

  function setState(text, className = '') {
    explorer.elements.state.textContent = text;
    explorer.elements.state.className = `state-badge${className ? ` ${className}` : ''}`;
  }

  function formatNumber(value) {
    return Number(value || 0).toLocaleString('ja-JP');
  }

  function clearNode(node) {
    node.replaceChildren();
  }

  function textNode(tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = value ?? '';
    return element;
  }

  function buttonLink(label, onClick, title = '') {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'component-link-button';
    button.textContent = label || '—';
    if (title) button.title = title;
    button.addEventListener('click', onClick);
    return button;
  }

  function showWarning(messages) {
    const list = Array.isArray(messages) ? messages.filter(Boolean) : messages ? [messages] : [];
    explorer.elements.warning.hidden = list.length === 0;
    explorer.elements.warning.textContent = list.slice(0, 20).join('\n');
  }

  function renderSummary(payload) {
    const summary = payload.summary || {};
    const classEntries = Object.entries(summary.classes || {});
    explorer.elements.summaryFiles.textContent = formatNumber(summary.xml_files);
    explorer.elements.summaryFilesNote.textContent = `${formatNumber(summary.parsed_files)} parsed / ${formatNumber(summary.failed_files)} failed`;
    explorer.elements.summaryElements.textContent = formatNumber(summary.elements);
    explorer.elements.summaryElementsNote.textContent = `${formatNumber(summary.attributes)} attrs / ${formatNumber(summary.scalar_values)} values`;
    explorer.elements.summaryComponents.textContent = formatNumber(summary.components);
    explorer.elements.summaryComponentsNote.textContent = Object.entries(summary.kinds || {}).slice(0, 3).map(([key, value]) => `${key} ${value}`).join(' · ') || '—';
    explorer.elements.summaryProperties.textContent = formatNumber(summary.properties);
    explorer.elements.summaryPropertiesNote.textContent = `${formatNumber(summary.editable_properties)} editable`;
    explorer.elements.summaryClasses.textContent = formatNumber(classEntries.length);
    explorer.elements.summaryClassesNote.textContent = classEntries.slice(0, 2).map(([key, value]) => `${key} ${value}`).join(' · ') || '—';
    explorer.elements.summaryRelations.textContent = formatNumber(summary.relationships);
    explorer.elements.summaryRelationsNote.textContent = `${formatNumber(summary.resolved_relationships)} resolved / ${formatNumber(summary.unresolved_relationships)} unresolved`;
    renderClassInventory(classEntries);
    showWarning(payload.warnings || []);
  }

  function renderClassInventory(entries) {
    const container = explorer.elements.classInventory;
    clearNode(container);
    const visible = entries.filter(([name]) => name && name !== '(unknown)').slice(0, 24);
    container.hidden = visible.length === 0;
    if (!visible.length) return;
    container.append(textNode('strong', '', '使用class'));
    visible.forEach(([name, count]) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'component-class-chip';
      chip.textContent = `${name} ${count}`;
      chip.title = `${name} を検索`;
      chip.addEventListener('click', () => {
        explorer.elements.query.value = name;
        explorer.offset = 0;
        void loadComponents();
      });
      container.append(chip);
    });
    if (entries.length > visible.length) container.append(textNode('span', 'component-class-more', `+${entries.length - visible.length}`));
  }

  function populateFilters(payload) {
    const selectedFile = explorer.elements.fileFilter.value;
    const selectedKind = explorer.elements.kindFilter.value;
    explorer.elements.fileFilter.replaceChildren(new Option('すべて', ''));
    (payload.files || []).forEach((file) => explorer.elements.fileFilter.add(new Option(file.path, file.path)));
    if ([...explorer.elements.fileFilter.options].some((option) => option.value === selectedFile)) explorer.elements.fileFilter.value = selectedFile;

    explorer.elements.kindFilter.replaceChildren(new Option('すべて', ''));
    Object.keys(payload.summary?.kinds || {}).sort().forEach((kind) => {
      explorer.elements.kindFilter.add(new Option(`${kindLabels[kind] || kind} (${payload.summary.kinds[kind]})`, kind));
    });
    if ([...explorer.elements.kindFilter.options].some((option) => option.value === selectedKind)) explorer.elements.kindFilter.value = selectedKind;
  }

  function renderFiles(files) {
    const container = explorer.elements.fileList;
    clearNode(container);
    explorer.elements.fileCount.textContent = String(files.length);
    const all = document.createElement('button');
    all.type = 'button';
    all.className = `component-file-button${explorer.elements.fileFilter.value ? '' : ' is-active'}`;
    all.append(textNode('strong', '', 'すべてのXML'), textNode('small', '', `${files.length} files`));
    all.addEventListener('click', () => selectFile(''));
    container.append(all);
    files.forEach((file) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `component-file-button${explorer.elements.fileFilter.value === file.path ? ' is-active' : ''}`;
      button.append(textNode('strong', '', file.path));
      const note = textNode('small', file.error ? 'component-file-error' : '', file.error
        ? `parse error · ${file.error}`
        : `${file.component_count} components · ${file.elements} elements · ${formatBytes(file.size)}`);
      button.append(note);
      button.addEventListener('click', () => selectFile(file.path));
      container.append(button);
    });
  }

  function selectFile(file) {
    explorer.elements.fileFilter.value = file;
    explorer.offset = 0;
    renderFiles(explorer.model?.files || []);
    void loadComponents();
  }

  function componentPosition(component) {
    const bounds = component.bounds;
    if (!bounds) return '—';
    return `${bounds.x},${bounds.y}\n${bounds.width}×${bounds.height}`;
  }

  function renderComponents(payload) {
    explorer.components = payload.items || [];
    explorer.total = payload.total || 0;
    explorer.elements.listCount.textContent = formatNumber(explorer.total);
    clearNode(explorer.elements.listBody);
    if (!explorer.components.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 4;
      cell.className = 'component-model-empty';
      cell.textContent = '条件に一致するコンポーネントはありません。';
      row.append(cell);
      explorer.elements.listBody.append(row);
    } else {
      explorer.components.forEach((component) => {
        const row = document.createElement('tr');
        row.dataset.componentId = component.id;
        row.classList.toggle('is-selected', component.id === explorer.selectedId);
        row.tabIndex = 0;
        row.addEventListener('click', () => void selectComponent(component.id));
        row.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            void selectComponent(component.id);
          }
        });

        const nameCell = document.createElement('td');
        const indent = Math.min(8, Number(component.depth || 0));
        const primary = textNode('span', 'component-primary', component.name || component.tag || 'unnamed');
        primary.classList.add(`component-depth-${indent}`);
        nameCell.append(primary, textNode('span', 'component-secondary', `${component.file} · ${component.path}`));

        const kindCell = document.createElement('td');
        kindCell.append(textNode('span', `component-kind ${component.kind || ''}`.trim(), kindLabels[component.kind] || component.kind || 'component'));
        kindCell.append(textNode('span', 'component-secondary', component.class_name || component.tag || '—'));

        const idCell = document.createElement('td');
        idCell.append(textNode('span', 'component-primary', component.uid || '—'));
        idCell.append(textNode('span', 'component-secondary', `${component.property_count} props · ${component.child_count} child · ${component.reference_count} ref`));

        const positionCell = textNode('td', 'component-position', componentPosition(component));
        row.append(nameCell, kindCell, idCell, positionCell);
        explorer.elements.listBody.append(row);
      });
    }
    const start = explorer.total ? explorer.offset + 1 : 0;
    const end = Math.min(explorer.total, explorer.offset + PAGE_SIZE);
    explorer.elements.pageInfo.textContent = `${start}–${end} / ${explorer.total}`;
    explorer.elements.prev.disabled = explorer.offset <= 0;
    explorer.elements.next.disabled = explorer.offset + PAGE_SIZE >= explorer.total;
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const query = explorer.elements.query.value.trim();
    const file = explorer.elements.fileFilter.value;
    const kind = explorer.elements.kindFilter.value;
    if (query) params.set('query', query);
    if (file) params.set('file', file);
    if (kind) params.set('kind', kind);
    params.set('offset', String(explorer.offset));
    params.set('limit', String(PAGE_SIZE));
    return params;
  }

  async function loadComponents() {
    if (!explorer.job) return;
    const sequence = ++explorer.loadSequence;
    explorer.elements.listBody.replaceChildren();
    const loadingRow = document.createElement('tr');
    const cell = textNode('td', 'component-model-empty', 'コンポーネントを検索中…');
    cell.colSpan = 4;
    loadingRow.append(cell);
    explorer.elements.listBody.append(loadingRow);
    try {
      const payload = await apiRequest(`/api/jobs/${encodeURIComponent(explorer.job.job_id)}/components?${buildQuery()}`);
      if (sequence !== explorer.loadSequence) return;
      renderComponents(payload);
      renderFiles(explorer.model?.files || []);
      if (explorer.selectedId && !explorer.detail) void selectComponent(explorer.selectedId);
    } catch (error) {
      if (sequence !== explorer.loadSequence) return;
      renderComponents({ items: [], total: 0 });
      showToast(`コンポーネント一覧: ${describeError(error)}`, 'error', 10000);
    }
  }

  function categoryForProperty(prop) {
    const name = String(prop.field_name || prop.normalized_name || '').toLowerCase();
    if (prop.value_type === 'rect' || prop.value_type === 'point' || name.includes('bounds') || name.includes('pos') || name.includes('origin')) return 'geometry';
    if (prop.reference_like || prop.value_type === 'reference' || prop.value_type === 'path') return 'reference';
    if (name.includes('color') || name.includes('font') || name.includes('visible') || name.includes('label') || name.includes('display')) return 'appearance';
    if (name.includes('type') || name.includes('td') || name.includes('datatype') || name.includes('value') || name.includes('data')) return 'data';
    if (prop.structural) return 'structure';
    if (prop.binary) return 'binary';
    return 'other';
  }

  function propertyCurrentValue(prop) {
    return explorer.changes.has(prop.id) ? explorer.changes.get(prop.id) : (prop.value ?? prop.preview ?? '');
  }

  function updateChange(prop, value) {
    const original = prop.value ?? prop.preview ?? '';
    if (value === original) explorer.changes.delete(prop.id);
    else explorer.changes.set(prop.id, value);
    updateSavebar();
  }

  function createPointEditor(prop) {
    const wrapper = document.createElement('div');
    wrapper.className = 'component-inline-coordinate';
    const parsed = prop.parsed || { x: 0, y: 0 };
    const current = propertyCurrentValue(prop);
    const tuple = /^\s*\(\s*([^,]+),\s*([^\)]+)\)\s*$/.exec(current);
    const yValue = tuple ? tuple[1].trim() : String(parsed.y ?? 0);
    const xValue = tuple ? tuple[2].trim() : String(parsed.x ?? 0);
    const x = document.createElement('input');
    const y = document.createElement('input');
    x.type = 'number';
    y.type = 'number';
    x.value = xValue;
    y.value = yValue;
    x.title = 'X';
    y.title = 'Y';
    const sync = () => updateChange(prop, `(${y.value || 0}, ${x.value || 0})`);
    x.addEventListener('input', sync);
    y.addEventListener('input', sync);
    wrapper.append(textNode('span', '', 'X'), x, textNode('span', '', 'Y'), y);
    return wrapper;
  }

  function createEditableControl(prop) {
    const value = propertyCurrentValue(prop);
    if (prop.value_type === 'bool') {
      const select = document.createElement('select');
      select.add(new Option('True', 'True'));
      select.add(new Option('False', 'False'));
      select.value = String(value).toLowerCase() === 'true' ? 'True' : 'False';
      select.addEventListener('change', () => updateChange(prop, select.value));
      return select;
    }
    if (prop.value_type === 'point') return createPointEditor(prop);
    const multiline = prop.value_type === 'string' && (String(value).length > 100 || String(value).includes('\n'));
    const control = multiline ? document.createElement('textarea') : document.createElement('input');
    if (!multiline) control.type = 'text';
    control.value = value;
    control.dataset.propertyId = prop.id;
    control.addEventListener('input', () => updateChange(prop, control.value));
    return control;
  }

  function createReadonlyControl(prop) {
    const value = prop.value ?? prop.preview ?? '';
    return textNode('div', 'component-property-readonly', value || '—');
  }

  function renderProperties(detail, filter = '') {
    const container = $('#component-property-list');
    if (!container) return;
    clearNode(container);
    const query = filter.trim().toLowerCase();
    const order = { geometry: 0, appearance: 1, data: 2, other: 3, reference: 4, structure: 5, binary: 6 };
    let properties = (detail.properties || []).filter((prop) => {
      if (!query) return true;
      return `${prop.name} ${prop.path} ${prop.preview} ${prop.value_type}`.toLowerCase().includes(query);
    });
    properties.sort((a, b) => {
      const category = order[categoryForProperty(a)] - order[categoryForProperty(b)];
      return category || a.path.localeCompare(b.path);
    });
    const total = properties.length;
    properties = properties.slice(0, PROPERTY_RENDER_LIMIT);
    properties.forEach((prop) => {
      const row = document.createElement('div');
      row.className = 'component-property-row';
      row.dataset.propertyId = prop.id;
      const meta = document.createElement('div');
      meta.className = 'component-property-meta';
      meta.append(textNode('strong', '', prop.name));
      meta.append(textNode('small', '', `${categoryForProperty(prop)} · ${prop.value_type} · ${prop.path}`));
      const badges = document.createElement('div');
      badges.className = 'component-property-badges';
      badges.append(textNode('span', `component-property-badge${prop.editable ? ' editable' : ''}`, prop.editable ? 'editable' : 'read only'));
      if (prop.reference_like) badges.append(textNode('span', 'component-property-badge reference', 'reference'));
      if (prop.binary) badges.append(textNode('span', 'component-property-badge binary', `binary ${prop.value_size}`));
      if (prop.structural) badges.append(textNode('span', 'component-property-badge', 'structural'));
      meta.append(badges);
      const control = document.createElement('div');
      control.className = 'component-property-control';
      control.append(prop.editable && !explorer.externalDirty ? createEditableControl(prop) : createReadonlyControl(prop));
      row.append(meta, control);
      container.append(row);
    });
    if (!properties.length) container.append(textNode('div', 'component-model-empty', '条件に一致するプロパティはありません。'));
    if (total > properties.length) container.append(textNode('div', 'component-model-empty', `表示上限 ${PROPERTY_RENDER_LIMIT} 件。検索で絞り込んでください。`));
    $('#component-property-count').textContent = `${total} / ${detail.properties.length}`;
  }

  function updateSavebar() {
    const count = explorer.changes.size;
    const note = $('#component-change-count');
    const save = $('#component-save');
    if (note) note.textContent = explorer.externalDirty
      ? 'メインXMLの未保存変更があります。先にXMLを保存してください。'
      : count ? `${count} プロパティ変更` : '変更なし';
    if (save) save.disabled = explorer.externalDirty || count === 0;
  }

  function renderGeometry(detail) {
    const section = $('#component-geometry-section');
    if (!section) return;
    const bounds = detail.bounds;
    section.hidden = !bounds;
    if (!bounds) return;
    const prop = (detail.properties || []).find((item) => item.id === bounds.property_id);
    if (!prop) {
      section.hidden = true;
      return;
    }
    const values = { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
    ['x', 'y', 'width', 'height'].forEach((key) => {
      const input = $(`#component-geometry-${key}`);
      input.value = String(values[key]);
      input.disabled = explorer.externalDirty || !prop.editable;
    });
    const sync = () => {
      const x = Number($('#component-geometry-x').value || 0);
      const y = Number($('#component-geometry-y').value || 0);
      const width = Number($('#component-geometry-width').value || 0);
      const height = Number($('#component-geometry-height').value || 0);
      updateChange(prop, `(${x}, ${y}, ${x + width}, ${y + height})`);
    };
    ['x', 'y', 'width', 'height'].forEach((key) => {
      const input = $(`#component-geometry-${key}`);
      input.oninput = sync;
    });
  }

  function renderRelationships(detail) {
    const container = $('#component-relationships');
    clearNode(container);
    const outbound = detail.relationships?.outbound || [];
    const inbound = detail.relationships?.inbound || [];
    const all = [
      ...outbound.map((relation) => ({ direction: 'out', ...relation })),
      ...inbound.map((relation) => ({ direction: 'in', ...relation })),
    ];
    $('#component-relationship-count').textContent = String(all.length);
    if (!all.length) {
      container.append(textNode('div', 'component-model-empty', '参照関係は検出されていません。'));
      return;
    }
    all.forEach((relation) => {
      const row = document.createElement('div');
      row.className = 'component-relation';
      row.append(textNode('span', '', relation.direction === 'out' ? 'outbound' : 'inbound'));
      const target = document.createElement('div');
      const label = `${relation.name || relation.type}: ${relation.target_key || relation.target_file || '—'}`;
      if (relation.target_component_id) target.append(buttonLink(label, () => void selectComponent(relation.target_component_id), relation.target_component_id));
      else target.append(textNode('span', '', `${label}${relation.resolved ? '' : ' (unresolved)'}`));
      row.append(target);
      container.append(row);
    });
  }

  function renderChildren(detail) {
    const container = $('#component-children');
    clearNode(container);
    const children = detail.children_detail || [];
    $('#component-child-count').textContent = String(children.length);
    if (!children.length) {
      container.append(textNode('div', 'component-model-empty', '子コンポーネントはありません。'));
      return;
    }
    children.forEach((child) => {
      const row = document.createElement('div');
      row.className = 'component-child';
      row.append(textNode('span', '', child.kind));
      const copy = document.createElement('div');
      copy.append(buttonLink(child.name || child.tag, () => void selectComponent(child.id), child.path));
      copy.append(textNode('span', 'component-secondary', `${child.class_name || child.tag} · ${child.property_count} props`));
      row.append(copy);
      container.append(row);
    });
  }

  function renderTreeNode(node, container, propertiesById, budget) {
    if (budget.remaining <= 0) return;
    budget.remaining -= 1;
    if (node.kind === 'component') {
      const row = document.createElement('div');
      row.className = 'component-tree-node';
      row.append(textNode('span', 'component-tree-kind', 'component'));
      row.append(buttonLink(`${node.tag} · ${node.name}`, () => void selectComponent(node.component_id), node.path));
      container.append(row);
      return;
    }
    if (node.kind === 'comment') {
      container.append(textNode('div', 'component-tree-node', `#comment ${node.preview || ''}`));
      return;
    }
    const children = Array.isArray(node.children) ? node.children : [];
    const attrProps = (node.attribute_property_ids || []).map((id) => propertiesById.get(id)).filter(Boolean);
    const textProp = node.text_property_id ? propertiesById.get(node.text_property_id) : null;
    const label = `${node.tag || 'node'}${attrProps.length ? ` @${attrProps.length}` : ''}${textProp ? ` = ${textProp.preview}` : ''}`;
    if (children.length) {
      const details = document.createElement('details');
      details.open = node.path?.split('/').length <= 5;
      const summary = document.createElement('summary');
      summary.append(textNode('span', 'component-tree-tag', label));
      summary.append(textNode('span', 'component-tree-kind', ` ${node.kind}`));
      details.append(summary);
      children.forEach((child) => renderTreeNode(child, details, propertiesById, budget));
      container.append(details);
    } else {
      const row = document.createElement('div');
      row.className = 'component-tree-node';
      row.append(textNode('span', 'component-tree-tag', label));
      row.append(textNode('span', 'component-tree-kind', node.kind));
      container.append(row);
    }
  }

  function renderTree(detail) {
    const container = $('#component-tree');
    clearNode(container);
    const propertiesById = new Map((detail.properties || []).map((prop) => [prop.id, prop]));
    const budget = { remaining: TREE_NODE_BUDGET };
    if (detail.property_tree) renderTreeNode(detail.property_tree, container, propertiesById, budget);
    if (budget.remaining <= 0) container.append(textNode('div', 'component-tree-cutoff', `DOM上限 ${TREE_NODE_BUDGET} ノードで省略しました。プロパティ検索を使用してください。`));
  }

  async function saveChanges() {
    if (!explorer.job || !explorer.detail || !explorer.changes.size || explorer.externalDirty) return;
    const button = $('#component-save');
    button.disabled = true;
    button.textContent = '保存中…';
    const selectedId = explorer.detail.id;
    try {
      const payload = await apiRequest(
        `/api/jobs/${encodeURIComponent(explorer.job.job_id)}/components/${encodeURIComponent(selectedId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_file_sha256: explorer.detail.file_sha256,
            updates: [...explorer.changes].map(([property_id, value]) => ({ property_id, value })),
          }),
        },
      );
      explorer.changes.clear();
      explorer.selectedId = selectedId;
      await renderJob(payload.job, { scroll: false });
      showToast(`${payload.updated_properties.length}件のプロパティをXMLデータセットへ保存しました。`, 'success');
    } catch (error) {
      showToast(`コンポーネント保存: ${describeError(error)}`, 'error', 10000);
      updateSavebar();
    } finally {
      button.textContent = '変更を保存';
    }
  }

  function inspectorMarkup() {
    return `
      <div id="component-breadcrumb" class="component-breadcrumb"></div>
      <dl class="component-identity">
        <div><dt>Name</dt><dd id="component-detail-name">—</dd></div>
        <div><dt>Kind</dt><dd id="component-detail-kind">—</dd></div>
        <div><dt>Class</dt><dd id="component-detail-class">—</dd></div>
        <div><dt>UID</dt><dd id="component-detail-uid">—</dd></div>
        <div><dt>XML file</dt><dd id="component-detail-file">—</dd></div>
        <div><dt>XML path</dt><dd id="component-detail-path">—</dd></div>
      </dl>
      <section id="component-geometry-section" class="component-section" hidden>
        <header><strong>Geometry</strong><span id="component-geometry-tag">bounds</span></header>
        <div class="component-geometry">
          <label>X<input id="component-geometry-x" type="number"></label>
          <label>Y<input id="component-geometry-y" type="number"></label>
          <label>W<input id="component-geometry-width" type="number"></label>
          <label>H<input id="component-geometry-height" type="number"></label>
        </div>
      </section>
      <section class="component-section">
        <header><strong>Properties</strong><span id="component-property-count">0</span></header>
        <div class="component-property-toolbar"><input id="component-property-filter" type="search" placeholder="プロパティ名・XMLパス・値で絞り込み"></div>
        <div id="component-property-list" class="component-property-list"></div>
      </section>
      <section class="component-section">
        <header><strong>Children</strong><span id="component-child-count">0</span></header>
        <div id="component-children" class="component-child-list"></div>
      </section>
      <section class="component-section">
        <header><strong>References</strong><span id="component-relationship-count">0</span></header>
        <div id="component-relationships" class="component-relationship-list"></div>
      </section>
      <section class="component-section">
        <header><strong>Full XML structure</strong><span>all fields</span></header>
        <div id="component-tree" class="component-tree"></div>
      </section>
      <div class="component-savebar">
        <span id="component-change-count">変更なし</span>
        <button id="component-save" class="primary-small button-reset" type="button" disabled>変更を保存</button>
      </div>`;
  }

  function renderInspector(detail) {
    explorer.detail = detail;
    explorer.changes.clear();
    explorer.elements.inspectorEmpty.hidden = true;
    explorer.elements.inspector.hidden = false;
    explorer.elements.inspector.innerHTML = inspectorMarkup();
    explorer.elements.inspectorCount.textContent = `${detail.properties.length} props`;
    $('#component-detail-name').textContent = detail.name || detail.tag || '—';
    $('#component-detail-kind').textContent = `${kindLabels[detail.kind] || detail.kind || '—'} / ${detail.role}`;
    $('#component-detail-class').textContent = detail.class_name || '—';
    $('#component-detail-uid').textContent = detail.uid || '—';
    $('#component-detail-file').textContent = detail.file;
    $('#component-detail-file').title = detail.file;
    $('#component-detail-path').textContent = detail.path;
    $('#component-detail-path').title = detail.path;
    const breadcrumb = $('#component-breadcrumb');
    (detail.breadcrumb || []).forEach((item, index, items) => {
      breadcrumb.append(buttonLink(item.name || item.tag, () => void selectComponent(item.id), item.tag));
      if (index < items.length - 1) breadcrumb.append(textNode('span', '', '›'));
    });
    renderGeometry(detail);
    renderProperties(detail, explorer.propertyFilter);
    renderChildren(detail);
    renderRelationships(detail);
    renderTree(detail);
    $('#component-property-filter').value = explorer.propertyFilter;
    let timer;
    $('#component-property-filter').addEventListener('input', (event) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        explorer.propertyFilter = event.target.value;
        renderProperties(detail, explorer.propertyFilter);
      }, 150);
    });
    $('#component-save').addEventListener('click', () => void saveChanges());
    updateSavebar();
  }

  async function selectComponent(componentId) {
    if (!explorer.job || !componentId) return;
    explorer.selectedId = componentId;
    $$('tr[data-component-id]').forEach((row) => row.classList.toggle('is-selected', row.dataset.componentId === componentId));
    explorer.elements.inspectorEmpty.hidden = false;
    explorer.elements.inspectorEmpty.textContent = 'コンポーネントを解析中…';
    explorer.elements.inspector.hidden = true;
    try {
      const detail = await apiRequest(`/api/jobs/${encodeURIComponent(explorer.job.job_id)}/components/${encodeURIComponent(componentId)}`);
      if (explorer.selectedId !== componentId) return;
      renderInspector(detail);
    } catch (error) {
      explorer.elements.inspectorEmpty.hidden = false;
      explorer.elements.inspectorEmpty.textContent = describeError(error);
      showToast(`コンポーネント詳細: ${describeError(error)}`, 'error', 10000);
    }
  }

  async function loadModel({ preserveSelection = true } = {}) {
    if (!explorer.job) return;
    const jobId = explorer.job.job_id;
    const selected = preserveSelection ? explorer.selectedId : null;
    const sequence = ++explorer.loadSequence;
    setState('全XML解析中');
    explorer.elements.refresh.disabled = true;
    explorer.elements.card.hidden = false;
    try {
      const payload = await apiRequest(`/api/jobs/${encodeURIComponent(jobId)}/model`);
      if (sequence !== explorer.loadSequence || explorer.job?.job_id !== jobId) return;
      explorer.model = payload;
      explorer.externalDirty = false;
      renderSummary(payload);
      populateFilters(payload);
      renderFiles(payload.files || []);
      setState('解析済み', 'is-ready');
      explorer.selectedId = selected;
      explorer.detail = null;
      await loadComponents();
      if (selected) await selectComponent(selected);
      else if (explorer.components.length) await selectComponent(explorer.components[0].id);
    } catch (error) {
      if (sequence !== explorer.loadSequence) return;
      setState('解析失敗', 'is-dirty');
      showWarning(describeError(error));
      renderComponents({ items: [], total: 0 });
      explorer.elements.inspectorEmpty.hidden = false;
      explorer.elements.inspectorEmpty.textContent = '構造モデルを作成できませんでした。';
      showToast(`構造解析: ${describeError(error)}`, 'error', 10000);
    } finally {
      explorer.elements.refresh.disabled = false;
    }
  }

  async function setJob(job) {
    const sameJob = explorer.job?.job_id === job?.job_id;
    explorer.job = job || null;
    explorer.elements.card.hidden = !job;
    if (!job) {
      clearJob();
      return;
    }
    await loadModel({ preserveSelection: sameJob });
  }

  async function onDatasetChanged(job) {
    explorer.job = job || explorer.job;
    explorer.externalDirty = false;
    await loadModel({ preserveSelection: true });
  }

  function markExternalDirty() {
    if (!explorer.job || explorer.externalDirty) return;
    explorer.externalDirty = true;
    explorer.changes.clear();
    setState('XML未保存', 'is-dirty');
    showWarning('メインXMLエディターに未保存の変更があります。構造プロパティを編集する前にXMLを保存してください。');
    if (explorer.detail) renderInspector(explorer.detail);
  }

  function clearJob() {
    explorer.loadSequence += 1;
    explorer.job = null;
    explorer.model = null;
    explorer.components = [];
    explorer.total = 0;
    explorer.offset = 0;
    explorer.selectedId = null;
    explorer.detail = null;
    explorer.changes.clear();
    explorer.externalDirty = false;
    if (explorer.elements.card) explorer.elements.card.hidden = true;
  }

  function initialize() {
    ensureStylesheet();
    createMarkup();
    cacheElements();
    let queryTimer;
    explorer.elements.query.addEventListener('input', () => {
      window.clearTimeout(queryTimer);
      queryTimer = window.setTimeout(() => {
        explorer.offset = 0;
        void loadComponents();
      }, 230);
    });
    explorer.elements.fileFilter.addEventListener('change', () => {
      explorer.offset = 0;
      renderFiles(explorer.model?.files || []);
      void loadComponents();
    });
    explorer.elements.kindFilter.addEventListener('change', () => {
      explorer.offset = 0;
      void loadComponents();
    });
    explorer.elements.clearFilter.addEventListener('click', () => {
      explorer.elements.query.value = '';
      explorer.elements.fileFilter.value = '';
      explorer.elements.kindFilter.value = '';
      explorer.offset = 0;
      renderFiles(explorer.model?.files || []);
      void loadComponents();
    });
    explorer.elements.refresh.addEventListener('click', () => void loadModel({ preserveSelection: true }));
    explorer.elements.prev.addEventListener('click', () => {
      explorer.offset = Math.max(0, explorer.offset - PAGE_SIZE);
      void loadComponents();
    });
    explorer.elements.next.addEventListener('click', () => {
      explorer.offset += PAGE_SIZE;
      void loadComponents();
    });
  }

  initialize();
  globalThis.viComponentExplorer = {
    setJob,
    clearJob,
    onDatasetChanged,
    markExternalDirty,
    refresh: () => loadModel({ preserveSelection: true }),
  };
})();
