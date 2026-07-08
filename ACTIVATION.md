# ACTIVATION.md（稼働ランブック）

このドキュメントは、paper-monitor（PubMed週次自動収集システム）を「実際に動く状態」にするための、上から順に実行するチェックリストです。SETUP.mdの内容を実行順に並べ替え、コピペ用コマンドと確認ポイントを添えたものです。専門用語には都度かんたんな説明を付けています。

対象リポジトリ: `/Users/shoichikimura/ClaudeCode/paper-monitor`（これが正本）
GitHubリポジトリ: `SHOICHI-KIMURA/paper-monitor`

**注意**: `~/Documents/GitHub/paper-monitor` は旧クローンです。今後の作業対象にしないでください（後述「旧クローンについて」参照）。

---

## 🟢 2026-07-02 稼働ステータス（このセクションが最新の真実）

当日の調査で「未稼働」は誤りと判明。**v1は2026年5月から毎週稼働しており、6/27にGemini APIのモデル廃止（400エラー）で故障**していた。同日夜に以下を実施済み：

- Secrets: 全6項目設定済み（NOTION_TOKEN / GEMINI_API_KEY / LINE_CHANNEL_TOKEN は5月から有効なものを流用。NOTION_DATABASE_ID は既存の正本DBに向け直し済み。DIGEST_BASE_URL 設定済み。NCBI_API_KEY は未設定＝任意）
- GitHub Pages: 有効化済み（https://shoichi-kimura.github.io/paper-monitor/）
- 書き込み先の正本DB: **📚 DB-ENT High IF Paper Monitor**（`e7427fbec1764fc9922066d4552fb884`）。morning-routine・/pubmed-weekly が参照する「Paper Monitor DB」と同一。**下のステップ1（DB新規作成）は実行禁止**（重複DBを作ってしまうため。手順は参考として残置）
- Geminiモデル: `gemini-flash-latest` に変更＋モデル廃止時の自動フォールバック機構を実装（scripts/llm_classify.py）
- 失敗時のLINE通知ステップを追加（気づける最小運用）
- v1のコードはブランチ `v1-archive` に保全

**2026-07-08 追加修正**: 「見つかる論文が少なすぎる」というユーザー指摘を受け、収集条件を「耳鼻科ドメイン語（OR）」に戻し、「AI/DX」はヒット後のタグ（チェックボックス＋専用ビュー）に格下げ。週44件取得→28件保存に回復（詳細: `~/dotfiles/.claude/PUBMED-SYSTEMS.md`）。この時に**pushの成否確認を怠り、一度古いコミットのままテスト実行してしまった**（`git push ... | tail -1` でexit codeが握りつぶされ `&&` が素通り）。以後、pushは`| tail`を挟まず素の終了コードで確認するか、直後に`git log origin/main`でSHA一致を見ること。

以下の手順書は「ゼロから再構築する場合」の参考資料。通常運用で使うのは「ステップ6: 手動テスト実行」「停止方法」のみ。

---

## 事前確認（このドキュメント作成時点の静的チェック結果）

コードとSETUP.md/README.mdを突き合わせた結果、致命的なバグは見つかりませんでした。以下は稼働前に知っておくとよい軽微な注意点です。

- README.mdの「必要なSecrets」の環境変数例に `GEMINI_MODEL` と `TZ` が含まれていますが、この2つはGitHub Secretsとして登録する必要はありません（`weekly.yml` に既に固定値で書き込み済みのため）。GitHub Secretsとして登録が必要なのは本ドキュメント下記の6項目だけです。
- Gemini分類のAPI呼び出しは失敗時に自動で最大3回リトライします（`scripts/llm_classify.py`）。ただしプログラム全体（`main.py`）には失敗時の通知処理が無いため、リトライを使い切って失敗した場合はGitHub Actionsの実行結果が赤い✕になるだけです。GitHubは既定でActions失敗時に登録メールアドレスへ通知を送るので、それで気づける想定です。
- Notion DB側のプロパティ名・型が1つでも不一致だと、保存処理全体が例外で止まります（PMIDでの重複チェックも失敗します）。README.mdの「Notion AIに貼るDB作成プロンプト」をそのまま使えば型のズレは防げます。

---

## ステップ0: 全体像

1. GitHub Secrets（合言葉の金庫）に5〜6個の値を登録する
2. Notion側にデータベースを作る（README.mdのNotion AI貼り付けプロンプトを使用）
3. GitHub Pagesを有効化する（週次まとめページの公開先）
4. Pages URLが決まったら `DIGEST_BASE_URL` を再設定する（ここだけ順番が前後する）
5. コードをpushしてActionsを有効化する
6. 手動テスト実行で動作確認する

