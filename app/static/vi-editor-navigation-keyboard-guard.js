'use strict';

(() => {
  const runtime = {
    ready: false,
    handled: 0,
  };

  function workflow() {
    return globalThis.VINavigationWorkflow;
  }

  function setActiveIndex(index) {
    const R = workflow()?.runtime;
    if (!R?.results?.length) {
      if (R) R.activeIndex = 0;
      R?.elements?.query?.removeAttribute('aria-activedescendant');
      return;
    }
    R.activeIndex = Math.max(0, Math.min(R.results.length - 1, index));
    const buttons = [
      ...(R.elements?.results?.querySelectorAll('[data-navigation-result]') || []),
    ];
    buttons.forEach((element, itemIndex) => {
      const active = itemIndex === R.activeIndex;
      element.classList.toggle('is-active', active);
      element.setAttribute('aria-selected', String(active));
      if (active) {
        R.elements.query?.setAttribute('aria-activedescendant', element.id);
        element.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function focusableElements() {
    const R = workflow()?.runtime;
    return [
      R?.elements?.query,
      ...(R?.elements?.results?.querySelectorAll('button:not(:disabled)') || []),
      R?.elements?.close,
    ].filter((element) => element && !element.hidden);
  }

  function trapTab(event) {
    const values = focusableElements();
    if (!values.length) return;
    const current = values.indexOf(document.activeElement);
    const next = event.shiftKey
      ? (current <= 0 ? values.length - 1 : current - 1)
      : (current < 0 || current === values.length - 1 ? 0 : current + 1);
    values[next].focus();
  }

  function handle(event) {
    const W = workflow();
    const R = W?.runtime;
    const dialog = R?.elements?.dialog;
    if (!W?.ready || !R?.open || !dialog?.contains(event.target)) return;

    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && event.key.toLowerCase() === 'k') {
      // The workflow's document-level handler owns the open/close shortcut.
      return;
    }

    let handled = true;
    if (event.key === 'Escape') {
      W.close();
    } else if (event.key === 'ArrowDown') {
      setActiveIndex(R.activeIndex + 1);
    } else if (event.key === 'ArrowUp') {
      setActiveIndex(R.activeIndex - 1);
    } else if (event.key === 'Home') {
      setActiveIndex(0);
    } else if (event.key === 'End') {
      setActiveIndex(R.results.length - 1);
    } else if (event.key === 'Enter') {
      const value = R.results[R.activeIndex];
      if (value) W.navigateTo(value.id);
    } else if (event.key === 'Tab') {
      trapTab(event);
    } else {
      handled = false;
    }

    if (!handled) return;
    runtime.handled += 1;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function install() {
    if (runtime.ready || !workflow()?.ready) return false;
    runtime.ready = true;
    window.addEventListener('keydown', handle, true);
    globalThis.VINavigationKeyboardGuard = {
      ready: true,
      runtime,
      setActiveIndex,
      trapTab,
      handle,
    };
    return true;
  }

  function waitForWorkflow(attempt = 0) {
    if (install()) return;
    if (attempt < 400) {
      setTimeout(() => waitForWorkflow(attempt + 1), 25);
      return;
    }
    globalThis.VINavigationKeyboardGuard = {
      ready: false,
      error: 'navigation workflow did not become ready',
      runtime,
    };
  }

  globalThis.VINavigationKeyboardGuard = { ready: false, runtime };
  waitForWorkflow();
})();
