'use strict';

(() => {
  const runtime = {
    ready: false,
    originalInstall: null,
    jobId: null,
    byId: new Map(),
  };

  function editor() {
    return globalThis.VISemanticEditor;
  }

  function state() {
    return editor()?.S;
  }

  function currentJobId() {
    return String(state()?.job?.job_id || 'unloaded');
  }

  function wireRecords(vi) {
    return [
      ...(vi?.all_structure_frame_wires || []),
      ...(vi?.inactive_structure_frame_wires || []),
      ...(vi?.wires || []),
    ].filter((wire) => wire?.id);
  }

  function preserve(vi) {
    if (!vi) return vi;
    const nextJobId = currentJobId();
    if (runtime.jobId !== nextJobId) {
      runtime.jobId = nextJobId;
      runtime.byId.clear();
    }
    // Merge, never replace. During same-job redraws S.vi.wires contains only
    // the currently visible frame. Replacing the catalog at that point made
    // every other frame's branches permanently disappear.
    wireRecords(vi).forEach((wire) => runtime.byId.set(wire.id, wire));
    vi.all_structure_frame_wires = [...runtime.byId.values()];
    return vi;
  }

  function install() {
    const E = editor();
    if (runtime.ready || !E || typeof E.install !== 'function') return false;
    runtime.ready = true;
    runtime.originalInstall = E.install;
    E.install = function installWithFrameWireCatalog(vi) {
      return runtime.originalInstall.call(E, preserve(vi));
    };
    if (state()?.vi) preserve(state().vi);
    globalThis.VIFrameWireCatalog = {
      ready: true,
      runtime,
      preserve,
      wireRecords,
    };
    return true;
  }

  function waitForEditor(attempt = 0) {
    if (install()) return;
    if (attempt < 360) setTimeout(() => waitForEditor(attempt + 1), 25);
  }

  globalThis.VIFrameWireCatalog = { ready: false, runtime };
  waitForEditor();
})();
