# SETUP.md（非エンジニア向け セットアップ手順）

このドキュメントは、paper-monitor（PubMed論文の週次自動収集システム）を実際に動かすための設定手順です。プログラミングの知識がなくてもできるように、専門用語には都度かんたんな説明を付けています。

---

## 0. 全体の流れ（イメージ）

1. 毎週日曜の朝、GitHub（コードを保管しているクラウドサービス）が自動で以下を実行する
   - PubMed（医学論文の検索データベース）から新着論文を取得
   - Gemini（Googleの生成AI）で論文を分類・要約
   - Notionに保存
   - LINEに通知
2. これを動かすには、「合言葉（Secrets＝秘密情報）」をGitHubに登録しておく必要がある
3. 登録が終われば、あとは自動で毎週動く

---

## 1. 必要なSecrets（合言葉）の一覧と取得場所

**Secrets（シークレット）とは**: パスワードやAPIキー（外部サービスを使うための合言葉）のような、他人に見せてはいけない情報のこと。コードの中に直接書かず、GitHub側の「金庫」に保管して、実行時だけ読み込む仕組みです。

`.env.example`（`/Users/shoichikimura/ClaudeCode/paper-monitor/.env.example`）に、必要な項目の一覧（値はダミー）が書かれています。実際の値はここには入れず、GitHub側に登録します。

| Secret名 | 何のためか | どこで取得するか |
|---|---|---|
| `NOTION_TOKEN` | Notionに論文データを書き込むための合言葉 | Notionの「連携（Integration）」設定画面で発行する社内用トークン。既存のNotion連携で使っているものと同じ仕組み |
| `NOTION_DATABASE_ID` | 論文を保存するNotionデータベースのID | 保存先データベースをNotionで開き、URLの中の32桁の英数字部分をコピーする |
| `GEMINI_API_KEY` | Google Geminiで論文を分類・要約するための合言葉 | Google AI Studio（`aistudio.google.com`）でAPIキーを発行する |
| `LINE_CHANNEL_TOKEN` | LINEに通知を送るための合言葉 | LINE Developersコンソールで、Messaging APIチャネルの「チャネルアクセストークン（長期）」を発行する |
| `DIGEST_BASE_URL` | 週次まとめページ（GitHub Pages）の公開URL | GitHubのPages設定後に決まるURL（後述の手順3で設定） |
| `NCBI_API_KEY`（任意） | PubMed検索を少し速くするための合言葉。無くても動く | NCBI（PubMedの運営元）のアカウント設定画面で発行 |

**注意**: 上記の実際の値（トークンやAPIキーそのもの）は、このSETUP.md含めどこにも書き込まないでください。値を扱うのは次の「2. GitHubへの登録」の画面上だけです。

---

## 2. GitHubへの登録手順

1. ブラウザでGitHubのリポジトリページ（`paper-monitor`）を開く
2. 右上あたりの「Settings（設定）」タブをクリック
3. 左メニューの「Secrets and variables」→「Actions」を開く
4. 「New repository secret（新しいシークレット）」ボタンを押す
5. 「Name（名前）」に上の表のSecret名（例: `NOTION_TOKEN`）を、「Secret（値）」に実際の値を入力して保存する
6. これを表の6項目それぞれについて繰り返す（`NCBI_API_KEY`は任意なので無くてもOK）

登録が終わると、GitHub Actions（自動実行の仕組み）がこれらの値を安全に読み込めるようになります。値は登録後、画面上でも二度と表示されません（更新はできます）。

---

## 3. GitHub Pages（週次まとめページ）の有効化

`docs/`フォルダの中身を、そのままWebページとして公開する設定です。

1. リポジトリの「Settings」→左メニューの「Pages」を開く
2. 「Source（公開元）」を `Deploy from a branch` にする
3. 「Branch」を `main`、フォルダを `/docs` に設定して保存する
4. 数分待つと、`https://（GitHubのユーザー名）.github.io/paper-monitor` のようなURLが発行される
5. そのURLを、手順2の `DIGEST_BASE_URL` というSecretに登録する（末尾に `/` は付けない）

このURLの `index.html` が、常に最新の週次まとめページを指すようになります。

---

## 4. GitHub Actions（自動実行の仕組み）の有効化

このリポジトリには `.github/workflows/weekly.yml` という設定ファイルがすでに入っており、これがGitHub Actionsの動作内容（「毎週日曜7時に実行する」等）を定義しています。

1. GitHubのリポジトリページ上部の「Actions」タブを開く
2. 初回はワークフローの有効化を促す画面が出るので「I understand my workflows, go ahead and enable them」のようなボタンを押す
3. 左側に「Weekly ENT Paper Digest」というワークフロー名が表示されればOK

Secretsの登録（手順2）が終わっていれば、これで毎週日曜7時（日本時間）に自動実行されます。

---

## 5. 手動でテスト実行する方法

毎週の実行を待たずに、今すぐ1回動かして確認したい場合の手順です。

1. GitHubのリポジトリの「Actions」タブを開く
2. 左側の「Weekly ENT Paper Digest」ワークフローをクリック
3. 右側に表示される「Run workflow」ボタン（プルダウン付き）をクリック
4. ブランチが `main` になっていることを確認して、緑色の「Run workflow」ボタンを押す
5. 数十秒〜数分で一覧に実行結果が表示される。緑のチェックマークなら成功、赤い✕なら失敗

これは `weekly.yml` の `on: workflow_dispatch:` という設定によって可能になっています（この設定自体は既に入っているので、追加作業は不要です）。

失敗した場合は、その実行結果をクリックすると、どのステップで何のエラーが出たかログが見られます。よくある原因は「Secretsの登録漏れ・タイプミス」「Notion DB側のプロパティ名の不一致」です（詳しくはREADME.mdの「トラブルシュート」を参照）。

---

## 6. 止め方（一時停止・完全に止める）

### 一時的に止めたい場合（おすすめ）

1. 「Actions」タブを開く
2. 左側の「Weekly ENT Paper Digest」をクリック
3. 右上の「...」（縦三点リーダー）メニューから「Disable workflow」を選ぶ
4. これで自動実行（毎週日曜）が止まる。手動実行（手順5）もできなくなる
5. 再開したいときは同じ場所に出る「Enable workflow」を押せば元に戻る

### 完全に止めたい場合

- 上記の「Disable workflow」で基本的に十分です
- さらに厳密に止めたい場合は、GitHubリポジトリの「Settings」→「Secrets and variables」→「Actions」から登録済みのSecretsを削除すると、仮にワークフローが動いても外部サービス（Notion・Gemini・LINE）に接続できず失敗するようになります

---

## 参考: 用語のかんたん解説

- **API（エーピーアイ）**: 別のサービス（NotionやGeminiなど）に対して、プログラムから「これをやって」とお願いするための窓口のこと
- **APIキー / トークン**: そのお願いをするときに提示する身分証明書のようなもの。他人に漏れると勝手に使われてしまうので厳重に扱う
- **Secrets（シークレット）**: GitHubが提供する「APIキーなどを安全に保管する金庫」の機能
- **GitHub Actions**: GitHub上でプログラムを自動実行してくれる仕組み。今回は「毎週日曜7時に論文取得プログラムを動かす」ために使っている
- **IF（インパクトファクター）**: その学術雑誌がどれくらい引用されているかを示す指標。数値が高いほど「よく参照される、影響力の大きい雑誌」とされる
- **workflow_dispatch**: GitHub Actionsの設定の一つで、「ボタンを押したら手動でも実行できる」機能のこと
