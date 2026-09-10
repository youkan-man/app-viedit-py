'use strict';

(() => {
  const runtime = { ready: false, rebuilding: false };

  function semanticState() {
    return globalThis.VISemanticEditor?.S;
  }

  function currentJob() {
    if (typeof state !== 'undefined' && state.currentJob) return state.currentJob;
    return semanticState()?.job || null;
  }

  function setActionStatus(text, stateClass = '') {
    let status = document.querySelector('#vi-action-status');
    if (!status) {
      status = document.createElement('span');
      status.id = 'vi-action-status';
      status.className = 'state-badge';
      const health = document.querySelector('#health-pill');
      health?.parentElement?.insertBefore(status, health);
    }
    status.textContent = text;
    status.className = `state-badge${stateClass ? ` ${stateClass}` : ''}`;
    status.hidden = !text;
  }

  async function rebuildInPlace(event) {
    event?.preventDefault();
    event?.stopImmediatePropagation();
    const job = currentJob();
    if (!job?.job_id || runtime.rebuilding) return;

    runtime.rebuilding = true;
    const activePage = globalThis.viPages?.activePage || 'model';
    const buttons = [
      document.querySelector('#rebuild-job'),
      document.querySelector('#build-run'),
      document.querySelector('#header-rebuild'),
    ].filter(Boolean);
    buttons.forEach((button) => { button.disabled = true; });
    setActionStatus('再構成中');

    try {
      let activeJob = job;
      if (typeof mainXmlDirty !== 'undefined' && mainXmlDirty) {
        const saved = await globalThis.saveMainXml?.();
        if (!saved) return;
        activeJob = currentJob();
      }
      const outputName = (
        document.querySelector('#build-output-name')?.value
        || document.querySelector('#rebuild-name')?.value
        || ''
      ).trim() || null;
      const updated = await apiRequest(activeJob.rebuild_url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_name: outputName,
          text_encoding: activeJob.text_encoding || 'shift_jis',
          verbosity: 1,
        }),
      });
      await globalThis.renderJob(updated, { scroll: false });
      if (globalThis.viPages?.activePage !== activePage) {
        globalThis.viPages?.open(activePage, { replace: true });
      }
      setActionStatus('再構成済み', 'is-ready');
      showToast('現在の画面を維持したままVI / RSRCを再構成しました。', 'success');
    } catch (error) {
      setActionStatus('再構成失敗', 'is-dirty');
      showToast(`再構成: ${describeError(error)}`, 'error', 10000);
    } finally {
      runtime.rebuilding = false;
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  function bind(button) {
    if (!button || button.dataset.inPlaceActionBound === 'true') return;
    button.dataset.inPlaceActionBound = 'true';
    button.addEventListener('click', rebuildInPlace, true);
  }

  function install() {
    if (runtime.ready || !document.querySelector('#header-rebuild')) return false;
    runtime.ready = true;
    document.querySelectorAll('#header-rebuild,#rebuild-job,#build-run').forEach(bind);
    globalThis.VIInPlaceActions = {
      ready: true,
      runtime,
      rebuildInPlace,
    };
    return true;
  }

  function waitForWorkspace(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForWorkspace(attempt + 1), 25);
  }

  globalThis.VIInPlaceActions = { ready: false, runtime };
  waitForWorkspace();
})();
