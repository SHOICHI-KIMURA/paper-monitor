# DESIGN: Paper Stock（図付き・コメント欄空欄設計）

作成日: 2026-07-02
対象: paper-monitor（PubMed週次収集 → IFフィルタ → Gemini分類・要約 → Notion保存 → LINE配信 → GitHub Pages）

これは設計書であり、実装はまだ行わない。

---

## 0. コンセプト（最重要・厳守事項）

**AIは「図と要点を運ぶ係」。学び・気づきのコメントはユーザー自身の言葉でのみ書く（Zettelkasten原則）。**

- AIが書いてよいもの: タイトル、ジャーナル名、日付、リンク、客観的事実の3行要約、図（PMCから取得できた場合）
- AIが**絶対に書いてはいけないもの**: 「自分コメント」プロパティの中身。解釈・評価・示唆・「これは〇〇に使える」といった一言も含めて、AIは一切書き込まない
- 溜まった「自分コメント」が、講演・記事のoutput原料になる。これはユーザーが後で書き足す前提の「空の器」であり、AIが埋めた瞬間にZettelkasten的な価値（＝自分の頭で考えた記録）が失われる
- 実装上もこの制約をコード上に明記する（後述 4-3）。将来誰かがこのコードを読んでも「なぜ自動生成しないのか」がわかるようにする

---

## 1. Notionエントリ構成（1論文＝1ページ）

現行の `scripts/notion_save.py` の `_properties()` が作るプロパティに、以下を追加する。

| プロパティ名 | 型 | 内容 | 誰が書くか |
|---|---|---|---|
| Title | title | 論文タイトル | AI（既存） |
| Journal | rich_text | ジャーナル名 | AI（既存） |
| Published Date | date | 発行日 | AI（既存） |
| URL | url | 論文リンク（DOI優先） | AI（既存） |
| Japanese Summary | rich_text | AI要約3行（**客観的事実のみ**。「重要」「注目すべき」等の評価語を含めない） | AI（既存。プロンプト強化） |
| **Figure** | files（Notionのファイル&メディア型） | PMCオープンアクセス論文の代表図1枚 | AI（新規） |
| **自分コメント** | rich_text | 学び・気づき・使えそうな講演/記事ネタ | **ユーザーのみ。AIは空欄で作成し、以後も一切書き込まない** |

「Why Important」等の既存プロパティは維持するが、Why Importantの文言も「客観的事実の言い換え」に留め、評価的な断定（「臨床的に重要」など）を避ける方向にプロンプトを見直す（4-2で詳述）。

### 図（Figure）取得の技術的実現方法

現行の依存関係（`requirements.txt`）は `requests`, `pyyaml`, `notion-client`, `python-dotenv`, `jinja2` のみで、BeautifulSoupやPMC専用SDKは入っていない。既存の `scripts/fetch_pubmed.py` がNCBI E-utilities（`requests` + `xml.etree.ElementTree`）で完結しているのと同じ思想を踏襲し、**追加ライブラリなしで実装可能**な経路を採用する。

**採用する経路: NCBI PMC + Europe PMC の組み合わせ**

1. **PMCID解決**: `fetch_pubmed.py` の `_find_doi()` と同様に、PubMed efetch結果のXML（`PubmedArticle`）内の `ArticleIdList` から `IdType="pmc"` のIDを探す。既にefetchで取得済みのXMLに含まれているため追加APIコール不要。PMCIDが無ければ非オープンアクセス、またはPMC未収載と判断し、図取得をスキップする（Notion側のFigureは空のまま）。

2. **オープンアクセス判定**: NCBI PMC OA Web Service（`https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={PMCID}`）を`requests.get()`で呼ぶ。オープンアクセスなら論文一式（tar.gz）のURLが返る。ただし画像1枚だけ欲しい場合はここまでダウンロードするのは重い。

