'use strict';

(() => {
  for (const [flag, src] of [
    ['vi-editor-structure-workflow-catalog-fix', '/static/vi-editor-structure-workflow-catalog-fix.js?v=1'],
    ['vi-editor-structure-workflow-probe', '/static/vi-editor-structure-workflow-probe.js?v=1'],
  ]) {
    if (document.querySelector(`script[data-${flag}]`)) continue;
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.setAttribute(`data-${flag}`, 'true');
    document.head.appendChild(script);
  }
})();
