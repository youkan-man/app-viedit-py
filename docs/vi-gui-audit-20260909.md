# 実VIによるコンポーネント表示監査 — 2026-09-09

## 結論

**整列の不足ではなく、VIの部品をモデルにする段階で欠落している。** 公開VIを実際に読み込むと、ModbusとSystemLinkは初期描画ノード0件。原XMLには制御器・端子・signal・ループが存在する。今回の変更は監査コードと記録だけで、アプリ本体の修正ではない。

アライメントは補助機能とする。主機能は「VIを開く → FP/BDを把握する → 部品プロパティを閲覧・編集する」。自動整列で解析や座標系の誤りを覆い隠さない。

## 条件と証拠

アプリ本体 `b4746c7ba4c5d4a162caa722fe54746c1869cebc`、pylabview `69768647c18d2d792a259b69884b2433761c3a4f`。採取コミット `c4e9330f52f8d17a462b6075510c7ba80ddaf3b0` のアプリ本体との差分は0バイト。

[Actions実行34305989351](https://github.com/youkan-man/app-viedit-py/actions/runs/34305989351) でアプリを実起動。Chromiumでファイル読み込み・モデル・プロパティの操作を行い、1440×1000と1366×768のPNG計27枚、DOM、SVG、解析JSON、元VI、展開XML、再構成VI、ログを採取した。既存テストは57 passed / 1 warning。4ケースの採取が完了し、pageerrorは0件だが、これは表示の受入テスト合格を意味しない。

[証拠ZIP](https://github.com/youkan-man/app-viedit-py/actions/runs/34305989351/artifacts/10086670543) のSHA-256は `a55856a3b82d2edcbaec317f9d048eaf08e45bdd250c6c2221cb8a3f11aa5c41`。Actionsでの期限は2026-09-23。後続の採取コードには警告消去後の画面、選択時のviewBox変化、ペイン実寸も記録する処理を追加した。

### 指定基盤

`codex-skill-sandbox-control-plane` と `local-transport-gateway-assets` のREADME・SKILLを確認。Gatewayのlocal.targetsは応答したが、カタログはvalidation=falseで検証用sandboxの明示的な分離設定がなかった。Control PlaneのAPI URL・認証情報も利用可能でなかった。

稼働中環境を変更せず、実行は隔離されたGitHub-hosted runnerへ切り替えた。指定Control Plane上での実行検証ではない。VIは解析・再構成のみ。VIコード、モーター通信、SystemLink通信は実行していない。LabVIEW本体での読み込み・実行・画面比較は未実施。

## 公開入力と結果

3種類のVIを固定Git blob SHAから取得し、SHAを照合。出典LICENSEも同梱。Modbusは文字コードを変えて2回検証した。

| 入力・文字コード | 実XML数 | モデル解析失敗 | 初期描画数 | バイナリ再構成比較 |
|---|---:|---|---:|---|
| pylabview empty_vifile.vi / Shift_JIS | 3 | FPHb | 1（内部名sRNの矩形） | 一致・4,786 B |
| AppliedMotionProducts AMP_Modbus_TCP.vi / Shift_JIS | 2 | BDHb。FPHbは文字コードエラーでBIN保存 | 0 | 一致・19,078 B |
| 同Modbus / CP1252 | 3 | BDHb・FPHb | 0 | 一致・19,078 B |
| NI Asset Utilization Example.vi / Shift_JIS | 3 | BDHb・FPHb | 0 | 不一致・25,661→25,701 B |

CP1252にするとModbusのFPHbはXML展開できたがモデル解析は失敗した。文字コード問題とモデル化の不具合は別である。SystemLinkの40バイト差について、機能的同等性は未確認。

| 公開リポジトリ | パス | 固定Git blob SHA |
|---|---|---|
| mefistotelis/pylabview（MIT） | examples/lv14f1/empty_vifile.vi | e5a2d6fabc3af4a074c563bb53eaa64ef915c5f8 |
| AppliedMotionProducts/LabVIEW（Apache-2.0） | AMP_Modbus_TCP.vi | 32ee3edc1e4d64db79b42cc7c3340bd89c9f1c94 |
| ni/systemlink-labview-examples（MIT） | Asset Management/Asset Utilization Example.vi | 71b54e6f518bbadc2c1188ac30da5c0692cc8d63 |

## 実データ・画面で確認した不具合

### P0: 色値でモデル解析が中断

`app/component_model.py::classify_value()` が実XMLの `<fgColor>01000000</fgColor>` を整数と判定し `int(text, 0)` に渡すため、`invalid literal for int() with base 0: '01000000'`。3種すべてで再現。FPHb/BDHbのモデル生成が止まる。

色・バイナリ・整数は保存形式とフィールドの意味で区別する必要がある。先頭ゼロを10進数として読めるようにするだけでは色の誤解釈になる。未知値は原値と診断を保持し、単一の値で部品全体を失わない。

証拠: 各model.jsonのwarnings、展開FPHb/BDHb、modbus/02-default-model.png。

### P0: class付きSL__arrayElementを除外

`component_candidate()` がSL__arrayElementをclass/UID確認より先に除外する。実XMLではその要素がterm、signal、forLoop、fPDCOなどの実体を持つ。

原XMLと判定関数の直接照合で、SystemLink BDHbのclass付き512要素中286要素が除外対象。term 163、signal 58、forLoop 2、fPTerm 7を含む。FPHbは302中182が除外され、fPDCO 7要素すべてが対象。Modbus BDHbは1,040中628が除外される。

数値はXML中のclass付き要素数で、画面上の部品数・配線数をそのまま示すものではない。前段の色エラーとは別に候補判定を直接検証した。単なる配列ラッパーとclass付きオブジェクトを分け、制御器・表示部品・ラベル・端子を意味のある部品モデルに関連付ける必要がある。除外を外して内部装飾まで全て独立した矩形にするだけでは不十分。

### P1: 解析失敗後の部分状態と重複

`_analyze_file()` は成功前にFileModelと空の部品を共有状態へ追加する。例外後にanalyze()が同じファイルのエラー行を追加し、元の途中状態を戻さない。

SystemLinkは実XML3なのに画面は5 files / 3 parsed / 2 failed。437部品中356はkind未設定、405はclass unknown。ファイル一覧にBDHb・FPHbがそれぞれ重複する。ファイル単位の確定処理、または明示的な部分解析状態が必要。

証拠: systemlink/model.json、systemlink/07-control-properties.png。

### P1: 失敗・読込中・解析済みの混在

Modbusは描画0件なのに上部「解析済み」、右「準備完了」「Binary identical」、中央「モデルを読み込んでいます」。エラー通知と緑の解析完了通知が同時に出る。

変換、部品モデル、再構成比較を別状態にする。空状態は読込中・部品なし・位置なし・フィルター0件・解析失敗を区別する。失敗XMLとFPHbのBIN退避は画面内に常設する。バイナリ一致は表示品質の保証にしない。

証拠: modbus/02-default-model.png、systemlink/02-default-model.png。

### P1: プロパティの主役がXML内部構造

SystemLinkの一覧先頭はRSRC、BDEx、BDHbなどで、選択先もType、Encoding、FormatVersion。元のFPHbには7個のfPDCO、2個のtableControl、3個のstdStringが存在するが部品としてたどれない。

通常画面は制御器・表示器・定数・SubVI・構造・端子・配線の単位にする。部品名、型、値、外観、接続、所有関係を意味別に表示し、XML class/UID/パスは詳細へ退避する。編集可否は個別フィールドの実装契約で決める。

証拠: systemlink/07-control-properties.png。旧スクリプトのファイル名はcontrolだが実際の選択はRSRC。後続では07-selected-propertiesへ改名した。

### P1: ノートPC幅で編集欄が圧迫

外側の左ナビと右ジョブ情報を残したまま中央をファイル・部品・プロパティに3分割するため、1366×768ではプロパティの文字・入力欄が切れる。サマリーと検索も大きな面積を占める。

中央を部品一覧／キャンバス、右を選択部品のプロパティに使い、ジョブ情報・変換結果を小さく折り畳む。幅を調整可能にし、狭い画面ではファイル一覧を退避する。

証拠: systemlink/08-laptop-properties.png。

## 描画コード上の制約（解析修正後の追加検証が必要）

graph.jsは全モデルを同じSVG矩形で描き、接続線は矩形中心を結ぶ生成経路。保存されたワイヤ経路や端子アンカーを描いていない。model_graph.pyの_node_public()はbounds／最初のpointをそのまま位置にしており、親子原点・ローカル座標を合成しない。

selectModel→render→renderGraph→fitGraphの経路もあり、部品の選択とズーム／パンが独立していない。後続スクリプトでviewBox前後値を採取する。空VIの実画面ではsRNの文字が矩形からはみ出していた。

複雑なVIの実配線・階層の描画誤差は、今回P0でモデルが止まるため定量化していない。ソースで分かる制約と画面再現済みの不具合を区別する。

## 修正順と受入条件

まず色値、class付き配列要素、解析途中状態を修正し、今回のVIでXML重複と無名部品が生じず、未対応形式を明示できることを回帰テストにする。次にFP/BDの座標系・所有関係・端子・配線を構築し、曖昧な参照を確定配線として描かない。LabVIEW本体の参照画面を用意できた段階で同じVIを比較する。

その上で意味モデルをプロパティ編集へつなぐ。対象選択、対応項目編集、保存・再読込、再構成差分の確認までを受入条件にする。整列は最後に選択範囲への補助操作として追加し、差分プレビューと取り消しを持たせる。

## 再実行

```bash
python -m pip install -r requirements-dev.txt playwright==1.55.0
python -m playwright install --with-deps chromium
WORK_ROOT=/tmp/vi-audit-tests python -m pytest -q
python scripts/audit_real_vi.py
```

出力はaudit-evidence/。外部ネットワークとブラウザーの使える隔離環境で実行する。127.0.0.1:8080を既存サービスと競合させない。スクリプトは自分で起動したアプリ子プロセスだけを終了する。capture_completedやworkflow成功は証拠採取完了を示し、モデル表示品質の合格ではない。
