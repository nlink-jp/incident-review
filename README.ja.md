# incident-review

自組織の IR コミュニケーション記録 — Slack エクスポート（scat/stail/
scli）、プレーンテキストの会話ログ、コネクター経由で読み取ったチャネル、
または任意の会話・タイムライン記録 — を事後に振り返り分析し、スキーマ検証
済み JSON レポート（サマリー / 参加者別活動 / 役割推定 / プロセス品質レビ
ュー）と再利用可能な調査戦術ナレッジを生成する Claude Code Skill。
`/incident-review <記録>` で起動します。

[ai-ir](https://github.com/nlink-jp/ai-ir) /
[ai-ir2](https://github.com/nlink-jp/ai-ir2) CLI の後継であり、
[incident-research](https://github.com/nlink-jp/incident-research) の姉妹
スキルです。あちらは *他組織の公知* 事案を Web から調査し、こちらは
*自組織の* 事案を内部記録から完全オフラインでレビューします。設計の要点は
3 つ（設計:
[ADR-009](https://github.com/nlink-jp/.github/blob/main/adr/009-incident-review-skill.md)）:

- **必須の前処理ゲート** — 分析エージェントは生の記録を読みません。
  `preprocess.py` が全 IoC を defang し、全メッセージをノンス付きタグで
  隔離し（攻撃者由来の引用文はデータであり指示ではない）、インジェクション
  疑いをフラグし、あらゆる入力形式を単一のトランスクリプト形式に正規化
  します。
- **入力の汎用化** — 入力の単位はファイル形式ではなく「コミュニケーション
  記録」です。Slack エクスポート・NDJSON・プレーンテキストログはネイティブ
  に読み込み、接続済みシステム内の記録（MCP コネクターで読める Slack
  チャネル等）は逐語的に書き起こして取得し、それ以外は小さな汎用トランス
  クリプト形式で受け付けます。
- **証拠規律付きナレッジ** — 抽出戦術は `confirmed`/`inferred`/`suggested`
  の確度を持ち（`confirmed` は記録内に実際の出力が共有されている場合のみ）、
  フィールド構成は ai-ir2 のナレッジドキュメントと互換です。

分析は設計上オフラインです。記録に登場する URL の取得やホストへの接続は
一切行いません。IoC エンリッチメントはこのスキルの外で意図的に行う別工程
です。

## インストール

リリース zip から（claude.ai → Settings → Skills にそのままアップロード
も可能）:

```bash
unzip incident-review-vX.Y.Z.zip -d ~/.claude/skills/
```

チェックアウトから:

```bash
make install
```

必要環境: Claude Code と `python3`（3.9+、stdlib のみ）。API キーや
クラウドプロジェクトは不要です — ai-ir2 の Vertex AI 依存はなくなりました。

## 使い方

```
/incident-review incident-export.json
/incident-review ticket-thread.json --lang en
```

前処理 → セクション別分析（summary / activity / roles / review /
tactics）→ 検証 → コンパイルのワークフローを経て、`./reports/` に以下を
生成します:

- `<incident_id>_<date>.json` — 構造化レポート（スキーマ:
  `incident-review/schema.json`、セマンティクス:
  `incident-review/references/report-format.md`）
- `<incident_id>_<date>.md` — 人間可読レポート（`--format html` で
  自己完結 HTML）
- `knowledge/<tactic-id>-<slug>.md` — 抽出戦術ごとの RAG 対応ナレッジ
  ドキュメント

レポートはデフォルト日本語、`--lang en` で全フィールド・ラベルが英語に
なります。記録が裏付けない項目は `不明` / `unknown` — 推測はしません。
振り返り専用です: 進行中インシデントのライブ分析や複数インシデントの
傾向分析はスコープ外です。

## 開発

| コマンド | 目的 |
|---------|------|
| `make check`（= `make test`） | 構造検証 + スクリプト挙動テスト |
| `make install` | `~/.claude/skills/incident-review` へコピー |
| `make package` | `dist/incident-review-vX.Y.Z.zip` を作成（zip ルート = スキルフォルダ） |

## ドキュメント

- [入力形式仕様](incident-review/references/input-formats.md)
- [レポート形式仕様](incident-review/references/report-format.md)
- [ADR-009 — 設計決定記録](https://github.com/nlink-jp/.github/blob/main/adr/009-incident-review-skill.md)
- [English documentation](README.md)

## 注意事項

- レビューは記録に含まれる内容のみを反映します — 記録されなかった作業は
  見えません。
- すべての出力内の IoC は defang 済み（`hxxps`, `[.]`）で、レポートは
  安全に共有・索引できます。
- 記録は機密として扱い、分析はローカルマシン内で完結します。

## ライセンス

MIT
