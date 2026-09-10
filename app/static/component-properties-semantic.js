'use strict';

(() => {
  const state = { ready: false, queued: false, decorating: false };

  function setText(element, value) {
    if (element && element.textContent !== value) element.textContent = value;
  }

  function detailsWrapper(className, summaryText) {
    const details = document.createElement('details');
    details.className = className;
    const summary = document.createElement('summary');
    summary.textContent = summaryText;
    details.append(summary);
    return details;
  }

  function decorateHeader(card) {
    setText(card.querySelector('#component-model-title'), 'VIオブジェクトのプロパティ');
    setText(
      card.querySelector('.component-model-head p'),
      'コントロール、インジケータ、ノード、端子として意味のある値を表示・編集します。XML構造と識別子はRAWデータへ分離しています。',
    );
    const headings = card.querySelectorAll('.component-pane-head strong');
    if (headings[0]) setText(headings[0], '解析ファイル');
    if (headings[1]) setText(headings[1], 'VIオブジェクト');
    if (headings[2]) setText(headings[2], 'プロパティ詳細');
  }

  function semanticIdentity(inspector, identity) {
    let semantic = inspector.querySelector('.component-semantic-identity');
    if (!semantic) {
      semantic = document.createElement('dl');
      semantic.className = 'component-semantic-identity';
      semantic.innerHTML = `
        <div><dt>オブジェクト</dt><dd data-semantic-name>—</dd></div>
        <div><dt>種類</dt><dd data-semantic-kind>—</dd></div>`;
      identity.before(semantic);
    }
    setText(
      semantic.querySelector('[data-semantic-name]'),
      inspector.querySelector('#component-detail-name')?.textContent || '—',
    );
    setText(
      semantic.querySelector('[data-semantic-kind]'),
      inspector.querySelector('#component-detail-kind')?.textContent || '—',
    );
  }

  function wrapIdentity(inspector) {
    const identity = inspector.querySelector('.component-identity');
    if (!identity || identity.closest('.component-raw-identity-details')) return;
    semanticIdentity(inspector, identity);
    const details = detailsWrapper(
      'component-raw-identity-details',
      'RAWデータ（class / UID / XML file / XML path）',
    );
    identity.before(details);
    details.append(identity);
  }

  function wrapXmlTree(inspector) {
    const section = [...inspector.querySelectorAll('.component-section')].find(
      (candidate) => candidate.querySelector('header strong')?.textContent === 'Full XML structure',
    );
    if (!section || section.closest('.component-raw-tree-details')) return;
    setText(section.querySelector('header strong'), 'XML構造');
    setText(section.querySelector('header span'), 'RAW');
    const details = detailsWrapper('component-raw-tree-details', 'RAW XML構造');
    section.before(details);
    details.append(section);
  }

  function splitRawProperties(inspector) {
    const list = inspector.querySelector('#component-property-list');
    if (!list) return;
    let details = inspector.querySelector('.component-raw-property-details');
    let body = details?.querySelector('.component-raw-property-body');
    if (!details) {
      details = detailsWrapper('component-raw-property-details', 'RAW・構造プロパティ');
      body = document.createElement('div');
      body.className = 'component-raw-property-body';
      details.append(body);
      list.after(details);
    }
    list.querySelectorAll('.component-property-row').forEach((row) => {
      const meta = row.querySelector('.component-property-meta small')?.textContent || '';
      const raw = /\b(reference|structure|binary)\b/i.test(meta);
      row.classList.toggle('is-raw-property', raw);
      if (raw) body.append(row);
    });
  }

  function boundsPropertyControl(inspector) {
    return [...inspector.querySelectorAll('.component-property-row')]
      .find((row) => /geometry\s*·\s*rect/i.test(
        row.querySelector('.component-property-meta small')?.textContent || '',
      ))
      ?.querySelector('[data-property-id]') || null;
  }

  function wireNativeGeometry(inspector) {
    const keys = ['x', 'y', 'width', 'height'];
    const inputs = Object.fromEntries(
      keys.map((key) => [key, inspector.querySelector(`#component-geometry-${key}`)]),
    );
    if (keys.some((key) => !inputs[key])) return;
    const target = boundsPropertyControl(inspector);
    if (!target) return;
    const row = target.closest('.component-property-row');
    const propertyName = row?.querySelector('.component-property-meta strong')?.textContent || '';
    const propertyPath = row?.querySelector('.component-property-meta small')?.textContent || '';
    const legacyOrder = /of[_\s-]*.*bounds/i.test(`${propertyName} ${propertyPath}`);
    const sync = () => {
      const x = Number(inputs.x.value || 0);
      const y = Number(inputs.y.value || 0);
      const width = Number(inputs.width.value || 0);
      const height = Number(inputs.height.value || 0);
      target.value = legacyOrder
        ? `(${x}, ${y}, ${x + width}, ${y + height})`
        : `(${y}, ${x}, ${y + height}, ${x + width})`;
      target.dispatchEvent(new Event('input', { bubbles: true }));
    };
    keys.forEach((key) => {
      inputs[key].oninput = sync;
      inputs[key].dataset.nativeGeometryOrder = legacyOrder
        ? 'left,top,right,bottom'
        : 'top,left,bottom,right';
    });
  }

  function renameSections(inspector) {
    inspector.querySelectorAll('.component-section > header').forEach((header) => {
      const strong = header.querySelector('strong');
      if (!strong) return;
      const labels = {
        Geometry: '配置とサイズ',
        Properties: '意味プロパティ',
        Children: '構成要素',
        References: '接続・参照',
      };
      if (labels[strong.textContent]) setText(strong, labels[strong.textContent]);
    });
  }

  function decorate() {
    if (state.decorating) return;
    const card = document.querySelector('#component-model-card');
    if (!card) return;
    state.decorating = true;
    try {
      decorateHeader(card);
      const inspector = card.querySelector('#component-inspector');
      if (inspector && !inspector.hidden) {
        renameSections(inspector);
        wrapIdentity(inspector);
        wrapXmlTree(inspector);
        splitRawProperties(inspector);
        wireNativeGeometry(inspector);
        inspector.dataset.semanticPropertyView = 'true';
      }
    } finally {
      state.decorating = false;
    }
  }

  function queue() {
    if (state.queued) return;
    state.queued = true;
    requestAnimationFrame(() => {
      state.queued = false;
      decorate();
    });
  }

  function install() {
    const card = document.querySelector('#component-model-card');
    if (state.ready || !card) return false;
    state.ready = true;
    new MutationObserver(queue).observe(card, { childList: true, subtree: true });
    queue();
    globalThis.VIPropertySemantics = { ready: true, decorate, state };
    return true;
  }

  function waitForExplorer(attempt = 0) {
    if (install()) return;
    if (attempt < 320) setTimeout(() => waitForExplorer(attempt + 1), 25);
  }

  globalThis.VIPropertySemantics = { ready: false, state };
  waitForExplorer();
})();
