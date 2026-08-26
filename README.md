# pylabview VI/XML Workbench

`pylabview` の `readRSRC` をWebブラウザから操作し、LabVIEWのVI/RSRCファイルをXMLデータセットへ展開したり、XMLデータセットからVI/RSRCファイルを再構成したりするDockerアプリです。

![Python](https://img.shields.io/badge/backend-Python%20%2B%20FastAPI-3776AB)
![Docker](https://img.shields.io/badge/host-Docker-2496ED)
![License](https://img.shields.io/badge/license-MIT-green)

![VI/XML Workbench UI](docs/ui-preview.svg)

## 主な機能

- VI、CTL、LLBなどのRSRCファイルをXMLへ展開
- メインXMLと補助XML/BINをデータセットZIPとして保存
- データセットZIPまたは単独XMLからVI/RSRCを再構成
- メインXMLをブラウザ上で編集・検証・保存
- XMLとして展開されたコンポーネント、端子、配線座標を指定粒度へ丸める
- 座標変更の対象ファイル、XMLパス、変更前後を適用前に確認
- 抽出直後のラウンドトリップ再構成とSHA-256比較
- 実行コマンド、標準出力、標準エラー、処理時間の表示
- `shift_jis`、`utf-8`、Windows/Mac系コードページの選択

## 必要なもの

- Docker Engine
- Docker Compose v2
- 生成したVIを最終確認する場合は、対象バージョンのLabVIEW

LabVIEW本体はDockerイメージには含まれません。XMLへの展開と再構成はコンテナ内の`pylabview`で行います。

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

ログを確認する場合:

```bash
docker compose logs -f --tail=200
```

停止する場合:

```bash
docker compose down
```

ジョブデータはDocker named volume `pylabview_data` に保存されます。既定では、最終更新から24時間を過ぎたジョブは、新しいジョブを作成したときに削除対象になります。

## 対応する入力ファイル

VIからXMLへの変換画面では、次の拡張子を選択できます。

```text
.vi .vit .ctl .ctt .llb .lvlib .lvlibp .lvclass
.lvproj .mnu .uir .lsb .rsrc
```

対応範囲はファイル形式とLabVIEWバージョン、および`pylabview`の解析状況によって異なります。

## 使い方

### VI / RSRCをXMLへ変換

1. `VI → XML`を選択します。
2. VIまたはRSRCファイルをドロップします。
3. 文字コードを選択します。
4. 必要に応じてラウンドトリップ検証を有効にします。
5. `XMLデータセットへ変換`を押します。
6. 変換後のデータセットZIPを保存します。

日本語版Windowsで作成されたVIでは、まず`shift_jis`を試してください。文字化けや変換エラーがある場合は、元の保存環境に合わせて文字コードを変更します。

### XMLからVI / RSRCを再構成

1. `XML → VI`を選択します。
2. このアプリが出力したデータセットZIP、または単独XMLをドロップします。
3. 必要に応じてメインXMLのパスと出力ファイル名を指定します。
4. 元ファイルと同じ文字コードを選択します。
5. `VI / RSRCを再構成`を押します。
6. 生成されたファイルをダウンロードします。

XMLへの展開結果には、メインXML以外の補助XMLやBINが含まれる場合があります。再構成にはデータセットZIPの使用を推奨します。単独XMLでは外部参照を解決できないことがあります。

### XMLを編集する

変換後のワークスペースでメインXMLを編集できます。

1. XMLを変更します。
2. `XMLを保存`を押します。
3. `このXMLから再構成`を押します。
4. 生成されたVIをLabVIEWで確認します。

保存時にXML構文と`RSRC`ルート要素を検証します。XMLを保存すると、以前の再構成結果とラウンドトリップ検証結果は旧版として扱われます。

既定では8 MiBを超えるメインXMLはブラウザ編集できません。その場合はデータセットZIPをダウンロードし、外部エディタで編集してから再アップロードしてください。

## 座標のクオンタイズ

データセット内のXMLに座標として展開されている値を、指定したグリッド粒度へ丸められます。

対象には次のような座標が含まれます。

- コンポーネントの矩形位置
- コネクタや端子の位置
- XMLとして展開された配線ポイント

操作手順:

1. グリッド粒度を1〜256 pxで指定します。
2. 丸め方式を選択します。
3. コンポーネント、コネクタ、配線から対象を選択します。
4. `差分を解析`を押します。
5. 対象ファイル、XMLパス、変更前後を確認します。
6. `データセットへ反映`を押します。
7. VIを再構成して結果を確認します。

矩形は既定では位置だけを移動し、元の幅と高さを維持します。`幅と高さも丸める`を有効にした場合は、矩形サイズも指定粒度へ合わせます。

座標形式は、矩形が`(left, top, right, bottom)`、ポイントが`(y, x)`です。

`compressedWireTable`や外部BINに保持されている配線情報は変更されません。対象となる座標がXMLへ展開されていない場合は、画面に警告が表示されます。

## ダウンロードできる成果物

ジョブの内容に応じて次の成果物を取得できます。

- XMLデータセットZIP
- メインXML
- ラウンドトリップ検証用RSRC
- 再構成したVI/RSRCファイル

## 設定

`docker-compose.yml`の環境変数で制限値や保存先を変更できます。

| 変数 | 既定値 | 内容 |
|---|---:|---|
| `WORK_ROOT` | `/data/jobs` | ジョブ保存先 |
| `MAX_UPLOAD_BYTES` | `268435456` | 1アップロードの最大サイズ（256 MiB） |
| `MAX_ARCHIVE_BYTES` | `536870912` | ZIP展開後の最大合計サイズ（512 MiB） |
| `MAX_ARCHIVE_FILES` | `10000` | ZIP内の最大ファイル数 |
| `COMMAND_TIMEOUT_SECONDS` | `300` | `readRSRC`のタイムアウト秒数 |
| `INLINE_XML_MAX_BYTES` | `8388608` | ブラウザ編集可能なXMLの最大サイズ（8 MiB） |
| `JOB_TTL_HOURS` | `24` | ジョブ保持時間 |
| `LOG_MAX_CHARS` | `100000` | 画面に保持するログの最大文字数 |
| `PYLABVIEW_COMMAND` | `readRSRC` | 実行するコマンド |

ポートを変更する例:

```yaml
services:
  app:
    ports:
      - "9000:8080"
```

変更後はコンテナを再作成します。

```bash
docker compose up --build -d
```

## API

OpenAPI UIは次のURLで確認できます。

```text
http://localhost:8080/api/docs
```

主なAPI:

| Method | Path | 内容 |
|---|---|---|
| `GET` | `/api/health` | アプリと`readRSRC`の状態確認 |
| `POST` | `/api/convert/vi-to-xml` | VI/RSRCをXMLデータセットへ変換 |
| `POST` | `/api/convert/xml-to-vi` | XML/ZIPからVI/RSRCを再構成 |
| `GET` | `/api/jobs/{job_id}` | ジョブ情報を取得 |
| `GET/PUT` | `/api/jobs/{job_id}/xml` | メインXMLを取得・更新 |
| `POST` | `/api/jobs/{job_id}/quantize/preview` | 座標変更をプレビュー |
| `POST` | `/api/jobs/{job_id}/quantize/apply` | プレビュー済み変更を反映 |
| `POST` | `/api/jobs/{job_id}/rebuild` | 現在のXMLから再構成 |
| `GET` | `/api/jobs/{job_id}/download/{artifact}` | 成果物を取得 |
| `DELETE` | `/api/jobs/{job_id}` | ジョブを削除 |

## トラブルシューティング

### 画面に「エンジン未検出」と表示される

コンテナログを確認してください。

```bash
docker compose logs --tail=200
```

イメージを再ビルドして改善するか確認します。

```bash
docker compose down
docker compose up --build -d
```

### 日本語が文字化けする

元VIを保存した環境に合わせて文字コードを変更します。日本語版Windowsでは`shift_jis`を最初に試してください。

### XMLから再構成できない

- 単独XMLではなくデータセットZIPを使用する
- 変換時と同じ文字コードを使用する
- 画面の標準エラーとコンテナログを確認する
- 対象バージョンのLabVIEWで生成物を開いて確認する

### ラウンドトリップでSHA-256が一致しない

ファイル内部のセクション順序、パディング、古いLabVIEW形式、LLBなどの影響で、編集していなくてもバイナリが一致しないことがあります。SHA-256比較だけでなく、LabVIEWで実際に開けるか確認してください。

## 制約

- XML化と再構成の対応範囲は`pylabview`に依存します。
- 未解析ブロックはBINとして保持される場合があります。
- XMLへ展開されていない座標や配線情報は編集できません。
- コンパイル済みVIから欠落したブロックダイアグラムは復元できません。
- 生成物が元ファイルとバイナリ一致するとは限りません。
- 生成物の最終確認には対象バージョンのLabVIEWを使用してください。

## セキュリティ

このアプリには認証機能がありません。インターネットへ直接公開せず、ローカル環境または信頼できるネットワークで使用してください。

アップロードされたZIPは、パストラバーサル、シンボリックリンク、展開後サイズ、ファイル数を検査してから展開されます。

## ライセンス

このWebアプリはMIT Licenseです。`pylabview`を含む依存ライブラリは各ライセンスに従います。詳細は[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)を参照してください。