3. **図URLの直接取得（推奨・軽量）**: Europe PMC REST APIを使う。
   - `https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/fullTextXML` でフルテキストXMLを取得し、`xml.etree.ElementTree`（既存コードと同じ標準ライブラリ）で `<fig>` 要素の `<graphic xlink:href="...">` を探す。
   - 見つかった画像ファイル名から、Europe PMCの画像配信URL `https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/bin/{graphic_href}` を組み立てて代表図（Figure 1相当、通常は最初の`<fig>`）を取得する。
   - この方式なら追加ライブラリ不要（`requests` + 標準`xml.etree.ElementTree`のみ）で、既存の `fetch_pubmed.py` のXMLパース手法をそのまま流用できる。

4. **Notionへの登録**: Notionの `files` プロパティは外部URLの参照（`{"type": "external", "external": {"url": "..."}}`）を受け付ける。Europe PMCの画像URLは公開URLなのでダウンロード・自前ホスティングは不要。`notion_save.py` の `_properties()` に以下のような形で追加する想定：
   ```python
   if paper.get("figure_url"):
       properties["Figure"] = {
           "files": [{"type": "external", "name": "figure.jpg", "external": {"url": paper["figure_url"]}}]
       }
   ```
   ※ Notion外部ファイルURLは、Notion側が定期的にアクセスして表示する仕組みのため、Europe PMCのURLが恒久的に生きている必要がある（Europe PMCは公的機関の永続APIなので基本的に問題ない）。

5. **失敗時のフォールバック**: PMCID無し／Europe PMC XMLに`<fig>`要素無し／リクエスト失敗、のいずれの場合もエラーにせず「Figureなしで保存」に倒す（既存コードの「不明ならlow/otherにする」という設計思想と一貫させる）。

**この設計を選んだ理由**: BeautifulSoup等の新規依存を増やさず、既存コードのXMLパース手法（標準ライブラリのみ）を踏襲できる。PMC OAの生tar.gzをダウンロードして展開する重い経路より、Europe PMC RESTのXML+画像URL方式の方が週次バッチ向けに軽量。

---

## 2. 週次配信（LINE・HTML digest）の変更

### 2-1. LINE配信（`scripts/line_messaging.py`）

現行はテキストのみ（`recommendation == "必読"` を最大3件、タイトルのみ）。

新設計:
- **最大5件**に変更（現行の `[:3]` を `[:5]` に変更）
- **図サムネイル付き**にする場合、LINE Messaging APIの `text` メッセージだけでなく **Flex Message**（カード型UIでサムネイル画像を横に並べられる）に切り替える必要がある
  - 現行は `{"messages": [{"type": "text", "text": message}]}` のシンプル送信
  - Flex Messageの `bubble` タイプで、各論文を「画像（Figure URL）＋タイトル＋Notionページへのリンクボタン」のカードにし、`carousel` で最大5件を横並びにする構成が自然
  - Figure URLが無い論文（非OA等）は、画像なし（テキストのみ）のbubbleにフォールバックする
- broadcast送信の仕組み自体（`LINE_BROADCAST_URL`、トークン、送信先ID不要）は変更しない

### 2-2. HTML digest（`scripts/digest_render.py` / GitHub Pages）

週次配信の主対象は上記LINE通知だが、GitHub Pages上のHTML digestも同じ「最大5件・図サムネイル付き」の原則に揃える。

- `_sort_papers()` の結果（必読 > 要約保存 > IF降順）を **上位5件にスライス**してからカード化する（全件表示ではなく5件に絞る）
- `_card()` に `figure_url` があれば `<img src="{figure_url}" ...>` をタイトル直下に追加する。無ければ現行どおりテキストのみのカードにする
- 5件に絞られなかった残りの論文もNotionには保存されている（digestは「今週のハイライト」に徹し、全件はNotion側で見る運用とする）

---

## 3. 月次「コメント済み論文」抽出（output原料リスト）

Notion DB上で、以下の条件のビュー（またはフィルタ）を新設する。