---

## ステップ1: Notion側の準備

- [ ] README.md記載の「Notion AIに貼るDB作成プロンプト」をコピーし、Notion AIに貼って「ENT High IF Paper Monitor」データベースを作成する
- [ ] 作成したデータベースのURLを開き、32桁の英数字ID（`NOTION_DATABASE_ID`になる値）をメモする
- [ ] 既存のNotion連携（Integration）がこのデータベースにアクセスできるよう、データベース右上の「接続」からNotion連携を追加する（Notion連携を初めて使う場合は https://www.notion.so/my-integrations で新規発行し、そのトークンが `NOTION_TOKEN` になる）

---

## ステップ2: 各Secretの取得場所

| Secret名 | 取得場所 | 備考 |
|---|---|---|
| `NOTION_TOKEN` | https://www.notion.so/my-integrations （Notion連携設定画面） | 「Internal Integration Token」をコピー。`ntn_` から始まる文字列（古い連携では `secret_` 始まり） |
| `NOTION_DATABASE_ID` | ステップ1で作成したNotion DBのURL | URL中の32桁の英数字部分 |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey （Google AI Studio） | 「Create API key」で発行 |
| `LINE_CHANNEL_TOKEN` | LINE Developersコンソール（https://developers.line.biz/console/） → 対象のMessaging APIチャネル → 「Messaging API設定」タブ | 「チャネルアクセストークン（長期）」を発行。まだLINE公式アカウント／Messaging APIチャネルが無い場合は先にチャネル作成が必要 |
| `DIGEST_BASE_URL` | ステップ4で確定するPages URL | 最初は仮の値でも登録可（後で更新する） |
| `NCBI_API_KEY`（任意） | https://www.ncbi.nlm.nih.gov/account/settings/ （NCBIアカウント設定） | 無くても動く。設定するとPubMed検索のレート制限が緩和される |

---

## ステップ3: GitHub Secretsへの登録

`gh`コマンド（GitHub CLI）でコピペ登録する場合、値の部分はプレースホルダです。実際の値に置き換えて実行してください。ブラウザのSettings画面から登録しても同じです（SETUP.md参照）。

```bash
gh secret set NOTION_TOKEN --repo SHOICHI-KIMURA/paper-monitor
# プロンプトが出たら値を貼り付けてEnter（値を引数に直書きしない方が履歴に残らず安全）

gh secret set NOTION_DATABASE_ID --repo SHOICHI-KIMURA/paper-monitor

gh secret set GEMINI_API_KEY --repo SHOICHI-KIMURA/paper-monitor

gh secret set LINE_CHANNEL_TOKEN --repo SHOICHI-KIMURA/paper-monitor

gh secret set DIGEST_BASE_URL --repo SHOICHI-KIMURA/paper-monitor
# 仮の値でOK。ステップ5でPages URL確定後に上書きする

# 任意
gh secret set NCBI_API_KEY --repo SHOICHI-KIMURA/paper-monitor
```

チェックリスト：

- [ ] `NOTION_TOKEN` 登録済み
- [ ] `NOTION_DATABASE_ID` 登録済み
- [ ] `GEMINI_API_KEY` 登録済み
- [ ] `LINE_CHANNEL_TOKEN` 登録済み
- [ ] `DIGEST_BASE_URL`（仮でよい）登録済み
- [ ] `NCBI_API_KEY`（任意・スキップ可）

登録確認コマンド（値は表示されず名前だけ一覧されます）：

```bash
gh secret list --repo SHOICHI-KIMURA/paper-monitor
```

---

## ステップ4: GitHub Pagesの有効化

- [ ] リポジトリの Settings → Pages を開く
- [ ] Source を `Deploy from a branch` にする
- [ ] Branch を `main`、フォルダを `/docs` にして保存する
- [ ] 数分待って `https://shoichi-kimura.github.io/paper-monitor` のようなURLが発行されるのを確認する

**循環ポイント（重要）**: `docs/index.html` はActionsの初回実行が終わるまで存在しない可能性があります。Pages自体は空でも有効化でき、URLは先に確定します。URLが確定したら、そのURLをステップ3で仮登録した `DIGEST_BASE_URL` に上書き登録してください（末尾に `/` は付けない）。

