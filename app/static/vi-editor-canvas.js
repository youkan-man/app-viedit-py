'use strict';

(() => {
  const E = globalThis.VISemanticEditor;
  const {
    S,
    SURFACES,
    label,
    html,
    svg,
    boundsText,
    snap,
    number,
    revisionFor,
  } = E;

  function clamp(value, minimum = 0, maximum = 1) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function fallbackBounds(item, index = 0) {
    if (!S.fallback.has(item.id)) {
      S.fallback.set(item.id, {
        x: 40 + (index % 4) * 160,
        y: 45 + Math.floor(index / 4) * 86,
        width: item.category === 'terminal' ? 10 : 124,
        height: item.category === 'terminal' ? 10 : 44,
        generated: true,
      });
    }
    return { ...S.fallback.get(item.id) };
  }

  function effectiveBounds(item, index = 0, stack = new Set()) {
    if (!item) return null;
    const local = S.local.get(item.id);
    if (local) return { ...local };
    if (!item.bounds) return fallbackBounds(item, index);

    const bounds = {
      x: number(item.bounds.x),
      y: number(item.bounds.y),
      width: Math.max(4, number(item.bounds.width, 40)),
      height: Math.max(4, number(item.bounds.height, 24)),
    };
    const ownerId = item.bounds.relative_to_object_id;
    if (!ownerId || stack.has(ownerId)) return bounds;

    const owner = S.objects.get(ownerId);
    if (!owner?.bounds) return bounds;
    const nextStack = new Set(stack);
    nextStack.add(item.id);
    const ownerBounds = effectiveBounds(owner, index, nextStack);
    if (!ownerBounds) return bounds;

    const originalOwner = owner.bounds;
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
    let anchorX = clamp(number(item.bounds.anchor_x, rawX / originalWidth));
    let anchorY = clamp(number(item.bounds.anchor_y, rawY / originalHeight));

    if (item.direction === 'source' && rawX >= originalWidth * 0.6) anchorX = 1;
    if (item.direction === 'sink' && rawX <= originalWidth * 0.4) anchorX = 0;
    if (rawY <= originalHeight * 0.2) anchorY = 0;
    if (rawY >= originalHeight * 0.8) anchorY = 1;

    return {
      x: ownerBounds.x + rawX + (ownerBounds.width - originalWidth) * anchorX,
      y: ownerBounds.y + rawY + (ownerBounds.height - originalHeight) * anchorY,
      width: bounds.width,
      height: bounds.height,
      relative_to_object_id: ownerId,
      anchor_x: anchorX,
      anchor_y: anchorY,
    };
  }

  function centerOf(item, index) {
    const bounds = effectiveBounds(item, index.get(item?.id) || 0);
    return bounds
      ? { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 }
      : null;
  }

  function endpointPoint(terminalId, objectId, index) {
    const item = S.objects.get(terminalId) || S.objects.get(objectId);
    return centerOf(item, index);
  }

  function distance(first, second) {
    if (!first || !second) return Number.POSITIVE_INFINITY;
    return Math.hypot(first.x - second.x, first.y - second.y);
  }

  function cleanRoutePoints(wire) {
    return (wire.route_points || [])
      .map((point) => ({ x: number(point?.x, NaN), y: number(point?.y, NaN) }))
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  }

  function orientRoute(points, source, target) {
    if (points.length < 2) return points;
    const forward = distance(points[0], source) + distance(points.at(-1), target);
    const reversed = distance(points.at(-1), source) + distance(points[0], target);
    return reversed < forward ? [...points].reverse() : points;
  }

  function compressPoints(points) {
    const unique = [];
    points.forEach((point) => {
      const previous = unique.at(-1);
      if (!previous || distance(previous, point) > 0.01) unique.push(point);
    });
    if (unique.length < 3) return unique;

    const compressed = [unique[0]];
    for (let index = 1; index < unique.length - 1; index += 1) {
      const previous = compressed.at(-1);
      const current = unique[index];
      const next = unique[index + 1];
      const sameX = Math.abs(previous.x - current.x) < 0.01
        && Math.abs(current.x - next.x) < 0.01;
      const sameY = Math.abs(previous.y - current.y) < 0.01
        && Math.abs(current.y - next.y) < 0.01;
      if (!sameX && !sameY) compressed.push(current);
    }
    compressed.push(unique.at(-1));
    return compressed;
  }

  function automaticRoute(source, target) {
    if (!source || !target) return [];
    const middle = source.x + (target.x - source.x) / 2;
    return compressPoints([
      source,
      { x: middle, y: source.y },
      { x: middle, y: target.y },
      target,
    ]);
  }

  function routedPoints(wire, targetTerminalId, targetObjectId, index) {
    const source = endpointPoint(
      wire.source_terminal_id,
      wire.source_object_id,
      index,
    );
    const target = endpointPoint(targetTerminalId, targetObjectId, index);
    if (!source || !target) {
      return { source: 'unresolved', points: [], bends: [] };
    }

    const nativePoints = orientRoute(cleanRoutePoints(wire), source, target);
    if (!nativePoints.length) {
      const points = automaticRoute(source, target);
      return { source: 'automatic', points, bends: points.slice(1, -1) };
    }

    const threshold = 12;
    const bends = [...nativePoints];
    if (distance(bends[0], source) <= threshold) bends.shift();
    if (bends.length && distance(bends.at(-1), target) <= threshold) bends.pop();
    const points = compressPoints([source, ...bends, target]);
    return { source: 'native', points, bends: points.slice(1, -1) };
  }

  function pathFromPoints(points) {
    if (!points.length) return '';
    const commands = [`M ${points[0].x} ${points[0].y}`];
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      if (Math.abs(previous.y - current.y) < 0.01) {
        commands.push(`H ${current.x}`);
      } else if (Math.abs(previous.x - current.x) < 0.01) {
        commands.push(`V ${current.y}`);
      } else {
        commands.push(`L ${current.x} ${current.y}`);
      }
    }
    return commands.join(' ');
  }

  function relatedIds() {
    const ids = new Set([S.selected]);
    const selectedWire = S.wires.get(S.selected);
    const selectedObject = S.objects.get(S.selected);
    if (selectedWire) {
      [
        selectedWire.source_object_id,
        ...(selectedWire.target_object_ids || []),
        ...(selectedWire.terminal_ids || []),
      ].filter(Boolean).forEach((id) => ids.add(id));
    }
    if (selectedObject) {
      (selectedObject.wire_ids || []).forEach((id) => {
        ids.add(id);
        const wire = S.wires.get(id);
        [
          wire?.source_object_id,
          ...(wire?.target_object_ids || []),
          ...(wire?.terminal_ids || []),
        ].filter(Boolean).forEach((target) => ids.add(target));
      });
      [
        selectedObject.owner_object_id,
        selectedObject.linked_object_id,
        ...(selectedObject.linked_terminal_ids || []),
        ...(selectedObject.terminal_ids || []),
      ].filter(Boolean).forEach((id) => ids.add(id));
    }
    return ids;
  }

  function wireDestinations(wire) {
    if (wire.target_terminal_ids?.length) {
      return wire.target_terminal_ids.map((terminalId, index) => ({
        terminalId,
        objectId: wire.target_object_ids?.[index] || null,
      }));
    }
    return (wire.target_object_ids || []).map((objectId) => ({
      terminalId: null,
      objectId,
    }));
  }

  function drawWire(root, wire, index, related) {
    wireDestinations(wire).forEach(({ terminalId, objectId }, branchIndex) => {
      const route = routedPoints(wire, terminalId, objectId, index);
      const path = pathFromPoints(route.points);
      if (!path) return;
      const group = svg('g', {
        class: `vi-wire-group${S.selected === wire.id ? ' is-selected' : ''}${wire.resolved ? '' : ' is-unresolved'}${related.has(wire.id) ? ' is-related' : ''}`,
        'data-wire-id': wire.id,
        'data-route-source': route.source,
        'data-route-point-count': route.points.length,
        'data-target-terminal-id': terminalId || '',
        'data-branch-index': branchIndex,
        tabindex: 0,
        role: 'button',
        'aria-label': `${E.wireName(wire)}、${route.source === 'native' ? '保存済み経路' : '自動経路'}`,
      });
      group.append(
        svg('path', { d: path, class: 'model-edge vi-wire-hit' }),
        svg('path', { d: path, class: 'model-edge vi-wire' }),
      );
      if (S.selected === wire.id && route.source === 'native') {
        route.bends.forEach((bend) => {
          group.append(svg('circle', {
            class: 'vi-wire-bend',
            cx: bend.x,
            cy: bend.y,
            r: 3.5,
            fill: '#ffffff',
            stroke: '#0067b8',
            'stroke-width': 1.4,
            'vector-effect': 'non-scaling-stroke',
            'pointer-events': 'none',
          }));
        });
      }
      group.addEventListener('click', (event) => {
        event.stopPropagation();
        E.select(wire.id);
      });
      group.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          E.select(wire.id);
        }
      });
      group.append(svg('title'));
      group.querySelector('title').textContent = `${E.wireName(wire)}\n${route.source === 'native' ? 'VI保存経路' : '自動経路'}`;
      root.append(group);
    });
  }

  function counterpartId(item) {
    if (!item) return null;
    if (item.surface === 'front-panel') {
      return (item.linked_terminal_ids || []).find((id) => S.objects.has(id)) || null;
    }
    if (item.category === 'terminal' && item.linked_object_id) {
      return S.objects.has(item.linked_object_id) ? item.linked_object_id : null;
    }
    return null;
  }

  function activateCounterpart(item, event) {
    const targetId = counterpartId(item);
    if (!targetId) return;
    event.preventDefault();
    event.stopPropagation();
    E.select(targetId, true);
  }

  function drawObject(root, item, index, related) {
    const bounds = effectiveBounds(item, index);
    const selected = S.selected === item.id;
    const counterpart = counterpartId(item);
    const group = svg('g', {
      class: `model-node vi-object ${E.typeClass(item)}${selected ? ' is-selected' : ''}${related.has(item.id) ? ' is-related' : ''}${S.dirty.has(item.id) ? ' is-dirty' : ''}${counterpart ? ' has-counterpart' : ''}`,
      'data-model-id': item.id,
      'data-object-id': item.id,
      'data-counterpart-id': counterpart || '',
      transform: `translate(${bounds.x} ${bounds.y})`,
      tabindex: 0,
      role: 'button',
      'aria-label': `${item.name}、${label(item)}${counterpart ? '、ダブルクリックで対応部品へ移動' : ''}`,
    });
    if (item.category === 'terminal') {
      group.append(svg('rect', {
        class: 'vi-terminal-body',
        x: 0,
        y: 0,
        width: bounds.width,
        height: bounds.height,
        rx: 1,
      }));
    } else if (item.surface === 'front-panel') {
      group.append(
        svg('rect', {
          class: 'vi-front-panel-shadow',
          x: 2,
          y: 3,
          width: bounds.width,
          height: bounds.height,
          rx: 2,
        }),
        svg('rect', {
          class: 'vi-front-panel-body',
          x: 0,
          y: 0,
          width: bounds.width,
          height: bounds.height,
          rx: 2,
        }),
        svg('rect', {
          class: 'vi-control-display',
          x: 8,
          y: Math.max(13, bounds.height / 2 - 8),
          width: Math.max(24, bounds.width - 16),
          height: Math.min(20, Math.max(14, bounds.height - 18)),
          rx: 1,
        }),
      );
      const value = svg('text', {
        class: 'vi-control-value',
        x: bounds.width - 13,
        y: Math.max(27, bounds.height / 2 + 5),
        'text-anchor': 'end',
      });
      value.textContent = item.category === 'indicator' ? '0.00' : '0';
      group.append(value);
    } else {
      group.append(svg('rect', {
        class: 'vi-block-node-body',
        x: 0,
        y: 0,
        width: bounds.width,
        height: bounds.height,
        rx: item.kind === 'structure' ? 0 : 3,
      }));
      const symbol = svg('text', {
        class: `vi-node-symbol is-${item.kind}`,
        x: bounds.width / 2,
        y: bounds.height / 2 + 7,
        'text-anchor': 'middle',
      });
      symbol.textContent = item.symbol || '◇';
      group.append(symbol);
    }
    if (S.showLabels && item.category !== 'terminal') {
      const text = svg('text', { class: 'vi-object-label', x: 0, y: -7 });
      text.textContent = item.name;
      group.append(text);
    }
    if (selected && item.resizable && item.category !== 'terminal') {
      group.append(svg('rect', {
        class: 'vi-resize-handle',
        x: bounds.width - 7,
        y: bounds.height - 7,
        width: 14,
        height: 14,
        'data-resize': 'true',
      }));
    }
    const title = svg('title');
    title.textContent = `${item.name}\n${label(item)}\n${boundsText(bounds)}${counterpart ? '\nダブルクリック: 対応部品へ移動' : ''}`;
    group.append(title);
    group.addEventListener('click', (event) => {
      event.stopPropagation();
      E.select(item.id);
    });
    group.addEventListener('dblclick', (event) => activateCounterpart(item, event));
    group.addEventListener('pointerdown', (event) => startObject(event, item));
    group.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && counterpart) {
        activateCounterpart(item, event);
        return;
      }
      keyMove(event, item);
    });
    root.append(group);
  }

  function routeFitPoints() {
    if (S.surface !== 'block-diagram') return [];
    return [...S.wires.values()].flatMap((wire) => cleanRoutePoints(wire));
  }

  function updateView(items, force) {
    const boxes = items
      .map((item, index) => effectiveBounds(item, index))
      .filter(Boolean);
    const routePoints = routeFitPoints();
    if (!boxes.length && !routePoints.length) {
      S.fitBox = { x: 0, y: 0, width: 640, height: 420 };
      if (!S.box || force) applyBox(S.fitBox);
      return;
    }
    const xs = [
      ...boxes.flatMap((bounds) => [bounds.x, bounds.x + bounds.width]),
      ...routePoints.map((point) => point.x),
    ];
    const ys = [
      ...boxes.flatMap((bounds) => [bounds.y, bounds.y + bounds.height]),
      ...routePoints.map((point) => point.y),
    ];
    const left = Math.min(...xs);
    const top = Math.min(...ys);
    const right = Math.max(...xs);
    const bottom = Math.max(...ys);
    S.fitBox = {
      x: left - 80,
      y: top - 70,
      width: Math.max(320, right - left + 160),
      height: Math.max(240, bottom - top + 140),
    };
    if (!S.box || force) applyBox(S.fitBox);
  }

  function applyBox(box) {
    S.box = { ...box };
    S.el.modelGraphSvg.setAttribute(
      'viewBox',
      `${box.x} ${box.y} ${box.width} ${box.height}`,
    );
  }

  function fitGraph() {
    if (S.fitBox) applyBox(S.fitBox);
  }

  function zoom(factor, clientX = null, clientY = null) {
    if (!S.box) return;
    const rect = S.el.modelGraphViewport.getBoundingClientRect();
    const px = clientX == null ? 0.5 : (clientX - rect.left) / rect.width;
    const py = clientY == null ? 0.5 : (clientY - rect.top) / rect.height;
    const width = S.box.width * factor;
    const height = S.box.height * factor;
    applyBox({
      x: S.box.x + (S.box.width - width) * px,
      y: S.box.y + (S.box.height - height) * py,
      width,
      height,
    });
  }

  function renderCanvas(fit = false) {
    const items = E.surfaceObjects();
    const shown = items.filter(E.visible);
    const index = new Map(items.map((item, itemIndex) => [item.id, itemIndex]));
    const related = relatedIds();
    const root = S.el.modelGraphSvg;
    root.replaceChildren();
    const defs = svg('defs');
    const pattern = svg('pattern', {
      id: 'vi-grid',
      width: S.grid,
      height: S.grid,
      patternUnits: 'userSpaceOnUse',
    });
    pattern.append(svg('path', {
      d: `M ${S.grid} 0 L 0 0 0 ${S.grid}`,
      class: 'vi-grid-line',
    }));
    defs.append(pattern);
    root.append(defs);
    root.append(svg('rect', {
      x: -10000,
      y: -10000,
      width: 20000,
      height: 20000,
      class: 'vi-canvas-background',
      fill: 'url(#vi-grid)',
    }));
    if (S.surface === 'block-diagram') {
      [...S.wires.values()].forEach((wire) => drawWire(root, wire, index, related));
    }
    shown.forEach((item, itemIndex) => {
      drawObject(root, item, index.get(item.id) ?? itemIndex, related);
    });
    updateView(items, fit);
    const hasContent = Boolean(
      shown.length || (S.surface === 'block-diagram' && S.wires.size),
    );
    S.el.modelGraphEmpty.hidden = hasContent;
    if (!hasContent) {
      S.el.modelGraphEmpty.querySelector('strong').textContent = `${SURFACES[S.surface]}に表示対象がありません`;
      S.el.modelGraphEmpty.querySelector('span').textContent = '解析元のXML情報は下のデバッグ欄で確認できます。';
    }
    S.el.viSelectionStatus.textContent = S.selected
      ? (S.objects.get(S.selected)?.name || E.wireName(S.wires.get(S.selected)))
      : '選択なし';
    S.el.viCoordinateStatus.textContent = boundsText(
      effectiveBounds(S.objects.get(S.selected)),
    );
  }

  function linkedInspectorIds(item, wire) {
    const links = [];
    if (wire) {
      [
        wire.source_object_id,
        ...(wire.target_object_ids || []),
        ...(wire.terminal_ids || []),
      ].filter(Boolean).forEach((id) => links.push(id));
    }
    if (item) {
      [
        item.owner_object_id,
        item.linked_object_id,
        ...(item.terminal_ids || []),
        ...(item.linked_terminal_ids || []),
        ...(item.wire_ids || []),
      ].filter(Boolean).forEach((id) => links.push(id));
    }
    return [...new Set(links)].filter((id) => id !== S.selected);
  }

  function renderInspector() {
    const item = S.objects.get(S.selected);
    const wire = S.wires.get(S.selected);
    const record = item || wire;
    S.el.modelInspectorEmpty.hidden = Boolean(record);
    S.el.modelInspector.hidden = !record;
    if (!record) return;
    S.el.modelSelectionKind.textContent = wire ? '配線' : label(item);
    S.el.modelInspectorName.textContent = wire ? E.wireName(wire) : item.name;
    S.el.modelInspectorClass.textContent = wire
      ? 'wire'
      : item.class_name || label(item);
    S.el.modelInspectorUid.textContent = wire ? wire.id : item.uid || '—';
    S.el.modelInspectorFile.textContent = item?.source?.file || '—';
    S.el.modelInspectorPath.textContent = item?.source?.xml_path || '意味モデル';
    const bounds = effectiveBounds(item);
    const editable = Boolean(item && item.movable && item.bounds?.source_property_id);
    S.el.modelInspectorPosition.textContent = boundsText(bounds);
    S.el.viEditability.textContent = editable ? '編集可能' : '読み取り専用';
    [
      S.el.viGeometryX,
      S.el.viGeometryY,
      S.el.viGeometryWidth,
      S.el.viGeometryHeight,
    ].forEach((input) => {
      input.disabled = !editable;
    });
    if (bounds) {
      S.el.viGeometryX.value = Math.round(bounds.x);
      S.el.viGeometryY.value = Math.round(bounds.y);
      S.el.viGeometryWidth.value = Math.round(bounds.width);
      S.el.viGeometryHeight.value = Math.round(bounds.height);
    } else {
      [
        S.el.viGeometryX,
        S.el.viGeometryY,
        S.el.viGeometryWidth,
        S.el.viGeometryHeight,
      ].forEach((input) => {
        input.value = '';
      });
    }
    const counterpart = counterpartId(item);
    S.el.viGeometryHint.textContent = editable
      ? counterpart
        ? 'キャンバス上で編集できます。ダブルクリックで対応部品へ移動します。'
        : 'キャンバス上でも移動・リサイズできます。'
      : counterpart
        ? 'ダブルクリックで対応する画面の部品へ移動します。'
        : '保存可能な位置プロパティがありません。';

    const links = linkedInspectorIds(item, wire);
    S.el.modelInspectorConnectionCount.textContent = links.length;
    S.el.modelInspectorConnections.replaceChildren(...(
      links.length
        ? links.map((id) => {
          const target = S.objects.get(id) || S.wires.get(id);
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'vi-connection-button';
          button.textContent = S.wires.has(id)
            ? E.wireName(target)
            : `${target?.name || id} · ${label(target)}`;
          button.addEventListener('click', () => E.select(id, true));
          return button;
        })
        : [html('div', 'context-empty', '接続なし')]
    ));
  }

  function updateGeometry() {
    const item = S.objects.get(S.selected);
    if (!item?.movable) return;
    const old = effectiveBounds(item);
    const next = {
      x: snap(number(S.el.viGeometryX.value, old.x)),
      y: snap(number(S.el.viGeometryY.value, old.y)),
      width: Math.max(16, snap(number(S.el.viGeometryWidth.value, old.width))),
      height: Math.max(16, snap(number(S.el.viGeometryHeight.value, old.height))),
    };
    S.local.set(item.id, next);
    S.dirty.add(item.id);
    renderCanvas();
    renderInspector();
    saveState();
  }

  function startObject(event, item) {
    if (event.button !== 0) return;
    event.stopPropagation();
    E.select(item.id);
    if (!item.movable) return;
    S.interaction = {
      id: item.id,
      mode: event.target.dataset.resize ? 'resize' : 'move',
      pointer: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      start: { ...effectiveBounds(item) },
    };
    S.el.modelGraphSvg.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function worldDelta(event) {
    const rect = S.el.modelGraphSvg.getBoundingClientRect();
    return {
      x: (event.clientX - S.interaction.startX) * S.box.width / rect.width,
      y: (event.clientY - S.interaction.startY) * S.box.height / rect.height,
    };
  }

  function moveObject(event) {
    if (!S.interaction || event.pointerId !== S.interaction.pointer) return;
    const delta = worldDelta(event);
    const start = S.interaction.start;
    const next = S.interaction.mode === 'resize'
      ? {
        ...start,
        width: Math.max(24, snap(start.width + delta.x)),
        height: Math.max(20, snap(start.height + delta.y)),
      }
      : {
        ...start,
        x: snap(start.x + delta.x),
        y: snap(start.y + delta.y),
      };
    S.local.set(S.interaction.id, next);
    S.dirty.add(S.interaction.id);
    renderCanvas();
    renderInspector();
    saveState();
  }

  function endObject(event) {
    if (!S.interaction || event.pointerId !== S.interaction.pointer) return;
    S.el.modelGraphSvg.releasePointerCapture?.(event.pointerId);
    S.interaction = null;
  }

  function keyMove(event, item) {
    if (
      !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)
      || !item.movable
    ) {
      return;
    }
    event.preventDefault();
    E.select(item.id);
    const bounds = effectiveBounds(item);
    const step = event.shiftKey ? S.grid * 2 : 1;
    const next = { ...bounds };
    if (event.key === 'ArrowLeft') next.x -= step;
    if (event.key === 'ArrowRight') next.x += step;
    if (event.key === 'ArrowUp') next.y -= step;
    if (event.key === 'ArrowDown') next.y += step;
    S.local.set(item.id, next);
    S.dirty.add(item.id);
    renderCanvas();
    renderInspector();
    saveState();
  }

  function saveState() {
    if (!S.el.viSaveLayout) return;
    S.el.viSaveLayout.disabled = !S.dirty.size || S.saving;
    S.el.viRevertLayout.disabled = !S.dirty.size || S.saving;
    S.el.viSaveLayout.textContent = S.saving
      ? '保存中…'
      : S.dirty.size
        ? `位置を保存 (${S.dirty.size})`
        : '位置を保存';
  }

  function revertLayout() {
    S.local.clear();
    S.dirty.clear();
    renderAll(false);
  }

  function serializeBounds(item, bounds) {
    const left = Math.round(bounds.x);
    const top = Math.round(bounds.y);
    const right = Math.round(bounds.x + bounds.width);
    const bottom = Math.round(bounds.y + bounds.height);
    const declaredOrder = String(item?.bounds?.storage_order || '').toLowerCase();
    return declaredOrder === 'top,left,bottom,right'
      ? `(${top}, ${left}, ${bottom}, ${right})`
      : `(${left}, ${top}, ${right}, ${bottom})`;
  }

  async function saveLayout() {
    if (!S.job || !S.dirty.size || S.saving) return;
    S.saving = true;
    saveState();
    const ids = [...S.dirty];
    let latestJob = S.job;
    try {
      for (const id of ids) {
        const item = S.objects.get(id);
        const bounds = S.local.get(id);
        if (!item || !bounds) continue;
        const detail = await apiRequest(
          `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
        );
        const propertyId = detail.bounds?.property_id;
        const property = (detail.properties || []).find(
          (candidate) => candidate.id === propertyId,
        );
        if (!propertyId || !property?.editable) {
          throw new Error(`${item.name} の位置は保存できません。`);
        }
        const response = await apiRequest(
          `/api/jobs/${encodeURIComponent(S.job.job_id)}/components/${encodeURIComponent(item.component_id)}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              expected_file_sha256: detail.file_sha256,
              updates: [{
                property_id: propertyId,
                value: serializeBounds(item, bounds),
              }],
            }),
          },
        );
        latestJob = response.job || latestJob;
      }
      S.dirty.clear();
      S.local.clear();
      S.job = latestJob;
      S.revision = revisionFor(latestJob);
      await renderJob(latestJob, { scroll: false });
      showToast(`${ids.length}個の配置を保存しました。`, 'success');
    } catch (error) {
      showToast(`配置保存: ${describeError(error)}`, 'error', 10000);
    } finally {
      S.saving = false;
      saveState();
    }
  }

  function renderAll(fit = false) {
    if (!S.vi) return;
    E.renderKinds();
    E.renderSummary();
    E.renderDiagnostics();
    E.renderDebug();
    E.renderList();
    renderCanvas(fit);
    renderInspector();
    saveState();
  }

  function bindInteractions() {
    E.getBounds = effectiveBounds;
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      button.addEventListener('click', () => E.setSurface(button.dataset.viSurface));
    });
    S.el.modelGraphLayer.addEventListener('change', () => {
      E.setSurface(S.el.modelGraphLayer.value);
    });
    let queryTimer;
    S.el.modelGraphQuery.addEventListener('input', () => {
      clearTimeout(queryTimer);
      queryTimer = setTimeout(() => {
        E.renderList();
        renderCanvas();
      }, 100);
    });
    S.el.modelGraphKind.addEventListener('change', () => {
      E.renderList();
      renderCanvas();
    });
    S.el.viShowTerminals.addEventListener('change', () => {
      S.showTerminals = S.el.viShowTerminals.checked;
      renderAll(false);
    });
    S.el.viShowLabels.addEventListener('change', () => {
      S.showLabels = S.el.viShowLabels.checked;
      renderCanvas();
    });
    S.el.viSnapGrid.addEventListener('change', () => {
      S.snap = S.el.viSnapGrid.checked;
    });
    S.el.viGridSize.addEventListener('change', () => {
      S.grid = number(S.el.viGridSize.value, 8);
      renderCanvas();
    });
    S.el.modelGraphFit.addEventListener('click', fitGraph);
    S.el.modelGraphZoomIn.addEventListener('click', () => zoom(0.8));
    S.el.modelGraphZoomOut.addEventListener('click', () => zoom(1.25));
    S.el.modelGraphRefresh.addEventListener('click', () => {
      void E.load(true, { preserveView: true });
    });
    S.el.viSaveLayout.addEventListener('click', () => void saveLayout());
    S.el.viRevertLayout.addEventListener('click', revertLayout);
    S.el.viObjectDrawerToggle.addEventListener('click', () => E.toggleDrawer());
    S.el.viObjectPaneClose.addEventListener('click', () => E.toggleDrawer(false));
    [
      S.el.viGeometryX,
      S.el.viGeometryY,
      S.el.viGeometryWidth,
      S.el.viGeometryHeight,
    ].forEach((input) => input.addEventListener('change', updateGeometry));
    S.el.modelGraphSvg.addEventListener('click', (event) => {
      if (event.target.closest?.('.vi-object,.vi-wire-group')) return;
      S.selected = null;
      E.renderList();
      renderCanvas();
      renderInspector();
    });
    S.el.modelGraphSvg.addEventListener('pointermove', moveObject);
    S.el.modelGraphSvg.addEventListener('pointerup', endObject);
    S.el.modelGraphSvg.addEventListener('pointercancel', endObject);
    S.el.modelGraphViewport.addEventListener('wheel', (event) => {
      if (!S.box) return;
      event.preventDefault();
      zoom(event.deltaY < 0 ? 0.86 : 1.16, event.clientX, event.clientY);
    }, { passive: false });
    S.el.modelGraphViewport.addEventListener('pointerdown', (event) => {
      if (
        event.button !== 0
        || !S.box
        || event.target.closest?.('.vi-object,.vi-wire-group')
      ) {
        return;
      }
      S.pan = {
        pointer: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        box: { ...S.box },
      };
      S.el.modelGraphViewport.setPointerCapture?.(event.pointerId);
      S.el.modelGraphViewport.classList.add('is-panning');
    });
    S.el.modelGraphViewport.addEventListener('pointermove', (event) => {
      if (!S.pan || event.pointerId !== S.pan.pointer) return;
      const rect = S.el.modelGraphViewport.getBoundingClientRect();
      applyBox({
        x: S.pan.box.x - (event.clientX - S.pan.x) * S.pan.box.width / rect.width,
        y: S.pan.box.y - (event.clientY - S.pan.y) * S.pan.box.height / rect.height,
        width: S.pan.box.width,
        height: S.pan.box.height,
      });
    });
    const endPan = (event) => {
      if (!S.pan || event.pointerId !== S.pan.pointer) return;
      S.pan = null;
      S.el.modelGraphViewport.classList.remove('is-panning');
      S.el.modelGraphViewport.releasePointerCapture?.(event.pointerId);
    };
    S.el.modelGraphViewport.addEventListener('pointerup', endPan);
    S.el.modelGraphViewport.addEventListener('pointercancel', endPan);
    S.el.modelGraphViewport.addEventListener('dblclick', (event) => {
      if (event.target.closest?.('.vi-object,.vi-wire-group')) return;
      fitGraph();
    });
  }

  Object.assign(E, {
    effectiveBounds,
    routedPoints,
    pathFromPoints,
    counterpartId,
    renderCanvas,
    renderInspector,
    renderAll,
    saveState,
    serializeBounds,
    bindInteractions,
  });
})();
