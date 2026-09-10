'use strict';

(() => {
  const state = { ready: false };

  function setText(element, value) {
    if (element && element.textContent !== value) element.textContent = value;
  }

  function rename() {
    const navigation = document.querySelector('.azure-navigation');
    navigation?.setAttribute('aria-label', 'ビュー切り替え');
    setText(navigation?.querySelector('.navigation-section-title'), 'ビュー');
    const labels = {
      model: ['VI編集', '部品・ノード・配線'],
      properties: ['プロパティ一覧', 'VIオブジェクト情報'],
      xml: ['RAWデータ', 'XMLと抽出ファイル'],
      align: ['整列ツール', '一括座標処理'],
      build: ['成果物', '再構成ログと出力'],
    };
    Object.entries(labels).forEach(([page, values]) => {
      const button = document.querySelector(`[data-app-page="${page}"]`);
      setText(button?.querySelector('strong'), values[0]);
      setText(button?.querySelector('small'), values[1]);
    });
    setText(
      document.querySelector('#page-xml .blade-description'),
      '解析元のRAW XMLとデータセットファイル。通常の部品編集には使用しません。',
    );
    setText(
      document.querySelector('#page-build .blade-description'),
      '再構成済み成果物と実行ログ。再構成ボタンは現在の画面で処理を実行します。',
    );
    setText(
      document.querySelector('#vi-inspector-source-details > summary'),
      'RAWデータ（class / UID / XML）',
    );
    setText(document.querySelector('#model-open-properties'), 'プロパティ詳細');
  }

  function install() {
    if (state.ready || !document.querySelector('.azure-navigation')) return false;
    state.ready = true;
    rename();
    let attempts = 0;
    const settle = () => {
      rename();
      attempts += 1;
      if (attempts < 40 && !document.querySelector('#vi-inspector-source-details')) {
        setTimeout(settle, 50);
      }
    };
    settle();
    globalThis.VIUILabels = { ready: true, rename };
    return true;
  }

  function waitForShell(attempt = 0) {
    if (install()) return;
    if (attempt < 240) setTimeout(() => waitForShell(attempt + 1), 25);
  }

  globalThis.VIUILabels = { ready: false };
  waitForShell();
})();
