# pylabview VI/XML Workbench

`pylabview` の `readRSRC` をWeb画面から操作し、LabVIEWのVI/RSRCファイルをXMLデータセットへ展開し、そのXMLデータセットからVI/RSRCファイルを再構成するDockerアプリです。

画面は `youkan-man/infra-test-sandbox` のWeb Console CSSを基準に、Azure Portal / Fluent系の配色、密度、タイポグラフィへ揃えています。独立した作図キャンバスはありません。配置補正は、**再構成に使う実際のpylabview XML内の座標を指定粒度へクオンタイズ**する編集機能です。

![Python](https://img.shields.io/badge/backend-Python%20%2B%20FastAPI-3776AB)
![Docker](https://img.shields.io/badge/host-Docker-2496ED)
![License](https://img.shields.io/badge/license-MIT-green)

![VI/XML Workbench UI](docs/ui-preview.svg)

## できること

- VI/CTL/LLBなどのRSRCファイルをアップロードしてXMLへ展開
- メインXMLと補助XML/BINを、再構成可能なデータセットZIPとして一括ダウンロード
- 抽出直後にXML→RSRCを実行し、元ファイルとのSHA-256一致を任意で検証
- データセットZIP、または単独XMLをアップロードしてVI/RSRCを再構成
- ブラウザ上でメインXMLを編集、検証、保存して再構成
- コンポーネント、コネクタ／端子、XML展開済み配線ポイントを指定ピッチへクオンタイズ
- クオンタイズ前後のXMLパス、座標値、対象種別をプレビューしてから反映
- `stdout` / `stderr` / 実行コマンド / 処理時間を画面で確認
- `shift_jis`、`utf-8`、各種Windows/Mac系コードページを選択
- ジョブごとの隔離、アップロード上限、ZIP Slip・シンボリックリンク・ZIP展開量の検査

## 起動

```bash
git clone https://github.com/youkan-man/app-viedit-py.git
cd app-viedit-py
docker compose up --build -d
```

ブラウザで次を開きます。

```text
http://localhost:8080
```

ログ確認と停止:

```bash
docker compose logs -f --tail=200
docker compose down
```

作業データはDocker named volume `pylabview_data` に保存され、既定では最終更新から24時間後に新しいジョブ作成時の清掃対象になります。

## 操作

### VI → XML

1. `VI → XML` タブへVI/RSRCファイルをドロップします。
2. 文字コードを選択します。日本語版LabVIEWの一般的なファイルでは、まず `shift_jis` を試します。
3. `XMLデータセットへ変換` を押します。
4. 必要に応じてXMLを編集または座標クオンタイズします。
5. `XMLデータセット ZIP` を保存するか、現在のXMLからVIを再構成します。

抽出結果は単一XMLだけとは限りません。`pylabview` が外部化した補助XML/BINを同梱するため、このアプリではZIPを再構成の正規入力として扱います。メインXML単独のダウンロードも可能ですが、外部ファイル参照が含まれる場合は単独では再構成できません。

### XML → VI

1. `XML → VI` タブへ、このアプリが出力したデータセットZIPをドロップします。
2. 必要なら出力名と文字コードを指定します。
3. `VI / RSRCを再構成` を押します。
4. 生成されたVI/RSRCファイルをダウンロードします。

他の方法で作ったZIPも利用できます。RSRCルートを持つXMLが複数ある場合は、ZIPルートからの相対パスを `メインXMLパス` に指定してください。

### XMLを画面で編集

変換後のワークスペースにメインXMLエディタが表示されます。保存時にXML構文とルート要素 `RSRC` を検査します。保存後は以前の再構成ファイルが「古い」状態になるため、再度 `このXMLから再構成` を実行してください。

既定では8 MiBを超えるメインXMLは画面編集を無効にします。データセットZIPをダウンロードし、外部エディタで編集して再アップロードしてください。

## 座標クオンタイズ

座標クオンタイズは、LabVIEWの見た目だけを模した別キャンバスではなく、**現在XMLエディタへ読み込まれているpylabview XML**を対象にします。

基本手順:

1. 粒度を1〜256 pxから指定します。一般的には4、8、16 pxを使います。
2. 最近傍、小さい側、大きい側の丸め方式を選択します。
3. 対象を選びます。
   - コンポーネント矩形
   - コネクタ／端子
   - XML上に展開された配線ルート
4. `差分を解析` を押し、変更前後とXMLパスを確認します。
5. `XMLへ反映` を押します。
6. XMLエディタで内容を確認し、`XMLを保存`、`このXMLから再構成` の順に実行します。

矩形は既定で左上位置だけをスナップし、元の幅と高さを維持します。`幅と高さも丸める` を有効にした場合だけ、矩形サイズも粒度へ合わせます。

`pylabview` のヒープXMLで座標として展開された、たとえば `bounds`、`termBounds`、`termHotPoint`、wire/segment配下の点・矩形タプルを対象にします。座標形式は `(left, top, right, bottom)` または `(y, x)` です。

### 配線に関する制限

`compressedWireTable` や外部BINへ保持された配線情報は、座標形式を安全に特定できないため変更しません。XML上に展開された配線座標だけを丸め、対象が見つからない場合や圧縮配線ブロックが残る場合は画面へ警告します。推測でバイナリを書き換えることはしません。

## Azure寄せの画面デザイン

画面の基礎トークンと密度は `youkan-man/infra-test-sandbox/web-console/app/static/styles/foundation.css` を参照しています。

- Azure Blue `#0078d4` とhover/pressedトークン
- `#f3f2f1` のキャンバスと白いパネル
- 48pxの固定ダークヘッダー
- Segoe UI系フォント
- 2px radius、32〜34pxのコンパクトなフォーム部品
- Azure Portalに近いパネル、タブ、状態表示、通知の階層

CSS上の余白は4px単位で統一していますが、これは画面レイアウト用です。VIオブジェクトのスナップ粒度は、座標クオンタイズ欄で独立して指定します。

## API

OpenAPI UI:

```text
http://localhost:8080/api/docs
```

主要エンドポイント:

| Method | Path | 内容 |
|---|---|---|
| `GET` | `/api/health` | アプリ・`readRSRC`状態と制限値 |
| `POST` | `/api/quantize/xml` | XML文字列の座標差分を解析し、クオンタイズ結果を返す |
| `POST` | `/api/convert/vi-to-xml` | VI/RSRCからXMLデータセットを作成 |
| `POST` | `/api/convert/xml-to-vi` | XML/ZIPからVI/RSRCを再構成 |
| `GET` | `/api/jobs/{job_id}` | ジョブ状態 |
| `GET/PUT` | `/api/jobs/{job_id}/xml` | メインXML取得・更新 |
| `POST` | `/api/jobs/{job_id}/rebuild` | 更新済みXMLから再構成 |
| `GET` | `/api/jobs/{job_id}/download/{artifact}` | 成果物取得 |
| `DELETE` | `/api/jobs/{job_id}` | ジョブ削除 |

クオンタイズAPI例:

```bash
curl -X POST http://localhost:8080/api/quantize/xml \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "<RSRC><bounds>(3, 5, 103, 55)</bounds></RSRC>",
    "grid_size": 8,
    "rounding": "nearest",
    "include_objects": true,
    "include_connectors": true,
    "include_wires": true,
    "resize_rectangles": false
  }'
```

APIはジョブを直接更新せず、クオンタイズ済みXMLと差分レポートを返します。ブラウザは結果をエディタへ反映し、ユーザーが明示的に保存してからVIを再構成します。

## 設定

`docker-compose.yml` の環境変数で変更できます。

| 変数 | 既定値 | 内容 |
|---|---:|---|
| `WORK_ROOT` | `/data/jobs` | ジョブ保存先 |
| `MAX_UPLOAD_BYTES` | `268435456` | 1アップロードの最大サイズ（256 MiB） |
| `MAX_ARCHIVE_BYTES` | `536870912` | ZIP展開後の最大合計サイズ（512 MiB） |
| `MAX_ARCHIVE_FILES` | `10000` | ZIP内の最大ファイル数 |
| `COMMAND_TIMEOUT_SECONDS` | `300` | `readRSRC`のタイムアウト |
| `INLINE_XML_MAX_BYTES` | `8388608` | ブラウザ編集・クオンタイズ可能なXML上限（8 MiB） |
| `JOB_TTL_HOURS` | `24` | ジョブ保持時間 |
| `LOG_MAX_CHARS` | `100000` | 1ログ欄に保持する最大文字数 |
| `PYLABVIEW_COMMAND` | `readRSRC` | 実行するコマンド。引数を含む指定も可能 |

ポート変更例:

```yaml
ports:
  - "9000:8080"
```

## `pylabview`の固定バージョン

Dockerビルドは次のコミットを固定してインストールします。

```text
mefistotelis/pylabview
69768647c18d2d792a259b69884b2433761c3a4f
```

別コミットでビルドする場合:

```bash
docker compose build \
  --build-arg PYLABVIEW_COMMIT=<commit-sha>
```

## 制約

- XML化・再構成の対応範囲は上流`pylabview`に依存します。未解析ブロックはバイナリとして保持される場合があります。
- 座標クオンタイズはXMLとして認識できる座標だけを変更します。外部BINや圧縮配線テーブルは変更しません。
- XMLを編集せず再構成しても、古いLabVIEW形式、LLB、セクション順序、パディングなどによりバイナリ一致しない場合があります。画面の検証結果とLabVIEWでの実読込を併用してください。
- コンパイル済みVIから欠落したブロックダイアグラムを自動復元する機能ではありません。
- LabVIEW本体はDockerイメージに含みません。生成物の最終確認・再保存には、対象バージョンのLabVIEW環境を使用してください。
- 認証機能はありません。インターネットへ直接公開せず、ローカルまたは信頼できるネットワークで使ってください。公開が必要な場合は、認証付きリバースプロキシを前段に置いてください。

## 開発・テスト

ローカルPython環境:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

静的確認:

```bash
python -m compileall -q app main.py
node --check app/static/app.js
node --check app/static/workspace.js
node --check app/static/quantizer.js
```

テストでは`readRSRC`をスタブ化し、変換オーケストレーション、API、XMLの原子的更新、座標クオンタイズ、ZIP Slip、シンボリックリンク、展開量制限、Azure UIのフロントエンド契約を確認します。実際のLabVIEWファイルによる互換性確認は、対象VIを使って画面のラウンドトリップ検証を実行してください。

## 構成

```text
.
├── app/
│   ├── main.py          # FastAPI / API / static hosting
│   ├── quantizer.py     # pylabview XML座標の検出・クオンタイズ
│   ├── service.py       # readRSRC実行・変換ワークフロー
│   ├── filesystem.py    # ジョブ・ZIP・XML・成果物管理
│   └── static/          # Azure寄せWeb UIとクオンタイズ画面
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── main.py
```

## ライセンス

このWebアプリはMIT Licenseです。`pylabview`を含む依存ライブラリは各ライセンスに従います。詳細は `THIRD_PARTY_NOTICES.md` を参照してください。
