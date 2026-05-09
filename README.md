# ENT×High IF論文監視システム v1

PubMed新着から高インパクト誌の論文を取得し、LLMで耳鼻咽喉科・頭頸部外科向けに分類して、Notion DBへ保存し、1枚HTML Digestを生成してLINEへ通知するMVPです。

## できること

- PubMed E-utilitiesで直近期間の論文を取得
- `config/journals_if.csv` の20誌MVPでIFフィルタ
- GeminiでENT関連度、臨床インパクト、推奨度をJSON分類
- PMIDをキーにNotion DB重複を除外
- `outputs/digest_YYYY-MM-DD.html` を生成
- `docs/index.html` を最新Digestへ更新
- LINE Messaging APIで固定URLと必読Top3を通知

## 必要なSecrets

GitHub Actions Secrets、またはローカルの `.env` に以下を設定してください。

```env
NOTION_TOKEN=secret_xxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=xxxxxxxxxxxx
GEMINI_MODEL=gemini-2.5-flash
LINE_CHANNEL_TOKEN=xxxxxxxxxxxx
DIGEST_BASE_URL=https://your-username.github.io/paper-monitor
DIGEST_OUTPUT_DIR=outputs/
TZ=Asia/Tokyo
NCBI_API_KEY=xxxxxxxxxxxx
```

`NCBI_API_KEY` は任意です。無くても動きます。

`LINE_CHANNEL_TOKEN` はLINE DevelopersのMessaging APIチャネルで発行する長期チャネルアクセストークンです。通知は送信先ID不要のbroadcastで送ります。broadcastは、そのLINE公式アカウントを友だち追加しているユーザー全員に届きます。

## Notion DBに必要なプロパティ

Notion側で以下の列を作ってください。プロパティ名が違うと保存時にエラーになります。

| 名前 | 型 |
|---|---|
| Title | title |
| PMID | text |
| DOI | text |
| URL | url |
| Journal | text |
| IF | number |
| Tier | select: IF50, IF10 |
| Published Date | date |
| ENT relevance | select |
| Category | select |
| Clinical Impact | select |
| Recommendation | select |
| Japanese Summary | rich_text |
| Why Important | rich_text |
| Read Status | select: 未読, 既読 |

`Read Status` はこのMVPでは未設定です。あとでNotion側の運用に合わせて追加できます。

## Notion AIに貼るDB作成プロンプト

以下をNotion AIに貼って、論文保存用データベースを作ってください。

```text
耳鼻咽喉科・頭頸部外科向けの「ENT High IF Paper Monitor」というフルページデータベースを作成してください。

目的:
PubMedから自動取得した高インパクト論文を保存し、PMIDで重複管理し、読む優先度と臨床的重要性を一覧できるようにする。

データベースのプロパティ:
- Title: タイトル型。論文タイトルを入れる。
- PMID: テキスト型。PubMed IDを入れる。重複確認に使うので必須。
- DOI: テキスト型。
- URL: URL型。論文ページまたはdoi.orgリンクを入れる。
- Journal: テキスト型。
- IF: 数値型。Impact Factorを入れる。
- Tier: セレクト型。選択肢は IF50, IF10。
- Published Date: 日付型。
- ENT relevance: セレクト型。選択肢は high, middle, low。
- Category: セレクト型。選択肢は head_neck_oncology, rhinology, allergy, airway, hearing, vestibular, dysphagia, microbiome, AI, thyroid, salivary, other。
- Clinical Impact: セレクト型。選択肢は high, middle, low。
- Recommendation: セレクト型。選択肢は 必読, 要約保存, スキップ。
- Japanese Summary: テキスト型またはリッチテキスト型。日本語3行要約を入れる。
- Why Important: テキスト型またはリッチテキスト型。耳鼻咽喉科医にとって重要な理由を入れる。
- Read Status: セレクト型。選択肢は 未読, 既読, 保留。

ビュー:
1. 今週の必読: Recommendation が 必読 のものを上に表示。Published Date の降順。
2. 未読: Read Status が 未読 または空のものを表示。
3. Head & Neck: Category が head_neck_oncology, thyroid, salivary のものを表示。
4. 鼻・アレルギー・気道: Category が rhinology, allergy, airway のものを表示。
5. AI・画像・Microbiome: Category が AI または microbiome のものを表示。

注意:
外部連携から保存するため、プロパティ名は上記と完全一致にしてください。英字の大文字小文字、半角スペースも変えないでください。
```

## ローカル実行

```bash
cd paper-monitor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## GitHub Pages設定

1. GitHubのリポジトリ設定で Pages を開く
2. Sourceを `Deploy from a branch` にする
3. Branchを `main`、フォルダを `/docs` にする
4. `DIGEST_BASE_URL` に Pages のURLを入れる

固定URL `${DIGEST_BASE_URL}/index.html` が常に最新Digestを指します。

## 設定変更

- 対象誌は `config/journals_if.csv` に追加します。
- ENTキーワードや取得期間は `config/keywords.yaml` で調整します。
- 取得件数上限は `max_results` です。

## トラブルシュート

### Notion保存でエラーになる

DBのプロパティ名と型を確認してください。特に `PMID` は text、`Title` は title が必要です。

### LLM JSONパースに失敗する

最大2回リトライします。それでも失敗した場合はログにPMIDと原因が残ります。抄録が極端に長い場合は先頭6000文字だけ送っています。

### Digestは生成されるがLINEが来ない

`LINE_CHANNEL_TOKEN` を確認してください。broadcast送信なので `LINE_TO_ID` は不要です。LINE公式アカウントを友だち追加していない端末には届きません。

### PubMed取得が少ない

`config/keywords.yaml` のキーワード、または `config/journals_if.csv` のjournal名をPubMed表記に合わせてください。このMVPは簡易正規化のみで照合します。

## メモ

- APIキーやトークンはコードに直書きしません。
- GeminiにはHTMLを直接作らせず、JSON分類だけを担当させます。
- 重複除外はPMIDで行います。
- `outputs/` は生成物置き場なのでGit管理から外しています。
