# Artifact Policy

この文書は、研究コードで生成されるファイルをGit管理するかどうかの方針です。`results/` には論文・発表で参照する評価結果を置き、`output/` にはLLM出力、ベースライン、中間生成物を置く。

## 分類

| 種類 | 例 | Git管理方針 |
|---|---|---|
| 入力データ | `data/aruba.csv`, OpenSHS本体 | 管理しない |
| 秘密情報 | `.env`, APIキー | 管理しない |
| 再現に必要な固定成果物 | 論文で使う代表状態表、採用したLLM出力、最終評価表、掲載図 | 必要最小限だけ管理する |
| 評価結果 | `results/4_adl_detect/`, `results/5_pattern_quality/`, `results/6_adl_match/`, `results/7_param_search/`, `results/e8_30_c_{K}_{hamming}/`, `results/e8_154_p_{K}_{hamming}/` | 論文で使う値だけ残す |
| 一時生成物 | LLM runごとの試行ファイル、再生成できる図、ログ、途中CSV | 原則管理しない |
| 設定・プロンプト | `configs/*.yaml`, `prompts/*.md` | 管理する |

## 出力先

新しく整理された実験では、以下を使う。

```text
results/
├── 4_adl_detect/
├── 5_pattern_quality/
├── 6_adl_match/
│   ├── 15_1_30days/
│   └── 30_1_30days/
├── 7_param_search/
├── e8_30_c_30_2/
└── e8_154_p_30_2/

output/
├── 5_rule_filter/
├── 6_adl_evaluation_30/
├── aruba_15_1_154days/
├── aruba_15_1_30days/
├── llm_direct_15_1_30days/
├── tmp/
└── logs/
```

## 現行ディレクトリの扱い

- `state/`: 現行コードの代表状態テーブル出力。すぐには移動しない。
- `picture/`: 現行コードの図とLLM入力JSON出力。すぐには移動しない。
- `output/`: 現行コードのベースライン、LLM出力、中間生成物。
- `results/`: 評価結果。論文・発表で参照するCSV/JSONのみを置く。

## 運用ルール

1. 論文・発表で使う評価結果は `results/` に置く。
2. 中間生成物、LLM runごとの試行出力、ログ、大量の再生成可能ファイルは `output/` に置く。
3. データセット本体とAPIキーはGit管理しない。
4. 既存の追跡済み生成物を外す場合は、先に `docs/experiment_reproduction.md` の再現手順と必要成果物リストを更新する。
5. 生成物を削除する場合は、論文再現に不要であることを確認してから行う。
