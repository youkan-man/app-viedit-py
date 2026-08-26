# VI Edit

`pylabview` をWeb画面から操作し、LabVIEWのVI/RSRCファイルをXMLデータセットへ抽出し、XMLデータセットからVI/RSRCファイルを再構成するDockerアプリです。

- VI / VIT / CTL / CTT / LLB / MNU / RSRC / LVLIBP → XML + BIN/MAP等
- 主XMLをブラウザー上で表示・編集・保存
- XML + 副ファイルを再構成可能なZIPとしてダウンロード
- ZIPまたはXML一式からVIを再構成
- 抽出直後に自動で再構成し、元ファイルとのSHA-256比較
- 変換ログと生成ファイルを画面から取得
- ジョブの自動期限切れ、ZIP Slip対策、XML外部実体対策、アップロード上限

![Python](https://img.shields.io/badge/backend-Python%203.12-3776AB)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)
![Docker](https://img.shields.io/badge/host-Docker-2496ED)

## 起動

```bash
git clone https://github.com/youkan-man/app-viedit-py.git
cd app-viedit-py
docker compose up --build -d
```

ブラウザーで `http://localhost:8080` を開きます。

停止:

```bash
docker compose down
```

保存済みの変換ジョブも含めて削除:

```bash
docker compose down -v
```

## 使い方

### VI → XML

1. `VI → XML` を選択します。
2. `.vi` などのRSRCファイルを投入します。
3. ファイルを作成したLabVIEW環境に合う文字コードを選択します。日本語版WindowsのVIは通常 `shift_jis` から試します。
4. `VIを解析` を押します。
5. 主XMLを画面で編集するか、データセットZIPをダウンロードします。
6. `VIを再構成` を押すと、編集後のXMLと副ファイルからVIを生成します。

### XML → VI

最も確実なのは、このアプリが出力した `pylabview-dataset.zip` を投入する方法です。主XMLだけを投入した場合、XMLから参照されるBIN/XML等が不足すると再構成に失敗します。

複数ファイルを直接選択することもできますが、ブラウザーのファイル選択ではディレクトリ構造が失われます。サブディレクトリを含むデータセットはZIPを使用してください。

## なぜ「XMLデータセット」なのか

`pylabview` はRSRC内の既知ブロックをXMLへ変換しますが、未知・未対応・1:1再現にバイナリが必要なブロックはBIN等の副ファイルへ保存します。主XMLはそれらを参照しているため、再構成には一式が必要です。

このアプリのZIPは次の形です。

```text
manifest.json       # 主XMLの場所など
main.xml            # RSRCカタログ兼、既知ブロックのXML
main_*.xml          # 分離されたXMLブロック（VIによる）
main_*.bin          # rawブロック、コンパイル済みコード等（VIによる）
main_*.map          # マップ情報（VIによる）
```

## ラウンドトリップ検証

`抽出後に自動再構成` を有効にすると、次を自動実行します。

```text
original.vi → XMLデータセット → roundtrip-original.vi
```

結果は3種類です。

- **バイナリ完全一致**: SHA-256が一致しました。
- **再構成成功・バイナリ不一致**: pylabviewでは古いVIやLLBなどで、機能的に同等でも並びやパディングが異なる場合があります。LabVIEWで開いて確認してください。
- **再構成失敗**: 対象バージョン・ブロック・文字コードなどが未対応の可能性があります。画面のログを確認してください。

## pylabview互換性

依存先は `mefistotelis/pylabview` のコミット `69768647c18d2d792a259b69884b2433761c3a4f`（2026-07-31）へ固定しています。

上流では主にLabVIEW 2014とLabVIEW 6.0付属VIでテストされています。新しいLabVIEWバージョンも解析できる場合がありますが、XML化されるブロックが少なくなったり、再構成に調整が必要になったりします。重要な成果物は必ず元VIを残し、対象バージョンのLabVIEWで生成VIを開いて検証してください。

上流: [mefistotelis/pylabview](https://github.com/mefistotelis/pylabview)

## 設定

`docker-compose.yml` の環境変数、または `.env` で変更できます。

| 変数 | 既定値 | 内容 |
|---|---:|---|
| `VIEDIT_PORT` | `8080` | ホスト側の公開ポート |
| `VIEDIT_DATA_DIR` | `/data/jobs` | コンテナ内ジョブ保存先 |
| `VIEDIT_DEFAULT_TEXT_ENCODING` | `shift_jis` | 画面/APIの既定文字コード |
| `VIEDIT_MAX_UPLOAD_BYTES` | `134217728` | 1ジョブのアップロード・展開上限（128 MiB） |
| `VIEDIT_MAX_ARCHIVE_FILES` | `4096` | ZIP内の最大エントリ数 |
| `VIEDIT_MAX_XML_EDITOR_BYTES` | `8388608` | ブラウザー編集可能な主XML上限（8 MiB） |
| `VIEDIT_COMMAND_TIMEOUT_SECONDS` | `180` | pylabview 1処理のタイムアウト |
| `VIEDIT_JOB_TTL_SECONDS` | `86400` | ジョブ保持期間（24時間） |
| `VIEDIT_PYLABVIEW_COMMAND` | `python -m pylabview.readRSRC` | pylabviewコマンドの差し替え |

例:

```bash
VIEDIT_PORT=9000 VIEDIT_JOB_TTL_SECONDS=604800 docker compose up --build -d
```

## API

OpenAPI UI: `http://localhost:8080/api/docs`

主要エンドポイント:

| Method | Path | 内容 |
|---|---|---|
| `POST` | `/api/extract` | VI/RSRCをXMLデータセットへ抽出 |
| `POST` | `/api/import` | ZIP/XML一式を取り込み、VIを再構成 |
| `GET` | `/api/jobs/{id}` | ジョブ状態・ファイル一覧 |
| `GET` | `/api/jobs/{id}/xml` | 主XMLを取得 |
| `PUT` | `/api/jobs/{id}/xml` | 主XMLを検証して保存 |
| `POST` | `/api/jobs/{id}/rebuild` | 現在のXMLデータセットから再構成 |
| `GET` | `/api/jobs/{id}/bundle` | 再構成可能なZIPを取得 |
| `GET` | `/api/jobs/{id}/outputs/{name}` | 生成VI/RSRCを取得 |

抽出例:

```bash
curl -F 'file=@Example.vi' \
     -F 'text_encoding=shift_jis' \
     -F 'verify_roundtrip=true' \
     http://localhost:8080/api/extract
```

ZIPから再構成:

```bash
curl -F 'files=@pylabview-dataset.zip' \
     -F 'output_filename=rebuilt.vi' \
     -F 'text_encoding=shift_jis' \
     http://localhost:8080/api/import
```

## 開発・テスト

Dockerを使わずテストする場合は、Python 3.12を推奨します。

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
```

テストではpylabviewのテストダブルを使い、次を検証しています。

- 抽出 → XML編集 → 再構成 → ダウンロード
- データセットZIPの再投入
- ZIP Slip拒否
- DTD/外部実体を含むXMLの拒否
- 出力拡張子制限
- ジョブID・ファイルパスの境界検査

実ファイルの対応可否はVIのLabVIEWバージョンと内部ブロックに依存するため、画面のラウンドトリップ検証とLabVIEW本体で確認してください。

## セキュリティ上の扱い

VI/RSRCは信頼できない入力として扱います。

- pylabviewは別プロセスで実行し、タイムアウトを設定
- ZIPの絶対パス、`..`、重複パス、シンボリックリンク、暗号化エントリを拒否
- ZIP展開後の実バイト数とファイル数を制限
- XMLは`defusedxml`で検証し、DTD/外部実体を拒否
- ファイル名を正規化し、ジョブディレクトリ外へのアクセスを拒否
- コンテナは非root、read-only root filesystem、capabilityなしで実行

公開インターネットへ直接出す用途ではありません。必要ならリバースプロキシ側で認証、TLS、レート制限、さらに厳しいボディサイズ制限を追加してください。

## ライセンス

本アプリはMIT Licenseです。`pylabview` もMIT Licenseで、著作権は各上流作者に帰属します。
