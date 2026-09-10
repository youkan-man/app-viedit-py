'use strict';

(() => {
  const runtime = {
    ready: false,
    activeDefinitionId: null,
    definitionIds: [],
    queued: false,
  };

  function semanticState() {
    return globalThis.VISemanticEditor?.S;
  }

  function definitions() {
    const S = semanticState();
    return new Map(
      (S?.vi?.type_definitions || []).map((definition) => [definition.id, definition]),
    );
  }

  function selectedDefinitionIds() {
    const S = semanticState();
    if (!S?.selected) return [];
    const item = S.objects.get(S.selected);
    const wire = S.wires.get(S.selected);
    const ids = [];
    const add = (id) => {
      if (id && !ids.includes(id)) ids.push(id);
    };
    add(item?.type_definition_id);
    add(wire?.type_definition_id);
    (item?.terminal_ids || []).forEach((id) => add(S.objects.get(id)?.type_definition_id));
    (item?.linked_terminal_ids || []).forEach((id) => add(S.objects.get(id)?.type_definition_id));
    (item?.wire_ids || []).forEach((id) => add(S.wires.get(id)?.type_definition_id));
    return ids.filter((id) => definitions().has(id));
  }

  function text(tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = value == null || value === '' ? '—' : String(value);
    return element;
  }

  function ensurePanel() {
    let section = document.querySelector('#vi-type-definition-section');
    if (section) return section;
    section = document.createElement('section');
    section.id = 'vi-type-definition-section';
    section.className = 'vi-type-definition-section';
    section.hidden = true;
    section.innerHTML = `
      <div class="vi-type-definition-actions">
        <button id="vi-open-type-definition" type="button">タイプ定義を開く</button>
        <small id="vi-type-definition-summary"></small>
      </div>
      <div id="vi-type-definition-panel" class="vi-type-definition-panel" hidden>
        <header>
          <div>
            <strong id="vi-type-definition-title">タイプ定義</strong>
            <small id="vi-type-definition-meta"></small>
          </div>
          <button id="vi-type-definition-close" type="button" aria-label="タイプ定義を閉じる">×</button>
        </header>
        <div id="vi-type-definition-tabs" class="vi-type-definition-tabs" role="tablist"></div>
        <div id="vi-type-definition-tree" class="vi-type-definition-tree"></div>
      </div>`;
    const geometry = document.querySelector('#vi-geometry-editor');
    const inspector = document.querySelector('#model-inspector');
    inspector?.insertBefore(section, geometry || inspector.firstChild);
    section.querySelector('#vi-open-type-definition')?.addEventListener('click', () => {
      open(runtime.definitionIds[0]);
    });
    section.querySelector('#vi-type-definition-close')?.addEventListener('click', () => {
      section.querySelector('#vi-type-definition-panel').hidden = true;
      runtime.activeDefinitionId = null;
    });
    return section;
  }

  function kindLabel(kind) {
    const labels = {
      primitive: 'スカラー',
      cluster: 'クラスター',
      array: '配列',
      enum: '列挙型',
      ring: 'リング',
      typedef_ref: 'タイプ定義参照',
      class: 'LabVIEWクラス',
    };
    return labels[kind] || kind || '型未判定';
  }

  function renderValues(values) {
    const list = document.createElement('ol');
    list.className = 'vi-type-enum-values';
    values.forEach((value) => {
      const item = document.createElement('li');
      item.append(
        text('span', 'vi-type-enum-ordinal', value.value),
        text('strong', '', value.name),
      );
      if (value.description) item.append(text('small', '', value.description));
      list.append(item);
    });
    return list;
  }

  function renderType(type, depth = 0, fieldName = null) {
    const node = document.createElement('div');
    node.className = 'vi-type-node';
    node.dataset.depth = String(depth);
    const heading = document.createElement('div');
    heading.className = 'vi-type-node-heading';
    const copy = document.createElement('span');
    copy.append(
      text('strong', '', fieldName || type?.display || type?.name || '型'),
      text(
        'small',
        '',
        fieldName
          ? `${kindLabel(type?.kind)} · ${type?.display || type?.name || '型未判定'}`
          : kindLabel(type?.kind),
      ),
    );
    heading.append(text('i', `vi-type-kind is-${type?.kind || 'unknown'}`, type?.kind === 'cluster' ? '{}' : type?.kind === 'array' ? '[]' : 'T'), copy);
    node.append(heading);

    if (type?.typedef_name || type?.typedef_path || type?.classname || type?.ref_type) {
      const facts = document.createElement('dl');
      facts.className = 'vi-type-facts';
      [
        ['名前', type.typedef_name],
        ['記録パス', type.typedef_path],
        ['クラス', type.classname],
        ['参照種別', type.ref_type],
      ].filter(([, value]) => value).forEach(([name, value]) => {
        const row = document.createElement('div');
        row.append(text('dt', '', name), text('dd', '', value));
        facts.append(row);
      });
      node.append(facts);
    }

    if (type?.values?.length) node.append(renderValues(type.values));
    if (type?.element_type) {
      const children = document.createElement('div');
      children.className = 'vi-type-children';
      children.append(renderType(type.element_type, depth + 1, `要素型${type.dimensions ? ` (${type.dimensions}次元)` : ''}`));
      node.append(children);
    }
    if (type?.fields?.length) {
      const children = document.createElement('div');
      children.className = 'vi-type-children';
      type.fields.forEach((field) => {
        children.append(renderType(field.type || { kind: 'unknown', name: '型未判定' }, depth + 1, field.name));
      });
      node.append(children);
    }
    if (!type?.fields?.length && !type?.element_type && !type?.values?.length) {
      node.classList.add('is-leaf');
    }
    return node;
  }

  function renderTabs() {
    const container = document.querySelector('#vi-type-definition-tabs');
    if (!container) return;
    const byId = definitions();
    container.replaceChildren();
    runtime.definitionIds.forEach((id) => {
      const definition = byId.get(id);
      if (!definition) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.role = 'tab';
      button.dataset.definitionId = id;
      button.className = id === runtime.activeDefinitionId ? 'is-active' : '';
      button.setAttribute('aria-selected', String(id === runtime.activeDefinitionId));
      button.textContent = definition.name || kindLabel(definition.kind);
      button.addEventListener('click', () => open(id));
      container.append(button);
    });
    container.hidden = runtime.definitionIds.length < 2;
  }

  function renderDefinition(definition) {
    const title = document.querySelector('#vi-type-definition-title');
    const meta = document.querySelector('#vi-type-definition-meta');
    const tree = document.querySelector('#vi-type-definition-tree');
    if (!title || !meta || !tree) return;
    title.textContent = definition.name || 'タイプ定義';
    const location = definition.target_file || definition.recorded_path;
    meta.textContent = [
      kindLabel(definition.kind),
      location ? `参照先: ${location}` : null,
      definition.target_file ? 'データセット内' : definition.definition ? 'VI内に型情報あり' : '参照先未解決',
    ].filter(Boolean).join(' · ');
    tree.replaceChildren();
    if (definition.definition) {
      tree.append(renderType(definition.definition));
    } else {
      const empty = text(
        'div',
        'vi-type-definition-empty',
        location
          ? `このVIには参照名だけが保存されています。定義ファイル ${location} を同じデータセットに含めると展開できます。`
          : 'このVIには参照名だけが保存されており、定義本体を解決できませんでした。',
      );
      tree.append(empty);
    }
  }

  function open(id) {
    const definition = definitions().get(id);
    if (!definition) return;
    const section = ensurePanel();
    runtime.activeDefinitionId = id;
    section.hidden = false;
    const panel = section.querySelector('#vi-type-definition-panel');
    panel.hidden = false;
    renderTabs();
    renderDefinition(definition);
    panel.scrollIntoView({ block: 'nearest' });
  }

  function update() {
    const section = ensurePanel();
    const ids = selectedDefinitionIds();
    runtime.definitionIds = ids;
    section.hidden = !ids.length;
    const button = section.querySelector('#vi-open-type-definition');
    const summary = section.querySelector('#vi-type-definition-summary');
    if (button) {
      button.disabled = !ids.length;
      button.textContent = ids.length > 1 ? `タイプ定義を開く (${ids.length})` : 'タイプ定義を開く';
    }
    if (summary) {
      const byId = definitions();
      summary.textContent = ids.map((id) => byId.get(id)?.name).filter(Boolean).join(' / ');
    }
    if (runtime.activeDefinitionId && !ids.includes(runtime.activeDefinitionId)) {
      section.querySelector('#vi-type-definition-panel').hidden = true;
      runtime.activeDefinitionId = null;
    }
  }

  function queue() {
    if (runtime.queued) return;
    runtime.queued = true;
    requestAnimationFrame(() => {
      runtime.queued = false;
      update();
    });
  }

  function install() {
    const inspector = document.querySelector('#model-inspector');
    const root = document.querySelector('#model-graph-svg');
    if (runtime.ready || !inspector || !root) return false;
    runtime.ready = true;
    ensurePanel();
    new MutationObserver(queue).observe(inspector, { childList: true, subtree: true });
    new MutationObserver(queue).observe(root, { childList: true, subtree: true });
    document.querySelector('#vi-object-list')?.addEventListener('click', queue);
    root.addEventListener('click', queue);
    root.addEventListener('dblclick', queue);
    queue();
    globalThis.VITypeDefinitions = {
      ready: true,
      runtime,
      open,
      update,
      selectedDefinitionIds,
    };
    return true;
  }

  function waitForInspector(attempt = 0) {
    if (install()) return;
    if (attempt < 320) setTimeout(() => waitForInspector(attempt + 1), 25);
  }

  globalThis.VITypeDefinitions = { ready: false, runtime };
  waitForInspector();
})();
