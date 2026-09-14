# 評価3: 提案手法とLLM単独ベースラインの比較

## 評価の要約

提案手法と、センサログに近い入力を直接LLMへ渡すLLM単独ベースラインを比較する。提案手法は状態遷移ネットワークを構造化してLLMに渡す。LLM単独ベースラインは、状態遷移ネットワーク化を介さず、ラベル付きCASASからactivityラベルを除いたセンサーイベント由来の入力で系列パターンを抽出する。

## RQ

| RQ | 内容 |
|---|---|
| RQ3-1 | 状態遷移ネットワークをLLM入力にすることで、前処理済み代表状態系列の直接入力より良い系列抽出ができるか。 |
| RQ3-2 | 提案手法とLLM単独ベースラインでPrecision / Recall / F1はどう変わるか。 |
| RQ3-3 | 前処理済み代表状態系列の直接入力では、長い系列により不安定な出力が増えるか。 |

## 評価指標

| 指標 | 確認すること |
|---|---|
| 遷移確率ベースラインに対するPrecision / Recall / F1 | 遷移確率に基づく系列との一致度。 |
| 頻度ベースラインに対するPrecision / Recall / F1 | 頻出状態系列との一致度。 |
| 出力パターン数 | 前処理済み代表状態系列の直接入力で過剰・過少抽出になっていないか。 |
| run間のばらつき | 同じ条件で複数runを行う場合の安定性。 |
| Groundedness | 必要に応じて、系列が状態遷移グラフ上に根拠を持つかを見る。 |

## 入力と出力

### 入力

| 入力 | 例 | 役割 |
|---|---|---|
| 提案手法の集計 | `output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx` | 比較対象となる提案手法の評価結果。 |
| 状態表 | `state/aruba_15_1_154days.txt` | LLM単独ベースラインでも代表状態化に使う。 |
| ラベル付きCASAS | `new_labeled_data/aruba.txt` | センサーイベント抽出元。activity `begin/end` はLLM入力に渡さない。 |
| センサーマップ | `configs/aruba_sensor_map.json` | `M003` などを部屋名・場所名へ変換する。 |
| 代表状態系列直接入力プロンプト | `prompts/direct_log_pattern_extraction_prompt.md` | LLM単独ベースライン用プロンプト。 |
| APIキー | `.env` | `GEMINI_API_KEY` を設定する。 |

### 出力

