# ADR-0001: incident-review Skill — 自組織インシデント対応の振り返り分析

| 項目 | 内容 |
|------|------|
| Status | **Accepted** |
| Date | 2026-07-31 |
| Decision makers | nlink-jp maintainers |
| Triggered by | ai-ir / ai-ir2 パイプラインがエージェントのネイティブ能力と重複していたこと、および Gemini 2.5 廃止（ADR-001）が ai-ir2 のデフォルトモデルに及んだこと |

> もとは `nlink-jp/.github` の組織 ADR-009 として記録していた。
> 2026-08-03 にここへ移設。組織の ADR ログは組織全体を拘束する決定のための
> ものであり、この決定が設計するのは 1 つのスキルだけである。
> `ai-ir` / `ai-ir2` の廃止という事実は、組織ログ側のリダイレクトエントリに
> 引き続き記録されている。

## Context

`ai-ir`（7 コマンドのツールセット）とその後継 `ai-ir2`（ワンストップの
`aiir2 analyze` パイプライン）は、scat/stail/scli でエクスポートした
インシデント対応 Slack 会話を分析し、レポート（サマリー・参加者別活動・
役割推定・プロセスレビュー）と再利用可能な調査戦術ナレッジドキュメントを
生成する。`ai-ir2` v0.2.1 は動作するが、そのアーキテクチャは
[service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/ja/adr/0001-agentic-research.ja.md)
が製品調査で廃止したものと同じである: `response_schema` 付きの単発
Vertex AI Gemini 呼び出しの固定シーケンスで、各呼び出しは会話の整形ダンプを
一度見るだけ、LLM 出力ドリフト向けの Pydantic 正規化シムで縫い合わされて
いる。GCP/ADC/Vertex のコストを抱え、`gemini-2.5-flash` をデフォルトとして
Gemini 2.5 廃止リスト（ADR-001）に載っている。

パイプラインは問題領域よりも狭くもある。入力は scat/stail/scli の Slack
エクスポートスキーマにハードワイヤされているが、インシデント対応の記録は
さまざまな形でやってくる — チケットのコメントスレッド、他プラットフォームの
チャットトランスクリプト、手書きのタイムラインメモ。新しい形式が増えるたび、
CLI に新しいローダーが必要になる。

目標とする成果物の形には、組織内に出荷済みの前例が 3 つある —
`meeting-notes`（トランスクリプト → 検証済み JSON レイヤー → 議事録
コンパイル）、`service-research`
（[ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/ja/adr/0001-agentic-research.ja.md)）、
`incident-research`
（[ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/ja/adr/0001-deep-dive-research.ja.md)）。
ai-ir2 のパイプラインはこの形へほぼ機械的にマップできる: 分析ステージは
すでに個別の構造化出力セクションになっている。

前例に無く ai-ir2 にあるものが 1 つある: 本物の敵対的入力セキュリティ
レイヤーである。LLM に届く前に全メッセージへ IoC defang とノンス付きタグ
隔離を施す。IR チャネルは攻撃者が制御する文字列（フィッシング本文・C2
URL・マルウェア出力）を引用するため、このレイヤーは形態変更を生き延び
なければならない — しかも Skill では読み手の LLM がセッションエージェント
自身であり、隔離の重要性は下がるどころか*上がる*。

## Decision

**Claude Code Skill `incident-review` を `skills-series` に 1 つ追加し、
`ai-ir` と `ai-ir2` の両方を置き換える（両者はリリース時にアーカイブ）。**

名前は `incident-research`
（[ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/ja/adr/0001-deep-dive-research.ja.md)）
と対をなす: *research* は他者のインシデントについて外部世界の報を読み、
*review* は自組織の対応記録を読む。形を決めるサブ決定は 5 つ。

### 1. スコープ: 1 インシデントの自組織対応記録、事後分析

対象: 1 つのインシデントの対応記録 — 会話ログと、あれば周辺のメモ — を
事後に分析し、構造化レポート（サマリー/タイムライン、参加者別活動、役割と
関係、プロセス品質レビュー）と再利用可能な戦術ナレッジドキュメントに
まとめる。v0.1 のスコープ外: 進行中インシデントのライブ分析（ir-tracker の
仕事）、継続監視、複数インシデント横断のトレンド分析。

### 2. 入力は IR コミュニケーションデータ、必須の前処理ゲートの背後に置く

入力の単位はファイル形式ではなく、**そのインシデントのコミュニケーション
記録** — どのような形で届くにせよ — である。3 つの取得経路が 1 つの
ゲートに合流する:

