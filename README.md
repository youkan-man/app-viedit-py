# VI/XML Workbench

LabVIEWのVI/RSRCファイルを`pylabview`でXMLデータセットへ展開し、モデル接続の確認、XML編集、座標整列、VI/RSRCへの再構成を行うDocker Webアプリです。

## 主な機能

- VI、VIT、CTL、CTT、LLBなどをXMLデータセットへ展開
- メインXML、補助XML、未解析BINを相対パスを維持したZIPで保存
- 複数XMLのUID、参照、`wireID`、`conID`、親子関係を解決して1つのモデルグラフを作成
- モデルの名称、class、UID、XMLパス、X、Y、幅、高さ、接続先を表示
- wire単位のネットと、解決できなかった参照を表示
- コンポーネントの全プロパティ表示と、安全な値のフォーム編集
- メインXMLのテキスト編集
- コンポーネント、端子、XML展開済みワイヤ座標のグリッド量子化
- XMLデータセットからVI/RSRCを再構成
- ラウンドトリップ検証、成果物ダウンロード、実行ログ表示

## 起動

```bash
git clone https://github.com/youkan-man/app-viedit-py.git
cd app-viedit-py
docker compose up --build -d
```

ブラウザーで次を開きます。

```text
http://localhost:8080
```

停止:

```bash
docker compose down
```

ログ:

```bash
docker compose logs -f --tail=200
```

## 基本操作

### 取込

VI/RSRCまたはXMLデータセットを開きます。

- `VI → XML`: VI/RSRCをXMLデータセットへ展開
- `XML → VI`: XMLまたはデータセットZIPを読み込み、VI/RSRCを再構成

変換後はモデル、XML、座標、再構成の各ページが利用できます。

### モデル

データセット内の複数XMLを1つの構造として表示します。

`接続グラフ`では次を確認できます。

- モデルの位置とサイズ
- class、UID、取得元XML
- 端子、コネクタ、ワイヤ、ノード間の接続
- XMLファイル間の参照
- wire単位のネット
- ブロックダイアグラム、フロントパネル、コネクタペインの区分
- 一意に解決できなかった参照

検索、画面区分、種類で絞り込めます。グラフ上のモデルを選択すると、接続先と座標を表示します。

`コンポーネント・プロパティ`では、XML要素、属性、値、親子階層、参照、編集可能プロパティを確認できます。

### XML

メインXMLを直接編集し、データセットに含まれるXML/BIN等のファイルを確認します。

保存時にXML構文とメインXMLの`RSRC`ルートを検証します。保存後はモデルグラフを再解析し、以前の再構成結果と検証結果を旧版として扱います。

### 座標

XMLデータセット内の座標を指定粒度へ量子化します。

1. 粒度を1〜256で指定
2. 最近傍、小さい側、大きい側の丸め方式を選択
3. コンポーネント、端子、ワイヤから対象を選択
4. 差分を確認
5. データセットへ反映

矩形は既定で位置だけを移動し、幅と高さを維持します。オプションを有効にした場合だけサイズも丸めます。

### 再構成

現在のXMLデータセットからVI/RSRCを生成します。

次をダウンロードできます。

- XMLデータセットZIP
- メインXML
- ラウンドトリップ検証用RSRC
- 再構成したVI/RSRC

同じページで`pylabview`の実行コマンド、標準出力、標準エラーを確認できます。

## VI構造・コンポーネント

XMLとして展開された次の情報を使用します。

- `SL__object`、`SL__rootObject`
- class、UID、ID
- `bounds`、`termBounds`、`origin`、`termHotPoint`
- `SL__reference`
- `wireID`、`conID`
- node、term、tunnel、signal、DCO等の参照
- XMLファイル参照

参照IDはデータセット全体で解決します。候補が複数ある場合は、同じXMLファイル、同じ画面区分の順に優先します。一意に決められない参照は未解決として表示します。

`compressedWireTable`や外部BIN内部など、`pylabview`がXML構造として展開していない接続情報は推測で作成しません。

## プロパティ編集

画面から編集できる例:

- 名称、ラベル、説明
- 色、フォント、表示状態
- `value`、`default`、`min`、`max`、`step`
- 矩形と点

読み取り専用の例:

- class、UID、ID
- type、index、count、flags、version
- 参照先IDとファイル参照
- バイナリ値
- 安全な編集対象へ分類できない値

解析後にXMLが変更されていた場合は、古い解析結果による保存を拒否します。

## API

OpenAPI:

```text
http://localhost:8080/api/docs
```

主要エンドポイント:

| Method | Path | 内容 |
|---|---|---|
| `GET` | `/api/health` | アプリと`readRSRC`の状態 |
| `POST` | `/api/convert/vi-to-xml` | VI/RSRCをXMLデータセットへ展開 |
| `POST` | `/api/convert/xml-to-vi` | XML/ZIPからVI/RSRCを再構成 |
| `GET` | `/api/jobs/{job_id}` | ジョブ状態 |
| `GET` | `/api/jobs/{job_id}/model` | 構造サマリーと統合モデルグラフ |
| `GET` | `/api/jobs/{job_id}/components` | コンポーネント一覧 |
| `GET` | `/api/jobs/{job_id}/components/{component_id}` | コンポーネント詳細 |
| `PATCH` | `/api/jobs/{job_id}/components/{component_id}` | 安全なプロパティを更新 |
| `GET/PUT` | `/api/jobs/{job_id}/xml` | メインXML取得・保存 |
| `POST` | `/api/jobs/{job_id}/quantize/preview` | 座標差分を解析 |
| `POST` | `/api/jobs/{job_id}/quantize/apply` | 座標差分を反映 |
| `POST` | `/api/jobs/{job_id}/rebuild` | 現在のデータセットから再構成 |
| `GET` | `/api/jobs/{job_id}/download/{artifact}` | 成果物を取得 |
| `DELETE` | `/api/jobs/{job_id}` | ジョブ削除 |

## 設定

| 変数 | 既定値 | 内容 |
|---|---:|---|
| `WORK_ROOT` | `/data/jobs` | ジョブ保存先 |
| `MAX_UPLOAD_BYTES` | `268435456` | アップロード上限 |
| `MAX_ARCHIVE_BYTES` | `536870912` | ZIP展開後および解析の合計上限 |
| `MAX_ARCHIVE_FILES` | `10000` | ZIP内の最大ファイル数 |
| `COMMAND_TIMEOUT_SECONDS` | `300` | `readRSRC`タイムアウト |
| `INLINE_XML_MAX_BYTES` | `8388608` | ブラウザー編集可能なXML上限 |
| `JOB_TTL_HOURS` | `24` | ジョブ保持時間 |
| `LOG_MAX_CHARS` | `100000` | ログ保持文字数 |
| `PYLABVIEW_COMMAND` | `readRSRC` | 実行するコマンド |

## 対応範囲と制約

- 解析・再構成範囲は`pylabview`の対応状況に依存します。
- 未解析ブロックはBINとして保持され、内部の意味や接続は表示できません。
- XMLの変更内容によっては、再構成できてもLabVIEWで開けない場合があります。
- 元ファイルと再構成結果は、セクション順序やパディングの差でバイナリ一致しない場合があります。
- LabVIEW本体はDockerイメージに含まれません。成果物は対象バージョンのLabVIEWで確認してください。
- 認証機能はありません。ローカルまたは信頼できるネットワークで使用してください。

## ライセンス

MIT Licenseです。依存ライブラリのライセンスは[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。
