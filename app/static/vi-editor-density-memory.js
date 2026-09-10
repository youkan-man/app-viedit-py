'use strict';

(() => {
  const runtime = { ready: false, originalSetSurface: null };

  function install() {
    const editor = globalThis.VISemanticEditor;
    const density = globalThis.VICanvasDensity;
    if (
      runtime.ready
      || !density?.ready
      || typeof editor?.setSurface !== 'function'
    ) {
      return false;
    }

    runtime.ready = true;
    runtime.originalSetSurface = editor.setSurface;
    editor.setSurface = function setSurfaceWithMemory(
      surface,
      fitRequested = true,
    ) {
      const changed = Boolean(surface && surface !== editor.S?.surface);
      if (changed) {
        density.rememberCurrentView();
        // The density wrapper interprets false as "restore a saved view when
        // one exists, otherwise create the initial readable view". Normal tab
        // switching must not discard the previous pan/zoom for that surface.
        return runtime.originalSetSurface.call(editor, surface, false);
      }
      return runtime.originalSetSurface.call(editor, surface, fitRequested);
    };

    globalThis.VICanvasDensityMemory = {
      ready: true,
      runtime,
    };
    return true;
  }

  function waitForDensity(attempt = 0) {
    if (install()) return;
    if (attempt < 320) setTimeout(() => waitForDensity(attempt + 1), 25);
  }

  globalThis.VICanvasDensityMemory = { ready: false, runtime };
  waitForDensity();
})();
