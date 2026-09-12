'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: false,
    decorating: false,
    scheduled: false,
    observer: null,
  };

  const LEGACY_DECORATIONS = [
    '.vi-cluster-interior',
    '.vi-cluster-header',
    '.vi-cluster-count',
    '.vi-array-index',
    '.vi-array-viewport',
    '.vi-boolean-led',
    '.vi-boolean-shine',
    '.vi-numeric-spinner',
    '.vi-primitive-body',
    '.vi-structure-titlebar',
    '.vi-structure-title',
    '.vi-subvi-icon',
  ].join(',');

  const TYPE_COLORS = {
    numeric: '#d97706',
    boolean: '#16843c',
    string: '#d62479',
    path: '#008272',
    array: '#7a3db8',
    cluster: '#8a5a2b',
    refnum: '#0f6cbd',
    ring: '#6b69d6',
    table: '#8764b8',
    unknown: '#66717d',
  };

  const OPERATORS = {
    add: '+',
    subtract: '−',
    multiply: '×',
    divide: '÷',
    equal: '=',
    greater: '>',
    less: '<',
    and: '∧',
    or: '∨',
    xor: '⊕',
    not: '¬',
    select: '?',
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function svg(tag, className, attributes = {}) {
    const element = document.createElementNS(SVG_NS, tag);
    if (className) element.setAttribute('class', className);
    Object.entries(attributes).forEach(([name, value]) => {
      if (value != null) element.setAttribute(name, String(value));
    });
    return element;
  }

  function text(className, value, attributes = {}) {
    const element = svg('text', className, attributes);
    element.textContent = String(value ?? '');
    return element;
  }

  function finite(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function logicalBounds(item, index = 0) {
    const E = editor();
    return E?.effectiveBounds?.(item, index)
      || E?.getBounds?.(item, index)
      || item?.bounds
      || null;
  }

  function normalized(value) {
    return String(value || '').toLowerCase();
  }

  function dataType(item) {
    const direct = normalized(item?.data_type);
    if (TYPE_COLORS[direct]) return direct;
    const haystack = [
      item?.visual_kind,
      item?.kind,
      item?.class_name,
      item?.widget,
    ].filter(Boolean).join(' ').toLowerCase();
    for (const [type, tokens] of Object.entries({
      cluster: ['cluster', 'record', 'struct'],
      array: ['array', 'indarr'],
      boolean: ['boolean', 'bool', 'and', 'or', 'xor'],
      string: ['string', 'text', 'char'],
      path: ['path'],
      refnum: ['refnum', 'reference'],
      ring: ['ring', 'enum'],
      table: ['table'],
      numeric: [
        'numeric',
        'number',
        'stdnum',
        'slide',
        'knob',
        'add',
        'subtract',
        'multiply',
        'divide',
      ],
    })) {
      if (tokens.some((token) => haystack.includes(token))) return type;
    }
    return 'unknown';
  }

  function roleFor(item) {
    if (item?.category === 'terminal') return normalized(item.direction) || 'terminal';
    if (item?.surface === 'front-panel') {
      return item?.category === 'indicator' ? 'indicator' : 'control';
    }
    return 'node';
  }

  function visualKind(item) {
    if (item?.category === 'terminal') return 'terminal';
    const visual = normalized(item?.visual_kind);
    const kind = normalized(item?.kind);
    if (item?.surface === 'front-panel') {
      if ([
        'numeric',
        'boolean',
        'string',
        'path',
        'ring',
        'table',
        'array',
        'cluster',
      ].includes(visual)) return visual;
      const type = dataType(item);
      return TYPE_COLORS[type] ? type : 'front-generic';
    }
    if (visual === 'structure' || kind.includes('structure')) return 'structure';
    if (visual === 'subvi' || kind.includes('subvi')) return 'subvi';
    if (visual === 'constant' || kind.includes('constant')) return 'constant';
    if (kind === 'select') return 'select';
    if (['equal', 'greater', 'less'].includes(kind)) return 'compare';
    if (['and', 'or', 'xor', 'not'].includes(kind)) return 'logic';
    if (
      visual === 'arithmetic'
      || ['add', 'subtract', 'multiply', 'divide'].includes(kind)
    ) return 'arithmetic';
    if (visual === 'primitive') return 'primitive';
    if (visual === 'array' || visual === 'cluster') return visual;
    return 'node';
  }

  function displayValue(item, kind) {
    const candidates = [
      item?.display_value,
      item?.value,
      item?.default_value,
      item?.current_value,
    ];
    const direct = candidates.find((value) => value != null && value !== '');
    if (direct != null) return String(direct);
    if (kind === 'boolean') return item?.category === 'indicator' ? 'TRUE' : 'OFF';
    if (kind === 'string') return item?.category === 'indicator' ? 'status text' : 'text';
    if (kind === 'path') return item?.category === 'indicator' ? '/result/data' : '/path/to/file';
    if (kind === 'ring') return 'Item 0';
    if (kind === 'constant') return item?.symbol || '0';
    return item?.category === 'indicator' ? '0.00' : '0';
  }

  function geometryParent(group) {
    return group.querySelector(':scope > .vi-component-geometry') || group;
  }

  function insertSkin(group, skin) {
    const parent = geometryParent(group);
    if (parent !== group) {
      parent.append(skin);
      return;
    }
    const overlay = group.querySelector([
      ':scope > .vi-object-label',
      ':scope > .vi-terminal-caption',
      ':scope > .vi-resize-handle',
      ':scope > .vi-resize-hit-target',
      ':scope > .vi-component-hit-target',
      ':scope > title',
    ].join(','));
    group.insertBefore(skin, overlay || null);
  }

  function frame(skin, bounds, role, type, options = {}) {
    const width = Math.max(8, finite(bounds.width, 8));
    const height = Math.max(8, finite(bounds.height, 8));
    const radius = options.radius ?? Math.min(3, height * 0.12);
    skin.append(svg('rect', 'vi-skin-frame', {
      x: options.x ?? 0.75,
      y: options.y ?? 0.75,
      width: options.width ?? Math.max(1, width - 1.5),
      height: options.height ?? Math.max(1, height - 1.5),
      rx: radius,
      'data-role': role,
      'data-type': type,
    }));
    if (role === 'control' || role === 'indicator') {
      const accentWidth = clamp(width * 0.045, 2, 5);
      skin.append(svg('rect', 'vi-skin-role-accent', {
        x: role === 'control' ? 1.5 : width - accentWidth - 1.5,
        y: 2,
        width: accentWidth,
        height: Math.max(4, height - 4),
        rx: 1,
      }));
    }
  }

  function addTypeStripe(skin, width, height, type, side = 'bottom') {
    const stripe = clamp(Math.min(width, height) * 0.08, 1.5, 4);
    const attributes = side === 'left'
      ? { x: 1, y: 1, width: stripe, height: Math.max(2, height - 2) }
      : { x: 1, y: Math.max(1, height - stripe - 1), width: Math.max(2, width - 2), height: stripe };
    skin.append(svg('rect', 'vi-skin-type-stripe', {
      ...attributes,
      'data-type': type,
    }));
  }

  function addValueText(skin, value, width, height, className = '') {
    skin.append(text(
      `vi-skin-value ${className}`.trim(),
      value,
      {
        x: width - clamp(width * 0.12, 5, 12),
        y: height / 2 + clamp(height * 0.11, 3, 7),
        'text-anchor': 'end',
      },
    ));
  }

  function numericSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, role, type, { radius: 1.5 });
    const padding = clamp(Math.min(width, height) * 0.12, 3, 9);
    const spinnerWidth = role === 'control' ? clamp(width * 0.14, 8, 16) : 0;
    skin.append(svg('rect', 'vi-skin-display vi-skin-numeric-display', {
      x: padding,
      y: padding,
      width: Math.max(10, width - padding * 2 - spinnerWidth),
      height: Math.max(8, height - padding * 2),
      rx: 0.75,
    }));
    if (role === 'control') {
      const x = Math.max(padding, width - padding - spinnerWidth);
      const middle = height / 2;
      skin.append(
        svg('rect', 'vi-skin-spinner', {
          x,
          y: padding,
          width: spinnerWidth,
          height: Math.max(8, height - padding * 2),
          rx: 0.5,
        }),
        svg('path', 'vi-skin-detail vi-skin-spinner-arrow', {
          d: `M ${x + spinnerWidth * 0.22} ${middle - 2} L ${x + spinnerWidth * 0.5} ${padding + 3} L ${x + spinnerWidth * 0.78} ${middle - 2} Z`,
        }),
        svg('path', 'vi-skin-detail vi-skin-spinner-arrow', {
          d: `M ${x + spinnerWidth * 0.22} ${middle + 2} L ${x + spinnerWidth * 0.5} ${height - padding - 3} L ${x + spinnerWidth * 0.78} ${middle + 2} Z`,
        }),
      );
    } else {
      skin.append(svg('circle', 'vi-skin-indicator-dot', {
        cx: width - padding * 0.62,
        cy: padding * 0.7,
        r: clamp(padding * 0.22, 1.2, 2.4),
      }));
    }
    addValueText(skin, displayValue(item, 'numeric'), width - spinnerWidth, height, 'is-numeric');
    addTypeStripe(skin, width, height, type);
  }

  function booleanSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, role, type, { radius: Math.min(4, height * 0.18) });
    const size = clamp(Math.min(width, height) * 0.56, 12, 34);
    const cx = width / 2;
    const cy = height / 2;
    if (role === 'indicator') {
      skin.append(
        svg('circle', 'vi-skin-boolean-bezel', { cx, cy, r: size * 0.54 }),
        svg('circle', 'vi-skin-boolean-led', { cx, cy, r: size * 0.40 }),
        svg('circle', 'vi-skin-detail vi-skin-boolean-highlight', {
          cx: cx - size * 0.13,
          cy: cy - size * 0.14,
          r: size * 0.09,
        }),
      );
    } else {
      const trackWidth = Math.max(size * 1.4, Math.min(width - 8, 42));
      const trackHeight = Math.max(10, size * 0.62);
      const x = cx - trackWidth / 2;
      const y = cy - trackHeight / 2;
      skin.append(
        svg('rect', 'vi-skin-boolean-track', {
          x,
          y,
          width: trackWidth,
          height: trackHeight,
          rx: trackHeight / 2,
        }),
        svg('circle', 'vi-skin-boolean-thumb', {
          cx: x + trackHeight / 2,
          cy,
          r: trackHeight * 0.38,
        }),
        text('vi-skin-detail vi-skin-boolean-mark', '0', {
          x: x + trackHeight * 0.52,
          y: cy + 2.5,
          'text-anchor': 'middle',
        }),
        text('vi-skin-detail vi-skin-boolean-mark', '1', {
          x: x + trackWidth - trackHeight * 0.52,
          y: cy + 2.5,
          'text-anchor': 'middle',
        }),
      );
    }
    addTypeStripe(skin, width, height, type);
  }

  function stringSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, role, type, { radius: 1 });
    const padding = clamp(Math.min(width, height) * 0.11, 3, 8);
    skin.append(svg('rect', 'vi-skin-display vi-skin-string-display', {
      x: padding,
      y: padding,
      width: Math.max(10, width - padding * 2),
      height: Math.max(8, height - padding * 2),
      rx: 0.5,
    }));
    if (role === 'control') {
      skin.append(svg('path', 'vi-skin-detail vi-skin-caret', {
        d: `M ${padding + 4} ${padding + 4} V ${height - padding - 4}`,
      }));
    }
    const value = displayValue(item, 'string');
    skin.append(text('vi-skin-value vi-skin-string-value', value, {
      x: padding + (role === 'control' ? 8 : 4),
      y: height / 2 + 4,
      'text-anchor': 'start',
    }));
    addTypeStripe(skin, width, height, type);
  }

  function pathSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, role, type, { radius: 1 });
    const padding = clamp(Math.min(width, height) * 0.11, 3, 8);
    const iconSize = clamp(height - padding * 2, 10, 24);
    skin.append(svg('rect', 'vi-skin-display vi-skin-path-display', {
      x: padding,
      y: padding,
      width: Math.max(10, width - padding * 2),
      height: Math.max(8, height - padding * 2),
      rx: 0.5,
    }));
    skin.append(svg('path', 'vi-skin-path-folder', {
      d: [
        `M ${padding + 2} ${height / 2 - iconSize * 0.25}`,
        `H ${padding + iconSize * 0.42}`,
        `L ${padding + iconSize * 0.55} ${height / 2 - iconSize * 0.38}`,
        `H ${padding + iconSize - 1}`,
        `V ${height / 2 + iconSize * 0.34}`,
        `H ${padding + 2} Z`,
      ].join(' '),
    }));
    skin.append(text('vi-skin-value vi-skin-path-value', displayValue(item, 'path'), {
      x: padding + iconSize + 3,
      y: height / 2 + 3.5,
      'text-anchor': 'start',
    }));
    if (role === 'control') {
      skin.append(svg('rect', 'vi-skin-detail vi-skin-path-button', {
        x: width - padding - 8,
        y: height / 2 - 4,
        width: 8,
        height: 8,
        rx: 1,
      }));
    }
    addTypeStripe(skin, width, height, type);
  }

  function ringSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, role, type, { radius: 1 });
    const padding = clamp(Math.min(width, height) * 0.11, 3, 8);
    const arrowWidth = role === 'control' ? clamp(width * 0.15, 9, 16) : 0;
    skin.append(svg('rect', 'vi-skin-display vi-skin-ring-display', {
      x: padding,
      y: padding,
      width: Math.max(10, width - padding * 2 - arrowWidth),
      height: Math.max(8, height - padding * 2),
      rx: 0.5,
    }));
    skin.append(text('vi-skin-value vi-skin-ring-value', displayValue(item, 'ring'), {
      x: padding + 4,
      y: height / 2 + 3.5,
      'text-anchor': 'start',
    }));
    if (role === 'control') {
      const x = width - padding - arrowWidth;
      skin.append(
        svg('rect', 'vi-skin-ring-button', {
          x,
          y: padding,
          width: arrowWidth,
          height: Math.max(8, height - padding * 2),
        }),
        svg('path', 'vi-skin-detail vi-skin-ring-arrow', {
          d: `M ${x + 3} ${height / 2 - 2} H ${x + arrowWidth - 3} L ${x + arrowWidth / 2} ${height / 2 + 3} Z`,
        }),
      );
    }
    addTypeStripe(skin, width, height, type);
  }

  function tableSkin(skin, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, role, type, { radius: 1 });
    const padding = clamp(Math.min(width, height) * 0.08, 3, 7);
    const x = padding;
    const y = padding;
    const innerWidth = Math.max(12, width - padding * 2);
    const innerHeight = Math.max(10, height - padding * 2);
    skin.append(svg('rect', 'vi-skin-table-body', {
      x,
      y,
      width: innerWidth,
      height: innerHeight,
    }));
    const columns = [0.32, 0.66];
    columns.forEach((ratio) => {
      skin.append(svg('path', 'vi-skin-detail vi-skin-table-grid', {
        d: `M ${x + innerWidth * ratio} ${y} V ${y + innerHeight}`,
      }));
    });
    [0.28, 0.52, 0.76].forEach((ratio) => {
      skin.append(svg('path', 'vi-skin-detail vi-skin-table-grid', {
        d: `M ${x} ${y + innerHeight * ratio} H ${x + innerWidth}`,
      }));
    });
    skin.append(svg('rect', 'vi-skin-table-header', {
      x,
      y,
      width: innerWidth,
      height: innerHeight * 0.28,
    }));
    addTypeStripe(skin, width, height, type);
  }

  function arraySkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    skin.append(svg('rect', 'vi-skin-container-shadow', {
      x: 3,
      y: 3,
      width: Math.max(4, width - 3.5),
      height: Math.max(4, height - 3.5),
      rx: 1,
    }));
    frame(skin, bounds, role, type, { radius: 1 });
    const indexWidth = clamp(width * 0.20, 18, 36);
    const indexHeight = clamp(height * 0.16, 13, 20);
    skin.append(
      svg('rect', 'vi-skin-array-index', {
        x: 5,
        y: 5,
        width: indexWidth,
        height: indexHeight,
        rx: 0.5,
      }),
      text('vi-skin-detail vi-skin-array-index-value', '0', {
        x: 5 + indexWidth / 2,
        y: 5 + indexHeight / 2 + 3,
        'text-anchor': 'middle',
      }),
      svg('rect', 'vi-skin-array-viewport', {
        x: 5,
        y: 8 + indexHeight,
        width: Math.max(12, width - 10),
        height: Math.max(10, height - indexHeight - 13),
        rx: 0.5,
      }),
      svg('path', 'vi-skin-detail vi-skin-array-stack', {
        d: `M ${Math.max(8, width - 8)} ${12 + indexHeight} V ${Math.max(16, height - 8)} H ${Math.max(12, width - 14)}`,
      }),
    );
    addTypeStripe(skin, width, height, type, 'left');
    skin.dataset.childCount = String((item.child_object_ids || []).length);
  }

  function clusterSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    skin.append(svg('rect', 'vi-skin-container-shadow', {
      x: 3,
      y: 3,
      width: Math.max(4, width - 3.5),
      height: Math.max(4, height - 3.5),
      rx: 3,
    }));
    frame(skin, bounds, role, type, { radius: 3 });
    const titleWidth = clamp(String(item.name || 'Cluster').length * 5.5 + 18, 42, Math.max(42, width - 12));
    skin.append(
      svg('rect', 'vi-skin-cluster-titleplate', {
        x: 8,
        y: 2,
        width: titleWidth,
        height: clamp(height * 0.13, 12, 19),
        rx: 2,
      }),
      text('vi-skin-detail vi-skin-cluster-title', item.name || 'Cluster', {
        x: 13,
        y: clamp(height * 0.13, 12, 19) - 2,
      }),
      svg('rect', 'vi-skin-cluster-interior', {
        x: 6,
        y: clamp(height * 0.15, 15, 22),
        width: Math.max(12, width - 12),
        height: Math.max(10, height - clamp(height * 0.15, 15, 22) - 6),
        rx: 2,
      }),
      text('vi-skin-detail vi-skin-child-count', `${(item.child_object_ids || []).length}`, {
        x: Math.max(10, width - 9),
        y: 13,
        'text-anchor': 'end',
      }),
    );
    addTypeStripe(skin, width, height, type, 'left');
  }

  function frontGenericSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, role, type, { radius: 1.5 });
    const padding = clamp(Math.min(width, height) * 0.12, 3, 8);
    skin.append(svg('rect', 'vi-skin-display vi-skin-generic-display', {
      x: padding,
      y: padding,
      width: Math.max(10, width - padding * 2),
      height: Math.max(8, height - padding * 2),
      rx: 0.5,
    }));
    skin.append(text('vi-skin-value vi-skin-generic-value', displayValue(item, 'generic'), {
      x: width / 2,
      y: height / 2 + 4,
      'text-anchor': 'middle',
    }));
    addTypeStripe(skin, width, height, type);
  }

  function primitiveBodyPath(width, height, kind) {
    if (kind === 'select') {
      return `M 2 2 L ${width - 2} ${height / 2} L 2 ${height - 2} Z`;
    }
    if (kind === 'compare') {
      const shoulder = clamp(width * 0.18, 4, 9);
      return `M ${shoulder} 1 H ${width - shoulder} L ${width - 1} ${height / 2} L ${width - shoulder} ${height - 1} H ${shoulder} L 1 ${height / 2} Z`;
    }
    const shoulder = clamp(width * 0.24, 5, 11);
    return `M 1 2 H ${width - shoulder} L ${width - 1} ${height / 2} L ${width - shoulder} ${height - 2} H 1 L ${Math.min(7, shoulder)} ${height / 2} Z`;
  }

  function primitiveSkin(skin, item, bounds, kind, type) {
    const width = bounds.width;
    const height = bounds.height;
    skin.append(svg('path', 'vi-skin-frame vi-skin-primitive-body', {
      d: primitiveBodyPath(width, height, kind),
      'data-type': type,
    }));
    const symbol = OPERATORS[normalized(item.kind)] || item.symbol || 'ƒ';
    skin.append(text('vi-skin-symbol vi-skin-operator', symbol, {
      x: width / 2,
      y: height / 2 + clamp(height * 0.16, 4, 8),
      'text-anchor': 'middle',
    }));
    addTypeStripe(skin, width, height, type);
  }

  function constantSkin(skin, item, bounds, type) {
    const width = bounds.width;
    const height = bounds.height;
    const fold = clamp(Math.min(width, height) * 0.22, 4, 9);
    skin.append(svg('path', 'vi-skin-frame vi-skin-constant-body', {
      d: `M 1 1 H ${width - fold - 1} L ${width - 1} ${fold + 1} V ${height - 1} H 1 Z`,
      'data-type': type,
    }));
    skin.append(svg('path', 'vi-skin-detail vi-skin-constant-fold', {
      d: `M ${width - fold - 1} 1 V ${fold + 1} H ${width - 1}`,
    }));
    skin.append(text('vi-skin-value vi-skin-constant-value', displayValue(item, 'constant'), {
      x: width / 2,
      y: height / 2 + clamp(height * 0.13, 3, 6),
      'text-anchor': 'middle',
    }));
    addTypeStripe(skin, width, height, type);
  }

  function subviSkin(skin, item, bounds, type) {
    const width = bounds.width;
    const height = bounds.height;
    const inset = clamp(Math.min(width, height) * 0.12, 3, 7);
    frame(skin, bounds, 'node', type, { radius: 1 });
    skin.append(svg('rect', 'vi-skin-subvi-icon', {
      x: inset,
      y: inset,
      width: Math.max(8, width - inset * 2),
      height: Math.max(8, height - inset * 2),
      rx: 0.5,
    }));
    const innerWidth = Math.max(8, width - inset * 2);
    const innerHeight = Math.max(8, height - inset * 2);
    skin.append(
      svg('rect', 'vi-skin-subvi-cell is-a', {
        x: inset + 2,
        y: inset + 2,
        width: Math.max(2, innerWidth * 0.30),
        height: Math.max(2, innerHeight * 0.30),
      }),
      svg('rect', 'vi-skin-subvi-cell is-b', {
        x: inset + innerWidth * 0.58,
        y: inset + 2,
        width: Math.max(2, innerWidth * 0.28),
        height: Math.max(2, innerHeight * 0.30),
      }),
      svg('path', 'vi-skin-detail vi-skin-subvi-wave', {
        d: `M ${inset + 3} ${inset + innerHeight * 0.72} C ${inset + innerWidth * 0.28} ${inset + innerHeight * 0.36}, ${inset + innerWidth * 0.55} ${inset + innerHeight}, ${inset + innerWidth - 3} ${inset + innerHeight * 0.58}`,
      }),
      text('vi-skin-symbol vi-skin-subvi-text', 'VI', {
        x: width / 2,
        y: height / 2 + 4,
        'text-anchor': 'middle',
      }),
    );
    addTypeStripe(skin, width, height, type);
    skin.dataset.viName = item.name || '';
  }

  function structureSkin(skin, item, bounds, type) {
    const width = bounds.width;
    const height = bounds.height;
    const headerHeight = clamp(height * 0.08, 16, 24);
    const titleWidth = clamp(String(item.name || 'Structure').length * 6 + 24, 58, Math.max(58, width * 0.55));
    skin.append(
      svg('rect', 'vi-skin-structure-frame', {
        x: 1,
        y: 1,
        width: Math.max(4, width - 2),
        height: Math.max(4, height - 2),
      }),
      svg('rect', 'vi-skin-structure-titlebar', {
        x: 1,
        y: 1,
        width: Math.min(width - 2, titleWidth),
        height: headerHeight,
      }),
      text('vi-skin-structure-title', item.name || 'Structure', {
        x: 7,
        y: headerHeight - 5,
      }),
      svg('rect', 'vi-skin-structure-selector', {
        x: Math.max(4, width - 45),
        y: 3,
        width: 40,
        height: Math.max(10, headerHeight - 5),
        rx: 1,
      }),
      text('vi-skin-detail vi-skin-structure-frame-name', (
        item.active_frame_label
        || item.displayed_frame
        || item.structure_frames?.[item.active_frame_index || 0]?.name
        || '0'
      ), {
        x: Math.max(8, width - 25),
        y: headerHeight - 6,
        'text-anchor': 'middle',
      }),
      svg('rect', 'vi-skin-structure-interior', {
        x: 5,
        y: headerHeight + 3,
        width: Math.max(8, width - 10),
        height: Math.max(8, height - headerHeight - 8),
      }),
    );
    addTypeStripe(skin, width, height, type, 'left');
  }

  function nodeSkin(skin, item, bounds, type) {
    const width = bounds.width;
    const height = bounds.height;
    frame(skin, bounds, 'node', type, { radius: 2 });
    const headerHeight = clamp(height * 0.24, 8, 15);
    skin.append(svg('rect', 'vi-skin-node-header', {
      x: 1.5,
      y: 1.5,
      width: Math.max(4, width - 3),
      height: headerHeight,
      rx: 1,
    }));
    skin.append(text('vi-skin-symbol vi-skin-node-symbol', item.symbol || 'ƒ', {
      x: width / 2,
      y: height / 2 + clamp(height * 0.16, 4, 8),
      'text-anchor': 'middle',
    }));
    addTypeStripe(skin, width, height, type);
  }

  function terminalSkin(skin, item, bounds, role, type) {
    const width = bounds.width;
    const height = bounds.height;
    const size = Math.max(4, Math.min(width, height));
    const x = (width - size) / 2;
    const y = (height - size) / 2;
    skin.append(svg('rect', 'vi-skin-terminal-body', {
      x,
      y,
      width: size,
      height: size,
      rx: type === 'boolean' ? size * 0.18 : 0.5,
      'data-type': type,
      'data-direction': role,
    }));
    const inward = role === 'source';
    const centerX = width / 2;
    const centerY = height / 2;
    const half = size * 0.23;
    skin.append(svg('path', 'vi-skin-terminal-direction', {
      d: inward
        ? `M ${centerX - half} ${centerY - half} L ${centerX + half} ${centerY} L ${centerX - half} ${centerY + half} Z`
        : `M ${centerX + half} ${centerY - half} L ${centerX - half} ${centerY} L ${centerX + half} ${centerY + half} Z`,
    }));
  }

  function buildSkin(item, bounds, kind, role, type) {
    const skin = svg('g', `vi-component-skin vi-skin-${kind}`);
    skin.dataset.visualKind = kind;
    skin.dataset.componentRole = role;
    skin.dataset.dataType = type;
    skin.dataset.visualSignature = `${item.surface}:${role}:${kind}:${type}`;
    if (kind === 'numeric') numericSkin(skin, item, bounds, role, type);
    else if (kind === 'boolean') booleanSkin(skin, item, bounds, role, type);
    else if (kind === 'string') stringSkin(skin, item, bounds, role, type);
    else if (kind === 'path') pathSkin(skin, item, bounds, role, type);
    else if (kind === 'ring') ringSkin(skin, item, bounds, role, type);
    else if (kind === 'table') tableSkin(skin, bounds, role, type);
    else if (kind === 'array') arraySkin(skin, item, bounds, role, type);
    else if (kind === 'cluster') clusterSkin(skin, item, bounds, role, type);
    else if (kind === 'front-generic') frontGenericSkin(skin, item, bounds, role, type);
    else if (['arithmetic', 'primitive', 'compare', 'logic', 'select'].includes(kind)) {
      primitiveSkin(skin, item, bounds, kind, type);
    } else if (kind === 'constant') constantSkin(skin, item, bounds, type);
    else if (kind === 'subvi') subviSkin(skin, item, bounds, type);
    else if (kind === 'structure') structureSkin(skin, item, bounds, type);
    else if (kind === 'terminal') terminalSkin(skin, item, bounds, role, type);
    else nodeSkin(skin, item, bounds, type);
    return skin;
  }

  function clearVisualClasses(group) {
    [...group.classList]
      .filter((name) => (
        name.startsWith('is-component-visual-')
        || name.startsWith('is-component-role-')
        || name.startsWith('is-component-data-')
      ))
      .forEach((name) => group.classList.remove(name));
  }

  function decorateObject(group, item, index) {
    const bounds = logicalBounds(item, index);
    if (!bounds) return;
    const kind = visualKind(item);
    const role = roleFor(item);
    const type = dataType(item);
    group.querySelectorAll(LEGACY_DECORATIONS).forEach((element) => element.remove());
    group.querySelectorAll('.vi-component-skin').forEach((element) => element.remove());
    clearVisualClasses(group);
    group.classList.add(
      'has-component-visual-system',
      `is-component-visual-${kind}`,
      `is-component-role-${role}`,
      `is-component-data-${type}`,
    );
    group.dataset.componentVisual = kind;
    group.dataset.componentRole = role;
    group.dataset.componentDataType = type;
    group.dataset.componentVisualSignature = `${item.surface}:${role}:${kind}:${type}`;
    group.querySelector([
      '.vi-front-panel-body',
      '.vi-block-node-body',
      '.vi-terminal-body',
    ].join(','))?.classList.add('vi-semantic-body-anchor');
    insertSkin(group, buildSkin(item, bounds, kind, role, type));
  }

  function raiseTerminalLayers(root) {
    root.querySelectorAll(':scope > .vi-object.is-terminal').forEach((group) => {
      root.append(group);
    });
  }

  function decorate() {
    const S = state();
    const root = S?.el?.modelGraphSvg;
    if (!S?.vi || !root || runtime.decorating) return false;
    runtime.decorating = true;
    try {
      const index = new Map(
        [...S.objects.keys()].map((id, itemIndex) => [id, itemIndex]),
      );
      root.querySelectorAll('[data-object-id]').forEach((group) => {
        const item = S.objects.get(group.dataset.objectId);
        if (item) decorateObject(group, item, index.get(item.id) || 0);
      });
      raiseTerminalLayers(root);
      root.dataset.componentVisualSystem = 'semantic-v1';
      return true;
    } finally {
      runtime.decorating = false;
    }
  }

  function schedule() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      runtime.scheduled = false;
      decorate();
    });
  }

  function install() {
    const root = state()?.el?.modelGraphSvg;
    if (
      runtime.ready
      || !root
      || !editor()
      || !globalThis.VIRealism?.ready
    ) return false;
    runtime.ready = true;
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.decorating) return;
      if (mutations.some((mutation) => mutation.addedNodes.length || mutation.removedNodes.length)) {
        schedule();
      }
    });
    runtime.observer.observe(root, { childList: true });
    globalThis.VIComponentVisuals = {
      ready: true,
      runtime,
      decorate,
      schedule,
      visualKind,
      roleFor,
      dataType,
      buildSkin,
    };
    decorate();
    return true;
  }

  function waitForRealism(attempt = 0) {
    if (install()) return;
    if (attempt < 400) {
      setTimeout(() => waitForRealism(attempt + 1), 25);
      return;
    }
    globalThis.VIComponentVisuals = {
      ready: false,
      error: 'semantic component visual system did not become ready',
      runtime,
    };
  }

  globalThis.VIComponentVisuals = { ready: false, runtime };
  waitForRealism();
})();
