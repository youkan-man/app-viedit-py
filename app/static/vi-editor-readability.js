'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const runtime = {
    ready: false,
    scheduled: false,
    decorating: false,
    observer: null,
    shellObserver: null,
    resizeObserver: null,
    metrics: null,
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
      element.setAttribute(name, String(value));
    });
    return element;
  }

  function root() {
    return document.querySelector('#model-graph-svg');
  }

  function shell() {
    return document.querySelector('#vi-editor-shell');
  }

  function currentLod() {
    return shell()?.dataset.viLod || 'normal';
  }

  function isStructure(item) {
    return Boolean(
      item
      && (
        item.visual_kind === 'structure'
        || String(item.kind || '').startsWith('structure')
      )
    );
  }

  function selectedContext() {
    const S = state();
    const context = {
      active: false,
      selectedId: S?.selected || null,
      primaryObjects: new Set(),
      relatedObjects: new Set(),
      primaryWires: new Set(),
      relatedWires: new Set(),
      netIds: new Set(),
    };
    if (!S?.selected) return context;

    const selectedItem = S.objects.get(S.selected);
    const selectedWire = S.wires.get(S.selected);
    if (!selectedItem && !selectedWire) return context;
    if (selectedItem && selectedItem.surface !== S.surface) return context;
    if (selectedWire && S.surface !== 'block-diagram') return context;
    context.active = true;

    const includeObject = (id, primary = false) => {
      if (!id || !S.objects.has(id)) return;
      (primary ? context.primaryObjects : context.relatedObjects).add(id);
    };
    const includeWire = (wire, primary = false) => {
      if (!wire) return;
      (primary ? context.primaryWires : context.relatedWires).add(wire.id);
      if (wire.net_id) context.netIds.add(wire.net_id);
      includeObject(wire.source_terminal_id);
      includeObject(wire.source_object_id);
      (wire.target_terminal_ids || []).forEach((id) => includeObject(id));
      (wire.target_object_ids || []).forEach((id) => includeObject(id));
    };

    if (selectedWire) {
      includeWire(selectedWire, true);
    } else if (selectedItem) {
      includeObject(selectedItem.id, true);
      includeObject(selectedItem.owner_object_id);
      includeObject(selectedItem.linked_object_id);
      includeObject(selectedItem.parent_object_id);
      (selectedItem.terminal_ids || []).forEach((id) => includeObject(id));
      (selectedItem.linked_terminal_ids || []).forEach((id) => includeObject(id));
      (selectedItem.child_object_ids || []).forEach((id) => includeObject(id));
      (selectedItem.wire_ids || []).forEach((id) => includeWire(S.wires.get(id)));
    }

    if (context.netIds.size) {
      S.wires.forEach((wire) => {
        if (wire.net_id && context.netIds.has(wire.net_id)) includeWire(wire);
      });
    }

    context.primaryObjects.forEach((id) => context.relatedObjects.delete(id));
    context.primaryWires.forEach((id) => context.relatedWires.delete(id));
    return context;
  }

  function applySelectionFocus(context) {
    const S = state();
    const canvas = root();
    if (!S || !canvas) return;
    canvas.classList.toggle('has-readability-focus', context.active);
    canvas.dataset.readabilityFocus = context.active ? 'selection' : 'none';

    canvas.querySelectorAll('[data-object-id]').forEach((group) => {
      const id = group.dataset.objectId;
      const primary = context.primaryObjects.has(id);
      const related = context.relatedObjects.has(id);
      group.classList.toggle('is-readability-primary', primary);
      group.classList.toggle('is-readability-related', related);
      group.classList.toggle(
        'is-readability-muted',
        context.active && !primary && !related,
      );
    });

    canvas.querySelectorAll('[data-wire-id]').forEach((group) => {
      const id = group.dataset.wireId;
      const wire = S.wires.get(id);
      const sameNet = Boolean(wire?.net_id && context.netIds.has(wire.net_id));
      const primary = context.primaryWires.has(id);
      const related = context.relatedWires.has(id) || sameNet;
      group.classList.toggle('is-readability-primary', primary);
      group.classList.toggle('is-readability-related', related && !primary);
      group.classList.toggle(
        'is-readability-muted',
        context.active && !primary && !related,
      );
    });
  }

  function boundsFor(item) {
    const E = editor();
    return E?.effectiveBounds?.(item) || E?.getBounds?.(item) || item?.bounds || null;
  }

  function structureFrameLabel(item) {
    if (!item) return '';
    if (item.active_frame_label != null) return String(item.active_frame_label);
    const structure = item.structure || {};
    const frames = item.structure_frames || structure.frames || [];
    const rawIndex = item.active_frame_index
      ?? structure.displayed_frame
      ?? structure.active_frame
      ?? structure.current_frame
      ?? 0;
    const index = Math.max(0, Math.min(frames.length - 1, Number(rawIndex) || 0));
    const frame = frames[index] || {};
    return String(
      frame.label
      ?? frame.selector_value
      ?? frame.event_name
      ?? frame.name
      ?? (frames.length ? `Frame ${index}` : ''),
    );
  }

  function decorateStructureFrames() {
    const S = state();
    const canvas = root();
    if (!S || !canvas) return;
    canvas.querySelectorAll('[data-object-id]').forEach((group) => {
      const item = S.objects.get(group.dataset.objectId);
      if (!isStructure(item)) return;
      const label = structureFrameLabel(item).trim();
      const bounds = boundsFor(item);
      let badge = group.querySelector('.vi-structure-frame-badge');
      if (!label || !bounds) {
        badge?.remove();
        return;
      }
      if (!badge) {
        badge = svg('text', 'vi-structure-frame-badge', {
          y: 14,
          'text-anchor': 'end',
        });
        const overlay = group.querySelector('.vi-object-label,.vi-resize-handle,title');
        group.insertBefore(badge, overlay || null);
      }
      badge.setAttribute('x', String(Math.max(62, Number(bounds.width || 0) - 7)));
      badge.textContent = label;
      group.dataset.activeFrameLabel = label;
    });
  }

  function tunnelPath(direction, width, height) {
    const centerY = height / 2;
    const left = Math.max(1, width * 0.16);
    const right = Math.max(left + 3, width * 0.84);
    const top = Math.max(1, centerY - Math.max(2, height * 0.22));
    const bottom = Math.min(height - 1, centerY + Math.max(2, height * 0.22));
    if (direction === 'source') {
      return `M ${left} ${top} L ${right} ${centerY} L ${left} ${bottom} Z`;
    }
    if (direction === 'sink') {
      return `M ${right} ${top} L ${left} ${centerY} L ${right} ${bottom} Z`;
    }
    return [
      `M ${left} ${top} L ${width / 2} ${centerY} L ${left} ${bottom}`,
      `M ${right} ${top} L ${width / 2} ${centerY} L ${right} ${bottom}`,
    ].join(' ');
  }

  function decorateStructureTunnels() {
    const S = state();
    const canvas = root();
    if (!S || !canvas) return;
    canvas.querySelectorAll('[data-object-id]').forEach((group) => {
      const item = S.objects.get(group.dataset.objectId);
      if (item?.category !== 'terminal') return;
      const owner = S.objects.get(item.owner_object_id);
      const tunnel = isStructure(owner);
      group.classList.toggle('is-structure-tunnel', tunnel);
      if (!tunnel) {
        group.querySelector('.vi-tunnel-direction')?.remove();
        return;
      }
      const bounds = boundsFor(item) || { width: 8, height: 8 };
      const direction = item.direction || 'unknown';
      group.dataset.tunnelDirection = direction;
      group.dataset.structureObjectId = owner.id;
      let mark = group.querySelector('.vi-tunnel-direction');
      if (!mark) {
        mark = svg('path', 'vi-tunnel-direction');
        group.append(mark);
      }
      mark.setAttribute(
        'd',
        tunnelPath(
          direction,
          Math.max(6, Number(bounds.width || 8)),
          Math.max(6, Number(bounds.height || 8)),
        ),
      );
      mark.classList.toggle('is-source', direction === 'source');
      mark.classList.toggle('is-sink', direction === 'sink');
      mark.classList.toggle('is-bidirectional', direction === 'bidirectional');
    });
  }

  function labelElements() {
    const canvas = root();
    if (!canvas) return [];
    return [...canvas.querySelectorAll(
      '.vi-object-label,.vi-terminal-caption,.vi-cluster-count,.vi-structure-frame-badge',
    )];
  }

  function ownerForLabel(element) {
    const group = element.closest('[data-object-id]');
    const item = state()?.objects.get(group?.dataset.objectId);
    return { group, item };
  }

  function labelPriority(element, context) {
    const { group, item } = ownerForLabel(element);
    if (!group || !item) return 0;
    const id = item.id;
    if (context.primaryObjects.has(id)) return 1000;
    if (context.relatedObjects.has(id)) return 900;
    if (element.classList.contains('vi-structure-frame-badge')) return 780;
    if (isStructure(item)) return 750;
    if (item.visual_kind === 'subvi' || item.kind === 'subvi') return 690;
    if (item.category === 'control' || item.category === 'indicator') {
      if (item.parent_object_id && currentLod() !== 'detail') return 470;
      return 620;
    }
    if (item.category === 'node') return 570;
    if (element.classList.contains('vi-terminal-caption')) return 320;
    if (element.classList.contains('vi-cluster-count')) return 260;
    return 400;
  }

  function isProtectedLabel(element, context) {
    const { item } = ownerForLabel(element);
    return Boolean(
      item
      && (
        context.primaryObjects.has(item.id)
        || context.relatedObjects.has(item.id)
      )
    );
  }

  function visibleRect(element) {
    const style = getComputedStyle(element);
    if (
      style.display === 'none'
      || style.visibility === 'hidden'
      || Number(style.opacity || 1) <= 0.02
    ) return null;
    const rect = element.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return null;
    return {
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
    };
  }

  function inflate(rect, amount) {
    return {
      left: rect.left - amount,
      top: rect.top - amount,
      right: rect.right + amount,
      bottom: rect.bottom + amount,
      width: rect.width + amount * 2,
      height: rect.height + amount * 2,
    };
  }

  function intersection(first, second) {
    const width = Math.max(0, Math.min(first.right, second.right) - Math.max(first.left, second.left));
    const height = Math.max(0, Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top));
    return width * height;
  }

  function collisionMargin(lod) {
    if (lod === 'overview') return 4;
    if (lod === 'compact') return 3;
    if (lod === 'normal') return 2;
    return 0;
  }

  function suppressCollidingLabels(context) {
    const canvas = root();
    const lod = currentLod();
    const labels = labelElements();
    labels.forEach((element) => {
      element.classList.remove('is-label-suppressed');
      element.removeAttribute('aria-hidden');
    });

    if (lod === 'detail') {
      canvas.dataset.visibleLabelCount = String(labels.filter(visibleRect).length);
      canvas.dataset.suppressedLabelCount = '0';
      canvas.dataset.labelOverlapCount = '0';
      return {
        total: labels.length,
        visible: labels.filter(visibleRect).length,
        suppressed: 0,
        overlaps: 0,
        lod,
      };
    }

    const margin = collisionMargin(lod);
    const candidates = labels
      .map((element, index) => ({
        element,
        index,
        priority: labelPriority(element, context),
        protected: isProtectedLabel(element, context),
        rect: visibleRect(element),
      }))
      .filter((candidate) => candidate.rect)
      .sort((first, second) => (
        Number(second.protected) - Number(first.protected)
        || second.priority - first.priority
        || first.index - second.index
      ));

    const accepted = [];
    const suppressed = [];
    candidates.forEach((candidate) => {
      const box = inflate(candidate.rect, margin);
      const collides = accepted.some((record) => intersection(box, record.box) > 4);
      if (collides && !candidate.protected) {
        candidate.element.classList.add('is-label-suppressed');
        candidate.element.setAttribute('aria-hidden', 'true');
        suppressed.push(candidate);
        return;
      }
      accepted.push({ ...candidate, box });
    });

    let overlaps = 0;
    for (let first = 0; first < accepted.length; first += 1) {
      for (let second = first + 1; second < accepted.length; second += 1) {
        if (intersection(accepted[first].rect, accepted[second].rect) > 4) overlaps += 1;
      }
    }

    canvas.dataset.visibleLabelCount = String(accepted.length);
    canvas.dataset.suppressedLabelCount = String(suppressed.length);
    canvas.dataset.labelOverlapCount = String(overlaps);
    return {
      total: candidates.length,
      visible: accepted.length,
      suppressed: suppressed.length,
      overlaps,
      lod,
    };
  }

  function measureLabelCollisions() {
    const visible = labelElements()
      .filter((element) => !element.classList.contains('is-label-suppressed'))
      .map((element) => ({ element, rect: visibleRect(element) }))
      .filter((record) => record.rect);
    const pairs = [];
    for (let first = 0; first < visible.length; first += 1) {
      for (let second = first + 1; second < visible.length; second += 1) {
        const area = intersection(visible[first].rect, visible[second].rect);
        if (area <= 4) continue;
        pairs.push({
          first: visible[first].element.textContent?.trim() || '',
          second: visible[second].element.textContent?.trim() || '',
          area,
        });
      }
    }
    return {
      visible: visible.length,
      overlaps: pairs.length,
      pairs,
    };
  }

  function decorate() {
    if (runtime.decorating) return runtime.metrics;
    const S = state();
    const canvas = root();
    if (!S?.vi || !canvas) return null;
    runtime.decorating = true;
    try {
      const context = selectedContext();
      applySelectionFocus(context);
      decorateStructureFrames();
      decorateStructureTunnels();
      runtime.metrics = suppressCollidingLabels(context);
      canvas.dataset.readabilityReady = 'true';
      return runtime.metrics;
    } finally {
      runtime.decorating = false;
    }
  }

  function schedule() {
    if (runtime.scheduled) return;
    runtime.scheduled = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        runtime.scheduled = false;
        decorate();
      });
    });
  }

  function install() {
    const canvas = root();
    const editorShell = shell();
    const viewport = document.querySelector('#model-graph-viewport');
    if (runtime.ready || !canvas || !editorShell || !viewport || !editor()?.S) return false;
    runtime.ready = true;

    runtime.observer = new MutationObserver(schedule);
    runtime.observer.observe(canvas, { childList: true, subtree: true });
    runtime.shellObserver = new MutationObserver(schedule);
    runtime.shellObserver.observe(editorShell, {
      attributes: true,
      attributeFilter: ['data-vi-lod', 'data-vi-scale', 'data-vi-view-mode'],
    });
    runtime.resizeObserver = new ResizeObserver(schedule);
    runtime.resizeObserver.observe(viewport);

    canvas.addEventListener('click', schedule);
    canvas.addEventListener('dblclick', schedule);
    canvas.addEventListener('pointerup', schedule);
    viewport.addEventListener('wheel', schedule, { passive: true });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') schedule();
    });
    document.querySelector('#model-graph-query')?.addEventListener('input', schedule);
    document.querySelector('#model-graph-kind')?.addEventListener('change', schedule);
    document.querySelectorAll('[data-vi-surface]').forEach((button) => {
      button.addEventListener('click', schedule);
    });

    globalThis.VIReadability = {
      ready: true,
      runtime,
      decorate,
      schedule,
      selectedContext,
      measureLabelCollisions,
      structureFrameLabel,
    };
    schedule();
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 360) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIReadability = { ready: false, runtime };
  waitForEditor();
})();
