'use strict';

(() => {
  if (!document.querySelector('link[data-vi-readability]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/semantic-readability.css?v=1';
    link.dataset.viReadability = '';
    document.head.appendChild(link);
  }

  if (document.querySelector('script[data-vi-editor-readability]')) return;
  const script = document.createElement('script');
  script.src = '/static/vi-editor-readability.js?v=1';
  script.async = false;
  script.dataset.viEditorReadability = '';
  document.head.appendChild(script);
})();
