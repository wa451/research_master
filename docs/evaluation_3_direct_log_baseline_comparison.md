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
| `output/llm_direct_154/1.json` | LLM単独ベースラインの系列パターンJSON。 |
| `output/llm_direct_154/llm_direct_metrics_154days.csv` | runごとの評価指標CSV。 |
| `output/llm_direct_154/evaluate_direct_log_report.txt` | 評価レポート。 |
| `output/llm_direct_154/evaluate_direct_log_metrics_154days.xlsx` | LLM単独ベースラインの評価指標集計。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx`, `output/llm_direct_154/evaluate_direct_log_metrics_154days.xlsx` | summaryとして、提案手法とLLM単独ベースラインの平均Precision / Recall / F1を並べて見る。 |
| 2 | `output/llm_direct_154/{run}.json`, `output/llm_direct_154/evaluate_direct_log_report.txt` | detailsとして、LLM単独ベースラインの系列内容、抽出数、長すぎる系列や不自然な系列を確認する。 |
| 3 | `configs/default.yaml`, `prompts/direct_log_pattern_extraction_prompt.md`, `docs/paper_parameters.md` | 再現条件として、run数、モデル、入力日数、プロンプトを確認する。 |

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

評価3の比較対象を作るために実行する。

```bash
uv run python scripts/run_direct_log_baseline.py
```

### 4. 🟨 **条件付き** Groundednessを確認する

グラフ上の根拠まで確認する場合のみ実行する。通常の評価3比較だけなら省略できる。

```bash
uv run python scripts/run_groundedness.py
```

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
5. `scripts/run_direct_log_baseline.py` が、同じ前処理と代表状態写像を適用した系列をネットワーク化せずLLMへ直接入力して抽出・評価する。
6. 評価指標は提案手法と同じベースライン系列に対するPrecision / Recall / F1を使う。

## パラメータ

| パラメータ | 値・注意 |
|---|---|
| 代表状態数 `K` | `15` |
| ハミング距離閾値 | `1` |
| 分析期間 | `154`日 |
| LLM run数 | `configs/default.yaml` の `llm.runs_default` に依存する。 |
| LLMモデル | `gemini-2.5-pro` |
| LLM単独出力先 | `output/llm_direct_{DAYS}/` |

`llm.runs_default` が `1` の場合、LLM単独ベースラインは1回実行になる。提案手法と同じく5回で比較する場合は、設定値を変更し、変更内容を記録する。

## 注意点

- 比較時は同じ `K`, ハミング距離、分析期間を使う。
- `llm.runs_default` を変更した場合、他のLLM実行にも影響する可能性がある。
- LLM単独ベースラインの出力先は `output/llm_direct_{DAYS}/` で、提案手法の出力先とは異なる。
- `src/behavior_pattern_mining/evaluation/groundedness_check.py` の既定入力がLLM単独出力向けになっている場合があるため、Groundedness確認時は入力パスを確認する。