- **フィルタ条件**: 「自分コメント」プロパティが空でない（`is_not_empty`）
- **並び順**: Published Date 降順、または「自分コメント」が追記された順（Notionのlast_edited_timeでソートする運用でもよい）
- **月次の使い方**: 月初のセッションで、このビューを `notion-search` / `notion-fetch` 等のNotion MCPツールで取得し、「今月コメントが付いた論文一覧＋そのコメント本文」をまとめて提示する。これが講演・記事のネタ出しの材料になる
- 実装としては新しいコードは不要（Notion DB側のビュー追加のみ）。Claude Code側では、月次にNotion DBを「自分コメント is_not_empty」でクエリするだけで実現できる

---

## 4. 実装手順（このタスクでは実施しない。設計のみ）

### 4-1. `config/keywords.yaml` / `scripts/fetch_pubmed.py` / `config/journals_if.csv`
- 済み（Phase Bで対応）。`config/keywords.yaml` を `ai_terms`（DX・AI共通語）＋`tracks`（rhinology_dx / dysphagia_dx の domain_terms）構造に変更し、`scripts/fetch_pubmed.py` に `build_keyword_block()` を追加してトラック単位で `(ai_terms) AND (domain_terms)` を組み立て、トラック同士をORで結合するようにした。旧方式（`ent_keywords` + `if50_extra_terms` の単純OR）はコメントアウトで保持しつつ、コードもフォールバックとして読める形にしてある。

### 4-2. `scripts/llm_classify.py`
- `SYSTEM_PROMPT` / `USER_TEMPLATE` に「japanese_summary_3lines は客観的事実のみ、評価語（重要・注目・画期的等）を含めない」という指示を追加する
- 出力JSONスキーマは変更不要（既存の3行要約フィールドをそのまま使う）

### 4-3. `scripts/fetch_pubmed.py`
- `_parse_article()` で PMCID（`ArticleIdList` の `IdType="pmc"`）を抽出し、`Paper` dataclassに `pmcid: str` フィールドを追加する
- 新規関数 `fetch_figure_url(pmcid: str) -> str | None` を追加し、Europe PMC REST APIでfullTextXMLを取得 → 最初の `<fig><graphic>` のhrefを組み立てて返す。失敗時は `None` を返す（例外を投げない）

### 4-4. `scripts/notion_save.py`
- `_properties()` に `Figure`（files型、external URL参照）を追加
- **重要**: `_properties()` および周辺コードに、以下のコメントを明記する
  ```python
  # 「自分コメント」プロパティはここでは絶対に設定しない。
  # Zettelkasten原則: コメントはユーザー自身の言葉でのみ書く。AIによる下書き・自動生成は禁止。
  # 新規ページ作成時は「自分コメント」を空欄のまま残すこと（プロパティ自体を properties dict に含めない）。
  ```
- 新規ページ作成時、「自分コメント」プロパティには一切触れない（Notion側でデフォルト空欄のまま保存される）

### 4-5. `scripts/line_messaging.py`
- `[:3]` を `[:5]` に変更
- Flex Message形式への切り替え（画像付きカルーセル）。図が無い論文は画像なしのシンプルbubbleにフォールバック

### 4-5b. `scripts/digest_render.py`
- `_sort_papers()` の結果を `_card()` に渡す前に上位5件へスライスする
- `_card()` に `figure_url` があれば `<img>` タグを追加する分岐を入れる

### 4-6. Notion DB側の設定変更（コード外）
- プロパティ追加: `Figure`（ファイル&メディア型）、`自分コメント`（テキスト型）
- ビュー追加: 「自分コメント is_not_empty」でフィルタした月次レビュー用ビュー
- README.md の「Notion DBに必要なプロパティ」表にもこの2つを追記する

### 4-7. `README.md`
- プロパティ表に `Figure` / `自分コメント` を追記
- Notion AI貼り付け用プロンプトにも同様に追記

---

## 5. 変更しないもの

- IFフィルタの仕組み（`scripts/if_filter.py`）はそのまま
- PMID重複除外の仕組みはそのまま
- `digest_publish.py`（docsフォルダへのコピー・index.html更新の仕組み）はそのまま
- `digest_render.py` の全体構造（HTML生成の骨格・カードの基本デザイン）はそのまま。変更は「上位5件へのスライス」と「図タグの追加」のみ（4-5b参照）