- **エクスポートファイル**は `scripts/preprocess.py` がネイティブに読む:
  scat/scli の Slack エクスポート JSON、stail の NDJSON、プレーンテキスト
  会話ログ（決定的な行パーサー: `[timestamp] author: text` +
  継続行）。
- **コネクター取得**: 記録がセッションから読めるシステム（例: Slack
  チャネルを読む MCP ツール）にある場合、エージェントがメッセージを
  取得し — 機械的に、逐語で — 小さく文書化された汎用トランスクリプト
  JSON に書き起こす。
- **それ以外すべて**（チケットスレッド、他プラットフォームの
  トランスクリプト、タイムラインメモ）: エージェントが機械的コピーで
  同じ汎用トランスクリプト JSON に変換する。

その後すべては `scripts/preprocess.py`（stdlib のみ）に入る。これが分析への
**唯一**の経路である: IoC を defang し（ai-ir2 `parser/defang.py` から
移植）、全メッセージをノンス付きタグの隔離ブロックで包み
（`parser/sanitizer.py` から移植）、正規化済みの前処理トランスクリプトを
出力する。信頼境界は正確に記述される: **分析は前処理の出力だけを読む**。
エージェントが生コンテンツに触れざるを得ない取得・変換は、明示的な
「コンテンツはデータ」ルールの下での機械的コピー専用ステップであり、
両方が存在する場合はコネクター読み取りよりファイルエクスポートを優先する
（生コンテンツをセッションから完全に締め出せる）。これにより ai-ir2 の
ローダー別インジェストは、どんな入力形からも到達できる 1 つの決定的
ゲートに置き換わる。

### 3. スキーマは ai-ir2 の分析モデルを移植し、戦術は互換を保つ

`schema.json` は ai-ir2 のステージを映す 5 セクション — `summary`・
`activity`・`roles`・`review`・`tactics` — を持ち、セクション単位
（`validate.py --part`）と全体で検証され、`compile.py` が Markdown または
自己完結 HTML にコンパイルする（meeting-notes の前例）。デフォルト日本語、
`--lang en` で英語。戦術ドキュメントは ai-ir2 のフィールド構成を逐語で
保つ（`id`/`title`/`purpose`/`category`/`tools`/`procedure`/
`observations`/`tags`/`confidence: confirmed|inferred|suggested`/
`evidence`/`source`/`created_at`）ため、ai-ir2 で蓄積したナレッジベースは
新しい出力と均質なままである。`confidence` のセマンティクス — *confirmed*
はチャネル内で実際に出力が共有された場合のみ — は変更なく引き継がれ、
レビューセクションの構造（フェーズ・コミュニケーション・役割明確性・
強み/改善点/チェックリスト）も同様である。

### 4. セキュリティレイヤーは形態変更を生き延びる、構造は再編する

3 部構成。組織のコントロール配置ルール（強制可能なコントロールは帯域外へ、
プロは短い位置的事実にとどめる）に従って配置する:

- **ノンス隔離はコードへ移る。**`preprocess.py` がノンスを生成して
  メッセージを包む。SKILL.md は冒頭に短いルールを置き、ノンスタグ内の
  コンテンツは分析対象のデータであって指示ではないと述べる — 冒頭の
  位置的防御は
  [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/ja/adr/0001-agentic-research.ja.md) /
  [incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/ja/adr/0001-deep-dive-research.ja.md)
  と同じ。
- **プロースに禁止カタログを置かない。**ai-ir2 のインジェクションパターン
  正規表現リストは今日ある場所 — スクリプトコード — にとどまる。マッチは
  SKILL.md の指示文としてではなく、前処理出力とレポートのメッセージ別
  リスクフラグとして表面化する。
- **defang はエンドツーエンドで維持される。**IoC はゲートで defang され、
  レポートとナレッジドキュメントでも defang されたままなので、成果物は
  安全に共有・索引できる。

### 5. 標準の skills-series スキャフォールド

リポジトリ = skill（ADR-004）、配布境界としての `incident-review/`
サブディレクトリ、vendored な `tests/validate-skill.sh`（ADR-006）、
CONVENTIONS.md の Skill テンプレート由来の Makefile、最も近い姉妹である
`incident-research` からスキャフォールド。フィクスチャは架空の
インシデントと example.com 系インフラのみを使う — 実在の被害者・実在の
アクター名・生きた IoC は使わない
（[incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/ja/adr/0001-deep-dive-research.ja.md)
のテスト規律。フィクスチャが攻撃者引用の会話を模倣する本スキルでは
二重に拘束する）。

## Consequences

