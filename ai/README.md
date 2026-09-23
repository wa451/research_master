# AI作業用の索引

このディレクトリは、コーディングAI／エージェントが安全に実装を調査・変更するための短い作業メモです。研究の目的、実験条件、評価の正本は `docs/` にあり、ここはそれらを置き換えません。

| 調べたいこと | 読むファイル |
|---|---|
| 実装・テスト・仕様への最短経路 | [CODEBASE_MAP.md](CODEBASE_MAP.md) |
| 評価ごとの文書・CLI・実装・テスト | [EVALUATION_ROUTES.md](EVALUATION_ROUTES.md) の該当節のみ |
| 評価4〜10をAIへ説明・引継ぎする | [evaluations/README.md](evaluations/README.md) |
| 採用済みの実装上の判断 | [DECISIONS.md](DECISIONS.md) |
| 研究上の不一致への入口 | [KNOWN_ISSUES.md](KNOWN_ISSUES.md) |
| 前回の作業を再開するときだけ | [CURRENT_STATE.md](CURRENT_STATE.md) |

共通の安全制約と調査順序は、リポジトリ直下の `AGENTS.md` を正本とします。研究判断には必ず `docs/` の対象文書と実装を照合してください。