| 出力 | 内容 |
|---|---|
| `output/llm_direct_154/{run}.json` | LLM単独ベースラインのrun別系列パターンJSON。 |
| `output/llm_direct_154/llm_direct_metrics_154days.csv` | runごとのモデル、backend、処理時間、token使用量、試行回数を記録するAPIテレメトリCSV。Precision / Recall / F1ではない。 |
| `output/llm_direct_154/evaluate_direct_log_report.txt` | 評価レポート。 |
| `output/llm_direct_154/evaluate_direct_log_metrics_154days.xlsx` | run別Precision / Recall / F1。現在は平均行を持たない（[KI-05](../research/known_issues.md)）。 |
| `output/llm_direct_154/groundedness_all_runs_15_1_154days.csv` | `scripts/run_groundedness.py` 実行時のrun別Groundedness集計。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx`, `output/llm_direct_154/evaluate_direct_log_metrics_154days.xlsx` | 提案手法Excelの平均行と、LLM単独ベースラインExcelのrun別行を確認する。後者の平均はrun別行から別途算出する（[KI-05](../research/known_issues.md)）。 |
| 2 | `output/llm_direct_154/{run}.json`, `output/llm_direct_154/evaluate_direct_log_report.txt` | detailsとして、LLM単独ベースラインの系列内容、抽出数、長すぎる系列や不自然な系列を確認する。 |
| 3 | `configs/default.yaml`, `prompts/direct_log_pattern_extraction_prompt.md`, `docs/research/paper_parameters.md` | 再現条件として、run数、モデル、入力日数、プロンプトを確認する。 |

## 実行手順

### 1. 🟨 **条件付き** 評価2の提案手法5回実行を完了させる

`output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx` がなければ実行する。既に評価2の出力がある場合は再実行しなくてよい。

```bash
uv run python scripts/run_all.py
```

### 2. 🟨 **条件付き** 代表状態表を作成する

`state/aruba_15_1_154days.txt` がなければ実行する。評価2または評価4の準備で作成済みならスキップしてよい。

```bash
uv run python scripts/run_build_network.py
```

### 3. 🟥 **必須** LLM単独ベースラインを実行する

評価3の比較対象を作るために実行する。提案手法と同じ5回分を生成する場合は、設定ファイルを変更せず `--runs 5` を指定する。

```bash
uv run python scripts/run_direct_log_baseline.py --runs 5
```

### 4. 🟨 **条件付き** Groundednessを確認する

グラフ上の根拠まで確認する場合のみ実行する。通常の評価3比較だけなら省略できる。

```bash
uv run python scripts/run_groundedness.py
```

実行時は `output/llm_direct_154/groundedness_all_runs_15_1_154days.csv` を確認する。現在のGroundedness入口はLLM単独出力ディレクトリを既定入力とする。

## 比較対象

| 手法 | 入力 | 主なスクリプト | 出力 |
|---|---|---|---|
| 提案手法 | 時間帯別状態遷移ネットワークJSON | `scripts/run_llm_eval_batch.py` | `output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx` |
| LLM単独ベースライン | ラベル付きCASAS由来のセンサーイベントから作った代表状態系列 | `scripts/run_direct_log_baseline.py` | `output/llm_direct_154/evaluate_direct_log_metrics_154days.xlsx` |

## 処理手順の内部仕様

1. 提案手法は評価2の出力を使う。
2. LLM単独ベースラインは `new_labeled_data/aruba.txt` からセンサーイベントだけを抽出する。
3. activity `begin/end` ラベルはLLM入力から除外する。
4. `configs/aruba_sensor_map.json` でセンサーIDを場所名へ変換する。
5. `scripts/run_direct_log_baseline.py` が、1秒粒度化・遅延OFF・圧縮後の系列をネットワーク化せずLLMへ直接入力して抽出・評価する。現在の最終状態写像は完全一致のみであり、提案手法のハミング写像との不一致は未解決である（[KI-04](../research/known_issues.md)）。
6. 評価指標は遷移確率・頻度ベースラインに対するPrecision / Recall / F1を使う。ただし、評価側のK/hと入力パスの固定箇所は未解決である（[KI-05](../research/known_issues.md)）。

## パラメータ

| パラメータ | 値・注意 |
|---|---|
| 代表状態数 `K` | `15` |
| ハミング距離閾値 | `1` |
| 分析期間 | `154`日 |
| LLM run数 | `--runs` で指定する。省略時は `configs/default.yaml` の `llm.runs_default`（現在 `1`）。評価2と同じ回数なら `--runs 5`。 |
| LLMモデル | `gemini-2.5-pro` |
| LLM単独出力先 | `output/llm_direct_{DAYS}/` |

`--runs` を省略し、`llm.runs_default` が `1` の場合は1回実行になる。提案手法と同じく5回で比較する場合は `--runs 5` を使用し、実行コマンドを記録する。

## 注意点

- 比較時は同じ `K`, ハミング距離、分析期間を使う。
- `--n-states` や `--hamming-threshold` は抽出CLIに存在するが、評価側の固定入力パスへ完全には伝播しないため、非既定条件の比較は未解決である（[KI-05](../research/known_issues.md)）。
- LLM単独ベースラインの出力先は `output/llm_direct_{DAYS}/` で、提案手法の出力先とは異なる。
- `src/behavior_pattern_mining/evaluation/groundedness_check.py` の現在の既定入力はLLM単独出力向けであるため、Groundedness確認時は入力パスを確認する。
- direct-log側と提案手法側の状態写像は現在一致していない（[KI-04](../research/known_issues.md)）。
- 無引数実行の `h=1` と現論文採用条件 `h=0` の関係は未解決である（[KI-01](../research/known_issues.md)）。