```bash
gh secret set DIGEST_BASE_URL --repo SHOICHI-KIMURA/paper-monitor
# 確定したPages URLを貼り付け
```

- [ ] `DIGEST_BASE_URL` をPages確定URLで再設定した

---

## ステップ5: pushしてActionsを有効化する

このステップは、リポジトリの状態を見てユーザー自身（またはユーザーの指示で）実行してください。このドキュメント自体はpushを行っていません。

- [ ] 変更をコミットし、GitHubへpushする
- [ ] GitHubリポジトリの「Actions」タブを開く
- [ ] 初回はワークフロー有効化を促す画面が出るので、案内に従って有効化する
- [ ] 左側に「Weekly ENT Paper Digest」ワークフローが表示されることを確認する

---

## ステップ6: 手動テスト実行

- [ ] Actionsタブ → 「Weekly ENT Paper Digest」を開く
- [ ] 「Run workflow」ボタン → ブランチが `main` であることを確認 → 緑の「Run workflow」を押す

コマンドで実行する場合：

```bash
gh workflow run weekly.yml --repo SHOICHI-KIMURA/paper-monitor
```

実行状況の確認：

```bash
gh run list --repo SHOICHI-KIMURA/paper-monitor --workflow=weekly.yml --limit 5
```

### 確認ポイント（成功判定）

- [ ] Actions実行結果が緑のチェックマークになっている
- [ ] Notion DB「ENT High IF Paper Monitor」に新しい行（論文）が増えている（対象論文が0件の週は増えないこともあります。ログで「No IF-matched papers found」等が出ていないか確認）
- [ ] LINEに通知が届く（LINE公式アカウントを友だち追加している端末のみ。broadcast配信のため個別の宛先設定は不要）
- [ ] Pages URL（`DIGEST_BASE_URL/index.html`）を開くと最新のDigestページが表示される

うまくいかない場合は、Actions実行結果の各ステップログを開いてエラー内容を確認してください。よくある原因はREADME.mdの「トラブルシュート」章、および本ドキュメント冒頭の「事前確認」を参照してください。

---

## コスト注記

週1回（日曜7時）の実行を前提にした見立てです。実際の論文件数により変動しますが、目安として記載します。

- **Gemini API（`gemini-2.5-flash`）**: 無料枠あり（Google AI Studio経由の場合、モデルや時期により条件が変わるため最新情報は https://ai.google.dev/pricing を確認してください）。週次で対象論文が数件〜数十件程度であれば、1回の実行で消費するトークン量はごく小さく、無料枠の範囲に収まる可能性が高いです。無料枠を超えた場合の従量課金も1論文あたり数円未満のオーダーが一般的です。念のため実行後にGoogle AI StudioのUsageページで確認することを推奨します。
- **GitHub Actions**: プライベートリポジトリの場合、Freeプランで月2,000分の無料枠があります。このワークフローは依存インストール＋Python実行で数十秒〜数分程度と見られ、週1回なら月4回×数分＝10〜20分程度の消費に収まり、無料枠内で十分です。
- **LINE Messaging API**: 無料プラン（コミュニケーションプラン）でも月200通までのメッセージ送信枠があります。broadcast配信は「友だち登録している人数」分をメッセージ通数として消費する点に注意してください。友だちが多い場合は、週1回のbroadcastでも月の送信数を圧迫する可能性があるため、無料枠の残数をLINE Official Account Managerでときどき確認することを推奨します。

**見立て**: 週1実行・少人数の友だち登録・論文十数件程度という前提であれば、3サービスとも無料枠内に収まる可能性が高いです。ただしLINEの友だち数やGemini/GitHub側の料金体系は変わることがあるため、運用開始後1〜2ヶ月は各サービスの使用量画面を一度確認しておくと安心です。

---

## 停止方法（ロールバック）

一時停止したい場合は、Actionsタブ →「Weekly ENT Paper Digest」→ 右上「...」→「Disable workflow」を選ぶだけです（1手順で完全に自動実行が止まり、再開は同じ場所の「Enable workflow」で戻せます）。

---

## 旧クローンについて

`~/Documents/GitHub/paper-monitor` は今回の正本（`/Users/shoichikimura/ClaudeCode/paper-monitor`）とは別の、古いクローンです。今後の作業では触らず、混乱を避けるためアーカイブ（フォルダ名を変える、または別の場所に退避する）ことを推奨します。削除するかどうかはユーザー自身の判断で行ってください（本ドキュメント・本タスクでは削除しません）。