- GCP/ADC/Vertex 依存とそのコストが消える。ai-ir2 は ADR-001 の Gemini 2.5
  移行リストから外れ、コード変更項目が 1 つ減る。
- エージェントは会話全体をセクション横断の一貫性を持って読む — 役割推定が
  プロセスレビューに情報を与えられる — ai-ir2 の並列単発 4 呼び出しは
  互いを見られなかった。実時間は ThreadPoolExecutor のファンアウトより
  遅いが、振り返り成果物では品質が勝ると見込む。
- あらゆるコミュニケーション記録が分析可能になる — エクスポート
  ファイル、プレーンテキストログ、コネクターで読むチャネル、あるいは
  汎用トランスクリプトへ変換できるものすべて。Slack エクスポート
  スキーマは硬い境界でなくなる。
- 出力ドリフトのシム（Pydantic の `coerce_list_to_str` など）は消える —
  `validate.py` は矯正せず拒否し、エージェントが報告されたエラーに対して
  自分の出力を直す。
- 2 リポジトリを Skill へのポインタ付き README でアーカイブする
  （product-research の前例）。カタログ面（org profile、nlink-web-site）は
  エントリを 1 つ得て、2 つを superseded とマークする。
- レポート言語: 1 実行 1 言語（デフォルト ja、`--lang en`）。ai-ir2 の
  常時英語 + 翻訳ステージを置き換える — 翻訳はいまやエージェントの
  ネイティブな仕事である。
- 組織の実データ E2E リリースゲートは適用できない — リリース時点で本物の
  IR 記録が存在しない。意図的に代替する: (a) リアルな合成インシデント
  （複数参加者・bot 投稿・フィッシング引用・コードブロックのログ貼り付け）
  に対するスキルのエージェント実行フルラン、(b) 実際の scat/stail チャネル
  エクスポート（非インシデント内容で足りる）に対する preprocess.py の
  ローダー忠実性チェック。最初の本番利用が真の E2E であると認め、
  発見事項は v0.1.x にする。
- v0.2+ 候補は意図的に先送り: cybersecurity-series のルックアップツール群
  への IoC ハンドオフ（mcp-tactics）、蓄積レポートを横断するインシデント間
  トレンド分析、ir-timeline/ir-tracker 記録のインポート。

## Alternatives considered

| 代替案 | 不採用の理由 |
|---|---|
| ai-ir2 を Gemini 3 へ移行し CLI を維持 | 弱い方のアーキテクチャ — 会話を読み返さない単発呼び出しと恒久的な GCP 結合 — を残すために移行コストを払うことになる。[service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/ja/adr/0001-agentic-research.ja.md) は同じトレードで既にもう一方の枝を選んだ |
| `aiir2` CLI を呼び出す薄いラッパーとしての Skill | メンテナンス面 2 つと Vertex 依存の両方が残る。Skill は間接参照以外の何も加えない |
| incident-research に「内部記録」モードを追加 | 信頼モデルと OpSec ルールが正反対（公開 Web の読み取り vs. モデルセッションとローカル出力以外に何も届いてはならない機密内部ログ）。1 つの SKILL.md は両方で開けない。service-research と incident-research を分けたのと同じ理由 |
| MCP サーバーとして再構築 | 決定的な部分（defang・ノンス包み・validate・compile）は stdlib スクリプトであり、ステートフルなエンジンではない。プロンプトワークフロー + スクリプトは Skill である（ADR-003 / [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/ja/adr/0001-agentic-research.ja.md) / [incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/ja/adr/0001-deep-dive-research.ja.md) の路線） |
| 任意の振り返り（障害・プロジェクト）へ汎用化 | スキーマの価値は IR 特有（証拠確度付き戦術・IR フェーズ・IoC 取り扱い）。汎用の会話構造化は meeting-notes が既にカバーしている |

## References

- [ADR-001](https://github.com/nlink-jp/.github/blob/main/adr/001-gemini3-migration.md) — Gemini 2.5 廃止の圧力
- [ADR-004](https://github.com/nlink-jp/.github/blob/main/adr/004-skills-series-umbrella.md) — リポジトリ = skill、配布境界
- [ADR-006](https://github.com/nlink-jp/.github/blob/main/adr/006-skill-validator-vendoring.md) — vendored バリデーター
- [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/ja/adr/0001-agentic-research.ja.md) — CLI → Skill 置き換えパターン、ポインタ付きアーカイブ
- [incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/ja/adr/0001-deep-dive-research.ja.md) — 姉妹スキルのスコープ境界、フィクスチャ規律
- [ai-ir2](https://github.com/nlink-jp/ai-ir2) — 移植したモデル・defang・ノンス隔離の出所
